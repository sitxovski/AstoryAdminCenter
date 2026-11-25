#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""tg_bot.py — отправитель уведомлений панели Astory владельцу в Telegram (шаг А7.5 админ-центра, 23.11.2026; решение владельца А7 №3: только
владельцу, через бота @@@ASTORY_TELEGRAM_BOT@@, только отправка, с ПК; канала для игроков нет).

ПУТЬ. Служба панели на сервере находит событие и кладёт строку в AsdaAdmin.adm.Outbox с transport = 'telegram'
(AstoryAdminCenter/sql/adminc_29_telegram.sql, domains/notify.py). Этот модуль крутится циклом в боте Oracle (oracle_bot.py, раз в
TICK_S, тот же вотчдог ensure_oracle.ps1), забирает строку процедурой adm.TgClaim ТЕМ ЖЕ логином asda_reports, что жалобы и очередь Discord
(пароль — reports.env), шлёт её в чат владельца и отмечает adm.TgDone.
ТОЛЬКО ДВА МЕТОДА Bot API — METHODS: sendMessage (уведомление) и getMe (проверка «жив ли токен и прокси», сообщения нет). Других вызовов в
коде нет и быть не должно: этим же ботом агенты задают вопросы владельцу и читают его ответы, поэтому отправитель не читает апдейты бота,
не ставит и не снимает вебхук и не меняет настройки бота (самотест проверяет текст модуля).
СЕКРЕТ — только на ПК: telegram.env рядом с ботом (TG_TOKEN — токен бота, TG_CHAT — номер личного чата владельца, только положительный:
группы и каналы отрицательные, туда отправитель не шлёт никогда). В базе, панели, журналах и итогах токена нет — тексты ошибок проходят mask().
Связь — напрямую или через прокси из TELEGRAM_PROXY / DISCORD_PROXY / HTTPS_PROXY (не задан, пусто или none — без прокси; botcfg.proxy).
ЗАЩИТЫ (в коде, в ini и .env их нет):
  * один раз: номер записи пишется в журнал отправителя tg_ledger.json ДО отправки («sending») и после («sent», номер сообщения). Повтор того же
    номера не отправляется: «sent» — отмечается заново, «sending» — «итог неизвестен»; номера нет в журнале, а попыток больше одной — журнал
    потерян, не отправляется. Точный отказ Telegram (ответ с ошибкой, нет связи с прокси) — «failed»: строка снова ждёт (не больше 3 попыток,
    adm.TgDone @retry); тайм-аут ответа — «итог неизвестен», без повтора (сообщение могло уйти);
  * предел частоты: не больше PER_HOUR вызовов Telegram за скользящий час (поверх 10 / час базы);
  * тихие часы QUIET: не-срочное (quiet) с 23:00 до 08:00 по часам ПК уходит без звука (disable_notification), но не задерживается;
  * проверочные записи: 'check' — только getMe, 'selftest' — только отметка «тест» без Telegram;
  * «служба панели не отвечает» ищет сам отправитель: отметка службы (adm.TgBeatGet) старше PANEL_STALE_MIN или база не отвечает с ПК дольше
    DB_DOWN_MIN — одно сообщение на случай и одно «снова отвечает»; выключатели — последние прочитанные из базы (никогда не прочитаны — молчит).
★ РЕВИЗИЯ 77 (24.11.2026): текст собирается из столбцов supp_n / over_n (М-3); сбои http.client — «итог неизвестен» (К-5); свои сообщения
  «служба / база» — строкой очереди для экрана (adm.TgLocalNote, К-3; база недоступна — после её возврата); «нет процедуры или прав» не выдаётся
  за «база не отвечает» (К-6); «база не отвечает» — по числу неудачных проходов подряд, разрыв между проходами больше 2×TICK_S (сон ПК)
  начинает счёт заново (К-7: time.monotonic на Windows — QueryPerformanceCounter, учитывает ли он сон, зависит от машины, поэтому не доверяем).
