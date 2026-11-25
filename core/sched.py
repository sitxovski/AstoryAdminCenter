# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""sched.py — периодические задачи службы админ-центра (волна А1, 18.11.2026; решение владельца: «ежедневный пересчёт рейтинга
чести службой панели»). До этого периодических задач у службы не было (только прогрев при старте, api/server.serve).

ЗАДАЧИ (DAILY): имя операции core/ops → время суток (по часам сервера). Каждая выполняется ОДИН раз в сутки после своего времени:
  * econ.snapshot 00:05 — ★ А6.3 (21.11.2026): суточный снимок золота на руках в AsdaAdmin (adm.EconDaily; «снимок − журналы» = неучтённое,
    золото с моба журналов не пишет); игровые базы только читаются.
  * ac.daily 00:20 — ★ А6.6 (22.11.2026): суточный отчёт античита за вчерашние сутки (тот же код AstoryServer/Tools/Anticheat/ac_daily_report, журналы
    стойки — локально, база — asda_admin) в AsdaAdmin (adm.AcDaily), пороги прежние; после снимка золота, задачи потока идут по очереди.
  * reports.purge 01:00 — ★ А6.11 (ревизия 67 С-2, 22.11.2026): байты скриншотов закрытых жалоб старше 90 суток после закрытия → пусто
    (adm.ReportFilePurge; имя, тип, размер и sha256 остаются).
  * release.prune 01:10 — ★ А7.1 (ревизия 74 М-4, 23.11.2026): оставить 100 последних разных снимков ПК раздела «Выпуски» (adm.ReleasePcPrune).
  * camp.rank_rebuild 06:10 — пересчёт рейтинга чести (EXEC adm.CampPointRank = штатный UP_CampPointRank; на dev его никто не
    запускал — research_a1_char_rest.md §3), после суточной границы ремесла 06:00 (ASDA_LimitationDailyReset 06:02).
ЖУРНАЛ: задача идёт обычной операцией ops.run от имени «service:daily» (роль owner, путь sched) — в adm.audit пишутся итог «ok»,
  отказ или сбой, как у действий оператора. «Уже сделано сегодня» — по журналу (запись ok этого имени после сегодняшнего времени
  запуска), поэтому перезапуск службы не даёт второго пересчёта.
ПОТОК: один поток-демон, проверка раз в CHECK_S; ошибка задачи не останавливает поток (печать в журнал службы).
★ А5.1 (20.11.2026): в том же потоке — задания adm.job с исполнителем «служба» (jobs_once → core/jobs.run_due; объявления в игру и пр.).
  Задания стойки (исполнитель «ПК») служба не исполняет — их берёт консоль ПК (asda_admin.py jobs run-due).
★ А7.5 (23.11.2026): в том же потоке — поиск событий для Telegram владельцу раз в notify.SCAN_S (domains/notify.scan_due: ставит строки в
  adm.Outbox, шлёт отправитель на ПК; отметка службы adm.NotifyBeat — по ней ПК видит, что служба жива).
