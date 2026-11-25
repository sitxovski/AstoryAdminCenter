# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""econ.py — раздел «Экономика: золото» (шаг А6.3, 21.11.2026; разбор research_a6_economy_20261121.md §3 строка А6.3, §2.2, §2.3; реверс и
отчёт — Reports/admin_center/impl_a6_econ_20261121.md §А6.3). Чтение игровых баз логином asda_admin (только SELECT); ПИШЕТ только своя
база панели AsdaAdmin (суточный снимок золота adm.EconDaily / adm.EconDailyChar, sql/adminc_18_econ.sql).

ЗОЛОТО персонажа — только Joy1.dbo.Item, Code = 20551 (все обновления золота в процедурах Joy1 — Plate = 2; склада золота нет: склад хранит
  предметы, в данных и процедурах золота вне Plate 2 нет). Одна строка на персонажа.
ЖУРНАЛЫ (JoyLog1.dbo.*) — реверс определений процедур Joy1 (отчёт §А6.3 шаг 1 а): у ВСЕХ писателей Amount = было, Ramount = стало, дельта =
  Ramount − Amount. Владелец строки — Userindex/Charidx, КРОМЕ «…To» обмена и лавки: там баланс в строке — Tuserindex/Tcharidx (Userindex —
  контрагент). Таблица без писателя (знак не снят) и дубли — НЕ считаются, показываются с пометкой (SKIPPED).
ЗОЛОТО С МОБА в журналы не попадает (отчёт §А6.3 шаг 1 б: подбор → пакет 2011 → DBManager → Joy1.UPItemPick, строки PickGold / Pick в теле
  процедуры закомментированы). Поэтому «неучтённое» = (снимок − предыдущий снимок) − сумма дельт журналов между ними. ★ ревизия 52 Н-2: без
  журнала золото меняют и другие известные пути (UNLOGGED: подбор и дроп, выдача GM-командой тем же пакетом 2011, награда ограниченных заданий
  CRT_UPLimitationReward, usp_CSusedItemToBuyUpdate); учтены по данным: сбор переноса опций (TransferOption.Gm), создание персонажа (+1,
  CharEventCreate), OpGameMoneyAdd (ItemEvent Code 10551), правки золота самой панелью (adm.audit gold.set и его откат).
