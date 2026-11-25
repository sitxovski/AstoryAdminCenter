# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""acdaily.py — «Античит: суточный отчёт» (шаг А6.6, 22.11.2026; разбор research_a6_economy_20261121.md §3 строка А6.6 и §1 «Суточный
отчёт»; отчёт — Reports/admin_center/impl_a6_econ_20261121.md §А6.6). Перенос AstoryServer/Tools/Anticheat/ac_daily_report.py в панель БЕЗ СМЕНЫ
ПОВЕДЕНИЯ: считает тот же код исходника (ac_daily_report.build / render, ac_metrics_logs, ac_metrics_db с исправленной по ревизии 54 M3,
ac_common), меняются только три входа:
  * ЖУРНАЛЫ — локально на сервере (config.STACK_ROOT), без шары //@@ASTORY_SERVER_HOSTNAME@@: встроенный open исходника заменён проверкой белого списка
    (копии GameServer / NpcServer из stack_layout и только те каналы и файлы, что читает исходник) и открытием с общим доступом READ | WRITE |
    DELETE (logs._open_shared — как у «Журналов стойки»). Архива OTP_Report на сервере нет (у исходника — папка ПК) — пустая строка;
  * БАЗА — логин службы asda_admin (db.GameReader, только чтение), а не devgsaccount с паролем из PasswordSQL.txt: подключение исходника
    (db_connect.connect / read_password) в частной копии отключено. Запросы идут через db_connect.query исходника (его проверка «только
    SELECT») и дополнительно через db.assert_select_only панели. Текст — сырой драйвер, как у исходника (без перекодировки fix_text);
  * ПОРОГИ — параметр операции thr {ключ: значение} вместо --thr; без него — прежние (ac_common.THR). Решение владельца №9 не принято:
    только экран, без уведомлений.
ЧАСТНАЯ КОПИЯ: на каждый прогон модули исходника исполняются заново под своими именами с собственным __builtins__ (__import__ отдаёт
  частные модули, open — проверка белого списка), поэтому пороги прогона не задевают правило M3 раздела «Передачи и рынок» (trade.m3 —
  свой экземпляр ac_common.THR) и соседний прогон. Исходник берётся с ПК (AstoryServer/Tools/Anticheat) или из копии ext/anticheat архива выкладки.
«ВНЕ ВЛАДЕЛЬЦА / ФОН» — как в исходнике: Ctx.is_owner по DEFAULT_OWNER_RE (ники и логины владельца и служебные GM_* / ADM_*); деления на
  служебные учётки ≤ 5000 в исходнике нет — и здесь нет.
ХРАНЕНИЕ — база панели AsdaAdmin, adm.AcDaily (sql/adminc_19_acdaily.sql: только SELECT / INSERT): разбор по метрикам, все события
  (до EVENTS_KEEP на метрику — CSV исходника) и Markdown исходника как есть. Файлов служба не пишет (в отчёте ники, логины и IP).
ЗАПУСК: служба сама раз в сутки (core/sched DAILY ac.daily RUN_AT, вчерашние сутки по часам сервера), задание adm.job или оператор с правом
  ac.daily_run — бюджет: RUNS_PER_HOUR ручных прогонов на пользователя в час, один прогон за раз, байты журналов окна — в бюджет чтения
  журналов пользователя (logs.charge). Считает только служба на сервере (журналы стойки — там). Просмотр — право ac.view, IP и MAC —
  только с players.view_net. Нет журнала — метрика без событий («событий нет»), журнал не открылся — статус «ошибка» с причиной (как у
  исходника: safe()). Побочных эффектов при импорте нет.
