# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
r"""bakdrop.py — уборка служебных копий таблиц и процедур (*_bak_*, AsdaProcBak*, …) в игровых базах (шаг А5.8 волны «Живое управление»,
план §4 Д, §5.1; 21.11.2026).

ЧТО ЕСТЬ. Каталог AsdaAdmin.adm.bakdrop_obj (sql/adminc_17_bakdrop.sql) — единственный источник вердикта: «можно убрать» (drop — доказано
  лишнее: откат копию не читает, её текст дословно в файле отката репозитория или копия пуста), «нужна откату» (rollback — копию читает откат,
  НЕ удаляется никогда), «неизвестно» (unknown — сток оригинала / происхождение не установлено). Объект с «копийным» именем, которого нет в
  каталоге, — тоже «неизвестно». Список и ссылки на копии (выражения, текст модулей, FK, триггеры, синонимы, шаги заданий msdb) — подписанная
  процедура adm.BakState (только чтение).
УДАЛЕНИЕ (db.bakdrop) — только владелец (право db.bakdrop), из браузера — слово bakdrop и свежий код второго фактора, из консоли ПК — ключ
  --confirm-bakdrop; заданием не ставится. Перед удалением обязателен свежий (≤ adm.bakdrop_cfg.fresh_hours) бэкап панели ЭТОЙ базы, прошедший
  RESTORE VERIFYONLY (шаг А5.7), иначе отказ с предложением сделать бэкап. Удаляет подписанная процедура adm.BakDrop: повторная проверка ссылок
  прямо перед DROP, снимок (DDL, строки, размер, файл бэкапа) в adm.bakdrop_log и DROP — одной транзакцией; у логина подписи CONTROL только на
  объекты каталога «можно убрать» — копию «нужна откату» не удалить даже в обход панели.
ОТМЕНЫ НЕТ. Вернуть объект — восстановить бэкап на стенд LocalDB ПК (db stand --id N --keep) и перенести вручную (DDL и строки — из базы
  стенда; снимок DDL — в журнале удаления). Кнопки восстановления на живой сервер нет (как у бэкапов, LIVE_RESTORE_REFUSAL).
Побочных эффектов при импорте нет.
"""
import datetime
import json
import re

from core import auth
from core.ops import Operation, OpRefused, register
from domains import dbbackup

CONFIRM = "bakdrop"
MAX_NAMES = 60
PANEL_DB = "AsdaAdmin"
STATE_TIMEOUT_S = 600
DROP_TIMEOUT_S = 900
VERDICTS = ("drop", "rollback", "unknown")
NAME_RX = re.compile(r"^(?:(?P<sch>[A-Za-z0-9_]{1,128})\.)?(?P<name>[A-Za-z0-9_]{1,128})$")
REF_RX = re.compile(r"(?P<db>[^.,\s]+)\.(?P<sch>[^.,\s]+)\.(?P<name>.+?) \((?P<how>[a-z]+)\)(?:, |$)")
PROC_CODE = re.compile(r"\((508\d\d)\)\s*\(SQL")       # код THROW adm.BakDrop в сообщении драйвера: «… (50805) (SQLExecDirectW)»
NO_UNDO = ("отмены нет: вернуть объект — восстановить бэкап №%d на стенд LocalDB ПК (python asda_admin.py db stand --id %d --keep) и перенести "
           "его вручную (строки — из базы стенда, снимок столбцов или текст процедуры — в журнале удаления adm.bakdrop_log). Бэкап №%d "
           "автоуборка не удалит, пока на него ссылается журнал удаления. До переноса не запускайте стенд другого бэкапа с --drop-kept")
CACHE_S = 60                   # ★ ревизия 48 (мелочь 9): список (поиск по тексту всех модулей, ~10 с) — из памяти не дольше этого
FORCE_MIN_S = 15               # «Обновить» (force) — не чаще раза в столько секунд; удаление сбрасывает память сразу
_CACHE = {"at": None, "data": None}
NEED_BACKUP = ("нет свежего проверенного бэкапа базы %s (не старше %d ч, RESTORE VERIFYONLY пройден) — ничего не удалено, сначала сделайте "
               "бэкап: «Состояние» → «Бэкапы БД» → «Сделать бэкап сейчас» или python asda_admin.py db backup --db %s")