СЛУЖЕБНЫЕ учётки ≤ 5000 (players.OPERATOR_MAX_UID) — отдельной строкой, не в общем итоге; переключатель svc=in включает их (как в money).
ВРЕМЯ — местные часы SQL-сервера (Edate журналов — GETDATE процедур; снимок пишет GETDATE того же сервера в момент чтения Item).
Каждое значение — параметром; даты ГГГГММДД — CONVERT(datetime2, ?, 112); имена таблиц — только из констант модуля; в тексте SQL нет
русских букв. Нет таблицы — строка в errors, остальное считается. Побочных эффектов при импорте нет.
"""
import datetime
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import acjournal, players, refdata

GOLD = 20551                         # код золота (Item.Code)
SERVICE_MAX = players.OPERATOR_MAX_UID     # служебные учётки 1…5000
DAYS_DEFAULT = 30                    # потоки по дням: период по умолчанию
DAYS_MAX = 366                       # предел периода
TOP_DEFAULT = 50                     # богатейших по умолчанию
TOP_MAX = 200                        # предел списка
RARE_MAX = 200                       # «редкое на руках»: кодов в ответе не больше
CHAR_N = 50                          # неучтённое по персонажам: строк в ответе
SNAP_LIST = 60                       # снимков в списке
CATS = ("player", "service")         # игрок > 5000 / служебная ≤ 5000
GRADE_FILE = r"ConfigSet\announce_codes.txt"   # таблица «редкого» P11/P59 по умолчанию (ключ GradeTableFile секции P11_ServerAnnounceSources)
GRADE_GS = "GameServer"              # копия GS, чьи patches.ini и таблица читаются

# Источники золота: key — имя в ответе, table — JoyLog1.dbo.<table>, owner — u (Userindex/Charidx) или t (Tuserindex/Tcharidx), code —
# только строки Code = 20551 (True) или этим кодом (число), extra — ещё условие (константа), kind — вид дельты: ba (по умолчанию: Ramount −
# Amount, было → стало), neg (−Gm: сумма без было/стало, списание), amt (Amount = сумма поступления), one (+1 на строку);
# split — столбец разбивки (State), sign — знак по реверсу (+ поступление, − списание, ± по строке),
# proc — писатель (Joy1), title — подпись консоли (веб — свой перевод по key). Порядок — как в отчёте §А6.3 таблица 1.
SOURCES = (
    {"key": "MoneyBuy", "table": "MoneyBuy", "owner": "u", "sign": "-", "proc": "UPBuyitem", "title": "покупка у NPC"},
    {"key": "MoneySell", "table": "MoneySell", "owner": "u", "sign": "+", "proc": "UPSellitem", "title": "продажа NPC"},
    {"key": "MoneyCraft", "table": "MoneyCraft", "owner": "u", "sign": "-", "proc": "UPItemCraft", "title": "ремесло"},
    {"key": "MoneyExchangeBuy", "table": "MoneyExchangeBuy", "owner": "u", "sign": "-", "proc": "UPExchangeItemBuy", "title": "биржа: покупка"},
    {"key": "MoneyExchangeFee", "table": "MoneyExchangeFee", "owner": "u", "sign": "-", "proc": "UPItemExchangeLock", "title": "биржа: сбор за выставление"},
    {"key": "MoneyReward", "table": "MoneyReward", "owner": "u", "sign": "+", "proc": "UPRewardGM", "title": "награда (эпизод)"},
    {"key": "MoneyTelePort", "table": "MoneyTelePort", "owner": "u", "sign": "-", "proc": "UPTeleportFee", "title": "телепорт"},
    {"key": "MoneyUse", "table": "MoneyUse", "owner": "u", "sign": "-", "proc": "UPClanCreate, UPClanMaxGrade", "title": "клан: создание и рост"},
    {"key": "MoneyWasteBasket", "table": "MoneyWasteBasket", "owner": "u", "sign": "+", "proc": "UPItemDump", "title": "корзина (выброс предметов)"},
    {"key": "MoneyCampReward", "table": "MoneyCampReward", "owner": "u", "sign": "+", "proc": "UpCampRewarditem", "title": "награда лагеря"},
    {"key": "TradeGoldFrom", "table": "TradeGoldFrom", "owner": "u", "sign": "-", "proc": "UPItemChange", "title": "обмен: отдал"},
    {"key": "TradeGoldTo", "table": "TradeGoldTo", "owner": "t", "sign": "+", "proc": "UPItemChange", "title": "обмен: получил"},
    {"key": "TradeShellGoldFrom", "table": "TradeShellGoldFrom", "owner": "u", "sign": "-", "proc": "UPShellItemChange", "title": "обмен ракушек: отдал"},
    {"key": "TradeShellGoldTo", "table": "TradeShellGoldTo", "owner": "t", "sign": "+", "proc": "UPShellItemChange", "title": "обмен ракушек: получил"},
    {"key": "PersonalStoreGoldFrom", "table": "PersonalStoreGoldFrom", "owner": "u", "sign": "+", "proc": "UPSelfStoreBuy", "title": "лавка: продавец получил"},
    {"key": "PersonalStoreGoldTo", "table": "PersonalStoreGoldTo", "owner": "t", "sign": "-", "proc": "UPSelfStoreBuy", "title": "лавка: покупатель заплатил"},
    {"key": "CampShopUseGold", "table": "CampShopUseGold", "owner": "u", "sign": "-", "proc": "UPBuyItemCampShop", "title": "лавка лагеря"},
    {"key": "TradeItemFrom", "table": "TradeItemFrom", "owner": "u", "sign": "-", "code": True, "proc": "UPItemChange",
     "title": "обмен всей кучкой: отдал"},
    {"key": "TradeitemTo", "table": "TradeitemTo", "owner": "t", "sign": "+", "code": True, "proc": "UPItemChange",
     "title": "обмен: получил без своей кучки"},
    {"key": "ItemEvent", "table": "ItemEvent", "owner": "u", "sign": "±", "code": True, "split": "State",
     "proc": "UPItemUpgradeReset, UPItemUpperRefine, UPItemRetake, UPItemExchangeRestore, UPExchangeItemBuy, UPCampKickFee, UPSellItemCommission",
     "title": "события предметов (ItemEvent)"},
    {"key": "AdminitemLog", "table": "AdminitemLog", "owner": "u", "sign": "±", "code": True, "split": "State",
     "proc": "adm.ItemGive, adm.ItemRecover, adm.ItemUndo", "title": "оператор (AdminitemLog)"},
    # ★ ревизия 52 Н-1: UPNewItemRefine — `@RGm=Amount=Amount-@Gm` → ItemRefine (20551, @RGm+@Gm, @RGm, State+'Use GameMoney'), было → стало
    {"key": "ItemRefine", "table": "ItemRefine", "owner": "u", "sign": "-", "code": True, "proc": "UPNewItemRefine", "title": "алхимия (ItemRefine)"},
    # ★ ревизия 52 С-1: UPItemTransferOption — строка TransferOption (…, Gm, Flag), затем `@TGm=Amount=Amount-@Gm … Code=20551` в той же
    #   транзакции (сбой — ROLLBACK): строки было/стало нет, дельта −Gm
    {"key": "TransferOption", "table": "TransferOption", "owner": "u", "sign": "-", "kind": "neg", "proc": "UPItemTransferOption",
     "title": "перенос опций (TransferOption.Gm)"},
    # ★ ревизия 52 Н-2: OpGameMoneyAdd — `@RGm=Amount=Amount+@Gm` → ItemEvent (Code 10551 — опечатка оригинала, Amount = @Gm, Ramount = стало)
    {"key": "OpGameMoneyAdd", "table": "ItemEvent", "owner": "u", "sign": "+", "kind": "amt", "code": 10551, "extra": "State = 'Clan Event GM Gain'",
     "proc": "OpGameMoneyAdd", "title": "выдача события клана (ItemEvent 10551)"},
    # ★ ревизия 52 Н-2: UPCreateChar кладёт новому персонажу строку золота Amount = 1 и пишет CharEventCreate (одна строка на персонажа)
    {"key": "CharEventCreate", "table": "CharEventCreate", "owner": "u", "sign": "+", "kind": "one", "proc": "UPCreateChar",
     "title": "создание персонажа (+1)"},
)
# ★ ревизия 52 С-2: правки золота самим админ-центром — в JoyLog1 их нет, только журнал действий AsdaAdmin.adm.audit (время — SYSDATETIME
#   того же SQL-сервера, шкала журналов): gold.set / gold.set.undo — было → стало в before_json / after_json; восстановление и копия персонажа
#   (char.restore, char.copy, char.copy.undo) кладут или убирают строки Item с золотом, но сумму в журнал не пишут — честная пометка «сумма не
#   записана», в неучтённом такие персонажи помечены.
PANEL = {"key": "panel", "table": "adm.audit", "owner": "u", "sign": "±", "proc": "gold.set, gold.set.undo (панель)", "title": "правки панели (adm.audit)"}
PANEL_EXACT = ("gold.set", "gold.set.undo")
PANEL_UNKNOWN = ("char.restore", "char.copy", "char.copy.undo")
# Известные пути без журнала золота (Н-2) — в неучтённое; ключ → (текст, писатель)
UNLOGGED = (("pick", "подбор золота и дроп с монстров", "UPItemPick (строки PickGold / Pick закомментированы)"),
            ("gm", "выдача золота GM-командой", "Recv_OperatorCommand_Add → пакет 2011 → UPItemPick"),
            ("limitation", "награда ограниченных заданий", "CRT_UPLimitationReward (+@iAddGold, журнала золота нет)"),
            ("csused", "списание при покупке за использованное", "usp_CSusedItemToBuyUpdate (DBManager её не вызывает)"),
            ("panel_char", "восстановление и копия персонажа панелью", "char.restore, char.copy (сумма в adm.audit не записана)"),
            ("delete", "удаление персонажа", "строка золота уходит из Item"))
# Не считаются (пометка): why — ключ причины, где — писатель и почему
SKIPPED = (
    {"key": "MoneyExchange", "table": "MoneyExchange", "why": "nowriter", "proc": ""},
    {"key": "MoneyTransferOption", "table": "MoneyTransferOption", "why": "nowriter", "proc": ""},
    {"key": "EpisodeEventGold", "table": "EpisodeEventGold", "why": "dup", "proc": "UPRewardGM"},
    {"key": "PickGold", "table": "PickGold", "why": "off", "proc": "UPItemPick"},
    {"key": "GainGameMoney", "table": "GainGameMoney", "why": "nowriter", "proc": ""},
    {"key": "CampGameMoney", "table": "CampGameMoney", "why": "nowriter", "proc": ""},
)
WHY = {"nowriter": "писателя нет ни в одной базе — знак не снят, не считается",
       "dup": "дубль MoneyReward (та же процедура, Amount = дельта) — не считается",
       "off": "строка журнала в процедуре закомментирована (золото с моба и подбор) — не считается"}
SRC = {s["key"]: s for s in SOURCES}
KNOWN = {s["table"].lower() for s in SOURCES} | {s["table"].lower() for s in SKIPPED}
_TBL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


# ---------------------------------------------------------------- проверка ввода

def _int(v, msg, lo, hi):
    """Целое из строки запроса в пределах [lo, hi]; иначе отказ полным текстом msg."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def _svc(q):
    """Служебные в общем итоге: «sep» (по умолчанию — отдельной строкой) или «in»."""
    v = (q.get("svc") or "").strip()
    if v and v not in ("sep", "in"):
        raise OpRefused("служебные в итоге — sep (отдельно) или in (в общем итоге)")
    return v or "sep"


def _top(q):
    """Сколько строк списка (богатейшие, редкое)."""
    return _int(q.get("n") or TOP_DEFAULT, "строк в списке экономики — целое от 1 до %d" % TOP_MAX, 1, TOP_MAX)


