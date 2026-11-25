# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
r"""dbbackup.py — бэкапы баз SQL Server (шаг А5.7 волны «Живое управление», план §4 Д, §5.1; 21.11.2026; ★ ревизия 47 — 21.11.2026).

ЧТО ДЕЛАЕТ. Полный бэкап базы из белого списка (AsdaAdmin.adm.dbbackup_db: Joy1, AsdaStoryOp, joylog1, AsdaStoryLogin, AsdaAdmin) в папку
  панели на сервере (adm.dbbackup_cfg, @@ASTORY_SERVER_ROOT@@\DbBackup): BACKUP DATABASE … WITH COPY_ONLY, CHECKSUM (COPY_ONLY — чужую цепочку бэкапов не
  трогает; сжатия у Express нет — ошибка 1844, проверено на LocalDB), затем RESTORE VERIFYONLY … WITH CHECKSUM. Всё это — внутри подписанной
  процедуры adm.DbBackupRun (sql/adminc_16_dbbackup.sql): у логина asda_admin своих прав на BACKUP нет, sysadmin ни у кого из служебных логинов
  нет. После бэкапа служба снимает длину и md5 файла и число строк таблиц (сверка стенда) и убирает старые бэкапы панели (ротация).
ОДИН ЗА РАЗ (★ ревизия 47 С-1): блокировка приложения adm.dbbackup на сеанс SQL (держит DbBackupRun / DbBackupVerify до итога; обрыв сеанса
  снимает её сама). Строка running при свободной блокировке — зависшая: её снимает следующий бэкап (предпросмотр не отказывает — В-1) или
  вручную db.release (владелец; заодно — зависшие задания db.backup / db.verify в adm.job).
ИСПОЛНИТЕЛЬ — СЛУЖБА на сервере (schedule_runner = service): SQL Server и файл бэкапа — на сервере, служба работает всегда (ПК владельца может
  быть выключен), SSH не нужен; по кнопке из браузера операция ставит задание службы на «сейчас» (adm.job, начнётся в течение минуты) — ответ
  браузеру не ждёт долгого бэкапа, итог — в журнале и в карточке. Долгие операции (schedule_long — бэкап, перепроверка) служба исполняет
  ОТДЕЛЬНЫМ потоком (core/sched.py, ★ ревизия 47 С-2): объявления и режим обслуживания не ждут бэкапа и не становятся «пропущенными».
  По расписанию — job.add с повтором daily / weekly (срок повтора — год, schedule_repeat_days). Консоль ПК (db backup) делает бэкап сразу.
РОТАЦИЯ (prune_plan; ★ ревизия 47 С-3): удаляются ТОЛЬКО файлы строк adm.dbbackup (сделанные панелью), лежащие прямо в папке панели и с
  именем панели (<база>_<ГГГГММДД>_<ЧЧММСС>_<номер>.bak, номер = строка). Никогда — KEEP_MIN последних проверенных бэкапов базы, последний
  проверенный бэкап каждой недели за LONG_WEEKS недель и каждого месяца за LONG_MONTHS месяцев. Автоматическая уборка после бэкапа — ТОЛЬКО
  по возрасту (старше KEEP_DAYS), поэтому частые нажатия «бэкап» ничего не вытесняют; правило «не больше KEEP_MAX на базу» — только ручная
  уборка владельца db.prune. Неудачные — старше FAILED_KEEP_DAYS. Нет ни одного проверенного — готовые не удаляются вовсе. Чужие бэкапы
  (H:\SQLBackup_*, история msdb) панель только показывает.
ВОССТАНОВЛЕНИЕ — только на стенд LocalDB ПК (domains/dbstand.py, операция db.restore_stand). Восстановление на живой сервер панель не делает
  и кнопки не даёт: операция db.restore всегда отказывает с объяснением (LIVE_RESTORE_REFUSAL).
Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import json
import ntpath
import os
import re
import uuid

from core import config, db, jobs
from core.ops import Operation, OpRefused, register

KEEP_DAYS = 30                 # ★ ревизия 47 С-3: готовые бэкапы панели старше — в автоуборку (кроме защищённых); полный набор баз ~170 МБ
KEEP_MIN = 3                   # столько последних ПРОВЕРЕННЫХ бэкапов базы не удаляются никогда (в том числе последний проверенный)
LONG_WEEKS = 8                 # ★ ревизия 47 С-3: последний проверенный бэкап каждой недели — столько недель не удаляется
LONG_MONTHS = 12               # ★ ревизия 47 С-3: последний проверенный бэкап каждого месяца — столько месяцев не удаляется
KEEP_MAX = 30                  # ручная уборка владельца: больше готовых на базу — лишние старые в уборку (кроме защищённых)
FAILED_KEEP_DAYS = 2           # неудачные (обрывки файла) — через столько дней
WARN_HOURS = 48                # последнему проверенному бэкапу базы больше — предупреждение в «Состоянии»
BACKUP_TIMEOUT_S = 4 * 3600    # предел ожидания одной базы (BACKUP + VERIFYONLY)
VERIFY_TIMEOUT_S = 2 * 3600
NAME_RX = re.compile(r"^(?P<db>[A-Za-z0-9_]+)_(?P<ts>\d{8}_\d{6})_(?P<id>\d+)\.bak$")
FOLDER_RX = re.compile(r"^[A-Za-z]:\\[^'\"`$;&|<>*?\r\n]+$")
LIVE_RESTORE_REFUSAL = ("восстановление на живой сервер панель не делает и кнопки не даёт: RESTORE поверх живой базы сотрёт всё, что игроки "
                        "сделали после бэкапа, и требует остановленной стойки и монопольного доступа — это решение и ручная работа владельца "
                        "(sqlcmd -E на сервере). Проверить бэкап можно восстановлением на стенд LocalDB ПК: db stand --id N")
CONFIRM_PRUNE = "prune"
CONFIRM_RELEASE = "release"
BUSY_TEXT = "уже идёт бэкап или проверка панели (база %s, №%s) — дождитесь итога"
_CODE_TAIL = re.compile(r"\s\(50[0-9]{3}\)$")          # ★ ревизия 47 Н-1: код THROW панели в конце текста — не часть сообщения

# подмены самотеста (None — настоящие): FILE_INFO(path) → (байты, md5); DELETE_FILE(path) → True (удалён) / False (файла не было);
# COUNTS(db) → {таблица: строк}
FILE_INFO = None
DELETE_FILE = None
COUNTS = None


class BackupFailed(Exception):
    """Бэкап одной или нескольких баз не удался (текст — по базам)."""


def utc_now():
    return jobs.utc_now()


def _call(sql, params=(), timeout=60, unlock=False):
    """Запрос к AsdaAdmin, длинный предел → (строки первого набора с описанием, текст ошибки | None). Ошибку SQL не бросает (процедура
    бэкапа после ошибки VERIFYONLY ещё отдаёт свою строку, а драйвер сообщает ошибку раньше неё). ★ ревизия 47 С-1: unlock — после ошибки на
    ТОМ ЖЕ соединении снять свою блокировку adm.dbbackup (обрыв запроса посреди процедуры оставил бы её у соединения, ушедшего в пул ODBC)."""
    import pyodbc
    cn = db.admin()
    rows, err = [], None
    try:
        cn.timeout = timeout
        cur = cn.cursor()
        try:
            cur.execute(sql, *params) if params else cur.execute(sql)
            while True:
                if cur.description and not rows:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                if not cur.nextset():
                    break
        except pyodbc.Error as ex:
            err = _reason(ex)
            if unlock:
                try:
                    cn.timeout = 60
                    cn.cursor().execute("EXEC adm.DbBackupUnlock")
                except pyodbc.Error:
                    pass
    finally:
        cn.close()
    return rows, err


def _reason(ex):
    """Все сообщения сервера из ошибки драйвера (без строки подключения, без кода THROW панели): «текст (код) | …»."""
    s = str(ex.args[1] if len(ex.args) > 1 else ex)
    parts = []
    for p in re.split(r"\s*;\s*(?=\[)", s):
        p = _CODE_TAIL.sub("", re.sub(r"\[[^\]]*\]", "", p).split("(SQL")[0].strip())
        if p and p not in parts:
            parts.append(p)
    return " | ".join(parts)[:1500] or "ошибка SQL"


def _rows(sql, params=()):
    cn = db.admin()
    try:
        return db.admin_rows(cn, sql, params)
    finally:
        cn.close()


def allowed():
    """Базы, которые панель бэкапит (adm.dbbackup_db) → [имя]."""
    return [r["name"] for r in _rows("SELECT name FROM adm.dbbackup_db ORDER BY name")]


def folder():
    """Папка бэкапов панели на сервере (adm.dbbackup_cfg)."""
    r = _rows("SELECT folder, free_factor, free_reserve_mb FROM adm.dbbackup_cfg WHERE id = 1")
    if not r:
        raise OpRefused("настройки бэкапов панели (adm.dbbackup_cfg) не прочитаны — бэкап не начат")
    return r[0]


def busy():
    """★ ревизия 47 В-1 / С-1: идёт ли бэкап панели на самом деле → {lock_held, server_backup, running_rows, running_id}. Не прочитано — OpRefused."""
    rows, err = _call("SET NOCOUNT ON; EXEC adm.DbBackupBusy")
    if err or not rows:
        raise OpRefused("состояние бэкапа панели не прочитано: %s" % (err or "пусто"))
    r = rows[0]
    return {"lock_held": bool(r["lock_held"]), "server_backup": bool(r["server_backup"]), "running_rows": int(r["running_rows"] or 0),
            "running_id": r["running_id"]}


def _long_ops():
    from core import ops
    return [n for n, o in ops.REGISTRY.items() if getattr(o, "schedule_long", False)]


def stale_jobs(b=None):
    """★ ревизия 47 В-1: задания db.* в «идёт», хотя бэкап панели не идёт (служба упала посреди) → [строки adm.job]."""
    b = b or busy()
    if b["lock_held"]:
        return []
    names = [n for n in _long_ops() if n.startswith("db.")]
    if not names:
        return []
    rows = _rows("SELECT id, op, started_at, host FROM adm.job WHERE status = 'running' AND op IN (%s) ORDER BY id" % ",".join("?" * len(names)),
                 tuple(names))
    # ★ ревизия 48 Н-2: блокировка adm.dbbackup свободна и между базами, и пока служба снимает md5 / строки / уборку — живое задание узнаётся
    #   по applock исполнителя (core/jobs.hold_job держит её всё время прогона), а не по блокировке бэкапа
    return [r for r in rows if not jobs.job_alive(r["id"])]


def panel_rows(limit=60, dbname=None):
    """Строки adm.dbbackup (новые сверху; без JSON строк и итога стенда)."""
    where, params = ("WHERE db = ? ", (dbname,)) if dbname else ("", ())
    return _rows("SELECT TOP (%d) id, db, file_path, status, verified, verified_at, started_at, finished_at, by_login, job_id, data_bytes, "
                 "backup_bytes, file_bytes, md5, message, stand_at, stand_ok, deleted_at, deleted_by, deleted_why FROM adm.dbbackup %sORDER BY id DESC"
                 % (max(1, min(int(limit), 500)), where), params)


def get(bid):
    r = _rows("SELECT * FROM adm.dbbackup WHERE id = ?", (int(bid),))
    return r[0] if r else None


def safe_file(fold, row):
    """Путь файла строки — прямо в папке панели и с именем панели этой строки → путь; иначе None (такой файл панель не трогает)."""
    p = str(row.get("file_path") or "")
    if not p or not FOLDER_RX.match(str(fold or "")) or not FOLDER_RX.match(p):
        return None
    if ntpath.normcase(ntpath.dirname(ntpath.normpath(p))) != ntpath.normcase(ntpath.normpath(str(fold).rstrip("\\"))):
        return None
    m = NAME_RX.match(ntpath.basename(p))
    if not m or m.group("db").lower() != str(row.get("db") or "").lower() or int(m.group("id")) != int(row["id"]):
        return None
    return p


def _when(r):
    w = r.get("finished_at") or r.get("started_at")
    return w if isinstance(w, datetime.datetime) else None


def long_keep(verified, now):
    """★ ревизия 47 С-3: долгие копии — последний проверенный бэкап каждой недели за LONG_WEEKS и каждого месяца за LONG_MONTHS → {id}."""
    keep, weeks, months = set(), set(), set()
    for r in verified:                                     # новые сначала
        w = _when(r)
        if w is None:
            continue
        wk, mo = w.isocalendar()[:2], (w.year, w.month)
        if wk not in weeks and now - w <= datetime.timedelta(weeks=LONG_WEEKS):
            weeks.add(wk)
            keep.add(int(r["id"]))
        if mo not in months and (now.year - w.year) * 12 + now.month - w.month < LONG_MONTHS:
            months.add(mo)
            keep.add(int(r["id"]))
    return keep


def prune_plan(rows, now, manual=False, pinned=()):
    """Что убрать из бэкапов ОДНОЙ базы → [(строка, причина)]. rows — строки adm.dbbackup этой базы (любой порядок). Автоуборка (после бэкапа) —
    только по возрасту; manual (db.prune владельца) — ещё и «сверх KEEP_MAX». Защищены всегда: KEEP_MIN последних проверенных, долгие копии и
    ★ ревизия 48 Н-4 — pinned: бэкапы, на которые ссылается журнал удаления служебных копий (adm.bakdrop_log.backup_id; из них копию
    возвращают через стенд — без бэкапа строки удалённой таблицы потеряны)."""
    rows = sorted([r for r in rows if r["status"] in ("done", "failed")], key=lambda r: -int(r["id"]))
    verified = [r for r in rows if r["status"] == "done" and bool(r.get("verified"))]
    keep = {int(r["id"]) for r in verified[:KEEP_MIN]} | long_keep(verified, now) | {int(x) for x in pinned}
    out, done_i = [], 0
    for r in rows:
        w = _when(r)
        age = (now - w) if w else datetime.timedelta(0)
        if int(r["id"]) in keep:
            if r["status"] == "done":
                done_i += 1
            continue
        if r["status"] == "failed":
            if age > datetime.timedelta(days=FAILED_KEEP_DAYS):
                out.append((r, "неудачный, старше %d дн." % FAILED_KEEP_DAYS))
            continue
        done_i += 1
        if not verified:
            continue                                    # ни одного проверенного — готовые не удаляем вовсе
        if age > datetime.timedelta(days=KEEP_DAYS):
            out.append((r, "старше %d дн." % KEEP_DAYS))
        elif manual and done_i > KEEP_MAX:
            out.append((r, "сверх %d бэкапов базы" % KEEP_MAX))
    return out


def _on_server():
    return config.get().on_server


def _file_info(path):
    """(длина, md5) файла бэкапа на сервере: служба — сама, консоль ПК — PowerShell по SSH. Путь — уже проверенный safe_file."""
    if FILE_INFO:
        return FILE_INFO(path)
    if _on_server():
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4 << 20), b""):
                h.update(chunk)
        return os.path.getsize(path), h.hexdigest()
    from core import hostshell
    out = hostshell.powershell("$f = Get-Item -LiteralPath '%s' -ErrorAction Stop; $h = Get-FileHash -LiteralPath $f.FullName -Algorithm MD5; "
                               "'INFO|' + $f.Length + '|' + $h.Hash.ToLower()" % path, timeout=3600)
    a = [l for l in out.splitlines() if l.startswith("INFO|")][-1].split("|")
    return int(a[1]), a[2]


def _delete_file(path):
    """Удалить файл бэкапа на сервере → True; файла не было → False. Путь — уже проверенный safe_file."""
    if DELETE_FILE:
        return DELETE_FILE(path)
    if _on_server():
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True
    from core import hostshell
    out = hostshell.powershell("if (Test-Path -LiteralPath '%s') { Remove-Item -LiteralPath '%s' -Force -ErrorAction Stop; 'DEL|1' } else { 'DEL|0' }"
                               % (path, path), timeout=120)
    return "DEL|1" in out


COUNT_SQL = ("SELECT s.name + '.' + t.name AS t, SUM(p.rows) AS n FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
             "JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1) WHERE t.is_ms_shipped = 0 GROUP BY s.name, t.name")


def counts(dbname):
    """Строк в таблицах базы (sys.partitions; видны таблицы, которые читает asda_admin) → {схема.таблица: строк}."""
    if COUNTS:
        return COUNTS(dbname)
    key = dbname.lower()
    if key in db.GAME_DBS:
        with db.GameReader(key) as r:
            rows = r.rows(COUNT_SQL)
    else:
        rows = _rows(COUNT_SQL)
    return {str(x["t"]): int(x["n"] or 0) for x in rows}


def backup_one(dbname, by, job_id=None):
    """Бэкап одной базы процедурой → dict(db, id, status, verified, file, bytes, md5, message, error, pruned, warnings).
    ★ ревизия 47 Н-4: своя строка ищется по метке вызова (run_tag), не по часам; нет строки — отказ процедуры до начала (ничего не снимаем)."""
    tag = str(uuid.uuid4())
    rows, err = _call("SET NOCOUNT ON; EXEC adm.DbBackupRun @db = ?, @by = ?, @job = ?, @tag = ?", (dbname, by[:64], job_id, tag),
                      BACKUP_TIMEOUT_S, unlock=True)
    r2 = _rows("SELECT TOP 1 * FROM adm.dbbackup WHERE run_tag = ? ORDER BY id DESC", (tag,))
    row = r2[0] if r2 else (rows[0] if rows else None)
    if err and row and row["status"] == "running":
        _call("EXEC adm.DbBackupAbort @msg = ?", ("сбой: " + err[:1900],))     # ★ С-1: снимет, только если блокировку никто не держит
        row = get(row["id"]) or row
    out = {"db": dbname, "id": row and row["id"], "status": row["status"] if row else "refused", "verified": row and row.get("verified"),
           "file": row and row.get("file_path"), "bytes": row and row.get("backup_bytes"), "md5": None, "message": row and row.get("message"),
           "error": err, "pruned": [], "warnings": []}
    if not row or row["status"] != "done":
        return out
    try:
        p = safe_file(folder()["folder"], row)              # ★ ревизия 47 (мелочь 2): путь в PowerShell — только проверенный
        if not p:
            raise OpRefused("путь файла не в папке панели или имя не панели — файл не трогаю")
        size, md5 = _file_info(p)
        try:
            cnt = json.dumps(counts(dbname), ensure_ascii=False, separators=(",", ":"))
        except Exception as ex:                       # снимок строк — для сверки стенда; без него бэкап остаётся годным
            cnt = None
            out["warnings"].append("число строк таблиц не снято (%s) — стенд сверит только CHECKDB" % ex.__class__.__name__)
        _rows("SET NOCOUNT ON; EXEC adm.DbBackupMark @id = ?, @md5 = ?, @bytes = ?, @counts = ?", (int(row["id"]), md5, size, cnt))
        out["md5"], out["file_bytes"] = md5, size
    except Exception as ex:
        out["warnings"].append("длина и md5 файла не сняты (%s: %s) — стенд посчитает md5 на сервере перед скачиванием" % (ex.__class__.__name__, str(ex)[:200]))
    if out["verified"]:
        try:
            out["pruned"] = [x["id"] for x in prune(dbname, by)["deleted"]]
        except Exception as ex:
            out["warnings"].append("уборка старых бэкапов не выполнена (%s: %s)" % (ex.__class__.__name__, str(ex)[:200]))
    return out


PINNED_SQL = ("IF OBJECT_ID(N'adm.bakdrop_log') IS NOT NULL SELECT DISTINCT backup_id AS id FROM adm.bakdrop_log "
              "ELSE SELECT CAST(NULL AS INT) AS id WHERE 1 = 0")


def pinned():
    """★ ревизия 48 Н-4: номера бэкапов из журнала удаления копий → {id}. Не прочитано — исключение (уборка тогда не идёт: «не прочитано» ≠ «нет»)."""
    return {int(r["id"]) for r in _rows(PINNED_SQL)}


def prune(dbname, by, dry=False, manual=False):
    """Уборка бэкапов панели одной базы → {"deleted": [{id, file, why, existed}], "skipped": [{id, why}]}."""
    cf = folder()
    pin = pinned()
    rows = _rows("SELECT id, db, file_path, status, verified, started_at, finished_at FROM adm.dbbackup WHERE db = ? AND status IN ('done','failed')",
                 (dbname,))
    out = {"deleted": [], "skipped": []}
    for r, why in prune_plan(rows, utc_now(), manual, pin):
        empty = r["status"] == "failed" and not r.get("file_path")      # ★ ревизия 47 (мелочь 4): сбой до записи пути — файла нет
        p = None if empty else safe_file(cf["folder"], r)
        if not p and not empty:
            out["skipped"].append({"id": r["id"], "why": "путь файла не в папке панели или имя не панели — файл не трогаю"})
            continue
        if dry:
            out["deleted"].append({"id": r["id"], "file": p, "why": why, "existed": None})
            continue
        existed = _delete_file(p) if p else False
        _rows("SET NOCOUNT ON; EXEC adm.DbBackupDeleted @id = ?, @by = ?, @why = ?", (int(r["id"]), by[:64], why if existed else why + ", файла уже не было"))
        out["deleted"].append({"id": r["id"], "file": p, "why": why, "existed": existed})
    return out


def _age_h(v, now):
    return round((now - v).total_seconds() / 3600, 1) if isinstance(v, datetime.datetime) else None


def _iso(v):
    return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v


def state():
    """Состояние для «Состояния» и консоли: базы (модель, размеры, последний бэкап любого инструмента), бэкапы панели, место, предупреждения."""
    now = utc_now()
    out = {"now_utc": _iso(now), "read": False, "error": None, "dbs": [], "rows": [], "warnings": [],
           "policy": {"keep_days": KEEP_DAYS, "keep_min": KEEP_MIN, "keep_max": KEEP_MAX, "failed_keep_days": FAILED_KEEP_DAYS,
                      "warn_hours": WARN_HOURS, "long_weeks": LONG_WEEKS, "long_months": LONG_MONTHS}}
    sq, err = _call("SET NOCOUNT ON; EXEC adm.DbBackupState")
    if err:
        out["error"] = "состояние баз не прочитано: %s" % err
        return out
    try:
        rows = panel_rows(500)
        total = _rows("SELECT COUNT(*) AS n, SUM(CAST(COALESCE(file_bytes, backup_bytes, 0) AS BIGINT)) AS b FROM adm.dbbackup WHERE status IN ('done','failed')")[0]
    except db.DbError as ex:
        out["error"] = "журнал бэкапов панели не прочитан: %s" % ex
        return out
    out["read"] = True
    out["panel_files"], out["panel_bytes"] = int(total["n"] or 0), int(total["b"] or 0)
    if sq:
        f = sq[0]
        out.update(folder=f["folder"], free_bytes=f["free_bytes"], total_bytes=f["total_bytes"], volume=f["volume"],
                   free_factor=None, reserve_mb=None)
        if f["free_bytes"] is None:
            out["warnings"].append("место на томе папки бэкапов не прочитано (папка не на томе файлов баз)")
    try:
        cf = folder()
        out["free_factor"], out["reserve_mb"] = cf["free_factor"], cf["free_reserve_mb"]
    except OpRefused:
        pass
    for s in sq:
        name = s["db"]
        mine = [r for r in rows if r["db"].lower() == name.lower()]
        last = next((r for r in mine if r["status"] == "done"), None)
        lastv = next((r for r in mine if r["status"] == "done" and r["verified"]), None)
        dev = str(s.get("any_device") or "")
        d = {"db": name, "state": s["state"], "recovery": s["recovery"], "log_wait": s["log_wait"], "data_bytes": s["data_bytes"],
             "log_bytes": s["log_bytes"], "any": None, "log_backup_utc": _iso(s["log_backup_utc"]), "panel_last": None, "panel_verified": None,
             "age_h": None, "warnings": []}
        if s.get("any_finish_utc"):
            d["any"] = {"finish_utc": _iso(s["any_finish_utc"]), "copy_only": bool(s["any_copy_only"]), "checksums": bool(s["any_checksums"]),
                        "device": dev, "user": s["any_user"], "bytes": s["any_bytes"],
                        "panel": bool(out.get("folder")) and dev.lower().startswith(str(out["folder"]).rstrip("\\").lower() + "\\"),
                        "age_h": _age_h(s["any_finish_utc"], now)}
        for k, r in (("panel_last", last), ("panel_verified", lastv)):
            if r:
                d[k] = {"id": r["id"], "finished_utc": _iso(r["finished_at"]), "verified": r["verified"], "file": r["file_path"],
                        "bytes": r["backup_bytes"], "md5": r["md5"], "stand_ok": r["stand_ok"], "stand_utc": _iso(r["stand_at"]),
                        "age_h": _age_h(r["finished_at"], now)}
        if s["state"] is None:
            d["warnings"].append("базы нет на сервере (в списке бэкапов панели она есть)")
        if lastv:
            d["age_h"] = d["panel_verified"]["age_h"]
            if d["age_h"] is not None and d["age_h"] > WARN_HOURS:
                d["warnings"].append("последний проверенный бэкап панели старше %d ч" % WARN_HOURS)
        elif d["any"]:
            d["warnings"].append("проверенных бэкапов панели нет, последний чужой бэкап — %s UTC (по истории msdb, наличие файла не проверялось)"
                                 % d["any"]["finish_utc"][:16])
        else:
            d["warnings"].append("бэкапов нет ни одного (ни панели, ни по истории msdb)")
        if last and not last["verified"]:
            d["warnings"].append("последний бэкап панели №%s не прошёл проверку VERIFYONLY" % last["id"])
        if s["recovery"] == "FULL" and not s["log_backup_utc"] and s["log_wait"] == "LOG_BACKUP":
            d["warnings"].append("модель FULL без бэкапов журнала: файл журнала только растёт (панель модель восстановления не меняет)")
        out["dbs"].append(d)
    out["rows"] = [{k: _iso(v) for k, v in r.items()} for r in rows[:60]]
    running = [r for r in rows if r["status"] == "running"]
    if running:
        try:
            b = busy()
        except OpRefused:
            b = None
        if b and not b["lock_held"]:
            out["warnings"].append("строка бэкапа №%s висит в «идёт», хотя бэкап не идёт: её снимет следующий бэкап или db release"
                                   % running[0]["id"])
        else:
            out["warnings"].append("идёт бэкап панели: %s (№%s, начат %s UTC)" % (running[0]["db"], running[0]["id"], _iso(running[0]["started_at"])[:16]))
    return out


def _dbs(p, names):
    """Базы из параметров (dbs: «all» / список / строка через запятую; db: одна) → список из белого списка."""
    v = p.get("dbs", p.get("db", "all"))
    if v in (None, "", "all", ["all"]):
        return list(names)
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",") if x.strip()]
    if not isinstance(v, list) or not v:
        raise OpRefused("базы для бэкапа — all или список имён")
    low = {n.lower(): n for n in names}
    bad = [str(x) for x in v if str(x).lower() not in low]
    if bad:
        raise OpRefused("база %s не в списке бэкапов панели (можно: %s)" % (", ".join(bad), ", ".join(names)))
    out = []
    for x in v:
        n = low[str(x).lower()]
        if n not in out:
            out.append(n)
    return out


def _mb(b):
    return "%.1f МБ" % ((b or 0) / 1048576.0)


def _busy_check(warn):
    """★ ревизия 47 В-1: отказ — только если бэкап панели идёт на самом деле (блокировку держит другой сеанс); зависшая строка — предупреждение,
    её снимет сама процедура. → состояние busy()."""
    b = busy()
    if b["lock_held"]:
        r = _rows("SELECT TOP 1 id, db FROM adm.dbbackup WHERE status = 'running' ORDER BY id")
        raise OpRefused(BUSY_TEXT % ((r[0]["db"], r[0]["id"]) if r else ("?", "?")))
    if b["running_rows"]:
        warn.append("строка бэкапа №%s висит в «идёт» (сеанс бэкапа оборвался) — будет снята как прерванная" % b["running_id"])
    return b


def _web_queue_check(name, b, warn):
    """Из браузера: уже поставленное задание этой операции — отказ; зависшее «идёт» (бэкап не идёт) — не отказ, подсказка db release."""
    q = _rows("SELECT TOP 1 id, status FROM adm.job WHERE op = ? AND status IN ('pending','running') AND run_at <= DATEADD(MINUTE, 2, SYSUTCDATETIME()) "
              "ORDER BY id", (name,))
    if q and (q[0]["status"] == "pending" or b["lock_held"]):
        if name == "db.backup":
            raise OpRefused("бэкап уже поставлен заданием №%s — дождитесь итога" % q[0]["id"])
        raise OpRefused("перепроверка уже поставлена заданием №%s — дождитесь итога" % q[0]["id"])
    if q:
        warn.append("задание №%s висит в «идёт», хотя бэкап не идёт (служба упала посреди) — снимите его: db release" % q[0]["id"])
    warn.insert(0, "будет поставлено заданием службы на сейчас: начнётся в течение минуты, итог — в журнале и в карточке «Бэкапы БД»")


@register
class DbBackup(Operation):
    name, title, perm, reversible = "db.backup", "Бэкапы БД: сделать бэкап (COPY_ONLY, проверка VERIFYONLY)", "db.backup", False
    schedule_runner = "service"          # SQL и файл — на сервере, служба работает всегда (обоснование — шапка модуля)
    schedule_repeat_days = 366           # подтверждений и второго фактора нет: повтор действует год
    schedule_long = True                 # ★ ревизия 47 С-2: служба исполняет отдельным потоком (не держит объявления и режим обслуживания)

    def target(self, p):
        v = p.get("dbs", p.get("db", "all"))
        return "db:%s" % (",".join(v) if isinstance(v, list) else (v or "all"))

    def schedule_check(self, ctx, p):
        return _dbs(p, allowed())

    def preview(self, ctx, p):
        names = self.schedule_check(ctx, p)
        sq, err = _call("SET NOCOUNT ON; EXEC adm.DbBackupState")
        if err:
            raise OpRefused("состояние баз не прочитано: %s" % err)
        cf = folder()
        by = {r["db"].lower(): r for r in sq}
        data = sum(int(by[n.lower()]["data_bytes"] or 0) for n in names if n.lower() in by)
        free = sq[0]["free_bytes"] if sq else None
        if free is None:
            raise OpRefused("свободное место на томе папки бэкапов не прочитано — бэкап не начат")
        need = data * int(cf["free_factor"]) + int(cf["free_reserve_mb"]) * 1048576
        if free < need:
            raise OpRefused("мало места на томе папки бэкапов: свободно %s, нужно не меньше %s (данные баз × %d + запас %d МБ) — бэкап не начат"
                            % (_mb(free), _mb(need), cf["free_factor"], cf["free_reserve_mb"]))
        warn = ["COPY_ONLY: цепочку бэкапов других инструментов не трогает, базы только читаются (игроки не замечают)",
                "сжатия бэкапов у SQL Server Express нет: файл — примерно размер занятых данных",
                "после бэкапа — уборка бэкапов панели старше %d дн. (последние %d проверенных, недельные за %d нед., месячные за %d мес. и чужие "
                "файлы не удаляются)" % (KEEP_DAYS, KEEP_MIN, LONG_WEEKS, LONG_MONTHS)]
        b = _busy_check(warn)
        if ctx.via == "web":
            _web_queue_check("db.backup", b, warn)
        return {"text": "бэкап баз: %s (папка %s, свободно %s)" % (", ".join(names), cf["folder"], _mb(free)), "dbs": names, "warnings": warn}

    def apply(self, ctx, p, prev):
        if ctx.via == "web":
            jid = jobs.add("db.backup", {"dbs": prev["dbs"]}, "service", utc_now(), "", "по кнопке", ctx.login, ctx.user_id, ctx.role)
            return {"before": None, "after": {"job": jid, "dbs": prev["dbs"]},
                    "message": "бэкап поставлен заданием службы №%d — начнётся в течение минуты" % jid}
        res = [backup_one(n, ctx.login, p.get("job_id")) for n in prev["dbs"]]
        parts = []                        # каждая часть — свой шаблон перевода, «бэкап: …» переводится по частям (core/i18n NESTED_AT)
        for r in res:
            mb = "%.1f" % ((r["bytes"] or 0) / 1048576.0)
            if r["status"] == "done" and r["verified"] and r["pruned"]:
                parts.append("%s №%s проверен, %s МБ, убрано старых: %d" % (r["db"], r["id"], mb, len(r["pruned"])))
            elif r["status"] == "done" and r["verified"]:
                parts.append("%s №%s проверен, %s МБ" % (r["db"], r["id"], mb))
            elif r["status"] == "done":
                parts.append("%s №%s записан, проверка НЕ прошла" % (r["db"], r["id"]))
            else:
                parts.append("%s не сделан: %s" % (r["db"], (r["error"] or r["message"] or "?").replace("; ", ", ")))
        msg = "бэкап: " + "; ".join(parts)
        if any(not (r["status"] == "done" and r["verified"]) for r in res):
            raise BackupFailed(msg)
        return {"before": None, "after": {"results": res}, "message": msg}


@register
class DbVerify(Operation):
    name, title, perm, reversible = "db.verify", "Бэкапы БД: перепроверить файл (RESTORE VERIFYONLY)", "db.backup", False
    schedule_runner = "service"          # ★ ревизия 47 Н-5: из браузера — заданием службы (не в потоке HTTP)
    schedule_long = True
    schedule_hidden = True               # в форме «Задания и стойка» не предлагается (нужен номер бэкапа — кнопка в карточке)

    def target(self, p):
        return "dbbackup:%s" % p.get("id")

    def preview(self, ctx, p):
        try:
            bid = int(p.get("id"))
        except (TypeError, ValueError):
            raise OpRefused("не указан номер бэкапа")
        r = get(bid)
        if not r or r["status"] != "done":
            raise OpRefused("готового бэкапа панели №%s нет (удалён, не завершён или не панели)" % bid)
        warn = []
        b = _busy_check(warn)
        if ctx.via == "web":
            _web_queue_check("db.verify", b, warn)
        return {"text": "перепроверить бэкап №%d (%s, %s)" % (bid, r["db"], r["file_path"]), "id": bid, "warnings": warn}

    def apply(self, ctx, p, prev):
        if ctx.via == "web":
            jid = jobs.add("db.verify", {"id": prev["id"]}, "service", utc_now(), "", "по кнопке", ctx.login, ctx.user_id, ctx.role)
            return {"before": None, "after": {"job": jid, "id": prev["id"]},
                    "message": "перепроверка бэкапа №%d поставлена заданием службы №%d — начнётся в течение минуты" % (prev["id"], jid)}
        rows, err = _call("SET NOCOUNT ON; EXEC adm.DbBackupVerify @id = ?", (prev["id"],), VERIFY_TIMEOUT_S, unlock=True)
        r = get(prev["id"])
        if err or not r or not r["verified"]:
            raise BackupFailed("бэкап №%d: проверка не прошла: %s" % (prev["id"], err or (r and r["message"]) or "?"))
        return {"before": None, "after": {"id": prev["id"], "verified": True}, "message": "бэкап №%d: проверка прошла" % prev["id"]}


@register
class DbPrune(Operation):
    name, title, perm, reversible = "db.prune", "Бэкапы БД: убрать старые бэкапы панели", "db.prune", False

    def target(self, p):
        return "db:%s" % (p.get("db") or "all")

    def preview(self, ctx, p):
        names = _dbs({"dbs": p.get("db") or "all"}, allowed())
        plan = {n: prune(n, ctx.login, dry=True, manual=True) for n in names}
        items = [dict(x, db=n) for n in names for x in plan[n]["deleted"]]
        if str(p.get("confirm") or "") != CONFIRM_PRUNE:
            raise OpRefused("нужно подтверждение: уборка удаляет файлы бэкапов панели (ключ confirm = prune)")
        return {"text": "убрать бэкапов панели: %d" % len(items), "items": items,
                "warnings": ["удаляются только файлы панели в её папке, последние %d проверенных каждой базы, недельные и месячные копии и "
                             "чужие бэкапы — никогда" % KEEP_MIN]
                + ["пропущено (не панели): №%s" % x["id"] for n in names for x in plan[n]["skipped"]], "dbs": names}

    def apply(self, ctx, p, prev):
        got = {n: prune(n, ctx.login, manual=True) for n in prev["dbs"]}
        ids = [x["id"] for n in got for x in got[n]["deleted"]]
        return {"before": None, "after": {"deleted": ids}, "message": "убрано бэкапов панели: %d" % len(ids)}


@register
class DbRelease(Operation):
    """★ ревизия 47 В-1: снять зависшее «идёт» — строки adm.dbbackup и задания db.backup / db.verify, если бэкап панели на самом деле не идёт."""
    name, title, perm, reversible = "db.release", "Бэкапы БД: снять зависшее «идёт»", "db.release", False

    def preview(self, ctx, p):
        b = busy()
        if b["lock_held"]:
            raise OpRefused("бэкап панели идёт на самом деле (блокировку держит сеанс SQL) — снимать нечего, дождитесь итога")
        if b["server_backup"] and b["running_rows"]:
            raise OpRefused("на сервере сейчас идёт BACKUP или RESTORE (возможно, откат оборванного) — повторите, когда он закончится")
        sj = stale_jobs(b)
        if not b["running_rows"] and not sj:
            raise OpRefused("зависших бэкапов и заданий бэкапа нет — снимать нечего")
        if str(p.get("confirm") or "") != CONFIRM_RELEASE:
            raise OpRefused("нужно подтверждение: снять зависшее «идёт» (ключ confirm = release)")
        return {"text": "снять зависшее «идёт»: строк бэкапа %d, заданий %d" % (b["running_rows"], len(sj)), "jobs": [j["id"] for j in sj],
                "rows": b["running_rows"], "warnings": ["блокировка бэкапа свободна: ни один сеанс SQL бэкап панели не ведёт"]}

    def apply(self, ctx, p, prev):
        rows, err = _call("DECLARE @r INT; EXEC @r = adm.DbBackupAbort @msg = ?; SELECT @r AS r", ("снято вручную: " + ctx.login,))
        if err or not rows or int(rows[0]["r"]) != 0:
            raise OpRefused("бэкап панели начался заново — снимать нечего, дождитесь итога")
        done = [j for j in prev["jobs"] if jobs.release(j, ctx.login)]
        return {"before": {"rows": prev["rows"], "jobs": prev["jobs"]}, "after": {"jobs": done},
                "message": "снято зависшее «идёт»: строк бэкапа %d, заданий %d" % (prev["rows"], len(done))}


@register
class DbRestoreLive(Operation):
    name, title, perm, reversible = "db.restore", "Бэкапы БД: восстановить на живой сервер — НЕ делается", "db.stand", False

    def preview(self, ctx, p):
        raise OpRefused(LIVE_RESTORE_REFUSAL)

    def apply(self, ctx, p, prev):
        raise OpRefused(LIVE_RESTORE_REFUSAL)
