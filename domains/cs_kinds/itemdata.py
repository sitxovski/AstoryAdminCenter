# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/itemdata.py — область «Предметы» (волна А4.4, 20.11.2026; разбор Reports/admin_center/research_a4_data.md §1.1, §3,
§4 п.5 и п.9, §5). Только правка СУЩЕСТВУЮЩИХ записей (решение владельца 19.11): новые предметы — не здесь.

ПАРА «сервер + клиент» (§3: «вес, стопка, уровень, класс предмета — пара, клиент проверяет и показывает сам»). Белый список — только
поля, у которых есть и загрузчик/потребитель сервера (декомпил GameServer.c), и потребитель клиента порта (§4 п.9 «не выдумывать»);
соответствие токен сервера ↔ поле клиента подтверждено вторым методом — сверкой всех 59 390 общих кодов 20.11.2026 (живые
item_table.txt и item_list.csv порта; Reports/gear_upgrade/scroll_sync.md §1 — та же карта):

  вид item.set {code, fields}: item_table.txt (sub_4A96A0, GameServer.c:68131, 42 токена → запись 71 б) во всех GameServer стойки
                 (база одна — политика same) + item_list.csv порта (колонка CSV и байты DataHex записи 248 б) + ВЕДОМОСТЬ
                 RawAssets/ItemDB/_value_overlay/item_list.csv (shopdata.ledger_plan; правило itemdb-ledger-overlays):
    durability  ток.1  → +4  u8   (sub_5340B0: Durability новой вещи; sub_4CDAA0: снаряжение с прочностью 0 не надевается, код 20)
                ↔ клиент +68 i32 DurabilityMax (знаменатель «Прочность:», ремонт) — поле ведомости Field68 (колонки CSV нет)   98.9 %
    weight      ток.2  → +5  i16  (≤ 0 → 1 при загрузке ItemName_Table, :68325; вес новой строки Item: штучный = вес, стопка =
                n × вес, sub_5340B0 :117722) ↔ клиент +72 (U16, AsdaItemTableSubsystem.cpp Weight; стопка — (int16)(Amount × Weight),
                AsdaNetSubsystem_Items.cpp) — поле ведомости Weight (колонки CSV нет)                                          96.6 %
    lvl_min     ток.4  → +8  u8   (sub_4CDAA0, items.equip_error) ↔ RequiredLevel (+80)                                       99.9 %
    lvl_max     ток.5  → +9  u8   ↔ RequiredLevelMax (+84)                                                                    99.8 %
    job         ток.7  → +10 u8   (sub_4CDDA0, items.job_ok) ↔ UsageCategory (+92; класс — item-duplicates-nature)            97.7 %
    stack       ток.23 → +35 u8   (sub_5340B0: сумка 2 складывает стопку, если ≠ 0; сумка 1 — никогда) ↔ TradableFlag (+152;
                клиент по нему рисует число и считает вес стопки)                                                             99.6 %
  вид gem.level {code, level}: Cellob_Table.txt ток.16 → +32 u8 (загрузчик GameServer.c:68663; srvtables.sowel_error: самоцвет выше
                 уровня персонажа — код 10; вещь с ним не надевается — код 14) во всех GS + sowell_list.csv RequiredLevel (+65 u8;
                 подсказка и обмен порта) + ВЕДОМОСТЬ _value_overlay/sowell_list.csv (реестр decode_item_db: value_ledger с 20.11) 100 %
Не правятся (смысл или пара не подтверждены): тип/подтип (ток.16/17 — сумка и ветки сервера: свитки, пакеты, коробки), цена
(вид А3 «price»), Function_Table (у special_itemlist подтверждена только цена ток.20 = Price, а путь цены спецпредметов А3 отклонил),
вес/прочность самоцветов Cellob (у sowell_list нет тёзки), остальные токены.

ДЮПЫ И ЦЕЛОСТНОСТЬ (§4 п.5; бриф 20.11: «отказ, не предупреждение, где разбор требует»): строки Joy1 (Item + Exitem + ItemPostBox —
shopdata.held_counts) панель не переписывает, поэтому правка, после которой строки на руках перестают значить то же самое, — ОТКАЗ:
  * стопка у кода, который есть у игроков: у штучных Amount = 0, у стопочных Amount = количество (research_item_props §4) — строки
    стали бы стопками «0 шт.» или N штук в одной штучной ячейке; не прочитано — тоже отказ (вслепую не делается);
  * стопка у предмета сумки 1 (сервер её не смотрит — клиент и сервер разошлись бы) и у контейнеров типа 10 (Amount = содержимое);
  * ★ ревизия 36 Б-2: стопка у предмета, который сервер не считает стопочным в выдаче/подборе/весе (ток.3 ≠ 4 или ток.24 ≠ 1 —
    sub_469010 :42966/:42986, sub_4D6CE0, sub_4DF6D0, sub_40E8F0 = shopdata.stack_flags), — в обе стороны;
  * ★ ревизия 36 М-1: вес стопочного предмета, который есть у игроков (Item.Weight строки = n × прежний вес, сервер списывает по
    новому — sub_53CC30 :121059, sub_55F050 :135442); пересчёт Item.Weight панель не делает; не прочитано — отказ;
  * ★ ревизия 36 К-2: мин. уровень больше макс. (клиент не пустит ни на каком уровне, сервер — выше макс.);
  * золото 20551 (одна строка на персонажа, вес 0) — не правится.
