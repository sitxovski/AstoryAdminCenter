#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""outbox_bot.py — очередь исходящих сообщений панели Astory → Discord (шаг А7.4 админ-центра, 23.11.2026; решение владельца А7 №2: в Discord
публикуется только то, что оператор поставил флажком «и в Discord» в форме объявления; тексты EN / RU / AR — его, канал и роль — из списка).

ПУТЬ. Панель кладёт запись в AsdaAdmin.adm.Outbox (AstoryAdminCenter/sql/adminc_28_outbox.sql), бот раз в TICK_S забирает её процедурой
adm.OutboxClaim ТЕМ ЖЕ логином asda_reports, что ответы на жалобы (пароль — reports.env рядом с ботом, player_reports.Store), публикует и
отмечает adm.OutboxDone. Удаление опубликованного (операция владельца в панели) — adm.OutboxDelClaim / adm.OutboxDelDone.
ЗАЩИТЫ (все — в коде, в ini и .env их нет; оператор их не задаёт):
  * белые списки: каналы CHANNELS (announcements, форум updates, test-info — по имени без эмодзи и типу канала, ровно один на сервере),
    роли ROLES (News Ping, Patch Ping, Playtest Ping — по имени без эмодзи, ровно одна). Чего нет в списке — не публикуется;
  * @everyone и @here — никогда: текст с ними не публикуется, AllowedMentions(everyone=False, users=False, roles=[только выбранная]);
  * срок годности: позже expires_utc не публикуется («просрочено»); время — по часам SQL сервера из захвата, не по часам ПК;
  * один раз: номер записи пишется в журнал бота outbox_ledger.json ДО отправки («отправляю») и после неё («опубликовано», id сообщения).
    Повтор того же номера (сбой отметки, кнопка «повторить») бот не публикует: опубликованное — отмечается заново теми же id, прерванное
    на середине — ошибкой «итог неизвестен, проверьте канал»; точный отказ — state=refused (★ р76 К1: номера нет в журнале, а попыток > 1 —
    журнал потерян, не публикуется). Собственный повтор discord.py при 5xx у сообщения в канале гасит nonce (enforce_nonce); у ветки форума
    nonce нет — дубль возможен только при сбое шлюза Discord в форуме (★ р76 М-2: бот ищет свои ветки с тем же именем и предупреждает);
  * удаляет только своё (★ р76 М-1): id совпадают с журналом бота (state=posted), автор сообщения / владелец ветки — этот бот;
  * предел частоты: не чаще раза в MIN_GAP_S и не больше PER_HOUR публикаций за час (скользящий час), плюс пределы базы (6 / час, 30 / сутки);
  * проверочные записи (kind test) Discord не трогают вовсе: только отметка «тест».