"""
import collections
import datetime
import decimal
import hashlib
import json
import os
import re
import threading
import time
import types

from core import config, db
from core.ops import Operation, OpRefused, register
from domains import acsrc, logs, shopdata, srvtables

AC_SRC = acsrc.AC_SRC                    # исходник на ПК (AstoryServer/Tools/Anticheat)
AC_EXT = acsrc.AC_EXT                    # его копия в дереве службы (ext/anticheat; на сервере — только она, сверка с манифестом)
AC_FILES = ("ac_daily_report.py", "ac_metrics_logs.py", "ac_metrics_db.py", "ac_common.py", "db_connect.py")
LOAD_ORDER = ("db_connect", "ac_common", "ac_metrics_logs", "ac_metrics_db", "ac_daily_report")   # зависимости — раньше
RUN_AT = datetime.time(0, 20)            # служба — вчерашние сутки после снимка золота econ.snapshot 00:05 (core/sched DAILY)
DAYS_MAX = 31                            # окно отчёта: суток не больше
RUNS_PER_HOUR = 4                        # ручных прогонов (не служба) одного пользователя за 60 минут
QUERY_TIMEOUT_S = 600                    # предел одного запроса (у исходника предела нет; у GameReader панели — 60 с)
EVENTS_KEEP = 5000                       # событий метрики в events_json (последние по времени; полный счёт — events_total)
LIST_MAX = 60                            # прогонов в списке
PAGE_DEF, PAGE_MAX = 100, 500            # события метрики: строк на странице
THR_MAX = 1e9                            # порог: больше нуля и не больше
SERVICE_LOGIN = "service:daily"          # = core/sched.LOGIN
SERVICE_BYTES_MAX = 1024 * 1024 * 1024   # ★ ревизия 56 Н-3: ночной прогон службы — свой предел окна (сутки dev ≈ 130 КБ; запас ×8000), без бюджета
                                         #   чтения пользователей (logs.charge) — пометка service_limit в meta
BACKFILL_DAYS = 7                        # ★ ревизия 56 Н-3: при старте службы досчитать сутки до вчерашних (вчера — DAILY) без отчёта, не дальше
KEEP_SERVICE_DAYS = 400                  # ★ ревизия 56 Н-4: прогоны службы хранятся не меньше года (= adm.AcDailyPurge)
KEEP_MANUAL_DAYS = 90                    #   ручные и задания — 90 суток
LOCK_NAME = "asda.acdaily.run"           # ★ ревизия 56 (мелочь 3): межпроцессный замок «один прогон» — sp_getapplock AsdaAdmin (служба и консоль)
# Что читает исходник (ac_metrics_logs.py; самотест сверяет с его текстом). ★ ревизия 56 (мелочь 4): имена — как у index_dir исходника
#   (любое имя на ГГГГММДД.txt без разделителей пути), каналы — только эти: GameServer Log\<канал>, NpcServer Error_Log\SpeedHack_<дата>,
#   LoginManager Log\LoginMngError\OTP_Report*<дата> | LoginoutCheck_<дата> | LoginProc_<дата>, архив OTP_Report*<дата>
GS_CHANNELS = ("Log_Game", "Log_SpeedHack", "Log_Secret", "Log_Exception_Asm", "Log_Item", "Log_LevelUp", "Log_Operator", "Login")
NPC_FILE = "SpeedHack"
LM_FILES = ("OTP_Report", "LoginoutCheck", "LoginProc")
DATE_RX = re.compile(r"(\d{8})\.txt$", re.I)          # = ac_common.DATE_IN_NAME
DAY_RX = re.compile(r"^\d{8}$")
# ★ ревизия 56 Н-2: архив старых OTP_Report (на ПК — @@ASTORY_DEV_ROOT@@\_backup\2026-10-12_otp_report_archive, 20260724…20261011) — на сервере в
#   дереве службы (права как у неё: Administrators / SYSTEM), без хешей паролей (tools/otp_archive_push.py маскирует 32-hex поля Pass);
#   выкладка папку не трогает
OTP_ARCHIVE = config.SERVICE_ROOT + r"\otp_archive"

STACK_OVERRIDE = None                    # самотест: (корень, [копии GS], [копии NPC], архив OTP | "") вместо стойки сервера
_RUN = threading.Lock()                  # один прогон за раз внутри процесса (между процессами — LOCK_NAME)


# ---------------------------------------------------------------- исходник

def src_dir():
    """Папка исходника: на сервере — только копия ext/anticheat в дереве службы (★ ревизия 56 С-1), на ПК — AstoryServer/Tools/Anticheat."""
    return acsrc.pick(AC_SRC, AC_EXT)


def code_md5(d=None):
    """md5 пяти файлов исходника (имя + байты, порядок AC_FILES) — какой код посчитал отчёт; копия ext/ — со сверкой манифеста."""
    d = d or src_dir()
    h = hashlib.md5()
    for f in AC_FILES:
        h.update(f.encode("ascii") + b"\0" + acsrc.read_verified(os.path.join(d, f)) + b"\0")
    return h.hexdigest()


def stack():
    """(корень стойки, копии GameServer, копии NpcServer, архив OTP_Report | ""): стойка сервера или подстановка самотеста."""
    if STACK_OVERRIDE:
        return STACK_OVERRIDE
    return config.STACK_ROOT, list(srvtables.STACK_GS), shopdata.folders("NPC"), OTP_ARCHIVE if os.path.isdir(OTP_ARCHIVE) else ""


class Guard:
    """Встроенный open частной копии исходника: только чтение «rb», только файлы белого списка под корнем стойки (и в архиве OTP_Report),
    открытие с общим доступом READ | WRITE | DELETE (logs._open_shared; занят писателем без общего доступа или нет файла — OpRefused)."""

    def __init__(self, root, gs, npc, archive=""):
        self.root = os.path.normcase(os.path.abspath(root))
        self.archive = os.path.normcase(os.path.abspath(archive)) if archive else ""
        alt = lambda xs: "(?:%s)" % "|".join(re.escape(x) for x in xs)
        self.rx = re.compile(r"(?:%s\\Log\\%s\\[^\\/]*\d{8}\.txt|%s\\Error_Log\\%s_\d{8}\.txt|"
                             r"LoginManager\\Log\\LoginMngError\\(?:OTP_Report[^\\/]*|LoginoutCheck_|LoginProc_)\d{8}\.txt)"
                             % (alt(gs), alt(GS_CHANNELS), alt(npc), NPC_FILE), re.I)
        self.arx = re.compile(r"OTP_Report[^\\/]*\d{8}\.txt", re.I)
        self.opened = 0

    @staticmethod
    def _rel(path, base):
        p = os.path.normcase(os.path.abspath(os.fspath(path)))
        if not base or not p.startswith(base + os.sep):
            return None
        return p[len(base) + 1:].replace("/", "\\")

    def rel(self, path):
        """Путь относительно корня стойки (разделитель «\\») или None — вне корня."""
        return self._rel(path, self.root)

    def open(self, file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
        if mode != "rb" or buffering != -1 or encoding or errors or newline or not closefd or opener:
            raise PermissionError("суточный отчёт открывает журналы только на чтение")
        r = self.rel(file)
        if r is not None and self.rx.fullmatch(r):
            path = os.path.join(self.root, r)
        else:
            a = self._rel(file, self.archive)
            if a is None or not self.arx.fullmatch(a):
                raise PermissionError("файл вне белого списка суточного отчёта: %s" % (r or a or os.path.basename(os.fspath(file))))
            path = os.path.join(self.archive, a)
        f = logs._open_shared(path)
        self.opened += 1
        return f


class _Cur:
    """Курсор с вторым рубежом панели (db.assert_select_only) поверх проверки исходника db_connect.assert_select_only."""

    def __init__(self, cur, owner):
        self._c, self._o = cur, owner

    def execute(self, sql, params=None):
        db.assert_select_only(sql)
        self._o.queries += 1
        return self._c.execute(sql, params) if params else self._c.execute(sql)

    @property
    def description(self):
        return self._c.description

    def fetchall(self):
        return self._c.fetchall()


class _Cn:
    """Соединение для db_connect.query исходника: сырой pyodbc логина asda_admin (db.GameReader), предел запроса QUERY_TIMEOUT_S."""

    def __init__(self, reader):
        self._r = reader
        self.queries = 0
        try:
            reader.cn.timeout = QUERY_TIMEOUT_S
        except Exception:
            pass

    def cursor(self):
        return _Cur(self._r.cn.cursor(), self)


def _no_source_connect(*_a, **_k):
    raise RuntimeError("подключение исходника к базе в панели отключено — база читается логином службы asda_admin")


class Src:
    """Частная копия исходника на один прогон: C (ac_common), L (ac_metrics_logs), D (ac_metrics_db), R (ac_daily_report)."""

    def __init__(self, mods, guard, d):
        self.C, self.L, self.D, self.R = mods["ac_common"], mods["ac_metrics_logs"], mods["ac_metrics_db"], mods["ac_daily_report"]
        self.guard, self.dir, self.readers, self.cns, self.mods = guard, d, [], [], mods
        mods["db_connect"].connect = _no_source_connect
        mods["db_connect"].read_password = _no_source_connect
        self.D.open_db = self.open_db

    def open_db(self, name):
        r = db.GameReader(name)
        self.readers.append(r)
        c = _Cn(r)
        self.cns.append(c)
        return c

    def queries(self):
        return sum(c.queries for c in self.cns)

    def close(self):
        for r in self.readers:
            r.close()
        self.readers = []


def load(root, gs, npc, archive="", d=None):
    """Исполнить модули исходника заново в частном пространстве (domains/acsrc.load: проверенные байты, свой __builtins__ и sys — общий
    sys.path и sys.modules не меняются) → Src."""
    d = d or src_dir()
    guard = Guard(root, gs, npc, archive)
    mods, _h = acsrc.load(d, LOAD_ORDER, "acdaily_src_", open_fn=guard.open,
                          extra={"stack_layout": types.SimpleNamespace(GS_FOLDERS=list(gs), NPC_FOLDERS=list(npc))})
    return Src(mods, guard, d)


def defaults():
    """Прежние пороги исходника (ac_common.THR) → {ключ: значение}."""
    mods, _h = acsrc.load(src_dir(), ("ac_common",), "acdaily_thr_")
    return dict(mods["ac_common"].THR)


# ---------------------------------------------------------------- проверка ввода

_DAY_MSG = {"last": ("последние сутки отчёта — дата ГГГГММДД", "последние сутки отчёта — нет такой даты %s"),
            "day": ("сутки отчёта — дата ГГГГММДД", "сутки отчёта — нет такой даты %s")}


def _day(v, what):
    """ГГГГММДД → date; what — "last" (последние сутки окна) | "day" (сутки отчёта в просмотре)."""
    bad_form, bad_date = _DAY_MSG[what]
    s = str(v if v is not None else "").strip()
    if not DAY_RX.match(s):
        raise OpRefused(bad_form)
    try:
        return datetime.datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        raise OpRefused(bad_date % s)


def check_params(p, today=None):
    """Параметры отчёта → {d1, days, thr (все), over (отличные от прежних)}. Отказ — до журналов и базы."""
    p = p or {}
    extra = sorted(k for k in p if k not in ("date", "days", "thr", "job_id", "expect"))
    if extra:
        raise OpRefused("у суточного отчёта нет параметра %s (есть: date, days, thr)" % extra[0])
    today = today or datetime.date.today()
    d1 = _day(p["date"], "last") if p.get("date") not in (None, "") else today - datetime.timedelta(days=1)
    if d1 > today:
        raise OpRefused("последние сутки отчёта позже сегодняшних по часам сервера")
    days = p.get("days", 1)
    if isinstance(days, bool) or not (isinstance(days, int) or (isinstance(days, str) and days.strip().isdigit())):
        raise OpRefused("суток в окне отчёта — целое от 1 до %d" % DAYS_MAX)
    days = int(days)
    if not 1 <= days <= DAYS_MAX:
        raise OpRefused("суток в окне отчёта — целое от 1 до %d" % DAYS_MAX)
    base = defaults()
    thr = dict(base)
    raw = p.get("thr") or {}
    if not isinstance(raw, dict):
        raise OpRefused("пороги отчёта — объект {ключ: значение}")
    for k, v in raw.items():
        if k not in base:
            raise OpRefused("неизвестный порог %s (есть: %s)" % (str(k)[:40], ", ".join(sorted(base))))
        thr[k] = _thr_value(k, v, base[k])
    over = {k: thr[k] for k in sorted(thr) if thr[k] != base[k]}
    return {"d1": d1, "days": days, "d0": d1 - datetime.timedelta(days=days - 1), "thr": thr, "over": over, "today": today}


def _thr_value(k, v, base):
    """Значение порога того же типа, что у исходника (int / float), больше нуля и не больше THR_MAX."""
    is_int = isinstance(base, int) and not isinstance(base, bool)
    try:
        if isinstance(v, bool):
            raise ValueError
        if is_int:
            x = int(v) if isinstance(v, int) else int(str(v).strip())
        else:
            x = float(v)
    except (TypeError, ValueError):
        raise OpRefused(("порог %s — целое больше нуля" if is_int else "порог %s — число больше нуля") % k)
    if not (0 < x <= THR_MAX) or x != x:
        raise OpRefused(("порог %s — целое больше нуля" if is_int else "порог %s — число больше нуля") % k)
    return x


# ---------------------------------------------------------------- журналы окна

def plan_files(root, gs, npc, d0, d1, archive=""):
    """Файлы журналов, которые прочитает исходник за окно, по его же правилам (ac_common.index_dir — любое имя на ГГГГММДД.txt; M6 / M7 /
    M12 — точные имена; OTP_Report — из LoginMngError, а за сутки без живого файла — из архива; Log_LevelUp — и сутки до окна: сессии через
    полночь) → ([(путь, байт)], [сутки ГГГГММДД без OTP_Report ни в журнале, ни в архиве])."""
    dates = sorted(d0 + datetime.timedelta(days=i) for i in range((d1 - d0).days + 1))
    want, prev = set(dates), set(dates) | {d0 - datetime.timedelta(days=1)}
    out = []

    def listing(d, days, prefix=""):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            return {}
        got = collections.defaultdict(list)
        for n in names:
            m = DATE_RX.search(n)
            if not m or not n.startswith(prefix):
                continue
            try:
                day = datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                continue
            if day in days:
                got[day].append(os.path.join(d, n))
        return got

    def add(path):
        try:
            out.append((path, os.stat(path).st_size))
        except OSError:
            pass
    for g in gs:
        for ch in GS_CHANNELS:
            for ps in listing(os.path.join(root, g, "Log", ch), prev if ch == "Log_LevelUp" else want).values():
                for x in ps:
                    add(x)
    lm = os.path.join(root, "LoginManager", "Log", "LoginMngError")
    live = listing(lm, want, "OTP_Report")
    arch = listing(archive, want, "OTP_Report") if archive else {}
    missing = []
    for d in dates:
        tag = d.strftime("%Y%m%d")
        for n in npc:
            p = os.path.join(root, n, "Error_Log", "%s_%s.txt" % (NPC_FILE, tag))
            if os.path.isfile(p):
                add(p)
        for k in ("LoginoutCheck", "LoginProc"):
            p = os.path.join(lm, "%s_%s.txt" % (k, tag))
            if os.path.isfile(p):
                add(p)
        ps = live.get(d) or arch.get(d) or []
        if not ps:
            missing.append(tag)
        for x in ps:
            add(x)
    return out, missing


def _mb(n):
    return "%.1f МБ" % (n / 1048576.0) if n >= 104858 else "%d КБ" % max(1, (n + 1023) // 1024) if n else "0 КБ"


# ---------------------------------------------------------------- прогон

def _cell(v):
    """Значение ячейки таблицы исходника → JSON."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return str(v)


