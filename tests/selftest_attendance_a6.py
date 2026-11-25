# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_attendance_a6.py — самотест шага А6.10 «Посещаемость: сводка, засчитать и снять день» (23.11.2026; domains/attendance.py,
sql/adminc_25_attendance.sql, /api/attendance, web/attendance.js, операции attendance.credit / attendance.revoke, проверки adminc_10 / 11, откат adminc_99).

offline(check)      — права (attendance.view — owner, admin, gm; attendance.edit — owner, admin), операции с откатом без второго фактора, маршрут,
                      отказы ввода без базы (день, причина, ключ, служебная учётка не владельцу, учётка живого игрока при TEST_ONLY_MAX_UID), базы
                      нет — понятный отказ, тексты без «; », коды отказа процедуры = REASONS, переводы EN, веб (без innerHTML, раздел, маршрут,
                      переход из карточки, подписи EN, node --check), adminc_25 (батчи, QUOTED_IDENTIFIER отдельным батчем, только EXECUTE для
                      asda_ops), выкладка (-x -I после adminc_04), adminc_10 / 11 / 99.
sandbox(check, ldb) — СВОИ базы LocalDB: Joy1 (Arabic_CI_AS) со столбцами живых таблиц Attendance*, НАСТОЯЩИЕ процедуры сервера OP_Attendance /
                      OP_Attendance_Insert (копии живых определений Reports/joylog_missing/evidence/live_modules; живой блок сверяет их с
                      живой базой), adminc_25 дважды; служба пишет ПОД asda_ops (EXECUTE AS USER), журнал adm.audit — свой AsdaAdmin.
                      Засчитать / снять / откат, «сегодня» и будущее — отказ, после засчитывания прошлого дня сервер по-прежнему отвечает «можно»
                      (флаг 1), после штатной отметки сегодня — «уже было» и панель её не снимает, отпечаток счёта, повтор ключа, строка ушла —
                      откат отказ, права ролей, сводка, инвариант «счёт = дням».
live(check)         — живая dev: определения OP_Attendance / OP_Attendance_Insert = копиям стенда, adm.AttendanceAdjust и права asda_ops (по SSH,
                      EXECUTE AS USER), сводка = COUNT(*) живой; запись с откатом ТОЛЬКО служебной учётке 2 (слот 12): засчитать прошедший день
                      без отметки → снять его → откат снятия → откат засчитывания, после цикла строки и счёт как до него; служба на сервере (SSH)
                      видит ту же сводку; без входа — 401.
