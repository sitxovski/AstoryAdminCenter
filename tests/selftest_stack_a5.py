# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_stack_a5.py — самотест шага А5.1 «Стойка и планировщик» (20.11.2026; domains/stack.py, core/jobs.py, restart_stack.py).

offline(check)       — restart_stack.py, загруженный модулем, с подменёнными SSH, подпроцессами и часами: отметки и длина отсчёта в игре
                       (без ASDA_RESTART_TICK — прежний один time.sleep), --stop-only (объявление «stop», нет старта; коды 1/2/7), текст
                       Discord «stop» (EN/AR/RU) без загрузки бота; операции стойки на подменах (ключи restart_stack, ПК/консоль,
                       подтверждение, «не прочитано», перепроверка в apply, итоги refused / error / ok), тексты отсчёта ≤ 95 байт cp1251,
                       выкладка (adminc_14 после 03, права в adminc_10), переводы веб-панели.
sandbox(check, ldb)  — adm.job на LocalDB (adminc_02 + adminc_14): взаимоисключение стойки уникальным индексом, прямой запуск и задание,
                       job.add (отказы, второй фактор из браузера, без кода в params), исполнитель ПК (взял → выполнил → повтор daily),
                       пропуск просроченного (поздно не запускается), занятая стойка — задание ждёт, автор отключён — отказ, job.cancel,
                       job.release, проход службы sched.jobs_once при сбое журнала.
live(check)          — только чтение и запись в СВОЮ базу AsdaAdmin: счёт процессов стойки (все копии, SSH), adm.job и права asda_admin,
                       постановка задания объявления на +30 дней и его немедленная отмена, сухой предпросмотр рестарта (ничего не запускает),
                       код службы на сервере (SSH, python через stdin).
НАСТОЯЩУЮ стойку самотест не останавливает и не перезапускает, в Discord не пишет. Побочных эффектов при импорте нет.
"""
import ast
import datetime
import importlib.util
import json
import os
import re
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
SRV_TOOLS = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "tools")
BOT = os.path.join(PORT, "AstoryAdminCenter", "DiscordBot")
FULL = {"ChannelManager": 1, "DBManager": 1, "OperationServer": 1, "OverlapCheckServer": 1, "RelayServer": 3, "ItemRelayServer": 1,
        "LoginManager": 1, "NpcServer": 3, "GameServer": 3}


# ------------------------------------------------------------------------------------------------ restart_stack.py на подменах
class _Clock:
    """Подмена модуля time для restart_stack: sleep двигает часы."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s

    def strftime(self, f, *a):
        return "00:00:00"


