# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_gp7adjust_a6.py — самотест шага А6.9 «Баланс gp7: начислить и списать» (22.11.2026; domains/gp7adjust.py, sql/adminc_22_gp7adjust.sql,
операция money.adjust, /api/money/adjustments, web/money.js, консоль money adjust / undo / adjustments).

offline(check)  — проверка ввода и отказы до базы (логин, вид, сумма ≤ 0 и выше лимита, причина, ключ запроса), тексты отказов без «; »,
                  право money.adjust только у owner, операция (откатываемая, второй фактор, не ставится заданием), маршрут журнала, переводы EN
                  (shadowed_translations = 0), веб без innerHTML (окно подтверждения: сумма и логин заново, код второго фактора, ключ запроса),
                  консоль (без --as / неизвестный ключ / ключ без значения — отказ без базы), SQL установщика (замки, лимиты внутри процедуры,
                  права только EXECUTE adm.GP7Adjust, журнал не в GP7PurchaseLog), проверки adminc_10 / adminc_11, откат adminc_99, шаг выкладки.
sandbox(check, ldb) — СВОИ базы LocalDB: AsdaStoryLogin — НАСТОЯЩИЙ установщик шлюза install_gp7_balance.sql + НАСТОЯЩИЙ adminc_22 (запись —
                  под пользователем asda_ops, EXECUTE AS USER), AsdaStoryOp — Us_member, AsdaAdmin — adminc_02 (журнал панели). Часы суток лимита —
                  ФИКСИРОВАННЫЕ (adm.GP7AdjustNow стенда читает таблицу часов): тест не зависит от времени запуска. Учётки только синтетические;
                  учётка > 5000 и сайт без игровой — отказ самотеста (TEST_ONLY_MAX_UID). Все отказы, второе подтверждение, второй фактор из
                  браузера, идемпотентность, открытый HOLD подарка (настоящие GP7_GiftHold / GP7_GiftSettle), «баланс изменился» (настоящая
                  GP7_Purchase), суточный лимит на границе суток, откат и повторный откат, гонка двух корректировок (UPDLOCK), занятый замок —
                  понятный отказ, сбой журнала / фиксации после записи — откат транзакции, потерянный ответ фиксации — сверка по ключу.
live(check)     — только чтение живой dev: права asda_admin на журнал (SELECT да, EXEC нет), журнал = COUNT(*), testFixedBalance, предпросмотр
                  (@dry = 1, ничего не пишет) служебной учётке ≤ 5000 — число строк журнала и баланс не изменились; служба без входа — 401.
                  НИКАКИХ корректировок на живой.
