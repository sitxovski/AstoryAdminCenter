#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""test_player_reports.py — модульные тесты жалоб бота (А6.11, 22.11.2026) БЕЗ подключения к Discord и к базе.

Запуск: python -I AstoryAdminCenter/DiscordBot/test_player_reports.py  (код 0 — всё прошло).
Что проверяется: форма (ник, описание, ссылки, категория), сигнатуры картинок (те же, что в adm.ReportFileAdd), проверка вложений до
скачивания, пауза между подачами на подставных часах, текст ответа автору, вызовы процедур Store на подставном соединении (имена процедур,
порядок параметров, коды), разбор файла секрета; по исходнику oracle_bot.py (ast, без импорта — импорт бота пишет в его журнал) — команда
/report зарегистрирована, пределы Discord (заголовок и подписи окна ≤ 45, полей ≤ 5, варианты ≤ 100 знаков), жалоба и цикл ответов ничего
не пишут в каналы (только ephemeral-ответ и личное сообщение автору), цикл ответов запускается в setup_hook.
Связка с настоящими процедурами (LocalDB, adminc_23) — в самотесте панели tests/selftest_reports_a6.py (раздел sandbox).
"""

import ast
import datetime as dt
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import bot_daily as B  # noqa: E402
import player_reports as R  # noqa: E402


class _Cur:
    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def execute(self, sql, *params):
        self.log.append((sql, params))
        return self

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        return self.rows.pop(0)


class _Cn:
    def __init__(self, log, rows):
        self.log, self.rows, self.closed = log, rows, False

    def cursor(self):
        return _Cur(self.log, self.rows)

    def close(self):
        self.closed = True


class FormTests(unittest.TestCase):
    def test_valid(self):
        f, errs = R.validate("  Bob_1 ", "вчера ~21:00", "Он использует бота для фарма на карте", "", "cheat")
        self.assertEqual(errs, [])
        self.assertEqual(f["nick"], "Bob_1")
        self.assertEqual(f["category"], "cheat")

    def test_refusals(self):
        cases = [("", "", "достаточно длинное описание", "", "cheat"), ("x" * 21, "", "достаточно длинное описание", "", "cheat"),
                 ("Bob", "", "коротко", "", "cheat"), ("Bob", "", "достаточно длинное описание", "", "hack"),
                 ("Bob", "", "достаточно длинное описание", "https://evil.example/x.png", "scam"),
                 ("Bob", "", "x" * 1501, "", "other")]
        for c in cases:
            _f, errs = R.validate(*c)
            self.assertTrue(errs, c)
            self.assertTrue(all(len(e) == 2 and e[0] and e[1] for e in errs))
            self.assertTrue(all("; " not in e[0] and "; " not in e[1] for e in errs))

    def test_control_chars(self):
        f, errs = R.validate("Bo\x00b", "\x07now", "строка\x01 с\r\nпереводом строки", "", "abuse")
        self.assertEqual(errs, [])
        self.assertEqual(f["nick"], "Bo b")
        self.assertNotIn("\r", f["body"])
        self.assertIn("\n", f["body"])

    def test_links(self):
        ok = ["https://discord.com/channels/1111111111111111115/1111111111111111101/1111111111111111116",
              "https://cdn.discordapp.com/attachments/1111111111111111101/1111111111111111116/shot.png?ex=1&is=2&hm=ab",
              "https://media.discordapp.net/attachments/1111111111111111101/1111111111111111116/a-b_c.jpg"]
        bad = ["http://discord.com/channels/1/2", "https://discord.com.evil.io/channels/1111111111111111115/1111111111111111101",
               "https://cdn.discordapp.com/attachments/1/2/x.png", "javascript:alert(1)", "https://example.com"]
        g, b = R.parse_links("\n".join(ok + bad))
        self.assertEqual(g, ok)
        self.assertEqual(b, bad)
        f, errs = R.validate("Bob", "", "достаточно длинное описание", "\n".join(ok[:1] * 2), "rmt")
        self.assertEqual(errs, [])
        self.assertEqual(f["links"], ok[0])                     # повтор ссылки — один раз
        _f, errs = R.validate("Bob", "", "достаточно длинное описание",
                              " ".join("https://discord.com/channels/1111111111111111115/1111111111111111101/11111111111111111%02d" % i
                                       for i in range(6)), "rmt")
        self.assertTrue(errs)


class FileTests(unittest.TestCase):
    def test_sniff(self):
        self.assertEqual(R.sniff_image(b"\x89PNG\r\n\x1a\n" + b"0" * 10), "image/png")
        self.assertEqual(R.sniff_image(b"\xff\xd8\xff\xe0abc"), "image/jpeg")
        self.assertEqual(R.sniff_image(b"GIF89a..."), "image/gif")
        self.assertEqual(R.sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertIsNone(R.sniff_image(b"<svg xmlns=...>"))
        self.assertIsNone(R.sniff_image(b""))

    def test_same_signatures_as_sql(self):
        with open(os.path.join(HERE, "..", "sql", "adminc_23_reports.sql"), encoding="utf-8") as fh:   # ★ р67 М-4
            sql = fh.read()
        for hx in ("0x89504E470D0A1A0A", "0xFFD8FF", "0x474946383761", "0x474946383961", "0x52494646", "0x57454250"):
            self.assertIn(hx, sql)
        self.assertIn("@size > 8388608", sql)
        self.assertEqual(R.FILE_MAX, 8388608)
        self.assertIn(">= 3\n        SET @code = 2;", sql)
        self.assertEqual(R.FILES_MAX, 3)

    def test_attachment(self):
        self.assertIsNone(R.check_attachment("image/png", 1000))
        self.assertIsNone(R.check_attachment("image/jpeg; charset=binary", R.FILE_MAX))
        self.assertIsNotNone(R.check_attachment("image/svg+xml", 1000))
        self.assertIsNotNone(R.check_attachment("application/pdf", 1000))
        self.assertIsNotNone(R.check_attachment("image/png", R.FILE_MAX + 1))
        self.assertIsNotNone(R.check_attachment(None, 10))


class CooldownTests(unittest.TestCase):
    def test_clock(self):
        t = [100.0]
        c = R.Cooldown(60, clock=lambda: t[0])
        self.assertEqual(c.left(7), 0)
        c.mark(7)
        self.assertEqual(c.left(7), 60)
        t[0] += 59.5
        self.assertEqual(c.left(7), 1)
        t[0] += 0.6
        self.assertEqual(c.left(7), 0)
        self.assertEqual(c.left(8), 0)


class GateTests(unittest.TestCase):
    """★ ревизия 67 С-1: кто может подать жалобу."""

    def test_may_report(self):
        now = dt.datetime(2026, 1, 20, 12, 0, tzinfo=dt.timezone.utc)
        old = now - dt.timedelta(days=R.MIN_MEMBER_DAYS, seconds=1)
        new = now - dt.timedelta(days=R.MIN_MEMBER_DAYS) + dt.timedelta(seconds=1)
        self.assertIsNone(R.may_report(True, old, now))
        self.assertIsNotNone(R.may_report(True, new, now))
        self.assertIsNotNone(R.may_report(False, old, now))
        self.assertIsNotNone(R.may_report(True, None, now))
        self.assertEqual(R.MIN_MEMBER_DAYS, 7)
        self.assertTrue(all("; " not in x for x in R.JOIN_TEXT))


class DailyTests(unittest.TestCase):
    """★ ревизия 67 Н-3: сводка не чаще раза в 23 ч, старт без отметки — не публикует."""

    def test_decide(self):
        now = dt.datetime(2026, 1, 20, 12, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(B.decide(None, now), (False, now.isoformat()))
        self.assertEqual(B.decide("мусор", now), (False, now.isoformat()))
        self.assertEqual(B.decide((now - dt.timedelta(hours=22, minutes=59)).isoformat(), now), (False, None))
        self.assertEqual(B.decide((now - dt.timedelta(hours=23)).isoformat(), now), (True, None))
        self.assertEqual(B.decide("2026-01-19T10:00:00", now), (True, None))          # без пояса — считается UTC
        # сутки подряд с проверкой раз в час: ровно одна сводка в каждые ~сутки, и ни одной — сразу после старта с отметкой < 23 ч
        last, sent, t = (now - dt.timedelta(hours=19)).isoformat(), [], now
        for _ in range(72):
            go, mark = B.decide(last, t)
            if go:
                sent.append(t)
                last = t.isoformat()
            t += dt.timedelta(minutes=B.CHECK_MINUTES)
        self.assertEqual(len(sent), 3)
        self.assertEqual(sent[0], now + dt.timedelta(hours=4))
        self.assertTrue(all(b - a == dt.timedelta(hours=23) for a, b in zip(sent, sent[1:])))


class TextTests(unittest.TestCase):
    def test_reply(self):
        m = R.reply_message(12, "scam", "Bob", "Спасибо, меры приняты.")
        self.assertIn("#12", m)
        self.assertIn("№12", m)
        self.assertIn("Спасибо, меры приняты.", m)
        self.assertLessEqual(len(R.reply_message(1, "other", "B", "x" * 5000)), 2000)

    def test_codes(self):
        self.assertEqual(sorted(R.SUBMIT_TEXT), [1, 2, 3, 4])
        self.assertEqual(sorted(R.FILE_TEXT), [1, 2, 3, 4, 5, 6])
        self.assertIn("7", R.both(R.SUBMIT_TEXT[3], id=7))

    def test_secret(self):
        self.assertEqual(R._parse_secret("# x\nREPORTS_PASSWORD = Ab1-xyz \n"), "Ab1-xyz")
        with self.assertRaises(RuntimeError):
            R._parse_secret("PASSWORD = x")


class StoreTests(unittest.TestCase):
    def test_calls(self):
        log, rows = [], [(0, 41), (3,), [(5, 41, 123456789012345678, "ответ", "Bob", "cheat")], (1,)]
        cns = []

        def mk():
            cns.append(_Cn(log, rows))
            return cns[-1]
        s = R.Store(connect=mk)
        f, _e = R.validate("Bob", "", "достаточно длинное описание", "", "cheat")
        self.assertEqual(s.submit(123456789012345678, "user#1", f), (0, 41))
        self.assertEqual(s.add_file(41, 123456789012345678, "a.png", b"\x89PNG\r\n\x1a\n"), 3)
        got = s.claim()
        self.assertEqual(got[0]["reporter_id"], 123456789012345678)
        self.assertEqual(s.done(5, False, "закрыты\x00"), 1)
        self.assertTrue(all(c.closed for c in cns))
        sqls = [x[0] for x in log]
        self.assertIn("EXEC adm.ReportSubmit ?, ?, ?, ?, ?, ?, ?, @id OUTPUT, @code OUTPUT", sqls[0])
        self.assertEqual(log[0][1][:4], (123456789012345678, "user#1", "Bob", "cheat"))
        self.assertIn("EXEC adm.ReportFileAdd ?, ?, ?, ?, @code OUTPUT", sqls[1])
        self.assertEqual(sqls[2], "EXEC adm.ReportReplyClaim ?, ?")
        self.assertEqual(log[2][1][0], R.REPLIES_PER_TICK)
        self.assertRegex(log[2][1][1], r"^[0-9a-f-]{36}$")
        self.assertEqual(log[3][1], (5, 0, "закрыты"))
        self.assertTrue(all(not re.search(r"\b(INSERT|UPDATE|DELETE|SELECT \*)\b", q) for q in sqls))


class BotSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8").read()
        cls.tree = ast.parse(cls.src)

    def _cls(self, name):
        return next(n for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef) and n.name == name)

    def test_modal_limits(self):
        m = self._cls("ReportModal")
        title = next(k.value.value for k in m.keywords if k.arg == "title")
        self.assertLessEqual(len(title), 45)
        fields = [n for n in m.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                  and getattr(n.value.func, "attr", "") == "TextInput"]
        self.assertLessEqual(len(fields), 5)
        for f in fields:
            kw = {k.arg: k.value for k in f.value.keywords}
            self.assertLessEqual(len(kw["label"].value), 45)
            if "placeholder" in kw:
                self.assertLessEqual(len(kw["placeholder"].value), 100)

    def test_choices(self):
        for k, (en, ru) in R.CATEGORIES.items():
            self.assertLessEqual(len("%s / %s" % (en, ru)), 100)

    def test_daily_and_claim(self):
        self.assertIn("@tasks.loop(minutes=bot_daily.CHECK_MINUTES)", self.src)
        self.assertNotIn("@tasks.loop(hours=24)", self.src)
        self.assertIn('self.state.data["daily_last_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()', self.src)
        loop = self.src[self.src.index("async def report_reply_loop"):self.src.index("@report_reply_loop.before_loop")]
        self.assertNotIn("asyncio.wait_for(", loop)
        self.assertIn("self.reports.claimed_ok()", loop)
        cmd = self.src[self.src.index('@bot.tree.command(name="report"'):self.src.index("def warns_of")]
        self.assertIn("player_reports.may_report(", cmd)
        self.assertLess(cmd.index("may_report("), cmd.index("send_modal("))

    def test_no_ssh(self):
        with open(os.path.join(HERE, "player_reports.py"), encoding="utf-8") as fh:
            src = fh.read()
        code = src.split('"""', 2)[2]
        for tok in ("ssh.exe", "@@ASTORY_SSH_KEY_NAME@@", "Administrator@", "subprocess", '"ssh"'):
            self.assertNotIn(tok, code)
        self.assertTrue(R.SECRET_PATH.endswith("reports.env"))

    def test_registered(self):
        self.assertIn('@bot.tree.command(name="report"', self.src)
        self.assertIn("send_modal(ReportModal(bot, category.value, files))", self.src)
        self.assertIn("self.report_reply_loop.start()", self.src)
        self.assertIn("@report_reply_loop.before_loop", self.src)

    def test_no_channel_posts(self):
        m = ast.get_source_segment(self.src, self._cls("ReportModal"))
        loop = self.src[self.src.index("async def report_reply_loop"):self.src.index("@report_reply_loop.before_loop")]
        cmd = self.src[self.src.index('@bot.tree.command(name="report"'):self.src.index("def warns_of")]
        for part in (m, loop, cmd):
            self.assertNotIn(".channel(", part)
            self.assertNotIn("staff", part)
        fn = next(n for n in ast.walk(self.tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "report")
        sends = [c for node in (self._cls("ReportModal"), fn) for c in ast.walk(node) if isinstance(c, ast.Call)
                 and getattr(c.func, "attr", "") in ("send_message", "send")]
        self.assertTrue(sends)
        self.assertTrue(all(any(k.arg == "ephemeral" and getattr(k.value, "value", None) is True for k in c.keywords) for c in sends),
                        [ast.get_source_segment(self.src, c)[:80] for c in sends])
        self.assertIn("await user.send(", loop)
        self.assertIn("AllowedMentions.none()", loop)


if __name__ == "__main__":
    unittest.main(verbosity=1)
