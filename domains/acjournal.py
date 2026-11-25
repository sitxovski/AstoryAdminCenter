# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""acjournal.py — экран «Античит»: журнал joylog1.ac.* целиком (шаг А6.1, 21.11.2026; разбор research_a6_economy_20261121.md §1,
§2.1, §3 строка А6.1; отчёт Reports/admin_center/impl_a6_econ_20261121.md §А6.1). ТОЛЬКО ЧТЕНИЕ (логин asda_admin, db_datareader).

Что даёт
  * events(...) — все 8 таблиц ac.* одной лентой по времени (новые сверху), страницами. Вид — текстом из базы + номер и патч по каталогу
    KindText (domains/acjournal_src.py; ac-journal-p53.md §9). Служебные строки (сервер о себе без учётки: журнал, мост EAC, выключение патча —
    acjournal_src.service_of) по умолчанию скрыты, переключатель service=1 их показывает. Фильтры: учётка (номер или логин), персонаж
    (имя точно), IP (только с правом сетевых данных players.view_net — без права и фильтр по IP отказ, и IP в строках скрыты), таблица,
    вид, сервер, интервал дат ГГГГММДД (параметром, CONVERT(…, 112)).
  * summary(day) — «виды за сутки» по всем таблицам (число, учёток, первое и последнее), топ нарушителей за 7 суток (ac.v_top_offenders —
    тело на живой 21.11: считает ВСЕ строки v_events, служебные тоже; поэтому рядом — своё число нарушений без служебных) и учётки
    за сутки (ac.v_account_daily).
  * Таблицы или представления нет (новая база, откат миграции) — строка в errors, остальное считается.
