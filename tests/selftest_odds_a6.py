# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_odds_a6.py — самотест шага А6.5 «Шансы: выпало против заявленного» (22.11.2026; domains/odds.py, /api/odds/*, web/odds.js,
консоль odds).

offline(check)  — формулы без SciPy на известных значениях (binom.test, χ², Холм, генератор sub_5329A0 перебором), критерий на синтетике
                  генератором MSVC rand с фиксированным зерном (честный шанс не ловит, сдвиг ловит, мало данных — без вывода), разбор
                  свитков и шанса заточки по реверсу (купон шанса 98, купон силы 97, Ev, зона t44, OverUpgrade, свиток 91), розыгрыш
                  Log_GachaItem, разбор журнала шлюза, отказы ввода до базы (без «; »), право econ.view, маршруты, SQL без русских букв
                  и «SELECT *», только чтение, переводы EN (shadowed_translations = 0), веб без innerHTML и с EN всех подписей, консоль,
                  импорт без побочных эффектов.
sandbox(check, ldb) — СВОЯ база LocalDB (JoyLog1: столбцы как на живой 22.11), синтетика на ФИКСИРОВАННЫХ сутках 05.10.2026, период задан
                  явно — от времени запуска тест не зависит. Таблицы сервера — подставные токены. Сверка: попыток = строк, ступени (откат —
                  по предыдущей строке серийника), честный свиток «согласуется», сдвинутый — «отклонение», мало данных, разрушение вне
                  критерия, служебные отдельно и в общем, бустеры (честный / сдвинутый / вне таблицы / без строки / без приза), коробки
                  (равномерно / сдвиг / не по таблице, кэш суток на диске, бюджет журналов — на пользователя, исчерпан — сутки «не
                  прочитаны»), нет таблицы журнала — строка ошибки. Все запросы — чтение.
live(check)     — живая dev: попыток = COUNT(*) UpgradeData, призов + без приза = COUNT(*) BoosterUse, перенос = COUNT(*), коробки за 4 дня =
                  числу строк SEND subtype=2 status=1 журнала шлюза (счёт по SSH), служба на сервере читает таблицы локально, 401 без входа.
Побочных эффектов при импорте нет.
"""
import datetime
import os
import random
import re
import secrets
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CYR = re.compile("[А-Яа-яЁё]")
DAY = datetime.datetime(2026, 10, 5)          # фиксированные сутки синтетики
Q = {"from": "20261001", "to": "20261010"}


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


class Rand:
    """Генератор MSVC rand (LCG 214013 / 2531011) и sub_5329A0(0, top) GameServer — фиксированное зерно."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def rand(self):
        self.s = (self.s * 214013 + 2531011) & 0xFFFFFFFF
        return (self.s >> 16) & 0x7FFF

    def roll(self, top):
        r = (self.rand() << 15 | self.rand()) if top >= 0x7FFF else self.rand()
        return r % (top + 1)


REFUSALS = [("upgrade", {"from": "2026-10-01"}), ("upgrade", {"to": "20261131"}), ("upgrade", {"from": "20261005", "to": "20261001"}),
            ("upgrade", {"from": "20250101", "to": "20261121"}), ("upgrade", {"svc": "all"}), ("boosters", {"alpha": "0.1"}),
            ("boosters", {"logs": "2"}), ("boxes", {"alpha": "x"})]

IU = {70: 70000, 73: 70000, 80: 70000, 91: 100000}      # подставной ItemUpgrade: остальные типы 70…91 — 50000
ITEMS = {20932: {17: 70}, 20942: {17: 80}, 20935: {17: 73}, 20954: {17: 91}, 30001: {24: 3}, 30002: {24: 0}, 25000: {39: 1}, 25001: {39: 2},
         25002: {39: 3}, 25003: {39: 0}}
FUNCS = {496: {5: 98, 6: 30}, 493: {5: 97, 6: 5}, 286: {5: 90, 6: 0}}
T44 = {30001: 8, 30002: 2, 30003: 8}
GACHA = [[(7001, 10), (7002, 30), (7003, 60)], [(7001, 10), (7002, 30), (7003, 60)], [(7001, 50), (7002, 50)]]


