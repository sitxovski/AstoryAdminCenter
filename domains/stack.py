# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""stack.py — управление игровой стойкой и задания планировщика (волна А5.1 «Живое управление», план §4.Д, §5.1; 20.11.2026).

СТОЙКА — ТОЛЬКО через AstoryServer/Patches/AsdaPatch/tools/restart_stack.py (правило проекта: объявление ботом Discord в #test-info
роли Beta Tester на EN/AR/RU и 3 минуты предупреждения), а он работает с ПК владельца (ключ SSH, бот Discord). Поэтому операции
стойки — только консолью ПК (via cli) или заданием, которое исполняет консоль ПК (via job, jobs run-due); служба на сервере и браузер
их только ставят в задания (job.add). Право stack.control — только владелец.
  stack.restart — restart_stack.py --no-deploy   (объявление, 3 мин с отсчётом в игре, штатная остановка, паритет Ch2, CharPos, старт);
  stack.stop    — restart_stack.py --stop-only   (объявление «остановка на обслуживание», 3 мин с отсчётом, штатная остановка);
  stack.start   — restart_stack.py --start-only  (только целиком остановленная стойка; объявления нет — игроков нет).
  Ключей --no-announce, --wait, --skip-* панель НЕ передаёт никогда. Отсчёт в игре — ASDA_RESTART_TICK = «asda_admin.py stack tick»
  (объявление всем мостом P127, live.announce): сразу после объявления Discord, каждую минуту и за 30 с; моста нет — предупреждение.
ПРОВЕРКИ (preview и ещё раз в apply прямо перед запуском — состояние могло измениться): счёт процессов стойки по stack_layout
  (ВСЕ копии: GameServer ×3, NpcServer ×3, RelayServer ×3 …) обязан быть ПРОЧИТАН («не прочитано» ≠ «нет процессов»); stop — есть что
  останавливать; start — процессов 0; подтверждение (--confirm-<действие>); одновременно — одно управление стойкой (adm.job, уникальный
  индекс; им же заперты рестарты наборов А3/А4 — shopcs, «stack.changeset»; и файл-замок самого restart_stack.py, код 8). После
  прогона — счёт ещё раз: restart / start — стойка полная, stop — процессов 0. ★ Ревизия 41 С-3: отказ «стойка не тронута» (журнал
  refused) — только код ДО действий (1, 2, 6, 7, 8 — untouched) без строк действующих шагов и с тем же счётом; иначе — сбой StackFailed
  (журнал error) с хвостом вывода. Вывод — по ходу в консоль и в data/stack_runs/<задание>_<время>.log (Н-2); Ctrl+C — запись error
  «прервано оператором, проверьте стойку» (Н-1).
ЗАДАНИЯ (core/jobs.py, adm.job): job.add (операция со schedule_runner, время UTC, повтор daily/weekly, подтверждения операции; из
  браузера для стойки — свежий код второго фактора), job.cancel, job.release (зависшее «идёт»). Права: jobs.manage + право операции.
