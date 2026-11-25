# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_live_a5.py — самотест шага А5.2 «Игроки живьём» (21.11.2026; domains/live.py, domains/charmove.py, мост P127 v83).

offline(check) — на подменах моста и Joy1: призыв / возврат группы монстров (live.mob_pop / live.mob_return: служебная учётка, GM-флаг,
                 узел v83 в режиме исполнения, группа, режим, подтверждение, команда моста и её аргументы), перенос «к персонажу»
                 (char.move режим char — аналог 6012 / 6014: права, сам к себе, цель вне игры, карта и клетка цели), «кто в игре»
                 с названием карты, права, белый список команд в adm.BridgeEnqueue, исходники DLL v83 (команды, гейты стока, стенд P1–P8,
                 выкладчик deploy_p127d по закреплённой сборке), веб (раздел «Кто в игре», переводы).
live(check)    — только чтение и сухие предпросмотры: узлы моста и присутствие, призыв на живых узлах v82 — честный отказ «нужен v83»,
                 перенос к отсутствующему — отказ. Ничего не отправляется ни игрокам, ни в NpcServer. Побочных эффектов при импорте нет.
"""
import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
AP = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch")


class _GR:
    """Подмена db.GameReader: CharGmInfo — есть ли строка у учётки."""
    gm = {1, 2}

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def rows(self, sql, params=()):
        if "CharGmInfo" in sql:
            return [{"x": 1}] if params and int(params[0]) in _GR.gm else []
        return []


def _mob_offline(check):
    from core import bridge, db, ops, audit, auth
    import domains.live as L
    saved = (bridge.live_row, bridge.call, db.GameReader, audit.write, L.map_groups)
    calls, rows = [], []
    cli = ops.Ctx(None, "cli:t", "owner", "", "cli")
    row = {"node": "GameServer", "Userindex": 2, "Charidx": 0, "charname": "GM_Test", "map": 3, "x": 120, "z": 340, "ver": 83}
    GROUPS = {12: {"total": 3, "event": 3}, 0: {"total": 16, "event": 0}, 20: {"total": 4, "event": 1}}

    def live_row(uid, idx, min_ver=bridge.LIVE_VER):
        calls.append(("live_row", uid, idx, min_ver))
        r = dict(row, Userindex=uid)
        return r if idx == 0 and uid in (2, 4) and min_ver <= int(row["ver"]) else None
    L.map_groups = lambda node, m, **k: {"file": "Alpen.svr", "npc": "NpcServer", "groups": GROUPS}

    def call(op, uid, idx, node, args="", ttl=30, by="", timeout=None):
        calls.append(("call", op, uid, idx, node, args, ttl))
        return {"id": 501, "result": "6045 отправлен в NpcServer: группа 12, точка — у оператора (ответа у стока нет)"}
    try:
        bridge.live_row, bridge.call, db.GameReader = live_row, call, _GR
        audit.write = lambda *a, **k: rows.append((a[1], k.get("result"))) or 1

        def refused(name, p, ctx=cli, part=""):
            try:
                ops.run(ctx, name, p)
            except ops.OpRefused as ex:
                return part in str(ex)
            return False
        base = {"uid": 2, "idx": 0, "group": 12, "confirm": "mobs"}
        check("монстры: учётка > 5000 — отказ «только служебная учётка» (как оператор стока sub_52ECF0)",
              refused("live.mob_pop", dict(base, uid=6001), part="служебная учётка"))
        check("монстры: группа вне 0…65535, режим не 0/1 — отказ", refused("live.mob_pop", dict(base, group=70000), part="0…65535")
              and refused("live.mob_pop", dict(base, mode=2), part="неверный режим"))
        check("монстры: без подтверждения «mobs» — отказ «не откатывается»", refused("live.mob_pop", {"uid": 2, "idx": 0, "group": 12}, part="confirm = mobs")
              and refused("live.mob_return", {"uid": 2, "idx": 0, "group": 12}, part="confirm = mobs"))
        check("монстры: у учётки нет GM-флага (CharGmInfo) — отказ до моста (сток с P47 не выполнил бы)",
              refused("live.mob_pop", dict(base, uid=3), part="GM-флага") and not any(c[0] == "call" for c in calls))
        row["ver"] = 82
        check("монстры: узел моста v82 (без mob_pop) — отказ «нужен v83», команда не ставится",
              refused("live.mob_pop", base, part="v83+") and not any(c[0] == "call" for c in calls))
        row["ver"] = 83
        gm = ops.Ctx(None, "cli:gm", "gm", "", "cli")
        check("монстры: право server.monsters — владелец и администратор, у GM — отказ «нет права»",
              auth.PERMS["server.monsters"] == {"owner", "admin"} and refused("live.mob_pop", base, gm, "нет права"))
        pv = ops.run(cli, "live.mob_pop", dict(base, mode=1), dry=True)["preview"]
        ws = " | ".join(pv["warnings"])
        check("монстры (р42 С-1): предпросмотр — от GM_Test (карта 3, 120,340), честно: событийные возрождаются снова и снова до 6046, точка "
              "сдвинута до рестарта NpcServer, режим 1 — на своих точках роуминга, флаг — после перезахода",
              "GM_Test" in pv["text"] and "120,340" in pv["text"] and "снова и снова" in ws and "до рестарта NpcServer" in ws
              and "роуминга" in ws and "перезаход" in ws and "3 мобов" in ws, ws)
        pr = ops.run(cli, "live.mob_return", base, dry=True)["preview"]
        check("монстры (р42 С-1): 6046 — «живые мобы группы умрут», подпись «убрать (вернуть)»",
              any("умрут" in w for w in pr["warnings"]) and "убрать (вернуть)" in ops.REGISTRY["live.mob_return"].title)
        # ★ ревизия 42 В-1: группа без умолчания, нет группы — отказ, группа 0 / обычные мобы — только mobs0
        check("монстры (р42 В-1): номер группы не указан (пусто / нет ключа) — отказ «укажите номер группы»",
              refused("live.mob_pop", dict(base, group=""), part="укажите номер") and refused("live.mob_pop", {"uid": 2, "idx": 0, "confirm": "mobs"},
                                                                                                 part="укажите номер"))
        check("монстры (р42 В-1): группы нет на карте (по справке .svr) — отказ «ничего не сделает» со списком вызываемых групп",
              refused("live.mob_pop", dict(base, group=77), part="ничего не сделает") and refused("live.mob_pop", dict(base, group=77), part="12 (3)"))
        check("монстры (р42 В-1): группа 0 (обычные мобы) и смешанная группа без confirm = mobs0 — отказ «точка уйдёт … до рестарта стойки»; с mobs0 — "
              "предпросмотр с предупреждением про обычных мобов",
              refused("live.mob_pop", dict(base, group=0), part="mobs0") and refused("live.mob_pop", dict(base, group=20), part="mobs0")
              and any("обычные мобы группы (16)" in w for w in ops.run(cli, "live.mob_pop", dict(base, group=0, confirm="mobs0"), dry=True)["preview"]["warnings"]))
        adm = ops.Ctx(7, "adm1", "admin", "", "web")
        _GR.gm = {1, 2, 4}
        pa = ops.run(adm, "live.mob_pop", dict(base, uid=4), dry=True)["preview"]
        check("монстры (р42 Н-4): администратор от персонажа учётки владельца (2) — отказ, от другой служебной (4) — с предупреждением о журнале сервера",
              refused("live.mob_pop", base, adm, "только владелец") and any("учётки 4" in w for w in pa["warnings"]), pa["warnings"][:1])
        _GR.gm = {1, 2}
        calls.clear()
        r = ops.run(cli, "live.mob_pop", dict(base, mode=1))
        r2 = ops.run(cli, "live.mob_return", dict(base, mode=1))
        cs = [c for c in calls if c[0] == "call"]
        check("монстры: мостом — mob_pop «group=12;mode=1», mob_return «group=12» (режима нет), узел и персонаж цели, журнал ok, не откатывается",
              cs == [("call", "mob_pop", 2, 0, "GameServer", "group=12;mode=1", 20), ("call", "mob_return", 2, 0, "GameServer", "group=12", 20)]
              and "NpcServer" in r["message"] and rows[-1] == ("live.mob_return", "ok") and not ops.REGISTRY["live.mob_pop"].reversible
              and r2["result"]["cmd"] == 501, (cs, r["message"]))
        check("мост: команды mob_pop / mob_return в OPS, MOB_VER = 83", "mob_pop" in bridge.OPS and "mob_return" in bridge.OPS and bridge.MOB_VER == 83)
        sql = open(os.path.join(ROOT, "sql", "adminc_07_bridge.sql"), encoding="utf-8").read()
        check("SQL: adm.BridgeEnqueue пропускает mob_pop и mob_return", "'mob_pop', 'mob_return'," in sql or "'mob_pop', 'mob_return')" in sql)   # ★ А5.4: + event_*
    finally:
        bridge.live_row, bridge.call, db.GameReader, audit.write, L.map_groups = saved


def _svr_offline(check):
    """★ ревизия 42 В-1: разбор .svr (раскладка загрузчика NpcServer) и справка карты через подменные чтения."""
    import struct
    from core import ops
    import domains.live as L
    recs = [(444, 1), (444, 1), (0, 0), (0, 0), (0, 1)]
    data = struct.pack("<hh", len(recs), 0)
    for g, en in recs:
        b = bytearray(74)
        struct.pack_into("<H", b, 0x47, g)
        b[0x49] = en
        data += bytes(b)
    gr = L.parse_svr(data)
    check("справка групп (р42 В-1): .svr — int16 число записей, записи по 74 байта, +0x47 группа, +0x49 enable (1 — событийный)",
          gr == {444: {"total": 2, "event": 2}, 0: {"total": 3, "event": 1}}, gr)
    bad = False
    try:
        L.parse_svr(data[:-10])
    except ValueError:
        bad = True
    seen = []
    ini = '[MAPINFO]\nMonsterInfo_002="Conquester.svr"\nMonsterInfo_003="Alpen.svr"\n'
    info = L.map_groups("GameServer", 3, read_text=lambda p: seen.append(p) or ini, read_bytes=lambda p: seen.append(p) or data)
    ch2 = L.map_groups("Ch2_GameServer", 3, read_text=lambda p: seen.append(p) or ini, read_bytes=lambda p: seen.append(p) or data)
    try:
        L.map_groups("GameServer", 9, read_text=lambda p: ini, read_bytes=lambda p: data)
        miss = False
    except ops.OpRefused as ex:
        miss = "не прочитана" in str(ex)
    check("справка групп: обрезанный .svr — ошибка; ini\\MapInfo.ini MonsterInfo_003 в кавычках → Monster\\Alpen.svr папки NpcServer узла "
          "(Ch2_GameServer → Ch2_NpcServer); нет строки карты — «не прочитана», а не «групп нет»",
          bad and info["file"] == "Alpen.svr" and seen[1].endswith("\\NpcServer\\Monster\\Alpen.svr") and seen[0].endswith("\\NpcServer\\ini\\MapInfo.ini")
          and seen[3].endswith("\\Ch2_NpcServer\\Monster\\Alpen.svr") and ch2["npc"] == "Ch2_NpcServer" and miss, seen)
    check("справка групп: текст вызываемых — «444 (2), 0 (1)» по возрастанию", L.groups_text(info) == "0 (1), 444 (2)", L.groups_text(info))
    js = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("веб (р42 В-1): окно «Монстры» — поле группы пустое (без value), справка /api/mobgroups (право server.monsters), галочка mobs0",
          'class: "num", placeholder: T("номер") }' in js and "/api/mobgroups?node=" in js and 'zero.checked ? "mobs0" : "mobs"' in js
          and '@route("GET", r"/api/mobgroups", perm="server.monsters")' in srv)


def _move_offline(check):
    from core import bridge, ops
    from domains import charmove as M
    saved = (bridge.presence, bridge.nodes, M._allowed_maps)
    pres = [{"node": "GameServer", "Userindex": 9001, "Charidx": 1, "charname": "Target", "map": 7, "x": 135, "z": 188},
            {"node": "Ch2_GameServer", "Userindex": 9002, "Charidx": 0, "charname": "InDungeon", "map": 10, "x": 50, "z": 50},
            {"node": "Stale", "Userindex": 9003, "Charidx": 0, "charname": "Stale", "map": 3, "x": 50, "z": 50},
            {"node": "GameServer", "Userindex": 9004, "Charidx": 0, "charname": "Edge", "map": 3, "x": 0, "z": 50}]
    try:
        bridge.presence = lambda uid=None: [r for r in pres if uid is None or r["Userindex"] == uid]
        bridge.nodes = lambda: [{"node": "GameServer", "fresh": True, "mode": 1}, {"node": "Ch2_GameServer", "fresh": True, "mode": 1},
                                {"node": "Stale", "fresh": False, "mode": 1}]
        M._allowed_maps = lambda: {0, 3, 7, 12}

        def tp(p, role="owner"):
            try:
                w = []
                return M.target_pos(None, 5, 0, dict({"uid": 5, "idx": 0, "mode": "char"}, **p), role=role, warn=w), w
            except ops.OpRefused as ex:
                return str(ex), None
        r, w = tp({"to_uid": 9001, "to_idx": 1})
        check("перенос к персонажу (6012/6014): карта и клетка цели по мосту (7, 135,188), предупреждение «мог отойти»",
              r == (7, 135, 188, "к персонажу Target") and w and "мог отойти" in w[0], r)
        check("перенос к персонажу: у GM — отказ (как «своя точка»: владелец и администратор)", "только владельцу" in tp({"to_uid": 9001, "to_idx": 1}, "gm")[0])
        check("перенос к персонажу: к самому себе — отказ", "к самому себе" in tp({"to_uid": 5, "to_idx": 0})[0])
        check("перенос к персонажу: цель не в игре или на узле без пульса — отказ «клетка неизвестна»",
              "клетка неизвестна" in tp({"to_uid": 9999, "to_idx": 0})[0] and "клетка неизвестна" in tp({"to_uid": 9003, "to_idx": 0})[0])
        check("перенос к персонажу: цель в подземелье 10 — отказ (правила карты как у «своей точки»), клетка 0 — отказ",
              "туда перенос не делается" in tp({"to_uid": 9002, "to_idx": 0})[0] and "вне 1…511" in tp({"to_uid": 9004, "to_idx": 0})[0])
        # ★ ревизия 42 С-2: каналы
        r_off, w_off = tp({"to_uid": 9001, "to_idx": 1})
        pres.append({"node": "Ch2_GameServer", "Userindex": 5, "Charidx": 0, "charname": "Mover", "map": 7, "x": 10, "z": 10})
        r_ch = tp({"to_uid": 9001, "to_idx": 1})[0]
        pres[-1]["node"] = "GameServer"
        r_same, w_same = tp({"to_uid": 9001, "to_idx": 1})
        check("перенос к персонажу (р42 С-2): цель на GameServer, переносимый в игре на Ch2_GameServer — отказ «между каналами»; на том же узле — "
              "перенос; переносимый не в игре — предупреждение «канал при входе выберет игрок»",
              "между каналами" in str(r_ch) and r_same[0] == 7 and not any("канал" in w for w in w_same)
              and any("канал" in w for w in w_off), (r_ch, w_off))
    finally:
        bridge.presence, bridge.nodes, M._allowed_maps = saved


def _who_offline(check):
    from core import bridge
    import domains.live as L
    saved = (bridge.presence, bridge.nodes)
    try:
        bridge.presence = lambda uid=None: [{"node": "GameServer", "Userindex": 9001, "Charidx": 1, "charname": "T", "map": 3, "x": 1, "z": 2,
                                             "since": None, "seen": None}]
        bridge.nodes = lambda: [{"node": "GameServer", "fresh": True, "mode": 1, "ver": 82, "started": None, "heartbeat": None}]
        w = L.who()
        check("кто в игре: строки моста с названием карты (map_name из справочника) и узлы", w["presence"][0].get("map_name") is not None
              and isinstance(w["presence"][0]["map_name"], str) and w["nodes"][0]["node"] == "GameServer", w["presence"][0])
    finally:
        bridge.presence, bridge.nodes = saved


def _static_offline(check):
    rd = lambda p: open(p, encoding="utf-8-sig").read()
    src = rd(os.path.join(AP, "src", "patches", "p127_admin_bridge.cpp"))
    check("DLL v83: команды mob_pop / mob_return, гейты стока (UserIndex ≤ 5000, GM-флаг CUser+0x40B9F), связь NpcServer sub_4C0A60, "
          "sub_5646C0(kNetMoveMgr, 6045|6046, 5|4), коды 31–34, начала функций сверяются установкой",
          '{ L"mob_pop", kOpMobPop }' in src and "kOffGmFlag   = 0x40B9F" in src and "pNpcConn  = (PFN_NpcConn) 0x004C0A60" in src
          and "pop ? 6045 : 6046, pop ? 5 : 4" in src and "const DWORD mobFns[] = { 0x005646C0, 0x004C0A60 }" in src
          and "kOperatorMax" in src)
    # ★ А5.4: v84 = v83 + события/рейтинги (mob_pop / mob_return остаются) — версия сборки 83 или 84
    # ★ 22.11 (P129, v86; ревизия 60): «не ниже 83» — каждая следующая сборка поднимает версию
    check("DLL v83+: Config::kVersion ≥ 83 и та же Version в шаблоне ini",
          any("constexpr int kVersion = %d;" % v in rd(os.path.join(AP, "src", "Config.h")) and '{ L"Version", L"%d",' % v in rd(os.path.join(AP, "src", "Config.cpp"))
              for v in range(83, 200)))
    st = rd(os.path.join(AP, "tools", "stand_p127", "stand_p127.cpp"))
    check("стенд P127: проверки P1–P8 призыва / возврата (GM-флаг, тело 6045 / 6046, группа, режим, связь, отправка, учётка > 5000)",
          all(("P%d " % i) in st for i in range(1, 9)) and "ConnSendStub" in st)
    dep = rd(os.path.join(AP, "tools", "deploy_p127d.py"))
    want = re.search(r'WANT_DLL = "([0-9a-f]{32})"', dep).group(1)
    built = os.path.join(AP, "tools", "p127_data", "AsdaPatch_v83p127d_%s.dll" % want[:8])
    md5 = hashlib.md5(open(built, "rb").read()).hexdigest() if os.path.isfile(built) else None
    check("выкладчик deploy_p127d: закреплённая сборка v83 = WANT_DLL, прежняя — живая v82 386d43f6, INI_VERSION 83, строка установки v83 обязательна",
          md5 == want and '"386d43f605d5ce693993fdcac43bc894"' in dep and "INI_VERSION = 83" in dep and "P127: живьём (v83)" in dep, (md5, want))
    js, en = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read(), open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    blk = js[js.index("// ---------- А5.2: кто в игре"):js.index("// ---------- Игроки: список всех")]
    keys = set(re.findall(r'"([^"\n]*[А-Яа-яЁё][^"\n]*)"', blk))
    miss = sorted(k for k in keys if ('"%s":' % k) not in en)
    check("веб А5.2: раздел «Кто в игре» (меню, маршрут #/online), действия (сообщение, отключить, перенос к персонажу, монстры v83, объявление "
          "всем сейчас или заданием), все строки — в I18N_EN", '["#/online", "Кто в игре", "players.view"' in js and 'case "online": return viewOnline' in js
          and "+node.ver >= 83" in blk and 'op: "live.announce", at:' in blk and not miss, miss[:5])


def _r42_static(check):
    """★ ревизия 42: выкладчик v83 без действий на --help / неизвестный ключ, стенд P9 (g_canMob = false), тексты объявления."""
    import subprocess
    import sys
    tools = os.path.join(AP, "tools")
    runs = os.path.join(tools, "run_p127d_deploy")
    had = os.path.isdir(runs)
    p1 = subprocess.run([sys.executable, os.path.join(tools, "deploy_p127d.py"), "--help"], capture_output=True, timeout=60,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    p2 = subprocess.run([sys.executable, os.path.join(tools, "deploy_p127d.py"), "--bogus"], capture_output=True, timeout=60,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    check("deploy_p127d (р42 Н-2): --help — шапка и код 0, неизвестный ключ — код 1, оба без SSH и без журнала выкладки",
          p1.returncode == 0 and "deploy_p127d.py" in p1.stdout.decode("utf-8", "replace") and p2.returncode == 1
          and (had or not os.path.isdir(runs)), (p1.returncode, p2.returncode))
    dep = open(os.path.join(tools, "deploy_p127d.py"), encoding="utf-8").read()
    check("deploy_p127d (р42 мелочи): шапка про mob_pop / mob_return, бэкап 2026-11-21_p127d в docstring, мёртвые write_bridge_secret / "
          "seed_section удалены", "mob_pop / mob_return в adm.BridgeEnqueue" in dep and "def write_bridge_secret" not in dep
          and "def seed_section" not in dep and "2026-11-18_p127" not in dep)
    st = open(os.path.join(tools, "stand_p127", "stand_p127.cpp"), encoding="utf-8").read()
    check("стенд P127 (р42 Н-3): режим nomob — начало 0x4C0A60 испорчено до установки → mob_pop / mob_return 3/11, PatchLog «… 6045/6046 НЕТ»",
          'nomob = !strcmp(mode, "nomob")' in st and "*(BYTE*)0x004C0A60 = 0xC3" in st and "P9 начало 0x4C0A60" in st and "P9 PatchLog" in st)
    from core import ops
    cli = ops.Ctx(None, "cli:t", "owner", "", "cli")
    import datetime
    at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    pv = ops.run(cli, "job.add", {"op": "live.announce", "at": at, "params": {"text": "Привет 😀"}}, dry=True)["preview"]
    check("объявление по расписанию (р42 мелочь): в окне подтверждения — текст объявления и предупреждение «символы вне cp1251 станут «?»»",
          any("Привет" in w for w in pv["warnings"]) and any("cp1251" in w for w in pv["warnings"]), pv["warnings"])


def offline(check):
    print("-- А5.2: монстры 6045 / 6046 мостом (подмены)")
    _mob_offline(check)
    _svr_offline(check)
    _r42_static(check)
    print("-- А5.2: перенос к персонажу (6012 / 6014 через char.move), кто в игре")
    _move_offline(check)
    _who_offline(check)
    _static_offline(check)


def live(check):
    """Только чтение и сухие предпросмотры (без dry=False): узлы, присутствие, честные отказы."""
    from core import config, ops
    import domains.live as L
    from domains import load_all
    load_all()      # ★ А7.11 (24.11): ниже ops.run("char.move") — без загрузки разделов её нет в реестре («неизвестная операция»), как у службы и консоли
    if config.get().on_server:
        return check("живой самотест А5.2 — с ПК", True)
    w = L.who()
    check("живой мост: узлы читаются (3 GameServer), у присутствия — название карты", len(w["nodes"]) >= 3
          and all("map_name" in r for r in w["presence"]), [(n["node"], n.get("ver"), n.get("fresh")) for n in w["nodes"]])
    # ★ ревизия 42 В-1: справка групп с живых .svr (SSH, только чтение) — Альпия (карта 3): событийные 444…, группа 0 — обычные мобы
    try:
        a = L.map_groups("GameServer", 3)
        ok = a["file"].lower() == "alpen.svr" and a["groups"].get(444, {}).get("event", 0) > 0 and a["groups"].get(0, {}).get("total", 0) > a["groups"].get(0, {}).get("event", 0)
        info = "%s: %s" % (a["file"], L.groups_text(a)[:200])
    except ops.OpRefused as ex:
        ok, info = False, str(ex)
    check("живая справка групп (SSH, только чтение): Альпия — Alpen.svr, группа 444 событийная, в группе 0 обычные мобы", ok, info)
    cli = ops.Ctx(None, "cli:selftest@pc", "owner", "", "cli")
    vers = {int(n.get("ver") or 0) for n in w["nodes"]}
    try:
        ops.run(cli, "live.mob_pop", {"uid": 2, "idx": 0, "group": 0, "confirm": "mobs"}, dry=True)
        res = "предпросмотр"
    except ops.OpRefused as ex:
        res = str(ex)
    # ★ А6.13 (22.11): с v83+ на узлах предпросмотр строится только от позиции персонажа в игре (domains/live.py MobPop._plan); при 0 игроков
    #   честный ответ — отказ «нет в игре». Ожидание по присутствию, прочитанному мостом независимо (bridge.live_row), а не «всегда предпросмотр»
    from core import bridge as _br
    _in_game = _br.live_row(2, 0, _br.MOB_VER) is not None
    check("живой призыв (сухой предпросмотр, ничего не отправлено): узлы v83+ и 2/0 в игре — предпросмотр; v83+ и 2/0 не в игре (по мосту) — "
          "отказ «нет в игре»; узлы без v83 — отказ «v83+» или «нет GM-флага»",
          (res == "предпросмотр" if _in_game else "нет в игре на узле с мостом v83+" in res) if max(vers or {0}) >= 83
          else ("v83+" in res or "GM-флага" in res), (res, sorted(vers), "в игре" if _in_game else "не в игре"))
    from core import db
    with db.GameReader("joy1") as r:                 # персонаж служебной учётки владельца (1 или 2) — только чтение
        own = r.rows("SELECT TOP 1 Userindex, Charidx FROM dbo.CharPos WHERE Userindex IN (1, 2) ORDER BY Userindex, Charidx")
    if not own:
        return check("живой перенос к персонажу: у учёток 1 и 2 нет персонажей — проверка пропущена", False)
    try:
        ops.run(cli, "char.move", {"uid": int(own[0]["Userindex"]), "idx": int(own[0]["Charidx"]), "mode": "char", "to_uid": 4999999,
                                   "to_idx": 0}, dry=True)
        res2 = "предпросмотр"
    except ops.OpRefused as ex:
        res2 = str(ex)
    check("живой перенос к отсутствующему персонажу (сухой) — отказ «клетка неизвестна», ничего не записано", "клетка неизвестна" in res2, res2)
