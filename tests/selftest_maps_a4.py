# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_maps_a4.py — самотест шага А4.8 «Карты» (20.11.2026, domains/cs_kinds/mapdata.py).

offline(check)       — подменная стойка selftest_shops.synthetic() + свои MapInfo / MapWarpCost (у Indun своя ячейка [0][2]) / ThreadInfo /
                       Total_PortalConfig / зоны / NpcData_Info трёх GS, OpenMapInfo копий поля (у Indun файла нет), подставные patches.ini
                       (P40 / P30 / P120) и персонажи Joy1, клиентские кнопки кристаллов и реестр карт: цена телепорта (копии, Indun, P40 «не
                       подействует», запрет −1, подписи кристаллов), открытие/закрытие карт (типы, P120, слоты, потоки ThreadInfo по итогу
                       набора, .sim, персонажи на карте и в корзине), паритет Ch2, перепроверка перед выкладкой и откатом (apply_guard),
                       план клиента (реестр карт → AsdaMapRegistry.h НАСТОЯЩИМ генератором на копиях), справка, расхождения, переводы, веб.
sandbox(check, ldb)  — путь набора целиком: создать → проверить → утвердить (сильная — второе подтверждение) → НАСТОЯЩИЙ сухой прогон
                       deploy_changeset (MapWarpCost ×3, OpenMapInfo ×2) → выкладка (персонаж появился на закрываемой карте — отказ до объявления)
                       → выкладка подставным рестартом → откат (всё вернулось, Indun без OpenMapInfo).
live(check)          — только чтение и сухие прогоны: md5 копий, справка, живая оценка набора, план клиента настоящим генератором реестра
                       (md5 порта до = после), НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH, перепроверка по манифесту, расхождения.
Ни рестартов стойки, ни записи в таблицы стойки или порта, ни записи в Joy1. Побочных эффектов при импорте нет.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile

BS = "\\"
GS3 = ("GameServer", "Indun_GameServer", "Ch2_GameServer")
FIELD = ("GameServer", "Ch2_GameServer")
WARP, OPEN = "MapData_Info" + BS + "MapWarpCost.txt", "MapData_Info" + BS + "OpenMapInfo.ini"
MI, THR, TOT = "MapData_Info" + BS + "MapInfo.txt", "ConfigSet" + BS + "ThreadInfo.ini", "PortalIP_Info" + BS + "Total_PortalConfig.Ini"
# id, имя, город (+62), тип (+63), группа (+130)
MAPS = [(0, "Town", 1, 0, 1), (1, "Field", 0, 0, 255), (2, "Dung", 0, 3, 255), (3, "Alpen", 1, 0, 0), (4, "Mine", 0, 6, 255),
        (5, "War", 0, 4, 255), (6, "Closed", 0, 0, 255)]
USE = [1, 1, 1, 1, 0, 0, 0]                     # 3 — карта новых персонажей (mapdata.NEW_CHAR_MAP), 4 — шахта (тип 6) закрыта


def _md5(b):
    return hashlib.md5(b).hexdigest()


def mapinfo():
    lines = [str(len(MAPS))]
    for mid, name, town, typ, grp in MAPS:
        f = [mid, name, 1000, 0, 0, town, typ] + [0] * 9 + [512, 512, 256, 256, 5]
        f += [129, 282] + [0] * 8 if mid == 2 else [0] * 10
        f += [grp, 19, -1, -1, -1] + [-1] * 60
        lines.append("\t".join(str(x) for x in f))
    return ("\r\n".join(lines) + "\r\n").encode("latin-1")


def warp(indun=False):
    n = len(MAPS)
    m = [[0] * n for _ in range(n)]
    m[0][1], m[1][0], m[0][6] = 1500, 1500, 3000
    if indun:
        m[0][2] = 700
    return ("\r\n".join([str(n)] + ["\t".join(str(x) for x in r) for r in m]) + "\r\n").encode("latin-1")


def openmap(use=None):
    use = USE if use is None else use
    out = ["[MAP_INFO]", "MapCount = 5"]
    for mid, name, _t, _ty, _g in MAPS:
        out += ["[MAP_%d]  " % mid, "Name = %s" % name.lower(), "Use = %d" % use[mid]]
    return ("\r\n".join(out) + "\r\n").encode("latin-1")


def thread(count=5):
    return ("[MAX_INIT_THREAD]\r\nCOUNT = %d\r\n\r\n[THREADID]\r\nCOUNT = 0\r\n" % count).encode("latin-1")


def total():
    out = ["[PORTAL_COUNT]", "count = %d" % len(MAPS)]
    for mid, _n, _t, _ty, _g in MAPS:
        out += ["[PORTAL_INFO_%d]" % mid, "USE = %d" % (0 if mid == 6 else 1), "Index = %d" % mid, "IP = 10.0.0.1", "PORT = 9000",
                "STARTPOSX = 100", "STARTPOSZ = 120"]
    return ("\r\n".join(out) + "\r\n").encode("latin-1")


def zone(to, x=50, z=60):
    return ("[PORTAL_COUNT]\r\ncount = 1\r\n[PORTAL_INFO_0]\r\nIndex = %d\r\nIP = 10.0.0.1\r\nPORT = 9000\r\nPOSX = %d\r\nPOSZ = %d\r\nRANGEX = 2\r\n"
            "RANGEZ = 3\r\nSTARTPOSX = 70\r\nSTARTPOSZ = 80\r\nINDUN = 0\r\n" % (to, x, z)).encode("latin-1")


def npc(*recs):
    b = bytearray(221 * len(recs))
    for i, (t, x, z) in enumerate(recs):
        struct.pack_into("<h", b, 221 * i + 4, t)
        struct.pack_into("<hh", b, 221 * i + 8, x, z)
    return bytes(b)


def stack_files():
    out = {}
    for g in GS3:
        out[g + BS + MI], out[g + BS + WARP], out[g + BS + THR], out[g + BS + TOT] = mapinfo(), warp(g == "Indun_GameServer"), thread(), total()
        out[g + BS + "PortalIP_Info" + BS + "Town_PortalConfig.Ini"] = zone(2)
        out[g + BS + "PortalIP_Info" + BS + "Field_PortalConfig.Ini"] = zone(6)
        out[g + BS + "NpcData_Info" + BS + "Town.npc"] = npc((46, 10, 10), (7, 20, 20))
        out[g + BS + "NpcData_Info" + BS + "Field.npc"] = npc((9, 5, 5))
        out[g + BS + "NpcData_Info" + BS + "Closed.npc"] = b""
        for _m, name, _t, _ty, _g in MAPS:
            out[g + BS + "MapData_Info" + BS + name + ".sim"] = b"SIM"
    for g in FIELD:
        out[g + BS + OPEN] = openmap()
    return out


CFG = {"p40": True, "open_gate": True, "crystals": {46: {1, 2}}, "slots": 23, "p120": True}


class _Env:
    """Подмена patches.ini (mapdata.patch_cfg) и персонажей Joy1 (mapdata.joy_holders) на время блока. when — с какого момента видны
    «появившиеся» персонажи (ревизия 39 Н-3)."""

    def __init__(self, cfg=None, hold=None, fail_cfg=False, fail_joy=False, when=None, extra=None, lm=None, notes=None):
        self.cfg = {g: dict(CFG, **((cfg or {}).get(g, {}))) for g in GS3}
        self.hold, self.fail_cfg, self.fail_joy, self.when, self.extra = dict(hold or {}), fail_cfg, fail_joy, when, dict(extra or {})
        self.lm = {"0_0": set(range(len(MAPS))), "0_1": set(range(len(MAPS)))} if lm is None else lm   # LoginManager Game_<n> (ревизия 40)
        self.notes = list(notes or [])                 # joy_holders.notes (ревизия 40 В-2: нет таблицы P108)

    def __enter__(self):
        from domains.cs_kinds import mapdata as M
        self.saved = (M.patch_cfg, M.joy_holders, M.lm_game_maps)
        me = self

        def lm_game_maps(ttl=60):
            lm_game_maps.last_error = None if me.lm != "fail" else "нет файла (самотест)"
            return None if me.lm == "fail" else {k: set(v) for k, v in me.lm.items()}
        lm_game_maps.last_error = None

        def patch_cfg(ttl=60):
            if me.fail_cfg:
                raise ValueError("GameServer\\ConfigSet\\patches.ini: секций нет")
            return {g: dict(v, crystals={k: set(s) for k, s in v["crystals"].items()}) for g, v in me.cfg.items()}

        def joy_holders(mids):
            joy_holders.last_error, joy_holders.notes = None, list(me.notes)
            if me.fail_joy:
                joy_holders.last_error = "нет связи с Joy1 (самотест)"
                return None
            src = dict(me.hold)
            if me.when is None or me.when():
                for k, v in me.extra.items():
                    src[k] = list(src.get(k, [])) + list(v)
            return {int(m): list(src.get(int(m), [])) for m in mids}
        joy_holders.last_error, joy_holders.notes = None, []
        M.patch_cfg, M.joy_holders, M.lm_game_maps = patch_cfg, joy_holders, lm_game_maps
        return self

    def __exit__(self, *a):
        from domains.cs_kinds import mapdata as M
        M.patch_cfg, M.joy_holders, M.lm_game_maps = self.saved
        return False


_EVS = []


def _ev(items):
    from domains import shopdata as SD
    e = SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False).run()
    _EVS.append(e)
    return e


def _errs(ev):
    return [e for r in ev.positions for e in r["errors"]] + list(ev.errors)


