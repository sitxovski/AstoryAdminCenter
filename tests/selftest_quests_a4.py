# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_quests_a4.py — самотест шага А4.5 «Задания» (20.11.2026, domains/cs_kinds/questtables.py).

offline(check)       — подменная стойка selftest_shops.synthetic() + свои RepayTable (у Indun своя база: короче и с другим золотом),
                       12 копий LimitationQuest, QuestNpcTable / ConditionTable (кто даёт награду), QuestBook_Table, item_table А4.4:
                       награды (золото, опыт, предметы A1/A2/B1), отказы «дюп и целостность» (нестопочный и самоцвет с количеством > 1,
                       полустопка, контейнер, золото, книга, нет на сервере, блок выключен, Indun без записи / с другим значением), баланс,
                       «кто держит задание», доска (уровни, лимит, опыт, золото, копии), перепроверка перед выкладкой и откатом
                       (apply_guard), расхождения, справка, переводы службы и веба, ведомость чисел импортёра доски, разбор questdata.
                       План клиента — на ВРЕМЕННЫХ КОПИЯХ настоящих файлов порта с НАСТОЯЩИМИ импортёрами (asda_import_quest_reward_table,
                       asda_import_board_quests): md5 файлов порта до = после.
sandbox(check, ldb)  — путь набора целиком: создать → проверить → утвердить (сильная — второе подтверждение) → НАСТОЯЩИЙ сухой прогон
                       deploy_changeset (RepayTable ×3 + LimitationQuest ×12) → клиент (копии BIN/JSON/ведомость, JSON-точки DT
                       подставной очередью UE) → выкладка (перепроверка: предмет стал нестопочным — отказ до объявления) → откат (прежний
                       предмет не проходит — без --held-ok отказ) → откаты сервера и клиента (всё вернулось).
live(check)          — только чтение и сухие прогоны: md5 копий стойки, справка, живая оценка набора, план клиента настоящими импортёрами
                       (md5 порта до = после), НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH.
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
NPC3 = ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")
REPAY_REL = "ItemTable_Info" + BS + "RepayTable.txt"
QB_REL = "ItemTable_Info" + BS + "QuestBook_Table.txt"
LQ_GS = ("NpcData_Info" + BS + "LimitationQuest.txt", "ItemTable_Info" + BS + "LimitationQuest.txt")
LQ_NPC = ("Quest" + BS + "LimitationQuest.txt", "NpcInfo" + BS + "LimitationQuest.txt")


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _crlf(rows):
    return ("\r\n".join(rows) + "\r\n").encode("latin-1")


def _repay_row(rid, gold=0, exp=10, a=1, i1=(-1, 0), i2=(-1, 0), b=0, i4=(-1, 0), pen=1):
    """35 токенов как в живой RepayTable (TAB, у ток.2–4 пробел после числа)."""
    t = [rid, pen, 3, gold, exp, a, 0, -1, -1, -1, -1, 0, -1, 0, -1, 0, i1[0], i1[1], i2[0], i2[1], -1, 0,
         b, 0, -1, -1, -1, 0, i4[0], i4[1], -1, 0, -1, 0, -1]
    s = ["%d" % v for v in t]
    s[2], s[3], s[4] = s[2] + " ", s[3] + " ", s[4] + " "
    return "\t".join(s)


def repay_rows(indun=False):
    rows = [_repay_row(1, gold=100, exp=50, i1=(31001, 2)),
            _repay_row(2, gold=5 if indun else 0, exp=10, b=1, i4=(31000, 1)),
            _repay_row(3, gold=7, exp=7)]
    rows = rows[:2] if indun else rows
    return _crlf([str(len(rows))] + rows)


def _lq_row(qid, typ, mx, lvmin, lvmax, exp, gold):
    t = [qid, typ, mx, qid, 2, lvmin, lvmax, 0, 31001, -1, -1, -1, -1, 5, -1, -1, -1, -1, -1, -1, -1, -1, 0, 0, 0, 0, exp, gold, -1, -1, 0, 0]
    return "\t".join("%d" % v for v in t)


def lq_file():
    return _crlf(["2", _lq_row(20000, 1, 3, 10, 50, 1000, 500), _lq_row(20001, 0, 0, 20, 100, 2000, 900)])


def _cond(key, rewards, action=2):
    r = bytearray(146)
    r[10] = 1
    for s, x in enumerate(rewards[:5]):
        struct.pack_into("<h", r, 11 + 4 * s, x)
    r[35] = action
    return bytes(r)


def cond_table():
    return b"".join([bytes(146), _cond(1, [1]), _cond(2, [2, 3])])


def npc_table():
    b = bytearray(1774)
    so = 894                                   # ячейка «ПРИНИМАЕТ» 0: задание 7, шаг 1, ключ 1; ячейка 1: задание 8, шаг 0, ключ 2
    struct.pack_into("<h", b, so, 7)
    b[so + 2] = ord("Q")
    struct.pack_into("<h", b, so + 66, 1)
    struct.pack_into("<5i", b, so + 68, 1, 0, 0, 0, 0)
    so += 88
    struct.pack_into("<h", b, so, 8)
    b[so + 2] = ord("Q")
    struct.pack_into("<5i", b, so + 68, 2, 0, 0, 0, 0)
    return bytes(b)


def stack_files():
    import selftest_items_a4 as I4
    out = dict(I4.stack_files())                 # item_table + Cellob_Table трёх GS (предметы А4.4: стопка, штучный, контейнер, полустопка)
    for g in GS3:
        out[g + BS + REPAY_REL] = repay_rows(indun=g == "Indun_GameServer")
        out[g + BS + QB_REL] = _crlf(["1", "2001\t7\t0\t-1\t-1\t-1"])
        for s in LQ_GS:
            out[g + BS + s] = lq_file()
    for n in NPC3:
        for s in LQ_NPC:
            out[n + BS + s] = lq_file()
        out[n + BS + "Quest" + BS + "QuestNpcTable.Bin"] = npc_table()
        out[n + BS + "Quest" + BS + "ConditionTable.Bin"] = cond_table()
    return out


QR_CLI = {1: [1, 7, 1, 100, 50, 31001, 2, -1, 0, 0, -1, 0], 2: [2, 7, 1, 0, 10, -1, 0, -1, 0, 1, 31000, 1], 3: [3, 8, 0, 7, 7, -1, 0, -1, 0, 0, -1, 0]}
BOARD_CLI = {20000: {"LevelMin": 10, "LevelMax": 50, "MaxCount": 3, "Exp": 1000, "Gold": 500, "PeriodType": 1, "Mode": 0, "Zone": 2},
             20001: {"LevelMin": 20, "LevelMax": 100, "MaxCount": 0, "Exp": 2000, "Gold": 900, "PeriodType": 0, "Mode": 0, "Zone": 2}}
HOLD_Q = {7: [(75001, 1, "Игрок", 12, 0), (75002, 3, "Second", 30, 0)]}
HOLD_B = {20000: [(75003, 2, "Борд", 15, 1, 0), (75004, 1, "Done", 40, 3, 3), (75005, 1, "Zero", 33, 0, 4)]}   # Zero — флаг 0, сдано 4 (М-3)


def _ev(items):
    from domains import shopdata as SD
    return SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False).run()


def _tok(raw, rid_or_k, tok, by_pos=True):
    lines = [ln for ln in raw.split(b"\r\n")[1:] if ln.strip()]
    return lines[rid_or_k].split(b"\t")[tok] if by_pos else None


class _Patch:
    """Подмены «кто держит задание» (Joy1) и Function/Cellob на время блока."""

    def __init__(self, fail=False):
        self.fail = fail

    def __enter__(self):
        from domains import srvtables
        from domains.cs_kinds import questtables as Q
        self.saved = (Q.quest_holders, Q.board_holders, srvtables.table)
        fail = self.fail

        def qh(qs):
            if fail:
                qh.last_error = "нет связи с Joy1 (самотест)"
                return None
            return {q: list(HOLD_Q.get(q, [])) for q in qs}
        qh.last_error = None

        def bh(ids, min_count=None):
            if fail:
                bh.last_error = "нет связи с Joy1 (самотест)"
                return None
            # ★ ревизия 37 М-3: как запрос — флаг ≠ 0, а при min_count ещё флаг 0 со счётчиком ≥ min_count
            return {q: [x for x in HOLD_B.get(q, []) if x[4] or (min_count is not None and x[5] >= min_count)] for q in ids}
        bh.last_error = None
        Q.quest_holders, Q.board_holders = qh, bh
        old = srvtables.table
        srvtables.table = lambda name: ({7001: ["7001"]} if name.startswith("Cellob") else old(name))
        return self

    def __exit__(self, *a):
        from domains import srvtables
        from domains.cs_kinds import questtables as Q
        Q.quest_holders, Q.board_holders, srvtables.table = self.saved
        return False