Побочных эффектов при импорте нет.
"""
import datetime
import os
import re
import secrets
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
STOCK = os.path.join(PORT, "Reports", "joylog_missing", "evidence", "live_modules")
CYR = re.compile("[А-Яа-яЁё]")
LIVE_UID, LIVE_IDX = 2, 12            # служебная учётка владельца (GM_MONSTER) — живая запись только ей
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


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


def _stock(name):
    """Текст живого определения процедуры (копия Reports/joylog_missing/evidence/live_modules) без строки-заголовка."""
    t = open(os.path.join(STOCK, "Joy1.dbo.%s.sql" % name), encoding="latin-1").read().replace("\r\n", "\n")
    return t.split("\n", 1)[1] if t.startswith("--") else t


def _norm(t):
    return re.sub(r"\s+", " ", t.replace("\r", "")).strip()


def _key():
    return str(uuid.uuid4())


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, db, i18n, ops
    import domains
    domains.load_all()
    from domains import attendance as A
    roles = ("owner", "admin", "gm", "support")
    check("посещаемость: attendance.view — owner, admin, gm; attendance.edit — owner, admin (gm только смотрит, решение владельца 23.11)",
          {r for r in roles if auth.can(r, "attendance.view")} == {"owner", "admin", "gm"}
          and {r for r in roles if auth.can(r, "attendance.edit")} == {"owner", "admin"})
    check("посещаемость: операции attendance.credit / attendance.revoke — право attendance.edit, с откатом, без второго фактора; откат — audit.undo",
          all(ops.REGISTRY[n].perm == "attendance.edit" and ops.REGISTRY[n].reversible and not ops.needs_two_factor(n)
              for n in ("attendance.credit", "attendance.revoke")) and A.KINDS == {"attendance.credit": 1, "attendance.revoke": -1})
    check("посещаемость (р73 М-1): attendance.undo_log — только owner, своя запись журнала, без своего отката; исключение «фиксация в apply» "
          "записано в шапке core/ops.py",
          {r for r in roles if auth.can(r, "attendance.undo_log")} == {"owner"} and ops.REGISTRY["attendance.undo_log"].perm == "attendance.undo_log"
          and not ops.REGISTRY["attendance.undo_log"].reversible and "ИСКЛЮЧЕНИЕ ИЗ «сначала журнал, потом фиксация»" in _read(ROOT, "core", "ops.py")
          and "«error» ядра" not in _read(ROOT, "domains", "attendance.py"))
    fn, perm = _route("/api/attendance")
    check("посещаемость: маршрут GET /api/attendance — право attendance.view", fn is not None and perm == "attendance.view", perm)
    owner = ops.Ctx(1, "owner_t", "owner", "", "web")
    admin = ops.Ctx(2, "admin_t", "admin", "", "web")
    k = _key()
    ok = {"uid": 2, "idx": 12, "day": "20261101", "reason": "пропуск из-за сбоя сервера", "req": k}
    bad = [dict(ok, uid="x"), dict(ok, uid=0), dict(ok, idx=256), dict(ok, idx="-1"), dict(ok, day="2026-11-01"), dict(ok, day="20261131"),
           dict(ok, day="0261101"), dict(ok, reason="abc"), dict(ok, reason="x" * 301), dict(ok, reason=None), dict(ok, req="nope"), dict(ok, req=None),
           dict(ok, uid=True)]
    why = [_refused(lambda p=p: A.plan(p, "owner")) for p in bad]
    why.append(_refused(lambda: A.plan(ok, "admin")))                                # служебная учётка — только владелец
    saved = A.TEST_ONLY_MAX_UID
    A.TEST_ONLY_MAX_UID = 5000
    try:
        why.append(_refused(lambda: A.plan(dict(ok, uid=9001), "owner")))            # самотест: живой игрок — отказ до базы
    finally:
        A.TEST_ONLY_MAX_UID = saved
    why += [_refused(lambda q=q: A.summary(q)) for q in ({"size": "0"}, {"size": "201"}, {"page": "x"}, {"from": "2026-11-01"},
                                                        {"from": "20261110", "to": "20261101"}, {"uid": "x", "idx": "1"}, {"uid": "5"},
                                                        {"account": "x" * 51}, {"char": "x" * 21})]
    check("посещаемость: отказы ввода без обращения к базе (%d: учётка, слот, день ГГГГММДД, причина 5…300, ключ UUID, служебная — не владельцу, "
          "живой игрок под TEST_ONLY_MAX_UID, страницы, даты, фильтры)" % len(why), all(why), [i for i, w in enumerate(why) if not w])
    check("посещаемость: служебная учётка — admin отказ, owner проходит проверку ввода",
          "только владелец" in (why[13] or "") and A.plan(ok, "owner")["day"] == "20261101" and A.plan(dict(ok, uid=9001), "admin")["uid"] == 9001)

    def nodb(database):
        raise db.DbError("нет подключения к %s: Login timeout expired" % database)
    db.set_override("game", nodb)
    db.set_override("ops", nodb)
    try:
        wn = [_refused(lambda: ops.REGISTRY["attendance.credit"].preview(owner, ok)), _refused(lambda: A.summary({"account": "boblogin"}))]
        sm = A.summary({})
    finally:
        db.set_override("game", None)
        db.set_override("ops", None)
    check("посещаемость: базы нет — отказ «… не прочитана/не найдена: нет подключения …» (409, не 500), сводка — строка ошибки",
          all(w and "нет подключения" in w for w in wn) and sm["errors"] and "нет подключения" in sm["errors"][0], (wn, sm["errors"]))
    why += wn + sm["errors"]
    texts = list(A.REASONS.values()) + [A.NOT_INSTALLED, A.LOCK_BUSY, A.FIRST_VISIT % "в мире слот 10",
                                             A.FIRST_VISIT % "учётка вошла в игру или на выбор персонажа: Flag 1, UserNum 3"]
    check("посещаемость: тексты отказов без «; »", all("; " not in x for x in why + texts if x), [x for x in why + texts if x and "; " in x])
    sql = _read(ROOT, "sql", "adminc_25_attendance.sql")
    codes = set(re.findall(r"SET @why = '([a-z-]+)'", sql)) | set(re.findall(r"THEN '([a-z-]+)'", sql)) | {"key-conflict", "busy"}
    check("посещаемость: коды отказа adm.AttendanceAdjust (%d) = ключам REASONS — у каждого понятный текст" % len(codes),
          codes == set(A.REASONS), sorted(codes ^ set(A.REASONS)))
    bs = _batches(sql)
    check("посещаемость adminc_25: QUOTED_IDENTIFIER ON — отдельным батчем до USE, процедура CREATE OR ALTER, нет таблиц — RAISERROR без изменений, "
          "asda_ops — только GRANT EXECUTE adm.AttendanceAdjust и DENY записи журнала, прямых прав на dbo.Attendance* нет, даты — стиль 112",
          any(b.strip() == "SET QUOTED_IDENTIFIER ON;" for b in bs) and sql.index("SET QUOTED_IDENTIFIER ON;") < sql.index("USE [Joy1]")
          and "CREATE OR ALTER PROCEDURE adm.AttendanceAdjust" in sql and "RAISERROR(N'adminc_25" in sql
          and re.findall(r"GRANT (\w+) ON ([\w.]+) TO \[asda_ops\]", sql) == [("EXECUTE", "adm.AttendanceAdjust")]
          and "DENY INSERT, UPDATE, DELETE ON adm.AttendanceAdjustLog TO [asda_ops]" in sql and not re.search(r"GRANT .* ON dbo\.Attendance", sql)
          and "ISDATE(@Day) = 1 THEN CONVERT(DATE, @Day, 112)" in sql and "TRY_" not in sql and "CAST(GETDATE() AS DATE)" in sql)
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    check("посещаемость: выкладка — adminc_25 с -x -I после adminc_04 (логин asda_ops) и до проверок прав",
          "Run 'adminc_25_attendance.sql' $null -xi" in dep and dep.index("Run 'adminc_04_ops.sql'") < dep.index("Run 'adminc_25_attendance.sql'")
          < dep.index("adminc_11_verify_ops.sql') 2>&1"))
    v10, v11, v99 = _read(ROOT, "sql", "adminc_10_verify.sql"), _read(ROOT, "sql", "adminc_11_verify_ops.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    check("посещаемость: adminc_11 — EXECUTE adm.AttendanceAdjust = 1 (если установлена), прежние «AttendanceDetail DELETE» / «AttendanceCount UPDATE» = 0, "
          "журнал без записи; счёт исполняемых Joy1 + 1 при установленной; adminc_10 — чтение журнала asda_admin; adminc_99 — DROP процедуры, журнал остаётся",
          "'ops.adm.AttendanceAdjust EXEC'" in v11 and "'ops.AttendanceDetail DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.AttendanceDetail','OBJECT','DELETE'), 0" in v11
          and "'ops.adm.AttendanceAdjustLog INSERT'" in v11
          and "9 + CASE WHEN OBJECT_ID(N'Joy1.adm.LoginMaintenanceSet', N'P') IS NULL THEN 0 ELSE 1 END + CASE WHEN OBJECT_ID(N'Joy1.adm.AttendanceAdjust', N'P') IS NULL THEN 0 ELSE 1 END" in v11
          and "'Joy1.adm.AttendanceAdjustLog SELECT'" in v10 and (v99 is None or "DROP PROCEDURE adm.AttendanceAdjust" in v99)
          and (v99 is None or "DROP TABLE adm.AttendanceAdjustLog" not in v99))
    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in why if x] + texts + [ops.REGISTRY[n].title for n in list(A.KINDS) + ["attendance.undo_log"]] + [
            "номер строки журнала отметок — целое от 1", "строки №5 в журнале отметок нет",
            "правка №5 есть в журнале действий — откат там (кнопка «Откатить» у её записи)",
            "откатить правку №5 (нет в журнале действий): снять день 2026-11-01 персонажу 2/12, отметок 3 → 2",
            "откатить правку №5 (нет в журнале действий): снова засчитать день 2026-11-01 персонажу 2/12, отметок 2 → 3",
            "правка №5 не попала в журнал действий (сбой записи журнала после сохранения) — откат по журналу отметок",
            "журнал действий не прочитан: запрос к AsdaAdmin: x", A.REASONS["busy"], A.REASONS["count-ambiguous"],
            "засчитать день 2026-11-01 персонажу Кирилл (учётка 2, слот 12): отметок 3 → 4",
            "снять день 2026-11-01 у персонажа Кирилл (учётка 2, слот 12): отметок 4 → 3",
            "правка видна сразу и при игроке в игре: сервер не держит посещаемость в памяти, а спрашивает базу при каждом визите к NPC",
            "награда за этот день (предмет 68788) не выдаётся — засчитывается только отметка",
            "строка дня №168074 от 2026-06-19 10:40:58 удаляется (вернуть — откатом)", "предмет 68788, выданный за этот день, остаётся у игрока",
            "сегодня (2026-11-23) награда уже получена", "сегодня (2026-11-23) награда ещё не получена", "служебная учётка 1…5000",
            "засчитан день 2026-11-01 персонажу 2/12: отметок 3 → 4 (правка №7)", "снят день 2026-11-01 персонажу 2/12: отметок 4 → 3 (правка №8)",
            "откат правки №7: снят день 2026-11-01 персонажу 2/12, отметок 4 → 3 (правка №9)",
            "откат правки №8: снова засчитан день 2026-11-01 персонажу 2/12, отметок 3 → 4 (правка №10)",
            "запрос уже выполнен: правка №7 — повтор ничего не пишет", "нет отпечатка предпросмотра (счёт) — повторите предпросмотр",
            "персонажа 2/12 нет", "учётки «boblogin» нет", "период — не больше 3660 суток",
            "после записи строки правки №7 в журнале ручных отметок нет или она другая", "в журнале нет данных для отката",
            "правки №7 нет в журнале ручных отметок (запись не зафиксирована) — откатывать нечего",
            "процедуры adm.AttendanceAdjust нет (sql/adminc_25_attendance.sql не установлен)", "процедура посещаемости отказала: x",
            "посещаемость не записана: запись в Joy1: x", "откат не записан: запись в Joy1: x", "логины учёток не прочитаны: запрос к AsdaStoryOp: x"]
        miss = [(x, i18n.tr(x)) for x in ru if CYR.search(i18n.tr(x).replace("Кирилл", ""))]
        check("посещаемость EN: отказы, предпросмотры, итоги и предупреждения — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("посещаемость: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "attendance.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("посещаемость веб: раздел #/attendance с правом attendance.view, маршрут viewAttendance(my, q), скрипт после acjournal.js; из карточки персонажа — "
          "переход «Посещаемость персонажа» (uid, idx)",
          '["#/attendance", "Посещаемость", "attendance.view"' in app and 'case "attendance": return viewAttendance(my, q);' in app
          and 0 < idx.index("/acjournal.js") < idx.index("/attendance.js") and '"#/attendance?uid=" + base.uid + "&idx=" + base.idx' in app
          and 'can("attendance.view")' in app)
    check("посещаемость веб: без innerHTML, данные — текстовыми узлами (acText / acTable), без T() над данными; действия — причина → предпросмотр → "
          "подтверждение → запись с expect и тем же ключом; «Снять день» — только прошедший (x.past) и Step 2; служебные — только владельцу",
          "innerHTML" not in js and "expect: pv.expect" in js and "req: atReq()" in js and "x.past && x.step === 2 && edit(x)" in js
          and '(!x.service || r.role === "owner")' in js and "T(x.name" not in js and "T(x.reason" not in js and "T(x.mark" not in js)
    labels = set(re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|div|a)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) | set(re.findall(r'\["([^"\]]+)", [a-z]+ =>', js)) \
        | set(re.findall(r'T\("([^"]+)"', js)) | set(re.findall(r'placeholder: "([^"]+)"', js)) | set(re.findall(r'\}, "([^"]+)"\)', js)) \
        | {"Посещаемость", "Посещаемость персонажа", "Здесь только показ. Засчитать или снять прошедший день — раздел «Посещаемость» (сегодняшний день не правится: снятая отметка дала бы вторую награду)."}
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("посещаемость веб EN: у подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack, lack[:8])
    keys = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А6.10 (23.11): «Посещаемость»"):]
    dup = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys.count(x) > 1})
    check("посещаемость веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("attendance.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("посещаемость: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("посещаемость: node --check web/%s (node не запустился)" % f, False, str(ex))
    code = _read(ROOT, "domains", "attendance.py")
    body = code.split('"""', 2)[2]
    check("посещаемость: запись — только EXEC adm.AttendanceAdjust логином asda_ops (в SQL домена нет INSERT / UPDATE / DELETE); импорт без побочных "
          "эффектов (верхний уровень — константы, функции, классы)",
          sorted(set(re.findall(r"EXEC (adm\.\w+)", body))) == ["adm.AttendanceAdjust"] and not re.search(r"\b(INSERT|UPDATE|DELETE)\s+(INTO\s+)?(dbo|adm)\.", body)
          and not re.search(r"^(?!def |class |@|import |from |[A-Z_]+ = |[A-Z_]+, [A-Z_]+ = |    |\)|\}|#|\"|$)", body, re.M))


