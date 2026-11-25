# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_econ_a6.py — самотест шага А6.3 «Экономика: золото» (21.11.2026; domains/econ.py, sql/adminc_18_econ.sql, /api/econ/*,
web/econ.js, консоль econ, операция econ.snapshot, core/sched DAILY).

offline(check)  — каталог источников по реверсу (12 Money* + Trade/PersonalStore Gold*: знак, владелец строки, не считающиеся), отказы ввода
                  до базы (без «; »), права econ.view / econ.snapshot (owner, admin), маршруты, операция и её место в планировщике,
                  таблица редкого (разбор), SQL модуля без русских букв и без «SELECT *», переводы EN (shadowed_translations = 0), веб без
                  innerHTML и с EN всех подписей, консоль (неизвестный ключ, ключ без значения, неизвестное действие — отказ без базы,
                  --help ничего не делает), выкладка (adminc_18 после adminc_17, права в adminc_10, QUOTED_IDENTIFIER отдельным пакетом),
                  импорт без побочных эффектов.
sandbox(check, ldb) — СВОИ базы LocalDB: AsdaAdmin (настоящие adminc_02 + adminc_18 дважды), Joy1 (Item, Charinfo по снимку живых схем,
                  Exitem, ItemPostBox, gifts, adm.ItemTaken / ItemLedger), JoyLog1 (журналы золота, ac.other), AsdaStoryLogin (GP7GiftLog).
                  Синтетика: игроки, служебная ≤ 5000, удалённый персонаж; снимок 1 → журналы (покупка, продажа против знака, обмен From/To
                  с владельцем Tuserindex, награда + её дубль EpisodeEventGold, ItemEvent золота и не золота) и «золото с моба» без журнала →
                  снимок 2. Сверка: сумма снимка = SUM(Amount) Item, строки персонажей = сумме, потоки по источникам и категориям, знак,
                  служебные отдельно и в итоге, неучтённое по категориям и персонажам, богатейшие, редкое на руках (против held_counts),
                  P59, таблица вне каталога, нет таблицы — строка ошибки, операция econ.snapshot (журнал, отказ параметров). Все запросы к
                  игровым базам — чтение, без русских букв.
live(check)     — живая dev: права asda_admin на adm.EconDaily* (INSERT да, UPDATE и DELETE нет), чтение игровых баз = COUNT / SUM, снимок
                  пишет ТОЛЬКО AsdaAdmin и равен SUM(Amount), неучтённое читается, /api/econ/summary без входа — 401.
Побочных эффектов при импорте нет.
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
CYR = re.compile("[А-Яа-яЁё]")
MONEY12 = ("MoneyBuy", "MoneyCampReward", "MoneyCraft", "MoneyExchange", "MoneyExchangeBuy", "MoneyExchangeFee", "MoneyReward", "MoneySell",
           "MoneyTelePort", "MoneyTransferOption", "MoneyUse", "MoneyWasteBasket")      # 12 таблиц Money* живой JoyLog1 (sys.tables 21.11)
# знак и владелец по реверсу (отчёт §А6.3 шаг 1 а) — каталог модуля должен совпасть
EXPECT = {"MoneyBuy": "-u", "MoneySell": "+u", "MoneyCraft": "-u", "MoneyExchangeBuy": "-u", "MoneyExchangeFee": "-u", "MoneyReward": "+u",
          "MoneyTelePort": "-u", "MoneyUse": "-u", "MoneyWasteBasket": "+u", "MoneyCampReward": "+u", "TradeGoldFrom": "-u", "TradeGoldTo": "+t",
          "TradeShellGoldFrom": "-u", "TradeShellGoldTo": "+t", "PersonalStoreGoldFrom": "+u", "PersonalStoreGoldTo": "-t", "CampShopUseGold": "-u",
          "TradeItemFrom": "-u", "TradeitemTo": "+t", "ItemEvent": "±u", "AdminitemLog": "±u",
          "ItemRefine": "-u", "TransferOption": "-u", "OpGameMoneyAdd": "+u", "CharEventCreate": "+u"}     # ★ ревизия 52 С-1, Н-1, Н-2


def _refused(fn):
    """Текст отказа OpRefused или None."""
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _route(path):
    """Маршрут GET по пути → (функция, право)."""
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