class _Proc:
    def __init__(self, rc=0, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class _Sub:
    """Подмена subprocess для restart_stack: записывает вызовы, отвечает по правилу."""
    TimeoutExpired = __import__("subprocess").TimeoutExpired

    def __init__(self, clock, answer):
        self.clock, self.answer, self.calls = clock, answer, []

    def run(self, argv, **kw):
        self.calls.append((list(argv), kw))
        self.clock.now += 1                       # вызов занимает секунду часов
        return self.answer(argv)


def _load_rs():
    """restart_stack.py свежим модулем (под своим именем, sys.argv без ключей — без --single-channel)."""
    if SRV_TOOLS not in sys.path:
        sys.path.insert(0, SRV_TOOLS)
    spec = importlib.util.spec_from_file_location("restart_stack_a5test", os.path.join(SRV_TOOLS, "restart_stack.py"))
    mod = importlib.util.module_from_spec(spec)
    saved = sys.argv
    sys.argv = ["restart_stack.py"]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod


def _rs_offline(check):
    rs = _load_rs()
    check("restart_stack: отметки отсчёта 180 → 180/120/60/30, 60 → 60/30, 30 → 30, 240 → 240/180/120/60/30",
          rs.tick_marks(180) == [180, 120, 60, 30] and rs.tick_marks(60) == [60, 30] and rs.tick_marks(30) == [30]
          and rs.tick_marks(240) == [240, 180, 120, 60, 30], (rs.tick_marks(180), rs.tick_marks(60)))
    saved_env = os.environ.pop(rs.TICK_ENV, None)
    try:
        clk = _Clock()
        sub = _Sub(clk, lambda a: _Proc(0, b"ok\n"))
        rs.time, rs.subprocess = clk, sub
        rs.countdown(180)
        check("restart_stack: без ASDA_RESTART_TICK — один time.sleep(180), подпроцессов нет (поведение прежнее)",
              clk.sleeps == [180] and not sub.calls, (clk.sleeps, sub.calls))
        os.environ[rs.TICK_ENV] = json.dumps(["py", "tick"])
        clk = _Clock()
        sub = _Sub(clk, lambda a: _Proc(0, b"sent\n"))
        rs.time, rs.subprocess = clk, sub
        t0 = clk.now
        rs.countdown(180)
        left = [c[0][-1] for c in sub.calls]
        check("restart_stack: с ASDA_RESTART_TICK — вызовы команды с 180/120/60/30 по порядку, предел вызова 30 с, общая длина ожидания 180 с",
              left == ["180", "120", "60", "30"] and all(c[0][:2] == ["py", "tick"] and c[1].get("timeout") == 30 for c in sub.calls)
              and abs((clk.now - t0) - 180) < 0.01, (left, clk.now - t0))
        os.environ[rs.TICK_ENV] = "{не json"
        clk = _Clock()
        sub = _Sub(clk, lambda a: _Proc(0))
        rs.time, rs.subprocess = clk, sub
        rs.countdown(180)
        check("restart_stack: ASDA_RESTART_TICK не список — предупреждение и прежний sleep(180), без вызовов", clk.sleeps == [180] and not sub.calls)

        def boom(a):
            raise OSError("нет python")
        os.environ[rs.TICK_ENV] = json.dumps(["py", "tick"])
        clk = _Clock()
        sub = _Sub(clk, boom)
        rs.time, rs.subprocess = clk, sub
        t0 = clk.now
        rs.countdown(180)
        check("restart_stack: сбой команды отсчёта — предупреждение, ожидание доходит до 180 с", len(sub.calls) == 4 and abs((clk.now - t0) - 180) < 0.01,
              clk.now - t0)
    finally:
        os.environ.pop(rs.TICK_ENV, None)
        if saved_env is not None:
            os.environ[rs.TICK_ENV] = saved_env

    # --stop-only
    def scenario(argv, count_out="15", count_rc=0, announce_ok=True, stop_rc=None):
        m = _load_rs()
        clk = _Clock()
        ssh, events = [], []

        def ssh_ps(cmd, timeout=180):
            ssh.append(cmd)
            if "Measure-Object" in cmd:
                return count_rc, count_out
            return 0, ""

        def answer(a):
            if any("announce_restart.py" in x for x in a):
                events.append(("announce", list(a)))
                return _Proc(0 if announce_ok else 1, ("Отправлено: x" if announce_ok else "ошибка").encode("utf-8"))
            return _Proc(0)
        sub = _Sub(clk, answer)
        m.time, m.subprocess, m.ssh_ps = clk, sub, ssh_ps
        m.graceful_stop = lambda: events.append(("graceful",)) or (True, 0)
        m.stop_all = lambda: events.append(("stop_all",)) or stop_rc
        m.firewall_missing = lambda: events.append(("firewall",)) or []
        saved = sys.argv
        sys.argv = ["restart_stack.py"] + argv
        try:
            rc = m.main()
        finally:
            sys.argv = saved
        return rc, events, ssh, clk

    rc, ev, ssh, clk = scenario(["--stop-only"])
    ann = [e for e in ev if e[0] == "announce"]
    check("--stop-only: объявление Discord с --kind stop и --minutes 3, ожидание 180 с, SC_CLOSE, остановка, код 0; ни start.bat, ни брандмауэра, "
          "ни паритета, ни CharPos", rc == 0 and len(ann) == 1 and ann[0][1][-2:] == ["--kind", "stop"] and "--minutes" in ann[0][1]
          and ann[0][1][ann[0][1].index("--minutes") + 1] == "3" and [e[0] for e in ev] == ["announce", "graceful", "stop_all"]
          and 180 in clk.sleeps and not any("AsdaStackStart" in c or "start.bat" in c or "UP_AsdaCharPosReset" in c for c in ssh), (rc, ev, ssh))
    rc, ev, ssh, clk = scenario(["--stop-only"], count_out="", count_rc=255)
    check("--stop-only: счёт процессов не прочитан — код 7, объявления и остановки нет", rc == 7 and not ev, (rc, ev))
    rc, ev, ssh, clk = scenario(["--stop-only"], count_out="0")
    check("--stop-only: процессов 0 — код 7 (останавливать нечего), объявления нет", rc == 7 and not ev, (rc, ev))
    rc, ev, ssh, clk = scenario(["--stop-only"], announce_ok=False)
    check("--stop-only: объявление не ушло — код 2, стойка не тронута (ни SC_CLOSE, ни остановки)", rc == 2 and [e[0] for e in ev] == ["announce"], (rc, ev))
    rc, ev, ssh, clk = scenario(["--stop-only"], stop_rc=3)
    check("--stop-only: процессы не остановились — код 3 (как в обычном режиме)", rc == 3, rc)
    rc1, ev1, _s, _c = scenario(["--stop-only", "--deploy", "deploy_x.py"])
    rc2, ev2, _s, _c = scenario(["--stop-only", "--start-only"])
    check("--stop-only вместе с --deploy или --start-only — код 1, ничего не делается", rc1 == 1 and rc2 == 1 and not ev1 and not ev2, (rc1, rc2))
    src = open(os.path.join(SRV_TOOLS, "restart_stack.py"), encoding="utf-8").read()
    check("restart_stack: обычный режим ждёт через countdown(wait) (без переменной — прежний sleep), шапка описывает --stop-only и ASDA_RESTART_TICK",
          "countdown(wait)                           # ★ А5.1" in src and "time.sleep(wait)\n\n    if start_only" not in src
          and "--stop-only" in src[:4000] and "ASDA_RESTART_TICK" in src[:4000])

    # текст Discord «stop» — функция text_for без загрузки бота (botctl / discord не импортируются)
    tree = ast.parse(open(os.path.join(BOT, "announce_restart.py"), encoding="utf-8").read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "text_for")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "announce_restart.text_for", "exec"), ns)
    t_stop, t_rs = ns["text_for"]("@BT", 3, "stop"), ns["text_for"]("@BT", 3)
    check("Discord: текст остановки — EN «shut down for maintenance», AR «للصيانة», RU «остановлен на обслуживание», 3 минуты; текст рестарта прежний",
          "shut down for maintenance in 3 minutes" in t_stop and "للصيانة" in t_stop and "остановлен на обслуживание через 3 минуты" in t_stop
          and t_rs.startswith("@BT\n") and "will be restarted in 3 minutes" in t_rs and "перезапущен через 3 минуты" in t_rs, t_stop)
    # ★ ревизия 41: «بعد» в тексте остановки; при 3 минутах текст рестарта — буква в букву как до А5 (бэкап 2026-11-21_a5_live)
    old_b = os.path.join(os.path.dirname(PORT), "_backup", "2026-11-21_a5_live", "AstoryAdminCenter", "DiscordBot", "announce_restart.py")
    if os.path.isfile(old_b):
        t_old = ast.parse(open(old_b, encoding="utf-8").read())
        f_old = next(n for n in t_old.body if isinstance(n, ast.FunctionDef) and n.name == "text_for")
        ns_old = {}
        exec(compile(ast.Module(body=[f_old], type_ignores=[]), "announce_restart_old.text_for", "exec"), ns_old)
        same = ns_old["text_for"]("@BT", 3) == t_rs
    else:
        same = None
    check("Discord (р41): остановка — «بعد 3 دقائق» («через»), не «خلال»; рестарт при 3 минутах = тексту до А5 буква в букву; 1 минута — "
          "«1 minute» / «1 минуту» / «1 دقيقة»", "بعد 3 دقائق" in t_stop and "خلال" not in t_stop and same is True
          and "in 1 minute." in ns["text_for"]("@BT", 1) and "через 1 минуту" in ns["text_for"]("@BT", 1, "stop")
          and "1 دقيقة" in ns["text_for"]("@BT", 1), same)
    # ★ ревизия 41 Н-4: не прочитанный счёт ≠ «остановлено»
    m4 = _load_rs()
    clk = _Clock()
    m4.time = clk
    m4.ssh_ps = lambda cmd, timeout=180: (255, "ssh: connect timed out")
    c_bad = m4.counts()
    m4.ssh_ps = lambda cmd, timeout=180: (0, "") if "Stop-Process" in cmd else (0, "GameServer=3\n" + m4.COUNTS_MARK)
    c_ok = m4.counts()
    m4.ssh_ps = lambda cmd, timeout=180: (0, "") if "Stop-Process" in cmd else (0, m4.COUNTS_MARK)
    c_zero = m4.counts()
    m4.ssh_ps = lambda cmd, timeout=180: (0, "") if "Stop-Process" in cmd else (255, "")
    rc_sa = m4.stop_all()
    check("restart_stack (р41 Н-4): сбой SSH — counts() = None (не {}), с меткой — счёт / {}; stop_all при непрочитанном — код 3, а не «остановлены»",
          c_bad is None and c_ok == {"GameServer": 3} and c_zero == {} and rc_sa == 3, (c_bad, c_ok, c_zero, rc_sa))
    check("restart_stack (р41 Н-4): сброс данжей и CharPos — только при прочитанном нуле (counts() != {}), --start-only отказывает и при None, "
          "шаг 6 — counts() or {}", src.count("elif counts() != {}:") == 2 and "if int(tail[-1]) or c or c is None:" in src
          and "c = counts() or {}" in src)
    # ★ ревизия 41 В-1: файл-замок restart_stack
    import tempfile
    tmp = tempfile.mkdtemp(prefix="asda_rs_lock_")
    try:
        lk = os.path.join(tmp, "x.lock")
        a1 = m4.acquire_lock(lk, alive=lambda pid: True)
        a2 = m4.acquire_lock(lk, alive=lambda pid: True)
        a3 = m4.acquire_lock(lk, alive=lambda pid: False)          # замок «умершего» — снимается
        m4.release_lock(lk)
        check("restart_stack (р41 В-1): файл-замок — первый берёт, второй при живом владельце — нет (PID владельца), замок умершего снимается, "
              "release снимает свой", a1 == (True, None) and a2 == (False, os.getpid()) and a3 == (True, None) and not os.path.exists(lk), (a1, a2, a3))
    finally:
        __import__("shutil").rmtree(tmp, ignore_errors=True)
    p = __import__("subprocess").run([sys.executable, os.path.join(SRV_TOOLS, "restart_stack.py"), "--help"], capture_output=True, timeout=60)
    check("restart_stack (р41): --help — шапка и код 0, замок не создаётся, ничего не делается; точка входа — run_locked (код 8 при занятом)",
          p.returncode == 0 and "--stop-only" in p.stdout.decode("utf-8", "replace") and not os.path.exists(m4.LOCK_FILE)
          and "sys.exit(run_locked())" in src and "return 8" in src, p.returncode)
    check("restart_stack (р41 Н-6): итог --stop-only — запуск только --start-only, не start.bat", "НЕ start.bat" in src)
    src_b = open(os.path.join(BOT, "announce_restart.py"), encoding="utf-8").read()
    check("Discord: ключ --kind restart|stop (по умолчанию restart), упоминается только роль", 'choices=("restart", "stop"), default="restart"' in src_b
          and "AllowedMentions(everyone=False, users=False, roles=[role])" in src_b)