Telegram-часть — TgApi (urllib, без сторонних пакетов); всё остальное проверяется подменами (test_tg_bot.py) без сети.
Побочных эффектов при импорте нет (сеть и pyodbc — лениво, внутри функций).
"""

import asyncio
import datetime as dt
import json
import os
import re
import socket
import time

import botcfg
import outbox_bot
import player_reports

TICK_S = 20                       # период цикла
CLAIM_MAX = 1                     # записей за проход
PER_HOUR = 20                     # вызовов Telegram за скользящий час
MSG_MAX = 4000                    # предел сообщения Telegram — 4096 знаков
TIMEOUT_S = 20
MAX_REPLY = 64 * 1024
QUIET = (23, 8)                   # = domains/notify.QUIET_FROM / QUIET_TO
PANEL_STALE_MIN = 15              # = domains/notify.PANEL_STALE_MIN
DB_DOWN_MIN = 15                  # база AsdaAdmin не отвечает с ПК дольше — сообщение
GAP_S = 2 * TICK_S + 30           # ★ р78 К-5: простой между КОНЦОМ прохода и началом следующего дольше — ПК спал, счёт заново
LOCAL_GAP_MIN = 30                # между своими сообщениями «служба / база» одного вида
LEDGER_MAX = 2000
API = "https://api.telegram.org"
METHODS = ("sendMessage", "getMe")
HERE = os.path.dirname(os.path.abspath(__file__))
SECRET_PATH = os.path.join(HERE, "telegram.env")
LEDGER_PATH = os.path.join(HERE, "tg_ledger.json")
DEFAULT_PROXY = None                     # ★ 25.11 (К-5): без прокси, пока он не задан в окружении
PREFIX = "Astory · "
_TOKEN_RX = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")


def mask(s, token=None):
    """Текст ошибки без токена (и без любого похожего на токен куска)."""
    s = str(s or "")
    if token:
        s = s.replace(token, "<token>")
    return _TOKEN_RX.sub("<token>", s)[:300]


def read_secret(path=SECRET_PATH):
    """telegram.env → (токен, номер чата). Нет файла или ключа — исключение (отправитель молчит)."""
    kv = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\s*(TG_TOKEN|TG_CHAT)\s*=\s*(\S+)\s*$", line)
            if m:
                kv[m.group(1)] = m.group(2).strip().strip('"')
    tok, chat = kv.get("TG_TOKEN", ""), kv.get("TG_CHAT", "")
    if not _TOKEN_RX.fullmatch(tok):
        raise ValueError("telegram.env: нет TG_TOKEN")
    if not chat.isdigit() or int(chat) <= 0:
        raise ValueError("telegram.env: TG_CHAT — номер личного чата (положительное число)")
    return tok, int(chat)


def quiet_now(now=None):
    h = (now or dt.datetime.now()).hour
    return h >= QUIET[0] or h < QUIET[1]


def compose(it):
    """Текст сообщения: подпись события и текст; подавленные повторы, не поставленные из-за предела и склеенные повторы — числами из столбцов
    (★ р77 М-3; тот же хвост — domains/notify.full_text)."""
    if it.get("kind") == "ping":
        body = (it.get("text") or "").strip()
    else:
        body = "%s%s\n%s" % (PREFIX, (it.get("title") or "").strip(), (it.get("text") or "").strip())
    if int(it.get("supp_n") or 0) > 0:
        body += "\n(ещё повторов этого события за паузу: %d)" % int(it["supp_n"])
    if int(it.get("over_n") or 0) > 0:
        body += "\n(уведомлений не поставлено из-за предела частоты: %d)" % int(it["over_n"])
    if int(it.get("repeats") or 0) > 0:
        body += "\n(повторов до отправки: %d)" % int(it["repeats"])
    return body if len(body) <= MSG_MAX else body[:MSG_MAX - 1] + "…"


class TgError(Exception):
    """Сбой Telegram. definite=True — сообщение точно НЕ ушло (ответ с ошибкой, нет связи), False — итог неизвестен (тайм-аут ответа)."""

    def __init__(self, text, definite):
        super().__init__(text)
        self.definite = definite


class TgApi:
    """Bot API — только METHODS. opener — подставной для тестов (urllib.request.OpenerDirector-подобный: open(req, timeout))."""

    def __init__(self, token, chat, proxy=DEFAULT_PROXY, opener=None):
        self.token, self.chat = token, int(chat)
        if self.chat <= 0:
            raise ValueError("чат Telegram — только личный (положительный номер)")
        self._opener, self.proxy = opener, proxy

    def _open(self):
        if self._opener is None:
            import urllib.request
            self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": self.proxy} if self.proxy else {}))
        return self._opener

    def call(self, method, params):
        import http.client
        import urllib.error
        import urllib.request
        if method not in METHODS:
            raise TgError("метод Telegram %s запрещён отправителю" % method, True)
        req = urllib.request.Request("%s/bot%s/%s" % (API, self.token, method), data=json.dumps(params).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self._open().open(req, timeout=TIMEOUT_S) as r:
                body = r.read(MAX_REPLY)
        except urllib.error.HTTPError as e:
            desc = ""
            try:
                desc = json.loads(e.read(MAX_REPLY) or b"{}").get("description") or ""
            except (ValueError, OSError, AttributeError):
                pass
            raise TgError("Telegram HTTP %s: %s" % (e.code, mask(desc, self.token)), True)
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise TgError("тайм-аут ответа Telegram — итог неизвестен", False)
            raise TgError("нет связи с Telegram (%s)" % type(e.reason).__name__, True)
        except (socket.timeout, TimeoutError):
            raise TgError("тайм-аут ответа Telegram — итог неизвестен", False)
        except http.client.HTTPException as e:       # ★ р77 К-5: IncompleteRead, BadStatusLine… — ответ оборван, сообщение могло уйти
            raise TgError("ответ Telegram оборван (%s) — итог неизвестен" % type(e).__name__, False)
        except OSError as e:
            raise TgError("обрыв связи с Telegram (%s) — итог неизвестен" % type(e).__name__, False)
        try:
            j = json.loads(body)
        except ValueError:
            raise TgError("ответ Telegram не JSON — итог неизвестен", False)
        if not j.get("ok"):
            raise TgError("Telegram отказал: %s" % mask(j.get("description"), self.token), True)
        return j.get("result")

    def get_me(self):
        r = self.call("getMe", {}) or {}
        return "@%s" % r.get("username") if r.get("is_bot") and r.get("username") else "ответ без имени бота"

    def send(self, text, silent=False):
        r = self.call("sendMessage", {"chat_id": self.chat, "text": text, "disable_notification": bool(silent),
                                      "link_preview_options": {"is_disabled": True}}) or {}
        return r.get("message_id")


class Ledger:
    """Журнал отправителя на ПК: номер записи → {state: sending | sent | failed, msg, utc}; «_local» — свои сообщения «служба / база».
    Запись — атомарно (временный файл + os.replace)."""

    def __init__(self, path=LEDGER_PATH):
        self.path, self.data = path, {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)          # повреждён — исключение: без журнала отправлять нельзя (иначе возможен повтор)

    def get(self, oid):
        return self.data.get(str(oid))

    def put(self, oid, **kw):
        self.data[str(oid)] = dict(kw, utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        ids = sorted((k for k in self.data if k.isdigit()), key=int)
        for k in ids[:max(0, len(ids) - LEDGER_MAX)]:
            del self.data[k]
        self.save()

    def local(self):
        return dict(self.data.get("_local") or {})

    def set_local(self, d):
        self.data["_local"] = d
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=0)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)


class Store(outbox_bot.Store):
    """Процедуры очереди Telegram под логином asda_reports (соединение и секрет — как у жалоб и очереди Discord)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.tg_nonce = None

    def tg_claim(self, n=CLAIM_MAX, test_only=False):
        if self.tg_nonce is None:
            import uuid
            self.tg_nonce = str(uuid.uuid4())
        rows = self._rows("EXEC adm.TgClaim ?, ?, ?", int(n), self.tg_nonce, 1 if test_only else 0)
        keys = ("id", "kind", "title", "text", "test", "quiet", "event", "repeats", "expires_utc", "attempts", "now_utc", "supp_n", "over_n")
        return [dict(zip(keys, tuple(r))) for r in rows]

    def tg_claimed_ok(self):
        self.tg_nonce = None

    def tg_done(self, oid, ok, error="", expired=False, retry=False, message_id=None):
        r = self._rows("EXEC adm.TgDone ?, ?, ?, ?, ?, ?", int(oid), 1 if ok else 0, 1 if expired else 0, 1 if retry else 0,
                       player_reports.clean_line(error, 400), message_id)
        return int(r[0][0])

    def tg_local(self, kind, text, ok, message_id=None, error=""):
        """★ р77 К-3: своё сообщение ПК — строкой очереди для экрана."""
        self._rows("EXEC adm.TgLocalNote ?, ?, ?, ?, ?", kind, player_reports.clean_line(text, 400), 1 if ok else 0, message_id,
                   player_reports.clean_line(error, 400))

    def tg_beat(self):
        r = self._rows("EXEC adm.TgBeatGet")
        keys = ("beat_utc", "age_s", "master", "panel_down", "now_utc")
        return dict(zip(keys, tuple(r[0]))) if r else {}


