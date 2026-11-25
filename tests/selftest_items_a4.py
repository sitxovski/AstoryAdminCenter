# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_items_a4.py — самотест шага А4.4 «Предметы» (20.11.2026, domains/cs_kinds/itemdata.py).

offline(check)       — подменная стойка selftest_shops.synthetic() + своя item_table (броня, расходник-стопка, штучный расходник,
                       контейнер, оружие, золото) и Cellob_Table трёх GS, карточки клиента: все поля белого списка, отказы «дюп и
                       целостность», баланс (×2, стопка, класс), план клиента на временных копиях с ведомостями (поля без колонки
                       Field68 / Weight → строки ведомости по имени; хвост; потеря правки → отказ), расхождения, справка, переводы.
sandbox(check, ldb)  — путь набора целиком: создать → проверить → утвердить (сильная — второе подтверждение) → сухой прогон НАСТОЯЩЕГО
                       deploy_changeset (item_table ×3 + Cellob_Table ×3) → клиент (CSV, ведомости, DT через подставную очередь UE) →
                       сервер подставным рестартом → откаты сервера и клиента (всё вернулось).
live(check)          — только чтение и сухие прогоны: md5 item_table / Cellob_Table трёх GS, справка по живой стойке, «на руках» из Joy1,
                       живая оценка набора, план клиента с НАСТОЯЩИМ генератором ItemDB (item_list: Weight/Field68/RequiredLevel,
                       sowell_list) — md5 порта до = после, НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH.
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
IT_REL = "ItemTable_Info" + BS + "item_table.txt"
CEL_REL = "ItemTable_Info" + BS + "Cellob_Table.txt"


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _crlf(rows):
    return ("\r\n".join(rows) + "\r\n").encode("latin-1")


def _it(code, t1=0, t2=1, t4=1, t5=150, t7=0, t16=11, t17=0, t23=0, t24=1, price=10, t3=4):
    f = ["0 "] * 42
    for k, v in ((0, code), (1, t1), (2, t2), (3, t3), (4, t4), (5, t5), (7, t7), (16, t16), (17, t17), (23, t23), (24, t24), (26, price), (38, 1)):
        f[k] = "%d " % v
    return "\t".join(f)


# код: (прочность, вес, мин. ур., макс. ур., класс, тип, стопка, ток.24)
ITEMS = {20551: (0, 0, 1, 150, 0, 11, 1, 1),
         31000: (50, 683, 1, 150, 1, 1, 0, 1),        # броня, сумка 1
         31001: (0, 23, 1, 150, 0, 11, 1, 1),         # расходник-стопка, сумка 2 (на руках у игроков)
         31002: (0, 5, 1, 150, 0, 11, 0, 1),          # штучный расходник, сумка 2 (на руках нет)
         31003: (0, 34, 1, 150, 0, 10, 1, 1),         # колчан (контейнер)
         31004: (60, 672, 1, 150, 40, 9, 0, 1),       # оружие
         31005: (60, 700, 1, 150, 3, 9, 0, 1),        # оружие с «битым» классом (значение встречается у типа 9)
         31006: (50, 690, 1, 150, 12, 1, 0, 1),       # броня второго класса (значения класса типа 1: 1, 12)
         31007: (0, 5, 1, 150, 0, 11, 0, 1),          # ★ ревизия 36 Б-2: как 23690 — ток.3 = 1, стопки нет (сервер не считает стопочным)
         31008: (0, 5, 1, 150, 0, 11, 1, 1)}          # ★ ревизия 36 Б-2: «полустопка» как 20826 — ток.3 = 0, ток.23 = 1
T3 = {31007: 1, 31008: 0}                             # ток.3 (у остальных — 4)
HELD = {31001: {"rows": 3, "amount": 900, "max": 600, "stack": True, "where": {"Item": 2, "ItemPostBox": 1}},
        31000: {"rows": 1, "amount": 0, "max": 0, "stack": False, "where": {"Item": 1}}}
GEMS = {7001: 5, 7002: 20}


def _item_table():
    return _crlf([str(len(ITEMS))] + [_it(c, t1=v[0], t2=v[1], t4=v[2], t5=v[3], t7=v[4], t16=v[5], t23=v[6], t24=v[7], t3=T3.get(c, 4))
                                      for c, v in sorted(ITEMS.items())])


def _cellob():
    rows = []
    for c, lv in sorted(GEMS.items()):
        f = ["0 "] * 20
        f[0], f[3], f[16] = "%d " % c, "3 ", "%d " % lv
        rows.append("\t".join(f))
    return _crlf([str(len(rows))] + rows)


def stack_files():
    # ★ ревизия 37 М-1: смена стопки сверяется с наградами заданий — подменной стойке нужны RepayTable, доска и книги (пустые)
    out = {g + BS + rel: b for g in GS3 for rel, b in ((IT_REL, _item_table()), (CEL_REL, _cellob()))}
    for g in GS3:
        for rel in ("ItemTable_Info" + BS + "RepayTable.txt", "NpcData_Info" + BS + "LimitationQuest.txt", "ItemTable_Info" + BS + "QuestBook_Table.txt"):
            out[g + BS + rel] = _crlf(["0"])
    return out


def _ihex(v):
    b = bytearray(248)
    for off, x in ((68, v[0]), (72, v[1]), (80, v[2]), (84, v[3]), (92, v[4])):
        struct.pack_into("<i", b, off, x)
    struct.pack_into("<i", b, 152, v[6])
    struct.pack_into("<i", b, 0xA4, 10)
    return bytes(b).hex()


def _ghex(lv):
    b = bytearray(120)
    b[64], b[65], b[66], b[67], b[68] = 7, lv, 0xAB, 0xCD, 0xEF
    return bytes(b).hex()


IL_HEAD = "_row,ItemCode,ItemName,RequiredLevel,RequiredLevelMax,UsageCategory,TradableFlag,Price,DataHex"
SH_PRICES = [(30000, 100), (30001, 500), (30002, 300), (30003, 900), (30004, 50), (30005, 70), (30006, 40), (30007, 45)]


def _item_list_csv():
    """item_list.csv: строки магазинов (selftest_shops) + предметы А4.4, колонки и DataHex согласованы."""
    import selftest_shops_sandbox as X
    rows = [IL_HEAD]
    for i, (c, p) in enumerate(SH_PRICES):
        rows.append("%d,%d,x%d,1,150,0,0,%d,%s" % (i, c, c, p, X._hexprice(p)))
    for j, (c, v) in enumerate(sorted(ITEMS.items())):
        rows.append("%d,%d,i%d,%d,%d,%d,%d,10,%s" % (len(SH_PRICES) + j, c, c, v[2], v[3], v[4], v[6], _ihex(v)))
    return ("\r\n".join(rows) + "\r\n").encode("utf-8")


