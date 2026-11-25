#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""player_reports.py — жалобы игроков на игроков: проверка формы, пределы частоты и запись в базу панели (шаг А6.11, часть «жалобы»,
22.11.2026; решение владельца №6 — канал жалоб = бот Discord). Интерфейс Discord (слэш-команда /report, окно формы, отправка ответов) —
в oracle_bot.py; здесь — всё, что проверяется без Discord (модульные тесты test_player_reports.py).

КУДА ПИШЕТСЯ. База панели AsdaAdmin на сервере (adm.PlayerReport / adm.PlayerReportFile / adm.PlayerReportReply,
AstoryAdminCenter/sql/adminc_23_reports.sql) — отдельным логином asda_reports, у которого есть ТОЛЬКО EXECUTE на четыре процедуры:
  adm.ReportSubmit, adm.ReportFileAdd   — подать жалобу и приложить скриншоты (пределы частоты и сигнатуры файлов — в процедурах);
  adm.ReportReplyClaim, adm.ReportReplyDone — забрать ответ оператора автору (каждый — один раз) и отметить, дошёл ли он.
Пароль логина — ЛОКАЛЬНО рядом с ботом, в reports.env (одна строка REPORTS_PASSWORD = …), так же, как токен бота в .env: та же папка, те же
права файла (наследуются от папки бота). ★ ревизия 67 Н-2: раньше бот читал его по SSH ключом администратора сервера — этого пути больше нет;
источник пароля на сервере — secrets\\asda_admin.ini (REPORTS_PASSWORD), перенос в reports.env — разовый, вручную (пароль не печатается).
Адрес SQL — как у db_connect (VPN). Пароль держится в памяти процесса, нигде не печатается.
КТО МОЖЕТ ПОДАТЬ (★ ревизия 67 С-1): участник с ролью User (её выдаёт бот после онбординга — выбор языка) и не меньше MIN_MEMBER_DAYS суток на
сервере (member.joined_at): вторые учётки Discord бесплатны, неделя ожидания делает массовый вброс дорогим, а честному игроку жалоба нужна
обычно не в первый день; проверка — may_report().

