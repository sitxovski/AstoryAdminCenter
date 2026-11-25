# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_trade_a6.py — самотест шага А6.4 «Передачи и рынок» (22.11.2026; domains/trade.py, /api/trade/*, web/trade.js, консоль trade,
выкладка ext/anticheat/).

offline(check)  — каталог передач по реверсу (кто отдал / кто получил, зеркала «…To» = ac_metrics_db.is_mirror), правило M3 — тот же модуль
                  AstoryServer/Tools/Anticheat/ac_metrics_db.py (флаги раздела = pair_flags на тех же строках), цепочки и серийники на синтетике, разбор
                  Log_SelfStore, отказы ввода до базы (без «; »), право econ.view, маршруты, SQL без русских букв и «SELECT *», только чтение,
                  переводы EN (shadowed_translations = 0), веб без innerHTML и с EN всех подписей, консоль (неизвестный ключ, ключ без
                  значения, неизвестное действие — отказ без базы, --help только печатает), выкладка (ext/anticheat), импорт без побочных
                  эффектов.
sandbox(check, ldb) — СВОИ базы LocalDB (Joy1, JoyLog1, AsdaStoryOp, AsdaStoryLogin; столбцы таблиц — как на живой 22.11). Синтетика на
                  ФИКСИРОВАННЫХ сутках 05.10.2026 (период задаётся явно — от времени запуска не зависит): обмен с зеркалами, лавка (вещь
                  продавец → покупатель, золото обратно), аукцион (Purchase + зеркало Sold out), подарок gp7, служебная учётка, серийник
                  через три передачи, входы LogInfo (общий IP, общий MAC, частный адрес). Сверка: асимметрия и «≥ 5 записей» по M3, зеркала
                  не двоятся, владелец строки «…To», цепочки, серийник, сеть только с правом, отбор учётки и пары, рынок (лоты, цены,
                  история, налог), лавки и сверка с журналом, нет таблицы — строка ошибки. Все запросы — чтение, без русских букв.
live(check)     — живая dev: строк каждого источника и зеркала = COUNT(*) за тот же период, каждая таблица Trade* / PersonalStore* — либо
                  источник, либо зеркало, лоты = COUNT Exitem, история = COUNT, сбор = SUM, сделки лавок = строкам золота, служба на
                  сервере берёт правило M3 из ext/anticheat, /api/trade/graph без входа — 401.
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
# кто отдал (g) и кто получил (r) по реверсу процедур Joy1 (отчёт §А6.4 шаг 1) — каталог модуля должен совпасть
EXPECT = {"TradeGoldFrom": ("Userindex", "Tuserindex"), "TradeShellGoldFrom": ("Userindex", "Tuserindex"), "TradeItemFrom": ("Userindex", "Tuserindex"),
          "TradeGear": ("Userindex", "Tuserindex"), "TradeFunctional": ("Userindex", "Tuserindex"), "TradeSowel": ("Userindex", "Tuserindex"),
          "TradeNoStack": ("Userindex", "Tuserindex"), "PersonalStoreitemFrom": ("Userindex", "Tuserindex"),
          "PersonalStoreFunctional": ("Userindex", "Tuserindex"), "PersonalStoreGear": ("Userindex", "Tuserindex"),
          "PersonalStoreSowel": ("Userindex", "Tuserindex"), "PersonalStoreNostack": ("Userindex", "Tuserindex"),
          "PersonalStoreGoldFrom": ("Tuserindex", "Userindex"), "ExchangeItem": ("Suserindex", "Userindex"), "ExchangeGold": ("Userindex", "Suserindex")}


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
    ("graph", {"from": "2026-10-01"}), ("graph", {"to": "20261131"}), ("graph", {"from": "20261005", "to": "20261001"}),
    ("graph", {"from": "20250101", "to": "20261121"}), ("graph", {"svc": "all"}), ("graph", {"group": "mail"}),
    ("graph", {"account": "x" * 41}), ("transfers", {"pair": "1-"}), ("transfers", {"pair": "a-b"}), ("transfers", {"pair": "99999999999-1"}),
    ("transfers", {"page": "0"}), ("transfers", {"size": "201"}), ("transfers", {"size": "x"}), ("market", {"page": "-1"}),
    ("stores", {"logs": "2"}), ("stores", {"svc": "both"})]