def _period(q, today):
    """(с, по) ГГГГММДД: проверены как даты; по умолчанию — последние DAYS_DEFAULT суток по часам SQL-сервера; не длиннее DAYS_MAX."""
    f, t = acjournal.parse_day(q.get("from"), "from"), acjournal.parse_day(q.get("to"), "to")
    if f and t and f > t:
        raise OpRefused("дата «с» позже даты «по»")
    t = t or today
    if not f:
        f = (datetime.datetime.strptime(t, "%Y%m%d") - datetime.timedelta(days=DAYS_DEFAULT - 1)).strftime("%Y%m%d")
    if f > t:
        raise OpRefused("дата «с» позже даты «по»")
    if (datetime.datetime.strptime(t, "%Y%m%d") - datetime.datetime.strptime(f, "%Y%m%d")).days + 1 > DAYS_MAX:
        raise OpRefused("период экономики — не больше %d суток" % DAYS_MAX)
    return f, t


def _source_filter(q):
    """Отбор одного источника (ключ из SOURCES) или None."""
    v = (q.get("source") or "").strip()
    if not v:
        return None
    if v not in SRC and v != PANEL["key"]:
        raise OpRefused("источник золота — один из: %s" % ", ".join(list(SRC) + [PANEL["key"]]))
    return v


def check_input(q, what):
    """Проверка ввода функции what ДО базы (те же отказы, что у функций): самотест и консоль."""
    if what == "flows":
        _svc(q)
        _source_filter(q)
        f, t = acjournal.parse_day(q.get("from"), "from"), acjournal.parse_day(q.get("to"), "to")
        if f and t and f > t:
            raise OpRefused("дата «с» позже даты «по»")
        if f and t:
            _period(q, t)
    elif what in ("richest", "rare"):
        _svc(q)
        _top(q)
    elif what == "unaccounted":
        _svc(q)
        if q.get("id") not in (None, ""):
            _int(q.get("id"), "номер снимка — целое от 1 до 2147483647", 1, 2 ** 31 - 1)
    elif what == "summary":
        _svc(q)


# ---------------------------------------------------------------- общие части

def cat_of(uid):
    """Категория учётки по номеру."""
    return "service" if int(uid) <= SERVICE_MAX else "player"


def _in_total(cat, svc):
    """Входит ли категория в общий итог: служебные — только при svc=«in»."""
    return cat != "service" or svc == "in"


def _owner(s):
    """(столбец учётки, столбец персонажа) владельца строки журнала."""
    return ("Tuserindex", "Tcharidx") if s["owner"] == "t" else ("Userindex", "Charidx")


def _gold_cond(s, alias=""):
    """Условие отбора строк источника (код золота и постоянное условие) → список."""
    cond = []
    if s.get("code"):
        cond.append("%sCode = %d" % (alias, GOLD if s["code"] is True else int(s["code"])))
    if s.get("extra"):
        cond.append(alias + s["extra"])
    return cond


def _delta(s, alias=""):
    """Дельта строки источника (SQL) по виду kind."""
    k = s.get("kind", "ba")
    if k == "neg":
        return "(-CAST(%sGm AS BIGINT))" % alias
    if k == "amt":
        return "CAST(%sAmount AS BIGINT)" % alias
    if k == "one":
        return "CAST(1 AS BIGINT)"
    return "(CAST(%sRamount AS BIGINT) - CAST(%sAmount AS BIGINT))" % (alias, alias)


def _src_sql(s, extra_cond="", group=""):
    """FROM … WHERE источника: таблица из констант, отбор золота у общих журналов предметов (Code = 20551)."""
    if not _TBL.match(s["table"]):
        raise db.DbError("неверное имя таблицы %s" % s["table"][:40])
    cond = _gold_cond(s)
    if extra_cond:
        cond.append(extra_cond)
    return "FROM dbo.%s%s%s" % (s["table"], (" WHERE " + " AND ".join(cond)) if cond else "", group)




def _cat_sql(col):
    """Выражение категории учётки по столбцу."""
    return "CASE WHEN %s <= %d THEN 'service' ELSE 'player' END" % (col, SERVICE_MAX)


def _against_sql(s):
    """Строк против ожидаемого знака (+ — дельта < 0, − — дельта > 0; ± — не считается)."""
    if s["sign"] == "+":
        return "SUM(CASE WHEN %s < 0 THEN 1 ELSE 0 END)" % _delta(s)
    if s["sign"] == "-":
        return "SUM(CASE WHEN %s > 0 THEN 1 ELSE 0 END)" % _delta(s)
    return "CAST(0 AS INT)"


def _zero():
    """Пустая ячейка денег."""
    return {"n": 0, "delta": 0, "inflow": 0, "outflow": 0}


def _add(a, r):
    """Сложить строку агрегата в ячейку."""
    a["n"] += int(r.get("n") or 0)
    a["delta"] += int(r.get("dsum") or 0)
    a["inflow"] += int(r.get("inflow") or 0)
    a["outflow"] += int(r.get("outflow") or 0)


def _total(cats, svc):
    """Итог по категориям с учётом переключателя."""
    t = _zero()
    for c in CATS:
        if _in_total(c, svc):
            for k in t:
                t[k] += cats[c][k]
    return t


def _today(g):
    """Сегодня ГГГГММДД по часам SQL-сервера."""
    return g.one("SELECT CONVERT(char(8), GETDATE(), 112) AS d")["d"]


# ---------------------------------------------------------------- потоки