def _stub(O):
    """Подставные таблицы сервера (токены как у файлов) и правила предметов. → функция возврата."""
    keep = (O.read_tokens, O.read_lines, O.item_tok, O.func_tok, O.sowel_t44)
    iu = ["22"] + [x for st in range(70, 92) for x in (str(st), "1", "99", str(IU.get(st, 50000)), "3", "0", "0")]
    ov = "5 0 100000 1 80000 2 40000 3 20000 4 0".split()
    ga = [str(len(GACHA))]
    for i, row in enumerate(GACHA):
        pr = list(row) + [(-1, 0)] * (35 - len(row))
        ga += [str(i + 1)] + [x for c, w in pr for x in (str(c), str(w))]
    ur = ["2"] + "0 1 9 0 0 -1 20956 5 85000 20923 10 50000 -1 0 0 60000 400".split() + "1 1 9 1 0 -1 20957 5 30000 -1 0 0 -1 0 0 90000 500".split()
    tok = {"ItemUpgrade.txt": iu, "OverUpgrade.txt": ov, "GachaItemRateTable.txt": ga, "UpperRefineTable.txt": ur,
           "ExtractionRateTable.txt": "1 15000 40000 30000 15000".split()}
    pool = ["40"] + ["%d 0 %d 1" % (i, 100 + i) for i in range(20)] + ["%d 1 %d 1" % (20 + i, 200 + i) for i in range(20)]
    O.read_tokens = lambda name: tok[name]
    O.read_lines = lambda name: pool
    O.item_tok = lambda code, k: ITEMS.get(int(code), {}).get(k, 0) if int(code) in ITEMS else None
    O.func_tok = lambda code, k: FUNCS.get(int(code), {}).get(k, 0) if int(code) in FUNCS else None
    O.sowel_t44 = lambda code: T44.get(int(code), 0)

    def back():
        O.read_tokens, O.read_lines, O.item_tok, O.func_tok, O.sowel_t44 = keep
    return back


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, i18n
    from domains import odds as O
    import domains
    domains.load_all()

    # ---- формулы на известных значениях (эталон — scipy.stats 1.x на ПК: binomtest, chi2.sf)
    ref_b = [((3, 10, 0.1), 0.0701908264), ((7, 20, 0.5), 0.26317596435546875), ((0, 10, 0.5), 0.001953125), ((520, 1000, 0.55), 0.06071759566220519)]
    got_b = [(a, O.binom_test(*a), v) for a, v in ref_b]
    check("шансы: точный биномиальный двусторонний = scipy binomtest на 4 известных значениях (отн. погрешность < 1e-9)",
          all(abs(g - v) <= 1e-9 * max(v, 1e-12) for _a, g, v in got_b), got_b)
    ref_c = [((3.841458820694124, 1), 0.05), ((11.070497693516351, 5), 0.05), ((100, 10), 5.4497019829205215e-17), ((2.5, 30), 0.9999999999932481),
             ((60.48, 45), 0.0613467956569587), ((0.0, 3), 1.0)]
    got_c = [(a, O.chi2_sf(*a), v) for a, v in ref_c]
    check("шансы: хвост χ² (неполная гамма, ряд и цепная дробь) = scipy chi2.sf на 6 значениях (отн. погрешность < 1e-9)",
          all(abs(g - v) <= 1e-9 * max(v, 1e-30) for _a, g, v in got_c), got_c)
    try:
        from scipy import stats as S
        rnd = random.Random(7)
        cases = [(rnd.randint(0, 400), rnd.randint(1, 3)) for _ in range(40)]
        bad = []
        for _ in range(40):
            n = rnd.randint(1, 500)
            k, p = rnd.randint(0, n), rnd.uniform(0.01, 0.99)
            if abs(O.binom_test(k, n, p) - S.binomtest(k, n, p).pvalue) > 1e-9:
                bad.append(("b", k, n, p))
        for x, df in cases:
            xx = x / 3.0
            if abs(O.chi2_sf(xx, df) - S.chi2.sf(xx, df)) > 1e-10:
                bad.append(("c", xx, df))
        check("шансы: на 80 случайных случаях (зерно 7) формулы = SciPy ПК (на службе SciPy нет — модуль его не импортирует)", not bad, bad[:4])
    except ImportError:
        check("шансы: SciPy на ПК нет — сверка со случайными случаями пропущена, известные значения выше", True)
    src = open(os.path.join(ROOT, "domains", "odds.py"), encoding="utf-8").read()
    check("шансы: модуль не импортирует scipy / numpy", "scipy" not in re.sub(r'"""(?:[^"]|"(?!""))*"""', "", src) and "numpy" not in src)
    t = O.holm([{"p": 0.01}, {"p": 0.04}, {"p": 0.03}, {"p": None}])
    check("шансы: поправка Холма — 0.01 / 0.04 / 0.03 → 0.03 / 0.06 / 0.06, «мало данных» без поправки",
          [round(x["p_adj"], 10) if x["p_adj"] is not None else None for x in t] == [0.03, 0.06, 0.06, None])
    brute = sum(1 for r in range(32768) if r % 101 <= 60)
    check("шансы: генератор sub_5329A0(0, 100) ≤ 60 — перебор всех 32 768 rand() = формуле (%d)" % brute,
          O.roll_count(100, 0, 61) == (brute, 32768) and abs(O.roll_p(100, 0, 61) - brute / 32768.0) < 1e-15)
    q, rem = divmod(1 << 30, 100001)
    check("шансы: sub_5329A0(0, 100000) — 30 бит, бросок 100000 тоже возможен: шанс 100000 даёт 1 − q / 2³⁰, шанс 70000 — 70000·q + min(70000, rem)",
          O.roll_count(100000, 0, 100000)[0] == (1 << 30) - q and O.roll_count(100000, 0, 70000)[0] == 70000 * q + min(70000, rem)
          and O.roll_p(100000, 0, 100001) == 1.0)

    # ---- критерий на синтетике (генератор GameServer, фиксированное зерно)
    R = Rand(12345)
    honest = sum(1 for _ in range(2000) if R.roll(100000) < 70000)
    shifted = sum(1 for _ in range(2000) if R.roll(100000) < 66000)
    p7 = O.roll_p(100000, 0, 70000)
    a, b, c = O.binom_case(honest, 2000, p7), O.binom_case(shifted, 2000, p7), O.binom_case(5, 10, p7)
    O.holm([a, b])
    check("шансы: честный шанс 70%% (2000 попыток генератором сервера) — согласуется (p = %.3f), сдвиг 70 → 66%% — отклонение (p = %.2g)" % (a["p"], b["p"]),
          O.verdict(a, 0.01) == "ok" and O.verdict(b, 0.01) == "deviation", (a, b))
    check("шансы: 10 попыток — «мало данных» без вывода (p не считается)", c["few"] and c["p"] is None and O.verdict(c, 0.01) == "few")
    d = O.binom_case(99, 100, 1.0)
    check("шансы: шанс 1 — без статистики: одна неудача = «противоречит таблице»", d["det"] and O.verdict(d, 0.01) == "contradiction")
    # ★ ревизия 55 В-1: «100 %» сервера = 1 − 1e-5 (бросок 0…100000) — расхождение видно при любом n; мало данных — только n < 30
    p100, p1 = O.roll_p(100000, 0, 100000), O.roll_p(100000, 0, 1)
    nr = [O.binom_case(1100, 1211, p100), O.binom_case(1211, 1211, p100), O.binom_case(9, 10, p100), O.binom_case(10, 10, p100),
          O.binom_case(3, 40, p1), O.binom_case(0, 40, p1), O.binom_case(5, 10, 0.5), O.binom_case(25, 40, 0.5)]
    O.holm(nr)
    vr = [O.verdict(x, 0.01) for x in nr]
    check("шансы (ревизия 55 В-1): шанс 100000 — 1100 из 1211 и 9 из 10 «противоречит таблице», 1211 из 1211 «согласуется», 10 из 10 — мало "
          "данных; шанс 1 из 100001 — 3 успеха из 40 «противоречит», 0 из 40 «согласуется»; обычный шанс — мало данных только при n < 30 (ожидание "
          "≥ 5 точному критерию не нужно)", vr == ["contradiction", "ok", "contradiction", "few", "contradiction", "ok", "few", "ok"]
          and nr[0]["near"] and nr[0]["p"] < 1e-100 and not nr[7]["few"], (vr, [x["p"] for x in nr]))
    w = [(7001, 10), (7002, 30), (7003, 60)] + [(-1, 0)] * 32
    probs, total, miss = O._booster_probs(w)
    obs_h, obs_s = {}, {}
    act = [(cd, ww) for cd, ww in w if cd > 0 and ww > 0]

    def draw(weights):
        while True:
            v = R.roll(sum(x for _c, x in weights))
            cum = 0
            for cd, ww in weights:
                if cum <= v < cum + ww:
                    return cd
                cum += ww
    for _ in range(3000):
        k = draw(act)
        obs_h[k] = obs_h.get(k, 0) + 1
    for _ in range(3000):
        k = draw([(7001, 14), (7002, 30), (7003, 56)])
        obs_s[k] = obs_s.get(k, 0) + 1
    g1, g2 = O.gof_case(obs_h, probs), O.gof_case(obs_s, probs)
    O.holm([g1, g2])
    check("шансы: бустер — честные веса 10/30/60 (3000 вскрытий) согласуются, 14/30/56 — отклонение; условие «не промах» (сумма вероятностей = 1, "
          "промах %.4f)" % miss, O.verdict(g1, 0.01) == "ok" and O.verdict(g2, 0.01) == "deviation" and abs(sum(probs.values()) - 1) < 1e-12
          and total == 100, (g1["p"], g2["p"]))
    g3 = O.gof_case({7001: 3, 7009: 1}, probs)
    check("шансы: приз вне строки таблицы — «противоречит таблице», мало вскрытий — мало данных", g3["contradiction"] and g3["outside"] == [(7009, 1)]
          and O.verdict(g3, 0.01) == "contradiction" and O.gof_case({7001: 3}, probs)["few"])
    g4 = O.gof_case(dict(list(obs_h.items()) + [(7009, 4)]), probs, stale=True)
    check("шансы (ревизия 55 Н-5): у бустера приз вне текущей строки — «не по текущей таблице» (вне критерия, счёт 4), не «противоречит»",
          not g4["contradiction"] and g4["stale"] == 4 and g4["n"] == 3000 and abs(g4["p"] - g1["p"]) < 1e-12, (g4["stale"], g4["n"]))

    # ---- заточка: свитки и шанс по реверсу
    back = _stub(O)
    try:
        iu, ov = O.item_upgrade(), O.over_upgrade()
        c1 = O.classify([20932, 496, 493])
        c2 = O.classify([286, 496])
        c3 = O.classify([20932, 20942])
        check("шансы: свитки попытки — Item_Table основной (Kind 1, тип t17), функция 98 — купон шанса (+t6), 97 — купон силы; без свитка Item_Table — "
              "Kind 2 (основной — купон не 97/98); два свитка Item_Table — не определён",
              (c1["kind"], c1["main"], c1["st"], c1["rate"], c1["has_power"]) == (1, 20932, 70, 30, True) and (c2["kind"], c2["main"], c2["st"], c2["rate"])
              == (2, 286, 90, 30) and c3["why"] == "scroll_unknown", (c1, c2, c3))
        ch = [O.chance(70, 0, 1, 3, 3, 8, iu, ov), O.chance(70, 30, 1, 3, 3, 8, iu, ov), O.chance(70, 0, 1, 9, 9, 8, iu, ov),
              O.chance(70, 0, 2, 2, 10, 8, iu, ov), O.chance(91, 0, 1, 12, 12, 8, iu, ov), O.chance(70, 0, 1, 13, 13, 8, iu, ov), O.chance(99, 0, 1, 0, 0, 8, iu, ov)]
        check("шансы: шанс заточки = GameServer.c:98933-98957 — 70000; +1000×30; зона t44 (AcuUpcnt ≥ t44) × OverUpgrade[ступень − t44] (80000/100000 "
              "→ 56000); Kind 2 — всегда с множителем (k = 2 → 28000); свиток 91 — 100000 даже за пределом; k вне OverUpgrade — нет строки; тип вне "
              "ItemUpgrade — нет строки",
              [x[0] for x in ch] == [70000, 100000, 56000, 28000, 100000, None, None] and ch[2][1:3] == ("over", 1) and ch[5][3] == "over_no_row"
              and ch[6][3] == "no_table_row", ch)
        key = (DAY, 9001, 0, 30001)
        rows = [{"Edate": DAY, "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 4, "acu": 4, "flag": 1, "Ev": "Upgrade", "pup": 3, "pacu": 3},
                {"Edate": DAY + datetime.timedelta(seconds=1), "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 4, "acu": 5, "flag": 0,
                 "Ev": "Successful upgrades", "pup": 4, "pacu": 4},
                {"Edate": DAY + datetime.timedelta(seconds=2), "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 0, "acu": 0, "flag": 0,
                 "Ev": "Upgrade", "pup": 9, "pacu": 9},
                {"Edate": DAY + datetime.timedelta(seconds=3), "Userindex": 9001, "Charidx": 0, "Code": 30002, "up": 6, "acu": 6, "flag": 0,
                 "Ev": "Destroyed-Limitless Upgrade", "pup": 6, "pacu": 6},
                {"Edate": DAY + datetime.timedelta(seconds=4), "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 2, "acu": 3, "flag": 0,
                 "Ev": "Upgrade", "pup": 2, "pacu": 2}]
        sc = {key: [20932], (rows[1]["Edate"], 9001, 0, 30001): [20932, 496], (rows[2]["Edate"], 9001, 0, 30001): [20932],
              (rows[4]["Edate"], 9001, 0, 30001): [20932, 496]}
        # ★ ревизия 55 Н-2 / Н-3: откат с MaxCnt 6 при текущем t44 = 8 — «t44 менялся»; успех с MaxCnt + 1 (зона), а по текущему t44 — обычная зона —
        #   тоже; неудача без отката при прогнозе «зона t44» — против правила; успех в зоне у предмета t24 ≠ 3 — исход виден наполовину
        extra = [{"Edate": DAY + datetime.timedelta(seconds=5), "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 0, "acu": 0, "mx": 6, "flag": 0,
                  "Ev": "Upgrade", "pup": 7, "pacu": 7, "pmx": 7},
                 {"Edate": DAY + datetime.timedelta(seconds=6), "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 7, "acu": 7, "mx": 8, "flag": 1,
                  "Ev": "Upgrade", "pup": 6, "pacu": 6, "pmx": 7},
                 {"Edate": DAY + datetime.timedelta(seconds=7), "Userindex": 9001, "Charidx": 0, "Code": 30001, "up": 9, "acu": 10, "mx": 9, "flag": 0,
                  "Ev": "Upgrade", "pup": 9, "pacu": 9, "pmx": 9},
                 {"Edate": DAY + datetime.timedelta(seconds=8), "Userindex": 9001, "Charidx": 0, "Code": 30002, "up": 4, "acu": 4, "mx": 5, "flag": 1,
                  "Ev": "Upgrade", "pup": 3, "pacu": 3, "pmx": 4}]
        for x in extra:
            sc[(x["Edate"], 9001, 0, x["Code"])] = [20932]
        ax = O.attempts(extra, sc, iu, ov)
        check("шансы (ревизия 55 Н-2/Н-3): вне критерия с причиной — откат с MaxCnt ≠ t44 и успех «в зоне» по MaxCnt + 1 при обычной зоне по текущему "
              "t44 (t44_changed), неудача без отката в зоне t44 (rule_bad), успех в зоне у предмета t24 ≠ 3 (half_observed); шанса для критерия нет",
              [x["why"] for x in ax] == ["t44_changed", "t44_changed", "rule_bad", "half_observed"] and all(x["prob"] is None for x in ax)
              and O._scroll_groups(ax)[0]["rule_bad"] == 2 and O._scroll_groups(ax)[0]["n"] == 0, [(x["why"], x["zone"]) for x in ax])
        at = O.attempts(rows, sc, iu, ov)
        check("шансы: попытки — Flag 1 = успех (ступень до = Upcnt − 1), Flag 0 вне зоны — неудача (ступень = Upcnt), откат (0/0) — ступень до по "
              "предыдущей строке серийника (9), разрушение — вне критерия (свитки не пишутся), Ev «Upgrade» при купоне шанса — вне критерия",
              [(x["outcome"], x["up_b"], x["why"]) for x in at] == [("success", 3, None), ("fail", 4, None), ("reset", 9, None),
                                                                    ("destroy", 6, "destroy_noscroll"), ("fail", 2, "ev_mismatch")]
              and at[2]["zone"] == "over" and at[2]["k"] == 1 and at[2]["rule"] is True and at[1]["c"] == 100000, at)
        lines = ["10 Mon 05 Day 10 hou 00 min 00 sec : Recv_GachaItemUse() UserIndex = 9001, TotalRate=100, Rate=5, Code=7001, Gacha=25000",
                 "10 Mon 05 Day 10 hou 00 min 01 sec : Recv_GachaItemUse() UserIndex = 9001, TotalRate=100, Rate=50, Code=7001, Gacha=25000",
                 "10 Mon 05 Day 10 hou 00 min 02 sec : Recv_GachaItemUse() UserIndex = 9001, TotalRate=90, Rate=50, Code=7003, Gacha=25000",
                 "10 Mon 05 Day 10 hou 00 min 02 sec : Send_GachaItemUse() UserIndex = 9001, Code=7003, Gacha=25000, Weight=1"]
        ev = O.parse_gacha_log(lines, "2026")
        rp = O.replay(ev, O.gacha_rows())
        check("шансы: Log_GachaItem — разбор (год из имени файла), розыгрыш по текущей строке: бросок 5 → 7001 (совпал), 50 → 7003 (в журнале 7001 — "
              "не совпал), другая сумма весов — таблица была иной",
              len(ev) == 3 and ev[0]["t"] == datetime.datetime(2026, 10, 5, 10, 0, 0) and (rp["match"], rp["mismatch"], rp["other_total"]) == (1, 1, 1)
              and rp["bad"][0]["want"] == 7003, rp)
    finally:
        back()
    ln = ('2026-10-05 10:00:00.000 SEND 1.2.3.4:5 bytes=188 command=0x0051 account="x" source=sql status=1 order=7 subtype=2 userIndex=9001 '
          'userNum=0 requestItemCode=2 itemCode=101 rewardIndex=1 rewardCount=1 requestedPrice=690 price=690 balance=1 present=0 hex=AA')
    pl = O.parse_lucky([ln, ln.replace("status=1", "status=0"), ln.replace("subtype=2", "subtype=1")])
    check("шансы: журнал шлюза — только SEND 0x0051 status=1 subtype=2; код — itemCode (не requestItemCode), строка — rewardIndex",
          pl == [{"t": "2026-10-05 10:00:00", "uid": 9001, "code": 101, "index": 1, "count": 1}], pl)

    # ---- отказы ввода
    why = [_refused(lambda f=f, q=q: O.check_input(q, f)) for f, q in REFUSALS]
    check("шансы: неверный ввод — отказ до базы (%d случаев: даты, период, служебные, уровень значимости, журнал)" % len(REFUSALS), all(why),
          [(REFUSALS[i], w) for i, w in enumerate(why) if not w])
    check("шансы: тексты отказов без «; »", all("; " not in w for w in why if w))
    check("шансы: upgrade проверяет ввод до обращения к базе", _refused(lambda: O.upgrade({"from": "20261005", "to": "20261001"})) == "дата «с» позже даты «по»")

    # ---- права, маршруты, SQL
    roles = ("owner", "admin", "gm", "support")
    paths = ("/api/odds/upgrade", "/api/odds/boosters", "/api/odds/boxes")
    rt = {p: _route(p) for p in paths}
    check("шансы: маршруты %s — GET, право econ.view (owner, admin)" % ", ".join(paths), all(fn and perm == "econ.view" for fn, perm in rt.values())
          and {r for r in roles if auth.can(r, "econ.view")} == {"owner", "admin"}, {p: v[1] for p, v in rt.items()})
    srv = open(os.path.join(ROOT, "api", "server.py"), encoding="utf-8").read()
    check("шансы: бюджет чтения журналов — на пользователя запроса (session.user.login) у бустеров и коробок",
          'odds.boosters(req.query, req.session["user"]["login"])' in srv and 'odds.boxes(req.query, req.session["user"]["login"])' in srv)
    sqls = [getattr(O, n) for n in dir(O) if n.startswith("SQL_")]
    check("шансы: SQL модуля (%d запросов) — только SELECT, без русских букв и «SELECT *», даты — параметрами CONVERT(datetime2, ?, 112)" % len(sqls),
          sqls and all(s.lstrip().upper().startswith("SELECT") and not CYR.search(s) and "select *" not in s.lower()
                       and not re.search(r"\b(INSERT|UPDATE|DELETE|EXEC|MERGE)\b", s) for s in sqls) and "CONVERT(datetime2, ?, 112)" in O.WINDOW)
    code = re.sub(r'"""(?:[^"]|"(?!""))*"""', "", src)
    check("шансы: модуль не пишет в базы (нет GameWriter, admin(), операций)", "GameWriter" not in code and "db.admin(" not in code and "@register" not in code)

    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [w for w in why if w] + ["журнал шансов UpgradeData не прочитан: запрос к joylog1: Invalid object name", "таблица сервера ItemUpgrade.txt не прочитана: x",
                                      "журнал Log_GachaItem GameServer не прочитан: x", "журнал шлюза gp7 gp7-20261005.log не прочитан: x",
                                      "журнал CachaItemLog_20261005.txt прочитан не целиком (больше 16 МБ)", "журналы JoyLog1 не прочитаны: x",
                                      "заточка без таблиц сервера ItemUpgrade / OverUpgrade не сравнивается",
                                      "суток журнала шлюза не прочитано: 3 (бюджет чтения журналов на пользователя исчерпан — прочитанное запомнено, повторите через минуту)"]
        miss = [x for x in ru if CYR.search(i18n.tr(x))]
        check("шансы EN: отказы, ошибки чтения (причина — вложенным переводом), пометки — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("шансы: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])

    # ---- веб
    js = open(os.path.join(ROOT, "web", "odds.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("шансы веб: раздел #/odds с правом econ.view, значок itemstrength (окна игры), маршрут viewOdds, скрипт после trade.js",
          '["#/odds", "Шансы: выпало против заявленного", "econ.view", "itemstrength"]' in app and 'case "odds": return viewOdds(my);' in app
          and idx.index("/trade.js") < idx.index("/odds.js") and os.path.isfile(os.path.join(ROOT, "web", "skin", "winicon_itemstrength.png")))
    check("шансы веб: без innerHTML, данные — текстовыми узлами (acText / itemLine), даты ГГГГММДД (acDay), служебные — переключатель svc=in",
          "innerHTML" not in js and "itemLine(" in js and "acDay(" in js and 'svcIn.checked ? "in" : "sep"' in js
          and not re.search(r"T\((?:x|r|p|c|e|s|d|g|a|i|f|t|b|o)\.", js))
    labels = re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|b|div)", (?:null|\{[^}]*\}), "([^"]+)"', js)
    labels += re.findall(r'\["([^"]+)", \w+ =>', js) + re.findall(r'T\("([^"]+)"', js) + re.findall(r'h\("label", null, \w+, "([^"]+)"\)', js)
    for m in re.findall(r"const OD_\w+ = \{([^}]*)\}", js, re.S):
        labels += re.findall(r':\s*"([^"]+)"', m)
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted({x for x in labels if x not in have and CYR.search(x)})
    check("шансы веб EN: у всех подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(set(labels)), not lack and len(set(labels)) > 80, lack[:8])
    rx = r'(?:^|[{,])\s*"((?:[^"\\]|\\.)+)":\s*"'
    blk = wi[wi.index("// ★ А6.5"):]
    kb = re.findall(rx, blk, re.M)
    earlier = set(re.findall(rx, wi[:wi.index("// ★ А6.5")], re.M))
    check("шансы веб EN: новые ключи web/i18n.js не повторяют прежние и друг друга (%d ключей)" % len(kb), kb and len(kb) == len(set(kb)) and not set(kb) & earlier,
          sorted(set(kb) & earlier)[:5])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "odds.js")], capture_output=True, timeout=60)
        check("шансы: node --check web/odds.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("шансы: node --check web/odds.js (node не запустился)", False, str(ex))

    # ---- консоль, импорт
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "odds"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("upgrade", "--bogus")
    c2, o2 = con("boosters", "--alpha")
    c3, o3 = con("nope")
    c4, o4 = con("boxes", "extra")
    c5, o5 = con("upgrade", "--from", "20261005", "--to", "20261001")
    c6, o6 = con("boxes", "--alpha", "0.2")
    check("шансы консоль: неизвестный ключ, ключ без значения, неизвестное действие, лишнее слово, неверный период и уровень — отказ без базы",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3 and c4
          and "неизвестный аргумент extra" in o4 and c5 and "позже" in o5 and c6 and "уровень значимости" in o6,
          (o1[-200:], o2[-200:], o3[-200:], o4[-200:], o5[-200:], o6[-200:]))
    hp = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "--help"], capture_output=True, timeout=60, cwd=ROOT,
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL)
    check("шансы консоль: --help печатает справку с командой odds (ничего не делает)", hp.returncode == 0 and "  odds …" in hp.stdout.decode("utf-8", "replace"))
    imp = subprocess.run([py, "-c", "import sys; sys.path.insert(0, %r); from core import db; from domains import odds; "
                          "print('IMPORT_OK', len(db._pw), len(db._override), len(odds._mem), len(odds._tok_cache))" % ROOT],
                         capture_output=True, timeout=60, cwd=ROOT, stdin=subprocess.DEVNULL)
    check("шансы: импорт domains/odds.py ничего не делает (пароль не читан, соединений нет, кэши пусты)", b"IMPORT_OK 0 0 0 0" in imp.stdout,
          (imp.stdout + imp.stderr)[-300:])