«На руках» (shopdata.held_counts, ★ ревизия 36 М-2): Item, Exitem, ItemPostBox, отложенные подарки dbo.gifts, неоткаченные снимки
изъятия adm.ItemTaken (их возвращает adm.ItemUndo с прежними Amount/Weight), неурегулированные подарки GP7GiftLog ('H').
★ ревизия 36 Б-1: смена стопки и вес стопки пишут в итог проверки guard — shopcs перечитывает «на руках» перед объявлением выкладки
(появились — отказ) и перед откатом сервера (есть — второе подтверждение владельца --held-ok); не прочитано — отказ.
Сильная правка баланса (решение владельца 19.11): значение больше чем в 2 раза (вес, прочность, уровни, уровень самоцвета), смена
стопки (kind stack), вес стопочного предмета (kind stackweight, ★ ревизия 36 М-4: предела стопки на сервере нет) и требования
класса (kind type) — второе подтверждение только владельцем (shopcs.CsApprove._balance) с показом «на руках у игроков».
Побочных эффектов при импорте нет.
"""
import json
import os
import struct

from core.ops import OpRefused
from domains import shopdata as E
from domains import srvtables

AREA, TITLE = "itemdata", "Предметы"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
IT, CEL = "item_table.txt", "Cellob_Table.txt"
SRV_FILES = [("GS", "ItemTable_Info\\" + IT, "same"), ("GS", "ItemTable_Info\\" + CEL, "same")]
CLIENT_FILES = {"sowell_list": os.path.join(E.ITEMDB, "sowell_list.csv")}       # item_list.csv — уже у области «Магазины»
DT = {"sowell_list": "/Game/AsdaAssets/Data/ItemDB/DT_sowell_list"}
CSV_KEYS = ("sowell_list",)                                                      # item_list — в CSV_KEYS магазинов (план движка)
KINDS = {"item.set": ("Предмет: поля карточки (item_table + item_list)", ("code", "fields"), False),
         "gem.level": ("Самоцвет: минимальный уровень (Cellob_Table + sowell_list)", ("code", "level"), False)}

# поле → (токен item_table, подпись, мин, макс, колонка CSV item_list | None, смещение в DataHex, поле ведомости)
FIELDS = {
    "durability": (1, "прочность (макс.)", 0, 255, None, 68, "Field68"),
    "weight": (2, "вес единицы", 1, 32767, None, 72, "Weight"),
    "lvl_min": (4, "мин. уровень", 0, 255, "RequiredLevel", 80, "RequiredLevel"),
    "lvl_max": (5, "макс. уровень", 0, 255, "RequiredLevelMax", 84, "RequiredLevelMax"),
    "job": (7, "требование класса", 0, 255, "UsageCategory", 92, "UsageCategory"),
    "stack": (23, "стопка", 0, 1, "TradableFlag", 152, "TradableFlag"),
}
ORDER = ("durability", "weight", "lvl_min", "lvl_max", "job", "stack")
CARD = {n: i + 1 for i, n in enumerate(ORDER)}              # снимок: [_row, durability, weight, lvl_min, lvl_max, job, stack, несогласованные]
PLATE1_TYPES = {0, 1, 2, 3, 4, 8, 9, 12, 13, 14, 15}         # sub_5340B0 (= domains/items.PLATE1_TYPES)
ARMOR_TYPES = {0, 1, 2, 3, 4, 8, 9, 11, 12, 13, 14, 15}      # sub_4CDAA0: прочность 0 → отказ 20 (= domains/items.ARMOR_TYPES)
CONTAINER_TYPE = 10                                          # колчаны / наживка / заряды бура: Amount = содержимое
I16_MAX = 32767
GEM_LVL_TOK, GEM_LVL_OFF = 16, 65                            # Cellob ток.16 (+32) ↔ sowell_list RequiredLevel (+65 u8)


def norm(kind, p):
    if kind == "gem.level":
        return {"code": E._ival(p, "code", srvtables.CELLOB_BASE, E.ITEM_FIRST - 1), "level": E._ival(p, "level", 0, 255)}
    src = p.get("fields")
    if isinstance(src, str):
        try:
            src = json.loads(src)
        except ValueError:
            src = None
    if not isinstance(src, dict) or not src:
        raise OpRefused("поле «fields»: {поле: число, …} — хотя бы одно поле (%s)" % ", ".join(ORDER))
    bad = sorted(str(k) for k in src if k not in FIELDS)
    if bad:
        raise OpRefused("поле «fields»: неизвестные поля %s (можно: %s)" % (", ".join(bad), ", ".join(ORDER)))
    out = {}
    for k in ORDER:
        v = src.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        out[k] = E._ival({k: v}, k, FIELDS[k][2], FIELDS[k][3])
    if not out:
        raise OpRefused("поле «fields»: {поле: число, …} — хотя бы одно поле (%s)" % ", ".join(ORDER))
    return {"code": E._ival(p, "code", E.ITEM_FIRST, E.SELL_CEIL), "fields": out}


def target_key(kind, p):
    return ("gem:%d" if kind == "gem.level" else "itemcard:%d") % p["code"]


def plate_of(typ, t24):
    """Сумка, в которую сервер кладёт предмет (sub_5340B0): 1 — ток.24 = 3 или тип 0–4, 8, 9, 12–15; иначе 2."""
    return 1 if t24 == 3 or typ in PLATE1_TYPES else 2


def held(ev, code):
    """«На руках у игроков» по коду (shopdata.held_counts: Item, Exitem, ItemPostBox, gifts, ItemTaken, GP7GiftLog) → {rows, amount, max, …}
    | None (не прочитано);
    один запрос на код за оценку."""
    cache = ev.__dict__.setdefault("_itemdata_held", {})
    if code not in cache:
        h = E.held_counts([code], {code: bool(E.stack_flags(ev, [code]).get(code))})
        cache[code] = None if h is None else h.get(code, {"rows": 0, "amount": 0, "max": 0, "where": {}})
    return cache[code]


def _held_txt(h):
    where = ", ".join("%s %d" % (t, n) for t, n in sorted((h.get("where") or {}).items()))
    return "записей %d, сумма Amount %d, наибольшая стопка %d (%s)" % (h.get("rows", 0), h.get("amount", 0), h.get("max", h.get("amount", 0)),
                                                                       where or "—")


def _req_held(ev, code, rep, done):
    """★ ревизия 36 К-1: смена требования класса или уровней — сведения «на руках» (одно предупреждение на позицию) → True."""
    if done:
        return True
    h = held(ev, code)
    if h is None:
        rep["warnings"].append("на руках у игроков: не прочитано (%s)" % (getattr(E.held_counts, "last_error", None) or "нет связи с Joy1"))
    elif h.get("rows"):
        rep["warnings"].append("на руках у игроков (%s): требование проверяется при надевании (sub_4CDAA0, sub_4CDDA0) — вещи, под новое "
                               "требование которых персонаж не подходит, после снятия не наденутся" % _held_txt(h))
    return True


def guard_codes(cs):
    """★ ревизия 36 Б-1: коды позиций «Предметы», которым и при выкладке, и при откате сервера нужно «нет на руках у игроков»:
    смена стопки и вес стопочного предмета (итог проверки: позиция → guard). Итог проверки старше ревизии 36 (без guard) —
    по параметрам позиции: любая смена стопки или веса (с запасом)."""
    pos = {r["pos"]: r for r in (cs.get("check") or {}).get("positions") or []}
    out = {}
    for it in cs.get("items") or []:
        if it["kind"] != "item.set":
            continue
        r = pos.get(it["pos"]) or {}
        if "guard" in r:
            for g in r["guard"]:
                out.setdefault(int(g["code"]), set()).add(g["why"])
            continue
        f = (it.get("params") or {}).get("fields") or {}
        if isinstance(f, str):
            try:
                f = json.loads(f)
            except ValueError:
                f = {}
        why = {w for w in ("stack", "weight") if w in f}
        if why:
            out.setdefault(int(it["params"]["code"]), set()).update(why)
    return out


def after_run(ev):
    """★ ревизия 37 М-1/М-2: смена стопки и веса проверяется против наград заданий (RepayTable всех GS, предметы доски) по ИТОГОВОМУ
    состоянию набора — проверку ведёт область «Задания» (questtables.after_run); если её позиций в наборе нет, зовётся отсюда."""
    from domains.cs_kinds import questtables as QT
    if QT not in ev.areas:
        QT.after_run(ev)


def apply_guard(cs, mode):
    """★ ревизия 37 М-1: перед выкладкой и откатом сервера смена стопки перепроверяется против наград заданий (живые таблицы + правки
    набора) — questtables.apply_guard; если в наборе есть позиции «Заданий», их хук уже это сделал."""
    from domains.cs_kinds import questtables as QT
    if any(E.AREA_OF.get(it["kind"]) is QT for it in cs.get("items") or []):
        return []
    return QT.apply_guard(cs, mode)


def held_guard(cs):
    """«На руках у игроков» по guard_codes набора, прочитано заново (shopdata.held_counts) → (коды, текст занятых | None).
    Не прочитано — OpRefused (вслепую выкладка и откат не делаются)."""
    codes = guard_codes(cs)
    if not codes:
        return [], None
    h = E.held_counts(sorted(codes), {c: True for c in codes})
    if h is None:
        raise OpRefused("коды со сменой стопки или веса стопки (%s): «на руках у игроков» не прочитано (%s) — вслепую не делается"
                        % (", ".join(map(str, sorted(codes))), getattr(E.held_counts, "last_error", None) or "нет связи с Joy1"))
    busy = [(c, v) for c, v in sorted(h.items()) if v.get("rows")]
    if not busy:
        return sorted(codes), None
    # ★ А4.5 (20.11, мелочь ревизии 36): коды — через «; », чтобы переводчик (i18n.tr режет вложенный текст по «; ») перевёл сведения
    #   «на руках» у КАЖДОГО кода, а не только у первого
    return sorted(codes), "; ".join("%d — %s" % (c, _held_txt(v)) for c, v in busy)


COND_TABLES = (("Quest\\ConditionTable.Bin", 146, 69, 89),            # questdata.cond_rec: 5 × i32 ids +69, 5 × i16 cnts +89 (sub_41FD70)
               ("Quest\\MonsterConditionTable.bin", 59, 21, 41))       # sub_41FB90 (NpcServer.exe.c:21608): 5 × i32 +21, 5 × i16 +41; ключ +0


def cond_uses(raw_by_table, code):
    """★ А4.6 (попутно из А4.5): записи ConditionTable / MonsterConditionTable NpcServer, где предмет code — цель (id среди 5 пар) →
    [(таблица, ключ, количество)]. Только чтение: условия область не правит."""
    import struct
    out = []
    for sub, rec, ido, cno in COND_TABLES:
        b = raw_by_table.get(sub)
        if not b:
            continue
        for k in range(len(b) // rec):
            r = b[k * rec:(k + 1) * rec]
            key = struct.unpack_from("<I", r, 0)[0] if rec == 59 else k
            for j in range(5):
                if struct.unpack_from("<i", r, ido + 4 * j)[0] == int(code):
                    out.append((sub.split("\\")[-1].split(".")[0], key, struct.unpack_from("<h", r, cno + 2 * j)[0]))
    return out


def cond_warn(ev, code, rep):
    """Смена стопки предмета, который — цель условий заданий: предупреждение со списком (условия не правятся)."""
    try:
        rels = [E.rel_of("NpcServer", sub) for sub, _r, _i, _c in COND_TABLES]
        ev.snap.extend(rels)
        raw = {sub: ev.snap.raw(rel) for (sub, _r, _i, _c), rel in zip(COND_TABLES, rels)}
    except Exception as ex:
        rep["warnings"].append("условия заданий с этим предметом не прочитаны (%s)" % str(ex)[:160])
        return
    uses = cond_uses(raw, code)
    if uses:
        rep["warnings"].append("смена стопки %s: предмет — цель условий заданий (%s) — условия панель не правит, проверьте, что сбор и сдача после "
                               "смены стопки идут как задумано" % (E.nm(code), ", ".join("%s %d × %d" % u for u in uses[:20])
                                                                    + (" и ещё %d" % (len(uses) - 20) if len(uses) > 20 else "")))


def job_values(ev, typ):
    """Требования класса (ток.7), которые встречаются у предметов того же типа (ток.16) в item_table GameServer ДО правок набора."""
    cache = ev.__dict__.setdefault("_itemdata_jobs", None)
    if cache is None:
        cache = {}
        raw = ev.snap.raw(E.rel_of(E.GS[0], IT))
        for ln in raw.split(b"\n")[1:]:
            f = ln.split(b"\t")
            if len(f) > 16 and f[0].strip().isdigit():
                cache.setdefault(E._int(f[16].decode("latin-1")), set()).add(E._int(f[7].decode("latin-1")))
        ev._itemdata_jobs = cache
    return cache.get(typ, set())


def k_item_set(ev, p, rep):
    code, want = p["code"], p["fields"]
    if code == E.ITEM_FIRST:
        raise OpRefused("золото 20551 не правится: одна строка на персонажа (Plate 2, вес 0), её ищут процедуры покупки")
    card = ev.cli.itemcard.get(code)
    if card is None:
        raise OpRefused("кода %d нет в item_list клиента — карточки нет (в А4 только правка существующих)" % code)
    olds, meta = {}, None
    for g in E.GS:
        t = ev.st.get(g, IT)
        i = t.index().get(code)
        if not i:
            raise OpRefused("кода %d нет в item_table %s — в А4 только правка существующих" % (code, g))
        f = t.lines[i].split(b"\t")
        if len(f) < 42:
            raise OpRefused("строка %d item_table %s — меньше 42 полей" % (code, g))
        if meta is None:
            meta = [E._int(f[k].decode("latin-1")) for k in (16, 17, 24, 23, 3, 4, 5)]   # до правки (set_token ниже)
        for name, v in want.items():
            tok = FIELDS[name][0]
            olds.setdefault(name, set()).add(E._int(f[tok].decode("latin-1")))
            f[tok] = E.set_token(f[tok], v)
        t.set_line(i, b"\t".join(f))
    typ, sub, t24, stack_old, t3, lmin_old, lmax_old = meta
    plate = plate_of(typ, t24)
    if card[7]:
        rep["errors"].append("item_list %d: колонки %s ≠ байтам DataHex — строка клиента не согласована" % (code, card[7]))
    changes = []
    for name in ORDER:
        if name not in want:
            continue
        label = FIELDS[name][1]
        if len(olds[name]) > 1:
            rep["errors"].append("%s у кода %d на GameServer разное: %s — правка вслепую запрещена" % (label, code, sorted(olds[name])))
        old, new, cv = sorted(olds[name])[0], want[name], card[CARD[name]]
        if name == "weight":
            cv &= 0xFFFF                                  # клиент читает младшее слово (U16 +72)
        if cv != old:
            rep["warnings"].append("%s: уже расходились — клиент %d, сервер %d" % (label, cv, old))
        if new == old and cv == new:
            continue
        changes.append((name, old, new, cv))
    if not changes:
        raise OpRefused("у предмета %d уже такие значения — менять нечего" % code)
    stack_new = want.get("stack", stack_old)
    bal, lines, guard = [], [], []
    req_warned = False
    for name, old, new, cv in changes:
        label = FIELDS[name][1]
        lines.append("%s: %d → %d" % (label, old, new))
        if name == "stack" and new != old:
            if plate == 1:
                raise OpRefused("стопка у предмета сумки 1 (тип %d, ток.24 = %d): сервер её не смотрит (sub_5340B0), клиент начал бы "
                                "считать стопку — клиент и сервер разошлись бы, правка не делается" % (typ, t24))
            if typ == CONTAINER_TYPE:
                raise OpRefused("стопка у контейнера типа 10 (колчан, наживка, заряд бура): Amount у него — содержимое, а не штуки "
                                "(research_item_props §4), правка не делается")
            if t3 != 4 or t24 != 1:
                # ★ ревизия 36 Б-2: сервер в выдаче, подборе и расчёте веса (sub_469010 :42966/:42986, sub_4D6CE0, sub_4DF6D0, sub_40E8F0 и
                #   ещё десятки мест) считает стопкой только +35 ≠ 0 И +26 ≠ 10 И +7 = 4 (часть — ещё +36 = 1) = shopdata.stack_flags;
                #   у «полустопки» создание (sub_5340B0) складывает n штук в строку, а выдача не пишет Amount/Weight пакета — расходится
                raise OpRefused("стопка у предмета с ток.3 = %d и ток.24 = %d: сервер считает стопкой только ток.3 = 4 и ток.24 = 1 "
                                "(sub_469010, sub_4D6CE0 и др.), а создание строки (sub_5340B0) смотрит один ток.23 — количество в памяти "
                                "сервера, в пакете и в Joy1 разошлось бы, смысл не подтверждён, правка не делается" % (t3, t24))
            h = held(ev, code)
            if h is None:
                raise OpRefused("смена стопки: «на руках у игроков» не прочитано (%s) — вслепую не делается" % (getattr(E.held_counts, "last_error", None) or "нет связи с Joy1"))
            if h.get("rows"):
                raise OpRefused("смена стопки кода, который есть у игроков (%s): у штучных Amount = 0, у стопок — количество, строки Joy1 "
                                "панель не переписывает — после правки они значили бы другое (дюп или потеря), правка не делается" % _held_txt(h))
            bal.append({"what": "предмет %s: стопка" % E.nm(code), "old": old, "new": new, "codes": [code], "kind": "stack"})
            guard.append("stack")
            cond_warn(ev, code, rep)                   # ★ А4.6 (попутно из А4.5): предмет — цель условий заданий (только чтение)
        elif name == "weight":
            if plate == 2 and (stack_new or stack_old):
                # ★ ревизия 36 М-1: сервер списывает расход по ТЕКУЩЕМУ весу таблицы (sub_53CC30 :121059 HIWORD(a5[3]) -= w,
                #   sub_55F050 :135442 v19[7] -= n × w), а Item.Weight строк хранит n × прежний вес — после правки вес строки уходит
                #   в минус (или остаётся завышенным). Пересчёт Item.Weight панель не делает (строки игроков не переписываются) — отказ
                h = held(ev, code)
                if h is None:
                    raise OpRefused("вес стопочного предмета: «на руках у игроков» не прочитано (%s) — вслепую не делается"
                                    % (getattr(E.held_counts, "last_error", None) or "нет связи с Joy1"))
                if h.get("rows"):
                    raise OpRefused("вес стопочного предмета, который есть у игроков (%s): Item.Weight строки = количество × прежний вес, а "
                                    "сервер списывает расход по новому весу (sub_53CC30, sub_55F050) — вес строки ушёл бы в минус (перегруз "
                                    "без предела) или остался бы завышенным, строки Joy1 панель не переписывает, правка не делается" % _held_txt(h))
                # ★ ревизия 36 М-4: предела стопки на сервере нет (sub_5340B0 :117717 / sub_4D6CE0 складывают без проверки) — правка
                #   веса стопки всегда сильная, с пояснением, при каком количестве переполнится SMALLINT Item.Weight
                rep["warnings"].append("вес стопочного предмета — сильная правка: предела стопки на сервере нет (sub_5340B0 и sub_4D6CE0 "
                                       "складывают без проверки), стопка больше %d шт. переполнит SMALLINT Item.Weight (n × вес %d > 32767)"
                                       % (I16_MAX // new, new))
                guard.append("weight")
            else:
                h = held(ev, code)
                if h is None:
                    rep["warnings"].append("на руках у игроков: не прочитано (%s)" % (getattr(E.held_counts, "last_error", None) or "нет связи с Joy1"))
                elif h.get("rows"):
                    rep["warnings"].append("на руках у игроков (%s): вес строк Item прежний, новый — у новых вещей, суммарный вес "
                                           "персонажа пересчитается при входе (UPCharInfo)" % _held_txt(h))
            if old <= 0:
                rep["warnings"].append("вес сервера %d: при загрузке GameServer ставит 1 (≤ 0 → 1, GameServer.c:68325)" % old)
            bal.append({"what": "предмет %s: вес единицы" % E.nm(code), "old": max(old, 1), "new": new, "codes": [code],
                        "kind": "stackweight" if "weight" in guard else "value"})
        elif name == "durability":
            if new == 0 and typ in ARMOR_TYPES:
                raise OpRefused("прочность 0 у снаряжения (тип %d): новые вещи сервер не даст надеть (sub_4CDAA0, код 20), правка не делается" % typ)
            rep["warnings"].append("прочность: у вещей на руках прочность строки Item прежняя — новый максимум получат новые вещи "
                                   "(sub_5340B0), клиент покажет его знаменателем «Прочность:»")
            bal.append({"what": "предмет %s: прочность (макс.)" % E.nm(code), "old": old, "new": new, "codes": [code]})
        elif name in ("lvl_min", "lvl_max"):
            req_warned = _req_held(ev, code, rep, req_warned)
            bal.append({"what": "предмет %s: %s" % (E.nm(code), label), "old": old, "new": new, "codes": [code]})
        elif name == "job":
            req_warned = _req_held(ev, code, rep, req_warned)
            vals = job_values(ev, typ)
            if new not in vals:
                raise OpRefused("требование класса %d не встречается у предметов типа %d (есть: %s) — смысл не подтверждён, правка не делается"
                                % (new, typ, ", ".join(map(str, sorted(vals))) or "—"))
            if typ == 9 and new and not 40 <= new <= 44:
                raise OpRefused("оружие (тип 9): требование класса %d — сервер (sub_4CDDA0) у оружия пускает только 40…44 (JobCount), "
                                "иначе не наденет никто, правка не делается" % new)
            bal.append({"what": "предмет %s: требование класса" % E.nm(code), "old": old, "new": new, "codes": [code], "kind": "type"})
    lmin, lmax = want.get("lvl_min", lmin_old), want.get("lvl_max", lmax_old)
    if ("lvl_min" in want or "lvl_max" in want) and lmin > lmax:
        # ★ ревизия 36 К-2: сервер (sub_4CDAA0 :81970) при min > max пускает уровни выше max, клиент — ни на каком: расходятся.
        #   В живых данных min > max — у одной вещи из 59 390 (23090), смысл не подтверждён — отказ
        raise OpRefused("мин. уровень %d больше макс. %d: клиент не даст применить ни на каком уровне, а сервер (sub_4CDAA0) пустит "
                        "уровни выше макс. — клиент и сервер разошлись бы, правка не делается" % (lmin, lmax))
    rep["text"] = "предмет %s: полей %d (сервер item_table ×%d GS, клиент item_list + ведомость)" % (E.nm(code), len(changes), len(E.GS))
    rep["lines"] = lines
    # ★ ревизия 36 Б-1: коды, которым нужны «нет на руках» и при выкладке, и при откате сервера (shopcs.held_guard) — в итог проверки
    rep["guard"] = [{"code": code, "why": w} for w in guard]
    rep["_codes"] = [code]
    rep["_balance"] = bal
    client = []
    for name, old, new, cv in changes:
        _tok, _label, _lo, _hi, col, off, _lf = FIELDS[name]
        hx = card[CARD[name]] if col is None else cv           # i32 записи (у колонок — = колонке: несогласованность — ошибка выше)
        nh = ((hx & -65536) | new) if name == "weight" else new
        if col:
            client.append({"type": "csv_cell", "file": "item_list", "key_col": "ItemCode", "key": str(code), "col": col,
                           "old": str(cv), "new": str(new), "src": AREA})
        client.append({"type": "csv_hex_i32", "file": "item_list", "key_col": "ItemCode", "key": str(code), "col": "DataHex",
                       "off": off, "old": hx, "new": nh, "src": AREA})
    rep["client"] = client
    ev.client += client


def k_gem_level(ev, p, rep):
    code, lvl = p["code"], p["level"]
    card = ev.cli.gemcard.get(code)
    if card is None:
        raise OpRefused("самоцвета %d нет в sowell_list клиента — карточки нет (в А4 только правка существующих)" % code)
    olds = set()
    for g in E.GS:
        t = ev.st.get(g, CEL)
        i = t.index().get(code)
        if not i:
            raise OpRefused("самоцвета %d нет в Cellob_Table %s — в А4 только правка существующих" % (code, g))
        f = t.lines[i].split(b"\t")
        if len(f) < 20:
            raise OpRefused("строка %d Cellob_Table %s — меньше 20 полей" % (code, g))
        olds.add(E._int(f[GEM_LVL_TOK].decode("latin-1")))
        f[GEM_LVL_TOK] = E.set_token(f[GEM_LVL_TOK], lvl)
        t.set_line(i, b"\t".join(f))
    old = sorted(olds)[0]
    if len(olds) > 1:
        rep["errors"].append("уровень самоцвета %d на GameServer разный: %s — правка вслепую запрещена" % (code, sorted(olds)))
    _row, cv, hx32 = card
    if (hx32 & 0xFF) != cv:
        rep["errors"].append("sowell_list %d: RequiredLevel %d ≠ DataHex +65 %d — строка клиента не согласована" % (code, cv, hx32 & 0xFF))
    if cv != old:
        rep["warnings"].append("уровень самоцвета: уже расходились — клиент %d, сервер %d" % (cv, old))
    if lvl == old and cv == lvl:
        raise OpRefused("у самоцвета %d уже уровень %d — менять нечего" % (code, lvl))
    if lvl > old:
        rep["warnings"].append("самоцветы, уже вставленные в гнёзда вещей, подчиняются новому уровню: вещь с ним сервер не даст надеть "
                               "персонажу ниже уровня (sub_4CDAA0, код 14)")
    rep["text"] = "самоцвет %s: мин. уровень %d → %d (сервер Cellob_Table ×%d GS, клиент sowell_list + ведомость)" % (E.nm(code), old, lvl, len(E.GS))
    rep["lines"] = ["мин. уровень: %d → %d" % (old, lvl)]
    rep["_codes"] = [code]
    rep["_balance"] = [{"what": "самоцвет %s: мин. уровень" % E.nm(code), "old": old, "new": lvl, "codes": [code]}]
    rep["client"] = [{"type": "csv_cell", "file": "sowell_list", "key_col": "Id", "key": str(code), "col": "RequiredLevel",
                      "old": str(cv), "new": str(lvl), "src": AREA},
                     {"type": "csv_hex_i32", "file": "sowell_list", "key_col": "Id", "key": str(code), "col": "DataHex",
                      "off": GEM_LVL_OFF, "old": hx32, "new": (hx32 & ~0xFF) | lvl, "src": AREA}]
    ev.client += rep["client"]


# =====================================================================================================================
# КЛИЕНТ: снимок и разбор
# =====================================================================================================================
def _i32(b, off):
    return struct.unpack_from("<i", b, off)[0] if len(b) >= off + 4 else None


def card_of(r):
    """Строка item_list.csv → [_row, durability (+68), weight (+72 i32), lvl_min, lvl_max, job, stack, «колонки ≠ DataHex»]."""
    try:
        b = bytes.fromhex(r.get("DataHex") or "")
    except ValueError:
        b = b""
    bad = [c for n in ORDER for c in [FIELDS[n][4]] if c and _i32(b, FIELDS[n][5]) is not None and _i32(b, FIELDS[n][5]) != E._int(r.get(c))]
    if len(b) < 156:
        bad.append("DataHex")
    return [int(r["_row"]), _i32(b, 68) or 0, _i32(b, 72) or 0] + [E._int(r.get(FIELDS[n][4])) for n in ORDER[2:]] + [",".join(bad)]


def snapshot(snap):
    snap["itemcard"] = {r["ItemCode"]: card_of(r) for r in E._read_csv(E.CLIENT_FILES["item_list"])}
    p = E.CLIENT_FILES["sowell_list"]
    gem = {}
    for r in (E._read_csv(p) if os.path.isfile(p) else []):
        try:
            b = bytes.fromhex(r.get("DataHex") or "")
        except ValueError:
            b = b""
        gem[r["Id"]] = [int(r["_row"]), E._int(r.get("RequiredLevel")), _i32(b, GEM_LVL_OFF) if len(b) >= GEM_LVL_OFF + 4 else -1]
    snap["gemcard"] = gem


def parse(cli, d):
    cli.itemcard = {int(k): v for k, v in (d.get("itemcard") or {}).items()}
    cli.gemcard = {int(k): v for k, v in (d.get("gemcard") or {}).items()}


def plan(pc):
    """★ Сверка итога плана: у строк item_list / sowell_list, которые правит область, в CSV ПОСЛЕ ведомости и DataHex генератора
    (shopdata.ledger_plan может заменить DataHex строки байтами перегенерации) колонки и байты — ровно как в позиции. Иначе правка
    молча потерялась бы (поле без строки ведомости, раскладка генератора без поля) — отказ плана."""
    for key in ("item_list", "sowell_list"):
        es = [e for e in pc["by_file"].get(key, []) if e.get("src") == AREA]
        if not es:
            continue
        cur = pc["files"].get(E.CLIENT_FILES[key])
        if not cur or cur[1] is None:
            pc["errors"].append("%s: план не изменил файл, а правки области «Предметы» есть" % key)
            continue
        _h, _by, rows = E._csv_rows(cur[1])
        kc = es[0]["key_col"]
        by = {r.get(kc): r for r in rows}
        for e in es:
            r = by.get(e["key"])
            if r is None:
                continue                                   # «строки нет» — уже ошибка плана движка
            if e["type"] == "csv_cell" and r.get(e["col"]) != e["new"]:
                pc["errors"].append("%s %s=%s: %s после плана %s, а позиция — %s" % (key, kc, e["key"], e["col"], r.get(e["col"]), e["new"]))
            elif e["type"] == "csv_hex_i32":
                got = E._hex_val(r.get("DataHex"), e["off"], "i32")
                if got != int(e["new"]):
                    pc["errors"].append("%s %s=%s: DataHex +%d после плана %s, а позиция — %s (правка потерялась бы при перегенерации)"
                                        % (key, kc, e["key"], e["off"], got, e["new"]))


# =====================================================================================================================
# Справка редактору (только чтение) и расхождения
# =====================================================================================================================
def search(q, limit=60):
    from domains import refdata
    q = (q or "").strip()
    if not q:
        return {"rows": []}
    return {"rows": [{"code": x["code"], "name": x["name"], "icon": x["icon"]} for x in refdata.search_items(q, limit)
                     if x["code"] >= srvtables.CELLOB_BASE]}


def lookup_item(code):
    from domains import refdata
    ev = E.Eval([{"pos": 1, "kind": "item.set", "params": {}}], False)
    srv = {}
    meta = None
    for g in E.GS:
        f = ev.it_fields(code, g)
        srv[g] = {n: E._int(f[FIELDS[n][0]]) for n in ORDER} if f else None
        if f and meta is None:
            meta = {"type": E._int(f[16]), "subtype": E._int(f[17]), "t24": E._int(f[24]), "t3": E._int(f[3])}
    c = ev.cli.itemcard.get(code)
    if c is None and not any(srv.values()):
        raise OpRefused("предмета %d нет ни на сервере, ни у клиента" % code)
    cli = None
    if c is not None:
        cli = {n: (c[CARD[n]] & 0xFFFF if n == "weight" else c[CARD[n]]) for n in ORDER}
        cli["_bad"] = c[7]
    h = E.held_counts([code], E.stack_flags(ev, [code])) if meta else None
    inf = refdata.item(code)
    return {"code": code, "name": inf["name"], "icon": inf["icon"], "server": srv, "client": cli, "meta": meta,
            "plate": plate_of(meta["type"], meta["t24"]) if meta else None, "fields": [[n, FIELDS[n][1], FIELDS[n][2], FIELDS[n][3]] for n in ORDER],
            "jobs": sorted(job_values(ev, meta["type"])) if meta else [], "held": (h or {}).get(code) if h is not None else None,
            "held_error": getattr(E.held_counts, "last_error", None) if h is None else None}


def lookup_gem(code):
    from domains import refdata
    ev = E.Eval([{"pos": 1, "kind": "gem.level", "params": {}}], False)
    srv = {}
    for g in E.GS:
        t = ev.st.get(g, CEL)
        i = t.index().get(code)
        f = E._f(t.lines[i]) if i else None
        srv[g] = E._int(f[GEM_LVL_TOK]) if f and len(f) > GEM_LVL_TOK else None
    c = ev.cli.gemcard.get(code)
    if c is None and not any(v is not None for v in srv.values()):
        raise OpRefused("самоцвета %d нет ни на сервере, ни у клиента" % code)
    inf = refdata.item(code)
    return {"code": code, "name": inf["name"], "icon": inf["icon"], "server": srv, "client": c[1] if c else None,
            "client_hex": (c[2] & 0xFF) if c else None}


def lookup(what, ident):
    if what == "items":
        return search(ident)
    try:
        n = int(str(ident).strip())
    except (TypeError, ValueError):
        raise OpRefused("код предмета: нужно целое число")
    if what == "gem":
        return lookup_gem(n)
    return lookup_item(n)


def divergence(ev, cli, sec):
    """Поля белого списка: item_table GameServer ≠ item_list клиента; Cellob ток.16 ≠ sowell_list.RequiredLevel."""
    rows = []
    t = ev.st.get(E.GS[0], IT)
    for code, i in sorted(t.index().items()):
        f = E._f(t.lines[i])
        c = cli.itemcard.get(code)
        if c is None or len(f) < 42:
            if c is None and code >= E.ITEM_FIRST:
                rows.append({"code": code, "field": "—", "why": "кода нет в item_list клиента"})
            continue
        for n in ORDER:
            sv, cv = E._int(f[FIELDS[n][0]]), c[CARD[n]]
            if n == "weight":
                sv, cv = max(sv, 1), cv & 0xFFFF
            if sv != cv:
                rows.append({"code": code, "field": FIELDS[n][1], "server": sv, "client": cv, "why": "сервер ≠ клиент"})
    tc = ev.st.get(E.GS[0], CEL)
    for code, i in sorted(tc.index().items()):
        f = E._f(tc.lines[i])
        c = cli.gemcard.get(code)
        if c is not None and len(f) > GEM_LVL_TOK and E._int(f[GEM_LVL_TOK]) != c[1]:
            rows.append({"code": code, "field": "уровень самоцвета", "server": E._int(f[GEM_LVL_TOK]), "client": c[1], "why": "сервер ≠ клиент"})
    sec("items", "предметы: поля сервер ≠ клиент (прочность, вес, уровни, класс, стопка, уровень самоцвета)", rows,
        "вес: у сервера ≤ 0 при загрузке становится 1, клиент читает младшее слово +72")