def flows(q):
    """Потоки золота по дням и источникам за период (местные сутки сервера; по умолчанию — 30 суток): по каждому источнику и дню —
    строк, поступило, списано, итог по категориям учёток; строки против знака; не считающиеся таблицы — с пометкой. → dict."""
    check_input(q, "flows")                    # отказы ввода — до обращения к базе
    svc = _svc(q)
    only = _source_filter(q)
    out = {"svc": svc, "days": [], "sources": [], "skipped": [], "errors": [], "period": None}
    try:
        with db.GameReader("joylog1") as g:
            f, t = _period(q, _today(g))
            out["period"] = {"from": f, "to": t}
            per_day = {}
            for s in SOURCES:
                if only and s["key"] != only:
                    continue
                uc, _cc = _owner(s)
                split = s.get("split")
                sub = "%s AS sub" % split if split else "CAST(NULL AS VARCHAR(1)) AS sub"
                cond = "Edate >= CONVERT(datetime2, ?, 112) AND Edate < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))"
                grp = " GROUP BY CONVERT(char(8), Edate, 112), %s%s" % (_cat_sql(uc), (", " + split) if split else "")
                sql = ("SELECT CONVERT(char(8), Edate, 112) AS d, %s, %s AS cat, COUNT(*) AS n, SUM(%s) AS dsum, "
                       "SUM(CASE WHEN %s > 0 THEN %s ELSE 0 END) AS inflow, SUM(CASE WHEN %s < 0 THEN -%s ELSE 0 END) AS outflow, "
                       "%s AS against %s" % (sub, _cat_sql(uc), _delta(s), _delta(s), _delta(s), _delta(s), _delta(s), _against_sql(s),
                                             _src_sql(s, cond, grp)))
                try:
                    rows = g.rows(sql, (f, t))
                except db.DbError as ex:
                    out["errors"].append("журнал золота %s не прочитан: %s" % (s["table"], ex))
                    out["sources"].append(dict(_src_public(s), read=False))
                    continue
                cats = {c: _zero() for c in CATS}
                subs, against = {}, 0
                for r in rows:
                    _add(cats[r["cat"]], r)
                    against += int(r["against"] or 0)
                    d = per_day.setdefault(r["d"], {"day": r["d"], "cats": {c: _zero() for c in CATS}, "by_source": {}})
                    _add(d["cats"][r["cat"]], r)
                    bs = d["by_source"].setdefault(s["key"], {c: _zero() for c in CATS})
                    _add(bs[r["cat"]], r)
                    if split:
                        x = subs.setdefault(r["sub"] or "", {c: _zero() for c in CATS})
                        _add(x[r["cat"]], r)
                row = dict(_src_public(s), read=True, cats=cats, total=_total(cats, svc), against=against)
                if split:
                    row["subs"] = sorted(({"sub": k, "cats": v, "total": _total(v, svc)} for k, v in subs.items()),
                                         key=lambda x: -abs(x["total"]["delta"]))
                out["sources"].append(row)
            for d in per_day.values():
                d["total"] = _total(d["cats"], svc)
                for k, v in list(d["by_source"].items()):
                    d["by_source"][k] = _total(v, svc)
            out["days"] = sorted(per_day.values(), key=lambda x: x["day"], reverse=True)
            if not only:
                out["skipped"] = _skipped(g, out["errors"], f, t)
    except db.DbError as ex:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex)
    if out["period"] and (not only or only == PANEL["key"]):
        f, t = out["period"]["from"], out["period"]["to"]
        n0 = len(out["errors"])
        evs = panel_events(datetime.datetime.strptime(f, "%Y%m%d"), datetime.datetime.strptime(t, "%Y%m%d") + datetime.timedelta(days=1), out["errors"])
        out["sources"].append(_panel_row(evs, svc, read=len(out["errors"]) == n0))
        per_day = {d["day"]: d for d in out["days"]}
        for e in evs:
            if e["delta"] is None:
                continue
            d = per_day.setdefault(e["day"], {"day": e["day"], "cats": {c: _zero() for c in CATS}, "by_source": {}})
            x = {"n": 1, "dsum": e["delta"], "inflow": max(e["delta"], 0), "outflow": max(-e["delta"], 0)}
            _add(d["cats"][cat_of(e["uid"])], x)
            d["total"] = _total(d["cats"], svc)
            bs = d["by_source"].get(PANEL["key"]) or _zero()
            if _in_total(cat_of(e["uid"]), svc):
                _add(bs, x)
            d["by_source"][PANEL["key"]] = bs
        out["days"] = sorted(per_day.values(), key=lambda x: x["day"], reverse=True)
    cats = {c: _zero() for c in CATS}
    for s in out["sources"]:
        for c in CATS:
            if s.get("read"):
                for k in cats[c]:
                    cats[c][k] += s["cats"][c][k]
    out["cats"], out["total"] = cats, _total(cats, svc)
    return out


_FAIL_RX = re.compile(r"запись №(\d+) НЕ зафиксирована")     # ops._finish: «ok» записан, фиксация в игровой базе не прошла


def panel_events(a=None, b=None, errors=None):
    """★ ревизия 52 С-2: правки золота панелью за [a; b) (datetime по часам SQL-сервера; None — без границы) из adm.audit →
    [{at, day, action, uid, idx, delta}]: delta — было → стало (gold.set, gold.set.undo) или None (восстановление и копия персонажа: сумма в
    журнал панели не записана). Запись «ok», у которой фиксация в игровой базе не прошла (следом error «запись №N НЕ зафиксирована»), не
    считается — как в core/sched.last_ok. Журнал не прочитан — [] и строка в errors."""
    import json
    acts = PANEL_EXACT + PANEL_UNKNOWN
    cond, args = ["action IN (%s)" % ",".join("?" * len(acts)), "result = 'ok'"], list(acts)
    if a is not None:
        cond.append("at >= ?")
        args.append(a)
    if b is not None:
        cond.append("at < ?")
        args.append(b)
    try:
        rows = _arows("SELECT id, at, action, target, before_json, after_json FROM adm.audit WHERE %s ORDER BY id" % " AND ".join(cond), args)
        bad = {int(m.group(1)) for r in _arows("SELECT message FROM adm.audit WHERE result = 'error' AND action IN (%s)" % ",".join("?" * len(acts)),
                                               list(acts)) for m in [_FAIL_RX.search(r["message"] or "")] if m}
    except db.DbError as ex:
        if errors is not None:
            errors.append("журнал панели не прочитан: %s" % ex)
        return []
    out = []
    for r in rows:
        if int(r["id"]) in bad:
            continue
        try:
            bj, aj = json.loads(r["before_json"] or "{}"), json.loads(r["after_json"] or "{}")
        except ValueError:
            bj, aj = {}, {}
        uid = idx = delta = None
        m = re.match(r"^char:(\d+)/(\d+)$", r["target"] or "")
        if r["action"] in PANEL_EXACT:
            if m and isinstance(bj.get("amount"), int) and isinstance(aj.get("amount"), int):
                uid, idx, delta = int(m.group(1)), int(m.group(2)), aj["amount"] - bj["amount"]
        elif r["action"] == "char.restore":
            uid, idx = aj.get("uid"), aj.get("slot")
        elif r["action"] == "char.copy":
            uid, idx = aj.get("to"), aj.get("slot")
        else:                                                   # char.copy.undo — копия удалена
            uid, idx = bj.get("to"), bj.get("slot")
        if uid is None or idx is None:
            if errors is not None and r["action"] in PANEL_EXACT:
                errors.append("правка панели №%s: было и стало не прочитаны" % r["id"])
            continue
        out.append({"id": int(r["id"]), "at": r["at"], "day": r["at"].strftime("%Y%m%d"), "action": r["action"], "uid": int(uid), "idx": int(idx),
                    "delta": delta})
    return out


def _panel_row(evs, svc, read=True):
    """Строка источника «панель» по событиям: точные (было → стало) — в итог, без суммы — счётом unknown."""
    cats = {c: _zero() for c in CATS}
    unknown = 0
    for e in evs:
        if e["delta"] is None:
            unknown += 1
            continue
        _add(cats[cat_of(e["uid"])], {"n": 1, "dsum": e["delta"], "inflow": max(e["delta"], 0), "outflow": max(-e["delta"], 0)})
    return dict(_src_public(PANEL), read=read, cats=cats, total=_total(cats, svc), against=0, unknown=unknown)


def _src_public(s):
    """Описание источника для ответа."""
    return {"key": s["key"], "table": s["table"], "owner": "Tuserindex" if s["owner"] == "t" else "Userindex", "sign": s["sign"],
            "gold_only": bool(s.get("code")), "code": (GOLD if s.get("code") is True else s.get("code")), "kind": s.get("kind", "ba"),
            "proc": s["proc"], "title": s["title"], "split": s.get("split")}


