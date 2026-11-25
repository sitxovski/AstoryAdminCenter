# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/mapdata.py — область «Карты» (волна А4.8, 20.11.2026; разбор Reports/admin_center/research_a4_data.md §1.5, §3, §5:
«цена телепорта и открытые карты (только сервер); остальное — на чтение»; переходы и кристаллы — Reports/owner_0927/world_transitions.md,
crystal_warp_audit.md, P40 — p40_crystal.md).

Только правка СУЩЕСТВУЮЩИХ записей (решение владельца 19.11): карт, секций и строк не добавляется, размер матрицы не меняется.

ЦЕНА ТЕЛЕПОРТА — MapData_Info\\MapWarpCost.txt во всех GS (загрузчик GameServer.c:72101: N, затем N×N чисел ПОТОКОМ (fscanf %s + atol) в
  матрицу pPrice[откуда][куда]). Читает её ТОЛЬКО RecvContinent_PortalMove @0x5498A0 (опкод 5477, кристалл; :125975) — второй метод:
  в GameServer.exe.asm 9 обращений к указателю матрицы stru_600C98.gap_4 — загрузчик, освобождение (:66545) и этот обработчик.
  Значение < 0 — молчаливый отказ (ответа нет), 0 — бесплатно; игрок фракции-владельца города (MapInfo +130 ТЕКУЩЕЙ карты ≤ 2, слот армии
  = владельцу) платит 0; денег (код 20551) меньше цены — 5055 код 12; иначе списание sub_4D7540 и журнал 2265. Прибытие — запись
  Total_PortalConfig[куда] (CUserManager+2656, флаг USE ≠ 0 обязателен). Политика per_copy: у Indun_GameServer своя база (dev 20.11:
  [7][16] поле 5000, Indun 0) — правка ложится на каждую копию по её числу, у копии с другим прежним значением ячейки — ОТКАЗ.
  warp.cost {from, to, cost}: cost −1 (запрет) или 0…2·10⁹. Смена «запрещено ↔ разрешено» — сильная всегда (type), число — порог ×2.
  P40 (AsdaPatch [P40_CrystalTeleportGate], CheckNpc) пропускает 5477 только у NPC текущей карты, у которого в ключе Crystals есть карта-
  цель (тип NPC из GameServer\\NpcData_Info\\<имя карты MapInfo>.npc: запись 221 б, +4 тип, +8/+10 клетка — LoadNpcInfo :22578). Маршрут
  без такого NPC при P40, действующем во ВСЕХ GS, — ОТКАЗ «цена не подействует»; P40 выключен хоть где-то — предупреждение.
  Клиент цену не знает: подписи кнопок кристаллов (NpcNsrButton.json, команда 30031) — текст оригинала, панель их не правит (предупреждение
  со списком подписей, где стоит прежнее число).
ОТКРЫТЫЕ КАРТЫ — MapData_Info\\OpenMapInfo.ini, только копии ПОЛЯ (GameServer, Ch2_GameServer; Indun_GameServer работает без файла —
  byte_5F5EF6 = 0, GameServer.c:64923). Загрузчик :64891: MapCount ≠ 0 (иначе файл не действует), секции MAP_0…MAP_<слотов−1> (сток 23,
  P30 — min(MaxMaps, 30, строк MapInfo), если больше 23), Use ≠ 0 → 1, число открытых ВСЕХ типов > ThreadInfo.ini [MAX_INIT_THREAD] COUNT —
  exit(1) при старте. Потоки (:66189) — только открытым картам типов 0/1/3 (MapInfo +63; тип 6 — при P120). Без потока вход в мир не
  состоится: SearchThreadInfo @0x4A8450 (:67625) для типов 0/1/3 возвращает 3. Use читают ещё напольный портал sub_52C4C0 (:114178 —
  зона на закрытую карту молчит), P40 (CheckOpenMap), P120, P123 (GM — разрешено).
  map.open {map, use}: только карты типов 0/1/3 (6 — при P120 во всех копиях поля), остальные — отказ «смысл Use не подтверждён». Открытие:
  в итоге набора открытых ≤ COUNT в каждой копии (after_run), файл MapData_Info\\<имя>.sim (sub_419E50, :10807) есть. Закрытие: персонажи
  на карте (CharPos.Poridx — по нему LoginManager выбирает Game_<карта>) и с точкой возрождения на ней (VillagePos.Villageidx), в т. ч. в
  корзине (Del_CharPos / Del_VillagePos без adm.CharRestored — восстановление вернёт их как есть), — ОТКАЗ (их вход не состоится);
  карта 3 — ОТКАЗ всегда: будущие держатели (UPCreateChar ставит новых персонажей на карту 3, charLogOnRes без VillagePos возрождает там).
  Открытие/закрытие — сильная всегда (type). ПАРА (необязательная): реестр карт порта Tools/data/asda_map_registry.json server.open_use →
  AsdaMapRegistry.h kServerMapOpen (маршруты трекера и автопути) — рендером НАСТОЯЩЕГО asda_map_registry.render_cpp_header; C++ — полная
  сборка выпуска.
Ни один AsdaPatch не переписывает цены и Use в памяти (исходники 20.11): P30 переносит массив Use (0x60A880) в DLL, P40/P120/P123 только
  читают; patches.ini панель не меняет.
НА ЧТЕНИЕ (справка): MapInfo.txt (имя, лимит игроков +56, тип +63, город +62, группа +130, точки входа/возврата +98/+108 — :71949),
  Total_PortalConfig.Ini (USE, прибытие кристалла; запись k = карта k — sub_522E80), зоны PortalIP_Info\\<имя>_PortalConfig.Ini (сток
  sub_522B40-область :110475: Index, POSX/POSZ/RANGEX/RANGEZ, STARTPOSX/Z, INDUN), ThreadInfo COUNT, кристаллы. Точки прибытия и возврата
  не правятся: для них нужен разбор проходимости .SIM и зон (метод world_transitions_probe/portal_check.py), в разборе §5 — на чтение.
Перед выкладкой и откатом закрываемые карты и счётчик потоков ПЕРЕЧИТЫВАЮТСЯ (apply_guard по «живая + файлы набора» / «живая, файлы
набора — базой»). Эти две причины (GameServer не стартует, вход персонажей не состоится) — GUARD_HARD: второе подтверждение отката
(--held-ok) их не прощает (shopcs.guard_hard, ревизия 40 В-1). Побочных эффектов при импорте нет.

★ Ревизия 40 (20.11.2026):
  * персонажи на карте (joy_holders) — ещё два пути входа на карту: LoginManager для CharPos.Poridx 19/20/22 берёт карту из
    Joy1.dbo.Charinpos (UPCharDetailPos, LM.c:4286-4311; строки нет — карта 0, дефект оригинала @Poridx IS NULL → 0) и P108
    UP_AsdaDungeonRelogReset (restart_stack шаг 4б2 ПОСЛЕ перепроверки выкладчика): Cporidx турнирных 10/11 «был в игре» (Usernum ≠ −1
    или State 1) → Poridx карты выхода AsdaDungeonRelogPoint Kind 'R'; таблицы нет — пропуск с пометкой (SQL P108 не применён — шаг 4б2
    пропускается тоже); то же — в невосстановленной корзине;
  * P30 / P40 / P120 — по ФАКТУ установки: блок последнего запуска журнала патчей <GS>\\Log\\Log_Patch\\PatchLog_<дата>.txt (метки
    dllmain [OK] / [ВЫКЛ] / [MISMATCH] / [ОШИБКА]): патч, не вставший при последнем старте ([MISMATCH] / [ОШИБКА] — сверка площадок
    VerifyAllSites), не встанет и после рестарта выкладки (тот же exe) — он не действует; журнал не прочитан или [ВЫКЛ] при включённом
    в patches.ini — пометка «установка не подтверждена»; число слотов P30 — объявленное N MapInfo.txt КАЖДОЙ копии (ReadMapInfoRows);
  * кнопки кристаллов — все команды 5477 клиента (game_main.c:10086-10131, 10269-10273): 30031 (строка WarpList) и с картой в коде
    (30033/30040 → 3, 30036 → 4, 30037 → 5, 30039/30041 → 0, 30042 → 7, 30063 → 21, 30064 → 22);
  * Crystals — побуквенно ParseCrystals (wcstol, тип 1…1023 = kMaxType, ≤ 64 записей g_crystals[64], буфер GetStr 512 — 511 знаков);
  * NPC с отрицательной клеткой в .npc: LoadNpcInfo пишет тип, а клетку оставляет конструкторной 0,0 (sub_439BF0) — P40 его видит в
    клетке 0,0; тип ≥ 300 (`< 0x12C`) гейтит только поле +91 из NpcInfo, а не саму запись (ревизия Н-3 — проверено, тип в массиве есть);
  * MapCount — байт byte_5F5EF7 (asm 0x4A0416: mov byte, al; test по байту): кратное 256 — файл не действует.
