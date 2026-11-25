# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_monsters_a4.py — самотест шага А4.3 «Монстры и добыча» (20.11.2026, domains/cs_kinds/monsters.py).

offline(check)       — подменная стойка selftest_shops.synthetic() + синтетические Monster.ai (6 копий, у Indun_GameServer — своя
                       квест-строка), WorldDropItem.itm, MapInfo.ini / Collection.ini, файл копания (4 сектора): шансы по правилам
                       розыгрыша, все виды позиций и отказы, правка по базе каждой копии, баланс, белый список выкладчика, переводы.
sandbox(check, ldb)  — путь набора целиком в песочнице: копии файлов стойки во временной папке, НАСТОЯЩИЕ deploy_premium_boxes /
                       deploy_changeset (сухой прогон, --apply, откат), подставной restart_stack, LocalDB; NpcServer.exe работает → СТОП.
live(check)          — только чтение и сухие прогоны: md5 шести копий Monster.ai, справка (поиск, моб, мировая запись, копание) по живой
                       стойке, сверка шансов с отчётом drop_tables_tournament_maps.md вторым методом, живая оценка набора, НАСТОЯЩИЙ сухой
                       прогон deploy_changeset.py по SSH (манифест во временной папке, ничего не пишется).
Ни рестартов стойки, ни записи в таблицы стойки или порта. Побочных эффектов при импорте нет.
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
NPC3 = ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")
MASK = (1 << 64) - 1


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _rec(mid, exp, drop, world=(-1, 0, -1), quest=(), qgate=1, mode=0, rgate=0, money=(10, 20, 100)):
    """Запись MONINFO 479 б как в Monster.ai (после конца списка дропа — «мусор» оригинала: -1, 100, 1)."""
    b = bytearray(479)
    struct.pack_into("<i", b, 0, mid)
    b[4] = mid % 100
    b[5:5 + 8] = ("mob%d" % mid).encode("ascii").ljust(8, b"\0")
    struct.pack_into("<i", b, 0x2D, 1000 + mid)
    struct.pack_into("<i", b, 0x35, exp)
    b[167] = mode
    struct.pack_into("<b", b, 168, rgate)
    struct.pack_into("<hhb", b, 169, *money)
    for k in range(20):
        struct.pack_into("<iiH", b, 174 + 10 * k, -1, 100, 1)
    for k, (it, rt, c) in enumerate(drop):
        struct.pack_into("<iiH", b, 174 + 10 * k, it, rt, c)
    struct.pack_into("<ii", b, 374, -1, 0)
    struct.pack_into("<hhi", b, 394, *world)
    b[402] = qgate
    for k in range(5):
        struct.pack_into("<ibhib", b, 403 + 12 * k, -1, 0, 0, 0, 0)
    for k, q in enumerate(quest):
        struct.pack_into("<ibhib", b, 403 + 12 * k, *q)
    b[463:475] = b"\xff" * 12
    return bytes(b)


MOBS = {1: dict(exp=10, drop=[(30000, 400, 1), (30004, 1000, 3)], world=(0, 1, 50000), quest=[(100, 1, 0, 30005, 50)]),
        2: dict(exp=20, drop=[], quest=[(200, 1, 0, 30006, 30), (201, 2, 0, 30007, 100)]),
        5: dict(exp=7, drop=[(30000, 30000, 1), (30004, 60000, 1)], mode=1, rgate=49)}


def _ai(indun=False):
    out = b""
    for mid, m in MOBS.items():
        m = dict(m)
        if indun and mid == 2:              # Indun_GameServer: своя квест-строка 0 у моба 2 (как 19 мобов dev)
            m["quest"] = [(200, 1, 0, 30003, 30), (201, 2, 0, 30007, 100)]
        out += _rec(mid, **m)
    return out


def _itm():
    recs = [[(30000, 30000), (30004, 60000)], [(30005, 100000)], []]
    out = b""
    for i, secs in enumerate(recs):
        b = bytearray(162)
        struct.pack_into("<h", b, 0, i)
        for k in range(20):
            struct.pack_into("<ii", b, 2 + 8 * k, -1, 0)
        for k, (it, rt) in enumerate(secs):
            struct.pack_into("<ii", b, 2 + 8 * k, it, rt)
        out += bytes(b)
    return out


MINE_ROWS = [(1, 100, 0, 30000, 1, 1, 50000, MASK), (1, 100, 0, 30004, 1, 2, 100000, MASK)]


def _mng(rows=MINE_ROWS, sectors=4, odd=None):
    out = b""
    for s in range(sectors):
        b = bytearray(1402)
        struct.pack_into("<h", b, 0, s)
        for k in range(45):
            struct.pack_into("<bbiiiiiQ", b, 2 + 30 * k, 0, 0, 0, -1, 0, 0, 0, 0)
        for k, r in enumerate(rows if s != odd else rows[:1]):
            struct.pack_into("<bbiiiiiQ", b, 2 + 30 * k, *r)
        b[1352:] = (b"\xff\xff\x00\xff\xff\xff\xff\xff\xff\x00" * 5)
        out += bytes(b)
    return out


# ServerName_000…023 ini\MapInfo.ini dev (SSH 20.11) — регистр MapInfo, а не диска (ревизия 35 К-5: у 6 карт он другой)
MAPINFO_DEV = ("Sillaris", "Rein", "Conquester", "Alpen", "Night_Valley", "LostValley", "SunnyCoast", "Flammio", "palace_of_queen",
               "Castle_of_Chess", "t_Palace_of_Queen", "t_Castle_of_chess", "MountainFlamion", "Flabis", "StagnantDesert", "DragonLaiR",
               "firewayforest", "Castle_of_Chaos", "Inferion", "battlefield", "eventfield", "fieldofhonor", "quizstage", "^MineWar^")


