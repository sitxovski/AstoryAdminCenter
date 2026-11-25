# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_titles_a4.py — самотест шага А4.6 «Звания» (20.11.2026, domains/cs_kinds/titledata.py).

offline(check)       — подменная стойка selftest_shops.synthetic() + свои FameInfo.txt трёх GS (у Indun своя база: другие очки звания 7 и
                       цель звания 10), клиентский снимок title_list, подставные держатели (Joy1): очки, включено, условия (поля, которые
                       сервер читает, по веткам sub_54B260), бонусы; отказы (держатели при выключении и смене кода бонуса, рейтинговые,
                       РАВЕНСТВО 47…55, параметр 19 / 35…37, поле не читается, цель 0, цикл > 1280, уровень звания 2, отличия Indun),
                       итог набора (after_run: новая неисправность копии), перепроверка перед выкладкой и откатом по «живая + файлы
                       набора» (apply_guard), AsdaFamePoints после выкладки (after_server, подставной asda_ops), расхождения, справка,
                       переводы службы и веба, план клиента (ведомость _value_overlay/title_list.csv, подставной генератор), попутно —
                       цели условий заданий у «Предметов» (itemdata.cond_uses / cond_warn).
sandbox(check, ldb)  — путь набора целиком: создать → проверить → утвердить (сильная — второе подтверждение) → НАСТОЯЩИЙ сухой прогон
                       deploy_changeset (FameInfo ×3, база Indun своя) → клиент (копия title_list.csv, ведомость, DT подставной очередью
                       UE) → выкладка (держатель появился у выключаемого звания — отказ до объявления) → выкладка → AsdaFamePoints →
                       откат сервера и клиента (всё вернулось).
live(check)          — только чтение и сухие прогоны: md5 трёх копий, справка (держатели из Joy1), живая оценка набора, план клиента
                       с НАСТОЯЩИМ генератором ItemDB (md5 порта до = после), НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH.
Ни рестартов стойки, ни записи в таблицы стойки или порта, ни записи в Joy1. Побочных эффектов при импорте нет.
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
FAME_REL = "ConfigSet" + BS + "FameInfo.txt"
N = 70
HOLD = {0: [(75001, 1, "Alice", 20, False)], 3: [(75002, 2, "Bob", 30, True)], 66: [(75003, 1, "Top", 50, False)]}
PROG = {0: [(75004, 1, "Carl", 12, 450)]}


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _tn(tid):
    from domains import titles as TT
    return TT.title_name(tid)


def _rec(i, indun=False):
    v = [i, 0, 0, 1, 0, -1, -1, -1, -1, -1, -1, -1] + [0] * 30 + [5, 1, 1, 0]
    if i in (0, 2, 3, 7, 10, 19, 21, 29, 35, 47, 66, 20, 25, 26):
        v[1] = 2
    if i == 29:
        v[10] = 26                         # ★ р38 М-2: 26 — «следующее» записи 29 (выключение — отказ)
    if i == 30:
        v[11] = 40                         # ★ р38 М-2: 40 выключено, но его выдаёт набор 30 (строка расхождений)
    if i == 0:
        v[3], v[43], v[44], v[42] = 500, 1, 10, 32
    if i == 2:
        v[3], v[4] = 30, 10
    if i == 3:
        v[12], v[13], v[14] = 65, 1, 3
    if i == 7:
        v[42] = 12 if indun else 9
    if i == 10:
        v[3], v[43] = (0 if indun else 5), 1
    if i == 21:
        v[3] = 30
    if i == 29:
        v[3], v[4] = 50, 50
    if i == 20:
        v[45] = 1
    if i == 66:
        v[42] = 188
    s = ["%d" % x for x in v]
    s[3] = s[3] + " "                      # хвостовой пробел у числа — как в живом файле (114 таких слов)
    return "\t".join(s)


def fame_file(indun=False):
    return ("\r\n".join([str(N)] + [_rec(i, indun) for i in range(N)]) + "\r\n").encode("latin-1")


def stack_files():
    return {g + BS + FAME_REL: fame_file(indun=g == "Indun_GameServer") for g in GS3}


def cli_titles():
    out = {}
    for i in range(N):
        f = [int(x) for x in _rec(i).split("\t")]
        out[i] = [i, f[1], f[42]] + [f[12 + 5 * m] if f[12 + 5 * m] >= 65 else 0 for m in range(6)] + [1] * 6
    return out


class _Hold:
    """Подмена держателей (Joy1) на время блока; extra — держатели, «появившиеся после проверки»."""

    def __init__(self, extra=None, fail=False, fp=None):
        self.extra, self.fail, self.fp = dict(extra or {}), fail, fp

    def __enter__(self):
        from domains.cs_kinds import titledata as TD
        self.saved = (TD.holders, TD.progress, TD.fame_points_db)
        me = self

        def fame_points_db():                 # ★ р38 К-4: AsdaFamePoints (по умолчанию = кол. 42 GameServer)
            fame_points_db.last_error = None
            return dict(me.fp) if me.fp is not None else {i: int(_rec(i).split("\t")[42]) for i in range(N)}
        fame_points_db.last_error = None
        TD.fame_points_db = fame_points_db

        def holders(ids):
            if me.fail:
                holders.last_error = "нет связи с Joy1 (самотест)"
                return None
            holders.last_error = None
            src = dict(HOLD)
            src.update(me.extra)
            return {int(i): list(src.get(int(i), [])) for i in ids}
        holders.last_error = None

        def progress(tid, target):
            progress.last_error = None
            return [x for x in PROG.get(int(tid), []) if x[4] >= target]
        progress.last_error = None
        TD.holders, TD.progress = holders, progress
        return self

    def __exit__(self, *a):
        from domains.cs_kinds import titledata as TD
        TD.holders, TD.progress, TD.fame_points_db = self.saved
        return False


def _ev(items):
    from domains import shopdata as SD
    return SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False).run()


def _errs(ev):
    return [e for r in ev.positions for e in r["errors"]]


def _line(raw, k):
    return raw.split(b"\r\n")[1 + k].split(b"\t")