REFUSALS = [  # (функция проверки, строка запроса) — отказ ДО базы
    ("flows", {"from": "2026-11-01"}), ("flows", {"to": "20261131"}), ("flows", {"from": "20261122", "to": "20261121"}),
    ("flows", {"from": "20250101", "to": "20261121"}), ("flows", {"svc": "all"}), ("flows", {"source": "Pick"}),
    ("richest", {"n": "0"}), ("richest", {"n": "201"}), ("richest", {"n": "x"}), ("rare", {"n": "-1"}), ("rare", {"svc": "x"}),
    ("unaccounted", {"id": "0"}), ("unaccounted", {"id": "abc"}), ("summary", {"svc": "both"})]


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n, ops, sched
    from domains import econ as E
    import domains
    domains.load_all()

    # ---- каталог по реверсу
    keys = {s["key"] for s in E.SOURCES} | {s["key"] for s in E.SKIPPED}
    check("экономика: все 12 таблиц Money* в каталоге (10 считаются, MoneyExchange и MoneyTransferOption — «писателя нет, знак не снят»)",
          all(t in keys for t in MONEY12) and {s["key"] for s in E.SKIPPED if s["why"] == "nowriter"} >= {"MoneyExchange", "MoneyTransferOption"}
          and sum(1 for s in E.SOURCES if s["key"].startswith("Money")) == 10, sorted(set(MONEY12) - keys))
    got = {s["key"]: s["sign"] + s["owner"] for s in E.SOURCES}
    check("экономика: знак и владелец строки каждого источника = реверсу процедур Joy1 (…To обмена и лавки — Tuserindex)", got == EXPECT,
          {k: (got.get(k), v) for k, v in EXPECT.items() if got.get(k) != v})
    kinds = {s["key"]: (s.get("kind", "ba"), s.get("code"), s.get("extra")) for s in E.SOURCES}
    check("экономика (ревизия 52): перенос опций — −Gm (без было/стало), создание персонажа — +1 на CharEventCreate, OpGameMoneyAdd — ItemEvent "
          "Code 10551 «Clan Event GM Gain» с Amount = суммой, алхимия ItemRefine — было → стало Code 20551; правки панели — источник adm.audit",
          kinds["TransferOption"][0] == "neg" and kinds["CharEventCreate"][0] == "one" and kinds["OpGameMoneyAdd"] == ("amt", 10551, "State = 'Clan Event GM Gain'")
          and kinds["ItemRefine"] == ("ba", True, None) and E._delta(E.SRC["TransferOption"]) == "(-CAST(Gm AS BIGINT))"
          and E.PANEL_EXACT == ("gold.set", "gold.set.undo") and {u[0] for u in E.UNLOGGED} >= {"pick", "gm", "limitation", "csused", "panel_char"}, kinds)
    check("экономика: дубль EpisodeEventGold и закомментированный PickGold — не считаются; общие журналы предметов — только Code 20551",
          {s["key"]: s["why"] for s in E.SKIPPED if s["key"] in ("EpisodeEventGold", "PickGold")} == {"EpisodeEventGold": "dup", "PickGold": "off"}
          and all(E.SRC[k].get("code") for k in ("ItemEvent", "AdminitemLog", "TradeItemFrom", "TradeitemTo")))

    # ---- отказы ввода
    why = [_refused(lambda f=f, q=q: E.check_input(q, f)) for f, q in REFUSALS]
    check("экономика: неверный ввод — отказ до базы (%d случаев: даты, период > 366 суток, служебные, источник, строк, номер снимка)" % len(REFUSALS),
          all(why), [(REFUSALS[i], w) for i, w in enumerate(why) if not w])
    check("экономика: тексты отказов без «; »", all("; " not in w for w in why if w), [w for w in why if w and "; " in w])
    check("экономика: flows проверяет ввод до обращения к базе (подставной базы нет — всё равно отказ)",
          _refused(lambda: E.flows({"from": "20261122", "to": "20261121"})) == "дата «с» позже даты «по»")

    # ---- права, маршруты, операция, планировщик
    roles = ("owner", "admin", "gm", "support")
    check("экономика: права econ.view и econ.snapshot — owner и admin (gm и support — нет)",
          {r for r in roles if auth.can(r, "econ.view")} == {"owner", "admin"} and {r for r in roles if auth.can(r, "econ.snapshot")} == {"owner", "admin"})
    paths = ("/api/econ/summary", "/api/econ/flows", "/api/econ/richest", "/api/econ/rare", "/api/econ/unaccounted")
    rt = {p: _route(p) for p in paths}
    check("экономика: маршруты %s — GET, право econ.view" % ", ".join(paths), all(fn and perm == "econ.view" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})
    o = ops.REGISTRY.get("econ.snapshot")
    check("экономика: операция econ.snapshot — право econ.snapshot, задание службы (повтор на год), необратима",
          o and o.perm == "econ.snapshot" and o.schedule_runner == "service" and o.schedule_repeat_days == 366 and not o.reversible)
    check("экономика: служба снимает снимок сама раз в сутки (core/sched DAILY econ.snapshot 00:05), рейтинг чести на месте",
          ("econ.snapshot", datetime.time(0, 5)) in sched.DAILY and ("camp.rank_rebuild", datetime.time(6, 10)) in sched.DAILY)
    check("экономика: у задания снимка параметров нет — лишний параметр отказ", _refused(lambda: o.schedule_check(None, {"x": 1})) == "у снимка золота параметров нет")

    # ---- таблица редкого
    g = E.parse_grade("# комментарий\n7722-7725\n61785\n\nплохо\n9-3\n100 # хвост\n")
    check("экономика: таблица редкого P11 — коды и диапазоны «от-до», «#» — комментарий, неверные строки пропускаются",
          g == {7722, 7723, 7724, 7725, 61785, 100}, sorted(g))

    # ---- SQL модуля
    src = open(os.path.join(ROOT, "domains", "econ.py"), encoding="utf-8").read()
    code = re.sub(r'"""(?:[^"]|"(?!""))*"""', "", src)
    lits = re.findall(r'"((?:SELECT|FROM|WHERE|CASE|SUM|COUNT|INSERT|SET NOCOUNT|\(CAST)[^"]*)"', code)
    check("экономика: в тексте SQL модуля нет русских букв и «SELECT *» (%d строк SQL)" % len(lits),
          lits and not any(CYR.search(s) or "select *" in s.lower() for s in lits), [s[:80] for s in lits if CYR.search(s)][:3])
    check("экономика: запись — только AsdaAdmin (INSERT в тексте модуля — только adm.EconDaily и adm.EconDailyChar)",
          sorted(set(re.findall(r"INSERT (\S+)", code))) == ["adm.EconDaily", "adm.EconDailyChar"], re.findall(r"INSERT (\S+)", code))

    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [w for w in why if w] + [
            "журнал золота MoneyBuy не прочитан: нет подключения к joylog1: Login timeout expired", "журналы JoyLog1 не прочитаны: x",
            "золото на руках не прочитано: запрос к Joy1: x", "таблица редкого не прочитана: HostError", "таблица редкого пуста",
            "места хранения Exitem не прочитаны: запрос к Joy1: x", "предметы на руках не прочитаны: x", "общий счёт «на руках» не прочитан: нет связи с Joy1",
            "виды P59 (ac.other 4 и 5) не найдены в каталоге журнала", "журнал P59 не прочитан: x", "снимки золота не прочитаны: AsdaAdmin: x",
            "неучтённое по персонажам не посчитано: x", "таблицы вне каталога не проверены: x", "неверное имя таблицы x",
            "снимка №7 нет среди последних 60 или он первый (неучтённое считается от предыдущего снимка)", "у снимка золота параметров нет",
            "Экономика: суточный снимок золота", "снимок золота на руках: всего 10 (игроки 7 у 2 персонажей, служебные 3 у 1)",
            "пишется только база панели AsdaAdmin (adm.EconDaily и adm.EconDailyChar), игровые базы только читаются",
            "предыдущий снимок №3 — 2026-11-21 00:05:00", "снимок золота №4: всего 10 (игроки 7, служебные 3)",
            "журнал панели не прочитан: AsdaAdmin: x", "правка панели №5211: было и стало не прочитаны"] + list(E.WHY.values())
        miss = [x for x in ru if CYR.search(i18n.tr(x))]
        check("экономика EN: отказы, ошибки чтения (причина — вложенным переводом), операция и причины «не считается» — без русских слов (%d строк)"
              % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("экономика: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])

    # ---- веб
    js = open(os.path.join(ROOT, "web", "econ.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("экономика веб: раздел #/econ «Экономика: золото» с правом econ.view, значок itemexchange (окна игры), маршрут viewEcon, скрипт после acjournal.js",
          '["#/econ", "Экономика: золото", "econ.view", "itemexchange"]' in app and 'case "econ": return viewEcon(my);' in app
          and "/econ.js" in idx and idx.index("/acjournal.js") < idx.index("/econ.js"))
    check("экономика веб: без innerHTML, данные — текстовыми узлами (acText / itemLine / acChar), State журнала — acText, кнопка снимка — по праву econ.snapshot",
          "innerHTML" not in js and "acText(y.sub)" in js and "itemLine(" in js and 'can("econ.snapshot")' in js and "T(x." not in js and "T(y." not in js)
    check("экономика веб: даты уходят ГГГГММДД (acDay), служебные — переключатель svc=in", "acDay(" in js and 'svcIn.checked ? "in" : "sep"' in js)
    sys.path.insert(0, os.path.join(HERE))
    labels = re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|b|div)", (?:null|\{[^}]*\}), "([^"]+)"', js)
    labels += re.findall(r'\["([^"]+)", \w+ =>', js) + re.findall(r'T\("([^"]+)"', js) + re.findall(r'placeholder: "([^"]+)"', js)
    for m in re.findall(r"const EC_\w+ = \{([^}]*)\}", js, re.S):
        labels += re.findall(r':\s*"([^"]+)"', m)
    labels += ["по персонажам", "по персонажам ✓"]
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted({x for x in labels if x not in have and CYR.search(x)})
    check("экономика веб EN: у всех подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(set(labels)), not lack and len(set(labels)) > 80, lack[:8])
    rx = r'(?:^|[{,])\s*"((?:[^"\\]|\\.)+)":\s*"'
    blk = wi[wi.index("// ★ А6.3"):]
    kb = re.findall(rx, blk, re.M)
    earlier = set(re.findall(rx, wi[:wi.index("// ★ А6.3")], re.M))
    check("экономика веб EN: новые ключи web/i18n.js не повторяют прежние и друг друга (%d ключей)" % len(kb),
          len(kb) == len(set(kb)) and not set(kb) & earlier, sorted(set(kb) & earlier)[:5])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "econ.js")], capture_output=True, timeout=60)
        check("экономика: node --check web/econ.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("экономика: node --check web/econ.js (node не запустился)", False, str(ex))

    # ---- консоль, выкладка, импорт
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "econ"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("flows", "--bogus")
    c2, o2 = con("richest", "--n")
    c3, o3 = con("nope")
    c4, o4 = con("snapshot", "extra")
    c5, o5 = con("flows", "--from", "20261122", "--to", "20261121")
    check("экономика консоль: неизвестный ключ, ключ без значения, неизвестное действие, лишнее слово, неверный период — отказ без запроса к базе",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3
          and c4 and "неизвестный аргумент extra" in o4 and c5 and "позже" in o5, (o1[-200:], o2[-200:], o3[-200:], o4[-200:], o5[-200:]))
    hp = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60, cwd=ROOT,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
    ho = hp.stdout.decode("utf-8", "replace")
    check("экономика консоль: --help печатает справку с командой econ (ничего не делает)", hp.returncode == 0 and "  econ …" in ho
          and "unaccounted [--id N]" in ho)
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read().replace("\r\n", "\n")
    ver = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    s18 = open(os.path.join(ROOT, "sql", "adminc_18_econ.sql"), encoding="utf-8").read()
    check("экономика выкладка: adminc_18_econ после adminc_17 в AsdaAdmin; проверка прав adminc_10 — INSERT 1, UPDATE и DELETE 0",
          "Run 'adminc_17_bakdrop.sql' 'AsdaAdmin'\nRun 'adminc_18_econ.sql' 'AsdaAdmin'" in dep
          and "'adm.EconDaily INSERT'" in ver and "'adm.EconDaily DELETE'" in ver and "'adm.EconDailyChar DELETE'" in ver)
    head = s18.split("GO", 1)[0]
    check("adminc_18: QUOTED_IDENTIFIER / ANSI_NULLS ON отдельным пакетом ДО CREATE TABLE; DENY UPDATE, DELETE",
          "SET QUOTED_IDENTIFIER ON" in head and "CREATE TABLE" not in head and "DENY  UPDATE, DELETE   ON adm.EconDaily " in s18)
    imp = subprocess.run([py, "-c", "import sys; sys.path.insert(0, %r); from core import db; from domains import econ; "
                          "print('IMPORT_OK', len(db._pw), len(db._override))" % ROOT], capture_output=True, timeout=60, cwd=ROOT, stdin=subprocess.DEVNULL)
    check("экономика: импорт domains/econ.py ничего не делает (пароль не читан, соединений нет)", b"IMPORT_OK 0 0" in imp.stdout,
          (imp.stdout + imp.stderr)[-300:])


# ---------------------------------------------------------------- стенд LocalDB

LOGCOLS = ("Edate DATETIME NOT NULL, Userindex INT NOT NULL, Charidx TINYINT NOT NULL, Fromname VARCHAR(20) NULL, Tuserindex INT NULL, "
           "Tcharidx TINYINT NULL, Toname VARCHAR(20) NULL, Code INT NULL, Serial VARCHAR(36) NULL, Amount INT NOT NULL, Ramount INT NULL, "
           "State VARCHAR(100) NULL, Gm INT NULL")
A, B, C, D, S = (9001, 0), (9002, 0), (9003, 0), (9004, 0), (3, 0)      # игроки A B C, удалённый D, служебная S
E_, F_ = (9005, 0), (9006, 0)                        # ★ ревизия 52: E — создан (+1, CharEventCreate), F — восстановлен панелью (сумма не записана)
GOLD0 = {A: 1000, B: 500, C: 100, D: 77, S: 10000}
GOLD1 = {A: 1030, B: 797, C: 80, S: 9000, E_: 1, F_: 500}   # A: −200 −100 +50 −20 (перенос) +300 (моб); B: +150 +100 +7 (10551) +40 (панель)


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def sandbox(check, ldb):
    """Свои базы LocalDB: снимки, потоки, неучтённое, богатейшие, редкое, нет таблицы, операция."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from core import config, db, ops
    from domains import econ as E, srvtables
    import domains
    domains.load_all()
    sys.path.insert(0, os.path.join(PORT, "AstoryServer", "Patches", "Gp7Gateway", "stand"))
    import reconcile_stand as R
    from selftest_money_a6 import _fill
    tag = secrets.token_hex(3)
    names = {"A": "AsdaEcA_" + tag, "Y": "AsdaEcY_" + tag, "G": "AsdaEcG_" + tag, "L": "AsdaEcL_" + tag}
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % names["A"])
    m.cursor().execute("CREATE DATABASE [%s] COLLATE SQL_Latin1_General_CP1_CI_AS" % names["L"])
    for k in ("Y", "G"):
        m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names[k])
    saved_text = srvtables.stack_text
    try:
        ac = ldb(names["A"])
        for f in ("adminc_02_schema.sql", "adminc_18_econ.sql", "adminc_18_econ.sql"):
            for b in _batches(open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()):
                ac.cursor().execute(b)
        check("экономика стенд: настоящие adminc_02 + adminc_18 дважды (повтор безопасен, без asda_admin — выдача прав пропущена)",
              ac.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name IN ('EconDaily', 'EconDailyChar')").fetchone()[0] == 2)
        yc = ldb(names["Y"]).cursor()
        yc.execute(R.ddl("Joy1", "dbo.Item"))
        yc.execute(R.ddl("Joy1", "dbo.Charinfo"))
        for t in ("Exitem", "ItemPostBox", "gifts"):
            yc.execute("CREATE TABLE dbo.%s (Userindex INT, Charidx TINYINT, Code INT, Amount INT)" % t)
        yc.execute("CREATE SCHEMA adm")
        yc.execute("CREATE TABLE adm.ItemLedger (Id INT PRIMARY KEY, UndoneBy INT NULL)")
        yc.execute("CREATE TABLE adm.ItemTaken (LedgerId INT, Code INT, Amount INT)")
        for (u, c), nm in ((A, "Alpha"), (B, "Beta"), (C, "Gamma"), (S, "Svc"), (E_, "Eps"), (F_, "Phi")):
            _fill(yc, "Joy1", "dbo.Charinfo", {"Userindex": u, "Charidx": c, "Uid": "acc_" + nm.lower(), "Charname": nm, "Lvl": 10}, R)
        for (u, c), a in GOLD0.items():
            _fill(yc, "Joy1", "dbo.Item", {"Userindex": u, "Charidx": c, "Code": 20551, "Plate": 2, "Posx": 0, "Amount": a}, R)
        for (u, c), code in ((A, 61785), (S, 70001), (B, 555)):     # редкие 61785 / 70001, не редкий 555
            _fill(yc, "Joy1", "dbo.Item", {"Userindex": u, "Charidx": c, "Code": code, "Plate": 1, "Posx": 1, "Amount": 0}, R)
        yc.execute("INSERT dbo.Exitem VALUES (9002, 0, 70000, 0)")
        gc = ldb(names["G"]).cursor()
        for t in sorted({x["table"] for x in list(E.SOURCES) + list(E.SKIPPED)}):     # ItemEvent — у двух источников
            gc.execute("CREATE TABLE dbo.%s (%s)" % (t, LOGCOLS))
        gc.execute("CREATE TABLE dbo.BundleGain (%s)" % LOGCOLS)                    # «новый писатель» вне каталога
        gc.execute("CREATE SCHEMA ac")
        gc.execute("CREATE TABLE ac.other (event_id BIGINT IDENTITY, ev_local DATETIME2(3) NOT NULL, event_kind NVARCHAR(200) NOT NULL, item_code INT NULL)")
        from domains import acjournal
        k4 = [r["text"] for r in acjournal.catalog()[0]["tables"]["other"] if r["n"] == 4][0]
        gc.execute("INSERT ac.other (ev_local, event_kind, item_code) VALUES (SYSDATETIME(), ?, 61785)", (k4,))
        lc = ldb(names["L"]).cursor()
        lc.execute("CREATE TABLE dbo.GP7GiftLog (state CHAR(1), code1 INT, code2 INT, code3 INT, code4 INT, code5 INT, code6 INT, code7 INT)")
        mp = {"Joy1": names["Y"], "joylog1": names["G"], "AsdaStoryLogin": names["L"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("admin", lambda database: ldb(names["A"]))
        grade = "# stand\n61785\n70000-70002\n"
        srvtables.stack_text = lambda rel, ttl=60: ("[P11_ServerAnnounceSources]\nGradeTableFile=ConfigSet\\announce_codes.txt\n"
                                                    if rel.endswith("patches.ini") else grade)
        seen = []
        orig = db.GameReader.rows

        def spy(self, sql, params=()):
            seen.append((self.name, sql))
            return orig(self, sql, params)
        db.GameReader.rows = spy
        try:
            _checks(check, E, ops, yc, gc, ac, config, R)
            check("экономика стенд: все %d запросов к игровым базам — чтение (assert_select_only), без русских букв и «SELECT *»" % len(seen),
                  seen and not any(CYR.search(s) or "select *" in s.lower() for _n, s in seen), [s[:100] for _n, s in seen if CYR.search(s)][:3])
        finally:
            db.GameReader.rows = orig
    finally:
        srvtables.stack_text = saved_text
        from core import db as _db
        _db.set_override("game", None)
        _db.set_override("admin", None)
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def _log(gc, table, owner, amount, ramount, code=None, state=None, tuser=None):
    """Строка журнала «сейчас» (GETDATE — та же шкала, что у снимка)."""
    gc.execute("INSERT dbo.%s (Edate, Userindex, Charidx, Tuserindex, Tcharidx, Code, Amount, Ramount, State) VALUES (GETDATE(), ?, ?, ?, ?, ?, ?, ?, ?)"
               % table, (owner[0], owner[1], tuser[0] if tuser else None, tuser[1] if tuser else None, code, amount, ramount, state))


def _checks(check, E, ops, yc, gc, ac, config, R):
    from selftest_money_a6 import _fill
    import time
    ctx = ops.Ctx(None, "selftest", "owner", "", "cli")
    # ---- снимок 1 операцией
    r1 = ops.run(ctx, "econ.snapshot", {})
    tot0 = int(yc.execute("SELECT SUM(CAST(Amount AS BIGINT)) FROM dbo.Item WHERE Code = 20551").fetchone()[0])
    s1 = ac.cursor().execute("SELECT id, total, players, service, chars_players, chars_service, via, taken_by FROM adm.EconDaily").fetchall()
    ch1 = ac.cursor().execute("SELECT COUNT(*), SUM(amount) FROM adm.EconDailyChar WHERE snap_id = ?", (s1[0][0],)).fetchone()
    check("экономика стенд: снимок 1 (econ.snapshot) — сумма = SUM(Amount) Item Code 20551 (%d), игроки / служебные, строки персонажей = сумме" % tot0,
          len(s1) == 1 and s1[0][1] == tot0 == sum(GOLD0.values()) and s1[0][2] == tot0 - 10000 and s1[0][3] == 10000 and s1[0][4] == 4
          and s1[0][5] == 1 and ch1[0] == 5 and ch1[1] == tot0 and s1[0][6] == "cli" and r1["message"].startswith("снимок золота №"), (s1, ch1, r1))
    aud = ac.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action = 'econ.snapshot' AND result = 'ok'").fetchone()[0]
    check("экономика стенд: снимок записан в журнал действий adm.audit (ok)", aud == 1, aud)
    check("экономика стенд: снимок с параметром — отказ (в журнале refused)", _refused(lambda: ops.run(ctx, "econ.snapshot", {"x": 1})) == "у снимка золота параметров нет")
    time.sleep(0.05)
    # ---- журналы между снимками
    _log(gc, "MoneyBuy", A, 1000, 800)
    _log(gc, "MoneySell", B, 500, 650)
    _log(gc, "MoneySell", C, 100, 90)                                   # против знака: продажа с убылью
    _log(gc, "TradeGoldFrom", A, 800, 700, tuser=B)                     # A отдал B 100: владелец From — Userindex
    _log(gc, "TradeGoldTo", A, 650, 750, tuser=B)                       # строка To: Userindex = отдавший (A), баланс — Tuserindex (B)
    _log(gc, "MoneyReward", A, 700, 750)
    gc.execute("INSERT dbo.EpisodeEventGold (Edate, Userindex, Charidx, Code, Amount) VALUES (GETDATE(), 9001, 0, 1, 50)")   # дубль — не считается
    _log(gc, "ItemEvent", S, 10000, 9000, code=20551, state="Reset costs")
    _log(gc, "ItemEvent", A, 5, 1, code=999, state="not gold")            # не золото — не считается
    _log(gc, "BundleGain", A, 0, 5, code=20551)                           # вне каталога — пометка, не считается
    # ★ ревизия 52: перенос опций (−Gm), алхимия (было → стало), 10551 (Amount = сумма), создание (+1), правки панели (adm.audit)
    gc.execute("INSERT dbo.TransferOption (Edate, Userindex, Charidx, Code, Amount, Gm) VALUES (GETDATE(), 9001, 0, 7001, 0, 20)")
    _log(gc, "ItemRefine", C, 90, 80, code=20551, state="xUse GameMoney")
    _log(gc, "ItemEvent", B, 7, 757, code=10551, state="Clan Event GM Gain")
    gc.execute("INSERT dbo.CharEventCreate (Edate, Userindex, Charidx, Amount) VALUES (GETDATE(), 9005, 0, 0)")
    au = ("INSERT adm.audit (login, via, action, target, before_json, after_json, result, message) OUTPUT INSERTED.id VALUES ('selftest', 'cli', ?, ?, ?, ?, ?, ?)")
    ac.cursor().execute(au, ("gold.set", "char:9002/0", '{"uid": 9002, "idx": 0, "amount": 757}', '{"uid": 9002, "idx": 0, "amount": 797, "old": 757}', "ok", "x"))
    bad = ac.cursor().execute(au, ("gold.set", "char:9001/0", '{"amount": 1}', '{"amount": 1000001}', "ok", "x")).fetchone()[0]
    ac.cursor().execute(au, ("gold.set", "char:9001/0", None, None, "error", "запись №%d НЕ зафиксирована в игровой базе" % bad))
    ac.cursor().execute(au, ("char.restore", "char:9006/0", '{"uid": 9006}', '{"uid": 9006, "slot": 0, "name": "Phi"}', "ok", "x"))
    for (u, c), a in GOLD1.items():
        if (u, c) in (E_, F_):
            _fill(yc, "Joy1", "dbo.Item", {"Userindex": u, "Charidx": c, "Code": 20551, "Plate": 2, "Posx": 0, "Amount": a}, R)
            continue
        yc.execute("UPDATE dbo.Item SET Amount = ? WHERE Userindex = ? AND Charidx = ? AND Code = 20551", (a, u, c))
    yc.execute("DELETE dbo.Item WHERE Userindex = ? AND Code = 20551", (D[0],))
    time.sleep(0.05)
    r2 = E.take_snapshot("selftest", "cli")
    tot1 = int(yc.execute("SELECT SUM(CAST(Amount AS BIGINT)) FROM dbo.Item WHERE Code = 20551").fetchone()[0])
    check("экономика стенд: снимок 2 — сумма = SUM(Amount) (%d), строк персонажей 6" % tot1,
          r2["total"] == tot1 == sum(GOLD1.values()) and ac.cursor().execute("SELECT COUNT(*) FROM adm.EconDailyChar WHERE snap_id = ?", (r2["id"],)).fetchone()[0] == 6)
    # ---- потоки
    f = E.flows({})
    by = {s["key"]: s for s in f["sources"]}
    check("экономика стенд: потоки по источникам — MoneyBuy −200, MoneySell +150 и −10 (против знака 1), TradeGoldFrom −100 у отдавшего, "
          "TradeGoldTo +100 у ПОЛУЧАТЕЛЯ (Tuserindex), MoneyReward +50, ItemEvent только золото (служебная −1000)",
          by["MoneyBuy"]["total"]["delta"] == -200 and by["MoneySell"]["total"]["delta"] == 140 and by["MoneySell"]["against"] == 1
          and by["TradeGoldFrom"]["cats"]["player"]["delta"] == -100 and by["TradeGoldTo"]["cats"]["player"]["delta"] == 100
          and by["MoneyReward"]["total"]["delta"] == 50 and by["ItemEvent"]["cats"]["service"]["delta"] == -1000
          and by["ItemEvent"]["cats"]["service"]["n"] == 1 and by["ItemEvent"]["cats"]["player"]["n"] == 0
          and [x["sub"] for x in by["ItemEvent"]["subs"]] == ["Reset costs"], {k: (v["total"], v.get("against")) for k, v in by.items() if v["total"]["n"]})
    check("экономика стенд (ревизия 52): перенос опций −20 (−Gm), алхимия −10, 10551 +7 (Amount), создание +1, правки панели +40 — "
          "неподтверждённая правка (error «НЕ зафиксирована») и восстановление без суммы в итог не вошли (восстановление — счётом unknown)",
          by["TransferOption"]["total"]["delta"] == -20 and by["ItemRefine"]["total"]["delta"] == -10 and by["OpGameMoneyAdd"]["total"]["delta"] == 7
          and by["CharEventCreate"]["total"]["delta"] == 1 and by["panel"]["total"]["delta"] == 40 and by["panel"]["total"]["n"] == 1
          and by["panel"]["unknown"] == 1 and by["ItemEvent"]["total"]["n"] == 0, {k: (by[k]["total"], by[k].get("unknown")) for k in
                                                                                    ("TransferOption", "ItemRefine", "OpGameMoneyAdd", "CharEventCreate", "panel")})
    check("экономика стенд: служебные отдельно (итог +8 игроков без −1000), svc=in — в общем итоге; по дням — та же сумма",
          f["total"]["delta"] == 8 and f["cats"]["service"]["delta"] == -1000 and E.flows({"svc": "in"})["total"]["delta"] == -992
          and sum(d["total"]["delta"] for d in f["days"]) == 8, (f["total"], f["cats"]))
    sk = {x["key"]: x["rows"] for x in f["skipped"]}
    check("экономика стенд: EpisodeEventGold (дубль) — строка видна в «не считаются», в потоки не вошла", sk.get("EpisodeEventGold") == 1, sk)
    one = E.flows({"source": "TradeGoldTo"})
    check("экономика стенд: отбор одного источника", [s["key"] for s in one["sources"]] == ["TradeGoldTo"] and one["total"]["delta"] == 100)
    # ---- неучтённое
    u = E.unaccounted({})
    p = u["pairs"][0] if u["pairs"] else None
    chars = {(x["uid"], x["idx"]): x for x in u["chars"]}
    check("экономика стенд: неучтённое = Δ снимков − журналы: игроки +723 (моб +300 у A, удалённый D −77, восстановленный панелью F +500), служебные 0",
          p and p["cats"]["player"]["snap"] == 731 and p["cats"]["player"]["journal"] == 8 and p["cats"]["player"]["unaccounted"] == 723
          and p["cats"]["service"]["unaccounted"] == 0 and p["total"]["unaccounted"] == 723, p)
    check("экономика стенд: неучтённое по персонажам — A +300, D −77 «персонажа нет», F +500 с пометкой «char.restore» (сумма не записана); "
          "у B (правка панели учтена), C, E и S ноль",
          set(chars) == {A, D, F_} and chars[A]["unaccounted"] == 300 and chars[A]["char"] == "Alpha" and chars[D]["unaccounted"] == -77
          and chars[D]["gone"] and chars[D]["after"] is None and chars[F_]["unaccounted"] == 500 and chars[F_]["panel"] == ["char.restore"]
          and chars[A]["panel"] == [], u["chars"])
    s = E.summary({})
    oth = [x["table"] for x in s["other"]]
    check("экономика стенд: сводка — на руках = SUM(Amount), последняя пара = неучтённое 223, таблица вне каталога BundleGain помечена",
          s["held"]["cats"]["player"]["sum"] == tot1 - 9000 and s["held"]["total"]["sum"] == tot1 - 9000 and s["pair"]["total"]["unaccounted"] == 723
          and [x for x in s["sources"] if x["key"] == "panel"][0]["unknown"] == 1 and len(s["unlogged"]) == len(E.UNLOGGED)
          and s["snapshots"] == 2 and oth == ["BundleGain"] and not s["errors"], (s["held"], s["pair"], oth, s["errors"]))
    check("экономика стенд: номер снимка без пары — отказ; первый снимок — тоже",
          _refused(lambda: E.unaccounted({"id": str(r1["result"]["id"])})) is not None and _refused(lambda: E.unaccounted({"id": "999"})) is not None)
    # ---- богатейшие и редкое
    rc = E.richest({"n": "10"})
    check("экономика стенд: богатейшие — игроки по убыванию; служебные отдельно; svc=in — общий список с S первой",
          [(x["uid"], x["gold"]) for x in rc["players"]] == [(9001, 1030), (9002, 797), (9006, 500), (9003, 80), (9005, 1)]
          and [x["uid"] for x in rc["service"]] == [3] and E.richest({"svc": "in"})["all"][0]["uid"] == 3 and rc["total"]["sum"] == 2408
          and rc["players"][0]["char"] == "Alpha", rc)
    rr = E.rare({})
    rows = {x["code"]: x for x in rr["rows"]}
    check("экономика стенд: редкое на руках — коды таблицы 61785 / 70000 / 70001 (555 не редкий), категории, места хранения, held_counts и P59",
          set(rows) == {61785, 70000, 70001} and rr["rare_codes"] == 4 and rows[70001]["cats"]["service"]["rows"] == 1
          and rows[70001]["total"]["rows"] == 0 and rows[70000]["cats"]["player"]["where"] == {"Exitem": 1}
          and rows[61785]["held"]["rows"] == 1 and rows[61785]["p59"] == {"drop": 1, "pickup": 0} and not rr["errors"], (rr["errors"], rows))
    # ---- нет таблицы
    gc.execute("DROP TABLE dbo.MoneyCraft")
    f2 = E.flows({})
    check("экономика стенд: таблицы MoneyCraft нет — строка ошибки «журнал золота MoneyCraft не прочитан», остальное считается",
          any(e.startswith("журнал золота MoneyCraft не прочитан:") for e in f2["errors"]) and f2["total"]["delta"] == 8, f2["errors"])
    ac.cursor().execute("DROP TABLE adm.EconDailyChar")
    u2 = E.unaccounted({})
    check("экономика стенд: таблицы снимков по персонажам нет — пары считаются, по персонажам — строка ошибки",
          u2["pairs"] and any(e.startswith("неучтённое по персонажам не посчитано:") for e in u2["errors"]), u2["errors"])


# ---------------------------------------------------------------- живая dev

def live(check):
    """Живая dev: чтение игровых баз (asda_admin); снимок — запись ТОЛЬКО в AsdaAdmin."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db, ops
    from domains import econ as E
    import domains
    domains.load_all()
    if config.get().on_server:
        return check("живой самотест А6.3 — с ПК", True)
    cn = db.admin()
    try:
        perm = {r["k"]: r["p"] for r in db.admin_rows(cn, "SELECT k, HAS_PERMS_BY_NAME(o, 'OBJECT', a) AS p FROM (VALUES ('di', 'adm.EconDaily', 'INSERT'), "
                                                    "('du', 'adm.EconDaily', 'UPDATE'), ('dd', 'adm.EconDaily', 'DELETE'), ('ci', 'adm.EconDailyChar', 'INSERT'), "
                                                    "('cd', 'adm.EconDailyChar', 'DELETE')) v(k, o, a)")}
    finally:
        cn.close()
    check("живое (asda_admin): adm.EconDaily / EconDailyChar — INSERT есть, UPDATE и DELETE нет", perm == {"di": 1, "du": 0, "dd": 0, "ci": 1, "cd": 0}, perm)
    with db.GameReader("joy1") as j:
        direct = j.one("SELECT SUM(CAST(Amount AS BIGINT)) AS s, SUM(CASE WHEN Userindex > 5000 THEN CAST(Amount AS BIGINT) ELSE 0 END) AS p FROM dbo.Item "
                       "WHERE Code = 20551")
    s = E.summary({})
    check("живое: золото на руках — игроки = SUM(Amount) Userindex > 5000 (%s), всего (svc=in) = SUM (%s)" % (direct["p"], direct["s"]),
          s["held"]["total"]["sum"] == direct["p"] and E.summary({"svc": "in"})["held"]["total"]["sum"] == direct["s"], s["held"])
    cnt = {}
    with db.GameReader("joylog1") as g:
        for src in E.SOURCES:
            w = E._gold_cond(src)
            cnt[src["key"]] = int(g.one("SELECT COUNT(*) AS n FROM dbo.%s%s" % (src["table"], (" WHERE " + " AND ".join(w)) if w else ""))["n"])
        n30 = 0
        for src in E.SOURCES:
            n30 += int(g.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE Edate >= DATEADD(DAY, -29, CONVERT(date, GETDATE()))%s"
                             % (src["table"], "".join(" AND " + c for c in E._gold_cond(src))))["n"])
        start = g.one("SELECT CAST(DATEADD(DAY, -29, CONVERT(date, GETDATE())) AS DATETIME2) AS d")["d"]
    pev = E.panel_events(start)
    n30 += sum(1 for e in pev if e["delta"] is not None)
    got = {x["key"]: x["cats"]["player"]["n"] + x["cats"]["service"]["n"] for x in s["sources"] if x.get("read") and x["key"] != "panel"}
    pall = E.panel_events()
    prow = [x for x in s["sources"] if x["key"] == "panel"]
    check("живое (ревизия 52): правки панели из adm.audit — точных %d (gold.set и откат), без суммы %d (восстановление, копия), сводка = им"
          % (sum(1 for e in pall if e["delta"] is not None), sum(1 for e in pall if e["delta"] is None)),
          prow and prow[0]["read"] and prow[0]["unknown"] == sum(1 for e in pall if e["delta"] is None)
          and prow[0]["cats"]["player"]["n"] + prow[0]["cats"]["service"]["n"] == sum(1 for e in pall if e["delta"] is not None), prow)
    check("живое: каталог источников — строк каждого = COUNT(*) таблицы (%d источников), строк против знака: %s" % (len(cnt),
          {x["key"]: x["against"] for x in s["sources"] if x.get("against")} or "нет"), got == cnt, {k: (got.get(k), v) for k, v in cnt.items() if got.get(k) != v})
    f = E.flows({"svc": "in"})
    check("живое: потоки за 30 суток (svc=in) — строк = COUNT(*) по всем источникам (%d), без ошибок" % n30,
          f["total"]["n"] == n30 and not f["errors"], (f["total"], f["errors"]))
    rc = E.richest({"n": "5", "svc": "in"})
    check("живое: богатейшие — первый = наибольшему золоту персонажа, сумма категорий = SUM", rc["all"] and rc["total"]["sum"] == direct["s"]
          and rc["all"][0]["gold"] == max(rc["cats"]["player"]["max"], rc["cats"]["service"]["max"]), rc["cats"])
    rr = E.rare({"n": "20"})
    check("живое: редкое на руках — таблица редкого прочитана по SSH (кодов > 0), строки с held_counts, без ошибок",
          rr["rare_codes"] > 0 and rr["present"] >= len(rr["rows"]) and all(x["held"] is not None for x in rr["rows"]) and not rr["errors"],
          (rr["rare_codes"], rr["present"], rr["errors"]))
    # снимок — запись ТОЛЬКО в AsdaAdmin; сверка с SUM(Amount) до и после (если золото не менялось — равно)
    ctx = ops.Ctx(None, "selftest:live", "owner", "", "cli")
    r = ops.run(ctx, "econ.snapshot", {})
    with db.GameReader("joy1") as j:
        after = j.one("SELECT SUM(CAST(Amount AS BIGINT)) AS s FROM dbo.Item WHERE Code = 20551")["s"]
    check("живое: снимок econ.snapshot (пишет только AsdaAdmin) = SUM(Amount) Item 20551 (%s)" % direct["s"],
          r["result"]["total"] == direct["s"] or direct["s"] != after, (r["result"], direct["s"], after))
    u = E.unaccounted({})
    check("живое: неучтённое читается (снимков %d, пар %d), без ошибок" % (len(u["snapshots"]), len(u["pairs"])), u["snapshots"] and not u["errors"], u["errors"])
    import ssl
    import urllib.error
    import urllib.request
    sc = ssl.create_default_context()
    sc.check_hostname, sc.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=sc)).open(
            "https://%s:17890/api/econ/summary" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/econ/summary без входа — 401", code == 401, code)
