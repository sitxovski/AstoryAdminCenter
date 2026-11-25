# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""events.py — шаг А5.4 «События и сбросы» (21.11.2026; разбор Reports/admin_center/impl_a5_live_20261121.md §«А5.4»).

ЧТО ЕСТЬ У СЕРВЕРА (реверс; все «нет» — вторым способом, см. отчёт):
  * СОБЫТИЯ ОПЫТА / ДОБЫЧИ (6038 EventSet / 6040 EventOff) — хранит и применяет NpcServer: GameServer Recv_OperatorCommand_EventSet@0x551BF0 /
    EventOff@0x5520A0 (гейты: оператор UserIndex 0…5000, GM-флаг, токен, MD5; диапазоны) → RelayServer → ChannelManager → ВСЕ NpcServer
    канала (−1 — все каналы: поле 0, Ch2 1, Indun 3). NpcServer sub_41D8E0 / sub_41D610 пишет ./Event/Event.dat (2200 б: 13 массивов по 50
    слотов на тип: 0 — добыча и золото (шансы), 1 — опыт; карта −1 — все MapCount карт ini\\MapInfo.ini) и отвечает 6039/6041 оператору; GameServer пишет
    зеркало ./Event/Event.dat и EventLog.txt (sub_417800 / sub_417B40). Окно — MMDDHHmm БЕЗ ГОДА (start ≤ сейчас < end по GetLocalTime
    сервера): окно ПОВТОРЯЕТСЯ каждый год, пока его не выключить 6040 (поэтому панель ставит выключение заданием после конца). Через новый
    год окно не переходит (end < start — не сработает никогда). Опыт: fEvent = значение вместо 1.0 (NpcServer 0x437C48), добыча: шанс
    × (1 + личные % + значение − 1) (sub_42E3A0). MinLevel / MaxLevel сервер хранит, но в расчёте их не читает (скан абсолютных адресов
    NpcServer.exe: только загрузка, запись, 6038/6040, Event.ini, журнал). Event.dat переживает рестарт; битый Event.dat (короче 2200 б)
    NpcServer не запустит (sub_44E7D0 → return 0).
  * СЧАСТЛИВЫЕ ЧАСЫ (GameServerEvent.txt) — только опыт, только GameServer, только при старте — набор изменений области «events»
    (domains/cs_kinds/eventdata.py); здесь — показ.
  * РЕЙТИНГИ (6020) — P25: пересчёт №3 условий званий у игроков в игре + 2333 в базу (P23: рейтинговые звания 65…69 и место в топе
    славы); команда только от оператора в игре; мостом — общая точка P25_RunRecalc (DLL v84). Рейтинг чести — отдельно, camp.rank_rebuild.
  * ЕЖЕДНЕВНЫЕ — задания доски (CRT_LimitationQuest, Quest_Type = 1): GS обнуляет их в памяти в 06:00 (TimeSyncProcess@0x539A00), БД —
    наш CRT_AsdaLimitationDailyReset (задача ОС 06:02 + страховка в списке); панель: догнать (тот же вызов) или внеочередной (то же тело,
    adm.LimitationReset); одному персонажу — уже есть craft.daily_reset.
ОПЕРАЦИИ: event.set / event.off (мост v84, от персонажа служебной учётки ≤ 5000 с GM-флагом в игре — сток требует оператора; канал −1 или
  только Indun 3 — поле или Ch2 по отдельности нарушили бы паритет Ch2 = поле и restart_stack отказал бы кодом 6), rank.recalc (мост v84),
  daily.reset (SQL). Все ставятся в задания службы (adm.job). Живые события / рейтинги / сбросы самотест не включает.
★ РЕВИЗИЯ 44 (21.11.2026): задание event.off хранит ожидаемое окно (expect) и не выключает чужое; event.set снимает перекрытые задания
  выключения или отказывает; окно — только ближайшее срабатывание сервера (без года) и не длиннее года; пауза до чтения Event.dat и
  чтение по времени записи; сбой проверки после отправки — не «отказ»; сложение с счастливыми часами > ×2 — второе подтверждение;
  rank.recalc — слово rank.