def _ini():
    mi = "[MAPINFO]\r\nMapCount = %d \r\n" % len(MAPINFO_DEV) + "".join('ServerName_%03d="%s" \r\n' % (i, n) for i, n in enumerate(MAPINFO_DEV))
    return mi.encode("latin-1"), b"[COLLECTION_INFO]\r\nCollectionTypeCount = 2\r\n\r\nCollectionTypeAniTime00 = 6000\r\n"


def stack_files():
    """{путь от v2: байты} синтетических файлов области (6 копий Monster.ai, .itm, ini, копание Alpen00 и Rein01)."""
    from domains.cs_kinds import monsters as M
    mi, co = _ini()
    out = {}
    for g in GS3:
        out[g + BS + M.AI_GS] = _ai(indun=(g == "Indun_GameServer"))
    for n in NPC3:
        out[n + BS + M.AI_NPC] = _ai()
        out[n + BS + M.ITM] = _itm()
        out[n + BS + M.MAPINFO] = mi
        out[n + BS + M.COLLECTION] = co
        out[n + BS + M.mine_sub("Alpen", 0)] = _mng()
        out[n + BS + M.mine_sub("Rein", 1)] = _mng(odd=2)
    return out


def _ev(items):
    from domains import shopdata as SD
    return SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False).run()