INVENTORY = None      # подмена самотеста: () → (строки adm.BakState, [{db, why}] базы, где ссылки не прочитаны)


def utc_now():
    return dbbackup.utc_now()


def _iso(v):
    return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v


def call(sql, params=(), timeout=60, sets=None):
    """Запрос к AsdaAdmin → (строки первого набора, текст ошибки | None, код THROW 508xx | None). Текст — как у бэкапов (dbbackup._reason,
    без кода в конце); код снимается с исходного сообщения драйвера: по нему отказ правил отличается от сбоя. sets — список, куда сложить
    ВСЕ наборы (adm.BakState отдаёт второй — базы, где ссылки не прочитаны)."""
    import pyodbc
    from core import db
    cn = db.admin()
    rows, err, code = [], None, None
    try:
        cn.timeout = timeout
        cur = cn.cursor()
        try:
            cur.execute(sql, *params) if params else cur.execute(sql)
            while True:
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    got = [dict(zip(cols, r)) for r in cur.fetchall()]
                    if sets is not None:
                        sets.append(got)
                    if not rows:
                        rows = got
                if not cur.nextset():
                    break
        except pyodbc.Error as ex:
            err = dbbackup._reason(ex)
            m = PROC_CODE.search(str(ex.args[1] if len(ex.args) > 1 else ex))
            code = int(m.group(1)) if m else None
    finally:
        cn.close()
    return rows, err, code


def scan():
    """adm.BakState → (строки копий, [{db, why}] базы, где ссылки не прочитаны). Не прочитано — OpRefused."""
    if INVENTORY:
        return INVENTORY()
    sets = []
    rows, err, _code = call("SET NOCOUNT ON; EXEC adm.BakState", (), STATE_TIMEOUT_S, sets)
    if err:
        raise OpRefused("список служебных копий не прочитан: %s" % err)
    if len(sets) < 2:                                  # второй набор — всегда (пусть пустой); нет — старая процедура / сбой драйвера
        raise OpRefused("список служебных копий не прочитан: нет набора «базы, где ссылки не прочитаны»")
    return sets[0], sets[1]


def inventory():
    """Строки adm.BakState (все базы списка, кроме AsdaAdmin) → [dict]. Не прочитано — OpRefused."""
    return scan()[0]


def unread_text(warn):
    return ", ".join("%s (%s)" % (w["db"], w["why"]) for w in warn)


def fresh_hours():
    r = dbbackup._rows("SELECT fresh_hours FROM adm.bakdrop_cfg WHERE id = 1")
    if not r:
        raise OpRefused("настройки уборки копий (adm.bakdrop_cfg) не прочитаны — ничего не удалено")
    return int(r[0]["fresh_hours"])


def backups(dbname):
    """Проверенные бэкапы панели базы (новые сверху) → [dict]."""
    return dbbackup._rows("SELECT TOP 20 id, db, file_path, started_at, finished_at, verified, verified_at, backup_set_id, counts FROM adm.dbbackup "
                          "WHERE db = ? AND status = 'done' AND verified = 1 AND backup_set_id IS NOT NULL ORDER BY id DESC", (dbname,))


def is_fresh(b, hours, now):
    """Бэкап годится для уборки: проверен, набор в истории есть, закончен и проверен не раньше hours часов назад."""
    lim = now - datetime.timedelta(hours=hours)
    return bool(b and b.get("verified") and b.get("backup_set_id") and isinstance(b.get("finished_at"), datetime.datetime)
                and b["finished_at"] >= lim and isinstance(b.get("verified_at"), datetime.datetime) and b["verified_at"] >= lim)


def pick_backup(rows, hours, now, want=None):
    """Свежий проверенный бэкап: заданный номер (want) или самый новый годный → строка | None."""
    for b in rows:
        if want is not None and int(b["id"]) != int(want):
            continue
        if is_fresh(b, hours, now):
            return b
        if want is not None:
            return None
    return None


def refs_of(row):
    """Ссылки на копию из текста adm.BakState → [(база, схема, имя, вид)]."""
    return [(m.group("db"), m.group("sch"), m.group("name"), m.group("how")) for m in REF_RX.finditer(str(row.get("refs") or ""))]