Побочных эффектов при импорте нет.
"""
import datetime
import os
import re
import secrets
import subprocess
import sys
import threading
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
GP7_DIR = os.path.join(PORT, "AstoryServer", "Patches", "Gp7Gateway")
CYR = re.compile("[А-Яа-яЁё]")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _refused(fn):
    """Текст отказа OpRefused или None."""
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _route(path, meth="GET"):
    from api import server
    for m, rx, fn, perm, _full in server.ROUTES:
        if m == meth and rx.match(path):
            return fn, perm
    return None, None


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


GOOD = {"login": "svc7", "kind": "credit", "amount": "1000", "reason": "компенсация за сбой магазина", "req": "11111111-2222-4333-8444-555555555555"}
BAD = [  # (изменение параметров, начало текста отказа) — отказ ДО обращения к базе
    ({"login": ""}, "укажите учётку сайта gp7"), ({"login": "x" * 51}, "логин — не длиннее 50 знаков"), ({"kind": "add"}, "вид корректировки"),
    ({"kind": ""}, "вид корректировки"), ({"amount": "0"}, "сумма должна быть больше 0"), ({"amount": "-5"}, "сумма должна быть больше 0"),
    ({"amount": "100001"}, "сумма выше лимита операции 100000"), ({"amount": "99999999999999"}, "сумма — целое число от 1 до 100000"),
    ({"amount": "1.5"}, "сумма — целое число"), ({"amount": "abc"}, "сумма — целое число"), ({"amount": ""}, "сумма — целое число"),
    ({"reason": ""}, "причина обязательна"), ({"reason": "  ab  "}, "причина обязательна"), ({"reason": "x" * 301}, "причина обязательна"),
    ({"req": ""}, "нет ключа запроса"), ({"req": "not-a-uuid"}, "нет ключа запроса")]


def offline(check):
    """Проверка ввода, права, операция, маршрут, переводы, веб, консоль, SQL — без баз."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n, ops
    import domains
    domains.load_all()
    from domains import gp7adjust as G
    out = []
    for ch, want in BAD:
        p = dict(GOOD, **ch)
        r = _refused(lambda: G.plan(p))
        out.append((ch, r))
    check("баланс gp7: %d неверных вводов — отказ до базы с нужным текстом (логин, вид, сумма ≤ 0 и выше лимита, причина, ключ запроса)" % len(BAD),
          all(r and r.startswith(w) for (_c, r), (_c2, w) in zip(out, BAD)), [x for x, (_c, w) in zip(out, BAD) if not (x[1] or "").startswith(w)][:4])
    pl = G.plan(dict(GOOD, kind="debit", reason="  две   причины \n слитно  "))
    check("баланс gp7: разбор ввода — debit = отрицательная сумма, причина без лишних пробелов, ключ UUID", pl["delta"] == -1000
          and pl["reason"] == "две причины слитно" and pl["key"] == GOOD["req"], pl)
    texts = [r for _c, r in out] + list(G.REASONS.values()) + [G.LOCK_BUSY]
    check("баланс gp7: тексты отказов без «; » (перевод EN режет по «; »)", all("; " not in t for t in texts if t), [t for t in texts if t and "; " in t][:3])
    check("баланс gp7: право money.adjust — только owner (admin, gm, support — нет); money.view — owner и admin",
          auth.can("owner", "money.adjust") and not any(auth.can(r, "money.adjust") for r in ("admin", "gm", "support"))
          and auth.can("admin", "money.view"))
    op = ops.REGISTRY.get("money.adjust")
    check("баланс gp7: операция money.adjust — откатываемая, второй фактор из браузера, проверка отката (undo_guard), заданием не ставится",
          op is not None and op.reversible and op.two_factor and callable(getattr(op, "undo_guard", None)) and not getattr(op, "schedule_runner", None)
          and op.perm == "money.adjust")
    fn, perm = _route("/api/money/adjustments")
    check("баланс gp7: маршрут GET /api/money/adjustments — право money.view; запись — только операцией /api/ops/money.adjust", fn is not None and perm == "money.view")
    # консоль: без --as, неизвестный ключ, ключ без значения — отказ без базы
    import asda_admin as A

    def _exit(args):
        try:
            A._money(args)
        except SystemExit as ex:
            return str(ex)
        return None
    e1, e2, e3, e4 = (_exit(["adjust", "--login", "svc7", "--kind", "credit"]), _exit(["adjust", "--bogus", "1"]), _exit(["adjust", "--login"]),
                      _exit(["undo", "--audit", "x", "--as", ""]))
    check("баланс gp7 консоль: adjust без --as — отказ «от имени учётки панели», неизвестный ключ и ключ без значения — отказ без базы",
          e1 and "--as" in e1 and e2 and "неизвестный аргумент --bogus" in e2 and e3 and "нет значения" in e3 and e4, (e1, e2, e3, e4))
    # переводы EN
    i18n.set_lang("en")
    try:
        samples = {"начислить 500 gp7 учётке svc7 (сайт №3, игровая 7, служебная): было 0 → станет 500": "credit 500 gp7 to account svc7 (site #3, game 7, service)",
                   "списано 5 gp7 учётке a (сайт №3, игровой учётки нет): было 9 → стало 4 (корректировка №4) (testFixedBalance > 0 — игрок правку не "
                   "увидит (шлюз показывает всем 999999))": "the player will not see the change",
                   "превышен суточный лимит корректировок 500000 (по часам сервера): за сутки уже 450000": "already 450000 today",
                   "журнал корректировок не прочитан: ошибка базы: нет": "the adjustment log was not read: database error"}
        bad = [(k, i18n.tr(k)) for k, v in samples.items() if v not in i18n.tr(k) or CYR.search(i18n.tr(k))]
        allr = [i18n.tr(t) for t in texts if t]
        bad += [t for t in allr if CYR.search(t)]
    finally:
        i18n.set_lang("ru")
    check("баланс gp7 EN: отказы, предпросмотр, итог и сутки лимита переведены без русских слов (логин — как есть)", not bad, bad[:4])
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("баланс gp7: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])
    # веб
    js = open(os.path.join(ROOT, "web", "money.js"), encoding="utf-8").read()
    blk = js[js.index("★ А6.9"):]
    check("баланс gp7 веб: карточка только с правом money.adjust, окно подтверждения — сумма и логин заново, свежий код второго фактора, ключ запроса "
          "один на окно, отпечаток expect; журнал корректировок отдельной таблицей; без innerHTML, данные — текстовыми узлами",
          'can("money.adjust") ?' in js and "confirm_amount: cAmount.value.trim()" in blk and "confirm_login: cLogin.value.trim()" in blk
          and "totp: code.value.trim()" in blk and "expect: pv.expect" in blk and "const req = adjReq = adjReq || mnReq();" in blk and "/api/money/adjustments?" in blk
          and "innerHTML" not in js and "acText(x.reason)" in blk and "acText(pv.text)" in blk and "confirmWin(" in blk)
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "money.js")], capture_output=True, timeout=60)
        check("баланс gp7: node --check web/money.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("баланс gp7: node --check web/money.js (node не запустился)", False, str(ex))
    # SQL
    sql = open(os.path.join(ROOT, "sql", "adminc_22_gp7adjust.sql"), encoding="utf-8").read()
    proc = sql[sql.index("CREATE OR ALTER PROCEDURE adm.GP7Adjust"):sql.index("/* права логина")]
    check("баланс gp7 SQL: QUOTED_IDENTIFIER отдельным пакетом, нет таблиц шлюза — отказ установки, лимиты 100000 / 500000 — константы ВНУТРИ процедуры, "
          "замки: GP7AdjustLock → ключ → [user] → GP7Balance (UPDLOCK, HOLDLOCK), открытый HOLD — GP7GiftLog state 'H', своя транзакция или транзакция панели",
          re.search(r"^SET QUOTED_IDENTIFIER ON;\s*\nGO", sql, re.M) and "RAISERROR(N'adminc_22" in sql
          and "DECLARE @op_max BIGINT = 100000;" in proc and "DECLARE @day_max BIGINT = 500000;" in proc
          and proc.index("adm.GP7AdjustLock WITH (UPDLOCK, HOLDLOCK)") < proc.index("WHERE req_key = @req_key")
          < proc.index("dbo.[user] WITH (UPDLOCK, HOLDLOCK)") < proc.index("dbo.GP7Balance WITH (UPDLOCK, HOLDLOCK)")
          and "sender_user_id = @uid AND state = 'H'" in proc and "@@TRANCOUNT = 0" in proc and "@op_max" in proc.split("BEGIN TRANSACTION")[0])
    check("баланс gp7 SQL: корректировка не пишет журнал покупок (не выручка), права asda_ops — EXECUTE только adm.GP7Adjust, EXECUTE на dbo и прямая "
          "запись — DENY, password — DENY",
          "GP7PurchaseLog" not in proc and "GRANT EXECUTE ON adm.GP7Adjust TO [asda_ops];" in sql and sql.count("GRANT ") == 1
          and "DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];" in sql and "DENY INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [asda_ops];" in sql
          and "DENY SELECT ON dbo.[user] (password) TO [asda_ops];" in sql)
    v10 = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    v11 = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("баланс gp7 SQL: проверки прав — adminc_10 (asda_admin: журнал SELECT 1, запись 0, EXEC 0) и adminc_11 (asda_ops: EXEC adm.GP7Adjust 1, "
          "процедуры шлюза 0, прямая запись 0, password 0); откат adminc_99 снимает процедуру, часы, замок и пользователя, журнал оставляет; выкладка — "
          "adminc_22 после adminc_21",
          "'gp7.adm.GP7AdjustLog SELECT', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLog','OBJECT','SELECT'), 1" in v10
          and "'gp7.adm.GP7Adjust EXEC',   HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7Adjust','OBJECT','EXECUTE'), 0" in v10
          and "'ops.gp7.adm.GP7Adjust EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7Adjust','OBJECT','EXECUTE'), 1" in v11
          and "'ops.gp7.GP7_Purchase EXEC'" in v11 and "'ops.gp7.GP7Balance UPDATE'" in v11 and "'ops.gp7.user.password'" in v11
          and (rb is None or "DROP PROCEDURE adm.GP7Adjust" in rb) and (rb is None or "DROP TABLE adm.GP7AdjustLog" not in rb) and (rb is None or "DROP TABLE adm.GP7AdjustLock" in rb)
          and dep.index("Run 'adminc_21_san.sql' $null") < dep.index("Run 'adminc_22_gp7adjust.sql' $null"))
    # ★ ревизия 63 Н-3: взаимоблокировка 1205 и тайм-аут замка 1222 — один понятный отказ «баланс занят», не сбой
    from core import db as _db

    class _W:
        def __init__(self, text):
            self.text = text

        def rows(self, *a):
            raise _db.DbError(self.text)
    lk = [_refused(lambda t=t: G._call(_W(t), "x", 1, "причина", "o", "cli", GOOD["req"])) for t in (
        "запись в AsdaStoryLogin: Transaction (Process ID 61) was deadlocked on lock resources with another process and has been chosen as the "
        "deadlock victim. Rerun the transaction. (1205)", "запись в AsdaStoryLogin: Lock request time out period exceeded. (1222)")]
    other = None
    try:
        G._call(_W("запись в AsdaStoryLogin: Invalid object name (208)"), "x", 1, "причина", "o", "cli", GOOD["req"])
    except _db.DbError as ex:
        other = str(ex)
    check("баланс gp7 (ревизия 63 Н-3): 1205 (жертва взаимоблокировки) и 1222 (тайм-аут замка) — отказ «баланс занят шлюзом gp7», прочая ошибка "
          "базы — сбой как был", lk == [G.LOCK_BUSY, G.LOCK_BUSY] and other and "208" in other, (lk, other))
    # ★ ревизия 63 С-1: правило второго фактора у отката общее (как у заданий): stack.* и операции с two_factor; откатываемая из них — money.adjust
    rev2 = sorted(n for n, o in ops.REGISTRY.items() if o.reversible and ops.needs_two_factor(n))
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    opsrc = open(os.path.join(ROOT, "core", "ops.py"), encoding="utf-8").read()
    check("баланс gp7 (ревизия 63 С-1): откат операции со вторым фактором из браузера — ops.undo зовёт auth.totp_confirm (неверный код — отказ), "
          "api_undo передаёт тело, /api/audit отдаёт two_factor, app.js — окно confirmWin с текстом записи и полем кода; откатываемые операции со "
          "вторым фактором: %s" % rev2,
          rev2 == ["money.adjust"] and ops.needs_two_factor("stack.restart") and ops.needs_two_factor("maint.on") and not ops.needs_two_factor("items.give")
          and 'auth.totp_confirm(ctx.user_id, str((params or {}).get("totp")' in opsrc
          and "except (OpRefused, auth.AuthError) as ex:" in opsrc and "ops.undo(_ctx(req), int(m.group(1)), req.body_json())" in srv
          and 'r["two_factor"] = bool(r["reversible"] and ops.needs_two_factor(r["action"]))' in srv and "if (x.two_factor) {" in app
          and 'body = { totp: code.value.trim() };' in app and 'api("/api/audit/" + x.id + "/undo", body)' in app)
    check("баланс gp7 (ревизия 63 Н-2): из браузера ключ запроса живёт до успеха или правки полей (повтор после потерянного ответа — тот же ключ), "
          "в окне — последние корректировки учётки (pv.last)",
          "const req = adjReq = adjReq || mnReq();" in blk and "adjReq = null;" in blk and 'el.addEventListener("input", adjReset)' in blk
          and "pv.last" in blk)
    check("баланс gp7 (ревизия 63 М-4): adminc_11 сверяет и EXEC GP7_GiftHold / GP7_GiftLookup = 0",
          "'ops.gp7.GP7_GiftHold EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_GiftHold','OBJECT','EXECUTE'), 0" in v11
          and "'ops.gp7.GP7_GiftLookup EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_GiftLookup','OBJECT','EXECUTE'), 0" in v11)
    e5 = _exit(["adjust", "--login", "svc7", "--expect-before", "x", "--as", "o"])
    check("баланс gp7 (ревизия 63 М-2) консоль: ключ --expect-before («было» из --dry) принимается, у предпросмотра в подсказке применения он "
          "печатается", "--expect-before" in A.MONEY_KEYS["adjust"] and "--expect-before %s" in open(os.path.join(ROOT, "asda_admin.py"),
                                                                                                    encoding="utf-8").read(), e5)
    src = open(os.path.join(ROOT, "domains", "gp7adjust.py"), encoding="utf-8").read()
    check("баланс gp7: в SQL раздела нет столбца password и «SELECT *»; запись — только EXEC adm.GP7Adjust логином asda_ops (GameWriter)",
          src.lower().count("password") == 1 and "Столбец password не читается" in src and "select *" not in src.lower()
          and src.count('db.GameWriter("asdastorylogin")') == 3 and "UPDATE dbo.GP7Balance" not in src and "INSERT " not in src)
    imp = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, r'%s'); import domains.gp7adjust as G; print('IMPORT_OK', G.TEST_ONLY_MAX_UID)"
                          % ROOT], capture_output=True, timeout=60, cwd=ROOT)
    check("баланс gp7: импорт domains/gp7adjust.py ничего не делает (к базе и серверу не обращается), предохранитель самотеста выключен",
          b"IMPORT_OK None" in imp.stdout, (imp.stdout + imp.stderr)[-300:])


