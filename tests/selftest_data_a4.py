# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_data_a4.py — самотест волны А4.0/А4.1 «Данные игры» (19.11.2026): реестр видов, политики копий (Indun — своя база),
ведомости ItemDB, баланс с двойным подтверждением, занятость по путям (NpcServer.exe, файлы), витрина 6800, магазин чести,
парикмахерская. Офлайн — подменная стойка selftest_shops.synthetic() и песочница selftest_shops_sandbox.sandbox() (копии файлов
GS, клиентских таблиц и ведомостей, НАСТОЯЩИЕ deploy_premium_boxes/deploy_changeset в процессе, подставной restart_stack, LocalDB).
Живое — только чтение и сухие прогоны (стойка и порт не меняются). Побочных эффектов при импорте нет.
"""
import hashlib
import json
import os
import shutil
import struct
import tempfile

BS = "\\"
GS3 = ("GameServer", "Indun_GameServer", "Ch2_GameServer")


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _crlf(rows):
    return ("\r\n".join(rows) + "\r\n").encode("latin-1")


def _honor_txt(code1=30002):
    return _crlf(["2", "0\t30001 \t0\t1\t2\t30000\t-1\t28 \t2\t0\t0\t-1", "1\t%d \t0\t1\t2\t30000\t-1\t32 \t2\t0\t0\t-1" % code1])


def _hair_txt(p1=19):
    return _crlf(["2", "0\tkor\t1\t0\t1\t19\t0\t0", "1\tkor2\t1\t0\t1\t%d\t0\t1" % p1])


def _a4_tables():
    """Таблицы А4 трёх GS: у Indun — своя база (магазин чести: строка 1 другая; причёска 1 — другая цена)."""
    out = {}
    for g in GS3:
        out[g + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt"] = _honor_txt(30005 if g == "Indun_GameServer" else 30002)
        out[g + BS + "ItemTable_Info" + BS + "HairTypeTable.txt"] = _hair_txt(29 if g == "Indun_GameServer" else 19)
    return out


HONOR_ROWS = [[0, 30001, 0, 1, 2, 30000, -1, 28, 2, 0, 0, -1], [1, 30002, 0, 1, 2, 30000, -1, 32, 2, 0, 0, -1]]   # валюта — стопка 30000
SHE_LISTS = [[], [], [], [], [30000, 30006], [30007], [], [], [], [], []]


def _hex(price, off=0x28, n=120):
    b = bytearray(n)
    struct.pack_into("<i", b, off, price)
    return bytes(b).hex()


def _client_files(d):
    """Временные клиентские файлы А4: Freeshop.she, Honor_price_table.bin, CampWar_HonorTable.BIN, hairtable.csv."""
    she = struct.pack("<11H", *[len(x) for x in SHE_LISTS]) + b"".join(struct.pack("<%di" % len(x), *x) for x in SHE_LISTS if x)
    hb = struct.pack("<iiI4sI", 0, len(HONOR_ROWS), 12, b"HPT\0", 0) + b"".join(struct.pack("<12i", *r) for r in HONOR_ROWS)
    rk = struct.pack("<fiI4sI", 100.0, 21, 0, b"HRT\0", 0) + b"\0" * 56 * 21
    hc = "_row,Id,Name,Price,DataHex\r\n0,0,Короткая,19,%s\r\n1,1,Длинная,19,%s\r\n" % (_hex(19), _hex(19))
    files = {"equipshop": ("Freeshop.she", she), "honor_bin": ("Honor_price_table.bin", hb), "honor_rank": ("CampWar_HonorTable.BIN", rk),
             "hairtable": ("hairtable.csv", hc.encode("utf-8"))}
    out = {}
    for k, (fn, b) in files.items():
        p = os.path.join(d, fn)
        open(p, "wb").write(b)
        out[k] = p
    return out


def _set_cli(cli):
    cli.equip = [list(x) for x in SHE_LISTS]
    cli.honor = [list(r) for r in HONOR_ROWS]
    cli.honor_ranks = 21
    cli.hair = {0: [0, 19, 19], 1: [1, 19, 19]}


def _ev(items, urgent=False):
    from domains import shopdata as SD
    return SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], urgent).run()


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check, ldb=None):
    import selftest_shops as T
    from core import config
    from domains import shopdata as SD
    # ★ А4.2: + область «texts» (вид text.set); ★ А4.3: + «monsters» (6 видов); ★ А4.4: + «itemdata» (2 вида) — ожидание дополнено
    # ★ А4.5: + «quests» (2 вида)
    # ★ А4.6: + «titledata» (4 вида)
    # ★ А4.7: + «skilldata» (5 видов)
    # ★ А4.8: + «mapdata» (2 вида)
    # ★ А5.4: + «events» (счастливые часы, 2 вида)
    check("А4.0 реестр видов: 13 областей (магазины, 6800, честь, причёски, тексты, монстры, предметы, задания, звания, навыки и классы, карты, "
          "счастливые часы, настройки патчей), 40 видов, у областей А4 права data.edit / data.apply",
          [a.AREA for a in SD.AREAS] == ["shops", "equipshop", "honorshop", "hairshop", "texts", "monsters", "itemdata", "quests",
                                            "titledata", "skilldata", "mapdata", "events", "patchcfg"]   # ★ А5.5: + «Настройки патчей» (2 вида)
          and len(SD.KINDS) == 40
          and SD.area_perm("hair.price", "apply") == "data.apply" and SD.area_perm("price", "edit") == "shop.edit"
          and SD.SRV_POLICY["ItemTable_Info\\HonorPrice_Table.txt"] == "per_copy" and len(SD.srv_rels()) == 18)
    check("баланс: «больше чем в 2 раза» в обе стороны, из нуля и в ноль — сильная; ровно ×2 — нет",
          SD.is_strong(10, 21) and SD.is_strong(10, 4) and SD.is_strong(0, 1) and SD.is_strong(5, 0) and not SD.is_strong(10, 20)
          and not SD.is_strong(10, 5) and not SD.is_strong(7, 7))
    with T.synthetic() as (raw, md5, cli):
        for rel, b in _a4_tables().items():
            raw[rel], md5[rel] = b, _md5(b)
        _set_cli(cli)
        # витрина 6800
        e = _ev([("equipshop.set", {"list": 4, "index": 1, "code": 30007})])
        s = e.summary()
        bad = [x for x in ({"list": 4, "index": 5, "code": 30007}, {"list": 4, "index": 0, "code": 30004},
                           {"list": 4, "index": 0, "code": 30001}, {"list": 4, "index": 0, "code": 500}, {"list": 4, "index": 0, "code": 30000})
               if not _ev([("equipshop.set", x)]).errors]
        check("6800: замена кода на месте — только клиент (she_set), без серверной половины; отказы: места нет, ShopBuyFlag 0, премиум-витрина "
              "(п.4), спецпредмет, тот же код", not e.errors and s["server"]["count"] == 0 and [x["type"] for x in s["client"]] == ["she_set"]
              and not bad, (e.errors, bad))
        # магазин чести: правка по базе каждой копии, отличия Indun сохраняются
        h = _ev([("honor.price", {"pos": 0, "coins": 30, "rank": 3})])
        nb = h.new_bytes()
        ind = nb.get("Indun_GameServer" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt", b"")
        fld = nb.get("GameServer" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt", b"")
        check("магазин чести: строка 0 правится во всех GS по базе каждой (у Indun своя строка 1 — 30005 — сохранена), формат P116 "
              "(пробел после кода и цены), Ch2 = поле", not h.errors and len(nb) == 3 and b"1\t30005 \t" in ind and b"1\t30002 \t" in fld
              and b"0\t30001 \t0\t1\t2\t30000\t-1\t30 \t3\t" in ind and nb["Ch2_GameServer" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt"] == fld
              and {f["table"] for f in h.summary()["server"]["files"]} == {"HonorPrice_Table.txt"}, h.errors)
        h1 = _ev([("honor.price", {"pos": 1, "coins": 30, "rank": 2})])
        h2 = _ev([("honor.price", {"pos": 0, "coins": 30, "rank": 25})])
        h3 = _ev([("honor.price", {"pos": 9, "coins": 30, "rank": 2})])
        check("магазин чести: у Indun в строке другой товар — отказ «пара по позиции разошлась»; звания нет — отказ; строки нет — отказ "
              "(в А4 только правка существующих)", any("разошлась" in x for x in h1.errors) and any("звания 25" in x for x in h2.errors)
              and any("только правка существующих" in x for x in h3.errors), (h1.errors, h2.errors, h3.errors))
        hb = _ev([("honor.price", {"pos": 0, "coins": 60, "rank": 2})]).summary()
        hi = _ev([("honor.item", {"pos": 0, "code": 30007})]).summary()
        check("баланс А4: монеты 28 → 60 (> ×2) и замена товара — сильная правка с гейтом (balance_strong)",
              hb["balance_strong"] and hi["balance_strong"] and any(b["kind"] == "swap" for b in hi["balance"]), (hb["balance"], hi["balance"]))
        # парикмахерская
        p = _ev([("hair.price", {"id": 0, "value": 25})])
        pb = p.new_bytes()
        pi = pb.get("Indun_GameServer" + BS + "ItemTable_Info" + BS + "HairTypeTable.txt", b"")
        check("парикмахерская: цена причёски — 3 GS (у Indun своя цена причёски 1 = 29 сохранена), клиент Price + DataHex +0x28, не сильная",
              not p.errors and len(pb) == 3 and b"0\tkor\t1\t0\t1\t25\t0\t0" in pi and b"1\tkor2\t1\t0\t1\t29\t" in pi
              and [x["type"] for x in p.client] == ["csv_cell", "csv_hex_i32"] and not p.summary()["balance_strong"], p.errors)
        check("парикмахерская: 19 → 100 — сильная правка; причёски нет — отказ",
              _ev([("hair.price", {"id": 0, "value": 100})]).summary()["balance_strong"]
              and _ev([("hair.price", {"id": 7, "value": 1})]).errors)
        shop = _ev([("price", {"code": 30001, "value": 5000})]).summary()
        check("ревизия 33 В-2: магазины А3 — цена 500 → 5000 — сильная правка С гейтом (двойное подтверждение и для А3)",
              any(b["strong"] and b["gate"] for b in shop["balance"]) and shop["balance_strong"], shop["balance"])
        eqs = _ev([("equipshop.set", {"list": 4, "index": 1, "code": 30007})]).summary()
        check("ревизия 33 М-4: замена товара витрины 6800 — правка баланса (swap, с гейтом)",
              eqs["balance_strong"] and any(b["kind"] == "swap" for b in eqs["balance"]), eqs["balance"])
        check("ревизия 33 М-2: «на руках» — нестопочные числом экземпляров, стопки — суммой Amount с подписью",
              SD.held_text({30001: {"rows": 44, "amount": 6209118543, "stack": False}}) == "30001: 44 экз."
              and SD.held_text({30000: {"rows": 3, "amount": 120, "stack": True}}) == "30000: 120 шт. в 3 стопках"
              and SD.stack_flags(_ev([]), [30000, 30001]) == {30000: True, 30001: False})
        # ★ ревизия 33 М-6: валюта магазина чести — путь цены сервера
        it = "%s" + BS + "ItemTable_Info" + BS + "item_table.txt"
        keep_it = {g: raw[it % g] for g in GS3}
        hon = "%s" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt"
        keep_h = {g: raw[hon % g] for g in GS3}
        try:
            for g in GS3:
                raw[it % g] = keep_it[g].replace(b"\r\n", b"\r\n", 0) + (T._itrow(30008, 10, t16=10) + "\r\n").encode("latin-1")
                raw[it % g] = raw[it % g].replace(str(len(T.ITEMS)).encode() + b"\r\n", str(len(T.ITEMS) + 1).encode() + b"\r\n", 1)
                md5[it % g] = _md5(raw[it % g])
            res = {}
            for cur in (30008, 30005, 500):
                for g in GS3:
                    raw[hon % g] = keep_h[g].replace(b"\t30000\t", ("\t%d\t" % cur).encode())
                    md5[hon % g] = _md5(raw[hon % g])
                res[cur] = _ev([("honor.price", {"pos": 0, "coins": 30, "rank": 2})]).errors
        finally:
            for g in GS3:
                raw[it % g], md5[it % g] = keep_it[g], _md5(keep_it[g])
                raw[hon % g], md5[hon % g] = keep_h[g], _md5(keep_h[g])
        check("ревизия 33 М-6: магазин чести — валюта с item_table +26 = 10 (количество из +47), не стопочная, не код item_table — отказ",
              any("+47" in x for x in res[30008]) and any("не стопочная" in x for x in res[30005]) and any("не код item_table" in x for x in res[500]),
              res)
        # ★ ревизия 33 К-4: строка — по порядку записи; файл не построчный — отказ
        hk = "%s" + BS + "ItemTable_Info" + BS + "HairTypeTable.txt"
        keep_hk = {g: raw[hk % g] for g in GS3}
        try:
            for g in GS3:
                raw[hk % g] = keep_hk[g].replace(b"0\tkor\t", b"0\tkor x\t")
                md5[hk % g] = _md5(raw[hk % g])
            nl = _ev([("hair.price", {"id": 0, "value": 25})]).errors
        finally:
            for g in GS3:
                raw[hk % g], md5[hk % g] = keep_hk[g], _md5(keep_hk[g])
        check("ревизия 33 К-4: запись ищется по порядку, как сервер; слова не ложатся построчно (имя из двух слов) — отказ",
              any("построчно" in x for x in nl), nl)
        ch2 = "Ch2_GameServer" + BS + "ItemTable_Info" + BS + "HairTypeTable.txt"
        keep = raw[ch2]
        raw[ch2] = _hair_txt(55)
        md5[ch2] = _md5(raw[ch2])
        par = _ev([("hair.price", {"id": 0, "value": 25})])
        raw[ch2], md5[ch2] = keep, _md5(keep)
        check("per_copy: база Ch2 ≠ поля — отказ «паритет Ch2» (Indun может отличаться, Ch2 — нет)", any("паритет Ch2" in x for x in par.errors),
              par.errors)
        _plan_checks(check, cli)


def _plan_checks(check, cli):
    """План клиента А4 и ведомости ItemDB на временных копиях (ничего не пишет)."""
    import selftest_shops as T
    from core import config
    from domains import shopdata as SD
    d = tempfile.mkdtemp(prefix="asda_cs_a4_")
    saved = dict(SD.CLIENT_FILES)
    cfg = config.get()
    was = cfg.on_server
    cfg.on_server = False
    try:
        SD.CLIENT_FILES.update(_client_files(d))
        before = {p: _md5(open(p, "rb").read()) for p in SD.CLIENT_FILES.values() if p.startswith(d)}
        ev = _ev([("equipshop.set", {"list": 4, "index": 1, "code": 30007}), ("honor.price", {"pos": 0, "coins": 30, "rank": 3}),
                  ("hair.price", {"id": 0, "value": 25})])
        plan = SD.client_plan(ev.client, 88)
        b = plan["_bytes"]
        she = b[SD.CLIENT_FILES["equipshop"]]
        hb = b[SD.CLIENT_FILES["honor_bin"]]
        hc = b[SD.CLIENT_FILES["hairtable"]].decode("utf-8")
        vo = SD.ledger_paths("hairtable")[0]
        led = b.get(vo, b"").decode("utf-8")
        row0 = hc.split("\r\n")[1].split(",")
        check("план клиента А4: .she — код на месте (страница/слот не сдвинуты), Honor_price_table.bin — монеты и звание строки 0, "
              "hairtable — Price и DataHex +0x28; импортёры 6800 и чести; DT_hairtable", not plan["errors"]
              and struct.unpack_from("<i", she, 22 + 4 * 1)[0] == 30007 and len(she) == len(open(SD.CLIENT_FILES["equipshop"], "rb").read())
              and struct.unpack_from("<i", hb, 20 + 28)[0] == 30 and struct.unpack_from("<i", hb, 20 + 32)[0] == 3
              and row0[3] == "25" and struct.unpack_from("<i", bytes.fromhex(row0[4]), 0x28)[0] == 25
              and plan["importers"] == ["equipshop", "honor"] and [j["dt"].rsplit("/", 1)[1] for j in plan["dt_jobs"]] == ["DT_hairtable"],
              plan["errors"])
        check("ведомость ItemDB: правка hairtable → строка _value_overlay/hairtable.csv «0,Price,19,25» (перегенерация её не сотрёт); "
              "план сухой — файлы не изменились", "0,Price,19,25," in led and led.startswith("row,column,was,now,source,reason")
              and before == {p: _md5(open(p, "rb").read()) for p in before}, led[:200])
        # хвост: строка из _tail_append правится в ведомости хвоста, а не _value_overlay
        il = os.path.join(d, "item_list.csv")
        open(il, "w", encoding="utf-8", newline="").write("_row,ItemCode,ItemName,Price,DataHex\r\n0,30001,x,500,%s\r\n1,30002,y,300,%s\r\n"
                                                         % (_hex(500, 0xA4, 248), _hex(300, 0xA4, 248)))
        SD.CLIENT_FILES["item_list"] = il
        ta = SD.ledger_paths("item_list")[1]
        open(ta, "w", encoding="utf-8", newline="").write("_row,ItemCode,ItemName,Price,DataHex,_source\r\n1,30002,y,300,%s,самотест\r\n"
                                                         % _hex(300, 0xA4, 248))
        pl = SD.client_plan(_ev([("price", {"code": 30002, "value": 310})]).client, 89)
        tl = pl["_bytes"].get(ta, b"").decode("utf-8")
        vol = pl["_bytes"].get(SD.ledger_paths("item_list")[0])
        check("ведомость ItemDB: строка из хвоста (_tail_append) — правится на месте (Price и DataHex), _value_overlay не пишется; "
              "перегенерация даёт план", not pl["errors"] and ",310," in tl and "самотест" in tl and vol is None, (pl["errors"], tl[:200]))
        os.remove(ta)
        # ★ ревизия 33 В-1: строка ХВОСТА booster_list (премиум-бустер) — DataHex пересобирается по раскладке, хвост не отвергается
        bl = os.path.join(d, "booster_list.csv")
        hx = lambda code, c0, w0: bytes(struct.pack("<iii", code, c0, w0) + bytes(16)).hex()
        open(bl, "w", encoding="utf-8", newline="").write("_row,Code,Slot00ItemCode,Slot00Weight,DataHex\r\n0,1,30000,100,%s\r\n1,4135,30005,50,%s\r\n"
                                                         % (hx(1, 30000, 100), hx(4135, 30005, 50)))
        SD.CLIENT_FILES["booster_list"] = bl
        tb = SD.ledger_paths("booster_list")[1]
        open(tb, "w", encoding="utf-8", newline="").write("_row,Code,Slot00ItemCode,Slot00Weight,DataHex,_source\r\n1,4135,30005,50,%s,премиум\r\n"
                                                         % hx(4135, 30005, 50))
        ed = lambda code, w0, w1: [{"type": "csv_cells", "file": "booster_list", "key_col": "Code", "key": str(code),
                                    "cells": {"Slot00Weight": [str(w0), str(w1)]}}]
        pt = SD.client_plan(ed(4135, 50, 60), 91)
        pa = SD.client_plan(ed(1, 100, 110), 92)
        tbn = pt["_bytes"].get(tb, b"").decode("utf-8")
        csv_t = pt["_bytes"][bl].decode("utf-8").split("\r\n")[2]
        csv_a = pa["_bytes"][bl].decode("utf-8").split("\r\n")[1]
        saved_cols = SD.itemdb_cols
        SD.itemdb_cols = lambda key: {}                    # без раскладки DataHex не пересобрать — хвост отвергся бы
        pbad = SD.client_plan(ed(4135, 50, 60), 93)
        SD.itemdb_cols = saved_cols
        check("ревизия 33 В-1: вес строки ХВОСТА booster_list (Code 4135) — DataHex ведомости хвоста и CSV пересобран, перегенерация "
              "согласна; строка архива (Code 1) — DataHex от генератора; без раскладки — отказ, а не тихая потеря хвоста",
              not pt["errors"] and hx(4135, 30005, 60) in tbn and csv_t.endswith(hx(4135, 30005, 60))
              and not pa["errors"] and csv_a.endswith(hx(1, 30000, 110)) and pbad["errors"], (pt["errors"], pa["errors"], pbad["errors"]))
        os.remove(tb)
        SD.itemdb_regen = T.fake_regen(archive={"hairtable": "_row,Id,Name,Price,DataHex\r\n0,0,Короткая,18,{0}\r\n1,1,Длинная,19,{1}\r\n".format(
            _hex(18), _hex(19)).encode("utf-8")})
        pd = SD.client_plan(_ev([("hair.price", {"id": 0, "value": 25})]).client, 90)
        check("ведомость ItemDB: CSV порта ≠ генератору (правили мимо ведомости) — отказ «разберите до правки»",
              any("мимо ведомости" in x for x in pd["errors"]), pd["errors"])
        SD.itemdb_regen = T.fake_regen()
    finally:
        cfg.on_server = was
        SD.CLIENT_FILES.clear()
        SD.CLIENT_FILES.update(saved)
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox_a4(check, ldb):
    """Путь набора А4 целиком в песочнице: копии GS (Indun — своя база), клиентские файлы А4 и ведомости ItemDB — во временной
    папке, настоящий deploy_changeset, подставной restart_stack; занятость по путям; баланс; порт сменился."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs, shopdata as SD
    if SD.SRV_TOOLS not in __import__("sys").path:
        __import__("sys").path.insert(0, SD.SRV_TOOLS)
    import deploy_premium_boxes as base
    import deploy_changeset as dc
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with X.sandbox(ldb) as (st, env):
        for rel, b in _a4_tables().items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        cdir = os.path.join(env["tmp"], "a4")
        os.makedirs(cdir)
        SD.CLIENT_FILES.update(_client_files(cdir))
        st.assets[SD.DT["hairtable"]] = open(SD.CLIENT_FILES["hairtable"], "rb").read()
        orig = {k: open(SD.CLIENT_FILES[k], "rb").read() for k in ("equipshop", "honor_bin", "hairtable")}
        items = [("equipshop.set", {"list": 4, "index": 1, "code": 30007}), ("honor.price", {"pos": 0, "coins": 30, "rank": 3}),
                 ("hair.price", {"id": 0, "value": 25})]
        cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4", note="самотест песочницы А4: путь применения и отката")["result"]["id"]
        for kind, prm in items:
            X._run(ctx, "shop.cs_item_add", cs=cid, kind=kind, params=prm)
        X._run(ctx, "shop.cs_check", cs=cid)
        adm = ops.Ctx(7, "adm", "admin", "100.64.0.9", "web")
        _r, adm_no = X._try(adm, "shop.cs_approve", cs=cid, balance_ok="balance")
        X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
        check("ревизия 33 М-1: второе подтверждение сильной правки (замена в 6800) — только владелец: admin с ключом — отказ",
              adm_no and "только владелец" in adm_no, adm_no)
        X._run(ctx, "shop.cs_server_dry", cs=cid)
        cs = shopcs.get(cid)
        man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
        ind = "Indun_GameServer" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt"
        check("песочница А4: набор (6800 + честь + причёски) проверен и утверждён, сухой прогон настоящего deploy_changeset — 6 файлов "
              "(у Indun своя база в манифесте)", cs["status"] == "approved" and cs["server_state"] == "dry_ok" and len(man["files"]) == 6
              and man["files"][ind]["base"] == _md5(_honor_txt(30005)), (cs["status"], cs["server_state"], sorted(man["files"])))
        st.held = {ind}
        rc_h, out_h = shopcs.run_deploy(shopcs.manifest_path(cid))
        st.held = set()
        check("ревизия 33 М-3: файл набора держит процесс — СТОП уже в сухом прогоне (до объявления и остановки)",
              rc_h == 2 and "файлы набора открыты процессом" in out_h and st.calls == [], (rc_h, out_h[-200:], st.calls))
        X._run(ctx, "shop.cs_client_dry", cs=cid)
        X._run(ctx, "shop.cs_client_apply", cs=cid)
        led = open(SD.ledger_paths("hairtable")[0], encoding="utf-8").read()
        she = open(SD.CLIENT_FILES["equipshop"], "rb").read()
        hbn = open(SD.CLIENT_FILES["honor_bin"], "rb").read()
        check("песочница А4: клиент — .she, Honor_price_table.bin, hairtable.csv + ведомость _value_overlay/hairtable.csv записаны, "
              "DT_hairtable залит, импортёры 6800 и чести запущены через очередь UE", shopcs.get(cid)["client_state"] == "applied"
              and "0,Price,19,25," in led and struct.unpack_from("<i", she, 22 + 4)[0] == 30007 and struct.unpack_from("<i", hbn, 48)[0] == 30
              and b",25," in st.assets[SD.DT["hairtable"]] and "asda_import_equip_shop.py" in st.imports and "asda_import_war_shop.py" in st.imports,
              (st.imports, led[:120]))
        r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
        got = open(st.path(ind), "rb").read()
        check("песочница А4: серверная половина выложена — у Indun строка 0 новая, своя строка 1 (30005) сохранена; поле = Ch2",
              r and shopcs.get(cid)["server_state"] == "applied" and b"1\t30005 \t" in got and b"\t30 \t3\t" in got
              and open(st.path("GameServer" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt"), "rb").read()
              == open(st.path("Ch2_GameServer" + BS + "ItemTable_Info" + BS + "HonorPrice_Table.txt"), "rb").read(), e)
        X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
        X._run(ctx, "shop.cs_client_rollback", cs=cid)
        back = all(open(SD.CLIENT_FILES[k], "rb").read() == orig[k] for k in orig)
        check("песочница А4: откат сервера и клиента — таблицы GS, .she, .bin, hairtable.csv и ведомость вернулись",
              back and not os.path.isfile(SD.ledger_paths("hairtable")[0]) and open(st.path(ind), "rb").read() == _honor_txt(30005),
              shopcs.get(cid)["client_state"])
        # баланс: сильная правка — утверждение без второго подтверждения отказывает, с ним — проходит
        c2 = X._run(ctx, "shop.cs_create", title="баланс", note="самотест А4: сильная правка баланса")["result"]["id"]
        X._run(ctx, "shop.cs_item_add", cs=c2, kind="hair.price", params={"id": 1, "value": 100})
        X._run(ctx, "shop.cs_check", cs=c2)
        _r, no2 = X._try(ctx, "shop.cs_approve", cs=c2)
        ok2, _e = X._try(ctx, "shop.cs_approve", cs=c2, balance_ok="balance")
        check("песочница А4: сильная правка (19 → 100) — утвердить без --balance-ok нельзя (текст: «на руках у игроков»), с ключом — утверждён",
              no2 and "второе подтверждение" in no2 and "на руках" in no2 and ok2 and shopcs.get(c2)["status"] == "approved", no2)
        # порт сменился между утверждением и сухим прогоном клиента
        p = SD.CLIENT_FILES["hairtable"]
        txt = open(p, "rb").read()
        open(p, "wb").write(txt.replace(b"1,1,\xd0\x94\xd0\xbb\xd0\xb8\xd0\xbd\xd0\xbd\xd0\xb0\xd1\x8f,19,", b"1,1,\xd0\x94\xd0\xbb\xd0\xb8\xd0\xbd\xd0\xbd\xd0\xb0\xd1\x8f,21,"))
        _r, ch = X._try(ctx, "shop.cs_client_dry", cs=c2)
        open(p, "wb").write(txt)
        X._run(ctx, "shop.cs_cancel", cs=c2)
        check("песочница А4: копия порта сменилась после утверждения — сухой прогон клиента отказывает «пересоберите»", ch and "пересоберите" in ch, ch)
        # занятость по путям: NpcServer.exe и сам файл (любой процесс)
        saved = (base.rbusy, set(dc.ALLOWED))
        st.held = set()
        base.rbusy = lambda pth: ("BUSY" if (pth.endswith("NpcServer.exe") and st.procs.get("NpcServer")) or
                                  (pth.endswith("GameServer.exe") and st.procs.get("GameServer")) or
                                  any(pth.endswith(h) for h in st.held) else "FREE")
        try:
            npc_rel = "NpcServer" + BS + "Monster" + BS + "Monster.ai"
            for f in ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer"):
                q = st.path(f + BS + "Monster" + BS + "Monster.ai")
                os.makedirs(os.path.dirname(q), exist_ok=True)
                open(q, "wb").write(b"\0" * 479)
                dc.ALLOWED.add(f + BS + "Monster" + BS + "Monster.ai")
            loc = os.path.join(env["tmp"], "npc_new.ai")
            open(loc, "wb").write(b"\1" * 479)
            mf = os.path.join(env["tmp"], "npc_manifest.json")
            json.dump({"tag": "20261119_a4npc", "files": {f + BS + "Monster" + BS + "Monster.ai": {"local": loc.replace(BS, "/"),
                       "base": _md5(b"\0" * 479), "new": _md5(b"\1" * 479)} for f in ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")}},
                      open(mf, "w", encoding="utf-8"))
            st.procs = {"NpcServer": 3}
            rc1, o1 = shopcs.run_deploy(mf, ["--apply"])
            st.procs = {}
            st.held = {"Indun_NpcServer" + BS + "Monster" + BS + "Monster.ai"}
            rc2, o2 = shopcs.run_deploy(mf, ["--apply"])
            st.held = set()
            json.dump({"tag": "x", "files": {"NpcServer" + BS + "Monster" + BS + "Monster.ai": {"local": loc, "base": "a", "new": "b"}}},
                      open(mf, "w", encoding="utf-8"))
            rc3, o3 = shopcs.run_deploy(mf)
            check("выкладчик: файлы NpcServer — NpcServer.exe работает → СТОП 2; файл держит любой процесс → СТОП 2; таблица не во всех "
                  "копиях семьи → СТОП 3; стойка не тронута", rc1 == 2 and "NpcServer.exe" in o1 and rc2 == 2 and "файл открыт процессом" in o2
                  and rc3 == 3 and "не во всех копиях" in o3 and open(st.path(npc_rel), "rb").read() == b"\0" * 479, (rc1, rc2, rc3, o3[-160:]))
        finally:
            base.rbusy = saved[0]
            dc.ALLOWED.clear()
            dc.ALLOWED.update(saved[1])
            st.procs = dict(st.expect)


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны: таблицы А4 трёх GS по SSH, живая оценка набора А4, план клиента на живом порту с НАСТОЯЩИМ
    генератором ItemDB (ведомость hairtable), расхождения всех областей. Ничего не пишет ни в стойку, ни в порт."""
    from core import config
    from domains import shopdata as SD
    if config.get().on_server:
        return check("живой самотест А4 — с ПК (порт и SSH)", True)
    sn = SD.Snap()
    sn.extend(SD.srv_rels_for(SD.AREAS[1:]))
    a4 = [r for r in sn.md5 if r.endswith(("HonorPrice_Table.txt", "HairTypeTable.txt"))]
    check("живая стойка А4: md5 HonorPrice_Table и HairTypeTable трёх GS получены", len(a4) == 6 and "none" not in [sn.md5[r] for r in a4],
          {r: sn.md5[r][:8] for r in a4})
    cli = SD.Client.load(force=True)
    li = next(i for i, x in enumerate(cli.equip or []) if x)
    cur = cli.equip[li][0]
    alt = next((c for c in cli.equip[li][1:] if c != cur), None)
    hid = sorted(cli.hair)[0]
    items = [{"pos": 1, "kind": "honor.price", "params": {"pos": 0, "coins": cli.honor[0][7] + 1, "rank": cli.honor[0][8]}},
             {"pos": 2, "kind": "hair.price", "params": {"id": hid, "value": cli.hair[hid][1] + 1}}]
    if alt:
        items.append({"pos": 3, "kind": "equipshop.set", "params": {"list": li, "index": 0, "code": alt}})
    ev = SD.Eval(items, False, sn, cli).run()
    s = ev.summary()
    check("живая оценка набора А4 (честь +1 монета, причёска +1, 6800 — перестановка кода): без ошибок, сервер — 2 таблицы × 3 GS",
          not s["errors"] and s["server"]["count"] == 6, s["errors"][:3])
    tracked = [p for p in list(SD.CLIENT_FILES.values()) + SD.all_ledger_paths() if os.path.isfile(p)]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0)
    after = {p: SD.md5f(p) for p in tracked}
    vo = SD.ledger_paths("hairtable")[0]
    check("живой план клиента А4: настоящий генератор ItemDB подтверждает ведомость hairtable, .she и .bin правятся на месте; ничего не "
          "записано (md5 до = после)", not plan["errors"] and vo in plan["files"] and before == after, plan["errors"][:3])
    d = SD.divergence(limit=5, areas="all")
    check("расхождения всех областей: 7 разделов магазинов + 6800, честь, причёски + монстры (А4.3) + предметы (А4.4) + задания и доска (А4.5) "
          "+ звания (А4.6) + навыки и опыт (А4.7) + карты (А4.8) + счастливые часы (А5.4) + настройки патчей (А5.5)",
          # ★ А5.9 (21.11): с А5.4 / А5.5 в конце ещё «Счастливые часы» (lucky) и «Настройки патчей» (patchcfg) — всего 19 разделов
          [x["key"] for x in d["sections"]][-12:] == ["equipshop", "honor", "hair", "mobs", "items", "quests", "board", "titles", "skills", "maps",
                                                      "lucky", "patchcfg"]
          and len(d["sections"]) == 19,
          [(x["key"], x["count"]) for x in d["sections"]])
