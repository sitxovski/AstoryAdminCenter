# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""itemgive.py — выдать и изъять предмет персонажа НЕ В ИГРЕ (волна А1, план §4.В; перенос вкладки «Выдача» старой утилиты
AstoryAdminCenter/tools/Admin/asda_give.py). 18.11.2026.

РАЗБОР — Reports/admin_center/research_item_give.md. РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11: своя процедура adm; сумки 1, 2 И склад;
опции выбирает оператор, основной камень — как в таблице предмета, есть «Случайно» (бросок как у сервера); откат изъятия — в ту
же ячейку, занята — в первую свободную той же сумки; журнал — свой (adm.ItemLedger) и стоковый JoyLog1.dbo.AdminitemLog.

ПРАВИЛО КОДА — как серверная sub_5340B0 (asda_give.item_spec, проверено на живых данных; research_item_props §2–§7):
  1…max Function_Table  → сумка 1, по ячейке на штуку, Amount = заряды (t9), вес t2, прочность 0; сроковые (тип 15/65) —
                          Rdate НЕ ставится, срок пойдёт с первого использования (как у сервера, research §3.2);
                          P100 (патч включён, код в AsdaChargeGroup с ключом ≠ 0): заряды каждой штуки — в первую по Posx ячейку
                          того же ключа, где хватает места до потолка, иначе новая ячейка; код ячейки не меняется, вес не растёт;
  7001…max Cellob_Table → сумка 2, Amount 0, вес t3, прочность t4, Owner t17;
  20551…max Item_Table  → сумка 1, если t24 == 3 или тип ∈ {0–4, 8, 9, 12–15} (снаряжение: прочность t1, вес t2, MaxupCnt —
                          SowelCombine t44; пары 1–2 — из групп t10/t13, гнездо 0 и ступень — исходы SowelCombine, см.
                          srvtables.creation_choices); иначе сумка 2: тип 10 — Amount = t29; стопка (t23) — к ПЕРВОЙ ячейке того
                          же кода (вес = количество × вес), иначе новая; прочее — по ячейке на штуку.
  Отказ: золото 20551 (своя операция), коды вне таблиц (в т.ч. книга заданий 2001…), склад без ёмкости, перегруз.
  Склад (Plate 5): ёмкость min(WareCount, 270); вес склада в вес персонажа не входит (как у сервера: SUM(Weight) Plate <> 5).
ИЗЪЯТИЕ — вся строка или часть стопки / зарядов (итог ≥ 1); только сумки 1, 2 и склад (надетое — сначала снять); золото — нет.
ЗАПИСЬ — logиn asda_ops: «учётка не в игре» под блокировкой (items.online_state) → EXEC adm.ItemGive / ItemTake (одна
  транзакция; процедура проверяет ячейку и пишет журналы). Откат — adm.ItemUndo по номерам записей adm.ItemLedger, только если
  предмет с тех пор не менялся. Побочных эффектов при импорте нет.