def _errs(ev):
    return [e for r in ev.positions for e in r["errors"]]


def _cs_man(e, cid, items):
    """★ ревизия 37: набор с итогом проверки e и НАСТОЯЩИМ манифестом сухого прогона (shopcs.build_server_out; каталог наборов —
    временный, его ставит offline)."""
    from domains import shopcs
    cs = {"id": cid, "items": [{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], "check": e.summary()}
    shopcs.build_server_out(cs, e)
    return cs


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check):
    import selftest_shops as T
    from domains import shopdata as SD, questdata as QD
    from domains.cs_kinds import questtables as Q
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    check("А4.5 реестр: область «quests» (за ней — только «Звания» А4.6), виды quest.reward / board.quest, права data.edit / data.apply, гейт баланса; RepayTable — "
          "per_copy (у Indun своя база), LimitationQuest — same во всех 4 подпутях; выкладчик пускает RepayTable ×3 и LimitationQuest ×12",
          SD.AREAS[SD.AREAS.index(Q) + 1:] == [a for a in SD.AREAS if a.AREA in ("titledata", "skilldata", "mapdata", "events", "patchcfg")] and set(Q.KINDS) == {"quest.reward", "board.quest"} and SD.area_perm("quest.reward", "apply") == "data.apply"
          and SD.area_perm("board.quest", "edit") == "data.edit" and Q.BALANCE_GATE
          and SD.SRV_POLICY["ItemTable_Info\\RepayTable.txt"] == "per_copy"
          and all(SD.SRV_POLICY[s] == "same" for s in LQ_GS + LQ_NPC)
          and all(g + BS + REPAY_REL in dc.ALLOWED and all(g + BS + s in dc.ALLOWED for s in LQ_GS) for g in GS3)
          and all(n + BS + s in dc.ALLOWED for n in NPC3 for s in LQ_NPC))
    bad = []
    for kind, p in (("quest.reward", {"rid": 1}), ("quest.reward", {"rid": 1, "fields": {}}), ("quest.reward", {"rid": 1, "fields": {"job": 3}}),
                    ("quest.reward", {"rid": 0, "fields": {"gold": 1}}), ("quest.reward", {"rid": 1, "fields": {"gold": -5}}),
                    ("quest.reward", {"rid": 1, "fields": {"item1n": 40000}}), ("board.quest", {"quest": 19999, "fields": {"exp": 1}}),
                    ("board.quest", {"quest": 20000, "fields": {"lvmin": 0}}), ("board.quest", {"quest": 20000, "fields": {"type": 1}})):
        try:
            SD.norm(kind, p)
            bad.append(p)
        except Exception:
            pass
    check("А4.5 позиции: неверные параметры — отказ (нет полей, пустые поля, неправимое поле профессии/типа, номер вне диапазона, "
          "отрицательное золото, количество > 32767, уровень 0); пустое поле — «не менять»", not bad and
          SD.norm("quest.reward", {"rid": 1, "fields": json.dumps({"gold": 7, "exp": ""})})["fields"] == {"gold": 7}, bad)
    # разбор questdata: прежние _cells / cond — через новые parse_cells / cond_rec (поведение то же)
    saved_b = QD._bytes
    QD._bytes = lambda rel: npc_table() if rel.endswith("QuestNpcTable.Bin") else (b"" if rel.endswith("Ext.Bin") else cond_table())
    QD._cache.clear()
    try:
        g, t = QD._cells()
        c1 = QD.cond(1)
    finally:
        QD._bytes = saved_b
        QD._cache.clear()
    check("А4.5 questdata: _cells и cond идут через parse_cells / cond_rec (байты передаются) — ячейки «ПРИНИМАЕТ» 7/шаг 1 и 8, условие 1 — "
          "награда 1, действие 2", t.get(7) == [(0, 0, 1, [1, 0, 0, 0, 0])] and 8 in t and not g and c1["rewards"][0] == 1 and c1["action"] == 2
          and QD.cond_rec(cond_table(), 2)["rewards"][:2] == [2, 3], (g, t))
    with T.synthetic() as (raw, md5, cli):
        for rel, b in stack_files().items():
            raw[rel], md5[rel] = b, _md5(b)
        cli.qreward, cli.board = {k: list(v) for k, v in QR_CLI.items()}, {k: dict(v) for k, v in BOARD_CLI.items()}
        import selftest_items_a4 as I4
        cli.itemcard, cli.gemcard = I4._cards()             # ★ ревизия 37: позиции «Предметов» в наборах с наградами
        saved_held, saved_dir = SD.held_counts, SD.CS_DIR
        SD.held_counts = I4._fake_held()
        SD.CS_DIR = tempfile.mkdtemp(prefix="asda_q37_cs_")  # манифесты сухого прогона — во временном каталоге
        try:
            with _Patch():
                _offline_reward(check, raw, md5, cli)
                _offline_board(check, raw, md5, cli)
                _offline_guard(check, raw, md5, cli)
                _offline_r37(check, raw, md5, cli)
        finally:
            shutil.rmtree(SD.CS_DIR, ignore_errors=True)
            SD.held_counts, SD.CS_DIR = saved_held, saved_dir
        with _Patch():
            d = SD.divergence(areas=("quests",))
            secs = {s["key"]: s for s in d["sections"]}
            cli.qreward[3][4] = 70
            d2 = SD.divergence(areas=("quests",))
            s2 = {s["key"]: s for s in d2["sections"]}
            check("А4.5 расхождения: разделы quests и board; у Indun записей 2 (своя база) — строка раздела; опыт клиента ≠ сервера — строка",
                  list(secs) == ["quests", "board"] and any("Indun_GameServer" == r["field"] for r in secs["quests"]["rows"])
                  and not secs["board"]["rows"] and any(r["rid"] == 3 and r["field"] == "опыт" for r in s2["quests"]["rows"]),
                  [(k, v["rows"][:3]) for k, v in secs.items()])
            cli.qreward[3][4] = 7
    _offline_tr(check)
    _ledger_board(check)
    _plan_real(check)