def _skipped(g, errors, f=None, t=None):
    """Не считающиеся таблицы: причина и строк (за период, если задан; иначе всего). Нет таблицы — read False."""
    out = []
    for s in SKIPPED:
        row = {"key": s["key"], "table": s["table"], "why": s["why"], "why_text": WHY[s["why"]], "proc": s["proc"], "rows": None, "read": True}
        try:
            if f:
                r = g.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE Edate >= CONVERT(datetime2, ?, 112) AND Edate < DATEADD(DAY, 1, "
                          "CONVERT(datetime2, ?, 112))" % s["table"], (f, t))
            else:
                r = g.one("SELECT COUNT(*) AS n FROM dbo.%s" % s["table"])
            row["rows"] = int(r["n"])
        except db.DbError as ex:
            row["read"] = False
            errors.append("журнал золота %s не прочитан: %s" % (s["table"], ex))
        out.append(row)
    return out


def other_gold_tables(g):
    """Таблицы JoyLog1 вне каталога со столбцами Code, Amount, Ramount и строками Code = 20551 → [{table, rows}] — знак не снят, не считаются.
    (Новый писатель золота, которого не было при реверсе, виден здесь, а не теряется в «неучтённом».)"""
    tabs = g.rows("SELECT s.name AS sch, t.name AS tbl FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
                  "WHERE s.name = 'dbo' AND COL_LENGTH(s.name + '.' + t.name, 'Code') IS NOT NULL AND COL_LENGTH(s.name + '.' + t.name, 'Amount') "
                  "IS NOT NULL AND COL_LENGTH(s.name + '.' + t.name, 'Ramount') IS NOT NULL ORDER BY t.name")
    out = []
    for r in tabs:
        name = r["tbl"]
        if name.lower() in KNOWN or not _TBL.match(name):
            continue
        n = int(g.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE Code = %d" % (name, GOLD))["n"])
        if n:
            out.append({"table": name, "rows": n})
    return out


# ---------------------------------------------------------------- золото на руках

def _gold_rows(j):
    """Золото по персонажам сейчас: [{Userindex, Charidx, a, n}] и время чтения (часы SQL-сервера) — одним запросом."""
    rows = j.rows("SELECT Userindex, Charidx, SUM(CAST(Amount AS BIGINT)) AS a, COUNT(*) AS n, MAX(SYSDATETIME()) AS t FROM dbo.Item "
                  "WHERE Code = %d GROUP BY Userindex, Charidx" % GOLD)
    t = rows[0]["t"] if rows else j.one("SELECT SYSDATETIME() AS t")["t"]
    return rows, t


def held_now():
    """Золото на руках сейчас по категориям: {cats: {cat: {chars, sum}}, rows, at}."""
    with db.GameReader("joy1") as j:
        rows, at = _gold_rows(j)
    cats = {c: {"chars": 0, "sum": 0} for c in CATS}
    for r in rows:
        x = cats[cat_of(r["Userindex"])]
        x["chars"] += 1
        x["sum"] += int(r["a"] or 0)
    return {"cats": cats, "rows": sum(int(r["n"]) for r in rows), "at": at}


def richest(q):
    """Богатейшие персонажи по золоту (Item.Code = 20551): игроки и служебные — отдельными списками (svc=in — общий список). → dict."""
    svc = _svc(q)
    n = _top(q)
    out = {"svc": svc, "players": [], "service": [], "all": [], "cats": None, "errors": [], "n": n}
    try:
        with db.GameReader("joy1") as j:
            base = ("SELECT TOP (%d) i.Userindex, i.Charidx, SUM(CAST(i.Amount AS BIGINT)) AS gold, MAX(c.Charname) AS charname, MAX(c.Uid) AS uid, "
                    "MAX(c.Lvl) AS lvl FROM dbo.Item i LEFT JOIN dbo.Charinfo c ON c.Userindex = i.Userindex AND c.Charidx = i.Charidx "
                    "WHERE i.Code = %d%s GROUP BY i.Userindex, i.Charidx ORDER BY SUM(CAST(i.Amount AS BIGINT)) DESC, i.Userindex, i.Charidx")
            conds = {"players": " AND i.Userindex > %d" % SERVICE_MAX, "service": " AND i.Userindex <= %d" % SERVICE_MAX, "all": ""}
            for k in (("all",) if svc == "in" else ("players", "service")):
                out[k] = [_rich_row(r) for r in j.rows(base % (n, GOLD, conds[k]))]
            agg = j.rows("SELECT %s AS cat, COUNT(*) AS chars, SUM(a) AS s, MAX(a) AS mx FROM (SELECT Userindex, SUM(CAST(Amount AS BIGINT)) AS a "
                         "FROM dbo.Item WHERE Code = %d GROUP BY Userindex, Charidx) x GROUP BY %s" % (_cat_sql("Userindex"), GOLD, _cat_sql("Userindex")))
            cats = {c: {"chars": 0, "sum": 0, "max": 0} for c in CATS}
            for r in agg:
                cats[r["cat"]] = {"chars": int(r["chars"]), "sum": int(r["s"] or 0), "max": int(r["mx"] or 0)}
            out["cats"] = cats
            out["total"] = {k: (sum(cats[c][k] for c in CATS if _in_total(c, svc)) if k != "max" else
                                max([cats[c][k] for c in CATS if _in_total(c, svc)] or [0])) for k in ("chars", "sum", "max")}
    except db.DbError as ex:
        out["errors"].append("золото на руках не прочитано: %s" % ex)
    return out


def _rich_row(r):
    """Строка богатейших."""
    return {"uid": int(r["Userindex"]), "idx": int(r["Charidx"]), "gold": int(r["gold"] or 0), "char": r["charname"], "login": r["uid"],
            "lvl": r["lvl"], "cat": cat_of(r["Userindex"])}


# ---------------------------------------------------------------- редкое на руках

def grade_codes():
    """Коды «редкого» по таблице P11/P59 стойки (GradeTableFile из patches.ini GameServer, иначе ConfigSet\\announce_codes.txt): строка —
    код или «от-до», «#» — комментарий. → (множество кодов, путь от корня v2)."""
    from domains import srvtables
    rel = GRADE_FILE
    try:
        sec = None
        for ln in srvtables.stack_text(GRADE_GS + r"\ConfigSet\patches.ini").splitlines():
            t = ln.strip()
            if t.startswith("[") and t.endswith("]"):
                sec = t[1:-1].strip()
            elif sec == "P11_ServerAnnounceSources" and "=" in t and t.split("=", 1)[0].strip().lower() == "gradetablefile":
                v = t.split("=", 1)[1].split(";", 1)[0].strip()
                if v and ":" not in v and not v.startswith("\\") and ".." not in v:
                    rel = v
    except Exception:                                 # patches.ini не прочитан — путь по умолчанию (как у DLL)
        pass
    path = GRADE_GS + "\\" + rel
    return parse_grade(srvtables.stack_text(path)), path


def parse_grade(text):
    """Текст таблицы «редкого» → множество кодов (неверные строки пропускаются — как у P11_EnsureGradeTable)."""
    out = set()
    for ln in text.splitlines():
        t = ln.split("#", 1)[0].strip()
        if not t:
            continue
        m = re.match(r"^(\d+)\s*(?:-\s*(\d+))?$", t)
        if not m:
            continue
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a > 0 and b >= a and b - a < 100000:
            out.update(range(a, b + 1))
    return out


HELD_SRC = ("Item", "Exitem", "ItemPostBox", "gifts")     # места хранения с учёткой (shopdata.HELD_TABLES)


def rare(q):
    """«Редкое на руках»: коды таблицы редкого (P11/P59), которые сейчас есть у персонажей — по категориям учёток (Item, Exitem, ItemPostBox,
    gifts), общий счёт shopdata.held_counts (ещё ItemTaken и висящие подарки gp7), события P59 за 30 суток (выпало / подобрано). → dict."""
    from domains import shopdata
    svc = _svc(q)
    n = _top(q)
    out = {"svc": svc, "rows": [], "errors": [], "rare_codes": 0, "present": 0, "table": None, "p59": None, "capped": False}
    try:
        codes, path = grade_codes()
    except Exception as ex:
        out["errors"].append("таблица редкого не прочитана: %s" % ex.__class__.__name__)
        return out
    out.update(rare_codes=len(codes), table=path)
    if not codes:
        out["errors"].append("таблица редкого пуста")
        return out
    per = {}
    try:
        with db.GameReader("joy1") as j:
            for t in HELD_SRC:
                try:
                    rows = j.rows("SELECT Code, %s AS cat, COUNT(*) AS n, SUM(CAST(Amount AS BIGINT)) AS a, COUNT(DISTINCT CAST(Userindex AS BIGINT) * 256 "
                                  "+ Charidx) AS chars FROM dbo.%s WHERE Code > 0 GROUP BY Code, %s" % (_cat_sql("Userindex"), t, _cat_sql("Userindex")))
                except db.DbError as ex:
                    out["errors"].append("места хранения %s не прочитаны: %s" % (t, ex))
                    continue
                for r in rows:
                    c = int(r["Code"])
                    if c not in codes:
                        continue
                    x = per.setdefault(c, {cat: {"rows": 0, "amount": 0, "chars": 0, "where": {}} for cat in CATS})[r["cat"]]
                    x["rows"] += int(r["n"])
                    x["amount"] += int(r["a"] or 0)
                    x["chars"] += int(r["chars"])        # по месту хранения: один персонаж в двух местах считается дважды (поле where)
                    x["where"][t] = x["where"].get(t, 0) + int(r["n"])
    except db.DbError as ex:
        out["errors"].append("предметы на руках не прочитаны: %s" % ex)
        return out
    out["present"] = len(per)

    def key(c):
        a = per[c]
        return (-sum(a[cat]["rows"] for cat in CATS if _in_total(cat, svc)), c)
    chosen = sorted(per, key=key)[:min(n, RARE_MAX)]
    out["capped"] = len(per) > len(chosen)
    held = shopdata.held_counts(chosen, {}) if chosen else {}
    if held is None:
        out["errors"].append("общий счёт «на руках» не прочитан: %s" % (shopdata.held_counts.last_error or "нет связи с Joy1"))
    p59 = _p59_counts(chosen, out["errors"])
    out["p59"] = None if p59 is None else {"days": DAYS_DEFAULT, "rows": sum(v["drop"] + v["pickup"] for v in p59.values())}
    for c in chosen:
        it = refdata.item(c)
        a = per[c]
        tot = {k: sum(a[cat][k] for cat in CATS if _in_total(cat, svc)) for k in ("rows", "amount", "chars")}
        out["rows"].append({"code": c, "name": it["name"], "icon": it["icon"], "cats": a, "total": tot,
                            "held": (held or {}).get(c) if held is not None else None,
                            "p59": (p59 or {}).get(c, {"drop": 0, "pickup": 0}) if p59 is not None else None})
    return out


def _p59_counts(codes, errors):
    """События P59 за DAYS_DEFAULT суток по коду: {код: {drop, pickup}} (виды 4 / 5 ac.other по каталогу KindText) или None (не прочитано)."""
    if not codes:
        return {}
    cat = acjournal.catalog()[0]["tables"].get("other", ())
    texts = {r["n"]: r["text"] for r in cat if r["n"] in (4, 5)}
    if set(texts) != {4, 5}:
        errors.append("виды P59 (ac.other 4 и 5) не найдены в каталоге журнала")
        return None
    try:
        with db.GameReader("joylog1") as g:
            rows = g.rows("SELECT item_code, event_kind, COUNT(*) AS n FROM ac.other WHERE event_kind IN (?, ?) AND ev_local >= DATEADD(DAY, ?, "
                          "GETDATE()) AND item_code IN (%s) GROUP BY item_code, event_kind" % ",".join("?" * len(codes)),
                          [texts[4], texts[5], -DAYS_DEFAULT] + list(codes))
    except db.DbError as ex:
        errors.append("журнал P59 не прочитан: %s" % ex)
        return None
    out = {}
    for r in rows:
        x = out.setdefault(int(r["item_code"]), {"drop": 0, "pickup": 0})
        x["drop" if r["event_kind"] == texts[4] else "pickup"] += int(r["n"])
    return out


# ---------------------------------------------------------------- суточный снимок (AsdaAdmin)

def _arows(sql, params=()):
    """Запрос к AsdaAdmin → список dict."""
    cn = db.admin()
    try:
        return db.admin_rows(cn, sql, params)
    finally:
        cn.close()


def take_snapshot(by, via, job_id=None):
    """Снять снимок золота: прочитать Item (одним запросом, время — часы SQL-сервера) и записать строку adm.EconDaily и строки
    adm.EconDailyChar ОДНОЙ транзакцией AsdaAdmin. В игровые базы ничего не пишется. → dict строки снимка."""
    with db.GameReader("joy1") as j:
        rows, at = _gold_rows(j)
    cats = {c: {"chars": 0, "sum": 0} for c in CATS}
    for r in rows:
        x = cats[cat_of(r["Userindex"])]
        x["chars"] += 1
        x["sum"] += int(r["a"] or 0)
    total = cats["player"]["sum"] + cats["service"]["sum"]
    cn = db.admin()
    try:
        cn.autocommit = False
        cur = cn.cursor()
        cur.execute("SET NOCOUNT ON; INSERT adm.EconDaily (snap_day, taken_local, total, players, service, chars_players, chars_service, item_rows, "
                    "taken_by, via, job_id) OUTPUT INSERTED.id VALUES (CONVERT(char(8), ?, 112), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    at, at, total, cats["player"]["sum"], cats["service"]["sum"], cats["player"]["chars"], cats["service"]["chars"],
                    sum(int(r["n"]) for r in rows), (by or "")[:32], (via or "")[:8], job_id)
        sid = int(cur.fetchone()[0])
        if rows:
            cur.fast_executemany = True
            cur.executemany("INSERT adm.EconDailyChar (snap_id, Userindex, Charidx, amount) VALUES (?, ?, ?, ?)",
                            [(sid, int(r["Userindex"]), int(r["Charidx"]), int(r["a"] or 0)) for r in rows])
        cn.commit()
    except Exception:
        try:
            cn.rollback()
        except Exception:
            pass
        raise
    finally:
        cn.close()
    return {"id": sid, "taken_local": at, "total": total, "cats": cats}


def snapshots(limit=SNAP_LIST):
    """Последние снимки (новые сверху)."""
    return _arows("SELECT TOP (%d) id, snap_day, taken_local, total, players, service, chars_players, chars_service, item_rows, taken_by, via, "
                  "job_id FROM adm.EconDaily ORDER BY taken_local DESC, id DESC" % int(limit))


def journal_sums(a, b, per_char=False, errors=None):
    """Сумма дельт считающихся журналов за [a; b) (datetime по часам SQL-сервера) → {cat: дельта} и, при per_char, {(uid, idx): дельта}."""
    cats, chars = {c: 0 for c in CATS}, {}
    with db.GameReader("joylog1") as g:
        for s in SOURCES:
            uc, cc = _owner(s)
            cond = "Edate >= ? AND Edate < ?"
            grp = " GROUP BY %s, %s" % (uc, cc)
            try:
                rows = g.rows("SELECT %s AS u, %s AS c, SUM(%s) AS d %s" % (uc, cc, _delta(s), _src_sql(s, cond, grp)), (a, b))
            except db.DbError as ex:
                if errors is not None:
                    errors.append("журнал золота %s не прочитан: %s" % (s["table"], ex))
                continue
            for r in rows:
                d = int(r["d"] or 0)
                cats[cat_of(r["u"])] += d
                if per_char:
                    k = (int(r["u"]), int(r["c"]))
                    chars[k] = chars.get(k, 0) + d
    for e in panel_events(a, b, errors):                    # ★ ревизия 52 С-2: правки панели (было → стало)
        if e["delta"] is not None:
            cats[cat_of(e["uid"])] += e["delta"]
            if per_char:
                chars[(e["uid"], e["idx"])] = chars.get((e["uid"], e["idx"]), 0) + e["delta"]
    return cats, chars


def journal_sums_multi(bounds, errors=None):
    """Суммы дельт считающихся журналов по интервалам [bounds[i]; bounds[i+1]) одним запросом на источник (интервалы — VALUES) →
    [{cat: дельта}] длины len(bounds) − 1."""
    n = len(bounds) - 1
    res = [{c: 0 for c in CATS} for _ in range(max(n, 0))]
    if n <= 0:
        return res
    vals = ", ".join("(?, ?, ?)" for _ in range(n))
    args = []
    for i in range(n):
        args.extend([i, bounds[i], bounds[i + 1]])
    with db.GameReader("joylog1") as g:
        for s in SOURCES:
            uc, _cc = _owner(s)
            code = "".join(" AND " + c for c in _gold_cond(s, "x."))
            sql = ("SELECT b.i AS i, %s AS cat, SUM(%s) AS d FROM dbo.%s x JOIN (VALUES %s) "
                   "b(i, a, z) ON x.Edate >= b.a AND x.Edate < b.z%s GROUP BY b.i, %s" % (_cat_sql("x." + uc), _delta(s, "x."), s["table"], vals, code,
                                                                                      _cat_sql("x." + uc)))
            try:
                rows = g.rows(sql, args)
            except db.DbError as ex:
                if errors is not None:
                    errors.append("журнал золота %s не прочитан: %s" % (s["table"], ex))
                continue
            for r in rows:
                res[int(r["i"])][r["cat"]] += int(r["d"] or 0)
    for e in panel_events(bounds[0], bounds[-1], errors):   # ★ ревизия 52 С-2: правки панели — в свой интервал
        if e["delta"] is None:
            continue
        for i in range(n):
            if bounds[i] <= e["at"] < bounds[i + 1]:
                res[i][cat_of(e["uid"])] += e["delta"]
                break
    return res


def unaccounted(q):
    """«Снимок − журналы» = неучтённое: по каждой паре соседних снимков — изменение золота на руках, сумма журналов между ними и разность по
    категориям; по последней паре (или по паре, кончающейся снимком id) — по персонажам (CHAR_N наибольших по модулю). → dict."""
    svc = _svc(q)
    sid = _int(q.get("id"), "номер снимка — целое от 1 до 2147483647", 1, 2 ** 31 - 1) if q.get("id") not in (None, "") else None
    out = {"svc": svc, "pairs": [], "chars": [], "snapshots": [], "errors": [], "detail_of": None}
    try:
        snaps = snapshots()
    except db.DbError as ex:
        out["errors"].append("снимки золота не прочитаны: %s" % ex)
        return out
    out["snapshots"] = [_snap_public(s) for s in snaps]
    if len(snaps) < 2:
        return out
    chron = list(reversed(snaps))
    try:
        sums = journal_sums_multi([s["taken_local"] for s in chron], out["errors"])
    except db.DbError as ex:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex)
        return out
    for i, (prev, cur) in enumerate(zip(chron, chron[1:])):
        js = sums[i]
        cats = {}
        for c in CATS:
            snap_d = int(cur["players" if c == "player" else "service"]) - int(prev["players" if c == "player" else "service"])
            cats[c] = {"snap": snap_d, "journal": js[c], "unaccounted": snap_d - js[c]}
        tot = {k: sum(cats[c][k] for c in CATS if _in_total(c, svc)) for k in ("snap", "journal", "unaccounted")}
        out["pairs"].append({"from_id": prev["id"], "to_id": cur["id"], "from": prev["taken_local"], "to": cur["taken_local"], "cats": cats, "total": tot})
    out["pairs"].reverse()
    pair = next((p for p in out["pairs"] if sid is None or p["to_id"] == sid), None)
    if sid is not None and pair is None:
        raise OpRefused("снимка №%d нет среди последних %d или он первый (неучтённое считается от предыдущего снимка)" % (sid, SNAP_LIST))
    out["detail_of"] = pair["to_id"]
    try:
        out["chars"] = _char_detail(pair, svc, out["errors"])
    except db.DbError as ex:
        out["errors"].append("неучтённое по персонажам не посчитано: %s" % ex)
    return out


