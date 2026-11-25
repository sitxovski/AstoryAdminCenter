# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""questdata.py — таблицы заданий стойки и проверки сервера для операций заданий (волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_quests_episodes.md (§3, §4); здесь — ровно то, что делают сервера:
  QuestBook_Table.txt   (GS, загрузчик :68799)  книга Code → Episodeidx (+4), предметы-цели при взятии (+8/+12/+16, кол. 1);
  RepayTable.txt        (GS, :68880, 35 токенов) награда; применяет sub_45DEE0 (GameServer.c:38194…39100);
  QuestNpcTable.Bin     (NpcServer) 200 × 1774 б: «ВЫДАЁТ» +34 + 86·k (k 0…9: +0 задание, +66 5 × i32 ключей ConditionTable),
                        «ПРИНИМАЕТ» +894 + 88·k (+0 задание, +66 i16 шаг, +68 5 × i32 ключей); QuestNpcTableExt.Bin (патч N22:
                        шапка «QNTX» 16 б, записи 96 б — ячейки ≥ 10 того же формата);
  ConditionTable.Bin    1165 × 146 б, ключ = номер записи (запись 0 — нулевая).
  check()      — CheckCondition sub_41FD70 (NpcServer.exe.c:21714) дословно по веткам (уровень, класс, блок заданий, предметы-цели,
                 +140 вид / +142 время);
  start_check() — Start_Quest sub_421020 (:22486): ключи ячейки по порядку; первый прошедший — выдача; не прошёл и +6 ≠ 0xFFFF —
                 отказ этим кодом; затем «уже в журнале» (2) / «нет слота» (3).