def compute(q, user=None, with_db=True):
    """Посчитать отчёт исходником (ничего не пишет) → dict: meta, metrics (разбор), events {метрика: строки}, md (Markdown исходника).
    with_db=False — как «--no-db» исходника (только самотест: сверка с исходником без базы)."""
    root, gs, npc, archive = stack()
    files, otp_missing = plan_files(root, gs, npc, q["d0"], q["d1"], archive)
    nbytes = sum(b for _, b in files)
    src = load(root, gs, npc, archive)
    C, L, R = src.C, src.L, src.R
    for k, v in q["thr"].items():
        C.THR[k] = type(C.THR[k])(v)
    ctx = C.Ctx(root, q["d0"], q["d1"], "", C.DEFAULT_OWNER_RE, list(gs), list(npc), archive, bool(with_db))
    t0 = time.time()
    try:
        ms = R.build(C, L, ctx)
    finally:
        src.close()
    elapsed = time.time() - t0
    md = R.render(C, ctx, ms, {"elapsed": elapsed})
    metrics, events = [], {}
    tot = collections.Counter()
    for m in ms:
        evs = sorted(m.events, key=lambda e: e.ts)
        rows = [[C.fmt_ts(e.ts), e.src, e.subject, e.kind, e.detail, e.file, e.ip] for e in evs[-EVENTS_KEEP:]]
        events[m.mid] = rows
        flags = [[s, t, bool(ctx.is_owner(s))] for s, t in m.flags]
        bg = collections.Counter(s for s, _t, o in flags if o)
        metrics.append({"mid": m.mid, "title": m.title, "source": m.source, "formula": m.formula, "status": m.status,
                        "notes": list(m.notes), "summary": [_cell(x) for x in R.summary_row(C, ctx, m)], "flags": flags,
                        "bg_top": [[s, n] for s, n in bg.most_common(6)],
                        "tables": [[name, [_cell(x) for x in hd], [[_cell(x) for x in r] for r in rws]] for name, hd, rws in m.tables],
                        "events_total": len(evs), "events_kept": len(rows), "last": [r[:4] + [r[4][:90]] for r in rows[-8:]]})
        tot["out"] += sum(1 for f in flags if not f[2])
        tot["bg"] += sum(1 for f in flags if f[2])
        tot["err"] += m.status == "ошибка"
        tot["nodata"] += m.status == "нет данных"
    meta = {"day_from": q["d0"].strftime("%Y%m%d"), "day_to": q["d1"].strftime("%Y%m%d"), "days": q["days"], "root": ctx.root,
            "servers": list(ctx.gs_servers), "npc": list(ctx.npc_servers), "owner_re": ctx.owner.pattern, "elapsed_ms": int(elapsed * 1000),
            "log_files": len(files), "log_bytes": nbytes, "opened": src.guard.opened, "queries": src.queries(), "code_md5": code_md5(src.dir),
            "otp_archive": archive, "otp_missing": otp_missing, "thr": q["thr"], "thr_over": q["over"], "service_limit": bool(q.get("service"))}
    return {"meta": meta, "metrics": metrics, "events": events, "md": md, "totals": dict(tot)}


