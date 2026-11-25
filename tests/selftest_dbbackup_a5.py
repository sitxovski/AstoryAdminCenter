# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_dbbackup_a5.py — самотест шага А5.7 «Бэкапы БД» (21.11.2026; domains/dbbackup.py, dbstand.py, sql/adminc_16_dbbackup.sql,
/api/dbbackup, карточка «Бэкапы БД», консоль db).

offline(check)  — план уборки (последний проверенный и KEEP_MIN проверенных — никогда, без проверенных готовые не удаляются, сроки,
                  KEEP_MAX), безопасный путь файла (только папка панели и имя панели этой строки), выбор баз, права ролей, операции и их
                  исполнитель, срок повтора задания, отказ восстановления на живой сервер, стенд только консолью ПК, имя базы стенда,
                  сверка строк, ключи консоли, переводы EN, тексты отказов без «; », SQL / выкладка / проверка прав / откат, веб без innerHTML.
sandbox(check)  — СВОЙ экземпляр LocalDB (AsdaA57Stand): базы AsdaAdmin и Joy1, логин asda_admin с теми же запретами, что на сервере;
                  настоящий sql/adminc_16_dbbackup.sql (дважды): у asda_admin прямой BACKUP — отказ, через подписанную процедуру — бэкап и
                  VERIFYONLY; операции db.backup / db.verify / db.prune под asda_admin, отказы (не из списка, мало места, идёт бэкап, зависшая
                  строка, задание уже поставлено), путь браузера через задание службы, уборка с защитой, испорченный файл, состояние; стенд
                  db.restore_stand на том же экземпляре (md5, RESTORE … WITH MOVE, CHECKDB, строки, файл и база стенда удалены).
live(check)     — только чтение сервера: состояние баз через подписанную процедуру, права asda_admin (BACKUP — нет), бэкапы панели проверены,
                  md5 файлов на сервере = журналу, папка и её права, чужие бэкапы на месте, модели восстановления не менялись, сухой
                  предпросмотр бэкапа, отказы. Новых бэкапов не делает.
Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE = "AsdaA57Stand"
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    except SystemExit as ex:
        return "SystemExit: %s" % ex
    return None


def _ctx(via="cli", role="owner", uid=None, login="cli:selftest@a57"):
    from core import ops
    return ops.Ctx(uid, login, role, "", via)


def _row(i, status="done", verified=True, days=0.0, db="Joy1", fold=r"@@ASTORY_SERVER_ROOT@@\DbBackup"):
    now = datetime.datetime(2026, 11, 21, 12, 0, 0)
    t = now - datetime.timedelta(days=days)
    return {"id": i, "db": db, "status": status, "verified": verified, "started_at": t, "finished_at": t,
            "file_path": "%s\\%s_%s_%d.bak" % (fold, db, t.strftime("%Y%m%d_%H%M%S"), i)}


def _plan_offline(check, B):
    now = datetime.datetime(2026, 11, 21, 12, 0, 0)
    ids = lambda rows: sorted(r["id"] for r, _w in B.prune_plan(rows, now))
    # все старше KEEP_DAYS (31…40 дн., 21.10…12.10): защищены последние KEEP_MIN проверенных (№10, 9, 8) и недельные / месячные (№7 — неделя 42)
    rows = [_row(i, days=B.KEEP_DAYS + (11 - i)) for i in range(1, 11)]
    check("бэкапы: уборка — все старше срока, последние %d проверенных и последний бэкап недели остаются" % B.KEEP_MIN,
          ids(rows) == [1, 2, 3, 4, 5, 6], ids(rows))
    # ★ ревизия 47 С-3: долгие копии — год ежедневных бэкапов: моложе срока не удаляется ничего, недельные за 8 нед. и месячные за 12 мес. — остаются
    rows = [_row(i, days=400 - i) for i in range(1, 401)]
    gone = set(ids(rows))
    kept = [r for r in rows if r["id"] not in gone]
    old_kept = [r for r in kept if now - r["finished_at"] > datetime.timedelta(days=B.KEEP_DAYS)]
    months = {(r["finished_at"].year, r["finished_at"].month) for r in old_kept if now - r["finished_at"] > datetime.timedelta(weeks=B.LONG_WEEKS)}
    check("бэкапы: уборка — год ежедневных: моложе %d дн. все на месте, старше — только недельные (%d нед.) и месячные (%d мес.)"
          % (B.KEEP_DAYS, B.LONG_WEEKS, B.LONG_MONTHS),
          all(now - r["finished_at"] > datetime.timedelta(days=B.KEEP_DAYS) for r in rows if r["id"] in gone)
          and len(months) == len([r for r in old_kept if now - r["finished_at"] > datetime.timedelta(weeks=B.LONG_WEEKS)])
          and B.LONG_MONTHS - 3 <= len(months) <= B.LONG_MONTHS and len(old_kept) < 30 and gone, (len(gone), len(kept), sorted(months)))
    # ★ ревизия 47 С-3: частые нажатия «бэкап» (40 свежих) — автоуборка не трогает ничего; ручная владельца — сверх KEEP_MAX
    rows = [_row(i, days=(B.KEEP_MAX + 10 - i) * 0.01) for i in range(1, B.KEEP_MAX + 11)]
    check("бэкапы: уборка — 40 свежих бэкапов: автоуборка ничего не вытесняет", ids(rows) == [], ids(rows))
    man = sorted(r["id"] for r, _w in B.prune_plan(rows, now, manual=True))
    check("бэкапы: уборка — ручная владельца (db.prune): сверх %d на базу уходят 10 самых старых" % B.KEEP_MAX, man == list(range(1, 11)), man)
    # последний проверенный — старый, после него неудачные и непроверенные свежие: он не удаляется
    rows = [_row(1, days=40), _row(2, verified=False, days=1), _row(3, status="failed", verified=None, days=5)]
    got = ids(rows)
    check("бэкапы: уборка — единственный проверенный (40 дн.) не удаляется, неудачный старше %d дн. — удаляется" % B.FAILED_KEEP_DAYS,
          got == [3], got)
    # ни одного проверенного: готовые не удаляются вовсе (даже очень старые), неудачные — по сроку
    rows = [_row(1, verified=False, days=100), _row(2, verified=None, days=90), _row(3, status="failed", verified=None, days=1)]
    check("бэкапы: уборка — нет проверенных: готовые не трогаются, свежий неудачный — тоже", ids(rows) == [], ids(rows))
    # ★ ревизия 47 (мелочь 4): неудачный без пути (сбой до записи файла) — в плане, без файла
    rows = [_row(1, days=1), dict(_row(2, status="failed", verified=None, days=5), file_path="")]
    check("бэкапы: уборка — неудачный без пути файла попадает в план (снимается отметкой, а не «пропущено»)", ids(rows) == [2], ids(rows))
    # удалённые и идущие в план не попадают
    rows = [_row(1, status="deleted", days=99), _row(2, status="running", verified=None, days=99), _row(3, days=1)]
    check("бэкапы: уборка — удалённые и идущие не рассматриваются", ids(rows) == [], ids(rows))
    # безопасный путь
    fold = r"@@ASTORY_SERVER_ROOT@@\DbBackup"
    r = _row(7)
    check("бэкапы: путь — файл панели этой строки в её папке принят", B.safe_file(fold, r) == r["file_path"], r["file_path"])
    check("бэкапы: путь — папка с «\\» в конце принята", B.safe_file(fold + "\\", r) == r["file_path"])
    bad = [dict(r, file_path=r"H:\SQLBackup_P45_20261008\Joy1.bak"), dict(r, file_path=r["file_path"].replace("_7.bak", "_8.bak")),
           dict(r, db="AsdaStoryOp"), dict(r, file_path=r"@@ASTORY_SERVER_ROOT@@\DbBackup\sub\Joy1_20261121_120000_7.bak"),
           dict(r, file_path=r"@@ASTORY_SERVER_ROOT@@\DbBackup\..\Joy1_20261121_120000_7.bak"), dict(r, file_path=r"@@ASTORY_SERVER_ROOT@@\DbBackup\Joy1'_20261121_120000_7.bak"),
           dict(r, file_path="")]
    check("бэкапы: путь — чужая папка, чужой номер, чужая база, подпапка, «..», кавычка, пусто — не трогается",
          all(B.safe_file(fold, x) is None for x in bad), [B.safe_file(fold, x) for x in bad])
    check("бэкапы: путь — папка с кавычкой не принимается", B.safe_file("H:\\A'B", r) is None)


