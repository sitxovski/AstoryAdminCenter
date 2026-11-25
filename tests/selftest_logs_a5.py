# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_logs_a5.py — самотест шага А5.6 «Журналы стойки» (21.11.2026; domains/logs.py, /api/logs*, web/logs.js, консоль logs).

offline(check) — белый список пути (неизвестные источник / копия / вид / файл, «..», разделители, абсолютный путь — отказ); маскировка
                 секретов (PWD=, password, токены, ключи, JSON, Bearer, аргументы UPUserLogin, длинный hex) — всегда и ДО поиска; IP / MAC —
                 по праву; время «чч:мм:сс:мс» — не адрес; уровни по источникам; ссылки на карточку; кодировки по строкам (UTF-8, cp1251
                 наших DLL, cp949 стока) и обрывок первой строки окна; хвост на подставном файле (N строк, пределы строки и ответа,
                 поиск, уровень); «следить» (тот же размер:время — данные НЕ открываются, прирост — только целые строки, файл короче —
                 заново, прирост больше предела — пропуск помечен); EventLog.txt (без «следить», тишина QUIET_S); настоящее открытие
                 файла на ПК против писателей с теми же режимами доступа, что у серверов (GameServer share READ держит; NpcServer
                 share 0 — наш дескриптор только на время чтения, os.stat ему не мешает); предел частоты; права; переводы; веб; консоль.
live(check)    — только чтение стойки по SSH: каталог, файлы журнала патчей GameServer (размер по пути = размеру потока, листинг
                 каталога не используется), хвост, «следить» без изменений не открывает данные, OLEDB LoginManager без аргументов входа,
                 EventLog без «следить», отказ обхода каталогов.
Ничего не пишет на сервер. Побочных эффектов при импорте нет.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


class _FakeIO:
    """Подставное чтение: файлы в словаре {путь: байты}, время — словарь; считает открытия данных."""

    def __init__(self):
        self.files, self.mtime, self.reads = {}, {}, 0

    def stat(self, p):
        return (len(self.files[p]), self.mtime.get(p, 1000)) + ((self.now,) if self.now is not None else ()) if p in self.files else None

    now = None

    def read(self, p, start, length, head=0):
        self.reads += 1
        return self.files[p][:head], self.files[p][start:start + length]

    def list(self, d, rx, kinds_rx=None, skip=()):
        return [], []


