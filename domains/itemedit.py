# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""itemedit.py — правка золота и свойств экземпляра снаряжения персонажа НЕ В ИГРЕ (волна А1). 16.11.2026.

ЗАЧЕМ. Владелец 16.11: «в окне инвентаря — карандаш у золота (поле, галочка, крестик)»; «у каждого снаряжения на
сервере свой экземпляр — дай править его характеристики, улучшение, эффекты, дополнительные свойства; в выпадающих
списках — ТОЛЬКО то, что допустимо для этого предмета».

ЭКЗЕМПЛЯР. Строка Joy1.dbo.Item = запись 57 б сервера (свой Uuid): +13 Durability, +14 Weight, +16…+22 Cell1…4 (гнёзда
самоцветов), +24 Upcount (ступень заточки), +25 AcuUpcnt, +26 MaxupCnt, +27 Updamage, +29…+48 пять пар опций
(Opidx/OpValue 1…5), +50 Owner (привязка) — соответствие по DBManager (research_item_props.md §0) и UPItemMove.
ЧТО ДОПУСТИМО (всё — из живых таблиц сервера и его кода; разбор с номерами строк — шапка domains/srvtables.py):
  ступень заточки   0…t44 + число ступеней OverUpgrade.txt с шансом > 0 (srvtables.upgrade_rule); вместе с ней —
                    Updamage (+27, «+N%» на иконке и сила предмета: атака/защита = Updamage × множитель + основа у
                    клиента) — сумма шагов свитков: шаг ∈ ItemUpgrade +8 подходящих свитков (+ усилитель Function_Table 97);
                    без Updamage ступень в игре меняет только «качество» (владелец 16.11);
  пара 1, пара 2    опции создания предмета: группы Item_Table t10 / t13 (sub_5340B0, :117685-117695) — тип из тех, что
                    выпадают в группе, значение из тех, что выпадают для типа (sub_4A7EE0 / sub_4A7FC0);
  пара 4            доп-опция заточки: группа SowelCombine col49 (+154), появляется на +6 (:99007-99016); на ступенях
                    7…20 значение растёт по OptionUpgrade.txt (:99018-99035) — в списке выбирается значение «как выпало
                    на +6», итог на текущей ступени считается так же, как у сервера; при ступени < 6 пары нет;
  пара 5            опция высшей переработки: группа col50 (+156, Recv_User_UpperRefine :98020);
  пара 3            сервер её не заполняет ни одним путём (12 мест выбора опций — :14133…:133903) — только показ;
  гнёзда            гнездо 0 — обычный самоцвет, гнёзда 1…t3 Item_Table — особые (Cellob t7 ≠ 0); t3 = 4 — гнёзд нет;
                    самоцвет допустим, если его не отверг бы sub_4DE250 (вид ↔ тип предмета, маска подтипа оружия, уровень
                    самоцвета ≤ уровня персонажа — sub_4DE530); вес предмета меняется на вес самоцветов, как у сервера
                    (CharCellobItemMove :87177/:87189); пустое гнездо после снятия — 0; у сервера снятый самоцвет
                    возвращается в сумку, панель строк в сумку не добавляет — самоцвет пропадает (предупреждение);
                    Uc гнезда = новый Uuid самоцвета или NULL, Fdate = время изменения (UPCellobMove);
  прочность         0…максимум Item_Table t1 (или текущее, если оно выше);  привязка  0 / 1 (текущее значение сохраняется).
  золото            строка кода 20551 в сумке 2; 0 … 2 147 483 647 (INT, asda_give.INT_MAX).