def _snap_public(s):
    """Строка снимка для ответа."""
    return {"id": s["id"], "day": s["snap_day"], "taken_local": s["taken_local"], "total": int(s["total"]), "players": int(s["players"]),
            "service": int(s["service"]), "chars_players": int(s["chars_players"]), "chars_service": int(s["chars_service"]),
            "by": s["taken_by"], "via": s["via"], "job_id": s["job_id"]}


def _char_detail(pair, svc, errors):
    """Неучтённое по персонажам между снимками пары: Δ снимков − журналы, CHAR_N наибольших по модулю (служебные — только при svc=in,
    иначе отдельно помечены и идут после игроков)."""
    a = {(int(r["Userindex"]), int(r["Charidx"])): int(r["amount"]) for r in
         _arows("SELECT Userindex, Charidx, amount FROM adm.EconDailyChar WHERE snap_id = ?", (pair["from_id"],))}
    b = {(int(r["Userindex"]), int(r["Charidx"])): int(r["amount"]) for r in
         _arows("SELECT Userindex, Charidx, amount FROM adm.EconDailyChar WHERE snap_id = ?", (pair["to_id"],))}
    _c, js = journal_sums(pair["from"], pair["to"], per_char=True, errors=errors)
    marks = {}
    for e in panel_events(pair["from"], pair["to"], errors):
        if e["delta"] is None:
            marks.setdefault((e["uid"], e["idx"]), []).append(e["action"])
    keys = set(a) | set(b) | set(js)
    rows = []
    for k in keys:
        d = b.get(k, 0) - a.get(k, 0)
        u = d - js.get(k, 0)
        if u:
            rows.append({"uid": k[0], "idx": k[1], "before": a.get(k), "after": b.get(k), "snap": d, "journal": js.get(k, 0), "unaccounted": u,
                         "cat": cat_of(k[0]), "panel": sorted(set(marks.get(k, [])))})
    rows.sort(key=lambda x: (x["cat"] == "service" and svc != "in", -abs(x["unaccounted"]), x["uid"], x["idx"]))
    rows = rows[:CHAR_N]
    if rows:
        with db.GameReader("joy1") as j:
            names = {}
            uids = sorted({r["uid"] for r in rows})
            for r in j.rows("SELECT Userindex, Charidx, Charname, Uid FROM dbo.Charinfo WHERE Userindex IN (%s)" % ",".join("?" * len(uids)), uids):
                names[(int(r["Userindex"]), int(r["Charidx"]))] = (r["Charname"], r["Uid"])
        for r in rows:
            nm = names.get((r["uid"], r["idx"]))
            r["char"], r["login"], r["gone"] = (nm[0], nm[1], False) if nm else (None, None, True)
    return rows


