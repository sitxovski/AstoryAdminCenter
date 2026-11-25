# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_money_a6.py — самотест шага А6.2 «Деньги: чтение» (21.11.2026; domains/money.py, /api/money/*, web/money.js, консоль money).

offline(check)  — проверка ввода и отказы (даты ГГГГММДД, страницы, вид, категория, тест, служебные, состояние, минуты, окно, код, длина
                  логина, период продаж), тексты отказов без «; », право money.view (owner, admin), маршруты /api/money/*, переводы EN
                  (shadowed_translations = 0), сверка подарков — модуль gift_reconcile.py шлюза (тот же файл, его hint), веб без innerHTML
                  и с EN всех подписей, консоль (неизвестный ключ, ключ без значения, неизвестное действие — отказ без базы), выкладка
                  кладёт ext/gift_reconcile.py, в тексте SQL модуля нет столбца password.
sandbox(check, ldb) — СВОИ базы LocalDB: AsdaStoryLogin — настоящий установщик шлюза install_gp7_balance.sql + [user] как на живой;
                  Joy1 / JoyLog1 — Charinfo, Item, EventGainItem по снимку живых схем (как стенд reconcile_stand.py); AsdaStoryOp —
                  Us_member и стоковые CashUse / SalePremium / SaleFunctional / SaleHair. Синтетика: игроки, служебная ≤ 5000, учётка сайта
                  без игровой, логин из цифр, регистр логина, покупки, отказ, подарки H / C / R, возврат, test_mode, свежая и висящие
                  заморозки, сток-зеркало и строка «только сток». Итоги = COUNT / SUM по таблице, служебные отдельно и в итоге (svc=in),
                  каждый фильтр, страницы, висящие — подсказки СОВПАДАЮТ с консольной сверкой gift_reconcile (её SQL на тех же базах),
                  продажи по дням и позициям, сверка заказов со стоком, связь учёток, маршруты API (EN), нет таблицы — строка ошибки.
                  Все запросы раздела перехвачены: только чтение, без password, без русских букв.
live(check)     — только чтение живой dev логином asda_admin: права SELECT (password — нет), итоги = COUNT(*) / SUM по живой, журнал,
                  подарки и висящие = COUNT, сток = COUNT, продажи за 30 суток = COUNT, связь учёток = COUNT [user]; служба на сервере
                  (SSH, stdin) — сверка из ext/, итоги те же; /api/money/summary без входа — 401.
Ничего не пишет ни в игровые базы, ни на сервер. Побочных эффектов при импорте нет.
"""
import datetime
import os
import re
import secrets
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
GP7_DIR = os.path.join(PORT, "AstoryServer", "Patches", "Gp7Gateway")
CYR = re.compile("[А-Яа-яЁё]")


def _refused(fn):
    """Текст отказа OpRefused или None."""
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


class _Req:
    """Подставной запрос для функций маршрутов: строка запроса и сессия с ролью."""

    def __init__(self, query, role="owner"):
        self.query, self.session = dict(query), {"user": {"role": role, "login": "selftest"}}


def _route(path):
    """Маршрут GET по пути → (функция, право)."""
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


REFUSALS = [  # (функция домена, строка запроса) — каждая должна отказать ДО обращения к базе
    ("purchases", {"from": "2026-11-21"}), ("purchases", {"to": "20261131"}), ("purchases", {"from": "20261122", "to": "20261121"}),
    ("purchases", {"size": "0"}), ("purchases", {"size": "201"}), ("purchases", {"page": "x"}), ("purchases", {"page": "0"}),
    ("purchases", {"kind": "sell"}), ("purchases", {"who": "admins"}), ("purchases", {"test": "2"}), ("purchases", {"svc": "all"}),
    ("purchases", {"code": "-1"}), ("purchases", {"code": "4294967296"}), ("purchases", {"code": "1; DROP"}),
    ("purchases", {"account": "x" * 51}), ("gifts", {"state": "X"}), ("gifts", {"hanging": "yes"}), ("gifts", {"minutes": "0"}),
    ("gifts", {"minutes": "10081"}), ("gifts", {"test": "t"}), ("holds", {"minutes": "-5"}), ("holds", {"window": "5"}),
    ("holds", {"window": "3601"}), ("sales", {"from": "20250101", "to": "20261121"}), ("sales", {"who": "x"}),
    ("sales", {"from": "20261122", "to": "20261121"}), ("accounts", {"who": "nobody"}), ("accounts", {"size": "500"}),
    ("summary", {"svc": "x"}), ("summary", {"minutes": "x"}),
    ("undelivered", {"minutes": "0"}), ("undelivered", {"minutes": "10081"}), ("undelivered", {"logs": "2"}), ("undelivered", {"who": "x"}),
    ("undelivered", {"from": "2026-11-01"}), ("undelivered", {"from": "20261122", "to": "20261121"}), ("undelivered", {"svc": "both"})]


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n
    from domains import money as M

    # ---- сверка подарков — тот же модуль шлюза
    GR = M.reconcile()
    check("деньги: сверка висящих подарков — модуль gift_reconcile.py шлюза gp7 (тот же файл, функции hint / build_sql / parse)",
          os.path.normcase(GR.LOADED_FROM) == os.path.normcase(M.RECONCILE_SRC) and callable(GR.hint) and callable(GR.build_sql)
          and GR.DEFAULT_WINDOW_SEC == 180, GR.LOADED_FROM)
    h0 = {"r_count": 1, "r_userindex": "9", "recipient": "x", "codes": [5]}
    check("деньги: подсказки gift_reconcile.hint — «вероятно выдано → commit», «не выдано → refund», «неясно» (поведение консольной сверки)",
          GR.hint(h0, {}, {5: (1, "")}, [])[0] == "вероятно выдано → commit" and GR.hint(h0, {}, {}, [])[0] == "не выдано → refund"
          and GR.hint(dict(h0, r_userindex=""), {}, {}, [])[0] == "неясно")

    # ---- проверка ввода (до базы: подставные соединения бросили бы ошибку, а не отказ)
    why = [_refused(lambda f=f, q=q: getattr(M, f)(q)) for f, q in REFUSALS]
    check("деньги: неверный ввод — отказ до базы (%d случаев: даты, страницы, вид, категория, тест, служебные, состояние, висящие, минуты, "
          "окно, код, длина логина, период продаж > 366 суток)" % len(REFUSALS), all(why), [(REFUSALS[i], w) for i, w in enumerate(why) if not w])
    check("деньги: тексты отказов без «; »", all("; " not in w for w in why if w), [w for w in why if w and "; " in w])
    check("деньги: период продаж > 366 суток — свой отказ", any(w and "период продаж" in w for w in why))

    # ---- права и маршруты
    roles = ("owner", "admin", "gm", "support")
    check("деньги: право money.view — owner и admin (gm и support — нет)", {r for r in roles if auth.can(r, "money.view")} == {"owner", "admin"})
    paths = ("/api/money/summary", "/api/money/purchases", "/api/money/gifts", "/api/money/holds", "/api/money/sales", "/api/money/accounts",
             "/api/money/undelivered")
    rt = {p: _route(p) for p in paths}
    check("деньги: маршруты %s — GET, право money.view" % ", ".join(paths), all(fn and perm == "money.view" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})

    # ---- SQL модуля: столбца password нет, [user] читается только перечнем столбцов
    src = open(os.path.join(ROOT, "domains", "money.py"), encoding="utf-8").read()
    code = re.sub(r'"""(?:[^"]|"(?!""))*"""', "", src)        # без строк документации (в них «FROM журнала…» — описание, не SQL)
    sql_lits = re.findall(r'"((?:SELECT|FROM|WHERE|LEFT|OUTER|CASE|SUM|COUNT|\(SELECT)[^"]*)"', code)
    check("деньги: в тексте SQL модуля нет password и «SELECT *» / «u.*» (DENY на password у asda_admin не обходится)",
          sql_lits and not any("password" in s.lower() or "select *" in s.lower() or "u.*" in s for s in sql_lits), len(sql_lits))
    check("деньги: в тексте SQL модуля нет русских букв (тексты — параметрами)", not any(CYR.search(s) for s in sql_lits),
          [s[:80] for s in sql_lits if CYR.search(s)][:3])

    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [w for w in why if w] + [
            "журнал покупок gp7 не прочитан: запрос к AsdaStoryLogin: Invalid object name 'dbo.GP7PurchaseLog'",
            "подарки gp7 не прочитаны: нет подключения к AsdaStoryLogin: Login timeout expired",
            "сверка подарка 15983 не выполнена: запрос к Joy1: Invalid object name 'Charinfo'",
            "продажи стока не прочитаны: SaleHair: запрос к AsdaStoryOp: Invalid object name 'SaleHair'",
            "продажи стока не прочитаны: нет подключения к AsdaStoryOp: Login timeout expired",
            "учётки сайта gp7 не прочитаны: запрос к AsdaStoryLogin: x", "учётки игры без строки сайта не посчитаны: запрос к AsdaStoryOp: x",
            "балансы gp7 не прочитаны: запрос к AsdaStoryLogin: x", "настройка testFixedBalance шлюза gp7 не прочитана: HostError",
            "карта шлюза gp7 не прочитана: HostError", "таблицы dbo.GP7GiftLog нет — подарки не показаны (шлюз без P101)",
            "учётки «Щит» нет ни в игре, ни на сайте gp7", "неясно", "вероятно выдано → commit", "не выдано → refund",
            "имя «Dupe» у 2 персонажей Joy1.dbo.Charinfo и ни один не совпал байт в байт", "получатель «Nobody» не найден в Joy1.dbo.Charinfo",
            "в окне есть другие подарки тому же получателю с тем же кодом: 208(H, 2026-11-21 10:00:00 UTC) — журнал выдачи может быть их",
            "EventGainItem 'CashGift' есть по всем кодам в окне заморозки",
            "ни EventGainItem 'CashGift' в окне, ни ячеек Item с этими кодами после заморозки",
            "частичные следы (EventGainItem: 79698×1,79699×0; Item: 79698×0,79699×0)",
            "журнал стойки gp7-20261024.log не прочитан: слишком много прочитано журналов за минуту — не больше 32 МБ на пользователя, подождите",
            "журнала шлюза за 16.10.2026 нет", "файл журнала шлюза gp7-20261101.log не прочитан", "журнал шлюза за 01.11.2026 не прочитан",
            "строка ответа шлюза не найдена в gp7-20261101.log",
            "отметка шлюза PURCHASE_UNCONFIRMED в gp7-20261122.log 01:10:00.123 (close, через 3 мс после ответа)",
            "ответ шлюза в gp7-20261023.log 00:28:35.787: отказ undeliverable-item-code",
            "ответ шлюза в gp7-20261023.log 00:28:35.787: код 493 < 20551 — GameServer такой код не выдаёт (sub_532A90)",
            "журнал GameServer GameServer Buy_20261024.txt в 16:45:21: «ItemCode is Invalid», код 606",
            "сокет GameServer закрыт через 1 мс после ответа шлюза в gp7-20261101.log 19:40:41.914 (SOCKET_ERROR read ECONNRESET)",
            "ответ шлюза найден в gp7-20261101.log 19:40:41.914: обрыва сокета и отказа GameServer по журналам нет",
            "сверка по номеру неприменима: заказ раньше первого номера gp7 в CashUse (№10113)",
            "сверка по номеру неприменима: в CashUse нет ни одного номера заказа gp7",
            "журнал «eventlog» пишется без общего доступа — целиком не читается"]
        miss = [x for x in ru if CYR.search(i18n.tr(x).replace("Щит", ""))]
        check("деньги EN: отказы, ошибки чтения (вложенным переводом), подсказки сверки — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
        check("деньги EN: имя в подсказке — данные (без замены слов: «Щит» остаётся «Щит»)",
              "“Щит”" in i18n.tr("учётки «Щит» нет ни в игре, ни на сайте gp7"))
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("деньги: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])

    # ---- веб
    js = open(os.path.join(ROOT, "web", "money.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("деньги веб: раздел #/money «Деньги» с правом money.view, значок premiumstore (окна игры), маршрут viewMoney, скрипт после acjournal.js",
          '["#/money", "Деньги", "money.view", "premiumstore"]' in app and 'case "money": return viewMoney(my);' in app
          and "/money.js" in idx and idx.index("/acjournal.js") < idx.index("/money.js"))
    check("деньги веб: без innerHTML, данные — текстовыми узлами (acText / itemLine), перевода данных нет",
          "innerHTML" not in js and "acText(" in js and "itemLine(" in js and "T(x." not in js and "T(r.login" not in js and "T(c.name" not in js)
    check("деньги веб: время в таблицах — одной шкалой «(сервер)», подписей UTC нет; «Расчёт» — settled_local (ревизия 51 Н-4)",
          "(UTC)" not in js and " UTC" not in js and '["Расчёт (сервер)", x => dt(x.settled_local)]' in js and "dt(x.settled_at)" not in js)
    check("деньги веб: итоги — «Списано», «Возвращено», «Итого» (ревизия 51 М-4), подпись стока по процедурам (UPCashitemBuy и UPHairChange — М-3), "
          "сверка с причёсками (Н-1), пометка обрезки висящих (М-2)", "Сумма списаний" not in js and '["Возвращено"' in js and "UPHairChange" in js
          and "hair_both" in js and "r.capped" in js and "в ящик" in js and "забраны из ящика" not in js)
    check("деньги веб: даты уходят ГГГГММДД (acDay), служебные — переключатель svc=in, подсказка «неясно» сверяется по hint_raw",
          "acDay(" in js and 'svcIn.checked ? "in" : "sep"' in js and "hint_raw" in js)
    labels = re.findall(r'h\("(?:h1|h2|th|span|button|label|b|div)", (?:null|\{[^}]*\}), "([^"]+)"', js)
    labels += re.findall(r'\["([^"]+)", \w+ =>', js) + re.findall(r'T\("([^"]+)"', js) + re.findall(r'placeholder: "([^"]+)"', js)
    labels += re.findall(r'h\("label", null, \w+, "([^"]+)"\)', js)
    for m in re.findall(r"const MN_\w+ = \{([^}]*)\}", js):
        labels += re.findall(r':\s*"([^"]+)"', m)
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted({x for x in labels if x not in have and CYR.search(x)})
    check("деньги веб EN: у всех подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(set(labels)), not lack and len(set(labels)) > 100, lack[:8])
    blk = wi[wi.index("// ★ А6.2"):]
    keys = re.findall(r'(?:^|[{,])\s*"((?:[^"\\]|\\.)+)":\s*"', blk, re.M)
    earlier = set(re.findall(r'(?:^|[{,])\s*"((?:[^"\\]|\\.)+)":\s*"', wi[:wi.index("// ★ А6.2")], re.M))
    check("деньги веб EN: новые ключи web/i18n.js не повторяют прежние и друг друга (%d ключей)" % len(keys),
          len(keys) == len(set(keys)) and not set(keys) & earlier, sorted(set(keys) & earlier)[:5])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "money.js")], capture_output=True, timeout=60)
        check("деньги: node --check web/money.js", r.returncode == 0, r.stderr[-300:])
        check("деньги веб: карточка «Оплачено, не выдано» (/api/money/undelivered, причина A / B / не установлена / неприменима, пояснение текстовым "
              "узлом, журналы — только по кнопке «Разобрать причины по журналам», ревизия 53 Н-2), в сводке — «Списано, но не выдано» отдельной таблицей категорий",
              '"/api/money/undelivered?"' in js and 'h("h2", null, "Оплачено, не выдано")' in js and "acText(x.reason_why)" in js
              and 'logs: withLogs ? "1" : "0"' in js and "loadUndelivered(true)" in js and "svcIn.addEventListener" in js
              and "loadUndelivered(); loadAccounts" not in js and 's.undelivered && s.undelivered.totals' in js and "MN_UNDEL_COLS" in js
              and all(k in js for k in ('A: "A:', 'B: "B:', 'unknown: "', 'na: "')))
    except (OSError, subprocess.SubprocessError) as ex:
        check("деньги: node --check web/money.js (node не запустился)", False, str(ex))

    # ---- консоль и выкладка
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "money"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("purchases", "--bogus")
    c2, o2 = con("gifts", "--state")
    c3, o3 = con("nope")
    c4, o4 = con("holds", "extra")
    c5, o5 = con("undelivered", "--minutes")
    check("деньги консоль: неизвестный ключ, ключ без значения, неизвестное действие, лишнее слово — отказ без запроса к базе",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3
          and c4 and "неизвестный аргумент extra" in o4 and c5 and "нет значения" in o5, (o1[-200:], o2[-200:], o3[-200:], o4[-200:], o5[-200:]))
    hp = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60, cwd=ROOT,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    ho = hp.stdout.decode("utf-8", "replace")
    check("деньги консоль: --help печатает справку с командой money (ничего не делает)", hp.returncode == 0 and "  money …" in ho
          and "holds [--minutes N]" in ho and "undelivered [--who" in ho)
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("деньги выкладка: в архив кладётся ext/gift_reconcile.py — тот же файл шлюза без правок; нет исходника — отказ выкладки",
          'z.writestr("ext/gift_reconcile.py", _b)' in dep and "_readb(_money.RECONCILE_SRC)" in dep and "SystemExit" in dep and M.RECONCILE_EXT.endswith(os.path.join("ext", "gift_reconcile.py")))
    imp = subprocess.run([py, "-c", "import sys; sys.path.insert(0, %r); from domains import money as M; "
                          "print('IMPORT_OK', M._GR is None, M._pmap['at'] is None)" % ROOT], capture_output=True, timeout=60, cwd=ROOT)
    check("деньги: импорт domains/money.py ничего не делает (сверка и карта шлюза не загружены, к базе и серверу не обращается)",
          b"IMPORT_OK True True" in imp.stdout, (imp.stdout + imp.stderr)[-300:])


# ---------------------------------------------------------------- стенд LocalDB

def _subst(text, names):
    """Имена живых баз в тексте SQL → имена баз стенда (AsdaStoryLogin / AsdaStoryOp / Joy1 / JoyLog1)."""
    for a, b in (("AsdaStoryLogin", names["L"]), ("AsdaStoryOp", names["O"]), ("AsdaStoryOP", names["O"]), ("JoyLog1", names["G"]), ("Joy1", names["Y"])):
        text = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % a, b, text)
    return text


def _fill(cur, db_, tbl, vals, R):
    """INSERT строки по снимку живой схемы (reconcile_stand.schema): заданные столбцы — параметрами, NOT NULL без значения — 0 / '' / сейчас."""
    cols, _pk = R.schema(db_, tbl)
    names, marks, args = [], [], []
    for n, t, _ml, nl, df in cols:
        if n in vals:
            names.append("[%s]" % n)
            marks.append("?")
            args.append(vals[n])
        elif not nl and not df:
            names.append("[%s]" % n)
            marks.append({"varchar": "''", "char": "''", "datetime": "GETDATE()", "uniqueidentifier": "NEWID()"}.get(t, "0"))
    cur.execute("INSERT %s (%s) VALUES (%s)" % (tbl, ", ".join(names), ", ".join(marks)), args)


# Покупки стенда: (id, учётка сайта, код, сумма, success, сколько назад) — учётки: 1 alpha (9001), 2 svc1 (3 — служебная), 3 nogame (без
# игровой), 4 Beta (9002, в игре «beta» — регистр), 5 «12345» (9005 — логин из цифр), 6 zeta (номер 12345).
# ★ 22.11.2026 (сбой стенда после полуночи 22.11 00:07): «сколько назад» у ПОКУПОК и стока — от ФИКСИРОВАННЫХ часов t0 = вчера 12:00
#   (сутки строк не зависят от времени запуска); у подарков — от настоящего «сейчас» (висящие сверяются с часами SQL-сервера), а их
#   сутки в ожиданиях считаются из тех же меток времени (_stamp), не числами «на сегодня».
USERS = [(1, "alpha"), (2, "svc1"), (3, "nogame"), (4, "Beta"), (5, "12345"), (6, "zeta")]
MEMBERS = [(9001, "alpha"), (3, "svc1"), (9002, "beta"), (9005, "12345"), (12345, "zeta"), (9010, "nosite"), (8001, "recvyes")]
CAT = {1: "player", 2: "service", 3: "nolink", 4: "player", 5: "player", 6: "player"}
M_ = datetime.timedelta(minutes=1)
D_ = datetime.timedelta(days=1)
BUYS = [(101, 1, 37, 190, 1, 2 * M_), (102, 1, 37, 190, 1, 3 * M_), (103, 1, 37, 190, 1, 4 * M_), (104, 1, 45, 10000, 1, 3 * D_),
        (105, 1, 37, 190, 0, 5 * M_), (106, 2, 37, 190, 1, 6 * M_), (107, 2, 37, 190, 1, 7 * M_), (108, 3, 9, 440, 1, 8 * M_),
        (109, 4, 20, 100000, 1, 9 * M_), (110, 5, 30, 990, 1, 10 * M_), (111, 6, 32, 1890, 1, 3 * D_),
        (112, 1, 96, 29, 1, 11 * M_), (113, 2, 99, 200000, 1, 12 * M_)]   # ★ ревизия 51: причёска (только SaleHair) и крупная покупка служебной
# Подарки: (заказ, отправитель, получатель, коды, сумма, состояние, test_mode, сколько назад)
GIFTS = [(201, 1, "RecvYes", [79698], 399, "H", 0, 30 * M_), (202, 1, "RecvNo", [79698], 399, "H", 1, 30 * M_),
         (203, 1, "Nobody", [79698], 399, "H", 0, 30 * M_), (204, 1, "Dupe", [79698], 399, "H", 0, 30 * M_),
         (205, 1, "RecvPart", [79698, 79699], 798, "H", 0, 30 * M_), (206, 1, "RecvYes", [79699], 399, "H", 0, 2 * M_),
         (207, 2, "RecvOld", [79698], 399, "H", 0, 31 * M_), (208, 1, "RecvOld", [79698], 399, "H", 0, 30 * M_),
         (209, 1, "RecvYes", [79698], 399, "C", 0, D_), (210, 1, "RecvNo", [79698], 399, "R", 0, D_),
         (212, 1, "RecvNo", [79698], 500, "R", 1, D_)]      # ★ ревизия 51 Н-3: возврат в тесте — только state, строки возврата нет
TEST_R = {212}                                    # подарки R с test_mode = 1: деньги «вернулись» без строки возврата
REFUND = (211, 1, 79698, -399, 1, D_)          # строка возврата подарка 210 (GP7_GiftSettle REFUND)
CHARS = {"RecvYes": (8001, 0), "RecvNo": (8002, 0), "Dupe": (8003, 0), "DUPE": (8004, 0), "RecvPart": (8005, 0), "RecvOld": (8006, 0),
         "Alice": (9001, 0)}
HOLD_EXPECT = {201: "вероятно выдано → commit", 202: "не выдано → refund", 203: "неясно", 204: "не выдано → refund", 205: "неясно",
               207: "неясно", 208: "неясно"}


def sandbox(check, ldb):
    """Свои базы LocalDB: настоящий установщик шлюза, синтетика покупок, подарков и стока; все функции раздела и маршруты; нет таблицы."""
    from core import db
    from domains import money as M
    sys.path.insert(0, os.path.join(GP7_DIR, "stand"))
    import reconcile_stand as R                     # снимок живых схем Item / Charinfo / EventGainItem (без побочных эффектов при импорте)
    tag = secrets.token_hex(3)
    names = {"L": "AsdaMnL_" + tag, "O": "AsdaMnO_" + tag, "Y": "AsdaMnY_" + tag, "G": "AsdaMnG_" + tag}
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE SQL_Latin1_General_CP1_CI_AS" % names["L"])
    for k in ("O", "Y", "G"):
        m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names[k])
    saved = (M.OP_DB, M.LOGIN_DB)
    try:
        now, utc = datetime.datetime.now().replace(microsecond=0), datetime.datetime.utcnow().replace(microsecond=0)
        t0 = datetime.datetime.combine(now.date() - D_, datetime.time(12, 0))      # фиксированные часы покупок и стока (местные)
        stamp = _stamp(now, t0)
        lc = ldb(names["L"]).cursor()
        lc.execute("CREATE TABLE dbo.[user] (id BIGINT IDENTITY(1,1) PRIMARY KEY, username VARCHAR(50) NOT NULL, password VARCHAR(50) NULL, "
                   "name VARCHAR(50) NULL, role VARCHAR(50) NULL)")
        lc.execute("SET IDENTITY_INSERT dbo.[user] ON")
        for i, u in USERS:
            lc.execute("INSERT dbo.[user] (id, username, password, role) VALUES (?, ?, ?, 'GA')", (i, u, "pw-" + u))
        lc.execute("SET IDENTITY_INSERT dbo.[user] OFF")
        text = open(os.path.join(GP7_DIR, "install_gp7_balance.sql"), encoding="utf-8-sig").read()
        nb = 0
        for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
            if batch.strip() and not re.match(r"^\s*USE\s", batch, re.I):
                lc.execute(batch)
                nb += 1
        objs = sorted(r[0] for r in lc.execute("SELECT name FROM sys.objects WHERE name LIKE 'GP7%' AND type IN ('U', 'P')").fetchall())
        check("деньги стенд: настоящий установщик шлюза install_gp7_balance.sql (%d пакетов) — GP7Balance / GP7PurchaseLog / GP7GiftLog и процедуры" % nb,
              {"GP7Balance", "GP7PurchaseLog", "GP7GiftLog", "GP7_Purchase", "GP7_GiftHold", "GP7_GiftSettle"} <= set(objs), objs)
        lc.execute("SET IDENTITY_INSERT dbo.GP7PurchaseLog ON")
        rows = list(BUYS) + [(g[0], g[1], g[3][0], g[4], 1, g[7]) for g in GIFTS] + [REFUND]
        for pid, uid, code, amount, ok, ago in rows:
            lc.execute("INSERT dbo.GP7PurchaseLog (id, user_id, item_code, amount, balance_before, balance_after, success, created_at) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (pid, uid, code, amount, amount if ok else 0, 0 if ok else 0, ok, stamp[pid] - (now - utc)))
        lc.execute("SET IDENTITY_INSERT dbo.GP7PurchaseLog OFF")
        for oid, uid, rcp, codes, amount, st, test, ago in GIFTS:
            c = (codes + [0] * 7)[:7]
            lc.execute("INSERT dbo.GP7GiftLog (order_id, gs_key, sender_user_id, sender_account, sender_userindex, sender_charidx, sender_usernum, "
                       "sender_name, recipient_name, code1, code2, code3, code4, code5, code6, code7, amount, state, test_mode, created_at, settled_at, "
                       "refund_log_id) VALUES (?, CAST(? AS BINARY(8)), ?, ?, ?, 0, 1, 'Alice', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [oid, oid, uid, dict(USERS)[uid], 9001 if uid == 1 else 3, rcp] + c + [amount, st, test, utc - ago,
                                                                                               None if st == "H" else utc - ago + M_, 211 if oid == 210 else None])
        for i, b in ((1, 0), (2, 544675), (3, 12345), (4, 0)):
            lc.execute("INSERT dbo.GP7Balance (user_id, balance, present) VALUES (?, ?, 0)", (i, b))
        oc = ldb(names["O"]).cursor()
        oc.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(20), us_block TINYINT NOT NULL DEFAULT 0)")
        for u, lg in MEMBERS:
            oc.execute("INSERT dbo.Us_member (Userindex, Us_id) VALUES (?, ?)", (u, lg))
        oc.execute("CREATE TABLE dbo.CashUse (sNum INT IDENTITY(1,1), Edate DATETIME, Seridx TINYINT, Orderidx INT, Realcash INT)")
        sale = "Edate DATETIME, iType TINYINT, Seridx TINYINT, Gameid VARCHAR(61), Charname VARCHAR(20), Userindex INT, Charidx TINYINT, Orderidx INT, " \
               "Channel TINYINT, Poridx TINYINT, Code INT, %sUmac INT, Report VARCHAR(100)"
        oc.execute("CREATE TABLE dbo.SalePremium (%s)" % (sale % ""))
        oc.execute("CREATE TABLE dbo.SaleFunctional (%s)" % (sale % "Ramount INT, "))
        oc.execute("CREATE TABLE dbo.SaleHair (Edate DATETIME, Seridx TINYINT, Gameid VARCHAR(61), Charname VARCHAR(20), Userindex INT, Charidx TINYINT, "
                   "Orderidx INT, Code INT, Umac INT)")
        for o, cash in ((101, 190), (102, 190), (103, 190), (106, 190), (108, 440), (999, 777)):
            oc.execute("INSERT dbo.CashUse (Edate, Seridx, Orderidx, Realcash) VALUES (?, 1, ?, ?)", (t0 - M_, o, cash))
        for o in (101, 102, 103):
            oc.execute("INSERT dbo.SalePremium (Edate, iType, Seridx, Gameid, Charname, Userindex, Charidx, Orderidx, Channel, Poridx, Code, Umac, Report) "
                       "VALUES (?, 0, 1, 'alpha', 'Alice', 9001, 0, ?, 0, 7, 79700, 190, 'Functional Item')", (t0 - M_, o))
        oc.execute("INSERT dbo.SaleFunctional (Edate, iType, Seridx, Gameid, Charname, Userindex, Charidx, Orderidx, Channel, Poridx, Code, Ramount, Umac, "
                   "Report) VALUES (?, 3, 1, 'svc1', 'Svc', 3, 0, 106, 0, 3, 197, 1, 999999, 'Locky Box')", (t0 - M_,))
        oc.execute("INSERT dbo.SaleHair (Edate, Seridx, Gameid, Charname, Userindex, Charidx, Orderidx, Code, Umac) VALUES (?, 1, 'alpha', 'Alice', 9001, "
                   "0, 555, -905, 29)", (t0 - M_,))
        oc.execute("INSERT dbo.SaleHair (Edate, Seridx, Gameid, Charname, Userindex, Charidx, Orderidx, Code, Umac) VALUES (?, 1, 'alpha', 'Alice', 9001, "
                   "0, 112, -904, 29)", (t0 - 11 * M_,))     # ★ ревизия 51 Н-1: причёска gp7 112 — строка только в SaleHair (UPHairChange)
        yc = ldb(names["Y"]).cursor()
        yc.execute(R.ddl("Joy1", "dbo.Item"))
        yc.execute(R.ddl("Joy1", "dbo.Charinfo"))
        yc.execute("CREATE TABLE dbo.ItemPostbox (iType TINYINT, Orderidx INT, Userindex INT, Charidx TINYINT, Code INT, Amount INT)")
        yc.execute("INSERT dbo.ItemPostbox VALUES (0, 109, 9002, 0, 65493, 1)")   # заказ 109 лежит в ящике (без строки стока)
        for nm, (u, c) in CHARS.items():
            _fill(yc, "Joy1", "dbo.Charinfo", {"Userindex": u, "Charidx": c, "Uid": "acc_" + nm.lower(), "Charname": nm}, R)
        gc = ldb(names["G"]).cursor()
        gc.execute(R.ddl("JoyLog1", "dbo.EventGainItem"))
        hold_local = now - 30 * M_
        for (u, c), code in (((8001, 0), 79698), ((8005, 0), 79698), ((8006, 0), 79698)):
            _fill(gc, "JoyLog1", "dbo.EventGainItem", {"Edate": hold_local + datetime.timedelta(seconds=40), "Userindex": u, "Charidx": c,
                                                       "Code": code, "Amount": 1, "State": "CashGift", "Serial": "s"}, R)
        mp = {"AsdaStoryLogin": names["L"], "AsdaStoryOp": names["O"], "Joy1": names["Y"], "joylog1": names["G"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        M.OP_DB, M.LOGIN_DB = names["O"], names["L"]
        import time
        pm_saved, tfb_saved = dict(M._pmap), M.test_fixed_balance
        M._pmap.update(at=time.monotonic() + 10 ** 9, map={37: (76451, 190), 20: (65493, 100000)}, error=None)   # карта шлюза стенда (без SSH)
        M.test_fixed_balance = lambda: (999999, None)
        seen = []
        orig = db.GameReader.rows

        def spy(self, sql, params=()):
            seen.append((self.name, sql))
            return orig(self, sql, params)
        db.GameReader.rows = spy
        try:
            _sandbox_checks(check, M, names, ldb, now, t0, stamp)
            _undelivered_checks(check, M, names, ldb, now, t0, stamp)
            check("деньги стенд: все %d запросов раздела — чтение (assert_select_only), без password, без «SELECT *», без русских букв" % len(seen),
                  seen and not any("password" in s.lower() or "select *" in s.lower() or CYR.search(s) for _n, s in seen),
                  [s[:100] for _n, s in seen if "password" in s.lower() or CYR.search(s)][:3])
            check("деньги стенд: [user] читается только столбцами id, username, role",
                  all(not re.search(r"\bu\.(?!id\b|username\b|role\b)\w+", s) for _n, s in seen if "[user]" in s)
                  and any("[user]" in s for _n, s in seen))
            # ---- нет таблицы: подарков (шлюз без P101) и одной таблицы стока
            lc.execute("ALTER TABLE dbo.GP7GiftLog DROP CONSTRAINT FK_GP7GiftLog_Purchase")
            lc.execute("DROP TABLE dbo.GP7GiftLog")
            oc.execute("DROP TABLE dbo.SaleHair")
            s = M.summary({})
            p = M.purchases({})
            sl = M.sales({})
            check("деньги стенд: таблицы GP7GiftLog нет — журнал покупок считается (те же 25 строк, без подарков, пометка в errors), в сводке — "
                  "строка ошибки подарков, итоги покупок есть",
                  p["total"] == 25 and any("GP7GiftLog нет" in e for e in p["errors"]) and all(r["kind"] != "gift" for r in p["rows"])
                  and s["purchases"] and s["purchases"]["cats"]["service"]["n"] == 4 and any(e.startswith("подарки gp7 не прочитаны:") for e in s["errors"]),
                  (p["total"], p["errors"], s["errors"]))
            check("деньги стенд: таблицы SaleHair нет — строка ошибки «продажи стока … SaleHair», CashUse / SalePremium / SaleFunctional считаются",
                  any(e.startswith("продажи стока не прочитаны: SaleHair:") for e in s["errors"]) and [x["table"] for x in s["stock"]]
                  == ["CashUse", "SalePremium", "SaleFunctional"] and any(e.startswith("продажи стока не прочитаны: SaleHair:") for e in sl["errors"])
                  and sl["days"], (s["errors"], sl["errors"]))
        finally:
            db.GameReader.rows = orig
            db.set_override("game", None)
            M._pmap.clear()
            M._pmap.update(pm_saved)
            M.test_fixed_balance = tfb_saved
    finally:
        M.OP_DB, M.LOGIN_DB = saved
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def _stamp(now, t0):
    """Местное время каждой строки журнала стенда: покупки — t0 − «назад» (фиксированные часы), подарки и строка возврата — сейчас − «назад»."""
    out = {pid: t0 - ago for pid, _u, _c, _a, _ok, ago in BUYS}
    out.update({g[0]: now - g[7] for g in GIFTS})
    out[REFUND[0]] = now - REFUND[5]
    return out


def _sandbox_checks(check, M, names, ldb, now, t0, stamp):
    """Итоги, фильтры, страницы, подарки, висящие (против консольной сверки), продажи, связь учёток, маршруты."""
    allrows = list(BUYS) + [(g[0], g[1], g[3][0], g[4], 1, g[7]) for g in GIFTS] + [REFUND]
    exp = {c: {"n": 0, "sum": 0, "gross": 0, "refunded": 0} for c in M.WHO}
    for pid, uid, code, amount, ok, ago in allrows:
        e = exp[CAT[uid]]
        e["n"] += 1
        e["gross"] += amount if ok and amount > 0 else 0
        e["refunded"] += (-amount if ok and amount < 0 else 0) + (amount if pid in TEST_R else 0)
        e["sum"] = e["gross"] - e["refunded"]
    lc = ldb(names["L"]).cursor()
    direct = lc.execute("SELECT COUNT(*), SUM(CASE WHEN success = 1 THEN amount ELSE 0 END) - (SELECT SUM(p.amount) FROM dbo.GP7PurchaseLog p JOIN "
                        "dbo.GP7GiftLog g ON g.order_id = p.id WHERE g.state = 'R' AND g.test_mode = 1) FROM dbo.GP7PurchaseLog").fetchone()
    s = M.summary({})
    si = M.summary({"svc": "in"})
    c = s["purchases"]["cats"]
    check("деньги стенд: итоги по категориям (строк, списано, возвращено, итого) — игроки %(player)s, служебные %(service)s, сайт без игровой "
          "%(nolink)s (по синтетике)" % {k: (v["n"], v["gross"], v["refunded"], v["sum"]) for k, v in exp.items()},
          all(c[k][x] == exp[k][x] for k in M.WHO for x in ("n", "gross", "refunded", "sum")), c)
    check("деньги стенд: служебные ≤ 5000 — отдельной строкой, НЕ в общем итоге (по умолчанию); svc=in — в итоге; итог всех = COUNT(*) и SUM по таблице "
          "минус тестовые возвращённые подарки",
          s["purchases"]["total"]["n"] == direct[0] - exp["service"]["n"] and s["purchases"]["total"]["sum"] == direct[1] - exp["service"]["sum"]
          and si["purchases"]["total"]["n"] == direct[0] and si["purchases"]["total"]["sum"] == direct[1] and not s["purchases"]["service_in_total"]
          and si["purchases"]["service_in_total"], (s["purchases"]["total"], si["purchases"]["total"], direct))
    check("деньги стенд: отказ (success 0) — 1, не в «списано»; возвратов 2 — строка возврата 211 (399) и тестовый подарок R 212 (500, без строки "
          "возврата — ревизия 51 Н-3); тестовых подарков 2 (202, 212)",
          c["player"]["fails"] == 1 and c["player"]["refunds"] == 2 and c["player"]["refunded"] == 899 and c["player"]["test_gifts"] == 2
          and c["player"]["test_gift_sum"] == 899, c["player"])
    check("деньги стенд: подарки по состояниям (H 8, C 1, R 1; test_mode у одного H), висящих старше 10 мин — 7 (свежий не висит)",
          {(g["state"], bool(g["test_mode"])): g["n"] for g in s["gifts"]} == {("H", False): 7, ("H", True): 1, ("C", False): 1, ("R", False): 1, ("R", True): 1}
          and s["hanging"] == 7, (s["gifts"], s["hanging"]))
    b = s["balances"]["cats"]
    check("деньги стенд: балансы по категориям — служебная 544675 отдельно, без игровой 12345; общий итог без служебных",
          b["service"]["sum"] == 544675 and b["nolink"]["sum"] == 12345 and s["balances"]["total"]["sum"] == 12345, b)
    st = {x["table"]: x for x in s["stock"]}
    check("деньги стенд: сток рядом — CashUse 6 строк, SalePremium 3, SaleFunctional 1 (служебная), SaleHair 2",
          st["CashUse"]["n"] == 6 and st["SalePremium"]["n"] == 3 and st["SaleFunctional"]["svc_n"] == 1 and st["SaleHair"]["n"] == 2, s["stock"])
    check("деньги стенд: testFixedBalance (подставной 999999) в сводке, сводка без ошибок", s["test_fixed_balance"] == 999999 and not s["errors"],
          s["errors"])

    # ---- журнал покупок: фильтры
    pa = M.purchases({"size": "200"})
    ids = [r["id"] for r in pa["rows"]]
    check("деньги стенд: журнал покупок — 25 строк, новые сверху (id), вид, категория, логины, test у подарка 202",
          pa["total"] == 25 and ids == sorted(ids, reverse=True) and {r["id"]: r["kind"] for r in pa["rows"]}[105] == "fail"
          and {r["id"]: r["kind"] for r in pa["rows"]}[211] == "refund" and {r["id"]: r["kind"] for r in pa["rows"]}[201] == "gift"
          and {r["id"]: r["kind"] for r in pa["rows"]}[101] == "buy" and {r["id"]: r["test"] for r in pa["rows"]}[202]
          and {r["id"]: r["cat"] for r in pa["rows"]}[106] == "service" and {r["id"]: r["cat"] for r in pa["rows"]}[108] == "nolink"
          and {r["id"]: r["Us_id"] for r in pa["rows"]}[109] == "beta" and {r["id"]: r["test_refunded"] for r in pa["rows"]}[212]
          and not {r["id"]: r["test_refunded"] for r in pa["rows"]}[210], [(r["id"], r["kind"], r["cat"]) for r in pa["rows"][:4]])
    d3 = (t0 - 3 * D_).strftime("%Y%m%d")
    today, t0d = now.strftime("%Y%m%d"), t0.strftime("%Y%m%d")
    n_from_today = sum(1 for v in stamp.values() if v.strftime("%Y%m%d") >= today)       # строки «с сегодня» — по их меткам, не числом
    n_t0 = sum(1 for v in stamp.values() if v.strftime("%Y%m%d") == t0d)
    flt = {"учётка логином alpha": ({"account": "alpha"}, 17), "учётка номером 9001": ({"account": "9001"}, 17),
           "учётка «BETA» (регистр, логин игры «beta», сайта «Beta»)": ({"account": "BETA"}, 1),
           "логин из цифр «12345» — и номер 12345 (zeta), и логин «12345»": ({"account": "12345"}, 2),
           "служебная svc1": ({"account": "svc1"}, 4), "игровая без строки сайта — 0 строк": ({"account": "nosite"}, 0),
           "код 37": ({"code": "37"}, 6), "вид buy": ({"kind": "buy"}, 12), "вид gift": ({"kind": "gift"}, 11), "вид refund": ({"kind": "refund"}, 1),
           "вид fail": ({"kind": "fail"}, 1), "категория service": ({"who": "service"}, 4), "категория nolink": ({"who": "nolink"}, 1),
           "категория player": ({"who": "player"}, 20), "тест": ({"test": "1"}, 2), "не тест": ({"test": "0"}, 23),
           "даты только 3 суток назад": ({"from": d3, "to": d3}, 2), "даты «по» 3 суток назад": ({"to": d3}, 2),
           "даты «с» сегодня (по меткам строк)": ({"from": today}, n_from_today),
           "даты — сутки фиксированных часов t0": ({"from": t0d, "to": t0d}, n_t0)}
    got = {k: M.purchases(q)["total"] for k, (q, _n) in flt.items()}
    check("деньги стенд: каждый фильтр журнала покупок (%d) даёт ожидаемое число строк" % len(flt), all(got[k] == n for k, (_q, n) in flt.items()),
          {k: (got[k], n) for k, (_q, n) in flt.items() if got[k] != n})
    acc = M.resolve_account("12345")
    check("деньги стенд: логин из цифр «12345» — учётки игры 9005 (логин) и 12345 (номер), строки сайта 5 и 6 (урок ревизии 50 п.9)",
          acc["uids"] == [9005, 12345] and acc["site"] == [5, 6], acc)
    w = _refused(lambda: M.purchases({"account": "nobody"}))
    check("деньги стенд: учётки нет ни в игре, ни на сайте — отказ с логином", w and "nobody" in w, w)
    ft = M.purchases({"who": "service"})
    check("деньги стенд: фильтр «служебные» — по фильтру 4 строки, общий итог 0 (служебные не в нём), svc=in — 4",
          ft["totals"]["cats"]["service"]["n"] == 4 and ft["totals"]["total"]["n"] == 0
          and M.purchases({"who": "service", "svc": "in"})["totals"]["total"]["n"] == 4)
    p1, p2, p8, p99 = (M.purchases({"size": "3", "page": str(p)}) for p in (1, 2, 9, 99))
    seq = [r["id"] for r in p1["rows"] + p2["rows"]]
    check("деньги стенд: страницы по 3 — 9 страниц, без повторов и пропусков, последняя — 1 строка, страница за концом → последняя",
          p1["pages"] == 9 and seq == ids[:6] and len(p8["rows"]) == 1 and p99["page"] == 9 and [r["id"] for r in p99["rows"]] == [r["id"] for r in p8["rows"]],
          (p1["pages"], seq, len(p8["rows"]), p99["page"]))
    r101 = {r["id"]: r for r in pa["rows"]}[101]
    check("деньги стенд: позиция — код витрины, код выдачи и цена по карте шлюза (76451, 190), местное время = UTC + сдвиг сервера",
          r101["pos"]["code"] == 37 and r101["pos"]["delivery"] == 76451 and r101["pos"]["map_price"] == 190 and r101["created_local"] - r101["created_at"] == datetime.timedelta(minutes=pa["shift_min"]), r101["pos"])

    # ---- подарки
    g_all = M.gifts({"size": "200"})
    check("деньги стенд: подарки — 11, новые сверху, у висящих H старше 10 мин метка, свежий 206 не висит, отправитель svc1 — служебный",
          g_all["total"] == 11 and {r["order_id"]: r["hanging"] for r in g_all["rows"]} == {201: True, 202: True, 203: True, 204: True, 205: True,
                                                                                               206: False, 207: True, 208: True, 209: False, 210: False, 212: False}
          and {r["order_id"]: r["service"] for r in g_all["rows"]}[207] and len({r["order_id"]: r for r in g_all["rows"]}[205]["items"]) == 2,
          [(r["order_id"], r["hanging"]) for r in g_all["rows"]])
    gf = {"состояние H": ({"state": "H"}, 8), "состояние C": ({"state": "C"}, 1), "состояние R": ({"state": "R"}, 2), "тест": ({"test": "1"}, 2),
          "висящие": ({"hanging": "1"}, 7), "висящие старше 60 мин": ({"hanging": "1", "minutes": "60"}, 0),
          "отправитель svc1": ({"account": "svc1"}, 1), "получатель — персонаж учётки 8001 (RecvYes)": ({"account": "8001"}, 3)}
    gg = {k: M.gifts(q)["total"] for k, (q, _n) in gf.items()}
    check("деньги стенд: каждый фильтр подарков (%d) даёт ожидаемое число строк" % len(gf), all(gg[k] == n for k, (_q, n) in gf.items()),
          {k: (gg[k], n) for k, (_q, n) in gf.items() if gg[k] != n})

    # ---- висящие: против консольной сверки gift_reconcile на тех же базах
    GR = M.reconcile()
    sql = _subst(GR.build_sql(10, GR.DEFAULT_WINDOW_SEC), names)
    cur = ldb(names["L"]).cursor()
    cur.execute(sql)
    lines = []
    while True:
        if cur.description:
            lines += [str(r[0]).strip() for r in cur.fetchall() if r[0] is not None]
        if not cur.nextset():
            break
    _info, holds, items, evs, others = GR.parse(lines)
    oracle = {h["order"]: GR.hint(h, items.get(h["order"], {}), evs.get(h["order"], {}), others.get(h["order"], [])) for h in holds}
    mine = M.holds({})
    got = {h["order_id"]: (h["hint"], h["hint_why"]) for h in mine["holds"]}
    check("деньги стенд: висящие — те же заказы и те же подсказки (метка И пояснение), что у консольной gift_reconcile.py на тех же базах (%d)" % len(oracle),
          oracle and got == oracle, {k: (got.get(k), oracle.get(k)) for k in set(got) | set(oracle) if got.get(k) != oracle.get(k)})
    check("деньги стенд: подсказки по случаям — выдано → commit (201), ничего → refund (202, test_mode), нет получателя → неясно (203), "
          "Dupe/DUPE — байт-в-байт (204 → refund), частично → неясно (205), два подарка одному получателю в окне → неясно (207, 208)",
          {k: v[0] for k, v in got.items()} == HOLD_EXPECT and mine["counts"] == {"H": 8, "hanging": 7, "all": 11} and not mine["capped"]
          and {h["order_id"]: h for h in mine["holds"]}[204]["r_userindex"] == 8003 and {h["order_id"]: h for h in mine["holds"]}[202]["test_mode"],
          {k: v[0] for k, v in got.items()})
    gview = {r["order_id"]: r for r in g_all["rows"]}
    check("деньги стенд: значок «висит» и счёт висящих — одна граница (ревизия 51 М-1): висящие в списке = заказы разбора = счёт сводки",
          {k for k, r in gview.items() if r["hanging"]} == set(got) == {201, 202, 203, 204, 205, 207, 208} and s["hanging"] == len(got))
    check("деньги стенд: время в одной шкале — «Расчёт» подарка и «Заморожено» в часах сервера (UTC + сдвиг), не UTC (ревизия 51 Н-4)",
          gview[209]["settled_local"] - gview[209]["settled_at"] == datetime.timedelta(minutes=g_all["shift_min"])
          and gview[209]["created_local"] - gview[209]["created_at"] == datetime.timedelta(minutes=g_all["shift_min"])
          and s["first"] == lc.execute("SELECT DATEADD(minute, ?, MIN(created_at)) FROM dbo.GP7PurchaseLog", s["shift_min"]).fetchone()[0])
    saved_max = M.HOLDS_MAX
    try:
        M.HOLDS_MAX = 2
        hc = M.holds({})
    finally:
        M.HOLDS_MAX = saved_max
    check("деньги стенд: висящих больше предела — разобраны первые 2 из 7, пометка capped (ревизия 51 М-2)",
          len(hc["holds"]) == 2 and hc["capped"] and hc["holds_max"] == 2 and hc["counts"]["hanging"] == 7, (len(hc["holds"]), hc["capped"]))
    h60 = M.holds({"minutes": "31"})
    check("деньги стенд: висящие старше 31 мин — только 207", [h["order_id"] for h in h60["holds"]] == [207], [h["order_id"] for h in h60["holds"]])

    # ---- продажи по дням и позициям
    sql_today = lambda: ldb(names["L"]).cursor().execute("SELECT CONVERT(char(8), SYSDATETIME(), 112)").fetchone()[0]
    td_before = sql_today()
    sl = M.sales({})
    td_after = sql_today()
    d1 = (now - D_).strftime("%Y%m%d")
    days = {d["day"]: d for d in sl["days"]}
    want = {}                                      # сутки → [покупок без служебных, служебных, подарков без служебных] — по меткам строк
    for r in BUYS + [(g[0], g[1], g[3][0], g[4], 1, g[7]) for g in GIFTS]:
        if r[4] != 1 or r[3] <= 0:
            continue
        w = want.setdefault(stamp[r[0]].strftime("%Y%m%d"), [0, 0, 0])
        if CAT[r[1]] == "service":
            w[1] += 1
        else:
            w[0] += 1
            w[2] += 1 if r[0] >= 200 else 0
    got_days = {d: [days[d]["total"]["n"], days[d]["cats"]["service"]["n"], days[d]["total"]["gifts"]] for d in days}
    check("деньги стенд: продажи по дням — КАЖДЫЕ сутки (%d): покупок без служебных, служебных отдельно и подарков столько же, сколько строк с "
          "такой меткой (не зависит от времени запуска: покупки — фиксированные часы t0); сутки −1 от «сейчас» — возвращено 899: строка возврата 399 "
          "и тестовый подарок R 500 (ревизия 51 Н-3)" % len(want),
          got_days == want and days[d1]["total"]["refunds"] == 2 and days[d1]["total"]["refunded"] == 899
          and days[d1]["total"]["sum"] == days[d1]["total"]["gross"] - 899 and d3 in days and t0d in days, {"got": got_days, "want": want})
    cs = {r["item_code"]: r for r in sl["codes"]}
    sin = M.sales({"svc": "in"})
    check("деньги стенд: позиции при svc=sep — отбор и порядок по сумме БЕЗ служебных (20 / 100000 первым, 99 — только служебная 200000 — последней), "
          "код 37: 5 покупок, служебных 2, в итоге 3, учёток без служебных 1 и служебных 1; тестовый подарок R 212 в позиции не входит (ревизия 51 Н-2, Н-3)",
          sl["codes"][0]["item_code"] == 20 and sl["codes"][-1]["item_code"] == 99 and cs[37]["n"] == 5 and cs[37]["svc_n"] == 2
          and cs[37]["total_n"] == 3 and cs[37]["users"] == 1 and cs[37]["svc_users"] == 1 and cs[79698]["n"] == 9
          and [r["total_s"] for r in sl["codes"]] == sorted([r["total_s"] for r in sl["codes"]], reverse=True) and not sl["codes_capped"],
          [(r["item_code"], r["n"], r["total_s"]) for r in sl["codes"]])
    check("деньги стенд: позиции при svc=in — порядок по сумме всех учёток (99 / 200000 первым)", sin["codes"][0]["item_code"] == 99
          and [r["s"] for r in sin["codes"]] == sorted([r["s"] for r in sin["codes"]], reverse=True), [(r["item_code"], r["s"]) for r in sin["codes"]][:3])
    check("деньги стенд: сверка заказов со стоком своей процедуры (ревизия 51 Н-1) — gp7 12 (без подарков); CashUse 6, сведено 5; причёска 112 сведена "
          "по SaleHair (2 строки, сведена 1), не «только gp7»; только gp7 6, из них в ящике ItemPostbox 1 (109); только сток 1 + причёска 555",
          sl["cross"] == {"gp7_orders": 12, "stock_orders": 6, "hair_orders": 2, "both": 5, "hair_both": 1, "gp7_only": 6, "stock_only": 1,
                          "hair_only": 1, "in_postbox": 1}, sl["cross"])
    sd = {d["day"]: d for d in sl["stock_days"]}
    check("деньги стенд: сток по дням — сутки фиксированных часов t0 (CashUse 6 / 1977, SalePremium 3) и по позициям (SalePremium 79700 ×3, "
          "SaleFunctional 197 — служебная)",
          sd[t0d]["cash_n"] == 6 and sd[t0d]["cash_sum"] == 1977 and sd[t0d]["SalePremium"]["n"] == 3
          and any(x["table"] == "SalePremium" and x["code"] == 79700 and x["n"] == 3 for x in sl["stock_codes"])
          and any(x["table"] == "SaleFunctional" and x["svc_n"] == 1 for x in sl["stock_codes"]), (sd.get(t0d), sl["stock_codes"]))
    ss = M.sales({"who": "service"})
    svc_want = {d: w[1] for d, w in want.items() if w[1]}
    svc_got = {d["day"]: d["cats"]["service"]["n"] for d in ss["days"] if d["cats"]["service"]["n"]}
    check("деньги стенд: продажи только служебных — 4 (три покупки и подарок 207) по своим суткам, CashUse по категории не отбирается (без сверки), "
          "SaleFunctional — 1",
          svc_got == svc_want and sum(svc_got.values()) == 4 and ss["cross"] is None
          and [x["table"] for x in ss["stock_codes"]] == ["SaleFunctional"], (ss["cross"], ss["stock_codes"]))
    check("деньги стенд: период по умолчанию — 30 суток до сегодня по часам SQL-сервера", sl["period"]["to"] in (td_before, td_after)
          and (datetime.datetime.strptime(sl["period"]["to"], "%Y%m%d") - datetime.datetime.strptime(sl["period"]["from"], "%Y%m%d")).days == 29,
          (sl["period"], td_before, td_after))

    # ---- связь учёток
    a = M.accounts({})
    ar = {r["username"]: r for r in a["rows"]}
    check("деньги стенд: связь учёток — 6 строк сайта, Beta ↔ beta (регистр), nogame без игровой, svc1 служебная, логин «12345» ↔ 9005; "
          "игровых без строки сайта — 2 (nosite, recvyes)",
          a["total"] == 6 and ar["Beta"]["Userindex"] == 9002 and ar["nogame"]["cat"] == "nolink" and ar["svc1"]["cat"] == "service"
          and ar["12345"]["Userindex"] == 9005 and a["game_without_site"] == 2 and ar["alpha"]["purchases"] == 17 and ar["alpha"]["refunded"] == 899
          and ar["alpha"]["spent"] == ar["alpha"]["gross"] - 899 and "password" not in ar["alpha"],
          [(r["username"], r["Userindex"], r["cat"]) for r in a["rows"]])
    check("деньги стенд: связь учёток — фильтр «служебные» 1, «без игровой» 1", M.accounts({"who": "service"})["total"] == 1
          and M.accounts({"who": "nolink"})["total"] == 1)

    # ---- маршруты API настоящими функциями
    from core import i18n
    from api import server as _srv
    fs, _p = _route("/api/money/summary")
    fh, _p = _route("/api/money/holds")
    fp, _p = _route("/api/money/purchases")
    check("деньги API: сводка и журнал настоящими функциями маршрутов", fs(_Req({}), None)["purchases"]["total"]["n"] == s_total(M)
          and fp(_Req({"size": "5"}), None)["total"] == 25)
    try:
        fp(_Req({"kind": "nope"}), None)
        code = None
    except _srv.HttpError as ex:
        code = ex.code
    check("деньги API: неверный ввод — 409", code == 409, code)
    i18n.set_lang("en")
    try:
        he = fh(_Req({}), None)
    finally:
        i18n.set_lang("ru")
    check("деньги API EN: подсказки сверки по-английски (hint, hint_why), hint_raw — исходная метка",
          he["holds"] and all(not CYR.search(x["hint"] + x["hint_why"]) for x in he["holds"])
          and {x["order_id"]: x["hint_raw"] for x in he["holds"]}[203] == "неясно", [(x["hint"], x["hint_why"]) for x in he["holds"]][:3])


# «Оплачено, не выдано» на стенде: журналы GameServer и шлюза — подставным вводом-выводом domains/logs.py (logs.IO), путь — белым списком.
#   Ожидания по синтетике BUYS: покупки без подарка, success = 1, старше 10 мин — 101…104, 106…113; сведены CashUse 101, 102, 103, 106, 108 и
#   SaleHair 112; в ящике 109 → не выданы 104, 107, 110, 111, 113 (первый сведённый номер 101 — все сверяемые).
UNDEL = {104: ("A", "журнал GameServer GameServer Buy_"), 107: ("B", "отметка шлюза PURCHASE_UNCONFIRMED"),
         110: ("A", "ответ шлюза в gp7-"), 111: ("B", "сокет GameServer закрыт через 5 мс"), 113: ("unknown", "ответ шлюза найден в gp7-")}


def _gw_line(t, text):
    """Строка журнала шлюза с меткой времени server.js stamp()."""
    return "%s.%03d %s" % (t.strftime("%Y-%m-%d %H:%M:%S"), t.microsecond // 1000, text)


def _undelivered_checks(check, M, names, ldb, now, t0, stamp):
    """Сверка «Оплачено, не выдано»: заказы, итоги по категориям, причины A / B / не установлена по подставным журналам, «неприменима»."""
    from core import config
    from domains import logs
    ms = datetime.timedelta(milliseconds=1)
    sec = datetime.timedelta(seconds=1)
    gp7 = {}                                   # день → строки журнала шлюза
    gs = {}                                    # день → строки Buy_<день>.txt GameServer

    def gw(pid, text, dt=300 * ms):
        gp7.setdefault(stamp[pid].strftime("%Y%m%d"), []).append(_gw_line(stamp[pid] + dt, text))
    t104 = stamp[104]
    gs.setdefault(t104.strftime("%Y%m%d"), []).append("%d Mon %02d Day %02d hou %02d min %02d sec : \tGP7's Response ItemCode is Invalid\t\tAlice\tItemCode\t45"
                                                     % (t104.month, t104.day, t104.hour, t104.minute, t104.second))
    gw(107, 'SEND @@ASTORY_SERVER_LAN_IP@@:50001 bytes=188 command=0x0051 account="svc1" source=sql status=1 order=107 subtype=1 userIndex=3 userNum=1 '
            'requestItemCode=37 itemCode=76451 rewardIndex=null rewardCount=1 requestedPrice=190 price=190 balance=999999 present=0 hex=FB00')
    gw(107, 'PURCHASE_UNCONFIRMED @@ASTORY_SERVER_LAN_IP@@:50001 order=107 account="svc1" subtype=1 itemCode=76451 price=190 afterMs=3 reason=close', 303 * ms)
    gw(110, 'SEND @@ASTORY_SERVER_LAN_IP@@:50002 bytes=188 command=0x0051 account="12345" source=sql status=1 subtype=1 userIndex=9005 userNum=1 '
            'requestItemCode=30 itemCode=30 rewardIndex=null rewardCount=1 requestedPrice=990 price=990 balance=999999 present=0 hex=FB00')
    gw(111, 'SEND @@ASTORY_SERVER_LAN_IP@@:50003 bytes=188 command=0x0051 account="zeta" source=sql status=1 subtype=1 userIndex=12345 userNum=1 '
            'requestItemCode=32 itemCode=76000 rewardIndex=null rewardCount=1 requestedPrice=1890 price=1890 balance=999999 present=0 hex=FB00')
    gw(111, "SOCKET_ERROR @@ASTORY_SERVER_LAN_IP@@:50003 read ECONNRESET", 305 * ms)
    gw(111, "CLOSE @@ASTORY_SERVER_LAN_IP@@:50003", 306 * ms)
    gw(113, 'SEND @@ASTORY_SERVER_LAN_IP@@:50004 bytes=188 command=0x0051 account="svc1" source=sql status=1 subtype=1 userIndex=3 userNum=1 '
            'requestItemCode=99 itemCode=79000 rewardIndex=null rewardCount=1 requestedPrice=200000 price=200000 balance=999999 present=0 hex=FB00')
    gw(113, "CLOSE @@ASTORY_SERVER_LAN_IP@@:50004", 30 * sec)                    # закрыт позже окна 2 с — не B
    gw(113, 'SEND @@ASTORY_SERVER_LAN_IP@@:50005 bytes=188 command=0x0051 account="svc1" source=sql status=1 subtype=1 userIndex=3 userNum=1 '
            'requestItemCode=37 itemCode=30 rewardIndex=null rewardCount=1 requestedPrice=190 price=190 balance=999999 present=0 hex=FB00', 40 * sec)
    files = {}
    for d, ls in gs.items():
        files["%s\\GameServer\\Log\\Log_MGamePremium\\Buy_%s.txt" % (config.STACK_ROOT, d)] = ("\r\n".join(ls) + "\r\n").encode("cp949")
    for d, ls in gp7.items():
        files["%s\\gp7-server\\logs\\gp7-%s.log" % (config.STACK_ROOT, d)] = ("\n".join(sorted(ls)) + "\n").encode("utf-8")
    asked = []

    def fstat(path):
        asked.append(path)
        b = files.get(path)
        return None if b is None else (len(b), 1795000000000, 1795000000000)

    def fread(path, start, length, head=0):
        b = files[path]
        return b[:head], b[start:start + length]
    saved_io = logs.IO
    logs.IO = {"stat": fstat, "read": fread, "list": lambda *a: (None, [])}
    M._scan_cache.clear()
    try:
        u = M.undelivered({})
        u0 = M.undelivered({"logs": "0"})
        ui = M.undelivered({"svc": "in"})
        s = M.summary({})
        lc = ldb(names["L"]).cursor()
        lc.execute("SET IDENTITY_INSERT dbo.GP7PurchaseLog ON")
        lc.execute("INSERT dbo.GP7PurchaseLog (id, user_id, item_code, amount, balance_before, balance_after, success, created_at) VALUES "
                   "(90, 1, 41, 500, 500, 0, 1, DATEADD(day, -40, SYSUTCDATETIME()))")
        lc.execute("SET IDENTITY_INSERT dbo.GP7PurchaseLog OFF")
        try:
            un = M.undelivered({})
        finally:
            lc.execute("DELETE dbo.GP7PurchaseLog WHERE id = 90")
        # ★ ревизия 53 С-1: фильтр по датам / учёткам не сдвигает границу «первый номер в CashUse» (сутки d3 — только 104 и 111, оба не выданы)
        d3 = (t0 - 3 * D_).strftime("%Y%m%d")
        ud3 = M.undelivered({"from": d3, "to": d3})
        upl = M.undelivered({"who": "player"})
        # ★ ревизия 53 М-4: свежий заказ (моложе 10 мин) не сверяется; с minutes=1 — сверяется
        lc.execute("SET IDENTITY_INSERT dbo.GP7PurchaseLog ON")
        lc.execute("INSERT dbo.GP7PurchaseLog (id, user_id, item_code, amount, balance_before, balance_after, success, created_at) VALUES "
                   "(120, 1, 41, 300, 300, 0, 1, DATEADD(minute, -3, SYSUTCDATETIME()))")
        lc.execute("SET IDENTITY_INSERT dbo.GP7PurchaseLog OFF")
        try:
            ufresh, ufresh1 = M.undelivered({"logs": "0"}), M.undelivered({"logs": "0", "minutes": "1"})
        finally:
            lc.execute("DELETE dbo.GP7PurchaseLog WHERE id = 120")
        # ★ ревизия 53 Н-1: файл журнала шлюза «прочитан не целиком» (предел logs.SCAN_FILE_MAX меньше файла на байт) — у «не установлена»
        #   пометка; logs.py не правится — подменяется только его предел на время проверки
        M._scan_cache.clear()
        saved_max = logs.SCAN_FILE_MAX
        logs.SCAN_FILE_MAX = len(files["%s\\gp7-server\\logs\\gp7-%s.log" % (config.STACK_ROOT, stamp[113].strftime("%Y%m%d"))]) - 1
        try:
            utr = M.undelivered({}, "selftest_r53")
        finally:
            logs.SCAN_FILE_MAX = saved_max
            M._scan_cache.clear()
    finally:
        logs.IO = saved_io
        M._scan_cache.clear()
    got = {r["id"]: (r["reason"], r["reason_why"] or "") for r in u["rows"]}
    check("деньги стенд: «Оплачено, не выдано» — заказы 113, 111, 110, 107, 104 (новые сверху): без строки CashUse / SaleHair и без ящика (109 в ящике "
          "— не в списке, в ящике 1), подарки и строка возврата не считаются, первый сведённый номер 101",
          [r["id"] for r in u["rows"]] == [113, 111, 110, 107, 104] and u["in_postbox"] == 1 and u["cutoff"]["id"] == 101
          and u["cutoff"]["local"] == stamp[101] and all(r["applicable"] for r in u["rows"]) and not u["capped"], ([r["id"] for r in u["rows"]], u["cutoff"]))
    tc = u["totals"]["cats"]
    check("деньги стенд: «Оплачено, не выдано» — итоги: игроки 3 / 12880 (104, 110, 111), служебные 2 / 200190 (107, 113) отдельно и не в общем "
          "итоге; svc=in — общий итог 5 / 213070; сводка — та же таблица «списано, но не выдано»",
          (tc["player"]["n"], tc["player"]["sum"], tc["service"]["n"], tc["service"]["sum"], tc["nolink"]["n"]) == (3, 12880, 2, 200190, 0)
          and (u["totals"]["total"]["n"], u["totals"]["total"]["sum"]) == (3, 12880) and not u["totals"]["service_in_total"]
          and (ui["totals"]["total"]["n"], ui["totals"]["total"]["sum"]) == (5, 213070) and s["undelivered"]["totals"] == u["totals"]
          and s["undelivered"]["in_postbox"] == 1, (tc, ui["totals"]["total"], s["undelivered"]))
    check("деньги стенд: причины по журналам — A по Buy_<день>.txt GameServer «ItemCode is Invalid» (104), B по отметке шлюза PURCHASE_UNCONFIRMED "
          "(107, номер в строке), A по ответу шлюза с кодом 30 < 20551 без номера в строке (110 — сопоставлен по учётке «12345», сумме и времени), "
          "B — SOCKET_ERROR того же сокета через 5 мс (111), не установлена — сокет закрыт через 30 с, позже окна 2 с (113); чужой ответ на 190 "
          "через 40 с к 107 не привязан",
          {k: v[0] for k, v in got.items()} == {k: v[0] for k, v in UNDEL.items()} and all(got[k][1].startswith(v[1]) for k, v in UNDEL.items())
          and u["by_reason"] == {"A": 2, "B": 2, "unknown": 1, "na": 0} and not u["errors"], (got, u["errors"]))
    check("деньги стенд: журналы читаются только по белому списку — Buy_<день>.txt копий GameServer (Log_MGamePremium) и gp7-<день>.log шлюза; "
          "журнал шлюза — только за дни заказов, не решённых по журналу GameServer",
          asked and all(p.startswith(config.STACK_ROOT + "\\") and (("\\Log\\Log_MGamePremium\\Buy_" in p) or ("\\gp7-server\\logs\\gp7-" in p)) for p in asked)
          and {re.search(r"gp7-(\d{8})\.log$", p).group(1) for p in asked if "\\gp7-server\\" in p}
          == {stamp[k].strftime("%Y%m%d") for k in (107, 110, 111, 113)}, asked)
    check("деньги стенд: logs=0 — те же заказы и итоги без чтения журналов (причина — «журналы не разбирались»)",
          [r["id"] for r in u0["rows"]] == [r["id"] for r in u["rows"]] and u0["totals"] == u["totals"] and all(r["reason"] is None for r in u0["rows"])
          and not u0["logs"])
    nr = {r["id"]: r for r in un["rows"]}
    check("деньги стенд: заказ 90 раньше первого сведённого номера 101 — «сверка по номеру неприменима» (номер в пояснении), в итогах отдельно "
          "(игроки 1 / 500), сверяемые итоги прежние",
          90 in nr and nr[90]["reason"] == "na" and "№101" in nr[90]["reason_why"] and un["totals"]["cats"]["player"]["na_n"] == 1
          and un["totals"]["cats"]["player"]["na_sum"] == 500 and un["totals"]["cats"]["player"]["n"] == 3 and un["by_reason"]["na"] == 1,
          (un["totals"], nr.get(90)))
    check("деньги стенд (ревизия 53 С-1): фильтр по суткам d3 (104, 111) — граница по всем покупкам (№101), заказы сверяемые, игроки 2 / 11890; "
          "учётки player — та же граница, 104 / 110 / 111",
          ud3["cutoff"]["id"] == 101 and [r["id"] for r in ud3["rows"]] == [111, 104] and all(r["applicable"] for r in ud3["rows"])
          and (ud3["totals"]["cats"]["player"]["n"], ud3["totals"]["cats"]["player"]["sum"], ud3["totals"]["cats"]["player"]["na_n"]) == (2, 11890, 0)
          and upl["cutoff"]["id"] == 101 and [r["id"] for r in upl["rows"]] == [111, 110, 104] and all(r["applicable"] for r in upl["rows"]),
          (ud3["cutoff"], [(r["id"], r["applicable"]) for r in ud3["rows"]], upl["cutoff"]))
    check("деньги стенд (ревизия 53 М-4): заказ 120 моложе 10 мин не сверяется; с minutes=1 — в списке",
          120 not in [r["id"] for r in ufresh["rows"]] and 120 in [r["id"] for r in ufresh1["rows"]], ([r["id"] for r in ufresh1["rows"]],))
    tr = {r["id"]: r for r in utr["rows"]}
    check("деньги стенд (ревизия 53 Н-1): журнал шлюза прочитан не целиком — у «не установлена» (113) пометка «журнал прочитан не целиком», "
          "остальные причины прежние; бюджет чтения — на пользователя запроса (ревизия 53 Н-2)",
          tr[113]["reason"] == "unknown" and tr[113]["reason_why"].startswith("журнал прочитан не целиком (gp7-")
          and {k: v["reason"] for k, v in tr.items()} == {k: v[0] for k, v in UNDEL.items()} and "selftest_r53" in logs._budget,
          (tr[113]["reason_why"], sorted(k for k in logs._budget if isinstance(k, str))[:6]))
    from core import i18n
    fu, _p = _route("/api/money/undelivered")
    saved_io = logs.IO
    logs.IO = {"stat": fstat, "read": fread, "list": lambda *a: (None, [])}
    i18n.set_lang("en")
    try:
        ue = fu(_Req({}), None)
    finally:
        i18n.set_lang("ru")
        logs.IO = saved_io
        M._scan_cache.clear()
    check("деньги API EN: /api/money/undelivered — пояснения причин по-английски (имена файлов и коды — данные)",
          ue["rows"] and all(not CYR.search(x["reason_why"] or "") for x in ue["rows"]) and len(ue["rows"]) == 5, [x["reason_why"] for x in ue["rows"]][:3])


def s_total(M):
    """Общий итог сводки по умолчанию (для сверки с маршрутом)."""
    return M.summary({})["purchases"]["total"]["n"]


# ---------------------------------------------------------------- живая dev

LIVE_UNDEL = {}                       # итог живой сверки «Оплачено, не выдано» с ПК — для сравнения со службой на сервере
KNOWN_ORPHANS = {12495: "A", 12496: "A", 12526: "A", 15068: "B"}   # разбор research_gp7_orphan_orders_20261121.md (A — код, B — обрыв)


def _live_undelivered(check, M, db):
    """Живая сверка «Оплачено, не выдано» (только чтение): заказы = независимому SQL, первый номер, известные 4 заказа и их причины."""
    with db.GameReader("asdastorylogin") as g:
        ind = g.one("SELECT COUNT(*) AS n, SUM(p.amount) AS s FROM dbo.GP7PurchaseLog p WHERE p.success = 1 AND p.amount > 0 AND p.created_at < "
                    "DATEADD(minute, -10, SYSUTCDATETIME()) AND NOT EXISTS (SELECT 1 FROM dbo.GP7GiftLog x WHERE x.order_id = p.id) AND NOT EXISTS "
                    "(SELECT 1 FROM AsdaStoryOp.dbo.CashUse c WHERE c.Orderidx = p.id) AND NOT EXISTS (SELECT 1 FROM AsdaStoryOp.dbo.SaleHair h WHERE "
                    "h.Orderidx = p.id) AND NOT EXISTS (SELECT 1 FROM Joy1.dbo.ItemPostbox b WHERE b.Orderidx = p.id)")
        first = g.one("SELECT MIN(p.id) AS i FROM dbo.GP7PurchaseLog p WHERE p.success = 1 AND p.amount > 0 AND (EXISTS (SELECT 1 FROM "
                      "AsdaStoryOp.dbo.CashUse c WHERE c.Orderidx = p.id) OR EXISTS (SELECT 1 FROM AsdaStoryOp.dbo.SaleHair h WHERE h.Orderidx = p.id))")["i"]
    u = M.undelivered({})
    LIVE_UNDEL["u"] = u
    t = u["totals"]
    allc = {k: sum(t["cats"][c][k] for c in M.WHO) for k in ("n", "sum", "na_n", "na_sum")}
    check("живое: «Оплачено, не выдано» — заказов %d = независимому SQL (NOT EXISTS CashUse / SaleHair / ItemPostbox, без подарков, старше 10 мин), "
          "сумма = SUM; первый номер в CashUse — №%s" % (ind["n"], first),
          u["total"] == ind["n"] and allc["n"] + allc["na_n"] == ind["n"] and allc["sum"] + allc["na_sum"] == (ind["s"] or 0)
          and (u["cutoff"] or {}).get("id") == first and not u["capped"], (u["total"], allc, ind, u["cutoff"]))
    rr = {r["id"]: r for r in u["rows"]}
    check("живое: известные заказы разбора research_gp7_orphan_orders — 12495, 12496, 12526 → A (журнал GameServer / шлюза), 15068 → B (обрыв "
          "сокета); у каждого сверяемого заказа есть пояснение, ошибок чтения журналов нет",
          all(k in rr and rr[k]["reason"] == v for k, v in KNOWN_ORPHANS.items()) and all(r["reason_why"] for r in u["rows"]) and not u["errors"],
          ({k: (rr[k]["reason"], rr[k]["reason_why"]) for k in KNOWN_ORPHANS if k in rr}, u["errors"]))
    check("живое: «Оплачено, не выдано» — служебные отдельно и не в общем итоге; заказы до первого номера — «неприменима» (%d)" % u["by_reason"]["na"],
          not t["service_in_total"] and t["total"]["n"] == t["cats"]["player"]["n"] + t["cats"]["nolink"]["n"]
          and u["by_reason"]["na"] == allc["na_n"] and all(r["reason"] == "na" for r in u["rows"] if not r["applicable"]), (t, u["by_reason"]))

def live(check):
    """Только чтение живой dev (asda_admin) и службы на сервере. Ничего не пишет."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db
    from domains import money as M
    if config.get().on_server:
        return check("живой самотест А6.2 — с ПК", True)
    perm = {}
    with db.GameReader("asdastorylogin") as g:
        for o in ("dbo.GP7PurchaseLog", "dbo.GP7GiftLog", "dbo.GP7Balance"):
            perm[o] = g.one("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT') AS p", (o,))["p"]
        for col in ("id", "username", "role", "password"):
            perm["[user]." + col] = g.one("SELECT HAS_PERMS_BY_NAME('dbo.[user]', 'OBJECT', 'SELECT', ?, 'COLUMN') AS p", (col,))["p"]
        direct = g.one("SELECT COUNT(*) AS n, SUM(CASE WHEN success = 1 AND amount > 0 THEN amount ELSE 0 END) AS gross, SUM(CASE WHEN success = 1 "
                       "AND amount < 0 THEN -amount ELSE 0 END) AS rrows FROM dbo.GP7PurchaseLog")
        trs = g.one("SELECT ISNULL(SUM(p.amount), 0) AS s FROM dbo.GP7PurchaseLog p JOIN dbo.GP7GiftLog x ON x.order_id = p.id WHERE x.state = 'R' "
                    "AND x.test_mode = 1 AND p.success = 1 AND p.amount > 0")["s"]
        direct["s"] = (direct["gross"] or 0) - (direct["rrows"] or 0) - trs
        ngift = g.one("SELECT COUNT(*) AS n FROM dbo.GP7GiftLog")["n"]
        nhang = g.one("SELECT COUNT(*) AS n FROM dbo.GP7GiftLog WHERE state = 'H' AND created_at < DATEADD(minute, -10, SYSUTCDATETIME())")["n"]
        nuser = g.one("SELECT COUNT(id) AS n FROM dbo.[user]")["n"]
        shift = M._shift(g)
        today = g.one("SELECT CONVERT(char(8), SYSDATETIME(), 112) AS d")["d"]
        f30 = (datetime.datetime.strptime(today, "%Y%m%d") - datetime.timedelta(days=29)).strftime("%Y%m%d")
        n30 = g.one("SELECT COUNT(*) AS n, SUM(amount) AS s FROM dbo.GP7PurchaseLog WHERE success = 1 AND amount > 0 AND created_at >= "
                    "DATEADD(minute, ?, CONVERT(datetime2, ?, 112))", (-shift, f30))
    stock = {}
    with db.GameReader("asdastoryop") as op:
        for t in ("CashUse", "SalePremium", "SaleFunctional", "SaleHair"):
            perm["AsdaStoryOp." + t] = op.one("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT') AS p", ("dbo." + t,))["p"]
            stock[t] = op.one("SELECT COUNT(*) AS n FROM %s" % t)["n"]
    with db.GameReader("joy1") as j:
        for t in ("dbo.Charinfo", "dbo.Item"):
            perm["Joy1." + t] = j.one("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT') AS p", (t,))["p"]
    with db.GameReader("joylog1") as lg:
        perm["JoyLog1.dbo.EventGainItem"] = lg.one("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT') AS p", ("dbo.EventGainItem",))["p"]
    check("живое (asda_admin): SELECT на GP7PurchaseLog / GP7GiftLog / GP7Balance, [user].id / username / role, сток AsdaStoryOp, Joy1 Charinfo / Item, "
          "JoyLog1 EventGainItem — есть (SQL-установка прав не нужна); [user].password — нет (DENY)",
          perm.pop("[user].password") == 0 and all(v == 1 for v in perm.values()), perm)
    s = M.summary({})
    si = M.summary({"svc": "in"})
    cats = s["purchases"]["cats"]
    check("живое: итоги покупок — сумма категорий = COUNT(*) %d и итого %d по GP7PurchaseLog (списано − строки возврата − тестовые R); svc=in — общий итог = таблице; по умолчанию служебные (%d) "
          "не в общем итоге" % (direct["n"], direct["s"] or 0, cats["service"]["n"]),
          sum(cats[c]["n"] for c in M.WHO) == direct["n"] and sum(cats[c]["sum"] for c in M.WHO) == direct["s"]
          and sum(cats[c]["gross"] for c in M.WHO) == (direct["gross"] or 0) and sum(cats[c]["refunded"] for c in M.WHO) == (direct["rrows"] or 0) + trs
          and si["purchases"]["total"]["n"] == direct["n"] and s["purchases"]["total"]["n"] == direct["n"] - cats["service"]["n"]
          and all(e.startswith("карта шлюза") for e in s["errors"]), (cats, direct, s["errors"]))
    check("живое: testFixedBalance шлюза прочитан (на dev > 0 — правка баланса игроку не видна)", isinstance(s["test_fixed_balance"], int), s["test_fixed_balance"])
    st = {x["table"]: x["n"] for x in s["stock"]}
    check("живое: сток рядом — строк CashUse / SalePremium / SaleFunctional / SaleHair = COUNT(*)", st == stock, (st, stock))
    p = M.purchases({"size": "20"})
    ids = [r["id"] for r in p["rows"]]
    check("живое: журнал покупок — total = COUNT(*) (%d), первая страница 20 строк новые сверху, у строк категория и позиция" % direct["n"],
          p["total"] == direct["n"] and len(ids) == min(20, direct["n"]) and ids == sorted(ids, reverse=True)
          and all(r["cat"] in M.WHO and r["pos"]["code"] == r["item_code"] for r in p["rows"]), (p["total"], p["errors"]))
    gf = M.gifts({})
    hs = M.holds({})
    check("живое: подарки = COUNT(*) GP7GiftLog (%d), висящие старше 10 мин = COUNT (%d), у каждого подсказка сверки" % (ngift, nhang),
          gf["total"] == ngift and len(hs["holds"]) == nhang and s["hanging"] == nhang and all(h["hint"] for h in hs["holds"]) and not hs["errors"],
          (gf["total"], len(hs["holds"]), hs["errors"]))
    sl = M.sales({})
    cr = sl["cross"] or {}
    check("живое: сверка заказов со стоком своей процедуры — сведённые CashUse + SaleHair + только gp7 = заказам gp7 (%s)" % cr,
          cr and cr["both"] + cr["hair_both"] + cr["gp7_only"] == cr["gp7_orders"] and cr["in_postbox"] is not None, cr)
    check("живое: продажи за 30 суток — покупок по дням (все категории) = COUNT %d, сумма = SUM" % n30["n"],
          sum(d["cats"][c]["n"] for d in sl["days"] for c in M.WHO) == n30["n"] and sum(d["cats"][c]["gross"] for d in sl["days"] for c in M.WHO)
          == (n30["s"] or 0) and sl["cross"] is not None, (n30, sl["errors"]))
    a = M.accounts({"size": "5"})
    check("живое: связь учёток — total = COUNT [user] (%d), без password в строках" % nuser, a["total"] == nuser and all("password" not in r for r in a["rows"])
          and a["game_without_site"] is not None, (a["total"], a["errors"]))
    _live_undelivered(check, M, db)
    probe = ("import sys\nsys.path.insert(0, '.')\nfrom domains import money as M\nimport os\n"
             "G = M.reconcile()\ns = M.summary({})\nh = M.holds({})\nu = M.undelivered({})\n"
             "print('MNUNDEL total=%d A=%d B=%d unk=%d na=%d err=%d' % (u['total'], u['by_reason']['A'], u['by_reason']['B'], u['by_reason']['unknown'], "
             "u['by_reason']['na'], len(u['errors'])))\n"
             "print('MNPROBE ext=%s n=%d hold=%d err=%d herr=%d' % (os.path.basename(os.path.dirname(G.LOADED_FROM)), "
             "sum(s['purchases']['cats'][c]['n'] for c in M.WHO), len(h['holds']), len(s['errors']), len(h['errors'])))\n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        r = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                            r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"MNPROBE ext=(\w+) n=(\d+) hold=(\d+) err=(\d+) herr=(\d+)", out)
    check("служба на сервере (SSH): сверка подарков из ext/gift_reconcile.py архива, итоги = живой COUNT, висящие = COUNT, без ошибок",
          bool(mm) and mm.group(1) == "ext" and int(mm.group(2)) >= direct["n"] and int(mm.group(3)) == nhang and mm.group(4) == "0" and mm.group(5) == "0",
          out[-600:])
    mu = re.search(r"MNUNDEL total=(\d+) A=(\d+) B=(\d+) unk=(\d+) na=(\d+) err=(\d+)", out)
    lu = LIVE_UNDEL.get("u") or {}
    check("служба на сервере (SSH): «Оплачено, не выдано» читает журналы стойки локально — те же число заказов и причины, что с ПК, без ошибок",
          bool(mu) and lu and int(mu.group(1)) == lu["total"] and [int(mu.group(i)) for i in range(2, 6)] == [lu["by_reason"][k] for k in M.REASONS]
          and mu.group(6) == "0", (out[-400:], lu.get("by_reason")))
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/money/summary" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/money/summary без входа — 401", code == 401, code)
    # ★ А6.9 (22.11): корректировка баланса gp7 — только чтение и предпросмотр @dry = 1 (никаких корректировок на живой)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_gp7adjust_a6
    selftest_gp7adjust_a6.live(check)