Побочных эффектов при импорте нет.
"""
import datetime
import json
import os
import subprocess
import sys
import time

from core import audit, auth, config, jobs
from core.ops import Operation, OpRefused, register, REGISTRY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_PY = os.path.join(ROOT, "asda_admin.py")
LOG_DIR = os.path.join(config.DATA_DIR, "stack_runs")
FORBIDDEN_FLAGS = ("--no-announce", "--wait", "--skip-parity", "--skip-firewall", "--no-graceful-stop", "--skip-charpos-reset",
                   "--skip-dungeon-relog-reset", "--deploy")
TAIL = 14                                         # строк вывода restart_stack в итоге операции
TICK_TTL = 8                                      # ★ ревизия 41 С-2: срок команды отсчёта в игре (все узлы сразу, ожидание ≤ 10 с)
STOP_START_NOTE = ("после остановки запускать только stack start (restart_stack.py --start-only), не start.bat вручную — иначе не будет "
                   "сброса CharPos и точек входа данжей")      # ★ ревизия 41 Н-6

# действие → (слово подтверждения, ключи restart_stack, отсчёт в игре, что должно стать)
MODES = {
    "stack.restart": ("restart", ["--no-deploy"], True, "full"),
    "stack.stop":    ("stop", ["--stop-only"], True, "zero"),
    "stack.start":   ("start", ["--start-only"], False, "full"),
}

# подмены для самотеста (None — настоящие): RUN(argv, env, log_path) → (код, вывод); COUNTS() → {процесс: число} | None
RUN = None
COUNTS = None
EXPECT = None                                     # подмена stack_layout.EXPECT


class StackFailed(RuntimeError):
    """restart_stack.py отработал, а стойка не в ожидаемом состоянии (журнал — error)."""


def _shopcs():
    from domains import shopcs
    return shopcs


def expect():
    """Ожидаемый состав стойки {процесс: копий} (stack_layout.EXPECT)."""
    return EXPECT if EXPECT is not None else _shopcs()._layout().EXPECT


def counts():
    """{процесс: число} по всем процессам стойки или None — не прочитано."""
    return COUNTS() if COUNTS else _shopcs().stack_counts()


def complete(c):
    return c is not None and all(c.get(k, 0) >= v for k, v in expect().items())


def total(c):
    return sum(c.values()) if c else 0


def counts_text(c):
    if c is None:
        return "не прочитано"
    if not c:
        return "процессов нет"
    return ", ".join("%s=%d" % kv for kv in sorted(c.items()))


def state():
    """Состояние для консоли и API: счёт процессов, ожидание, полнота, идущее управление, ближайшие задания."""
    c = counts()
    run = None
    try:
        run = jobs.running_stack()
    except Exception as ex:                      # журнал недоступен — показать, а не упасть
        run = {"error": str(ex)[:200]}
    return {"counts": c, "expect": expect(), "complete": complete(c), "total": total(c), "text": counts_text(c), "running": run}


def tick_text(kind, left):
    """Текст отсчёта в игре (cp1251 ≤ live.ANNOUNCE_MAX): EN / RU."""
    en, ru = ("%d min" % (left // 60), "%d мин" % (left // 60)) if left >= 60 else ("%d s" % left, "%d с" % left)
    if kind == "stop":
        return "Server shutdown for maintenance in %s / Остановка сервера на обслуживание через %s" % (en, ru)
    return "Server restart in %s / Перезапуск сервера через %s" % (en, ru)


def _run_restart(argv, env, log_path):
    """restart_stack.py без предела времени (убийство посреди работы оставило бы стойку остановленной; ревизия 30 К-6) → (код, вывод).
    ★ ревизия 41 Н-2: вывод (stdout + stderr) идёт ПО ХОДУ — в log_path (сброс после каждой строки: ПК упадёт — журнал уже на диске) и в
    консоль. Чтение кончается на конце вывода, итог — код возврата процесса (wait)."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    buf = []
    with open(log_path, "w", encoding="utf-8", newline="") as f:        # концы строк — как у процесса (без \r\r\n)
        p = subprocess.Popen(argv, cwd=os.path.dirname(argv[1]), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for raw in p.stdout:
            ln = raw.decode("utf-8", "replace")
            buf.append(ln)
            f.write(ln)
            f.flush()
            print("  | " + ln.rstrip(), flush=True)
        rc = p.wait()
    return rc, "".join(buf)


# ★ ревизия 41 С-3: «стойка не тронута» — только коды restart_stack ДО объявления / до первого действия (1 — ключи, 2 — объявление не
#   ушло, 6 — предпроверка брандмауэра/паритета, 7 — --start-only/--stop-only отказал, 8 — идёт другой restart_stack) и без единой
#   строки шагов, которые что-то делают (объявление ушло, ожидание, SC_CLOSE, остановка, паритет --sync, данжи, CharPos, start.bat).
UNTOUCHED_RC = (1, 2, 6, 7, 8)
TOUCH_MARKS = ("Отправлено", "2. ожидание", "3а.", "3. остановка", "все процессы стойки остановлены", "4. выкладка", "4б.", "4б2.", "4в.",
               "5. запуск")


def untouched(rc, out):
    """Стойку restart_stack точно не трогал (код до действий и ни одной строки действующих шагов)."""
    return rc in UNTOUCHED_RC and not any(m in out for m in TOUCH_MARKS)


def build_argv(name):
    """Команда restart_stack.py и окружение для действия name → (argv, env). Отсчёт в игре — ASDA_RESTART_TICK."""
    word, flags, tick, _want = MODES[name]
    argv = [sys.executable, _shopcs().RESTART] + list(flags)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("ASDA_RESTART_TICK", None)
    if tick:
        env["ASDA_RESTART_TICK"] = json.dumps([sys.executable, ADMIN_PY, "stack", "tick", "--kind", word])
    bad = [a for a in argv if a in FORBIDDEN_FLAGS]
    if bad:                                       # страховка: панель такие ключи не передаёт
        raise OpRefused("запрещённые ключи restart_stack: %s" % ", ".join(bad))
    return argv, env


def _pc_only(ctx, what):
    """Действие стойки — только консолью ПК (или заданием, которое исполняет консоль ПК)."""
    if config.get().on_server:
        raise OpRefused("%s — только консолью на ПК владельца: restart_stack.py работает с ПК (ключ SSH, бот Discord), служба только "
                        "ставит задание" % what)
    if ctx.via not in ("cli", "job"):
        raise OpRefused("%s — только консолью (python asda_admin.py stack …) или заданием планировщика" % what)


class _StackOp(Operation):
    """Общее у рестарта / остановки / запуска стойки."""
    perm, reversible, schedule_runner = "stack.control", False, "pc"

    def target(self, p):
        return "stack"

    def schedule_check(self, ctx, p):
        word = MODES[self.name][0]
        if str(p.get("confirm") or "") != word:
            raise OpRefused("нужно подтверждение: ключ --confirm-%s (в панели — галочка подтверждения)" % word)

    def _check(self, c):
        """Состояние стойки допускает действие → None, иначе OpRefused."""
        if c is None:
            raise OpRefused("число процессов стойки не прочитано (SSH) — ничего не делаю")
        if self.name == "stack.stop" and not total(c):
            raise OpRefused("стойка уже остановлена — останавливать нечего")
        if self.name == "stack.start" and total(c):
            raise OpRefused("процессы стойки работают (%s) — запуск только целиком остановленной стойки" % counts_text(c))

    def preview(self, ctx, p):
        _pc_only(ctx, self.title)
        self.schedule_check(ctx, p)
        c = counts()
        self._check(c)
        mine = p.get("job_id")
        run = jobs.running_stack()
        if run and int(run["id"]) != int(mine or 0):
            raise OpRefused("уже идёт управление стойкой (задание №%s)" % run["id"])
        warn = []
        if self.name != "stack.start":
            warn.append("объявление ботом Discord (#test-info, роль Beta Tester, EN / AR / RU), 3 минуты с отсчётом в игре, "
                        "штатное завершение GameServer")
        if self.name == "stack.stop":             # ★ ревизия 41 Н-6
            warn.append(STOP_START_NOTE)
        if self.name == "stack.restart" and not complete(c):
            warn.append("стойка сейчас неполная (%s) — рестарт остановит и поднимет её целиком" % counts_text(c))
        try:
            from core import bridge
            n = len(bridge.presence())
            if n:
                warn.append("в игре по данным моста: %d" % n)
        except Exception:
            warn.append("кто в игре по данным моста — не прочитано")
        argv, _env = build_argv(self.name)
        return {"text": "%s: restart_stack.py %s (сейчас: %s)" % (self.title, " ".join(argv[2:]), counts_text(c)),
                "warnings": warn, "expect": c}

    def apply(self, ctx, p, prev):
        word, _flags, _tick, want = MODES[self.name]
        own = p.get("job_id") is None
        try:
            jid = jobs.begin_direct(self.name, {"confirm": word}, ctx.login, ctx.user_id, ctx.role) if own else int(p["job_id"])
        except jobs.JobLocked as ex:
            raise OpRefused(str(ex))
        status, text = "failed", "сбой до запуска"
        try:
            before = counts()                    # перепроверка прямо перед запуском: состояние могло измениться после предпросмотра
            self._check(before)
            argv, env = build_argv(self.name)
            log = os.path.join(LOG_DIR, "%s_%s_%s.log" % (jid, word, time.strftime("%Y%m%d_%H%M%S")))
            rc, out = (RUN or _run_restart)(argv, env, log)
            after = counts()
            ok = (complete(after) if want == "full" else (after is not None and not total(after)))
            tail = [ln.rstrip() for ln in out.splitlines() if ln.strip()][-TAIL:]
            res = {"rc": rc, "before": counts_text(before), "after": counts_text(after), "lines": tail, "log": log, "job": jid}
            if rc == 0 and ok:
                status, text = "done", "%s: готово, код 0 (было: %s, стало: %s)" % (self.title, counts_text(before), counts_text(after))
                return {"before": {"counts": before}, "after": res, "message": text}
            if untouched(rc, out) and after is not None and after == before:      # ★ ревизия 41 С-3
                status = "refused"
                text = "restart_stack.py: код %d — стойка не тронута (%s): %s" % (rc, counts_text(after), (tail[-1] if tail else "")[:300])
                raise OpRefused(text)
            text = ("restart_stack.py: код %d, стойка: %s (ожидалось: %s) — проверьте журнал %s: %s"
                    % (rc, counts_text(after), "полная" if want == "full" else "процессов нет", log, (tail[-1] if tail else "")[:300]))
            raise StackFailed(text)
        except OpRefused as ex:
            status, text = "refused", str(ex)
            raise
        except StackFailed as ex:
            status, text = "failed", str(ex)
            raise
        except Exception as ex:
            status, text = "failed", "%s: %s" % (ex.__class__.__name__, str(ex)[:600])
            raise
        except BaseException as ex:               # ★ ревизия 41 Н-1: Ctrl+C — restart_stack мог уже остановить стойку
            status = "failed"
            text = ("прервано оператором (%s) — restart_stack.py мог уже объявить или остановить стойку, проверьте: "
                    "python asda_admin.py stack state" % ex.__class__.__name__)
            try:
                audit.write(ctx, self.name, "stack", {"confirm": word}, result="error", message=text)   # ops.run ловит только Exception
            except Exception:
                pass
            own = True                            # строку задания закрыть здесь: run_job до итога не дойдёт
            raise
        finally:
            if own:
                try:
                    jobs.finish(jid, status, text)
                except Exception:
                    pass                          # строку снимет job.release; сам итог уже в журнале adm.audit


@register
class StackRestart(_StackOp):
    name, title = "stack.restart", "Стойка: рестарт с объявлением"


@register
class StackStop(_StackOp):
    name, title = "stack.stop", "Стойка: остановка с объявлением"


@register
class StackStart(_StackOp):
    name, title = "stack.start", "Стойка: запуск остановленной"


# ------------------------------------------------------------------------------------------------------------------- задания
def schedulable(ctx):
    """Операции, которые роль может ставить в задания."""
    # ★ А5.3: слово подтверждения и второй фактор — и у операций вне стойки (maint.on / maint.off: confirm_word, two_factor)
    return [{"op": n, "title": o.title, "runner": o.schedule_runner, "stack": n.startswith("stack."),
             "confirm": MODES[n][0] if n in MODES else getattr(o, "confirm_word", ""),
             "two": n.startswith("stack.") or bool(getattr(o, "two_factor", False))}
            for n, o in sorted(REGISTRY.items()) if getattr(o, "schedule_runner", None) and ctx.can(o.perm)
            and not getattr(o, "schedule_hidden", False)]                # ★ ревизия 47: db.verify — только кнопкой карточки (нужен номер)


def _job_id(p):
    try:
        return int(p.get("id"))
    except (TypeError, ValueError):
        raise OpRefused("не указан номер задания")


@register
class JobAdd(Operation):
    name, title, perm, reversible = "job.add", "Задания: поставить", "jobs.manage", False

    def target(self, p):
        return "job:%s" % (p.get("op") or "")

    def preview(self, ctx, p):
        name = str(p.get("op") or "")
        op = REGISTRY.get(name)
        if not op:
            raise OpRefused("неизвестная операция %s" % name)
        runner = getattr(op, "schedule_runner", None)
        if not runner:
            raise OpRefused("операция %s не ставится в задания" % name)
        if not ctx.can(op.perm):
            raise OpRefused("нет права «%s»" % op.perm)
        try:
            at = jobs.parse_at(p.get("at"))
        except (TypeError, ValueError):
            raise OpRefused("неверное время запуска")
        now = jobs.utc_now()
        if at < now + datetime.timedelta(seconds=jobs.MIN_AHEAD_S) or at > now + datetime.timedelta(days=jobs.MAX_AHEAD_DAYS):
            raise OpRefused("время запуска — не раньше чем через минуту и не позже чем через %d дн." % jobs.MAX_AHEAD_DAYS)
        repeat = str(p.get("repeat") or "")
        if repeat not in jobs.REPEATS:
            raise OpRefused("неверный повтор (можно: разово, daily, weekly)")
        sub = p.get("params") or {}
        if not isinstance(sub, dict):
            raise OpRefused("параметры операции — объект JSON")
        sub = {k: v for k, v in sub.items() if k not in ("job_id", "totp", "totp_code")}
        check = getattr(op, "schedule_check", None)
        if check:
            check(ctx, sub)
        # ★ А5.3: второй фактор — у стойки и у операций с two_factor (включение режима обслуживания)
        two = (name.startswith("stack.") or bool(getattr(op, "two_factor", False))) and ctx.via == "web"
        if two and not str(p.get("totp") or "").strip():
            raise OpRefused("нужен свежий код второго фактора")
        warn = []
        if runner == "pc":
            warn.append("исполнитель — консоль ПК владельца (asda_admin.py jobs run-due): если ПК в срок не запустит его, задание "
                        "будет пропущено (поздно не выполняется)")
        if repeat:                                # ★ ревизия 41 Н-3: повтор не вечен (★ А5.7: срок — по операции, у бэкапа БД — год)
            days = jobs.repeat_days(name)
            warn.append("повтор: %s до %s (%d дн. от первого запуска), потом задание нужно поставить заново"
                        % (repeat, jobs.fmt_utc(jobs.repeat_limit(at, repeat, days)), days))
        if name == "stack.stop":
            warn.append(STOP_START_NOTE)
        if name in ("maint.on", "maint.off"):        # ★ А5.3: состояние входа проверяется в срок (служба), сейчас — только параметры
            t = str(sub.get("announce") or "").strip()
            warn.insert(0, "текст объявления: «%s»" % t if t else "без объявления в игру")
            if name == "maint.on" and sub.get("kick"):
                warn.append("в срок будут отключены мостом игроки вне 1…5000")
            warn.append("готовность SQL-части L09 и состояние режима проверяются в момент запуска задания")
        if name == "live.announce":                 # ★ ревизия 42 (мелочь): текст объявления — в окне подтверждения
            t = str(sub.get("text") or "").strip()
            warn.insert(0, "текст объявления: «%s»" % t)
            from domains import live as _live
            if _live.cp1251_lossy(t):
                warn.append(_live.CP1251_WARN)
            if sub.get("discord"):                  # ★ А7.4: «и в Discord» в задании — канал, роль, срок и сам текст в окне подтверждения
                from domains import outbox as _ob
                _ob.refuse_repeat(repeat)           # ★ р76 К4 (решение координатора): с Discord — только разовое задание
                dc = _ob.check(ctx, sub["discord"], t)
                warn += _ob.describe(dc) + ["текст в Discord:\n" + _ob.preview_text(dc),
                                            "срок годности и пределы частоты считаются в момент запуска задания"]
        return {"text": "задание «%s» на %s (исполнитель: %s)" % (op.title, jobs.fmt_utc(at), runner), "warnings": warn,
                "op": name, "sub": sub, "at": at.isoformat(sep=" "), "runner": runner, "repeat": repeat, "two": two}

    def apply(self, ctx, p, prev):
        if prev["two"]:
            auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())
        at = datetime.datetime.fromisoformat(prev["at"])
        jid = jobs.add(prev["op"], prev["sub"], prev["runner"], at, prev["repeat"], str(p.get("note") or ""), ctx.login,
                       ctx.user_id, ctx.role)
        return {"before": None, "after": {"job": jid, "op": prev["op"], "at": prev["at"], "runner": prev["runner"], "repeat": prev["repeat"]},
                "message": "задание №%d поставлено: %s на %s" % (jid, prev["op"], jobs.fmt_utc(at))}