def outer_refs(row, dbname, chosen):
    """Ссылки, которые мешают удалению: все, кроме выражений / текста других выбранных копий той же базы."""
    keys = {k.lower() for k in chosen}
    return [r for r in refs_of(row) if not (r[0].lower() == dbname.lower() and r[3] in ("expr", "text") and ("%s.%s" % (r[1], r[2])).lower() in keys)]


def classify(row):
    """Вердикт для показа: drop / rollback / unknown (+ можно ли выбрать сейчас и почему нет)."""
    v = row.get("verdict") if row.get("verdict") in VERDICTS else "unknown"
    if not row.get("in_catalog"):
        v = "unknown"
    why = None
    if v == "rollback":
        why = "нужна откату: %s" % (row.get("needed_by") or "?")
    elif v == "unknown":
        why = "происхождение не установлено (нет в каталоге или сток) — панель не удаляет"
    elif not row.get("present"):
        why = "на сервере нет"
    elif int(row.get("refs_n") or 0):
        why = "на неё ссылаются: %s" % (row.get("refs") or "?")
    return v, why


def forget():
    """Сбросить память списка (после удаления)."""
    _CACHE["at"], _CACHE["data"] = None, None


def state(force=False):
    """Для карточки и консоли (из памяти не старше CACHE_S; force — заново, но не чаще FORCE_MIN_S)."""
    import time
    now_s = time.monotonic()
    age = None if _CACHE["at"] is None else now_s - _CACHE["at"]
    if age is not None and (age < FORCE_MIN_S or (not force and age < CACHE_S)):
        return dict(_CACHE["data"], cached_s=round(age, 1))
    out = _state()
    if out["read"]:
        _CACHE["at"], _CACHE["data"] = now_s, out
    return dict(out, cached_s=0)


def _state():
    """Копии всех баз (вердикт, размер, даты, происхождение, ссылки), базы без прочитанных ссылок, свежий бэкап по базам, журнал удалений."""
    now = utc_now()
    out = {"now_utc": _iso(now), "read": False, "error": None, "items": [], "dbs": {}, "log": [], "fresh_hours": None, "counts": {},
           "unread": []}
    try:
        rows, warn = scan()
        out["unread"] = [{"db": w["db"], "why": w["why"]} for w in warn]
        hours = fresh_hours()
    except OpRefused as ex:
        out["error"] = str(ex)
        return out
    out["read"], out["fresh_hours"] = True, hours
    for r in rows:
        v, why = classify(r)
        it = {k: _iso(r.get(k)) for k in ("db", "sch", "name", "type", "type_desc", "present", "created_utc", "modified_utc", "rows_n", "kb",
                                           "origin", "needed_by", "ref_file", "evidence", "refs_n", "refs", "in_catalog")}
        it.update(verdict=v, blocked=why, droppable=why is None and v == "drop")
        out["items"].append(it)
        out["counts"][v] = out["counts"].get(v, 0) + (1 if r.get("present") else 0)
    for name in sorted({x["db"] for x in out["items"]}):
        try:
            b = pick_backup(backups(name), hours, now)
            out["dbs"][name] = {"fresh": b and {"id": b["id"], "finished_utc": _iso(b["finished_at"]), "file": b["file_path"],
                                                "age_h": round((now - b["finished_at"]).total_seconds() / 3600, 1)}}
        except Exception as ex:                    # «не прочитано» ≠ «нет»
            out["dbs"][name] = {"fresh": None, "error": "бэкапы базы не прочитаны (%s)" % ex.__class__.__name__}
    try:
        out["log"] = [{k: _iso(v) for k, v in x.items()} for x in dbbackup._rows(
            "SELECT TOP 50 id, db, sch, name, RTRIM(kind) AS kind, rows_n, kb, backup_id, backup_file, by_login, dropped_at, LEN(ddl) AS ddl_len "
            "FROM adm.bakdrop_log ORDER BY id DESC")]
    except Exception as ex:
        out["log_error"] = "журнал удалений не прочитан (%s)" % ex.__class__.__name__
    return out


