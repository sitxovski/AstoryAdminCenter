# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/eventdata.py — область «Счастливые часы» (шаг А5.4 «События и сбросы», 21.11.2026; разбор
Reports/admin_center/impl_a5_live_20261121.md §«А5.4»).

ТОЛЬКО СЕРВЕР. Event\\GameServerEvent.txt во ВСЕХ GameServer (поле, Indun, Ch2 — одна база, политика same; dev 21.11: 487FF8B5 ×3).
Реверс загрузчика (GameServer.c:10394-10470, sub_4190E0@0x4190E0 — зовётся ОДИН раз из WM_INITDIALOG диалога GameServer, :9132;
перечитывания нет — правка действует только после рестарта стойки):
  * сначала .\\Event\\Event.dat (зеркало GS, 2200 б): файл есть, но короче — return ДО чтения GameServerEvent.txt (счастливых часов нет);
  * затем fscanf «%s»: первое слово — число строк N (WORD 0x5A7964, со знаком), затем N строк по 6 слов
    «год месяц день час_от час_до значение» (atol / atof), массивы 0x5E23AC (WORD) / 0x5E2414 / 0x5E247C / 0x5E24E4 / 0x5E26DC (BYTE) /
    0x5E2744 (float).
Применение — GetExpUpDownValue@0x4CC3A0 (:81150) и ответ клиенту 4301 AlarmGameServerEventInfo@0x5585D0: ПЕРВАЯ строка с год = месяц =
день = сегодня (GetLocalTime сервера) и час_от ≤ час < час_до; значение ПРИБАВЛЯЕТСЯ к рейту опыта (fEvent NpcServer + значение), только
опыт (добычу не трогает). P91 (потолок опыта за моба × рейт) берёт ту же сумму; рейт вне 0…20 — потолок стока (P91 журнал 118).
Правка: lucky.add — строки на каждый день диапазона (по желанию — только выбранные дни недели) в конец файла и новое N; lucky.del —
убрать строки дат диапазона (все или с данным часом начала). Пересечение часов одного дня — отказ (у сервера сработала бы только первая
строка). Рейт > ×2 (значение > 1.0) — сильная правка: второе подтверждение владельца при утверждении набора (balance_ok).
Побочных эффектов при импорте нет.
"""
import datetime
import re

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "events", "Счастливые часы (опыт)"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
LUCKY = "Event\\GameServerEvent.txt"
SRV_FILES = [("GS", LUCKY, "same")]
CLIENT_FILES, DT, IMPORTERS, CSV_KEYS = {}, {}, {}, ()
ROWS_MAX = 32767                  # счётчик WORD со знаком (movsx у стока)
DAYS_MAX = 366                    # позиция — не больше года строк
VALUE_MAX = 10.0                  # ≤ fEvent 6038 (0…10): сумма с событием NpcServer остаётся в пределе P91 (0…20)
STRONG = 1.0                      # значение > 1.0 — рейт выше ×2 (при базе 1.0) — второе подтверждение владельца
TOK = 6

KINDS = {
    "lucky.add": ("Счастливые часы: добавить (GameServerEvent.txt ×3 GS, опыт +значение в часы каждого дня диапазона; рестарт стойки)",
                  ("date_from", "date_to", "h_from", "h_to", "value", "days"), False),
    "lucky.del": ("Счастливые часы: убрать строки дат (GameServerEvent.txt ×3 GS; рестарт стойки)", ("date_from", "date_to", "h_from"), False),
}


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def _date(p, k):
    try:
        return datetime.date.fromisoformat(str(p.get(k, "")).strip())
    except ValueError:
        raise OpRefused("поле «%s»: дата ГГГГ-ММ-ДД" % k)


def _value(p):
    s = str(p.get("value", "")).strip().replace(",", ".")
    if not re.match(r"^\d+(\.\d{1,2})?$", s):
        raise OpRefused("поле «value»: число с точкой, до двух знаков (например 1.0 — опыт ×2)")
    v = float(s)
    if not 0.0 < v <= VALUE_MAX:
        raise OpRefused("поле «value»: больше 0 и не больше %s" % fmt_value(VALUE_MAX))
    return v


def _days(p):
    s = re.sub(r"\s", "", str(p.get("days") or ""))
    if not s:
        return ""
    if not re.match(r"^[1-7]{1,7}$", s) or len(set(s)) != len(s):
        raise OpRefused("поле «days»: дни недели цифрами 1…7 без повторов (1 — понедельник), пусто — все дни")
    return "".join(sorted(s))


def norm(kind, p):
    a, b = _date(p, "date_from"), _date(p, "date_to")
    if b < a:
        raise OpRefused("конец диапазона %s раньше начала %s" % (b, a))
    if (b - a).days + 1 > DAYS_MAX:
        raise OpRefused("диапазон длиннее %d дней — разбейте на несколько позиций" % DAYS_MAX)
    if not (2000 <= a.year <= 2099 and 2000 <= b.year <= 2099):
        raise OpRefused("год вне 2000…2099")
    if kind == "lucky.del":
        return {"date_from": a.isoformat(), "date_to": b.isoformat(), "h_from": E._ival(p, "h_from", -1, 23)}
    hf, ht = E._ival(p, "h_from", 0, 23), E._ival(p, "h_to", 1, 24)
    if ht <= hf:
        raise OpRefused("конец окна (час %d) не позже начала (час %d) — сервер сверяет час_от ≤ час < час_до" % (ht, hf))
    return {"date_from": a.isoformat(), "date_to": b.isoformat(), "h_from": hf, "h_to": ht, "value": _value(p), "days": _days(p)}


def target_key(kind, p):
    return "lucky:%s:%s:%s" % (p["date_from"], p["date_to"], p["h_from"])


# =====================================================================================================================
# Разбор таблицы (повтор загрузчика sub_4190E0)
# =====================================================================================================================
_INT = re.compile(r"^-?\d+$")
_FLT = re.compile(r"^-?\d+(\.\d*)?$")


def parse_rows(raw_lines):
    """Строки файла (байты) → (N, [(номер строки, год, мес, день, час_от, час_до, значение)]). Отказ, если слова не ложатся построчно
    по 6 (сервер читает поток слов — порядок записей и строк файла должен совпадать) или числа не числа."""
    n = E._int(raw_lines[0].decode("latin-1"), -1) if raw_lines else -1
    body = [i for i in range(1, len(raw_lines)) if raw_lines[i].strip()]
    if n < 0 or len(body) != n or any(len(raw_lines[i].split()) != TOK for i in body):
        raise OpRefused("%s: число строк %d, строк тела %d — слова не ложатся построчно по %d, правка не делается" % (LUCKY, n, len(body), TOK))
    rows = []
    for i in body:
        w = [x.decode("latin-1") for x in raw_lines[i].split()]
        if not all(_INT.match(x) for x in w[:5]) or not _FLT.match(w[5]):
            raise OpRefused("%s: строка %d «%s» — не числа, правка не делается" % (LUCKY, i + 1, " ".join(w)[:60]))
        rows.append((i, int(w[0]), int(w[1]), int(w[2]), int(w[3]), int(w[4]), float(w[5])))
    return n, rows


def fmt_value(v):
    s = ("%.2f" % v).rstrip("0")
    return s + "0" if s.endswith(".") else s


def _dates(a, b, days):
    d = datetime.date.fromisoformat(a)
    end = datetime.date.fromisoformat(b)
    while d <= end:
        if not days or str(d.isoweekday()) in days:
            yield d
        d += datetime.timedelta(days=1)


def _rebuild(t, keep, extra, sep_tail):
    """Новые строки файла: число строк, оставленные строки тела (байты как были), добавленные строки."""
    body = [t.lines[i] for i in keep] + extra
    old0 = t.lines[0]
    t.lines = [str(len(body)).encode("ascii")] + body + ([b""] if sep_tail else [])
    t.changed = {0: old0} if old0 != t.lines[0] else {}


def _today(ev):
    """★ ревизия 44: «сегодня» — по часам СЕРВЕРА (GetLocalTime GameServer = местное время машины стойки; SQL на той же машине,
    domains.events.clock), не ПК. Подмена самотеста — ev._events_today."""
    t = getattr(ev, "_events_today", None)
    if t:
        return t
    from domains import events
    return events.clock()[0].date()


def _exp_events(ev):
    """★ ревизия 44: окна событий ОПЫТА (тип 1) в Event.dat всех NpcServer → ([(start, end, значение)] без года, непрочитанные | None).
    Подмена самотеста — ev._events_dat = {папка NpcServer: байты | None}."""
    from domains import events
    raw = getattr(ev, "_events_dat", None)
    if raw is None:
        try:
            got = events.read_files([n + "\\" + events.EV_DAT for n in events.NPC])
        except OpRefused as ex:
            return [], "все NpcServer (%s)" % str(ex)[:120]
        raw = {n: got.get(n + "\\" + events.EV_DAT) for n in events.NPC}
    out, bad = set(), [n for n in events.NPC if events.decode_dat(raw.get(n)) is None]
    for n in events.NPC:
        d = events.decode_dat(raw.get(n))
        if d is None:
            continue
        for m in range(events.SLOTS):
            e = d[(1, m)]
            if not events.entry_empty(e) and e["e_time"] > e["s_time"]:
                out.add((e["s_time"], e["e_time"], round(e["value"], 4)))
    return sorted(out), (", ".join(bad) if bad else None)


def k_lucky_add(ev, p, rep):
    new = list(_dates(p["date_from"], p["date_to"], p["days"]))
    if not new:
        raise OpRefused("в диапазоне %s…%s нет выбранных дней недели (%s)" % (p["date_from"], p["date_to"], p["days"]))
    today = _today(ev)
    if new[0] < today:
        raise OpRefused("дата %s уже прошла — сервер сверяет год, месяц и день, прошедшие строки не сработают никогда" % new[0])
    olds = None
    for g in E.GS:                                         # сначала проверка ВСЕХ копий — отказ до первой записи
        t = ev.st.get(g, LUCKY)
        n, rows = parse_rows(t.lines)
        key = [r[1:] for r in rows]
        if olds is None:
            olds = key
        elif key != olds:
            raise OpRefused("копия %s: строки %s не те, что в GameServer — копии разошлись, правка не однозначна" % (g, LUCKY))
        if n + len(new) > ROWS_MAX:
            raise OpRefused("строк станет %d — больше %d (счётчик сервера WORD со знаком)" % (n + len(new), ROWS_MAX))
    busy = []
    for d in new:
        for (y, m, dd, hf, ht, v) in olds:
            if (y, m, dd) == (d.year, d.month, d.day) and hf < p["h_to"] and p["h_from"] < ht:
                busy.append("%s %02d–%02d (+%s)" % (d, hf, ht, fmt_value(v)))
    if busy:
        raise OpRefused("часы пересекаются с уже записанными строками (%s) — у сервера сработала бы только первая строка дня — уберите их "
                        "(lucky.del) или выберите другие часы" % ", ".join(busy[:6]))
    val = fmt_value(p["value"])
    extra = [("%d\t%d\t%d\t%d\t%d\t%s" % (d.year, d.month, d.day, p["h_from"], p["h_to"], val)).encode("ascii") for d in new]
    for g in E.GS:
        t = ev.st.get(g, LUCKY)
        _n, rows = parse_rows(t.lines)
        _rebuild(t, [r[0] for r in rows], extra, not t.lines[-1].strip())
    rep["text"] = "счастливые часы: %s…%s%s, %s–%s — опыт +%s (×%s при базе 1.0), строк +%d (GameServerEvent.txt ×%d GS, после рестарта)" % (
        p["date_from"], p["date_to"], (" (дни недели %s)" % p["days"]) if p["days"] else "", "%02d:00" % p["h_from"], "%02d:00" % p["h_to"], val,
        fmt_value(1.0 + p["value"]), len(new), len(E.GS))
    rep["warnings"].append("GameServer читает GameServerEvent.txt только при старте (sub_4190E0) — действует после рестарта стойки")
    rep["warnings"].append("значение прибавляется к рейту опыта (событие NpcServer + счастливые часы), добычу не меняет; P91 поднимает "
                           "потолок опыта за моба вместе с рейтом")
    # ★ ревизия 44: событие опыта NpcServer (6038, окно MMDDчмм без года) и счастливые часы СКЛАДЫВАЮТСЯ (fEvent + значение):
    #   итог больше ×2 — сильная правка (второе подтверждение), даже если каждое по отдельности не сильное; Event.dat не прочитан — тоже.
    wins, werr = _exp_events(ev)
    base, hit = 1.0, None
    for d in new:
        a = d.month * 1000000 + d.day * 10000 + p["h_from"] * 100
        b = d.month * 1000000 + d.day * 10000 + p["h_to"] * 100
        for s, e, v in wins:
            if a < e and s < b and v > base:
                base, hit = v, "%s ×%s" % (d, fmt_value(v))
    top = base + p["value"]
    if werr:
        rep["warnings"].append("Event.dat не прочитан или битый: %s — сложение с событием опыта (6038) не проверено: при утверждении нужно "
                               "второе подтверждение" % werr)
    elif hit:
        rep["warnings"].append("на эти часы есть событие опыта NpcServer (%s) — рейт складывается: ×%s" % (hit, fmt_value(top)))
    what = "счастливые часы %s…%s %s–%s: рейт опыта" % (p["date_from"], p["date_to"], "%02d" % p["h_from"], "%02d" % p["h_to"])
    rep["_balance"] = [{"what": what, "old": "1.0", "new": fmt_value(top), "codes": [],
                        "kind": "rate" if (p["value"] > STRONG or top > 1.0 + STRONG or werr) else "value"}]


def k_lucky_del(ev, p, rep):
    a, b = datetime.date.fromisoformat(p["date_from"]), datetime.date.fromisoformat(p["date_to"])
    olds, drop = None, None
    for g in E.GS:
        t = ev.st.get(g, LUCKY)
        _n, rows = parse_rows(t.lines)
        key = [r[1:] for r in rows]
        if olds is None:
            olds = key
            drop = [k for k, r in enumerate(rows) if a <= _safe_date(r[1], r[2], r[3]) <= b and (p["h_from"] < 0 or r[4] == p["h_from"])]
        elif key != olds:
            raise OpRefused("копия %s: строки %s не те, что в GameServer — копии разошлись, правка не однозначна" % (g, LUCKY))
    if not drop:
        raise OpRefused("строк с датами %s…%s%s нет — убирать нечего" % (p["date_from"], p["date_to"],
                                                                         (" и часом начала %d" % p["h_from"]) if p["h_from"] >= 0 else ""))
    gone = [olds[k] for k in drop]
    for g in E.GS:
        t = ev.st.get(g, LUCKY)
        _n, rows = parse_rows(t.lines)
        _rebuild(t, [r[0] for k, r in enumerate(rows) if k not in set(drop)], [], not t.lines[-1].strip())
    rep["text"] = "счастливые часы: убрать %d строк (%s…%s%s) — GameServerEvent.txt ×%d GS, после рестарта" % (
        len(drop), p["date_from"], p["date_to"], (", час начала %d" % p["h_from"]) if p["h_from"] >= 0 else "", len(E.GS))
    rep["warnings"].append("убираются: " + ", ".join("%d-%02d-%02d %02d–%02d +%s" % (y, m, d, hf, ht, fmt_value(v)) for y, m, d, hf, ht, v in gone[:8])
                           + (" …" if len(gone) > 8 else ""))
    rep["warnings"].append("GameServer читает GameServerEvent.txt только при старте (sub_4190E0) — действует после рестарта стойки")


def _safe_date(y, m, d):
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return datetime.date(1900, 1, 1)                  # строка с несуществующей датой у сервера не сработает никогда


# =====================================================================================================================
# Клиентской половины у области нет
# =====================================================================================================================
def snapshot(snap):
    """Клиентской половины у области нет."""


def parse(cli, d):
    """Клиентской половины у области нет (разбор таблицы сервера — parse_rows)."""


def divergence(ev, cli, sec):
    """Копии GameServerEvent.txt у всех GameServer обязаны совпадать (одна база)."""
    rows = []
    t0 = ev.st.get(E.GS[0], LUCKY)
    for g in E.GS[1:]:
        t = ev.st.get(g, LUCKY)
        if t.data() != t0.data():
            rows.append({"id": g, "why": "%s отличается от GameServer (%s ≠ %s)" % (LUCKY, E.md5b(t.data())[:8], E.md5b(t0.data())[:8])})
    sec("lucky", "счастливые часы: копии GameServerEvent.txt отличаются от GameServer", rows,
        "у всех GameServer одна база — правка ложится на все три копии")
