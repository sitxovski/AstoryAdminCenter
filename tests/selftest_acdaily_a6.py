# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_acdaily_a6.py — самотест шага А6.6 «Античит: суточный отчёт» (22.11.2026; domains/acdaily.py, domains/acdaily_en.py,
sql/adminc_19_acdaily.sql, /api/acdaily/*, web/acdaily.js, консоль acdaily, операция ac.daily, core/sched DAILY).

offline(check)  — исходник: его --selftest зелёный, код берётся без правок (md5), белый список = каналам, которые читает исходник;
                  ПОВЕДЕНИЕ ТО ЖЕ: синтетические журналы стойки (фиксированные сутки 05.01.2026, от часов запуска не зависит) — Markdown
                  панели (частная копия, open белого списка, общий доступ) построчно равен Markdown исходника, посчитанному обычным импортом
                  в отдельном процессе (без базы, как --no-db), кроме строки шапки со временем; файл занят писателем (share 0) — у обоих
                  статус метрики «ошибка», нет папки журнала — у обоих «событий нет»; пороги прогона частные (не задевают правило M3
                  «Передач» и следующий прогон); open вне белого списка / не «rb» — отказ; отказы ввода до журналов и базы (без «; »);
                  права ac.view / ac.daily_run, маршруты, операция и планировщик (00:20 после снимка золота 00:05, до 00:20 не
                  запускается), только служба на сервере, переводы (панель — core/i18n без перехватов, отчёт — acdaily_en без русских
                  букв), веб без innerHTML, консоль, выкладка, импорт без побочных эффектов.
sandbox(check, ldb) — СВОИ базы LocalDB: AsdaAdmin (adminc_02 + adminc_19 дважды), JoyLog1 (Trade*, LogInfo, ac.* и представления), Joy1
                  (Item, Del_item). Операция ac.daily: запись в adm.AcDaily, журнал adm.audit, отчёт / события / Markdown читаются, M3 / M4 /
                  M8 / ACJ по базе (все запросы проходят обе проверки «только чтение»), бюджет ручных прогонов, служба вне бюджета, один
                  прогон за раз, право ac.daily_run, EN-вид без русских букв.
live(check)     — живая dev: права asda_admin на adm.AcDaily (SELECT / INSERT да, UPDATE / DELETE нет), прогоны читаются, последний прогон
                  службы посчитан тем же кодом, что исходник на ПК (md5), предпросмотр на сервере по SSH (--dry, без записи), записей
                  живой прогон не добавляет, /api/acdaily/* без входа — 401.
Побочных эффектов при импорте нет.
"""
import copy
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
CYR = re.compile("[А-Яа-яЁё]")
DAY = datetime.date(2026, 1, 5)          # сутки синтетики (фиксированы: самотест не зависит от часов запуска)
TODAY = datetime.date(2026, 1, 6)
GS = ["GameServer", "Indun_GameServer", "Ch2_GameServer"]
NPC = ["NpcServer", "Indun_NpcServer", "Ch2_NpcServer"]
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _refused(fn):
    """Текст отказа OpRefused или None."""
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


def write_logs(root):
    """Синтетические журналы стойки за DAY (и сутки до — сессия через полночь): cp1251, CRLF — как пишет сток."""
    def w(rel, lines):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(("\r\n".join(lines) + "\r\n").encode("cp1251"))
    pre = lambda d, hh, mm, ss: "01 Mon %02d Day %02d hou %02d min %02d sec : " % (d, hh, mm, ss)
    w("GameServer/Log/Log_Game/GameLog_20260105.txt",
      [pre(5, 10, m, 0) + "CharMove Hack Position Cheater Error" for m in range(0, 6)] +
      [pre(5, 11, 0, 0) + "CharReMove Hack Position GM_sitxovski Error",
       pre(5, 11, 1, 0) + "___ExceptionDisConnetUser___ CallFunc = CharMove(), UserNum = 3, CharN = Cheater, IP = 10.0.0.5",
       pre(5, 11, 2, 0) + "___ExceptionDisConnetUser___ CallFunc = Ping TimeOut, UserNum = 4, CharN = Quiet, IP = 10.0.0.6"])
    w("Ch2_GameServer/Log/Log_Game/GameLog_20260105.txt", [pre(5, 12, m, 0) + "CharMove Hack Position Runner Error" for m in range(0, 3)])
    # ★ ревизия 56 (мелочь 4): имя без «_» перед датой — index_dir исходника его читает, белый список панели тоже должен
    w("GameServer/Log/Log_Game/Extra20260105.txt", [pre(5, 12, 30, 0) + "CharMove Hack Position Odd Error"])
    w("GameServer/Log/Log_Secret/Secret_20260105.txt", [pre(5, 12, 0, 0) + "\t123\tCheater\tSecret Error\tUser 1, Server 2, CharMove()"])
    w("GameServer/Log/Log_Exception_Asm/AsmLog_20260105.txt", [pre(5, 12, 5, 0) + "memcmp(szMD5, x) Command = 4321",
                                                                pre(5, 12, 6, 0) + "hack packet from client"])
    w("GameServer/Log/Log_Item/ItemLog_20260105.txt", [pre(5, 12, 7, 0) + "ItemMove Failed, 77 slot", pre(5, 12, 8, 0) + "Refine Error ok"])
    w("GameServer/Log/Log_SpeedHack/SpeedHack_20260105.txt", [pre(5, 9, 0, s) + "\tWarning\t1000/2000\t" for s in range(3)] +
      [pre(5, 9, 1, 0) + "\tHackCheck\t1000/1500\tSpeedy", pre(5, 9, 1, 1) + "\tWarning\t1000/1600\tSpeedy"])
    w("GameServer/Log/Log_LevelUp/LevelUp_20260104.txt", [pre(4, 23, 0, 0) + "CUserManager::CharLogonRes1\tCharName\tNight\tLevel\t3\tExp\t10"])
    w("GameServer/Log/Log_LevelUp/LevelUp_20260105.txt",
      [pre(5, 1, 0, 0) + "CUserManager::CharLogonRes1\tCharName\tBotty\tLevel\t5\tExp\t100",
       pre(5, 1, 30, 0) + "CUserManager::DisConnectUser\tCharName\tNight\tLevel\t3\tExp\t4000",
       pre(5, 10, 0, 0) + "CUserManager::DisConnectUser\tCharName\tBotty\tLevel\t6\tExp\t90100",
       pre(5, 10, 1, 0) + "CUserManager::CharPortalLogonRes1\tCharName\tBotty\tLevel\t6\tExp\t90100",
       pre(5, 10, 30, 0) + "CUserManager::DisConnectUser\tCharName\tBotty\tLevel\t6\tExp\t95100"] +
      [pre(5, 13, i, 0) + "CUserManager::CharLogonRes1\tCharName\tPeer%d\tLevel\t5\tExp\t0" % i for i in range(6)] +
      [pre(5, 14, i, 0) + "CUserManager::DisConnectUser\tCharName\tPeer%d\tLevel\t5\tExp\t%d" % (i, 1000 * (i + 1)) for i in range(6)])
    w("GameServer/Log/Log_Operator/OperatorLog_20260105.txt",
      [pre(5, 9, 0, 0) + "Recv_OperatorCommand_ItemGive() Give OK UserID = GM_sitxovski, 2 -> UserID = Stranger, 77, Code = 20551, iAmount = 3",
       pre(5, 9, 5, 0) + "Recv_OperatorCommand_Kick() UserID = Mallory, 9, target x", pre(5, 9, 6, 0) + "Send_HideCommand() UserID = GM_sitxovski, 2"])
    w("GameServer/Log/Login/Login_Check_20260105.txt", [pre(5, 8, 0, 0) + "x -> GM_LOGON_REQ", pre(5, 8, 1, 0) + "y -> GM_LOGON_REQ"])
    w("NpcServer/Error_Log/SpeedHack_20260105.txt",
      ["%d\t10:00:%02d:000->SpeedHack Check....!\tNick \tFast\tCount %d\tPDuration 1000\tDuration 500" % (i, i, 20 + i) for i in range(12)])
    w("LoginManager/Log/LoginMngError/OTP_Report_20260105.txt",
      [pre(5, 8, 0, i) + "Login User ID u1/u1, Pass " + "a" * 32 + "/" + "b" * 32 + "00-15-5d-a3-01-00, IP 10.0.0.9" for i in range(6)] +
      [pre(5, 8, 0, 10 + i) + "u1 UPUserLogin result : iUserLoginStatus 3" for i in range(6)] +
      [pre(5, 8, 5, 0) + "Login User ID u2/u2, Pass x, IP 10.0.0.9", pre(5, 8, 5, 1) + "u2 UPUserLogin result : iUserLoginStatus 4",
       pre(5, 8, 6, 0) + "Login User ID u3/u3, Pass x, IP 10.0.0.9", pre(5, 8, 6, 1) + "u3 UPUserLogin result : iUserLoginStatus 1"])
    w("LoginManager/Log/LoginMngError/LoginoutCheck_20260105.txt",
      [pre(5, 8, 10, 0) + "UserNum 5 Disconnect_PingCount() : pCallFunc = GetMD5_Cmp, Count 3",
       pre(5, 8, 11, 0) + "UserNum 6 Disconnect_PingCount() : pCallFunc = Ping, Count 9"])
    w("LoginManager/Log/LoginMngError/LoginProc_20260105.txt",
      [pre(5, 8, 12, 0) + "[LOGIN] Failed Count UserID = bob, x", pre(5, 8, 13, 0) + "ProcConnect = 1, 10.0.0.7",
       pre(5, 8, 14, 0) + "Overlap User Error UserID = bob"])


SRC_RUN = r'''# -*- coding: utf-8 -*-
import datetime, sys
sys.path.insert(0, sys.argv[1])
import ac_common as C, ac_metrics_logs as L, ac_daily_report as R
d = datetime.date(2026, 1, 5)
ctx = C.Ctx(sys.argv[2], d, d, sys.argv[3], C.DEFAULT_OWNER_RE, %r, %r, sys.argv[4] if len(sys.argv) > 4 else "", False)
ms = R.build(C, L, ctx)
open(sys.argv[3], "w", encoding="utf-8", newline="\n").write(R.render(C, ctx, ms, {"elapsed": 0.0}))
''' % (GS, NPC)


def source_md(root, out, archive=""):
    """Markdown исходника (обычный импорт AstoryServer/Tools/Anticheat, отдельный процесс, без базы) по журналам root → текст."""
    from domains import acdaily as A
    script = os.path.join(os.path.dirname(out), "src_run.py")
    open(script, "w", encoding="utf-8").write(SRC_RUN)
    p = subprocess.run([sys.executable, "-I", script, A.AC_SRC, root, out, archive], capture_output=True, timeout=180, stdin=subprocess.DEVNULL)
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr).decode("utf-8", "replace")[-600:])
    return open(out, encoding="utf-8").read()


def _body(md):
    """Markdown без строки шапки «Сформирован …» (время и длительность прогона)."""
    return [x for x in md.splitlines() if not x.startswith("Сформирован ")]


def _status(md):
    """{метрика: статус} из раздела «Метрики» Markdown."""
    out, cur = {}, None
    for x in md.splitlines():
        m = re.match(r"^### (\S+) - ", x)
        if m:
            cur = m.group(1)
        m = re.match(r"^- Статус: \*\*(.+)\*\*$", x)
        if m and cur:
            out[cur] = m.group(1)
    return out


def _lock_share0(path):
    """Открыть файл как писатель без общего доступа (share 0) → дескриптор (Windows)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    h = k32.CreateFileW(path, 0x40000000, 0, None, 3, 0x80, None)
    return k32, h


def _cyr_view(rep):
    """Русские строки EN-вида отчёта (кроме данных журналов: субъекты-ники, файлы, IP) → список."""
    bad = []
    for m in rep["metrics"]:
        for k in ("title", "source", "formula", "status"):
            if CYR.search(str(m[k])):
                bad.append((m["mid"], k, m[k]))
        bad += [(m["mid"], "note", n) for n in m["notes"] if CYR.search(n)]
        bad += [(m["mid"], "summary", c) for c in m["summary"] if CYR.search(str(c))]
        bad += [(m["mid"], "flag", f[1]) for f in m["flags"] if CYR.search(f[1])]
        for t in m["tables"]:
            bad += [(m["mid"], "table", x) for x in [t[0]] + list(t[1]) if CYR.search(str(x))]
            bad += [(m["mid"], "cell", c) for r in t[2] for c in r if CYR.search(str(c))]
        bad += [(m["mid"], "event", e[2:5]) for e in m["last"] if CYR.search(" ".join(str(x) for x in e[2:5]))]
    return bad


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n, ops, sched
    from domains import acdaily as A, acdaily_en as AE, trade
    import domains
    domains.load_all()

    # ---- исходник: самотест, код без правок, белый список
    p = subprocess.run([sys.executable, "-I", os.path.join(A.AC_SRC, "ac_daily_report.py"), "--selftest"], capture_output=True, timeout=180,
                       stdin=subprocess.DEVNULL)
    so = p.stdout.decode("utf-8", "replace")
    check("суточный отчёт: --selftest исходника ac_daily_report.py зелёный (%d проверок)" % so.count("OK   "),
          p.returncode == 0 and "FAIL" not in so and so.count("OK   ") >= 19, so[-400:])
    check("суточный отчёт: на ПК исходник берётся из AstoryServer/Tools/Anticheat (не из копии), md5 — пяти файлов", A.src_dir() == A.AC_SRC
          and len(A.code_md5()) == 32 and set(A.AC_FILES) >= set(trade.AC_FILES))
    lg = open(os.path.join(A.AC_SRC, "ac_metrics_logs.py"), encoding="utf-8").read()
    chans = set(re.findall(r'gs_lines\(ctx, "(\w+)"', lg))
    lm = set(re.findall(r'"(\w+)_%s\.txt"', lg)) | set(re.findall(r'startswith\("(\w+)"\)', lg))
    check("суточный отчёт: белый список = тому, что читает исходник (каналы GameServer %s, LoginManager %s, NpcServer SpeedHack)"
          % (sorted(chans), sorted(lm - {"SpeedHack"})), chans == set(A.GS_CHANNELS) and lm == set(A.LM_FILES) | {"SpeedHack"}, (chans, lm))
    check("суточный отчёт: «служебные ≤ 5000» — как в исходнике: деления по номеру учётки нет, «фон» — только Ctx.is_owner (regex владельца)",
          "OPERATOR_MAX_UID" not in open(os.path.join(ROOT, "domains", "acdaily.py"), encoding="utf-8").read()
          and not any(re.search(r"(?<![\d.])5000(?![\d])", open(os.path.join(A.AC_SRC, f), encoding="utf-8").read()) for f in A.AC_FILES))
    dfl = A.defaults()
    sys.path.insert(0, A.AC_SRC)
    try:
        import importlib.util as _iu
        sp = _iu.spec_from_file_location("st_acd_common", os.path.join(A.AC_SRC, "ac_common.py"))
        cm = _iu.module_from_spec(sp)
        sp.loader.exec_module(cm)
    finally:
        sys.path.remove(A.AC_SRC)
    check("суточный отчёт: пороги по умолчанию = ac_common.THR исходника (%d ключей)" % len(dfl), dfl == cm.THR and len(dfl) > 10, dfl)

    # ---- поведение то же: синтетика, сверка с исходником
    tmp = tempfile.mkdtemp(prefix="acd_st_")
    saved = A.STACK_OVERRIDE
    try:
        root = os.path.join(tmp, "v2")
        write_logs(root)
        A.STACK_OVERRIDE = (root, GS, NPC, "")
        q = A.check_params({"date": "20260105"}, today=TODAY)
        rep = A.compute(q, with_db=False)
        src = source_md(root, os.path.join(tmp, "src.md"))
        b1, b2 = _body(src), _body(rep["md"])
        diff = [(i, a, b) for i, (a, b) in enumerate(zip(b1, b2)) if a != b]
        check("суточный отчёт: ПОВЕДЕНИЕ ТО ЖЕ — Markdown панели построчно равен Markdown исходника (%d строк, кроме шапки со временем)" % len(b1),
              b1 == b2 and len(b1) > 100, diff[:3] or (len(b1), len(b2)))
        by = {m["mid"]: m for m in rep["metrics"]}
        st = {k: v["status"] for k, v in by.items()}
        check("суточный отчёт: на синтетике сработали M1 M5 M6 M6b M7 M7d M8 M9 M11 M12 M12o; без базы M3 / M4 / ACJ — «нет данных» (как --no-db)",
              all(by[k]["events_total"] for k in ("M1", "M5", "M6", "M6b", "M7", "M7d", "M8", "M9", "M11", "M12", "M12o"))
              and st["M3"] == st["M4"] == st["ACJ"] == "нет данных" and not [k for k, v in st.items() if v == "ошибка"], st)
        fl = {m["mid"]: [(f[0], f[2]) for f in m["flags"]] for m in rep["metrics"]}
        check("суточный отчёт: флаги «вне / фон» — Ctx.is_owner исходника (Cheater, Fast, Speedy, Stranger, Mallory, Botty — вне; GM_sitxovski — фон)",
              ("Cheater", False) in fl["M5"] and ("Fast", False) in fl["M6"] and ("Speedy", False) in fl["M6b"] and ("Stranger", False) in fl["M11"]
              and ("Mallory", False) in fl["M11"] and ("Botty", False) in fl["M9"] and not any(s == "GM_sitxovski" for s, _o in fl["M5"])
              and rep["totals"]["out"] == sum(1 for v in fl.values() for _s, o in v if not o), fl)
        check("суточный отчёт: сессия через полночь — день до окна прочитан (Night 23:00 → 01:30), портал склеен (Botty 01:00 → 10:30 одна сессия)",
              any(e[2] == "Night" for e in by["M9"]["last"]) and sum(1 for e in A.compute(q, with_db=False)["events"]["M9"] if e[2] == "Botty") == 1)
        check("суточный отчёт: файлов прочитано через белый список %d, журналов окна %d (%d байт), без запросов к базе" % (
            rep["meta"]["opened"], rep["meta"]["log_files"], rep["meta"]["log_bytes"]),
              rep["meta"]["opened"] >= 12 and rep["meta"]["log_files"] == 15 and rep["meta"]["queries"] == 0
              and any(e[2] == "Odd" for e in rep["events"]["M5"]), rep["meta"])
        check("суточный отчёт: в отчёте и событиях нет хешей паролей OTP_Report", ("a" * 32) not in rep["md"] and ("a" * 32) not in str(rep["events"]))
        # пороги прогона — частные
        q2 = A.check_params({"date": "20260105", "thr": {"m5_burst_n": "7"}}, today=TODAY)
        r2 = A.compute(q2, with_db=False)
        m3_thr = trade.m3().COMMON.THR
        r3 = A.compute(q, with_db=False)
        n5 = lambda r: sum(1 for m in r["metrics"] if m["mid"] == "M5" for f in m["flags"] if "серия" in f[1])
        check("суточный отчёт: пороги прогона частные — m5_burst_n=7 убирает серию Cheater, следующий прогон с прежними — серия есть, правило M3 "
              "«Передач» не задето", n5(rep) == 1 and n5(r2) == 0 and n5(r3) == 1 and q2["over"] == {"m5_burst_n": 7}
              and m3_thr["m5_burst_n"] == 5 and r2["meta"]["thr"]["m5_burst_n"] == 7, (n5(rep), n5(r2), n5(r3)))
        # нет папки журнала / файл занят
        shutil.rmtree(os.path.join(root, "GameServer", "Log", "Log_Secret"))
        rs = A.compute(q, with_db=False)
        ss = _status(source_md(root, os.path.join(tmp, "src2.md")))
        check("суточный отчёт: нет папки журнала (Log_Secret) — метрика считается дальше без него, статусы = исходнику", _status(rs["md"]) == ss
              and not any(e[2] == "Cheater" and e[3].startswith("Secret") for e in rs["events"]["M7"]), (_status(rs["md"]), ss))
        if os.name == "nt":
            lp = os.path.join(root, "GameServer", "Log", "Log_Game", "GameLog_20260105.txt")
            k32, hnd = _lock_share0(lp)
            try:
                rb = A.compute(q, with_db=False)
                sb = _status(source_md(root, os.path.join(tmp, "src3.md")))
            finally:
                k32.CloseHandle(hnd)
            m5 = [m for m in rb["metrics"] if m["mid"] == "M5"][0]
            check("суточный отчёт: файл занят писателем без общего доступа — у панели и у исходника M5 / M7d «ошибка» (как сейчас: safe() исходника), "
                  "причина в заметке, остальные метрики считаются", _status(rb["md"]) == sb and sb["M5"] == "ошибка" and sb["M7d"] == "ошибка"
                  and any("занят" in n for n in m5["notes"]) and sb["M9"] != "ошибка", (sb, m5["notes"]))
        _r56_offline(check, A, root, tmp, q)
        _r57_offline(check, A, root, tmp, q)
        # open частной копии
        src_m = A.load(root, GS, NPC)
        g = src_m.guard
        bad = [_os_err(lambda: g.open(os.path.join(root, "GameServer", "Log", "Log_Frame", "Frame_20260105.txt"), "rb")),
               _os_err(lambda: g.open(os.path.join(root, "GameServer", "ConfigSet", "patches.ini"), "rb")),
               _os_err(lambda: g.open(os.path.join(tmp, "src.md"), "rb")),
               _os_err(lambda: g.open(os.path.join(root, "LoginManager", "Log", "LoginMngError", "OTP_Report_20260105.txt"), "r")),
               _os_err(lambda: g.open(os.path.join(root, "GameServer", "Log", "Log_Game", "..", "..", "..", "x_20260105.txt"), "rb"))]
        check("суточный отчёт: open частной копии — вне белого списка (Log_Frame, patches.ini, вне корня, «..»), не «rb» — отказ PermissionError",
              all(isinstance(x, PermissionError) for x in bad), bad)
        sp0 = list(sys.path)
        A.load(root, GS, NPC)
        check("суточный отчёт: частная копия не трогает sys.path и sys.modules (ac_common / ac_metrics_db правила M3 — прежние объекты)",
              not any(x.startswith("acdaily_src_") for x in sys.modules) and src_m.C is not trade.m3().COMMON and sys.path == sp0)
        check("суточный отчёт: подключение исходника к базе (пароль с сервера по SSH) в частной копии отключено",
              _exc(lambda: src_m.R.__dict__["__builtins__"]["__import__"]("db_connect").connect("Joy1")) is not None
              and "отключено" in str(_exc(lambda: src_m.R.__dict__["__builtins__"]["__import__"]("db_connect").read_password())))
        # EN-вид
        i18n.set_lang("en")
        try:
            v = AE.view(copy.deepcopy({"metrics": rep["metrics"]}))
            ev = AE.rows(rep["events"]["M9"] + rep["events"]["M1"] + rep["events"]["M6b"] + rep["events"]["M11"] + rep["events"]["M7"])
        finally:
            i18n.set_lang("ru")
        cb = _cyr_view(v)
        check("суточный отчёт EN: вид отчёта (названия, источники, формулы, статусы, заметки, итог, флаги, таблицы, события) без русских букв",
              not cb and not [e for e in ev if CYR.search(" ".join(str(x) for x in e[2:5]))], cb[:6])
    finally:
        A.STACK_OVERRIDE = saved
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- отказы ввода (до журналов и базы)
    bad_in = [{"date": "2026-01-05"}, {"date": "20261331"}, {"date": "20260107"}, {"days": 0}, {"days": 32}, {"days": "x"}, {"days": True},
              {"thr": {"nope": 1}}, {"thr": {"m5_burst_n": "1.5"}}, {"thr": {"m6_ratio": "0"}}, {"thr": {"m6_ratio": "nan"}},
              {"thr": {"m5_burst_n": True}}, {"thr": "m5=1"}, {"extra": 1}]
    why = [_refused(lambda p=p: A.check_params(p, today=TODAY)) for p in bad_in]
    check("суточный отчёт: неверный ввод — отказ до журналов и базы (%d случаев: дата, будущее, суток 1…31, пороги, лишний параметр)" % len(bad_in),
          all(why), [(bad_in[i], w) for i, w in enumerate(why) if not w])
    check("суточный отчёт: тексты отказов без «; »", all("; " not in w for w in why if w), [w for w in why if w and "; " in w])
    okq = A.check_params({"thr": {"m6_ratio": "0.5", "m9_session_h": 8}}, today=TODAY)
    check("суточный отчёт: без даты — вчера по часам сервера (подставлено today), пороги того же типа, «не прежние» — только отличные",
          okq["d1"] == DAY and okq["days"] == 1 and okq["thr"]["m6_ratio"] == 0.5 and okq["over"] == {"m6_ratio": 0.5}
          and isinstance(okq["thr"]["m9_session_h"], float))

    # ---- права, маршруты, операция, планировщик
    roles = ("owner", "admin", "gm", "support")
    check("суточный отчёт: просмотр ac.view (owner, admin, gm), прогон ac.daily_run (owner, admin)",
          {r for r in roles if auth.can(r, "ac.view")} == {"owner", "admin", "gm"} and {r for r in roles if auth.can(r, "ac.daily_run")} == {"owner", "admin"})
    paths = ("/api/acdaily/list", "/api/acdaily/report", "/api/acdaily/events", "/api/acdaily/md")
    rt = {x: _route(x) for x in paths}
    check("суточный отчёт: маршруты %s — GET, право ac.view" % ", ".join(paths), all(fn and perm == "ac.view" for fn, perm in rt.values()), rt)
    o = ops.REGISTRY.get("ac.daily")
    check("суточный отчёт: операция ac.daily — право ac.daily_run, задание службы (повтор на год), необратима",
          o and o.perm == "ac.daily_run" and o.schedule_runner == "service" and o.schedule_repeat_days == 366 and not o.reversible)
    dl = dict(sched.DAILY)
    check("суточный отчёт: служба считает сама раз в сутки — core/sched DAILY ac.daily 00:20 = RUN_AT, после снимка золота 00:05",
          dl.get("ac.daily") == A.RUN_AT == datetime.time(0, 20) and dl.get("econ.snapshot") == datetime.time(0, 5) and "camp.rank_rebuild" in dl)
    saved_daily = list(sched.DAILY)
    try:
        sched.DAILY[:] = [x for x in saved_daily if x[0] == "ac.daily"]
        sched._tried.clear()
        got = []
        r0 = sched.run_once(datetime.datetime(2026, 1, 6, 0, 15), last=lambda n: None, runner=lambda n: got.append(n) or {"message": "x"})
        sched._tried.clear()
        r1 = sched.run_once(datetime.datetime(2026, 1, 6, 0, 25), last=lambda n: None, runner=lambda n: got.append(n) or {"message": "x"})
        sched._tried.clear()
        r2 = sched.run_once(datetime.datetime(2026, 1, 6, 0, 30), last=lambda n: datetime.datetime(2026, 1, 6, 0, 25), runner=lambda n: got.append(n) or {})
    finally:
        sched.DAILY[:] = saved_daily
        sched._tried.clear()
    check("суточный отчёт: планировщик — до 00:20 не запускает, после — один раз, сделанный сегодня не повторяет",
          r0 == [] and r1 == [("ac.daily", "x")] and r2 == [] and got == ["ac.daily"], (r0, r1, r2, got))
    ctx = ops.Ctx(None, "selftest", "owner", "", "cli")
    saved = A.STACK_OVERRIDE
    try:
        A.STACK_OVERRIDE = None
        from core import config
        sv = _refused(lambda: o.preview(ctx, {})) if not config.get().on_server else "пропуск (на сервере)"
    finally:
        A.STACK_OVERRIDE = saved
    check("суточный отчёт: на ПК не считается — журналы стойки только у службы на сервере (шары нет)",
          sv and sv.startswith("суточный отчёт считает служба на сервере"), sv)

    # ---- SQL модуля
    srcpy = open(os.path.join(ROOT, "domains", "acdaily.py"), encoding="utf-8").read()
    code = re.sub(r'"""(?:[^"]|"(?!""))*"""', "", srcpy)
    lits = re.findall(r'"((?:SELECT|SET NOCOUNT|FROM|WHERE|INSERT)[^"]*)"', code)
    check("суточный отчёт: в тексте SQL модуля нет русских букв и «SELECT *»; запись — только INSERT adm.AcDaily (%d строк SQL)" % len(lits),
          lits and not any(CYR.search(s) or "select *" in s.lower() for s in lits) and sorted(set(re.findall(r"INSERT (\S+)", code))) == ["adm.AcDaily"],
          [s[:80] for s in lits if CYR.search(s)][:3])

    # ---- переводы панели
    i18n.set_lang("en")
    try:
        ru = [w for w in why if w] + [
            "суточный отчёт считает служба на сервере: журналы стойки читаются там локально (без шары) — запуск из панели или заданием планировщика (jobs add ac.daily)",
            "суточный отчёт вручную — не больше 4 раз в час на пользователя, подождите", "номер суточного отчёта — целое от 1", "суточного отчёта №7 нет",
            "суточных отчётов ещё нет (служба считает их сама в 00:20)", "суточного отчёта за 20260105 нет", "метрика отчёта — имя вида M1, M12o, ACJ",
            "строк на странице событий — от 1 до 500", "страница событий — целое от 1", "метрики M99 в отчёте №3 нет", "Античит: суточный отчёт",
            "пишется только база панели AsdaAdmin (adm.AcDaily), игровые базы и журналы стойки только читаются",
            "последние сутки окна ещё идут — отчёт за них неполный", "пороги не прежние: m5_burst_n=3, m6_ratio=0.5",
            "суточный отчёт уже считается — повторите через минуту", "журнал суточных отчётов не прочитан: AsdaAdmin: x",
            "суточный отчёт античита за 20260105: журналов стойки 13 (12 КБ)", "суточный отчёт античита за 20260101–20260105: журналов стойки 70 (1.5 МБ)",
            "журналов в окне 40.2 МБ — больше предела 32 МБ, сократите окно",
            "суточный отчёт античита №5 за 20260105: флагов вне владельца 9, фон владельца 1, метрик с ошибкой 0, без данных 3",
            "сутки отчёта — дата ГГГГММДД", "сутки отчёта — нет такой даты 20261331"]
        miss = [x for x in ru if CYR.search(i18n.tr(x))]
        check("суточный отчёт EN: отказы, предпросмотр, итог операции, ошибки чтения — без русских слов (%d строк)" % len(ru), not miss,
              [(x, i18n.tr(x)) for x in miss][:5])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("суточный отчёт: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])
    check("суточный отчёт EN: все шаблоны отчёта компилируются, русские шаблоны не повторяются (%d)" % len(AE.TABLE),
          len({a for a, _b, _c in AE.TABLE}) == len(AE.TABLE) and all(CYR.search(a) or a == "ok" or c for a, _b, c in AE.TABLE)
          and not any(CYR.search(b) for a, b, _c in AE.TABLE if "журнал:" not in b))

    # ---- веб
    js = open(os.path.join(ROOT, "web", "acdaily.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    acj = open(os.path.join(ROOT, "web", "acjournal.js"), encoding="utf-8").read()
    check("суточный отчёт веб: раздел #/acdaily с правом ac.view, маршрут viewAcDaily, скрипт после acjournal.js, переход из «Античита» и обратно",
          '["#/acdaily", "Античит: суточный отчёт", "ac.view", "quest"]' in app and 'case "acdaily": return viewAcDaily(my);' in app
          and "/acdaily.js" in idx and idx.index("/acjournal.js") < idx.index("/acdaily.js") and 'location.hash = "#/acdaily"' in acj
          and 'location.hash = "#/ac"' in js)
    check("суточный отчёт веб: без innerHTML, данные — текстовыми узлами (acText), прогон — по праву (can_run), даты ГГГГММДД (acDay), Markdown — <pre> текстом",
          "innerHTML" not in js and "acText(x.md)" in js and "lst.can_run" in js and "acDay(" in js and "T(m." not in js and "T(r." not in js)
    labels = re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|b|div|summary)", (?:null|\{[^}]*\}), "([^"]+)"', js)
    labels += re.findall(r'\["([^"]+)", \w+ =>', js) + re.findall(r'T\("([^"]+)"', js) + ["Античит: суточный отчёт", "Суточный отчёт"]
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted({x for x in labels if x not in have and CYR.search(x)})
    check("суточный отчёт веб EN: у всех подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(set(labels)), not lack and len(set(labels)) > 60, lack[:8])
    rx = r'(?:^|[{,])\s*"((?:[^"\\]|\\.)+)":\s*"'
    blk = wi[wi.index("// ★ А6.6"):]
    kb = re.findall(rx, blk, re.M)
    earlier = set(re.findall(rx, wi[:wi.index("// ★ А6.6")], re.M))
    check("суточный отчёт веб EN: новые ключи web/i18n.js не повторяют прежние и друг друга (%d ключей)" % len(kb),
          len(kb) == len(set(kb)) and not set(kb) & earlier, sorted(set(kb) & earlier)[:5])
    for f in ("acdaily.js", "i18n.js", "app.js", "acjournal.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("суточный отчёт: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("суточный отчёт: node --check web/%s (node не запустился)" % f, False, str(ex))

    # ---- консоль, выкладка, импорт
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "acdaily"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("show", "--bogus")
    c2, o2 = con("events", "--metric")
    c3, o3 = con("nope")
    c4, o4 = con("run", "--thr", "m5_burst_n")
    c5, o5 = con("list", "extra")
    check("суточный отчёт консоль: неизвестный ключ, ключ без значения, неизвестное действие, порог без «=», лишнее слово — отказ без базы и журналов",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3
          and c4 and "КЛЮЧ=ЗНАЧЕНИЕ" in o4 and c5 and "неизвестный аргумент extra" in o5, (o1[-200:], o2[-200:], o3[-200:], o4[-200:], o5[-200:]))
    hp = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60, cwd=ROOT,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
    ho = hp.stdout.decode("utf-8", "replace")
    check("суточный отчёт консоль: --help печатает справку с командой acdaily (ничего не делает)", hp.returncode == 0 and "  acdaily …" in ho
          and "run [--date ГГГГММДД] [--days N] [--thr КЛЮЧ=ЗНАЧЕНИЕ …] [--dry]" in ho)
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read().replace("\r\n", "\n")
    ver = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    s19 = open(os.path.join(ROOT, "sql", "adminc_19_acdaily.sql"), encoding="utf-8").read()
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    check("суточный отчёт выкладка: adminc_19_acdaily после adminc_18 в AsdaAdmin; проверка прав adminc_10 — SELECT / INSERT 1, UPDATE / DELETE 0; "
          "откат описан в adminc_99; в ext/anticheat — все файлы исходника отчёта",
          "Run 'adminc_18_econ.sql' 'AsdaAdmin'\nRun 'adminc_19_acdaily.sql' 'AsdaAdmin'" in dep and "_acd.AC_FILES" in dep
          and all("'adm.AcDaily %s'" % k in ver for k in ("SELECT", "INSERT", "UPDATE", "DELETE")) and (rb is None or "adminc_19_acdaily.sql" in rb)
          and 'z.writestr("ext/MANIFEST.json"' in dep and ",'otp_archive'" in dep and "'adm.AcDailyPurge EXEC'" in ver
          and "GRANT EXECUTE          ON adm.AcDailyPurge TO [asda_admin]" in s19 and (rb is None or "DROP PROCEDURE adm.AcDailyPurge" in rb))
    head = s19.split("GO", 1)[0]
    check("adminc_19: QUOTED_IDENTIFIER / ANSI_NULLS ON отдельным пакетом ДО CREATE TABLE; DENY UPDATE, DELETE; сутки ГГГГММДД и окно 1…31 — CHECK",
          "SET QUOTED_IDENTIFIER ON" in head and "CREATE TABLE" not in head and "DENY  UPDATE, DELETE   ON adm.AcDaily" in s19
          and "CK_adm_AcDaily_days CHECK (days BETWEEN 1 AND 31" in s19)
    imp = subprocess.run([py, "-c", "import sys; sys.path.insert(0, %r); from core import db; from domains import acdaily, acdaily_en; "
                          "print('IMPORT_OK', len(db._pw), len(db._override), any(m.startswith('acdaily_src_') for m in sys.modules))" % ROOT],
                         capture_output=True, timeout=60, cwd=ROOT, stdin=subprocess.DEVNULL)
    check("суточный отчёт: импорт domains/acdaily.py ничего не делает (пароль не читан, соединений нет, исходник не исполнен)",
          b"IMPORT_OK 0 0 False" in imp.stdout, (imp.stdout + imp.stderr)[-300:])


def _os_err(fn):
    try:
        f = fn()
        f.close()
        return None
    except Exception as ex:
        return ex


def _exc(fn):
    try:
        fn()
        return None
    except Exception as ex:
        return ex


# ---------------------------------------------------------------- ★ ревизия 56

TRAP = '''import os
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "TRAP_RAN"), "w").write("x")
'''


def _r56_offline(check, A, root, tmp, q):
    """Ревизия 56: Н-1 (общий источник не открылся), Н-2 (архив OTP_Report), С-1 (подложенный исходник), Н-3 (предел службы, досчёт),
    мелочь 2 (номер задания)."""
    import hashlib
    import json
    from core import config, ops, sched
    from domains import acsrc, logs, shopcs, shopdata, trade
    saved = A.STACK_OVERRIDE
    try:
        # Н-1: на месте Log_LevelUp — папка (open падает, как у занятого писателем файла)
        r2 = os.path.join(tmp, "v2_busy")
        shutil.copytree(root, r2)
        lv = os.path.join(r2, "GameServer", "Log", "Log_LevelUp", "LevelUp_20260105.txt")
        os.remove(lv)
        os.makedirs(lv)
        A.STACK_OVERRIDE = (r2, GS, NPC, "")
        rb = A.compute(q, with_db=False)
        sb = _status(source_md(r2, os.path.join(tmp, "src_busy.md")))
        check("р56 Н-1: Log_LevelUp не открылся — отчёт не падает ни у исходника, ни у панели: M1 / M9 «ошибка», остальные считаются, статусы равны",
              _status(rb["md"]) == sb and sb["M1"] == sb["M9"] == "ошибка" and sb["M5"] == "ok" and sb["M12"] == "ok", sb)
        # Н-2: OTP_Report только в архиве
        r3, arch = os.path.join(tmp, "v2_arch"), os.path.join(tmp, "otp_arch")
        shutil.copytree(root, r3)
        os.makedirs(arch)
        shutil.move(os.path.join(r3, "LoginManager", "Log", "LoginMngError", "OTP_Report_20260105.txt"), os.path.join(arch, "OTP_Report_20260105.txt"))
        A.STACK_OVERRIDE = (root, GS, NPC, "")
        base = A.compute(q, with_db=False)
        A.STACK_OVERRIDE = (r3, GS, NPC, arch)
        ra = A.compute(q, with_db=False)
        sa = source_md(r3, os.path.join(tmp, "src_arch.md"), arch)
        _f, miss = A.plan_files(r3, GS, NPC, q["d0"], q["d1"], arch)
        m12 = lambda r: [m for m in r["metrics"] if m["mid"] == "M12"][0]["events_total"]
        check("р56 Н-2: OTP_Report только в архиве — панель читает его как --otp-archive исходника: Markdown = исходнику, M12 как с живым файлом, "
              "суток без OTP нет", _body(ra["md"]) == _body(sa) and m12(ra) == m12(base) > 0 and not miss and ra["meta"]["otp_missing"] == [], (m12(ra), miss))
        A.STACK_OVERRIDE = (r3, GS, NPC, "")
        rn = A.compute(q, with_db=False)
        pv = ops.REGISTRY["ac.daily"].preview(ops.Ctx(None, "service:daily", "owner", "", "sched"), {"date": "20260105"})
        note = [n for m in rn["metrics"] if m["mid"] == "M12" for n in m["notes"] if n.startswith("OTP_Report за период")]
        check("р56 Н-2: нет OTP_Report ни в журнале, ни в архиве — предупреждение в предпросмотре, otp_missing в отчёте (плашка экрана), заметка "
              "исходника «нет ни в LoginMngError, ни в архиве»", rn["meta"]["otp_missing"] == ["20260105"]
              and any("нет OTP_Report ни в журнале LoginManager, ни в архиве" in w for w in pv["warnings"])
              and note == ["OTP_Report за период нет ни в LoginMngError, ни в архиве (архив не задан): M8 / M12 / M12o без записей входа LoginManager."],
              (rn["meta"]["otp_missing"], pv["warnings"], note))
        ga = A.Guard(r3, GS, NPC, arch)
        okf = ga.open(os.path.join(arch, "OTP_Report_20260105.txt"), "rb")
        okf.close()
        check("р56 Н-2: белый список архива — только OTP_Report*<дата>.txt прямо в папке архива",
              isinstance(_os_err(lambda: ga.open(os.path.join(arch, "secret.txt"), "rb")), PermissionError)
              and isinstance(_os_err(lambda: ga.open(os.path.join(arch, "x", "OTP_Report_20260105.txt"), "rb")), PermissionError))
    finally:
        A.STACK_OVERRIDE = saved
    # С-1: подложенный исходник вне дерева службы не исполняется
    trap, ext = os.path.join(tmp, "trap"), os.path.join(tmp, "ext")
    os.makedirs(trap)
    os.makedirs(os.path.join(ext, "anticheat"))
    for f in A.AC_FILES:
        open(os.path.join(trap, f), "w", encoding="utf-8").write(TRAP)
        shutil.copy2(os.path.join(A.AC_SRC, f), os.path.join(ext, "anticheat", f))
    man = {"anticheat/" + f: hashlib.md5(open(os.path.join(ext, "anticheat", f), "rb").read()).hexdigest() for f in A.AC_FILES}
    open(os.path.join(ext, "MANIFEST.json"), "w", encoding="utf-8").write(json.dumps(man))
    cfg = config.get()
    sv = (cfg.on_server, acsrc.EXT, acsrc.MANIFEST, A.AC_SRC, A.AC_EXT, trade.AC_SRC, trade.AC_EXT, trade._AC)
    try:
        cfg.on_server = True
        acsrc.EXT, acsrc.MANIFEST = ext, os.path.join(ext, "MANIFEST.json")
        A.AC_SRC, A.AC_EXT = trap, os.path.join(ext, "anticheat")
        trade.AC_SRC, trade.AC_EXT, trade._AC = trap, os.path.join(ext, "anticheat"), None
        m3 = trade.m3()
        sd = A.src_dir()
        md = A.code_md5()
        e_out = _exc(lambda: acsrc.read_verified(os.path.join(trap, "ac_common.py")))
        with open(os.path.join(ext, "anticheat", "ac_common.py"), "ab") as f:
            f.write(b"\n# tamper\n")
        e_md5 = _exc(lambda: A.defaults())
        man.pop("anticheat/db_connect.py")
        open(os.path.join(ext, "MANIFEST.json"), "w", encoding="utf-8").write(json.dumps(man))
        trade._AC = None
        e_man = _exc(lambda: trade.m3())
        e_port = _exc(lambda: config.port_code(shopdata.SRV_TOOLS))
        lay = shopdata._layout()
        e_cs = _exc(lambda: shopcs._layout())
        check("р56 С-1: на сервере исходник берётся ТОЛЬКО из ext/ дерева службы — подложенная папка вне дерева (ловушка в каждом из 5 файлов) "
              "не исполняется ни суточным отчётом, ни правилом M3 «Передач»",
              not os.path.exists(os.path.join(trap, "TRAP_RAN")) and sd == os.path.join(ext, "anticheat") and len(md) == 32
              and os.path.dirname(m3.LOADED_FROM) == os.path.join(ext, "anticheat") and isinstance(e_out, acsrc.SourceError), (sd, e_out))
        check("р56 С-1: копия ext/ не совпала с манифестом выкладки (md5) или её нет в манифесте — отказ SourceError до исполнения",
              isinstance(e_md5, acsrc.SourceError) and "md5" in str(e_md5) and isinstance(e_man, acsrc.SourceError) and "нет в манифесте" in str(e_man),
              (e_md5, e_man))
        check("р56 С-1: код порта вне дерева службы на сервере — отказ (config.port_code), stack_layout — копия полей, а не импорт H:\\Server\\…",
              isinstance(e_port, config.PortCodeError) and lay is shopdata._LayoutCopy and isinstance(e_cs, config.PortCodeError), (e_port, e_cs))
    finally:
        cfg.on_server, acsrc.EXT, acsrc.MANIFEST, A.AC_SRC, A.AC_EXT, trade.AC_SRC, trade.AC_EXT, trade._AC = sv
    pr = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); from core import config; config.get().on_server = True; "
                         "import domains; domains.load_all(); print('SRV_LOAD_OK')" % ROOT], capture_output=True, timeout=120, cwd=ROOT,
                        stdin=subprocess.DEVNULL)
    check("р56 С-1: в режиме сервера все разделы загружаются (код порта недоступен — прежняя работа по снимку, PortCodeError — наследник ImportError)",
          b"SRV_LOAD_OK" in pr.stdout and issubclass(config.PortCodeError, ImportError), (pr.stdout + pr.stderr)[-400:])
    # Н-3: предел службы, досчёт
    cs, cw = ops.Ctx(None, "service:daily", "owner", "", "sched"), ops.Ctx(None, "u", "owner", "", "web")
    calls = []
    sched._backfilled[:] = []
    sched._backfill_next[0] = 0.0
    b1 = sched.backfill_once(datetime.date(2026, 1, 9), missing=["20260101", "20260103"], runner=lambda d: calls.append(d) or {"message": "ok " + d})
    b2 = sched.backfill_once(datetime.date(2026, 1, 9), missing=["20260104"], runner=lambda d: calls.append(d) or {})
    sched._backfilled[:] = []
    check("р56 Н-3: ночной прогон службы — свой предел (%d МБ, без бюджета пользователей %d МБ); досчёт пропущенных суток — один раз за процесс, "
          "старые первыми" % (A.SERVICE_BYTES_MAX // 1048576, logs.BYTES_USER_MIN // 1048576),
          A._limit(cs) == A.SERVICE_BYTES_MAX > logs.BYTES_USER_MIN == A._limit(cw) and calls == ["20260101", "20260103"] and b2 == []
          and b1 == [("20260101", "ok 20260101"), ("20260103", "ok 20260103")], (calls, b1, b2))
    # мелочь 2: номер задания
    j = [_refused(lambda: A._job_id(cw, {"job_id": 5})), _refused(lambda: A._job_id(ops.Ctx(None, "j", "owner", "", "job"), {"job_id": "5"})),
         _refused(lambda: A._job_id(ops.Ctx(None, "j", "owner", "", "job"), {"job_id": 0}))]
    check("р56 (мелочь 2): номер задания — только от планировщика (via job), только целое ≥ 1", all(j) and A._job_id(ops.Ctx(None, "j", "owner", "", "job"),
          {"job_id": 5}) == 5 and A._job_id(cw, {}) is None, j)


def _r56_sandbox(check, A, ops, ac, ldb, names, rid):
    """Ревизия 56 на стенде: срок хранения (процедура), сводка размера, досчёт по журналу, межпроцессный замок, номер задания, «день» с пробелом."""
    import datetime as _d
    cur = ac.cursor()
    cols = ("day_from, day_to, days, made_local, taken_by, via, job_id, elapsed_ms, metrics_n, flags_out, flags_bg, errors_n, nodata_n, log_files, "
            "log_bytes, code_md5, thr_json, thr_over_json, summary_json, events_json, report_md")
    for via, age in (("sched", 401), ("sched", 200), ("cli", 91), ("cli", 30)):
        cur.execute("INSERT adm.AcDaily (%s, made_utc) SELECT %s, DATEADD(DAY, -?, SYSUTCDATETIME()) FROM adm.AcDaily WHERE id = ?"
                    % (cols, cols.replace("via,", "'%s'," % via)), (age, rid))
    n0 = cur.execute("SELECT COUNT(*) FROM adm.AcDaily").fetchone()[0]
    pg = A.purge()
    n1 = cur.execute("SELECT COUNT(*) FROM adm.AcDaily").fetchone()[0]
    st = {r["kind"]: r for r in A.storage()}
    check("р56 Н-4: срок хранения — процедура adm.AcDailyPurge: служба старше 400 суток и ручные старше 90 — удалены, служба 200 суток и ручные "
          "30 суток — на месте; сводка размера по пути", pg == {"sched": 1, "manual": 1} and n1 == n0 - 2 and st["sched"]["n"] >= 2
          and st["manual"]["bytes"] > 0, (pg, n0, n1, st))
    miss = A.missing_days(_d.date(2026, 1, 8))
    check("р56 Н-3: досчёт по журналу — сутки 31.12–06.01 без отчёта на одни сутки (05.01 уже есть, вчера 07.01 — DAILY)",
          miss == ["20251231", "20260101", "20260102", "20260103", "20260104", "20260106"], miss)
    lk = ldb(names["A"])
    lk.cursor().execute("DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', @LockOwner = 'Session', @LockTimeout = 0",
                        (A.LOCK_NAME,))
    try:
        w = _refused(lambda: ops.run(ops.Ctx(None, "lk_user", "owner", "", "web"), "ac.daily", {"date": "20260105"}))
    finally:
        lk.cursor().execute("EXEC sp_releaseapplock @Resource = ?, @LockOwner = 'Session'", (A.LOCK_NAME,))
        lk.close()
    rj = ops.run(ops.Ctx(None, "jobber", "owner", "", "job"), "ac.daily", {"date": "20260105", "job_id": 77})
    jid = cur.execute("SELECT job_id, via FROM adm.AcDaily WHERE id = ?", (rj["result"]["id"],)).fetchone()
    wj = _refused(lambda: ops.run(ops.Ctx(None, "webber", "owner", "", "web"), "ac.daily", {"date": "20260105", "job_id": 77}))
    check("р56 (мелочи 3, 2): прогон держит межпроцессный замок (занят другим процессом — отказ «уже считается»); номер задания от планировщика "
          "записан, из веба — отказ", w == "суточный отчёт уже считается — повторите через минуту" and tuple(jid) == (77, "job")
          and wj == "номер задания суточного отчёта передаёт только планировщик заданий", (w, jid, wj))
    check("р56 (мелочь 5): «сутки» с пробелом — проверяется и уходит в запрос одно значение", A.reports({"day": " 20260105 "})["reports"]
          and A.report({"day": " 20260105"})["day_to"] == "20260105")


# ---------------------------------------------------------------- ★ ревизия 57

def _r57_offline(check, A, root, tmp, q):
    """Ревизия 57: Н-1 (LoginProc занят), Н-2 (выкладчик: проба на «сервере», откат), Н-3 (каталоги только из data/ref), мелочи 1, 5, 6, 7."""
    import io
    import json
    import zipfile
    from core import config, ops, sched
    from domains import acjournal_src, acsrc, patchcfg_src
    saved = A.STACK_OVERRIDE
    # Н-1: LoginProc занят писателем без общего доступа
    if os.name == "nt":
        try:
            A.STACK_OVERRIDE = (root, GS, NPC, "")
            lp = os.path.join(root, "LoginManager", "Log", "LoginMngError", "LoginProc_20260105.txt")
            k32, hnd = _lock_share0(lp)
            try:
                rb = A.compute(q, with_db=False)
                sb = _status(source_md(root, os.path.join(tmp, "src_lp.md")))
            finally:
                k32.CloseHandle(hnd)
            m8 = [m for m in rb["metrics"] if m["mid"] == "M8"][0]
            check("р57 Н-1: LoginProc занят писателем (CreateFileW без общего доступа) — отчёт не падает ни у исходника, ни у панели: M8 «ошибка» "
                  "с причиной, статусы равны, M5 / M9 считаются", _status(rb["md"]) == sb and sb["M8"] == "ошибка" and sb["M5"] == sb["M9"] == "ok"
                  and any(n.startswith("LoginProc не прочитан") for n in m8["notes"]), sb)
        finally:
            A.STACK_OVERRIDE = saved
    # Н-2 (а): пробный импорт — настоящий пакет выкладки вне дерева порта, режим сервера
    sys.path.insert(0, os.path.join(ROOT, "deploy"))
    try:
        import deploy_admin_center as DP
    finally:
        sys.path.remove(os.path.join(ROOT, "deploy"))
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        pkg = DP.build_zip()
    box = os.path.join(tempfile.mkdtemp(prefix="acd_probe_"), "svc")
    zipfile.ZipFile(io.BytesIO(pkg)).extractall(box)

    def probe(where):
        code = "import sys; sys.path.insert(0, '.'); from core import config; config.get().on_server = True; exec(%r)" % DP.PROBE_CODE
        p = subprocess.run([sys.executable, "-I", "-c", code], cwd=where, capture_output=True, timeout=300, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return (p.stdout + p.stderr).decode("utf-8", "replace")
    try:
        good = probe(box)
        man = json.load(open(os.path.join(box, "ext", "MANIFEST.json"), encoding="utf-8"))
        from domains import autoblock as _ab, trade as _tr
        n_ext = 1 + len(set(_tr.AC_FILES) | set(A.AC_FILES) | set(_ab.AC_FILES))   # ★ А6.8 (22.11): ext/ — по спискам разделов, а не числом
        with open(os.path.join(box, "domains", "cs_kinds", "equipshop.py"), "a", encoding="utf-8") as f:
            f.write("\nraise RuntimeError('probe trap')\n")
        bad = probe(box)
    finally:
        shutil.rmtree(os.path.dirname(box), ignore_errors=True)
    check("р57 Н-2 (а): пробный импорт настоящего пакета выкладки ВНЕ дерева порта в режиме сервера — все разделы, API, планировщик (%s); "
          "пакет без tests/, манифест ext/ на %d файлов (сверка подарков + AstoryServer/Tools/Anticheat трёх разделов — ★ А6.8: + ac_case.py и конфиг); "
          "сломанный при импорте раздел — пробы нет" % (good.strip()[-60:], n_ext),
          re.search(r"PROBE_OK on_server=True routes=\d+", good) and not re.search(r"PROBE_OK on_server=\w+ routes=\d+", bad) and "probe trap" in bad
          and len(man) == n_ext and n_ext == 8 and {"anticheat/ac_case.py", "anticheat/ac_case_config.json"} <= set(man)
          and not any(n.startswith("tests/") for n in zipfile.ZipFile(io.BytesIO(pkg)).namelist()), (good[-400:], bad[-300:]))
    calls = []
    ok1 = DP.probe_package("X", run=lambda s, timeout=300: calls.append(s) or "PROBE_OK on_server=True routes=1 ops=1")
    ok2 = DP.probe_package("X", run=lambda s, timeout=300: "Traceback … PortCodeError")
    ok3 = DP.probe_package("X", run=lambda s, timeout=300: "PROBE_OK on_server=False routes=1 ops=1")
    src = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    main_src = src[src.index("def main("):]
    check("р57 Н-2 (а): проба на сервере — до остановки прежней службы (шаг 2б раньше шага 3, отказ — код 6); распаковка в _incoming\\probe_, "
          "папка пробы удаляется; не на сервере (on_server=False) — не годится",
          ok1[0] and not ok2[0] and not ok3[0] and "probe_" in calls[0] and "Remove-Item $pd" in calls[0]
          and main_src.index('step("2б.') < main_src.index('step("3.') and "return 6" in main_src[:main_src.index('step("3.')])
    seq, rest = [], []
    r_ok = DP.after_start("S1", wait=lambda: seq.append("w") or (0, "ok"), restore=lambda s: rest.append(s), log=lambda: None)
    w2 = iter([(4, "нет"), (0, "401")])
    r_back = DP.after_start("S2", wait=lambda: next(w2), restore=lambda s: rest.append(s), log=lambda: None)
    w3 = iter([(4, "нет"), (4, "нет")])
    with contextlib.redirect_stdout(io.StringIO()):
        r_dead = DP.after_start("S3", wait=lambda: next(w3), restore=lambda s: rest.append(s), log=lambda: None)
    check("р57 Н-2 (б): служба не поднялась — возврат прежней версии из _backup\\<метка> и повторная проверка: поднялась — код 4 «откачено», "
          "нет — код 5; поднялась сразу — 0 без возврата; шаг 8 идёт через after_start",
          r_ok[0] == 0 and r_back[0] == 4 and "ОТКАЧЕНА" in r_back[1] and r_dead[0] == 5 and rest == ["S2", "S3"]
          and "after_start(stamp)" in main_src, (r_ok, r_back, r_dead, rest))
    # Н-3: каталоги на сервере — только справочник выкладки
    cfg = config.get()
    trap = os.path.join(tmp, "trap_srv")
    os.makedirs(os.path.join(trap, "AsdaPatch", "src"))
    open(os.path.join(trap, "AsdaPatch", "src", "Config.cpp"), "w").write("/* trap */")
    open(os.path.join(trap, "AcJournal.cpp"), "w").write("/* trap */")
    sv = (cfg.on_server, patchcfg_src.PATCHES, acjournal_src.SRC, patchcfg_src.build, acjournal_src.build, patchcfg_src.CATALOG_REF,
          acjournal_src.CATALOG_REF)
    built = []
    refs = {}
    for k in ("patchcfg", "acjournal"):                       # справочники выкладки (на ПК их строит build_zip) — подставные
        refs[k] = os.path.join(tmp, "ref_%s.json" % k)
        json.dump({"ref": k}, open(refs[k], "w", encoding="utf-8"))
    try:
        cfg.on_server = True
        patchcfg_src.CATALOG_REF, acjournal_src.CATALOG_REF = refs["patchcfg"], refs["acjournal"]
        patchcfg_src.PATCHES, acjournal_src.SRC = trap, os.path.join(trap, "AcJournal.cpp")
        patchcfg_src.build = lambda *a, **k: built.append("patchcfg") or {}
        acjournal_src.build = lambda *a, **k: built.append("acjournal") or {}
        pc, aj = patchcfg_src.load(), acjournal_src.load()
    finally:
        (cfg.on_server, patchcfg_src.PATCHES, acjournal_src.SRC, patchcfg_src.build, acjournal_src.build, patchcfg_src.CATALOG_REF,
         acjournal_src.CATALOG_REF) = sv
    check("р57 Н-3: на сервере каталоги «Настройки патчей» и «Античит: журнал» — только из data/ref выкладки, подложенные Config.cpp / "
          "AcJournal.cpp по пути порта не читаются", not built and pc == {"ref": "patchcfg"} and aj == {"ref": "acjournal"}, built)
    # мелочь 1: самотест на сервере не запускается
    import importlib
    sys.path.insert(0, ROOT)
    AA = importlib.import_module("asda_admin")
    try:
        cfg.on_server = True
        try:
            AA.main(["selftest"])
            msg = None
        except SystemExit as ex:
            msg = ex
    finally:
        cfg.on_server = sv[0]
    check("р57 (мелочь 1): самотест на сервере отказывает (исполнял бы код из путей порта), tests/ на сервер не выкладывается",
          isinstance(msg, SystemExit) and "самотест на сервере не запускается" in str(msg) and '"tests"' not in src.split("PACK_DIRS = ", 1)[1].split("\n")[0],
          str(msg)[:200])
    # мелочь 6: досчёт — отказавшие сутки повторяются не чаще RETRY_S, «сделано» — только после успеха всех
    sched._backfilled[:] = []
    sched._backfill_next[0] = 0.0
    n = [0]

    def run(d):
        n[0] += 1
        if n[0] == 1:
            raise ops.OpRefused("занят")
        return {"message": "ok"}
    with contextlib.redirect_stdout(io.StringIO()):
        a1 = sched.backfill_once(datetime.date(2026, 1, 9), missing=["20260101"], runner=run, mono=1000.0)
        a2 = sched.backfill_once(datetime.date(2026, 1, 9), missing=["20260101"], runner=run, mono=1000.0 + sched.RETRY_S - 1)
        a3 = sched.backfill_once(datetime.date(2026, 1, 9), missing=["20260101"], runner=run, mono=1000.0 + sched.RETRY_S + 1)
        a4 = sched.backfill_once(datetime.date(2026, 1, 9), missing=["20260102"], runner=run, mono=1e9)
    sched._backfilled[:] = []
    sched._backfill_next[0] = 0.0
    check("р57 (мелочь 6): досчёт — отказавшие сутки повторяются через RETRY_S, после успеха всех — «сделано» (дальше не зовётся)",
          a1 and "OpRefused" in a1[0][1] and a2 == [] and a3 == [("20260101", "ok")] and a4 == [], (a1, a2, a3, a4))
    # мелочь 7: SourceError — отказ (409), а не 500; пометка на экране
    check("р57 (мелочь 7): SourceError — наследник OpRefused (в журнале refused, ответ 409 с текстом)", issubclass(acsrc.SourceError, ops.OpRefused))