def _warns(ev):
    return [w for r in ev.positions for w in r["warnings"]]


def _cell(raw, a, b):
    return int(raw.split(b"\r\n")[1 + a].split(b"\t")[b])


def _use(raw, mid):
    from domains.cs_kinds import mapdata as M
    return M.open_state(raw, 23)["use"].get(mid)


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check):
    import selftest_shops as T
    from domains import shopdata as SD
    from domains.cs_kinds import mapdata as M
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    check("А4.8 реестр: область «mapdata» последней, виды warp.cost / map.open, права data.edit / data.apply, гейт баланса; MapWarpCost — per_copy "
          "во всех GS, OpenMapInfo — per_copy в копиях поля (GSF = GameServer + Ch2_GameServer); выкладчик пускает MapWarpCost ×3 и OpenMapInfo "
          "только в копиях поля (у Indun — нет), check_roots: 2 копии поля — да, 3 копии или одна — СТОП",
          [a.AREA for a in SD.AREAS[SD.AREAS.index(M) + 1:]] == ["events", "patchcfg"] and set(M.KINDS) == {"warp.cost", "map.open"} and SD.area_perm("warp.cost", "apply") == "data.apply"
          and SD.area_perm("map.open", "edit") == "data.edit" and M.BALANCE_GATE and SD.SRV_POLICY[WARP] == "per_copy"
          and SD.SRV_POLICY[OPEN] == "per_copy" and SD.SRV_FAMILY[OPEN] == "GSF" and SD.SRV_FAMILY[WARP] == "GS"
          and SD.folders("GSF") == list(FIELD) and all(g + BS + WARP in dc.ALLOWED for g in GS3)
          and all(g + BS + OPEN in dc.ALLOWED for g in FIELD) and "Indun_GameServer" + BS + OPEN not in dc.ALLOWED
          and dc.check_roots({g + BS + OPEN: 1 for g in FIELD}) is None and dc.check_roots({"GameServer" + BS + OPEN: 1}) is not None
          and dc.check_roots({g + BS + WARP: 1 for g in GS3}) is None and dc.check_roots({"GameServer" + BS + WARP: 1}) is not None)
    bad = []
    for kind, p in (("warp.cost", {"from": 0, "to": 1, "cost": -2}), ("warp.cost", {"from": 0, "to": 1, "cost": 2000000001}),
                    ("warp.cost", {"from": 30, "to": 1, "cost": 5}), ("warp.cost", {"from": 0, "to": "x", "cost": 5}),
                    ("map.open", {"map": 1, "use": 2}), ("map.open", {"map": -1, "use": 1}), ("map.open", {"map": 30, "use": 0})):
        try:
            SD.norm(kind, p)
            bad.append((kind, p))
        except Exception:
            pass
    check("А4.8 позиции: неверные параметры — отказ (цена < −1 и > 2·10⁹, карта вне 0…29, не число, Use не 0/1)", not bad, bad)
    check("А4.8 разбор: MapInfo — имя, тип +63, группа +130 после пар точек, точки входа/возврата (+98/+108); Total — USE и прибытие по порядку "
          "секций; зона — прямоугольник и прибытие; .npc — тип и клетка (отрицательная — запись в клетке 0,0, ревизия 40); Crystals как "
          "ParseCrystals (битый — None)",
          [(m["name"], m["type"], m["group"]) for m in M.mapinfo(mapinfo())][:3] == [("Town", 0, 1), ("Field", 0, 255), ("Dung", 3, 255)]
          and M.mapinfo(mapinfo())[2]["points"] == [[129, 282]] and M.total_state(total())[5]["use"] == 1
          and M.total_state(total())[1]["x"] == 100 and M.zones_state(zone(5))[0]["to"] == 5 and M.total_state(total())[6]["use"] == 0
          and M.zones_state(zone(5))[0]["x1"] == 52 and M.npc_types(npc((46, 10, 10), (3, -1, 4))) == [(46, 10, 10), (3, 0, 0)]
          and M.parse_crystals("46:7,0,1;49:3") == {46: {7, 0, 1}, 49: {3}} and M.parse_crystals("46:7;x") is None
          and M.parse_crystals("46:31") is None)
    with T.synthetic() as (raw, md5, cli):
        for rel, b in stack_files().items():
            raw[rel], md5[rel] = b, _md5(b)
        cli.crystals = [["46npc", 46, 0, "Field: 1500", 1], ["46npc", 46, 1, "Dung", 2]]
        cli.mapreg = {m[0]: USE[m[0]] for m in MAPS}
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tempfile.mkdtemp(prefix="asda_t48_cs_")
        try:
            with _Env():
                _offline_warp(check, raw, md5)
                _offline_open(check, raw, md5)
                _offline_guard(check, raw, md5)
                _offline_ref(check, raw, md5, cli)
                _offline_r40(check, raw, md5, cli)
        finally:
            shutil.rmtree(SD.CS_DIR, ignore_errors=True)
            SD.CS_DIR = saved_dir
    _offline_plan(check)
    _offline_tr(check)
    _offline_r40_pure(check)


def _offline_warp(check, raw, md5):
    from domains.cs_kinds import mapdata as M
    e = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 4000})])
    s = e.summary()
    nb = e.new_bytes()
    ind = nb.get("Indun_GameServer" + BS + WARP)
    check("А4.8 warp.cost Town → Field 1500 → 4000: 3 файла MapWarpCost (все GS), у Indun своя ячейка [0][2] = 700 сохранена, остальные байты "
          "как были, позиция — «кристаллы: NPC 46», сильная правка (×2.7, value), предупреждение «подпись … показывает прежнюю цену 1500»",
          not _errs(e) and s["server"]["count"] == 3 and all(_cell(nb[g + BS + WARP], 0, 1) == 4000 for g in GS3) and ind is not None
          and _cell(ind, 0, 2) == 700 and len(ind) == len(raw["Indun_GameServer" + BS + WARP])
          and "кристаллы: NPC 46" in e.positions[0]["text"] and any(b["strong"] and b["kind"] == "value" for b in s["balance"])
          and any("показывает прежнюю цену 1500" in w for w in _warns(e)) and not s["client_needed"], (_errs(e), _warns(e)))
    e2 = _ev([("warp.cost", {"from": 0, "to": 2, "cost": 100})])
    e3 = _ev([("warp.cost", {"from": 1, "to": 0, "cost": 2000})])
    with _Env(cfg={"Indun_GameServer": {"p40": False}}):
        e4 = _ev([("warp.cost", {"from": 1, "to": 0, "cost": 2000})])
    e5 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": -1})])
    e6 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 1500})])
    with _Env(fail_cfg=True):
        e7 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 2000})])
    e8 = _ev([("warp.cost", {"from": 7, "to": 1, "cost": 2000})])
    check("А4.8 warp.cost отказы и случаи: Indun с другим прежним числом ячейки — отказ «копия Indun_GameServer»; маршрут без кристалла при P40 во всех "
          "GS — отказ «не подействует»; P40 выключен в Indun — правка с предупреждением; −1 (запрет) — сильная type; то же число — «менять нечего»; "
          "patches.ini не прочитан — отказ; карта вне MapInfo — отказ",
          any("копия Indun_GameServer: цена [0][2] = 700" in x for x in _errs(e2))
          and any("цена не подействует" in x for x in _errs(e3)) and not _errs(e4)
          and any("P40 выключен в Indun_GameServer" in w for w in _warns(e4))
          and not _errs(e5) and any(b["kind"] == "type" and b["strong"] for b in e5.summary()["balance"])
          and any("менять нечего" in x for x in _errs(e6)) and any("patches.ini стойки не прочитан" in x for x in _errs(e7))
          and any("нет в MapInfo.txt" in x for x in _errs(e8)), [(_errs(x)[:1]) for x in (e2, e3, e4, e5, e6, e7, e8)])
    with _Env(cfg={g: {"crystals": {46: {1, 2, 6}}} for g in GS3}):
        e9 = _ev([("warp.cost", {"from": 0, "to": 6, "cost": 3500})])
    check("А4.8 warp.cost на закрытую карту без записи Total USE: предупреждения «нет записи Total_PortalConfig с USE ≠ 0» и «закрыта в "
          "OpenMapInfo.ini — P40 (CheckOpenMap) откажет»; группа города 1 — «платят 0»", not _errs(e9)
          and any("Total_PortalConfig с USE" in w for w in _warns(e9)) and any("P40 (CheckOpenMap)" in w for w in _warns(e9))
          and any("фракции-владельца города (группа 1" in w for w in _warns(e9)), _warns(e9))
    saved = raw["Ch2_GameServer" + BS + WARP]
    try:
        bad = saved.replace(b"\r\n", b"\t", 2)              # первые строки слиты — построчность не доказана
        raw["Ch2_GameServer" + BS + WARP], md5["Ch2_GameServer" + BS + WARP] = bad, _md5(bad)
        e10 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 2000})])
        nb10 = e10.new_bytes()
    finally:
        raw["Ch2_GameServer" + BS + WARP], md5["Ch2_GameServer" + BS + WARP] = saved, _md5(saved)
    check("А4.8 warp.cost: матрица Ch2 не ложится построчно — отказ до записи (ни одна копия не тронута)",
          any("матрица не ложится построчно" in x for x in _errs(e10)) and not nb10, _errs(e10))
    # ★ живой прогон 20.11: файл, который держит работающий GameServer, служба не читает (PermissionError) — «не прочитан», а не «нет»
    rel = "Ch2_GameServer" + BS + "NpcData_Info" + BS + "Town.npc"
    saved_m = md5[rel]
    try:
        md5[rel] = M.UNREAD
        e11 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 2000})])
        lk = M.lookup("map", "1")
        saved_t = md5["GameServer" + BS + THR]
        md5["GameServer" + BS + THR] = M.UNREAD
        e12 = _ev([("map.open", {"map": 6, "use": 1})])
        md5["GameServer" + BS + THR] = saved_t
    finally:
        md5[rel] = saved_m
    check("А4.8 файл стойки не читается (держит процесс): .npc карты-источника — отказ цены «не прочитан» (не «кристаллов нет»), справка карты "
          "не падает; ThreadInfo не прочитан — отказ открытия «не прочитан»",
          any("Town.npc не прочитан" in x for x in _errs(e11)) and lk["id"] == 1
          and any("ThreadInfo.ini не прочитан" in x for x in _errs(e12)), (_errs(e11), _errs(e12)))
    _ = M


