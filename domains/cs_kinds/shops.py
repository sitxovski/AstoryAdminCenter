# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/shops.py — область «Магазины» (волна А3, 19.11.2026; вынесено из domains/shopdata.py в реестр видов в А4.0 БЕЗ смены
поведения: тексты, проверки и порядок сообщений — прежние). Разбор — Reports/admin_center/research_a3_shops.md; решения
владельца 19.11 — шапка domains/shopcs.py.

СЕРВЕР (во всех GameServer стойки; файлы GS читает один раз при старте → любая серверная половина = рестарт стойки с объявлением):
  item_table.txt              ток.26 (+41) — ЦЕНА: и золото лавки NPC (CharItemBuy@0x50F170), и GXP премиума (CharChargeShopBuy
                              @0x511DA0) — одно поле на оба магазина; ток.38 (+62) ShopBuyFlag лавки; ток.39 (+63) строка пакета/бустера.
  SellItemTable.txt           белый список покупки 5070: «макс_код<TAB>число», затем код на строку (загрузчик GameServer.c:68424:
                              массив new[макс+1] — код выше шапки отклоняется). У Indun свой порядок кодов — правится своим файлом.
  PackageItem_Table.txt       строка = номер пакета (ток.39 коробки 11/200): 5 пар «код, кол-во» (i16), пустая пара «-1 0».
  GachaItemRateTable.txt      строка = ПОЗИЦИЯ ток.39−1 (id строки GS не читает, sub_4B46B0 :72174): 35 пар «код, вес». Розыгрыш
                              Recv_GachaItemUse@0x4F48C0 (:94330): сумма весов пар с кодом > 0 и весом > 0 = T; v = sub_5329A0(0, T)
                              (rand() при T < 0x7FFF, иначе rand()<<15|rand(); v = r mod (T+1)); выигрывает пара с cum ≤ v < cum+вес;
                              v = T — мимо (ничего). Позиции 0–4 — «особые» (флаг v31).
  PrimiumGaChaTable.txt       пул премиум-гачи: «индекс слот код кол-во», индекс строго +1 от 0, слот < числа строк цен (иначе exit
                              при старте); шлюз gp7 держит пул в кэше до своего перезапуска (restart_stack останавливает и node gp7).
                              Шансов нет: приз выбирает gp7 равномерно (crypto.randomInt по пулу слота).
  PrimiumGaChaPriceTable.txt  «слот цена»; число строк = гейт номеров автоматов (word_7E037C), потолок 5.
КЛИЕНТ (порт, AstoryClient): item_list.csv (Price + DataHex +0xA4 — одно и то же поле, сверено на всех 59 390 строках 19.11),
  витрина 6000 PremiumShopBin.json + хвост ПАНЕЛИ PremiumShopBin_tail_panel.json (своя ведомость генератора — правило импортёра
  asda_import_premium_shop_bin.py), витрина 15300 BoosterShopList.json, лавки NPC js<npcId>.spd + ведомость npc_shop_hidden.csv
  → NpcShop.json, packagetable.csv, booster_list.csv (веса клиент не читает — только «Вид»), premium_gatya_data.csv (цена автомата).
  ★ А4.0: item_list / packagetable / booster_list — таблицы ItemDB: правка пишется и в ВЕДОМОСТЬ (shopdata.ledger_plan).
