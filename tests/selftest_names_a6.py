# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_names_a6.py — самотест шага А6.11, часть «имена» (22.11.2026; domains/namereview.py, sql/adminc_20_names.sql, /api/names/*,
web/names.js, консоль names, операция names.mark).

offline(check)  — проверка имени ТЕМ ЖЕ кодом, что char.rename (rename._check_name на данных из памяти): весь корпус P68 набора 0 (1590 имён —
                  тот же, на котором дым A13 сверил SQL-функцию) даёт то же правило; слова CurseTable (5), LewdWordList без учёта регистра (6),
                  занятость без учёта регистра и хвостовых пробелов (7), своя удалённая строка того же слота — не двойник, чужая — двойник,
                  оператор (латиница, цифры, «_» не в конце), набор ≠ 0; состояние отметки (нет / ок / сменить / имя изменилось); отказы ввода
                  без базы, тексты без «; », права (names.review — owner, admin, gm), операция names.mark (не откатывается, пишет только
                  INSERT adm.NameReview), маршруты, переводы EN (shadowed_translations = 0), веб без innerHTML, консоль, SQL adminc_20 и выкладка.
sandbox(check, ldb) — СВОИ базы LocalDB: AsdaAdmin (adminc_02 + adminc_20 дважды), Joy1 (Charinfo, CharPos, Del_Charinfo, CharGmInfo, A13_*,
                  LewdWordList), joylog1 (CharEventCreate, CharEvent, ac.other вид 55); синтетика с ФИКСИРОВАННЫМИ датами (январь 2026): создание,
                  смена в игре, смена панелью (adm.audit), сторож A13, удалённый персонаж; очередь за период и «все имена», фильтры, svc; отметки
                  операцией names.mark (предпросмотр, запись, повтор — отказ, имя изменилось — «stale», изменилось после предпросмотра — отказ).
live(check)     — только чтение живой dev: права asda_admin на adm.NameReview, очередь за 30 суток = числу персонажей в источниках (второй путь —
                  прямые запросы), каждое ASCII-имя перепроверено rename._check_name на НАСТОЯЩЕМ читателе Joy1 (занятость — SQL charname.taken_sql),
                  предпросмотр names.mark без записи; служба на сервере (SSH) считает очередь; без входа — 401. Отметок в живой не создаёт.