def _edges_syn():
    """Синтетические передачи (без базы) для правила M3, цепочек и серийников."""
    t = lambda h, m=0: datetime.datetime(2026, 10, 5, h, m)
    e = lambda tt, fu, tu, what, qty, code=None, serial=None, src="TradeGoldFrom": {
        "t": tt, "group": "trade", "src": src, "what": what, "fu": fu, "fi": 0, "fn": None, "tu": tu, "ti": 0, "tn": None, "code": code,
        "qty": qty, "serial": serial}
    return [e(t(9), 3, 9001, "gold", 1500000), e(t(10), 9001, 9002, "gold", 2000000), e(t(10, 5), 9002, 9001, "item", 3, 555, None, "TradeItemFrom"),
            e(t(11), 9002, 9003, "gold", 500), e(t(12), 9002, 9004, "gold", 1000)] + \
           [e(t(10, 10 + i), 9001, 9003, "item", 1, 7100, None, "TradeSowel") for i in range(5)] + \
           [e(t(10, 20), 9001, 9003, "item", 2, 600, "SER-X", "TradeItemFrom"), e(t(11, 1), 9003, 9002, "item", 2, 600, "SER-X", "PersonalStoreitemFrom"),
            e(t(13), 9002, 9004, "item", 2, 600, "SER-X", "TradeItemFrom")]


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n
    from domains import trade as T
    import domains
    domains.load_all()
    M = T.m3()

    # ---- каталог по реверсу и правило M3
    got = {s["key"]: (s["gu"], s["ru"]) for s in T.EDGES}
    check("передачи: кто отдал и кто получил у каждого источника = реверсу процедур Joy1 (обмен Userindex → Tuserindex, лавка: вещь продавец "
          "Userindex → покупатель Tuserindex, золото обратно; аукцион Suserindex ↔ Userindex)", got == EXPECT,
          {k: (got.get(k), v) for k, v in EXPECT.items() if got.get(k) != v})
    trade_store = [s["table"] for s in T.EDGES if s["table"].startswith(("Trade", "PersonalStore"))]
    mir = [m["table"] for m in T.MIRRORS if m["table"].startswith(("Trade", "PersonalStore"))]
    check("передачи: зеркала «…To» — ровно те, что ac_metrics_db.is_mirror (правило M3), источники зеркалами не являются; «Sold out» — зеркало покупки",
          all(M.is_mirror(x) for x in mir) and not any(M.is_mirror(x) for x in trade_store) and len(mir) == 5
          and [m.get("extra") for m in T.MIRRORS if m["table"] == "ExchangeEvent"] == ["State = 'Sold out at the Exchange'"], (mir, trade_store))
    check("передачи: правило M3 — тот же модуль AstoryServer/Tools/Anticheat/ac_metrics_db.py (на ПК — исходник), пороги ac_common.THR",
          T.m3().LOADED_FROM == os.path.join(T.AC_SRC, "ac_metrics_db.py") and M.THR["m3_pair_deals"] == 5 and M.THR["m3_gold_oneway"] == 1000000,
          T.m3().LOADED_FROM)
    src = open(os.path.join(ROOT, "domains", "trade.py"), encoding="utf-8").read()
    check("передачи: правило M3 не продублировано (analyse_pairs и pair_flags зовутся из модуля, своих порогов в trade.py нет)",
          "M.analyse_pairs(" in src and "m3().pair_flags(" in src and "def analyse_pairs" not in src and "def pair_flags" not in src
          and "1000000" not in src)
    ed = _edges_syn()
    pairs = M.analyse_pairs(T.m3_rows(ed))
    fl = T.m3_flags(pairs)
    raw = M.pair_flags(pairs)
    check("передачи: флаги раздела = pair_flags модуля на тех же строках (%d флагов): A→B золото 2 000 000 без обратного, служебная 3 → A, "
          "A ↔ C ≥ 5 записей" % len(raw),
          sum(len(v) for v in fl.values()) == len(raw) and {(k, x["type"]) for k, v in fl.items() for x in v} ==
          {((3, 9001), "oneway"), ((9001, 9002), "oneway"), ((9001, 9003), "deals")} and
          [x for x in fl[(9001, 9002)] if x["type"] == "oneway"][0] == {"type": "oneway", "from": 9001, "to": 9002, "value": 2000000}, (fl, raw))
    check("передачи: в строках M3 количество — переданное (2 000 000), а не баланс «было» (M3 консоли суммирует Amount)",
          pairs[(9001, 9002)]["gold_ab"] == 2000000 and pairs[(9001, 9002)]["items_ba"] == 3, pairs[(9001, 9002)])
    ch, cap = T.chains(ed)
    nodes = sorted(tuple(c["nodes"]) for c in ch["all"])
    pnodes = sorted(tuple(c["nodes"]) for c in ch["player"])
    check("передачи: цепочки по времени одним проходом — 3 → A → B → (C или D) и 3 → A → C → B → D, A → B → C и A → B → D видны "
          "(вложенные не повторяются); полоса игроков — A → B → C и A → B → D без служебной, без обрезки",
          not cap and any(c[:3] == (3, 9001, 9002) and len(c) == 4 for c in nodes) and (3, 9001, 9003, 9002, 9004) in nodes
          and all(any(c[i:i + 3] == (9001, 9002, x) for c in nodes for i in range(len(c))) for x in (9003, 9004))
          and (9001, 9002, 9003) in pnodes and (9001, 9002, 9004) in pnodes and all(3 not in c for c in pnodes), (nodes, pnodes))
    AM = T.m3()                          # ★ ревизия 56 С-1: правило M3 — частная копия (domains/acsrc), в sys.modules её нет
    check("передачи (ревизия 54): M3 консоли исправлена — лавка: золото покупатель → продавец (Ramount − Amount), обмен: переданное, а не "
          "баланс «было», стопка золота TradeItemFrom Code 20551 — золото; пороги THR прежние",
          AM.pair_rows("PersonalStoreGoldFrom", True, True, [(75210, 75204, 0, 6, 66753743, 66754928)]) == [(75204, 75210, "gold", 6, 1185)]
          and AM.pair_rows("TradeGoldFrom", True, True, [(1, 2, 0, 1, 50, 20)]) == [(1, 2, "gold", 1, 30)]
          and AM.pair_rows("TradeItemFrom", True, True, [(1, 2, 1, 1, 9, 0)]) == [(1, 2, "gold", 1, 9)]
          and AM.THR["m3_pair_deals"] == 5 and AM.THR["m3_gold_oneway"] == 1000000 and "ac_metrics_db" not in sys.modules)
    _selfstore_more(check, T)
    sr, thr = T.serial_chains(ed)
    check("передачи: серийник SER-X передан 3 раза (порог M4 = %d) — путь A → C → B → D" % thr,
          thr == 3 and len(sr) == 1 and sr[0]["serial"] == "SER-X" and [(e["fu"], e["tu"]) for e in sr[0]["path"]] == [(9001, 9003), (9003, 9002), (9002, 9004)],
          sr)
    lines = ["10 Mon 05 Day 11 hou 00 min 00 sec : [OPEN]\tHostNum:0\tHostIndex:9003\tHostName:Gamma",
             "10 Mon 05 Day 11 hou 00 min 00 sec : [OPEN]\tItemIndex:600\tPlate:2\tPosX:1\tAmount:2\tGold:250",
             "10 Mon 05 Day 11 hou 00 min 01 sec : [BUY]\tDB Send..!!\tHostNum:0\tHostIndex:9003\tHostName:Gamma\tBuyNum:1\tBuyIndex:9002\tBuyName:Beta\tTotalGold:500",
             "10 Mon 05 Day 11 hou 00 min 01 sec : [BUY]\tItemIndex:600\tPlate:2\tPosX:1\tAmount:2",
             "10 Mon 05 Day 11 hou 00 min 02 sec : \t[E] CharSelfStoreReady() CharFlag Not 0..!! UserIndex:9003 [Gamma]",
             "мусор без шапки"]
    ev = T.parse_selfstore(lines, "2026")
    check("передачи: разбор Log_SelfStore — шапка ac_common.HDR, год из имени файла, хозяин лавки, покупатель, сумма, вещи, строка «[E]»",
          [x["tag"] for x in ev] == ["OPEN", "BUY", "error"] and ev[0]["host_uid"] == 9003 and ev[0]["items"][0]["gold"] == 250
          and ev[1]["buyer_uid"] == 9002 and ev[1]["gold"] == 500 and ev[1]["db"] == "DB Send..!!" and ev[1]["t"] == datetime.datetime(2026, 10, 5, 11, 0, 1)
          and ev[2]["msg"].startswith("CharSelfStoreReady()"), ev)

    # ---- отказы ввода
    why = [_refused(lambda f=f, q=q: T.check_input(q, f)) for f, q in REFUSALS]
    check("передачи: неверный ввод — отказ до базы (%d случаев: даты, период, служебные, вид, учётка, пара, страница, строк, журнал)" % len(REFUSALS),
          all(why), [(REFUSALS[i], w) for i, w in enumerate(why) if not w])
    check("передачи: тексты отказов без «; »", all("; " not in w for w in why if w), [w for w in why if w and "; " in w])
    check("передачи: graph проверяет ввод до обращения к базе (подставной базы нет — всё равно отказ)",
          _refused(lambda: T.graph({"from": "20261005", "to": "20261001"})) == "дата «с» позже даты «по»")

    # ---- права, маршруты
    roles = ("owner", "admin", "gm", "support")
    check("передачи: право econ.view — owner и admin; сеть — players.view_net (owner, admin, gm)",
          {r for r in roles if auth.can(r, "econ.view")} == {"owner", "admin"} and {r for r in roles if auth.can(r, "players.view_net")} >= {"owner", "admin"})
    paths = ("/api/trade/graph", "/api/trade/transfers", "/api/trade/market", "/api/trade/stores")
    rt = {p: _route(p) for p in paths}
    check("передачи: маршруты %s — GET, право econ.view" % ", ".join(paths), all(fn and perm == "econ.view" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("передачи: сеть в граф — только по праву запроса players.view_net", 'trade.graph(req.query, can_net=req.can("players.view_net"))' in srv)

    # ---- SQL модуля
    code = re.sub(r'"""(?:[^"]|"(?!""))*"""', "", src)
    lits = re.findall(r'"((?:SELECT|FROM|WHERE|CASE|SUM|COUNT|Edate|State|\(CAST|CAST)[^"]*)"', code)
    check("передачи: в тексте SQL модуля нет русских букв и «SELECT *» (%d строк SQL)" % len(lits),
          lits and not any(CYR.search(s) or "select *" in s.lower() for s in lits), [s[:80] for s in lits if CYR.search(s)][:3])
    check("передачи: только чтение — в SQL модуля нет INSERT / UPDATE / DELETE / EXEC, нет операций и записи (GameWriter, admin()); «INSERT» — только "
          "тег строки журнала Log_SelfStore", not any(re.search(r"\b(INSERT|UPDATE|DELETE|EXEC)\b", x) for x in lits) and "@register" not in code
          and "GameWriter" not in code and "db.admin(" not in code and len(re.findall(r"\bINSERT\b", code)) == len(re.findall(r'"INSERT"', code)) == 2)

    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [w for w in why if w] + [
            "журнал передач TradeGear не прочитан: запрос к joylog1: Invalid object name", "подарки gp7 не прочитаны: x",
            "получатели подарков gp7 не найдены: x", "зеркальная таблица TradeGoldTo не прочитана: x", "ящик ItemPostBox и отложенные подарки не прочитаны: x",
            "входы LogInfo не прочитаны: x", "лоты аукциона не прочитаны: x", "история аукциона ExchangeRegi не прочитана: x", "налог аукциона не прочитан: x",
            "имена персонажей не прочитаны: x", "журнал лавок GameServer не прочитан: HostError", "журнал лавок SelfStore_20261005.txt не прочитан: x",
            "журналы JoyLog1 не прочитаны: x", T.OPEN_NOTE, "учётки с логином «x» нет"]
        miss = [x for x in ru if CYR.search(i18n.tr(x))]
        check("передачи EN: отказы, ошибки чтения (причина — вложенным переводом) и пометка лавок — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("передачи: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])

    # ---- веб
    js = open(os.path.join(ROOT, "web", "trade.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("передачи веб: раздел #/trade «Передачи и рынок» с правом econ.view, значок trade (окна игры), маршрут viewTrade, скрипт после acjournal.js",
          '["#/trade", "Передачи и рынок", "econ.view", "trade"]' in app and 'case "trade": return viewTrade(my);' in app
          and "/trade.js" in idx and idx.index("/acjournal.js") < idx.index("/trade.js")
          and os.path.isfile(os.path.join(ROOT, "web", "skin", "winicon_trade.png")))
    check("передачи веб: без innerHTML, данные — текстовыми узлами (acText / itemLine / acChar / acAccount), без T() над данными, строки журнала — acText",
          "innerHTML" not in js and "acText(e.msg)" in js and "itemLine(" in js and "acChar(" in js and not re.search(r"T\((?:x|r|p|c|e|s|d|g|a|i|f)\.", js))
    check("передачи веб: даты уходят ГГГГММДД (acDay), служебные — переключатель svc=in, сеть скрыта без права (net_hidden)",
          "acDay(" in js and 'svcIn.checked ? "in" : "sep"' in js and "r.net_hidden" in js)
    labels = re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|b|div)", (?:null|\{[^}]*\}), "([^"]+)"', js)
    labels += re.findall(r'\["([^"]+)", \w+ =>', js) + re.findall(r'T\("([^"]+)"', js) + re.findall(r'placeholder: "([^"]+)"', js)
    for m in re.findall(r"const TR_\w+ = \{([^}]*)\}", js, re.S):
        labels += re.findall(r':\s*"([^"]+)"', m)
    labels += ["передачи"]
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted({x for x in labels if x not in have and CYR.search(x)})
    check("передачи веб EN: у всех подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(set(labels)), not lack and len(set(labels)) > 120, lack[:8])
    rx = r'(?:^|[{,])\s*"((?:[^"\\]|\\.)+)":\s*"'
    blk = wi[wi.index("// ★ А6.4"):]
    kb = re.findall(rx, blk, re.M)
    earlier = set(re.findall(rx, wi[:wi.index("// ★ А6.4")], re.M))
    check("передачи веб EN: новые ключи web/i18n.js не повторяют прежние и друг друга (%d ключей)" % len(kb),
          len(kb) == len(set(kb)) and not set(kb) & earlier, sorted(set(kb) & earlier)[:5])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "trade.js")], capture_output=True, timeout=60)
        check("передачи: node --check web/trade.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("передачи: node --check web/trade.js (node не запустился)", False, str(ex))

    # ---- консоль, выкладка, импорт
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "trade"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("graph", "--bogus")
    c2, o2 = con("transfers", "--pair")
    c3, o3 = con("nope")
    c4, o4 = con("stores", "extra")
    c5, o5 = con("graph", "--from", "20261005", "--to", "20261001")
    c6, o6 = con("transfers", "--pair", "1-x")
    check("передачи консоль: неизвестный ключ, ключ без значения, неизвестное действие, лишнее слово, неверный период и пара — отказ без запроса к базе",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3
          and c4 and "неизвестный аргумент extra" in o4 and c5 and "позже" in o5 and c6 and "два номера через дефис" in o6,
          (o1[-200:], o2[-200:], o3[-200:], o4[-200:], o5[-200:], o6[-200:]))
    hp = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60, cwd=ROOT,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
    ho = hp.stdout.decode("utf-8", "replace")
    check("передачи консоль: --help печатает справку с командой trade (ничего не делает)", hp.returncode == 0 and "  trade …" in ho
          and "transfers [--from …]" in ho)
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("передачи выкладка: в архив кладутся ext/anticheat/ ac_metrics_db.py, ac_common.py, db_connect.py — те же файлы без правок; нет исходника — отказ",
          'z.writestr("ext/anticheat/" + _f, _b)' in dep and "без правила M3 не выкладывается" in dep
          and T.AC_FILES == ("ac_metrics_db.py", "ac_common.py", "db_connect.py") and T.AC_EXT.endswith(os.path.join("ext", "anticheat"))
          and all(os.path.isfile(os.path.join(T.AC_SRC, f)) for f in T.AC_FILES))
    imp = subprocess.run([py, "-c", "import sys; sys.path.insert(0, %r); from core import db; from domains import trade; "
                          "print('IMPORT_OK', len(db._pw), len(db._override), trade._AC is None, 'ac_metrics_db' in sys.modules)" % ROOT],
                         capture_output=True, timeout=60, cwd=ROOT, stdin=subprocess.DEVNULL)
    check("передачи: импорт domains/trade.py ничего не делает (пароль не читан, соединений нет, правило M3 не загружено)",
          b"IMPORT_OK 0 0 True False" in imp.stdout, (imp.stdout + imp.stderr)[-300:])


def _selfstore_more(check, T):
    """★ ревизия 54 Н-3, Н-4: список logs.files обрезан (more) — дни старше списка с ПК не читаются и помечаются, на сервере дочитываются
    по имени (logs.stat); бюджет чтения — на пользователя запроса."""
    from core import config
    from domains import logs
    saved = (logs.files, logs.scan, logs.stat, logs.procs_of, config.get().on_server)
    calls = {"scan": [], "stat": []}
    try:
        logs.procs_of = lambda key: ["GameServer"]
        logs.files = lambda key, proc, kind=None: {"missing": False, "more": True, "total": 75,
                                                   "files": [{"name": "SelfStore_20261009.txt", "size": 10}, {"name": "SelfStore_20261008.txt", "size": 10}]}
        logs.scan = lambda key, proc, name, kind=None, needles=(), show_ip=False, user=None, size=None: (
            calls["scan"].append((name, user)) or {"lines": [], "missing": False})
        logs.stat = lambda key, proc, name, kind=None: (calls["stat"].append(name) or ((5, 0) if name == "SelfStore_20261005.txt" else None))
        config.get().on_server = False
        unread = []
        T.selfstore_files("20261001", "20261010", [], "tester", unread)
        pc = (list(calls["scan"]), list(calls["stat"]), list(unread))
        calls["scan"].clear()
        calls["stat"].clear()
        config.get().on_server = True
        unread2 = []
        T.selfstore_files("20261001", "20261010", [], None, unread2)
        srv = (list(calls["scan"]), list(calls["stat"]), unread2)
    finally:
        logs.files, logs.scan, logs.stat, logs.procs_of, config.get().on_server = saved
    check("передачи (ревизия 54 Н-3, Н-4): журнал лавок — список обрезан (more): с ПК дни до 08.10 не читаются и помечены «не прочитан», "
          "на сервере дочитываются по имени файла (stat 01.10–07.10, прочитан 05.10); бюджет — на пользователя запроса (tester), иначе trade.stores",
          pc[0] == [("SelfStore_20261009.txt", "tester"), ("SelfStore_20261008.txt", "tester")] and not pc[1]
          and pc[2] == [{"proc": "GameServer", "before": "20261008", "listed": 2, "total": 75}]
          and srv[1] == ["SelfStore_202610%02d.txt" % d for d in range(1, 8)] and ("SelfStore_20261005.txt", "trade.stores") in srv[0] and not srv[2],
          (pc, srv))


# ---------------------------------------------------------------- стенд LocalDB

# Столбцы таблиц — как на живой dev 22.11 (sys.columns; varchar — без длины в снимке: имена 20, серийники 36, State 100)
_V = {"Fromname": 20, "FromName": 20, "Toname": 20, "Scharname": 20, "Charname": 20, "Serial": 36, "Tserial": 36, "State": 100, "IpAddress": 20,
      "Mac": 20, "Us_id": 20, "Uid": 20}
TRADE_COLS = "Edate:datetime, Userindex:int, Charidx:tinyint, Fromname:varchar, Tuserindex:int, Tcharidx:tinyint, Toname:varchar"
SCHEMA = {
    "TradeGoldFrom": TRADE_COLS + ", Serial:varchar, Amount:int, Ramount:int",
    "TradeGoldTo": TRADE_COLS + ", Serial:varchar, Amount:int, Ramount:int",
    "TradeShellGoldFrom": TRADE_COLS + ", Serial:varchar, Amount:int, Ramount:int",
    "TradeShellGoldTo": TRADE_COLS + ", Serial:varchar, Amount:int, Ramount:int",
    "TradeItemFrom": TRADE_COLS + ", Code:int, Serial:varchar, Amount:int, Ramount:int",
    "TradeitemTo": TRADE_COLS + ", Code:int, Serial:varchar, Tserial:varchar, Amount:int, Ramount:int",
    "TradeGear": TRADE_COLS + ", Code:int, Serial:varchar, Cell1:smallint, Upcount:tinyint",
    "TradeFunctional": TRADE_COLS + ", Code:int, Serial:varchar, Amount:int",
    "TradeSowel": "Edate:datetime, Userindex:int, Charidx:tinyint, Fromname:varchar, TUserindex:int, TCharidx:tinyint, Toname:varchar, Code:int, Serial:varchar",
    "TradeNoStack": "Edate:datetime, Userindex:int, Charidx:tinyint, Fromname:varchar, TUserindex:int, TCharidx:tinyint, Toname:varchar, Code:int, Serial:varchar",
    "PersonalStoreitemFrom": TRADE_COLS + ", Code:int, Serial:varchar, Amount:int, Ramount:int",
    "PersonalStoreitemTo": TRADE_COLS + ", Code:int, Serial:varchar, Amount:int, Ramount:int",
    "PersonalStoreGoldFrom": TRADE_COLS + ", Serial:varchar, Amount:int, Ramount:int",
    "PersonalStoreGoldTo": TRADE_COLS + ", Serial:varchar, Amount:int, Ramount:int",
    "PersonalStoreFunctional": "Edate:datetime, Userindex:int, Charidx:tinyint, FromName:varchar, Tuserindex:int, Tcharidx:tinyint, Toname:varchar, Code:int, Serial:varchar, Ramount:int",
    "PersonalStoreGear": TRADE_COLS + ", Code:int, Serial:varchar, Cell1:smallint, Upcnt:tinyint",
    "PersonalStoreSowel": "Edate:datetime, Userindex:int, Charidx:tinyint, FromName:varchar, Tuserindex:int, Tcharidx:tinyint, Toname:varchar, Code:int, Serial:varchar",
    "PersonalStoreNostack": "Edate:datetime, Userindex:int, Charidx:tinyint, FromName:varchar, Tuserindex:int, Tcharidx:tinyint, Toname:varchar, Code:int, Serial:varchar",
    "ExchangeEvent": "Edate:datetime, Userindex:int, Charidx:tinyint, Channel:tinyint, Poridx:tinyint, Suserindex:int, Scharidx:tinyint, Scharname:varchar, "
                     "Code:int, Serial:varchar, Amount:int, Ramount:int, UpCount:tinyint, Gm:int, State:varchar",
    "ExchangeRegi": "Edate:datetime, Userindex:int, Charidx:tinyint, Channel:tinyint, Poridx:tinyint, Code:int, Serial:varchar, Amount:int, Ramount:int",
    "ExchangeRegiFunctional": "Edate:datetime, Userindex:int, Charidx:tinyint, Channel:tinyint, Poridx:tinyint, Code:int, Serial:varchar, Amount:int",
    "ExchangeRegiGear": "Edate:datetime, Userindex:int, Charidx:tinyint, Channel:tinyint, Poridx:tinyint, Code:int, Serial:varchar, Cell1:smallint",
    "ExchangeRegiSowel": "Edate:datetime, Userindex:int, Charidx:tinyint, Channel:tinyint, Poridx:tinyint, Code:int, Serial:varchar",
    "ExchangeRegiNoStack": "Edate:datetime, Userindex:int, Charidx:tinyint, Channel:tinyint, Poridx:tinyint, Code:int, Serial:varchar",
    "MoneyExchangeFee": "Edate:datetime, Userindex:int, Charidx:tinyint, Serial:varchar, Amount:int, Ramount:int",
    "ItemEvent": "Edate:datetime, Userindex:int, Charidx:tinyint, Code:int, Serial:varchar, Amount:int, Ramount:int, State:varchar",
    "LogInfo": "idx:bigint, Seridx:tinyint, Userindex:int, Charidx:tinyint, IpAddress:varchar, Mac:varchar, Login:datetime, Logout:datetime, State:tinyint",
}
A, B, C, D, S = (9001, 0, "Alpha"), (9002, 0, "Beta"), (9003, 0, "Gamma"), (9004, 0, "Delta"), (3, 0, "Svc")
E5, F6 = (9005, 0, "Eps"), (9006, 0, "Phi")    # ★ ревизия 54: продавец и покупатель снаряжения на аукционе
DAY = datetime.datetime(2026, 10, 5)          # фиксированные сутки синтетики: период запроса задаётся явно (полночь запуска не влияет)
Q = {"from": "20261001", "to": "20261010"}


def _ddl(table, spec):
    """CREATE TABLE по строке «столбец:тип, …»."""
    cols = []
    for part in spec.split(","):
        n, t = [x.strip() for x in part.split(":")]
        cols.append("[%s] %s NULL" % (n, "VARCHAR(%d)" % _V.get(n, 50) if t == "varchar" else t.upper()))
    return "CREATE TABLE dbo.%s (%s)" % (table, ", ".join(cols))


def _ins(cur, table, **v):
    """INSERT строки (столбцы — параметрами)."""
    cur.execute("INSERT dbo.%s (%s) VALUES (%s)" % (table, ", ".join("[%s]" % k for k in v), ", ".join("?" * len(v))), list(v.values()))


def _tr(cur, table, at, g, r, **v):
    """Строка Trade* / PersonalStore*: Userindex/Charidx/Fromname = g, Tuserindex/Tcharidx/Toname = r."""
    tu = "TUserindex" if table in ("TradeSowel", "TradeNoStack") else "Tuserindex"
    tc = "TCharidx" if table in ("TradeSowel", "TradeNoStack") else "Tcharidx"
    fn = "FromName" if table in ("PersonalStoreFunctional", "PersonalStoreSowel", "PersonalStoreNostack") else "Fromname"
    _ins(cur, table, Edate=at, Userindex=g[0], Charidx=g[1], **{fn: g[2], tu: r[0], tc: r[1], "Toname": r[2]}, **v)


def sandbox(check, ldb):
    """Свои базы LocalDB: граф, пары M3, зеркала, цепочки, сеть по праву, рынок, лавки, нет таблицы."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from core import db
    from domains import trade as T
    import domains
    domains.load_all()
    sys.path.insert(0, os.path.join(PORT, "AstoryServer", "Patches", "Gp7Gateway", "stand"))
    import reconcile_stand as R
    from selftest_money_a6 import _fill
    _chain_speed(check, T)
    tag = secrets.token_hex(3)
    names = {"Y": "AsdaTrY_" + tag, "G": "AsdaTrG_" + tag, "O": "AsdaTrO_" + tag, "L": "AsdaTrL_" + tag}
    m = ldb("master")
    for k in ("Y", "G", "O"):
        m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names[k])
    m.cursor().execute("CREATE DATABASE [%s] COLLATE SQL_Latin1_General_CP1_CI_AS" % names["L"])
    saved_files = T.selfstore_files
    try:
        yc = ldb(names["Y"]).cursor()
        yc.execute(R.ddl("Joy1", "dbo.Charinfo"))
        for u in (A, B, C, D, S, E5, F6):
            _fill(yc, "Joy1", "dbo.Charinfo", {"Userindex": u[0], "Charidx": u[1], "Uid": "acc_" + u[2].lower(), "Charname": u[2], "Lvl": 10}, R)
        yc.execute("CREATE TABLE dbo.Exitem (Eid UNIQUEIDENTIFIER, idx INT, Gidx TINYINT, State TINYINT, Userindex INT, Charidx TINYINT, "
                   "Charname VARCHAR(20), Code INT, Plate TINYINT, Amount INT, Upcount TINYINT, Sprice INT, Stime TINYINT, Gaindate DATETIME, Fdate DATETIME)")
        yc.execute("INSERT dbo.Exitem VALUES (NEWID(), 1, 0, 0, 9003, 0, 'Gamma', 600, 2, 10, 0, 5000, 24, ?, ?)", (DAY, DAY + datetime.timedelta(days=1)))
        yc.execute("INSERT dbo.Exitem VALUES (NEWID(), 2, 0, 0, 3, 0, 'Svc', 600, 2, 1, 0, 100, 24, ?, ?)", (DAY, DAY + datetime.timedelta(days=1)))
        # ★ ревизия 54 Н-1: лот снаряжения (Plate 1, Amount 0) — одна штука, цена за штуку = цене лота
        yc.execute("INSERT dbo.Exitem VALUES (NEWID(), 3, 0, 0, 9005, 0, 'Eps', 30001, 1, 0, 0, 700, 24, ?, ?)", (DAY, DAY + datetime.timedelta(days=1)))
        yc.execute("CREATE TABLE dbo.ItemPostBox (iType TINYINT, Orderidx INT, Userindex INT, Charidx TINYINT, Code INT, Amount TINYINT)")
        yc.execute("CREATE TABLE dbo.gifts (iType TINYINT, Orderidx INT, Userindex INT, Charidx TINYINT, Code INT, Amount TINYINT)")
        yc.execute("INSERT dbo.ItemPostBox VALUES (1, 501, 9002, 0, 70001, 1), (3, 77, 9001, 0, 555, 1)")
        yc.execute("INSERT dbo.gifts VALUES (34, 3030304, 2, 10, 492, 1)")
        yc.execute("CREATE TABLE dbo.CharPos (Userindex INT, Charidx TINYINT, UserNum INT)")
        oc = ldb(names["O"]).cursor()
        oc.execute("CREATE TABLE dbo.Us_member (Userindex INT, Us_id VARCHAR(20), Flag INT, UserNum INT)")
        for u in (A, B, C, D, S, E5, F6):
            oc.execute("INSERT dbo.Us_member VALUES (?, ?, 0, -1)", (u[0], "acc_" + u[2].lower()))
        gc = ldb(names["G"]).cursor()
        for t, spec in SCHEMA.items():
            gc.execute(_ddl(t, spec))
        at = lambda h, mi=0, d=0: DAY + datetime.timedelta(days=d, hours=h, minutes=mi)
        # обмен: A отдал B 2 000 000 (From — баланс A 5 000 000 → 3 000 000; To — баланс B 100 → 2 000 100, Userindex = отдавший A)
        _tr(gc, "TradeGoldFrom", at(10), A, B, Serial="G-A", Amount=5000000, Ramount=3000000)
        _tr(gc, "TradeGoldTo", at(10), A, B, Serial="G-B", Amount=100, Ramount=2000100)
        _tr(gc, "TradeItemFrom", at(10, 5), B, A, Code=555, Serial="I-555", Amount=3, Ramount=0)
        _tr(gc, "TradeitemTo", at(10, 5), B, A, Code=555, Serial="I-555", Tserial="I-555", Amount=0, Ramount=3)
        for i in range(5):
            _tr(gc, "TradeSowel", at(10, 10 + i), A, C, Code=7100, Serial="S-%d" % i)
        _tr(gc, "TradeItemFrom", at(10, 20), A, C, Code=600, Serial="ser-x", Amount=2, Ramount=0)
        _tr(gc, "TradeGoldFrom", at(9), S, A, Serial="G-S", Amount=2000000, Ramount=500000)           # служебная → A 1 500 000
        _tr(gc, "TradeGoldFrom", at(10, d=-15), A, B, Serial="G-old", Amount=10000000, Ramount=1)    # 20.09 — вне периода
        # лавка: продавец C (Userindex), покупатель B (Tuserindex): вещь C → B, 500 золота B → C (строка From — баланс продавца 100 → 600)
        _tr(gc, "PersonalStoreitemFrom", at(11), C, B, Code=600, Serial="SER-X", Amount=2, Ramount=0)
        _tr(gc, "PersonalStoreitemTo", at(11), C, B, Code=600, Serial="SER-X", Amount=0, Ramount=2)
        _tr(gc, "PersonalStoreGoldFrom", at(11), C, B, Serial="G-C", Amount=100, Ramount=600)
        _tr(gc, "PersonalStoreGoldTo", at(11), C, B, Serial="G-B2", Amount=1000, Ramount=500)
        _tr(gc, "TradeItemFrom", at(13), B, D, Code=600, Serial="SER-X", Amount=2, Ramount=0)
        # аукцион: B купил у D 4 × 777 за 1000; зеркало Sold out у D; снятие лота D; регистрация D
        _ins(gc, "ExchangeEvent", Edate=at(12), Userindex=B[0], Charidx=0, Channel=1, Poridx=0, Suserindex=D[0], Scharidx=0, Scharname="Delta", Code=777,
             Serial="E-1", Amount=0, Ramount=4, Gm=1000, State="Purchase at the Exchange")
        _ins(gc, "ExchangeEvent", Edate=at(12), Userindex=D[0], Charidx=0, Channel=1, Poridx=0, Suserindex=B[0], Scharidx=0, Scharname="Beta", Code=777,
             Serial="E-1", Amount=4, Ramount=0, Gm=1000, State="Sold out at the Exchange")
        _ins(gc, "ExchangeEvent", Edate=at(14), Userindex=D[0], Charidx=0, Channel=1, Poridx=0, Suserindex=D[0], Scharidx=0, Scharname="Delta", Code=778,
             Serial="E-2", Amount=0, Ramount=1, Gm=50, State="Registration Cancel")
        _ins(gc, "ExchangeRegi", Edate=at(8), Userindex=D[0], Charidx=0, Channel=1, Poridx=0, Code=777, Serial="E-1", Amount=4, Ramount=0)
        # ★ ревизия 54 Н-1: F купил у E снаряжение (Amount 0 → 0 в строке «Purchase»); Н-2: снятие по сроку — удалён без возврата (Amount =
        #   Ramount = 5) и возврат (0 → 3)
        _ins(gc, "ExchangeEvent", Edate=at(15), Userindex=F6[0], Charidx=0, Channel=1, Poridx=0, Suserindex=E5[0], Scharidx=0, Scharname="Eps", Code=30001,
             Serial="E-3", Amount=0, Ramount=0, Gm=900, State="Purchase at the Exchange")
        _ins(gc, "ExchangeEvent", Edate=at(16), Userindex=E5[0], Charidx=0, Channel=200, Poridx=200, Suserindex=E5[0], Scharidx=0, Scharname="Eps",
             Code=779, Serial="E-4", Amount=5, Ramount=5, Gm=0, State="Time Out-Delete")
        _ins(gc, "ExchangeEvent", Edate=at(17), Userindex=E5[0], Charidx=0, Channel=200, Poridx=200, Suserindex=E5[0], Scharidx=0, Scharname="Eps",
             Code=780, Serial="E-5", Amount=0, Ramount=3, Gm=10, State="Time Out-Return")
        _ins(gc, "MoneyExchangeFee", Edate=at(8), Userindex=D[0], Charidx=0, Serial="F", Amount=1000, Ramount=950)
        _ins(gc, "MoneyExchangeFee", Edate=at(8), Userindex=S[0], Charidx=0, Serial="F", Amount=100, Ramount=93)
        _ins(gc, "ItemEvent", Edate=at(12), Userindex=D[0], Charidx=0, Code=20551, Serial="F", Amount=1030, Ramount=1000, State="Commission at the Exchange")
        _ins(gc, "ItemEvent", Edate=at(14), Userindex=A[0], Charidx=0, Code=20551, Serial="F", Amount=100, Ramount=110,
             State="Commision Refund on a registration")
        _ins(gc, "ItemEvent", Edate=at(14), Userindex=A[0], Charidx=0, Code=999, Serial="F", Amount=1, Ramount=5, State="Commission at the Exchange")
        # входы: A и B — один публичный IP в разное время, A и D — один MAC, служебная — частный адрес, C — свой IP
        li = 0
        for u, ip, mac, h in ((A, "8.8.8.8", "AC-DE-48-00-11-22", 8), (B, "8.8.8.8", "AC-DE-48-00-33-44", 9), (C, "1.1.1.1", "AC-DE-48-00-55-66", 9),
                              (D, "9.9.9.9", "AC-DE-48-00-11-22", 15), (S, "192.168.1.1", "00-15-5D-00-00-01", 7), (B, "8.8.4.4", "AC-DE-48-00-33-44", 9)):
            li += 1
            _ins(gc, "LogInfo", idx=li, Seridx=1, Userindex=u[0], Charidx=0, IpAddress=ip, Mac=mac, Login=at(h), Logout=at(h, 30), State=0)
        lc = ldb(names["L"]).cursor()
        lc.execute("CREATE TABLE dbo.GP7GiftLog (order_id BIGINT, sender_user_id BIGINT, sender_userindex INT, sender_charidx INT, sender_name VARCHAR(20), "
                   "recipient_name VARCHAR(20), code1 BIGINT, code2 BIGINT, code3 BIGINT, code4 BIGINT, code5 BIGINT, code6 BIGINT, code7 BIGINT, amount BIGINT, "
                   "state CHAR(1), test_mode BIT, created_at DATETIME2, settled_at DATETIME2)")
        shift = int(round(lc.execute("SELECT DATEDIFF(second, SYSUTCDATETIME(), SYSDATETIME())").fetchone()[0] / 900.0)) * 15
        for oid, st, tm in ((501, "C", 0), (502, "H", 0), (503, "R", 1)):
            lc.execute("INSERT dbo.GP7GiftLog VALUES (?, 1, 9001, 0, 'Alpha', 'Beta', 70001, NULL, NULL, NULL, NULL, NULL, NULL, 399, ?, ?, ?, NULL)",
                       (oid, st, tm, at(10, 30) - datetime.timedelta(minutes=shift)))
        mp = {"Joy1": names["Y"], "joylog1": names["G"], "AsdaStoryOp": names["O"], "AsdaStoryLogin": names["L"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        sample = ["10 Mon 05 Day 10 hou 59 min 00 sec : [OPEN]\tHostNum:0\tHostIndex:9003\tHostName:Gamma",
                  "10 Mon 05 Day 10 hou 59 min 00 sec : [OPEN]\tItemIndex:600\tPlate:2\tPosX:1\tAmount:2\tGold:250",
                  "10 Mon 05 Day 11 hou 00 min 00 sec : [BUY]\tDB Send..!!\tHostNum:0\tHostIndex:9003\tHostName:Gamma\tBuyNum:1\tBuyIndex:9002\tBuyName:Beta\tTotalGold:500",
                  "10 Mon 05 Day 11 hou 00 min 00 sec : [INSERT]\tDB Success..!!\tHostNum:0\tHostIndex:9003\tHostName:Gamma\tBuyNum:1\tBuyIndex:9002\tBuyName:Beta\tTotalGold:500",
                  "10 Mon 05 Day 11 hou 05 min 00 sec : [RETURN]\tHostNum:0\tHostIndex:9003\tHostName:Gamma"]
        seen_user = []

        def fake_files(f, t, errors, user=None, unread=None):
            seen_user.append(user)
            if f == "20261001" and t == "20261009" and unread is not None:      # список «обрезан»: дни до 06.10 не прочитаны
                unread.append({"proc": "GameServer", "before": "20261006", "listed": 60, "total": 75})
                return []
            return [("GameServer", "SelfStore_20261005.txt", "20261005", sample)] if f <= "20261005" <= t else []
        T.selfstore_files = fake_files
        seen = []
        orig = db.GameReader.rows

        def spy(self, sql, params=()):
            seen.append((self.name, sql))
            return orig(self, sql, params)
        db.GameReader.rows = spy
        try:
            _checks(check, T, gc, seen, seen_user)
            check("передачи стенд: все %d запросов к игровым базам — чтение (assert_select_only), без русских букв и «SELECT *»" % len(seen),
                  seen and not any(CYR.search(s) or "select *" in s.lower() for _n, s in seen), [s[:100] for _n, s in seen if CYR.search(s)][:3])
        finally:
            db.GameReader.rows = orig
    finally:
        T.selfstore_files = saved_files
        from core import db as _db
        _db.set_override("game", None)
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def _chain_speed(check, T):
    """★ ревизия 54 В-1: цепочки — один проход O(E log E): 5 000 и 50 000 синтетических передач (3 «узла» и 60 игроков, как в замере ревизии,
    и случайные пары 2 000 учёток) укладываются с большим запасом в порог, без обрезки по времени; прежний перебор на 300 передачах шёл 54 с."""
    import random
    import time
    rnd = random.Random(54)
    base = datetime.datetime(2026, 10, 1)

    def syn(n, hubs):
        out = []
        for i in range(n):
            if hubs:
                a = rnd.choice([9001, 9002, 9003]) if i % 2 else rnd.randint(9100, 9160)
                b = rnd.randint(9100, 9160) if i % 2 else rnd.choice([9001, 9002, 9003])
            else:
                a, b = rnd.randint(9100, 11100), rnd.randint(9100, 11100)
            out.append({"t": base + datetime.timedelta(seconds=i * 7), "group": "trade", "src": "TradeGoldFrom", "what": "gold", "fu": a, "fi": 0,
                        "fn": None, "tu": b, "ti": 0, "tn": None, "code": None, "qty": rnd.randint(1, 1000), "serial": None})
        return out
    res = []
    for n, hubs, lim in ((300, True, 2.0), (5000, True, 3.0), (5000, False, 3.0), (50000, True, 15.0), (50000, False, 15.0)):
        ed = syn(n, hubs)
        t0 = time.monotonic()
        ch, cap = T.chains(ed, deadline_s=60)
        dt_ = time.monotonic() - t0
        res.append((n, hubs, round(dt_, 2), len(ch["all"]), cap, lim))
    check("передачи стенд (ревизия 54 В-1): цепочки одним проходом — 300 / 5 000 / 50 000 передач (узлы и случайные пары) быстрее порога "
          "(2 / 3 / 15 с), без обрезки: %s" % ", ".join("%d%s %.2f с" % (n, "у" if h else "с", d) for n, h, d, _k, _c, _l in res),
          all(d < lim and not cap and k > 0 for _n, _h, d, k, cap, lim in res), res)
    ch, cap = T.chains(syn(50000, False), deadline_s=0.0)
    check("передачи стенд (ревизия 54 В-1): предел времени разбора цепочек — пометка «обрезано»", cap)


class _Req:
    """Запрос маршрута самотеста: строка запроса и право сети."""

    def __init__(self, q, net):
        self.query, self._net = q, net

    def can(self, perm):
        return self._net if perm == "players.view_net" else True


def _checks(check, T, gc, seen, seen_user):
    g = T.graph(dict(Q), can_net=True)
    pr = {(p["a"], p["b"]): p for p in g["pairs"]}
    sp = {(p["a"], p["b"]): p for p in g["service_pairs"]}
    src = {s["key"]: s["rows"] for s in g["sources"]}
    check("передачи стенд: строк источников за период — обмен золотом 2 (вне периода не попала), стопки 3, совелы 5, лавка 1 + 1, аукцион 1 + 1, "
          "подарок gp7 1 (выдан), без ошибок",
          src.get("TradeGoldFrom") == 2 and src.get("TradeItemFrom") == 3 and src.get("TradeSowel") == 5 and src.get("PersonalStoreitemFrom") == 1
          and src.get("PersonalStoreGoldFrom") == 1 and src.get("ExchangeItem") == 2 and src.get("ExchangeGold") == 2 and src.get("GP7GiftLog") == 1
          and not g["errors"], (src, g["errors"]))
    ab = pr.get((9001, 9002)) or {}
    check("передачи стенд: зеркала не двоятся — A → B золото ровно 2 000 000 (строки TradeGoldTo нет в передачах), B → A вещи 3 (TradeitemTo не считается)",
          ab.get("gold_ab") == 2000000 and ab.get("items_ba") == 3 + 0 and ab.get("gold_ba") == 0
          and {m["table"]: m["rows"] for m in g["mirrors"]} == {"TradeGoldTo": 1, "TradeitemTo": 1, "TradeShellGoldTo": 0, "PersonalStoreGoldTo": 1,
                                                               "PersonalStoreitemTo": 1, "ExchangeEvent": 1}, (ab, g["mirrors"]))
    check("передачи стенд: асимметрия M3 — A → B золото 2 000 000 без обратного (вещи обратно 3), A ↔ C ≥ 5 записей (совелы + стопка)",
          {"type": "oneway", "from": 9001, "to": 9002, "value": 2000000} in ab.get("flags", []) and pr[(9005, 9006)]["items_ab"] == 1
          and [x["type"] for x in (pr.get((9001, 9003)) or {}).get("flags", [])] == ["deals"] and pr[(9001, 9003)]["deals"] == 6, (ab, pr.get((9001, 9003))))
    bc, bd = pr.get((9002, 9003)) or {}, pr.get((9002, 9004)) or {}
    check("передачи стенд: владелец строк лавки и аукциона — вещь продавец → покупатель, золото покупатель → продавец (B заплатил C 500 и D 1000, "
          "получил от C 2 штуки и от D 4), «Sold out» не двоится",
          bc.get("gold_ab") == 500 and bc.get("gold_ba") == 0 and bc.get("items_ba") == 2 and bd.get("gold_ab") == 1000 and bd.get("items_ba") == 4
          and bd.get("items_ab") == 2 and bd.get("groups") == {"auction": 2, "trade": 1}, (bc, bd))
    check("передачи стенд: подарок gp7 (выдан, C) — передача A → B; заморожен и возвращён — только счётом; в ящике сейчас 1 заказ подарка",
          ab.get("groups", {}).get("gift") == 1 and g["gifts"] == {"states": {"C": 1, "H": 1, "R": 1}, "test": 1, "unresolved": 0}
          and g["box"]["gift_orders"] == 1 and g["box"]["gifts_rows"] == 1, (ab.get("groups"), g["gifts"], g["box"]))
    check("передачи стенд: служебная учётка ≤ 5000 — отдельным списком (3 → A, флаг M3), не в общем итоге; svc=in — в общем списке",
          (3, 9001) in sp and (3, 9001) not in pr and sp[(3, 9001)]["flags"] and g["totals"]["total"]["pairs"] == g["totals"]["cats"]["player"]["pairs"]
          and (3, 9001) in {(p["a"], p["b"]) for p in T.graph(dict(Q, svc="in"), can_net=False)["pairs"]}, (list(sp), g["totals"]))
    cn = sorted(tuple(c["nodes"]) for c in g["chains"])
    sc = sorted(tuple(c["nodes"]) for c in g["service_chains"])
    check("передачи стенд: цепочки игроков A → B → C и A → B → D (служебная цепочка их не поглощает), служебные — 3 → A → B → …",
          (9001, 9002, 9003) in cn and (9001, 9002, 9004) in cn and all(3 not in c for c in cn) and any(c[:3] == (3, 9001, 9002) for c in sc), (cn, sc))
    check("передачи стенд: серийник SER-X (регистр не важен) — 3 передачи A → C → B → D",
          [(x["serial"], x["n"], [(e["fu"], e["tu"]) for e in x["path"]]) for x in g["serials"]] ==
          [("SER-X", 3, [(9001, 9003), (9003, 9002), (9002, 9004)])], g["serials"])
    ips = {x["value"]: [a["uid"] for a in x["accounts"]] for x in g["net"]["ip"]}
    macs = {x["value"]: [a["uid"] for a in x["accounts"]] for x in g["net"]["mac"]}
    check("передачи стенд: один IP — A и B (8.8.8.8), один MAC — A и D; частный адрес и MAC Hyper-V служебной не связывают; связь пары A ↔ B — "
          "«IP (не пересекались)» (players.link_degree)",
          ips == {"8.8.8.8": [9001, 9002]} and macs == {"AC-DE-48-00-11-22": [9001, 9004]} and ab.get("link") == "ip_apart"
          and pr[(9001, 9003)].get("link") is None, (ips, macs, ab.get("link")))
    n0 = len(seen)
    g2 = T.graph(dict(Q), can_net=False)
    check("передачи стенд: без права сети — IP и MAC не читаются (запросов к LogInfo нет), групп нет, связи у пар нет",
          g2["net"] is None and g2["net_hidden"] and not any("LogInfo" in s for _n, s in seen[n0:]) and all("link" not in p for p in g2["pairs"]))
    from api import server
    fn, _perm = _route("/api/trade/graph")
    r_no, r_yes = fn(_Req(dict(Q), False), None), fn(_Req(dict(Q), True), None)
    check("передачи стенд: маршрут /api/trade/graph настоящей функцией — без players.view_net сети нет, с правом — есть",
          r_no["net"] is None and r_no["net_hidden"] and r_yes["net"] and r_yes["net"]["ip"] and server is not None)
    gd = T.graph(dict(Q, account="acc_delta"), can_net=False)
    check("передачи стенд: отбор учётки (логин) — только пары с D", {(p["a"], p["b"]) for p in gd["pairs"]} == {(9002, 9004)}, [(p["a"], p["b"]) for p in gd["pairs"]])
    tr = T.transfers(dict(Q, pair="9002-9001", size="2"))
    tall = T.transfers(dict(Q, pair="9001-9002"))
    check("передачи стенд: передачи пары A ↔ B — золото, вещи обратно и подарок (3 строки), страницы по 2, новые сверху",
          tall["total"] == 3 and tr["pages"] == 2 and len(tr["rows"]) == 2 and tr["rows"][0]["t"] >= tr["rows"][1]["t"]
          and {(x["src"], x["fu"], x["tu"], x["qty"]) for x in tall["rows"]} == {("TradeGoldFrom", 9001, 9002, 2000000), ("TradeItemFrom", 9002, 9001, 3),
                                                                                ("GP7GiftLog", 9001, 9002, 1)}, tall["rows"])
    mk = T.market(dict(Q))
    pc = {p["code"]: p for p in mk["prices"]}
    check("передачи стенд: рынок — живые лоты 3, служебный лот — отдельным списком (svc=sep), цена за штуку 500, цены без служебного лота, "
          "продано 777: 4 штуки по 250; снаряжение без стопки (Amount 0) — 1 штука: лот 700 за штуку, продано 30001 × 1 по 900 (ревизия 54 Н-1, Н-5)",
          mk["lots_total"] == 3 and sorted(x["unit"] for x in mk["lots"]) == [500.0, 700.0] and [x["uid"] for x in mk["service_lots"]] == [3]
          and [x["nostack"] for x in mk["lots"] if x["code"] == 30001] == [True] and pc[600]["listed"] == 1 and pc[600]["lmin"] == 500.0
          and pc[777]["sold"] == 1 and pc[777]["sold_qty"] == 4 and pc[777]["savg"] == 250.0 and pc[30001]["sold_qty"] == 1 and pc[30001]["savg"] == 900.0
          and pc[30001]["listed_qty"] == 1 and not mk["errors"], (mk["prices"], mk["errors"]))
    mi = T.market(dict(Q, svc="in"))
    check("передачи стенд: рынок svc=in — служебный лот в общем списке, отдельного нет", len(mi["lots"]) == 3 and not mi["service_lots"])
    tx = mk["tax"]
    check("передачи стенд: налог — сбор за выставление 50 (служебные 7 отдельно), сбор с продажи 30, возврат 10 (не золото не считается), итого 70",
          tx["total"]["fee"] == 50 and tx["cats"]["service"]["fee"] == 7 and tx["total"]["commission"] == 30 and tx["total"]["refund"] == 10
          and tx["total"]["net"] == 70, tx)
    hs = [(x["kind"], x["state"]) for x in mk["history"]]
    hq = {x["state"]: x["qty"] for x in mk["history"] if x["kind"] == "event" and x["code"] in (779, 780, 30001)}
    check("передачи стенд: история аукциона — 7 строк (2 покупки, зеркало, снятие продавцом, удалён по сроку, возврат по сроку, регистрация), "
          "зеркало и «вещь пропала» помечены; количество: удалён без возврата 5, возврат 3, снаряжение 1 (ревизия 54 Н-1, Н-2)",
          mk["hist_total"] == 7 and len(hs) == 7 and [x["mirror"] for x in mk["history"] if x["state"] == "Sold out at the Exchange"] == [True]
          and [x["deleted"] for x in mk["history"] if x["state"] == "Time Out-Delete"] == [True]
          and hq == {"Time Out-Delete": 5, "Time Out-Return": 3, "Purchase at the Exchange": 1}
          and mk["hist_counts"] == {"regi": 1, "Purchase at the Exchange": 2, "Sold out at the Exchange": 1, "Registration Cancel": 1,
                                    "Time Out-Delete": 1, "Time Out-Return": 1} and mk["service_hist_total"] == 0, (hs, hq, mk["hist_counts"]))
    st = T.stores(dict(Q))
    d5 = [d for d in st["days"] if d["day"] == "20261005"]
    check("передачи стенд: лавки — 1 сделка (продавец C, покупатель B, золото 500, вещь 600 × 2), сверка с журналом: покупок 1, подтверждено 1, "
          "открытые лавки — пометка «показать нельзя»",
          st["sales_total"] == 1 and st["sales"][0]["su"] == 9003 and st["sales"][0]["bu"] == 9002 and st["sales"][0]["gold"] == 500
          and st["sales"][0]["items"][0]["qty"] == 2 and d5 and d5[0]["sales"] == 1 and d5[0]["log_buy"] == 1 and d5[0]["log_ok"] == 1
          and st["log"]["events_total"] == 4 and "показать нельзя" in st["open_note"] and not st["errors"], (st["sales"], st["days"], st["errors"]))
    tsv = T.transfers(dict(Q))
    check("передачи стенд (ревизия 54 Н-5): передачи svc=sep — служебная 3 → A отдельным списком, в общем её нет; svc=in — в общем",
          tsv["service_total"] == 1 and [(x["fu"], x["tu"]) for x in tsv["service_rows"]] == [(3, 9001)] and all(x["cat"] == "player" for x in tsv["rows"])
          and any(x["fu"] == 3 for x in T.transfers(dict(Q, svc="in"))["rows"]), (tsv["service_total"], tsv["service_rows"]))
    gt = T.graph(dict(Q, group="trade"), can_net=False)
    check("передачи стенд: вид trade — только зеркала обмена (без лавки и аукциона)", {m["table"] for m in gt["mirrors"]} == {"TradeGoldTo", "TradeitemTo", "TradeShellGoldTo"},
          gt["mirrors"])
    stu = T.stores(dict(Q), "tester")
    check("передачи стенд (ревизия 54 Н-4): бюджет журнала лавок — на пользователя запроса (tester)", seen_user[-1] == "tester" and stu["sales_total"] == 1)
    su = T.stores({"from": "20261001", "to": "20261009"})
    d5u = [d for d in su["days"] if d["day"] == "20261005"]
    check("передачи стенд (ревизия 54 Н-3): дни раньше прочитанного списка журнала — «журнал не прочитан», пометка в notes",
          d5u and d5u[0]["log_unread"] and d5u[0]["log_buy"] is None and su["notes"] == [
              "журнал лавок GameServer за дни до 20261006 не прочитан (в списке файлов только 60 новых из 75)"], (su["days"], su["notes"]))
    st0 = T.stores(dict(Q, logs="0"))
    check("передачи стенд: лавки без журнала (logs=0) — журнал не читается", st0["log"] is None and st0["sales_total"] == 1)
    gc.execute("DROP TABLE dbo.TradeShellGoldFrom")
    g3 = T.graph(dict(Q), can_net=False)
    check("передачи стенд: таблицы TradeShellGoldFrom нет — строка ошибки «журнал передач TradeShellGoldFrom не прочитан», остальное считается",
          any(e.startswith("журнал передач TradeShellGoldFrom не прочитан:") for e in g3["errors"]) and g3["totals"]["edges"] == g2["totals"]["edges"],
          g3["errors"])


# ---------------------------------------------------------------- живая dev

def live(check):
    """Живая dev: чтение игровых баз (asda_admin) — счёт строк = COUNT(*) за тот же период, служба на сервере."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db
    from domains import trade as T
    import domains
    domains.load_all()
    if config.get().on_server:
        return check("живой самотест А6.4 — с ПК", True)
    g = T.graph({"svc": "in"}, can_net=True)
    f, t = g["period"]["from"], g["period"]["to"]
    cnt, mir = {}, {}
    with db.GameReader("joylog1") as lg:
        for s in T.EDGES:
            cnt[s["key"]] = int(lg.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE %s%s" % (s["table"], T.WINDOW, (" AND " + s["extra"]) if s.get("extra") else ""),
                                       (f, t))["n"])
        for m in T.MIRRORS:
            mir[m["table"] + (":sold" if m.get("extra") else "")] = int(lg.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE %s%s" % (
                m["table"], T.WINDOW, (" AND " + m["extra"]) if m.get("extra") else ""), (f, t))["n"])
        tabs = sorted(r["name"] for r in lg.rows("SELECT name FROM sys.tables WHERE name LIKE 'Trade%' OR name LIKE 'PersonalStore%'"))
        hist = sum(int(lg.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE %s" % (h["table"], T.WINDOW), (f, t))["n"]) for h in T.HISTORY)
        fee = lg.one("SELECT SUM(CAST(Amount AS BIGINT) - CAST(Ramount AS BIGINT)) AS s FROM dbo.MoneyExchangeFee WHERE %s" % T.WINDOW, (f, t))["s"] or 0
        nli = int(lg.one("SELECT COUNT(*) AS n FROM dbo.LogInfo WHERE Login >= CONVERT(datetime2, ?, 112) AND Login < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))",
                         (f, t))["n"])
    with db.GameReader("joy1") as j:
        lots = int(j.one("SELECT COUNT(*) AS n FROM dbo.Exitem")["n"])
    got = {s["key"]: s["rows"] for s in g["sources"] if s["key"] != "GP7GiftLog"}
    check("живое: строк каждого источника передач = COUNT(*) за период %s — %s (%d источников, всего %d)" % (f, t, len(cnt), sum(cnt.values())),
          got == cnt and not g["errors"], ({k: (got.get(k), v) for k, v in cnt.items() if got.get(k) != v}, g["errors"]))
    gm = {m["table"] + (":sold" if m["sold"] else ""): m["rows"] for m in g["mirrors"]}
    check("живое: зеркала (не считаются) — строк = COUNT(*): %s" % mir, gm == mir, gm)
    known = {s["table"].lower() for s in T.EDGES} | {m["table"].lower() for m in T.MIRRORS}      # имена в базе — без учёта регистра (TradeitemFrom)
    check("живое: каждая таблица Trade* / PersonalStore* живой JoyLog1 (%d) — источник или зеркало (новых без разбора нет)" % len(tabs),
          tabs and all(x.lower() in known for x in tabs), [x for x in tabs if x.lower() not in known])
    check("живое: правило M3 — модуль с ПК (исходник AstoryServer/Tools/Anticheat), пороги M3/M4 из ac_common.THR (%s)" % g["thr"],
          g["m3_from"] == "Anticheat" and g["thr"]["m3_pair_deals"] >= 1)
    check("живое: сеть — входы LogInfo за период прочитаны (%d строк), без ошибок" % nli, g["net"] is not None and not g["net"]["capped"])
    mk = T.market({"svc": "in"})
    check("живое: рынок — лотов = COUNT Exitem (%d), история = COUNT за период (%d), сбор за выставление = SUM (%d)" % (lots, hist, fee),
          mk["lots_total"] == lots and mk["hist_total"] == hist and mk["tax"] and mk["tax"]["total"]["fee"] == fee and not mk["errors"],
          (mk["lots_total"], mk["hist_total"], mk["tax"], mk["errors"]))
    st = T.stores({"svc": "in"})
    nsale = sum(1 for e in T.collect(f, t, [], groups={"store"})[0] if e["src"] == "PersonalStoreGoldFrom")
    check("живое: лавки — сделок не меньше строк оплаты PersonalStoreGoldFrom (%d), журнал Log_SelfStore прочитан, без ошибок" % cnt["PersonalStoreGoldFrom"],
          st["sales_total"] >= nsale == cnt["PersonalStoreGoldFrom"] and st["log"] is not None and not st["errors"], (st["sales_total"], st["errors"]))
    probe = ("import sys\nsys.path.insert(0, '.')\nimport os\nfrom domains import trade as T\n"
             "M = T.m3()\ng = T.graph({'from': %r, 'to': %r, 'svc': 'in'}, can_net=False)\n"
             "print('TRPROBE ext=%%s edges=%%d err=%%d' %% (os.path.basename(os.path.dirname(M.LOADED_FROM)), g['totals']['edges'], len(g['errors'])))\n"
             % (f, t))
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
    mm = re.search(r"TRPROBE ext=(\w+) edges=(\d+) err=(\d+)", out)
    check("служба на сервере (SSH): правило M3 из ext/anticheat архива, передач столько же, сколько с ПК (%d), без ошибок" % g["totals"]["edges"],
          bool(mm) and mm.group(1) == "anticheat" and int(mm.group(2)) == g["totals"]["edges"] and mm.group(3) == "0", out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    sc = ssl.create_default_context()
    sc.check_hostname, sc.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=sc)).open(
            "https://%s:17890/api/trade/graph" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/trade/graph без входа — 401", code == 401, code)