def _ops_offline(check, B, S):
    from core import auth, jobs, ops
    names = ["AsdaAdmin", "AsdaStoryLogin", "AsdaStoryOp", "Joy1", "joylog1"]
    check("бэкапы: базы — all → весь список", B._dbs({"dbs": "all"}, names) == names)
    check("бэкапы: базы — строка через запятую, регистр, повтор", B._dbs({"dbs": "joy1, JOY1,asdastoryop"}, names) == ["Joy1", "AsdaStoryOp"])
    check("бэкапы: базы — не из списка — отказ", "не в списке бэкапов панели" in (_refused(lambda: B._dbs({"dbs": "master"}, names)) or ""))
    check("бэкапы: базы — пустой список — отказ", _refused(lambda: B._dbs({"dbs": []}, names)) is not None)
    for n in ("db.backup", "db.verify", "db.prune", "db.restore", "db.restore_stand", "db.release"):
        check("бэкапы: операция %s зарегистрирована" % n, n in ops.REGISTRY)
    op = ops.REGISTRY["db.backup"]
    check("бэкапы: исполнитель заданий бэкапа — служба, срок повтора — 366 дн.", op.schedule_runner == "service" and jobs.repeat_days("db.backup") == 366)
    t = datetime.datetime(2026, 11, 21, 3, 0)
    check("бэкапы: срок повтора задания бэкапа — год, у прочих — прежние %d дн." % jobs.REPEAT_DAYS,
          jobs.repeat_limit(t, "daily", jobs.repeat_days("db.backup")) == t + datetime.timedelta(days=366)
          and jobs.repeat_limit(t, "daily", jobs.repeat_days("live.announce")) == t + datetime.timedelta(days=jobs.REPEAT_DAYS)
          and jobs.repeat_limit(t, "", 366) is None)
    for perm, roles in (("db.view", {"owner", "admin"}), ("db.backup", {"owner", "admin"}), ("db.prune", {"owner"}), ("db.stand", {"owner"})):
        check("бэкапы: право %s — только %s" % (perm, ", ".join(sorted(roles))),
              {r for r in ("owner", "admin", "gm", "support") if auth.can(r, perm)} == roles)
    for ctx in (_ctx(), _ctx("web"), _ctx("job")):
        w = _refused(lambda: ops.run(ctx, "db.restore", {}, dry=True))
        check("бэкапы: восстановление на живой сервер — всегда отказ с объяснением (%s)" % ctx.via, w == B.LIVE_RESTORE_REFUSAL, w)
    for via in ("web", "job"):
        w = _refused(lambda: ops.run(_ctx(via), "db.restore_stand", {"id": 1}, dry=True))
        check("бэкапы: стенд LocalDB — не консолью (%s) — отказ до чтения базы" % via, w and "только консолью на ПК" in w, w)
    check("бэкапы: стенд — строка подключения только (localdb)", S.STAND_SERVER.lower().startswith("(localdb)\\"))
    keep = B.allowed
    B.allowed = lambda: names
    try:
        check("бэкапы: имя базы стенда — <база>_stand_<номер>", S.stand_name("Joy1", 12) == "Joy1_stand_12")
        check("бэкапы: имя базы стенда — лишние знаки убраны", S.stand_name("Joy1]; DROP", 3) == "Joy1DROP_stand_3")
    finally:
        B.allowed = keep
    # ★ ревизия 47 С-2: долгие задания — своим потоком службы
    check("бэкапы: долгие операции — db.backup и db.verify", jobs.long_ops() == ["db.backup", "db.verify"], jobs.long_ops())
    f0, f1, f2 = jobs._op_filter(None), jobs._op_filter(True), jobs._op_filter(False)
    check("бэкапы: фильтр заданий — все / только долгие / без долгих", f0 == ("", ()) and f1 == (" AND op IN (?,?)", ("db.backup", "db.verify"))
          and f2 == (" AND op NOT IN (?,?)", ("db.backup", "db.verify")), (f0, f1, f2))
    from core import sched
    seen = []
    sched.jobs_once(run_due=lambda r, now, long=None: seen.append((r, long)) or [], long=True)
    sched.jobs_once(run_due=lambda r, now: seen.append((r, "старый вызов")) or [])
    src = open(os.path.join(ROOT, "core", "sched.py"), encoding="utf-8").read()
    check("бэкапы: служба — поток sched (без долгих) и поток sched-long (только долгие), просрочка долгих — %d ч" % (jobs.GRACE_LONG_S // 3600),
          seen == [("service", True), ("service", "старый вызов")] and 'name="sched-long"' in src and "jobs_once(long=False)" in src
          and "jobs_once(long=True)" in src, seen)
    from domains import stack
    check("бэкапы: форма заданий — db.backup есть, db.verify нет (нужен номер — кнопка карточки)",
          {"db.backup"} == {o["op"] for o in stack.schedulable(_ctx())} & {"db.backup", "db.verify"})
    check("бэкапы: право db.release — только владелец", {r for r in ("owner", "admin", "gm", "support") if auth.can(r, "db.release")} == {"owner"})
    miss, diff, same = S.compare_counts({"dbo.a": 1, "dbo.b": 2, "dbo.c": 3}, {"dbo.a": 1, "dbo.b": 5, "dbo.d": 9})
    check("бэкапы: сверка строк — нет таблицы, расхождение, совпало", miss == ["dbo.c"] and diff == [("dbo.b", 2, 5)] and same == 1, (miss, diff, same))


def _cli_offline(check):
    sys.path.insert(0, ROOT)
    import asda_admin as A
    ok = lambda a: A.db_args(a)
    check("бэкапы: консоль — ключи backup --all, --db, prune --confirm-prune --dry, stand --id N --keep разобраны",
          ok(["backup", "--all"]) == ("backup", {"--all": True}) and ok(["backup", "--db", "Joy1"]) == ("backup", {"--db": "Joy1"})
          and ok(["prune", "--confirm-prune", "--dry"]) == ("prune", {"--confirm-prune": True, "--dry": True})
          and ok(["stand", "--id", "5", "--keep"]) == ("stand", {"--id": "5", "--keep": True})
          and ok(["release", "--confirm-release"]) == ("release", {"--confirm-release": True}))
    for bad in (["backup", "--force"], ["backup", "--db"], ["verify", "--id", "--keep"], ["nope"], [], ["state", "--all"], ["stand", "--live"]):
        check("бэкапы: консоль — %s — отказ без действий" % " ".join(bad or ["(пусто)"]), (_refused(lambda: A.db_args(bad)) or "").startswith("SystemExit"))
    w = _refused(lambda: A._db(["backup", "--all", "--db", "Joy1"]))
    check("бэкапы: консоль — --all вместе с --db — отказ до операции", w and "ровно одно" in w, w)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60)
    out = r.stdout.decode("utf-8", "replace")
    check("бэкапы: консоль --help — справка с разделом db, без действий", r.returncode == 0 and "db …" in out and "stand --id N" in out)