Тексты видов и имена персонажей в ac.* — NVARCHAR (Юникод): параметры к ним идут как есть, без to_db_text (та нужна только varchar
Arabic-столбцам). Каждое значение — параметром, без склейки строк; имена таблиц и столбцов — только из TABLES ниже.
Побочных эффектов при импорте нет.
"""
import datetime
import re

from core import db
from core.ops import OpRefused
from domains import acjournal_src

# (таблица, столбец вида, свои столбцы, заголовок) — столбцы сняты с живой joylog1 21.11 (sys.columns), совпадают с ac-journal-p53.md §1
TABLES = (
    ("operator_refusal", "refusal_kind", ("gm_flag", "hack_counted"), "отказ операторской команды (P47)"),
    ("identity_mismatch", "logon_kind", ("packet_user_index", "session_user_index"), "несовпадение учётки сессии (P47 B)"),
    ("login_check_refusal", "check_result", ("reason", "acc_exists", "acc_block", "char_ok", "sess_open", "ip_match", "ip_passed",
                                             "client_code", "client_message"), "отказ сверки входа (P50)"),
    ("kick_block", "event_kind", ("disc_type", "disc_type_name", "reason", "counted", "not_counted_reason", "kick_count", "kick_threshold",
                                  "block_hours", "block_sent", "owner_user_index"), "кики и автоблоки (P48)"),
    ("sign_replay", "event_kind", ("handler", "token_client", "token_server", "error_count"), "подпись и повторы пакетов"),
    ("move_combat", "event_kind", ("map_index", "interval_ms", "violation_count", "p_duration", "duration"), "ход и бой"),
    ("other", "event_kind", ("item_code", "value1", "value2", "detail"), "прочее и служебные строки журнала"),
    ("packet_validator", "event_kind", ("action", "op_class", "handler", "frame_size", "size_min", "size_max", "rate_per_sec",
                                        "packets_last_sec", "session_state", "char_owner_user_index"), "проверка пакетов (P55)"),
)
TABLE_NAMES = tuple(t[0] for t in TABLES)
TABLES_EXTRA = {t[0]: t[2] for t in TABLES}                       # таблица → свои столбцы
COMMON = ("event_id", "ev_local", "server_name", "server_port", "user_index", "char_slot", "char_name", "ip", "opcode", "repeat_suppressed")
PAGE = 50                     # строк на страницу по умолчанию
PAGE_MAX = 200                # предел страницы
DEPTH_MAX = 10000             # дальше этой глубины ленты страницы не листаются (сузьте фильтр или интервал)
TOP_N = 30                    # строк топа нарушителей
DAILY_N = 50                  # строк «учётки за сутки»
_DAY = re.compile(r"^\d{8}$")
_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_CAT = None
SERVICE_LIKE = ("журнал:%",)   # служебные тексты не из каталога — по началу (acjournal_src.service_of, без учёта регистра, как CI LIKE)
TOP_VIEW_COLS = ("login", "us_block_now", "kicks", "autoblocks", "sign_replay", "move_combat", "operator_refusals", "identity_mismatches",
                 "login_check_refusals", "other", "packet_validator", "total", "suppressed_repeats", "first_local", "last_local", "char_names")
NO_FILTER = {"uid": None, "char": None, "ip": None, "table": None, "kind": None, "server": None, "from": None, "to": None, "service": False}


def catalog():
    """Каталог видов (на ПК — из исходника, на службе — data/ref/ac_kinds.json) + индекс «таблица, текст → вид»; кэш на процесс."""
    global _CAT
    if _CAT is None:
        cat = acjournal_src.load()
        idx = {(t, r["text"]): r for t, rows in cat["tables"].items() for r in rows}
        _CAT = (cat, idx)
    return _CAT


def kind_info(table, text):
    """Текст вида из базы → {n, patch, service}; текста нет в каталоге — номер неизвестен, патч по началу текста."""
    r = catalog()[1].get((table, text))
    if r:
        return {"n": r["n"], "patch": r["patch"], "service": r["service"], "known": True}
    if text == acjournal_src.UNKNOWN_TEXT:
        return {"n": None, "patch": None, "service": None, "known": False, "hint": acjournal_src.UNKNOWN_HINT}
    return {"n": None, "patch": acjournal_src.patch_of(table, None, text), "service": acjournal_src.service_of(table, None, text), "known": False}


def service_texts(table):
    """Тексты служебных видов таблицы по каталогу (для условия NOT IN)."""
    return [r["text"] for r in catalog()[0]["tables"].get(table, ()) if r["service"]]


def parse_day(s, what):
    """ГГГГММДД → строка (проверена как дата) или None; иначе отказ. what — ключ DAY_MSG (полные тексты отказов для перевода)."""
    if s in (None, ""):
        return None
    s = str(s).strip()
    if not _DAY.match(s):
        raise OpRefused(DAY_MSG[what][0])
    try:
        datetime.datetime.strptime(s, "%Y%m%d")
    except ValueError:
        raise OpRefused(DAY_MSG[what][1] % s[:8])
    return s


# (неверный вид, нет такой даты) — по полю
DAY_MSG = {"from": ("дата «с» — восемь цифр ГГГГММДД", "дата «с»: такого дня нет (%s)"),
           "to": ("дата «по» — восемь цифр ГГГГММДД", "дата «по»: такого дня нет (%s)"),
           "day": ("сутки сводки — восемь цифр ГГГГММДД", "сутки сводки: такого дня нет (%s)")}


def _int(v, msg, lo, hi):
    """Целое из строки запроса в пределах [lo, hi]; иначе отказ полным текстом msg."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def resolve_account(acc):
    """Учётки фильтра → список номеров (или None). Логин — по AsdaStoryOp.Us_member; ★ ревизия 50 п.9: ввод из одних цифр — и номер
    учётки, и логин (обе учётки, если обе есть). Логина нет и это не номер — отказ."""
    acc = (acc or "").strip()
    if not acc:
        return None
    out = []
    if acc.isdigit():
        out.append(_int(acc, "номер учётки журнала — целое от 1 до 2147483647", 1, 2 ** 31 - 1))
    with db.GameReader("asdastoryop") as op:
        r = op.one("SELECT Userindex FROM Us_member WHERE Us_id = ?", (op.text(acc),))
    if r and int(r["Userindex"]) not in out:
        out.append(int(r["Userindex"]))
    if not out:
        raise OpRefused("учётки с логином «%s» нет" % acc[:40])
    return out


