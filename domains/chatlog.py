# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""chatlog.py — «Журнал чата» и заглушки чата (шаг А6.12, часть «панель», 22.11.2026; решение владельца №5 — журнал + заглушка, хранить
90 дней, план ADMIN_TOOL_PLAN.md §6 п.5; спецификация research_a6_economy_20261121.md §3 строка А6.12; серверная часть — P129 / AsdaPatch v86,
AstoryServer/Docs/GameServer/chat-log-p129.md; SQL AstoryServer/Docs/SQL/chat_01_migrate.sql; отчёт impl_a6_econ_20261121.md §А6.12 «панель»).

ЧТО ПИШЕТ СЕРВЕР. AsdaPatch.dll (P129) на трёх GameServer пишет каждое сообщение игрока в joylog1.chat.message (время UTC и местное,
сервер, карта, канал — коды 1…10 ниже, учётка сессии, хозяин и слот персонажа, имя, адресат шёпота / хозяин лавки, текст, сырые байты
text_raw, отметка заглушки mute_state). Заглушки — joylog1.chat.mute; DLL читает действующие процедурой chat.UP_ChatMuteActive раз в
MuteRefreshSec (15 с) в свой кэш: новая заглушка начинает действовать не позже чем через 15 с. Mode=0 (первая выкладка) — сообщение уходит,
в журнале mute_state=2 («заглушка, только журнал»); Mode=1 — сообщение никому не уходит (mute_state=1), игроку — нотис 3113.
ЧТО ДЕЛАЕТ ПАНЕЛЬ
  * state()          — установлена ли схема chat (таблицы и представления), сколько строк, первая и последняя запись, действующих
                       заглушек; режим P129 по patches.ini и журналу патчей копий GameServer (domains/patchcfg.state). Схемы нет —
                       installed=False и понятная пометка NOT_INSTALLED, без ошибок.
  * messages(q, user) — поиск по журналу: даты ГГГГММДД (по местному времени сервера, параметром), каналы, учётка (номер или логин; и
                       учётка сессии, и хозяин персонажа), персонаж (имя точно или хозяин + слот), подстрока текста (параметром LIKE по
                       NVARCHAR Arabic_CI_AS — без учёта регистра и для кириллицы, и для латиницы; арабский регистра не имеет), карта,
                       сервер, отметка заглушки, номер заглушки; страницы и предел глубины DEPTH_MAX; text_raw (hex и прочтения
                       cp1251 / UTF-8 / cp1256) — по ключу raw=1. Поиск по тексту без учётки и персонажа — только в окне ≤ TEXT_DAYS_MAX
                       суток и не чаще TEXT_PER_MIN раз в минуту на пользователя (бюджет на пользователя) и TEXT_ALL_MIN на службу.
  * mutes(q)         — заглушки: действующие / истёкшие / снятые / все, по учётке, страницами.
  * операции core/ops (журнал adm.audit; логин правок asda_ops — только EXECUTE chat.UP_ChatMuteSet / UP_ChatMuteLift и SELECT chat.mute,
    sql/adminc_24_chat.sql):
      chat.mute   — поставить заглушку на учётку (scope 1) или персонажа (scope 2: хозяин + слот) на срок 1…5 256 000 мин с причиной;
                    откат — снять её (UP_ChatMuteLift);
      chat.unmute — снять действующую заглушку досрочно (с причиной); откат — поставить снова на остаток исходного срока (до того же
                    until_utc, с округлением вверх до минуты).
    Права chat.view / chat.mute / chat.unmute — owner, admin, gm (решение владельца №3 по делам: gm ведёт и отзывает низкие ступени —
    предупреждение и кик; заглушка ниже блока). Служебные учётки (≤ SVC_MAX) — заглушить и снять только владелец.
Тексты chat.* — NVARCHAR (Юникод): чтение БЕЗ fix_text (GameReader joylog1 перекодирует cp1256 → cp1251 — арабский текст исказился бы),
параметры — как есть, без to_db_text. Каждое значение — параметром; имена столбцов — только из кода ниже. Побочных эффектов при импорте нет.
"""
import datetime
import math
import re
import threading
import time

from core import db
from core.ops import Operation, OpRefused, register
from domains import acjournal

# канал: (код в chat.message.channel, название, опкод клиента) — chat_01_migrate.sql (колонка channel), chat-log-p129.md §1
CHANNELS = ((1, "обычный", 5084), (2, "глобальный", 5086), (3, "широкий (поиск отряда / торговля)", 6560), (4, "шёпот", 5088),
            (5, "отряд", 5105), (6, "клан", 4120), (7, "армия", 6718), (8, "лавка", 6313), (9, "крик лавки", 6316),
            (10, "крик предметом", 5450))
CHANNEL_NAMES = {c: n for c, n, _o in CHANNELS}
MUTE_STATES = {0: "", 1: "отклонено заглушкой", 2: "помечено: заглушка, сообщение ушло (Mode=0)"}
SESSION_STATES = {0: "до входа в мир", 1: "в мире", 2: "вход соулмейтом", 3: "соулмейт без учётки"}
SCOPES = {"account": 1, "char": 2}
SCOPE_NAMES = {1: "учётка", 2: "персонаж"}
NOT_INSTALLED = "журнал чата не установлен (P129, AsdaPatch v86 — ждёт общего рестарта)"
PARTIAL = "схема chat установлена не полностью: нет %s — переустановите chat_01_migrate.sql (P129)"
GRANTS_MISSING = ("у логина правок панели нет прав на заглушки chat.* — sql/adminc_24_chat.sql (выдаёт выкладка панели или deploy_p129.py "
                  "после установки схемы)")
TABLES = {"message": "U", "mute": "U", "v_recent": "V", "v_mute_active": "V"}   # что видит asda_admin (процедуры ему не видны: EXECUTE запрещён)
REFRESH_SEC = 15              # MuteRefreshSec P129 по умолчанию: заглушка доходит до GameServer не позже
RETENTION_DAYS = 90           # RetentionDays P129 (решение владельца №5)
SVC_MAX = 5000                # служебные учётки (players.OPERATOR_MAX_UID): заглушить / снять — только владелец
MINUTES_MAX = 5256000         # предел chat.UP_ChatMuteSet (10 лет)
# ★ ревизия 71 Н-3 (решение координатора до слова владельца): пределы роли — ОДНО место. gm: срок заглушки не больше max_minutes (сутки —
#   «мягче блока на сутки», ступени ≥ 3 дел gm не решает) и снятие только своих заглушек; admin / owner — без этих пределов.
ROLE_LIMITS = {"gm": {"max_minutes": 1440, "unmute_own_only": True}}
REFRESH_MIN, REFRESH_MAX = 2, 3600                             # пределы MuteRefreshSec в DLL (ChatJournal.cpp:959)
REASON_MIN, REASON_MAX = 3, 256
PAGE, PAGE_MAX = 50, 200
DEPTH_MAX = 10000             # дальше этой глубины журнал не листается (сузьте фильтр)
DEFAULT_DAYS = 2              # без дат — последние сутки и ещё одни (по часам SQL-сервера)
TEXT_MIN, TEXT_MAX = 2, 100   # подстрока текста
TEXT_DAYS_MAX = 31            # поиск по тексту без учётки и персонажа — окно не больше стольких суток
TEXT_PER_MIN = 12             # поисков по тексту в минуту на пользователя панели
TEXT_ALL_MIN = 40             # … и на всю службу
P129_CACHE_S = 60             # режим P129 (patches.ini трёх копий по SSH) — не чаще раза в минуту
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_SERVER = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_lock = threading.Lock()
_text_hits = {}               # пользователь | "*" → [время поиска по тексту]
_p129 = {}                    # "v" → (время, ответ)


def _int(v, msg, lo, hi):
    """Целое из строки в пределах [lo, hi]; иначе отказ полным текстом msg."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def _iso(v):
    return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v