def _sowell_csv():
    return ("_row,Id,Name,RequiredLevel,DataHex\r\n" + "".join("%d,%d,g%d,%d,%s\r\n" % (i, c, c, lv, _ghex(lv))
                                                               for i, (c, lv) in enumerate(sorted(GEMS.items())))).encode("utf-8")


def _cards():
    from domains.cs_kinds import itemdata as I
    from domains import shopdata as SD
    il = {r["ItemCode"]: r for r in SD._csv_rows(_item_list_csv())[2]}
    return {int(c): I.card_of(il[str(c)]) for c in ITEMS}, {c: [i, lv, struct.unpack_from("<i", bytes.fromhex(_ghex(lv)), 65)[0]]
                                                          for i, (c, lv) in enumerate(sorted(GEMS.items()))}


def _ev(items):
    from domains import shopdata as SD
    return SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False).run()


def _tok(raw, code, k):
    for ln in raw.split(b"\r\n")[1:]:
        f = ln.split(b"\t")
        if f and f[0].strip() == str(code).encode():
            return f[k]
    return None


def _fake_held(held=None, fail=False):
    def h(codes, stack=None):
        if fail:
            h.last_error = "нет связи с Joy1 (самотест)"
            return None
        return {int(c): dict((HELD if held is None else held).get(int(c), {"rows": 0, "amount": 0, "max": 0, "stack": False, "where": {}})) for c in codes}
    h.last_error = None
    return h


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check):
    import selftest_shops as T
    from core import config, i18n
    from domains import shopdata as SD, shopview
    from domains.cs_kinds import itemdata as I
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    if SD.DECODER_DIR not in sys.path:
        sys.path.insert(0, SD.DECODER_DIR)
    import decode_item_db as D
    vo_sw = os.path.join(SD.LEDGER_ROOT, "_value_overlay", "sowell_list.csv")
    check("А4.4 реестр: область «itemdata» седьмой (за ней — «Задания» А4.5), виды item.set / gem.level, права data.edit / data.apply, гейт баланса; item_table и "
          "Cellob_Table — политика same; выкладчик пускает Cellob_Table во всех GS; ведомость sowell_list — в движке, в реестре декодера "
          "(value_ledger) и на диске (шапка)",
          SD.AREAS[SD.AREAS.index(I)] is I and SD.AREAS.index(I) == 6       # ★ А4.5: после «Предметов» — «Задания»
          and set(I.KINDS) == {"item.set", "gem.level"} and SD.area_perm("item.set", "apply") == "data.apply"   # ★ ревизия 39 Н-1: было закомментировано
          and SD.area_perm("gem.level", "edit") == "data.edit" and I.BALANCE_GATE and SD.SRV_POLICY["ItemTable_Info\\Cellob_Table.txt"] == "same"
          and all(g + BS + CEL_REL in dc.ALLOWED and g + BS + IT_REL in dc.ALLOWED for g in GS3)
          and SD.LEDGER_TABLES.get("sowell_list") == "sowell_list.bin" and D.REGISTRY["sowell_list.bin"].get("value_ledger") == "sowell_list.csv"
          and os.path.isfile(vo_sw) and open(vo_sw, encoding="utf-8").read().startswith("row,column,was,now,source,reason"))
    lf = D.REGISTRY["item_list.bin"]["ledger_fields"]
    check("А4.4 раскладка: поля ведомости без колонки CSV совпадают с реестром декодера (Field68 +68, Weight +72), колонки — с cols "
          "(RequiredLevel +80, RequiredLevelMax +84, UsageCategory +92, TradableFlag +152)",
          lf["Field68"] == (68, "i32") and lf["Weight"] == (72, "i32") and all(
              (I.FIELDS[n][5], "i32", I.FIELDS[n][4]) in D.REGISTRY["item_list.bin"]["cols"] for n in ("lvl_min", "lvl_max", "job", "stack"))
          and (65, "u8", "RequiredLevel") in D.REGISTRY["sowell_list.bin"]["cols"])
    bad = []
    for kind, p in (("item.set", {"code": 31000}), ("item.set", {"code": 31000, "fields": {}}), ("item.set", {"code": 31000, "fields": {"price": 5}}),
                    ("item.set", {"code": 31000, "fields": {"weight": 0}}), ("item.set", {"code": 31000, "fields": {"stack": 2}}),
                    ("item.set", {"code": 7001, "fields": {"weight": 3}}), ("item.set", {"code": 31000, "fields": {"weight": ""}}),
                    ("gem.level", {"code": 20551, "level": 1}), ("gem.level", {"code": 7001, "level": 256})):
        try:
            SD.norm(kind, p)
            bad.append(p)
        except Exception:
            pass
    check("А4.4 позиции: неверные параметры — отказ (нет полей, неизвестное поле, вес 0, стопка 2, код < 20551, только пустые поля, "
          "самоцвет вне 7001…20550, уровень > 255); пустое поле — «не менять»", not bad and
          SD.norm("item.set", {"code": 31000, "fields": json.dumps({"weight": 700, "job": ""})})["fields"] == {"weight": 700}, bad)
    saved_held = SD.held_counts
    with T.synthetic() as (raw, md5, cli):
        for rel, b in stack_files().items():
            raw[rel], md5[rel] = b, _md5(b)
        cli.itemcard, cli.gemcard = _cards()
        SD.held_counts = _fake_held()
        try:
            _offline_kinds(check, raw, md5, cli)
            _plan(check, cli)
            # расхождения и справка
            cli.itemcard[31006] = list(cli.itemcard[31006])
            cli.itemcard[31006][3] = 7
            d = SD.divergence(areas=("itemdata",))
            sec = next((s for s in d["sections"] if s["key"] == "items"), None)
            check("А4.4 расхождения: раздел «items» — поле сервер ≠ клиент (мин. уровень 31006: сервер 1, клиент 7)",
                  [x["key"] for x in d["sections"]] == ["items"] and sec and any(r["code"] == 31006 and r["server"] == 1 and r["client"] == 7 for r in sec["rows"]),
                  sec and sec["rows"][:3])
            cli.itemcard[31006][3] = 1
            lk = shopview.lookup("item", "31001")
            lg = shopview.lookup("gem", "7001")
            fnd = shopview.lookup("items", "31001")
            check("А4.4 справка: карточка 31001 (3 GS, клиент, сумка 2, стопка, «на руках» 900 шт.), самоцвет 7001 (уровень 5 у сервера и "
                  "клиента), поиск; нечисловой код — отказ 409", lk["plate"] == 2 and lk["server"]["Indun_GameServer"]["weight"] == 23
                  and lk["client"]["stack"] == 1 and lk["held"]["amount"] == 900 and lg["server"]["GameServer"] == 5 and lg["client"] == 5
                  and isinstance(fnd["rows"], list) and _raises(lambda: shopview.lookup("item", "x")), (lk.get("held"), lg))
        finally:
            SD.held_counts = saved_held
    _held_real(check)                                  # настоящий held_counts (подмена снята)
    # переводы службы
    samples = ["золото 20551 не правится: одна строка на персонажа (Plate 2, вес 0), её ищут процедуры покупки",
               "смена стопки кода, который есть у игроков (записей 3, сумма Amount 900, наибольшая стопка 600 (Item 2, ItemPostBox 1)): у "
               "штучных Amount = 0, у стопок — количество, строки Joy1 панель не переписывает — после правки они значили бы другое (дюп или "
               "потеря), правка не делается",
               "вес стопочного предмета: на руках стопка 600 шт., 600 × 60 = 36000 > 32767 — вес строки переполнит SMALLINT Item.Weight "
               "(UPItemPick / UPBuyitem прибавляют n × вес) и i16 клиента (отрицательный вес — перегруз без предела), правка не делается",
               "предмет Броня (31000): полей 3 (сервер item_table ×3 GS, клиент item_list + ведомость)",
               "вес единицы: 683 → 700", "предмет Броня (31000): вес единицы", "самоцвет Камень (7001): мин. уровень",
               "позиция 1: требование класса 7 не встречается у предметов типа 1 (есть: 1, 12) — смысл не подтверждён, правка не делается",
               "предметы: поля сервер ≠ клиент (прочность, вес, уровни, класс, стопка, уровень самоцвета)", "Предмет: поля карточки (item_table + item_list)",
               # ★ ревизия 36
               "позиция 1: стопка у предмета с ток.3 = 1 и ток.24 = 1: сервер считает стопкой только ток.3 = 4 и ток.24 = 1 (sub_469010, "
               "sub_4D6CE0 и др.), а создание строки (sub_5340B0) смотрит один ток.23 — количество в памяти сервера, в пакете и в Joy1 "
               "разошлось бы, смысл не подтверждён, правка не делается",
               "вес стопочного предмета, который есть у игроков (записей 3, сумма Amount 900, наибольшая стопка 600 (Item 2, ItemPostBox 1)): "
               "Item.Weight строки = количество × прежний вес, а сервер списывает расход по новому весу (sub_53CC30, sub_55F050) — вес строки "
               "ушёл бы в минус (перегруз без предела) или остался бы завышенным, строки Joy1 панель не переписывает, правка не делается",
               "вес стопочного предмета — сильная правка: предела стопки на сервере нет (sub_5340B0 и sub_4D6CE0 складывают без проверки), "
               "стопка больше 655 шт. переполнит SMALLINT Item.Weight (n × вес 50 > 32767)",
               "после проверки набора у игроков появились коды со сменой стопки или веса стопки (31002 — записей 2, сумма Amount 0, "
               "наибольшая стопка 0 (Item 2)): строки Joy1 после рестарта значили бы другое (дюп или потеря) — выкладка не делается, стойка "
               "не тронута, объявления не было",
               "после выкладки у игроков есть коды со сменой стопки или веса стопки (31002 — записей 3, сумма Amount 40, наибольшая стопка 20 "
               "(Item 3)): после отката строки Joy1 значили бы другое (стопка стала бы штучной вещью или наоборот, вес строки разошёлся бы) — "
               "нужно второе подтверждение владельца (ключ --held-ok)",
               "мин. уровень 151 больше макс. 150: клиент не даст применить ни на каком уровне, а сервер (sub_4CDAA0) пустит уровни выше "
               "макс. — клиент и сервер разошлись бы, правка не делается",
               "изменены после применения: port/x.csv — откат вручную, ни один файл не записан"]
    i18n.set_lang("en")
    try:
        tr = [i18n.tr(x) for x in samples]
    finally:
        i18n.set_lang("ru")
    check("А4.4 переводы службы: тексты позиций, отказов и баланса переводятся (EN)",
          all(a != b and not re.search("[А-Яа-я]{4}", b.replace("Броня", "").replace("Камень", "")) for a, b in zip(samples, tr)), tr)
    # веб: переводы и подключение
    web = os.path.join(SD.ROOT, "web")
    js = open(os.path.join(web, "itemdata.js"), encoding="utf-8").read()
    ij = open(os.path.join(web, "i18n.js"), encoding="utf-8").read()
    need = sorted(set(re.findall(r'(?:T\(|h\("[a-z0-9]+", (?:null|\{[^}]*\}), )"([^"]*[А-Яа-яЁё][^"]*)"', js)))
    miss = [s for s in need if '"%s":' % s.replace("\\", "\\\\") not in ij]
    check("А4.4 веб: itemdata.js подключён (index.html, вкладка в shops.js), у строк интерфейса есть EN (i18n.js)",
          "/itemdata.js" in open(os.path.join(web, "index.html"), encoding="utf-8").read()
          and "#/shops/items" in open(os.path.join(web, "shops.js"), encoding="utf-8").read() and not miss, miss[:6])


