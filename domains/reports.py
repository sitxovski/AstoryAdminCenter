# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""reports.py — «Жалобы игроков»: очередь жалоб игроков на игроков, поданных через бота Discord, и их разбор (шаг А6.11, часть «жалобы»,
22.11.2026; решение владельца №6 — канал = бот Discord; спецификация Reports/admin_center/research_a6_economy_20261121.md §3 строка
А6.11; отчёт impl_a6_econ_20261121.md §А6.11 «жалобы»).

ОТКУДА ЖАЛОБЫ. Бот Oracle (AstoryAdminCenter/DiscordBot, работает на ПК владельца) по команде /report пишет жалобу процедурой
adm.ReportSubmit под логином asda_reports (у него только EXECUTE на adm.ReportSubmit / ReportFileAdd / ReportReplyClaim / ReportReplyDone —
sql/adminc_23_reports.sql). Пределы частоты (3 в час, 10 в сутки, повтор на того же персонажа, 200 в сутки от всех) и сигнатуры
скриншотов проверяют процедуры. Панель читает AsdaAdmin логином asda_admin: SELECT трёх таблиц, UPDATE только столбцов разбора
adm.PlayerReport, INSERT ответа adm.PlayerReportReply; удаления нет нигде.
РАЗБОР — операции core/ops (журнал adm.audit; право reports.handle — owner, admin, gm; просмотр — reports.view):
  report.take   — взять новую жалобу в работу (кто взял — в строке и в журнале);
  report.close  — закрыть с итогом (action — меры приняты, case — передано в дело, no_violation — нарушения нет, duplicate — повтор,
                  insufficient — мало данных) и пояснением; чужую взятую закрывает взявший или admin / owner;
  report.case   — связать жалобу с делом AC-NNNN (дело открывает существующая операция case.open с предзаполнением из жалобы — право ac.case;
                  связь проверяется по joylog1.san.v_cases);
  report.reply  — ответ автору: текст оператора в очередь adm.PlayerReportReply; бот на ПК забирает его раз в минуту и шлёт автору
                  личным сообщением. Автоответов нет: строка появляется только этой операцией. Не больше 5 ответов на жалобу и 20 ответов
                  в час от одного оператора.
КАРТОЧКА: жалоба, скриншоты (байты из базы, тип — заново по сигнатуре), ссылки (только discord.com/channels и вложения CDN Discord — те же
  правила, что у бота), автор Discord ↔ учётка игры (data/ref/discord_links.json — domains/discordlinks), цель — ник → персонаж и учётка
  (Joy1.Charinfo, удалённые — Del_Charinfo), другие жалобы на ту же цель и от того же автора, переходы в карточку учётки (лента журналов,
  античит), персонажа и дела учётки.