Побочных эффектов при импорте нет (pyodbc — лениво, внутри функций).
"""

import datetime as dt
import os
import re
import time
import uuid

CATEGORIES = {                       # код → (EN, RU); те же коды — CHECK в adm.PlayerReport
    "cheat": ("Cheating / bot", "Чит / бот"),
    "scam": ("Scam", "Мошенничество"),
    "abuse": ("Insults / harassment", "Оскорбления"),
    "rmt": ("Real-money trading (RMT)", "Торговля за реальные деньги (RMT)"),
    "other": ("Other", "Другое"),
}
NICK_MAX = 20                         # Charname VARCHAR(20) Joy1
WHEN_MAX = 100
BODY_MIN, BODY_MAX = 10, 1500
LINKS_MAX = 1000
LINKS_COUNT = 5
FILES_MAX = 3                         # скриншотов к жалобе (ReportFileAdd: код 2)
FILE_MAX = 8 * 1024 * 1024            # байт на файл (ReportFileAdd: код 3)
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
COOLDOWN_S = 60                       # между подачами одного участника (поверх пределов процедуры: 3 в час, 10 в сутки)
REPLIES_PER_TICK = 5                  # ответов за один проход цикла бота

MIN_MEMBER_DAYS = 7                   # ★ ревизия 67 С-1: суток на сервере до первой жалобы
SQL_QUERY_TIMEOUT_S = 30              # ★ ревизия 67 Н-4: предел запроса (вход — 15 с): поток не висит, тайм-аут сверху не нужен

SECRET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports.env")
SQL_LOGIN = "asda_reports"
SQL_DB = "AsdaAdmin"

# ссылки, которые можно приложить к жалобе: сообщение Discord и файл с CDN Discord — больше никаких адресов
LINK_RX = re.compile(r"^https://(?:(?:ptb\.|canary\.)?discord\.com/channels/\d{15,20}/\d{15,20}(?:/\d{15,20})?"
                     r"|(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/\d{15,20}/\d{15,20}/[A-Za-z0-9._-]{1,100}"
                     r"(?:\?[A-Za-z0-9=&%._-]{0,300})?)$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

SUBMIT_TEXT = {                       # код ReportSubmit → ответ автору (EN / RU)
    1: ("You have already sent 3 reports in the last hour — please wait a little.",
        "За последний час ты уже отправил 3 жалобы — подожди немного."),
    2: ("You have already sent 10 reports in the last 24 hours — please try again tomorrow.",
        "За сутки ты уже отправил 10 жалоб — попробуй завтра."),
    3: ("You already have an open report #{id} about this character — the team will look at it.",
        "У тебя уже есть открытая жалоба №{id} на этого персонажа — команда её рассмотрит."),
    4: ("Too many reports right now — please try again later.",
        "Сейчас слишком много жалоб — попробуй позже."),
}
FILE_TEXT = {                         # код ReportFileAdd → пометка в ответе автору
    1: ("the report is no longer open for screenshots", "жалоба уже закрыта для скриншотов"),
    2: ("only 3 screenshots per report", "к жалобе — не больше 3 скриншотов"),
    3: ("the file is empty or larger than 8 MB", "файл пустой или больше 8 МБ"),
    4: ("not a PNG / JPEG / GIF / WEBP picture", "не картинка PNG / JPEG / GIF / WEBP"),
    5: ("too many screenshots from you today (40 MB)", "за сутки от тебя слишком много скриншотов (40 МБ)"),
    6: ("too many screenshots from everyone today", "за сутки слишком много скриншотов от всех"),
}


def both(pair, **kw):
    """(EN, RU) → строка «EN / RU» с подстановкой."""
    return "%s / %s" % (pair[0].format(**kw), pair[1].format(**kw))


def clean_line(s, limit):
    """Одна строка без управляющих символов, без пробелов по краям, не длиннее limit."""
    s = _CTRL.sub(" ", str(s or "")).replace("\n", " ").strip()
    return s[:limit]


def clean_text(s, limit):
    """Многострочный текст: управляющие символы (кроме перевода строки) → пробел, \\r\\n → \\n, края без пробелов."""
    s = str(s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = _CTRL.sub(" ", s).strip()
    return s[:limit]


def parse_links(text):
    """Поле «ссылки» → (список допустимых ссылок, список отвергнутых). Разделители — пробелы и переводы строк."""
    good, bad = [], []
    for tok in re.split(r"\s+", str(text or "").strip()):
        if not tok or tok in good:
            continue                              # пусто или повтор той же ссылки — один раз
        (good if LINK_RX.match(tok) else bad).append(tok)
    return good, bad


def validate(nick, when, body, links, category):
    """Поля формы → (чистые значения, ошибки EN/RU). Ошибок нет — можно подавать."""
    errs = []
    if category not in CATEGORIES:
        errs.append(("Unknown category.", "Неизвестная категория."))
    n = clean_line(nick, 200)
    if not n:
        errs.append(("Write the character's nickname.", "Укажи ник персонажа."))
    elif len(n) > NICK_MAX:
        errs.append(("A character nickname is at most %d characters." % NICK_MAX, "Ник персонажа — не длиннее %d знаков." % NICK_MAX))
    b = clean_text(body, BODY_MAX + 1)
    if len(b) < BODY_MIN:
        errs.append(("Describe what happened (at least %d characters)." % BODY_MIN, "Опиши, что случилось (не короче %d знаков)." % BODY_MIN))
    elif len(b) > BODY_MAX:
        errs.append(("The description is at most %d characters." % BODY_MAX, "Описание — не длиннее %d знаков." % BODY_MAX))
    good, bad = parse_links(links)
    if bad:
        errs.append(("Links: only Discord message links or Discord attachment links.",
                     "Ссылки: только ссылки на сообщения Discord или на вложения Discord."))
    if len(good) > LINKS_COUNT:
        errs.append(("At most %d links." % LINKS_COUNT, "Не больше %d ссылок." % LINKS_COUNT))
    joined = "\n".join(good)
    if len(joined) > LINKS_MAX:
        errs.append(("The links are too long.", "Ссылки слишком длинные."))
    return {"nick": n, "when": clean_line(when, WHEN_MAX), "body": b, "links": joined, "category": category}, errs


def sniff_image(data):
    """Байты → тип картинки по сигнатуре (как adm.ReportFileAdd) или None."""
    d = bytes(data or b"")
    if d[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if d[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if d[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
        return "image/webp"
    return None


def check_attachment(content_type, size):
    """Вложение команды до скачивания → None (годно) или (EN, RU) причина."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in IMAGE_TYPES:
        return ("Screenshots: only PNG, JPEG, GIF or WEBP pictures.", "Скриншоты: только картинки PNG, JPEG, GIF или WEBP.")
    if not size or size > FILE_MAX:
        return ("Screenshots: each file must be at most 8 MB.", "Скриншоты: каждый файл — не больше 8 МБ.")
    return None


