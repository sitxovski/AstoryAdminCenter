# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/questtables.py — область «Задания» (волна А4.5, 20.11.2026; разбор Reports/admin_center/research_a4_data.md §1.3, §3,
§5; формат и логика сервера — research_quests_episodes.md §3.6, Docs/Port/systems/BOARD_QUEST_FLOW.md §4.2–§6).

Только правка СУЩЕСТВУЮЩИХ записей (решение владельца 19.11): заданий, записей и строк не добавляется, вставок нет.

1) quest.reward — награда задания: запись N RepayTable.txt (GS ItemTable_Info, загрузчик GameServer.c:68880 — число N, затем N записей
   ПОТОКОМ слов, 35 токенов, запись 126 б; применяет sub_45DEE0 по ПОЗИЦИИ: dword_5F5E74 + 126·(N − 1), GameServer.c:38438…).
   Правятся: золото (ток.3, +8), опыт (ток.4, +12 i64), предметы в сумку A1/A2 (ток.15/16, ток.17/18: +56/+60, +64/+68) и B1 (ток.27/28:
   +98/+102). Не правятся (меняют ход задания или не имеют пары у клиента): штраф опыта, флаги блоков, харизма, книга, профессия, слава,
   очки навыков, предметы-цели в слот (+40…+52) и «снять предмет-цель» (+122) — это прогресс задания; предметы A3/B2/B3 — у клиента
   для них нет поля.
   ПАРА С КЛИЕНТОМ: окно наград клиента читает свою таблицу Data/NPC/RewardTable.BIN (questLoadRewardTableBin@0xC66190, 669 × 48 б),
   запись N клиента = запись N сервера (JOB4_QUEST_REMAP.md: «номер строки = seq в клиентском RewardTable»; второй метод — сверка всех
   669 записей dev 20.11: золото = Money 669/669, опыт = Exp 659/669, предмет A1 = ItemCode1 644/669, A2 = ItemCode2 668/669, B1 =
   Choice +40/+44 663/669). Клиентская половина: RewardTable.BIN рабочей сборки _MINE (источник импортёра
   asda_import_quest_reward_table.py) + QuestRewardTable.json + DT_QuestRewardTable точечно (asda_dt_json_point). У Indun своя база
   (636 записей против 669) — правка по базе каждой копии; записи нет — отказ (решение владельца 19.11, разбор §6 п.2).
   ВЫДАЧА ПРЕДМЕТА (sub_45DEE0, GameServer.c:38665…38900): Function_Table — количество × вес, сумка 1; Cellob — ОДИН самоцвет, количество
   не читается; item_table — стопка ТОЛЬКО по +35 (ток.23 ≠ 0: сумка 2, складывает sub_4D6CE0), иначе ОДНА вещь, количество не читается.
   Поэтому: нестопочный или самоцвет с количеством > 1 — отказ (клиент покажет N, сервер даст 1), «полустопка» (ток.23 ≠ 0 без ток.3 = 4,
   ток.24 = 1 — ревизия 36 Б-2) — отказ, контейнер (тип 10) — отказ, золото и книги заданий — отказ, нового кода на сервере нет — отказ.
   Эти правила ПЕРЕПРОВЕРЯЮТСЯ перед выкладкой и откатом сервера (apply_guard; урок ревизии 36 Б-1): item_table мог смениться другим набором.
2) board.quest — задание доски объявлений: запись k LimitationQuest.txt (20000 + k; загрузчик GS sub_4BD710 — номера подряд, иначе «Sync
   Error»; 32 токена: id, тип, max, имя, зона, lvMin, lvMax, режим, 5 + 5 целей, 4 + 4 на выбор, опыт, золото, 2 + 2 предмета). Правятся
   lvMin / lvMax (проверка взятия 6591), max (лимит раз), опыт, золото (награда 6593). Не правятся: тип периода (суточный сброс), режим и цели
   (ход задания), награды-предметы. 12 копий одинаковы (b19a88ed): GS NpcData_Info (читает GS) и ItemTable_Info, NpcServer Quest (читает
   NpcServer) и NpcInfo — панель держит их одинаковыми (политика same).
   ПАРА С КЛИЕНТОМ: доска клиента показывает «Ур. lvMin/lvMax», фильтрует и красит по ним, показывает опыт и золото из DT_RaidQuestData
   (asda_import_board_quests.py). Его источник — Raid_quest_data.BIN ЭТАЛОНА Interlude (решение владельца 28.10) — эталон не пишется;
   правка ложится ведомостью чисел Tools/data/board_quest_values.json (импортёр накладывает её в apply_overrides, «was» ≠ — останов
   импорта) + RaidQuestData.json + DT_RaidQuestData точечно.
