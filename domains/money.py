# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""money.py — раздел «Деньги»: монетизация gp7, ТОЛЬКО ЧТЕНИЕ (шаг А6.2, 21.11.2026; разбор research_a6_economy_20261121.md §1 строки
«gp7», «gp7 в панели», «Стоковые продажи», §2.1, §3 строка А6.2; отчёт Reports/admin_center/impl_a6_econ_20261121.md §А6.2).
Логин asda_admin (db_datareader); в базы ничего не пишется, шлюз gp7 и стойка не трогаются.

ИСТОЧНИКИ (схема снята с живой dev 21.11 — sys.columns / INFORMATION_SCHEMA; установщик шлюза AstoryServer/Patches/Gp7Gateway/install_gp7_balance.sql)
  AsdaStoryLogin.dbo.GP7PurchaseLog — журнал списаний шлюза (GP7_Purchase / GP7_GiftHold: success 1 — списано, 0 — не хватило баланса;
      GP7_GiftSettle REFUND пишет строку возврата с amount < 0). created_at — UTC (SYSUTCDATETIME).
  AsdaStoryLogin.dbo.GP7GiftLog — подарки (state H — заморожено и не выдано, C — выдано, R — деньги возвращены; test_mode 1 — заморожено
      в тестовом режиме testFixedBalance, возврат меняет только state). order_id = GP7PurchaseLog.id списания, refund_log_id — строка возврата.
  AsdaStoryLogin.dbo.[user] — учётка сайта (username = AsdaStoryOp.dbo.Us_member.Us_id, создаёт шлюз siteUserProvisionSql, server.js:314).
      Читаются ТОЛЬКО id, username, role: на password у asda_admin DENY (sql/adminc_03_grants.sql:41) — он не читается и не обходится.
  AsdaStoryLogin.dbo.GP7Balance — баланс (на dev testFixedBalance > 0: игрок видит фиксированный баланс, база не меняется, server.js:499).
  AsdaStoryOp.dbo.CashUse / SalePremium / SaleFunctional / SaleHair — СТОКОВЫЕ строки продаж (определения сняты по SSH 21.11).
      Предметы: Joy1.dbo.UPCashitemBuy (GS после списания gp7 кладёт заказ в ящик ItemPostbox и в ТОЙ ЖЕ процедуре пишет CashUse — сумма
      заказа, код < 7001 → SaleFunctional, > 7000 → SalePremium, Umac = цена). Причёски: Joy1.dbo.UPHairChange / AsdaStoryOp.dbo.UPWebMallHair
      пишут ТОЛЬКО SaleHair (Code = Hairidx − 1000, Umac = цена), строки CashUse у причёски нет (ревизия 51 Н-1). Orderidx = GP7PurchaseLog.id —
      это ЗЕРКАЛО заказов gp7, поэтому в итог gp7 оно не прибавляется и показывается рядом с пометкой «сток». Время стока — местное (GETDATE).
  ДЕНЬГИ (ревизия 51 Н-3, М-4; ветки GP7_GiftSettle в install_gp7_balance.sql): «списано» — success = 1 и amount > 0; «возвращено» — строки
      возврата (amount < 0, REFUND вне теста) И подарки R с test_mode = 1 (REFUND в тесте меняет только state, строки возврата нет — деньги
      не списывались по-настоящему); «итого» = списано − возвращено. Отказ (success = 0) — не деньги. COMMIT (C) деньги не двигает.
      Тестовые подарки (test_mode = 1) — отдельным столбцом; тестовые ПОКУПКИ в журнале неотличимы (пополнение перед списанием, server.js:565).
  Название позиции — справочник предметов панели (refdata) по коду витрины, иначе по коду выдачи из карты шлюза
      gp7-server\\premium_item_map.json (код → deliveryItemCode, price).
  Висящие подарки — та же сверка, что консольная AstoryServer/Patches/Gp7Gateway/tools/gift_reconcile.py: заморозка 'H' старше N минут,
      получатель по имени в Joy1.dbo.Charinfo (Arabic_CI_AS; при нескольких — единственный байт-в-байт), ячейки Item с этими кодами после
      заморозки, EventGainItem State='CashGift' в окне [−5 с; +окно], другие заморозки тому же получателю с общим кодом в окне ±окно;
      подсказку даёт САМА функция gift_reconcile.hint (модуль грузится из исходника на ПК или из ext/ архива выкладки — поведение одно).
      Только SELECT: временных таблиц, как у консольной версии, тут нет (assert_select_only), запросы — по одной заморозке.
СЛУЖЕБНЫЕ учётки ≤ 5000 (players.OPERATOR_MAX_UID) — отдельной строкой итогов и не в общем итоге (решение владельца №10 ещё не подтверждено,
  поэтому переключатель svc: «sep» — отдельно, по умолчанию; «in» — в общем итоге). Учётка сайта без игровой — своей строкой, в общем итоге.
