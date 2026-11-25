# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""outbox.py — очередь исходящих сообщений: объявления в Discord (шаг А7.4, 23.11.2026; решение владельца А7 №2 — в Discord только по флажку
«и в Discord» в форме объявления в игру, тексты EN / RU / AR оператор пишет сам, канал и роль выбирает из списка; разбор
Reports/admin_center/research_a7_releases_20261123.md §0 п.1, §3 А7.4; отчёт impl_a7_releases_20261123.md §А7.4).

КАК ИДЁТ СООБЩЕНИЕ. Сервер Discord не видит, поэтому публикует бот Oracle на ПК владельца (AstoryAdminCenter/DiscordBot/outbox_bot.py):
  панель (live.announce с флажком «и в Discord») → adm.OutboxPut (статус 7 «ждёт объявления в игру») → объявление в игру мостом → удалось —
  adm.OutboxRelease (статус 0 «ждёт бота»), не удалось — запись отменяется, в Discord ничего не уходит → бот раз в 30 с забирает запись
  adm.OutboxClaim (логин asda_reports, только процедуры), проверяет белые списки и срок, публикует, отмечает adm.OutboxDone.
БЕЛЫЕ СПИСКИ — в коде (здесь и у бота; самотест сверяет, что они одинаковые), оператор их не задаёт и в ini их нет:
  каналы  announcements (новости), updates (форум: ветка, её имя — текст объявления в игру), test-info (тестерам);
  роли    News Ping, Patch Ping, Playtest Ping или без упоминания. @everyone и @here запрещены всегда (здесь, в CHECK таблицы и у бота).
ОПЕРАЦИИ (журнал adm.audit; права — core/auth.py):
  live.announce + discord  — объявление в игру и в Discord (community.post — owner, admin; gm нет: это публично для всего сервера Discord);
  outbox.cancel            — отменить до публикации (community.post);
  outbox.retry             — повторить после ошибки или если бот взял и молчит дольше STUCK_MIN (community.post); опубликованный номер бот
                             повторно не публикует (журнал на ПК, у сообщения в канале — ещё и nonce Discord); дубль возможен только при сбое
                             шлюза Discord в форуме updates (у ветки nonce нет — ★ ревизия 76 М-2);
  outbox.delete            — удалить опубликованное из Discord (community.delete — только owner; отката нет: сообщение исчезает у всех);
  outbox.test              — проверочная запись: бот её забирает и отмечает «тест», но в Discord НЕ публикует (проверка пути бота).
