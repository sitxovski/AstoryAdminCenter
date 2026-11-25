#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""account_register.py — регистрация игровой учётки из Discord: команда /register ЛОГИН ПАРОЛЬ (25.11.2026, задание владельца).
Интерфейс Discord (слэш-команды /register и /password, ответы) — в oracle_bot.py; здесь — всё, что проверяется без Discord
(модульные тесты test_account_register.py).

ЧТО ДЕЛАЕТ. Заводит НАСТОЯЩУЮ игровую учётку: одна строка AsdaStoryOp.dbo.Us_member (как UP_AC_CreateAccount P52 и создание в админ-центре,
AstoryAdminCenter/domains/accountnew.py) — процедурой adm.BotAccountRegister (AstoryAdminCenter/sql/adminc_32_botreg.sql) под тем же
логином бота asda_reports, у которого в AsdaStoryOp есть ТОЛЬКО EXECUTE этой процедуры. Одна учётка на одного участника Discord (привязка
adm.BotAccount на сервере); номер учётки — обычный счётчик (> 75000), служебной / операторской через бота не получить.
ПАРОЛЬ. На сервер уходит не пароль, а соль и хеш (как панель, domains/password.py): md5hex = MD5(пароль) hex — то, что клиент шлёт при входе
(памятка login-password-check-p52); хеш = SHA-256(соль(16) + md5hex) = Joy1.dbo.FN_AC_PwHash. Правила пароля — клиента: только печатный ASCII
(MD5 у клиента от байтов ANSI), до 50 знаков (поле входа LOGIN_EDIT01); пробелы запрещены (клиент снимает ведущие, а строка файла учёток
делится по пробелам); короче PW_MIN — отказ (учётки открыты всем, короткий пароль подбирается).
ЛОГИН. [A-Za-z0-9_.@-], 3…32 знака (поле входа LOGIN_EDIT00 — 32; правило входа P51) — те же, что в процедуре.
/password. Открытый пароль хранится ТОЛЬКО локально рядом с ботом — строкой в playtest_accounts.txt того же вида, что у прежних тестовых учёток
(«имя (@handle) [discord_id] - логин/пароль»), поэтому /password показывает и прежние, и новые учётки одним путём. В журнал бота пароль не
пишется. В имя и @handle строки идёт только user.name Discord, очищенный до [A-Za-z0-9_.] (отображаемое имя участник задаёт сам — в файл не идёт).
Адрес SQL и секрет — как у player_reports (reports.env, VPN). Побочных эффектов при импорте нет (pyodbc — лениво).
"""

import hashlib
import os
import re

import player_reports

LOGIN_MIN, LOGIN_MAX = 3, 32
LOGIN_RX = re.compile(r"[A-Za-z0-9_.@-]+")           # fullmatch: «$» пропустил бы хвостовой перевод строки
PW_MIN, PW_MAX = 6, 50
SQL_DB = "AsdaStoryOp"
# сообщение с установщиком игры (канал test-info) — ссылку задал владелец 25.11.2026
INSTALLER_URL = "https://discord.com/channels/@@ASTORY_DISCORD_GUILD@@/@@ASTORY_DISCORD_INSTALLER_CH@@/@@ASTORY_DISCORD_INSTALLER_MSG@@"

REGISTER_TEXT = {                     # код adm.BotAccountRegister → ответ участнику (EN, RU)
    1: ("You already have a game account: `{login}`. Use /password to see your login and password.",
        "У тебя уже есть игровая учётка: `{login}`. Логин и пароль покажет /password."),
    2: ("The login `{login}` is already taken — choose another one.",
        "Логин `{login}` уже занят — выбери другой."),
    3: ("Too many registrations right now — please try again later.",
        "Сейчас слишком много регистраций — попробуй позже."),
}
BANNED_TEXT = ("Registration is not available for you.", "Регистрация для тебя недоступна.")
HAVE_TEXT = REGISTER_TEXT[1]

# строка файла учёток — тот же вид, что разбирает oracle_bot.find_playtest_account
_LINE = re.compile(r"\(@(?P<handle>[^)]+)\)\s*(?:\[(?P<uid>\d+)\])?\s*-\s*(?P<login>[^/\s]+)/(?P<pw>\S+)\s*$")
_HANDLE_BAD = re.compile(r"[^A-Za-z0-9_.]")


def both(pair, **kw):
    """(EN, RU) → строка «EN / RU» с подстановкой."""
    return player_reports.both(pair, **kw)


def validate(login, password):
    """Параметры команды → (логин, пароль, ошибки [(EN, RU)]). Ошибок нет — можно регистрировать."""
    errs = []
    lg = str(login or "").strip(" ")
    pw = str(password or "")
    if not (LOGIN_MIN <= len(lg) <= LOGIN_MAX) or not LOGIN_RX.fullmatch(lg):
        errs.append(("Login: %d–%d characters, only Latin letters, digits and _ . @ -" % (LOGIN_MIN, LOGIN_MAX),
                     "Логин: %d–%d знаков, только латиница, цифры и знаки _ . @ -" % (LOGIN_MIN, LOGIN_MAX)))
    if any(not ("!" <= c <= "~") or c == "`" for c in pw) or not (PW_MIN <= len(pw) <= PW_MAX):   # «`» ломает показ пароля в Discord
        errs.append(("Password: %d–%d characters, only Latin letters, digits and ASCII symbols, no spaces and no `" % (PW_MIN, PW_MAX),
                     "Пароль: %d–%d знаков, только латиница, цифры и знаки ASCII, без пробелов и без `" % (PW_MIN, PW_MAX)))
    elif pw.lower() == lg.lower():
        errs.append(("The password must differ from the login.", "Пароль не должен совпадать с логином."))
    return lg, pw, errs


def md5hex(password):
    """Как клиент при входе и dbo.FN_AC_PwMd5Hex: MD5 от байтов ASCII, hex в нижнем регистре."""
    return hashlib.md5(password.encode("ascii")).hexdigest()


def pw_hash(salt, hexs):
    """= dbo.FN_AC_PwHash: SHA2_256(соль + LOWER(md5hex))."""
    return hashlib.sha256(bytes(salt) + hexs.lower().encode("ascii")).digest()


def make_secret(password, salt=None):
    """Пароль → (соль 16 б, хеш 32 б) для adm.BotAccountRegister."""
    salt = os.urandom(16) if salt is None else bytes(salt)
    return salt, pw_hash(salt, md5hex(password))


def file_status(text, uid):
    """Содержимое файла учёток и Discord ID → ("banned", None) | ("have", (логин, пароль)) | (None, None).
    Забаненный — закомментированная строка с пометкой BANNED и этим ID (так бан записан в файле с 27.10.2026)."""
    tag = "[%d]" % int(uid)
    have = None
    for line in str(text or "").splitlines():
        if tag not in line:
            continue
        if line.lstrip().startswith("#"):
            if "BANNED" in line:
                return "banned", None
            continue
        m = _LINE.search(line)
        if m and m["uid"] and int(m["uid"]) == int(uid) and have is None:
            have = (m["login"], m["pw"])
    return ("have", have) if have else (None, None)


def account_line(handle, uid, login, password):
    """Строка файла учёток для новой регистрации (вид прежних строк; имя и @handle — очищенный user.name)."""
    h = _HANDLE_BAD.sub("", str(handle or ""))[:32] or "user"
    line = "%s (@%s) [%d]   - %s/%s" % (h, h, int(uid), login, password)
    m = _LINE.search(line)
    if not m or m["login"] != login or m["pw"] != password or int(m["uid"]) != int(uid):   # строка обязана читаться обратно тем же разбором
        raise ValueError("строка учётки не читается обратно")
    return line


def append_account(path, handle, uid, login, password):
    """Дописать учётку в файл (ничего не перезаписывая: только добавление в конец)."""
    line = account_line(handle, uid, login, password)
    lead = ""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data and not data.endswith(b"\n"):
            lead = "\n"
    except FileNotFoundError:
        pass
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(lead + line + "\n")


def success_message(login, password, saved=True):
    """Ответ после создания учётки (видит только участник): логин, пароль, ссылка на установщик."""
    tail = ("-# Only you can see this message. Forgot it? Use /password. / Видно только тебе. Забыл — команда /password."
            if saved else
            "-# ⚠️ Save the password now — /password will not be able to show it. / Сохрани пароль сейчас — /password его показать не сможет.")
    return ("✅ **Account created / Учётка создана**\n"
            f"Login: `{login}`\nPassword: `{password}`\n"
            f"⬇️ Game installer / Установщик игры: {INSTALLER_URL}\n" + tail)


class Store:
    """Вызов adm.BotAccountRegister под логином asda_reports. connect — фабрика соединения (подставная в тестах)."""

    def __init__(self, connect=None, secret=player_reports.SECRET_PATH, server="@@ASTORY_SERVER_VPN_IP@@,1433"):
        self._connect, self._secret, self._server, self._pw = connect, secret, server, None

    def _cn(self):
        if self._connect is not None:
            return self._connect()
        import pyodbc
        if self._pw is None:
            self._pw = player_reports._parse_secret(player_reports._read_secret(self._secret))
        drv = sorted((d for d in pyodbc.drivers() if "SQL Server" in d), key=lambda d: ("ODBC Driver" not in d, d))
        if not drv:
            raise RuntimeError("нет ODBC-драйвера SQL Server")
        cs = ("DRIVER={%s};SERVER=%s;DATABASE=%s;UID=%s;PWD={%s};TrustServerCertificate=yes"
              % (drv[0], self._server, SQL_DB, player_reports.SQL_LOGIN, self._pw.replace("}", "}}")))
        cn = pyodbc.connect(cs, autocommit=True, timeout=15)
        cn.timeout = player_reports.SQL_QUERY_TIMEOUT_S
        return cn

    def register(self, discord_id, discord_name, login, salt, pwhash):
        """→ (код, номер учётки | None, логин | None). Код 0 — создана; 1 — у участника уже есть (её номер и логин); 2 — логин занят; 3 — предел."""
        cn = self._cn()
        try:
            row = cn.cursor().execute(
                "SET NOCOUNT ON; DECLARE @code INT, @uid INT, @login VARCHAR(32); "
                "EXEC adm.BotAccountRegister ?, ?, ?, ?, ?, @code OUTPUT, @uid OUTPUT, @login OUTPUT; SELECT @code, @uid, @login",
                int(discord_id), str(discord_name)[:64], login, bytes(salt), bytes(pwhash)).fetchone()
        finally:
            cn.close()
        return int(row[0]), (int(row[1]) if row[1] is not None else None), row[2]