def _r57_sandbox(check, A, ops, ac):
    """Ревизия 57 на стенде: ручной отчёт ночной не заменяет (мелочь 5), пометка «исходник не прошёл проверку» в списке и отчёте (мелочь 7)."""
    from domains import acsrc
    cur = ac.cursor()
    cols = ("day_from, day_to, days, made_local, taken_by, via, job_id, elapsed_ms, metrics_n, flags_out, flags_bg, errors_n, nodata_n, log_files, "
            "log_bytes, code_md5, thr_json, thr_over_json, summary_json, events_json, report_md")
    rid = cur.execute("SELECT MIN(id) FROM adm.AcDaily").fetchone()[0]
    cur.execute("INSERT adm.AcDaily (%s) SELECT %s FROM adm.AcDaily WHERE id = ?"
                % (cols, cols.replace("day_from, day_to,", "'20260102', '20260102',").replace("via,", "'web',")), (rid,))
    import datetime as _d
    miss = A.missing_days(_d.date(2026, 1, 8))
    sv = A.defaults, A.code_md5

    def boom(*_a):
        raise acsrc.SourceError("файл anticheat/ac_common.py не совпадает с манифестом выкладки (md5) — код не исполняется")
    try:
        A.defaults, A.code_md5 = boom, boom
        lst, rep = A.reports({}), A.report({"day": "20260105"})
    finally:
        A.defaults, A.code_md5 = sv
    check("р57 (мелочь 5): ручной отчёт за 02.01 ночной не заменяет — служба его досчитает", "20260102" in miss, miss)
    check("р57 (мелочь 7): исходник не прошёл проверку — список и отчёт открываются с пометкой (errors), а не молча", lst["errors"]
          and lst["errors"][0].startswith("исходник отчёта не прошёл проверку:") and rep["errors"] and rep["code_now"] is None, (lst["errors"], rep["errors"]))


