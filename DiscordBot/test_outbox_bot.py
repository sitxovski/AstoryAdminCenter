#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""test_outbox_bot.py — модульные тесты очереди объявлений бота (А7.4, 23.11.2026) БЕЗ подключения к Discord и к базе.

Запуск: python -I AstoryAdminCenter/DiscordBot/test_outbox_bot.py  (код 0 — всё прошло).
Discord подменён: Worker — подставным адаптером (записывает вызовы, ничего не отправляет), DiscordAdapter — подставной гильдией и каналами
(настоящие классы discord.py только для AllowedMentions / ChannelType / исключений — сеть не трогается). Что проверяется: белые списки каналов и
ролей (по имени без эмодзи и по типу, ровно один), @everyone / @here и <@…> не публикуются, срок годности по часам SQL, один раз по номеру записи
(журнал бота: опубликовано — не повторяется, прервано — «итог неизвестен», точный отказ — повтор допустим), проверочные записи Discord не
трогают вовсе, предел частоты, удаление — только в разрешённом канале (у форума — родитель ветки), вызовы процедур Store (имена, порядок
параметров, номер захвата), AllowedMentions адаптера (everyone=False, users=False, только выбранная роль), форум — новая ветка с заголовком;
по исходнику oracle_bot.py (ast, без импорта) — цикл очереди запускается в setup_hook, его тело — только outbox.tick.
Связка с настоящими процедурами (LocalDB, adminc_28) — в самотесте панели tests/selftest_outbox_a7.py.
"""

import ast
import asyncio
import datetime as dt
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import outbox_bot as O  # noqa: E402

NOW = dt.datetime(2026, 11, 23, 12, 0, 0)
CH = [(101, "📣┃announcements", "news"), (102, "⚙️┃updates-old", "news"), (103, "updates", "forum"), (104, "📋┃test-info", "text"),
      (105, "general", "text"), (106, "🔔┃discord-updates", "text")]
RL = [(201, "📢 News Ping"), (202, "⚙️ Patch Ping"), (203, "🧪 Playtest Ping"), (204, "@everyone"), (205, "Beta Tester")]


def item(oid=1, **kw):
    it = {"id": oid, "kind": "announce", "channel": "announcements", "role": "news", "title": "Server restart at 18:00", "en": "Restart soon",
          "ru": "Скоро рестарт", "ar": "إعادة التشغيل قريبا", "test": False, "expires_utc": NOW + dt.timedelta(minutes=30), "attempts": 1, "now_utc": NOW}
    it.update(kw)
    return it


class FakeAdapter:
    def __init__(self, channels=CH, roles=RL, fail=None, parents=None, threads=None, foreign=()):
        self.ch, self.rl, self.fail, self.parents = list(channels), list(roles), fail, parents or {}
        self.posts, self.deletes, self.calls, self.oids = [], [], 0, []
        self.threads = threads if threads is not None else []      # найденные «свои» ветки с тем же именем
        self.foreign = set(foreign)                                # id сообщений / веток, опубликованных НЕ ботом

    def channels(self):
        self.calls += 1
        return self.ch

    def roles(self):
        self.calls += 1
        return self.rl

    async def post(self, channel_id, kind, title, content, role_id, oid):
        self.calls += 1
        if self.fail:
            raise self.fail
        self.posts.append((channel_id, kind, title, content, role_id))
        self.oids.append(oid)
        if kind == "forum":                                  # у ветки форума id первого сообщения = id ветки
            tid = channel_id + 9000 + len(self.posts)
            return tid, tid
        return channel_id, 777000 + len(self.posts)

    async def find_threads(self, forum_id, title, minutes):
        return list(self.threads)

    async def is_ours(self, channel_id, message_id, forum):
        return message_id not in self.foreign

    async def parent_of(self, thread_id):
        return self.parents.get(thread_id)

    async def delete(self, channel_id, message_id, forum):
        self.calls += 1
        self.deletes.append((channel_id, message_id, forum))
        return "удалено"


class NoDiscord(FakeAdapter):
    """Любой вызов Discord — ошибка теста."""

    def channels(self):
        raise AssertionError("Discord тронут")

    def roles(self):
        raise AssertionError("Discord тронут")

    async def post(self, *a):
        raise AssertionError("Discord тронут")


class FakeStore:
    def __init__(self, items=None, dels=None):
        self.items, self.dels, self.done, self.del_done_log, self.claims = list(items or []), list(dels or []), [], [], 0

    def out_claim(self, n=1):
        self.claims += 1
        out, self.items = self.items[:n], self.items[n:]
        return out

    def out_claimed_ok(self):
        pass

    def out_done(self, oid, ok, error="", expired=False, channel_id=None, message_id=None):
        self.done.append({"id": oid, "ok": ok, "error": error, "expired": expired, "ch": channel_id, "msg": message_id})
        return 1

    def del_claim(self, n=1):
        out, self.dels = self.dels[:n], self.dels[n:]
        return out

    def del_claimed_ok(self):
        pass

    def del_done(self, oid, ok, error=""):
        self.del_done_log.append((oid, ok, error))
        return 1


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def run(coro):
    return asyncio.run(coro)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "ledger.json")
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def worker(self, store, ledger=None):
        return O.Worker(store, ledger=ledger or O.Ledger(self.path), limiter=O.Limiter(clock=self.clock), mono=self.clock)


class TestText(unittest.TestCase):
    def test_norm(self):
        self.assertEqual([O.norm(n) for _i, n, _k in CH], ["announcements", "updatesold", "updates", "testinfo", "general", "discordupdates"])
        self.assertEqual([O.norm(n) for _i, n in RL][:3], ["newsping", "patchping", "playtestping"])

    def test_compose(self):
        self.assertEqual(O.compose("<@&1>", "a", "b", "c"), "<@&1>\n🇬🇧 a\n🇸🇦 c\n🇷🇺 b")
        self.assertEqual(O.compose("", "a", "", None), "🇬🇧 a")

    def test_whitelists(self):
        self.assertEqual(set(O.CHANNELS), {"announcements", "updates", "test-info"})
        self.assertEqual(set(O.ROLES), {"news", "patch", "playtest"})
        self.assertTrue(O.forbidden_in("hi @EveryOne"))
        self.assertTrue(O.forbidden_in(None, "x @here"))
        self.assertFalse(O.forbidden_in("everyone here"))


class TestWorker(Base):
    def test_publish_once_with_role(self):
        st, ad = FakeStore([item(1)]), FakeAdapter()
        w = self.worker(st)
        run(w.tick(ad))
        self.assertEqual(len(ad.posts), 1)
        cid, kind, title, content, role = ad.posts[0]
        self.assertEqual((cid, kind, role), (101, "news", 201))
        self.assertTrue(content.startswith("<@&201>\n🇬🇧 Restart soon"))
        self.assertEqual(st.done, [{"id": 1, "ok": True, "error": "", "expired": False, "ch": 101, "msg": 777001}])
        self.assertEqual(O.Ledger(self.path).get(1)["state"], "posted")
        # повтор того же номера (кнопка «повторить», сбой отметки) — второй публикации нет, итог — те же id
        st.items = [item(1, attempts=2)]
        self.clock.t += 100
        run(w.tick(ad))
        self.assertEqual(len(ad.posts), 1)
        self.assertEqual(st.done[-1], {"id": 1, "ok": True, "error": "", "expired": False, "ch": 101, "msg": 777001})

    def test_interrupted_is_not_reposted(self):
        led = O.Ledger(self.path)
        led.put(5, state="sending")
        st, ad = FakeStore([item(5)]), FakeAdapter()
        run(self.worker(st, led).tick(ad))
        self.assertEqual(ad.posts, [])
        self.assertFalse(st.done[0]["ok"])
        self.assertIn("итог неизвестен", st.done[0]["error"])

    def test_test_record_never_touches_discord(self):
        st = FakeStore([item(2, kind="test", test=True, channel="test-info", role=None)])
        run(self.worker(st).tick(NoDiscord()))
        self.assertEqual(st.done, [{"id": 2, "ok": True, "error": "", "expired": False, "ch": None, "msg": None}])
        self.assertIsNone(O.Ledger(self.path).get(2))

    def test_expired_by_server_clock(self):
        st, ad = FakeStore([item(3, expires_utc=NOW + dt.timedelta(seconds=5))]), FakeAdapter()
        w = self.worker(st)
        # захват — в NOW по часам SQL; к проверке срока у бота прошло 6 с (первый вызов часов — момент захвата, второй — проверка)
        ticks = iter([1000.0, 1006.0])
        w.mono = lambda: next(ticks)
        run(w.tick(ad))
        self.assertEqual(ad.posts, [])
        self.assertTrue(st.done[0]["expired"])
        self.assertFalse(st.done[0]["ok"])

    def test_refusals_without_post(self):
        cases = [item(10, channel="general"), item(11, role="everyone"), item(12, en="hi @everyone"), item(13, ru="всем @Here"),
                 item(14, ar="<@123456789>"), item(15, title="<#105> look"), item(16, en="  ")]
        st, ad = FakeStore(cases), FakeAdapter()
        w = self.worker(st)
        for _ in cases:
            run(w.tick(ad))
            self.clock.t += 60
        self.assertEqual(ad.posts, [])
        self.assertEqual([d["ok"] for d in st.done], [False] * len(cases))
        self.assertTrue(all(d["error"] for d in st.done))

    def test_ambiguous_channel_or_role(self):
        ch = CH + [(107, "announcements", "text")]
        st, ad = FakeStore([item(20)]), FakeAdapter(channels=ch)
        run(self.worker(st).tick(ad))
        self.assertEqual(ad.posts, [])
        self.assertIn("найдено 2", st.done[0]["error"])
        st2, ad2 = FakeStore([item(21)]), FakeAdapter(roles=[(1, "📢 News Ping"), (2, "news ping")])
        run(self.worker(st2).tick(ad2))
        self.assertEqual(ad2.posts, [])

    def test_type_matters(self):
        # «updates» — только форум; новостной «updates-old» не подходит; «test-info» — только текстовый
        st, ad = FakeStore([item(22, channel="updates", role="patch")]), FakeAdapter()
        run(self.worker(st).tick(ad))
        self.assertEqual(ad.posts[0][:3], (103, "forum", "Server restart at 18:00"))
        self.assertEqual((st.done[0]["ch"], st.done[0]["msg"]), (9104, 9104))
        st2, ad2 = FakeStore([item(23, channel="test-info")]), FakeAdapter(channels=[(104, "📋┃test-info", "news")])
        run(self.worker(st2).tick(ad2))
        self.assertEqual(ad2.posts, [])

    def test_errors_definite_and_unknown(self):
        st, ad = FakeStore([item(30)]), FakeAdapter(fail=O.AdapterError("Discord HTTP 403", True))
        w = self.worker(st)
        run(w.tick(ad))
        self.assertEqual(O.Ledger(self.path).get(30)["state"], "refused")     # ★ р76 К1: номер не удаляется, а помечается
        self.assertEqual(st.done[0]["error"], "Discord HTTP 403")
        # точный отказ → «повторить» (попытка 2) — публикуется, раз номер в журнале «refused»
        st.items, ad.fail = [item(30, attempts=2)], None
        self.clock.t += 60
        run(w.tick(ad))
        self.assertEqual(len(ad.posts), 1)
        self.assertEqual(O.Ledger(self.path).get(30)["state"], "posted")
        ad.posts.clear()
        ad.fail = O.AdapterError("Discord HTTP 403", True)
        st.items = [item(31)]
        ad.fail = O.AdapterError("сбой связи с Discord (TimeoutError) — итог неизвестен", False)
        self.clock.t += 60
        run(w.tick(ad))
        self.assertEqual(O.Ledger(self.path).get(31)["state"], "sending")
        self.assertIn("повторно бот эту запись не публикует", st.done[-1]["error"])
        # тот же номер ещё раз — не публикуется
        st.items, ad.fail = [item(31)], None
        self.clock.t += 60
        run(w.tick(ad))
        self.assertEqual(ad.posts, [])

    def test_rate_limit(self):
        st, ad = FakeStore([item(i) for i in range(40, 60)]), FakeAdapter()
        w = self.worker(st)
        run(w.tick(ad))
        run(w.tick(ad))                         # сразу — пауза MIN_GAP_S, захвата нет
        self.assertEqual((len(ad.posts), st.claims), (1, 1))
        for _ in range(30):
            self.clock.t += O.MIN_GAP_S
            run(w.tick(ad))
        self.assertEqual(len(ad.posts), O.PER_HOUR)
        self.clock.t += 3600
        run(w.tick(ad))
        self.assertEqual(len(ad.posts), O.PER_HOUR + 1)

    def test_delete_only_in_whitelist(self):
        dels = [{"id": 70, "channel": "announcements", "channel_id": 101, "message_id": 5},
                {"id": 71, "channel": "announcements", "channel_id": 105, "message_id": 6},
                {"id": 72, "channel": "updates", "channel_id": 9103, "message_id": 9103},
                {"id": 73, "channel": "updates", "channel_id": 9999, "message_id": 9999},
                {"id": 74, "channel": "general", "channel_id": 105, "message_id": 9}]
        led = O.Ledger(self.path)
        for d in dels:                                   # все — «свои» по журналу; отсекают канал и родитель ветки
            led.put(d["id"], state="posted", ch=d["channel_id"], msg=d["message_id"])
        st, ad = FakeStore([], dels), FakeAdapter(parents={9103: 103, 9999: 105})
        w = self.worker(st, led)
        for _ in dels:
            run(w.tick(ad))
        self.assertEqual(ad.deletes, [(101, 5, False), (9103, 9103, True)])
        self.assertEqual([x[1] for x in st.del_done_log], [True, False, True, False, False])

    def test_delete_only_own_r76(self):
        """★ р76 М-1: подменённые id (запись «опубликовано» с чужими id) — не удаляется; чужой автор / владелец ветки — не удаляется."""
        led = O.Ledger(self.path)
        led.put(80, state="posted", ch=101, msg=500)
        led.put(81, state="posted", ch=101, msg=501)
        led.put(82, state="posted", ch=9103, msg=9103)
        led.put(84, state="refused")
        dels = [{"id": 80, "channel": "announcements", "channel_id": 101, "message_id": 999},     # id сообщения подменён
                {"id": 83, "channel": "announcements", "channel_id": 101, "message_id": 502},     # номера нет в журнале
                {"id": 84, "channel": "announcements", "channel_id": 101, "message_id": 503},     # в журнале — не опубликовано
                {"id": 81, "channel": "announcements", "channel_id": 101, "message_id": 501},     # автор — человек
                {"id": 82, "channel": "updates", "channel_id": 9103, "message_id": 9103}]         # ветку создал человек
        st, ad = FakeStore([], dels), FakeAdapter(parents={9103: 103}, foreign={501, 9103})
        w = self.worker(st, led)
        for _ in dels:
            run(w.tick(ad))
        self.assertEqual(ad.deletes, [])
        self.assertEqual([x[1] for x in st.del_done_log], [False] * 5)
        self.assertIn("не совпадают с журналом", st.del_done_log[0][2])
        self.assertIn("не этот бот", st.del_done_log[3][2])

    def test_lost_ledger_r76(self):
        """★ р76 К1: журнал потерян (номера нет), а попыток уже 2 — не публикуется, «итог неизвестен»."""
        st, ad = FakeStore([item(90, attempts=2)]), FakeAdapter()
        run(self.worker(st).tick(ad))
        self.assertEqual(ad.posts, [])
        self.assertIn("журнал бота не знает эту запись", st.done[0]["error"])

    def test_nonce_and_forum_recovery_r76(self):
        """★ р76 М-2: в адаптер уходит номер записи (nonce); прерванная публикация ветки — найдена своя ветка с тем же именем → «опубликовано»."""
        st, ad = FakeStore([item(91)]), FakeAdapter()
        run(self.worker(st).tick(ad))
        self.assertEqual(ad.oids, [91])
        self.assertEqual(O.nonce_of(91), "astory-ob-91")
        self.assertLessEqual(len(O.nonce_of(2 ** 31 - 1)), 25)
        led = O.Ledger(self.path)
        led.put(92, state="sending")
        st2, ad2 = FakeStore([item(92, channel="updates", attempts=2)]), FakeAdapter(threads=[9555])
        run(self.worker(st2, led).tick(ad2))
        self.assertEqual(ad2.posts, [])
        self.assertEqual((st2.done[0]["ok"], st2.done[0]["ch"], st2.done[0]["msg"]), (True, 9555, 9555))
        led.put(93, state="sending")
        st3, ad3 = FakeStore([item(93, channel="updates", attempts=2)]), FakeAdapter(threads=[1, 2])
        run(self.worker(st3, led).tick(ad3))
        self.assertEqual(ad3.posts, [])
        self.assertFalse(st3.done[0]["ok"])

    def test_forum_recovery_skips_threads_of_other_records_r83(self):
        """★ р83 М-2 (А7.7): прерванная публикация не принимает за свою ветку, которую журнал бота уже записал за другим номером очереди."""
        led = O.Ledger(self.path)
        led.put(95, state="posted", ch=9555, msg=9555)            # прежняя ветка с тем же именем — за записью №95
        led.put(96, state="sending")
        st, ad = FakeStore([item(96, channel="updates", attempts=2)]), FakeAdapter(threads=[9555])
        run(self.worker(st, led).tick(ad))
        self.assertEqual(ad.posts, [])
        self.assertFalse(st.done[0]["ok"])                       # «итог неизвестен», а не «опубликовано» с чужим id
        self.assertIn("итог неизвестен", st.done[0]["error"])
        led.put(97, state="sending")
        st2, ad2 = FakeStore([item(97, channel="updates", attempts=2)]), FakeAdapter(threads=[9555, 9666])
        run(self.worker(st2, led).tick(ad2))
        self.assertEqual((st2.done[0]["ok"], st2.done[0]["msg"]), (True, 9666))   # своя — единственная не чужая

    def test_length_utf16_r76(self):
        """★ р76 К7: длина — в единицах UTF-16 (флаг = 4, эмодзи вне BMP = 2): запас против подсчёта Discord."""
        self.assertEqual(O.dlen("🇬🇧 a"), 6)
        st, ad = FakeStore([item(94, en="😀" * 1000, ru="", ar="")]), FakeAdapter()      # кодовых точек ~1013, UTF-16 — 2013
        run(self.worker(st).tick(ad))
        self.assertEqual(ad.posts, [])
        self.assertIn("длиннее 2000", st.done[0]["error"])


class _Cur:
    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def execute(self, sql, *params):
        self.log.append((sql, params))
        return self

    def fetchall(self):
        return self.rows.pop(0)

    def nextset(self):
        return False

    def close(self):
        pass


class _Cn:
    def __init__(self, log, rows):
        self.log, self.rows, self.closed = log, rows, 0

    def cursor(self):
        return _Cur(self.log, self.rows)

    def close(self):
        self.closed += 1


class TestStore(unittest.TestCase):
    def test_procs(self):
        log = []
        rows = [[(1, "announce", "announcements", "news", "t", "en", None, None, False, NOW, 1, NOW)], [(1,)], [], [(9, "updates", 5, 6)], [(1,)]]
        cn = _Cn(log, rows)
        s = O.Store(connect=lambda: cn)
        got = s.out_claim(1)
        n1 = s.out_nonce
        s.out_done(1, True, channel_id=5, message_id=6)
        s.out_claim(1)
        self.assertEqual(s.out_nonce, n1)          # тот же номер до out_claimed_ok
        s.out_claimed_ok()
        d = s.del_claim(1)
        s.del_done(9, False, "x\ny")
        self.assertEqual(got[0]["channel"], "announcements")
        self.assertEqual(d[0], {"id": 9, "channel": "updates", "channel_id": 5, "message_id": 6})
        self.assertEqual([x[0] for x in log], ["EXEC adm.OutboxClaim ?, ?, ?", "EXEC adm.OutboxDone ?, ?, ?, ?, ?, ?", "EXEC adm.OutboxClaim ?, ?, ?",
                                               "EXEC adm.OutboxDelClaim ?, ?", "EXEC adm.OutboxDelDone ?, ?, ?"])
        self.assertEqual(log[0][1], (1, n1, 0))
        self.assertEqual(log[1][1], (1, 1, 0, "", 5, 6))
        self.assertEqual(log[4][1], (9, 0, "x y"))
        self.assertIsNone(s.out_nonce)
        self.assertEqual(cn.closed, 5)


class TestAdapter(unittest.TestCase):
    """Настоящий DiscordAdapter на подставной гильдии: discord.py — только классы, сети нет."""

    def setUp(self):
        try:
            import discord
        except ImportError:                 # запуск с -I: discord.py стоит в пользовательских пакетах (там же, откуда его берёт бот)
            import site
            sys.path.append(site.getusersitepackages())
            import discord
        self.d = discord
        sent = self.sent = []

        class Ch:
            def __init__(s, cid, name, typ):
                s.id, s.name, s.type = cid, name, typ

            async def send(s, content, **kw):
                sent.append(("send", s.id, content, kw))
                return types.SimpleNamespace(id=555)

            async def create_thread(s, **kw):
                sent.append(("thread", s.id, kw))
                return types.SimpleNamespace(thread=types.SimpleNamespace(id=666), message=types.SimpleNamespace(id=667))

        T = discord.ChannelType
        self.chs = {101: Ch(101, "📣┃announcements", T.news), 103: Ch(103, "updates", T.forum), 104: Ch(104, "📋┃test-info", T.text),
                    108: Ch(108, "voice", T.voice)}
        g = types.SimpleNamespace(channels=list(self.chs.values()), roles=[types.SimpleNamespace(id=201, name="📢 News Ping")],
                                  get_channel=lambda i: self.chs.get(i))
        self.a = O.DiscordAdapter(g)

    def test_kinds_and_mentions(self):
        self.assertEqual(self.a.channels(), [(101, "📣┃announcements", "news"), (103, "updates", "forum"), (104, "📋┃test-info", "text"),
                                             (108, "voice", "other")])
        r = run(self.a.post(101, "news", "T", "<@&201>\nhi", 201, 7))
        self.assertEqual(r, (101, 555))
        am = self.sent[0][3]["allowed_mentions"]
        self.assertIsInstance(am, self.d.AllowedMentions)
        self.assertEqual((am.everyone, am.users, am.replied_user), (False, False, False))
        self.assertEqual([x.id for x in am.roles], [201])
        run(self.a.post(104, "text", "T", "hi", None, 8))
        am2 = self.sent[1][3]["allowed_mentions"]
        self.assertEqual((am2.everyone, am2.users, am2.roles), (False, False, False))
        r = run(self.a.post(103, "forum", "x" * 150, "hi", None, 9))
        self.assertEqual(r, (666, 667))
        self.assertEqual(len(self.sent[2][2]["name"]), O.TITLE_MAX)
        # ★ р76 М-2 / К5: nonce записи у сообщения в канале, без превью ссылок у обоих; у ветки nonce нет (discord.py его не принимает)
        self.assertEqual((self.sent[0][3]["nonce"], self.sent[1][3]["nonce"]), ("astory-ob-7", "astory-ob-8"))
        self.assertTrue(self.sent[0][3]["suppress_embeds"] and self.sent[2][2]["suppress_embeds"])
        self.assertNotIn("nonce", self.sent[2][2])

    def test_nonce_enforced_by_discordpy(self):
        """★ р76 М-2: в discord.py 2.7.1 nonce в запросе идёт вместе с enforce_nonce=True (Discord отбрасывает повтор)."""
        from discord import http
        params = http.handle_message_parameters(content="x", nonce="astory-ob-7")
        self.assertEqual((params.payload["nonce"], params.payload["enforce_nonce"]), ("astory-ob-7", True))

    def test_is_ours_and_threads(self):
        me = 4242
        msgs = {5: me, 6: 1}
        ch = self.chs[101]

        async def fetch_message(mid):
            return types.SimpleNamespace(author=types.SimpleNamespace(id=msgs[mid]))
        ch.fetch_message = fetch_message
        snow = lambda sec_ago: (int((self.d.utils.utcnow().timestamp() - sec_ago) * 1000) - 1420070400000) << 22
        th_own = types.SimpleNamespace(id=snow(10), owner_id=me, name="Patch", parent_id=103)
        th_old = types.SimpleNamespace(id=snow(7200), owner_id=me, name="Patch", parent_id=103)
        th_man = types.SimpleNamespace(id=snow(5), owner_id=1, name="Patch", parent_id=103)
        self.chs[103].threads = [th_own, th_old, th_man]
        th = {th_own.id: th_own, th_man.id: th_man}
        g = self.a.guild
        g.me = types.SimpleNamespace(id=me)
        g.get_channel_or_thread = lambda i: th.get(i) or self.chs.get(i)
        self.assertTrue(run(self.a.is_ours(101, 5, False)))
        self.assertFalse(run(self.a.is_ours(101, 6, False)))
        self.assertTrue(run(self.a.is_ours(th_own.id, th_own.id, True)))
        self.assertFalse(run(self.a.is_ours(th_man.id, th_man.id, True)))
        self.assertFalse(run(self.a.is_ours(th_own.id, 123, True)))         # id сообщения ≠ id ветки
        self.assertEqual(run(self.a.find_threads(103, "Patch", 30)), [th_own.id])

    def test_errors(self):
        resp = types.SimpleNamespace(status=403, reason="Forbidden")
        e = O.DiscordAdapter._err(self.d.Forbidden(resp, "no"))
        self.assertTrue(e.definite)
        e2 = O.DiscordAdapter._err(self.d.HTTPException(types.SimpleNamespace(status=503, reason="x"), "busy"))
        self.assertFalse(e2.definite)
        self.assertFalse(O.DiscordAdapter._err(TimeoutError()).definite)
        with self.assertRaises(O.AdapterError):
            run(self.a.post(999, "text", "T", "hi", None, 10))


class TestRunLogged(unittest.TestCase):
    """★ ревизия 84 М-2: oracle_bot.run_logged — исключение из run() в журнал с трассой без токена и выход с кодом 1 (функции берутся из
    исходника через ast, без импорта oracle_bot и discord)."""

    def test_run_logged(self):
        import ast
        import logging
        with open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_safe_tb", "run_logged")]
        self.assertEqual(len(fns), 2)
        seen = []

        class Log:
            def error(self, msg, *a):
                seen.append(msg % a)

            def info(self, msg, *a):
                seen.append(msg % a)
        ns = {"log": Log(), "logging": logging}
        exec(compile(ast.Module(body=fns, type_ignores=[]), "oracle_bot.py", "exec"), ns)
        secret = "MTAx.fake-token-value-123456"

        class Bot:
            def run(self, token, log_handler=None):
                raise ConnectionError("cannot connect with " + token)
        with self.assertRaises(SystemExit) as cm:
            ns["run_logged"](Bot(), secret)
        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(seen and "ConnectionError" in seen[0] and "Traceback" in seen[0] and secret not in seen[0] and "***" in seen[0])

        class Ok:
            def run(self, token, log_handler=None):
                return None
        ns["run_logged"](Ok(), secret)
        self.assertIn("run вернулся", seen[-1])

    def test_main_uses_run_logged(self):
        with open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("    run_logged(OracleBot(), TOKEN)", src)
        self.assertNotIn("OracleBot().run(TOKEN", src)


class TestSource(unittest.TestCase):
    def test_bot_wiring(self):
        with open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        self.assertIn("self.outbox_loop.start()", ast.get_source_segment(src, fns["setup_hook"]))
        self.assertNotIn("outbox", ast.get_source_segment(src, fns["on_ready"]))
        body = ast.get_source_segment(src, fns["outbox_loop"])
        self.assertIn("await self.outbox.tick(outbox_bot.DiscordAdapter(self.guild_()))", body)
        self.assertNotIn(".send(", body)
        with open(os.path.join(HERE, "outbox_bot.py"), encoding="utf-8") as f:
            osrc = f.read()
        self.assertNotIn("everyone=True", osrc)
        self.assertEqual(osrc.count("allowed_mentions=am"), 2)
        self.assertIn("nonce=nonce_of(oid), suppress_embeds=True", osrc)


if __name__ == "__main__":
    unittest.main(verbosity=1)
