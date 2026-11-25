# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""feed.py — лента игрока и след предмета по ВСЕМ журналам базы joylog1 (только чтение). 16.11.2026.

КАТАЛОГ ЖУРНАЛОВ строится по метаданным (sys.columns) при первом обращении, а не списком вручную: новая таблица
журнала попадает в ленту сама. Для каждой таблицы берутся:
  столбец игрока  — Userindex | user_index | Userindex1/Userindex2 (журналы соулмейта: SoulMate);
  столбец слота   — Charidx | char_slot | char_idx (если есть — лента персонажа фильтрует по нему);
  столбец времени — первый из TIME_COLS, который есть в таблице И имеет тип даты (Edate у 229 таблиц, ev_local у ac.*);
  серийный номер  — Serial | Uuid | Tserial | Fserial (для следа предмета; равен Joy1.Item.Uuid).
Снято с живой базы 16.11.2026: 247 таблиц, 230 с Userindex, 192 с серийным номером.
Таблицы без столбца игрока и без серийного номера (SoulMateExp/…info/…LevelUp — только Smidx) в ленту не входят.
Побочных эффектов при импорте нет.
"""
import datetime
import threading

from core import db
from domains import refdata

USER_COLS = ("Userindex", "user_index", "Userindex1", "Userindex2")
CHAR_COLS = ("Charidx", "char_slot", "char_idx")
TIME_COLS = ("Edate", "ev_local", "Fdate", "Login", "at", "opened_at", "applied_at", "attached_at", "added_at",
             "Time", "InDate", "GainDate", "Rdate", "created_at")
SERIAL_COLS = ("Serial", "Uuid", "Tserial", "Fserial")
CODE_COLS = ("Code", "item_code", "Code1", "Code2")

# Группы по началу имени таблицы (порядок важен: первое совпадение).
GROUPS = [
    ("ac.", "античит"), ("san.", "дела античита"), ("LogInfo", "входы"), ("PortalInfo", "порталы"),
    ("Money", "золото"), ("Trade", "обмен"), ("PersonalStore", "личная лавка"), ("Exchange", "аукцион"),
    ("BuyNPC", "покупка у NPC"), ("BuyNpc", "покупка у NPC"), ("SellNPC", "продажа NPC"), ("Cash", "премиум-магазин"),
    ("Booster", "бустеры"), ("Bundle", "коробки и наборы"), ("GaCha", "гача"), ("SoulRoulette", "рулетка"),
    ("Upgrade", "улучшение"), ("ItemUpgrade", "улучшение"), ("UpperRefine", "улучшение"), ("ItemUpperRefine", "улучшение"),
    ("Option", "опции"), ("ExtractOption", "опции"), ("TransferOption", "опции"), ("ItemOption", "опции"),
    ("Disassemble", "разбор"), ("Craft", "ремесло"), ("Wastebasket", "корзина (выброшено)"), ("Pick", "подбор"),
    ("Reward", "награды"), ("Episode", "задания"), ("Fame", "звания"), ("UseFame", "звания"), ("Pet", "питомцы"),
    ("SoulMate", "соулмейт"), ("Camp", "лагерь и осада"), ("Fish", "рыбалка"), ("Storeitem", "склад"),
    ("Item_", "предметы (служебные)"), ("Item", "предметы"), ("Use", "использование"), ("LevelUP", "развитие"),
    ("JobChange", "развитие"), ("SkillEvent", "развитие"), ("ExpEvent", "опыт"), ("Char", "персонаж"),
    ("HairChange", "внешность"), ("Admin", "выдача администрацией"), ("Durability", "прочность"),
]

_lock = threading.Lock()
_catalog = None


def _group(name):
    """Группа таблицы для подписи в ленте."""
    short = name.split(".", 1)[1] if name.startswith("dbo.") else name
    for pfx, title in GROUPS:
        if name.startswith(pfx) or short.startswith(pfx):
            return title
    return "прочее"


def catalog(refresh=False):
    """Каталог журналов: [dict(name, group, user, char, time, serial, code, cols)]."""
    global _catalog
    with _lock:
        if _catalog is not None and not refresh:
            return _catalog
        with db.GameReader("joylog1") as lg:
            rows = lg.rows("SELECT s.name AS sch, t.name AS tab, c.name AS col, ty.name AS ty FROM sys.tables t "
                           "JOIN sys.schemas s ON s.schema_id = t.schema_id JOIN sys.columns c ON c.object_id = t.object_id "
                           "JOIN sys.types ty ON ty.user_type_id = c.user_type_id ORDER BY s.name, t.name, c.column_id")
        tabs, types = {}, {}
        for r in rows:
            tabs.setdefault((r["sch"], r["tab"]), []).append(r["col"])
            types[(r["sch"], r["tab"], r["col"])] = r["ty"]
        out = []
        for (sch, tab), cols in sorted(tabs.items()):
            lc = {c.lower(): c for c in cols}
            pick = lambda names: next((lc[n.lower()] for n in names if n.lower() in lc), None)
            # время — только столбец типа даты (у san.cases есть varchar «login», совпадающий с именем Login из LogInfo)
            tlc = {c.lower(): c for c in cols if types[(sch, tab, c)] in ("datetime", "datetime2", "smalldatetime", "date")}
            pick_time = lambda names: next((tlc[n.lower()] for n in names if n.lower() in tlc), None)
            users = [lc[n.lower()] for n in USER_COLS if n.lower() in lc]
            ent = {"name": "%s.%s" % (sch, tab), "sch": sch, "tab": tab, "group": _group("%s.%s" % (sch, tab)),
                   "users": users, "char": pick(CHAR_COLS), "time": pick_time(TIME_COLS), "serial": pick(SERIAL_COLS),
                   "code": pick(CODE_COLS), "cols": cols,
                   # след v2 (19.11): ВСЕ столбцы-номера с типом (у TradeitemTo — Serial и Tserial, у SerialChange — Fserial/Tserial)
                   "serials": [(lc[n.lower()], types[(sch, tab, lc[n.lower()])]) for n in SERIAL_COLS if n.lower() in lc]}
            if users or ent["serial"]:
                out.append(ent)
        _catalog = out
        return out


def _q(ent):
    """[схема].[таблица] для запроса (имена — из sys.tables, не от пользователя)."""
    return "[%s].[%s]" % (ent["sch"].replace("]", "]]"), ent["tab"].replace("]", "]]"))


def _decorate(ent, r):
    """Строка журнала → запись ленты: время, таблица, группа, название предмета, все поля."""
    t = r.get(ent["time"]) if ent["time"] else None
    rec = {"at": t, "table": ent["name"], "group": ent["group"], "fields": r}
    if ent["code"] and r.get(ent["code"]) not in (None, 0, -1):
        rec["item"] = refdata.item(r[ent["code"]])
    return rec


def feed(uid, idx=None, days=30, groups=None, limit=300):
    """Лента учётки (или персонажа idx) за days суток по всем журналам → (записи новые сверху, сводка по таблицам)."""
    since = datetime.datetime.now() - datetime.timedelta(days=max(1, min(int(days), 3650)))
    per_table = max(20, min(int(limit), 2000))
    out, summary, errors = [], [], []
    plan = []                                  # (таблица, текст SELECT, параметры)
    for ent in catalog():
        if not ent["users"] or (groups and ent["group"] not in groups):
            continue
        where = "(" + " OR ".join("[%s] = ?" % u for u in ent["users"]) + ")"
        args = [int(uid)] * len(ent["users"])
        if idx is not None and ent["char"] and ent["users"][0] in ("Userindex", "user_index"):
            where += " AND [%s] = ?" % ent["char"]
            args.append(int(idx))
        if ent["time"]:
            where += " AND [%s] >= ?" % ent["time"]
            args.append(since)
        order = (" ORDER BY [%s] DESC" % ent["time"]) if ent["time"] else ""
        plan.append((ent, "SELECT TOP (%d) * FROM %s WHERE %s%s" % (per_table, _q(ent), where, order), args))
    with db.GameReader("joylog1") as lg:
        results = _batched(lg, plan, errors)
    for ent, rows in results:
        if rows:
            summary.append({"table": ent["name"], "group": ent["group"], "rows": len(rows), "capped": len(rows) >= per_table})
            out.extend(_decorate(ent, r) for r in rows)
    out.sort(key=lambda x: x["at"] or datetime.datetime.min, reverse=True)
    return {"items": out[:limit], "total": len(out), "summary": summary, "errors": errors, "since": since}


BATCH = 40          # SELECT в одном пакете (SQL Server: не больше 2100 параметров; у нас ≤ 4 на SELECT)


def _batched(lg, plan, errors):
    """Выполнить план пакетами по BATCH одним обращением на пакет; сбой пакета → по одному (виновник — в errors)."""
    res = []
    for i in range(0, len(plan), BATCH):
        part = plan[i:i + BATCH]
        try:
            sets = lg.multi(";\n".join(p[1] for p in part), tuple(a for p in part for a in p[2]))
            if len(sets) != len(part):
                raise db.DbError("пакет вернул %d наборов вместо %d" % (len(sets), len(part)))
            res.extend(zip((p[0] for p in part), sets))
        except db.DbError:
            for ent, sql, args in part:
                try:
                    res.append((ent, lg.rows(sql, tuple(args))))
                except db.DbError as ex:
                    errors.append({"table": ent["name"], "error": str(ex)})
    return res


# ───────────────────────── след предмета v2 (19.11.2026; research_items_trace.md §2–§4, решение владельца п.1) ─────────────────────────
# Номер (Item.Uuid) переходит: неполный обмен — новый NEWID у получателя, TradeitemTo.Serial = новый, Tserial = исходный; слияние в
# стопку получателя — Serial = стопка получателя, Tserial = исходный; SerialChange — Fserial → Tserial. След ходит по этим связям
# (глубина ≤ TRACE_DEPTH, набор посещённых, не больше TRACE_MAX номеров). Поиск — по каждому столбцу-номеру таблицы, без CAST по
# столбцу (varchar — сравнение с CAST(? AS varchar(36)), uniqueidentifier — с TRY_CAST(? AS uniqueidentifier)). Временных таблиц нет
# (читатель — только SELECT); сравнение — с параметрами, сортировка столбца не важна.
TRACE_DEPTH = 5
TRACE_MAX = 10
JOURNALS_SINCE = datetime.datetime(2026, 10, 1)       # журналы фактически ведутся с 10.2026 (до — единицы строк; research §1)
LOT_DELETE_DAYS = 14                                  # ItemRelayServer ini\Section.ini [TIME_INFO] ItemDeleteTime (живой, 19.11)


def _norm_serial(serial):
    """GUID 8-4-4-4-12 в верхнем регистре (как Serial журналов) или ValueError."""
    import re
    s = (serial or "").strip().strip("{}").upper()
    if not re.fullmatch(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", s):
        raise ValueError("серийный номер — GUID вида 8-4-4-4-12")
    return s


# Таблицы, где событие означает «предмет уничтожен» (последнее событие номера). Значение — (вид, можно ли вернуть по журналу).
DEATH = {
    "WastebasketGear": ("выброшен", True), "WastebasketFunctional": ("выброшен", True), "WastebasketSowel": ("выброшен", True),
    "WastebasketNostack": ("выброшен", True), "Wastebasketitem": ("выброшен", True),
    "SellNPCGear": ("продан NPC", True), "SellNPC": ("продан NPC", True), "SellNPCFunctional": ("продан NPC", True),
    "SellNPCSowel": ("продан NPC", True), "SellNPCNoStack": ("продан NPC", True),
    "DisassembleUse": ("разобран", True),
    "TimeExpired": ("кончился срок", False), "Item_Delete": ("израсходован ремеслом", False),
}
TIMEOUT_STATE = "Time Out-Delete"                      # ExchangeEvent: лот снят реле по таймауту (до ac0z — без возврата)
BIRTH_PREFIX = ("BuyNPC", "BuyNpc", "CashBuy", "BundleGain", "BoosterGain", "Pick", "Reward", "DisassembleGain", "GaCha",
                "EventGain", "Item_Insert", "AdminitemLog", "SoulRoulette")


def death_of(table, fields):
    """(вид, можно_вернуть) для события уничтожения или None. table — «dbo.Имя»."""
    short = table.split(".", 1)[-1]
    if short in DEATH:
        return DEATH[short]
    if short == "ExchangeEvent" and (fields.get("State") or "").strip() == TIMEOUT_STATE:
        return ("снят с аукциона по таймауту", True)
    return None


def _in_list(col, ty, n):
    """[столбец] IN (…n параметров) без преобразования столбца."""
    one = "TRY_CAST(? AS uniqueidentifier)" if ty == "uniqueidentifier" else "CAST(? AS varchar(36))"
    name = col if "." in col else "[%s]" % col.replace("]", "]]")      # «t.Uuid» — столбец с псевдонимом таблицы
    return "%s IN (%s)" % (name, ", ".join([one] * n))


def _trace_round(lg, serials, errors):
    """Один проход по всем журналам для набора номеров → [(ent, строки)]."""
    plan = []
    for ent in catalog():
        if not ent.get("serials"):
            continue
        where = " OR ".join(_in_list(c, t, len(serials)) for c, t in ent["serials"])
        at = (", CONVERT(varchar(23), [%s], 121) AS [__at]" % ent["time"]) if ent["time"] else ""
        # ★ ревизия 27 К-5: при > 500 строк одного номера в таблице — ПОСЛЕДНИЕ 500 (позднее событие не теряется)
        order = (" ORDER BY [%s] DESC" % ent["time"]) if ent["time"] else ""
        plan.append((ent, "SELECT TOP 500 *%s FROM %s WHERE %s%s" % (at, _q(ent), where, order),
                     [s for _c, _t in ent["serials"] for s in serials]))
    return _batched(lg, plan, errors)


def _row_serials(ent, r):
    """Номера строки журнала по всем её столбцам-номерам (верхний регистр)."""
    out = {}
    for c, _t in ent.get("serials") or []:
        v = r.get(c)
        if v not in (None, ""):
            out[c] = str(v).strip().upper()
    return out


def trace(serial):
    """След предмета v2: все журналы и все столбцы-номера, цепочка через обмен/смену номера, «где сейчас» во всех местах базы,
    ярлык «появился» и объяснение пустого следа. → dict(serial, chain, events, now, summary, errors)."""
    s = _norm_serial(serial)
    errors, events, seen_rows = [], [], set()
    visited, frontier, links = [s], [s], []
    with db.GameReader("joylog1") as lg:
        for depth in range(TRACE_DEPTH + 1):
            if not frontier:
                break
            nxt = []
            for ent, rows in _trace_round(lg, frontier, errors):
                for r in rows:
                    key = (ent["name"], repr(sorted((k, str(v)) for k, v in r.items())))
                    if key in seen_rows:
                        continue
                    seen_rows.add(key)
                    sers = _row_serials(ent, r)
                    rec = _decorate(ent, {k: v for k, v in r.items() if k != "__at"})
                    rec["key"] = r.get("__at")
                    rec["hit"] = sorted({v for v in sers.values() if v in visited or v in frontier})
                    d = death_of(ent["name"], r)
                    if d:
                        rec["death"], rec["recoverable"] = d[0], d[1]
                    if ent["name"].split(".")[-1].startswith(BIRTH_PREFIX):
                        rec["birth"] = True
                    if len(sers) > 1:                     # строка-связь: Serial↔Tserial, Fserial→Tserial
                        rec["link"] = sers
                        links.append({"table": ent["name"], "at": rec["at"], "serials": sers})
                        for v in sers.values():
                            if v not in visited and v not in nxt and len(visited) + len(nxt) < TRACE_MAX:
                                nxt.append(v)
                    events.append(rec)
            visited += nxt
            frontier = nxt
    events.sort(key=lambda x: x["at"] or datetime.datetime.min)
    now = where_now(visited)
    return {"serial": s, "chain": visited, "links": links, "events": events, "now": now,
            "summary": _summary(s, events, now), "errors": errors}


def where_now(serials):
    """Где номера сейчас (Joy1): сумки (и замок аукциона Plate 11/12), оправа совела (Uc1..4), корзина удалённых, лот аукциона
    (Exitem.Eid и его Uc), снимок изъятого панелью (adm.ItemTaken), журнал предметов панели (adm.ItemLedger), копия персонажа."""
    n = len(serials)
    uu = lambda col: _in_list(col, "uniqueidentifier", n)
    vc = lambda col: _in_list(col, "varchar", n)
    uc_any = "(" + " OR ".join(vc("Uc%d" % k) for k in range(1, 5)) + ")"
    a1, a4 = list(serials), list(serials) * 4
    now = {}
    with db.GameReader("joy1") as j:
        now["item"] = j.rows("SELECT Userindex, Charidx, Code, Plate, Posx, Amount, Upcount, GainDate, CONVERT(varchar(36), Uuid) AS Uuid "
                             "FROM Item WHERE %s" % uu("Uuid"), a1)
        for r in now["item"]:
            r["lock"] = int(r["Plate"]) in (11, 12)            # UPItemExchangeLock: на время выставления лота
        now["socket"] = j.rows("SELECT Userindex, Charidx, Code, Plate, Posx, CONVERT(varchar(36), Uuid) AS Uuid, Uc1, Uc2, Uc3, Uc4, "
                               "Cell1, Cell2, Cell3, Cell4 FROM Item WHERE %s" % uc_any, a4)
        now["deleted"] = j.rows("SELECT TOP 20 Edate, Userindex, Charidx, Code, Plate, Posx, Amount, GainDate, CONVERT(varchar(36), Uuid) AS Uuid "
                                "FROM Del_item WHERE %s" % uu("Uuid"), a1) if _has_col(j, "Del_item", "Uuid") else []
        now["deleted_socket"] = j.rows("SELECT TOP 20 Edate, Userindex, Charidx, Code, CONVERT(varchar(36), Uuid) AS Uuid, Uc1, Uc2, Uc3, Uc4 "
                                       "FROM Del_item WHERE %s" % uc_any, a4) if _has_col(j, "Del_item", "Uc1") else []
        now["lots"] = j.rows("SELECT CONVERT(varchar(36), Eid) AS Eid, idx, Gidx, State, Userindex, Charidx, Charname, Code, Plate, Amount, "
                             "Upcount, Sprice, Stime, Gaindate, Fdate FROM Exitem WHERE %s" % uu("Eid"), a1)
        # ★ ревизия 27 М-5: лоты удалённых персонажей (OP_DelChar копирует Exitem в Del_ExItem) и их Uc
        now["deleted_lots"] = j.rows("SELECT TOP 20 Edate, CONVERT(varchar(36), Eid) AS Eid, idx, Userindex, Charidx, Code, Amount, Uc1, Uc2, Uc3, Uc4 "
                                     "FROM Del_ExItem WHERE %s OR %s" % (uu("Eid"), uc_any), a1 + a4) if _has_col(j, "Del_ExItem", "Eid") else []
        now["lot_socket"] = j.rows("SELECT CONVERT(varchar(36), Eid) AS Eid, idx, Userindex, Charidx, Code, Uc1, Uc2, Uc3, Uc4 FROM Exitem "
                                   "WHERE %s" % uc_any, a4)
        has_adm = j.one("SELECT CASE WHEN OBJECT_ID('adm.ItemLedger', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"]
        now["taken"] = j.rows("SELECT t.LedgerId, t.Userindex, t.Charidx, t.Code, t.Plate, t.Posx, t.Amount, l.At, l.Operator, l.UndoneBy, "
                              "t.Uc1, t.Uc2, t.Uc3, t.Uc4 FROM adm.ItemTaken t JOIN adm.ItemLedger l ON l.Id = t.LedgerId WHERE %s OR %s"
                              % (uu("t.Uuid"), "(" + " OR ".join(vc("t.Uc%d" % k) for k in range(1, 5)) + ")"), a1 + a4) if has_adm else []
        now["ledger"] = j.rows("SELECT TOP 50 * FROM adm.ItemLedger WHERE %s ORDER BY Id" % uu("Uuid"), a1) if has_adm else []
        has_map = j.one("SELECT CASE WHEN OBJECT_ID('adm.CharCopyItemMap', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"]
        now["copies"] = j.rows("SELECT TOP 20 * FROM adm.CharCopyItemMap WHERE %s OR %s" % (vc("OldUuid"), vc("NewUuid")),
                               a1 + a1) if has_map else []
    stamp = datetime.datetime.now()
    for r in now["lots"]:
        lot_marks(r, stamp)
    for k in ("item", "socket", "deleted", "deleted_socket", "lots", "lot_socket", "deleted_lots", "taken"):
        for r in now[k]:
            if r.get("Code") is not None:
                r["name"] = refdata.item(r["Code"])["name"]
    for k in ("socket", "deleted_socket", "lot_socket", "deleted_lots", "taken"):
        for r in now[k]:
            r["slot"] = [i for i in range(1, 5) if str(r.get("Uc%d" % i) or "").strip().upper() in serials]
    return now


LOT_OVERDUE = "срок реле прошёл — лот ждёт рестарта реле или отмены владельцем"


def lot_marks(r, stamp=None):
    """Пометки лота Exitem (строка с Gaindate, Fdate): истёк (Fdate прошёл), срок снятия реле и «срок реле прошёл». ★ А6.4 (22.11): вынесено
    из where_now без изменений — тем же пользуется рынок (domains/trade.market). → r."""
    stamp = stamp or datetime.datetime.now()
    r["expired"] = bool(r.get("Fdate") and r["Fdate"] < stamp)
    # снятие реле: 14 суток после регистрации (истёкший при выключенном реле — Fdate + 14 суток); оценка, рестарт реле сдвигает
    r["relay_due"] = (r["Gaindate"] + datetime.timedelta(days=LOT_DELETE_DAYS)) if r.get("Gaindate") else None
    r["relay_due_late"] = (r["Fdate"] + datetime.timedelta(days=LOT_DELETE_DAYS)) if r.get("Fdate") else None   # реле перезапускали после истечения
    r["relay_overdue"] = lot_overdue(r, stamp)
    return r


def lot_overdue(r, stamp=None):
    """★ ревизия 27 М-4: срок реле прошёл (и поздняя оценка Fdate + 14 сут), а лот ещё в Exitem — реле его уже пробовало снять и получило
    Flag 0 (ac0z: владелец был в игре, нет места или перегруз) или не успело: состояние 3 в памяти реле, повтор — только при загрузке реле.
    → текст пометки или None."""
    stamp = stamp or datetime.datetime.now()
    late = r.get("relay_due_late") or r.get("relay_due")
    return LOT_OVERDUE if late and late < stamp else None


def _summary(s, events, now):
    """Ярлыки: появился (первое событие), последнее событие, жив ли, объяснение пустого следа появления."""
    out = {"alive": bool(now["item"] or now["lots"] or now["socket"] or now["lot_socket"]
                         or [t for t in now.get("taken") or [] if not t.get("UndoneBy")]),
           "born": None, "last": None, "explain": []}
    if events:
        f, l = events[0], events[-1]
        out["born"] = {"at": f["at"], "table": f["table"], "birth": bool(f.get("birth"))}
        out["last"] = {"at": l["at"], "table": l["table"], "death": l.get("death")}
    if not any(e.get("birth") for e in events):
        out["explain"] = explain_no_birth(s, now)
    return out


def explain_no_birth(s, now):
    """Почему у номера нет события появления (research §2.1): стартовый набор (CharEventCreate ±5 с от GainDate), совел (извлечение из
    оправы журнала не пишет), до начала журналов, копия / восстановление панелью; иначе — «не подтверждено»."""
    out = []
    rows = now["item"] or now["deleted"]
    if any(str(c.get("NewUuid") or "").upper() == s for c in now.get("copies") or []):
        out.append("копия персонажа панелью (adm.CharCopy, новый номер)")
    for r in rows[:3]:
        g = r.get("GainDate")
        code = int(r.get("Code") or 0)
        if g and g < JOURNALS_SINCE:
            out.append("получен до начала журналов (%s)" % str(g)[:10])
        if 7001 <= code < 20551:
            out.append("совел: возврат из оправы (UPCellobDetach) журнала не пишет")
        if g:
            try:
                with db.GameReader("joylog1") as lg:
                    st = lg.rows("SELECT TOP 1 Edate FROM CharEventCreate WHERE Userindex = ? AND Charidx = ? AND Edate BETWEEN ? AND ?",
                                 (int(r["Userindex"]), int(r["Charidx"]), g - datetime.timedelta(seconds=5), g + datetime.timedelta(seconds=5)))
                with db.GameReader("joy1") as j:
                    rs = j.rows("SELECT TOP 1 RestoredAt FROM adm.CharRestored WHERE Userindex = ? AND NewCharidx = ?",
                                (int(r["Userindex"]), int(r["Charidx"]))) if j.one(
                        "SELECT CASE WHEN OBJECT_ID('adm.CharRestored', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"] else []
            except db.DbError:
                st, rs = [], []
            if st:
                out.append("стартовый набор персонажа (создан %s; UPCreateChar номер в журнал не пишет)" % str(st[0]["Edate"])[:19])
            if rs:
                out.append("персонаж восстановлен панелью из удалённых (adm.CharRestore)")
    if not out:
        out.append("появление не найдено ни в одном журнале — не подтверждено")
    seen = []
    return [x for x in out if not (x in seen or seen.append(x))]


def _has_col(reader, table, col):
    """Есть ли столбец у таблицы Joy1."""
    return bool(reader.rows("SELECT 1 AS x FROM sys.columns WHERE object_id = OBJECT_ID(?) AND name = ?",
                            ("dbo." + table, col)))