def _cs_man(e, cid, items):
    from domains import shopcs
    cs = {"id": cid, "items": [{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], "check": e.summary()}
    _mp, m = shopcs.build_server_out(cs, e)
    cs["server_tag"] = m["tag"]
    return cs, m


class _FakeWriter:
    """Подставной db.GameWriter (asda_ops): AsdaFamePoints в памяти."""
    table = {}
    updates = []

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def rows(self, sql, params=()):
        return [{"FameIdx": k, "Point": v} for k, v in sorted(_FakeWriter.table.items())]

    force = {}                                # ★ р38 К-4: {FameIdx: rowcount} — «UPDATE затронул не одну строку»

    def execute(self, sql, params=()):
        v, k, was = params
        if k in _FakeWriter.force:
            return _FakeWriter.force[k]
        if _FakeWriter.table.get(k) == was:
            _FakeWriter.table[k] = v
            _FakeWriter.updates.append((k, v))
            return 1
        return 0

    def commit(self):
        _FakeWriter.committed = True


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check):
    import selftest_shops as T
    from domains import shopdata as SD
    from domains.cs_kinds import titledata as TD
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    check("А4.6 реестр: область «titledata» последней, виды title.points / enabled / cond / bonus, права data.edit / data.apply, гейт "
          "баланса; FameInfo.txt — per_copy (у Indun своя база); выкладчик пускает ConfigSet\\FameInfo.txt во всех трёх GS",
          SD.AREAS[SD.AREAS.index(TD) + 1:] == [a for a in SD.AREAS if a.AREA in ("skilldata", "mapdata", "events", "patchcfg")]   # ★ А5.4: + «Счастливые часы»; ★ А4.7: за ней — «Навыки и классы»; ★ А4.8 — «Карты»
          and set(TD.KINDS) == {"title.points", "title.enabled", "title.cond", "title.bonus"}   # ★ ревизия 39 Н-1: условие было закомментировано
          and SD.area_perm("title.bonus", "apply") == "data.apply" and SD.area_perm("title.cond", "edit") == "data.edit" and TD.BALANCE_GATE
          and SD.SRV_POLICY[FAME_REL] == "per_copy" and all(g + BS + FAME_REL in dc.ALLOWED for g in GS3))
    bad = []
    for kind, p in (("title.points", {"id": 600, "value": 1}), ("title.points", {"id": 1, "value": 40000}), ("title.enabled", {"id": 1, "on": 2}),
                    ("title.bonus", {"id": 1, "slot": 0, "code": 50, "min": 0, "max": 0}),
                    ("title.bonus", {"id": 1, "slot": 6, "code": 65, "min": 0, "max": 1}),
                    ("title.bonus", {"id": 1, "slot": 0, "code": 65, "min": 5, "max": 1}),
                    ("title.bonus", {"id": 1, "slot": 0, "code": 0, "min": 1, "max": 1}),
                    ("title.cond", {"id": 1, "fields": {"accum": 1}}), ("title.cond", {"id": 1, "fields": {}}),
                    ("title.cond", {"id": 1, "fields": {"mode2": 3}})):
        try:
            SD.norm(kind, p)
            bad.append((kind, p))
        except Exception:
            pass
    check("А4.6 позиции: неверные параметры — отказ (номер вне 0…511, очки > 32767, включено не 0/1, код бонуса вне −1/0/65…71, слот 6, "
          "мин. > макс., значения у пустого слота, неизвестное или пустое поле условия, вид второй ступени 3); пустое поле — «не менять»",
          not bad and SD.norm("title.cond", {"id": 2, "fields": json.dumps({"param": 20, "target": ""})})["fields"] == {"param": 20}, bad)
    r0 = [int(x) for x in _rec(0).split("\t")]
    r20 = [int(x) for x in _rec(20).split("\t")]
    check("А4.6 ветки сервера (sub_54A050 / sub_54B260): простое 0 — цель и вторая ступень; кол.45 = 1 (20) — общий накопитель без параметра; "
          "2 — ещё уровень; 29/45 — цикл; 47…55 — цель НЕ читается как порог; 237…244 — оба счётчика; 21 — число званий; 133 — ничего",
          set(TD.reads(0, r0)) == {"target", "mode2", "thr2"} and set(TD.reads(20, r20)) == {"target", "mode2", "thr2"}
          and "param" in TD.reads(2, r0) and set(TD.reads(29, r0)) == {"target", "param", "mode2", "thr2"}
          and "target" not in TD.reads(47, r0) and "param" in TD.reads(47, r0) and set(TD.reads(240, r0)) == {"target", "param", "mode2", "thr2"}
          and set(TD.reads(21, r0)) == {"target"} and TD.reads(133, r0) == {} and len(TD.SIMPLE) == 172)
    with T.synthetic() as (raw, md5, cli):
        for rel, b in stack_files().items():
            raw[rel], md5[rel] = b, _md5(b)
        cli.titles = cli_titles()
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tempfile.mkdtemp(prefix="asda_t46_cs_")
        try:
            with _Hold():
                _offline_kinds(check, raw, md5, cli)
                _offline_after_run(check, raw, md5, cli)
                _offline_guard(check, raw, md5, cli)
                _offline_plan(check, raw, md5, cli)
                _offline_p88(check, raw, md5, cli)
            _offline_after_server(check, raw, md5)
            with _Hold():
                d = SD.divergence(areas=("titledata",))
                secs = {s["key"]: s for s in d["sections"]}
                cli.titles[2][2] = 99
                d2 = SD.divergence(areas=("titledata",))
                s2 = {s["key"]: s for s in d2["sections"]}
                cli.titles[2][2] = cli_titles()[2][2]
                check("А4.6 расхождения: раздел titles; Indun — своя база (строка раздела); очки клиента ≠ сервера — строка",
                      list(secs) == ["titles"] and any("Indun_GameServer" in r["why"] for r in secs["titles"]["rows"])
                      and any(r["id"] == 2 and r.get("field") == "очки" for r in s2["titles"]["rows"]), secs["titles"]["rows"][:3])
                fp = {i: int(_rec(i).split("\t")[42]) for i in range(N)}
                fp[0], fp[N + 1] = 31, 5
                fp.pop(4)
                with _Hold(extra={40: [(75020, 1, "Ghost", 9, False)]}, fp=fp):
                    d3 = {s["key"]: s for s in SD.divergence(areas=("titledata",))["sections"]}["titles"]["rows"]
                w3 = [r["why"] for r in d3]
                ok3 = [r["why"] for r in secs["titles"]["rows"]]
                check("А4.6 ревизия 38 М-2 / К-4: расхождения — «выключено, но его выдаёт набор (записи 30)», «выключено, но есть держатели» "
                      "(40, Ghost), AsdaFamePoints ≠ кол. 42 (0: 31 ≠ 32), нет строки (4), лишняя строка (N + 1); при согласованной "
                      "AsdaFamePoints строк AsdaFamePoints нет",
                      any(r["id"] == 40 and "выдаёт набор (кол. 10/11 записей 30)" in r["why"] for r in d3)
                      and any(r["id"] == 40 and "есть держатели: 1 перс. (Ghost (75020/1))" in r["why"] for r in d3)
                      and any(r["id"] == 0 and r.get("field") == "AsdaFamePoints" and r.get("client") == 31 for r in d3)
                      and any(r["id"] == 4 and "нет строки" in r["why"] for r in d3) and any(r["id"] == N + 1 and "лишняя строка" in r["why"] for r in d3)
                      and not any("AsdaFamePoints" in x for x in ok3), w3[-6:])
                lk = TD.lookup("title", "0")
                sr = TD.lookup("titles", "")
                check("А4.6 справка: карточка звания 0 (3 копии, клиент, поля условий с тем, как их читает сервер, держатели), поиск — все записи",
                      lk["server"]["GameServer"]["points"] == 32 and lk["client"]["Point"] == 32 and lk["holders"][0]["name"] == "Alice"
                      and any(f[0] == "target" and f[4] for f in lk["fields"]) and any(f[0] == "param" and not f[4] for f in lk["fields"])
                      and len(sr["rows"]) == N, (lk.get("holders"), len(sr["rows"])))
        finally:
            shutil.rmtree(SD.CS_DIR, ignore_errors=True)
            SD.CS_DIR = saved_dir
    _offline_items(check)
    _offline_tr(check)