# ---------------------------------------------------------------- стенд LocalDB
SCHEMA = {
    "UpgradeData": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Upcnt TINYINT, AcuCnt TINYINT, MaxCnt TINYINT, "
                   "Updamage SMALLINT, Flag TINYINT, Ev VARCHAR(100)",
    "UpgradeScroll": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Scode INT, Amount INT, Ramount INT, Flag TINYINT, "
                     "Ev VARCHAR(100)",
    "UpperRefine": "Edate DATETIME, Userindex INT, Charidx TINYINT, Ucode INT, Opidx SMALLINT, Opvalue SMALLINT, Code1 INT, Amount1 INT, Code2 INT, "
                   "Amount2 INT, Code3 INT, Amount3 INT, Gm INT, Flag TINYINT",
    "UpgradeTransplantUse": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Upcount TINYINT, AcuUpcnt TINYINT, "
                            "MaxUpcnt TINYINT, Updamage SMALLINT, Opidx4 SMALLINT, OPvalue4 SMALLINT, Flag TINYINT",
    "Stat_UpgradeSeparation": "Edate DATETIME, Userindex INT, Charidx TINYINT, State TINYINT, Ucode INT, Gcode INT, Scode1 INT, Scode2 INT, Scode3 INT, "
                              "Scode4 INT, Scode5 INT, Scode6 INT, Scode7 INT, Scode8 INT",
    "ItemUpgrade": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Amount INT, Ramount INT, Gm INT, State VARCHAR(100)",
    "BoosterUse": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36)",
    "BoosterGain": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Ramount INT",
    "BoosterGainFunctional": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Ramount INT",
    "BoosterGainGear": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36), Cell1 SMALLINT",
    "BoosterGainSowel": "Edate DATETIME, Userindex INT, Charidx TINYINT, Code SMALLINT, Serial VARCHAR(36)",
}
for _t in ("GaChaTranFunctional", "GaChaTranNostack", "GaChaTranSowel", "GaChaTranGearitem"):
    SCHEMA[_t] = "Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(36)"