Игровые базы — ТОЛЬКО ЧТЕНИЕ (GameReader). Побочных эффектов при импорте нет.
"""
import base64
import datetime
import hashlib
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import acjournal, discordlinks

STATUSES = ("new", "taken", "closed")
FILTERS = ("open", "new", "taken", "closed", "all")
CATEGORIES = {"cheat": "чит / бот", "scam": "мошенничество", "abuse": "оскорбления", "rmt": "торговля за реальные деньги (RMT)", "other": "другое"}
OUTCOMES = {"action": "меры приняты", "case": "передано в дело", "no_violation": "нарушения нет", "duplicate": "повтор", "insufficient": "мало данных"}
NOTE_MIN, NOTE_MAX = 3, 500
REPLY_MAX = 1500
REPLIES_PER_REPORT = 5                 # ответов на одну жалобу
REPLIES_PER_HOUR = 20                  # ответов в час от одного оператора (бюджет на пользователя панели)
STUCK_MIN = 10                         # ответ «бот взял» без итога дольше — «неизвестно, проверьте» (повторно бот его не возьмёт)
PAGE_DEF, PAGE_MAX = 50, 200
RELATED_MAX = 20
SVC_MAX = 5000
CASE_RX = re.compile(r"^AC-(\d{4,6})$")
# ★ те же правила ссылок, что у бота (player_reports.LINK_RX; самотест сверяет тексты): сообщение Discord и вложение CDN Discord
LINK_RX = re.compile(r"^https://(?:(?:ptb\.|canary\.)?discord\.com/channels/\d{15,20}/\d{15,20}(?:/\d{15,20})?"
                     r"|(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/\d{15,20}/\d{15,20}/[A-Za-z0-9._-]{1,100}"
                     r"(?:\?[A-Za-z0-9=&%._-]{0,300})?)$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_CYR = re.compile("[А-Яа-яЁё]")
CYR_SCAN_MAX = 5000                    # ★ ревизия 67 Н-5: кандидатов той же длины с не-ASCII байтами за один поиск ника
RETENTION_DAYS = 90                    # ★ ревизия 67 С-2: байты скриншотов закрытой жалобы хранятся столько суток после закрытия
DB_LIMIT_GB, DB_WARN_GB = 10, 8        # ★ ревизия 67 С-2: потолок SQL Server Express на базу и порог предупреждения в «Состоянии»
REPLY_STATE = {0: "ждёт бота", 1: "бот взял", 2: "отправлено", 3: "не доставлено"}


def _int(v, msg, lo, hi):
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def _rid(v):
    return _int(v, "номер жалобы — целое от 1 до 2147483647", 1, 2 ** 31 - 1)


def _iso(v):
    return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v


def sniff(data):
    """Байты → тип картинки по сигнатуре (как adm.ReportFileAdd) или None."""
    d = bytes(data or b"")
    if d[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if d[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if d[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
        return "image/webp"
    return None


def links_of(text):
    """Поле ссылок жалобы → [{url, ok}]: ok — ссылка по правилам (её можно открыть), иначе — только текстом."""
    out = []
    for tok in re.split(r"\s+", str(text or "").strip()):
        if tok:
            out.append({"url": tok, "ok": bool(LINK_RX.match(tok))})
    return out


def _read(fn):
    """Чтение базы панели: сбой подключения — понятный отказ, а не 500."""
    try:
        cn = db.admin()
    except db.DbError as ex:
        raise OpRefused("жалобы не прочитаны: %s" % ex)
    try:
        return fn(cn)
    except db.DbError as ex:
        raise OpRefused("жалобы не прочитаны: %s" % ex)
    finally:
        cn.close()


def _row(r):
    return {"id": r["id"], "reporter_id": str(r["reporter_id"]), "reporter_name": r["reporter_name"], "target": r["target_name"],
            "category": r["category"], "happened": r["happened"], "body": r.get("body"), "created": _iso(r["created_utc"]), "status": r["status"],
            "taken_by": r["taken_by"], "taken": _iso(r["taken_utc"]), "closed_by": r["closed_by"], "closed": _iso(r["closed_utc"]),
            "outcome": r["outcome"], "outcome_note": r["outcome_note"], "case_no": r["case_no"], "case_by": r["case_by"], "case_at": _iso(r["case_utc"])}


_COLS = ("id, reporter_id, reporter_name, target_name, category, happened, created_utc, status, taken_by, taken_utc, closed_by, closed_utc, "
         "outcome, outcome_note, case_no, case_by, case_utc")


def report_list(q):
    """Очередь: q — status (open | new | taken | closed | all), category, target (ник, начало), reporter (Discord ID), mine (1 — взятые мной:
    login передаёт вызывающий), page, size. Новые и взятые — по номеру сверху вниз (старые первыми), закрытые — новые сверху."""
    q = q or {}
    st = (q.get("status") or "open").strip()
    if st not in FILTERS:
        raise OpRefused("состояние очереди — одно из: %s" % ", ".join(FILTERS))
    cat = (q.get("category") or "").strip()
    if cat and cat not in CATEGORIES:
        raise OpRefused("категория — одна из: %s" % ", ".join(CATEGORIES))
    tgt = (q.get("target") or "").strip()
    if len(tgt) > 20 or _CTRL.search(tgt):
        raise OpRefused("ник цели — до 20 знаков")
    rep = (q.get("reporter") or "").strip()
    if rep and not re.match(r"^\d{15,20}$", rep):
        raise OpRefused("автор — Discord ID (15–20 цифр)")
    size = _int(q.get("size") or PAGE_DEF, "строк на странице — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница — целое от 1 до 100000", 1, 100000)
    where, prm = ["1 = 1"], []
    if st == "open":
        where.append("status IN ('new', 'taken')")
    elif st != "all":
        where.append("status = ?")
        prm.append(st)
    if cat:
        where.append("category = ?")
        prm.append(cat)
    if tgt:
        where.append("target_name LIKE ? ESCAPE '\\'")
        prm.append(re.sub(r"([\\%_\[])", r"\\\1", tgt) + "%")
    if rep:
        where.append("reporter_id = ?")
        prm.append(int(rep))
    if q.get("mine_login"):
        where.append("taken_by = ? AND status = 'taken'")
        prm.append(q["mine_login"])
    order = "id DESC" if st in ("closed", "all") else "id ASC"

    def go(cn):
        w = " AND ".join(where)
        total = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.PlayerReport WHERE " + w, tuple(prm))[0]["n"]
        rows = db.admin_rows(cn, "SELECT %s, (SELECT COUNT(*) FROM adm.PlayerReportFile f WHERE f.report_id = r.id) AS n_files, "
                                 "(SELECT COUNT(*) FROM adm.PlayerReportReply y WHERE y.report_id = r.id) AS n_replies FROM adm.PlayerReport r "
                                 "WHERE %s ORDER BY %s OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % (_COLS, w, order),
                             tuple(prm) + ((page - 1) * size, size))
        counts = {r["status"]: r["n"] for r in db.admin_rows(cn, "SELECT status, COUNT(*) AS n FROM adm.PlayerReport GROUP BY status")}
        return total, rows, counts
    total, rows, counts = _read(go)
    out = []
    for r in rows:
        x = _row(dict(r, body=None))
        x.update(n_files=r["n_files"], n_replies=r["n_replies"])
        out.append(x)
    return {"rows": out, "total": total, "page": page, "pages": max(1, (total + size - 1) // size), "size": size, "status": st,
            "counts": {s: counts.get(s, 0) for s in STATUSES}, "categories": CATEGORIES, "outcomes": OUTCOMES}


def _target(nick, errors):
    """Ник → персонажи (Joy1.Charinfo, удалённые — Del_Charinfo) с учёткой и логином. Латиница — Arabic_CI_AS (без учёта регистра), кириллица — без
    учёта регистра на стороне Python (★ ревизия 67 Н-5)."""
    if not nick:
        return []
    out = []
    try:
        with db.GameReader("joy1") as y:
            p = y.text(nick)
            rows = y.rows("SELECT TOP (10) Userindex, Charidx, Charname, Lvl FROM dbo.Charinfo WHERE Charname = ?", (p,))
            drows = y.rows("SELECT TOP (10) Userindex, Charidx, Charname, Lvl, Edate FROM dbo.Del_Charinfo WHERE Charname = ? ORDER BY Edate DESC", (p,))
            if not rows and not drows and _CYR.search(nick):
                # ★ ревизия 67 Н-5: кириллица в Arabic_CI_AS — байты cp1251, их «регистр» база не знает («вася» ≠ «Вася»). Кандидаты той же длины
                #   с не-ASCII байтами (Arabic_BIN, как charname.taken_sql) читаются и сравниваются в Python без учёта регистра (cp1251 → casefold)
                key = nick.strip().casefold()
                rows = [r for r in y.rows("SELECT TOP (%d) Userindex, Charidx, Charname, Lvl FROM dbo.Charinfo WHERE LEN(Charname) = ? AND "
                                          "Charname COLLATE Arabic_BIN LIKE '%%[^ -~]%%'" % CYR_SCAN_MAX, (len(nick.strip()),))
                        if (r["Charname"] or "").strip().casefold() == key][:10]
                drows = [r for r in y.rows("SELECT TOP (%d) Userindex, Charidx, Charname, Lvl, Edate FROM dbo.Del_Charinfo WHERE LEN(Charname) = ? AND "
                                           "Charname COLLATE Arabic_BIN LIKE '%%[^ -~]%%' ORDER BY Edate DESC" % CYR_SCAN_MAX, (len(nick.strip()),))
                         if (r["Charname"] or "").strip().casefold() == key][:10]
            for r in rows:
                out.append({"uid": int(r["Userindex"]), "idx": int(r["Charidx"]), "name": r["Charname"], "level": r["Lvl"], "deleted": False})
            for r in drows:
                out.append({"uid": int(r["Userindex"]), "idx": int(r["Charidx"]), "name": r["Charname"], "level": r["Lvl"], "deleted": True,
                            "deleted_at": _iso(r["Edate"])})
    except db.DbError as ex:
        errors.append("Joy1 (персонаж по нику): %s" % ex)
        return []
    lg = acjournal._logins([x["uid"] for x in out], errors)
    for x in out:
        x["login"] = lg.get(x["uid"])
        x["service"] = 0 < x["uid"] <= SVC_MAX
    return out


def _reporter(discord_id, errors):
    """Автор Discord → привязка к учётке игры (discord_links.json из файла бота, без паролей) и номер учётки."""
    ln = next((x for x in discordlinks.links() if x.get("discord_id") == str(discord_id)), None)
    if not ln:
        return {"linked": False}
    uid = None
    try:
        with db.GameReader("asdastoryop") as op:
            r = op.one("SELECT Userindex FROM Us_member WHERE Us_id = ?", (op.text(ln["login"]),))
            uid = int(r["Userindex"]) if r else None
    except db.DbError as ex:
        errors.append("AsdaStoryOp (учётка автора): %s" % ex)
    return {"linked": True, "handle": ln.get("handle"), "login": ln.get("login"), "uid": uid, "list_banned": ln.get("banned")}


def _case_info(case_no, errors):
    if not case_no:
        return None
    try:
        with db.GameReader("joylog1") as lg:
            r = lg.one("SELECT case_no, user_index, status, title FROM san.v_cases WHERE case_no = ?", (case_no,))
    except db.DbError as ex:
        errors.append("joylog1.san (дело): %s" % ex)
        return {"case_no": case_no, "found": None}
    if not r:
        return {"case_no": case_no, "found": False}
    return {"case_no": r["case_no"], "found": True, "uid": r["user_index"], "status": r["status"], "title": r["title"]}


def _reply_state(r, now):
    st = int(r["status"])
    if st == 1 and r["claimed_utc"] and (now - r["claimed_utc"]).total_seconds() > STUCK_MIN * 60:
        return "unknown"
    return {0: "queued", 1: "claimed", 2: "sent", 3: "failed"}[st]


def show(rid):
    """Карточка жалобы (см. шапку)."""
    rid = _rid(rid)

    def go(cn):
        r = db.admin_rows(cn, "SELECT %s, body, links FROM adm.PlayerReport WHERE id = ?" % _COLS, (rid,))
        if not r:
            raise OpRefused("жалобы №%d нет" % rid)
        r = r[0]
        files = db.admin_rows(cn, "SELECT id, name, mime, size_bytes, sha256, added_utc, purged_utc FROM adm.PlayerReportFile WHERE report_id = ? ORDER BY id", (rid,))
        reps = db.admin_rows(cn, "SELECT id, text, by_login, created_utc, status, claimed_utc, done_utc, result FROM adm.PlayerReportReply "
                                 "WHERE report_id = ? ORDER BY id", (rid,))
        now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        same_t = db.admin_rows(cn, "SELECT TOP (%d) id, status, category, reporter_name, created_utc FROM adm.PlayerReport WHERE target_name = ? AND id <> ? "
                                   "ORDER BY id DESC" % RELATED_MAX, (r["target_name"], rid))
        n_t = db.admin_rows(cn, "SELECT COUNT(*) AS n, COUNT(DISTINCT reporter_id) AS a FROM adm.PlayerReport WHERE target_name = ? AND id <> ?",
                            (r["target_name"], rid))[0]
        same_a = db.admin_rows(cn, "SELECT TOP (%d) id, status, category, target_name, created_utc FROM adm.PlayerReport WHERE reporter_id = ? AND id <> ? "
                                   "ORDER BY id DESC" % RELATED_MAX, (r["reporter_id"], rid))
        n_a = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.PlayerReport WHERE reporter_id = ? AND id <> ?", (r["reporter_id"], rid))[0]["n"]
        return r, files, reps, now, same_t, n_t, same_a, n_a
    r, files, reps, now, same_t, n_t, same_a, n_a = _read(go)
    errors = []
    x = _row(r)
    x["links"] = links_of(r["links"])
    x["files"] = [{"id": f["id"], "name": f["name"], "mime": f["mime"], "size": f["size_bytes"], "sha256": bytes(f["sha256"]).hex(),
                   "added": _iso(f["added_utc"]), "purged": _iso(f["purged_utc"])} for f in files]
    x["replies"] = [{"id": y["id"], "text": y["text"], "by": y["by_login"], "created": _iso(y["created_utc"]), "state": _reply_state(y, now),
                     "claimed": _iso(y["claimed_utc"]), "done": _iso(y["done_utc"]), "result": y["result"]} for y in reps]
    x["reporter"] = _reporter(r["reporter_id"], errors)
    x["targets"] = _target(r["target_name"], errors)
    x["case"] = _case_info(r["case_no"], errors)
    x["same_target"] = {"total": n_t["n"], "authors": n_t["a"], "rows": [{"id": s["id"], "status": s["status"], "category": s["category"],
                                                                           "reporter_name": s["reporter_name"], "created": _iso(s["created_utc"])} for s in same_t]}
    x["same_author"] = {"total": n_a, "rows": [{"id": s["id"], "status": s["status"], "category": s["category"], "target": s["target_name"],
                                                "created": _iso(s["created_utc"])} for s in same_a]}
    x["errors"] = errors
    x["limits"] = {"replies_per_report": REPLIES_PER_REPORT, "replies_per_hour": REPLIES_PER_HOUR, "stuck_min": STUCK_MIN}
    x["categories"], x["outcomes"] = CATEGORIES, OUTCOMES
    return x


def file_data(fid):
    """Скриншот жалобы → {id, report_id, name, mime, size, sha256, b64}. Тип — заново по сигнатуре; не совпал с записанным или sha256 не тот — отказ."""
    fid = _int(fid, "номер файла — целое от 1 до 2147483647", 1, 2 ** 31 - 1)

    def go(cn):
        return db.admin_rows(cn, "SELECT id, report_id, name, mime, size_bytes, sha256, data, purged_utc FROM adm.PlayerReportFile WHERE id = ?", (fid,))
    r = _read(go)
    if not r:
        raise OpRefused("файла №%d нет" % fid)
    r = r[0]
    if r["purged_utc"] is not None:
        raise OpRefused("скриншот №%d удалён по сроку хранения %s (%d суток после закрытия жалобы), sha256 и размер сохранены" % (
            fid, _iso(r["purged_utc"]), RETENTION_DAYS))
    data = bytes(r["data"])
    if sniff(data) != r["mime"] or hashlib.sha256(data).digest() != bytes(r["sha256"]) or len(data) != r["size_bytes"]:
        raise OpRefused("файл №%d не совпал с записью (тип, размер или sha256) — не показывается" % fid)
    return {"id": r["id"], "report_id": r["report_id"], "name": r["name"], "mime": r["mime"], "size": r["size_bytes"],
            "sha256": hashlib.sha256(data).hexdigest(), "b64": base64.b64encode(data).decode("ascii")}


def _get(cn, rid):
    r = db.admin_rows(cn, "SELECT id, status, taken_by, outcome, case_no, target_name, reporter_id, reporter_name, category FROM adm.PlayerReport "
                          "WITH (UPDLOCK, ROWLOCK) WHERE id = ?", (rid,))
    if not r:
        raise OpRefused("жалобы №%d нет" % rid)
    return r[0]


def _peek(rid):
    def go(cn):
        r = db.admin_rows(cn, "SELECT id, status, taken_by, outcome, case_no, target_name, reporter_id, reporter_name, category FROM adm.PlayerReport "
                              "WHERE id = ?", (rid,))
        if not r:
            raise OpRefused("жалобы №%d нет" % rid)
        return r[0]
    return _read(go)


def _expect(r):
    return {"status": r["status"], "taken_by": r["taken_by"] or "", "case_no": r["case_no"] or ""}


def _same(prev, cur, p=None):
    """Состояние жалобы при записи = предпросмотру (и тому, что видел оператор: p.expect из окна подтверждения)."""
    exp = (prev or {}).get("expect") or {}
    seen = (p or {}).get("expect")
    if exp != _expect(cur) or (seen is not None and seen != _expect(cur)):
        raise OpRefused("жалоба №%d изменилась с предпросмотра — откройте её заново" % cur["id"])


def _text(v, msg, lo, hi):
    """Многострочный текст оператора (переводы строк можно, прочие управляющие символы — нет) → строка, иначе отказ msg."""
    if not isinstance(v, str):
        raise OpRefused(msg)
    s = v.replace("\r\n", "\n").strip()
    if _CTRL.search(s) or len(s) < lo or len(s) > hi:
        raise OpRefused(msg)
    return s


class _RepOp(Operation):
    """Общее: цель журнала, транзакция AsdaAdmin, фиксация после записи журнала (ops._finish)."""
    reversible = False

    def target(self, p):
        return "report:%s" % ((p or {}).get("id"),)

    def _tx(self, ctx, p, prev, fn):
        rid = _rid((p or {}).get("id"))
        cn = db.admin()
        try:
            cn.autocommit = False
            cur = _get(cn, rid)
            _same(prev, cur, p)
            out = fn(cn, cur)
        except BaseException:
            try:
                cn.rollback()
            finally:
                cn.close()
            raise
        out.update(_commit=cn.commit, _close=cn.close)
        return out


@register
class ReportTake(_RepOp):
    name, title, perm = "report.take", "Жалобы: взять в работу", "reports.handle"

    def preview(self, ctx, p):
        r = _peek(_rid((p or {}).get("id")))
        if r["status"] == "closed":
            raise OpRefused("жалоба №%d уже закрыта" % r["id"])
        if r["status"] == "taken":
            raise OpRefused("жалобу №%d уже ведёт %s" % (r["id"], r["taken_by"]) if r["taken_by"] != ctx.login else "жалоба №%d уже у вас" % r["id"])
        return {"text": "взять жалобу №%d (%s на %s) в работу" % (r["id"], CATEGORIES.get(r["category"], r["category"]), r["target_name"]),
                "expect": _expect(r), "warnings": ["пишется только база панели AsdaAdmin (adm.PlayerReport): кто ведёт жалобу"]}

    def apply(self, ctx, p, prev):
        def go(cn, cur):
            n = db.admin_rows(cn, "SET NOCOUNT ON; UPDATE adm.PlayerReport SET status = 'taken', taken_by = ?, taken_utc = SYSUTCDATETIME() "
                                  "WHERE id = ? AND status = 'new'; SELECT @@ROWCOUNT AS n", (ctx.login[:32], cur["id"]))[0]["n"]
            if n != 1:
                raise OpRefused("жалоба №%d уже не новая — откройте её заново" % cur["id"])
            return {"before": _expect(cur), "after": {"id": cur["id"], "status": "taken", "taken_by": ctx.login[:32]},
                    "message": "жалоба №%d взята в работу" % cur["id"]}
        return self._tx(ctx, p, prev, go)


def _may_close(ctx, r):
    if r["status"] == "taken" and r["taken_by"] and r["taken_by"] != ctx.login and ctx.role not in ("owner", "admin"):
        raise OpRefused("жалобу №%d ведёт %s — закрыть может он или администратор" % (r["id"], r["taken_by"]))


def _close_plan(p):
    o = str((p or {}).get("outcome") or "").strip()
    if o not in OUTCOMES:
        raise OpRefused("итог — один из: %s" % ", ".join(OUTCOMES))
    return o, _text((p or {}).get("note"), "пояснение итога — строка от %d до %d знаков" % (NOTE_MIN, NOTE_MAX), NOTE_MIN, NOTE_MAX)


@register
class ReportClose(_RepOp):
    name, title, perm = "report.close", "Жалобы: закрыть с итогом", "reports.handle"

    def preview(self, ctx, p):
        o, note = _close_plan(p)
        r = _peek(_rid((p or {}).get("id")))
        if r["status"] == "closed":
            raise OpRefused("жалоба №%d уже закрыта (итог %s)" % (r["id"], r["outcome"]))
        _may_close(ctx, r)
        if o == "case" and not r["case_no"]:
            raise OpRefused("итог «передано в дело» — сначала свяжите жалобу с делом (кнопка «Открыть дело» или номер AC-NNNN)")
        warn = ["пишется только база панели AsdaAdmin (adm.PlayerReport), автору ничего не отправляется — ответ отдельной кнопкой"]
        if r["status"] == "taken" and r["taken_by"] != ctx.login:
            warn.append("жалобу вёл %s — закрываете вы" % r["taken_by"])
        return {"text": "закрыть жалобу №%d с итогом «%s»: %s" % (r["id"], OUTCOMES[o], note), "expect": _expect(r), "warnings": warn}

    def apply(self, ctx, p, prev):
        o, note = _close_plan(p)

        def go(cn, cur):
            _may_close(ctx, cur)
            if o == "case" and not cur["case_no"]:
                raise OpRefused("итог «передано в дело» — жалоба не связана с делом")
            n = db.admin_rows(cn, "SET NOCOUNT ON; UPDATE adm.PlayerReport SET status = 'closed', closed_by = ?, closed_utc = SYSUTCDATETIME(), "
                                  "outcome = ?, outcome_note = ? WHERE id = ? AND status <> 'closed'; SELECT @@ROWCOUNT AS n",
                              (ctx.login[:32], o, note, cur["id"]))[0]["n"]
            if n != 1:
                raise OpRefused("жалоба №%d уже закрыта" % cur["id"])
            return {"before": _expect(cur), "after": {"id": cur["id"], "status": "closed", "outcome": o, "note": note},
                    "message": "жалоба №%d закрыта: %s" % (cur["id"], OUTCOMES[o])}
        return self._tx(ctx, p, prev, go)


def _case_plan(p):
    c = str((p or {}).get("case") or "").strip().upper()
    if not CASE_RX.match(c):
        raise OpRefused("номер дела — AC-NNNN")
    return c


@register
class ReportCase(_RepOp):
    name, title, perm = "report.case", "Жалобы: связать с делом", "reports.handle"

    def _check(self, ctx, r, c):
        if not ctx.can("ac.case"):
            raise OpRefused("связать жалобу с делом может роль с правом ac.case")
        if r["case_no"]:
            raise OpRefused("жалоба №%d уже связана с делом %s" % (r["id"], r["case_no"]))
        if r["status"] == "closed":
            raise OpRefused("жалоба №%d уже закрыта" % r["id"])
        # ★ ревизия 67 М-2: дело, открытое по жалобе, связывается и тогда, когда жалобу ведёт другой оператор — с отметкой (иначе дело осталось бы
        #   открытым, но не связанным); закрывать чужую жалобу по-прежнему может только взявший или admin / owner
        errs = []
        info = _case_info(c, errs)
        if errs:
            raise OpRefused(errs[0])
        if not info["found"]:
            raise OpRefused("дела %s нет в журнале дел" % c)
        return info

    def preview(self, ctx, p):
        c = _case_plan(p)
        r = _peek(_rid((p or {}).get("id")))
        info = self._check(ctx, r, c)
        warn = ["пишется только база панели AsdaAdmin (adm.PlayerReport): номер дела у жалобы"]
        errs = []
        uids = {t["uid"] for t in _target(r["target_name"], errs) if not t["deleted"]}
        if uids and info["uid"] not in uids:
            warn.append("учётка дела №%s — не учётка персонажа %s из жалобы (%s)" % (info["uid"], r["target_name"], ", ".join("№%d" % u for u in sorted(uids))))
        if r["status"] == "new":
            warn.append("жалоба новая — она будет взята в работу вами")
        elif r["taken_by"] and r["taken_by"] != ctx.login:
            warn.append("жалобу ведёт %s — дело будет связано вами (отметка в журнале), вести жалобу продолжает %s" % (r["taken_by"], r["taken_by"]))
        return {"text": "связать жалобу №%d с делом %s" % (r["id"], c), "expect": _expect(r), "warnings": warn}

    def apply(self, ctx, p, prev):
        c = _case_plan(p)

        def go(cn, cur):
            self._check(ctx, cur, c)
            n = db.admin_rows(cn, "SET NOCOUNT ON; UPDATE adm.PlayerReport SET case_no = ?, case_by = ?, case_utc = SYSUTCDATETIME(), "
                                  "status = CASE WHEN status = 'new' THEN 'taken' ELSE status END, "
                                  "taken_by = CASE WHEN status = 'new' THEN ? ELSE taken_by END, "
                                  "taken_utc = CASE WHEN status = 'new' THEN SYSUTCDATETIME() ELSE taken_utc END "
                                  "WHERE id = ? AND case_no IS NULL AND status <> 'closed'; SELECT @@ROWCOUNT AS n",
                              (c, ctx.login[:32], ctx.login[:32], cur["id"]))[0]["n"]
            if n != 1:
                raise OpRefused("жалоба №%d уже закрыта или связана с делом" % cur["id"])
            return {"before": _expect(cur), "after": {"id": cur["id"], "case_no": c, "by": ctx.login[:32],
                                                      "handled_by_other": bool(cur["taken_by"]) and cur["taken_by"] != ctx.login},
                    "message": "жалоба №%d связана с делом %s" % (cur["id"], c)}
        return self._tx(ctx, p, prev, go)


@register
class ReportReply(_RepOp):
    name, title, perm = "report.reply", "Жалобы: ответ автору через бота", "reports.handle"

    def _budget(self, cn, ctx, rid):
        n_r = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.PlayerReportReply WHERE report_id = ?", (rid,))[0]["n"]
        if n_r >= REPLIES_PER_REPORT:
            raise OpRefused("на жалобу №%d уже %d ответов — больше нельзя" % (rid, n_r))
        n_h = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.PlayerReportReply WHERE by_login = ? AND created_utc > DATEADD(HOUR, -1, SYSUTCDATETIME())",
                            (ctx.login[:32],))[0]["n"]
        if n_h >= REPLIES_PER_HOUR:
            raise OpRefused("за час вы уже поставили %d ответов — предел %d в час" % (n_h, REPLIES_PER_HOUR))

    def preview(self, ctx, p):
        text = _text((p or {}).get("text"), "текст ответа — строка от 1 до %d знаков" % REPLY_MAX, 1, REPLY_MAX)
        r = _peek(_rid((p or {}).get("id")))
        _read(lambda cn: self._budget(cn, ctx, r["id"]))
        return {"text": "ответ автору жалобы №%d (%s, Discord ID %s) личным сообщением бота:\n%s" % (r["id"], r["reporter_name"], r["reporter_id"], text),
                "expect": _expect(r),
                "warnings": ["бот на ПК владельца отправит сообщение в течение минуты, если бот запущен — итог «отправлено / не доставлено» появится в карточке",
                             "текст уходит автору как есть — без подписи оператора"]}

    def apply(self, ctx, p, prev):
        text = _text((p or {}).get("text"), "текст ответа — строка от 1 до %d знаков" % REPLY_MAX, 1, REPLY_MAX)

        def go(cn, cur):
            db.admin_rows(cn, "EXEC sp_getapplock @Resource = N'adm.report.reply', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000")
            self._budget(cn, ctx, cur["id"])
            r = db.admin_rows(cn, "SET NOCOUNT ON; INSERT adm.PlayerReportReply (report_id, text, by_login) OUTPUT INSERTED.id VALUES (?, ?, ?)",
                              (cur["id"], text, ctx.login[:32]))
            yid = int(r[0]["id"])
            return {"before": None, "after": {"id": cur["id"], "reply_id": yid, "text": text},
                    "message": "ответ №%d по жалобе №%d поставлен в очередь бота" % (yid, cur["id"])}
        return self._tx(ctx, p, prev, go)


def db_usage():
    """★ ревизия 67 С-2: размер базы панели AsdaAdmin и доля скриншотов (для «Состояния»): МБ файлов данных, МБ байтов скриншотов (ещё не
    удалённых), их число, удалено по сроку, потолок SQL Express и порог предупреждения. Сбой — {"error": …}, а не исключение."""
    try:
        cn = db.admin()
    except db.DbError as ex:
        return {"error": str(ex)}
    try:
        d = db.admin_rows(cn, "SELECT CAST(SUM(CAST(size AS BIGINT)) * 8 / 1024.0 AS FLOAT) AS mb FROM sys.database_files WHERE type = 0")[0]
        f = db.admin_rows(cn, "SELECT COUNT(*) AS n, CAST(ISNULL(SUM(CASE WHEN purged_utc IS NULL THEN CAST(size_bytes AS BIGINT) ELSE 0 END), 0) "
                              "/ 1048576.0 AS FLOAT) AS mb, SUM(CASE WHEN purged_utc IS NULL THEN 0 ELSE 1 END) AS purged FROM adm.PlayerReportFile")[0]
    except db.DbError as ex:
        return {"error": str(ex)}
    finally:
        cn.close()
    mb = float(d["mb"] or 0)
    smb = float(f["mb"] or 0)
    return {"db_mb": round(mb, 1), "shots_mb": round(smb, 1), "shots_n": int(f["n"] or 0), "shots_purged": int(f["purged"] or 0),
            "shots_share": round(smb / mb * 100, 1) if mb else 0.0, "limit_gb": DB_LIMIT_GB, "warn_gb": DB_WARN_GB,
            "warn": mb >= DB_WARN_GB * 1024, "retention_days": RETENTION_DAYS}


@register
class ReportPurge(Operation):
    """★ ревизия 67 С-2: срок хранения скриншотов — байты закрытых жалоб старше RETENTION_DAYS суток после закрытия → пусто
    (adm.ReportFilePurge; имя, тип, размер и sha256 остаются). Задача службы раз в сутки (core/sched.py DAILY)."""
    name, title, perm, reversible = "reports.purge", "Жалобы: срок хранения скриншотов", "reports.handle", False

    def target(self, p):
        return "reports:files"

    def _run(self, dry):
        def go(cn):
            return db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.ReportFilePurge ?, ?", (RETENTION_DAYS, 1 if dry else 0))[0]
        return _read(go)

    def preview(self, ctx, p):
        r = self._run(True)
        return {"text": "удалить байты %d скриншотов закрытых жалоб старше %d суток после закрытия (%s МБ)" % (
            int(r["files"] or 0), RETENTION_DAYS, "%.1f" % (int(r["bytes"] or 0) / 1048576.0)),
            "expect": {"files": int(r["files"] or 0)}, "warnings": ["имя, тип, размер и sha256 скриншотов остаются в карточке жалобы"]}

    def apply(self, ctx, p, prev):
        r = self._run(False)
        n, b = int(r["files"] or 0), int(r["bytes"] or 0)
        return {"before": None, "after": {"files": n, "bytes": b, "days": RETENTION_DAYS},
                "message": "срок хранения скриншотов: удалены байты %d файлов (%s МБ)" % (n, "%.1f" % (b / 1048576.0))}
