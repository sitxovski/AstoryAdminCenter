# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/honorshop.py — область «Магазин чести 67200» (волна А4.1, 19.11.2026; разбор research_a4_data.md §1.8).

СЕРВЕР: ItemTable_Info\\HonorPrice_Table.txt во всех GS (загрузчик GameServer.c:68356: число строк, затем записи ПОТОКОМ слов
`fscanf %s`; номер строки = StorePos, обязан идти подряд +1, иначе «HonorPrice_Table.txt Sync Error» и GS не стартует; запись 31 б:
+0 StorePos, +4 код, +8 i16 флаг, +10/+11 типы цен, +12/+16 коды цен, +20/+24 значения цен, +28 категория, +29 «только победившая
армия», +30 город). ★ «HororPrice_Table.txt» — только текст строки ошибки, сервер его НЕ грузит — не трогаем. Формат файла P116:
TAB, пробел после кода товара и после цены колонки 0, CRLF. На dev 19.11 все три копии ED893DD2 (= клиенту, P116).
ПОКУПКА: CharRoseWarStoreBuy@0x514FE0 — StorePos < числа строк («Wrong TableIndex»), код строки = коду из пакета клиента («Wrong
ItemIndex»), тип цены 1 = предмет (код +12, количество +20 — «Монеты славы» 20628), тип 2 = звание (+24 — требуемое воинское звание),
+29 и +30 — армия и город. → ПАРА СТРОГО ПО ПОЗИЦИИ: правка только на месте (решение владельца 19.11: без новых записей).
КЛИЕНТ: Data/Honor_price_table.bin клиента-донора _MINE (HonorPriceTable_Load@0xB76BB0: 20 б шапки, записи 12 × i32 по 48 б:
+4 код, +28 PriceQty0, +32 PriceQty1) → asda_import_war_shop.py → DT_WarShopList (и DT_WarRank из CampWar_HonorTable.BIN — тот же
импортёр, сторож ручной правки обоих DT). Звание — номер записи CampWar_HonorTable.BIN (шапка +4 = число званий).
Правка применяется к КАЖДОЙ копии сервера по её базе (политика per_copy; Ch2 = поле): если у Indun строка другая — отказ, а не
затирание.
Побочных эффектов при импорте нет.
"""
import os
import struct

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "honorshop", "Магазин чести 67200"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
TABLE = "HonorPrice_Table.txt"
SRV_FILES = [("GS", "ItemTable_Info\\" + TABLE, "per_copy")]
HDR, REC = 20, 48                     # Honor_price_table.bin
FIELDS = ("StorePos", "ItemCode", "Flag8", "PriceType0", "PriceType1", "PriceCode0", "PriceCode1", "PriceQty0", "PriceQty1",
          "Category", "VictorOnly", "RegionFilter")


def _data(name):
    try:
        return os.path.join(E.data_dir(), name)
    except ImportError:                 # служба на сервере: исходников порта нет — работает по снимку
        return os.path.join(E.UPROJ, "_no_asda_paths", name)


CLIENT_FILES = {"honor_bin": _data("Honor_price_table.bin"), "honor_rank": _data("CampWar_HonorTable.BIN")}
IMPORTERS = {"honor": ("asda_import_war_shop.py", "/Game/AsdaAssets/Data/Character/DT_WarShopList")}
KINDS = {
    "honor.price": ("Магазин чести: цена строки (монеты славы, звание)", ("pos", "coins", "rank"), False),
    "honor.item": ("Магазин чести: товар строки (замена на месте)", ("pos", "code"), False),
}


def parse_bin(raw):
    """Honor_price_table.bin → [12 × int] или None (шапка «HPT», размер = 20 + 48·N)."""
    if not raw or len(raw) < HDR or raw[12:15] != b"HPT":
        return None
    n = struct.unpack_from("<i", raw, 4)[0]
    if n < 0 or HDR + REC * n != len(raw):
        return None
    return [list(struct.unpack_from("<12i", raw, HDR + REC * i)) for i in range(n)]


def rank_count(raw):
    if not raw or len(raw) < HDR or raw[12:15] != b"HRT":
        return None
    return struct.unpack_from("<i", raw, 4)[0]


def norm(kind, p):
    if kind == "honor.price":
        return {"pos": E._ival(p, "pos", 0, 32767), "coins": E._ival(p, "coins", 0, 2000000000), "rank": E._ival(p, "rank", 0, 255)}
    return {"pos": E._ival(p, "pos", 0, 32767), "code": E._ival(p, "code", 1, 100000)}


def target_key(kind, p):
    return "honor:%d:%s" % (p["pos"], "price" if kind == "honor.price" else "item")


def _rows(ev, pos, rep):
    """Строка pos во всех копиях: [(копия, таблица, номер строки, поля)] + проверка пары по позиции с клиентом."""
    crow = ev.cli.honor[pos] if ev.cli.honor and pos < len(ev.cli.honor) else None
    if crow is None:
        raise OpRefused("строки %d витрины магазина чести у клиента нет (Honor_price_table.bin) — в А4 только правка существующих" % pos)
    out = []
    for g in E.GS:
        t = ev.st.get(g, TABLE)
        n = E._int(t.lines[0].decode("latin-1"))
        i = E.record_line(t, pos, 12)          # ★ ревизия 33 К-4: по порядку записи, как сервер (StorePos = номер записи)
        if i is None:
            raise OpRefused("%s %s: слова не ложатся построчно по 12 на запись — порядок записей сервера не доказан, правка не делается"
                            % (TABLE, g))
        if i < 0:
            raise OpRefused("строки %d в %s %s нет (строк %d) — в А4 только правка существующих" % (pos, TABLE, g, n))
        f = t.lines[i].split(b"\t")
        if len(f) < 12:
            raise OpRefused("строка %d %s %s — меньше 12 полей" % (pos, TABLE, g))
        if E._int(f[0].decode("latin-1")) != pos:
            rep["warnings"].append("%s: у записи %d номер %s — сервер берёт ПОРЯДОК записи" % (g, pos, f[0].decode("latin-1").strip()))
        # ★ ревизия 33 М-6: валюта колонки 0 — путь CharRoseWarStoreBuyItem (GameServer.c:105780…): код item_table (иначе ветки
        #   Function/Cellob — не разобраны), стопка (+7 = 4, +36 = 1); при +26 = 10 количество сервер берёт из item_table +47, а не
        #   из строки — такую цену этим путём не править
        cur = E._int(f[5].decode("latin-1"))
        cf = ev.it_fields(cur, g) if cur >= E.ITEM_FIRST else None
        if not cf:
            raise OpRefused("строка %d %s: валюта %d — не код item_table; путь цены сервера для неё не подтверждён" % (pos, g, cur))
        if E._int(cf[16]) == 10:
            raise OpRefused("строка %d %s: у валюты %d item_table +26 = 10 — количество сервер берёт из item_table +47, а не из строки; "
                            "правка цены строки не подействует" % (pos, g, cur))
        if cf[3] != "4" or cf[24] != "1":
            raise OpRefused("строка %d %s: валюта %d не стопочная (+7 = %s, +36 = %s) — путь цены сервера не подтверждён"
                            % (pos, g, cur, cf[3], cf[24]))
        code = E._int(f[1].decode("latin-1"))
        if code != crow[1]:
            raise OpRefused("строка %d: у %s товар %d, у клиента %d — пара по позиции разошлась (Wrong ItemIndex); сначала сверка"
                            % (pos, g, code, crow[1]))
        if E._int(f[3].decode("latin-1")) != 1 or E._int(f[4].decode("latin-1")) != 2:
            raise OpRefused("строка %d %s: типы цен %s/%s, а подтверждены разбором только 1 (предмет) и 2 (звание)"
                            % (pos, g, f[3].decode("latin-1").strip(), f[4].decode("latin-1").strip()))
        out.append((g, t, i, f))
    return crow, out


def k_honor_price(ev, p, rep):
    pos, coins, rank = p["pos"], p["coins"], p["rank"]
    crow, rows = _rows(ev, pos, rep)
    rc = ev.cli.honor_ranks
    if rc is None:
        rep["warnings"].append("число воинских званий клиента (CampWar_HonorTable.BIN) не прочитано — звание не сверено")
    elif rank >= rc:
        raise OpRefused("звания %d нет: в CampWar_HonorTable.BIN клиента званий %d" % (rank, rc))
    olds = set()
    for g, t, i, f in rows:
        olds.add((E._int(f[7].decode("latin-1")), E._int(f[8].decode("latin-1"))))
        f = list(f)
        f[7], f[8] = E.set_token(f[7], coins), E.set_token(f[8], rank)
        t.set_line(i, b"\t".join(f))
    old = sorted(olds)[0]
    if len(olds) > 1:
        rep["warnings"].append("цена строки %d на копиях разная: %s — правка ложится на каждую копию" % (pos, sorted(olds)))
    if (crow[7], crow[8]) != old:
        rep["warnings"].append("цены уже расходились: клиент %d монет / звание %d, сервер %d / %d" % (crow[7], crow[8], old[0], old[1]))
    if (coins, rank) == old and (crow[7], crow[8]) == old:
        raise OpRefused("строка %d: уже %d монет, звание %d — менять нечего" % (pos, coins, rank))
    rep["text"] = "магазин чести, строка %d (%s): %d монет, звание %d → %d монет, звание %d" % (
        pos, E.nm(crow[1]), old[0], old[1], coins, rank)
    rep["_codes"] = [crow[1]]
    rep["_balance"] = [{"what": "магазин чести, строка %d: монеты славы" % pos, "old": old[0], "new": coins, "codes": [crow[1]]},
                       {"what": "магазин чести, строка %d: требуемое звание" % pos, "old": old[1], "new": rank, "codes": [crow[1]]}]
    rep["client"] = [{"type": "honor_set", "file": "honor_bin", "pos": pos,
                      "fields": {"PriceQty0": [crow[7], coins], "PriceQty1": [crow[8], rank]}}]
    ev.client += rep["client"]


def k_honor_item(ev, p, rep):
    pos, code = p["pos"], p["code"]
    crow, rows = _rows(ev, pos, rep)
    if code < E.ITEM_FIRST:
        raise OpRefused("в магазин чести — только коды item_list (≥ 20551): выдача спецпредметов этим путём разбором не подтверждена")
    if code == crow[1]:
        raise OpRefused("в строке %d уже %d — менять нечего" % (pos, code))
    if not ev.exists(code):
        raise OpRefused("кода %d нет на сервере" % code)
    if code not in ev.cli.items:
        raise OpRefused("кода %d нет в item_list клиента — карточки нет" % code)
    for g, t, i, f in rows:
        f = list(f)
        f[1] = E.set_token(f[1], code)
        t.set_line(i, b"\t".join(f))
    rep["text"] = "магазин чести, строка %d: товар %s → %s" % (pos, E.nm(crow[1]), E.nm(code))
    rep["_codes"] = [crow[1], code]
    rep["_balance"] = [{"what": "магазин чести, строка %d: товар %d → %d" % (pos, crow[1], code), "old": crow[1], "new": code,
                        "codes": [crow[1], code], "kind": "swap"}]
    rep["client"] = [{"type": "honor_set", "file": "honor_bin", "pos": pos, "fields": {"ItemCode": [crow[1], code]}}]
    ev.client += rep["client"]


def snapshot(snap):
    p, r = E.CLIENT_FILES["honor_bin"], E.CLIENT_FILES["honor_rank"]
    snap["honor"] = parse_bin(open(p, "rb").read()) if os.path.isfile(p) else None
    snap["honor_ranks"] = rank_count(open(r, "rb").read()) if os.path.isfile(r) else None


def parse(cli, d):
    cli.honor = d.get("honor")
    cli.honor_ranks = d.get("honor_ranks")


def plan(pc):
    for e in pc["by_file"].get("honor_bin", []):
        cur = pc["load"]("honor_bin", E.CLIENT_FILES["honor_bin"])
        rows = parse_bin(cur[1])
        if rows is None or e["pos"] >= len(rows):
            pc["errors"].append("Honor_price_table.bin: строки %d нет или файл не бьётся с шапкой" % e["pos"])
            continue
        b = bytearray(cur[1])
        bad = []
        for name, (o, n) in e["fields"].items():
            off = HDR + REC * e["pos"] + 4 * FIELDS.index(name)
            if struct.unpack_from("<i", b, off)[0] != int(o):
                bad.append(name)
            else:
                struct.pack_into("<i", b, off, int(n))
        if bad:
            pc["errors"].append("Honor_price_table.bin строка %d: %s изменились с проверки — пересоберите набор" % (e["pos"], ", ".join(bad)))
            continue
        cur[1] = bytes(b)
        pc["importers"].add("honor")


def divergence(ev, cli, sec):
    t = ev.st.get("GameServer", TABLE)
    n = E._int(t.lines[0].decode("latin-1"))
    rows = []
    if cli.honor is None:
        sec("honor", "магазин чести: сервер ≠ клиент (строка = StorePos)", [], "Honor_price_table.bin не прочитан")
        return
    if n != len(cli.honor):
        rows.append({"pos": "—", "why": "строк: сервер %d, клиент %d" % (n, len(cli.honor))})
    for pos, i in sorted(t.index().items()):
        f = [E._int(x) for x in E._f(t.lines[i])[:12]]
        c = cli.honor[pos] if pos < len(cli.honor) else None
        if c is None:
            rows.append({"pos": pos, "why": "строки нет у клиента"})
        elif f[:9] != c[:9] or f[10:12] != c[10:12]:
            diff = [FIELDS[k] for k in range(12) if k != 9 and k < len(f) and f[k] != c[k]]
            rows.append({"pos": pos, "code": c[1], "name": E._name(c[1]), "why": "различаются: %s" % ", ".join(diff)})
    for g in E.GS[1:]:
        if ev.snap.md5.get(E.rel_of(g, TABLE)) != ev.snap.md5.get(E.rel_of("GameServer", TABLE)):
            rows.append({"pos": "—", "why": "%s: %s ≠ GameServer (своя база копии)" % (g, TABLE)})
    sec("honor", "магазин чести: сервер ≠ клиент (строка = StorePos)", rows, "категория (+28) сервером не читается — не сравнивается")