"""
import re

from core import bridge, db
from core.ops import Operation, OpRefused, register
from domains import items, refdata, srvtables

GOLD_CODE = 20551
INT_MAX = 2147483647
WEIGHT_MAX = 32767
QTY_MAX_CELLS = 60                 # штук «по ячейке» за раз — не больше ёмкости сумки
QTY_MAX_STACK = 1000000            # стопка за раз
PLATE1_TYPES = {0, 1, 2, 3, 4, 8, 9, 12, 13, 14, 15}
QUIVER_TYPE = 10
TIMED_FUNCTIONS = {15, 65}


def _refuse_db(ex, proc):
    m = re.search(r"%s: ([^\[\]]+?)(?: \(\d+\))?$" % re.escape(proc), str(ex))
    return OpRefused(("отказ сервера: " + m.group(1)) if m else "ошибка базы: %s" % ex)


def item_spec(code):
    """Правило выдачи кода → dict(kind, plate, stack, amount_each, unit_weight, dur, maxup, owner, gear, timed)."""
    code = int(code)
    if code == GOLD_CODE:
        raise OpRefused("золото выдаётся правкой золота (карандаш у золота в инвентаре)")
    fmax, cmax, imax = (srvtables.table_max(n) for n in ("Function_Table.txt", "Cellob_Table.txt", "Item_Table.txt"))
    if 1 <= code <= fmax:
        f = srvtables.function_rule(code)
        if not f:
            raise OpRefused("кода %d нет в Function_Table сервера" % code)
        return dict(kind="function", plate=1, stack=False, amount_each=f["charges"], unit_weight=f["weight"], dur=0, maxup=0,
                    owner=0, gear=False, timed=f["type"] in TIMED_FUNCTIONS)
    if srvtables.CELLOB_BASE <= code <= cmax:
        c = srvtables.cellob(code)
        if not c:
            raise OpRefused("кода %d нет в Cellob_Table сервера" % code)
        return dict(kind="cellob", plate=2, stack=False, amount_each=0, unit_weight=c["weight"], dur=c["dur_cost"], maxup=0,
                    owner=c["owner"], gear=False, timed=False)
    if srvtables.ITEM_BASE < code <= imax:
        r = srvtables.item_rule(code)
        if not r:
            raise OpRefused("кода %d нет в Item_Table сервера" % code)
        f = srvtables.table("Item_Table.txt")[code]
        weight = srvtables._i(f, 2)
        if r["plate_flag"] == 3 or r["type"] in PLATE1_TYPES:
            return dict(kind="gear", plate=1, stack=False, amount_each=0, unit_weight=weight, dur=r["durability_max"],
                        maxup=srvtables.sowel_maxup(code), owner=0, gear=True, timed=False)   # перепроверка 18 М2: пары 1–2 у ВСЕГО снаряжения сумки 1 (в т.ч. t24 == 3)
        if r["type"] == QUIVER_TYPE:
            # перепроверка 18 К2: ОТСТУПЛЕНИЕ от sub_5340B0 (сервер создаёт колчан с Amount 0) — правило старой утилиты asda_give:
            # выдаётся полным (Amount = ёмкость t29), иначе оператор выдавал бы пустой колчан
            return dict(kind="quiver", plate=2, stack=False, amount_each=srvtables._i(f, 29), unit_weight=weight,
                        dur=r["durability_max"], maxup=0, owner=0, gear=False, timed=False)
        st = r["stack"] != 0
        return dict(kind="stack" if st else "single", plate=2, stack=st, amount_each=0, unit_weight=weight,
                    dur=r["durability_max"], maxup=0, owner=0, gear=False, timed=False)
    raise OpRefused("код %d не существует на сервере (вне Function / Cellob / Item_Table)" % code)


def _name(code):
    inf = refdata.item(code)
    return inf["ru"] or inf["en"] or "без названия"


def _pair_lists(code):
    """Допустимые опции пар 1–2 при создании (как itemedit.describe): {пара: [типы с значениями]}."""
    groups = srvtables.item_option_groups(code)
    out = {}
    for k in (1, 2):
        g = groups.get(k, 0)
        out[k] = [{"type": t, "chance": p, "name": refdata.option_name(t),
                   "values": [{"value": v, "chance": vp, "label": refdata.option_name(t, v)} for v, vp in srvtables.group_values(g, t)]}
                  for t, p in srvtables.group_types(g)] if g else []
    return out


def describe(code):
    """Что панель покажет в окне выдачи: сумка, вид, и для снаряжения — допустимые пары, исходы гнезда 0 и ступени."""
    s = item_spec(code)
    out = {"code": int(code), "name": refdata.item(code)["name"] or _name(code), "kind": s["kind"], "plate": s["plate"],
           "stack": s["stack"], "weight": s["unit_weight"], "timed": s["timed"], "charge": False}
    if s["kind"] == "function":
        out["charge"] = _charge_key(None, int(code)) is not None
    if s["gear"]:
        ch = srvtables.creation_choices(code)
        out["pairs"] = _pair_lists(code)
        out["stones"] = [{"code": c, "name": _name(c) if c else "", "chance": p} for c, p in ch["stones"]]
        out["upcounts"] = [{"value": v, "chance": p} for v, p in ch["upcounts"]]
        out["default"] = {"stone": ch["stones"][0][0], "upcount": ch["upcounts"][0][0], "pairs": {1: None, 2: None}}
    return out


_ckeys = {}


def _charge_key(w, code):
    """Ключ слияния зарядов P100 (dbo.AsdaChargeGroup.GroupKey ≠ 0) или None (P100 выключен / не спецпредмет с зарядами)."""
    if srvtables.charge_cap() is None:
        return None
    if w is None:
        with db.GameReader("joy1") as r:
            rows = r.rows("SELECT GroupKey FROM dbo.AsdaChargeGroup WHERE Code = ?", (int(code),))
    else:
        rows = w.rows("SELECT GroupKey FROM dbo.AsdaChargeGroup WHERE Code = ?", (int(code),))
    k = rows[0]["GroupKey"] if rows else None
    return int(k) if k else None


def _opts(code, s, o):
    """Опции снаряжения из запроса → dict(Cell1, Upcount, Opidx1, OpValue1, Opidx2, OpValue2, stone_weight). Проверка — как у
    сервера: пары — только из групп предмета; гнездо 0 и ступень — только исходы, которые сервер может дать."""
    empty = {"Cell1": 0, "Upcount": 0, "Opidx1": -1, "OpValue1": 0, "Opidx2": -1, "OpValue2": 0, "stone_weight": 0}
    if not s["gear"]:
        if o:
            raise OpRefused("опции и самоцвет задаются только у брони и оружия")
        return empty
    o = o or {}
    if not isinstance(o, dict):
        raise OpRefused("неверные параметры выдачи")
    groups = srvtables.item_option_groups(code)
    res = dict(empty)
    pairs = o.get("pairs") or {}
    if not isinstance(pairs, dict):
        raise OpRefused("неверные параметры выдачи")
    for k in (1, 2):
        val = pairs.get(str(k), pairs.get(k))
        if val in (None, "") or (isinstance(val, dict) and val.get("type") in (None, "", -1)):
            continue
        if not isinstance(val, dict):
            raise OpRefused("неверные параметры выдачи")
        try:
            t, v = int(val["type"]), int(val["value"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры выдачи")
        g = groups.get(k, 0)
        if not g or t not in [x for x, _ in srvtables.group_types(g)]:
            raise OpRefused("опция %s недопустима для этого предмета (пара %d)" % (t, k))
        if v not in [x for x, _ in srvtables.group_values(g, t)]:
            raise OpRefused("значение %s недопустимо для опции %s этого предмета" % (v, t))
        res["Opidx%d" % k], res["OpValue%d" % k] = t, v
    ch = srvtables.creation_choices(code)
    try:
        stone = int(o.get("stone") or 0)
        up = int(o.get("upcount") or 0)
    except (TypeError, ValueError):
        raise OpRefused("неверные параметры выдачи")
    if stone not in [c for c, _ in ch["stones"]]:
        raise OpRefused("самоцвет %s: в гнездо при создании этого предмета сервер его не ставит (таблица SowelCombine)" % stone)
    if up not in [v for v, _ in ch["upcounts"]]:
        raise OpRefused("ступень %s: при создании этого предмета сервер такую не даёт (таблица SowelCombine)" % up)
    res["Cell1"], res["Upcount"] = stone, up
    res["stone_weight"] = srvtables.cellob(stone)["weight"] if stone else 0
    return res


def _weights(w, uid, idx, lock):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    cur = w.rows("SELECT ISNULL(SUM(CAST(Weight AS INT)), 0) AS s FROM Item%s WHERE Userindex = ? AND Charidx = ? AND Plate <> 5"
                 % hint, (uid, idx))[0]["s"]
    mx = w.rows("SELECT MaxWeight FROM Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, idx))
    return int(cur or 0), (int(mx[0]["MaxWeight"] or 0) & 0xFFFF) if mx else 0    # MaxWeight — u16 в smallint (asda_give)


def _amounts(w, uid, idx, plate, lock):
    """{Posx: (Code, Amount, Weight)} сумки (с Weight — для стопок)."""
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    return {int(r["Posx"]): (int(r["Code"]), int(r["Amount"] or 0), int(r["Weight"] or 0)) for r in w.rows(
        "SELECT Posx, Code, Amount, Weight FROM Item%s WHERE Userindex = ? AND Charidx = ? AND Plate = ?" % hint, (uid, idx, plate))}


def _qty(v, top):
    try:
        q = int(str(v).replace(" ", ""))
    except (TypeError, ValueError):
        raise OpRefused("количество — целое число")
    if not (1 <= q <= top):
        raise OpRefused("количество — от 1 до %d" % top)
    return q


def plan_give(w, p, lock=False):
    """→ dict(uid, idx, code, plate, cap, ops[{mode, posx, amount, weight, expect}], opts, text, warnings, sig)."""
    try:
        uid, idx, code = int(p["uid"]), int(p["idx"]), int(p["code"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры выдачи")
    s = item_spec(code)
    ch, cells, caps = items._load(w, uid, idx, lock)
    to = p.get("to") or "bag"
    if to not in ("bag", "ware"):
        raise OpRefused("неверные параметры выдачи")
    plate = 5 if to == "ware" else s["plate"]
    cap = caps[plate]
    if cap < 1:
        raise OpRefused("у персонажа нет склада (ёмкость 0)")
    o = _opts(code, s, p.get("opts"))
    occ = _amounts(w, uid, idx, plate, lock)
    free = [x for x in range(cap) if x not in occ]
    warn, ops = [], []
    key = _charge_key(w, code) if s["kind"] == "function" else None
    if s["stack"]:
        q = _qty(p.get("qty", 1), QTY_MAX_STACK)
        add_w = q * s["unit_weight"]
        same = sorted(x for x, r in occ.items() if r[0] == code)
        if same:
            x = same[0]
            c0, a0, w0 = occ[x]
            if a0 + q > INT_MAX or w0 + add_w > WEIGHT_MAX:
                raise OpRefused("стопка в ячейке %d переполнится (количество ≤ %d, вес строки ≤ %d)" % (x, INT_MAX, WEIGHT_MAX))
            ops.append({"mode": "stack", "posx": x, "amount": q, "weight": add_w, "expect": a0})
        elif free:
            if add_w > WEIGHT_MAX:
                raise OpRefused("стопка тяжелее %d (вес %d × %d)" % (WEIGHT_MAX, s["unit_weight"], q))
            ops.append({"mode": "new", "posx": free[0], "amount": q, "weight": add_w, "expect": None})
        else:
            raise OpRefused("в сумке нет свободной ячейки")
    elif key is not None:
        q = _qty(p.get("qty", 1), QTY_MAX_CELLS)
        ccap = srvtables.charge_cap()
        rows = w.rows("SELECT Code, GroupKey FROM dbo.AsdaChargeGroup WHERE GroupKey = ?", (key,))
        kcodes = {int(r["Code"]) for r in rows}
        if plate == 5:
            kcodes = {code}          # перепроверка 18 М1: на складе P100 сливает только одинаковый код (P100_PROJECT §7 п.2)
        state = {x: r[1] for x, r in occ.items() if r[0] in kcodes}
        add, new = {}, []
        for _ in range(q):
            n = s["amount_each"]
            spot = next((x for x in sorted(state) if state[x] + n <= ccap), None)
            if spot is not None:
                state[spot] += n
                if spot in occ:
                    add[spot] = add.get(spot, 0) + n
                else:
                    new[[e["posx"] for e in new].index(spot)]["amount"] += n
            else:
                left = [x for x in free if x not in [e["posx"] for e in new]]
                if not left:
                    raise OpRefused("в сумке не хватает места для %d шт." % q)
                new.append({"mode": "new", "posx": left[0], "amount": n, "weight": s["unit_weight"], "expect": None})
                state[left[0]] = n
        for x in sorted(add):
            ops.append({"mode": "charge", "posx": x, "amount": add[x], "weight": 0, "expect": occ[x][1]})
        ops += new
        warn.append("заряды складываются в уже лежащий предмет того же вида (патч P100), потолок %d" % ccap)
    else:
        q = _qty(p.get("qty", 1), QTY_MAX_CELLS)
        if len(free) < q:
            raise OpRefused("в сумке свободно %d ячеек, нужно %d" % (len(free), q))
        wt = s["unit_weight"] + o["stone_weight"]
        if wt > WEIGHT_MAX:
            raise OpRefused("вес предмета вышел бы за пределы (%d)" % wt)
        ops = [{"mode": "new", "posx": x, "amount": s["amount_each"], "weight": wt, "expect": None} for x in free[:q]]
    add_w = sum(e["weight"] for e in ops)
    if plate != 5:
        cur_w, max_w = _weights(w, uid, idx, lock)
        if cur_w + add_w > max_w:            # ★ ревизия 27 К-7: как GameServer (GameServer.c:85371 — отказ при «предел < текущий + вес»)
            raise OpRefused("перегруз: вес %d + %d > предела %d" % (cur_w, add_w, max_w))
        if cur_w + add_w > WEIGHT_MAX:
            raise OpRefused("суммарный вес вышел бы за %d" % WEIGHT_MAX)
    if s["timed"]:
        warn.append("предмет со сроком: срок пойдёт с первого использования (как у сервера)")
    if s["gear"] and o["Opidx1"] == -1 and o["Opidx2"] == -1 and _pair_lists(code)[1]:
        warn.append("опции не выбраны — сервер при добыче выдал бы их из групп предмета")
    if not refdata.item(code)["ru"] and not refdata.item(code)["en"]:
        warn.append("у предмета нет названия в клиенте — возможно, служебный код")
    opts = {k: v for k, v in o.items() if k != "stone_weight"}
    where = items.PLATE_NAMES.get(plate, str(plate))
    extra = ""
    if s["gear"]:
        bits = []
        if o["Cell1"]:
            bits.append("самоцвет %s (%d)" % (_name(o["Cell1"]), o["Cell1"]))
        if o["Upcount"]:
            bits.append("ступень +%d" % o["Upcount"])
        for k in (1, 2):
            if o["Opidx%d" % k] != -1:
                bits.append(refdata.option_name(o["Opidx%d" % k], o["OpValue%d" % k]))
        extra = " (%s)" % ", ".join(bits) if bits else " (без опций)"
    text = "выдать персонажу %s (%d/%d): %s (%d) × %d%s → %s, ячейки %s" % (
        ch["Charname"], uid, idx, _name(code), code, q, extra, where, ", ".join(str(e["posx"]) for e in ops))
    sig = {"code": code, "plate": plate, "ops": ops, "opts": opts}
    return {"uid": uid, "idx": idx, "code": code, "plate": plate, "cap": cap, "spec": s, "ops": ops, "opts": opts,
            "text": text, "warnings": warn, "sig": sig}


# ★ А2.3 (мост P127 v82): выдача игроку В ИГРЕ — живьём, стоковым путём GM-выдачи (перенос хвоста Recv_OperatorCommand_ItemGive
#   0x552360 в DLL: ветки Function / Cellob / Item_Table, ячейку, стопку, вес и заряды P100 выбирает сервер, 2231 UPGmItemAdd с
#   оператором ADM_sitxovski 2/11 сам пишет предмет и JoyLog1.AdminItemLog — adm.ItemLedger/AdminitemLog панель НЕ пишет).
#   Сток за одну выдачу: спецпредмет/снаряжение/прочее — 1 шт., стопка — 1…19 → узел повторяет: до 30 штук или стопка до 570.
#   Больше / склад для спецпредмета / узел < v82 — прежний путь «кик + запись». Откат — «кик + изъятие» (adm.ItemTake по ячейкам итога).
#   ★ ревизия 29: М-1 — откат штучных видов узнаёт предмет по Uuid (снят из базы после выдачи) или по полному отпечатку выданного,
#   при неоднозначности — отказ; М-2 — итог «неизвестен» пишется в журнал с номером команды, поздний итог подтягивается из
#   adm.bridge_cmd (откат, журнал, следующая выдача), новая живая выдача персонажу — только после него; К-1 — отказ узла 20 / 11 →
#   следующий предпросмотр идёт прежним путём «кик + запись».
import time as _time

LIVE_COPIES_MAX = 30
LIVE_STACK_MAX = 19 * 30
LIVE_GIVE_WARN = ("выдача живьём: ячейку, вес и стопку выбирает сервер (как GM-выдача); оператор в журнале сервера — ADM_sitxovski; "
                  "откат — отключение игрока и изъятие выданного")
LIVE_STOP = {1: "неверная сумка для этого вида", 2: "нет свободной ячейки в сумке", 3: "нет свободной ячейки на складе",
             4: "кода нет в таблицах сервера", 6: "перегруз (вес)", 7: "количество стопки вне 1…19", 8: "исключение в функции стока"}
LIVE_OFF_S = 600                   # К-1: после отказа узла 20/11 этот персонаж/код идёт «кик + записью» столько секунд
UUID_WAIT_S = 3.0                  # М-1: сколько ждать строки UPGmItemAdd в базе, чтобы снять Uuid выданного
FP_COLS = ("Opidx1", "OpValue1", "Opidx2", "OpValue2", "Cell1", "Upcount")
_live_off = {}                     # (uid, idx, code) → до какого времени не выдавать живьём


def _parse_cells(text):
    kv = bridge.parse_kv(text)
    cells = []
    for part in str(kv.get("cells", "")).split(","):
        bits = part.split(".")
        if len(bits) == 3:
            try:
                cells.append([int(bits[0]), int(bits[1]), int(bits[2])])
            except ValueError:
                pass
    return kv, cells


def _opts_of(args):
    kv = bridge.parse_kv(args)
    return {"Opidx1": kv.get("o1", -1), "OpValue1": kv.get("v1", 0), "Opidx2": kv.get("o2", -1), "OpValue2": kv.get("v2", 0),
            "Cell1": kv.get("gem", 0), "Upcount": kv.get("up", 0)}


def late_result(a):
    """М-2: поздний итог «неизвестной» живой выдачи из adm.bridge_cmd → (состояние, after с ячейками | None).
    Состояния: «pending» — итога всё ещё нет; «done» — узел выдал (after дополнен ячейками); «none» — узел не выдал."""
    try:
        r = bridge.get_cmd(a["cmd"])
    except bridge.BridgeError:
        return "pending", None
    st = int(r["status"]) if r else 1
    if st in (0, 1):
        return "pending", None
    if st != 2:
        return "none", None
    kv, cells = _parse_cells(r.get("result") or "")
    b = dict(a, pending=False, cells=cells, plate=int(kv.get("plate", a.get("plate") or 0)), trunc=bool(kv.get("trunc", 0)),
             given=int(kv.get("given", 0)))
    return "done", b


def pending_note(after_json):
    """Журнал (api_audit): к записи «итог неизвестен» — что ответил узел позже."""
    import json
    try:
        a = json.loads(after_json or "{}")
    except ValueError:
        return None
    if not (a.get("live") and a.get("pending") and a.get("cmd")):
        return None
    st, b = late_result(a)
    if st == "pending":
        return "итог команды №%s ещё не пришёл" % a["cmd"]
    if st == "none":
        return "поздний итог команды №%s: узел НЕ выдал" % a["cmd"]
    return "поздний итог команды №%s: выдано %s, ячейки %s" % (a["cmd"], b["given"], ", ".join(str(c[0]) for c in b["cells"]) or "—")


def _pending_gives(uid, idx):
    """М-2: живые выдачи этому персонажу с неизвестным итогом (последние 50 записей журнала) → [(номер записи, состояние)]."""
    import json
    from core import audit
    try:
        rows = audit.query("items.give", target="char:%d/%d" % (uid, idx), limit=50)
    except Exception:
        return []
    out = []
    for r in rows:
        if r.get("target") != "char:%d/%d" % (uid, idx) or r.get("result") != "ok":
            continue
        try:
            a = json.loads(r.get("after_json") or "{}")
        except ValueError:
            continue
        if a.get("live") and a.get("pending") and a.get("cmd"):
            out.append((r["id"], a["cmd"], late_result(a)[0]))
    return out


def _live_give(ctx, p):
    """Предпросмотр живой выдачи (игрок в игре на узле v82+, Mode=1) или None — тогда обычный путь (офлайн / «кик + запись»)."""
    try:
        uid, idx, code = int(p["uid"]), int(p["idx"]), int(p["code"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры выдачи")
    row = bridge.live_row(uid, idx, min_ver=bridge.GIVE_VER)
    if not row:
        return None
    if _live_off.get((uid, idx, code), 0) > _time.time():
        return None                                    # К-1: узел недавно отказал «не поддерживается» — «кик + запись»
    s = item_spec(code)
    to = p.get("to") or "bag"
    if to not in ("bag", "ware"):
        raise OpRefused("неверные параметры выдачи")
    if to == "ware" and s["kind"] == "function":
        return None                                    # у стока GM-выдача спецпредмета — только в сумку 1
    plate = 5 if to == "ware" else s["plate"]
    q = _qty(p.get("qty", 1), QTY_MAX_STACK if s["stack"] else QTY_MAX_CELLS)
    if q > (LIVE_STACK_MAX if s["stack"] else LIVE_COPIES_MAX):
        return None                                    # за одну команду столько живьём не выдаём — «кик + запись»
    o = _opts(code, s, p.get("opts"))
    for aid, cmd, st in _pending_gives(uid, idx):
        if st == "pending":
            raise OpRefused("предыдущая живая выдача этому персонажу (журнал №%s, команда №%s) ещё не подтверждена узлом — повторите позже"
                            % (aid, cmd))
    args = "code=%d;q=%d;ware=%d;plate=%d;o1=%d;v1=%d;o2=%d;v2=%d;gem=%d;up=%d" % (
        code, q, 1 if to == "ware" else 0, plate, o["Opidx1"], o["OpValue1"], o["Opidx2"], o["OpValue2"], o["Cell1"], o["Upcount"])
    extra = ""
    if s["gear"]:
        bits = (["самоцвет %s (%d)" % (_name(o["Cell1"]), o["Cell1"])] if o["Cell1"] else []) + (["ступень +%d" % o["Upcount"]] if o["Upcount"] else []) \
            + [refdata.option_name(o["Opidx%d" % k], o["OpValue%d" % k]) for k in (1, 2) if o["Opidx%d" % k] != -1]
        extra = " (%s)" % ", ".join(bits) if bits else " (без опций)"
    text = "выдать персонажу %s (%d/%d) ЖИВЬЁМ: %s (%d) × %d%s → %s" % (row.get("charname") or "", uid, idx, _name(code), code, q, extra,
                                                                      items.PLATE_NAMES.get(plate, str(plate)))
    return {"text": text, "expect": {"live": ["give", args]}, "warnings": [bridge.LIVE_WARN, LIVE_GIVE_WARN],
            "live": {"op": "give", "args": args, "row": row, "uid": uid, "idx": idx, "code": code, "plate": plate, "q": q}}


def _snap_uuids(uid, idx, plate, code, cells):
    """М-1: Uuid выданных НОВЫХ ячеек (строку пишет UPGmItemAdd через DBManager — ждём до UUID_WAIT_S). Не нашлась — None."""
    want = [c for c in cells if not c[2]]
    if not want:
        return
    end = _time.time() + UUID_WAIT_S
    while True:
        try:
            with db.GameReader("joy1") as r:
                for c in want:
                    if len(c) < 4:
                        x = r.rows("SELECT Uuid FROM Item WHERE Userindex = ? AND Charidx = ? AND Plate = ? AND Posx = ? AND Code = ?",
                                   (uid, idx, plate, c[0], code))
                        if x:
                            c.append(str(x[0]["Uuid"]).upper())
        except db.DbError:
            return
        if all(len(c) >= 4 for c in want) or _time.time() >= end:
            return
        _time.sleep(0.25)


def _live_give_apply(ctx, prev):
    lv = prev["live"]
    after = {"uid": lv["uid"], "idx": lv["idx"], "live": True, "op": "give", "node": lv["row"]["node"], "code": lv["code"],
             "plate": lv["plate"], "opts": _opts_of(lv["args"]), "q": lv["q"]}
    try:
        r, text = bridge.live_call("give", lv["row"], lv["args"], by=ctx.login)
    except bridge.BridgeError as ex:
        if getattr(ex, "unknown", False) and getattr(ex, "cid", None):
            # М-2: узел МОГ выдать — запись журнала с номером команды; итог подтянется позже (откат, журнал, следующая выдача)
            after.update(pending=True, cmd=int(ex.cid), cells=[])
            return {"before": {"uid": lv["uid"], "idx": lv["idx"]}, "after": after,
                    "message": "итог живой выдачи неизвестен (команда №%s): узел мог выдать — итог подтянется из журнала моста; "
                               "новая живая выдача этому персонажу — после него" % ex.cid}
        if getattr(ex, "code", None) in (11, 20):
            _live_off[(lv["uid"], lv["idx"], lv["code"])] = _time.time() + LIVE_OFF_S        # К-1
            raise OpRefused("живьём не выполнено: %s — повторите предпросмотр: выдача пойдёт прежним путём «кик + запись»" % ex)
        raise OpRefused("живьём не выполнено: %s" % ex)
    kv, cells = _parse_cells(text)
    given, stop = int(kv.get("given", 0)), int(kv.get("stop", 0))
    _snap_uuids(lv["uid"], lv["idx"], int(kv.get("plate", lv["plate"])), lv["code"], cells)
    done = int(kv.get("units", 0)) if item_spec(lv["code"])["stack"] else given          # стопка — штук, прочее — выдач
    msg = "выдано живьём %d из %d: %s (%d) → %s, ячейки %s" % (done, int(lv["q"]), _name(lv["code"]), lv["code"],
                                                            items.PLATE_NAMES.get(lv["plate"], str(lv["plate"])), ", ".join(str(c[0]) for c in cells))
    if stop:
        msg += " — сервер остановил выдачу: %s" % LIVE_STOP.get(stop, str(stop))
    if int(kv.get("after2231", 0)):
        msg += " — исключение после записи в базу: проверьте ячейку %s" % kv.get("fault", "?")
    if int(kv.get("trunc", 0)):
        msg += " — список ячеек не поместился в итог узла: откат по журналу недоступен"
    after.update(cmd=int(r["id"]), plate=int(kv.get("plate", lv["plate"])), cells=cells, trunc=bool(kv.get("trunc", 0)), given=given)
    return {"before": {"uid": lv["uid"], "idx": lv["idx"]}, "after": after, "message": msg}


def _fp_ok(row, want, s):
    """М-1: строка ячейки = выданный предмет по отпечатку (самоцвет/опции/ступень; самоцвет «нет» = −1 или 0 в базе)."""
    for k in FP_COLS:
        have = int(row.get(k) if row.get(k) is not None else 0)
        w = int(want.get(k, -1 if k.startswith("Opidx") else 0))
        if k == "Cell1":
            have, w = max(have, 0), max(w, 0)
        if k.startswith("OpValue") and int(want.get("Opidx" + k[-1], -1)) == -1:
            continue                                   # пары нет — значение не сверяем (сток пишет 0)
        if not s["gear"] and k in FP_COLS:
            continue                                   # у не-снаряжения опций нет — отпечаток: код и количество
        if have != w:
            return False
    if s["gear"] and s["maxup"] and row.get("MaxUpcnt") is not None and int(row["MaxUpcnt"]) != int(s["maxup"]):
        return False
    return True


def _live_give_undo(ctx, a):
    """Откат живой выдачи: игрок в игре — отказ под блокировкой (ops.undo отключит его мостом и попросит повторить); не в игре —
    изъятие выданного из ячеек итога (adm.ItemTake): стопка/заряды — выданное количество; штучное — вся ячейка, только если в ней
    ИМЕННО выданный предмет (Uuid или полный отпечаток, без двойников) — ★ ревизия 29 М-1."""
    if a.get("pending"):
        st, b = late_result(a)                         # М-2: поздний итог
        if st == "pending":
            raise OpRefused("итог живой выдачи (команда №%s) ещё не пришёл — откат позже" % a.get("cmd"))
        if st == "none":
            raise OpRefused("узел эту выдачу не выполнил (команда №%s) — откатывать нечего" % a.get("cmd"))
        a = b
    if a.get("trunc"):
        raise OpRefused("список ячеек выдачи неполный (не поместился в итог узла) — откат по журналу недоступен, изымите вручную")
    uid, idx, code, plate, cells = a.get("uid"), a.get("idx"), a.get("code"), a.get("plate"), a.get("cells") or []
    if not uid or not code or not cells:
        raise OpRefused("в журнале нет данных для отката")
    s = item_spec(code)
    want = a.get("opts") or {}
    w = db.GameWriter("joy1")
    try:
        ok, why = items.online_state(w, uid, lock=True)
        if not ok:
            raise OpRefused("откат только когда игрок не в игре: " + why)
        part_ok = s["stack"] or (s["kind"] == "function" and _charge_key(w, code) is not None)
        oper = ("panel:%s" % (ctx.login or ""))[:64]
        cols = "Posx, Uuid, Code, Amount, Weight, CONVERT(varchar(23), Fdate, 121) AS fd, Opidx1, OpValue1, Opidx2, OpValue2, Cell1, Upcount, MaxUpcnt"
        ids = []
        for c in reversed(cells):
            posx, amount = int(c[0]), int(c[1])
            r = w.rows("SELECT %s FROM Item WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ? AND Plate = ? AND Posx = ?" % cols,
                       (uid, idx, plate, posx))
            if not r or int(r[0]["Code"]) != int(code):
                raise OpRefused("в ячейке %d уже другой предмет — откат не выполнен" % posx)
            r = r[0]
            have, wt = int(r["Amount"] or 0), int(r["Weight"] or 0)
            take, tw = None, 0
            if part_ok:
                if have < amount:
                    raise OpRefused("в ячейке %d меньше выданного (%d < %d) — откат не выполнен" % (posx, have, amount))
                if have > amount:
                    take, tw = amount, (0 if s["kind"] == "function" else min(wt, amount * s["unit_weight"]))
            else:
                if len(c) >= 4 and c[3]:
                    if str(r["Uuid"]).upper() != str(c[3]).upper():
                        raise OpRefused("в ячейке %d не тот предмет, что выдан (другой Uuid) — откат не выполнен" % posx)
                else:
                    if have != amount or not _fp_ok(r, want, s):
                        raise OpRefused("в ячейке %d не тот предмет, что выдан (отпечаток не совпал) — откат не выполнен" % posx)
                    twins = w.rows("SELECT %s FROM Item WHERE Userindex = ? AND Charidx = ? AND Plate = ? AND Code = ? AND Posx <> ?" % cols,
                                   (uid, idx, plate, int(code), posx))
                    given_pos = {int(x[0]) for x in cells}             # ячейки этой же выдачи — не двойники
                    if any(int(t.get("Posx", -1)) not in given_pos and int(t["Amount"] or 0) == amount and _fp_ok(t, want, s) for t in twins):
                        raise OpRefused("в ячейке %d предмет не опознан однозначно (такой же лежит в другой ячейке, Uuid выдачи неизвестен) — "
                                        "откат не выполнен" % posx)
            try:
                x = w.rows("EXEC adm.ItemTake ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                           (uid, idx, plate, posx, int(code), str(r["Uuid"]).upper(), have, r["fd"], take, tw, oper))
            except db.DbError as ex:
                raise _refuse_db(ex, "adm.ItemTake")
            if not x:
                raise OpRefused("процедура изъятия не ответила — ничего не записано")
            ids.append(int(x[0]["LedgerId"]))
    except db.DbError as ex:
        w.close()
        raise OpRefused("ошибка базы: %s" % ex)
    except BaseException:
        w.close()
        raise
    return {"before": {"cells": cells, "code": code, "plate": plate}, "after": {"uid": uid, "idx": idx, "ledger": ids},
            "message": "выданное живьём изъято (ячейки %s)" % ", ".join(str(c[0]) for c in cells), "_commit": w.commit, "_close": w.close}


@register
class ItemGive(Operation):
    name, title, perm, reversible = "items.give", "Предмет: выдать персонажу", "players.items_give", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        lv = _live_give(ctx, p)                                  # ★ А2.3: игрок в игре на узле v82+ — живьём
        if lv:
            return lv
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                pl = plan_give(ad, p)
                ok, why = items.online_state(ad, pl["uid"])
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("выдавать можно только когда игрок не в игре: " + why)
        return {"text": pl["text"], "expect": pl["sig"],
                "warnings": pl["warnings"] + ([items.RECENT_WARN] if items.recently_left(pl["uid"]) else [])}

    def apply(self, ctx, p, prev):
        if prev.get("live"):
            return _live_give_apply(ctx, prev)
        try:
            uid0 = int(p["uid"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры выдачи")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("выдавать можно только когда игрок не в игре: " + why)
            pl = plan_give(w, p, lock=True)
            if pl["sig"] != prev["expect"] or ("expect" in p and p["expect"] != pl["sig"]):
                raise OpRefused("пока вы смотрели предпросмотр, сумка персонажа изменилась — повторите")
            s, o, ccap = pl["spec"], pl["opts"], srvtables.charge_cap() or 30000
            ledger, oper = [], ("panel:%s" % (ctx.login or ""))[:64]
            for e in pl["ops"]:
                try:
                    r = w.rows("EXEC adm.ItemGive ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                               (pl["uid"], pl["idx"], pl["plate"], e["posx"], pl["cap"], e["mode"], pl["code"], e["amount"],
                                s["dur"], e["weight"], o["Cell1"], o["Upcount"], s["maxup"], o["Opidx1"], o["OpValue1"],
                                o["Opidx2"], o["OpValue2"], s["owner"], e["expect"], ccap, oper))
                except db.DbError as ex:
                    raise _refuse_db(ex, "adm.ItemGive")
                if not r:
                    raise OpRefused("процедура выдачи не ответила — ничего не записано")
                ledger.append(int(r[0]["LedgerId"]))
        except db.DbError as ex:                    # перепроверка 18 К4: тайм-аут блокировки и т.п. — понятный отказ
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": pl["uid"], "idx": pl["idx"], "plate": pl["plate"], "ops": pl["ops"]},
                "after": {"uid": pl["uid"], "idx": pl["idx"], "code": pl["code"], "plate": pl["plate"], "ledger": ledger},
                "message": pl["text"], "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        if a.get("live"):
            return _live_give_undo(ctx, a)
        return _undo_ledger(ctx, a, "выдача предмета откачена")


def _undo_ledger(ctx, a, msg):
    uid, idx, ids = a.get("uid"), a.get("idx"), a.get("ledger") or []
    if not uid or not ids:
        raise OpRefused("в журнале нет данных для отката")
    w = db.GameWriter("joy1")
    try:
        ok, why = items.online_state(w, uid, lock=True)
        if not ok:
            raise OpRefused("откат только когда игрок не в игре: " + why)
        ch, cells, caps = items._load(w, uid, idx, lock=True)
        oper = ("panel:%s" % (ctx.login or ""))[:64]
        for lid in reversed(ids):
            led = w.rows("SELECT Kind, Plate, WeightBefore, WeightAfter FROM adm.ItemLedger WHERE Id = ?", (lid,))
            if not led:
                raise OpRefused("записи %s нет в журнале предметов" % lid)
            k = led[0]["Kind"]
            if k in ("take", "takepart") and int(led[0]["Plate"]) != 5:       # перепроверка 18 М3: и возврат части стопки
                cur_w, max_w = _weights(w, uid, idx, True)
                wt = int(led[0]["WeightBefore"] or 0) - (int(led[0]["WeightAfter"] or 0) if k == "takepart" else 0)
                if cur_w + wt > max_w or cur_w + wt > WEIGHT_MAX:        # ★ ревизия 27 К-7: как GameServer
                    raise OpRefused("перегруз: вернуть предмет нельзя (вес %d + %d > %d)" % (cur_w, wt, max_w))
            try:
                w.rows("EXEC adm.ItemUndo ?, ?, ?", (lid, caps.get(int(led[0]["Plate"]), 0), oper))
            except db.DbError as ex:
                raise _refuse_db(ex, "adm.ItemUndo")
    except db.DbError as ex:
        w.close()
        raise OpRefused("ошибка базы: %s" % ex)
    except BaseException:
        w.close()
        raise
    return {"before": {"ledger": ids}, "after": {"undone": ids}, "message": msg, "_commit": w.commit, "_close": w.close}


def plan_take(w, p, lock=False):
    try:
        uid, idx, plate, posx = int(p["uid"]), int(p["idx"]), int(p["plate"]), int(p["posx"])
        uuid = str(p["uuid"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры изъятия")
    if plate not in (1, 2, 5):
        raise OpRefused("изымать можно только из сумок и склада (надетое — сначала снять)")
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Uuid, Code, Amount, Weight, CONVERT(varchar(23), Fdate, 121) AS fd FROM Item%s WHERE Userindex = ? "
               "AND Charidx = ? AND Plate = ? AND Posx = ?" % hint, (uid, idx, plate, posx))
    if not r or str(r[0]["Uuid"]).upper() != uuid.upper():
        raise OpRefused("в этой ячейке уже другой предмет — обновите страницу")
    r = r[0]
    code, amount, weight = int(r["Code"]), int(r["Amount"] or 0), int(r["Weight"] or 0)
    if code == GOLD_CODE:
        raise OpRefused("золото правится карандашом у золота, не изъятием")
    chn = w.rows("SELECT Charname FROM Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, idx))
    if not chn:
        raise OpRefused("персонаж не найден")
    q = p.get("qty")
    part, tw = None, 0
    if q not in (None, "", "all"):
        q = _qty(q, INT_MAX)
        if q < amount:
            try:
                s = item_spec(code)
            except OpRefused:
                s = None
            charge = s is not None and s["kind"] == "function" and _charge_key(w, code) is not None
            if not charge and not (s and s["stack"]):
                raise OpRefused("часть можно снять только у стопки или у зарядов — этот предмет изымается целиком")
            part = q
            tw = 0 if charge else min(weight, q * s["unit_weight"])
        elif q > amount:
            raise OpRefused("в ячейке только %d" % amount)
    text = "изъять у персонажа %s (%d/%d): %s (%d)%s — %s, ячейка %d" % (
        chn[0]["Charname"], uid, idx, _name(code), code, (" × %d из %d" % (part, amount)) if part else
        (" (%d)" % amount if amount else ""), items.PLATE_NAMES.get(plate, str(plate)), posx)
    sig = {"uuid": str(r["Uuid"]).upper(), "code": code, "amount": amount, "fdate": r["fd"], "take": part, "weight": tw}
    return {"uid": uid, "idx": idx, "plate": plate, "posx": posx, "code": code, "sig": sig, "text": text}


@register
class ItemTake(Operation):
    name, title, perm, reversible = "items.take", "Предмет: изъять у персонажа", "players.items_give", True

    def target(self, p):
        return "item:%s/%s/%s" % (p.get("uid"), p.get("idx"), p.get("uuid"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                pl = plan_take(ad, p)
                ok, why = items.online_state(ad, pl["uid"])
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("изымать можно только когда игрок не в игре: " + why)
        return {"text": pl["text"], "expect": pl["sig"],
                "warnings": ["предмет пропадёт у игрока; вернуть — откатом в журнале действий"]
                + ([items.RECENT_WARN] if items.recently_left(pl["uid"]) else [])}

    def apply(self, ctx, p, prev):
        try:
            uid0 = int(p["uid"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры изъятия")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("изымать можно только когда игрок не в игре: " + why)
            pl = plan_take(w, p, lock=True)
            sg = pl["sig"]
            if sg != prev["expect"] or ("expect" in p and p["expect"] != sg):
                raise OpRefused("пока вы смотрели предпросмотр, предмет изменился — повторите")
            try:
                r = w.rows("EXEC adm.ItemTake ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                           (pl["uid"], pl["idx"], pl["plate"], pl["posx"], pl["code"], sg["uuid"], sg["amount"], sg["fdate"],
                            sg["take"], sg["weight"], ("panel:%s" % (ctx.login or ""))[:64]))
            except db.DbError as ex:
                raise _refuse_db(ex, "adm.ItemTake")
            if not r:
                raise OpRefused("процедура изъятия не ответила — ничего не записано")
            lid = int(r[0]["LedgerId"])
        except db.DbError as ex:                    # перепроверка 18 К4: тайм-аут блокировки и т.п. — понятный отказ
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": pl["uid"], "idx": pl["idx"], "plate": pl["plate"], "posx": pl["posx"], "item": sg},
                "after": {"uid": pl["uid"], "idx": pl["idx"], "ledger": [lid]}, "message": pl["text"],
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        return _undo_ledger(ctx, a, "изъятый предмет возвращён")
