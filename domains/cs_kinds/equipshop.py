# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/equipshop.py — область «Магазин снаряжения 6800» (волна А4.1, 19.11.2026; разбор research_a4_data.md §1.8).

ВИТРИНА — только клиентская: Data/NPC/Shop/Freeshop.she клиента-донора _MINE (`cShopLoadFreeShop@0xCAB270`: 11 × u16 длин списков,
затем списки i32 подряд; размер = 22 + 4·сумма) → asda_import_equip_shop.py → DT_EquipShopList. ★ ПОРЯДОК КОДОВ ЗНАЧИМ: место
карточки = позиция кода в списке (страница = i / на странице, слот = i % на странице) — поэтому правка ТОЛЬКО «заменить код на
месте» (решение владельца 19.11: в А4 только правка существующих записей; вставка и удаление сдвинули бы страницы). Списки 11–13
файла нет — их строит рантайм из списка 4 по itemType/itemSubType item_list (UAsdaEquipShopSubsystem::LoadShe).
Своего списка у сервера НЕТ: покупка — 5020 CharItemBuy@0x50F170 (как лавка NPC): ShopBuyFlag ток.38, +36 = 1, цена ток.26 →
проверки лавки А3 (cs_kinds/shops.npc_rules) и решение владельца п.4 (предмет премиум-витрины — нельзя: у кода одна цена).
Цена — отдельной позицией «price» (пара сервер + клиент, А3).
Побочных эффектов при импорте нет.
"""
import os
import struct

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "equipshop", "Магазин снаряжения 6800"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
LISTS = 11                            # списков в файле (cShopLoadFreeShop)
SRV_FILES = []                        # сервер витрину не хранит


def _she_path():
    try:
        return os.path.join(E.data_dir(), "NPC", "Shop", "Freeshop.she")
    except ImportError:                 # служба на сервере: исходников порта нет — работает по снимку
        return os.path.join(E.UPROJ, "_no_asda_paths", "Freeshop.she")


CLIENT_FILES = {"equipshop": _she_path()}
IMPORTERS = {"equipshop": ("asda_import_equip_shop.py", "/Game/AsdaAssets/Data/NPC/DT_EquipShopList")}
KINDS = {
    "equipshop.set": ("Магазин снаряжения 6800: заменить товар на месте (Freeshop.she)", ("list", "index", "code"), False),
}


def parse_she(raw):
    """Байты .she → 11 списков кодов или None (файл не бьётся с шапкой) — как asda_import_equip_shop.parse_she."""
    if not raw or len(raw) < 2 * LISTS:
        return None
    counts = struct.unpack_from("<%dH" % LISTS, raw, 0)
    if 2 * LISTS + 4 * sum(counts) != len(raw):
        return None
    out, off = [], 2 * LISTS
    for n in counts:
        out.append(list(struct.unpack_from("<%di" % n, raw, off)) if n else [])
        off += 4 * n
    return out


def norm(kind, p):
    return {"list": E._ival(p, "list", 0, LISTS - 1), "index": E._ival(p, "index", 0, 9999), "code": E._ival(p, "code", 1, 100000)}


def target_key(kind, p):
    return "equipshop:%d:%d" % (p["list"], p["index"])


def k_equipshop_set(ev, p, rep):
    lists = ev.cli.equip
    if lists is None:
        raise OpRefused("витрина 6800 клиента (Freeshop.she) не прочитана — файл не бьётся с шапкой")
    li, ix, code = p["list"], p["index"], p["code"]
    cur = lists[li]
    if ix >= len(cur):
        raise OpRefused("в списке %d витрины 6800 мест %d — места %d нет (в А4 только правка существующих)" % (li, len(cur), ix))
    old = cur[ix]
    if old == code:
        raise OpRefused("на месте %d/%d уже %d — менять нечего" % (li, ix, code))
    if code < E.ITEM_FIRST:
        raise OpRefused("в витрину 6800 — только коды item_list (≥ 20551): путь покупки спецпредметов и самоцветов не подтверждён")
    if code not in ev.cli.items:
        raise OpRefused("кода %d нет в item_list клиента — карточки нет" % code)
    if not ev.exists(code):
        raise OpRefused("кода %d нет на сервере" % code)
    if ev.cli.on_premium(code) or code in E.AREAS[0].premium_new(ev):
        raise OpRefused("код %d — на премиум-витрине: у кода одна цена (золото = GXP), в магазин снаряжения его ставить нельзя "
                        "(решение владельца 19.11 п.4)" % code)
    why = E.AREAS[0].npc_rules(ev, code)
    if why:
        raise OpRefused("сервер не продаст (5020 CharItemBuy): " + why)
    if code in cur:
        rep["warnings"].append("код %d уже есть в списке %d (место %d) — будет дважды" % (code, li, cur.index(code)))
    sp, cp = E._int(ev.it_fields(code)[26]), ev.cli.price(code)
    if cp is not None and sp != cp:
        rep["warnings"].append("цена клиента %d ≠ цене сервера %d: игрок увидит одну, заплатит другую" % (cp, sp))
    if li == 4:
        rep["warnings"].append("список 4 — источник производных списков 11–13 (рантайм фильтрует по itemType/itemSubType item_list)")
    rep["text"] = "витрина 6800, список %d, место %d: %s → %s" % (li, ix, E.nm(old), E.nm(code))
    rep["_codes"] = [code]
    # ★ ревизия 33 М-4: замена товара витрины — правка баланса (как замена товара магазина чести)
    rep["_balance"] = [{"what": "витрина 6800, список %d, место %d: товар %d → %d" % (li, ix, old, code), "old": old, "new": code,
                        "codes": [old, code], "kind": "swap"}]
    rep["client"] = [{"type": "she_set", "file": "equipshop", "list": li, "index": ix, "old": old, "new": code}]
    ev.client += rep["client"]


def snapshot(snap):
    p = E.CLIENT_FILES["equipshop"]
    snap["equipshop"] = parse_she(open(p, "rb").read()) if os.path.isfile(p) else None


def parse(cli, d):
    cli.equip = d.get("equipshop")


def plan(pc):
    for e in pc["by_file"].get("equipshop", []):
        path = E.CLIENT_FILES["equipshop"]
        cur = pc["load"]("equipshop", path)
        lists = parse_she(cur[1])
        if lists is None:
            pc["errors"].append("Freeshop.she не бьётся с шапкой — правка отменена")
            continue
        if e["index"] >= len(lists[e["list"]]) or lists[e["list"]][e["index"]] != e["old"]:
            pc["errors"].append("витрина 6800, список %d, место %d: сейчас не %d — пересоберите набор" % (e["list"], e["index"], e["old"]))
            continue
        off = 2 * LISTS + 4 * (sum(len(x) for x in lists[:e["list"]]) + e["index"])
        b = bytearray(cur[1])
        struct.pack_into("<i", b, off, int(e["new"]))
        cur[1] = bytes(b)
        pc["importers"].add("equipshop")


def divergence(ev, cli, sec):
    rows = []
    for li, codes in enumerate(cli.equip or []):
        for ix, code in enumerate(codes):
            why = E.AREAS[0].npc_rules(ev, code)
            if why:
                rows.append({"list": li, "index": ix, "code": code, "name": E._name(code), "why": why})
                continue
            f = ev.it_fields(code)
            cp = cli.price(code)
            if f and cp is not None and E._int(f[26]) != cp:
                rows.append({"list": li, "index": ix, "code": code, "name": E._name(code), "why": "цена клиент %d ≠ сервер %d" % (cp, E._int(f[26]))})
            if cli.on_premium(code):
                rows.append({"list": li, "index": ix, "code": code, "name": E._name(code), "why": "код и на премиум-витрине (общая цена)"})
    sec("equipshop", "магазин снаряжения 6800: витрина против правил сервера", rows,
        "" if cli.equip is not None else "Freeshop.she не прочитан")