CONFIG_ERRORS = (2812, 229, 230)   # ★ р78 М-1: нет процедуры (2812), нет прав (229, 230) — настройка; остальное (4060 — база недоступна,
                                   # 18456 — отказ входа, в том числе при старте SQL Server, обрывы) — «не отвечает»


def sql_errors(e):
    """Номера ошибок SQL Server из текста pyodbc («… (2812) (SQLExecDirectW)»)."""
    return {int(x) for x in re.findall(r"\((\d{3,5})\)", str(e))}


def db_config_error(e):
    """★ р77 К-6 / р78 М-1: сбой базы из-за настройки отправителя (нет процедуры, нет прав) — по номеру ошибки SQL Server, а не по SQLSTATE."""
    return bool(sql_errors(e) & set(CONFIG_ERRORS))


class Limiter:
    """Не больше per_hour вызовов за скользящий час. clock — подставные часы для тестов."""

    def __init__(self, per_hour=PER_HOUR, clock=time.monotonic):
        self.per_hour, self.clock, self.times = per_hour, clock, []

    def ok(self):
        now = self.clock()
        self.times = [t for t in self.times if now - t < 3600]
        return len(self.times) < self.per_hour

    def mark(self):
        self.times.append(self.clock())


class Worker:
    """Один проход: отметка службы (свои сообщения «служба / база»), затем одна запись очереди. api — TgApi или подмена; None — секрета нет."""

    def __init__(self, store, api=None, ledger=None, limiter=None, log=None, mono=time.monotonic, proxy=None, secret=SECRET_PATH, clock=None):
        self.store, self.limiter, self.log, self.mono = store, limiter or Limiter(), log, mono
        self._api, self._ledger, self.proxy, self.secret, self.clock = api, ledger, proxy, secret, clock
        self._no_secret = False
        self.flags = None                          # (общий выключатель, «служба не отвечает» включено) — последние прочитанные
        self.db_fail_since = None
        self.db_fails = 0                          # ★ р77 К-7: неудачных проходов подряд
        self.last_tick = None                      # ★ р78 К-5: КОНЕЦ прошлого прохода (разрыв = простой между проходами, долгий вызов его не растит)
        self.db_cfg = False                        # последний сбой — настройка (другой текст сообщения)
        self.cfg_said = False
        self.sent = 0

    def _say(self, text):
        if self.log:
            self.log(text)

    @property
    def ledger(self):
        if self._ledger is None:
            self._ledger = Ledger()
        return self._ledger

    def api(self):
        if self._api is None and not self._no_secret:
            try:
                tok, chat = read_secret(self.secret)
                self._api = TgApi(tok, chat, proxy=self.proxy or botcfg.proxy("TELEGRAM_PROXY", "DISCORD_PROXY", "HTTPS_PROXY"))
            except (OSError, ValueError) as e:
                self._no_secret = True             # один раз: без секрета отправитель молчит и записи не берёт
                self._say("Telegram: отправитель выключен — %s" % mask(e))
        return self._api

    def _now(self):
        return self.clock() if self.clock else dt.datetime.now()

    async def _done(self, it, **kw):
        try:
            return await asyncio.to_thread(self.store.tg_done, it["id"], **kw)
        except Exception as e:                     # итог не записан — запись останется «взята»; журнал не даст отправить её второй раз
            self._say("Telegram: итог №%d не записан (%s)" % (it["id"], type(e).__name__))
            return 0

    async def one(self, api, it, t_claim):
        oid = it["id"]
        if it.get("test"):
            if (it.get("title") or "") == "check":
                self.limiter.mark()
                try:
                    who = await asyncio.to_thread(api.get_me)
                except TgError as e:
                    return await self._done(it, ok=False, error="getMe не прошёл: %s" % e)
                return await self._done(it, ok=True, error="getMe: %s — токен и связь в порядке, сообщение не отправлялось" % who)
            return await self._done(it, ok=True, error="проверочная запись — Telegram не вызывался")
        led = self.ledger.get(oid)
        if led and led.get("state") == "sent":
            return await self._done(it, ok=True, message_id=led.get("msg"))
        if led and led.get("state") == "sending":
            return await self._done(it, ok=False, error="итог неизвестен: отправка прервалась — проверьте чат, повторно эта запись не отправляется")
        if led is None and int(it.get("attempts") or 1) > 1:
            return await self._done(it, ok=False, error="итог неизвестен: журнал отправителя не знает эту запись, а попыток уже %d — повторно "
                                                        "она не отправляется" % int(it["attempts"]))
        now_srv = it["now_utc"] + dt.timedelta(seconds=max(0.0, self.mono() - t_claim))
        if now_srv >= it["expires_utc"]:
            self.ledger.put(oid, state="failed")
            return await self._done(it, ok=False, expired=True, error="просрочено: срок годности прошёл до отправки")
        text = compose(it)
        silent = bool(it.get("quiet")) and quiet_now(self._now())
        self.ledger.put(oid, state="sending")
        self.limiter.mark()
        try:
            mid = await asyncio.to_thread(api.send, text, silent)
        except TgError as e:
            if e.definite:
                self.ledger.put(oid, state="failed")
                return await self._done(it, ok=False, retry=True, error=str(e))
            return await self._done(it, ok=False, error="%s — проверьте чат, повторно эта запись не отправляется" % e)
        self.ledger.put(oid, state="sent", msg=mid)
        self.sent += 1
        self._say("Telegram №%d: отправлено%s" % (oid, " без звука" if silent else ""))
        return await self._done(it, ok=True, message_id=mid)

    async def _local(self, api, kind, text):
        """Своё сообщение «служба / база» (не из очереди): не чаще LOCAL_GAP_MIN одного вида, по пределу частоты, без повтора при сбое."""
        loc = self.ledger.local()
        last = loc.get("last_" + kind)
        now = time.time()
        if last and now - float(last) < LOCAL_GAP_MIN * 60:
            return False
        if not self.limiter.ok():
            return False
        self.limiter.mark()
        loc["last_" + kind] = now
        self.ledger.set_local(loc)
        ok, mid, err = False, None, ""
        try:
            mid = await asyncio.to_thread(api.send, PREFIX + text, False)
            ok = True
            self._say("Telegram: %s" % text)
        except TgError as e:
            err = str(e)
            self._say("Telegram: своё сообщение не ушло (%s)" % e)
        notes = list(self.ledger.local().get("notes") or []) + [[kind, text, ok, mid, err]]
        loc = self.ledger.local()
        loc["notes"] = notes[-20:]                 # ★ р77 К-3: на экран — при первой доступной базе
        self.ledger.set_local(loc)
        await self._flush_notes()
        return ok

    async def _flush_notes(self):
        loc = self.ledger.local()
        notes = list(loc.get("notes") or [])
        while notes:
            k, t, ok, mid, err = notes[0]
            try:
                await asyncio.to_thread(self.store.tg_local, k, t, ok, mid, err)
            except Exception:
                break                              # база недоступна — запишется потом
            notes.pop(0)
        loc = self.ledger.local()
        loc["notes"] = notes
        self.ledger.set_local(loc)

    async def beat(self, api):
        """«Служба панели не отвечает»: отметка службы старше PANEL_STALE_MIN или база не отвечает с ПК дольше DB_DOWN_MIN."""
        loc = self.ledger.local()
        t = self.mono()
        if self.last_tick is not None and t - self.last_tick > GAP_S:
            self.db_fail_since, self.db_fails = None, 0   # ★ р77 К-7 / р78 К-5: простой между проходами (сон ПК) — счёт заново
        try:
            b = await asyncio.to_thread(self.store.tg_beat)
        except Exception as e:
            cfg = db_config_error(e)
            if cfg and not self.cfg_said:              # ★ р78 М-1: нет процедуры или прав — тоже сообщение через 15 мин, но со своим текстом
                self._say("Telegram: отправитель не может читать отметку службы — нет процедуры или прав в AsdaAdmin (%s)" % type(e).__name__)
                self.cfg_said = True
            if self.db_fail_since is None:
                self.db_fail_since = t
                if not cfg:
                    self._say("Telegram: база AsdaAdmin не отвечает (%s)" % type(e).__name__)
            self.db_fails += 1
            self.db_cfg = cfg
            on = self.flags and self.flags[0] and self.flags[1]
            if on and not loc.get("db_down") and t - self.db_fail_since >= DB_DOWN_MIN * 60 and self.db_fails >= 2:
                text = ("отправитель на ПК больше %d мин не может читать отметку службы: нет процедуры или прав в AsdaAdmin (проверьте "
                        "adminc_29_telegram.sql) — уведомления о событиях не доходят" % DB_DOWN_MIN) if cfg else (
                       "служба панели не отвечает: база AsdaAdmin недоступна с ПК больше %d мин (сервер, VPN или SQL Server) — уведомления о "
                       "событиях не доходят" % DB_DOWN_MIN)
                if await self._local(api, "db", text):
                    loc = self.ledger.local()
                    loc["db_down"] = True
                    self.ledger.set_local(loc)
            return None
        self.db_fail_since, self.db_fails, self.cfg_said = None, 0, False
        self.flags = (bool(b.get("master")), bool(b.get("panel_down")))
        if loc.get("notes"):
            await self._flush_notes()
            loc = self.ledger.local()
        on = self.flags[0] and self.flags[1]
        if loc.get("db_down"):
            loc["db_down"] = False
            self.ledger.set_local(loc)
            if on:
                await self._local(api, "db_up", "база AsdaAdmin снова отвечает с ПК")
        age = b.get("age_s")
        stale = age is None or int(age) >= PANEL_STALE_MIN * 60
        if stale and on and not loc.get("panel_down"):
            last = b.get("beat_utc")
            if await self._local(api, "panel", "служба админ-центра не отмечалась %s (последний раз %s UTC) — поиск событий, задания и "
                                                "объявления панели стоят" % ("ни разу" if age is None else "%d мин" % (int(age) // 60),
                                                                              last.strftime("%Y-%m-%d %H:%M") if last else "—")):
                loc = self.ledger.local()
                loc["panel_down"] = True
                self.ledger.set_local(loc)
        elif not stale and loc.get("panel_down"):
            loc["panel_down"] = False
            self.ledger.set_local(loc)
            if on:
                await self._local(api, "panel_up", "служба админ-центра снова отмечается")
        return b

    async def tick(self):
        api = self.api()
        if api is None:
            return
        try:
            await self._tick(api)
        finally:
            self.last_tick = self.mono()           # ★ р78 К-5: конец прохода

    async def _tick(self, api):
        await self.beat(api)
        if not self.limiter.ok():
            return
        try:
            items = await asyncio.to_thread(self.store.tg_claim, CLAIM_MAX)
        except Exception as e:
            self._say("Telegram: очередь не прочитана (%s)" % type(e).__name__)
            return
        t_claim = self.mono()
        for it in items:
            await self.one(api, it, t_claim)
        self.store.tg_claimed_ok()
