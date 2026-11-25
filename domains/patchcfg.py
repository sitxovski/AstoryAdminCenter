# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""patchcfg.py — «Живое управление → Настройки серверных патчей и конфиги стойки» (шаг А5.5, 21.11.2026; разбор
Reports/admin_center/impl_a5_live_20261121.md §«А5.5»). ТОЛЬКО ЧТЕНИЕ стойки; правка — набором изменений (cs_kinds/patchcfg.py,
виды patch.set / config.set) и рестартом стойки.

state() — по каждой DLL (AsdaPatch ×3 GS, AddonNPC ×3 NpcServer, LoginPatch, DBPatch, SrvDbPatch ×5): копии (md5 ini, Version, MasterEnable,
последний запуск по журналу патчей Log\\Log_Patch\\PatchLog_<дата>.txt — шапка, PID, итог, «Version не поддерживается»), секции шаблона
(описание из реестра INDEX.md, документы, зависимости) с ключами: умолчание, тип и предел по исходнику, значение в КАЖДОЙ копии (секреты —
скрыты), расхождение копий, можно ли править панелью; режим патча по копии — «действует» / «журнал» (Mode=0) / «выключен» ([ВЫКЛ]) /
«не встал» ([MISMATCH] / [ОШИБКА]) / «нет в журнале»; «в ini не то, что работает» (Enabled в ini ≠ итогу последнего запуска — ждёт рестарта).
configs() — стоковые конфиги стойки (разбор реверсом А5.5 §1.3): что читается, кем и когда, можно ли править (белый список
cs_kinds/patchcfg.CONFIGS), содержимое не секретных; файлы с паролями и DSN — только «есть / размер / время», содержимое не показывается.
«Не прочитано» ≠ «нет»: сбой чтения копии — пометка у копии, а не пустые значения. Побочных эффектов при импорте нет.
"""
import base64
import re
import time

from core import config, hostshell
from core.ops import OpRefused
from domains import shopdata as E
from domains.cs_kinds import patchcfg as K

LOG_DIR = "Log\\Log_Patch"
LOG_TAIL = 1024 * 1024                    # хвост журнала патчей (суточный журнал GameServer ~0,2 МБ; установка — первые ~600 строк запуска)
_MARK = re.compile(r"\[(OK|ВЫКЛ|MISMATCH|ОШИБКА)\]\s+(\S+)")
_HEAD = re.compile(r"(\S+) — старт (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d), PID (\d+)")
_TOTAL = re.compile(r"=== итог: применено (\d+), пропущено (\d+), ошибок (\d+)")
_cache = {}

# Стоковые конфиги стойки — разбор А5.5 §1.3 (декомпилы RE/ida/*: строка «кем читается» — функция и строка декомпила).
#   edit — есть в белом списке cs_kinds/patchcfg.CONFIGS; secret — содержимое не показывается (пароли, DSN); why — почему только просмотр.
STACK_CONFIGS = [
    ("GS", "ConfigSet\\ThreadInfo.ini", "потоки карт MAX_INIT_THREAD / THREADID / SYSTEMID (LoadThreadInfo GameServer.c:67974; меньше открытых "
     "карт — exit(1) при старте, GameServer.c:64913)", "потоки — неверное значение не даст подняться стойке", False),
    ("GS", "ConfigSet\\ChannelInfo.ini", "CHANNEL_INFO Count и CHANNEL_NN Age (возраст канала, GameServer.c:64857-64889; Count ≤ 0 — exit(1)); "
     "у Ch2 — свой файл (stack_layout.CHANNEL_FILES)", "проверка возраста канала в бою не разобрана — только просмотр", False),
    ("GS", "ConfigSet\\Udp.ini", "UDP_INFO IP / Port (sub_417240 GameServer.c:9885)", "адрес и порт", False),
    ("GS", "ConfigSet\\VillageServerConfig.Ini", "SERVER_INFO_N IP / PORT / STARTPOS (LoadVillageServerInfo GameServer.c:68065)", "адреса и порты", False),
    ("GS", "ConfigSet\\ConnectIPPORT.ini", "адреса серверов стойки (GameServer.c:73269, 136631)", "адреса и порты", False),
    ("GS", "ConfigSet\\ServerIPPORT.txt", "свой порт (GameServer.c:136549)", "порт", False),
    ("NPC", "ini\\Collection.ini", "COLLECTION_INFO CollectionTypeCount и CollectionTypeAniTimeNN (NpcServer sub_44E7D0 NpcServer.exe.c:53149-53196, "
     "только при старте)", None, False),
    ("NPC", "ini\\AIInfo.ini", "AI_INFO: группа, потоки, номер канала (у Ch2 — свой файл)", "потоки и номер канала", False),
    ("NPC", "ini\\Server_Info.ini", "SERVERINFO потоки и порты", "потоки и порты", False),
    ("NPC", "ini\\UDP.ini", "UDP адрес и порт", "адрес и порт", False),
    ("NPC", "ini\\AcceptIp.ini", "разрешённые адреса (NpcServer.exe.c, ./ini/AcceptIp.ini)", "адреса", False),
    ("NPC", "ini\\MapInfo.ini", "список карт NpcServer (данные, правятся областью «Монстры и добыча» / реестром карт)", "данные карт", False),
    ("LM", "Version.ini", "VERSION / TESTVERSION VER_* и FTPSITE (LoginManager sub_403A10 LoginManager.c:1146 — при старте и кнопкой окна, "
     "sub_406080)", "куда уходят значения клиенту — не разобрано, FTPSITE — адрес", False),
    ("LM", "ConfigSet\\AcceptIP.ini", "AcceptIpFlag и список адресов (sub_405450 при старте; 4101/28 — стоковый режим профилактики)",
     "адреса (режим обслуживания — раздел «Режим обслуживания», L09)", False),
    ("LM", "LoginMng.ini", "SERVERGROUP и DB_DNS*: GAMEDNS / GAMEUSER / GAMEPASS", "подключение к базе и пароли", True),
    ("LM", "GameServerIP\\GameServerIP.ini", "адреса GameServer для клиента (LoginManager.c:1787)", "адреса", False),
    ("DBM", "DBMng.ini", "SERVERGROUP и DB_DNS*: DSN, пользователь, пароль", "подключение к базе и пароли", True),
    ("DBM", "ConfigSet\\Mgame.ini", "Mgame.ini DBManager (DBManager.exe.c)", "подключение (значения не показываются)", True),
    ("DBM", "ConfigSet\\ServerInfo.ini", "SERVERINFO ServerGroup", "группа серверов — меняется только вместе с DBMng.ini", False),
    ("SDB", "ini\\DBInfo.ini", "подключение к базе RelayServer / ItemRelayServer / OperationServer", "подключение к базе и пароли", True),
    ("ONE:ChannelManager", "ini\\Server_Info.ini", "SERVERINFO потоки, порты, ChannelCount, MaxMapCount; CONNECT_INFO адреса",
     "состав каналов и адреса — меняется только вместе с копиями стойки (deploy_channel2)", False),
    ("ONE:ChannelManager", "ini\\PartyMatching.ini", "размеры пулов подбора отряда", "размеры памяти — не разобраны", False),
    ("ONE:ChannelManager", "ini\\EventMap.ini", "EVENT_INFO адрес, порт и точка карты событий", "адрес и порт", False),
    ("ONE:ItemRelayServer", "ini\\Section.ini", "SECTION / ITEM_INFO / TIME_INFO ItemDeleteTime (ItemRelayServer.c:1103, CheckRegistTimeOver :607)",
     "что удаляет CheckRegistTimeOver — не разобрано", False),
    ("ONE:OperationServer", "ini\\LogInfo.ini", "LOG_INFO банки журнала", "размеры памяти журнала", False),
    ("ONE:EacServer", "EacServer.ini", "сайдкар EAC (наш)", "ключи и подключения — значения не показываются", True),
    ("ONE:.", "PasswordSQL.txt", "пароль SQL стойки", "секрет", True),
]


def _folders(fam):
    if fam.startswith("ONE:"):
        return [fam[4:]]
    return E.folders(fam)


def _rel(folder, sub):
    return sub if folder == "." else folder + "\\" + sub


# =====================================================================================================================
# Чтение стойки одним вызовом
# =====================================================================================================================
CHUNK = 14                                # путей на одну команду: длина командной строки SSH → cmd.exe ограничена (~8 тыс. знаков)


def _read(ini_rels, log_dirs, stat_rels):
    """Чтение кусками по CHUNK путей (см. _read1) → то же, что _read1."""
    items = [("I", r) for r in ini_rels] + [("L", d) for d in log_dirs] + [("S", r) for r in stat_rels]
    ini, logs, st = {}, {}, {}
    for k in range(0, max(1, len(items)), CHUNK):
        part = items[k:k + CHUNK]
        a, b, c = _read1([r for t, r in part if t == "I"], [r for t, r in part if t == "L"], [r for t, r in part if t == "S"])
        ini.update(a)
        logs.update(b)
        st.update(c)
    return ini, logs, st


def _read1(ini_rels, log_dirs, stat_rels):
    """→ ({ini rel: байты | None}, {папка: текст хвоста журнала | None | 'NOLOG'}, {rel: (размер, время) | None}). Одна команда PowerShell
    (служба — локально, ПК — SSH); файлы открываются с FileShare.ReadWrite (журнал держит процесс)."""
    root = config.STACK_ROOT.replace("'", "''")
    q = lambda xs: ",".join("'%s'" % x.replace("'", "''") for x in xs)
    ps = ("$v2='%s'; function RB($p, $tail) { $fs = [IO.File]::Open($p, 'Open', 'Read', 'ReadWrite'); try { $len = $fs.Length; "
          "$n = if ($tail -gt 0) { [Math]::Min($len, $tail) } else { $len }; [void]$fs.Seek($len - $n, 'Begin'); $b = New-Object byte[] $n; "
          "$g = 0; while ($g -lt $n) { $r = $fs.Read($b, $g, $n - $g); if ($r -le 0) { break }; $g += $r }; "
          "[Convert]::ToBase64String($b, 0, $g) } finally { $fs.Close() } }; "
          "foreach ($r in @(%s)) { $p = Join-Path $v2 $r; try { if (Test-Path -LiteralPath $p) { Write-Output ('I|' + $r + '|' + (RB $p 0)) } "
          "else { Write-Output ('I|' + $r + '|NONE') } } catch { Write-Output ('I|' + $r + '|ERR') } }; "
          "foreach ($d in @(%s)) { $dir = Join-Path $v2 ($d + '\\%s'); try { $f = Get-ChildItem -LiteralPath $dir -Filter 'PatchLog_*.txt' "
          "-ErrorAction Stop | Where-Object { $_.Name -match '^PatchLog_\\d{8}\\.txt$' } | Sort-Object Name -Descending | Select-Object -First 1; "
          "if (-not $f) { Write-Output ('L|' + $d + '|NOLOG') } else { Write-Output ('L|' + $d + '|' + (RB $f.FullName %d) + '|' + $f.Length) } } "
          "catch { Write-Output ('L|' + $d + '|ERR') } }; "
          "foreach ($r in @(%s)) { $p = Join-Path $v2 $r; $i = Get-Item -LiteralPath $p -ErrorAction SilentlyContinue; "
          "if ($i) { Write-Output ('S|' + $r + '|' + $i.Length + '|' + $i.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')) } "
          "else { Write-Output ('S|' + $r + '|NONE') } }; Write-Output 'END|'"
          % (root, q(ini_rels), q(log_dirs), LOG_DIR, LOG_TAIL, q(stat_rels)))
    out = hostshell.powershell(ps, 240)
    if "END|" not in out:
        raise OpRefused("чтение стойки оборвалось (нет метки конца)")
    ini, logs, st = {}, {}, {}
    for ln in out.splitlines():
        parts = ln.strip().split("|")
        if len(parts) < 3:
            continue
        kind, rel, val = parts[0], parts[1], parts[2]
        if kind == "I":
            ini[rel] = None if val in ("NONE", "ERR") else base64.b64decode(val)
            if val == "ERR":
                ini[rel + "#err"] = True
        elif kind == "L":
            logs[rel] = "NOLOG" if val == "NOLOG" else None if val == "ERR" else _log_text(base64.b64decode(val))
            if len(parts) > 3 and parts[3].strip().isdigit() and int(parts[3]) > LOG_TAIL:
                logs[rel + "#trunc"] = True          # ★ ревизия 45 Н-4: прочитан только хвост — паспорта в нём может не быть
        elif kind == "S":
            st[rel] = None if val == "NONE" else (int(val), parts[3] if len(parts) > 3 else "")
    return ini, logs, st


def _log_text(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1251", "replace")


def last_run(text):
    """Последний запуск журнала патчей → {start, pid, product, total: (применено, пропущено, ошибок) | None, marks: {секция: ok|off|bad},
    version_bad, master_off} или None (паспорта «Хост   :» нет)."""
    ls = text.splitlines()
    starts = [i for i, ln in enumerate(ls) if "Хост   :" in ln]
    if not starts:
        return None
    s0 = starts[-1]
    head = next((m for m in (_HEAD.search(ln) for ln in reversed(ls[max(0, s0 - 400):s0])) if m), None)
    block = ls[s0:]
    end = next((i for i, ln in enumerate(block) if "=== итог" in ln), None)
    inst = block if end is None else block[:end + 1]
    marks = {}
    for ln in inst:
        m = _MARK.search(ln)
        if m:
            marks[m.group(2)] = {"OK": "ok", "ВЫКЛ": "off"}.get(m.group(1), "bad")
    tot = _TOTAL.search(block[end]) if end is not None else None
    return {"start": head.group(2) if head else None, "pid": int(head.group(3)) if head else None, "product": head.group(1) if head else None,
            "total": [int(x) for x in tot.groups()] if tot else None, "marks": marks,
            "version_bad": any("не поддерживается" in ln for ln in inst), "master_off": any("MasterEnable=0" in ln for ln in inst)}


MERGE_GRACE = 120                         # с: DLL при старте сама дописывает ini (MergeMissing) — запись в эти секунды не «правка после старта»


def ini_newer(mtime, start):
    """★ ревизия 45 Н-4: ini изменён ПОСЛЕ старта последнего запуска (с точностью до секунды и с запасом MERGE_GRACE на запись
    MergeMissing при старте) → True / False / None (не прочитано)."""
    import datetime as _dt
    if not mtime or not start:
        return None
    try:
        m = _dt.datetime.strptime(mtime[:19], "%Y-%m-%d %H:%M:%S") if len(mtime) >= 19 else _dt.datetime.strptime(mtime[:16], "%Y-%m-%d %H:%M")
        s = _dt.datetime.strptime(start[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if len(mtime) < 19:                    # время ini без секунд — сравнение до минуты не годится (ложное «ждёт рестарта»): не знаем
        return None if abs((m - s).total_seconds()) < 60 + MERGE_GRACE else m > s
    return (m - s).total_seconds() > MERGE_GRACE


def _mode(state, enabled, mode_val, has_mode, ini_newer):
    """Режим патча копии по итогу последнего запуска и ini. ini_newer — ini изменён после старта последнего запуска (True / False / None)."""
    if state is None:
        return "nolog"
    if state == "bad":
        return "failed"
    if state == "off":
        if not enabled:
            return "off"
        return "pending_on" if ini_newer else "self_off"     # self_off — в ini включён, а установка сама вернула «выключен» (P08 при P49)
    if not enabled:
        return "pending_off"
    if has_mode and str(mode_val).strip() == "0":
        return "journal"
    return "active"


def state(force=False, dll_only=None):
    """Состояние настроек всех DLL (см. шапку). Кэш 60 с (force — заново)."""
    hit = _cache.get("state")
    if hit and not force and time.monotonic() - hit[0] < 60 and dll_only is None:
        return hit[1]
    cat = K.catalog()
    dlls = [d for d in K.DLL_INI if dll_only in (None, d)]
    ini_rels, log_dirs = [], []
    for d in dlls:
        ini, fam = K.DLL_INI[d]
        for g in E.folders(fam):
            ini_rels.append(E.rel_of(g, ini))
            log_dirs.append(g)
    try:
        raw, logs, st_ini = _read(ini_rels, log_dirs, ini_rels)
    except (hostshell.HostError, OpRefused) as ex:
        raise OpRefused("настройки патчей не прочитаны: %s" % str(ex)[:300])
    out = {"dlls": [], "warnings": [], "read_at": E.utc_now()}
    for d in dlls:
        ini, fam = K.DLL_INI[d]
        cd = cat["dlls"][d]
        folders = E.folders(fam)
        tabs, cps = {}, []
        for g in folders:
            rel = E.rel_of(g, ini)
            b = raw.get(rel)
            lg = logs.get(g)
            run = last_run(lg) if isinstance(lg, str) and lg != "NOLOG" else None
            sti = st_ini.get(rel)
            trunc = bool(logs.get(g + "#trunc"))
            c = {"folder": g, "read": b is not None, "md5": E.md5b(b) if b is not None else None, "mtime": sti[1] if sti else None,
                 "ini_newer": ini_newer(sti[1] if sti else None, (run or {}).get("start")),
                 "log": "unread" if lg is None else "none" if lg == "NOLOG" else ("ok" if run else ("tail" if trunc else "norun")), "run": run}
            if c["log"] == "tail":
                out["warnings"].append("%s %s: журнал патчей больше %d КБ, в прочитанном хвосте нет паспорта запуска — режимы «не прочитано», "
                                       "а не «нет в журнале»" % (d, g, LOG_TAIL // 1024))
            if b is not None:
                t = K.IniTable(rel, b)
                tabs[g] = t
                c.update(version=t.get("General", "Version"), master=t.get("General", "MasterEnable"), enc=t.enc, bad=t.bad)
                if str(c["version"]) != str(cd["version"]):
                    # ★ ревизия 45 С-5 / С-6: правка настроек такой копии — отказ до выкладки DLL (cs_kinds/patchcfg.k_patch_set)
                    out["warnings"].append("%s %s: Version в ini %s, исходник %s — живая DLL другой сборки: тип и предел по исходнику Version %s, "
                                           "правка настроек этой DLL панелью — только после выкладки DLL этой сборки (сначала DLL отдельным "
                                           "рестартом, потом наборы)" % (d, g, c["version"], cd["version"], cd["version"]))
                if t.bad:
                    out["warnings"].append("%s %s: %s не собирается обратно байт в байт (кодировка %s) — панелью не правится" % (d, g, ini, t.bad))
            else:
                out["warnings"].append(("%s %s: %s не прочитан (ошибка чтения)" if raw.get(rel + "#err") else "%s %s: %s не прочитан (файла нет)")
                                       % (d, g, ini))
            if lg is None:
                out["warnings"].append("%s %s: журнал патчей не прочитан — режимы «не прочитано», а не «выключено»" % (d, g))
            cps.append(c)
        lay = E._layout()
        for twin, field in lay.TWINS.items():
            a = next((c for c in cps if c["folder"] == twin), None)
            b_ = next((c for c in cps if c["folder"] == field), None)
            if a and b_ and a["md5"] and b_["md5"] and a["md5"] != b_["md5"]:
                out["warnings"].append("%s: %s ≠ %s (md5 %s ≠ %s) — паритет Ch2 нарушен, restart_stack не запустит стойку (код 6)" % (
                    ini, twin, field, a["md5"][:8], b_["md5"][:8]))
        secs = []
        for s in cd["sections"]:
            keys = []
            for k in s["keys"]:
                vals = {g: (t.get(s["name"], k["key"]) if g in tabs else None) for g, t in ((g, tabs.get(g)) for g in folders)}
                secret = K.is_secret(k["key"])
                shown = {g: ("•••" if (secret and v) else v) for g, v in vals.items()}
                present = [v for g, v in vals.items() if g in tabs]
                vo = K.view_only_why(k["key"], s["name"], k) or next(
                    (K.view_only_why(k["key"], s["name"], k, v) for v in present if v and K.view_only_why(k["key"], s["name"], k, v)), None)
                keys.append({"key": k["key"], "def": "•••" if secret else k["def"], "type": k["type"], "lo": k["lo"], "hi": k["hi"],
                             "range_src": k.get("range_src"), "range_how": k.get("range_how"), "excl": k.get("excl") or [],
                             "off_when": k.get("off_when") or [], "maxlen": k.get("maxlen"), "values": shown,
                             "diverge": len(set(present)) > 1, "missing": [g for g in tabs if vals[g] is None], "secret": secret,
                             "edit": not vo and not secret, "view_only": vo or ("секрет" if secret else None),
                             "reads": ["%s:%d" % (r["file"], r["line"]) for r in k["reads"][:3]],
                             "comment": (k.get("comment") or "")[:400]})
            has_mode = any(k["key"] == "Mode" for k in s["keys"])
            modes = {}
            for c in cps:
                g = c["folder"]
                if g not in tabs:
                    modes[g] = "unread"
                    continue
                if c["log"] in ("unread", "tail"):
                    modes[g] = "unread"
                    continue
                if s["name"] != "General" and not tabs[g].sections(s["name"]):
                    modes[g] = "absent"                      # секции нет в живом ini — живая DLL её не знает
                    continue
                en = tabs[g].get(s["name"], "Enabled")
                master = str(c.get("master") or "0").strip() != "0"
                enabled = master and (en is None or en.strip() not in ("0", ""))
                st = (c["run"] or {}).get("marks", {}).get(s["name"]) if c["run"] else None
                modes[g] = "general" if s["name"] == "General" else _mode(st, enabled, tabs[g].get(s["name"], "Mode"), has_mode, c.get("ini_newer"))
            users = [x["name"] for x in cd["sections"] if s["name"] in (x.get("needs") or {})]
            hard = [u for u, _k, _w in K.hard_deps(d).get((d, s["name"]), [])]
            secs.append({"name": s["name"], "id": s["id"], "index": s["index"][:2], "docs": s.get("docs") or [], "comment": (s.get("comment") or "")[:600],
                         "keys": keys, "modes": modes, "needs": s.get("needs") or {}, "used_by": users, "hard_users": hard,
                         "panel": (d, s["name"]) in K.PANEL_NEEDS, "strong": K.strong_section(d, s),
                         "present": [g for g in tabs if tabs[g].sections(s["name"])]})
        # ★ ревизия 45 (мелочь): чтения секций, которых нет в шаблоне (P20 AsdaPatch — значение всегда умолчание кода, ini его не содержит)
        outside = [{"section": n, "where": w} for n, w in sorted((cd.get("outside_why") or {}).items())]
        out["dlls"].append({"dll": d, "ini": ini, "family": fam, "version_src": cd["version"], "copies": cps, "sections": secs,
                            "outside": outside})
    if dll_only is None:
        _cache["state"] = (time.monotonic(), out)
    return out


def configs():
    """Стоковые конфиги стойки: классификация + содержимое не секретных (только чтение). Секреты — без содержимого."""
    rels, stat_rels = [], []
    rows = []
    for fam, sub, what, why, secret in STACK_CONFIGS:
        for g in _folders(fam):
            r = _rel(g, sub)
            (stat_rels if secret else rels).append(r)
            rows.append((fam, g, sub, r, what, why, secret))
    try:
        raw, _l, st = _read(rels, [], stat_rels)
    except (hostshell.HostError, OpRefused) as ex:
        raise OpRefused("конфиги стойки не прочитаны: %s" % str(ex)[:300])
    out = []
    for fam, g, sub, r, what, why, secret in rows:
        item = {"folder": g, "file": sub, "what": what, "edit": sub in K.CONFIGS, "why": why, "secret": secret}
        if secret:
            s = st.get(r)
            item.update(read=s is not None, size=s[0] if s else None, mtime=s[1] if s else None, text=None)
        else:
            b = raw.get(r)
            item.update(read=b is not None, md5=E.md5b(b) if b is not None else None,
                        text=hostshell.decode_text(b)[:4000] if b is not None else None)
            if b is not None and _looks_secret(item["text"]):
                item.update(text=None, secret=True, why=(why or "") + " — в файле найдены пароль / DSN, содержимое скрыто")
        out.append(item)
    return {"configs": out}


# ★ ревизия 45 Н-7: и учётные имена — USER= / …USER…= / LOGIN= / ID= / UID= (Server_Info ChannelManager и подобные)
_SECRET_LINE = re.compile(r"^\s*(\w*(pass|pwd|password|secret|token|hmac|user|login)\w*|uid|id|userid|loginid|\w*dsn)\s*=", re.I | re.M)


def _looks_secret(text):
    return bool(text and _SECRET_LINE.search(text))
