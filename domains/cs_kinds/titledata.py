# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/titledata.py — область «Звания» (волна А4.6, 20.11.2026; разбор Reports/admin_center/research_a4_data.md §1.6, §3, §5;
система званий — Reports/title_system.md §2, §11.6, §14, §15; выдача и снятие — research_titles_honor.md §1–§3).

Только правка СУЩЕСТВУЮЩИХ записей (решение владельца 19.11): званий не добавляется, номер (= бит маски P21, 512 бит) не меняется.

СЕРВЕР: GameServer\\ConfigSet\\FameInfo.txt во всех GS (загрузчик sub_4A18F0, GameServer.c:65319: число N (P21 поднял предел 256 → 512),
затем N записей по 46 слов, запись 96 б; на dev 20.11 у всех трёх копий acdb4845, одна запись — одна строка TAB). Правятся:
  title.points  кол. 42 (+86, __int16) — очки славы: AddFameBit sub_54A980 :126540 «Fmpoint += очки», снятие sub_54AD00 «−=»,
                вход recvDB :127077 пересчитывает Fmpoint по маске (2274). ПАРА: title_list.Point (+96, колонка «Очки» окна).
  title.enabled кол. 1 (+2, «atol ≠ 0») — включено: sub_54A050 :126126 при нуле сразу выходит. ПАРА: title_list.Enabled (+200) —
                клиент выводит строку, если поле ≠ 0 (QuestLog_PopulateCategoryList, quest.c: «*(rec + 200)»). У обеих сторон
                1 и 2 неразличимы — включение пишет 2 (как у 208 из 220 включённых).
  title.cond    кол. 3 (+4 DWORD цель), кол. 4 (+8 DWORD параметр), кол. 43 (+88 вид второй ступени), кол. 44 (+90 __int16 её порог) —
                только сервер (у клиента условий нет — title_system.md §11.1 «требования по уровню в таблице НЕТ»). Кто какое поле
                читает — по ВЕТКАМ sub_54B260 (GameServer.c:126677) и sub_54A050 (:126114), см. reads(). ★ Ревизия 38 К-3: ещё два
                читателя вне веток — параметр звания 34 сравнивает копка sub_546C00 (:124962, «FameInfo + 3272» = 96·34 + 8 против поля
                +5 найденного предмета; только при равенстве зовёт sub_54A050(…, 34)) — правка отказом «смысл не подтверждён»; цель
                любого звания читает RecvClient_TitleItemCheck (:135428/135438) — предмет-звание расходует «цель − прогресс», но выдача
                всё равно идёт ветками sub_54A050, поэтому правимость цели решают ветки. ★ Ревизия 38 М-1: у званий P88 (P88_GOALS)
                цель в памяти задаёт patches.ini [P88_TitleEvents] Threshold<id> (p88_title_events.cpp ApplyGoals) — при включённом P88
                правка кол. 3 не действует, отказ.
  title.bonus   слот m: кол. 12+5m (+26+10m код), 13+5m / 14+5m (min/max ПЕРВОГО значения). AddFameBit пишет код и случайное
                sub_5329A0(min, max) в запись звания игрока; sub_54D210 (:127601) применяет только коды 65…71 ('A'…'G'), значение — процент
                от базы (sub_43B750 с a4 = 1). ВТОРОЕ значение (кол. 15/16 + 5m) потребителя нет (sub_54D210 его не читает) — не правится.
                ПАРА: title_list.OptionTypeId<m> (+176 + 4m) — имя бонуса из title_option; title_option 65…71 = «Сила, Выносливость,
                Интеллект, Энергия, Ловкость, Удача, Все характеристики» (второй метод: клиентский словарь = коды сервера).
Не правятся: кол. 2 (читателей нет), 5…11 (структура наборов sub_54A610 — двусторонняя связь предпосылок и «следующих»), 45 (выбор
ветки), тексты (вид А4.2 title.name / title.desc), ClassReq/группа/цвет (только отображение клиента).
NpcServer\\FameInfo\\FameInfo.txt (63 записи, другой формат) — читает только загрузчик sub_44FF80: аксессор sub_44FF70 не вызывается,
адреса таблицы 0x77F1D4/0x77F1D8 в образе NpcServer.exe встречаются только в загрузчике (сплошной поиск байтов, 20.11) — не правится.

Indun — своя база (per_copy): та же логическая правка по значениям каждой копии, у копии с другим прежним значением поля — отказ
(отличия не затираются), записи нет — отказ; Ch2 = полю.
ДЕРЖАТЕЛИ (Joy1: CharFameBank Fame1…4 — биты 0…255, CharFameHigh BankHi1…4 — 256…511; только чтение):
  * выключение звания, которое у кого-то есть, — ОТКАЗ: клиент скрывает строку (Enabled = 0), игрок не может ни снять его (6069 идёт
    по выбранной строке), ни увидеть, а бит, слава и надетый слот остаются (recvDBUserActiveFame не проверяет владение);
  * смена кода бонуса у звания с держателями — ОТКАЗ: код и значение бонуса держателя лежат в CharFame (Opidx/Opvalue), их пишет только
    AddFameBit при получении (2256 → UPCharFameOptionUp), при входе запись берётся из БД (recvDBUserFameInfo :127279) — FameInfo
    держателю не перечитывается, а клиент покажет НОВОЕ имя бонуса со старым кодом и значением;
  * очки, условия и разброс значений бонуса — предупреждение со списком (слава пересчитается при входе; выданное условием не
    пересматривается — sub_54A890 «бит стоит»; значения бонуса у держателей прежние); снижение цели — список «получат при
    следующем событии» (CharFame Condition1 ≥ новой цели).