def _offline_kinds(check, raw, md5, cli):
    e = _ev([("title.points", {"id": 0, "value": 40}), ("title.points", {"id": 66, "value": 188 * 3})])
    p0, p1 = e.positions
    gi = e.new_bytes()["Indun_GameServer" + BS + FAME_REL]
    gg = e.new_bytes()["GameServer" + BS + FAME_REL]
    check("А4.6 очки: правка на 3 копии по значениям каждой (Indun сохранил свои очки звания 7 = 12 и цель звания 10 = 0), хвостовой пробел "
          "слова сохранён, клиент — csv_cell title_list.Point, держатели — предупреждение со списком, рейтинговое — предупреждение P23; "
          "×3 — сильная правка",
          not _errs(e) and _line(gg, 0)[42] == b"40" and _line(gi, 0)[42] == b"40" and _line(gi, 7)[42] == b"12" and _line(gi, 10)[3] == b"0 "
          and _line(gg, 0)[3] == b"500 " and p0["client"] == [{"type": "csv_cell", "file": "title_list", "key_col": "Id", "key": "0", "col": "Point",
                                                              "old": "32", "new": "40"}]
          and any("Alice (75001/1, ур. 20)" in w for w in p0["warnings"]) and any("рейтинговое" in w for w in p1["warnings"])
          and [b["strong"] for b in e.balance] == [False, True], (_errs(e), p0["warnings"], e.balance))
    e = _ev([("title.points", {"id": 7, "value": 20})])
    check("А4.6 отличия Indun: у звания 7 очки Indun ≠ GameServer — правка очков отказ «отличия копии не затираются», ни одна копия не тронута",
          any("отличия копии не затираются" in x for x in _errs(e)) and not e.new_bytes(), _errs(e))
    e1 = _ev([("title.enabled", {"id": 0, "on": 0})])
    e2 = _ev([("title.enabled", {"id": 25, "on": 0}), ("title.enabled", {"id": 18, "on": 1}), ("title.enabled", {"id": 66, "on": 0})])
    with _Hold(fail=True):
        e3 = _ev([("title.enabled", {"id": 25, "on": 0})])
    gg = e2.new_bytes()["GameServer" + BS + FAME_REL]
    check("А4.6 включено: выключить звание с держателями — отказ (клиент скрыл бы строку); без держателей — правка (сильная, type), включить 18 — "
          "0 → 2 у сервера и клиента; рейтинговое 66 — отказ; держатели не прочитаны — отказ",
          any("клиент скрыл бы строку" in x and "Alice (75001/1)" in x for x in _errs(e1)) and len(_errs(e2)) == 1
          and "рейтинговое" in _errs(e2)[0] and _line(gg, 25)[1] == b"0" and _line(gg, 18)[1] == b"2"
          and e2.positions[1]["client"][0]["new"] == "2" and all(b["kind"] == "type" and b["strong"] for b in e2.balance)
          and any("не прочитаны" in x for x in _errs(e3)), (_errs(e1), _errs(e2), _errs(e3)))
    refuse = {
        "РАВЕНСТВО": ("title.cond", {"id": 47, "fields": {"target": 5}}),
        "сравнивается с нулём": ("title.cond", {"id": 19, "fields": {"param": 1}}),
        "gender_": ("title.cond", {"id": 35, "fields": {"param": 1}}),
        "не читает": ("title.cond", {"id": 0, "fields": {"param": 3}}),
        "не читают": ("title.cond", {"id": 60, "fields": {"target": 3}}),          # р38 К-3: ветки не читают, TitleItemCheck — расход
        "копка сравнивает": ("title.cond", {"id": 34, "fields": {"param": 3}}),     # р38 К-3: звание 34 — «смысл не подтверждён»
        "выдаёт набор (кол. 10/11 записей 29)": ("title.enabled", {"id": 26, "on": 0}),   # р38 М-2
        "чтение за её концом": ("title.cond", {"id": 29, "fields": {"target": 2000}}),
        "при цели 0": ("title.cond", {"id": 0, "fields": {"target": 0}}),
        "уровень персонажа": ("title.cond", {"id": 2, "fields": {"param": 200}}),
        "менять нечего": ("title.cond", {"id": 0, "fields": {"target": 500}}),
        "смена кода бонуса не делается": ("title.bonus", {"id": 0, "slot": 0, "code": 66, "min": 1, "max": 2}),
        "звания 75 нет": ("title.points", {"id": 75, "value": 1}),
    }
    got = {}
    for k, (kind, p) in refuse.items():
        ee = _ev([(kind, p)])
        got[k] = any(k.strip() in x for x in _errs(ee)) and not ee.new_bytes()
    check("А4.6 условия и бонусы — 13 отказов: цель 47…55 (равенство), параметр 19 и 35…37 (смысл не подтверждён), поле, которое сервер для "
          "звания не читает (0 — параметр, 60 — ветки не читают цель, RecvClient_TitleItemCheck — только расход), параметр 34 (копка, "
          "смысл поля предмета не подтверждён), выключение звания, которое выдаёт набор (26 — «следующее» записи 29), цикл 29 > 1280, цель 0, "
          "уровень звания 2 > 150, «менять нечего», смена кода бонуса у звания с держателями, звания нет в таблице — стойка не тронута",
          all(got.values()) and len(got) == 13, got)
    import domains.cs_kinds.titledata as TD
    r34 = [int(x) for x in _rec(34).split("\t")]
    check("А4.6 ревизия 38 К-3: звание 34 — параметр в справке «копка (sub_546C00)» и отказ UNSAFE «смысл не подтверждён» при любой кол. 45",
          "param" in TD.reads(34, r34) and TD._unsafe(34, r34, "param") == TD.UNSAFE["param_34"]
          and TD._unsafe(34, r34[:45] + [1], "param") == TD.UNSAFE["param_34"] and "param" in TD.reads(34, r34[:45] + [1]))
    e = _ev([("title.cond", {"id": 0, "fields": {"target": 400, "thr2": 20}}), ("title.cond", {"id": 2, "fields": {"param": 20}})])
    pa = e.positions[0]
    gg = e.new_bytes()["GameServer" + BS + FAME_REL]
    check("А4.6 условия: цель и порог второй ступени — правка трёх копий (у клиента условий нет: клиентских правок нет), строки «как читает "
          "сервер», держатели — «звание остаётся», снижение цели — список «получат при следующем событии» (Carl, счётчик 450 ≥ 400); "
          "параметр звания 2 (уровень) — правка", not _errs(e) and _line(gg, 0)[3] == b"400 " and _line(gg, 0)[44] == b"20"
          and _line(gg, 2)[4] == b"20" and not pa["client"] and any(x.startswith("как читает сервер — цель (кол. 3)") for x in pa["lines"])
          and any("звание остаётся" in w for w in pa["warnings"]) and any("Carl (75004/1, ур. 12, счётчик 450)" in w for w in pa["warnings"]),
          (_errs(e), pa["warnings"], pa.get("lines")))
    e = _ev([("title.bonus", {"id": 25, "slot": 2, "code": 70, "min": 2, "max": 5}), ("title.bonus", {"id": 3, "slot": 0, "code": 65, "min": 2, "max": 8})])
    b0, b1 = e.positions
    gg = e.new_bytes()["GameServer" + BS + FAME_REL]
    check("А4.6 бонусы: новый код у звания без держателей — правка (сильная: type), клиент OptionTypeId2 0 → 70; разброс у звания с держателями "
          "(код прежний) — правка с предупреждением «у них прежние значения», клиент не меняется; строка «как применяет сервер»",
          not _errs(e) and [x.decode() for x in _line(gg, 25)[22:25]] == ["70", "2", "5"] and b0["client"][0]["col"] == "OptionTypeId2"
          and b0["client"][0]["new"] == "70" and not b1["client"] and any("прежние значения бонуса" in w for w in b1["warnings"])
          and any(b["kind"] == "type" and b["strong"] for b in e.balance) and any(x.startswith("как применяет сервер: Удача") for x in b0["lines"]),
          (_errs(e), e.balance))


def _offline_after_run(check, raw, md5, cli):
    from domains import shopdata as SD
    e = _ev([("title.cond", {"id": 10, "fields": {"mode2": 2}})])
    e2 = _ev([("title.cond", {"id": 10, "fields": {"thr2": 3}})])
    check("А4.6 итог набора (after_run): вид второй ступени 2 у звания 10 — у Indun цель 0 (своя база) → деление на ноль, новой неисправности "
          "копии нет у GameServer, есть у Indun — отказ «копия Indun_GameServer: …»; правка порога при той же цели 0 — неисправность была и "
          "до правки, не отказ", any(x.startswith("копия Indun_GameServer: ") and "деление на ноль" in x for x in _errs(e))
          and not _errs(e2), (_errs(e), _errs(e2)))