def _offline_open(check, raw, md5):
    from domains.cs_kinds import mapdata as M
    e = _ev([("map.open", {"map": 6, "use": 1})])
    s = e.summary()
    nb = e.new_bytes()
    check("А4.8 map.open открыть Closed (6, тип 0): OpenMapInfo только копий поля (2 файла, у Indun файла нет), Use 0 → 1, прочие строки байт в "
          "байт; клиент — необязательная правка реестра карт (map_open 0 → 1, сервер без выпуска), сильная type; предупреждение «NPC на карте "
          "не будет» (пустой .npc)", not _errs(e) and sorted(nb) == sorted(g + BS + OPEN for g in FIELD)
          and all(_use(nb[g + BS + OPEN], 6) == 1 and _use(nb[g + BS + OPEN], 1) == 1 for g in FIELD)
          and len(nb["GameServer" + BS + OPEN]) == len(raw["GameServer" + BS + OPEN])
          and s["client"] == [{"type": "map_open", "file": "mapdata", "src": "mapdata", "map": 6, "old": 0, "new": 1, "optional": True}]
          and not s["client_needed"] and any(b["kind"] == "type" for b in s["balance"]) and any("NPC на карте не будет" in w for w in _warns(e)),
          (_errs(e), sorted(nb), s["client"]))
    e2 = _ev([("map.open", {"map": 5, "use": 1})])
    with _Env(cfg={"Ch2_GameServer": {"p120": False}}):
        e3 = _ev([("map.open", {"map": 4, "use": 1})])
    e3b = _ev([("map.open", {"map": 4, "use": 1})])
    e4 = _ev([("map.open", {"map": 1, "use": 1})])
    with _Env(hold={3: []}):
        e4b = _ev([("map.open", {"map": 3, "use": 0})])
    check("А4.8 map.open: тип 4 — отказ «смысл Use … не подтверждён»; тип 6 при P120, не стоящем в Ch2, — отказ «не подействует», при P120 везде — "
          "правка; уже открыта — «менять нечего»; закрыть карту 3 — отказ даже без персонажей (будущие держатели: там создаются новые персонажи и "
          "возрождаются персонажи без VillagePos)", any("смысл Use" in x for x in _errs(e2)) and any("только P120" in x for x in _errs(e3))
          and not _errs(e3b) and any("менять нечего" in x for x in _errs(e4)) and any("создаются новые персонажи" in x for x in _errs(e4b)),
          (_errs(e2), _errs(e3), _errs(e3b), _errs(e4), _errs(e4b)))
    saved = {g: raw[g + BS + THR] for g in GS3}
    try:
        for g in GS3:
            raw[g + BS + THR], md5[g + BS + THR] = thread(4), _md5(thread(4))
        e5 = _ev([("map.open", {"map": 6, "use": 1})])
        with _Env(hold={1: []}):
            e6 = _ev([("map.open", {"map": 6, "use": 1}), ("map.open", {"map": 1, "use": 0})])
            e7 = _ev([("map.open", {"map": 1, "use": 0}), ("map.open", {"map": 6, "use": 1})])
    finally:
        for g in GS3:
            raw[g + BS + THR], md5[g + BS + THR] = saved[g], _md5(saved[g])
    check("А4.8 map.open по ИТОГУ набора (after_run): COUNT 4, открыто 4 — открытие ещё одной — отказ «больше ThreadInfo.ini COUNT … exit(1)» в обеих "
          "копиях поля; в одном наборе с закрытием другой — без ошибок при любом порядке позиций",
          any("больше ThreadInfo.ini COUNT 4" in x and "GameServer" in x for x in _errs(e5))
          and any("Ch2_GameServer: открытых карт 5" in x for x in _errs(e5)) and not _errs(e6) and not _errs(e7), (_errs(e5), _errs(e6), _errs(e7)))
    saved_sim = md5["GameServer" + BS + "MapData_Info" + BS + "Closed.sim"]
    try:
        md5.pop("GameServer" + BS + "MapData_Info" + BS + "Closed.sim")
        e8 = _ev([("map.open", {"map": 6, "use": 1})])
    finally:
        md5["GameServer" + BS + "MapData_Info" + BS + "Closed.sim"] = saved_sim
    hold = {1: [(75001, 1, "Alice", "CharPos"), (75002, 0, "[Del_VillagePos 2026-11-01 10:00]", "Del_VillagePos")]}
    with _Env(hold=hold):
        e9 = _ev([("map.open", {"map": 1, "use": 0})])
    with _Env(fail_joy=True):
        e10 = _ev([("map.open", {"map": 1, "use": 0})])
    with _Env(hold={1: []}):
        e11 = _ev([("map.open", {"map": 1, "use": 0})])
    check("А4.8 map.open: нет .sim — отказ; закрытие карты с персонажами (живой и корзина Del_VillagePos) — отказ со списком «SearchThreadInfo вернёт "
          "3»; Joy1 не прочитан — отказ; без персонажей — правка и предупреждение «перестанут вести: Town зона 0 … кристалл с карты Town (0)»",
          any("нет MapData_Info" + BS + "Closed.sim" in x for x in _errs(e8))
          and any("SearchThreadInfo вернёт 3" in x and "Alice (75001/1, CharPos)" in x and "Del_VillagePos" in x for x in _errs(e9))
          and any("персонажи не прочитаны" in x for x in _errs(e10)) and not _errs(e11)
          and any("перестанут вести" in w and "кристалл с карты Town (0)" in w for w in _warns(e11)), (_errs(e9), _warns(e11)))
    saved = raw["Ch2_GameServer" + BS + OPEN]
    try:
        other = openmap([1, 1, 1, 1, 0, 0, 1])
        raw["Ch2_GameServer" + BS + OPEN], md5["Ch2_GameServer" + BS + OPEN] = other, _md5(other)
        with _Env(hold={2: []}):
            e12 = _ev([("map.open", {"map": 2, "use": 0})])
        e13 = _ev([("map.open", {"map": 6, "use": 1})])
    finally:
        raw["Ch2_GameServer" + BS + OPEN], md5["Ch2_GameServer" + BS + OPEN] = saved, _md5(saved)
    check("А4.8 map.open: Ch2 ≠ поле — паритет (Ch2 = поле, иначе отказ) и Use карты в копиях поля разный — отказ «отличия копии не затираются»",
          any("паритет Ch2" in x for x in _errs(e12) + _errs(e13)) and any("в копиях поля разный" in x for x in _errs(e13)),
          (_errs(e12), _errs(e13)))
    _ = M