def _reader():
    """Чтение joylog1 логином asda_admin БЕЗ перекодировки fix_text (chat.* — NVARCHAR); сбой подключения — понятный отказ."""
    try:
        r = db.GameReader("joylog1")
    except db.DbError as ex:
        raise OpRefused("журнал чата не прочитан: %s" % ex)
    r.arabic = False
    return r


def _rows(r, sql, params=()):
    try:
        return r.rows(sql, params)
    except db.DbError as ex:
        raise OpRefused("журнал чата не прочитан: %s" % ex)


def _installed(r):
    """→ (установлен ли, [нет объектов]). Видны таблицы и представления схемы chat (SELECT у asda_admin есть)."""
    have = {x["name"]: x["type"].strip() for x in _rows(r, "SELECT o.name, o.type FROM sys.objects o JOIN sys.schemas s ON s.schema_id = o.schema_id "
                                                          "WHERE s.name = N'chat' AND o.type IN ('U', 'V')")}
    miss = ["chat.%s" % n for n, t in TABLES.items() if have.get(n) != t]
    return (not miss), miss


def _need(r):
    """Отказ, если схемы нет или она неполная (для операций)."""
    ok, miss = _installed(r)
    if ok:
        return
    if len(miss) == len(TABLES):
        raise OpRefused(NOT_INSTALLED)
    raise OpRefused(PARTIAL % ", ".join(miss))


def _not_installed(miss):
    return {"installed": False, "missing": miss, "note": NOT_INSTALLED if len(miss) == len(TABLES) else PARTIAL % ", ".join(miss)}


def p129_mode(force=False):
    """Режим P129 по копиям GameServer (patchcfg.state AsdaPatch: секция [P129_ChatLog] в patches.ini, итог журнала патчей) → {read, modes,
    mode, refresh, mode_note | error}. Кэш P129_CACHE_S; сбой чтения — read=False с причиной («не прочитано» ≠ «нет»)."""
    with _lock:
        hit = _p129.get("v")
        if hit and not force and time.monotonic() - hit[0] < P129_CACHE_S:
            return hit[1]
    from domains import patchcfg
    try:
        st = patchcfg.state(dll_only="AsdaPatch")
        d = st["dlls"][0]
        sec = next((s for s in d["sections"] if s["name"] == "P129_ChatLog"), None)
        if sec is None:
            out = {"read": False, "error": "в каталоге настроек AsdaPatch нет секции P129_ChatLog (исходник старше v86)"}
        else:
            vals = {k["key"]: k["values"] for k in sec["keys"]}
            modes = dict(sec["modes"])
            out = {"read": True, "modes": modes, "mode": vals.get("Mode") or {}, "refresh": vals.get("MuteRefreshSec") or {},
                   "mode_note": p129_summary(modes, vals.get("Mode") or {})}   # ★ р71 Н-2: отдельный ключ (служба переводит mode_note)
    except OpRefused as ex:
        out = {"read": False, "error": str(ex)}
    with _lock:
        _p129["v"] = (time.monotonic(), out)
    return out


def p129_summary(modes, mode_vals):
    """Строка для человека по режимам копий: не выложен / только журнал / заглушка действует / выключен / смешанно."""
    vs = set(modes.values())
    if not vs or vs <= {"unread"}:
        return "режим P129 не прочитан (patches.ini или журнал патчей копий GameServer)"
    if vs == {"absent"}:
        return "P129 на сервере ещё не выложен: секции [P129_ChatLog] в patches.ini нет (AsdaPatch v86 ждёт общего рестарта)"
    if vs == {"journal"}:
        return "P129 Mode=0: заглушка только помечает сообщения в журнале (mute_state=2) — сообщение уходит, как прежде; запрет — при Mode=1"
    if vs == {"active"}:
        return "P129 Mode=1: заглушка действует — сообщение никому не уходит, игроку — нотис"
    if vs <= {"off", "pending_off", "self_off"}:
        return "P129 выключен (Enabled=0): журнал не пишется, заглушка не действует"
    return "P129 в копиях по-разному: %s" % ", ".join("%s — %s" % (g, m) for g, m in sorted(modes.items()))


