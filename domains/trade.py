# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""trade.py — раздел «Передачи и рынок» (шаг А6.4, 22.11.2026; разбор research_a6_economy_20261121.md §3 строка А6.4, §1 «Аукцион»,
«Личные лавки», «Обмен»; реверс и отчёт — Reports/admin_center/impl_a6_econ_20261121.md §А6.4). ТОЛЬКО ЧТЕНИЕ игровых баз (asda_admin).

КТО КОМУ (реверс определений процедур Joy1 живой dev 22.11; отчёт §А6.4 шаг 1):
  * обмен (UPItemChange, UPShellItemChange): во ВСЕХ таблицах Trade* Userindex = отдал, Tuserindex = получил; Amount / Ramount — баланс
    владельца строки (From — отдавший, «…To» — получатель, А6.3), поэтому передано = Amount − Ramount строки From. TradeSowel / TradeNoStack
    (пишутся в ветке получателя), TradeGear / TradeFunctional — одна строка на вещь, без пары;
  * лавка (UPSelfStoreBuy): во ВСЕХ PersonalStore* Userindex = ПРОДАВЕЦ, Tuserindex = ПОКУПАТЕЛЬ. Вещь идёт продавец → покупатель
    (PersonalStoreitemFrom: Amount − Ramount; PersonalStoreFunctional: количество = Ramount; Gear / Sowel / Nostack — 1), золото —
    покупатель → продавец (PersonalStoreGoldFrom: строка продавца, Ramount − Amount);
  * аукцион (UPExchangeItemBuy): ExchangeEvent «Purchase at the Exchange» — Userindex = покупатель, Suserindex = продавец, вещь (Ramount −
    Amount) продавец → покупатель, цена лота Gm (Sprice) покупатель → продавец; «Sold out at the Exchange» — зеркало той же сделки у продавца;
  * подарки gp7 (GP7GiftLog): отправитель (sender_userindex) → получатель по имени (Joy1.Charinfo, Arabic_CI_AS, при нескольких — единственный
    байт-в-байт, как сверка «Денег»); передачей считается выданный подарок (state C). Ящик ItemPostBox и отложенные Joy1.gifts отправителя не
    хранят — показываются счётом «в ящике сейчас» (подарок gp7 — по Orderidx = order_id).
ЗЕРКАЛА «…To» не считаются (правило M3: AstoryServer/Tools/Anticheat/ac_metrics_db.is_mirror), их строки показаны отдельным счётом.
ПАРЫ — правило M3 того же модуля без изменений (analyse_pairs + pair_flags, пороги ac_common.THR): ≥ m3_pair_deals записей пары или золото
  ≥ m3_gold_oneway в одну сторону при нуле обратно. Модуль грузится из исходника на ПК или из копии ext/anticheat/ архива выкладки.
  Консольная M3 до 22.11 суммировала Amount (баланс «было») и считала золото лавки продавец → покупатель — исправлена по ревизии 54
  (ac_metrics_db.pair_rows); раздел подаёт правилу свои строки (ещё аукцион и подарки gp7) с тем же направлением и количеством.
