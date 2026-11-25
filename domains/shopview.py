# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""shopview.py — справка редактору позиций набора изменений магазинов (А3, 19.11.2026): текущее состояние цели на стойке и у
клиента (только чтение). Источники — domains/shopdata.py (живые таблицы всех GameServer + клиент порта / снимок выкладки).
Побочных эффектов при импорте нет.
"""
from core.ops import OpRefused
from domains import refdata, shopdata as SD


def _it(code):
    inf = refdata.item(code)
    return {"code": code, "name": inf["name"] or inf["ru"] or inf["en"], "icon": inf["icon"]}


MONSTER_WHAT = ("mobs", "mob", "world", "mine")      # ★ А4.3: справка области «Монстры и добыча» (только таблицы стойки)
ITEM_WHAT = ("items", "item", "gem")                  # ★ А4.4: справка области «Предметы» (item_table / Cellob + item_list / sowell_list)
QUEST_WHAT = ("quests", "repay", "boards")            # ★ А4.5: справка области «Задания» (RepayTable ↔ RewardTable, доска LimitationQuest)
TITLE_WHAT = ("titles", "title")                      # ★ А4.6: справка области «Звания» (FameInfo ↔ title_list, держатели — Joy1)
SKILL_WHAT = ("skills", "skill", "spt", "classstat", "exptable")   # ★ А4.7: «Навыки и классы» (SkillInfo, SPT, ClassStat, ExpTable; Joy1)
MAP_WHAT = ("maps", "map")                            # ★ А4.8: «Карты» (MapInfo, OpenMapInfo, MapWarpCost, порталы, кристаллы; Joy1)


def lookup(what, ident):
    if what in MONSTER_WHAT:                          # ★ А4.3: без оценки магазинов — только Monster.ai / WorldDropItem / копание
        from domains.cs_kinds import monsters
        return monsters.lookup(what, ident)
    if what in ITEM_WHAT:                             # ★ А4.4: карточка предмета / самоцвета и поиск
        from domains.cs_kinds import itemdata
        return itemdata.lookup(what, ident)
    if what in QUEST_WHAT:                            # ★ А4.5: награды заданий и доска (только чтение; «кто держит» — Joy1)
        from domains.cs_kinds import questtables
        return questtables.lookup(what, ident)
    if what in TITLE_WHAT:                            # ★ А4.6: звания (только чтение; держатели — Joy1)
        from domains.cs_kinds import titledata
        return titledata.lookup(what, ident)
    if what in SKILL_WHAT:                            # ★ А4.7: навыки и классы (только чтение; держатели — Joy1)
        from domains.cs_kinds import skilldata
        return skilldata.lookup(what, ident)
    if what in MAP_WHAT:                              # ★ А4.8: карты (только чтение; персонажи на карте — Joy1)
        from domains.cs_kinds import mapdata
        return mapdata.lookup(what, ident)
    ev = SD.Eval([], False)
    cli = ev.cli
    if what == "cats6000":
        cnt = {}
        for r in cli.p6000.values():
            k = (int(r[1]), int(r[2]))
            cnt[k] = cnt.get(k, 0) + 1
        return {"cats": [{"cat": a, "sub1": b, "n": n} for (a, b), n in sorted(cnt.items())]}
    n = int(ident)
    if what == "code":
        f = ev.it_fields(n) if n >= SD.ITEM_FIRST else None
        sell = {g: ev.st.get(g, "SellItemTable.txt").has(n) for g in SD.GS}
        r6 = cli.p6000.get(n)
        out = dict(_it(n), server={"exists": ev.exists(n), "price": SD._int(f[26]) if f else None,
                                   "shop_flag": SD._int(f[38]) if f else None, "t24": SD._int(f[24]) if f else None,
                                   "type": [SD._int(f[16]), SD._int(f[17])] if f else None, "t39": SD._int(f[39]) if f else None,
                                   "sell": sell, "map": ev.pmap.get(n)},
                   client={"in_item_list": n in cli.items, "price": cli.price(n),
                           "p6000": {"cat": int(r6[1]), "sub1": int(r6[2]), "sub2": int(r6[3]), "newflag": int(r6[4])} if r6 else None,
                           "panel_tail": n in cli.tail, "b15300": n in cli.b15300, "npc": cli.npc_shown(n)})
        return out
    if what == "booster":
        t = ev.st.get("GameServer", "GachaItemRateTable.txt")
        if not 1 <= n < len(t.lines):
            raise OpRefused("строки %d в GachaItemRateTable нет" % n)
        f = SD._f(t.lines[n])
        srv = [[SD._int(f[1 + 2 * j]), SD._int(f[2 + 2 * j])] for j in range(35)]
        return {"row": n, "server": srv, "client": cli.booster.get(n), "users": [_it(c) for c in ev.booster_users(n)],
                "odds": SD.booster_odds(srv), "names": {str(c): _it(c)["name"] for c, _ in srv if c > 0}}
    if what == "package":
        t = ev.st.get("GameServer", "PackageItem_Table.txt")
        i = t.index().get(n)
        if not i:
            raise OpRefused("строки пакета %d нет" % n)
        f = SD._f(t.lines[i])
        srv = [[SD._int(f[1 + 2 * k]), SD._int(f[2 + 2 * k])] for k in range(5) if len(f) > 2 + 2 * k]
        return {"row": n, "server": [x for x in srv if x[0] > 0], "client": cli.pkg.get(n), "users": [_it(c) for c in ev.box_users(n)],
                "names": {str(c): _it(c)["name"] for c, _ in srv if c > 0}}
    if what == "gacha":
        pr = ev.st.get("GameServer", "PrimiumGaChaPriceTable.txt")
        i = pr.index().get(n)
        if i is None:
            raise OpRefused("автомата %d нет" % n)
        pool = ev.st.get("GameServer", "PrimiumGaChaTable.txt").slot_rows(n)
        agg = {}
        for c, q in pool:
            agg[(c, q)] = agg.get((c, q), 0) + 1
        return {"slot": n, "price": SD._int(SD._f(pr.lines[i])[1]), "client_price": cli.gatya_price.get(n), "rows": pool,
                "groups": [dict(_it(c), qty=q, n=k, chance=k / float(len(pool))) for (c, q), k in sorted(agg.items())]}
    if what == "npc":
        v = cli.npc.get(n)
        if not v:
            raise OpRefused("лавки NPC %d нет" % n)
        return {"npc": n, "shown": [_it(c) for c in v.get("shown") or []], "hidden": [_it(c) for c in v.get("hidden") or []],
                "spd": v.get("spd"), "npcs": sorted(cli.npc)}
    # ★ А4.1: витрина 6800, магазин чести, парикмахерская (только чтение; таблицы стойки — все GS, у Indun своя база)
    if what == "equipshop":
        lists = cli.equip or []
        if not 0 <= n < len(lists):
            raise OpRefused("списка %d витрины 6800 нет" % n)
        return {"list": n, "codes": [_it(c) for c in lists[n]], "counts": [len(x) for x in lists]}
    if what in ("honor", "hair"):
        ev2 = SD.Eval([{"pos": 1, "kind": "honor.price" if what == "honor" else "hair.price", "params": {}}], False)
        table = "HonorPrice_Table.txt" if what == "honor" else "HairTypeTable.txt"
        srv = {}
        for g in SD.GS:
            t = ev2.st.get(g, table)
            i = t.index().get(n)
            srv[g] = [SD._int(x) if x.lstrip("-").isdigit() else x for x in SD._f(t.lines[i])] if i else None
        if what == "honor":
            c = cli.honor[n] if cli.honor and 0 <= n < len(cli.honor) else None
            if c is None and not any(srv.values()):
                raise OpRefused("строки %d магазина чести нет" % n)
            return {"pos": n, "server": srv, "client": c, "item": _it(c[1]) if c else None, "ranks": cli.honor_ranks,
                    "rows": len(cli.honor or [])}
        c = cli.hair.get(n)
        if c is None and not any(srv.values()):
            raise OpRefused("причёски %d нет" % n)
        return {"id": n, "server": {g: (v[5] if v and len(v) > 5 else None) for g, v in srv.items()},
                "client": c[1] if c else None, "rows": len(cli.hair)}
    raise OpRefused("неизвестный запрос справки %s" % what)