def refresh_sec(m=None):
    """★ р71 М-2: через сколько секунд заглушка доходит до GameServer — фактический MuteRefreshSec копий (наибольший из прочитанных, в пределах
    DLL); не прочитано — умолчание REFRESH_SEC. m — ответ p129_mode() (None — последний из кэша, без нового чтения стойки)."""
    if m is None:
        with _lock:
            hit = _p129.get("v")
        m = hit[1] if hit else {}
    vals = []
    for v in ((m or {}).get("refresh") or {}).values():
        try:
            n = int(str(v).strip())
        except (TypeError, ValueError):
            continue
        if REFRESH_MIN <= n <= REFRESH_MAX:
            vals.append(n)
    return max(vals) if vals else REFRESH_SEC


def limits_of(role):
    """Пределы роли для заглушек (ROLE_LIMITS) → {max_minutes, unmute_own_only}; без записи — без пределов."""
    x = ROLE_LIMITS.get(role) or {}
    return {"max_minutes": int(x.get("max_minutes") or MINUTES_MAX), "unmute_own_only": bool(x.get("unmute_own_only"))}


def state(with_p129=True):
    """Состояние журнала чата (см. шапку)."""
    with _reader() as r:
        ok, miss = _installed(r)
        out = {"channels": [{"code": c, "name": n, "opcode": o} for c, n, o in CHANNELS], "refresh_sec": REFRESH_SEC,
               "retention_days": RETENTION_DAYS, "svc_max": SVC_MAX, "servers": servers(), "minutes_max": MINUTES_MAX}
        if not ok:
            out.update(_not_installed(miss))
        else:
            j = _rows(r, "SELECT MIN(ev_utc) AS oldest, MAX(ev_utc) AS newest FROM chat.message")[0]
            n = _rows(r, "SELECT SUM(p.rows) AS n FROM sys.partitions p WHERE p.object_id = OBJECT_ID(N'chat.message') AND p.index_id IN (0, 1)")[0]["n"]
            m = _rows(r, "SELECT COUNT(*) AS n FROM chat.mute WHERE lifted_utc IS NULL AND until_utc > SYSUTCDATETIME()")[0]["n"]
            out.update(installed=True, missing=[], note=None, oldest=_iso(j["oldest"]), newest=_iso(j["newest"]),
                       rows=None if n is None else int(n), mutes_active=int(m))
    out["p129"] = p129_mode() if with_p129 else None
    out["refresh_sec"] = refresh_sec(out["p129"])                 # ★ р71 М-2: фактический MuteRefreshSec копий
    return out


def servers():
    """Имена процессов-источников (папки GameServer стойки — stack_layout); список для выбора, фильтр принимает и другое имя."""
    try:
        from domains import shopdata
        return list(shopdata.folders("GSP"))
    except Exception:                                    # состав стойки не прочитан — стоковые три папки
        return ["GameServer", "Indun_GameServer", "Ch2_GameServer"]


def _budget(user, now=None):
    """Бюджет поиска по тексту: TEXT_PER_MIN на пользователя и TEXT_ALL_MIN на службу в минуту; превышение — отказ."""
    now = time.monotonic() if now is None else now
    with _lock:
        for who, cap, text in ((user or "?", TEXT_PER_MIN, "поиск по тексту чата — не больше %d в минуту на пользователя, подождите"),
                               ("*", TEXT_ALL_MIN, "поиск по тексту чата — не больше %d в минуту на всю службу, подождите")):
            lst = [t for t in _text_hits.get(who, []) if now - t < 60]
            _text_hits[who] = lst
            if len(lst) >= cap:
                raise OpRefused(text % cap)
        for who in (user or "?", "*"):
            _text_hits[who].append(now)


def _channels(v):
    """«1,2,4» → [1, 2, 4]; пусто — None (все)."""
    s = str(v or "").strip()
    if not s:
        return None
    out = []
    for part in s.split(","):
        c = _int(part, "канал — номер из списка 1…10 (через запятую)", 1, 10)
        if c not in out:
            out.append(c)
    return out


def _resolve(acc):
    try:
        return acjournal.resolve_account(acc)
    except db.DbError as ex:
        raise OpRefused("учётка не найдена: %s" % ex)


