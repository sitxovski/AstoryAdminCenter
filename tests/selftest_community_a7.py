# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_community_a7.py — самотест шага А7.6 «Сообщество» (24.11.2026; решение владельца А7 №9 — хозяин реестра заявок и тестеров — бот Oracle;
domains/community.py, sql/adminc_30_community.sql и adminc_30_community_verify.sql, /api/community, web/community.js; бот —
AstoryAdminCenter/DiscordBot/community_bot.py и test_community_bot.py).

НИ ОДИН ПРОГОН НЕ МЕНЯЕТ DISCORD: офлайн и стенд — бот с подставным адаптером Discord (записывает вызовы, сети нет); живой — только команды с
отметкой «тест» (бот их отмечает «тест» без вызова Discord) и захват только проверочных (@test_only = 1). Настоящих ролей, банов и сообщений нет.

offline(check)  — права (community.view — owner, admin, gm; community.manage и community.ban — owner, admin; support — ничего), операции и их
                  откат, маршрут, белые списки панели = бота = CHECK таблицы, поля снимка = полям, которые читает adm.BotSnapPut, снимок НАСТОЯЩЕГО
                  state.json без ответов анкеты и без поприветствованных (только чтение файла), тексты без «; », переводы EN (панель и итоги бота),
                  веб (без innerHTML, данные — acText), adminc_30 (уровень 100, права), проверка под asda_reports, adminc_10 / 99, выкладка, импорт
                  без побочных эффектов, модульные тесты бота.
sandbox(check, ldb) — СВОЯ база LocalDB: adminc_02 + adminc_23 + adminc_30 дважды; бот — НАСТОЯЩИЙ community_bot.Store под EXECUTE AS USER
                  asda_reports и Worker с подставным Discord: снимок → экран, решение по заявке и откат, снятие тестера и откат, снятие варнов и
                  откат, бан с блоком учётки (подставная account.block: порядок «ждёт блока → блок → боту», отказ блока — команда отменена), защищённая
                  роль — отказ, «тест» без Discord, отмена, повтор, дубль, пределы, CHECK роли, права asda_reports, журнал adm.audit, маршрут.
live(check)     — живая dev: права asda_admin на adm.Bot*, путь бота (пароль из reports.env, вход asda_reports по VPN = adminc_30_community_verify),
                  копия реестра свежая и совпадает со state.json по числу заявок, столбцов анкеты в копии нет, команда «тест» и решение по заявке с
                  отметкой «тест» → захват только проверочных → «тест» (Discord не вызывается, заявка осталась на рассмотрении), служба на сервере (SSH)
                  читает то же, без входа — 401.
