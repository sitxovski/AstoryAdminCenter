# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""jobs.py — задания планировщика AsdaAdmin.adm.job (волна А5.1 «Живое управление», план §3.2 «adm.job — с А5», §5.1; 20.11.2026).

ЗАДАНИЕ — отложенный вызов операции core/ops: op + params (JSON), время запуска run_at (UTC, без пояса), исполнитель runner:
  service — поток планировщика службы на сервере (core/sched.py, раз в CHECK_S);
  pc      — консоль ПК владельца (asda_admin.py jobs run-due): управление стойкой идёт только restart_stack.py, а он работает с ПК
            (ключ SSH, бот Discord). ПК выключен — задание ждёт; просрочено больше GRACE_S — «пропущено» (missed), поздно НЕ запускается.
  Какие операции можно ставить в задания — атрибут операции schedule_runner ("service" | "pc"); проверка параметров заранее —
  метод операции schedule_check(ctx, p) (подтверждения, длина текста) — тот же, что зовёт её preview.
ЗАПУСК — от имени АВТОРА задания с его ТЕКУЩЕЙ ролью (adm.users; учётка отключена/удалена или право снято — отказ, не запуск);
  автор-консоль (cli:…) — роль, записанная при постановке. Каждый запуск — обычный ops.run (журнал adm.audit), путь via = "job".
  Номер задания передаётся операции в params["job_id"] (операции стойки по нему узнают свою строку взаимоисключения).
ВЗАИМОИСКЛЮЧЕНИЕ стойки — уникальный индекс UX_adm_job_stack_running (sql/adminc_14_jobs.sql): строка running с op stack.* одна.
  Прямой запуск консолью тоже ставит строку running (begin_direct), рестарты наборов изменений А3/А4 (shopcs) — тоже (stack_guard,
  op «stack.changeset»; ревизия 41 В-1). Зависшую строку (ПК упал посреди прогона) снимает job.release.
ПОВТОР — daily / weekly: после прогона (и после пропуска) ставится следующее задание на ближайшее будущее время того же шага, но не позже
  repeat_until (REPEAT_DAYS от первого запуска; ревизия 41 Н-3). Задание консоли (cli:…) исполняет только машина постановки (Н-5).
Побочных эффектов при импорте нет.
"""
import contextlib
import datetime
import json
import socket

from . import db

RUNNERS = ("service", "pc")
REPEATS = {"": None, "daily": datetime.timedelta(days=1), "weekly": datetime.timedelta(days=7)}
STATUSES = ("pending", "running", "done", "failed", "refused", "cancelled", "missed")
GRACE_S = 600                  # просрочка запуска больше этого — missed (не поздний рестарт)
GRACE_LONG_S = 6 * 3600        # ★ ревизия 47 С-2: у долгих операций (бэкап) — поток долгих может быть занят предыдущим бэкапом
MIN_AHEAD_S = 60               # задание — не раньше чем через минуту (сразу — прямым запуском)
MAX_AHEAD_DAYS = 31            # и не дальше месяца
CLAIM_MAX = 5                  # заданий за один проход исполнителя
REPEAT_DAYS = 31               # ★ ревизия 41 Н-3: повтор действует столько дней от первого запуска, потом — поставить заново
LOCK_INDEX = "UX_adm_job_stack_running"


class JobLocked(Exception):
    """Уже идёт управление стойкой (строка running stack.*)."""

    def __init__(self, other):
        super().__init__("уже идёт управление стойкой (задание №%s)" % (other or "?"))
        self.other = other


def utc_now():
    """Текущее время UTC без пояса (как DATETIME2 adm.job)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def parse_at(text):
    """Время запуска → UTC без пояса. ISO с поясом (из браузера: …Z / +03:00) — как есть; без пояса — местное время ЭТОЙ машины
    (консоль ПК). Неразборчиво — ValueError."""
    s = str(text or "").strip().replace("T", " ")
    if not s:
        raise ValueError("пусто")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    v = datetime.datetime.fromisoformat(s)
    if v.tzinfo is None:
        v = v.astimezone()                         # местное время машины
    return v.astimezone(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def fmt_utc(v):
    """UTC без пояса → «ГГГГ-ММ-ДД ЧЧ:ММ UTC»."""
    return v.strftime("%Y-%m-%d %H:%M UTC") if isinstance(v, datetime.datetime) else str(v)


def _rows(sql, params=()):
    cn = db.admin()
    try:
        return db.admin_rows(cn, sql, params)
    finally:
        cn.close()


JOB_LOCK = "adm.job:%d"        # ★ ревизия 48 Н-2: applock исполнителя на всё время прогона задания (признак «живое» для db.release)


def hold_job(job_id):
    """Взять applock задания (Exclusive, Session) на своём соединении → соединение (держать до release_job) | None (не взялся / нет базы)."""
    try:
        cn = db.admin()
    except Exception:
        return None
    try:
        r = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @r INT; EXEC @r = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
                              "@LockOwner = 'Session', @LockTimeout = 0; SELECT @r AS r", (JOB_LOCK % int(job_id),))
        if r and int(r[0]["r"]) >= 0:
            return cn
    except Exception:
        pass
    try:
        cn.close()
    except Exception:
        pass
    return None