def _cs_man(e, cid, items):
    from domains import shopcs
    cs = {"id": cid, "items": [{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], "check": e.summary()}
    _mp, m = shopcs.build_server_out(cs, e)
    cs["server_tag"] = m["tag"]
    return cs, m


def _offline_guard(check, raw, md5):
    from domains.cs_kinds import mapdata as M
    items = [("map.open", {"map": 1, "use": 0}), ("warp.cost", {"from": 0, "to": 1, "cost": 2000})]
    with _Env(hold={1: []}):
        e = _ev(items)
    cs, man = _cs_man(e, 9481, items)
    late = {1: [(75020, 1, "Late", "CharPos")]}
    with _Env(hold={1: []}):
        ok = M.apply_guard(cs, "apply")
        after, now = M._guard_state(cs, "apply")
    with _Env(hold={1: []}, extra=late):
        late_apply = M.apply_guard(cs, "apply")
    with _Env(fail_joy=True):
        nr = M.apply_guard(cs, "apply")
    rel = "GameServer" + BS + OPEN
    # откат открытия: набор открывает 5 — на стойке уже файл набора, база — в .bak; персонаж на 5 появился — откат закрыл бы карту под ним
    items2 = [("map.open", {"map": 6, "use": 1})]
    e2 = _ev(items2)
    cs2, man2 = _cs_man(e2, 9482, items2)
    saved = {g: raw[g + BS + OPEN] for g in FIELD}
    try:
        for g in FIELD:
            r = g + BS + OPEN
            raw[r + ".bak_" + man2["tag"]], md5[r + ".bak_" + man2["tag"]] = saved[g], _md5(saved[g])
            nb = e2.new_bytes()[r]
            raw[r], md5[r] = nb, _md5(nb)
        with _Env(hold={6: [(75030, 1, "Bob", "CharPos")]}):
            rb = M.apply_guard(cs2, "rollback")
    finally:
        for g in FIELD:
            r = g + BS + OPEN
            raw[r], md5[r] = saved[g], _md5(saved[g])
    check("А4.8 перепроверка перед выкладкой и откатом (apply_guard по «живая + файлы набора» / «живая, файлы набора — базой»): чисто — пусто; "
          "персонаж появился на закрываемой карте — причина с его именем; Joy1 не прочитан — «не прочитаны»; откат открытия при персонаже на карте "
          "— причина (база из .bak_<метка>)", ok == [] and _use(after[rel], 1) == 0 and _use(now[rel], 1) == 1
          and any("Late" in x for x in late_apply) and any("не прочитаны" in x for x in nr) and any("Bob" in x for x in rb),
          (ok, late_apply, nr, rb))


def _offline_ref(check, raw, md5, cli):
    from domains import shopdata as SD
    from domains.cs_kinds import mapdata as M
    with _Env(hold={0: [(75001, 1, "Alice", "CharPos")]}):
        ls = M.lookup("maps", "")
        lk = M.lookup("map", "0")
    check("А4.8 справка: список 7 карт (тип, группа, Use копий поля, реестр, прибытие кристалла, правится ли), потоки и открытые по копиям; "
          "карточка Town — зона на Dung, вход из Field нет (зона Field — на Closed), кристалл NPC 46 → 1, 2, подписи, персонажи, цены строки "
          "×3 копии (Indun [0][2] = 700)", len(ls["rows"]) == 7 and ls["rows"][5]["editable"] is False and ls["rows"][4]["editable"]
          and ls["rows"][0]["use"] == {"GameServer": 1, "Ch2_GameServer": 1} and ls["threads"]["GameServer"] == 5 and ls["opened"]["GameServer"] == 4
          and [z["to"] for z in lk["zones"]] == [2] and lk["inbound"] == [] and lk["crystals"] == [{"type": 46, "x": 10, "z": 10, "to": [1, 2]}]
          and len(lk["captions"]) == 2 and lk["holders"] == [{"u": 75001, "c": 1, "name": "Alice", "where": "CharPos"}]
          and lk["warp_row"][2]["cost"] == {"GameServer": 0, "Indun_GameServer": 700, "Ch2_GameServer": 0}, (ls["rows"][:1], lk.get("crystals")))
    cli.mapreg[2] = 0
    cli.crystals.append(["46npc", 46, 2, "Dung 900G", 2])
    try:
        d = {x["key"]: x for x in SD.divergence(areas=("mapdata",))["sections"]}
    finally:
        cli.mapreg[2] = 1
        cli.crystals.pop()
    rows = d["maps"]["rows"]
    check("А4.8 расхождения: раздел maps — реестр карт порта ≠ Use (карта 2), Indun — свои цены ([0][2] 0/700), подпись кристалла «900» ≠ цене "
          "сервера 0", list(d) == ["maps"] and any(r["id"] == 2 and "server.open_use" in r["why"] for r in rows)
          and any("Indun_GameServer: цены телепорта" in r["why"] and "[0][2] 0/700" in r["why"] for r in rows)
          and any("подпись кристалла 46npc кн.2" in r["why"] for r in rows), rows)


def _offline_plan(check):
    """План клиента на КОПИЯХ реестра карт и AsdaMapRegistry.h (НАСТОЯЩИЙ генератор asda_map_registry): JSON меняется только server.open_use,
    заголовок = render_cpp_header нового реестра; заголовок «мимо реестра» — отказ. Настоящие файлы порта — md5 до = после."""
    from domains import shopdata as SD
    from domains.cs_kinds import mapdata as M
    real = (M.REG_JSON, M.REG_H)
    if not all(os.path.isfile(p) for p in real):
        return check("А4.8 план клиента — реестр карт и AsdaMapRegistry.h порта есть", False, real)
    md0 = [SD.md5f(p) for p in real]
    tmp = tempfile.mkdtemp(prefix="asda_t48_plan_")
    try:
        cj, ch = os.path.join(tmp, "asda_map_registry.json"), os.path.join(tmp, "AsdaMapRegistry.h")
        shutil.copy2(real[0], cj)
        shutil.copy2(real[1], ch)
        M.REG_JSON, M.REG_H = cj, ch
        reg = json.load(open(cj, encoding="utf-8-sig"))
        m20 = [m for m in reg["maps"] if m["id"] == 20][0]["server"]["open_use"]
        edits = [{"type": "map_open", "file": "mapdata", "src": "mapdata", "map": 20, "old": m20, "new": 1 - m20, "optional": True}]
        pl = SD.client_plan(edits, 0)
        b = pl["_bytes"]
        MR = M._tool()
        reg2 = json.loads(b[cj].decode("utf-8-sig"))
        want = json.loads(open(cj, encoding="utf-8-sig").read())
        [m for m in want["maps"] if m["id"] == 20][0]["server"]["open_use"] = 1 - m20
        why = [("errors", pl["errors"]), ("reg", reg2 == want), ("h", b[ch] == MR.render_cpp_header(reg2)), ("h_changed", b[ch] != open(ch, "rb").read()),
               ("files", sorted(pl["files"]) == sorted([cj, ch])), ("dt", pl["dt_jobs"])]
        ok_plan = not pl["errors"] and all(v for k, v in why[1:5]) and not pl["dt_jobs"]
        stale_ = [dict(edits[0], old=1 - m20)]
        pl3 = SD.client_plan(stale_, 0)
        open(ch, "ab").write(b"// hand edit\r\n")
        pl2 = SD.client_plan(edits, 0)
    finally:
        M.REG_JSON, M.REG_H = real
        shutil.rmtree(tmp, ignore_errors=True)
    check("А4.8 план клиента (копии, НАСТОЯЩИЙ asda_map_registry): реестр — только server.open_use карты 20, AsdaMapRegistry.h = render_cpp_header "
          "нового реестра, DT нет; заголовок правили мимо реестра — отказ; «было» в реестре другое — отказ «пересоберите набор»; файлы порта md5 "
          "до = после", ok_plan and any("мимо реестра" in x for x in pl2["errors"]) and any("пересоберите набор" in x for x in pl3["errors"])
          and [SD.md5f(p) for p in real] == md0, (why, pl2["errors"], pl3["errors"]))


def _offline_tr(check):
    from core import i18n
    samples = [
        "позиция 1: копия Indun_GameServer: цена [0][2] = 700, а в GameServer 0 — отличия копии не затираются, правка не делается",
        "позиция 1: у карты Field (1) нет NPC, которому ключ Crystals P40 разрешает вести на Town (0) (ни в одной копии) — P40 пропускает 5477 только "
        "у такого NPC, цена не подействует, правка не делается",
        "маршрута у кристаллов нет: цену возьмёт только переход, который P40 пропускает (P40 выключен в Indun_GameServer) — честный клиент так не ходит",
        "подпись кнопки кристалла 46npc кн.0 «Field: 1500» показывает прежнюю цену 1500 — клиент цену не пересчитывает, подпись (NSR) панель не правит",
        "телепорт кристаллом Town (0) → Field (1): цена 1500 → 4000 (сервер MapWarpCost.txt ×3 GS, кристаллы: NPC 46)",
        "телепорт кристаллом Field (1) → Town (0): цена 1500 → 2000 (сервер MapWarpCost.txt ×3 GS)", "телепорт Town (0) → Field (1): цена",
        "позиция 1: карта War (4) типа 4 (война (RoseWar)): поток по OpenMapInfo сервер даёт только типам 0/1/3 (SetUserInfo_ThreadID_Mapping) — смысл Use "
        "у этого типа не подтверждён, правка не делается",
        "позиция 1: на карте Field (1) стоят или возрождаются 2 перс. (Alice (75001/1, CharPos), [Del_VillagePos 2026-11-01 10:00] (75002/0, "
        "Del_VillagePos)) — без потока карты их вход в мир не состоится (SearchThreadInfo вернёт 3), правка не делается — сначала перенесите их "
        "(карточка игрока, «вытащить застрявшего»)",
        "позиция 1: на карте Alpen (3) создаются новые персонажи (UPCreateChar) и возрождаются персонажи без строки VillagePos (charLogOnRes) — "
        "без потока карты их вход в мир не состоится, правка не делается",
        "позиция 1: копия GameServer: открытых карт 5 больше ThreadInfo.ini COUNT 4 — GameServer выйдет при старте (exit(1), GameServer.c:64912)",
        "на закрытую карту Field (1) перестанут вести: Town зона 0; кристалл с карты Town (0) — напольный портал (sub_52C4C0) молчит, кристалл откажет P40",
        "карта Closed (5) (тип 0): открыть (сервер OpenMapInfo.ini ×2 — GameServer, Ch2_GameServer)", "карта Closed (5): открыта",
        "реестр карт порта (маршруты трекера и автопути) получит open_use 1 клиентской половиной — нужна полная сборка C++ выпуска (AsdaMapRegistry.h), "
        "серверу клиент не нужен",
        "карты: персонажи не прочитаны (нет связи с Joy1) — вслепую не делается", "GameServer: NpcData_Info" + BS + "Closed.npc нет или пуст — NPC на карте не будет",
        "позиция 1: GameServer: нет MapData_Info" + BS + "Closed.sim — поток карты его загружает (sub_419E50), правка не делается",
        "Indun_GameServer: цены телепорта ≠ GameServer (своя база копии): [0][2] 0/700", "реестр карт порта server.open_use 0 ≠ OpenMapInfo Use 1",
        "карты: сервер ≠ реестр порта, копии, подписи кристаллов", "AsdaMapRegistry.h изменится (kServerMapOpen и пометки рёбер kPortalGraph) — нужна полная "
        "сборка C++ выпуска", "Карты: цена телепорта кристаллом (MapWarpCost.txt [откуда][куда], только сервер; −1 — переход запрещён)",
        "OpenMapInfo.ini меняется не во всех копиях поля (GameServer) — выкладчик требует GameServer, Ch2_GameServer, пересоберите набор",
        # ★ ревизия 40
        "откат не делается и с ключом --held-ok: копия GameServer: открытых карт 5 больше ThreadInfo.ini COUNT 4 — GameServer выйдет при старте "
        "(exit(1), GameServer.c:64912)",
        "откат не делается и с ключом --held-ok (причин 2, первая): на карте Field (1) стоят или возрождаются 1 перс. (Dave (75050/2, Charinpos "
        "(CharPos.Poridx 22))) — без потока карты их вход в мир не состоится (SearchThreadInfo вернёт 3), правка не делается — сначала перенесите "
        "их (карточка игрока, «вытащить застрявшего»)",
        "секцию MAP_23 сервер читает только при P30, а его установка в GameServer журналом патчей не подтверждена — правка может не подействовать",
        "у LoginManager нет адреса Game_6 (0_1) — персонаж, сохранённый на карте Closed (6), в мир не войдёт, попасть на неё можно только переходом",
        "адреса Game_<n> LoginManager не прочитаны (GameServer: журнал патчей не прочитан) — вход в мир по карте Closed (6) не проверен",
        "таблицы dbo.AsdaDungeonRelogPoint нет (SQL P108 не применён) — перенос с турнирных карт шагом 4б2 рестарта не учтён, его и не будет",
        "GameServer: установка патчей не подтверждена (журнал патчей: GameServer: журнала патчей нет) — P30 / P40 / P120 взяты по patches.ini",
        "GameServer: P40_CrystalTeleportGate при последнем запуске не встал ([MISMATCH] / [ОШИБКА] в журнале патчей) — не действует",
        "Ch2_GameServer: P120_MineTravel включён в patches.ini, а при последнем запуске выключен — установка не подтверждена, взят по patches.ini",
        "Ch2_GameServer: P30_MapSlots включён в patches.ini, а в журнале последнего запуска его нет — установка не подтверждена, взят по patches.ini",
        "у карты Field (1) нет записи Total_PortalConfig с USE ≠ 0 (Indun_GameServer) — переход 5477 сервер молча отклонит при любой цене",
        "карта Closed (6) закрыта в OpenMapInfo.ini (GameServer, Ch2_GameServer) — P40 (CheckOpenMap) откажет в переходе при любой цене"]
    i18n.set_lang("en")
    try:
        tr = [i18n.tr(x) for x in samples]
    finally:
        i18n.set_lang("ru")
    left = [(a, b) for a, b in zip(samples, tr) if a == b or re.search("[А-Яа-яЁё]{3}", b)]
    check("А4.8 переводы службы: позиции, отказы (вложенные «позиция N: копия …»), предупреждения со списком «; », итог набора, расхождения — EN без "
          "русского", not left, left[:2])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "mapdata.js"), encoding="utf-8").read()
    en = open(os.path.join(root, "web", "i18n.js"), encoding="utf-8").read()
    shops = open(os.path.join(root, "web", "shops.js"), encoding="utf-8").read()
    STR = r'"([^"\n]*)"'
    have = set(re.findall(STR + r"\s*:", en))
    need = {x for x in re.findall(r"T\(" + STR, js)} | {x for x in re.findall(STR, js) if re.search("[А-Яа-яЁё]", x)}
    from domains.cs_kinds import mapdata as M
    help_ = set(re.findall(r'"(?:warp\.cost|map\.open)":\s*' + STR, shops))
    miss = sorted((need | set(M.TYPE_NAMES.values()) | help_) - have)
    block = en.split("// А4.8 20.11", 1)[1] if "// А4.8 20.11" in en else ""
    keys = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", block, re.M)
    allk = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", en, re.M)
    check("А4.8 веб: mapdata.js подключён (index.html, вкладка и маршрут в shops.js, справка видов), все его строки и подписи типов карт есть в "
          "I18N_EN, ключи блока А4.8 не повторяют прежние", "/mapdata.js" in open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
          and "#/shops/maps" in shops and "viewMapData" in shops and len(help_) == 2 and not miss and keys and all(allk.count(k) == 1 for k in keys),
          miss[:5])