@register
class JobCancel(Operation):
    name, title, perm, reversible = "job.cancel", "Задания: отменить", "jobs.manage", False

    def target(self, p):
        return "job:%s" % p.get("id")

    def preview(self, ctx, p):
        j = jobs.get(_job_id(p))
        if not j:
            raise OpRefused("задания №%s нет" % p.get("id"))
        op = REGISTRY.get(j["op"])
        if op and not ctx.can(op.perm):
            raise OpRefused("нет права «%s»" % op.perm)
        if j["status"] != "pending":
            raise OpRefused("задание №%d уже не ждёт (статус %s)" % (j["id"], j["status"]))
        return {"text": "отменить задание №%d «%s» на %s" % (j["id"], j["op"], jobs.fmt_utc(j["run_at"])), "id": j["id"]}

    def apply(self, ctx, p, prev):
        if not jobs.cancel(prev["id"]):
            j = jobs.get(prev["id"]) or {"status": "?"}
            raise OpRefused("задание №%d уже не ждёт (статус %s)" % (prev["id"], j["status"]))
        return {"before": {"status": "pending"}, "after": {"status": "cancelled"}, "message": "задание №%d отменено" % prev["id"]}


@register
class JobRelease(Operation):
    name, title, perm, reversible = "job.release", "Задания: снять зависшее «идёт»", "jobs.release", False

    def target(self, p):
        return "job:%s" % p.get("id")

    def preview(self, ctx, p):
        j = jobs.get(_job_id(p))
        if not j:
            raise OpRefused("задания №%s нет" % p.get("id"))
        if j["status"] != "running":
            raise OpRefused("задание №%d не в состоянии «идёт» (статус %s)" % (j["id"], j["status"]))
        if str(p.get("confirm") or "") != "release":
            raise OpRefused("нужно подтверждение: ключ --confirm-release (сначала убедитесь, что restart_stack.py не работает)")
        return {"text": "снять «идёт» с задания №%d «%s» (начато %s на %s)" % (j["id"], j["op"], jobs.fmt_utc(j["started_at"]), j["host"]),
                "warnings": ["если restart_stack.py на самом деле ещё работает, второе управление стойкой станет возможным"], "id": j["id"]}

    def apply(self, ctx, p, prev):
        if not jobs.release(prev["id"], ctx.login):
            raise OpRefused("задание №%d не в состоянии «идёт»" % prev["id"])
        return {"before": {"status": "running"}, "after": {"status": "failed"}, "message": "задание №%d снято вручную" % prev["id"]}