def _offline_reward(check, raw, md5, cli):
    from domains.cs_kinds import questtables as Q
    e = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 150, "exp": 60}})])
    s = e.summary()
    files = sorted(f for f in e.new_bytes())
    nb = e.new_bytes()
    p = s["positions"][0]
    check("quest.reward: золото 100 → 150, опыт 50 → 60 — RepayTable ×3 GS (Indun правится в своей записи 1, его запись 2 со своим золотом "
          "сохранена), пробелы токенов сохранены; клиент — RewardTable Money/Exp; «даёт» — задание 7, шаг 1; кто держит — предупреждение "
          "со списком (ход задания не меняется); баланс не сильный",
          not e.errors and files == sorted(g + BS + REPAY_REL for g in GS3)
          and _tok(nb["Indun_GameServer" + BS + REPAY_REL], 0, 3) == b"150 " and _tok(nb["Indun_GameServer" + BS + REPAY_REL], 1, 3) == b"5 "
          and _tok(nb["GameServer" + BS + REPAY_REL], 0, 4) == b"60 "
          and s["client"] == [{"type": "qreward_set", "file": "qreward_bin", "rid": 1, "fields": {"Exp": [50, 60], "Money": [100, 150]}}]
          and p["quests"] == [{"quest": 7, "step": 1, "action": 2}] and any("сейчас взято (2 перс.)" in w and "Игрок (75001/1, ур. 12, шаг 0)" in w
                                                                         for w in p["warnings"])
          and not s["balance_strong"] and p["guard"] == [], (e.errors, p.get("warnings"), s["client"]))
    e = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 400, "item1": 31001, "item1n": 5}})])
    check("quest.reward: золото ×4 — сильная правка; количество стопочного предмета 2 → 5 — правка количества (порог ×2: сильная); guard — "
          "слот A1 (новое и прежнее)", not e.errors and e.summary()["balance_strong"]
          and e.summary()["positions"][0]["guard"] == [{"slot": "item1", "new": [31001, 5], "old": [31001, 2]}], (e.errors, e.balance))
    e = _ev([("quest.reward", {"rid": 2, "fields": {"exp": 12, "item4": 31002, "item4n": 1}})])
    b = e.summary()["balance"]
    check("quest.reward: замена предмета B1 31000 → 31002 — swap (сильная всегда); опыт записи 2 правится и у Indun (у него другое только "
          "золото); у клиентской записи флаг «на выбор» = 1 — без предупреждения",
          not e.errors and any(x["kind"] == "swap" and x["strong"] and set(x["codes"]) == {31000, 31002} for x in b)
          and not any("флаг «на выбор»" in w for w in e.positions[0]["warnings"]), (e.errors, b))
    e = _ev([("quest.reward", {"rid": 1, "fields": {"item1": 5, "item1n": 3}})])
    check("quest.reward: предмет Function_Table (5) с количеством 3 — можно (сервер выдаёт количество × вес, ветка sub_532B10)",
          not e.errors, e.errors)
    cases = [
        ({"rid": 3, "fields": {"gold": 8}}, "у копии своя база"),                           # у Indun записи 3 нет
        ({"rid": 2, "fields": {"gold": 9}}, "отличия копии не затираются"),                  # у Indun другое золото
        ({"rid": 9, "fields": {"gold": 9}}, "записей 3"),
        ({"rid": 2, "fields": {"item4n": 2}}, "не стопочный, количество 2"),                  # 31000 — броня, штучная
        ({"rid": 1, "fields": {"item1": 31008}}, "полустопка"),
        ({"rid": 1, "fields": {"item1": 31003}}, "контейнер"),
        ({"rid": 1, "fields": {"item1": 20551}}, "золото (20551)"),
        ({"rid": 1, "fields": {"item1": 2001, "item1n": 1}}, "книга задания"),
        ({"rid": 1, "fields": {"item1": 39999}}, "нет на сервере"),
        ({"rid": 1, "fields": {"item2": 7001, "item2n": 2}}, "самоцвет 7001, количество 2"),
        ({"rid": 1, "fields": {"item4": 31001, "item4n": 1}}, "блок B записи 1 выключен"),
        ({"rid": 1, "fields": {"item1n": 0}}, "нужно от 1"),
        ({"rid": 1, "fields": {"item2n": 3}}, "без предмета"),
        ({"rid": 1, "fields": {"gold": 100}}, "менять нечего"),
    ]
    bad = []
    for prm, want in cases:
        errs = _errs(_ev([("quest.reward", prm)]))
        if not any(want in x for x in errs):
            bad.append((prm, errs[:1]))
    check("quest.reward: 14 отказов (Indun без записи, Indun с другим значением, нет записи, нестопочный ×2, полустопка, контейнер, золото, "
          "книга задания, нет на сервере, самоцвет ×2, блок B выключен, количество 0 при предмете, количество без предмета, «менять нечего»)",
          not bad, bad)
    keep = cli.qreward.pop(1)
    errs = _errs(_ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})]))
    cli.qreward[1] = keep
    cli.qreward[1][3] = 90
    e = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})])
    cli.qreward[1][3] = 100
    check("quest.reward: у клиента нет записи — отказ «пара не собирается»; клиент уже расходился с сервером — предупреждение, клиенту "
          "ставится новое (было клиентское 90)", any("пара не собирается" in x for x in errs) and not e.errors
          and any("уже расходились" in w for w in e.positions[0]["warnings"]) and e.client[0]["fields"]["Money"] == [90, 120], (errs, e.errors))
    with _Patch(fail=True):
        e = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})])
    check("quest.reward: «кто держит задание» не прочитано — предупреждение «не прочитано», не отказ (правка хода задания не меняет)",
          not e.errors and any("не прочитано" in w for w in e.positions[0]["warnings"]), e.errors)


def _offline_board(check, raw, md5, cli):
    e = _ev([("board.quest", {"quest": 20000, "fields": {"lvmin": 12, "exp": 1500, "max": 5}})])
    s = e.summary()
    nb = e.new_bytes()
    w = e.positions[0]["warnings"]
    want = sorted([g + BS + x for g in GS3 for x in LQ_GS] + [n + BS + x for n in NPC3 for x in LQ_NPC])
    check("board.quest: мин. уровень 10 → 12, опыт 1000 → 1500, лимит 3 → 5 — 12 копий LimitationQuest одинаково; клиент — LevelMin/Exp/"
          "MaxCount; взявшие (флаг 1) — предупреждение со списком; лимит исчерпан у 1 (флаг 3) — предупреждение",
          not e.errors and sorted(nb) == want and len({v for v in nb.values()}) == 1 and _tok(nb[want[0]], 0, 5) == b"12"
          and _tok(nb[want[0]], 0, 26) == b"1500" and _tok(nb[want[0]], 0, 2) == b"5" and _tok(nb[want[0]], 1, 5) == b"20"
          and s["client"][0]["fields"] == {"Exp": [1000, 1500], "LevelMin": [10, 12], "MaxCount": [3, 5]}
          and any("сейчас взято (1 перс.)" in x and "Борд" in x for x in w) and any("лимит задания 20000 исчерпан" in x for x in w), (e.errors, w))
    cases = [({"quest": 20000, "fields": {"lvmin": 60}}, "больше макс."), ({"quest": 20000, "fields": {"max": 0}}, "после первой сдачи"),
             ({"quest": 20005, "fields": {"exp": 1}}, "нет в"), ({"quest": 20000, "fields": {"exp": 1000}}, "менять нечего")]
    bad = [(p, _errs(_ev([("board.quest", p)]))[:1]) for p, want_ in cases if not any(want_ in x for x in _errs(_ev([("board.quest", p)])))]
    rel = "Indun_NpcServer" + BS + LQ_NPC[1]
    keep = raw[rel]
    raw[rel] = keep.replace(b"\t1000\t500\t", b"\t1100\t500\t")
    md5[rel] = _md5(raw[rel])
    e2 = _ev([("board.quest", {"quest": 20000, "fields": {"exp": 1200}})])
    raw[rel], md5[rel] = keep, _md5(keep)
    e3 = _ev([("board.quest", {"quest": 20001, "fields": {"max": 4}})])
    check("board.quest: 4 отказа (мин. > макс., лимит 0 при типе 1, нет задания, «менять нечего»); копия NpcInfo Indun разошлась — отказ "
          "«копии разошлись»; лимит у типа 0 — предупреждение «лимит не проверяет»",
          not bad and any("копии разошлись" in x for x in _errs(e2)) and not e3.errors
          and any("лимит не проверяет" in x for x in e3.positions[0]["warnings"]), (bad, _errs(e2)))


def _offline_guard(check, raw, md5, cli):
    from domains import shopcs
    from domains.cs_kinds import questtables as Q
    e = _ev([("quest.reward", {"rid": 1, "fields": {"item1": 31001, "item1n": 4}}), ("board.quest", {"quest": 20000, "fields": {"exp": 1100}})])
    # ★ ревизия 37 Б-1: перепроверка читает файлы ЭТОГО набора из манифеста сухого прогона (живые + правки набора)
    cs = _cs_man(e, 9901, [("quest.reward", {}), ("board.quest", {})])
    ok_a, ok_r = shopcs.area_guard(cs, "apply"), shopcs.area_guard(cs, "rollback")
    rel = "GameServer" + BS + "ItemTable_Info" + BS + "item_table.txt"
    keep = raw[rel]
    ln = [x for x in keep.split(b"\r\n") if x.startswith(b"31001 ")][0]
    f = ln.split(b"\t")
    f[23] = b"0 "
    raw[rel] = keep.replace(ln, b"\t".join(f))
    md5[rel] = _md5(raw[rel])
    bad_a, bad_r = shopcs.area_guard(cs, "apply"), shopcs.area_guard(cs, "rollback")
    raw[rel], md5[rel] = keep, _md5(keep)
    check("А4.5 перепроверка (урок ревизии 36 Б-1): правила выдачи предметов награды по живой item_table — прошли: пусто; 31001 стал "
          "нестопочным — и выкладка (новое: 4 шт.), и откат (прежнее: 2 шт.) получают причину «не стопочный» с номером позиции",
          ok_a == [] and ok_r == [] and len(bad_a) == 1 and "позиция 1: награда — предмет A1: 31001 не стопочный, количество 4" in bad_a[0]
          and len(bad_r) == 1 and "количество 2" in bad_r[0], (ok_a, bad_a, bad_r))
    saved = Q.E.live_md5
    Q.E.live_md5 = lambda rels: (_ for _ in ()).throw(RuntimeError("нет SSH (самотест)"))
    try:
        un = shopcs.area_guard(cs, "apply")
    finally:
        Q.E.live_md5 = saved
    check("А4.5 перепроверка: таблицы стойки не прочитаны — причина «не прочитаны — вслепую не делается» (отказ)",
          len(un) == 1 and "не прочитаны" in un[0] and "вслепую" in un[0], un)