def _i18n_offline(check):
    from core import i18n
    i18n.set_lang("en")
    try:
        cyr = re.compile("[А-Яа-яЁё]")
        samples = [
            "база вне списка бэкапов панели (adm.dbbackup_db) — бэкап не начат",
            "мало места на томе папки бэкапов: свободно 100 МБ, нужно не меньше 2048 МБ (данные базы × 2 + запас 1024 МБ) — бэкап не начат",
            "бэкап записан и проверен (COPY_ONLY, CHECKSUM, VERIFYONLY)",
            "бэкап: Joy1 №12 проверен, 41.7 МБ; AsdaStoryOp №13 проверен, 30.3 МБ, убрано старых: 2; joylog1 не сделан: Cannot open backup device",
            "последний проверенный бэкап панели старше 48 ч",
            "модель FULL без бэкапов журнала: файл журнала только растёт (панель модель восстановления не меняет)",
            "мало места на диске стенда (C:\\x): свободно 1.5 ГБ, нужно для начала не меньше 7.0 ГБ — восстановление не начато",
            "стенд бэкапа №12: восстановлен, CHECKDB без ошибок, таблиц 300, совпало со снимком 298, расхождений в живых таблицах 2 — файл и база стенда удалены с ПК",
            "бэкап поставлен заданием службы №55 — начнётся в течение минуты",
            "Бэкапы БД: сделать бэкап (COPY_ONLY, проверка VERIFYONLY)",
        ]
        from domains import dbbackup as B
        samples.append(B.LIVE_RESTORE_REFUSAL)
        # ★ ревизия 47 Н-1: образцы — настоящим _reason (код THROW снимается) и вложенные причины
        import pyodbc
        raw = "[42000] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]%s (%d) (SQLExecDirectW)"
        for txt, code in (("база вне списка бэкапов панели (adm.dbbackup_db) — бэкап не начат", 50701),
                          ("уже идёт бэкап или восстановление на сервере — бэкап не начат", 50704),
                          ("мало места на томе папки бэкапов: свободно 10 МБ, нужно не меньше 2048 МБ (данные базы × 2 + запас 1024 МБ) — бэкап не начат", 50707)):
            got = B._reason(pyodbc.ProgrammingError("42000", raw % (txt, code)))
            check("бэкапы: _reason снимает код THROW (%d), текст = шаблону" % code, got == txt, got)
            samples.append(got)
            samples.append("бэкап: Joy1 не сделан: %s" % got)
        samples += ["бэкап №3: проверка не прошла: повторная проверка RESTORE VERIFYONLY не прошла",
                    "стенд бэкапа №3: md5 скачанного файла не совпал (aa, на сервере bb) — файл стёрт, восстановление не начато",
                    "стенд бэкапа №3: RuntimeError: DBCC CHECKDB нашёл ошибки: 8939: Table error",
                    "стенд бэкапа №3: проверка прошла, но уборка стенда не удалась: x.mdf: busy",
                    "сбой: уже идёт бэкап или восстановление на сервере — бэкап не начат",
                    "уже идёт бэкап или проверка панели (база Joy1, №4) — дождитесь итога",
                    "задание №7 висит в «идёт», хотя бэкап не идёт (служба упала посреди) — снимите его: db release",
                    "проверенных бэкапов панели нет, последний чужой бэкап — 2026-10-30 00:17 UTC (по истории msdb, наличие файла не проверялось)"]
        bad = [(s[:60], i18n.tr(s)[:80]) for s in samples if cyr.search(i18n.tr(s))]
        check("бэкапы: переводы EN — без русских букв (%d образцов, в том числе составной итог по базам)" % len(samples), not bad, bad)
    finally:
        i18n.set_lang("ru")


def _static_offline(check):
    sql = open(os.path.join(ROOT, "sql", "adminc_16_dbbackup.sql"), encoding="utf-8").read()
    body = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S)
    check("бэкапы SQL: COPY_ONLY + CHECKSUM, NOINIT (файл не затирается), VERIFYONLY с CHECKSUM",
          "WITH COPY_ONLY, CHECKSUM, NOINIT, NOSKIP" in body and body.count("RESTORE VERIFYONLY FROM DISK = @file WITH FILE = @pos, CHECKSUM") == 2)
    check("бэкапы SQL: нет BACKUP LOG, RESTORE DATABASE, смены модели, xp_cmdshell, sysadmin, TRUSTWORTHY, COMPRESSION",
          not re.search(r"BACKUP\s+LOG|RESTORE\s+DATABASE|SET\s+RECOVERY|xp_cmdshell|sysadmin|TRUSTWORTHY|COMPRESSION|\bFORMAT\b(?!\s*\()", body, re.I))
    check("бэкапы SQL: подпись — закрытый ключ стирается, четыре процедуры подписаны, логин подписи — VIEW SERVER STATE и CREATE ANY DATABASE",
          "REMOVE PRIVATE KEY" in body and body.count("ADD SIGNATURE TO adm.DbBackup") == 5
          and "GRANT VIEW SERVER STATE TO adm_dbbackup_signer; GRANT CREATE ANY DATABASE TO adm_dbbackup_signer;" in body
          and "ALTER ROLE db_backupoperator ADD MEMBER adm_dbbackup_u" in body)
    check("бэкапы SQL: asda_admin — EXECUTE процедур и SELECT таблиц, прямой записи нет",
          "DENY INSERT, UPDATE, DELETE ON adm.dbbackup TO [asda_admin]" in body and "GRANT EXECUTE ON adm.DbBackupRun TO [asda_admin]" in body
          and not re.search(r"GRANT\s+(INSERT|UPDATE|DELETE)[^;]*adm\.dbbackup", body))
    check("бэкапы SQL: даты только ГГГГММДД (у русского входа сервера «ГГГГ-ММ-ДД» читается как dmy — ошибка 190)",
          not re.search(r"'{1,2}\d{4}-\d{2}-\d{2}", body))
    check("бэкапы SQL: QUOTED_IDENTIFIER ON отдельным пакетом до создания таблиц (урок А5.1)",
          re.match(r"\s*SET ANSI_NULLS ON;\s*SET QUOTED_IDENTIFIER ON;\s*GO", body) is not None)
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("бэкапы выкладка: adminc_16 после adminc_14 в AsdaAdmin, папка @@ASTORY_SERVER_ROOT_ESC@@\\DbBackup с правами SQL Server, файлы не удаляются",
          "Run 'adminc_14_jobs.sql' 'AsdaAdmin'\nRun 'adminc_16_dbbackup.sql' 'AsdaAdmin'" in dep.replace("\r\n", "\n")
          and 'BACKUP_DIR = r"@@ASTORY_SERVER_ROOT_ESC@@\\DbBackup"' in dep and "'%(svc)s:(OI)(CI)M'" in dep and '"NT SERVICE\\\\MSSQL$" + SQL_INSTANCE' in dep   # ★ 25.11 (М-7): служба экземпляра
          and not re.search(r"Remove-Item[^\n]*\$d", dep))
    ver = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    check("бэкапы проверка прав: у asda_admin нет BACKUP DATABASE / LOG, CREATE ANY DATABASE, VIEW SERVER STATE, записи в adm.dbbackup",
          all(x in ver for x in ("'Joy1 BACKUP DATABASE'", "'Joy1 BACKUP LOG'", "'CREATE ANY DATABASE'", "'VIEW SERVER STATE'",
                                 "'adm.dbbackup INSERT'", "'adm.DbBackupRun EXEC'")))
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    check("бэкапы откат: логин подписи, сертификат и пользователи — убираются, файлы бэкапов — нет",
          (rb is None or "DROP LOGIN adm_dbbackup_signer" in rb) and (rb is None or "DROP CERTIFICATE adm_dbbackup_cert" in rb) and (rb is None or rb.count("DROP USER adm_dbbackup_u") == 1)
          and (rb is None or "FOR SELECT name FROM sys.databases WHERE state_desc = 'ONLINE'" in rb))          # ★ ревизия 47 Н-3: курсор по всем базам
    # тексты отказов без «; » (перевод разбирает «; » как список вложенных причин)
    for f in ("dbbackup.py", "dbstand.py"):
        src = open(os.path.join(ROOT, "domains", f), encoding="utf-8").read()
        bad = re.findall(r'OpRefused\(\s*"([^"]*; [^"]*)"', src) + re.findall(r'OpRefused\(\s*\(\s*"([^"]*; [^"]*)"', src)
        check("бэкапы: отказы %s без «; »" % f, not bad, bad)
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    i = app.index("function dbCard()")
    card = app[i:app.index("\nfunction ", i + 10)]           # только сама карточка (за ней в файле — карточки других шагов)
    card = re.sub(r"(?m)^\s*//.*$", "", card)               # без комментариев (проверка — по коду)
    check("бэкапы веб: карточка без innerHTML, кнопки только db.backup / db.verify, кнопки восстановления нет",
          "innerHTML" not in card and '"db.backup"' in card and '"db.verify"' in card and "db.restore" not in app
          and "can(\"db.view\") ? dbCard() : null" in app)
    js = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    need = ["Бэкапы БД", "Сделать бэкап сейчас", "Перепроверить", "Проверенный бэкап панели", "Бэкапов панели ещё нет."]
    check("бэкапы веб: надписи карточки переведены (i18n.js)", all('"%s":' % x in js for x in need), [x for x in need if '"%s":' % x not in js])
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("бэкапы API: GET /api/dbbackup — право db.view", '@route("GET", r"/api/dbbackup", perm="db.view")' in srv)


def offline(check):
    sys.path.insert(0, ROOT)
    from domains import load_all
    load_all()
    from domains import dbbackup as B, dbstand as S
    _plan_offline(check, B)
    _ops_offline(check, B, S)
    _cli_offline(check)
    _i18n_offline(check)
    _static_offline(check)


# ---------------------------------------------------------------------------------------------------------------- песочница LocalDB