def _applied(raw, md5, e, man):
    """Стойка «после выкладки» набора: файлы OpenMapInfo — новые, база — в .bak_<метка> → {путь: прежние байты} для возврата."""
    saved = {}
    for g in FIELD:
        r = g + BS + OPEN
        saved[r] = raw[r]
        raw[r + ".bak_" + man["tag"]], md5[r + ".bak_" + man["tag"]] = raw[r], _md5(raw[r])
        nb = e.new_bytes()[r]
        raw[r], md5[r] = nb, _md5(nb)
    return saved


def _restore(raw, md5, saved):
    for r, b in saved.items():
        raw[r], md5[r] = b, _md5(b)


def _offline_r40(check, raw, md5, cli):
    """★ Ревизия 40 (20.11.2026): В-1 непрощаемые причины отката, С-1 запись после отказов, С-2 пометки установки патчей, мелочи 2/4/5/6."""
    from domains import shopcs
    from domains.cs_kinds import mapdata as M
    # --- В-1: откат с --held-ok (post_stop_guard) не прощает «персонажи на карте» и «открытых больше COUNT»
    items = [("map.open", {"map": 6, "use": 1})]
    e = _ev(items)
    cs, man = _cs_man(e, 9491, items)
    items_c = [("map.open", {"map": 1, "use": 0})]
    with _Env(hold={1: []}):
        e_c = _ev(items_c)
    cs_c, man_c = _cs_man(e_c, 9492, items_c)
    sv = (shopcs.get, shopcs.held_guard)
    shopcs.held_guard = lambda c: ([], None)
    try:
        saved = _applied(raw, md5, e, man)
        try:
            shopcs.get = lambda i: cs
            with _Env(hold={6: [(75040, 1, "Carol", "CharPos")]}):
                g_hold = shopcs.post_stop_guard(9491, "rollback", True)
        finally:
            _restore(raw, md5, saved)
        saved = _applied(raw, md5, e_c, man_c)
        thr0 = {g: raw[g + BS + THR] for g in GS3}
        try:
            for g in GS3:
                raw[g + BS + THR], md5[g + BS + THR] = thread(3), _md5(thread(3))    # COUNT снижен вручную после выкладки
            shopcs.get = lambda i: cs_c
            with _Env(hold={1: []}):
                g_cnt = shopcs.post_stop_guard(9492, "rollback", True)
                g_cnt_plain = shopcs.post_stop_guard(9492, "rollback", False)
        finally:
            _restore(raw, md5, saved)
            for g in GS3:
                raw[g + BS + THR], md5[g + BS + THR] = thr0[g], _md5(thr0[g])
    finally:
        shopcs.get, shopcs.held_guard = sv
    soft = ["звание Герой (190): выключение при 2 держателях (A (1/1, CharFame))"]
    check("ревизия 40 В-1: откат с --held-ok — «персонажи на закрываемой откатом карте» и «открытых карт больше ThreadInfo COUNT» перепроверка "
          "после остановки НЕ прощает (обе — в guard_hard), а обычная причина второго подтверждения — прощаемая",
          any("Carol" in x and "вход в мир не состоится" in x for x in g_hold)
          and any("больше ThreadInfo.ini COUNT 3" in x for x in g_cnt) and g_cnt == g_cnt_plain
          and shopcs.guard_hard(g_hold) and shopcs.guard_hard(g_cnt) and shopcs.guard_hard(soft) == []
          and shopcs.guard_hard(["карты: персонажи не прочитаны (x) — вслепую не делается"]), (g_hold, g_cnt, g_cnt_plain))
    # --- С-1: запись Use — после всех отказов (отказанная позиция не меняет итог набора для COUNT)
    thr0 = {g: raw[g + BS + THR] for g in GS3}
    sim = "GameServer" + BS + "MapData_Info" + BS + "Closed.sim"
    sim0 = md5[sim]
    try:
        for g in GS3:
            raw[g + BS + THR], md5[g + BS + THR] = thread(4), _md5(thread(4))
        with _Env(hold={1: [(75001, 1, "Alice", "CharPos")]}):
            e1 = _ev([("map.open", {"map": 6, "use": 1}), ("map.open", {"map": 1, "use": 0})])
        for g in GS3:
            raw[g + BS + THR], md5[g + BS + THR] = thread(5), _md5(thread(5))
        md5.pop(sim)
        e2 = _ev([("map.open", {"map": 6, "use": 1}), ("map.open", {"map": 4, "use": 1})])
    finally:
        md5[sim] = sim0
        for g in GS3:
            raw[g + BS + THR], md5[g + BS + THR] = thr0[g], _md5(thr0[g])
    check("ревизия 40 С-1: COUNT 4, открыто 4 — «открыть 6» + отказанное «закрыть 1» (персонаж) — у открытия отказ COUNT (запись отказанной "
          "позиции в итог не попала); COUNT 5 — отказанное «открыть 6» (нет .sim) не даёт ложного отказа COUNT соседнему открытию",
          any("больше ThreadInfo.ini COUNT 4" in x for x in e1.positions[0]["errors"]) and e1.positions[1]["errors"]
          and any("Closed.sim" in x for x in e2.positions[0]["errors"]) and not e2.positions[1]["errors"],
          (e1.positions[0]["errors"], e2.positions[0]["errors"][:1], e2.positions[1]["errors"]))
    # --- С-2 / мелочи 4, 5: пометки установки патчей, LoginManager Game_<n>, Total и «закрыта» по каждой копии
    note = "Ch2_GameServer: P40_CrystalTeleportGate включён в patches.ini, а при последнем запуске выключен — установка не подтверждена, взят по patches.ini"
    with _Env(cfg={"Ch2_GameServer": {"notes": [note]}}, lm={"0_0": set(range(7)), "0_1": set(range(6))}):
        w1 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 4100})])
        o1 = _ev([("map.open", {"map": 6, "use": 1})])
    with _Env(lm="fail"):
        o2 = _ev([("map.open", {"map": 6, "use": 1})])
    tot = "Indun_GameServer" + BS + TOT
    t0 = raw[tot]
    try:
        tb = t0.replace(b"[PORTAL_INFO_1]\r\nUSE = 1", b"[PORTAL_INFO_1]\r\nUSE = 0")
        raw[tot], md5[tot] = tb, _md5(tb)
        w2 = _ev([("warp.cost", {"from": 0, "to": 1, "cost": 4200})])
    finally:
        raw[tot], md5[tot] = t0, _md5(t0)
    check("ревизия 40 С-2, мелочи 4/5: пометка «установка не подтверждена» из журнала патчей — в предупреждениях позиции; открытие карты без "
          "адреса Game_6 в канале 0_1 LoginManager — предупреждение «в мир не войдёт», адреса не прочитаны — предупреждение «не проверен»; "
          "у Indun нет Total USE карты-цели — предупреждение с копией Indun_GameServer",
          note in _warns(w1) and not _errs(o1) and any("нет адреса Game_6 (0_1)" in w for w in _warns(o1))
          and any("Game_<n> LoginManager не прочитаны" in w for w in _warns(o2))
          and any("Total_PortalConfig с USE ≠ 0 (Indun_GameServer)" in w for w in _warns(w2)), (_warns(w1), _warns(o1), _warns(w2)))
    # --- В-2 (часть офлайн): пометка «нет таблицы P108» — в предупреждениях закрытия; новые пути — в списке отказа
    with _Env(hold={1: [(75050, 2, "Dave", "Charinpos (CharPos.Poridx 22)"), (75051, 0, "Eve", "P108 4б2 (Cporidx 10)")]}):
        c1 = _ev([("map.open", {"map": 1, "use": 0})])
    with _Env(hold={1: []}, notes=["таблицы dbo.AsdaDungeonRelogPoint нет (SQL P108 не применён) — перенос с турнирных карт шагом 4б2 "
                                   "рестарта не учтён, его и не будет"]):
        c2 = _ev([("map.open", {"map": 1, "use": 0})])
    check("ревизия 40 В-2 (офлайн): закрытие карты — отказ и для входа через Charinpos и для переноса P108 (имена в списке); нет таблицы P108 — "
          "пометка в предупреждениях, правка проходит", any("Dave (75050/2, Charinpos (CharPos.Poridx 22))" in x and "Eve" in x for x in _errs(c1))
          and not _errs(c2) and any("AsdaDungeonRelogPoint нет" in w for w in _warns(c2)), (_errs(c1), _warns(c2)))
    # --- мелочь 2: одно правило «новая или хуже базы»
    over5, over6 = openmap([1, 1, 1, 1, 1, 0, 0]), openmap([1, 1, 1, 1, 1, 0, 1])
    check("ревизия 40 мелочь 2: open_count_issue с базой — база уже 5 > COUNT 4: те же 5 — не новая неисправность, 6 — хуже базы (отказ); без "
          "базы — неисправность; MapCount 256 (байт 0) — файл не действует, открытых 0 (мелочь 3)",
          M.open_count_issue(over5, thread(4), 23, "GameServer", base_raw=over5) is None
          and M.open_count_issue(over6, thread(4), 23, "GameServer", base_raw=over5) is not None
          and M.open_count_issue(over5, thread(4), 23, "GameServer") is not None
          and M.open_state(over5.replace(b"MapCount = 5", b"MapCount = 256"), 23)["count"] == 0
          and M.open_count(over6.replace(b"MapCount = 5", b"MapCount = 256"), thread(4), 23)[0] == 0)
    # --- мелочь 6: справка не падает, если ключевая таблица не читается
    rel = "Ch2_GameServer" + BS + THR
    h0 = md5[rel]
    try:
        md5[rel] = M.UNREAD
        ls = M.lookup("maps", "")
    finally:
        md5[rel] = h0
    check("ревизия 40 мелочь 6: ThreadInfo копии Ch2 не читается — справка списка карт строится, у копии потоков нет, причина в read_errors",
          len(ls["rows"]) == len(MAPS) and ls["threads"]["Ch2_GameServer"] is None and ls["threads"]["GameServer"] == 5
          and any("ThreadInfo.ini не прочитан" in x for x in ls["read_errors"]), (ls.get("read_errors"), ls.get("threads")))
    _ = cli