def _offline_guard(check, raw, md5, cli):
    from domains import shopdata as SD
    from domains.cs_kinds import titledata as TD
    items = [("title.enabled", {"id": 25, "on": 0}), ("title.bonus", {"id": 20, "slot": 1, "code": 67, "min": 1, "max": 1})]
    e = _ev(items)
    cs, m = _cs_man(e, 9461, items)
    ok0 = TD.apply_guard(cs, "apply") == []
    with _Hold(extra={25: [(75010, 1, "Late", 5, False)], 20: [(75011, 1, "Late2", 6, False)]}):
        ap = TD.apply_guard(cs, "apply")
    with _Hold(fail=True):
        apf = TD.apply_guard(cs, "apply")
    # ★ ревизия 38 М-2: к выкладке выключаемое звание 25 оказалось «следующим» набора (подмена set_sources) — причина
    saved_ss = TD.set_sources
    TD.set_sources = lambda t, tid, where: [33] if tid == 25 else []
    try:
        ap_src = TD.apply_guard(cs, "apply")
    finally:
        TD.set_sources = saved_ss
    check("А4.6 ревизия 38 М-2 (перепроверка перед выкладкой): выключаемое звание 25 выдаёт набор — причина «выключение, а его выдаёт набор "
          "(кол. 10/11 записей 33)»", ap_src == ["звание 25 «%s»: выключение, а его выдаёт набор (кол. 10/11 записей 33)" % _tn(25)], ap_src)
    # откат: набор выложен (на стойке — новые файлы, база в .bak_<метка>), держатель 25 появился после выкладки — откат включит, не выключит
    for rel, f in m["files"].items():
        raw[rel + ".bak_" + m["tag"]] = raw[rel]
        md5[rel + ".bak_" + m["tag"]] = f["base"]
        raw[rel] = open(f["local"], "rb").read()
        md5[rel] = f["new"]
    try:
        with _Hold(extra={20: [(75011, 1, "Late2", 6, False)]}):
            rb = TD.apply_guard(cs, "rollback")
    finally:
        for rel in m["files"]:
            raw[rel] = raw.pop(rel + ".bak_" + m["tag"])
            md5[rel] = md5.pop(rel + ".bak_" + m["tag"])
    check("А4.6 перепроверка (урок ревизий 36–37): по манифесту набора — держателей нет: пусто; держатели появились после проверки — выкладка: "
          "«выключение при 1 держателях», «смена кода бонуса 1»; не прочитано — «не прочитаны»; откат (живая = набор, база в .bak) — смена кода "
          "бонуса обратно при держателе 20 — причина, выключение 25 обратно не опасно",
          ok0 and len(ap) == 2 and any("выключение при 1 держателях (Late (75010/1))" in x for x in ap) and any("смена кода бонуса 1" in x for x in ap)
          and apf and "не прочитаны" in apf[0] and len(rb) == 1 and "смена кода бонуса 1" in rb[0], (ap, apf, rb))


P88_INI_ON = "[General]\r\nMasterEnable=1\r\n[P88_TitleEvents]\r\nEnabled=1\r\nThreshold192=300\r\n"
P88_INI_OFF = "[General]\r\nMasterEnable=1\r\n[P88_TitleEvents]\r\nEnabled=0\r\n"
P88_INI_NOMASTER = "[General]\r\nMasterEnable=0\r\n[P88_TitleEvents]\r\nEnabled=1\r\n"
P88_INI_NOSITES = ("[General]\r\nMasterEnable=1\r\n[P88_TitleEvents]\r\nEnabled=1\r\nWarKill=0\r\nSkillReset=0\r\nWarehouseMax=0\r\nCraft=0\r\n"
                   "Dig=0\r\nPetLevel=0\r\nPickup=0\r\n")


def _offline_p88(check, raw, md5, cli):
    """★ ревизия 38 М-1: цель званий P88 (190, 192, 199–203, 205) задаёт patches.ini [P88_TitleEvents] Threshold<id> — подменная
    таблица на 206 записей (192 — общий накопитель), patches.ini трёх GS — подменой srvtables.stack_text."""
    from domains import shopdata as SD, srvtables
    from domains.cs_kinds import titledata as TD
    big = 206

    def fame(indun):
        recs = [_rec(i, indun) for i in range(N)]
        for i in range(N, big):
            v = [i, 2, 0, 50, 0] + [-1] * 7 + [0] * 30 + [5, 0, 0, 1]
            recs.append("\t".join("%d" % x for x in v))
        return ("\r\n".join([str(big)] + recs) + "\r\n").encode("latin-1")
    saved_raw = {g + BS + FAME_REL: (raw[g + BS + FAME_REL], md5[g + BS + FAME_REL]) for g in GS3}
    saved_cli, saved_st = cli.titles, srvtables.stack_text
    ini = {g: P88_INI_ON for g in GS3}

    def stack_text(rel, ttl=60):
        g = rel.split(BS, 1)[0]
        if rel.endswith("patches.ini"):
            if ini[g] is None:
                raise OSError("нет ответа (самотест)")
            return ini[g]
        return saved_st(rel, ttl)
    try:
        for g in GS3:
            b = fame(g == "Indun_GameServer")
            raw[g + BS + FAME_REL], md5[g + BS + FAME_REL] = b, _md5(b)
        cli.titles = dict(saved_cli)
        for i in range(N, big):
            cli.titles[i] = [i, 2, 0] + [0] * 6 + [1] * 6
        srvtables.stack_text = stack_text
        item = ("title.cond", {"id": 192, "fields": {"target": 100}})
        e_on = _ev([item])
        nb_on = e_on.new_bytes()                  # до возврата подменной стойки (new_bytes сравнивает с текущим снимком)
        st = TD.p88_goals()
        lk = TD.lookup("title", "192")
        ini.update({g: P88_INI_OFF for g in GS3})
        e_off = _ev([item])
        ini.update({g: P88_INI_NOMASTER for g in GS3})
        e_nm = _ev([item])
        ini.update({g: P88_INI_NOSITES for g in GS3})
        e_ns = _ev([item])
        ini.update({g: P88_INI_OFF for g in GS3})
        ini["Indun_GameServer"] = P88_INI_ON
        e_mix = _ev([item])
        ini["Indun_GameServer"] = None
        e_err = _ev([item])
        e_other = _ev([("title.cond", {"id": 193, "fields": {"target": 100}})])
        # перепроверка перед выкладкой: набор проверен при выключенном P88, к выкладке P88 включили — отказ; откат цели — без отказа
        ini.update({g: P88_INI_OFF for g in GS3})
        e_ok = _ev([item])
        cs, _m = _cs_man(e_ok, 9462, [item])
        g_off = TD.apply_guard(cs, "apply")
        ini.update({g: P88_INI_ON for g in GS3})
        g_on = TD.apply_guard(cs, "apply")
        ini["GameServer"] = None
        g_err = TD.apply_guard(cs, "apply")
    finally:
        for rel, (b, h) in saved_raw.items():
            raw[rel], md5[rel] = b, h
        cli.titles, srvtables.stack_text = saved_cli, saved_st
    E = _errs
    check("А4.6 ревизия 38 М-1: звание 192 (P88) — цель задаёт patches.ini: P88 включён во всех GS — отказ «порог задаёт patches.ini "
          "[P88_TitleEvents] Threshold192 (… 300 …)»; Enabled = 0 / MasterEnable = 0 / все площадки событий выключены — правка с "
          "предупреждением «P88 выключен во всех GS»; включён только в Indun — отказ; patches.ini не прочитан — отказ «не прочитан»; "
          "193 (не из g_goals) — без отказа",
          any("порог задаёт patches.ini [P88_TitleEvents] Threshold192 (GameServer 300" in x and "P88 включён в GameServer, Indun_GameServer, "
              "Ch2_GameServer" in x for x in E(e_on)) and not nb_on
          and all(not E(x) and any("P88 выключен во всех GS" in w for w in x.positions[0]["warnings"]) for x in (e_off, e_nm, e_ns))
          and any("P88 включён в Indun_GameServer" in x and "[P88 = 0]" in x for x in E(e_mix)) and any("patches.ini не прочитан" in x for x in E(e_err))
          and not E(e_other) and st["GameServer"]["on"] and st["GameServer"]["thr"][192] == 300 and st["GameServer"]["thr"][205] == 500,
          (E(e_on), E(e_mix), E(e_err), E(e_other)))
    tf = [f for f in lk["fields"] if f[0] == "target"][0]
    check("А4.6 ревизия 38 М-1: справка звания 192 — порог P88 по копиям (300, включён), поле цели — причина «задаёт patches.ini» (редактора нет)",
          lk["p88"] and lk["p88"]["GameServer"] == {"on": True, "thr": 300} and tf[5] == TD.UNSAFE["p88_on"], (lk.get("p88"), tf))
    check("А4.6 ревизия 38 М-1 (перепроверка перед выкладкой): проверено при P88 = 0 — пусто; к выкладке P88 включили — причина «цель задаёт "
          "patches.ini»; patches.ini не прочитан — «не прочитаны» (отказ и с ключом)",
          g_off == [] and len(g_on) == 1 and "звание 192: цель задаёт patches.ini [P88_TitleEvents]" in g_on[0] and g_err
          and "не прочитаны" in g_err[0], (g_off, g_on, g_err))