def save(rep, by, via, job_id=None):
    """Записать прогон в AsdaAdmin adm.AcDaily (одна строка) → номер. Время made_local — часы этой машины (службы)."""
    m = rep["meta"]
    cn = db.admin()
    try:
        cur = cn.cursor()
        cur.execute("SET NOCOUNT ON; INSERT adm.AcDaily (day_from, day_to, days, made_local, taken_by, via, job_id, elapsed_ms, metrics_n, flags_out, "
                    "flags_bg, errors_n, nodata_n, log_files, log_bytes, code_md5, thr_json, thr_over_json, summary_json, events_json, report_md) "
                    "OUTPUT INSERTED.id VALUES (?, ?, ?, SYSDATETIME(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    m["day_from"], m["day_to"], m["days"], (by or "")[:32], (via or "")[:8], job_id, m["elapsed_ms"], len(rep["metrics"]),
                    rep["totals"].get("out", 0), rep["totals"].get("bg", 0), rep["totals"].get("err", 0), rep["totals"].get("nodata", 0),
                    m["log_files"], m["log_bytes"], m["code_md5"], json.dumps(m["thr"], ensure_ascii=False, sort_keys=True),
                    json.dumps(m["thr_over"], ensure_ascii=False, sort_keys=True),
                    json.dumps({"meta": m, "metrics": rep["metrics"]}, ensure_ascii=False),
                    json.dumps(rep["events"], ensure_ascii=False), rep["md"])
        return int(cur.fetchone()[0])
    finally:
        cn.close()