def _raises(fn):
    try:
        fn()
    except Exception:
        return True
    return False


class _FakeCur:
    """Подставной курсор pyodbc для shopdata.held_counts: sys.columns, dbo.<таблица>, adm.ItemTaken + ItemLedger, GP7GiftLog."""

    def __init__(self, db, data):
        self.db, self.data, self.description, self._r = db, data, None, []

    def execute(self, sql, *params):
        d = self.data
        if "FROM sys.columns" in sql:
            cols = d["schema"].get(params[0], [])
            self.description, self._r = [("name",)], [(c,) for c in cols]
            return
        codes = {int(x) for x in re.search(r"IN \(([\d,]+)\)", sql).group(1).split(",")}
        agg = {}
        m = re.search(r"FROM dbo\.(\w+) WHERE Code IN", sql)
        if m:
            src = [(c, a) for c, a in d["rows"].get(m.group(1), [])]
        elif "adm.ItemTaken" in sql:
            src = [(c, a) for c, a, undone in d["taken"] if undone is None]
        else:
            k = int(re.search(r"SELECT code(\d) AS Code", sql).group(1))
            src = [(codes7[k - 1], 0) for state, codes7 in d["gp7"] if state == "H" and codes7[k - 1]]
        for c, a in src:
            if c in codes:
                n, s, mx = agg.get(c, (0, 0, 0))
                agg[c] = (n + 1, s + a, max(mx, a))
        self.description = [("Code",), ("n",), ("a",), ("mx",)]
        self._r = [(c, n, s, mx) for c, (n, s, mx) in sorted(agg.items())]

    def fetchall(self):
        return self._r


class _FakeCn:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def cursor(self):
        return _FakeCur(self.name, self.data)

    def close(self):
        pass