def _setup(ldb, names):
    """Стенд: Joy1 (Arabic_CI_AS) со столбцами живых таблиц, НАСТОЯЩИЕ OP_Attendance / OP_Attendance_Insert, adminc_25 дважды; AsdaStoryOp, AsdaAdmin."""
    mst = ldb("master")
    mst.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names["J"])
    mst.cursor().execute("ALTER DATABASE [%s] SET COMPATIBILITY_LEVEL = 100" % names["J"])     # как живая Joy1 (23.11: 100 — нет TRY_CONVERT и пр.)
    mst.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names["O"])
    mst.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % names["A"])
    a = ldb(names["A"])
    for b in _batches(_read(ROOT, "sql", "adminc_02_schema.sql")):
        a.cursor().execute(b)
    jc = ldb(names["J"]).cursor()
    jc.execute("CREATE TABLE dbo.Charinfo (Userindex INT NOT NULL, Charidx TINYINT NOT NULL, Charname VARCHAR(20) NOT NULL)")
    jc.execute("CREATE TABLE dbo.AttendanceCount (ACNo INT IDENTITY(1,1) NOT NULL, Userindex INT NOT NULL, Charidx TINYINT NOT NULL, "
               "ACount INT NOT NULL CONSTRAINT DF_AttendanceCount_ACount DEFAULT ((0)), Step TINYINT NOT NULL CONSTRAINT DF_AttendanceCount_Step DEFAULT ((1)), "
               "RegistDay DATETIME NOT NULL CONSTRAINT DF_AttendanceCount_RegistDay DEFAULT (getdate()), Note VARCHAR(50) NULL)")
    jc.execute("CREATE TABLE dbo.AttendanceDetail (ADNo INT IDENTITY(168074,1) NOT NULL, Userindex INT NOT NULL, Charidx TINYINT NOT NULL, "
               "Step TINYINT NOT NULL CONSTRAINT DF_AttendanceDetail_Step DEFAULT ((1)), RegistDay DATETIME NOT NULL CONSTRAINT DF_AttendanceDetail_RegistDay DEFAULT (getdate()), "
               "Note VARCHAR(50) NULL)")
    for n in ("OP_Attendance", "OP_Attendance_Insert"):
        jc.execute(_stock(n))
    jc.execute("CREATE USER asda_ops WITHOUT LOGIN")
    jc.execute("DENY EXECUTE ON SCHEMA::dbo TO asda_ops")                          # как adminc_04_ops.sql
    jc.execute("DENY INSERT, UPDATE, DELETE ON SCHEMA::dbo TO asda_ops")
    jc.execute("GRANT SELECT ON SCHEMA::dbo TO asda_ops")
    sql = _read(ROOT, "sql", "adminc_25_attendance.sql").replace("USE [Joy1];", "USE [%s];" % names["J"])
    for _ in range(2):
        for b in _batches(sql):
            jc.execute(b)
    oc = ldb(names["O"]).cursor()
    oc.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(20), Flag TINYINT NOT NULL DEFAULT 0, UserNum SMALLINT NOT NULL DEFAULT -1)")
    for u, lg in ((1, "owner1"), (2, "owner2"), (9001, "boblogin")):
        oc.execute("INSERT dbo.Us_member (Userindex, Us_id) VALUES (?, ?)", (u, lg))
    jc.execute("CREATE TABLE dbo.CharPos (Userindex INT NOT NULL, Charidx TINYINT NOT NULL, UserNum SMALLINT NOT NULL DEFAULT -1)")
    for u, i, nm in ((1, 10, "GM_sitx"), (2, 12, "GM_MONSTER"), (2, 11, "ADM_x"), (9001, 10, "Bob"), (1, 11, "Slot11"), (1, 12, "Slot12")):
        jc.execute("INSERT dbo.Charinfo VALUES (?, ?, ?)", (u, i, nm))
        jc.execute("INSERT dbo.CharPos (Userindex, Charidx) VALUES (?, ?)", (u, i))
    return jc