def release_job(cn, job_id):
    """Отпустить applock задания (явно: соединение из пула ODBC держит Session-блокировку и после close — урок ревизии 47) и закрыть."""
    if cn is None:
        return
    try:
        db.admin_rows(cn, "SET NOCOUNT ON; EXEC sp_releaseapplock @Resource = ?, @LockOwner = 'Session'; SELECT 1 AS ok", (JOB_LOCK % int(job_id),))
    except Exception:
        pass
    try:
        cn.close()
    except Exception:
        pass


def job_alive(job_id):
    """Исполнитель сейчас держит applock задания → True; свободна → False. Не прочитано — исключение («не прочитано» ≠ «зависло»)."""
    r = _rows("SELECT APPLOCK_TEST('public', ?, 'Exclusive', 'Session') AS free", (JOB_LOCK % int(job_id),))
    return not (r and int(r[0]["free"]) == 1)


def _norm(r):
    """Строка adm.job → dict (params разобраны)."""
    r = dict(r)
    try:
        r["params"] = json.loads(r.get("params") or "{}")
    except ValueError:
        r["params"] = {}
    r.pop("stack_lock", None)
    return r


def get(job_id):
    r = _rows("SELECT * FROM adm.job WHERE id = ?", (int(job_id),))
    return _norm(r[0]) if r else None


def list_jobs(limit=100, active=False):
    """Задания, новые сверху (active — только pending/running)."""
    where = "WHERE status IN ('pending','running') " if active else ""
    return [_norm(r) for r in _rows("SELECT TOP (%d) * FROM adm.job %sORDER BY id DESC" % (max(1, min(int(limit), 500)), where))]


def running_stack():
    """Строка running управления стойкой или None."""
    r = _rows("SELECT TOP 1 * FROM adm.job WHERE status = 'running' AND op LIKE 'stack.%' ORDER BY id")
    return _norm(r[0]) if r else None


def repeat_limit(run_at, repeat, days=None):
    """★ ревизия 41 Н-3: срок действия повтора — REPEAT_DAYS от первого запуска (подтверждение и второй фактор даны один раз) или None.
    ★ А5.7: операция может задать свой срок (schedule_repeat_days — бэкап БД: год, у него нет подтверждений и второго фактора)."""
    return run_at + datetime.timedelta(days=days or REPEAT_DAYS) if repeat else None


def repeat_days(op_name):
    """★ А5.7: срок повтора операции в днях (атрибут schedule_repeat_days, иначе REPEAT_DAYS)."""
    from . import ops
    return int(getattr(ops.REGISTRY.get(op_name), "schedule_repeat_days", 0) or REPEAT_DAYS)


def add(op, params, runner, run_at, repeat, note, by, uid, role):
    """Новое задание pending → его номер. ★ ревизия 41: повтор — до repeat_until; машина постановки — created_host (Н-5)."""
    r = _rows("SET NOCOUNT ON; INSERT adm.job (op, params, runner, run_at, repeat_mode, note, created_by, created_uid, created_role, "
              "repeat_until, created_host) OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (op, json.dumps(params or {}, ensure_ascii=False), runner, run_at, repeat or "", (note or "")[:400], by[:32], uid, role,
               repeat_limit(run_at, repeat, repeat_days(op)), socket.gethostname()[:64]))
    return int(r[0]["id"])


class _Guard:
    """Итог строки взаимоисключения stack_guard (ставит вызывающий)."""

    def __init__(self, jid):
        self.id, self.status, self.text = jid, "failed", "прервано до итога"


@contextlib.contextmanager
def stack_guard(op, by, uid, role, note=""):
    """★ ревизия 41 В-1: строка running взаимоисключения стойки на время любого restart_stack.py панели (наборы А3/А4 — op
    «stack.changeset»). Занято — JobLocked (до объявления, ничего не тронуто). Итог — g.status / g.text; исключение внутри — failed."""
    g = _Guard(begin_direct(op, {}, by, uid, role, note))
    try:
        yield g
    except BaseException as ex:
        g.status, g.text = "failed", "%s: %s" % (ex.__class__.__name__, str(ex)[:600])
        raise
    finally:
        try:
            finish(g.id, g.status if g.status in ("done", "failed", "refused") else "failed", g.text)
        except Exception:
            pass                                  # строку снимет job.release; итог действия — в adm.audit


