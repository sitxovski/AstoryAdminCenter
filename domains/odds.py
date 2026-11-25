# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""odds.py — раздел «Шансы: выпало против заявленного» (шаг А6.5, 22.11.2026; разбор research_a6_economy_20261121.md §3 строка А6.5;
реверс и отчёт — Reports/admin_center/impl_a6_econ_20261121.md §А6.5). ТОЛЬКО ЧТЕНИЕ: игровые базы — логином asda_admin (SELECT),
таблицы сервера — те же файлы, что читает GameServer (srvtables: на сервере с диска, на ПК копия по scp), журналы стойки — белым списком
domains/logs.py (бюджет чтения — на пользователя запроса). Пишет только свой кэш разобранных журналов шлюза (data/odds_cache).

ЗАТОЧКА (реверс §А6.5 шаг 1 а). Joy1.UPItemUpgrade(@State, @Kind, @Destory, …) пишет UpgradeData (одна строка на попытку) и UpgradeScroll
  (строка на каждый потраченный свиток) с одним @DATE; Flag обеих = @State = УСПЕХ (GameServer CharShellItemUpgrade_0@0x4FEE50: v69, пакет
  2304 байт +7 → DBManager.exe.c:22397 первый параметр). Kind 1 — свиток Item_Table (ScrollType = t17 свитка), 2 — купон Function_Table
  (ScrollType = функция t5). Купон шанса — функция 98 (шанс + 1000 × t6), купон силы — функция 97 (Updamage + t6). Ev — ТЕКСТ, а не исход:
  «Upgrade» / «Limitless Upgrade» по Kind, но «Successful upgrades» при купоне шанса и «Additional upgrades» при купоне силы (при Flag 0 тоже).
  Шанс (GameServer.c:98933-98957): ItemUpgrade.txt[ScrollType − 70] токен 3 (+4) + 1000 × купон шанса; при Kind 2 или AcuUpcnt до попытки ≥ t44
  (SowelCombine t44, +146) — × OverUpgrade[Upcount − t44] / 100000 (усечение int); ScrollType 91 — 100000. Бросок sub_5329A0(0, 100000) =
  (rand() << 15 | rand()) % 100001; успех, если бросок < шанса. Неудача: Kind 1 вне зоны — только AcuUpcnt + 1; Kind 1 в зоне t44 — откат
  в 0 (Item_Table t24 = 3) или разрушение (иначе: строка «Destroyed-Limitless Upgrade» со значениями ДО, свитки в UpgradeScroll НЕ пишутся);
  Kind 2 — откат в 0. Откат: Flag 0, Upcnt = 0, AcuCnt = 0, MaxCnt = t44 (ступень до — по предыдущей строке того же серийника).
ПРОЧЕЕ. Высшая переработка (Recv_User_UpperRefine@0x4FC7E0): успех — бросок (0, 100000) < UpperRefineTable токен 15; при неудаче материал i
  теряется с шансом токена 8 / 11 / 14 (UpperRefine.Flag = успех, Amount_i = потрачено). Перенос (Recv_UserUpgradeBless@0x5358C0): бросок
  sub_5329A0(0, 100) ≤ 60 — порог ЗАШИТ в GameServer (таблицы нет), UpgradeTransplantUse.Flag = успех. Извлечение (Recv_UserUpgradeExtraction
  @0x534640): 4 исхода по ExtractionRateTable строка 0, Stat_UpgradeSeparation.State = исход + 1. Сброс ItemUpgrade и обмен GaChaTran* —
  без розыгрыша (только счёт). Опкод 5033 (CharShellItemUpgrade@0x4FB210) в базу не пишет (DBManager 0x808 — пустая функция).
БУСТЕР (Recv_GachaItemUse@0x4F48C0): строка GachaItemRateTable = t39 бустера (позиция t39 − 1), 35 пар «код, вес»; бросок (0, T), T — сумма
  весов пар с кодом > 0 и весом > 0; бросок = T — промах: отказ клиенту, бустер НЕ тратится, в базе ничего. Удача — UPBoosterItemSpend:
  BoosterUse (бустер) + одна строка BoosterGain / Functional / Gear / Sowel (приз) с тем же Edate. Поэтому заявленный шанс кода — доля его
  весов при условии «не промах» (shops.booster_odds, тот же генератор). Журнал Log_GachaItem (CachaItemLog_ГГГГММДД.txt): TotalRate, Rate =
  бросок, Code = приз, Gacha = бустер — розыгрыш воспроизводится по текущей строке таблицы. ★ ревизия 55 Н-4: после броска GameServer отказывает
  ещё по призу (нет ячейки, флаг +35, неизвестный код, перевес; GameServer.c:94376–94522) — бустер не тратится, в базе и Log_GachaItem ничего;
  выпавшее — распределение при условии «не промах и приз принят», отказы считаются по Log_CRTJIN (crtjin_refusals). Приз вне текущей строки —
  «не по текущей таблице» (вне критерия).
ПРЕМИУМ-КОРОБКА gp7 (шлюз AstoryServer/Patches/Gp7Gateway/server.js, selectLuckyBoxReward): crypto.randomInt по строкам PrimiumGaChaTable
  своего автомата (код > 0, кол-во > 0) — РАВНОМЕРНО по строкам; журнал шлюза gp7-ГГГГММДД.log, строка SEND … subtype=2 … rewardIndex =
  номер строки таблицы. Строка не совпала с текущей таблицей (код или кол-во) — розыгрыш шёл по другой таблице, в сравнение не входит.
КРИТЕРИЙ. Два исхода — точный биномиальный двусторонний (как binom.test: сумма вероятностей исходов не вероятнее наблюдённого); много —
  хи-квадрат согласия (категории с ожиданием < MIN_EXP сливаются); поправка на множественность — Холм по всем проверкам ответа (отдельно для
  игроков и служебных). «Мало данных» (без вывода): попыток < MIN_N или ожидание исхода < MIN_EXP. Шанс 0 или 1 — проверка без статистики
  (противоречит таблице, если хоть один исход против). SciPy не нужен (на службе его нет): формулы ниже, тест — на известных значениях.