def _gen_upgrade(R):
    """Синтетика заточки генератором сервера: (строки UpgradeData, строки UpgradeScroll, что ожидать)."""
    ud, us = [], []
    t = [DAY]

    def at():
        t[0] += datetime.timedelta(seconds=1)
        return t[0]

    def one(uid, code, serial, up, acu, scroll, chance, rate=False, ev="Upgrade"):
        """Попытка вне зоны t44: успех — ступень + 1."""
        ok = R.roll(100000) < chance
        e = at()
        ud.append((e, uid, 0, code, serial, up + 1 if ok else up, acu + 1, 8, 0, 1 if ok else 0, ev))
        us.append((e, uid, 0, scroll, "S", code, 5, 4, 1 if ok else 0, ev))
        if rate:
            us.append((e, uid, 0, 496, "R", code, 5, 4, 1 if ok else 0, ev))
        return (up + 1 if ok else up), acu + 1, ok
    exp = {"ok_honest": 0, "ok_shift": 0}
    for i in range(300):                                  # 20932 (тип 70, 70%) — честно; ступени 0…3
        up = i % 4
        _u, _a, ok = one(9001, 30003, "H%d" % i, up, up, 20932, 70000)
        exp["ok_honest"] += ok
    for i in range(300):                                  # 20942 (тип 80, заявлено 70%) — на деле 55%
        up = i % 4
        _u, _a, ok = one(9002, 30003, "X%d" % i, up, up, 20942, 55000)
        exp["ok_shift"] += ok
    for i in range(10):                                   # 20935 — 10 попыток: мало данных
        one(9001, 30003, "F%d" % i, 1, 1, 20935, 70000)
    for i in range(40):                                   # служебная учётка 3: тот же честный свиток
        one(3, 30003, "V%d" % i, 2, 2, 20932, 70000)
    # серийник Z: ступень 9 (t44 = 8, зона) → неудача → откат в 0 (предмет t24 = 3) — ступень до по предыдущей строке
    e = at()
    ud.append((e, 9001, 0, 30001, "Z", 9, 9, 9, 50, 1, "Upgrade"))
    us.append((e, 9001, 0, 20932, "S", 30001, 5, 4, 1, "Upgrade"))
    e = at()
    ud.append((e, 9001, 0, 30001, "Z", 0, 0, 8, 0, 0, "Upgrade"))
    us.append((e, 9001, 0, 20932, "S", 30001, 5, 4, 0, "Upgrade"))
    # разрушение (предмет t24 ≠ 3): значения ДО, свитков нет
    ud.append((at(), 9001, 0, 30002, "D", 4, 4, 4, 30, 0, "Destroyed-Limitless Upgrade"))
    # купон шанса: Ev «Successful upgrades», шанс 100000
    e = at()
    ud.append((e, 9001, 0, 30003, "C", 1, 1, 8, 0, 1, "Successful upgrades"))
    us += [(e, 9001, 0, 20932, "S", 30003, 5, 4, 1, "Successful upgrades"), (e, 9001, 0, 496, "R", 30003, 5, 4, 1, "Successful upgrades")]
    # ★ ревизия 55 Н-2: откат с MaxCnt 6 при текущем t44 = 8 (SowelCombine менялась) — вне критерия; Н-3: успех в зоне у предмета t24 ≠ 3
    e = at()
    ud.append((e, 9001, 0, 30001, "Y", 7, 7, 7, 40, 1, "Upgrade"))
    us.append((e, 9001, 0, 20954, "S", 30001, 5, 4, 1, "Upgrade"))
    e = at()
    ud.append((e, 9001, 0, 30001, "Y", 0, 0, 6, 0, 0, "Upgrade"))
    us.append((e, 9001, 0, 20932, "S", 30001, 5, 4, 0, "Upgrade"))
    e = at()
    ud.append((e, 9001, 0, 30002, "W", 4, 4, 5, 20, 1, "Upgrade"))
    us.append((e, 9001, 0, 20932, "S", 30002, 5, 4, 1, "Upgrade"))
    # до периода (01.09) — не считается
    ud.append((DAY - datetime.timedelta(days=34), 9001, 0, 30003, "OLD", 1, 1, 8, 0, 1, "Upgrade"))
    return ud, us, exp


