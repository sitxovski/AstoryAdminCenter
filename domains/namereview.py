# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""namereview.py — «Очередь имён»: новые и сменённые имена персонажей за период с проверкой правилами A13 (шаг А6.11, часть «имена»,
22.11.2026; разбор Reports/admin_center/research_a6_economy_20261121.md §1 строка «Правила имён», §3 строка А6.11; отчёт
impl_a6_econ_20261121.md §А6.11). Игровые базы — ТОЛЬКО ЧТЕНИЕ (логин asda_admin); пишется только база панели AsdaAdmin (adm.NameReview).

Откуда очередь
  * joylog1.CharEventCreate — создание персонажа (UPCreateChar, одна строка на персонажа: Edate, Userindex, Charidx, Charname);
  * joylog1.CharEvent с State = 'Rename' — смена имени в игре (UPCharRename пишет её после записи, UPCharRename_a13state.sql:104);
  * AsdaAdmin.adm.audit char.rename / char.rename.undo (итог ok) — смена имени панелью и её откат (domains/rename.py);
  * joylog1.ac.other вид 55 «SQL: имя персонажа нарушает правило (A13)» — сторож A13 сервера (A13_NameGuard, a13_01_migrate.sql §4:
    при Mode = 0 только пишет журнал, имя проходит);
  * Joy1.Charinfo — текущее имя (байтами, CAST … AS varbinary(20)); all = 1 — все текущие имена, не только из событий периода.