# ---------------------------------------------------------------- стенд LocalDB

def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


TRADE_COLS = ("Edate DATETIME NOT NULL, Userindex INT NOT NULL, Charidx TINYINT NULL, Fromname VARCHAR(20) NULL, Tuserindex INT NULL, "
              "Tcharidx TINYINT NULL, Toname VARCHAR(20) NULL, Code INT NULL, Serial VARCHAR(36) NULL, Amount INT NULL, Ramount INT NULL")


def sandbox(check, ldb):
    """Свои базы LocalDB: операция ac.daily пишет adm.AcDaily, M3 / M4 / M8 / ACJ — по базе."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import secrets
    from core import db, ops
    from domains import acdaily as A, acdaily_en as AE
    import domains
    domains.load_all()
    tag = secrets.token_hex(3)
    names = {"A": "AsdaAcdA_" + tag, "Y": "AsdaAcdY_" + tag, "G": "AsdaAcdG_" + tag}
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % names["A"])
    for k in ("Y", "G"):
        m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % names[k])
    tmp = tempfile.mkdtemp(prefix="acd_sb_")
    saved = A.STACK_OVERRIDE, A.RUNS_PER_HOUR
    try:
        ac = ldb(names["A"])
        for f in ("adminc_02_schema.sql", "adminc_19_acdaily.sql", "adminc_19_acdaily.sql"):
            for b in _batches(open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()):
                ac.cursor().execute(b)
        check("суточный отчёт стенд: настоящие adminc_02 + adminc_19 дважды (повтор безопасен, без asda_admin — выдача прав пропущена)",
              ac.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'AcDaily'").fetchone()[0] == 1)
        yc = ldb(names["Y"]).cursor()
        yc.execute("CREATE TABLE dbo.Item (Uuid UNIQUEIDENTIFIER NULL, Userindex INT, Charidx TINYINT, Code INT, GainDate DATETIME NULL)")
        yc.execute("CREATE TABLE dbo.Del_item (Uuid UNIQUEIDENTIFIER NULL, Userindex INT, Edate DATETIME NULL)")
        u = "6F9619FF-8B86-D011-B42D-00C04FC964FF"
        yc.execute("INSERT dbo.Item VALUES (?, 9001, 0, 555, '2026-01-05'), (?, 9002, 0, 555, '2026-01-05'), (NEWID(), 9003, 0, 7, NULL)", (u, u))
        gc = ldb(names["G"]).cursor()
        for t in ("TradeGoldFrom", "TradeGoldTo", "TradeItemFrom"):
            gc.execute("CREATE TABLE dbo.%s (%s)" % (t, TRADE_COLS))
        for i in range(5):
            gc.execute("INSERT dbo.TradeGoldFrom (Edate, Userindex, Tuserindex, Fromname, Toname, Amount, Ramount) VALUES "
                       "(DATEADD(MINUTE, ?, '2026-01-05T10:00:00'), 9001, 9002, 'Alpha', 'Beta', 2000000, 1700000)", (i,))
            gc.execute("INSERT dbo.TradeGoldTo (Edate, Userindex, Tuserindex, Fromname, Toname, Amount, Ramount) VALUES "
                       "(DATEADD(MINUTE, ?, '2026-01-05T10:00:00'), 9001, 9002, 'Alpha', 'Beta', 0, 300000)", (i,))
        gc.execute("INSERT dbo.TradeItemFrom (Edate, Userindex, Tuserindex, Fromname, Toname, Code, Serial, Amount, Ramount) VALUES "
                   "('2026-01-05T11:00:00', 9002, 9001, 'Beta', 'Alpha', 555, 'S-1', 1, 0), ('2026-01-05T11:01:00', 9001, 9003, 'Alpha', 'Gamma', 555, 'S-1', 1, 0), "
                   "('2026-01-05T11:02:00', 9003, 9002, 'Gamma', 'Beta', 555, 'S-1', 1, 0)")
        gc.execute("CREATE TABLE dbo.LogInfo (Userindex INT, IpAddress VARCHAR(20), Mac VARCHAR(20), Login DATETIME)")
        for uid in (9001, 9002, 9003):
            gc.execute("INSERT dbo.LogInfo VALUES (?, '10.1.1.1', '', '2026-01-05T09:00:00')", (uid,))
        gc.execute("CREATE SCHEMA ac")
        for t in A.load(tmp, GS, NPC).D.AC_TABLES:
            gc.execute("CREATE TABLE ac.[%s] (id INT IDENTITY, ev_local DATETIME2(3) NOT NULL, event_kind NVARCHAR(200) NULL, user_index INT NULL, "
                       "login VARCHAR(20) NULL)" % t)
        gc.execute("INSERT ac.move_combat (ev_local, event_kind, user_index, login) VALUES ('2026-01-05T12:00:00', N'move', 9001, 'alpha'), "
                   "('2026-01-05T12:01:00', N'move', 9001, 'alpha')")
        gc.execute("INSERT ac.other (ev_local, event_kind) VALUES ('2026-01-05T00:00:00', N'журнал: старт')")
        gc.execute("CREATE VIEW ac.v_events AS SELECT ev_local, CAST(N'move_combat' AS NVARCHAR(40)) AS violation_type, CAST('GameServer' AS VARCHAR(20)) AS server_name, "
                   "user_index, login, CAST(NULL AS VARCHAR(20)) AS char_name, CAST('10.1.1.1' AS VARCHAR(20)) AS ip, 4007 AS opcode, event_kind AS summary, "
                   "CAST(N'move_combat' AS NVARCHAR(40)) AS table_name FROM ac.move_combat UNION ALL SELECT ev_local, N'other', NULL, user_index, login, NULL, NULL, "
                   "NULL, event_kind, N'other' FROM ac.other")
        gc.execute("CREATE VIEW ac.v_top_offenders AS SELECT user_index, login, COUNT(*) AS total, 0 AS kicks, 0 AS autoblocks, 0 AS sign_replay, "
                   "COUNT(*) AS move_combat FROM ac.move_combat GROUP BY user_index, login")
        mp = {"Joy1": names["Y"], "joylog1": names["G"], "JoyLog1": names["G"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("admin", lambda database: ldb(names["A"]))
        root = os.path.join(tmp, "v2")
        write_logs(root)
        A.STACK_OVERRIDE = (root, GS, NPC, "")
        ctx = ops.Ctx(None, "selftest", "owner", "", "cli")
        r1 = ops.run(ctx, "ac.daily", {"date": "20260105"})
        rid = r1["result"]["id"]
        row = ac.cursor().execute("SELECT day_from, day_to, days, taken_by, via, flags_out, flags_bg, errors_n, nodata_n, log_files, code_md5, "
                                  "LEN(report_md) FROM adm.AcDaily WHERE id = ?", (rid,)).fetchone()
        check("суточный отчёт стенд: ac.daily записал строку adm.AcDaily (сутки 20260105, кто, путь cli, флаги, журналов 15, md5 кода, Markdown)",
              row and row[0] == row[1] == "20260105" and row[2] == 1 and row[3] == "selftest" and row[4] == "cli" and row[5] > 0 and row[9] == 15
              and row[10] == A.code_md5() and row[11] > 1000 and r1["message"].startswith("суточный отчёт античита №%d за 20260105" % rid), (row, r1["message"]))
        aud = ac.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action = 'ac.daily' AND result = 'ok'").fetchone()[0]
        check("суточный отчёт стенд: прогон в журнале действий adm.audit (ok)", aud == 1, aud)
        rep = A.report({"id": str(rid)})
        by = {x["mid"]: x for x in rep["metrics"]}
        check("суточный отчёт стенд: все метрики без «ошибки» — каждый запрос прошёл проверки «только чтение» исходника и панели (%s)"
              % ", ".join("%s=%s" % (k, v["status"]) for k, v in by.items() if v["status"] != "ok"),
              not [k for k, v in by.items() if v["status"] == "ошибка"] and len(by) == 14, {k: v["notes"][:2] for k, v in by.items() if v["status"] == "ошибка"})
        m3f = [f[1] for f in by["M3"]["flags"]]
        check("суточный отчёт стенд: M3 по базе — пара 9001↔9002: 6 записей (5 золотом + вещь обратно) и 1 500 000 золота в одну сторону (сумма = Amount − "
              "Ramount, зеркала …To не считаются), в окне и за 7 дней", len(m3f) == 4 and any("6 записей сделок" in t for t in m3f) and any("золото 1500000 в одну сторону" in t for t in m3f), m3f)
        check("суточный отчёт стенд: M4 — дубль Uuid (Item ×2) и цепочка Serial S-1 (3 передачи); ACJ — 2 события окна без служебной «журнал:»; "
              "M8 — LogInfo: IP 10.1.1.1 делят 3 учётки",
              any("встречается 2 раз" in f[1] for f in by["M4"]["flags"]) and any("Serial S-1" in f[1] for f in by["M4"]["flags"])
              and by["ACJ"]["events_total"] == 2 and any("10.1.1.1 делят 3" in f[1] for f in by["M8"]["flags"]), (by["M4"]["flags"], by["ACJ"]["events_total"], by["M8"]["flags"]))
        ev = A.events({"id": str(rid), "metric": "M5", "size": "2", "page": "2"})
        check("суточный отчёт стенд: события метрики листаются (M5: %d, страница 2 по 2)" % ev["total"], ev["total"] == 11 and ev["page"] == 2
              and len(ev["rows"]) == 2 and ev["pages"] == 6)
        md = A.markdown({"day": "20260105"})
        lst = A.reports({"day": "20260105"})
        check("суточный отчёт стенд: Markdown исходника читается как есть, список прогонов за сутки, отчёт за сутки = последний",
              md["id"] == rid and md["md"].startswith("# Суточный отчёт античита: 2026-01-05") and [x["id"] for x in lst["reports"]] == [rid]
              and A.report({"day": "20260105"})["id"] == rid)
        why = [_refused(lambda q=q: A.report(q)) for q in ({"id": "999"}, {"id": "x"}, {"day": "20260106"})] + \
              [_refused(lambda q=q: A.events(q)) for q in ({"id": str(rid), "metric": "M99"}, {"id": str(rid), "metric": "M1;"}, {"id": str(rid), "metric": "M1", "size": "501"})]
        check("суточный отчёт стенд: нет отчёта, неверный номер, нет метрики, неверное имя метрики, размер страницы — отказ", all(why), why)
        # бюджет, служба вне бюджета, один прогон за раз, право
        A.RUNS_PER_HOUR = 1
        b1 = _refused(lambda: ops.run(ctx, "ac.daily", {"date": "20260105"}))
        rs = ops.run(ops.Ctx(None, "service:daily", "owner", "", "sched"), "ac.daily", {"date": "20260105"})
        A._RUN.acquire()
        try:
            b2 = _refused(lambda: ops.run(ops.Ctx(None, "other", "owner", "", "web"), "ac.daily", {"date": "20260105"}))
        finally:
            A._RUN.release()
        b3 = _refused(lambda: ops.run(ops.Ctx(None, "gm1", "gm", "", "web"), "ac.daily", {"date": "20260105"}))
        n = ac.cursor().execute("SELECT COUNT(*) FROM adm.AcDaily").fetchone()[0]
        check("суточный отчёт стенд: бюджет — ручных прогонов не больше RUNS_PER_HOUR в час на пользователя, служба (sched) вне бюджета, второй прогон "
              "во время первого — отказ, без ac.daily_run — отказ; записей ровно 2", b1 == "суточный отчёт вручную — не больше 1 раз в час на пользователя, подождите"
              and rs["result"]["id"] > rid and b2 == "суточный отчёт уже считается — повторите через минуту" and b3 == "нет права «ac.daily_run»" and n == 2,
              (b1, b2, b3, n))
        i18n_en = __import__("core.i18n", fromlist=["x"])
        i18n_en.set_lang("en")
        try:
            v = AE.view(copy.deepcopy(rep))
        finally:
            i18n_en.set_lang("ru")
        cb = [x for x in _cyr_view(v) if "журнал:" not in str(x)]
        check("суточный отчёт стенд EN: вид отчёта с M3 / M4 / M8 / ACJ по базе без русских букв (кроме данных журнала)", not cb, cb[:6])
        _r56_sandbox(check, A, ops, ac, ldb, names, rid)
        _r57_sandbox(check, A, ops, ac)
    finally:
        A.STACK_OVERRIDE, A.RUNS_PER_HOUR = saved
        db.set_override("game", None)
        db.set_override("admin", None)
        shutil.rmtree(tmp, ignore_errors=True)
        m2 = ldb("master")
        for nm in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % nm)
                m2.cursor().execute("DROP DATABASE [%s]" % nm)
            except Exception:
                pass


# ---------------------------------------------------------------- живая dev

def live(check):
    """Живая dev: права, прогоны службы, тот же код, предпросмотр на сервере (без записи), 401."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db, hostshell
    from domains import acdaily as A
    import domains
    domains.load_all()
    if config.get().on_server:
        return check("живой самотест А6.6 — с ПК", True)
    cn = db.admin()
    try:
        perm = {r["k"]: r["p"] for r in db.admin_rows(cn, "SELECT k, HAS_PERMS_BY_NAME('adm.AcDaily', 'OBJECT', a) AS p FROM (VALUES ('s', 'SELECT'), "
                                                    "('i', 'INSERT'), ('u', 'UPDATE'), ('d', 'DELETE')) v(k, a)")}
        n0 = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.AcDaily")[0]["n"]
    finally:
        cn.close()
    check("живое (asda_admin): adm.AcDaily — SELECT и INSERT есть, UPDATE и DELETE нет", perm == {"s": 1, "i": 1, "u": 0, "d": 0}, perm)
    lst = A.reports({})
    check("живое: прогоны суточного отчёта читаются (%d), служба считает в %s" % (len(lst["reports"]), lst["run_at"]), lst["run_at"] == "00:20")
    svc = [x for x in lst["reports"] if x["code_md5"] == A.code_md5()]
    if svc:
        rep = A.report({"id": str(svc[0]["id"])})
        check("живое: прогон №%d посчитан тем же кодом, что исходник на ПК (md5 %s), 14 метрик, Markdown читается" % (rep["id"], rep["code_md5"][:8]),
              len(rep["metrics"]) == 14 and rep["code_md5"] == rep["code_now"] and A.markdown({"id": str(rep["id"])})["md"].startswith("# Суточный отчёт"))
    else:
        check("живое: есть прогон, посчитанный выложенным кодом (md5 %s) — нет ни одного" % A.code_md5()[:8], False)
    py = r"@@ASTORY_SERVER_PYTHON@@"
    try:
        out = hostshell.powershell("$env:PYTHONIOENCODING='utf-8'; Set-Location '%s'; & '%s' asda_admin.py acdaily run --dry 2>&1 | Out-String"
                                   % (config.SERVICE_ROOT, py), timeout=180)
    except Exception as ex:              # ★ ревизия 56: отказ (бюджет ручных прогонов консоли сервера исчерпан и т. п.) — провал проверки, не падение
        out = "%s: %s" % (ex.__class__.__name__, ex)
    check("живое (сервер, SSH): предпросмотр ac.daily за вчера по локальным журналам стойки — без записи", "суточный отчёт античита за" in out
          and "журналов стойки" in out, out[-400:])
    cn = db.admin()
    try:
        n1 = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.AcDaily")[0]["n"]
    finally:
        cn.close()
    check("живое: живой самотест записей в adm.AcDaily не добавил (%d)" % n0, n1 == n0, (n0, n1))
    import ssl
    import urllib.error
    import urllib.request
    sc = ssl.create_default_context()
    sc.check_hostname, sc.verify_mode = False, ssl.CERT_NONE
    codes = {}
    for pth in ("/api/acdaily/list", "/api/acdaily/report"):
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=sc)).open(
                "https://%s:17890%s" % (config.SERVER_VPN_IP, pth), timeout=10)
            codes[pth] = 200
        except urllib.error.HTTPError as ex:
            codes[pth] = ex.code
        except (urllib.error.URLError, OSError) as ex:
            codes[pth] = str(ex)[:120]
    check("служба (живьём): GET /api/acdaily/list и /report без входа — 401", set(codes.values()) == {401}, codes)