Discord-часть — DiscordAdapter (тонкая обёртка над discord.Guild); всё остальное проверяется подменами (test_outbox_bot.py) без сети.
Побочных эффектов при импорте нет (discord и pyodbc — лениво, внутри функций).
"""

import asyncio
import datetime as dt
import json
import os
import re
import time
import unicodedata
import uuid

import player_reports

TICK_S = 30                      # период цикла бота
CLAIM_MAX = 1                    # записей за проход (одна: между публикациями — не меньше TICK_S)
MIN_GAP_S = 10                   # между публикациями
PER_HOUR = 10                    # публикаций за скользящий час (поверх 6 / час базы — запас на повторы)
MSG_MAX = 2000                   # предел сообщения Discord
TITLE_MAX = 100                  # имя ветки форума
LEDGER_MAX = 2000                # записей в журнале бота (старые вытесняются)
THREAD_LOOKBACK_MIN = 30         # ★ р76 М-2: окно поиска своей ветки форума с тем же именем (прерванная публикация, дубль при сбое шлюза)
FORUM_KEYS = ("updates",)
LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox_ledger.json")

# ★ белые списки — ключи те же, что CHECK adm.Outbox и domains/outbox.py (самотест панели сверяет): ключ → (имя без эмодзи, допустимые типы)
CHANNELS = {"announcements": ("announcements", ("news", "text")), "updates": ("updates", ("forum",)), "test-info": ("testinfo", ("text",))}
ROLES = {"news": "newsping", "patch": "patchping", "playtest": "playtestping"}
FORBIDDEN = ("@everyone", "@here")
LANGS = (("en", "🇬🇧"), ("ar", "🇸🇦"), ("ru", "🇷🇺"))   # как announce_restart.py: EN, AR, RU
_MENTION = re.compile(r"<@[!&]?\d*>?|<#\d+>")


def norm(name):
    """Имя канала / роли → только латиница и цифры в нижнем регистре (как announce_restart: «📣┃announcements» → announcements)."""
    kept = "".join(ch for ch in str(name or "") if unicodedata.category(ch)[0] in ("L", "N"))
    return re.sub(r"[^a-z0-9]", "", kept.casefold())


def compose(mention, en, ru, ar):
    """Текст сообщения: упоминание роли и строки языков с флагами. ★ Тот же текст собирает панель (domains/outbox.compose)."""
    parts = [mention] if mention else []
    vals = {"en": en, "ru": ru, "ar": ar}
    for k, flag in LANGS:
        v = (vals.get(k) or "").strip()
        if v:
            parts.append("%s %s" % (flag, v))
    return "\n".join(parts)


def nonce_of(oid):
    """★ р76 М-2: nonce сообщения Discord по номеру записи (≤ 25 знаков)."""
    return ("astory-ob-%d" % int(oid))[:25]


def dlen(s):
    """★ р76 К7: длина для пределов Discord (2000 у сообщения, 100 у имени ветки) — в единицах UTF-16. Как именно Discord считает «знаки»,
    по документации discord.py и API не установлено (discord.py длину не проверяет); UTF-16 не меньше числа кодовых точек — запас: флаги и
    эмодзи вне BMP считаются за 2, и отказа 4xx из-за длины не будет."""
    return len(str(s or "").encode("utf-16-le")) // 2


def forbidden_in(*texts):
    low = " ".join(t or "" for t in texts).lower()
    return any(f in low for f in FORBIDDEN)


class AdapterError(Exception):
    """Сбой Discord. definite=True — сообщение точно НЕ опубликовано (отказ 4xx), False — итог неизвестен (тайм-аут, обрыв)."""

    def __init__(self, text, definite):
        super().__init__(text)
        self.definite = definite


class Ledger:
    """Журнал бота на ПК: номер записи → {state: sending | posted, ch, msg, utc}. Запись — атомарно (временный файл + os.replace)."""

    def __init__(self, path=LEDGER_PATH):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)          # повреждён — исключение: без журнала публиковать нельзя (иначе возможен повтор)

    def get(self, oid):
        return self.data.get(str(oid))

    def put(self, oid, **kw):
        self.data[str(oid)] = dict(kw, utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        if len(self.data) > LEDGER_MAX:
            for k in sorted(self.data, key=int)[:len(self.data) - LEDGER_MAX]:
                del self.data[k]
        self.put_all()

    def drop(self, oid):
        if self.data.pop(str(oid), None) is not None:
            self.put_all()

    def put_all(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=0)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)


class Limiter:
    """Не чаще раза в gap секунд и не больше per_hour за скользящий час. clock — подставные часы для тестов."""

    def __init__(self, gap=MIN_GAP_S, per_hour=PER_HOUR, clock=time.monotonic):
        self.gap, self.per_hour, self.clock, self.times = gap, per_hour, clock, []

    def ok(self):
        now = self.clock()
        self.times = [t for t in self.times if now - t < 3600]
        return len(self.times) < self.per_hour and (not self.times or now - self.times[-1] >= self.gap)

    def mark(self):
        self.times.append(self.clock())


class Store(player_reports.Store):
    """Процедуры очереди adm.Outbox* под логином asda_reports (соединение и секрет — как у жалоб). connect — подставная фабрика для тестов."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.out_nonce = None
        self.del_nonce = None

    def _rows(self, sql, *args):
        cn = self._cn()
        try:
            cur = cn.cursor().execute(sql, *args)
            rows = cur.fetchall()
            while cur.nextset():                    # дочитать хвост ответа процедуры: соединение свободно для следующей команды
                pass
            cur.close()
            return rows
        finally:
            cn.close()

    def out_claim(self, n=CLAIM_MAX, test_only=False):
        """Записи к публикации → [dict]. Номер захвата живёт до out_claimed_ok (сбой по дороге — те же строки ещё раз)."""
        if self.out_nonce is None:
            self.out_nonce = str(uuid.uuid4())
        rows = self._rows("EXEC adm.OutboxClaim ?, ?, ?", int(n), self.out_nonce, 1 if test_only else 0)
        keys = ("id", "kind", "channel", "role", "title", "en", "ru", "ar", "test", "expires_utc", "attempts", "now_utc")
        return [dict(zip(keys, tuple(r))) for r in rows]

    def out_claimed_ok(self):
        self.out_nonce = None

    def out_done(self, oid, ok, error="", expired=False, channel_id=None, message_id=None):
        r = self._rows("EXEC adm.OutboxDone ?, ?, ?, ?, ?, ?", int(oid), 1 if ok else 0, 1 if expired else 0,
                       player_reports.clean_line(error, 400), channel_id, message_id)
        return int(r[0][0])

    def del_claim(self, n=CLAIM_MAX):
        if self.del_nonce is None:
            self.del_nonce = str(uuid.uuid4())
        rows = self._rows("EXEC adm.OutboxDelClaim ?, ?", int(n), self.del_nonce)
        return [dict(zip(("id", "channel", "channel_id", "message_id"), tuple(r))) for r in rows]

    def del_claimed_ok(self):
        self.del_nonce = None

    def del_done(self, oid, ok, error=""):
        r = self._rows("EXEC adm.OutboxDelDone ?, ?, ?", int(oid), 1 if ok else 0, player_reports.clean_line(error, 400))
        return int(r[0][0])