def _offline_after_server(check, raw, md5):
    from core import db
    from domains.cs_kinds import titledata as TD
    saved = db.GameWriter
    _FakeWriter.table = {i: int(_rec(i).split("\t")[42]) for i in range(N)}
    _FakeWriter.table[0] = 31                         # «устаревшая» строка
    _FakeWriter.table.pop(5)                          # строки нет — заметка «пересоберите»
    _FakeWriter.updates = []
    db.GameWriter = _FakeWriter
    try:
        notes = TD.after_server({"id": 1, "items": [{"pos": 1, "kind": "title.points", "params": {"id": 0}}]}, "sync")
        none = TD.after_server({"id": 2, "items": [{"pos": 1, "kind": "price", "params": {}}]}, "sync")
        u1 = list(_FakeWriter.updates)
        # ★ ревизия 38 К-4: UPDATE затронул не 1 строку — без commit (откат), заметка «повторите server-sync»; лишняя строка FameIdx ≥ N
        _FakeWriter.table = {i: int(_rec(i).split("\t")[42]) for i in range(N)}
        _FakeWriter.table[0], _FakeWriter.table[N + 3] = 31, 7
        _FakeWriter.force, _FakeWriter.committed = {0: 2}, False
        bad = TD.after_server({"id": 3, "items": [{"pos": 1, "kind": "title.points", "params": {"id": 0}}]}, "sync")
        c_bad = _FakeWriter.committed
        _FakeWriter.force = {}
        ok2 = TD.after_server({"id": 4, "items": [{"pos": 1, "kind": "title.points", "params": {"id": 0}}]}, "sync")
    finally:
        db.GameWriter = saved
        _FakeWriter.force = {}
    check("А4.6 после выкладки: Joy1.dbo.AsdaFamePoints приводится к живому FameInfo.txt — пишется только различающаяся строка (0: 31 → 32, "
          "UPDATE с прежним значением), нет строки 5 — заметка «пересоберите»; набор без званий — ничего",
          u1 == [(0, 32)] and any("строк изменено 1" in n for n in notes) and any("нет званий 5" in n for n in notes) and none == [],
          notes)
    check("А4.6 ревизия 38 К-4: UPDATE затронул 2 строки вместо 1 — транзакция без commit, заметка «не приведена … повторите changeset "
          "server-sync 3»; лишняя строка FameIdx ≥ N — заметка «лишние строки»",
          not c_bad and len(bad) == 1 and "UPDATE затронул 2 строк вместо 1" in bad[0] and "server-sync 3" in bad[0]
          and any("лишние строки %d" % (N + 3) in n for n in ok2), (bad, ok2))


def _offline_plan(check, raw, md5, cli):
    from domains import shopdata as SD
    real = SD.CLIENT_FILES["title_list"]
    if not os.path.isfile(real):
        return check("А4.6 план клиента — title_list.csv порта есть", False, real)
    before = SD.md5f(real)
    import csv as _csv
    rows = {r["Id"]: r for r in _csv.DictReader(open(real, encoding="utf-8-sig", newline=""))}
    r0 = rows["0"]
    edits = [{"type": "csv_cell", "file": "title_list", "key_col": "Id", "key": "0", "col": "Point", "old": r0["Point"], "new": str(int(r0["Point"]) + 1)},
             {"type": "csv_cell", "file": "title_list", "key_col": "Id", "key": "0", "col": "OptionTypeId2", "old": r0["OptionTypeId2"], "new": "70"}]
    plan = SD.client_plan(edits, 0)
    vo = [p for p in plan["files"] if p.replace("\\", "/").endswith("_value_overlay/title_list.csv")]
    led = plan["_bytes"][vo[0]].decode("utf-8") if vo else ""
    check("А4.6 план клиента (подставной генератор, ведомости во временной папке): title_list.csv — Point и OptionTypeId2 звания 0, ведомость "
          "_value_overlay/title_list.csv — две строки «было → стало», DT_title_list точечно (строка звания 0); файл порта md5 до = после",
          not plan["errors"] and real in plan["files"] and vo and led.count("админ-центр, набор изменений №0") == 2 and re.search(r"(?m)^0,Point,", led)
          and re.search(r"(?m)^0,OptionTypeId2,", led) and any(j["dt"].endswith("DT_title_list") for j in plan["dt_jobs"]) and SD.md5f(real) == before,
          (plan["errors"], list(plan["files"])))


def _offline_items(check):
    from domains.cs_kinds import itemdata as I
    ct = bytearray(146 * 3)
    struct.pack_into("<5i", ct, 146 * 2 + 69, 31001, -1, -1, -1, -1)
    struct.pack_into("<5h", ct, 146 * 2 + 89, 5, 0, 0, 0, 0)
    mct = bytearray(59 * 2)
    struct.pack_into("<I", mct, 59, 7)
    struct.pack_into("<5i", mct, 59 + 21, -1, 31001, -1, -1, -1)
    struct.pack_into("<5h", mct, 59 + 41, 0, 3, 0, 0, 0)
    uses = I.cond_uses({"Quest\\ConditionTable.Bin": bytes(ct), "Quest\\MonsterConditionTable.bin": bytes(mct)}, 31001)

    class _Ev:
        class snap:
            @staticmethod
            def extend(rels):
                pass

            @staticmethod
            def raw(rel):
                return bytes(ct) if rel.endswith("ConditionTable.Bin") and "Monster" not in rel else bytes(mct)
    rep = {"warnings": []}
    I.cond_warn(_Ev, 31001, rep)
    rep2 = {"warnings": []}
    I.cond_warn(_Ev, 31002, rep2)
    check("А4.6 попутно («Предметы», смена стопки): предмет — цель условий заданий — ConditionTable (ключ = номер записи, ids +69 / cnts +89) и "
          "MonsterConditionTable (ключ +0, ids +21 / cnts +41, sub_41FB90) — предупреждение со списком, условия не правятся; не цель — тихо",
          uses == [("ConditionTable", 2, 5), ("MonsterConditionTable", 7, 3)] and len(rep["warnings"]) == 1
          and "ConditionTable 2 × 5, MonsterConditionTable 7 × 3" in rep["warnings"][0] and not rep2["warnings"], (uses, rep))