ВРЕМЯ: сутки — по местным часам SQL-сервера; сдвиг «местное − UTC» берётся у сервера (как gift_reconcile) и округляется до 15 минут.
Каждое значение — параметром; даты ГГГГММДД — CONVERT(datetime2, ?, 112); в тексте SQL нет ни значений, ни русских букв.
Таблицы нет (новая база, откат установщика) — строка в errors, остальное считается. Побочных эффектов при импорте нет.
"""
import datetime
import json
import os
import re

from core import db
from core.ops import OpRefused
from domains import acjournal, players, refdata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # AstoryAdminCenter (на службе — @@ASTORY_SERVER_ROOT@@\AdminCenter)
PORT = os.path.dirname(ROOT)                               # папка с клонами (только на ПК)
RECONCILE_SRC = os.path.join(PORT, "AstoryServer", "Patches", "Gp7Gateway", "tools", "gift_reconcile.py")   # исходник сверки подарков
RECONCILE_EXT = os.path.join(ROOT, "ext", "gift_reconcile.py")             # его копия в архиве выкладки (служба исходников не видит)
PREMIUM_MAP = r"gp7-server\premium_item_map.json"                           # карта шлюза: код витрины → код выдачи и цена
GP7_CONFIG = r"gp7-server\config.json"                                      # настройки шлюза: читается ТОЛЬКО testFixedBalance
OP_DB = "AsdaStoryOp"                # база учёток игры для межбазового соединения со строкой сайта (стенд подменяет своей)
LOGIN_DB = "AsdaStoryLogin"          # база сайта gp7 для межбазового счёта со стороны AsdaStoryOp (стенд подменяет своей)
SERVICE_MAX = players.OPERATOR_MAX_UID     # служебные учётки 1…5000
PAGE = 50                            # строк на страницу по умолчанию
PAGE_MAX = 200                       # предел страницы
CODES_N = 100                        # позиций в «продажах по позициям» (отбор TOP в SQL по сумме)
DAYS_DEFAULT = 30                    # продажи по дням: период по умолчанию
DAYS_MAX = 366                       # предел периода продаж
HOLD_MIN = 10                        # «висящий» подарок — 'H' старше N минут (как gift_reconcile --minutes)
HOLDS_MAX = 200                      # висящих за один разбор не больше
STATES = ("H", "C", "R")                       # состояния GP7GiftLog: заморожен / выдан / деньги возвращены (CK_GP7GiftLog_State)
KINDS = ("buy", "gift", "refund", "fail")      # покупка / списание подарка / возврат подарка / отказ (не хватило баланса)
WHO = ("player", "service", "nolink")          # игрок > 5000 / служебная ≤ 5000 / учётка сайта без игровой
STOCK = (("SalePremium", "Umac"), ("SaleFunctional", "Umac"), ("SaleHair", "Umac"))   # таблицы стока по позициям и столбец цены
_GR = None                                     # модуль gift_reconcile.py (загружается лениво функцией reconcile)


def reconcile():
    """Модуль gift_reconcile.py шлюза gp7 (кэш на процесс): исходник на ПК, иначе копия ext/ архива выкладки."""
    global _GR
    if _GR is None:
        # ★ ревизия 56 С-1: на сервере исходник порта был бы H:\Server\… вне дерева службы — только копия ext/ со сверкой манифеста
        from domains import acsrc
        path = acsrc.pick(RECONCILE_SRC, RECONCILE_EXT)
        mods, _h = acsrc.load(os.path.dirname(path), ("gift_reconcile",), "money_src_")
        mod = mods["gift_reconcile"]
        mod.LOADED_FROM = path
        _GR = mod
    return _GR


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


def _choice(v, allowed, msg):
    """Значение из списка (пусто — None); иначе отказ."""
    v = (v or "").strip()
    if not v:
        return None
    if v not in allowed:
        raise OpRefused(msg)
    return v


def _svc(q):
    """Служебные в общем итоге: «sep» (по умолчанию — отдельной строкой) или «in»."""
    return _choice(q.get("svc"), ("sep", "in"), "служебные в итоге — sep (отдельно) или in (в общем итоге)") or "sep"


def _page(q):
    """(страница, размер) из строки запроса."""
    size = _int(q.get("size") or PAGE, "строк на странице раздела «Деньги» — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница раздела «Деньги» — целое от 1 до 1000000", 1, 1000000)
    return page, size


def _days(q):
    """(с, по) ГГГГММДД — проверены как даты (те же тексты отказов, что у журнала античита)."""
    f, t = acjournal.parse_day(q.get("from"), "from"), acjournal.parse_day(q.get("to"), "to")
    if f and t and f > t:
        raise OpRefused("дата «с» позже даты «по»")
    return f, t


def resolve_account(acc):
    """Учётка фильтра → {"uids": [Userindex], "site": [id учётки сайта], "logins": [Us_id]} или None.
    Ввод из одних цифр — и номер учётки игры, и логин (игры или сайта: логин «12345» тоже находится — урок ревизии 50 п.9); текст — логин
    игры (AsdaStoryOp.Us_member.Us_id) или сайта ([user].username), без учёта регистра (CI-сортировки обеих баз). Нет нигде — отказ."""
    acc = (acc or "").strip()
    if not acc:
        return None
    if len(acc) > 50:
        raise OpRefused("логин — не длиннее 50 знаков")
    uids, logins = [], []
    with db.GameReader("asdastoryop") as op:
        cond, args = "Us_id = ?", [op.text(acc)]
        if acc.isdigit() and int(acc) <= 2 ** 31 - 1:
            cond, args = "Userindex = ? OR " + cond, [int(acc)] + args
        for r in op.rows("SELECT Userindex, Us_id FROM Us_member WHERE %s ORDER BY Userindex" % cond, args):
            uids.append(int(r["Userindex"]))
            logins.append(r["Us_id"])
    with db.GameReader("asdastorylogin") as g:
        names = [acc] + [x for x in logins if x and x.lower() != acc.lower()]
        site = [int(r["id"]) for r in g.rows("SELECT id FROM dbo.[user] WHERE username IN (%s) ORDER BY id" % ",".join("?" * len(names)), names)]
    if not uids and not site:
        raise OpRefused("учётки «%s» нет ни в игре, ни на сайте gp7" % acc[:40])
    return {"uids": uids, "site": site, "logins": logins}


def _in(col, vals, args):
    """«col IN (?,…)» по списку (пустой список — ложь)."""
    if not vals:
        return "1 = 0"
    args.extend(vals)
    return "%s IN (%s)" % (col, ",".join("?" * len(vals)))


# ---------------------------------------------------------------- общие части

def _db_name(name):
    """Имя базы для текста SQL межбазового соединения (только буквы, цифры, «_» — константа модуля, не ввод)."""
    if not re.match(r"^[A-Za-z0-9_]+$", name):
        raise db.DbError("неверное имя базы %s" % name[:40])
    return name


def _op_db():
    """Имя базы учёток игры для текста SQL."""
    return _db_name(OP_DB)


def _shift(g):
    """Сдвиг «местное − UTC» SQL-сервера, минут (округлён до 15: два вызова часов не в одну микросекунду)."""
    s = int(g.one("SELECT DATEDIFF(second, SYSUTCDATETIME(), SYSDATETIME()) AS s")["s"])
    return int(round(s / 900.0)) * 15


def _cat_sql():
    """Выражение SQL категории учётки строки покупки (по m.Userindex межбазового соединения)."""
    return "CASE WHEN m.Userindex IS NULL THEN 'nolink' WHEN m.Userindex <= %d THEN 'service' ELSE 'player' END" % SERVICE_MAX


GIFT_NULL = ("(SELECT CAST(NULL AS BIGINT) AS order_id, CAST(NULL AS CHAR(1)) AS state, CAST(NULL AS BIT) AS test_mode, "
             "CAST(NULL AS VARCHAR(20)) AS recipient_name, CAST(NULL AS BIGINT) AS refund_log_id)")   # подарков нет: те же столбцы пустыми


def _gift_table(g, errors=None):
    """Есть ли dbo.GP7GiftLog (шлюз без P101 — нет): журнал покупок тогда читается без подарков, с пометкой в errors (раз на соединение)."""
    if not hasattr(g, "gift_ok"):
        g.gift_ok = g.one("SELECT OBJECT_ID(?) AS o", ("dbo.GP7GiftLog",))["o"] is not None
        if not g.gift_ok and errors is not None:
            errors.append("таблицы dbo.GP7GiftLog нет — подарки не показаны (шлюз без P101)")
    return g.gift_ok


def _from_purchases(gift_ok=True):
    """FROM журнала покупок: строка сайта, игровая учётка (TOP 1 по логину — без размножения строк), подарок по заказу и по возврату
    (нет таблицы подарков — пустые столбцы того же вида, остальное считается)."""
    gift = ("LEFT JOIN dbo.GP7GiftLog g ON g.order_id = p.id LEFT JOIN dbo.GP7GiftLog gr ON gr.refund_log_id = p.id" if gift_ok
            else "CROSS JOIN %s g CROSS JOIN %s gr" % (GIFT_NULL, GIFT_NULL))
    return ("FROM dbo.GP7PurchaseLog p LEFT JOIN dbo.[user] u ON u.id = p.user_id "
            "OUTER APPLY (SELECT TOP (1) x.Userindex, x.Us_id FROM %s.dbo.Us_member x WHERE x.Us_id = u.username COLLATE Arabic_CI_AS "
            "ORDER BY x.Userindex) m %s" % (_op_db(), gift))


def _who_cond(who):
    """Условие категории учётки (alias m)."""
    return {"player": "m.Userindex > %d" % SERVICE_MAX, "service": "m.Userindex <= %d" % SERVICE_MAX,
            "nolink": "m.Userindex IS NULL"}[who]


# тестовый подарок с возвратом: деньги «вернулись» без строки возврата; ISNULL — у покупки без подарка условие ЛОЖНО, а не NULL (иначе NOT (…) её отсечёт)
TEST_R = "p.success = 1 AND p.amount > 0 AND ISNULL(g.state, 'N') = 'R' AND ISNULL(g.test_mode, 0) = 1"


def _money_sql():
    """Список столбцов денег строки агрегата (alias p/g): строк, списано, возвращено (строки возврата + тестовые R), отказов, возвратов,
    тестовых подарков и их сумма."""
    return ("COUNT(*) AS n, SUM(CASE WHEN p.success = 1 AND p.amount > 0 THEN p.amount ELSE 0 END) AS gross, "
            "SUM(CASE WHEN p.success = 1 AND p.amount < 0 THEN -p.amount WHEN %s THEN p.amount ELSE 0 END) AS refunded, "
            "SUM(CASE WHEN p.success = 1 AND p.amount < 0 THEN 1 WHEN %s THEN 1 ELSE 0 END) AS refunds, "
            "SUM(CASE WHEN p.success = 0 THEN 1 ELSE 0 END) AS fails, "
            "SUM(CASE WHEN p.success = 1 AND p.amount > 0 AND g.test_mode = 1 THEN 1 ELSE 0 END) AS test_gifts, "
            "SUM(CASE WHEN p.success = 1 AND p.amount > 0 AND g.test_mode = 1 THEN p.amount ELSE 0 END) AS test_gift_sum" % (TEST_R, TEST_R))


def _in_total(cat, svc):
    """Входит ли категория в общий итог: служебные — только при svc=«in»."""
    return cat != "service" or svc == "in"


_pmap = {"at": None, "map": None, "error": None}   # кэш карты шлюза: время чтения (monotonic), {код: (выдача, цена)}, ошибка чтения


def premium_map():
    """Карта шлюза gp7 {код витрины: (код выдачи, цена)} и ошибка чтения (кэш 60 с — как srvtables.stack_text)."""
    import time
    if _pmap["at"] is None or time.monotonic() - _pmap["at"] > 60:
        from domains import srvtables
        try:
            src = json.loads(srvtables.stack_text(PREMIUM_MAP).lstrip("\ufeff"))
            out = {}
            for k, v in src.items():
                v = v if isinstance(v, dict) else {"deliveryItemCode": v}
                out[int(k)] = (int(v["deliveryItemCode"]), int(v.get("price", -1)))
            _pmap.update(map=out, error=None)
        except Exception as ex:                       # нет файла / SSH / разбор — названия по справочнику, без кода выдачи
            _pmap.update(map={}, error="карта шлюза gp7 не прочитана: %s" % ex.__class__.__name__)
        _pmap["at"] = time.monotonic()
    return _pmap["map"], _pmap["error"]


def position(code):
    """Позиция витрины gp7 → {code, name, delivery, delivery_name, map_price, icon}."""
    pm, _err = premium_map()
    code = int(code)
    it = refdata.item(code) if code >= 0 else {"name": "", "icon": None}
    dl, price = pm.get(code, (None, None))
    di = refdata.item(dl) if dl else None
    return {"code": code, "name": it["name"] or (di["name"] if di else ""), "delivery": dl, "delivery_name": di["name"] if di else None,
            "map_price": price, "icon": it["icon"] or (di["icon"] if di else None)}


def test_fixed_balance():
    """testFixedBalance шлюза (config.json gp7-server): число и ошибка. Другие ключи файла не возвращаются и не печатаются (там адреса SQL)."""
    from domains import srvtables
    try:
        v = json.loads(srvtables.stack_text(GP7_CONFIG).lstrip("\ufeff")).get("testFixedBalance", 0)
        return int(v or 0) & 0xFFFFFFFF, None
    except Exception as ex:
        return None, "настройка testFixedBalance шлюза gp7 не прочитана: %s" % ex.__class__.__name__


def _kind(r):
    """Вид строки журнала покупок."""
    if not r["success"]:
        return "fail"
    if (r["amount"] or 0) < 0:
        return "refund"
    return "gift" if r.get("gift_state") else "buy"


# ---------------------------------------------------------------- журнал покупок

def _purchase_where(q, acc, args):
    """Условие журнала покупок по фильтрам (alias p/u/m/g)."""
    cond = []
    if acc is not None:
        cond.append(_in("p.user_id", acc["site"], args))
    if q.get("code") not in (None, ""):
        cond.append("p.item_code = ?")
        args.append(_int(q.get("code"), "код позиции gp7 — целое от 0 до 4294967295", 0, 4294967295))
    kind = _choice(q.get("kind"), KINDS, "вид строки — buy (покупка), gift (подарок), refund (возврат) или fail (отказ)")
    if kind:
        cond.append({"buy": "p.success = 1 AND p.amount > 0 AND g.order_id IS NULL", "gift": "g.order_id IS NOT NULL",
                     "refund": "p.success = 1 AND p.amount < 0", "fail": "p.success = 0"}[kind])
    who = _choice(q.get("who"), WHO, "учётки — player (игроки), service (служебные ≤ 5000) или nolink (сайт без игровой)")
    if who:
        cond.append(_who_cond(who))
    test = _choice(q.get("test"), ("0", "1"), "пометка теста — 0 или 1")
    if test == "1":
        cond.append("(g.test_mode = 1 OR gr.test_mode = 1)")
    elif test == "0":
        cond.append("ISNULL(g.test_mode, 0) = 0 AND ISNULL(gr.test_mode, 0) = 0")
    return cond


def _utc_bounds(cond, args, col, f, t, shift):
    """Сутки ГГГГММДД по местным часам → условие на столбец UTC (граница «по» — начало следующих суток)."""
    if f:
        cond.append("%s >= DATEADD(minute, ?, CONVERT(datetime2, ?, 112))" % col)
        args.extend([-shift, f])
    if t:
        cond.append("%s < DATEADD(minute, ?, DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)))" % col)
        args.extend([-shift, t])


def purchases(q):
    """Журнал покупок gp7 по всем учёткам страницами: {rows, total, page, pages, size, totals, errors}. Новые сверху (id)."""
    f, t = _days(q)
    page, size = _page(q)
    svc = _svc(q)
    acc = resolve_account(q.get("account"))
    args = []
    cond = _purchase_where(q, acc, args)
    out = {"rows": [], "total": 0, "page": 1, "pages": 1, "size": size, "totals": None, "errors": [], "svc": svc}
    try:
        with db.GameReader("asdastorylogin") as g:
            shift = _shift(g)
            gok = _gift_table(g, out["errors"])
            _utc_bounds(cond, args, "p.created_at", f, t, shift)
            w = (" WHERE " + " AND ".join(cond)) if cond else ""
            agg = g.rows("SELECT %s AS cat, %s %s%s GROUP BY %s" % (_cat_sql(), _money_sql(), _from_purchases(gok), w, _cat_sql()), args)
            total = sum(int(r["n"]) for r in agg)
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages)
            rows = g.rows("SELECT p.id, p.user_id, p.item_code, p.amount, p.balance_before, p.balance_after, p.success, p.created_at, "
                          "DATEADD(minute, ?, p.created_at) AS created_local, u.username AS site_login, u.role AS site_role, m.Userindex, "
                          "m.Us_id, g.state AS gift_state, g.test_mode AS gift_test, g.recipient_name, gr.order_id AS refund_of, "
                          "gr.test_mode AS refund_test, gr.state AS refund_state %s%s ORDER BY p.id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % (_from_purchases(gok), w),
                          [shift] + args + [(page - 1) * size, size])
    except db.DbError as ex:
        out["errors"].append("журнал покупок gp7 не прочитан: %s" % ex)
        return out
    for r in rows:
        r["kind"] = _kind(r)
        r["cat"] = "nolink" if r["Userindex"] is None else ("service" if int(r["Userindex"]) <= SERVICE_MAX else "player")
        r["test"] = bool(r["gift_test"] or r["refund_test"])
        r["test_refunded"] = r["kind"] == "gift" and r["gift_state"] == "R" and bool(r["gift_test"])   # возврат в тесте: без строки возврата
        r["recipient_name"] = db.fix_text(r["recipient_name"])
        r["Us_id"] = db.fix_text(r["Us_id"])
        r["pos"] = position(r["item_code"])
    _pm, perr = premium_map()
    if perr:
        out["errors"].append(perr)
    out.update(rows=rows, total=total, page=page, pages=pages, totals=_totals(agg, svc), shift_min=shift)
    return out


def _totals(agg, svc):
    """Строки категорий {cat: {n, gross — списано, refunded — возвращено, sum — итого, fails, refunds, test_gifts, test_gift_sum}} и общий
    итог по правилу служебных (svc)."""
    keys = ("n", "gross", "refunded", "fails", "refunds", "test_gifts", "test_gift_sum")
    cats = {c: dict({k: 0 for k in keys}, sum=0) for c in WHO}
    for r in agg:
        c = cats[r["cat"]]
        for k in keys:
            c[k] += int(r.get(k) or 0)
        c["sum"] = c["gross"] - c["refunded"]
    tot = {k: sum(cats[c][k] for c in WHO if _in_total(c, svc)) for k in keys + ("sum",)}
    return {"cats": cats, "total": tot, "svc": svc, "service_in_total": svc == "in"}


# ---------------------------------------------------------------- подарки

GIFT_COLS = ("g.order_id, g.sender_user_id, g.sender_account, g.sender_userindex, g.sender_charidx, g.sender_name, g.recipient_name, "
             "g.code1, g.code2, g.code3, g.code4, g.code5, g.code6, g.code7, g.amount, g.state, g.test_mode, g.created_at, g.settled_at, "
             "g.settle_result, g.refund_log_id")        # без gs_key: ключ запроса GS панели не нужен


def _codes(r):
    """Коды позиций подарка (code1…code7, 0 — пусто)."""
    return [int(r["code%d" % i]) for i in range(1, 8) if r.get("code%d" % i)]


def gifts(q):
    """Подарки gp7 страницами: {rows, total, page, pages, size, by_state, errors}. Фильтры: state H/C/R, test 0/1, hanging=1 (H старше
    minutes), учётка (отправитель — учётка игры или сайта, или получатель — персонаж учётки), даты. Новые сверху."""
    f, t = _days(q)
    page, size = _page(q)
    state = _choice(q.get("state"), STATES, "состояние подарка — H (заморожен), C (выдан) или R (возвращён)")
    test = _choice(q.get("test"), ("0", "1"), "пометка теста — 0 или 1")
    hanging = _choice(q.get("hanging"), ("0", "1"), "«висящие» — 0 или 1") == "1"
    minutes = _int(q.get("minutes") or HOLD_MIN, "возраст висящего подарка — целое число минут от 1 до 10080", 1, 10080)
    acc = resolve_account(q.get("account"))
    names = []
    if acc and acc["uids"]:
        with db.GameReader("joy1") as j:
            names = [db.to_db_text(r["Charname"]) for r in j.rows(
                "SELECT Charname FROM Charinfo WHERE %s" % _in("Userindex", acc["uids"], []), acc["uids"]) if r["Charname"]]
    out = {"rows": [], "total": 0, "page": 1, "pages": 1, "size": size, "by_state": [], "errors": [], "minutes": minutes}
    try:
        with db.GameReader("asdastorylogin") as g:
            shift = _shift(g)
            cond, args = [], []
            if acc is not None:
                part = [_in("g.sender_user_id", acc["site"], args), _in("g.sender_userindex", acc["uids"], args)]
                if names:
                    part.append(_in("g.recipient_name", names, args))
                cond.append("(" + " OR ".join(part) + ")")
            if state:
                cond.append("g.state = ?")
                args.append(state)
            if test:
                cond.append("g.test_mode = ?")
                args.append(int(test))
            if hanging:
                cond.append(HANG_SQL)
                args.append(-minutes)
            _utc_bounds(cond, args, "g.created_at", f, t, shift)
            w = (" WHERE " + " AND ".join(cond)) if cond else ""
            total = int(g.one("SELECT COUNT(*) AS n FROM dbo.GP7GiftLog g%s" % w, args)["n"])
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages)
            rows = g.rows("SELECT %s, DATEADD(minute, ?, g.created_at) AS created_local, DATEADD(minute, ?, g.settled_at) AS settled_local, "
                          "DATEDIFF(minute, g.created_at, SYSUTCDATETIME()) AS age_min, CASE WHEN %s THEN 1 ELSE 0 END AS hang FROM dbo.GP7GiftLog g%s "
                          "ORDER BY g.created_at DESC, g.order_id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % (GIFT_COLS, HANG_SQL, w),
                          [shift, shift, -minutes] + args + [(page - 1) * size, size])
            out["by_state"] = g.rows("SELECT state, test_mode, COUNT(*) AS n, SUM(amount) AS s FROM dbo.GP7GiftLog GROUP BY state, test_mode "
                                     "ORDER BY state, test_mode")
    except db.DbError as ex:
        out["errors"].append("подарки gp7 не прочитаны: %s" % ex)
        return out
    for r in rows:
        _gift_view(r)
    out.update(rows=rows, total=total, page=page, pages=pages, shift_min=shift)
    return out


HANG_SQL = "g.state = 'H' AND g.created_at < DATEADD(minute, ?, SYSUTCDATETIME())"   # ★ ревизия 51 М-1: одна граница «висит» для значка и счёта


def _gift_view(r):
    """Поля подарка для показа: имена в виде игры, позиции с названиями, служебный ли отправитель, «висящий» (по HANG_SQL запроса)."""
    r["sender_name"], r["recipient_name"] = db.fix_text(r["sender_name"]), db.fix_text(r["recipient_name"])
    r["items"] = [position(c) for c in _codes(r)]
    r["service"] = r["sender_userindex"] is not None and int(r["sender_userindex"]) <= SERVICE_MAX
    r["hanging"] = bool(r.get("hang"))
    r["test_mode"] = bool(r["test_mode"])


def holds(q):
    """Висящие подарки 'H' старше minutes — сверка как gift_reconcile.py (подсказка — его функция hint): {holds, counts, minutes, window,
    errors, source}. Ничего не применяет: решение «commit / refund» — через координатора консольной сверкой (--emit-sql)."""
    GR = reconcile()
    minutes = _int(q.get("minutes") or HOLD_MIN, "возраст висящего подарка — целое число минут от 1 до 10080", 1, 10080)
    window = _int(q.get("window") or GR.DEFAULT_WINDOW_SEC, "окно сопоставления подарка — целое число секунд от 10 до 3600", 10, 3600)
    out = {"holds": [], "counts": None, "minutes": minutes, "window": window, "errors": [], "source": os.path.basename(GR.LOADED_FROM)}
    try:
        with db.GameReader("asdastorylogin") as g:
            shift = _shift(g)
            c = g.one("SELECT SUM(CASE WHEN g.state = 'H' THEN 1 ELSE 0 END) AS h, SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS hang, COUNT(*) AS n "
                      "FROM dbo.GP7GiftLog g" % HANG_SQL, (-minutes,))
            out["counts"] = {"H": int(c["h"] or 0), "hanging": int(c["hang"] or 0), "all": int(c["n"] or 0)}
            hs = g.rows("SELECT TOP (%d) %s, DATEDIFF(minute, g.created_at, SYSUTCDATETIME()) AS age_min, 1 AS hang FROM dbo.GP7GiftLog g WHERE %s "
                        "ORDER BY g.order_id" % (HOLDS_MAX, GIFT_COLS, HANG_SQL), (-minutes,))
            out["capped"] = out["counts"]["hanging"] > len(hs)          # ★ ревизия 51 М-2: висящих больше HOLDS_MAX — пометка
            out["holds_max"] = HOLDS_MAX
            for h in hs:
                h["others"] = []
                codes = set(_codes(h))
                lo, hi = h["created_at"] - datetime.timedelta(seconds=window), h["created_at"] + datetime.timedelta(seconds=window)
                for o in g.rows("SELECT order_id, state, CONVERT(varchar(19), created_at, 120) AS c, code1, code2, code3, code4, code5, code6, "
                                "code7 FROM dbo.GP7GiftLog WHERE recipient_name = ? AND order_id <> ? AND created_at BETWEEN ? AND ? "
                                "ORDER BY order_id", (h["recipient_name"], h["order_id"], lo, hi)):
                    if codes & set(_codes(o)):
                        h["others"].append((int(o["order_id"]), o["state"], o["c"]))
    except db.DbError as ex:
        out["errors"].append("подарки gp7 не прочитаны: %s" % ex)
        return out
    for h in hs:
        try:
            out["holds"].append(_reconcile_one(GR, h, shift, window))
        except db.DbError as ex:
            out["errors"].append("сверка подарка %d не выполнена: %s" % (h["order_id"], ex))
    return out


def _reconcile_one(GR, h, shift, window):
    """Одна заморозка: получатель, ячейки Item и EventGainItem в окне → подсказка gift_reconcile.hint (метка, пояснение)."""
    raw_recipient = h["recipient_name"]
    created_local = h["created_at"] + datetime.timedelta(minutes=shift)
    with db.GameReader("joy1") as j:
        cs = j.rows("SELECT Userindex, Charidx, Uid, CASE WHEN CAST(Charname AS VARBINARY(20)) = CAST(CAST(? AS VARCHAR(20)) AS VARBINARY(20)) "
                    "THEN 1 ELSE 0 END AS exact FROM Charinfo WITH (READUNCOMMITTED) WHERE Charname = ? COLLATE Arabic_CI_AS ORDER BY Userindex, "
                    "Charidx", (raw_recipient, raw_recipient))
        exact = [c for c in cs if c["exact"]]
        pick = cs[0] if len(cs) == 1 else (exact[0] if len(cs) > 1 and len(exact) == 1 else None)
        codes = _codes(h)
        items, evs = {}, {}
        if pick and codes:
            a = [pick["Userindex"], pick["Charidx"]]
            inn = _in("Code", sorted(set(codes)), a)
            for r in j.rows("SELECT Code, COUNT(*) AS n, SUM(CAST(Amount AS BIGINT)) AS a, MAX(CASE WHEN Fdate IS NULL OR GainDate > Fdate "
                            "THEN GainDate ELSE Fdate END) AS last FROM Item WITH (READUNCOMMITTED) WHERE Userindex = ? AND Charidx = ? AND %s "
                            "AND Code > 0 AND (GainDate >= ? OR Fdate >= ?) GROUP BY Code" % inn, a + [created_local, created_local]):
                items[int(r["Code"])] = (int(r["n"]), r["last"])
    if pick and codes:
        with db.GameReader("joylog1") as lg:
            a = [pick["Userindex"], pick["Charidx"], "CashGift"]
            inn = _in("Code", sorted(set(codes)), a)
            for r in lg.rows("SELECT Code, COUNT(*) AS n, SUM(CAST(Amount AS BIGINT)) AS a, MIN(Edate) AS f, MAX(Edate) AS l FROM dbo.EventGainItem "
                             "WITH (READUNCOMMITTED) WHERE Userindex = ? AND Charidx = ? AND State = ? AND %s AND Code > 0 AND "
                             "Edate >= DATEADD(second, -5, ?) AND Edate <= DATEADD(second, ?, ?) GROUP BY Code" % inn,
                             a + [created_local, window, created_local]):
                evs[int(r["Code"])] = (int(r["n"]), "%s..%s" % (r["f"], r["l"]))
    rec = {"order": int(h["order_id"]), "recipient": db.fix_text(raw_recipient), "codes": codes, "r_count": len(cs),
           "r_userindex": str(pick["Userindex"]) if pick else "", "r_charidx": str(pick["Charidx"]) if pick else "",
           "r_uid": db.fix_text(pick["Uid"]) if pick else ""}
    label, why = GR.hint(rec, items, evs, h["others"])
    view = dict(h)
    _gift_view(view)
    view.update(hint=label, hint_why=why, r_count=len(cs), r_userindex=pick["Userindex"] if pick else None,
                r_charidx=pick["Charidx"] if pick else None, r_uid=rec["r_uid"] or None, created_local=created_local,
                settled_local=h["settled_at"] + datetime.timedelta(minutes=shift) if h.get("settled_at") else None,
                item_after={c: n for c, (n, _l) in items.items()}, eventgain={c: n for c, (n, _s) in evs.items()},
                others=[{"order_id": o[0], "state": o[1], "created_at": o[2]} for o in h["others"]])
    return view


# ---------------------------------------------------------------- продажи по дням и позициям

DAY_KEYS = ("n", "gross", "refunds", "refunded", "sum", "gifts", "test_gifts")   # поля дня продаж: списаний, списано, возвратов, возвращено, итого, подарков, тестовых


def _span(f, t):
    """Период продаж: «с» не позже «по» и не длиннее DAYS_MAX суток; иначе отказ."""
    if f > t:
        raise OpRefused("дата «с» позже даты «по»")
    if (datetime.datetime.strptime(t, "%Y%m%d") - datetime.datetime.strptime(f, "%Y%m%d")).days + 1 > DAYS_MAX:
        raise OpRefused("период продаж — не больше %d суток" % DAYS_MAX)


def sales(q):
    """Продажи по дням и по позициям за период (по умолчанию — последние 30 суток по часам SQL-сервера): gp7 (списания success = 1,
    amount > 0; возвраты отдельно) по категориям учёток и рядом сток (CashUse и Sale*, пометка «сток», в итог не входит). → dict."""
    f, t = _days(q)
    svc = _svc(q)
    who = _choice(q.get("who"), WHO, "учётки — player (игроки), service (служебные ≤ 5000) или nolink (сайт без игровой)")
    if f and t:
        _span(f, t)
    out = {"days": [], "codes": [], "stock_days": [], "stock_codes": [], "cross": None, "errors": [], "svc": svc}
    try:
        with db.GameReader("asdastorylogin") as g:
            shift = _shift(g)
            gok = _gift_table(g, out["errors"])
            today = g.one("SELECT CONVERT(char(8), SYSDATETIME(), 112) AS d")["d"]
            t = t or today
            if not f:
                f = (datetime.datetime.strptime(t, "%Y%m%d") - datetime.timedelta(days=DAYS_DEFAULT - 1)).strftime("%Y%m%d")
            _span(f, t)
            cond, args = ["p.success = 1"], []
            if who:
                cond.append(_who_cond(who))
            _utc_bounds(cond, args, "p.created_at", f, t, shift)
            w = " WHERE " + " AND ".join(cond)
            # ★ ревизия 51 Н-3, М-4: по дням — списано (amount > 0), возвращено (строки возврата в свой день + тестовые R в день списания),
            #   итого = списано − возвращено; тестовые подарки — отдельно
            days = g.rows("SELECT d, cat, SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) AS n, SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS gross, "
                          "SUM(CASE WHEN amount < 0 OR tr = 1 THEN 1 ELSE 0 END) AS rn, SUM(CASE WHEN amount < 0 THEN -amount WHEN tr = 1 THEN amount "
                          "ELSE 0 END) AS rs, SUM(CASE WHEN gift = 1 AND amount > 0 THEN 1 ELSE 0 END) AS gifts, SUM(CASE WHEN tg = 1 AND amount > 0 "
                          "THEN 1 ELSE 0 END) AS tgn FROM (SELECT CONVERT(char(8), DATEADD(minute, ?, p.created_at), 112) AS d, %s AS cat, p.amount, "
                          "CASE WHEN g.order_id IS NULL THEN 0 ELSE 1 END AS gift, CASE WHEN %s THEN 1 ELSE 0 END AS tr, CASE WHEN g.test_mode = 1 THEN 1 "
                          "ELSE 0 END AS tg %s%s) x GROUP BY d, cat ORDER BY d DESC, cat" % (_cat_sql(), TEST_R, _from_purchases(gok), w), [shift] + args)
            # ★ ревизия 51 Н-2: позиции — без тестовых возвращённых подарков (не выручка); отбор TOP и порядок — по сумме БЕЗ служебных при
            #   svc=sep (со служебными при svc=in), «учёток» — без служебных, служебные — своими столбцами
            cw = list(cond) + ["p.amount > 0", "NOT (%s)" % TEST_R]
            key = "SUM(p.amount)" if svc == "in" else "SUM(CASE WHEN %s = 'service' THEN 0 ELSE p.amount END)" % _cat_sql()
            codes = g.rows("SELECT TOP (%d) p.item_code, COUNT(*) AS n, SUM(p.amount) AS s, COUNT(DISTINCT CASE WHEN %s <> 'service' THEN p.user_id END) "
                           "AS users, COUNT(DISTINCT CASE WHEN %s = 'service' THEN p.user_id END) AS svc_users, SUM(CASE WHEN %s = 'service' THEN 1 ELSE 0 END) "
                           "AS svc_n, SUM(CASE WHEN %s = 'service' THEN p.amount ELSE 0 END) AS svc_s %s WHERE %s GROUP BY p.item_code ORDER BY %s DESC, "
                           "p.item_code" % (CODES_N, _cat_sql(), _cat_sql(), _cat_sql(), _cat_sql(), _from_purchases(gok), " AND ".join(cw), key), args)
            ncodes = int(g.one("SELECT COUNT(DISTINCT p.item_code) AS n %s WHERE %s" % (_from_purchases(gok), " AND ".join(cw)), args)["n"])
            ids = {int(r["id"]) for r in g.rows("SELECT p.id %s WHERE %s" % (_from_purchases(gok), " AND ".join(cw + ["g.order_id IS NULL"])), args)}
    except db.DbError as ex:
        out["errors"].append("журнал покупок gp7 не прочитан: %s" % ex)
        return out
    per = {}
    for r in days:
        d = per.setdefault(r["d"], {"day": r["d"], "cats": {c: dict.fromkeys(DAY_KEYS, 0) for c in WHO}})
        x = {"n": int(r["n"] or 0), "gross": int(r["gross"] or 0), "refunds": int(r["rn"] or 0), "refunded": int(r["rs"] or 0),
             "gifts": int(r["gifts"] or 0), "test_gifts": int(r["tgn"] or 0)}
        x["sum"] = x["gross"] - x["refunded"]
        d["cats"][r["cat"]] = x
    for d in per.values():
        d["total"] = {k: sum(d["cats"][c][k] for c in WHO if _in_total(c, svc)) for k in DAY_KEYS}
    out["days"] = sorted(per.values(), key=lambda x: x["day"], reverse=True)
    for r in codes:
        r.update(pos=position(r["item_code"]), n=int(r["n"]), s=int(r["s"] or 0), svc_n=int(r["svc_n"] or 0), svc_s=int(r["svc_s"] or 0),
                 users=int(r["users"] or 0), svc_users=int(r["svc_users"] or 0))
        r["total_n"] = r["n"] - (0 if svc == "in" else r["svc_n"])
        r["total_s"] = r["s"] - (0 if svc == "in" else r["svc_s"])
    out.update(codes=codes, codes_all=ncodes, codes_capped=ncodes > len(codes), period={"from": f, "to": t}, shift_min=shift)
    _pm, perr = premium_map()
    if perr:
        out["errors"].append(perr)
    _stock_sales(out, f, t, who, ids)
    return out


def _stock_sales(out, f, t, who, gp7_ids):
    """Сток за тот же период (местное Edate): CashUse по дням, Sale* по дням и позициям; сверка номеров заказов покупок gp7 (без подарков) с
    таблицей, которую пишет процедура вида позиции: предметы — CashUse (UPCashitemBuy), причёски — SaleHair (UPHairChange / UPWebMallHair) —
    ревизия 51 Н-1. «Только gp7» дополнительно проверяется по ящику Joy1.ItemPostbox (лежит ли заказ там сейчас). Каждая таблица стока —
    отдельно: нет таблицы — строка в errors, остальные считаются."""
    cond_d = "Edate >= CONVERT(datetime2, ?, 112) AND Edate < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))"
    wc = {"player": "Userindex > %d" % SERVICE_MAX, "service": "Userindex <= %d" % SERVICE_MAX, "nolink": "1 = 0"}.get(who)
    sd, sc, orders, hair = {}, [], None, None
    try:
        with db.GameReader("asdastoryop") as op:
            if not who:                                # у CashUse нет учётки: по категории его не отобрать
                try:
                    for r in op.rows("SELECT CONVERT(char(8), Edate, 112) AS d, COUNT(*) AS n, SUM(CAST(Realcash AS BIGINT)) AS s FROM CashUse "
                                     "WHERE %s GROUP BY CONVERT(char(8), Edate, 112)" % cond_d, (f, t)):
                        sd[r["d"]] = {"day": r["d"], "cash_n": int(r["n"]), "cash_sum": int(r["s"] or 0)}
                    orders = {int(r["Orderidx"]) for r in op.rows("SELECT DISTINCT Orderidx FROM CashUse WHERE %s" % cond_d, (f, t))}
                except db.DbError as ex:
                    out["errors"].append("продажи стока не прочитаны: CashUse: %s" % ex)
            w = cond_d + (" AND " + wc if wc else "")
            for tbl, col in STOCK:
                try:
                    for r in op.rows("SELECT CONVERT(char(8), Edate, 112) AS d, COUNT(*) AS n, SUM(CAST(%s AS BIGINT)) AS s, SUM(CASE WHEN "
                                     "Userindex <= %d THEN 1 ELSE 0 END) AS svc_n FROM %s WHERE %s GROUP BY CONVERT(char(8), Edate, 112)"
                                     % (col, SERVICE_MAX, tbl, w), (f, t)):
                        d = sd.setdefault(r["d"], {"day": r["d"], "cash_n": None, "cash_sum": None})
                        d[tbl] = {"n": int(r["n"]), "sum": int(r["s"] or 0), "svc_n": int(r["svc_n"] or 0)}
                    for r in op.rows("SELECT TOP (%d) Code, COUNT(*) AS n, SUM(CAST(%s AS BIGINT)) AS s, SUM(CASE WHEN Userindex <= %d THEN 1 "
                                     "ELSE 0 END) AS svc_n FROM %s WHERE %s GROUP BY Code ORDER BY COUNT(*) DESC, Code"
                                     % (CODES_N, col, SERVICE_MAX, tbl, w), (f, t)):
                        it = refdata.item(int(r["Code"])) if tbl != "SaleHair" and int(r["Code"]) > 0 else {"name": ""}
                        sc.append({"table": tbl, "code": int(r["Code"]), "name": it["name"], "n": int(r["n"]), "sum": int(r["s"] or 0),
                                   "svc_n": int(r["svc_n"] or 0)})
                except db.DbError as ex:
                    out["errors"].append("продажи стока не прочитаны: %s: %s" % (tbl, ex))
            if not who:
                try:
                    hair = {int(r["Orderidx"]) for r in op.rows("SELECT DISTINCT Orderidx FROM SaleHair WHERE %s" % cond_d, (f, t))}
                except db.DbError:
                    hair = None                        # ошибка таблицы уже записана выше
    except db.DbError as ex:
        out["errors"].append("продажи стока не прочитаны: %s" % ex)
        return
    out["stock_days"] = sorted(sd.values(), key=lambda x: x["day"], reverse=True)
    out["stock_codes"] = sc
    if orders is not None:
        hs = hair or set()
        only = sorted(gp7_ids - orders - hs)
        out["cross"] = {"gp7_orders": len(gp7_ids), "stock_orders": len(orders), "hair_orders": len(hs) if hair is not None else None,
                        "both": len(gp7_ids & orders), "hair_both": len(gp7_ids & hs), "gp7_only": len(only),
                        "stock_only": len(orders - gp7_ids), "hair_only": len(hs - gp7_ids), "in_postbox": None}
        if only:
            try:
                with db.GameReader("joy1") as j:
                    n = 0
                    for i in range(0, len(only), 1000):
                        part = only[i:i + 1000]
                        n += int(j.one("SELECT COUNT(DISTINCT Orderidx) AS n FROM ItemPostbox WHERE %s" % _in("Orderidx", part, []), part)["n"])
                out["cross"]["in_postbox"] = n
            except db.DbError as ex:
                out["errors"].append("ящик ItemPostbox не прочитан: %s" % ex)


# ---------------------------------------------------------------- оплачено, но не выдано (22.11.2026)
# Разбор Reports/admin_center/research_gp7_orphan_orders_20261121.md; отчёт impl_a6_econ_20261121.md §«gp7: оплачено, не выдано».
# Заказ gp7 «оплачен, не выдан» — покупка (success = 1, amount > 0, не подарок), у которой нет строки стока той процедуры, что пишет
# выдачу (предметы — CashUse, причёски — SaleHair; ревизия 51 Н-1), и которой нет в ящике Joy1.ItemPostbox. Свежие (моложе minutes)
# не считаются: GameServer ещё может класть заказ в ящик. CashUse.Orderidx = номер строки журнала gp7 появился только с первым
# сведённым заказом (на живой — 15.10, №10113): у более ранних заказов связи по номеру нет — «сверка по номеру неприменима».
# Причина — ТОЛЬКО по журналам (чтение белым списком domains/logs.py, источники gslog и gp7):
#   A — GameServer отбросил ответ из-за кода: в журнале шлюза ответ status 1 подтипа 1 с кодом < 20551 (sub_532A90, GameServer.c:95213)
#       или отказ undeliverable-*, либо в Buy_<день>.txt GameServer строка «GP7's Response ItemCode is Invalid» с тем же кодом рядом
#       по времени;
#   B — ответ не дошёл: отметка шлюза PURCHASE_UNCONFIRMED с этим номером (server.js с 22.11) или после строки ответа SEND 0x0051 тот
#       же сокет закрылся / дал ошибку не позже чем через BROKEN_MS;
#   иначе — «не установлена» (с пояснением, что прочитано).
UNDELIVERED_MIN = 10               # заказ моложе N минут ещё не сверяется
UNDELIVERED_ROWS = 500             # строк заказов в ответе (новые сверху; итоги — по всем)
BROKEN_MS = 2000                   # обрыв сокета не позже стольких мс после ответа — причина B
MATCH_BEFORE_S, MATCH_AFTER_S = 2, 7   # строка журнала ответа / GameServer — в окне [время заказа − 2 с; + 7 с] (sqlcmd до 5 с)
DELIVERABLE_MIN = 20551            # GameServer выдаёт по ответу подтипа 1 только код >= 20551 (sub_532A90)
GS_BUY_KIND = "Log_MGamePremium"   # подпапка журнала покупок GameServer (Buy_ГГГГММДД.txt)
REASONS = ("A", "B", "unknown", "na")   # код ответа / обрыв / не установлена / сверка по номеру неприменима
_scan_cache = {}                   # (источник, копия, вид, файл) → {st: (размер, время), lines, truncated, at} — см. _log_lines
_TS = r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})"
_RX_SEND = re.compile(r"^" + _TS + r" SEND (\S+) bytes=\d+ command=0x0051 account=\"([^\"]*)\" source=(\S+) status=(\d+) (?:order=(\d+) )?"
                      r"subtype=(\d+) .*? itemCode=(\d+) .*? price=(\d+) ")
_RX_DROP = re.compile(r"^" + _TS + r" (SOCKET_ERROR|CLOSE) (\S+)(?: (.*))?$")
_RX_UNCONF = re.compile(r"^" + _TS + r" PURCHASE_UNCONFIRMED (\S+) order=(\d+) .*?afterMs=(\d+) reason=(\S+)")
_RX_GSBAD = re.compile(r"^\s*(\d{1,2}) Mon (\d{1,2}) Day (\d{1,2}) hou (\d{1,2}) min (\d{1,2}) sec :\s*GP7's Response ItemCode is Invalid\s+(.*?)\s+"
                       r"ItemCode\s+(\d+)\s*$")


MISSING = "missing"                # _log_lines: файла журнала нет (не путать с ошибкой чтения — None)


class _ScanCtx:
    """Разбор журналов одного запроса: errors — строки ошибок ответа; user — чей бюджет чтения журналов (logs.charge, ревизия 53 Н-2);
    truncated — файлы, которые logs.scan прочитал не целиком (больше logs.SCAN_FILE_MAX, ревизия 53 Н-1)."""

    def __init__(self, errors, user):
        self.errors, self.user, self.truncated = errors, user or "money.undelivered", set()


SCAN_TTL_S = 120                   # ★ ревизия 53 Н-2: растущий (сегодняшний) журнал не перечитывается чаще раза в 2 мин


def _log_lines(key, proc, name, kind, needles, ctx):
    """Строки журнала (logs.stat → logs.scan): список строк | MISSING (файла нет) | None (ошибка — в ctx.errors). Кэш на процесс: тот же
    размер:время — без чтения; изменился, но прочитан меньше SCAN_TTL_S назад — тоже из кэша (сегодняшний журнал шлюза растёт каждую
    секунду). Флаг logs.scan «truncated» — имя файла в ctx.truncated."""
    import time
    from domains import logs
    k = (key, proc, kind, name)
    try:
        st = logs.stat(key, proc, name, kind)
        if st is None:
            return MISSING
        c = _scan_cache.get(k)
        if c and (c["st"] == tuple(st) or time.monotonic() - c["at"] < SCAN_TTL_S):
            if c["truncated"]:
                ctx.truncated.add(name)
            return c["lines"]
        got = logs.scan(key, proc, name, kind=kind, needles=needles, show_ip=True, user=ctx.user, size=st[0])
    except OpRefused as ex:                    # Throttled — его подкласс
        ctx.errors.append("журнал стойки %s не прочитан: %s" % (name, ex))
        return None
    if len(_scan_cache) > 64:
        _scan_cache.clear()
    _scan_cache[k] = {"st": tuple(st), "lines": got["lines"], "truncated": bool(got.get("truncated")), "at": time.monotonic()}
    if got.get("truncated"):
        ctx.truncated.add(name)
    return got["lines"]


def _ts(s):
    """«ГГГГ-ММ-ДД чч:мм:сс.ммм» журнала шлюза → datetime."""
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")


def _gs_invalid(days, ctx):
    """Строки «GP7's Response ItemCode is Invalid» журналов Buy_<день>.txt всех GameServer за дни → [(время, копия, файл, код)]."""
    from domains import logs
    out = []
    for proc in logs.procs_of("gslog"):
        for d in sorted(days):
            name = "Buy_%s.txt" % d.strftime("%Y%m%d")
            lines = _log_lines("gslog", proc, name, GS_BUY_KIND, ("ItemCode is Invalid",), ctx)
            if lines in (None, MISSING):
                continue
            for ln in lines:
                m = _RX_GSBAD.match(ln)
                if not m:
                    continue
                mon, day, hh, mi, ss = (int(x) for x in m.groups()[:5])
                try:
                    t = datetime.datetime(d.year, mon, day, hh, mi, ss)
                except ValueError:
                    continue
                out.append((t, proc, name, int(m.group(7))))
    return out