def purge():
    """★ ревизия 56 Н-4: срок хранения — процедура adm.AcDailyPurge (у asda_admin только EXECUTE, DELETE запрещён): прогоны службы
    хранятся KEEP_SERVICE_DAYS суток, ручные и задания — KEEP_MANUAL_DAYS → {sched, manual} удалено."""
    r = _rows("SET NOCOUNT ON; DECLARE @s INT, @m INT; EXEC adm.AcDailyPurge @Sched = @s OUTPUT, @Manual = @m OUTPUT; SELECT @s AS s, @m AS m")
    return {"sched": int(r[0]["s"] or 0), "manual": int(r[0]["m"] or 0)}


def storage():
    """Сводка размера adm.AcDaily по пути (служба / вручную) → [{via, rows, bytes, oldest}]."""
    return _rows("SELECT CASE WHEN via = 'sched' THEN 'sched' ELSE 'manual' END AS kind, COUNT(*) AS n, "
                 "SUM(CAST(DATALENGTH(summary_json) + DATALENGTH(events_json) + DATALENGTH(report_md) AS BIGINT)) AS bytes, MIN(day_to) AS oldest "
                 "FROM adm.AcDaily GROUP BY CASE WHEN via = 'sched' THEN 'sched' ELSE 'manual' END ORDER BY kind")