def rows_snapshot(b):
    """Число строк таблиц из снимка бэкапа (adm.dbbackup.counts) → {«схема.имя» в нижнем регистре: строк} | None (снимка нет / не JSON)."""
    try:
        d = json.loads(b.get("counts") or "")
    except (TypeError, ValueError):
        return None
    return {str(k).lower(): int(v) for k, v in d.items()} if isinstance(d, dict) else None


def names_arg(p):
    """Имена из параметров (names: список или строка через запятую; «имя» — схема dbo) → ['схема.имя'] без повторов."""
    v = p.get("names")
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",") if x.strip()]
    if not isinstance(v, list) or not v:
        raise OpRefused("не выбраны копии для удаления (names — список «схема.имя»)")
    out = []
    for x in v:
        m = NAME_RX.match(str(x).strip())
        if not m:
            raise OpRefused("имя копии %s — только латиница, цифры и «_» (схема.имя) — ничего не удалено" % str(x)[:80])
        n = "%s.%s" % (m.group("sch") or "dbo", m.group("name"))
        if n.lower() not in {o.lower() for o in out}:
            out.append(n)
    if len(out) > MAX_NAMES:
        raise OpRefused("за один раз — не больше %d копий" % MAX_NAMES)
    return out


def _db_arg(p):
    name = str(p.get("db") or "").strip()
    allowed = {x.lower(): x for x in dbbackup.allowed()}
    if not name or name.lower() not in allowed or name.lower() == PANEL_DB.lower():
        raise OpRefused("база %s — не игровая база списка панели (уборка копий в AsdaAdmin не делается) — ничего не удалено" % (name or "—"))
    return allowed[name.lower()]