# ------------------------------------------------------------------------------------------------ операции стойки на подменах
class _FakeJobs:
    """Подмена core/jobs для операций стойки без базы."""

    def __init__(self, running=None):
        self.running, self.rows, self.finished = running, [], []

    def running_stack(self):
        return self.running

    def begin_direct(self, op, params, by, uid, role):
        if self.running:
            raise self.JobLocked(self.running["id"])
        self.rows.append(op)
        self.running = {"id": 100 + len(self.rows)}
        return self.running["id"]

    def finish(self, jid, status, text="", aid=None):
        self.finished.append((jid, status, text))
        self.running = None
        return True


def _ops_offline(check):
    from core import config, jobs, ops
    from domains import stack
    FakeJobsCls = _FakeJobs
    FakeJobsCls.JobLocked = jobs.JobLocked
    cfg = config.get()
    saved = (stack.RUN, stack.COUNTS, stack.EXPECT, stack.jobs, cfg.on_server)
    audit_rows = []
    from core import audit, bridge
    saved_audit, saved_pres = audit.write, bridge.presence
    audit.write = lambda ctx, action, target="", params=None, before=None, after=None, result="ok", message="", **k: audit_rows.append(
        (action, result, message)) or len(audit_rows)
    bridge.presence = lambda uid=None: [{"uid": 1}, {"uid": 2}]
    cli = ops.Ctx(None, "cli:test@pc", "owner", "", "cli")
    try:
        stack.EXPECT = dict(FULL)
        cfg.on_server = False
        state = {"c": [dict(FULL)]}

        def counts():
            v = state["c"][0]
            if len(state["c"]) > 1:
                state["c"].pop(0)
            return v
        stack.COUNTS = counts
        runs = []

        def run_ok(argv, env, log):
            runs.append((argv, env))
            state["c"] = [dict(FULL)]
            return 0, "3. остановка стойки\n   все процессы стойки остановлены\nИТОГ: стойка поднята, патчи стоят\n"
        stack.RUN = run_ok
        stack.jobs = FakeJobsCls()
        argv, env = stack.build_argv("stack.restart")
        a2, e2 = stack.build_argv("stack.stop")
        a3, e3 = stack.build_argv("stack.start")
        tick = json.loads(env["ASDA_RESTART_TICK"])
        check("стойка: ключи restart_stack — рестарт --no-deploy, остановка --stop-only, запуск --start-only, никогда --no-announce/--wait/--skip-*/--deploy",
              argv[2:] == ["--no-deploy"] and a2[2:] == ["--stop-only"] and a3[2:] == ["--start-only"] and argv[1].endswith("restart_stack.py")
              and not any(x in stack.FORBIDDEN_FLAGS for x in argv + a2 + a3), (argv, a2, a3))
        check("стойка: отсчёт в игре — ASDA_RESTART_TICK = asda_admin.py stack tick --kind restart|stop (у запуска — нет: игроков нет)",
              tick[1].endswith("asda_admin.py") and tick[2:] == ["stack", "tick", "--kind", "restart"]
              and json.loads(e2["ASDA_RESTART_TICK"])[-1] == "stop" and "ASDA_RESTART_TICK" not in e3, (tick, e3.get("ASDA_RESTART_TICK")))

        def refused(name, p, ctx=cli, part=""):
            try:
                ops.run(ctx, name, p)
            except ops.OpRefused as ex:
                return part in str(ex)
            return False
        web = ops.Ctx(1, "owner1", "owner", "1.2.3.4", "web")
        check("стойка: из браузера — отказ «только консолью»", refused("stack.restart", {"confirm": "restart"}, web, "только консолью"))
        cfg.on_server = True
        check("стойка: служба на сервере — отказ «только консолью на ПК владельца»", refused("stack.restart", {"confirm": "restart"}, cli, "на ПК владельца"))
        cfg.on_server = False
        check("стойка: без подтверждения — отказ «--confirm-restart»", refused("stack.restart", {}, cli, "--confirm-restart")
              and refused("stack.stop", {"confirm": "restart"}, cli, "--confirm-stop"))
        gm = ops.Ctx(None, "cli:gm", "admin", "", "cli")
        check("стойка: право stack.control — только владелец (у администратора — отказ «нет права»)",
              refused("stack.restart", {"confirm": "restart"}, gm, "нет права") and ops.auth.PERMS["stack.control"] == {"owner"})
        state["c"] = [None]
        check("стойка: счёт процессов не прочитан — отказ «не прочитано», restart_stack не запускается",
              refused("stack.restart", {"confirm": "restart"}, cli, "не прочитано") and not runs)
        state["c"] = [{}]
        check("стойка: остановка при 0 процессов — отказ «уже остановлена»", refused("stack.stop", {"confirm": "stop"}, cli, "уже остановлена"))
        state["c"] = [dict(FULL)]
        check("стойка: запуск при работающих процессах — отказ «только целиком остановленной»",
              refused("stack.start", {"confirm": "start"}, cli, "целиком остановленной"))
        state["c"] = [dict(FULL), None]
        check("стойка: перепроверка в apply — счёт стал «не прочитано» после предпросмотра — отказ, restart_stack не запускается, строка задания — refused",
              refused("stack.restart", {"confirm": "restart"}, cli, "не прочитано") and not runs and stack.jobs.finished[-1][1] == "refused")
        stack.jobs = FakeJobsCls(running={"id": 7})
        state["c"] = [dict(FULL)]
        check("стойка: идёт другое управление стойкой — отказ «задание №7»", refused("stack.restart", {"confirm": "restart"}, cli, "задание №7") and not runs)
        stack.jobs = FakeJobsCls()
        audit_rows.clear()
        r = ops.run(cli, "stack.restart", {"confirm": "restart"})
        check("стойка: рестарт — restart_stack запущен один раз, итог «готово», журнал ok, строка задания done, хвост вывода в итоге",
              len(runs) == 1 and "готово" in r["message"] and audit_rows[-1][1] == "ok" and stack.jobs.finished[-1][1] == "done"
              and r["result"]["lines"][-1].startswith("ИТОГ"), (r["message"], audit_rows[-1:]))

        def run_rc(rc, out, after):
            def f(argv, env, log):
                runs.append((argv, env))
                state["c"] = [after]
                return rc, out
            return f
        stack.RUN = run_rc(2, "1. объявление в Discord\nСТОП: объявление не отправлено — стойку не трогаю\n", dict(FULL))
        state["c"] = [dict(FULL)]
        audit_rows.clear()
        check("стойка: код 2 (объявление не ушло), остановки не было, счёт тот же — отказ «стойка не тронута», журнал refused, задание refused",
              refused("stack.restart", {"confirm": "restart"}, cli, "не тронута") and audit_rows[-1][1] == "refused"
              and stack.jobs.finished[-1][1] == "refused")
        stack.RUN = run_rc(4, "   все процессы стойки остановлены\nСТОП: выкладка не прошла\n", {})
        state["c"] = [dict(FULL)]
        audit_rows.clear()
        failed = False
        try:
            ops.run(cli, "stack.restart", {"confirm": "restart"})
        except stack.StackFailed as ex:
            failed = "ожидалось: полная" in str(ex)
        check("стойка: код 4 после остановки, процессов 0 — сбой StackFailed (журнал error, задание failed), путь к журналу прогона в тексте",
              failed and audit_rows[-1][1] == "error" and stack.jobs.finished[-1][1] == "failed")
        stack.RUN = run_rc(5, "   все процессы стойки остановлены\nИТОГ: ЕСТЬ ПРОБЛЕМЫ — смотри выше\n", dict(FULL))
        state["c"] = [dict(FULL)]
        failed = False
        try:
            ops.run(cli, "stack.restart", {"confirm": "restart"})
        except stack.StackFailed:
            failed = True
        check("стойка: код 5 (стойка поднята, патчи не сошлись) при том же счёте — сбой, не «не тронута» (остановка была)", failed)
        stack.RUN = run_rc(0, "   все процессы стойки остановлены\nИТОГ: стойка остановлена (--stop-only)\n", {})
        state["c"] = [dict(FULL)]
        r = ops.run(cli, "stack.stop", {"confirm": "stop"})
        check("стойка: остановка — код 0 и процессов 0 — «готово»", "готово" in r["message"] and stack.jobs.finished[-1][1] == "done")
        stack.RUN = run_rc(0, "ИТОГ: стойка поднята, патчи стоят\n", dict(FULL))
        state["c"] = [{}]
        r = ops.run(cli, "stack.start", {"confirm": "start"})
        check("стойка: запуск — из 0 процессов в полную — «готово»", "готово" in r["message"])
        ok = all(len(stack.tick_text(k, s).encode("cp1251")) <= 95 for k in ("restart", "stop") for s in (180, 120, 60, 30))
        check("отсчёт в игре: тексты EN / RU в cp1251 не длиннее 95 байт (3113), минуты и секунды",
              ok and "3 min" in stack.tick_text("restart", 180) and "30 с" in stack.tick_text("stop", 30), stack.tick_text("stop", 180))
        prev = ops.run(cli, "stack.restart", {"confirm": "restart"}, dry=True)["preview"]
        check("стойка: предпросмотр — объявление Discord, 3 минуты с отсчётом, кто в игре по мосту (2)",
              any("Beta Tester" in w for w in prev["warnings"]) and any("моста: 2" in w for w in prev["warnings"]))
        # ★ ревизия 41 С-3: «не тронута» — только коды до действий без строк действующих шагов
        def failed_with(name, word, rc, out, before, after):
            stack.RUN = run_rc(rc, out, after)
            state["c"] = [before]
            try:
                ops.run(cli, name, {"confirm": word})
            except stack.StackFailed:
                return "failed"
            except ops.OpRefused as ex:
                return "refused" if "не тронута" in str(ex) else str(ex)
            return "ok"
        s1 = failed_with("stack.start", "start", 5, "3. остановка: нет (--start-only, процессов нет)\n4б. паритет\n4в. сброс CharPos\n5. запуск start.bat\n"
                         "ИТОГ: ЕСТЬ ПРОБЛЕМЫ\n", {}, {})
        s6 = failed_with("stack.start", "start", 6, "4б. паритет копий канала 2 с полем (stack_parity --sync)\nСТОП: СУЩЕСТВЕННОЕ расхождение\n", {}, {})
        s2 = failed_with("stack.restart", "restart", 3, "1. объявление в Discord\nОтправлено: x\n2. ожидание 180 с\n3а. штатное\n3. остановка стойки\n"
                         "СТОП: процессы не остановились\n", dict(FULL), dict(FULL))
        s0 = failed_with("stack.restart", "restart", 6, "0. паритет копий канала 2 до остановки\nСТОП до остановки: паритета нет (код 8)\n", dict(FULL), dict(FULL))
        s8 = failed_with("stack.restart", "restart", 8, "СТОП: уже работает другой restart_stack.py (PID 1, замок x) — ничего не делаю\n",
                         dict(FULL), dict(FULL))
        check("стойка (р41 С-3): --start-only с кодом 5 после CharPos/start.bat и с кодом 6 после --sync, рестарт с кодом 3 после объявления — "
              "сбой (не «не тронута»); код 6 до объявления и код 8 (другой restart_stack) — отказ «не тронута»",
              (s1, s6, s2, s0, s8) == ("failed", "failed", "failed", "refused", "refused"), (s1, s6, s2, s0, s8))

        def ki(argv, env, log):
            raise KeyboardInterrupt
        stack.RUN = ki
        state["c"] = [dict(FULL)]
        audit_rows.clear()
        got = False
        try:
            ops.run(cli, "stack.restart", {"confirm": "restart"})
        except KeyboardInterrupt:
            got = True
        check("стойка (р41 Н-1): Ctrl+C — запись журнала error «прервано оператором, проверьте стойку», строка задания failed с тем же текстом",
              got and audit_rows and audit_rows[-1][1] == "error" and "прервано оператором" in audit_rows[-1][2]
              and stack.jobs.finished[-1][1] == "failed" and "прервано оператором" in stack.jobs.finished[-1][2], (audit_rows[-1:], stack.jobs.finished[-1:]))
        state["c"] = [dict(FULL)]
        pv = ops.run(cli, "stack.stop", {"confirm": "stop"}, dry=True)["preview"]
        check("стойка (р41 Н-6): предпросмотр остановки предупреждает — запуск только stack start, не start.bat", any("start.bat" in w for w in pv["warnings"]))
    finally:
        stack.RUN, stack.COUNTS, stack.EXPECT, stack.jobs, cfg.on_server = saved
        audit.write, bridge.presence = saved_audit, saved_pres
    _stream_offline(check)
    _announce_offline(check)