class Cooldown:
    """Не чаще одной подачи за COOLDOWN_S на участника (в памяти процесса). clock — подставные часы для тестов."""

    def __init__(self, seconds=COOLDOWN_S, clock=time.monotonic):
        self.seconds, self.clock, self.last = seconds, clock, {}

    def left(self, uid):
        """Сколько секунд ждать (0 — можно)."""
        t = self.last.get(uid)
        if t is None:
            return 0
        return max(0, int(self.seconds - (self.clock() - t) + 0.999))

    def mark(self, uid):
        self.last[uid] = self.clock()
        if len(self.last) > 5000:                 # не копить навсегда: старые отметки больше не нужны
            now = self.clock()
            self.last = {k: v for k, v in self.last.items() if now - v < self.seconds}


def reply_message(report_id, category, target, text):
    """Личное сообщение автору с ответом оператора (текст — оператора, как он его написал)."""
    cat = CATEGORIES.get(category, (category, category))
    return ("📨 **Astory** — reply to your report #%d (%s, %s) / ответ по твоей жалобе №%d (%s, %s):\n%s"
            % (report_id, cat[0], target, report_id, cat[1], target, text))[:2000]


def _parse_secret(text):
    for line in str(text or "").splitlines():
        m = re.match(r"^\s*REPORTS_PASSWORD\s*=\s*(.*?)\s*$", line)
        if m and m.group(1):
            return m.group(1)
    raise RuntimeError("REPORTS_PASSWORD не найден в файле секрета бота")


def _read_secret(path):
    """Локальный файл секрета бота (reports.env). ★ ревизия 67 Н-2: только локальный путь — SSH здесь нет."""
    with open(path, encoding="utf-8") as f:
        return f.read()


JOIN_TEXT = ("Reports can be sent by members who finished onboarding and have been on the server for at least %d days."
             % MIN_MEMBER_DAYS, "Жалобу может отправить участник, прошедший онбординг и пробывший на сервере не меньше %d суток." % MIN_MEMBER_DAYS)


def may_report(has_user_role, joined_at, now=None):
    """★ ревизия 67 С-1: можно ли участнику подать жалобу → None (можно) или (EN, RU) причина. joined_at — когда вошёл на сервер (aware UTC)."""
    if not has_user_role or joined_at is None:
        return JOIN_TEXT
    now = now or dt.datetime.now(dt.timezone.utc)
    if now - joined_at < dt.timedelta(days=MIN_MEMBER_DAYS):
        return JOIN_TEXT
    return None