ВЗЯТЫЕ ИГРОКАМИ (Joy1 dbo.CharEpisode — слоты журнала, dbo.CRT_LimitationQuest — доска; только чтение): правки этой области ход задания
не меняют (шаги, условия, цели не правятся; награда и уровни доски проверяются сервером только при сдаче / взятии) — поэтому предупреждение
со списком, а не отказ. Условия ConditionTable (уровень и т. п.) — НЕ в А4.5: у клиента три копии уровня (SNQICT.Bin, шаги .NSR в Nsr.bsz,
QCT.BIN), нужен отдельный разбор (вторая очередь).
Побочных эффектов при импорте нет.
"""
import contextlib
import io
import json
import os
import struct
import tempfile

from core.ops import OpRefused
from domains import questdata as QD, shopdata as E

AREA, TITLE = "quests", "Задания"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
REPAY = "RepayTable.txt"
LQ_GS, LQ_GS2, LQ_NPC, LQ_NPC2 = "NpcData_Info\\LimitationQuest.txt", "ItemTable_Info\\LimitationQuest.txt", "Quest\\LimitationQuest.txt", \
    "NpcInfo\\LimitationQuest.txt"
SRV_FILES = [("GS", "ItemTable_Info\\" + REPAY, "per_copy"), ("GS", LQ_GS, "same"), ("GS", LQ_GS2, "same"), ("NPC", LQ_NPC, "same"),
             ("NPC", LQ_NPC2, "same")]
QNT, QNTX, COND, QBOOK = "Quest\\QuestNpcTable.Bin", "Quest\\QuestNpcTableExt.Bin", "Quest\\ConditionTable.Bin", "QuestBook_Table.txt"
REPAY_TOK = 35
LQ_TOK, LQ_BASE, LQ_MAX = 32, 20000, 200
LVL_TOP = 150                              # уровень в данных — не выше 150 (как у ConditionTable, questdata.check)
VAL_MAX = 2000000000                       # золото / опыт: клиент держит i32
CNT_MAX = 32767                            # количество предмета: сервер берёт (__int16) (GameServer.c:38786)
DT_QREWARD = "/Game/AsdaAssets/Data/NPC/DT_QuestRewardTable"
DT_BOARD = "/Game/AsdaAssets/Data/Quest/DT_RaidQuestData"
QR_HDR, QR_REC = 0x14, 0x30
NO_JOY1 = "нет связи с Joy1"               # ★ ревизия 37 К-4: запасная причина «не прочитано» — отдельная строка перевода


def _data(name):
    try:
        return os.path.join(E.data_dir(), name)
    except ImportError:                    # служба на сервере: исходников порта нет — работает по снимку
        return os.path.join(E.UPROJ, "_no_asda_paths", name)


CLIENT_FILES = {"qreward_bin": _data(os.path.join("NPC", "RewardTable.BIN")),
                "qreward_json": os.path.join(E.UPROJ, "RawAssets", "Data", "NPC", "QuestRewardTable.json"),
                "board_json": os.path.join(E.UPROJ, "RawAssets", "Data", "Quest", "RaidQuestData.json"),
                "board_values": os.path.join(E.UE_TOOLS, "data", "board_quest_values.json")}
DT, IMPORTERS, CSV_KEYS = {}, {}, ()
KINDS = {
    "quest.reward": ("Задание: награда (RepayTable + RewardTable клиента)", ("rid", "fields"), False),
    "board.quest": ("Доска объявлений: уровни, лимит, опыт, золото (LimitationQuest + клиент)", ("quest", "fields"), False),
}
# поле позиции → (номер токена RepayTable после номера записи, поле клиента RewardTable, подпись)
REWARD = {"gold": (2, "Money", "золото"), "exp": (3, "Exp", "опыт"),
          "item1": (15, "ItemCode1", "предмет A1"), "item1n": (16, "ItemCount1", "предмет A1, количество"),
          "item2": (17, "ItemCode2", "предмет A2"), "item2n": (18, "ItemCount2", "предмет A2, количество"),
          "item4": (27, "ChoiceItemCode", "предмет B1 (на выбор у клиента)"), "item4n": (28, "ChoiceItemCount", "предмет B1, количество")}
SLOTS = (("item1", "item1n", "a"), ("item2", "item2n", "a"), ("item4", "item4n", "b"))
# ★ ревизия 37: все 6 слотов предметов записи RepayTable — (имя, токен кода, токен количества, токен флага блока); номера токенов — строки
#   с номером записи (загрузчик GameServer.c:68880…: +56/+60 A1, +64/+68 A2, +72/+76 A3, +98/+102 B1, +106/+110 B2, +114/+118 B3;
#   флаги блоков +20 / +80). Выдаёт все шесть подряд один цикл sub_45DEE0 (:38665, i < 6); у клиента поля есть только у A1, A2, B1.
ALL_SLOTS = (("A1", 16, 17, 5), ("A2", 18, 19, 5), ("A3", 20, 21, 5), ("B1", 28, 29, 22), ("B2", 30, 31, 22), ("B3", 32, 33, 22))
# ★ ревизия 37 М-1: предметы записи доски — (смещение, первый токен кода, первый токен количества, штук) по загрузчику sub_4BD710
#   (:75633…): цели +142/+162 (RecvUser_LimitationQuestResult :120309…: у нестопочного цель засчитывается только при количестве 1),
#   награда на выбор +172/+188 и предметы +196/+204 (выдача sub_5340B0: у нестопочного количество не пишется — одна вещь)
BOARD_ITEMS = (("+142", 8, 13, 5), ("+172", 18, 22, 4), ("+196", 28, 30, 2))
I16_MAX = 32767
QR_COLS = ("RecordIndex", "QuestId", "Stage", "Money", "Exp", "ItemCode1", "ItemCount1", "ItemCode2", "ItemCount2", "ChoiceFlag",
           "ChoiceItemCode", "ChoiceItemCount")
# поле позиции доски → (токен LimitationQuest, поле клиента RaidQuestData, подпись)
BOARD = {"lvmin": (5, "LevelMin", "мин. уровень"), "lvmax": (6, "LevelMax", "макс. уровень"), "max": (2, "MaxCount", "лимит раз"),
         "exp": (26, "Exp", "опыт"), "gold": (27, "Gold", "золото")}
BOARD_COLS = ("LevelMin", "LevelMax", "MaxCount", "Exp", "Gold", "PeriodType", "Mode", "Zone")


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def _fields(p, allowed, lo_hi):
    f = p.get("fields")
    if isinstance(f, str):
        try:
            f = json.loads(f)
        except ValueError:
            f = None
    if not isinstance(f, dict):
        raise OpRefused("поле «fields»: {поле: число, …} — хотя бы одно поле (%s)" % ", ".join(allowed))
    bad = sorted(k for k in f if k not in allowed)
    if bad:
        raise OpRefused("поле «fields»: неизвестные поля %s (можно: %s)" % (", ".join(bad), ", ".join(allowed)))
    out = {}
    for k in allowed:
        if k in f and str(f[k]).strip() != "":
            lo, hi = lo_hi(k)
            out[k] = E._ival(f, k, lo, hi)
    if not out:
        raise OpRefused("поле «fields»: {поле: число, …} — хотя бы одно поле (%s)" % ", ".join(allowed))
    return out


def rng_reward(k):
    """Пределы поля награды (★ ревизия 37 К-5: те же отдаёт справка — поля формы веба)."""
    return (-1, VAL_MAX) if k in ("item1", "item2", "item4") else ((0, CNT_MAX) if k.endswith("n") else (0, VAL_MAX))


def rng_board(k):
    """Пределы поля задания доски (★ ревизия 37 К-5: те же отдаёт справка)."""
    return (1, LVL_TOP) if k.startswith("lv") else ((0, 32767) if k == "max" else (0, VAL_MAX))


def norm(kind, p):
    if kind == "quest.reward":
        return {"rid": E._ival(p, "rid", 1, 32767), "fields": _fields(p, tuple(REWARD), rng_reward)}
    return {"quest": E._ival(p, "quest", LQ_BASE, LQ_BASE + LQ_MAX - 1), "fields": _fields(p, tuple(BOARD), rng_board)}


def target_key(kind, p):
    return "repay:%d" % p["rid"] if kind == "quest.reward" else "board:%d" % p["quest"]


def _toks(line):
    return line.split(b"\t")


def _tok_int(f, i):
    return E._int(f[i].decode("latin-1"))


def _qname(q):
    from domains import refdata
    return "%d «%s»" % (q, refdata.quest(q))


# ---- книги заданий (их держит CharEpisode — предметом в сумку не выдаются, research_item_give) ----
def quest_books(ev):
    rel = E.rel_of(E.GS[0], QBOOK)
    ev.snap.extend([rel])
    try:
        raw = ev.snap.raw(rel)
    except OpRefused:
        return set()
    return {E._int(t[0]) for t in (ln.split() for ln in raw.decode("latin-1").splitlines()[1:]) if t}


def item_rule(code, count, it_fields, exists, books, where):
    """Проверки предмета награды по таблицам сервера (sub_45DEE0) → None или причина отказа. it_fields(code) — токены item_table,
    exists(code) — есть ли код на сервере (item_table / Function_Table / Cellob_Table)."""
    return item_static(code, count, it_fields, exists, books, where) or item_stack(code, count, it_fields, where)


def item_static(code, count, it_fields, exists, books, where):
    """Часть item_rule, которую позиции набора не меняют (золото, книга, есть ли код, самоцвет, контейнер — тип ток.16 «Предметы» не
    правят): проверяется сразу у позиции."""
    if code <= 0:
        return None
    if code == E.ITEM_FIRST:
        return "награда — %s: золото (20551) — у награды своё поле золота, предметом его не выдают" % where
    if code in books:
        return "награда — %s: %d — книга задания (QuestBook_Table): книги живут в журнале (CharEpisode), предметом в сумку их не выдают" % (where, code)
    if not exists(code):
        return "награда — %s: предмета %d нет на сервере (item_table / Function_Table / Cellob_Table)" % (where, code)
    if E.srvtables.CELLOB_BASE <= code < E.ITEM_FIRST:
        if count > 1:
            return ("награда — %s: самоцвет %d, количество %d — сервер выдаёт ОДИН самоцвет и количество не читает (sub_45DEE0, ветка Cellob), клиент "
                    "показал бы %d" % (where, code, count, count))
        return None
    if code < E.srvtables.CELLOB_BASE:
        return None                                    # Function_Table: количество × вес, сумка 1 (ветка sub_532B10)
    f = it_fields(code)
    if not f:
        return "награда — %s: предмета %d нет в item_table" % (where, code)
    if E._int(f[16]) == 10:
        return "награда — %s: %d — контейнер (тип 10): Amount у него — содержимое, а не штуки, выдача наградой не подтверждена" % (where, code)
    return None


def item_stack(code, count, it_fields, where):
    """★ ревизия 37 Б-1: часть item_rule, зависящая от стопки item_table (ток.23 правит «Предметы» в том же наборе) — проверяется по
    ИТОГОВОМУ состоянию набора (after_run) и перед выкладкой / откатом (apply_guard), а не по состоянию на момент позиции."""
    if code < E.ITEM_FIRST:
        return None
    f = it_fields(code)
    if not f:
        return None                                    # «нет в item_table» — item_static
    t23 = E._int(f[23])
    full = f[3] == "4" and f[23] == "1" and f[24] == "1"
    if t23 and not full:
        return ("награда — %s: %d — «полустопка» (ток.23 = %s, ток.3 = %s, ток.24 = %s): награда складывает по одному ток.23 (sub_4D6CE0), а прочие "
                "пути сервера считают стопкой только ток.3 = 4 и ток.24 = 1 — количество разошлось бы, смысл не подтверждён"
                % (where, code, f[23], f[3], f[24]))
    if not t23 and count > 1:
        return ("награда — %s: %d не стопочный, количество %d — сервер выдаёт ОДНУ вещь и количество не читает (sub_45DEE0), клиент показал бы %d"
                % (where, code, count, count))
    return None


def _repay_rows(ev, rid, rep):
    """Запись rid во всех GS: [(копия, таблица, номер строки, токены)]; отказ — до первой записи."""
    out = []
    for g in E.GS:
        t = ev.st.get(g, REPAY)
        n = E._int(t.lines[0].decode("latin-1"))
        i = E.record_line(t, rid - 1, REPAY_TOK)       # сервер читает ПОТОКОМ по порядку (ревизия 33 К-4)
        if i is None:
            raise OpRefused("таблица %s %s: слова не ложатся построчно по %d на запись — порядок записей сервера не доказан, правка не делается"
                            % (REPAY, g, REPAY_TOK))
        if i < 0 and g == E.GS[0]:
            raise OpRefused("записи %d в %s нет (записей %d) — в А4 только правка существующих" % (rid, REPAY, n))
        if i < 0:
            raise OpRefused("записи %d в %s %s нет (записей %d) — у копии своя база, в А4 только правка существующих" % (rid, REPAY, g, n))
        f = _toks(t.lines[i])
        if len(f) < REPAY_TOK:
            raise OpRefused("запись %d %s %s — меньше %d полей" % (rid, REPAY, g, REPAY_TOK))
        _tab_is_word(f, "%s %s #%d" % (g, REPAY, rid))
        if _tok_int(f, 0) != rid:
            # ★ ревизия 37 К-4: текст начинается со слова (шаблон «%s: …» перехватил бы вложенный перевод) и есть в _A4_QUESTS
            rep["warnings"].append("копия %s: у записи %d номер %s — сервер берёт ПОРЯДОК записи" % (g, rid, f[0].decode("latin-1").strip()))
        out.append((g, t, i, f))
    return out


def _tab_is_word(f, where):
    """★ ревизия 37 К-3: поле TAB = ровно одно слово. record_line считает слова по пробелам (как fscanf «%s» сервера), а правка
    идёт по полям TAB — поле из двух слов или пустое сдвинуло бы set_token на чужой токен."""
    bad = [j for j, x in enumerate(f) if len(x.split()) != 1]
    if bad:
        raise OpRefused("поля TAB не совпадают со словами сервера (%s, поле %d — не одно слово), правка не делается" % (where, bad[0]))


def _val(f, k):
    return _tok_int(f, REWARD[k][0] + 1)


def k_quest_reward(ev, p, rep):
    rid, new = p["rid"], dict(p["fields"])
    for code_k, n_k, _blk in SLOTS:                     # пустой слот — как в данных оригинала: код −1, количество 0
        if code_k in new and new[code_k] <= 0:
            new[code_k] = -1
            new[n_k] = 0
    rows = _repay_rows(ev, rid, rep)
    g0, _t0, _i0, f0 = rows[0]
    old = {k: _val(f0, k) for k in REWARD}
    for g, _t, _i, f in rows[1:]:                       # отличия копии (Indun) не затираются — сверка правимых полей ДО записи
        dif = [k for k in new if _val(f, k) != old[k]]
        if dif:
            raise OpRefused("копия %s: запись %d отличается от GameServer (%s) — отличия копии не затираются, правка не однозначна"
                            % (g, rid, ", ".join("%s %d ≠ %d" % (k, _val(f, k), old[k]) for k in dif)))
    a_flag, b_flag = _tok_int(f0, 5), _tok_int(f0, 22)
    want = dict(old, **new)
    books = quest_books(ev)
    slots = []
    for code_k, n_k, blk in SLOTS:
        if code_k not in new and n_k not in new:
            continue
        code, cnt = want[code_k], want[n_k]
        lbl = REWARD[code_k][2]
        if code > 0 and cnt < 1:
            raise OpRefused("награда — %s: предмет %d с количеством %d — нужно от 1 (без предмета — код −1)" % (lbl, code, cnt))
        if code <= 0 and cnt > 0:
            raise OpRefused("награда — %s: количество %d без предмета — укажите код или уберите количество" % (lbl, cnt))
        if code > 0 and not (a_flag if blk == "a" else b_flag):
            raise OpRefused("награда — %s: блок %s записи %d выключен (+%d = 0) — сервер этот предмет не выдаст (sub_45DEE0), правка не подействует"
                            % (lbl, blk.upper(), rid, 20 if blk == "a" else 80))
        # ★ ревизия 37 Б-1: здесь — только то, что позиции набора не меняют; стопка (ток.23 правят «Предметы» в том же наборе, до или после
        #   этой позиции) — по ИТОГОВОМУ состоянию набора в after_run
        why = item_static(code, cnt, ev.it_fields, ev.exists, books, lbl)
        if why:
            raise OpRefused(why)
        slots.append((code_k, code, cnt))
        if code > 0 and code != old[code_k]:
            from domains.cs_kinds import monsters as M          # предупреждения «дюп и экономика» (премиум, коробка пакета) — общие с А4.3
            M._item(ev, code, rep, lbl, 1)                       # количество × стопка — отказом item_stack по итогу набора
    cli = (ev.cli.qreward or {}).get(rid)
    if cli is None:
        raise OpRefused("у клиента нет записи %d RewardTable (окно наград) — пара не собирается, в А4 только правка существующих" % rid)
    cf = dict(zip(QR_COLS, cli))
    cdiff = [k for k in new if cf[REWARD[k][1]] != old[k]]
    if cdiff:
        rep["warnings"].append("уже расходились (клиент ≠ сервер): %s — правка ставит обоим новое значение" % "; ".join(
            "%s: клиент %d, сервер %d" % (REWARD[k][2], cf[REWARD[k][1]], old[k]) for k in cdiff))
    if all(new[k] == old[k] and cf[REWARD[k][1]] == new[k] for k in new):
        raise OpRefused("у награды %d уже такие значения — менять нечего" % rid)
    if any(k.startswith("item4") for k in new) and not cf["ChoiceFlag"]:
        rep["warnings"].append("у клиентской записи %d флаг «на выбор» (+36) = 0 — окно наград предмет B1 не покажет, сервер выдаст" % rid)
    if b_flag and any(k.startswith(("item1", "item2")) for k in new):
        rep["warnings"].append("у записи %d включён и блок B: сервер выдаёт предметы A и B вместе, клиент показывает B как «на выбор»" % rid)
    for g, t, i, f in rows:
        f = list(f)
        for k, v in new.items():
            f[REWARD[k][0] + 1] = E.set_token(f[REWARD[k][0] + 1], v)
        t.set_line(i, b"\t".join(f))
    ch = {k: v for k, v in new.items() if v != old[k] or cf[REWARD[k][1]] != v}
    rep["text"] = "награда %d: %s (сервер RepayTable ×%d GS, клиент RewardTable + DT_QuestRewardTable)" % (
        rid, "; ".join("%s: %d → %d" % (REWARD[k][2], old[k], v) for k, v in sorted(ch.items())), len(E.GS))
    rep["lines"] = ["было: %s" % _reward_text(old), "станет: %s" % _reward_text(dict(old, **new))]
    if "exp" in ch and _tok_int(f0, 1):
        rep["lines"].append("опыт со штрафом за уровень (база %d): сервер снижает его выше базового уровня (−10 %% за 5 уровней, до ×0.5), "
                            "клиент показывает без штрафа" % _tok_int(f0, 2))
    bal = rep.setdefault("_balance", [])
    for k in ("gold", "exp"):
        if k in ch and new[k] != old[k]:
            bal.append({"what": "награда %d: %s" % (rid, REWARD[k][2]), "old": old[k], "new": new[k], "codes": []})
    guard = []
    for code_k, n_k, _blk in SLOTS:
        oc, on, nc, nn = old[code_k], old[n_k], want[code_k], want[n_k]
        if (oc, on) == (nc, nn):
            continue
        if nc != oc:
            bal.append({"what": "награда %d: %s %d → %d" % (rid, REWARD[code_k][2], oc, nc), "old": oc, "new": nc,
                        "codes": [c for c in (oc, nc) if c > 0], "kind": "swap"})
        elif nn != on:
            bal.append({"what": "награда %d: %s, количество" % (rid, REWARD[code_k][2]), "old": on, "new": nn, "codes": [nc]})
        guard.append({"slot": code_k, "new": [nc, nn], "old": [oc, on]})
    # ★ урок ревизии 36 Б-1: правила выдачи предметов награды перепроверяются перед выкладкой (новые) и откатом (прежние) — apply_guard
    rep["guard"] = guard
    rep["_slots"], rep["_rid"] = slots, rid                       # ★ ревизия 37: проверка стопки и веса по итогу набора (after_run)
    _holders_quest(ev, rid, rep)
    # ★ ревизия 37 К-1: окно наград клиента ищет запись по (QuestId, Stage) (questBuildRewardSet@0xC663A0); запись, которую сервер
    #   даёт за задание, а клиент к нему не привязывает (533–536: QuestId −1), игрок в окне не увидит — правка клиентской половины невидима
    uses = {(q["quest"], q["step"]) for q in rep.get("quests") or []}
    if uses and cf["QuestId"] not in {q for q, _s in uses}:
        rep["warnings"].append("окно наград клиента запись %d к заданию не привязывает (QuestId %d, шаг %d), сервер даёт её за %s — клиентскую "
                               "половину игрок не увидит" % (rid, cf["QuestId"], cf["Stage"], ", ".join("%d/%d" % x for x in sorted(uses))))
    elif uses and (cf["QuestId"], cf["Stage"]) not in uses:
        rep["warnings"].append("окно наград клиента привязывает запись %d к шагу %d задания %d, а сервер даёт её на шаге %s — окно может "
                               "показать её не на том шаге" % (rid, cf["Stage"], cf["QuestId"], ", ".join(
                                   str(s) for q, s in sorted(uses) if q == cf["QuestId"])))
    ent = {"type": "qreward_set", "file": "qreward_bin", "rid": rid,
           "fields": {REWARD[k][1]: [cf[REWARD[k][1]], v] for k, v in sorted(ch.items())}}
    rep["client"] = [ent]
    ev.client += rep["client"]


def _reward_text(v):
    items = ", ".join("%s × %d" % (E.nm(v[c]), v[n]) for c, n, _b in SLOTS if v[c] > 0) or "—"
    return "золото %d, опыт %d, предметы: %s" % (v["gold"], v["exp"], items)


# ---- кто сейчас держит задание (только чтение Joy1) ----
def _npc_bytes(ev):
    rels = [E.folders("NPC")[0] + "\\" + x for x in (QNT, QNTX, COND)]
    ev.snap.extend(rels)
    get = lambda r: ev.snap.raw(r) if ev.snap.md5.get(r) not in (None, "none") else b""
    return get(rels[0]), get(rels[1]), get(rels[2])


def users_of_reward(ev, rid):
    """Задания, у которых ячейка «ПРИНИМАЕТ» даёт награду rid (условие с +10 = 1 и номером rid среди 5 вариантов): [(задание, шаг,
    действие)]."""
    if "_qt_cells" not in ev.__dict__:
        b, x, c = _npc_bytes(ev)
        ev._qt_cells = (QD.parse_cells(b, x)[1], c)
    takes, cb = ev._qt_cells
    out = set()
    for q, lst in takes.items():
        for _npc, _cell, st, keys in lst:
            for key in keys:
                c = QD.cond_rec(cb, key) if key > 0 else None
                if c and c["reward_flag"] == 1 and rid in c["rewards"]:
                    out.add((q, st, c["action"]))
    return sorted(out)


def quest_holders(qs):
    """{задание: [(учётка, персонаж, имя, уровень, шаг)]} по Joy1.dbo.CharEpisode (только чтение) или None (причина — last_error)."""
    quest_holders.last_error = None
    qs = sorted({int(q) for q in qs})
    if not qs:
        return {}
    try:
        from core import db
        with db.GameReader("joy1") as j:
            rows = j.rows("SELECT e.Episodeidx AS q, e.Stepidx AS st, e.Userindex AS u, e.Charidx AS c, ch.Charname AS nm, ch.Lvl AS lv "
                          "FROM dbo.CharEpisode e LEFT JOIN dbo.Charinfo ch ON ch.Userindex = e.Userindex AND ch.Charidx = e.Charidx "
                          "WHERE e.Episodeidx IN (%s) ORDER BY e.Episodeidx, e.Userindex, e.Charidx" % ",".join(map(str, qs)))
        out = {q: [] for q in qs}
        for r in rows:
            out.setdefault(int(r["q"]), []).append((int(r["u"]), int(r["c"]), r["nm"] or "", int(r["lv"] or 0), int(r["st"] or 0)))
        return out
    except Exception as ex:
        quest_holders.last_error = str(ex)[:200]
        return None


quest_holders.last_error = None


def board_holders(ids, min_count=None):
    """{задание доски: [(учётка, персонаж, имя, уровень, флаг, счётчик)]} по Joy1.dbo.CRT_LimitationQuest (флаг ≠ 0) или None.
    ★ ревизия 37 М-3: min_count — ещё строки с флагом 0 и счётчиком ≥ min_count (новый лимит: RecvUser_LimitationQuestEnter закроет
    им задание кодом 5 до сброса периода)."""
    board_holders.last_error = None
    ids = sorted({int(q) for q in ids})
    if not ids:
        return {}
    try:
        from core import db
        cond = "l.Quest_Flag <> 0" if min_count is None else "(l.Quest_Flag <> 0 OR l.Quest_Count >= %d)" % int(min_count)
        with db.GameReader("joy1") as j:
            rows = j.rows("SELECT l.Quest_Index AS q, l.Quest_Flag AS fl, l.Quest_Count AS n, l.Userindex AS u, l.Charidx AS c, "
                          "ch.Charname AS nm, ch.Lvl AS lv FROM dbo.CRT_LimitationQuest l LEFT JOIN dbo.Charinfo ch ON "
                          "ch.Userindex = l.Userindex AND ch.Charidx = l.Charidx WHERE %s AND l.Quest_Index IN (%s) "
                          "ORDER BY l.Quest_Index, l.Userindex, l.Charidx" % (cond, ",".join(map(str, ids))))
        out = {q: [] for q in ids}
        for r in rows:
            out.setdefault(int(r["q"]), []).append((int(r["u"]), int(r["c"]), r["nm"] or "", int(r["lv"] or 0), int(r["fl"] or 0),
                                                    int(r["n"] or 0)))
        return out
    except Exception as ex:
        board_holders.last_error = str(ex)[:200]
        return None


board_holders.last_error = None


def _who(lst, tail):
    """Список персонажей через «; » (переводчик переводит каждую часть)."""
    parts = ["%s (%d/%d, ур. %d, %s)" % (nm or "?", u, c, lv, tail(x)) for x in lst[:10] for u, c, nm, lv in [x[:4]]]
    if len(lst) > 10:
        parts.append("и ещё %d" % (len(lst) - 10))
    return "; ".join(parts)


def _holders_quest(ev, rid, rep):
    uses = users_of_reward(ev, rid)
    rep["quests"] = [{"quest": q, "step": st, "action": a} for q, st, a in uses]
    if not uses:
        rep["warnings"].append("награду %d не даёт ни одна ячейка «ПРИНИМАЕТ» NPC (ссылок в ConditionTable нет) — правка игрокам не видна" % rid)
        return
    rep["lines"].append("даёт: %s" % "; ".join("%s, шаг %d (%s)" % (_qname(q), st, "завершить" if a == 2 else "шаг") for q, st, a in uses))
    h = quest_holders([q for q, _s, _a in uses])
    if h is None:
        rep["warnings"].append("кто держит задание сейчас — не прочитано (%s)" % (quest_holders.last_error or NO_JOY1))
        return
    for q in sorted(h):
        if h[q]:
            rep["warnings"].append("задание %s сейчас взято (%d перс.): %s — ход задания правка не меняет, при сдаче они получат новую "
                                   "награду" % (_qname(q), len(h[q]), _who(h[q], lambda x: "шаг %d" % x[4])))


# ---- доска ----
def board_copies():
    return [(g, s) for g in E.GS for s in (LQ_GS, LQ_GS2)] + [(n, s) for n in E.folders("NPC") for s in (LQ_NPC, LQ_NPC2)]


def k_board_quest(ev, p, rep):
    qid, new = p["quest"], p["fields"]
    k = qid - LQ_BASE
    rows, old = [], None
    for fold, sub in board_copies():                    # сначала проверка ВСЕХ копий — отказ до первой записи
        t = ev.st.get(fold, sub)
        n = E._int(t.lines[0].decode("latin-1"))
        i = E.record_line(t, k, LQ_TOK)
        if i is None:
            raise OpRefused("копия %s\\%s: слова не ложатся построчно по %d на запись — порядок записей сервера не доказан, правка не делается"
                            % (fold, sub, LQ_TOK))
        if i < 0:
            raise OpRefused("задания доски %d нет в %s\\%s (записей %d) — в А4 только правка существующих" % (qid, fold, sub, n))
        f = _toks(t.lines[i])
        if len(f) < LQ_TOK:                             # ★ ревизия 37 К-3: как у RepayTable — отказ, а не IndexError / чужой токен
            raise OpRefused("копия %s\\%s: запись %d — меньше %d полей" % (fold, sub, qid, LQ_TOK))
        _tab_is_word(f, "%s\\%s #%d" % (fold, sub, qid))
        if _tok_int(f, 0) != qid:
            raise OpRefused("копия %s\\%s: запись %d несёт номер %s, а сервер требует подряд с 20000 («Sync Error») — правка не делается"
                            % (fold, sub, k, f[0].decode("latin-1").strip()))
        cur = {x: _tok_int(f, BOARD[x][0]) for x in BOARD}
        if old is None:
            old, typ = cur, _tok_int(f, 1)
        elif cur != old:
            raise OpRefused("копия %s\\%s: задание %d другое, чем в GameServer\\%s — копии разошлись, правка не однозначна" % (fold, sub, qid, LQ_GS))
        rows.append((t, i, f))
    want = dict(old, **new)
    if want["lvmin"] > want["lvmax"]:
        raise OpRefused("мин. уровень %d больше макс. %d — задание не возьмёт никто (6591, код 3)" % (want["lvmin"], want["lvmax"]))
    try:
        top = E.srvtables.max_level()
    except Exception:
        top = None
    if top and want["lvmin"] > top:
        raise OpRefused("мин. уровень %d выше потолка уровня сервера %d — задание не возьмёт никто" % (want["lvmin"], top))
    if top and want["lvmax"] > top:
        rep["warnings"].append("макс. уровень %d выше потолка уровня сервера %d — ограничение сверху не действует" % (want["lvmax"], top))
    if "max" in new:
        if typ == 0:
            rep["warnings"].append("тип задания 0 (повтор без лимита): сервер лимит не проверяет (тип ≠ 0 и max ≤ счётчика — код 5)")
        elif want["max"] < 1:
            raise OpRefused("лимит %d при типе %d — задание после первой сдачи не возьмёт никто, правка не делается" % (want["max"], typ))
    cli = (ev.cli.board or {}).get(qid)
    if cli is None:
        raise OpRefused("у клиента нет задания доски %d (DT_RaidQuestData) — пара не собирается" % qid)
    cdiff = [x for x in new if cli.get(BOARD[x][1]) != old[x]]
    if cdiff:
        rep["warnings"].append("уже расходились (клиент ≠ сервер): %s — правка ставит обоим новое значение" % "; ".join(
            "%s: клиент %s, сервер %d" % (BOARD[x][2], cli.get(BOARD[x][1]), old[x]) for x in cdiff))
    if all(new[x] == old[x] and cli.get(BOARD[x][1]) == new[x] for x in new):
        raise OpRefused("у задания доски %d уже такие значения — менять нечего" % qid)
    for t, i, f in rows:
        f = list(f)
        for x, v in new.items():
            f[BOARD[x][0]] = E.set_token(f[BOARD[x][0]], v)
        t.set_line(i, b"\t".join(f))
    ch = {x: v for x, v in new.items() if v != old[x] or cli.get(BOARD[x][1]) != v}
    rep["text"] = "доска, задание %d: %s (сервер LimitationQuest ×%d копий, клиент DT_RaidQuestData + ведомость)" % (
        qid, "; ".join("%s: %d → %d" % (BOARD[x][2], old[x], v) for x, v in sorted(ch.items())), len(rows))
    bt = lambda v: "ур. %d…%d, лимит %d, опыт %d, золото %d" % (v["lvmin"], v["lvmax"], v["max"], v["exp"], v["gold"])
    rep["lines"] = ["было: %s (тип %d)" % (bt(old), typ), "станет: %s" % bt(want)]
    bal = rep.setdefault("_balance", [])
    for x, v in sorted(ch.items()):
        if v != old[x]:
            bal.append({"what": "доска %d: %s" % (qid, BOARD[x][2]), "old": old[x], "new": v, "codes": []})
    lim = want["max"] if "max" in ch and typ != 0 else None
    h = board_holders([qid], min_count=lim)
    if h is None:
        rep["warnings"].append("кто держит задание сейчас — не прочитано (%s)" % (board_holders.last_error or NO_JOY1))
    else:
        taken = [x for x in h.get(qid, []) if x[4] in (1, 2)]
        done = [x for x in h.get(qid, []) if x[4] == 3]
        if taken:
            rep["warnings"].append("задание доски %d сейчас взято (%d перс.): %s — уровни сервер проверяет только при взятии, награду — при "
                                   "сдаче (новую)" % (qid, len(taken), _who(taken, lambda x: "флаг %d" % x[4])))
        if done and "max" in ch:
            rep["warnings"].append("у %d перс. лимит задания %d исчерпан (флаг 3): в Joy1 флаг остаётся, новый лимит их не откроет до сброса"
                                   % (len(done), qid))
        # ★ ревизия 37 М-3: флаг 0 и счётчик ≥ нового лимита — RecvUser_LimitationQuestEnter (GameServer.c:119892…: тип ≠ 0 и
        #   max ≤ счётчика → код 5) сразу закроет им задание до сброса периода
        if lim is not None:
            shut = [x for x in h.get(qid, []) if x[4] == 0 and x[5] >= lim]
            if shut:
                rep["warnings"].append("у %d перс. сдано уже не меньше нового лимита %d (флаг 0): %s — сервер не даст им взять задание %d "
                                       "(код 5) до сброса периода" % (len(shut), lim, _who(shut, lambda x: "сдано %d" % x[5]), qid))
    rep["client"] = [{"type": "board_set", "file": "board_json", "quest": qid,
                      "fields": {BOARD[x][1]: [cli.get(BOARD[x][1]), v] for x, v in sorted(ch.items())}}]
    ev.client += rep["client"]


# =====================================================================================================================
# ★ ревизия 37: проверки по ИТОГОВОМУ состоянию набора (after_run) и перед выкладкой / откатом сервера (apply_guard, урок ревизии 36 Б-1)
# =====================================================================================================================
IT_TABLE = "item_table.txt"
STACK_MSG = ("смена стопки %s: награды и цели доски с этим предметом и количеством больше 1 (%s) стали бы выдавать или принимать ОДНУ вещь — "
             "у нестопочного сервер количество не читает (sub_45DEE0, sub_5340B0, RecvUser_LimitationQuestResult), окно наград показало бы "
             "количество")


def _wi(f, i):
    x = f[i]
    return E._int(x.decode("latin-1") if isinstance(x, bytes) else x)


def _records(t, ntok):
    """Записи таблицы так, как их читает сервер (fscanf «%s» подряд: число N, затем N записей по ntok слов) → [[слова]]."""
    w = b"\n".join(t.lines).split()
    n = E._int(w[0].decode("latin-1")) if w else 0
    return [w[1 + ntok * k:1 + ntok * (k + 1)] for k in range(n) if len(w) >= 1 + ntok * (k + 1)]


def _itf_of(t):
    idx = t.index()

    def itf(c):
        i = idx.get(int(c))
        return E._f(t.lines[i]) if i else None
    return itf


def _exists_of(itf, fn, cel):
    def ex(c):
        if c >= E.ITEM_FIRST:
            return itf(c) is not None
        return c in cel if c >= E.srvtables.CELLOB_BASE else c in fn
    return ex


def _books_of(raw):
    return {E._int(x[0]) for x in (ln.split() for ln in raw.decode("latin-1").splitlines()[1:]) if x}


def code_uses(repays, board, codes):
    """Где коды codes лежат в наградах: [(таблица, копия, запись, слот, код, количество, блок включён)] — все 6 слотов RepayTable
    каждой копии GS (номер записи = порядок, как у sub_45DEE0) и предметы доски (цели +142, на выбор +172, предметы +196)."""
    out = []
    for g, t in repays:
        for k, f in enumerate(_records(t, REPAY_TOK)):
            for nm, ci, ni, fl in ALL_SLOTS:
                c = _wi(f, ci)
                if c in codes:
                    out.append(("RepayTable", g, k + 1, nm, c, _wi(f, ni), _wi(f, fl) != 0))
    if board is not None:
        for f in _records(board, LQ_TOK):
            for off, c0, n0, cnt in BOARD_ITEMS:
                for j in range(cnt):
                    c = _wi(f, c0 + j)
                    if c in codes:
                        out.append(("LimitationQuest", "", _wi(f, 0), "%s.%d" % (off, j + 1), c, _wi(f, n0 + j), True))
    return out


def use_broken(u, itf, exists, books):
    """Место награды нарушает правила выдачи по состоянию item_table itf → причина | None. RepayTable — item_rule (sub_45DEE0);
    доска — нестопочный предмет item_table с количеством больше 1 (sub_5340B0 пишет одну вещь, цель засчитывается только при 1)."""
    tbl, _g, _r, slot, c, n, on = u
    if not on or c <= 0:
        return None
    if tbl == "RepayTable":
        return item_rule(c, n, itf, exists, books, slot)
    f = itf(c) if c >= E.ITEM_FIRST else None
    if f and n > 1 and not E._int(f[23]):
        return "не стопочный"
    return None


def _use_list(uses):
    """Места наград списком через запятую (без «; » — текст идёт в отказ): «RepayTable 12 A1 × 5 [GameServer/Ch2_GameServer]»."""
    groups = {}
    for tbl, g, r, slot, _c, n, _on in uses:
        groups.setdefault((tbl, r, slot, n), []).append(g)
    parts = ["%s %d %s × %d%s" % (tbl, r, slot, n, " [%s]" % "/".join(gs) if any(gs) else "") for (tbl, r, slot, n), gs in sorted(groups.items())]
    return ", ".join(parts[:12] + (["+%d" % (len(parts) - 12)] if len(parts) > 12 else []))


def slot_weight(code, cnt, itf):
    """★ ревизия 37 М-2: вес слота награды при выдаче (sub_45DEE0 :38665…): Function_Table — количество × вес (ток.2, +4), Cellob — вес
    самоцвета (ток.3, +6), количество не читается; item_table — стопка (+35): количество × вес (ток.2, +5), иначе вес одной вещи
    (≤ 0 → 1 при загрузке, GameServer.c:68325). Нет кода — 0."""
    if code <= 0:
        return 0
    if code < E.srvtables.CELLOB_BASE:
        r = E.srvtables.function_rule(code)
        return cnt * r["weight"] if r else 0
    if code < E.ITEM_FIRST:
        r = E.srvtables.cellob(code)
        return r["weight"] if r else 0
    f = itf(code)
    if not f:
        return 0
    w = max(E._int(f[2]), 1)
    return cnt * w if E._int(f[23]) else w


def rec_weight(f, itf):
    """Вес всей награды записи (включённые блоки, все 6 слотов) и число предметов в ней."""
    tot = n = 0
    for _nm, ci, ni, fl in ALL_SLOTS:
        c = _wi(f, ci)
        if c > 0 and _wi(f, fl):
            n += 1
            tot += slot_weight(c, _wi(f, ni), itf)
    return tot, n


def _base_tables(ev):
    """item_table и RepayTable всех GS ДО правок набора (снимок)."""
    if "_qt_base" not in ev.__dict__:
        rel = E.rel_of(E.GS[0], IT_TABLE)
        rep = {g: E.Table(E.rel_of(g, REPAY), ev.snap.raw(E.rel_of(g, REPAY))) for g in E.GS}
        ev._qt_base = (_itf_of(E.Table(rel, ev.snap.raw(rel))), rep)
    return ev._qt_base


def weight_top(ev):
    """★ ревизия 37 М-2: порог веса — самая тяжёлая награда RepayTable GameServer до правок набора (доказано выдаваемая данными: dev
    20.11 — 897, награды 545/535/475/362, по одному предмету) → (вес, запись)."""
    if "_qt_wtop" not in ev.__dict__:
        itf, rep = _base_tables(ev)
        best = (0, 0)
        for k, f in enumerate(_records(rep[E.GS[0]], REPAY_TOK)):
            best = max(best, (rec_weight(f, itf)[0], k + 1))
        ev._qt_wtop = best
    return ev._qt_wtop


def _item_set_codes(ev):
    """{код: [позиции «Предметы» без ошибок]} набора."""
    out = {}
    for r in ev.positions:
        if r["kind"] != "item.set" or r["errors"]:
            continue
        try:
            c = int((r.get("params") or {}).get("code"))
        except (TypeError, ValueError):
            continue
        out.setdefault(c, []).append(r)
    return out


def _weight_note(rid, old, new, n, top):
    """(предупреждение | None, сильная) по весу награды: при перегрузе sub_45DEE0 выходит ПОСРЕДИ цикла слотов (sub_4D7CD0 = 3:
    вес персонажа + вес слота > предела) — уже выданные слоты остаются, золото и опыт (после цикла) не выдаются, задание не сдано
    (Recv_RewardQuestProcess :37903 просто выходит), сдачу можно повторить."""
    if new <= old:
        return None, False
    strong = new > top[0]
    if not strong and n < 2:
        return None, False
    why = []
    if n >= 2:
        why.append("предметов в награде %d: при перегрузе сервер выходит посреди выдачи — уже выданные остаются, задание не сдано, сдачу можно "
                   "повторить и снова получить их (sub_45DEE0, sub_4D7CD0, GameServer.c:37903)" % n)
    if strong:
        why.append("больше самой тяжёлой награды в данных (%d, награда %d) — персонажу с обычной загрузкой может не влезть, сильная правка" % top)
    return "вес награды %d растёт %d → %d: %s" % (rid, old, new, "; ".join(why)), strong


def after_run(ev):
    """★ ревизия 37: проверки по ИТОГОВОМУ состоянию набора (все позиции уже применены к ev.st, порядок позиций не важен).
    Б-1 — стопка предметов награды по итоговой item_table; М-1 — смена стопки «Предметов» против всех наград RepayTable и предметов
    доски с этим кодом; М-2 — вес награды. Зовётся и из «Предметов» (itemdata.after_run), если «Заданий» в наборе нет."""
    rew = [r for r in ev.positions if r["kind"] == "quest.reward" and not r["errors"] and r.get("_slots") is not None]
    iset = _item_set_codes(ev)
    if not rew and not iset:
        return
    try:
        ev.snap.extend([E.rel_of(g, REPAY) for g in E.GS] + [E.rel_of(E.GS[0], LQ_GS)])
        repays = [(g, ev.st.get(g, REPAY)) for g in E.GS]
        board = ev.st.get(E.GS[0], LQ_GS)
        books = quest_books(ev)
        base_itf, base_rep = _base_tables(ev)
    except Exception as ex:
        for rs in iset.values():
            for r in rs:
                if any(g.get("why") == "stack" for g in r.get("guard") or []):
                    r["errors"].append("смена стопки: награды заданий не прочитаны (%s) — вслепую не делается" % str(ex)[:160])
        return
    itf, exists = ev.it_fields, ev.exists
    base_ex = _exists_of(base_itf, ev.fn, ev.cel)
    for r in rew:                                       # Б-1: стопка по итоговой item_table (с правками «Предметов» этого набора)
        for code_k, code, cnt in r["_slots"]:
            why = item_stack(code, cnt, itf, REWARD[code_k][2])
            if why:
                r["errors"].append(why)
    if iset:                                            # М-1: награды, которые ломает смена стопки
        uses = code_uses(repays, board, set(iset))
        for c, rs in iset.items():
            bad = [u for u in uses if u[4] == c and use_broken(u, itf, exists, books) and not use_broken(u, base_itf, base_ex, books)]
            if bad:
                for r in rs:
                    r["errors"].append((STACK_MSG + " — сначала поставьте в них количество 1, правка не делается") % (E.nm(c), _use_list(bad)))
    top = weight_top(ev)
    done = set()
    for r in rew:                                       # М-2: вес награды позиции
        if r["errors"]:
            continue
        rid = r["_rid"]
        done.add(rid)
        for code_k, code, cnt in r["_slots"]:
            w = slot_weight(code, cnt, itf)
            if w > I16_MAX:
                r["errors"].append("награда — %s: вес слота %d больше %d — сервер передаёт его проверке перегруза как __int16 (sub_4D7CD0) и "
                                   "прибавляет к весу персонажа младшее слово (sub_43F880), вес разошёлся бы, правка не делается"
                                   % (REWARD[code_k][2], w, I16_MAX))
        if r["errors"]:
            continue
        old = new = n = 0
        for g, t in repays:
            fo, fn_ = _records(base_rep[g], REPAY_TOK), _records(t, REPAY_TOK)
            if len(fo) >= rid and len(fn_) >= rid:
                o, _n = rec_weight(fo[rid - 1], base_itf)
                w, nn = rec_weight(fn_[rid - 1], itf)
                if w > new:
                    old, new, n = o, w, nn
        r.setdefault("lines", []).append("вес награды: %d → %d (самая тяжёлая награда в данных — %d, награда %d)" % (old, new, top[0], top[1]))
        note, strong = _weight_note(rid, old, new, n, top)
        if note:
            r["warnings"].append(note)
        if strong:
            r.setdefault("_balance", []).append({"what": "награда %d: вес награды" % rid, "old": old, "new": new, "codes": [], "kind": "weight"})
    for c, rs in iset.items():                          # М-2: вес наград, который меняет правка «Предметов» (вес / стопка кода)
        rows = []
        strong = False
        for _tbl, g, rid, _slot, _c, _n, on in code_uses(repays, None, {c}):
            if not on or g != E.GS[0] or rid in done:
                continue
            fo, fn_ = _records(base_rep[g], REPAY_TOK), _records(dict(repays)[g], REPAY_TOK)
            o = rec_weight(fo[rid - 1], base_itf)[0] if len(fo) >= rid else 0
            w, nn = rec_weight(fn_[rid - 1], itf)
            note, st = _weight_note(rid, o, w, nn, top)
            if note and rid not in [x[0] for x in rows]:
                rows.append((rid, o, w))
                strong = strong or st
        if rows:
            for r in rs:
                r["warnings"].append("вес наград заданий с %s растёт: %s — при перегрузе сервер выходит посреди выдачи (sub_45DEE0, sub_4D7CD0), "
                                     "самая тяжёлая награда в данных — %d" % (E.nm(c), ", ".join("RepayTable %d: %d → %d" % x for x in rows[:12]), top[0]))
                if strong:
                    r.setdefault("_balance", []).append({"what": "предмет %s: вес наград заданий" % E.nm(c), "old": max(x[1] for x in rows),
                                                         "new": max(x[2] for x in rows), "codes": [c], "kind": "weight"})


def _guard_state(cs, mode):
    """Таблицы стойки, какими они станут: apply — живые + файлы ЭТОГО набора (манифест сухого прогона: те же байты, что выложит
    выкладчик, md5 = утверждённому); rollback — живые, файлы набора — базой (.bak_<метка> = база). → ({путь: байты}, снимок живых).
    Не сходится — исключение (у вызывающего «не прочитаны» → отказ)."""
    rels = [E.rel_of(E.GS[0], IT_TABLE), E.rel_of(E.GS[0], QBOOK), E.rel_of(E.GS[0], LQ_GS)] + [E.rel_of(g, REPAY) for g in E.GS]
    files = {}
    for f in ((cs.get("check") or {}).get("server") or {}).get("files") or []:
        for g in f["gs"]:
            files[E.rel_of(g, f["table"])] = (f["base"], f["new"])
    mine = [r for r in rels if r in files]
    man = None
    if mine and cs.get("id") is not None:
        from domains import shopcs
        mp = shopcs.manifest_path(cs["id"])
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                man = json.load(fh)
    tag = (man or {}).get("tag") or cs.get("server_tag")
    baks = {r: r + ".bak_" + tag for r in mine} if mode == "rollback" and tag else {}
    md5 = E.live_md5(rels + list(baks.values()))
    sn = E.Snap(dict(md5))
    out = {}
    for r in rels:
        if r not in files:
            out[r] = sn.raw(r)
            continue
        base, new = files[r]
        if mode == "apply":
            if md5.get(r) == new:
                out[r] = sn.raw(r)
            elif md5.get(r) == base:
                lp = (((man or {}).get("files") or {}).get(r) or {}).get("local")
                if not lp or not os.path.isfile(lp):
                    raise RuntimeError("нет файла набора %s — сначала changeset server-dry" % r)
                with open(lp, "rb") as fh:
                    b = fh.read()
                if E.md5b(b) != new:
                    raise RuntimeError("файл набора %s ≠ утверждённому — повторите server-dry" % r)
                out[r] = b
            else:
                raise RuntimeError("%s на стойке — не база и не файл набора" % r)
        elif md5.get(r) == base:
            out[r] = sn.raw(r)
        elif r in baks and md5.get(baks[r]) == base:
            out[r] = sn.raw(baks[r])
        else:
            raise RuntimeError("%s: базы набора нет ни на месте, ни в .bak" % r)
    return out, sn


def apply_guard(cs, mode):
    """Правила выдачи предметов награды по таблицам, какими они СТАНУТ после выкладки (mode = apply: живые + правки набора) или после
    отката (rollback: живые, файлы набора — базой) → [причины отказа]. ★ ревизия 37 Б-1: item_table и RepayTable — с правками этого
    набора (стопка 1 → 0 в том же наборе — отказ, предмет стал стопочным в том же наборе — не отказ); М-1: смена стопки «Предметов»
    против всех наград RepayTable и предметов доски (появились после проверки — отказ). Не прочитано — отказ (вслепую не делается)."""
    from domains.cs_kinds import itemdata as I
    pos = {r["pos"]: r for r in (cs.get("check") or {}).get("positions") or []}
    todo = []
    for it in cs.get("items") or []:
        if it["kind"] != "quest.reward":
            continue
        for g in (pos.get(it["pos"]) or {}).get("guard") or []:
            code, cnt = g["new" if mode == "apply" else "old"]
            if code > 0:
                todo.append((it["pos"], g["slot"], code, cnt))
    stack_codes = {c for c, why in I.guard_codes(cs).items() if "stack" in why}
    ipos = {}
    for it in cs.get("items") or []:
        if it["kind"] == "item.set":
            try:
                ipos.setdefault(int((it.get("params") or {}).get("code")), it["pos"])
            except (TypeError, ValueError):
                pass
    if not todo and not stack_codes:
        return []
    try:
        st, sn = _guard_state(cs, mode)
        fn, cel = E.srvtables.table("Function_Table.txt"), E.srvtables.table("Cellob_Table.txt")
        tab = lambda rel, b: E.Table(rel, b)
        rit, rq, rlq = E.rel_of(E.GS[0], IT_TABLE), E.rel_of(E.GS[0], QBOOK), E.rel_of(E.GS[0], LQ_GS)
        itf = _itf_of(tab(rit, st[rit]))
        books = _books_of(st[rq])
        exists = _exists_of(itf, fn, cel)
        if stack_codes:
            now_itf = _itf_of(tab(rit, sn.raw(rit)))
            now_ex = _exists_of(now_itf, fn, cel)
            after = code_uses([(g, tab(E.rel_of(g, REPAY), st[E.rel_of(g, REPAY)])) for g in E.GS], tab(rlq, st[rlq]), stack_codes)
            now = {u[:4]: u for u in code_uses([(g, tab(E.rel_of(g, REPAY), sn.raw(E.rel_of(g, REPAY)))) for g in E.GS],
                                               tab(rlq, sn.raw(rlq)), stack_codes)}
    except Exception as ex:
        return ["предметы награды: таблицы стойки не прочитаны (%s) — вслепую не делается" % str(ex)[:160]]
    out = []
    for p, slot, code, cnt in todo:
        why = item_rule(code, cnt, itf, exists, books, REWARD[slot][2])
        if why:
            out.append("позиция %d: %s" % (p, why))
    for c in sorted(stack_codes):
        bad = [u for u in after if u[4] == c and use_broken(u, itf, exists, books)
               and not (u[:4] in now and use_broken(now[u[:4]], now_itf, now_ex, books))]
        if bad:
            out.append(("позиция %d: " + STACK_MSG) % (ipos.get(c, 0), E.nm(c), _use_list(bad)))
    return out


# =====================================================================================================================
# Клиент: снимок для службы и план половины на ПК
# =====================================================================================================================
def _tool(name):
    from domains.cs_kinds import texts as TX
    return TX._tool(name)


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def snapshot(snap):
    try:
        QR = _tool("asda_import_quest_reward_table")
        snap["qreward"] = {str(r["RecordIndex"]): [r[c] for c in QR_COLS] for r in _quiet(QR.read_rewards, E.CLIENT_FILES["qreward_bin"])}
    except Exception as ex:                             # нет файла / импортёра — область покажет «не прочитано»
        snap["qreward"], snap["qreward_err"] = None, str(ex)[:200]
    try:
        BQ = _tool("asda_import_board_quests")
        snap["board"] = {str(r["QuestId"]): {c: r[c] for c in BOARD_COLS}
                         for r in _quiet(BQ.read_quests, values_path=E.CLIENT_FILES["board_values"])}
    except Exception as ex:
        snap["board"], snap["board_err"] = None, str(ex)[:200]


def parse(cli, d):
    q, b = d.get("qreward"), d.get("board")
    cli.qreward = {int(k): v for k, v in q.items()} if isinstance(q, dict) else None
    cli.board = {int(k): v for k, v in b.items()} if isinstance(b, dict) else None


def _jobs(pc, dt, path, edits):
    for j in pc["json_jobs"]:
        if j["dt"] == dt:
            j["edits"] += edits
            return
    pc["json_jobs"].append({"dt": dt, "file": path, "edits": edits})


def _json_load(pc, key, err):
    from domains.cs_kinds import texts as TX
    cur = pc["load"](key, E.CLIENT_FILES[key])
    if cur[1] is None:
        err.append("%s: файла нет" % os.path.basename(E.CLIENT_FILES[key]))
        return None, None, None
    data, fmt = TX._json_fmt(cur[1])
    if fmt is None:
        err.append("%s: json.dumps не воспроизводит файл — правка не делается" % os.path.basename(E.CLIENT_FILES[key]))
        return None, None, None
    return cur, data, fmt


def _tmp_write(data):
    fd, tmp = tempfile.mkstemp(prefix="asda_cs_q_")
    os.write(fd, data)
    os.close(fd)
    return tmp


def _plan_reward(pc, e, err):
    from domains.cs_kinds import texts as TX
    QR = _tool("asda_import_quest_reward_table")
    DD = _tool("asda_item_dedup")
    bc = pc["load"]("qreward_bin", E.CLIENT_FILES["qreward_bin"])
    if bc[1] is None:
        return err.append("RewardTable.BIN: файла нет")
    jc, data, fmt = _json_load(pc, "qreward_json", err)
    if jc is None:
        return
    rid = e["rid"]
    # сторож правки владельца: JSON = НАСТОЯЩЕМУ импорту текущего BIN (иначе JSON или DT правили мимо источника — сначала импорт)
    tmp = _tmp_write(bc[1])
    try:
        now = _quiet(QR.read_rewards, tmp)
    finally:
        os.remove(tmp)
    if QR.json_rows(now).encode("utf-8") != jc[1]:
        return err.append("QuestRewardTable.json ≠ импорту RewardTable.BIN (asda_import_quest_reward_table) — JSON правили мимо BIN или "
                          "BIN не импортирован, правка не делается")
    b = bytearray(bc[1])
    n = struct.unpack_from("<i", b, 4)[0]
    off = next((QR_HDR + QR_REC * i for i in range(n) if struct.unpack_from("<i", b, QR_HDR + QR_REC * i)[0] == rid), None)
    if off is None or b[0x0C:0x0F] != b"RTE" or QR_HDR + QR_REC * n != len(b):
        return err.append("RewardTable.BIN: записи %d нет или файл не бьётся с шапкой" % rid)
    dmap = DD.active_map()
    for col, (o, nv) in e["fields"].items():
        at = off + 4 * QR_COLS.index(col)
        raw = struct.unpack_from("<i", b, at)[0]
        seen = {"v": raw}
        if col in ("ItemCode1", "ItemCode2", "ChoiceItemCode"):          # как read_rewards: коды — после карты item_dedup
            DD.remap_keys(seen, ("v",), dmap)
        if seen["v"] != int(o):
            return err.append("RewardTable.BIN запись %d: %s сейчас %d, при проверке было %s — пересоберите набор" % (rid, col, seen["v"], o))
        struct.pack_into("<i", b, at, int(nv))
    bc[1] = bytes(b)
    rows = [r for r in data if r.get("Name") == str(rid)]
    if len(rows) != 1:
        return err.append("QuestRewardTable.json: строки %d нет" % rid)
    edits = []
    for col, (o, nv) in sorted(e["fields"].items()):
        edits.append({"row": str(rid), "field": col, "index": None, "sub": None, "was": rows[0][col], "now": int(nv)})
        rows[0][col] = int(nv)
    jc[1] = TX._json_dump(data, fmt)
    tmp = _tmp_write(bc[1])                              # доказательство: НАСТОЯЩИЙ импорт нового BIN даёт ровно новый JSON
    try:
        got = QR.json_rows(_quiet(QR.read_rewards, tmp)).encode("utf-8")
    finally:
        os.remove(tmp)
    if got != jc[1]:
        return err.append("RewardTable.BIN запись %d: настоящий импорт нового BIN не даёт плановый QuestRewardTable.json (замена кода "
                          "картой item_dedup?) — правка не делается" % rid)
    _jobs(pc, DT_QREWARD, E.CLIENT_FILES["qreward_json"], edits)


def _plan_board(pc, e, err):
    from domains.cs_kinds import texts as TX
    BQ = _tool("asda_import_board_quests")
    jc, data, fmt = _json_load(pc, "board_json", err)
    if jc is None:
        return
    lc = pc["load"]("board_values", E.CLIENT_FILES["board_values"])
    if lc[1] is None:
        led, lfmt = {"rows": []}, (1, "\n", "\n", False)
    else:
        led, lfmt = TX._json_fmt(lc[1])
        if lfmt is None:
            return err.append("board_quest_values.json: json.dumps не воспроизводит файл — правка не делается")
    # сторож: JSON = НАСТОЯЩЕМУ импорту (эталон + lvMax 100 + скрытие + текущая ведомость чисел)
    tmp = _tmp_write(lc[1] or b'{"rows": []}')
    try:
        cur = _quiet(BQ.read_quests, values_path=tmp)
    except ValueError as ex:
        return err.append("ведомость board_quest_values.json не ложится на эталон: %s" % str(ex)[:200])
    finally:
        os.remove(tmp)
    if BQ.json_rows(cur, lambda r: str(r["QuestId"])).encode("utf-8") != jc[1]:
        return err.append("RaidQuestData.json ≠ импорту доски (asda_import_board_quests) — JSON правили мимо ведомости или импорт не сделан, "
                          "правка не делается")
    qid = e["quest"]
    rows = [r for r in data if r.get("Name") == str(qid)]
    if len(rows) != 1:
        return err.append("RaidQuestData.json: задания %d нет" % qid)
    edits = []
    for col, (o, nv) in sorted(e["fields"].items()):
        if rows[0][col] != o:
            return err.append("RaidQuestData.json %d: %s сейчас %s, при проверке было %s — пересоберите набор" % (qid, col, rows[0][col], o))
        hit = [r for r in led["rows"] if int(r["quest"]) == qid and r["field"] == col]
        if hit:
            hit[-1]["now"] = int(nv)
            if int(hit[-1]["was"]) == int(nv):
                led["rows"].remove(hit[-1])
        else:
            led["rows"].append({"quest": qid, "field": col, "was": o, "now": int(nv), "source": "admin_center",
                                "reason": "набор изменений №%s админ-центра (причина — в карточке набора и changelog)" % pc["cs_id"]})
        edits.append({"row": str(qid), "field": col, "index": None, "sub": None, "was": o, "now": int(nv)})
        rows[0][col] = int(nv)
    jc[1] = TX._json_dump(data, fmt)
    lc[1] = TX._json_dump(led, lfmt)
    tmp = _tmp_write(lc[1])                              # доказательство: НАСТОЯЩИЙ импорт с новой ведомостью даёт ровно новый JSON
    try:
        got = BQ.json_rows(_quiet(BQ.read_quests, values_path=tmp), lambda r: str(r["QuestId"])).encode("utf-8")
    except ValueError as ex:
        return err.append("новая ведомость board_quest_values.json не ложится: %s" % str(ex)[:200])
    finally:
        os.remove(tmp)
    if got != jc[1]:
        return err.append("доска %d: настоящий импорт с новой ведомостью не даёт плановый RaidQuestData.json — правка не делается" % qid)
    _jobs(pc, DT_BOARD, E.CLIENT_FILES["board_json"], edits)


def plan(pc):
    err = pc["errors"]
    for e in pc["by_file"].get("qreward_bin", []):
        try:
            _plan_reward(pc, e, err)
        except ImportError as ex:
            err.append("импортёр наград порта не загружен: %s" % ex)
    for e in pc["by_file"].get("board_json", []):
        try:
            _plan_board(pc, e, err)
        except ImportError as ex:
            err.append("импортёр доски порта не загружен: %s" % ex)


# =====================================================================================================================
# Справка редактору (только чтение) и расхождения
# =====================================================================================================================
class _RefEv:
    """Носитель снимка для users_of_reward в справке (без оценки набора)."""

    def __init__(self, snap):
        self.snap = snap


def _ref():
    sn = E.Snap(E.live_md5([E.rel_of(g, REPAY) for g in E.GS]))
    return sn, E.SrvState(sn)


def _repay_of(st, g, rid):
    t = st.get(g, REPAY)
    i = E.record_line(t, rid - 1, REPAY_TOK)
    if i is None or i < 0:
        return None
    return dict(zip(QD.REPAY_KEYS, (_tok_int(_toks(t.lines[i]), j + 1) for j in range(len(QD.REPAY_KEYS)))))


def lookup_reward(rid):
    sn, st = _ref()
    srv = {g: _repay_of(st, g, rid) for g in E.GS}
    cli = E.Client.load()
    c = (cli.qreward or {}).get(rid)
    if srv[E.GS[0]] is None and c is None:
        raise OpRefused("награды %d нет ни на сервере, ни у клиента" % rid)
    uses = users_of_reward(_RefEv(sn), rid)
    hold = quest_holders([q for q, _s, _a in uses])
    r0 = srv[E.GS[0]] or {}
    return {"rid": rid, "server": srv, "client": dict(zip(QR_COLS, c)) if c else None, "client_err": None if cli.qreward is not None else
            "RewardTable не прочитан", "fields": [[k, REWARD[k][1], REWARD[k][2]] + list(rng_reward(k)) for k in REWARD],    # ★ ревизия 37 К-5: пределы = norm
            "counts": {g: E._int(st.get(g, REPAY).lines[0].decode("latin-1")) for g in E.GS},   # ★ К-2: у копии своя база
            "flags": {"a": r0.get("a_flag"), "b": r0.get("b_flag"), "pen": r0.get("pen_flag"), "pen_base": r0.get("pen_base"),
                      "job": r0.get("job")},
            "names": {str(r0.get(x)): E._name(r0.get(x)) for x in ("item1", "item2", "item4") if r0.get(x, -1) > 0},
            "quests": [{"quest": q, "name": _qname(q), "step": s, "action": a,
                        "holders": None if hold is None else len(hold.get(q, []))} for q, s, a in uses],
            "holders_error": quest_holders.last_error}


def search(q, limit=80):
    """Награды по заданию (номер или часть названия) → [{quest, name, rewards: [rid…]}]; число — ещё и номер награды."""
    from domains import refdata
    sn, _st = _ref()
    b, x, c = _npc_bytes(_RefEv(sn))
    takes = QD.parse_cells(b, x)[1]
    s = (q or "").strip().lower()
    out = []
    for qq in sorted(takes):
        nm = refdata.quest(qq)
        if s and s != str(qq) and s not in nm.lower():
            continue
        rids = sorted({r for _n, _c, _st, keys in takes[qq] for key in keys if key > 0
                       for cc in [QD.cond_rec(c, key)] if cc and cc["reward_flag"] == 1 for r in cc["rewards"] if r > 0})
        out.append({"quest": qq, "name": nm, "rewards": rids})
        if len(out) >= limit:
            break
    return {"rows": out}


def lookup_board(ident):
    sn = E.Snap(E.live_md5([f + "\\" + s for f, s in board_copies()]))
    st = E.SrvState(sn)
    t = st.get(E.GS[0], LQ_GS)
    cli = E.Client.load()
    n = E._int(t.lines[0].decode("latin-1"))
    rows = []
    for k in range(n):
        i = E.record_line(t, k, LQ_TOK)
        if i is None or i < 0:
            break
        f = _toks(t.lines[i])
        qid = _tok_int(f, 0)
        c = (cli.board or {}).get(qid) or {}
        rows.append({"quest": qid, "type": _tok_int(f, 1), "mode": _tok_int(f, 7), "zone": _tok_int(f, 4),
                     "server": {x: _tok_int(f, BOARD[x][0]) for x in BOARD}, "client": {x: c.get(BOARD[x][1]) for x in BOARD} if c else None})
    same = len({sn.md5.get(f + "\\" + s) for f, s in board_copies()}) == 1
    out = {"rows": rows, "copies_same": same, "fields": [[x, BOARD[x][1], BOARD[x][2]] + list(rng_board(x)) for x in BOARD]}   # ★ ревизия 37 К-5
    s = str(ident or "").strip()
    if s:
        try:
            qid = int(s)
        except ValueError:
            raise OpRefused("задание доски: нужно целое число")
        hit = [r for r in rows if r["quest"] == qid]
        if not hit:
            raise OpRefused("задания доски %d нет" % qid)
        h = board_holders([qid])
        out["card"] = dict(hit[0], holders=None if h is None else [{"name": x[2], "uid": x[0], "idx": x[1], "lvl": x[3], "flag": x[4],
                                                                     "count": x[5]} for x in h.get(qid, [])[:50]],
                           holders_error=board_holders.last_error)
    return out


def lookup(what, ident):
    if what == "quests":
        return search(ident)
    if what == "repay":
        try:
            rid = int(str(ident).strip())
        except (TypeError, ValueError):
            raise OpRefused("награда: нужно целое число")
        return lookup_reward(rid)
    return lookup_board(ident)


def divergence(ev, cli, sec):
    """Награды RepayTable ≠ RewardTable клиента (золото, опыт, A1, A2, B1); записи Indun; доска сервер ≠ клиент."""
    rows = []
    t = ev.st.get(E.GS[0], REPAY)
    n = E._int(t.lines[0].decode("latin-1"))
    if cli.qreward is None:
        sec("quests", "задания: награды сервер ≠ клиент (RepayTable ↔ RewardTable)", [], "RewardTable клиента не прочитан")
    else:
        for rid in range(1, n + 1):
            r = _repay_of(ev.st, E.GS[0], rid)
            c = cli.qreward.get(rid)
            if r is None:
                break
            if c is None:
                rows.append({"rid": rid, "field": "—", "why": "записи нет у клиента"})
                continue
            cf = dict(zip(QR_COLS, c))
            for k, (_tk, col, lbl) in REWARD.items():
                empty = k.endswith("n") and r[k[:-1]] <= 0 and cf[REWARD[k[:-1]][1]] <= 0     # пустой слот: количество не сравнивается
                if cf[col] != r[k] and not empty:
                    rows.append({"rid": rid, "field": lbl, "server": r[k], "client": cf[col], "why": "сервер ≠ клиент"})
        for g in E.GS[1:]:
            ni = E._int(ev.st.get(g, REPAY).lines[0].decode("latin-1"))
            if ni != n:
                rows.append({"rid": "—", "field": g, "why": "записей %d, у GameServer %d — своя база копии (правка записей сверх — отказ)" % (ni, n)})
        sec("quests", "задания: награды сервер ≠ клиент (RepayTable ↔ RewardTable)", rows,
            "запись N клиента = запись N сервера; коды клиента — после карты item_dedup")
    rows = []
    tb = ev.st.get(E.GS[0], LQ_GS)
    for k in range(E._int(tb.lines[0].decode("latin-1"))):
        i = E.record_line(tb, k, LQ_TOK)
        if i is None or i < 0:
            rows.append({"rid": LQ_BASE + k, "field": "—", "why": "записи доски сервер не читает построчно"})
            break
        f = _toks(tb.lines[i])
        qid = _tok_int(f, 0)
        c = (cli.board or {}).get(qid)
        if c is None:
            rows.append({"rid": qid, "field": "—", "why": "задания нет у клиента"})
            continue
        for x, (tk, col, lbl) in BOARD.items():
            if _tok_int(f, tk) != c.get(col):
                rows.append({"rid": qid, "field": lbl, "server": _tok_int(f, tk), "client": c.get(col), "why": "сервер ≠ клиент"})
    sec("board", "доска объявлений: сервер ≠ клиент (LimitationQuest ↔ DT_RaidQuestData)", rows, "клиент — эталон + ведомость чисел")
