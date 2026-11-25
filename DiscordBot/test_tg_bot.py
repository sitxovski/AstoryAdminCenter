#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""test_tg_bot.py — модульные тесты отправителя Telegram (А7.5, 23.11.2026) БЕЗ сети, без Telegram и без базы.

Запуск: python -I AstoryAdminCenter/DiscordBot/test_tg_bot.py  (код 0 — всё прошло).
Telegram подменён: TgApi — подставным HTTP (запоминает запросы, отвечает как Bot API), Worker — подставным Store (без базы). Что проверяется:
только методы sendMessage и getMe (по запросам и по тексту модуля — других имён методов Bot API в нём нет), чат — только личный (положительный)
и только из секрета, токен не попадает в ошибки, сообщение один раз по номеру записи (журнал: отправлено — не повторяется, прервано — «итог
неизвестен», точный отказ — повтор, тайм-аут — без повтора), срок годности по часам SQL, проверочные записи (check — только getMe, selftest —
без Telegram), тихие часы — без звука, но сразу, предел частоты, «служба панели не отвечает» и «база недоступна» — одно сообщение на случай и
одно «снова», выключатели не прочитаны — молчит; по исходнику oracle_bot.py (ast) — цикл запускается в setup_hook, его тело — только tg.tick.
Связка с настоящими процедурами (LocalDB, adminc_29) — в самотесте панели tests/selftest_telegram_a7.py.
"""

import ast
import asyncio
import datetime as dt
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import tg_bot as G  # noqa: E402

NOW = dt.datetime(2026, 11, 23, 12, 0, 0)
TOKEN = "123456789:" + "A" * 35            # подставной: настоящий токен в тестах не нужен и не читается


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeHttp:
    """Подставной Bot API: open(req, timeout) → ответ; mode — ok | http400 | refused | timeout."""

    def __init__(self, mode="ok"):
        self.mode, self.reqs, self.mid = mode, [], 700

    def open(self, req, timeout=None):
        method = req.full_url.rsplit("/", 1)[1]
        body = json.loads(req.data.decode("utf-8"))
        self.reqs.append((method, body, req.full_url))
        if self.mode == "refused":
            raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        if self.mode == "timeout":
            raise urllib.error.URLError(socket.timeout("timed out"))
        if self.mode == "http400":
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(json.dumps(
                {"ok": False, "description": "Bad Request: chat not found " + TOKEN}).encode()))
        if method == "getMe":
            return _Resp(json.dumps({"ok": True, "result": {"id": 1, "is_bot": True, "username": "@@ASTORY_TELEGRAM_BOT@@"}}).encode())
        self.mid += 1
        return _Resp(json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode())


class FakeStore:
    def __init__(self, items=None, beat=None):
        self.items, self.done, self.claims, self.locals = list(items or []), [], 0, []
        self.beat_v, self.beat_err = beat if beat is not None else {"beat_utc": NOW, "age_s": 30, "master": True, "panel_down": True, "now_utc": NOW}, None

    def tg_claim(self, n=1, test_only=False):
        self.claims += 1
        out, self.items = self.items[:n], self.items[n:]
        return out

    def tg_claimed_ok(self):
        pass

    def tg_done(self, oid, ok, error="", expired=False, retry=False, message_id=None):
        self.done.append(dict(id=oid, ok=ok, error=error, expired=expired, retry=retry, msg=message_id))
        return 1

    def tg_beat(self):
        if self.beat_err:
            raise self.beat_err
        return self.beat_v

    def tg_local(self, kind, text, ok, message_id=None, error=""):
        if self.beat_err:
            raise self.beat_err
        self.locals.append((kind, text, ok, message_id))


def item(oid=1, **kw):
    it = {"id": oid, "kind": "notify", "title": "EacServer не работает", "text": "AsdaEacServer не запущен", "test": False, "quiet": False,
          "event": "eac_down", "repeats": 0, "expires_utc": NOW + dt.timedelta(hours=1), "attempts": 1, "now_utc": NOW}
    it.update(kw)
    return it


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.http = FakeHttp()
        self.api = G.TgApi(TOKEN, 5000, proxy="", opener=self.http)

    def tearDown(self):
        self.tmp.cleanup()

    def worker(self, store, hour=12, per_hour=100):
        led = G.Ledger(os.path.join(self.tmp.name, "led.json"))
        return G.Worker(store, api=self.api, ledger=led, limiter=G.Limiter(per_hour=per_hour), clock=lambda: dt.datetime(2026, 11, 23, hour, 0))

    def run_(self, w):
        asyncio.run(w.tick())

    def sends(self):
        return [r for r in self.http.reqs if r[0] == "sendMessage"]

    def test_only_two_methods_in_source(self):
        with open(os.path.join(HERE, "tg_bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(G.METHODS, ("sendMessage", "getMe"))
        bad = [w for w in ("get" + "Updates", "set" + "Webhook", "delete" + "Webhook", "log" + "Out", "set" + "MyCommands", "close(")
               if w in src and w != "close("]
        self.assertEqual(bad, [])
        names = set(re.findall(r'"([a-z][A-Za-z]+)"', src)) & {"sendMessage", "getMe", "getUpdates", "setWebhook", "deleteWebhook", "getWebhookInfo",
                                                                "editMessageText", "deleteMessage", "forwardMessage", "sendPhoto"}
        self.assertEqual(names, {"sendMessage", "getMe"})
        with self.assertRaises(G.TgError):
            self.api.call("get" + "Updates", {})
        self.assertEqual(self.http.reqs, [])

    def test_private_chat_only(self):
        with self.assertRaises(ValueError):
            G.TgApi(TOKEN, -100123, opener=self.http)
        p = os.path.join(self.tmp.name, "telegram.env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("TG_TOKEN = %s\nTG_CHAT = -5\n" % TOKEN)
        with self.assertRaises(ValueError):
            G.read_secret(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write("# x\nTG_TOKEN = %s\nTG_CHAT = 42\n" % TOKEN)
        self.assertEqual(G.read_secret(p), (TOKEN, 42))

    def test_send_once_and_chat(self):
        s = FakeStore([item(1)])
        w = self.worker(s)
        self.run_(w)
        self.assertEqual(len(self.sends()), 1)
        m, body, url = self.sends()[0]
        self.assertEqual(body["chat_id"], 5000)
        self.assertTrue(body["text"].startswith("Astory · EacServer не работает\nAsdaEacServer"))
        self.assertFalse(body["disable_notification"])
        self.assertEqual(s.done[-1]["ok"], True)
        self.assertEqual(s.done[-1]["msg"], 701)
        s.items = [item(1, attempts=2)]                 # тот же номер ещё раз (сбой отметки) — не отправляется второй раз
        self.run_(w)
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(s.done[-1]["msg"], 701)

    def test_interrupted_and_lost_ledger(self):
        s = FakeStore([item(2)])
        w = self.worker(s)
        w.ledger.put(2, state="sending")
        self.run_(w)
        self.assertEqual(self.sends(), [])
        self.assertIn("итог неизвестен", s.done[-1]["error"])
        s.items = [item(3, attempts=2)]
        self.run_(w)
        self.assertEqual(self.sends(), [])
        self.assertIn("журнал отправителя не знает", s.done[-1]["error"])

    def test_definite_failure_retries_timeout_does_not(self):
        self.http.mode = "http400"
        s = FakeStore([item(4)])
        w = self.worker(s)
        self.run_(w)
        d = s.done[-1]
        self.assertFalse(d["ok"])
        self.assertTrue(d["retry"])
        self.assertNotIn(TOKEN, d["error"])
        self.assertIn("<token>", d["error"])
        self.http.mode = "ok"
        s.items = [item(4, attempts=2)]                 # точный отказ — повтор отправляет
        self.run_(w)
        self.assertTrue(s.done[-1]["ok"])
        self.http.mode = "timeout"
        s.items = [item(5)]
        self.run_(w)
        self.assertFalse(s.done[-1]["retry"])
        self.assertIn("итог неизвестен", s.done[-1]["error"])
        self.http.mode = "refused"
        s.items = [item(6)]
        self.run_(w)
        self.assertTrue(s.done[-1]["retry"])

    def test_expired(self):
        s = FakeStore([item(7, expires_utc=NOW - dt.timedelta(seconds=1))])
        w = self.worker(s)
        self.run_(w)
        self.assertEqual(self.sends(), [])
        self.assertTrue(s.done[-1]["expired"])

    def test_test_records(self):
        s = FakeStore([item(8, kind="test", test=True, title="check"), item(9, kind="test", test=True, title="selftest")])
        w = self.worker(s)
        self.run_(w)
        self.run_(w)
        self.assertEqual([r[0] for r in self.http.reqs], ["getMe"])
        self.assertTrue(s.done[0]["ok"] and "@@@ASTORY_TELEGRAM_BOT@@" in s.done[0]["error"])
        self.assertTrue(s.done[1]["ok"] and "не вызывался" in s.done[1]["error"])

    def test_quiet_hours_silent_not_delayed(self):
        s = FakeStore([item(10, quiet=True), item(11, quiet=False)])
        w = self.worker(s, hour=2)
        self.run_(w)
        self.run_(w)
        self.assertEqual([r[1]["disable_notification"] for r in self.sends()], [True, False])
        s.items = [item(12, quiet=True)]
        w2 = self.worker(s, hour=14)
        w2._ledger = w.ledger
        self.run_(w2)
        self.assertFalse(self.sends()[-1][1]["disable_notification"])

    def test_ping_and_repeats(self):
        s = FakeStore([item(13, kind="ping", title="ping", text="Astory: проверочное сообщение"), item(14, repeats=3)])
        w = self.worker(s)
        self.run_(w)
        self.run_(w)
        t = [r[1]["text"] for r in self.sends()]
        self.assertEqual(t[0], "Astory: проверочное сообщение")
        self.assertTrue(t[1].endswith("(повторов до отправки: 3)"))

    def test_rate_limit(self):
        s = FakeStore([item(i) for i in range(20, 25)])
        w = self.worker(s, per_hour=2)
        for _ in range(5):
            self.run_(w)
        self.assertEqual(len(self.sends()), 2)
        self.assertEqual(s.claims, 2)

    def test_panel_down_once_and_back(self):
        s = FakeStore(beat={"beat_utc": NOW, "age_s": 20 * 60, "master": True, "panel_down": True, "now_utc": NOW})
        w = self.worker(s)
        self.run_(w)
        self.run_(w)
        self.assertEqual(len(self.sends()), 1)
        self.assertIn("служба админ-центра не отмечалась 20 мин", self.sends()[0][1]["text"])
        s.beat_v = dict(s.beat_v, age_s=30)
        self.run_(w)
        self.assertEqual(len(self.sends()), 2)
        self.assertIn("снова отмечается", self.sends()[1][1]["text"])

    def test_panel_down_respects_switches(self):
        s = FakeStore(beat={"beat_utc": NOW, "age_s": 99 * 60, "master": False, "panel_down": True, "now_utc": NOW})
        w = self.worker(s)
        self.run_(w)
        s.beat_v = dict(s.beat_v, master=True, panel_down=False)
        self.run_(w)
        self.assertEqual(self.sends(), [])

    def ticks(self, w, t, n):
        for _ in range(n):
            t[0] += G.TICK_S
            self.run_(w)

    def test_db_down_needs_known_switches(self):
        t = [1000.0]
        s = FakeStore()
        s.beat_err = RuntimeError("08S01", "link failure")
        w = self.worker(s)
        w.mono = lambda: t[0]
        self.ticks(w, t, G.DB_DOWN_MIN * 60 // G.TICK_S + 3)
        self.assertEqual(self.sends(), [])          # выключатели ни разу не прочитаны — молчит
        s.beat_err = None
        self.ticks(w, t, 1)                         # прочитаны: общий и «служба не отвечает» включены
        s.beat_err = RuntimeError("08S01", "link failure")
        self.ticks(w, t, G.DB_DOWN_MIN * 60 // G.TICK_S + 3)
        self.assertEqual(len(self.sends()), 1)
        self.assertIn("база AsdaAdmin недоступна", self.sends()[0][1]["text"])
        self.assertEqual(s.locals, [])              # база лежит — на экран запишется потом
        s.beat_err = None
        self.ticks(w, t, 1)
        self.assertIn("снова отвечает", self.sends()[-1][1]["text"])
        self.assertEqual([x[0] for x in s.locals], ["db", "db_up"])     # р77 К-3: оба — строками для экрана, по порядку

    def test_r77_sleep_gap_restarts_count(self):
        t = [1000.0]
        s = FakeStore()
        w = self.worker(s)
        w.mono = lambda: t[0]
        self.ticks(w, t, 1)
        s.beat_err = RuntimeError("08001", "unreachable")
        self.ticks(w, t, 2)
        t[0] += 8 * 3600                            # сон ПК 8 ч: monotonic мог учесть сон
        self.ticks(w, t, 1)
        self.assertEqual(self.sends(), [])          # р77 К-7: разрыв — счёт заново, ложной «недоступна > 15 мин» нет
        self.assertEqual(w.db_fails, 1)

    def test_r78_config_error_own_text(self):
        t = [1000.0]
        s = FakeStore()
        w = self.worker(s)
        w.mono = lambda: t[0]
        self.ticks(w, t, 1)
        s.beat_err = RuntimeError("42000", "[42000] The EXECUTE permission was denied on the object 'TgBeatGet'. (229) (SQLExecDirectW)")
        self.ticks(w, t, 5)
        self.assertEqual(self.sends(), [])          # меньше 15 мин — молчит
        self.assertTrue(w.cfg_said)
        self.ticks(w, t, G.DB_DOWN_MIN * 60 // G.TICK_S)
        self.assertEqual(len(self.sends()), 1)      # р78 М-1: настройка — тоже сообщение через 15 мин, со своим текстом
        self.assertIn("нет процедуры или прав", self.sends()[0][1]["text"])

    def test_r78_db_offline_4060_is_down(self):
        t = [1000.0]
        s = FakeStore()
        w = self.worker(s)
        w.mono = lambda: t[0]
        self.ticks(w, t, 1)
        s.beat_err = RuntimeError("42000", "[42000] Cannot open database \"AsdaAdmin\" requested by the login. The login failed. (4060) (SQLDriverConnect)")
        self.assertFalse(G.db_config_error(s.beat_err))
        self.ticks(w, t, G.DB_DOWN_MIN * 60 // G.TICK_S + 2)
        self.assertEqual(len(self.sends()), 1)      # р78 М-1: база выключена (4060) — «база недоступна», а не молчание
        self.assertIn("база AsdaAdmin недоступна", self.sends()[0][1]["text"])

    def test_r78_slow_calls_still_alert_at_15_min(self):
        t = [1000.0]
        s = FakeStore()

        class Slow(FakeStore):
            def tg_beat(self_):
                t[0] += 25                          # вызов при недоступной базе висит 25 с (тайм-аут входа)
                raise RuntimeError("08001", "timeout (0)")

            def tg_claim(self_, n=1, test_only=False):
                t[0] += 15
                raise RuntimeError("08001", "timeout")
        w = self.worker(s)
        w.mono = lambda: t[0]
        self.ticks(w, t, 1)                         # выключатели прочитаны
        w.store = Slow()
        start = t[0]
        while not self.sends() and t[0] - start < 40 * 60:
            t[0] += G.TICK_S
            self.run_(w)
        self.assertEqual(len(self.sends()), 1)      # р78 К-5: долгие вызовы не сбрасывают счёт
        self.assertLessEqual(t[0] - start, (G.DB_DOWN_MIN + 2) * 60)   # и приходит около 15 мин, а не 22

    def test_r77_http_exception_unknown(self):
        import http.client

        class H(FakeHttp):
            def open(self, req, timeout=None):
                self.reqs.append(("sendMessage", json.loads(req.data.decode("utf-8")), req.full_url))
                raise http.client.IncompleteRead(b"")
        self.http = H()
        self.api = G.TgApi(TOKEN, 5000, proxy="", opener=self.http)
        s = FakeStore([item(40)])
        w = self.worker(s)
        self.run_(w)
        self.assertFalse(s.done[-1]["retry"])       # р77 К-5: ответ оборван — итог неизвестен, без повтора
        self.assertIn("итог неизвестен", s.done[-1]["error"])

    def test_r77_tails_from_columns(self):
        s = FakeStore([item(41, supp_n=2, over_n=3, repeats=1)])
        w = self.worker(s)
        self.run_(w)
        t = self.sends()[0][1]["text"]
        self.assertTrue(t.endswith("(ещё повторов этого события за паузу: 2)\n(уведомлений не поставлено из-за предела частоты: 3)\n"
                                   "(повторов до отправки: 1)"), t)

    def test_no_secret_silent(self):
        s = FakeStore([item(30)])
        w = G.Worker(s, ledger=G.Ledger(os.path.join(self.tmp.name, "l2.json")), secret=os.path.join(self.tmp.name, "nope.env"))
        asyncio.run(w.tick())
        asyncio.run(w.tick())
        self.assertEqual(s.claims, 0)
        self.assertEqual(s.done, [])

    def test_mask(self):
        self.assertNotIn(TOKEN, G.mask("x https://api.telegram.org/bot%s/sendMessage" % TOKEN))
        self.assertNotIn(TOKEN, G.mask("x %s" % TOKEN, TOKEN))

    def test_oracle_loop(self):
        with open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OracleBot"][0]
        fns = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn("self.tg_loop.start()", ast.unparse(fns["setup_hook"]))
        body = ast.unparse(fns["tg_loop"])
        self.assertIn("await self.tg.tick()", body)
        self.assertNotIn("wait_until_ready", body)
        self.assertNotIn("_tg_wait", fns)
        self.assertIn("tg_bot.Worker(tg_bot.Store(), log=log.info, proxy=PROXY)", ast.unparse(fns["__init__"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
