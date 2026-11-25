# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_ac_a6.py — самотест шага А6.1 «Античит» (21.11.2026; domains/acjournal.py, acjournal_src.py, /api/ac/*, web/acjournal.js,
консоль ac).

offline(check)  — каталог видов по AcJournal.cpp KindText (все 8 таблиц, номера уникальны, патч у каждого вида, служебные по §9, вид 60
                  только SQL, тернарные виды kick_block / identity_mismatch, 145–147 P96 не заведены и не пишутся, «?» — вид без текста; EN у каждого вида; служебные только по SERVICE_OTHER — ревизия 50), разбор подставного исходника
                  (повтор номера, нераспознанная строка, нет функции), фильтры и отказы (даты ГГГГММДД, IP без права, таблица, вид, размеры,
                  глубина ленты), тексты отказов без «; », права ролей, маршруты /api/ac/*, переводы EN (shadowed_translations = 0), веб
                  без innerHTML и без перевода данных, консоль (неизвестный ключ — отказ), выкладка кладёт каталог.
sandbox(check, ldb) — СВОИ базы LocalDB: настоящие миграции схемы ac (acdb_01, acdb_p55_01, acj2_01, autoban_01 — с подменой имён баз),
                  синтетика во всех 8 таблицах (служебные, неизвестный текст, «?», IP, серверы, разные сутки, кик и автоблок); лента: число,
                  порядок, служебные, каждый фильтр, IP без права, страницы; сводка: виды за сутки, топ (представление + без служебных),
                  учётки за сутки; маршруты API настоящими функциями; таблицы нет — строка ошибки, остальное считается.
live(check)     — только чтение живой joylog1 логином asda_admin: SELECT на 8 таблиц и 5 представлений, каждый вид живой базы есть в каталоге
                  и в переводах, лента = сумме COUNT(*) таблиц, служебных = числу по каталогу, сводка без ошибок, страница и фильтры; служба на
                  сервере (SSH, stdin) — каталог из data/ref/ac_kinds.json того же md5, лента считается; /api/ac/events без входа — 401.
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
SQL_DIR = os.path.join(PORT, "AstoryServer", "Docs", "SQL")
MIGRATIONS = ("acdb_01_migrate.sql", "acdb_p55_01_migrate.sql", "acj2_01_migrate.sql", "autoban_01_migrate.sql")


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


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n
    from domains import acjournal as A, acjournal_src as S

    # ---- каталог по исходнику
    cat = S.build()
    t = cat["tables"]
    check("античит: каталог KindText разобран без проблем, все 8 таблиц ac.*", not cat["problems"] and set(t) == set(A.TABLE_NAMES)
          and len(A.TABLES) == 8, cat["problems"][:5])
    nums = {k: [r["n"] for r in v] for k, v in t.items()}
    check("античит: номера видов в каждой таблице уникальны, тексты — тоже", all(len(v) == len(set(v)) for v in nums.values())
          and all(len({r["text"] for r in v}) == len(v) for v in t.values()), {k: len(v) for k, v in nums.items()})
    check("античит: число видов — operator_refusal 6, identity 2, login_check 3, kick_block 2, sign_replay 5, packet_validator 4, "
          "move_combat ≥ 32, other ≥ 135", [len(t[x]) for x in ("operator_refusal", "identity_mismatch", "login_check_refusal", "kick_block",
                                                              "sign_replay", "packet_validator")] == [6, 2, 3, 2, 5, 4]
          and len(t["move_combat"]) >= 32 and len(t["other"]) >= 135, {k: len(v) for k, v in t.items()})
    check("античит: у каждого вида есть патч по диапазонам §9", all(r["patch"] for v in t.values() for r in v),
          [(k, r["n"]) for k, v in t.items() for r in v if not r["patch"]][:5])
    by = {(k, r["n"]): r for k, v in t.items() for r in v}
    check("античит: тернарные виды — kick_block 1 «кик», 2 «автоблок»; identity_mismatch 1 «4001 вход в мир», 2 «5058 переход через портал»",
          by[("kick_block", 1)]["text"] == "кик" and by[("kick_block", 2)]["text"] == "автоблок"
          and by[("identity_mismatch", 1)]["text"] == "4001 вход в мир" and by[("identity_mismatch", 2)]["text"] == "5058 переход через портал")
    check("античит: опорные виды — other 3 P53 «неизвестный опкод», 77 P73 служебная, 10 «журнал: старт» служебная, 62 P69 не служебная, "
          "move_combat 103 N19, 24 P66, 23 P56b", by[("other", 3)]["patch"] == "P53" and "NotKnow" in by[("other", 3)]["text"]
          and by[("other", 77)]["patch"] == "P73" and by[("other", 77)]["service"] and by[("other", 10)]["service"]
          and by[("other", 10)]["text"] == "журнал: старт" and not by[("other", 62)]["service"] and by[("move_combat", 103)]["patch"] == "N19"
          and by[("move_combat", 24)]["patch"] == "P66" and by[("move_combat", 23)]["patch"] == "P56b")
    check("античит: вид 60 «SQL: ошибка процедуры, откат (A11c)» — только SQL (в коде номер не занят), НЕ служебный (ревизия 50 п.1: строки с учёткой)",
          by[("other", 60)]["sql"] and not by[("other", 60)]["service"] and by[("other", 60)]["text"] == "SQL: ошибка процедуры, откат (A11c)")
    check("античит: вид 156 P100 «расхождение памяти и БД / исключение…» — НЕ служебный (ревизия 50 п.2)", not by[("other", 156)]["service"])
    svc = [r for v in t.values() for r in v if r["service"]]
    check("античит: служебные — только ac.other по списку SERVICE_OTHER (журнал, мост EAC, без учётки, выключение патча) — %d видов, у каждого причина"
          % len(svc), svc and all(r in t["other"] for r in svc) and {r["n"] for r in svc} == set(S.SERVICE_OTHER)
          and all(isinstance(r["service"], str) and r["service"] for r in svc), sorted(r["n"] for r in svc))
    check("античит: каждый номер SERVICE_OTHER и NOT_SERVICE_WHY есть в каталоге ac.other, списки не пересекаются",
          all(("other", n) in by for n in list(S.SERVICE_OTHER) + list(S.NOT_SERVICE_WHY)) and not set(S.SERVICE_OTHER) & set(S.NOT_SERVICE_WHY),
          [n for n in list(S.SERVICE_OTHER) + list(S.NOT_SERVICE_WHY) if ("other", n) not in by])
    exc = [r["n"] for r in t["other"] if "исключение" in r["text"]]
    check("античит: все %d видов со словом «исключение» — НЕ служебные и с записанной причиной (NOT_SERVICE_WHY, ревизия 50 п.2)" % len(exc),
          exc and all(n in S.NOT_SERVICE_WHY and not by[("other", n)]["service"] for n in exc), [n for n in exc if n not in S.NOT_SERVICE_WHY])
    check("античит: 145–147 (P96) в KindText нет, P96 их не пишет (ревизия 50 п.3: в p96_inventory_x2.cpp только константы, без AcJournal::Clear/Push), "
          "«?» показывается видом без текста с подсказкой без ссылки на P96",
          not any(("other", n) in by for n in (145, 146, 147)) and A.kind_info("other", "?")["hint"] == S.UNKNOWN_HINT
          and "P96" not in S.UNKNOWN_HINT and A.kind_info("other", "?")["n"] is None)
    p96 = open(os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "src", "patches", "p96_inventory_x2.cpp"), encoding="utf-8", errors="replace").read()
    check("античит: p96_inventory_x2.cpp не пишет журнал (нет AcJournal::Clear / Push / kKind* в вызовах) — второй метод к ревизии 50 п.3",
          "AcJournal::Clear" not in p96 and "AcJournal::Push" not in p96 and len(re.findall(r"kKind(?:Canary|SlotOOB|Fault)", p96)) == 3)
    ki = A.kind_info("other", "P999: новый вид, которого нет в каталоге")
    kj = A.kind_info("other", "журнал: новая служебная строка")
    kk = A.kind_info("other", "Журнал: строка с заглавной")
    kx = A.kind_info("other", "P999: исключение нового патча")
    check("античит: текст не из каталога — номер «?», патч по началу текста, «журнал:» — служебная без учёта регистра (как CI LIKE), "
          "«исключение» — не служебное", ki["n"] is None and ki["patch"] == "P999" and not ki["service"] and not ki["known"] and kj["service"]
          and kk["service"] and not kx["service"], (ki, kj, kk, kx))
    from core import i18n as _i
    noen = [(k, r["n"]) for k, v in t.items() for r in v if r["text"] not in _i.AC_KINDS]
    check("античит EN: у каждого из %d видов каталога есть перевод в i18n.AC_KINDS (ревизия 50 п.4)" % sum(len(v) for v in t.values()),
          not noen and all(not re.search("[А-Яа-яЁё]", _i.AC_KINDS[r["text"]]) for v in t.values() for r in v), noen[:8])
    check("античит: патч по началу и концу текста — «N24: …», «… (P56)», «В7d: …»", S.patch_of("other", None, "N24: x") == "N24"
          and S.patch_of("move_combat", None, "x (P56)") == "P56" and S.patch_of("other", None, "В7d: x") == "В7d")

    # ---- разбор подставного исходника
    good = 'namespace {\n    const wchar_t* KindText(int table, int kind)\n    {\n        switch (table)\n        {\n        case AcJournal::kOther:\n' \
           '            switch (kind)\n            {\n            case 1: return L"a";\n            case 2: return L"b";\n            }\n' \
           '            break;\n        case AcJournal::kKickBlock:\n            return kind == 2 ? L"x" : L"y";\n        }\n        return L"?";\n    }\n}\n'
    k, bad = S.parse(good)
    check("античит: разбор подставного KindText — виды и тернарный, без проблем", k == {"other": {1: "a", 2: "b"}, "kick_block": {2: "x", 1: "y"}}
          and not bad, (k, bad))
    _k, bad2 = S.parse(good.replace('case 2: return L"b";', 'case 1: return L"b";'))
    _k3, bad3 = S.parse(good.replace('case 2: return L"b";', 'case 2: return Pick(L"b");'))
    check("античит: повтор номера и нераспознанная строка с текстом — проблемы разбора (выкладка тогда отказывает)",
          any("повторён" in b[1] for b in bad2) and any("не разобрана" in b[1] for b in bad3), (bad2, bad3))
    try:
        S.parse("int x;\n")
        nofn = False
    except ValueError:
        nofn = True
    check("античит: нет функции KindText — ошибка, а не пустой каталог", nofn)

    # ---- фильтры и отказы (без базы)
    bad_cases = [({"from": "2026-11-21"}, True), ({"from": "20261131"}, True), ({"to": "2026112"}, True), ({"from": "20261122", "to": "20261121"}, True),
                 ({"ip": "1.2.3.4"}, False), ({"ip": "1.2.3"}, True), ({"ip": "1.2.3.4; DROP"}, True), ({"table": "users"}, True),
                 ({"table": "other'--"}, True), ({"kind": "other"}, True), ({"kind": "nope:текст"}, True),
                 ({"kind": "other:журнал: старт", "table": "kick_block"}, True), ({"char": "x" * 33}, True), ({"server": "s" * 65}, True),
                 ({"account": "0"}, True), ({"account": "99999999999"}, True)]
    why = [_refused(lambda q=q, ip=ip: A.build_filters(q, ip)) for q, ip in bad_cases]
    check("античит: неверные фильтры — отказ (%d случаев: даты не ГГГГММДД / нет дня / «с» позже «по», IP без права и неверный, чужая таблица, "
          "вид без таблицы, вид другой таблицы, длины, номер учётки вне границ)" % len(bad_cases), all(why), list(zip([b[0] for b in bad_cases], why)))
    check("античит: IP без права — отказ с названием права players.view_net", "players.view_net" in (why[4] or ""), why[4])
    f = A.build_filters({"from": "20261101", "to": "20261121", "kind": "other:P73: мост EAC: подключён", "server": "GameServer", "char": "Имя",
                         "ip": "10.0.0.1", "service": "1"}, True)
    check("античит: верные фильтры — даты строкой ГГГГММДД, вид — (таблица, текст как есть с двоеточиями), служебные включены",
          f["from"] == "20261101" and f["to"] == "20261121" and f["kind"] == ("other", "P73: мост EAC: подключён") and f["service"] and f["ip"] == "10.0.0.1", f)
    w, args = A._where("other", "event_kind", f)
    check("античит: условие SQL — только параметры (значения фильтров не склеены в текст), даты через CONVERT(datetime2, ?, 112)",
          "?" in w and "Имя" not in w and "20261101" not in w and "GameServer" not in w and "10.0.0.1" not in w and "CONVERT(datetime2, ?, 112)" in w
          and args[:2] == ["Имя", "10.0.0.1"] and "20261101" in args, (w, args))
    w2, a2 = A._where("other", "event_kind", A.NO_FILTER)
    check("античит: без «служебных» — NOT IN по каталогу ac.other + LIKE «журнал:%», все тексты параметрами (в SQL русских букв нет)",
          "NOT IN" in w2 and w2.count("NOT LIKE ?") == 1 and "журнал:%" in a2 and "%исключение%" not in a2 and set(A.service_texts("other")) <= set(a2)
          and not re.search("[А-Яа-я]", w2), w2[:200])
    w3, _a3 = A._where("move_combat", "event_kind", A.NO_FILTER)
    check("античит: в таблицах без служебных видов — без NOT IN (только LIKE-страховки)", "NOT IN" not in w3 and "LIKE" in w3, w3)
    why2 = [_refused(lambda q=q: A.events(q, True)) for q in ({"size": "0"}, {"size": "201"}, {"page": "x"}, {"page": "201", "size": "50"})]
    check("античит: размер страницы 1…200, страница — целое, глубина ленты ≤ %d строк — отказ до запроса" % A.DEPTH_MAX, all(why2), why2)
    texts = [x for x in why + why2 if x]
    check("античит: тексты отказов без «; »", all("; " not in x for x in texts), [x for x in texts if "; " in x])

    # ---- права и маршруты
    roles = ("owner", "admin", "gm", "support")
    check("античит: право ac.view — owner, admin, gm (support — нет); IP — players.view_net (owner, admin, gm)",
          {r for r in roles if auth.can(r, "ac.view")} == {"owner", "admin", "gm"} and {r for r in roles if auth.can(r, "players.view_net")}
          == {"owner", "admin", "gm"})
    rt = {p: _route(p) for p in ("/api/ac/catalog", "/api/ac/events", "/api/ac/summary")}
    check("античит: маршруты /api/ac/catalog, /api/ac/events, /api/ac/summary — GET, право ac.view",
          all(fn and perm == "ac.view" for fn, perm in rt.values()), {p: v[1] for p, v in rt.items()})
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("античит: лента API — IP по праву players.view_net (не по ac.view), отказ ввода — 409",
          srv.count('auth.can(req.session["user"]["role"], "players.view_net")') >= 2 and "def _ac_call" in srv and "HttpError(409, str(ex))" in srv)

    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in texts] + [ti for _t, _k, _e, ti in A.TABLES] + list(S.SERVICE_OTHER.values()) + [
            S.UNKNOWN_HINT, "топ нарушителей не посчитан: запрос к joylog1: Invalid object name 'ac.other'", "§9: строка самого журнала", "ac.other: запрос к joylog1: Invalid object name 'ac.other'",
            "AsdaStoryOp.Us_member: нет подключения к AsdaStoryOp: Login timeout expired",
            "ac.v_top_offenders: запрос к joylog1: Invalid object name 'ac.sign_replay'", "учётки с логином «abc» нет",
            "дата «с»: такого дня нет (20261131)", "дальше 10000 строк лента не листается — сузьте фильтр или интервал дат"]
        miss = [x for x in ru if re.search("[А-Яа-яЁё]", i18n.tr(x))]
        check("античит EN: отказы, таблицы, причины «служебная», ошибки таблиц (вложенным переводом) — без русских слов (%d строк)" % len(ru),
              not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("античит: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])

    # ---- веб
    js = open(os.path.join(ROOT, "web", "acjournal.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("античит веб: раздел #/ac «Античит» с правом ac.view, маршрут viewAc, скрипт подключён",
          '["#/ac", "Античит", "ac.view"' in app and 'case "ac": return viewAc(my);' in app and "/acjournal.js" in idx)
    check("античит веб: без innerHTML, данные — текстовыми узлами (acText), перевода данных нет (T() только к подписям)",
          "innerHTML" not in js and "createTextNode" in js and "T(e.kind_text" not in js and "T(k.kind" not in js and "T(r.login" not in js)
    check("античит веб: даты уходят в службу ГГГГММДД, вид — kind_raw (сырой текст, не перевод), IP без права — поле выключено, «•••» в ленте",
          'replace(/-/g, "")' in js and "kind_raw" in js and "disabled: !cat.can_ip" in js and '"•••"' in js)
    labels = re.findall(r'h\("(?:h1|h2|th|span|button|label)", (?:null|\{[^}]*\}), "([^"]+)"\)', js) + re.findall(r'\["([^"\]]+)", (?:k|r|e) =>', js) + \
        re.findall(r'T\("([^"]+)"', js)
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted({x for x in labels if x not in have and re.search("[А-Яа-яЁё]", x)})
    check("античит веб EN: у подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(set(labels)), not lack, lack[:8])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "acjournal.js")], capture_output=True, timeout=60)
        check("античит: node --check web/acjournal.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("античит: node --check web/acjournal.js (node не запустился)", False, str(ex))

    # ---- консоль и выкладка
    py = sys.executable
    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "ac"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("events", "--bogus")
    c2, o2 = con("events", "--from")
    c3, o3 = con("nope")
    c4, o4 = con("kinds", "--table", "kick_block")
    check("античит консоль: неизвестный ключ, ключ без значения, неизвестное действие — отказ без запроса к базе; kinds — каталог без базы",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3
          and c4 == 0 and "автоблок" in o4 and "P48" in o4, (o1[-200:], o2[-200:], o3[-200:], o4[-300:]))
    hlp = subprocess.run([py, os.path.join(ROOT, "domains", "acjournal_src.py"), "--help"], capture_output=True, timeout=60, cwd=ROOT)
    unk = subprocess.run([py, os.path.join(ROOT, "domains", "acjournal_src.py"), "--nope"], capture_output=True, timeout=60, cwd=ROOT)
    wr = subprocess.run([py, os.path.join(ROOT, "domains", "acjournal_src.py"), "--write"], capture_output=True, timeout=60, cwd=ROOT)
    check("античит: acjournal_src.py --help ничего не пишет, неизвестный ключ и прежний --write — код 1 (ревизия 50 п.10), data/ref/ac_kinds.json на ПК нет",
          hlp.returncode == 0 and unk.returncode == 1 and wr.returncode == 1 and not os.path.exists(S.CATALOG_REF))
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("античит выкладка: каталог видов кладётся в data/ref/ac_kinds.json, проблемы разбора — отказ выкладки, локальная копия из обхода data/ref "
          "не берётся (BUILT_REF — без дубля записи)", '"data/ref/ac_kinds.json"' in dep and '_acat["problems"]' in dep and "SystemExit" in dep
          and 'BUILT_REF = {"data/ref/ac_kinds.json"}' in dep and "if arc in BUILT_REF" in dep)
    adm = open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read()
    check("античит консоль: команда ac описана в справке asda_admin.py", "  ac …" in adm and "events [--account" in adm and "summary [--day" in adm)


def _subst(text, names):
    """Миграции схемы ac — на свои базы стенда: joylog1 / AsdaStoryOp / Joy1 → имена баз стенда."""
    for a, b in (("joylog1", names["J"]), ("AsdaStoryOp", names["O"]), ("Joy1", names["Y"])):
        text = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % a, b, text)
    return text


def sandbox(check, ldb):
    """Свои базы LocalDB: настоящие миграции схемы ac, синтетика, лента, сводка, маршруты API, отсутствующая таблица."""
    from core import db
    from domains import acjournal as A
    tag = secrets.token_hex(3)
    names = {"J": "AsdaAcJ_" + tag, "O": "AsdaAcO_" + tag, "Y": "AsdaAcY_" + tag}
    m = ldb("master")
    for k, n in names.items():
        m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % n)
    try:
        o = ldb(names["O"]).cursor()
        o.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(20), us_block TINYINT)")
        o.execute("INSERT dbo.Us_member VALUES (9001, 'alpha', 0), (9002, 'beta', 5), (9003, 'gamma', 0), (9006, '9001', 0)")
        y = ldb(names["Y"]).cursor()
        y.execute("CREATE TABLE dbo.SoulMate (Userindex INT, Ouserindex INT, State TINYINT)")
        j = ldb(names["J"])
        jc = j.cursor()
        jc.execute("CREATE TABLE dbo.Loginfo (Userindex INT, Login DATETIME, State TINYINT)")
        for f in MIGRATIONS:
            text = _subst(open(os.path.join(SQL_DIR, f), encoding="utf-8-sig").read(), names)
            for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
                if batch.strip():
                    jc.execute(batch)
        objs = sorted(r[0] for r in jc.execute("SELECT o.name FROM sys.objects o WHERE SCHEMA_NAME(o.schema_id) = 'ac' AND o.type IN ('U', 'V')").fetchall())
        check("античит стенд: настоящие миграции acdb_01 + acdb_p55_01 + acj2_01 + autoban_01 — 8 таблиц и 5 представлений ac.*",
              objs == sorted(list(A.TABLE_NAMES) + ["v_events", "v_recent", "v_account_daily", "v_top_offenders", "v_login_check_readable"]), objs)
        now = datetime.datetime.now().replace(microsecond=0)
        old = now - datetime.timedelta(days=3)
        far = now - datetime.timedelta(days=20)
        utc = lambda d: d - datetime.timedelta(hours=3)

        def ins(table, kind_col, rows, extra_cols=(), extra=()):
            for i, r in enumerate(rows):
                when, srv, uid, slot, name, ip, kind = r[:7]
                ex = r[7] if len(r) > 7 else extra
                cols = "ev_utc, ev_local, server_name, server_port, user_index, char_slot, char_name, ip, user_num, opcode, repeat_suppressed, " + kind_col
                vals = [utc(when), when, srv, 15601, uid, slot, name, ip, 1, 4006, i % 2, kind]
                if extra_cols:
                    cols += ", " + ", ".join(extra_cols)
                    vals += list(ex)
                jc.execute("INSERT ac.%s (%s) VALUES (%s)" % (table, cols, ",".join("?" * len(vals))), vals)
        ins("other", "event_kind", [
            (now, "GameServer", 9001, 10, "Альфа", "10.0.0.1", "неизвестный опкод (NotKnow Packet)"),
            (now - datetime.timedelta(minutes=1), "GameServer", None, None, None, None, "журнал: старт"),
            (now - datetime.timedelta(minutes=2), "GameServer", None, None, None, None, "P73: мост EAC подключён к сайдкару (HELLO + LOGIN всех в игре)"),
            (now - datetime.timedelta(minutes=3), "GameServer", 9002, 11, "Бета", "10.0.0.2", "P100: расхождение памяти и БД / исключение при слиянии — решение стока"),
            (now - datetime.timedelta(minutes=4), "Ch2_GameServer", 9002, 11, "Бета", "10.0.0.2", "P999: вид новой сборки, которого нет в каталоге"),
            (now - datetime.timedelta(minutes=5), "GameServer", 9003, 10, "Гамма", "10.0.0.3", "?"),
            (old, "Indun_GameServer", 9001, 10, "Альфа", "10.0.0.1", "P64: не в игре (CUser+0x190 == 0)"),
            (far, "GameServer", 9001, 10, "Альфа", "10.0.0.1", "покупка запрещённого товара (обычный, флаг продажи)"),
        ], ("item_code", "value1", "value2", "detail"), (20551, 1, 2, "d"))
        ins("move_combat", "event_kind", [(now - datetime.timedelta(seconds=30), "GameServer", 9001, 10, "Альфа", "10.0.0.1",
                                           "CharMove: позиция клиента не равна серверной — откат")], ("map_index", "interval_ms"), (3, 120))
        ins("kick_block", "event_kind", [(now - datetime.timedelta(seconds=40), "GameServer", 9002, 11, "Бета", "10.0.0.2", "кик"),
                                         (now - datetime.timedelta(seconds=41), "GameServer", 9002, 11, "Бета", "10.0.0.2", "автоблок")],
            ("disc_type", "counted"), (3, 1))
        ins("operator_refusal", "refusal_kind", [(now - datetime.timedelta(seconds=50), "GameServer", 9003, 10, "Гамма", "10.0.0.3",
                                                  "операторская команда без GM-флага")], ("gm_flag", "hack_counted"), (0, 1))
        ins("identity_mismatch", "logon_kind", [(now - datetime.timedelta(seconds=60), "GameServer", 9001, 10, "Альфа", "10.0.0.1", "4001 вход в мир")],
            ("packet_user_index", "session_user_index"), (9001, 9002))
        ins("login_check_refusal", "check_result", [(now - datetime.timedelta(seconds=70), "DBManager", 9003, 10, "Гамма", "10.0.0.3", "отказ")],
            ("reason", "client_code"), ("нет сессии", 5))
        ins("sign_replay", "event_kind", [(now - datetime.timedelta(seconds=80), "GameServer", 9001, 10, "Альфа", "10.0.0.1",
                                           "секрет: повтор/подделка счётчика пакета")], ("handler", "error_count"), ("h", 3))
        ins("packet_validator", "event_kind", [(now - datetime.timedelta(seconds=90), "GameServer", 9002, 11, "Бета", "10.0.0.2",
                                                "превышена частота пакетов класса")], ("action", "frame_size"), ("drop", 12))
        db.set_override("game", lambda database: ldb({"joylog1": names["J"], "AsdaStoryOp": names["O"]}.get(database, database)))
        try:
            _sandbox_checks(check, A, now, names)
            # ---- таблицы нет — строка ошибки, остальное считается
            jc.execute("DROP TABLE ac.sign_replay")
            r = A.events({"service": "1"}, True)
            s = A.summary()
            check("античит стенд: таблицы ac.sign_replay нет — в ленте строка ошибки, остальные 7 таблиц считаются (15 строк)",
                  any(e.startswith("ac.sign_replay:") for e in r["errors"]) and r["total"] == 15 and "sign_replay" not in r["per_table"], (r["errors"], r["total"]))
            check("античит стенд: таблицы нет — сводка: ошибка таблицы и представлений (v_top_offenders, v_account_daily), виды остальных таблиц считаются",
                  any(e.startswith("ac.sign_replay:") for e in s["errors"]) and any(e.startswith("ac.v_top_offenders:") for e in s["errors"])
                  and any(e.startswith("ac.v_account_daily:") for e in s["errors"]) and s["kinds_total"] >= 13, (s["errors"], s["kinds_total"]))
            check("античит стенд: таблицы нет — топ по нарушениям всё равно посчитан по остальным таблицам (без полей представления)",
                  s["top"] and s["top"][0]["violations"] > 0 and s["top"][0]["total"] is None, s["top"][:2])
        finally:
            db.set_override("game", None)
    finally:
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def _sandbox_checks(check, A, now, names):
    """Лента, фильтры, IP, страницы, сводка и маршруты на синтетике стенда (16 строк в 8 таблицах, из них служебных 3)."""
    r_all = A.events({"service": "1"}, True)
    r = A.events({}, True)
    check("античит стенд: лента всех 8 таблиц — 16 строк со служебными, 14 без (скрыты «журнал: старт» и мост P73; P100 156 с учёткой — показан)",
          r_all["total"] == 16 and r["total"] == 14 and len(r_all["per_table"]) == 8 and r_all["errors"] == [] and r["errors"] == [],
          (r_all["total"], r["total"], r_all["per_table"], r_all["errors"]))
    times = [x["ev_local"] for x in r_all["rows"]]
    check("античит стенд: лента по времени — новые сверху, строки разных таблиц перемешаны по времени", times == sorted(times, reverse=True)
          and len({x["table"] for x in r_all["rows"][:12]}) >= 6, [(x["table"], str(x["ev_local"])) for x in r_all["rows"][:6]])
    top = r_all["rows"][0]
    check("античит стенд: строка — вид текстом, номер 3, патч P53, логин учётки, слот, персонаж, IP (с правом), подробности таблицы",
          top["kind_text"] == "неизвестный опкод (NotKnow Packet)" and top["n"] == 3 and top["patch"] == "P53" and top["login"] == "alpha"
          and top["slot"] == 10 and top["char"] == "Альфа" and top["ip"] == "10.0.0.1" and top["extra"] == {"item_code": 20551, "value1": 1, "value2": 2, "detail": "d"}, top)
    svc = {x["kind_text"]: x["service"] for x in r_all["rows"] if x["service"]}
    check("античит стенд: служебные в ленте помечены причиной (журнал, P73) — 2", len(svc) == 2 and all(svc.values()), svc)
    unk = [x for x in r_all["rows"] if not x["known"]]
    check("античит стенд: «P999 …» — номер «?», патч P999; «?» — подсказка про вид без текста", len(unk) == 2
          and any(x["patch"] == "P999" and x["n"] is None for x in unk) and any(x["hint"] for x in unk), unk)
    nip = A.events({}, False)
    check("античит стенд: без players.view_net — IP во всех строках пусты, ip_hidden", nip["ip_hidden"] and all(x["ip"] is None for x in nip["rows"])
          and nip["total"] == 14)
    flt = {
        "учётка номером 9002 (P100 156 — не служебная)": ({"account": "9002"}, 5), "учётка логином beta": ({"account": "beta"}, 5),
        "учётка 9002 со служебными": ({"account": "9002", "service": "1"}, 5), "персонаж «Альфа»": ({"char": "Альфа"}, 6), "IP 10.0.0.3": ({"ip": "10.0.0.3"}, 3), "таблица kick_block": ({"table": "kick_block"}, 2),
        "вид other:P64": ({"kind": "other:P64: не в игре (CUser+0x190 == 0)"}, 1), "вид kick_block:автоблок": ({"kind": "kick_block:автоблок"}, 1),
        "сервер Ch2_GameServer": ({"server": "Ch2_GameServer"}, 1), "сервер DBManager": ({"server": "DBManager"}, 1),
        "даты «с» сегодня": ({"from": now.strftime("%Y%m%d")}, 12),
        "даты только 3 суток назад": ({"from": (now - datetime.timedelta(days=3)).strftime("%Y%m%d"),
                                       "to": (now - datetime.timedelta(days=3)).strftime("%Y%m%d")}, 1),
        "даты «по» 20 суток назад": ({"to": (now - datetime.timedelta(days=20)).strftime("%Y%m%d")}, 1),
        "учётка + таблица": ({"account": "9001", "table": "other"}, 3), "служебный вид с service=1": ({"kind": "other:журнал: старт", "service": "1"}, 1),
        "служебный вид без service — служебные включаются сами (ревизия 50 п.7)": ({"kind": "other:журнал: старт"}, 1),
    }
    got = {k: A.events(q, True)["total"] for k, (q, _n) in flt.items()}
    check("античит стенд: каждый фильтр (%d) даёт ожидаемое число строк" % len(flt), all(got[k] == n for k, (_q, n) in flt.items()),
          {k: (got[k], n) for k, (_q, n) in flt.items() if got[k] != n})
    w = _refused(lambda: A.events({"account": "nobody"}, True))
    check("античит стенд: логина нет — отказ", w and "nobody" in w, w)
    sa = A.events({"kind": "other:журнал: старт"}, True)
    sn = A.events({"kind": "other:неизвестный опкод (NotKnow Packet)"}, True)
    check("античит стенд: служебный вид без галочки — service_auto (служебные показаны с пометкой), обычный вид — без неё",
          sa["service"] and sa["service_auto"] and sa["total"] == 1 and not sn["service"] and not sn["service_auto"], (sa["service_auto"], sn["service_auto"]))
    check("античит стенд: логин из одних цифр («9001» у учётки 9006) — ищется и номером, и логином (ревизия 50 п.9)",
          A.resolve_account("9001") == [9001, 9006] and A.resolve_account("9002") == [9002], (A.resolve_account("9001"), A.resolve_account("9002")))
    saved = A.DEPTH_MAX
    try:
        A.DEPTH_MAX = 10
        pc = A.events({"service": "1", "size": "5"}, True)
        why = _refused(lambda: A.events({"service": "1", "size": "5", "page": str(pc["pages"])}, True))
    finally:
        A.DEPTH_MAX = saved
    check("античит стенд: при глубине 10 и странице 5 — страниц 2 (не 4), pages_capped, последняя страница открывается (ревизия 50 п.6)",
          pc["pages"] == 2 and pc["pages_capped"] and why is None, (pc["pages"], pc["pages_capped"], why))
    p1, p2, p4 = (A.events({"service": "1", "size": "5", "page": str(p)}, True) for p in (1, 2, 4))
    ids = [(x["table"], x["event_id"]) for x in p1["rows"] + p2["rows"]]
    check("античит стенд: страницы по 5 — 4 страницы, без повторов и пропусков, последняя — 1 строка", p1["pages"] == 4 and len(set(ids)) == 10
          and [x["event_id"] for x in p1["rows"]] == [x["event_id"] for x in r_all["rows"][:5]]
          and [(x["table"], x["event_id"]) for x in p2["rows"]] == [(x["table"], x["event_id"]) for x in r_all["rows"][5:10]] and len(p4["rows"]) == 1,
          (p1["pages"], ids, len(p4["rows"])))
    s = A.summary()
    kinds = {(k["table"], k["kind_text"]): k for k in s["kinds"]}
    check("античит стенд: виды за сутки — %d событий сегодня, из них служебных 2; номера и патчи из каталога, служебные внизу" % s["kinds_total"],
          s["kinds_total"] == 14 and s["kinds_service"] == 2 and kinds[("kick_block", "автоблок")]["num"] == 2
          and kinds[("other", "журнал: старт")]["service"] and s["kinds"][-1]["service"] and not s["errors"]
          and s["day"] == now.strftime("%Y%m%d"), (s["kinds_total"], s["kinds_service"], s["errors"]))
    old = A.summary((now - datetime.timedelta(days=3)).strftime("%Y%m%d"))
    check("античит стенд: виды за выбранные сутки (3 дня назад) — 1 вид P64", old["kinds_total"] == 1 and old["kinds"][0]["patch"] == "P64", old["kinds"])
    t = {x["user_index"]: x for x in s["top"]}
    check("античит стенд: топ нарушителей — отбор и сортировка по нарушениям без служебных В SQL (ревизия 50 п.5), к ним ac.v_top_offenders "
          "(7 суток, всего строк, блок сейчас)", [x["violations"] for x in s["top"]] == sorted([x["violations"] for x in s["top"]], reverse=True)
          and len(s["top"]) <= A.TOP_N and set(t) == {9001, 9002, 9003} and t[9002]["total"] == 5 and t[9002]["violations"] == 5 and t[9003]["violations"] == 3 and t[9002]["us_block_now"] == 5
          and t[9002]["kicks"] == 1 and t[9002]["autoblocks"] == 1 and t[9001]["total"] == 5 and t[9001]["violations"] == 5
          and [x["user_index"] for x in s["top"]][:2] == [9001, 9002], [(x["user_index"], x["total"], x["violations"]) for x in s["top"]])
    d = {x["user_index"]: x for x in s["daily"]}
    check("античит стенд: учётки за сутки (ac.v_account_daily) — 3 учётки сегодня, у 9001 четыре строки, логин", set(d) == {9001, 9002, 9003}
          and d[9001]["total"] == 4 and d[9001]["login"] == "alpha", [(x["user_index"], x["total"]) for x in s["daily"]])
    check("античит стенд: серверы журнала — 4 источника", A.servers() == ["Ch2_GameServer", "DBManager", "GameServer", "Indun_GameServer"], A.servers())
    # ---- маршруты API настоящими функциями
    from core import i18n
    fe, _p = _route("/api/ac/events")
    fs, _p = _route("/api/ac/summary")
    fc, _p = _route("/api/ac/catalog")
    gm = fe(_Req({"service": "1"}, "gm"), None)
    check("античит API: gm видит ленту и IP (players.view_net), у строки kind_raw = текст базы", gm["total"] == 16 and gm["rows"][0]["ip"] == "10.0.0.1"
          and all(x["kind_raw"] == x["kind_text"] for x in gm["rows"]))
    from api import server as _srv
    try:
        fe(_Req({"ip": "10.0.0.1"}, "support"), None)
        code = None
    except _srv.HttpError as ex:
        code = ex.code
    check("античит API: роль без players.view_net и фильтр по IP — 409 (право IP проверяется отдельно от ac.view)", code == 409, code)
    i18n.set_lang("en")
    try:
        en = fe(_Req({"service": "1", "kind": "other:журнал: старт"}, "owner"), None)
        sm = fs(_Req({}, "owner"), None)
        ct = fc(_Req({}, "admin"), None)
    finally:
        i18n.set_lang("ru")
    row = en["rows"][0]
    check("античит API EN: текст вида — перевод AC_KINDS («log: start»), kind_raw — русский текст базы (значение фильтра), причина «служебная» по-английски",
          row["kind_text"] == "log: start" and row["kind_raw"] == "журнал: старт" and not re.search("[А-Яа-я]", row["service"] or "x"), row)
    check("античит API: сводка и каталог (таблицы с заголовком EN, виды с kind_raw, серверы, can_ip у admin)",
          sm["kinds_total"] == 14 and len(ct["tables"]) == 8 and ct["can_ip"] and ct["servers"] and all(k["kind_raw"] for t in ct["tables"] for k in t["kinds"])
          and not re.search("[А-Яа-я]", ct["tables"][0]["title"]), (sm["kinds_total"], ct["tables"][0]["title"]))


def live(check):
    """Только чтение живой joylog1 (asda_admin) и службы на сервере. Ничего не пишет."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db, i18n
    from domains import acjournal as A, acjournal_src as S
    if config.get().on_server:
        return check("живой самотест А6.1 — с ПК", True)
    objs = list(A.TABLE_NAMES) + ["v_events", "v_recent", "v_account_daily", "v_top_offenders", "v_login_check_readable"]
    with db.GameReader("joylog1") as lg:
        perm = {o: lg.one("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', 'SELECT') AS p", ("ac." + o,))["p"] for o in objs}
        cnt = {t: lg.one("SELECT COUNT(*) AS n FROM ac.%s" % t)["n"] for t in A.TABLE_NAMES}
        seen = {}
        for t, kc, _e, _ti in A.TABLES:
            for r in lg.rows("SELECT %s AS k, COUNT(*) AS n FROM ac.%s GROUP BY %s" % (kc, t, kc)):
                seen[(t, r["k"])] = r["n"]
    check("живое (asda_admin): SELECT на 8 таблиц и 5 представлений ac.* есть (SQL-установка прав не нужна)", all(v == 1 for v in perm.values()), perm)
    unk = [k for k in seen if not A.kind_info(*k)["known"]]
    check("живое: каждый вид живой базы (%d) есть в каталоге KindText" % len(seen), not unk, unk[:5])
    noen = [k for k in seen if k[1] not in i18n.AC_KINDS]
    check("живое: у каждого вида живой базы есть перевод EN (i18n.AC_KINDS)", not noen, noen[:5])
    r_all = A.events({"service": "1", "size": "10"}, True)
    r = A.events({"size": "10"}, True)
    nsvc = sum(n for (t, k), n in seen.items() if A.kind_info(t, k)["service"])
    check("живое: лента со служебными = сумме COUNT(*) 8 таблиц (%d), без служебных = минус служебные по каталогу (%d)" % (sum(cnt.values()), nsvc),
          r_all["total"] == sum(cnt.values()) and r["total"] == sum(cnt.values()) - nsvc and not r_all["errors"] and not r["errors"],
          (r_all["total"], r["total"], cnt, r_all["errors"]))
    times = [x["ev_local"] for x in r_all["rows"]]
    check("живое: первая страница — 10 строк новые сверху, у каждой номер или «?», патч", len(r_all["rows"]) == min(10, r_all["total"])
          and times == sorted(times, reverse=True) and all(x["patch"] for x in r_all["rows"] if x["known"]))
    if r["rows"] and r["rows"][0]["uid"]:
        u = r["rows"][0]["uid"]
        ru = A.events({"account": str(u), "service": "1"}, True)
        check("живое: фильтр по учётке %s — только её строки" % u, ru["total"] > 0 and all(x["uid"] == u for x in ru["rows"]), ru["total"])
    s = A.summary()
    check("живое: сводка — виды за сутки, топ (v_top_offenders), учётки за сутки (v_account_daily) без ошибок", not s["errors"]
          and isinstance(s["top"], list) and isinstance(s["daily"], list), s["errors"])
    # служба на сервере: каталог из data/ref того же md5, лента считается (python службы через stdin, без файлов на сервере)
    probe = ("import sys\nsys.path.insert(0, '.')\nfrom domains import acjournal as A, acjournal_src as S\nimport os\n"
             "c = A.catalog()[0]\nr = A.events({'service': '1', 'size': '5'}, False)\n"
             "print('ACPROBE src=%s md5=%s total=%d rows=%d ip=%s err=%d' % (os.path.isfile(S.SRC), c['md5'], r['total'], len(r['rows']), "
             "any(x['ip'] for x in r['rows']), len(r['errors'])))\n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        p = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                            r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"ACPROBE src=(\w+) md5=(\w+) total=(\d+) rows=(\d+) ip=(\w+) err=(\d+)", out)
    check("служба на сервере (SSH): каталог видов из data/ref/ac_kinds.json (исходника нет), md5 = AcJournal.cpp ПК, лента = живой, IP без права скрыты",
          bool(mm) and mm.group(1) == "False" and mm.group(2) == S.build()["md5"] and int(mm.group(3)) >= r_all["total"] and mm.group(5) == "False"
          and mm.group(6) == "0", out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/ac/events" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/ac/events без входа — 401", code == 401, code)