@register
class DbBakDrop(Operation):
    name, title, perm, reversible = "db.bakdrop", "Служебные копии: удалить (бэкап базы, второе подтверждение)", "db.bakdrop", False
    two_factor, confirm_word = True, CONFIRM          # заданием не ставится (schedule_runner нет): только сейчас, владельцем

    def target(self, p):
        return "bak:%s:%s" % (p.get("db") or "", ",".join(p["names"]) if isinstance(p.get("names"), list) else (p.get("names") or ""))

    def preview(self, ctx, p):
        dbname = _db_arg(p)
        names = names_arg(p)
        allrows, warn = scan()
        if warn:                                       # ★ ревизия 48 С-1: «не прочитано» ≠ «ссылок нет»
            raise OpRefused("ссылки на копии прочитаны не во всех базах (причины — в списке служебных копий) — ничего не удалено: %s"
                            % ", ".join(sorted({w["db"] for w in warn})))
        rows = {("%s.%s" % (r["sch"], r["name"])).lower(): r for r in allrows if str(r["db"]).lower() == dbname.lower()}
        items = []
        for n in names:
            r = rows.get(n.lower())
            if not r:
                raise OpRefused("копии %s нет в списке служебных копий базы %s — ничего не удалено" % (n, dbname))
            v, _why = classify(r)
            if v == "rollback":
                raise OpRefused("копия %s нужна откату (%s), панель её не удаляет — ничего не удалено" % (n, r.get("needed_by") or "?"))
            if v != "drop":
                raise OpRefused("происхождение копии %s не установлено (нет в каталоге или сток), панель её не удаляет — ничего не удалено" % n)
            if not r.get("present"):
                raise OpRefused("копии %s в базе %s нет — ничего не удалено" % (n, dbname))
            bad = outer_refs(r, dbname, names)
            if bad:
                raise OpRefused("на копию %s ссылаются другие объекты (%s) — ничего не удалено"
                                % (n, ", ".join(sorted({"%s.%s.%s" % x[:3] for x in bad})[:8])))
            items.append({"name": n, "type": r["type"], "rows": r.get("rows_n"), "kb": r.get("kb"), "origin": r.get("origin"),
                          "evidence": r.get("evidence"), "modified_utc": _iso(r.get("modified_utc"))})
        hours = fresh_hours()
        now = utc_now()
        want = p.get("backup_id")
        try:
            want = int(want) if want not in (None, "") else None
        except (TypeError, ValueError):
            raise OpRefused("номер бэкапа — число")
        b = pick_backup(backups(dbname), hours, now, want)
        if not b:
            raise OpRefused(NEED_BACKUP % (dbname, hours, dbname))
        late = [x["name"] for x in items if x["modified_utc"] and rows[x["name"].lower()]["modified_utc"] >= b["started_at"]]
        if late:
            raise OpRefused("копия создана или изменена после начала бэкапа №%d (%s) — нужен новый бэкап, ничего не удалено" % (b["id"], ", ".join(late)))
        snap = rows_snapshot(b)                        # ★ ревизия 48 Н-1: строки таблиц против снимка бэкапа (DDL-даты строк не видят)
        moved = [x["name"] for x in items if x["type"] == "U" and (snap is None or snap.get(x["name"].lower()) != int(x["rows"] or 0))]
        if moved:
            raise OpRefused("строки копии не совпадают со снимком бэкапа №%d или снимка нет (%s) — нужен новый бэкап, ничего не удалено"
                            % (b["id"], ", ".join(moved)))
        age = round((now - b["finished_at"]).total_seconds() / 3600, 1)
        return {"text": "удалить служебные копии базы %s: %d (%s), бэкап №%d от %s UTC (%s ч назад)"
                        % (dbname, len(names), ", ".join(names), b["id"], _iso(b["finished_at"])[:16], age),
                "db": dbname, "names": names, "backup_id": int(b["id"]), "backup_file": b["file_path"], "items": items,
                "warnings": [NO_UNDO % (int(b["id"]), int(b["id"]), int(b["id"])),
                             "удаление одной транзакцией: ссылки на копии проверяются ещё раз прямо перед DROP, снимок DDL и строк — в журнале удаления",
                             "удаляются только копии каталога «можно убрать» — у процедуры удаления прав на другие объекты нет"],
                "expect": {"db": dbname, "names": names, "backup_id": int(b["id"])}}

    def apply(self, ctx, p, prev):
        if str(p.get("confirm") or "") != CONFIRM:
            raise OpRefused("нужно подтверждение удаления: слово bakdrop (в панели — ввести слово, в консоли — ключ --confirm-bakdrop)")
        if ctx.via == "web":
            auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())
        elif ctx.via != "cli":
            raise OpRefused("удаление служебных копий — только сейчас: из браузера (слово и второй фактор) или консолью ПК, не заданием")
        rows, err, code = call("SET NOCOUNT ON; EXEC adm.BakDrop @db = ?, @names = ?, @backup_id = ?, @by = ?, @confirm = ?",
                               (prev["db"], json.dumps(prev["names"]), prev["backup_id"], ctx.login[:64], CONFIRM), DROP_TIMEOUT_S)
        if err:
            if code:                                   # отказ правил процедуры (50801…50810): ничего не удалено
                raise OpRefused(err)
            raise RuntimeError("удаление не выполнено (транзакция отменена): %s" % err)
        if len(rows) != len(prev["names"]):
            raise RuntimeError("процедура удаления вернула %d строк журнала вместо %d" % (len(rows), len(prev["names"])))
        forget()
        ids = [int(r["id"]) for r in rows]
        done = ["%s.%s" % (r["sch"], r["name"]) for r in rows]
        return {"before": {"objects": [{k: x[k] for k in ("name", "type", "rows", "kb")} for x in prev["items"]]},
                "after": {"db": prev["db"], "dropped": done, "backup_id": prev["backup_id"], "log_ids": ids, "batch": str(rows[0]["batch"])},
                "message": "удалено служебных копий базы %s: %d (%s), снимок — журнал удаления №%d…%d, бэкап №%d"
                           % (prev["db"], len(done), ", ".join(done), min(ids), max(ids), prev["backup_id"])}

    def verify(self, ctx, p, res):
        after = res.get("after") or {}
        left = [r for r in inventory() if str(r["db"]).lower() == str(after.get("db")).lower() and r.get("present")
                and ("%s.%s" % (r["sch"], r["name"])).lower() in {x.lower() for x in after.get("dropped") or []}]
        if left:
            raise RuntimeError("после удаления копии ещё на месте: %s" % ", ".join("%s.%s" % (r["sch"], r["name"]) for r in left))