IT_GS = "ItemTable_Info" + BS + "item_table.txt"


def _put(raw, md5, rel, b):
    raw[rel], md5[rel] = b, _md5(b)


def _stack31002(raw, md5, cli, on):
    """31002 (штучный расходник сумки 2, ток.3 = 4, ток.24 = 1, на руках нет) — сделать стопочным (on) или вернуть штучным во всех GS
    и в карточке клиента."""
    from domains.cs_kinds import itemdata as I
    for g in GS3:
        rel = g + BS + IT_GS
        ln = [x for x in raw[rel].split(b"\r\n") if x.startswith(b"31002 ")][0]
        f = ln.split(b"\t")
        f[23] = b"1 " if on else b"0 "
        _put(raw, md5, rel, raw[rel].replace(ln, b"\t".join(f)))
    cli.itemcard[31002] = list(cli.itemcard[31002])
    cli.itemcard[31002][I.CARD["stack"]] = 1 if on else 0


def _repay_with(raw, md5, i1):
    for g in GS3:
        rows = [_repay_row(1, gold=100, exp=50, i1=i1), _repay_row(2, gold=5 if g == "Indun_GameServer" else 0, exp=10, b=1, i4=(31000, 1)),
                _repay_row(3, gold=7, exp=7)]
        rows = rows[:2] if g == "Indun_GameServer" else rows
        _put(raw, md5, g + BS + REPAY_REL, _crlf([str(len(rows))] + rows))


def _offline_r37(check, raw, md5, cli):
    """★ ревизия 37: Б-1 (итог набора и перепроверка с правками набора), М-1 (смена стопки против наград и доски), М-2 (вес награды),
    М-3 (флаг 0 и счётчик ≥ нового лимита), К-1 (QuestId клиента), К-3 (поля TAB = слова)."""
    from domains import shopcs
    keep = dict(raw), dict(md5)
    card = list(cli.itemcard[31002])
    try:
        # ---- Б-1, сценарий 1: стопка 1 → 0 в том же наборе — отказ при любом порядке позиций и перед выкладкой
        _stack31002(raw, md5, cli, True)
        rew, ist = ("quest.reward", {"rid": 1, "fields": {"item1": 31002, "item1n": 5}}), ("item.set", {"code": 31002, "fields": {"stack": 0}})
        res = []
        for items in ([rew, ist], [ist, rew]):
            e = _ev(items)
            pr = {r["kind"]: r["errors"] for r in e.positions}
            res.append(any("31002 не стопочный, количество 5" in x for x in pr["quest.reward"])
                       and any("смена стопки" in x and "RepayTable 1 A1 × 5" in x for x in pr["item.set"]))
        cs = _cs_man(_ev([rew, ist]), 9902, [rew, ist])
        bad = shopcs.area_guard(cs, "apply")
        check("ревизия 37 Б-1 (сценарий 1): награда 31002 × 5 и стопка 31002 1 → 0 в одном наборе — отказ обеим позициям при любом порядке "
              "(проверка по ИТОГОВОЙ item_table, а не на момент позиции); перепроверка перед выкладкой по «живая + правки набора» — тоже отказ",
              all(res) and any("позиция 1: награда — предмет A1: 31002 не стопочный, количество 5" in x for x in bad)
              and any(x.startswith("позиция 2: смена стопки") for x in bad), (res, bad))
        # ---- Б-1, сценарий 2: 31002 становится стопочным в том же наборе — проходит и проверку, и перепроверку
        _stack31002(raw, md5, cli, False)
        rew, ist = ("quest.reward", {"rid": 1, "fields": {"item1": 31002, "item1n": 5}}), ("item.set", {"code": 31002, "fields": {"stack": 1}})
        e1, e2 = _ev([rew, ist]), _ev([ist, rew])
        cs = _cs_man(e1, 9903, [rew, ist])
        ga, gr = shopcs.area_guard(cs, "apply"), shopcs.area_guard(cs, "rollback")
        os.remove(shopcs.manifest_path(9903))
        gn = shopcs.area_guard(cs, "apply")
        check("ревизия 37 Б-1 (сценарий 2): 31002 становится стопочным + награда 31002 × 5 — без ошибок при любом порядке позиций; "
              "перепроверка выкладки по манифесту (item_table набора — стопочный) и отката (база — прежняя награда 31001 × 2) — пусто; "
              "нет манифеста сухого прогона — «не прочитаны» (отказ)",
              not _errs(e1) and not _errs(e2) and ga == [] and gr == [] and len(gn) == 1 and "не прочитаны" in gn[0] and "server-dry" in gn[0],
              (_errs(e1), _errs(e2), ga, gr, gn))
        # ---- М-1: смена стопки «Предметов» против наград RepayTable (все GS) и предметов доски
        _stack31002(raw, md5, cli, True)
        _repay_with(raw, md5, (31002, 3))
        for g in GS3:
            for s in LQ_GS:
                _put(raw, md5, g + BS + s, raw[g + BS + s].replace(b"\t0\t31001\t-1", b"\t0\t31002\t-1"))
        for n in NPC3:
            for s in LQ_NPC:
                _put(raw, md5, n + BS + s, raw[n + BS + s].replace(b"\t0\t31001\t-1", b"\t0\t31002\t-1"))
        e = _ev([("item.set", {"code": 31002, "fields": {"stack": 0}})])
        ew = _ev([("item.set", {"code": 31002, "fields": {"weight": 6}})])
        er = e.positions[0]["errors"]
        check("ревизия 37 М-1: стопка 31002 1 → 0 при награде 31002 × 3 (запись 1 у всех GS) и цели доски 20000 31002 × 5 — отказ со списком "
              "(«RepayTable 1 A1 × 3 [3 GS]», «LimitationQuest 20000 +142.1 × 5»); вес того же кода — без отказа",
              len(er) == 1 and "RepayTable 1 A1 × 3 [GameServer/Indun_GameServer/Ch2_GameServer]" in er[0]
              and "LimitationQuest 20000 +142.1 × 5" in er[0] and "; " not in er[0] and not _errs(ew), (er, _errs(ew)))
        raw.clear(), raw.update(keep[0]), md5.clear(), md5.update(keep[1])
        # М-1 перед выкладкой: награда 31002 × 3 появилась ПОСЛЕ проверки (другой набор) — отказ; при откате — тоже
        _stack31002(raw, md5, cli, True)
        it0 = ("item.set", {"code": 31002, "fields": {"stack": 0}})
        e = _ev([it0])
        cs = _cs_man(e, 9904, [it0])
        ok0 = shopcs.area_guard(cs, "apply")
        _repay_with(raw, md5, (31002, 3))
        late = shopcs.area_guard(cs, "apply")
        raw.clear(), raw.update(keep[0]), md5.clear(), md5.update(keep[1])
        cli.itemcard[31002] = list(card)
        it1 = ("item.set", {"code": 31002, "fields": {"stack": 1}})
        e = _ev([it1])
        cs = _cs_man(e, 9905, [it1])
        man = json.load(open(shopcs.manifest_path(9905), encoding="utf-8"))
        for rel, f in man["files"].items():                    # как после выкладки: на стойке — файлы набора, база — в .bak_<метка>
            _put(raw, md5, rel + ".bak_" + man["tag"], raw[rel])
            _put(raw, md5, rel, open(f["local"], "rb").read())
        _repay_with(raw, md5, (31002, 3))                      # после выкладки другой набор дал награду 31002 × 3 (стопочный)
        rb = shopcs.area_guard(cs, "rollback")
        check("ревизия 37 М-1 (перепроверка): смена стопки без наград — пусто; награда 31002 × 3 появилась после проверки — выкладка отказ "
              "«позиция 1: смена стопки … RepayTable 1 A1 × 3»; откат вернул бы 31002 штучным при такой награде — причина (второе "
              "подтверждение)", ok0 == [] and len(late) == 1 and late[0].startswith("позиция 1: смена стопки")
              and "RepayTable 1 A1 × 3" in late[0] and len(rb) == 1 and "RepayTable 1 A1 × 3" in rb[0], (ok0, late, rb))
        raw.clear(), raw.update(keep[0]), md5.clear(), md5.update(keep[1])
        cli.itemcard[31002] = list(card)
        # ---- М-2: вес награды
        e1 = _ev([("quest.reward", {"rid": 1, "fields": {"item1n": 40}})])
        p1 = e1.positions[0]
        e2 = _ev([("quest.reward", {"rid": 1, "fields": {"item2": 31002, "item2n": 1}})])
        e3 = _ev([("quest.reward", {"rid": 1, "fields": {"item1n": 2000}})])
        e4 = _ev([("item.set", {"code": 31000, "fields": {"weight": 1000}})])
        p4 = e4.positions[0]
        check("ревизия 37 М-2: вес награды — строка «вес награды: 46 → 920»; тяжелее самой тяжёлой в данных (683, награда 2) — предупреждение "
              "и сильная правка kind weight; второй предмет — предупреждение о частичной выдаче и повторной сдаче; вес слота 46000 > 32767 — "
              "отказ; вес предмета награды 31000 683 → 1000 — предупреждение и сильная правка у позиции «Предметов»",
              not e1.errors and any("вес награды: 46 → 920" in x for x in p1["lines"])
              and any("больше самой тяжёлой награды в данных (683, награда 2)" in w for w in p1["warnings"])
              and any(b["kind"] == "weight" and b["strong"] for b in e1.summary()["balance"])
              and not e2.errors and any("вес награды 1 растёт 46 → 51" in w and "предметов в награде 2" in w for w in e2.positions[0]["warnings"])
              and any("вес слота 46000 больше 32767" in x for x in _errs(e3))
              and not e4.errors and any("RepayTable 2: 683 → 1000" in w for w in p4["warnings"])
              and any(b["kind"] == "weight" and b["strong"] for b in e4.summary()["balance"]),
              (e1.errors, p1.get("lines"), p1["warnings"][-2:], e2.positions[0]["warnings"][-1:], _errs(e3), e4.errors, p4["warnings"]))
        # ---- М-3: флаг 0 и счётчик ≥ нового лимита
        w4 = _ev([("board.quest", {"quest": 20000, "fields": {"max": 4}})]).positions[0]["warnings"]
        w5 = _ev([("board.quest", {"quest": 20000, "fields": {"max": 5}})]).positions[0]["warnings"]
        check("ревизия 37 М-3: лимит 3 → 4 — предупреждение «сдано уже не меньше нового лимита 4» со списком (Zero, сдано 4, флаг 0); лимит 5 — "
              "нет (сдано 4 < 5)", any("сдано уже не меньше нового лимита 4" in w and "Zero (75005/1, ур. 33, сдано 4)" in w for w in w4)
              and not any("не меньше нового лимита" in w for w in w5), (w4, w5))
        # ---- К-1: окно наград клиента запись к заданию не привязывает / другой шаг
        cli.qreward[1][1] = -1
        wq = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})]).positions[0]["warnings"]
        cli.qreward[1][1], cli.qreward[1][2] = 7, 4
        ws = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})]).positions[0]["warnings"]
        cli.qreward[1][2] = 1
        w0 = _ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})]).positions[0]["warnings"]
        check("ревизия 37 К-1: у клиента QuestId −1 — предупреждение «не привязывает … сервер даёт её за 7/1»; другой шаг — «к шагу 4 "
              "задания 7»; пара совпадает — без предупреждения", any("не привязывает (QuestId -1, шаг 1)" in w and "7/1" in w for w in wq)
              and any("к шагу 4 задания 7" in w for w in ws) and not any("окно наград клиента" in w for w in w0), (wq, ws))
        # ---- К-3: поле TAB из двух слов (число слов прежнее) — отказ, а не правка чужого токена
        rel = "GameServer" + BS + LQ_GS[0]
        _put(raw, md5, rel, raw[rel].replace(b"\t31001\t-1\t-1\t", b"\t31001 -1\t\t-1\t", 1))
        eb = _errs(_ev([("board.quest", {"quest": 20000, "fields": {"exp": 1200}})]))
        raw.clear(), raw.update(keep[0]), md5.clear(), md5.update(keep[1])
        rel = "GameServer" + BS + REPAY_REL
        _put(raw, md5, rel, raw[rel].replace(b"\t-1\t0\t31001\t2\t", b"\t-1 0\t\t31001\t2\t", 1))
        er = _errs(_ev([("quest.reward", {"rid": 1, "fields": {"gold": 120}})]))
        check("ревизия 37 К-3: доска и RepayTable — поле TAB из двух слов при прежнем числе слов — отказ «поля TAB не совпадают со словами "
              "сервера»", any("поля TAB не совпадают со словами сервера" in x for x in eb) and any("поля TAB не совпадают" in x for x in er),
              (eb, er))
    finally:
        raw.clear(), raw.update(keep[0]), md5.clear(), md5.update(keep[1])
        cli.itemcard[31002] = card