def sandbox(check, ldb):
    """Свои базы LocalDB (см. шапку модуля)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import audit, db, ops
    import domains
    domains.load_all()
    from domains import attendance as A
    tag = secrets.token_hex(3)
    names = {"J": "AsdaAtJ_" + tag, "O": "AsdaAtO_" + tag, "A": "AsdaAtA_" + tag}
    saved = A.TEST_ONLY_MAX_UID
    try:
        jc = _setup(ldb, names)

        class _Imp:
            """Связь «под asda_ops» (EXECUTE AS USER): перед закрытием — REVERT."""

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
        mp = {"Joy1": names["J"], "AsdaStoryOp": names["O"]}

        def ops_cn(database):
            cn = ldb(mp.get(database, database))
            cn.cursor().execute("EXECUTE AS USER = 'asda_ops'")
            return _Imp(cn)
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("ops", ops_cn)
        db.set_override("admin", lambda database: ldb(names["A"]))
        A.TEST_ONLY_MAX_UID = 5000
        try:
            _checks(check, A, ops, audit, jc)
        finally:
            db.set_override("game", None)
            db.set_override("ops", None)
            db.set_override("admin", None)
    finally:
        A.TEST_ONLY_MAX_UID = saved
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def _checks(check, A, ops, audit, jc):
    owner = ops.Ctx(None, "owner1", "owner", "127.0.0.1", "test")
    admin = ops.Ctx(None, "admin2", "admin", "127.0.0.1", "test")
    gm = ops.Ctx(None, "gm3", "gm", "127.0.0.1", "test")
    today = datetime.date.fromisoformat(jc.execute("SELECT CONVERT(char(10), GETDATE(), 23)").fetchone()[0])
    d8 = lambda n: (today - datetime.timedelta(days=n)).strftime("%Y%m%d")   # noqa: E731

    def cnt(u, i):
        r = jc.execute("SELECT COUNT(*), MIN(ACount), MIN(ACNo) FROM dbo.AttendanceCount WHERE Userindex = ? AND Charidx = ? AND Step = 2", (u, i)).fetchone()
        return int(r[0]), r[1], r[2]

    def days(u, i):
        return [(r[0], r[1], r[2]) for r in jc.execute("SELECT CONVERT(char(8), RegistDay, 112), CONVERT(varchar(23), RegistDay, 121), Note FROM dbo.AttendanceDetail "
                                                       "WHERE Userindex = ? AND Charidx = ? AND Step = 2 ORDER BY RegistDay", (u, i)).fetchall()]

    def flag(proc, u, i):
        return int(jc.execute("EXEC dbo.%s ?, ?" % proc, (u, i)).fetchone()[0])

    def run(ctx, name, u, i, day, reason="пропуск из-за сбоя сервера", req=None, dry=False, expect=None):
        p = {"uid": u, "idx": i, "day": day, "reason": reason, "req": req or _key()}
        if expect is not None:
            p["expect"] = expect
        return ops.run(ctx, name, p, dry=dry)

    def refused(fn):
        try:
            fn()
        except ops.OpRefused as ex:
            return str(ex)
        return None
    perms = {r[0]: r[1] for r in jc.execute(
        "EXECUTE AS USER = 'asda_ops'; SELECT 'exec', HAS_PERMS_BY_NAME('adm.AttendanceAdjust','OBJECT','EXECUTE') UNION ALL "
        "SELECT 'stock', HAS_PERMS_BY_NAME('dbo.OP_Attendance_Insert','OBJECT','EXECUTE') UNION ALL "
        "SELECT 'ins_d', HAS_PERMS_BY_NAME('dbo.AttendanceDetail','OBJECT','INSERT') UNION ALL "
        "SELECT 'del_d', HAS_PERMS_BY_NAME('dbo.AttendanceDetail','OBJECT','DELETE') UNION ALL "
        "SELECT 'upd_c', HAS_PERMS_BY_NAME('dbo.AttendanceCount','OBJECT','UPDATE') UNION ALL "
        "SELECT 'ins_log', HAS_PERMS_BY_NAME('adm.AttendanceAdjustLog','OBJECT','INSERT'); REVERT;").fetchall()}
    direct = None
    try:
        jc.execute("EXECUTE AS USER = 'asda_ops'; DELETE FROM dbo.AttendanceDetail WHERE 1 = 0;")
        direct = "прошло"
    except Exception as ex:
        direct = str(ex)[:80]
    finally:
        try:
            jc.execute("REVERT")
        except Exception:
            pass
    check("посещаемость стенд: НАСТОЯЩИЕ OP_Attendance / OP_Attendance_Insert и adminc_25 дважды; asda_ops — EXEC adm.AttendanceAdjust да, процедуры "
          "сервера и прямая запись в Attendance* и журнал — нет (прямой DELETE — отказ сервера)",
          perms == {"exec": 1, "stock": 0, "ins_d": 0, "del_d": 0, "upd_c": 0, "ins_log": 0} and direct != "прошло", (perms, direct))
    # засев: персонаж 1/10 — три прошлых дня, как пишет сервер (счёт = 3); 2/12 — ничего
    for n in (40, 20, 10):
        jc.execute("INSERT dbo.AttendanceDetail (Userindex, Charidx, Step, RegistDay) VALUES (1, 10, 2, DATEADD(DAY, -?, DATEADD(HOUR, 13, CAST(CAST(GETDATE() AS DATE) AS DATETIME))))", (n,))
    jc.execute("INSERT dbo.AttendanceCount (Userindex, Charidx, ACount, Step) VALUES (1, 10, 3, 2)")
    before_1 = days(1, 10)
    # ---- засчитать прошедший день персонажу без счёта
    pv = run(owner, "attendance.credit", 2, 12, d8(3), dry=True)["preview"]
    check("посещаемость стенд: предпросмотр «засчитать» — отметок 0 → 1, предупреждения «награда не выдаётся», «видна и в игре», «сегодня ещё не получена», "
          "служебная; ничего не записано", pv["count_before"] == 0 and pv["count_after"] == 1 and pv["expect"] == {"count": 0}
          and any("не выдаётся" in w for w in pv["warnings"]) and any("при игроке в игре" in w for w in pv["warnings"])
          and any("ещё не получена" in w for w in pv["warnings"]) and cnt(2, 12)[0] == 0 and days(2, 12) == [], pv)
    k1 = _key()
    r1 = run(owner, "attendance.credit", 2, 12, d8(3), req=k1, expect={"count": 0})
    c1, d1 = cnt(2, 12), days(2, 12)
    lid1 = r1["result"]["log_id"]
    check("посещаемость стенд: засчитан прошедший день — строка счёта создана (ACount 1, Step 2, как OP_Attendance_Insert), строка дня Step 2 на 00:00 "
          "с отметкой «adm #N», запись журнала панели и журнала ручных отметок",
          c1[0] == 1 and c1[1] == 1 and d1 == [(d8(3), d1[0][1], "adm #%d" % lid1)] and d1[0][1].endswith("00:00:00.000")
          and r1["audit_id"] and audit.get(r1["audit_id"])["action"] == "attendance.credit", (c1, d1, r1))
    check("посещаемость стенд: после засчитывания ПРОШЛОГО дня сервер по-прежнему отвечает «можно» (OP_Attendance = 1) — сегодняшняя награда не отнята",
          flag("OP_Attendance", 2, 12) == 1)
    rep = refused(lambda: run(owner, "attendance.credit", 2, 12, d8(3), req=k1, expect={"count": 0}))
    again = refused(lambda: run(owner, "attendance.credit", 2, 12, d8(3), expect={"count": 1}))
    check("посещаемость стенд: повтор того же ключа — «запрос уже выполнен», ничего не пишет; тот же день новым запросом — «уже засчитан»",
          rep and "уже выполнен" in rep and again == "этот день уже засчитан" and cnt(2, 12)[1] == 1 and len(days(2, 12)) == 1, (rep, again))
    # ---- сегодня, будущее, старше 365 — отказ процедуры (и при откате тоже)
    w = [refused(lambda: run(owner, "attendance.credit", 2, 12, today.strftime("%Y%m%d"))), refused(lambda: run(owner, "attendance.revoke", 2, 12, today.strftime("%Y%m%d"))),
         refused(lambda: run(owner, "attendance.credit", 2, 12, d8(-1))), refused(lambda: run(owner, "attendance.credit", 2, 12, d8(366)))]
    check("посещаемость стенд: сегодняшний и будущий день — отказ в обе стороны, старше 365 суток — отказ", w[0] == w[1] == w[2] == A.REASONS["not-past"]
          and w[3] == A.REASONS["too-old"], w)
    # ---- штатная отметка сегодня → «уже было» и панель её не снимает (вторая награда невозможна)
    f_ins = flag("OP_Attendance_Insert", 1, 10)
    f_after = flag("OP_Attendance", 1, 10)
    rv_today = refused(lambda: run(owner, "attendance.revoke", 1, 10, today.strftime("%Y%m%d")))
    s1 = A.summary({"uid": "1", "idx": "10"})
    ch1 = s1["chars"][0] if s1["chars"] else {}
    check("посещаемость стенд: штатный визит сегодня (OP_Attendance_Insert = 1, затем OP_Attendance = 2), сводка — «сегодня уже получено», счёт 4 = дням; "
          "снять сегодняшний день — отказ", f_ins == 1 and f_after == 2 and rv_today == A.REASONS["not-past"] and ch1.get("today_got") is True
          and ch1.get("count") == 4 and ch1.get("days_total") == 4 and ch1.get("mismatch") is False, (f_ins, f_after, ch1))
    # ---- снять прошедший день (строка сервера) и откат: строка вернулась с прежними RegistDay и Note
    pv2 = run(owner, "attendance.revoke", 1, 10, d8(20), dry=True)["preview"]
    r2 = run(owner, "attendance.revoke", 1, 10, d8(20), expect=pv2["expect"])
    c2, dd2 = cnt(1, 10), days(1, 10)
    check("посещаемость стенд: снят прошедший день — строка дня удалена, ACount 4 → 3, предупреждение «предмет остаётся»",
          pv2["count_before"] == 4 and pv2["count_after"] == 3 and any("остаётся у игрока" in w for w in pv2["warnings"])
          and c2[1] == 3 and d8(20) not in [x[0] for x in dd2] and len(dd2) == 3, (pv2, c2, dd2))
    u2 = ops.undo(owner, r2["audit_id"])
    dd2b = days(1, 10)
    check("посещаемость стенд: откат снятия — строка дня с прежними RegistDay и Note (NULL у строки сервера) и ACount 3 → 4; повторный откат — отказ",
          cnt(1, 10)[1] == 4 and [x for x in dd2b if x[0] == d8(20)] == [x for x in before_1 if x[0] == d8(20)]
          and refused(lambda: ops.undo(owner, r2["audit_id"])) is not None and u2["ok"], (dd2b, before_1))
    # ---- откат засчитывания: строка дня и созданная строка счёта удалены — как было
    u1 = ops.undo(owner, r1["audit_id"])
    check("посещаемость стенд: откат засчитывания — строка дня удалена, созданная им строка счёта тоже (как до правки: ни счёта, ни дней)",
          u1["ok"] and cnt(2, 12)[0] == 0 and days(2, 12) == [], (cnt(2, 12), days(2, 12)))
    # ---- строка ушла: засчитать → снять ту же строку → откат засчитывания — отказ
    r3 = run(owner, "attendance.credit", 2, 12, d8(5), expect={"count": 0})
    r4 = run(owner, "attendance.revoke", 2, 12, d8(5), expect={"count": 1})
    gone = refused(lambda: ops.undo(owner, r3["audit_id"]))
    ops.undo(owner, r4["audit_id"])
    ops.undo(owner, r3["audit_id"])
    check("посещаемость стенд: засчитанную строку сняли позже — откат засчитывания «строки уже нет»; откат снятия, затем засчитывания — снова как было",
          gone and "строки дня уже нет" in gone and cnt(2, 12)[0] == 0 and days(2, 12) == [], (gone, cnt(2, 12), days(2, 12)))
    # ---- отпечаток счёта: изменился между предпросмотром и записью
    pv5 = run(owner, "attendance.credit", 2, 11, d8(2), dry=True)["preview"]
    jc.execute("EXEC dbo.OP_Attendance_Insert 2, 11")                                 # сервер отметил сегодня — счёт 0 → 1
    ch5 = refused(lambda: run(owner, "attendance.credit", 2, 11, d8(2), expect=pv5["expect"]))
    nolive = refused(lambda: ops.REGISTRY["attendance.credit"].apply(ops.Ctx(None, "o", "owner", "", "web"),
                                                                     {"uid": 2, "idx": 11, "day": d8(2), "reason": "пропуск дня", "req": _key()}, pv5))
    check("посещаемость стенд: счёт изменился с предпросмотра — отказ «повторите предпросмотр»; из браузера без отпечатка — отказ",
          ch5 == A.REASONS["count-changed"] and nolive and "отпечатка" in nolive and cnt(2, 11)[1] == 1, (ch5, nolive))
    # ---- права ролей и живой игрок
    rr = [refused(lambda: run(admin, "attendance.credit", 2, 12, d8(3))), refused(lambda: run(gm, "attendance.credit", 9001, 10, d8(3))),
          refused(lambda: run(owner, "attendance.credit", 9001, 10, d8(3))), refused(lambda: run(admin, "attendance.credit", 9001, 10, d8(3)))]
    check("посещаемость стенд: служебная учётка — admin отказ; gm — «нет права»; живой игрок 9001 под TEST_ONLY_MAX_UID — отказ до базы (owner и admin)",
          "только владелец" in (rr[0] or "") and "нет права" in (rr[1] or "") and all("самотест" in (x or "") for x in rr[2:])
          and days(9001, 10) == [], rr)
    # ---- сводка
    s = A.summary({"test": "1"})
    s_def = A.summary({})
    s_acc = A.summary({"account": "owner2"})
    s_name = A.summary({"char": "GM_sitx", "from": d8(45), "to": today.strftime("%Y%m%d")})
    adj = s["adjustments"]
    check("посещаемость стенд: сводка без фильтра — персонажи с отметками (1/10, 2/11), фильтр по логину и по имени; история за период — строки со "
          "«сегодня» (past = False); журнал ручных отметок — правки и откаты со ссылками",
          sorted((c["uid"], c["idx"]) for c in s["chars"]) == [(1, 10), (2, 11)] and {c["uid"] for c in s_acc["chars"]} == {2}
          and [c["name"] for c in s_name["chars"]] == ["GM_sitx"] and s_name["history"]["total"] == 4
          and [x["past"] for x in s_name["history"]["rows"]][0] is False and s["installed"] and len(adj) >= 8
          and any(a["undo_of"] for a in adj) and any(a["undone_by"] for a in adj) and not s["errors"], (s["chars"], s_name["history"], s["errors"]))
    check("посещаемость стенд (р73 К-3): записи самотеста (via test) отсекает сервер — без test=1 их нет, счётчик adjustments_test = всем таким строкам "
          "журнала; у каждой правки отмечено, есть ли запись «ok» в журнале действий",
          s_def["adjustments"] == [] and s_def["adjustments_test"] == len(adj) == s["adjustments_test"] and all(a["in_audit"] is True for a in adj),
          (s_def["adjustments_test"], len(adj), [a.get("in_audit") for a in adj]))
    # ---- ★ ревизия 72 М-1: замок — по персонажу (sp_getapplock), фиксация сразу после процедуры: сканирующий UPDATE стока другого игрока не ждёт
    jc.execute("INSERT dbo.AttendanceDetail (Userindex, Charidx, Step, RegistDay) VALUES (1, 11, 2, DATEADD(DAY, -9, GETDATE()))")
    jc.execute("INSERT dbo.AttendanceCount (Userindex, Charidx, ACount, Step) VALUES (1, 11, 1, 2)")
    op = ops.REGISTRY["attendance.credit"]
    p7 = {"uid": 2, "idx": 11, "day": d8(7), "reason": "проверка замка", "req": _key()}
    prev7 = op.preview(owner, p7)
    res7 = op.apply(owner, dict(p7, expect=prev7["expect"]), prev7)          # журнал панели ещё не писался (как между apply и _finish)
    blocked = None
    try:
        f11 = int(jc.execute("SET LOCK_TIMEOUT 1000; EXEC dbo.OP_Attendance_Insert 1, 11").fetchone()[0])
    except Exception as ex:
        f11, blocked = None, str(ex)[:120]
    jc.execute("SET LOCK_TIMEOUT -1")
    check("посещаемость стенд (р72 М-1): после apply и ДО журнала панели правка уже зафиксирована (нет _commit), штатный визит другого персонажа "
          "(UPDATE счёта сканом heap) проходит без ожидания (LOCK_TIMEOUT 1 с)", "_commit" not in res7 and f11 == 1 and blocked is None
          and cnt(1, 11)[1] == 2 and cnt(2, 11)[1] == 2, (res7.get("after"), f11, blocked))
    from core import db
    w2 = db.GameWriter("joy1")
    try:
        got = w2.rows("DECLARE @r INT; EXEC @r = sp_getapplock @Resource = N'adm.att:2/11', @LockMode = 'Exclusive', @LockOwner = 'Transaction'; SELECT @r AS r")
        bz = refused(lambda: op.preview(owner, {"uid": 2, "idx": 11, "day": d8(8), "reason": "проверка замка", "req": _key()}))
        other = refused(lambda: op.preview(owner, {"uid": 1, "idx": 11, "day": d8(8), "reason": "проверка замка", "req": _key()}))
    finally:
        w2.close()
    check("посещаемость стенд (р72 М-1): правку того же персонажа держит другой оператор (замок adm.att:2/11) — через 5 с отказ «правит другой "
          "оператор»; другого персонажа — без ожидания", got and int(got[0]["r"]) >= 0 and bz == A.REASONS["busy"] and other is None, (got, bz, other))
    # ---- ★ ревизия 72 М-2: персонаж в игре и без строки счёта — засчитать нельзя (предел стока); со строкой счёта — можно; вышел — можно
    jc.execute("UPDATE dbo.CharPos SET UserNum = 7 WHERE Userindex = 1 AND Charidx = 12")
    fv = refused(lambda: run(owner, "attendance.credit", 1, 12, d8(4), dry=True))
    ok10 = refused(lambda: run(owner, "attendance.credit", 1, 10, d8(8), dry=True))
    jc.execute("UPDATE dbo.CharPos SET UserNum = -1 WHERE Userindex = 1 AND Charidx = 12")
    ok12 = refused(lambda: run(owner, "attendance.credit", 1, 12, d8(4), dry=True))
    check("посещаемость стенд (р72 М-2): персонаж в игре без строки счёта — отказ «засчитайте, когда игрок выйдет», со строкой счёта — можно, "
          "вышел — можно (кика нет)", (fv or "").startswith("персонаж в игре (в мире слот 12)") and "войдёт и выйдет" in fv and ok10 is None and ok12 is None, (fv, ok10, ok12))
    # ---- ★ ревизия 73 М-1: журнал действий падает ПОСЛЕ фиксации — правка есть, записи adm.audit нет; откат — attendance.undo_log (владелец)
    real_write = audit.write

    def bad_write(ctx, action, *a, **kw):
        if action == "attendance.credit" and kw.get("result", "ok") == "ok":
            raise RuntimeError("AsdaAdmin недоступна (самотест)")
        return real_write(ctx, action, *a, **kw)
    audit.write = bad_write
    crash = None
    try:
        run(owner, "attendance.credit", 2, 12, d8(6), expect={"count": 0})
    except Exception as ex:
        crash = str(ex)
    finally:
        audit.write = real_write
    lost = jc.execute("SELECT TOP (1) id FROM adm.AttendanceAdjustLog WHERE userindex = 2 AND charidx = 12 AND day = CONVERT(date, ?, 112) AND delta = 1 "
                      "ORDER BY id DESC", (d8(6),)).fetchone()
    lid = int(lost[0]) if lost else None
    sm = A.summary({"uid": "2", "idx": "12", "test": "1"})
    mark = next((a for a in sm["adjustments"] if a["id"] == lid), {})
    check("посещаемость стенд (р73 М-1): сбой журнала действий после фиксации — оператор получает ошибку, правка в Joy1 есть (строка дня и счёт 1), "
          "в разделе строка помечена «нет в журнале действий» (in_audit = False)", crash and "AsdaAdmin" in crash and lid and cnt(2, 12)[1] == 1
          and len(days(2, 12)) == 1 and mark.get("in_audit") is False, (crash, lid, mark))
    adm_ul = refused(lambda: ops.run(admin, "attendance.undo_log", {"log_id": lid, "reason": "откат после сбоя журнала", "req": _key()}, dry=True))
    pvu = ops.run(owner, "attendance.undo_log", {"log_id": lid, "reason": "откат после сбоя журнала", "req": _key()}, dry=True)["preview"]
    ku = _key()
    ru = ops.run(owner, "attendance.undo_log", {"log_id": lid, "reason": "откат после сбоя журнала", "req": ku, "expect": pvu["expect"]})
    again_ul = refused(lambda: ops.run(owner, "attendance.undo_log", {"log_id": lid, "reason": "откат после сбоя журнала", "req": _key()}, dry=True))
    audited = refused(lambda: ops.run(owner, "attendance.undo_log", {"log_id": ru["result"]["log_id"], "reason": "откат отката", "req": _key()}, dry=True))
    rok = run(owner, "attendance.credit", 1, 11, d8(12), expect={"count": cnt(1, 11)[1]})
    first_ok = next((a for a in A.summary({"test": "1"})["adjustments"] if a["id"] == rok["result"]["log_id"]), {})
    on_audited = refused(lambda: ops.run(owner, "attendance.undo_log", {"log_id": rok["result"]["log_id"], "reason": "откат правки из журнала", "req": _key()}, dry=True))
    ops.undo(owner, rok["audit_id"])
    check("посещаемость стенд (р73 М-1): attendance.undo_log — admin «нет права»; owner откатывает по номеру строки журнала отметок (строки дня и "
          "созданной строки счёта нет, как до правки), своя запись «ok» в журнале действий; повтор — «уже откачена»; откат отката и правка, которая "
          "есть в журнале действий, — отказ",
          "нет права" in (adm_ul or "") and ru["ok"] and cnt(2, 12)[0] == 0 and days(2, 12) == [] and ru["audit_id"]
          and audit.get(ru["audit_id"])["action"] == "attendance.undo_log" and again_ul == A.REASONS["undo-repeat"]
          and audited == A.REASONS["undo-is-undo"] and first_ok.get("in_audit") is True and on_audited and "есть в журнале действий" in on_audited,
          (adm_ul, ru.get("message"), again_ul, audited, on_audited))
    inv = jc.execute("SELECT COUNT(*) FROM dbo.AttendanceCount c WHERE c.ACount <> (SELECT COUNT(*) FROM dbo.AttendanceDetail d WHERE d.Userindex = c.Userindex "
                     "AND d.Charidx = c.Charidx AND d.Step = 2)").fetchone()[0]
    check("посещаемость стенд: после всех правок и откатов у каждого персонажа счёт = числу строк дней (как на живой dev 23.11)", int(inv) == 0, inv)


def _ssh_sql(q):
    """Запрос под Windows-входом Administrator (sysadmin) по SSH, только чтение; вывод — строки «A|B|…»."""
    from core import config
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    ps = "$q = @'\n%s\n'@\nsqlcmd -S 'lpc:.\\SQLEXPRESS' -E -x -I -h -1 -W -s '|' -Q $q\n" % q
    import base64
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    try:
        r = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            "powershell -NoProfile -EncodedCommand " + enc], capture_output=True, timeout=180)
        return (r.stdout + r.stderr).decode("cp866", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        return "ssh: %s" % ex


def live(check):
    """Живая dev (см. шапку модуля): чтение + цикл записи с откатом только служебной учётке LIVE_UID/LIVE_IDX."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import attendance as A
    if config.get().on_server:
        return check("живой самотест А6.10 «посещаемость» — с ПК", True)
    # 1. определения процедур сервера = копиям стенда (стенд гонял ровно их); процедура панели и права asda_ops
    out = _ssh_sql("SET NOCOUNT ON; USE Joy1; SELECT 'DEF|' + o.name + '|' + CONVERT(varchar(32), HASHBYTES('MD5', CAST(REPLACE(REPLACE(REPLACE(REPLACE(m.definition, CHAR(13), ''), CHAR(10), ''), CHAR(9), ''), ' ', '') AS VARCHAR(MAX))), 2) "
                   "FROM sys.sql_modules m JOIN sys.objects o ON o.object_id = m.object_id WHERE o.name IN ('OP_Attendance', 'OP_Attendance_Insert'); "
                   "EXECUTE AS USER = 'asda_ops'; SELECT 'PERM|' + CAST(ISNULL(HAS_PERMS_BY_NAME('adm.AttendanceAdjust','OBJECT','EXECUTE'), -1) AS varchar) + '|' + "
                   "CAST(HAS_PERMS_BY_NAME('dbo.AttendanceDetail','OBJECT','DELETE') AS varchar) + '|' + CAST(HAS_PERMS_BY_NAME('dbo.AttendanceCount','OBJECT','UPDATE') AS varchar) "
                   "+ '|' + CAST(ISNULL(HAS_PERMS_BY_NAME('adm.AttendanceAdjustLog','OBJECT','INSERT'), -1) AS varchar); REVERT;")
    import hashlib
    want = {}
    for n in ("OP_Attendance", "OP_Attendance_Insert"):
        t = re.sub(r"[\r\n\t ]", "", _stock(n))
        want[n] = hashlib.md5(t.encode("latin-1")).hexdigest().upper()
    got = dict(re.findall(r"DEF\|(\w+)\|([0-9A-F]{32})", out))
    check("живое (SSH): определения OP_Attendance / OP_Attendance_Insert на сервере = копиям, которые гонял стенд (md5 без пробелов)",
          got == want, (got, want, out[-300:]))
    m = re.search(r"PERM\|(-?\d)\|(\d)\|(\d)\|(-?\d)", out)
    check("живое (SSH, EXECUTE AS USER asda_ops): EXECUTE adm.AttendanceAdjust = 1, прямой DELETE Detail / UPDATE Count = 0, запись журнала = 0",
          bool(m) and m.groups() == ("1", "0", "0", "0"), out[-300:])
    # 2. сводка = живой COUNT(*)
    s = A.summary({"from": "20200101", "to": datetime.date.today().strftime("%Y%m%d"), "size": "200"})
    with db.GameReader("joy1") as r:
        n_det = int(r.one("SELECT COUNT(*) AS n FROM dbo.AttendanceDetail d JOIN dbo.Charinfo c ON c.Userindex = d.Userindex AND c.Charidx = d.Charidx "
                          "WHERE d.RegistDay >= '20200101' AND d.RegistDay < DATEADD(DAY, 1, CAST(CAST(GETDATE() AS DATE) AS DATETIME))")["n"])
        n_cnt = int(r.one("SELECT COUNT(*) AS n FROM dbo.AttendanceCount")["n"])
        mis = int(r.one("SELECT COUNT(*) AS n FROM dbo.AttendanceCount c WHERE c.ACount <> (SELECT COUNT(*) FROM dbo.AttendanceDetail d WHERE "
                        "d.Userindex = c.Userindex AND d.Charidx = c.Charidx AND d.Step = 2)")["n"])
    check("живое: сводка — строк дней = COUNT(*) живой (%d), персонажей со счётом ≥ строк счёта (%d), расхождений «счёт ≠ дням» = живой (%d)" % (n_det, n_cnt, mis),
          s["history"]["total"] == n_det and sum(1 for c in s["chars"] if c["count"] is not None) == n_cnt
          and sum(1 for c in s["chars"] if c["mismatch"]) == mis and s["installed"] and not s["errors"], (s["history"]["total"], s["errors"]))
    # 3. цикл записи с откатом — только служебная учётка LIVE_UID/LIVE_IDX, день без отметки
    saved = A.TEST_ONLY_MAX_UID
    A.TEST_ONLY_MAX_UID = 5000
    owner = ops.Ctx(None, "selftest_a610", "owner", "127.0.0.1", "test")

    def snap():
        with db.GameReader("joy1") as r:
            c = r.rows("SELECT ACNo, ACount, Step FROM dbo.AttendanceCount WHERE Userindex = ? AND Charidx = ? ORDER BY ACNo", (LIVE_UID, LIVE_IDX))
            d = r.rows("SELECT ADNo, Step, CONVERT(varchar(23), RegistDay, 121) AS rd, Note FROM dbo.AttendanceDetail WHERE Userindex = ? AND Charidx = ? "
                       "ORDER BY ADNo", (LIVE_UID, LIVE_IDX))
        return [tuple(x.values()) for x in c], [tuple(x.values()) for x in d]
    try:
        c0, d0 = snap()
        taken = {x[2][:10].replace("-", "") for x in d0}
        day = next((datetime.date.today() - datetime.timedelta(days=n)).strftime("%Y%m%d") for n in range(30, 300)
                   if (datetime.date.today() - datetime.timedelta(days=n)).strftime("%Y%m%d") not in taken)
        base = {"uid": LIVE_UID, "idx": LIVE_IDX, "day": day, "reason": "живой самотест А6.10 (откат сразу)"}
        pv = ops.run(owner, "attendance.credit", dict(base, req=_key()), dry=True)["preview"]
        r1 = ops.run(owner, "attendance.credit", dict(base, req=_key(), expect=pv["expect"]))
        c1, d1 = snap()
        r2 = ops.run(owner, "attendance.revoke", dict(base, req=_key(), expect={"count": r1["result"]["count_after"]}))
        c2, d2 = snap()
        u2 = ops.undo(owner, r2["audit_id"])
        u1 = ops.undo(owner, r1["audit_id"])
        c3, d3 = snap()
        check("живое (запись с откатом, учётка %d слот %d, день %s): засчитать → строка дня «adm #N» и счёт +1, снять → строки нет и счёт −1, откат снятия "
              "и откат засчитывания → строки и счёт как до цикла" % (LIVE_UID, LIVE_IDX, day),
              len(d1) == len(d0) + 1 and any(x[3] == "adm #%d" % r1["result"]["log_id"] for x in d1) and len(d2) == len(d0)
              and r1["result"]["count_after"] == r1["result"]["count_before"] + 1 and u2["ok"] and u1["ok"] and d3 == d0
              and [(x[1], x[2]) for x in c3] == [(x[1], x[2]) for x in c0] and (len(c3) == len(c0)), (c0, d0, c1, d1, c2, d2, c3, d3))
    except ops.OpRefused as ex:
        check("живое: цикл записи с откатом (учётка %d слот %d)" % (LIVE_UID, LIVE_IDX), False, str(ex))
    finally:
        A.TEST_ONLY_MAX_UID = saved
    # 4. служба на сервере (код службы, SSH, python -): та же сводка
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import attendance as A\n"
             "S = A.summary({'from': '20200101', 'size': '1'})\nprint('ATPROBE total=%d installed=%s errors=%d' % (S['history']['total'], S['installed'], len(S['errors'])))\n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        p2 = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                             r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                             r'@@ASTORY_SERVER_PYTHON@@ -"'],
                            input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out2 = (p2.stdout + p2.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out2 = "ssh: %s" % ex
    mm = re.search(r"ATPROBE total=(\d+) installed=(\w+) errors=(\d+)", out2)
    check("служба на сервере (SSH): сводка тем же кодом — строк дней %d, журнал установлен, без ошибок" % n_det,
          bool(mm) and int(mm.group(1)) == n_det and mm.group(2) == "True" and mm.group(3) == "0", out2[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/attendance" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/attendance без входа — 401", code == 401, code)
