# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""asda_give.py — выдача золота и предметов персонажам прямой правкой dev-БД (Joy1). 19.10.2026.

Часть утилиты учёток (asda_accounts.py: вкладка «Выдача» и консольные команды give-gold / give-item).

ЧТО УМЕЕТ
  * золото — отдельной кнопкой: к текущему золоту персонажа ПРИБАВЛЯЕТСЯ указанное;
  * предмет по коду и количеству: стопочный — прибавляется к уже лежащей стопке того же кода (или новая стопка),
    нестопочный — по ячейке на штуку;
  * получатель: персонаж по имени / все персонажи учётки по логину / все персонажи всех учёток (кроме служебных,
    Userindex <= 5000 — операторы ADM_*/GM, как стоковая админка);
  * предпросмотр без записи: кому выдастся, кто будет пропущен и почему.

КАК ПИШЕТ (стоковые процедуры наград, тот же путь, что у сервера)
  золото   — Joy1.dbo.UPRewardGM  @Seridx 0, @Userindex, @Charidx, @Code 0, @Episodeidx 0, @Stepidx 0, @Gm
             (Amount = Amount + @Gm у строки кода 20551; журнал JoyLog1.dbo.MoneyReward «было/стало»);
  предметы — Joy1.dbo.UPRewardItem @Code 0, @Episodeidx 0, @Stepidx 0, @Code1 … @Owner
             (та же ячейка с тем же кодом → Amount/Weight прибавляются, иначе новая строка; журнал JoyLog1 Reward*).
  @Code 0 = несуществующий эпизод: процедуры сначала двигают шаг эпизода в CharEpisode — строк с Code 0 там нет,
  поэтому квесты не задеваются (кодов эпизодов 2003…2435, проверено 19.10).

ПРАВИЛА ПРЕДМЕТА — по живым таблицам сервера (GameServer\\ItemTable_Info), как серверная sub_5340B0:
  разбор и доказательства — Reports/admin_items/research_item_props.md (§2–§7).
  1…558 Function_Table → сумка 1, по ячейке на штуку, Amount = заряды (поле 9), вес поле 2, прочность 0;
  7001… Cellob_Table (самоцветы) → сумка 2, Amount 0, вес поле 3, прочность поле 4, Owner поле 17;
  20551… Item_Table → сумка 1, если поле 24 == 3 или тип (поле 16) ∈ {0–4, 8, 9, 12–15} (Amount 0, вес поле 2,
  прочность поле 1, MaxupCnt — SowelCombine поле 44); иначе сумка 2: тип 10 (колчаны/наживка/заряды) — Amount = поле 29,
  стопка по флагу поля 23 (Amount = количество, Weight = количество × вес), прочее — Amount 0.
  Ячейки: сумка 1 — 0…59 (★ 30.10.2026 «инвентарь ×2»; до выкладки P96 на стойке — 0…29, см. _plate_cells), сумка 2 — 0…59;
  стопка — первая ячейка с тем же кодом, иначе первая свободная. MaxWeight читается как u16 (вес ×2: значения до 65535
  хранятся в smallint битовым образом, 37500 лежит как −28036).

БЕЗОПАСНОСТЬ (разбор — Reports/admin_items/research_online_persist.md)
  * ★ 19.10.2026 (решение владельца): флаг «в игре» НЕ проверяется — выдача всем найденным персонажам. Вместо проверки —
    предупреждение «Убедитесь, что сервер выключен» (окно подтверждения, консоль). Причина: при остановке сервера флаги
    Us_member.Flag / CharPos.UserNum не снимаются (их снимает выход игрока или старт GameServer), и проверка ложно
    отказывала. Выдавать при ЗАПУЩЕННОМ сервере нельзя: GameServer держит инвентарь в памяти, правка «под ним» даёт
    потерю/дюп (разбор — research_online_persist.md).
  * Переполнение: золото не выше 2 147 483 647 (INT); вес строки не выше 32 767 (SMALLINT); вес персонажа (без склада)
    не выше MaxWeight; нехватка ячеек — пропуск. Надетое (3), квестовая книга (4), склад (5), замок аукциона (11/12)
    не пишутся.
  * Каждый персонаж — своя транзакция; после записи — сверка в той же транзакции (золото = было + выдано, предметы на
    месте), иначе откат.
