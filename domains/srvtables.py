# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""srvtables.py — живые таблицы предметов СЕРВЕРА (авторитет — сервер) для правил операций над предметами. 16.11.2026.

ОТКУДА. <стойка>\\GameServer\\ItemTable_Info\\{Item_Table,Cellob_Table,SowelCombine}.txt — те же файлы, что читает
GameServer при старте (sub_4A96A0 / :68663 / :65161). Формат: первая строка — число записей, далее записи токенами через
пробельные символы (fscanf "%s"), токен 0 — код. На сервере читаются с диска, на ПК — копия по scp (кэш data/srv_cache,
обновляется раз в процесс). Таблица перечитывается, если файл на сервере изменился (mtime).

ПОЛЯ (номер токена → смещение записи сервера; разбор GameServer.c:68195-68330, сверка с research_item_props.md):
  Item_Table  t1 +4 прочность, t2 +5 вес, t3 +7 вид (4 = щит, допустимый при двуручном), t4 +8 мин. уровень,
              t5 +9 (уровень: «+8 ≤ lvl ИЛИ +9 < lvl»), t7 +10 требование класса, t16 +26 itemType = слот экипировки,
              t17 +27 подтип, t23 +35 стопка, t24 +36 (==3 → сумка 1), t27 +45 (==2 → двуручное), t35 +58 (==1 → привязка
              при надевании), t39 +63 (>0 → пакет/гача, не надевается).
  Cellob_Table t16 +32 мин. уровень самоцвета (гнёзда надеваемого предмета), t17 +33 Owner.
  SowelCombine t44 +146 MaxupCnt (при перемещении сервер поднимает MaxupCnt записи до этого значения, GameServer.c:82477).
