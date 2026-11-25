# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_shops.py — самотест волны А3 «Данные: магазины» (наборы изменений, domains/shopdata.py, shopcs.py). 19.11.2026.

offline(check, ldb)  — без сети: шансы и прогон бустера, правка таблиц (SellItemTable / пакет / бустер / гача / цена с пробелами
                       поля), все виды позиций и отказы (решение владельца п.4, ShopBuyFlag, стопки, «срочно»), план клиентской
                       половины на временных копиях (сверка «порт сменился», ничего не пишется), весь путь набора на временной
                       базе LocalDB (создать → позиции → проверить → утвердить → сухой прогон сервера и клиента → отменить), журнал,
                       SQL/выкладка/права/переводы.
live(check)          — только чтение стойки и порта + сухие прогоны: оценка тестового набора по живым таблицам, экран расхождений,
                       стенд шлюза (gift_check.py), план клиента на живом порту (md5 файлов порта до = после), настоящий сухой прогон
                       deploy_changeset.py (SSH, без записи) и весь путь тестового набора в AsdaAdmin (отменяется в конце).
Ни рестартов стойки, ни записи в таблицы стойки или порта. Побочных эффектов при импорте нет.
"""
import contextlib
import json
import os
import re
import secrets
import shutil
import struct
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


# ---------------------------------------------------------------------------------------------------------- синтетическая стойка
def _itrow(code, price=100, t2=1, t3=4, t16=0, t17=0, t23=1, t24=1, t38=1, t39=0):
    f = ["0 "] * 42
    f[0], f[2], f[3], f[16], f[17], f[23], f[24], f[26], f[38], f[39] = (str(code) + " ", str(t2) + " ", str(t3) + " ", str(t16) + " ",
                                                                        str(t17) + " ", str(t23) + " ", str(t24) + " ", str(price) + " ",
                                                                        str(t38) + " ", str(t39) + " ")
    return "\t".join(f)


ITEMS = [_itrow(30000, 100), _itrow(30001, 500, t24=0), _itrow(30002, 300, t39=1), _itrow(30003, 900, t16=11, t17=200, t39=0, t24=0),
         _itrow(30004, 50, t38=0), _itrow(30005, 70, t2=10, t3=1, t23=0, t24=3), _itrow(30006, 40), _itrow(30007, 45)]


def _tables():
    crlf = lambda rows: ("\r\n".join(rows) + "\r\n").encode("latin-1")
    base = {
        "item_table.txt": crlf([str(len(ITEMS))] + ITEMS),
        "SellItemTable.txt": crlf(["79940\t3", "30001", "30002", "30003"]),
        "PackageItem_Table.txt": crlf(["1", "0\t30000\t5\t-1\t0\t-1\t0\t-1\t0\t-1\t0"]),
        "GachaItemRateTable.txt": crlf(["1", "1\t30000\t100\t30005\t50" + "\t0\t0" * 33]),
        "PrimiumGaChaTable.txt": crlf(["3", "0\t0\t30000\t1", "1\t0\t30005\t1", "2\t1\t30000\t2"]),
        "PrimiumGaChaPriceTable.txt": crlf(["2", "0\t690", "1\t690"]),
    }
    out = {}
    for g in ("GameServer", "Indun_GameServer", "Ch2_GameServer"):
        for t, b in base.items():
            if g == "Indun_GameServer" and t == "SellItemTable.txt":
                b = crlf(["79940\t3", "30003", "30001", "30002"])
            out[g + "\\ItemTable_Info\\" + t] = b
    return out


def _client_dict():
    pairs = [[30000, 100], [30005, 50]] + [[0, 0]] * 33
    return {"built": "selftest", "md5": {"item_list": "a"},
            "items": {str(c): [i, p, p] for i, (c, p) in enumerate([(30000, 100), (30001, 500), (30002, 300), (30003, 900), (30004, 50),
                                                                     (30005, 70), (30006, 40), (30007, 45)])},
            "premium6000": [[30001, 2, 2, 9, 0, 0]], "panel_tail": [], "booster15300": [30002],
            "npc": {"1": {"spd": [30000, 30006], "hidden": [30006], "shown": [30000]}},
            "pkg": {"0": [[30000, 5], [-1, 0], [-1, 0], [-1, 0], [-1, 0], [780, 0]]}, "booster": {"1": pairs},
            "gatya": [[0, 0, 30000, 0, 1], [1, 0, 33, 1, 1]], "gatya_price": {"0": 690, "1": 690}}


FAKE_COLS = {   # раскладка записи (смещение в DataHex, тип) — как REGISTRY генератора; для подставного генератора и rebuild_hex
    "item_list": {"Price": (0xA4, "i32"),
                  # ★ А4.4: поля «Предметов» (колонки CSV и поля ведомости без колонки — Field68 / Weight, как ledger_fields реестра)
                  "Field68": (68, "i32"), "Weight": (72, "i32"), "RequiredLevel": (80, "i32"), "RequiredLevelMax": (84, "i32"),
                  "UsageCategory": (92, "i32"), "TradableFlag": (152, "i32")},
    "hairtable": {"Price": (0x28, "i32")},
    "booster_list": {"Code": (0, "i32"), "Slot00ItemCode": (4, "i32"), "Slot00Weight": (8, "i32")},
    "sowell_list": {"RequiredLevel": (65, "u8")},                  # ★ А4.4: уровень самоцвета
}
_FMT = {"i32": "<i", "u8": "<B", "i16": "<h", "u16": "<H"}


def fake_regen(archive=None):
    """★ А4.0: подставной генератор ItemDB для самотестов (настоящий decode_item_db читает Bin.bbz): «архив» — заданные байты CSV
    (archive[key]) или текущий CSV порта; ведомость значений накладывается по порядку строк с семантикой декодера (в данных
    «стало» — уже; «было» — применить, байты DataHex — тоже), хвост — замена/дописывание строк по _row.
    ★ ревизия 33 В-1: хвост — АТОМАРНО, как decode_item_db.append_tail: у строки с DataHex колонки раскладки обязаны совпасть с
    байтами, иначе хвост отвергается целиком."""
    import csv as _csv
    from domains import shopdata as SD

    def regen(key, vd, td):
        raw = archive[key] if archive and key in archive else open(SD.CLIENT_FILES[key], "rb").read()
        _h, _by, rows = SD._csv_rows(raw)
        rows = [dict(r) for r in rows]
        by = {r["_row"]: r for r in rows}
        lay = FAKE_COLS.get(key, {})
        vo = os.path.join(vd, key + ".csv")
        if os.path.isfile(vo):
            for e in _csv.DictReader(open(vo, encoding="utf-8", newline="")):
                r = by.get(e["row"])
                if r is None:
                    continue
                col = e["column"]
                if col not in r and col in lay and r.get("DataHex"):      # ★ А4.4: поле ведомости без колонки — только байты
                    off, ty = lay[col]
                    cur = str(struct.unpack_from(_FMT[ty], bytes.fromhex(r["DataHex"]), off)[0])
                    if cur == e["now"] or cur != e["was"]:
                        continue
                elif r.get(col) == e["now"] or r.get(col) != e["was"]:
                    continue
                else:
                    r[col] = e["now"]
                if col in lay and r.get("DataHex"):
                    b = bytearray(bytes.fromhex(r["DataHex"]))
                    struct.pack_into(_FMT[lay[col][1]], b, lay[col][0], int(e["now"]))
                    r["DataHex"] = bytes(b).hex()
        ta = os.path.join(td, key + ".csv")
        if os.path.isfile(ta):
            tail = list(_csv.DictReader(open(ta, encoding="utf-8", newline="")))
            bad = [t["_row"] for t in tail if t.get("DataHex") and any(
                c in t and struct.unpack_from(_FMT[_ty], bytes.fromhex(t["DataHex"]), off)[0] != int(t[c]) for c, (off, _ty) in lay.items())]
            if not bad:
                for t in tail:
                    if t["_row"] in by:
                        by[t["_row"]].update({c: v for c, v in t.items() if c in by[t["_row"]]})
                    else:
                        rows.append({c: v for c, v in t.items() if c != "_source"})
            elif archive is None:                    # «архив» = текущий CSV с хвостом: хвост отвергнут — его строк нет
                rows = [r for r in rows if r["_row"] not in {t["_row"] for t in tail}]
        return rows
    return regen


@contextlib.contextmanager
def ledger_fixture(archive=None):
    """Ведомости ItemDB во временной папке + подставной генератор и раскладка (настоящие ведомости порта не читаются и не пишутся).
    Сведения «на руках у игроков» — подставные (живая база в офлайн-самотесте не читается)."""
    from domains import shopdata as SD
    tmp = tempfile.mkdtemp(prefix="asda_cs_ledger_fx_")
    saved = (SD.LEDGER_ROOT, SD.itemdb_regen, SD.itemdb_cols, SD.held_counts)
    os.makedirs(os.path.join(tmp, "_value_overlay"))
    os.makedirs(os.path.join(tmp, "_tail_append"))
    SD.LEDGER_ROOT, SD.itemdb_regen, SD.itemdb_cols = tmp, fake_regen(archive), (lambda key: dict(FAKE_COLS.get(key, {})))
    SD.held_counts = lambda codes, stack=None: {int(c): {"rows": 2, "amount": 7, "stack": bool((stack or {}).get(int(c)))} for c in codes}
    try:
        yield tmp
    finally:
        SD.LEDGER_ROOT, SD.itemdb_regen, SD.itemdb_cols, SD.held_counts = saved
        shutil.rmtree(tmp, ignore_errors=True)


@contextlib.contextmanager
def synthetic():
    """Подмена источников shopdata синтетической стойкой и клиентом (srvtables, Snap, Client)."""
    from domains import shopdata as SD, srvtables
    raw = _tables()
    md5 = {r: SD.md5b(b) for r, b in raw.items()}

    class FakeSnap(SD.Snap):
        def __init__(self, md5_=None):
            self.md5 = dict(md5)
            self._b = {}

        def raw(self, rel):
            return raw[rel]

    saved = (SD.Snap, SD.Client.load, SD.live_md5, srvtables.table, srvtables.stack_text, srvtables.patch_on_all, SD.gateway_stand)
    cli = SD.Client(_client_dict(), "snapshot")
    fn = {5: ["5"] + ["0"] * 25}
    SD.Snap = FakeSnap
    SD.Client.load = classmethod(lambda cls, force=False: cli)
    SD.live_md5 = lambda rels: {r: md5.get(r, "none") for r in rels}
    srvtables.table = lambda name: fn if name.startswith("Function") else {}
    srvtables.stack_text = lambda rel, ttl=60: '{"30010": {"deliveryItemCode": 30003, "price": 900}}'
    srvtables.patch_on_all = lambda sec: {g: sec != "P16_GachaToInven" for g in SD.GS}
    SD.gateway_stand = lambda ev: (True, ["стенд шлюза: самотест (подмена)"])
    lfx = ledger_fixture()                     # ★ А4.0: ведомости ItemDB — во временной папке, генератор — подставной
    lfx.__enter__()
    try:
        yield raw, md5, cli
    finally:
        lfx.__exit__(None, None, None)
        (SD.Snap, SD.Client.load, SD.live_md5, srvtables.table, srvtables.stack_text, srvtables.patch_on_all, SD.gateway_stand) = saved


def _ev(items, urgent=False):
    from domains import shopdata as SD
    return SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], urgent).run()


def _pos(ev, i=0):
    return ev.positions[i]


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check, ldb=None):
    from domains import shopdata as SD
    # шансы бустера (Recv_GachaItemUse + sub_5329A0)
    o = SD.booster_odds([[1, 1], [2, 1]] + [[0, 0]] * 33)
    check("бустер: точные шансы при сумме < 0x7FFF — rand() mod (T+1) (2 + мимо = 32768 исходов)",
          abs(o["rows"][0][3] - 10923 / 32768.0) < 1e-12 and abs(o["miss"] - 10922 / 32768.0) < 1e-12)
    big = SD.booster_odds([[7, 40000], [8, 1], [0, 999], [9, 0]])
    check("бустер: при сумме ≥ 0x7FFF — 30 бит (rand()<<15|rand()); пары с кодом 0 или весом 0 не участвуют, сумма шансов = 1",
          len(big["rows"]) == 2 and abs(sum(r[3] for r in big["rows"]) + big["miss"] - 1) < 1e-12)
    pr = [[30000 + j, (j + 1) * 100] for j in range(35)]
    sim = SD.booster_sim(pr, 100000, seed=12345)
    odd = SD.booster_odds(pr)
    worst = max(abs(sim["hits"].get(str(r[0]), 0) / 100000.0 - r[3]) for r in odd["rows"])
    check("бустер: прогон 100 000 открытий (LCG MSVC) сходится с точными шансами (отклонение < 0,5 %%) и повторяем по зерну",
          sum(sim["hits"].values()) + sim["miss"] == 100000 and worst < 0.005 and SD.booster_sim(pr, 1000, seed=7) == SD.booster_sim(pr, 1000, seed=7),
          "%.4f" % worst)
    # нормализация позиций
    bad = []
    for kind, p in (("price", {"code": "x", "value": 1}), ("npcshop.hide", {"npc": 1, "code": 2}), ("package.set", {"row": 0, "pairs": []}),
                    ("gacha.price", {"slot": 5, "value": 1}), ("booster.weights", {"row": 1, "pairs": [[1, 1]] * 36}), ("нет", {})):
        try:
            SD.norm(kind, p)
            bad.append(kind)
        except Exception:
            pass
    check("позиции: неверные параметры — отказ (не число, нет причины скрытия, пустой набор, автомат > 5, > 35 пар, неизвестный вид)", not bad, bad)
    with synthetic() as (raw, md5, cli):
        ev = _ev([("price", {"code": 30001, "value": 600})])
        nb = ev.new_bytes()
        line = [ln for ln in nb["GameServer\\ItemTable_Info\\item_table.txt"].split(b"\r\n") if ln.startswith(b"30001")][0]
        check("цена: ток.26 во всех 3 GS, пробелы поля как были; клиент — item_list.Price и DataHex +0xA4",
              not ev.errors and len(nb) == 3 and line.split(b"\t")[26] == b"600 " and [e["type"] for e in ev.client] == ["csv_cell", "csv_hex_i32"],
              ev.errors)
        e1 = _ev([("price", {"code": 30010, "value": 1})])
        e2 = _ev([("price", {"code": 500, "value": 1})])
        check("цена: код карты шлюза и спецпредмет < 20551 — отказ «не подтверждено разбором»",
              _pos(e1)["errors"] and "карте шлюза" in _pos(e1)["errors"][0] and _pos(e2)["errors"] and "Function_Table" in _pos(e2)["errors"][0])
        ev = _ev([("sell.allow", {"code": 30000}), ("sell.deny", {"code": 30002})])
        f = ev.new_bytes()
        gs, ind = f["GameServer\\ItemTable_Info\\SellItemTable.txt"], f["Indun_GameServer\\ItemTable_Info\\SellItemTable.txt"]
        check("белый список: добавить в конец / убрать, шапка «макс число» пересчитана; у Indun свой порядок сохранён",
              gs == b"79940\t3\r\n30001\r\n30003\r\n30000\r\n" and ind == b"79940\t3\r\n30003\r\n30001\r\n30000\r\n" and not ev.errors, (gs, ind))
        check("белый список: запрет кода с карточкой — предупреждение «5071 код 14 до выпуска»",
              any("5071" in w for w in _pos(ev, 1)["warnings"]))
        ev = _ev([("shop6000.add", {"code": 30000, "cat": 2, "sub1": 2, "sub2": 9, "newflag": 0})])
        ev2 = _ev([("npcshop.add", {"npc": 1, "code": 30001})])
        check("решение владельца п.4: код лавки NPC на премиум-витрину и код премиум-витрины в лавку — отказ (одна цена: золото = GXP)",
              any("п.4" in e for e in _pos(ev)["errors"]) and any("п.4" in e for e in _pos(ev2)["errors"]))
        ev = _ev([("npcshop.add", {"npc": 1, "code": 30004})])
        ev2 = _ev([("npcshop.add", {"npc": 1, "code": 30005})])
        ev3 = _ev([("npcshop.add", {"npc": 1, "code": 30006}), ("npcshop.add", {"npc": 1, "code": 30007}), ("npcshop.add", {"npc": 9, "code": 30007})])
        check("лавка NPC: ShopBuyFlag 0 и «+36 ≠ 1» — отказ по правилам CharItemBuy; скрытый — строка ведомости убирается, новый — в .spd; "
              "нет js<npc>.spd — отказ", "ShopBuyFlag" in str(_pos(ev)["errors"]) and "+36" in str(_pos(ev2)["errors"])
              and [e["type"] for e in ev3.client] == ["hidden_del", "spd_append"] and _pos(ev3, 2)["errors"])
        ev = _ev([("npcshop.hide", {"npc": 1, "code": 30000, "reason": "тест"}), ("npcshop.hide", {"npc": 1, "code": 30007, "reason": "тест"})])
        check("лавка NPC: скрыть — строка ведомости npc_shop_hidden.csv; товара нет в витрине — отказ; сервер не меняется",
              ev.client[0]["type"] == "hidden_add" and _pos(ev, 1)["errors"] and not ev.new_bytes())
        res = {}
        for name, pairs in (("over", [[30000, 40000]]), ("single", [[30005, 2]]), ("func", [[5, 2]]), ("heavy", [[30000, 6000]]),
                            ("ok", [[30000, 10], [30005, 1]])):
            e = _ev([("package.set", {"row": 0, "pairs": pairs})])
            res[name] = e
        okline = res["ok"].new_bytes()["GameServer\\ItemTable_Info\\PackageItem_Table.txt"].split(b"\r\n")[1]
        check("набор: стопка > 32 767 и нестопочный ×2 и функциональный ×2 — ошибки; вес > 5 000 — предупреждение; пустые пары «-1 0»; "
              "шестая пара клиента не трогается", res["over"].errors and res["single"].errors and res["func"].errors and not res["heavy"].errors
              and any("5000" in w for w in _pos(res["heavy"])["warnings"]) and okline == b"0\t30000\t10\t30005\t1\t-1\t0\t-1\t0\t-1\t0"
              and "Item5" not in res["ok"].client[0]["cells"], okline)
        w1 = _ev([("booster.weights", {"row": 1, "pairs": [[30000, 300], [30005, 50]]})], urgent=True)
        w2 = _ev([("booster.weights", {"row": 1, "pairs": [[30005, 300], [30000, 50]]})], urgent=True)
        w3 = _ev([("price", {"code": 30001, "value": 7})], urgent=True)
        check("срочно, только сервер: веса бустера без смены кодов — можно; смена кодов и цена — отказ (решение владельца п.1)",
              not w1.errors and w1.summary()["urgent_ok"] and w2.errors and w3.errors and "booster:1" in w1.sim)
        g = _ev([("gacha.pool", {"slot": 1, "rows": [[30000, 1], [30005, 3]]}), ("gacha.price", {"slot": 0, "value": 700})])
        pool = g.new_bytes()["GameServer\\ItemTable_Info\\PrimiumGaChaTable.txt"]
        g2 = _ev([("gacha.pool", {"slot": 2, "rows": [[30000, 1]]})])
        check("гача: пул слота заменён, индексы заново строго +1, шапка = строк; цена автомата; автомат вне таблицы цен — отказ; шанс 1/N",
              pool == b"4\r\n0\t0\t30000\t1\r\n1\t0\t30005\t1\r\n2\t1\t30000\t1\r\n3\t1\t30005\t3\r\n" and not g.errors and g2.errors
              and any("1/2" in w for w in _pos(g)["warnings"]), pool)
        d = _ev([("price", {"code": 30001, "value": 1}), ("price", {"code": 30001, "value": 2})])
        check("две позиции на одну цель — отказ", any("одну цель" in e for e in d.errors))
        part = SD.Eval([], False)
        part.st.get("GameServer", "SellItemTable.txt").allow(30000)
        part.cross()
        check("выкладчик требует все GameServer: таблица меняется не во всех — ошибка", any("не во всех" in e for e in part.errors), part.errors)
        o1 = _ev([("npcshop.add", {"npc": 1, "code": 30007}), ("shop6000.add", {"code": 30007, "cat": 2, "sub1": 2, "sub2": 9, "newflag": 0})])
        o2 = _ev([("shop6000.add", {"code": 30007, "cat": 2, "sub1": 2, "sub2": 9, "newflag": 0}), ("npcshop.add", {"npc": 1, "code": 30007})])
        check("ревизия 30 М-1: п.4 по итогу набора — «лавка, потом витрина» и обратный порядок оба отказывают",
              any("п.4" in e for e in o1.errors) and any("п.4" in e for e in o2.errors), (o1.errors, o2.errors))
        bad5 = [c for c in (500, 7100) if not _refused_norm("shop6000.add", {"code": c, "cat": 2, "sub1": 2, "sub2": 9, "newflag": 0})]
        check("ревизия 30 М-5: на витрину 6000 — только item_list (спецпредмет и самоцвет — отказ «не подтверждено»)", not bad5, bad5)
        # план клиентской половины на временных копиях порта
        _client_plan_checks(check)
        if ldb:
            _flow_localdb(check, ldb)
    if ldb:                                   # песочница — ВНЕ synthetic(): там свой настоящий Client.load по копиям порта
        import selftest_shops_sandbox
        selftest_shops_sandbox.run(check, ldb)
    _static_checks(check)


def _client_plan_checks(check):
    from core import config
    from domains import shopdata as SD
    d = tempfile.mkdtemp(prefix="asda_cs_cli_")
    saved = (dict(SD.CLIENT_FILES), SD.PANEL_TAIL, SD.HIDDEN_CSV, SD.spd_dir)
    try:
        il = os.path.join(d, "item_list.csv")
        hx = bytearray(248)
        struct.pack_into("<i", hx, SD.PRICE_OFF, 500)
        open(il, "w", encoding="utf-8", newline="").write("_row,ItemCode,ItemName,Price,DataHex\r\n0,30001,\"Имя, с запятой\",500,%s\r\n" % bytes(hx).hex())
        pk = os.path.join(d, "packagetable.csv")
        open(pk, "w", encoding="utf-8", newline="").write("_row,Index,Item0,Qty0,Item1,Qty1,Item2,Qty2,Item3,Qty3,Item4,Qty4,Item5,Qty5,Reserved52\r\n"
                                                         "0,0,30000,5,-1,0,-1,0,-1,0,-1,0,780,0,21\r\n")
        hd = os.path.join(d, "npc_shop_hidden.csv")
        open(hd, "w", encoding="utf-8-sig", newline="").write("npc,code,name_ru,reason\r\n1,30006,x,y\r\n")
        spd = os.path.join(d, "Shop")
        os.makedirs(spd)
        open(os.path.join(spd, "js1.spd"), "wb").write(struct.pack("<II", 0, 2) + struct.pack("<2I", 30000, 30006))
        SD.CLIENT_FILES.update(item_list=il, packagetable=pk, hidden=hd)
        SD.PANEL_TAIL, SD.HIDDEN_CSV, SD.spd_dir = os.path.join(d, "PremiumShopBin_tail_panel.json"), hd, (lambda: spd)
        before = {p: SD.md5f(os.path.join(d, p)) for p in ("item_list.csv", "packagetable.csv", "npc_shop_hidden.csv", r"Shop\js1.spd")}
        ev = _ev([("price", {"code": 30001, "value": 600}), ("package.set", {"row": 0, "pairs": [[30000, 7]]}),
                  ("npcshop.hide", {"npc": 1, "code": 30000, "reason": "самотест"}), ("npcshop.add", {"npc": 1, "code": 30007}),
                  ("shop6000.add", {"code": 30003, "cat": 2, "sub1": 2, "sub2": 9, "newflag": 1}),
                  ("sell.allow", {"code": 30000})])
        cfg = config.get()
        was = cfg.on_server
        cfg.on_server = False
        try:
            plan = SD.client_plan(ev.client, 77)
        finally:
            cfg.on_server = was
        b = plan["_bytes"]
        il2 = b[il].decode("utf-8")
        row = il2.split("\r\n")[1]
        nh = struct.unpack_from("<i", bytes.fromhex(row.rsplit(",", 1)[1]), SD.PRICE_OFF)[0]
        spd2 = b[os.path.join(spd, "js1.spd")]
        tail = json.loads(b[SD.PANEL_TAIL].decode("utf-8"))
        after = {p: SD.md5f(os.path.join(d, p)) for p in before}
        check("план клиента: Price и DataHex +0xA4 одной строки (кавычки имени сохранены), пакет — 5 пар, шестая не тронута, ведомость "
              "скрытых +1 строка, .spd +код, хвост витрины 6000 панели; DT — item_list, packagetable; импортёры NpcShop и PremiumShopBin",
              not plan["errors"] and row.startswith('0,30001,"Имя, с запятой",600,') and nh == 600
              and "0,0,30000,7,-1,0,-1,0,-1,0,-1,0,780,0,21" in b[pk].decode("utf-8")
              and "самотест" in b[hd].decode("utf-8-sig") and struct.unpack_from("<I", spd2, 4)[0] == 3 and tail["rows"][0]["ItemId"] == 30003
              and sorted(j["dt"].rsplit("/", 1)[1] for j in plan["dt_jobs"]) == ["DT_item_list", "DT_packagetable"]
              and plan["importers"] == ["npcshop", "premium6000"], plan["errors"])
        check("план клиента — сухой: файлы порта не изменились (md5 до = после)", before == after)
        open(il, "w", encoding="utf-8", newline="").write("_row,ItemCode,ItemName,Price,DataHex\r\n0,30001,x,555,%s\r\n" % bytes(hx).hex())
        cfg.on_server = False
        try:
            plan2 = SD.client_plan(ev.client, 77)
        finally:
            cfg.on_server = was
        check("план клиента: порт сменился с проверки (цена 555 ≠ 500) — отказ «пересоберите набор»",
              any("пересоберите" in e for e in plan2["errors"]), plan2["errors"])
    finally:
        SD.CLIENT_FILES.clear()
        SD.CLIENT_FILES.update(saved[0])
        SD.PANEL_TAIL, SD.HIDDEN_CSV, SD.spd_dir = saved[1], saved[2], saved[3]
        shutil.rmtree(d, ignore_errors=True)


def _flow_localdb(check, ldb):
    """Весь путь набора на временной базе LocalDB (схема adminc_02 + adminc_13), подменённая стойка/клиент, подменённый выкладчик."""
    from core import audit, config, db, ops
    from domains import shopcs, shopdata as SD
    import pyodbc
    name = "AsdaAdminCsTest_" + secrets.token_hex(4)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    tmp = tempfile.mkdtemp(prefix="asda_cs_flow_")
    saved = (SD.CS_DIR, shopcs.run_deploy, SD.client_plan)
    try:
        cn = ldb(name)
        for f in ("adminc_02_schema.sql", "adminc_13_changeset.sql", "adminc_14_jobs.sql"):   # ★ ревизия 41 В-1: рестарт набора — под adm.job
            text = open(os.path.join(ROOT, "sql", f), encoding="utf-8").read()
            for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
                if batch.strip():
                    cn.cursor().execute(batch)
        cn.close()
        check("adminc_13 на LocalDB (без пользователя asda_admin — выдача прав пропущена)", True)
        db.set_override("admin", lambda database: ldb(name))
        SD.CS_DIR = tmp
        seen = {}

        def fake_deploy(manifest, args=(), mode="", timeout=900):
            seen["man"] = json.load(open(manifest, encoding="utf-8"))
            return 0, "сухой прогон: всё готово к --apply (%d файлов)" % len(seen["man"]["files"])
        shopcs.run_deploy = fake_deploy
        SD.client_plan = lambda edits, cs_id: {"files": {"x": {"old": "a", "new": "b", "diff": []}}, "errors": [], "dt_jobs": [],
                                               "importers": [], "_bytes": {}}
        cli = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
        web_admin = ops.Ctx(1, "adm_test", "admin", "100.64.0.9", "web")
        gm = ops.Ctx(2, "gm_test", "gm", "100.64.0.9", "web")
        cfg = config.get()
        was = cfg.on_server
        cfg.on_server = False
        try:
            r = ops.run(web_admin, "shop.cs_create", {"title": "САМОТЕСТ А3", "note": "самотест пути набора на LocalDB", "order_mode": "together"})
            cid = r["result"]["id"]
            for kind, p in (("price", {"code": 30001, "value": 600}), ("sell.deny", {"code": 30002}),
                            ("booster.weights", {"row": 1, "pairs": [[30000, 150], [30005, 50]]})):   # ★ ревизия 33: не сильная правка (утверждает admin; второе подтверждение — только владелец)
                ops.run(web_admin, "shop.cs_item_add", {"cs": cid, "kind": kind, "params": p})
            gm_refused = _refused(lambda: ops.run(gm, "shop.cs_item_add", {"cs": cid, "kind": "sell.deny", "params": {"code": 30001}}))
            ops.run(web_admin, "shop.cs_check", {"cs": cid})
            cs = shopcs.get(cid)
            st1 = cs["status"]
            ops.run(web_admin, "shop.cs_approve", {"cs": cid})
            add_late = _refused(lambda: ops.run(web_admin, "shop.cs_item_add", {"cs": cid, "kind": "sell.deny", "params": {"code": 30001}}))
            ops.run(web_admin, "shop.cs_server_dry", {"cs": cid})
            web_client = _refused(lambda: ops.run(web_admin, "shop.cs_client_dry", {"cs": cid}))
            ops.run(cli, "shop.cs_client_dry", {"cs": cid})
            no_owner = _refused(lambda: ops.run(web_admin, "shop.cs_server_apply", {"cs": cid, "confirm": "restart"}))
            no_cli = _refused(lambda: ops.run(ops.Ctx(3, "own", "owner", "100.64.0.9", "web"), "shop.cs_server_apply",
                                              {"cs": cid, "confirm": "restart"}))
            no_confirm = _refused(lambda: ops.run(cli, "shop.cs_server_apply", {"cs": cid, "unsynced_ok": True}))
            unsynced = _refused(lambda: ops.run(cli, "shop.cs_server_apply", {"cs": cid, "confirm": "restart"}))
            cs2 = shopcs.get(cid)
            ops.run(web_admin, "shop.cs_cancel", {"cs": cid})
            cs3 = shopcs.get(cid)
            acts = [a["action"] for a in audit.query(action_prefix="shop.cs", target="changeset:%d" % cid, limit=100)]
            acts += [a["action"] for a in audit.query(action_prefix="shop.cs_create", target="changeset:new", limit=5)
                     if json.loads(a.get("after_json") or "{}").get("id") == cid]
        finally:
            cfg.on_server = was
        man = seen.get("man") or {}
        check("путь набора: создать → позиции → проверить (checked) → утвердить → сухой прогон сервера (манифест всех 3 GS, база/новый md5) "
              "→ сухой прогон клиента → отменить (rolled_back)", st1 == "checked" and cs2["status"] == "approved" and cs2["server_state"] == "dry_ok"
              and cs2["client_state"] == "dry_ok" and cs3["status"] == "rolled_back" and len(man.get("files", {})) == 9
              and all(set(v) == {"local", "base", "new"} for v in man.get("files", {}).values()), (st1, cs2["status"], len(man.get("files", {}))))
        check("права: GM позиции не правит; после утверждения позиции не правятся; клиентская половина — только консолью ПК",
              gm_refused and add_late and web_client)
        check("применение сервера: admin — нет права shop.apply; владелец из браузера — отказ (только консоль ПК); без --confirm-restart — "
              "отказ; клиент не применён — отказ без --unsynced-ok", no_owner and no_cli and no_confirm and unsynced)
        check("журнал: каждый шаг набора — запись adm.audit с целью changeset:№",
              all(a in acts for a in ("shop.cs_create", "shop.cs_item_add", "shop.cs_check", "shop.cs_approve", "shop.cs_server_dry",
                                      "shop.cs_client_dry", "shop.cs_cancel", "shop.cs_server_apply")), acts)
    except pyodbc.Error as ex:
        check("путь набора на LocalDB", False, ex)
    finally:
        SD.CS_DIR, shopcs.run_deploy, SD.client_plan = saved
        db.set_override("admin", None)
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
        except pyodbc.Error:
            pass
        m.close()


def _refused_norm(kind, p):
    from domains import shopdata as SD
    from core import ops
    try:
        SD.norm(kind, p)
    except ops.OpRefused:
        return True
    return False


def _refused(fn):
    from core import ops
    try:
        fn()
    except ops.OpRefused:
        return True
    return False


def _static_checks(check):
    from core import auth, i18n
    rd = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()
    port = os.path.dirname(ROOT)
    dep = rd("deploy", "deploy_admin_center.py")
    check("выкладка: adminc_13_changeset после adminc_03 (-d AsdaAdmin), снимок клиента shop_client.json в пакете",
          dep.index("Run 'adminc_13_changeset.sql' 'AsdaAdmin'") > dep.index("Run 'adminc_03_grants.sql'") and "shop_client.json" in dep)
    v = rd("sql", "adminc_10_verify.sql")
    s13 = rd("sql", "adminc_13_changeset.sql")
    check("права asda_admin: набор — без DELETE (история), позиции — с DELETE; проверки в adminc_10; откат описан в adminc_99",
          "DENY  DELETE                         ON adm.changeset" in s13 and "'adm.changeset DELETE'" in v and "'adm.changeset_item DELETE'" in v
          and (P.dev_text(ROOT, "sql", "adminc_99_rollback.sql") is None or "adminc_13_changeset" in rd("sql", "adminc_99_rollback.sql")))
    check("права: shop.edit — owner, admin; shop.apply — только owner; shop.view — owner, admin",
          auth.PERMS["shop.edit"] == {"owner", "admin"} and auth.PERMS["shop.apply"] == {"owner"} and auth.PERMS["shop.view"] == {"owner", "admin"})
    imp = open(os.path.join(port, "AstoryClient", "Tools", "asda_import_premium_shop_bin.py"), encoding="utf-8").read()
    dc = open(os.path.join(port, "AstoryServer", "Patches", "AsdaPatch", "tools", "deploy_changeset.py"), encoding="utf-8").read()
    cs = rd("domains", "shopcs.py")
    check("хвост витрины 6000 панели — третья ведомость импортёра; выкладчик набора — обёртка deploy_premium_boxes (манифест из окружения, "
          "только 6 таблиц ItemTable_Info); рестарт — restart_stack.py с объявлением, подъём — только --start-only",
          "PremiumShopBin_tail_panel.json" in imp and "import deploy_premium_boxes as base" in dc and "ASDA_CHANGESET_MANIFEST" in dc
          and all('"--no-deploy", "--no-announce"' in ln for ln in cs.split('"""', 2)[2].splitlines() if '"--no-announce"' in ln)
          and "restart_stack.py" in cs and '"--start-only"' in cs)
    js = rd("web", "shops.js")
    en = rd("web", "i18n.js")
    STR = r'"((?:[^"\\]|\\.)*)"'
    have = set(re.findall(STR + r"\s*:", en))
    need = {x for x in re.findall(r"T\(" + STR, js)} | {x for x in re.findall(STR, js) if re.search("[А-Яа-яЁё]", x)}
    miss = sorted(need - have)
    block = en.split("// А3 19.11", 1)[1] if "// А3 19.11" in en else ""
    keys = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", block, re.M)
    check("переводы панели: все строки web/shops.js есть в I18N_EN, в блоке А3 нет дублей", not miss and len(keys) == len(set(keys)), miss[:5])
    i18n.LANG.set("en")
    try:
        samples = ["набор №3 утверждён", "проверка набора №2: ошибок 0, предупреждений 3",
                   "позиция 1: сервер не продаст в лавке: GameServer: item_table ток.38 (+62, ShopBuyFlag) = 0 → 5021 код 5",
                   "правка позиций: набор №4 в статусе «approved» (нужно: draft, checked)",
                   "применение серверной половины — только консолью: python asda_admin.py changeset …",
                   "GameServer: кода нет в SellItemTable — магазин не продаст (5071 код 14); добавьте «Разрешить продажу»",
                   "набор больше не проходит проверку: две позиции набора на одну цель (позиция 2)",
                   "шансы — равномерно по строкам пула: 1/460 на строку (приз выбирает шлюз gp7, таблицы шансов нет)",
                   "карточка на витрине, а сервер не продаёт", "сухой прогон сервера набора №5: готово к выкладке"]
        left = [s for s in samples if re.search("[А-Яа-яЁё]", i18n.tr(s))]
    finally:
        i18n.LANG.set("ru")
    check("переводы службы: сообщения наборов — шаблоны EN в core/i18n.py (вложенные причины переводятся)", not left, left)