# ---------------------------------------------------------------- сводка

def summary(q):
    """Сводка: золото на руках по категориям, последний снимок и неучтённое последней пары, каталог источников (строк всего, против знака),
    не считающиеся таблицы и таблицы вне каталога с золотом (знак не снят). → dict."""
    svc = _svc(q)
    out = {"svc": svc, "held": None, "last": None, "pair": None, "sources": [], "skipped": [], "other": [], "errors": [], "snapshots": 0,
           "unlogged": [{"key": k, "title": t, "proc": p} for k, t, p in UNLOGGED]}
    try:
        h = held_now()
        h["total"] = {k: sum(h["cats"][c][k] for c in CATS if _in_total(c, svc)) for k in ("chars", "sum")}
        out["held"] = h
    except db.DbError as ex:
        out["errors"].append("золото на руках не прочитано: %s" % ex)
    try:
        with db.GameReader("joylog1") as g:
            for s in SOURCES:
                uc, _cc = _owner(s)
                try:
                    rows = g.rows("SELECT %s AS cat, COUNT(*) AS n, SUM(%s) AS dsum, SUM(CASE WHEN %s > 0 THEN %s ELSE 0 END) AS inflow, "
                                  "SUM(CASE WHEN %s < 0 THEN -%s ELSE 0 END) AS outflow, %s AS against, MIN(Edate) AS a, MAX(Edate) AS b %s"
                                  % (_cat_sql(uc), _delta(s), _delta(s), _delta(s), _delta(s), _delta(s), _against_sql(s),
                                     _src_sql(s, "", " GROUP BY " + _cat_sql(uc))))
                except db.DbError as ex:
                    out["errors"].append("журнал золота %s не прочитан: %s" % (s["table"], ex))
                    out["sources"].append(dict(_src_public(s), read=False))
                    continue
                cats = {c: _zero() for c in CATS}
                against, first, last = 0, None, None
                for r in rows:
                    _add(cats[r["cat"]], r)
                    against += int(r["against"] or 0)
                    first = r["a"] if first is None or (r["a"] and r["a"] < first) else first
                    last = r["b"] if last is None or (r["b"] and r["b"] > last) else last
                out["sources"].append(dict(_src_public(s), read=True, cats=cats, total=_total(cats, svc), against=against, first=first, last=last))
            out["skipped"] = _skipped(g, out["errors"])
            n0 = len(out["errors"])
            evs = panel_events(errors=out["errors"])
            out["sources"].append(_panel_row(evs, svc, read=len(out["errors"]) == n0))
            try:
                out["other"] = other_gold_tables(g)
            except db.DbError as ex:
                out["errors"].append("таблицы вне каталога не проверены: %s" % ex)
    except db.DbError as ex:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex)
    try:
        snaps = snapshots(2)
        out["snapshots"] = int(_arows("SELECT COUNT(*) AS n FROM adm.EconDaily")[0]["n"])
        if snaps:
            out["last"] = _snap_public(snaps[0])
        if len(snaps) == 2:
            js, _ = journal_sums(snaps[1]["taken_local"], snaps[0]["taken_local"], errors=out["errors"])
            cats = {}
            for c in CATS:
                col = "players" if c == "player" else "service"
                d = int(snaps[0][col]) - int(snaps[1][col])
                cats[c] = {"snap": d, "journal": js[c], "unaccounted": d - js[c]}
            out["pair"] = {"from_id": snaps[1]["id"], "to_id": snaps[0]["id"], "from": snaps[1]["taken_local"], "to": snaps[0]["taken_local"],
                           "cats": cats, "total": {k: sum(cats[c][k] for c in CATS if _in_total(c, svc)) for k in ("snap", "journal", "unaccounted")}}
    except db.DbError as ex:
        out["errors"].append("снимки золота не прочитаны: %s" % ex)
    return out