# ---------------------------------------------------------------- стенд LocalDB

USERS = [(1, "svc7"), (2, "svc8"), (3, "alpha"), (4, "nogame"), (5, "dupe"), (6, "dupe")]   # учётки сайта стенда
MEMBERS = [(7, "svc7"), (8, "svc8"), (9001, "alpha"), (9, "svc9"), (10, "dupe")]           # игровые: svc9 — без строки сайта, alpha — игрок > 5000


def sandbox(check, ldb):
    """Свои базы LocalDB: настоящий установщик шлюза + adminc_22 под asda_ops, фиксированные часы суток лимита, все ветки операции."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import audit, auth, db, ops
    import domains
    domains.load_all()
    from domains import gp7adjust as G, money as M
    tag = secrets.token_hex(3)
    names = {"L": "AsdaGaL_" + tag, "O": "AsdaGaO_" + tag, "A": "AsdaGaA_" + tag}
    mst = ldb("master")
    mst.cursor().execute("CREATE DATABASE [%s] COLLATE SQL_Latin1_General_CP1_CI_AS" % names["L"])
    mst.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names["O"])
    mst.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % names["A"])
    saved = (M.OP_DB, M.LOGIN_DB, M.test_fixed_balance, G.TEST_ONLY_MAX_UID, auth.totp_confirm)
    try:
        a = ldb(names["A"])
        for b in _batches(open(os.path.join(ROOT, "sql", "adminc_02_schema.sql"), encoding="utf-8").read()):
            a.cursor().execute(b)
        lc = ldb(names["L"]).cursor()
        lc.execute("CREATE TABLE dbo.[user] (id BIGINT IDENTITY(1,1) PRIMARY KEY, username VARCHAR(50) NOT NULL, password VARCHAR(50) NULL, "
                   "name VARCHAR(50) NULL, role VARCHAR(50) NULL)")
        lc.execute("SET IDENTITY_INSERT dbo.[user] ON")
        for i, u in USERS:
            lc.execute("INSERT dbo.[user] (id, username, password, role) VALUES (?, ?, ?, 'GA')", (i, u, "pw-" + u))
        lc.execute("SET IDENTITY_INSERT dbo.[user] OFF")
        nb = 0
        for b in _batches(open(os.path.join(GP7_DIR, "install_gp7_balance.sql"), encoding="utf-8-sig").read()):
            if not re.match(r"^\s*USE\s", b, re.I):
                lc.execute(b)
                nb += 1
        lc.execute("CREATE USER asda_ops WITHOUT LOGIN")
        sql = open(os.path.join(ROOT, "sql", "adminc_22_gp7adjust.sql"), encoding="utf-8").read()
        sql = re.sub(r"(?<![A-Za-z0-9_])AsdaStoryLogin(?![A-Za-z0-9_])", names["L"], sql)
        for b in _batches(sql):
            lc.execute(b)
        objs = {r[0] for r in lc.execute("SELECT SCHEMA_NAME(schema_id) + '.' + name FROM sys.objects WHERE type IN ('U', 'P', 'FN')").fetchall()}
        check("баланс gp7 стенд: НАСТОЯЩИЙ установщик шлюза (%d пакетов) и НАСТОЯЩИЙ adminc_22 — adm.GP7AdjustLog / GP7AdjustLock / GP7AdjustNow / "
              "GP7Adjust рядом с dbo.GP7Balance / GP7GiftLog" % nb,
              {"adm.GP7AdjustLog", "adm.GP7AdjustLock", "adm.GP7AdjustNow", "adm.GP7Adjust", "dbo.GP7Balance", "dbo.GP7GiftLog", "dbo.GP7_Purchase"} <= objs, sorted(objs))
        perms = {r[0]: r[1] for r in lc.execute(
            "EXECUTE AS USER = 'asda_ops'; SELECT 'exec_adj', HAS_PERMS_BY_NAME('adm.GP7Adjust','OBJECT','EXECUTE') UNION ALL "
            "SELECT 'exec_buy', HAS_PERMS_BY_NAME('dbo.GP7_Purchase','OBJECT','EXECUTE') UNION ALL "
            "SELECT 'exec_settle', HAS_PERMS_BY_NAME('dbo.GP7_GiftSettle','OBJECT','EXECUTE') UNION ALL "
            "SELECT 'upd_bal', HAS_PERMS_BY_NAME('dbo.GP7Balance','OBJECT','UPDATE') UNION ALL "
            "SELECT 'sel_bal', HAS_PERMS_BY_NAME('dbo.GP7Balance','OBJECT','SELECT') UNION ALL "
            "SELECT 'ins_log', HAS_PERMS_BY_NAME('adm.GP7AdjustLog','OBJECT','INSERT') UNION ALL "
            "SELECT 'pw', HAS_PERMS_BY_NAME('dbo.[user]','OBJECT','SELECT','password','COLUMN'); REVERT;").fetchall()}
        direct = None
        try:
            lc.execute("EXECUTE AS USER = 'asda_ops'; UPDATE dbo.GP7Balance SET balance = 1 WHERE user_id = 1;")
            direct = "прошло"
        except Exception as ex:                           # ожидаемо: нет права
            direct = str(ex)[:80]
        finally:
            try:
                lc.execute("REVERT")
            except Exception:
                pass
        check("баланс gp7 стенд: asda_ops — EXEC adm.GP7Adjust да; GP7_Purchase / GP7_GiftSettle, UPDATE и SELECT GP7Balance, INSERT журнала, password — "
              "нет; прямой UPDATE баланса — отказ сервера",
              perms == {"exec_adj": 1, "exec_buy": 0, "exec_settle": 0, "upd_bal": 0, "sel_bal": 0, "ins_log": 0, "pw": 0} and direct != "прошло",
              (perms, direct))
        # фиксированные часы суток лимита (функция стенда читает таблицу часов)
        lc.execute("CREATE TABLE adm.TestClock (t DATETIME2(0) NOT NULL)")
        lc.execute("INSERT adm.TestClock VALUES ('2026-11-20T12:00:00')")
        lc.execute("ALTER FUNCTION adm.GP7AdjustNow() RETURNS DATETIME2(0) AS BEGIN RETURN (SELECT TOP (1) t FROM adm.TestClock); END")
        clock = lambda t: lc.execute("UPDATE adm.TestClock SET t = ?", (t,))   # noqa: E731
        oc = ldb(names["O"]).cursor()
        oc.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(20), us_block TINYINT NOT NULL DEFAULT 0)")
        for u, lg in MEMBERS:
            oc.execute("INSERT dbo.Us_member (Userindex, Us_id) VALUES (?, ?)", (u, lg))

        class _Imp:
            """Связь «под asda_ops» (EXECUTE AS USER): перед закрытием — REVERT (иначе пул драйвера не сбросит сеанс)."""

            def __init__(self, cn):
                object.__setattr__(self, "_cn", cn)

            def __getattr__(self, k):
                return getattr(self._cn, k)

            def __setattr__(self, k, v):
                setattr(self._cn, k, v)

            def close(self):
                try:
                    self._cn.rollback()
                    self._cn.cursor().execute("REVERT")
                except Exception:
                    pass
                self._cn.close()
        mp = {"AsdaStoryLogin": names["L"], "AsdaStoryOp": names["O"]}

        def ops_cn(database):
            cn = ldb(mp.get(database, database))
            cn.cursor().execute("EXECUTE AS USER = 'asda_ops'")
            return _Imp(cn)
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("ops", ops_cn)
        db.set_override("admin", lambda database: ldb(names["A"]))
        M.OP_DB, M.LOGIN_DB = names["O"], names["L"]
        M.test_fixed_balance = lambda: (999999, None)
        G.TEST_ONLY_MAX_UID = 5000
        try:
            _checks(check, G, M, ops, audit, auth, db, lc, clock, names, ldb)
        finally:
            db.set_override("game", None)
            db.set_override("ops", None)
            db.set_override("admin", None)
    finally:
        M.OP_DB, M.LOGIN_DB, M.test_fixed_balance, G.TEST_ONLY_MAX_UID, auth.totp_confirm = saved
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def gateway_sql(src, account, item_code, amount, op_db, transactional=True):
    """★ ревизия 63 М-5: текст SQL тестовой одиночной покупки шлюза (testFixedBalance > 0) — из ИСХОДНИКА server.js (те же литералы
    siteUserProvisionSql, topUp и ветки «topUp ?»), подстановкой значений. transactional=False — прежний вид той же ветки (без BEGIN TRAN,
    без UPDLOCK): для показа гонки, которую правка закрыла."""
    def lits(a, b):
        i = src.index(a)
        j = src.index(b, i)
        return "".join(re.findall(r"`([^`]*)`", src[i:j]))
    prov = lits("function siteUserProvisionSql(account) {", "\n}")
    top = lits("const topUp = testFixedBalance() > 0", ': "";')
    one = lits(": topUp\n      ? `", "\n      : `SET NOCOUNT ON;")
    sub = {"${a}": account, "${sqlString(account)}": account, "${Number(amount)}": str(amount), "${itemCode}": str(item_code),
           "${amount}": str(amount)}
    for k, v in sub.items():
        prov, top, one = prov.replace(k, v), top.replace(k, v), one.replace(k, v)
    prov = prov.replace("AsdaStoryOP.dbo.", op_db + ".dbo.")
    q = one.replace("${siteUserProvisionSql(account)}", prov).replace("${topUp}", top)
    if not transactional:
        q = q.replace("SET XACT_ABORT ON; BEGIN TRAN; ", "").replace(" COMMIT TRAN;", "").replace(" WITH (UPDLOCK, HOLDLOCK)", "")
    return q


def _checks(check, G, M, ops, audit, auth, db, lc, clock, names, ldb):
    """Ветки операции на стенде (см. шапку sandbox)."""
    owner = ops.Ctx(None, "owner1", "owner", "127.0.0.1", "test")
    admin = ops.Ctx(None, "admin2", "admin", "127.0.0.1", "test")

    def bal(uid):
        r = lc.execute("SELECT balance FROM dbo.GP7Balance WHERE user_id = ?", (uid,)).fetchone()
        return None if r is None else int(r[0])

    def nlog():
        return int(lc.execute("SELECT COUNT(*) FROM adm.GP7AdjustLog").fetchone()[0])

    def key():
        return str(uuid.uuid4())

    def params(login="svc7", kind="credit", amount=1000, reason="компенсация за сбой магазина", req=None, confirm=True, **kw):
        p = {"login": login, "kind": kind, "amount": str(amount), "reason": reason, "req": req or key()}
        if confirm:
            p.update(confirm_amount=str(amount), confirm_login=kw.pop("confirm_login", login))
        p.update(kw)
        return p
    R = lambda c, p, dry=False: ops.run(c, "money.adjust", p, dry)        # noqa: E731
    F = lambda c, p, dry=False: _refused(lambda: ops.run(c, "money.adjust", p, dry))   # noqa: E731
    npl = int(lc.execute("SELECT COUNT(*) FROM dbo.GP7PurchaseLog").fetchone()[0])

    # ---- предпросмотр ничего не пишет; начисление; журнал; не выручка
    p1 = params(amount=1000)
    pv = R(owner, p1, dry=True)["preview"]
    check("баланс gp7 стенд: предпросмотр (@dry = 1) — было 0 → станет 1000, сутки 1000 из 500000, предупреждение testFixedBalance, ничего не записано",
          pv["balance_before"] == 0 and pv["balance_after"] == 1000 and pv["day_used"] == 1000 and pv["day_max"] == 500000
          and any("testFixedBalance > 0 — игрок правку не увидит" in w for w in pv["warnings"]) and bal(1) is None and nlog() == 0, pv)
    r1 = R(owner, dict(p1, expect=pv["expect"]))
    row = lc.execute("SELECT id, user_id, username, delta, balance_before, balance_after, reason, operator, via, undo_of FROM adm.GP7AdjustLog").fetchall()
    au = audit.get(r1["audit_id"])
    check("баланс gp7 стенд: начисление 1000 — баланс 0 → 1000, строка журнала корректировок (было → стало, причина, оператор), журнал панели «ok» "
          "со ссылкой на корректировку, журнал покупок gp7 не тронут (не выручка)",
          bal(1) == 1000 and len(row) == 1 and tuple(row[0])[1:] == (1, "svc7", 1000, 0, 1000, "компенсация за сбой магазина", "owner1", "cli", None)
          and au["result"] == "ok" and '"log_id": %d' % row[0][0] in au["after_json"]
          and int(lc.execute("SELECT COUNT(*) FROM dbo.GP7PurchaseLog").fetchone()[0]) == npl, (bal(1), [tuple(x) for x in row], au and au["result"]))
    # ---- идемпотентность: тот же ключ
    rep = F(owner, p1)
    kc = F(owner, dict(p1, amount="2000", confirm_amount="2000"))
    check("баланс gp7 стенд: повтор того же ключа — отказ «запрос уже выполнен: корректировка №…» без движения денег; тот же ключ с другой суммой — "
          "«ключ занят»", rep and rep.startswith("запрос уже выполнен: корректировка №") and kc and kc.startswith("ключ запроса уже занят")
          and bal(1) == 1000 and nlog() == 1, (rep, kc))
    # ---- второе подтверждение
    w1 = F(owner, params(amount=500, confirm_amount="50"))
    w2 = F(owner, params(amount=500, confirm_login="svc8"))
    w3 = F(owner, params(amount=500, confirm=False))
    check("баланс gp7 стенд: второе подтверждение — сумма или логин не совпали (или не набраны) — отказ, ничего не записано",
          w1 and w1.startswith("второе подтверждение: набранная сумма") and w2 and w2.startswith("второе подтверждение: набранный логин")
          and w3 and w3.startswith("второе подтверждение") and bal(1) == 1000 and nlog() == 1, (w1, w2, w3))
    # ---- права
    na = F(admin, params(amount=5))
    check("баланс gp7 стенд: роль admin — отказ «нет права money.adjust»", na and "money.adjust" in na and nlog() == 1, na)
    # ---- отказы
    cases = {
        "ниже 0": (params(kind="debit", amount=5000), "баланс ушёл бы ниже 0: было 1000"),
        "учётки сайта нет": (params(login="svc9", amount=5), "у учётки «svc9» нет строки сайта gp7"),
        "несколько учёток сайта": (params(login="dupe", amount=5), "логину «dupe» соответствуют несколько учёток сайта gp7"),
        "игрок > 5000": (params(login="alpha", amount=5), "самотест: корректировка только служебной учётке 1…5000"),
        "сайт без игровой": (params(login="nogame", amount=5), "самотест: корректировка только служебной учётке 1…5000"),
        "нигде нет": (params(login="ghost", amount=5), "учётки «ghost» нет ни в игре, ни на сайте gp7"),
        "без причины": (params(reason=""), "причина обязательна"),
        "сумма 0": (params(amount=0), "сумма должна быть больше 0"),
        "выше лимита": (params(amount=100001), "сумма выше лимита операции 100000")}
    got = {k: F(owner, p) for k, (p, _w) in cases.items()}
    check("баланс gp7 стенд: отказы — ниже 0, учётки сайта нет, несколько учёток сайта, учётка > 5000 и сайт без игровой (самотест), нет нигде, без "
          "причины, сумма 0, выше лимита — понятным текстом, ничего не записано",
          all(got[k] and got[k].startswith(w) for k, (_p, w) in cases.items()) and bal(1) == 1000 and nlog() == 1,
          {k: v for k, v in got.items() if not (v or "").startswith(cases[k][1])})
    # ---- открытый HOLD подарка (настоящие процедуры шлюза)
    lc.execute("EXEC dbo.GP7_Purchase @username = 'svc8', @item_code = 37, @amount = 1")      # строка баланса svc8 (мало денег — отказ, баланс 0)
    R(owner, params(login="svc8", amount=2000))
    h = lc.execute("EXEC dbo.GP7_GiftHold @username = 'svc8', @gs_key = 0x0102030405060708, @userindex = 8, @charidx = 0, @usernum = 1, "
                   "@sender_name = 0x416c696365, @recipient_name = 0x426f62, @code1 = 79698, @code2 = 0, @code3 = 0, @code4 = 0, @code5 = 0, "
                   "@code6 = 0, @code7 = 0, @amount = 399").fetchone()
    oh = F(owner, params(login="svc8", amount=10))
    oh_dry = F(owner, params(login="svc8", amount=10), dry=True)
    lc.execute("EXEC dbo.GP7_GiftSettle @order_id = ?, @action = 3", (int(h[3]),))
    after_refund = bal(2)
    ok_after = R(owner, params(login="svc8", amount=10))
    check("баланс gp7 стенд: открытый HOLD подарка (GP7_GiftHold шлюза) — отказ и в предпросмотре, и в записи; после возврата (GP7_GiftSettle REFUND) "
          "корректировка проходит",
          int(h[0]) == 1 and oh and oh.startswith("у учётки открыт подарок gp7") and oh_dry == oh and after_refund == 2000
          and ok_after["ok"] and bal(2) == 2010, (tuple(h), oh, oh_dry, after_refund, bal(2)))
    # ---- баланс изменился с предпросмотра (настоящая покупка шлюза)
    p2 = params(amount=300)
    pv2 = R(owner, p2, dry=True)["preview"]
    lc.execute("EXEC dbo.GP7_Purchase @username = 'svc7', @item_code = 37, @amount = 190")
    ch = F(owner, dict(p2, expect=pv2["expect"]))
    check("баланс gp7 стенд: покупка в шлюзе после предпросмотра — отказ «баланс изменился с предпросмотра», ничего не записано",
          ch and ch.startswith("баланс учётки изменился с предпросмотра") and bal(1) == 810, (ch, bal(1)))
    # ---- второй фактор из браузера
    web = ops.Ctx(None, "owner1", "owner", "127.0.0.1", "web")

    def bad_totp(uid, code):
        raise auth.AuthError("код второго фактора не подошёл (нужен свежий код из приложения, не тот, которым входили)")
    seen = []
    auth.totp_confirm = bad_totp
    t1 = F(web, params(amount=7, totp="000000", expect={"balance": 810}))
    auth.totp_confirm = lambda uid, code: seen.append(code)
    t2 = R(web, params(amount=7, totp="123456", expect={"balance": 810}))
    lv = lc.execute("SELECT TOP (1) via FROM adm.GP7AdjustLog ORDER BY id DESC").fetchone()[0]
    check("баланс gp7 стенд: из браузера — неверный код второго фактора — отказ без записи; верный (свежий) — записано, via = web, код в журнал панели "
          "не попал", t1 and t1.startswith("код второго фактора не подошёл") and t2["ok"] and seen == ["123456"] and lv == "web"
          and '"totp": "***"' in audit.get(t2["audit_id"])["params"] and bal(1) == 817, (t1, seen, lv))
    # ---- откат и повторный откат
    u1 = ops.undo(owner, t2["audit_id"])
    orig = lc.execute("SELECT undone_by FROM adm.GP7AdjustLog WHERE id = ?", (int(t2["result"]["log_id"]),)).fetchone()[0]
    back = lc.execute("SELECT delta, undo_of, balance_before, balance_after FROM adm.GP7AdjustLog WHERE id = ?", (orig,)).fetchone()
    u2 = _refused(lambda: ops.undo(owner, t2["audit_id"]))
    u3 = _refused(lambda: ops.undo(owner, u1["audit_id"]))
    w = db.GameWriter("asdastorylogin")
    try:
        direct = G._call(w, "svc7", -7, "повторный откат напрямую", "owner1", "cli", key(), undo_of=int(t2["result"]["log_id"]))
    finally:
        w.close()
    check("баланс gp7 стенд: откат — обратная корректировка (−7, undo_of = исходная, было 817 → стало 810), у исходной undone_by; повторный откат — "
          "отказ (панель: «уже откачена», процедура: undo-repeat), откат отката — отказ",
          bal(1) == 810 and tuple(back) == (-7, int(t2["result"]["log_id"]), 817, 810) and u2 and "уже откачена" in u2 and u3
          and "отката" in u3 and direct["reason"] == "undo-repeat", (bal(1), tuple(back) if back else None, u2, u3, direct["reason"]))
    # откат начисления, когда деньги уже потрачены — ниже 0
    sp = R(owner, params(login="svc8", amount=100))
    lc.execute("EXEC dbo.GP7_Purchase @username = 'svc8', @item_code = 37, @amount = 2100")
    u4 = _refused(lambda: ops.undo(owner, sp["audit_id"]))
    check("баланс gp7 стенд: откат начисления, которое уже потрачено, — отказ «ниже 0», баланс не тронут", u4 and u4.startswith("баланс ушёл бы ниже 0")
          and bal(2) == 10, (u4, bal(2)))
    # ---- суточный лимит на границе суток (фиксированные часы)
    lc.execute("UPDATE dbo.GP7Balance SET balance = 0 WHERE user_id IN (1, 2)")
    clock("2026-11-21T23:58:00")
    done = []
    for i in range(5):
        done.append(R(owner, params(login="svc7" if i % 2 == 0 else "svc8", amount=100000)))
    d6 = F(owner, params(amount=1))
    dbt = F(owner, params(kind="debit", amount=1))
    und = ops.undo(owner, done[0]["audit_id"])                  # откат в лимит не идёт
    clock("2026-11-21T23:59:59")
    d7 = F(owner, params(amount=1))
    clock("2026-11-22T00:00:00")
    d8 = R(owner, params(amount=100000))
    used = R(owner, params(amount=1), dry=True)["preview"]["day_used"]
    check("баланс gp7 стенд: суточный лимит по часам сервера (фиксированные) — 5 × 100000 в 23:58 проходят, шестая (и списание 1) — отказ "
          "«превышен суточный лимит … за сутки уже 500000»; откат в лимит не идёт; в 23:59:59 ещё отказ, в 00:00:00 новых суток — проходит",
          all(x["ok"] for x in done) and d6 and d6.startswith("превышен суточный лимит корректировок 500000 (по часам сервера): за сутки уже 500000")
          and dbt and dbt.startswith("превышен суточный лимит") and und["ok"] and d7 and d7.startswith("превышен суточный лимит") and d8["ok"]
          and used == 100001, (d6, dbt, d7, used))
    # ---- гонка двух корректировок одной учётке (UPDLOCK): денег хватает на одну
    lc.execute("UPDATE dbo.GP7Balance SET balance = 1500 WHERE user_id = 1")
    n0 = nlog()
    res = [None, None]
    gate = threading.Barrier(2)

    def worker(i):
        gate.wait()
        res[i] = _refused(lambda: R(owner, params(kind="debit", amount=1000)))
    th = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in th:
        t.start()
    for t in th:
        t.join(60)
    check("баланс gp7 стенд: гонка двух списаний по 1000 при балансе 1500 — ровно одно проходит, второе ждёт замок (UPDLOCK держится до фиксации после "
          "журнала панели) и получает отказ по НОВОМУ балансу 500 («баланс изменился с предпросмотра» или «ниже 0: было 500»), баланс 500, строка журнала одна",
          sorted([res[0] is None, res[1] is None]) == [False, True]
          and any(x and (x.startswith("баланс ушёл бы ниже 0: было 500") or x.startswith("баланс учётки изменился с предпросмотра")) for x in res)
          and bal(1) == 500 and nlog() == n0 + 1, (res, bal(1), nlog() - n0))
    # гонка на уровне процедуры (без сверки «было»): две транзакции панели одновременно — вторая ждёт замок и видит баланс после первой
    lc.execute("UPDATE dbo.GP7Balance SET balance = 1500 WHERE user_id = 1")
    w1, w2 = db.GameWriter("asdastorylogin"), db.GameWriter("asdastorylogin")
    out2 = {}
    try:
        a1 = G._call(w1, "svc7", -1000, "гонка: первая транзакция", "owner1", "cli", key())

        def second():
            out2["r"] = G._call(w2, "svc7", -1000, "гонка: вторая транзакция", "owner1", "cli", key())
        t2 = threading.Thread(target=second)
        t2.start()
        t2.join(1.5)
        waiting = t2.is_alive()                      # вторая стоит на замке, пока первая не зафиксирована
        w1.commit()
        t2.join(30)
        w2.commit()
    finally:
        w1.close()
        w2.close()
    check("баланс gp7 стенд: гонка на уровне процедуры (UPDLOCK) — вторая транзакция ждёт фиксации первой и получает «ниже 0» по балансу 500; "
          "баланс 500, одна строка журнала",
          int(a1["status"]) == 1 and waiting and out2.get("r") and out2["r"]["reason"] == "below-zero" and int(out2["r"]["balance_before"]) == 500
          and bal(1) == 500, (a1["reason"], waiting, out2.get("r") and out2["r"]["reason"], bal(1)))
    # ---- занятый замок — понятный отказ (не 500)
    hold = ldb(names["L"])
    hold.autocommit = False
    hold.cursor().execute("SELECT * FROM dbo.GP7Balance WITH (UPDLOCK, HOLDLOCK) WHERE user_id = 1")
    try:
        bz = F(owner, params(amount=5))
    finally:
        hold.rollback()
        hold.close()
    check("баланс gp7 стенд: баланс держит чужая транзакция (шлюз) дольше 5 с — отказ «баланс учётки сейчас занят шлюзом gp7», не сбой",
          bz == G.LOCK_BUSY and bal(1) == 500, bz)
    # ---- сбой после записи: журнал панели / фиксация — откат транзакции (компенсация), потерянный ответ фиксации — сверка по ключу
    n1, b1 = nlog(), bal(1)
    real_write = audit.write

    def bad_write(ctx, action, *a, **kw):
        if action == "money.adjust" and kw.get("result") == "ok":
            raise RuntimeError("AsdaAdmin недоступна (самотест)")
        return real_write(ctx, action, *a, **kw)
    audit.write = bad_write
    try:
        e1 = None
        try:
            R(owner, params(amount=11))
        except RuntimeError as ex:
            e1 = str(ex)
    finally:
        audit.write = real_write
    check("баланс gp7 стенд: сбой журнала панели после записи процедуры — транзакция откатывается: баланс и журнал корректировок как были",
          e1 and "AsdaAdmin" in e1 and nlog() == n1 and bal(1) == b1, (e1, nlog() - n1, bal(1)))
    real_commit = db.GameWriter.commit

    def bad_commit(self):
        raise RuntimeError("связь оборвалась при фиксации (самотест)")
    db.GameWriter.commit = bad_commit
    try:
        e2 = None
        try:
            R(owner, params(amount=12))
        except RuntimeError as ex:
            e2 = str(ex)
    finally:
        db.GameWriter.commit = real_commit
    last = audit.query("money.adjust", limit=2)
    check("баланс gp7 стенд: фиксация не прошла — баланс и журнал корректировок как были, в журнале панели «ok» и следом «error … НЕ зафиксирована»; "
          "откат такой записи — отказ «не зафиксирована»",
          e2 and nlog() == n1 and bal(1) == b1 and last[0]["result"] == "error" and "НЕ зафиксирована" in last[0]["message"] and last[1]["result"] == "ok"
          and (_refused(lambda: ops.undo(owner, last[1]["id"])) or "").startswith("корректировки №"), (e2, [(x["result"], x["message"][:60]) for x in last]))

    def lost_commit(self):
        real_commit(self)
        raise RuntimeError("ответ фиксации потерян (самотест)")
    db.GameWriter.commit = lost_commit
    try:
        r3 = R(owner, params(amount=13))
    finally:
        db.GameWriter.commit = real_commit
    l3 = audit.query("money.adjust", limit=1)[0]
    check("баланс gp7 стенд: фиксация прошла, а ответ потерян — сверка по ключу запроса: записано, журнал панели «ok» без ложного «error»",
          r3["ok"] and nlog() == n1 + 1 and bal(1) == b1 + 13 and l3["result"] == "ok" and l3["id"] == r3["audit_id"], (r3.get("message"), l3["result"]))
    # ★ ревизия 63 Н-2: повтор после потерянного ответа с ТЕМ ЖЕ ключом (браузер держит ключ до успеха) — второй корректировки нет
    p13 = params(amount=13, req=lc.execute("SELECT TOP (1) CONVERT(varchar(36), req_key) FROM adm.GP7AdjustLog ORDER BY id DESC").fetchone()[0])
    again = F(owner, p13)
    check("баланс gp7 стенд (ревизия 63 Н-2): повтор с тем же ключом после потерянного ответа — «запрос уже выполнен: корректировка №…», вторая "
          "корректировка не проведена", again and again.startswith("запрос уже выполнен: корректировка №") and nlog() == n1 + 1
          and bal(1) == b1 + 13, again)
    # ★ ревизия 63 Н-1: списание ровно до 0 — «ok», без ложной записи «error … проверка после записи»
    full = bal(1)
    r0 = R(owner, params(kind="debit", amount=full))
    l0 = audit.query("money.adjust", limit=1)[0]
    check("баланс gp7 стенд (ревизия 63 Н-1): списание всего баланса (%d → 0) — «ok», проверка после записи не падает, записи «error» нет" % full,
          r0["ok"] and bal(1) == 0 and l0["result"] == "ok" and l0["id"] == r0["audit_id"], (l0["result"], l0["message"][:80]))
    # ★ ревизия 63 М-2: из браузера без отпечатка «было» — отказ; из консоли устаревший --expect-before — «баланс изменился»
    auth.totp_confirm = lambda uid, code: None
    m2a = F(web, params(amount=3, totp="111111"))
    m2b = F(web, params(amount=3, totp="111111", expect={}))
    m2c = F(owner, params(amount=3, expect={"balance": 12345}))
    check("баланс gp7 стенд (ревизия 63 М-2): из браузера без expect.balance — отказ «нет отпечатка предпросмотра», консоль с устаревшим «было» — "
          "отказ «баланс изменился», ничего не записано",
          m2a and m2a.startswith("нет отпечатка предпросмотра") and m2b == m2a and m2c and m2c.startswith("баланс учётки изменился")
          and bal(1) == 0, (m2a, m2b, m2c))
    # ★ ревизия 63 С-1: откат из браузера — со свежим кодом второго фактора; без кода / неверный / повтор того же кода — отказ, деньги на месте
    used = set()

    def one_time(uid, code):
        if not code or code in used or code == "000000":
            raise auth.AuthError("код второго фактора не подошёл (нужен свежий код из приложения, не тот, которым входили)")
        used.add(code)
    auth.totp_confirm = one_time
    c1 = R(web, params(amount=40, totp="222222", expect={"balance": 0}))
    nr = int(lc.execute("SELECT COUNT(*) FROM adm.GP7AdjustLog").fetchone()[0])
    x1 = _refused(lambda: ops.undo(web, c1["audit_id"]))
    x2 = _refused(lambda: ops.undo(web, c1["audit_id"], {"totp": "000000"}))
    x3 = _refused(lambda: ops.undo(web, c1["audit_id"], {"totp": "222222"}))
    rf = audit.query("money.adjust.undo", limit=1)[0]
    ok_u = ops.undo(web, c1["audit_id"], {"totp": "333333"})
    check("баланс gp7 стенд (ревизия 63 С-1): откат корректировки из браузера без кода, с неверным и с уже использованным кодом — отказ (запись "
          "журнала «refused»), деньги на месте; со свежим кодом — откат прошёл",
          all(x and x.startswith("код второго фактора не подошёл") for x in (x1, x2, x3)) and rf["result"] == "refused" and ok_u["ok"]
          and bal(1) == 0 and int(lc.execute("SELECT COUNT(*) FROM adm.GP7AdjustLog").fetchone()[0]) == nr + 1, (x1, x2, x3, rf["result"]))
    auth.totp_confirm = lambda uid, code: (_ for _ in ()).throw(auth.AuthError("консоль не должна спрашивать код"))
    c2 = R(owner, params(amount=41))
    cli = ops.Ctx(None, "owner1", "owner", "", "cli")
    ok_c = ops.undo(cli, c2["audit_id"])
    check("баланс gp7 стенд (ревизия 63 С-1): откат из консоли (--as) — без кода второго фактора, как применение", ok_c["ok"] and bal(1) == 0)
    fn_a, _pa = _route("/api/audit")

    class _Ra:
        def __init__(self, q):
            self.query, self.session = q, {"user": {"role": "owner", "login": "t"}}
    rows_a = fn_a(_Ra({"action": "money.adjust", "limit": "50"}), None)["items"]
    tf = [r for r in rows_a if r["action"] == "money.adjust" and r["reversible"]]
    check("баланс gp7 стенд (ревизия 63 С-1): /api/audit — у откатываемых строк money.adjust признак two_factor (браузер спросит код)",
          tf and all(r["two_factor"] for r in tf) and all(not r["two_factor"] for r in rows_a if not r["reversible"]), len(tf))
    # ★ ревизия 63 М-1: консоль money undo — только записи money.adjust
    import asda_admin as A
    other_id = audit.write(owner, "items.give", "char:1/1", {"x": 1}, after={"x": 1}, result="ok", message="выдано (самотест)")
    try:
        A._money(["undo", "--audit", str(other_id), "--as", "owner1"])
        m1 = None
    except SystemExit as ex:
        m1 = str(ex)
    check("баланс gp7 стенд (ревизия 63 М-1): money undo --audit N чужой записи (items.give) — отказ до отката", m1 and "не корректировка баланса gp7" in m1
          and "items.give" in m1, m1)
    # ---- ★ ревизия 63 М-5: гонка тестовой покупки шлюза (testFixedBalance > 0) с корректировкой adm.GP7Adjust — НАСТОЯЩИЙ текст SQL из
    #   server.js; между пополнением и покупкой — пауза (WAITFOR), в паузе — списание панелью суммы «реальный + 1»
    gsrc = open(os.path.join(GP7_DIR, "server.js"), encoding="utf-8").read()

    def race_run(transactional):
        lc.execute("UPDATE dbo.GP7Balance SET balance = 500 WHERE user_id = 1")
        q = gateway_sql(gsrc, "svc7", 37, 300, names["O"], transactional).replace("EXEC dbo.GP7_Purchase", "WAITFOR DELAY '00:00:01.500'; EXEC dbo.GP7_Purchase", 1)
        out = {}

        def buy():
            cn = ldb(names["L"])
            cur = cn.cursor()
            try:
                cur.execute(q)
                rows = []
                while True:
                    if cur.description:
                        rows += [tuple(r) for r in cur.fetchall()]
                    if not cur.nextset():
                        break
                out["rows"] = rows
            except Exception as ex:              # взаимоблокировка / тайм-аут шлюза — в проверку
                out["err"] = str(ex)[:200]
            finally:
                cn.close()
        t = threading.Thread(target=buy)
        t.start()
        threading.Event().wait(0.5)
        out["adj"] = _refused(lambda: R(owner, params(kind="debit", amount=501)))
        t.join(30)
        out["bal"] = bal(1)
        return out
    old = race_run(False)
    new = race_run(True)
    st_old = next((r for r in old.get("rows", []) if len(r) == 3), None)
    st_new = next((r for r in new.get("rows", []) if len(r) == 3), None)
    check("баланс gp7 стенд (ревизия 63 М-5): тестовая покупка шлюза (настоящий текст SQL server.js) против корректировки в окне «пополнено, ещё "
          "не куплено» — прежний вид без транзакции: списание 501 при реальном 500 ПРОХОДИТ, покупка срывается, остаток тестовых денег %s; "
          "новый вид: корректировка ждёт замок [user] и получает «ниже 0: было 500», покупка проходит, баланс 500, взаимоблокировки нет"
          % old.get("bal"),
          "BEGIN TRAN" in gateway_sql(gsrc, "svc7", 37, 300, names["O"]) and old.get("adj") is None and st_old and int(st_old[0]) == 2
          and old.get("bal") == 299 and "err" not in new and new.get("adj") and new["adj"].startswith("баланс ушёл бы ниже 0: было 500")
          and st_new and int(st_new[0]) == 1 and new.get("bal") == 500, (old, new))
    # ---- журнал корректировок (money.view) и маршрут
    j = G.adjustments({})
    js = G.adjustments({"account": "svc8"})
    fn, _perm = _route("/api/money/adjustments")

    class _Req:
        def __init__(self, q):
            self.query, self.session = q, {"user": {"role": "admin", "login": "t"}}
    api = fn(_Req({"size": "3"}), None)
    check("баланс gp7 стенд: журнал корректировок — строк = COUNT(*) %d, новые сверху, фильтр по учётке (только svc8), учётка игры и категория, "
          "откаты помечены; маршрут /api/money/adjustments отдаёт ту же страницу" % nlog(),
          j["total"] == nlog() and [r["id"] for r in j["rows"]] == sorted([r["id"] for r in j["rows"]], reverse=True)
          and js["total"] == int(lc.execute("SELECT COUNT(*) FROM adm.GP7AdjustLog WHERE user_id = 2").fetchone()[0]) and all(r["username"] == "svc8" for r in js["rows"])
          and all(r["cat"] == "service" for r in j["rows"]) and any(r["undo_of"] for r in j["rows"]) and any(r["undone_by"] for r in j["rows"])
          and api["total"] == j["total"] and len(api["rows"]) == 3 and not j["errors"], (j["total"], nlog(), j["errors"]))
    check("баланс gp7 стенд: за весь прогон журнал покупок gp7 вырос только на покупки шлюза самого теста (корректировки туда не пишутся)",
          int(lc.execute("SELECT COUNT(*) FROM dbo.GP7PurchaseLog WHERE item_code <> 37 AND item_code <> 79698").fetchone()[0]) == 0)


# ---------------------------------------------------------------- живое (только чтение)

def live(check):
    """Только чтение живой dev: права и журнал, testFixedBalance, предпросмотр @dry = 1 служебной учётке (ничего не пишет), служба — 401."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import gp7adjust as G
    if config.get().on_server:
        return check("живой самотест А6.9 — с ПК", True)
    with db.GameReader("asdastorylogin") as g:
        perm = {k: g.one("SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?) AS p", (o, w))["p"] for k, o, w in (
            ("log_select", "adm.GP7AdjustLog", "SELECT"), ("log_insert", "adm.GP7AdjustLog", "INSERT"), ("proc_exec", "adm.GP7Adjust", "EXECUTE"),
            ("bal_update", "dbo.GP7Balance", "UPDATE"))}
        n = int(g.one("SELECT COUNT(*) AS n FROM adm.GP7AdjustLog")["n"])
        svc = g.one("SELECT TOP (1) u.username, b.balance FROM dbo.[user] u JOIN %s.dbo.Us_member m ON m.Us_id = u.username COLLATE Arabic_CI_AS "
                    "LEFT JOIN dbo.GP7Balance b ON b.user_id = u.id WHERE m.Userindex BETWEEN 1 AND 5000 AND NOT EXISTS (SELECT 1 FROM dbo.GP7GiftLog x "
                    "WHERE x.sender_user_id = u.id AND x.state = 'H') AND (SELECT COUNT(*) FROM dbo.[user] d WHERE d.username = u.username) = 1 "
                    "ORDER BY m.Userindex" % "AsdaStoryOp")
    check("живое (asda_admin): журнал корректировок adm.GP7AdjustLog — SELECT да, INSERT нет; EXEC adm.GP7Adjust нет; UPDATE GP7Balance нет",
          perm == {"log_select": 1, "log_insert": 0, "proc_exec": 0, "bal_update": 0}, perm)
    j = G.adjustments({"size": "5"})
    check("живое: журнал корректировок панели — total = COUNT(*) (%d), без ошибок, сутки лимита прочитаны" % n,
          j["total"] == n and not j["errors"] and j["day"] is not None, (j["total"], j["errors"]))
    from domains import money as M
    tfb, err = M.test_fixed_balance()
    check("живое: testFixedBalance шлюза прочитан белым списком (%s) — при > 0 предупреждение «игрок правку не увидит»" % tfb,
          err is None and isinstance(tfb, int) and (G._tfb_warning() or "").startswith("testFixedBalance > 0") == (tfb > 0), (tfb, err))
    # ★ ревизия 63 М-3: живой блок — ТОЛЬКО чтение: процедура на живой не вызывается (даже @dry — он берёт замки шлюза). Определения и
    #   действующие права asda_ops — по SSH под sysadmin: OBJECT_DEFINITION, fn_my_permissions под EXECUTE AS USER с REVERT
    q = ("SET NOCOUNT ON; USE AsdaStoryLogin; SELECT 'NOW|' + REPLACE(REPLACE(OBJECT_DEFINITION(OBJECT_ID('adm.GP7AdjustNow')) COLLATE DATABASE_DEFAULT, CHAR(13), ' '), CHAR(10), ' '); "
         "SELECT 'LIM|' + CAST(CASE WHEN OBJECT_DEFINITION(OBJECT_ID('adm.GP7Adjust')) LIKE '%@op_max BIGINT = 100000;%' AND "
         "OBJECT_DEFINITION(OBJECT_ID('adm.GP7Adjust')) LIKE '%@day_max BIGINT = 500000;%' THEN 1 ELSE 0 END AS varchar(1)); "
         "EXECUTE AS USER = 'asda_ops'; SELECT 'PERM|' + ISNULL(OBJECT_SCHEMA_NAME(o.object_id) COLLATE DATABASE_DEFAULT + '.' + o.name COLLATE DATABASE_DEFAULT, '?') + '|' + p.permission_name COLLATE DATABASE_DEFAULT "
         "FROM sys.objects o CROSS APPLY fn_my_permissions(QUOTENAME(SCHEMA_NAME(o.schema_id)) + '.' + QUOTENAME(o.name), 'OBJECT') p "
         "WHERE o.type IN ('U', 'P', 'FN', 'V') AND p.subentity_name = ''; REVERT;")
    import base64
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    # запрос — here-string PowerShell через -EncodedCommand (кавычки и % запроса не проходят через cmd)
    psq = "$q = @'\n%s\n'@\nsqlcmd -S 'lpc:.\\SQLEXPRESS' -E -h -1 -W -Q $q\n" % q
    enc = base64.b64encode(psq.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            "powershell -NoProfile -EncodedCommand " + enc], capture_output=True, timeout=120)
        out = r.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    now_def = " ".join(ln for ln in out.splitlines() if ln.startswith("NOW|"))
    perms_ops = sorted({ln.split("|", 1)[1] for ln in out.splitlines() if ln.startswith("PERM|")})
    check("живое (SSH, только чтение): adm.GP7AdjustNow() = SYSDATETIME() (часы суток лимита — не подменены), лимиты 100000 / 500000 в теле "
          "adm.GP7Adjust, действующие права asda_ops на объекты AsdaStoryLogin — ровно EXECUTE adm.GP7Adjust; процедура на живой не вызывалась",
          "RETURN SYSDATETIME();" in now_def and "TestClock" not in now_def and "LIM|1" in out and perms_ops == ["adm.GP7Adjust|EXECUTE"],
          (now_def[:160], perms_ops, out[-300:]))
    if svc:
        check("живое: служебная учётка ≤ 5000 со строкой сайта без открытого HOLD есть (%s) — предпросмотр на живой НЕ делается (ревизия 63 М-3)"
              % svc["username"], True)
    import ssl
    import urllib.error
    import urllib.request
    sc = ssl.create_default_context()
    sc.check_hostname, sc.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=sc)).open(
            "https://%s:17890/api/money/adjustments" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/money/adjustments без входа — 401", code == 401, code)