class DiscordAdapter:
    """Тонкая обёртка над discord.Guild. Единственное место, где бот публикует и удаляет сообщения очереди."""

    def __init__(self, guild):
        self.guild = guild

    def channels(self):
        """[(id, имя, тип)] тип: text | news | forum | other."""
        import discord
        kinds = {discord.ChannelType.text: "text", discord.ChannelType.news: "news", discord.ChannelType.forum: "forum"}
        return [(c.id, c.name, kinds.get(getattr(c, "type", None), "other")) for c in self.guild.channels]

    def roles(self):
        return [(r.id, r.name) for r in self.guild.roles]

    @staticmethod
    def _err(ex):
        import discord
        if isinstance(ex, discord.HTTPException) and 400 <= int(getattr(ex, "status", 0) or 0) < 500:
            return AdapterError("Discord HTTP %s" % ex.status, True)
        if isinstance(ex, discord.HTTPException):
            return AdapterError("Discord HTTP %s — итог неизвестен" % ex.status, False)
        return AdapterError("сбой связи с Discord (%s) — итог неизвестен" % type(ex).__name__, False)

    async def post(self, channel_id, kind, title, content, role_id, oid):
        """Публикация. ★ ревизия 76 М-2: у сообщения в канале — nonce «astory-ob-<номер>»: discord.py 2.7.1 при nonce шлёт enforce_nonce=True
        (http.py handle_message_parameters), и Discord отбрасывает второй POST с тем же nonce в течение нескольких минут — так собственный повтор
        discord.py при 500/502/504/524 (http.py request) не даёт дубля. У ветки форума (create_thread) nonce нет: остаточный риск дубля при сбое
        шлюза Discord — бот после публикации ищет свои ветки с тем же именем и пишет предупреждение (find_threads). ★ К5: suppress_embeds —
        без превью ссылок."""
        import discord
        am = discord.AllowedMentions(everyone=False, users=False, replied_user=False,
                                     roles=[discord.Object(id=role_id)] if role_id else False)
        ch = self.guild.get_channel(channel_id)
        if ch is None:
            raise AdapterError("канал %s пропал" % channel_id, True)
        try:
            if kind == "forum":
                tw = await ch.create_thread(name=title[:TITLE_MAX], content=content, allowed_mentions=am, suppress_embeds=True)
                return tw.thread.id, tw.message.id
            msg = await ch.send(content, allowed_mentions=am, nonce=nonce_of(oid), suppress_embeds=True)
            return ch.id, msg.id
        except discord.DiscordException as ex:
            raise self._err(ex) from None
        except (OSError, asyncio.TimeoutError) as ex:
            raise self._err(ex) from None

    async def find_threads(self, forum_id, title, minutes):
        """★ р76 М-2: ветки форума, созданные ЭТИМ ботом, с тем же именем, моложе minutes минут → [id] (активные — из кэша гильдии)."""
        import discord
        ch = self.guild.get_channel(forum_id)
        me = self.guild.me.id
        cut = discord.utils.utcnow() - dt.timedelta(minutes=minutes)
        return [t.id for t in getattr(ch, "threads", []) or []
                if t.owner_id == me and t.name == title[:TITLE_MAX] and discord.utils.snowflake_time(t.id) >= cut]

    async def is_ours(self, channel_id, message_id, forum):
        """★ р76 М-1: сообщение (у форума — ветка, её первое сообщение = её id) опубликовал этот бот → True / False; нет в Discord → None."""
        import discord
        me = self.guild.me.id
        try:
            ch = self.guild.get_channel_or_thread(channel_id) if hasattr(self.guild, "get_channel_or_thread") else self.guild.get_channel(channel_id)
            if ch is None:
                ch = await self.guild.fetch_channel(channel_id)
            if forum:
                return getattr(ch, "owner_id", None) == me and ch.id == message_id
            msg = await ch.fetch_message(message_id)
            return msg.author.id == me
        except discord.NotFound:
            return None
        except discord.DiscordException as ex:
            raise self._err(ex) from None

    async def parent_of(self, thread_id):
        """Родитель ветки (id форума) или None."""
        import discord
        try:
            th = self.guild.get_thread(thread_id) or await self.guild.fetch_channel(thread_id)
        except discord.DiscordException:
            return None
        return getattr(th, "parent_id", None)

    async def delete(self, channel_id, message_id, forum):
        import discord
        try:
            ch = self.guild.get_channel_or_thread(channel_id) if hasattr(self.guild, "get_channel_or_thread") else self.guild.get_channel(channel_id)
            if ch is None:
                ch = await self.guild.fetch_channel(channel_id)
            if forum:
                await ch.delete(reason="Astory: удаление объявления из панели (владелец)")
            else:
                await ch.get_partial_message(message_id).delete()
        except discord.NotFound:
            return "уже удалено"
        except discord.DiscordException as ex:
            raise self._err(ex) from None
        return "удалено"