def _stream_offline(check):
    """★ ревизия 41 Н-2: вывод restart_stack пишется в журнал прогона ПО ХОДУ (настоящий _run_restart на маленьком сценарии)."""
    import tempfile
    from domains import stack
    tmp = tempfile.mkdtemp(prefix="asda_stack_run_")
    try:
        sc = os.path.join(tmp, "fake_rs.py")
        log = os.path.join(tmp, "runs", "1_restart.log")
        with open(sc, "w", encoding="utf-8") as f:
            f.write("import os, sys\nlog = sys.argv[1]\nprint('строка 1', flush=True)\nprint('видно в журнале:', open(log, encoding='utf-8').read()"
                    ".count('строка 1'), flush=True)\nsys.stderr.write('ошибка в stderr\\n')\nsys.exit(5)\n")
        rc, out = stack._run_restart([sys.executable, sc, log], dict(os.environ, PYTHONIOENCODING="utf-8"), log)
        text = open(log, encoding="utf-8").read()
        check("стойка (р41 Н-2): вывод restart_stack идёт в журнал по ходу (строка видна в файле, пока процесс жив), stderr — туда же, код возврата 5",
              rc == 5 and "видно в журнале: 1" in out and "ошибка в stderr" in text and text == out.replace("\r\n", "\n"), (rc, out[-200:]))
    finally:
        __import__("shutil").rmtree(tmp, ignore_errors=True)