Побочных эффектов при импорте нет.
"""
import base64
import datetime
import hashlib
import json
import struct
import time

from core import auth, bridge, config
from core.ops import Operation, OpRefused, register

EV_SIZE, SLOTS = 2200, 50
TYPE_NAMES = {0: "добыча и золото", 1: "опыт"}   # ★ А5.10: тип 0 («ItemDrop» стока) множит ШАНСЫ дропа И выпадения золота (сумму — нет)
CHAN_NAMES = {-1: "все каналы", 3: "только Indun"}
CHAN_PARITY = {0: "только поле (канал 1)", 1: "только Ch2 (канал 2)", 2: "канал 3 (пустой слот)"}
NPC = ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")      # = stack_layout.NPC_FOLDERS (сверка — самотест)
NPC_CHAN = {"NpcServer": 0, "Ch2_NpcServer": 1, "Indun_NpcServer": 3}
GS = ("GameServer", "Indun_GameServer", "Ch2_GameServer")    # = stack_layout.GS_FOLDERS
EV_DAT, EV_LOG, LUCKY, MAPINFO = "Event\\Event.dat", "Event\\EventLog.txt", "Event\\GameServerEvent.txt", "ini\\MapInfo.ini"
VALUE_MAX = 10.0              # сток: 0.0…10.0 (GameServer.c:129645)
STRONG_HI, STRONG_LO = 2.0, 1.0   # > ×2 или < ×1 — сильная правка: только владелец и второе подтверждение (rate_ok = rate)
CONFIRM, RATE_OK, REPLACE = "event", "rate", "replace"
OFF_DELAY_MIN = 2             # выключение заданием — через 2 мин после конца окна
VERIFY_S, VERIFY_STEP = 15.0, 2.0
VERIFY_FIRST = 3.0            # ★ ревизия 44 Н-1: пауза до первого чтения Event.dat после команды (NpcServer пишет его CreateFileA share 0)
OPERATOR_MAX_UID = 5000
BADGE_VER = 85                # ★ А5.10: P128 — значок события Event.dat всем игрокам (узлы с DLL v85+); ниже — значок видит только оператор
RANK_CONFIRM = "rank"         # ★ ревизия 44 Н-3: слово подтверждения rank.recalc (массовая операция)
OFF_NOTE = "выключение события после конца окна (event.set)"
RANK_WHAT = {0: "условия званий у игроков в игре (№3), рейтинговые звания 65…69 и место в топе славы (база, P23)",
             1: "только рейтинговые звания 65…69 (база, P23)", 2: "только место в топе по очкам славы (база, 3409)",
             3: "только условия званий у игроков в игре (№3, база не нужна)"}
DAILY_MODES = {"catchup": 0, "force": 1}
DAILY_CONFIRM = "daily"
_L = [("s_mon", 0, "B", 1), ("s_day", 100, "B", 1), ("s_hour", 200, "B", 1), ("s_min", 300, "B", 1), ("s_time", 400, "i", 4),
      ("e_mon", 800, "B", 1), ("e_day", 900, "B", 1), ("e_hour", 1000, "B", 1), ("e_min", 1100, "B", 1), ("e_time", 1200, "i", 4),
      ("value", 1600, "f", 4), ("min_level", 2000, "B", 1), ("max_level", 2100, "B", 1)]
READ = None                   # подмена чтения файлов стойки для самотеста: READ(список путей от v2) → {путь: байты | None}, время
STAT = None                   # подмена атрибутов файлов для самотеста: STAT(список путей) → {путь: (размер, время записи) | None}
CLOCK = None                 # подмена часов сервера: CLOCK() → (местное, UTC)
SQL = None                    # подмена чтения Joy1 для daily: SQL(запрос, параметры) → строки
BADGE = None                  # ★ ревизия 49 Н-1: подмена badge_state() для самотеста → ({GS: bool | None}, {GS: код})


# =====================================================================================================================
# Event.dat и окна
# =====================================================================================================================
def pack(m, d, h, mi):
    """Как сервер: минуты + 100·час + 10 000·день + 1 000 000·месяц."""
    return mi + 100 * h + 10000 * d + 1000000 * m


def decode_dat(b):
    """Event.dat → {(тип, карта): поля} или None (не 2200 б)."""
    if b is None or len(b) != EV_SIZE:
        return None
    out = {}
    for t in (0, 1):
        for m in range(SLOTS):
            i = SLOTS * t + m
            out[(t, m)] = {n: struct.unpack_from("<" + f, b, o + s * i)[0] for n, o, f, s in _L}
    return out


def entry_empty(e):
    return not any(e[k] for k in ("s_mon", "e_mon", "s_time", "e_time")) and e["value"] == 0.0


def phase(e, now):
    """Положение окна относительно «сейчас» (без года, как у сервера): empty | active | ahead | past | never (конец не позже начала)."""
    if entry_empty(e):
        return "empty"
    if e["e_time"] <= e["s_time"]:
        return "never"
    cur = pack(now.month, now.day, now.hour, now.minute)
    if e["s_time"] <= cur < e["e_time"]:
        return "active"
    return "ahead" if cur < e["s_time"] else "past"


def win_text(e):
    return "%02d.%02d %02d:%02d → %02d.%02d %02d:%02d ×%s" % (e["s_day"], e["s_mon"], e["s_hour"], e["s_min"], e["e_day"], e["e_mon"],
                                                              e["e_hour"], e["e_min"], _fv(e["value"]))


def _fv(v):
    s = ("%.2f" % v).rstrip("0")
    return s + "0" if s.endswith(".") else s


def same_entry(e, want):
    return all(e[k] == want[k] for k in want if k != "value") and abs(e["value"] - want["value"]) < 1e-6


def want_entry(w):
    """Ожидаемая запись Event.dat после 6038 (как sub_41D8E0)."""
    return {"s_mon": w["s"].month, "s_day": w["s"].day, "s_hour": w["s"].hour, "s_min": w["s"].minute,
            "s_time": pack(w["s"].month, w["s"].day, w["s"].hour, w["s"].minute),
            "e_mon": w["e"].month, "e_day": w["e"].day, "e_hour": w["e"].hour, "e_min": w["e"].minute,
            "e_time": pack(w["e"].month, w["e"].day, w["e"].hour, w["e"].minute),
            "value": struct.unpack("<f", struct.pack("<f", w["v100"] / 100.0))[0], "min_level": w["minlv"], "max_level": w["maxlv"]}


ZERO = {n: (0.0 if f == "f" else 0) for n, _o, f, _s in _L}


# =====================================================================================================================
# Чтение стойки (одна команда на сервер)
# =====================================================================================================================
def clock():
    """Часы сервера (GetLocalTime у NpcServer = местное время машины стойки) → (местное, UTC). SQL на той же машине."""
    if CLOCK:
        return CLOCK()
    from core import db
    try:
        with db.GameReader("joy1") as r:
            x = r.rows("SELECT GETDATE() AS loc, GETUTCDATE() AS utc")[0]
        return x["loc"].replace(microsecond=0), x["utc"].replace(microsecond=0)
    except db.DbError as ex:
        raise OpRefused("часы сервера не прочитаны (%s) — окно события не с чем сверить" % ex)


def read_files(rels):
    """Файлы стойки (пути от v2) → {путь: байты | None}. Одна команда PowerShell (на сервере — диск)."""
    if READ:
        return READ(rels)
    from core import hostshell
    cfg = config.get()
    root = config.STACK_ROOT
    if cfg.on_server:
        out = {}
        for r in rels:
            try:
                with open(root + "\\" + r, "rb") as f:
                    out[r] = f.read()
            except OSError:
                out[r] = None
        return out
    lst = ",".join("'%s'" % (root + "\\" + r).replace("'", "''") for r in rels)
    script = ("foreach ($p in @(%s)) { try { $fs = [IO.File]::Open($p, 'Open', 'Read', 'ReadWrite'); try { $ms = New-Object IO.MemoryStream; "
              "$fs.CopyTo($ms); 'OK|' + $p + '|' + [Convert]::ToBase64String($ms.ToArray()) } finally { $fs.Close() } } "
              "catch { 'ERR|' + $p + '|' } }" % lst)
    try:
        text = hostshell.powershell(script, 90)
    except hostshell.HostError as ex:
        raise OpRefused("файлы событий стойки не прочитаны: %s" % ex)
    got = {}
    for ln in text.splitlines():
        parts = ln.strip().split("|", 2)
        if len(parts) == 3 and parts[1].lower().startswith(root.lower() + "\\"):
            rel = parts[1][len(root) + 1:]
            got[rel] = base64.b64decode(parts[2]) if parts[0] == "OK" else None
    return {r: got.get(r) for r in rels}


def stat_files(rels):
    """★ ревизия 44 Н-1: размер и время записи файлов стойки БЕЗ открытия данных → {путь: (размер, время) | None}; None — не узнать.
    NpcServer открывает Event.dat на запись CreateFileA(GENERIC_WRITE, share 0) — любой чужой дескриптор ДАННЫХ (с любым share) сорвёт
    его запись, а запрос атрибутов (os.stat / FileInfo — только FILE_READ_ATTRIBUTES или GetFileAttributesEx) общий доступ не проверяет.
    Опрос ждёт по времени записи и открывает данные только когда файл изменился."""
    if STAT:
        return STAT(rels)
    if READ:
        return None                                  # самотест с подменой чтения без подмены атрибутов — сверка по данным
    import os
    from core import hostshell
    cfg = config.get()
    root = config.STACK_ROOT
    if cfg.on_server:
        out = {}
        for r in rels:
            try:
                s = os.stat(root + "\\" + r)
                out[r] = (s.st_size, s.st_mtime_ns)
            except OSError:
                out[r] = None
        return out
    lst = ",".join("'%s'" % (root + "\\" + r).replace("'", "''") for r in rels)
    script = ("foreach ($p in @(%s)) { $i = New-Object IO.FileInfo($p); if ($i.Exists) { 'OK|' + $p + '|' + $i.Length + '|' + "
              "$i.LastWriteTimeUtc.Ticks } else { 'ERR|' + $p + '|' } }" % lst)
    try:
        text = hostshell.powershell(script, 60)
    except hostshell.HostError:
        return None
    got = {}
    for ln in text.splitlines():
        parts = ln.strip().split("|")
        if len(parts) >= 2 and parts[1].lower().startswith(root.lower() + "\\"):
            rel = parts[1][len(root) + 1:]
            got[rel] = (int(parts[2]), int(parts[3])) if parts[0] == "OK" and len(parts) == 4 else None
    return {r: got.get(r) for r in rels}


def map_names(ini_bytes):
    """ini\\MapInfo.ini NpcServer → (MapCount, [имя карты по номеру])."""
    if ini_bytes is None:
        return None, []
    from core import hostshell
    cnt, names = None, {}
    for ln in hostshell.decode_text(ini_bytes).splitlines():
        k, sep, v = ln.partition("=")
        k = k.strip().lower()
        if not sep:
            continue
        if k == "mapcount":
            try:
                cnt = int(v.strip())
            except ValueError:
                cnt = None
        elif k.startswith("servername_") and k[11:].isdigit():
            names[int(k[11:])] = v.strip().strip('"').strip()
    return cnt, [names.get(i, "карта %d" % i) for i in range(cnt or 0)]


def lucky_rows(raw):
    """GameServerEvent.txt → (строк по счётчику, [(год, мес, день, час_от, час_до, значение)], ошибка | None) — как читает сервер."""
    if raw is None:
        return None, [], "не прочитан"
    from domains.cs_kinds import eventdata
    from domains import shopdata as E
    try:
        n, rows = eventdata.parse_rows(E._split(raw)[0])
        return n, [r[1:] for r in rows], None
    except OpRefused as ex:
        return None, [], str(ex)


def lucky_now(rows, now):
    """Первая строка, которая сработала бы сейчас (как GetExpUpDownValue), или None."""
    for r in rows:
        if (r[0], r[1], r[2]) == (now.year, now.month, now.day) and r[3] <= now.hour < r[4]:
            return r
    return None


BADGE_TEXT = {"all": "всем (P128)", "ver": "только оператору (нужна DLL v%d)" % BADGE_VER, "off": "только оператору (P128 выключен в ini)",
              "failed": "только оператору (P128 не встал при старте — журнал патчей)", "absent": "только оператору (секции P128 в ini нет)",
              "nopulse": "не прочитано (нет пульса узла)", "unread": "не прочитано (журнал патчей)"}


def badge_state():
    """★ ревизия 49 Н-1: значок события у игроков по ФАКТУ установки P128 на каждом GS → ({GS: True/False/None}, {GS: код BADGE_TEXT}).
    Узел без свежего пульса — «не прочитано» (None), DLL ниже v85 — «нужна DLL», иначе режим секции [P128_EventBadgeAll] по журналу
    патчей последнего запуска (domains/patchcfg: active — всем; off / pending_on / self_off — выключен; failed; absent; unread / nolog)."""
    if BADGE:
        return BADGE()
    nds = {x["node"]: x for x in bridge.nodes()}
    modes = {}
    try:
        from domains import patchcfg
        ap = next((d for d in patchcfg.state(dll_only="AsdaPatch")["dlls"] if d["dll"] == "AsdaPatch"), None)
        sec = next((s for s in (ap or {}).get("sections", []) if s["name"] == "P128_EventBadgeAll"), None)
        modes = (sec or {}).get("modes") or {}
    except Exception:
        modes = {}
    on, why = {}, {}
    for g in GS:
        n = nds.get(g)
        if not n or not n.get("fresh"):
            on[g], why[g] = None, "nopulse"
        elif int(n.get("ver") or 0) < BADGE_VER:
            on[g], why[g] = False, "ver"
        else:
            m = modes.get(g)
            code = {"active": "all", "journal": "all", "off": "off", "pending_on": "off", "self_off": "off", "pending_off": "all",
                    "failed": "failed", "absent": "absent"}.get(m, "unread")
            on[g], why[g] = (True if code == "all" else None if code == "unread" else False), code
    return on, why


def state(force=False):
    """Состояние событий стойки (только чтение): Event.dat всех NpcServer и зеркал GS, GameServerEvent.txt ×3, карты, часы сервера,
    предупреждения (паритет, повтор окон через год, конец счастливых часов, битые файлы). «Не прочитано» ≠ «нет»."""
    loc, utc = clock()
    rels = [n + "\\" + EV_DAT for n in NPC] + [g + "\\" + EV_DAT for g in GS] + [g + "\\" + LUCKY for g in GS] + ["NpcServer\\" + MAPINFO,
                                                                                                                  "Indun_NpcServer\\" + MAPINFO]
    files = read_files(rels)
    cnt, names = map_names(files.get("NpcServer\\" + MAPINFO))
    cnt_i, names_i = map_names(files.get("Indun_NpcServer\\" + MAPINFO))
    warn, npc = [], {}
    for n in NPC:
        b = files.get(n + "\\" + EV_DAT)
        dec = decode_dat(b)
        npc[n] = {"read": b is not None, "size": len(b) if b is not None else None,
                  "md5": hashlib.md5(b).hexdigest() if b is not None else None, "ok": dec is not None, "_dec": dec}
        if b is None:
            warn.append("%s\\%s не прочитан — события этого канала неизвестны" % (n, EV_DAT))
        elif dec is None:
            warn.append("%s\\%s — %d б вместо %d: NpcServer с таким файлом не запустится (sub_44E7D0)" % (n, EV_DAT, len(b), EV_SIZE))
    md5s = {npc[n]["md5"] for n in NPC if npc[n]["md5"]}
    if npc["NpcServer"]["md5"] and npc["Ch2_NpcServer"]["md5"] and npc["NpcServer"]["md5"] != npc["Ch2_NpcServer"]["md5"]:
        warn.append("Event.dat NpcServer и Ch2_NpcServer разные — паритет Ch2 нарушен: restart_stack откажет (код 6), пока их не выровнять "
                    "событием на все каналы")
    windows = []
    base = npc["NpcServer"]["_dec"] or npc["Indun_NpcServer"]["_dec"] or npc["Ch2_NpcServer"]["_dec"]
    for t in (0, 1):
        groups = {}
        for m in range(cnt or SLOTS):
            per = {}
            for n in NPC:
                d = npc[n]["_dec"]
                if d is not None:
                    e = d[(t, m)]
                    per[n] = None if entry_empty(e) else json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in e.items()},
                                                                     sort_keys=True)
            key = json.dumps(per, sort_keys=True)
            groups.setdefault(key, []).append(m)
        for key, maps in groups.items():
            per = json.loads(key)
            if not any(per.values()):
                continue
            sample = next(json.loads(v) for v in per.values() if v)
            ph = phase(sample, loc)
            item = {"type": t, "type_name": TYPE_NAMES[t], "maps": maps, "map_names": [names[m] if m < len(names) else "карта %d" % m for m in maps],
                    "copies": sorted(k for k, v in per.items() if v), "window": win_text(sample), "phase": ph, "value": sample["value"],
                    "min_level": sample["min_level"], "max_level": sample["max_level"], "entry": sample}
            windows.append(item)
            if ph == "past":
                warn.append("окно %s (%s, карт %d) прошло, но не выключено — сервер включит его снова %s следующего года (6040 / event.off)"
                            % (item["window"], item["type_name"], len(maps), "%02d.%02d" % (sample["s_day"], sample["s_mon"])))
            if ph == "never":
                warn.append("окно %s (%s) — конец не позже начала (через новый год сервер окно не переносит): не сработает никогда"
                            % (item["window"], item["type_name"]))
    lucky, lmd5 = {}, set()
    for g in GS:
        b = files.get(g + "\\" + LUCKY)
        n, rows, err = lucky_rows(b)
        mirror = files.get(g + "\\" + EV_DAT)
        lucky[g] = {"read": b is not None, "md5": hashlib.md5(b).hexdigest() if b is not None else None, "count": n, "rows": len(rows),
                    "error": err, "first": "%04d-%02d-%02d" % rows[0][:3] if rows else None,
                    "last": "%04d-%02d-%02d" % max(r[:3] for r in rows) if rows else None,
                    "now": list(lucky_now(rows, loc) or []) or None,
                    "upcoming": [list(r) for r in sorted(rows) if (r[0], r[1], r[2]) >= (loc.year, loc.month, loc.day)][:12],
                    "mirror_size": len(mirror) if mirror is not None else None}
        if b is not None:
            lmd5.add(lucky[g]["md5"])
        if err:
            warn.append("%s\\%s: %s" % (g, LUCKY, err))
        if mirror is not None and len(mirror) != EV_SIZE:
            warn.append("%s\\%s — %d б: GameServer при старте выйдет из загрузчика ДО GameServerEvent.txt — счастливые часы не загрузятся"
                        % (g, EV_DAT, len(mirror)))
    if len(lmd5) > 1:
        warn.append("GameServerEvent.txt у GameServer разные (%s) — у одной базы копий быть не должно" % ", ".join(sorted(x[:8] for x in lmd5)))
    last = lucky["GameServer"]["last"]
    if last and last < loc.strftime("%Y-%m-%d"):
        warn.append("счастливые часы кончились %s — после этой даты их нет (добавить — набор изменений «Счастливые часы»)" % last)
    elif last:
        warn.append("счастливые часы расписаны до %s" % last)
    for n in NPC:
        npc[n].pop("_dec", None)
    # ★ А5.10: значок события у игроков — P128 (DLL v85+) шлёт 6039/6041 всем в мире; у v84 и ниже — только оператору (сток)
    badge, bwhy = badge_state()
    return {"badge_all": badge, "badge_why": bwhy, "badge_text": {g: BADGE_TEXT.get(c, c) for g, c in bwhy.items()}, "badge_ver": BADGE_VER,"server_now": loc.strftime("%Y-%m-%d %H:%M:%S"), "server_utc": utc.strftime("%Y-%m-%d %H:%M:%S"), "npc": npc,
            "npc_same": len(md5s) == 1 and all(npc[n]["md5"] for n in NPC), "windows": windows, "lucky": lucky, "map_count": cnt,
            "maps": names, "indun_maps_same": names == names_i and cnt == cnt_i, "warnings": warn, "event_ver": bridge.EVENT_VER,
            "nodes": [{"node": x["node"], "mode": x["mode"], "ver": x.get("ver"), "fresh": x["fresh"]} for x in bridge.nodes()]}


# =====================================================================================================================
# Оператор (сток требует его: 6038 / 6040 / 6020 — только служебная учётка ≤ 5000 с GM-флагом, в игре)
# =====================================================================================================================
def _gm_uids(uids):
    from core import db
    if not uids:
        return set()
    try:
        with db.GameReader("joy1") as r:
            rows = r.rows("SELECT DISTINCT Userindex FROM dbo.CharGmInfo WHERE Userindex IN (%s)" % ",".join(str(int(u)) for u in uids))
    except db.DbError as ex:
        raise OpRefused("GM-флаг служебных учёток не прочитан: %s" % ex)
    return {int(x["Userindex"]) for x in rows}


def operator(ctx, p, what):
    """Персонаж-оператор для команды моста v84: заданный (uid/idx) или первый подходящий в игре → строка присутствия."""
    from domains import live
    owners = live.owner_accounts()
    fresh = {n["node"]: n for n in bridge.nodes() if n["fresh"] and int(n["mode"]) == 1}
    if not fresh:
        raise OpRefused("%s: нет ни одного GameServer с мостом в режиме исполнения (Mode=1) — сервер команду не получит" % what)
    rows = [r for r in bridge.presence() if r["node"] in fresh and int(r.get("ver") or 0) >= bridge.EVENT_VER
            and 0 < int(r["Userindex"]) <= OPERATOR_MAX_UID]
    want_uid, want_idx = p.get("uid"), p.get("idx")
    if want_uid not in (None, ""):
        try:
            u, i = int(want_uid), int(want_idx)
        except (TypeError, ValueError):
            raise OpRefused("неверный персонаж-оператор")
        if not 0 < u <= OPERATOR_MAX_UID:
            raise OpRefused("%s: оператор — только служебная учётка (номер 1…5000) — так проверяет сток" % what)
        if u in owners and ctx.role != "owner":
            raise OpRefused("от персонажей служебных учёток владельца (%s) это делает только владелец" % ", ".join(map(str, sorted(owners))))
        rows = [r for r in rows if int(r["Userindex"]) == u and int(r["Charidx"]) == i]
        if not rows:
            raise OpRefused("%s: персонажа %d/%d нет в игре на узле с мостом v%d+ в режиме исполнения" % (what, u, i, bridge.EVENT_VER))
    else:
        rows = [r for r in rows if int(r["Userindex"]) not in owners or ctx.role == "owner"]
        if not rows:
            vers = sorted({int(n.get("ver") or 0) for n in fresh.values()})
            raise OpRefused("%s: в игре нет персонажа служебной учётки 1…5000 на узле с мостом v%d+ (узлы: v%s) — сток выполняет команду только "
                            "от оператора в игре" % (what, bridge.EVENT_VER, "/".join(map(str, vers)) or "?"))
    gm = _gm_uids({int(r["Userindex"]) for r in rows})
    rows = [r for r in rows if int(r["Userindex"]) in gm]
    if not rows:
        raise OpRefused("%s: у служебных учёток в игре нет GM-флага (CharGmInfo) — сток команду не выполнит" % what)
    return rows[0]


# =====================================================================================================================
# Параметры события
# =====================================================================================================================
def _dt(v, k):
    s = str(v or "").strip().replace("T", " ")
    try:
        return datetime.datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        raise OpRefused("поле «%s»: время сервера ГГГГ-ММ-ДД чч:мм" % k)


def _int(p, k, lo, hi, d=None):
    v = p.get(k, d)
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise OpRefused("поле «%s»: нужно целое число" % k)
    if not lo <= v <= hi:
        raise OpRefused("поле «%s»: от %d до %d" % (k, lo, hi))
    return v


def _scope(p):
    t = _int(p, "type", 0, 1)
    chan = _int(p, "chan", -1, 3, -1)
    if chan in CHAN_PARITY:
        raise OpRefused("канал %s: %s — Event.dat разошёлся бы с парой (паритет Ch2 = поле), restart_stack откажет кодом 6 — можно: все каналы (−1) "
                        "или только Indun (3)" % (chan, CHAN_PARITY[chan]))
    m = _int(p, "map", -1, SLOTS - 1, -1)
    return t, chan, m


def _copies(chan):
    return [n for n in NPC if chan == -1 or NPC_CHAN[n] == chan]


def window(p):
    """Параметры 6038 → dict (тип, канал, карта, начало, конец, v100, уровни) с проверками стока и панели."""
    t, chan, m = _scope(p)
    s, e = _dt(p.get("start"), "start"), _dt(p.get("end"), "end")
    if e <= s:
        raise OpRefused("конец окна не позже начала")
    if (e.month, e.day, e.hour, e.minute) <= (s.month, s.day, s.hour, s.minute):
        raise OpRefused("окно переходит через новый год — сервер сравнивает без года (MMDDчмм), такое окно не сработает никогда — разбейте "
                        "на два: до 31.12 и с 01.01")
    if s.year != e.year:                             # ★ ревизия 44 С-2: годы разные, а MMDD конца позже — окно длиннее года
        raise OpRefused("окно %s → %s длиннее года — сервер хранит окно без года (MMDDчмм) и включал бы его каждый год с %02d.%02d по %02d.%02d — "
                        "задайте окно в пределах одного года" % (s.strftime("%Y-%m-%d %H:%M"), e.strftime("%Y-%m-%d %H:%M"), s.day, s.month,
                                                                e.day, e.month))
    raw = str(p.get("value", "")).strip().replace(",", ".")
    try:
        val = float(raw)
    except ValueError:
        raise OpRefused("поле «value»: множитель числом (2.0 — ×2)")
    if not 0.0 <= val <= VALUE_MAX or abs(val * 100 - round(val * 100)) > 1e-6:
        raise OpRefused("поле «value»: от 0.0 до %s, до двух знаков" % _fv(VALUE_MAX))
    minlv, maxlv = _int(p, "minlv", 0, 255, 1), _int(p, "maxlv", 0, 255, 100)
    return {"type": t, "chan": chan, "map": m, "s": s, "e": e, "v100": int(round(val * 100)), "value": val, "minlv": minlv, "maxlv": maxlv}


def strong(val):
    return val > STRONG_HI or val < STRONG_LO


def next_year(w, now):
    """★ ревизия 44 С-2: год ближайшего срабатывания окна у сервера. Сервер сравнивает MMDDчмм без года (start ≤ сейчас < end по часам
    стойки): пока конец окна в этом году не наступил — окно идёт или впереди В ЭТОМ году, иначе — в следующем."""
    cur = pack(now.month, now.day, now.hour, now.minute)
    return now.year if cur < pack(w["e"].month, w["e"].day, w["e"].hour, w["e"].minute) else now.year + 1


def lucky_over(rows, s, e):
    """★ ревизия 44: строки счастливых часов, часы которых пересекают окно [s, e) → (наибольшее значение, «ГГГГ-ММ-ДД чч–чч») или None."""
    best = None
    for y, m, d, hf, ht, v in rows:
        try:
            day = datetime.datetime(y, m, d)
        except ValueError:
            continue                                 # несуществующая дата у сервера не сработает никогда
        a, b = day + datetime.timedelta(hours=hf), day + datetime.timedelta(hours=ht)
        if a < e and s < b and (best is None or v > best[0]):
            best = (v, "%04d-%02d-%02d %02d–%02d" % (y, m, d, hf, ht))
    return best


def args_set(w):
    return ("type=%d;chan=%d;map=%d;smon=%d;sday=%d;shour=%d;smin=%d;emon=%d;eday=%d;ehour=%d;emin=%d;v100=%d;lv=%d" % (
        w["type"], w["chan"], w["map"], w["s"].month, w["s"].day, w["s"].hour, w["s"].minute, w["e"].month, w["e"].day, w["e"].hour,
        w["e"].minute, w["v100"], w["minlv"] + 256 * w["maxlv"]))


def _maps_of(m, st):
    return list(range(st["map_count"] or 0)) if m == -1 else [m]


def _map_label(m, st):
    if m == -1:
        return "все карты"
    return "%d %s" % (m, st["maps"][m] if m < len(st["maps"]) else "?")


def _pending_overlaps(w, job_id=None):
    """★ пересечение с уже поставленными заданиями event.set того же типа (общие карты и каналы, окна пересекаются)."""
    from core import jobs
    out = []
    try:
        lst = jobs.list_jobs(200, active=True)
    except Exception as ex:
        raise OpRefused("задания планировщика не прочитаны (%s) — пересечение с поставленными событиями не проверено" % str(ex)[:200])
    for j in lst:
        if j.get("op") != "event.set" or j.get("status") != "pending" or (job_id and int(j["id"]) == int(job_id)):
            continue
        try:
            o = window(j.get("params") or {})
        except OpRefused:
            continue
        if o["type"] != w["type"]:
            continue
        if not (o["chan"] == -1 or w["chan"] == -1 or o["chan"] == w["chan"]):
            continue
        if not (o["map"] == -1 or w["map"] == -1 or o["map"] == w["map"]):
            continue
        if o["s"] < w["e"] and w["s"] < o["e"]:
            out.append("задание №%s (%s → %s)" % (j["id"], o["s"].strftime("%d.%m %H:%M"), o["e"].strftime("%d.%m %H:%M")))
    return out


def _wait_dat(copies, maps, t, want, timeout=VERIFY_S):
    """Ждать, пока Event.dat нужных NpcServer покажет want у всех карт (по коду возврата чтения и сроку) → (сошлось [копии], нет [копии])."""
    # ★ ревизия 44 Н-1: пауза до первого чтения (NpcServer пишет Event.dat сразу по приходу команды, CreateFileA share 0 — чужой открытый
    #   дескриптор сорвал бы запись, событие осталось бы только в памяти до рестарта); дальше данные открываются, только когда время записи
    #   файла изменилось (атрибуты общий доступ не проверяют), а не каждый шаг.
    time.sleep(VERIFY_FIRST)
    end = time.time() + timeout
    good, bad, seen, first = [], list(copies), {}, True
    while True:
        st = stat_files([n + "\\" + EV_DAT for n in bad])
        todo = [n for n in bad if first or st is None or st.get(n + "\\" + EV_DAT) is None or st[n + "\\" + EV_DAT] != seen.get(n)]
        if todo:
            files = read_files([n + "\\" + EV_DAT for n in todo])
            for n in todo:
                seen[n] = st.get(n + "\\" + EV_DAT) if st else None
                d = decode_dat(files.get(n + "\\" + EV_DAT))
                if d is not None and all(same_entry(d[(t, m)], want) for m in maps):
                    good.append(n)
                    bad.remove(n)
        first = False
        if not bad or time.time() >= end:
            return [n for n in copies if n in good], bad
        time.sleep(VERIFY_STEP)


def _verify(copies, maps, t, want):
    """★ ревизия 44 Н-2: проверка ПОСЛЕ отправленной команды не превращает выполненное в отказ → (сошлось, нет, ошибка чтения | None)."""
    try:
        good, bad = _wait_dat(copies, maps, t, want)
        return good, bad, None
    except Exception as ex:                         # OpRefused (SSH / диск) и любой сбой чтения — команда уже ушла
        return [], list(copies), str(ex)[:300]


def _off_jobs(w, copies, maps, files, utc_off, map_count, job_id=None):
    """★ ревизия 44 С-1: ждущие задания event.off того же типа, задевающие эти копии и карты → (снять после записи [№], отказ-текст | None).
    Задание с ожидаемым окном (expect, ставит event.set): его окно ещё записано и новое событие перекрывает его целиком — снять (новое
    ставит своё); окно уже не записано — снять (оно отказало бы «выключать нечего»); перекрыто частично — отказ (прежнее окно осталось бы
    на остальных картах). Задание без ожидаемого окна (поставлено вручную) до конца нового окна — отказ: оно выключило бы и это событие."""
    from core import jobs
    try:
        lst = jobs.list_jobs(200, active=True)
    except Exception as ex:
        raise OpRefused("задания планировщика не прочитаны (%s) — задания выключения на этих картах не проверены" % str(ex)[:200])
    drop, bad = [], []
    mine_c, mine_m = set(copies), set(maps)
    for j in lst:
        if j.get("op") != "event.off" or j.get("status") != "pending" or (job_id and int(j["id"]) == int(job_id)):
            continue
        q = j.get("params") or {}
        try:
            t, chan, m = _scope(q)
        except OpRefused:
            continue
        oc, om = set(_copies(chan)), set(range(map_count or 0) if m == -1 else [m])
        if t != w["type"] or not (oc & mine_c) or not (om & mine_m):
            continue
        exp = q.get("expect")
        if not isinstance(exp, dict):
            at = j.get("run_at")
            loc_at = at - utc_off if isinstance(at, datetime.datetime) else None
            if loc_at is None or loc_at < w["e"]:
                bad.append("задание выключения №%s (%s) поставлено без ожидаемого окна и выключит и это событие" % (
                    j["id"], loc_at.strftime("%d.%m %H:%M") if loc_at else "?"))
            continue
        live = False
        for n in oc:
            d = decode_dat(files.get(n + "\\" + EV_DAT)) if n + "\\" + EV_DAT in files else None
            if d is not None and any(same_entry(d[(t, mm)], exp) for mm in om if mm < SLOTS):
                live = True
        if not live or (oc <= mine_c and om <= mine_m):
            drop.append(int(j["id"]))
        else:
            bad.append("задание выключения №%s (окно %s) задевает больше карт или каналов, чем это событие — после замены оно не выключит "
                       "прежнее окно на остальных" % (j["id"], win_text(exp)))
    return drop, ((" и ".join(bad)) + " — сначала выключите прежнее окно (event.off) или отмените задание, либо задайте те же карты и каналы"
                  if bad else None)


def _two(ctx, p):
    if ctx.via == "web":
        auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())


# =====================================================================================================================
# Операции
# =====================================================================================================================
@register
class EventSet(Operation):
    name, title, perm, reversible = "event.set", "События: включить событие опыта / добычи и золота (6038, мост)", "server.events", False
    schedule_runner, two_factor, confirm_word = "service", True, CONFIRM

    def target(self, p):
        return "event:%s:%s:%s" % (p.get("type"), p.get("chan", -1), p.get("map", -1))

    def schedule_check(self, ctx, p):
        """Параметры и подтверждения (то же при постановке в задание, без моста и без чтения стойки)."""
        w = window(p)
        if str(p.get("confirm") or "") != CONFIRM:
            raise OpRefused("нужно подтверждение: событие меняет рейт всем игрокам (ключ confirm = event)")
        if strong(w["value"]):
            if ctx.role != "owner":
                raise OpRefused("рейт ×%s — сильная правка (больше ×2 или меньше ×1): только владелец" % _fv(w["value"]))
            if str(p.get("rate_ok") or "") != RATE_OK:
                raise OpRefused("рейт ×%s — сильная правка (больше ×2 или меньше ×1): нужно второе подтверждение (ключ rate_ok = rate)"
                                % _fv(w["value"]))
        busy = _pending_overlaps(w, p.get("job_id"))
        if busy:
            raise OpRefused("окно пересекается с уже поставленным событием того же типа: %s — отмените его или сдвиньте окно" % ", ".join(busy))
        return w

    def preview(self, ctx, p):
        w = self.schedule_check(ctx, p)
        loc, utc = clock()                                  # перепроверка в момент предпросмотра / запуска задания
        if w["e"] <= loc:
            raise OpRefused("конец окна %s уже прошёл (сейчас на сервере %s)" % (w["e"].strftime("%Y-%m-%d %H:%M"), loc.strftime("%Y-%m-%d %H:%M")))
        ny = next_year(w, loc)
        if w["s"].year != ny:                               # ★ ревизия 44 С-2: ближайшее срабатывание сервера (без года) — не эти даты
            raise OpRefused("окно %s → %s: сервер сравнивает даты без года и включит его уже %02d.%02d.%d (сейчас на сервере %s) — задайте "
                            "ближайшие даты или поставьте событие заданием ближе к дате" % (
                                w["s"].strftime("%Y-%m-%d %H:%M"), w["e"].strftime("%Y-%m-%d %H:%M"), w["s"].day, w["s"].month, ny,
                                loc.strftime("%Y-%m-%d %H:%M")))
        st = state()
        copies = _copies(w["chan"])
        miss = [n for n in copies if not st["npc"][n]["ok"]]
        if miss:
            raise OpRefused("Event.dat не прочитан или битый: %s — было / станет неизвестно, вслепую не делается" % ", ".join(miss))
        if w["map"] >= 0 and (st["map_count"] is None or w["map"] >= st["map_count"]):
            raise OpRefused("карты %d нет в ini\\MapInfo.ini NpcServer (карт %s) — NpcServer ответит отказом" % (w["map"], st["map_count"]))
        if w["chan"] == -1 and not st["indun_maps_same"] and w["map"] >= 0:
            raise OpRefused("у Indun_NpcServer другой список карт ini\\MapInfo.ini — номер карты %d там означает другую карту — выберите все карты "
                            "или только Indun" % w["map"])
        op = operator(ctx, p, "событие")
        want = want_entry(w)
        maps = _maps_of(w["map"], st)
        files = read_files([n + "\\" + EV_DAT for n in NPC] + ["GameServer\\" + LUCKY])
        if any(decode_dat(files.get(n + "\\" + EV_DAT)) is None for n in copies):
            raise OpRefused("Event.dat не прочитан или битый при повторном чтении — было / станет неизвестно, вслепую не делается")
        before, replace = [], []
        for n in copies:
            d = decode_dat(files.get(n + "\\" + EV_DAT))
            for m in maps:
                e = d[(w["type"], m)]
                if entry_empty(e) or same_entry(e, want):
                    continue
                ph = phase(e, loc)
                before.append((n, m, win_text(e), ph))
                if ph in ("active", "ahead"):
                    replace.append(win_text(e))
        if replace and str(p.get("replace") or "") != REPLACE:
            raise OpRefused("у этих карт уже есть идущее или будущее окно «%s» (%s), событие его заменит (у карты одно окно на тип) — заменить — "
                            "ключ replace = replace" % (TYPE_NAMES[w["type"]], ", ".join(sorted(set(replace))[:4])))
        utc_off = utc - loc
        drop, why = _off_jobs(w, copies, maps, files, utc_off, st["map_count"], p.get("job_id"))
        if why:
            raise OpRefused(why)
        warn = []
        if w["type"] == 1:                                  # ★ ревизия 44: событие опыта + счастливые часы складываются (GetExpUpDownValue)
            n_l, rows_l, err_l = lucky_rows(files.get("GameServer\\" + LUCKY))
            over = None if err_l else lucky_over(rows_l, w["s"], w["e"])
            total = w["value"] + over[0] if over else None
            if err_l:                                       # «не прочитано» ≠ «нет»: как сильная правка
                if ctx.role != "owner":
                    raise OpRefused("счастливые часы GameServerEvent.txt не прочитаны или не разобраны (%s) — сложение с ними не проверено: "
                                    "только владелец" % err_l)
                if str(p.get("rate_ok") or "") != RATE_OK:
                    raise OpRefused("счастливые часы GameServerEvent.txt не прочитаны или не разобраны (%s) — сложение с ними не проверено: "
                                    "нужно второе подтверждение (ключ rate_ok = rate)" % err_l)
                warn.append("счастливые часы GameServerEvent.txt не прочитаны или не разобраны (%s) — сложение с ними не проверено: второе "
                            "подтверждение дано" % err_l)
            elif total is not None and total > STRONG_HI and not strong(w["value"]):
                lw = (_fv(over[0]), over[1], _fv(total))
                if ctx.role != "owner":
                    raise OpRefused("вместе со счастливыми часами (+%s, %s) рейт опыта ×%s — больше ×2: только владелец" % lw)
                if str(p.get("rate_ok") or "") != RATE_OK:
                    raise OpRefused("вместе со счастливыми часами (+%s, %s) рейт опыта ×%s — больше ×2: нужно второе подтверждение (ключ rate_ok = rate)"
                                    % lw)
                warn.append("вместе со счастливыми часами (+%s, %s) рейт опыта ×%s — больше ×2: второе подтверждение дано" % lw)
            elif over:
                warn.append("вместе со счастливыми часами (+%s, %s) рейт опыта ×%s" % (_fv(over[0]), over[1], _fv(total)))
        if drop:
            warn.append("после записи будут сняты прежние задания выключения этих карт: %s (их окно заменяется — новое событие ставит своё)"
                        % ", ".join("№%d" % x for x in drop))
        if w["type"] == 1:
            warn.append("опыт: NpcServer подставляет ×%s вместо 1.0; счастливые часы GameServerEvent.txt прибавляются сверху; P91 поднимает "
                        "потолок опыта за моба вместе с рейтом" % _fv(w["value"]))
        else:
            # ★ А5.10: sub_42E3A0 в sub_437A30 — шансы строк основного (+30982) и группового (+31182) дропа, гейтов рулетки (+30976) и
            #   мирового дропа (+31206) и шанс золота (+30981); сумма золота (+30977/+30979) — без множителя
            warn.append("добыча и золото: NpcServer прибавляет %s к множителю ШАНСА строк дропа (основной, групповой, мировой) и шанса "
                        "выпадения золота (вместе с личными бонусами); сумму золота в кучке не меняет" % _fv(w["value"] - 1.0))
        if w["value"] < 1.0:
            warn.append("значение меньше 1.0 — рейт УМЕНЬШАЕТСЯ")
        warn.append("окно без года: сервер включит его снова в те же даты следующего года, пока не выключить (6040)")
        auto = str(p.get("auto_off", "1")) not in ("0", "", "false", "False")
        if auto:
            if w["e"] + datetime.timedelta(minutes=OFF_DELAY_MIN) > loc + datetime.timedelta(days=31):
                warn.append("выключение заданием не ставится: конец окна дальше 31 дня — выключите вручную (event.off) до %s следующего года"
                            % ("%02d.%02d" % (w["s"].day, w["s"].month)))
                auto = False
            else:
                warn.append("после конца окна будет поставлено задание event.off (через %d мин) — оно выполнится только от оператора в игре" % OFF_DELAY_MIN)
                warn.append("задание выключения выключит только это окно: если к его сроку запись Event.dat другая (новое событие) — откажет")
        warn.append("границы уровней (%d…%d) сервер хранит, но в расчёте не применяет (реверс NpcServer)" % (w["minlv"], w["maxlv"]))
        warn.append("от персонажа %s (учётка %s, %s); сток ответит ему в чат «[Success EVENT SET] …»" % (op["charname"], op["Userindex"], op["node"]))
        for n, m, txt, ph in before[:6]:
            if ph == "past":
                warn.append("%s карта %d: прошедшее окно %s заменяется (иначе повторилось бы через год)" % (n, m, txt))
        if not st["npc_same"]:
            warn.append("Event.dat копий NpcServer сейчас разные — событие на все каналы их выровняет только для этих карт и типа")
        text = "событие: %s ×%s, %s → %s (время сервера), %s, %s; NpcServer: %s" % (
            TYPE_NAMES[w["type"]], _fv(w["value"]), w["s"].strftime("%Y-%m-%d %H:%M"), w["e"].strftime("%Y-%m-%d %H:%M"),
            CHAN_NAMES[w["chan"]], _map_label(w["map"], st), ", ".join(copies))
        return {"text": text, "warnings": warn, "args": args_set(w), "copies": copies, "maps": maps, "type": w["type"], "want": want,
                "op": {k: op[k] for k in ("node", "Userindex", "Charidx", "charname")}, "auto": auto,
                "end_local": w["e"].isoformat(sep=" "), "w": {"type": w["type"], "chan": w["chan"], "map": w["map"]},
                "utc_off_s": int(utc_off.total_seconds()), "drop_off": drop, "window": win_text(want)}

    def apply(self, ctx, p, prev):
        _two(ctx, p)
        o = prev["op"]
        try:
            row = bridge.call("event_set", int(o["Userindex"]), int(o["Charidx"]), o["node"], prev["args"], ttl=20, by=ctx.login)
        except bridge.BridgeError as ex:
            raise OpRefused("6038 не выполнен: %s" % ex)
        # ★ ревизия 44 Н-2: всё ниже — после отправленной 6038: сбой чтения / заданий не превращает выполненное в «отказ»
        good, bad, err = _verify(prev["copies"], prev["maps"], prev["type"], prev["want"])
        parts = ["Event.dat записали: %s" % (", ".join(good) or "никто")]
        if err:
            parts.append("проверка Event.dat не прочитана (%s) — итог записи неизвестен, посмотрите карточку «События и сбросы»" % err)
        elif bad:
            parts.append("НЕ подтвердили за %d с: %s — событие может идти только в памяти NpcServer до его рестарта (Event.dat не записан)"
                         % (VERIFY_S, ", ".join(bad)))
        job, job_err, dropped = None, None, []
        from core import jobs
        if prev["auto"]:
            # ★ ревизия 44 С-1: задание знает, КАКОЕ окно выключает (expect) — запись Event.dat к его сроку другая → отказ, не 6040.
            #   Часы для срока — из предпросмотра (Н-2: повторное чтение часов не нужно); ставится и когда проверка не прочитана.
            at = (datetime.datetime.fromisoformat(prev["end_local"]) + datetime.timedelta(seconds=prev["utc_off_s"])
                  + datetime.timedelta(minutes=OFF_DELAY_MIN))
            try:
                job = jobs.add("event.off", {"type": prev["w"]["type"], "chan": prev["w"]["chan"], "map": prev["w"]["map"], "confirm": CONFIRM,
                                             "expect": prev["want"], "expect_window": prev["window"], "set_cmd": int(row["id"])},
                               "service", at.replace(microsecond=0), "", OFF_NOTE, ctx.login, ctx.user_id, ctx.role)
                parts.append("выключение — задание №%d (выключит только окно %s)" % (job, prev["window"]))
            except Exception as ex:
                job_err = str(ex)[:200]
                parts.append("задание выключения НЕ поставлено (%s) — выключите вручную (event.off) после %s" % (job_err, prev["end_local"][:16]))
        if prev.get("drop_off") and not bad and not err:   # окно прежних заданий заменено у всех копий — снять их (новое ставит своё)
            for jid in prev["drop_off"]:
                try:
                    if jobs.cancel(jid):
                        dropped.append(jid)
                except Exception:
                    pass
            if dropped:
                parts.append("сняты прежние задания выключения: %s" % ", ".join("№%d" % x for x in dropped))
            if len(dropped) < len(prev["drop_off"]):
                parts.append("не сняты (уже не ждут или сбой): %s — они откажут сами (окно заменено)"
                             % ", ".join("№%d" % x for x in prev["drop_off"] if x not in dropped))
        elif prev.get("drop_off"):
            parts.append("прежние задания выключения %s не сняты: запись не подтверждена — к сроку они сверят окно сами"
                         % ", ".join("№%d" % x for x in prev["drop_off"]))
        msg = "6038 отправлен (команда №%s): %s" % (row["id"], "; ".join(parts))
        return {"before": None, "after": {"cmd": int(row["id"]), "confirmed": good, "unconfirmed": bad, "verify_error": err, "args": prev["args"],
                                          "job": job, "job_error": job_err, "dropped_off": dropped}, "message": msg}


@register
class EventOff(Operation):
    name, title, perm, reversible = "event.off", "События: выключить событие (6040, мост)", "server.events", False
    schedule_runner, two_factor, confirm_word = "service", False, CONFIRM

    def target(self, p):
        return "event:%s:%s:%s" % (p.get("type"), p.get("chan", -1), p.get("map", -1))

    def schedule_check(self, ctx, p):
        t, chan, m = _scope(p)
        if str(p.get("confirm") or "") != CONFIRM:
            raise OpRefused("нужно подтверждение: выключение события (ключ confirm = event)")
        exp = p.get("expect")
        if exp is not None and (not isinstance(exp, dict) or set(exp) != set(ZERO)):
            raise OpRefused("ожидаемое окно задания выключения (expect) испорчено — не выключаю вслепую")
        return t, chan, m

    def preview(self, ctx, p):
        t, chan, m = self.schedule_check(ctx, p)
        exp = p.get("expect")
        st = state()
        copies = _copies(chan)
        miss = [n for n in copies if not st["npc"][n]["ok"]]
        if miss:
            raise OpRefused("Event.dat не прочитан или битый: %s — что выключается, неизвестно, вслепую не делается" % ", ".join(miss))
        if m >= 0 and (st["map_count"] is None or m >= st["map_count"]):
            raise OpRefused("карты %d нет в ini\\MapInfo.ini NpcServer (карт %s) — NpcServer ответит отказом" % (m, st["map_count"]))
        maps = _maps_of(m, st)                       # 6040 с картой −1 обнуляет только MapCount карт (sub_41D610), слоты дальше не применяются
        files = read_files([n + "\\" + EV_DAT for n in copies])
        loc, _u = clock()
        on, foreign = [], []
        for n in copies:
            d = decode_dat(files.get(n + "\\" + EV_DAT))
            if d is None:
                raise OpRefused("Event.dat %s не прочитан или битый при повторном чтении — что выключается, неизвестно, вслепую не делается" % n)
            for mm in maps:
                e = d[(t, mm)]
                if not entry_empty(e):
                    on.append((n, mm, win_text(e), phase(e, loc)))
                    if exp is not None and not same_entry(e, exp):
                        foreign.append((n, mm, win_text(e)))
        if not on:
            raise OpRefused("событий типа «%s» на %s (%s) нет — выключать нечего" % (TYPE_NAMES[t], _map_label(m, st), ", ".join(copies)))
        if foreign:                                  # ★ ревизия 44 С-1: задание event.set выключает только СВОЁ окно
            fw = (p.get("expect_window") or win_text(exp), foreign[0][2], foreign[0][0], foreign[0][1])
            if len(foreign) > 1:
                raise OpRefused("окно заменено — не выключаю: задание выключало %s, а сейчас записано %s (%s карта %d и ещё %d) — новое событие "
                                "не трогаю" % (fw + (len(foreign) - 1,)))
            raise OpRefused("окно заменено — не выключаю: задание выключало %s, а сейчас записано %s (%s карта %d) — новое событие не трогаю" % fw)
        op = operator(ctx, p, "выключение события")
        uniq = sorted({(x[2], x[3]) for x in on})
        text = "выключить событие «%s»: %s, %s; сейчас: %s" % (TYPE_NAMES[t], CHAN_NAMES[chan], _map_label(m, st),
                                                              "; ".join("%s (%s)" % u for u in uniq[:4]))
        warn = ["6040 обнуляет все поля типа «%s» у выбранных карт (у карты одно окно на тип)" % TYPE_NAMES[t],
                "от персонажа %s (учётка %s, %s); сток ответит ему в чат «[Success EVENT OFF] …»" % (op["charname"], op["Userindex"], op["node"])]
        if exp is not None:
            warn.append("ожидаемое окно %s записано у всех выбранных карт — выключается оно" % (p.get("expect_window") or win_text(exp)))
        return {"text": text, "warnings": warn, "args": "type=%d;chan=%d;map=%d" % (t, chan, m), "copies": copies,
                "maps": maps, "type": t, "op": {k: op[k] for k in ("node", "Userindex", "Charidx", "charname")}}

    def apply(self, ctx, p, prev):
        o = prev["op"]
        try:
            row = bridge.call("event_off", int(o["Userindex"]), int(o["Charidx"]), o["node"], prev["args"], ttl=20, by=ctx.login)
        except bridge.BridgeError as ex:
            raise OpRefused("6040 не выполнен: %s" % ex)
        good, bad, err = _verify(prev["copies"], prev["maps"], prev["type"], ZERO)      # ★ ревизия 44 Н-2: после отправки — не отказ
        parts = ["Event.dat обнулили: %s" % (", ".join(good) or "никто")]
        if err:
            parts.append("проверка Event.dat не прочитана (%s) — итог записи неизвестен, посмотрите карточку «События и сбросы»" % err)
        elif bad:
            parts.append("НЕ подтвердили за %d с: %s — событие может быть выключено только в памяти NpcServer до его рестарта (Event.dat не "
                         "записан)" % (VERIFY_S, ", ".join(bad)))
        return {"before": None, "after": {"cmd": int(row["id"]), "confirmed": good, "unconfirmed": bad, "verify_error": err},
                "message": "6040 отправлен (команда №%s): %s" % (row["id"], "; ".join(parts))}


@register
class RankRecalc(Operation):
    name, title, perm, reversible = "rank.recalc", "Рейтинги: пересчитать сейчас (6020 / P25, мост)", "server.ranks", False
    schedule_runner, confirm_word = "service", RANK_CONFIRM

    def target(self, p):
        return "rank:%s" % p.get("what", 0)

    def schedule_check(self, ctx, p):
        what = _int(p, "what", 0, 3, 0)
        if str(p.get("confirm") or "") != RANK_CONFIRM:            # ★ ревизия 44 Н-3: массовая операция — как остальные массовые
            raise OpRefused("нужно подтверждение: пересчёт меняет звания и топ всем игрокам (ключ confirm = rank)")
        return what

    def preview(self, ctx, p):
        what = self.schedule_check(ctx, p)
        op = operator(ctx, p, "пересчёт рейтингов")
        return {"text": "пересчитать рейтинги сейчас: %s" % RANK_WHAT[what], "what": what,
                "warnings": ["P25: повтор не чаще раза в MinIntervalSec (dev: 60 с) — иначе отказ «слишком часто»",
                             "итог пересчёта базы (2334) придёт строками в чат оператору %s (учётка %s); в панели — что запрос ушёл"
                             % (op["charname"], op["Userindex"]),
                             "рейтинг чести — отдельно: «Лагерь: пересчитать рейтинг чести» (camp.rank_rebuild)"],
                "op": {k: op[k] for k in ("node", "Userindex", "Charidx", "charname")}}

    def apply(self, ctx, p, prev):
        o = prev["op"]
        try:
            row = bridge.call("rank_recalc", int(o["Userindex"]), int(o["Charidx"]), o["node"], "what=%d" % prev["what"], ttl=20, by=ctx.login)
        except bridge.BridgeError as ex:
            raise OpRefused("6020 не выполнен: %s" % ex)
        kv = bridge.parse_kv(row.get("result"))
        msg = ("пересчёт условий званий: выдано %s (персонажей в игре %s); " % (kv.get("granted"), kv.get("players"))
               if prev["what"] in (0, 3) else "") + ("запрос 2333 ушёл в базу — итог придёт оператору" if kv.get("sent") == 1 else "база не нужна")
        return {"before": None, "after": {"cmd": int(row["id"]), "result": kv}, "message": msg}


def _sql(q, params=()):
    if SQL:
        return SQL(q, params)
    from core import db
    with db.GameReader("joy1") as r:
        return r.rows(q, params)


def boundary(now):
    """Граница суток 06:00 — как в CRT_AsdaLimitationDailyReset (минута запаса)."""
    d = now - datetime.timedelta(minutes=1)
    b = datetime.datetime(d.year, d.month, d.day, 6, 0)
    return b if d >= b else b - datetime.timedelta(days=1)


def daily_state():
    """Ежедневные задания доски: строк к сбросу, журнал сброса, граница, задача ОС (только чтение)."""
    from core import db
    try:
        now = _sql("SELECT GETDATE() AS n")[0]["n"]
        n = _sql("SELECT COUNT(*) AS n FROM dbo.CRT_LimitationQuest WHERE Quest_Type = 1 AND (Quest_Flag = 3 OR Quest_Count <> 0)")[0]["n"]
        log = _sql("SELECT TOP 6 Id, Boundary, Edate, Source, Done, FlagRows, CountRows FROM dbo.AsdaLimitationResetLog ORDER BY Id DESC")
    except db.DbError as ex:
        raise OpRefused("журнал сброса ежедневных не прочитан: %s" % ex)
    b = boundary(now)
    done = _sql("SELECT TOP 1 Source, Edate FROM dbo.AsdaLimitationResetLog WHERE Done = 1 AND Boundary = ?", (b,))
    task = None
    try:
        from core import hostshell
        t = hostshell.powershell("$i = Get-ScheduledTaskInfo -TaskName ASDA_LimitationDailyReset -ErrorAction Stop; "
                                 "'{0:yyyy-MM-dd HH:mm}|{1}|{2:yyyy-MM-dd HH:mm}' -f $i.LastRunTime, $i.LastTaskResult, $i.NextRunTime", 40)
        a = t.strip().splitlines()[-1].split("|")
        task = {"last": a[0], "result": a[1], "next": a[2]} if len(a) == 3 else None
    except Exception:
        task = None
    return {"now": str(now)[:19], "boundary": b.strftime("%Y-%m-%d %H:%M"), "pending_rows": int(n),
            "done": ({"source": done[0]["Source"], "at": str(done[0]["Edate"])[:19]} if done else None),
            "log": [{k: (str(v)[:19] if isinstance(v, datetime.datetime) else v) for k, v in r.items()} for r in log], "task": task}


@register
class DailyReset(Operation):
    name, title, perm, reversible = "daily.reset", "Ежедневные задания доски: сбросить всем", "server.daily", False
    schedule_runner, two_factor, confirm_word = "service", True, DAILY_CONFIRM

    def target(self, p):
        return "daily:%s" % p.get("mode")

    def schedule_check(self, ctx, p):
        mode = str(p.get("mode") or "")
        if mode not in DAILY_MODES:
            raise OpRefused("неверный режим сброса (можно: catchup — догнать суточный, force — внеочередной всем)")
        if mode == "force" and str(p.get("confirm") or "") != DAILY_CONFIRM:
            raise OpRefused("внеочередной сброс снимает «выполнено сегодня» у всех — нужно подтверждение (ключ confirm = daily)")
        return mode

    def preview(self, ctx, p):
        mode = self.schedule_check(ctx, p)
        s = daily_state()
        warn = []
        if mode == "catchup":
            if s["done"]:
                raise OpRefused("суточный сброс за границу %s уже сделан (%s, %s) — догонять нечего" % (s["boundary"], s["done"]["source"], s["done"]["at"]))
            text = "догнать суточный сброс ежедневных заданий доски за границу %s (как задача ОС 06:02): строк к сбросу %d" % (s["boundary"], s["pending_rows"])
        else:
            text = "внеочередной сброс ежедневных заданий доски всем: строк к сбросу %d (граница %s%s)" % (
                s["pending_rows"], s["boundary"], ", суточный уже сделан" if s["done"] else ", суточный ещё НЕ сделан")
            warn.append("игроки в игре увидят сброс после смены карты или перезахода: память GameServer сбрасывает их задания только в 06:00")
        if s["pending_rows"] == 0:
            warn.append("строк к сбросу 0 — сброс ничего не изменит")
        warn.append("сбрасываются только дневные задания доски (Quest_Type = 1): «выполнено» и счётчик; повторяемые и разовые не трогаются")
        if s["task"] is None:
            warn.append("задача ОС ASDA_LimitationDailyReset — состояние не прочитано")
        elif s["task"]["result"] != "0":
            warn.append("задача ОС ASDA_LimitationDailyReset: последний итог %s (%s)" % (s["task"]["result"], s["task"]["last"]))
        return {"text": text, "warnings": warn, "mode": mode, "expect": s["pending_rows"]}

    def apply(self, ctx, p, prev):
        if prev["mode"] == "force":
            _two(ctx, p)
        from core import db
        w = db.GameWriter("joy1")
        try:
            r = w.rows("EXEC adm.LimitationReset ?", (DAILY_MODES[prev["mode"]],))
            w.commit()
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        w.close()
        x = r[0] if r else {"rc": None}
        rc = x.get("rc")
        if rc == 0:
            raise OpRefused("суточный сброс за эту границу уже был — ничего не сброшено")
        if rc == -1:
            raise OpRefused("сброс занят другим вызовом (замок не взят за 5 с) — повторите")
        if rc != 1:
            raise OpRefused("процедура сброса вернула %s" % rc)
        return {"before": {"pending_rows": prev["expect"]}, "after": {"flag_rows": x.get("flag_rows"), "count_rows": x.get("count_rows"),
                                                                      "boundary": str(x.get("boundary"))[:16]},
                "message": "сброшено: «выполнено» %s строк, счётчиков %s" % (x.get("flag_rows"), x.get("count_rows"))}