def _gen_boosters(R):
    """Синтетика бустеров: (BoosterUse, BoosterGainSowel, ожидания)."""
    uses, gains = [], []
    t = [DAY + datetime.timedelta(hours=5)]

    def draw(weights):
        while True:                                      # промах (бросок = сумме весов) бустер не тратит — в базе его нет, бросаем снова
            v = R.roll(sum(w for _c, w in weights))
            cum = 0
            for c, w in weights:
                if cum <= v < cum + w:
                    return c
                cum += w

    def add(uid, booster, prize):
        t[0] += datetime.timedelta(seconds=1)
        uses.append((t[0], uid, 0, booster, "B"))
        if prize is not None:
            gains.append((t[0], uid, 0, prize, "G"))
    honest = [(7001, 10), (7002, 30), (7003, 60)]
    for _ in range(600):
        add(9001, 25000, draw(honest))                     # строка 1 — честно
    for _ in range(600):
        add(9002, 25001, draw([(7001, 25), (7002, 30), (7003, 45)]))   # строка 2 — сдвиг
    for _ in range(3):
        add(9001, 25002, 7001)
    add(9001, 25002, 7009)                                 # строка 3: приз вне таблицы
    add(9001, 25003, 7001)                                 # у бустера нет строки (t39 = 0)
    add(9001, 25000, None)                                 # вскрытие без приза
    for _ in range(20):
        add(3, 25000, draw(honest))                        # служебная
    return [u for u in uses], [g for g in gains if g[3] is not None]