Запускается только на сервере (api/server.serve при cfg.on_server). Побочных эффектов при импорте нет.
"""
import datetime
import re
import threading
import time
import traceback

DAILY = [("camp.rank_rebuild", datetime.time(6, 10)),
         ("econ.snapshot", datetime.time(0, 5)),   # ★ А6.3: суточный снимок золота на руках (adm.EconDaily, domains/econ.py)
         ("ac.daily", datetime.time(0, 20)),       # ★ А6.6: суточный отчёт античита за вчера (adm.AcDaily, domains/acdaily.py RUN_AT)
         ("reports.purge", datetime.time(1, 0)),   # ★ А6.11 ревизия 67 С-2: срок хранения скриншотов жалоб (adm.ReportFilePurge, domains/reports.py)
         ("release.prune", datetime.time(1, 10))]  # ★ А7.1 р74 М-4: 100 последних снимков ПК раздела «Выпуски» (adm.ReleasePcPrune, domains/releases.py)
LOGIN = "service:daily"
CHECK_S = 60
RETRY_S = 3600                 # неудачную задачу повторять не чаще раза в час (не забивать журнал отказами)
_started = []
_tried = {}                    # имя → время последней попытки (monotonic)


def due(now, at, last_ok):
    """Пора ли запускать: сегодняшнее время запуска наступило, и после него успешного запуска не было."""
    start = datetime.datetime.combine(now.date(), at)
    return now >= start and (last_ok is None or last_ok < start)


_FAIL_RX = re.compile(r"запись №(\d+) НЕ зафиксирована")
_quiet = {}                    # имя → журнал недоступен: уже сообщили (дальше — одна строка раз в RETRY_S, без трассировки)


def last_ok(rows):
    """Время последнего УСПЕШНОГО запуска по записям журнала (новые сверху). ★ ревизия 26 М-3: запись ok, у которой фиксация в игровой
    базе не прошла (ops._finish пишет следом error «запись №N НЕ зафиксирована…»), успехом не считается."""
    failed = {int(m.group(1)) for r in rows if r["result"] == "error" for m in [_FAIL_RX.search(r.get("message") or "")] if m}
    for r in rows:
        if r["result"] == "ok" and int(r["id"]) not in failed:
            v = r["at"]
            return v if isinstance(v, datetime.datetime) else datetime.datetime.fromisoformat(str(v)[:19])
    return None


def _last_ok(name):
    from . import audit
    return last_ok(audit.query(name, LOGIN, "", None, 50, None))


def run_once(now=None, last=None, runner=None):
    """Один проход: выполнить задачи, которым пора. → [(имя, итог)]. last / runner — подстановки для самотеста."""
    from . import ops
    now = now or datetime.datetime.now()
    last = last or _last_ok
    runner = runner or (lambda name: ops.run(ops.Ctx(None, LOGIN, "owner", "", "sched"), name, {}, dry=False))
    out = []
    for name, at in DAILY:
        if now < datetime.datetime.combine(now.date(), at):
            continue                                 # до времени запуска журнал не спрашиваем
        t = time.monotonic()
        if name in _tried and t - _tried[name] < RETRY_S:
            continue                                 # ★ ревизия 26 М-4: попытка (и сбой журнала) — не чаще раза в RETRY_S
        try:
            lo = last(name)
        except Exception as ex:                      # журнал AsdaAdmin недоступен: одна строка, без трассировки, повтор через RETRY_S
            _tried[name] = t
            if not _quiet.get(name):
                print("%s задача %s: журнал недоступен (%s: %s) — повтор через %d мин" % (
                    now.strftime("%Y-%m-%d %H:%M:%S"), name, ex.__class__.__name__, str(ex)[:200], RETRY_S // 60))
            _quiet[name] = True
            out.append((name, "журнал недоступен"))
            continue
        _quiet[name] = False
        if not due(now, at, lo):
            continue
        _tried[name] = t
        try:
            r = runner(name)
            out.append((name, r.get("message") or "ok"))
            print("%s задача %s: %s" % (now.strftime("%Y-%m-%d %H:%M:%S"), name, r.get("message")))
        except Exception as ex:                      # отказ/сбой уже в журнале (ops.run пишет сам); поток не падает
            out.append((name, "%s: %s" % (ex.__class__.__name__, ex)))
            print("%s задача %s не выполнена: %s" % (now.strftime("%Y-%m-%d %H:%M:%S"), name, ex))
            if ex.__class__.__name__ != "OpRefused":
                traceback.print_exc()
    return out


_backfilled = []              # ★ ревизия 56 Н-3: досчёт пропущенных суток в этом процессе закончен (все сутки посчитаны)
_backfill_next = [0.0]         # ★ ревизия 57 (мелочь 6): не раньше этого времени (monotonic) — повтор отказавших суток


def backfill_once(today=None, missing=None, runner=None, mono=None):
    """★ ревизия 56 Н-3 (22.11.2026): после старта службы — суточный отчёт за сутки от позавчера на acdaily.BACKFILL_DAYS назад, за которые
    нет НОЧНОГО отчёта (служба лежала в 00:20). Вчера считает DAILY (поэтому звать ПОСЛЕ run_once: досчёт после 00:20 иначе засчитался бы
    DAILY как «сегодня уже сделано»). ★ ревизия 57 (мелочь 6): «сделано» — только когда все сутки посчитаны; отказавшие (журнал занят,
    замок, база) — повтор не чаще RETRY_S. → [(ГГГГММДД, итог)]. missing / runner / mono — подстановки самотеста."""
    from . import ops
    t = time.monotonic() if mono is None else mono
    if _backfilled or t < _backfill_next[0]:
        return []
    today = today or datetime.date.today()
    try:
        if missing is None:
            from domains import acdaily
            missing = acdaily.missing_days(today)
    except Exception as ex:                          # журнал недоступен — повтор при следующем проходе
        print("%s досчёт суточного отчёта: журнал недоступен (%s: %s)" % (time.strftime("%Y-%m-%d %H:%M:%S"), ex.__class__.__name__, str(ex)[:200]))
        _backfill_next[0] = t + RETRY_S
        return []
    runner = runner or (lambda day: ops.run(ops.Ctx(None, LOGIN, "owner", "", "sched"), "ac.daily", {"date": day}, dry=False))
    out, failed = [], 0
    for day in missing:
        try:
            r = runner(day)
            out.append((day, r.get("message") or "ok"))
        except Exception as ex:                      # отказ / сбой — в журнале (ops.run пишет сам); остальные сутки считаются
            out.append((day, "%s: %s" % (ex.__class__.__name__, ex)))
            failed += 1
        print("%s досчёт суточного отчёта за %s: %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), day, out[-1][1]))
    if failed:
        _backfill_next[0] = t + RETRY_S
    else:
        _backfilled.append(True)
    return out


_jobs_quiet = []               # ★ А5.1: журнал заданий недоступен — уже сообщили (до первого успешного прохода)


def jobs_once(now=None, run_due=None, long=None):
    """★ А5.1 (20.11.2026): один проход заданий adm.job с исполнителем «служба» (core/jobs.py: пропущенные → missed, наступившие —
    ops.run от имени автора) → [(номер, статус, текст)]. Сбой журнала — одна строка до восстановления, поток не падает.
    ★ ревизия 47 С-2: long — False обычные задания (поток sched), True долгие (поток sched-long: бэкап БД), None — все."""
    from . import jobs
    try:
        fn = run_due or jobs.run_due
        out = fn("service", now) if long is None else fn("service", now, long=long)
    except Exception as ex:
        if not _jobs_quiet:
            print("%s задания: журнал недоступен (%s: %s)" % (time.strftime("%Y-%m-%d %H:%M:%S"), ex.__class__.__name__, str(ex)[:200]))
        _jobs_quiet[:] = [True]
        return []
    _jobs_quiet[:] = []
    for jid, st, text in out:
        print("%s задание №%s: %s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), jid, st, (text or "")[:300]))
    return out


def start():
    """Поток задач (один на процесс)."""
    if _started:
        return
    _started.append(True)

    def loop():
        while True:
            try:
                run_once()
            except Exception:
                traceback.print_exc()
            try:
                backfill_once()                      # ★ ревизия 56 Н-3: после DAILY (вчера), один раз за процесс
            except Exception:
                traceback.print_exc()
            try:
                jobs_once(long=False)
            except Exception:
                traceback.print_exc()
            try:
                from domains import notify           # ★ А7.5: события для Telegram владельцу (раз в notify.SCAN_S, сбой — одна строка)
                notify.scan_due()
            except Exception:
                traceback.print_exc()
            time.sleep(CHECK_S)

    def loop_long():
        # ★ ревизия 47 С-2: долгие задания (бэкап БД, перепроверка) — своим потоком: обычные (объявления, режим обслуживания) их не ждут и
        #   не становятся «пропущенными» через GRACE_S, пока идёт бэкап
        while True:
            try:
                jobs_once(long=True)
            except Exception:
                traceback.print_exc()
            time.sleep(CHECK_S)
    threading.Thread(target=loop, daemon=True, name="sched").start()
    threading.Thread(target=loop_long, daemon=True, name="sched-long").start()