Побочных эффектов при импорте нет.
"""
import os
import threading

from core import config, hostshell

TABLE_DIR = r"GameServer\ItemTable_Info"
ITEM_BASE, CELLOB_BASE = 20551, 7001
_lock = threading.Lock()
_cache = {}            # имя → (mtime, {код: [токены]})
LOCAL_CACHE = os.path.join(config.DATA_DIR, "srv_cache")


def _server_path(name):
    return config.STACK_ROOT + "\\" + TABLE_DIR + "\\" + name


def _local_copy(name):
    """На ПК — копия файла сервера (scp раз в процесс: за время работы ПК-службы таблицы НЕ обновляются — перепроверка 5
    М9); на сервере — сам файл (сверка времени файла раз в RECHECK_S)."""
    cfg = config.get()
    if cfg.on_server:
        return _server_path(name)
    os.makedirs(LOCAL_CACHE, exist_ok=True)
    dst = os.path.join(LOCAL_CACHE, name)
    if name not in _copied:
        import subprocess
        exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
        r = subprocess.run([exe if os.path.exists(exe) else "scp", "-i", config.SSH_KEY, "-o", "BatchMode=yes",
                            "%s:%s" % (config.SSH_HOST, _server_path(name).replace("\\", "/")), dst + ".part"],
                           capture_output=True, timeout=180)
        if r.returncode == 0:
            os.replace(dst + ".part", dst)
            _copied.add(name)
        elif not os.path.exists(dst):
            raise hostshell.HostError("таблица сервера %s не скопирована: %s" % (name, r.stderr.decode("utf-8", "replace")[:200]))
        else:
            # перепроверка 5 В3: нет SSH — работаем на прежней копии и scp больше не повторяем (иначе 180 с под общим
            # замком каждые RECHECK_S по каждой таблице)
            _copied.add(name)
    return dst


_copied = set()


RECHECK_S = 30          # как часто сверять файл таблицы с диском (раньше — при КАЖДОМ обращении: 23 818 stat+mkdir
                        # на одно окно свойств предмета, 5–15 с; владелец 16.11: «панель очень медленная»)
_checked = {}           # имя → время последней сверки


def table(name):
    """{код: [токены строкой]} таблицы сервера (кэш, перечитывается при смене файла; файл сверяется раз в RECHECK_S)."""
    import time
    with _lock:
        hit = _cache.get(name)
        now = time.monotonic()
        if hit and now - _checked.get(name, 0) < RECHECK_S:
            return hit[1]
        path = _local_copy(name)
        mt = os.path.getmtime(path)
        _checked[name] = now
        if hit and hit[0] == mt:
            return hit[1]
        rows = {}
        # первая строка — число записей; дальше строка = запись, поля через TAB (так же делит проверенная утилита
        # выдачи asda_give._read_table — номера полей совпадают с её разбором и с токенами сервера)
        for ln in open(path, "rb").read().decode("cp1251", "replace").splitlines()[1:]:
            f = [t.strip() for t in ln.split("\t")]
            if f and f[0].lstrip("-").isdigit():
                rows[int(f[0])] = f
        _cache[name] = (mt, rows)
        return rows


def _i(f, k):
    try:
        return int(f[k])
    except (IndexError, ValueError, TypeError):
        return 0


def item_rule(code):
    """Правила надевания предмета Item_Table (None — код не из Item_Table)."""
    f = table("Item_Table.txt").get(int(code))
    if f is None:
        return None
    return {"durability_max": _i(f, 1), "kind": _i(f, 3), "lvl_min": _i(f, 4), "lvl_max": _i(f, 5), "job_req": _i(f, 7),
            "type": _i(f, 16), "subtype": _i(f, 17), "stack": _i(f, 23), "plate_flag": _i(f, 24), "two_hand": _i(f, 27),
            "bind": _i(f, 35), "package": _i(f, 39), "arrow_kind": _i(f, 21)}   # t21 +33 — вид стрел у оружия (1 лук, 2 арбалет; GameServer.c:82732)


def cellob_level(code):
    """Минимальный уровень самоцвета (Cellob_Table t16, +32); не самоцвет — 0."""
    f = table("Cellob_Table.txt").get(int(code))
    return _i(f, 16) if f else 0


def sowel_maxup(code):
    """MaxupCnt из SowelCombine (t44, +146); нет строки — 0."""
    f = table("SowelCombine.txt").get(int(code))
    return _i(f, 44) if f else 0


# ---------------------------------------------------------------------------------------------------------------------
# ОПЦИИ ПРЕДМЕТА (16.11.2026, правка свойств предмета в панели). Разбор — точная копия загрузчиков сервера:
#   Item_OptionTable.txt (GameServer.c:70719-70806): первое число — строк N; далее N записей по 43 токена ПОТОКОМ (fscanf
#     "%s": пустое поле сдвигает хвост — повторяем так же): группа, тип опции, накопленный вес, 20 пар (значение, порог).
#     Группа k = ПЕРВАЯ непрерывная серия строк с номером k; групп = число серий (k вне — «нет группы»).
#   выбор типа sub_4A7EE0 (:67478): бросок 1…100000, первая строка с весом ≥ броска → тип выпадает, только если его вес
#     больше веса предыдущей строки; выбор значения sub_4A7FC0 (:67505): то же по 20 порогам → значение выпадает, только
#     если его порог больше предыдущего (и > 0).
#   OptionUpgrade.txt (:65277-65306): N; записи (тип, режим, прирост); запись ищется по индексу = типу, действует, если её
#     тип = индексу. Режим 1 — значение += прирост, режим 2 — += int(прирост × значение / 100), не меньше 1.
# ---------------------------------------------------------------------------------------------------------------------
_opt_cache = {}


def _tokens(name):
    """(время файла, разобранное из кэша | токены файла, из_кэша). Файл сверяется раз в RECHECK_S, как у table()."""
    import time
    hit = _opt_cache.get(name)
    now = time.monotonic()
    if hit and now - _checked.get("tok:" + name, 0) < RECHECK_S:
        return hit[0], hit[1], True
    path = _local_copy(name)
    mt = os.path.getmtime(path)
    _checked["tok:" + name] = now
    if hit and hit[0] == mt:
        return mt, hit[1], True
    return mt, open(path, "rb").read().decode("cp1251", "replace").split(), False


def _atol(s):
    """atol: ведущее целое, иначе 0."""
    import re as _re
    m = _re.match(r"\s*([+-]?\d+)", s or "")
    return int(m.group(1)) if m else 0


def option_groups():
    """{группа: [(тип, накопленный вес, [20 значений], [20 порогов])]} — как видит сервер."""
    with _lock:
        mt, toks, cached = _tokens("Item_OptionTable.txt")
        if cached:
            return toks
        n, pos, rows = _atol(toks[0]), 1, []
        for _ in range(n):
            rec = toks[pos:pos + 43]
            pos += 43
            if len(rec) < 43:
                break
            rows.append((_atol(rec[0]), _atol(rec[1]), _atol(rec[2]),
                         [_atol(rec[3 + 2 * j]) for j in range(20)], [_atol(rec[4 + 2 * j]) for j in range(20)]))
        series, last = 0, None
        for r in rows:
            if r[0] != last:
                series += 1
                last = r[0]
        groups = {}
        for k_rows in _first_runs(rows):
            k = k_rows[0][0]
            if 0 <= k < series and k not in groups:
                groups[k] = [(r[1], r[2], r[3], r[4]) for r in k_rows]
        _opt_cache["Item_OptionTable.txt"] = (mt, groups)
        return groups


def _first_runs(rows):
    run = []
    for r in rows:
        if run and r[0] != run[0][0]:
            yield run
            run = []
        run.append(r)
    if run:
        yield run


def group_types(g):
    """Типы опций, которые реально выпадают в группе g (sub_4A7EE0): [(тип, шанс %)]."""
    rows = option_groups().get(int(g)) if g is not None else None
    out, prev = {}, 0
    for t, w, _v, _p in rows or []:
        if w > prev and w >= 1:
            # тип, встречающийся в группе несколько раз, — один пункт, шансы складываются; значения у сервера берутся
            # из первой строки этого типа (group_values) — перепроверка 3 М3
            out[t] = out.get(t, 0) + (min(w, 100000) - prev) / 1000.0
        prev = max(prev, w)
    return [(t, round(p, 3)) for t, p in out.items()]


def group_values(g, t):
    """Значения опции типа t в группе g, которые реально выпадают (sub_4A7FC0): [(значение, шанс %)]."""
    for typ, _w, vals, thr in option_groups().get(int(g), []):
        if typ == int(t):
            out, prev = {}, 0
            for v, th in zip(vals, thr):
                if th > prev and th >= 1:
                    out[v] = out.get(v, 0) + (min(th, 100000) - prev) / 1000.0
                prev = max(prev, th)
            return sorted((v, round(p, 3)) for v, p in out.items())
    return []


def option_upgrade():
    """OptionUpgrade.txt → {тип: (режим, прирост)} (только записи с типом = индексу, как проверяет сервер)."""
    with _lock:
        mt, toks, cached = _tokens("OptionUpgrade.txt")
        if cached:
            return toks
        n, out = _atol(toks[0]), {}
        for i in range(n):
            rec = toks[1 + 3 * i: 4 + 3 * i]
            if len(rec) == 3 and _atol(rec[0]) == i:
                out[i] = (_atol(rec[1]), _atol(rec[2]))
        _opt_cache["OptionUpgrade.txt"] = (mt, out)
        return out


def _i16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


# ---------------------------------------------------------------------------------------------------------------------
# ЗАТОЧКА (16.11.2026, владелец: «поменял ступень — в игре сменилось только качество, +n% нет»). Разбор Recv_User_ShellItemUpgrade
# (GameServer.c:98760-99050):
#   удача: Upcount(+24) += 1, AcuUpcnt(+25) += 1, Updamage(+27) += шаг свитка (ItemUpgrade +8) + усилитель (Function_Table
#   тип 97, +9; :98814-98828); неудача: только AcuUpcnt += 1 (купон/свиток сверх t44 — сброс в 0).
#   «+N%» на иконке и сила предмета — Updamage: клиент рисует sprintf("+%d%%", +27) (item_enhance.c:7645) и считает атаку/защиту
#   как Updamage × множитель + основа (item_inventory.c:24289, 62499). Ступень сама характеристик не даёт.
#   Свиток подходит предмету: вид свитка (+10) ∈ {1,2,3} для брони/щита (тип 0–4, 8), ∈ {0,2,3} для оружия (тип 9) (:98868);
#   уровень свитка (+11) = SowelCombine +150 (токен 46), кроме вида 2 и типов 74/84/91 (:98906).
#   Сверх t44 шанс умножается на OverUpgrade.txt[ступень − t44] (:98940-98950): шанс 0 — дальше не заточить.
#   ItemUpgrade.txt: N, затем N строк «тип мин макс шанс шаг% вид уровень» (загрузчик :70990-71030).

def item_upgrade_rows():
    """ItemUpgrade.txt → [(тип, шанс, шаг %, вид, уровень)]."""
    with _lock:
        mt, toks, cached = _tokens("ItemUpgrade.txt")
        if cached:
            return toks
        n, out = _atol(toks[0]), []
        for i in range(n):
            rec = toks[1 + 7 * i: 8 + 7 * i]
            if len(rec) == 7:
                out.append((_atol(rec[0]), _atol(rec[3]), _atol(rec[4]), _atol(rec[5]), _atol(rec[6])))
        _opt_cache["ItemUpgrade.txt"] = (mt, out)
        return out


def over_upgrade_steps():
    """Сколько ступеней сверх t44 можно получить: число первых записей OverUpgrade.txt с шансом > 0."""
    with _lock:
        mt, toks, cached = _tokens("OverUpgrade.txt")
        if cached:
            return toks
        n, k = _atol(toks[0]), 0
        for i in range(n):
            rec = toks[1 + 2 * i: 3 + 2 * i]
            if len(rec) != 2 or _atol(rec[0]) != i or _atol(rec[1]) <= 0:
                break
            k += 1
        _opt_cache["OverUpgrade.txt"] = (mt, k)
        return k


def upgrade_boost_max():
    """Наибольший усилитель процента заточки: Function_Table, функция (+8, токен 5) = 97, значение (+9, токен 6)."""
    best = 0
    for f in table("Function_Table.txt").values():
        if _i(f, 5) == 97:
            best = max(best, _i(f, 6))
    return best


def upgrade_rule(code):
    """Правило заточки предмета: {t44, max (предел ступени), steps (шаги % подходящих свитков), default_step, boost_max}.
    default_step — шаг обычного свитка с наибольшим шансом (без гарантированного типа 91): так и заточено большинство
    предметов на живой базе (91 из 125 — ровно 8 % за ступень, 16.11)."""
    rule = item_rule(code) or {}
    typ = rule.get("type")
    kinds = {1, 2, 3} if typ in (0, 1, 2, 3, 4, 8) else ({0, 2, 3} if typ == 9 else set())
    sc = table("SowelCombine.txt").get(int(code)) or []
    lvl = _i(sc, 46)
    rows = [r for r in item_upgrade_rows() if r[3] in kinds and (r[3] == 2 or r[0] in (74, 84, 91) or r[4] == lvl)]
    steps = sorted({r[2] for r in rows if r[2] > 0})
    usual = [r for r in rows if r[0] != 91 and r[2] > 0]
    default = max(usual, key=lambda r: (r[1], r[2]))[2] if usual else (steps[0] if steps else 0)
    t44 = sowel_maxup(code)
    # перепроверка 5 В1: свиток 91 ставит шанс 100000 ПОСЛЕ умножения на OverUpgrade (GameServer.c:98955) — им можно
    # заточить и там, где OverUpgrade даёт 0; держит только «ступень − t44 ≤ 254» (:98946) и байт ступени (+24) → 255
    sure = sorted({r[2] for r in rows if r[0] == 91 and r[2] > 0})
    normal = t44 + over_upgrade_steps()
    return {"t44": t44, "max_normal": normal, "max": 255 if sure else normal, "steps": steps, "sure_steps": sure,
            "default_step": default, "boost_max": upgrade_boost_max()}


def updamage_reachable(urule, up, value, boost=True):
    """Можно ли набрать «+N%» = value за up удачных заточек: первые min(up, max_normal) — любым подходящим свитком,
    дальше — только гарантированным (тип 91); к каждому шагу — усилитель или нет (перепроверка 5 М3)."""
    b = urule["boost_max"] if boost else 0
    add = lambda st: sorted({s for s in st} | ({s + b for s in st} if b else set()))
    first, rest = add(urule["steps"]), add(urule["sure_steps"])
    n1 = min(up, urule["max_normal"])
    if up > n1 and not rest:
        return False
    if value < 0:
        return False
    mask = (1 << (value + 1)) - 1
    sums = 1                                   # бит k = «сумма k достижима»
    for i in range(up):
        st = first if i < n1 else rest
        nxt = 0
        for s in st:
            nxt |= sums << s
        sums = nxt & mask
        if not sums:
            return False
    return bool(sums >> value & 1)


def upgrade_value(t, base, upcount):
    """Значение опции заточки на ступени upcount (≥ 6) при выпавшем на +6 значении base (GameServer.c:99018-99035, 118207)."""
    v = _i16(base)
    rule = option_upgrade().get(int(t))
    for _ in range(6, min(int(upcount), 20)):
        if not rule:
            break
        mode, inc = rule
        if mode == 1:
            v = _i16(v + inc)
        elif mode == 2:
            d = int(inc * v / 100.0)
            v = _i16(v + (d if d > 0 else 1))
    return v


def item_option_groups(code):
    """Группы опций предмета: пары 1–2 — Item_Table t10/t13 (создание, sub_5340B0), 4 — SowelCombine col49 (+154, заточка),
    5 — col50 (+156, высшая переработка)."""
    f = table("Item_Table.txt").get(int(code)) or []
    s = table("SowelCombine.txt").get(int(code)) or []
    return {1: _i(f, 10), 2: _i(f, 13), 4: _i(s, 48), 5: _i(s, 49)}


def cellob(code):
    """Поля самоцвета (Cellob_Table: t3 +6 вес, t4 +7 расход прочности при замене, t7 +11 «особый», t8/t9/t10 +12/+13/+14
    виды, t16 +32 уровень, t17 +33 Owner, t18 +34 маска подтипов оружия) или None."""
    f = table("Cellob_Table.txt").get(int(code))
    if not f:
        return None
    return {"weight": _i(f, 3), "dur_cost": _i(f, 4), "special": _i(f, 7), "k1": _i(f, 8), "k2": _i(f, 9), "k3": _i(f, 10),
            "lvl": _i(f, 16), "owner": _i(f, 17), "mask": _atol_q(f[18] if len(f) > 18 else "0")}


def _atol_q(tok):
    """Маска подтипов оружия как у сервера: `*(_QWORD *)(+34) = atol(tok)` — atol MSVC зажимает к LONG_MIN…LONG_MAX,
    long расширяется знаком до 64 бит."""
    v = max(-2147483648, min(2147483647, _atol(tok)))
    return v & 0xFFFFFFFFFFFFFFFF


def sowel_error(item_code, sowel_code, socket, char_lvl):
    """Код отказа сервера при вставке самоцвета (sub_4DE250 / sub_4DE530, GameServer.c); 0 — можно."""
    c = cellob(sowel_code)
    r = item_rule(item_code)
    if not c or not r:
        return 7
    if c["lvl"] > char_lvl:
        return 10
    kind = _i(table("Item_Table.txt").get(int(item_code)), 3)
    if socket == 4 or kind == 4:
        return 6
    if (socket and not c["special"]) or (not socket and c["special"]):
        return 6
    if kind < socket:
        return 8
    t26, t27 = r["type"], r["subtype"]
    if c["special"] or t26 != 9:
        if t26 in (c["k1"], c["k2"], c["k3"]) or c["k1"] in (12, 13, 15) or (c["k1"] == 14 and t26 != 8):
            return 0
        return 7
    return 0 if c["mask"] and (c["mask"] >> t27) & 1 else 11


def socket_count(item_code):
    """Гнёзд у предмета: 0 (гнездо 0) … t3; t3 == 4 — гнёзд нет (sub_4DE250)."""
    kind = _i(table("Item_Table.txt").get(int(item_code)), 3)
    return 0 if kind == 4 else min(kind, 3) + 1


# ---------------------------------------------------------------------------------------------------------------------
# УРОВЕНЬ (17.11.2026, разбор Reports/admin_center/research_level_job.md). Файлы GameServer\ConfigSet:
#   ClassStat.txt  N, затем строки «класс уровень Str Agi Hea Spe Men For» (загрузчик GameServer.c:69181; база = ClassStat[Class][Lvl],
#                  sub_43AF30 :24510 — при каждом повышении и при входе в мир);
#   ExpTable.txt   N, затем «уровень опыт» (sub_4AC640 :69098): E[L] — накопленный опыт НАЧАЛА уровня L; уровень L ⇔ E[L] ≤ Expe < E[L+1];
#   patches.ini    [P29_LevelCap] Enabled / MaxLevel — потолок (сток 59 = 0x3B, :81009).
_cfg = {}


def _cfg_text(name, ttl=60):
    """Текст файла GameServer/ConfigSet/<name> (кэш ttl с)."""
    import time
    hit = _cfg.get(name)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    txt = hostshell.read_server_file(config.STACK_ROOT + r"\GameServer\ConfigSet" + "\\" + name)
    _cfg[name] = (time.monotonic(), txt)
    return txt


def class_stat():
    """{(класс, уровень): [Str, Agi, Hea, Spe, Men, For]} — как загрузчик GS (:69181): по порядку записей, значения int16, на первой
    неполной/нечисловой записи загрузка обрывается (перепроверка 11 М4)."""
    import re as _re
    toks = _cfg_text("ClassStat.txt").split()
    n, out = _atol(toks[0]) if toks else 0, {}
    for i in range(n):
        rec = toks[1 + 8 * i: 9 + 8 * i]
        if len(rec) != 8 or not all(_re.match(r"^[+-]?\d+$", x) for x in rec):
            break
        out[(_atol(rec[0]), _atol(rec[1]))] = [_i16(_atol(x)) for x in rec[2:]]
    return out


def exp_table():
    """{уровень: накопленный опыт начала уровня} — как sub_4AC640 (:69098): уровень = номер ЗАПИСИ (1…N), опыт — ведущее целое
    (_atoi64); запись, где столбец уровня не совпал с номером, — таблица не согласована → отказ вызывающему (перепроверка 11 М4)."""
    import re as _re
    toks = _cfg_text("ExpTable.txt").split()
    n, out = _atol(toks[0]) if toks else 0, {}
    for i in range(n):
        rec = toks[1 + 2 * i: 3 + 2 * i]
        if len(rec) != 2:
            break
        m = _re.match(r"\s*([+-]?\d+)", rec[1])
        out[i + 1] = int(m.group(1)) if m else 0
        if _atol(rec[0]) != i + 1:
            raise hostshell.HostError("ExpTable.txt: запись %d содержит уровень %s — таблица не согласована" % (i + 1, rec[0]))
    return out


def open_maps():
    """Карты, которые GameServer поднимает: GameServer/MapData_Info/OpenMapInfo.ini — [MAP_n] Use = 1 и n < [MAP_INFO] MapCount
    (GS создаёт поток карты только при Use = 1 — GameServer.c:66193, перепроверка 17 В2; на dev 19–22 — Use 0, MapCount 21)."""
    txt = hostshell.read_server_file(config.STACK_ROOT + r"\GameServer\MapData_Info\OpenMapInfo.ini")
    sec, use, count = None, {}, None
    for ln in txt.splitlines():
        t = ln.strip()
        if t.startswith("[") and t.endswith("]"):
            sec = t[1:-1].strip().upper()
        elif "=" in t and sec:
            k, v = [x.strip() for x in t.split("=", 1)]
            if sec == "MAP_INFO" and k.lower() == "mapcount":
                count = _atol(v)
            elif sec.startswith("MAP_") and k.lower() == "use" and sec[4:].isdigit():
                use[int(sec[4:])] = _atol(v)
    if count is None:
        raise ValueError("OpenMapInfo.ini: нет MapCount")
    return {m for m, u in use.items() if u == 1 and m < count}


def patches_ini():
    """{секция: {ключ: значение}} живого GameServer/ConfigSet/patches.ini (UTF-16 — hostshell.decode_text)."""
    out, sec = {}, None
    for ln in _cfg_text("patches.ini").splitlines():
        t = ln.strip()
        if not t or t.startswith(";"):
            continue
        if t.startswith("[") and t.endswith("]"):
            sec = t[1:-1].strip()
            out.setdefault(sec, {})
        elif sec and "=" in t:
            k, v = [x.strip() for x in t.split("=", 1)]
            out[sec][k.lower()] = v
    return out


def patch_on(section, ini=None):
    """Патч действует: [General] MasterEnable = 1 и секция есть с Enabled ≠ 0 (нет ключа — по умолчанию DLL «включён»)."""
    ini = ini if ini is not None else patches_ini()
    if not str(ini.get("General", {}).get("masterenable", "0")).startswith("1"):
        return False
    sec = ini.get(section)
    return sec is not None and not str(sec.get("enabled", "1")).startswith("0")


def max_level():
    """Потолок уровня, как его ставит AsdaPatch P29: MaxLevel, зажатый длиной таблиц (ExpTable − 1, ClassStat / 4 класса) и 127;
    патч не действует — стоковые 59 (перепроверка 11 М1). ⚠ GS держит значения с момента старта: правка ini без перезапуска
    сервера разведёт панель и игру (М3)."""
    ini = patches_ini()
    if not patch_on("P29_LevelCap", ini):
        return 59
    mx = _atol(ini["P29_LevelCap"].get("maxlevel", "100"))
    et, cs = exp_table(), class_stat()
    per_class = len(cs) // 4 if cs else 0
    return max(1, min(mx, len(et) - 1, per_class, 127))


def stat_points_top():
    """До какого уровня повышение даёт +2 очка навыков: P29 StatPoints = 1 — до потолка, иначе стоковые 59 (перепроверка 11 М2)."""
    ini = patches_ini()
    if patch_on("P29_LevelCap", ini) and str(ini["P29_LevelCap"].get("statpoints", "1")).startswith("1"):
        return max_level()
    return 59


# ---------------------------------------------------------------------------------------------------------------------
# ПРОФЕССИЯ (17.11.2026, разбор Reports/admin_center/research_job_change_write.md). Файлы GameServer:
#   SkillTable_Info/SkillInfo.sif — записи по 209 б (индекс записи = номер навыка): +189 дерево (категория), +190 нужно очков
#     категории, +200/+203/+206 int16 предшественник (−1 нет) и +202/+205/+208 его уровень; поля нулевого уровня (sub_475F20 →
#     UPSkillAdd): +47 i32 Cooltime, +53 u8 Distance, +55 u8 Scope, +58 i16 Mpvalue, +62 i16 Evalue, +66 u8 SkillPer, +68 u8 SubSkillPer,
#     +74 i16 SubValue1, +78 i32 SubTime1, +91 i16 SubValue2, +95 i32 SubTime2, +108 i16 SubValue3, +112 i32 SubTime3;
#   SkillTable_Info/ChangeJobAddSkillTable.txt — «строка количество навыки…» (строка = Job для 1–3-й, Subjob для 4-й; :71620);
#   ConfigSet/FameInfo.txt — N, затем по 46 чисел (запись 96 б, :65335): [0] id … [42] очки славы.
_bin = {}
SKILL_REC = 209


def _skill_dir_bytes(name, ttl=300):
    import time
    hit = _bin.get(name)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    b = hostshell.read_server_bytes(config.STACK_ROOT + r"\GameServer\SkillTable_Info" + "\\" + name)
    _bin[name] = (time.monotonic(), b)
    return b


def skill_info(idx):
    """Запись навыка → dict(tree, need, req[(skill, lvl)×3], zero{13 полей нулевого уровня}) или None."""
    import struct
    data = _skill_dir_bytes("SkillInfo.sif")
    i = int(idx)
    if i < 0 or (i + 1) * SKILL_REC > len(data):
        return None
    r = data[i * SKILL_REC:(i + 1) * SKILL_REC]
    i16 = lambda o: struct.unpack_from("<h", r, o)[0]
    i32 = lambda o: struct.unpack_from("<i", r, o)[0]
    # 18.11 (research_skills_pets.md A.2): +2 имя (cp949, «-» — заглушка), +42 вид, +43 максимальный уровень, +44 пассив (3/4),
    #   +123 u64 маска классов (бит = Job или Subjob), +151 u64 маска пассивных эффектов, +191/+194/+197 «следующие» навыки
    name = r[2:42].split(b"\x00", 1)[0].decode("cp949", "replace")
    return {"tree": r[189], "need": r[190], "name": name, "kind": r[42], "max": r[43], "passive": r[44],
            "mask": struct.unpack_from("<Q", r, 123)[0], "pmask": struct.unpack_from("<q", r, 151)[0],
            "next": [(i16(191), r[193]), (i16(194), r[196]), (i16(197), r[199])],
            "req": [(i16(200), r[202]), (i16(203), r[205]), (i16(206), r[208])],
            "zero": {"Cooltime": i32(47), "Distance": r[53], "Scope": r[55], "Mpvalue": i16(58), "Evalue": i16(62),
                     "SkillPer": r[66], "SubSkillPer": r[68], "SubValue1": i16(74), "SubTime1": i32(78), "SubValue2": i16(91),
                     "SubTime2": i32(95), "SubValue3": i16(108), "SubTime3": i32(112)}}


def change_job_rows():
    """{строка: [номера навыков]} из ChangeJobAddSkillTable.txt (как загрузчик :71620: строка 1…39, количество > 0)."""
    toks = [t for t in _skill_dir_bytes("ChangeJobAddSkillTable.txt").decode("latin-1").split()]
    out, i = {}, 0
    while i + 1 < len(toks):
        row, n = _atol(toks[i]), _atol(toks[i + 1])
        if row <= 0 or row > 39 or n <= 0:
            break
        out[row] = [_atol(x) for x in toks[i + 2:i + 2 + n]]
        i += 2 + n
    return out


def fame_points(fame_id):
    """Очки славы звания (FameInfo.txt, поле [42] записи); нет записи — None."""
    toks = _cfg_text("FameInfo.txt").split()
    n = _atol(toks[0]) if toks else 0
    for k in range(n):
        rec = toks[1 + 46 * k: 47 + 46 * k]
        if len(rec) == 46 and _atol(rec[0]) == int(fame_id):
            return _atol(rec[42])
    return None


# ---------------------------------------------------------------------------------------------------------------------
# СОЗДАНИЕ ПРЕДМЕТА (18.11.2026, выдача панелью — domains/itemgive.py; разбор Reports/admin_center/research_item_give.md):
#   Function_Table  t2 вес, t5 тип (15/65 — сроковые: срок идёт с первого использования), t9 заряды, t24 привязка, t25 дней срока
#                   (asda_give.item_spec, research_item_props §2).
#   SowelCombine    загрузчик GameServer.c:65161: t1 (+4), затем 10 пар «ступень (+8, char), вес (+20)», затем 10 пар
#                   «самоцвет (+60), вес (+100)», t42…, t44 (+146) MaxupCnt.
#   sub_4B7B00 (GameServer.c:73474) — только для типов 0–4, 8, 9: бросок 0…100000 (sub_5329A0), первый с накопленным весом ≥
#     броска → самоцвет в гнездо 0, если он «обычный» (Cellob +11 == 0) и подходит виду предмета (+12: 9 — оружие этого подтипа
#     по маске +34; 8 — щит; 0–4, 13, 14 — типы 0–4), вес предмета += вес самоцвета (Cellob +6); второй бросок — ступень 1…10.
#     Дефект оригинала: вес самоцвета прибавляется, даже если самоцвет не подошёл и в гнездо не встал — панель прибавляет вес
#     только вставленного (fix-original-defects).
#   Опции пар 1–2 (sub_5340B0 :117685): тип — sub_4A7EE0 (бросок 1…100000, первая строка группы с накопленным весом ≥ броска,
#     иначе −1), значение — sub_4A7FC0 (бросок 1…100000, первый порог ≥ броска у первой строки этого типа, иначе 0; у группы 0
#     значение всегда 0).
# ---------------------------------------------------------------------------------------------------------------------
ROLL_MAX = 100000


def function_rule(code):
    """Поля Function_Table для выдачи (None — кода нет)."""
    f = table("Function_Table.txt").get(int(code))
    if f is None:
        return None
    return {"weight": _i(f, 2), "type": _i(f, 5), "charges": _i(f, 9), "bind": _i(f, 24), "days": _i(f, 25)}


def table_max(name):
    """Наибольший код таблицы (диапазон кодов, как у sub_5340B0: 1…max Function, 7001…max Cellob, 20551…max Item)."""
    t = table(name)
    return max(t) if t else 0


def _schar(v):
    return ((int(v) & 0xFF) ^ 0x80) - 0x80


def creation_lists(code):
    """SowelCombine: ([(ступень, вес)] × 10, [(самоцвет, вес)] × 10) — как хранит сервер."""
    s = table("SowelCombine.txt").get(int(code)) or []
    ups = [(_schar(_i(s, 2 + 2 * j)), _i(s, 3 + 2 * j)) for j in range(10)]
    stones = [(_i(s, 22 + 2 * k), _i(s, 23 + 2 * k)) for k in range(10)]
    return ups, stones


def _pick_index(weights, r):
    """Индекс, который выбрал бы сервер при броске r (накопленный вес ≥ r), или None."""
    cum = 0
    for i, w in enumerate(weights):
        cum += w
        if cum >= r:
            return i
    return None


def _outcomes(weights):
    """Точные шансы исходов броска 0…100000 (включительно): {индекс | None: доля}."""
    total = ROLL_MAX + 1
    out, cum, lo = {}, 0, 0
    for i, w in enumerate(weights):
        cum += w
        hi = min(cum, ROLL_MAX)
        if hi >= lo:
            out[i] = out.get(i, 0) + (hi - lo + 1)
            lo = hi + 1
    if lo <= ROLL_MAX:
        out[None] = ROLL_MAX - lo + 1
    return {k: v / total for k, v in out.items()}


def stone_fits(item_code, stone):
    """Встал бы самоцвет stone в гнездо 0 при создании предмета (sub_4B7B00 :73529-73560)."""
    c = cellob(stone)
    r = item_rule(item_code)
    if not c or not r or not (CELLOB_BASE <= int(stone) <= table_max("Cellob_Table.txt")) or c["special"]:
        return False
    t = r["type"]
    if c["k1"] == 9:
        return t == 9 and bool((c["mask"] >> r["subtype"]) & 1) if r["subtype"] < 64 else False
    if c["k1"] == 8:
        return t == 8
    if c["k1"] in (0, 1, 2, 3, 4, 13, 14):
        return t <= 4
    return False


STONE_TYPES = {0, 1, 2, 3, 4, 8, 9}             # sub_4B7B00 бросает самоцвет и ступень только для этих типов


def creation_choices(code):
    """Исходы создания у сервера: {"stones": [(самоцвет | 0, шанс %)], "upcounts": [(ступень, шанс %)]} — только возможные
    (шанс > 0). Самоцвет 0 — гнездо пустое (бросок мимо или самоцвет не подошёл)."""
    r = item_rule(code)
    if not r or r["type"] not in STONE_TYPES:
        return {"stones": [(0, 100.0)], "upcounts": [(0, 100.0)]}
    ups, stones = creation_lists(code)
    st = {}
    for i, p in _outcomes([w for _c, w in stones]).items():
        s = stones[i][0] if i is not None else 0
        s = s if s and stone_fits(code, s) else 0
        st[s] = st.get(s, 0) + p
    up = {}
    for i, p in _outcomes([w for _v, w in ups]).items():
        v = ups[i][0] if i is not None else 0
        v = v if 0 < v <= 10 else 0
        up[v] = up.get(v, 0) + p
    rnd = lambda d: sorted(((k, round(v * 100, 3)) for k, v in d.items() if v > 0), key=lambda kv: -kv[1])
    return {"stones": rnd(st), "upcounts": rnd(up)}


def roll_creation(code, rng=None):
    """Бросок как у сервера при создании снаряжения: пары 1–2, самоцвет гнезда 0, ступень. → dict."""
    import random
    rng = rng or random.SystemRandom()
    groups = item_option_groups(code)
    pairs = {}
    for k in (1, 2):
        g = groups.get(k, 0)
        rows = option_groups().get(int(g), []) if g else []
        t = -1
        r = rng.randint(1, ROLL_MAX)
        for typ, w, _v, _p in rows:
            if w >= r:
                t = typ
                break
        v = 0
        if t != -1 and g >= 1:
            r = rng.randint(1, ROLL_MAX)
            for typ, _w, vals, thr in rows:
                if typ == t:
                    for val, th in zip(vals, thr):
                        if th >= r:
                            v = val
                            break
                    break
        pairs[k] = None if t == -1 else {"type": t, "value": v}
    stone, up = 0, 0
    rule = item_rule(code)
    if rule and rule["type"] in STONE_TYPES:
        ups, stones = creation_lists(code)
        i = _pick_index([w for _c, w in stones], rng.randint(0, ROLL_MAX))
        if i is not None and stones[i][0] and stone_fits(code, stones[i][0]):
            stone = stones[i][0]
        i = _pick_index([w for _v, w in ups], rng.randint(0, ROLL_MAX))
        if i is not None and 0 < ups[i][0] <= 10:
            up = ups[i][0]
    return {"pairs": pairs, "stone": stone, "upcount": up}


def charge_cap():
    """Потолок зарядов P100 (patches.ini [P100_ChargeStack] Cap, не выше 30 000) или None — P100 не действует."""
    ini = patches_ini()
    if not patch_on("P100_ChargeStack", ini):
        return None
    try:
        cap = int(ini.get("P100_ChargeStack", {}).get("cap", "30000"))
    except ValueError:
        cap = 30000
    return max(1, min(cap, 30000))


# ---------------------------------------------------------------------------------------------------------------------
# ФАЙЛЫ СТОЙКИ ДЛЯ ПОДАРКОВ (18.11.2026, domains/gifts.py — перенос вкладки «Подарки» AstoryAdminCenter/tools/Admin/asda_gifts.py):
#   ItemTable_Info\SellItemTable.txt (белый список покупки 5070), PackageItem_Table.txt (состав коробок),
#   gp7-server\premium_item_map.json (карта шлюза), patches.ini КАЖДОГО GS (P98/P100 ставятся на все три).
# ---------------------------------------------------------------------------------------------------------------------
STACK_GS = ("GameServer", "Indun_GameServer", "Ch2_GameServer")
_stack = {}


def stack_text(rel, ttl=60):
    """Текст файла стойки (путь от корня v2), кэш ttl с."""
    import time
    hit = _stack.get(rel)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    txt = hostshell.read_server_file(config.STACK_ROOT + "\\" + rel)
    _stack[rel] = (time.monotonic(), txt)
    return txt


def patch_on_all(section):
    """{GS: патч действует} по patches.ini всех трёх GS стойки."""
    out = {}
    for gs in STACK_GS:
        ini, sec = {}, None
        for ln in stack_text(gs + r"\ConfigSet\patches.ini").splitlines():
            t = ln.strip()
            if not t or t.startswith(";"):
                continue
            if t.startswith("[") and t.endswith("]"):
                sec = t[1:-1].strip()
                ini.setdefault(sec, {})
            elif sec and "=" in t:
                k, v = [x.strip() for x in t.split("=", 1)]
                ini[sec][k.lower()] = v
        out[gs] = patch_on(section, ini)
    return out


# ★ ревизия 38 М-1 (20.11.2026): у званий P88 цель (FameInfo кол. 3) задаёт patches.ini — p88_title_events.cpp g_goals (:125–131) и
#   ApplyGoals (:281–299): при первом событии P88 после старта пишет Threshold<id> в FameInfo[id].+4 в памяти, вызывается из Count() —
#   то есть только когда стоит хоть одна площадка события. Чтение ключей — как GetPrivateProfileIntW (Config::GetInt, Config.cpp:3308):
#   первая секция и первый ключ, ведущие цифры, нет ключа — значение по умолчанию; Threshold вне 1…1000000 — по умолчанию (:667).
P88_SEC = "P88_TitleEvents"
P88_GOALS = {190: 10, 192: 300, 199: 100, 200: 100, 201: 200, 202: 50, 203: 100, 205: 500}      # g_goals: звание → порог по умолчанию
P88_SITES = ("WarKill", "SkillReset", "WarehouseMax", "Craft", "Dig", "PetLevel", "Pickup")      # площадки событий (Enabled каждой — 1)


def _ini_first(text):
    """{секция (нижний регистр): {ключ (нижний регистр): значение}} — первая секция и первый ключ, как GetPrivateProfile*."""
    ini, sec = {}, None
    for ln in text.splitlines():
        t = ln.strip()
        if not t or t.startswith(";"):
            continue
        if t.startswith("[") and t.endswith("]"):
            name = t[1:-1].strip().lower()
            sec = None if name in ini else ini.setdefault(name, {})
        elif sec is not None and "=" in t:
            k, v = [x.strip() for x in t.split("=", 1)]
            sec.setdefault(k.lower(), v)
    return ini


def _ini_int(sec, key, default):
    """GetPrivateProfileIntW: нет ключа — default; иначе ведущее десятичное (не число — 0, отрицательное — 0)."""
    import re as _re
    v = (sec or {}).get(key.lower())
    if v is None:
        return default
    m = _re.match(r"\s*(-?)(\d+)", v)
    if not m:
        return 0
    return 0 if m.group(1) else int(m.group(2))


def p88_goals_all(ttl=60):
    """{GS: {"on": P88 ставится и хоть одна площадка события включена, "thr": {звание: порог из ini}}} по patches.ini всех GS стойки.
    Файл не прочитан — исключение (вызывающий отказывает «не прочитан»)."""
    out = {}
    for gs in STACK_GS:
        ini = _ini_first(stack_text(gs + r"\ConfigSet\patches.ini", ttl=ttl))
        if not ini:
            raise ValueError("%s\\ConfigSet\\patches.ini: секций нет" % gs)
        sec = ini.get(P88_SEC.lower())
        on = (_ini_int(ini.get("general"), "MasterEnable", 0) != 0 and _ini_int(sec, "Enabled", 1) != 0
              and any(_ini_int(sec, k, 1) != 0 for k in P88_SITES))
        thr = {}
        for tid, d in P88_GOALS.items():
            v = _ini_int(sec, "Threshold%d" % tid, d)
            thr[tid] = v if 1 <= v <= 1000000 else d
        out[gs] = {"on": on, "thr": thr}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# ЗВАНИЯ (18.11.2026, domains/titles.py; разбор Reports/admin_center/research_titles_honor.md): GameServer\ConfigSet\FameInfo.txt
#   (загрузчик GameServer.c:65335): N, затем по 46 чисел на запись; id = позиция. Столбцы (с 0): 0 id, 1 включено, 3 цель
#   Condition1, 4 параметр, 5…9 предпосылки набора, 10/11 «следующие», 12+5m код бонуса m (−1 нет) и min/max двух значений,
#   42 очки славы, 43/44 вид и порог второй ступени (бит «найдено»), 45 общий накопитель.
# ---------------------------------------------------------------------------------------------------------------------
def fame_info():
    """[46 чисел] по id звания."""
    toks = _cfg_text("FameInfo.txt").split()
    n, out = _atol(toks[0]), []
    for i in range(n):
        rec = toks[1 + 46 * i: 47 + 46 * i]
        if len(rec) < 46:
            break
        out.append([_atol(x) for x in rec])
    return out


def skill_count():
    """Записей в SkillInfo.sif (допустимые навыки — 500 ≤ id < числа; гейты sub_475290 / Recv_SkillPoint_SkillActive)."""
    return len(_skill_dir_bytes("SkillInfo.sif")) // SKILL_REC


def passive_skills():
    """Навыки, участвующие в PassiveSkillEffectTable.txt (источник и цели бонусов) — их уровень панель не меняет (пассивы не перенесены)."""
    # строка (загрузчик GameServer.c:71759): навык, затем до 15 пассивов, которые меняют его поля (−1 — нет)
    out = set()
    for ln in _skill_dir_bytes("PassiveSkillEffectTable.txt").decode("latin-1").splitlines()[1:]:
        t = [_atol(x) for x in ln.split()]
        ps = [x for x in t[1:16] if x >= 0]
        if t and ps:
            out.add(t[0])
            out.update(ps)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# ПИТОМЦЫ (18.11.2026, domains/pets.py; research_skills_pets.md C): GameServer\PetData_Info\PetInfo_Table.txt (загрузчик
#   GameServer.c:69613: N, затем записи «порода кличка …»; кол. 1 — кличка по умолчанию, кол. 4 — PetMaxLvl при вылуплении,
#   кол. 5 — множитель опыта) и PetExp_Table.txt (:69679: N, затем «уровень опыт …»). Порог уровня L: E(L) = int(опыт[L] × множ / 10).
# ---------------------------------------------------------------------------------------------------------------------
def _pet_text(name):
    return stack_text(r"GameServer\PetData_Info" + "\\" + name, ttl=300)


def pet_info():
    """{порода: dict(name, maxlvl, mult)}."""
    lines = _pet_text("PetInfo_Table.txt").splitlines()
    out = {}
    for ln in lines[1:]:
        t = ln.split()
        if len(t) >= 6 and t[0].lstrip("-").isdigit():
            out[int(t[0])] = {"name": t[1], "maxlvl": _atol(t[4]), "mult": _atol(t[5])}
    return out


def pet_exp_table():
    """{уровень: опыт начала уровня (кол. 1)}."""
    out = {}
    for ln in _pet_text("PetExp_Table.txt").splitlines()[1:]:
        t = ln.split()
        if len(t) >= 2 and t[0].isdigit():
            out[int(t[0])] = _atol(t[1])
    return out


def pet_level_exp(breed, lvl):
    """E(L) — опыт начала уровня L для породы (sub_456D90 :35255)."""
    pi, et = pet_info().get(int(breed)), pet_exp_table()
    if not pi or int(lvl) not in et:
        return None
    return int(et[int(lvl)] * pi["mult"] / 10.0)