СЕТЬ (LogInfo: IP, MAC) — только с правом players.view_net; связь пары — players.link_degree (как в карточке учётки).
ОТКРЫТЫЕ ЛАВКИ живут только в памяти GameServer — показать нельзя (пометка); журнал Log_SelfStore — через белый список domains/logs.py.
СЛУЖЕБНЫЕ учётки ≤ 5000 — отдельно (пара, цепочка или сделка со служебной стороной), svc=in — в общем списке и итоге.
Каждое значение — параметром; даты ГГГГММДД — CONVERT(datetime2, ?, 112); имена таблиц — только константы модуля; в тексте SQL нет русских
букв. Нет таблицы — строка в errors, остальное считается. Побочных эффектов при импорте нет.
"""
import datetime
import os
import re
import threading

from core import db
from core.ops import OpRefused
from domains import acjournal, econ, feed, players, refdata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = os.path.dirname(ROOT)
AC_SRC = os.path.join(PORT, "AstoryServer", "Tools", "Anticheat")          # исходник правила M3 (ac_metrics_db.py, ac_common.py, db_connect.py) на ПК
AC_EXT = os.path.join(ROOT, "ext", "anticheat")            # его копия в дереве службы — на сервере только она (★ ревизия 56 С-1, domains/acsrc)
AC_FILES = ("ac_metrics_db.py", "ac_common.py", "db_connect.py")
GOLD = econ.GOLD                     # код золота
CATS = econ.CATS                     # игрок > 5000 / служебная ≤ 5000
GROUPS = ("trade", "store", "auction", "gift")             # обмен / лавка / аукцион / подарок gp7
EDGE_MAX = 20000                     # строк одного источника за период (больше — пометка capped)
PAGE_DEF, PAGE_MAX, PAGES_MAX = 50, 200, 100000            # передачи и история: строк на странице / предел / страниц
PAIRS_MAX = 100                      # пар в ответе (в каждом списке)
CHAIN_HOPS = 5                       # шагов в цепочке не больше
CHAINS_MAX = 50                      # цепочек в ответе
CHAIN_WORK = 200000                  # цепочек-кандидатов (дальше — пометка capped)
CHAIN_K = 4                          # ★ ревизия 54 В-1: продолжений на учётку (ветки первого шага цепочки)
CHAIN_TIME_S = 3.0                   # ★ ревизия 54 В-1: предел времени разбора цепочек на запрос (дальше — пометка capped)
SERIALS_MAX = 50                     # серийников с цепочкой в ответе
NET_ROWS = 50000                     # строк LogInfo за один запрос
NET_GROUPS_MAX = 100                 # групп «один IP / MAC — разные учётки»
LOTS_MAX = 500                       # живых лотов в ответе
HIST_DEPTH = 10000                   # история аукциона листается до стольких строк
STORE_ROWS = 200                     # сделок лавок в ответе
LOG_EVENTS = 300                     # событий журнала лавок в ответе
GIFT_NAMES_MAX = 500                 # разных получателей подарков за период
PURCHASE, SOLD = "Purchase at the Exchange", "Sold out at the Exchange"     # ExchangeEvent.State (UPExchangeItemBuy)
TO_DELETE, TO_RETURN = "Time Out-Delete", "Time Out-Return"                  # ExchangeEvent.State (UPTimeoutDeleteItem): удалён без возврата / возвращён
FEE_STATES = (("commission", "Commission at the Exchange", -1),             # ItemEvent Code 20551 (UPExchangeItemBuy): сбор с продавца
              ("refund", "Commision Refund on a registration", 1))          # (UPItemExchangeRestore): возврат сбора (опечатка оригинала)
OPEN_NOTE = ("открытые сейчас лавки хранятся только в памяти GameServer (в базе и журналах текущего состояния нет) — показать нельзя")
_TBL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_PAIR = re.compile(r"^(\d{1,10})-(\d{1,10})$")
_N1 = "CAST(1 AS BIGINT)"
_NULLS = {"name": "CAST(NULL AS VARCHAR(20))", "code": "CAST(NULL AS INT)", "serial": "CAST(NULL AS VARCHAR(36))"}
WINDOW = "Edate >= CONVERT(datetime2, ?, 112) AND Edate < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))"

# Источники передач (НЕ зеркала): key — имя в ответе, table — JoyLog1.dbo.<table>, group, what (gold / item; у TradeItemFrom Code 20551 —
# золото всей кучкой), g* — отдавший (учётка, персонаж, имя), r* — получивший, qty — сколько передано (SQL), code, serial, extra — условие.
EDGES = (
    {"key": "TradeGoldFrom", "table": "TradeGoldFrom", "group": "trade", "what": "gold", "gu": "Userindex", "gc": "Charidx", "gn": "Fromname",
     "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": "(CAST(Amount AS BIGINT) - CAST(Ramount AS BIGINT))", "serial": "Serial",
     "proc": "UPItemChange"},
    {"key": "TradeShellGoldFrom", "table": "TradeShellGoldFrom", "group": "trade", "what": "gold", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": "(CAST(Amount AS BIGINT) - CAST(Ramount AS BIGINT))",
     "serial": "Serial", "proc": "UPShellItemChange"},
    {"key": "TradeItemFrom", "table": "TradeItemFrom", "group": "trade", "what": "item", "gu": "Userindex", "gc": "Charidx", "gn": "Fromname",
     "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": "(CAST(Amount AS BIGINT) - CAST(Ramount AS BIGINT))", "code": "Code",
     "serial": "Serial", "proc": "UPItemChange"},
    {"key": "TradeGear", "table": "TradeGear", "group": "trade", "what": "item", "gu": "Userindex", "gc": "Charidx", "gn": "Fromname",
     "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": _N1, "code": "Code", "serial": "Serial", "proc": "UPShellItemChange"},
    {"key": "TradeFunctional", "table": "TradeFunctional", "group": "trade", "what": "item", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": "CAST(Amount AS BIGINT)", "code": "Code", "serial": "Serial",
     "proc": "UPShellItemChange"},
    {"key": "TradeSowel", "table": "TradeSowel", "group": "trade", "what": "item", "gu": "Userindex", "gc": "Charidx", "gn": "Fromname",
     "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": _N1, "code": "Code", "serial": "Serial", "proc": "UPItemChange"},
    {"key": "TradeNoStack", "table": "TradeNoStack", "group": "trade", "what": "item", "gu": "Userindex", "gc": "Charidx", "gn": "Fromname",
     "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": _N1, "code": "Code", "serial": "Serial", "proc": "UPItemChange"},
    {"key": "PersonalStoreitemFrom", "table": "PersonalStoreitemFrom", "group": "store", "what": "item", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": "(CAST(Amount AS BIGINT) - CAST(Ramount AS BIGINT))",
     "code": "Code", "serial": "Serial", "proc": "UPSelfStoreBuy"},
    {"key": "PersonalStoreFunctional", "table": "PersonalStoreFunctional", "group": "store", "what": "item", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": "CAST(Ramount AS BIGINT)", "code": "Code", "serial": "Serial",
     "proc": "UPSelfStoreBuy"},
    {"key": "PersonalStoreGear", "table": "PersonalStoreGear", "group": "store", "what": "item", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": _N1, "code": "Code", "serial": "Serial", "proc": "UPSelfStoreBuy"},
    {"key": "PersonalStoreSowel", "table": "PersonalStoreSowel", "group": "store", "what": "item", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": _N1, "code": "Code", "serial": "Serial", "proc": "UPSelfStoreBuy"},
    {"key": "PersonalStoreNostack", "table": "PersonalStoreNostack", "group": "store", "what": "item", "gu": "Userindex", "gc": "Charidx",
     "gn": "Fromname", "ru": "Tuserindex", "rc": "Tcharidx", "rn": "Toname", "qty": _N1, "code": "Code", "serial": "Serial", "proc": "UPSelfStoreBuy"},
    # золото лавки — строка ПРОДАВЦА (Userindex), платит покупатель (Tuserindex): направление обратное столбцам
    {"key": "PersonalStoreGoldFrom", "table": "PersonalStoreGoldFrom", "group": "store", "what": "gold", "gu": "Tuserindex", "gc": "Tcharidx",
     "gn": "Toname", "ru": "Userindex", "rc": "Charidx", "rn": "Fromname", "qty": "(CAST(Ramount AS BIGINT) - CAST(Amount AS BIGINT))",
     "serial": "Serial", "proc": "UPSelfStoreBuy"},
    # аукцион — строка покупателя «Purchase at the Exchange»: вещь от продавца (Suserindex), цена лота Gm — продавцу
    #   ★ ревизия 54 Н-1: у снаряжения и совелов (Plate 1) в Item.Amount = 0 — строка «Purchase» даёт 0 → одна вещь (как _N1 у TradeGear)
    {"key": "ExchangeItem", "table": "ExchangeEvent", "group": "auction", "what": "item", "gu": "Suserindex", "gc": "Scharidx", "gn": "Scharname",
     "ru": "Userindex", "rc": "Charidx", "rn": None, "qty": "(CASE WHEN CAST(Ramount AS BIGINT) - CAST(Amount AS BIGINT) > 0 THEN "
     "CAST(Ramount AS BIGINT) - CAST(Amount AS BIGINT) ELSE CAST(1 AS BIGINT) END)", "code": "Code", "serial": "Serial",
     "extra": "State = 'Purchase at the Exchange'", "proc": "UPExchangeItemBuy"},
    {"key": "ExchangeGold", "table": "ExchangeEvent", "group": "auction", "what": "gold", "gu": "Userindex", "gc": "Charidx", "gn": None,
     "ru": "Suserindex", "rc": "Scharidx", "rn": "Scharname", "qty": "CAST(Gm AS BIGINT)", "extra": "State = 'Purchase at the Exchange'",
     "proc": "UPExchangeItemBuy"},
)
# Зеркала той же передачи — не считаются (M3 is_mirror для Trade* / PersonalStore*; «Sold out» — строка продавца той же покупки)
MIRRORS = ({"table": "TradeGoldTo", "of": "TradeGoldFrom", "group": "trade"}, {"table": "TradeitemTo", "of": "TradeItemFrom", "group": "trade"},
           {"table": "TradeShellGoldTo", "of": "TradeShellGoldFrom", "group": "trade"},
           {"table": "PersonalStoreGoldTo", "of": "PersonalStoreGoldFrom", "group": "store"},
           {"table": "PersonalStoreitemTo", "of": "PersonalStoreitemFrom", "group": "store"},
           {"table": "ExchangeEvent", "of": "ExchangeEvent", "extra": "State = 'Sold out at the Exchange'", "group": "auction"})
# История аукциона: ExchangeEvent (все состояния) и регистрации ExchangeRegi* (UPExchangeEnroll; выставлено = Amount − Ramount у ExchangeRegi,
# Amount у Functional, 1 у Gear / Sowel / NoStack)
HISTORY = (
    # ★ ревизия 54 Н-2 (UPTimeoutDeleteItem): «Time Out-Delete» — персонажа нет, лот удалён без возврата, Amount = Ramount = количество;
    #   «Time Out-Return» — возврат лота по сроку (0, количество); у остальных — |Ramount − Amount|; 0 (вещь без стопки) → 1
    {"key": "event", "table": "ExchangeEvent", "qty": "(CASE WHEN State = 'Time Out-Delete' THEN CAST(Amount AS BIGINT) ELSE "
     "ABS(CAST(Ramount AS BIGINT) - CAST(Amount AS BIGINT)) END)", "state": "State",
     "other": ("Suserindex", "Scharidx", "Scharname"), "price": "CAST(Gm AS BIGINT)"},
    {"key": "regi", "table": "ExchangeRegi", "qty": "(CAST(Amount AS BIGINT) - CAST(Ramount AS BIGINT))"},
    {"key": "regi", "table": "ExchangeRegiFunctional", "qty": "CAST(Amount AS BIGINT)"},
    {"key": "regi", "table": "ExchangeRegiGear", "qty": _N1},
    {"key": "regi", "table": "ExchangeRegiSowel", "qty": _N1},
    {"key": "regi", "table": "ExchangeRegiNoStack", "qty": _N1},
)
EDGE = {s["key"]: s for s in EDGES}
_AC = None                           # модуль ac_metrics_db (правило M3, грузится лениво функцией m3)
_AC_LOCK = threading.Lock()


def m3():
    """Модуль AstoryServer/Tools/Anticheat/ac_metrics_db.py (правило M3 без изменений; кэш на процесс): исходник на ПК, иначе копия ext/anticheat/
    архива выкладки. Его импорт без побочных эффектов (db_connect подключается лениво)."""
    # ★ ревизия 56 С-1: было «AC_SRC, если там есть ac_metrics_db.py» — на сервере это H:\AstoryServer\Tools\Anticheat вне дерева службы (папку может
    #   создать любой локальный пользователь, служба — SYSTEM). Теперь domains/acsrc: на сервере только ext/anticheat со сверкой манифеста
    #   выкладки, код — из проверенных байтов в частном пространстве (общий sys.path и sys.modules не меняются)
    global _AC
    with _AC_LOCK:
        if _AC is None:
            from domains import acsrc
            d = acsrc.pick(AC_SRC, AC_EXT)
            mods, _h = acsrc.load(d, ("db_connect", "ac_common", "ac_metrics_db"), "trade_src_")
            mod = mods["ac_metrics_db"]
            mod.COMMON = mods["ac_common"]                       # разбор шапки строк журналов GameServer (HDR) — как ac_daily_report
            mod.LOADED_FROM = os.path.join(d, "ac_metrics_db.py")
            _AC = mod
    return _AC


# ---------------------------------------------------------------- проверка ввода

def _page(q, key="page"):
    """Номер страницы."""
    return econ._int(q.get(key) or 1, "страница передач — целое от 1 до %d" % PAGES_MAX, 1, PAGES_MAX)


def _size(q):
    """Строк на странице."""
    return econ._int(q.get("size") or PAGE_DEF, "строк на странице передач — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)


def _group(q):
    """Отбор вида передачи или None."""
    v = (q.get("group") or "").strip()
    if v and v not in GROUPS:
        raise OpRefused("вид передачи — один из: %s" % ", ".join(GROUPS))
    return v or None


def _pair(q):
    """Отбор пары «N-N» → (меньший, больший) или None."""
    v = (q.get("pair") or "").strip()
    if not v:
        return None
    m = _PAIR.match(v)
    if not m or int(m.group(1)) > 2 ** 31 - 1 or int(m.group(2)) > 2 ** 31 - 1:
        raise OpRefused("пара учёток — два номера через дефис (например 75204-75216)")
    a, b = int(m.group(1)), int(m.group(2))
    return (min(a, b), max(a, b))


def _account_text(q):
    """Учётка отбора (номер или логин) — длина до базы."""
    v = (q.get("account") or "").strip()
    if len(v) > 40:
        raise OpRefused("учётка передач — не длиннее 40 знаков")
    return v


def _dates(q):
    """Даты периода (ГГГГММДД) — вид и порядок до базы."""
    f, t = acjournal.parse_day(q.get("from"), "from"), acjournal.parse_day(q.get("to"), "to")
    if f and t and f > t:
        raise OpRefused("дата «с» позже даты «по»")
    if f and t:
        econ._period(q, t)
    return f, t


def check_input(q, what):
    """Проверка ввода функции what ДО базы (те же отказы, что у функций): самотест и консоль."""
    econ._svc(q)
    _dates(q)
    if what in ("graph", "transfers"):
        _group(q)
        _account_text(q)
    if what == "transfers":
        _pair(q)
        _page(q)
        _size(q)
    if what == "market":
        _page(q)
    if what == "stores":
        v = str(q.get("logs") if q.get("logs") not in (None, "") else "1")
        if v not in ("0", "1"):
            raise OpRefused("журнал лавок — 0 или 1")


# ---------------------------------------------------------------- общее

def pair_cat(a, b):
    """Категория пары (цепочки, сделки): служебная, если хоть одна сторона ≤ 5000."""
    return "service" if min(int(a), int(b)) <= econ.SERVICE_MAX else "player"


def _period(q):
    """(с, по) ГГГГММДД по часам SQL-сервера (по умолчанию — 30 суток, предел — 366, как в «Экономике»)."""
    with db.GameReader("joylog1") as g:
        return econ._period(q, econ._today(g))


def _edge_sql(s):
    """SELECT строк источника передач за период (таблица и столбцы — только из констант EDGES)."""
    if not _TBL.match(s["table"]):
        raise db.DbError("неверное имя таблицы %s" % s["table"][:40])
    cols = ["Edate AS t", "%s AS gu" % s["gu"], "%s AS gc" % s["gc"], "%s AS gn" % (s["gn"] or _NULLS["name"]), "%s AS ru" % s["ru"],
            "%s AS rc" % s["rc"], "%s AS rn" % (s["rn"] or _NULLS["name"]), "%s AS code" % (s.get("code") or _NULLS["code"]),
            "%s AS qty" % s["qty"], "%s AS serial" % (s.get("serial") or _NULLS["serial"])]
    cond = WINDOW + ((" AND " + s["extra"]) if s.get("extra") else "")
    return "SELECT TOP (%d) %s FROM dbo.%s WHERE %s ORDER BY Edate, %s" % (EDGE_MAX + 1, ", ".join(cols), s["table"], cond, s["gu"])


def _edge(s, r):
    """Строка журнала → передача (золото всей кучкой у TradeItemFrom — Code 20551 — тоже золото)."""
    code = int(r["code"]) if r["code"] is not None else None
    what = "gold" if s["what"] == "gold" or code == GOLD else "item"
    return {"t": r["t"], "group": s["group"], "src": s["key"], "what": what, "fu": _i(r["gu"]), "fi": _i(r["gc"]), "fn": r["gn"],
            "tu": _i(r["ru"]), "ti": _i(r["rc"]), "tn": r["rn"], "code": None if what == "gold" else code, "qty": int(r["qty"] or 0),
            "serial": (str(r["serial"]).strip().upper() or None) if r["serial"] is not None else None}


def _i(v):
    """Целое или None."""
    return int(v) if v is not None else None


def collect(f, t, errors, groups=None):
    """Все передачи за [f; t] (ГГГГММДД, сутки по часам SQL-сервера) → (передачи по времени, {источник: строк}, {источник: обрезан},
    сводка подарков gp7 или None). Нет таблицы — строка в errors, остальное считается. groups — отбор видов (None — все)."""
    edges, counts, capped, ginfo = [], {}, {}, None
    want = lambda g: groups is None or g in groups
    if any(want(s["group"]) for s in EDGES):
        try:
            with db.GameReader("joylog1") as g:
                for s in EDGES:
                    if not want(s["group"]):
                        continue
                    try:
                        rows = g.rows(_edge_sql(s), (f, t))
                    except db.DbError as ex:
                        errors.append("журнал передач %s не прочитан: %s" % (s["table"], ex))
                        counts[s["key"]] = None
                        continue
                    capped[s["key"]] = len(rows) > EDGE_MAX
                    rows = rows[:EDGE_MAX]
                    counts[s["key"]] = len(rows)
                    for r in rows:
                        if r["gu"] is None or r["ru"] is None:
                            continue
                        edges.append(_edge(s, r))
        except db.DbError as ex:
            errors.append("журналы JoyLog1 не прочитаны: %s" % ex)
    if want("gift"):
        gifts = gift_edges(f, t, errors)
        counts["GP7GiftLog"] = None if gifts is None else len(gifts["edges"])
        if gifts:
            edges.extend(gifts["edges"])
            ginfo = {"states": gifts["states"], "test": gifts["test"], "unresolved": gifts["unresolved"]}
    edges.sort(key=lambda e: (e["t"], e["fu"], e["tu"]))
    return edges, counts, capped, ginfo


def gift_edges(f, t, errors):
    """Подарки gp7 за период (created_at — UTC, сдвиг «местное − UTC» у SQL-сервера, как «Деньги»): выданные (C) — передачи отправитель →
    получатель; заморожены (H) и возвращены (R) — счётом. → {edges, states, test, unresolved} или None (журнал не прочитан)."""
    from domains import money                    # только чтение: сдвиг часов сервера (money._shift)
    try:
        with db.GameReader("asdastorylogin") as g:
            shift = money._shift(g)
            rows = g.rows("SELECT TOP (%d) order_id, sender_userindex, sender_charidx, sender_name, recipient_name, code1, code2, code3, code4, "
                          "code5, code6, code7, amount, state, test_mode, DATEADD(minute, ?, created_at) AS t FROM dbo.GP7GiftLog WHERE "
                          "DATEADD(minute, ?, created_at) >= CONVERT(datetime2, ?, 112) AND DATEADD(minute, ?, created_at) < "
                          "DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)) ORDER BY order_id" % (EDGE_MAX + 1), (shift, shift, f, shift, t))
    except db.DbError as ex:
        errors.append("подарки gp7 не прочитаны: %s" % ex)
        return None
    rows = rows[:EDGE_MAX]
    out = {"edges": [], "states": {}, "test": 0, "unresolved": 0}
    names = sorted({r["recipient_name"] for r in rows if r["state"] == "C" and r["recipient_name"]})[:GIFT_NAMES_MAX]
    who = {}
    if names:
        try:
            with db.GameReader("joy1") as j:
                for nm in names:
                    cs = j.rows("SELECT Userindex, Charidx, Charname, CASE WHEN CAST(Charname AS VARBINARY(20)) = CAST(CAST(? AS VARCHAR(20)) AS "
                                "VARBINARY(20)) THEN 1 ELSE 0 END AS exact FROM Charinfo WHERE Charname = ? COLLATE Arabic_CI_AS ORDER BY "
                                "Userindex, Charidx", (nm, nm))
                    exact = [c for c in cs if c["exact"]]
                    pick = cs[0] if len(cs) == 1 else (exact[0] if len(cs) > 1 and len(exact) == 1 else None)
                    if pick:
                        who[nm] = (int(pick["Userindex"]), int(pick["Charidx"]), pick["Charname"])
        except db.DbError as ex:
            errors.append("получатели подарков gp7 не найдены: %s" % ex)
    for r in rows:
        st = (r["state"] or "?").strip()
        out["states"][st] = out["states"].get(st, 0) + 1
        out["test"] += 1 if r["test_mode"] else 0
        if st != "C":
            continue
        rc = who.get(r["recipient_name"])
        if rc is None or r["sender_userindex"] is None:
            out["unresolved"] += 1
            continue
        codes = [int(r["code%d" % k]) for k in range(1, 8) if r.get("code%d" % k)]
        out["edges"].append({"t": r["t"], "group": "gift", "src": "GP7GiftLog", "what": "item", "fu": int(r["sender_userindex"]),
                             "fi": _i(r["sender_charidx"]), "fn": db.fix_text(r["sender_name"]), "tu": rc[0], "ti": rc[1], "tn": rc[2],
                             "code": codes[0] if codes else None, "qty": len(codes), "serial": None, "order": int(r["order_id"]),
                             "cash": int(r["amount"] or 0), "test": bool(r["test_mode"])})
    return out


def mirror_counts(f, t, errors, group=None):
    """Строк зеркал за период (не считаются): [{table, of, rows}]; group — только зеркала этого вида (★ ревизия 54: мелочь)."""
    out = []
    try:
        with db.GameReader("joylog1") as g:
            for m in MIRRORS:
                if group and m["group"] != group:
                    continue
                cond = WINDOW + ((" AND " + m["extra"]) if m.get("extra") else "")
                try:
                    n = int(g.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE %s" % (m["table"], cond), (f, t))["n"])
                except db.DbError as ex:
                    errors.append("зеркальная таблица %s не прочитана: %s" % (m["table"], ex))
                    n = None
                out.append({"table": m["table"], "of": m["of"], "rows": n, "sold": bool(m.get("extra"))})
    except db.DbError as ex:
        errors.append("журналы JoyLog1 не прочитаны: %s" % ex)
    return out


def postbox_now(errors):
    """Ящик ItemPostBox и отложенные Joy1.gifts сейчас (отправителя нет): строк по iType, из них подарков gp7 (Orderidx = order_id)."""
    out = {"postbox": None, "gifts_rows": None, "gift_orders": None}
    try:
        with db.GameReader("joy1") as j:
            out["postbox"] = [{"itype": int(r["iType"]), "rows": int(r["n"]), "orders": int(r["o"])} for r in
                              j.rows("SELECT iType, COUNT(*) AS n, COUNT(DISTINCT Orderidx) AS o FROM dbo.ItemPostBox GROUP BY iType ORDER BY iType")]
            out["gifts_rows"] = int(j.one("SELECT COUNT(*) AS n FROM dbo.gifts")["n"])
            orders = sorted({int(r["Orderidx"]) for r in j.rows("SELECT DISTINCT Orderidx FROM dbo.ItemPostBox WHERE Orderidx > 0")})
    except db.DbError as ex:
        errors.append("ящик ItemPostBox и отложенные подарки не прочитаны: %s" % ex)
        return out
    n = 0
    try:
        with db.GameReader("asdastorylogin") as g:
            for i in range(0, len(orders), 500):
                part = orders[i:i + 500]
                n += int(g.one("SELECT COUNT(*) AS n FROM dbo.GP7GiftLog WHERE order_id IN (%s)" % ",".join("?" * len(part)), part)["n"])
        out["gift_orders"] = n
    except db.DbError as ex:
        errors.append("подарки gp7 не прочитаны: %s" % ex)
    return out


# ---------------------------------------------------------------- граф: пары, цепочки, серийники, сеть

_FL_DEALS = re.compile(r"^пара (\d+)<->(\d+): (\d+) записей")
_FL_ONE = re.compile(r"^пара (\d+)->(\d+): золото (\d+) в одну сторону")


def m3_rows(edges):
    """Передачи → строки правила M3 (a, b, «gold» | «item», записей, количество), a → b (порядок как у ac_metrics_db.window_pairs)."""
    agg = {}
    for e in edges:
        k = (e["fu"], e["tu"], "gold" if e["what"] == "gold" else "item")
        x = agg.setdefault(k, [0, 0])
        x[0] += 1
        x[1] += e["qty"]
    return [(a, b, kind, n, amt) for (a, b, kind), (n, amt) in sorted(agg.items())]


def m3_flags(pairs):
    """Флаги правила M3 (ac_metrics_db.pair_flags — без изменений) → {пара: [{type: deals | oneway, from, to, value} | {type: other, raw}]}."""
    out = {}
    for k, text in m3().pair_flags(pairs):
        m1, m2 = _FL_DEALS.match(text), _FL_ONE.match(text)
        if m1:
            x = {"type": "deals", "from": k[0], "to": k[1], "value": int(m1.group(3))}
        elif m2:
            x = {"type": "oneway", "from": int(m2.group(1)), "to": int(m2.group(2)), "value": int(m2.group(3))}
        else:
            x = {"type": "other", "raw": text}
        out.setdefault(k, []).append(x)
    return out


def chains(edges, svc_max=None, deadline_s=None):
    """Цепочки передач по времени: A → B, затем B → C не раньше, … (≤ CHAIN_HOPS шагов, между учётками, без повторов). ★ ревизия 54 В-1:
    ОДИН проход за O(E·K) вместо перебора всех путей. Передачи идут от поздних к ранним; у каждой учётки хранятся CHAIN_K лучших продолжений
    «с этой учётки не раньше этого времени» (длина, золото; разные получатели) — все уже разобранные передачи не раньше текущей, поэтому
    продолжения передачи e — снимок списка её получателя. Цепочка от каждой передачи: первый шаг — по каждому продолжению снимка (до
    CHAIN_K веток), дальше — первое продолжение без повтора учётки. Две «полосы» за тот же проход: all — все передачи, player — только между
    учётками > svc_max (служебная цепочка не поглощает цепочку игроков). Оставляются наибольшие: цепочка, целиком входящая в другую,
    отбрасывается по множеству подцепочек (O(K·L²), L ≤ CHAIN_HOPS + 1). Пределы: CHAIN_WORK цепочек-кандидатов и deadline_s секунд
    (CHAIN_TIME_S) — дальше пометка «обрезано». Цепочки — подсказка для разбора (лучшие продолжения), а не все пути.
    → ({"all": [...], "player": [...]}, обрезано ли)."""
    import time
    t_end = time.monotonic() + (CHAIN_TIME_S if deadline_s is None else deadline_s)
    svc_max = econ.SERVICE_MAX if svc_max is None else svc_max
    hops = sorted((e for e in edges if e["fu"] != e["tu"]), key=lambda e: e["t"], reverse=True)
    lanes = ("all", "player")
    best = {ln: {} for ln in lanes}               # полоса → учётка → [(длина, золото, номер передачи)] — CHAIN_K лучших, разные получатели
    snap = {ln: {} for ln in lanes}               # полоса → номер передачи → снимок продолжений её получателя (номера передач)
    score = {ln: {} for ln in lanes}
    capped = False
    for i, e in enumerate(hops):
        if i % 2000 == 0 and time.monotonic() > t_end:
            capped = True
            break
        g = e["qty"] if e["what"] == "gold" else 0
        for ln in lanes:
            if ln == "player" and min(e["fu"], e["tu"]) <= svc_max:
                continue
            cont = [c for c in best[ln].get(e["tu"], ()) if hops[c[2]]["tu"] != e["fu"]]
            c = cont[0] if cont else None
            sc = (min(1 + (c[0] if c else 0), CHAIN_HOPS), g + (c[1] if c else 0))
            score[ln][i] = sc
            if cont:
                snap[ln][i] = [x[2] for x in cont]
            lst = [x for x in best[ln].get(e["fu"], []) if hops[x[2]]["tu"] != e["tu"]]
            lst.append((sc[0], sc[1], i))
            lst.sort(key=lambda x: (-x[0], -x[1]))
            best[ln][e["fu"]] = lst[:CHAIN_K]
    out = {}
    for ln in lanes:
        found = {}

        def add(path, nodes):
            key = tuple(nodes)
            gold = sum(x["qty"] for x in path if x["what"] == "gold")
            if key not in found or gold > found[key]["gold"]:
                found[key] = {"nodes": list(nodes), "hops": list(path), "gold": gold, "items": sum(x["qty"] for x in path if x["what"] != "gold")}
        for i, sc in score[ln].items():
            if sc[0] < 2:
                continue
            if len(found) >= CHAIN_WORK or time.monotonic() > t_end:
                capped = True
                break
            for j0 in snap[ln].get(i, ()):
                path, nodes = [hops[i]], [hops[i]["fu"], hops[i]["tu"]]
                j = j0
                while j is not None and len(path) < CHAIN_HOPS:
                    if hops[j]["tu"] in nodes:
                        break
                    path.append(hops[j])
                    nodes.append(hops[j]["tu"])
                    j = next((k for k in snap[ln].get(j, ()) if hops[k]["tu"] not in nodes), None)
                if len(path) >= 2:
                    add(path, nodes)
        inner = set()
        for k in found:                           # все собственные подцепочки (≥ 3 учёток) каждой цепочки
            for ln2 in range(3, len(k)):
                for a in range(0, len(k) - ln2 + 1):
                    inner.add(k[a:a + ln2])
        res = [v for k, v in found.items() if k not in inner]
        res.sort(key=lambda c: (-len(c["nodes"]), -c["gold"], c["hops"][0]["t"]))
        out[ln] = res
    return out, capped


def serial_chains(edges):
    """Серийник вещи, переданный ≥ m4_chain раз за период (порог M4 ac_common.THR; учитываются все виды передач, зеркала — нет) →
    [{serial, code, n, path}]."""
    thr = int(m3().THR["m4_chain"])
    by = {}
    for e in edges:
        if e["what"] == "item" and e.get("serial") and e["src"] != "GP7GiftLog":
            by.setdefault(e["serial"], []).append(e)
    out = []
    for s, es in by.items():
        if len(es) >= thr:
            es = sorted(es, key=lambda e: e["t"])
            out.append({"serial": s, "code": es[0]["code"], "n": len(es), "path": es})
    out.sort(key=lambda x: (-x["n"], x["serial"]))
    return out, thr


def net_groups(f, t, errors):
    """Один IP / один MAC — разные учётки за период (LogInfo.Login; адреса — только пригодные для связи: players._linkable_ip /
    _linkable_mac). → {ip: [...], mac: [...], crowd: LINK_CROWD} или None (не прочитано)."""
    try:
        with db.GameReader("joylog1") as lg:
            rows = lg.rows("SELECT TOP (%d) Userindex, IpAddress, Mac, Login, Logout FROM dbo.LogInfo WHERE Login >= CONVERT(datetime2, ?, 112) "
                           "AND Login < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)) ORDER BY idx" % (NET_ROWS + 1), (f, t))
    except db.DbError as ex:
        errors.append("входы LogInfo не прочитаны: %s" % ex)
        return None
    capped = len(rows) > NET_ROWS
    rows = rows[:NET_ROWS]
    res = {"ip": [], "mac": [], "crowd": players.LINK_CROWD, "capped": capped}
    for kind, col, ok in (("ip", "IpAddress", players._linkable_ip), ("mac", "Mac", players._linkable_mac)):
        by = {}
        for r in rows:
            v = (r[col] or "").strip()
            if r["Userindex"] is None or not ok(v):
                continue
            v = v.upper() if kind == "mac" else v
            a = by.setdefault(v, {}).setdefault(int(r["Userindex"]), {"uid": int(r["Userindex"]), "sessions": 0, "first": None, "last": None})
            a["sessions"] += 1
            if r["Login"] and (a["first"] is None or r["Login"] < a["first"]):
                a["first"] = r["Login"]
            if r["Login"] and (a["last"] is None or r["Login"] > a["last"]):
                a["last"] = r["Login"]
        groups = [{"value": v, "accounts": sorted(acc.values(), key=lambda x: x["uid"]), "n": len(acc), "crowd": len(acc) > players.LINK_CROWD}
                  for v, acc in by.items() if len(acc) >= 2]
        groups.sort(key=lambda x: (-x["n"], x["value"]))
        res[kind] = groups[:NET_GROUPS_MAX]
    return res


def pair_links(keys, errors):
    """Связь учёток пары по всем входам LogInfo (players.link_degree — как в карточке учётки; открытая сейчас сессия — players.mark_open).
    → {(a, b): ключ связи | None}."""
    uids = sorted({u for k in keys for u in k})
    if not uids:
        return {}
    try:
        with db.GameReader("joylog1") as lg:
            rows = lg.rows("SELECT TOP (%d) Userindex, IpAddress, Mac, Login, Logout FROM dbo.LogInfo WHERE Userindex IN (%s) ORDER BY idx DESC"
                           % (NET_ROWS, ",".join("?" * len(uids))), uids)
            ips = sorted({(r["IpAddress"] or "").strip() for r in rows if players._linkable_ip(r["IpAddress"])})[:2000]
            crowd = {}
            for i in range(0, len(ips), 500):
                part = ips[i:i + 500]
                for r in lg.rows("SELECT IpAddress, COUNT(DISTINCT Userindex) AS n FROM dbo.LogInfo WHERE IpAddress IN (%s) GROUP BY IpAddress"
                                 % ",".join("?" * len(part)), part):
                    crowd[(r["IpAddress"] or "").strip()] = int(r["n"])
        on = players._online_ids(uids)
    except db.DbError as ex:
        errors.append("входы LogInfo не прочитаны: %s" % ex)
        return {}
    per = {}
    for r in rows:
        per.setdefault(int(r["Userindex"]), []).append(r)
    for u, rs in per.items():
        players.mark_open(rs, u in on)
    out = {}
    for a, b in keys:
        if a == b:
            out[(a, b)] = None
            continue
        key = players.link_degree(per.get(a, []), per.get(b, []), crowd)[0]
        out[(a, b)] = key
    return out


def _who(q):
    """Учётки отбора (номер или логин, acjournal.resolve_account) или None."""
    v = _account_text(q)
    return set(acjournal.resolve_account(v)) if v else None


def _pub_edge(e):
    """Передача для ответа."""
    x = {k: e.get(k) for k in ("t", "group", "src", "what", "fu", "fi", "fn", "tu", "ti", "tn", "code", "qty", "serial", "order", "cash", "test")}
    x["cat"] = pair_cat(e["fu"], e["tu"])
    if e.get("code") is not None:
        it = refdata.item(e["code"])
        x["name"], x["icon"] = it["name"], it["icon"]
    return x


def graph(q, can_net=False):
    """Граф «кто кому» за период: пары учёток (правило M3: записей, золото и вещи в обе стороны, флаги), цепочки, серийники с цепочкой,
    один IP / MAC — разные учётки и связь пары (только can_net — право players.view_net), зеркала (не считаются), ящик сейчас. → dict."""
    check_input(q, "graph")
    svc = econ._svc(q)
    grp = _group(q)
    out = {"svc": svc, "period": None, "group": grp, "sources": [], "pairs": [], "service_pairs": [], "chains": [], "service_chains": [],
           "serials": [], "net": None, "net_hidden": not can_net, "mirrors": [], "box": None, "gifts": None, "errors": [], "thr": None,
           "totals": None, "capped": False, "chains_capped": False}
    f, t = _period(q)
    out["period"] = {"from": f, "to": t}
    who = _who(q)
    edges, counts, capped, out["gifts"] = collect(f, t, out["errors"], groups={grp} if grp else None)
    out["capped"] = any(capped.values())
    out["sources"] = [{"key": s["key"], "table": s["table"], "group": s["group"], "what": s["what"], "proc": s["proc"],
                       "rows": counts.get(s["key"]), "capped": capped.get(s["key"], False)} for s in EDGES if s["key"] in counts]
    if "GP7GiftLog" in counts:
        out["sources"].append({"key": "GP7GiftLog", "table": "GP7GiftLog", "group": "gift", "what": "item", "proc": "GP7_GiftSettle",
                               "rows": counts["GP7GiftLog"], "capped": False})
    if who:
        edges = [e for e in edges if e["fu"] in who or e["tu"] in who]
    M = m3()
    out["thr"] = {k: M.THR[k] for k in ("m3_pair_deals", "m3_gold_oneway", "m4_chain")}
    out["m3_from"] = os.path.basename(os.path.dirname(M.LOADED_FROM))
    pairs = M.analyse_pairs(m3_rows(edges))
    flags = m3_flags(pairs)
    info = {}
    for e in edges:
        k = (min(e["fu"], e["tu"]), max(e["fu"], e["tu"]))
        x = info.setdefault(k, {"groups": {}, "first": e["t"], "last": e["t"]})
        x["groups"][e["group"]] = x["groups"].get(e["group"], 0) + 1
        x["first"], x["last"] = min(x["first"], e["t"]), max(x["last"], e["t"])
    rows = []
    for k, p in pairs.items():
        rows.append(dict(p, a=k[0], b=k[1], cat=pair_cat(*k), flags=flags.get(k, []), groups=info[k]["groups"], first=info[k]["first"],
                         last=info[k]["last"], self=k[0] == k[1]))
    rows.sort(key=lambda r: (not r["flags"], -r["deals"], r["a"], r["b"]))
    tot = {c: {"pairs": 0, "deals": 0, "flagged": 0} for c in CATS}
    for r in rows:
        x = tot[r["cat"]]
        x["pairs"] += 1
        x["deals"] += r["deals"]
        x["flagged"] += 1 if r["flags"] else 0
    out["totals"] = {"cats": tot, "total": {k: sum(tot[c][k] for c in CATS if econ._in_total(c, svc)) for k in ("pairs", "deals", "flagged")},
                     "edges": len(edges)}
    if svc == "in":
        out["pairs"] = rows[:PAIRS_MAX]
    else:
        out["pairs"] = [r for r in rows if r["cat"] == "player"][:PAIRS_MAX]
        out["service_pairs"] = [r for r in rows if r["cat"] == "service"][:PAIRS_MAX]
    out["pairs_total"] = {c: sum(1 for r in rows if r["cat"] == c) for c in CATS}
    shown = out["pairs"] + out["service_pairs"]
    if can_net:
        links = pair_links([(r["a"], r["b"]) for r in shown], out["errors"])
        for r in shown:
            key = links.get((r["a"], r["b"]))
            r["link"] = key
            r["link_title"] = players.LINK_TITLES.get(key) if key else None
        out["net"] = net_groups(f, t, out["errors"])
    # цепочки — один проход (★ ревизия 54 В-1): полоса all — все передачи, полоса player — только между игроками (служебная цепочка не
    #   поглощает цепочку игроков); при svc=sep цепочки со служебной учёткой — отдельным списком из полосы all
    svc_of = lambda c: "service" if any(u <= econ.SERVICE_MAX for u in c["nodes"]) else "player"
    pub = lambda c: dict(c, hops=[_pub_edge(e) for e in c["hops"]], cat=svc_of(c))
    ch, out["chains_capped"] = chains(edges)
    if svc == "in":
        out["chains"] = [pub(c) for c in ch["all"][:CHAINS_MAX]]
    else:
        out["chains"] = [pub(c) for c in ch["player"][:CHAINS_MAX]]
        out["service_chains"] = [pub(c) for c in ch["all"] if svc_of(c) == "service"][:CHAINS_MAX]
    sr, out["thr"]["m4_chain"] = serial_chains(edges)
    out["serials"] = [dict(x, path=[_pub_edge(e) for e in x["path"]], name=refdata.item(x["code"])["name"] if x["code"] else "")
                      for x in sr[:SERIALS_MAX]]
    out["mirrors"] = mirror_counts(f, t, out["errors"], grp) if grp != "gift" else []
    out["box"] = postbox_now(out["errors"])
    uids = {u for r in shown for u in (r["a"], r["b"])} | {u for c in out["chains"] + out["service_chains"] for u in c["nodes"]}
    if out["net"]:
        uids |= {a["uid"] for kind in ("ip", "mac") for g in out["net"][kind] for a in g["accounts"]}
    out["logins"] = {str(k): v for k, v in acjournal._logins(uids, out["errors"]).items()}
    return out


def transfers(q):
    """Передачи построчно (новые сверху) с отбором: учётка (номер или логин), пара «N-N», вид; страницы. → dict."""
    check_input(q, "transfers")
    svc = econ._svc(q)
    grp, pr, page, size = _group(q), _pair(q), _page(q), _size(q)
    out = {"svc": svc, "period": None, "rows": [], "total": 0, "page": page, "pages": 1, "size": size, "errors": [], "capped": False}
    f, t = _period(q)
    out["period"] = {"from": f, "to": t}
    who = _who(q)
    edges, _c, capped, _g = collect(f, t, out["errors"], groups={grp} if grp else None)
    out["capped"] = any(capped.values())
    if who:
        edges = [e for e in edges if e["fu"] in who or e["tu"] in who]
    if pr:
        edges = [e for e in edges if (min(e["fu"], e["tu"]), max(e["fu"], e["tu"])) == pr]
    edges.sort(key=lambda e: (e["t"], e["fu"], e["tu"]), reverse=True)
    # ★ ревизия 54 Н-5: при svc=sep передачи со служебной стороной — отдельным списком (первые PAGE_DEF новых и их число), не в общем
    out["service_rows"], out["service_total"] = [], 0
    if svc != "in":
        sv = [e for e in edges if pair_cat(e["fu"], e["tu"]) == "service"]
        edges = [e for e in edges if pair_cat(e["fu"], e["tu"]) == "player"]
        out["service_total"] = len(sv)
        out["service_rows"] = [_pub_edge(e) for e in sv[:PAGE_DEF]]
    out["total"] = len(edges)
    out["pages"] = max(1, (len(edges) + size - 1) // size)
    page = min(page, out["pages"])
    out["page"] = page
    out["rows"] = [_pub_edge(e) for e in edges[(page - 1) * size:page * size]]
    out["logins"] = {str(k): v for k, v in acjournal._logins({u for r in out["rows"] + out["service_rows"] for u in (r["fu"], r["tu"])},
                                                              out["errors"]).items()}
    return out


# ---------------------------------------------------------------- рынок (аукцион)

def _one_if_zero(expr):
    """Количество 0 (вещь без стопки: Item.Amount = 0) → 1."""
    return "(CASE WHEN %s = 0 THEN CAST(1 AS BIGINT) ELSE %s END)" % (expr, expr)


def _hist_cond(h, cat):
    """★ ревизия 54 Н-5: условие категории строки истории: player — обе стороны > 5000, service — хоть одна ≤ 5000, None — все."""
    if cat is None:
        return ""
    other = (h.get("other") or (None,))[0]
    if cat == "player":
        return " AND Userindex > %d%s" % (econ.SERVICE_MAX, (" AND (%s > %d OR %s IS NULL)" % (other, econ.SERVICE_MAX, other)) if other else "")
    return " AND (Userindex <= %d%s)" % (econ.SERVICE_MAX, (" OR %s <= %d" % (other, econ.SERVICE_MAX)) if other else "")


def _history(g, f, t, depth, cat, errors):
    """История аукциона за период по категории: (всего, строки TOP depth каждой таблицы, счёт по состояниям)."""
    total, rows, counts = 0, [], {}
    for h in HISTORY:
        st = h.get("state") or "CAST(NULL AS VARCHAR(100))"
        ou, oc, on = h.get("other") or ("CAST(NULL AS INT)", "CAST(NULL AS INT)", _NULLS["name"])
        cond = WINDOW + _hist_cond(h, cat)
        try:
            n = int(g.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE %s" % (h["table"], cond), (f, t))["n"])
            rs = g.rows("SELECT TOP (%d) Edate AS t, Userindex, Charidx, %s AS ou, %s AS oc, %s AS onm, Code, %s AS qty, %s AS price, "
                        "%s AS st, Serial FROM dbo.%s WHERE %s ORDER BY Edate DESC" % (
                            depth, ou, oc, on, _one_if_zero(h["qty"]), h.get("price") or "CAST(NULL AS BIGINT)", st, h["table"], cond), (f, t))
            if h["key"] == "event":
                for r in g.rows("SELECT State, COUNT(*) AS n FROM dbo.ExchangeEvent WHERE %s GROUP BY State" % cond, (f, t)):
                    counts[r["State"] or ""] = int(r["n"])
        except db.DbError as ex:
            errors.append("история аукциона %s не прочитана: %s" % (h["table"], ex))
            continue
        total += n
        if h["key"] == "regi":
            counts["regi"] = counts.get("regi", 0) + n
        rows.extend(dict(r, kind=h["key"], table=h["table"]) for r in rs)
    rows.sort(key=lambda r: (r["t"], r["table"]), reverse=True)
    return total, rows, counts


def _hist_pub(rows, errors):
    """Строки истории для ответа (имена персонажей — Charinfo)."""
    names = _char_names({(int(r["Userindex"]), int(r["Charidx"])) for r in rows if r["Userindex"] is not None}, errors)
    out = []
    for r in rows:
        it = refdata.item(r["Code"]) if r["Code"] is not None else {"name": "", "icon": None}
        nm = names.get((int(r["Userindex"]), int(r["Charidx"]))) if r["Userindex"] is not None else None
        out.append({"t": r["t"], "kind": r["kind"], "table": r["table"], "state": r["st"], "uid": _i(r["Userindex"]), "slot": _i(r["Charidx"]),
                    "char": nm[0] if nm else None, "login": nm[1] if nm else None, "ou": _i(r["ou"]), "oslot": _i(r["oc"]), "oname": r["onm"],
                    "code": _i(r["Code"]), "name": it["name"], "icon": it["icon"], "qty": _i(r["qty"]), "price": _i(r["price"]),
                    "serial": r["Serial"], "mirror": r["st"] == SOLD, "deleted": r["st"] == TO_DELETE,
                    "cat": pair_cat(r["Userindex"], r["ou"] if r["ou"] is not None else r["Userindex"]) if r["Userindex"] is not None else None})
    return out


def market(q):
    """Рынок: живые лоты Exitem с ценами (за штуку — Sprice / Amount, у вещи без стопки — Sprice; срок реле — feed.lot_marks), цены
    выставленных и проданных за период по коду, история аукциона (ExchangeEvent всех состояний + регистрации ExchangeRegi*, страницы),
    налог: сбор за выставление MoneyExchangeFee, сбор с продажи и его возврат (ItemEvent Code 20551). ★ ревизия 54 Н-5: служебные ≤ 5000
    при svc=sep — отдельными списками лотов и истории (не в ценах и итогах). → dict."""
    check_input(q, "market")
    svc = econ._svc(q)
    page = _page(q)
    size = PAGE_DEF
    out = {"svc": svc, "period": None, "lots": [], "service_lots": [], "lots_total": 0, "lots_capped": False, "prices": [], "history": [],
           "service_history": [], "hist_total": 0, "service_hist_total": 0, "page": page, "pages": 1, "hist_counts": {}, "tax": None,
           "sold_capped": False, "errors": []}
    f, t = _period(q)
    out["period"] = {"from": f, "to": t}
    stamp = None
    try:
        with db.GameReader("joy1") as j:
            stamp = j.one("SELECT SYSDATETIME() AS t")["t"]
            out["lots_total"] = int(j.one("SELECT COUNT(*) AS n FROM dbo.Exitem")["n"])
            lots = j.rows("SELECT TOP (%d) CONVERT(varchar(36), Eid) AS Eid, idx, Gidx, State, Userindex, Charidx, Charname, Code, Plate, Amount, "
                          "Upcount, Sprice, Stime, Gaindate, Fdate FROM dbo.Exitem ORDER BY Fdate, idx" % LOTS_MAX)
    except db.DbError as ex:
        out["errors"].append("лоты аукциона не прочитаны: %s" % ex)
        lots = []
    out["lots_capped"] = out["lots_total"] > len(lots)
    prices = {}
    new_p = lambda c: {"code": c, "listed": 0, "listed_qty": 0, "lmin": None, "lmax": None, "lsum": 0.0, "sold": 0, "sold_qty": 0, "smin": None,
                       "smax": None, "ssum": 0}
    for r in lots:
        feed.lot_marks(r, stamp)
        cat = econ.cat_of(r["Userindex"])
        it = refdata.item(r["Code"])
        amt = int(r["Amount"] or 0)
        pcs = amt if amt > 0 else 1                 # ★ ревизия 54 Н-1: вещь без стопки (Amount 0) — одна штука
        unit = int(r["Sprice"] or 0) / pcs
        lot = {"eid": r["Eid"], "idx": r["idx"], "gidx": r["Gidx"], "state": r["State"], "uid": int(r["Userindex"]), "slot": r["Charidx"],
               "char": r["Charname"], "code": int(r["Code"]), "name": it["name"], "icon": it["icon"], "amount": amt, "pieces": pcs,
               "nostack": amt <= 0, "upcount": r["Upcount"], "price": int(r["Sprice"] or 0), "unit": unit, "stime": r["Stime"],
               "gaindate": r["Gaindate"], "fdate": r["Fdate"], "expired": r["expired"], "relay_due": r["relay_due"], "overdue": r["relay_overdue"],
               "cat": cat}
        (out["lots"] if econ._in_total(cat, svc) else out["service_lots"]).append(lot)
        if econ._in_total(cat, svc):
            p = prices.setdefault(int(r["Code"]), new_p(int(r["Code"])))
            p["listed"] += 1
            p["listed_qty"] += pcs
            p["lsum"] += int(r["Sprice"] or 0)
            p["lmin"] = unit if p["lmin"] is None else min(p["lmin"], unit)
            p["lmax"] = unit if p["lmax"] is None else max(p["lmax"], unit)
    try:
        with db.GameReader("joylog1") as g:
            sold = g.rows("SELECT TOP (%d) Userindex, Suserindex, Code, %s AS qty, CAST(Gm AS BIGINT) AS price FROM dbo.ExchangeEvent WHERE %s AND "
                          "State = 'Purchase at the Exchange' ORDER BY Edate DESC" % (
                              EDGE_MAX + 1, _one_if_zero("(CAST(Ramount AS BIGINT) - CAST(Amount AS BIGINT))"), WINDOW), (f, t))
            out["sold_capped"] = len(sold) > EDGE_MAX
            for r in sold[:EDGE_MAX]:
                if not econ._in_total(pair_cat(r["Userindex"], r["Suserindex"] if r["Suserindex"] is not None else r["Userindex"]), svc):
                    continue
                qty = int(r["qty"] or 0)
                p = prices.setdefault(int(r["Code"]), new_p(int(r["Code"])))
                p["sold"] += 1
                p["sold_qty"] += qty
                p["ssum"] += int(r["price"] or 0)
                if qty > 0:
                    u = int(r["price"] or 0) / qty
                    p["smin"] = u if p["smin"] is None else min(p["smin"], u)
                    p["smax"] = u if p["smax"] is None else max(p["smax"], u)
            depth = min(page * size, HIST_DEPTH)
            out["hist_total"], hist, out["hist_counts"] = _history(g, f, t, depth, None if svc == "in" else "player", out["errors"])
            if svc != "in":
                out["service_hist_total"], shist, _sc = _history(g, f, t, PAGE_DEF, "service", out["errors"])
                out["service_history"] = _hist_pub(shist[:PAGE_DEF], out["errors"])
            out["tax"] = _tax(g, f, t, svc, out["errors"])
    except db.DbError as ex:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex)
        hist = []
    for p in prices.values():
        p["lavg"] = (p["lsum"] / p["listed_qty"]) if p["listed_qty"] else None
        p["savg"] = (p["ssum"] / p["sold_qty"]) if p["sold_qty"] else None
        it = refdata.item(p["code"])
        p["name"], p["icon"] = it["name"], it["icon"]
    out["prices"] = sorted(prices.values(), key=lambda p: (-(p["listed"] + p["sold"]), p["code"]))[:200]
    lim = min(out["hist_total"], HIST_DEPTH)
    out["pages"] = max(1, (lim + size - 1) // size)
    page = min(page, out["pages"])
    out["page"] = page
    out["pages_capped"] = out["hist_total"] > HIST_DEPTH
    out["history"] = _hist_pub(hist[(page - 1) * size:page * size], out["errors"])
    return out


def _tax(g, f, t, svc, errors):
    """Налог аукциона за период по категориям учёток: сбор за выставление (MoneyExchangeFee, UPItemExchangeLock: Amount − Ramount), сбор с
    продажи (ItemEvent «Commission at the Exchange») и его возврат (ItemEvent «Commision Refund on a registration», Code 20551)."""
    cats = {c: {"fee_n": 0, "fee": 0, "commission_n": 0, "commission": 0, "refund_n": 0, "refund": 0} for c in CATS}
    try:
        s = econ.SRC["MoneyExchangeFee"]
        for r in g.rows("SELECT %s AS cat, COUNT(*) AS n, SUM(-%s) AS s FROM dbo.%s WHERE %s GROUP BY %s"
                        % (econ._cat_sql("Userindex"), econ._delta(s), s["table"], WINDOW, econ._cat_sql("Userindex")), (f, t)):
            cats[r["cat"]]["fee_n"] += int(r["n"])
            cats[r["cat"]]["fee"] += int(r["s"] or 0)
        e = econ.SRC["ItemEvent"]
        for key, state, sign in FEE_STATES:
            for r in g.rows("SELECT %s AS cat, COUNT(*) AS n, SUM(%s) AS s FROM dbo.%s WHERE %s AND Code = %d AND State = ? GROUP BY %s"
                            % (econ._cat_sql("Userindex"), econ._delta(e), e["table"], WINDOW, GOLD, econ._cat_sql("Userindex")), (f, t, state)):
                cats[r["cat"]][key + "_n"] += int(r["n"])
                cats[r["cat"]][key] += sign * int(r["s"] or 0)
    except db.DbError as ex:
        errors.append("налог аукциона не прочитан: %s" % ex)
        return None
    for c in CATS:
        x = cats[c]
        x["net"] = x["fee"] + x["commission"] - x["refund"]
    total = {k: sum(cats[c][k] for c in CATS if econ._in_total(c, svc)) for k in cats["player"]}
    return {"cats": cats, "total": total}


def _char_names(keys, errors):
    """(учётка, персонаж) → (имя, логин) по Joy1.Charinfo."""
    uids = sorted({k[0] for k in keys})
    if not uids:
        return {}
    try:
        with db.GameReader("joy1") as j:
            return {(int(r["Userindex"]), int(r["Charidx"])): (r["Charname"], r["Uid"]) for r in
                    j.rows("SELECT Userindex, Charidx, Charname, Uid FROM dbo.Charinfo WHERE Userindex IN (%s)" % ",".join("?" * len(uids)), uids)}
    except db.DbError as ex:
        errors.append("имена персонажей не прочитаны: %s" % ex)
        return {}


# ---------------------------------------------------------------- лавки

_LOG_TAGS = ("OPEN", "RETURN", "BUY", "INSERT")       # открыта / закрыта (вещи вернулись) / покупка отправлена в базу / база подтвердила
_LOG_NAME = re.compile(r"^SelfStore_(\d{8})\.txt$", re.I)
_LOG_LINE = re.compile(r"^\[(\w+)\]\t(.*)$")


def parse_selfstore(lines, year):
    """Строки Log_SelfStore (GameServer CharSelfStore*: «MM Mon DD Day HH hou MM min SS sec : [ТЕГ]\\tКлюч:Значение…», год — из имени файла)
    → события [{t, tag, host_uid, host_name, host_num, buyer_uid, buyer_name, gold, db, items, msg}]. Строка хозяина (HostIndex) открывает
    событие, строки вещей (ItemIndex) того же тега — его вещи; «[E] …» — событие error. Разбор шапки — ac_common.HDR (как ac_daily_report)."""
    hdr = m3().COMMON.HDR
    out, cur = [], None
    for ln in lines:
        m = hdr.match(ln.rstrip("\r\n"))
        if not m:
            continue
        mon, day, hh, mi, ss, rest = m.groups()
        try:
            t = datetime.datetime(int(year), int(mon), int(day), int(hh), int(mi), int(ss))
        except ValueError:
            continue
        rest = rest.strip()
        if rest.startswith("[E]"):
            out.append({"t": t, "tag": "error", "msg": rest[3:].strip()[:300], "items": []})   # данные журнала (не «text» — его переводит служба)
            cur = None
            continue
        lm = _LOG_LINE.match(rest)
        if not lm:
            continue
        tag, body = lm.group(1).upper(), lm.group(2)
        kv, notes = {}, []
        for part in body.split("\t"):
            k, sep, v = part.partition(":")
            if sep and re.match(r"^[A-Za-z]+$", k.strip()):
                kv[k.strip()] = v.strip()
            elif part.strip():
                notes.append(part.strip())
        if "HostIndex" in kv:
            cur = {"t": t, "tag": tag, "host_uid": _int_s(kv.get("HostIndex")), "host_name": kv.get("HostName"), "host_num": _int_s(kv.get("HostNum")),
                   "buyer_uid": _int_s(kv.get("BuyIndex")), "buyer_name": kv.get("BuyName"), "gold": _int_s(kv.get("TotalGold")),
                   "db": " ".join(notes)[:60] or None, "items": []}
            out.append(cur)
        elif "ItemIndex" in kv:
            it = {"code": _int_s(kv.get("ItemIndex")), "plate": _int_s(kv.get("Plate")), "posx": _int_s(kv.get("PosX")),
                  "amount": _int_s(kv.get("Amount")), "gold": _int_s(kv.get("Gold")), "new_amount": _int_s(kv.get("NewAmount")),
                  "old_amount": _int_s(kv.get("OldAmount")), "user_uid": _int_s(kv.get("UserIndex")), "user_name": kv.get("UserName")}
            if cur is not None and cur["tag"] == tag:
                cur["items"].append(it)
            else:
                cur = {"t": t, "tag": tag, "host_uid": None, "host_name": None, "host_num": None, "buyer_uid": it["user_uid"],
                       "buyer_name": it["user_name"], "gold": None, "db": None, "items": [it]}
                out.append(cur)
    return out


def _int_s(v):
    """Целое из текста журнала или None."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def selfstore_files(f, t, errors, user=None, unread=None):
    """Файлы Log_SelfStore всех копий GameServer за период (белый список domains/logs.py: источник gslog, вид Log_SelfStore) →
    [(копия, имя, ГГГГММДД, строки)]. Читается весь файл (logs.scan, общий доступ). ★ ревизия 54 Н-4: бюджет чтения logs.charge — на
    пользователя запроса user (консоль — «console»), как «Деньги» по ревизии 53. ★ Н-3: список logs.files обрезан FILES_MAX новыми файлами
    (признак more): дни периода старше самого старого файла списка служба на сервере дочитывает по имени файла (logs.stat — атрибуты по
    пути, без SSH); с ПК (каждый stat — вызов SSH) они не читаются и попадают в unread [{proc, before, listed, total}] — честная пометка."""
    from core import config
    from domains import logs
    out = []
    who = user or "trade.stores"

    def read(proc, name, day, size):
        try:
            r = logs.scan("gslog", proc, name, kind="Log_SelfStore", needles=("sec :",), show_ip=False, user=who, size=size)
        except Exception as ex:
            errors.append("журнал лавок %s не прочитан: %s" % (name, ex if isinstance(ex, OpRefused) else ex.__class__.__name__))
            return
        if not r.get("missing"):
            out.append((proc, name, day, r["lines"]))
    for proc in logs.procs_of("gslog"):
        try:
            lst = logs.files("gslog", proc, "Log_SelfStore")
        except Exception as ex:
            errors.append("журнал лавок %s не прочитан: %s" % (proc, ex.__class__.__name__ if not isinstance(ex, OpRefused) else ex))
            continue
        if lst.get("missing"):
            continue
        listed = []
        for x in lst["files"]:
            m = _LOG_NAME.match(x["name"])
            if not m:
                continue
            listed.append(m.group(1))
            if f <= m.group(1) <= t:
                read(proc, x["name"], m.group(1), x.get("size"))
        if not lst.get("more") or not listed or min(listed) <= f:
            continue
        before = min(listed)                    # дни периода [f; before) в список не попали
        if config.get().on_server:
            d = datetime.datetime.strptime(f, "%Y%m%d")
            while d.strftime("%Y%m%d") < before:
                day = d.strftime("%Y%m%d")
                name = "SelfStore_%s.txt" % day
                try:
                    st = logs.stat("gslog", proc, name, "Log_SelfStore")
                except Exception as ex:
                    errors.append("журнал лавок %s не прочитан: %s" % (name, ex if isinstance(ex, OpRefused) else ex.__class__.__name__))
                    st = None
                if st:
                    read(proc, name, day, st[0])
                d += datetime.timedelta(days=1)
        elif unread is not None:
            unread.append({"proc": proc, "before": before, "listed": len(lst["files"]), "total": lst.get("total")})
    return out


