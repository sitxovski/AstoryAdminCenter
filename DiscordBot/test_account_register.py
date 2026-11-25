#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""test_account_register.py — модульные тесты регистрации учётки из бота (/register, 25.11.2026) БЕЗ подключения к Discord и к базе.

Запуск: python -I AstoryAdminCenter/DiscordBot/test_account_register.py  (код 0 — всё прошло).
Что проверяется: правила логина и пароля, формула хеша (= панель domains/password.py = FN_AC_PwHash), разбор файла учёток (есть / забанен /
нет; чужая строка не подходит), строка новой учётки читается обратно тем же разбором, что у /password в oracle_bot.py, запись в файл только
добавлением, вызов процедуры на подставном соединении (имя, порядок параметров, коды), текст ответа со ссылкой на установщик; по исходнику
oracle_bot.py (ast, без импорта — импорт бота пишет в его журнал) — команды /register и /password зарегистрированы, /register отвечает только
ephemeral и не пишет пароль в журнал; SQL-скрипт adminc_32 — права бота и значения строки Us_member.
Живая связка с настоящей процедурой — test_account_register.py --live (dev-база по VPN; пробная учётка создаётся и НЕ удаляется ботом — её
убирает вызывающий под администратором сервера).
"""

import ast
import hashlib
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import account_register as A  # noqa: E402

SQL = os.path.join(HERE, "..", "sql", "adminc_32_botreg.sql")                 # ★ 25.11 (С-6): AstoryAdminCenter/sql


class _Cur:
    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def execute(self, sql, *params):
        self.log.append((sql, params))
        return self

    def fetchone(self):
        return self.rows.pop(0)


class _Cn:
    def __init__(self, log, rows):
        self.log, self.rows, self.closed = log, rows, False

    def cursor(self):
        return _Cur(self.log, self.rows)

    def close(self):
        self.closed = True


def _oracle_src():
    with open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8") as f:
        return f.read()


def _func(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError("нет функции %s" % name)


class Rules(unittest.TestCase):
    def test_good(self):
        self.assertEqual(A.validate("Hero_01", "s3cret!x"), ("Hero_01", "s3cret!x", []))
        self.assertEqual(A.validate("a.b@c-d", "x" * 50)[2], [])
        self.assertEqual(A.validate("abc", "123456")[2], [])

    def test_login_bad(self):
        for lg in ("", "ab", "x" * 33, "имя", "a b", "a/b", "a'b", "abc\n", "a;b", "a`b"):
            self.assertEqual(len(A.validate(lg, "s3cret!x")[2]), 1, lg)

    def test_password_bad(self):
        for pw in ("", "12345", "x" * 51, "пароль1", "ab cdef", " abcdef", "abcdef\n", "abc`def", "abc\tdef"):
            self.assertEqual(len(A.validate("Hero_01", pw)[2]), 1, repr(pw))
        self.assertEqual(len(A.validate("Hero_01", "hero_01")[2]), 1)       # пароль = логин

    def test_hash_formula(self):
        self.assertEqual(A.md5hex("123123"), "4297f44b13955235245b2497399d7a93")
        salt = bytes(range(16))
        self.assertEqual(A.pw_hash(salt, "ABCDEF"), hashlib.sha256(salt + b"abcdef").digest())
        s, h = A.make_secret("123123", salt)
        self.assertEqual((s, h), (salt, hashlib.sha256(salt + b"4297f44b13955235245b2497399d7a93").digest()))
        s2, h2 = A.make_secret("123123")
        self.assertEqual((len(s2), len(h2)), (16, 32))
        self.assertNotEqual(s2, A.make_secret("123123")[0])                 # соль случайная

    def test_same_as_panel(self):
        """Формулы совпадают с панелью (domains/password.py md5hex / pw_hash) — по её исходнику."""
        with open(os.path.join(HERE, "..", "domains", "password.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('hashlib.md5(s.encode("ascii")).hexdigest()', src)
        self.assertIn('hashlib.sha256(bytes(salt) + hexs.lower().encode("ascii")).digest()', src)


FILE = """# Тестовые аккаунты
Hades (@Player5) [111111111111111105]   - hades1/pw-One
# BANNED 2026-10-27 Player57 (@Player6.) [111111111111111106]   - anas/pw2
old (@nouid)   - nouid/pw3
# заметка про [555]
"""


class Accounts(unittest.TestCase):
    def test_status(self):
        self.assertEqual(A.file_status(FILE, 111111111111111105), ("have", ("hades1", "pw-One")))
        self.assertEqual(A.file_status(FILE, 111111111111111106), ("banned", None))
        self.assertEqual(A.file_status(FILE, 555), (None, None))             # комментарий без BANNED — не бан и не учётка
        self.assertEqual(A.file_status(FILE, 11111111111111110), (None, None))   # часть чужого ID не подходит
        self.assertEqual(A.file_status("", 1), (None, None))

    def test_line_roundtrip_with_bot_regex(self):
        """Новая строка читается разбором /password (регулярное выражение взято из исходника oracle_bot.py)."""
        m = re.search(r'_ACCOUNT_LINE = re\.compile\(\s*r"(.+?)"\)', _oracle_src(), re.S)
        rx = re.compile(m.group(1))
        self.assertEqual(rx.pattern, A._LINE.pattern)
        for pw in ("s3cret!x", "a/b-c)d(e", "[1]-x/y@z", "######"):
            line = A.account_line("some.user_1", 123456789012345678, "Hero_01", pw)
            g = rx.search(line)
            self.assertEqual((g["handle"], g["uid"], g["login"], g["pw"]), ("some.user_1", "123456789012345678", "Hero_01", pw))
            self.assertFalse(line.lstrip().startswith("#"))

    def test_handle_sanitized(self):
        line = A.account_line("x) [1] - a/b (@evil", 42, "Hero_01", "s3cret!x")
        self.assertTrue(line.startswith("x1-abevil (@x1-abevil) [42]".replace("-", "")), line)
        self.assertEqual(A.file_status(line, 42), ("have", ("Hero_01", "s3cret!x")))
        self.assertEqual(A.file_status(line, 1), (None, None))
        self.assertIn("(@user)", A.account_line("!!!", 42, "Hero_01", "s3cret!x"))

    def test_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "acc.txt")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write("# head\nold (@old) [1]   - old/pw")                 # без перевода строки в конце
            A.append_account(p, "new", 2, "newlogin", "s3cret!x")
            A.append_account(p, "third", 3, "third", "abc#def")
            with open(p, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith("# head\nold (@old) [1]   - old/pw\n"))
            self.assertEqual(A.file_status(text, 1), ("have", ("old", "pw")))
            self.assertEqual(A.file_status(text, 2), ("have", ("newlogin", "s3cret!x")))
            self.assertEqual(A.file_status(text, 3), ("have", ("third", "abc#def")))
            self.assertEqual(text.count("\n"), 4)
            q = os.path.join(d, "none.txt")                                  # файла нет — создаётся
            A.append_account(q, "new", 2, "newlogin", "s3cret!x")
            with open(q, encoding="utf-8") as f:
                self.assertEqual(A.file_status(f.read(), 2)[0], "have")


class StoreCalls(unittest.TestCase):
    def test_register(self):
        log, cn = [], None

        def connect():
            nonlocal cn
            cn = _Cn(log, [(0, 75300, "Hero_01")])
            return cn
        st = A.Store(connect=connect)
        salt, h = A.make_secret("s3cret!x")
        self.assertEqual(st.register(42, "n" * 80, "Hero_01", salt, h), (0, 75300, "Hero_01"))
        sql, params = log[0]
        self.assertIn("EXEC adm.BotAccountRegister ?, ?, ?, ?, ?, @code OUTPUT, @uid OUTPUT, @login OUTPUT", sql)
        self.assertEqual(params, (42, "n" * 64, "Hero_01", salt, h))
        self.assertNotIn("s3cret!x", repr(log))                             # открытый пароль в базу не уходит
        self.assertTrue(cn.closed)

    def test_codes(self):
        st = A.Store(connect=lambda: _Cn([], [(2, None, None)]))
        self.assertEqual(st.register(1, "x", "abc", b"\0" * 16, b"\0" * 32), (2, None, None))
        for code in (1, 2, 3):
            self.assertIn(code, A.REGISTER_TEXT)
            self.assertIn("/", A.both(A.REGISTER_TEXT[code], login="abc"))

    def test_message(self):
        m = A.success_message("Hero_01", "s3cret!x")
        self.assertIn("https://discord.com/channels/@@ASTORY_DISCORD_GUILD@@/@@ASTORY_DISCORD_INSTALLER_CH@@/@@ASTORY_DISCORD_INSTALLER_MSG@@", m)
        self.assertIn("`Hero_01`", m)
        self.assertIn("`s3cret!x`", m)
        self.assertIn("/password", m)
        self.assertIn("Save the password now", A.success_message("Hero_01", "s3cret!x", saved=False))
        self.assertLess(len(A.success_message("x" * 32, "y" * 50)), 2000)


class BotSource(unittest.TestCase):
    def setUp(self):
        self.src = _oracle_src()
        self.tree = ast.parse(self.src)

    def test_commands(self):
        self.assertIn('@bot.tree.command(name="register"', self.src)
        self.assertIn('@bot.tree.command(name="password"', self.src)
        f = _func(self.tree, "register")
        self.assertEqual([a.arg for a in f.args.args], ["itx", "login", "password"])
        for d in re.findall(r'description="([^"]+)"', self.src) + re.findall(r'(?:login|password)="([^"]+)"', self.src):
            self.assertLessEqual(len(d), 100, d)                             # предел Discord на описания

    def test_register_private(self):
        f = _func(self.tree, "register")
        body = ast.get_source_segment(self.src, f)
        self.assertIn("defer(ephemeral=True", body)
        self.assertEqual(body.count("followup.send("), body.count("ephemeral=True)"))
        self.assertNotIn(".channel", body)
        for call in ast.walk(f):                                             # в журнал — ни пароль, ни хеш
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) \
                    and call.func.value.id == "log":
                names = {n.id for a in call.args for n in ast.walk(a) if isinstance(n, ast.Name)}
                self.assertFalse(names & {"pw", "password", "pwhash", "salt"}, ast.get_source_segment(self.src, call))

    def test_sql(self):
        with open(SQL, encoding="utf-8") as f:
            s = f.read()
        self.assertIn("VALUES (@Us_id, 0, GETDATE(), 0, 0, 0, 0, 0, 3, -1, 0, @Salt, @Hash, GETDATE());", s)   # = UP_AC_CreateAccount / adm_NewAccount
        self.assertNotIn("IDENTITY_INSERT", s.split("CREATE PROCEDURE", 1)[1])   # номер — только счётчик, служебный не задать
        self.assertIn("GRANT EXECUTE ON adm.BotAccountRegister TO [asda_reports];", s)
        self.assertIn("DENY  SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::dbo TO [asda_reports];", s)
        self.assertEqual(s.count("GRANT "), 1)
        self.assertIn("LIKE '%%[^A-Za-z0-9_.@-]%%'" % (), s)
        self.assertIn("LEN(@Us_id) < %d OR DATALENGTH(@Us_id) > %d" % (A.LOGIN_MIN, A.LOGIN_MAX), s)


def live():
    """Живая dev-база под логином бота: права (adminc_32_botreg_verify.sql), создание пробной учётки, повтор, занятый логин."""
    import pyodbc  # noqa: F401
    st = A.Store()
    cn = st._cn()
    with open(os.path.join(os.path.dirname(SQL), "adminc_32_botreg_verify.sql"), encoding="utf-8") as f:
        rows = [tuple(r) for r in cn.cursor().execute(f.read()).fetchall()]
    cn.close()
    bad = [r for r in rows if r[1] != r[2]]
    print("права asda_reports в AsdaStoryOp: %d проверок, расхождений %d %s" % (len(rows), len(bad), bad or ""))
    login, pw, did = sys.argv[2], sys.argv[3], int(sys.argv[4])
    salt, h = A.make_secret(pw)
    r1 = st.register(did, "selftest", login, salt, h)
    r2 = st.register(did, "selftest", login + "x", *A.make_secret(pw))
    r3 = st.register(did + 1, "selftest2", login.upper(), *A.make_secret(pw))
    print("создание:", r1, "| повтор тем же участником:", r2, "| тот же логин другим участником:", r3)
    ok = len(rows) == 16 and not bad and r1[0] == 0 and r1[2] == login and r2 == (1, r1[1], login) and r3[0] == 2
    print("ИТОГ:", "OK" if ok else "ОШИБКА")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        sys.exit(live())
    unittest.main()
