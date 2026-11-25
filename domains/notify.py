# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""notify.py — уведомления владельцу в Telegram (шаг А7.5, 23.11.2026; решение владельца А7 №3 — только владельцу, через бота @@@ASTORY_TELEGRAM_BOT@@,
только отправка, с ПК; канала для игроков нет; флаги суточного отчёта античита в Telegram НЕ идут — только экран, решение А6 №9; разбор
Reports/admin_center/research_a7_releases_20261123.md §3 А7.5; отчёт impl_a7_releases_20261123.md §А7.5).

КАК ИДЁТ СООБЩЕНИЕ. Сервер Telegram не видит (разбор А7 §0 п.1). Служба панели раз в SCAN_S ищет события (scan_due из потока core/sched) и
ставит строку в ту же очередь adm.Outbox (transport = 'telegram', adm.TgNotifyPut — выключатели, склейка, подавление повторов и пределы
частоты там, под замком). Отправитель на ПК (AstoryAdminCenter/DiscordBot/tg_bot.py, цикл в боте Oracle) забирает её процедурой adm.TgClaim
логином asda_reports и шлёт ОДНИМ методом Bot API — sendMessage — в чат владельца. Токен и номер чата — только на ПК (telegram.env рядом с
ботом), в панели и в базе их нет. Апдейты бота отправитель не читает и настройки бота не трогает: этим ботом агенты задают вопросы владельцу.
СОБЫТИЯ — RULES (каждое: зачем, срочность, пауза между повторами, напоминание). «Тихие часы»: не-срочные (prio low) с 23:00 до 08:00 по часам
  ПК уходят без звука, но не задерживаются — так не теряется ни одно сообщение, а ночью звенит только срочное.
ВЫКЛЮЧАТЕЛИ — adm.NotifyRule: общий '_master' (нет строки — ВЫКЛЮЧЕН, до слова владельца ничего не ставится) и у каждого события свой (нет
  строки — включён). Меняет только владелец операцией notify.rule.set. Механики в ini нет: пороги, паузы и список событий — здесь, в коде.
ОПЕРАЦИИ (журнал adm.audit; право notify.manage — только owner): notify.rule.set, telegram.test (проверочная запись: отправитель вызывает
  только getMe — сообщения нет), telegram.ping (НАСТОЯЩЕЕ проверочное сообщение в чат владельца — нажимает владелец).