class Store:
    """Запись жалоб процедурами adm.Report* под логином asda_reports. connect — фабрика соединения (подставная в тестах)."""

    def __init__(self, connect=None, secret=SECRET_PATH, server="@@ASTORY_SERVER_VPN_IP@@,1433"):
        self._connect, self._secret, self._server, self._pw = connect, secret, server, None
        self.claim_nonce = None            # ★ ревизия 67 Н-4: номер захвата, ответы которого ещё не обработаны (сбой — тот же номер)

    def _cn(self):
        if self._connect is not None:
            return self._connect()
        import pyodbc
        if self._pw is None:
            self._pw = _parse_secret(_read_secret(self._secret))
        drv = sorted((d for d in pyodbc.drivers() if "SQL Server" in d), key=lambda d: ("ODBC Driver" not in d, d))
        if not drv:
            raise RuntimeError("нет ODBC-драйвера SQL Server")
        cs = ("DRIVER={%s};SERVER=%s;DATABASE=%s;UID=%s;PWD={%s};TrustServerCertificate=yes"
              % (drv[0], self._server, SQL_DB, SQL_LOGIN, self._pw.replace("}", "}}")))
        cn = pyodbc.connect(cs, autocommit=True, timeout=15)
        cn.timeout = SQL_QUERY_TIMEOUT_S
        return cn

    def submit(self, reporter_id, reporter_name, f):
        """Жалоба (значения validate) → (код, номер). Код 0 — записана; 1–4 — предел (SUBMIT_TEXT)."""
        cn = self._cn()
        try:
            row = cn.cursor().execute(
                "SET NOCOUNT ON; DECLARE @id INT, @code INT; EXEC adm.ReportSubmit ?, ?, ?, ?, ?, ?, ?, @id OUTPUT, @code OUTPUT; SELECT @code, @id",
                int(reporter_id), str(reporter_name)[:64], f["nick"], f["category"], f["when"], f["body"], f["links"]).fetchone()
        finally:
            cn.close()
        return int(row[0]), (int(row[1]) if row[1] is not None else None)

    def add_file(self, report_id, reporter_id, name, data):
        """Скриншот к своей жалобе → код (0 — записан; FILE_TEXT)."""
        cn = self._cn()
        try:
            row = cn.cursor().execute("SET NOCOUNT ON; DECLARE @code INT; EXEC adm.ReportFileAdd ?, ?, ?, ?, @code OUTPUT; SELECT @code",
                                      int(report_id), int(reporter_id), clean_line(name, 100) or "screenshot", bytes(data)).fetchone()
        finally:
            cn.close()
        return int(row[0])

    def claim(self, n=REPLIES_PER_TICK):
        """Ответы авторам, ждущие отправки → [dict(id, report_id, reporter_id, text, target, category)] (каждый отдаётся один раз).
        ★ ревизия 67 Н-4: захват идёт под номером claim_nonce; если запрос упал по дороге (строки взяты, а до бота не дошли), номер остаётся, и
        следующий захват тем же номером вернёт их снова. Номер сбрасывается вызывающим (claimed_ok) после обработки полученных строк."""
        if self.claim_nonce is None:
            self.claim_nonce = str(uuid.uuid4())
        cn = self._cn()
        try:
            rows = cn.cursor().execute("EXEC adm.ReportReplyClaim ?, ?", int(n), self.claim_nonce).fetchall()
        finally:
            cn.close()
        return [{"id": int(r[0]), "report_id": int(r[1]), "reporter_id": int(r[2]), "text": r[3], "target": r[4], "category": r[5]} for r in rows]

    def claimed_ok(self):
        """Все строки последнего захвата обработаны (итог записан или записать не удалось) → новый номер на следующий захват."""
        self.claim_nonce = None

    def done(self, reply_id, ok, result):
        """Итог отправки ответа → 1 записан, 0 — строка уже не «взята ботом»."""
        cn = self._cn()
        try:
            row = cn.cursor().execute("EXEC adm.ReportReplyDone ?, ?, ?", int(reply_id), 1 if ok else 0, clean_line(result, 200)).fetchone()
        finally:
            cn.close()
        return int(row[0])