def build_filters(q, can_ip):
    """Строка запроса → проверенные фильтры (без SQL). Отказ — понятной причиной."""
    f = {"uid": resolve_account(q.get("account")), "char": (q.get("char") or "").strip() or None,
         "ip": (q.get("ip") or "").strip() or None, "table": (q.get("table") or "").strip() or None,
         "kind": (q.get("kind") or "").strip() or None, "server": (q.get("server") or "").strip() or None,
         "from": parse_day(q.get("from"), "from"), "to": parse_day(q.get("to"), "to"),
         "service": str(q.get("service") or "0") == "1"}
    if f["char"] and len(f["char"]) > 32:
        raise OpRefused("имя персонажа — не длиннее 32 знаков")
    if f["ip"]:
        if not can_ip:
            raise OpRefused("фильтр по IP — только с правом сетевых данных (players.view_net)")
        if not _IP.match(f["ip"]):
            raise OpRefused("IP — четыре числа через точку")
    if f["table"] and f["table"] not in TABLE_NAMES:
        raise OpRefused("таблицы ac.%s в журнале нет" % f["table"][:40])
    if f["kind"]:
        t, sep, txt = f["kind"].partition(":")
        if not sep or t not in TABLE_NAMES or not txt:
            raise OpRefused("вид — «таблица:текст вида» из каталога")
        if f["table"] and f["table"] != t:
            raise OpRefused("вид из другой таблицы, чем выбранная")
        f["kind"] = (t, txt)
        if not f["service"] and kind_info(t, txt)["service"]:    # ★ ревизия 50 п.7: выбран служебный вид — служебные включаются сами
            f["service"], f["service_auto"] = True, True
    if f["server"] and len(f["server"]) > 64:
        raise OpRefused("имя сервера — не длиннее 64 знаков")
    if f["from"] and f["to"] and f["from"] > f["to"]:
        raise OpRefused("дата «с» позже даты «по»")
    return f


def _where(table, kind_col, f):
    """Условие и параметры одной таблицы по фильтрам (имена столбцов — только из TABLES)."""
    cond, args = [], []
    if f["uid"]:
        cond.append("user_index IN (%s)" % ",".join("?" * len(f["uid"]))); args.extend(f["uid"])
    if f["char"]:
        cond.append("char_name = ?"); args.append(f["char"])
    if f["ip"]:
        cond.append("ip = ?"); args.append(f["ip"])
    if f["kind"]:
        cond.append("%s = ?" % kind_col); args.append(f["kind"][1])
    if f["server"]:
        cond.append("server_name = ?"); args.append(f["server"])
    if f["from"]:
        cond.append("ev_local >= CONVERT(datetime2, ?, 112)"); args.append(f["from"])
    if f["to"]:
        cond.append("ev_local < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))"); args.append(f["to"])
    if not f["service"]:
        st = service_texts(table)
        if st:
            cond.append("ISNULL(%s, N'') NOT IN (%s)" % (kind_col, ",".join("?" * len(st)))); args.extend(st)
        for pat in SERVICE_LIKE:                               # тексты не из каталога (старые сборки) — те же правила, что service_of
            cond.append("ISNULL(%s, N'') NOT LIKE ?" % kind_col); args.append(pat)
    return (" WHERE " + " AND ".join(cond)) if cond else "", args


def _tables_for(f):
    """Таблицы ленты по фильтрам."""
    if f["kind"]:
        return [t for t in TABLES if t[0] == f["kind"][0]]
    return [t for t in TABLES if not f["table"] or t[0] == f["table"]]