def build_filters(q):
    """Строка запроса → проверенные фильтры (без SQL). Отказ — понятной причиной, без обращения к журналу."""
    q = q or {}
    f = {"uid": _resolve(q.get("account")), "char": (q.get("char") or "").strip() or None, "char_uid": None, "char_slot": None,
         "channels": _channels(q.get("channel")), "text": q.get("text") or None, "map": None, "server": (q.get("server") or "").strip() or None,
         "mute": (q.get("mute") or "").strip() or None, "mute_id": None, "from": acjournal.parse_day(q.get("from"), "from"),
         "to": acjournal.parse_day(q.get("to"), "to"), "raw": str(q.get("raw") or "0") == "1"}
    if f["char"] and (len(f["char"]) > 32 or _CTRL.search(f["char"])):
        raise OpRefused("имя персонажа — не длиннее 32 знаков")
    if q.get("char_uid") not in (None, "") or q.get("char_slot") not in (None, ""):
        f["char_uid"] = _int(q.get("char_uid"), "хозяин персонажа — номер учётки от 1 до 2147483647", 1, 2 ** 31 - 1)
        f["char_slot"] = _int(q.get("char_slot"), "слот персонажа — целое от 0 до 255", 0, 255)
    if f["text"] is not None:
        t = str(f["text"]).strip()
        if len(t) < TEXT_MIN or len(t) > TEXT_MAX or _CTRL.search(t):
            raise OpRefused("подстрока текста — от %d до %d знаков" % (TEXT_MIN, TEXT_MAX))
        f["text"] = t
    if q.get("map") not in (None, ""):
        f["map"] = _int(q.get("map"), "карта — номер от 0 до 65535", 0, 65535)
    if f["server"] and not _SERVER.match(f["server"]):
        raise OpRefused("имя сервера — латиница, цифры, «_», до 64 знаков")
    if f["mute"] and f["mute"] not in ("any", "0", "1", "2"):
        raise OpRefused("отметка заглушки — any, 0, 1 или 2")
    if q.get("mute_id") not in (None, ""):
        f["mute_id"] = _int(q.get("mute_id"), "номер заглушки — целое от 1", 1, 2 ** 62)
    if f["from"] and f["to"] and f["from"] > f["to"]:
        raise OpRefused("дата «с» позже даты «по»")
    if f["text"] and not (f["uid"] or f["char"] or f["char_uid"]):
        if bool(f["from"]) != bool(f["to"]):
            raise OpRefused("поиск по тексту без учётки и персонажа — укажите обе даты (окно не больше %d суток) или ни одной (последние %d суток)"
                            % (TEXT_DAYS_MAX, DEFAULT_DAYS))
        if f["from"]:
            span = (datetime.datetime.strptime(f["to"], "%Y%m%d") - datetime.datetime.strptime(f["from"], "%Y%m%d")).days + 1
            if span > TEXT_DAYS_MAX:
                raise OpRefused("поиск по тексту без учётки и персонажа — окно не больше %d суток (сейчас %d)" % (TEXT_DAYS_MAX, span))
    return f


_OFF = "DATEDIFF(MINUTE, SYSDATETIME(), SYSUTCDATETIME())"      # местное время сервера → UTC (DLL пишет ev_local по часам этой же машины)


def _where(f):
    cond, args = [], []
    if f["uid"]:
        marks = ",".join("?" * len(f["uid"]))
        cond.append("(user_index IN (%s) OR char_owner IN (%s))" % (marks, marks))
        args.extend(f["uid"] + f["uid"])
    if f["char"]:
        cond.append("char_name = ?")
        args.append(f["char"])
    if f["char_uid"]:
        cond.append("char_owner = ? AND char_slot = ?")
        args.extend([f["char_uid"], f["char_slot"]])
    if f["channels"]:
        cond.append("channel IN (%s)" % ",".join("?" * len(f["channels"])))
        args.extend(f["channels"])
    if f["text"]:
        cond.append("text LIKE ? ESCAPE '\\'")
        args.append("%" + re.sub(r"([\\%_\[])", r"\\\1", f["text"]) + "%")
    if f["map"] is not None:
        cond.append("map_index = ?")
        args.append(f["map"])
    if f["server"]:
        cond.append("server_name = ?")
        args.append(f["server"])
    if f["mute"] == "any":
        cond.append("mute_state <> 0")
    elif f["mute"]:
        cond.append("mute_state = ?")
        args.append(int(f["mute"]))
    if f["mute_id"]:
        cond.append("mute_id = ?")
        args.append(f["mute_id"])
    if f["from"]:
        cond.append("ev_utc >= DATEADD(MINUTE, %s, CONVERT(datetime2(3), ?, 112))" % _OFF)
        args.append(f["from"])
    if f["to"]:
        cond.append("ev_utc < DATEADD(MINUTE, %s, DATEADD(DAY, 1, CONVERT(datetime2(3), ?, 112)))" % _OFF)
        args.append(f["to"])
    if not f["from"] and not f["to"]:
        cond.append("ev_utc >= DATEADD(DAY, -%d, SYSUTCDATETIME())" % DEFAULT_DAYS)
    return " WHERE " + " AND ".join(cond), args


def raw_views(b):
    """Сырые байты текста → {hex, cp1251, utf8, cp1256} — для разбора кодировки (прочтения с заменой нечитаемого)."""
    if b is None:
        return None
    b = bytes(b)
    return {"hex": b.hex(" ").upper(), "len": len(b), "cp1251": b.decode("cp1251", "replace"), "utf8": b.decode("utf-8", "replace"),
            "cp1256": b.decode("cp1256", "replace")}


_COLS = ("msg_id, ev_utc, ev_local, server_name, server_port, map_index, channel, channel_name, sub_channel, opcode, user_index, char_owner, "
         "char_slot, char_name, session_state, gm_flag, target_name, target_user_num, text, mute_state, mute_id")