Побочных эффектов при импорте нет.
"""
import re

from core import db
from core.ops import Operation, OpRefused, register

# ★ белые списки — те же ключи, что CHECK adm.Outbox и outbox_bot.CHANNELS / ROLES (самотест сверяет)
CHANNELS = {"announcements": "#announcements — новости", "updates": "форум updates — новая ветка", "test-info": "#test-info — тестерам"}
FORUM = ("updates",)
ROLES = {"": "без упоминания", "news": "News Ping", "patch": "Patch Ping", "playtest": "Playtest Ping"}
FORBIDDEN = ("@everyone", "@here")
LANGS = (("en", "🇬🇧"), ("ar", "🇸🇦"), ("ru", "🇷🇺"))   # порядок строк в сообщении — как у announce_restart.py (EN, AR, RU)
TEXT_MAX = 1800                 # знаков на язык (NVARCHAR(1800))
MSG_MAX = 2000                  # предел сообщения Discord
MENTION_MAX = 23                # «<@&» + id роли (до 19 цифр) + «>»
TITLE_MAX = 100                 # имя ветки форума Discord
TTL_DEF, TTL_MIN, TTL_MAX = 60, 5, 1440   # срок годности, минут
PER_HOUR, PER_DAY, TEST_PER_HOUR = 6, 30, 10   # пределы adm.OutboxPut (здесь — для предпросмотра)
STUCK_MIN = 10                  # бот взял и не отчитался дольше — «итог неизвестен», можно повторить
BOT_IDLE_MIN = 5                # запись ждёт бота дольше — предупреждение «бот не забирает»
HOLD_STALE_MIN = 10             # запись «ждёт объявления в игру» дольше — объявление в игру не подтвердилось
MAX_ATTEMPTS = 5
PAGE_MAX = 200
STATUS = {7: "hold", 0: "queued", 1: "claimed", 2: "posted", 3: "failed", 4: "cancelled", 5: "expired", 6: "test"}
DEL_STATUS = {0: "queued", 1: "claimed", 2: "deleted", 3: "failed"}
FILTERS = ("all", "active", "posted", "failed", "cancelled", "expired", "test")
NOT_INSTALLED = "таблицы adm.Outbox нет (sql/adminc_28_outbox.sql не установлен)"
PUT_CODES = {1: "в Discord за час уже %d объявлений — предел %d в час" % (PER_HOUR, PER_HOUR),
             2: "в Discord за сутки уже %d объявлений — предел %d в сутки" % (PER_DAY, PER_DAY),
             3: "проверочных записей за час уже %d — предел %d в час" % (TEST_PER_HOUR, TEST_PER_HOUR),
             4: "поля объявления в Discord не прошли проверку базы (канал, роль, длина, срок, @everyone / @here)",
             5: "в форуме updates за сутки уже была ветка с таким именем (объявление или заметки к выпуску) — дайте объявлению другой текст"}   # ★ р83 М-2
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MENTION = re.compile(r"<@[!&]?\d*>?|<#\d+>")


def compose(mention, en, ru, ar):
    """Текст сообщения Discord: упоминание роли (если есть) и строки языков с флагами. ★ Тот же текст собирает бот (outbox_bot.compose)."""
    parts = [mention] if mention else []
    vals = {"en": en, "ru": ru, "ar": ar}
    for k, flag in LANGS:
        v = (vals.get(k) or "").strip()
        if v:
            parts.append("%s %s" % (flag, v))
    return "\n".join(parts)


def _text(v, name, required):
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise OpRefused("текст %s — строка" % name)
    s = v.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not s and required:
        raise OpRefused("текст %s для Discord обязателен" % name)
    if len(s) > TEXT_MAX:
        raise OpRefused("текст %s длиннее %d знаков" % (name, TEXT_MAX))
    if _CTRL.search(s):
        raise OpRefused("в тексте %s управляющие символы" % name)
    return s


def forbidden_in(*texts):
    """Есть ли в текстах @everyone / @here (без учёта регистра)."""
    low = " ".join(t or "" for t in texts).lower()
    return any(f in low for f in FORBIDDEN)


def check(ctx, d, title):
    """Поля «и в Discord» формы объявления → чистый dict(channel, role, en, ru, ar, ttl, title). Ошибка — отказ. title — текст объявления в игру
    (заголовок; для форума — имя ветки)."""
    if not ctx.can("community.post"):
        raise OpRefused("нет права «community.post» (публикация в Discord — owner и admin)")
    if not isinstance(d, dict):
        raise OpRefused("поля объявления в Discord — объект")
    ch = str(d.get("channel") or "")
    if ch not in CHANNELS:
        raise OpRefused("канал Discord не из списка (можно: %s)" % ", ".join(CHANNELS))
    role = str(d.get("role") or "")
    if role not in ROLES:
        raise OpRefused("роль Discord не из списка (можно: News Ping, Patch Ping, Playtest Ping или без упоминания)")
    en, ru, ar = _text(d.get("en"), "EN", True), _text(d.get("ru"), "RU", False), _text(d.get("ar"), "AR", False)
    title = str(title or "").strip()
    if not title or len(title) > TITLE_MAX:
        raise OpRefused("заголовок (текст объявления в игру) — от 1 до %d знаков" % TITLE_MAX)
    if forbidden_in(title, en, ru, ar):
        raise OpRefused("@everyone и @here в Discord запрещены — упомянуть можно только роль из списка")
    if any(_MENTION.search(t) for t in (title, en, ru, ar)):
        raise OpRefused("в тексте упоминание вида <@…> или <#…> — упомянуть можно только роль из списка (поле «роль»)")
    try:
        ttl = int(d.get("ttl") if d.get("ttl") not in (None, "") else TTL_DEF)
    except (TypeError, ValueError):
        raise OpRefused("срок годности — целое число минут")
    if not TTL_MIN <= ttl <= TTL_MAX:
        raise OpRefused("срок годности — от %d до %d минут" % (TTL_MIN, TTL_MAX))
    if dlen(title) > TITLE_MAX:
        raise OpRefused("заголовок (текст объявления в игру) — от 1 до %d знаков" % TITLE_MAX)
    n = dlen(compose("x" * MENTION_MAX if role else "", en, ru, ar))
    if n > MSG_MAX:
        raise OpRefused("сообщение Discord длиннее %d знаков (сейчас %d вместе с флагами и упоминанием)" % (MSG_MAX, n))
    return {"channel": ch, "role": role, "en": en, "ru": ru, "ar": ar, "ttl": ttl, "title": title}


NOTES_NO_RETRY = ("запись №%d — заметки к выпуску: повтор записи не делается (её записи changelog могли уже уйти в другую ветку) — опубликуйте их "
                  "заново в «Заметках к выпуску», «итог неизвестен» решается там же")   # ★ р82 М-2: отказ outbox.retry для вида notes
REPEAT_REFUSED = "объявление в Discord ставится только разовым заданием — повтор «каждый день» / «каждую неделю» с флажком «и в Discord» запрещён"
_URL = re.compile(r"(?i)\bhttps?://([^/\s<>()\[\]\"']+)")


def refuse_repeat(repeat):
    """★ ревизия 76 К4 (решение координатора 23.11): каждый повтор задания был бы новым сообщением в Discord с пингом роли — с флажком
    «и в Discord» разрешено только разовое задание. Проверка — при постановке задания (domains/stack.py JobAdd)."""
    if repeat:
        raise OpRefused(REPEAT_REFUSED)


def link_domains(*texts):
    """★ р76 К5: домены ссылок в текстах (для предпросмотра; превью ссылок бот отключает — suppress_embeds)."""
    out = []
    for t in texts:
        for d in _URL.findall(t or ""):
            d = d.lower().split("@")[-1].split(":")[0]
            if d not in out:
                out.append(d)
    return out


def dlen(s):
    """★ р76 К7: длина для пределов Discord — в единицах UTF-16 (не меньше числа кодовых точек: запас). ★ Тот же подсчёт — outbox_bot.dlen."""
    return len(str(s or "").encode("utf-16-le")) // 2


def describe(dc):
    """Строки предпросмотра для окна подтверждения (и для job.add)."""
    langs = [k.upper() for k, _f in LANGS if dc.get(k)]
    miss = [k.upper() for k, _f in LANGS if not dc.get(k)]
    out = ["и в Discord: %s, %s, срок годности %d мин (позже бот не публикует), языки %s"
           % (CHANNELS[dc["channel"]], ("роль %s" % ROLES[dc["role"]]) if dc["role"] else "без упоминания роли", dc["ttl"], " ".join(langs))]
    if miss:
        out.append("в Discord нет текста на %s" % " ".join(miss))
    doms = link_domains(dc["title"], dc["en"], dc["ru"], dc["ar"])
    if doms:
        out.append("ссылки в тексте ведут на: %s (превью ссылок в Discord отключено)" % ", ".join(doms))
    if dc["channel"] in FORUM:
        out.append("форум updates: имя новой ветки — «%s»" % dc["title"])
    out.append("в Discord публикует бот Oracle на ПК владельца (раз в 30 с), если он запущен — итог виден на странице «Очередь Discord»")
    return out


def preview_text(dc):
    """Сообщение, как его увидят в Discord (роль — именем, бот подставит упоминание)."""
    return compose(("@" + ROLES[dc["role"]]) if dc["role"] else "", dc["en"], dc["ru"], dc["ar"])


def _read(fn):
    try:
        cn = db.admin()
    except db.DbError as ex:
        raise OpRefused("очередь Discord не прочитана: %s" % ex)
    try:
        return fn(cn)
    except db.DbError as ex:
        raise OpRefused("очередь Discord не прочитана: %s" % ex)
    finally:
        cn.close()


def _installed(cn):
    return bool(db.admin_rows(cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.Outbox', N'U') IS NOT NULL AND OBJECT_ID(N'adm.OutboxPut', N'P') IS NOT NULL"))


def budget(test=False):
    """Пределы для предпросмотра (сама проверка — в adm.OutboxPut под замком). Превышено — отказ."""
    def go(cn):
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        return db.admin_rows(cn, "SELECT SUM(CASE WHEN created_utc > DATEADD(HOUR, -1, SYSUTCDATETIME()) THEN 1 ELSE 0 END) AS h, COUNT(*) AS d "
                                 "FROM adm.Outbox WHERE transport = 'discord' AND is_test = ? AND created_utc > DATEADD(DAY, -1, SYSUTCDATETIME())", (1 if test else 0,))[0]
    r = _read(go)
    h, d = int(r["h"] or 0), int(r["d"] or 0)
    if test and h >= TEST_PER_HOUR:
        raise OpRefused(PUT_CODES[3])
    if not test and h >= PER_HOUR:
        raise OpRefused(PUT_CODES[1])
    if not test and d >= PER_DAY:
        raise OpRefused(PUT_CODES[2])
    return {"hour": h, "day": d}


def put(dc, by, hold, kind="announce"):
    """Поставить запись (своё соединение, фиксация сразу) → номер. Отказ по пределу — OpRefused."""
    def go(cn):
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        return db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @id INT, @code INT; EXEC adm.OutboxPut ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, @id OUTPUT, @code OUTPUT; "
                                 "SELECT @code AS code, @id AS id",
                             (kind, dc["channel"], dc["role"] or None, dc["title"], dc["en"], dc["ru"] or None, dc["ar"] or None, int(dc["ttl"]),
                              str(by)[:32], 1 if hold else 0))[0]
    r = _read(go)
    code = int(r["code"])
    if code:
        raise OpRefused(PUT_CODES.get(code, "очередь Discord: код %d" % code))
    return int(r["id"])


def release(oid, ok, by, note="", cn=None):
    """Запись «ждёт объявления в игру» → боту (ok) или отменить. cn — открытая транзакция вызывающего (фиксирует он) или None (своё соединение)."""
    sql = "SET NOCOUNT ON; EXEC adm.OutboxRelease ?, ?, ?, ?"
    prm = (int(oid), 1 if ok else 0, str(by)[:32], str(note or "")[:400])
    if cn is not None:
        return int(db.admin_rows(cn, sql, prm)[0]["n"])
    return int(_read(lambda c: db.admin_rows(c, sql, prm))[0]["n"])


def _iso(v):
    return v.isoformat(sep=" ") if hasattr(v, "isoformat") else (str(v) if v is not None else None)


def _state(r, now):
    st = int(r["status"])
    if st == 1 and r["claimed_utc"] and (now - r["claimed_utc"]).total_seconds() > STUCK_MIN * 60:
        return "unknown"
    if st == 7 and (now - r["created_utc"]).total_seconds() > HOLD_STALE_MIN * 60:
        return "hold_stale"
    return STATUS.get(st, str(st))


_COLS = ("id, kind, channel_key, role_key, title, text_en, text_ru, text_ar, is_test, created_utc, created_by, expires_utc, status, attempts, "
         "claimed_utc, done_utc, error, discord_channel_id, discord_message_id, changed_by, changed_utc, del_status, del_by, del_utc, del_done_utc, del_error")
_WHERE = {"all": "", "active": "AND (status IN (0, 1, 7) OR del_status IN (0, 1))", "posted": "AND status = 2", "failed": "AND (status = 3 OR del_status = 3)",
          "cancelled": "AND status = 4", "expired": "AND status = 5", "test": "AND is_test = 1"}
_DISCORD = "WHERE transport = 'discord' "     # ★ А7.5: строки Telegram (transport = 'telegram') живут в той же таблице — экран Discord их не показывает


def view(q=None):
    """Экран «Очередь Discord»: записи (новые сверху), счётчики по статусам, предупреждения (бот не забирает, итог неизвестен, ошибки)."""
    q = q or {}
    flt = str(q.get("status") or "all")
    if flt not in FILTERS:
        raise OpRefused("неверный фильтр (можно: %s)" % ", ".join(FILTERS))

    def go(cn):
        if not _installed(cn):
            return None
        rows = db.admin_rows(cn, "SELECT TOP (%d) %s FROM adm.Outbox %s%s ORDER BY id DESC" % (PAGE_MAX, _COLS, _DISCORD, _WHERE[flt]))
        cnt = db.admin_rows(cn, "SELECT status, COUNT(*) AS n FROM adm.Outbox " + _DISCORD + "GROUP BY status")
        last = db.admin_rows(cn, "SELECT MAX(claimed_utc) AS c, MAX(done_utc) AS d FROM adm.Outbox " + _DISCORD)[0]
        now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        return rows, cnt, last, now
    base = {"channels": CHANNELS, "roles": ROLES, "filters": FILTERS, "limits": {"per_hour": PER_HOUR, "per_day": PER_DAY, "ttl_def": TTL_DEF,
            "ttl_min": TTL_MIN, "ttl_max": TTL_MAX, "stuck_min": STUCK_MIN, "max_attempts": MAX_ATTEMPTS, "text_max": TEXT_MAX}}
    got = _read(go)
    if got is None:
        return dict(base, installed=False, error=NOT_INSTALLED, rows=[], counts={}, warnings=[NOT_INSTALLED])
    rows, cnt, last, now = got
    out, warn = [], []
    for r in rows:
        st = _state(r, now)
        x = {"id": r["id"], "kind": r["kind"], "channel": r["channel_key"], "role": r["role_key"] or "", "title": r["title"], "en": r["text_en"],
             "ru": r["text_ru"] or "", "ar": r["text_ar"] or "", "test": bool(r["is_test"]), "created": _iso(r["created_utc"]), "by": r["created_by"],
             "expires": _iso(r["expires_utc"]), "state": st, "attempts": r["attempts"], "claimed": _iso(r["claimed_utc"]), "done": _iso(r["done_utc"]),
             "error": r["error"] or "", "changed_by": r["changed_by"] or "", "changed": _iso(r["changed_utc"]),
             "posted_at": ("%s/%s" % (r["discord_channel_id"], r["discord_message_id"])) if r["discord_message_id"] else "",
             "del_state": DEL_STATUS.get(r["del_status"]) if r["del_status"] is not None else "", "del_by": r["del_by"] or "",
             "del_done": _iso(r["del_done_utc"]), "del_error": r["del_error"] or ""}
        x["preview"] = compose(("@" + ROLES.get(x["role"], x["role"])) if x["role"] else "", x["en"], x["ru"], x["ar"])
        x["can_cancel"] = st in ("queued", "hold", "hold_stale")
        x["can_retry"] = st in ("failed", "unknown") and r["attempts"] < MAX_ATTEMPTS and r["expires_utc"] > now and r["kind"] != "notes"
        x["can_delete"] = st == "posted" and r["discord_message_id"] is not None and r["del_status"] in (None, 3)
        if st == "queued" and (now - r["created_utc"]).total_seconds() > BOT_IDLE_MIN * 60:
            warn.append("запись №%d ждёт бота дольше %d мин — запущен ли бот Oracle на ПК владельца" % (r["id"], BOT_IDLE_MIN))
        elif st == "unknown":
            warn.append("запись №%d: бот взял её и не отчитался дольше %d мин — проверьте канал в Discord, потом «повторить» или «отменить»"
                        % (r["id"], STUCK_MIN))
        elif st == "hold_stale":
            warn.append("запись №%d: объявление в игру не подтвердилось за %d мин — в Discord она не уйдёт, её можно отменить" % (r["id"], HOLD_STALE_MIN))
        out.append(x)
    return dict(base, installed=True, error="", rows=out, counts={STATUS.get(int(c["status"]), str(c["status"])): int(c["n"]) for c in cnt},
                bot_seen=_iso(last["c"]), bot_done=_iso(last["d"]), now=_iso(now), warnings=warn)


def _row(cn, oid, lock):
    r = db.admin_rows(cn, "SELECT %s FROM adm.Outbox %s WHERE id = ? AND transport = 'discord'" % (_COLS, "WITH (UPDLOCK, ROWLOCK)" if lock else ""), (oid,))
    if not r:
        raise OpRefused("записи очереди Discord №%d нет" % oid)
    return r[0]


def _oid(p):
    try:
        v = int((p or {}).get("id"))
    except (TypeError, ValueError):
        raise OpRefused("номер записи — целое от 1")
    if v < 1 or v > 2 ** 31 - 1:
        raise OpRefused("номер записи — целое от 1")
    return v


class _OutOp(Operation):
    """Общее: цель журнала, транзакция AsdaAdmin, фиксация после записи журнала (ops._finish)."""
    reversible = False
    proc = ""

    def target(self, p):
        return "outbox:%s" % ((p or {}).get("id"),)

    def _peek(self, p):
        oid = _oid(p)

        def go(cn):
            if not _installed(cn):
                raise OpRefused(NOT_INSTALLED)
            r = _row(cn, oid, False)
            return r, db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        return _read(go)

    def _tx(self, ctx, oid, args, fail):
        cn = db.admin()
        try:
            cn.autocommit = False
            n = int(db.admin_rows(cn, "SET NOCOUNT ON; EXEC %s %s" % (self.proc, ", ".join("?" * len(args))), args)[0]["n"])
            if n != 1:
                raise OpRefused(fail)
        except BaseException:
            try:
                cn.rollback()
            finally:
                cn.close()
            raise
        return {"_commit": cn.commit, "_close": cn.close}


def _brief(r):
    return "№%d (%s%s, «%s»)" % (r["id"], r["channel_key"], (", " + ROLES.get(r["role_key"], r["role_key"])) if r["role_key"] else "", r["title"])


@register
class OutboxCancel(_OutOp):
    name, title, perm, proc = "outbox.cancel", "Discord: отменить запись до публикации", "community.post", "adm.OutboxCancel"

    def preview(self, ctx, p):
        r, now = self._peek(p)
        if int(r["status"]) not in (0, 7):
            raise OpRefused("запись №%d уже не ждёт публикации (%s) — отменить нельзя" % (r["id"], _state(r, now)))
        return {"text": "отменить запись очереди Discord %s — в Discord она не уйдёт" % _brief(r), "expect": {"status": int(r["status"])},
                "warnings": ["пишется только база панели AsdaAdmin (adm.Outbox): статус «отменено»"]}

    def apply(self, ctx, p, prev):
        oid = _oid(p)
        out = self._tx(ctx, oid, (oid, ctx.login[:32]), "запись №%d уже взята ботом или изменилась — откройте очередь заново" % oid)
        out.update(before={"id": oid, "status": prev["expect"]["status"]}, after={"id": oid, "status": 4},
                   message="запись очереди Discord №%d отменена" % oid)
        return out


@register
class OutboxRetry(_OutOp):
    name, title, perm, proc = "outbox.retry", "Discord: повторить запись", "community.post", "adm.OutboxRetry"

    def preview(self, ctx, p):
        r, now = self._peek(p)
        st = _state(r, now)
        if r["kind"] == "notes":            # ★ р82 М-2 (А7.7): записи заметок могли уже уйти в другую ветку — повтор только новой публикацией
            raise OpRefused(NOTES_NO_RETRY % r["id"])
        if st not in ("failed", "unknown"):
            raise OpRefused("запись №%d не в ошибке и не «итог неизвестен» (%s) — повторять нечего" % (r["id"], st))
        if r["attempts"] >= MAX_ATTEMPTS:
            raise OpRefused("у записи №%d уже %d попыток — больше нельзя, поставьте объявление заново" % (r["id"], r["attempts"]))
        if r["expires_utc"] <= now:
            raise OpRefused("срок годности записи №%d прошёл — поставьте объявление заново" % r["id"])
        w = ["бот возьмёт запись снова в течение 30 с, если он запущен"]
        if st == "unknown":
            w.insert(0, "бот взял запись и не отчитался — если сообщение уже есть в Discord, бот его не повторит (номер есть в журнале бота на ПК)")
        return {"text": "повторить запись очереди Discord %s (попытка %d из %d)" % (_brief(r), r["attempts"] + 1, MAX_ATTEMPTS),
                "expect": {"status": int(r["status"])}, "warnings": w}

    def apply(self, ctx, p, prev):
        oid = _oid(p)
        out = self._tx(ctx, oid, (oid, ctx.login[:32], STUCK_MIN), "запись №%d уже нельзя повторить (статус изменился, срок или попытки) — откройте очередь заново" % oid)
        out.update(before={"id": oid, "status": prev["expect"]["status"]}, after={"id": oid, "status": 0},
                   message="запись очереди Discord №%d поставлена на повтор" % oid)
        return out


@register
class OutboxDelete(_OutOp):
    name, title, perm, proc = "outbox.delete", "Discord: удалить опубликованное сообщение", "community.delete", "adm.OutboxDelete"

    def preview(self, ctx, p):
        r, now = self._peek(p)
        if int(r["status"]) != 2 or r["discord_message_id"] is None:
            raise OpRefused("запись №%d не опубликована — удалять в Discord нечего" % r["id"])
        if r["del_status"] not in (None, 3):
            raise OpRefused("удаление записи №%d уже поставлено (%s)" % (r["id"], DEL_STATUS.get(r["del_status"])))
        w = ["отката нет: сообщение исчезнет из Discord у всех, вернуть его можно только новым объявлением",
             "удаляет бот Oracle на ПК владельца в течение 30 с, если он запущен — итог виден в очереди"]
        if r["channel_key"] in FORUM:
            w.insert(0, "у форума updates удаляется ветка целиком (вместе с ответами в ней)")
        return {"text": "удалить из Discord опубликованное сообщение %s" % _brief(r), "expect": {"status": 2, "del": r["del_status"]}, "warnings": w}

    def apply(self, ctx, p, prev):
        oid = _oid(p)
        out = self._tx(ctx, oid, (oid, ctx.login[:32]), "удаление записи №%d уже поставлено или она изменилась — откройте очередь заново" % oid)
        out.update(before={"id": oid, "del": prev["expect"]["del"]}, after={"id": oid, "del": 0},
                   message="удаление сообщения Discord по записи №%d поставлено боту" % oid)
        return out


@register
class OutboxTest(Operation):
    """Проверочная запись: бот забирает её тем же путём и отмечает «тест», но в Discord НЕ публикует (outbox_bot: is_test — без вызова Discord)."""
    name, title, perm, reversible = "outbox.test", "Discord: проверочная запись (бот не публикует)", "community.post", False

    def target(self, p):
        return "outbox:test"

    def preview(self, ctx, p):
        budget(test=True)
        return {"text": "поставить проверочную запись в очередь Discord — бот её заберёт и отметит «тест», в Discord ничего не уйдёт",
                "warnings": ["пишется только база панели AsdaAdmin (adm.Outbox, запись с отметкой «тест»)"]}

    def apply(self, ctx, p, prev):
        dc = {"channel": "test-info", "role": "", "title": "test", "en": "test record — not published", "ru": None, "ar": None, "ttl": 30}
        oid = put(dc, ctx.login, hold=False, kind="test")
        return {"before": None, "after": {"id": oid, "test": True}, "message": "проверочная запись очереди Discord №%d поставлена" % oid}