def _announce_offline(check):
    """★ ревизия 41 С-2: live.announce ставит команду во все узлы сразу и ждёт один общий срок ttl + 2 (а не узлы × 22 с)."""
    from core import bridge, ops, audit
    import time as _t
    saved = (bridge.nodes, bridge.enqueue, bridge.wait, audit.write)
    calls = []
    clock = {"t": 0.0}
    try:
        bridge.nodes = lambda: [{"node": n, "fresh": True, "mode": 1} for n in ("GS1", "GS2", "GS3")]
        bridge.enqueue = lambda op, uid, idx, node, args, ttl, by: calls.append(("enq", node, ttl)) or (len(calls), None)
        def wait(cid, timeout=20.0, step=0.25):
            calls.append(("wait", cid, round(timeout, 1)))
            return {"status": 2 if cid != 2 else 1, "result": "ok"}
        bridge.wait = wait
        audit.write = lambda *a, **k: 1
        r = ops.run(ops.Ctx(None, "cli:t", "owner", "", "cli"), "live.announce", {"text": "hi", "ttl": 8})
        enq = [c for c in calls if c[0] == "enq"]
        waits = [c for c in calls if c[0] == "wait"]
        check("live.announce (р41 С-2): все 3 узла поставлены до первого ожидания, срок 8 с, ожидания укладываются в общий срок ttl + 2 = 10 с; "
              "узел без итога — «итог неизвестен», остальные разосланы", [c[0] for c in calls[:3]] == ["enq"] * 3 and all(c[2] == 8 for c in enq)
              and all(w[2] <= 10.0 for w in waits) and "разослано на 2" in r["message"] and "итог неизвестен" in r["message"], (calls, r["message"]))
        calls.clear()
        ops.run(ops.Ctx(None, "cli:t", "owner", "", "cli"), "live.announce", {"text": "hi"})
        check("live.announce: без ttl — прежний срок 20 с (общее ожидание ≤ 22 с)", all(c[2] == 20 for c in calls if c[0] == "enq")
              and all(c[2] <= 22.0 for c in calls if c[0] == "wait"))
    finally:
        bridge.nodes, bridge.enqueue, bridge.wait, audit.write = saved
    from domains import stack
    check("отсчёт в игре (р41 С-2): stack tick зовёт live.announce со сроком 8 с (TICK_TTL), предел вызова restart_stack — 30 с",
          stack.TICK_TTL == 8 and '"ttl": stack.TICK_TTL' in open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read())


def _static_offline(check):
    rd = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()
    dep = rd("deploy", "deploy_admin_center.py")
    v = rd("sql", "adminc_10_verify.sql")
    s14 = rd("sql", "adminc_14_jobs.sql")
    check("выкладка: adminc_14_jobs после adminc_03 (-d AsdaAdmin); проверка прав: adm.job INSERT/UPDATE = 1, DELETE = 0",
          dep.index("Run 'adminc_14_jobs.sql' 'AsdaAdmin'") > dep.index("Run 'adminc_03_grants.sql'")
          and "'adm.job DELETE',         HAS_PERMS_BY_NAME('AsdaAdmin.adm.job','OBJECT','DELETE'),       0" in v
          and "'adm.job INSERT'" in v and "DENY  DELETE                 ON adm.job TO [asda_admin]" in s14)
    check("adminc_14: QUOTED_IDENTIFIER / ANSI_NULLS ON отдельным пакетом ДО CREATE TABLE (у sqlcmd по умолчанию OFF — выкладка 20.11 упала с 1934)",
          s14.index("SET QUOTED_IDENTIFIER ON;\nGO") < s14.index("CREATE TABLE adm.job") and "SET ANSI_NULLS ON;" in s14)
    from core import auth
    check("права А5.1: stack.control и jobs.release — только владелец, jobs.view / jobs.manage — владелец и администратор",
          auth.PERMS["stack.control"] == {"owner"} and auth.PERMS["jobs.release"] == {"owner"}
          and auth.PERMS["jobs.manage"] == {"owner", "admin"} and auth.PERMS["jobs.view"] == {"owner", "admin"})
    js, en = rd("web", "app.js"), rd("web", "i18n.js")
    blk = js[js.index("// ---------- А5.1: задания"):js.index("// ---------- Игроки: список всех")]
    keys = set(re.findall(r'"([^"\n]*[А-Яа-яЁё][^"\n]*)"', blk)) | {"Стойка: рестарт с объявлением", "Стойка: остановка с объявлением",
                                                                   "Стойка: запуск остановленной", "Живьём: объявление всем игрокам (мост, 3113)"}
    miss = sorted(k for k in keys if ('"%s":' % k) not in en)
    check("веб А5.1: карточка «Задания и стойка» на странице «Состояние» (право jobs.view), все её строки есть в I18N_EN",
          'can("jobs.view") ? jobsCard() : null' in js and not miss, miss[:5])
    from core import i18n
    i18n.set_lang("en")
    try:
        t_en = i18n.tr("restart_stack.py: код 2 — стойка не тронута (GameServer=3): [23:01:02] СТОП: объявление не отправлено — стойку не трогаю")
    finally:
        i18n.set_lang("ru")
    check("перевод (р41): отказ «стойка не тронута» по-английски целиком, вместе с хвостом вывода restart_stack",
          t_en == "restart_stack.py: code 2 — the stack was not touched (GameServer=3): STOP: the announcement was not sent — the stack is not touched", t_en)
    import subprocess
    p = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = p.stdout.decode("utf-8", "replace")
    check("консоль: --help печатает справку (stack …, jobs …) и ничего не делает", p.returncode == 0 and "stack …" in out and "jobs …" in out
          and "run-due" in out)


def offline(check):
    print("-- А5.1: restart_stack.py на подменах (отсчёт в игре, --stop-only, текст Discord)")
    _rs_offline(check)
    print("-- А5.1: операции стойки на подменах")
    _ops_offline(check)
    _static_offline(check)