def messages(q, user=None):
    """Журнал чата по фильтрам (см. шапку) → {installed, rows, total, more, page, pages, size, …}. Схемы нет — installed=False и пометка."""
    q = q or {}
    f = build_filters(q)
    size = _int(q.get("size") or PAGE, "строк на странице — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница журнала чата — целое от 1 до %d" % DEPTH_MAX, 1, DEPTH_MAX)
    if page * size > DEPTH_MAX:
        raise OpRefused("дальше %d строк журнал не листается — сузьте фильтр или интервал дат" % DEPTH_MAX)
    with _reader() as r:
        ok, miss = _installed(r)
        if not ok:
            return dict(_not_installed(miss), rows=[], total=0, more=False, page=1, pages=1, size=size)
        if f["text"]:
            _budget(user)
        w, args = _where(f)
        total = _rows(r, "SELECT COUNT(*) AS n FROM (SELECT TOP (%d) msg_id FROM chat.message%s) t" % (DEPTH_MAX + 1, w), args)[0]["n"]
        rows = _rows(r, "SELECT %s%s FROM chat.message%s ORDER BY ev_utc DESC, msg_id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
                     % (_COLS, ", text_raw" if f["raw"] else "", w), args + [(page - 1) * size, size])
    errors = []
    logins = acjournal._logins([x["user_index"] for x in rows] + [x["char_owner"] for x in rows], errors)
    out = []
    for x in rows:
        uid, own = x["user_index"], x["char_owner"]
        item = {"id": x["msg_id"], "utc": _iso(x["ev_utc"]), "local": _iso(x["ev_local"]), "server": x["server_name"], "port": x["server_port"],
                "map": x["map_index"], "channel": x["channel"], "channel_title": CHANNEL_NAMES.get(x["channel"], "канал %s" % x["channel"]),
                "channel_name": x["channel_name"], "sub": x["sub_channel"], "opcode": x["opcode"], "uid": uid, "login": logins.get(uid),
                "owner": own, "owner_login": logins.get(own), "slot": x["char_slot"], "char": x["char_name"],
                "session": x["session_state"], "gm": bool(x["gm_flag"]), "to": x["target_name"], "to_num": x["target_user_num"],
                "chat_text": x["text"], "mute_state": x["mute_state"], "mute_title": MUTE_STATES.get(x["mute_state"], str(x["mute_state"])),
                "mute_id": x["mute_id"], "service": any(v is not None and 0 < int(v) <= SVC_MAX for v in (uid, own))}
        if f["raw"]:
            item["raw"] = raw_views(x.get("text_raw"))
        out.append(item)
    pages_all = max(1, (min(total, DEPTH_MAX) + size - 1) // size)
    return {"installed": True, "rows": out, "total": min(total, DEPTH_MAX), "more": total > DEPTH_MAX, "page": page, "size": size,
            "pages": pages_all, "errors": errors, "depth_max": DEPTH_MAX, "default_days": None if (f["from"] or f["to"]) else DEFAULT_DAYS,
            "raw": f["raw"]}


MUTE_FILTERS = ("active", "expired", "lifted", "all")
_MUTE_COLS = ("mute_id, scope, user_index, char_slot, char_name, until_utc, reason, created_utc, created_by, lifted_utc, lifted_by, lift_reason, "
              "CASE WHEN lifted_utc IS NOT NULL THEN 'lifted' WHEN until_utc > SYSUTCDATETIME() THEN 'active' ELSE 'expired' END AS st, "
              "DATEDIFF(MINUTE, SYSUTCDATETIME(), until_utc) AS minutes_left")
_MUTE_ST = {"active": "lifted_utc IS NULL AND until_utc > SYSUTCDATETIME()", "expired": "lifted_utc IS NULL AND until_utc <= SYSUTCDATETIME()",
            "lifted": "lifted_utc IS NOT NULL", "all": "1 = 1"}


def _mute_row(x, logins=None):
    return {"id": x["mute_id"], "scope": int(x["scope"]), "scope_title": SCOPE_NAMES.get(int(x["scope"]), str(x["scope"])), "uid": x["user_index"],
            "login": (logins or {}).get(x["user_index"]), "slot": x["char_slot"], "char": x["char_name"], "until": _iso(x["until_utc"]),
            "reason": x["reason"], "created": _iso(x["created_utc"]), "by": x["created_by"], "lifted": _iso(x["lifted_utc"]),
            "lifted_by": x["lifted_by"], "lift_reason": x["lift_reason"], "state": x["st"], "minutes_left": x["minutes_left"],
            "service": 0 < int(x["user_index"]) <= SVC_MAX}


def mutes(q):
    """Заглушки: q — state (active | expired | lifted | all), account (номер или логин), page, size. Новые сверху."""
    q = q or {}
    st = (q.get("state") or "active").strip()
    if st not in MUTE_FILTERS:
        raise OpRefused("состояние заглушек — одно из: %s" % ", ".join(MUTE_FILTERS))
    uids = _resolve(q.get("account"))
    size = _int(q.get("size") or PAGE, "строк на странице — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница — целое от 1 до 100000", 1, 100000)
    cond, args = [_MUTE_ST[st]], []
    if uids:
        cond.append("user_index IN (%s)" % ",".join("?" * len(uids)))
        args.extend(uids)
    w = " WHERE " + " AND ".join(cond)
    with _reader() as r:
        ok, miss = _installed(r)
        if not ok:
            return dict(_not_installed(miss), rows=[], total=0, page=1, pages=1, size=size, counts={k: 0 for k in MUTE_FILTERS[:3]})
        total = _rows(r, "SELECT COUNT(*) AS n FROM chat.mute" + w, args)[0]["n"]
        rows = _rows(r, "SELECT %s FROM chat.mute%s ORDER BY mute_id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % (_MUTE_COLS, w),
                     args + [(page - 1) * size, size])
        c = _rows(r, "SELECT SUM(CASE WHEN lifted_utc IS NULL AND until_utc > SYSUTCDATETIME() THEN 1 ELSE 0 END) AS active, "
                     "SUM(CASE WHEN lifted_utc IS NULL AND until_utc <= SYSUTCDATETIME() THEN 1 ELSE 0 END) AS expired, "
                     "SUM(CASE WHEN lifted_utc IS NOT NULL THEN 1 ELSE 0 END) AS lifted FROM chat.mute")[0]
    errors = []
    logins = acjournal._logins([x["user_index"] for x in rows], errors)
    return {"installed": True, "rows": [_mute_row(x, logins) for x in rows], "total": total, "page": page, "size": size,
            "pages": max(1, (total + size - 1) // size), "state": st, "counts": {k: int(c[k] or 0) for k in ("active", "expired", "lifted")},
            "errors": errors, "refresh_sec": refresh_sec()}


# ------------------------------------------------------------------------------------------------------------ операции
REASON_MSG = "причина — строка от %d до %d знаков"
LIFT_REASON_MSG = "причина снятия — строка от %d до %d знаков"


def _reason(v, msg=REASON_MSG):
    """Причина оператора (одна строка без управляющих символов) → строка, иначе отказ msg."""
    s = v.strip() if isinstance(v, str) else ""
    if len(s) < REASON_MIN or len(s) > REASON_MAX or _CTRL.search(s):
        raise OpRefused(msg % (REASON_MIN, REASON_MAX))
    return s


def _target(ctx, p):
    """Цель заглушки из параметров → {scope, uid, slot, name, login}. scope account — uid или login; char — uid + idx или имя (char)."""
    p = p or {}
    sc = str(p.get("scope") or "").strip()
    if sc not in SCOPES:
        raise OpRefused("на кого заглушка — account (учётка) или char (персонаж)")
    scope = SCOPES[sc]
    uid, slot, name, login = None, None, None, None
    try:
        if scope == 2 and p.get("char") and p.get("uid") in (None, ""):
            nm = str(p["char"]).strip()
            if not nm or len(nm) > 20 or _CTRL.search(nm):
                raise OpRefused("имя персонажа — до 20 знаков")
            from domains import reports
            errs = []
            found = [t for t in reports._target(nm, errs) if not t["deleted"]]
            if errs:
                raise OpRefused(errs[0])
            if not found:
                raise OpRefused("персонажа «%s» нет" % nm)
            if len(found) > 1:
                raise OpRefused("персонажей с именем «%s» несколько — укажите учётку и слот" % nm)
            uid, slot = found[0]["uid"], found[0]["idx"]
        elif p.get("uid") not in (None, ""):
            uid = _int(p.get("uid"), "учётка — номер от 1 до 2147483647", 1, 2 ** 31 - 1)
        elif p.get("login"):                                  # ★ р71 Н-1: логин — и для учётки, и для персонажа (логин + слот)
            got = _resolve(str(p["login"]))
            if len(got) != 1:
                raise OpRefused("по «%s» нашлось несколько учёток (номер и логин) — укажите номер" % str(p["login"])[:40])
            uid = got[0]
        else:
            raise OpRefused("нужна учётка (номер или логин) или персонаж")
        if scope == 2 and slot is None:
            slot = _int(p.get("idx"), "слот персонажа — целое от 0 до 255", 0, 255)
        with db.GameReader("asdastoryop") as op:
            a = op.one("SELECT Userindex, Us_id FROM Us_member WHERE Userindex = ?", (uid,))
        if not a:
            raise OpRefused("учётки №%d нет" % uid)
        login = a["Us_id"]
        if scope == 2:
            with db.GameReader("joy1") as y:
                c = y.one("SELECT Charname FROM dbo.Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, slot))
            if not c:
                raise OpRefused("у учётки №%d нет персонажа в слоте %d" % (uid, slot))
            name = (c["Charname"] or "").strip()
    except db.DbError as ex:
        raise OpRefused("цель заглушки не прочитана: %s" % ex)
    if uid <= SVC_MAX and ctx.role != "owner":
        raise OpRefused("заглушки служебных учёток (номер ≤ %d) ставит и снимает только владелец" % SVC_MAX)
    return {"scope": scope, "uid": uid, "slot": slot, "name": name, "login": login}


def _active_of(cur, t, lock=False):
    """Действующие заглушки ровно этой цели (scope, учётка, слот) → [номер]; lock — под UPDLOCK, HOLDLOCK (в транзакции записи)."""
    sql = ("SELECT mute_id, until_utc FROM chat.mute%s WHERE scope = ? AND user_index = ? AND %s AND lifted_utc IS NULL AND until_utc > SYSUTCDATETIME() "
           "ORDER BY mute_id" % (" WITH (UPDLOCK, HOLDLOCK)" if lock else "", "char_slot = ?" if t["scope"] == 2 else "char_slot IS NULL"))
    args = (t["scope"], t["uid"]) + ((t["slot"],) if t["scope"] == 2 else ())
    return cur.rows(sql, args)


def _writer():
    """Транзакция записи joylog1 логином asda_ops с проверкой прав на заглушки (иначе — понятный отказ GRANTS_MISSING)."""
    try:
        w = db.GameWriter("joylog1")
    except db.DbError as ex:
        raise OpRefused("заглушка не записана: %s" % ex)
    w.arabic = False                                     # chat.* — NVARCHAR: имя и причина без fix_text (иначе арабский исказился бы и в журнале, и в откате)
    try:
        g = w.rows("SELECT HAS_PERMS_BY_NAME(N'chat.UP_ChatMuteSet', 'OBJECT', 'EXECUTE') AS s, "
                   "HAS_PERMS_BY_NAME(N'chat.UP_ChatMuteLift', 'OBJECT', 'EXECUTE') AS l, HAS_PERMS_BY_NAME(N'chat.mute', 'OBJECT', 'SELECT') AS m")[0]
    except db.DbError as ex:
        w.close()
        raise OpRefused("заглушка не записана: %s" % ex)
    if not (g["s"] == 1 and g["l"] == 1 and g["m"] == 1):
        w.close()
        raise OpRefused(GRANTS_MISSING)
    return w


def _w(w, sql, params=()):
    try:
        return w.rows(sql, params)
    except db.DbError as ex:
        raise OpRefused("заглушка не записана: %s" % ex)


def _mode_warn(out):
    m = p129_mode()
    if not m.get("read"):
        out.append("режим P129 не прочитан: %s" % m.get("error"))
        return
    if set(m["modes"].values()) != {"active"}:
        out.append(m["mode_note"])


def _set(w, t, minutes, reason, by):
    r = _w(w, "SET NOCOUNT ON; EXEC chat.UP_ChatMuteSet @Scope = ?, @UserIndex = ?, @CharSlot = ?, @CharName = ?, @Minutes = ?, @Reason = ?, @By = ?",
           (t["scope"], t["uid"], t["slot"], t["name"], minutes, reason[:REASON_MAX], by[:64]))
    if not r or not r[0].get("mute_id"):
        raise OpRefused("процедура заглушки не вернула номер — заглушка не записана")
    return int(r[0]["mute_id"]), r[0]["until_utc"]


def _lift(w, mid, by, reason):
    r = _w(w, "SET NOCOUNT ON; EXEC chat.UP_ChatMuteLift @MuteId = ?, @By = ?, @Reason = ?", (mid, by[:64], reason[:REASON_MAX]))
    return int(r[0]["lifted"]) if r else 0


class _ChatOp(Operation):
    """Общее для операций заглушек: журнал — цель «chat:…», транзакция asda_ops, фиксация после записи журнала (ops._finish)."""
    reversible = True
    two_factor = False

    @staticmethod
    def _tx(fn):
        w = _writer()
        try:
            out = fn(w)
        except BaseException:
            w.close()
            raise
        out.update(_commit=w.commit, _close=w.close)
        return out


def _minutes(v, ctx=None):
    """Срок в минутах: 1…MINUTES_MAX; ★ р71 Н-3 — и не больше предела роли (ROLE_LIMITS)."""
    n = _int(v, "срок — целое число минут от 1 до %d" % MINUTES_MAX, 1, MINUTES_MAX)
    lim = limits_of(ctx.role)["max_minutes"] if ctx is not None else MINUTES_MAX
    if n > lim:
        raise OpRefused("роль %s ставит заглушку не дольше %d мин — дольше ставит администратор или владелец" % (ctx.role, lim))
    return n


@register
class ChatMute(_ChatOp):
    name, title, perm = "chat.mute", "Чат: поставить заглушку", "chat.mute"

    def target(self, p):
        p = p or {}
        return "chat:%s:%s%s" % (p.get("scope"), p.get("uid") or p.get("login") or p.get("char") or "?",
                                 (":%s" % p.get("idx")) if p.get("idx") not in (None, "") else "")

    def preview(self, ctx, p):
        minutes = _minutes((p or {}).get("minutes"), ctx)
        reason = _reason((p or {}).get("reason"))
        with _reader() as r:
            _need(r)
            t = _target(ctx, p)
            act = _active_of(_Rd(r), t)
            until = _rows(r, "SELECT DATEADD(MINUTE, ?, SYSUTCDATETIME()) AS u", (minutes,))[0]["u"]
        w = _writer()                                    # права логина правок — в предпросмотре (иначе отказ только при записи)
        w.close()
        rs = refresh_sec(p129_mode())
        warn = ["заглушка начнёт действовать не позже чем через %d с — сервер перечитывает заглушки раз в %d с" % (rs, rs),
                "на учётку — все её персонажи и вход соулмейтом с неё" if t["scope"] == 1 else "на персонажа — кто бы им ни играл (хозяин и слот)",
                "GM-флаг сессии не глушится (ExemptOperators=1 по умолчанию)"]
        for a in act:
            warn.append("у цели уже есть действующая заглушка №%d до %s UTC — новая добавится рядом" % (a["mute_id"], _iso(a["until_utc"])))
        _mode_warn(warn)
        u16 = _iso(until)[:16]
        text = ("заглушить учётку №%d (%s) на %d мин. (до %s UTC): %s" % (t["uid"], t["login"] or "?", minutes, u16, reason) if t["scope"] == 1 else
                "заглушить персонажа %s (учётка №%d, слот %d) на %d мин. (до %s UTC): %s" % (t["name"] or "?", t["uid"], t["slot"], minutes, u16, reason))
        return {"text": text,
                "expect": {"active": [int(a["mute_id"]) for a in act]}, "target": t, "warnings": warn}

    def apply(self, ctx, p, prev):
        minutes = _minutes((p or {}).get("minutes"), ctx)
        reason = _reason((p or {}).get("reason"))
        t = prev["target"]

        def go(w):
            now = [int(a["mute_id"]) for a in _active_of(_Wr(w), t, lock=True)]
            seen = (p or {}).get("expect")
            if now != prev["expect"]["active"] or (seen is not None and seen != prev["expect"]):
                raise OpRefused("заглушки цели изменились с предпросмотра — откройте заново")
            mid, until = _set(w, t, minutes, reason, ctx.login)
            return {"before": {"active": now}, "after": {"mute_id": mid, "until_utc": _iso(until), "scope": t["scope"], "uid": t["uid"],
                                                          "slot": t["slot"], "name": t["name"], "minutes": minutes, "reason": reason},
                    "message": ("заглушка №%d: учётка №%d (%s) до %s UTC" % (mid, t["uid"], t["login"] or "?", _iso(until)[:16]) if t["scope"] == 1 else
                                "заглушка №%d: персонаж %s (учётка №%d, слот %d) до %s UTC" % (mid, t["name"] or "?", t["uid"], t["slot"], _iso(until)[:16]))}
        return self._tx(go)

    def undo(self, ctx, row):
        import json
        a = json.loads(row.get("after_json") or "{}")
        mid = a.get("mute_id")
        if not mid:
            raise OpRefused("в журнале нет номера заглушки — откат не выполнен")
        if int(a.get("uid") or 0) <= SVC_MAX and ctx.role != "owner":
            raise OpRefused("заглушки служебных учёток (номер ≤ %d) ставит и снимает только владелец" % SVC_MAX)

        def go(w):
            n = _lift(w, int(mid), ctx.login, "откат записи журнала №%s" % row["id"])
            if n != 1:
                raise OpRefused("заглушка №%d уже не действует (снята или истекла) — откатывать нечего" % int(mid))
            return {"before": {"mute_id": int(mid)}, "after": {"mute_id": int(mid), "lifted": 1},
                    "message": "заглушка №%d снята откатом записи №%s" % (int(mid), row["id"])}
        return self._tx(go)


class _Rd:
    """Курсор чтения для _active_of (GameReader asda_admin)."""

    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return _rows(self.r, sql, params)


class _Wr:
    """Курсор записи для _active_of (GameWriter asda_ops, внутри транзакции)."""

    def __init__(self, w):
        self.w = w

    def rows(self, sql, params=()):
        return _w(self.w, sql, params)


def _mute_by_id(cur, mid, lock=False):
    r = cur.rows("SELECT %s FROM chat.mute%s WHERE mute_id = ?" % (_MUTE_COLS, " WITH (UPDLOCK, HOLDLOCK)" if lock else ""), (mid,))
    return r[0] if r else None


def _mid(p):
    return _int((p or {}).get("mute_id"), "номер заглушки — целое от 1", 1, 2 ** 62)


@register
class ChatUnmute(_ChatOp):
    name, title, perm = "chat.unmute", "Чат: снять заглушку", "chat.unmute"

    def target(self, p):
        return "chat:mute:%s" % ((p or {}).get("mute_id"),)

    def _check(self, ctx, x, mid):
        if not x:
            raise OpRefused("заглушки №%d нет" % mid)
        if x["st"] == "lifted":
            raise OpRefused("заглушка №%d уже снята (%s, %s)" % (mid, x["lifted_by"], _iso(x["lifted_utc"])[:16]))
        if x["st"] == "expired":
            raise OpRefused("заглушка №%d уже истекла (%s UTC)" % (mid, _iso(x["until_utc"])[:16]))
        if int(x["user_index"]) <= SVC_MAX and ctx.role != "owner":
            raise OpRefused("заглушки служебных учёток (номер ≤ %d) ставит и снимает только владелец" % SVC_MAX)
        if limits_of(ctx.role)["unmute_own_only"] and (x["created_by"] or "") != ctx.login:     # ★ р71 Н-3
            raise OpRefused("роль %s снимает только свои заглушки — №%d поставил %s" % (ctx.role, mid, x["created_by"]))

    def preview(self, ctx, p):
        mid = _mid(p)
        reason = _reason((p or {}).get("reason"), LIFT_REASON_MSG)
        with _reader() as r:
            _need(r)
            x = _mute_by_id(_Rd(r), mid)
        self._check(ctx, x, mid)
        w = _writer()
        w.close()
        rs = refresh_sec(p129_mode())
        warn = ["снятие дойдёт до GameServer не позже чем через %d с — сервер перечитывает заглушки раз в %d с" % (rs, rs)]
        _mode_warn(warn)
        u16 = _iso(x["until_utc"])[:16]
        text = ("снять заглушку №%d (учётка №%d, до %s UTC, поставил %s: %s): %s" % (mid, x["user_index"], u16, x["created_by"], x["reason"], reason)
                if int(x["scope"]) == 1 else "снять заглушку №%d (персонаж %s, учётка №%d, слот %d, до %s UTC, поставил %s: %s): %s" % (
                    mid, x["char_name"] or "?", x["user_index"], x["char_slot"], u16, x["created_by"], x["reason"], reason))
        return {"text": text,
            "expect": {"mute_id": mid, "until_utc": _iso(x["until_utc"]), "state": x["st"]}, "warnings": warn}

    def apply(self, ctx, p, prev):
        mid = _mid(p)
        reason = _reason((p or {}).get("reason"), LIFT_REASON_MSG)

        def go(w):
            x = _mute_by_id(_Wr(w), mid, lock=True)
            self._check(ctx, x, mid)
            cur = {"mute_id": mid, "until_utc": _iso(x["until_utc"]), "state": x["st"]}
            seen = (p or {}).get("expect")
            if cur != prev["expect"] or (seen is not None and seen != prev["expect"]):
                raise OpRefused("заглушка №%d изменилась с предпросмотра — откройте заново" % mid)
            if _lift(w, mid, ctx.login, reason) != 1:
                raise OpRefused("заглушка №%d уже не действует — снимать нечего" % mid)
            return {"before": _mute_row(x), "after": {"mute_id": mid, "lifted": 1, "scope": int(x["scope"]), "uid": x["user_index"],
                                                      "slot": x["char_slot"], "name": x["char_name"], "until_utc": _iso(x["until_utc"]),
                                                      "reason": x["reason"], "lift_reason": reason},
                    "message": "заглушка №%d снята" % mid}
        return self._tx(go)

    def undo(self, ctx, row):
        import json
        a = json.loads(row.get("after_json") or "{}")
        if not a.get("mute_id") or not a.get("until_utc"):
            raise OpRefused("в журнале нет данных заглушки — откат не выполнен")
        if int(a.get("uid") or 0) <= SVC_MAX and ctx.role != "owner":
            raise OpRefused("заглушки служебных учёток (номер ≤ %d) ставит и снимает только владелец" % SVC_MAX)
        t = {"scope": int(a["scope"]), "uid": int(a["uid"]), "slot": a.get("slot"), "name": a.get("name"), "login": None}

        def go(w):
            left = _w(w, "SELECT DATEDIFF_BIG(SECOND, SYSUTCDATETIME(), CONVERT(datetime2(3), ?, 121)) AS s", (str(a["until_utc"])[:23],))[0]["s"]
            if left is None or int(left) <= 0:
                raise OpRefused("срок заглушки №%d уже вышел (%s UTC) — ставить снова нечего" % (int(a["mute_id"]), str(a["until_utc"])[:16]))
            minutes = min(MINUTES_MAX, max(1, int(math.ceil(int(left) / 60.0))))
            reason = ("откат снятия (запись №%s): %s" % (row["id"], a.get("reason") or ""))[:REASON_MAX]
            mid, until = _set(w, t, minutes, reason, ctx.login)
            return {"before": {"mute_id": int(a["mute_id"]), "lifted": 1}, "after": {"mute_id": mid, "until_utc": _iso(until), "scope": t["scope"],
                                                                                     "uid": t["uid"], "slot": t["slot"], "name": t["name"],
                                                                                     "minutes": minutes, "restored_from": int(a["mute_id"])},
                    "message": "заглушка снова поставлена откатом записи №%s: №%d до %s UTC" % (row["id"], mid, _iso(until)[:16])}
        return self._tx(go)