Побочных эффектов при импорте нет.
"""
import struct
import threading
import time

from core import config, hostshell

COND_REC, NPC_REC, GIVE_OFF, GIVE_CELL, TAKE_OFF, TAKE_CELL = 146, 1774, 34, 86, 894, 88
QMAX = 0x4FF                       # индекс задания в условиях ≤ 1279 (маска 20 × 64)
SLOTS = 12
BOARD_MIN = 20000                  # книги доски
_lock = threading.Lock()
_cache = {}
TTL = 300


def _bytes(rel):
    with _lock:
        hit = _cache.get(rel)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
    try:
        b = hostshell.read_server_bytes(config.STACK_ROOT + "\\" + rel)
    except hostshell.HostError:
        if rel.endswith("QuestNpcTableExt.Bin"):
            b = b""                # нет таблицы N22 — сервер как сток
        else:
            raise
    with _lock:
        _cache[rel] = (time.monotonic(), b)
    return b


def _text(rel):
    from domains import srvtables
    return srvtables.stack_text(rel, ttl=TTL)


def _rows(txt):
    out = []
    for ln in txt.splitlines():
        t = ln.split()
        if t:
            out.append(t)
    return out


def quest_book():
    """→ (code → {idx, goals[3]}, idx → code). Порядок строк — как у загрузчика (первая строка — число записей)."""
    rows = _rows(_text(r"GameServer\ItemTable_Info\QuestBook_Table.txt"))
    by_code, by_idx = {}, {}
    for t in rows[1:]:
        if len(t) < 6:
            continue
        code, idx = int(t[0]), int(t[1])
        by_code[code] = {"idx": idx, "goals": [int(t[3]), int(t[4]), int(t[5])]}
        by_idx.setdefault(idx, code)
    return by_code, by_idx


REPAY_KEYS = ("pen_flag", "pen_base", "gold", "exp", "a_flag", "a_charisma", "a_book", "job", "a_fame", "t10", "a_sp",
              "goal1", "goal1n", "goal2", "goal2n", "item1", "item1n", "item2", "item2n", "item3", "item3n",
              "b_flag", "b_charisma", "b_book", "b_fame", "b_t26", "b_sp", "item4", "item4n", "item5", "item5n", "item6", "item6n",
              "remove_goal")


def repay(rid):
    """Запись RepayTable (номер = строка 1…N) → dict по REPAY_KEYS; нет — None."""
    rows = _rows(_text(r"GameServer\ItemTable_Info\RepayTable.txt"))
    for t in rows[1:]:
        if len(t) >= 35 and int(t[0]) == int(rid):
            return {k: int(t[i + 1]) for i, k in enumerate(REPAY_KEYS)}
    return None


def reward_parts(r):
    """Что даёт награда (как sub_45DEE0): опыт и золото — всегда; блок A при a_flag, блок B при b_flag. → dict."""
    items = []
    if r["a_flag"]:
        items += [(r["item%d" % k], r["item%dn" % k]) for k in (1, 2, 3) if r["item%d" % k] > 0]
    if r["b_flag"]:
        items += [(r["item%d" % k], r["item%dn" % k]) for k in (4, 5, 6) if r["item%d" % k] > 0]
    sp = (r["a_sp"] if r["a_flag"] and r["a_sp"] > 0 else 0) + (r["b_sp"] if r["b_flag"] and r["b_sp"] > 0 else 0)
    unsupported = []
    for flag, pre in ((r["a_flag"], "a"), (r["b_flag"], "b")):
        if flag:
            for k, nm in (("charisma", "харизма"), ("book", "следующая книга"), ("fame", "слава")):
                if r["%s_%s" % (pre, k)] > 0:
                    unsupported.append(nm)
    return {"exp": max(0, r["exp"]), "gold": max(0, r["gold"]), "items": items, "sp": sp,
            "job": r["job"] if r["a_flag"] and r["job"] > 0 else 0, "unsupported": unsupported}


def penalized_exp(r, lvl):
    """Опыт со штрафом за уровень (GameServer.c:38968–39010): v = Lv − база; флаг → v /= 5 (при v > 0); 0 → ×1, 1 → ×0.9 … ≥ 5 → ×0.5;
    множители — float-константы сервера, усечение к целому."""
    e = r["exp"]
    if e <= 0:
        return 0
    if not r["pen_flag"]:
        return e
    v = int(lvl) - r["pen_base"]
    if v > 0:
        v //= 5
    if v < 1:
        return e
    mult = {1: 0.8999999761581421, 2: 0.800000011920929, 3: 0.699999988079071, 4: 0.6000000238418579}.get(v, 0.5)
    return int(float(e) * mult)


def _cells():
    """→ (gives{q: [(npc, cell, keys)]}, takes{q: [(npc, cell, step, keys)]})."""
    return parse_cells(_bytes(r"NpcServer\Quest\QuestNpcTable.Bin"), _bytes(r"NpcServer\Quest\QuestNpcTableExt.Bin"))


def parse_cells(b, x):
    """★ А4.5 (20.11.2026): разбор ячеек по байтам QuestNpcTable.Bin (b) и QuestNpcTableExt.Bin (x) — тело прежнего _cells без
    чтения стойки (его зовёт и область «Задания» наборов изменений по снимку набора). → (gives, takes) как _cells."""
    gives, takes = {}, {}
    for i in range(len(b) // NPC_REC):
        o = i * NPC_REC
        for k in range(10):
            so = o + GIVE_OFF + GIVE_CELL * k
            q = struct.unpack_from("<h", b, so)[0]
            if q > 0 or (q == 0 and b[so + 2:so + 3] not in (b"", b"\x00")):
                gives.setdefault(q, []).append((i, k, list(struct.unpack_from("<5i", b, so + 66))))
            so = o + TAKE_OFF + TAKE_CELL * k
            q = struct.unpack_from("<h", b, so)[0]
            if q > 0 or (q == 0 and b[so + 2:so + 3] not in (b"", b"\x00")):
                takes.setdefault(q, []).append((i, k, struct.unpack_from("<h", b, so + 66)[0], list(struct.unpack_from("<5i", b, so + 68))))
    if _ext_ok(x):
        n = struct.unpack_from("<I", x, 8)[0]
        for j in range(n):
            o = 16 + 96 * j
            if o + 96 > len(x):
                break
            npc, kind, slot = struct.unpack_from("<h", x, o)[0], x[o + 2], struct.unpack_from("<H", x, o + 4)[0]
            c = o + 8
            q = struct.unpack_from("<h", x, c)[0]
            if kind == 0:
                gives.setdefault(q, []).append((npc, slot, list(struct.unpack_from("<5i", x, c + 66))))
            else:
                takes.setdefault(q, []).append((npc, slot, struct.unpack_from("<h", x, c + 66)[0], list(struct.unpack_from("<5i", x, c + 68))))
    return gives, takes


def _ext_ok(x):
    """Проверки загрузчика N22 (N22_PATCH_DESIGN.md): шапка «QNTX», версия 1, размер = 16 + 96·N, вид ≤ 1, байт 3 и +6 = 0, слот
    10…127, без повторов (npc, вид, слот) — иначе патч не ставится целиком, и панель таблицу не читает (перепроверка 22 К9)."""
    if len(x) < 16 or x[:4] != b"QNTX" or struct.unpack_from("<I", x, 4)[0] != 1:
        return False
    n = struct.unpack_from("<I", x, 8)[0]
    if len(x) != 16 + 96 * n:
        return False
    seen = set()
    for j in range(n):
        o = 16 + 96 * j
        npc, kind, b3, slot, z = struct.unpack_from("<hBBHH", x, o)
        if kind > 1 or b3 or z or not 10 <= slot <= 127 or (npc, kind, slot) in seen:
            return False
        seen.add((npc, kind, slot))
    return True


def cells():
    with _lock:
        hit = _cache.get("_cells")
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
    v = _cells()
    with _lock:
        _cache["_cells"] = (time.monotonic(), v)
    return v


def cond(key):
    """Запись ConditionTable по ключу → dict; вне таблицы — None."""
    return cond_rec(_bytes(r"NpcServer\Quest\ConditionTable.Bin"), key)


def cond_rec(b, key):
    """★ А4.5: запись ConditionTable по байтам таблицы (тело прежнего cond) → dict; вне таблицы — None."""
    if key < 0 or (key + 1) * COND_REC > len(b):
        return None
    r = b[key * COND_REC:(key + 1) * COND_REC]
    U = lambda off: struct.unpack_from("<I", r, off)[0]
    return {"key": key, "stop": struct.unpack_from("<H", r, 6)[0], "reward_flag": r[10], "book": struct.unpack_from("<i", r, 11)[0],
            "rewards": [struct.unpack_from("<h", r, 11 + 4 * s)[0] for s in range(5)], "action": r[35],
            "lvl_flag": r[36], "lvl_min": r[37], "lvl_max": r[38], "cls_flag": r[39],
            "job": struct.unpack_from("<i", r, 40)[0], "job_case": struct.unpack_from("<i", r, 44)[0],
            "qblock": r[48], "A": U(49), "P": U(53), "J": U(57), "B": U(61), "J_step": struct.unpack_from("<b", r, 65)[0],
            "items_flag": r[66], "items_none": r[67], "items_any": r[68],
            "ids": list(struct.unpack_from("<5i", r, 69)), "cnts": list(struct.unpack_from("<5h", r, 89)),
            "kind140": struct.unpack_from("<h", r, 140)[0], "time142": struct.unpack_from("<I", r, 142)[0]}


def _class_ok(c, J, S):
    """Ветка класса CheckCondition (NpcServer.exe.c:21758–21990) дословно. → код (0 — прошло)."""
    a, v = c["job"], c["job_case"]
    if a < 0 or J < 0 or S < 0:
        return 4
    if a == 99:
        return 0 if J else 5
    E = lambda *xs: J in xs or S in xs
    if v in (-1, 0):
        if a == 40:
            ok = E(1, 12, 23)
        elif a == 41:
            ok = E(2, 13, 24)
        elif a == 42:
            ok = E(3, 14, 25)
        elif a == 43:
            ok = E(4, 6, 15, 17, 26, 28, 34, 36, 38)
        elif a == 44:
            ok = E(5, 7, 16, 18, 27, 29, 35, 37, 39)
        else:
            ok = a == J or a == S
    elif v == 1:
        if a == 40:
            ok = J != 0
        elif a == 41:
            ok = J >= 2 and J not in (12, 23)
        elif a == 42:
            ok = J >= 2 and J not in (12, 23, 2, 13, 24)
        elif a in (43, 44):
            ok = (a == 43 and S in (4, 6, 15, 17, 26, 28, 34, 36, 38)) or S in (5, 7, 16, 18, 27, 29, 35, 37, 39)
        else:
            tops = [(range(1, 8), 7), (range(12, 19), 18), (range(23, 30), 29), ((34, 35), 35), ((36, 37), 37), ((38, 39), 39)]
            top = next((t for rr, t in tops if a in rr), None)
            ok = top is not None and a <= J and S <= top
    elif v == 2:
        if a in (40, 41, 42):
            ok = False                           # сравнение с самим ArgList (40…42) — у сервера всегда ложь
        elif a == 43:
            ok = S == 0
        elif a == 44:
            ok = S in (0, 4, 6, 15, 17, 26, 28, 34, 36, 38)
        else:
            lows = [(range(1, 8), 1), (range(12, 19), 12), (range(23, 30), 23), ((34, 35), 34), ((36, 37), 36), ((38, 39), 38)]
            low = next((t for rr, t in lows if a in rr), None)
            ok = low is not None and J >= low and a > S
    else:
        ok = False
    return 0 if ok else 5


def _in_journal(slots, q):
    return any(s and s["Episodeidx"] == q for s in slots)


def check(c, ch, done, slots):
    """CheckCondition → код (0 — прошло). ch: Lvl, Job, Subjob; done(q) → bool; slots: 12 элементов (None или dict Episodeidx,
    Stepidx, items[(Eitem, Amount)×5]). Отличие от сервера одно: +140 (поля игрока 30470/30472/30476) и +142 (время) панель не
    знает — такие условия возвращают 99 (панель откажет)."""
    if c is None:
        return 9
    lv = int(ch["Lvl"] or 0)
    if c["lvl_flag"] == 1:
        if not c["lvl_min"] or c["lvl_max"] > 150 or lv == 0 or lv > 150:
            return 10
        if c["lvl_min"] > lv or c["lvl_max"] < lv:
            return 11
    if c["cls_flag"] == 1:
        r = _class_ok(c, int(ch["Job"] or 0), int(ch["Subjob"] or 0))
        if r:
            return r
    if c["qblock"] == 1:
        for g in (c["A"], c["B"]):
            if g <= QMAX and (done(g) or _in_journal(slots, g)):
                return 6
        if c["P"] <= QMAX and not (done(c["P"]) and not _in_journal(slots, c["P"])):
            return 7
        if c["J"] <= QMAX:
            pos = next((i for i, s in enumerate(slots) if s and s["Episodeidx"] == c["J"]
                        and (c["J_step"] <= -1 or c["J_step"] == s["Stepidx"])), None)
            if pos is None:
                return 8
            if c["items_flag"] == 1:
                r = _items(c, slots[pos]["items"])
                if r:
                    return r
    if c["kind140"] in (1, 2, 3) or c["time142"]:
        return 99
    return 0


def _items(c, have):
    """Предметы-цели слота (NpcServer.exe.c:22040–22168): ids/cnts условия против 5 пар слота."""
    ids, cnts = c["ids"], c["cnts"]
    sid = [x for x, _ in have]
    if c["items_any"]:
        if c["items_none"]:
            hit = 0
            for x in ids:
                if x != -1:
                    if x not in sid:
                        return 0
                    hit = 8
            return hit
        for it, n in have:
            if any(ids[k] == it and cnts[k] <= n for k in range(5)):
                return 0
        return 8
    if c["items_none"]:
        return 8 if any(x != -1 and x in sid for x in ids) else 0
    got = [False] * 5
    for it, n in have:
        for k in range(5):
            if ids[k] == it and cnts[k] <= n:
                got[k] = True
                break
        for k in range(1, 5):
            if ids[k] == -1:
                got[k] = True
        if all(got):
            return 0
    return 8


REASONS = {2: "задание уже в журнале", 3: "в журнале нет свободного места (12)", 4: "ошибка данных класса", 5: "не подходит профессия",
           6: "задание уже выполнено или взято", 7: "не выполнено предшествующее задание", 8: "нет нужного задания или предметов в журнале",
           9: "нет условия в таблице", 10: "ошибка уровня в условии", 11: "не подходит уровень",
           99: "условие по полям игрока (+140) или по времени (+142) — панель такие не выдаёт", 100: "ошибка таблицы NPC",
           101: "ячейка NPC книгу задания не выдаёт"}


def book_of(c, q):
    """Книга, которую GS создаст по прошедшему условию выдачи (Start_Quest :22603: +10 == 1 → код +11; GS sub_45CA70 —
    sub_532B30): код, если он из QuestBook и его Episodeidx = q; иначе None (перепроверка 22 В1: ячейка NPC 81 с ключами 0
    проходит условие, но книги не даёт — сервер задание не выдаёт)."""
    if not c or c["reward_flag"] != 1:
        return None
    bk = quest_book()[0].get(c["book"])
    return c["book"] if bk and bk["idx"] == q else None


def _real_gives(q):
    """Ячейки «ВЫДАЁТ», которые дают книгу задания q (первый ключ — его условие)."""
    gives, _t = cells()
    out = []
    for npc, cell, keys in gives.get(q, []):
        c = cond(keys[0]) if keys and keys[0] >= 0 else None
        if book_of(c, q) is not None:
            out.append((npc, cell, keys, c))
    return out


def start_check(q, ch, done, slots):
    """Start_Quest по всем ячейкам «ВЫДАЁТ» задания q. → (True, ячейка) или (False, [коды по ячейкам])."""
    gives, _t = cells()
    codes = []
    for npc, cell, keys in gives.get(q, []):
        if keys[0] < 0:
            codes.append(100)
            continue
        res = None
        for key in keys:
            c = cond(key)
            r = check(c, ch, done, slots)
            if r == 0:
                res = 0
                break
            if c is None or c["stop"] != 0xFFFF:
                res = r
                break
        if res is None:
            res = r
        if res == 0 and book_of(c, q) is None:
            codes.append(101)
            continue
        if res == 0:
            if _in_journal(slots, q):
                codes.append(2)
                continue
            if all(slots):
                codes.append(3)
                continue
            return True, (npc, cell, book_of(c, q))
        codes.append(res)
    return False, codes


def predecessors(q):
    """Предшественники задания по ячейкам «ВЫДАЁТ»: [множество P по ячейке] (пустое — без предшественника)."""
    return [{c["P"]} if c["qblock"] == 1 and c["P"] <= QMAX else set() for _n, _c, _k, c in _real_gives(q)]


def dependents(q):
    """Задания, у которых q — предшественник (+53) хотя бы в одной ячейке «ВЫДАЁТ»."""
    gives, _t = cells()
    return {t for t in gives if any(c["qblock"] == 1 and c["P"] == q for _n, _c, _k, c in _real_gives(t))}


def repeatable(q):
    """Нет гейта «не выполнено» на себя ни в одной ячейке выдачи (6 заданий на живых)."""
    lst = _real_gives(q)
    return bool(lst) and not any(c["qblock"] == 1 and q in (c["A"], c["B"]) for _n, _c, _k, c in lst)


def step_rewards(q):
    """Ячейки «ПРИНИМАЕТ» без завершения (действие 0/1), у которых есть награда: [(шаг, [номера])] (перепроверка 22 М2)."""
    _g, takes = cells()
    out = []
    for npc, cell, st, keys in takes.get(q, []):
        for key in keys:
            c = cond(key) if key > 0 else None
            if c and c["action"] != 2 and c["reward_flag"] == 1 and any(x > 0 for x in c["rewards"]):
                out.append((st, [x for x in c["rewards"] if x > 0]))
    return out


def finish_rewards(q, step=None):
    """Награды ячеек «ПРИНИМАЕТ» с действием 2 (завершить): [(npc, ячейка, шаг, ключ, [номера RepayTable по вариантам])].
    step — шаг взятого задания (сервер сдаёт пару «задание, шаг»); None — все шаги."""
    _g, takes = cells()
    out = []
    for npc, cell, st, keys in takes.get(q, []):
        if step is not None and st != step:
            continue
        for key in keys:
            c = cond(key) if key > 0 else None
            if c and c["action"] == 2:
                out.append((npc, cell, st, key, [x for x in c["rewards"] if x > 0] if c["reward_flag"] == 1 else []))
    return out