def _offline_r40_pure(check):
    """★ Ревизия 40: ParseCrystals побуквенно (Н-2), кнопки 5477 (Н-1), журнал патчей и patch_cfg по факту установки (С-2), N MapInfo копии,
    адреса LoginManager (мелочь 4) — без стойки (подмена stack_text и журнала)."""
    from domains import srvtables
    from domains.cs_kinds import mapdata as M
    many = ";".join("%d:1" % (i + 1) for i in range(64))
    pc = M.parse_crystals
    check("ревизия 40 Н-2: Crystals как ParseCrystals — тип 1…1023 (1023 — да, 1024 — нет), ≤ 64 записей (64 — да, 65 — нет, повтор типа — тоже "
          "запись, действует первая), «46 :3» (пробел до «:») — нет, «+46:3» (wcstol) — да, карты 0…29, ключ длиннее 511 знаков обрезается",
          pc("1023:3") == {1023: {3}} and pc("1024:3") is None and pc(many) is not None and pc(many + ";65:2") is None
          and pc("46:3;46:5") == {46: {3}} and pc("46 :3") is None and pc("+46:3") == {46: {3}} and pc("46:30") is None
          and pc(" ; 46: 3 , 4 ;") == {46: {3, 4}} and pc("46:3x") is None and pc("") is None
          and pc("46:3;" + "4" * 520 + ":1") is None and pc("46:3" + " " * 520 + ";x") == {46: {3}})
    btn = M.crystal_buttons()
    check("ревизия 40 Н-1: кнопки 5477 клиента — 30031 по WarpList и с картой в коде: у Эллы (ella, NPC 107) кнопка 30037 → карта 5 («Забытая "
          "Лощина»); таблица кодов = game_main.c (30033/30040 → 3, 30036 → 4, 30037 → 5, 30039/30041 → 0, 30042 → 7, 30063 → 21, 30064 → 22)",
          any(b[0] == "ella" and b[4] == 5 for b in btn) and M.CRYSTAL_FIXED == {30033: 3, 30036: 4, 30037: 5, 30039: 0, 30040: 3, 30041: 0,
                                                                                  30042: 7, 30063: 21, 30064: 22},
          [b for b in btn if b[0] == "ella"])
    log = "\r\n".join(["[1] старт", "[2] Хост   : старый", "[3]   [MISMATCH] P40_CrystalTeleportGate — x", "[3] === итог: применено 1, пропущено 0, ошибок 1 ===",
                       "[4] AsdaPatch — старт 2026-11-20 10:00:00, PID 5", "[5] Хост   : H:\\v2\\GameServer\\GameServer.exe",
                       "[6]     P30: слотов карт 23 -> 24 (номера 0…23); массив перенесён",
                       "[6]   [OK]       P30_MapSlots — слоты", "[6]   [MISMATCH] P40_CrystalTeleportGate — гейт   * НЕ ПОСТАВЛЕН",
                       "[6]   [ВЫКЛ]     P120_MineTravel — шахта", "[7] === итог: применено 1, пропущено 1, ошибок 1 ===", "[8]   [OK] P40_CrystalTeleportGate позже"])
    st = M.patch_log_state(log)
    ini = ("[General]\r\nMasterEnable=1\r\n[P30_MapSlots]\r\nMaxMaps=30\r\n[P40_CrystalTeleportGate]\r\nCrystals=\"46:7,0,1\"\r\n")
    logs = {"GameServer": st, "Indun_GameServer": "fail", "Ch2_GameServer": dict(st, P40_CrystalTeleportGate="ok", P120_MineTravel="ok")}
    sv = (srvtables.stack_text, M.patch_log)

    def plog(g, ttl=60):
        if logs[g] == "fail":
            raise ValueError("%s: журнала патчей нет" % g)
        return logs[g]
    try:
        srvtables.stack_text = lambda rel, ttl=60: ini
        M.patch_log = plog
        cfg = M.patch_cfg(ttl=0)
    finally:
        srvtables.stack_text, M.patch_log = sv
    gs, ind, ch2 = cfg["GameServer"], cfg["Indun_GameServer"], cfg["Ch2_GameServer"]
    check("ревизия 40 С-2: журнал патчей — блок ПОСЛЕДНЕГО запуска (прежний [MISMATCH] и строки после итога не в счёт): P30 [OK] со слотами 24, "
          "P40 [MISMATCH], P120 [ВЫКЛ]; patch_cfg: P40 не встал — гейт не действует (пометка «не встал»), P120 [ВЫКЛ] при включённом — по "
          "patches.ini с пометкой «не подтверждена»; журнал не прочитан — по patches.ini с пометкой; Crystals в кавычках — как GetPrivateProfileString",
          st == {"P30_MapSlots": "ok", "P40_CrystalTeleportGate": "bad", "P120_MineTravel": "off", "slots": 24, "total": True}
          and not gs["p40"] and not gs["open_gate"] and gs["p30_ok"] and gs["log_slots"] == 24 and gs["p120"]
          and any("P40_CrystalTeleportGate при последнем запуске не встал" in n for n in gs["notes"])
          and any("P120_MineTravel включён в patches.ini, а при последнем запуске выключен" in n for n in gs["notes"])
          and ind["p40"] and any("установка патчей не подтверждена (журнал патчей: Indun_GameServer: журнала патчей нет)" in n for n in ind["notes"])
          and not ind["p30_ok"] and ch2["p40"] and ch2["crystals"] == {46: {7, 0, 1}} and ch2["notes"] == [] and ch2["slots"] == 30
          and M.patch_log_state("нет паспорта") is None and M.declared_maps(b"24\r\n0\tA") == 24 and M.declared_maps(b"x") == -1,
          (st, gs, ind["notes"], ch2))
    top = "[SERVERGROUP_TOTAL]\r\nCOUNT=1\r\n[SERVERGROUP_0_CHANNEL_TOTAL]\r\nCOUNT=2\r\nGAMECOUNT=4\r\n"
    ch = {0: "".join("[Game_%d]\r\nIP=10.0.0.1\r\nPORT=1\r\n" % k for k in range(6)),
          1: "[Game_0]\r\nIP=10.0.0.1\r\n[Game_1]\r\nIP=\r\n[Game_2]\r\nIP=10.0.0.1\r\n"}
    try:
        srvtables.stack_text = lambda rel, ttl=60: top if rel.endswith("\\GameServerIP.ini") else ch[int(rel.rsplit("_", 2)[-2])]
        lm = M.lm_game_maps(ttl=0)
        srvtables.stack_text = lambda rel, ttl=60: (_ for _ in ()).throw(OSError("нет файла"))
        lm_bad = M.lm_game_maps(ttl=0)
    finally:
        srvtables.stack_text = sv[0]
    check("ревизия 40 мелочь 4: адреса LoginManager — Game_j только j < GAMECOUNT и до первого пустого IP (как sub_4046E0); не прочитаны — None с "
          "причиной", lm == {"0_0": {0, 1, 2, 3}, "0_1": {0}} and lm_bad is None and M.lm_game_maps.last_error, (lm, M.lm_game_maps.last_error))