def _rows(sql, params=()):
    cn = db.admin()
    try:
        return db.admin_rows(cn, sql, params)
    finally:
        cn.close()


def runs_last_hour(login):
    """Ручных прогонов пользователя (не служба) за последние 60 минут — по журналу adm.AcDaily (переживает перезапуск службы)."""
    return int(_rows("SELECT COUNT(*) AS n FROM adm.AcDaily WHERE taken_by = ? AND via <> 'sched' AND made_utc >= DATEADD(MINUTE, -60, SYSUTCDATETIME())",
                     ((login or "")[:32],))[0]["n"])


def missing_days(today, n=BACKFILL_DAYS):
    """★ ревизия 56 Н-3: сутки от позавчера на n назад (вчера считает DAILY), за которые нет отчёта на одни сутки → [ГГГГММДД], старые первыми."""
    days = [(today - datetime.timedelta(days=k)).strftime("%Y%m%d") for k in range(n + 1, 1, -1)]
    # ★ ревизия 57 (мелочь 5): только НОЧНЫЕ отчёты (via sched, хранятся 400 суток) — ручной (90 суток) ночной не заменяет
    have = {r["day_to"] for r in _rows("SELECT DISTINCT day_to FROM adm.AcDaily WHERE days = 1 AND via = 'sched' AND day_to >= ? AND day_to <= ?",
                                       (days[0], days[-1]))}
    return [d for d in days if d not in have]


def _server_only():
    if not STACK_OVERRIDE and not config.get().on_server:
        raise OpRefused("суточный отчёт считает служба на сервере: журналы стойки читаются там локально (без шары) — запуск из панели или "
                        "заданием планировщика (jobs add ac.daily)")


def _budget(ctx):
    if ctx.via == "sched":
        return
    try:
        n = runs_last_hour(ctx.login)
    except db.DbError as ex:
        raise OpRefused("журнал суточных отчётов не прочитан: %s" % ex)
    if n >= RUNS_PER_HOUR:
        raise OpRefused("суточный отчёт вручную — не больше %d раз в час на пользователя, подождите" % RUNS_PER_HOUR)


def _job_id(ctx, p):
    """★ ревизия 56 (мелочь 2): номер задания — только от планировщика заданий (via job) и только целое ≥ 1."""
    v = (p or {}).get("job_id")
    if v is None:
        return None
    if ctx.via != "job":
        raise OpRefused("номер задания суточного отчёта передаёт только планировщик заданий")
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise OpRefused("номер задания суточного отчёта — целое от 1")
    return v


def _limit(ctx):
    """Предел байт журналов окна: служба (ночной прогон, досчёт) — SERVICE_BYTES_MAX, люди — бюджет чтения журналов logs.BYTES_USER_MIN."""
    return SERVICE_BYTES_MAX if ctx.via == "sched" else logs.BYTES_USER_MIN


def _lock():
    """★ ревизия 56 (мелочь 3): межпроцессный замок «один прогон» (sp_getapplock Exclusive, Session) → соединение | None (занят)."""
    cn = db.admin()
    try:
        r = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
                              "@LockOwner = 'Session', @LockTimeout = 0; SELECT @r AS r", (LOCK_NAME,))
        if r and int(r[0]["r"]) >= 0:
            return cn
    except Exception:
        cn.close()
        raise
    cn.close()
    return None


def _unlock(cn):
    try:
        db.admin_rows(cn, "SET NOCOUNT ON; EXEC sp_releaseapplock @Resource = ?, @LockOwner = 'Session'; SELECT 1 AS ok", (LOCK_NAME,))
    except Exception:
        pass
    try:
        cn.close()
    except Exception:
        pass


# ---------------------------------------------------------------- просмотр