def offline(check):
    sys.path.insert(0, ROOT)
    from core import auth, config, i18n
    from domains import logs as L

    # ---- белый список пути
    gs = L.procs_of("patch")
    check("журналы: копии журнала патчей — 13 (GS ×3, NPC ×3, Relay ×3, ItemRelay, Operation, LoginManager, DBManager)",
          len(gs) == 13 and "ChannelManager" not in gs and gs[:3] == ["GameServer", "Indun_GameServer", "Ch2_GameServer"], gs)
    bad = [("nope", "GameServer", "PatchLog_20261119.txt", None), ("patch", "..", "PatchLog_20261119.txt", None),
           ("patch", "C:\\Windows", "x.txt", None), ("patch", "GameServer", "..\\..\\secrets\\asda_admin.ini", None),
           ("patch", "GameServer", "PatchLog_20261119.txt\\..\\x", None), ("patch", "GameServer", "PasswordSQL.txt", None),
           ("patch", "GameServer", "PatchLog_2026111.txt", None), ("gslog", "GameServer", "GameLog_20261120.txt", "Log_Patch"),
           ("gslog", "GameServer", "GameLog_20261120.txt", "..\\ConfigSet"), ("gslog", "GameServer", "GameLog_20261120.txt", None),
           ("patch", "GameServer", "PatchLog_20261119.txt", "Log_Game"), ("panel", "GameServer", "service.log", None),
           ("errlog", "GameServer", "Exception_20261121.txt", None), ("eac", "EacServer", "../eac_20261121.log", None)]
    io = _FakeIO()
    L.IO = {"stat": io.stat, "read": io.read, "list": io.list}
    try:
        why = [_refused(lambda a=a: L.tail(*a[:3], kind=a[3])) for a in bad]
        check("журналы: обход каталогов и чужие пути — отказ белым списком (%d случаев, данные не открывались)" % len(bad),
              all(why) and io.reads == 0, list(zip([b[:4] for b in bad], why)))
        check("журналы: путь собирается из корня стойки, копии, подпапки и вида", L._dir_of("gslog", "GameServer", "Log_Game")[0]
              == config.STACK_ROOT + "\\GameServer\\Log\\Log_Game" and L._dir_of("panel", "AdminCenter", None)[0] == config.SERVICE_ROOT + "\\logs"
              and L._dir_of("stack_runs", "stack_runs", None)[0] == config.DATA_DIR + "\\stack_runs")

        # ---- маскировка
        S = [("[12:28:12] [P53] журнал: подключено (DSN=joy1;UID=devgsaccount;PWD=Sekr3t!;DATABASE=joylog1)", "Sekr3t!"),
             ("EXEC UPUserLogin 'vasya','hunter22', 0, '', '' :: Execute Error", "hunter22"),
             ("EXEC UPUserLogin vasya,hunter22 :: Execute", "hunter22"),
             ('{"level":"info","token":"abc.def.ghi","password":"p@ss w"}', "abc.def.ghi"),
             ("Authorization: Bearer eyJhbGciOi.xyz", "eyJhbGciOi"), ("start keyIds=6b62ddbeb4f84985 quota=5", "6b62ddbeb4f84985"),
             ("sig=" + "a1" * 32 + " ok", "a1a1a1a1"), ("hmac " + "f" * 64, "f" * 64), ("password = 'qwe rty'", "qwe rty")]
        res = [L.mask_line(s, True) for s, _ in S]
        leaked = [S[i][1] for i, (t, n) in enumerate(res) if S[i][1] in t or n == 0]
        check("журналы: секреты маскируются всегда (PWD, UPUserLogin, JSON, Bearer, keyIds, sig, длинный hex, password = '…')", not leaked,
              [(r[0]) for r in res])
        # ★ ревизия 46 В-1: апостроф и «','» в логине / пароле, любые формы вызова — весь список аргументов скрыт
        pw = [("80004005 EXEC UPUserLogin 'ab','p'q1w2','IP1', 0, '', '', '', '' :: Execute Error", "q1w2"),
              ("EXEC UPUserLogin 'x','','y','Zz9secret', 0, '', '', '', '' :: Execute Error", "Zz9secret"),
              ("{call dbo.UPUserLogin('a','Kk7pass')}", "Kk7pass"), ("UPUserLogin 'a','Mm5pass'", "Mm5pass"),
              ("EXEC [dbo].[UPUserLogin] 'a','Nn4pass'", "Nn4pass"), ("EXECUTE UPUserLogin a,Bb3pass", "Bb3pass"),
              ("exec upuserlogin 'a','Cc2pass' :: x :: Execute Error", "Cc2pass")]
        lk = [(t, L.mask_line(t, True)[0]) for t, _ in pw]
        check("журналы (р46 В-1): UPUserLogin — весь список аргументов скрыт (апостроф, «','», {call}, dbo., [скобки], без EXEC / кавычек), хвост «:: Execute Error» сохранён",
              all(sec not in m for (t, m), (_, sec) in zip(lk, pw)) and lk[0][1].endswith(":: Execute Error") and "<аргументы скрыты>" in lk[0][1],
              [m for _, m in lk])
        keep = L.mask_line("EXEC UPCharUserid 'abc' ; EXEC UPGameServerStart 0, 1", True)[0]
        check("журналы (р46 В-1): процедуры без паролей (UPCharUserid, UPGameServerStart — реверс всех EXEC декомпилов) не трогаются",
              keep == "EXEC UPCharUserid 'abc' ; EXEC UPGameServerStart 0, 1", keep)
        # ★ ревизия 46 С-1: ключ по шаблону имени, JSON, массивы заголовков, без «=»
        c1 = [("UserPwd=Aa1 x", "Aa1"), ("DBPassword=Bb2", "Bb2"), ("db_password=Cc3", "Cc3"), ("client_secret=Dd4", "Dd4"),
              ("ClientSecret=Ee5", "Ee5"), ('{"clientSecret": "Ff6"}', "Ff6"), ('{"client_secret":"Gg7"}', "Gg7"), ("passphrase=Hh8", "Hh8"),
              ("Login User ID a/b, Pass Ii9/Jj0, IP 1", "Ii9"), ("password Kk1 next", "Kk1"),
              ('"Authorization":["Basic QWxhZGRpbjpvcGVuc2VzYW1l"]', "QWxhZGRpbjpvcGVuc2VzYW1l"), ('"Cookie":["sid=Ll2abcdef"]', "Ll2abcdef"),
              ('"Set-Cookie":["a=Mm3"]', "Mm3"), ("Proxy-Authorization: Basic Nn4xxxxxxx", "Nn4xxxxxxx"), ("x-api-key=Oo5", "Oo5"),
              ("auth_token: Pp6", "Pp6"), ("sessionId=Qq7", "Qq7")]
        lk1 = [L.mask_line(t, True)[0] for t, _ in c1]
        check("журналы (р46 С-1): ключи с префиксом / суффиксом, snake / camel / kebab, JSON, массивы Authorization / Cookie, «Pass x», «password x» — скрыты (%d случаев)" % len(c1),
              all(sec not in m for m, (_, sec) in zip(lk1, c1)), [m for m, (_, sec) in zip(lk1, c1) if sec in m])
        safe = L.mask_line("authz_status=ok SessionNum = 9 Passive Type: 3 UID=devgsaccount level=info", True)[0]
        check("журналы (р46 С-1): не секреты (authz_status, SessionNum, Passive, UID, level) не трогаются", safe ==
              "authz_status=ok SessionNum = 9 Passive Type: 3 UID=devgsaccount level=info", safe)
        # ★ ревизия 46 Н-2: идентификатор установки — под logs.view_ip
        inst = 'inst=6ed4c568572dfc53fc477de64b90fb2a "X-Asda-Install":["6ed4c568572dfc53fc477de64b90fb2a"]'
        check("журналы (р46 Н-2): inst= и X-Asda-Install скрыты без права logs.view_ip, с правом — видны",
              "6ed4c568" not in L.mask_line(inst, False)[0] and L.mask_line(inst, True)[0] == inst)
        t, _ = L.mask_line("md5 791b1a09c0ffee00112233445566778899 UID=devgsaccount SessionNum = 9 Nick Player58", True)
        check("журналы: md5 (32), UID, SessionNum и имена не трогаются", "791b1a09" in t and "devgsaccount" in t and "SessionNum = 9" in t
              and "Player58" in t, t)
        ip = "slot 0 IP 5.252.83.153 mac 2C-F0-5D-00-00-01 v6 fe80::1:2:3:4 12:28:05:586->x"
        t0, _ = L.mask_line(ip, False)
        t1, _ = L.mask_line(ip, True)
        check("журналы: IP / MAC — маска без права, время «12:28:05:586» адресом не считается; с правом — как есть",
              "5.252" not in t0 and "2C-F0" not in t0 and "12:28:05:586" in t0 and t1 == ip, t0)
        check("журналы: права logs.view / logs.view_ip — владелец и администратор (не GM и не поддержка)",
              [r for r in auth.ROLES if auth.can(r, "logs.view")] == ["owner", "admin"]
              and [r for r in auth.ROLES if auth.can(r, "logs.view_ip")] == ["owner", "admin"])

        # ---- уровни и ссылки
        lv = [L.level_of("eac", "2026-11-20 23:59:37.389 [ERR] [eos] x"), L.level_of("eac", "2026-11-20 23:59:37.389 [WRN] [main] x"),
              L.level_of("caddy", '{"level":"error","msg":"x"}'), L.level_of("patch", "[12:00:00]   [ОШИБКА]   P12 x"),
              L.level_of("patch", "[12:00:00]   [ВЫКЛ]     P08"), L.level_of("patch", "[12:00:00]   [OK]       P30"),
              L.level_of("generic", "05:11:05:797->Move_Tile() Exception...!"), L.level_of("eac", "2026-11-20 23:59:37.389 [DBG] [x] y")]
        check("журналы: уровни — EAC [ERR]/[WRN]/[DBG], caddy level, журнал патчей [ОШИБКА]/[ВЫКЛ]/[OK], сток Exception",
              lv == ["err", "warn", "err", "err", "warn", "info", "err", "debug"], lv)
        ln = L.links_of("Recv_GachaItemUse() UserIndex = 75230, Code=9879 ; CharName\tGM_MONSTER\tLevel 100; userIdx=0; Nick (null)")
        check("журналы: ссылки — учётка по UserIndex (0 — нет), имя из размеченного поля", ln == [{"k": "account", "v": 75230},
              {"k": "name", "v": "GM_MONSTER"}], ln)

        # ---- кодировки, хвост, пределы
        d = config.STACK_ROOT + "\\GameServer\\Log\\Log_Patch\\"
        p = d + "PatchLog_20261119.txt"
        body = ("[00:00:01] старт патча\r\n".encode("cp1251") + "[00:00:02] [ОШИБКА] P12 UTF8 строка\r\n".encode("utf-8")
                + b"".join(("[00:01:%02d] [OK] P%d PWD=zz%d\r\n" % (i % 60, i, i)).encode() for i in range(300)) + b"[00:09:59] partial")
        io.files[p] = body
        r = L.tail("patch", "GameServer", "PatchLog_20261119.txt", lines=5, show_ip=True)
        check("журналы: хвост 5 строк, незаконченная последняя строка показывается, отметка следить = конец файла",
              len(r["lines"]) == 5 and r["lines"][-1]["t"] == "[00:09:59] partial" and r["offset"] == len(body) and r["truncated"], r["lines"])
        r = L.tail("patch", "GameServer", "PatchLog_20261119.txt", lines=2000, show_ip=True)
        txt = [x["t"] for x in r["lines"]]
        check("журналы: строки по отдельности — cp1251 наших DLL и UTF-8 в одном файле, секреты скрыты (300 замен)",
              txt[0] == "[00:00:01] старт патча" and txt[1] == "[00:00:02] [ОШИБКА] P12 UTF8 строка" and r["masked"] == 300
              and not any("zz" in x for x in txt), txt[:3])
        r = L.tail("patch", "GameServer", "PatchLog_20261119.txt", q="zz1", show_ip=True)
        check("журналы: поиск — после маскировки (секрет подстрокой не найти)", r["matched"] == 0, r["matched"])
        r = L.tail("patch", "GameServer", "PatchLog_20261119.txt", level="err", show_ip=True)
        check("журналы: уровень «только ошибки»", [x["t"] for x in r["lines"]] == ["[00:00:02] [ОШИБКА] P12 UTF8 строка"], r["lines"])
        k = config.STACK_ROOT + "\\NpcServer\\Log_IocpNet\\Flag_20261119.Txt"
        io.files[k] = b"x" * 20000 + "\r\n11월19일12시25분49초 : Disconnect\r\n".encode("cp949") + b"\xff" * (L.LINE_MAX + 50) + b"\r\n\x01\x07ok\r\n"
        r = L.tail("iocp", "NpcServer", "Flag_20261119.Txt", scan=16 * 1024)
        tt = [x["t"] for x in r["lines"]]
        check("журналы: сток cp949 (корейский), обрывок первой строки окна отброшен, длинная строка обрезана, управляющие — точкой",
              tt[0].startswith("11월19일12시25분49초") and tt[1].endswith("…[+50]") and tt[2] == "··ok" and not tt[0].startswith("x"), tt)
        io.files[k] = b"".join(b"L%05d " % i + b"y" * 900 + b"\r\n" for i in range(2000))
        r = L.tail("iocp", "NpcServer", "Flag_20261119.Txt", lines=2000, scan=L.SCAN_MAX)
        check("журналы: ответ ≤ OUT_MAX знаков (старые строки отброшены, помечено)", sum(len(x["t"]) + 1 for x in r["lines"]) <= L.OUT_MAX
              and r["truncated"] and r["lines"][-1]["t"].startswith("L01999"), len(r["lines"]))
        check("журналы: пределы строк и окна — отказ на мусор, уровень из списка", bool(_refused(lambda: L.tail("patch", "GameServer",
              "PatchLog_20261119.txt", lines="x"))) and bool(_refused(lambda: L.tail("patch", "GameServer", "PatchLog_20261119.txt", level="all"))))

        # ---- «следить»
        r0 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", lines=3)
        n0 = io.reads
        r1 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=r0["offset"], sig=r0["sig"])
        check("журналы: следить — тот же «размер:время» → без изменений, данные НЕ открывались", r1["unchanged"] and io.reads == n0 and not r1["lines"])
        io.files[p] = body + " end\r\n[00:10:00] new1\r\n[00:10:01] new2 half".encode()
        io.mtime[p] = 2000
        cut = len(body) - len(b"[00:09:59] partial")
        r2 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=cut, sig=r0["sig"])
        check("журналы: следить — прирост: только целые новые строки, отметка — после последнего перевода строки",
              [x["t"] for x in r2["lines"]] == ["[00:09:59] partial end", "[00:10:00] new1"] and r2["offset"] == len(io.files[p]) - len(b"[00:10:01] new2 half"),
              r2["lines"])
        io.files[p] = b"[00:00:00] fresh\r\n"
        io.mtime[p] = 3000
        r3 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=r2["offset"], sig=r2["sig"])
        check("журналы: следить — файл стал короче → хвост заново (reset)", r3["reset"] and [x["t"] for x in r3["lines"]] == ["[00:00:00] fresh"])
        io.files[p] = b"[00:00:00] fresh\r\n" + b"z" * (L.FOLLOW_MAX + 100) + b"\r\n[01:00:00] tail\r\n"
        io.mtime[p] = 4000
        r4 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=r3["offset"], sig=r3["sig"])
        check("журналы: следить — прирост больше FOLLOW_MAX: читается конец, пропуск помечен, обрывок отброшен",
              r4["skipped"] > 0 and [x["t"] for x in r4["lines"]] == ["[01:00:00] tail"], (r4["skipped"], r4["lines"]))

        # ---- EventLog.txt
        e = config.STACK_ROOT + "\\NpcServer\\Event\\EventLog.txt"
        io.files[e], io.mtime[e] = b"20261121 -> Read\r\n", 10_000_000
        n0 = io.reads
        w1 = _refused(lambda: L.tail("eventlog", "NpcServer", "EventLog.txt", since=0, sig="1:1"))
        w2 = _refused(lambda: L.tail("eventlog", "NpcServer", "EventLog.txt", now_ms=10_000_000 + 3000))
        r5 = L.tail("eventlog", "NpcServer", "EventLog.txt", now_ms=10_000_000 + L.QUIET_S * 1000 + 1)
        check("журналы: EventLog.txt (share 0) — «следить» отказ, писался < 10 с назад — отказ без открытия данных, позже — читается",
              bool(w1) and bool(w2) and "3 с назад" in w2 and io.reads == n0 + 1 and r5["lines"][0]["t"] == "20261121 -> Read", (w1, w2))
        check("журналы: каталог — у EventLog нет «следить», у остальных есть; stack_runs — только своя машина",
              {s["key"]: s["follow"] for s in L.catalog()["sources"]}.get("eventlog") is False
              and all(s["follow"] for s in L.catalog()["sources"] if s["key"] != "eventlog")
              and [s["key"] for s in L.catalog()["sources"] if s["local_only"]] == ["stack_runs"])
    finally:
        L.IO = None

    # ---- настоящее открытие файла против писателей с режимами доступа серверов (Windows)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        INV = ctypes.c_void_p(-1).value
        tmp = tempfile.mkdtemp(prefix="asda_logs_")
        fp = os.path.join(tmp, "Net_20261121.Txt")
        with open(fp, "wb") as f:
            f.write(b"line1\r\nline2\r\n")

        def wopen(share, disp=3):
            h = k32.CreateFileW(fp, 0x40000000, share, None, disp, 0x80, None)
            return h, ctypes.get_last_error()

        h, _ = wopen(1)                                       # GameServer / Log_IocpNet: GENERIC_WRITE, share READ, держит весь день
        got = L._read_local(fp, 0, 100)[1] if h != INV else None
        k32.CloseHandle(h)
        f = L._open_shared(fp)
        h2, e2 = wopen(1)                                     # писатель открывает, пока читаем мы
        ok2 = h2 != INV
        k32.CloseHandle(h2)
        h3, e3 = wopen(0, 4)                                  # EventLog.txt: share 0 — пока НАШ дескриптор открыт — отказ 32 (поэтому — только на время чтения)
        f.close()
        h4, _ = wopen(0, 4)                                   # после закрытия — открывается
        st = L._stat_local(fp)                                # пока писатель share 0 держит — os.stat работает (атрибуты), чтение — «занят»
        busy = _refused(lambda: L._read_local(fp, 0, 10))
        k32.CloseHandle(h4)
        st2 = L._stat_local(fp)
        h5, _ = wopen(0, 4)                                   # os.stat дескриптор не держит — share 0 после него открывается
        k32.CloseHandle(h5)
        check("журналы: открытие на ПК — читаем, пока писатель (share READ) держит файл; писатель открывает, пока читаем мы",
              got == b"line1\r\nline2\r\n" and ok2, (got, e2))
        check("журналы: писатель share 0 (EventLog) — при нашем открытом дескрипторе отказ 32, после закрытия — открывается (дескриптор только на время чтения)",
              h3 == INV and e3 == 32 and h4 != INV, e3)
        check("журналы: при писателе share 0 os.stat работает, чтение — «занят» (не «нет»); после os.stat писатель открывает файл",
              st is not None and st[0] == 14 and busy and "занят" in busy and st2 and h5 != INV, busy)

    # ---- предел частоты
    L._thr_file.clear()
    L._thr_user.clear()
    k = ("patch", "GameServer", "", "PatchLog_20261119.txt")
    L.throttle("u1", k, now=100.0)
    t1 = _refused(lambda: L.throttle("u1", k, now=101.0))
    L.throttle("u1", k, now=102.5)
    L.throttle("u2", k, now=101.0)
    for i in range(L.PER_MIN - 2):
        L.throttle("u1", None, now=103.0 + i * 0.1)
    t2 = _refused(lambda: L.throttle("u1", None, now=110.0))
    t3 = _refused(lambda: L.throttle("u1", None, now=170.0))
    check("журналы: предел — один файл не чаще 2 с, %d запросов в минуту на пользователя (другой пользователь не мешает)" % L.PER_MIN,
          t1 and "2 с" in t1 and t2 and "в минуту" in t2 and t3 is None and isinstance(L.Throttled("x"), Exception))
    L._thr_file.clear()
    L._thr_user.clear()

    # ★ ревизия 46 С-2: нормализованный ключ, бюджет байт, семафор
    L._thr_file.clear()
    L._thr_user.clear()
    L.throttle("u9", ("patch", "GameServer", "", "PatchLog_20261119.txt"), now=500.0)
    nk = _refused(lambda: L.throttle("u9", ("PATCH", "gameserver", "", "patchlog_20261119.TXT"), now=500.5))
    L._budget.clear()
    L.charge("u9", L.BYTES_USER_MIN - 10, now=600.0)
    b1 = _refused(lambda: L.charge("u9", 100, now=601.0))
    L.charge("u9", 100, now=661.0)
    L._budget.clear()
    L.charge("a", L.BYTES_USER_MIN - 1, now=700.0)
    L.charge("b", L.BYTES_USER_MIN - 1, now=700.0)
    L.charge("c", L.BYTES_USER_MIN - 1, now=700.0)
    b2 = _refused(lambda: L.charge("d", 1024 * 1024, now=700.5))
    L._budget.clear()
    got = [L._SEM.acquire(blocking=False) for _ in range(L.READERS)]
    wait0, L.READ_WAIT_S = L.READ_WAIT_S, 0.05
    io2 = _FakeIO()
    L.IO = {"stat": io2.stat, "read": io2.read, "list": io2.list}
    pp = config.STACK_ROOT + "\\GameServer\\Log\\Log_Patch\\PatchLog_20261119.txt"
    io2.files[pp] = b"a\r\n"
    try:
        sm = _refused(lambda: L.tail("patch", "GameServer", "PatchLog_20261119.txt"))
    finally:
        for g in got:
            if g:
                L._SEM.release()
        L.READ_WAIT_S = wait0
    check("журналы (р46 С-2): пауза «один файл» без учёта регистра имени; бюджет байт на пользователя и на всю службу; семафор READERS — занято → 429, данные не читались",
          nk and "2 с" in nk and b1 and "на пользователя" in b1 and b2 and "на всех" in b2 and sm and "занята" in sm and io2.reads == 0
          and isinstance(L.Throttled("x"), L.OpRefused if hasattr(L, "OpRefused") else Exception), (nk, b1, b2, sm))
    # ★ ревизия 46 Н-1: файл переписан, а не короче — отпечаток начала другой → reset
    io2.files[pp] = b"[00:00:01] old one\r\n[00:00:02] old two\r\n"
    r0 = L.tail("patch", "GameServer", "PatchLog_20261119.txt")
    io2.files[pp] = b"[00:00:09] NEW start line longer than before\r\n[00:00:10] next\r\n"
    io2.mtime[pp] = 5000
    r1 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=r0["offset"], sig=r0["sig"], head=r0["head"])
    io2.files[pp] = b"[00:00:09] NEW start line longer than before\r\n[00:00:10] next\r\n[00:00:11] more\r\n"
    io2.mtime[pp] = 6000
    r2 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=r1["offset"], sig=r1["sig"], head=r1["head"])
    check("журналы (р46 Н-1): переписанный файл не короче отметки — reset по отпечатку начала; дописанный — только новые строки",
          r1["reset"] and r1["lines"][0]["t"].startswith("[00:00:09] NEW") and not r2["reset"] and [x["t"] for x in r2["lines"]] == ["[00:00:11] more"],
          (r1["reset"], r2["lines"]))
    # ★ ревизия 46 Н-4: UTF-16
    u16 = "\ufeff[00:00:01] UTF16 строка PWD=Rr8secret\r\n[00:00:02] вторая\r\n".encode("utf-16-le")
    io2.files[pp] = u16
    r3 = L.tail("patch", "GameServer", "PatchLog_20261119.txt")
    io2.files[pp] = u16 + "[00:00:03] третья\r\n".encode("utf-16-le")
    io2.mtime[pp] = 7000
    r4 = L.tail("patch", "GameServer", "PatchLog_20261119.txt", since=r3["offset"], sig=r3["sig"], head=r3["head"])
    check("журналы (р46 Н-4): UTF-16 (метка FF FE) — декодируется до разбиения, секрет скрыт; «следить» — по целым строкам UTF-16",
          r3["utf16"] and [x["t"] for x in r3["lines"]] == ["[00:00:01] UTF16 строка PWD=•••", "[00:00:02] вторая"]
          and [x["t"] for x in r4["lines"]] == ["[00:00:03] третья"], (r3["lines"], r4["lines"]))
    # ★ ревизия 46 С-3: тишина EventLog — по часам сервера из stat
    ee = config.STACK_ROOT + "\\NpcServer\\Event\\EventLog.txt"
    io2.files[ee], io2.mtime[ee], io2.now = b"x\r\n", 10_000_000, 10_000_000 + 2000
    sv = _refused(lambda: L.tail("eventlog", "NpcServer", "EventLog.txt"))
    io2.now = None
    L.IO = None
    src_rd = open(os.path.join(ROOT, "domains", "logs.py"), encoding="utf-8").read()
    body = src_rd[src_rd.index("def _read_remote"):src_rd.index("# подмена для самотеста")]
    check("журналы (р46 С-3): тишина EventLog — по «сейчас» сервера (часы ПК не участвуют); с ПК файл закрывается ДО кодирования и вывода по SSH",
          sv and "2 с назад" in sv and body.index("$fs.Close()") < body.index("ToBase64String") and "UtcNow" in src_rd, sv)
    sys.path.insert(0, ROOT)
    import asda_admin as A0
    check("журналы (р46 Н-3): консоль «следить» — опрос раз в 10 с, не дольше 30 мин", A0.LOGS_FOLLOW_POLL_S >= 5 and A0.LOGS_FOLLOW_MAX_MIN <= 30)
    L._thr_file.clear()
    L._thr_user.clear()
    L._budget.clear()

    # ---- переводы
    i18n.set_lang("en")
    try:
        texts = ["неизвестный источник журнала «x»", "копии «X» у источника «patch» нет", "файл «a» не подходит под шаблон источника «patch»",
                 "файл занят процессом-писателем (открыт им без общего доступа) — повторите через несколько секунд",
                 "слишком частый опрос журнала — один файл не чаще раза в 2 с", "журнал не прочитан (SSH): код 255: x"]
        texts += ["слишком много прочитано журналов за минуту — не больше 32 МБ на пользователя, подождите",
                  "служба занята чтением журналов (одновременно не больше 2) — повторите через несколько секунд"]
        texts += [s["title"] for s in L.catalog()["sources"]] + [s["rotation"] for s in L.catalog()["sources"]] + [s["how"] for s in L.catalog()["sources"]]
        miss = [t for t in texts if i18n.tr(t) == t]
        check("журналы: переводы EN — отказы и каталог источников (%d текстов)" % len(texts), not miss, miss[:4])
    finally:
        i18n.set_lang("ru")

    # ---- веб и маршруты
    js = open(os.path.join(ROOT, "web", "logs.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("журналы: веб — без innerHTML / insertAdjacentHTML, строки журнала текстовыми узлами, вкладка в меню и маршрут, скрипт подключён",
          "innerHTML" not in js and "insertAdjacentHTML" not in js and "createTextNode" in js and "lgText(ln.t)" in js
          and "st.sig = st.offset = st.head = null" in js and "if (st.offset === null) return;" in js
          and '["#/logs", "Журналы стойки", "logs.view"' in app and 'case "logs": return viewLogs(my);' in app and '/logs.js' in idx)
    check("журналы: маршруты /api/logs, /api/logs/files, /api/logs/tail — право logs.view, IP по logs.view_ip, предел частоты — 429",
          srv.count('perm="logs.view")') == 3 and 'auth.can(u["role"], "logs.view_ip")' in srv and "HttpError(429" in srv
          and srv.count("logs.throttle(") == 2 and "logs.norm_key(*key)" in srv and "user=u[\"login\"]" in srv.replace("'", '"'))
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "logs.js")], capture_output=True, timeout=60)
        check("журналы: node --check web/logs.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("журналы: node --check web/logs.js (node не запустился)", False, str(ex))

    # ---- консоль
    sys.path.insert(0, ROOT)
    import asda_admin as A
    bad_keys = []
    for a in (["--nope"], ["--lines"], ["--minutes", "5"], ["--grep", "--level"]):
        try:
            A.logs_args(a)
            bad_keys.append(a)
        except SystemExit:
            pass
    pos, opt = A.logs_args(["patch", "GameServer", "--lines", "50", "--follow", "--minutes", "3"])
    check("журналы: консоль — неизвестный ключ, ключ без значения, --minutes без --follow — отказ; разбор позиционных и ключей",
          not bad_keys and pos == ["patch", "GameServer"] and opt == {"--lines": "50", "--follow": True, "--minutes": "3"}, bad_keys)
    hp = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60)
    nc = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "logs"], capture_output=True, timeout=60)
    check("журналы: консоль — --help печатает справку с logs и ничего не делает; logs без действия — отказ",
          hp.returncode == 0 and "logs …" in hp.stdout.decode("utf-8", "replace") and nc.returncode != 0
          and "нужно действие" in nc.stderr.decode("utf-8", "replace"))