"""
import json
import os
import re
import struct
import sys

from core import config
from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "mapdata", "Карты"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
WARP, OPEN = "MapData_Info\\MapWarpCost.txt", "MapData_Info\\OpenMapInfo.ini"
MAPINFO, THREAD = "MapData_Info\\MapInfo.txt", "ConfigSet\\ThreadInfo.ini"
TOTAL, PATCHES = "PortalIP_Info\\Total_PortalConfig.Ini", "ConfigSet\\patches.ini"
SRV_FILES = [("GS", WARP, "per_copy"), ("GSF", OPEN, "per_copy")]
REG_JSON = os.path.join(E.UE_TOOLS, "data", "asda_map_registry.json")
REG_H = os.path.join(E.UPROJ, "Source", "AsdaReborn", "Public", "World", "AsdaMapRegistry.h")
NSR_BTN, NSR_HDR = os.path.join(E.NPC_DIR, "NpcNsrButton.json"), os.path.join(E.NPC_DIR, "NpcNsrHeader.json")
WARPLIST = os.path.join(E.NPC_DIR, "WarpList.json")
CLIENT_FILES = {"map_registry": REG_JSON}
DT, IMPORTERS = {}, {}
COST_MAX = 2000000000
STOCK_SLOTS, HARD_SLOTS = 23, 30                    # сток 0x60A880 (23 записи), P30 kHardMax
THREAD_TYPES = (0, 1, 3)                            # SetUserInfo_ThreadID_Mapping :66189 (тип 6 — площадка A P120)
CRYSTAL_CMD = 30031                                 # кнопка кристалла: Param = строка WarpList (crystal_warp_audit.md §2)
CRYSTAL_FIXED = {30033: 3, 30036: 4, 30037: 5, 30039: 0, 30040: 3, 30041: 0, 30042: 7, 30063: 21, 30064: 22}   # ★ ревизия 40 Н-1:
                                                    # 5477 с картой в коде (CGameUI_HandleControlCommand, game_main.c:10096-10131, 10269-10273)
P40_SEC, P40_DEFAULT = "P40_CrystalTeleportGate", "46:7,0,1;49:3;50:7,3,6,2;51:6,0;52:2,0;53:3,0,16;55:3;201:7;107:5"
P40_MAX_TYPE, P40_MAX_REC, P40_BUF = 1024, 64, 511  # kMaxType, g_crystals[64], wchar_t buf[512] Config::GetStr (p40…cpp)
NO_JOY1 = "нет связи с Joy1"
GUARD_HARD = ("GameServer выйдет при старте", "вход в мир не состоится")   # ★ ревизия 40 В-1: невыполнимое (shopcs.guard_hard)
CHARINPOS_MAPS = (19, 20, 22)                       # LoginManager: эти Poridx подменяет Charinpos.Poridx (UPCharDetailPos, LM.c:4286)
PATCHLOG_DIR = "Log\\Log_Patch"                     # журнал патчей AsdaPatch (Log.cpp; разбор — tools/patchlog.py, тот же формат)
PATCH_TAIL = 4 * 1024 * 1024                        # предел чтения журнала с конца (суточный журнал GameServer ~0,2 МБ)
LM_DIR = "LoginManager\\GameServerIP"               # адреса Game_<n> LoginManager (sub_4046E0, LM.c:1486-1520)
TYPE_NAMES = {0: "поле/город", 1: "особая", 2: "инстанс", 3: "подземелье", 4: "война (RoseWar)", 5: "тип 5", 6: "шахта (P120)"}

KINDS = {
    "warp.cost": ("Карты: цена телепорта кристаллом (MapWarpCost.txt [откуда][куда], только сервер; −1 — переход запрещён)",
                  ("from", "to", "cost"), False),
    "map.open": ("Карты: карта открыта (OpenMapInfo.ini MAP_<n> Use, копии поля; зеркало в реестре карт порта)", ("map", "use"), False),
}


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def norm(kind, p):
    if kind == "warp.cost":
        cost = E._ival(p, "cost", -1, COST_MAX)
        return {"from": E._ival(p, "from", 0, HARD_SLOTS - 1), "to": E._ival(p, "to", 0, HARD_SLOTS - 1), "cost": cost}
    return {"map": E._ival(p, "map", 0, HARD_SLOTS - 1), "use": E._ival(p, "use", 0, 1)}


def target_key(kind, p):
    if kind == "warp.cost":
        return "warp:%d:%d" % (p["from"], p["to"])
    return "open:%d" % p["map"]


# =====================================================================================================================
# Разбор таблиц стойки (повтор загрузчиков)
# =====================================================================================================================
_TOK = re.compile(rb"\S+")


def warp_rows(t, where):
    """Строки тела MapWarpCost.txt по строкам матрицы → (N, [номер строки файла]). Сервер читает поток чисел; правка по строке допустима,
    только если слов ровно 1 + N·N и в каждой из N строк тела N слов — иначе отказ (порядок чисел сервера и строк файла не доказан)."""
    n = E._int(t.lines[0].decode("latin-1"), -1)
    body = [i for i in range(1, len(t.lines)) if t.lines[i].strip()]
    if n <= 0 or len(body) < n or any(len(t.lines[i].split()) != n for i in body[:n]) or len(b" ".join(t.lines).split()) != 1 + n * n:
        raise OpRefused("%s %s: матрица не ложится построчно (N = %d, строк тела %d) — порядок чисел сервера не доказан, правка не делается"
                        % (WARP, where, n, len(body)))
    return n, body[:n]


def warp_get(t, rows, fr, to):
    m = list(_TOK.finditer(t.lines[rows[fr]]))[to]
    v = m.group(0).decode("latin-1")
    if not re.match(r"^-?\d+$", v):
        raise OpRefused("%s: ячейка [%d][%d] «%s» — не число, правка не делается" % (WARP, fr, to, v[:20]))
    return int(v)


def warp_set(t, rows, fr, to, val):
    ln = t.lines[rows[fr]]
    m = list(_TOK.finditer(ln))[to]
    t.set_line(rows[fr], ln[:m.start()] + str(val).encode("ascii") + ln[m.end():])


def warp_matrix(raw, where="GameServer"):
    """Матрица цен (список строк) из байтов файла."""
    t = E.Table(where, raw)
    n, rows = warp_rows(t, where)
    return [[warp_get(t, rows, a, b) for b in range(n)] for a in range(n)]


def mapinfo(raw):
    """MapInfo.txt → [{id, name, users, town, type, group, points}] — как загрузчик :71949 (id = позиция, иначе «Sync Error»)."""
    lines = [ln for ln in raw.split(b"\n")[1:] if ln.strip()]
    n = E._int(raw.split(b"\n", 1)[0].decode("latin-1"), -1)
    out = []
    for k in range(max(n, 0)):
        if k >= len(lines):
            break
        f = lines[k].decode("cp1251", "replace").split()
        if len(f) < 22 or E._int(f[0], -1) != k:
            raise OpRefused("MapInfo.txt: строка карты %d не разобрана (Sync Error у сервера) — справка не строится" % k)
        cnt = max(0, E._int(f[20]))
        pts = [(E._int(f[21 + 2 * j]), E._int(f[22 + 2 * j])) for j in range(min(cnt, 5)) if 22 + 2 * j < len(f)]
        g = 21 + 2 * cnt
        out.append({"id": k, "name": f[1], "users": E._int(f[2]), "town": E._int(f[5]), "type": E._int(f[6]),
                    "group": (E._int(f[g]) & 0xFF) if g < len(f) else 255, "points": [list(x) for x in pts if x != (0, 0)]})
    return out


def ini_sections(raw):
    """INI как GetPrivateProfile*: {секция (нижний регистр): {ключ (нижний регистр): (значение, номер строки)}} — первая секция и первый ключ."""
    lines, _sep = E._split(raw)                      # строки — как у shopdata.Table (номер строки годится для set_line)
    out, sec = {}, None
    for i, ln in enumerate(lines):
        s = ln.decode("cp1251", "replace").strip()
        if not s or s.startswith(";"):
            continue
        m = re.match(r"^\[([^\]]*)\]", s)
        if m:
            name = m.group(1).strip().lower()
            sec = None if name in out else out.setdefault(name, {})
        elif sec is not None and "=" in s:
            k, v = s.split("=", 1)
            sec.setdefault(k.strip().lower(), (v.strip().strip('"').strip(), i))
    return out


def ini_int(sec, key, default=0):
    """GetPrivateProfileInt: нет ключа — default, иначе ведущее число (не число — 0)."""
    v = (sec or {}).get(key.lower())
    if v is None:
        return default
    m = re.match(r"\s*([+-]?\d+)", v[0])
    return int(m.group(1)) if m else 0


def open_state(raw, slots):
    """OpenMapInfo.ini → {"count": MapCount, "use": {карта: 0/1 по секциям < slots}, "line": {карта: строка Use}}."""
    s = ini_sections(raw)
    use, line = {}, {}
    for k in range(slots):
        sec = s.get("map_%d" % k)
        if sec is None:
            continue
        use[k] = 1 if ini_int(sec, "use", 0) != 0 else 0
        if "use" in sec:
            line[k] = sec["use"][1]
    # MapCount — БАЙТ (asm 0x4A0416 mov byte_5F5EF7, al; test по байту): кратное 256 — файл не действует (ревизия 40, мелочь 3)
    return {"count": ini_int(s.get("map_info"), "mapcount", 0) & 0xFF, "use": use, "line": line}


def set_ini_use(t, line_no, val):
    ln = t.lines[line_no]
    m = re.match(rb"^(\s*[^=]*=\s*)([+-]?\d+)", ln)
    if not m:
        raise OpRefused("%s: строка Use «%s» — не число, правка не делается" % (OPEN, ln.decode("latin-1")[:40]))
    t.set_line(line_no, m.group(1) + str(val).encode("ascii") + ln[m.end():])


def total_state(raw):
    """Total_PortalConfig.Ini → {карта: {"use", "x", "z", "ip"}} — запись k по порядку секций (sub_522E80: цикл k < count, конец — пустой IP)."""
    s = ini_sections(raw)
    out = {}
    for k in range(ini_int(s.get("portal_count"), "count", 0)):
        sec = s.get("portal_info_%d" % k)
        ip = (sec or {}).get("ip", ("", 0))[0]
        if not ip:
            break
        out[k] = {"use": ini_int(sec, "use"), "index": ini_int(sec, "index"), "x": ini_int(sec, "startposx"), "z": ini_int(sec, "startposz")}
    return out


def zones_state(raw):
    """<имя>_PortalConfig.Ini → [{"k", "to", "x0", "z0", "x1", "z1", "ax", "az", "indun"}] — как LoadPortalServerInfo (:110475)."""
    if not isinstance(raw, bytes):                    # None (нет) или UNREAD (не прочитан) — зон нет в справке
        return []
    s = ini_sections(raw)
    out = []
    for k in range(ini_int(s.get("portal_count"), "count", 0)):
        sec = s.get("portal_info_%d" % k)
        if not (sec or {}).get("ip", ("", 0))[0]:
            break
        x, z = ini_int(sec, "posx"), ini_int(sec, "posz")
        out.append({"k": k, "to": ini_int(sec, "index"), "x0": x, "z0": z, "x1": x + ini_int(sec, "rangex"), "z1": z + ini_int(sec, "rangez"),
                    "ax": ini_int(sec, "startposx"), "az": ini_int(sec, "startposz"), "indun": ini_int(sec, "indun")})
    return out


def npc_types(raw):
    """NpcData_Info\\<карта>.npc → [(тип, x, z)] рабочего массива NPC (запись 221 б, LoadNpcInfo :22578-22690: размер не кратен — файл не
    читается). ★ Ревизия 40: тип (+4 → массив +2) пишется у КАЖДОЙ записи, а клетка (+8/+10) — только если обе ≥ 0; иначе остаётся
    конструкторная 0,0 (sub_439BF0) — такой NPC в массиве есть, и P40 видит его в клетке 0,0. Тип ≥ 300 запись не отбрасывает (`< 0x12C`
    гейтит лишь поле +91 из NpcInfo)."""
    if not isinstance(raw, bytes) or not raw or len(raw) % 221:
        return []
    out = []
    for i in range(len(raw) // 221):
        t, = struct.unpack_from("<h", raw, 221 * i + 4)
        x, z = struct.unpack_from("<hh", raw, 221 * i + 8)
        out.append((t, x, z) if x >= 0 and z >= 0 else (t, 0, 0))
    return out


def _wcstol(s, i):
    """wcstol(p, &end, 10) → (значение, конец) или (None, i): ведущие пробельные знаки, знак, десятичные цифры (без них — end == p)."""
    j = i
    while j < len(s) and s[j] in " \t\n\v\f\r":
        j += 1
    k = j + 1 if j < len(s) and s[j] in "+-" else j
    e = k
    while e < len(s) and "0" <= s[e] <= "9":
        e += 1
    if e == k:
        return None, i
    return int(s[j:e]), e


def parse_crystals(s):
    """Ключ P40 Crystals «тип:карта,карта;тип:карта» побуквенно как ParseCrystals (p40_crystal_teleport_gate.cpp, ревизия 40 Н-2): буфер
    GetStr — 511 знаков; тип 1…1023 (kMaxType), карты 0…29, после типа сразу «:», записей ≤ 64 (g_crystals[64], повтор типа — тоже
    запись, действует первая) → {тип: {карты}} или None (синтаксис битый — патч не ставится, PatchResult::Failed)."""
    p, i, out, n = (s or "")[:P40_BUF], 0, {}, 0
    while i < len(p):
        while i < len(p) and p[i] in " ;":
            i += 1
        if i >= len(p):
            break
        t, e = _wcstol(p, i)
        if t is None or e >= len(p) or p[e] != ":" or t <= 0 or t >= P40_MAX_TYPE:
            return None
        i, maps = e + 1, set()
        while True:
            while i < len(p) and p[i] == " ":
                i += 1
            m, e = _wcstol(p, i)
            if m is None or m < 0 or m >= HARD_SLOTS:
                return None
            maps.add(m)
            i = e
            while i < len(p) and p[i] == " ":
                i += 1
            if i < len(p) and p[i] == ",":
                i += 1
                continue
            break
        if i < len(p) and p[i] != ";":
            return None
        if n >= P40_MAX_REC:
            return None
        n += 1
        out.setdefault(t, maps)
    return out or None


PATCH_SECS = {"p30": "P30_MapSlots", "p40": P40_SEC, "p120": "P120_MineTravel"}
_RUN_MARK = re.compile(r"\[(OK|ВЫКЛ|MISMATCH|ОШИБКА)\]\s+(\S+)")
_P30_SLOTS = re.compile(r"P30: слотов карт 23 -> (\d+)")
_plog = {}


def patch_log_state(text):
    """Блок ПОСЛЕДНЕГО запуска журнала патчей (как tools/patchlog.last_run: от последней строки паспорта «Хост   :» до «=== итог») →
    {"P30_MapSlots": "ok" | "off" | "bad" | None, …, "slots": N из «P30: слотов карт 23 -> N» | None, "total": есть ли итог} или None
    (паспорта нет — запуск не найден). bad — [MISMATCH] / [ОШИБКА] (площадки не совпали или патч не встал)."""
    ls = text.splitlines()
    starts = [i for i, ln in enumerate(ls) if "Хост   :" in ln]
    if not starts:
        return None
    block = ls[starts[-1]:]
    end = next((i for i, ln in enumerate(block) if "=== итог" in ln), None)
    inst = block if end is None else block[:end + 1]
    out = {sec: None for sec in PATCH_SECS.values()}
    out["slots"], out["total"] = None, end is not None
    for ln in inst:
        m = _RUN_MARK.search(ln)
        if m and m.group(2) in out:
            out[m.group(2)] = {"OK": "ok", "ВЫКЛ": "off"}.get(m.group(1), "bad")
        m = _P30_SLOTS.search(ln)
        if m:
            out["slots"] = int(m.group(1))
    return out


def patch_log(g, ttl=60):
    """Журнал патчей копии g: самый поздний <g>\\Log\\Log_Patch\\PatchLog_<8 цифр>.txt (файл держит работающий GameServer — FileShare
    ReadWrite), хвост ≤ PATCH_TAIL → patch_log_state или исключение (не прочитан). Только чтение (hostshell: служба — локально, ПК — SSH)."""
    import base64
    import time
    from core import config, hostshell
    hit = _plog.get(g)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    d = (config.STACK_ROOT + "\\" + g + "\\" + PATCHLOG_DIR).replace("'", "''")
    out = hostshell.powershell(
        "$f = Get-ChildItem -LiteralPath '%s' -Filter 'PatchLog_*.txt' -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "
        "'^PatchLog_\\d{8}\\.txt$' } | Sort-Object Name -Descending | Select-Object -First 1; if (-not $f) { Write-Output 'NOLOG'; return }; "
        "$fs = [IO.File]::Open($f.FullName, 'Open', 'Read', 'ReadWrite'); try { $len = $fs.Length; $n = [Math]::Min($len, %d); "
        "[void]$fs.Seek($len - $n, 'Begin'); $buf = New-Object byte[] $n; $got = 0; while ($got -lt $n) { $r = $fs.Read($buf, $got, $n - $got); "
        "if ($r -le 0) { break }; $got += $r } } finally { $fs.Close() }; Write-Output ('B64|' + [Convert]::ToBase64String($buf, 0, $got))"
        % (d, PATCH_TAIL), 90)
    if "NOLOG" in out.split():
        raise ValueError("%s: журнала патчей нет" % g)
    b64 = [ln for ln in out.splitlines() if ln.startswith("B64|")]
    if not b64:
        raise ValueError("%s: журнал патчей не прочитан" % g)
    raw = base64.b64decode(b64[-1][4:].strip())
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", "replace")          # Log.cpp пишет cp1251 (patchlog.decode_log)
    st = patch_log_state(text)
    if st is None:
        raise ValueError("%s: в журнале патчей нет запуска" % g)
    _plog[g] = (time.monotonic(), st)
    return st


def _ini_str(sec, key, default):
    """GetPrivateProfileStringW: нет ключа — default; значение без пар кавычек по краям."""
    v = (sec or {}).get(key.lower())
    if v is None:
        return default
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def patch_cfg(ttl=60):
    """{GS: {"p40": гейт «у NPC» действует, "open_gate": гейт «карта открыта», "crystals": {тип: {карты}}, "slots": слотов OpenMapInfo
    (до min со строками MapInfo копии — у вызывающего), "p120": P120 ставится, "p30_ok": P30 подтверждён журналом, "log_slots": слотов
    по журналу, "notes": [пометки]}} по patches.ini каждой копии (Config::GetBool/GetInt — GetPrivateProfileIntW, нет ключа — по умолчанию
    DLL) И ★ ревизия 40 С-2 по ФАКТУ установки (блок последнего запуска журнала патчей): [MISMATCH] / [ОШИБКА] — патч не действует (рестарт
    выкладки поднимет тот же exe, сверка площадок не пройдёт снова); [ВЫКЛ] при включённом в patches.ini или журнал не прочитан — по
    patches.ini с пометкой «установка не подтверждена». patches.ini не прочитан — исключение (вызывающий отказывает «не прочитан»)."""
    from domains import srvtables
    out = {}
    for g in E.GS:
        ini = srvtables._ini_first(srvtables.stack_text(g + "\\" + PATCHES, ttl=ttl))
        if not ini or "general" not in ini:
            raise ValueError("%s\\%s: секций нет" % (g, PATCHES))
        master = srvtables._ini_int(ini.get("general"), "MasterEnable", 0) != 0
        sec = ini.get(P40_SEC.lower())
        on = master and srvtables._ini_int(sec, "Enabled", 1) != 0
        cn, co = srvtables._ini_int(sec, "CheckNpc", 1) != 0, srvtables._ini_int(sec, "CheckOpenMap", 1) != 0
        if on and not (cn or co):
            on = False                                   # проверять нечего — Disabled (P40_CrystalTeleportGate)
        cr = parse_crystals(_ini_str(sec, "Crystals", P40_DEFAULT)) if cn else {}
        if on and cn and cr is None:
            on = False                                   # ключ не разобран — патч не ставится
        p30 = ini.get("p30_mapslots")
        p30_on = master and srvtables._ini_int(p30, "Enabled", 1) != 0
        slots = max(STOCK_SLOTS, min(srvtables._ini_int(p30, "MaxMaps", HARD_SLOTS), HARD_SLOTS)) if p30_on else STOCK_SLOTS
        p120 = master and srvtables._ini_int(ini.get("p120_minetravel"), "Enabled", 1) != 0
        notes, log_slots, p30_ok = [], None, False
        try:
            lg = patch_log(g, ttl=ttl)
        except Exception as ex:
            lg = None
            notes.append("%s: установка патчей не подтверждена (журнал патчей: %s) — P30 / P40 / P120 взяты по patches.ini" % (g, str(ex)[:120]))
        if lg is not None:
            want = {"p30": p30_on and slots > STOCK_SLOTS, "p40": on, "p120": p120}
            for k, sname in PATCH_SECS.items():
                stv = lg.get(sname)
                if not want[k]:
                    continue
                if stv == "bad":
                    notes.append("%s: %s при последнем запуске не встал ([MISMATCH] / [ОШИБКА] в журнале патчей) — не действует" % (g, sname))
                    if k == "p30":
                        slots = STOCK_SLOTS
                    elif k == "p40":
                        on = False
                    else:
                        p120 = False
                elif stv == "off":
                    notes.append("%s: %s включён в patches.ini, а при последнем запуске выключен — установка не подтверждена, взят по "
                                 "patches.ini" % (g, sname))
                elif stv != "ok":
                    notes.append("%s: %s включён в patches.ini, а в журнале последнего запуска его нет — установка не подтверждена, взят по "
                                 "patches.ini" % (g, sname))
            p30_ok, log_slots = lg.get("P30_MapSlots") == "ok", lg.get("slots")
        out[g] = {"p40": on and cn, "open_gate": on and co, "crystals": cr or {}, "slots": slots, "p120": p120, "p30_ok": p30_ok,
                  "log_slots": log_slots, "notes": notes}
    return out


def _cfg_notes(cfg, folders, rep, pats):
    """Пометки установки патчей (patch_cfg notes) копий folders, относящиеся к патчам pats («P30», «P40», «P120», «установка»), — в
    предупреждения позиции (без повторов)."""
    for g in folders:
        for n in cfg[g].get("notes") or []:
            if any(p in n for p in pats + ("установка патчей не подтверждена",)) and n not in rep["warnings"]:
                rep["warnings"].append(n)


def _cfg(ev):
    if "_map_cfg" not in ev.__dict__:
        try:
            ev.__dict__["_map_cfg"] = patch_cfg()
        except Exception as ex:
            ev.__dict__["_map_cfg"] = None
            ev.__dict__["_map_cfg_err"] = str(ex)[:160]
    return ev.__dict__["_map_cfg"]


UNREAD = "unreadable"     # ★ живой прогон 20.11: на службе файл, который держит работающий GameServer, md5f не читает (PermissionError)


def _extend(ev, rels):
    """md5 файлов в снимок оценки; файл, который не читается (держит процесс, права), — UNREAD, а не сбой всей оценки."""
    try:
        ev.snap.extend(rels)
        return
    except Exception:
        pass
    for r in rels:
        if r in ev.snap.md5:
            continue
        try:
            ev.snap.extend([r])
        except Exception:
            ev.snap.md5[r] = UNREAD


def _raw(ev, g, sub):
    """Байты таблицы копии; None — файла нет; UNREAD — есть, но не прочитан."""
    rel = g + "\\" + sub
    _extend(ev, [rel])
    h = ev.snap.md5.get(rel)
    if h in (None, "none"):
        return None
    if h != UNREAD:
        try:
            return ev.snap.raw(rel)
        except Exception:
            ev.snap.md5[rel] = UNREAD
    if sub in (MAPINFO, OPEN, THREAD, TOTAL, WARP):    # таблицы, без которых проверка не доказана, — отказ, а не «нет»
        raise OpRefused("на стойке %s\\%s не прочитан — вслепую не делается" % (g, sub))
    return UNREAD


def _has(ev, g, sub):
    """Файл копии есть на стойке (только md5, без чтения байтов); не читается — тоже «есть»."""
    rel = g + "\\" + sub
    _extend(ev, [rel])
    return ev.snap.md5.get(rel) not in (None, "none")


def _prefetch(ev, g, maps):
    """md5 файлов NPC и зон переходов всех карт копии — одним запросом (а не по файлу)."""
    _extend(ev, [g + "\\NpcData_Info\\%s.npc" % m["name"] for m in maps] + [g + "\\PortalIP_Info\\%s_PortalConfig.Ini" % m["name"] for m in maps])


def _maps(ev, g=None):
    key = "_map_info_" + (g or E.GS[0])
    if key not in ev.__dict__:
        raw = _raw(ev, g or E.GS[0], MAPINFO)
        if raw is None:
            raise OpRefused("на стойке нет %s\\%s" % (g or E.GS[0], MAPINFO))
        ev.__dict__[key] = mapinfo(raw)
    return ev.__dict__[key]


def _slots(cfg, g, nmaps):
    """Слотов OpenMapInfo копии g: P30 cap = min(MaxMaps, 30, nmaps), cap ≤ 23 — сток (p30_map_slots.cpp:185-230)."""
    s = cfg[g]["slots"]
    return min(s, nmaps) if s > STOCK_SLOTS and min(s, nmaps) > STOCK_SLOTS else STOCK_SLOTS


def declared_maps(raw):
    """Объявленное число карт MapInfo.txt — первое число файла (ReadMapInfoRows P30: fscanf %d; не число — −1)."""
    m = re.match(rb"\s*([+-]?\d+)", raw or b"")
    return int(m.group(1)) if m else -1


def _nmaps(ev, g):
    """★ ревизия 40 С-2: N MapInfo копии g, по которому P30 этой копии считает слоты (у каждой копии свой файл)."""
    key = "_map_n_" + g
    if key not in ev.__dict__:
        raw = _raw(ev, g, MAPINFO)
        ev.__dict__[key] = declared_maps(raw) if raw is not None else len(_maps(ev))
    return ev.__dict__[key]


def _sl(ev, cfg, g):
    return _slots(cfg, g, _nmaps(ev, g))


def _sl_safe(ev, cfg, g):
    """Для справки: MapInfo копии не прочитан — None, а не отказ всей справки."""
    try:
        return _sl(ev, cfg, g)
    except OpRefused:
        return None


def map_label(maps, mid):
    m = maps[mid] if 0 <= mid < len(maps) else None
    return "%s (%d)" % (m["name"], mid) if m else "карта %d" % mid


def crystal_routes(ev, g, fr, cfg):
    """Типы NPC на карте fr копии g, которые по ключу Crystals ведут куда-то → {куда: [типы]}."""
    maps = _maps(ev, g)
    if not 0 <= fr < len(maps):
        return {}
    raw = _raw(ev, g, "NpcData_Info\\%s.npc" % maps[fr]["name"])
    if raw == UNREAD:
        return None                                   # не прочитан — вызывающий не считает это «кристаллов нет»
    out = {}
    for t, _x, _z in npc_types(raw):
        for d in sorted(cfg[g]["crystals"].get(t, ())):
            out.setdefault(d, [])
            if t not in out[d]:
                out[d].append(t)
    return out


# =====================================================================================================================
# Клиент: кнопки кристаллов (подписи) и реестр карт порта
# =====================================================================================================================
def _read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def crystal_buttons():
    """Видимые кнопки кристаллов клиента: [[nsr, npcId, кнопка, подпись, карта]] — кнопка < MenuCount, команда 5477: 30031 (Param = строка
    WarpList, младший байт MapId) или ★ ревизия 40 Н-1 с картой в коде клиента (CRYSTAL_FIXED: 30037 Эллы → 5 и др.)."""
    if not all(os.path.isfile(p) for p in (NSR_BTN, NSR_HDR, WARPLIST)):
        return []
    hdr = {h["NsrName"]: h for h in _read_json(NSR_HDR)}
    wl = {int(w["ListIndex"]): int(w["MapId"]) & 0xFF for w in _read_json(WARPLIST)}
    out = []
    for b in _read_json(NSR_BTN):
        h = hdr.get(b.get("NsrName"))
        if not h or int(b.get("ButtonIndex", 99)) >= int(h.get("MenuCount") or 0):
            continue
        for s in b.get("Subs") or []:
            if not isinstance(s, dict):
                continue
            cmd = s.get("CmdCode")
            dest = (wl.get(int(s.get("Param", -1))) if cmd == CRYSTAL_CMD else CRYSTAL_FIXED.get(cmd))
            if dest is not None:
                out.append([b["NsrName"], int(h.get("NpcId") or -1), int(b["ButtonIndex"]), b.get("Caption") or "", dest])
                break
    return out


def registry_open():
    """{карта: server.open_use} реестра карт порта."""
    if not os.path.isfile(REG_JSON):
        return {}
    reg = _read_json(REG_JSON)
    return {int(m["id"]): (m.get("server") or {}).get("open_use") for m in reg.get("maps") or []}


def snapshot(snap):
    snap["crystals"] = crystal_buttons()
    snap["mapreg"] = {str(k): v for k, v in registry_open().items()}


def parse(cli, d):
    cli.crystals = [list(x) for x in d.get("crystals") or []]
    cli.mapreg = {int(k): v for k, v in (d.get("mapreg") or {}).items()}


# =====================================================================================================================
# warp.cost
# =====================================================================================================================
def k_warp_cost(ev, p, rep):
    fr, to, val = p["from"], p["to"], p["cost"]
    maps = _maps(ev)
    if not (fr < len(maps) and to < len(maps)):
        raise OpRefused("карты %d нет в MapInfo.txt (карт %d) — RecvContinent_PortalMove берёт только номер меньше числа карт"
                        % (max(fr, to), len(maps)))
    olds = {}
    for g in E.GS:                                   # сначала проверка ВСЕХ копий — отказ до первой записи
        t = ev.st.get(g, WARP)
        n, rows = warp_rows(t, g)
        if not (fr < n and to < n):
            raise OpRefused("%s %s: матрица %d×%d, ячейки [%d][%d] нет — в А4 только правка существующих" % (WARP, g, n, n, fr, to))
        olds[g] = warp_get(t, rows, fr, to)
    base = olds[E.GS[0]]
    for g in E.GS[1:]:
        if olds[g] != base:
            raise OpRefused("копия %s: цена [%d][%d] = %d, а в GameServer %d — отличия копии не затираются, правка не делается"
                            % (g, fr, to, olds[g], base))
    if val == base:
        raise OpRefused("у перехода %s → %s цена уже %d — менять нечего" % (map_label(maps, fr), map_label(maps, to), val))
    cfg = _cfg(ev)
    if cfg is None:
        raise OpRefused("patches.ini стойки не прочитан (%s) — гейт кристаллов P40 неизвестен, вслепую не делается"
                        % ev.__dict__.get("_map_cfg_err", "?"))
    honest, deaf = {}, []
    for g in E.GS:
        cr = crystal_routes(ev, g, fr, cfg)
        if cr is None:
            raise OpRefused("копия %s: NpcData_Info\\%s.npc не прочитан — кристаллы карты %s неизвестны, вслепую не делается"
                            % (g, maps[fr]["name"], map_label(maps, fr)))
        r = cr.get(to)
        if r:
            honest[g] = r
        elif cfg[g]["p40"]:
            deaf.append(g)
    if len(deaf) == len(E.GS):
        raise OpRefused("у карты %s нет NPC, которому ключ Crystals P40 разрешает вести на %s (ни в одной копии) — P40 пропускает 5477 "
                        "только у такого NPC, цена не подействует, правка не делается" % (map_label(maps, fr), map_label(maps, to)))
    if not honest:
        rep["warnings"].append("маршрута у кристаллов нет: цену возьмёт только переход, который P40 пропускает (P40 выключен в %s) — честный "
                               "клиент так не ходит" % ", ".join(g for g in E.GS if not cfg[g]["p40"]))
    elif deaf:
        rep["warnings"].append("в копиях %s маршрута у кристаллов нет — там правка не подействует" % ", ".join(deaf))
    grp = maps[fr]["group"]
    if val > 0 and grp <= 2:
        rep["warnings"].append("игроки фракции-владельца города (группа %d карты %s) платят 0 — скидка RecvContinent_PortalMove"
                               % (grp, map_label(maps, fr)))
    _cfg_notes(cfg, E.GS, rep, ("P40",))
    no_tot = []                                      # ★ ревизия 40, мелочь 5: прибытие и «закрыта» — по КАЖДОЙ копии (у Indun свой Total)
    for g in E.GS:
        tot = _raw(ev, g, TOTAL)
        tr = total_state(tot).get(to) if tot is not None else None
        if not (tr and tr["use"]):
            no_tot.append(g)
    if val >= 0 and no_tot:
        rep["warnings"].append("у карты %s нет записи Total_PortalConfig с USE ≠ 0 (%s) — переход 5477 сервер молча отклонит при любой цене"
                               % (map_label(maps, to), ", ".join(no_tot)))
    shut = []
    for g in (x for x in E.folders("GSF") if cfg[x]["open_gate"]):
        oraw = _raw(ev, g, OPEN)
        ou = open_state(oraw, _sl(ev, cfg, g))["use"] if oraw is not None else {}
        if not ou.get(to):
            shut.append(g)
    if val >= 0 and shut:
        rep["warnings"].append("карта %s закрыта в OpenMapInfo.ini (%s) — P40 (CheckOpenMap) откажет в переходе при любой цене"
                               % (map_label(maps, to), ", ".join(shut)))
    for g in E.GS:
        warp_set(ev.st.get(g, WARP), warp_rows(ev.st.get(g, WARP), g)[1], fr, to, val)
    caps = [b for b in getattr(ev.cli, "crystals", []) or [] if b[4] == to and any(b[1] in v for v in honest.values())]
    for nsr, _npc, btn, cap, _d in caps:
        if base > 0 and str(base) in re.findall(r"\d+", cap):
            rep["warnings"].append("подпись кнопки кристалла %s кн.%d «%s» показывает прежнюю цену %d — клиент цену не пересчитывает, подпись "
                                   "(NSR) панель не правит" % (nsr, btn, cap, base))
    kind = "type" if (base < 0) != (val < 0) else "value"
    what = "телепорт %s → %s: цена" % (map_label(maps, fr), map_label(maps, to))
    if honest:
        rep["text"] = "телепорт кристаллом %s → %s: цена %d → %d (сервер MapWarpCost.txt ×%d GS, кристаллы: NPC %s)" % (
            map_label(maps, fr), map_label(maps, to), base, val, len(E.GS), ", ".join(str(x) for x in sorted({x for v in honest.values() for x in v})))
    else:
        rep["text"] = "телепорт кристаллом %s → %s: цена %d → %d (сервер MapWarpCost.txt ×%d GS)" % (
            map_label(maps, fr), map_label(maps, to), base, val, len(E.GS))
    rep["_balance"] = [{"what": what, "old": base, "new": val, "codes": [], "kind": kind}]


# =====================================================================================================================
# map.open
# =====================================================================================================================
RELOG_TABLE = "dbo.AsdaDungeonRelogPoint"            # P108 SQL (AstoryServer/SQL/dungeon_relog_fix_20261105.sql)


def joy_holders(mids):
    """{карта: [(учётка, персонаж, имя, где)]} — кто войдёт в мир на картах mids или возродится там → или None (причина — last_error):
    CharPos.Poridx (по нему LoginManager выбирает Game_<карта>) и VillagePos.Villageidx; ★ ревизия 40 В-2:
      * CharPos.Poridx 19/20/22 — LoginManager берёт карту из Charinpos.Poridx (UPCharDetailPos, LM.c:4286-4311), строки нет — карта 0
        (дефект оригинала @Poridx IS NULL → 0);
      * P108: restart_stack шаг 4б2 (UP_AsdaDungeonRelogReset — ПОСЛЕ перепроверки выкладчика) ставит «бывшим в игре» (Usernum ≠ −1 или
        State 1) на турнирной Cporidx Poridx карты выхода AsdaDungeonRelogPoint Kind 'R'; таблицы нет — пропуск, пометка в notes;
    в т. ч. невосстановленные наборы корзины (Del_CharPos / Del_VillagePos без adm.CharRestored: adm.CharRestore возвращает их как есть)."""
    joy_holders.last_error, joy_holders.notes = None, []
    ids = sorted({int(m) for m in mids})
    if not ids:
        return {}
    marks = ", ".join(str(m) for m in ids)
    via = ", ".join(str(m) for m in CHARINPOS_MAPS)
    nr = ("NOT EXISTS (SELECT 1 FROM adm.CharRestored r WHERE r.Userindex = d.Userindex AND r.Charidx = d.Charidx AND r.Edate = d.Edate)")
    try:
        from core import db
        with db.GameReader("joy1") as j:
            pos = j.rows("SELECT Userindex AS u, Charidx AS c, Charname AS nm, Poridx AS m FROM dbo.CharPos WHERE Poridx IN (%s)" % marks)
            vil = j.rows("SELECT v.Userindex AS u, v.Charidx AS c, p.Charname AS nm, v.Villageidx AS m FROM dbo.VillagePos v LEFT JOIN dbo.CharPos p "
                         "ON p.Userindex = v.Userindex AND p.Charidx = v.Charidx WHERE v.Villageidx IN (%s)" % marks)
            dpos = j.rows("SELECT d.Userindex AS u, d.Charidx AS c, d.Charname AS nm, d.Poridx AS m, CONVERT(varchar(16), d.Edate, 121) AS ek "
                          "FROM dbo.Del_CharPos d WHERE d.Poridx IN (%s) AND %s" % (marks, nr))
            dvil = j.rows("SELECT d.Userindex AS u, d.Charidx AS c, d.Villageidx AS m, CONVERT(varchar(16), d.Edate, 121) AS ek "
                          "FROM dbo.Del_VillagePos d WHERE d.Villageidx IN (%s) AND %s" % (marks, nr))
            cin = j.rows("SELECT p.Userindex AS u, p.Charidx AS c, p.Charname AS nm, p.Poridx AS v, ISNULL(ci.Poridx, 0) AS m FROM dbo.CharPos p "
                         "LEFT JOIN dbo.Charinpos ci ON ci.Userindex = p.Userindex AND ci.Charidx = p.Charidx "
                         "WHERE p.Poridx IN (%s) AND ISNULL(ci.Poridx, 0) IN (%s)" % (via, marks))
            dcin = j.rows("SELECT d.Userindex AS u, d.Charidx AS c, d.Charname AS nm, d.Poridx AS v, ISNULL(ci.Poridx, 0) AS m, "
                          "CONVERT(varchar(16), d.Edate, 121) AS ek FROM dbo.Del_CharPos d LEFT JOIN dbo.Charinpos ci ON ci.Userindex = d.Userindex "
                          "AND ci.Charidx = d.Charidx WHERE d.Poridx IN (%s) AND ISNULL(ci.Poridx, 0) IN (%s) AND %s" % (via, marks, nr))
            rel, drel = [], []
            if (j.rows("SELECT OBJECT_ID('%s', 'U') AS o" % RELOG_TABLE) or [{}])[0].get("o") is None:
                joy_holders.notes.append("таблицы %s нет (SQL P108 не применён) — перенос с турнирных карт шагом 4б2 рестарта не учтён, "
                                         "его и не будет" % RELOG_TABLE)
            else:
                rel = j.rows("SELECT p.Userindex AS u, p.Charidx AS c, p.Charname AS nm, p.Cporidx AS v, rp.Poridx AS m FROM dbo.CharPos p "
                             "INNER JOIN %s rp ON rp.Kind = 'R' AND rp.Mapidx = p.Cporidx WHERE (p.Usernum <> -1 OR p.State = 1) "
                             "AND rp.Poridx IN (%s)" % (RELOG_TABLE, marks))
                drel = j.rows("SELECT d.Userindex AS u, d.Charidx AS c, d.Charname AS nm, d.Cporidx AS v, rp.Poridx AS m, "
                              "CONVERT(varchar(16), d.Edate, 121) AS ek FROM dbo.Del_CharPos d INNER JOIN %s rp ON rp.Kind = 'R' "
                              "AND rp.Mapidx = d.Cporidx WHERE (d.Usernum <> -1 OR d.State = 1) AND rp.Poridx IN (%s) AND %s"
                              % (RELOG_TABLE, marks, nr))
    except Exception as ex:
        joy_holders.last_error = str(ex)[:200]
        return None
    out = {m: [] for m in ids}
    for r in pos:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), r["nm"] or "?", "CharPos"))
    for r in vil:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), r["nm"] or "?", "VillagePos"))
    for r in dpos:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), "%s [Del_CharPos %s]" % (r["nm"] or "?", r["ek"]), "Del_CharPos"))
    for r in dvil:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), "[Del_VillagePos %s]" % r["ek"], "Del_VillagePos"))
    for r in cin:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), r["nm"] or "?", "Charinpos (CharPos.Poridx %d)" % int(r["v"])))
    for r in dcin:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), "%s [Del_CharPos %s]" % (r["nm"] or "?", r["ek"]),
                                 "Charinpos (Del_CharPos.Poridx %d)" % int(r["v"])))
    for r in rel:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), r["nm"] or "?", "P108 4б2 (Cporidx %d)" % int(r["v"])))
    for r in drel:
        out[int(r["m"])].append((int(r["u"]), int(r["c"]), "%s [Del_CharPos %s]" % (r["nm"] or "?", r["ek"]),
                                 "P108 4б2 (Del_CharPos.Cporidx %d)" % int(r["v"])))
    return out


joy_holders.last_error, joy_holders.notes = None, []


def lm_game_maps(ttl=60):
    """★ ревизия 40, мелочь 4: карты, адрес которых LoginManager загружает (sub_4046E0, LM.c:1486-1520): GameServerIP.ini
    [SERVERGROUP_TOTAL] COUNT, [SERVERGROUP_<g>_CHANNEL_TOTAL] COUNT / GAMECOUNT, <g>_<ch>_ServerIP.ini [Game_<j>] IP — j < GAMECOUNT,
    до первого пустого IP → {"<g>_<ch>": {карты}} или None (не прочитано — last_error)."""
    from domains import srvtables
    lm_game_maps.last_error = None
    try:
        top = srvtables._ini_first(srvtables.stack_text(LM_DIR + "\\GameServerIP.ini", ttl=ttl))
        out = {}
        for grp in range(srvtables._ini_int(top.get("servergroup_total"), "COUNT", 0)):
            sec = top.get("servergroup_%d_channel_total" % grp)
            for ch in range(srvtables._ini_int(sec, "COUNT", 0)):
                ini = srvtables._ini_first(srvtables.stack_text(LM_DIR + "\\%d_%d_ServerIP.ini" % (grp, ch), ttl=ttl))
                got = set()
                for k in range(srvtables._ini_int(sec, "GAMECOUNT", 0)):
                    if not _ini_str(ini.get("game_%d" % k), "IP", ""):
                        break
                    got.add(k)
                out["%d_%d" % (grp, ch)] = got
        return out
    except Exception as ex:
        lm_game_maps.last_error = str(ex)[:160]
        return None


lm_game_maps.last_error = None


def _who_err(lst):
    """Список для ОТКАЗА (через запятую — без «; »)."""
    return ", ".join("%s (%d/%d, %s)" % (x[2], x[0], x[1], x[3]) for x in lst[:10]) + (" +%d" % (len(lst) - 10) if len(lst) > 10 else "")


NEW_CHAR_MAP = 3          # UPCreateChar: карта 3, клетка 0,0 (LoginManager → старт MapInfo Альпии); charLogOnRes без строки VillagePos — 3
                          # (domains/charmove.py NEW_POS / VILLAGE_DEFAULT, research_char_move.md) — будущие держатели карты 3 есть всегда


def block_close(hold, mid, maps):
    if mid == NEW_CHAR_MAP:
        return ("на карте %s создаются новые персонажи (UPCreateChar) и возрождаются персонажи без строки VillagePos (charLogOnRes) — без потока "
                "карты их вход в мир не состоится, правка не делается" % map_label(maps, mid))
    lst = (hold or {}).get(mid) or []
    if lst:
        return ("на карте %s стоят или возрождаются %d перс. (%s) — без потока карты их вход в мир не состоится (SearchThreadInfo вернёт 3), "
                "правка не делается — сначала перенесите их (карточка игрока, «вытащить застрявшего»)" % (map_label(maps, mid), len(lst), _who_err(lst)))
    return None


def k_map_open(ev, p, rep):
    mid, val = p["map"], p["use"]
    maps = _maps(ev)
    if mid >= len(maps):
        raise OpRefused("карты %d нет в MapInfo.txt (карт %d) — в А4 только правка существующих" % (mid, len(maps)))
    cfg = _cfg(ev)
    if cfg is None:
        raise OpRefused("patches.ini стойки не прочитан (%s) — число слотов карт (P30) и P120 неизвестны, вслепую не делается"
                        % ev.__dict__.get("_map_cfg_err", "?"))
    typ = maps[mid]["type"]
    fold = E.folders("GSF")
    if typ == 6:
        off = [g for g in fold if not cfg[g]["p120"]]
        if off:
            raise OpRefused("карта %s типа 6: поток ей даёт только P120 (площадка A), а в %s он не ставится — правка не подействует"
                            % (map_label(maps, mid), ", ".join(off)))
    elif typ not in THREAD_TYPES:
        raise OpRefused("карта %s типа %d (%s): поток по OpenMapInfo сервер даёт только типам 0/1/3 (SetUserInfo_ThreadID_Mapping) — смысл Use "
                        "у этого типа не подтверждён, правка не делается" % (map_label(maps, mid), typ, TYPE_NAMES.get(typ, "?")))
    olds, lines = {}, {}
    for g in fold:
        sl = _sl(ev, cfg, g)
        if mid >= sl:
            raise OpRefused("%s: сервер читает секции MAP_0…MAP_%d (слотов %d, P30) — секция карты %d не действует, правка не делается"
                            % (g, sl - 1, sl, mid))
        t = ev.st.get(g, OPEN)
        st = open_state(t.data(), sl)
        if st["count"] == 0:
            raise OpRefused("%s %s: MapCount = 0 — сервер файл не применяет (byte_5F5EF6 = 0), правка не подействует" % (OPEN, g))
        if mid not in st["line"]:
            raise OpRefused("%s %s: у секции MAP_%d нет строки Use — в А4 только правка существующих" % (OPEN, g, mid))
        if not re.match(rb"^(\s*[^=]*=\s*)([+-]?\d+)", t.lines[st["line"][mid]]):
            raise OpRefused("%s: строка Use «%s» — не число, правка не делается" % (OPEN, t.lines[st["line"][mid]].decode("latin-1")[:40]))
        olds[g], lines[g] = st["use"][mid], st["line"][mid]
    base = olds[fold[0]]
    if any(v != base for v in olds.values()):
        raise OpRefused("Use карты %d в копиях поля разный (%s) — отличия копии не затираются, правка не делается"
                        % (mid, ", ".join("%s %d" % kv for kv in sorted(olds.items()))))
    if val == base:
        raise OpRefused(("карта %s уже открыта — менять нечего" if val else "карта %s уже закрыта — менять нечего") % map_label(maps, mid))
    _cfg_notes(cfg, fold, rep, ("P30", "P120") if typ == 6 else ("P30",))
    if mid >= STOCK_SLOTS:                           # ★ ревизия 40 С-2: секция ≥ 23 действует только при вставшем P30
        unc = [g for g in fold if not cfg[g].get("p30_ok")]
        if unc:
            rep["warnings"].append("секцию MAP_%d сервер читает только при P30, а его установка в %s журналом патчей не подтверждена — правка "
                                   "может не подействовать" % (mid, ", ".join(unc)))
    name = maps[mid]["name"]
    if val:
        for g in fold:
            if not _has(ev, g, "MapData_Info\\%s.sim" % name):
                raise OpRefused("%s: нет MapData_Info\\%s.sim — поток карты его загружает (sub_419E50), правка не делается" % (g, name))
            nr = _raw(ev, g, "NpcData_Info\\%s.npc" % name)
            if nr == UNREAD:
                rep["warnings"].append("%s: NpcData_Info\\%s.npc не прочитан (файл держит процесс) — NPC карты не проверены" % (g, name))
            elif not npc_types(nr):
                rep["warnings"].append("%s: NpcData_Info\\%s.npc нет или пуст — NPC на карте не будет" % (g, name))
        lm = lm_game_maps()
        if lm is None:
            rep["warnings"].append("адреса Game_<n> LoginManager не прочитаны (%s) — вход в мир по карте %s не проверен"
                                   % (lm_game_maps.last_error or "?", map_label(maps, mid)))
        elif lm and not all(mid in s for s in lm.values()):
            rep["warnings"].append("у LoginManager нет адреса Game_%d (%s) — персонаж, сохранённый на карте %s, в мир не войдёт, попасть на "
                                   "неё можно только переходом" % (mid, ", ".join(sorted(k for k, s in lm.items() if mid not in s)),
                                                                    map_label(maps, mid)))
    else:
        hold = joy_holders([mid])
        if hold is None:
            raise OpRefused("карта %s: персонажи не прочитаны (%s) — вслепую не делается" % (map_label(maps, mid), joy_holders.last_error or NO_JOY1))
        for n in getattr(joy_holders, "notes", None) or []:
            rep["warnings"].append(n)
        why = block_close(hold, mid, maps)
        if why:
            raise OpRefused(why)
    for g in fold:                                   # ★ ревизия 40 С-1: запись — только после ВСЕХ отказов (Eval.run запись не откатывает)
        set_ini_use(ev.st.get(g, OPEN), lines[g], val)
    inb = []
    _prefetch(ev, E.GS[0], maps)
    for k, m in enumerate(maps):
        zr = _raw(ev, E.GS[0], "PortalIP_Info\\%s_PortalConfig.Ini" % m["name"])
        for z in zones_state(zr) if zr is not None else []:
            if z["to"] == mid and k != mid:
                inb.append("%s зона %d" % (m["name"], z["k"]))
    cry = sorted({k for k in range(len(maps)) if k != mid and (crystal_routes(ev, E.GS[0], k, cfg) or {}).get(mid)})   # md5 .npc — уже в _prefetch; не прочитан — только справка
    if val:
        if not inb and not cry:
            rep["warnings"].append("на карту %s не ведёт ни один напольный портал и ни один кристалл — открытая, но попасть на неё можно только "
                                   "GM-прыжком (P123) или переносом персонажа" % map_label(maps, mid))
    elif inb or cry:
        rep["warnings"].append("на закрытую карту %s перестанут вести: %s — напольный портал (sub_52C4C0) молчит, кристалл откажет P40"
                               % (map_label(maps, mid), "; ".join(inb + ["кристалл с карты %s" % map_label(maps, k) for k in cry])))   # «; » — перевод каждой части
    reg = getattr(ev.cli, "mapreg", {}) or {}
    rv = reg.get(mid)
    if rv != val:
        rep["client"] = [{"type": "map_open", "file": AREA, "src": AREA, "map": mid, "old": rv, "new": val, "optional": True}]
        ev.client += rep["client"]
        rep["warnings"].append("реестр карт порта (маршруты трекера и автопути) получит open_use %d клиентской половиной — нужна полная сборка "
                               "C++ выпуска (AsdaMapRegistry.h), серверу клиент не нужен" % val)
    rep["text"] = (("карта %s (тип %d): открыть (сервер OpenMapInfo.ini ×%d — %s)" if val else
                    "карта %s (тип %d): закрыть (сервер OpenMapInfo.ini ×%d — %s)") % (map_label(maps, mid), typ, len(fold), ", ".join(fold)))
    rep["_balance"] = [{"what": "карта %s: открыта" % map_label(maps, mid), "old": base, "new": val, "codes": [], "kind": "type"}]


# =====================================================================================================================
# Итог набора, перепроверка перед выкладкой и откатом
# =====================================================================================================================
def _touched(ev, kind):
    out = {}
    for r in ev.positions:
        if r["kind"] == kind and not r["errors"] and isinstance(r.get("params"), dict):
            try:
                out.setdefault(int(r["params"]["map"]), []).append(r)
            except (KeyError, TypeError, ValueError):
                continue
    return out


def open_count(raw, thr_raw, slots):
    """(открытых карт — все типы, Use ≠ 0, секции < slots, 0 — если файл не действует (MapCount-байт 0); ThreadInfo COUNT)."""
    st = open_state(raw, slots)
    cnt = sum(1 for v in st["use"].values() if v) if st["count"] else 0
    th = ini_int(ini_sections(thr_raw).get("max_init_thread"), "count", 0) if thr_raw is not None else 0
    return cnt, th


def open_count_issue(raw, thr_raw, slots, g, base_raw=None):
    """Число открытых против ThreadInfo COUNT → текст неисправности или None (загрузчик :64910). ★ ревизия 40, мелочь 2 — одно правило
    для after_run и apply_guard: с base_raw неисправность — только НОВАЯ или ХУЖЕ базы (открытых больше COUNT и больше, чем в базе)."""
    cnt, th = open_count(raw, thr_raw, slots)
    if th >= cnt or (base_raw is not None and cnt <= open_count(base_raw, thr_raw, slots)[0]):
        return None
    return "копия %s: открытых карт %d больше ThreadInfo.ini COUNT %d — GameServer выйдет при старте (exit(1), GameServer.c:64912)" % (g, cnt, th)


def after_run(ev):
    """По ИТОГОВОМУ состоянию набора (порядок позиций не важен): в каждой копии поля число открытых карт не больше COUNT ThreadInfo (новой
    неисправности относительно базы копии быть не должно)."""
    tr = _touched(ev, "map.open")
    if not tr:
        return
    cfg = _cfg(ev)
    if cfg is None:
        return
    bad = []
    for g in E.folders("GSF"):
        t = ev.st.get(g, OPEN)
        try:
            sl = _sl(ev, cfg, g)
            thr = _raw(ev, g, THREAD)
        except OpRefused as ex:                       # не прочитан — отказ позиций открытия, а не сбой оценки
            bad.append(str(ex))
            continue
        now = open_count_issue(t.data(), thr, sl, g, base_raw=ev.snap.raw(t.rel))
        if now:
            bad.append(now)
    for rs in tr.values():
        for r in rs:
            if r["params"].get("use") == 1:
                r["errors"] += [b for b in bad if b not in r["errors"]]


def _guard_rels():
    return [E.rel_of(g, OPEN) for g in E.folders("GSF")]


def _guard_state(cs, mode):
    """OpenMapInfo копий поля, каким он СТАНЕТ (apply — живой + файлы ЭТОГО набора из манифеста, md5 = утверждённому; rollback — живой,
    файлы набора — базой: живая = база или .bak_<метка> = база) и какой он сейчас → ({путь: байты}, {путь: байты}). Не сходится —
    исключение (у вызывающего «не прочитаны» → отказ). Та же схема, что skilldata._guard_state, — для своих путей."""
    rels = _guard_rels()
    files = {}
    for f in ((cs.get("check") or {}).get("server") or {}).get("files") or []:
        for g in f["gs"]:
            files[E.rel_of(g, f["table"])] = (f["base"], f["new"])
    man = None
    if any(r in files for r in rels) and cs.get("id") is not None:
        from domains import shopcs
        mp = shopcs.manifest_path(cs["id"])
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                man = json.load(fh)
    tag = (man or {}).get("tag") or cs.get("server_tag")
    baks = {r: r + ".bak_" + tag for r in rels if r in files} if mode == "rollback" and tag else {}
    md5 = E.live_md5(rels + list(baks.values()))
    sn = E.Snap(dict(md5))
    now, after = {}, {}
    for r in rels:
        now[r] = sn.raw(r)
        if r not in files:
            after[r] = now[r]
            continue
        base, new = files[r]
        if mode == "apply":
            if md5.get(r) == new:
                after[r] = now[r]
            elif md5.get(r) == base:
                lp = (((man or {}).get("files") or {}).get(r) or {}).get("local")
                if not lp or not os.path.isfile(lp):
                    raise RuntimeError("нет файла набора %s — сначала changeset server-dry" % r)
                with open(lp, "rb") as fh:
                    b = fh.read()
                if E.md5b(b) != new:
                    raise RuntimeError("файл набора %s ≠ утверждённому — повторите server-dry" % r)
                after[r] = b
            else:
                raise RuntimeError("%s на стойке — не база и не файл набора" % r)
        elif md5.get(r) == base:
            after[r] = now[r]
        elif r in baks and md5.get(baks[r]) == base:
            after[r] = sn.raw(baks[r])
        else:
            raise RuntimeError("%s: базы набора нет ни на месте, ни в .bak" % r)
    return after, now


def apply_guard(cs, mode):
    """Перед выкладкой (apply) и откатом (rollback) сервера: карты, которые станут закрытыми, — персонажи на них ПЕРЕЧИТЫВАЮТСЯ (Joy1),
    открытые — против живого ThreadInfo COUNT → [причины]. Не прочитано — причина с «не прочитаны»."""
    mids = set()
    for it in cs.get("items") or []:
        if it["kind"] == "map.open":
            try:
                mids.add(int((it.get("params") or {})["map"]))
            except (KeyError, TypeError, ValueError):
                pass
    if not mids:
        return []
    try:
        after, now = _guard_state(cs, mode)
        cfg = patch_cfg(ttl=0)
        rel_mi = {g: E.rel_of(g, MAPINFO) for g in E.GS}
        rel_th = [E.rel_of(g, THREAD) for g in E.folders("GSF")]
        sn = E.Snap(dict(E.live_md5(list(rel_mi.values()) + rel_th)))
        maps = mapinfo(sn.raw(rel_mi[E.GS[0]]))
        nmaps = {g: declared_maps(sn.raw(rel_mi[g])) for g in E.folders("GSF")}   # ★ ревизия 40 С-2: N MapInfo каждой копии (P30)
    except Exception as ex:
        return ["карты: таблицы стойки не прочитаны (%s) — вслепую не делается" % str(ex)[:160]]
    out, closing = [], set()
    for g in E.folders("GSF"):
        r = E.rel_of(g, OPEN)
        sl = _slots(cfg, g, nmaps[g])
        a, n = open_state(after[r], sl)["use"], open_state(now[r], sl)["use"]
        closing |= {m for m in mids if n.get(m) and not a.get(m)}
        thr = sn.raw(E.rel_of(g, THREAD)) if sn.md5.get(E.rel_of(g, THREAD)) not in (None, "none") else None
        w = open_count_issue(after[r], thr, sl, g, base_raw=now[r])       # ★ ревизия 40, мелочь 2: как after_run — новая или хуже
        if w:
            out.append(w)
    if closing:
        hold = joy_holders(closing)
        if hold is None:
            return out + ["карты: персонажи не прочитаны (%s) — вслепую не делается" % (joy_holders.last_error or NO_JOY1)]
        out += [w for w in (block_close(hold, m, maps) for m in sorted(closing)) if w]
    return out


# =====================================================================================================================
# Клиентская половина (ПК): реестр карт порта → AsdaMapRegistry.h рендером НАСТОЯЩЕГО asda_map_registry
# =====================================================================================================================
def _tool():
    config.port_code(E.UE_TOOLS)          # ★ ревизия 56 С-1: только ПК
    if E.UE_TOOLS not in sys.path:
        sys.path.insert(0, E.UE_TOOLS)
    import asda_map_registry as MR        # noqa: E402 — без побочных эффектов при импорте (закон tools-no-import-side-effects)
    return MR


def allowed_extra(ap):
    return ap in {os.path.normcase(os.path.abspath(x)) for x in (REG_JSON, REG_H)}


def plan(pc):
    """server.open_use карты в реестре (точечно в тексте; JSON отличается только этим полем) и AsdaMapRegistry.h = рендер НАСТОЯЩЕГО
    asda_map_registry.render_cpp_header нового реестра. Сторож: текущий заголовок = рендеру текущего реестра (иначе «мимо реестра»)."""
    edits = pc["by_file"].get(AREA, [])
    if not edits:
        return
    err = pc["errors"]
    MR = _tool()
    rc = pc["load"]("txt:map_reg", REG_JSON)
    hc = pc["load"]("txt:map_reg_h", REG_H)
    if rc[0] is None or hc[0] is None:
        return err.append("реестр карт порта или AsdaMapRegistry.h не найдены — клиентская половина не собирается")
    if MR.render_cpp_header(json.loads(rc[0].decode("utf-8-sig"))) != hc[0]:
        return err.append("AsdaMapRegistry.h ≠ рендеру реестра карт (asda_map_registry) — заголовок правили мимо реестра, разберите до правки")
    t = rc[1].decode("utf-8")
    want = json.loads(t.lstrip("﻿"))
    for e in edits:
        mid = int(e["map"])
        m = re.search(r'\n(\s*)\{\s*"id":\s*%d,' % mid, t)
        if not m:
            return err.append("реестр карт: записи карты %d не найдено" % mid)
        end = t.find("\n" + m.group(1) + "}", m.end())
        s = t.find('"server":', m.end(), end if end > 0 else len(t))
        old_j = '"open_use": ' + json.dumps(e["old"])
        at = t.find(old_j, s, end if end > 0 else len(t)) if s >= 0 else -1
        if at < 0:
            return err.append("реестр карт: у карты %d server.open_use не %s — пересоберите набор" % (mid, json.dumps(e["old"])))
        t = t[:at] + '"open_use": ' + json.dumps(int(e["new"])) + t[at + len(old_j):]
        for mm in want["maps"]:
            if mm["id"] == mid:
                mm["server"]["open_use"] = int(e["new"])
    reg2 = json.loads(t.lstrip("﻿"))
    if reg2 != want:
        return err.append("реестр карт: правка задела не только server.open_use — отказ")
    rc[1] = t.encode("utf-8")
    hc[1] = MR.render_cpp_header(reg2)
    pc["warnings"].append("AsdaMapRegistry.h изменится (kServerMapOpen и пометки рёбер kPortalGraph) — нужна полная сборка C++ выпуска")


# =====================================================================================================================
# Справка редактору (только чтение) и расхождения
# =====================================================================================================================
def _ref():
    rels = [E.rel_of(g, x) for g in E.GS for x in (MAPINFO, WARP, THREAD, TOTAL)] + [E.rel_of(g, OPEN) for g in E.folders("GSF")]
    md5 = E.live_md5(rels)
    ev = E.Eval([], False, E.Snap(md5))
    return ev


def _warp_all(ev):
    out = {}
    for g in E.GS:
        try:
            out[g] = warp_matrix(ev.snap.raw(E.rel_of(g, WARP)), g)
        except OpRefused:
            out[g] = None
    return out


def lookup_maps(ev=None):
    ev = ev or _ref()
    maps = _maps(ev)
    try:
        cfg = patch_cfg()
        cfg_err = None
    except Exception as ex:
        cfg, cfg_err = None, str(ex)[:160]
    rows, field, errs = [], {}, []                   # ★ ревизия 40, мелочь 6: таблица не читается — справка частично, причина в read_errors
    for g in E.folders("GSF"):
        try:
            raw = _raw(ev, g, OPEN)
            sl = _sl(ev, cfg, g) if cfg else STOCK_SLOTS
            field[g] = open_state(raw, sl) if raw is not None else None
        except OpRefused as ex:
            field[g] = None
            errs.append(str(ex))
    try:
        tot = total_state(_raw(ev, E.GS[0], TOTAL) or b"")
    except OpRefused as ex:
        tot = {}
        errs.append(str(ex))
    reg = getattr(ev.cli, "mapreg", {}) or {}
    thr = {}
    for g in E.folders("GSF"):
        try:
            tr = _raw(ev, g, THREAD)
            thr[g] = ini_int(ini_sections(tr).get("max_init_thread"), "count", 0) if tr is not None else None
        except OpRefused as ex:
            thr[g] = None
            errs.append(str(ex))
    for m in maps:
        use = {g: (s["use"].get(m["id"]) if s else None) for g, s in field.items()}
        rows.append({"id": m["id"], "name": m["name"], "type": m["type"], "type_name": TYPE_NAMES.get(m["type"], "?"), "users": m["users"],
                     "town": m["town"], "group": m["group"], "use": use, "registry": reg.get(m["id"]),
                     "total": tot.get(m["id"]), "points": m["points"],
                     "editable": m["type"] in THREAD_TYPES or m["type"] == 6})
    opened = {g: (sum(1 for v in s["use"].values() if v) if s else None) for g, s in field.items()}
    from core import i18n
    return {"rows": rows, "threads": thr, "opened": opened, "cfg_error": cfg_err, "read_errors": [i18n.tr(x) for x in errs],
            "p40": {g: v["p40"] for g, v in cfg.items()} if cfg else None,
            "slots": {g: _sl_safe(ev, cfg, g) for g in cfg} if cfg else None,
            "patch_notes": [i18n.tr(n) for v in (cfg or {}).values() for n in v.get("notes") or []]}


def lookup_map(mid):
    from core import i18n
    ev = _ref()
    maps = _maps(ev)
    if not 0 <= mid < len(maps):
        raise OpRefused("карты %d нет в MapInfo.txt (карт %d)" % (mid, len(maps)))
    base = lookup_maps(ev)
    row = base["rows"][mid]
    zr = _raw(ev, E.GS[0], "PortalIP_Info\\%s_PortalConfig.Ini" % maps[mid]["name"])
    out_z = [dict(z, to_name=map_label(maps, z["to"])) for z in (zones_state(zr) if zr is not None else [])]
    inb = []
    _prefetch(ev, E.GS[0], maps)
    for k, m in enumerate(maps):
        if k == mid:
            continue
        r = _raw(ev, E.GS[0], "PortalIP_Info\\%s_PortalConfig.Ini" % m["name"])
        inb += [dict(z, frm=k, frm_name=map_label(maps, k)) for z in (zones_state(r) if r is not None else []) if z["to"] == mid]
    wm = _warp_all(ev)
    n = len(wm[E.GS[0]] or [])
    row_cost = [{"to": b, "to_name": map_label(maps, b), "cost": {g: (wm[g][mid][b] if wm[g] and mid < len(wm[g]) and b < len(wm[g]) else None)
                                                                  for g in E.GS}} for b in range(n)] if mid < n else []
    col_cost = [{"from": a, "from_name": map_label(maps, a), "cost": {g: (wm[g][a][mid] if wm[g] and mid < len(wm[g]) and a < len(wm[g]) else None)
                                                                      for g in E.GS}} for a in range(n)] if mid < n else []
    try:
        cfg = patch_cfg()
        nraw = _raw(ev, E.GS[0], "NpcData_Info\\%s.npc" % maps[mid]["name"])
        if nraw == UNREAD:
            raise ValueError("npc не прочитан")       # справка покажет «не прочитано», а не «нет»
        npcs = npc_types(nraw)
        crys = [{"type": t, "x": x, "z": z, "to": sorted(cfg[E.GS[0]]["crystals"][t])} for t, x, z in npcs if t in cfg[E.GS[0]]["crystals"]]
    except Exception:
        crys = None
    hold = joy_holders([mid])
    caps = [{"nsr": b[0], "npc": b[1], "btn": b[2], "caption": b[3], "to": b[4], "to_name": map_label(maps, b[4])}
            for b in getattr(ev.cli, "crystals", []) or [] if crys and any(c["type"] == b[1] for c in crys)]
    return dict(row, zones=out_z, inbound=inb, warp_row=row_cost, warp_col=col_cost, crystals=crys, captions=caps,
                holders=None if hold is None else [{"u": h[0], "c": h[1], "name": h[2], "where": h[3]} for h in hold.get(mid, [])][:200],
                holders_error=joy_holders.last_error, holders_notes=[i18n.tr(x) for x in getattr(joy_holders, "notes", None) or []],
                threads=base["threads"], opened=base["opened"], p40=base["p40"], slots=base["slots"], read_errors=base["read_errors"],
                patch_notes=base["patch_notes"])


def lookup(what, ident):
    if what == "maps":
        return lookup_maps()
    try:
        return lookup_map(int(str(ident).strip()))
    except ValueError:
        raise OpRefused("номер карты — целое число")


def divergence(ev, cli, sec):
    """Раздел «карты»; таблица не прочитана (держит процесс, нет связи) — строка «не прочитаны», а не сбой экрана расхождений."""
    try:
        _divergence(ev, cli, sec)
    except OpRefused as ex:
        sec("maps", "карты: сервер ≠ реестр порта, копии", [{"id": "—", "why": "таблицы карт не прочитаны (%s)" % str(ex)[:160]}])


def _divergence(ev, cli, sec):
    rows = []
    try:
        maps = _maps(ev)
        cfg = patch_cfg()
    except Exception as ex:
        sec("maps", "карты: сервер ≠ реестр порта, копии", [{"id": "—", "why": "таблицы карт не прочитаны (%s)" % str(ex)[:160]}])
        return
    reg = getattr(cli, "mapreg", {}) or {}
    for g in E.folders("GSF"):
        try:                                         # ★ ревизия 40, мелочь 6: копия не читается — строка о ней, прочие разделы — как есть
            raw = _raw(ev, g, OPEN)
            if raw is None:
                rows.append({"id": "—", "why": "%s: нет %s" % (g, OPEN)})
                continue
            sl = _sl(ev, cfg, g)
            st = open_state(raw, sl)
            if g == E.GS[0]:
                for m in maps:
                    if m["id"] < sl and reg.get(m["id"]) != st["use"].get(m["id"]):
                        rows.append({"id": m["id"], "why": "реестр карт порта server.open_use %s ≠ OpenMapInfo Use %s" % (reg.get(m["id"]), st["use"].get(m["id"]))})
            w = open_count_issue(raw, _raw(ev, g, THREAD), sl, g)
            if w:
                rows.append({"id": "—", "why": w})
        except OpRefused as ex:
            rows.append({"id": "—", "why": "таблицы карт не прочитаны (%s)" % str(ex)[:160]})
    rows += [{"id": "—", "why": n} for v in cfg.values() for n in v.get("notes") or []]
    wm = _warp_all(ev)
    f = wm[E.GS[0]]
    for g in E.GS[1:]:
        if wm[g] is None or f is None:
            rows.append({"id": "—", "why": "%s: %s не разобран" % (g, WARP)})
            continue
        diff = ["[%d][%d] %d/%d" % (a, b, f[a][b], wm[g][a][b]) for a in range(min(len(f), len(wm[g]))) for b in range(min(len(f), len(wm[g])))
                if f[a][b] != wm[g][a][b]]
        if diff:
            rows.append({"id": "—", "why": "%s: цены телепорта ≠ GameServer (своя база копии): %s" % (g, ", ".join(diff[:8]))})
    for g in E.folders("GSF")[1:]:
        if ev.snap.md5.get(E.rel_of(g, OPEN)) != ev.snap.md5.get(E.rel_of(E.GS[0], OPEN)):
            rows.append({"id": "—", "why": "%s: %s ≠ GameServer (паритет Ch2)" % (g, OPEN)})
    _prefetch(ev, E.GS[0], maps)
    routes = {k: crystal_routes(ev, E.GS[0], k, cfg) or {} for k in range(len(maps))}
    for nsr, npc, btn, cap, to in getattr(cli, "crystals", []) or []:
        for k in range(len(maps)):
            if f and k < len(f) and to < len(f) and npc in routes[k].get(to, []):
                nums = [int(x) for x in re.findall(r"\d+", cap) if int(x) >= 100]
                if nums and f[k][to] not in nums:
                    rows.append({"id": k, "why": "подпись кристалла %s кн.%d «%s» ≠ цене сервера %d (%s → %s)"
                                 % (nsr, btn, cap, f[k][to], map_label(maps, k), map_label(maps, to))})
    sec("maps", "карты: сервер ≠ реестр порта, копии, подписи кристаллов", rows)