LIST_COLS = ("id, day_from, day_to, days, made_local, taken_by, via, job_id, elapsed_ms, metrics_n, flags_out, flags_bg, errors_n, nodata_n, "
             "log_files, log_bytes, code_md5, thr_over_json")


def _pub(r):
    """Строка списка прогонов → dict ответа."""
    return {"id": r["id"], "day_from": r["day_from"], "day_to": r["day_to"], "days": r["days"], "made_local": r["made_local"], "by": r["taken_by"],
            "via": r["via"], "job_id": r["job_id"], "elapsed_ms": r["elapsed_ms"], "metrics": r["metrics_n"], "flags_out": r["flags_out"],
            "flags_bg": r["flags_bg"], "errors": r["errors_n"], "nodata": r["nodata_n"], "log_files": r["log_files"], "log_bytes": r["log_bytes"],
            "code_md5": r["code_md5"], "thr_over": json.loads(r["thr_over_json"] or "{}")}


def _int(v, msg, lo, hi):
    s = str(v if v is not None else "").strip()
    if not s.isdigit() or not lo <= int(s) <= hi:
        raise OpRefused(msg)
    return int(s)


def reports(q=None):
    """Прогоны (новые сверху, не больше LIST_MAX); ?day=ГГГГММДД — только с этими последними сутками окна; сводка размера и сроков."""
    q = q or {}
    if q.get("day"):
        day = _day(q["day"], "day").strftime("%Y%m%d")        # ★ ревизия 56 (мелочь 5): проверяется и уходит в запрос одно значение
        rows = _rows("SELECT TOP (%d) %s FROM adm.AcDaily WHERE day_to = ? ORDER BY made_local DESC, id DESC" % (LIST_MAX, LIST_COLS), (day,))
    else:
        rows = _rows("SELECT TOP (%d) %s FROM adm.AcDaily ORDER BY made_local DESC, id DESC" % (LIST_MAX, LIST_COLS))
    src_err = None
    try:
        dflt = defaults()
    except (OSError, acsrc.SourceError) as ex:            # ★ ревизия 57 (мелочь 7): не молча — пометка на экране
        dflt, src_err = {}, "исходник отчёта не прошёл проверку: %s" % ex
    try:
        st = storage()
    except db.DbError:
        st = None
    return {"reports": [_pub(r) for r in rows], "run_at": RUN_AT.strftime("%H:%M"), "defaults": dflt, "days_max": DAYS_MAX,
            "runs_per_hour": RUNS_PER_HOUR, "on_server": bool(config.get().on_server or STACK_OVERRIDE), "storage": st,
            "keep": {"sched": KEEP_SERVICE_DAYS, "manual": KEEP_MANUAL_DAYS}, "errors": [src_err] if src_err else []}


def _pick(q, cols):
    """Прогон по ?id=N или последний за ?day=ГГГГММДД (окно в одни сутки, иначе любой с такими последними сутками) → строка или отказ."""
    if q.get("id") not in (None, ""):
        rid = _int(q["id"], "номер суточного отчёта — целое от 1", 1, 2 ** 31 - 1)
        r = _rows("SELECT %s FROM adm.AcDaily WHERE id = ?" % cols, (rid,))
        if not r:
            raise OpRefused("суточного отчёта №%d нет" % rid)
        return r[0]
    if q.get("day") in (None, ""):
        r = _rows("SELECT TOP (1) %s FROM adm.AcDaily ORDER BY made_local DESC, id DESC" % cols)
        if not r:
            raise OpRefused("суточных отчётов ещё нет (служба считает их сама в %s)" % RUN_AT.strftime("%H:%M"))
        return r[0]
    day = _day(q["day"], "day").strftime("%Y%m%d")
    r = _rows("SELECT TOP (1) %s FROM adm.AcDaily WHERE day_to = ? ORDER BY CASE WHEN days = 1 THEN 0 ELSE 1 END, made_local DESC, id DESC" % cols, (day,))
    if not r:
        raise OpRefused("суточного отчёта за %s нет" % day)
    return r[0]


def report(q):
    """Отчёт: шапка, итог по метрикам (как «Итог» исходника), флаги вне владельца и фон, заметки, таблицы, последние события."""
    r = _pick(q or {}, LIST_COLS + ", summary_json")
    s = json.loads(r["summary_json"])
    out = _pub(r)
    errs = []
    try:
        now = code_md5()
    except (OSError, acsrc.SourceError) as ex:            # ★ ревизия 57 (мелочь 7): пометка на экране
        now = None
        errs.append("исходник отчёта не прошёл проверку: %s" % ex)
    out.update({"meta": s["meta"], "metrics": s["metrics"], "code_now": now, "errors": errs})
    return out