Проверка — ТЕМ ЖЕ кодом, что операция char.rename (domains/rename._check_name: правила A13 1–5 domains/charname.rule, сверенные с
корпусом P68; 6 LewdWordList без учёта регистра; 7 занятость по CharPos + Charinfo + Del_Charinfo; учётка-оператор при ExemptOperators —
только латиница, цифры и «_» не в конце; набор символов ≠ 0 — панель имя не проверяет). Таблицы и настройки читаются ОДИН раз на запрос и
подаются этой функции из памяти (_Mem) — без запроса на каждое имя; занятость — словарём по имени (как fn_AsdaNameEq для печатного ASCII:
без учёта регистра и хвостовых пробелов), без перебора пар. Сервер при СОЗДАНИИ проверяет только правила 1–4 (A13_NameGuard область 3:
слова — только при смене имени), при смене — 1–7; панель проверяет все — как смену имени.
Отметка «ок / сменить» — операция names.mark (право names.review): строка adm.NameReview (только INSERT; история не правится) с байтами
имени на момент отметки. Имя изменилось после отметки — отметка недействительна («stale»), имя снова в очереди. «Сменить» само имя не
меняет: смена — существующей операцией char.rename (кнопка «Сменить имя», право players.rename). Правка словаря (A13_CurseWord,
LewdWordList) — набором данных А4, не здесь.
Побочных эффектов при импорте нет.
"""
import datetime
import json
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import acjournal, charname, rename

SVC_MAX = 5000                         # служебные учётки (rename.OPERATOR_MAX_UID)
NAMES_MAX = 100000                     # строк имён одной таблицы (Charinfo / CharPos / Del_Charinfo) — больше: отказ, а не неполная проверка
EVENTS_MAX = 20000                     # событий одного источника за период (больше — пометка capped)
MARKS_MAX = 200000                     # последних отметок (по персонажу)
DAYS_DEF, DAYS_MAX = 30, 366           # период по умолчанию / предел
PAGE_DEF, PAGE_MAX = 50, 200           # строк очереди на странице
EVENTS_PER_ITEM = 20                   # событий персонажа в строке очереди (остальные — числом events_n)
NOTE_MAX = 200                         # длина пояснения к отметке
VERDICTS = ("ok", "rename")            # «ок» / «сменить»
STATES = ("all", "bad", "open", "ok", "rename", "stale")
EVENT_KINDS = ("create", "rename_game", "rename_panel", "a13")
SERVER_RULES = {"create": "1–4", "rename_game": "1–7", "rename_panel": "1–7 (панель)", "a13": "1–7"}
_OPER_TXT = "имя оператора"


class _Mem:
    """Подставной читатель для rename._check_name: настройки A13, слова, LewdWordList, операторы и занятость — из памяти (одно чтение
    таблиц на запрос). Тексты имён — в том же виде, что параметр проверки (байты cp1256 → строка, rename._check_name кодирует обратно)."""

    def __init__(self, cfg, words, lewd, opers, index):
        self.cfg, self.words, self.lewd, self.opers, self.index = cfg, words, lewd, opers, index
        self.uid = None

    def rows(self, sql, params=()):
        if "A13_NameRuleConfig" in sql:
            return [self.cfg] if self.cfg else []
        if "A13_CurseWord" in sql:
            return [{"Word": w} for w in self.words]
        if "LewdWordList" in sql:
            return [{"LewdWord": w} for w in self.lewd]
        if "CharGmInfo" in sql:
            return [{"x": 1}] if params and int(params[0]) in self.opers else []
        if "Del_Charinfo" in sql:                        # charname.taken_sql(): параметр — имя (6 раз)
            return list(self.index.get(name_key(params[0].encode("cp1256")), ()))
        raise RuntimeError("неожиданный запрос проверки имени")


def name_key(b):
    """Ключ занятости как у fn_AsdaNameEq для печатного ASCII: без хвостовых пробелов, без учёта регистра A-Z (Arabic_CI_AS). Имя не
    печатный ASCII — ключ по байтам (сравнение байтов; до занятости такое имя не доходит: правила 3 / 4 и правило оператора)."""
    b = bytes(b or b"").rstrip(b" ")
    if all(32 <= c <= 126 for c in b):
        return b"a:" + bytes(c + 32 if 65 <= c <= 90 else c for c in b)
    return b"b:" + b


def show(b):
    """Байты имени → как его видит игра (cp1251; db.fix_text делает то же для строк Arabic-базы)."""
    return bytes(b or b"").decode("cp1251", "replace")


def rule_of(text):
    """Текст отказа rename._check_name → код: 0 (годно), r1…r7, oper (правило оператора), charset (набор ≠ 0)."""
    if not text:
        return "0"
    m = re.search(r"\(правило (\d)\)$", text)
    if m:
        return "r" + m.group(1)
    if text.startswith("имя занято"):
        return "r7"
    if text.startswith(_OPER_TXT):
        return "oper"
    if text.startswith("набор символов"):
        return "charset"
    return "other"


def _bytes(v):
    return bytes(v) if v is not None else b""


def load_rules(y):
    """Настройки и словари A13, операторы, все имена (Charinfo, CharPos, Del_Charinfo) — одним заходом. → dict для verdict()."""
    cfg, words, lewd = charname.load_config(y)
    sw = (y.rows("SELECT CheckCreate, CheckRename FROM dbo.A13_NameRuleConfig WHERE Id = 1") or [{}])[0]   # для экрана (проверка их не читает)
    opers = {int(r["Userindex"]) for r in y.rows("SELECT DISTINCT UserIndex AS Userindex FROM dbo.CharGmInfo WHERE GMFlag IS NOT NULL")}
    tabs = {}
    for t in ("Charinfo", "CharPos", "Del_Charinfo"):
        rr = y.rows("SELECT TOP (%d) Userindex, Charidx, CAST(Charname AS varbinary(20)) AS nb FROM dbo.%s" % (NAMES_MAX + 1, t))
        if len(rr) > NAMES_MAX:
            raise OpRefused("в Joy1.%s больше %d имён — очередь имён так не считается (предел NAMES_MAX)" % (t, NAMES_MAX))
        tabs[t] = rr
    index = {}
    seen = set()
    for t, dl in (("CharPos", 0), ("Charinfo", 0), ("Del_Charinfo", 1)):
        for r in tabs[t]:
            k = (int(r["Userindex"]), int(r["Charidx"]), dl, name_key(r["nb"]))
            if k in seen:                                    # CharPos и Charinfo с тем же именем — один носитель
                continue
            seen.add(k)
            index.setdefault(k[3], []).append({"Userindex": k[0], "Charidx": k[1], "Charname": show(r["nb"]), "deleted": dl})
    # слова LewdWordList — в виде параметра проверки (байты cp1251 базы → строка cp1256, как имя)
    lewd2 = [str(w).encode("cp1251", "replace").decode("cp1256") for w in lewd if w]
    return {"cfg": cfg, "switches": sw, "words": words, "lewd": lewd2, "opers": opers, "index": index,
            "chars": {(int(r["Userindex"]), int(r["Charidx"])): _bytes(r["nb"]) for r in tabs["Charinfo"]},
            "pos": {(int(r["Userindex"]), int(r["Charidx"])): _bytes(r["nb"]) for r in tabs["CharPos"]}}


def verdict(rules, uid, idx, nb):
    """Проверка имени nb персонажа uid/idx тем же кодом, что char.rename → (код, текст отказа | None)."""
    mem = _Mem(rules["cfg"], rules["words"], rules["lewd"], rules["opers"], rules["index"])
    # own_deleted — своя прежняя строка Del_Charinfo того же слота (удалён и создан заново): слот занят, восстановить её нельзя — не двойник
    why = rename._check_name(mem, uid, idx, bytes(nb).decode("cp1256"), None, own_deleted=(uid, idx))
    return rule_of(why), why


def _period(q, r):
    """Период ГГГГММДД (параметром; по умолчанию DAYS_DEF суток по часам SQL-сервера) → (from, to)."""
    f = acjournal.parse_day(q.get("from"), "from")
    t = acjournal.parse_day(q.get("to"), "to")
    if not f or not t:
        d = r.one("SELECT CONVERT(char(8), DATEADD(DAY, ?, GETDATE()), 112) AS f, CONVERT(char(8), GETDATE(), 112) AS t", (1 - DAYS_DEF,))
        f, t = f or d["f"], t or d["t"]
    if f > t:
        raise OpRefused("дата «с» позже даты «по»")
    if (datetime.datetime.strptime(t, "%Y%m%d") - datetime.datetime.strptime(f, "%Y%m%d")).days + 1 > DAYS_MAX:
        raise OpRefused("период очереди имён — не длиннее %d суток" % DAYS_MAX)
    return f, t


def _int(v, msg, lo, hi):
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def latest_marks(keys=None):
    """Последняя отметка по персонажу → {(uid, idx): строка}. keys — только эти персонажи (иначе все, до MARKS_MAX)."""
    cn = db.admin()
    try:
        sql = ("SELECT TOP (%d) id, Userindex, Charidx, name_bin, verdict, rule_at_mark, note, marked_by, via, marked_local FROM (SELECT *, "
               "ROW_NUMBER() OVER (PARTITION BY Userindex, Charidx ORDER BY id DESC) AS rn FROM adm.NameReview) x WHERE rn = 1" % MARKS_MAX)
        rows = db.admin_rows(cn, sql)
    finally:
        cn.close()
    out = {(int(r["Userindex"]), int(r["Charidx"])): r for r in rows}
    if keys is not None:
        out = {k: v for k, v in out.items() if k in keys}
    return out


def mark_state(mark, cur_b):
    """Состояние отметки для текущего имени: none / ok / rename / stale (имя изменилось после отметки)."""
    if not mark:
        return "none"
    if _bytes(mark["name_bin"]) != bytes(cur_b or b""):
        return "stale"
    return mark["verdict"]


def queue(q):
    """Очередь имён (см. _queue); сбой подключения к базе — понятный отказ, а не 500."""
    try:
        return _queue(q)
    except db.DbError as ex:
        raise OpRefused("очередь имён не прочитана: %s" % ex)


def _queue(q):
    """Очередь имён (см. шапку). q: from, to (ГГГГММДД), all (1 — все текущие имена), state (all | bad | open | ok | rename | stale),
    account (номер или логин), svc (sep | in), page, size. → dict."""
    st = (q.get("state") or "all").strip()
    if st not in STATES:
        raise OpRefused("состояние очереди — одно из: %s" % ", ".join(STATES))
    svc = (q.get("svc") or "sep").strip()
    if svc not in ("sep", "in"):
        raise OpRefused("svc — sep (служебные отдельно) или in (в общем итоге)")
    size = _int(q.get("size") or PAGE_DEF, "строк на странице очереди — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница очереди — целое от 1 до 100000", 1, 100000)
    every = str(q.get("all") or "0") == "1"
    uids_f = acjournal.resolve_account(q.get("account"))
    errors, notes, capped = [], [], {}
    with db.GameReader("joy1") as y:
        f, t = _period(q, y)
        rules = load_rules(y)
    cfg = rules["cfg"] or {}
    if not cfg:
        errors.append("в Joy1 нет строки A13_NameRuleConfig Id = 1 — проверка по умолчаниям (Charset 0, без слов)")
    events = {}

    def add(key, ev):
        if uids_f and key[0] not in uids_f:
            return
        events.setdefault(key, []).append(ev)
    with db.GameReader("joylog1") as lg:
        cond = "Edate >= CONVERT(datetime, ?, 112) AND Edate < DATEADD(DAY, 1, CONVERT(datetime, ?, 112))"
        try:
            rr = lg.rows("SELECT TOP (%d) Edate, Userindex, Charidx, CAST(Charname AS varbinary(20)) AS nb FROM dbo.CharEventCreate WHERE %s "
                         "ORDER BY Edate DESC" % (EVENTS_MAX + 1, cond), (f, t))
            capped["create"] = len(rr) > EVENTS_MAX
            for r in rr[:EVENTS_MAX]:
                add((int(r["Userindex"]), int(r["Charidx"])), {"kind": "create", "at": r["Edate"], "name": show(r["nb"]), "name_hex": _bytes(r["nb"]).hex()})
        except db.DbError as ex:
            errors.append("joylog1.CharEventCreate: %s" % ex)
        try:
            rr = lg.rows("SELECT TOP (%d) Edate, Userindex, Charidx, CAST(Charname AS varbinary(20)) AS nb FROM dbo.CharEvent WHERE %s AND State = ? "
                         "ORDER BY Edate DESC" % (EVENTS_MAX + 1, cond), (f, t, "Rename"))
            capped["rename_game"] = len(rr) > EVENTS_MAX
            for r in rr[:EVENTS_MAX]:
                add((int(r["Userindex"]), int(r["Charidx"])), {"kind": "rename_game", "at": r["Edate"], "name": show(r["nb"]),
                                                               "name_hex": _bytes(r["nb"]).hex()})
        except db.DbError as ex:
            errors.append("joylog1.CharEvent: %s" % ex)
        k55 = next((r["text"] for r in acjournal.catalog()[0]["tables"].get("other", []) if r["n"] == 55), None)
        if k55:
            try:
                rr = lg.rows("SELECT TOP (%d) ev_local, user_index, char_slot, char_name, value1 AS rule_no, value2 AS scope, detail FROM ac.other "
                             "WHERE ev_local >= CONVERT(datetime2, ?, 112) AND ev_local < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)) AND event_kind = ? "
                             "ORDER BY ev_local DESC" % (EVENTS_MAX + 1), (f, t, k55))
                capped["a13"] = len(rr) > EVENTS_MAX
                for r in rr[:EVENTS_MAX]:
                    if r["user_index"] is None or r["char_slot"] is None:
                        continue
                    add((int(r["user_index"]), int(r["char_slot"])), {"kind": "a13", "at": r["ev_local"], "name": r["char_name"],
                                                                      "rule": r["rule_no"], "scope": r["scope"], "detail_text": r["detail"]})
            except db.DbError as ex:
                errors.append("ac.other: %s" % ex)
        else:
            errors.append("в каталоге видов ac.other нет вида 55 (сторож A13) — журнал сторожа не показан")
    marks = {}
    try:
        cn = db.admin()
        try:
            rr = db.admin_rows(cn, "SELECT TOP (%d) id, at, login, action, target, before_json, after_json FROM adm.audit WHERE result = 'ok' "
                                   "AND action IN ('char.rename', 'char.rename.undo') AND at >= CONVERT(datetime2, ?, 112) "
                                   "AND at < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)) ORDER BY id DESC" % (EVENTS_MAX + 1), (f, t))
        finally:
            cn.close()
        capped["rename_panel"] = len(rr) > EVENTS_MAX
        for r in rr[:EVENTS_MAX]:
            m = re.match(r"^char:(\d+)/(\d+)$", r["target"] or "")
            if not m:
                continue
            try:
                a, b = json.loads(r["after_json"] or "{}"), json.loads(r["before_json"] or "{}")
            except ValueError:
                a, b = {}, {}
            add((int(m.group(1)), int(m.group(2))), {"kind": "rename_panel", "at": r["at"], "name": a.get("name"),
                                                     "old": a.get("old") if r["action"] == "char.rename" else b.get("name"),
                                                     "by": r["login"], "audit_id": r["id"], "undo": r["action"].endswith(".undo")})
        marks = latest_marks()
    except db.DbError as ex:
        errors.append("AsdaAdmin (журнал панели и отметки): %s" % ex)
    keys = set(events)
    if every:
        keys |= {k for k in rules["chars"] if not uids_f or k[0] in uids_f}
    items = []
    for k in keys:
        uid, idx = k
        cur = rules["chars"].get(k)
        evs = sorted(events.get(k, []), key=lambda e: e["at"] or datetime.datetime.min, reverse=True)
        it = {"uid": uid, "idx": idx, "last": evs[0]["at"] if evs else None, "cat": "service" if 0 < uid <= SVC_MAX else "player", "exists": cur is not None,
              "events": evs[:EVENTS_PER_ITEM], "events_n": len(evs), "oper": uid in rules["opers"] and bool(cfg.get("ExemptOperators"))}
        if cur is None:
            it.update(name=None, name_hex=None, rule="gone", why="персонажа нет в Charinfo (удалён или перенесён) — проверять нечего",
                      mark=None, state="gone")
        else:
            code, why = verdict(rules, uid, idx, cur)
            mk = marks.get(k)
            ms = mark_state(mk, cur)
            pos = rules["pos"].get(k)
            it.update(name=show(cur), name_hex=cur.hex(), rule=code, why=why, pos_differs=pos is not None and pos != cur,
                      mark=({"id": mk["id"], "verdict": mk["verdict"], "by": mk["marked_by"], "at": mk["marked_local"], "note_text": mk["note"],
                             "name": show(mk["name_bin"]), "rule_at_mark": mk["rule_at_mark"]} if mk else None), state=ms)
        items.append(it)
    tot = {}
    for it in items:
        c = tot.setdefault(it["cat"], {"items": 0, "bad": 0, "open": 0, "ok": 0, "rename": 0, "stale": 0, "gone": 0})
        c["items"] += 1
        if it["state"] == "gone":
            c["gone"] += 1
            continue
        if it["rule"] != "0":
            c["bad"] += 1
        if it["state"] in ("none", "stale"):
            c["open"] += 1
        if it["state"] in ("ok", "rename", "stale"):
            c[it["state"]] += 1

    def keep(it):
        if st == "all":
            return True
        if st == "bad":
            return it["state"] != "gone" and it["rule"] != "0"
        if st == "open":
            return it["state"] in ("none", "stale")
        return it["state"] == st
    sel = [it for it in items if keep(it)]
    # порядок: не прошедшие правила и неотмеченные — сверху, затем по последнему событию (новые сверху), затем по номеру
    sel.sort(key=lambda it: (it["state"] == "gone", it.get("rule") == "0", it["state"] not in ("none", "stale"),
                             -(it["last"].timestamp() if it["last"] else 0), it["uid"], it["idx"]))
    if svc == "sep":
        sel.sort(key=lambda it: it["cat"] == "service")              # служебные — отдельным блоком внизу (порядок внутри сохраняется)
        notes.append("служебные учётки ≤ %d — отдельным итогом и внизу списка (svc=in — вместе)" % SVC_MAX)
    total = len(sel)
    pages = max(1, (total + size - 1) // size)
    rows = sel[(page - 1) * size: page * size]
    logins = acjournal._logins([it["uid"] for it in rows], errors)
    for it in rows:
        it["login"] = logins.get(it["uid"])
    notes.append(("правила — как у смены имени char.rename (1–7); сервер при создании проверяет только 1–4, при смене — 1–7; A13 Mode %d (отказ)"
                  if cfg.get("Mode") == 1 else "правила — как у смены имени char.rename (1–7); сервер при создании проверяет только 1–4, при смене — "
                  "1–7; A13 Mode %d (только журнал ac.other 55, имя проходит)") % int(cfg.get("Mode") or 0))
    return {"from": f, "to": t, "all": every, "state": st, "svc": svc, "rows": rows, "total": total, "page": page, "pages": pages, "size": size,
            "totals": tot, "capped": capped, "config": dict({k: cfg.get(k) for k in ("Mode", "Charset", "CurseWords", "RenameLewdDup", "ExemptOperators")},
                                                           CheckCreate=rules["switches"].get("CheckCreate"), CheckRename=rules["switches"].get("CheckRename")),
            "words": {"curse_ascii": len(rules["words"]), "lewd": len(rules["lewd"])}, "opers": sorted(rules["opers"]),
            "dict_link": "#/shops", "errors": errors, "notes": notes}


def marks_of(uid, idx):
    """История отметок персонажа (новые сверху)."""
    uid = _int(uid, "номер учётки — целое от 1 до 2147483647", 1, 2 ** 31 - 1)
    idx = _int(idx, "слот персонажа — целое от 0 до 255", 0, 255)
    try:
        cn = db.admin()
        try:
            rows = db.admin_rows(cn, "SELECT TOP (200) id, name_bin, verdict, rule_at_mark, note, marked_by, via, marked_local FROM adm.NameReview "
                                     "WHERE Userindex = ? AND Charidx = ? ORDER BY id DESC", (uid, idx))
        finally:
            cn.close()
    except db.DbError as ex:
        raise OpRefused("отметки имени не прочитаны: %s" % ex)
    return [{"id": r["id"], "name": show(r["name_bin"]), "name_hex": _bytes(r["name_bin"]).hex(), "verdict": r["verdict"],
             "rule_at_mark": r["rule_at_mark"], "note_text": r["note"], "by": r["marked_by"], "via": r["via"], "at": r["marked_local"]} for r in rows]


def _plan(p):
    """Параметры отметки → (uid, idx, verdict, note). Отказ — понятной причиной."""
    if not isinstance(p, dict):
        raise OpRefused("неверные параметры отметки имени")
    uid = _int(p.get("uid"), "номер учётки — целое от 1 до 2147483647", 1, 2 ** 31 - 1)
    idx = _int(p.get("idx"), "слот персонажа — целое от 0 до 255", 0, 255)
    v = str(p.get("verdict") or "").strip()
    if v not in VERDICTS:
        raise OpRefused("отметка — ok (имя годно) или rename (сменить)")
    note = p.get("note") or ""
    if not isinstance(note, str) or len(note) > NOTE_MAX or any(ord(c) < 32 for c in note):
        raise OpRefused("пояснение к отметке — строка до %d знаков без переводов строки" % NOTE_MAX)
    return uid, idx, v, note.strip()


def _current(uid, idx):
    """Текущее имя персонажа и его проверка → (байты, код, текст) — тем же кодом, что очередь."""
    with db.GameReader("joy1") as y:
        rules = load_rules(y)
    cur = rules["chars"].get((uid, idx))
    if cur is None:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    code, why = verdict(rules, uid, idx, cur)
    return cur, code, why


@register
class NameMark(Operation):
    name, title, perm, reversible = "names.mark", "Имена: отметка «ок / сменить»", "names.review", False

    def target(self, p):
        return "char:%s/%s" % ((p or {}).get("uid"), (p or {}).get("idx"))

    def preview(self, ctx, p):
        uid, idx, v, note = _plan(p)
        try:
            cur, code, why = _current(uid, idx)
            last = latest_marks({(uid, idx)}).get((uid, idx))
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if last and mark_state(last, cur) == v:
            raise OpRefused("имя уже отмечено так же (отметка №%d, %s)" % (last["id"], last["marked_by"]))
        warn = ["пишется только база панели AsdaAdmin (adm.NameReview), имя персонажа не меняется"]
        if v == "ok" and code != "0":
            warn.append("имя не проходит правило (%s) — отмечено «ок» вручную" % why)
        if v == "rename":
            warn.append("смена имени — отдельной операцией char.rename (кнопка «Сменить имя», право players.rename)")
        if last and mark_state(last, cur) == "stale":
            warn.append("прежняя отметка №%d была для имени %s — имя с тех пор изменилось" % (last["id"], show(last["name_bin"])))
        return {"text": "отметка имени персонажа %d/%d %s: %s" % (uid, idx, show(cur), "ок" if v == "ok" else "сменить"),
                "expect": {"name_hex": cur.hex(), "verdict": v, "rule": code}, "warnings": warn}

    def apply(self, ctx, p, prev):
        uid, idx, v, note = _plan(p)
        try:
            cur, code, _why = _current(uid, idx)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        exp = prev.get("expect") or {}
        if cur.hex() != exp.get("name_hex") or ("expect" in p and (p["expect"] or {}).get("name_hex") != cur.hex()):
            raise OpRefused("имя персонажа изменилось с предпросмотра — повторите проверку")
        cn = db.admin()
        try:
            cn.autocommit = False
            r = db.admin_rows(cn, "SET NOCOUNT ON; INSERT adm.NameReview (Userindex, Charidx, name_bin, verdict, rule_at_mark, note, marked_by, via) "
                                  "OUTPUT INSERTED.id VALUES (?, ?, CONVERT(varbinary(20), ?), ?, ?, ?, ?, ?)",
                              (uid, idx, cur, v, code, note, ctx.login[:32], ctx.via[:8]))
            mid = int(r[0]["id"])
        except BaseException:
            try:
                cn.rollback()
            finally:
                cn.close()
            raise
        return {"before": None, "after": {"id": mid, "uid": uid, "idx": idx, "name_hex": cur.hex(), "verdict": v, "rule": code},
                "message": "имя персонажа %d/%d %s отмечено: %s (№%d)" % (uid, idx, show(cur), "ок" if v == "ok" else "сменить", mid),
                "_commit": cn.commit, "_close": cn.close}