async def allowed_place(adapter, channel_id, key):
    """Удалять можно только в каналах белого списка: сам канал (у форума — родитель ветки) должен быть разрешённым каналом этого ключа."""
    want = CHANNELS.get(key)
    if not want:
        return False
    ok_ids = {cid for cid, name, kind in adapter.channels() if norm(name) == want[0] and kind in want[1]}
    if "forum" in want[1]:
        return await adapter.parent_of(channel_id) in ok_ids
    return channel_id in ok_ids


class Worker:
    """Один проход цикла: публикации, затем удаления. store — Store (или подмена), ledger — Ledger, limiter — Limiter."""

    def __init__(self, store, ledger=None, limiter=None, log=None, mono=time.monotonic):
        self.store, self.limiter, self.log, self.mono = store, limiter or Limiter(), log, mono
        self._ledger = ledger
        self.posted = 0

    @property
    def ledger(self):
        if self._ledger is None:
            self._ledger = Ledger()
        return self._ledger

    def _say(self, text):
        if self.log:
            self.log(text)

    def resolve(self, adapter, it):
        """Запись → (id канала, тип, id роли или None) или AdapterError(definite=True) с причиной."""
        want = CHANNELS.get(it["channel"])
        if not want:
            raise AdapterError("канал «%s» не из белого списка бота" % it["channel"], True)
        chans = [(cid, kind) for cid, name, kind in adapter.channels() if norm(name) == want[0] and kind in want[1]]
        if len(chans) != 1:
            raise AdapterError("канал «%s»: на сервере Discord найдено %d подходящих (нужен ровно один)" % (it["channel"], len(chans)), True)
        role_id = None
        if it.get("role"):
            rn = ROLES.get(it["role"])
            if not rn:
                raise AdapterError("роль «%s» не из белого списка бота" % it["role"], True)
            rs = [rid for rid, name in adapter.roles() if norm(name) == rn]
            if len(rs) != 1:
                raise AdapterError("роль «%s»: на сервере Discord найдено %d (нужна ровно одна)" % (it["role"], len(rs)), True)
            role_id = rs[0]
        return chans[0][0], chans[0][1], role_id

    def check(self, it):
        """Проверка записи до Discord → None (годна) или причина."""
        if it["channel"] not in CHANNELS:
            return "канал «%s» не из белого списка бота" % it["channel"]
        if it.get("role") and it["role"] not in ROLES:
            return "роль «%s» не из белого списка бота" % it["role"]
        if forbidden_in(it.get("title"), it.get("en"), it.get("ru"), it.get("ar")):
            return "в тексте @everyone или @here — бот это не публикует"
        if any(_MENTION.search(t or "") for t in (it.get("title"), it.get("en"), it.get("ru"), it.get("ar"))):
            return "в тексте упоминание <@…> или <#…> — бот это не публикует"
        if not (it.get("en") or "").strip():
            return "нет текста EN"
        if not (it.get("title") or "").strip():
            return "нет заголовка"
        return None

    async def _done(self, it, **kw):
        try:
            n = await asyncio.to_thread(self.store.out_done, it["id"], **kw)
        except Exception as e:                  # итог не записан — запись останется «бот взял»; журнал бота не даст опубликовать её второй раз
            self._say("очередь Discord: итог №%d не записан (%s)" % (it["id"], type(e).__name__))
            return 0
        return n

    async def _refuse(self, it, **kw):
        """★ р76 К1: точный отказ до публикации — номер остаётся в журнале бота со state=refused (повтор кнопкой допустим). Номера нет в журнале,
        а попыток уже больше одной — значит, журнал потерян: такую запись бот не публикует («итог неизвестен»)."""
        self.ledger.put(it["id"], state="refused")
        return await self._done(it, ok=False, **kw)

    async def one(self, adapter, it, t_claim):
        """Одна запись: итог пишется всегда (опубликовано / тест / просрочено / ошибка)."""
        oid = it["id"]
        if it.get("test") or it.get("kind") == "test":
            self._say("очередь Discord №%d: проверочная запись — в Discord не публикуется" % oid)
            return await self._done(it, ok=True)
        led = self.ledger.get(oid)
        if led and led.get("state") == "posted":
            self._say("очередь Discord №%d: уже опубликовано (журнал бота) — повтор не публикуется" % oid)
            return await self._done(it, ok=True, channel_id=led.get("ch"), message_id=led.get("msg"))
        if led and led.get("state") == "sending":
            found = await self._own_thread(adapter, it) if it["channel"] in FORUM_KEYS else []
            if len(found) == 1:                 # ★ р76 М-2: ветка уже есть (создана этим ботом с тем же именем) — это она, второй не будет
                self.ledger.put(oid, state="posted", ch=found[0], msg=found[0])
                return await self._done(it, ok=True, channel_id=found[0], message_id=found[0])
            return await self._done(it, ok=False, error="итог неизвестен: бот начал публикацию и прервался — проверьте канал в Discord, "
                                                        "повторно бот эту запись не публикует")
        if led is None and int(it.get("attempts") or 1) > 1:
            return await self._done(it, ok=False, error="итог неизвестен: журнал бота не знает эту запись, а попыток уже %d — проверьте канал "
                                                        "в Discord, повторно бот эту запись не публикует" % int(it["attempts"]))
        why = self.check(it)
        if why:
            return await self._refuse(it, error=why)
        # срок — по часам SQL: время сервера при захвате + сколько прошло у нас с захвата
        now_srv = it["now_utc"] + dt.timedelta(seconds=max(0.0, self.mono() - t_claim))
        if now_srv >= it["expires_utc"]:
            return await self._refuse(it, expired=True, error="просрочено: срок годности прошёл до публикации")
        try:
            cid, kind, role_id = self.resolve(adapter, it)
        except AdapterError as e:
            return await self._refuse(it, error=str(e))
        content = compose("<@&%d>" % role_id if role_id else "", it["en"], it.get("ru"), it.get("ar"))
        if dlen(content) > MSG_MAX or dlen(it["title"]) > TITLE_MAX:
            return await self._refuse(it, error="сообщение длиннее %d знаков" % MSG_MAX)
        self.ledger.put(oid, state="sending")
        self.limiter.mark()
        try:
            ch_id, msg_id = await adapter.post(cid, kind, it["title"], content, role_id, oid)
        except AdapterError as e:
            if e.definite:
                return await self._refuse(it, error=str(e))     # точно не опубликовано — повтор кнопкой допустим
            return await self._done(it, ok=False, error="%s — проверьте канал в Discord, повторно бот эту запись не публикует" % e)
        self.ledger.put(oid, state="posted", ch=ch_id, msg=msg_id)
        self.posted += 1
        self._say("очередь Discord №%d: опубликовано в «%s» (%s/%s)" % (oid, it["channel"], ch_id, msg_id))
        if kind == "forum":                     # ★ р76 М-2: у ветки nonce нет — проверить, не создал ли discord.py вторую при сбое шлюза
            dup = await self._own_thread(adapter, it, cid)
            if len(dup) > 1:
                self._say("очередь Discord №%d: ВНИМАНИЕ — в форуме %d веток бота с именем «%s» за %d мин (дубль при сбое шлюза Discord?) — "
                          "проверьте форум" % (oid, len(dup), it["title"], THREAD_LOOKBACK_MIN))
        return await self._done(it, ok=True, channel_id=ch_id, message_id=msg_id)

    async def _own_thread(self, adapter, it, forum_id=None):
        """Свои ветки форума с тем же именем за THREAD_LOOKBACK_MIN. ★ р83 М-2 (А7.7): ветки, которые журнал бота уже записал за другим номером
        очереди, отбрасываются — чужая (более ранняя) ветка с тем же именем не принимается за свою и не считается дублем."""
        try:
            if forum_id is None:
                forum_id = self.resolve(adapter, it)[0]
            found = await adapter.find_threads(forum_id, it["title"], THREAD_LOOKBACK_MIN)
        except Exception:
            return []
        me = str(it["id"])
        taken = {int(v.get("msg") or 0) for k, v in self.ledger.data.items() if k != me and v.get("state") == "posted"}
        return [t for t in found if int(t) not in taken]

    async def tick(self, adapter):
        """Проход: сколько можно по пределу — забрать и опубликовать, затем удаления. Сбой базы — до следующего прохода."""
        if self.limiter.ok():
            try:
                items = await asyncio.to_thread(self.store.out_claim, CLAIM_MAX)
            except Exception as e:
                self._say("очередь Discord: не прочитана (%s)" % type(e).__name__)
                items = None
            if items is not None:
                t_claim = self.mono()
                for it in items:
                    await self.one(adapter, it, t_claim)
                self.store.out_claimed_ok()
        try:
            dels = await asyncio.to_thread(self.store.del_claim, CLAIM_MAX)
        except Exception as e:
            self._say("очередь Discord: удаления не прочитаны (%s)" % type(e).__name__)
            return
        for d in dels:
            ok, res = False, ""
            led = self.ledger.get(d["id"]) or {}
            forum = d["channel"] in FORUM_KEYS
            if not d.get("channel_id") or not d.get("message_id"):
                res = "нет id сообщения"
            elif led.get("state") != "posted" or led.get("ch") != d["channel_id"] or led.get("msg") != d["message_id"]:
                res = "id сообщения не совпадают с журналом бота — не удаляю"            # ★ р76 М-1: удаляется только то, что бот сам опубликовал
            elif not await allowed_place(adapter, d["channel_id"], d["channel"]):
                res = "канал сообщения не из белого списка бота — не удаляю"
            else:
                try:
                    ours = await adapter.is_ours(d["channel_id"], d["message_id"], forum)
                    if ours is None:
                        res, ok = "уже удалено", True
                    elif not ours:
                        res = "сообщение опубликовал не этот бот — не удаляю"
                    else:
                        res = await adapter.delete(d["channel_id"], d["message_id"], forum)
                        ok = True
                except AdapterError as e:
                    res = str(e)
            try:
                await asyncio.to_thread(self.store.del_done, d["id"], ok, res)
            except Exception as e:
                self._say("очередь Discord: итог удаления №%d не записан (%s)" % (d["id"], type(e).__name__))
            self._say("очередь Discord №%d: удаление — %s" % (d["id"], res))
        self.store.del_claimed_ok()