ЗАПИСЬ — как items.move: логин asda_ops, одна транзакция, проверка «учётка не в игре» под блокировкой Charinfo, сверка
«было» по Uuid; откат из журнала возвращает прежние значения. Побочных эффектов при импорте нет.
"""
from core import db
from core.ops import Operation, OpRefused, register
from domains import items, refdata, srvtables

GOLD_CODE = 20551
INT_MAX = 2147483647
UPCOUNT_MAX = 20                                 # доп-опция заточки растёт до +20 (GameServer.c:99018)
EDIT_TYPES = {0, 1, 2, 3, 4, 8, 9}               # броня и оружие (слоты 0–4, 8, 9) — экземпляры с опциями и гнёздами
PAIRS = {1: ("Opidx1", "OpValue1"), 2: ("Opidx2", "OpValue2"), 3: ("Opidx3", "Opvalue3"), 4: ("Opidx4", "Opvalue4"),
         5: ("OPidx5", "Opvalue5")}
CELLS = ("Cell1", "Cell2", "Cell3", "Cell4")
COLS = ("Uuid, Code, Plate, Posx, Durability, Weight, Owner, Upcount, AcuUpcnt, MaxupCnt, Updamage, "
        "Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3, Opidx4, Opvalue4, OPidx5, Opvalue5, Cell1, Cell2, Cell3, Cell4, "
        "Uc1, Uc2, Uc3, Uc4, Fdate")
WRITE = ("Durability", "Weight", "Owner", "Upcount", "AcuUpcnt", "MaxupCnt", "Updamage", "Opidx1", "OpValue1", "Opidx2", "OpValue2",
         "Opidx4", "Opvalue4", "OPidx5", "Opvalue5", "Cell1", "Cell2", "Cell3", "Cell4", "Uc1", "Uc2", "Uc3", "Uc4", "Fdate")


def _name(code):
    from core import i18n
    inf = refdata.item(code)
    return (inf["en"] or inf["ru"]) if i18n.is_en() else (inf["ru"] or inf["en"])


def _row(w, uid, idx, uuid, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT %s FROM Item%s WHERE Userindex = ? AND Charidx = ? AND Uuid = ?" % (COLS, hint), (uid, idx, uuid))
    if not r:
        raise OpRefused("предмета с этим серийным номером у персонажа нет — обновите страницу")
    r = r[0]
    r["Uuid"] = str(r["Uuid"])
    return r


def _char(w, uid, idx, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Lvl FROM Charinfo%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    if not r:
        raise OpRefused("персонаж не найден")
    return r[0]


def _editable(row):
    code = int(row["Code"])
    rule = srvtables.item_rule(code)
    if not rule or rule["type"] not in EDIT_TYPES:
        raise OpRefused("свойства правятся только у брони и оружия (у этого предмета нет экземпляра с опциями)")
    if int(row["Plate"]) not in (1, 2, 3, 5):
        raise OpRefused("предмет сейчас не в сумке, не надет и не на складе (например, выставлен на аукцион)")
    return rule


def _base_of(t, value, upcount, g):
    """Значение доп-опции «как выпало на +6» по итоговому значению на ступени upcount (обратный расчёт)."""
    for v, _p in srvtables.group_values(g, t):
        if srvtables.upgrade_value(t, v, upcount) == value:
            return v
    return None


def per_step(urule):
    """Возможные прибавки Updamage за одну удачную заточку: шаг свитка или шаг + усилитель (Function_Table 97)."""
    out = set(urule["steps"])
    if urule["boost_max"]:
        out |= {s + urule["boost_max"] for s in urule["steps"]}
    return sorted(out)


_live_step = {"at": 0.0, "v": None}


def default_step(urule):
    """Шаг «+%» за ступень по умолчанию: самый частый на живой базе (Updamage / Upcount у заточенных предметов, кэш 10 мин;
    16.11 — 8 % у 91 из 125), если он есть среди шагов этого предмета; иначе — шаг обычного свитка с наибольшим шансом."""
    import time
    if time.monotonic() - _live_step["at"] > 600:
        try:
            with db.GameReader("joy1") as r:
                rows = r.rows("SELECT TOP 1 Updamage / Upcount AS s, COUNT(*) AS n FROM Item WHERE Upcount > 0 AND Updamage > 0 "
                              "AND Updamage % Upcount = 0 GROUP BY Updamage / Upcount ORDER BY COUNT(*) DESC")
            _live_step.update(at=time.monotonic(), v=int(rows[0]["s"]) if rows else None)
        except db.DbError:
            _live_step.update(at=time.monotonic(), v=None)
    v = _live_step["v"]
    return v if v in per_step(urule) else urule["default_step"]


def updamage_range(urule, up):
    """Наименьшая и наибольшая «+N%» на ступени up (для текста отказа и подсказки)."""
    if up <= 0:
        return 0, 0
    first = per_step(urule)
    rest = per_step({"steps": urule["sure_steps"], "boost_max": urule["boost_max"]}) or first
    n1 = min(up, urule["max_normal"])
    return (n1 * first[0] + (up - n1) * rest[0], n1 * first[-1] + (up - n1) * rest[-1]) if first else (0, 0)


def nearest_updamage(urule, up, d):
    """Ближайшее к d достижимое значение «+N%» на ступени up."""
    lo, hi = updamage_range(urule, up)
    for k in range(0, hi - lo + 1):
        for v in (d - k, d + k):
            if lo <= v <= hi and srvtables.updamage_reachable(urule, up, v):
                return v
    return lo


def auto_updamage(row, up, urule):
    """Updamage для новой ступени, если «+%» не выбран явно: прежний процент за ступень сохраняется; у незаточенного —
    шаг по умолчанию. Та же формула — в панели (app.js upTotal)."""
    cur_up, cur_d = int(row["Upcount"] or 0), int(row["Updamage"] or 0)
    if up <= 0:
        return 0
    if cur_up > 0 and cur_d > 0:
        return int(cur_d * up / cur_up + 0.5)
    return up * default_step(urule)


def describe(uid, idx, uuid):
    """Текущие свойства экземпляра и ВСЕ допустимые варианты (для выпадающих списков панели)."""
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        row = _row(ad, int(uid), int(idx), uuid)
        ch = _char(ad, int(uid), int(idx))
        ok, why = items.online_state(ad, int(uid))
    rule = _editable(row)
    code = int(row["Code"])
    groups = srvtables.item_option_groups(code)
    up = int(row["Upcount"] or 0)
    urule = srvtables.upgrade_rule(code)

    def pair_info(k):
        g = groups.get(k, 0)
        types = [{"type": t, "chance": p, "name": refdata.option_name(t),
                  "values": [{"value": v, "chance": vp, "label": refdata.option_name(t, v)} for v, vp in srvtables.group_values(g, t)]}
                 for t, p in srvtables.group_types(g)] if g else []
        a, b = PAIRS[k]
        cur_t, cur_v = row[a], row[b]
        cur = None if cur_t in (None, -1, 0) else {"type": cur_t, "value": cur_v, "label": refdata.option_name(cur_t, cur_v)}
        return {"pair": k, "group": g, "types": types, "cur": cur}

    pairs = {k: pair_info(k) for k in (1, 2, 4, 5)}
    if pairs[4]["cur"]:
        pairs[4]["cur"]["base"] = _base_of(pairs[4]["cur"]["type"], pairs[4]["cur"]["value"], up, groups[4])
    # на клиент — таблица прироста только для типов группы col49 (значение на любой ступени считает и панель)
    ou = srvtables.option_upgrade()
    growth = {t["type"]: list(ou.get(t["type"], (0, 0))) for t in pairs[4]["types"]}
    p3 = row["Opidx3"]
    nsock = srvtables.socket_count(code)
    cells = []
    for i, col in enumerate(CELLS):
        cur = row[col]
        opts = []
        if i < nsock:
            for sc in sorted(srvtables.table("Cellob_Table.txt")):
                if srvtables.sowel_error(code, sc, i, int(ch["Lvl"] or 0)) == 0:
                    c = srvtables.cellob(sc)
                    opts.append({"code": sc, "name": _name(sc), "lvl": c["lvl"], "weight": c["weight"]})
        cells.append({"socket": i, "enabled": i < nsock, "cur": cur if cur and cur > 7000 else None,
                      "cur_name": _name(cur) if cur and cur > 7000 else "", "options": opts})
    return {"uuid": row["Uuid"], "code": code, "name": _name(code), "type": rule["type"], "lvl_char": ch["Lvl"],
            "upcount": up, "upcount_max": urule["max"], "acu": row["AcuUpcnt"], "maxup": row["MaxupCnt"],
            "upgrade": {"steps": per_step(urule), "base_steps": urule["steps"], "default_step": default_step(urule), "t44": urule["t44"],
                        "max_normal": urule["max_normal"], "sure_steps": urule["sure_steps"],
                        "boost_max": urule["boost_max"]},
            "updamage": row["Updamage"], "durability": row["Durability"],
            "durability_max": max(rule["durability_max"], int(row["Durability"] or 0)), "owner": row["Owner"],
            "weight": row["Weight"], "pairs": pairs, "pair3": None if p3 in (None, -1, 0) else
            {"type": p3, "value": row["Opvalue3"], "label": refdata.option_name(p3, row["Opvalue3"])},
            "growth": growth, "cells": cells, "editable": ok, "edit_block": why}


def plan(w, p, lock=False):
    """Новые значения столбцов по запросу панели + проверка допустимости → (строка_было, {столбец: стало}, текст)."""
    uid, idx = int(p["uid"]), int(p["idx"])
    row = _row(w, uid, idx, str(p["uuid"]), lock)
    ch = _char(w, uid, idx, lock)
    rule = _editable(row)
    code = int(row["Code"])
    groups = srvtables.item_option_groups(code)
    s = p.get("set") or {}
    if not isinstance(s, dict):
        raise OpRefused("неверные параметры правки предмета")
    # ПЕРЕПРОВЕРКА А1 К1: меняется ТОЛЬКО то, что прислано. Поле, которого нет в запросе, остаётся как есть — даже если его
    # текущее значение вне правил сервера (нестандартную опцию нельзя стереть случайно, правя прочность).
    new, warn = {}, []
    cur_up = int(row["Upcount"] or 0)
    up = cur_up
    if "upcount" in s:
        up = int(s["upcount"])
        urule = srvtables.upgrade_rule(code)
        if not (0 <= up <= urule["max"]) and up != cur_up:
            raise OpRefused("ступень заточки — от 0 до %d" % urule["max"])
        if up != cur_up:
            new["Upcount"] = up
            # ПЕРЕПРОВЕРКА А1 В1: ступень — вместе со счётчиками, которые сервер сверяет при заточке (GameServer.c:98913-98950):
            #   MaxupCnt = max(SowelCombine t44, ступень) (при ступени ≥ t44 сервер держит MaxupCnt == Upcount, иначе отказ 7);
            #   AcuUpcnt = ступени (перепроверка 3 В7: при AcuUpcnt ≥ t44 сервер требует Upcount ≥ t44, иначе отказ 6, а
            #   пройти t44 можно только при AcuUpcnt == Upcount — любые «лишние попытки» навсегда снижают предел заточки;
            #   на живой базе у всех предметов выше порога AcuUpcnt == Upcount)
            t44 = srvtables.sowel_maxup(code)
            new["MaxupCnt"] = max(t44, up)
            new["AcuUpcnt"] = up
    # «+N%» заточки (Updamage, +27): вместе со ступенью (владелец 16.11: «в игре сменилось только качество, +n% нет»).
    # Сумма шагов удачных заточек: каждая прибавляет шаг свитка (+ усилитель) — допустимо up × мин. шаг … up × макс. шаг.
    if "updamage" in s or "upstep" in s or "Upcount" in new:
        urule = srvtables.upgrade_rule(code)
        cur_d = int(row["Updamage"] or 0)
        explicit = s.get("updamage") not in (None, "")
        d = int(s["updamage"]) if explicit else (auto_updamage(row, up, urule) if "Upcount" in new else cur_d)
        if not explicit and s.get("upstep") not in (None, ""):
            # панель шлёт шаг за ступень; сумму — ближайшую достижимую (выше max_normal — только шаги свитка 91)
            st = int(s["upstep"])
            if st not in per_step(urule):
                raise OpRefused("шаг заточки %s %% — не из шагов свитков этого предмета" % st)
            d = up * st
        lo, hi = updamage_range(urule, up)
        if not explicit and d != cur_d and not srvtables.updamage_reachable(urule, up, d):
            # перепроверка 5 М1: прежний процент мог прийти благословением/извлечением с другого предмета (:118190,
            # :117940) и не делиться на ступени — берём ближайшее достижимое
            d = nearest_updamage(urule, up, d)
        if d != cur_d and not srvtables.updamage_reachable(urule, up, d):
            raise OpRefused("процент заточки на +%d — от %d до %d %% и набираемый шагами свитков (%s)"
                            % (up, lo, hi, ", ".join(map(str, per_step(urule))) or "—"))
        if d != cur_d:
            new["Updamage"] = d
            if (d >= 88) != (cur_d >= 88):
                # перепроверка 5 М2: Recv_User_Disassemble (:98327) — от 88 % предмет разбирается в камень заточки
                warn.append("прибавка %s 88 %%: при разборе предмет %s" % ("достигает" if d >= 88 else "опускается ниже",
                            "даст камень заточки" if d >= 88 else "больше не даст камня заточки"))

    def opt(k, val):
        # пустая пара — −1/−1, как пишут сервер и процедуры (INSERT … -1,-1; перепроверка 3 М21); пару 4 сброс заточки
        # сервера оставляет −1/0 — её задаёт вызывающий
        if val is None or val == "" or (isinstance(val, dict) and val.get("type") in (None, "", -1)):
            return -1, -1
        if not isinstance(val, dict):
            raise OpRefused("неверные параметры правки предмета")
        t, v = int(val["type"]), int(val["value"])
        g = groups.get(k, 0)
        if t not in [x for x, _ in srvtables.group_types(g)]:
            raise OpRefused("опция %s недопустима для этого предмета (пара %d, группа %s)" % (t, k, g))
        if v not in [x for x, _ in srvtables.group_values(g, t)]:
            raise OpRefused("значение %s недопустимо для опции %s этого предмета" % (v, t))
        return t, v

    pairs = s.get("pairs") or {}
    if not isinstance(pairs, dict):
        raise OpRefused("неверные параметры правки предмета")
    for k in (1, 2, 5):
        if str(k) in pairs:
            t, v = opt(k, pairs[str(k)])
            if t == -1 and row[PAIRS[k][0]] in (None, -1, 0):
                continue                                  # «нет» у уже пустой пары — не трогать (перепроверка 3 М21)
            new[PAIRS[k][0]], new[PAIRS[k][1]] = t, v
    had4 = row["Opidx4"] not in (None, -1, 0)
    if "4" in pairs:
        if up < 6 and pairs["4"] not in (None, "") and isinstance(pairs["4"], dict) and pairs["4"].get("type") not in (None, "", -1):
            raise OpRefused("доп-опция заточки появляется только с +6")
        t, base = opt(4, pairs["4"]) if up >= 6 else (-1, 0)
        if t != -1 or had4:
            new["Opidx4"], new["Opvalue4"] = t, (srvtables.upgrade_value(t, base, up) if t != -1 else 0)
        if t == -1 and up >= 6 and groups.get(4):
            warn.append("доп-опция заточки не выбрана — сервер на +6 выдал бы её из группы предмета")
    elif "Upcount" in new:
        if up < 6:
            if row["Opidx4"] not in (None, -1, 0):
                new["Opidx4"], new["Opvalue4"] = -1, 0
                warn.append("ступень ниже +6 — доп-опция заточки снимается")
        elif row["Opidx4"] not in (None, -1, 0):
            base = _base_of(row["Opidx4"], row["Opvalue4"], cur_up, groups[4])
            if base is not None:                                     # сменили только ступень — пересчитать как сервер
                new["Opvalue4"] = srvtables.upgrade_value(row["Opidx4"], base, up)
            else:
                warn.append("доп-опция заточки нестандартная (её значения нет в таблице) — оставлена как есть")
        elif cur_up < 6 and groups.get(4):                        # перепроверка 3 М20: подняли до +6 и выше без опции
            warn.append("доп-опция заточки не выбрана — сервер на +6 выдал бы её из группы предмета")
    cells = s.get("cells") or {}
    if not isinstance(cells, dict):
        raise OpRefused("неверные параметры правки предмета")
    if cells:
        import datetime
        import uuid as _uuid
        weight = int(row["Weight"] or 0)
        nsock = srvtables.socket_count(code)
        if any(str(k) not in ("0", "1", "2", "3") for k in cells):          # перепроверка 3 М16: «00», «+0» — то же гнездо
            raise OpRefused("неверные параметры правки предмета")
        for key, want in cells.items():
            i = int(key)
            col, uc = CELLS[i], "Uc%d" % (i + 1)
            old = row[col]
            if want in (None, "", 0, -1):
                want = 0 if old and old > 7000 else old          # снять самоцвет → 0 (как сервер), пустое — как было
            else:
                want = int(want)
                # ПЕРЕПРОВЕРКА А1 В4: в гнездо — только самоцвет, который сервер принял бы (никаких иных чисел)
                if i >= nsock:
                    raise OpRefused("у этого предмета нет гнезда %d" % (i + 1))
                e = srvtables.sowel_error(code, want, i, int(ch["Lvl"] or 0))
                if e:
                    raise OpRefused("самоцвет %s нельзя вставить в гнездо %d (код сервера %d)" % (want, i + 1, e))
            if want == old:
                continue
            if old and old > 7000:
                weight -= srvtables.cellob(old)["weight"] if srvtables.cellob(old) else 0
                warn.append("снятый из гнезда %d самоцвет пропадёт: в игре сервер вернул бы его в сумку, а панель строк в "
                            "сумку не добавляет" % (i + 1))
            if want and want > 7000:
                weight += srvtables.cellob(want)["weight"]
            new[col] = want
            # ПЕРЕПРОВЕРКА А1 В2: Uc — Uuid вставленного самоцвета (UPCellobMove: Uc = Uuid самоцвета из сумки); панель
            # вставляет новый экземпляр — свой Uuid; снятие — NULL. Fdate = время изменения (так пишет процедура).
            new[uc] = str(_uuid.uuid4()).upper() if want and want > 7000 else None
            new["Fdate"] = datetime.datetime.now().replace(microsecond=0)
        if not (0 <= weight <= 32767):
            raise OpRefused("вес предмета вышел бы за пределы (%d)" % weight)
        new["Weight"] = weight
    if "durability" in s and s["durability"] not in (None, ""):
        d = int(s["durability"])
        dmax = max(rule["durability_max"], int(row["Durability"] or 0))
        if not (0 <= d <= dmax):
            raise OpRefused("прочность — от 0 до %d" % dmax)
        new["Durability"] = d
    if "owner" in s and s["owner"] not in (None, ""):
        o = int(s["owner"])
        if o not in (0, 1, int(row["Owner"] or 0)):
            raise OpRefused("привязка — 0 (не привязан) или 1 (привязан)")
        new["Owner"] = o
    changed = {k: v for k, v in new.items() if row.get(k) != v}
    if not changed:
        raise OpRefused("ничего не меняется")
    shown = {k: v for k, v in changed.items() if k not in ("Fdate",) and not k.startswith("Uc")}
    inf = refdata.item(code)                     # текст = запись журнала — по-русски (перепроверка 5 М6)
    text = "%s (%s): %s" % (inf["ru"] or inf["en"] or "без названия", code, ", ".join("%s %s → %s" % (k, row.get(k), v) for k, v in shown.items()))
    return row, changed, text, warn


def _ms(v):
    """datetime → «ГГГГ-ММ-ДД ЧЧ:ММ:СС.ммм» (как CONVERT(varchar(23), …, 121))."""
    return v.strftime("%Y-%m-%d %H:%M:%S.") + "%03d" % (v.microsecond // 1000)


def _apply(w, uid, idx, uuid, before, after, stale="предмет изменился, пока вы смотрели предпросмотр — ничего не записано"):
    """UPDATE только столбцов из WRITE (имена приходят и из журнала при откате — перепроверка А1 М6)."""
    if any(k not in WRITE for k in after) or set(before) != set(after):
        raise OpRefused("в журнале неожиданные столбцы — откат не выполнен")
    # Fdate из журнала приходит строкой «ГГГГ-ММ-ДД ЧЧ:ММ:СС.ммм»; SQL Server с русским языком логина читает её как
    # ГГГГ-ДД-ММ (ошибка 242) — отдаём datetime, а не строку (живой самотест 16.11, откат гнезда)
    import datetime
    fix = lambda k, v: datetime.datetime.fromisoformat(v) if k == "Fdate" and isinstance(v, str) else v
    before = {k: fix(k, v) for k, v in before.items()}
    after = {k: fix(k, v) for k, v in after.items()}
    sets = ", ".join("%s = ?" % k for k in after)
    conds, wp = [], []
    for k in after:
        b = before[k]
        if isinstance(b, datetime.datetime):
            # перепроверка 3 М15: «Fdate = ?» с параметром зависит от уровня совместимости базы (≥ 130 — datetime2,
            # .997 не совпадает); строковое сравнение в формате 121 от уровня не зависит
            conds.append("CONVERT(varchar(23), %s, 121) = ?" % k)
            wp.append(_ms(b))
        else:
            conds.append("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (k, k))
            wp += [b, b]
    params = list(after.values()) + [uid, idx, uuid] + wp
    n = w.execute("UPDATE Item SET %s WHERE Userindex = ? AND Charidx = ? AND Uuid = ? AND %s" % (sets, " AND ".join(conds)),
                  params)
    if n != 1:
        raise OpRefused(stale)


def _sig(row, changed):
    """Отпечаток изменений для сверки с подтверждённым предпросмотром: «было → стало» по каждому столбцу (перепроверка 3
    М17 — чужая правка между предпросмотром и записью, даже с тем же «стало», даёт отказ). Новые Uuid самоцветов и время
    создаёт сама служба — они не в счёт."""
    return {k: [row.get(k), v] for k, v in changed.items() if k != "Fdate" and not k.startswith("Uc")}


@register
class ItemsEdit(Operation):
    name, title, perm, reversible = "items.edit", "Предмет: свойства экземпляра", "players.items_props", True

    def target(self, p):
        return "item:%s/%s/%s" % (p.get("uid"), p.get("idx"), p.get("uuid"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                row, changed, text, warn = plan(ad, p)
                ok, why = items.online_state(ad, int(p["uid"]))
        except (KeyError, TypeError, ValueError, db.DbError):
            raise OpRefused("неверные параметры правки предмета")
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "changes": changed, "expect": _sig(row, changed),
                "warnings": warn + ([items.RECENT_WARN] if items.recently_left(int(p["uid"])) else [])}

    def apply(self, ctx, p, prev):
        uid, idx = int(p["uid"]), int(p["idx"])
        w = db.GameWriter("joy1")
        try:
            row, changed, text, _w = plan(w, p, lock=True)
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            sig = _sig(row, changed)
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):   # ревизия А1 R5
                raise OpRefused("пока вы смотрели предпросмотр, предмет изменился — повторите")
            before = {k: row[k] for k in changed}
            _apply(w, uid, idx, row["Uuid"], before, changed)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "uuid": row["Uuid"], "values": before},
                "after": {"uid": uid, "idx": idx, "uuid": row["Uuid"], "values": changed, "before": before}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, idx, uuid = a.get("uid"), a.get("idx"), a.get("uuid")
        if not a.get("values"):
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            _char(w, uid, idx, lock=True)
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            # условие WHERE = «стало»: менялся — отказ (перепроверка 3 М14: в том числе склад сервера, он меняет Fdate)
            _apply(w, uid, idx, uuid, a["values"], a["before"],
                   stale="предмет с тех пор менялся (в игре или в панели) — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": a["values"], "after": a["before"], "message": "свойства предмета возвращены",
                "_commit": w.commit, "_close": w.close}


@register
class GoldSet(Operation):
    name, title, perm, reversible = "gold.set", "Золото персонажа", "players.items_props", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def _plan(self, w, p, lock=False):
        uid, idx = int(p["uid"]), int(p["idx"])
        try:
            amount = int(str(p["amount"]).replace(" ", "").replace(",", ""))
        except (KeyError, ValueError):
            raise OpRefused("золото — целое число")
        if not (0 <= amount <= INT_MAX):
            raise OpRefused("золото — от 0 до %d" % INT_MAX)
        _char(w, uid, idx, lock)
        hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
        r = w.rows("SELECT Uuid, Amount FROM Item%s WHERE Userindex = ? AND Charidx = ? AND Plate = 2 AND Code = ?" % hint,
                   (uid, idx, GOLD_CODE))
        if not r:
            raise OpRefused("у персонажа нет строки золота (сумка 2) — её создаёт сервер; панель строки не добавляет")
        if int(r[0]["Amount"]) == amount:
            raise OpRefused("золото уже %s" % amount)
        return str(r[0]["Uuid"]), int(r[0]["Amount"]), amount

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uuid, old, new = self._plan(ad, p)
                ok, why = items.online_state(ad, int(p["uid"]))
        except (KeyError, TypeError, ValueError, db.DbError):
            raise OpRefused("неверные параметры правки золота")
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": "золото: %s → %s" % (old, new), "old": old, "new": new, "expect": old,
                "warnings": [items.RECENT_WARN] if items.recently_left(int(p["uid"])) else []}

    def apply(self, ctx, p, prev):
        try:                                               # остаток R13: мусор в параметрах — отказ, а не 500
            uid, idx = int(p["uid"]), int(p["idx"])
            expect = int(p["expect"]) if "expect" in p else None
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры правки золота")
        w = db.GameWriter("joy1")
        try:
            uuid, old, new = self._plan(w, p, lock=True)
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            if old != prev["old"] or (expect is not None and expect != old):          # ревизия А1 R5
                raise OpRefused("золото изменилось, пока вы смотрели предпросмотр — повторите")
            if w.execute("UPDATE Item SET Amount = ? WHERE Userindex = ? AND Charidx = ? AND Uuid = ? AND Amount = ?",
                         (new, uid, idx, uuid, old)) != 1:
                raise OpRefused("золото изменилось — ничего не записано")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "uuid": uuid, "amount": old},
                "after": {"uid": uid, "idx": idx, "uuid": uuid, "amount": new, "old": old}, "message": "золото: %s → %s" % (old, new),
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, idx, uuid = a.get("uid"), a.get("idx"), a.get("uuid")
        w = db.GameWriter("joy1")
        try:
            _char(w, uid, idx, lock=True)
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            if w.execute("UPDATE Item SET Amount = ? WHERE Userindex = ? AND Charidx = ? AND Uuid = ? AND Amount = ?",
                         (a["old"], uid, idx, uuid, a["amount"])) != 1:
                raise OpRefused("золото с тех пор изменилось — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": {"amount": a["amount"]}, "after": {"amount": a["old"]}, "message": "золото возвращено: %s" % a["old"],
                "_commit": w.commit, "_close": w.close}