Побочных эффектов при импорте нет.
"""
import json
import os
import re
import struct
import subprocess
import sys

from core import config, hostshell
from core.ops import OpRefused
from domains import srvtables
from domains import shopdata as E

AREA, TITLE = "shops", "Магазины"
PERM_EDIT, PERM_APPLY = "shop.edit", "shop.apply"
BALANCE_GATE = True                   # ★ ревизия 33 В-2 (решение координатора 19.11 19:34): двойное подтверждение и для магазинов А3
SRV_TABLES = ("item_table.txt", "SellItemTable.txt", "PackageItem_Table.txt", "GachaItemRateTable.txt",
              "PrimiumGaChaTable.txt", "PrimiumGaChaPriceTable.txt")
SRV_FILES = [("GS", "ItemTable_Info\\" + t, "own" if t == "SellItemTable.txt" else "same") for t in SRV_TABLES]
SELL_CEIL = 100000                    # потолок шапки SellItemTable (разбор §3.3)
I16_MAX = 32767                       # кол-во пары пакета (__int16), вес стопки (SMALLINT БД)
SET_WEIGHT_CAP = 5000                 # потолок веса набора — решение владельца 26.10 (PREMIUM_ITEM_ADD_FLOW §3)
GACHA_SLOTS_MAX = 5                   # автоматов не больше 5 (GACHA_FLOW §4.3)
SPECIAL_MAX = 637                     # 1…637 — функциональные (лавка NPC их не продаёт, shop_audit.py)
ROLLS = 100000                        # прогон «100 000 открытий» бустера

CLIENT_FILES = {   # ключ → путь (ПК)
    "item_list": os.path.join(E.ITEMDB, "item_list.csv"),
    "packagetable": os.path.join(E.ITEMDB, "packagetable.csv"),
    "booster_list": os.path.join(E.ITEMDB, "booster_list.csv"),
    "premium_gatya": os.path.join(E.ITEMDB, "premium_gatya.csv"),
    "premium_gatya_data": os.path.join(E.ITEMDB, "premium_gatya_data.csv"),
    "premium6000": os.path.join(E.NPC_DIR, "PremiumShopBin.json"),
    "booster15300": os.path.join(E.NPC_DIR, "BoosterShopList.json"),
    "npcshop": os.path.join(E.NPC_DIR, "NpcShop.json"),
    "hidden": E.HIDDEN_CSV,
}
DT = {   # CSV ведомость → DataTable (точечная заливка asda_ml_dt_point.py со сторожем ручной правки)
    "item_list": "/Game/AsdaAssets/Data/ItemDB/DT_item_list",
    "packagetable": "/Game/AsdaAssets/Data/ItemDB/DT_packagetable",
    "booster_list": "/Game/AsdaAssets/Data/ItemDB/DT_booster_list",
    "premium_gatya_data": "/Game/AsdaAssets/Data/ItemDB/DT_premium_gatya_data",
}
IMPORTERS = {   # ведомость → импортёр DT. Оба со сторожем ручной правки «ассет = прежний JSON» (лавки — с 29.10; витрина 6000 —
                #   добавлен 19.11, ревизия 30 В-7) и итоговой строкой «ЗАВЕРШЕНО: импорт <DT> (ok)» ПОСЛЕ сохранения DT (В-6)
    "npcshop": ("asda_import_npc_shop.py", "/Game/AsdaAssets/Data/NPC/DT_NpcShopList"),
    "premium6000": ("asda_import_premium_shop_bin.py", "/Game/AsdaAssets/Data/NPC/DT_PremiumShopBin"),
}
CSV_KEYS = ("item_list", "packagetable", "booster_list", "premium_gatya_data")    # правки «ячейка CSV» (план клиента движка)

KINDS = {   # вид → (подпись, поля, срочно-допустимо)
    "price":          ("Цена (GXP премиума / золото лавки — одно поле item_table ток.26)", ("code", "value"), False),
    "sell.allow":     ("Разрешить продажу (SellItemTable)", ("code",), False),
    "sell.deny":      ("Запретить продажу (SellItemTable)", ("code",), True),
    "shop6000.add":   ("Показать на витрине 6000", ("code", "cat", "sub1", "sub2", "newflag"), False),
    "npcshop.add":    ("Лавка NPC: добавить товар", ("npc", "code"), False),
    "npcshop.hide":   ("Лавка NPC: скрыть товар", ("npc", "code", "reason"), False),
    "booster.weights": ("Бустер: состав и веса (GachaItemRateTable)", ("row", "pairs"), True),
    "package.set":    ("Набор / коробка: состав (PackageItem_Table)", ("row", "pairs"), False),
    "gacha.price":    ("Гача: цена автомата", ("slot", "value"), False),
    "gacha.pool":     ("Гача: пул автомата", ("slot", "rows"), False),
}


def _pairs(v, n_max, lo2, hi2, name):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            raise OpRefused("поле «%s»: список пар [[код, число], …]" % name)
    if not isinstance(v, list) or len(v) > n_max:
        raise OpRefused("поле «%s»: не больше %d пар [[код, число], …]" % (name, n_max))
    out = []
    for x in v:
        try:
            c, q = int(x[0]), int(x[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise OpRefused("поле «%s»: пара — два целых числа" % name)
        if c < 0 or c > SELL_CEIL or not lo2 <= q <= hi2:
            raise OpRefused("поле «%s»: код 0…%d, число %d…%d" % (name, SELL_CEIL, lo2, hi2))
        out.append([c, q])
    return out


def norm(kind, p):
    """Позиция → канонические параметры (отказ — OpRefused с причиной)."""
    _ival = E._ival
    if kind == "price":
        return {"code": _ival(p, "code", 1, SELL_CEIL), "value": _ival(p, "value", 0, 2000000000)}
    if kind in ("sell.allow", "sell.deny"):
        return {"code": _ival(p, "code", 1, SELL_CEIL)}
    if kind == "shop6000.add":
        if _ival(p, "code", 1, SELL_CEIL) < E.ITEM_FIRST:
            raise OpRefused("на витрину 6000 — только коды item_list (≥ 20551): путь покупки и цена самоцветов и спецпредметов на "
                            "витрине разбором не подтверждены (CharChargeShopBuy — ветки sub_532A90 / sub_532B10)")
        return {"code": _ival(p, "code", 1, SELL_CEIL), "cat": _ival(p, "cat", 0, 255), "sub1": _ival(p, "sub1", -1, 255),
                "sub2": _ival(p, "sub2", -1, 255), "newflag": _ival(p, "newflag", 0, 255)}
    if kind == "npcshop.add":
        return {"npc": _ival(p, "npc", 1, 1000000), "code": _ival(p, "code", 1, SELL_CEIL)}
    if kind == "npcshop.hide":
        reason = str(p.get("reason") or "").strip()
        if not reason or len(reason) > 200:
            raise OpRefused("причина скрытия обязательна (до 200 символов)")
        return {"npc": _ival(p, "npc", 1, 1000000), "code": _ival(p, "code", 1, SELL_CEIL), "reason": reason}
    if kind == "booster.weights":
        pr = _pairs(p.get("pairs"), 35, 0, 2000000000, "pairs")
        return {"row": _ival(p, "row", 1, 1000000), "pairs": pr + [[0, 0]] * (35 - len(pr))}
    if kind == "package.set":
        pr = [x for x in _pairs(p.get("pairs"), 5, 1, I16_MAX, "pairs") if x[0] > 0]
        if not pr:
            raise OpRefused("набор без предметов")
        return {"row": _ival(p, "row", 0, 1000000), "pairs": pr}
    if kind == "gacha.price":
        return {"slot": _ival(p, "slot", 0, GACHA_SLOTS_MAX - 1), "value": _ival(p, "value", 1, 2000000000)}
    if kind == "gacha.pool":
        rows = [x for x in _pairs(p.get("rows"), 3000, 1, I16_MAX, "rows") if x[0] > 0]
        if not rows:
            raise OpRefused("пул автомата пуст")
        return {"slot": _ival(p, "slot", 0, GACHA_SLOTS_MAX - 1), "rows": rows}
    raise OpRefused("неизвестный вид позиции %s" % kind)


def target_key(kind, p):
    """Цель позиции (две позиции на одну цель в наборе — отказ)."""
    if kind in ("price",):
        return "price:%d" % p["code"]
    if kind in ("sell.allow", "sell.deny"):
        return "sell:%d" % p["code"]
    if kind == "shop6000.add":
        return "shop6000:%d" % p["code"]
    if kind in ("npcshop.add", "npcshop.hide"):
        return "npc:%d:%d" % (p["npc"], p["code"])
    if kind == "booster.weights":
        return "booster:%d" % p["row"]
    if kind == "package.set":
        return "package:%d" % p["row"]
    return "%s:%d" % (kind, p["slot"])


# =====================================================================================================================
# ПОЗИЦИИ
# =====================================================================================================================
def k_price(ev, p, rep):
    code, val = p["code"], p["value"]
    if code < E.ITEM_FIRST:
        raise OpRefused("цена спецпредмета (Function_Table, код < 20551) — путь цены не подтверждён разбором; не в А3")
    if code in ev.pmap:
        raise OpRefused("код %d — в карте шлюза gp7 (premium_item_map.json): цену берёт карта, клиентская цена карточки "
                        "не подтверждена разбором; не в А3" % code)
    olds = set()
    for g in E.GS:
        t = ev.st.get(g, "item_table.txt")
        i = t.index().get(code)
        if not i:
            raise OpRefused("кода %d нет в item_table %s" % (code, g))
        f = t.lines[i].split(b"\t")
        if len(f) < 42:
            raise OpRefused("строка %d item_table %s — меньше 42 полей" % (code, g))
        olds.add(E._int(f[26].decode("latin-1")))
        f[26] = re.sub(rb"[+-]?\d+", str(val).encode("ascii"), f[26], count=1)     # пробелы поля — как были
        t.set_line(i, b"\t".join(f))
    old = sorted(olds)[0]
    if len(olds) > 1:
        rep["warnings"].append("цена на GameServer разошлась: %s" % ", ".join(map(str, sorted(olds))))
    cp = ev.cli.price(code)
    if cp is None:
        raise OpRefused("кода %d нет в item_list клиента — карточки нет" % code)
    if cp != old:
        rep["warnings"].append("цены уже расходились: клиент %d, сервер %d" % (cp, old))
    hx = ev.cli.items[code][2]
    if hx is not None and hx != cp:
        rep["errors"].append("item_list: Price %d ≠ DataHex +0xA4 %d — строка клиента не согласована" % (cp, hx))
    npcs = ev.cli.npc_shown(code)
    if npcs:
        rep["warnings"].append("та же цена у лавок NPC %s: золото = GXP (одно поле ток.26)" % ", ".join(map(str, npcs)))
    rep["text"] = "цена %s: %d → %d (сервер ×%d GS, клиент item_list.Price)" % (E.nm(code), old, val, len(E.GS))
    rep["_codes"] = [code]
    rep["_balance"] = [{"what": "цена %s" % E.nm(code), "old": old, "new": val, "codes": [code]}]
    rep["client"] = [{"type": "csv_cell", "file": "item_list", "key_col": "ItemCode", "key": str(code), "col": "Price",
                      "old": str(cp), "new": str(val)},
                     {"type": "csv_hex_i32", "file": "item_list", "key_col": "ItemCode", "key": str(code), "col": "DataHex",
                      "off": E.PRICE_OFF, "old": cp, "new": val}]
    ev.client += rep["client"]


def k_sell_allow(ev, p, rep):
    code = p["code"]
    if not ev.exists(code):
        raise OpRefused("кода %d нет на сервере (item_table / Function_Table)" % code)
    if code >= E.ITEM_FIRST and code not in ev.cli.items:
        raise OpRefused("кода %d нет в item_list клиента — карточки нет (сервер после клиента)" % code)
    done = []
    for g in E.GS:
        t = ev.st.get(g, "SellItemTable.txt")
        hm = t.head_max
        if t.allow(code):
            done.append(g)
            if t.head_max != hm:
                rep["warnings"].append("%s: шапка SellItemTable поднимется %d → %d" % (g, hm, t.head_max))
    if not done:
        rep["warnings"].append("код уже в белом списке всех GS — менять нечего")
    rep["text"] = "разрешить продажу %s: SellItemTable %s" % (E.nm(code), ", ".join(done) or "без изменений")
    rep["_codes"] = [code]
    rep["client"] = []


def k_sell_deny(ev, p, rep):
    code = p["code"]
    done = [g for g in E.GS if ev.st.get(g, "SellItemTable.txt").deny(code)]
    if not done:
        rep["warnings"].append("кода нет в белом списке ни одного GS — менять нечего")
    if ev.cli.on_premium(code):
        rep["warnings"].append("карточка видна на витрине: до выпуска клиента покупка даст отказ 5071 код 14 без списания")
    rep["text"] = "запретить продажу %s: SellItemTable %s" % (E.nm(code), ", ".join(done) or "без изменений")


def k_shop6000_add(ev, p, rep):
    code = p["code"]
    if code in ev.cli.p6000 or code in ev.cli.tail:
        raise OpRefused("код %d уже на витрине 6000" % code)
    if (p["cat"], p["sub1"]) not in ev.cli.cats6000:
        raise OpRefused("на витрине 6000 нет образца категории %d / %d — импортёр не соберёт запись" % (p["cat"], p["sub1"]))
    if not ev.exists(code):
        raise OpRefused("кода %d нет на сервере" % code)
    if code >= E.ITEM_FIRST and code not in ev.cli.items:
        raise OpRefused("кода %d нет в item_list клиента" % code)
    npcs = ev.cli.npc_shown(code)
    if npcs:
        raise OpRefused("код %d продаётся в лавке NPC %s за золото — у кода одна цена (золото = GXP); решение владельца 19.11 п.4"
                        % (code, ", ".join(map(str, npcs))))
    row = {"ItemId": code, "Category": p["cat"], "Sub1": p["sub1"], "Sub2": p["sub2"], "Field16": 0, "Field20": 0,
           "NewFlag": p["newflag"], "Note": "0", "Field57": 0, "Name": "0"}
    rep["text"] = "витрина 6000: показать %s (категория %d / %d / %d, метка %d)" % (E.nm(code), p["cat"], p["sub1"], p["sub2"],
                                                                               p["newflag"])
    rep["client"] = [{"type": "tail6000_add", "file": "panel_tail", "row": row}]
    ev.client += rep["client"]
    rep["_shop6000"] = code
    rep["_codes"] = [code]


def npc_rules(ev, code):
    """Правила CharItemBuy@0x50F170 (как shop_audit.py) по item_table / Cellob всех GS: None — продаст, иначе причина."""
    if 1 <= code <= SPECIAL_MAX or 2001 <= code < srvtables.CELLOB_BASE:
        return "особый предмет — сервер в лавке не продаёт (5021 код 0)"
    if srvtables.CELLOB_BASE <= code < E.ITEM_FIRST:
        c = ev.cel.get(code)
        if not c:
            return "нет в Cellob_Table сервера (код 5)"
        if E._int(c[19] if len(c) > 19 else "0") == 0:
            return "Cellob +42 (продаётся) = 0 (код 5)"
        if E._int(c[2]) > 2:
            return "Cellob +5 > 2 (код 0)"
        return None
    for g in E.GS:
        f = ev.it_fields(code, g)
        if not f:
            return "нет в item_table %s (код 5)" % g
        if E._int(f[38]) == 0:
            return "%s: item_table ток.38 (+62, ShopBuyFlag) = 0 → 5021 код 5" % g
        if E._int(f[24]) != 1:          # CharItemBuy: +36 ≠ 1 → отказ (у расходника тоже нужно +36 = 1; ревизия 30 К-8)
            return "%s: предмет сумки с +36 = %d (нужно 1) — код 0" % (g, E._int(f[24]))
    return None


def k_npcshop_add(ev, p, rep):
    npc, code = p["npc"], p["code"]
    v = ev.cli.npc.get(npc)
    if not v or v.get("spd") is None:
        raise OpRefused("лавки NPC %d нет (js%d.spd клиента) — новая лавка не в А3" % (npc, npc))
    if code in (v.get("shown") or []):
        raise OpRefused("товар уже в лавке NPC %d" % npc)
    if ev.cli.on_premium(code) or code in premium_new(ev):
        raise OpRefused("код %d — на премиум-витрине: у кода одна цена (золото = GXP), в лавку NPC его ставить нельзя "
                        "(решение владельца 19.11 п.4)" % code)
    why = npc_rules(ev, code)
    if why:
        raise OpRefused("сервер не продаст в лавке: " + why)
    sp = E._int(ev.it_fields(code)[26]) if code >= E.ITEM_FIRST else None
    cp = ev.cli.price(code)
    if sp is not None and cp is not None and sp != cp:
        rep["warnings"].append("цена клиента %d ≠ цене сервера %d: игрок увидит одну, заплатит другую" % (cp, sp))
    if code in (v.get("hidden") or []):
        ed = {"type": "hidden_del", "file": "hidden", "npc": npc, "code": code}
        how = "убрать строку ведомости скрытых"
    else:
        ed = {"type": "spd_append", "file": "spd", "npc": npc, "code": code}
        how = "дописать в js%d.spd" % npc
    rep["text"] = "лавка NPC %d: добавить %s (%s)" % (npc, E.nm(code), how)
    rep["client"] = [ed]
    ev.client += rep["client"]


def k_npcshop_hide(ev, p, rep):
    npc, code = p["npc"], p["code"]
    v = ev.cli.npc.get(npc)
    if not v or code not in (v.get("shown") or []):
        raise OpRefused("товара %d нет в витрине лавки NPC %d" % (code, npc))
    rep["text"] = "лавка NPC %d: скрыть %s" % (npc, E.nm(code))
    rep["client"] = [{"type": "hidden_add", "file": "hidden", "npc": npc, "code": code, "name": E._name(code),
                      "reason": p["reason"]}]
    ev.client += rep["client"]


def _code_ok(ev, code, rep, what):
    if code and not ev.exists(code):
        rep["errors"].append("%s: кода %d нет на сервере" % (what, code))


def k_booster_weights(ev, p, rep):
    row, pairs = p["row"], p["pairs"]
    old = None
    for g in E.GS:
        t = ev.st.get(g, "GachaItemRateTable.txt")
        n = E._int(t.lines[0].decode("latin-1"))
        if not 1 <= row <= n or row >= len(t.lines):
            raise OpRefused("строки %d в GachaItemRateTable %s нет (строк %d)" % (row, g, n))
        f = E._f(t.lines[row])
        if E._int(f[0]) != row:
            rep["warnings"].append("%s: у строки на позиции %d id %s — GS берёт ПОЗИЦИЮ (ток.39−1), id не читает" % (g, row, f[0]))
        cur = [[E._int(f[1 + 2 * j]), E._int(f[2 + 2 * j])] for j in range(35)]
        old = old or cur
        t.set_line(row, ("%d\t" % E._int(f[0]) + "\t".join("%d\t%d" % (c, w) for c, w in pairs)).encode("ascii"))
    for j, (c, w) in enumerate(pairs):
        _code_ok(ev, c, rep, "позиция %d" % j)
    act = [w for c, w in pairs if c > 0 and w > 0]
    if not act:
        raise OpRefused("сумма весов 0 — бустер ничего не даст (Recv_GachaItemUse: v39 = 0)")
    codes_changed = [c for c, _ in old] != [c for c, _ in pairs]
    rep["urgent_ok"] = not codes_changed
    users = ev.booster_users(row)
    rep["_codes"] = users
    if not users:
        rep["warnings"].append("строку %d не использует ни один предмет item_table (ток.39 = %d)" % (row, row))
    odds = booster_odds(pairs)
    sim = booster_sim(pairs, ROLLS)
    ev.sim["booster:%d" % row] = {"odds": odds, "sim": sim, "old_odds": booster_odds(old)}
    # ★ А4.0: баланс — шанс каждого кода «было → станет» (двойное подтверждение при изменении > 2 раз; shopdata.balance)
    oc, nc = {}, {}
    for _j, c, _w, ch in booster_odds(old)["rows"]:
        oc[c] = oc.get(c, 0.0) + ch
    for _j, c, _w, ch in odds["rows"]:
        nc[c] = nc.get(c, 0.0) + ch
    rep["_balance"] = [{"what": "бустер %d: шанс %s, %%" % (row, E.nm(c)), "old": round(oc.get(c, 0.0) * 100, 4),
                        "new": round(nc.get(c, 0.0) * 100, 4), "codes": users} for c in sorted(set(oc) | set(nc))]
    cl = ev.cli.booster.get(row)
    if cl is None:
        rep["errors"].append("строки %d нет в booster_list клиента" % row)
    else:
        rep["client"] = [{"type": "csv_cells", "file": "booster_list", "key_col": "Code", "key": str(row),
                          "cells": dict([("Slot%02dItemCode" % j, [str(cl[j][0]), str(pairs[j][0])]) for j in range(35)]
                                        + [("Slot%02dWeight" % j, [str(cl[j][1]), str(pairs[j][1])]) for j in range(35)]),
                          "optional": not codes_changed}]
        ev.client += rep["client"]
    rep["text"] = "бустер, строка %d (%s): %s; мимо %.4f %%" % (
        row, ", ".join(E.nm(u) for u in users[:3]) or "нет предметов",
        "коды меняются" if codes_changed else "только веса", odds["miss"] * 100)


def k_package_set(ev, p, rep):
    row, pairs = p["row"], p["pairs"]
    p98 = srvtables.patch_on_all("P98_PremiumStackAmount")
    weight_total = 0
    for j, (c, q) in enumerate(pairs):
        if c < E.ITEM_FIRST:
            if c not in ev.fn:
                rep["errors"].append("пара %d: функционального %d нет в Function_Table (sub_532B10)" % (j, c))
            elif q != 1:
                rep["errors"].append("пара %d: функциональный %d — только ×1" % (j, c))
            continue
        ti = ev.it_fields(c)
        if not ti:
            rep["errors"].append("пара %d: предмета %d нет в item_table (sub_532A90)" % (j, c))
            continue
        w = E._int(ti[2])
        stack = ti[3] == "4" and ti[23] == "1" and ti[24] == "1" and ti[16] != "10"   # = asda_premium_box_add.verify
        if stack:
            if q > I16_MAX or q * w > I16_MAX:
                rep["errors"].append("пара %d: %s × %d (вес %d) не влезает в одну стопку i16/SMALLINT" % (j, E.nm(c), q, w))
            off = [g for g, on in p98.items() if not on]
            if off:
                rep["warnings"].append("стопочный %s: P98 выключен на %s" % (E.nm(c), ", ".join(off)))
        elif q != 1:
            rep["errors"].append("пара %d: %s не стопочный — количество %d пакетом не выдаётся (по штуке в паре)" % (j, E.nm(c), q))
        weight_total += q * w
    if weight_total > SET_WEIGHT_CAP:
        rep["warnings"].append("вес набора %d > %d (потолок набора, решение владельца 26.10) — у части персонажей перегруз"
                               % (weight_total, SET_WEIGHT_CAP))
    old = None
    full = pairs + [[-1, 0]] * (5 - len(pairs))
    for g in E.GS:
        t = ev.st.get(g, "PackageItem_Table.txt")
        i = t.index().get(row)
        if not i:
            raise OpRefused("строки пакета %d нет в PackageItem_Table %s" % (row, g))
        f = E._f(t.lines[i])
        cur = [[E._int(f[1 + 2 * k]), E._int(f[2 + 2 * k])] for k in range(5) if len(f) > 2 + 2 * k]
        old = old or cur
        t.set_line(i, ("%d\t" % row + "\t".join("%d\t%d" % (c, q) for c, q in full)).encode("ascii"))
    users = ev.box_users(row)
    rep["_codes"] = users
    if not users:
        rep["warnings"].append("строку %d не использует ни одна коробка 11/200 item_table" % row)
    # ★ А4.0: баланс — количество каждого кода в наборе «было → станет»
    oq, nq = {}, {}
    for c, q in old or []:
        if c > 0:
            oq[c] = oq.get(c, 0) + q
    for c, q in pairs:
        nq[c] = nq.get(c, 0) + q
    rep["_balance"] = [{"what": "набор %d: %s, шт." % (row, E.nm(c)), "old": oq.get(c, 0), "new": nq.get(c, 0), "codes": users}
                       for c in sorted(set(oq) | set(nq))]
    cl = ev.cli.pkg.get(row)
    if cl is None:
        rep["errors"].append("строки %d нет в packagetable клиента" % row)
    else:
        cells = {}
        for k in range(5):
            c, q = full[k]
            cells["Item%d" % k] = [str(cl[k][0]), str(c)]
            cells["Qty%d" % k] = [str(cl[k][1]), str(q)]
        if cl[5][0] > 0:
            rep["warnings"].append("у клиента шестая пара (%d × %d) — сервер её не выдаёт; панель её не трогает" % tuple(cl[5]))
        rep["client"] = [{"type": "csv_cells", "file": "packagetable", "key_col": "Index", "key": str(row), "cells": cells}]
        ev.client += rep["client"]
    rep["text"] = "набор, пакет %d (%s): %s → %s" % (
        row, ", ".join(E.nm(u) for u in users[:3]) or "нет коробок",
        "; ".join("%d×%d" % (c, q) for c, q in old if c > 0) or "пусто", "; ".join("%d×%d" % (c, q) for c, q in pairs))


def k_gacha_price(ev, p, rep):
    slot, val = p["slot"], p["value"]
    old = None
    for g in E.GS:
        t = ev.st.get(g, "PrimiumGaChaPriceTable.txt")
        i = t.index().get(slot)
        if i is None or slot >= E._int(t.lines[0].decode("latin-1")):
            raise OpRefused("автомата %d нет в PrimiumGaChaPriceTable %s — число автоматов в А3 не меняется" % (slot, g))
        old = E._int(E._f(t.lines[i])[1])
        t.set_line(i, ("%d\t%d" % (slot, val)).encode("ascii"))
    cp = ev.cli.gatya_price.get(slot)
    if cp is None:
        raise OpRefused("автомата %d нет в premium_gatya_data клиента" % slot)
    if cp != old:
        rep["warnings"].append("цены уже расходились: клиент %d, сервер %d" % (cp, old))
    rep["text"] = "гача, автомат %d: цена %d → %d" % (slot + 1, old, val)
    rep["_balance"] = [{"what": "гача, автомат %d: цена" % (slot + 1), "old": old, "new": val, "codes": []}]
    rep["client"] = [{"type": "csv_cell", "file": "premium_gatya_data", "key_col": "Slot", "key": str(slot), "col": "Price",
                      "old": str(cp), "new": str(val)}]
    ev.client += rep["client"]


def k_gacha_pool(ev, p, rep):
    slot, rows = p["slot"], p["rows"]
    # коды < 20551 в пуле живого dev уже есть (30, 32, 33… — каталожные номера премиума, выдаёт шлюз gp7): такие допустимы,
    # только если они уже стоят в каком-либо пуле стойки (путь выдачи доказан живым пулом); прочие — отказ «не подтверждено»
    proven = {c for _s, c, _q in ev.st.get("GameServer", "PrimiumGaChaTable.txt").orig_rows if c < E.ITEM_FIRST}
    for j, (c, q) in enumerate(rows):
        if c >= E.ITEM_FIRST and not ev.it_fields(c):
            rep["errors"].append("приз %d: кода %d нет в item_table" % (j, c))
        elif c < E.ITEM_FIRST and c not in proven:
            rep["errors"].append("приз %d: код %d < 20551 не встречается ни в одном пуле стойки — путь выдачи шлюзом не подтверждён" % (j, c))
    old = None
    for g in E.GS:
        pt = ev.st.get(g, "PrimiumGaChaPriceTable.txt")
        n = E._int(pt.lines[0].decode("latin-1"))
        if slot >= n:
            raise OpRefused("автомата %d нет: в PrimiumGaChaPriceTable %s строк %d (iSlotNumber ≤ числа строк цен)" % (slot, g, n))
        t = ev.st.get(g, "PrimiumGaChaTable.txt")
        old = old or t.slot_rows(slot)
        t.replace(slot, rows)
    uniq = len({c for c, _ in rows})
    rep["warnings"].append("шансы — равномерно по строкам пула: 1/%d на строку (приз выбирает шлюз gp7, таблицы шансов нет)" % len(rows))
    if not all(srvtables.patch_on_all("P16_GachaToInven").values()):
        rep["warnings"].append("P16 выключен: приз идёт в элитный почтовый ящик, не в сумку (поведение dev)")
    rep["warnings"].append("нужен перезапуск GameServer и шлюза gp7 (пул в кэше gp7) — restart_stack делает оба")
    view = sorted({r[2] for r in ev.cli.gatya if r[3] == slot})
    pool = {c for c, _ in rows}
    miss = [c for c in view if c not in pool]
    if miss:
        rep["warnings"].append("витрина автомата клиента (ViewSlot %d) показывает %d кодов не из нового пула — витрина автомата "
                               "в А3 не правится (коды premium_gatya.csv не сопоставлены с пулом сервера)" % (slot, len(miss)))
    # ★ А4.0: баланс — доля строк кода в пуле (шанс = строк кода / строк пула)
    oc, ncnt = {}, {}
    for c, _q in old or []:
        oc[c] = oc.get(c, 0) + 1
    for c, _q in rows:
        ncnt[c] = ncnt.get(c, 0) + 1
    on, nn = max(1, len(old or [])), max(1, len(rows))
    rep["_balance"] = [{"what": "гача, автомат %d: шанс %s, %%" % (slot + 1, E.nm(c)), "old": round(oc.get(c, 0) * 100.0 / on, 4),
                        "new": round(ncnt.get(c, 0) * 100.0 / nn, 4), "codes": [c]} for c in sorted(set(oc) | set(ncnt))]
    rep["text"] = "гача, автомат %d: пул %d → %d строк (%d разных призов)" % (slot + 1, len(old or []), len(rows), uniq)


# ---- сквозные проверки по итоговому состоянию ----
def premium_new(ev):
    return {r.get("_shop6000") for r in ev.positions if r.get("_shop6000")}


def cross_pre(ev):
    """Витрина 6000: белый список, ток.24, цена клиента = ток.26 (до общей проверки копий — порядок сообщений А3)."""
    for r in ev.positions:
        code = r.get("_shop6000")
        if not code:
            continue
        for g in E.GS:
            if not ev.st.get(g, "SellItemTable.txt").has(code):
                r["errors"].append("%s: кода нет в SellItemTable — магазин не продаст (5071 код 14); добавьте «Разрешить продажу»" % g)
            elif code > ev.st.get(g, "SellItemTable.txt").head_max:
                r["errors"].append("%s: код выше шапки SellItemTable" % g)
        if code >= E.ITEM_FIRST:
            f = ev.it_fields(code)
            if f and E._int(f[24]) not in (0, 3):
                r["errors"].append("item_table ток.24 = %s (не 0/3) — сервер откажет в покупке (5071 код 0)" % f[24])
            cp = ev.cli.price(code)
            np_ = next((x["params"].get("value") for x in ev.positions if x["kind"] == "price"
                        and str(x["params"].get("code")) == str(code)), None)
            cp = int(np_) if np_ is not None else cp
            sp = E._int(f[26]) if f else None
            if cp is not None and sp is not None and cp != sp:
                r["errors"].append("цена клиента %d ≠ ток.26 сервера %d — шлюз сверит с файлом сервера" % (cp, sp))


def cross_post(ev):
    """Паритет Ch2 белого списка (после общей проверки копий)."""
    fm = ev.snap.md5.get("GameServer\\ItemTable_Info\\SellItemTable.txt")
    cm = ev.snap.md5.get("Ch2_GameServer\\ItemTable_Info\\SellItemTable.txt")
    if fm != cm:
        ev.errors.append("SellItemTable канала 2 ≠ поля (паритет Ch2) — сначала stack_parity")


def after_run(ev):
    """★ ревизия 30 М-1: п.4 — по ИТОГОВОМУ состоянию набора, независимо от порядка позиций."""
    both = sorted(premium_new(ev) & {int(r["params"]["code"]) for r in ev.positions if r["kind"] == "npcshop.add" and not r["errors"]})
    if both:
        ev.errors.append("коды %s в наборе ставятся и на премиум-витрину, и в лавку NPC — у кода одна цена (золото = GXP); "
                         "решение владельца 19.11 п.4" % ", ".join(map(str, both)))


# =====================================================================================================================
# БУСТЕР: точные шансы и прогон «100 000 открытий»
# =====================================================================================================================
def booster_odds(pairs):
    """Точные шансы Recv_GachaItemUse: {"rows": [[позиция, код, вес, шанс]], "miss": шанс «мимо», "special": шанс позиций 0–4}."""
    act = [(j, c, w) for j, (c, w) in enumerate(pairs) if c > 0 and w > 0]
    total = sum(w for _, _, w in act)
    if total <= 0:
        return {"rows": [], "miss": 1.0, "special": 0.0, "total": 0}
    m = total + 1
    n = 32768 if total < 0x7FFF else (1 << 30)          # rand() или rand()<<15 | rand() (sub_5329A0)
    q, rem = divmod(n, m)
    cnt = lambda lo, hi: (hi - lo) * q + max(0, min(hi, rem) - lo)
    rows, cum = [], 0
    for j, c, w in act:
        rows.append([j, c, w, cnt(cum, cum + w) / float(n)])
        cum += w
    return {"rows": rows, "miss": cnt(total, total + 1) / float(n), "special": sum(r[3] for r in rows if r[0] <= 4),
            "total": total}


def booster_sim(pairs, n=ROLLS, seed=None):
    """«Открыть n раз» генератором MSVC rand (LCG 214013 / 2531011, как у GameServer) → {позиция: выпало}, miss, special."""
    import random
    import bisect
    s = (seed if seed is not None else random.SystemRandom().getrandbits(32)) & 0xFFFFFFFF
    act = [(j, c, w) for j, (c, w) in enumerate(pairs) if c > 0 and w > 0]
    total = sum(w for _, _, w in act)
    out, miss, special = {}, 0, 0
    if total <= 0:
        return {"n": n, "hits": {}, "miss": n, "special": 0}
    bounds, cum = [], 0
    for j, c, w in act:
        bounds.append((cum, cum + w, j))
        cum += w
    starts = [b[0] for b in bounds]
    for _ in range(n):
        s = (s * 214013 + 2531011) & 0xFFFFFFFF
        r = (s >> 16) & 0x7FFF
        if total >= 0x7FFF:
            s = (s * 214013 + 2531011) & 0xFFFFFFFF
            r = (r << 15) | ((s >> 16) & 0x7FFF)
        v = r % (total + 1)
        if v >= total:
            miss += 1
            continue
        k = bisect.bisect_right(starts, v) - 1
        j = bounds[k][2]
        out[j] = out.get(j, 0) + 1
        if j <= 4:
            special += 1
    return {"n": n, "hits": {str(k): v for k, v in sorted(out.items())}, "miss": miss, "special": special}


# =====================================================================================================================
# КЛИЕНТ: снимок и разбор
# =====================================================================================================================
def snapshot(snap):
    """Магазинная часть снимка клиентских таблиц (в тот же dict, ключи — как в А3)."""
    items = {}
    for r in E._read_csv(E.CLIENT_FILES["item_list"]):
        items[r["ItemCode"]] = [int(r["_row"]), int(r["Price"]), E._hex_price(r["DataHex"])]
    snap["items"] = items
    snap["premium6000"] = [[r["ItemId"], r["Category"], r["Sub1"], r["Sub2"], r["NewFlag"], r.get("GiftCode", 0)]
                           for r in json.load(open(E.CLIENT_FILES["premium6000"], encoding="utf-8"))]
    snap["panel_tail"] = (json.load(open(E.PANEL_TAIL, encoding="utf-8"))["rows"] if os.path.isfile(E.PANEL_TAIL) else [])
    snap["booster15300"] = sorted({int(r["ItemCode"]) for r in json.load(open(E.CLIENT_FILES["booster15300"], encoding="utf-8"))})
    shown = {int(r["NpcId"]): [int(c) for c in r["ItemCodes"]] for r in json.load(open(E.CLIENT_FILES["npcshop"], encoding="utf-8"))}
    hidden = {}
    if os.path.isfile(E.HIDDEN_CSV):
        for r in E._read_csv(E.HIDDEN_CSV):
            hidden.setdefault(int(r["npc"]), []).append(int(r["code"]))
    spd = {}
    d = E.spd_dir()
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.fullmatch(r"js(\d+)\.spd", fn, re.I)
        if m:
            raw = open(os.path.join(d, fn), "rb").read()
            cnt = struct.unpack_from("<I", raw, 4)[0] if len(raw) >= 8 else -1
            spd[int(m.group(1))] = list(struct.unpack_from("<%dI" % cnt, raw, 8)) if cnt >= 0 and 8 + 4 * cnt == len(raw) else None
    snap["npc"] = {str(n): {"spd": spd.get(n), "hidden": hidden.get(n, []), "shown": shown.get(n, [])}
                   for n in sorted(set(spd) | set(shown))}
    snap["pkg"] = {r["Index"]: [[E._int(r["Item%d" % i]), E._int(r["Qty%d" % i])] for i in range(6)]
                   for r in E._read_csv(E.CLIENT_FILES["packagetable"])}
    bl = {}
    for r in E._read_csv(E.CLIENT_FILES["booster_list"]):
        pairs = [[E._int(r["Slot%02dItemCode" % i]), E._int(r["Slot%02dWeight" % i])] for i in range(35)]
        bl[r["Code"]] = pairs
    snap["booster"] = bl
    snap["gatya"] = [[E._int(r["Index"]), E._int(r["SlotNumber"]), E._int(r["ItemCode"]), E._int(r["ViewSlot"]), E._int(r["Quantity"])]
                     for r in E._read_csv(E.CLIENT_FILES["premium_gatya"])]
    snap["gatya_price"] = {r["Slot"]: E._int(r["Price"]) for r in E._read_csv(E.CLIENT_FILES["premium_gatya_data"])}


def parse(cli, d):
    cli.items = {int(k): v for k, v in d["items"].items()}
    cli.p6000 = {int(r[0]): r for r in d["premium6000"]}
    cli.tail = {int(r["ItemId"]): r for r in d.get("panel_tail") or []}
    cli.cats6000 = {(int(r[1]), int(r[2])) for r in d["premium6000"]}
    cli.b15300 = set(d["booster15300"])
    cli.npc = {int(k): v for k, v in d["npc"].items()}
    cli.pkg = {int(k): v for k, v in d["pkg"].items()}
    cli.booster = {int(k): v for k, v in d["booster"].items()}
    cli.gatya = d["gatya"]
    cli.gatya_price = {int(k): v for k, v in d["gatya_price"].items()}


# =====================================================================================================================
# КЛИЕНТСКАЯ ПОЛОВИНА: файлы, которые правит только эта область (хвост витрины 6000, ведомость скрытых, .spd)
# =====================================================================================================================
def plan(pc):
    """Правки панели-хвоста, ведомости скрытых и .spd (pc — контекст плана движка: by_file, load, errors, importers, cs_id)."""
    by_file, load, errors, imp, cs_id = pc["by_file"], pc["load"], pc["errors"], pc["importers"], pc["cs_id"]
    es = by_file.get("panel_tail")
    if es:
        cur = load("panel_tail", E.PANEL_TAIL)
        doc = json.loads(cur[0].decode("utf-8")) if cur[0] else {
            "_comment": "строки витрины 6000, добавленные наборами изменений админ-центра (domains/shopdata.py); дописывает "
                        "asda_import_premium_shop_bin.py (TAIL_JSONS)", "rows": []}
        have = {int(r["ItemId"]) for r in doc["rows"]}
        for e in es:
            if e["row"]["ItemId"] in have:
                errors.append("витрина 6000: код %d уже в хвосте панели" % e["row"]["ItemId"])
                continue
            doc["rows"].append(dict(e["row"], _changeset=cs_id))
        cur[1] = (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        imp.add("premium6000")
    es = by_file.get("hidden")
    if es:
        cur = load("hidden", E.HIDDEN_CSV)
        body = cur[0].decode("utf-8-sig")
        nl = "\r\n" if "\r\n" in body else "\n"
        lines = body.split(nl)
        for e in es:
            if e["type"] == "hidden_add":
                if lines and lines[-1] == "":
                    lines.pop()
                lines.append(E._csv_join([str(e["npc"]), str(e["code"]), e["name"], "скрыто набором изменений №%s: %s" % (cs_id, e["reason"])]))
                lines.append("")
            else:
                keep = [ln for ln in lines if not (ln and E._csv_line(ln)[:2] == [str(e["npc"]), str(e["code"])])]
                if len(keep) == len(lines):
                    errors.append("ведомость скрытых: строки %d/%d нет" % (e["npc"], e["code"]))
                lines = keep
        cur[1] = (b"\xef\xbb\xbf" if cur[0].startswith(b"\xef\xbb\xbf") else b"") + nl.join(lines).encode("utf-8")
        imp.add("npcshop")
    for e in by_file.get("spd", []):
        path = os.path.join(E.spd_dir(), "js%d.spd" % e["npc"])
        cur = load("spd", path)
        if cur[1] is None:
            errors.append("нет файла лавки NPC %s" % E.rel_area(path))
            continue
        raw = cur[1]
        z, cnt = struct.unpack_from("<II", raw, 0)
        codes = list(struct.unpack_from("<%dI" % cnt, raw, 8))
        if e["code"] in codes:
            errors.append("js%d.spd уже содержит %d" % (e["npc"], e["code"]))
            continue
        codes.append(e["code"])
        cur[1] = struct.pack("<II", z, len(codes)) + struct.pack("<%dI" % len(codes), *codes)
        imp.add("npcshop")


def allowed_extra(ap):
    """Путь лавки NPC js<N>.spd в каталоге лавок клиента (ревизия 30 К-3)."""
    try:
        spd = os.path.normcase(os.path.abspath(E.spd_dir()))
    except Exception:
        return False
    return os.path.dirname(ap) == spd and bool(re.fullmatch(r"js\d+\.spd", os.path.basename(ap), re.I))


# =====================================================================================================================
# РАСХОЖДЕНИЯ «сервер знает — клиент нет» и наоборот (разбор §3.7)
# =====================================================================================================================
def divergence(ev, cli, sec):
    st = ev.st
    sell = st.get("GameServer", "SellItemTable.txt")
    sellset = set(sell.codes)
    shown = set(cli.p6000) | set(cli.tail) | cli.b15300
    _name, _int, _f, ITEM_FIRST = E._name, E._int, E._f, E.ITEM_FIRST
    # 1. карточка без белого списка / цена
    no_sell, price_bad = [], []
    for code in sorted(shown):
        mp = ev.pmap.get(code)
        if code >= ITEM_FIRST or code in ev.fn:
            if code not in sellset:
                no_sell.append({"code": code, "name": _name(code), "why": "нет в SellItemTable GameServer"})
        if code >= ITEM_FIRST:
            f = ev.it_fields(code)
            cp = cli.price(code)
            sp = int(mp["price"]) if mp and "price" in mp else (_int(f[26]) if f else None)
            if cp is not None and sp is not None and cp != sp:
                price_bad.append({"code": code, "name": _name(code), "client": cp, "server": sp,
                                  "why": "карта шлюза" if mp else "item_table ток.26"})
    sec("card_no_sell", "карточка на витрине, а сервер не продаёт", no_sell, "покупка: 5071 код 14 без списания")
    sec("price", "цена клиента ≠ цене сервера (витрины 6000/15300)", price_bad)
    # 2. сервер продаёт, карточки нет
    nocard = [{"code": c, "name": _name(c)} for c in sorted(sellset) if c not in shown and c >= ITEM_FIRST]
    sec("sell_no_card", "в SellItemTable, но не на витринах 6000/15300", nocard,
        "не ошибка сама по себе: часть кодов — коробки подарков и коды выдачи карты шлюза")
    # 3. лавки NPC
    npc_bad = []
    for npc, v in sorted(cli.npc.items()):
        for code in v.get("shown") or []:
            why = npc_rules(ev, code)
            sp = _int(ev.it_fields(code)[26]) if code >= ITEM_FIRST and ev.it_fields(code) else None
            cp = cli.price(code)
            if why:
                npc_bad.append({"npc": npc, "code": code, "name": _name(code), "why": why})
            elif sp is not None and cp is not None and sp != cp:
                npc_bad.append({"npc": npc, "code": code, "name": _name(code), "why": "цена клиент %d ≠ сервер %d" % (cp, sp)})
            if cli.on_premium(code):
                npc_bad.append({"npc": npc, "code": code, "name": _name(code), "why": "код и на премиум-витрине (общая цена)"})
    sec("npc", "лавки NPC: витрина против правил сервера", npc_bad)
    # 4. состав коробок и бустеров
    pk = st.get("GameServer", "PackageItem_Table.txt")
    pkg_bad = []
    for row, i in sorted(pk.index().items()):
        f = _f(pk.lines[i])
        srv = [[_int(f[1 + 2 * k]), _int(f[2 + 2 * k])] for k in range(5) if len(f) > 2 + 2 * k]
        cl = cli.pkg.get(row)
        if cl is None:
            pkg_bad.append({"row": row, "why": "строки нет у клиента"})
        else:
            a = [x for x in srv if x[0] > 0]
            b = [x for x in cl[:5] if x[0] > 0]
            if a != b:
                pkg_bad.append({"row": row, "why": "сервер %s ≠ клиент %s" % (a, b)})
    sec("package", "состав пакета: сервер ≠ клиент (packagetable)", pkg_bad)
    gr = st.get("GameServer", "GachaItemRateTable.txt")
    b_bad = []
    for row in range(1, min(_int(gr.lines[0].decode("latin-1")), len(gr.lines) - 1) + 1):
        f = _f(gr.lines[row])
        srv = [[_int(f[1 + 2 * j]), _int(f[2 + 2 * j])] for j in range(35)]
        cl = cli.booster.get(row)
        if cl is None:
            b_bad.append({"row": row, "why": "строки нет у клиента"})
        elif [c for c, _ in srv] != [c for c, _ in cl]:
            b_bad.append({"row": row, "why": "коды «Вида» клиента ≠ серверу"})
        elif srv != cl:
            b_bad.append({"row": row, "why": "веса клиента ≠ серверу (клиент веса не читает — только сведения)"})
    sec("booster", "бустер: сервер ≠ клиент (booster_list)", b_bad)
    # 5. гача
    gp = st.get("GameServer", "PrimiumGaChaTable.txt")
    pr = st.get("GameServer", "PrimiumGaChaPriceTable.txt")
    g_bad = []
    for s, i in sorted(pr.index().items()):
        sp = _int(_f(pr.lines[i])[1])
        cp = cli.gatya_price.get(s)
        if cp != sp:
            g_bad.append({"slot": s, "why": "цена клиент %s ≠ сервер %d" % (cp, sp)})
        pool = {c for c, _ in gp.slot_rows(s)}
        view = sorted({r[2] for r in cli.gatya if r[3] == s})
        miss = [c for c in view if c not in pool]
        if miss:
            g_bad.append({"slot": s, "why": "витрина (ViewSlot) показывает %d кодов не из пула: %s" % (len(miss), miss[:8])})
    sec("gacha", "гача: витрина и цена автомата против сервера", g_bad)


# =====================================================================================================================
# СТЕНД ШЛЮЗА: gift_check.py (настоящий server.js шлюза + правила GS) на итоговых таблицах — до и после набора (ПК)
# =====================================================================================================================
def gateway_stand(ev):
    """→ (ok, [строки итога]). Запускает Reports/premium_circle_bike/gift_check.py ПРОЦЕССОМ (у него побочные эффекты при
    импорте) во временной папке с его раскладкой: live/ (карта шлюза и Function_Table стойки), витрина клиента, server.js."""
    import shutil
    import tempfile
    if config.get().on_server or not os.path.isfile(E.GIFT_CHECK) or not os.path.isfile(E.GW_SERVER_JS):
        return None, ["стенд шлюза — только на ПК (нужны port и node)"]
    res = {}
    for label, new in (("до", False), ("после", True)):
        d = tempfile.mkdtemp(prefix="asda_cs_gw_")
        try:
            cwd = os.path.join(d, "a", "b")
            live = os.path.join(cwd, "live")
            tabs = os.path.join(d, "tables")
            for x in (live, tabs, os.path.join(d, "AsdaReborn", "RawAssets", "Data", "NPC"),
                      os.path.join(d, "Server", "Patches", "Gp7Gateway")):
                os.makedirs(x, exist_ok=True)
            open(os.path.join(live, "premium_item_map.json"), "w", encoding="utf-8").write(srvtables.stack_text(E.PREMIUM_MAP).lstrip("﻿"))
            open(os.path.join(live, "Function_Table.txt"), "wb").write(hostshell.read_server_bytes(
                config.STACK_ROOT + r"\GameServer\ItemTable_Info\Function_Table.txt", timeout=120))
            for name in ("item_table.txt", "SellItemTable.txt"):
                t = ev.st.get("GameServer", name)
                open(os.path.join(tabs, name), "wb").write(t.data() if new else ev.snap.raw("GameServer\\ItemTable_Info\\" + name))
            shop = json.load(open(E.CLIENT_FILES["premium6000"], encoding="utf-8"))
            if new:
                for e in ev.client:
                    if e["type"] == "tail6000_add":
                        shop.append(dict(e["row"], GiftCode=0))
            json.dump(shop, open(os.path.join(d, "AsdaReborn", "RawAssets", "Data", "NPC", "PremiumShopBin.json"), "w", encoding="utf-8"))
            shutil.copy2(os.path.join(E.NPC_DIR, "PremiumShopBin_card_qty.json"), os.path.join(d, "AsdaReborn", "RawAssets", "Data", "NPC"))
            shutil.copy2(E.GW_SERVER_JS, os.path.join(d, "Server", "Patches", "Gp7Gateway"))
            p = subprocess.run([sys.executable, E.GIFT_CHECK, tabs], cwd=cwd, capture_output=True, timeout=300,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            txt = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
            gs = re.search(r"правила GS: расхождений (\d+)", txt)
            gw = re.search(r"шлюз: карточек (\d+), расхождений (\d+)", txt)
            res[label] = (int(gs.group(1)) if gs else None, int(gw.group(2)) if gw else None, txt.strip().splitlines()[-6:])
        finally:
            shutil.rmtree(d, ignore_errors=True)
    a, b = res["до"], res["после"]
    lines = ["стенд шлюза: правила GS расхождений %s → %s; шлюз gp7 расхождений %s → %s" % (a[0], b[0], a[1], b[1])]
    if None in (a[0], a[1], b[0], b[1]):
        return False, lines + ["стенд не дал итога: " + " | ".join(b[2])]
    ok = b[0] <= a[0] and b[1] <= a[1]
    if not ok:
        lines += b[2]
    return ok, lines