def sandbox(check, ldb):
    """Своя база LocalDB: заточка, бустеры, коробки, нет таблицы."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import db
    from domains import logs, odds as O
    import domains
    domains.load_all()
    tag = secrets.token_hex(3)
    name = "AsdaOdG_" + tag
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Arabic_CI_AS" % name)
    back = _stub(O)
    saved = (O._listing, O._scan_cached, O.CACHE_DIR, O.gacha_log, O.crtjin_refusals)
    tmp = tempfile.mkdtemp(prefix="odds_a65_")
    try:
        gc = ldb(name).cursor()
        for tb, spec in SCHEMA.items():
            gc.execute("CREATE TABLE dbo.%s (%s)" % (tb, spec))
        R = Rand(2026)
        ud, us, exp = _gen_upgrade(R)
        gc.executemany("INSERT dbo.UpgradeData VALUES (?,?,?,?,?,?,?,?,?,?,?)", ud)
        gc.executemany("INSERT dbo.UpgradeScroll VALUES (?,?,?,?,?,?,?,?,?,?)", us)
        # высшая переработка: рецепт 0 (шанс 60000, материалы 20956×5 потеря 85000, 20923×10 потеря 50000), 200 попыток честно
        for i in range(200):
            ok = R.roll(100000) < 60000
            a1 = 5 if ok or R.roll(100000) < 85000 else 0
            a2 = 10 if ok or R.roll(100000) < 50000 else 0
            gc.execute("INSERT dbo.UpperRefine VALUES (?,?,0,30003,1,1,20956,?,20923,?,-1,0,400,?)", (DAY + datetime.timedelta(minutes=i), 9001, a1, a2, 1 if ok else 0))
        for i in range(100):                                # перенос: порог 60 из 0…100 — честно
            gc.execute("INSERT dbo.UpgradeTransplantUse VALUES (?,9001,0,30003,'T',1,1,8,0,-1,0,?)", (DAY + datetime.timedelta(minutes=i),
                                                                                                   1 if R.roll(100) <= 60 else 0))
        for st in (1, 2, 2, 3):
            gc.execute("INSERT dbo.Stat_UpgradeSeparation VALUES (?,9001,0,?,30003,0,0,0,0,0,0,0,0,0)", (DAY, st))
        gc.execute("INSERT dbo.ItemUpgrade VALUES (?,9001,0,30003,'U',0,1,100,'Item upgrade all reset')", (DAY,))
        gc.execute("INSERT dbo.GaChaTranGearitem VALUES (?,9001,0,30003,'G')", (DAY,))
        bu, bg = _gen_boosters(R)
        gc.executemany("INSERT dbo.BoosterUse VALUES (?,?,?,?,?)", bu)
        gc.executemany("INSERT dbo.BoosterGainSowel VALUES (?,?,?,?,?)", bg)
        db.set_override("game", lambda database: ldb(name if database.lower() == "joylog1" else database))
        seen = []
        orig = db.GameReader.rows

        def spy(self, sql, params=()):
            seen.append(sql)
            return orig(self, sql, params)
        db.GameReader.rows = spy
        try:
            _checks(check, O, logs, gc, ud, exp, bu, tmp)
        finally:
            db.GameReader.rows = orig
        check("шансы стенд: все %d запросов к игровой базе — чтение, без русских букв и «SELECT *»" % len(seen),
              seen and not any(CYR.search(s) or "select *" in s.lower() for s in seen))
    finally:
        O._listing, O._scan_cached, O.CACHE_DIR, O.gacha_log, O.crtjin_refusals = saved
        back()
        db.set_override("game", None)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        m2 = ldb("master")
        try:
            m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m2.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def _checks(check, O, logs, gc, ud, exp, bu, tmp):
    # ---- заточка
    r = O.upgrade(dict(Q))
    s, v = r["main"], r["service"]
    inper = [x for x in ud if x[0] >= DAY - datetime.timedelta(days=4)]
    check("шансы стенд: период задан явно (%s — %s), попыток игроков + служебных = строк UpgradeData за период (%d), строка до периода не считается"
          % (Q["from"], Q["to"], len(inper)), not r["errors"] and s["attempts"] + v["attempts"] == len(inper) and v["attempts"] == 40, r["errors"])
    gr = {(g["scroll"], g["rate"], g["zone"]): g for g in s["groups"]}
    h, x = gr[(20932, 0, "normal")], gr[(20942, 0, "normal")]
    check("шансы стенд: честный свиток 20932 (70%%, %d из 300) — согласуется; 20942 заявлен 70%%, выпадает 55%% (%d из 300) — отклонение (с поправкой Холма)"
          % (exp["ok_honest"], exp["ok_shift"]), h["success"] == exp["ok_honest"] and h["n"] == 300 and h["verdict"] == "ok"
          and x["success"] == exp["ok_shift"] and x["verdict"] == "deviation" and x["p_adj"] >= x["p"], (h["verdict"], h["p"], x["verdict"], x["p"]))
    f = gr[(20935, 0, "normal")]
    check("шансы стенд: 10 попыток свитка 20935 — «мало данных», без p", f["verdict"] == "few" and f["p"] is None and f["n"] == 10)
    z = [a for a in s["stages"] if a["stage"] == 9]
    check("шансы стенд: откат в 0 (Flag 0, Upcnt 0, AcuCnt 0) — ступень до 9 по предыдущей строке серийника; разрушение — в ступенях, вне критерия",
          z and z[0]["reset"] == 1 and s["outcomes"]["destroy"] == 1 and s["excluded"].get("destroy_noscroll") == 1 and s["rule_bad"] == 0,
          (z, s["excluded"], s["rule_bad"]))
    off = {k: v for k, v in s["excluded"].items() if k in ("t44_changed", "half_observed")}
    check("шансы стенд (ревизия 55 Н-2/Н-3): откат с MaxCnt 6 при t44 = 8 — «t44 менялся», успех в зоне у предмета t24 ≠ 3 — «исход виден наполовину»; "
          "оба вне критерия и видны у своей группы", off == {"t44_changed": 1, "half_observed": 1}
          and sum(g["rule_bad"] for g in s["groups"]) == 2, (s["excluded"], [(g["scroll"], g["zone"], g["off"]) for g in s["groups"] if g["off"]]))
    check("шансы стенд: купон шанса (функция 98, +30) — своя группа, Ev «Successful upgrades»; шанс 100000 — мало данных (неудача ~1e-5)",
          (20932, 30, "normal") in gr and gr[(20932, 30, "normal")]["c"] == 100000)
    check("шансы стенд: высшая переработка — шанс рецепта 60000 согласуется, потеря материалов при неудаче (85000, 50000) — свои проверки; перенос "
          "(порог 60) согласуется; извлечение 4 строки — мало данных; сброс и обмен — счёт",
          [t["c"] for t in s["refine"]] == [60000] and s["refine"][0]["verdict"] == "ok" and {t["c"] for t in s["refine_loss"]} == {85000, 50000}
          and s["bless"]["n"] == 100 and s["bless"]["verdict"] == "ok" and s["extract"]["verdict"] == "few" and s["extract"]["obs"] == {"0": 1, "1": 2, "2": 1}
          and s["reset"] == [{"state": "Item upgrade all reset", "n": 1}] and s["tran"] == 1, (s["refine"], s["bless"], s["extract"]))
    ri = O.upgrade(dict(Q, svc="in"))
    check("шансы стенд: служебные ≤ 5000 — отдельным разделом (40 попыток), svc=in — в общем (раздела служебных нет)",
          ri["service"] is None and ri["main"]["attempts"] == s["attempts"] + 40 and v["groups"][0]["n"] == 40)
    # ---- бустеры
    O.gacha_log = lambda f, t, today, user, errors, notes: (seen_user.append(user) or [])
    O.crtjin_refusals = lambda f, t, today, user, errors: (seen_user.append(user) or {"13": 2})
    seen_user = []
    b = O.boosters(dict(Q), "alice")
    rows = {t["row"]: t for t in b["main"]["rows"]}
    check("шансы стенд: бустеры — призов + без приза = строк BoosterUse (%d), честная строка 1 согласуется, сдвинутая строка 2 — отклонение, "
          "приз вне строки 3 — «не по текущей таблице» (вне критерия), вскрытие без приза — у игроков, бустер без строки (t39 = 0) — отдельно, служебные отдельно" % len(bu),
          b["main"]["draws"] + b["service"]["draws"] + b["lost"] == len(bu) and b["lost"] == 1 and b["main"]["lost"] == 1 and b["service"]["lost"] == 0
          and rows[1]["verdict"] == "ok" and rows[2]["verdict"] == "deviation" and rows[3]["verdict"] == "few" and rows[3]["stale"] == 1
          and rows[3]["outside"][0]["code"] == 7009 and b["main"]["stale"] == 1
          and b["main"]["no_row"][0]["code"] == 25003 and b["service"]["draws"] == 20 and not b["errors"], (b["errors"], {k: t["verdict"] for k, t in rows.items()}))
    check("шансы стенд: журналы Log_GachaItem и Log_CRTJIN (отказы после броска, ревизия 55 Н-4) читаются с бюджетом пользователя запроса (alice), "
          "logs=0 — не читаются",
          seen_user == ["alice", "alice"] and b["refused"] == {"13": 2} and O.boosters(dict(Q, logs="0"), "bob")["replay"] is None
          and seen_user == ["alice", "alice"])
    # ---- коробки
    pool0, pool1 = list(range(20)), list(range(20, 40))
    rnd = random.Random(99)
    days = {}
    for d in range(1, 11):
        lines = []
        for _ in range(150):
            i = rnd.choice(pool0)
            lines.append((9001, 100 + i, i))
        for _ in range(150):
            i = rnd.choice(pool1[:5] * 3 + pool1)
            lines.append((9002, 200 + i - 20, i))
        lines.append((9001, 999, 3))                     # не по текущей таблице (код другой)
        lines.append((3, 101, 1))                        # служебная
        days["202610%02d" % d] = ['2026-10-%02d 10:00:00.000 SEND 1.2.3.4:5 bytes=188 command=0x0051 account="x" source=sql status=1 order=7 subtype=2 '
                                   'userIndex=%d userNum=0 requestItemCode=2 itemCode=%d rewardIndex=%d rewardCount=1 requestedPrice=1 price=1 balance=1 '
                                   'present=0 hex=AA' % (d, u, c, i) for u, c, i in lines]
    calls = []
    O._listing = lambda key, proc, kind: ({"gp7-%s.log" % d: (len(v) * 100, 7) for d, v in days.items()}, False, None)
    O.CACHE_DIR = tmp

    def fake_scan(key, proc, name, kind, needles, user, closed, st):
        calls.append((name, user))
        if user == "limit" and len(calls) > 3:
            raise logs.Throttled("слишком много прочитано журналов за минуту — не больше 32 МБ на пользователя, подождите")
        return days[name[4:12]], False
    O._scan_cached = fake_scan
    x1 = O.boxes(dict(Q), "carol")
    bx = {t["box"]: t for t in x1["main"]["boxes"]}
    check("шансы стенд: коробки — автомат 0 (равномерно) согласуется, автомат 1 (первые 5 строк вчетверо чаще) — отклонение, строка с другим кодом — "
          "«не по текущей таблице» (10), служебная — отдельно, журнал читается с бюджетом пользователя carol",
          bx[0]["verdict"] == "ok" and bx[1]["verdict"] == "deviation" and x1["main"]["mismatch"] == 10 and x1["service"]["draws"] == 10
          and x1["main"]["draws"] == 3000 and {u for _n, u in calls} == {"carol"} and x1["days"]["read"] == 10, (bx[0]["p"], bx[1]["p"], x1["days"]))
    calls.clear()
    x2 = O.boxes(dict(Q), "dave")
    check("шансы стенд: повтор — закрытые сутки из кэша на диске (журнал не читается), итог тот же",
          not calls and x2["days"]["cached"] == 10 and x2["main"]["draws"] == 3000, (calls, x2["days"]))
    O.CACHE_DIR = os.path.join(tmp, "empty")
    calls.clear()
    x3 = O.boxes(dict(Q), "limit")
    check("шансы стенд: бюджет журналов исчерпан — прочитаны 3 суток, остальные «не прочитаны» с пометкой (без ошибки ответа)",
          x3["days"]["read"] == 3 and len(x3["days"]["unread"]) == 7 and x3["notes"] and not x3["errors"], x3["days"])
    # ---- нет таблицы журнала
    gc.execute("DROP TABLE dbo.UpperRefine")
    r2 = O.upgrade(dict(Q))
    check("шансы стенд: нет таблицы UpperRefine — строка ошибки «журнал шансов UpperRefine не прочитан», остальное считается",
          any(e.startswith("журнал шансов UpperRefine не прочитан") for e in r2["errors"]) and r2["main"]["attempts"] == s["attempts"], r2["errors"])


def live(check):
    """Живая dev (только чтение): счёт = COUNT(*), коробки за 4 дня = строкам журнала шлюза, служба на сервере, 401 без входа."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db
    from domains import odds as O
    import domains
    domains.load_all()
    if config.get().on_server:
        return check("живой самотест А6.5 — с ПК", True)
    u = O.upgrade({"svc": "in"})
    f, t = u["period"]["from"], u["period"]["to"]
    with db.GameReader("joylog1") as g:
        n_ud = int(g.one("SELECT COUNT(*) AS n FROM dbo.UpgradeData WHERE " + O.WINDOW, (f, t))["n"])
        n_bu = int(g.one("SELECT COUNT(*) AS n FROM dbo.BoosterUse WHERE " + O.WINDOW, (f, t))["n"])
        n_tu = int(g.one("SELECT COUNT(*) AS n FROM dbo.UpgradeTransplantUse WHERE " + O.WINDOW, (f, t))["n"])
        n_ur = int(g.one("SELECT COUNT(*) AS n FROM dbo.UpperRefine WHERE " + O.WINDOW, (f, t))["n"])
    m = u["main"]
    check("живое: попыток заточки = COUNT(*) UpgradeData за %s — %s (%d), таблицы сервера прочитаны, без ошибок" % (f, t, n_ud),
          m["attempts"] == n_ud and not u["errors"] and u["tables"]["item_upgrade"] and u["tables"]["over_upgrade"], (m["attempts"], u["errors"]))
    check("живое: перенос = COUNT(*) UpgradeTransplantUse (%d), высшая переработка = COUNT(*) UpperRefine (%d)" % (n_tu, n_ur),
          m["bless"]["n"] == n_tu and sum(x["n"] for x in m["refine"]) + m["refine_unmatched"] == n_ur)
    b = O.boosters({"svc": "in"}, "selftest-live")
    check("живое: призов бустеров + без приза = COUNT(*) BoosterUse (%d), журнал Log_GachaItem прочитан" % n_bu,
          b["main"]["draws"] + b["lost"] == n_bu and b["replay"] is not None and not b["errors"], (b["main"]["draws"], b["lost"], b["errors"]))
    fr, to = "20261018", "20261021"
    x = O.boxes({"from": fr, "to": to, "svc": "in"}, "selftest-live")
    ps = ("$n = 0; foreach ($d in 18..21) { $p = '@@ASTORY_SERVER_ROOT_ESC@@\\Working_ASDA\\v2\\gp7-server\\logs\\gp7-202610' + $d + '.log'; "
          "if (Test-Path $p) { $n += @(Select-String -Path $p -SimpleMatch 'command=0x0051' | Where-Object { $_.Line -match ' status=1 (order=\\d+ )?subtype=2 ' }).Count } }; "
          "'BOXN=' + $n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        import base64
        enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        rr = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                             "powershell -NoProfile -EncodedCommand " + enc], capture_output=True, timeout=300)
        out = (rr.stdout + rr.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"BOXN=(\d+)", out)
    got = x["main"]["draws"] + x["main"]["mismatch"] if x["main"] else None
    check("живое: коробки %s — %s — розыгрышей (вкл. «не по таблице») = строкам SEND subtype=2 status=1 журнала шлюза по SSH (%s), все сутки прочитаны"
          % (fr, to, mm.group(1) if mm else "?"), bool(mm) and got == int(mm.group(1)) and not x["days"]["unread"] and not x["errors"], (got, out[-300:], x["days"]))
    probe = ("import sys\nsys.path.insert(0, '.')\nfrom domains import odds as O\nr = O.upgrade({'from': %r, 'to': %r, 'svc': 'in'})\n"
             "print('ODPROBE n=%%d err=%%d iu=%%s' %% (r['main']['attempts'], len(r['errors']), r['tables']['item_upgrade']))\n" % (f, t))
    try:
        rr = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                             r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                             r'@@ASTORY_SERVER_PYTHON@@ -"'],
                            input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (rr.stdout + rr.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"ODPROBE n=(\d+) err=(\d+) iu=(\d+)", out)
    check("служба на сервере (SSH): таблицы сервера читаются локально, попыток столько же, сколько с ПК (%d), без ошибок" % m["attempts"],
          bool(mm) and int(mm.group(1)) == m["attempts"] and mm.group(2) == "0" and int(mm.group(3)) == u["tables"]["item_upgrade"], out[-500:])
    import ssl
    import urllib.error
    import urllib.request
    sc = ssl.create_default_context()
    sc.check_hostname, sc.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=sc)).open(
            "https://%s:17890/api/odds/upgrade" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/odds/upgrade без входа — 401", code == 401, code)