def _offline_tr(check):
    from core import i18n
    samples = [
        "звание 0 Boring: очки славы 32 → 40 (сервер FameInfo ×3 GS, клиент title_list.Point)",
        "звание 0 Boring есть у 2 перс.: Alice (75001/1, ур. 20); Bob (75002/2, ур. 30, надето) — слава держателей пересчитается при входе "
        "(recvDB, 2274); до входа — прежняя слава и место в рейтинге славы (FamePointRank); снятие вычтет новые очки (не ниже 0) — пересчёт "
        "славы панелью или вход это выровняют",
        "позиция 1: звание 0 Boring есть у 1 перс. (Alice (75001/1)): клиент скрыл бы строку (Enabled = 0), игрок не смог бы ни увидеть, ни "
        "снять его, а бит, слава и надетый слот остались бы (recvDBUserActiveFame не проверяет владение) — правка не делается",
        "звание 0 Boring, условия: цель (кол. 3): 500 → 400; порог второй ступени (кол. 44): 10 → 20 (сервер FameInfo ×3 GS; у клиента "
        "условий нет — текст условия правится в «Текстах»)",
        "как читает сервер — цель (кол. 3): счётчик ≥ цели", "как читает сервер — параметр (кол. 4): второй счётчик ≥ параметра",
        "цель снижается: у 1 перс. счётчик уже не меньше новой цели 400: Carl (75004/1, ур. 12, счётчик 450) — они получат звание при "
        "следующем событии этого вида",
        "звание 25 Tester: бонус 2: пусто 0…0% → Удача 2…5% (сервер FameInfo ×3 GS, клиент title_list.OptionTypeId того же слота)",
        "как применяет сервер: Удача + случайное 2…5 % от базы (sub_5329A0 при получении, sub_54D210 / sub_43B750 при надевании)",
        "позиция 1: копия Indun_GameServer: цель 0: при цели 0 и меньше «счётчик ≥ цели» выполняется на первом же событии (а при виде второй "
        "ступени 2 — деление на ноль, sub_54B260)",
        "после проверки набора изменились данные стойки (звание 25 Tester: выключение при 1 держателях (Late (75010/1)); звание 20 X: смена "
        "кода бонуса 1 при 1 держателях (Late2 (75011/1))) — выкладка не делается, стойка не тронута, объявления не было",
        "Joy1.dbo.AsdaFamePoints приведена к FameInfo.txt: строк изменено 1",
        "звание 0: очки славы", "звание 18: включено", "звание 0: цель (кол. 3)", "звание 3: бонус 0 — максимум, %",
        "у званий 47…55 цель (кол. 3) сравнивается с параметром события на РАВЕНСТВО (sub_54B260) — это не порог, смысл параметра события не "
        "подтверждён, правка не делается",
        "смена стопки x31001 (31001): предмет — цель условий заданий (ConditionTable 2 × 5, MonsterConditionTable 7 × 3) — условия панель не "
        "правит, проверьте, что сбор и сдача после смены стопки идут как задумано",
        "звания: FameInfo сервер ≠ title_list клиент", "Звание: бонус характеристики (FameInfo кол. 12+5m…14+5m + title_list.OptionTypeId)",
        # ★ ревизия 38
        "позиция 1: копия Indun_GameServer: вид второй ступени 2 при цели 0: sub_54B260 делит счётчик на цель (кол. 3) — деление на ноль",
        "позиция 1: звание 192: порог задаёт patches.ini [P88_TitleEvents] Threshold192 (GameServer 300, Indun_GameServer 300 [P88 = 0], "
        "Ch2_GameServer 300) — P88 включён в GameServer, Ch2_GameServer и при первом событии пишет порог из ini в FameInfo в памяти "
        "(p88_title_events.cpp ApplyGoals), правка кол. 3 не подействует, не делается (ini правится не здесь)",
        "позиция 1: звание 192: цель может задавать patches.ini [P88_TitleEvents] Threshold192 — patches.ini не прочитан (нет ответа), вслепую "
        "не делается",
        "P88 выключен во всех GS — цель берётся из FameInfo, но если P88 включат, порог снова возьмёт patches.ini [P88_TitleEvents] Threshold192",
        "позиция 1: звание 60: ветки выдачи (sub_54A050 / sub_54B260) цель для этого звания не читают, а RecvClient_TitleItemCheck берёт её "
        "только для расхода предметов-званий — звание этим не выдаётся, правка не подействует, не делается",
        "позиция 1: у звания 34 параметр (кол. 4) копка сравнивает с полем +5 найденного предмета (sub_546C00, GameServer.c:124962) — смысл "
        "поля предмета не подтверждён, правка не делается",
        "цель снижается: у 1 перс. счётчик уже не меньше новой цели 400: Carl (75004/1, ур. 12, счётчик 450) — они получат звание при "
        "следующем событии этого вида или при GM-пересчёте P25 (SweepAllTitles: игроки в игре, sub_54B260 по накопленному счётчику)",
        "позиция 1: звание 26 Tester выдаёт набор (кол. 10/11 записей 29): каскад sub_54A610 выдаёт «следующее» звание без проверки "
        "«включено» — игрок получил бы скрытое звание, которое не снять, правка не делается",
        "после проверки набора изменились данные стойки (звание 192: цель задаёт patches.ini [P88_TitleEvents], P88 включён в GameServer; "
        "звание 25 Tester: выключение, а его выдаёт набор (кол. 10/11 записей 33)) — выкладка не делается, стойка не тронута, объявления не было",
        "Joy1.dbo.AsdaFamePoints не приведена к FameInfo.txt (звание 0: UPDATE затронул 2 строк вместо 1 — ничего не записано) — повторите "
        "changeset server-sync 3",
        "в Joy1.dbo.AsdaFamePoints лишние строки 73 (званий в FameInfo.txt нет) — пересоберите её (ac0w_01_migrate.sql)",
        "выключено, но его выдаёт набор (кол. 10/11 записей 30)", "выключено, но есть держатели: 1 перс. (Ghost (75020/1))",
        "держатели выключенных званий не прочитаны (нет связи с Joy1)", "Joy1.dbo.AsdaFamePoints не прочитана (нет связи с Joy1)",
        "в Joy1.dbo.AsdaFamePoints нет строки звания",
        "Joy1.dbo.AsdaFamePoints ≠ FameInfo кол. 42 (снятие UPCharFameBitDis вычтет не те очки) — changeset server-sync",
        "лишняя строка Joy1.dbo.AsdaFamePoints (звания в FameInfo.txt нет)",
        "собран набор, но звание 6 «Tester» выключено — панель его не выдаёт (каскад сервера sub_54A610 выдал бы его скрытым)",
        "звание 5 живьём не выдаётся: каскад наборов сервера (sub_54A610, его зовёт P127 после выдачи) выдал бы и выключенное звание 6 без "
        "проверки «включено» — выдайте, когда игрок не в игре (панель выключенное звание набора не выдаёт)",
        "звание 5 выключено на сервере после предпросмотра — живая выдача не делается"]
    i18n.set_lang("en")
    try:
        tr = [i18n.tr(x) for x in samples]
    finally:
        i18n.set_lang("ru")
    left = [(a, b) for a, b in zip(samples, tr) if a == b or re.search("[А-Яа-яЁё]{3}", b)]
    check("А4.6 переводы службы: позиции, держатели, отказы, итог набора, перепроверка, AsdaFamePoints, попутное предупреждение — EN без "
          "русского (вложенные «позиция N: копия …: …» и списки через «; » тоже)", not left, left[:2])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "titledata.js"), encoding="utf-8").read()
    en = open(os.path.join(root, "web", "i18n.js"), encoding="utf-8").read()
    STR = r'"((?:[^"\\]|\\.)*)"'
    have = set(re.findall(STR + r"\s*:", en))
    need = {x for x in re.findall(r"T\(" + STR, js)} | {x for x in re.findall(STR, js) if re.search("[А-Яа-яЁё]", x)}
    from domains.cs_kinds import titledata as TD
    srv = set(TD.UNSAFE.values()) | {v[1] for v in TD.COND.values()}
    for tid in (0, 2, 29, 47, 237, 21, 34):
        srv |= set(TD.reads(tid, [0] * 46).values())
    miss = sorted((need | srv) - have)
    block = en.split("// А4.6 20.11", 1)[1] if "// А4.6 20.11" in en else ""
    keys = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", block, re.M)
    allk = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", en, re.M)
    check("А4.6 веб: titledata.js подключён (index.html, вкладка и маршрут в shops.js), все его строки и тексты справки службы («как читает "
          "сервер», отказы полей) есть в I18N_EN, ключи блока А4.6 не повторяют прежние",
          "/titledata.js" in open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
          and "#/shops/titles" in open(os.path.join(root, "web", "shops.js"), encoding="utf-8").read() and not miss and keys
          and all(allk.count(k) == 1 for k in keys), miss[:5])
    check("А4.6 ревизия 38 К-2: веб — имя характеристики в столбце «Сервер» через T() (как в выпадающем списке); справка показывает порог P88 "
          "и записи набора", "T((m.stats.find(x => x[0] === c)" in js and "m.p88" in js and "m.set_sources" in js)
    _offline_live_gate(check)