def _gw_events(days, ctx, notes):
    """Журнал шлюза gp7-<день>.log за дни → ({день: файл}, ответы 0x0051, обрывы сокетов, отметки PURCHASE_UNCONFIRMED)."""
    files, sends, drops, unconf = {}, [], [], []
    for d in sorted(days):
        f = ("gp7-%s.log" % d.strftime("%Y%m%d"),)
        lines = _log_lines("gp7", "gp7-server", f[0], None, ("command=0x0051", "SOCKET_ERROR ", " CLOSE ", "PURCHASE_UNCONFIRMED "), ctx)
        if lines == MISSING:
            notes[d] = "журнала шлюза за %s нет" % d.strftime("%d.%m.%Y")
            continue
        if lines is None:
            notes[d] = "файл журнала шлюза %s не прочитан" % f[0]
            continue
        files[d] = f[0]
        for ln in lines:
            m = _RX_SEND.match(ln)
            if m:
                sends.append({"t": _ts(m.group(1)), "remote": m.group(2), "account": m.group(3).lower(), "source": m.group(4),
                              "status": int(m.group(5)), "order": int(m.group(6)) if m.group(6) else None, "subtype": int(m.group(7)),
                              "code": int(m.group(8)), "price": int(m.group(9)), "file": f[0], "used": False})
                continue
            m = _RX_UNCONF.match(ln)
            if m:
                unconf.append({"t": _ts(m.group(1)), "order": int(m.group(3)), "ms": int(m.group(4)), "reason": m.group(5), "file": f[0]})
                continue
            m = _RX_DROP.match(ln)
            if m:
                drops.append({"t": _ts(m.group(1)), "what": m.group(2), "remote": m.group(3), "msg": (m.group(4) or "")[:80]})
    return files, sends, drops, unconf