# ------------------------------------------------------------------------------------------------ adm.job на LocalDB
def sandbox(check, ldb):
    from core import audit, auth, config, db, jobs, ops, sched
    from domains import stack
    import pyodbc
    name = "AsdaAdminJobTest_" + secrets.token_hex(4)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    cfg = config.get()
    saved = (stack.RUN, stack.COUNTS, stack.EXPECT, cfg.on_server, auth.totp_confirm)
    try:
        cn = ldb(name)
        for f in ("adminc_02_schema.sql", "adminc_14_jobs.sql", "adminc_14_jobs.sql"):
            text = open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()
            for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
                if batch.strip():
                    cn.cursor().execute(batch)
        cn.close()
        check("adminc_14 на LocalDB дважды (повторный запуск безопасен, без пользователя asda_admin — выдача прав пропущена)", True)
        db.set_override("admin", lambda database: ldb(name))
        stack.EXPECT = dict(FULL)
        cfg.on_server = False
        cur = {"c": dict(FULL)}
        stack.COUNTS = lambda: cur["c"]
        runs = []

        def run_ok(argv, env, log):
            runs.append(argv[2:])
            return 0, "   все процессы стойки остановлены\nИТОГ: стойка поднята, патчи стоят\n"
        stack.RUN = run_ok
        cli = ops.Ctx(None, "cli:test@pc", "owner", "", "cli")
        now = jobs.utc_now()

        # взаимоисключение
        j1 = jobs.begin_direct("stack.restart", {}, "cli:a", None, "owner")
        locked = None
        try:
            jobs.begin_direct("stack.stop", {}, "cli:b", None, "owner")
        except jobs.JobLocked as ex:
            locked = ex.other
        check("adm.job: второе прямое управление стойкой при идущем — JobLocked с номером идущего (уникальный индекс)", locked == j1, locked)
        try:
            ops.run(cli, "stack.restart", {"confirm": "restart"})
            r_lock = False
        except ops.OpRefused as ex:
            r_lock = ("№%d" % j1) in str(ex)
        check("adm.job: операция стойки при идущем управлении — отказ «уже идёт … задание №N», restart_stack не запускался", r_lock and not runs)
        aid = jobs.add("live.announce", {"text": "x"}, "service", now, "", "", "cli:x", None, "owner")
        check("adm.job: не-стоечное задание running не мешает (индекс — только stack.*)", bool(jobs.claim("service", now + datetime.timedelta(seconds=1), "h")))
        jobs.finish(aid, "done", "ok")
        try:
            ops.run(cli, "job.release", {"id": j1})
            rel_need = False
        except ops.OpRefused as ex:
            rel_need = "--confirm-release" in str(ex)
        r = ops.run(cli, "job.release", {"id": j1, "confirm": "release"})
        check("job.release: без подтверждения — отказ, с ним — «снято вручную», строка failed", rel_need and jobs.get(j1)["status"] == "failed"
              and "снято вручную" in jobs.get(j1)["result"], r["message"])
        r = ops.run(cli, "stack.restart", {"confirm": "restart"})
        rows = jobs.list_jobs(5)
        check("прямой рестарт консолью: строка adm.job running → done с итогом, restart_stack с --no-deploy", runs == [["--no-deploy"]]
              and rows[0]["op"] == "stack.restart" and rows[0]["status"] == "done" and "готово" in rows[0]["result"])

        # job.add
        def refused(p, ctx=cli, part=""):
            try:
                ops.run(ctx, "job.add", p)
            except ops.OpRefused as ex:
                return part in str(ex)
            return False
        at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()
        check("job.add: рестарт без подтверждения — отказ «--confirm-restart»", refused({"op": "stack.restart", "at": at}, part="--confirm-restart"))
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
        far = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=40)).isoformat()
        check("job.add: время в прошлом / дальше 31 дня / мусор — отказ", refused({"op": "stack.restart", "at": past, "params": {"confirm": "restart"}}, part="не раньше")
              and refused({"op": "stack.restart", "at": far, "params": {"confirm": "restart"}}, part="не позже")
              and refused({"op": "stack.restart", "at": "завтра", "params": {"confirm": "restart"}}, part="неверное время"))
        check("job.add: неверный повтор, операция не для заданий, неизвестная операция — отказ",
              refused({"op": "stack.restart", "at": at, "repeat": "hourly", "params": {"confirm": "restart"}}, part="повтор")
              and refused({"op": "char.move", "at": at}, part="не ставится") and refused({"op": "x.y", "at": at}, part="неизвестная"))
        adm = ops.Ctx(5, "adm1", "admin", "10.0.0.1", "web")
        check("job.add: администратор не ставит рестарт (нет права stack.control), объявление — может",
              refused({"op": "stack.restart", "at": at, "params": {"confirm": "restart"}}, adm, "нет права")
              and ops.run(adm, "job.add", {"op": "live.announce", "at": at, "params": {"text": "hello"}}, dry=True)["ok"])
        check("job.add: объявление длиннее 95 байт — отказ при постановке (без опроса моста)",
              refused({"op": "live.announce", "at": at, "params": {"text": "я" * 96}}, adm, "длиннее"))
        web = ops.Ctx(1, "owner1", "owner", "10.0.0.1", "web")
        check("job.add из браузера для стойки без кода второго фактора — отказ", refused({"op": "stack.stop", "at": at, "params": {"confirm": "stop"}}, web,
                                                                                     "второго фактора"))
        seen = []

        def fake_totp(uid, code):                 # подмена проверки кода: верен только 123456
            seen.append((uid, code))
            if code != "123456":
                raise auth.AuthError("код второго фактора не подошёл (нужен свежий код из приложения)")
        auth.totp_confirm = fake_totp
        check("job.add из браузера: неверный код — отказ (проверка кода — при применении, не при предпросмотре)",
              refused({"op": "stack.stop", "at": at, "params": {"confirm": "stop"}, "totp": "000000"}, web, "не подошёл"))
        r = ops.run(web, "job.add", {"op": "stack.stop", "at": at, "params": {"confirm": "stop", "totp": "111"}, "totp": "123456", "repeat": "weekly"})
        jid = r["result"]["job"]
        j = jobs.get(jid)
        check("job.add из браузера: верный код — задание pending, исполнитель pc, в params нет кода второго фактора, автор и роль записаны",
              j["status"] == "pending" and j["runner"] == "pc" and j["params"] == {"confirm": "stop"} and j["created_uid"] == 1
              and j["created_role"] == "owner" and j["repeat_mode"] == "weekly" and (1, "123456") in seen, j)
        cn = ldb(name)
        cn.cursor().execute("INSERT adm.users (login, role, pw_hash, pw_salt, pw_iter) VALUES ('owner1', 'owner', 0x00, 0x00, 1)")
        uid1 = cn.cursor().execute("SELECT id FROM adm.users WHERE login = 'owner1'").fetchone()[0]
        cn.cursor().execute("UPDATE adm.job SET created_uid = ? WHERE id = ?", uid1, jid)
        cn.close()

        # исполнитель ПК: наступило → выполнено → повтор
        run_at = jobs.get(jid)["run_at"]
        cur["c"] = dict(FULL)
        stops = []

        def run_stop(argv, env, log):
            stops.append(argv[2:])
            cur["c"] = {}
            return 0, "   все процессы стойки остановлены\nИТОГ: стойка остановлена (--stop-only)\n"
        stack.RUN = run_stop
        out = jobs.run_due("pc", now=run_at + datetime.timedelta(seconds=30))
        nxt = [x for x in jobs.list_jobs(20) if x.get("prev_id") == jid]
        check("исполнитель ПК: наступившее задание взято и выполнено от имени автора (via job): остановка --stop-only, статус done, следующее через неделю",
              out and out[-1][:2] == (jid, "done") and stops == [["--stop-only"]] and jobs.get(jid)["status"] == "done"
              and nxt and nxt[0]["status"] == "pending" and nxt[0]["run_at"] == run_at + datetime.timedelta(days=7), (out, nxt[:1]))
        acts = [r["action"] for r in audit.query(limit=20)]
        check("журнал: постановка (job.add) и выполнение (stack.stop) — записи adm.audit", "job.add" in acts and "stack.stop" in acts, acts[:6])

        # пропуск просроченного
        stops.clear()
        late = jobs.add("stack.restart", {"confirm": "restart"}, "pc", now - datetime.timedelta(minutes=20), "daily", "", "cli:x", None, "owner")
        out = jobs.run_due("pc", now=now)
        nxt = [x for x in jobs.list_jobs(30) if x.get("prev_id") == late]
        check("просроченное больше 10 мин — «пропущено», restart_stack не запускается, повтор daily — на завтра в то же время",
              (late, "missed", "") in out and not stops and jobs.get(late)["status"] == "missed" and nxt
              and nxt[0]["run_at"] == now - datetime.timedelta(minutes=20) + datetime.timedelta(days=1), out)
        ops.run(cli, "job.cancel", {"id": nxt[0]["id"]})
        for x in jobs.list_jobs(50, active=True):
            if x["status"] == "pending":
                jobs.cancel(x["id"])

        # занятая стойка — задание ждёт
        busy = jobs.begin_direct("stack.restart", {}, "cli:busy", None, "owner")
        due = jobs.add("stack.restart", {"confirm": "restart"}, "pc", now, "", "", "cli:x", None, "owner")
        out = jobs.run_due("pc", now=now + datetime.timedelta(seconds=5))
        check("стойка занята прямым запуском — задание не взято, остаётся ждать (pending)", not out and jobs.get(due)["status"] == "pending", out)
        jobs.finish(busy, "done", "x")
        jobs.cancel(due)

        # автор отключён / лишился права
        cn = ldb(name)
        cn.cursor().execute("UPDATE adm.users SET disabled = 1 WHERE id = ?", uid1)
        cn.close()
        dis = jobs.add("stack.restart", {"confirm": "restart"}, "pc", now, "", "", "owner1", uid1, "owner")
        stops.clear()
        out = jobs.run_due("pc", now=now + datetime.timedelta(seconds=5))
        check("автор задания отключён — отказ, restart_stack не запускается", out and out[-1][1] == "refused" and "отключён" in out[-1][2] and not stops, out)
        cn = ldb(name)
        cn.cursor().execute("UPDATE adm.users SET disabled = 0, role = 'admin' WHERE id = ?", uid1)
        cn.close()
        dem = jobs.add("stack.restart", {"confirm": "restart"}, "pc", now, "", "", "owner1", uid1, "owner")
        out = jobs.run_due("pc", now=now + datetime.timedelta(seconds=5))
        check("автор задания стал администратором — отказ «больше нет права stack.control» (роль — текущая, не записанная)",
              out and out[-1][:2] == (dem, "refused") and "stack.control" in out[-1][2] and not stops, out)

        # служба: объявление с подменённым исполнителем; задания ПК служба не берёт
        called = []
        sj = jobs.add("live.announce", {"text": "hi"}, "service", now, "", "", "cli:x", None, "owner")
        pj = jobs.add("stack.restart", {"confirm": "restart"}, "pc", now, "", "", "cli:x", None, "owner")
        out = jobs.run_due("service", now=now + datetime.timedelta(seconds=5),
                           runner=lambda ctx, n, p: called.append((ctx.via, n, p)) or {"message": "разослано", "audit_id": 9})
        check("служба: берёт только свои задания (объявление), автор — via job, номер задания в params; задание ПК остаётся ждать",
              called == [("job", "live.announce", {"text": "hi", "job_id": sj})] and jobs.get(sj)["status"] == "done"
              and jobs.get(sj)["audit_id"] == 9 and jobs.get(pj)["status"] == "pending", (called, out))
        ops.run(cli, "job.cancel", {"id": pj})
        try:
            ops.run(cli, "job.cancel", {"id": pj})
            twice = False
        except ops.OpRefused as ex:
            twice = "уже не ждёт" in str(ex)
        check("job.cancel: ждущее — отменено, повторная отмена — отказ «уже не ждёт»", jobs.get(pj)["status"] == "cancelled" and twice)
        saved_q = list(sched._jobs_quiet)

        def bad(runner, now=None):
            raise db.DbError("AsdaAdmin: нет связи")
        got = sched.jobs_once(run_due=bad)
        check("служба: журнал заданий недоступен — проход возвращает пусто, поток не падает", got == [] and sched._jobs_quiet == [True])
        sched._jobs_quiet[:] = saved_q
        check("время: ISO с поясом из браузера → UTC; без пояса — местное время машины → UTC",
              jobs.parse_at("2026-11-21T06:00:00Z") == datetime.datetime(2026, 11, 21, 6, 0)
              and jobs.parse_at("2026-11-21T09:00:00+03:00") == datetime.datetime(2026, 11, 21, 6, 0)
              and jobs.parse_at("2026-11-21 06:00") == datetime.datetime(2026, 11, 21, 6, 0).astimezone().astimezone(datetime.timezone.utc).replace(tzinfo=None))
        auth.totp_confirm = saved[4]               # настоящая проверка кода — для р41 С-1
        _sandbox_r41(check, ldb, name, cli, now)
    except pyodbc.Error as ex:
        check("adm.job на LocalDB", False, ex)
    finally:
        stack.RUN, stack.COUNTS, stack.EXPECT, cfg.on_server, auth.totp_confirm = saved
        db.set_override("admin", None)
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
        except pyodbc.Error:
            pass
        m.close()