def events(q):
    """События одной метрики прогона (?id=&metric=&page=&size=) — то, что исходник пишет в CSV."""
    q = q or {}
    mid = str(q.get("metric") or "")
    if not re.fullmatch(r"[A-Za-z0-9]{1,8}", mid):
        raise OpRefused("метрика отчёта — имя вида M1, M12o, ACJ")
    size = _int(q.get("size") or PAGE_DEF, "строк на странице событий — от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница событий — целое от 1", 1, 10 ** 6)
    r = _pick(q, "id, events_json")
    ev = json.loads(r["events_json"]).get(mid)
    if ev is None:
        raise OpRefused("метрики %s в отчёте №%d нет" % (mid, r["id"]))
    pages = max(1, (len(ev) + size - 1) // size)
    page = min(page, pages)
    return {"id": r["id"], "metric": mid, "total": len(ev), "page": page, "pages": pages, "size": size,
            "rows": ev[(page - 1) * size: page * size]}


def markdown(q):
    """Markdown исходника этого прогона как есть."""
    r = _pick(q or {}, "id, report_md")
    return {"id": r["id"], "md": r["report_md"]}


# ---------------------------------------------------------------- операция

@register
class AcDaily(Operation):
    name, title, perm, reversible = "ac.daily", "Античит: суточный отчёт", "ac.daily_run", False
    schedule_runner = "service"          # журналы стойки читаются локально — считает только служба на сервере (сама раз в сутки — core/sched)
    schedule_repeat_days = 366           # подтверждений и второго фактора нет: повтор действует год (как снимок золота)

    def target(self, p):
        d = (p or {}).get("date")
        return "acdaily:%s" % (d if d else "вчера")

    def schedule_check(self, ctx, p):
        """Параметры задания (без даты — «вчера» на момент запуска; days, thr — как у ручного прогона) → проверенные параметры."""
        return check_params(p)

    def _plan(self, ctx, p):
        q = check_params(p)
        _job_id(ctx, p)
        _server_only()
        q["service"] = ctx.via == "sched"
        root, gs, npc, archive = stack()
        files, missing = plan_files(root, gs, npc, q["d0"], q["d1"], archive)
        nbytes = sum(b for _, b in files)
        lim = _limit(ctx)
        if nbytes > lim:
            raise OpRefused("журналов в окне %s — больше предела %d МБ, сократите окно" % (_mb(nbytes), lim // 1048576))
        return q, files, nbytes, missing

    def preview(self, ctx, p):
        q, files, nbytes, missing = self._plan(ctx, p)
        _budget(ctx)
        warn = ["пишется только база панели AsdaAdmin (adm.AcDaily), игровые базы и журналы стойки только читаются"]
        if q["d1"] >= q["today"]:
            warn.append("последние сутки окна ещё идут — отчёт за них неполный")
        if q["over"]:
            warn.append("пороги не прежние: %s" % ", ".join("%s=%s" % kv for kv in sorted(q["over"].items())))
        if missing:
            warn.append("за сутки %s нет OTP_Report ни в журнале LoginManager, ни в архиве: M8 / M12 / M12o без записей входа" % ", ".join(missing))
        win = q["d1"].strftime("%Y%m%d") if q["days"] == 1 else "%s–%s" % (q["d0"].strftime("%Y%m%d"), q["d1"].strftime("%Y%m%d"))
        return {"text": "суточный отчёт античита за %s: журналов стойки %d (%s)" % (win, len(files), _mb(nbytes)), "warnings": warn,
                "files": len(files), "bytes": nbytes, "otp_missing": missing}

    def apply(self, ctx, p, prev):
        if not _RUN.acquire(blocking=False):
            raise OpRefused("суточный отчёт уже считается — повторите через минуту")
        try:
            q, files, nbytes, _missing = self._plan(ctx, p)
            lk = _lock()
            if lk is None:
                raise OpRefused("суточный отчёт уже считается — повторите через минуту")
            try:
                _budget(ctx)
                if ctx.via != "sched":
                    logs.charge(ctx.login, nbytes)
                rep = compute(q, ctx.login)
                rid = save(rep, ctx.login, ctx.via, _job_id(ctx, p))
            finally:
                _unlock(lk)
        finally:
            _RUN.release()
        purged = None
        if ctx.via == "sched":
            try:
                purged = purge()
            except db.DbError as ex:
                print("суточный отчёт: срок хранения не применён (%s)" % str(ex)[:200])
        t = rep["totals"]
        m = rep["meta"]
        return {"before": None, "after": {"id": rid, "day_from": m["day_from"], "day_to": m["day_to"], "flags_out": t.get("out", 0),
                                          "flags_bg": t.get("bg", 0), "errors": t.get("err", 0), "nodata": t.get("nodata", 0),
                                          "otp_missing": m["otp_missing"], "purged": purged},
                "message": "суточный отчёт античита №%d за %s: флагов вне владельца %d, фон владельца %d, метрик с ошибкой %d, без данных %d" % (
                    rid, m["day_to"] if m["days"] == 1 else "%s–%s" % (m["day_from"], m["day_to"]), t.get("out", 0), t.get("bg", 0),
                    t.get("err", 0), t.get("nodata", 0))}