def _hms(t):
    """Время строки для пояснения (чч:мм:сс.ммм)."""
    return t.strftime("%H:%M:%S.") + "%03d" % (t.microsecond // 1000)


def _reasons(rows, ctx):
    """Причина каждого сверяемого заказа (A / B / unknown) и пояснение — по журналам GameServer и шлюза (см. блок выше)."""
    win_lo, win_hi = datetime.timedelta(seconds=MATCH_BEFORE_S), datetime.timedelta(seconds=MATCH_AFTER_S)

    def _days_of(rs):
        out = set()
        for r in rs:
            out.update({r["created_local"].date(), (r["created_local"] + win_hi).date()})
        return out
    # шаг 1 — маленькие журналы GameServer (Buy_<день>.txt): «ItemCode is Invalid» с кодом заказа рядом по времени → A
    bad = _gs_invalid(_days_of(rows), ctx)
    rest = []
    for r in rows:
        t = r["created_local"]
        gsb = [b for b in bad if t - win_lo <= b[0] <= t + win_hi and b[3] == r["item_code"]]
        if gsb:
            b = gsb[0]
            r["reason"], r["reason_why"] = "A", "журнал GameServer %s %s в %s: «ItemCode is Invalid», код %d" % (b[1], b[2], b[0].strftime("%H:%M:%S"), b[3])
        else:
            rest.append(r)
    if not rest:
        return
    # шаг 2 — журнал шлюза (~7 МБ в сутки) только за дни нерешённых заказов (бюджет чтения журналов logs.charge)
    rows = rest
    notes = {}
    files, sends, drops, unconf = _gw_events(_days_of(rows), ctx, notes)
    by_order = {}
    for s in sends:
        if s["order"]:
            by_order.setdefault(s["order"], s)
    for r in sorted(rows, key=lambda x: x["id"]):
        t, acc = r["created_local"], (r["site_login"] or "").lower()
        s = by_order.get(r["id"])
        if s is None:
            near = [x for x in sends if not x["used"] and x["order"] is None and x["status"] == 1 and x["account"] == acc
                    and x["price"] == r["amount"] and t - win_lo <= x["t"] <= t + win_hi]
            s = min(near, key=lambda x: abs((x["t"] - t).total_seconds())) if near else None
        if s is not None:
            s["used"] = True
        reason, why = "unknown", None
        mark = [u for u in unconf if u["order"] == r["id"]]
        code = s["code"] if s else r["item_code"]
        gsb = [b for b in bad if t - win_lo <= b[0] <= t + win_hi and b[3] == code]
        if mark:
            u = mark[0]
            reason, why = "B", "отметка шлюза PURCHASE_UNCONFIRMED в %s %s (%s, через %d мс после ответа)" % (u["file"], _hms(u["t"]), u["reason"], u["ms"])
        elif s and s["source"].startswith("undeliverable"):
            reason, why = "A", "ответ шлюза в %s %s: отказ %s" % (s["file"], _hms(s["t"]), s["source"])
        elif s and s["subtype"] == 1 and s["code"] < DELIVERABLE_MIN:
            reason, why = "A", "ответ шлюза в %s %s: код %d < %d — GameServer такой код не выдаёт (sub_532A90)" % (
                s["file"], _hms(s["t"]), s["code"], DELIVERABLE_MIN)
        elif gsb:
            b = gsb[0]
            reason, why = "A", "журнал GameServer %s %s в %s: «ItemCode is Invalid», код %d" % (b[1], b[2], b[0].strftime("%H:%M:%S"), b[3])
        elif s:
            dr = [x for x in drops if x["remote"] == s["remote"] and datetime.timedelta(0) <= x["t"] - s["t"] <= datetime.timedelta(milliseconds=BROKEN_MS)]
            if dr:
                x = min(dr, key=lambda y: y["t"])
                ms = int((x["t"] - s["t"]).total_seconds() * 1000)
                reason, why = "B", "сокет GameServer закрыт через %d мс после ответа шлюза в %s %s (%s)" % (
                    ms, s["file"], _hms(s["t"]), (x["what"] + " " + x["msg"]).strip())
            else:
                why = "ответ шлюза найден в %s %s: обрыва сокета и отказа GameServer по журналам нет" % (s["file"], _hms(s["t"]))
        else:
            d = t.date()
            why = notes.get(d) or ("строка ответа шлюза не найдена в %s" % files[d] if d in files else "журнал шлюза за %s не прочитан"
                                                                                                         % d.strftime("%d.%m.%Y"))
        # ★ ревизия 53 Н-1: журнал дня прочитан не целиком (больше logs.SCAN_FILE_MAX) — «не установлена» с этой пометкой, а не молча
        cut = [n for n in (files.get(t.date()), "Buy_%s.txt" % t.strftime("%Y%m%d")) if n and n in ctx.truncated]
        if reason == "unknown" and cut:
            why = "журнал прочитан не целиком (%s больше 16 МБ): %s" % (", ".join(cut), why)
        r["reason"], r["reason_why"] = reason, why


def _undelivered_core(q, with_logs):
    """Общая часть «Оплачено, не выдано» (раздел и сводка): → dict с rows (новые сверху, не больше UNDELIVERED_ROWS), totals, cutoff."""
    f, t = _days(q)
    svc = _svc(q)
    who = _choice(q.get("who"), WHO, "учётки — player (игроки), service (служебные ≤ 5000) или nolink (сайт без игровой)")
    minutes = _int(q.get("minutes") or UNDELIVERED_MIN, "возраст сверяемого заказа — целое число минут от 1 до 10080", 1, 10080)
    out = {"rows": [], "total": 0, "capped": False, "totals": None, "cutoff": None, "in_postbox": 0, "minutes": minutes, "errors": [],
           "svc": svc, "logs": with_logs, "rows_max": UNDELIVERED_ROWS}
    try:
        with db.GameReader("asdastorylogin") as g:
            shift = _shift(g)
            gok = _gift_table(g, out["errors"])
            cond, args = ["p.success = 1", "p.amount > 0", "g.order_id IS NULL", "p.created_at < DATEADD(minute, ?, SYSUTCDATETIME())"], [-minutes]
            if who:
                cond.append(_who_cond(who))
            _utc_bounds(cond, args, "p.created_at", f, t, shift)
            cand = g.rows("SELECT p.id, p.item_code, p.amount, p.created_at, DATEADD(minute, ?, p.created_at) AS created_local, u.username AS site_login, "
                          "m.Userindex, m.Us_id, %s AS cat %s WHERE %s ORDER BY p.id" % (_cat_sql(), _from_purchases(gok), " AND ".join(cond)),
                          [shift] + args)
            # ★ ревизия 53 С-1: граница «первый номер gp7 в CashUse» — по ВСЕМ покупкам (без фильтров учётки и дат): фильтр не должен
            #   переводить сверяемые заказы периода в «неприменима»
            all_ids = [int(r["id"]) for r in g.rows("SELECT p.id FROM dbo.GP7PurchaseLog p WHERE p.success = 1 AND p.amount > 0 ORDER BY p.id")]
    except db.DbError as ex:
        out["errors"].append("журнал покупок gp7 не прочитан: %s" % ex)
        return out
    try:
        with db.GameReader("asdastoryop") as op:
            stock = {int(r["Orderidx"]) for r in op.rows("SELECT DISTINCT Orderidx FROM CashUse WHERE Orderidx > 0")}
            stock |= {int(r["Orderidx"]) for r in op.rows("SELECT DISTINCT Orderidx FROM SaleHair WHERE Orderidx > 0")}
    except db.DbError as ex:
        out["errors"].append("продажи стока не прочитаны: %s" % ex)
        return out
    cutoff = next((i for i in all_ids if i in stock), None)            # ★ ревизия 53 С-1: первый сведённый номер без фильтров
    cutoff_local = None
    if cutoff is not None:
        try:
            with db.GameReader("asdastorylogin") as g:
                cutoff_local = g.one("SELECT DATEADD(minute, ?, created_at) AS t FROM dbo.GP7PurchaseLog WHERE id = ?", (shift, cutoff))["t"]
        except db.DbError as ex:
            out["errors"].append("журнал покупок gp7 не прочитан: %s" % ex)
    orphans = [r for r in cand if int(r["id"]) not in stock]
    if orphans:
        try:
            with db.GameReader("joy1") as j:
                ids, box = [int(r["id"]) for r in orphans], set()
                for i in range(0, len(ids), 1000):
                    part = ids[i:i + 1000]
                    box |= {int(x["Orderidx"]) for x in j.rows("SELECT DISTINCT Orderidx FROM ItemPostbox WHERE %s" % _in("Orderidx", part, []), part)}
        except db.DbError as ex:
            out["errors"].append("ящик ItemPostbox не прочитан: %s" % ex)
            return out
        out["in_postbox"] = sum(1 for r in orphans if int(r["id"]) in box)
        orphans = [r for r in orphans if int(r["id"]) not in box]
    cats = {c: {"n": 0, "sum": 0, "na_n": 0, "na_sum": 0} for c in WHO}
    for r in orphans:
        r["applicable"] = cutoff is not None and int(r["id"]) >= cutoff
        c = cats[r["cat"]]
        k = "" if r["applicable"] else "na_"
        c[k + "n"] += 1
        c[k + "sum"] += int(r["amount"])
    tot = {k: sum(cats[c][k] for c in WHO if _in_total(c, svc)) for k in ("n", "sum", "na_n", "na_sum")}
    rows = sorted(orphans, key=lambda x: -int(x["id"]))[:UNDELIVERED_ROWS]
    for r in rows:
        r["Us_id"] = db.fix_text(r["Us_id"])
        r["reason"], r["reason_why"] = ("na", None) if not r["applicable"] else (None, None)
        if not r["applicable"]:
            r["reason_why"] = ("сверка по номеру неприменима: заказ раньше первого номера gp7 в CashUse (№%d)" % cutoff if cutoff
                               else "сверка по номеру неприменима: в CashUse нет ни одного номера заказа gp7")
    out.update(rows=rows, total=len(orphans), capped=len(orphans) > len(rows), shift_min=shift,
               totals={"cats": cats, "total": tot, "svc": svc, "service_in_total": svc == "in"},
               cutoff={"id": cutoff, "local": cutoff_local} if cutoff else None)
    return out


def undelivered(q, user=None):
    """«Оплачено, не выдано» (22.11.2026): заказы gp7 без строки стока своей процедуры и без ящика, с причиной по журналам (?logs=0 — без
    журналов). Фильтры: who, from / to (ГГГГММДД), minutes (свежие не сверяются), svc (служебные в общем итоге). user — логин запроса: бюджет
    чтения журналов logs.charge считается на него (ревизия 53 Н-2). Только чтение. → dict."""
    with_logs = _choice(q.get("logs"), ("0", "1"), "разбор причин по журналам — 0 или 1") != "0"
    out = _undelivered_core(q, with_logs)
    if with_logs and out["rows"]:
        todo = [r for r in out["rows"] if r["applicable"]]
        if todo:
            _reasons(todo, _ScanCtx(out["errors"], user))
    out["by_reason"] = {k: sum(1 for r in out["rows"] if r["reason"] == k) for k in REASONS}
    for r in out["rows"]:
        r["pos"] = position(r["item_code"])
    return out


# ---------------------------------------------------------------- учётка сайта ↔ игровая

def accounts(q):
    """Связь учётки сайта gp7 ([user]) с игровой (Us_member по логину): баланс, покупки, служебная ли. Страницами; фильтры учётка, who.
    Плюс число игровых учёток без строки сайта (её шлюз заводит при первом обращении). → dict."""
    page, size = _page(q)
    who = _choice(q.get("who"), WHO, "учётки — player (игроки), service (служебные ≤ 5000) или nolink (сайт без игровой)")
    acc = resolve_account(q.get("account"))
    out = {"rows": [], "total": 0, "page": 1, "pages": 1, "size": size, "game_without_site": None, "errors": []}
    cond, args = [], []
    if acc is not None:
        cond.append(_in("u.id", acc["site"], args))
    if who:
        cond.append(_who_cond(who))
    w = (" WHERE " + " AND ".join(cond)) if cond else ""
    try:
        with db.GameReader("asdastorylogin") as g:
            # ★ ревизия 51 Н-3, М-4: «списано» и «возвращено» (строки возврата + тестовые R) — как в сводке; итого = разность
            gj = "LEFT JOIN dbo.GP7GiftLog g ON g.order_id = p.id" if _gift_table(g, out["errors"]) else "CROSS JOIN %s g" % GIFT_NULL
            frm = ("FROM dbo.[user] u OUTER APPLY (SELECT TOP (1) x.Userindex, x.Us_id, x.us_block FROM %s.dbo.Us_member x WHERE x.Us_id = u.username "
                   "COLLATE Arabic_CI_AS ORDER BY x.Userindex) m LEFT JOIN dbo.GP7Balance b ON b.user_id = u.id OUTER APPLY (SELECT COUNT(*) AS n, "
                   "SUM(CASE WHEN p.success = 1 AND p.amount > 0 THEN p.amount ELSE 0 END) AS gross, SUM(CASE WHEN p.success = 1 AND p.amount < 0 "
                   "THEN -p.amount WHEN %s THEN p.amount ELSE 0 END) AS refunded, MAX(p.created_at) AS last_utc FROM dbo.GP7PurchaseLog p %s "
                   "WHERE p.user_id = u.id) pa" % (_op_db(), TEST_R, gj))
            total = int(g.one("SELECT COUNT(*) AS n %s%s" % (frm, w), args)["n"])
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages)
            rows = g.rows("SELECT u.id, u.username, u.role, m.Userindex, m.Us_id, m.us_block, b.balance, b.present, b.updated_at, pa.n AS purchases, "
                          "pa.gross, pa.refunded, DATEADD(minute, ?, pa.last_utc) AS last %s%s ORDER BY pa.gross DESC, u.id OFFSET ? ROWS FETCH NEXT ? "
                          "ROWS ONLY"
                          % (frm, w), [_shift(g)] + args + [(page - 1) * size, size])
    except db.DbError as ex:
        out["errors"].append("учётки сайта gp7 не прочитаны: %s" % ex)
        return out
    for r in rows:
        r["Us_id"] = db.fix_text(r["Us_id"])
        r["cat"] = "nolink" if r["Userindex"] is None else ("service" if int(r["Userindex"]) <= SERVICE_MAX else "player")
        r["gross"], r["refunded"] = int(r["gross"] or 0), int(r["refunded"] or 0)
        r["spent"] = r["gross"] - r["refunded"]
    try:
        with db.GameReader("asdastoryop") as op:
            out["game_without_site"] = int(op.one("SELECT COUNT(*) AS n FROM Us_member m WHERE NOT EXISTS (SELECT 1 FROM %s.dbo.[user] u "
                                                  "WHERE u.username = m.Us_id COLLATE SQL_Latin1_General_CP1_CI_AS)" % _db_name(LOGIN_DB))["n"])
    except db.DbError as ex:
        out["errors"].append("учётки игры без строки сайта не посчитаны: %s" % ex)
    out.update(rows=rows, total=total, page=page, pages=pages)
    return out