def events(q, can_ip):
    """Лента журнала: {rows, total, page, pages, size, errors, ip_hidden, service, depth_max}. q — словарь строки запроса."""
    f = build_filters(q, can_ip)
    size = _int(q.get("size") or PAGE, "строк на странице журнала — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница журнала — целое от 1 до %d" % DEPTH_MAX, 1, DEPTH_MAX)
    if page * size > DEPTH_MAX:
        raise OpRefused("дальше %d строк лента не листается — сузьте фильтр или интервал дат" % DEPTH_MAX)
    take = page * size
    rows, total, errors, per = [], 0, [], {}
    with db.GameReader("joylog1") as lg:
        for t, kc, extra, title in _tables_for(f):
            w, args = _where(t, kc, f)
            try:
                n = lg.one("SELECT COUNT(*) AS n FROM ac.%s%s" % (t, w), args)["n"]
                per[t] = n
                total += n
                if n:
                    cols = ", ".join(COMMON + extra)
                    for r in lg.rows("SELECT TOP (%d) %s, %s AS kind_text FROM ac.%s%s ORDER BY ev_local DESC, event_id DESC"
                                     % (take, cols, kc, t, w), args):
                        rows.append(dict(r, table=t))
            except db.DbError as ex:
                errors.append("ac.%s: %s" % (t, ex))
    rows.sort(key=lambda r: (r["ev_local"] or datetime.datetime.min, r["event_id"] or 0), reverse=True)
    rows = rows[(page - 1) * size: take]
    logins = _logins([r["user_index"] for r in rows], errors)
    out = []
    for r in rows:
        k = kind_info(r["table"], r["kind_text"])
        item = {"table": r["table"], "event_id": r["event_id"], "ev_local": r["ev_local"], "server": r["server_name"],
                "port": r["server_port"], "uid": r["user_index"], "login": logins.get(r["user_index"]), "slot": r["char_slot"],
                "char": r["char_name"], "ip": r["ip"] if can_ip else None, "opcode": r["opcode"], "repeat": r["repeat_suppressed"],
                "kind_text": r["kind_text"], "n": k["n"], "patch": k["patch"], "service": k["service"], "known": k["known"],
                "hint": k.get("hint"), "extra": {c: r.get(c) for c in TABLES_EXTRA[r["table"]]}}
        out.append(item)
    # ★ ревизия 50 п.6: страниц не больше, чем помещается в DEPTH_MAX (кнопка «последняя» не ведёт к отказу)
    pages_all = max(1, (total + size - 1) // size)
    pages = min(pages_all, max(1, DEPTH_MAX // size))
    return {"rows": out, "total": total, "per_table": per, "page": page, "size": size, "pages": pages, "pages_capped": pages < pages_all,
            "errors": errors, "ip_hidden": not can_ip, "service": f["service"], "service_auto": bool(f.get("service_auto")),
            "depth_max": DEPTH_MAX}


def _logins(uids, errors):
    """Номер учётки → логин (AsdaStoryOp.Us_member) для строк страницы."""
    ids = sorted({int(u) for u in uids if u is not None})
    if not ids:
        return {}
    try:
        with db.GameReader("asdastoryop") as op:
            return {r["Userindex"]: r["Us_id"] for r in op.rows(
                "SELECT Userindex, Us_id FROM Us_member WHERE Userindex IN (%s)" % ",".join("?" * len(ids)), ids)}
    except db.DbError as ex:
        errors.append("AsdaStoryOp.Us_member: %s" % ex)
        return {}


def summary(day=None):
    """Сводка: виды за сутки (все таблицы), топ нарушителей за 7 суток, учётки за сутки. Ошибка части — в errors."""
    day = parse_day(day, "day")
    errors, kinds = [], []
    with db.GameReader("joylog1") as lg:
        if not day:
            day = lg.one("SELECT CONVERT(char(8), SYSDATETIME(), 112) AS d")["d"]
        for t, kc, _extra, _title in TABLES:
            try:
                for r in lg.rows("SELECT %s AS kind_text, COUNT(*) AS n, COUNT(DISTINCT user_index) AS users, MIN(ev_local) AS first, "
                                 "MAX(ev_local) AS last FROM ac.%s WHERE ev_local >= CONVERT(datetime2, ?, 112) AND ev_local < "
                                 "DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)) GROUP BY %s" % (kc, t, kc), (day, day)):
                    k = kind_info(t, r["kind_text"])
                    kinds.append({"table": t, "kind_text": r["kind_text"], "n": r["n"], "users": r["users"], "first": r["first"],
                                  "last": r["last"], "num": k["n"], "patch": k["patch"], "service": k["service"], "known": k["known"]})
            except db.DbError as ex:
                errors.append("ac.%s: %s" % (t, ex))
        kinds.sort(key=lambda x: (bool(x["service"]), -x["n"]))
        # ★ ревизия 50 п.5: топ выбирается В SQL по числу нарушений без служебных (UNION ALL читаемых таблиц, те же 7 суток по ev_utc,
        #   что у v_top_offenders); представление даёт к нему «всего», блок сейчас, разбивку и имена персонажей
        bad_t = {e.split(":", 1)[0][3:] for e in errors}
        parts, args = [], []
        for t, kc, _extra, _title in TABLES:
            if t in bad_t:
                continue
            w, a = _where(t, kc, NO_FILTER)
            parts.append("SELECT user_index FROM ac.%s%s AND user_index IS NOT NULL AND ev_utc >= DATEADD(DAY, -7, SYSUTCDATETIME())" % (t, w))
            args.extend(a)
        top = []
        if parts:
            try:
                top = lg.rows("SELECT TOP (%d) user_index, COUNT(*) AS violations FROM (%s) x GROUP BY user_index "
                              "ORDER BY COUNT(*) DESC, user_index" % (TOP_N, " UNION ALL ".join(parts)), args)
            except db.DbError as ex:
                errors.append("топ нарушителей не посчитан: %s" % ex)
        view = {}
        if top:
            ids = [r["user_index"] for r in top]
            try:
                view = {r["user_index"]: r for r in lg.rows(
                    "SELECT user_index, login, us_block_now, kicks, autoblocks, sign_replay, move_combat, operator_refusals, identity_mismatches, "
                    "login_check_refusals, other, packet_validator, total, suppressed_repeats, first_local, last_local, char_names "
                    "FROM ac.v_top_offenders WHERE user_index IN (%s)" % ",".join("?" * len(ids)), ids)}
            except db.DbError as ex:
                errors.append("ac.v_top_offenders: %s" % ex)
        for r in top:                                          # учётки нет в представлении (оно не прочиталось) — поля пустые
            v = view.get(r["user_index"], {})
            r.update({k: v.get(k) for k in TOP_VIEW_COLS})
        daily = []
        try:
            daily = lg.rows("SELECT TOP (%d) day_local, user_index, login, operator_refusals, identity_mismatches, login_check_refusals, kicks, "
                            "autoblocks, sign_replay, move_combat, other, packet_validator, total, suppressed_repeats, first_local, last_local "
                            "FROM ac.v_account_daily WHERE day_local = CONVERT(date, ?, 112) ORDER BY total DESC" % DAILY_N, (day,))
        except db.DbError as ex:
            errors.append("ac.v_account_daily: %s" % ex)
    return {"day": day, "kinds": kinds, "kinds_total": sum(k["n"] for k in kinds),
            "kinds_service": sum(k["n"] for k in kinds if k["service"]), "top": top, "daily": daily, "errors": errors}


def servers():
    """Имена серверов-источников в журнале (для выбора фильтра). Ошибка таблицы пропускается."""
    out = set()
    with db.GameReader("joylog1") as lg:
        for t, _kc, _e, _ti in TABLES:
            try:
                out.update(r["server_name"] for r in lg.rows("SELECT DISTINCT server_name FROM ac.%s" % t) if r["server_name"])
            except db.DbError:
                pass
    return sorted(out)


def catalog_public():
    """Каталог для интерфейса: таблицы (заголовок), виды (номер, текст, патч, служебная), источник и его md5."""
    cat = catalog()[0]
    return {"source": cat["source"], "md5": cat["md5"], "unknown_hint": acjournal_src.UNKNOWN_HINT,
            "tables": [{"name": t, "kind_col": kc, "title": ti,
                        "kinds": [{"n": r["n"], "kind": r["text"], "patch": r["patch"], "service": r["service"], "sql": r["sql"]}
                                  for r in cat["tables"].get(t, [])]} for t, kc, _e, ti in TABLES]}