def stores(q, user=None):
    """Лавки за период: сделки по журналам PersonalStore* (продавец Userindex → покупатель Tuserindex: вещи; золото — обратно), по дням;
    журнал GameServer Log_SelfStore (открытие, закрытие, покупка, подтверждение базы) и сверка «покупок по журналу ↔ сделок в базе» по дням;
    открытые сейчас лавки — пометка «показать нельзя». → dict."""
    check_input(q, "stores")
    svc = econ._svc(q)
    want_logs = str(q.get("logs") if q.get("logs") not in (None, "") else "1") == "1"
    out = {"svc": svc, "period": None, "sales": [], "sales_total": 0, "days": [], "cats": None, "total": None, "log": None, "open_note": OPEN_NOTE,
           "errors": [], "notes": [], "service_sales": [], "service_total": 0}
    f, t = _period(q)
    out["period"] = {"from": f, "to": t}
    edges, _c, capped, _g = collect(f, t, out["errors"], groups={"store"})
    out["capped"] = any(capped.values())
    sales = {}
    for e in edges:
        seller = (e["tu"], e["ti"], e["tn"]) if e["what"] == "gold" else (e["fu"], e["fi"], e["fn"])
        buyer = (e["fu"], e["fi"], e["fn"]) if e["what"] == "gold" else (e["tu"], e["ti"], e["tn"])
        k = (e["t"], seller[0], seller[1], buyer[0], buyer[1])
        s = sales.setdefault(k, {"t": e["t"], "su": seller[0], "si": seller[1], "sn": seller[2], "bu": buyer[0], "bi": buyer[1], "bn": buyer[2],
                                 "gold": 0, "items": [], "cat": pair_cat(seller[0], buyer[0])})
        if e["what"] == "gold":
            s["gold"] += e["qty"]
        else:
            it = refdata.item(e["code"]) if e["code"] is not None else {"name": "", "icon": None}
            s["items"].append({"code": e["code"], "qty": e["qty"], "src": e["src"], "name": it["name"], "icon": it["icon"], "serial": e["serial"]})
    cats = {c: {"sales": 0, "gold": 0, "items": 0} for c in CATS}
    days = {}
    for s in sales.values():
        x = cats[s["cat"]]
        x["sales"] += 1
        x["gold"] += s["gold"]
        x["items"] += sum(i["qty"] for i in s["items"])
        d = days.setdefault(s["t"].strftime("%Y%m%d"), {"day": s["t"].strftime("%Y%m%d"), "cats": {c: {"sales": 0, "gold": 0} for c in CATS},
                                                         "log_buy": None, "log_ok": None})
        d["cats"][s["cat"]]["sales"] += 1
        d["cats"][s["cat"]]["gold"] += s["gold"]
    out["cats"] = cats
    out["total"] = {k: sum(cats[c][k] for c in CATS if econ._in_total(c, svc)) for k in ("sales", "gold", "items")}
    lst = sorted(sales.values(), key=lambda s: s["t"], reverse=True)
    if svc != "in":                                   # ★ ревизия 54 Н-5: служебные — отдельным списком
        sv = [s for s in lst if s["cat"] == "service"]
        lst = [s for s in lst if s["cat"] == "player"]
        out["service_total"], out["service_sales"] = len(sv), sv[:STORE_ROWS]
    out["sales_total"] = len(lst)
    out["sales"] = lst[:STORE_ROWS]
    if want_logs:
        unread = []
        files = selfstore_files(f, t, out["errors"], user, unread)
        evs = []
        for proc, name, day, lines in files:
            for ev in parse_selfstore(lines, day[:4]):
                ev["proc"], ev["file"] = proc, name
                evs.append(ev)
        evs.sort(key=lambda e: e["t"], reverse=True)
        counts = {}
        for ev in evs:
            dd = ev["t"].strftime("%Y%m%d")
            c = counts.setdefault(dd, {})
            c[ev["tag"]] = c.get(ev["tag"], 0) + 1
            if ev["tag"] in ("BUY", "INSERT") and ev.get("host_uid") is not None:
                d = days.setdefault(dd, {"day": dd, "cats": {c2: {"sales": 0, "gold": 0} for c2 in CATS}, "log_buy": None, "log_ok": None})
                key = "log_buy" if ev["tag"] == "BUY" else "log_ok"
                d[key] = (d[key] or 0) + 1
        read_days = {dd for _p, _n, dd, _l in files}
        cut = max([u["before"] for u in unread] or [""])        # ★ ревизия 54 Н-3: дни раньше — журнал не прочитан
        for d in days.values():
            if d["log_buy"] is None and (d["day"] in counts or d["day"] in read_days):
                d["log_buy"] = 0
            if d["log_ok"] is None and (d["day"] in counts or d["day"] in read_days):
                d["log_ok"] = 0
            d["log_unread"] = bool(cut) and d["day"] < cut and d["day"] not in read_days
        for u in unread:
            out["notes"].append("журнал лавок %s за дни до %s не прочитан (в списке файлов только %d новых из %s)" % (
                u["proc"], u["before"], u["listed"], u["total"] if u["total"] is not None else "?"))
        out["log"] = {"files": [{"proc": p, "file": n, "day": d, "lines": len(ls)} for p, n, d, ls in files], "events": evs[:LOG_EVENTS],
                      "events_total": len(evs), "by_day": [dict(day=k, **v) for k, v in sorted(counts.items(), reverse=True)],
                      "unread": unread}
    out["days"] = sorted(days.values(), key=lambda d: d["day"], reverse=True)
    for d in out["days"]:
        d["sales"] = sum(d["cats"][c]["sales"] for c in CATS)           # сверка с журналом — все сделки (журнал категорий не знает)
        d["total"] = {k: sum(d["cats"][c][k] for c in CATS if econ._in_total(c, svc)) for k in ("sales", "gold")}
    return out