# ---------------------------------------------------------------- сводка

def summary(q):
    """Итоги: покупки gp7 по категориям учёток за всё время (служебные — отдельной строкой, в общий итог по svc), подарки по состояниям
    и висящие, балансы, сток рядом, testFixedBalance шлюза. Ошибка части — в errors."""
    svc = _svc(q)
    minutes = _int(q.get("minutes") or HOLD_MIN, "возраст висящего подарка — целое число минут от 1 до 10080", 1, 10080)
    out = {"svc": svc, "purchases": None, "first": None, "last": None, "gifts": [], "hanging": None, "balances": None, "stock": [],
           "test_fixed_balance": None, "errors": [], "minutes": minutes, "service_max": SERVICE_MAX}
    tfb, err = test_fixed_balance()
    out["test_fixed_balance"] = tfb
    if err:
        out["errors"].append(err)
    try:
        with db.GameReader("asdastorylogin") as g:
            gok = _gift_table(g, out["errors"])
            agg = g.rows("SELECT %s AS cat, %s %s GROUP BY %s" % (_cat_sql(), _money_sql(), _from_purchases(gok), _cat_sql()))
            out["purchases"] = _totals(agg, svc)
            shift = _shift(g)                         # ★ ревизия 51 Н-4: времена раздела — по часам сервера (местные)
            fl = g.one("SELECT DATEADD(minute, ?, MIN(created_at)) AS a, DATEADD(minute, ?, MAX(created_at)) AS b, COUNT(DISTINCT user_id) AS users, "
                       "COUNT(DISTINCT item_code) AS codes "
                       "FROM dbo.GP7PurchaseLog", (shift, shift))
            out.update(first=fl["a"], last=fl["b"], users=fl["users"], codes=fl["codes"], shift_min=shift)
    except db.DbError as ex:
        out["errors"].append("журнал покупок gp7 не прочитан: %s" % ex)
    try:
        with db.GameReader("asdastorylogin") as g:
            out["gifts"] = g.rows("SELECT state, test_mode, COUNT(*) AS n, SUM(amount) AS s FROM dbo.GP7GiftLog GROUP BY state, test_mode "
                                  "ORDER BY state, test_mode")
            out["hanging"] = int(g.one("SELECT COUNT(*) AS n FROM dbo.GP7GiftLog WHERE state = 'H' AND created_at < DATEADD(minute, ?, "
                                       "SYSUTCDATETIME())", (-minutes,))["n"])
    except db.DbError as ex:
        out["errors"].append("подарки gp7 не прочитаны: %s" % ex)
    try:
        with db.GameReader("asdastorylogin") as g:
            bal = g.rows("SELECT CASE WHEN m.Userindex IS NULL THEN 'nolink' WHEN m.Userindex <= %d THEN 'service' ELSE 'player' END AS cat, "
                         "COUNT(*) AS n, SUM(CASE WHEN b.balance > 0 THEN 1 ELSE 0 END) AS pos, SUM(b.balance) AS s, MAX(b.balance) AS mx "
                         "FROM dbo.GP7Balance b LEFT JOIN dbo.[user] u ON u.id = b.user_id OUTER APPLY (SELECT TOP (1) x.Userindex FROM %s.dbo.Us_member x "
                         "WHERE x.Us_id = u.username COLLATE Arabic_CI_AS ORDER BY x.Userindex) m GROUP BY CASE WHEN m.Userindex IS NULL THEN 'nolink' "
                         "WHEN m.Userindex <= %d THEN 'service' ELSE 'player' END" % (SERVICE_MAX, _op_db(), SERVICE_MAX))
            cats = {c: {"n": 0, "positive": 0, "sum": 0, "max": 0} for c in WHO}
            for r in bal:
                cats[r["cat"]] = {"n": int(r["n"]), "positive": int(r["pos"] or 0), "sum": int(r["s"] or 0), "max": int(r["mx"] or 0)}
            out["balances"] = {"cats": cats, "total": {k: (sum(cats[c][k] for c in WHO if _in_total(c, svc)) if k != "max" else
                                                       max(cats[c][k] for c in WHO if _in_total(c, svc))) for k in ("n", "positive", "sum", "max")}}
    except db.DbError as ex:
        out["errors"].append("балансы gp7 не прочитаны: %s" % ex)
    try:
        with db.GameReader("asdastoryop") as op:
            for tbl, col in (("CashUse", "Realcash"),) + STOCK:
                svc_sql = "CAST(NULL AS INT)" if tbl == "CashUse" else "SUM(CASE WHEN Userindex <= %d THEN 1 ELSE 0 END)" % SERVICE_MAX
                try:
                    r = op.one("SELECT COUNT(*) AS n, SUM(CAST(%s AS BIGINT)) AS s, MIN(Edate) AS a, MAX(Edate) AS b, %s AS svc_n FROM %s"
                               % (col, svc_sql, tbl))
                except db.DbError as ex:
                    out["errors"].append("продажи стока не прочитаны: %s: %s" % (tbl, ex))
                    continue
                out["stock"].append({"table": tbl, "n": int(r["n"]), "sum": int(r["s"] or 0), "first": r["a"], "last": r["b"],
                                     "svc_n": None if r["svc_n"] is None else int(r["svc_n"])})
    except db.DbError as ex:
        out["errors"].append("продажи стока не прочитаны: %s" % ex)
    # ★ 22.11.2026: «списано, но не выдано» — отдельной строкой итогов (не прячется в выручке), служебные отдельно; без разбора журналов
    u = _undelivered_core({"svc": svc}, False)
    out["undelivered"] = {"totals": u["totals"], "cutoff": u["cutoff"], "in_postbox": u["in_postbox"], "minutes": u["minutes"]}
    out["errors"].extend(u["errors"])
    return out