СЛУЖЕБНЫЕ учётки ≤ 5000 — отдельным разделом (svc=sep), svc=in — в общем. Даты ГГГГММДД — параметрами, сутки — по часам SQL-сервера.
Сравнение — с ТЕКУЩИМИ таблицами сервера. Побочных эффектов при импорте нет.
"""
import datetime
import json
import math
import os
import re
import threading
import time

from core import config, db
from core.ops import OpRefused
from domains import acjournal, players, refdata, srvtables

SERVICE_MAX = players.OPERATOR_MAX_UID     # служебные учётки 1…5000
DAYS_DEFAULT = 90                    # период по умолчанию (суток)
DAYS_MAX = 366                       # предел периода
ALPHAS = ("0.05", "0.01", "0.001")   # уровни значимости на выбор
ALPHA_DEFAULT = "0.01"
MIN_N = 30                           # меньше попыток — «мало данных»
MIN_EXP = 5                          # хи-квадрат: ожидание категории меньше — слияние категорий / «мало данных»
NEAR = 1e-4                          # ★ ревизия 55 В-1: шанс ближе к 0 или 1 — «почти наверняка» (значимое расхождение = противоречит таблице)
ROWS_MAX = 200000                    # строк журнала за запрос (дальше — пометка «обрезано»)
TOP_CODES = 12                       # кодов в разбивке бустера
LOT_TOP = 12                         # строк в разбивке коробки
ROLL_TOP = 100000                    # sub_5329A0(0, 100000): заточка, высшая переработка, извлечение
BLESS_TOP, BLESS_MAX = 100, 60       # перенос: sub_5329A0(0, 100) ≤ 60 (GameServer.c:118189-118190)
GOLD = 20551                         # первый код Item_Table
FN_POWER, FN_RATE, ST_SURE = 97, 98, 91   # функция купона силы / купона шанса; ScrollType гарантированного свитка
DESTROYED = "Destroyed-Limitless Upgrade"
EV_KIND = {1: "Upgrade", 2: "Limitless Upgrade"}
EV_RATE, EV_POWER = "Successful upgrades", "Additional upgrades"
GAIN_TABLES = ("BoosterGain", "BoosterGainFunctional", "BoosterGainGear", "BoosterGainSowel")
TRAN_TABLES = ("GaChaTranFunctional", "GaChaTranGearitem", "GaChaTranNostack", "GaChaTranSowel")
OFF_RULE = ("t44_changed", "rule_bad", "half_observed")   # ★ ревизия 55: шанс известен, но попытка вне критерия (счёт у группы)
REASONS = ("destroy_noscroll", "stage_unknown", "scroll_unknown", "scroll_ambiguous", "ev_mismatch", "no_table_row", "stage_below",
           "over_no_row", "no_item", "t44_changed", "rule_bad", "half_observed")       # почему попытка не входит в критерий (подписи — web/odds.js TR_WHY)
WINDOW = "Edate >= CONVERT(datetime2, ?, 112) AND Edate < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))"
GP7_PROC, GP7_KEY = "gp7-server", "gp7"
GACHA_KIND = "Log_GachaItem"
SCAN_TTL_S = 120                     # сегодняшний (растущий) журнал не перечитывается чаще
CACHE_DIR = os.path.join(config.DATA_DIR, "odds_cache")   # разобранные закрытые сутки журнала шлюза (без логинов)
_RX_SEND = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d{3} SEND \S+ bytes=\d+ command=0x0051 .*? status=1 (?:order=\d+ )?subtype=2 "
                      r"userIndex=(\d+) .*? itemCode=(-?\d+) rewardIndex=(-?\d+) rewardCount=(-?\d+) ")
_RX_GACHA = re.compile(r"^\s*(\d{1,2}) Mon (\d{1,2}) Day (\d{1,2}) hou (\d{1,2}) min (\d{1,2}) sec : Recv_GachaItemUse\(\) UserIndex = (\d+), "
                       r"TotalRate=(-?\d+), Rate=(-?\d+), Code=(-?\d+), Gacha=(-?\d+)")
_mem = {}                            # (вид, файл) → {"st", "at", "data"} — разобранные журналы в памяти процесса
_mem_lock = threading.Lock()
_tok_cache = {}                      # имя таблицы → (время файла, токены)


# =====================================================================================================================
# СТАТИСТИКА (без SciPy)
# =====================================================================================================================
def roll_count(top, lo, hi):
    """(число исходов генератора, всего исходов): sub_5329A0(0, top) ∈ [lo, hi). rand() — 15 бит (top < 0x7FFF), иначе rand() << 15 | rand()
    — 30 бит; значение = r % (top + 1) (GameServer sub_5329A0)."""
    n = (1 << 15) if top < 0x7FFF else (1 << 30)
    m = top + 1
    lo = max(0, min(int(lo), m))
    hi = max(lo, min(int(hi), m))
    q, rem = divmod(n, m)
    return (hi - lo) * q + max(0, min(hi, rem) - lo), n


def roll_p(top, lo, hi):
    """Вероятность sub_5329A0(0, top) ∈ [lo, hi)."""
    c, n = roll_count(top, lo, hi)
    return c / float(n)


def binom_test(k, n, p):
    """Двусторонний точный биномиальный критерий (как R binom.test / scipy binomtest): сумма P(X = i) по i, у которых P(X = i) ≤ P(X = k)
    (относительный допуск 1e-7). p = 0 или 1 — 1.0, если исход возможен, иначе 0.0."""
    if n <= 0:
        return 1.0
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    lg, lp, lq = math.lgamma(n + 1), math.log(p), math.log1p(-p)

    def lpmf(i):
        return lg - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
    thr = lpmf(k) + math.log1p(1e-7)
    tot = 0.0
    for i in range(n + 1):
        v = lpmf(i)
        if v <= thr:
            tot += math.exp(v)
    return min(1.0, tot)


def _gammq(a, x):
    """Регуляризованная верхняя неполная гамма Q(a, x) (ряд при x < a + 1, иначе цепная дробь Лентца)."""
    if x <= 0.0:
        return 1.0
    lead = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1.0:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(100000):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-16:
                break
        return max(0.0, 1.0 - s * math.exp(lead))
    tiny = 1e-300
    b = x + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 100000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-16:
            break
    return min(1.0, max(0.0, math.exp(lead) * h))


def chi2_sf(x, df):
    """P(χ²(df) ≥ x)."""
    if df <= 0:
        return 1.0
    return _gammq(df / 2.0, x / 2.0)


def holm(tests):
    """Поправка Холма: у каждой проверки с «p» (не мало данных, не детерминированной) — «p_adj»."""
    idx = sorted([i for i, t in enumerate(tests) if t.get("p") is not None], key=lambda i: tests[i]["p"])
    m, run = len(idx), 0.0
    for r, i in enumerate(idx):
        run = max(run, min(1.0, (m - r) * tests[i]["p"]))
        tests[i]["p_adj"] = run
    for t in tests:
        t.setdefault("p_adj", None)
    return tests


def verdict(t, alpha):
    """Итог проверки: contradiction — исход против таблицы (шанс 0 / 1 без статистики или ★ ревизия 55 В-1: шанс почти 0 / 1 — «100 %» сервера
    = 1 − 1e-5 — и p с поправкой < α); few — мало данных; deviation — p_adj < α; ok."""
    if t.get("contradiction"):
        return "contradiction"
    if t.get("near") and t.get("p_adj") is not None and t["p_adj"] < alpha:
        return "contradiction"
    if t.get("few"):
        return "few"
    if t.get("p_adj") is not None and t["p_adj"] < alpha:
        return "deviation"
    return "ok"


def binom_case(k, n, p):
    """Проверка «двух исходов»: успехов k из n при заявленном prob → {n, prob, expected, p, few, contradiction, det} (успехи — у вызывающего)."""
    out = {"n": n, "prob": p, "expected": n * p, "p": None, "few": False, "contradiction": False, "det": False, "near": False}
    if p <= 0.0 or p >= 1.0:
        out["det"] = True
        out["contradiction"] = binom_test(k, n, p) == 0.0
        return out
    # ★ ревизия 55 В-1: точному критерию правило «ожидание ≥ 5» не нужно — «мало данных» только n < MIN_N. Шанс почти 0 или 1 (min(p, 1 − p)
    #   < NEAR, например «100 %» заточки = 1 − 1e-5) — near: p считается при любом n, значимое расхождение — «противоречит таблице».
    out["near"] = min(p, 1.0 - p) < NEAR
    out["few"] = n < MIN_N
    if out["few"] and not out["near"]:
        return out
    out["p"] = binom_test(k, n, p)
    return out


def gof_case(obs, probs, stale=False):
    """Хи-квадрат согласия: obs {категория: выпало}, probs {категория: заявленная вероятность}. Категории с ожиданием < MIN_EXP сливаются в
    одну («прочие»), она — с наименьшей оставшейся, пока у всех ожидание ≥ MIN_EXP. Выпавшее вне probs — противоречие таблице
    (stale=True — ★ ревизия 55 Н-5: «не по текущей таблице», вне критерия).
    → {n, chi2, df, p, bins, few, contradiction, outside}."""
    outside = {c: v for c, v in obs.items() if v and probs.get(c, 0.0) <= 0.0}
    if stale:                     # ★ ревизия 55 Н-5: выпавшее вне ТЕКУЩЕЙ строки — розыгрыш по другой версии таблицы, в критерий не входит
        obs = {c: v for c, v in obs.items() if c not in outside}
    n = sum(obs.values())
    out = {"n": n, "chi2": None, "df": None, "p": None, "bins": 0, "few": False, "contradiction": bool(outside) and not stale,
           "outside": sorted(outside.items(), key=lambda kv: -kv[1]), "stale": sum(outside.values()) if stale else 0}
    cells = sorted(((n * p, obs.get(c, 0)) for c, p in probs.items() if p > 0.0), key=lambda x: -x[0])
    big = [list(x) for x in cells if x[0] >= MIN_EXP]
    rest = [sum(x[0] for x in cells if x[0] < MIN_EXP), sum(x[1] for x in cells if x[0] < MIN_EXP)]
    if rest[0] > 0:
        if rest[0] >= MIN_EXP or not big:
            big.append(rest)
        else:
            big[-1][0] += rest[0]
            big[-1][1] += rest[1]
    while len(big) > 1 and big[-1][0] < MIN_EXP:
        e, o = big.pop()
        big[-1][0] += e
        big[-1][1] += o
    out["bins"] = len(big)
    if n < MIN_N or len(big) < 2 or any(e < MIN_EXP for e, _ in big):
        out["few"] = True
        return out
    x = sum((o - e) ** 2 / e for e, o in big)
    out["chi2"], out["df"] = x, len(big) - 1
    out["p"] = chi2_sf(x, len(big) - 1)
    return out


# =====================================================================================================================
# ВВОД
# =====================================================================================================================
def _svc(q):
    v = (q.get("svc") or "").strip()
    if v and v not in ("sep", "in"):
        raise OpRefused("служебные в шансах — sep (отдельно) или in (в общем итоге)")
    return v or "sep"


def _alpha(q):
    v = (q.get("alpha") or "").strip()
    if v and v not in ALPHAS:
        raise OpRefused("уровень значимости шансов — 0.05, 0.01 или 0.001")
    return float(v or ALPHA_DEFAULT)


def _logs_flag(q):
    v = (q.get("logs") or "").strip()
    if v and v not in ("0", "1"):
        raise OpRefused("журнал Log_GachaItem в шансах — 0 или 1")
    return v != "0"


def _dates(q):
    f, t = acjournal.parse_day(q.get("from"), "from"), acjournal.parse_day(q.get("to"), "to")
    if f and t and f > t:
        raise OpRefused("дата «с» позже даты «по»")
    return f, t


def _period(q, today):
    """(с, по) ГГГГММДД; по умолчанию — DAYS_DEFAULT суток до «сегодня» сервера; не длиннее DAYS_MAX."""
    f, t = _dates(q)
    t = t or today
    if not f:
        f = (datetime.datetime.strptime(t, "%Y%m%d") - datetime.timedelta(days=DAYS_DEFAULT - 1)).strftime("%Y%m%d")
    if f > t:
        raise OpRefused("дата «с» позже даты «по»")
    if (datetime.datetime.strptime(t, "%Y%m%d") - datetime.datetime.strptime(f, "%Y%m%d")).days + 1 > DAYS_MAX:
        raise OpRefused("период шансов — не больше %d суток" % DAYS_MAX)
    return f, t


def check_input(q, what):
    """Проверка ввода ДО базы (те же отказы, что у функций): самотест и консоль."""
    _svc(q)
    _alpha(q)
    f, t = _dates(q)
    if f and t:
        _period(q, t)
    if what == "boosters":
        _logs_flag(q)


def cat_of(uid):
    return "service" if int(uid) <= SERVICE_MAX else "player"


def _today(g):
    return g.one("SELECT CONVERT(char(8), GETDATE(), 112) AS d")["d"]


def _split(rows, svc, uid=lambda r: r["Userindex"]):
    """{категория раздела: строки}: svc=sep — игроки и служебные отдельно, in — всё в «player»."""
    out = {"player": [], "service": []}
    for r in rows:
        out["player" if svc == "in" else cat_of(uid(r))].append(r)
    return out


def _name(code):
    try:
        return refdata.item(int(code))["name"]
    except Exception:           # справочника нет / код вне справочника — имя пустое (число показывается всегда)
        return ""


# =====================================================================================================================
# ТАБЛИЦЫ СЕРВЕРА (точные копии загрузчиков GameServer)
# =====================================================================================================================
def _file_tokens(name):
    """Токены файла ItemTable_Info (fscanf "%s" — пробельные символы), кэш по времени файла."""
    with srvtables._lock:
        path = srvtables._local_copy(name)
        mt = os.path.getmtime(path)
        hit = _tok_cache.get(name)
        if hit and hit[0] == mt:
            return hit[1]
        toks = open(path, "rb").read().decode("cp1251", "replace").split()
        _tok_cache[name] = (mt, toks)
        return toks


def _file_lines(name):
    """Строки файла ItemTable_Info (как читает шлюз gp7: построчно)."""
    with srvtables._lock:
        path = srvtables._local_copy(name)
        return open(path, "rb").read().decode("utf-8", "replace").lstrip("\ufeff").splitlines()


read_tokens = _file_tokens           # подмена в самотесте (стенд): имя → токены
read_lines = _file_lines             # подмена в самотесте: имя → строки


def item_tok(code, k):
    """Токен k Item_Table (srvtables.table) или None — кода нет."""
    f = srvtables.table("Item_Table.txt").get(int(code))
    return srvtables._i(f, k) if f is not None else None


def func_tok(code, k):
    """Токен k Function_Table или None — кода нет."""
    f = srvtables.table("Function_Table.txt").get(int(code))
    return srvtables._i(f, k) if f is not None else None


def sowel_t44(code):
    """MaxupCnt предмета (SowelCombine t44, +146)."""
    return srvtables.sowel_maxup(int(code))


def item_upgrade():
    """ItemUpgrade.txt (GameServer.c:70989): N, затем N записей по 7 токенов: тип(+0) мин(+2) макс(+3) шанс(+4) шаг(+8) вид(+10) уровень(+11).
    → [запись или None по позициям]; позиция = ScrollType − 70."""
    t = read_tokens("ItemUpgrade.txt")
    n = srvtables._atol(t[0]) if t else 0
    out = []
    for i in range(n):
        r = t[1 + 7 * i: 8 + 7 * i]
        if len(r) < 7:
            break
        out.append({"type": srvtables._atol(r[0]), "chance": srvtables._atol(r[3]), "step": srvtables._atol(r[4]), "kind": srvtables._atol(r[5]),
                    "level": srvtables._atol(r[6])})
    return out


def over_upgrade():
    """OverUpgrade.txt (GameServer.c:72421): N, записи (индекс, шанс); предел индекса = N − 1."""
    t = read_tokens("OverUpgrade.txt")
    n = srvtables._atol(t[0]) if t else 0
    return [(srvtables._atol(t[1 + 2 * i]), srvtables._atol(t[2 + 2 * i])) for i in range(n) if 2 + 2 * i < len(t)]


def upper_refine():
    """UpperRefineTable.txt (GameServer.c:71410): N, записи по 17 токенов — индекс, уровень, ?, слот, грейд, ?, (материал, кол-во, шанс потери)
    × 3, шанс успеха (+60), золото (+64)."""
    t = read_tokens("UpperRefineTable.txt")
    n = srvtables._atol(t[0]) if t else 0
    out = []
    for i in range(n):
        r = [srvtables._atol(x) for x in t[1 + 17 * i: 18 + 17 * i]]
        if len(r) < 17:
            break
        out.append({"idx": r[0], "mats": [(r[6], r[7], r[8]), (r[9], r[10], r[11]), (r[12], r[13], r[14])], "chance": r[15], "gold": r[16]})
    return out


def extraction_rates():
    """ExtractionRateTable.txt (GameServer.c:75150, указатель this+1922644 = gap_1D6028[38568]): N, по 4 шанса; GameServer берёт строку 0."""
    t = read_tokens("ExtractionRateTable.txt")
    return [srvtables._atol(x) for x in t[1:5]] if len(t) >= 5 else None


def gacha_rows():
    """GachaItemRateTable.txt (GameServer.c:72189): N, записи: id (не читается GS по смыслу) + 35 пар «код, вес» потоком токенов."""
    t = read_tokens("GachaItemRateTable.txt")
    n = srvtables._atol(t[0]) if t else 0
    out = []
    for i in range(n):
        r = t[1 + 71 * i: 72 + 71 * i]
        if len(r) < 71:
            break
        out.append([(srvtables._atol(r[1 + 2 * j]), srvtables._atol(r[2 + 2 * j])) for j in range(35)])
    return out


def lucky_pool():
    """PrimiumGaChaTable.txt ровно как шлюз gp7 (server.js loadLuckyBoxPools, ★ ревизия 55): строки без пробелов по краям, пустые выброшены;
    первая — объявленное число; у каждой следующей ≥ 4 поля и ВСЕ поля — целые, иначе ошибка (шлюз падает при старте); строки с кодом ≤ 0 или
    кол-вом ≤ 0 в пул не входят; число строк пула ≠ объявленному — ошибка. → ({индекс: (автомат, код, кол-во)}, {автомат: [индексы]})."""
    lines = [x.strip() for x in read_lines("PrimiumGaChaTable.txt")]
    lines = [x for x in lines if x]
    if not lines:
        raise ValueError("LuckyBox table is empty")
    head = lines.pop(0)
    declared = int(head) if re.match(r"^-?\d+$", head) else None
    rows, pools = {}, {}
    for ln in lines:
        f = ln.split()
        if len(f) < 4 or not all(re.match(r"^-?\d+$", x) for x in f):
            raise ValueError("Invalid LuckyBox table row: %s" % json.dumps(ln[:80]))
        i, box, code, cnt = (int(x) for x in f[:4])
        if code <= 0 or cnt <= 0:
            continue
        rows[i] = (box, code, cnt)
        pools.setdefault(box, []).append(i)
    parsed = sum(len(v) for v in pools.values())
    if declared is None or parsed != declared:
        raise ValueError("LuckyBox row count mismatch: declared=%s parsed=%d" % (head[:20], parsed))
    return rows, pools


def _booster_odds(pairs):
    from domains.cs_kinds import shops
    return shops.booster_odds(pairs)


# =====================================================================================================================
# ЗАТОЧКА: попытка → (свиток, ступень до, шанс)
# =====================================================================================================================
def classify(codes):
    """Свитки одной попытки → {kind, main, st, rate, power, why}. Свиток Item_Table — основной (Kind 1, ScrollType = t17); купоны функции 97
    (сила) и 98 (шанс); без свитка Item_Table — Kind 2, основной — купон с функцией не 97/98 (или единственный купон)."""
    out = {"kind": None, "main": None, "st": None, "rate": 0, "power": 0, "has_rate": False, "has_power": False, "why": None}
    items = [c for c in codes if c >= GOLD]
    fns = [(c, func_tok(c, 5)) for c in codes if c < GOLD]
    if len(items) > 1 or any(t is None for _c, t in fns):
        out["why"] = "scroll_unknown"
        return out
    if items:
        out["kind"], out["main"] = 1, items[0]
        st = item_tok(items[0], 17)
        if st is None:
            out["why"] = "scroll_unknown"
            return out
        out["st"] = st
        extra = fns
    else:
        mains = [(c, t) for c, t in fns if t not in (FN_POWER, FN_RATE)]
        if len(mains) == 1:
            m = mains[0]
        elif not mains and len(fns) == 1:
            m = fns[0]
        else:
            out["why"] = "scroll_ambiguous" if fns else "scroll_unknown"
            return out
        out["kind"], out["main"], out["st"] = 2, m[0], m[1]
        extra = [x for x in fns if x is not m]
    for c, t in extra:
        if t == FN_RATE and not out["has_rate"]:
            out["has_rate"], out["rate"] = True, func_tok(c, 6) or 0
        elif t == FN_POWER and not out["has_power"]:
            out["has_power"], out["power"] = True, func_tok(c, 6) or 0
        else:
            out["why"] = "scroll_ambiguous"
    return out


def chance(st, rate, kind, acu_b, up_b, t44, iu, ov):
    """Заявленный шанс (из 100000) и зона: (шанс | None, зона, k, why). Повтор GameServer.c:98933-98957."""
    i = st - 70
    if i < 0 or i >= len(iu) or iu[i]["type"] != st:
        return None, None, None, "no_table_row"
    c = iu[i]["chance"] + 1000 * rate
    over = kind == 2 or (acu_b is not None and acu_b >= t44)
    k = None
    if over:
        k = up_b - t44
        if k < 0:
            return None, "over", k, "stage_below"
        if k > len(ov) - 1 or ov[k][0] != k:
            return None, "over", k, "over_no_row"
        c = int(c * (ov[k][1] / 100000.0))
    if st == ST_SURE and kind == 1:          # ★ ревизия 55: v13 ставится только для свитка Item_Table (GameServer.c:98832–98836)
        c = 100000
    return c, ("over" if over else "normal"), k, None


def attempts(rows, scrolls, iu, ov):
    """Строки UpgradeData (с предыдущей строкой серийника) + свитки по ключу (Edate, Userindex, Charidx, Scode) → попытки:
    {uid, code, outcome (success / fail / reset / destroy), up_b, kind, main, st, rate, zone, k, c, prob, why, rule}."""
    out = []
    for r in rows:
        destroyed = (r["Ev"] or "") == DESTROYED
        flag, up, acu = int(r["flag"] or 0), int(r["up"] or 0), int(r["acu"] or 0)
        reset = not destroyed and flag == 0 and up == 0 and acu == 0
        a = {"uid": int(r["Userindex"]), "code": int(r["Code"]), "t": r["Edate"], "outcome": "success" if flag == 1 else
             ("destroy" if destroyed else ("reset" if reset else "fail")), "up_b": None, "kind": None, "main": None, "st": None, "rate": 0,
             "zone": None, "k": None, "c": None, "prob": None, "why": None, "rule": None}
        if destroyed:
            a["up_b"], acu_b, a["kind"] = up, acu, 1
        elif flag == 1:
            a["up_b"], acu_b = up - 1, acu - 1
        elif reset:
            a["up_b"], acu_b = r.get("pup"), r.get("pacu")
        else:
            a["up_b"], acu_b = up, acu - 1
        t44 = sowel_t44(a["code"])
        if destroyed:
            a["zone"] = "over"
            a["why"] = "destroy_noscroll"
            out.append(a)
            continue
        cl = classify(scrolls.get((r["Edate"], int(r["Userindex"]), int(r["Charidx"]), int(r["Code"])), []))
        a.update(kind=cl["kind"], main=cl["main"], st=cl["st"], rate=cl["rate"])
        if cl["why"]:
            a["why"] = cl["why"]
            out.append(a)
            continue
        ev = EV_RATE if cl["has_rate"] else (EV_POWER if cl["has_power"] else EV_KIND[cl["kind"]])
        if (r["Ev"] or "") != ev:
            a["why"] = "ev_mismatch"
            out.append(a)
            continue
        if a["up_b"] is None or acu_b is None:
            a["why"] = "stage_unknown"
            out.append(a)
            continue
        c, zone, k, why = chance(cl["st"], cl["rate"], cl["kind"], acu_b, a["up_b"], t44, iu, ov)
        a.update(zone=zone, k=k, c=c, why=why)
        if zone is not None and not why:
            # ★ ревизия 55 Н-2: зона — по ЗАПИСАННОМУ MaxCnt (тогдашний t44), а не только по текущему SowelCombine: откат ставит MaxUpcnt = t44
            #   (GameServer.c:98963 / 98974), успех в зоне — MaxUpcnt + 1 (:98994–98997), вне зоны MaxUpcnt не меняется.
            mx, pmx = r.get("mx"), r.get("pmx")
            if reset and mx is not None and int(mx) != t44:
                a["why"] = "t44_changed"
            elif a["outcome"] == "success" and cl["kind"] == 1 and mx is not None and pmx is not None and int(mx) - int(pmx) in (0, 1) \
                    and (int(mx) == int(pmx) + 1) != (zone == "over"):
                a["why"] = "t44_changed"
        if a["outcome"] != "success" and zone is not None and not a["why"]:     # неудача по правилу GameServer: вне зоны — без отката
            want = "fail" if zone == "normal" else ("reset" if cl["kind"] == 2 or item_tok(a["code"], 24) == 3 else "destroy")
            a["rule"] = want == a["outcome"]
            if not a["rule"]:
                a["why"] = "rule_bad"                  # ★ ревизия 55 Н-2: попытка против правила сервера — вне критерия, отдельным счётом
        if not a["why"] and zone == "over" and cl["kind"] == 1 and item_tok(a["code"], 24) != 3:
            a["why"] = "half_observed"                 # ★ ревизия 55 Н-3: неудача = разрушение без свитка — исход виден наполовину
        if c is not None and not a["why"]:
            a["prob"] = roll_p(ROLL_TOP, 0, c)
        out.append(a)
    return out


def _stage_rows(att):
    """Разбивка по ступени до попытки (все свитки): попыток, исходов, ожидалось успехов (Σ шансов попыток с известным шансом)."""
    st = {}
    for a in att:
        s = st.setdefault(a["up_b"], {"stage": a["up_b"], "n": 0, "success": 0, "fail": 0, "reset": 0, "destroy": 0, "known": 0, "expected": 0.0,
                                      "known_success": 0})
        s["n"] += 1
        s[a["outcome"]] += 1
        if a["prob"] is not None:
            s["known"] += 1
            s["expected"] += a["prob"]
            s["known_success"] += a["outcome"] == "success"
    return sorted(st.values(), key=lambda s: (s["stage"] is None, s["stage"] if s["stage"] is not None else 0))


def _scroll_groups(att):
    """Проверки по свитку: ключ (свиток, купон шанса, зона, k) — у группы один заявленный шанс."""
    g = {}
    for a in att:
        if a["c"] is None or a["why"] not in (None,) + OFF_RULE:
            continue
        key = (a["main"], a["rate"], a["zone"], a["k"])
        x = g.setdefault(key, {"scroll": a["main"], "st": a["st"], "kind": a["kind"], "rate": a["rate"], "zone": a["zone"], "k": a["k"],
                               "c": a["c"], "prob": roll_p(ROLL_TOP, 0, a["c"]), "n": 0, "success": 0, "fail": 0, "reset": 0, "destroy": 0,
                               "stage_min": a["up_b"], "stage_max": a["up_b"], "rule_bad": 0, "off": {}})
        if a["why"]:                     # ★ ревизия 55 Н-2/Н-3: вне критерия, но видно у своей группы (столбец «не по правилу»)
            x["off"][a["why"]] = x["off"].get(a["why"], 0) + 1
            x["rule_bad"] += 1
            continue
        x["n"] += 1
        x[a["outcome"]] += 1
        x["stage_min"], x["stage_max"] = min(x["stage_min"], a["up_b"]), max(x["stage_max"], a["up_b"])
    out = []
    for x in sorted(g.values(), key=lambda x: (-x["n"], x["scroll"])):
        x.update(binom_case(x["success"], x["n"], x["prob"]))
        x["name"] = _name(x["scroll"])
        x["what"] = "scroll"
        out.append(x)
    return out


# =====================================================================================================================
# ЧТЕНИЕ
# =====================================================================================================================
def _rows(g, sql, params, what, errors, cap=None):
    """Строки запроса или None с ошибкой «журнал шансов … не прочитан». cap — список, куда кладётся what, если строк больше ROWS_MAX."""
    try:
        rs = g.rows(sql, params)
    except db.DbError as ex:
        errors.append("журнал шансов %s не прочитан: %s" % (what, ex))
        return None
    if cap is not None and len(rs) > ROWS_MAX:
        cap.append(what)
        rs = rs[:ROWS_MAX]
    return rs


def _tables(errors, names):
    """Таблицы сервера по именам (функции разбора) → {имя: данные | None}; ошибка — строка «таблица сервера … не прочитана»."""
    fn = {"ItemUpgrade.txt": item_upgrade, "OverUpgrade.txt": over_upgrade, "UpperRefineTable.txt": upper_refine,
          "ExtractionRateTable.txt": extraction_rates, "GachaItemRateTable.txt": gacha_rows, "PrimiumGaChaTable.txt": lucky_pool}
    out = {}
    for n in names:
        try:
            out[n] = fn[n]()
        except Exception as ex:           # нет файла / SSH / разбор — раздел считается без этой таблицы, причина — в errors
            errors.append("таблица сервера %s не прочитана: %s" % (n, str(ex)[:200]))
            out[n] = None
    return out


SQL_UPG = ("SELECT TOP (" + str(ROWS_MAX + 1) + ") x.Edate, x.Userindex, x.Charidx, x.Code, x.up, x.acu, x.mx, x.flag, x.Ev, x.pup, x.pacu, x.pmx FROM ("
           "SELECT Edate, Userindex, Charidx, Code, CAST(Upcnt AS INT) AS up, CAST(AcuCnt AS INT) AS acu, CAST(MaxCnt AS INT) AS mx, CAST(Flag AS INT) AS flag, Ev, "
           "LAG(CAST(Upcnt AS INT)) OVER (PARTITION BY Serial ORDER BY Edate) AS pup, "
           "LAG(CAST(AcuCnt AS INT)) OVER (PARTITION BY Serial ORDER BY Edate) AS pacu, "
           "LAG(CAST(MaxCnt AS INT)) OVER (PARTITION BY Serial ORDER BY Edate) AS pmx "
           "FROM dbo.UpgradeData WHERE Edate < DATEADD(DAY, 1, CONVERT(datetime2, ?, 112)) AND Serial IN "
           "(SELECT Serial FROM dbo.UpgradeData WHERE " + WINDOW + ")) x WHERE x.Edate >= CONVERT(datetime2, ?, 112) ORDER BY x.Edate")
SQL_SCROLL = "SELECT TOP (%d) Edate, Userindex, Charidx, Scode, Code FROM dbo.UpgradeScroll WHERE %s" % (ROWS_MAX + 1, WINDOW)
SQL_REFINE = ("SELECT TOP (%d) Edate, Userindex, Code1, Amount1, Code2, Amount2, Code3, Amount3, Gm, CAST(Flag AS INT) AS flag "
              "FROM dbo.UpperRefine WHERE %s" % (ROWS_MAX + 1, WINDOW))
SQL_BLESS = "SELECT Userindex, CAST(Flag AS INT) AS flag, COUNT(*) AS n FROM dbo.UpgradeTransplantUse WHERE %s GROUP BY Userindex, Flag" % WINDOW
SQL_EXTRACT = "SELECT Userindex, CAST(State AS INT) AS st, COUNT(*) AS n FROM dbo.Stat_UpgradeSeparation WHERE %s GROUP BY Userindex, State" % WINDOW
SQL_RESET = "SELECT Userindex, State, COUNT(*) AS n FROM dbo.ItemUpgrade WHERE %s GROUP BY Userindex, State" % WINDOW
SQL_TRAN = "SELECT Userindex, COUNT(*) AS n FROM dbo.%s WHERE %s GROUP BY Userindex"
SQL_BUSE = "SELECT TOP (%d) Edate, Userindex, Charidx, Code FROM dbo.BoosterUse WHERE %s" % (ROWS_MAX + 1, WINDOW)
SQL_BGAIN = "SELECT TOP (%d) Edate, Userindex, Charidx, Code FROM dbo.%%s WHERE %s" % (ROWS_MAX + 1, WINDOW)


def _counts(rows, svc, key):
    """[{Userindex, key, n}] → {категория: {значение key: n}}."""
    out = {"player": {}, "service": {}}
    for r in rows or []:
        c = "player" if svc == "in" else cat_of(r["Userindex"])
        out[c][r[key]] = out[c].get(r[key], 0) + int(r["n"])
    return out


def _refine_tests(rows, recipes):
    """Высшая переработка: успех по шансу рецепта и потеря материалов при неудаче. Рецепт — по (материалы, золото); у разных рецептов с
    одним ключом и разным шансом — «рецепт не определён»."""
    by = {}
    for rc in recipes or []:
        key = (tuple(max(0, m[0]) for m in rc["mats"]), rc["gold"])
        by.setdefault(key, []).append(rc)
    grp, loss, unmatched = {}, {}, 0
    for r in rows:
        mats = (max(0, int(r["Code1"] or 0)), max(0, int(r["Code2"] or 0)), max(0, int(r["Code3"] or 0)))
        cand = by.get((mats, int(r["Gm"] or 0)), [])
        if not cand or len({(c["chance"], tuple(m[2] for m in c["mats"])) for c in cand}) != 1:
            unmatched += 1
            continue
        rc = cand[0]
        x = grp.setdefault(rc["chance"], {"what": "refine", "c": rc["chance"], "prob": roll_p(ROLL_TOP, 0, rc["chance"]), "n": 0, "success": 0,
                                          "recipes": set()})
        x["n"] += 1
        x["success"] += int(r["flag"]) == 1
        x["recipes"].add(rc["idx"])
        if int(r["flag"]) != 1:
            for i, (code, need, lr) in enumerate(rc["mats"]):
                if code <= 0 or need <= 0:
                    continue
                y = loss.setdefault(lr, {"what": "refine_loss", "c": lr, "prob": roll_p(ROLL_TOP, 0, lr), "n": 0, "success": 0, "slots": set()})
                y["n"] += 1
                y["success"] += int(r["Amount%d" % (i + 1)] or 0) > 0
                y["slots"].add(i + 1)
    out = []
    for x in sorted(grp.values(), key=lambda x: -x["n"]):
        x.update(binom_case(x["success"], x["n"], x["prob"]))
        x["recipes"] = sorted(x["recipes"])[:20]
        out.append(x)
    lo = []
    for y in sorted(loss.values(), key=lambda y: -y["n"]):
        y.update(binom_case(y["success"], y["n"], y["prob"]))
        y["slots"] = sorted(y["slots"])
        lo.append(y)
    return out, lo, unmatched


def _extract_test(counts, rates):
    """Извлечение: 4 исхода (State − 1) против ExtractionRateTable строки 0; бросок ≥ суммы — исход 0 (resultGrade = 0 до цикла)."""
    if not rates:
        return None
    cum, probs = 0, {}
    for i, r in enumerate(rates):
        probs[i] = roll_p(ROLL_TOP, cum, cum + max(0, r))
        cum += max(0, r)
    probs[0] += roll_p(ROLL_TOP, cum, ROLL_TOP + 1)
    obs = {}
    for st, n in counts.items():
        obs[int(st) - 1] = obs.get(int(st) - 1, 0) + n
    t = gof_case(obs, probs)
    t.update(what="extract", obs={str(k): v for k, v in sorted(obs.items())}, probs={str(k): v for k, v in probs.items()}, rates=rates)
    return t


def _section_upgrade(att, refine_rows, recipes, bless, extract, rates, reset, tran, alpha):
    """Раздел «заточка и прочее» одной категории учёток → dict; поправка Холма — по всем проверкам раздела."""
    groups = _scroll_groups(att)
    ref, loss, unmatched = _refine_tests(refine_rows, recipes) if recipes is not None else ([], [], len(refine_rows))
    nb = sum(bless.values())
    bt = binom_case(bless.get(1, 0), nb, roll_p(BLESS_TOP, 0, BLESS_MAX + 1))
    bt.update(what="bless", success=bless.get(1, 0), c=BLESS_MAX)
    et = _extract_test(extract, rates)
    tests = groups + ref + loss + [bt] + ([et] if et else [])
    holm(tests)
    for t in tests:
        t["verdict"] = verdict(t, alpha)
    excl = {}
    for a in att:
        if a["prob"] is None:
            excl[a["why"] or "no_item"] = excl.get(a["why"] or "no_item", 0) + 1
    return {"attempts": len(att), "outcomes": {o: sum(1 for a in att if a["outcome"] == o) for o in ("success", "fail", "reset", "destroy")},
            "stages": _stage_rows(att), "groups": groups, "excluded": excl, "rule_bad": sum(1 for a in att if a["rule"] is False),
            "refine": ref, "refine_loss": loss, "refine_unmatched": unmatched, "bless": bt, "extract": et,
            "reset": [{"state": k, "n": v} for k, v in sorted(reset.items())], "tran": tran,
            "verdicts": {v: sum(1 for t in tests if t["verdict"] == v) for v in ("ok", "deviation", "few", "contradiction")}}


def upgrade(q):
    """Заточка (UpgradeData + UpgradeScroll) против ItemUpgrade / OverUpgrade, высшая переработка против UpperRefineTable, перенос против
    порога 60, извлечение против ExtractionRateTable; сброс ItemUpgrade и обмен GaChaTran* — счёт без розыгрыша. → dict."""
    check_input(q, "upgrade")
    svc, alpha = _svc(q), _alpha(q)
    out = {"svc": svc, "alpha": alpha, "period": None, "errors": [], "capped": [], "main": None, "service": None, "tables": {}}
    tb = _tables(out["errors"], ("ItemUpgrade.txt", "OverUpgrade.txt", "UpperRefineTable.txt", "ExtractionRateTable.txt"))
    iu, ov = tb["ItemUpgrade.txt"], tb["OverUpgrade.txt"]
    out["tables"] = {"item_upgrade": len(iu) if iu is not None else None, "over_upgrade": len(ov) if ov is not None else None,
                     "upper_refine": len(tb["UpperRefineTable.txt"]) if tb["UpperRefineTable.txt"] is not None else None,
                     "extraction": tb["ExtractionRateTable.txt"], "bless_max": BLESS_MAX}
    try:
        with db.GameReader("joylog1") as g:
            f, t = _period(q, _today(g))
            out["period"] = {"from": f, "to": t}
            up = _rows(g, SQL_UPG, (t, f, t, f), "UpgradeData", out["errors"], out["capped"]) or []
            sc = _rows(g, SQL_SCROLL, (f, t), "UpgradeScroll", out["errors"], out["capped"]) or []
            rf = _rows(g, SQL_REFINE, (f, t), "UpperRefine", out["errors"], out["capped"]) or []
            bl = _rows(g, SQL_BLESS, (f, t), "UpgradeTransplantUse", out["errors"])
            ex = _rows(g, SQL_EXTRACT, (f, t), "Stat_UpgradeSeparation", out["errors"])
            rs = _rows(g, SQL_RESET, (f, t), "ItemUpgrade", out["errors"])
            tr = {"player": 0, "service": 0}
            for tab in TRAN_TABLES:
                for r in _rows(g, SQL_TRAN % (tab, WINDOW), (f, t), tab, out["errors"]) or []:
                    tr["player" if svc == "in" else cat_of(r["Userindex"])] += int(r["n"])
    except db.DbError as ex2:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex2)
        return out
    scrolls = {}
    for s in sc:
        scrolls.setdefault((s["Edate"], int(s["Userindex"]), int(s["Charidx"]), int(s["Scode"])), []).append(int(s["Code"]))
    att = attempts(up, scrolls, iu, ov) if iu is not None and ov is not None else []
    if iu is None or ov is None:
        out["errors"].append("заточка без таблиц сервера ItemUpgrade / OverUpgrade не сравнивается")
    cats = ("player",) if svc == "in" else ("player", "service")
    sa = _split(att, svc, uid=lambda a: a["uid"])
    sr = _split(rf, svc)
    bc, ec, rc = _counts(bl, svc, "flag"), _counts(ex, svc, "st"), _counts(rs, svc, "State")
    for c in cats:
        sec = _section_upgrade(sa[c], sr[c], tb["UpperRefineTable.txt"], bc[c], ec[c], tb["ExtractionRateTable.txt"], rc[c], tr[c], alpha)
        out["main" if c == "player" else "service"] = sec
    return out


# =====================================================================================================================
# БУСТЕРЫ
# =====================================================================================================================
def _booster_probs(pairs):
    """Заявленный шанс кода при условии «не промах» (промах — бустер не тратится, в базе нет) → ({код: p}, сумма весов, шанс промаха)."""
    o = _booster_odds(pairs)
    miss = o["miss"]
    probs = {}
    for _j, code, _w, p in o["rows"]:
        probs[code] = probs.get(code, 0.0) + p / (1.0 - miss)
    return probs, o["total"], miss


def booster_draws(uses, gains):
    """BoosterUse + BoosterGain* (тот же Edate, учётка, персонаж) → ([{uid, booster, prize}], [учётки вскрытий без приза])."""
    gk, lost = {}, []
    for r in gains:
        gk.setdefault((r["Edate"], int(r["Userindex"]), int(r["Charidx"])), []).append(int(r["Code"]))
    out = []
    for u in uses:
        key = (u["Edate"], int(u["Userindex"]), int(u["Charidx"]))
        lst = gk.get(key)
        if not lst:
            lost.append(int(u["Userindex"]))
            continue
        out.append({"uid": int(u["Userindex"]), "booster": int(u["Code"]), "prize": lst.pop(0), "t": u["Edate"]})
    return out, lost


def _section_boosters(draws, rows, alpha, lost=0, events=None):
    by_row, no_row = {}, {}
    for d in draws:
        r = item_tok(d["booster"], 39)
        if r is None or r <= 0 or r > len(rows):
            no_row[d["booster"]] = no_row.get(d["booster"], 0) + 1
            continue
        x = by_row.setdefault(r, {"row": r, "boosters": {}, "obs": {}})
        x["boosters"][d["booster"]] = x["boosters"].get(d["booster"], 0) + 1
        x["obs"][d["prize"]] = x["obs"].get(d["prize"], 0) + 1
    tests = []
    for r, x in sorted(by_row.items(), key=lambda kv: -sum(kv[1]["obs"].values())):
        probs, total, miss = _booster_probs(rows[r - 1])
        t = gof_case(x["obs"], probs, stale=True)
        n = t["n"]
        top = sorted(set(x["obs"]) | set(probs), key=lambda c: -max(x["obs"].get(c, 0), n * probs.get(c, 0.0)))[:TOP_CODES]
        t.update(what="booster", row=r, total_w=total, miss=miss, codes=len(probs),
                 boosters=[{"code": c, "name": _name(c), "n": v} for c, v in sorted(x["boosters"].items(), key=lambda kv: -kv[1])],
                 top=[{"code": c, "name": _name(c), "n": x["obs"].get(c, 0), "expected": n * probs.get(c, 0.0), "prob": probs.get(c, 0.0)} for c in top],
                 outside=[{"code": c, "name": _name(c), "n": v} for c, v in t["outside"]])
        tests.append(t)
    holm(tests)
    for t in tests:
        t["verdict"] = verdict(t, alpha)
    return {"draws": len(draws), "lost": lost, "replay": replay(events, rows) if events is not None else None,
            "stale": sum(t["stale"] for t in tests),
            "rows": tests, "no_row": [{"code": c, "name": _name(c), "n": v} for c, v in sorted(no_row.items())],
            "verdicts": {v: sum(1 for t in tests if t["verdict"] == v) for v in ("ok", "deviation", "few", "contradiction")}}


def parse_gacha_log(lines, year):
    """Строки Log_GachaItem → [{t, uid, total, rate, code, gacha}] (год — из имени файла)."""
    out = []
    for ln in lines:
        m = _RX_GACHA.match(ln)
        if not m:
            continue
        mo, d, hh, mi, ss = (int(x) for x in m.groups()[:5])
        try:
            tt = datetime.datetime(int(year), mo, d, hh, mi, ss)
        except ValueError:
            continue
        out.append({"t": tt, "uid": int(m.group(6)), "total": int(m.group(7)), "rate": int(m.group(8)), "code": int(m.group(9)),
                    "gacha": int(m.group(10))})
    return out


def replay(events, rows):
    """Розыгрыш по текущей строке таблицы: сумма весов та же — победитель по броску (cum ≤ бросок < cum + вес) против Code журнала."""
    out = {"lines": len(events), "same_total": 0, "match": 0, "mismatch": 0, "other_total": 0, "no_row": 0, "bad": []}
    for e in events:
        r = item_tok(e["gacha"], 39)
        if r is None or r <= 0 or r > len(rows):
            out["no_row"] += 1
            continue
        act = [(c, w) for c, w in rows[r - 1] if c > 0 and w > 0]
        if sum(w for _c, w in act) != e["total"]:
            out["other_total"] += 1
            continue
        out["same_total"] += 1
        cum, win = 0, None
        for c, w in act:
            if cum <= e["rate"] < cum + w:
                win = c
                break
            cum += w
        if win == e["code"]:
            out["match"] += 1
        else:
            out["mismatch"] += 1
            if len(out["bad"]) < 20:
                out["bad"].append({"t": e["t"], "row": r, "rate": e["rate"], "code": e["code"], "want": win, "gacha": e["gacha"]})
    return out


def _listing(key, proc, kind):
    """Файлы журнала копии одним списком (logs.files): ({имя: (размер, время)}, список обрезан FILES_MAX, самое старое имя в списке)."""
    from domains import logs
    got = logs.files(key, proc, kind)
    have = {x["name"]: (int(x["size"]), int(x["mtime"] or 0)) for x in got["files"]}
    return have, bool(got.get("more")), (min(have) if have else None)


def _stat_of(key, proc, name, kind, lst):
    """(размер, время) файла: из списка; старше обрезанного списка — logs.stat по пути; иначе None (файла нет)."""
    from domains import logs
    have, more, oldest = lst
    if name in have:
        return have[name]
    if more and (oldest is None or name < oldest):
        st = logs.stat(key, proc, name, kind)
        return None if st is None else (int(st[0]), int(st[1] or 0))
    return None


def _scan_cached(key, proc, name, kind, needles, user, closed, st):
    """Строки файла журнала (logs.scan) с кэшем в памяти: тот же размер:время — без чтения; растущий — не чаще SCAN_TTL_S.
    st — (размер, время) из списка файлов. → (строки, truncated)."""
    from domains import logs
    k = (key, proc, kind, name)
    with _mem_lock:
        c = _mem.get(k)
    if c and (c["st"] == tuple(st) or (not closed and time.monotonic() - c["at"] < SCAN_TTL_S)):
        return c["lines"], c["truncated"]
    got = logs.scan(key, proc, name, kind=kind, needles=needles, show_ip=False, user=user, size=st[0])
    with _mem_lock:
        if len(_mem) > 128:
            _mem.clear()
        _mem[k] = {"st": tuple(st), "at": time.monotonic(), "lines": got["lines"], "truncated": bool(got.get("truncated"))}
    return got["lines"], bool(got.get("truncated"))


def _days(f, t):
    d0, d1 = datetime.datetime.strptime(f, "%Y%m%d"), datetime.datetime.strptime(t, "%Y%m%d")
    return [(d0 + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range((d1 - d0).days + 1)]


def gacha_log(f, t, today, user, errors, notes):
    """События Log_GachaItem всех копий GameServer за дни периода (белый список logs, один список файлов на копию, бюджет — на пользователя)."""
    from domains import logs
    ev = []
    for proc in logs.procs_of("gslog"):
        try:
            lst = _listing("gslog", proc, GACHA_KIND)
            for d in _days(f, t):
                name = "CachaItemLog_%s.txt" % d
                st = _stat_of("gslog", proc, name, GACHA_KIND, lst)
                if st is None:
                    continue
                lines, trunc = _scan_cached("gslog", proc, name, GACHA_KIND, ("Recv_GachaItemUse()",), user, d < today, st)
                if trunc:
                    notes.append("журнал %s прочитан не целиком (больше 16 МБ)" % name)
                ev += parse_gacha_log(lines, d[:4])
        except OpRefused as ex:                 # Throttled — подкласс; нет папки копии — тоже здесь
            errors.append("журнал Log_GachaItem %s не прочитан: %s" % (proc, ex))
            return ev
    return ev


CRTJIN_KIND = "Log_CRTJIN"
_RX_REFUSE = re.compile(r"Recv_GachaItemUse\((\d+)\)")
REFUSE_AFTER = {9: "miss", 10: "slot", 11: "flag35", 12: "slot", 13: "slot", 14: "slot", 15: "unknown_code", 16: "weight"}


def crtjin_refusals(f, t, today, user, errors):
    """★ ревизия 55 Н-4: отказы вскрытия ПОСЛЕ броска (журнал Log_CRTJIN, канал 26: «Recv_GachaItemUse(N)», GameServer.c:94376–94522) —
    9 промах, 10/12/13/14 нет ячейки, 11 флаг +35 вещи, 15 неизвестный код, 16 перевес. Бустер не тратится, в базе и Log_GachaItem ничего;
    учётки в строке нет — счёт общий. → {код: строк}."""
    from domains import logs
    out = {}
    for proc in logs.procs_of("gslog"):
        try:
            lst = _listing("gslog", proc, CRTJIN_KIND)
            for d in _days(f, t):
                name = "CRTJIN_%s.txt" % d
                st = _stat_of("gslog", proc, name, CRTJIN_KIND, lst)
                if st is None:
                    continue
                lines, _tr = _scan_cached("gslog", proc, name, CRTJIN_KIND, ("Recv_GachaItemUse(",), user, d < today, st)
                for ln in lines:
                    m = _RX_REFUSE.search(ln)
                    if m and int(m.group(1)) in REFUSE_AFTER:
                        out[int(m.group(1))] = out.get(int(m.group(1)), 0) + 1
        except OpRefused as ex:
            errors.append("журнал Log_CRTJIN %s не прочитан: %s" % (proc, ex))
            return out
    return {str(k): v for k, v in sorted(out.items())}


def boosters(q, user=None):
    """Бустеры: призы (BoosterUse + BoosterGain*) против весов GachaItemRateTable (условно «не промах»), хи-квадрат по строке таблицы;
    журнал Log_GachaItem — воспроизведение розыгрыша (logs=0 — без журнала). → dict."""
    check_input(q, "boosters")
    svc, alpha, with_logs = _svc(q), _alpha(q), _logs_flag(q)
    out = {"svc": svc, "alpha": alpha, "period": None, "errors": [], "notes": [], "capped": [], "main": None, "service": None, "replay": None,
           "lost": 0, "table_rows": None, "refused": None}
    tb = _tables(out["errors"], ("GachaItemRateTable.txt",))
    rows = tb["GachaItemRateTable.txt"]
    out["table_rows"] = len(rows) if rows is not None else None
    try:
        with db.GameReader("joylog1") as g:
            today = _today(g)
            f, t = _period(q, today)
            out["period"] = {"from": f, "to": t}
            uses = _rows(g, SQL_BUSE, (f, t), "BoosterUse", out["errors"], out["capped"]) or []
            gains = []
            for tab in GAIN_TABLES:
                gains += _rows(g, SQL_BGAIN % tab, (f, t), tab, out["errors"], out["capped"]) or []
    except db.DbError as ex:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex)
        return out
    draws, lost = booster_draws(uses, gains)
    out["lost"] = len(lost)
    if rows is None:
        return out
    sd = _split(draws, svc, uid=lambda d: d["uid"])
    sl = _split(lost, svc, uid=lambda u: u)
    se = {"player": None, "service": None}
    if with_logs:
        ev = gacha_log(f, t, today, user or "odds.boosters", out["errors"], out["notes"])
        se = _split(ev, svc, uid=lambda e: e["uid"])
        out["replay"] = replay(ev, rows)
        out["refused"] = crtjin_refusals(f, t, today, user or "odds.boosters", out["errors"])
    out["main"] = _section_boosters(sd["player"], rows, alpha, len(sl["player"]), se["player"])
    if svc == "sep":
        out["service"] = _section_boosters(sd["service"], rows, alpha, len(sl["service"]), se["service"])
    return out


# =====================================================================================================================
# ПРЕМИУМ-КОРОБКИ gp7
# =====================================================================================================================
def parse_lucky(lines):
    """Строки журнала шлюза → [{t, uid, code, index, count}] — только SEND 0x0051 status=1 subtype=2 (лаки-бокс выдан)."""
    out = []
    for ln in lines:
        m = _RX_SEND.match(ln)
        if m:
            out.append({"t": m.group(1), "uid": int(m.group(2)), "code": int(m.group(3)), "index": int(m.group(4)), "count": int(m.group(5))})
    return out


def _disk_cache(name):
    return os.path.join(CACHE_DIR, name + ".json")


def _lucky_day(d, today, user, lst):
    """Розыгрыши коробок за сутки: закрытые сутки — из кэша на диске (ключ размер:время файла), иначе журнал читается (бюджет на
    пользователя). → (список | None — файла нет, читалось ли сейчас)."""
    name = "gp7-%s.log" % d
    st = _stat_of(GP7_KEY, GP7_PROC, name, None, lst)
    if st is None:
        return None, False
    stamp = "%d:%d" % st
    p = _disk_cache(name)
    if d < today:
        try:
            with open(p, encoding="utf-8") as fh:
                j = json.load(fh)
            if j.get("stamp") == stamp:
                return j["draws"], False
        except (OSError, ValueError, KeyError):
            pass
    lines, trunc = _scan_cached(GP7_KEY, GP7_PROC, name, None, (" subtype=2 ",), user, d < today, st)
    draws = parse_lucky(lines)
    if d < today and not trunc:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(p + ".part", "w", encoding="utf-8") as fh:
                json.dump({"stamp": stamp, "draws": draws}, fh)
            os.replace(p + ".part", p)
        except OSError:
            pass                                  # кэш не записался — в следующий раз сутки прочитаются снова
    return draws, True


def _section_boxes(draws, rows, pools, alpha):
    by, bad = {}, 0
    for d in draws:
        r = rows.get(d["index"])
        if r is None or r[1] != d["code"] or r[2] != d["count"]:
            bad += 1
            continue
        cell = by.setdefault(r[0], {})
        cell[d["index"]] = cell.get(d["index"], 0) + 1
    tests = []
    for box in sorted(set(by) | set(pools)):
        pool = sorted(pools.get(box, []))
        obs = by.get(box, {})
        n = sum(obs.values())
        if not pool:
            continue
        # равномерно по строкам: подряд идущие строки сливаются в корзины так, чтобы ожидание корзины было ≥ MIN_EXP
        size = max(1, int(math.ceil(MIN_EXP * len(pool) / float(n)))) if n else len(pool)
        bins_o, bins_p = {}, {}
        for i, ix in enumerate(pool):
            b = i // size
            bins_o[b] = bins_o.get(b, 0) + obs.get(ix, 0)
            bins_p[b] = bins_p.get(b, 0.0) + 1.0 / len(pool)
        t = gof_case(bins_o, bins_p)
        codes = {}
        for ix in pool:
            codes.setdefault(rows[ix][1], [0, 0])[0] += 1
            codes[rows[ix][1]][1] += obs.get(ix, 0)
        top = sorted(codes.items(), key=lambda kv: -max(kv[1][1], n * kv[1][0] / float(len(pool))))[:LOT_TOP]
        t.update(what="box", box=box, pool=len(pool), bin_rows=size,
                 top=[{"code": c, "name": _name(c), "rows": v[0], "n": v[1], "expected": n * v[0] / float(len(pool))} for c, v in top])
        tests.append(t)
    holm(tests)
    for t in tests:
        t["verdict"] = verdict(t, alpha)
    return {"draws": len(draws) - bad, "mismatch": bad, "boxes": tests,
            "verdicts": {v: sum(1 for t in tests if t["verdict"] == v) for v in ("ok", "deviation", "few", "contradiction")}}


def boxes(q, user=None):
    """Премиум-коробки gp7: розыгрыши из журнала шлюза (rewardIndex — строка PrimiumGaChaTable) против равномерного выбора по строкам
    автомата (как server.js selectLuckyBoxReward). Журнал читается с бюджетом на пользователя; закрытые сутки разбираются один раз (кэш). → dict."""
    from domains import logs
    check_input(q, "boxes")
    svc, alpha = _svc(q), _alpha(q)
    out = {"svc": svc, "alpha": alpha, "period": None, "errors": [], "notes": [], "main": None, "service": None,
           "days": {"read": 0, "cached": 0, "missing": 0, "unread": []}}
    tb = _tables(out["errors"], ("PrimiumGaChaTable.txt",))
    try:
        with db.GameReader("joylog1") as g:
            today = _today(g)
            f, t = _period(q, today)
    except db.DbError as ex:
        out["errors"].append("журналы JoyLog1 не прочитаны: %s" % ex)
        return out
    out["period"] = {"from": f, "to": t}
    draws = []
    stop = None
    try:
        lst = _listing(GP7_KEY, GP7_PROC, None)
    except OpRefused as ex:
        out["errors"].append("журнал шлюза gp7 %s не прочитан: %s" % (GP7_PROC, ex))
        return out
    for d in _days(f, t):
        if stop:
            out["days"]["unread"].append(d)
            continue
        try:
            got, fresh = _lucky_day(d, today, user or "odds.boxes", lst)
        except logs.Throttled as ex:
            stop = str(ex)
            out["days"]["unread"].append(d)
            continue
        except OpRefused as ex:
            out["errors"].append("журнал шлюза gp7 %s не прочитан: %s" % ("gp7-%s.log" % d, ex))
            out["days"]["unread"].append(d)
            continue
        if got is None:
            out["days"]["missing"] += 1
            continue
        out["days"]["read" if fresh else "cached"] += 1
        draws += got
    if out["days"]["unread"]:
        out["notes"].append("суток журнала шлюза не прочитано: %d (бюджет чтения журналов на пользователя исчерпан — прочитанное запомнено, "
                            "повторите через минуту)" % len(out["days"]["unread"]))
    if tb["PrimiumGaChaTable.txt"] is None:
        return out
    rows, pools = tb["PrimiumGaChaTable.txt"]
    out["pool_rows"] = len(rows)
    sd = _split(draws, svc, uid=lambda d: d["uid"])
    out["main"] = _section_boxes(sd["player"], rows, pools, alpha)
    if svc == "sep":
        out["service"] = _section_boxes(sd["service"], rows, pools, alpha)
    return out


def public(v):
    """Ответ → JSON-пригодный (множества — списки, даты — строки)."""
    if isinstance(v, dict):
        return {k: public(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [public(x) for x in v]
    if isinstance(v, set):
        return sorted(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v.isoformat()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v