def _held_real(check):
    """★ ревизия 36 М-2: НАСТОЯЩИЙ shopdata.held_counts на подставной базе — Item, Exitem, ItemPostBox, gifts, неоткаченные ItemTaken,
    GP7GiftLog 'H' (code1…code7); нет столбца — «не прочитано» (None с причиной), а не тихий пропуск."""
    from core import db
    from domains import shopdata as SD
    item_cols = ["Code", "Amount", "Weight"]
    data = {"schema": {"dbo.Item": item_cols, "dbo.Exitem": item_cols, "dbo.ItemPostBox": item_cols, "dbo.gifts": ["Code", "Amount"],
                       "adm.ItemTaken": item_cols + ["LedgerId"], "adm.ItemLedger": ["Id", "UndoneBy"],
                       "dbo.GP7GiftLog": ["state"] + ["code%d" % k for k in range(1, 8)]},
            "rows": {"Item": [(31001, 20)], "Exitem": [], "ItemPostBox": [], "gifts": [(31002, 1)]},
            "taken": [(31007, 0, None), (31007, 0, 5), (31001, 30, None)],
            "gp7": [("H", [31008, 0, 0, 0, 0, 0, 0]), ("C", [31008, 0, 0, 0, 0, 0, 0]), ("H", [0, 0, 31001, 0, 0, 0, 0])]}
    saved = db._override.get("game")
    db.set_override("game", lambda name: _FakeCn(name, data))
    try:
        h = SD.held_counts([31001, 31002, 31007, 31008, 31009])
        data["schema"]["dbo.gifts"] = ["Code"]
        h2 = SD.held_counts([31001])
        err2 = SD.held_counts.last_error
    finally:
        db.set_override("game", saved)
    ok = (h is not None and h[31001]["rows"] == 3 and h[31001]["amount"] == 50 and h[31001]["max"] == 30
          and h[31001]["where"] == {"Item": 1, "ItemTaken": 1, "GP7GiftLog": 1}
          and h[31002]["where"] == {"gifts": 1} and h[31007]["where"] == {"ItemTaken": 1} and h[31008]["where"] == {"GP7GiftLog": 1}
          and h[31009]["rows"] == 0)
    check("«на руках» (ревизия 36 М-2): НАСТОЯЩИЙ held_counts считает Item, отложенные подарки gifts, только неоткаченные снимки "
          "ItemTaken (UndoneBy IS NULL), только подарки GP7 в состоянии 'H' по code1…code7; у таблицы нет столбца Amount — «не прочитано» "
          "с причиной", ok and h2 is None and err2 and "dbo.gifts" in err2, (h, h2, err2))