def _rec_of(raw, mid):
    for i in range(len(raw) // 479):
        if struct.unpack_from("<i", raw, i * 479)[0] == mid:
            return raw[i * 479:(i + 1) * 479]
    return None


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check):
    import selftest_shops as T
    from domains import shopdata as SD
    from domains.cs_kinds import monsters as M
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    check("А4.3 реестр: область «monsters» (за ней — только «Предметы» А4.4), 6 видов (mob.drop/money/world/qdrop/exp, mine.drop), права data.edit / data.apply, "
          "гейт баланса; Monster.ai GS и NpcServer — per_copy, копание 24 × 2 — ленивые per_copy",
          SD.AREAS[SD.AREAS.index(M):] == [M] + [a for a in SD.AREAS if a.AREA in ("itemdata", "quests", "titledata", "skilldata", "mapdata", "events", "patchcfg")]   # ★ А5.4: + «Счастливые часы»; ★ А4.5: + «Задания»; ★ А4.7: + «Навыки и классы»; ★ А4.8: + «Карты»
          and set(M.KINDS) == {"mob.drop", "mob.money", "mob.world", "mob.qdrop", "mob.exp", "mine.drop"}   # ★ ревизия 39 Н-1: условие было закомментировано
          and SD.area_perm("mob.drop", "apply") == "data.apply" and SD.area_perm("mine.drop", "edit") == "data.edit" and M.BALANCE_GATE
          and SD.SRV_POLICY[M.AI_GS] == SD.SRV_POLICY[M.AI_NPC] == "per_copy" and len(M.SRV_FILES_LAZY) == 48
          and SD.SRV_POLICY[M.mine_sub("^MineWar^", 1)] == "per_copy")
    import stack_layout as SL
    LC = SD._LayoutCopy
    check("служба на сервере (нет stack_layout в пакете): копия состава стойки в shopdata = настоящему stack_layout (GS, NpcServer, пары Ch2)",
          LC.GS_FOLDERS == list(SL.GS_FOLDERS) and LC.NPC_FOLDERS == list(SL.NPC_FOLDERS) and LC.TWINS == dict(SL.TWINS)
          and list(SD.GS) == LC.GS_FOLDERS)
    rels = {f + BS + s for f, s in M.copies()} |{n + BS + sub for _fam, sub, _p in M.SRV_FILES_LAZY for n in NPC3}
    check("выкладчик deploy_changeset: белый список = все копии Monster.ai (3 GS + 3 NpcServer) и 48 файлов копания × 3 NpcServer; "
          "список карт выкладчика = панели", rels <= dc.ALLOWED and tuple(dc.MINING_MAPS) == tuple(M.MINING_MAPS) and dc.check_roots(
              {f + BS + s: 1 for f, s in M.copies()}) is None, sorted(rels - dc.ALLOWED)[:3])
    # шансы — правила розыгрыша drop_tables_tournament_maps.md §0
    cum = M.p_cumulative([47950, 62950, 100000])
    check("шансы: основной (rate+1)/100 000 (400 → 0,401 %, ≥ 99 999 — всегда, −1 — никогда); проценты (rate+1)/100; накопительные "
          "пороги — первая (r0+1)/100 000, далее разность; показ «0.401 %»",
          abs(M.p_rate(400) - 0.00401) < 1e-12 and M.p_rate(99999) == 1 and M.p_rate(100000) == 1 and M.p_rate(-1) == 0
          and M.p_pct(49) == 0.5 and M.p_pct(100) == 1 and M.p_pct(-1) == 0 and abs(cum[0] - 0.47951) < 1e-12
          and abs(cum[1] - 0.15) < 1e-12 and abs(sum(cum) - 1) < 1e-12 and M.pct(0.00401) == "0.401 %"
          and M.main_odds(1, 49, [[1, 30000, 1], [2, 60000, 1]]) == [0.5 * 0.30001, 0.5 * 0.3])
    with T.synthetic() as (raw, md5, cli):
        for rel, b in stack_files().items():
            raw[rel], md5[rel] = b, _md5(b)
        # основной дроп
        e = _ev([("mob.drop", {"mob": 1, "rows": [[30000, 800, 1], [30004, 1000, 3], [30006, 5000, 2]]})])
        s, nb = e.summary(), e.new_bytes()
        ok_sizes = all(len(nb[r]) == len(raw[r]) for r in nb)
        ind = nb.get("Indun_GameServer" + BS + M.AI_GS, b"")
        r1 = _rec_of(nb.get("NpcServer" + BS + M.AI_NPC, b""), 1) or b""
        check("mob.drop: строки моба 1 на всех 6 копиях (GS ×3 + NpcServer ×3), размер файла прежний, конец списка −1 после 3-й строки, "
              "у Indun_GameServer своя квест-строка моба 2 сохранена, Ch2 = поле",
              not e.errors and len(nb) == 6 and ok_sizes and struct.unpack_from("<iiH", r1, 174 + 20) == (30006, 5000, 2)
              and struct.unpack_from("<i", r1, 174 + 30)[0] == -1 and _rec_of(ind, 2) == _rec(2, **dict(MOBS[2], quest=[(200, 1, 0, 30003, 30),
                                                                                                                     (201, 2, 0, 30007, 100)]))
              and nb["Ch2_GameServer" + BS + M.AI_GS] == nb["GameServer" + BS + M.AI_GS]
              and {f["table"] for f in s["server"]["files"]} == {M.AI_GS, M.AI_NPC}, e.errors)
        bal = {b["what"]: b for b in s["balance"]}
        new_item = [b for b in s["balance"] if "новый предмет" in b["what"]]
        rate2 = [b for b in s["balance"] if b["old"] == 0.401]
        check("mob.drop: баланс — шанс 0.401 → 0.801 % (≤ ×2 — не сильная), новый предмет 30006 — замена (сильная, гейт), "
              "строки «было / станет» с шансами",
              new_item and new_item[0]["strong"] and new_item[0]["gate"] and rate2 and not rate2[0]["strong"] and s["balance_strong"]
              and any("0.801 %" in x for x in s["positions"][0].get("lines", [])), list(bal))
        bad = {"нет моба": _ev([("mob.drop", {"mob": 9, "rows": []})]).errors,
               "−1": _ev([("mob.drop", {"mob": 1, "rows": [[-1, 1, 1]]})]).errors,
               "нет кода": _ev([("mob.drop", {"mob": 1, "rows": [[30099, 1, 1]]})]).errors,
               "то же": _ev([("mob.drop", {"mob": 1, "rows": [[30000, 400, 1], [30004, 1000, 3]]})]).errors,
               "21 строка": _ev([("mob.drop", {"mob": 1, "rows": [[30000, 1, 1]] * 21})]).errors,
               "кол-во 0": _ev([("mob.drop", {"mob": 1, "rows": [[30000, 1, 0]]})]).errors,
               "две позиции": _ev([("mob.drop", {"mob": 1, "rows": []}), ("mob.drop", {"mob": 1, "rows": [[30000, 5, 1]]})]).errors}
        check("mob.drop: отказы — моба нет (только существующие), itemId −1 внутри, кода нет на сервере, менять нечего, 21 строка, "
              "количество 0, две позиции на одну цель", all(bad.values()) and "только правка существующих" in bad["нет моба"][0]
              and "нет на сервере" in bad["нет кода"][0], {k: v[:1] for k, v in bad.items()})
        w = _ev([("mob.drop", {"mob": 2, "rows": [[30001, 100, 1], [30003, 100, 2], [5, 100, 1]]})])
        ws = " | ".join(w.positions[0]["warnings"])
        check("mob.drop: «дюп и экономика» (разбор §4 п.5) — премиум-предмет (GXP), коробка пакета, нестопочный с количеством 2 — "
              "предупреждения; код Function_Table (5) допустим", not w.errors and "GXP" in ws and "коробка пакета" in ws and "не стопочный" in ws,
              (w.errors, ws[:300]))
        key = "Indun_GameServer" + BS + M.AI_GS
        keep = raw[key]
        try:
            raw[key] = keep.replace(_rec(1, **MOBS[1]), _rec(1, **dict(MOBS[1], drop=[(30000, 401, 1), (30004, 1000, 3)])))
            md5[key] = _md5(raw[key])
            d2 = _ev([("mob.drop", {"mob": 1, "rows": [[30000, 800, 1]]})]).errors
            e2 = _ev([("mob.exp", {"mob": 1, "exp": 12})])
        finally:
            raw[key], md5[key] = keep, _md5(keep)
        check("правка к каждой копии по её байтам: у Indun другой дроп моба 1 — отказ «отличия копии не затираются»; опыт того же моба "
              "(поле совпадает) — правится и в Indun", d2 and "не затираются" in d2[0] and not e2.errors and len(e2.new_bytes()) == 6, d2)
        ch2 = "Ch2_NpcServer" + BS + M.AI_NPC
        keep = raw[ch2]
        raw[ch2] = keep[:-1] + b"\x01"
        md5[ch2] = _md5(raw[ch2])
        par = _ev([("mob.exp", {"mob": 1, "exp": 12})]).errors
        raw[ch2] = keep[:100]
        md5[ch2] = _md5(raw[ch2])
        size = _ev([("mob.exp", {"mob": 1, "exp": 12})]).errors
        raw[ch2], md5[ch2] = keep, _md5(keep)
        check("паритет Ch2 (база Ch2_NpcServer ≠ NpcServer) — отказ; размер Monster.ai не кратен 479 — отказ",
              any("паритет Ch2" in x for x in par) and any("не кратен 479" in x for x in size), (par, size))
        # опыт
        x1 = _ev([("mob.exp", {"mob": 1, "exp": 25})]).summary()
        x2 = _ev([("mob.exp", {"mob": 1, "exp": 15})]).summary()
        check("mob.exp: опыт +0x35 на 6 копиях; 10 → 25 — сильная (гейт), 10 → 15 — нет; «было → стало» в тексте",
              x1["server"]["count"] == 6 and x1["balance_strong"] and not x2["balance_strong"] and "10 → 25" in x1["positions"][0]["text"],
              x1["balance"])
        # деньги
        m1 = _ev([("mob.money", {"mob": 1, "min": 12, "max": 24, "chance": 100})])
        m2 = _ev([("mob.money", {"mob": 1, "min": 30, "max": 5, "chance": 100})]).errors
        r = _rec_of(m1.new_bytes()["GameServer" + BS + M.AI_GS], 1)
        check("mob.money: +169/+171/+173 правятся, среднее за моба 15 → 18 (не сильная); min > max — отказ",
              not m1.errors and struct.unpack_from("<hhb", r, 169) == (12, 24, 100) and not m1.summary()["balance_strong"] and m2, m2)
        # мировой
        w1 = _ev([("mob.world", {"mob": 1, "index": 1, "count": 1, "gate": 50000})])
        w2 = _ev([("mob.world", {"mob": 1, "index": 3, "count": 1, "gate": 50000})]).errors
        w3 = _ev([("mob.world", {"mob": 1, "index": 0, "count": 2, "gate": 50000})]).summary()
        r = _rec_of(w1.new_bytes()["NpcServer" + BS + M.AI_NPC], 1)
        check("mob.world: запись WorldDropItem 0 → 1 (+394/+396/+398), шансы гейт × доля секции, другая запись — замена (сильная); "
              "записи нет — отказ (GetWorldItemIndex Exception); раз 1 → 2 — «в среднем шт.» ×2 (не сильная)",
              not w1.errors and struct.unpack_from("<hhi", r, 394) == (1, 1, 50000) and w1.summary()["balance_strong"]
              and any("50.001 %" in x for x in w1.positions[0]["lines"]) and w2 and "GetWorldItemIndex" in w2[0]
              and not w3["errors"] and not w3["balance_strong"], (w1.errors, w1.positions[0].get("lines"), w2))
        # квест-дроп
        q1 = _ev([("mob.qdrop", {"mob": 2, "gate": 1, "rows": [[30006, 30], [30007, 60]]})])
        q2 = _ev([("mob.qdrop", {"mob": 2, "gate": 1, "rows": [[30006, 60], [30007, 100]]})]).errors
        q3 = _ev([("mob.qdrop", {"mob": 2, "gate": 1, "rows": [[30006, 30]]})]).errors
        qi = q1.new_bytes().get("Indun_GameServer" + BS + M.AI_GS, b"")
        r = _rec_of(qi, 2)
        check("mob.qdrop: строка 1 (одинаковая во всех копиях) — шанс 100 → 60 в 6 копиях, у Indun своя строка 0 (30003) сохранена; "
              "предупреждение про DT_MobQuestDrop; строка 0 (у Indun другая) — отказ; число строк другое — отказ",
              not q1.errors and len(q1.new_bytes()) == 6 and struct.unpack_from("<ibhib", r, 403) == (200, 1, 0, 30003, 30)
              and struct.unpack_from("<ibhib", r, 415) == (201, 2, 0, 30007, 60) and any("DT_MobQuestDrop" in x for x in q1.positions[0]["warnings"])
              and q2 and "не затираются" in q2[0] and q3 and "не добавляются" in q3[0], (q1.errors, q2, q3))
        # копание
        rows = [[30000, 1, 100, 1, 1, 40000, 0, "ffffffffffffffff"], [30004, 1, 100, 1, 3, 90000, 5, "ffffffffffffffff"],
                [30006, 10, 100, 2, 2, 100000, 0, "00000000000000ff"]]
        k1 = _ev([("mine.drop", {"map": "alpen", "type": 0, "rows": rows})])
        sub = M.mine_sub("Alpen", 0)
        nbk = k1.new_bytes()
        f = nbk.get("Indun_NpcServer" + BS + sub, b"")
        secs = [f[i * 1402:(i + 1) * 1402] for i in range(len(f) // 1402)]
        check("mine.drop: Alpen тип 0 — 3 копии NpcServer, ВСЕ 4 сектора одинаковы (номер сектора +0 сохранён), строка 2 — маска 0xff, "
              "конец −1 после неё, хвост 50 б не тронут, размер прежний; доли 40.0 / 50 / 10 %",
              not k1.errors and len(nbk) == 3 and len(f) == len(raw["NpcServer" + BS + sub]) and len({x[2:] for x in secs}) == 1
              and [struct.unpack_from("<h", x, 0)[0] for x in secs] == [0, 1, 2, 3]
              and struct.unpack_from("<bbiiiiiQ", secs[2], 2 + 60) == (10, 100, 0, 30006, 2, 2, 100000, 0xff)
              and struct.unpack_from("<i", secs[2], 2 + 90 + 6)[0] == -1 and secs[1][1352:] == raw["NpcServer" + BS + sub][1402 + 1352:2804]
              and any("40.001 %" in x for x in k1.positions[0]["lines"]), (k1.errors, k1.positions[0].get("lines")))
        kb = {"рост порога": _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": [rows[1], rows[0]]})]).errors,
              "min > max": _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": [[30000, 1, 100, 3, 1, 100000, 0, "ff"]]})]).errors,
              "нет карты": _ev([("mine.drop", {"map": "Nowhere", "type": 0, "rows": rows})]).errors,
              "тип 2": _ev([("mine.drop", {"map": "Alpen", "type": 2, "rows": rows})]).errors,
              "сектора": _ev([("mine.drop", {"map": "Rein", "type": 1, "rows": rows})]).errors,
              "маска": _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": [[30000, 1, 100, 1, 1, 100000, 0, "xyz"]]})]).errors}
        check("mine.drop: отказы — порог не растёт (строка недостижима), мин. количество > макс. (деление на max−min+1), карты нет, "
              "типа нет, сектора файла различаются (макс. количество сервер берёт из сектора k), маска не hex",
              all(kb.values()) and "сектора различаются" in kb["сектора"][0], {k: v[:1] for k, v in kb.items()})
        km = "Ch2_NpcServer" + BS + sub
        keep = raw[km]
        raw[km] = _mng(rows=MINE_ROWS[:1] + [(1, 100, 0, 30004, 1, 2, 99999, MASK)])
        md5[km] = _md5(raw[km])
        kc = _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": rows})]).errors
        raw[km], md5[km] = keep, _md5(keep)
        check("mine.drop: копия NpcServer с другими записями — отказ (паритет Ch2 / отличия копии)", kc, kc)
        # ★ ревизия 35
        r5 = [[30000 if i % 2 == 0 else 30004, 1, 100, 1, 1, 20000 * (i + 1), 0, "ffffffffffffffff"] for i in range(5)]
        e5 = _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": r5})]).errors
        e4 = _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": r5[:3] + [r5[4]]})]).errors
        check("ревизия 35 М-1: копание — строк 5 при 4 секторах — отказ (max количества строки k сервер берёт из сектора k, иначе чтение "
              "за таблицей и rand() % 0); 4 строки при 4 секторах — правится",
              e5 and "секторов 4" in e5[0] and "rand() % 0" in e5[0] and not e4, (e5, e4))
        keep = {n: raw[n + BS + sub] for n in NPC3}
        try:
            r10 = [(1, 100, 10, 30000, 1, 1, 50000, MASK), (1, 100, 10, 30004, 1, 2, 100000, MASK)]
            for n in NPC3:
                raw[n + BS + sub] = _mng(rows=r10)
                md5[n + BS + sub] = _md5(raw[n + BS + sub])
            base = [[30000, 1, 100, 1, 1, 50000, 10, "ffffffffffffffff"], [30004, 1, 100, 1, 2, 100000, 10, "ffffffffffffffff"]]

            def mb(ch):
                rr = [list(x) for x in base]
                ch(rr)
                s2 = _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": rr})]).summary()
                return s2["errors"], s2["balance_strong"], [(b["what"], b["kind"], b["strong"]) for b in s2["balance"]]
            g15 = mb(lambda rr: rr[0].__setitem__(6, 15))
            g25 = mb(lambda rr: rr[0].__setitem__(6, 25))
            glv = mb(lambda rr: rr[1].__setitem__(2, 127))
            gmk = mb(lambda rr: rr[1].__setitem__(7, "00000000000000ff"))
            gth = mb(lambda rr: rr[0].__setitem__(5, 60000))
        finally:
            for n in NPC3:
                raw[n + BS + sub], md5[n + BS + sub] = keep[n], _md5(keep[n])
        has = lambda g, w, kind: any(w in x[0] and x[1] == kind and x[2] for x in g[2])
        check("ревизия 35 М-2: копание — опыт строки 10 → 15 не сильная, 10 → 25 сильная (порог ×2); смена уровней и маски классов — "
              "сильная всегда (kind type); только порог 50 000 → 60 000 (≤ ×2) — не сильная",
              not any(g[0] for g in (g15, g25, glv, gmk, gth)) and not g15[1] and any("опыт копания" in x[0] and not x[2] for x in g15[2])
              and g25[1] and has(g25, "опыт копания", "value") and glv[1] and has(glv, "уровни копателя", "type")
              and gmk[1] and has(gmk, "маска классов", "type") and not gth[1], (g15, g25, glv, gmk, gth))
        k9 = _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": [[30000, 1, 100, 1, 1, 100000, 0, "ff", 7]]})]).errors
        k7 = _ev([("mine.drop", {"map": "Alpen", "type": 0, "rows": [[30000, 1, 100, 1, 1, 100000, 0]]})])
        k7m = struct.unpack_from("<bbiiiiiQ", k7.new_bytes().get("NpcServer" + BS + sub, b"\0" * 1402), 2)[7] if not k7.errors else None
        check("ревизия 35 К-6: копание — строка из 9 столбцов — отказ (хвост не отбрасывается молча); 7 столбцов — маска «все классы»",
              k9 and "дано 9" in k9[0] and not k7.errors and k7m == MASK, (k9, k7.errors, k7m))
        wa = _ev([("mob.world", {"mob": 1, "index": -1, "count": 1, "gate": 50000})]).errors
        wb = _ev([("mob.world", {"mob": 1, "index": -1, "count": 0, "gate": 50000})]).errors
        wc = _ev([("mob.world", {"mob": 1, "index": -1, "count": 1, "gate": -1})]).errors
        check("ревизия 35 К-1: мировой дроп — индекс −1 при «сколько раз» > 0 и гейте ≥ 0 — отказ (GetWorldItemIndex на каждом повторе); "
              "индекс −1 с раз 0 или гейтом −1 — правится (выключение)", wa and "iIndex -1" in wa[0] and not wb and not wc, (wa, wb, wc))
        w19 = _ev([("mob.world", {"mob": 1, "index": 0, "count": 19, "gate": 50000})])
        check("ревизия 35 К-7: мировой дроп — строка «в среднем шт. — верхняя оценка (предел 20 слотов)»; строк основного 2 + повторов 19 "
              "> 20 — предупреждение «до 1 повторов не выпадут»",
              not w19.errors and any("верхняя оценка" in x for x in w19.positions[0]["lines"])
              and any("до 1 повторов" in x for x in w19.positions[0]["warnings"])
              and any("верхняя оценка" in x for x in w1.positions[0]["lines"]) and not any("предел 20 слотов" in x for x in w1.positions[0]["warnings"]),
              (w19.errors, w19.positions[0].get("warnings")))
        from core.ops import OpRefused
        lk = {}
        for q in ("Alpen:5", "Alpen:-1", "Alpen:x"):
            try:
                M.lookup_mine(q)
                lk[q] = "нет отказа"
            except OpRefused as ex:
                lk[q] = str(ex)
            except Exception as ex:                       # не OpRefused — это 500
                lk[q] = "500: %r" % ex
        for w_, q in (("mob", "abc"), ("world", "1x")):
            try:
                M.lookup(w_, q)
                lk[w_] = "нет отказа"
            except OpRefused as ex:
                lk[w_] = str(ex)
            except Exception as ex:
                lk[w_] = "500: %r" % ex
        check("ревизия 35 К-4: справка копания — тип 5, −1, «x» — OpRefused (409), а не 500; моб «abc», запись «1x» — тоже",
              "типа копания 5 нет" in lk["Alpen:5"] and "типа копания -1 нет" in lk["Alpen:-1"] and "целое число" in lk["Alpen:x"]
              and "целое число" in lk["mob"] and "целое число" in lk["world"], lk)
        check("ревизия 35 К-5: MINING_MAPS — регистр файлов диска (Lostvalley, castle_of_chess, t_palace_of_queen, t_castle_of_chess, "
              "flabis, castle_of_chaos), без учёта регистра = MapInfo.ini; MapInfo в регистре dev — копание правится (Alpen00 выше)",
              [m.lower() for m in M.MINING_MAPS] == [m.lower() for m in MAPINFO_DEV]
              and {"Lostvalley", "castle_of_chess", "t_palace_of_queen", "t_castle_of_chess", "flabis", "castle_of_chaos"} <= set(M.MINING_MAPS)
              and M.norm("mine.drop", {"map": "LostValley", "type": 0, "rows": []})["map"] == "Lostvalley", M.MINING_MAPS)
        # расхождения
        from domains.cs_kinds import monsters as M2
        secs = []
        ev = _ev([])
        M2.divergence(ev, ev.cli, lambda k, t, rws, note="": secs.append((k, rws)))
        check("расхождения: раздел «mobs» — Indun_GameServer: 1 запись с отличиями (моб 2)", secs and secs[0][0] == "mobs" and len(secs[0][1]) == 1
              and "Indun_GameServer" in secs[0][1][0]["id"] and "(2)" in secs[0][1][0]["why"], secs)
    # переводы веба
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "monsters.js"), encoding="utf-8").read()
    en = open(os.path.join(root, "web", "i18n.js"), encoding="utf-8").read()
    STR = r'"((?:[^"\\]|\\.)*)"'
    have = set(re.findall(STR + r"\s*:", en))
    need = {x for x in re.findall(r"T\(" + STR, js)} | {x for x in re.findall(STR, js) if re.search("[А-Яа-яЁё]", x)}
    miss = sorted(need - have)
    block = en.split("// А4.3 20.11", 1)[1] if "// А4.3 20.11" in en else ""
    keys = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", block, re.M)
    idx = open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
    check("веб: monsters.js подключён, все его строки есть в I18N_EN, в блоке А4.3 нет дублей", "/monsters.js" in idx and not miss
          and keys and len(keys) == len(set(keys)), miss[:5])
    # попутно (20.11): разбор ключей выкладчика панели — --help и неизвестный ключ ничего не выкладывают
    import contextlib
    import importlib.util
    import io
    spec = importlib.util.spec_from_file_location("deploy_admin_center_t", os.path.join(root, "deploy", "deploy_admin_center.py"))
    dac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dac)
    with contextlib.redirect_stdout(io.StringIO()):
        pa = [dac.parse_args(["--help"]), dac.parse_args(["-h"]), dac.parse_args(["--bogus"]), dac.parse_args([]), dac.parse_args(["--skip-selftest"])]
    check("deploy_admin_center: --help / -h → справка, код 0, выкладки нет; неизвестный ключ → код 2; без ключей и --skip-selftest — как прежде",
          pa[0] == (0, None) and pa[1] == (0, None) and pa[2] == (2, None) and pa[3] == (None, set()) and pa[4] == (None, {"--skip-selftest"}), pa)
    from core import i18n
    i18n.set_lang("en")
    try:
        samples = ["моб 441 «Сильная пешка»: основной дроп — строк 2 → 3 (сервер: Monster.ai ×6 копий)",
                   "копание Alpen, тип 0: строк 30 → 31 (сервер: MiningItemTable\\Alpen00.mng ×3 NpcServer, все сектора)",
                   "позиция 1: Indun_GameServer\\MonsterData_Info\\Monster.ai: квест-дроп моба 2 другой, чем у GameServer ([1] ≠ [2]) — отличия "
                   "копии не затираются, правка не однозначна",
                   # ★ ревизия 35
                   "позиция 1: NpcServer\\MiningItemTable\\Alpen00.mng: строк 5, а секторов 4 — сервер (sub_44F170) берёт макс. количество "
                   "строки k из СЕКТОРА k, поэтому строка с номером ≥ числа секторов читается за концом таблицы (мусорный максимум, при max = min − 1 "
                   "— rand() % 0 и падение NpcServer), правка не делается",
                   "мировой дроп: индекс −1 при «сколько раз» 1 > 0 и гейте 50000 ≥ 0 — сервер после гейта на каждом повторе пишет "
                   "«GetWorldItemIndex() Exception… iIndex -1» (NpcServer.exe.c:41700), предмета не даёт; чтобы выключить мировой дроп, "
                   "поставьте «сколько раз» 0 или гейт −1",
                   "копание Alpen/0: 30000, опыт копания", "копание Alpen/0: 30004, уровни копателя", "копание Alpen/0: 30004, маска классов",
                   "копание, строка 0: нужно 7 чисел и маска классов (8-й столбец, можно опустить), а дано 9",
                   "типа копания 5 нет (типов 2: 0…1)", "тип копания: нужно целое число",
                   "«в среднем шт.» мирового дропа — верхняя оценка: предел 20 выпадений за моба общий (sub_437A30, v109 < 20), основной "
                   "(строк 2) и групповой дроп занимают слоты раньше",
                   "мировой дроп: строк основного дропа 2 + повторов 19 > 20 — если выпадет весь основной дроп, до 1 повторов мирового не "
                   "выпадут (предел 20 слотов)"]
        tr = [i18n.tr(x) for x in samples]
    finally:
        i18n.set_lang("ru")
    check("переводы службы: тексты позиций и отказов А4.3 переводятся (EN)", all(a != b and not re.search("[А-Яа-я]{4}", b.replace("«Сильная пешка»", ""))
                                                                              for a, b in zip(samples, tr)), tr)


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox(check, ldb):
    """Набор «монстры и добыча» целиком: создать → проверить → утвердить (сильная правка — второе подтверждение) → сухой прогон
    НАСТОЯЩЕГО deploy_changeset (9 файлов, база Indun — своя) → NpcServer.exe работает — СТОП → выкладка подставным рестартом →
    откат; клиентской половины нет."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs
    from domains.cs_kinds import monsters as M
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with X.sandbox(ldb) as (st, env):
        files = stack_files()
        for rel, b in files.items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        items = [("mob.drop", {"mob": 1, "rows": [[30000, 800, 1], [30004, 1000, 3], [30006, 5000, 2]]}),
                 ("mob.exp", {"mob": 5, "exp": 9}),
                 ("mine.drop", {"map": "Alpen", "type": 0, "rows": [[30000, 1, 100, 1, 1, 40000, 0, "ffffffffffffffff"],
                                                                      [30004, 1, 100, 1, 2, 100000, 0, "ffffffffffffffff"]]})]
        cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.3", note="самотест песочницы А4.3: монстры и добыча")["result"]["id"]
        for kind, prm in items:
            X._run(ctx, "shop.cs_item_add", cs=cid, kind=kind, params=prm)
        X._run(ctx, "shop.cs_check", cs=cid)
        cs = shopcs.get(cid)
        _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
        X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
        check("песочница А4.3: проверка — только сервер (клиентской половины нет), сильная правка (новый предмет) — без второго "
              "подтверждения отказ, с ним — утверждён", cs["check"]["ok"] and not cs["check"]["client_needed"] and cs["check"]["server_needed"]
              and no and "второе подтверждение" in no and shopcs.get(cid)["status"] == "approved", (cs["check"]["errors"], no))
        X._run(ctx, "shop.cs_server_dry", cs=cid)
        man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
        ind = "Indun_GameServer" + BS + M.AI_GS
        check("песочница А4.3: сухой прогон НАСТОЯЩЕГО deploy_changeset — 9 файлов (Monster.ai ×6, Alpen00.mng ×3), у Indun_GameServer "
              "своя база", shopcs.get(cid)["server_state"] == "dry_ok" and len(man["files"]) == 9 and man["files"][ind]["base"] == _md5(files[ind]),
              sorted(man["files"]))
        st.procs = {"NpcServer": 3}
        rc1, o1 = shopcs.run_deploy(shopcs.manifest_path(cid), ["--apply"])
        st.procs = dict(st.expect)
        check("песочница А4.3: NpcServer.exe работает → выкладчик СТОП 2 (NpcServer читает Monster.ai и копание при старте), стойка не тронута",
              rc1 == 2 and "NpcServer.exe" in o1 and open(st.path(ind), "rb").read() == files[ind], (rc1, o1[-200:]))
        r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart")
        got = open(st.path(ind), "rb").read()
        mng = open(st.path("NpcServer" + BS + M.mine_sub("Alpen", 0)), "rb").read()
        check("песочница А4.3: серверная половина выложена рестартом (без --unsynced-ok — клиента нет) — у Indun моб 1 новый, своя "
              "квест-строка моба 2 сохранена; копание — все сектора", r and shopcs.get(cid)["server_state"] == "applied"
              and struct.unpack_from("<iiH", _rec_of(got, 1), 194) == (30006, 5000, 2) and _rec_of(got, 2) == _rec_of(files[ind], 2)
              and len({mng[i * 1402 + 2:(i + 1) * 1402] for i in range(4)}) == 1 and struct.unpack_from("<i", mng, 2 + 18)[0] == 40000, e)
        X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
        back = all(open(st.path(rel), "rb").read() == b for rel, b in files.items())
        check("песочница А4.3: откат — все 9 файлов стойки вернулись побайтно", back and shopcs.get(cid)["server_state"] == "rolled_back",
              shopcs.get(cid)["server_state"])


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны на живой стойке (SSH); манифест сухого прогона — во временной папке."""
    from core import config
    from domains import shopcs, shopdata as SD
    from domains.cs_kinds import monsters as M
    if config.get().on_server:
        return check("живой самотест А4.3 — с ПК (SSH)", True)
    rels = [f + BS + s for f, s in M.copies()]
    md = SD.live_md5(rels)
    base = md[rels[0]]
    check("живая стойка: шесть копий Monster.ai — две базы (Indun_GameServer своя), Ch2 = поле",
          "none" not in md.values() and len(set(md.values())) == 2 and md["Ch2_GameServer" + BS + M.AI_GS] == base
          and md["Indun_GameServer" + BS + M.AI_GS] != base and all(md[n + BS + M.AI_NPC] == base for n in NPC3),
          {r: h[:8] for r, h in md.items()})
    s = M.search("")
    one = M.lookup_mob(441)
    row = next((x for x in one["drop"] if x["item"] == 20917), None)
    check("справка: мобов 850; моб 441 — «Реагент уровня D» (20917) rate 400 → 0.401 % (второй метод: отчёт drop_tables_tournament_maps.md)",
          s["total"] == 850 and row and row["rate"] == 400 and abs(row["p"] - 0.00401) < 1e-12, (s["total"], one["drop"][:2]))
    # ★ ревизия 35 К-5: имена файлов копания на диске всех NpcServer = MINING_MAPS С учётом регистра; MapInfo = без учёта регистра
    from core import hostshell
    txt = hostshell.powershell("$v2='%s'; foreach($n in @(%s)){ foreach($f in (Get-ChildItem -LiteralPath (Join-Path $v2 ($n+'\\MiningItemTable')) "
                               "-Filter *.mng)){ Write-Output ($n+'|'+$f.Name) } }" % (config.STACK_ROOT, ",".join("'%s'" % n for n in NPC3)),
                               timeout=120)
    disk = {}
    for ln in txt.splitlines():
        if "|" in ln:
            n, f = ln.strip().split("|", 1)
            disk.setdefault(n, set()).add(f)
    want = {"%s%02d.mng" % (m, t) for m in M.MINING_MAPS for t in range(M.MINE_TYPES)}
    mi = SD.Snap(md5=SD.live_md5(["NpcServer" + BS + M.MAPINFO]))
    names = re.findall(r'ServerName_\d+\s*=\s*"?([^"\r\n]*?)"?\s*$', mi.raw("NpcServer" + BS + M.MAPINFO).decode("latin-1"), re.M)
    check("ревизия 35 К-5: 48 файлов копания лежат на диске всех 3 NpcServer ровно в регистре MINING_MAPS (как их пишет выкладчик); "
          "MapInfo.ini — те же 24 карты без учёта регистра",
          len(disk) == 3 and all(want <= disk[n] for n in NPC3) and [x.lower() for x in names] == [m.lower() for m in M.MINING_MAPS],
          {n: sorted(want - disk.get(n, set()))[:4] for n in NPC3})
    mine = M.lookup_mine("Alpen:0")
    check("справка: копание Alpen00.mng — 324 сектора одинаковы, копии NpcServer одинаковы, последний порог 100 000",
          mine["uniform"] is True and mine["sectors"] == 324 and mine["copies_same"] and mine["rows"][-1]["rate"] == 100000, mine.get("uniform"))
    w = M.lookup_world(one["world"]["index"]) if one["world"]["index"] >= 0 else {"items": []}
    check("справка: мировая запись моба 441 читается (WorldDropItem.itm 1852 записи)", one["world"]["records"] == 1852 and isinstance(w["items"], list),
          one["world"])
    sn = SD.Snap()
    cli = SD.Client.load()
    mr = [[x["item"], x["rate"], x["count"]] for x in one["drop"]]
    mr[0][1] += 1
    mrows = [[r["item"], r["lvmin"], r["lvmax"], r["cmin"], r["cmax"], r["rate"], r["exp"], r["mask"]] for r in mine["rows"]]
    mrows[0][4] += 1
    items = [{"pos": 1, "kind": "mob.drop", "params": {"mob": 441, "rows": mr}},
             {"pos": 2, "kind": "mob.exp", "params": {"mob": 441, "exp": one["exp"] + 1}},
             {"pos": 3, "kind": "mine.drop", "params": {"map": "Alpen", "type": 0, "rows": mrows}}]
    ev = SD.Eval(items, False, sn, cli).run()
    sm = ev.summary()
    check("живая оценка набора (дроп моба 441 rate +1, опыт +1, копание Alpen00 макс. количество +1): без ошибок, сервер — 9 файлов",
          not sm["errors"] and sm["server"]["count"] == 9, sm["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_a43_live_")
    try:
        man = {"tag": "20261120_a43live", "changeset": 0, "files": {}}
        for rel, data in sorted(ev.new_bytes().items()):
            lp = os.path.join(tmp, rel.replace(BS, os.sep))
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            open(lp, "wb").write(data)
            man["files"][rel] = {"local": lp.replace(BS, "/"), "base": ev.snap.md5[rel], "new": SD.md5b(data)}
        mp = os.path.join(tmp, "manifest.json")
        json.dump(man, open(mp, "w", encoding="utf-8"))
        before = SD.live_md5(sorted(man["files"]))
        rc, out = shopcs.run_deploy(mp)
        after = SD.live_md5(sorted(man["files"]))
        check("НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH (9 файлов: Monster.ai ×6, Alpen00.mng ×3): «всё готово к --apply», файлы "
              "NpcServer процессы не держат; стойка не изменилась (md5 до = после)", rc == 0 and "всё готово" in out and before == after,
              (rc, out[-400:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
