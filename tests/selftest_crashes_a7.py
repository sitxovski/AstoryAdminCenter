# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_crashes_a7.py — самотест шага А7.2 «Сбои клиента» (23.11.2026; domains/crashes.py, sql/adminc_27_crashes.sql, /api/crashes,
web/crashes.js, операции crash.sync и crash.alog_prune, консоль asda_admin.py crashes show|sync|prune, AstoryClient/Tools/LogSeal/fetch_and_decrypt.py
по SSH, проверки adminc_10, откат adminc_99).

offline(check)      — права (crash.view — owner, admin; crash.sync и crash.prune — owner), операции (crash.sync — исполнитель «pc»; crash.alog_prune —
                      слово и второй фактор, не заданием), маршрут; разбор summary.txt и CrashContext движка, подпись места, начало сессии, версия
                      по времени и «на границе»; НАСТОЯЩИЕ пакеты _player_logs (если ключ на этом ПК): разбор в памяти = summary.txt, который
                      расшифровка FetchAndDecrypt положила на диск (второй способ), время падения = сведениям .acrash.txt; свои пакеты своим ключом:
                      не расшифрован (чужой ключ, порча GCM), без сводки, повтор того же пакета и того же падения в другом пакете; сбор по scp на
                      подменах: целость SHA-256 против .json, «не забран», список хранилища по правилам приёмника; утечки (IP, пути, exe=, имя
                      пользователя); НАСТОЯЩИЕ PowerShell-скрипты квоты, кандидатов и удаления на своей папке этого ПК (.acrash и свежие .alog не
                      трогаются, .json пакета падения остаётся); тексты без «; », переводы EN, веб, adminc_27, выкладка, adminc_10 / 99, консоль,
                      импорт без побочных эффектов.
sandbox(check, ldb) — СВОЯ база LocalDB: adminc_02 + adminc_27 дважды; до установки — «не установлен»; push_pc: новые строки, тот же итог — только
                      отметка, изменение строки; группы (adm.ClientCrashSig) = пересчёту; summary() — частота за сутки и 7 суток, дни, ссылка на
                      карточку; устаревание; crash.sync через ops.run (журнал); crash.alog_prune — без слова, чужой отпечаток, без второго фактора из
                      браузера — отказ, консолью со словом — удаление на подмене; маршрут /api/crashes (EN).
live(check)         — живая dev: список хранилища по SSH = квоте службы (второй способ), права asda_admin на adm.ClientCrash*, crash.sync с ПК (пишет
                      только AsdaAdmin) и чтение обратно (sha), служба на сервере (SSH): та же сводка и квота, код LogSeal на сервере — PortCodeError,
                      предпросмотр удаления — без удаления; без входа — 401.