Побочных эффектов при импорте нет.
"""
import datetime
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
CORPUS = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "tools", "name_corpus_p68.txt")
CYR = re.compile("[А-Яа-яЁё]")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


class _Req:
    def __init__(self, query, role="owner"):
        self.query, self.session = dict(query), {"user": {"role": role, "login": "selftest"}}


def rules_of(names, words=(), lewd=(), opers=(), cfg=None, deleted=()):
    """Данные проверки (как namereview.load_rules) из списков: names — [(uid, idx, байты)], deleted — [(uid, idx, байты)]."""
    from domains import namereview as N
    cfg = cfg or {"Mode": 0, "Charset": 0, "CurseWords": True, "RenameLewdDup": True, "ExemptOperators": True}
    index = {}
    for uid, idx, b in names:
        index.setdefault(N.name_key(b), []).append({"Userindex": uid, "Charidx": idx, "Charname": N.show(b), "deleted": 0})
    for uid, idx, b in deleted:
        index.setdefault(N.name_key(b), []).append({"Userindex": uid, "Charidx": idx, "Charname": N.show(b), "deleted": 1})
    return {"cfg": cfg, "switches": {}, "words": list(words), "lewd": [str(w).encode("cp1251").decode("cp1256") for w in lewd], "opers": set(opers),
            "index": index, "chars": {(u, i): b for u, i, b in names}, "pos": {(u, i): b for u, i, b in names}}


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n, ops
    import domains
    domains.load_all()
    from domains import charname, namereview as N
    # ---- корпус P68 (набор 0) — тем же кодом, что char.rename
    bad, n = [], 0
    empty = rules_of([])
    for ln in pathlib.Path(CORPUS).read_text(encoding="utf-8").splitlines():
        q = ln.split()
        if len(q) >= 3 and q[0] == "0":
            n += 1
            b = bytes.fromhex(q[2]) if q[2] != "-" else b""
            code, _why = N.verdict(empty, 9001, 10, b)
            got = 0 if code == "0" else int(code[1:]) if code.startswith("r") else -1
            if got != int(q[1]) or got != charname.rule(b, []):
                bad.append(q[2])
    check("имена: корпус P68 набора 0 — %d/%d имён дают то же правило, что функция A13 (тот же код, что char.rename)" % (n - len(bad), n),
          n == 1590 and not bad, bad[:5])
    words = [b"buyasdastory"]
    R = rules_of([(9001, 10, b"Alpha"), (9002, 10, b"xBuyAsdastory1"), (9003, 10, b"FUCKer1"), (9004, 10, b"Beta"), (9005, 11, b"beta "),
                  (9006, 10, "Кирилл".encode("cp1251")), (9007, 10, b"Delta"), (9008, 10, b"Omega"), (7, 10, b"GM_Bob"), (7, 11, b"GM Bob"),
                  (7, 12, b"GMBob_"), (9009, 10, b"Gm_Bobby")],
                 words=words, lewd=["fuck"], opers=[7], deleted=[(9007, 10, b"Delta"), (9099, 11, b"OMEGA")])
    v = {k: N.verdict(R, k[0], k[1], b)[0] for k, b in R["chars"].items()}
    check("имена: правила — Alpha годно, слово CurseTable без учёта регистра имени (5), LewdWordList без учёта регистра (6), Beta / «beta » — "
          "заняты друг другом (7), кириллица — символ вне набора (4)",
          v[(9001, 10)] == "0" and v[(9002, 10)] == "r5" and v[(9003, 10)] == "r6" and v[(9004, 10)] == "r7" and v[(9005, 11)] == "r4"
          and v[(9006, 10)] == "r4", v)
    check("имена: своя удалённая строка того же слота (Delta) — не двойник; чужой удалённый OMEGA — «занято удалённым»",
          v[(9007, 10)] == "0" and v[(9008, 10)] == "r7" and "удалённым" in N.verdict(R, 9008, 10, b"Omega")[1], v)
    check("имена: оператор (учётка 7 с GM-флагом) — GM_Bob годно, «GM Bob» и «GMBob_» — правило оператора; не оператору «_» нельзя (4)",
          v[(7, 10)] == "0" and v[(7, 11)] == "oper" and v[(7, 12)] == "oper" and v[(9009, 10)] == "r4", v)
    R1 = rules_of([(9001, 10, b"Alpha")], cfg={"Mode": 0, "Charset": 1, "CurseWords": True, "RenameLewdDup": True, "ExemptOperators": True})
    check("имена: набор символов ≠ 0 — панель имя не проверяет (charset), как char.rename", N.verdict(R1, 9001, 10, b"Alpha")[0] == "charset")
    check("имена: ключ занятости — без учёта регистра и хвостовых пробелов для печатного ASCII, иначе — байты",
          N.name_key(b"Bob ") == N.name_key(b"bOB") and N.name_key(b"\xc0") != N.name_key(b"\xe0") and N.name_key(b"\xc0") == b"b:\xc0")
    mk = {"name_bin": b"Alpha", "verdict": "ok"}
    check("имена: состояние отметки — нет / ок / сменить / имя изменилось после отметки (по байтам)",
          N.mark_state(None, b"Alpha") == "none" and N.mark_state(mk, b"Alpha") == "ok" and N.mark_state(dict(mk, verdict="rename"), b"Alpha") == "rename"
          and N.mark_state(mk, b"alpha") == "stale")
    check("имена: код по тексту отказа char.rename — r1…r7, oper, charset", [N.rule_of(x) for x in (None, "имя: пустое имя (правило 1)",
          "имя занято: X (учётка 1, слот 2)", "имя оператора: только латиница", "набор символов имени на сервере — не латиница")]
          == ["0", "r1", "r7", "oper", "charset"])
    why = [_refused(lambda q=q: N.queue(q)) for q in ({"state": "x"}, {"svc": "all"}, {"size": "0"}, {"size": "201"}, {"page": "x"})]
    why += [_refused(lambda p=p: N._plan(p)) for p in ({"uid": "x", "idx": 1, "verdict": "ok"}, {"uid": 1, "idx": 256, "verdict": "ok"},
                                                      {"uid": 1, "idx": 1, "verdict": "bad"}, {"uid": 1, "idx": 1, "verdict": "ok", "note": "x" * 201},
                                                      {"uid": 1, "idx": 1, "verdict": "ok", "note": "a\nb"}, None)]

    class _Y:
        def one(self, sql, p=()):
            return {"f": "20260101", "t": "20260130"}
    why += [_refused(lambda q=q: N._period(q, _Y())) for q in ({"from": "2026-01-01"}, {"from": "20260201", "to": "20260101"},
                                                                 {"from": "20240101", "to": "20260101"})]
    check("имена: отказы ввода без обращения к базе (%d: состояние, svc, страница, отметка, пояснение, даты, период)" % len(why), all(why), why)
    from core import db as _db

    def nodb(database):
        raise _db.DbError("нет подключения к %s: Login timeout expired" % database)
    _db.set_override("game", nodb)
    _db.set_override("admin", nodb)
    try:
        wn = [_refused(lambda: N.queue({"from": "20260101", "to": "20260102"})), _refused(lambda: N.marks_of(1, 10))]
    finally:
        _db.set_override("game", None)
        _db.set_override("admin", None)
    check("имена: базы нет — отказ «очередь имён не прочитана» / «отметки имени не прочитаны» с причиной (не 500)",
          wn[0] and wn[0].startswith("очередь имён не прочитана: нет подключения") and wn[1] and wn[1].startswith("отметки имени не прочитаны"), wn)
    why += wn
    check("имена: тексты отказов без «; »", all("; " not in x for x in why if x), why)
    roles = ("owner", "admin", "gm", "support")
    op = ops.REGISTRY.get("names.mark")
    check("имена: право names.review — owner, admin, gm; операция names.mark под ним, не откатывается (новая отметка заменяет прежнюю)",
          {r for r in roles if auth.can(r, "names.review")} == {"owner", "admin", "gm"} and op and op.perm == "names.review" and not op.reversible)
    rt = {p: _route(p) for p in ("/api/names/queue", "/api/names/marks")}
    check("имена: маршруты /api/names/queue и /api/names/marks — GET, право names.review", all(fn and perm == "names.review" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})
    code = open(os.path.join(ROOT, "domains", "namereview.py"), encoding="utf-8").read()
    body = code.split('"""', 2)[2]
    lits = [s for s in re.findall(r'"((?:[^"\\]|\\.)*)"', body) if re.search(r"\b(SELECT|FROM|INSERT)\b", s)]
    check("имена: запись — только INSERT adm.NameReview (без UPDATE / DELETE), в SQL нет русских букв, игровые базы — GameReader (только чтение)",
          sorted(set(re.findall(r"INSERT (\S+)", body))) == ["adm.NameReview"] and not re.search(r"\b(UPDATE|DELETE)\s", body)
          and not any(CYR.search(s) for s in lits) and "GameWriter" not in body and "rename._check_name(" in body, lits[:3])
    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in why if x] + ["в Joy1.Charinfo больше 100000 имён — очередь имён так не считается (предел NAMES_MAX)",
              "в Joy1 нет строки A13_NameRuleConfig Id = 1 — проверка по умолчаниям (Charset 0, без слов)",
              "joylog1.CharEventCreate: запрос к joylog1: x", "joylog1.CharEvent: запрос к joylog1: x", "AsdaAdmin (журнал панели и отметки): AsdaAdmin: x",
              "в каталоге видов ac.other нет вида 55 (сторож A13) — журнал сторожа не показан",
              "персонажа нет в Charinfo (удалён или перенесён) — проверять нечего",
              "служебные учётки ≤ 5000 — отдельным итогом и внизу списка (svc=in — вместе)",
              "правила — как у смены имени char.rename (1–7); сервер при создании проверяет только 1–4, при смене — 1–7; A13 Mode 0 (только журнал ac.other 55, имя проходит)",
              "правила — как у смены имени char.rename (1–7); сервер при создании проверяет только 1–4, при смене — 1–7; A13 Mode 1 (отказ)",
              "имя уже отмечено так же (отметка №3, owner)", "пишется только база панели AsdaAdmin (adm.NameReview), имя персонажа не меняется",
              "имя не проходит правило (имя: запрещённое слово (CurseTable клиента) (правило 5)) — отмечено «ок» вручную",
              "смена имени — отдельной операцией char.rename (кнопка «Сменить имя», право players.rename)",
              "прежняя отметка №3 была для имени Bob — имя с тех пор изменилось", "отметка имени персонажа 9001/10 Alpha: ок",
              "отметка имени персонажа 9001/10 Alpha: сменить", "имя персонажа изменилось с предпросмотра — повторите проверку",
              "имя персонажа 9001/10 Alpha отмечено: ок (№4)", "имя персонажа 9001/10 Alpha отмечено: сменить (№5)", "Имена: отметка «ок / сменить»",
              "персонажа 9001/10 нет", "ошибка базы: x"] + [N.verdict(R, k[0], k[1], b)[1] for k, b in R["chars"].items() if N.verdict(R, k[0], k[1], b)[1]]
        miss = [x for x in ru if CYR.search(i18n.tr(x).replace("Кирилл", ""))]
        check("имена EN: отказы, заметки, предпросмотр и итог отметки, тексты проверки char.rename — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("имена: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js = open(os.path.join(ROOT, "web", "names.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("имена веб: раздел #/names с правом names.review, маршрут viewNames, скрипт после acjournal.js",
          '["#/names", "Очередь имён", "names.review"' in app and 'case "names": return viewNames(my);' in app
          and 0 < idx.index("/acjournal.js") < idx.index("/names.js"))
    check("имена веб: без innerHTML, имена — текстовыми узлами; «Сменить имя» — существующая renameChar (char.rename), отметка — op(\"names.mark\")",
          "innerHTML" not in js and "acText(" in js and "renameChar(x.uid, x.idx, x.name, reload)" in js and 'op("names.mark"' in js
          and "T(x.name" not in js and "T(it.name" not in js and "async function renameChar(" in app)
    labels = set(re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|div)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) | set(re.findall(r'\["([^"\]]+)", (?:x|m) =>', js)) \
        | set(re.findall(r'T\("([^"]+)"', js)) | set(re.findall(r':\s*"([^"]+)"', js[js.index("NM_STATE"):js.index("function nmRule")]))
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("имена веб EN: у подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack, lack[:8])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "names.js")], capture_output=True, timeout=60)
        check("имена: node --check web/names.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("имена: node --check web/names.js (node не запустился)", False, str(ex))
    # ---- консоль, SQL, выкладка
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "names"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("queue", "--bogus")
    c2, o2 = con("queue", "--state")
    c3, o3 = con("nope")
    c4, o4 = con("mark", "--uid", "1", "--idx", "10", "--verdict", "maybe")
    check("имена консоль: неизвестный ключ, ключ без значения, неизвестное действие, неверная отметка — отказ без обращения к базе",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3 and c4 and "--verdict" in o4,
          (o1[-200:], o2[-200:], o3[-200:], o4[-200:]))
    s20 = open(os.path.join(ROOT, "sql", "adminc_20_names.sql"), encoding="utf-8").read()
    head = s20.split("GO", 1)[0]
    ver = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    adm = open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read()
    check("adminc_20: QUOTED_IDENTIFIER / ANSI_NULLS ON отдельным пакетом ДО CREATE TABLE; GRANT SELECT, INSERT и DENY UPDATE, DELETE; CHECK отметки",
          "SET QUOTED_IDENTIFIER ON" in head and "CREATE TABLE" not in head and "GRANT SELECT, INSERT   ON adm.NameReview" in s20
          and "DENY  UPDATE, DELETE   ON adm.NameReview" in s20 and "CHECK (verdict IN ('ok', 'rename'))" in s20)
    check("имена выкладка: adminc_20 после adminc_19 в AsdaAdmin; проверка прав adminc_10 — SELECT / INSERT 1, UPDATE / DELETE 0; откат в adminc_99; "
          "консоль в справке", "Run 'adminc_19_acdaily.sql' 'AsdaAdmin'\nRun 'adminc_20_names.sql' 'AsdaAdmin'" in dep
          and all("'adm.NameReview %s'" % k in ver for k in ("SELECT", "INSERT", "UPDATE", "DELETE")) and (rb is None or "adminc_20_names.sql" in rb)
          and (rb is None or "DROP TABLE adm.NameReview" in rb) and "  names …" in adm)


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def sandbox(check, ldb):
    """Свои базы LocalDB: очередь имён и отметки операцией names.mark на синтетике (даты января 2026)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import db, ops
    import domains
    domains.load_all()
    from domains import namereview as N
    tag = secrets.token_hex(3)
    names = {"A": "AsdaNmA_" + tag, "Y": "AsdaNmY_" + tag, "L": "AsdaNmL_" + tag, "O": "AsdaNmO_" + tag}
    m = ldb("master")
    for k, n in names.items():
        m.cursor().execute("CREATE DATABASE [%s] COLLATE %s" % (n, "Cyrillic_General_CI_AS" if k == "A" else "Arabic_CI_AS"))
    try:
        a = ldb(names["A"])
        for f in ("adminc_02_schema.sql", "adminc_20_names.sql", "adminc_20_names.sql"):
            for b in _batches(open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()):
                a.cursor().execute(b)
        check("имена стенд: настоящие adminc_02 + adminc_20 дважды (повтор безопасен, без asda_admin — выдача прав пропущена)",
              a.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'NameReview'").fetchone()[0] == 1)
        y = ldb(names["Y"]).cursor()
        for t in ("Charinfo", "CharPos"):
            y.execute("CREATE TABLE dbo.%s (Userindex INT, Charidx TINYINT, Charname VARCHAR(20))" % t)
        y.execute("CREATE TABLE dbo.Del_Charinfo (Edate DATETIME, Userindex INT, Charidx TINYINT, Charname VARCHAR(20))")
        y.execute("CREATE TABLE dbo.CharGmInfo (UserIndex INT, Charidx TINYINT, GMFlag TINYINT)")
        y.execute("CREATE TABLE dbo.A13_NameRuleConfig (Id TINYINT, Mode TINYINT, Charset TINYINT, CheckCreate BIT, CheckRename BIT, CurseWords BIT, "
                  "RenameLewdDup BIT, ExemptOperators BIT)")
        y.execute("INSERT dbo.A13_NameRuleConfig VALUES (1, 0, 0, 1, 1, 1, 1, 1)")
        y.execute("CREATE TABLE dbo.A13_CurseWord (Word VARBINARY(32), Enc VARCHAR(8))")
        y.execute("INSERT dbo.A13_CurseWord VALUES (CAST('buyasdastory' AS VARBINARY(32)), 'ascii'), (0xB0A1, 'euc-kr')")
        y.execute("CREATE TABLE dbo.LewdWordList (LewdWord VARCHAR(20))")
        y.execute("INSERT dbo.LewdWordList VALUES ('fuck')")
        chars = [(9001, 10, "Alpha"), (9002, 10, "xbuyasdastory1"), (9003, 10, "FUCKer1"), (9004, 10, "Beta"), (9005, 11, "BETA"),
                 (9009, 10, "Zeta"), (9010, 10, "Eta"), (7, 10, "GM_Bob"), (9012, 10, "Old1"), (9013, 10, "Delta")]
        for u, i, nm in chars:
            for t in ("Charinfo", "CharPos"):
                y.execute("INSERT dbo.%s VALUES (?, ?, ?)" % t, (u, i, nm))
        y.execute("INSERT dbo.Charinfo VALUES (9006, 10, CONVERT(varchar(20), 0xCAE8F0E8EBEB))")    # «Кирилл» байтами cp1251
        y.execute("INSERT dbo.CharPos VALUES (9006, 10, CONVERT(varchar(20), 0xCAE8F0E8EBEB))")
        y.execute("INSERT dbo.Del_Charinfo VALUES ('2026-01-02', 9013, 10, 'Delta'), ('2026-01-02', 9099, 11, 'alpha')")
        y.execute("INSERT dbo.CharGmInfo VALUES (7, 10, 1)")
        lg = ldb(names["L"]).cursor()
        lg.execute("CREATE TABLE dbo.CharEventCreate (Edate DATETIME, Userindex INT, Charidx TINYINT, Charname VARCHAR(20))")
        lg.execute("CREATE TABLE dbo.CharEvent (Edate DATETIME, Userindex INT, Charidx TINYINT, Charname VARCHAR(20), State VARCHAR(50))")
        for k, (u, i, nm) in enumerate([(9001, 10, "Alpha"), (9002, 10, "xbuyasdastory1"), (9003, 10, "FUCKer1"), (9004, 10, "Beta"),
                                        (9005, 11, "BETA"), (7, 10, "GM_Bob"), (9011, 10, "Gone1"), (9013, 10, "Delta")]):
            lg.execute("INSERT dbo.CharEventCreate VALUES (DATEADD(HOUR, ?, '2026-01-05T08:00:00'), ?, ?, ?)", (k, u, i, nm))
        lg.execute("INSERT dbo.CharEventCreate VALUES ('2026-01-05T20:00:00', 9006, 10, CONVERT(varchar(20), 0xCAE8F0E8EBEB))")
        lg.execute("INSERT dbo.CharEventCreate VALUES ('2025-12-01T10:00:00', 9012, 10, 'Old1')")
        lg.execute("INSERT dbo.CharEvent VALUES ('2026-01-07T10:00:00', 9009, 10, 'Zeta', 'Rename'), ('2026-01-07T11:00:00', 9009, 10, 'Zeta', 'Max Weight Change')")
        lg.execute("CREATE SCHEMA ac")
        lg.execute("CREATE TABLE ac.other (event_id BIGINT IDENTITY, ev_local DATETIME2(3), user_index INT, char_slot INT, char_name NVARCHAR(64), "
                   "value1 INT, value2 INT, detail NVARCHAR(512), event_kind NVARCHAR(512))")
        k55 = next(r["text"] for r in __import__("domains.acjournal", fromlist=["x"]).catalog()[0]["tables"]["other"] if r["n"] == 55)
        lg.execute("INSERT ac.other (ev_local, user_index, char_slot, char_name, value1, value2, detail, event_kind) VALUES "
                   "('2026-01-05T09:00:01', 9002, 10, N'xbuyasdastory1', 5, 3, N'UPCreateChar: правило 5', ?)", (k55,))
        o = ldb(names["O"]).cursor()
        o.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(61), us_block TINYINT)")
        o.execute("INSERT dbo.Us_member VALUES (9001, 'alpha', 0), (7, 'svc7', 0), (9002, 'beta', 0)")
        a.cursor().execute("INSERT adm.audit (at, login, ip, via, action, target, params, before_json, after_json, result, message) VALUES "
                           "('2026-01-08T10:00:00', 'tester', '', 'web', 'char.rename', 'char:9010/10', NULL, ?, ?, 'ok', '')",
                           (json.dumps({"name": "Theta"}), json.dumps({"uid": 9010, "idx": 10, "name": "Eta", "old": "Theta"})))
        mp = {"Joy1": names["Y"], "joylog1": names["L"], "AsdaStoryOp": names["O"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("admin", lambda database: ldb(names["A"]))
        try:
            Q = N.queue({"from": "20260101", "to": "20260131", "size": "200"})
            it = {(x["uid"], x["idx"]): x for x in Q["rows"]}
            check("имена стенд: очередь за январь — 11 персонажей (создание 9, смена в игре 1, смена панелью 1; Old1 декабря — нет), без ошибок",
                  set(it) == {(9001, 10), (9002, 10), (9003, 10), (9004, 10), (9005, 11), (7, 10), (9011, 10), (9013, 10), (9006, 10), (9009, 10),
                              (9010, 10)} and not Q["errors"], (sorted(it), Q["errors"]))
            rl = {k: x["rule"] for k, x in it.items()}
            check("имена стенд: проверка — Alpha занято удалённым alpha (7), слово (5), Lewd (6), Beta / BETA (7), кириллица (4), оператор GM_Bob годно, "
                  "своя удалённая Delta — годно, Zeta / Eta годны, удалённый Gone1 — «персонажа нет»",
                  rl[(9001, 10)] == "r7" and rl[(9002, 10)] == "r5" and rl[(9003, 10)] == "r6" and rl[(9004, 10)] == "r7" and rl[(9005, 11)] == "r7"
                  and rl[(9006, 10)] == "r4" and rl[(7, 10)] == "0" and rl[(9013, 10)] == "0" and rl[(9009, 10)] == "0" and rl[(9010, 10)] == "0"
                  and rl[(9011, 10)] == "gone" and it[(9006, 10)]["name"] == "Кирилл", rl)
            ev = {k: [e["kind"] for e in x["events"]] for k, x in it.items()}
            check("имена стенд: события — создание, сторож A13 (9002: правило 5, область 3), смена в игре (только State Rename), смена панелью (кто, старое имя)",
                  ev[(9002, 10)] == ["a13", "create"] and ev[(9009, 10)] == ["rename_game"] and ev[(9010, 10)] == ["rename_panel"]
                  and it[(9010, 10)]["events"][0]["old"] == "Theta" and it[(9010, 10)]["events"][0]["by"] == "tester"
                  and it[(9002, 10)]["events"][0]["rule"] == 5, ev)
            tot = Q["totals"]
            check("имена стенд: итоги — игроки 10 (не проходят 6, персонажа нет 1), служебные 1 отдельно; служебные внизу списка (svc=sep)",
                  tot["player"]["items"] == 10 and tot["player"]["bad"] == 6 and tot["player"]["gone"] == 1 and tot["service"]["items"] == 1
                  and Q["rows"][-1]["cat"] == "service" and Q["rows"][0]["rule"] != "0", (tot, [x["uid"] for x in Q["rows"]]))
            Qa = N.queue({"from": "20260101", "to": "20260131", "all": "1", "size": "200"})
            check("имена стенд: «все текущие имена» — ещё Old1 (без событий периода), 12 строк", Qa["total"] == 12
                  and any(x["uid"] == 9012 and not x["events"] for x in Qa["rows"]), Qa["total"])
            Qb = N.queue({"from": "20260101", "to": "20260131", "state": "bad"})
            Qc = N.queue({"from": "20260101", "to": "20260131", "account": "beta"})
            check("имена стенд: фильтры — «не проходят правила» 6, учётка beta (9002) — 1", Qb["total"] == 6 and Qc["total"] == 1
                  and Qc["rows"][0]["uid"] == 9002, (Qb["total"], Qc["total"]))
            # ---- отметки
            ctx = ops.Ctx(1, "owner_t", "owner", "", "web")
            gm = ops.Ctx(2, "gm_t", "gm", "", "web")
            sup = ops.Ctx(3, "sup_t", "support", "", "web")
            pv = ops.run(gm, "names.mark", {"uid": 9002, "idx": 10, "verdict": "rename", "note": "слово"}, dry=True)
            r1 = ops.run(gm, "names.mark", {"uid": 9002, "idx": 10, "verdict": "rename", "note": "слово", "expect": pv["preview"]["expect"]})
            w_same = _refused(lambda: ops.run(ctx, "names.mark", {"uid": 9002, "idx": 10, "verdict": "rename"}, dry=True))
            w_sup = _refused(lambda: ops.run(sup, "names.mark", {"uid": 9001, "idx": 10, "verdict": "ok"}, dry=True))
            pv2 = ops.run(ctx, "names.mark", {"uid": 9003, "idx": 10, "verdict": "ok"}, dry=True)
            r2 = ops.run(ctx, "names.mark", {"uid": 9003, "idx": 10, "verdict": "ok", "expect": pv2["preview"]["expect"]})
            Q2 = N.queue({"from": "20260101", "to": "20260131", "size": "200"})
            it2 = {(x["uid"], x["idx"]): x for x in Q2["rows"]}
            check("имена стенд: names.mark — gm отмечает «сменить» (запись adm.NameReview + журнал), повтор той же отметки — отказ, support — нет права; "
                  "«ок» имени с правилом — предупреждение; в очереди — состояние и кто отметил",
                  r1["ok"] and r1["audit_id"] and w_same and "уже отмечено" in w_same and w_sup and "names.review" in w_sup
                  and any("не проходит правило" in x for x in pv2["preview"]["warnings"]) and r2["ok"]
                  and it2[(9002, 10)]["state"] == "rename" and it2[(9002, 10)]["mark"]["by"] == "gm_t" and it2[(9002, 10)]["mark"]["note_text"] == "слово"
                  and it2[(9003, 10)]["state"] == "ok" and Q2["totals"]["player"]["open"] == Q["totals"]["player"]["open"] - 2,
                  (r1.get("message"), w_same, w_sup, it2[(9002, 10)]["state"]))
            y.execute("UPDATE dbo.Charinfo SET Charname = 'Fine1' WHERE Userindex = 9002 AND Charidx = 10")
            Q3 = N.queue({"from": "20260101", "to": "20260131", "state": "stale"})
            check("имена стенд: имя изменилось после отметки — отметка недействительна (stale), имя снова ждёт отметки, проверка по новому имени",
                  Q3["total"] == 1 and Q3["rows"][0]["uid"] == 9002 and Q3["rows"][0]["rule"] == "0" and Q3["rows"][0]["mark"]["name"] == "xbuyasdastory1",
                  [(x["uid"], x["state"]) for x in Q3["rows"]])
            pv3 = ops.run(ctx, "names.mark", {"uid": 9001, "idx": 10, "verdict": "ok"}, dry=True)
            y.execute("UPDATE dbo.Charinfo SET Charname = 'Alpha2' WHERE Userindex = 9001 AND Charidx = 10")
            w_chg = _refused(lambda: ops.run(ctx, "names.mark", {"uid": 9001, "idx": 10, "verdict": "ok", "expect": pv3["preview"]["expect"]}))
            n_rows = a.cursor().execute("SELECT COUNT(*) FROM adm.NameReview").fetchone()[0]
            hist = N.marks_of(9002, 10)
            aud = a.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action = 'names.mark' AND result = 'ok'").fetchone()[0]
            check("имена стенд: имя изменилось между предпросмотром и записью — отказ, ничего не записано (отметок 2, журнал ok 2); история отметок",
                  w_chg and "изменилось с предпросмотра" in w_chg and n_rows == 2 and aud == 2 and len(hist) == 1 and hist[0]["verdict"] == "rename"
                  and hist[0]["name"] == "xbuyasdastory1", (w_chg, n_rows, aud))
            fq, _p = _route("/api/names/queue")
            rq = fq(_Req({"from": "20260101", "to": "20260131"}, "gm"), None)
            ra = fq(_Req({"from": "20260101", "to": "20260131"}, "admin"), None)
            check("имена API: gm видит очередь без права смены имени (can_rename нет), admin — с правом players.rename", rq["total"] >= 10
                  and rq["can_rename"] is False and ra["can_rename"] is True)
        finally:
            db.set_override("game", None)
            db.set_override("admin", None)
    finally:
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def live(check):
    """Только чтение живой dev и службы на сервере; отметок не создаёт (только предпросмотр)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import namereview as N, rename
    if config.get().on_server:
        return check("живой самотест А6.11 — с ПК", True)
    cn = db.admin()
    try:
        perm = {k: db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME('adm.NameReview', 'OBJECT', ?) AS p", (k,))[0]["p"] for k in ("SELECT", "INSERT", "UPDATE", "DELETE")}
    finally:
        cn.close()
    check("живое (asda_admin): adm.NameReview — SELECT / INSERT да, UPDATE / DELETE нет", perm == {"SELECT": 1, "INSERT": 1, "UPDATE": 0, "DELETE": 0}, perm)
    with db.GameReader("joylog1") as lg:
        d = lg.one("SELECT CONVERT(char(8), DATEADD(DAY, -29, GETDATE()), 112) AS f, CONVERT(char(8), GETDATE(), 112) AS t")
        keys = {(r["Userindex"], r["Charidx"]) for r in lg.rows(
            "SELECT DISTINCT Userindex, Charidx FROM dbo.CharEventCreate WHERE Edate >= CONVERT(datetime, ?, 112) AND Edate < "
            "DATEADD(DAY, 1, CONVERT(datetime, ?, 112)) UNION SELECT DISTINCT Userindex, Charidx FROM dbo.CharEvent WHERE State = 'Rename' AND "
            "Edate >= CONVERT(datetime, ?, 112) AND Edate < DATEADD(DAY, 1, CONVERT(datetime, ?, 112))", (d["f"], d["t"], d["f"], d["t"]))}
    cn = db.admin()
    try:
        for r in db.admin_rows(cn, "SELECT DISTINCT target FROM adm.audit WHERE result = 'ok' AND action IN ('char.rename', 'char.rename.undo') AND "
                                   "at >= CONVERT(datetime2, ?, 112) AND at < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))", (d["f"], d["t"])):
            mm = re.match(r"^char:(\d+)/(\d+)$", r["target"] or "")
            if mm:
                keys.add((int(mm.group(1)), int(mm.group(2))))
    finally:
        cn.close()
    Q = N.queue({"from": d["f"], "to": d["t"], "size": "200", "svc": "in"})
    got = {(x["uid"], x["idx"]) for x in Q["rows"]}
    check("живое: очередь за 30 суток (%d) = персонажам из CharEventCreate, CharEvent Rename и журнала char.rename (второй путь — прямые запросы; "
          "строк сторожа A13 сверх них — %d)" % (Q["total"], len(got - keys)), keys <= got and Q["total"] == len(got) and not Q["errors"],
          (len(keys), len(got), Q["errors"]))
    bad = []
    with db.GameReader("joy1") as y:
        for x in Q["rows"]:
            if x["state"] == "gone" or not x["name_hex"]:
                continue
            nb = bytes.fromhex(x["name_hex"])
            if not all(32 <= c <= 126 for c in nb):
                continue
            why = rename._check_name(y, x["uid"], x["idx"], nb.decode("ascii"), None, own_deleted=(x["uid"], x["idx"]))
            if N.rule_of(why) != x["rule"]:
                bad.append((x["uid"], x["idx"], x["name"], x["rule"], why))
    check("живое: каждое ASCII-имя очереди перепроверено rename._check_name на настоящем читателе Joy1 (занятость — SQL charname.taken_sql) — "
          "то же правило", not bad, bad[:5])
    if Q["rows"]:
        x = next((r for r in Q["rows"] if r["state"] != "gone"), None)
        if x:
            pv = ops.run(ops.Ctx(None, "selftest", "owner", "", "cli"), "names.mark", {"uid": x["uid"], "idx": x["idx"],
                                                                                          "verdict": "rename" if x["state"] != "rename" else "ok"}, dry=True)
            check("живое: предпросмотр names.mark без записи (отметки в живой не создаются)", pv["dry"] and pv["preview"]["expect"]["name_hex"] == x["name_hex"])
    probe = ("import sys\nsys.path.insert(0, '.')\nfrom domains import namereview as N\nQ = N.queue({'svc': 'in', 'size': '200'})\n"
             "print('NMPROBE total=%d err=%d bad=%d' % (Q['total'], len(Q['errors']), sum(v['bad'] for v in Q['totals'].values())))\n")
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
    mm = re.search(r"NMPROBE total=(\d+) err=(\d+) bad=(\d+)", out)
    check("служба на сервере (SSH): очередь имён считается (adm.NameReview есть), без ошибок, не проходят = ПК",
          bool(mm) and mm.group(2) == "0" and int(mm.group(3)) == sum(v["bad"] for v in Q["totals"].values()), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/names/queue" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/names/queue без входа — 401", code == 401, code)
