# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""autoblock.py — «Античит: автоблок и EAC» (шаг А6.8, часть «чтение», 22.11.2026; разбор Reports/admin_center/research_a6_economy_20261121.md
§1 строки «Автоблок P48/P69», «EAC», §3 строка А6.8; отчёт impl_a6_econ_20261121.md §А6.8). ТОЛЬКО ЧТЕНИЕ: игровые базы — логином asda_admin
(db_datareader), стойка — читателем «Настроек патчей» А5.5 (domains/patchcfg._read / state), EacServer не трогается.

Что даёт
  * ladder() — сверка лестницы санкций ac_case_config.json с patches.ini AsdaPatch всех копий GameServer (поле, Indun, Ch2) ТЕМ ЖЕ кодом,
    что консоль ПК `ac_case.py ladder --check`: функции ladder_map / parse_ini_bytes / ladder_check исполняются из исходника
    AstoryServer/Tools/Anticheat/ac_case.py (на ПК) или из его копии ext/anticheat/ (на сервере — только она, со сверкой md5 манифеста выкладки,
    domains/acsrc). Отличие от консоли — только в подаче: копия, которую не удалось прочитать, помечена «не прочитано» (консоль печатает
    её строки «РАСХОЖДЕНИЕ» с ini=None — это число тоже отдаётся, ladder_check_bad). Рядом: паритет копий (md5 ini поля и Ch2 —
    restart_stack код 6; значения секций P48 / P69 / P73 во всех копиях), режим секций по журналу патчей (patchcfg.state: «действует» /
    «журнал» Mode=0 / «выключен» / «не встал»), ключи автоблоков и счётчики киков и нарушений (CounterFile P48 [Kicks] и P69 [Mode0|Mode1] —
    формат «счёт,начало» и «счёт,ступень,первое,последнее», p48_kick_autoblock.cpp:48-50, p69_integrity_autoblock.cpp:105-131).
    Правка автоблока — НЕ здесь: только наборами patch.set «Настроек патчей» (#/shops/patches) и рестартом стойки.
  * history(q) — история автоблоков за период: ac.kick_block (кики и «автоблок» P48, засчитан / почему нет), ac.other вид 62 (ступень P69),
    BlockList (действует) + BlockHistory (снят) Joy1… AsdaStoryOp с причиной, сроком и снятием; происхождение блока — по причине
    (UPHackBlock пишет «Speed Hack», UPUserBlock — «Login Block», дело — «AC-NNNN …», ac0u_01_migrate.sql) и по паре в журнале
    (кик P48 с block_sent / ступень P69 с опкодом 2271 той же учётки в пределах MATCH_MIN минут), блок и снятие панелью — по adm.audit
    (account.block / account.unblock / account.block.undo с той же учёткой и временем начала). Служебные учётки ≤ 5000 — отдельным итогом.
    ★ ревизия 58: снятие «по сроку» — только где установимо (BlockHistory времени снятия не хранит: «срок прошёл — по сроку или досрочно»;
    дело AC-… — время и способ снятия из joylog1.san.case_block); «Speed Hack» без пары P48 / P69 — GM-блок 6094 по Log_SpeedHack
    («GM Recv_CharBlock() UserNick <GM>, Time <ч>», белый список logs.py, бюджет на пользователя); счётчик P69 — секции [Mode0] наблюдение
    и [Mode1] боевой раздельно; CounterFile без ключа — умолчание DLL; P48 — окно WindowHours (счёт сгорел).
  * eac(uid) — EAC по учётке: процесс и порты AsdaEacServer (domains/status.py), режим моста P73 в копиях, KICK-события P73 и сводка
    журнала учётки (players.eac_summary), блок учётки сейчас, счётчики автоблоков; ★ А6.8 (вторая часть, 22.11): состояние сессии EAC
    «сейчас» — eac_live(): точка статуса службы AsdaEacServer 127.0.0.1:8447 (AstoryServer/EacServer/src/AdminStatus.h, только чтение;
    заголовок X-Asda-Key — секрет из secrets/eac_status.key службы ПАНЕЛИ, копия секрета службы EAC; секрет не печатается и не отдаётся):
    подключён ли, Authenticated, игровые сессии и их защита, срок, решение и KICK, последние события. IP (канала EAC и игры) — только с
    правом players.view_net (поля net). Служба EAC и панель — одна машина: на ПК точки нет — честно «только на сервере».
Побочных эффектов при импорте нет.
"""
import bisect
import datetime
import hashlib
import http.client
import json
import socket
import os
import re
import threading
import time

from core import config, db, hostshell
from core.ops import OpRefused
from domains import acjournal, acsrc, patchcfg as V, players, shopdata as E, status
from domains.cs_kinds import patchcfg as K

AC_SRC = acsrc.AC_SRC                       # исходник лестницы на ПК (AstoryServer/Tools/Anticheat)
AC_EXT = acsrc.AC_EXT                       # его копия в дереве службы (ext/anticheat; на сервере — только она)
AC_FILES = ("ac_case.py", "ac_case_config.json")   # что кладёт выкладка в ext/anticheat (deploy_admin_center.build_zip, манифест md5)
SECTIONS = ("P48_KickAutoBlock", "P69_IntegrityAutoBlock", "P73_EacBridge")
SVC_MAX = 5000                              # служебные учётки (players.OPERATOR_MAX_UID)
CACHE_S = 60                                # сверка лестницы: чтение стойки не чаще раза в минуту на всех
HIST_MAX = 2000                             # строк одного источника истории за запрос (больше — пометка capped)
AUDIT_MAX = 5000                            # строк adm.audit (блок / снятие панелью) за запрос
DAYS_DEF, DAYS_MAX = 30, 366                # период истории по умолчанию / предел
MATCH_MIN = 5                               # блок BlockList ↔ событие журнала той же учётки: разница во времени, минут
PERM_YEARS = 20                             # срок длиннее — бессрочный (UPHackBlock: −1 → 30 лет)
EDIT_LINK = "#/shops/patches"               # правка автоблока — набор patch.set (А5.5)
# ★ А6.8 (вторая часть): точка статуса EAC (AdminStatus.h). Адрес и файл секрета — Config.eac_status_port / eac_status_secret (config.ini
#   может переопределить); самотест подставляет свою точку через EAC_POINT = {"port": N, "secret_file": путь} (тогда и не на сервере).
EAC_POINT = None
EAC_TIMEOUT_S = 3.0                         # предел запроса к точке (ядро отвечает за ≤ 1,5 с даже при старом снимке)
EAC_SCHEMA = "a68."                         # версия схемы ответа точки (AdminStatus.cpp kVersion «a68.N»)
EAC_NOTES = {
    "pc": "состояние сессии EAC — только на сервере: точка 127.0.0.1 службы AsdaEacServer, панель и консоль на ПК её не видят",
    "no_secret": "секрет точки статуса EAC не прочитан (%s) — состояние сессии не показано",
    "short": "секрет точки статуса EAC короче 32 знаков — состояние сессии не показано",
    "no_point": "точка статуса EAC не отвечает (служба AsdaEacServer не запущена или [AdminStatus] Enabled=0) — состояние сессии не показано",
    "timeout": "точка статуса EAC не ответила за %d с — состояние сессии не показано",
    "bad_key": "точка статуса EAC отказала: ключ не подошёл (секрет панели не совпадает с секретом службы EAC)",
    "rate": "точка статуса EAC: слишком частые запросы — повторите через минуту",
    "error": "точка статуса EAC ответила ошибкой: HTTP %d (%s)",
    "schema": "точка статуса EAC: схема ответа %s, панель ждёт a68.* — состояние сессии не показано",
}
EAC_NOTE = EAC_NOTES["pc"]                  # пометка для ПК (живой самотест и консоль ПК)
LADDER_NOTE = ("сверка как ac_case.py ladder --check: сроки ступеней 3–5 лестницы против часов P69 Stage1/2/3Hours и P48 BlockHours "
               "в каждой копии GameServer; пороги (KickThreshold, StageNCount) лестница не задаёт и не сверяет, Enabled и Mode тоже не "
               "сверяются — при P69 Mode=0 ступени 3–5 автоматически не исполняются (состояние каждого патча — строками ниже)")
# ★ ревизия 58 М-3: CounterFile без ключа в ini — умолчание DLL (p48_kick_autoblock.cpp:426, p69_integrity_autoblock.cpp:442; от папки exe)
COUNTER_DEFAULT = {"P48_KickAutoBlock": "..\\GameServer\\ConfigSet\\ac_kick_counter.ini",
                   "P69_IntegrityAutoBlock": "..\\GameServer\\ConfigSet\\ac_integrity_counter.ini"}
# ★ ревизия 58 Н-2: секции счётчика P69 — разные счёты (p69_integrity_autoblock.cpp:39, :103): [Mode0] — наблюдение «был бы блок»,
#   [Mode1] — боевой; наблюдение в боевой не переносится. P48 — [Kicks] с окном WindowHours (p48:51, умолчание 24 — p48:414)
COUNTER_SECTIONS = {"P48_KickAutoBlock": (("Kicks", "kicks"),), "P69_IntegrityAutoBlock": (("Mode0", "observe"), ("Mode1", "live"))}
WINDOW_DEFAULT = 24
GM_LOG_KIND = "Log_SpeedHack"               # ★ ревизия 58 М-2: GM-блок 6094 (Recv_CharBlock, GameServer.c:133301) пишется сюда
GM_LOG_RX = re.compile(r"^(\d+) Mon (\d+) Day (\d+) hou (\d+) min (\d+) sec : GM Recv_CharBlock\(\) UserNick (.+?), Time (-?\d+)\s*$")
GM_MATCH_S = 60                             # BlackDate smalldatetime округляет до минуты: строка журнала и начало блока — в пределах 60 с
_cache = {}
_lock = threading.Lock()


# =====================================================================================================================
# Код лестницы — тот же, что у консоли ПК
# =====================================================================================================================
def source():
    """Исходник ac_case.py и конфиг лестницы → (модуль, cfg, {where, code_md5, config_md5}). На сервере — только ext/ с манифестом."""
    d = acsrc.pick(AC_SRC, AC_EXT)
    try:
        mods, h = acsrc.load(d, ("ac_case",), "autoblock_src_")
        raw = acsrc.read_verified(os.path.join(d, "ac_case_config.json"))
    except OSError as ex:                                   # нет файла / нет доступа — понятный отказ, а не 500
        raise OpRefused("исходник лестницы ac_case не прочитан: %s" % (getattr(ex, "filename", None) or ex.__class__.__name__))
    m = mods["ac_case"]
    cfg = dict(m.DEFAULT_CONFIG)                       # = ac_case.load_config(): умолчания + файл (без второго чтения файла)
    try:
        cfg.update(json.loads(raw.decode("utf-8")))
    except ValueError as ex:
        raise OpRefused("конфиг лестницы ac_case_config.json не разобран: %s" % str(ex)[:200])
    where = "ext" if acsrc._under(d, acsrc.EXT) else "port"
    return m, cfg, {"where": where, "code_md5": h, "config_md5": hashlib.md5(raw).hexdigest()}


def _counter_rel(folder, val):
    """CounterFile ini (относительно папки exe) → путь от v2 или None (абсолютный / выход за v2 — не читается)."""
    if not val or ":" in val or val.startswith(("\\", "/")):
        return None
    parts = []
    for p in (folder + "\\" + val.replace("/", "\\")).split("\\"):
        if p in ("", "."):
            continue
        if p == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(p)
    return "\\".join(parts) if len(parts) >= 2 else None


def _counters(m, raw, sec):
    """Секция sec файла счётчика → {номер учётки: [числа]} (ac_case.parse_ini_bytes — тот же разбор ini); файла нет — None."""
    if raw is None:
        return None
    out = {}
    for k, v in (m.parse_ini_bytes(raw).get(sec) or {}).items():
        if k.strip().lstrip("-").isdigit():
            out[int(k)] = [int(x) if x.strip().isdigit() else None for x in v.split(",")]
    return out


def _now_unix():
    """Секунды unix сейчас (самотест подменяет — проверки не от времени запуска)."""
    return int(time.time())


def _int_or(v, d):
    try:
        return int(str(v).split(";")[0].strip())
    except (TypeError, ValueError):
        return d


def patch_states(ini_by, folders):
    """★ ревизия 58 М-1: состояние каждого патча автоблока по ini копий (Enabled / Mode; умолчания — исходники: P48 Enabled 1, P69 Enabled 1
    Mode 0 — p69:409-410 «всё, кроме 1, — 0», P73 Enabled 0 Mode 0) → [{section, copies, enabled, mode, why}] — одна строка на набор значений."""
    defs = {"P48_KickAutoBlock": ("1", None), "P69_IntegrityAutoBlock": ("1", "0"), "P73_EacBridge": ("0", "0")}
    groups = {}
    for s in SECTIONS:
        for g in folders:
            if not ini_by.get(g):
                continue
            sec = ini_by[g].get(s) or {}
            en = "0" if _int_or(sec.get("Enabled", defs[s][0]), 1) == 0 else "1"
            md = None if defs[s][1] is None else ("1" if _int_or(sec.get("Mode", defs[s][1]), 0) == 1 else "0")
            groups.setdefault((s, en, md), []).append(g)
    out = []
    for (s, en, md), gs in groups.items():
        if en == "0":
            why = "%s: Enabled=0 — патч выключен, автоблок по нему не идёт" % s
        elif s == "P48_KickAutoBlock":
            why = "P48_KickAutoBlock: Enabled=1 — автоблок по кикам действует"
        elif s == "P69_IntegrityAutoBlock":
            why = ("P69_IntegrityAutoBlock: Enabled=1, Mode=1 — ступени исполняются (блок 2271 / UPHackBlock)" if md == "1" else
                   "P69_IntegrityAutoBlock: Enabled=1, Mode=0 — только журнал «был бы блок»: ступени 3–5 автоматически не исполняются (2271 не уходит)")
        else:
            why = ("P73_EacBridge: Enabled=1, Mode=1 — KICK от EAC исполняется" if md == "1" else
                   "P73_EacBridge: Enabled=1, Mode=0 — KICK от EAC только пишется в журнал")
        out.append({"section": s, "copies": gs, "enabled": en, "mode": md, "why": why, "journal_only": md == "0" and en == "1"})
    return out


def _unix(v):
    """Секунды unix → «ГГГГ-ММ-ДД ЧЧ:ММ:СС UTC» (счётчики пишут время в UTC, p48 NowUnix) или None."""
    if not v:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(v), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + " UTC"
    except (OverflowError, OSError, ValueError):
        return None


def ladder(force=False):
    """Сверка лестницы с patches.ini AsdaPatch всех копий GameServer (см. шапку). Кэш CACHE_S на процесс."""
    with _lock:
        hit = _cache.get("ladder")
        if hit and not force and time.monotonic() - hit[0] < CACHE_S:
            return hit[1]
    m, cfg, src = source()
    try:
        lad = m.ladder_map(cfg)
    except Exception as ex:                                  # CaseError исходника: ступеней не 0..6
        raise OpRefused("лестница санкций не прочитана: %s" % str(ex)[:200])
    folders = E.folders("GSP")
    ini_name = K.DLL_INI["AsdaPatch"][0]
    rels = [E.rel_of(g, ini_name) for g in folders]
    try:
        raw, _l, st = V._read(rels, [], rels)
    except (hostshell.HostError, OpRefused) as ex:
        raise OpRefused("patches.ini копий GameServer не прочитаны: %s" % str(ex)[:300])
    errors, notes, copies, ini_by, unread = [], [LADDER_NOTE], [], {}, set()
    for g, r in zip(folders, rels):
        b = raw.get(r)
        sti = st.get(r)
        if b is None:
            unread.add(g)
            errors.append(("%s: patches.ini не прочитан (ошибка чтения)" if raw.get(r + "#err") else "%s: patches.ini не прочитан (файла нет)") % g)
            ini_by[g] = {}                                    # как ac_case.read_stand_ini: нет доступа — пустой словарь
            copies.append({"folder": g, "read": False, "md5": None, "mtime": sti[1] if sti else None})
            continue
        ini_by[g] = m.parse_ini_bytes(b)
        copies.append({"folder": g, "read": True, "md5": E.md5b(b), "mtime": sti[1] if sti else None,
                       "sections": {s: ini_by[g].get(s) for s in SECTIONS}})
    check = []
    for srv, stp, key, v, hrs, ok in m.ladder_check(cfg, ini_by):
        check.append({"server": srv, "step": stp, "key": key, "ini": v, "ladder": hrs, "ok": bool(ok), "unread": srv in unread})
    # паритет копий: md5 ini пары «поле — Ch2» (restart_stack код 6) и значения секций автоблока во всех прочитанных копиях
    lay = E._layout()
    by_f = {c["folder"]: c for c in copies}
    parity = []
    for twin, field in lay.TWINS.items():
        a, b_ = by_f.get(twin), by_f.get(field)
        if a and b_ and a["md5"] and b_["md5"]:
            parity.append({"pair": [field, twin], "same": a["md5"] == b_["md5"], "md5": [b_["md5"], a["md5"]]})
    diverge = []
    read_ok = [c for c in copies if c["read"]]
    for s in SECTIONS:
        keys = sorted({k for c in read_ok for k in (c["sections"].get(s) or {})})
        for k in keys:
            vals = {c["folder"]: (c["sections"].get(s) or {}).get(k) for c in read_ok}
            if len(set(vals.values())) > 1:
                diverge.append({"section": s, "key": k, "values": vals})
    for p in parity:
        if not p["same"]:
            errors.append("patches.ini: %s ≠ %s (md5 %s ≠ %s) — паритет Ch2 нарушен" % (p["pair"][0], p["pair"][1], p["md5"][0][:8], p["md5"][1][:8]))
    # режимы секций по журналу патчей (тот же разбор, что «Настройки патчей»)
    modes = {}
    try:
        stt = V.state(dll_only="AsdaPatch")
        d0 = next((d for d in stt["dlls"] if d["dll"] == "AsdaPatch"), None)
        for s in (d0 or {}).get("sections", []):
            if s["name"] in SECTIONS:
                modes[s["name"]] = s["modes"]
    except OpRefused as ex:
        errors.append("режимы патчей по журналу не прочитаны: %s" % str(ex)[:300])
    # счётчики автоблоков (CounterFile каждой копии — у поля, Indun и Ch2 по умолчанию один и тот же файл GameServer\ConfigSet)
    crel = set()
    window = WINDOW_DEFAULT
    for g in folders:
        if not ini_by.get(g):
            continue
        for s in COUNTER_SECTIONS:
            sec = ini_by[g].get(s) or {}
            r = _counter_rel(g, sec.get("CounterFile", COUNTER_DEFAULT[s]))   # нет ключа — путь по умолчанию DLL (ревизия 58 М-3)
            if r:
                crel.add((s, r))
        window = _int_or((ini_by[g].get("P48_KickAutoBlock") or {}).get("WindowHours", window), window)
    now_u = _now_unix()
    counters = {}
    if crel:
        try:
            craw, _l2, cst = V._read(sorted({r for _s, r in crel}), [], sorted({r for _s, r in crel}))
        except (hostshell.HostError, OpRefused) as ex:
            craw, cst = {}, {}
            errors.append("счётчики автоблоков не прочитаны: %s" % str(ex)[:300])
        for s, r in sorted(crel):
            if r not in craw:
                continue
            if craw.get(r) is None:
                notes.append("%s: файла счётчика %s нет — счёта ещё не было (DLL создаёт его на первом засчитанном событии) или он не прочитан"
                             % (s, r))
            for sec, kind in COUNTER_SECTIONS[s]:
                c = _counters(m, craw.get(r), sec)
                x = {"file": r, "section": sec, "kind": kind, "read": c is not None, "accounts": len(c or {}),
                     "mtime": (cst.get(r) or (None, None))[1], "_rows": c or {}}
                if kind == "kicks":                          # ★ ревизия 58 М-5: окно WindowHours от первого кика (0 — не сгорает)
                    x["window_hours"] = window
                    x["expired"] = sum(1 for v in (c or {}).values() if window > 0 and len(v) > 1 and v[1] and now_u - v[1] > window * 3600)
                counters.setdefault(s, []).append(x)
    out = {"read_at": E.utc_now(), "source": src, "ladder": [dict(lad[k], step=k) for k in sorted(lad)],
           "appeal_days": cfg.get("appeal_days"), "retention_days": cfg.get("retention_days"),
           "two_sources_from_step": cfg.get("two_sources_from_step"), "check": check,
           "mismatches": sum(1 for c in check if not c["ok"] and not c["unread"]), "unread_checks": sum(1 for c in check if c["unread"]),
           "ladder_check_bad": sum(1 for c in check if not c["ok"]), "copies": copies, "parity": parity, "diverge": diverge, "modes": modes,
           "states": patch_states(ini_by, folders), "now_unix": now_u,
           "counters": {s: [{k: v for k, v in x.items() if k != "_rows"} for x in xs] for s, xs in counters.items()},
           "edit_link": EDIT_LINK, "errors": errors, "notes": notes}
    with _lock:
        _cache["ladder"] = (time.monotonic(), out)
        _cache["counters"] = counters
    return out


def counters_of(uid):
    """Счётчики автоблоков учётки по последнему прочтению ladder() → {P48: {...}, P69: {...}}."""
    with _lock:
        cs = _cache.get("counters") or {}
        hit = _cache.get("ladder")
    now_u = (hit[1].get("now_unix") if hit else None) or _now_unix()
    out = {}
    for s, xs in cs.items():
        for x in xs:
            v = (x.get("_rows") or {}).get(int(uid))
            if not v:
                continue
            if s == "P48_KickAutoBlock":
                first = v[1] if len(v) > 1 else None
                w = x.get("window_hours", WINDOW_DEFAULT)
                out["P48"] = {"file": x["file"], "section": x["section"], "count": v[0], "first": _unix(first), "window_hours": w,
                              "window_end": _unix(first + w * 3600) if (first and w > 0) else None,
                              "expired": bool(first and w > 0 and now_u - first > w * 3600)}
            else:                                            # ★ ревизия 58 Н-2: наблюдение и боевой — раздельно, с секцией
                out.setdefault("P69", {})[x["kind"]] = {"file": x["file"], "section": x["section"], "count": v[0],
                                                         "stage": v[1] if len(v) > 1 else None,
                                                         "first": _unix(v[2] if len(v) > 2 else None), "last": _unix(v[3] if len(v) > 3 else None)}
    return out


# =====================================================================================================================
# История автоблоков
# =====================================================================================================================
def _period(q, r):
    """Период ГГГГММДД из запроса (параметром; по умолчанию — DAYS_DEF суток по часам SQL-сервера) → (from, to)."""
    f = acjournal.parse_day(q.get("from"), "from")
    t = acjournal.parse_day(q.get("to"), "to")
    if not f or not t:
        d = r.one("SELECT CONVERT(char(8), DATEADD(DAY, ?, GETDATE()), 112) AS f, CONVERT(char(8), GETDATE(), 112) AS t", (1 - DAYS_DEF,))
        f, t = f or d["f"], t or d["t"]
    if f > t:
        raise OpRefused("дата «с» позже даты «по»")
    span = (datetime.datetime.strptime(t, "%Y%m%d") - datetime.datetime.strptime(f, "%Y%m%d")).days + 1
    if span > DAYS_MAX:
        raise OpRefused("период истории автоблоков — не длиннее %d суток" % DAYS_MAX)
    return f, t


def svc_mode(q):
    """svc: sep — служебные учётки ≤ 5000 отдельным итогом (по умолчанию), in — в общем итоге."""
    v = (q.get("svc") or "sep").strip()
    if v not in ("sep", "in"):
        raise OpRefused("svc — sep (служебные отдельно) или in (в общем итоге)")
    return v


def cat_of(uid):
    """Категория учётки: service (≤ 5000) / player / none (без учётки)."""
    if uid is None:
        return "none"
    return "service" if 0 < int(uid) <= SVC_MAX else "player"


def origin_of(reason):
    """Откуда строка BlockList по тексту причины (ac0u_01_migrate.sql: UPHackBlock — «Speed Hack», UPUserBlock — «Login Block»;
    дело ac_case — «AC-NNNN …»; иначе — причина оператора: панель account.block, ac0_block_user.sql или вручную)."""
    s = (reason or "").strip()
    if s == "Speed Hack":
        return "hack"
    if s == "Login Block":
        return "user"
    if re.match(r"^AC-\d{4}\b", s):
        return "case"
    return "manual"


def _rows_json(txt):
    try:
        return json.loads(txt or "null")
    except ValueError:
        return None


def _minute(v):
    """Время строки BlockList (smalldatetime — до минуты) или из журнала («ГГГГ-ММ-ДД ЧЧ:ММ:…») → ключ «ГГГГ-ММ-ДД ЧЧ:ММ»."""
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    return str(v or "")[:16]


def _audit_rows(uids, f):
    """Блоки и снятия панелью (adm.audit, только ok) для учёток uids с даты f → {(uid, ключ минуты BlackDate): {block, lift}}."""
    out = {}
    if not uids:
        return out, None
    ids = sorted(uids)
    cn = db.admin()
    try:
        rows = db.admin_rows(cn, "SELECT TOP (%d) id, at, login, action, target, before_json, after_json, undone_by FROM adm.audit WHERE result = 'ok' "
                                 "AND action IN ('account.block', 'account.unblock', 'account.block.undo') AND at >= CONVERT(datetime2, ?, 112) "
                                 "AND target IN (%s) ORDER BY id" % (AUDIT_MAX + 1, ",".join("?" * len(ids))),
                             [f] + ["account:%d" % u for u in ids])
    finally:
        cn.close()
    capped = len(rows) > AUDIT_MAX
    for r in rows[:AUDIT_MAX]:
        a, b = _rows_json(r["after_json"]) or {}, _rows_json(r["before_json"]) or {}
        who = {"audit_id": r["id"], "at": r["at"], "login": r["login"], "action": r["action"], "undone_by": r["undone_by"]}
        if r["action"] == "account.block":
            row = a.get("row") or {}
            if row.get("Userindex") is not None:
                out.setdefault((int(row["Userindex"]), _minute(row.get("BlackDate"))), {})["block"] = who
        else:                                            # снятие: account.unblock (after.rows) / откат блока (before.rows или after.rows)
            for row in (a.get("rows") or []) + (b.get("rows") or []) + ([a["row"]] if isinstance(a.get("row"), dict) else []):
                if isinstance(row, dict) and row.get("Userindex") is not None:
                    out.setdefault((int(row["Userindex"]), _minute(row.get("BlackDate"))), {}).setdefault("lift", who)
    return out, capped


def _near(times, at, minutes=MATCH_MIN):
    """Есть ли в отсортированном списке времён times значение в пределах minutes от at (bisect — без перебора пар)."""
    if not times or at is None:
        return None
    i = bisect.bisect_left(times, at - datetime.timedelta(minutes=minutes))
    if i < len(times) and times[i] <= at + datetime.timedelta(minutes=minutes):
        return times[i]
    return None


def history(q, user=None):
    """История автоблоков (см. _history); сбой подключения к базе — понятный отказ, а не 500. user — кто читает (бюджет журналов стойки)."""
    try:
        return _history(q, user or "autoblock")
    except db.DbError as ex:
        raise OpRefused("история автоблоков не прочитана: %s" % ex)


def _case_blocks(uids, errors):
    """★ ревизия 58 Н-1: блоки дел (joylog1.san.case_block — ac_case.py пишет и наложение, и снятие) → {(uid, минута black_date): строка}."""
    out = {}
    ids = sorted(uids)
    if not ids:
        return out
    try:
        with db.GameReader("joylog1") as lg:
            for k in range(0, len(ids), 1000):
                part = ids[k:k + 1000]
                for r in lg.rows("SELECT user_index, black_date, close_date, applied_by, applied_at, lifted_by, lifted_at, lift_via FROM san.case_block "
                                 "WHERE user_index IN (%s)" % ",".join("?" * len(part)), part):
                    out[(int(r["user_index"]), _minute(r["black_date"]))] = r
    except db.DbError as ex:
        errors.append("joylog1.san.case_block: %s" % ex)
    return out


def gm_blocks(days, user, errors, notes):
    """★ ревизия 58 М-2: GM-блоки 6094 по журналу Log_SpeedHack всех копий GameServer (белый список domains/logs.py, источник gslog; бюджет
    чтения — на пользователя user) за дни days (ГГГГММДД) → [(время, ник GM, часы, копия, файл)]. Строка — «GM Recv_CharBlock() UserNick <GM>,
    Time <ч>» (GameServer.c:133301): цели в ней нет — пара с блоком по времени и сроку."""
    from domains import logs
    out = []
    if not days:
        return out
    for proc in logs.procs_of("gslog"):
        try:
            lst = logs.files("gslog", proc, GM_LOG_KIND)
        except Exception as ex:
            errors.append("журнал Log_SpeedHack %s не прочитан: %s" % (proc, ex if isinstance(ex, OpRefused) else ex.__class__.__name__))
            continue
        if lst.get("missing"):
            continue
        have = {x["name"]: x for x in lst["files"]}
        for day in sorted(days):
            name = "SpeedHack_%s.txt" % day
            if name not in have:
                if lst.get("more"):
                    notes.append("журнал Log_SpeedHack %s за %s в список файлов не попал (список обрезан) — GM-блок за эти сутки не опознан" % (proc, day))
                continue
            try:
                r = logs.scan("gslog", proc, name, kind=GM_LOG_KIND, needles=("Recv_CharBlock",), show_ip=False, user=user, size=have[name].get("size"))
            except Exception as ex:
                errors.append("журнал Log_SpeedHack %s не прочитан: %s" % (name, ex if isinstance(ex, OpRefused) else ex.__class__.__name__))
                continue
            for ln in r.get("lines") or []:
                m = GM_LOG_RX.match(ln.strip())
                if not m:
                    continue
                try:
                    at = datetime.datetime(int(day[:4]), int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
                except ValueError:
                    continue
                out.append((at, m.group(6), int(m.group(7)), proc, name))
    out.sort()
    return out


def _history(q, user="autoblock"):
    """История автоблоков за период (см. шапку). q — строка запроса: from, to (ГГГГММДД), account (номер или логин), svc (sep | in)."""
    svc = svc_mode(q)
    uids_f = acjournal.resolve_account(q.get("account"))
    errors, notes, capped = [], [], {}
    cat = acjournal.catalog()[0]
    k62 = next((r["text"] for r in cat["tables"].get("other", []) if r["n"] == 62), None)
    kick_txt = {r["n"]: r["text"] for r in cat["tables"].get("kick_block", [])}
    kicks, p69, agg = [], [], []
    with db.GameReader("joylog1") as lg:
        f, t = _period(q, lg)
        cond = "ev_local >= CONVERT(datetime2, ?, 112) AND ev_local < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))"
        args = [f, t]
        if uids_f:
            cond += " AND user_index IN (%s)" % ",".join("?" * len(uids_f))
            args += uids_f
        try:
            agg = lg.rows("SELECT event_kind, counted, ISNULL(not_counted_reason, N'') AS why, COUNT(*) AS n, COUNT(DISTINCT user_index) AS users, "
                          "SUM(CASE WHEN user_index BETWEEN 1 AND ? THEN 1 ELSE 0 END) AS n_service, MAX(ev_local) AS last "
                          "FROM ac.kick_block WHERE %s GROUP BY event_kind, counted, ISNULL(not_counted_reason, N'')" % cond, [SVC_MAX] + args)
            kicks = lg.rows("SELECT TOP (%d) event_id, ev_local, server_name, user_index, char_slot, char_name, event_kind, disc_type, disc_type_name, "
                            "reason, counted, not_counted_reason, kick_count, kick_threshold, block_hours, block_sent, owner_user_index "
                            "FROM ac.kick_block WHERE %s AND (counted = 1 OR event_kind = ?) ORDER BY ev_local DESC, event_id DESC"
                            % (HIST_MAX + 1, cond), args + [kick_txt.get(2, "")])
        except db.DbError as ex:
            errors.append("ac.kick_block: %s" % ex)
        if k62:
            try:
                p69 = lg.rows("SELECT TOP (%d) event_id, ev_local, server_name, user_index, char_slot, char_name, item_code AS stage, value1 AS cnt, "
                              "value2 AS hours, opcode, detail FROM ac.other WHERE %s AND event_kind = ? ORDER BY ev_local DESC, event_id DESC"
                              % (HIST_MAX + 1, cond), args + [k62])
            except db.DbError as ex:
                errors.append("ac.other: %s" % ex)
        else:
            errors.append("в каталоге видов ac.other нет вида 62 (ступень P69) — ступени P69 не показаны")
    capped["kick_block"], kicks = len(kicks) > HIST_MAX, kicks[:HIST_MAX]
    capped["p69"], p69 = len(p69) > HIST_MAX, p69[:HIST_MAX]
    blocks, now, us = [], None, {}
    with db.GameReader("asdastoryop") as op:
        bc = "BlackDate >= CONVERT(datetime, ?, 112) AND BlackDate < DATEADD(DAY, 1, CONVERT(datetime, ?, 112))"
        ba = [f, t]
        if uids_f:
            bc += " AND Userindex IN (%s)" % ",".join("?" * len(uids_f))
            ba += uids_f
        try:
            now = op.one("SELECT GETDATE() AS n")["n"]
            for src_t, tag in (("BlockList", "list"), ("BlockHistory", "history")):
                rr = op.rows("SELECT TOP (%d) Userindex, Uid, Cou, grade, BlackDate, CloseDate, Reason FROM dbo.%s WHERE %s "
                             "ORDER BY BlackDate DESC, Userindex" % (HIST_MAX + 1, src_t, bc), ba)
                capped[src_t] = len(rr) > HIST_MAX
                blocks += [dict(x, src=tag) for x in rr[:HIST_MAX]]
        except db.DbError as ex:
            errors.append("AsdaStoryOp BlockList / BlockHistory: %s" % ex)
        ids = sorted({int(b["Userindex"]) for b in blocks} | {int(k["user_index"]) for k in kicks + p69 if k["user_index"] is not None})
        if ids:
            try:
                for k in range(0, len(ids), 1000):
                    part = ids[k:k + 1000]
                    us.update({int(r["Userindex"]): r for r in op.rows(
                        "SELECT Userindex, Us_id, us_block FROM dbo.Us_member WHERE Userindex IN (%s)" % ",".join("?" * len(part)), part)})
            except db.DbError as ex:
                errors.append("AsdaStoryOp.Us_member: %s" % ex)
    cases = _case_blocks({int(b["Userindex"]) for b in blocks if origin_of(b["Reason"]) == "case"}, errors)
    try:
        aud, capped["audit"] = _audit_rows({int(b["Userindex"]) for b in blocks}, f)
    except db.DbError as ex:
        aud = {}
        errors.append("журнал панели adm.audit: %s" % ex)
    # пары «блок ↔ событие журнала» той же учётки: отсортированные времена по учётке (без перебора всех пар)
    t48, t69 = {}, {}
    for k in kicks:
        if k["user_index"] is not None and k["event_kind"] == kick_txt.get(2) and k["block_sent"]:
            t48.setdefault(int(k["user_index"]), []).append(k["ev_local"])
    for k in p69:
        if k["user_index"] is not None and k["opcode"] == 2271:
            t69.setdefault(int(k["user_index"]), []).append(k["ev_local"])
    for d in (t48, t69):
        for v in d.values():
            v.sort()
    # GM-блок 6094 (ревизия 58 М-2): только для «Speed Hack» без пары P48 / P69 — журнал читается за сутки таких блоков, не за весь период
    unpaired = [b for b in blocks if origin_of(b["Reason"]) == "hack" and b["BlackDate"]
                and not _near(t48.get(int(b["Userindex"])), b["BlackDate"]) and not _near(t69.get(int(b["Userindex"])), b["BlackDate"])]
    gms = gm_blocks({b["BlackDate"].strftime("%Y%m%d") for b in unpaired}, user, errors, notes) if unpaired else []
    gm_at = [g[0] for g in gms]
    out_blocks = []
    for b in blocks:
        uid = int(b["Userindex"])
        o = origin_of(b["Reason"])
        a = aud.get((uid, _minute(b["BlackDate"]))) or {}
        cb = cases.get((uid, _minute(b["BlackDate"]))) if o == "case" else None
        gm = None
        if o == "hack":
            if _near(t48.get(uid), b["BlackDate"]):
                o = "p48"
            elif _near(t69.get(uid), b["BlackDate"]):
                o = "p69"
            elif gms:
                hb = b["BlackDate"]
                hrs = (-1 if (b["CloseDate"] - hb).days > PERM_YEARS * 365 else int(round((b["CloseDate"] - hb).total_seconds() / 3600.0))) if b["CloseDate"] else None
                i = bisect.bisect_left(gm_at, hb - datetime.timedelta(seconds=GM_MATCH_S))
                while i < len(gms) and gms[i][0] <= hb + datetime.timedelta(seconds=GM_MATCH_S):
                    if hrs is not None and (gms[i][2] == hrs or (hrs == -1 and (gms[i][2] == -1 or gms[i][2] > 262800))):
                        gm = gms[i]
                        o = "gm6094"
                        break
                    i += 1
        elif a.get("block"):
            o = "panel"
        cd = b["CloseDate"]
        perm = bool(cd and b["BlackDate"] and (cd - b["BlackDate"]).days > PERM_YEARS * 365)
        hours = None if (perm or not cd or not b["BlackDate"]) else int(round((cd - b["BlackDate"]).total_seconds() / 3600.0))
        if b["src"] == "list":
            state = "active" if (cd and now and cd > now) else "expired"
            lift = None
        else:
            # ★ ревизия 58 Н-1: BlockHistory времени снятия не хранит — «по сроку» только там, где это установимо (дело: san.case_block)
            state = "lifted"
            if a.get("lift"):
                lift = "panel"
            elif cb and cb.get("lifted_at"):
                lift = "case_early" if (cd and cb["lifted_at"] < cd - datetime.timedelta(minutes=1)) else "case_term"
            elif cd and now and cd <= now:
                lift = "unknown"
            else:
                lift = "early"
        lift_by = a.get("lift") or ({"login": cb["lifted_by"], "at": cb["lifted_at"], "via_text": cb["lift_via"], "source": "san.case_block"}
                                    if cb and cb.get("lifted_at") else None)
        block_by = a.get("block") or ({"login": cb["applied_by"], "at": cb["applied_at"], "source": "san.case_block"} if cb else None) \
            or ({"gm": gm[1], "at": gm[0], "proc": gm[3], "file": gm[4], "source": GM_LOG_KIND} if gm else None)
        m = us.get(uid) or {}
        out_blocks.append({"uid": uid, "login": m.get("Us_id") or b["Uid"], "cat": cat_of(uid), "src": b["src"], "reason": b["Reason"],
                           "origin": o, "black": b["BlackDate"], "close": cd, "hours": hours, "perm": perm, "state": state, "lift": lift,
                           "lift_by": lift_by, "block_by": block_by, "us_block_now": m.get("us_block")})
    out_kicks = [{"event_id": k["event_id"], "ev_local": k["ev_local"], "server": k["server_name"], "uid": k["user_index"],
                  "login": (us.get(int(k["user_index"])) or {}).get("Us_id") if k["user_index"] is not None else None, "cat": cat_of(k["user_index"]),
                  "slot": k["char_slot"], "char": k["char_name"], "kind": k["event_kind"], "autoblock": k["event_kind"] == kick_txt.get(2),
                  "disc_type": k["disc_type"], "disc_type_name": k["disc_type_name"], "reason_text": k["reason"], "counted": k["counted"],
                  "kick_count": k["kick_count"], "kick_threshold": k["kick_threshold"], "block_hours": k["block_hours"],
                  "block_sent": k["block_sent"], "owner_uid": k["owner_user_index"]} for k in kicks]
    out_p69 = [{"event_id": k["event_id"], "ev_local": k["ev_local"], "server": k["server_name"], "uid": k["user_index"],
                "login": (us.get(int(k["user_index"])) or {}).get("Us_id") if k["user_index"] is not None else None, "cat": cat_of(k["user_index"]),
                "slot": k["char_slot"], "char": k["char_name"], "stage": k["stage"], "count": k["cnt"], "hours": k["hours"],
                "sent": k["opcode"] == 2271, "detail_text": k["detail"]} for k in p69]
    sums = {"kicks": {"player": 0, "service": 0, "none": 0}, "counted": {"player": 0, "service": 0, "none": 0},
            "autoblocks": {"player": 0, "service": 0, "none": 0}}
    reasons = {}
    for r in agg:
        n, ns = int(r["n"] or 0), int(r["n_service"] or 0)
        is_ab = r["event_kind"] == kick_txt.get(2)
        key = "autoblocks" if is_ab else "kicks"
        sums[key]["service"] += ns
        sums[key]["player"] += n - ns                    # строки без учётки (NULL) не служебные — в «игроков» (у kick_block учётка есть всегда)
        if r["counted"] and not is_ab:
            sums["counted"]["service"] += ns
            sums["counted"]["player"] += n - ns
        if not r["counted"] and not is_ab:
            reasons[r["why"] or ""] = reasons.get(r["why"] or "", 0) + n
    bsum = {}
    for b in out_blocks:
        x = bsum.setdefault(b["cat"], {"blocks": 0, "active": 0, "auto": 0})
        x["blocks"] += 1
        x["active"] += 1 if b["state"] == "active" else 0
        x["auto"] += 1 if b["origin"] in ("p48", "p69") else 0
    if svc == "sep":
        notes.append("служебные учётки ≤ %d — отдельным итогом (svc=in — в общем)" % SVC_MAX)
    return {"from": f, "to": t, "svc": svc, "now": now, "kicks": out_kicks, "p69": out_p69, "blocks": out_blocks, "sums": sums,
            "not_counted": [{"reason_db": k, "n": v} for k, v in sorted(reasons.items(), key=lambda x: -x[1])], "blocks_sum": bsum,
            "capped": capped, "match_min": MATCH_MIN, "errors": errors, "notes": notes, "ac_link": "#/ac"}


# =====================================================================================================================
# EAC по учётке — только то, что уже есть
# =====================================================================================================================
def _strip_net(v):
    """Убрать поля net (IP канала EAC и игры) любой вложенности — для ролей без players.view_net."""
    if isinstance(v, dict):
        return {k: _strip_net(x) for k, x in v.items() if k != "net"}
    if isinstance(v, list):
        return [_strip_net(x) for x in v]
    return v


def _at(u):
    """Секунды Unix от точки → «ГГГГ-ММ-ДД ЧЧ:ММ:СС» по часам машины (служба панели и EAC — одна машина) или None."""
    if not u:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(u)).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def _with_at(v):
    """Ко всем полям *_unix добавить *_at (строка времени); вложенно."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out[k] = _with_at(x)
            if k.endswith("_unix") and (x is None or isinstance(x, (int, float))):
                out[k[:-5] + "_at"] = _at(x)
        if "unix" in v and isinstance(v.get("unix"), (int, float)):
            out["at"] = _at(v["unix"])
        return out
    if isinstance(v, list):
        return [_with_at(x) for x in v]
    return v


def eac_live(uid, can_net=False):
    """★ А6.8: состояние сессии EAC учётки «сейчас» из точки статуса AsdaEacServer (127.0.0.1, только чтение) →
    {state, note, server, found, account}. state: ok | pc | no_secret | no_point | timeout | bad_key | rate | error | schema.
    Секрет — первая строка файла secrets/eac_status.key службы панели; в ответ и в журнал не попадает. Без can_net поля net убираются."""
    point = EAC_POINT
    cfg = config.get()
    if point is None and not cfg.on_server:
        return {"state": "pc", "note": EAC_NOTES["pc"]}
    port = int((point or {}).get("port") or cfg.eac_status_port)
    sfile = (point or {}).get("secret_file") or cfg.eac_status_secret
    try:
        with open(sfile, "r", encoding="utf-8-sig") as f:
            key = (f.readline() or "").strip()
    except OSError as ex:
        return {"state": "no_secret", "note": EAC_NOTES["no_secret"] % (ex.strerror or ex.__class__.__name__)}
    if len(key) < 32:
        return {"state": "no_secret", "note": EAC_NOTES["short"]}
    cn = http.client.HTTPConnection("127.0.0.1", port, timeout=EAC_TIMEOUT_S)
    try:
        cn.request("GET", "/eac/v1/account/%d" % int(uid), headers={"X-Asda-Key": key, "Connection": "close"})
        rs = cn.getresponse()
        code, body = rs.status, rs.read(4 * 1024 * 1024)
    except (socket.timeout, TimeoutError):
        return {"state": "timeout", "note": EAC_NOTES["timeout"] % int(EAC_TIMEOUT_S)}
    except (ConnectionError, OSError, http.client.HTTPException):
        return {"state": "no_point", "note": EAC_NOTES["no_point"]}
    finally:
        cn.close()
        key = None
    try:
        js = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        js = {}
    if code == 401:
        return {"state": "bad_key", "note": EAC_NOTES["bad_key"]}
    if code == 429:
        return {"state": "rate", "note": EAC_NOTES["rate"]}
    if code != 200 or not isinstance(js, dict) or not js.get("ok"):
        why = str(js.get("error") or "")[:40] if isinstance(js, dict) else ""
        return {"state": "error", "note": EAC_NOTES["error"] % (code, why or "—")}
    ver = str((js.get("server") or {}).get("version") or "")
    if not ver.startswith(EAC_SCHEMA):
        return {"state": "schema", "note": EAC_NOTES["schema"] % (ver[:20] or "?")}
    out = {"state": "ok", "note": None, "server": js.get("server"), "found": bool(js.get("found")), "account": js.get("account"),
           "read_at": _at(int(time.time())), "can_net": bool(can_net)}   # ★ р61 М-4: одной шкалой с временами EAC — часы сервера
    out = _with_at(out)
    return out if can_net else _strip_net(out)


def eac(uid, can_net=False):
    """EAC по учётке (см. _eac); сбой подключения к базе — понятный отказ, а не 500. can_net — право players.view_net (IP в live)."""
    try:
        return _eac(uid, can_net)
    except db.DbError as ex:
        raise OpRefused("EAC по учётке не прочитан: %s" % ex)


def _eac(uid, can_net=False):
    """EAC и автоблок по учётке: процесс и порты AsdaEacServer, режим P73 в копиях, KICK-события и журнал учётки, блок сейчас, счётчики;
    ★ А6.8: состояние сессии EAC сейчас — eac_live (точка статуса службы EAC)."""
    try:
        uid = int(str(uid).strip())
    except (TypeError, ValueError):
        raise OpRefused("номер учётки — целое от 1 до 2147483647")
    if uid < 1 or uid > 2 ** 31 - 1:
        raise OpRefused("номер учётки — целое от 1 до 2147483647")
    errors = []
    acc, blk = None, None
    with db.GameReader("asdastoryop") as op:
        acc = op.one("SELECT Userindex, Us_id, us_block FROM dbo.Us_member WHERE Userindex = ?", (uid,))
        if not acc:
            raise OpRefused("учётки %d нет" % uid)
        try:
            b = op.one("SELECT COUNT(*) AS n, SUM(CASE WHEN CloseDate > GETDATE() THEN 1 ELSE 0 END) AS act, MAX(CloseDate) AS until "
                       "FROM dbo.BlockList WHERE Userindex = ?", (uid,))
            blk = players.block_state(acc["us_block"], b["n"], b["act"] or 0, b["until"])
        except db.DbError as ex:
            errors.append("AsdaStoryOp.BlockList: %s" % ex)
    svc_row = None
    try:
        snap = status.snapshot()
        svc_row = next((s for s in snap.get("stack", []) if s["key"] == "eac"), None)
        if snap.get("host_error"):
            errors.append(snap["host_error"])
    except Exception as ex:                                 # снимок процессов не получен — остальное считается
        errors.append("снимок процессов не получен: %s" % str(ex)[:200])
    try:
        summ = players.eac_summary(uid)
    except db.DbError as ex:
        summ = {"tables": [], "recent": [], "errors": [str(ex)], "kicks": {}}
    lad = None
    try:
        lad = ladder()
    except OpRefused as ex:
        errors.append("режим моста P73 и счётчики не прочитаны: %s" % ex)
    live = eac_live(uid, can_net)
    p73 = {}
    if lad:
        for c in lad["copies"]:
            if c["read"]:
                s = (c.get("sections") or {}).get("P73_EacBridge") or {}
                p73[c["folder"]] = {"enabled": s.get("Enabled"), "mode": s.get("Mode"), "mode_log": (lad["modes"].get("P73_EacBridge") or {}).get(c["folder"])}
    return {"uid": uid, "login": acc["Us_id"], "cat": cat_of(uid), "us_block": acc["us_block"], "block": blk,
            "service": ({k: svc_row.get(k) for k in ("running", "ports_ok", "ports", "listening", "start", "pids")} if svc_row else None),
            "p73": p73, "summary": summ, "counters": counters_of(uid) if lad else {}, "live": live, "note": live.get("note"),
            "errors": errors + list(summ.get("errors") or []), "ac_link": "#/ac", "account_link": "#/account/%d" % uid}