# ---------------------------------------------------------------- операция: снимок

@register
class EconSnapshot(Operation):
    name, title, perm, reversible = "econ.snapshot", "Экономика: суточный снимок золота", "econ.snapshot", False
    schedule_runner = "service"          # чтение Joy1 и запись AsdaAdmin — на сервере; служба снимает его и сама раз в сутки (core/sched DAILY)
    schedule_repeat_days = 366           # подтверждений и второго фактора нет: повтор действует год (как бэкап БД)

    def target(self, p):
        return "econ:gold"

    def schedule_check(self, ctx, p):
        if p:
            raise OpRefused("у снимка золота параметров нет")
        return {}

    def preview(self, ctx, p):
        if {k for k in (p or {}) if k not in ("job_id", "expect")}:
            raise OpRefused("у снимка золота параметров нет")
        try:
            h = held_now()
        except db.DbError as ex:
            raise OpRefused("золото на руках не прочитано: %s" % ex)
        try:
            last = snapshots(1)
        except db.DbError as ex:
            raise OpRefused("снимки золота не прочитаны: %s" % ex)
        warn = ["пишется только база панели AsdaAdmin (adm.EconDaily и adm.EconDailyChar), игровые базы только читаются"]
        if last:
            warn.append("предыдущий снимок №%s — %s" % (last[0]["id"], str(last[0]["taken_local"])[:19]))
        tot = h["cats"]["player"]["sum"] + h["cats"]["service"]["sum"]
        return {"text": "снимок золота на руках: всего %d (игроки %d у %d персонажей, служебные %d у %d)" % (
            tot, h["cats"]["player"]["sum"], h["cats"]["player"]["chars"], h["cats"]["service"]["sum"], h["cats"]["service"]["chars"]),
            "warnings": warn}

    def apply(self, ctx, p, prev):
        r = take_snapshot(ctx.login, ctx.via, p.get("job_id"))
        return {"before": None, "after": {"id": r["id"], "total": r["total"], "players": r["cats"]["player"]["sum"],
                                          "service": r["cats"]["service"]["sum"]},
                "message": "снимок золота №%d: всего %d (игроки %d, служебные %d)" % (r["id"], r["total"], r["cats"]["player"]["sum"],
                                                                                    r["cats"]["service"]["sum"])}