def _offline_live_gate(check):
    """★ ревизия 38 М-2: живая выдача P127 title_add — каскад sub_54A610 выдал бы выключенное «следующее» → отказ живого пути; перед
    записью FameInfo перечитывается (звание выключили после предпросмотра — отказ, команды узлу нет)."""
    from core.ops import OpRefused
    from domains import titles as TT
    fi = [[i, 1] + [0] * 3 + [-1] * 7 + [0] * 34 for i in range(10)]
    fi[5][10], fi[6][1], fi[7][10], fi[7][11] = 6, 0, 8, -1
    got = {}
    for tid in (5, 7):
        try:
            TT._live_cascade_gate(fi, tid)
            got[tid] = None
        except OpRefused as ex:
            got[tid] = str(ex)
    saved = TT._fi
    TT._fi = lambda: [[i, 0 if i == 7 else 1] + [0] * 3 + [-1] * 7 + [0] * 34 for i in range(10)]
    calls = []
    saved_call = TT.bridge.live_call
    TT.bridge.live_call = lambda *a, **k: calls.append(a) or ({"id": 1}, "ok")
    try:
        try:
            TT._live_title_apply(type("C", (), {"login": "selftest"})(), {"live": {"op": "title_add", "title": 7, "row": {}, "args": "id=7",
                                                                                  "uid": 1, "idx": 1}})
            late = None
        except OpRefused as ex:
            late = str(ex)
    finally:
        TT._fi, TT.bridge.live_call = saved, saved_call
    check("А4.6 ревизия 38 М-2 (P127 title_add): «следующее» 6 выключено — живая выдача 5 отказ (каскад sub_54A610), 7 со включённым "
          "«следующим» 8 — без отказа; звание выключили после предпросмотра — отказ перед командой узлу (команд 0)",
          got[5] and "выключенное звание 6" in got[5] and got[7] is None and TT.hidden_next(fi, 5) == [6]
          and late and "после предпросмотра" in late and not calls, (got, late, calls))


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox(check, ldb):
    """Набор «Звания» целиком: пара сервер + клиент, второе подтверждение сильной правки, перепроверка держателей, AsdaFamePoints, откаты."""
    import selftest_shops_sandbox as X
    from core import db, ops
    from domains import shopcs, shopdata as SD
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    real = SD.CLIENT_FILES["title_list"]
    if not os.path.isfile(real):
        return check("песочница А4.6 — title_list.csv порта есть", False, real)
    real_md5 = SD.md5f(real)
    saved_w = db.GameWriter
    with X.sandbox(ldb) as (st, env), _Hold():
        files = stack_files()
        for rel, b in files.items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        cdir = os.path.join(env["tmp"], "a46")
        os.makedirs(cdir)
        dst = os.path.join(cdir, "title_list.csv")
        shutil.copy2(real, dst)
        SD.CLIENT_FILES["title_list"] = dst
        orig = open(dst, "rb").read()
        st.assets[SD.DT["title_list"]] = orig
        _FakeWriter.table = {i: int(_rec(i).split("\t")[42]) for i in range(N)}
        _FakeWriter.updates = []
        db.GameWriter = _FakeWriter
        import csv as _csv
        r0 = {r["Id"]: r for r in _csv.DictReader(open(dst, encoding="utf-8-sig", newline=""))}["0"]
        try:
            cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.6", note="самотест песочницы А4.6: звания")["result"]["id"]
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="title.points", params={"id": 0, "value": int(r0["Point"]) * 3})
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="title.cond", params={"id": 0, "fields": {"target": 600}})
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="title.enabled", params={"id": 25, "on": 0})
            X._run(ctx, "shop.cs_check", cs=cid)
            cs = shopcs.get(cid)
            _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
            adm = ops.Ctx(7, "adm", "admin", "100.64.0.9", "web")
            _r, adm_no = X._try(adm, "shop.cs_approve", cs=cid, balance_ok="balance")
            X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
            check("песочница А4.6: пара (сервер и клиент), сильная правка (очки ×3, выключение) — без второго подтверждения отказ, admin с ключом — "
                  "отказ «только владелец», владелец — утверждён", cs["check"]["ok"] and cs["check"]["client_needed"] and cs["check"]["server_needed"]
                  and no and "второе подтверждение" in no and adm_no and "только владелец" in adm_no and shopcs.get(cid)["status"] == "approved",
                  (cs["check"]["errors"], no, adm_no))
            X._run(ctx, "shop.cs_server_dry", cs=cid)
            man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
            check("песочница А4.6: сухой прогон НАСТОЯЩЕГО deploy_changeset — 3 файла FameInfo.txt (база Indun своя)",
                  shopcs.get(cid)["server_state"] == "dry_ok" and sorted(man["files"]) == sorted(g + BS + FAME_REL for g in GS3)
                  and man["files"]["Indun_GameServer" + BS + FAME_REL]["base"] != man["files"]["GameServer" + BS + FAME_REL]["base"],
                  sorted(man["files"]))
            X._run(ctx, "shop.cs_client_dry", cs=cid)
            X._run(ctx, "shop.cs_client_apply", cs=cid)
            now = {r["Id"]: r for r in _csv.DictReader(open(dst, encoding="utf-8-sig", newline=""))}
            check("песочница А4.6: клиент — title_list.csv (Point звания 0, Enabled звания 25), ведомость _value_overlay/title_list.csv, DT_title_list "
                  "подставной очередью UE", shopcs.get(cid)["client_state"] == "applied" and now["0"]["Point"] == str(int(r0["Point"]) * 3)
                  and now["25"]["Enabled"] == "0" and st.assets[SD.DT["title_list"]] == open(dst, "rb").read(), shopcs.get(cid)["client_state"])
            calls0 = len(st.calls)
            g0 = open(st.path("GameServer" + BS + FAME_REL), "rb").read()
            with _Hold(extra={25: [(75010, 1, "Late", 5, False)]}):
                _r, e_g = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            check("песочница А4.6 (перепроверка): у выключаемого звания 25 появился держатель после проверки — выкладка отказ «изменились данные "
                  "стойки … объявления не было» (рестарта не было, FameInfo прежний)", e_g and "изменились данные стойки" in e_g and "Late" in e_g
                  and len(st.calls) == calls0 and open(st.path("GameServer" + BS + FAME_REL), "rb").read() == g0, e_g)
            _FakeWriter.updates = []
            r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            gi = open(st.path("Indun_GameServer" + BS + FAME_REL), "rb").read()
            note = shopcs.get(cid).get("server_note") or ""
            check("песочница А4.6: серверная половина выложена рестартом — очки звания 0 и цель 600 во всех GS, у Indun своё звание 7 сохранено; "
                  "AsdaFamePoints приведена (0 → новые очки), заметка в карточке набора",
                  r and shopcs.get(cid)["server_state"] == "applied" and _line(gi, 0)[42] == str(int(r0["Point"]) * 3).encode()
                  and _line(gi, 0)[3] == b"600 " and _line(gi, 7)[42] == b"12" and _FakeWriter.updates == [(0, int(r0["Point"]) * 3)]
                  and "AsdaFamePoints приведена" in note, (e, note, _FakeWriter.updates))
            _FakeWriter.updates = []
            X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
            X._run(ctx, "shop.cs_client_rollback", cs=cid)
            back = all(open(st.path(rel_), "rb").read() == b for rel_, b in files.items()) and open(dst, "rb").read() == orig
            check("песочница А4.6: откат сервера (rolled_back, AsdaFamePoints снова = FameInfo) и клиента — три FameInfo и title_list.csv вернулись",
                  back and shopcs.get(cid)["server_state"] == "rolled_back" and _FakeWriter.updates == [(0, int(r0["Point"]))],
                  (shopcs.get(cid)["server_state"], _FakeWriter.updates))
        finally:
            db.GameWriter = saved_w
            SD.CLIENT_FILES["title_list"] = real
    check("песочница А4.6: настоящий title_list.csv порта — md5 до = после", real_md5 == SD.md5f(real))


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны на живой стойке (SSH), Joy1 (SELECT) и живом порту (настоящий генератор ItemDB)."""
    from core import config
    from domains import shopcs, shopdata as SD
    from domains.cs_kinds import titledata as TD
    if config.get().on_server:
        return check("живой самотест А4.6 — с ПК (SSH и порт)", True)
    rels = [g + BS + FAME_REL for g in GS3]
    md = SD.live_md5(rels)
    check("живая стойка А4.6: FameInfo.txt трёх GS есть, поле = Ch2", "none" not in md.values()
          and md["GameServer" + BS + FAME_REL] == md["Ch2_GameServer" + BS + FAME_REL], {r: h[:8] for r, h in md.items()})
    lk = TD.lookup("title", "0")
    sr = TD.lookup("titles", "")
    check("живая справка А4.6: звание 0 (3 копии, клиент, держатели из Joy1, AsdaFamePoints), поиск — все записи FameInfo",
          lk["server"]["GameServer"] and lk["client"] and lk["holders"] is not None and lk["fame_points_db"] is not None
          and len(sr["rows"]) == sr["total"] and sr["total"] >= 280, (lk.get("holders_error"), sr["total"]))
    cur = lk["server"]["GameServer"]
    items = [{"pos": 1, "kind": "title.points", "params": {"id": 0, "value": cur["points"] + 1}},
             {"pos": 2, "kind": "title.cond", "params": {"id": 0, "fields": {"target": cur["target"] + 1}}}]
    cli = SD.Client.load(force=True)
    ev = SD.Eval(items, False, SD.Snap(), cli).run()
    s = ev.summary()
    check("живая оценка набора А4.6 (звание 0: очки +1, цель +1): без ошибок, сервер — 3 файла, клиент — 1 правка (Point), держатели прочитаны",
          not s["errors"] and s["server"]["count"] == 3 and len(s["client"]) == 1
          and not any("не прочитано" in w for r in s["positions"] for w in r["warnings"]), s["errors"][:3])
    led = os.path.join(SD.LEDGER_ROOT, "_value_overlay", "title_list.csv")
    tracked = [p for p in (SD.CLIENT_FILES["title_list"], led) if os.path.isfile(p)]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0)
    after = {p: SD.md5f(p) for p in tracked}
    check("живой план клиента А4.6: НАСТОЯЩИЙ генератор ItemDB подтверждает строку ведомости title_list (Point), точечный DT_title_list; ничего не "
          "записано (md5 порта до = после)", not plan["errors"] and any(j["dt"].endswith("DT_title_list") for j in plan["dt_jobs"])
          and before == after, plan["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_a46_live_")
    try:
        man = {"tag": "20261120_a46live", "changeset": 0, "files": {}}
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
        check("НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH (3 файла FameInfo.txt): «всё готово к --apply», стойка не изменилась (md5 до = после)",
              rc == 0 and "всё готово" in out and b0m == b1m, (rc, out[-400:]))
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tmp
        try:
            cs = {"id": 9946, "items": items, "check": s}
            _mp, mman = shopcs.build_server_out(cs, ev)
            sa, now = TD._guard_state(cs, "apply")
            sr_, now2 = TD._guard_state(cs, "rollback")
            g = TD.apply_guard(cs, "apply")
        finally:
            SD.CS_DIR = saved_dir
        rg = "GameServer" + BS + FAME_REL
        check("живая перепроверка А4.6: выкладка — FameInfo из манифеста набора (md5 = новому), откат — живой (база); опасных переходов нет",
              SD.md5b(sa[rg]) == mman["files"][rg]["new"] and SD.md5b(sr_[rg]) == SD.live_md5([rg])[rg] and g == [], g)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _live_r38(check, cli)


def _live_r38(check, cli):
    """★ ревизия 38: живой patches.ini трёх GS (P88), отказ правки цели 192, справка, расхождения (держатели выключенных, наборы,
    AsdaFamePoints) — только чтение."""
    from domains import shopdata as SD, srvtables
    from domains.cs_kinds import titledata as TD
    st = TD.p88_goals()
    on = sorted(g for g, v in (st or {}).items() if v["on"])
    check("живой patches.ini А4.6 (ревизия 38 М-1): [P88_TitleEvents] трёх GS прочитан, пороги 8 званий g_goals в 1…1000000",
          st is not None and set(st) == set(GS3) and all(set(v["thr"]) == set(srvtables.P88_GOALS) and all(1 <= x <= 1000000 for x in v["thr"].values())
                                                          for v in st.values()),
          (TD.p88_goals.last_error, {g: (v["on"], v["thr"].get(192)) for g, v in (st or {}).items()}))
    lk = TD.lookup("title", "192")
    cur = lk["server"]["GameServer"]["target"]
    ev = SD.Eval([{"pos": 1, "kind": "title.cond", "params": {"id": 192, "fields": {"target": cur + 1}}}], False, SD.Snap(), cli).run()
    errs = [e for r in ev.positions for e in r["errors"]]
    tf = [f for f in lk["fields"] if f[0] == "target"][0]
    check("живая оценка А4.6 (ревизия 38 М-1): цель звания 192 +1 — при включённом P88 отказ «порог задаёт patches.ini», при выключенном — "
          "без отказа; справка: порог P88 по копиям, причина у поля цели",
          (any("порог задаёт patches.ini [P88_TitleEvents] Threshold192" in e for e in errs) and tf[5] == TD.UNSAFE["p88_on"]) if on
          else (not errs and tf[5] is None), (on, errs[:2], lk.get("p88")))
    d = {s["key"]: s for s in SD.divergence(limit=1000, areas=("titledata",))["sections"]}["titles"]["rows"]
    unread = [r["why"] for r in d if "не прочитан" in r["why"]]
    held = sorted(r["id"] for r in d if "есть держатели" in r["why"])
    sets = sorted(r["id"] for r in d if "его выдаёт набор" in r["why"])
    fp = [r for r in d if r.get("field") == "AsdaFamePoints"]
    check("живые расхождения А4.6 (ревизия 38 М-2 / К-4): Joy1 прочитан; «выключено, но есть держатели» и «выключено, но его выдаёт набор» "
          "посчитаны; AsdaFamePoints = FameInfo кол. 42 (строк расхождения 0)", not unread and not fp,
          {"unread": unread[:2], "held": held, "sets": sets, "fame_points": fp[:3]})