# ---------------------------------------------------------------------------------------------------------- живое (только чтение + сухие)
def live(check):
    from core import config, ops
    from domains import shopcs, shopdata as SD
    from domains import load_all
    load_all()      # ★ ревизия 87 Н-1 (24.11): разделы — как у службы и консоли; иначе операция чужого раздела — «неизвестная операция»
    cfg = config.get()
    if cfg.on_server:
        return check("живой самотест магазинов — с ПК (порт и SSH)", True)
    cli = SD.Client.load(force=True)
    sn = SD.Snap()
    check("живая стойка: md5 18 таблиц (3 GS × 6) получены по SSH", len(sn.md5) == 18 and "none" not in sn.md5.values())
    gr = SD.Table("x", sn.raw("GameServer\\ItemTable_Info\\GachaItemRateTable.txt"))
    f = SD._f(gr.lines[1])
    row1 = [[SD._int(f[1 + 2 * j]), SD._int(f[2 + 2 * j])] for j in range(35)]
    w = [[c, (wt + 1) if c else 0] for c, wt in row1]
    pk = SD.Table("x", sn.raw("GameServer\\ItemTable_Info\\PackageItem_Table.txt"))
    f2 = SD._f(pk.lines[pk.index()[0] if 0 in pk.index() else 1])
    prow = [[SD._int(f2[1 + 2 * k]), SD._int(f2[2 + 2 * k])] for k in range(5) if SD._int(f2[1 + 2 * k]) > 0]
    sell = SD.SellTable("x", sn.raw("GameServer\\ItemTable_Info\\SellItemTable.txt"))
    code = next(c for c in sell.codes if c in cli.b15300)
    items = [{"pos": 1, "kind": "booster.weights", "params": {"row": 1, "pairs": w}},
             {"pos": 2, "kind": "gacha.price", "params": {"slot": 0, "value": 691}},
             {"pos": 3, "kind": "npcshop.hide", "params": {"npc": 1, "code": cli.npc[1]["shown"][0], "reason": "самотест А3"}},
             {"pos": 4, "kind": "sell.deny", "params": {"code": code}},
             {"pos": 5, "kind": "package.set", "params": {"row": SD._int(f2[0]), "pairs": prow}}]
    ev = SD.Eval(items, False, sn, cli).run()
    s = ev.summary()
    check("живая оценка тестового набора: без ошибок; сервер — 4 таблицы × GS, клиент — правки booster_list / premium_gatya_data / "
          "ведомости; шансы и прогон 100 000 открытий бустера", not s["errors"] and s["server"]["count"] >= 9 and "booster:1" in s["sim"]
          and s["sim"]["booster:1"]["sim"]["n"] == SD.ROLLS, s["errors"][:3])
    bad = SD.Eval([{"pos": 1, "kind": "npcshop.add", "params": {"npc": 1, "code": next(iter(cli.p6000))}}], False, sn, cli).run()
    check("живая проверка решения п.4: предмет витрины 6000 в лавку NPC — отказ", any("п.4" in e for e in bad.errors), bad.errors[:2])
    d = SD.divergence(limit=5)
    check("экран расхождений: 7 разделов по живой стойке и порту", len(d["sections"]) == 7 and d["client_source"] == "port",
          [(x["key"], x["count"]) for x in d["sections"]])
    ok, lines = SD.gateway_stand(SD.Eval([{"pos": 1, "kind": "sell.deny", "params": {"code": code}}], False, sn, cli).run())
    check("стенд шлюза (gift_check.py процессом: настоящий server.js + правила GS) до/после: запрет продажи даёт расхождение «после»",
          ok is not None and lines and lines[0].startswith("стенд шлюза:"), lines)
    tracked = [p for p in SD.CLIENT_FILES.values() if os.path.isfile(p)] + [os.path.join(SD.spd_dir(), "js1.spd")]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0)
    after = {p: SD.md5f(p) for p in tracked}
    check("живой план клиента (порт): собирается без ошибок, ничего не записано (md5 файлов порта до = после)",
          not plan["errors"] and before == after and plan["files"], plan["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_live_")
    saved = SD.CS_DIR
    try:
        SD.CS_DIR = tmp
        man, mm = shopcs.build_server_out({"id": 0, "server_tag": None}, ev)
        rc, out = shopcs.run_deploy(man)
        check("настоящий сухой прогон deploy_changeset.py (обёртка deploy_premium_boxes; md5 базы по SSH, без записи)",
              rc == 0 and "сухой прогон: всё готово" in out, out.strip().splitlines()[-3:])
    finally:
        SD.CS_DIR = saved
        shutil.rmtree(tmp, ignore_errors=True)
    # весь путь тестового набора в живой AsdaAdmin (стойка и порт не меняются; набор отменяется)
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    try:
        cid = ops.run(ctx, "shop.cs_create", {"title": "САМОТЕСТ А3 (отменяется)", "note": "живой самотест волны А3"})["result"]["id"]
    except Exception as ex:
        return check("живой путь набора: AsdaAdmin.adm.changeset (выложена adminc_13?)", False, ex)
    flow_ok = False
    try:
        for it in items[:4]:
            ops.run(ctx, "shop.cs_item_add", {"cs": cid, "kind": it["kind"], "params": it["params"]})
        ops.run(ctx, "shop.cs_check", {"cs": cid})
        st = shopcs.get(cid)["status"]
        # ★ ревизия 33 В-2: гейт баланса и у магазинов А3 — веса бустера 0 → 1 (из нуля) — сильная правка, подтверждается явно
        ops.run(ctx, "shop.cs_approve", {"cs": cid, "balance_ok": "balance"})
        ops.run(ctx, "shop.cs_server_dry", {"cs": cid})
        r = ops.run(ctx, "shop.cs_client_dry", {"cs": cid})
        cs = shopcs.get(cid)
        check("живой путь тестового набора: проверен → утверждён → сухой прогон сервера (deploy_changeset.py) → сухой прогон клиента",
              st == "checked" and cs["status"] == "approved" and cs["server_state"] == "dry_ok" and cs["client_state"] == "dry_ok"
              and r["result"]["files"], (st, cs["status"], cs["server_state"], cs["client_state"]))
        flow_ok = True
    except Exception as ex:
        c = shopcs.get(cid).get("check") or {}
        check("живой путь тестового набора", False, "%s; ошибки проверки: %s" % (ex, (c.get("errors") or [])[:3]))
    finally:
        try:
            ops.run(ctx, "shop.cs_cancel", {"cs": cid})
        except Exception as ex:
            check("живой путь: отмена тестового набора", False, ex)
    check("живой путь: тестовый набор отменён (rolled_back), на стойку и в порт ничего не выкладывалось",
          shopcs.get(cid)["status"] == "rolled_back" and after == {p: SD.md5f(p) for p in tracked})