def _offline_tr(check):
    from core import i18n
    samples = [
        "награда 3: опыт: 150 → 45; золото: 400 → 80 (сервер RepayTable ×3 GS, клиент RewardTable + DT_QuestRewardTable)",
        "задание 2 «Q» сейчас взято (4 перс.): testttt (1/12, ур. 4, шаг 0); Oro (75205/10, ур. 6, шаг 0); и ещё 3 — ход задания правка не "
        "меняет, при сдаче они получат новую награду",
        "даёт: 2 «Q», шаг 1 (завершить); 5 «X», шаг 0 (шаг)",
        "позиция 1: награда — предмет B1 (на выбор у клиента): 36753 не стопочный, количество 2 — сервер выдаёт ОДНУ вещь и количество не "
        "читает (sub_45DEE0), клиент показал бы 2",
        "уже расходились (клиент ≠ сервер): опыт: клиент 4000, сервер 1000; предмет A1: клиент 1, сервер 2 — правка ставит обоим новое значение",
        "после проверки набора изменились данные стойки (позиция 1: награда — предмет A1: предмета 41782 нет на сервере (item_table / "
        "Function_Table / Cellob_Table)) — выкладка не делается, стойка не тронута, объявления не было",
        "доска, задание 20000: опыт: 10000 → 11000; мин. уровень: 36 → 35 (сервер LimitationQuest ×12 копий, клиент DT_RaidQuestData + ведомость)",
        "копия Indun_NpcServer\\Quest\\LimitationQuest.txt: задание 20000 другое, чем в GameServer\\NpcData_Info\\LimitationQuest.txt — копии "
        "разошлись, правка не однозначна",
        "награда 3: предмет A1 41782 → 20571", "доска 20000: лимит раз", "было: ур. 36…100, лимит 0, опыт 10000, золото 7000 (тип 0)",
        "задание доски 20000 сейчас взято (1 перс.): Bob (75003/2, ур. 15, флаг 1) — уровни сервер проверяет только при взятии, награду — "
        "при сдаче (новую)",
        "откат вернёт данные, которые по живым таблицам стойки не проходят проверку (позиция 1: награда — предмет A1: 31001 не стопочный, "
        "количество 2 — сервер выдаёт ОДНУ вещь и количество не читает (sub_45DEE0), клиент показал бы 2) — нужно второе подтверждение "
        "владельца (ключ --held-ok)",
        # ★ мелочь ревизии 36: отказ Б-1 с НЕСКОЛЬКИМИ кодами — сведения «на руках» переводятся у каждого (коды через «; »)
        "после проверки набора у игроков появились коды со сменой стопки или веса стопки (31002 — записей 2, сумма Amount 0, наибольшая "
        "стопка 0 (Item 2); 31001 — записей 3, сумма Amount 900, наибольшая стопка 600 (Item 2, ItemPostBox 1)): строки Joy1 после рестарта "
        "значили бы другое (дюп или потеря) — выкладка не делается, стойка не тронута, объявления не было",
        "после выкладки у игроков есть коды со сменой стопки или веса стопки (31002 — записей 3, сумма Amount 40, наибольшая стопка 20 "
        "(Item 3); 31001 — записей 1, сумма Amount 5, наибольшая стопка 5 (gifts 1)): после отката строки Joy1 значили бы другое (стопка "
        "стала бы штучной вещью или наоборот, вес строки разошёлся бы) — нужно второе подтверждение владельца (ключ --held-ok)",
        "Задание: награда (RepayTable + RewardTable клиента)", "задания: награды сервер ≠ клиент (RepayTable ↔ RewardTable)",
        # ★ ревизия 37: новые тексты и К-4 (номер записи, запасной «нет связи с Joy1»)
        "кто держит задание сейчас — не прочитано (нет связи с Joy1)",
        "копия Indun_GameServer: у записи 2 номер 7 — сервер берёт ПОРЯДОК записи",
        "позиция 2: смена стопки x31002 (31002): награды и цели доски с этим предметом и количеством больше 1 (RepayTable 1 A1 × 5 "
        "[GameServer/Ch2_GameServer], LimitationQuest 20000 +142.1 × 5) стали бы выдавать или принимать ОДНУ вещь — у нестопочного сервер "
        "количество не читает (sub_45DEE0, sub_5340B0, RecvUser_LimitationQuestResult), окно наград показало бы количество — сначала "
        "поставьте в них количество 1, правка не делается",
        "после проверки набора изменились данные стойки (позиция 1: смена стопки x31002 (31002): награды и цели доски с этим предметом и "
        "количеством больше 1 (RepayTable 1 A1 × 3) стали бы выдавать или принимать ОДНУ вещь — у нестопочного сервер количество не читает "
        "(sub_45DEE0, sub_5340B0, RecvUser_LimitationQuestResult), окно наград показало бы количество) — выкладка не делается, стойка не "
        "тронута, объявления не было",
        "вес награды 1 растёт 46 → 920: предметов в награде 2: при перегрузе сервер выходит посреди выдачи — уже выданные остаются, задание "
        "не сдано, сдачу можно повторить и снова получить их (sub_45DEE0, sub_4D7CD0, GameServer.c:37903); больше самой тяжёлой награды в "
        "данных (683, награда 2) — персонажу с обычной загрузкой может не влезть, сильная правка",
        "вес награды: 46 → 920 (самая тяжёлая награда в данных — 683, награда 2)", "награда 1: вес награды",
        "позиция 1: награда — предмет A1: вес слота 46000 больше 32767 — сервер передаёт его проверке перегруза как __int16 (sub_4D7CD0) и "
        "прибавляет к весу персонажа младшее слово (sub_43F880), вес разошёлся бы, правка не делается",
        "вес наград заданий с x31000 (31000) растёт: RepayTable 2: 683 → 1000 — при перегрузе сервер выходит посреди выдачи (sub_45DEE0, "
        "sub_4D7CD0), самая тяжёлая награда в данных — 683",
        "у 1 перс. сдано уже не меньше нового лимита 4 (флаг 0): Zero (75005/1, ур. 33, сдано 4) — сервер не даст им взять задание 20000 "
        "(код 5) до сброса периода",
        "окно наград клиента запись 533 к заданию не привязывает (QuestId -1, шаг 0), сервер даёт её за 21/1 — клиентскую половину игрок не "
        "увидит",
        "окно наград клиента привязывает запись 1 к шагу 4 задания 7, а сервер даёт её на шаге 1 — окно может показать её не на том шаге",
        "позиция 1: поля TAB не совпадают со словами сервера (GameServer\\NpcData_Info\\LimitationQuest.txt #20000, поле 8 — не одно слово), "
        "правка не делается", "позиция 1: смена стопки: награды заданий не прочитаны (ssh timeout) — вслепую не делается"]
    i18n.set_lang("en")
    try:
        tr = [i18n.tr(x) for x in samples]
    finally:
        i18n.set_lang("ru")
    left = [(a, b) for a, b in zip(samples, tr) if a == b or re.search("[А-Яа-яЁё]{3}", b.replace("«Q»", "").replace("«X»", ""))]
    check("А4.5 переводы службы: позиции, отказы, перепроверка, баланс — EN без русского; отказ Б-1 с двумя кодами переводит «на руках» у "
          "обоих (мелочь ревизии 36)", not left, left[:2])
    from domains.cs_kinds import itemdata as I
    from domains import shopdata as SD
    saved = SD.held_counts
    SD.held_counts = lambda codes, stack=None: {int(c): {"rows": 1, "amount": 2, "max": 2, "stack": True, "where": {"Item": 1}} for c in codes}
    try:
        _c, busy = I.held_guard({"items": [{"pos": 1, "kind": "item.set", "params": {"code": 31001, "fields": {"stack": 1}}},
                                           {"pos": 2, "kind": "item.set", "params": {"code": 31002, "fields": {"weight": 3}}}], "check": {}})
    finally:
        SD.held_counts = saved
    check("ревизия 36 (мелочь): itemdata.held_guard разделяет коды «; » — вложенный перевод режет по «; »",
          busy and busy.count("; ") == 1 and busy.startswith("31001 — записей 1"), busy)
    # веб
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "questdata.js"), encoding="utf-8").read()
    en = open(os.path.join(root, "web", "i18n.js"), encoding="utf-8").read()
    STR = r'"((?:[^"\\]|\\.)*)"'
    have = set(re.findall(STR + r"\s*:", en))
    need = {x for x in re.findall(r"T\(" + STR, js)} | {x for x in re.findall(STR, js) if re.search("[А-Яа-яЁё]", x)}
    miss = sorted(need - have)
    block = en.split("// А4.5 20.11", 1)[1] if "// А4.5 20.11" in en else ""
    keys = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", block, re.M)
    from domains.cs_kinds import questtables as Q
    labels = [v[2] for v in Q.REWARD.values()] + [v[2] for v in Q.BOARD.values()]
    check("А4.5 веб: questdata.js подключён (index.html, вкладка и маршрут в shops.js), все его строки и подписи полей есть в I18N_EN, в "
          "блоке А4.5 нет дублей", "/questdata.js" in open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
          and "#/shops/quests" in open(os.path.join(root, "web", "shops.js"), encoding="utf-8").read() and not miss
          and keys and len(keys) == len(set(keys)) and all('"%s":' % x in en for x in labels), miss[:5])