Побочных эффектов при импорте нет.
"""
import ast
import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
UE_TOOLS = os.path.join(PORT, "AstoryClient", "Tools")
LOGSEAL = os.path.join(PORT, "AstoryClient", "Tools", "LogSeal")
CYR = re.compile("[А-Яа-яЁё]")
SUMMARY = ("исключение: 0xC0000005 EXCEPTION_ACCESS_VIOLATION, флаги 0x0, адрес AsdaReborn-Win64-Shipping.exe+0x2C2CE15\r\n"
           "доступ: чтение по адресу 0xFFFFFFFFFFFFFFFF\r\n"
           "ошибка: Assertion failed: x [File:C:\\Users\\John Smith\\build\\Foo.cpp] [Line: 12] from 10.1.2.3\r\n"
           "нить: 13944\r\nстек:\r\n"
           "  #00 AsdaReborn-Win64-Shipping.exe+0x2C2CE15\r\n  #01 KERNELBASE.dll+0xC408A\r\n  #02 AsdaReborn-Win64-Shipping.exe+0x1436B95\r\n"
           "  #03 AsdaReborn-Win64-Shipping.exe+0x43B5118\r\n  #04 AsdaReborn-Win64-Shipping.exe+0x43B69DC\r\n  #05 ntdll.dll+0x7EE4C\r\n")
XML = ("<FGenericCrashContext><RuntimeProperties><CrashGUID>UECC-Windows-ABC_0000</CrashGUID><CrashType>Hang</CrashType>"
       "<ErrorMessage>GameThread timed out waiting for RenderThread after 120.00 seconds:\n  0x1 ntdll.dll!UnknownFunction []</ErrorMessage>"
       "<UserName>john</UserName><BaseDir>C:/Users/john/Game/</BaseDir>"
       "<PCallStack>\n\n                     ntdll 0x00007fff32eb0000 + 9d144           \n"
       "                AsdaReborn-Win64-Shipping 0x00007ff64ec70000 + 143c19e         \n"
       "               igd10iumd64 0x00007fff25f50000 + 110539          \n</PCallStack></RuntimeProperties></FGenericCrashContext>")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _paths():
    for p in (ROOT, UE_TOOLS, LOGSEAL, HERE):
        if p not in sys.path:
            sys.path.insert(0, p)


def _rec_file(name, data):
    """Записи файла пакета падения (как клиент: FBEGIN u16 имя u64 размер, FDATA, FEND)."""
    import asda_logseal as LS
    nb = name.encode("utf-8")
    return [bytes([LS.REC_FBEGIN]) + struct.pack("<H", len(nb)) + nb + struct.pack("<Q", len(data)), bytes([LS.REC_FDATA]) + data,
            bytes([LS.REC_FEND])]


def _pkg(xy, kind=4, summary=SUMMARY, pid=8920, t_utc="2026-10-25T20:59:59.379Z", t_loc="2026.10.26 00:59:59",
         session="20261026-005505_8920.alog", xml=None, extra=b""):
    """Свой пакет падения своим ключом (asda_logseal._seal_segment_py — эмуляция клиента)."""
    import asda_logseal as LS
    info = ("kind=%d\ntime=%s\ntime_utc=%s\npid=%d\nconfig=Shipping\nexe=C:\\Program Files\\AStory\\x.exe\nsession=%s\n%s"
            % (kind, t_loc, t_utc, pid, session, extra.decode())).encode()
    recs = []
    if summary is not None:
        recs += _rec_file("summary.txt", summary.encode("utf-8"))
    if xml is not None:
        recs += _rec_file("Crashes/UECC-Windows-ABC_0000/CrashContext.runtime-xml", xml.encode("utf-8"))
    recs += _rec_file("minidump.dmp", b"MDMP" + secrets.token_bytes(64))
    return LS._seal_segment_py(xy, kind, recs, info)


def _local_ps(script):
    """PowerShell этой машины (тот же перевод, что core/hostshell: UTF-8 вывод, -EncodedCommand)."""
    wrapped = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';" + script
    enc = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], capture_output=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[:300])
    return r.stdout.decode("utf-8", "replace")


def offline(check):
    _paths()
    from core import auth, config, i18n, ops
    import domains
    domains.load_all()
    from domains import crashes as C
    import fetch_and_decrypt as F
    import asda_logseal as LS
    roles = ("owner", "admin", "gm", "support")
    check("сбои: crash.view — owner, admin (gm нет — логин заявлен клиентом, кухня сборки); crash.sync и crash.prune — owner",
          {r for r in roles if auth.can(r, "crash.view")} == {"owner", "admin"} and {r for r in roles if auth.can(r, "crash.sync")} == {"owner"}
          and {r for r in roles if auth.can(r, "crash.prune")} == {"owner"})
    so, po = ops.REGISTRY.get("crash.sync"), ops.REGISTRY.get("crash.alog_prune")
    check("сбои: crash.sync — исполнитель «pc», без отката, без второго фактора; crash.alog_prune — owner, слово alogprune, второй фактор, без "
          "отката, заданием не ставится (schedule_runner нет)",
          so is not None and so.schedule_runner == "pc" and not so.reversible and not ops.needs_two_factor("crash.sync")
          and po is not None and po.perm == "crash.prune" and po.confirm_word == "alogprune" and ops.needs_two_factor("crash.alog_prune")
          and not po.reversible and not getattr(po, "schedule_runner", None))
    fn, perm = _route("/api/crashes")
    check("сбои: маршрут GET /api/crashes — право crash.view", fn is not None and perm == "crash.view", perm)
    ini = _read(ROOT, "domains", "__init__.py")
    check("сбои: раздел crashes в domains.load_all (операции crash.* зарегистрированы и до первого открытия раздела: задания ПК, /api/ops)",
          "crashes" in [x.strip() for x in ini.split("from . import", 1)[1].split("#", 1)[0].split(",")])
    # ---- разбор
    p = C.parse_summary(SUMMARY)
    check("сбои: разбор summary.txt (формат MakeCrashSummary) — код 0xC0000005, адрес, доступ, 6 кадров модуль+0xRVA; в тексте ошибки путь и IP "
          "вырезаны (имени пользователя нет)",
          p["code"] == "0xC0000005" and p["addr"] == "AsdaReborn-Win64-Shipping.exe+0x2C2CE15" and p["access"] == "чтение 0xFFFFFFFFFFFFFFFF"
          and len(p["frames"]) == 6 and p["frames"][1] == "KERNELBASE.dll+0xC408A" and "John" not in p["error"] and "10.1.2.3" not in p["error"]
          and "Foo.cpp" in p["error"] and "<IP>" in p["error"], p)
    x = C.parse_crash_context(XML)
    check("сбои: разбор CrashContext движка (пакет вида 5) — код UE:Hang, кадры «модуль 0xбаза + rva» → модуль.exe/.dll+0xRVA, CrashGUID; UserName "
          "и BaseDir не берутся",
          x["code"] == "UE:Hang" and x["frames"] == ["ntdll.dll+0x9D144", "AsdaReborn-Win64-Shipping.exe+0x143C19E", "igd10iumd64.dll+0x110539"]
          and x["guid"] == "UECC-Windows-ABC_0000" and "john" not in json.dumps(x), x)
    s1 = C.signature("0xC0000005", p["frames"])
    s2 = C.signature("0xC0000005", p["frames"][:5] + ["ntdll.dll+0x1"])
    s3 = C.signature("0xC0000005", [p["frames"][0], p["frames"][2], "AsdaReborn-Win64-Shipping.exe+0x1"])
    s4 = C.signature("0x00008000", p["frames"])
    s5 = C.signature("UE:Hang", ["ntdll.dll+0x9D144", "d3d11.dll+0x12EB6B"])
    check("сбои: подпись места = код + первые 3 кадра exe — чужие кадры между ними не влияют, 4-й кадр exe не влияет, другой 3-й или другой код — "
          "другая подпись; кадров exe нет — первые кадры стека с пометкой",
          s1[0] == s2[0] and s1[0] != s3[0] and s1[0] != s4[0] and s1[2] == 4 and "кадров exe нет" in s5[1] and s5[2] == 0 and len(s1[0]) == 12,
          (s1, s2, s3, s4, s5))
    e = ["AsdaReborn-Win64-Shipping.exe+0x%X" % x for x in (0x1436B95, 0x43B5118, 0x43B69DC)]
    g1 = C.signature("0x00008000", ["KERNELBASE.dll+0xC408A"] + e + ["AsdaReborn-Win64-Shipping.exe+0x43A80C4", "AsdaReborn-Win64-Shipping.exe+0x43B1039"], "Fatal error!")
    g2 = C.signature("0x00008000", ["KERNELBASE.dll+0xC408A"] + e + ["AsdaReborn-Win64-Shipping.exe+0x43A240D", "AsdaReborn-Win64-Shipping.exe+0x43A27F5"], "Fatal error!")
    g3 = C.signature("0x00008000", ["KERNELBASE.dll+0xC408A"] + e + ["AsdaReborn-Win64-Shipping.exe+0x43A80C4", "AsdaReborn-Win64-Shipping.exe+0x43B1039"], "")
    a1 = C.signature("0x00004000", e, "Assertion failed: Index >= 0 [File:Foo.cpp] [Line: 12]")
    a2 = C.signature("0x00004000", e, "Assertion failed: Ptr != nullptr [File:Bar.cpp] [Line: 99]")
    a3 = C.signature("0x00004000", e, "Assertion failed: Index >= 0 [File:Foo.cpp] [Line: 13]")
    check("сбои (р75 М-3): у кодов движка подпись — не общий путь отчёта: GPU (0x8000) с одинаковыми первыми 3 кадрами exe и разными 4–5-м — разные "
          "места, «Fatal error!» не влияет; assert (0x4000) с одинаковыми кадрами — по тексту ошибки без чисел (другой текст — другое место, другая "
          "строка — то же)", g1[0] != g2[0] and g1[0] == g3[0] and "пропущено 3 кадра" in g1[1] and a1[0] != a2[0] and a1[0] == a3[0],
          (g1, g2, a1, a2, a3))
    su = C.session_utc({"session": "20261026-005505_8920.alog", "time": "2026.10.26 00:59:59", "time_utc": "2026-10-25T20:59:59.379Z"})
    bad_su = [C.session_utc({"session": "x", "time": "2026.10.26 00:59:59", "time_utc": "2026-10-25T20:59:59Z"}),
              C.session_utc({"session": "20261028-005505_1.alog", "time": "2026.10.26 00:59:59", "time_utc": "2026-10-25T20:59:59Z"})]
    check("сбои: начало сессии в UTC — имя журнала сессии (местное) минус смещение time − time_utc (+4 ч) = 20:55:05; мусор и «сессия позже падения» — нет",
          su == datetime.datetime(2026, 10, 25, 20, 55, 5) and bad_su == [None, None], (su, bad_su))
    rels = [(datetime.datetime(2026, 10, 1), "alpha-1.0.0-10.2026"), (datetime.datetime(2026, 10, 5), "alpha-1.0.1-10.2026")]
    v = [C.version_at(datetime.datetime(2026, 10, 3), rels, "session"), C.version_at(datetime.datetime(2026, 10, 5, 3), rels, "crash"),
         C.version_at(datetime.datetime(2026, 9, 1), rels, "sealed"), C.version_at(None, rels, "none"), C.version_at(datetime.datetime(2026, 10, 3), [], "crash")]
    check("сбои: версия по времени — выпуск, действовавший на это время; ближе 12 ч к выпуску — «на границе, возможна прежняя»; раньше первого выпуска, "
          "нет времени, пустой releases.log — версии нет с причиной",
          v[0][:2] == ("alpha-1.0.0-10.2026", "session") and v[1][0] == "alpha-1.0.1-10.2026" and "возможна прежняя alpha-1.0.0-10.2026" in v[1][2]
          and v[2][0] is None and "раньше первого выпуска" in v[2][2] and v[3][0] is None and v[4][0] is None and "пуст" in v[4][2], v)
    rl = P.dev_text(PORT, "Releases", "releases.log")                # ★ 25.11 (К-3): Releases — только среда разработчика
    if rl is None:
        P.skip("сбои: настоящий releases.log → выпуски alpha", "нет Releases/releases.log")
    else:
        ar = C.alpha_releases(rl)
        n_alpha = sum(1 for ln in rl.splitlines() if "\talpha-" in ln)
        check("сбои: releases.log → выпуски alpha по возрастанию тем же разбором, что «Выпуски» (число = строкам alpha в файле, второй способ — grep)",
              len(ar) == n_alpha and ar == sorted(ar) and all(x[1].startswith("alpha-") for x in ar), (len(ar), n_alpha))
    # ---- свои пакеты своим ключом
    d, xy = LS.gen_keypair()
    d2, xy2 = LS.gen_keypair()
    keys = lambda kid: (d, xy) if kid == LS.key_id(xy) else None
    tmp = tempfile.mkdtemp(prefix="asda_crash_")
    try:
        def put(name, data, meta=None):
            fp = os.path.join(tmp, name)
            with open(fp, "wb") as f:
                f.write(data)
            return fp
        good = put("a.acrash", _pkg(xy))
        r = C.read_package(good, LS, keys, {"account_claimed": "Player22", "account_status": "ok", "received_utc": "2026-10-25T21:00:05.594Z",
                                           "sha256": hashlib.sha256(open(good, "rb").read()).hexdigest(), "ip": "9.9.9.9", "install": "ab" * 16})
        row = C.finish(r, rels + [(datetime.datetime(2026, 10, 25, 12), "alpha-3.0.2-10.2026")])
        foreign = C.read_package(put("b.acrash", _pkg(xy2)), LS, keys)
        raw = bytearray(_pkg(xy))
        raw[-5] ^= 1
        gcm = C.read_package(put("c.acrash", bytes(raw)), LS, keys)
        nos = C.read_package(put("d.acrash", _pkg(xy, summary=None)), LS, keys)
        k5 = C.read_package(put("e.acrash", _pkg(xy, kind=5, summary=None, xml=XML, extra=b"note=old\n")), LS, keys)
        nolog = C.read_package(good, LS, keys, {"account_claimed": "bob", "account_status": "not_found"})
        check("сбои: свой пакет своим ключом — итог ok, логин нижним регистром (только account_status ok), время падения и начала сессии, подпись, "
              "версия «по времени начала сессии»; в строке сводки нет exe=, IP, install, пути (утечек нет)",
              r["status"] == "ok" and r["login"] == "Player22" and row["crash_utc"] == "2026-10-25 20:59:59" and row["session_utc"] == "2026-10-25 20:55:05"
              and row["sig"] == s1[0] and row["version"] == "alpha-3.0.2-10.2026" and row["version_basis"] == "session" and nolog["login"] is None
              and not C.leaks(json.dumps(row, ensure_ascii=False)) and "Program Files" not in json.dumps(row), (row, C.leaks(json.dumps(row))))
        check("сбои: чужой ключ — «не расшифрован: нет закрытого ключа»; порча кадра — «тег GCM не сошёлся»; без summary.txt — «без сводки»; пакет вида 5 — "
              "код UE:Hang, время — упаковки (основание sealed), ключ падения — CrashGUID",
              foreign["status"] == "unread" and "нет закрытого ключа" in foreign["status_note"] and gcm["status"] in ("unread", "ok")
              and ("GCM" in gcm["status_note"] or "часть сегментов" in gcm["status_note"]) and nos["status"] == "nosummary"
              and k5["code"] == "UE:Hang" and k5["basis"] == "sealed" and k5["key"] == "ue:UECC-Windows-ABC_0000" and k5["crash_utc"] is None,
              (foreign["status_note"], gcm["status"], gcm["status_note"], nos["status"], k5.get("code"), k5.get("basis")))
        # ---- сбор: раскладка приёмника, повторы, scp на подменах, «не забран»
        srv = os.path.join(tmp, "srv")
        dest = os.path.join(tmp, "dest")
        items = [("Player22", "2026-10-26", "20261026-000005_aaaaaaaaaaaaaaaa.acrash", _pkg(xy, pid=1)),
                 ("Player22", "2026-10-26", "20261026-000006_bbbbbbbbbbbbbbbb.acrash", None),                 # тот же пакет (байты) — повтор
                 ("_unknown", "2026-10-27", "20261027-000007_cccccccccccccccc.acrash", _pkg(xy, pid=1)),       # то же падение, другие байты — повтор
                 ("Player59", "2026-10-28", "20261028-000008_dddddddddddddddd.acrash", _pkg(xy, pid=2, t_utc="2026-10-27T22:43:37.864Z")),
                 ("Player54", "2026-10-25", "20261025-000009_eeeeeeeeeeeeeeee.acrash", _pkg(xy, pid=3)),            # .json с чужим sha — порча в пути
                 ("Player15", "2026-10-19", "20261019-000010_ffffffffffffffff.acrash", _pkg(xy, pid=4))]           # копирование падает — «не забран»
        items[1] = (items[1][0], items[1][1], items[1][2], items[0][3])
        for lg, day, n, data in items:
            dd = os.path.join(srv, lg, day)
            os.makedirs(dd, exist_ok=True)
            with open(os.path.join(dd, n), "wb") as f:
                f.write(data)
            sha = hashlib.sha256(data).hexdigest() if lg != "Player54" else "0" * 64
            with open(os.path.join(dd, n[:-7] + ".json"), "w", encoding="utf-8") as f:
                json.dump({"file": n, "account_claimed": lg, "account_status": "ok" if not lg.startswith("_") else "none", "sha256": sha,
                           "received_utc": "2026-10-26T00:00:05.000Z", "ip": "1.2.3.4", "install": "cd" * 16}, f)
        listing = [(lg, day, n, len(data)) for lg, day, n, data in items] + [("service", "2026-10-26", "x.acrash", 1)]
        saved = F.scp_get
        calls = []

        def fake_get(sources, dest_dir, timeout=0):
            calls.append(len(sources))
            missing = []
            for s in sources:
                rel = s.split(":", 1)[1].replace(F.REMOTE_ROOT.replace("\\", "/") + "/", "")
                if rel.startswith("H:"):
                    rel = rel.split("LogDrop/", 1)[1]
                if "Player15" in rel:
                    missing.append(rel)
                    continue
                src = os.path.join(srv, *rel.split("/"))
                if os.path.isfile(src):
                    shutil.copy2(src, dest_dir)
                else:
                    missing.append(rel)
            if missing:
                raise RuntimeError("scp, код 1: нет %s" % missing[0])
        F.scp_get = fake_get
        try:
            snap = C.pc_collect(fetch=True, dest=dest, listing=[x for x in listing if F.LOGIN_DIR_RE.match(x[0]) and x[0] != "service"],
                                tools=(F, LS), rel_text=(rl, ""), keys=keys)
        finally:
            F.scp_get = saved
        st = snap["stats"]
        by = {r["file"]: r for r in snap["rows"]}
        fetched = F.load_state(dest)
        check("сбои сбор: scp пачкой с .json на папку дня; SHA-256 копии ≠ .json — копия стёрта, в «забранное» не записана, ошибка названа; копирование "
              "упало — строка «не забран»; тот же пакет (SHA-256) и то же падение в другом пакете (pid + время) — повторы, в сводку не идут",
              st["on_server"] == 6 and st["dups"] == 2 and st["notfetched"] == 2 and len(snap["rows"]) == 4
              and any("SHA-256 копии" in e for e in snap["errors"]) and "Player54/2026-10-25/20261025-000009_eeeeeeeeeeeeeeee.acrash" not in fetched
              and not os.path.exists(os.path.join(dest, "Player54", "2026-10-25", "20261025-000009_eeeeeeeeeeeeeeee.acrash"))
              and by["20261019-000010_ffffffffffffffff.acrash"]["status"] == "notfetched"
              and by["20261028-000008_dddddddddddddddd.acrash"]["login"] == "Player59" and min(calls) >= 1,
              (st, snap["errors"], sorted(by)))
        check("сбои сбор (р75 К-3): пакет скопирован, но расшифровка FetchAndDecrypt не удалась (ключ этого ПК к нему не подходит) — в «забранное» "
              "не записан, следующий запуск возьмёт его заново", "Player59/2026-10-28/20261028-000008_dddddddddddddddd.acrash" not in fetched
              and os.path.exists(os.path.join(dest, "Player59", "2026-10-28", "20261028-000008_dddddddddddddddd.acrash")), sorted(fetched))
        # ---- р75 М-1: обрыв scp на первом файле пачки (файл записан частично, .json не дошёл)
        dest2 = os.path.join(tmp, "dest2")
        lg1, dy1, n1, data1 = items[3]
        lst1 = [(lg1, dy1, n1, len(data1))]
        state = {"n": 0}

        def cut_get(sources, dest_dir, timeout=0):
            state["n"] += 1
            if state["n"] == 1:                              # первая пачка: половина файла, без .json, ошибка
                with open(os.path.join(dest_dir, n1), "wb") as f:
                    f.write(data1[:len(data1) // 2])
                raise RuntimeError("scp не уложился в 900 с")
            fake_get(sources, dest_dir)
        ok1, er1 = F.ssh_fetch(lst1, dest2, get=cut_get, log=lambda x: None)
        state["n"] = -10                                     # повтор по одному тоже обрывается: файл не должен быть принят
        cut2 = {"n": 0}

        def cut_all(sources, dest_dir, timeout=0):
            with open(os.path.join(dest_dir, n1), "wb") as f:
                f.write(data1[:100])
            raise RuntimeError("scp, код 255: Connection reset")
        ok2, er2 = F.ssh_fetch(lst1, os.path.join(tmp, "dest3"), get=cut_all, log=lambda x: None)
        sz = F.ssh_fetch([(lg1, dy1, n1, len(data1) + 1)], os.path.join(tmp, "dest4"), get=fake_get, log=lambda x: None)
        check("сбои сбор (р75 М-1): обрыв пачки — обрывок без .json стёрт и забран заново парой (принят, SHA-256 = .json); обрывается и повтор — "
              "не принят, ошибка названа, обрывка нет; размер копии ≠ размеру из списка — «копия оборвана», не принята",
              ok1 == [(lg1, dy1, n1)] and not er1 and os.path.getsize(os.path.join(dest2, lg1, dy1, n1)) == len(data1)
              and ok2 == [] and er2 and not os.path.exists(os.path.join(tmp, "dest3", lg1, dy1, n1))
              and sz[0] == [] and any("оборвана" in e for e in sz[1]), (ok1, er1, ok2, er2, sz))
        # ---- р75: без ключа LogSeal — отказ ДО scp, ничего не забрано
        class _NoKey:
            def __getattr__(self, k):
                return getattr(LS, k)

            def current_key(self):
                return None
        calls.clear()
        F.scp_get = fake_get
        try:
            nk = _refused(lambda: C.pc_collect(fetch=True, dest=os.path.join(tmp, "dest5"), listing=lst1, tools=(F, _NoKey()), rel_text=(rl, "")))
        finally:
            F.scp_get = saved
        check("сбои (р75, планировщик): ключ LogSeal не открывается (S4U без DPAPI) — crash.sync отказывает до scp, ничего не забрано и не записано",
              nk == C.NO_KEY and not calls and not os.path.exists(os.path.join(tmp, "dest5", lg1)), (nk, calls))
        full = json.dumps(snap, ensure_ascii=False)
        check("сбои сбор: в сводке нет IP, install, exe=, путей (X:\\, \\Users\\) и имени пользователя этого ПК — leaks() пусто",
              not C.leaks(full) and "1.2.3.4" not in full and "cdcdcdcd" not in full, C.leaks(full))
        lk = [C.leaks('{"error":"from 10.0.0.1"}'), C.leaks('{"e":"exe=C:\\\\Program Files\\\\x"}'), C.leaks('{"e":"C:\\\\Users\\\\x\\\\y"}'),
              C.leaks('{"install":"ab"}'), C.leaks('{"e":"minidump.dmp"}')]
        check("сбои: проверка утечек ловит IP, exe= и Program Files, путь \\Users\\, поле install, minidump", all(lk), lk)
        # ---- список хранилища по правилам приёмника (подмена ssh)
        out = ("Player22\t2026-10-26\t20261026-000005_aaaaaaaaaaaaaaaa.acrash\t10\r\nservice\t2026-10-26\tx.acrash\t1\r\n"
               "Bad Login\t2026-10-26\ty.acrash\t1\r\nzx0440\t2026-13\tz.acrash\t1\r\nzx0440\t2026-10-28\t..\\evil.acrash\t1\r\n"
               "Player59\t2026-10-28\tq.alog\t5\r\nzx0440\t2026-10-28\tq.exe\t5\r\n")
        sc = F.ssh_scan(("acrash",), run=lambda s: out)
        sa = F.ssh_scan(("alog", "acrash"), run=lambda s: out)
        check("сбои (р75 К-8): имя папки логина не «.» / «..» и не с точки — список приёмника и удаление отказывают",
              not F.LOGIN_DIR_RE.match("..") and not F.LOGIN_DIR_RE.match(".x") and F.LOGIN_DIR_RE.match("_unknown") and F.LOGIN_DIR_RE.match("Player1")
              and not C._REL_RE.match("..\\2026-01-05\\a.alog") and C._REL_RE.match("Player22\\2026-01-05\\a.alog")
              and not C.LOGIN_RE.match(".."))
        check("сбои: список хранилища по SSH — только папки и имена по правилам приёмника (service, чужой логин, плохая дата, «..», не тот вид — "
              "пропущены); виды отбираются (--kinds)", [x[2] for x in sc] == ["20261026-000005_aaaaaaaaaaaaaaaa.acrash"] and len(sa) == 2, (sc, sa))
        # ---- НАСТОЯЩИЕ PowerShell-скрипты квоты / кандидатов / удаления на своей папке этого ПК
        root = os.path.join(tmp, "LogDrop")
        old_day, new_day = "2026-01-05", datetime.datetime.utcnow().strftime("%Y-%m-%d")
        files = {("Player22", old_day, "a1.alog"): 1000, ("Player22", old_day, "a1.json"): 10, ("Player22", old_day, "c1.acrash"): 3000,
                 ("Player22", old_day, "c1.json"): 11, ("Player22", old_day, "fresh.alog"): 50, ("_unknown", old_day, "a2.alog"): 700,
                 ("_unknown", new_day, "a3.alog"): 600, ("service", "logs", "service_x.log"): 5}
        oldt = datetime.datetime(2026, 1, 5).timestamp()
        for (lg, day, n), size in files.items():
            dd = os.path.join(root, lg, day)
            os.makedirs(dd, exist_ok=True)
            fp = os.path.join(dd, n)
            with open(fp, "wb") as f:
                f.write(b"x" * size)
            if n != "fresh.alog" and day == old_day:
                os.utime(fp, (oldt, oldt))
        saved_root = C.LOGDROP_ROOT
        C.LOGDROP_ROOT = root
        try:
            stj = C.summarize_stats(json.loads(_local_ps(C._stats_script()).strip()))
            cand, tot, cut = C.old_alogs(run=_local_ps)
            refused = _refused(lambda: C.delete_alogs(cand + ["Player22\\%s\\c1.acrash" % old_day], cut, run=_local_ps))
            n, b, skip = C.delete_alogs(cand + ["Player22\\%s\\fresh.alog" % old_day], cut, run=_local_ps)
            # р75 К-7: папка логина — junction в чужое место: удаление через неё пропускается
            other = os.path.join(tmp, "other", old_day)
            os.makedirs(other, exist_ok=True)
            vp = os.path.join(other, "v.alog")
            with open(vp, "wb") as f:
                f.write(b"v" * 9)
            os.utime(vp, (oldt, oldt))
            jr = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(root, "jlogin"), os.path.join(tmp, "other")], capture_output=True)
            jn, _jb, jskip = C.delete_alogs(["jlogin\\%s\\v.alog" % old_day], cut, run=_local_ps) if jr.returncode == 0 else (None, 0, [])
            junction = (jr.returncode, jn, os.path.exists(vp))
            if jr.returncode == 0:
                os.rmdir(os.path.join(root, "jlogin"))
            left = sorted(os.path.relpath(os.path.join(a, f), root) for a, _d, fs in os.walk(root) for f in fs)
        finally:
            C.LOGDROP_ROOT = saved_root
        check("сбои LogDrop (настоящий PowerShell, своя папка): квота считает всё, кроме service\\ (5371 байт), разбивка по видам; кандидаты — только "
              ".alog, где и день папки, и время записи старше 60 суток (свежая запись в старом дне и сегодняшний — нет, .acrash — никогда)",
              stj["used"] == 5371 and stj["by_ext"]["acrash"]["n"] == 1 and stj["by_ext"]["alog"]["n"] == 4
              and cand == ["_unknown\\%s\\a2.alog" % old_day, "Player22\\%s\\a1.alog" % old_day] and tot == 1700
              and stj["old_alog"]["n"] == 2, (stj, cand, tot))
        check("сбои удаление (настоящий PowerShell): .acrash в списке — отказ до сервера, ничего не удалено; .alog удалены вместе с .json, свежий .alog "
              "в списке — пропущен повторной проверкой; .acrash и его .json, сегодняшний .alog и service\\ — на месте",
              refused and "ничего не удалено" in refused and n == 2 and b == 1710 and [x[0] for x in skip] == ["Player22\\%s\\fresh.alog" % old_day]
              and left == sorted(["_unknown\\%s\\a3.alog" % new_day, "Player22\\%s\\c1.acrash" % old_day, "Player22\\%s\\c1.json" % old_day,
                                  "Player22\\%s\\fresh.alog" % old_day, "service\\logs\\service_x.log"]), (refused, n, b, skip, left))
        check("сбои удаление (р75 К-7, настоящий PowerShell): папка логина — точка соединения в чужую папку — файл через неё не удалён (пропущен)",
              junction[0] == 0 and junction[1] == 0 and junction[2], junction)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # ---- НАСТОЯЩИЕ пакеты _player_logs (если ключ LogSeal есть на этом ПК): разбор в памяти = summary.txt на диске (второй способ)
    dest = F.default_dest()
    pk = C.local_packages(dest, F)
    kf = LS._keys_fn(None)
    real, same, times = [], 0, 0
    for lg, day, pth in pk:
        rr = C.read_package(pth, LS, kf, C._meta(pth))
        real.append(rr)
        sp = pth + ".d" + os.sep + "summary.txt"
        if rr["status"] == "ok" and os.path.isfile(sp):
            same += C.parse_summary(open(sp, encoding="utf-8", errors="replace").read())["frames"][:C.FRAMES_KEEP] == rr["frames"]
        tx = pth + ".txt"
        if os.path.isfile(tx):
            m = re.search(r"time_utc=([^;]+);", open(tx, encoding="utf-8", errors="replace").read())
            times += bool(m) and C._parse_utc(m.group(1)) in (rr.get("crash_utc"), rr.get("basis_time"))
    with_sum = sum(1 for _l, _d, pth in pk if os.path.isfile(pth + ".d" + os.sep + "summary.txt"))
    if pk and all(r["status"] != "unread" for r in real):
        check("сбои (настоящие пакеты этого ПК, %d): все прочитаны; кадры разбора в памяти = summary.txt, который положила расшифровка FetchAndDecrypt "
              "(%d из %d); время = сведениям .acrash.txt (%d)" % (len(pk), same, with_sum, times),
              same == with_sum and times == len(pk), (same, with_sum, times))
        by_file = {os.path.basename(pth)[:15]: rr for (_l, _d, pth), rr in zip(pk, real)}
        k1, k2 = by_file.get("20261026-000005"), by_file.get("20261026-010022")
        u1, u2 = by_file.get("20261020-211459"), by_file.get("20261026-013903")
        if k1 and k2 and u1 and u2:
            check("сбои (р75 М-3, настоящие пакеты): два падения GPU Player22 26.10 (бывшее место 2870c85878ec) — теперь разные места; два падения "
                  "с одинаковым стеком 20.10 — одно место", k1["sig"] != k2["sig"] and u1["sig"] == u2["sig"] and "2870c85878ec" not in (k1["sig"], k2["sig"]),
                  (k1["sig"], k2["sig"], u1["sig"], u2["sig"]))
    else:
        check("сбои (настоящие пакеты): на этом ПК нет пакетов или ключа LogSeal — проверка пропущена (%d пакетов)" % len(pk), True)
    # ---- сервер: сбор — отказ
    cfg = config.get()
    was = cfg.on_server
    cfg.on_server = True
    try:
        srvr = [_refused(lambda: so.preview(ops.Ctx(None, "x", "owner", "", "web"), {}))]
        try:
            C._tools()
            srvr.append(False)
        except config.PortCodeError:
            srvr.append(True)
    finally:
        cfg.on_server = was
    check("сбои: на сервере crash.sync — отказ «только ПК владельца», код LogSeal — PortCodeError (ключа и кода расшифровки на сервере нет)",
          srvr[0] and "только ПК" in srvr[0] and srvr[1], srvr)
    # ---- тексты и переводы
    texts = [C.NOT_INSTALLED, so.title, po.title, "по времени начала сессии, на границе: выпуск за 0.3 ч до этого, возможна прежняя alpha-1.0.9-10.2026",
             "раньше первого выпуска в releases.log (alpha-1.0.0-10.2026)", "версия не определена: нет времени", "по времени упаковки (падение раньше)",
             "по времени приёма", "по времени падения", "пакет не расшифрован: нет закрытого ключа на этом ПК",
             "пакет не расшифрован: тег GCM не сошёлся (порча или подмена)", "в пакете нет summary.txt", "в пакете нет CrashContext движка",
             "пакет на сервере, на ПК не забран (ошибка копирования)", 
             "в сводке сбоев найдено то, что наружу не отправляется (IP) — не записана", "сводка сбоев не прочитана: AsdaAdmin: x",
             "квота LogDrop не прочитана: x", "ПК ещё не присылал сводку сбоев (asda_admin.py crashes sync на ПК владельца)",
             "сводка сбоев старше 48 ч (ПК присылал 2026-11-20 10:00:00 UTC) — новые падения могли не попасть в раздел",
             "LogDrop занят на 81.2% (порог предупреждения приёмника 80%) — при 100% приём журналов останавливается (507)",
             ".alog старше 60 суток: 12 (4.5 МБ) — удалить может владелец (кнопка ниже)",
             "на сервере пакетов падений 14, в последней сводке ПК 13 — запустите crashes sync на ПК",
             "пакетов не прочитано или не забрано: 2 (причина — в таблице случаев)", "новое место падения за сутки: 0xC0000005 07751717ed41 (1)",
             "сбои расшифровывает только ПК владельца (ключ LogSeal — там, решение владельца А7 №1) — поставьте задание ПК",
             "сводка сбоев: пакетов на сервере 13, на ПК 13, строк 13, повторов 0, не прочитано 0, не забрано 0, забрано сейчас 4",
             "сводка сбоев записана: новых 13, изменилось 0, без изменений 0 (отправка №1)", "ssh, код 255: Connection timed out",
             "список пакетов на сервере не получен (ssh, код 255: Connection timed out) — сводка не собрана",
             "список пакетов на сервере не получен (список хранилища по SSH не уложился в 120 с) — сводка не собрана",
             "сводка сбоев записана: новых 0, изменилось 0, без изменений 13 (отправка №1, итог тот же)",
             "удалить .alog старше 60 суток (до 2026-09-24 UTC): 0 файлов, 0.0 МБ, учёток 0",
             ".acrash (пакеты падений) не удаляются никогда — только .alog и их .json",
             "отката нет: удалённые журналы не восстанавливаются (расшифрованные копии на ПК владельца остаются)",
             "нужно подтверждение удаления: слово alogprune (в панели — ввести слово, в консоли — ключ --confirm alogprune)",
             "удаление старых журналов — только сейчас: из браузера (слово и второй фактор) или консолью ПК, не заданием",
             "список .alog изменился с предпросмотра (или предпросмотра не было) — повторите предпросмотр, ничего не удалено",
             ".alog старше 60 суток нет — ничего не удалено", "удалено .alog: 2 (0.0 МБ, с их .json), пропущено 1",
             "в списке на удаление не .alog по правилам приёмника (x.acrash) — ничего не удалено",
             "строка сводки сбоев не прошла проверку (x.acrash) — не записана"] + sorted(set(C.CODE_NAMES.values()) | set(C.UE_TYPES.values()))
    check("сбои: тексты отказов, предупреждений и пометок без «; »", all("; " not in t for t in texts), [t for t in texts if "; " in t])
    i18n.set_lang("en")
    try:
        miss = [(t, i18n.tr(t)) for t in texts if CYR.search(i18n.tr(t))]
    finally:
        i18n.set_lang("ru")
    check("сбои EN: отказы, предупреждения, пометки версии, имена кодов — без русских слов (%d строк)" % len(texts), not miss, miss[:6])
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("сбои: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "crashes.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("сбои веб: раздел #/crashes с правом crash.view, маршрут viewCrashes(my), скрипт после releases.js; без innerHTML, данные — acText, "
          "удаление — только с правом crash.prune, словом, вторым фактором и отпечатком предпросмотра",
          '["#/crashes", "Сбои клиента", "crash.view"' in app and 'case "crashes": return viewCrashes(my);' in app
          and 0 < idx.index("/releases.js") < idx.index("/crashes.js") and "innerHTML" not in js
          and 'can["crash.prune"] ? h("div", { class: "row" }, h("button"' in js and 'op("crash.alog_prune", { confirm: word.value.trim(), totp: code.value.trim(), expect: pv.expect }, false)' in js
          and "T(x." not in js.replace("T(x.message)", "") and "T(g." not in js and "T(r.summary" not in js)
    q = re.compile(r'"((?:[^"\\]|\\.)*)"')
    labels = {x for x in q.findall(js) if CYR.search(x)} | {"Сбои клиента"}
    have = set(re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(labels - have)
    check("сбои веб EN: у русских строк раздела есть перевод в web/i18n.js (%d строк)" % len(labels), not lack, lack[:8])
    keys_all = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А7.2 (23.11): «Сбои клиента»"):]
    dup = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys_all.count(x) > 1})
    check("сбои веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("crashes.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("сбои: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("сбои: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- SQL и выкладка
    sql = _read(ROOT, "sql", "adminc_27_crashes.sql")
    bs = _batches(sql)
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    check("сбои adminc_27: QUOTED_IDENTIFIER ON отдельным батчем до CREATE, уровень 100 (нет TRY_CONVERT, IIF, FORMAT, THROW, STRING_SPLIT, ISJSON), "
          "asda_admin — только SELECT трёх таблиц и EXECUTE двух процедур, INSERT / UPDATE / DELETE — DENY",
          bs[0].strip().endswith("SET QUOTED_IDENTIFIER ON;") and "CREATE TABLE" not in bs[0]
          and not re.search(r"\b(TRY_CONVERT|TRY_CAST|IIF|FORMAT|THROW|STRING_SPLIT|ISJSON|OPENJSON|CONCAT|STRING_AGG)\b", body)
          and sorted(re.findall(r"GRANT (\w+) ON (adm\.\w+)\s+TO \[asda_admin\]", body)) == sorted(
              [("SELECT", "adm.ClientCrash"), ("SELECT", "adm.ClientCrashSig"), ("SELECT", "adm.ClientCrashSync"), ("EXECUTE", "adm.ClientCrashPut"),
               ("EXECUTE", "adm.ClientCrashSyncAdd")])
          and len(re.findall(r"DENY  INSERT, UPDATE, DELETE ON adm\.ClientCrash\w* +TO \[asda_admin\]", body)) == 3)
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    check("сбои: выкладка — adminc_27 с -x -I в AsdaAdmin после adminc_26 и до проверок прав (adminc_10)",
          "Run 'adminc_27_crashes.sql' 'AsdaAdmin' -xi" in dep and dep.index("Run 'adminc_26_releases.sql'") < dep.index("Run 'adminc_27_crashes.sql'")
          < dep.index("adminc_10_verify.sql') 2>&1"))
    v10, v99 = _read(ROOT, "sql", "adminc_10_verify.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    check("сбои: adminc_10 — SELECT и EXECUTE = 1, INSERT / UPDATE / DELETE = 0; adminc_99 — откат шага",
          "'adm.ClientCrash SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','SELECT'), 1" in v10
          and "'adm.ClientCrash INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','INSERT'), 0" in v10
          and "'adm.ClientCrash DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','DELETE'), 0" in v10
          and "'adm.ClientCrashPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashPut','OBJECT','EXECUTE'), 1" in v10
          and (v99 is None or "DROP TABLE IF EXISTS adm.ClientCrashSync, adm.ClientCrashSig, adm.ClientCrash" in v99))
    cli = _read(ROOT, "asda_admin.py")
    check("сбои: консоль — crashes show | sync [--dry] [--no-fetch] | prune [--confirm alogprune] (операциями, журнал adm.audit), справка",
          'if cmd == "crashes":' in cli and 'ops.run(_cli_ctx(), "crash.sync", prm, dry="--dry" in args)' in cli
          and 'ops.run(_cli_ctx(), "crash.alog_prune", {"confirm": word, "expect": pv["expect"]})' in cli and "  crashes …" in cli
          and 'prm = {"no_fetch": True} if "--no-fetch" in args or "--dry" in args else {}' in cli)
    # ---- р75: файлы задач планировщика (не создаются — только файлы для владельца)
    import xml.dom.minidom as MD
    st_dir = os.path.join(ROOT, "deploy", "schtasks")
    tk = {}
    for f in ("release_push.xml", "crash_sync.xml"):
        raw = open(os.path.join(st_dir, f), "rb").read()
        d = MD.parseString(raw)
        tk[f] = (raw[:2] == b"\xff\xfe", d.getElementsByTagName("LogonType")[0].firstChild.data,
                 {x.firstChild.data for x in d.getElementsByTagName("UserId")}, d.getElementsByTagName("Arguments")[0].firstChild.data)
    rd = _read(st_dir, "README.md")
    check("сбои (р75, планировщик): release_push.xml — S4U, releases push; crash_sync.xml — InteractiveToken («только при входе»), crashes sync, журнал "
          "в файл; оба UTF-16 с BOM, одна учётка; README — команды создания, проверки и удаления; в выкладку службы папка не входит",
          tk["release_push.xml"][:2] == (True, "S4U") and "releases push" in tk["release_push.xml"][3]
          and tk["crash_sync.xml"][:2] == (True, "InteractiveToken") and "crashes sync" in tk["crash_sync.xml"][3] and "crash_sync.log" in tk["crash_sync.xml"][3]
          and len(tk["release_push.xml"][2] | tk["crash_sync.xml"][2]) == 1 and 'schtasks /Create /TN "Astory\\CrashSync" /XML crash_sync.xml' in rd
          and 'schtasks /Run /TN "Astory\\CrashSync"' in rd and "schtasks" not in _read(ROOT, "deploy", "deploy_admin_center.py").split("PACK_FILES", 1)[1][:200],
          {k: v[:3] for k, v in tk.items()})
    code = _read(ROOT, "domains", "crashes.py")
    fd = _read(LOGSEAL, "fetch_and_decrypt.py")
    ok_top = True
    for src in (code, fd):
        tree = ast.parse(src)
        top = {type(n).__name__ for n in tree.body}
        ok_top &= top <= {"Expr", "Import", "ImportFrom", "Assign", "FunctionDef", "ClassDef", "If"} and all(
            isinstance(n.value, ast.Constant) for n in tree.body if isinstance(n, ast.Expr))
        ok_top &= all(isinstance(n.test, ast.Compare) and "__main__" in ast.dump(n.test) for n in tree.body if isinstance(n, ast.If))
    check("сбои: импорт domains/crashes и fetch_and_decrypt без побочных эффектов (верхний уровень — импорты, константы, функции, классы, __main__); "
          "в коде нет прямой записи в таблицы (только процедуры), в fetch_and_decrypt — нет шары \\\\@@ASTORY_SERVER_HOSTNAME@@",
          ok_top and not re.findall(r"\b(INSERT|UPDATE|DELETE)\s+adm\.", code) and "EXEC adm.ClientCrashPut" in code
          and "@@ASTORY_SERVER_HOSTNAME@@" not in fd.replace("\\\\@@ASTORY_SERVER_HOSTNAME@@\\\\H(@@ASTORY_SERVER_HOSTNAME@@_ns) больше не используется", ""))


class _Req:
    def __init__(self, q, role):
        self.query = q
        self.session = {"user": {"role": role, "login": "t_" + role, "id": 1}}


def _row(sha, file, login, code, frames, crash, status="ok", version="alpha-1.0.0-10.2026"):
    from domains import crashes as C
    sig = C.signature(code, frames)[0] if code else None
    r = {"sha": sha, "file": file, "login": login, "kind": 4, "crash_utc": crash, "session_utc": None, "received_utc": crash, "status": status,
         "status_note": "", "code": code, "addr": frames[0] if frames else None, "access": None, "error": "Fatal error!", "frames": " ".join(frames) or None,
         "exe_frames": len(frames), "sig": sig, "version": version, "version_basis": "crash", "version_note": "по времени падения", "symbols": "none"}
    r["row_md5"] = hashlib.md5(json.dumps(r, sort_keys=True).encode()).hexdigest()
    return r


def sandbox(check, ldb):
    """Своя база LocalDB: adminc_02 + adminc_27, запись сводки, группы, чтение, операции, маршрут."""
    _paths()
    from core import db, i18n, ops
    import domains
    domains.load_all()
    from domains import crashes as C
    name = "AsdaCrash_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s]" % name)
    try:
        a = ldb(name)
        for b in _batches(_read(ROOT, "sql", "adminc_02_schema.sql")):
            a.cursor().execute(b)
        db.set_override("admin", lambda database: ldb(name))
        try:
            s0 = C.summary(uids={})
            snap0 = {"format": C.FORMAT, "host": "PC1", "collected_utc": "2026-11-23 10:00:00", "rows": [], "stats": {}, "errors": []}
            check("сбои стенд: до adminc_27 — «не установлен», push — отказ тем же текстом",
                  s0["installed"] is False and s0["error"] == C.NOT_INSTALLED and _refused(lambda: C.push_pc("t", snap0)) == C.NOT_INSTALLED)
            for _ in range(2):
                for b in _batches(_read(ROOT, "sql", "adminc_27_crashes.sql")):
                    a.cursor().execute(b)
            check("сбои стенд: настоящий adminc_27 дважды (повтор безопасен, без asda_admin — выдача прав пропущена)",
                  a.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name LIKE 'ClientCrash%'").fetchone()[0] == 3)
            now = datetime.datetime.utcnow().replace(microsecond=0)
            ts = lambda h: (now - datetime.timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")
            fa = ["AsdaReborn-Win64-Shipping.exe+0x1", "AsdaReborn-Win64-Shipping.exe+0x2", "AsdaReborn-Win64-Shipping.exe+0x3"]
            fb = ["KERNELBASE.dll+0x5", "AsdaReborn-Win64-Shipping.exe+0x9"]
            rows = [_row("a" * 64, "f1.acrash", "Player22", "0xC0000005", fa, ts(2)), _row("b" * 64, "f2.acrash", "Player59", "0xC0000005", fa, ts(30)),
                    _row("c" * 64, "f3.acrash", None, "0x00008000", fb, ts(24 * 9)), _row("d" * 64, "f4.acrash", None, None, [], None, status="unread")]
            snap = dict(snap0, rows=rows, stats={"on_server": 4, "local": 4, "dups": 0})
            w1 = C.push_pc("cli:bob@PC1", snap)
            w2 = C.push_pc("tester", dict(snap, collected_utc="2026-11-23 11:00:00"))
            sy = a.cursor().execute("SELECT COUNT(*), MAX(seen_count), MAX(pushed_by) FROM adm.ClientCrashSync").fetchone()
            r2 = dict(rows[3], status="ok", code="0x00008000", sig=rows[2]["sig"], frames=rows[2]["frames"], crash_utc=ts(1), row_md5="e" * 32)
            w3 = C.push_pc("tester", dict(snap, rows=[r2], stats={"on_server": 5}))
            n = a.cursor().execute("SELECT COUNT(*) FROM adm.ClientCrash").fetchone()[0]
            w4 = C.push_pc("tester", dict(snap, rows=[dict(rows[0], status="unread", status_note="пакет не расшифрован: нет закрытого ключа на этом ПК",
                                                           code=None, sig=None, row_md5="9" * 32)]))
            st0 = a.cursor().execute("SELECT status, sig FROM adm.ClientCrash WHERE pkg_sha256 = ?", "a" * 64).fetchone()
            check("сбои стенд: прочитанная строка не ухудшается — ПК без ключа прислал «не прочитан», строка осталась «прочитан» с прежней подписью",
                  w4["same"] == 1 and w4["changed"] == 0 and tuple(st0) == ("ok", rows[0]["sig"]), (w4, tuple(st0)))
            check("сбои стенд: первая отправка — 4 новых строки; тот же итог — строки те же (0 новых), отправка та же, seen_count 2, кто прислал — без "
                  "имени пользователя Windows; строка дочитана (unread → ok, другой отпечаток) — переписана, второй строки нет",
                  w1["new"] == 4 and w2["new"] == 0 and w2["same"] == 4 and not w2["sync_new"] and tuple(sy) == (1, 2, "cli@PC1")
                  and w3["changed"] == 1 and w3["sync_new"] and n == 4, (w1, w2, tuple(sy), w3, n))
            sg = {r[0]: (r[1], r[2]) for r in a.cursor().execute("SELECT sig, n, accounts FROM adm.ClientCrashSig").fetchall()}
            check("сбои стенд: группы adm.ClientCrashSig = пересчёту (место A — 2 падения, 2 учётки; место B — 2 падения, 0 учёток), строка без подписи "
                  "в группы не входит", sg == {rows[0]["sig"]: (2, 2), rows[2]["sig"]: (2, 0)}, sg)
            s = C.summary(uids={"Player22": 77})
            g = {x["sig"]: x for x in s["groups"]}
            ga, gb = g[rows[0]["sig"]], g[rows[2]["sig"]]
            check("сбои стенд: summary() — место A: за сутки 1, за 7 суток 2, учётки со ссылкой на карточку (Player22 → №77, Player59 — без номера); "
                  "место B: за сутки 1, за 7 суток 1, всего 2, без логина 2; дни — 14 суток; отправка свежая",
                  (ga["n"], ga["n_24h"], ga["n_7d"]) == (2, 1, 2) and ga["accounts"] == [{"login": "Player22", "uid": 77}, {"login": "Player59", "uid": None}]
                  and (gb["n"], gb["n_24h"], gb["n_7d"], gb["unknown"]) == (2, 1, 1, 2) and len(s["days"]) == 14 and sum(d["n"] for d in s["days"]) == 4
                  and s["sync"] and not s["sync"]["stale"] and s["sync"]["stats"]["on_server"] == 4, (ga, gb, s["days"]))
            st = {"quota": 100, "warn_pct": 80, "pct": 85.0, "warn": True, "by_ext": {"acrash": {"n": 6}}, "old_alog": {"n": 3, "bytes": 2048}, "error": ""}
            w = C.warnings(s, st)
            a.cursor().execute("UPDATE adm.ClientCrashSync SET seen_utc = DATEADD(hour, -50, SYSUTCDATETIME())")
            w50 = C.warnings(C.summary(uids={}), {"error": ""})
            check("сбои стенд: предупреждения — квота выше порога, .alog старше срока, на сервере пакетов больше, чем в сводке; ПК не присылал 50 ч — "
                  "«сводка старше 48 ч»", any("LogDrop занят на 85.0%" in x for x in w) and any(".alog старше 60 суток: 3" in x for x in w)
                  and any("на сервере пакетов падений 6" in x for x in w) and any("старше 48 ч" in x for x in w50), (w, w50))
            nf = _row(hashlib.sha256(b"notfetched:Player59/x/f7.acrash").hexdigest(), "f7.acrash", None, None, [], None, status="notfetched")
            C.push_pc("tester", dict(snap, rows=[nf], stats={"on_server": 9}))
            had = a.cursor().execute("SELECT COUNT(*) FROM adm.ClientCrash WHERE file_name = 'f7.acrash'").fetchone()[0]
            C.push_pc("tester", dict(snap, rows=[_row("7" * 64, "f7.acrash", "Player59", "0xC0000005", fa, ts(5))], stats={"on_server": 10}))
            now7 = a.cursor().execute("SELECT status FROM adm.ClientCrash WHERE file_name = 'f7.acrash'").fetchall()
            check("сбои стенд (р75 М-2): строка «не забран» уходит, когда тот же файл пришёл настоящей строкой (процедура, без прямого DELETE у asda_admin)",
                  had == 1 and [x[0] for x in now7] == ["ok"], (had, now7))
            # операции
            saved = C.pc_collect
            C.pc_collect = lambda fetch=True, **k: dict(snap, rows=[_row("f" * 64, "f9.acrash", "Player54", "0xC00000FD", fa, ts(3))],
                                                        stats={"on_server": 5, "local": 5, "rows": 1, "dups": 0, "unread": 0, "notfetched": 0, "fetched_now": 0})
            try:
                r = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "crash.sync", {})
                gm = _refused(lambda: ops.run(ops.Ctx(5, "g", "gm", "", "web"), "crash.sync", {}))
                adm = _refused(lambda: ops.run(ops.Ctx(6, "a", "admin", "", "web"), "crash.sync", {}))
            finally:
                C.pc_collect = saved
            au = a.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action = 'crash.sync' AND result = 'ok'").fetchone()[0]
            check("сбои стенд: crash.sync через ops.run — сводка записана (1 новая), запись «ok» в adm.audit; admin и gm — «нет права»",
                  r["message"].startswith("сводка сбоев записана: новых 1") and au == 1 and gm and "нет права" in gm and adm and "нет права" in adm,
                  (r["message"], au, gm, adm))
            deleted = []
            so, sd = C.old_alogs, C.delete_alogs
            C.old_alogs = lambda now=None, run=None: (["Player22\\2026-01-05\\a.alog"], 1000, datetime.datetime(2026, 9, 24))
            C.delete_alogs = lambda items, cut, run=None: (deleted.append(list(items)) or (len(items), 1000, []))
            try:
                ow = ops.Ctx(1, "owner1", "owner", "", "web")
                pv = ops.run(ow, "crash.alog_prune", {}, dry=True)["preview"]
                e1 = _refused(lambda: ops.run(ow, "crash.alog_prune", {"expect": pv["expect"]}))
                e2 = _refused(lambda: ops.run(ops.Ctx(None, "cli:t", "owner", "", "cli"), "crash.alog_prune", {"confirm": "alogprune", "expect": {"md5": "x"}}))
                e3 = _refused(lambda: ops.run(ow, "crash.alog_prune", {"confirm": "alogprune", "expect": pv["expect"], "totp": "000000"}))
                e6 = _refused(lambda: ops.run(ow, "crash.alog_prune", {"confirm": "alogprune", "expect": {"md5": "x"}, "totp": "000000"}))
                e4 = _refused(lambda: ops.run(ops.Ctx(None, "service:x", "owner", "", "job"), "crash.alog_prune", {"confirm": "alogprune", "expect": pv["expect"]}))
                e5 = _refused(lambda: ops.run(ops.Ctx(6, "a", "admin", "", "web"), "crash.alog_prune", {}))
                ok = ops.run(ops.Ctx(None, "cli:t", "owner", "", "cli"), "crash.alog_prune", {"confirm": "alogprune", "expect": pv["expect"]})
                C.old_alogs = lambda now=None, run=None: (["Player22\\2026-01-05\\a.alog", "Player59\\2026-01-05\\b.alog"], 2000,
                                                          datetime.datetime(2026, 9, 24))

                def fake_del(items, cut, run=None):
                    C.delete_alogs.last_done = list(items)
                    deleted.append(list(items))
                    return len(items), 1000 * len(items), []
                C.delete_alogs = fake_del
                pm = C.PRUNE_MAX
                C.PRUNE_MAX = 1
                try:
                    pv2 = ops.run(ow, "crash.alog_prune", {}, dry=True)["preview"]
                    ok2 = ops.run(ops.Ctx(None, "cli:t", "owner", "", "cli"), "crash.alog_prune", {"confirm": "alogprune", "expect": pv2["expect"]})
                finally:
                    C.PRUNE_MAX = pm
            finally:
                C.old_alogs, C.delete_alogs = so, sd
            au2 = a.cursor().execute("SELECT result, COUNT(*) FROM adm.audit WHERE action = 'crash.alog_prune' GROUP BY result").fetchall()
            aft = json.loads(a.cursor().execute("SELECT TOP 1 after_json FROM adm.audit WHERE action = 'crash.alog_prune' AND result = 'ok' "
                                                "ORDER BY id DESC").fetchone()[0] or "{}") if a.cursor().execute(
                "SELECT COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('adm.audit') AND name = 'after_json'").fetchone()[0] else ok2["result"]
            check("сбои стенд (р75 К-6, К-4, К-5): чужой отпечаток — отказ «список изменился» раньше проверки кода второго фактора; больше PRUNE_MAX — "
                  "удалено столько, «осталось N — повторите»; в журнале — удалённые пути и учётки",
                  e6 and "изменился" in e6 and "осталось 1 — повторите" in ok2["message"] and ok2["result"]["paths"] == ["Player22\\2026-01-05\\a.alog"]
                  and ok2["result"]["by_login"] == {"Player22": 1} and ok2["result"]["rest"] == 1, (e6, ok2["message"], ok2["result"], aft))
            check("сбои стенд: crash.alog_prune — без слова, с чужим отпечатком списка, из браузера без верного второго фактора, заданием, у admin — отказ, "
                  "ничего не удалено; консолью со словом и отпечатком — удалено по списку предпросмотра, в журнале «ok» и отказы",
                  e1 and "слово alogprune" in e1 and e2 and "изменился" in e2 and e3 and e4 and "только сейчас" in e4 and e5 and "нет права" in e5
                  and ok["message"].startswith("удалено .alog: 1") and deleted[0] == ["Player22\\2026-01-05\\a.alog"]
                  and dict((x[0], x[1]) for x in au2).get("ok") == 2 and dict((x[0], x[1]) for x in au2).get("refused", 0) >= 4,
                  (e1, e2, e3, e4, e5, ok["message"], deleted, au2))
            fn, _perm = _route("/api/crashes")
            sr = C.logdrop_stats
            C.logdrop_stats = lambda force=False, run=None: {"quota": 100, "warn_pct": 80, "pct": 85.0, "warn": True, "by_ext": {}, "old_alog": {"n": 0},
                                                             "error": "", "keep_days": 60}
            try:
                i18n.set_lang("en")
                try:
                    out = fn(_Req({}, "admin"), None)
                finally:
                    i18n.set_lang("ru")
            finally:
                C.logdrop_stats = sr
            check("сбои API (EN): /api/crashes для admin — группы и случаи, предупреждения и пометки версии по-английски, can: crash.prune и crash.sync нет",
                  out["summary"]["groups"] and not [x for x in out["warnings"] if CYR.search(x)]
                  and not [r["version_note"] for r in out["summary"]["rows"] if CYR.search(r["version_note"] or "")]
                  and out["can"]["crash.prune"] is False and out["can"]["crash.sync"] is False, out["warnings"])
        finally:
            db.set_override("admin", None)
    finally:
        m2 = ldb("master")
        try:
            m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m2.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def live(check):
    """Живая dev: список хранилища по SSH = квоте службы, права asda_admin, crash.sync с ПК и чтение, служба на сервере, 401."""
    _paths()
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import crashes as C
    import fetch_and_decrypt as F
    lst = F.ssh_scan(("alog", "acrash"))
    st = C.logdrop_stats(force=True)
    na = sum(1 for x in lst if x[2].endswith(".acrash"))
    nl = sum(1 for x in lst if x[2].endswith(".alog"))
    check("живое: список хранилища по SSH (fetch_and_decrypt.ssh_scan) = квоте службы по видам (второй способ: свой скрипт сводки) — .acrash %d, .alog %d; "
          "занято %.2f ГиБ из %.2f" % (na, nl, (st.get("used") or 0) / 1073741824.0, (st.get("quota") or 0) / 1073741824.0),
          not st.get("error") and st["by_ext"]["acrash"]["n"] == na and st["by_ext"]["alog"]["n"] == nl
          and st["by_ext"]["alog"]["bytes"] == sum(x[3] for x in lst if x[2].endswith(".alog")) and st["ini"], (st.get("error"), st.get("by_ext"), na, nl))
    cn = db.admin()
    try:
        pr = db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME('adm.ClientCrash','OBJECT','SELECT') AS s, HAS_PERMS_BY_NAME('adm.ClientCrash','OBJECT','INSERT') AS i, "
                               "HAS_PERMS_BY_NAME('adm.ClientCrash','OBJECT','UPDATE') AS u, HAS_PERMS_BY_NAME('adm.ClientCrash','OBJECT','DELETE') AS d, "
                               "HAS_PERMS_BY_NAME('adm.ClientCrashPut','OBJECT','EXECUTE') AS p, HAS_PERMS_BY_NAME('adm.ClientCrashSyncAdd','OBJECT','EXECUTE') AS a")[0]
    finally:
        cn.close()
    check("живое: права asda_admin — SELECT adm.ClientCrash, EXECUTE двух процедур есть; INSERT, UPDATE, DELETE напрямую нет",
          (pr["s"], pr["i"], pr["u"], pr["d"], pr["p"], pr["a"]) == (1, 0, 0, 0, 1, 1), pr)
    r = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "crash.sync", {})
    s = C.summary()
    snap = C.pc_collect(fetch=False)
    shas = {x["sha"][:16] for x in snap["rows"]}
    got = {x["sha"] for x in s["rows"]}
    check("живое: crash.sync с ПК (%s) — пишет только AsdaAdmin; чтение обратно: строки сводки = пакетам этого ПК (sha), отправка свежая, на сервере %s "
          "пакетов = в сводке" % (r["message"], (s.get("sync") or {}).get("stats", {}).get("on_server")),
          shas <= got and s.get("sync") and not s["sync"]["stale"] and s["sync"]["stats"]["on_server"] == na, (r["message"], len(shas), len(got)))
    probe = ("import sys, json\nsys.path.insert(0, '.')\nfrom domains import crashes as C\nfrom core import config\n"
             "v = C.view(force=True)\ns = v['summary']\n"
             "try:\n    C._tools()\n    pc = 'нет отказа'\nexcept config.PortCodeError:\n    pc = 'PortCodeError'\n"
             "items, tot, cut = C.old_alogs()\n"
             "print('CRPROBE ' + json.dumps({'rows': len(s['rows']), 'groups': len(s['groups']), 'used': v['logdrop'].get('used'), "
             "'acrash': (v['logdrop'].get('by_ext') or {}).get('acrash', {}).get('n'), 'pc': pc, 'old': len(items), 'err': s.get('error') or v['logdrop'].get('error')}, ensure_ascii=True))\n")
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
    mm = re.search(r"CRPROBE (\{.*\})", out)
    g = json.loads(mm.group(1)) if mm else {}
    check("служба на сервере (SSH): та же сводка (строк и групп = чтению с ПК), квота LogDrop своими силами (.acrash = списку по SSH), код LogSeal — "
          "PortCodeError, кандидаты на удаление — только предпросмотр (ничего не удаляется)",
          g.get("rows") == len(s["rows"]) and g.get("groups") == len(s["groups"]) and g.get("acrash") == na and g.get("pc") == "PortCodeError"
          and isinstance(g.get("old"), int) and not g.get("err"), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/crashes" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/crashes без входа — 401", code == 401, code)