Побочных эффектов при импорте нет.
"""
import ast
import asyncio
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
BOT = os.path.join(PORT, "AstoryAdminCenter", "DiscordBot")
CYR = re.compile("[А-Яа-яЁё]")
ANKETA = ("experience", "hardware", "timezone", "motivation")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def _paths():
    for p in (ROOT, BOT):
        if p not in sys.path:
            sys.path.insert(0, p)


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


def _consts(src, skip_doc=True):
    """Строковые константы с кириллицей (без докстрок)."""
    tree = ast.parse(src)
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(n.body[0].value, ast.Constant):
            doc.add(id(n.body[0].value))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and CYR.search(n.value) and (id(n) not in doc or not skip_doc):
            if n.value not in out:
                out.append(n.value)
    return out


def _bot_results(src):
    """Тексты бота, которые видит панель: return «…» / «…» % …, Refused(…), AdapterError(…), check() и третий аргумент _done."""
    tree = ast.parse(src)
    out = []

    def lit(v):
        if isinstance(v, ast.BinOp) and isinstance(v.op, ast.Mod):
            v = v.left
        if isinstance(v, ast.Constant) and isinstance(v.value, str) and CYR.search(v.value):
            out.append(v.value)
        if isinstance(v, ast.IfExp):
            lit(v.body)
            lit(v.orelse)
        if isinstance(v, ast.Tuple) and v.elts:          # ★ р79: run_cmd возвращает (текст, changed, undo)
            lit(v.elts[0])
    for n in ast.walk(tree):
        if isinstance(n, ast.Return) and n.value is not None:
            lit(n.value)
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("Refused", "AdapterError") and n.args:
            lit(n.args[0])
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "_done" and len(n.args) >= 3:
            lit(n.args[2])
    return [t for t in dict.fromkeys(out)]


def _code_only(src):
    """Исходник без докстрок (для проверок «в коде нет …»; комментарии ast.unparse и так отбрасывает)."""
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(n.body[0].value, ast.Constant):
            n.body[0].value.value = ""
    return ast.unparse(tree)


def _sample(t):
    return t.replace("%%", "\x00").replace("%d", "1").replace("%s", "X").replace("\x00", "%")


def offline(check):
    _paths()
    from core import auth, i18n, ops
    import domains
    domains.load_all()
    from domains import community as C
    import community_bot as CB
    roles = ("owner", "admin", "gm", "support")
    who = lambda p: {r for r in roles if auth.can(r, p)}
    check("Сообщество: право community.view — owner, admin, gm (gm — только просмотр); community.manage и community.ban — owner, admin; support — ничего",
          who("community.view") == {"owner", "admin", "gm"} and who("community.manage") == who("community.ban") == {"owner", "admin"})
    reg = ops.REGISTRY
    rev = ("community.app.decide", "community.tester.add", "community.tester.remove", "community.warns.clear", "community.ban", "community.unban")
    check("Сообщество: решение по заявке, роль, варны, бан и разбан — с откатом (обратная команда боту); отмена, повтор, проверочная — без отката; бан и "
          "разбан — под community.ban, остальное — community.manage",
          all(reg[n].reversible for n in rev) and not any(reg[n].reversible for n in ("community.cmd.cancel", "community.cmd.retry", "community.test"))
          and reg["community.ban"].perm == reg["community.unban"].perm == "community.ban"
          and all(reg[n].perm == "community.manage" for n in rev[:4] + ("community.cmd.cancel", "community.cmd.retry", "community.test")))
    fn, perm = _route("/api/community")
    check("Сообщество: маршрут GET /api/community — право community.view", fn is not None and perm == "community.view")
    sql = _read(ROOT, "sql", "adminc_30_community.sql")
    chk_cmd = set(re.search(r"CK_adm_BotCmd_cmd CHECK \(cmd IN \(([^)]*)\)\)", sql).group(1).replace("'", "").replace(" ", "").replace("\n", "").split(","))
    chk_role = set(re.search(r"CK_adm_BotCmd_role CHECK \(role_key IN \(([^)]*)\)\)", sql).group(1).replace("'", "").replace(" ", "").split(","))
    check("белые списки: команды панели = бота = CHECK adm.BotCmd (11, ★ р79 — с check), роль — только beta_tester («Beta Tester») у панели, бота и в CHECK",
          set(C.CMDS) == set(CB.CMDS) == chk_cmd and len(chk_cmd) == 11 and "check" in chk_cmd and C.ROLES == CB.ROLES == {"beta_tester": "Beta Tester"}
          and chk_role == {"beta_tester"} and set(C.ROLE_CMDS) == set(CB.ROLE_CMDS), (chk_cmd, chk_role))
    proc = sql[sql.index("CREATE PROCEDURE adm.BotSnapPut"):]
    proc = proc[:proc.index("\nGO")]
    read = {}
    for m in re.finditer(r"@x\.nodes\('/s/(\w)'\)", proc):
        read.setdefault(m.group(1), set())
    for kind in ("a", "t", "w", "b", "p"):
        seg = proc[:proc.index("@x.nodes('/s/%s')" % kind)]
        seg = seg[seg.rindex("INSERT adm."):]
        read[kind] = set(re.findall(r"n\.value\('@(\w+)'", seg))
    read["s"] = set(re.findall(r"@x\.value\('\(/s/@(\w+)\)\[1\]'", proc))
    check("снимок: атрибуты, которые шлёт бот (SNAP_FIELDS), = атрибутам, которые читает adm.BotSnapPut — ничего лишнего не уходит и не теряется",
          all(set(CB.SNAP_FIELDS[k]) == read[k] for k in ("s", "a", "t", "w", "b", "p")), (read, CB.SNAP_FIELDS))
    # снимок НАСТОЯЩЕГО state.json (только чтение файла): ответов анкеты и поприветствованных в нём нет
    try:
        with open(os.path.join(BOT, "state.json"), encoding="utf-8") as f:
            st = json.load(f)
        snap = CB.build_snapshot(st, set(), [], [], 0)
        xml = CB.to_xml(snap)
        leaks = 0
        for a in st.get("applications") or []:
            for k in ANKETA:
                v = str(a.get(k) or "")
                if len(v) >= 12 and v in xml:
                    leaks += 1
        appl = {str(a.get("uid")) for a in st.get("applications") or []}
        welcomed = [str(x) for x in (st.get("welcomed") or [])[:200] if len(str(x)) >= 15 and str(x) not in appl]
        valid = sum(1 for a in st.get("applications") or [] if isinstance(a.get("msg_id"), int) and a.get("status") in CB.APP_STATUSES)
        check("снимок настоящего state.json: заявок %d (= годных записей), ответов анкеты в XML нет, поприветствованных нет, ключей кроме s/a/t/w/b нет, "
              "IP и паролей нет" % len(snap["a"]),
              leaks == 0 and not any(w in xml for w in welcomed) and len({a["m"] for a in snap["a"]}) == len(snap["a"]) <= valid
              and set(snap) == {"s", "a", "t", "w", "b", "p"} and not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", xml) and "password" not in xml.lower(),
              (leaks, len(snap["a"]), valid))
    except OSError as ex:
        check("снимок настоящего state.json (файла нет на этом ПК)", True, str(ex))
    # ---- тексты и переводы
    csrc, bsrc = _read(ROOT, "domains", "community.py"), _read(BOT, "community_bot.py")
    texts = [t for t in _consts(csrc) if not t.startswith(" ")] + _bot_results(bsrc)
    check("Сообщество: тексты панели и итоги бота без «; » (%d)" % len(texts), all("; " not in t for t in texts), [t for t in texts if "; " in t][:5])
    samples = [_sample(t) for t in texts] + ["принять заявку: заявка 1001 от alice, участник 111111111111111111 (логин игры sitx), подана 2026-11-20 — причина: ok",
                                             "команда боту №5 поставлена: бан сервера Discord 123456789012345678 · account.block — запись журнала №7",
                                             "роль Beta Tester снята, одобренных заявок отклонено: 2", "роль Beta Tester уже была",
                                             "заявка одобрена, роль Beta Tester выдана, карточка исправлена, личное сообщение не дошло (личка закрыта)"]
    i18n.set_lang("en")
    try:
        miss = [(t, i18n.tr(t)) for t in samples if CYR.search(i18n.tr(t)) and t not in i18n._WORDS]   # слова-подстановки (_WORDS) переводятся в составе
    finally:
        i18n.set_lang("ru")
    check("Сообщество EN: тексты панели и итоги бота — без русских слов (%d строк)" % len(samples), not miss, miss[:6])
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("Сообщество: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "community.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("веб: раздел #/community с правом community.view, viewCommunity(my), скрипт после telegram.js; без innerHTML, данные (ники, причины, итоги "
          "бота) — acText, не T(); кнопки — только с community.manage / community.ban; реестр исключённых — общий discordBans()",
          '["#/community", "Сообщество", "community.view"' in app and 'case "community": return viewCommunity(my);' in app
          and 0 < idx.index("/telegram.js") < idx.index("/community.js") and "innerHTML" not in js
          and not re.search(r"T\(x\.(reason|result|user|title|by)", js) and "acText(x.reason)" in js and "acText(x.result)" in js
          and 'const M = can["community.manage"], B = can["community.ban"];' in js and "discordBans(regBox)" in js)
    q = re.compile(r'"((?:[^"\\]|\\.)*)"')
    code = "\n".join(l for l in js.splitlines() if not l.lstrip().startswith("//"))
    labels = {x for x in q.findall(code) if CYR.search(x)} | {"Сообщество"}
    have = set(re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(labels - have)
    check("веб EN: у русских строк раздела есть перевод в web/i18n.js (%d строк)" % len(labels), not lack, lack[:8])
    keys_all = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А7.6 (24.11): «Сообщество»"):]
    dup = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys_all.count(x) > 1})
    check("веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("community.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("Сообщество: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("Сообщество: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- SQL, права, выкладка
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    body = re.sub(r"--[^\n]*", "", body)
    bad = [w for w in ("THROW", "IIF(", "CONCAT(", "TRY_CONVERT", "FORMAT(", "STRING_SPLIT", "CREATE OR ALTER", "DROP TABLE IF EXISTS",
                       "DROP PROCEDURE IF EXISTS", "OPENJSON", "JSON_VALUE") if w in body.upper()]
    bs = _batches(sql)
    check("adminc_30: уровень 100 (без THROW / IIF / CONCAT / TRY_CONVERT / FORMAT / STRING_SPLIT / CREATE OR ALTER / JSON), QUOTED_IDENTIFIER и "
          "ANSI_NULLS ON — отдельным первым пакетом, повтор безопасен (IF OBJECT_ID … IS NULL / DROP PROCEDURE перед CREATE)",
          not bad and bs[0].strip().splitlines()[-1].strip() == "SET QUOTED_IDENTIFIER ON;" and "SET ANSI_NULLS ON;" in bs[0]
          and body.count("CREATE PROCEDURE") == body.count("DROP PROCEDURE") == 7, bad)
    inst = re.findall(r"OBJECT_ID\(N'(adm\.\w+)', N'P'\)", csrc)
    granted = set(re.findall(r"GRANT EXECUTE ON (adm\.\w+)\s+TO \[asda_admin\]", sql))
    check("«установлено ли» панель проверяет по процедуре, которую ей разрешено выполнять (у процедур бота DENY — под asda_admin их OBJECT_ID = NULL; "
          "найдено живым самотестом 24.11)", inst and set(inst) <= granted, (inst, granted))
    vr = _read(ROOT, "sql", "adminc_30_community_verify.sql")
    rows = re.findall(r"HAS_PERMS_BY_NAME\('([\w.]+)','OBJECT','(\w+)'\)\s*(?:AS v)?\s*,\s*(\d)", vr)
    yes = {r[0] for r in rows if r[2] == "1"}
    check("adminc_30_community_verify: ★ р79 М-3 — 36 проверок под asda_reports (каждое GRANT / DENY adminc_30): да только BotCmdClaim / BotCmdDone / "
          "BotSnapPut, семь таблиц × 4 действия и процедуры панели — нет, sysadmin — нет", len(rows) == 35 and "IS_SRVROLEMEMBER('sysadmin')" in vr and yes == {"adm.BotCmdClaim", "adm.BotCmdDone", "adm.BotSnapPut"},
          (len(rows), yes))
    v10, v99, dep = _read(ROOT, "sql", "adminc_10_verify.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql"), _read(ROOT, "deploy", "deploy_admin_center.py")
    check("выкладка: adminc_30 -x -I в AsdaAdmin после adminc_29 и до проверок, проверка ПОД asda_reports (adminc_30_community_verify, 36); adminc_10 — "
          "SELECT / процедуры панели = 1, INSERT / процедуры бота = 0; adminc_99 — откат шага",
          "Run 'adminc_30_community.sql' 'AsdaAdmin' -xi" in dep and dep.index("Run 'adminc_29_telegram.sql'") < dep.index("Run 'adminc_30_community.sql'")
          < dep.index("adminc_10_verify.sql') 2>&1") and "adminc_30_community_verify.sql" in dep and '("asda_reports/community", part_comm, 36)' in dep
          and "'adm.BotCmd SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmd','OBJECT','SELECT'), 1" in v10
          and "'adm.BotCmd INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmd','OBJECT','INSERT'), 0" in v10
          and "'adm.BotSnapPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotSnapPut','OBJECT','EXECUTE'), 0" in v10 and (v99 is None or "adminc_30_community.sql" in v99))
    want10 = []
    for t in ("BotCmd", "BotSnap", "BotApp", "BotTester", "BotWarn", "BotBan", "BotStaff"):
        for act, w in (("SELECT", 1), ("INSERT", 0), ("UPDATE", 0), ("DELETE", 0)):
            want10.append("'adm.%s %s', HAS_PERMS_BY_NAME('AsdaAdmin.adm.%s','OBJECT','%s'), %d" % (t, act, t, act, w))
    for p_, w in (("BotCmdPut", 1), ("BotCmdRelease", 1), ("BotCmdCancel", 1), ("BotCmdRetry", 1), ("BotCmdClaim", 0), ("BotCmdDone", 0), ("BotSnapPut", 0)):
        want10.append("'adm.%s EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.%s','OBJECT','EXECUTE'), %d" % (p_, p_, w))
    check("adminc_10 (панель): ★ р79 М-3 — каждое GRANT / DENY adminc_30 для asda_admin (%d строк)" % len(want10), all(x in v10 for x in want10),
          [x for x in want10 if x not in v10][:3])
    # М-2: у каждого объявления — докстрока (правило проекта «комментарий к объявлению»)
    nodoc = []
    for fname, src in (("community.py", csrc), ("community_bot.py", bsrc)):
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not ast.get_docstring(n):
                nodoc.append("%s:%s" % (fname, n.name))
    check("★ р79 М-2: у каждой функции, метода и класса domains/community.py и community_bot.py есть докстрока", not nodoc, nodoc[:8])
    procs_nc = []
    for pn in re.findall(r"CREATE PROCEDURE (adm[.][A-Za-z]+)", sql):
        k = sql.index("IF OBJECT_ID(N'%s', N'P')" % pn)
        seg = sql[sql.rfind("GO", 0, k):k]
        if "/*" not in seg and "--" not in seg:
            procs_nc.append(pn)
    check("★ р79 М-2: у каждой процедуры adminc_30 — комментарий перед ней", not procs_nc, procs_nc)
    ok_top = True
    code_c, code_b = _code_only(csrc), _code_only(bsrc)
    for src in (csrc, bsrc):
        tree = ast.parse(src)
        ok_top &= {type(n).__name__ for n in tree.body} <= {"Expr", "Import", "ImportFrom", "Assign", "FunctionDef", "AsyncFunctionDef", "ClassDef"}
    check("импорт domains/community и community_bot без побочных эффектов; в панели нет прямой записи в adm.Bot* (только процедуры); ни панель, ни бот "
          "не открывают playtest_accounts.txt и не трогают /password",
          ok_top and not re.findall(r"\b(INSERT|UPDATE|DELETE)\s+adm\.Bot", code_c) and "EXEC adm.BotCmdPut" in code_c
          and "playtest_accounts.txt" not in code_c and "playtest_accounts" not in code_b and "open(" not in code_c
          and "ACCOUNTS_FILE" not in code_b and "/password" not in code_b,
          ([k for k in ("playtest_accounts.txt", "open(") if k in code_c], [k for k in ("playtest_accounts", "ACCOUNTS_FILE", "/password") if k in code_b]))
    py = sys.executable
    try:
        r = subprocess.run([py, "-I", os.path.join(BOT, "test_community_bot.py")], capture_output=True, timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        n = re.search(r"Ran (\d+) tests", out)
        check("бот: модульные тесты «Сообщества» test_community_bot.py (%s тестов) — Discord подменён, сети нет" % (n.group(1) if n else "?"),
              r.returncode == 0 and n and "OK" in out, out[-400:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("бот: модульные тесты «Сообщества» (не запустились)", False, str(ex))


class _StubBlock:
    """Подставная account.block / account.unblock для стенда: записывает вызовы, игровую базу не трогает."""
    reversible = True

    def __init__(self, name, perm, refuse=False):
        """name — имя операции, refuse — предпросмотр отказывает («не заблокирована» и т. п.)."""
        self.name, self.perm, self.title, self.refuse, self.calls = name, perm, name, refuse, []

    def target(self, p):
        """Цель журнала — как у настоящей операции."""
        return "account:%s" % p.get("uid")

    def preview(self, ctx, p):
        """Предпросмотр (или отказ)."""
        from core.ops import OpRefused
        if self.refuse:
            raise OpRefused("учётка не заблокирована")
        return {"text": "блок учётки stub (%d) навсегда (30 лет): %s" % (p["uid"], p.get("reason", "")), "expect": {"us_block": 0, "rows": 0}, "warnings": []}

    def apply(self, ctx, p, prev):
        """Записать вызов."""
        self.calls.append(dict(p))
        return {"before": {"uid": p["uid"]}, "after": {"uid": p["uid"]}, "message": "stub"}

    def verify(self, ctx, p, res):
        """Проверка после записи — всегда успешна."""
        return None


def sandbox(check, ldb):
    """Своя база LocalDB: панель (операции) → бот (настоящий community_bot.Store под asda_reports, Worker с подставным Discord)."""
    _paths()
    from core import db, ops
    import domains
    domains.load_all()
    from domains import community as C
    from api import server as SRV
    import community_bot as CB
    import outbox_bot
    import test_community_bot as TB
    name = "AsdaComm_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    tmp = tempfile.TemporaryDirectory()
    saved_reg = {k: ops.REGISTRY[k] for k in ("account.block", "account.unblock")}
    saved_acc = C._account_of
    try:
        a = ldb(name)
        s23 = _read(ROOT, "sql", "adminc_23_reports.sql").replace("$(ReportsPw)", "Aa1-" + secrets.token_hex(12))
        s30 = _read(ROOT, "sql", "adminc_30_community.sql")
        for b in _batches(_read(ROOT, "sql", "adminc_02_schema.sql")) + _batches(s23) + _batches(s30) + _batches(s30):
            a.cursor().execute(b)
        np = a.cursor().execute("SELECT COUNT(*) FROM sys.procedures WHERE name LIKE 'BotCmd%' OR name = 'BotSnapPut'").fetchone()[0]
        nt = a.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name IN ('BotCmd', 'BotSnap', 'BotApp', 'BotTester', 'BotWarn', 'BotBan', "
                                "'BotStaff')").fetchone()[0]
        cols = {r[0] for r in a.cursor().execute("SELECT name FROM sys.columns WHERE object_id = OBJECT_ID('adm.BotApp')")}
        check("стенд: настоящие adminc_02 + adminc_23 + adminc_30 дважды (повтор безопасен), 7 таблиц и 7 процедур; в копии заявок нет столбцов анкеты",
              np == 7 and nt == 7 and not cols & set(ANKETA), (np, nt, cols))
        # ★ р79: доводка таблицы первой версии — старый CHECK без check и без столбцов changed / undo_json → после adminc_30 всё на месте
        a.cursor().execute("ALTER TABLE adm.BotCmd DROP CONSTRAINT CK_adm_BotCmd_cmd")
        a.cursor().execute("ALTER TABLE adm.BotCmd ADD CONSTRAINT CK_adm_BotCmd_cmd CHECK (cmd IN ('test', 'ban'))")
        for b in _batches(s30):
            a.cursor().execute(b)
        ck = a.cursor().execute("SELECT definition FROM sys.check_constraints WHERE name = 'CK_adm_BotCmd_cmd'").fetchone()[0]
        check("стенд р79: adminc_30 доводит таблицу первой версии — CHECK команд снова полный (с check), столбцы changed / undo_json есть",
              "'check'" in ck and "'app_approve'" in ck and a.cursor().execute("SELECT COL_LENGTH('adm.BotCmd', 'undo_json')").fetchone()[0], ck)
        db.set_override("admin", lambda database: ldb(name))

        class _AsBot:
            """Соединение под asda_reports (EXECUTE AS USER) — как у бота."""

            def __init__(self):
                """Открыть и переключиться на пользователя бота."""
                self.c = ldb(name)
                self.c.cursor().execute("EXECUTE AS USER = 'asda_reports'")

            def cursor(self):
                """Курсор."""
                return self.c.cursor()

            def close(self):
                """Вернуться и закрыть."""
                try:
                    self.c.cursor().execute("REVERT")
                finally:
                    self.c.close()
        cb = _AsBot()
        deny = []
        for qq in ("SELECT COUNT(*) FROM adm.BotCmd", "SELECT COUNT(*) FROM adm.BotApp", "SELECT COUNT(*) FROM adm.BotStaff", "UPDATE adm.BotCmd SET status = 2",
                   "DECLARE @i INT, @c INT; EXEC adm.BotCmdPut 'test', 0, NULL, NULL, NULL, N'xxx', NULL, N'x', 0, 1, @i OUTPUT, @c OUTPUT",
                   "EXEC adm.BotCmdCancel 1, N'x'", "SELECT COUNT(*) FROM adm.audit"):
            try:
                cur = cb.cursor().execute(qq)
                if qq.startswith("SELECT"):
                    cur.fetchall()
                deny.append(qq[:40])
            except Exception:
                pass
        cb.close()
        check("стенд: asda_reports — ни чтения и записи adm.Bot*, ни процедур панели, ни журнала (только процедуры бота)", not deny, deny)
        S = CB.Store(connect=_AsBot)
        state = TB.FakeState(TB.data())
        ad = TB.FakeAdapter()
        W = CB.Worker(S, state, ledger=outbox_bot.Ledger(os.path.join(tmp.name, "ledger.json")), limiter=outbox_bot.Limiter(gap=0, per_hour=1000),
                      staff=CB.StaffBook(os.path.join(tmp.name, "staff.json")))
        tick = lambda: asyncio.run(W.tick(ad))
        st = lambda cid: a.cursor().execute("SELECT status, attempts, result, is_test, block_audit, changed FROM adm.BotCmd WHERE id = ?", cid).fetchone()
        own, adm, gm = ops.Ctx(None, "own_t", "owner", "", "web"), ops.Ctx(None, "adm_t", "admin", "", "web"), ops.Ctx(None, "gm_t", "gm", "", "web")
        AL, BO, ST, RB = TB.A, TB.B, TB.S, TB.R
        v0 = C.view({})
        tick()
        v1 = C.view({"apps": "all"})
        check("стенд: до снимка — предупреждение «бот ещё не прислал копию»; после прохода бота копия на экране: 4 заявки (2 на рассмотрении), тестер bob, "
              "1 предупреждение, 1 бан, известные модераторы (2)",
              v0["snap"] is None and any("ещё не прислал" in w for w in v0["warnings"]) and v1["snap"]["n_apps"] == 4 and v1["counts"].get("pending") == 2
              and [t["user"] for t in v1["testers"]] == ["bob"] and len(v1["warns"]) == 1 and len(v1["bans"]) == 1 and v1["staff"] == 2,
              (v1["snap"], v1["counts"], v1["staff"]))
        # решение по заявке и откат
        w_gm = _refused(lambda: ops.run(gm, "community.app.decide", {"msg_id": "1001", "decision": "approve", "reason": "ok ok"}))
        pv = ops.run(adm, "community.app.decide", {"msg_id": "1001", "decision": "approve", "reason": "опытный игрок"}, dry=True)["preview"]
        r1 = ops.run(adm, "community.app.decide", {"msg_id": "1001", "decision": "approve", "reason": "опытный игрок"})
        c1 = r1["result"]["cmd"]
        w_dup = _refused(lambda: ops.run(adm, "community.app.decide", {"msg_id": "1001", "decision": "approve", "reason": "опытный игрок"}))
        tick()
        rec = state.data["applications"][0]
        check("стенд: решение по заявке — gm отказ, предпросмотр про личное сообщение и откат, вторая такая же — «уже ждёт»; бот выдал роль, исправил "
              "карточку, написал ОДИН раз; статус «выполнено», changed = 1, данные отката в базе",
              w_gm and any("отката личного сообщения нет" in w for w in pv["warnings"]) and w_dup and "уже ждёт бота" in w_dup
              and st(c1)[0] == 2 and st(c1)[5] is True and rec["status"] == "approved"
              and json.loads(a.cursor().execute("SELECT undo_json FROM adm.BotCmd WHERE id = ?", c1).fetchone()[0]) == {"role_added": True, "prev_status": "pending"},
              (tuple(st(c1)), ad.calls))
        n0 = len(ad.calls)
        ru = ops.undo(own, r1["audit_id"])
        tick()
        check("стенд: откат решения — app_reopen; бот вернул заявку на рассмотрение и снял роль, которую выдал (по данным отката из базы)",
              st(ru["result"]["cmd"])[0] == 2 and rec["status"] == "pending" and ("remove_role", AL, 777) in ad.calls[n0:], ad.calls[n0:])
        n1 = len(ad.calls)
        rt = ops.run(adm, "community.app.decide", {"msg_id": "1001", "decision": "approve", "reason": "selftest", "test": True})
        tick()
        check("стенд: решение с отметкой «тест» — «тест», Discord не вызывается, заявка остаётся на рассмотрении",
              st(rt["result"]["cmd"])[0] == 6 and ad.calls[n1:] == [] and rec["status"] == "pending", ad.calls[n1:])
        # тестер: снятие и откат; ★ В-1: «пустое» снятие — откат запрещён
        rr = ops.run(adm, "community.tester.remove", {"uid": str(BO), "reason": "не тестирует"})
        tick()
        rec2 = state.data["applications"][1]
        s_rm = (st(rr["result"]["cmd"])[0], rec2["status"], "Beta Tester" in ad.members[BO][1])
        ops.undo(own, rr["audit_id"])
        tick()
        rn = ops.run(adm, "community.tester.remove", {"uid": str(AL), "reason": "роли нет"})
        tick()
        w_un = _refused(lambda: ops.undo(own, rn["audit_id"]))
        row_n = [x for x in SRV.api_audit(type("Q", (), {"query": {}, "session": {"user": {"role": "owner"}}})(), None)["items"] if x["id"] == rn["audit_id"]][0]
        check("стенд: снять тестера — роль снята, заявка «отклонено», откат вернул роль и статус; ★ р79 В-1: снятие у участника без роли — "
              "changed = 0, откат отказан «ничего не изменила», в журнале действий вместо кнопки — причина",
              s_rm == (2, "rejected", False) and rec2["status"] == "approved" and "Beta Tester" in ad.members[BO][1]
              and st(rn["result"]["cmd"])[5] is False and w_un and "ничего не изменила" in w_un and not row_n["reversible"]
              and "ничего не изменила" in row_n.get("undo_note", "") and "Beta Tester" not in ad.members[AL][1], (s_rm, w_un, row_n.get("undo_note")))
        # предупреждения
        rw = ops.run(adm, "community.warns.clear", {"uid": str(AL), "reason": "ошибка модератора"})
        tick()
        w_cleared = list(state.data["warns"][str(AL)])
        ops.undo(own, rw["audit_id"])
        tick()
        check("стенд: снять предупреждения — бот очистил список, откат вернул их по данным отката из базы",
              w_cleared == [] and len(state.data["warns"][str(AL)]) == 1, w_cleared)
        # ★ В-1: бан уже стоял → откат не снимает
        rbn = ops.run(adm, "community.ban", {"uid": "555555555555555555", "reason": "уже забанен"})
        tick()
        w_ub = _refused(lambda: ops.undo(own, rbn["audit_id"]))
        check("стенд р79 В-1: бан уже стоял — changed = 0, откат отказан, бан на месте (чужой бан откат не снимает)",
              st(rbn["result"]["cmd"])[5] is False and w_ub and "ничего не изменила" in w_ub and 555555555555555555 in ad.banned, w_ub)
        # бан + блок: без проверки цели — отказ; проверка; бан; откат
        stub = _StubBlock("account.block", "players.block")
        ops.REGISTRY["account.block"] = stub
        ops.REGISTRY["account.unblock"] = _StubBlock("account.unblock", "players.unblock")
        C._account_of = lambda uid, explicit: (75001, "alice_login")
        w_nochk = _refused(lambda: ops.run(adm, "community.ban", {"uid": str(AL), "reason": "читы и спам", "account": True}, dry=True))
        rcs = ops.run(adm, "community.ban.check", {"uid": str(ST)})     # ★ р80 М-4: модератор НА сервере — проверяет бот (панель пускает)
        rc_ = ops.run(adm, "community.ban.check", {"uid": str(AL)})
        nchk = len(ad.calls)
        tick()
        check("стенд р79 В-2: бан с блоком без проверки цели — отказ «только после проверки» (текст — про окно бана, ★ р80 М-5); проверка модератора на "
              "сервере — бот: «защищённая роль»; проверка alice — бот: «проверка прошла», в Discord ничего (ни одного вызова)",
              w_nochk and "нажмите «Бан» ещё раз" in w_nochk and st(rcs["result"]["cmd"])[0] == 3 and "защищённая роль" in st(rcs["result"]["cmd"])[2]
              and st(rc_["result"]["cmd"])[0] == 2 and "проверка прошла" in st(rc_["result"]["cmd"])[2] and ad.calls[nchk:] == [],
              (w_nochk, tuple(st(rcs["result"]["cmd"])), tuple(st(rc_["result"]["cmd"]))))
        # ★ р80 М-4: модератор ушёл с сервера — в списке «вне сервера», панель отказывает в бане по id; разжалованный на сервере — из списка снят
        saved_s, saved_mx = ad.members.pop(ST), ad.modperm.pop(TB.MODX)
        W.dirty = True
        tick()
        w_gone = _refused(lambda: ops.run(adm, "community.ban.check", {"uid": str(ST)}, dry=True))
        stf = {r[0]: r[1] for r in a.cursor().execute("SELECT uid, on_server FROM adm.BotStaff")}
        check("стенд р80 М-4: ушедший модератор — в adm.BotStaff с on_server = 0, панель отказывает «ушедший с сервера»; разжалованный (на сервере без "
              "прав) — из списка снят", w_gone and "ушедший с сервера" in w_gone and stf.get(ST) is False and TB.MODX not in stf, (w_gone, stf))
        ad.members[ST], ad.modperm[TB.MODX] = saved_s, saved_mx
        # ★ р80 М-2: откат только той же цели, обратной командой, тот же «тест»
        c6 = a.cursor().execute("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.BotCmdPut 'tester_add', ?, 'beta_tester', NULL, ?, N'чужой откат', NULL, "
                                "N'x', 0, 0, @i OUTPUT, @c OUTPUT; SELECT @c", TB.GONE, rr["result"]["cmd"]).fetchone()[0]
        c6b = a.cursor().execute("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.BotCmdPut 'ban', ?, NULL, NULL, ?, N'не пара', NULL, N'x', 0, 0, "
                                 "@i OUTPUT, @c OUTPUT; SELECT @c", BO, rr["result"]["cmd"]).fetchone()[0]
        c6c = a.cursor().execute("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.BotCmdPut 'tester_add', ?, 'beta_tester', NULL, ?, N'тест не тест', "
                                 "NULL, N'x', 0, 1, @i OUTPUT, @c OUTPUT; SELECT @c", BO, rr["result"]["cmd"]).fetchone()[0]
        rw2 = ops.run(adm, "community.warns.clear", {"uid": str(AL), "reason": "второе снятие"})
        tick()
        a.cursor().execute("UPDATE adm.BotCmd SET undo_json = N'{\"_too_long\": true}' WHERE id = ?", rw2["result"]["cmd"])
        w_lost = _refused(lambda: ops.undo(own, rw2["audit_id"]))
        check("стенд р80 М-2 / М-6: откат другой цели, не парной командой или с другим «тест» — код 6 базы; данные отката не сохранены (длиннее "
              "предела) — откат отказан «откатывать нечем»", c6 == c6b == c6c == 6 and w_lost and "не сохранены" in w_lost, (c6, c6b, c6c, w_lost))
        holds = []
        orig_apply = stub.apply

        def watch_apply(ctx, p, prev):
            """Статус команды в момент блока."""
            holds.append(a.cursor().execute("SELECT TOP 1 status FROM adm.BotCmd ORDER BY id DESC").fetchone()[0])
            return orig_apply(ctx, p, prev)
        stub.apply = watch_apply
        pb = ops.run(adm, "community.ban", {"uid": str(AL), "reason": "читы и спам", "account": True}, dry=True)["preview"]
        rb = ops.run(adm, "community.ban", {"uid": str(AL), "reason": "читы и спам", "account": True})
        cb_ = rb["result"]["cmd"]
        tick()
        check("стенд: бан + блок — в окне: проверка прошла, блок до бана и сам не снимется; во время блока команда «ждёт блока» (7); бот банит; changed = 1",
              any(w.startswith("проверка цели №") for w in pb["warnings"]) and any("блок сам не снимется" in w for w in pb["warnings"])
              and holds == [7] and st(cb_)[0] == 2 and st(cb_)[5] is True and AL in ad.banned, (pb["warnings"][:3], holds, tuple(st(cb_))))
        ru2 = ops.undo(own, rb["audit_id"])
        tick()
        check("стенд: откат бана — разбан ботом (бан ставила эта команда); итог отката называет запись журнала блока",
              AL not in ad.banned and "снимается откатом записи журнала №%d" % rb["result"]["block_audit"] in ru2["message"], ru2["message"])
        # ★ В-2: бан не встал (ошибка Discord), блок стоит → крупное предупреждение и «Снять блок»
        real_ban = ad.ban

        async def bad_ban(uid, reason):
            """Discord отказал."""
            raise CB.AdapterError("Discord: нет прав на «бан»")
        ad.ban = bad_ban
        ops.run(adm, "community.ban.check", {"uid": str(AL), "reason": "перед вторым баном"})
        tick()
        rb2 = ops.run(adm, "community.ban", {"uid": str(AL), "reason": "второй бан", "account": True})
        tick()
        ad.ban = real_ban
        vs = C.view({})
        stuck = [s for s in vs["block_stuck"] if s["cmd"] == rb2["result"]["cmd"]]
        ops.run(adm, "account.unblock", {"uid": 75001})
        vs2 = C.view({})
        check("стенд р79 В-2: бан с блоком упал в Discord — команда «ошибка», на экране «учётка заблокирована, бана в Discord нет» (первым предупреждением) "
              "с номером записи блока; после account.unblock (своя запись журнала) предупреждение исчезло",
              st(rb2["result"]["cmd"])[0] == 3 and stuck and stuck[0]["block_audit"] == rb2["result"]["block_audit"]
              and vs["warnings"][0].startswith("учётка 75001 заблокирована, а бана в Discord нет") and not vs2["block_stuck"], (stuck, vs["warnings"][:1]))
        ops.REGISTRY["account.block"] = _StubBlock("account.block", "players.block", refuse=True)
        nb = len(ad.calls)
        w_blk = _refused(lambda: ops.run(adm, "community.ban", {"uid": str(AL), "reason": "третий бан", "account": True}))
        tick()
        check("стенд: блок учётки не встал — операция отказана, в Discord ничего", w_blk and not [x for x in ad.calls[nb:] if x[0] == "ban"], w_blk)
        # отказ бота (цель — бот), повтор, отмена, проверочные, пределы, CHECK, номер захвата
        rp = ops.run(adm, "community.ban", {"uid": str(RB), "reason": "проверка защиты"})
        tick()
        sp = st(rp["result"]["cmd"])
        ops.run(adm, "community.cmd.retry", {"id": rp["result"]["cmd"]})
        tick()
        sp2 = st(rp["result"]["cmd"])
        rcn = ops.run(adm, "community.tester.add", {"uid": str(AL), "reason": "отменю"})
        ops.run(adm, "community.cmd.cancel", {"id": rcn["result"]["cmd"]})
        nc = len(ad.calls)
        tick()

        class _OnlyManage:
            """Оператор с community.manage, но без community.ban (на будущее: если gm дадут manage)."""
            login, role = "m_t", "gm"

            def can(self, p):
                """Только manage."""
                return p == "community.manage"
        w_m4 = _refused(lambda: C.CmdRetry().preview(_OnlyManage(), {"id": rp["result"]["cmd"]}))
        check("стенд: цель — бот: бот отказывает, бана нет; повтор — снова отказ (попытка 2); отменённая команда боту не уходит; ★ р79 М-4: повтор бана "
              "без community.ban — отказ",
              sp[0] == 3 and "цель — бот" in sp[2] and sp2[0] == 3 and sp2[1] == 2 and RB not in ad.banned and st(rcn["result"]["cmd"])[0] == 4
              and not [x for x in ad.calls[nc:] if x[0] == "add_role"] and w_m4 and "community.ban" in w_m4, (tuple(sp), tuple(sp2), w_m4))
        for _ in range(10 - a.cursor().execute("SELECT COUNT(*) FROM adm.BotCmd WHERE is_test = 1 AND created_utc > DATEADD(HOUR, -1, SYSUTCDATETIME())").fetchone()[0]):
            ops.run(adm, "community.test", {})
        w_lim = _refused(lambda: ops.run(adm, "community.test", {}))
        for _ in range(4):
            tick()
        e_chk = None
        try:
            a.cursor().execute("INSERT adm.BotCmd (cmd, target_uid, role_key, reason, created_by, expires_utc) VALUES ('tester_add', 111111111111111111, "
                               "'admin', N'xxx', N'x', '20991231')")
        except Exception as ex:
            e_chk = str(ex)
        c4 = a.cursor().execute("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.BotCmdPut 'kick', 111111111111111111, NULL, NULL, NULL, N'xxx', NULL, N'x', "
                                "0, 0, @i OUTPUT, @c OUTPUT; SELECT @c").fetchone()[0]
        a.cursor().execute("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.BotCmdPut 'unban', 222222222222222222, NULL, NULL, NULL, N'nonce test', NULL, N'x', "
                           "0, 0, @i OUTPUT, @c OUTPUT")
        S2 = CB.Store(connect=_AsBot)
        got = S2.cmd_claim(1)
        mine = S2.cmd_nonce
        S2.cmd_nonce = "00000000-0000-0000-0000-000000000001"
        n_foreign = S2.cmd_done(got[0]["id"], True, "чужой итог")
        S2.cmd_nonce = mine
        n_own = S2.cmd_done(got[0]["id"], False, "свой итог")
        S2.cmd_claimed_ok()
        check("стенд: предел 10 проверочных в час; CHECK роли; команда не из списка — код 4; ★ р79 М-8: итог чужим номером захвата не пишется (0), своим — "
              "пишется (1)", w_lim and "предел 10 в час" in w_lim and e_chk and "CK_adm_BotCmd" in e_chk and c4 == 4 and n_foreign == 0 and n_own == 1,
              (w_lim, e_chk, c4, n_foreign, n_own))
        fq, _p = _route("/api/community")

        class _Req:
            """Запрос API с ролью."""

            def __init__(self, query, role):
                """query — параметры, role — роль пользователя."""
                self.query, self.session = dict(query), {"user": {"role": role, "login": "t_" + role}}
        ra, rg = fq(_Req({"apps": "all"}, "admin"), None), fq(_Req({}, "gm"), None)
        aud = {r[0]: r[1] for r in a.cursor().execute("SELECT action, COUNT(*) FROM adm.audit WHERE result = 'ok' AND action LIKE 'community.%' GROUP BY action")}
        check("стенд: журнал adm.audit — решения, откаты, тестер, варны, проверки цели, баны, отмена, повтор, проверочные; API — admin может команды, "
              "gm — только смотрит; у «пустых» команд в очереди — причина «откатывать нечего»",
              aud.get("community.app.decide") == 2 and aud.get("community.app.decide.undo") == 1 and aud.get("community.ban.check") == 3
              and aud.get("community.ban.undo") == 1 and aud.get("community.cmd.cancel") == 1 and aud.get("community.cmd.retry") == 1
              and ra["can"]["community.manage"] and not rg["can"]["community.manage"] and not rg["can"]["community.ban"]
              and any("ничего не изменила" in x["undo_note"] for x in ra["cmds"]), aud)
    finally:
        ops.REGISTRY.update(saved_reg)
        C._account_of = saved_acc
        db.set_override("admin", None)
        tmp.cleanup()
        m2 = ldb("master")
        try:
            m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m2.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def live(check):
    """Живая dev: только команды с отметкой «тест» (бот их не исполняет) и захват только проверочных. В Discord ничего не меняется."""
    _paths()
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import community as C
    import community_bot as CB
    if config.get().on_server:
        return check("живой самотест А7.6 «Сообщество» — с ПК", True)
    cn = db.admin()
    try:
        q = lambda o, p: db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?) AS p", (o, p))[0]["p"]
        perm = {"sel": q("adm.BotCmd", "SELECT"), "ins": q("adm.BotCmd", "INSERT"), "app": q("adm.BotApp", "SELECT"), "appd": q("adm.BotApp", "DELETE"),
                "put": q("adm.BotCmdPut", "EXECUTE"), "claim": q("adm.BotCmdClaim", "EXECUTE"), "snap": q("adm.BotSnapPut", "EXECUTE")}
        cols = {r["name"] for r in db.admin_rows(cn, "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID('adm.BotApp')")}
    finally:
        cn.close()
    check("живое (asda_admin): adm.Bot* — чтение и процедуры панели, без прямой записи и без процедур бота; в копии заявок нет столбцов анкеты",
          perm == {"sel": 1, "ins": 0, "app": 1, "appd": 0, "put": 1, "claim": 0, "snap": 0} and cols and not cols & set(ANKETA), (perm, cols))
    S = CB.Store()
    try:
        c = S._cn()
        try:
            rows = c.cursor().execute(_read(ROOT, "sql", "adminc_30_community_verify.sql")).fetchall()
        finally:
            c.close()
        bad = [tuple(r) for r in rows if int(r[1] or 0) != int(r[2])]
        check("живое (путь бота): пароль asda_reports из reports.env, вход по VPN, права = adminc_30_community_verify (%d проверок)" % len(rows),
              len(rows) == 36 and not bad, bad)
    except Exception as ex:
        check("живое (путь бота): вход asda_reports по VPN", False, "%s: %s" % (type(ex).__name__, str(ex)[:200]))
    v0 = C.view({"apps": "all"})
    real_q = [r for r in v0["cmds"] if not r["test"] and r["state"] in ("queued", "claimed", "hold")]
    check("живое: экран читается (установлено), настоящих команд, ждущих бота, нет — самотест ничего не исполняет", v0["installed"] and not real_q, real_q[:3])
    try:
        with open(os.path.join(BOT, "state.json"), encoding="utf-8") as f:
            stj = json.load(f)
        valid = len({a.get("msg_id") for a in stj.get("applications") or [] if isinstance(a.get("msg_id"), int) and a.get("status") in CB.APP_STATUSES})
    except (OSError, ValueError):
        valid = None
    s = v0.get("snap")
    check("живое: копия реестра есть и свежая (моложе %d мин — бот Oracle присылает её), заявок в копии = записей state.json (%s)" % (C.SNAP_STALE_MIN, valid),
          bool(s) and s["age_s"] < C.SNAP_STALE_MIN * 60 and (valid is None or s["n_apps"] == valid), s)
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    ids = [ops.run(ctx, "community.test", {})["result"]["cmd"]]
    pend = [x for x in v0["apps"] if x["status"] == "pending" and x["uid"] and not x["pending_cmd"]]
    if pend:
        ids.append(ops.run(ctx, "community.app.decide", {"msg_id": pend[0]["msg_id"], "decision": "approve", "reason": "selftest A7.6 (test, not executed)",
                                                         "test": True})["result"]["cmd"])
    got = []
    try:
        got = S.cmd_claim(5, test_only=True)          # ТОЛЬКО проверочные: настоящие команды этим захватом не берутся
        for x in got:
            if not x["test"]:
                raise RuntimeError("захват test_only вернул НЕ проверочную команду №%d" % x["id"])
        for x in got:
            S.cmd_done(x["id"], True, "тест — бот команду не исполнял, Discord не вызывался")
        S.cmd_claimed_ok()
        claimed = True
    except Exception as ex:
        claimed = "%s: %s" % (type(ex).__name__, str(ex)[:200])
    v1 = C.view({"apps": "all"})
    mine = [r for r in v1["cmds"] if r["id"] in ids]
    still = [x for x in v1["apps"] if pend and x["msg_id"] == pend[0]["msg_id"]]
    check("живое: проверочная команда и решение по заявке с отметкой «тест» (№%s) → захват только проверочных (или их уже взял работающий бот) → итог "
          "«тест»; заявка осталась на рассмотрении — в Discord ничего не изменилось" % ", ".join(str(i) for i in ids),
          claimed is True and len(mine) == len(ids) and all(r["state"] == "test" and r["test"] for r in mine)
          and (not pend or (still and still[0]["status"] == "pending")), (claimed, [(r["id"], r["state"]) for r in mine]))
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import community as C\nv = C.view({'apps': 'all'})\n"
             "print('CMPROBE installed=%s snap=%s ids=%s' % (v['installed'], bool(v['snap']), ','.join(str(r['id']) for r in v['cmds'][:30])))\n")
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
    mm = re.search(r"CMPROBE installed=(\w+) snap=(\w+) ids=([\d,]*)", out)
    check("служба на сервере (SSH): «Сообщество» читается, копия реестра есть, проверочная команда №%d видна" % ids[0],
          bool(mm) and mm.group(1) == "True" and mm.group(2) == "True" and str(ids[0]) in mm.group(3).split(","), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    sc = ssl.create_default_context()
    sc.check_hostname, sc.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=sc)).open(
            "https://%s:17890/api/community" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/community без входа — 401", code == 401, code)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import selftest as T
    T.utf8_stdout()                         # ★ р83 М-6 (А7.7): консоль cp1251 не роняет самотест
    offline(T.check)
    if "--sandbox" in sys.argv:
        sandbox(T.check, T._ldb)
    if "--live" in sys.argv:
        live(T.check)
    bad = [r for r in T.RESULTS if not r[1]]
    print("\nИТОГ: %d проверок, ошибок %d" % (len(T.RESULTS), len(bad)))
    sys.exit(1 if bad else 0)