def _ledger_board(check):
    from domains.cs_kinds import texts as TX
    BQ = TX._tool("asda_import_board_quests")
    rows = [{"QuestId": 20000, "LevelMin": 10, "LevelMax": 100, "MaxCount": 0, "Exp": 5, "Gold": 6}]
    d = tempfile.mkdtemp(prefix="asda_q_led_")
    try:
        p = os.path.join(d, "v.json")
        none = BQ.apply_values([dict(r) for r in rows], os.path.join(d, "нет.json"))
        json.dump({"rows": [{"quest": 20000, "field": "Exp", "was": 5, "now": 9}]}, open(p, "w", encoding="utf-8"))
        rr = [dict(r) for r in rows]
        n = BQ.apply_values(rr, p)
        json.dump({"rows": [{"quest": 20000, "field": "Exp", "was": 4, "now": 9}]}, open(p, "w", encoding="utf-8"))
        try:
            BQ.apply_values([dict(r) for r in rows], p)
            stop = False
        except ValueError:
            stop = True
    finally:
        shutil.rmtree(d, ignore_errors=True)
    check("импортёр доски: ведомость чисел board_quest_values.json — нет файла: без изменений; строка ложится (Exp 5 → 9); was ≠ — останов "
          "импорта (ValueError), а не молчаливая потеря", none == 0 and n == 1 and rr[0]["Exp"] == 9 and stop)