def _localdb(*a):
    return subprocess.run(["sqllocaldb"] + list(a), capture_output=True, timeout=180)


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def sandbox(check, _ldb=None):
    import pyodbc
    srv = "(localdb)\\" + INSTANCE
    raw = lambda database: pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=%s;DATABASE=%s;Trusted_Connection=yes;" % (srv, database),
                                          autocommit=True, timeout=60)
    _localdb("stop", INSTANCE, "-k")
    _localdb("delete", INSTANCE)
    c = _localdb("create", INSTANCE, "-s")
    if c.returncode != 0:
        return check("бэкапы стенд: свой экземпляр LocalDB %s создан" % INSTANCE, False, (c.stdout + c.stderr)[-300:])
    fdir = tempfile.mkdtemp(prefix="asda_a57_")
    try:
        _sandbox(check, raw, fdir)
    finally:
        _localdb("stop", INSTANCE, "-k")
        _localdb("delete", INSTANCE)
        shutil.rmtree(fdir, ignore_errors=True)


def _sandbox(check, raw, fdir):
    import pyodbc
    from core import db, jobs, ops
    from domains import dbbackup as B, dbstand as S
    m = raw("master")
    for d, coll in (("AsdaAdmin", "Cyrillic_General_CI_AS"), ("Joy1", "Arabic_CI_AS")):
        f = os.path.join(fdir, d)
        m.cursor().execute("CREATE DATABASE [%s] ON (NAME = N'%s', FILENAME = N'%s.mdf') LOG ON (NAME = N'%s_log', FILENAME = N'%s_log.ldf') COLLATE %s"
                           % (d, d, f, d, f, coll))
    m.cursor().execute("CREATE LOGIN asda_admin WITH PASSWORD = N'Aa1-stand-%s', CHECK_POLICY = OFF" % os.urandom(6).hex())
    a = raw("AsdaAdmin")
    for b in _batches(open(os.path.join(ROOT, "sql", "adminc_02_schema.sql"), encoding="utf-8").read()):
        a.cursor().execute(b)
    a.cursor().execute("CREATE USER asda_admin FOR LOGIN asda_admin WITH DEFAULT_SCHEMA = adm")
    a.cursor().execute("GRANT SELECT, INSERT ON adm.audit TO asda_admin; GRANT UPDATE (undone_by) ON adm.audit TO asda_admin; "
                       "GRANT SELECT ON adm.users TO asda_admin")
    for b in _batches(open(os.path.join(ROOT, "sql", "adminc_14_jobs.sql"), encoding="utf-8").read()):
        a.cursor().execute(b)
    j = raw("Joy1")
    j.cursor().execute("CREATE TABLE dbo.Charinfo (Userindex INT, Charname VARCHAR(20)); INSERT dbo.Charinfo VALUES (1,'a'),(2,'b'),(3,'c'); "
                       "CREATE TABLE dbo.Item (Uuid BIGINT); INSERT dbo.Item SELECT TOP 500 ROW_NUMBER() OVER (ORDER BY (SELECT 1)) FROM sys.all_objects")
    j.cursor().execute("CREATE USER asda_admin FOR LOGIN asda_admin; ALTER ROLE db_datareader ADD MEMBER asda_admin; DENY INSERT, UPDATE, DELETE, "
                       "EXECUTE, ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO asda_admin")
    sql16 = open(os.path.join(ROOT, "sql", "adminc_16_dbbackup.sql"), encoding="utf-8").read()
    a.cursor().execute("SET LANGUAGE Russian")      # как у Windows-входа Administrator на сервере (dmy: '2099-12-31' — ошибка 190, выкладка 21.11)
    try:
        for k in (1, 2):
            for b in _batches(sql16):
                a.cursor().execute(b)
        check("бэкапы стенд: adminc_16_dbbackup.sql выполнен дважды (повтор безопасен: сертификат, подпись, логин пересозданы)", True)
    except pyodbc.Error as ex:
        return check("бэкапы стенд: adminc_16_dbbackup.sql выполнен", False, str(ex)[:400])
    bk = os.path.join(fdir, "bk")
    os.makedirs(bk)
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET folder = ?", bk)
    lst = [r[0] for r in a.cursor().execute("SELECT name FROM adm.dbbackup_db ORDER BY name").fetchall()]
    check("бэкапы стенд: список баз — только существующие из белого списка", lst == ["AsdaAdmin", "Joy1"], lst)
    priv = a.cursor().execute("SELECT pvt_key_encryption_type_desc FROM sys.certificates WHERE name = 'adm_dbbackup_cert'").fetchone()
    check("бэкапы стенд: у сертификата подписи нет закрытого ключа", priv and priv[0] == "NO_PRIVATE_KEY", priv)

    seq = [0]

    def as_admin(database):                         # соединение «как служба»: логин asda_admin (EXECUTE AS LOGIN, REVERT при закрытии)
        # своя строка подключения на каждое соединение: пул ODBC не отдаёт его повторно (сброс соединения после EXECUTE AS сервер
        # отвергает «session is in the kill state»)
        seq[0] += 1
        cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=(localdb)\\%s;DATABASE=%s;Trusted_Connection=yes;APP=a57sb%d;"
                            % (INSTANCE, database, seq[0]), autocommit=True, timeout=60)
        return _AsLogin(cn, "asda_admin")

    def direct(sql):
        cn = as_admin("AsdaAdmin")
        try:
            cn.cursor().execute(sql)
            return None
        except pyodbc.Error as ex:
            return str(ex)
        finally:
            cn.close()
    w = direct("BACKUP DATABASE Joy1 TO DISK = N'%s' WITH COPY_ONLY" % os.path.join(bk, "direct.bak"))
    check("бэкапы стенд: asda_admin сам BACKUP DATABASE — отказ 262", w and "(262)" in w, (w or "")[:200])
    w = direct("RESTORE VERIFYONLY FROM DISK = N'%s'" % os.path.join(bk, "direct.bak"))
    check("бэкапы стенд: asda_admin сам RESTORE VERIFYONLY — отказ", w is not None, (w or "")[:200])
    w = direct("INSERT adm.dbbackup (db, file_path, by_login) VALUES ('Joy1', 'x', 'y')")
    check("бэкапы стенд: asda_admin пишет в adm.dbbackup напрямую — отказ", w and "(229)" in w, (w or "")[:200])
    a.cursor().execute("INSERT adm.users (login, role, pw_hash, pw_salt, pw_iter) VALUES (N'a57owner', 'owner', 0x00, 0x00, 1), "
                       "(N'a57gm', 'gm', 0x00, 0x00, 1)")
    uid = a.cursor().execute("SELECT id FROM adm.users WHERE login = N'a57owner'").fetchone()[0]

    hooks = (B.FILE_INFO, B.DELETE_FILE, B.COUNTS, S.DOWNLOAD, S.CONNECT, S.STAND_DIR, S.LOG)

    def finfo(p):
        h = hashlib.md5(open(p, "rb").read()).hexdigest()
        return os.path.getsize(p), h

    def fdel(p):
        if not os.path.exists(p):
            return False
        os.remove(p)
        return True

    def fcounts(dbname):
        cn = as_admin(dbname)
        try:
            return {str(r[0]): int(r[1]) for r in cn.cursor().execute(B.COUNT_SQL).fetchall()}
        finally:
            cn.close()
    B.FILE_INFO, B.DELETE_FILE, B.COUNTS = finfo, fdel, fcounts
    db.set_override("admin", lambda database: as_admin("AsdaAdmin"))
    try:
        _sandbox_ops(check, raw, a, bk, uid, fdir)
    finally:
        db.set_override("admin", None)
        B.FILE_INFO, B.DELETE_FILE, B.COUNTS, S.DOWNLOAD, S.CONNECT, S.STAND_DIR, S.LOG = hooks
        for c in (a, j, m):
            try:
                c.close()
            except Exception:
                pass