Побочных эффектов при импорте нет.
"""
import datetime
import re
import socket
import time
import traceback

from core import db
from core.ops import Operation, OpRefused, register

MASTER = "_master"
SCAN_S = 300                   # проход поиска событий службой
TTL_MIN = 720                  # уведомление старше 12 ч не отправляется («просрочено»): ПК был выключен
PER_HOUR, PER_DAY = 10, 40     # = adm.TgNotifyPut (здесь — для экрана)
QUIET_FROM, QUIET_TO = 23, 8   # тихие часы по часам ПК (tg_bot.QUIET — самотест сверяет)
LOGDROP_PCT = 80               # квота LogDrop
REPORT_STALE_H = 12            # жалоба без «взять» дольше — уведомление (один раз на жалобу)
REPORT_MAX_AGE_D = 7           # старее — не напоминаем (старый хвост до включения не шлётся пачкой)
CRASH_NEW_H = 48               # место падения впервые пришло в панель не раньше — «новое» (один раз на место)
BAD_SCANS = 2                  # процесс не работает столько проходов подряд — уведомление (рестарт стойки длится дольше прохода — не дребезг)
STACK_BAD_SCANS = 3            # ★ ревизия 77 В-2: у «стойка не поднялась» — 3 прохода (15 мин): запасной предел, если отметки рестарта нет
STACK_QUIET_MIN = 15           # ★ р77 В-2: после успешного stack.* панели — столько минут тишины (стойка поднимается)
STACK_ACTIVITY_FILE = r"@@ASTORY_SERVER_ROOT@@\stack_activity.txt"   # ★ р77 В-2: отметка restart_stack.py (= его ACTIVITY_FILE, самотест сверяет)
URGENT_EVENTS = ("stack", "eac_down", "backup_failed")  # ★ р77 В-1: вне общего предела (= adm.TgNotifyPut), у каждого свой
URGENT_PER_HOUR = 6
DAILY_FAIL_GAP = 1440          # ★ р77 М-1: сбой суточной задачи — одно уведомление в сутки на задачу (и «снова выполнена»)
REMIND_HOUR = 10               # ★ р77 К-2: напоминания (подпись, LogDrop) — в 10:00 по часам сервера (= часам ПК владельца)
SUMMARY_DAYS = 7               # ★ р77 М-4: сводка при включении общего — разовые события за столько суток
CRASH_BATCH = 10               # мест падения в одном сообщении (остальные — числом)
PC_STALE_MIN = 10              # отправитель на ПК не отмечался дольше — предупреждение на экране
PANEL_STALE_MIN = 15           # = tg_bot.PANEL_STALE_MIN: служба не отмечалась дольше — ПК шлёт «служба панели не отвечает»
TEXT_MAX = 1500
ERR_MAX = 160                  # хвост сообщения операции в уведомлении
PAGE_MAX = 50
NOT_INSTALLED = "таблиц Telegram нет (sql/adminc_29_telegram.sql не установлен)"

# ключ → подпись, зачем (почему владельцу стоит знать сразу), срочность (urgent — всегда со звуком, low — ночью без звука), пауза между
# сообщениями одного и того же (мин), напоминание о незакрытом состоянии (мин, 0 — нет), где ищется
RULES = [
    {"key": "panel_down", "title": "служба панели не отвечает",
     "why": "служба админ-центра не отмечалась 15 мин или база AsdaAdmin не отвечает с ПК — задания, объявления и отчёты стоят. Без службы "
            "этот же канал молчал бы, поэтому событие ищет ПК",
     "prio": "urgent", "gap": 30, "remind": 0, "where": "pc"},
    {"key": "task_failed", "title": "задача или задание не выполнены",
     "why": "суточная задача службы (снимок золота, отчёт античита, рейтинг) или задание планировщика упали, получили отказ или пропущены. "
            "Суточная задача — одно уведомление в сутки и «снова выполнена»",
     "prio": "normal", "gap": 60, "remind": 0, "where": "service"},
    {"key": "stack", "title": "стойка не поднялась",
     "why": "рестарт, остановка или запуск стойки закончились сбоем либо процессы игры не работают три прохода подряд вне управления стойкой "
            "(в том числе вне прямого restart_stack.py) — игроки не могут играть",
     "prio": "urgent", "gap": 30, "remind": 360, "where": "service"},
    {"key": "eac_down", "title": "EacServer не работает",
     "why": "процесс AsdaEacServer не найден или не слушает свои порты два прохода подряд — античит не проверяет вход",
     "prio": "urgent", "gap": 30, "remind": 360, "where": "service"},
    {"key": "backup_failed", "title": "бэкап базы не удался",
     "why": "бэкап или его перепроверка закончились сбоем — без бэкапа нечем откатывать базы",
     "prio": "normal", "gap": 60, "remind": 0, "where": "service"},
    {"key": "changeset_apply", "title": "итог серверной половины набора изменений",
     "why": "применение или откат серверной половины набора (рестарт стойки) закончились — итог нужен сразу, даже если запускали заданием",
     "prio": "normal", "gap": 0, "remind": 0, "where": "service"},
    {"key": "logdrop_quota", "title": "LogDrop занят больше 80 %",
     "why": "при 100 % приёмник перестаёт принимать журналы и падения клиента — чистка .alog только кнопкой владельца",
     "prio": "low", "gap": 60, "remind": 1440, "where": "service"},
    {"key": "release_sign", "title": "подпись выпуска истекает",
     "why": "подписи указателя alpha, launcher или version.json осталось меньше 3 суток, она просрочена или не сошлась — после срока лаунчер "
            "не обновит игру",
     "prio": "normal", "gap": 60, "remind": 1440, "where": "service"},
    {"key": "crash_new", "title": "новое место падения клиента",
     "why": "впервые пришли группы падений с новой подписью места — все новые места прохода одним сообщением, известные места не шлются",
     "prio": "low", "gap": 0, "remind": 0, "where": "service"},
    {"key": "report_stale", "title": "жалоба ждёт дольше 12 ч",
     "why": "жалобу игрока через /report никто не взял в работу 12 ч — один раз на жалобу, только номер и категория",
     "prio": "low", "gap": 0, "remind": 0, "where": "service"},
]
RULE = {r["key"]: r for r in RULES}
EVENTS = tuple(r["key"] for r in RULES)
SERVICE_EVENTS = tuple(r["key"] for r in RULES if r["where"] == "service")
STACK_OPS = ("stack.restart", "stack.stop", "stack.start")
BACKUP_OPS = ("db.backup", "db.verify")
CS_OPS = ("shop.cs_server_apply", "shop.cs_server_rollback")
CORE_KEYS = ("login", "dbm", "overlap", "channel", "itemrelay", "operation", "gs", "gs_ch2", "gs_indun", "npc", "npc_ch2", "npc_indun",
             "relay", "relay_ch2", "relay_indun")          # процессы игры (domains/status.STACK); EacServer — своё событие
SENT = (0, 1, 2, 6, 7)          # итог adm.TgNotifyPut «учтено»: поставлено, склеено, подавлено паузой (уже сообщалось) или пределом частоты (одно
                                # событие — одно число в счётчике «не поставлено из-за предела», без повторных попыток каждый проход)
RETRY = (4,)                    # поля не прошли проверку базы — не учтено, разовое событие попробовать в следующий проход
LOCAL_TITLES = {"panel": "сообщение ПК: служба панели не отвечает", "panel_up": "сообщение ПК: служба снова отмечается",
                "db": "сообщение ПК: база не отвечает", "db_up": "сообщение ПК: база снова отвечает"}   # ★ р77 К-3: строки kind local
STATUS = {0: "queued", 1: "claimed", 2: "sent", 3: "failed", 4: "cancelled", 5: "expired", 6: "test"}
TEST_MODES = ("check", "selftest")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


_URL = re.compile(r"(?i)\b(https?|ftp)://")
_WWW = re.compile(r"(?i)\bwww\.")
_TAG = re.compile(r"([@#/])(?=\w)")
ZW = "\u200b"


def clean(s, n=ERR_MAX, keep_nl=False):
    """Хвост сообщения операции для уведомления: одна строка, без адресов IP и почты, ссылки, @имена и #теги разорваны невидимым пробелом
    (★ р77 К-1: Telegram сам делает их ссылками), не длиннее n. keep_nl — сохранить переводы строк (★ р78 К-6: сводка М-4 — построчно)."""
    s = str(s or "")
    if keep_nl:
        return "\n".join(clean(x, n) for x in s.split("\n"))[:n]
    s = _CTRL.sub(" ", s).replace("\n", " ")
    s = _EMAIL.sub("…@…", _IPV4.sub("x.x.x.x", s))
    s = _URL.sub(lambda m: m.group(1) + ":" + ZW + "//", s)
    s = _WWW.sub(lambda m: m.group(0)[:3] + ZW + ".", s)
    s = _TAG.sub(lambda m: m.group(1) + ZW, s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def full_text(text, repeats=0, supp=0, over=0):
    """★ р77 М-3: текст уведомления с хвостом из столбцов (тот же, что собирает отправитель — tg_bot.compose)."""
    out = (text or "").strip()
    if int(supp or 0) > 0:
        out += "\n(ещё повторов этого события за паузу: %d)" % int(supp)
    if int(over or 0) > 0:
        out += "\n(уведомлений не поставлено из-за предела частоты: %d)" % int(over)
    if int(repeats or 0) > 0:
        out += "\n(повторов до отправки: %d)" % int(repeats)
    return out


def _iso(v):
    return v.isoformat(sep=" ") if hasattr(v, "isoformat") else (str(v) if v is not None else None)


def _installed(cn):
    return bool(db.admin_rows(cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.NotifyRule', N'U') IS NOT NULL AND OBJECT_ID(N'adm.TgNotifyPut', N'P') IS NOT NULL"))


def _read(fn, factory=None):
    try:
        cn = (factory or db.admin)()
    except db.DbError as ex:
        raise OpRefused("Telegram: база панели не прочитана: %s" % ex)
    try:
        return fn(cn)
    except db.DbError as ex:
        raise OpRefused("Telegram: база панели не прочитана: %s" % ex)
    finally:
        cn.close()


def rules_state(cn):
    """Выключатели: {'_master': bool, ключ: bool} — нет строки: общий выключен, событие включено."""
    rows = {r["event_key"]: r for r in db.admin_rows(cn, "SELECT event_key, enabled, changed_by, changed_utc FROM adm.NotifyRule")}
    out = {MASTER: bool(rows.get(MASTER, {}).get("enabled", False))}
    for k in EVENTS:
        out[k] = bool(rows[k]["enabled"]) if k in rows else True
    return out, rows


# ── поиск событий (служба) ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
class Sources:
    """Откуда берутся данные. Подменяется в самотесте (сети, SSH и PowerShell там нет)."""

    def status(self):
        from domains import status
        return status.snapshot(force=True)

    def logdrop(self):
        from domains import crashes
        return crashes.logdrop_stats()

    def releases(self):
        from domains import releases
        return releases.outside()

    def resign_hint(self, name):
        from domains import releases
        return releases.resign_hint(name)

    def op_title(self, name):
        from core import ops
        o = ops.REGISTRY.get(name)
        return o.title if o else name

    def host(self):
        return socket.gethostname()

    def activity(self):
        """★ р77 В-2: отметка restart_stack.py на сервере (нет файла — пусто)."""
        try:
            with open(STACK_ACTIVITY_FILE, encoding="ascii", errors="replace") as f:
                return f.read(400)
        except OSError:
            return ""

    def local_now(self):
        return datetime.datetime.now()


ACTIVITY_MAX_H = 13             # ★ р78 К-3: срок отметки дальше — не верим (у restart_stack.py самый долгий — 12 ч «stopped»)


def activity_until(text):
    """«phase=… until=ГГГГММДДTЧЧММССZ …» → datetime UTC (наивный) или None."""
    m = re.search(r"\buntil=(\d{8}T\d{6})Z", text or "")
    try:
        return datetime.datetime.strptime(m.group(1), "%Y%m%dT%H%M%S") if m else None
    except ValueError:
        return None


class Scan:
    """Один проход: память событий (adm.NotifyState), постановка (adm.TgNotifyPut). Итог — список (событие, ключ, итог)."""

    def __init__(self, cn, src, by="service:notify"):
        self.cn, self.src, self.by, self.out = cn, src, by, []
        self.now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        self.state = {(r["event_key"], r["item_key"]): r for r in db.admin_rows(
            cn, "SELECT event_key, item_key, active, val, sent, first_utc, changed_utc, last_put_utc, suppressed FROM adm.NotifyState")}

    def st(self, ev, key):
        return self.state.get((ev, key)) or {}

    def mark(self, ev, key, active=None, val=None, sent=None):
        db.admin_rows(self.cn, "SET NOCOUNT ON; EXEC adm.TgStateSet ?, ?, ?, ?, ?",
                      (ev, key[:100], None if active is None else (1 if active else 0), val, None if sent is None else (1 if sent else 0)))
        r = self.state.setdefault((ev, key), {"active": False, "val": None, "sent": False, "last_put_utc": None})
        if active is not None:
            r["active"] = bool(active)
        if sent is not None:
            r["sent"] = bool(sent)
        r["val"] = val

    def fire(self, ev, key, text, gap=None, quiet=None):
        rule = RULE[ev]
        q = (rule["prio"] == "low") if quiet is None else quiet
        r = db.admin_rows(self.cn, "SET NOCOUNT ON; DECLARE @id INT, @code INT; EXEC adm.TgNotifyPut ?, ?, ?, ?, ?, ?, ?, ?, @id OUTPUT, @code OUTPUT; "
                                   "SELECT @code AS code, @id AS id",
                          (ev, key[:100], rule["title"][:100], clean(text, TEXT_MAX, keep_nl=True), rule["gap"] if gap is None else gap,
                           1 if q else 0, TTL_MIN, self.by))[0]
        code = int(r["code"])
        if code in (0, 6) or (code in (1, 2) and ev not in URGENT_EVENTS):   # ★ р77 М-2 / р78 К-4: упор в предел — попытка (кроме срочных)
            self.state.setdefault((ev, key), {"active": False, "val": None, "sent": False})["last_put_utc"] = self.now
        self.out.append((ev, key, code))
        return code

    def due_remind(self, ev, key):
        """Пора напомнить: прошло RULE.remind (★ р77 М-2: попытки, упёршиеся в предел, тоже считаются)."""
        m = RULE[ev]["remind"]
        last = self.st(ev, key).get("last_put_utc")
        return bool(m) and last is not None and (self.now - last).total_seconds() >= m * 60

    def due_daily(self, ev, key):
        """★ р77 К-2: напоминание раз в сутки в REMIND_HOUR по местным часам (последнее — до сегодняшних 10:00 и не меньше 12 ч назад)."""
        last = self.st(ev, key).get("last_put_utc")
        if last is None:
            return False
        loc = self.src.local_now()
        if loc.hour < REMIND_HOUR:
            return False
        mark_utc = loc.replace(hour=REMIND_HOUR, minute=0, second=0, microsecond=0) - (loc - self.now)   # 10:00 местного → в часах SQL (UTC)
        return last < mark_utc and (self.now - last).total_seconds() >= 12 * 3600

    def cursor(self, name):
        r = self.state.get(("_cursor", name))
        return None if r is None or r.get("val") is None else int(r["val"])


SENT_OK = (0, 6)               # уведомление действительно поставлено (или склеено с ещё не отправленным)


def _audit(S):
    """Журнал adm.audit после курсора: суточные задачи службы, стойка, бэкап, наборы изменений. Первый проход — только курсор (старое не шлётся)."""
    from core import sched
    mx = int(db.admin_rows(S.cn, "SELECT ISNULL(MAX(id), 0) AS m FROM adm.audit")[0]["m"])
    cur = S.cursor("audit")
    if cur is None:
        S.mark("_cursor", "audit", val=mx)
        return
    acts = STACK_OPS + BACKUP_OPS + CS_OPS
    rows = db.admin_rows(S.cn, "SELECT TOP 200 id, login, action, target, result, message FROM adm.audit WHERE id > ? AND id <= ? AND "
                               "(login = ? OR action IN (%s)) ORDER BY id" % ", ".join("?" * len(acts)), (cur, mx, sched.LOGIN) + acts)
    for r in rows:
        act, res, msg = r["action"], r["result"], clean(r["message"])
        if r["login"] == sched.LOGIN and act not in acts:
            key = "daily:" + act
            st = S.st("task_failed", key)
            if res in ("error", "refused"):
                # ★ р77 М-1: служба повторяет задачу раз в час — одно уведомление в сутки на задачу
                code = S.fire("task_failed", key, "суточная задача службы «%s» (%s) — %s: %s"
                              % (S.src.op_title(act), act, "сбой" if res == "error" else "отказ", msg or "без текста"), gap=DAILY_FAIL_GAP)
                S.mark("task_failed", key, active=True, sent=bool(st.get("sent")) or code in SENT_OK)
            elif res == "ok" and st.get("active"):
                if st.get("sent"):
                    S.fire("task_failed", key + ":up", "суточная задача службы «%s» (%s) снова выполнена." % (S.src.op_title(act), act), gap=0)
                S.mark("task_failed", key, active=False, sent=False)
        elif act in STACK_OPS and res == "error":
            S.fire("stack", "op:" + act, "«%s» — сбой, стойка могла остаться не поднятой: %s. Проверьте раздел «Состояние»."
                   % (S.src.op_title(act), msg or "без текста"))
        elif act in BACKUP_OPS and res == "error":
            S.fire("backup_failed", act, "«%s» — сбой: %s" % (S.src.op_title(act), msg or "без текста"))
        elif act in CS_OPS and res in ("ok", "error"):
            S.fire("changeset_apply", "%s:%s:%s" % (act, r["target"] or "", r["id"]), "%s, %s — %s: %s"
                   % (S.src.op_title(act), r["target"] or "набор ?", "готово" if res == "ok" else "СБОЙ", msg or "без текста"))
    S.mark("_cursor", "audit", val=int(rows[-1]["id"]) if len(rows) == 200 else mx)


def _jobs(S):
    """Задания adm.job, закончившиеся после курсора: пропущено — любое, сбой и отказ — кроме стойки, бэкапа и наборов (их итог — из журнала).
    ★ р77 К-4: хвост итога задания в текст не идёт (у выдач и подарков там может быть имя персонажа) — подробности на экране «Задания»."""
    t0 = datetime.datetime(2000, 1, 1)
    mx = db.admin_rows(S.cn, "SELECT MAX(finished_at) AS m FROM adm.job")[0]["m"]
    cur = S.cursor("job")
    mx_s = int((mx - t0).total_seconds()) if mx else 0
    if cur is None:
        S.mark("_cursor", "job", val=mx_s)
        return
    since = t0 + datetime.timedelta(seconds=cur)
    rows = db.admin_rows(S.cn, "SELECT TOP 100 id, op, status, finished_at FROM adm.job WHERE finished_at > ? AND status IN ('failed', 'refused', 'missed') "
                               "ORDER BY finished_at, id", (since,))
    covered = STACK_OPS + BACKUP_OPS + CS_OPS
    for r in rows:
        if r["status"] != "missed" and (r["op"] in covered or str(r["op"]).startswith("stack.")):
            continue
        what = {"missed": "пропущено (исполнитель не взял его вовремя — ПК выключен или служба стояла)", "failed": "сбой", "refused": "отказ"}[r["status"]]
        S.fire("task_failed", "job:" + r["op"], "задание №%d «%s» — %s. Подробности — раздел «Задания»." % (r["id"], S.src.op_title(r["op"]), what))
    last = rows[-1]["finished_at"] if len(rows) == 100 else mx
    S.mark("_cursor", "job", val=int((last - t0).total_seconds()) if last else mx_s)


def _stack_busy(S, full=False):
    """Процессов стойки и не должно быть (или они поднимаются) → (занято, остановлена штатно). Занято: строка running stack.* в adm.job, отметка
    restart_stack.py ещё действует (★ р77 В-2: прямой запуск без панели — тоже), или успешный stack.* панели меньше STACK_QUIET_MIN назад.
    ★ р78 В-1: «остановлена» — ТОЛЬКО отметка restart_stack.py «stopped» (её пишет и панельный stack.stop: он идёт тем же restart_stack.py
    --stop-only), бессрочного признака по журналу больше нет; full — стойка в снимке полная: «stopped» снимается. К-3: срок дальше
    ACTIVITY_MAX_H — не верим."""
    run = db.admin_rows(S.cn, "SELECT COUNT(*) AS n FROM adm.job WHERE status = 'running' AND op LIKE 'stack.%'")[0]["n"]
    last = db.admin_rows(S.cn, "SELECT TOP 1 action, DATEDIFF(SECOND, at, SYSDATETIME()) AS age_s FROM adm.audit WHERE action IN (?, ?, ?) AND result = 'ok' "
                               "ORDER BY id DESC", STACK_OPS)
    act = S.src.activity()
    until = activity_until(act)
    marked = until is not None and S.now < until <= S.now + datetime.timedelta(hours=ACTIVITY_MAX_H)
    stopped = marked and "phase=stopped" in act and not full
    quiet = bool(last) and last[0]["action"] != "stack.stop" and int(last[0]["age_s"] or 0) < STACK_QUIET_MIN * 60
    return bool(run) or (marked and "phase=stopped" not in act) or quiet, stopped


def _state_event(S, ev, key, bad, alert, recover_text=None, remind_text=None, need=BAD_SCANS):
    """Состояние с памятью: плохо need проходов подряд — уведомление; держится — напоминание раз в RULE.remind; прошло — отметка и «снова в
    порядке» ТОЛЬКО если в этом эпизоде уведомление действительно ушло в очередь (★ р77 М-6)."""
    st = S.st(ev, key)
    cnt = int(st.get("val") or 0)
    active, sent = bool(st.get("active")), bool(st.get("sent"))
    if bad:
        cnt += 1
        if not active and cnt >= need:
            code = S.fire(ev, key, alert)
            active = code in SENT                  # выключено — не «сообщено»: после включения сообщится текущее состояние
            sent = code in SENT_OK
        elif active and S.due_remind(ev, key):
            sent = S.fire(ev, key, remind_text or alert, gap=0) in SENT_OK or sent
    else:
        if active and sent and recover_text:
            S.fire(ev, key + ":up", recover_text, gap=0)
        cnt, active, sent = 0, False, False
    S.mark(ev, key, active=active, val=cnt, sent=sent)


def _processes(S, snap, busy):
    if not snap or snap.get("host_error") or not snap.get("stack"):
        return                                     # снимок не получен — «не прочитано» не равно «не работает»
    run, stopped = busy
    if run or stopped:
        return                                     # идёт управление стойкой или она остановлена штатно — процессов и не должно быть
    by = {e["key"]: e for e in snap["stack"]}
    eac = by.get("eac")
    if eac is not None:
        why = "не запущен" if not eac["running"] else "не слушает порты %s (слушает: %s)" % (
            ", ".join(str(p) for p in eac["ports"] if p not in eac["listening"]), ", ".join(str(p) for p in eac["listening"]) or "ничего")
        _state_event(S, "eac_down", "eac", not (eac["running"] and eac["ports_ok"]),
                     "AsdaEacServer %s — два прохода подряд (%d мин). Проверьте службу на сервере." % (why, BAD_SCANS * SCAN_S // 60),
                     "AsdaEacServer снова работает и слушает свои порты.", "AsdaEacServer всё ещё %s." % why)
    down = [by[k]["title"] for k in CORE_KEYS if k in by and not by[k]["running"]]
    _state_event(S, "stack", "down", bool(down),
                 "не работают процессы стойки (%d из %d): %s — %d прохода подряд (%d мин), вне управления стойкой." % (
                     len(down), len(CORE_KEYS), ", ".join(down), STACK_BAD_SCANS, STACK_BAD_SCANS * SCAN_S // 60),
                 "стойка снова полная: работают все %d процессов игры." % len(CORE_KEYS),
                 "процессы стойки всё ещё не работают: %s." % ", ".join(down), need=STACK_BAD_SCANS)


def _daily_state(S, ev, key, bad, text):
    """Состояние с напоминанием раз в сутки в REMIND_HOUR (LogDrop, подпись): первое — сразу, напоминание — в 10:00 (★ р77 К-2), без звука."""
    st = S.st(ev, key)
    active = bool(st.get("active")) and bad
    if bad and not active:
        active = S.fire(ev, key, text, gap=0) in SENT
    elif bad and S.due_daily(ev, key):
        S.fire(ev, key, text, gap=0, quiet=True)
    S.mark(ev, key, active=active)


def _logdrop(S, st):
    if not st or st.get("error") or st.get("pct") is None:
        return
    pct = float(st["pct"])
    gib = lambda b: "%.2f ГиБ" % (float(b or 0) / 1073741824.0)
    _daily_state(S, "logdrop_quota", "quota", pct >= LOGDROP_PCT,
                 "LogDrop занят на %s%% (%s из %s) — при 100%% приём журналов и падений клиента останавливается. "
                 "Удалить .alog старше %d суток — кнопка владельца в разделе «Сбои клиента»." % (pct, gib(st.get("used")), gib(st.get("quota")),
                                                                                                int(st.get("keep_days") or 60)))


def _release(S, rel):
    if not rel:
        return
    for p in rel.get("pointers") or []:
        name = p.get("name") or "?"
        if p.get("sig") == "unverified":
            continue                               # указатель не получен — без вывода
        lvl, sig = p.get("level"), p.get("sig")
        if sig == "bad":
            txt = "%s: подпись указателя НЕ сошлась (%s) — лаунчер такой указатель не примет." % (name, clean(p.get("error")))
        elif lvl == "expired":
            txt = "%s: подпись просрочена с %s — продлить: %s." % (name, p.get("expires"), S.src.resign_hint(name))
        else:
            txt = "%s: подпись истекает через %s сут (%s) — продлить: %s." % (name, p.get("days_left"), p.get("expires"), S.src.resign_hint(name))
        _daily_state(S, "release_sign", name, sig == "bad" or lvl in ("urgent", "expired"), txt)


def _reported(S, ev, key):
    """Разовое событие уже сообщено (val = 1). ★ р77 М-4: строки без val = 1 (помеченные при выключенном общем до ревизии 77) — не сообщены."""
    return int((S.st(ev, key) or {}).get("val") or 0) == 1


def _crash_rows(S, hours):
    if not db.admin_rows(S.cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.ClientCrash', N'U') IS NOT NULL"):
        return []
    rows = db.admin_rows(S.cn, "SELECT sig, MAX(exc_code) AS code, COUNT(*) AS n, COUNT(DISTINCT login) AS acc, MIN(pushed_utc) AS first_push "
                               "FROM adm.ClientCrash WHERE sig IS NOT NULL GROUP BY sig HAVING MIN(pushed_utc) > DATEADD(HOUR, -?, SYSUTCDATETIME()) "
                               "ORDER BY MIN(pushed_utc)", (hours,))
    return [r for r in rows if not _reported(S, "crash_new", r["sig"])]


def _report_rows(S, days):
    if not db.admin_rows(S.cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.PlayerReport', N'U') IS NOT NULL"):
        return []
    rows = db.admin_rows(S.cn, "SELECT id, category, created_utc FROM adm.PlayerReport WHERE status = 'new' AND created_utc < DATEADD(HOUR, -?, SYSUTCDATETIME()) "
                               "AND created_utc > DATEADD(DAY, -?, SYSUTCDATETIME()) ORDER BY id", (REPORT_STALE_H, days))
    return [r for r in rows if not _reported(S, "report_stale", str(r["id"]))]


def _crash_text(new):
    parts = ["%s (код %s, пакетов %d, учёток %d)" % (r["sig"], r["code"] or "?", r["n"], r["acc"]) for r in new[:CRASH_BATCH]]
    more = (" и ещё %d" % (len(new) - CRASH_BATCH)) if len(new) > CRASH_BATCH else ""
    return "новые места падения клиента (%d): %s%s. Подробности — раздел «Сбои клиента»." % (len(new), ", ".join(parts), more)


def _report_text(new):
    from domains import reports
    parts = ["№%d (%s)" % (r["id"], reports.CATEGORIES.get(r["category"], r["category"])) for r in new[:10]]
    more = (" и ещё %d" % (len(new) - 10)) if len(new) > 10 else ""
    return "жалобы игроков без «взять» дольше %d ч: %s%s. Раздел «Жалобы игроков»." % (REPORT_STALE_H, ", ".join(parts), more)


def _crashes(S):
    """★ р77 В-1: все новые места прохода — ОДНИМ сообщением (как жалобы), предел частоты им не забивается."""
    new = _crash_rows(S, CRASH_NEW_H)
    if not new:
        return
    code = S.fire("crash_new", "batch:" + new[0]["sig"], _crash_text(new))
    if code in RETRY:
        return
    for r in new:
        S.mark("crash_new", r["sig"], active=False, val=1)


def _reports(S):
    new = _report_rows(S, REPORT_MAX_AGE_D)
    if not new:
        return
    code = S.fire("report_stale", "r%d" % new[0]["id"], _report_text(new))
    if code in RETRY:
        return                                     # поля не прошли проверку — в следующий проход
    for r in new:
        S.mark("report_stale", str(r["id"]), active=False, val=1)


def _summary(S, rules):
    """★ р77 М-4: общий выключатель только что включён — одна сводка разовых событий, накопленных за время выключения (места падения и жалобы
    за SUMMARY_DAYS суток), и они помечаются сообщёнными. Выключенное событие в сводку не входит и не помечается."""
    crash = _crash_rows(S, SUMMARY_DAYS * 24) if rules.get("crash_new") else []
    rep = _report_rows(S, SUMMARY_DAYS) if rules.get("report_stale") else []
    if not crash and not rep:
        return
    parts = []
    if crash:
        parts.append(_crash_text(crash))
    if rep:
        parts.append(_report_text(rep))
    ev = "crash_new" if crash else "report_stale"
    code = S.fire(ev, "summary:%s" % S.now.strftime("%Y%m%d%H%M"), "за время, пока общий выключатель был выключен: %d новых мест падения, %d жалоб "
                  "ждут дольше %d ч.\n%s" % (len(crash), len(rep), REPORT_STALE_H, "\n".join(parts)))
    if code in RETRY:
        return
    for r in crash:
        S.mark("crash_new", r["sig"], active=False, val=1)
    for r in rep:
        S.mark("report_stale", str(r["id"]), active=False, val=1)


def scan(cn_factory=None, src=None):
    """Один проход поиска событий → dict(beat, results, errors). Отметка службы пишется всегда (по ней ПК видит, что служба жива). Каждое
    событие — отдельно: сбой одного источника не останавливает остальные. ★ р77 М-4: пока общий выключатель выключен, разовые события (места
    падения, жалобы) не ищутся и не помечаются; при включении — одна сводка."""
    src = src or Sources()
    cn = (cn_factory or db.admin)()
    out = {"beat": False, "results": [], "errors": []}
    try:
        if not _installed(cn):
            out["errors"].append(NOT_INSTALLED)
            return out
        rules, _rows = rules_state(cn)
        db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.TgBeatSet ?, ?", (src.host()[:64], "общий %s" % ("включён" if rules[MASTER] else "выключен")))
        out["beat"] = True
        S = Scan(cn, src)
        on = rules[MASTER]
        was_on = S.cursor("master") == 1
        steps = [("audit", lambda: _audit(S)), ("job", lambda: _jobs(S))]
        snap = {}

        def procs():
            snap["s"] = src.status()
            by = {e["key"]: e for e in (snap["s"] or {}).get("stack") or []}
            full = bool(by) and all(k in by and by[k]["running"] for k in CORE_KEYS)
            _processes(S, snap["s"], _stack_busy(S, full))
        steps += [("status", procs), ("logdrop", lambda: _logdrop(S, src.logdrop())), ("releases", lambda: _release(S, src.releases()))]
        if on and not was_on:
            steps.append(("summary", lambda: _summary(S, rules)))
        if on:
            steps += [("crashes", lambda: _crashes(S)), ("reports", lambda: _reports(S))]
        steps.append(("master", lambda: S.mark("_cursor", "master", val=1 if on else 0)))
        for name, fn in steps:
            try:
                fn()
            except Exception as ex:                       # один источник не должен глушить остальные
                out["errors"].append("%s: %s: %s" % (name, ex.__class__.__name__, clean(ex, 200)))
        out["results"] = S.out
        return out
    finally:
        cn.close()


_next = [0.0]
_quiet_err = []


def scan_due(mono=None, runner=None):
    """Из потока core/sched: проход раз в SCAN_S. Сбой — одна строка в журнал службы до первого удачного прохода."""
    t = time.monotonic() if mono is None else mono
    if t < _next[0]:
        return None
    _next[0] = t + SCAN_S
    try:
        res = (runner or scan)()
    except Exception as ex:
        if not _quiet_err:
            print("%s Telegram: поиск событий не выполнен (%s: %s)" % (time.strftime("%Y-%m-%d %H:%M:%S"), ex.__class__.__name__, clean(ex, 200)))
            if ex.__class__.__name__ not in ("DbError", "OpRefused"):
                traceback.print_exc()
        _quiet_err[:] = [True]
        return None
    _quiet_err[:] = []
    for ev, key, code in res.get("results") or []:
        if code in (0, 6):
            print("%s Telegram: %s %s — %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), ev, key, "поставлено" if code == 0 else "склеено"))
    for e in res.get("errors") or []:
        print("%s Telegram: источник не прочитан — %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), e))
    return res


# ── экран ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _state_of(r, now):
    st = int(r["status"])
    if st == 1 and r["claimed_utc"] and (now - r["claimed_utc"]).total_seconds() > 600:
        return "unknown"
    return STATUS.get(st, str(st))


def view(cn_factory=None):
    """Раздел «Telegram владельцу»: выключатели, события, отметки службы и отправителя, последние записи очереди Telegram, предупреждения."""
    base = {"rules": [dict(r) for r in RULES], "limits": {"per_hour": PER_HOUR, "per_day": PER_DAY, "ttl_min": TTL_MIN, "quiet": [QUIET_FROM, QUIET_TO],
            "scan_min": SCAN_S // 60, "panel_stale_min": PANEL_STALE_MIN}}

    def go(cn):
        if not _installed(cn):
            return None
        rules, rows = rules_state(cn)
        beat = db.admin_rows(cn, "SELECT beat_utc, host, note, pc_seen_utc FROM adm.NotifyBeat WHERE id = 1")
        q = db.admin_rows(cn, "SELECT TOP (%d) id, kind, title, text_en, is_test, quiet, event_key, repeats, supp_n, over_n, created_utc, created_by, "
                              "expires_utc, status, attempts, claimed_utc, done_utc, error, tg_message_id FROM adm.Outbox WHERE transport = 'telegram' "
                              "ORDER BY id DESC" % PAGE_MAX)
        cnt = db.admin_rows(cn, "SELECT status, COUNT(*) AS n FROM adm.Outbox WHERE transport = 'telegram' GROUP BY status")
        now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        return rules, rows, beat, q, cnt, now
    got = _read(go, cn_factory)
    if got is None:
        return dict(base, installed=False, error=NOT_INSTALLED, master=False, rows=[], counts={}, warnings=[NOT_INSTALLED])
    rules, rrows, beat, q, cnt, now = got
    b = beat[0] if beat else {}
    warn = []
    if not rules[MASTER]:
        warn.append("общий выключатель Telegram выключен — служба уведомлений не ставит (проверка и проверочное сообщение работают)")
    if not b.get("beat_utc") or (now - b["beat_utc"]).total_seconds() > PANEL_STALE_MIN * 60:
        warn.append("служба панели не отмечалась дольше %d мин — поиск событий не идёт" % PANEL_STALE_MIN)
    if not b.get("pc_seen_utc") or (now - b["pc_seen_utc"]).total_seconds() > PC_STALE_MIN * 60:
        warn.append("отправитель на ПК (бот Oracle) не отмечался дольше %d мин — запущен ли бот и есть ли telegram.env рядом с ним" % PC_STALE_MIN)
    out = []
    for r in q:
        x = {"id": r["id"], "kind": r["kind"], "title": r["title"], "test": bool(r["is_test"]), "quiet": bool(r["quiet"]),
             "text": full_text(r["text_en"], r["repeats"], r["supp_n"], r["over_n"]) if r["kind"] == "notify" else r["text_en"],
             "event": r["event_key"] or "", "repeats": r["repeats"], "created": _iso(r["created_utc"]), "by": r["created_by"],
             "expires": _iso(r["expires_utc"]), "state": _state_of(r, now), "attempts": r["attempts"], "done": _iso(r["done_utc"]),
             "error": r["error"] or "", "message_id": r["tg_message_id"]}
        if x["kind"] == "local":
            x["title"] = LOCAL_TITLES.get(r["title"], r["title"])
        if x["state"] == "queued" and (now - r["created_utc"]).total_seconds() > 300:
            warn.append("запись Telegram №%d ждёт отправителя дольше 5 мин" % r["id"])
        elif x["state"] == "unknown":
            warn.append("запись Telegram №%d: отправитель взял её и не отчитался дольше 10 мин" % r["id"])
        out.append(x)
    ev = []
    for r in RULES:
        rr = rrows.get(r["key"]) or {}
        ev.append(dict(r, enabled=rules[r["key"]], changed_by=rr.get("changed_by") or "", changed=_iso(rr.get("changed_utc"))))
    m = rrows.get(MASTER) or {}
    return dict(base, installed=True, error="", master=rules[MASTER], master_by=m.get("changed_by") or "", master_changed=_iso(m.get("changed_utc")),
                rules=ev, beat=_iso(b.get("beat_utc")), beat_host=b.get("host") or "", pc_seen=_iso(b.get("pc_seen_utc")), now=_iso(now), rows=out,
                counts={STATUS.get(int(c["status"]), str(c["status"])): int(c["n"]) for c in cnt}, warnings=warn)


# ── операции ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
TEST_CODES = {3: "проверок Telegram за час уже много — предел 10 проверочных записей и 3 проверочных сообщения в час",
              4: "проверка Telegram: неверный вид"}


def test_put(mode, by, cn_factory=None):
    """Проверочная запись Telegram (check | selftest | ping) → номер. Предел — в adm.TgTestPut."""
    def go(cn):
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        return db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @id INT, @code INT; EXEC adm.TgTestPut ?, ?, @id OUTPUT, @code OUTPUT; SELECT @code AS code, @id AS id",
                             (mode, str(by)[:32]))[0]
    r = _read(go, cn_factory)
    if int(r["code"]):
        raise OpRefused(TEST_CODES.get(int(r["code"]), "проверка Telegram: код %d" % int(r["code"])))
    return int(r["id"])


def _event(p):
    k = str((p or {}).get("event") or "")
    if k != MASTER and k not in EVENTS:
        raise OpRefused("событие не из списка (можно: %s)" % ", ".join((MASTER,) + EVENTS))
    v = (p or {}).get("enabled")
    if not isinstance(v, bool):
        raise OpRefused("enabled — true или false")
    return k, v


@register
class NotifyRuleSet(Operation):
    name, title, perm, reversible = "notify.rule.set", "Telegram: включить или выключить уведомление", "notify.manage", False

    def target(self, p):
        return "notify:%s" % ((p or {}).get("event"),)

    def preview(self, ctx, p):
        k, v = _event(p)
        cur = _read(lambda cn: rules_state(cn)[0] if _installed(cn) else None)
        if cur is None:
            raise OpRefused(NOT_INSTALLED)
        if cur[k] == v:
            raise OpRefused("выключатель Telegram уже включён" if v else "выключатель Telegram уже выключен")
        name = "общий выключатель Telegram" if k == MASTER else "уведомление «%s»" % RULE[k]["title"]
        w = ["пишется только база панели AsdaAdmin (adm.NotifyRule)"]
        if k == MASTER and v:
            w.insert(0, "после включения служба начнёт ставить уведомления о событиях, отправитель на ПК — слать их в чат владельца (sendMessage)")
        return {"text": "%s %s" % ("включить" if v else "выключить", name), "expect": {"enabled": cur[k]}, "warnings": w}

    def apply(self, ctx, p, prev):
        k, v = _event(p)
        _read(lambda cn: db.admin_rows(cn, "SET NOCOUNT ON; EXEC adm.TgRuleSet ?, ?, ?", (k, 1 if v else 0, ctx.login[:32])))
        if k == MASTER:
            msg = "общий выключатель Telegram включён" if v else "общий выключатель Telegram выключен"
        else:
            msg = ("уведомление «%s» включено" if v else "уведомление «%s» выключено") % RULE[k]["title"]
        return {"before": {"event": k, "enabled": prev["expect"]["enabled"]}, "after": {"event": k, "enabled": v}, "message": msg}


@register
class TelegramTest(Operation):
    """Проверочная запись: отправитель на ПК её забирает и вызывает ТОЛЬКО getMe (токен и прокси живы) — сообщения в чат нет. selftest — отправитель
    только отмечает «тест», Telegram не вызывается (живой самотест)."""
    name, title, perm, reversible = "telegram.test", "Telegram: проверить (getMe, без сообщения)", "notify.manage", False

    def target(self, p):
        return "telegram:test"

    def _mode(self, p):
        m = str((p or {}).get("mode") or "check")
        if m not in TEST_MODES:
            raise OpRefused("проверка Telegram: вид check или selftest")
        return m

    def preview(self, ctx, p):
        m = self._mode(p)
        return {"text": "поставить проверочную запись Telegram — отправитель на ПК %s, сообщения в чат не будет"
                        % ("вызовет только getMe (жив ли токен и прокси)" if m == "check" else "только отметит «тест», Telegram не вызывается"),
                "warnings": ["пишется только база панели AsdaAdmin (adm.Outbox, запись с отметкой «тест»)"]}

    def apply(self, ctx, p, prev):
        oid = test_put(self._mode(p), ctx.login)
        return {"before": None, "after": {"id": oid, "test": True}, "message": "проверочная запись Telegram №%d поставлена" % oid}


@register
class TelegramPing(Operation):
    """НАСТОЯЩЕЕ проверочное сообщение в чат владельца (sendMessage). Общий выключатель на него не влияет — это первая проверка канала."""
    name, title, perm, reversible = "telegram.ping", "Telegram: отправить проверочное сообщение", "notify.manage", False

    def target(self, p):
        return "telegram:ping"

    def preview(self, ctx, p):
        return {"text": "отправить в Telegram владельцу проверочное сообщение «Astory: проверочное сообщение админ-центра — уведомления владельцу доходят.»",
                "warnings": ["это настоящая отправка: сообщение придёт в чат владельца от @@@ASTORY_TELEGRAM_BOT@@ в течение 30 с, если бот Oracle на ПК запущен",
                             "отката нет — сообщение остаётся в чате"]}

    def apply(self, ctx, p, prev):
        oid = test_put("ping", ctx.login)
        return {"before": None, "after": {"id": oid, "ping": True}, "message": "проверочное сообщение Telegram №%d поставлено отправителю" % oid}