def _locked(ex):
    return LOCK_INDEX in str(ex) or "duplicate key" in str(ex).lower()


def begin_direct(op, params, by, uid, role, note=""):
    """Прямой запуск операции стойки (консоль ПК): строка running сразу (взаимоисключение) → номер. Занято — JobLocked."""
    try:
        r = _rows("SET NOCOUNT ON; INSERT adm.job (op, params, runner, run_at, status, note, created_by, created_uid, created_role, "
                  "started_at, host, created_host) OUTPUT INSERTED.id VALUES (?, ?, 'pc', SYSUTCDATETIME(), 'running', ?, ?, ?, ?, "
                  "SYSUTCDATETIME(), ?, ?)", (op, json.dumps(params or {}, ensure_ascii=False), (note or "прямой запуск")[:400], by[:32], uid,
                                               role, socket.gethostname()[:64], socket.gethostname()[:64]))
    except db.DbError as ex:
        if _locked(ex):
            other = running_stack()
            raise JobLocked(other["id"] if other else None)
        raise
    return int(r[0]["id"])


def finish(job_id, status, result="", audit_id=None):
    """Итог прогона: только у строки running (повторный итог не перетирает первый) → True, если записан."""
    if status not in ("done", "failed", "refused"):
        raise ValueError(status)
    r = _rows("SET NOCOUNT ON; UPDATE adm.job SET status = ?, finished_at = SYSUTCDATETIME(), result = ?, audit_id = COALESCE(?, audit_id) "
              "OUTPUT INSERTED.id WHERE id = ? AND status = 'running'", (status, (result or "")[:2000], audit_id, int(job_id)))
    return bool(r)


def cancel(job_id):
    """pending → cancelled → True; иначе False (уже идёт / закончено)."""
    return bool(_rows("SET NOCOUNT ON; UPDATE adm.job SET status = 'cancelled', finished_at = SYSUTCDATETIME() OUTPUT INSERTED.id "
                      "WHERE id = ? AND status = 'pending'", (int(job_id),)))


def release(job_id, why):
    """Зависшая running → failed с пометкой «снято вручную» → True; иначе False."""
    return bool(_rows("SET NOCOUNT ON; UPDATE adm.job SET status = 'failed', finished_at = SYSUTCDATETIME(), result = ? OUTPUT INSERTED.id "
                      "WHERE id = ? AND status = 'running'", (("снято вручную: " + (why or ""))[:2000], int(job_id))))


def next_time(run_at, repeat, now):
    """Следующее время повтора строго позже now (или None — разовое)."""
    step = REPEATS.get(repeat or "")
    if not step:
        return None
    t = run_at + step
    while t <= now:
        t += step
    return t


def _repeat(job, now):
    """Поставить следующее повторение (новая строка pending, prev_id) → номер или None."""
    t = next_time(job["run_at"], job.get("repeat_mode"), now)
    if t is None:
        return None
    until = job.get("repeat_until")
    if until is None or t > until:                # ★ ревизия 41 Н-3: повтор не вечен (нет срока — тоже не повторять)
        return None
    r = _rows("SET NOCOUNT ON; INSERT adm.job (op, params, runner, run_at, repeat_mode, note, created_by, created_uid, created_role, prev_id, "
              "repeat_until, created_host) OUTPUT INSERTED.id SELECT op, params, runner, ?, repeat_mode, note, created_by, created_uid, "
              "created_role, id, repeat_until, created_host FROM adm.job WHERE id = ?", (t, int(job["id"])))
    return int(r[0]["id"]) if r else None


def long_ops():
    """★ ревизия 47 С-2: долгие операции (атрибут schedule_long — бэкап БД, перепроверка) → [имена]. Служба исполняет их отдельным потоком."""
    from . import ops
    return sorted(n for n, o in ops.REGISTRY.items() if getattr(o, "schedule_long", False))


def _op_filter(long):
    """Условие SQL по долгим операциям: None — все задания, True — только долгие, False — все, кроме долгих → (текст, параметры)."""
    names = long_ops() if long is not None else []
    if long is None or not names:
        return ("", ()) if long is not True else (" AND 1 = 0", ())
    return (" AND op %sIN (%s)" % ("" if long else "NOT ", ",".join("?" * len(names))), tuple(names))


def mark_missed(runner, now, long=None):
    """Просроченные больше GRACE_S (долгие операции — GRACE_LONG_S) pending → missed (и следующее повторение) → [номера]."""
    lim = now - datetime.timedelta(seconds=GRACE_LONG_S if long else GRACE_S)
    cond, extra = _op_filter(long)
    rows = _rows("SET NOCOUNT ON; UPDATE adm.job SET status = 'missed', finished_at = SYSUTCDATETIME(), "
                 "result = N'пропущено: исполнитель не запускался в срок' OUTPUT INSERTED.* "
                 "WHERE status = 'pending' AND runner = ? AND run_at < ?" + cond, (runner, lim) + extra)
    for r in rows:
        _repeat(_norm(r), now)
    return [int(r["id"]) for r in rows]