# ---------------------------------------------------------------------------------------------------------- Joy1 на LocalDB
JOY_SQL = r"""
CREATE SCHEMA adm
GO
CREATE TABLE dbo.CharPos (Userindex INT, Charidx INT, Charname VARCHAR(20), Usernum INT, Poridx TINYINT, Posx SMALLINT, Posy SMALLINT,
                          Cporidx TINYINT, State TINYINT)
CREATE TABLE dbo.Del_CharPos (Edate DATETIME, Userindex INT, Charidx INT, Charname VARCHAR(20), Usernum INT, Poridx TINYINT, Posx SMALLINT,
                              Posy SMALLINT, Cporidx TINYINT, State TINYINT)
CREATE TABLE dbo.VillagePos (Userindex INT, Charidx INT, Villageidx TINYINT)
CREATE TABLE dbo.Del_VillagePos (Edate DATETIME, Userindex INT, Charidx INT, Villageidx TINYINT)
CREATE TABLE dbo.Charinpos (Userindex INT, Charidx INT, Channel TINYINT, Poridx TINYINT, Posx SMALLINT, Posy SMALLINT)
CREATE TABLE adm.CharRestored (Userindex INT, Charidx INT, Edate DATETIME)
CREATE TABLE dbo.AsdaDungeonRelogPoint (Mapidx TINYINT, Kind CHAR(1), Poridx TINYINT, Posx SMALLINT, Posy SMALLINT)
GO
INSERT dbo.AsdaDungeonRelogPoint VALUES (8, 'E', 8, 129, 282), (10, 'R', 2, 440, 420), (11, 'R', 6, 72, 273)
INSERT dbo.CharPos VALUES (75101, 0, 'Plain', -1, 2, 10, 10, 2, 3), (75102, 0, 'Quiz', -1, 22, 5, 5, 22, 3), (75103, 0, 'NoRow', -1, 20, 5, 5, 20, 3),
                          (75104, 0, 'Arena', 7, 1, 300, 300, 10, 1), (75105, 0, 'ArenaOff', -1, 1, 300, 300, 10, 3),
                          (75106, 0, 'Arena2', -1, 3, 1, 1, 11, 1), (75107, 0, 'Quiz7', -1, 19, 5, 5, 19, 3)
INSERT dbo.Charinpos VALUES (75102, 0, 0, 2, 1, 1), (75107, 0, 0, 7, 1, 1)
INSERT dbo.VillagePos VALUES (75101, 0, 3)
INSERT dbo.Del_CharPos VALUES ('2026-11-01 10:00', 75110, 1, 'DelQuiz', -1, 22, 5, 5, 22, 3), ('2026-11-01 10:00', 75111, 1, 'DelArena', 3, 3, 5, 5, 10, 1),
                              ('2026-11-02 10:00', 75112, 1, 'DelBack', 3, 3, 5, 5, 10, 1)
INSERT dbo.Charinpos VALUES (75110, 1, 0, 2, 1, 1)
INSERT adm.CharRestored VALUES (75112, 1, '2026-11-02 10:00')
"""