def _sandbox_r41(check, ldb, name, cli, now):
    """★ ревизия 41 на LocalDB: В-1 (рестарт набора под adm.job), С-1 (предел неверных кодов), Н-3 (срок повтора), Н-5 (машина постановки)."""
    from core import auth, jobs, ops
    from domains import shopcs, stack
    for x in jobs.list_jobs(100, active=True):                     # чистый лист
        if x["status"] == "running":
            jobs.finish(x["id"], "done", "x")
        else:
            jobs.cancel(x["id"])
    # В-1: идёт управление стойкой → рестарт набора не начинается; идёт рестарт набора → stack.* и задания не начинаются
    busy = jobs.begin_direct("stack.restart", {}, "cli:busy", None, "owner")
    entered = []
    try:
        with shopcs._stack_lock(cli, 77, "выкладка"):
            entered.append(1)
        r1 = False
    except ops.OpRefused as ex:
        r1 = ("№%d" % busy) in str(ex) and "объявления не было" in str(ex)
    jobs.finish(busy, "done", "x")
    with shopcs._stack_lock(cli, 77, "выкладка") as g:
        row = jobs.running_stack()
        try:
            ops.run(cli, "stack.restart", {"confirm": "restart"})
            r2 = False
        except ops.OpRefused as ex:
            r2 = ("№%d" % row["id"]) in str(ex)
        due = jobs.add("stack.restart", {"confirm": "restart"}, "pc", now, "", "", "cli:x", None, "owner")
        r3 = not jobs.run_due("pc", now=now + datetime.timedelta(seconds=5)) and jobs.get(due)["status"] == "pending"
        g.status, g.text = "done", "набор №77: код 0"
    jobs.cancel(due)
    fin = jobs.get(row["id"])
    check("р41 В-1: рестарт набора (shopcs._stack_lock) при идущем управлении стойкой — отказ до объявления; во время рестарта набора stack.restart "
          "и задание стойки не начинаются; строка «stack.changeset» закрыта итогом", r1 and not entered and r2 and r3 and row["op"] == "stack.changeset"
          and fin["status"] == "done" and fin["result"] == "набор №77: код 0", (r1, r2, r3, row, fin))
    src = open(shopcs.__file__, encoding="utf-8").read()
    check("р41 В-1: выкладка и откат серверной половины набора идут внутри _stack_lock (оба места)", src.count("with _stack_lock(ctx, cs[\"id\"],") == 2)
    with shopcs._stack_lock(cli, 78, "откат") as g:
        try:
            with shopcs._stack_lock(cli, 79, "выкладка"):
                pass
            r4 = False
        except ops.OpRefused:
            r4 = True
        raise_ok = True
    check("р41 В-1: вложенный рестарт набора при идущем — отказ; строка без явного итога закрывается failed («прервано до итога»)",
          r4 and raise_ok and jobs.list_jobs(3)[0]["status"] == "failed", jobs.list_jobs(3)[0]["status"])

    # С-1: предел неверных кодов второго фактора (настоящая auth.totp_confirm, ключ шифрования — подмена)
    saved_key = auth._totp_key
    auth._totp_key = lambda: b"k" * 32
    auth._confirm_fails.clear()
    try:
        secret = auth.totp_new_secret()
        cn = ldb(name)
        cn.cursor().execute("INSERT adm.users (login, role, pw_hash, pw_salt, pw_iter, totp_enc, totp_on) VALUES ('tf1', 'owner', 0x00, 0x00, 1, ?, 1)",
                            auth.totp_seal(secret))
        uid = cn.cursor().execute("SELECT id FROM adm.users WHERE login = 'tf1'").fetchone()[0]
        cn.close()
        import time as _time
        good = auth.totp_code(secret, int(_time.time() // auth.TOTP_STEP))
        bad = "000000" if good != "000000" else "111111"
        res = []
        for _ in range(5):
            try:
                auth.totp_confirm(uid, bad)
                res.append("ok")
            except auth.AuthError as ex:
                res.append("закрыто" if "закрыто" in str(ex) else "неверный")
        try:
            auth.totp_confirm(uid, good)
            after_lock = "ok"
        except auth.AuthError as ex:
            after_lock = "закрыто" if "закрыто" in str(ex) else str(ex)
        auth._confirm_fails.clear()
        try:
            auth.totp_confirm(uid, good)
            fresh = "ok"
        except auth.AuthError as ex:
            fresh = str(ex)
        try:
            auth.totp_confirm(uid, good)
            replay = "ok"
        except auth.AuthError as ex:
            replay = "не подошёл" if "не подошёл" in str(ex) else str(ex)
        auth._confirm_fails.clear()
        auth._confirm_fails[int(uid)] = [0, 0.0, [_time.time()] * auth.CONFIRM_RATE]    # уже CONFIRM_RATE попыток за минуту
        rate = []
        try:
            auth.totp_confirm(uid, bad)
        except auth.AuthError as ex:
            rate.append("много" if "слишком много" in str(ex) else str(ex))
        check("р41 С-1: 5 неверных кодов подряд — подтверждение закрыто на 15 мин (и верный код отклоняется); верный код после снятия — принят, "
              "повтор того же кода — отказ (одноразовый); больше 10 попыток в минуту — отказ «слишком много»",
              res == ["неверный"] * 5 and after_lock == "закрыто" and fresh == "ok" and replay == "не подошёл"
              and rate == ["много"], (res, after_lock, fresh, replay, rate))
    finally:
        auth._totp_key = saved_key
        auth._confirm_fails.clear()

    # Н-3: срок повтора
    j = jobs.add("live.announce", {"text": "x"}, "service", now - datetime.timedelta(minutes=20), "daily", "", "cli:x", None, "owner")
    lim = jobs.get(j)["repeat_until"]
    cn = ldb(name)
    cn.cursor().execute("UPDATE adm.job SET repeat_until = run_at WHERE id = ?", j)
    cn.close()
    jobs.run_due("service", now=now, runner=lambda c, n, p: {"message": "x"})
    nxt = [x for x in jobs.list_jobs(50) if x.get("prev_id") == j]
    check("р41 Н-3: повтор ставится только до repeat_until (31 день от первого запуска): за сроком — следующего нет",
          lim == now - datetime.timedelta(minutes=20) + datetime.timedelta(days=31) and jobs.get(j)["status"] == "missed" and not nxt, (lim, nxt))
    # Н-5: задание консоли с другой машины
    k = jobs.add("live.announce", {"text": "x"}, "service", now, "", "", "cli:evil@srv", None, "owner")
    cn = ldb(name)
    cn.cursor().execute("UPDATE adm.job SET created_host = N'OTHER-HOST' WHERE id = ?", k)
    cn.close()
    called = []
    out = jobs.run_due("service", now=now + datetime.timedelta(seconds=5), runner=lambda c, n, p: called.append(n) or {"message": "x"})
    check("р41 Н-5: задание «cli:…», поставленное на другой машине, не исполняется (отказ «другой машине»), операция не зовётся",
          out and out[-1][:2] == (k, "refused") and "другой машине" in out[-1][2] and not called, out)


# ------------------------------------------------------------------------------------------------ живой
PROBE = r'''# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
from domains import load_all
load_all()
from core import jobs, ops
from domains import stack
n = len(jobs.list_jobs(5, active=False))
s = stack.schedulable(ops.Ctx(None, "probe", "owner", "", "web"))
print("PROBE_JOBS ok=1 rows=%d sched=%s" % (n, ",".join(sorted(x["op"] for x in s))))
'''


def live(check):
    """Только чтение стойки и запись в СВОЮ базу AsdaAdmin (задание объявления на +30 дней — тут же отменяется)."""
    import subprocess
    from core import config, db, jobs, ops
    from domains import load_all, stack
    load_all()      # ★ А7.11 (24.11): job.add ниже ставит live.announce — без загрузки разделов её нет в реестре («неизвестная операция»), как у службы и консоли
    if config.get().on_server:
        return check("живой самотест А5.1 — с ПК (SSH)", True)
    s = stack.state()
    check("живая стойка А5.1: счёт процессов прочитан по SSH, стойка полная по stack_layout.EXPECT (все копии GameServer / NpcServer / Relay)",
          s["counts"] is not None and s["complete"], s["text"])
    cn = db.admin()
    try:
        perm = db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME('adm.job','OBJECT','INSERT') AS i, HAS_PERMS_BY_NAME('adm.job','OBJECT','DELETE') AS d, "
                                 "(SELECT COUNT(*) FROM sys.indexes WHERE name = 'UX_adm_job_stack_running') AS ux, "
                                 "CASE WHEN COL_LENGTH('adm.job', 'repeat_until') IS NOT NULL AND COL_LENGTH('adm.job', 'created_host') IS NOT NULL "
                                 "THEN 1 ELSE 0 END AS r41")[0]
    finally:
        cn.close()
    check("живая AsdaAdmin: adm.job есть, asda_admin — INSERT да, DELETE нет, уникальный индекс взаимоисключения на месте",
          perm["i"] == 1 and perm["d"] == 0 and perm["ux"] == 1, perm)
    check("живая AsdaAdmin (р41): у adm.job есть repeat_until (срок повтора) и created_host (машина постановки)", perm["r41"] == 1, perm)
    cli = ops.Ctx(None, "cli:selftest@pc", "owner", "", "cli")
    at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
    jid = None
    try:
        r = ops.run(cli, "job.add", {"op": "live.announce", "at": at, "params": {"text": "selftest A5.1 (cancelled at once)"},
                                     "note": "самотест А5.1: отменяется сразу"})
        jid = r["result"]["job"]
        ops.run(cli, "job.cancel", {"id": jid})
        j = jobs.get(jid)
        check("живая AsdaAdmin: задание объявления на +30 дней поставлено и сразу отменено (cancelled), исполнитель — служба",
              j["status"] == "cancelled" and j["runner"] == "service", j)
    finally:
        if jid:
            jobs.cancel(jid)
    try:
        prev = ops.run(cli, "stack.restart", {"confirm": "restart"}, dry=True)["preview"]
        ok = "--no-deploy" in prev["text"] and any("Beta Tester" in w for w in prev["warnings"])
    except ops.OpRefused as ex:
        prev, ok = str(ex), False
    check("живой сухой предпросмотр рестарта (ничего не запускается): restart_stack.py --no-deploy, объявление Discord, счёт процессов", ok, prev)
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH")
    ssh = os.path.join(exe, "ssh.exe") if os.path.isdir(exe) else "ssh"
    try:
        p = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                            r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=PROBE.encode("utf-8"), capture_output=True, timeout=300)
        out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"PROBE_JOBS ok=1 rows=(\d+) sched=(\S*)", out)
    # ★ А5.9 (21.11): с А5.3 / А5.4 / А5.7 в задания ставятся и maint.*, event.*, rank.recalc, daily.reset, db.backup — список службы сверяется
    #   со списком этого же кода (тот же REGISTRY), обязательные — live.announce и stack.*; удаление копий db.bakdrop заданием не ставится
    from core import ops as _ops
    from domains import load_all as _la, stack as _st
    _la()
    want = sorted(x["op"] for x in _st.schedulable(_ops.Ctx(None, "probe", "owner", "", "web")))
    got = mm.group(2).split(",") if mm else []
    check("служба на сервере (код службы, SSH): adm.job читается, список операций заданий = коду (live.announce, stack.restart/stop/start есть, "
          "db.bakdrop нет)", bool(mm) and got == want and {"live.announce", "stack.restart", "stack.start", "stack.stop"} <= set(got)
          and "db.bakdrop" not in got, (got, want, out[-300:]))
