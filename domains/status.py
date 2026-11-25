# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""status.py — раздел «Состояние»: процессы игровой стойки, порты, машина сервера, игроки по БД. 16.11.2026.

ОЖИДАЕМЫЙ СОСТАВ СТОЙКИ (снят с живого @@ASTORY_SERVER_HOSTNAME@@ 16.11.2026: Get-CimInstance Win32_Process + Get-NetTCPConnection):
  STACK — имя для панели, путь exe (от корня стойки или абсолютный), порты, которые процесс должен слушать.
  Процесс считается «работает», если найден по пути; «порты в порядке» — если слушает все свои порты.
Снимок берётся одним PowerShell-скриптом (локально на сервере или по SSH с ПК) и кэшируется на CACHE_S секунд,
чтобы десяток открытых вкладок не долбил сервер. Только чтение.
Игроки «в игре» — по БД (CharPos.Usernum ≠ −1; 0 — действующий номер слота, правило asda_exp.py): после аварийной остановки сервера признак залипает (памятка
asda_give: «флаги не снимаются»), поэтому рядом показывается время старта GameServer — строки старше старта подозрительны.
Побочных эффектов при импорте нет.
"""
import json
import threading
import time

from core import config, db, hostshell

CACHE_S = 15   # срок кэша снимка, с

# (ключ, подпись, путь exe, [порты]) — путь без буквы диска = от корня стойки config.STACK_ROOT
STACK = [
    ("login",        "LoginManager (вход)",            r"LoginManager\LoginManager.exe",            [15001]),
    ("dbm",          "DBManager",                      r"DBManager\DBManager.exe",                  [15101]),
    ("overlap",      "OverlapCheckServer",             r"OverlapCheckServer\OverlapCheckServer.exe", [15201]),
    ("channel",      "ChannelManager",                 r"ChannelManager\ChannelManager.exe",        [15301]),
    ("itemrelay",    "ItemRelayServer (аукцион)",      r"ItemRelayServer\ItemRelayServer.exe",      [15401]),
    ("operation",    "OperationServer",                r"OperationServer\OperationServer.exe",      [15501]),
    ("gs",           "GameServer (мир, канал 1)",      r"GameServer\GameServer.exe",                [15601]),
    ("gs_ch2",       "GameServer (канал 2)",           r"Ch2_GameServer\GameServer.exe",            [15621]),
    ("gs_indun",     "GameServer (подземелья)",        r"Indun_GameServer\GameServer.exe",          [15651]),
    ("npc",          "NpcServer (мир)",                r"NpcServer\NpcServer.exe",                  [15701]),
    ("npc_ch2",      "NpcServer (канал 2)",            r"Ch2_NpcServer\NpcServer.exe",              [15721]),
    ("npc_indun",    "NpcServer (подземелья)",         r"Indun_NpcServer\NpcServer.exe",            [15751]),
    ("relay",        "RelayServer (мир)",              r"RelayServer\RelayServer.exe",              [15801]),
    ("relay_ch2",    "RelayServer (канал 2)",          r"Ch2_RelayServer\RelayServer.exe",          [15821]),
    ("relay_indun",  "RelayServer (подземелья)",       r"Indun_RelayServer\RelayServer.exe",        [15851]),
    ("eac",          "AsdaEacServer (античит, AsdaId)", r"EacServer\AsdaEacServer.exe",              [15901, 15702, 8444]),
    ("logdrop",      "AsdaLogDrop (журналы клиента)",  r"LogDrop\service\AsdaLogDrop.exe",          [8446]),
    ("caddy",        "Caddy (HTTPS 443)",              r"EacServer\caddy\caddy.exe",                [443]),
    ("gp7",          "Шлюз gp7 (node)",                "node:server.js",                            [15022]),
    ("sql",          "SQL Server",                     r"H:\Program Files\Microsoft SQL Server\MSSQL15.SQLEXPRESS\MSSQL\Binn\sqlservr.exe", [1433]),
]

_PS = r"""
$p = Get-CimInstance Win32_Process -Filter "ExecutablePath like 'H:%' or Name='node.exe' or Name='caddy.exe' or Name='GameServer.exe' or Name='LoginManager.exe'" |
  % { [pscustomobject]@{ pid=$_.ProcessId; name=$_.Name; path=$_.ExecutablePath; cmd=$_.CommandLine;
      start=$_.CreationDate.ToString('yyyy-MM-dd HH:mm:ss'); ws=[int64]$_.WorkingSetSize } }
# слушающие порты — netstat (Get-NetTCPConnection на @@ASTORY_SERVER_HOSTNAME@@ — 1,3 с из 3 с снимка; замер 16.11)
$l = netstat -ano | % { if ($_ -match '^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)') {
      [pscustomobject]@{ port=[int]$matches[2]; addr=$matches[1]; pid=[int]$matches[3] } } }
$os = Get-CimInstance Win32_OperatingSystem
$d = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | % { [pscustomobject]@{ dev=$_.DeviceID; free=[int64]$_.FreeSpace; size=[int64]$_.Size } }
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
[pscustomobject]@{ procs=@($p); listen=@($l); boot=$os.LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss');
  now=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); memfree=[int64]$os.FreePhysicalMemory*1024;
  memtotal=[int64]$os.TotalVisibleMemorySize*1024; disks=@($d); cpu=$cpu; host=$env:COMPUTERNAME } | ConvertTo-Json -Depth 4 -Compress