Эти правила ПЕРЕПРОВЕРЯЮТСЯ перед выкладкой и откатом (apply_guard; урок ревизий 36–37): держатели могли появиться после проверки.
Перед выкладкой и откатом — по итоговому состоянию FameInfo («живая + файлы набора» / «живая, файлы набора — базой»).
ПОСЛЕ ВЫКЛАДКИ И ОТКАТА: Joy1.dbo.AsdaFamePoints (ac0w: UPCharFameBitDis вычитает очки по ней) приводится к живому FameInfo.txt
(after_server; asda_ops — только UPDATE (Point)). Побочных эффектов при импорте нет.
"""
import os

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "titledata", "Звания"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
FAME = "ConfigSet\\FameInfo.txt"
SRV_FILES = [("GS", FAME, "per_copy")]
NCOL = 46
ID_MAX = 511                                       # P21: маска 512 бит
I16_MAX = 32767
LVL_TOP = 150
LOOP_BITS = 0xA0 * 8                               # маска выполненных заданий CUser+0x552E+490 — 0xA0 байт (GameServer.c:37581)
RATING = set(range(65, 70))                        # хозяин — P23 (research_titles_honor.md §2.4)
STAT_CODES = {65: "Сила", 66: "Выносливость", 67: "Интеллект", 68: "Энергия", 69: "Ловкость", 70: "Удача", 71: "Все характеристики"}
ON_VALUE = 2
NO_JOY1 = "нет связи с Joy1"
# ветки sub_54B260 (GameServer.c:126677…127076; списки case сняты разбором декомпила 20.11)
_R = ((0, 20), (22, 28), (30, 44), (46, 46), (70, 128), (130, 132), (140, 143), (145, 187), (206, 206), (219, 220), (223, 236), (245, 246))
SIMPLE = {i for a, b in _R for i in range(a, b + 1)}                  # v42 = счётчик ≥ кол.3
LOOP = {29, 45}                                                     # доля выполненных заданий среди первых кол.3
EQ = set(range(47, 56))                                             # кол.3 — РАВЕНСТВО параметру события, кол.4 — порог второго
DBL = set(range(237, 245))                                          # кол.3 и кол.4 — два счётчика
TITLES21 = 21                                                       # «N званий»: sub_54B260 :127045 счётчик ≥ кол.3
DIG34 = 34                                                          # ★ р38 К-3: копка sub_546C00 :124962 — кол.4 против поля +5 предмета
P88_INI = "patches.ini [P88_TitleEvents]"                           # ★ р38 М-1: звания P88 — srvtables.P88_GOALS (g_goals p88_title_events.cpp)
COND = {"target": (3, "цель (кол. 3)"), "param": (4, "параметр (кол. 4)"), "mode2": (43, "вид второй ступени (кол. 43)"),
        "thr2": (44, "порог второй ступени (кол. 44)")}
CLIENT_COL = {"points": "Point", "enabled": "Enabled"}
KINDS = {
    "title.points": ("Звание: очки славы (FameInfo кол. 42 + title_list.Point)", ("id", "value"), False),
    "title.enabled": ("Звание: включено (FameInfo кол. 1 + title_list.Enabled)", ("id", "on"), False),
    "title.cond": ("Звание: условия получения (FameInfo кол. 3, 4, 43, 44 — только сервер)", ("id", "fields"), False),
    "title.bonus": ("Звание: бонус характеристики (FameInfo кол. 12+5m…14+5m + title_list.OptionTypeId)", ("id", "slot", "code", "min", "max"),
                    False),
}


def rng_cond(k):
    """Пределы полей условия (те же отдаёт справка — поля формы веба)."""
    return {"target": (0, 2147483647), "param": (-2147483648, 2147483647), "mode2": (0, 2), "thr2": (0, I16_MAX)}[k]


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def norm(kind, p):
    tid = E._ival(p, "id", 0, ID_MAX)
    if kind == "title.points":
        return {"id": tid, "value": E._ival(p, "value", 0, I16_MAX)}
    if kind == "title.enabled":
        return {"id": tid, "on": E._ival(p, "on", 0, 1)}
    if kind == "title.bonus":
        code = E._ival(p, "code", -1, 71)
        if code not in STAT_CODES and code not in (-1, 0):
            raise OpRefused("код бонуса %d: сервер применяет только 65…71 (sub_54D210: Сила, Выносливость, Интеллект, Энергия, Ловкость, Удача, "
                            "Все характеристики), −1 — слота нет, 0 — пустой слот" % code)
        lo, hi = E._ival(p, "min", 0, I16_MAX), E._ival(p, "max", 0, I16_MAX)
        if lo > hi:
            raise OpRefused("бонус: минимум %d больше максимума %d" % (lo, hi))
        if code in (-1, 0) and (lo or hi):
            raise OpRefused("бонус без кода характеристики (код %d): значения должны быть 0 — сервер их не применяет" % code)
        return {"id": tid, "slot": E._ival(p, "slot", 0, 5), "code": code, "min": lo, "max": hi}
    from domains.cs_kinds.questtables import _fields
    return {"id": tid, "fields": _fields(p, tuple(COND), rng_cond)}


def target_key(kind, p):
    return "title:%d:%s" % (p["id"], kind.split(".")[1] + (":%d" % p["slot"] if kind == "title.bonus" else ""))


# =====================================================================================================================
# Таблица и ветки сервера
# =====================================================================================================================
def _fields_of(line):
    return line.split(b"\t")


def _num(f, i):
    return E._int(f[i].decode("latin-1"))


def record(t, tid, where):
    """(номер строки, поля) записи tid копии (по ПОРЯДКУ, как сервер; id = позиция) или OpRefused."""
    i = E.record_line(t, tid, NCOL)
    if i is None:
        raise OpRefused("таблица %s: слова не ложатся построчно по %d на запись — порядок записей сервера не доказан, правка не делается" % (where, NCOL))
    if i < 0:
        raise OpRefused("звания %d нет в %s — в А4 только правка существующих записей, новые звания не создаются" % (tid, where))
    f = _fields_of(t.lines[i])
    if len(f) != NCOL:
        raise OpRefused("таблица %s: запись %d — поля TAB не совпадают со словами сервера, правка не делается" % (where, tid))
    if _num(f, 0) != tid:
        raise OpRefused("таблица %s: у записи %d номер %d — номер звания = позиция записи, правка не делается" % (where, tid, _num(f, 0)))
    return i, f


def rec_values(f):
    return [_num(f, k) for k in range(NCOL)]


def reads(tid, rec):
    """Поля условия, которые сервер ЧИТАЕТ для звания tid при записи rec → {поле: как читает}. Источник — ветки sub_54A050 и
    sub_54B260: при кол.45 = 1 — общий накопитель (кол.3, 43, 44); иначе switch по номеру звания; номер вне веток — поля не читаются
    (звание выдаётся только наборами, рейтингом P23 или панелью)."""
    out = {}
    if rec[45] == 1:
        out = {"target": "счётчик ≥ цели (общий накопитель, кол. 45 = 1)", "mode2": "вторая ступень", "thr2": "вторая ступень"}
    elif tid in SIMPLE:
        out = {"target": "счётчик ≥ цели", "mode2": "вторая ступень", "thr2": "вторая ступень"}
        if tid == 2:
            out["param"] = "счётчик растёт, только если уровень персонажа ≥ параметра (sub_54A050, ветка 2)"
    elif tid in LOOP:
        out = {"target": "доля выполненных заданий среди первых N (N = цель, не больше %d)" % LOOP_BITS,
               "param": "нужная доля, %", "mode2": "вторая ступень (доля, %)", "thr2": "вторая ступень (доля, %)"}
    elif tid in EQ:
        out = {"param": "второй параметр события ≥ параметра", "mode2": "вторая ступень", "thr2": "вторая ступень"}
    elif tid in DBL:
        out = {"target": "первый счётчик ≥ цели", "param": "второй счётчик ≥ параметра", "mode2": "вторая ступень", "thr2": "вторая ступень"}
    elif tid == TITLES21:
        out = {"target": "число полученных званий ≥ цели (sub_54B260, звание 21)"}
    if tid == DIG34:
        out = dict(out, param="копка (sub_546C00): счётчик растёт, только если поле +5 найденного предмета = параметру")
    return out


UNSAFE = {
    "target_eq": "у званий 47…55 цель (кол. 3) сравнивается с параметром события на РАВЕНСТВО (sub_54B260) — это не порог, смысл параметра "
                 "события не подтверждён, правка не делается",
    "param_19": "у звания 19 параметр (кол. 4) сравнивается с нулём (sub_54A050: v12 = 0 в этой ветке) — смысл не подтверждён, правка не делается",
    "param_gender": "у званий 35…37 параметр (кол. 4) сравнивается с полем персонажа, которое декомпил называет gender_ (данные 1/2/3) — смысл "
                    "не подтверждён, правка не делается",
    # ★ ревизия 38 К-3 / М-1 (тексты без чисел — их же показывает справка веба через T())
    "param_34": "у звания 34 параметр (кол. 4) копка сравнивает с полем +5 найденного предмета (sub_546C00, GameServer.c:124962) — смысл поля "
                "предмета не подтверждён, правка не делается",
    "p88_on": "цель этого звания задаёт patches.ini [P88_TitleEvents] Threshold<номер> — P88 включён и при первом событии пишет порог из ini в "
              "FameInfo в памяти (p88_title_events.cpp ApplyGoals), правка кол. 3 не подействует, не делается",
    "p88_unread": "цель этого звания может задавать patches.ini [P88_TitleEvents] — patches.ini не прочитан, вслепую не делается",
}


def _unsafe(tid, rec, field):
    if field == "param" and tid == DIG34:
        return UNSAFE["param_34"]                      # гейт копки — до накопителя, при любой кол. 45
    if rec[45] == 1:
        return None
    if field == "target" and tid in EQ:
        return UNSAFE["target_eq"]
    if field == "param" and tid == 19:
        return UNSAFE["param_19"]
    if field == "param" and tid in (35, 36, 37):
        return UNSAFE["param_gender"]
    return None


def issues(tid, rec):
    """Неисправности записи, которые сервер читает (итоговое состояние) → {код: текст}."""
    r = reads(tid, rec)
    out = {}
    if "target" in r and rec[3] <= 0:
        out["target0"] = ("цель %d: при цели 0 и меньше «счётчик ≥ цели» выполняется на первом же событии (а при виде второй ступени 2 — деление "
                          "на ноль, sub_54B260)" % rec[3])
    if ("target" in r or rec[45] == 1) and rec[43] == 2 and rec[3] == 0:
        out["div0"] = "вид второй ступени 2 при цели 0: sub_54B260 делит счётчик на цель (кол. 3) — деление на ноль"
    if tid in LOOP and rec[45] != 1 and rec[3] > LOOP_BITS:
        out["loop"] = ("цель %d больше %d: sub_54B260 перебирает биты маски выполненных заданий (0xA0 байт, GameServer.c:37581) — чтение за "
                       "её концом" % (rec[3], LOOP_BITS))
    if rec[43] not in (0, 1, 2):
        out["mode2"] = "вид второй ступени %d: сервер знает только 0, 1, 2" % rec[43]
    if not 0 <= rec[44] <= I16_MAX:
        out["thr2"] = "порог второй ступени %d вне 0…32767 (__int16)" % rec[44]
    if not 0 <= rec[42] <= I16_MAX:
        out["pts"] = "очки славы %d вне 0…32767 (__int16)" % rec[42]
    if tid == 2 and rec[45] != 1 and not 1 <= rec[4] <= LVL_TOP:
        out["lvl"] = "параметр звания 2 — уровень персонажа, нужен 1…%d, а дано %d" % (LVL_TOP, rec[4])
    for m in range(6):
        c, lo, hi = rec[12 + 5 * m], rec[13 + 5 * m], rec[14 + 5 * m]
        if c in STAT_CODES and not (0 <= lo <= hi <= I16_MAX):
            out["bon%d" % m] = "бонус %d: значения %d…%d — нужно 0 ≤ мин. ≤ макс. ≤ 32767" % (m, lo, hi)
    return out


# =====================================================================================================================
# Держатели (Joy1, только чтение)
# =====================================================================================================================
def _bank_rows():
    """Все строки масок «получено» (CharFameBank + CharFameHigh) → [(учётка, персонаж, имя, уровень, {биты}, надето {id})] или None."""
    _bank_rows.last_error = None
    try:
        from core import db
        with db.GameReader("joy1") as j:
            rows = j.rows("SELECT b.Userindex AS u, b.Charidx AS c, b.Fame1 AS f1, b.Fame2 AS f2, b.Fame3 AS f3, b.Fame4 AS f4, b.Fmidx1 AS e1, "
                          "b.Fmidx2 AS e2, ch.Charname AS nm, ch.Lvl AS lv FROM dbo.CharFameBank b LEFT JOIN dbo.Charinfo ch ON "
                          "ch.Userindex = b.Userindex AND ch.Charidx = b.Charidx")
            hi = j.rows("SELECT UserIndex AS u, CharIdx AS c, BankHi1 AS h1, BankHi2 AS h2, BankHi3 AS h3, BankHi4 AS h4 FROM dbo.CharFameHigh")
    except Exception as ex:
        _bank_rows.last_error = str(ex)[:200]
        return None
    his = {(int(r["u"]), int(r["c"])): r for r in hi}
    out = []
    for r in rows:
        bits = set()
        for w in range(4):
            v = int(r["f%d" % (w + 1)] or 0) & 0xFFFFFFFFFFFFFFFF
            bits |= {64 * w + b for b in range(64) if v >> b & 1}
        h = his.get((int(r["u"]), int(r["c"])))
        if h:
            for w in range(4):
                v = int(h["h%d" % (w + 1)] or 0) & 0xFFFFFFFFFFFFFFFF
                bits |= {256 + 64 * w + b for b in range(64) if v >> b & 1}
        eq = {int(x) for x in (r["e1"], r["e2"]) if x is not None and int(x) >= 0}
        out.append((int(r["u"]), int(r["c"]), r["nm"] or "", int(r["lv"] or 0), bits, eq))
    return out


_bank_rows.last_error = None


def holders(ids):
    """{звание: [(учётка, персонаж, имя, уровень, надето)]} или None (причина — holders.last_error)."""
    holders.last_error = None
    rows = _bank_rows()
    if rows is None:
        holders.last_error = _bank_rows.last_error
        return None
    out = {int(i): [] for i in ids}
    for u, c, nm, lv, bits, eq in rows:
        for i in out:
            if i in bits:
                out[i].append((u, c, nm, lv, i in eq))
    return out


holders.last_error = None


def progress(tid, target):
    """Персонажи «в процессе» (бита нет, CharFame.Condition1 ≥ target) → [(учётка, персонаж, имя, уровень, счётчик)] или None."""
    progress.last_error = None
    try:
        from core import db
        with db.GameReader("joy1") as j:
            rows = j.rows("SELECT f.Userindex AS u, f.Charidx AS c, f.Condition1 AS n, ch.Charname AS nm, ch.Lvl AS lv FROM dbo.CharFame f "
                          "LEFT JOIN dbo.Charinfo ch ON ch.Userindex = f.Userindex AND ch.Charidx = f.Charidx WHERE f.Fameidx = ? AND "
                          "f.Condition1 >= ?", (int(tid), int(target)))
    except Exception as ex:
        progress.last_error = str(ex)[:200]
        return None
    bank = _bank_rows()
    if bank is None:
        progress.last_error = _bank_rows.last_error
        return None
    have = {(u, c) for u, c, _n, _l, bits, _e in bank if int(tid) in bits}
    return [(int(r["u"]), int(r["c"]), r["nm"] or "", int(r["lv"] or 0), int(r["n"] or 0)) for r in rows
            if (int(r["u"]), int(r["c"])) not in have]


progress.last_error = None


def _who(lst):
    """Список персонажей через «; » (переводчик переводит каждую часть)."""
    parts = ["%s (%d/%d, ур. %d%s)" % (x[2] or "?", x[0], x[1], x[3], ", надето" if len(x) > 4 and x[4] is True else "") for x in lst[:10]]
    if len(lst) > 10:
        parts.append("и ещё %d" % (len(lst) - 10))
    return "; ".join(parts)


def _who_err(lst):
    """Список персонажей для ОТКАЗА (через запятую, без «; » и без слов — переводчик режет вложенное по «; »)."""
    return ", ".join("%s (%d/%d)" % (x[2] or "?", x[0], x[1]) for x in lst[:10]) + (" +%d" % (len(lst) - 10) if len(lst) > 10 else "")


def _held(ev, tid):
    cache = ev.__dict__.setdefault("_title_holders", {})
    if tid not in cache:
        h = holders([tid])
        cache[tid] = None if h is None else h[tid]
    return cache[tid]


def _tname(tid):
    from domains import titles as TT
    return "%d «%s»" % (tid, TT.title_name(tid))


# ---------------------------------------------------------------------------------------------------------------------
# ★ ревизия 38 М-1: пороги P88 (patches.ini всех GS; правка ini — не эта область, шаг А5)
# ---------------------------------------------------------------------------------------------------------------------
def p88_goals():
    """{GS: {"on", "thr"}} по живому patches.ini (srvtables.p88_goals_all) или None (причина — p88_goals.last_error)."""
    from domains import srvtables
    p88_goals.last_error = None
    try:
        return srvtables.p88_goals_all(ttl=0)
    except Exception as ex:
        p88_goals.last_error = str(ex)[:200]
        return None


p88_goals.last_error = None


def _p88_ids():
    from domains import srvtables
    return set(srvtables.P88_GOALS)


def _p88_text(st, tid):
    """«GameServer 300, Indun_GameServer 300 [P88 = 0]» — пороги ini по копиям (без слов: текст отказа переводится целиком)."""
    return ", ".join("%s %d%s" % (g, v["thr"].get(tid, 0), "" if v["on"] else " [P88 = 0]") for g, v in st.items())


def p88_target_block(tid, st):
    """Отказ правки цели звания P88 → текст или None. st — p88_goals() (None — не прочитано)."""
    if tid not in _p88_ids():
        return None
    if st is None:
        return ("звание %d: цель может задавать %s Threshold%d — patches.ini не прочитан (%s), вслепую не делается"
                % (tid, P88_INI, tid, p88_goals.last_error or "нет ответа"))
    on = [g for g, v in st.items() if v["on"]]
    if on:
        return ("звание %d: порог задаёт %s Threshold%d (%s) — P88 включён в %s и при первом событии пишет порог из ini в FameInfo в памяти "
                "(p88_title_events.cpp ApplyGoals), правка кол. 3 не подействует, не делается (ini правится не здесь)"
                % (tid, P88_INI, tid, _p88_text(st, tid), ", ".join(on)))
    return None


def _p88(ev):
    if "_title_p88" not in ev.__dict__:
        ev.__dict__["_title_p88"] = p88_goals()
    return ev.__dict__["_title_p88"]


# ---------------------------------------------------------------------------------------------------------------------
# ★ ревизия 38 М-2: кто выдаёт звание наборами (каскад sub_54A610 «включено» не проверяет)
# ---------------------------------------------------------------------------------------------------------------------
def set_sources(t, tid, where):
    """Записи таблицы t, у которых tid — «следующее» (кол. 10/11) → [номер записи]."""
    n = E._int(t.lines[0].decode("latin-1"))
    out = []
    for k in range(n):
        try:
            v = rec_values(record(t, k, where)[1])
        except OpRefused:
            continue
        if tid in (v[10], v[11]) and k not in out:
            out.append(k)
    return out


# =====================================================================================================================
# Применение позиций к копиям
# =====================================================================================================================
def _apply(ev, tid, cols, rep):
    """{кол.: новое} → прежние значения GameServer; правка ложится на каждую копию по её значениям (per_copy)."""
    base, todo = None, []
    for g in E.GS:                                     # все копии проверяются ДО первой записи
        t = ev.st.get(g, FAME)
        i, f = record(t, tid, "%s\\%s" % (g, FAME))
        vals = rec_values(f)
        if base is None:
            base = vals
        else:
            diff = [c for c in cols if vals[c] != base[c]]
            if diff:
                raise OpRefused("копия %s: у звания %d кол. %s = %s, а в GameServer %s — отличия копии не затираются, правка не делается"
                                % (g, tid, ", ".join(map(str, diff)), ", ".join(str(vals[c]) for c in diff),
                                   ", ".join(str(base[c]) for c in diff)))
        todo.append((t, i, f))
    for t, i, f in todo:
        for c, v in cols.items():
            f[c] = E.set_token(f[c], v)
        t.set_line(i, b"\t".join(f))
    return base


def _cli_row(ev, tid):
    r = (getattr(ev.cli, "titles", None) or {}).get(tid)
    if r is None:
        raise OpRefused("звания %d нет в title_list клиента — в А4 только правка существующих записей" % tid)
    return r


def _cli_edit(ev, rep, tid, col, old, new):
    e = {"type": "csv_cell", "file": "title_list", "key_col": "Id", "key": str(tid), "col": col, "old": str(old), "new": str(new)}
    rep["client"].append(e)
    ev.client.append(e)


HOLD = "звание %s есть у %d перс.: %s — "
HOLD_PTS = HOLD + ("слава держателей пересчитается при входе (recvDB, 2274); до входа — прежняя слава и место в рейтинге славы (FamePointRank); "
                   "снятие вычтет новые очки (не ниже 0) — пересчёт славы панелью или вход это выровняют")
HOLD_COND = HOLD + "у них звание остаётся: выданное условием сервер не пересматривает (sub_54A890 — бит уже стоит)"
HOLD_BON = HOLD + "у них прежние значения бонуса (выпали при получении, sub_54A980), новые получат только новые держатели"


def _holder_note(ev, rep, tid, tmpl):
    """Предупреждение «звание есть у N перс.: список — что с ними будет» (tmpl — один из HOLD_*; переводы — core/i18n.py _A4_TITLES)."""
    h = _held(ev, tid)
    if h is None:
        rep["warnings"].append("держатели звания — не прочитано (%s)" % (holders.last_error or NO_JOY1))
    elif h:
        rep["warnings"].append(tmpl % (_tname(tid), len(h), _who(h)))
    return h


def k_title_points(ev, p, rep):
    tid, val = p["id"], p["value"]
    cr = _cli_row(ev, tid)
    old = _apply(ev, tid, {42: val}, rep)[42]
    cp = cr[2]
    if val == old and cp == old:
        raise OpRefused("у звания %d уже очки %d — менять нечего" % (tid, val))
    if cp != old:
        rep["warnings"].append("очки уже расходились: клиент %d, сервер %d — правка ставит обоим новое значение" % (cp, old))
    rep["text"] = "звание %s: очки славы %d → %d (сервер FameInfo ×%d GS, клиент title_list.Point)" % (_tname(tid), old, val, len(E.GS))
    rep["_balance"] = [{"what": "звание %d: очки славы" % tid, "old": old, "new": val, "codes": []}]
    if tid in RATING:
        rep["warnings"].append("звание %d — рейтинговое (P23 выдаёт и снимает его держателю сам): новые очки получит следующий держатель, "
                               "нынешнему слава пересчитается при входе" % tid)
    _holder_note(ev, rep, tid, HOLD_PTS)
    _cli_edit(ev, rep, tid, "Point", cp, val)


def k_title_enabled(ev, p, rep):
    tid, on = p["id"], p["on"]
    if tid in RATING:
        raise OpRefused("звание %d — рейтинговое (хозяин — P23: держатель записан в FameRatingHolder и самозаживление вернёт звание), "
                        "включённость не правится" % tid)
    cr = _cli_row(ev, tid)
    t = ev.st.get(E.GS[0], FAME)
    cur = rec_values(record(t, tid, "%s\\%s" % (E.GS[0], FAME))[1])
    old = cur[1]
    if bool(old) == bool(on) and bool(cr[1]) == bool(on):
        raise OpRefused(("звание %d уже включено — менять нечего (1 и 2 сервер и клиент не различают: «≠ 0»)" if on else
                         "звание %d уже выключено — менять нечего") % tid)
    new = ON_VALUE if on else 0
    if on and old:
        new = old                                      # сервер уже включён — оставить его число (клиент приводится к нему)
    if not on:
        src = {}
        for g in E.GS:                                 # ★ ревизия 38 М-2: каскад наборов выдал бы выключенное звание скрытым
            for k in set_sources(ev.st.get(g, FAME), tid, "%s\\%s" % (g, FAME)):
                src.setdefault(k, []).append(g)
        if src:
            raise OpRefused("звание %s выдаёт набор (кол. 10/11 записей %s): каскад sub_54A610 выдаёт «следующее» звание без проверки "
                            "«включено» — игрок получил бы скрытое звание, которое не снять, правка не делается"
                            % (_tname(tid), ", ".join(map(str, sorted(src)))))
        h = _held(ev, tid)
        if h is None:
            raise OpRefused("выключение звания: держатели не прочитаны (%s) — вслепую не делается" % (holders.last_error or NO_JOY1))
        if h:
            raise OpRefused("звание %s есть у %d перс. (%s): клиент скрыл бы строку (Enabled = 0), игрок не смог бы ни увидеть, ни снять "
                            "его, а бит, слава и надетый слот остались бы (recvDBUserActiveFame не проверяет владение) — правка не делается"
                            % (_tname(tid), len(h), _who_err(h)))
    else:
        if not reads(tid, cur):
            rep["warnings"].append("у звания %d нет ветки выдачи по событию (sub_54B260) — включённое, его всё равно не получить игрой, только "
                                   "наборами, рейтингом или панелью" % tid)
    _apply(ev, tid, {1: new}, rep)
    if bool(cr[1]) != bool(old):
        rep["warnings"].append("включённость уже расходилась: клиент %d, сервер %d — правка ставит обоим новое значение" % (cr[1], old))
    rep["text"] = (("звание %s: включить (сервер FameInfo кол. 1: %d → %d ×%d GS, клиент title_list.Enabled %d → %d)" if on else
                    "звание %s: выключить (сервер FameInfo кол. 1: %d → %d ×%d GS, клиент title_list.Enabled %d → %d)")
                   % (_tname(tid), old, new, len(E.GS), cr[1], new))
    rep["_balance"] = [{"what": "звание %d: включено" % tid, "old": old, "new": new, "codes": [], "kind": "type"}]
    if cr[1] != new:
        _cli_edit(ev, rep, tid, "Enabled", cr[1], new)


def k_title_cond(ev, p, rep):
    tid, want = p["id"], p["fields"]
    t = ev.st.get(E.GS[0], FAME)
    cur = rec_values(record(t, tid, "%s\\%s" % (E.GS[0], FAME))[1])
    rd = reads(tid, cur)
    for k in want:
        why = _unsafe(tid, cur, k)
        if why:
            raise OpRefused(why)
        if k not in rd:
            if k == "target":                          # ★ ревизия 38 К-3: цель читает ещё RecvClient_TitleItemCheck — но выдача только ветками
                raise OpRefused("звание %d: ветки выдачи (sub_54A050 / sub_54B260) цель для этого звания не читают, а RecvClient_TitleItemCheck "
                                "берёт её только для расхода предметов-званий — звание этим не выдаётся, правка не подействует, не делается"
                                % tid)
            raise OpRefused(("звание %d: сервер поле «%s» для этого звания не читает (ветки sub_54A050 / sub_54B260, кол. 45 = 1) — правка "
                             "не подействует, не делается" if cur[45] == 1 else "звание %d: сервер поле «%s» для этого звания не читает "
                             "(ветки sub_54A050 / sub_54B260) — правка не подействует, не делается") % (tid, COND[k][1]))
    if "target" in want and tid in _p88_ids():         # ★ ревизия 38 М-1: цель звания P88 задаёт patches.ini
        why = p88_target_block(tid, _p88(ev))
        if why:
            raise OpRefused(why)
        rep["warnings"].append("P88 выключен во всех GS — цель берётся из FameInfo, но если P88 включат, порог снова возьмёт %s Threshold%d"
                               % (P88_INI, tid))
    cols = {COND[k][0]: v for k, v in want.items()}
    changes = [(k, cur[COND[k][0]], v) for k, v in want.items() if cur[COND[k][0]] != v]
    if not changes:
        raise OpRefused("у звания %d условия уже такие — менять нечего" % tid)
    new = list(cur)
    for c, v in cols.items():
        new[c] = v
    if tid in LOOP and new[3] > LOOP_BITS:
        raise OpRefused(issues(tid, new)["loop"] + " — правка не делается")
    if "target" in want and new[3] <= 0:
        raise OpRefused("цель %d: при цели 0 и меньше «счётчик ≥ цели» выполняется на первом же событии (а при виде второй ступени 2 — деление "
                        "на ноль, sub_54B260) — правка не делается" % new[3])
    if tid == 2 and "param" in want and not 1 <= new[4] <= LVL_TOP:
        raise OpRefused("параметр звания 2 — уровень персонажа, нужен 1…%d, а дано %d" % (LVL_TOP, new[4]))
    _apply(ev, tid, cols, rep)
    if new[43] == 2 and new[44] > 100 or tid in LOOP and (new[4] > 100 or new[43] and new[44] > 100):
        rep["warnings"].append("порог в процентах больше 100 — эта ступень не выполнится никогда")
    lines = ["%s: %d → %d" % (COND[k][1], o, n) for k, o, n in changes]
    rep["text"] = "звание %s, условия: %s (сервер FameInfo ×%d GS; у клиента условий нет — текст условия правится в «Текстах»)" % (
        _tname(tid), "; ".join(lines), len(E.GS))
    rep["lines"] = ["как читает сервер — %s: %s" % (COND[k][1], rd[k]) for k, _o, _n in changes]
    rep["_balance"] = [{"what": "звание %d: %s" % (tid, COND[k][1]), "old": o, "new": n, "codes": [], "kind": "type" if k == "mode2" else "value"}
                       for k, o, n in changes]
    rep["warnings"].append("описание условия у клиента (title_list.Desc) не меняется — если текст говорит о прежних числах, поправьте его "
                           "видом «Звание: описание» во вкладке «Тексты»")
    _holder_note(ev, rep, tid, HOLD_COND)
    if "target" in want and want["target"] < cur[3] and "target" in rd:
        pr = progress(tid, want["target"])
        if pr is None:
            rep["warnings"].append("кто получит звание при снижении цели — не прочитано (%s)" % (progress.last_error or NO_JOY1))
        elif pr:
            rep["warnings"].append("цель снижается: у %d перс. счётчик уже не меньше новой цели %d: %s — они получат звание при следующем "
                                   "событии этого вида или при GM-пересчёте P25 (SweepAllTitles: игроки в игре, sub_54B260 по накопленному "
                                   "счётчику)" % (len(pr), want["target"], "; ".join(
                                       "%s (%d/%d, ур. %d, счётчик %d)" % (x[2] or "?", x[0], x[1], x[3], x[4]) for x in pr[:10])))


def k_title_bonus(ev, p, rep):
    tid, m, code, lo, hi = p["id"], p["slot"], p["code"], p["min"], p["max"]
    cr = _cli_row(ev, tid)
    c0 = 12 + 5 * m
    t = ev.st.get(E.GS[0], FAME)
    cur = rec_values(record(t, tid, "%s\\%s" % (E.GS[0], FAME))[1])
    oc, olo, ohi = cur[c0], cur[c0 + 1], cur[c0 + 2]
    if (oc, olo, ohi) == (code, lo, hi):
        raise OpRefused("у звания %d бонус %d уже такой — менять нечего" % (tid, m))
    cli_new = code if code in STAT_CODES else 0
    if (oc in STAT_CODES or code in STAT_CODES) and oc != code:
        h = _held(ev, tid)
        if h is None:
            raise OpRefused("смена кода бонуса: держатели не прочитаны (%s) — вслепую не делается" % (holders.last_error or NO_JOY1))
        if h:
            raise OpRefused("звание %s есть у %d перс. (%s): код и значение бонуса держателя записаны при получении (AddFameBit → CharFame "
                            "Opidx/Opvalue) и FameInfo им не перечитывается, а клиент показал бы новое имя бонуса со старым кодом — смена "
                            "кода бонуса не делается" % (_tname(tid), len(h), _who_err(h)))
    _apply(ev, tid, {c0: code, c0 + 1: lo, c0 + 2: hi}, rep)
    nm = lambda c: STAT_CODES.get(c, "нет" if c == -1 else "пусто")
    rep["text"] = "звание %s: бонус %d: %s %d…%d%% → %s %d…%d%% (сервер FameInfo ×%d GS, клиент title_list.OptionTypeId того же слота)" % (
        _tname(tid), m, nm(oc), olo, ohi, nm(code), lo, hi, len(E.GS))
    bal = []
    if oc != code and (oc in STAT_CODES or code in STAT_CODES):
        bal.append({"what": "звание %d: бонус %d — характеристика" % (tid, m), "old": oc, "new": code, "codes": [], "kind": "type"})
    if code in STAT_CODES:
        bal.append({"what": "звание %d: бонус %d — максимум, %%" % (tid, m), "old": ohi if oc == code else 0, "new": hi, "codes": []})
    rep["_balance"] = bal
    if code in STAT_CODES:
        rep["lines"] = ["как применяет сервер: %s + случайное %d…%d %% от базы (sub_5329A0 при получении, sub_54D210 / sub_43B750 при надевании)"
                        % (STAT_CODES[code], lo, hi)]
        if hi > 100:
            rep["warnings"].append("бонус больше 100 % от базы характеристики — характеристика вырастет больше чем вдвое")
        if not cr[3 + 6 + m]:
            rep["warnings"].append("у клиента знак «%%» у бонуса %d выключен (title_list.IsPercent%d = 0) — окно покажет число без «%%», "
                                   "а сервер даёт проценты" % (m, m))
    _holder_note(ev, rep, tid, HOLD_BON)
    if cr[3 + m] != (oc if oc in STAT_CODES else 0):
        rep["warnings"].append("бонус клиента уже расходился: OptionTypeId%d = %d, сервер код %d — правка ставит обоим новое значение"
                               % (m, cr[3 + m], oc))
    if cr[3 + m] != cli_new:
        _cli_edit(ev, rep, tid, "OptionTypeId%d" % m, cr[3 + m], cli_new)


# =====================================================================================================================
# Итог набора, перепроверка, после выкладки
# =====================================================================================================================
def _touched(ev):
    out = {}
    for r in ev.positions:
        if r["kind"] in KINDS and not r["errors"] and isinstance(r.get("params"), dict):
            try:
                out.setdefault(int(r["params"]["id"]), []).append(r)
            except (KeyError, TypeError, ValueError):
                pass
    return out


def after_run(ev):
    """По ИТОГОВОМУ состоянию набора (все позиции применены — порядок не важен): запись каждого тронутого звания в каждой копии не
    получает новых неисправностей (сравнение с базой копии); у копий итог одинаков в правленых полях."""
    tt = _touched(ev)
    if not tt:
        return
    for tid, rs in sorted(tt.items()):
        bad = []
        for g in E.GS:
            try:
                t = ev.st.get(g, FAME)
                _i, f = record(t, tid, "%s\\%s" % (g, FAME))
                base = E.Table(t.rel, ev.snap.raw(t.rel))
                _j, fb = record(base, tid, "%s\\%s" % (g, FAME))
            except OpRefused as ex:
                bad.append(str(ex))
                continue
            now, was = rec_values(f), rec_values(fb)
            new = issues(tid, now)
            old = issues(tid, was)
            bad += ["копия %s: %s" % (g, v) for k, v in sorted(new.items()) if k not in old]
        for r in rs:
            for b in bad:
                if b not in r["errors"]:
                    r["errors"].append(b)
    if any(r["kind"] == "title.points" for rs in tt.values() for r in rs if not r["errors"]):
        ev.warnings.append("после выкладки и отката панель приведёт Joy1.dbo.AsdaFamePoints (очки для UPCharFameBitDis, ac0w) к живому FameInfo.txt")


def _fame_now(rels):
    md5 = E.live_md5(rels)
    return md5, E.Snap(dict(md5))


def _guard_state(cs, mode):
    """FameInfo трёх GS, каким он СТАНЕТ (apply — живые + файлы ЭТОГО набора из манифеста сухого прогона, md5 = утверждённому; rollback —
    живые, файлы набора — базой: живая = база или .bak_<метка> = база) и каким он есть сейчас → ({путь: байты}, {путь: байты}).
    Не сходится — исключение (у вызывающего «не прочитаны» → отказ)."""
    import json
    rels = [E.rel_of(g, FAME) for g in E.GS]
    files = {}
    for f in ((cs.get("check") or {}).get("server") or {}).get("files") or []:
        for g in f["gs"]:
            files[E.rel_of(g, f["table"])] = (f["base"], f["new"])
    man = None
    if any(r in files for r in rels) and cs.get("id") is not None:
        from domains import shopcs
        mp = shopcs.manifest_path(cs["id"])
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                man = json.load(fh)
    tag = (man or {}).get("tag") or cs.get("server_tag")
    baks = {r: r + ".bak_" + tag for r in rels if r in files} if mode == "rollback" and tag else {}
    md5, sn = _fame_now(rels + list(baks.values()))
    now, after = {}, {}
    for r in rels:
        now[r] = sn.raw(r)
        if r not in files:
            after[r] = now[r]
            continue
        base, new = files[r]
        if mode == "apply":
            if md5.get(r) == new:
                after[r] = now[r]
            elif md5.get(r) == base:
                lp = (((man or {}).get("files") or {}).get(r) or {}).get("local")
                if not lp or not os.path.isfile(lp):
                    raise RuntimeError("нет файла набора %s — сначала changeset server-dry" % r)
                with open(lp, "rb") as fh:
                    b = fh.read()
                if E.md5b(b) != new:
                    raise RuntimeError("файл набора %s ≠ утверждённому — повторите server-dry" % r)
                after[r] = b
            else:
                raise RuntimeError("%s на стойке — не база и не файл набора" % r)
        elif md5.get(r) == base:
            after[r] = now[r]
        elif r in baks and md5.get(baks[r]) == base:
            after[r] = sn.raw(baks[r])
        else:
            raise RuntimeError("%s: базы набора нет ни на месте, ни в .bak" % r)
    return after, now


def risky(ids, after, now):
    """Звания, у которых переход «сейчас → станет» опасен для держателей: {id: [что]} (выключение, смена кода бонуса)."""
    out = {}
    for r in after:
        ta, tn = E.Table(r, after[r]), E.Table(r, now[r])
        for tid in ids:
            try:
                fa = rec_values(record(ta, tid, r)[1])
                fn = rec_values(record(tn, tid, r)[1])
            except OpRefused:
                continue
            what = []
            if fn[1] and not fa[1]:
                what.append("off")
            if fa[3] != fn[3] and tid in _p88_ids():   # ★ ревизия 38 М-1: цель звания P88 — patches.ini перечитывается
                what.append("p88")
            for m in range(6):
                c = 12 + 5 * m
                if fa[c] != fn[c] and (fa[c] in STAT_CODES or fn[c] in STAT_CODES):
                    what.append(m)
            if what:
                out.setdefault(tid, []).extend(w for w in what if w not in out.get(tid, []))
    return out


def apply_guard(cs, mode):
    """Перед выкладкой (apply) и откатом (rollback) сервера: звания, у которых итоговый переход выключает их или меняет код бонуса, держатели
    перечитываются заново → [причины]. Не прочитано — причина с «не прочитаны» (откат и с ключом --held-ok не делается)."""
    ids = set()
    for it in cs.get("items") or []:
        if it["kind"] in KINDS:
            try:
                ids.add(int((it.get("params") or {}).get("id")))
            except (TypeError, ValueError):
                pass
    if not ids:
        return []
    try:
        after, now = _guard_state(cs, mode)
        rk = risky(sorted(ids), after, now)
        hid = sorted(t for t, w in rk.items() if any(x != "p88" for x in w))
        h = holders(hid) if hid else {}
        src = {}                                       # ★ ревизия 38 М-2: выключаемое звание выдаёт набор (по итоговому состоянию)
        for tid in (t for t, w in rk.items() if "off" in w and mode == "apply"):   # откат возвращает базу — там это уже было
            for r in after:
                src.setdefault(tid, set()).update(set_sources(E.Table(r, after[r]), tid, r))
    except Exception as ex:
        return ["звания: таблицы стойки не прочитаны (%s) — вслепую не делается" % str(ex)[:160]]
    if h is None:
        return ["звания: держатели не прочитаны (%s) — вслепую не делается" % (holders.last_error or NO_JOY1)]
    out = []
    if mode == "apply" and any("p88" in w for w in rk.values()):
        st = p88_goals()                               # перечитать ПЕРЕД выкладкой (ini могли поменять после проверки); откат цели — к базе, безопасен
        if st is None:
            return ["звания: patches.ini не прочитаны (%s) — вслепую не делается" % (p88_goals.last_error or "нет ответа")]
        for tid in sorted(t for t, w in rk.items() if "p88" in w):
            why = p88_target_block(tid, st)
            if why:
                out.append("звание %d: цель задаёт %s, P88 включён в %s" % (tid, P88_INI, ", ".join(g for g, v in st.items() if v["on"])))
    for tid in sorted(src):
        if src[tid]:
            out.append("звание %s: выключение, а его выдаёт набор (кол. 10/11 записей %s)" % (_tname(tid), ", ".join(map(str, sorted(src[tid])))))
    for tid in sorted(rk):
        if h.get(tid):
            for what in rk[tid]:
                if what == "p88":
                    continue
                if what == "off":
                    out.append("звание %s: выключение при %d держателях (%s)" % (_tname(tid), len(h[tid]), _who_err(h[tid])))
                else:
                    out.append("звание %s: смена кода бонуса %d при %d держателях (%s)" % (_tname(tid), what, len(h[tid]), _who_err(h[tid])))
    return out


def after_server(cs, mode):
    """После выкладки / отката (и server-sync): Joy1.dbo.AsdaFamePoints = очки живого GameServer\\ConfigSet\\FameInfo.txt (ac0w: снятие
    UPCharFameBitDis вычитает очки по ней). → [заметки]. Пишет только различающиеся строки (asda_ops: UPDATE (Point))."""
    if not any(it["kind"] in KINDS for it in cs.get("items") or []):
        return []
    try:
        rel = E.rel_of(E.GS[0], FAME)
        md5, sn = _fame_now([rel])
        t = E.Table(rel, sn.raw(rel))
        n = E._int(t.lines[0].decode("latin-1"))
        pts = {}
        for k in range(n):
            pts[k] = rec_values(record(t, k, rel)[1])[42]
        from core import db
        with db.GameWriter("joy1") as w:
            cur = {int(r["FameIdx"]): int(r["Point"]) for r in w.rows("SELECT FameIdx, Point FROM dbo.AsdaFamePoints WITH (UPDLOCK, HOLDLOCK)")}
            fix = [(k, v) for k, v in sorted(pts.items()) if k in cur and cur[k] != v]
            miss = sorted(set(pts) - set(cur))
            extra = sorted(set(cur) - set(pts))        # ★ ревизия 38 К-4: строки FameIdx ≥ N (званий в FameInfo нет)
            for k, v in fix:
                # ★ ревизия 38 К-4: ровно одна строка на звание — иначе откат всей транзакции (без commit GameWriter откатывает)
                n_ = w.execute("UPDATE dbo.AsdaFamePoints SET Point = ? WHERE FameIdx = ? AND Point = ?", (v, k, cur[k]))
                if n_ != 1:
                    raise RuntimeError("звание %d: UPDATE затронул %s строк вместо 1 — ничего не записано" % (k, n_))
            w.commit()
    except Exception as ex:
        return ["Joy1.dbo.AsdaFamePoints не приведена к FameInfo.txt (%s) — повторите changeset server-sync %s" % (str(ex)[:160], cs.get("id"))]
    out = ["Joy1.dbo.AsdaFamePoints приведена к FameInfo.txt: строк изменено %d" % len(fix)]
    if miss:
        out.append("в Joy1.dbo.AsdaFamePoints нет званий %s — пересоберите её (ac0w_01_migrate.sql)" % ", ".join(map(str, miss[:10])))
    if extra:
        out.append("в Joy1.dbo.AsdaFamePoints лишние строки %s (званий в FameInfo.txt нет) — пересоберите её (ac0w_01_migrate.sql)"
                   % ", ".join(map(str, extra[:10])))
    return out


# =====================================================================================================================
# Клиент: снимок для службы
# =====================================================================================================================
CLI_COLS = ("Enabled", "Point") + tuple("OptionTypeId%d" % m for m in range(6)) + tuple("IsPercent%d" % m for m in range(6))


def snapshot(snap):
    p = E.CLIENT_FILES.get("title_list")
    snap["titles"] = ({r["Id"]: [int(r["_row"])] + [E._int(r.get(c)) for c in CLI_COLS] for r in E._read_csv(p)}
                      if p and os.path.isfile(p) else {})


def parse(cli, d):
    cli.titles = {int(k): v for k, v in (d.get("titles") or {}).items()}


# =====================================================================================================================
# Справка редактору (только чтение) и расхождения
# =====================================================================================================================
def _ref():
    rels = [E.rel_of(g, FAME) for g in E.GS]
    sn = E.Snap(E.live_md5(rels))
    return sn, E.SrvState(sn)


def _dec(vals):
    return {"enabled": vals[1], "target": vals[3], "param": vals[4], "mode2": vals[43], "thr2": vals[44], "points": vals[42],
            "accum": vals[45], "prereq": [x for x in vals[5:10] if x >= 0], "next": [x for x in vals[10:12] if x >= 0],
            "bonus": [{"code": vals[12 + 5 * m], "min": vals[13 + 5 * m], "max": vals[14 + 5 * m], "v2": [vals[15 + 5 * m], vals[16 + 5 * m]]}
                      for m in range(6)]}


def search(q, limit=600):
    from domains import titles as TT
    q = (q or "").strip().lower()
    sn, st = _ref()
    t = st.get(E.GS[0], FAME)
    n = E._int(t.lines[0].decode("latin-1"))
    rows = []
    names = TT.names()
    for k in range(n):
        r = names.get(k) or ["", ""]
        if q and not (q == str(k) or q in (r[0] or "").lower() or q in (r[1] or "").lower()):
            continue
        try:
            v = rec_values(record(t, k, "GameServer")[1])
        except OpRefused:
            continue
        rows.append({"id": k, "name": TT.title_name(k), "enabled": v[1], "points": v[42], "target": v[3], "accum": v[45]})
        if len(rows) >= limit:
            break
    return {"rows": rows, "total": n}


def lookup_title(tid):
    from domains import titles as TT
    tid = int(tid)
    sn, st = _ref()
    srv = {}
    for g in E.GS:
        try:
            srv[g] = _dec(rec_values(record(st.get(g, FAME), tid, g)[1]))
        except OpRefused as ex:
            srv[g] = {"error": str(ex)}
    gs = srv.get(E.GS[0]) or {}
    if "error" in gs:
        raise OpRefused(gs["error"])
    vals = rec_values(record(st.get(E.GS[0], FAME), tid, E.GS[0])[1])
    cli = E.Client.load()
    cr = (getattr(cli, "titles", None) or {}).get(tid)
    client = None if cr is None else dict(zip(CLI_COLS, cr[1:]))
    rd = reads(tid, vals)
    h = holders([tid])
    pts = None
    try:
        from core import db
        with db.GameReader("joy1") as j:
            r = j.rows("SELECT Point FROM dbo.AsdaFamePoints WHERE FameIdx = ?", (tid,))
            pts = int(r[0]["Point"]) if r else None
    except Exception:
        pts = None
    fields = [[k, COND[k][1], rng_cond(k)[0], rng_cond(k)[1], rd.get(k), _unsafe(tid, vals, k)] for k in COND]
    p88 = None
    if tid in _p88_ids():                              # ★ ревизия 38 М-1: цель звания P88 — из patches.ini
        pst = p88_goals()
        p88 = None if pst is None else {g: {"on": v["on"], "thr": v["thr"][tid]} for g, v in pst.items()}
        why = UNSAFE["p88_unread"] if pst is None else (UNSAFE["p88_on"] if any(v["on"] for v in pst.values()) else None)
        if why:
            for f in fields:
                if f[0] == "target":
                    f[5] = why
    sets = set_sources(st.get(E.GS[0], FAME), tid, E.GS[0])       # ★ ревизия 38 М-2: записи, у которых звание — «следующее»
    return {"id": tid, "name": TT.title_name(tid), "server": srv, "client": client, "client_source": cli.source,
            "p88": p88, "p88_error": p88_goals.last_error if tid in _p88_ids() else None, "set_sources": sets,
            "reads": rd, "fields": fields, "rating": tid in RATING, "stats": [[c, n] for c, n in sorted(STAT_CODES.items())],
            "holders": None if h is None else [{"uid": u, "idx": c, "name": nm, "lvl": lv, "worn": w} for u, c, nm, lv, w in h[tid]],
            "holders_error": holders.last_error, "fame_points_db": pts,
            "copies_same": len({sn.md5[E.rel_of(g, FAME)] for g in E.GS}) == 1}


def lookup(what, ident):
    if what == "titles":
        return search(ident)
    try:
        return lookup_title(int(str(ident).strip()))
    except ValueError:
        raise OpRefused("номер звания — целое число")


def fame_points_db():
    """{FameIdx: Point} из Joy1.dbo.AsdaFamePoints или None (причина — fame_points_db.last_error); только чтение."""
    fame_points_db.last_error = None
    try:
        from core import db
        with db.GameReader("joy1") as j:
            return {int(r["i"]): int(r["p"]) for r in j.rows("SELECT FameIdx AS i, Point AS p FROM dbo.AsdaFamePoints")}
    except Exception as ex:
        fame_points_db.last_error = str(ex)[:200]
        return None


fame_points_db.last_error = None


def _div_joy1(t, n):
    """★ ревизия 38 М-2 / К-4: строки раздела по Joy1 — выключенное звание с держателями, выключенное звание, которое выдаёт набор,
    AsdaFamePoints ≠ FameInfo кол. 42 (несделанный server-sync виден на вкладке и в --live)."""
    rows, vals = [], {}
    for k in range(n):
        try:
            vals[k] = rec_values(record(t, k, "GameServer")[1])
        except OpRefused:
            pass
    off = sorted(k for k, v in vals.items() if not v[1])
    for k in off:
        src = [r for r, v in sorted(vals.items()) if k in (v[10], v[11])]
        if src:
            rows.append({"id": k, "field": "включено", "server": 0, "why": "выключено, но его выдаёт набор (кол. 10/11 записей %s)"
                         % ", ".join(map(str, src))})
    h = holders(off) if off else {}
    if h is None:
        rows.append({"id": "—", "why": "держатели выключенных званий не прочитаны (%s)" % (holders.last_error or NO_JOY1)})
    else:
        for k in off:
            if h.get(k):
                rows.append({"id": k, "field": "включено", "server": 0, "why": "выключено, но есть держатели: %d перс. (%s)"
                             % (len(h[k]), _who_err(h[k]))})
    db_pts = fame_points_db()
    if db_pts is None:
        rows.append({"id": "—", "why": "Joy1.dbo.AsdaFamePoints не прочитана (%s)" % (fame_points_db.last_error or NO_JOY1)})
        return rows
    for k, v in sorted(vals.items()):
        if k not in db_pts:
            rows.append({"id": k, "field": "AsdaFamePoints", "server": v[42], "why": "в Joy1.dbo.AsdaFamePoints нет строки звания"})
        elif db_pts[k] != v[42]:
            rows.append({"id": k, "field": "AsdaFamePoints", "client": db_pts[k], "server": v[42],
                         "why": "Joy1.dbo.AsdaFamePoints ≠ FameInfo кол. 42 (снятие UPCharFameBitDis вычтет не те очки) — changeset server-sync"})
    for k in sorted(set(db_pts) - set(range(n))):
        rows.append({"id": k, "field": "AsdaFamePoints", "why": "лишняя строка Joy1.dbo.AsdaFamePoints (звания в FameInfo.txt нет)"})
    return rows


def divergence(ev, cli, sec):
    rows = []
    t = ev.st.get(E.GS[0], FAME)
    n = E._int(t.lines[0].decode("latin-1"))
    ct = getattr(cli, "titles", None) or {}
    for k in range(n):
        try:
            v = rec_values(record(t, k, "GameServer")[1])
        except OpRefused as ex:
            rows.append({"id": k, "why": str(ex)})
            continue
        c = ct.get(k)
        if c is None:
            rows.append({"id": k, "why": "звания нет у клиента"})
            continue
        if bool(c[1]) != bool(v[1]):
            rows.append({"id": k, "field": "включено", "client": c[1], "server": v[1], "why": "включённость клиент ≠ сервер"})
        if c[2] != v[42]:
            rows.append({"id": k, "field": "очки", "client": c[2], "server": v[42], "why": "очки славы клиент ≠ сервер"})
        for m in range(6):
            want = v[12 + 5 * m] if v[12 + 5 * m] in STAT_CODES else 0
            if c[3 + m] != want:
                rows.append({"id": k, "field": "бонус %d" % m, "client": c[3 + m], "server": v[12 + 5 * m], "why": "бонус клиент ≠ сервер"})
    for k in sorted(set(ct) - set(range(n))):
        rows.append({"id": k, "why": "звания нет на сервере"})
    rows += _div_joy1(t, n)
    for g in E.GS[1:]:
        if ev.snap.md5.get(E.rel_of(g, FAME)) != ev.snap.md5.get(E.rel_of(E.GS[0], FAME)):
            rows.append({"id": "—", "why": "%s: FameInfo.txt ≠ GameServer (своя база копии)" % g})
    sec("titles", "звания: FameInfo сервер ≠ title_list клиент", rows)