def joy_sql(check, ldb):
    """★ Ревизия 40 В-2: НАСТОЯЩИЕ запросы mapdata.joy_holders на подставной Joy1 (LocalDB): Charinpos для CharPos.Poridx 19/20/22 (строки нет —
    карта 0), перенос P108 4б2 «бывших в игре» с турнирных 10/11, корзина без adm.CharRestored; без таблицы P108 — пропуск с пометкой."""
    import secrets
    from core import db
    from domains.cs_kinds import mapdata as M
    name = "AsdaJoyR40_" + secrets.token_hex(4)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    saved = db._override.get("game")
    try:
        cn = ldb(name)
        for batch in re.split(r"^\s*GO\s*$", JOY_SQL, flags=re.M):
            if batch.strip():
                cn.cursor().execute(batch)
        db.set_override("game", lambda database: ldb(name))
        h = M.joy_holders([0, 2, 6, 7])
        n1 = list(M.joy_holders.notes)
        cn.cursor().execute("DROP TABLE dbo.AsdaDungeonRelogPoint")
        h2 = M.joy_holders([2, 6])
        n2 = list(M.joy_holders.notes)
        cn.close()
    finally:
        db.set_override("game", saved)
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
        except Exception:
            pass
        m.close()
    who = {k: sorted((x[2], x[3]) for x in v) for k, v in (h or {}).items()}
    check("ревизия 40 В-2 (НАСТОЯЩИЙ SQL на LocalDB): карта 2 — CharPos, Charinpos (Poridx 22 → 2), корзина через Charinpos, P108 Cporidx 10 → 2 "
          "(в игре и корзина без восстановления), восстановленный набор корзины — нет, «не в игре» (Usernum −1, State 3) — нет; карта 0 — "
          "Poridx 20 без строки Charinpos; карта 6 — P108 Cporidx 11 (State 1); карта 7 — Charinpos 19 → 7; без таблицы P108 — переносов нет, "
          "пометка", h is not None and n1 == []
          and who[2] == sorted([("Plain", "CharPos"), ("Quiz", "Charinpos (CharPos.Poridx 22)"), ("DelQuiz [Del_CharPos 2026-11-01 10:00]",
                                                                                                      "Charinpos (Del_CharPos.Poridx 22)"),
                                ("Arena", "P108 4б2 (Cporidx 10)"), ("DelArena [Del_CharPos 2026-11-01 10:00]", "P108 4б2 (Del_CharPos.Cporidx 10)")])
          and who[0] == [("NoRow", "Charinpos (CharPos.Poridx 20)")] and who[6] == [("Arena2", "P108 4б2 (Cporidx 11)")]
          and who[7] == [("Quiz7", "Charinpos (CharPos.Poridx 19)")]
          and h2 is not None and sorted(x[2] for x in h2[2]) == ["DelQuiz [Del_CharPos 2026-11-01 10:00]", "Plain", "Quiz"] and h2[6] == []
          and any("AsdaDungeonRelogPoint нет" in x for x in n2), (who, M.joy_holders.last_error, n2))


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox(check, ldb):
    """Набор «Карты» целиком: только сервер (реестр карт — необязательная клиентская правка), второе подтверждение, перепроверка, откат."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs, shopdata as SD
    joy_sql(check, ldb)                                  # ★ ревизия 40 В-2: настоящий SQL joy_holders на подставной Joy1
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with X.sandbox(ldb) as (st, env), _Env(hold={1: []}):
        files = stack_files()
        for rel, b in files.items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        ev_cli = SD.Client.load()
        ev_cli.crystals, ev_cli.mapreg = [], {m[0]: USE[m[0]] for m in MAPS}
        try:
            cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.8", note="самотест песочницы А4.8: карты")["result"]["id"]
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="warp.cost", params={"from": 0, "to": 1, "cost": 4000})
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="map.open", params={"map": 1, "use": 0})
            X._run(ctx, "shop.cs_check", cs=cid)
            cs = shopcs.get(cid)
            _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
            X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
            check("песочница А4.8: только сервер (реестр карт — необязательная клиентская правка), сильная правка — без второго подтверждения отказ, "
                  "владелец — утверждён", cs["check"]["ok"] and cs["check"]["server_needed"] and not cs["check"]["client_needed"]
                  and no and "второе подтверждение" in no and shopcs.get(cid)["status"] == "approved", (cs["check"]["errors"], no))
            X._run(ctx, "shop.cs_server_dry", cs=cid)
            man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
            want = sorted([g + BS + WARP for g in GS3] + [g + BS + OPEN for g in FIELD])
            check("песочница А4.8: сухой прогон НАСТОЯЩЕГО deploy_changeset — MapWarpCost ×3 и OpenMapInfo ×2 (копии поля)",
                  shopcs.get(cid)["server_state"] == "dry_ok" and sorted(man["files"]) == want, sorted(man["files"]))
            calls0 = len(st.calls)
            o0 = open(st.path("GameServer" + BS + OPEN), "rb").read()
            with _Env(hold={1: []}, extra={1: [(75020, 1, "Late", "CharPos")]}):
                _r, e_g = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            check("песочница А4.8 (перепроверка): после проверки на закрываемой карте появился персонаж — выкладка отказ без объявления, файлы прежние",
                  e_g and "Late" in e_g and len(st.calls) == calls0 and open(st.path("GameServer" + BS + OPEN), "rb").read() == o0, e_g)
            calls1 = len(st.calls)
            with _Env(hold={1: []}, extra={1: [(75021, 1, "Late2", "CharPos")]},
                      when=lambda: bool(st.calls) and st.calls[-1].startswith("deploy:")):
                _r, e_s = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            check("песочница А4.8 (после остановки): персонаж появился за время объявления — перепроверка после остановки отказ «… Late2», файлы не "
                  "тронуты, прежняя стойка поднята", e_s and "перепроверка набора после остановки стойки" in e_s and "Late2" in e_s
                  and st.calls[calls1:] == ["announce", "stop", "deploy:apply", "bring_up"]
                  and open(st.path("GameServer" + BS + OPEN), "rb").read() == o0, (e_s, st.calls[calls1:]))
            r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            ok = (all(_cell(open(st.path(g + BS + WARP), "rb").read(), 0, 1) == 4000 for g in GS3)
                  and all(_use(open(st.path(g + BS + OPEN), "rb").read(), 1) == 0 for g in FIELD)
                  and not os.path.isfile(st.path("Indun_GameServer" + BS + OPEN))
                  and _cell(open(st.path("Indun_GameServer" + BS + WARP), "rb").read(), 0, 2) == 700)
            check("песочница А4.8: выложено рестартом — цена ×3 GS (у Indun своя ячейка [0][2] сохранена), карта закрыта в копиях поля, у Indun "
                  "OpenMapInfo не появился", r and shopcs.get(cid)["server_state"] == "applied" and ok, e)
            # ★ ревизия 40 В-1: откат вернёт открытую карту, а потоков (ThreadInfo COUNT, снижен вручную) не хватит — отказ и с --held-ok
            thr_p = {g: st.path(g + BS + THR) for g in GS3}
            calls2 = len(st.calls)
            try:
                for g in GS3:
                    open(thr_p[g], "wb").write(thread(3))
                _r, e_h = X._try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart", held_ok="held")
            finally:
                for g in GS3:
                    open(thr_p[g], "wb").write(files[g + BS + THR])
            check("песочница А4.8 (ревизия 40 В-1): откат при нехватке потоков — отказ «откат не делается и с ключом --held-ok … GameServer выйдет при "
                  "старте» до объявления, стойка не тронута", e_h and "откат не делается и с ключом --held-ok" in e_h and "COUNT 3" in e_h
                  and len(st.calls) == calls2 and shopcs.get(cid)["server_state"] == "applied", (e_h, st.calls[calls2:]))
            X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
            back = all(open(st.path(rel), "rb").read() == b for rel, b in files.items() if rel.endswith((WARP, OPEN)))
            check("песочница А4.8: откат сервера — MapWarpCost ×3 и OpenMapInfo ×2 вернулись побайтно", back and shopcs.get(cid)["server_state"] == "rolled_back",
                  shopcs.get(cid)["server_state"])
        except ops.OpRefused as ex:
            check("песочница А4.8: путь набора без отказа", False, str(ex)[:400])


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны на живой стойке (SSH), Joy1 (SELECT) и живом порту (настоящий генератор реестра карт)."""
    from core import config
    from domains import shopcs, shopdata as SD
    from domains.cs_kinds import mapdata as M
    if config.get().on_server:
        return check("живой самотест А4.8 — с ПК (SSH и порт)", True)
    rels = [g + BS + x for g in GS3 for x in (WARP, MI, THR, TOT)] + [g + BS + OPEN for g in GS3]
    md = SD.live_md5(rels)
    check("живая стойка А4.8: MapWarpCost / MapInfo / ThreadInfo / Total ×3 есть, OpenMapInfo — в копиях поля и НЕТ у Indun, поле = Ch2 (MapWarpCost, "
          "OpenMapInfo), у Indun своя MapWarpCost", all(md[g + BS + x] != "none" for g in GS3 for x in (WARP, MI, THR, TOT))
          and md["Indun_GameServer" + BS + OPEN] == "none" and all(md[g + BS + OPEN] != "none" for g in FIELD)
          and md["GameServer" + BS + WARP] == md["Ch2_GameServer" + BS + WARP] and md["GameServer" + BS + OPEN] == md["Ch2_GameServer" + BS + OPEN],
          {r: h[:8] for r, h in md.items()})
    ls = M.lookup("maps", "")
    lk = M.lookup("map", "3")
    check("живая справка А4.8: карты MapInfo (≥ 24), потоки ThreadInfo и открытые по копиям поля, patches.ini прочитан (P40 действует), карточка "
          "Альпии (3): кристаллы P40 (NPC 46), подписи кнопок, персонажи из Joy1, цены строки ×3 копии",
          len(ls["rows"]) >= 24 and not ls["cfg_error"] and all(ls["threads"][g] for g in FIELD) and ls["p40"] and all(ls["p40"].values())
          and lk["crystals"] and any(c["type"] == 46 for c in lk["crystals"]) and lk["captions"] and lk["holders"] is not None
          and len(lk["warp_row"]) >= 24, (ls.get("cfg_error"), lk.get("crystals"), lk.get("holders_error")))
    cur = {r["to"]: r["cost"]["GameServer"] for r in lk["warp_row"]}
    closed = [r for r in ls["rows"] if r["editable"] and r["use"].get("GameServer") == 0 and r["type"] in (0, 1, 3)]
    items = [{"pos": 1, "kind": "warp.cost", "params": {"from": 3, "to": 7, "cost": cur[7] + 1}}]
    if closed:
        items.append({"pos": 2, "kind": "map.open", "params": {"map": closed[0]["id"], "use": 1}})
    cli = SD.Client.load(force=True)
    ev = SD.Eval(items, False, SD.Snap(), cli).run()
    s = ev.summary()
    nfiles = 3 + (2 if closed else 0)
    check("живая оценка набора А4.8 (Альпия → Пламения +1%s): без ошибок, сервер — %d файлов, клиент — только необязательный реестр карт"
          % (", открыть закрытую карту %s" % closed[0]["id"] if closed else "", nfiles),
          not s["errors"] and s["server"]["count"] == nfiles and not s["client_needed"], (s["errors"][:3], s["server"]["count"]))
    tracked = [M.REG_JSON, M.REG_H]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0) if s["client"] else {"errors": [], "files": {}}
    after = {p: SD.md5f(p) for p in tracked}
    check("живой план клиента А4.8: НАСТОЯЩИЙ asda_map_registry — реестр и AsdaMapRegistry.h (если карта открывается), ничего не записано (md5 порта "
          "до = после)", not plan["errors"] and before == after and (not closed or sorted(plan["files"]) == sorted(tracked)), plan["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_a48_live_")
    try:
        man = {"tag": "20261120_a48live", "changeset": 0, "files": {}}
        for rel, data in sorted(ev.new_bytes().items()):
            lp = os.path.join(tmp, rel.replace(BS, os.sep))
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            open(lp, "wb").write(data)
            man["files"][rel] = {"local": lp.replace(BS, "/"), "base": ev.snap.md5[rel], "new": SD.md5b(data)}
        mp = os.path.join(tmp, "manifest.json")
        json.dump(man, open(mp, "w", encoding="utf-8"))
        b0m = SD.live_md5(sorted(man["files"]))
        rc, out = shopcs.run_deploy(mp)
        b1m = SD.live_md5(sorted(man["files"]))
        check("НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH (MapWarpCost ×3%s): «всё готово к --apply», стойка не изменилась"
              % (", OpenMapInfo ×2" if closed else ""), rc == 0 and "всё готово" in out and b0m == b1m, (rc, out[-400:]))
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tmp
        try:
            cs = {"id": 9948, "items": items, "check": s}
            _mp, mman = shopcs.build_server_out(cs, ev)
            g = M.apply_guard(cs, "apply")
            gr = M.apply_guard(cs, "rollback")
        finally:
            SD.CS_DIR = saved_dir
        check("живая перепроверка А4.8 (по настоящему манифесту): выкладка и откат — опасных переходов нет (закрываемых карт нет, потоков хватает)",
              g == [] and gr == [], (g, gr))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    d = {x["key"]: x for x in SD.divergence(limit=2000, areas=("mapdata",))["sections"]}["maps"]["rows"]
    check("живые расхождения А4.8: таблицы прочитаны, реестр карт порта = OpenMapInfo, потоков хватает (свои цены Indun — сведения)",
          not any("не прочитаны" in r["why"] or "server.open_use" in r["why"] or "ThreadInfo" in r["why"] for r in d), d[:5])