Журнал действий — logs/accounts.log (через asda_accounts._log). Побочных эффектов при импорте нет.
"""
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN_ROOT = os.path.dirname(os.path.dirname(HERE))   # ★ 25.11 (С-2): tools/Admin → AstoryAdminCenter (корень клона)
PORT = os.path.dirname(ADMIN_ROOT)                    # папка с клонами AstoryClient / AstoryServer / AstoryAdminCenter
# Живые таблицы предметов сервера (авторитет — сервер; локальные копии в Server\Docs уже расходятся с живыми).
# ★ 01.11.2026: читаются ТОЛЬКО по SSH (scp в кэш утилиты): шара \\@@ASTORY_SERVER_HOSTNAME@@ висит без таймаута (правило владельца 22.10).
#   Каждый файл копируется с сервера один раз за запуск утилиты; сервер недоступен — берётся прошлая копия из кэша
#   (с предупреждением в SRV_WARN), копии нет — отказ.
SRV_HOST = "Administrator@@@ASTORY_SERVER_VPN_IP@@"                                   # dev-сервер (Tailscale), только SSH
SRV_KEY = os.path.join(os.environ.get("USERPROFILE", ""), ".ssh", "@@ASTORY_SSH_KEY_NAME@@")   # ключ SSH
SRV_ROOT = "@@ASTORY_SERVER_ROOT_FWD@@/Working_ASDA/v2"                                         # корень стойки на сервере
SRV_TABLES = "GameServer/ItemTable_Info"                                     # живые таблицы предметов (от корня стойки)
SRV_CACHE = os.path.join(HERE, "data", "srv_cache")                          # локальные копии файлов сервера
SRV_TIMEOUT_S = 120                                                          # предел одного scp (SowelCombine ~10 МБ)
_SRV_FETCHED = {}   # относительный путь → локальный путь (скопировано в этом запуске)
# ★ 02.11.2026 (ревизия п.3): потоки окна (выбор позиции, «Подарить») копировали один файл одновременно в общий «.part» —
#   ложная ошибка «файл занят» или ложное «сервер недоступен». Теперь копирование и чтение копий — под одним замком,
#   временный файл уникален на вызов.
SRV_LOCK = threading.RLock()
SRV_WARN = []       # предупреждения «сервер недоступен, взята прошлая копия» (показываются в окне/консоли)
# Названия предметов для показа (клиентские таблицы порта).
NAMES_DIR = os.path.join(PORT, "AstoryClient", "RawAssets", "Data", "ItemDB")

GOLD_CODE = 20551                 # золото — предмет в сумке 2, одна строка на персонажа
INT_MAX = 2147483647              # предел Item.Amount (INT)
WEIGHT_MAX = 32767                # предел Item.Weight (SMALLINT)
OPERATOR_MAX_UID = 5000           # Userindex 0…5000 — служебные учётки операторов (гейт sub_52ECF0 сервера)
PLATE_CELLS = {1: 60, 2: 60}      # ёмкость сумок: 1 — снаряжение, 2 — расходники/аксессуары (★ 30.10: сумка 1 30 → 60)
PLATE1_CELLS_OLD = 30             # сумка 1 до выкладки P96 (старые DBManager/GameServer срезают ячейки 30..59 при входе)
BAG60_MIGKEY = "inventory_x2_weight"   # метка Joy1.dbo.AsdaMigrationLog: волна «инвентарь ×2» выложена (тем же окном, что P96)
PLATE1_TYPES = {0, 1, 2, 3, 4, 8, 9, 12, 13, 14, 15}   # itemType (Item_Table поле 16) → сумка 1
QUIVER_TYPE = 10                  # колчаны/наживка/заряды: Amount = ёмкость (поле 29), вес не умножается
TIMED_FUNCTIONS = {15, 65}
# Предупреждение вместо проверки «в игре» (решение владельца 19.10.2026): писать в инвентарь можно только при выключенном
#   сервере — GameServer держит инвентарь в памяти.
SERVER_OFF_WARNING = "Убедитесь, что сервер выключен."        # Function: срочные (маунты «(7 дн.)», «Реклама магазина») — срок с первого использования


class GiveError(Exception):
    """Отказ операции выдачи с понятной причиной."""


# ═════════════════════════════ таблицы предметов ═════════════════════════════

_TABLES = {}   # имя → {код: [поля]} (кэш на процесс)
_NAMES = None  # код → название


def srv_file(rel, refresh=False):
    """Локальная копия файла стойки (путь от корня стойки, через «/»): scp с сервера один раз за запуск
    (refresh=True — заново). Сервер недоступен — прошлая копия из кэша + запись в SRV_WARN; копии нет — GiveError.
    Потокобезопасно (SRV_LOCK), временный файл уникален на вызов."""
    with SRV_LOCK:
        if rel in _SRV_FETCHED and not refresh:
            return _SRV_FETCHED[rel]
        return _srv_fetch(rel)


def _srv_fetch(rel):
    """Копирование файла стойки по scp в кэш (вызывать под SRV_LOCK)."""
    import subprocess
    import tempfile
    local = os.path.join(SRV_CACHE, rel.replace("/", "__"))
    os.makedirs(SRV_CACHE, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(local) + ".", suffix=".part", dir=SRV_CACHE)
    os.close(fd)
    scp = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
    if not os.path.exists(scp):
        scp = "scp"
    err = ""
    try:
        r = subprocess.run([scp, "-q", "-i", SRV_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                            "%s:%s/%s" % (SRV_HOST, SRV_ROOT, rel), tmp],
                           capture_output=True, timeout=SRV_TIMEOUT_S, creationflags=0x08000000)   # без окна консоли
        if r.returncode == 0 and os.path.getsize(tmp) > 0:
            os.replace(tmp, local)
            _SRV_FETCHED[rel] = local
            return local
        err = (r.stderr or b"").decode("utf-8", "replace").strip() or "код %d" % r.returncode
    except (OSError, subprocess.TimeoutExpired) as ex:
        err = str(ex)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    if os.path.exists(local):
        import datetime
        when = datetime.datetime.fromtimestamp(os.path.getmtime(local)).strftime("%Y-%m-%d %H:%M")
        SRV_WARN.append("сервер недоступен (%s) — %s взят из копии от %s" % (err, rel, when))
        _SRV_FETCHED[rel] = local
        return local
    raise GiveError("файл сервера %s не получен по SSH (%s), прошлой копии нет" % (rel, err))


def srv_reset():
    """Забыть скопированные в этом запуске файлы и разобранные таблицы (следующее чтение — заново с сервера)."""
    with SRV_LOCK:
        _SRV_FETCHED.clear()
        _TABLES.clear()
        del SRV_WARN[:]


def _read_table(name):
    """Таблица сервера: первая строка — число записей, далее поля через TAB, поле 0 — код. Под SRV_LOCK."""
    with SRV_LOCK:
        return _read_table_locked(name)


def _read_table_locked(name):
    """Тело _read_table (вызывать под SRV_LOCK)."""
    if name in _TABLES:
        return _TABLES[name]
    path = srv_file(SRV_TABLES + "/" + name)
    try:
        raw = open(path, "rb").read().decode("cp1251", errors="replace")
    except OSError as ex:
        raise GiveError("нет доступа к копии таблицы сервера %s: %s" % (path, ex))
    lines = raw.splitlines()
    rows = {}
    for ln in lines[1:]:
        f = [t.strip() for t in ln.split("\t")]
        if f and f[0].lstrip("-").isdigit():
            rows[int(f[0])] = f
    if not rows:
        raise GiveError("таблица сервера %s пуста или не разобрана" % path)
    _TABLES[name] = rows
    return rows


def _int(f, i):
    """Поле i как целое (нет поля / не число — 0)."""
    try:
        return int(f[i])
    except (IndexError, ValueError):
        return 0


def item_name(code):
    """Название предмета из клиентских таблиц (первое осмысленное), иначе пусто."""
    global _NAMES
    if _NAMES is None:
        import csv
        names = {}
        for fname, kcol, ncol in (("special_itemlist.csv", "Code", "Name"), ("sowell_list.csv", "Id", "Name"),
                                  ("item_list.csv", "ItemCode", "ItemName")):
            try:
                with open(os.path.join(NAMES_DIR, fname), encoding="utf-8-sig", newline="") as fh:
                    for r in csv.DictReader(fh):
                        k, n = (r.get(kcol) or "").strip(), (r.get(ncol) or "").strip()
                        if k.isdigit() and n and n not in ("-", "Нет") and int(k) not in names:
                            names[int(k)] = n
            except OSError:
                pass
        _NAMES = names
    return _NAMES.get(code, "")


def find_items(text, limit=60):
    """Поиск по части названия или коду: [(код, название)] (не больше limit)."""
    item_name(0)
    t = (text or "").strip().lower()
    if not t:
        return []
    out = [(k, v) for k, v in _NAMES.items() if t in v.lower() or t == str(k)]
    out.sort()
    return out[:limit]


def item_spec(code):
    """Правило выдачи кода (как серверная sub_5340B0): dict(kind, plate, stack, amount_each, unit_weight, dur, maxup,
    owner, name, note). Код вне таблиц сервера / особые — GiveError."""
    if code == GOLD_CODE:
        raise GiveError("золото выдаётся отдельной кнопкой «Выдать золото»")
    fn, ce, it = _read_table("Function_Table.txt"), _read_table("Cellob_Table.txt"), _read_table("Item_Table.txt")
    name = item_name(code)
    if 1 <= code <= max(fn):
        f = fn.get(code)
        if not f:
            raise GiveError("кода %d нет в Function_Table сервера" % code)
        ftype = _int(f, 5)
        return dict(kind="function", plate=1, stack=False, amount_each=_int(f, 9), unit_weight=_int(f, 2), dur=0,
                    maxup=0, owner=0, name=name,
                    note="срочный: срок пойдёт с первого использования" if ftype in TIMED_FUNCTIONS else "")
    if 7001 <= code <= max(ce):
        f = ce.get(code)
        if not f:
            raise GiveError("кода %d нет в Cellob_Table сервера" % code)
        return dict(kind="cellob", plate=2, stack=False, amount_each=0, unit_weight=_int(f, 3), dur=_int(f, 4),
                    maxup=0, owner=_int(f, 17), name=name, note="")
    if 20551 <= code <= max(it):
        f = it.get(code)
        if not f:
            raise GiveError("кода %d нет в Item_Table сервера" % code)
        itype = _int(f, 16)
        if _int(f, 24) == 3 or itype in PLATE1_TYPES:
            sc = _read_table("SowelCombine.txt").get(code, [])
            return dict(kind="gear", plate=1, stack=False, amount_each=0, unit_weight=_int(f, 2), dur=_int(f, 1),
                        maxup=_int(sc, 44), owner=0, name=name, note="")
        if itype == QUIVER_TYPE:
            return dict(kind="quiver", plate=2, stack=False, amount_each=_int(f, 29), unit_weight=_int(f, 2),
                        dur=_int(f, 1), maxup=0, owner=0, name=name, note="")
        stack = _int(f, 23) != 0
        return dict(kind="stack" if stack else "single", plate=2, stack=stack, amount_each=0, unit_weight=_int(f, 2),
                    dur=_int(f, 1), maxup=0, owner=0, name=name, note="")
    raise GiveError("код %d не существует на сервере (вне Function / Cellob / Item_Table)" % code)


def describe_spec(code):
    """Строка-описание кода для окна: название, сумка, стопка."""
    s = item_spec(code)
    plate = "снаряжение (сумка 1)" if s["plate"] == 1 else "расходники (сумка 2)"
    how = "стопка" if s["stack"] else "по ячейке на штуку"
    return "%s — %s, %s, вес %d%s" % (s["name"] or "без названия", plate, how, s["unit_weight"],
                                      ("; " + s["note"]) if s["note"] else "")


# ═════════════════════════════ получатели ═════════════════════════════

def resolve_targets(cn, mode, value):
    """Персонажи-получатели: [dict(uid, cidx, name, login)].
    mode: 'char' — персонаж по имени; 'login' — все персонажи учётки; 'all' — все персонажи всех учёток (кроме служебных)."""
    cur = cn.cursor()
    base = ("SELECT c.Userindex, c.Charidx, c.Charname, m.us_id FROM dbo.Charinfo c "
            "JOIN AsdaStoryOP.dbo.Us_member m ON m.Userindex = c.Userindex ")
    if mode == "char":
        name = (value or "").strip()
        if not name:
            raise GiveError("укажите имя персонажа")
        cur.execute(base + "WHERE c.Charname = ?", name)
    elif mode == "login":
        login = (value or "").rstrip(" ")
        if not login:
            raise GiveError("укажите логин учётки")
        cur.execute(base + "WHERE m.us_id = ? ORDER BY c.Charidx", login)
    elif mode == "all":
        cur.execute(base + "WHERE c.Userindex > ? ORDER BY c.Userindex, c.Charidx", OPERATOR_MAX_UID)
    else:
        raise GiveError("неизвестный режим получателя: %s" % mode)
    out = [dict(uid=int(r[0]), cidx=int(r[1]), name=str(r[2]).rstrip(), login=str(r[3]).rstrip()) for r in cur.fetchall()]
    if not out:
        raise GiveError({"char": "персонаж не найден: %s", "login": "у учётки нет персонажей (или учётки нет): %s",
                         "all": "нет ни одного персонажа игроков%s"}[mode] % (value or ""))
    return out


# ★ 02.11.2026 (ревизия п.4): забаненные владельцем учётки (бан = смена пароля, us_block 0 — SQL их не отличит).
#   Источник — реестр AstoryAdminCenter/DiscordBot/BANNED_PLAYERS.md (таблицы со столбцами «Игровой логин» и «Userindex»).
BANNED_REGISTRY = os.path.join(ADMIN_ROOT, "DiscordBot", "BANNED_PLAYERS.md")   # ★ 25.11 (М-2): от корня клона, не по имени папки


def banned_accounts(path=None):
    """{Userindex: логин} из реестра банов (строки markdown-таблиц). Нет файла — GiveError (без реестра «всем» не выдаём)."""
    path = path or BANNED_REGISTRY
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as ex:
        raise GiveError("нет реестра банов %s: %s" % (path, ex))
    out, cols = {}, None
    for ln in lines:
        if not ln.strip().startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if "Userindex" in cells and "Игровой логин" in cells:
            cols = (cells.index("Userindex"), cells.index("Игровой логин"))
        elif cols and cells[cols[0]].isdigit():
            out[int(cells[cols[0]])] = cells[cols[1]]
    return out


def split_banned(targets, mode):
    """(кому выдавать, строки отчёта). Режим 'all' — забаненные исключаются; 'char'/'login' — выдаётся явно выбранному,
    но с предупреждением в отчёте."""
    ban = banned_accounts()
    hit = [t for t in targets if t["uid"] in ban]
    if mode == "all":
        keep = [t for t in targets if t["uid"] not in ban]
        lines = ["⊘ исключён (реестр банов BANNED_PLAYERS.md): %s (учётка %s, ID %d/%d)" % (
            t["name"], t["login"], t["uid"], t["cidx"]) for t in hit]
        return keep, lines
    return targets, ["⚠ учётка в реестре банов BANNED_PLAYERS.md, выдача по явному выбору: %s (учётка %s)" % (
        t["name"], t["login"]) for t in hit]


# ═════════════════════════════ план выдачи ═════════════════════════════

def _plate_cells(cur, plate):
    """Ёмкость сумки на стойке: сумка 1 — 60, только если волна «инвентарь ×2» выложена (метка BAG60_MIGKEY в
    Joy1.dbo.AsdaMigrationLog; SQL-миграция, DBPatch и AsdaPatch P96 ставятся одним окном — PLAN §5), иначе 30: старый DBManager
    при входе срезал бы ячейки 30..59, GameServer счёл бы их пустыми, а вставка в них упала бы на PK."""
    if plate != 1:
        return PLATE_CELLS[plate]
    cur.execute("SET NOCOUNT ON; DECLARE @n INT = 0; IF OBJECT_ID('dbo.AsdaMigrationLog', 'U') IS NOT NULL "
                "SELECT @n = COUNT(*) FROM dbo.AsdaMigrationLog WHERE MigKey = ?; SELECT @n", BAG60_MIGKEY)
    return PLATE_CELLS[1] if int(cur.fetchone()[0] or 0) > 0 else PLATE1_CELLS_OLD


def _plan_item(cur, t, code, qty, spec):
    """Раскладка предмета для персонажа: [(posx, amount, weight)] + прибавка веса. Отказ — GiveError."""
    plate = spec["plate"]
    cur.execute("SELECT Posx, Code, Amount, Weight FROM dbo.Item WITH (UPDLOCK, HOLDLOCK) "
                "WHERE Userindex = ? AND Charidx = ? AND Plate = ? ORDER BY Posx", t["uid"], t["cidx"], plate)
    used = cur.fetchall()
    taken = {int(r[0]) for r in used}
    free = [p for p in range(_plate_cells(cur, plate)) if p not in taken]
    if spec["stack"]:
        add_w = qty * spec["unit_weight"]
        if add_w > WEIGHT_MAX:
            raise GiveError("стопка тяжелее %d (вес %d × %d)" % (WEIGHT_MAX, spec["unit_weight"], qty))
        same = [r for r in used if int(r[1]) == code]
        if same:
            r = same[0]                                   # первая ячейка с тем же кодом — как сервер (sub_4D6CE0)
            if int(r[2]) + qty > INT_MAX or int(r[3]) + add_w > WEIGHT_MAX:
                raise GiveError("стопка в ячейке %d переполнится" % int(r[0]))
            plan = [(int(r[0]), qty, add_w)]
        elif free:
            plan = [(free[0], qty, add_w)]
        else:
            raise GiveError("сумка %d полна" % plate)
    else:
        if len(free) < qty:
            raise GiveError("в сумке %d свободно %d ячеек, нужно %d" % (plate, len(free), qty))
        plan = [(p, spec["amount_each"], spec["unit_weight"]) for p in free[:qty]]
        add_w = qty * spec["unit_weight"]
    cur.execute("SELECT ISNULL(SUM(CAST(Weight AS INT)), 0) FROM dbo.Item WITH (UPDLOCK, HOLDLOCK) "
                "WHERE Userindex = ? AND Charidx = ? AND Plate <> 5", t["uid"], t["cidx"])
    cur_w = int(cur.fetchone()[0])
    cur.execute("SELECT MaxWeight FROM dbo.Charinfo WHERE Userindex = ? AND Charidx = ?", t["uid"], t["cidx"])
    max_w = int(cur.fetchone()[0] or 0) & 0xFFFF   # u16 побитно в smallint (вес ×2: 37500…64000 лежат отрицательными)
    if cur_w + add_w >= max_w:
        raise GiveError("перегруз: вес %d + %d ≥ предела %d" % (cur_w, add_w, max_w))
    return plan


def _flag(cur):
    """Флаг ответа процедуры наград (последний набор строк)."""
    val = None
    while True:
        if cur.description:
            rows = cur.fetchall()
            if rows:
                val = rows[-1][0]
        if not cur.nextset():
            break
    return None if val is None else int(val)


def _give_one(cn, t, what, code, qty, dry, commit=True):
    """Выдача одному персонажу в своей транзакции. → (ok, текст). Пропуск/отказ — ok=False с причиной.
    commit=False — самотест: запись и сверка выполняются по-настоящему, затем откат (в БД не остаётся ничего)."""
    cur = cn.cursor()
    cn.autocommit = False
    try:
        if what == "gold":
            cur.execute("SELECT COUNT(*), MAX(Amount) FROM dbo.Item WITH (UPDLOCK, HOLDLOCK) "
                        "WHERE Userindex = ? AND Charidx = ? AND Plate = 2 AND Code = ?", t["uid"], t["cidx"], GOLD_CODE)
            n, before = cur.fetchone()
            if int(n) != 1:
                cn.rollback()
                return False, "строк золота %d (ожидалась одна)" % int(n)
            before = int(before)
            if before + qty > INT_MAX:
                cn.rollback()
                return False, "золото переполнится: %d + %d > %d" % (before, qty, INT_MAX)
            if dry:
                cn.rollback()
                return True, "золото %d → %d" % (before, before + qty)
            cur.execute("SET NOCOUNT ON; EXEC dbo.UPRewardGM @Seridx = 0, @Userindex = ?, @Charidx = ?, @Code = 0, "
                        "@Episodeidx = 0, @Stepidx = 0, @Gm = ?", t["uid"], t["cidx"], qty)
            fl = _flag(cur)
            cur.execute("SELECT Amount FROM dbo.Item WHERE Userindex = ? AND Charidx = ? AND Plate = 2 AND Code = ?",
                        t["uid"], t["cidx"], GOLD_CODE)
            after = int(cur.fetchone()[0])
            if fl != 1 or after != before + qty:
                cn.rollback()
                return False, "процедура ответила %s, золото %d (ожидалось %d) — откат" % (fl, after, before + qty)
            cn.commit() if commit else cn.rollback()
            return True, "золото %d → %d" % (before, after)

        if what == "honor":
            # ★ 19.10.2026: очки чести (Honor point, loc 10082/10127) = Joy1.dbo.CharFameBank.Fmpoint — по нему рейтинг
            #   «Honor point ranking» (UPTopFamePoint). Сервер держит значение в памяти и пишет АБСОЛЮТНО (UPCharFamePointUP
            #   SET Fmpoint=@Fmpoint) — поэтому тоже только при выключенном сервере. Пишем той же стоковой процедурой.
            cur.execute("SELECT Fmpoint FROM dbo.CharFameBank WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ?",
                        t["uid"], t["cidx"])
            r = cur.fetchone()
            before = int(r[0] or 0) if r else 0
            if before + qty > INT_MAX:
                cn.rollback()
                return False, "очки чести переполнятся: %d + %d > %d" % (before, qty, INT_MAX)
            if dry:
                cn.rollback()
                return True, "очки чести %d → %d%s" % (before, before + qty, "" if r else " (строка будет создана)")
            # Дефект стока: при отсутствии строки процедура вставляет 0 и переданное значение не пишет — тогда второй вызов.
            for _ in range(1 if r else 2):
                cur.execute("SET NOCOUNT ON; EXEC dbo.UPCharFamePointUP @Userindex = ?, @Charidx = ?, @Fmpoint = ?",
                            t["uid"], t["cidx"], before + qty)
                fl = _flag(cur)
            cur.execute("SELECT Fmpoint FROM dbo.CharFameBank WHERE Userindex = ? AND Charidx = ?", t["uid"], t["cidx"])
            r2 = cur.fetchone()
            after = int(r2[0]) if r2 else None
            if fl != 1 or after != before + qty:
                cn.rollback()
                return False, "процедура ответила %s, очки чести %s (ожидалось %d) — откат" % (fl, after, before + qty)
            cn.commit() if commit else cn.rollback()
            return True, "очки чести %d → %d" % (before, after)

        spec = item_spec(code)
        try:
            plan = _plan_item(cur, t, code, qty, spec)
        except GiveError as ex:
            cn.rollback()
            return False, str(ex)
        cells = ", ".join(str(p[0]) for p in plan)
        if dry:
            cn.rollback()
            return True, "сумка %d, ячейки %s" % (spec["plate"], cells)
        for posx, amount, weight in plan:
            cur.execute("SELECT Amount FROM dbo.Item WHERE Userindex = ? AND Charidx = ? AND Plate = ? AND Posx = ? "
                        "AND Code = ?", t["uid"], t["cidx"], spec["plate"], posx, code)
            r = cur.fetchone()
            before = int(r[0]) if r else None
            cur.execute("SET NOCOUNT ON; EXEC dbo.UPRewardItem @Userindex = ?, @Charidx = ?, @Code = 0, @Episodeidx = 0, "
                        "@Stepidx = 0, @Code1 = ?, @Plate = ?, @Posx = ?, @Amount = ?, @Durability = ?, @Weight = ?, "
                        "@Cell1 = 0, @Cell2 = 0, @Cell3 = 0, @Cell4 = 0, @Upcount = 0, @MaxUPCnt = ?, @AcuUpcnt = 0, "
                        "@UpDamage = 0, @Opidx1 = -1, @OpValue1 = 0, @Opidx2 = -1, @OpValue2 = 0, @Opidx3 = -1, "
                        "@OpValue3 = 0, @Owner = ?",
                        t["uid"], t["cidx"], code, spec["plate"], posx, amount, spec["dur"], weight, spec["maxup"],
                        spec["owner"])
            fl = _flag(cur)
            cur.execute("SELECT Amount FROM dbo.Item WHERE Userindex = ? AND Charidx = ? AND Plate = ? AND Posx = ? "
                        "AND Code = ?", t["uid"], t["cidx"], spec["plate"], posx, code)
            r = cur.fetchone()
            want = (before + amount) if (before is not None and spec["stack"]) else amount
            if fl != 1 or not r or int(r[0]) != want:
                cn.rollback()
                return False, "ячейка %d: процедура ответила %s, в ячейке %s (ожидалось %d) — откат" % (
                    posx, fl, None if not r else int(r[0]), want)
        cn.commit() if commit else cn.rollback()
        return True, "сумка %d, ячейки %s" % (spec["plate"], cells)
    except Exception:
        cn.rollback()
        raise
    finally:
        cn.autocommit = True


def give(mode, value, what, amount, code=0, dry=False, progress=None):
    """Выдача: what = 'gold' (amount — сколько золота), 'honor' (amount — сколько очков чести) или 'item' (code,
    amount — количество штук). → (выдано, пропущено, строки отчёта). Ошибка запроса/параметров — GiveError."""
    from asda_accounts import _db, _log
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise GiveError("количество — целое число")
    if amount < 1:
        raise GiveError("количество должно быть больше нуля")
    if what in ("gold", "honor") and amount > INT_MAX:
        raise GiveError("не больше %d за раз" % INT_MAX)
    if what == "item":
        try:
            code = int(code)
        except (TypeError, ValueError):
            raise GiveError("код предмета — целое число")
        spec = item_spec(code)                      # отказ по коду — до обращения к получателям
        if not spec["stack"] and amount > PLATE_CELLS[spec["plate"]]:
            raise GiveError("нестопочного предмета не больше %d штук (ячеек в сумке)" % PLATE_CELLS[spec["plate"]])
    cn = _db()
    try:
        targets, ban_lines = split_banned(resolve_targets(cn, mode, value), mode)
        ok_n, skip_n, lines = 0, 0, list(ban_lines)
        label = {"gold": "золото +%d" % amount, "honor": "очки чести +%d" % amount}.get(what) or (
            "%d × %d «%s»" % (amount, code, item_name(code)))
        for i, t in enumerate(targets):
            if progress:
                progress(i, len(targets))
            try:
                ok, text = _give_one(cn, t, what, code, amount, dry)
            except Exception as ex:   # ошибка SQL у одного — не останавливает остальных
                ok, text = False, "ошибка: %s" % ex
            who = "%s (учётка %s, ID %d/%d)" % (t["name"], t["login"], t["uid"], t["cidx"])
            lines.append(("✔ " if ok else "✖ ") + who + ": " + text)
            if ok:
                ok_n += 1
            else:
                skip_n += 1
            if not dry:
                _log("give-" + what, t["login"], t["uid"], "%s, перс. %s/%d: %s — %s" % (
                    label, t["name"], t["cidx"], "ok" if ok else "пропуск", text))
        head = "%s%s: выдано %d, пропущено %d" % ("ПРОВЕРКА (без записи) — " if dry else "", label, ok_n, skip_n)
        return ok_n, skip_n, [head] + lines
    finally:
        cn.close()


# ═════════════════════════════ премиум-почта (элитный ящик) ═════════════════════════════
# ★ 19.10.2026 (просьба владельца): отправка предметов в элитный почтовый ящик — Joy1.dbo.ItemPostBox (iType, Orderidx,
#   Userindex, Charidx, Code, Amount), та же таблица, куда кладёт покупки шлюз gp7 (UPCashitemBuy). Игрок забирает сам
#   (окно 69000, 11006 → UPCashitemToinvenGear/Functional): ячейку выбирает СЕРВЕР по своей памяти, поэтому отправлять можно
#   и игрокам в игре. Список ящика сервер читает из БД на каждый запрос 11004 (UPCashitemList, TOP 7 ORDER BY Orderidx);
#   порт-клиент шлёт 11004 при входе в мир и каждой смене карты (значок у панели) и при открытии ящика.
#   Разбор протокола — Reports/elite_mailbox_re.md; правила отправки — Reports/admin_items/README.md.
POST_MAX_PER_ROW = 7      # копий в одной строке ящика: клиент рисует ≤ 7 иконок, сервер кладёт ≤ 7 ячеек (§2.2, §3.3 разбора)
POST_MAX_QTY = 60         # больше копий не поместится ни в одну сумку (сумка 2 — 60 ячеек)
POST_BUY_TYPE = 1         # BuyType 1 = «премиум-шоп» (при заборе — нотис 110671); 3 = гача (окно результата гачи)


# ★ 01.11.2026: состояние серверных исправлений забора из ящика — по ЖИВЫМ ConfigSet/patches.ini трёх GameServer
#   (UTF-16, копии по SSH). P98_PremiumStackAmount: стопочный item_list из ящика приходит стопкой из 1 шт. в каждой ячейке
#   (без P98 — Amount 0 или дюп стопки; док AstoryServer/Docs/GameServer/premium-stack-amount-p98.md). P100_ChargeStack:
#   заряды спецпредмета складываются с лежащим при получении (проект Reports/item_dedup/charges/P100_PROJECT.md).
STACK_GS = ("GameServer", "Indun_GameServer", "Ch2_GameServer")   # все GS стойки (P98/P100 ставятся на все три)


def patch_enabled(section):
    """{GS: True/False} — секция [section] с Enabled=1 в живом patches.ini каждого GameServer (нет секции — False)."""
    out = {}
    for gs in STACK_GS:
        with SRV_LOCK:
            raw = open(srv_file(gs + "/ConfigSet/patches.ini"), "rb").read()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("cp1251", "replace")
        on, cur = False, None
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("["):
                cur = s.strip("[]").strip()
            elif cur == section and s.lower().replace(" ", "") in ("enabled=1",):
                on = True
        out[gs] = on
    return out


def p98_on():
    """True — P98 включён на всех трёх GameServer (стопочный из ящика = стопка из 1 шт. на ячейку)."""
    return all(patch_enabled("P98_PremiumStackAmount").values())


def post_spec(code):
    """Правило кода для премиум-почты. Сток строит предмет при заборе с количеством 0 (`sub_5340B0(…, a4 = 0, …)`,
    GameServer.c:117645): стопочный получил бы Amount 0 (или копию лежащей стопки — дюп), колчан / наживка — пустыми.
    ★ 01.11.2026: с P98 на всех GS стопочный приходит стопкой из 1 шт. в каждой ячейке — разрешён (копий = ячеек).
    Колчаны P98 не трогает (тип 10, стенд stand_p98 сценарий F: Amount 0) — отказ с подсказкой «Выдать предмет»."""
    s = item_spec(code)
    if s["stack"] and not p98_on():
        raise GiveError("стопочный предмет почтой придёт с количеством 0 (на сервере не включён P98_PremiumStackAmount) — "
                        "выдайте его кнопкой «Выдать предмет»")
    if s["kind"] == "quiver":
        raise GiveError("колчан/наживка почтой придут пустыми (забор из ящика не заполняет ёмкость, P98 их не "
                        "исправляет) — выдайте кнопкой «Выдать предмет»")
    return s


def _free_orders(used, need):
    """Номера заказа (Orderidx) для новых строк: наименьшие свободные с 1 у этого персонажа. Ящик показывает строки по
    возрастанию номера (TOP 7) — подарок встаёт первым; номер уникален среди строк персонажа."""
    out, n = [], 1
    while len(out) < need:
        if n not in used:
            out.append(n)
        n += 1
    return out


# ★ 02.11.2026 (ревизия п.2): у ItemPostBox нет индексов (куча) — UPDLOCK/HOLDLOCK запирал ВСЮ таблицу на время
#   записи (покупки 2601 и забор 11006 всех игроков ждали), а построчные INSERT растягивали это на N × RTT.
#   Теперь утилиты сериализуются своим замком приложения (sp_getapplock, покупки и забор его не берут), номер заказа
#   читается обычным SELECT, все строки — ОДНИМ INSERT с OUTPUT (сверка в том же операторе), транзакция короткая.
POSTBOX_APPLOCK = "AsdaAdmin.ItemPostBox.Orders"   # ресурс sp_getapplock: выбор номера заказа утилитами
POSTBOX_LOCK_MS = 15000                            # ждать замок не дольше, мс


def postbox_write(cn, t, orders_rows, dry, commit=True):
    """Запись в ящик одному персонажу. orders_rows — по заказу список строк (iType, Code, Amount).
    → (ok, текст, [номера заказов]). Номера — наименьшие свободные у персонажа; dry — без транзакции и записи.
    Два обращения к БД: (1) BEGIN TRAN + замок приложения + номера заказов (строк ещё нет); (2) ОДИН пакет:
    INSERT всех строк с OUTPUT, сверка числа и суммы, COMMIT (или ROLLBACK при расхождении / commit=False) — новые строки
    существуют незакоммиченными только внутри этого пакета на сервере (без сетевых ожиданий)."""
    cur = cn.cursor()
    if dry:
        cur.execute("SELECT Orderidx FROM dbo.ItemPostBox WHERE Userindex = ? AND Charidx = ?", t["uid"], t["cidx"])
        orders = _free_orders({int(r[0]) for r in cur.fetchall()}, len(orders_rows))
        return True, _orders_text(orders, orders_rows), orders
    cn.autocommit = True   # транзакцией управляет сам T-SQL (BEGIN TRAN … COMMIT/ROLLBACK в пакете 2)
    try:
        cur.execute("SET NOCOUNT ON; SET XACT_ABORT ON; BEGIN TRAN; DECLARE @rc INT; "
                    "EXEC @rc = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', @LockOwner = 'Transaction', "
                    "@LockTimeout = ?; IF @rc < 0 ROLLBACK; SELECT @rc", POSTBOX_APPLOCK, POSTBOX_LOCK_MS)
        rc = int(cur.fetchone()[0])
        if rc < 0:
            return False, "замок выдачи не получен (sp_getapplock %d) — другая выдача идёт слишком долго" % rc, []
        cur.execute("SELECT Orderidx FROM dbo.ItemPostBox WHERE Userindex = ? AND Charidx = ?", t["uid"], t["cidx"])
        orders = _free_orders({int(r[0]) for r in cur.fetchall()}, len(orders_rows))
        want = sorted((n, it, code, amt) for n, rows in zip(orders, orders_rows) for it, code, amt in rows)
        cur.execute("SET NOCOUNT ON; DECLARE @o TABLE (Orderidx INT, iType INT, Code INT, Amount INT); "
                    "INSERT INTO dbo.ItemPostBox (iType, Orderidx, Userindex, Charidx, Code, Amount) "
                    "OUTPUT inserted.Orderidx, inserted.iType, inserted.Code, inserted.Amount INTO @o VALUES " +
                    ", ".join(["(?, ?, ?, ?, ?, ?)"] * len(want)) + "; "
                    "DECLARE @ok INT = CASE WHEN (SELECT COUNT(*) FROM @o) = ? AND (SELECT SUM(Amount) FROM @o) = ? "
                    "THEN 1 ELSE 0 END; IF @ok = 1 AND ? = 1 COMMIT ELSE ROLLBACK; "
                    "SELECT Orderidx, iType, Code, Amount, @ok FROM @o",
                    *([v for n, it, code, amt in want for v in (it, n, t["uid"], t["cidx"], code, amt)] +
                      [len(want), sum(w[3] for w in want), 1 if commit else 0]))
        res = cur.fetchall()
        got = sorted(tuple(int(v) for v in r[:4]) for r in res)
        if not res or not int(res[0][4]) or got != want:
            return False, ("вставлено не то, что ожидалось (%d строк из %d) — %s" % (
                len(got), len(want), "откат" if not res or not int(res[0][4]) else "ЗАПИСАНО, проверьте ящик")), []
        return True, _orders_text(orders, orders_rows), orders
    finally:
        try:
            cur.execute("IF @@TRANCOUNT > 0 ROLLBACK")   # обрыв между пакетами — не оставить открытую транзакцию
        except Exception:
            pass


def _orders_text(orders, orders_rows):
    """«заказ N × штук (код C, iType T)» по заказам — для отчёта."""
    return ", ".join("заказ %d × %d (код %s, iType %s)" % (
        n, sum(a for _, _, a in rows), "/".join(sorted({str(c) for _, c, _ in rows})),
        "/".join(sorted({str(i) for i, _, _ in rows}))) for n, rows in zip(orders, orders_rows))


def _post_one(cn, t, code, qty, dry, commit=True):
    """Строки ящика премиум-почты одному персонажу (строка = до 7 копий, Amount = копий) в своей транзакции.
    → (ok, текст)."""
    chunks = [min(POST_MAX_PER_ROW, qty - i) for i in range(0, qty, POST_MAX_PER_ROW)]
    ok, text, _ = postbox_write(cn, t, [[(POST_BUY_TYPE, code, c)] for c in chunks], dry, commit)
    return ok, ("в ящик легло бы: " if dry else ("в ящик: " if ok else "")) + text


def send_post(mode, value, code, qty, dry=False, progress=None):
    """Премиум-почта: qty копий кода каждому получателю (строки ящика по ≤ 7). → (отправлено, пропущено, строки отчёта)."""
    from asda_accounts import _db, _log
    try:
        code, qty = int(code), int(qty)
    except (TypeError, ValueError):
        raise GiveError("код и количество — целые числа")
    if not 1 <= qty <= POST_MAX_QTY:
        raise GiveError("количество — от 1 до %d (каждая копия займёт ячейку сумки)" % POST_MAX_QTY)
    post_spec(code)                                  # отказ по коду — до обращения к получателям
    cn = _db()
    try:
        targets, ban_lines = split_banned(resolve_targets(cn, mode, value), mode)
        ok_n, skip_n, lines = 0, 0, list(ban_lines)
        label = "почта: %d × %d «%s»" % (qty, code, item_name(code))
        for i, t in enumerate(targets):
            if progress:
                progress(i, len(targets))
            try:
                ok, text = _post_one(cn, t, code, qty, dry)
            except Exception as ex:   # ошибка SQL у одного — не останавливает остальных
                ok, text = False, "ошибка: %s" % ex
            who = "%s (учётка %s, ID %d/%d)" % (t["name"], t["login"], t["uid"], t["cidx"])
            lines.append(("✔ " if ok else "✖ ") + who + ": " + text)
            ok_n, skip_n = ok_n + (1 if ok else 0), skip_n + (0 if ok else 1)
            if not dry:
                _log("send-post", t["login"], t["uid"], "%s, перс. %s/%d: %s — %s" % (
                    label, t["name"], t["cidx"], "ok" if ok else "пропуск", text))
        head = "%s%s: отправлено %d, пропущено %d" % ("ПРОВЕРКА (без записи) — " if dry else "", label, ok_n, skip_n)
        return ok_n, skip_n, [head] + lines
    finally:
        cn.close()


# ═════════════════════════════ вкладка окна ═════════════════════════════

def build_tab(nb, root):
    """Вкладка «Выдача» в окне утилиты: получатель, золото, предмет (поиск по названию), предпросмотр и отчёт."""
    import threading
    import tkinter as tk
    from tkinter import messagebox, ttk

    f = ttk.Frame(nb, padding=12)
    nb.add(f, text="Выдача")

    # ── получатель ──
    box = ttk.LabelFrame(f, text="Кому", padding=8)
    box.grid(row=0, column=0, columnspan=3, sticky="ew")
    mode = tk.StringVar(value="char")
    target = tk.StringVar()
    for i, (val, text) in enumerate((("char", "Персонаж (имя)"), ("login", "Учётка (логин) — все её персонажи"),
                                     ("all", "Все игроки — все персонажи всех учёток (кроме служебных ≤ 5000)"))):
        ttk.Radiobutton(box, text=text, value=val, variable=mode).grid(row=i, column=0, columnspan=2, sticky="w")
    ttk.Label(box, text="Имя / логин:").grid(row=3, column=0, sticky="w", pady=(6, 0))
    tentry = ttk.Entry(box, textvariable=target, width=34)
    tentry.grid(row=3, column=1, sticky="w", pady=(6, 0))
    mode.trace_add("write", lambda *_: tentry.state(["disabled"] if mode.get() == "all" else ["!disabled"]))

    # ── золото ──
    gbox = ttk.LabelFrame(f, text="Золото и очки чести (прибавляются к текущим)", padding=8)
    gbox.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    gold = tk.StringVar()
    ttk.Label(gbox, text="Сколько:").grid(row=0, column=0, sticky="w")
    ttk.Entry(gbox, textvariable=gold, width=16).grid(row=0, column=1, sticky="w", padx=(4, 8))
    gbtn = ttk.Button(gbox, text="Выдать золото")
    gbtn.grid(row=0, column=2, sticky="w")
    # ★ 19.10.2026: очки чести (Honor point, CharFameBank.Fmpoint) — так же прибавляются к текущим
    honor = tk.StringVar()
    ttk.Label(gbox, text="Очки чести (Honor):").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(gbox, textvariable=honor, width=16).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(6, 0))
    hbtn = ttk.Button(gbox, text="Начислить очки чести")
    hbtn.grid(row=1, column=2, sticky="w", pady=(6, 0))

    # ── предмет ──
    ibox = ttk.LabelFrame(f, text="Предмет", padding=8)
    ibox.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    code, qty, search = tk.StringVar(), tk.StringVar(value="1"), tk.StringVar()
    ttk.Label(ibox, text="Код:").grid(row=0, column=0, sticky="w")
    ttk.Entry(ibox, textvariable=code, width=10).grid(row=0, column=1, sticky="w", padx=(4, 8))
    ttk.Label(ibox, text="Количество:").grid(row=0, column=2, sticky="w")
    ttk.Entry(ibox, textvariable=qty, width=8).grid(row=0, column=3, sticky="w", padx=(4, 8))
    ibtn = ttk.Button(ibox, text="Выдать предмет")
    ibtn.grid(row=0, column=4, sticky="w")
    # ★ 19.10.2026: тот же код и количество — в элитный почтовый ящик (игрок забирает сам; можно игрокам в игре)
    pbtn = ttk.Button(ibox, text="Отправить премиум-почтой")
    pbtn.grid(row=0, column=5, sticky="w", padx=(6, 0))
    info = tk.Label(ibox, text="", anchor="w", justify="left", wraplength=520, fg="#555555")
    info.grid(row=1, column=0, columnspan=6, sticky="w", pady=(4, 4))
    ttk.Label(ibox, text="Найти по названию:").grid(row=2, column=0, columnspan=2, sticky="w")
    ttk.Entry(ibox, textvariable=search, width=28).grid(row=2, column=2, columnspan=2, sticky="w")
    sbtn = ttk.Button(ibox, text="Найти")
    sbtn.grid(row=2, column=4, sticky="w")
    found = tk.Listbox(ibox, height=5, width=70)
    found.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(4, 0))

    def show_info(*_):
        """Строка-описание кода под полем «код» (сумка, стопка, можно ли почтой)."""
        c = code.get().strip()
        if not c.isdigit():
            info.config(text="", fg="#555555")
            return
        try:
            text = describe_spec(int(c))
            try:
                post_spec(int(c))
                text += "; почтой — можно"
            except GiveError:
                text += "; почтой — нельзя (только «Выдать предмет»)"
            info.config(text=text, fg="#555555")
        except GiveError as ex:
            info.config(text="✖ " + str(ex), fg="#c62828")
    code.trace_add("write", show_info)

    def do_search():
        """Поиск кода по части названия — в список под полем."""
        found.delete(0, "end")
        for k, v in find_items(search.get()):
            found.insert("end", "%d — %s" % (k, v))
    sbtn.config(command=do_search)
    found.bind("<<ListboxSelect>>", lambda e: found.curselection() and code.set(
        found.get(found.curselection()[0]).split(" ", 1)[0]))

    # ── отчёт ──
    dry = tk.BooleanVar(value=False)
    ttk.Checkbutton(f, text="Только проверить (без записи)", variable=dry).grid(row=3, column=0, sticky="w", pady=(8, 0))
    status = tk.Label(f, text=SERVER_OFF_WARNING, anchor="w", fg="#b26a00")
    status.grid(row=4, column=0, columnspan=3, sticky="w")
    out = tk.Text(f, height=12, width=78, wrap="word")
    out.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(4, 0))

    def run(what):
        """Кнопки выдачи: подтверждение (кроме проверки), затем выдача в фоновом потоке."""
        val, m = target.get(), mode.get()
        args = {"gold": (gold.get(), 0), "honor": (honor.get(), 0)}.get(what) or (qty.get(), code.get())
        if not dry.get():
            who = {"char": "персонажу «%s»" % val, "login": "всем персонажам учётки «%s»" % val,
                   "all": "ВСЕМ персонажам всех игроков"}[m]
            thing = {"gold": "золото +%s" % args[0], "honor": "очки чести +%s" % args[0]}.get(what) or (
                "%s × код %s" % (args[0], args[1]))
            if what == "post":   # ящик сервер читает сам — выключать его не нужно
                ask = "Отправить премиум-почтой %s %s?\nИгрок заберёт сам из элитного ящика." % (thing, who)
            else:
                ask = "%s\n\nВыдать %s %s?" % (SERVER_OFF_WARNING, thing, who)
            if not messagebox.askyesno("Подтверждение", ask):
                return
        for b in (gbtn, hbtn, ibtn, pbtn):
            b.state(["disabled"])
        status.config(text="… выполняется", fg="#555555")
        out.delete("1.0", "end")

        def work():
            """Фоновый поток выдачи; итог — в done() через очередь окна."""
            try:
                prog = lambda i, n: root.after(0, status.config, {"text": "… %d из %d" % (i + 1, n)})
                if what == "post":
                    ok_n, skip_n, lines = send_post(m, val, args[1], args[0], dry=dry.get(), progress=prog)
                else:
                    ok_n, skip_n, lines = give(m, val, what, args[0], args[1], dry=dry.get(), progress=prog)
                root.after(0, done, True, "\n".join(lines), skip_n == 0)
            except GiveError as ex:
                root.after(0, done, False, str(ex), False)
            except Exception as ex:   # драйвер, сеть, права — показать, а не уронить окно
                root.after(0, done, False, "ошибка: %s" % ex, False)
        threading.Thread(target=work, daemon=True).start()

    def done(ok, text, clean):
        """Итог выдачи: строка состояния и отчёт по получателям."""
        for b in (gbtn, hbtn, ibtn, pbtn):
            b.state(["!disabled"])
        first = text.split("\n", 1)[0]
        status.config(text=("✔ " if ok and clean else ("⚠ " if ok else "✖ ")) + first,
                      fg="#1a7f37" if ok and clean else ("#b26a00" if ok else "#c62828"))
        out.insert("end", text)

    gbtn.config(command=lambda: run("gold"))
    hbtn.config(command=lambda: run("honor"))
    ibtn.config(command=lambda: run("item"))
    pbtn.config(command=lambda: run("post"))
    return f