def _plan_real(check):
    """План клиента на ВРЕМЕННЫХ копиях настоящих файлов порта с НАСТОЯЩИМИ импортёрами."""
    from domains import shopdata as SD
    from domains.cs_kinds import questtables as Q, texts as TX
    keys = ("qreward_bin", "qreward_json", "board_json", "board_values")
    real = {k: SD.CLIENT_FILES[k] for k in keys}
    if not all(os.path.isfile(real[k]) for k in keys[:3]):
        return check("А4.5 план клиента настоящими импортёрами — файлы порта есть", False, real)
    before = {p: SD.md5f(p) for p in real.values() if os.path.isfile(p)}
    d = tempfile.mkdtemp(prefix="asda_q_plan_")
    try:
        for k in keys[:3]:
            shutil.copy2(real[k], os.path.join(d, os.path.basename(real[k])))
            SD.CLIENT_FILES[k] = os.path.join(d, os.path.basename(real[k]))
        SD.CLIENT_FILES["board_values"] = os.path.join(d, "board_quest_values.json")
        QR = TX._tool("asda_import_quest_reward_table")
        rew = {r["RecordIndex"]: r for r in Q._quiet(QR.read_rewards, SD.CLIENT_FILES["qreward_bin"])}
        r3 = rew[3]
        brd = json.loads(open(SD.CLIENT_FILES["board_json"], encoding="utf-8").read())[0]
        edits = [{"type": "qreward_set", "file": "qreward_bin", "rid": 3, "fields": {"Money": [r3["Money"], r3["Money"] + 1],
                                                                                    "ItemCount1": [r3["ItemCount1"], r3["ItemCount1"] + 1]}},
                 {"type": "board_set", "file": "board_json", "quest": brd["QuestId"], "fields": {"Exp": [brd["Exp"], brd["Exp"] + 1]}}]
        plan = SD.client_plan(edits, 0)
        led = json.loads(plan["_bytes"][SD.CLIENT_FILES["board_values"]].decode("utf-8"))
        jj = {j["dt"]: j for j in plan["json_jobs"]}
        ok = (not plan["errors"] and set(plan["files"]) == {SD.CLIENT_FILES[k] for k in keys}
              and led["rows"] == [{"quest": brd["QuestId"], "field": "Exp", "was": brd["Exp"], "now": brd["Exp"] + 1, "source": "admin_center",
                                   "reason": led["rows"][0]["reason"]}]
              and len(jj[Q.DT_QREWARD]["edits"]) == 2 and jj[Q.DT_BOARD]["edits"][0]["now"] == brd["Exp"] + 1)
        # сторож правки владельца: JSON правили мимо BIN — отказ
        js = open(SD.CLIENT_FILES["qreward_json"], "rb").read()
        open(SD.CLIENT_FILES["qreward_json"], "wb").write(js.replace(b'"Exp": ', b'"Exp": 9', 1))
        p2 = SD.client_plan(edits[:1], 0)
        open(SD.CLIENT_FILES["qreward_json"], "wb").write(js)
        bj = open(SD.CLIENT_FILES["board_json"], "rb").read()
        open(SD.CLIENT_FILES["board_json"], "wb").write(bj.replace(b'"Gold": ', b'"Gold": 1', 1))
        p3 = SD.client_plan(edits[1:], 0)
        open(SD.CLIENT_FILES["board_json"], "wb").write(bj)
        stale = [dict(edits[0], fields={"Money": [r3["Money"] + 7, r3["Money"] + 8]})]
        p4 = SD.client_plan(stale, 0)
    finally:
        for k in keys:
            SD.CLIENT_FILES[k] = real[k]
        shutil.rmtree(d, ignore_errors=True)
    after = {p: SD.md5f(p) for p in real.values() if os.path.isfile(p)}
    check("А4.5 план клиента (временные копии настоящих файлов, НАСТОЯЩИЕ импортёры): RewardTable.BIN + QuestRewardTable.json — импорт "
          "нового BIN даёт плановый JSON, ведомость board_quest_values.json заводится строкой «was → now», импорт доски с ней даёт плановый "
          "RaidQuestData.json, JSON-точки DT_QuestRewardTable (2 ячейки) и DT_RaidQuestData; сторожа: JSON наград ≠ импорту — отказ «мимо», "
          "JSON доски ≠ импорту — отказ, «было» устарело — отказ «пересоберите»; файлы порта md5 до = после",
          ok and any("мимо" in x for x in p2["errors"]) and any("мимо" in x or "импорту" in x for x in p3["errors"])
          and any("пересоберите" in x for x in p4["errors"]) and before == after, (plan["errors"], p2["errors"], p3["errors"], p4["errors"]))


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox(check, ldb):
    """Набор «Задания» целиком: пара сервер + клиент, второе подтверждение сильной правки, перепроверка, выкладка и откаты."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs, shopdata as SD
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    keys = ("qreward_bin", "qreward_json", "board_json", "board_values")
    real = {k: SD.CLIENT_FILES[k] for k in keys}
    if not all(os.path.isfile(real[k]) for k in keys[:3]):
        return check("песочница А4.5 — файлы порта есть", False, real)
    real_md5 = {p: SD.md5f(p) for p in real.values() if os.path.isfile(p)}
    with X.sandbox(ldb) as (st, env), _Patch():
        files = stack_files()
        for rel, b in files.items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        cdir = os.path.join(env["tmp"], "a45")
        os.makedirs(cdir)
        for k in keys[:3]:
            dst = os.path.join(cdir, os.path.basename(real[k]))
            shutil.copy2(real[k], dst)
            SD.CLIENT_FILES[k] = dst
        SD.CLIENT_FILES["board_values"] = os.path.join(cdir, "board_quest_values.json")
        orig = {SD.CLIENT_FILES[k]: open(SD.CLIENT_FILES[k], "rb").read() for k in keys[:3]}
        jp = []
        real_ue = shopcs._ue_run

        def ue_run(script, log, marker, env=None, expect=None, require=None):
            if script == "asda_dt_json_point.py":
                jobs = json.load(open(env["ASDA_JP_JOBS"], encoding="utf-8"))
                if not env.get("ASDA_JP_DRYRUN"):
                    jp.append(jobs)
                return 0, "ЗАВЕРШЕНО: JSON-точечные DT"
            return real_ue(script, log, marker, env, expect, require)
        shopcs._ue_run = ue_run
        try:
            cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.5", note="самотест песочницы А4.5: задания")["result"]["id"]
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="quest.reward", params={"rid": 1, "fields": {"gold": 400, "item1n": 3}})
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="board.quest", params={"quest": 20000, "fields": {"exp": 1100}})
            X._run(ctx, "shop.cs_check", cs=cid)
            cs = shopcs.get(cid)
            _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
            adm = ops.Ctx(7, "adm", "admin", "100.64.0.9", "web")
            _r, adm_no = X._try(adm, "shop.cs_approve", cs=cid, balance_ok="balance")
            X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
            check("песочница А4.5: пара (сервер и клиент), сильная правка (золото ×4) — без второго подтверждения отказ, admin с ключом — отказ "
                  "«только владелец», владелец — утверждён", cs["check"]["ok"] and cs["check"]["client_needed"] and cs["check"]["server_needed"]
                  and no and "второе подтверждение" in no and adm_no and "только владелец" in adm_no and shopcs.get(cid)["status"] == "approved",
                  (cs["check"]["errors"], no, adm_no))
            X._run(ctx, "shop.cs_server_dry", cs=cid)
            man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
            want = sorted([g + BS + REPAY_REL for g in GS3] + [g + BS + x for g in GS3 for x in LQ_GS] + [n + BS + x for n in NPC3 for x in LQ_NPC])
            check("песочница А4.5: сухой прогон НАСТОЯЩЕГО deploy_changeset — 15 файлов (RepayTable ×3 со своей базой Indun, LimitationQuest ×12)",
                  shopcs.get(cid)["server_state"] == "dry_ok" and sorted(man["files"]) == want
                  and man["files"]["Indun_GameServer" + BS + REPAY_REL]["base"] != man["files"]["GameServer" + BS + REPAY_REL]["base"],
                  sorted(man["files"]))
            X._run(ctx, "shop.cs_client_dry", cs=cid)
            X._run(ctx, "shop.cs_client_apply", cs=cid)
            led = json.load(open(SD.CLIENT_FILES["board_values"], encoding="utf-8"))
            dts = sorted(j["dt"] for jobs in jp for j in jobs)
            check("песочница А4.5: клиент — RewardTable.BIN, QuestRewardTable.json, RaidQuestData.json записаны, ведомость чисел доски заведена "
                  "(Exp → 1100), JSON-точки DT_QuestRewardTable и DT_RaidQuestData отправлены очередью UE",
                  shopcs.get(cid)["client_state"] == "applied" and led["rows"][0]["now"] == 1100
                  and all(open(p, "rb").read() != b for p, b in orig.items())
                  and dts == sorted(["/Game/AsdaAssets/Data/NPC/DT_QuestRewardTable", "/Game/AsdaAssets/Data/Quest/DT_RaidQuestData"]), (led, dts))
            # ★ урок ревизии 36 Б-1: после проверки предмет награды 31001 стал нестопочным (другой набор) — выкладка отказ ДО объявления
            rel = "GameServer" + BS + "ItemTable_Info" + BS + "item_table.txt"
            keep = open(st.path(rel), "rb").read()
            ln = [x for x in keep.split(b"\r\n") if x.startswith(b"31001 ")][0]
            f = ln.split(b"\t")
            f[23] = b"0 "
            open(st.path(rel), "wb").write(keep.replace(ln, b"\t".join(f)))
            calls0 = len(st.calls)
            g0 = open(st.path("GameServer" + BS + REPAY_REL), "rb").read()
            _r, e_g = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            open(st.path(rel), "wb").write(keep)
            check("песочница А4.5 (перепроверка): предмет награды стал нестопочным после проверки — выкладка отказ «изменились данные стойки "
                  "… объявления не было» (рестарта не было, RepayTable прежняя, состояние dry_ok)",
                  e_g and "изменились данные стойки" in e_g and "не стопочный" in e_g and len(st.calls) == calls0
                  and open(st.path("GameServer" + BS + REPAY_REL), "rb").read() == g0 and shopcs.get(cid)["server_state"] == "dry_ok", e_g)
            r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            gi = open(st.path("Indun_GameServer" + BS + REPAY_REL), "rb").read()
            lq = open(st.path("Ch2_NpcServer" + BS + LQ_NPC[1]), "rb").read()
            check("песочница А4.5: серверная половина выложена рестартом — у всех GS золото записи 1 = 400 и количество A1 = 3 (Indun: своя "
                  "запись 2 с золотом 5 сохранена), опыт задания доски 20000 = 1100 во всех 12 копиях",
                  r and shopcs.get(cid)["server_state"] == "applied" and _tok(gi, 0, 3) == b"400 " and _tok(gi, 0, 17) == b"3"
                  and _tok(gi, 1, 3) == b"5 " and _tok(lq, 0, 26) == b"1100", e)
            # откат: прежний предмет (2 шт.) стал нестопочным — без --held-ok отказ, с ключом владельцем — выполнен
            open(st.path(rel), "wb").write(keep.replace(ln, b"\t".join(f)))
            calls0 = len(st.calls)
            _r, e_r = X._try(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
            check("песочница А4.5 (перепроверка отката): откат вернул бы награду 31001 × 2, а он уже нестопочный — без второго подтверждения "
                  "отказ «--held-ok», рестарта не было", e_r and "--held-ok" in e_r and "не стопочный" in e_r and len(st.calls) == calls0
                  and shopcs.get(cid)["server_state"] == "applied", e_r)
            X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart", held_ok="held")
            open(st.path(rel), "wb").write(keep)
            X._run(ctx, "shop.cs_client_rollback", cs=cid)
            back = all(open(st.path(rel_), "rb").read() == b for rel_, b in files.items()) and all(open(p, "rb").read() == b for p, b in orig.items())
            check("песочница А4.5: откат владельцем с --held-ok (rolled_back) и откат клиента — 15 таблиц стойки, BIN и оба JSON вернулись, "
                  "ведомость доски убрана", back and shopcs.get(cid)["server_state"] == "rolled_back"
                  and not os.path.isfile(SD.CLIENT_FILES["board_values"]), shopcs.get(cid)["client_state"])
        finally:
            shopcs._ue_run = real_ue
            for k in keys:
                SD.CLIENT_FILES[k] = real[k]
    check("песочница А4.5: настоящие файлы порта (RewardTable.BIN, QuestRewardTable.json, RaidQuestData.json) — md5 до = после",
          real_md5 == {p: SD.md5f(p) for p in real.values() if os.path.isfile(p)})


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны на живой стойке (SSH) и живом порту (настоящие импортёры)."""
    from core import config
    from domains import shopcs, shopdata as SD
    from domains.cs_kinds import questtables as Q
    if config.get().on_server:
        return check("живой самотест А4.5 — с ПК (SSH и порт)", True)
    rels = [g + BS + REPAY_REL for g in GS3] + [f + BS + s for f, s in Q.board_copies()]
    md = SD.live_md5(rels)
    check("живая стойка А4.5: RepayTable — поле = Ch2, у Indun своя база; 12 копий LimitationQuest одинаковы",
          "none" not in md.values() and md["GameServer" + BS + REPAY_REL] == md["Ch2_GameServer" + BS + REPAY_REL]
          and len({md[f + BS + s] for f, s in Q.board_copies()}) == 1, {r: h[:8] for r, h in md.items()})
    cli = SD.Client.load(force=True)
    lr = Q.lookup_reward(3)
    lb = Q.lookup_board("20000")
    sr = Q.search("2")
    check("живая справка А4.5: награда 3 (3 GS, клиент, задания, кто держит из Joy1), доска 20000 (держат — из Joy1), поиск заданий",
          lr["server"]["GameServer"] and lr["client"] and lr["quests"] and lr["holders_error"] is None and lb["card"]["holders"] is not None
          and sr["rows"], (lr.get("holders_error"), lb["card"].get("holders_error")))
    r3 = cli.qreward[3]
    b0 = cli.board[20000]
    items = [{"pos": 1, "kind": "quest.reward", "params": {"rid": 3, "fields": {"gold": lr["server"]["GameServer"]["gold"] + 1}}},
             {"pos": 2, "kind": "board.quest", "params": {"quest": 20000, "fields": {"exp": b0["Exp"] + 1}}}]
    ev = SD.Eval(items, False, SD.Snap(), cli).run()
    s = ev.summary()
    check("живая оценка набора А4.5 (награда 3: золото +1, доска 20000: опыт +1): без ошибок, сервер — 15 файлов, клиент — 2 правки",
          not s["errors"] and s["server"]["count"] == 15 and len(s["client"]) == 2, s["errors"][:3])
    tracked = [p for p in (SD.CLIENT_FILES[k] for k in ("qreward_bin", "qreward_json", "board_json", "board_values")) if os.path.isfile(p)]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0)
    after = {p: SD.md5f(p) for p in tracked}
    check("живой план клиента А4.5: НАСТОЯЩИЕ импортёры подтверждают BIN → JSON наград и ведомость → JSON доски, JSON-точки двух DT; "
          "ничего не записано (md5 порта до = после)", not plan["errors"] and len(plan["json_jobs"]) == 2 and before == after
          and r3[3] + 0 == r3[3], plan["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_a45_live_")
    try:
        man = {"tag": "20261120_a45live", "changeset": 0, "files": {}}
        for rel, data in sorted(ev.new_bytes().items()):
            lp = os.path.join(tmp, rel.replace(BS, os.sep))
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            open(lp, "wb").write(data)
            man["files"][rel] = {"local": lp.replace(BS, "/"), "base": ev.snap.md5[rel], "new": SD.md5b(data)}
        mp = os.path.join(tmp, "manifest.json")
        json.dump(man, open(mp, "w", encoding="utf-8"))
        b0m = SD.live_md5(sorted(man["files"]))
        rc, out = shopcs.run_deploy(mp)
        b1m = SD.live_md5(sorted(man["files"]))
        check("НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH (15 файлов: RepayTable ×3, LimitationQuest ×12): «всё готово к --apply», стойка "
              "не изменилась (md5 до = после)", rc == 0 and "всё готово" in out and b0m == b1m, (rc, out[-400:]))
        # ★ ревизия 37 Б-1: состояние перепроверки «живая + правки набора» по НАСТОЯЩЕМУ манифесту (выкладка) и «живая, файлы набора —
        #   базой» (откат); М-2: порог веса по живой RepayTable; М-3: запрос «флаг 0 и счётчик ≥ лимита» к Joy1 (только чтение)
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tmp
        try:
            cs = {"id": 9937, "items": items, "check": s}
            _mp, mman = shopcs.build_server_out(cs, ev)
            sa, _sn = Q._guard_state(cs, "apply")
            sr_, _sn2 = Q._guard_state(cs, "rollback")
        finally:
            SD.CS_DIR = saved_dir
        rg = "GameServer" + BS + REPAY_REL
        rit = "GameServer" + BS + "ItemTable_Info" + BS + "item_table.txt"
        top = Q.weight_top(ev)
        bh = Q.board_holders([20000 + k for k in range(57)], min_count=1)
        check("живая перепроверка ревизии 37: выкладка — RepayTable из манифеста набора (md5 = новому), item_table живая; откат — RepayTable "
              "живая (база); порог веса по живой RepayTable > 0 и строка «вес награды» у позиции; запрос доски с флагом 0 и счётчиком "
              "к Joy1 прочитан", SD.md5b(sa[rg]) == mman["files"][rg]["new"] and SD.md5b(sa[rit]) == SD.live_md5([rit])[rit]
              and SD.md5b(sr_[rg]) == SD.live_md5([rg])[rg] and top[0] > 0
              and any(x.startswith("вес награды:") for x in ev.positions[0].get("lines") or []) and bh is not None,
              (top, Q.board_holders.last_error, ev.positions[0].get("lines")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