def _sandbox_ops(check, raw, a, bk, uid, fdir):
    import pyodbc
    from core import jobs, ops
    from domains import dbbackup as B, dbstand as S
    cli = _ctx("cli")
    q = lambda sql, *p: a.cursor().execute(sql, *p).fetchall()
    # 1. бэкап консолью: обе базы, проверка, md5, снимок строк
    r = ops.run(cli, "db.backup", {"dbs": "all"})
    rows = q("SELECT id, db, status, verified, file_path, md5, file_bytes, counts, position FROM adm.dbbackup ORDER BY id")
    ok = len(rows) == 2 and all(x[2] == "done" and x[3] and os.path.exists(x[4]) and x[5] == hashlib.md5(open(x[4], "rb").read()).hexdigest()
                                and x[6] == os.path.getsize(x[4]) for x in rows)
    check("бэкапы стенд: db.backup под asda_admin — обе базы готовы и проверены, md5 и длина в журнале = файлу", ok, (r["message"], rows))
    cj = json.loads([x for x in rows if x[1] == "Joy1"][0][7] or "{}")
    check("бэкапы стенд: снимок строк Joy1 после бэкапа (Charinfo 3, Item 500)", cj.get("dbo.Charinfo") == 3 and cj.get("dbo.Item") == 500, cj)
    names = [os.path.basename(x[4]) for x in rows]
    check("бэкапы стенд: имена файлов — <база>_<ГГГГММДД>_<ЧЧММСС>_<номер>.bak", all(B.NAME_RX.match(n) for n in names), names)
    hist = q("SELECT TOP 2 is_copy_only, has_backup_checksums FROM msdb.dbo.backupset ORDER BY backup_set_id DESC")
    check("бэкапы стенд: в истории msdb — COPY_ONLY и контрольные суммы", all(h[0] and h[1] for h in hist), hist)
    au = q("SELECT TOP 1 action, result, message FROM adm.audit ORDER BY id DESC")
    check("бэкапы стенд: запись журнала db.backup ok с итогом по базам", au and au[0][0] == "db.backup" and au[0][1] == "ok"
          and "проверен" in au[0][2], au)
    # 2. отказы
    w = B._call("SET NOCOUNT ON; EXEC adm.DbBackupRun @db = ?, @by = ?", ("master", "t"))[1]
    check("бэкапы стенд: база не из списка — отказ процедуры (50701, код снят в тексте)", w == "база вне списка бэкапов панели (adm.dbbackup_db) — бэкап не начат", w)
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET free_factor = 100000000")
    w = _refused(lambda: ops.run(cli, "db.backup", {"dbs": "Joy1"}, dry=True))
    w2 = B._call("SET NOCOUNT ON; EXEC adm.DbBackupRun @db = ?, @by = ?", ("Joy1", "t"))[1]
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET free_factor = 2")
    check("бэкапы стенд: мало места — отказ и в предпросмотре, и в процедуре (строки не появилось)",
          w and "мало места" in w and w2 and w2.startswith("мало места на томе папки бэкапов") and len(q("SELECT id FROM adm.dbbackup")) == 2, (w, w2))
    # ★ ревизия 47 В-1: зависшая строка «идёт» (сеанс оборвался) — ops.run бэкапа не отказывает, а снимает её и делает бэкап
    a.cursor().execute("INSERT adm.dbbackup (db, file_path, by_login, started_at) VALUES ('Joy1', N'', N'stale', DATEADD(HOUR, -3, SYSUTCDATETIME()))")
    pv = ops.run(cli, "db.backup", {"dbs": "Joy1"}, dry=True)["preview"]
    check("бэкапы стенд (рев. 47 В-1): зависшая строка — предпросмотр не отказывает, предупреждает «будет снята»",
          any("висит в «идёт»" in x for x in pv["warnings"]), pv["warnings"])
    r = ops.run(cli, "db.backup", {"dbs": "Joy1"})
    stale = q("SELECT status, message FROM adm.dbbackup WHERE by_login = N'stale'")
    check("бэкапы стенд (рев. 47 В-1): ops.run db.backup — зависшая строка закрыта «прервано», бэкап сделан",
          stale and stale[0][0] == "failed" and "прервано" in stale[0][1] and "проверен" in r["message"], (stale, r["message"]))
    # ★ ревизия 47 С-1: бэкап идёт на самом деле (блокировку держит другой сеанс) — отказ везде, его строка «идёт» не снимается
    holder = raw("AsdaAdmin")
    holder.cursor().execute("EXEC sp_getapplock @Resource = N'adm.dbbackup', @LockMode = N'Exclusive', @LockOwner = N'Session', @LockTimeout = 0")
    a.cursor().execute("INSERT adm.dbbackup (db, file_path, by_login) VALUES ('Joy1', N'', N'live')")
    w = _refused(lambda: ops.run(cli, "db.backup", {"dbs": "Joy1"}, dry=True))
    w2 = B._call("SET NOCOUNT ON; EXEC adm.DbBackupRun @db = ?, @by = ?", ("Joy1", "t"))[1]
    rc = B._call("DECLARE @r INT; EXEC @r = adm.DbBackupAbort; SELECT @r AS r")[0]
    w3 = _refused(lambda: ops.run(cli, "db.release", {"confirm": "release"}, dry=True))
    w4 = _refused(lambda: ops.run(cli, "db.verify", {"id": 1}, dry=True))
    live = q("SELECT status FROM adm.dbbackup WHERE by_login = N'live'")[0][0]
    check("бэкапы стенд (рев. 47 С-1): блокировку держит другой сеанс — отказ предпросмотра, процедуры (50704), снятия и перепроверки, "
          "строка «идёт» цела", w and "уже идёт бэкап или проверка" in w and w2 == "уже идёт бэкап или восстановление на сервере — бэкап не начат" and rc and rc[0]["r"] == 1
          and w3 and "идёт на самом деле" in w3 and w4 and "уже идёт" in w4 and live == "running", (w, w2, rc, w3, w4, live))
    spid = holder.cursor().execute("SELECT @@SPID").fetchone()[0]
    a.cursor().execute("KILL %d" % int(spid))         # сеанс оборвался (служба упала) — блокировка снялась сама, строка стала зависшей
    try:
        holder.close()
    except pyodbc.Error:
        pass
    # ★ ревизия 47 В-1: зависшее задание db.backup и строка — снимает db.release (владелец), из браузера кнопка не блокируется
    jst = jobs.add("db.backup", {"dbs": ["Joy1"]}, "service", jobs.utc_now(), "", "", "a57owner", uid, "owner")
    a.cursor().execute("UPDATE adm.job SET status = 'running', started_at = SYSUTCDATETIME() WHERE id = ?", jst)
    web = _ctx("web", uid=uid, login="a57owner")
    pv = ops.run(web, "db.backup", {"dbs": "Joy1"}, dry=True)["preview"]
    check("бэкапы стенд (рев. 47 В-1): зависшее задание db.backup — кнопка не отказывает, подсказка db release",
          any("db release" in x for x in pv["warnings"]), pv["warnings"])
    w = _refused(lambda: ops.run(_ctx("cli", role="admin"), "db.release", {"confirm": "release"}, dry=True))
    w2 = _refused(lambda: ops.run(cli, "db.release", {}, dry=True))
    r = ops.run(cli, "db.release", {"confirm": "release"})
    st = q("SELECT status FROM adm.dbbackup WHERE by_login = N'live'")[0][0]
    js = q("SELECT status, result FROM adm.job WHERE id = ?", jst)[0]
    check("бэкапы стенд (рев. 47 В-1): db.release — администратору нет права, без слова — отказ; владелец снял строку и задание",
          w and "нет права" in w and w2 and "confirm = release" in w2 and st == "failed" and js[0] == "failed" and "снято вручную" in js[1]
          and "заданий 1" in r["message"], (w, w2, st, js, r["message"]))
    w = _refused(lambda: ops.run(cli, "db.release", {"confirm": "release"}, dry=True))
    check("бэкапы стенд (рев. 47 В-1): снимать больше нечего — отказ", w and "снимать нечего" in w, w)
    # ★ ревизия 48 Н-2: живое задание db.backup между базами (блокировка бэкапа свободна) — db.release его НЕ видит: исполнитель держит
    #   applock задания всё время прогона; без applock (служба упала) то же задание — зависшее
    seen = {}
    jlive = jobs.add("db.backup", {"dbs": ["Joy1"]}, "service", jobs.utc_now(), "", "", "a57owner", uid, "owner")

    def mid_run(ctx, name, prm):                       # «между базами»: строки running нет, блокировка adm.dbbackup свободна
        seen["busy"] = B.busy()
        seen["stale"] = [j["id"] for j in B.stale_jobs()]
        seen["release"] = _refused(lambda: ops.run(cli, "db.release", {"confirm": "release"}, dry=True))
        keep_alive = jobs.job_alive                      # воспроизведение прежней логики (только блокировка бэкапа): задание — «зависшее»
        jobs.job_alive = lambda i: False
        try:
            seen["old"] = [j["id"] for j in B.stale_jobs()]
        finally:
            jobs.job_alive = keep_alive
        return {"message": "подмена: бэкап между базами"}
    jobs.run_due("service", long=True, runner=mid_run)
    jdone = q("SELECT status, result FROM adm.job WHERE id = ?", jlive)[0]
    check("бэкапы стенд (рев. 48 Н-2): живое задание между базами (блокировка бэкапа свободна) — не «зависшее», db.release снимать нечего, "
          "итог задания записан", not seen["busy"]["lock_held"] and jlive not in seen["stale"] and seen["release"] and "снимать нечего" in seen["release"]
          and jdone[0] == "done" and "между базами" in jdone[1], (seen, jdone))
    check("бэкапы стенд (рев. 48 Н-2): воспроизведение — по одной блокировке бэкапа (прежняя логика) то же живое задание считалось зависшим",
          jlive in seen["old"], seen.get("old"))
    jdead = jobs.add("db.backup", {"dbs": ["Joy1"]}, "service", jobs.utc_now(), "", "", "a57owner", uid, "owner")
    a.cursor().execute("UPDATE adm.job SET status = 'running', started_at = SYSUTCDATETIME() WHERE id = ?", jdead)
    check("бэкапы стенд (рев. 48 Н-2): то же задание без applock исполнителя (служба упала) — зависшее", jdead in [j["id"] for j in B.stale_jobs()])
    ops.run(cli, "db.release", {"confirm": "release"})
    # ★ ревизия 47 Н-4: отказ процедуры до начала — строка не ищется по времени, чужая не подменяет итог
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET free_factor = 100000000")
    res = B.backup_one("Joy1", "cli:selftest@a57")
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET free_factor = 2")
    check("бэкапы стенд (рев. 47 Н-4): отказ процедуры (мало места) — итог «отказ» без номера, прошлый бэкап того же автора не подставлен",
          res["status"] == "refused" and res["id"] is None and "мало места" in (res["error"] or ""), res)
    w = B._call("SET NOCOUNT ON; EXEC adm.DbBackupRun @db = ?, @by = ?", ("Joy1 ", "t"))[1]
    check("бэкапы стенд (рев. 47, мелочь 1): имя базы с хвостовым пробелом — отказ 50701", w and "вне списка" in w, w)
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET folder = ?", bk + "'x")
    w = B._call("SET NOCOUNT ON; EXEC adm.DbBackupRun @db = ?, @by = ?", ("Joy1", "t"))[1]
    a.cursor().execute("UPDATE adm.dbbackup_cfg SET folder = ?", bk)
    check("бэкапы стенд (рев. 47, мелочь 2): папка с кавычкой — отказ процедуры", w and "папка бэкапов панели" in w, w)
    # 3. путь браузера: задание службы на «сейчас», повторное нажатие — отказ, исполнитель службы — делает бэкап
    web = _ctx("web", uid=uid, login="a57owner")
    r = ops.run(web, "db.backup", {"dbs": "Joy1"})
    jid = r["result"]["job"]
    jr = q("SELECT op, runner, status, params FROM adm.job WHERE id = ?", jid)
    check("бэкапы стенд: из браузера — задание службы №N на сейчас, бэкап не начат", jr and jr[0][0] == "db.backup" and jr[0][1] == "service"
          and jr[0][2] == "pending" and json.loads(jr[0][3]) == {"dbs": ["Joy1"]}, jr)
    w = _refused(lambda: ops.run(web, "db.backup", {"dbs": "Joy1"}, dry=True))
    check("бэкапы стенд: повторное нажатие, пока задание ждёт — отказ", w and "уже поставлен заданием" in w, w)
    n0 = len(q("SELECT id FROM adm.dbbackup WHERE status = 'done'"))
    out0 = jobs.run_due("service", long=False)
    j0 = q("SELECT status FROM adm.job WHERE id = ?", jid)[0][0]
    check("бэкапы стенд (рев. 47 С-2): поток обычных заданий службы бэкап не берёт", j0 == "pending" and not out0, (j0, out0))
    out = jobs.run_due("service", long=True)
    jr = q("SELECT status, result FROM adm.job WHERE id = ?", jid)
    check("бэкапы стенд: исполнитель службы выполнил задание бэкапа (done, итог по базе)", jr and jr[0][0] == "done" and "Joy1" in jr[0][1]
          and len(q("SELECT id FROM adm.dbbackup WHERE status = 'done'")) == n0 + 1, (out, jr))
    a.cursor().execute("UPDATE adm.users SET role = 'gm' WHERE id = ?", uid)
    jid2 = jobs.add("db.backup", {"dbs": "all"}, "service", jobs.utc_now(), "daily", "", "a57owner", uid, "owner")
    out = jobs.run_due("service")
    jr = q("SELECT status, result, DATEDIFF(DAY, run_at, repeat_until) FROM adm.job WHERE id = ?", jid2)
    check("бэкапы стенд: автор задания потерял право (gm) — задание отказано, бэкапа нет; срок повтора — 366 дн.",
          jr and jr[0][0] == "refused" and "db.backup" in jr[0][1] and jr[0][2] == 366, jr)
    a.cursor().execute("UPDATE adm.users SET role = 'owner' WHERE id = ?", uid)
    a.cursor().execute("UPDATE adm.job SET status = 'cancelled' WHERE status = 'pending'")
    # 4. перепроверка и испорченный файл
    last = q("SELECT TOP 1 id, file_path FROM adm.dbbackup WHERE db = 'AsdaAdmin' AND status = 'done' ORDER BY id DESC")[0]
    r = ops.run(cli, "db.verify", {"id": last[0]})
    check("бэкапы стенд: db.verify — проверка прошла", r["message"].endswith("проверка прошла"), r["message"])
    r = ops.run(web, "db.verify", {"id": last[0]})
    jv = r["result"]["job"]
    w = _refused(lambda: ops.run(web, "db.verify", {"id": last[0]}, dry=True))
    out = jobs.run_due("service", long=True)
    jr = q("SELECT op, status, result FROM adm.job WHERE id = ?", jv)[0]
    check("бэкапы стенд (рев. 47 Н-5): перепроверка из браузера — задание службы (поток долгих), повтор пока ждёт — отказ",
          jr[0] == "db.verify" and jr[1] == "done" and "проверка прошла" in jr[2] and w and "уже поставлена заданием" in w, (jr, w))
    with open(last[1], "r+b") as f:
        f.seek(os.path.getsize(last[1]) // 2)
        f.write(b"\x00" * 65536)
    try:
        ops.run(cli, "db.verify", {"id": last[0]})
        bad = None
    except B.BackupFailed as ex:
        bad = str(ex)
    v = q("SELECT verified FROM adm.dbbackup WHERE id = ?", last[0])[0][0]
    check("бэкапы стенд: испорченный файл — db.verify сбой, отметка «не проверен»", bad and "проверка не прошла" in bad and v is False, (bad, v))
    # 5. уборка: старые строки, защищённые, чужие файлы
    foreign = os.path.join(bk, "Joy1_20200101_000000_999.bak")
    open(foreign, "wb").write(b"foreign")
    other = os.path.join(fdir, "Joy1_other.bak")
    open(other, "wb").write(b"other")
    # строка с файлом вне папки панели — до четырёх новых (номер меньше: не в KEEP_MIN и не последняя за неделю / месяц), того же дня
    a.cursor().execute("INSERT adm.dbbackup (db, file_path, by_login, status, verified, finished_at, started_at) VALUES ('Joy1', ?, N'x', 'done', 1, "
                       "SYSUTCDATETIME(), SYSUTCDATETIME())", other)
    for k in range(4):
        B.backup_one("Joy1", "selftest")
    a.cursor().execute("UPDATE adm.dbbackup SET finished_at = DATEADD(DAY, -40, finished_at), started_at = DATEADD(DAY, -40, started_at) WHERE db = 'Joy1'")
    joy = q("SELECT id, file_path FROM adm.dbbackup WHERE db = 'Joy1' AND status = 'done' AND verified = 1 ORDER BY id DESC")
    w = _refused(lambda: ops.run(cli, "db.prune", {"db": "Joy1"}, dry=True))
    check("бэкапы стенд: уборка без подтверждения — отказ", w and "confirm = prune" in w, w)
    pv = ops.run(cli, "db.prune", {"db": "Joy1", "confirm": "prune"}, dry=True)["preview"]
    r = ops.run(cli, "db.prune", {"db": "Joy1", "confirm": "prune"})
    kept = [x[0] for x in joy[:B.KEEP_MIN]]
    left = q("SELECT id FROM adm.dbbackup WHERE db = 'Joy1' AND status = 'done' ORDER BY id DESC")
    gone = q("SELECT id, deleted_why FROM adm.dbbackup WHERE db = 'Joy1' AND status = 'deleted'")
    check("бэкапы стенд: уборка — последние %d проверенных остались, старшие удалены (файлы и отметки), чужие файлы на месте" % B.KEEP_MIN,
          [x[0] for x in left if x[0] in kept] == kept and all(not os.path.exists(x[1]) for x in joy[B.KEEP_MIN:] if x[1] != other)
          and all(os.path.exists(x[1]) for x in joy[:B.KEEP_MIN]) and os.path.exists(foreign) and os.path.exists(other)
          and gone and all("старше" in (g[1] or "") for g in gone), (r["message"], left, gone))
    check("бэкапы стенд: строка с файлом вне папки панели — пропущена с объяснением", any("пропущено (не панели)" in x for x in pv["warnings"]), pv["warnings"])
    # 6. состояние (у AsdaAdmin единственный бэкап испорчен выше)
    st = B.state()
    d = {x["db"]: x for x in st["dbs"]}
    check("бэкапы стенд: состояние прочитано через подписанную процедуру (место на томе, модель, последний любой бэкап)",
          st["read"] and st["free_bytes"] and set(d) == {"AsdaAdmin", "Joy1"} and d["Joy1"]["any"] and d["Joy1"]["recovery"], st.get("error"))
    wa = d["AsdaAdmin"]["warnings"]
    check("бэкапы стенд: предупреждения — «проверенных нет» и «последний не прошёл проверку»",
          any("проверенных бэкапов панели нет" in w for w in wa) and any("не прошёл проверку" in w for w in wa) and not d["AsdaAdmin"]["panel_verified"], wa)
    B.backup_one("AsdaAdmin", "selftest")
    a.cursor().execute("UPDATE adm.dbbackup SET finished_at = DATEADD(DAY, -3, finished_at) WHERE db = 'AsdaAdmin' AND verified = 1")
    B.backup_one("Joy1", "selftest")                 # у Joy1 все бэкапы состарены уборкой выше — свежий
    d = {x["db"]: x for x in B.state()["dbs"]}
    check("бэкапы стенд: предупреждение — последний проверенный старше %d ч, у свежей Joy1 — нет" % B.WARN_HOURS,
          any("старше %d ч" % B.WARN_HOURS in w for w in d["AsdaAdmin"]["warnings"]) and d["AsdaAdmin"]["age_h"] > B.WARN_HOURS
          and not any("старше" in w for w in d["Joy1"]["warnings"]), (d["AsdaAdmin"]["warnings"], d["Joy1"]["warnings"]))
    # 7. стенд LocalDB на этом же экземпляре
    sdir = os.path.join(fdir, "stand")
    S.STAND_DIR, S.LOG = sdir, (lambda *x: None)
    S.CONNECT = lambda database: _stand_cn(raw, database)
    oth = q("SELECT id FROM adm.dbbackup WHERE file_path = ?", other)[0][0]
    w = _refused(lambda: ops.run(cli, "db.restore_stand", {"id": oth}))
    check("бэкапы стенд: файл не в папке панели — на стенд не скачивается", w and "не в папке панели" in w, w)
    src = q("SELECT TOP 1 id, file_path FROM adm.dbbackup WHERE db = 'Joy1' AND status = 'done' AND verified = 1 AND file_path <> ? ORDER BY id DESC",
            other)[0]
    S.DOWNLOAD = lambda remote, local: open(local, "wb").write(b"broken")
    w = _refused(lambda: ops.run(cli, "db.restore_stand", {"id": src[0]}))
    check("бэкапы стенд: md5 скачанного не совпал — отказ, файл стёрт", w and "md5 скачанного файла не совпал" in w and not os.listdir(sdir), w)
    S.DOWNLOAD = lambda remote, local: shutil.copyfile(remote, local)
    r = ops.run(cli, "db.restore_stand", {"id": src[0]})
    sres = q("SELECT stand_ok, stand_result FROM adm.dbbackup WHERE id = ?", src[0])[0]
    left_db = q("SELECT name FROM sys.databases WHERE name LIKE '%_stand_%'")
    check("бэкапы стенд: восстановлено на стенд, CHECKDB чист, строки = снимку, файл и база стенда удалены, итог в журнале",
          "CHECKDB без ошибок" in r["message"] and sres[0] is True and json.loads(sres[1])["counts"]["same"] >= 2 and not os.listdir(sdir)
          and not left_db, (r["message"], left_db))
    r = ops.run(cli, "db.restore_stand", {"id": src[0], "keep": True})
    kept_db = q("SELECT name FROM sys.databases WHERE name = ?", "Joy1_stand_%d" % src[0])
    check("бэкапы стенд: --keep — база стенда оставлена (и названа в итоге), файл бэкапа всё равно стёрт",
          kept_db and "оставлена" in r["message"] and not [x for x in os.listdir(sdir) if x.endswith(".bak")], r["message"])
    w = _refused(lambda: ops.run(cli, "db.restore_stand", {"id": last[0]}))
    check("бэкапы стенд: непроверенный бэкап на стенд — отказ", w and "не прошёл проверку VERIFYONLY" in w, w)
    # ★ ревизия 48 Н-5: база --keep (для ручного переноса) переживает прогон стенда ДРУГОГО бэкапа; тот же бэкап поверх неё — только --drop-kept
    kname = "Joy1_stand_%d" % src[0]
    src2 = q("SELECT TOP 1 id FROM adm.dbbackup WHERE db = 'AsdaAdmin' AND status = 'done' AND verified = 1 ORDER BY id DESC")[0][0]
    pv = ops.run(cli, "db.restore_stand", {"id": src2}, dry=True)["preview"]
    r2 = ops.run(cli, "db.restore_stand", {"id": src2})
    j2 = json.loads(q("SELECT stand_result FROM adm.dbbackup WHERE id = ?", src2)[0][0])
    check("бэкапы стенд (рев. 48 Н-5): прогон другого бэкапа — база --keep на месте, предпросмотр называет её «не трогаются»",
          q("SELECT name FROM sys.databases WHERE name = ?", kname) and kname in j2["leftovers"]["kept"] and kname not in j2["leftovers"]["dbs"]
          and any("не трогаются" in x and kname in x for x in pv["warnings"]) and "CHECKDB без ошибок" in r2["message"],
          (j2.get("leftovers"), pv["warnings"]))
    w = _refused(lambda: ops.run(cli, "db.restore_stand", {"id": src[0]}, dry=True))
    w2 = _refused(lambda: ops.run(cli, "db.restore_stand", {"id": src[0]}))
    check("бэкапы стенд (рев. 48 Н-5): тот же бэкап поверх базы --keep без --drop-kept — отказ (предпросмотр и прогон), база на месте",
          w and "--drop-kept" in w and w2 and "--drop-kept" in w2 and q("SELECT name FROM sys.databases WHERE name = ?", kname), (w, w2))
    pv = ops.run(cli, "db.restore_stand", {"id": src[0], "drop_kept": True}, dry=True)["preview"]
    check("бэкапы стенд (рев. 48 Н-5): с --drop-kept предпросмотр предупреждает, что база --keep будет удалена",
          any("будут удалены" in x and kname in x for x in pv["warnings"]), pv["warnings"])
    # ★ ревизия 47 В-2: оборванный RESTORE (повреждение посреди файла, md5 «совпал») → база в RESTORING → удалена без ALTER, файлы убраны,
    #   исходная ошибка — в итоге и журнале; следующий прогон убирает остатки (база --keep, база в RESTORING, чужие файлы папки стенда)
    md5_real = S._md5

    def broken(remote, local):
        shutil.copyfile(remote, local)
        with open(local, "r+b") as f:
            f.seek(os.path.getsize(local) // 2)
            f.write(os.urandom(1 << 18))
    S.DOWNLOAD, S._md5 = broken, (lambda p: q("SELECT md5 FROM adm.dbbackup WHERE id = ?", src[0])[0][0])
    try:
        bad = None
        try:
            ops.run(cli, "db.restore_stand", {"id": src[0], "drop_kept": True})
        except B.BackupFailed as ex:
            bad = str(ex)
    finally:
        S._md5 = md5_real
    sres = q("SELECT stand_ok, stand_result FROM adm.dbbackup WHERE id = ?", src[0])[0]
    left_db = q("SELECT name, state_desc FROM sys.databases WHERE name LIKE '%[_]stand[_]%'")
    jr = json.loads(sres[1])
    check("бэкапы стенд (рев. 47 В-2): RESTORE оборван — база стенда (RESTORING) удалена, файлов в папке стенда нет, исходная ошибка RESTORE "
          "в итоге, запись итога есть (stand_ok = 0)", bad and "RESTORE" in bad and not left_db and not os.listdir(sdir) and sres[0] is False
          and "RESTORE" in (jr.get("error") or "") and not jr.get("cleanup_errors"), (bad, left_db, os.listdir(sdir), jr.get("error")))
    check("бэкапы стенд (рев. 47 В-2, 48 Н-5): прошлый прогон с --keep убран этим прогоном (с --drop-kept, до скачивания)",
          ("Joy1_stand_%d" % src[0]) in (jr.get("leftovers") or {}).get("dbs", []), jr.get("leftovers"))
    m2 = raw("master")
    bakp = os.path.join(fdir, "left.bak")
    cur = m2.cursor()
    cur.execute("BACKUP DATABASE Joy1 TO DISK = ? WITH COPY_ONLY, INIT", bakp)
    while cur.nextset():
        pass
    cur = m2.cursor()
    cur.execute("RESTORE DATABASE Joy1_stand_999 FROM DISK = ? WITH MOVE 'Joy1' TO ?, MOVE 'Joy1_log' TO ?, NORECOVERY", bakp,
                os.path.join(sdir, "Joy1_stand_999_0.mdf"), os.path.join(sdir, "Joy1_stand_999_1.ldf"))
    while cur.nextset():
        pass
    open(os.path.join(sdir, "Joy1_20200101_000000_1.bak"), "wb").write(b"left")
    restoring = q("SELECT state_desc FROM sys.databases WHERE name = 'Joy1_stand_999'")
    S.DOWNLOAD = lambda remote, local: shutil.copyfile(remote, local)
    r = ops.run(cli, "db.restore_stand", {"id": src[0]})
    jr = json.loads(q("SELECT stand_result FROM adm.dbbackup WHERE id = ?", src[0])[0][0])
    check("бэкапы стенд (рев. 47 В-2): остатки (база в RESTORING, файлы, .bak) убраны при старте, затем стенд прошёл",
          restoring and restoring[0][0] == "RESTORING" and "Joy1_stand_999" in jr["leftovers"]["dbs"] and jr["leftovers"]["files"] >= 3
          and not q("SELECT name FROM sys.databases WHERE name LIKE '%[_]stand[_]%'") and not os.listdir(sdir) and "CHECKDB без ошибок" in r["message"],
          (restoring, jr.get("leftovers"), os.listdir(sdir)))
    m2.close()


class _AsLogin:
    """Соединение под чужим логином (EXECUTE AS LOGIN); при закрытии — REVERT: соединение из пула ODBC с невозвращённым контекстом сервер
    убивает при следующем сбросе («session is in the kill state»)."""

    def __init__(self, cn, login):
        object.__setattr__(self, "_cn", cn)
        cn.cursor().execute("EXECUTE AS LOGIN = ?", login)

    def __getattr__(self, k):
        return getattr(self._cn, k)

    def __setattr__(self, k, v):
        setattr(self._cn, k, v)

    def close(self):
        try:
            cur = self._cn.cursor()
            cur.execute("REVERT")
        except Exception:
            pass
        self._cn.close()


def _stand_cn(raw, database):
    import pyodbc                                       # как dbstand._connect: своя строка на соединение (без повторного соединения из пула)
    cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=(localdb)\\%s;DATABASE=%s;Trusted_Connection=yes;APP=a57st-%s;"
                        % (INSTANCE, database, os.urandom(4).hex()), autocommit=True, timeout=60)
    cn.timeout = 600
    return cn


# ---------------------------------------------------------------------------------------------------------------- живьём (только чтение)

def live(check):
    sys.path.insert(0, ROOT)
    from domains import load_all
    load_all()
    from core import db, hostshell, ops
    from domains import dbbackup as B
    st = B.state()
    check("бэкапы (живьём): состояние баз прочитано подписанной процедурой (asda_admin)", st["read"], st.get("error"))
    if not st["read"]:
        return
    d = {x["db"]: x for x in st["dbs"]}
    check("бэкапы (живьём): список — Joy1, AsdaStoryOp, joylog1, AsdaStoryLogin, AsdaAdmin",
          set(d) == {"Joy1", "AsdaStoryOp", "joylog1", "AsdaStoryLogin", "AsdaAdmin"}, sorted(d))
    check("бэкапы (живьём): папка @@ASTORY_SERVER_ROOT_ESC@@\\DbBackup, место на томе прочитано", st.get("folder") == r"@@ASTORY_SERVER_ROOT@@\DbBackup" and (st.get("free_bytes") or 0) > 0,
          (st.get("folder"), st.get("free_bytes")))
    want = {"Joy1": "FULL", "AsdaStoryOp": "FULL", "joylog1": "FULL", "AsdaStoryLogin": "FULL", "AsdaAdmin": "SIMPLE"}
    check("бэкапы (живьём): модели восстановления не менялись", {k: d[k]["recovery"] for k in d} == want, {k: d[k]["recovery"] for k in d})
    with db.GameReader("joy1") as r:
        perm = r.rows("SELECT HAS_PERMS_BY_NAME('Joy1', 'DATABASE', 'BACKUP DATABASE') AS b, HAS_PERMS_BY_NAME(NULL, NULL, 'CREATE ANY DATABASE') AS c, "
                      "IS_SRVROLEMEMBER('sysadmin') AS s")[0]
    check("бэкапы (живьём): у asda_admin своих прав BACKUP / CREATE ANY DATABASE / sysadmin нет", perm["b"] == 0 and perm["c"] == 0 and perm["s"] == 0, perm)
    ver = {k: v["panel_verified"] for k, v in d.items()}
    check("бэкапы (живьём): у каждой базы есть проверенный бэкап панели (VERIFYONLY) с md5", all(v and v["md5"] for v in ver.values()),
          {k: (v and v["id"]) for k, v in ver.items()})
    files = [v["file"] for v in ver.values() if v]
    if files:
        ps = "; ".join("$h = Get-FileHash -LiteralPath '%s' -Algorithm MD5; 'MD5|%s|' + $h.Hash.ToLower()" % (f, os.path.basename(f)) for f in files)
        try:
            out = hostshell.powershell(ps, 600)
            got = dict(re.findall(r"MD5\|(\S+)\|([0-9a-f]{32})", out))
        except hostshell.HostError as ex:
            got = {"error": str(ex)}
        check("бэкапы (живьём): md5 файлов на сервере = журналу панели", all(got.get(os.path.basename(v["file"])) == v["md5"] for v in ver.values() if v),
              got)
    try:
        acl = hostshell.powershell("(Get-Acl -LiteralPath '%s').Access | %% { $_.IdentityReference.Value + '|' + $_.FileSystemRights }; "
                                   "'BAK|' + (Get-ChildItem H:\\ -Directory -Filter 'SQLBackup_*' | %% { $_.Name + ':' + (Get-ChildItem $_.FullName -File).Count }) -join ','"
                                   % st["folder"], 60)
    except hostshell.HostError as ex:
        acl = "ошибка: %s" % ex
    check("бэкапы (живьём): права папки — Administrators, SYSTEM, SQL Server, без Users / Everyone",
          "MSSQL$SQLEXPRESS" in acl and "SYSTEM" in acl and not re.search(r"\\Users\||Everyone|Authenticated Users", acl), acl[:400])
    m = re.search(r"BAK\|(.*)", acl)
    check("бэкапы (живьём): чужие бэкапы H:\\SQLBackup_* на месте (4 папки, файлы не удалены)",
          m and m.group(1).count(":") == 4 and "SQLBackup_precleanup_20260830:4" in m.group(1) and "SQLBackup_P45_20261008:3" in m.group(1),
          m and m.group(1))
    cli = _ctx("cli")
    try:
        r = ops.run(cli, "db.backup", {"dbs": "all"}, dry=True)
        check("бэкапы (живьём): сухой предпросмотр бэкапа всех баз (бэкап не делается)", r["dry"] and len(r["preview"]["dbs"]) == 5, r["preview"]["text"])
    except ops.OpRefused as ex:
        check("бэкапы (живьём): сухой предпросмотр бэкапа всех баз", False, str(ex))
    w = _refused(lambda: ops.run(cli, "db.restore", {}, dry=True))
    check("бэкапы (живьём): восстановление на живой сервер — отказ", w == B.LIVE_RESTORE_REFUSAL, w)
    w = _refused(lambda: ops.run(_ctx("web"), "db.restore_stand", {"id": 1}, dry=True))
    check("бэкапы (живьём): стенд из браузера — отказ", w and "только консолью" in w, w)
    running = [x for x in st["rows"] if x["status"] == "running"]
    check("бэкапы (живьём): зависших строк «идёт» нет", not running, running)