"""

_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}


def _full(path):
    """Абсолютный путь exe (нижний регистр) для сравнения."""
    if path.startswith("node:") or (len(path) > 1 and path[1] == ":"):
        return path.lower()
    return (config.STACK_ROOT + "\\" + path).lower()


def _match(entry_path, procs):
    """Процессы стойки, подходящие под запись STACK."""
    want = _full(entry_path)
    if want.startswith("node:"):
        script = want.split(":", 1)[1]
        return [p for p in procs if (p.get("name") or "").lower() == "node.exe" and script in (p.get("cmd") or "").lower()]
    return [p for p in procs if (p.get("path") or "").lower() == want]


def _players():
    """Игроки «в игре» по БД и последние входы."""
    out = {"online_db": None, "online_list": [], "logins_24h": None, "error": ""}
    try:
        with db.GameReader("joy1") as j:
            rows = j.rows("SELECT TOP 200 p.Userindex, p.Charidx, p.Charname, p.Poridx, p.Posx, p.Posy, p.Channel, "
                          "p.LastDate, i.Lvl, i.Job FROM CharPos p LEFT JOIN Charinfo i ON i.Userindex = p.Userindex "
                          "AND i.Charidx = p.Charidx WHERE p.Usernum <> -1 ORDER BY p.LastDate DESC")
            out["online_db"] = j.one("SELECT COUNT(*) AS n FROM CharPos WHERE Usernum <> -1")["n"]   # список — до 200
            out["online_list"] = rows
        with db.GameReader("joylog1") as lg:
            r = lg.one("SELECT COUNT(*) AS n, COUNT(DISTINCT Userindex) AS u FROM LogInfo "
                       "WHERE Login >= DATEADD(hour, -24, GETDATE())")
            out["logins_24h"] = r
    except db.DbError as ex:
        out["error"] = str(ex)
    return out


_busy = threading.Lock()   # один сбор снимка за раз


def snapshot(force=False, max_age=None):
    """Снимок состояния стойки. Свежий (моложе CACHE_S) — из кэша; устаревший отдаётся СРАЗУ, а новый собирается
    в фоне (владелец 16.11: «долго обновляется информация о сервере»); force — собрать сейчас и дождаться."""
    with _lock:
        data, age = _cache["data"], time.time() - _cache["at"]
    if data and max_age is not None and age < max_age:
        return data                                   # «свежий» по просьбе вызывающего (онлайн-правила: ≤ 10 с, один сбор на операцию)
    if data and not force:
        if age >= CACHE_S and _busy.acquire(blocking=False):
            def bg():
                try:
                    _collect()
                finally:
                    _busy.release()
            threading.Thread(target=bg, daemon=True, name="status-refresh").start()
        return data
    asked = time.time()
    with _busy:
        with _lock:
            if _cache["data"] and (_cache["at"] >= asked or (not force and time.time() - _cache["at"] < CACHE_S)):
                return _cache["data"]           # перепроверка 5 М11: фоновый сбор закончился, пока ждали — он и есть свежий
        return _collect()


def _collect():
    """Собрать снимок (PowerShell + БД) и положить в кэш."""
    res = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "host_error": "", "machine": None, "stack": []}
    try:
        raw = json.loads(hostshell.powershell(_PS, timeout=45))
    except (hostshell.HostError, ValueError) as ex:
        raw = None
        res["host_error"] = "снимок процессов не получен: %s" % ex
    if raw:
        procs = raw.get("procs") or []
        procs = procs if isinstance(procs, list) else [procs]
        listen = raw.get("listen") or []
        by_pid = {}
        for l in listen:
            by_pid.setdefault(int(l["pid"]), []).append(int(l["port"]))
        for key, title, path, ports in STACK:
            found = _match(path, procs)
            have = sorted({pt for p in found for pt in by_pid.get(int(p["pid"]), [])})
            res["stack"].append({
                "key": key, "title": title, "path": path, "running": bool(found),
                "pids": [p["pid"] for p in found], "start": min((p["start"] for p in found), default=""),
                "mem": sum(int(p.get("ws") or 0) for p in found), "ports": ports, "listening": have,
                "ports_ok": bool(found) and all(pt in have for pt in ports)})
        res["machine"] = {k: raw.get(k) for k in ("host", "boot", "now", "memfree", "memtotal", "disks", "cpu")}
        # процессы ПО ИМЕНИ, из любой папки (перепроверка 9 В1: «не найден по пути» ≠ «не запущен»; онлайн-правила
        # domains/online.py смотрят сюда, а не в STACK)
        res["named"] = {n: sorted(p.get("start") or "" for p in procs if (p.get("name") or "").lower() == n + ".exe")
                        for n in ("gameserver", "loginmanager", "sqlservr")}
    gs = next((s for s in res["stack"] if s["key"] == "gs"), None)
    res["players"] = _players()
    res["players"]["gs_start"] = gs["start"] if gs else ""
    from domains import reports                       # ★ А6.11 ревизия 67 С-2: размер базы панели AsdaAdmin и доля скриншотов жалоб
    res["admin_db"] = reports.db_usage()
    res["summary"] = {"total": len(res["stack"]), "running": sum(1 for s in res["stack"] if s["running"]),
                      "ports_ok": sum(1 for s in res["stack"] if s["ports_ok"])}
    with _lock:
        _cache.update(at=time.time(), data=res)
    return res
