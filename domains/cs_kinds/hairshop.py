# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/hairshop.py — область «Парикмахерская 15000» (волна А4.1, 19.11.2026; разбор research_a4_data.md §1.8).

СЕРВЕР: ItemTable_Info\\HairTypeTable.txt во всех GS (sub_4B4970, GameServer.c:72264: число N, затем N записей ПОТОКОМ слов:
Id подряд +1 — иначе «Sync Error», имя одним словом, Gender, RequiredLevel, Enabled, Price (колонка 5 → +69 DWORD), HairStyle,
ColorIdx). Деньги списывает СЕРВЕР по своей цене, витрину рисует КЛИЕНТ — пара обязана совпадать (дефект D2,
Reports/npc_hairshop_30029.md). На dev 19.11 все три копии 8FDD73BB, клиент приведён к серверу asda_hairtable_sync.py.
КЛИЕНТ: RawAssets/Data/ItemDB/hairtable.csv (Price + DataHex +0x28 — одно поле записи, реестр decode_item_db 'hairtable.bin')
→ DT_hairtable (точечная заливка asda_ml_dt_point). ★ Правка цены пишется и в ВЕДОМОСТЬ _value_overlay/hairtable.csv (движок:
shopdata.ledger_plan; правило itemdb-ledger-overlays — так 31.08 потеряли цены причёсок). asda_hairtable_sync.py --apply
пересобирает эту ведомость целиком «архив → сервер»: после выкладки серверной половины его итог тот же.
Правка — только цена существующей причёски (решение владельца 19.11: без новых записей); применяется к каждой копии по её базе
(политика per_copy; Ch2 = поле). Проверка загрузки повторяет asda_hairtable_sync.read_server (как читает сервер), если доступна.
Побочных эффектов при импорте нет.
"""
import os
import sys
import tempfile

from core import config
from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "hairshop", "Парикмахерская 15000"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
TABLE = "HairTypeTable.txt"
SRV_FILES = [("GS", "ItemTable_Info\\" + TABLE, "per_copy")]
PRICE_COL, PRICE_HEX = 5, 0x28        # колонка сервера; смещение Price в записи клиента (реестр 'hairtable.bin': (40,'i32','Price'))
CLIENT_FILES = {"hairtable": os.path.join(E.ITEMDB, "hairtable.csv")}
DT = {"hairtable": "/Game/AsdaAssets/Data/ItemDB/DT_hairtable"}
CSV_KEYS = ("hairtable",)
KINDS = {"hair.price": ("Парикмахерская: цена причёски (HairTypeTable + hairtable)", ("id", "value"), False)}


def norm(kind, p):
    return {"id": E._ival(p, "id", 0, 32767), "value": E._ival(p, "value", 0, 2000000000)}


def target_key(kind, p):
    return "hair:%d" % p["id"]


def server_check(raw):
    """Повтор загрузчика сервера над новыми байтами: (ошибка | None). asda_hairtable_sync.read_server (ПК), иначе — свой
    разбор потоком слов (Id подряд +1, 8 слов на запись)."""
    try:
        config.port_code(E.UE_TOOLS)        # ★ ревизия 56 С-1: на сервере — свой разбор (код порта вне дерева службы не исполняется)
        if E.UE_TOOLS not in sys.path:
            sys.path.insert(0, E.UE_TOOLS)
        import asda_hairtable_sync as HS    # noqa: E402 — без побочных эффектов при импорте
    except Exception:
        HS = None
    if HS is not None:
        fd, tmp = tempfile.mkstemp(prefix="asda_cs_hair_", suffix=".txt")
        try:
            os.write(fd, raw)
            os.close(fd)
            try:
                declared, rows = HS.read_server(tmp)
            except SystemExit as ex:
                return str(ex)
            return None if declared == len(rows) else "заголовок %d ≠ записей %d" % (declared, len(rows))
        finally:
            os.remove(tmp)
    tok = raw.split()
    n = E._int(tok[0].decode("latin-1")) if tok else -1
    if n < 0 or len(tok) < 1 + 8 * n:
        return "слов %d, ждали 1 + 8 × %d" % (len(tok), n)
    first = E._int(tok[1].decode("latin-1")) if n else 0
    for k in range(n):                          # ★ ревизия 33 К-4: как сервер — подряд +1 от первого (не обязательно с 0)
        if E._int(tok[1 + 8 * k].decode("latin-1")) != first + k:
            return "Id %s на месте %d — «Sync Error»" % (tok[1 + 8 * k].decode("latin-1"), k)
    return None


def k_hair_price(ev, p, rep):
    hid, val = p["id"], p["value"]
    cr = ev.cli.hair.get(hid)
    if cr is None:
        raise OpRefused("причёски %d нет в hairtable клиента — в А4 только правка существующих" % hid)
    olds = set()
    for g in E.GS:
        t = ev.st.get(g, TABLE)
        i = E.record_line(t, hid, 8)           # ★ ревизия 33 К-4: по порядку записи (Id подряд +1 — правило загрузчика)
        if i is None:
            raise OpRefused("%s %s: слова не ложатся построчно по 8 на запись — порядок записей сервера не доказан, правка не делается"
                            % (TABLE, g))
        if i < 0 or E._int(t.lines[i].split(b"\t")[0].decode("latin-1")) != hid:
            raise OpRefused("причёски %d нет в %s %s — в А4 только правка существующих" % (hid, TABLE, g))
        f = t.lines[i].split(b"\t")
        if len(f) < 8:
            raise OpRefused("строка причёски %d %s %s — меньше 8 полей" % (hid, TABLE, g))
        olds.add(E._int(f[PRICE_COL].decode("latin-1")))
        f[PRICE_COL] = E.set_token(f[PRICE_COL], val)
        t.set_line(i, b"\t".join(f))
        why = server_check(t.data())
        if why:
            raise OpRefused("%s %s после правки не загрузится сервером: %s" % (TABLE, g, why))
    old = sorted(olds)[0]
    if len(olds) > 1:
        rep["warnings"].append("цена причёски %d на копиях разная: %s — правка ложится на каждую копию" % (hid, sorted(olds)))
    _row, cp, hx = cr
    if cp != old:
        rep["warnings"].append("цены уже расходились: клиент %d, сервер %d" % (cp, old))
    if hx is not None and hx != cp:
        rep["errors"].append("hairtable: Price %d ≠ DataHex +0x28 %d — строка клиента не согласована" % (cp, hx))
    if val == old and cp == old:
        raise OpRefused("у причёски %d уже цена %d — менять нечего" % (hid, val))
    rep["text"] = "парикмахерская, причёска %d: цена %d → %d (сервер ×%d GS, клиент hairtable.Price + ведомость)" % (hid, old, val, len(E.GS))
    rep["_balance"] = [{"what": "парикмахерская, причёска %d: цена" % hid, "old": old, "new": val, "codes": []}]
    rep["client"] = [{"type": "csv_cell", "file": "hairtable", "key_col": "Id", "key": str(hid), "col": "Price", "old": str(cp), "new": str(val)},
                     {"type": "csv_hex_i32", "file": "hairtable", "key_col": "Id", "key": str(hid), "col": "DataHex", "off": PRICE_HEX,
                      "old": cp, "new": val}]
    ev.client += rep["client"]


def snapshot(snap):
    p = E.CLIENT_FILES["hairtable"]
    snap["hair"] = ({r["Id"]: [int(r["_row"]), E._int(r["Price"]), E._hex_price(r.get("DataHex") or "", PRICE_HEX)]
                     for r in E._read_csv(p)} if os.path.isfile(p) else {})


def parse(cli, d):
    cli.hair = {int(k): v for k, v in (d.get("hair") or {}).items()}


def divergence(ev, cli, sec):
    t = ev.st.get("GameServer", TABLE)
    rows = []
    for hid, i in sorted(t.index().items()):
        sp = E._int(E._f(t.lines[i])[PRICE_COL]) if len(E._f(t.lines[i])) > PRICE_COL else None
        c = cli.hair.get(hid)
        if c is None:
            rows.append({"id": hid, "why": "причёски нет у клиента"})
        elif c[1] != sp:
            rows.append({"id": hid, "client": c[1], "server": sp, "why": "цена клиент ≠ сервер (видит одно, платит другое)"})
    for hid in sorted(set(cli.hair) - set(t.index())):
        rows.append({"id": hid, "why": "причёски нет на сервере"})
    for g in E.GS[1:]:
        if ev.snap.md5.get(E.rel_of(g, TABLE)) != ev.snap.md5.get(E.rel_of("GameServer", TABLE)):
            rows.append({"id": "—", "why": "%s: %s ≠ GameServer (своя база копии)" % (g, TABLE)})
    sec("hair", "парикмахерская: цена сервер ≠ клиент", rows)