def _offline_kinds(check, raw, md5, cli):
    from domains import shopdata as SD
    from domains.cs_kinds import itemdata as I
    ev = _ev([("item.set", {"code": 31000, "fields": {"weight": 700, "durability": 60, "lvl_min": 2}})])
    nb = ev.new_bytes()
    r = ev.positions[0]
    g = nb.get("GameServer" + BS + IT_REL, b"")
    line_old = [ln for ln in raw["GameServer" + BS + IT_REL].split(b"\r\n") if ln.startswith(b"31000")][0]
    line_new = [ln for ln in g.split(b"\r\n") if ln.startswith(b"31000")][0]
    diff = [k for k, (a, b) in enumerate(zip(line_old.split(b"\t"), line_new.split(b"\t"))) if a != b]
    types = [(e["type"], e.get("col"), e.get("off")) for e in ev.client]
    check("item.set броня 31000 (вес 683 → 700, прочность 50 → 60, мин. уровень 1 → 2): ток.1/2/4 во всех 3 GS, пробелы полей как "
          "были, прочие токены нетронуты; клиент — DataHex +68 / +72, RequiredLevel + DataHex +80; баланс ×2 не превышен",
          not ev.errors and len(nb) == 3 and diff == [1, 2, 4] and line_new.split(b"\t")[2] == b"700 "
          and types == [("csv_hex_i32", "DataHex", 68), ("csv_hex_i32", "DataHex", 72), ("csv_cell", "RequiredLevel", None),
                        ("csv_hex_i32", "DataHex", 80)] and not any(b["strong"] for b in ev.balance) and len(r["lines"]) == 3
          and r["lines"][1] == "вес единицы: 683 → 700", (ev.errors, types, diff))
    ev = _ev([("item.set", {"code": 31000, "fields": {"weight": 2000}}), ("item.set", {"code": 31006, "fields": {"job": 1}})])
    kinds = sorted((b["kind"], b["strong"]) for b in ev.balance)
    check("item.set: вес ×2.9 — сильная правка (value), смена требования класса 12 → 1 — сильная всегда (kind type)",
          not ev.errors and kinds == [("type", True), ("value", True)], (ev.errors, kinds))
    cases = [
        ("класс не встречается у типа", ("item.set", {"code": 31000, "fields": {"job": 7}}), "не встречается у предметов типа 1"),
        ("класс оружия не 40…44", ("item.set", {"code": 31004, "fields": {"job": 3}}), "только 40…44"),
        ("прочность 0 у снаряжения", ("item.set", {"code": 31000, "fields": {"durability": 0}}), "код 20"),
        ("стопка у сумки 1", ("item.set", {"code": 31000, "fields": {"stack": 1}}), "сумки 1"),
        ("стопка у контейнера", ("item.set", {"code": 31003, "fields": {"stack": 0}}), "контейнера типа 10"),
        ("стопка кода на руках (дюп)", ("item.set", {"code": 31001, "fields": {"stack": 0}}), "дюп или потеря"),
        ("вес стопки на руках (М-1)", ("item.set", {"code": 31001, "fields": {"weight": 24}}), "который есть у игроков (записей 3"),
        ("стопка вкл. при ток.3 ≠ 4 (Б-2, как 23690)", ("item.set", {"code": 31007, "fields": {"stack": 1}}), "ток.3 = 1 и ток.24 = 1"),
        ("стопка выкл. у полустопки (Б-2, как 20826)", ("item.set", {"code": 31008, "fields": {"stack": 0}}), "ток.3 = 0 и ток.24 = 1"),
        ("мин. > макс. (К-2)", ("item.set", {"code": 31000, "fields": {"lvl_min": 151}}), "больше макс. 150"),
        ("мин. > макс. обоими полями (К-2)", ("item.set", {"code": 31000, "fields": {"lvl_min": 20, "lvl_max": 10}}), "разошлись бы"),
        ("золото", ("item.set", {"code": 20551, "fields": {"weight": 2}}), "золото 20551"),
        ("нет карточки клиента", ("item.set", {"code": 30000, "fields": {"weight": 2}}), "нет в item_list клиента"),
        ("менять нечего", ("item.set", {"code": 31000, "fields": {"weight": 683}}), "менять нечего"),
        ("нет самоцвета", ("gem.level", {"code": 7003, "level": 9}), "нет в sowell_list"),
    ]
    bad = []
    for label, (k, p), want in cases:
        e = _ev([(k, p)])
        if not any(want in x for x in e.errors):
            bad.append((label, e.errors[:2]))
    check("item.set / gem.level: %d отказов «дюп и целостность» и «только существующие» (класс, оружие, прочность 0, стопка сумки 1 / "
          "контейнера / на руках, вес стопки на руках, стопка у ток.3 ≠ 4 в обе стороны, мин. > макс., золото, нет карточки, менять "
          "нечего, нет самоцвета)" % len(cases), not bad, bad)
    e = _ev([("item.set", {"code": 31002, "fields": {"stack": 1}})])
    b = e.balance[0] if e.balance else {}
    s = e.summary()
    check("item.set: стопка штучного расходника (ток.3 = 4, ток.24 = 1), которого нет на руках, — можно; сильная правка (kind stack), "
          "клиент TradableFlag; в итоге проверки guard «stack» для перепроверки при выкладке и откате (ревизия 36 Б-1)",
          not e.errors and b.get("kind") == "stack" and b.get("strong") and any(x.get("col") == "TradableFlag" for x in e.client)
          and s["positions"][0].get("guard") == [{"code": 31002, "why": "stack"}], (e.errors, s["positions"][0].get("guard")))
    keep = SD.held_counts
    SD.held_counts = _fake_held({})
    e = _ev([("item.set", {"code": 31001, "fields": {"weight": 50}})])
    SD.held_counts = keep
    b = e.balance[0] if e.balance else {}
    check("item.set: вес стопки 23 → 50 без экземпляров на руках — можно, но сильная правка (kind stackweight, ×2.2 и без порога) с "
          "пояснением «предела стопки на сервере нет … больше 655 шт.», guard «weight» (ревизия 36 М-1, М-4)",
          not e.errors and b.get("kind") == "stackweight" and b.get("strong")
          and any("предела стопки на сервере нет" in w and "больше 655" in w for w in e.positions[0]["warnings"])
          and e.summary()["positions"][0].get("guard") == [{"code": 31001, "why": "weight"}], (e.errors, b))
    SD.held_counts = _fake_held({})
    e = _ev([("item.set", {"code": 31001, "fields": {"weight": 24}})])
    SD.held_counts = keep
    b = e.balance[0] if e.balance else {}
    check("item.set: вес стопки 23 → 24 (меньше ×2) — всё равно сильная (kind stackweight, ревизия 36 М-4)",
          not e.errors and b.get("kind") == "stackweight" and b.get("strong"), (e.errors, b))
    e = _ev([("item.set", {"code": 31000, "fields": {"lvl_min": 2, "job": 12}})])
    ws = e.positions[0]["warnings"]
    check("item.set: уровни и класс у вещи на руках — предупреждение «на руках … требование проверяется при надевании» (одно на "
          "позицию, ревизия 36 К-1)", not e.errors and sum("требование проверяется при надевании" in w and "записей 1" in w for w in ws) == 1,
          (e.errors, ws))
    SD.held_counts = _fake_held(fail=True)
    e1 = _ev([("item.set", {"code": 31002, "fields": {"stack": 1}})])
    e2 = _ev([("item.set", {"code": 31001, "fields": {"weight": 24}})])
    e3 = _ev([("item.set", {"code": 31000, "fields": {"weight": 690}})])
    SD.held_counts = keep
    check("item.set: «на руках» не прочитано — смена стопки и вес стопочного предмета отказ (вслепую не делается); вес штучного — "
          "предупреждение", any("не прочитано" in x for x in e1.errors) and any("не прочитано" in x for x in e2.errors) and not e3.errors
          and any("не прочитано" in w for w in e3.positions[0]["warnings"]), (e1.errors, e2.errors, e3.errors))
    c = cli.itemcard[31000]
    cli.itemcard[31000] = c[:7] + ["RequiredLevel"]
    e = _ev([("item.set", {"code": 31000, "fields": {"weight": 690}})])
    cli.itemcard[31000] = c
    check("item.set: колонка клиента ≠ DataHex — ошибка «строка клиента не согласована»", any("не согласована" in x for x in e.errors), e.errors)
    e = _ev([("gem.level", {"code": 7001, "level": 9})])
    nb = e.new_bytes()
    ed = [x for x in e.client if x["type"] == "csv_hex_i32"][0]
    check("gem.level 7001 (5 → 9): Cellob ток.16 во всех 3 GS, клиент RequiredLevel + DataHex +65 (соседние байты сохранены), "
          "предупреждение о вставленных самоцветах", not e.errors and len(nb) == 3
          and _tok(nb["Indun_GameServer" + BS + CEL_REL], 7001, 16) == b"9 " and ed["off"] == 65 and ed["new"] & 0xFF == 9
          and ed["new"] >> 8 == ed["old"] >> 8 and any("код 14" in w for w in e.positions[0]["warnings"]), e.errors)
    # копии item_table GS разные (политика same) — отказ движка «правка вслепую запрещена»
    rel = "Ch2_GameServer" + BS + IT_REL
    keep_raw, keep_md5 = raw[rel], md5[rel]
    raw[rel] = keep_raw.replace(b"31002 	0 	5 ", b"31002 	0 	6 ")
    md5[rel] = _md5(raw[rel])
    e = _ev([("item.set", {"code": 31000, "fields": {"lvl_max": 140}})])
    raw[rel], md5[rel] = keep_raw, keep_md5
    check("item.set: item_table на GameServer стойки разные (у Ch2 другой вес 31002) — «правка вслепую запрещена»",
          raw[rel] != keep_raw.replace(b"31002 	0 	5 ", b"31002 	0 	6 ") and any("вслепую" in x for x in e.errors), e.errors[:2])