def live(check):
    """Только чтение стойки (консоль ПК — SSH; служба — локально)."""
    sys.path.insert(0, ROOT)
    from core import hostshell
    from core.ops import OpRefused
    from domains import logs as L
    cat = L.catalog()
    check("журналы (живьём): каталог — 14 источников", len(cat["sources"]) == 14, [s["key"] for s in cat["sources"]])
    try:
        fl = L.files("patch", "GameServer")
    except OpRefused as ex:
        check("журналы (живьём): файлы журнала патчей GameServer прочитаны", False, str(ex))
        return
    check("журналы (живьём): файлы журнала патчей GameServer — есть, новые сверху, размеры > 0",
          not fl["missing"] and fl["files"] and fl["files"][0]["size"] > 0
          and all(fl["files"][i]["mtime"] >= fl["files"][i + 1]["mtime"] for i in range(len(fl["files"]) - 1)), fl["files"][:2])
    # файл, который писатель держит открытым весь день: размер по пути = длине потока, листинг каталога (Get-ChildItem папки) — устарел
    try:
        ping = L.files("gslog", "GameServer", "Log_AliveCheck")["files"][0]
        out = hostshell.powershell("$p='%s\\GameServer\\Log\\Log_AliveCheck\\%s'; $fs=[IO.File]::Open($p,'Open','Read','ReadWrite'); "
                                   "$n=$fs.Length; $fs.Close(); Write-Output ('LEN|' + $n)" % (L.config.STACK_ROOT, ping["name"]), 60)
        n = int(re.search(r"LEN\|(\d+)", out).group(1))
        check("журналы (живьём): Ping сегодня (GameServer держит весь день) — размер списка по пути ≈ длине потока (не 0 из записи каталога)",
              ping["size"] > 0 and abs(n - ping["size"]) < 64 * 1024, (ping, n))
    except (OpRefused, hostshell.HostError, AttributeError, IndexError) as ex:
        check("журналы (живьём): Ping GameServer прочитан", False, str(ex))
    name = fl["files"][-1]["name"] if len(fl["files"]) > 1 else fl["files"][0]["name"]     # старый файл — не меняется
    r = L.tail("patch", "GameServer", name, lines=50)
    check("журналы (живьём): хвост 50 строк старого журнала патчей, секреты (PWD=) не видны",
          r["lines"] and len(r["lines"]) <= 50 and not any(re.search(r"(?i)PWD=(?!•••)", x["t"]) for x in r["lines"]), r["path"])
    r2 = L.tail("patch", "GameServer", name, since=r["offset"], sig=r["sig"])
    check("журналы (живьём): «следить» по старому файлу — без изменений (данные не открывались)", r2["unchanged"], r2.get("sig"))
    try:
        o = L.files("oledb", "LoginManager")
        if o["files"]:
            ro = L.tail("oledb", "LoginManager", o["files"][0]["name"], lines=200, q="Login")
            ul = [x["t"] for x in ro["lines"] if "UPUserLogin" in x["t"]]
            check("журналы (живьём): OLEDB LoginManager — весь список аргументов UPUserLogin скрыт (ревизия 46 В-1), строки есть",
                  bool(ul) and all(re.search(r"UPUserLogin <аргументы скрыты>( :: .*)?$", t) for t in ul), (ro["matched"], ul[:1]))
    except OpRefused as ex:
        check("журналы (живьём): OLEDB LoginManager прочитан", False, str(ex))
    w = _refused(lambda: L.tail("eventlog", "NpcServer", "EventLog.txt", since=0, sig="0:0"))
    check("журналы (живьём): EventLog.txt — «следить» отказ (до чтения данных)", bool(w) and "без общего доступа" in w, w)
    t = _refused(lambda: L.tail("patch", "GameServer", "..\\..\\..\\AdminCenter\\secrets\\asda_admin.ini"))
    check("журналы (живьём): обход каталогов — отказ белым списком", bool(t), t)