def claim(runner, now, host, long=None):
    """Взять одно наступившее задание (pending, run_at ≤ now, не просрочено) → dict или None. Стойка занята — задание остаётся ждать.
    ★ ревизия 47 С-2: long — None все / True только долгие / False без долгих."""
    lim = now - datetime.timedelta(seconds=GRACE_LONG_S if long else GRACE_S)
    cond, extra = _op_filter(long)
    try:
        r = _rows("SET NOCOUNT ON; WITH c AS (SELECT TOP 1 * FROM adm.job WITH (UPDLOCK, READPAST) WHERE status = 'pending' AND runner = ? "
                  "AND run_at <= ? AND run_at >= ?" + cond + " ORDER BY run_at, id) UPDATE c SET status = 'running', started_at = SYSUTCDATETIME(), "
                  "host = ? OUTPUT INSERTED.*", (runner, now, lim) + extra + (host[:64],))
    except db.DbError as ex:
        if _locked(ex):
            return None
        raise
    return _norm(r[0]) if r else None


def author_role(job):
    """Текущая роль автора задания → роль или None (отключён / удалён). Автор-консоль — роль, записанная при постановке, и ТОЛЬКО если
    задание ставилось на этой же машине (★ ревизия 41 Н-5: строку «cli:…» с ролью owner мог бы вставить любой владелец логина SQL
    asda_admin; задание консоли исполняет только машина, на которой его поставили)."""
    if job.get("created_uid") is None:
        if not str(job["created_by"]).startswith("cli:"):
            return None
        if (job.get("created_host") or "").lower() != socket.gethostname()[:64].lower():
            return None
        return job["created_role"]
    r = _rows("SELECT role, disabled FROM adm.users WHERE id = ?", (int(job["created_uid"]),))
    if not r or r[0]["disabled"]:
        return None
    return r[0]["role"]


def run_job(job, runner=None):
    """Прогон одного взятого задания (строка уже running) → (статус, текст). runner(ctx, op, params) — подмена для самотеста.
    ★ ревизия 48 Н-2: всё время прогона исполнитель держит applock JOB_LOCK — db.release снимает только задания без неё."""
    lock = hold_job(job["id"])
    try:
        return _run_job(job, runner)
    finally:
        release_job(lock, job["id"])


def _run_job(job, runner=None):
    from . import ops
    runner = runner or (lambda ctx, name, p: ops.run(ctx, name, p))
    role = author_role(job)
    op = ops.REGISTRY.get(job["op"])
    if role is None and job.get("created_uid") is None and str(job["created_by"]).startswith("cli:"):
        status, text, aid = "refused", "задание консоли поставлено на другой машине (%s) — исполняет только она" % (job.get("created_host") or "?"), None
    elif role is None:
        status, text, aid = "refused", "автор задания отключён или удалён — задание не выполнено", None
    elif not op or not getattr(op, "schedule_runner", None):
        status, text, aid = "refused", "операция %s не ставится в задания" % job["op"], None
    elif not ops.auth.can(role, op.perm):
        status, text, aid = "refused", "у автора задания больше нет права «%s»" % op.perm, None
    else:
        ctx = ops.Ctx(job.get("created_uid"), job["created_by"], role, "", "job")
        p = dict(job["params"] or {}, job_id=int(job["id"]))
        try:
            res = runner(ctx, job["op"], p) or {}
            status, text, aid = "done", res.get("message") or "ok", res.get("audit_id")
        except ops.OpRefused as ex:
            status, text, aid = "refused", str(ex), None
        except Exception as ex:                      # сбой операции уже в журнале (ops.run пишет сам)
            status, text, aid = "failed", "%s: %s" % (ex.__class__.__name__, str(ex)[:800]), None
    finish(job["id"], status, text, aid)
    _repeat(job, utc_now())
    return status, text


def run_due(runner_name, now=None, runner=None, long=None):
    """Один проход исполнителя: пропущенные → missed, наступившие — по одному (до CLAIM_MAX) → [(номер, статус, текст)].
    ★ ревизия 47 С-2: long — None все задания (консоль ПК, самотест), True / False — поток долгих / обычных заданий службы."""
    now = now or utc_now()
    out = [(i, "missed", "") for i in mark_missed(runner_name, now, long)]
    host = socket.gethostname()
    for _ in range(CLAIM_MAX):
        job = claim(runner_name, now, host, long)
        if not job:
            break
        st, text = run_job(job, runner)
        out.append((job["id"], st, text))
    return out