def _plan(check, cli):
    """План клиента на временных копиях: item_list (поля ведомости без колонки и колонки) и sowell_list; хвост; потеря правки."""
    from core import config
    from domains import shopdata as SD
    import selftest_shops as T
    d = tempfile.mkdtemp(prefix="asda_cs_a44_")
    saved = dict(SD.CLIENT_FILES)
    cfg = config.get()
    was = cfg.on_server
    cfg.on_server = False
    try:
        il, sw = os.path.join(d, "item_list.csv"), os.path.join(d, "sowell_list.csv")
        open(il, "wb").write(_item_list_csv())
        open(sw, "wb").write(_sowell_csv())
        SD.CLIENT_FILES.update({"item_list": il, "sowell_list": sw})
        before = {p: _md5(open(p, "rb").read()) for p in (il, sw)}
        ev = _ev([("item.set", {"code": 31000, "fields": {"weight": 700, "durability": 60, "lvl_min": 5}}),
                  ("gem.level", {"code": 7001, "level": 9})])
        plan = SD.client_plan(ev.client, 101)
        b = plan["_bytes"]
        row = [r for r in SD._csv_rows(b[il])[2] if r["ItemCode"] == "31000"][0]
        hx = bytes.fromhex(row["DataHex"])
        vo = b.get(SD.ledger_paths("item_list")[0], b"").decode("utf-8")
        vs = b.get(SD.ledger_paths("sowell_list")[0], b"").decode("utf-8")
        srow = [r for r in SD._csv_rows(b[sw])[2] if r["Id"] == "7001"][0]
        check("план клиента А4.4: item_list — RequiredLevel 5 и байты +68/+72/+80; ведомость _value_overlay/item_list.csv — строки "
              "Field68 50→60, Weight 683→700 (поля без колонки — по имени поля) и RequiredLevel 1→5; sowell_list — RequiredLevel 9 и +65, "
              "ведомость sowell_list; DT_item_list и DT_sowell_list; файлы не изменились",
              not plan["errors"] and row["RequiredLevel"] == "5" and [struct.unpack_from("<i", hx, o)[0] for o in (68, 72, 80)] == [60, 700, 5]
              and ",Field68,50,60," in vo and ",Weight,683,700," in vo and ",RequiredLevel,1,5," in vo and ",RequiredLevel,5,9," in vs
              and srow["RequiredLevel"] == "9" and bytes.fromhex(srow["DataHex"])[65:69] == bytes([9, 0xAB, 0xCD, 0xEF])
              and sorted(j["dt"].rsplit("/", 1)[1] for j in plan["dt_jobs"]) == ["DT_item_list", "DT_sowell_list"]
              and before == {p: _md5(open(p, "rb").read()) for p in (il, sw)}, (plan["errors"], vo[-300:]))
        # раскладка генератора без поля Weight: строки ведомости нет — генератор вернул бы прежний DataHex → отказ, а не тихая потеря
        keep = SD.itemdb_cols
        SD.itemdb_cols = lambda key: {k: v for k, v in T.FAKE_COLS.get(key, {}).items() if k != "Weight"}
        pb = SD.client_plan(_ev([("item.set", {"code": 31000, "fields": {"weight": 700}})]).client, 102)
        SD.itemdb_cols = keep
        check("план клиента А4.4: поле без колонки, которого нет в раскладке генератора, — отказ «правка потерялась бы при перегенерации»",
              any("потерялась бы" in x for x in pb["errors"]), pb["errors"])
        # строка хвоста _tail_append: правится на месте (колонка и DataHex), _value_overlay не пишется
        ta = SD.ledger_paths("item_list")[1]
        r2 = [r for r in SD._csv_rows(_item_list_csv())[2] if r["ItemCode"] == "31002"][0]
        open(ta, "w", encoding="utf-8", newline="").write(IL_HEAD + ",_source\r\n" + ",".join(r2[c] for c in IL_HEAD.split(",")) + ",самотест\r\n")
        pt = SD.client_plan(_ev([("item.set", {"code": 31002, "fields": {"lvl_min": 3, "weight": 6}})]).client, 103)
        tl = pt["_bytes"].get(ta, b"").decode("utf-8").split("\r\n")[1].split(",")
        os.remove(ta)
        check("план клиента А4.4: строка из хвоста — правится в ведомости хвоста на месте (RequiredLevel и DataHex с весом), "
              "_value_overlay не пишется", not pt["errors"] and tl[3] == "3" and struct.unpack_from("<i", bytes.fromhex(tl[8]), 72)[0] == 6
              and struct.unpack_from("<i", bytes.fromhex(tl[8]), 80)[0] == 3
              and SD.ledger_paths("item_list")[0] not in pt["files"], (pt["errors"], tl))
    finally:
        cfg.on_server = was
        SD.CLIENT_FILES.clear()
        SD.CLIENT_FILES.update(saved)
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox(check, ldb):
    """Набор «Предметы» целиком: пара сервер + клиент, второе подтверждение сильной правки, выкладка и откаты."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs, shopdata as SD
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    saved_held = SD.held_counts
    with X.sandbox(ldb) as (st, env):
        SD.held_counts = _fake_held()
        try:
            files = stack_files()
            for rel, b in files.items():
                p = st.path(rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(b)
            cdir = os.path.join(env["tmp"], "a44")
            os.makedirs(cdir)
            il, sw = SD.CLIENT_FILES["item_list"], os.path.join(cdir, "sowell_list.csv")
            open(il, "wb").write(_item_list_csv())
            open(sw, "wb").write(_sowell_csv())
            SD.CLIENT_FILES["sowell_list"] = sw
            for k in ("item_list", "sowell_list"):
                st.assets[SD.DT[k]] = open(SD.CLIENT_FILES[k], "rb").read()
            orig = {p: open(p, "rb").read() for p in (il, sw)}
            items = [("item.set", {"code": 31000, "fields": {"weight": 700, "lvl_min": 5}}), ("gem.level", {"code": 7001, "level": 9}),
                     ("item.set", {"code": 31002, "fields": {"stack": 1}})]
            cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.4", note="самотест песочницы А4.4: предметы")["result"]["id"]
            for kind, prm in items:
                X._run(ctx, "shop.cs_item_add", cs=cid, kind=kind, params=prm)
            X._run(ctx, "shop.cs_check", cs=cid)
            cs = shopcs.get(cid)
            _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
            adm = ops.Ctx(7, "adm", "admin", "100.64.0.9", "web")
            _r, adm_no = X._try(adm, "shop.cs_approve", cs=cid, balance_ok="balance")
            X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
            check("песочница А4.4: пара (сервер и клиент), сильная правка (стопка) — без второго подтверждения отказ с «на руках», admin с "
                  "ключом — отказ «только владелец», владелец — утверждён", cs["check"]["ok"] and cs["check"]["client_needed"]
                  and cs["check"]["server_needed"] and no and "второе подтверждение" in no and "на руках" in no and adm_no
                  and "только владелец" in adm_no and shopcs.get(cid)["status"] == "approved", (cs["check"]["errors"], no, adm_no))
            X._run(ctx, "shop.cs_server_dry", cs=cid)
            man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
            check("песочница А4.4: сухой прогон НАСТОЯЩЕГО deploy_changeset — 6 файлов (item_table ×3, Cellob_Table ×3)",
                  shopcs.get(cid)["server_state"] == "dry_ok"
                  and sorted(man["files"]) == sorted(r for r in files if r.endswith((IT_REL, CEL_REL))), sorted(man["files"]))   # ★ р.37: прочие — пустые
            X._run(ctx, "shop.cs_client_dry", cs=cid)
            X._run(ctx, "shop.cs_client_apply", cs=cid)
            vo = open(SD.ledger_paths("item_list")[0], encoding="utf-8").read()
            vs = open(SD.ledger_paths("sowell_list")[0], encoding="utf-8").read()
            check("песочница А4.4: клиент — item_list.csv и sowell_list.csv записаны, ведомости item_list (Weight, RequiredLevel, "
                  "TradableFlag) и sowell_list, DT_item_list и DT_sowell_list залиты через очередь UE", shopcs.get(cid)["client_state"] == "applied"
                  and ",Weight,683,700," in vo and ",RequiredLevel,1,5," in vo and ",TradableFlag,0,1," in vo and ",RequiredLevel,5,9," in vs
                  and st.assets[SD.DT["item_list"]] == open(il, "rb").read() and st.assets[SD.DT["sowell_list"]] == open(sw, "rb").read(),
                  (vo[-200:], shopcs.get(cid)["client_state"]))
            # ★ ревизия 36 М-3: откат клиента — сначала md5 ВСЕХ файлов: чужая правка последнего файла плана — отказ, ни один не записан
            cb = shopcs.get(cid)["client_backup"]
            pl = json.load(open(os.path.join(cb, "client_plan.json"), encoding="utf-8"))["files"]
            last = list(pl)[-1]
            keep_last = open(last, "rb").read()
            open(last, "ab").write(b"#foreign")
            _r, e_m3 = X._try(ctx, "shop.cs_client_rollback", cs=cid)
            same = all(SD.md5f(p) == v["new"] for p, v in pl.items() if p != last)
            open(last, "wb").write(keep_last)
            check("песочница А4.4 (ревизия 36 М-3): откат клиента при чужой правке последнего файла плана (%s) — отказ «ни один файл не "
                  "записан», остальные %d файлов остались применёнными, состояние applied" % (os.path.basename(last), len(pl) - 1),
                  e_m3 and "ни один файл не записан" in e_m3 and same and shopcs.get(cid)["client_state"] == "applied", e_m3)
            # ★ ревизия 36 М-3: применение — сначала md5 ВСЕХ файлов = «было» плана (подставной план: второй файл устарел)
            a_il = open(il, "rb").read()
            fake_plan = {"files": {il: {"old": SD.md5b(a_il), "new": SD.md5b(b"x")}, sw: {"old": "0" * 32, "new": SD.md5b(b"y")}},
                         "_bytes": {il: b"x", sw: b"y"}, "dt_jobs": [], "importers": []}
            try:
                shopcs.client_write({"id": 0}, fake_plan, os.path.join(env["tmp"], "m3_apply"))
                e_m3a = None
            except Exception as ex:
                e_m3a = str(ex)
            check("песочница А4.4 (ревизия 36 М-3): применение клиента при устаревшем втором файле — отказ «ни один файл не записан» "
                  "до бэкапа и записи, первый файл не тронут", e_m3a and "ни один файл не записан" in e_m3a and open(il, "rb").read() == a_il
                  and not [f for _d, _s, fs in os.walk(os.path.join(env["tmp"], "m3_apply")) for f in fs], e_m3a)
            # ★ ревизия 36 Б-1: после проверки у игроков появились строки 31002 (стопка 0 → 1) — выкладка отказ ДО объявления
            SD.held_counts = _fake_held({31002: {"rows": 2, "amount": 0, "max": 0, "stack": False, "where": {"Item": 2}}})
            calls0 = len(st.calls)
            g0 = open(st.path("GameServer" + BS + IT_REL), "rb").read()
            _r, e_b1 = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            SD.held_counts = _fake_held(fail=True)
            _r, e_b1u = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            SD.held_counts = _fake_held()
            check("песочница А4.4 (ревизия 36 Б-1): у игроков появились строки кода со сменой стопки — выкладка сервера отказ «появились … "
                  "объявления не было» (рестарта не было, таблицы стойки прежние, состояние dry_ok); «на руках» не прочитано — тоже отказ",
                  e_b1 and "появились" in e_b1 and "31002 — записей 2" in e_b1 and e_b1u and "не прочитано" in e_b1u
                  and len(st.calls) == calls0 and open(st.path("GameServer" + BS + IT_REL), "rb").read() == g0
                  and shopcs.get(cid)["server_state"] == "dry_ok", (e_b1, e_b1u, st.calls[calls0:]))
            r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            g = open(st.path("Indun_GameServer" + BS + IT_REL), "rb").read()
            c = open(st.path("Ch2_GameServer" + BS + CEL_REL), "rb").read()
            check("песочница А4.4: серверная половина выложена рестартом — у всех GS вес 700, мин. уровень 5, стопка 31002, уровень "
                  "самоцвета 9", r and shopcs.get(cid)["server_state"] == "applied" and _tok(g, 31000, 2) == b"700 " and _tok(g, 31000, 4) == b"5 "
                  and _tok(g, 31002, 23) == b"1 " and _tok(c, 7001, 16) == b"9 ", e)
            # ★ ревизия 36 Б-1: игроки набрали стопки 31002 после выкладки — откат без --held-ok отказ, не прочитано — отказ и с ключом
            SD.held_counts = _fake_held({31002: {"rows": 3, "amount": 40, "max": 20, "stack": True, "where": {"Item": 3}}})
            calls0 = len(st.calls)
            _r, e_r1 = X._try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
            SD.held_counts = _fake_held(fail=True)
            _r, e_r2 = X._try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart", held_ok="held")
            SD.held_counts = _fake_held({31002: {"rows": 3, "amount": 40, "max": 20, "stack": True, "where": {"Item": 3}}})
            check("песочница А4.4 (ревизия 36 Б-1): откат сервера при стопках 31002 на руках — без второго подтверждения отказ «ключ "
                  "--held-ok» с показом «на руках», «не прочитано» — отказ и с ключом; рестарта не было, сервер applied",
                  e_r1 and "--held-ok" in e_r1 and "31002 — записей 3" in e_r1 and e_r2 and "не прочитано" in e_r2
                  and len(st.calls) == calls0 and shopcs.get(cid)["server_state"] == "applied", (e_r1, e_r2))
            rr = X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart", held_ok="held")
            SD.held_counts = _fake_held()
            check("песочница А4.4 (ревизия 36 Б-1): откат сервера владельцем с --held-ok — выполнен (rolled_back)",
                  shopcs.get(cid)["server_state"] == "rolled_back", rr.get("message") if isinstance(rr, dict) else rr)
            X._run(ctx, "shop.cs_client_rollback", cs=cid)
            back = all(open(st.path(rel), "rb").read() == b for rel, b in files.items()) and all(open(p, "rb").read() == b for p, b in orig.items())
            check("песочница А4.4: откат сервера и клиента — 6 таблиц стойки, item_list.csv и sowell_list.csv вернулись, ведомости убраны",
                  back and not os.path.isfile(SD.ledger_paths("item_list")[0]) and not os.path.isfile(SD.ledger_paths("sowell_list")[0]),
                  shopcs.get(cid)["client_state"])
        finally:
            SD.held_counts = saved_held


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны на живой стойке (SSH) и живом порту (настоящий генератор ItemDB)."""
    from core import config
    from domains import shopcs, shopdata as SD, srvtables
    from domains.cs_kinds import itemdata as I
    if config.get().on_server:
        return check("живой самотест А4.4 — с ПК (SSH и порт)", True)
    rels = [g + BS + r for g in GS3 for r in (IT_REL, CEL_REL)]
    md = SD.live_md5(rels)
    check("живая стойка А4.4: item_table и Cellob_Table во всех трёх GS одинаковы (политика same)",
          "none" not in md.values() and len({md[g + BS + IT_REL] for g in GS3}) == 1 and len({md[g + BS + CEL_REL] for g in GS3}) == 1,
          {r: h[:8] for r, h in md.items()})
    cli = SD.Client.load(force=True)
    it = srvtables.table("Item_Table.txt")
    # стопочный расходник сумки 2 и броня; «на руках» — из Joy1
    stk = next(c for c in sorted(cli.itemcard) if c in it and it[c][16] == "11" and it[c][23] == "1" and it[c][24] != "3" and c != 20551
               and int(it[c][2]) > 0 and not cli.itemcard[c][7])
    arm = next(c for c in sorted(cli.itemcard) if c in it and it[c][16] == "1" and int(it[c][2]) > 1 and not cli.itemcard[c][7]
               and int(it[c][1]) < 255 and int(it[c][4]) < 255
               and int(it[c][2]) == (cli.itemcard[c][2] & 0xFFFF) and int(it[c][1]) == cli.itemcard[c][1] and it[c][4] == str(cli.itemcard[c][3]))
    lk = I.lookup_item(arm)
    h = SD.held_counts([stk])
    check("живая справка А4.4: карточка брони %d (3 GS, клиент, сумка 1); «на руках» по стопочному %d из Joy1 прочитано (Item + Exitem + "
          "ItemPostBox, наибольшая стопка)" % (arm, stk), lk["plate"] == 1 and all(lk["server"].values()) and lk["client"]
          and h is not None and "max" in h[stk], (lk.get("held_error"), getattr(SD.held_counts, "last_error", None)))
    # ★ ревизия 36 М-2: живые неоткаченные снимки ItemTaken, отложенные подарки gifts и подарки GP7 'H' видны в «на руках»
    from core import db
    with db.GameReader("joy1") as j:
        tk = [int(r["Code"]) for r in j.rows("SELECT TOP 5 t.Code FROM adm.ItemTaken t JOIN adm.ItemLedger l ON l.Id = t.LedgerId "
                                             "WHERE l.UndoneBy IS NULL AND t.Code > 0")]
        gf = [int(r["Code"]) for r in j.rows("SELECT TOP 5 Code FROM dbo.gifts WHERE Code > 0")]
    with db.GameReader("asdastorylogin") as g:
        gp = [int(r["c"]) for r in g.rows("SELECT TOP 5 code1 AS c FROM dbo.GP7GiftLog WHERE state = 'H' AND code1 > 0")]
    hh = SD.held_counts(tk + gf + gp)
    check("живое «на руках» (ревизия 36 М-2): неоткаченные снимки ItemTaken %s, подарки gifts %s и GP7GiftLog 'H' %s прочитаны и видны "
          "в where" % (tk, gf, gp), hh is not None and all("ItemTaken" in hh[c]["where"] for c in tk) and all("gifts" in hh[c]["where"] for c in gf)
          and all("GP7GiftLog" in hh[c]["where"] for c in gp), (getattr(SD.held_counts, "last_error", None), hh))
    gem = next(c for c in sorted(cli.gemcard) if cli.gemcard[c][1] == (cli.gemcard[c][2] & 0xFF) and 0 < cli.gemcard[c][1] < 200)
    w = int(it[arm][2])
    items = [{"pos": 1, "kind": "item.set", "params": {"code": arm, "fields": {"weight": w + 1, "durability": int(it[arm][1]) + 1,
                                                                                 "lvl_min": int(it[arm][4]) + 1}}},
             {"pos": 2, "kind": "gem.level", "params": {"code": gem, "level": cli.gemcard[gem][1] + 1}}]
    sn = SD.Snap()
    ev = SD.Eval(items, False, sn, cli).run()
    s = ev.summary()
    check("живая оценка набора А4.4 (броня %d: вес/прочность/мин. уровень +1, самоцвет %d: уровень +1): без ошибок, сервер — 6 файлов"
          % (arm, gem), not s["errors"] and s["server"]["count"] == 6, s["errors"][:3])
    tracked = [p for p in list(SD.CLIENT_FILES.values()) + SD.all_ledger_paths() if os.path.isfile(p)]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0)
    after = {p: SD.md5f(p) for p in tracked}
    vo = plan["_bytes"].get(SD.ledger_paths("item_list")[0], b"").decode("utf-8")
    vs = plan["_bytes"].get(SD.ledger_paths("sowell_list")[0], b"").decode("utf-8")
    check("живой план клиента А4.4: НАСТОЯЩИЙ генератор ItemDB подтверждает ведомости item_list (Weight, Field68 — поля без колонки, "
          "RequiredLevel) и sowell_list; ничего не записано (md5 порта до = после)",
          not plan["errors"] and ",Weight,%d,%d," % (cli.itemcard[arm][2], cli.itemcard[arm][2] + 1) in vo and ",Field68," in vo
          and ",RequiredLevel," in vo and ",RequiredLevel," in vs and before == after, plan["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_a44_live_")
    try:
        man = {"tag": "20261120_a44live", "changeset": 0, "files": {}}
        for rel, data in sorted(ev.new_bytes().items()):
            lp = os.path.join(tmp, rel.replace(BS, os.sep))
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            open(lp, "wb").write(data)
            man["files"][rel] = {"local": lp.replace(BS, "/"), "base": ev.snap.md5[rel], "new": SD.md5b(data)}
        mp = os.path.join(tmp, "manifest.json")
        json.dump(man, open(mp, "w", encoding="utf-8"))
        b0 = SD.live_md5(sorted(man["files"]))
        rc, out = shopcs.run_deploy(mp)
        b1 = SD.live_md5(sorted(man["files"]))
        check("НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH (6 файлов: item_table ×3, Cellob_Table ×3): «всё готово к --apply», стойка не "
              "изменилась (md5 до = после)", rc == 0 and "всё готово" in out and b0 == b1, (rc, out[-400:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
