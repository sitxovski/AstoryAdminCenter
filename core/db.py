# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""db.py — подключения админ-центра к SQL Server. 16.11.2026.

ДВА ВИДА ПОДКЛЮЧЕНИЙ
  * game(db)  — игровые базы Joy1 / AsdaStoryOp / joylog1 / AsdaStoryLogin. В волне А0 только чтение: логин
                `asda_admin` имеет там лишь db_datareader (sql/adminc_01…03), а каждый запрос ещё и проходит
                assert_select_only (второй рубеж, тот же, что у AstoryServer/Tools/Anticheat/db_connect.py).
  * admin()   — своя база AsdaAdmin (пользователи панели, сессии, журнал действий); логин asda_admin — её владелец.

ТЕКСТ В ИГРОВЫХ БАЗАХ. Joy1, AsdaStoryOp и joylog1 имеют сортировку Arabic_CI_AS (кодовая страница 1256), а игра
  кладёт в varchar байты cp1251 (разбор — памятка db-collation-cyrillic). Драйвер расшифровывает их по 1256, поэтому
  русское имя приходит «арабскими» буквами. Байты при этом целы: cp1256 обратима для всех 256 значений, так что
  fix_text() возвращает ровно то, что видит игрок (перекодировка 1256 → байты → 1251). В обратную сторону (поиск по
  русскому имени) to_db_text() делает обратное, чтобы сравнение шло по тем же байтам.

ПАРОЛЬ asda_admin — только в файле на сервере (config.SECRET_FILE, права — Administrators/SYSTEM), читается локально
  или по SSH, хранится в памяти процесса; не печатается и не пишется в журналы.
Побочных эффектов при импорте нет (pyodbc подключается лениво).
"""
import re
import threading

from . import config, hostshell

ARABIC_DBS = {"joy1", "asdastoryop", "joylog1"}            # базы с Arabic_CI_AS (сняты с живого 16.11.2026)
GAME_DBS = {"joy1": "Joy1", "asdastoryop": "AsdaStoryOp", "joylog1": "joylog1", "asdastorylogin": "AsdaStoryLogin"}

# Слово ищется без \b слева: после цифры граница слова не видна («SELECT 1DELETE FROM t» T-SQL исполняет как
# «SELECT 1 DELETE FROM t» — перепроверка ревизии А0 №7). Слева допускается всё, кроме букв/_/@/#/$ имени.
_FORBIDDEN = re.compile(
    r"(?<![A-Za-z_@#$])(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|MERGE|GRANT|REVOKE|DENY|BACKUP|RESTORE|"
    r"SHUTDOWN|INTO|OPENROWSET|OPENQUERY|OPENDATASOURCE|DBCC|KILL|WAITFOR|RECONFIGURE|UPDATETEXT|WRITETEXT|"
    r"READTEXT|BULK|OPENXML|NEXT\s+VALUE|USE|GO|BEGIN|COMMIT|ROLLBACK|SAVE|DISABLE|ENABLE)(?![A-Za-z0-9_@#$])", re.I)
_LEAD_OK = re.compile(r"^\s*(SELECT|WITH|DECLARE|SET\s+NOCOUNT)\b", re.I)

_pw_lock = threading.Lock()
_pw = {}                  # ключ секрета → пароль (только в памяти процесса)
_override = {}            # самотест: "admin"/"game" → фабрика соединения (LocalDB и т.п.)


class DbError(Exception):
    """Ошибка подключения/запроса с понятной причиной (без секретов)."""


_TOKENS = re.compile(r"N?'(?:[^']|'')*'|\[(?:[^\]]|\]\])*\]|--[^\n]*|/\*.*?\*/", re.S)


def _strip_literals(sql):
    """Текст запроса без литералов, [имён] и комментариев — ОДНИМ проходом слева направо: что встретилось раньше,
    то и считается (ревизия А0 №7: при раздельных проходах «SELECT '--'; DELETE …» прятал DELETE в «комментарий»).
    Незакрытый литерал или комментарий → отказ (в нём могло бы спрятаться что угодно)."""
    def sub(m):
        t = m.group(0)
        return "''" if t.startswith(("'", "N'")) else ("[x]" if t.startswith("[") else " ")
    out = _TOKENS.sub(sub, sql)
    if "'" in out.replace("''", "") or "/*" in out:
        raise DbError("к игровым базам допускаются только запросы чтения (незакрытый литерал или комментарий)")
    return out


def assert_select_only(sql):
    """Отказ, если запрос не чистое чтение (второй рубеж поверх прав db_datareader)."""
    body = _strip_literals(sql)
    for part in [p for p in body.split(";") if p.strip()]:
        if not _LEAD_OK.match(part):
            raise DbError("к игровым базам допускаются только запросы чтения")
    m = _FORBIDDEN.search(body)
    if m:
        raise DbError("к игровым базам допускаются только запросы чтения (слово %s)" % m.group(1).upper())


def fix_text(v):
    """Строка из Arabic-базы → как её видит игра (cp1251)."""
    if not isinstance(v, str) or not v:
        return v
    try:
        return v.encode("cp1256").decode("cp1251", "replace")
    except UnicodeEncodeError:
        return v


def to_db_text(s):
    """Строка поиска → вид, в котором драйвер сравнит её с байтами cp1251 Arabic-столбца."""
    if not isinstance(s, str) or not s:
        return s
    try:
        return s.encode("cp1251").decode("cp1256")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _secret(key="PASSWORD"):
    """Значение из файла секретов на сервере (KEY = value), кэш на процесс."""
    with _pw_lock:
        if key in _pw:
            return _pw[key]
        try:
            text = hostshell.read_server_file(config.get().secret_file)
        except (OSError, hostshell.HostError) as ex:
            raise DbError("файл секретов админ-центра не прочитан (%s)" % ex.__class__.__name__)
        for line in text.splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip().upper() == key:
                _pw[key] = v.strip().strip('"')
                return _pw[key]
        raise DbError("в файле секретов нет ключа %s" % key)


def _connect(database):
    """Новое соединение логином asda_admin к базе database."""
    import pyodbc  # ленивый импорт: модуль безопасно импортировать без драйвера
    cfg = config.get()
    try:
        cn = pyodbc.connect("DRIVER={%s};SERVER=tcp:%s;DATABASE=%s;UID=%s;PWD={%s};Connect Timeout=10;"
                            "Application Name=AsdaAdminCenter" % (cfg.sql_driver, cfg.sql_server, database,
                                                                  cfg.sql_login, _secret().replace("}", "}}")),
                            autocommit=True, timeout=10)
    except pyodbc.Error as ex:
        raise DbError("нет подключения к %s: %s" % (database, _sql_reason(ex)))
    cn.timeout = 60
    return cn


def _sql_reason(ex):
    """Короткая причина ошибки pyodbc без строки подключения."""
    s = str(ex.args[1] if len(ex.args) > 1 else ex)
    s = re.sub(r"\[[^\]]*\]", "", s)
    return s.split("(SQL")[0].strip()[:300]


def set_override(kind, factory):
    """Самотест: подменить источник соединений ("admin" | "game") фабрикой factory(database) или None."""
    if factory is None:
        _override.pop(kind, None)
    else:
        _override[kind] = factory


def admin():
    """Соединение с базой AsdaAdmin (вызывающий закрывает)."""
    f = _override.get("admin")
    return f(config.get().admin_db) if f else _connect(config.get().admin_db)


class GameReader:
    """Чтение игровой базы: только SELECT, текст Arabic-баз перекодирован в cp1251."""

    def __init__(self, key):
        k = key.lower()
        if k not in GAME_DBS:
            raise DbError("неизвестная игровая база %s" % key)
        self.key = k
        self.name = GAME_DBS[k]
        f = _override.get("game")
        self.cn = f(self.name) if f else _connect(self.name)
        self.arabic = k in ARABIC_DBS

    def rows(self, sql, params=()):
        """Список dict по запросу (только чтение)."""
        assert_select_only(sql)
        import pyodbc
        try:
            cur = self.cn.cursor()
            cur.execute(sql, *params) if params else cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            out = []
            for r in cur.fetchall():
                out.append({c: (fix_text(v) if self.arabic else v) for c, v in zip(cols, r)})
            return out
        except pyodbc.Error as ex:
            raise DbError("запрос к %s: %s" % (self.name, _sql_reason(ex)))

    def multi(self, sql, params=()):
        """Пакет из нескольких SELECT одним обращением → список наборов строк (по одному на SELECT).

        Ошибка пакета → DbError (вызывающий может повторить по одному запросу, чтобы найти виновника)."""
        assert_select_only(sql)
        import pyodbc
        out = []
        try:
            cur = self.cn.cursor()
            cur.execute(sql, *params) if params else cur.execute(sql)
            while True:
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    out.append([{c: (fix_text(v) if self.arabic else v) for c, v in zip(cols, r)} for r in cur.fetchall()])
                if not cur.nextset():
                    break
            return out
        except pyodbc.Error as ex:
            raise DbError("запрос к %s: %s" % (self.name, _sql_reason(ex)))

    def one(self, sql, params=()):
        """Первая строка или None."""
        r = self.rows(sql, params)
        return r[0] if r else None

    def text(self, s):
        """Параметр-строка для сравнения со столбцом этой базы."""
        return to_db_text(s) if self.arabic else s

    def close(self):
        """Закрыть соединение."""
        try:
            self.cn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class GameWriter:
    """ЗАПИСЬ в игровую базу логином asda_ops (sql/adminc_04_ops.sql: Item — UPDATE только перечисленных там столбцов: перенос,
    золото, свойства экземпляра).

    Одна транзакция на объект: commit() — зафиксировать, без commit() при закрытии — откат. Пользоваться только из
    операций core/ops (журнал, предпросмотр, откат). Текст Arabic-баз — как у GameReader (fix_text / text)."""

    def __init__(self, key):
        k = key.lower()
        # ★ А6.7 (22.11): + joylog1 — журнал дел san.* (domains/cases.py); права логина там — только san.* (sql/adminc_21_san.sql)
        # ★ А6.9 (22.11): + asdastorylogin — корректировка баланса gp7; права логина там — только EXECUTE adm.GP7Adjust (sql/adminc_22_gp7adjust.sql)
        if k not in ("joy1", "asdastoryop", "joylog1", "asdastorylogin"):
            raise DbError("логину правок доступны только Joy1, AsdaStoryOp, joylog1 (дела san.*) и AsdaStoryLogin (adm.GP7Adjust)")
        self.name = GAME_DBS[k]
        f = _override.get("ops")
        if f:
            self.cn = f(self.name)
        else:
            import pyodbc
            cfg = config.get()
            try:
                self.cn = pyodbc.connect("DRIVER={%s};SERVER=tcp:%s;DATABASE=%s;UID=asda_ops;PWD={%s};Connect Timeout=10;"
                                         "Application Name=AsdaAdminCenter-ops" % (cfg.sql_driver, cfg.sql_server, self.name,
                                                                                   _secret("OPS_PASSWORD").replace("}", "}}")),
                                         autocommit=False, timeout=10)
            except pyodbc.Error as ex:
                raise DbError("нет подключения на запись к %s: %s" % (self.name, _sql_reason(ex)))
        self.cn.autocommit = False
        self.cn.timeout = 30
        # ревизия А1: ждать чужую блокировку не дольше 5 с и уступать игровому серверу при взаимной блокировке
        self.cn.cursor().execute("SET LOCK_TIMEOUT 5000; SET DEADLOCK_PRIORITY LOW")
        self.arabic = k in ARABIC_DBS
        self.done = False

    def rows(self, sql, params=()):
        """Список dict (внутри транзакции записи)."""
        import pyodbc
        try:
            cur = self.cn.cursor()
            cur.execute(sql, *params) if params else cur.execute(sql)
            if not cur.description:
                return []
            cols = [d[0] for d in cur.description]
            return [{c: (fix_text(v) if self.arabic else v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        except pyodbc.Error as ex:
            raise DbError("запись в %s: %s" % (self.name, _sql_reason(ex)))

    def execute(self, sql, params=()):
        """Изменяющий запрос → число затронутых строк."""
        import pyodbc
        try:
            cur = self.cn.cursor()
            cur.execute(sql, *params) if params else cur.execute(sql)
            return cur.rowcount
        except pyodbc.Error as ex:
            raise DbError("запись в %s: %s" % (self.name, _sql_reason(ex)))

    def commit(self):
        self.cn.commit()
        self.done = True

    def close(self):
        try:
            if not self.done:
                self.cn.rollback()
            self.cn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def admin_rows(cn, sql, params=()):
    """Список dict по запросу к AsdaAdmin (любой запрос; база своя)."""
    import pyodbc
    try:
        cur = cn.cursor()
        cur.execute(sql, *params) if params else cur.execute(sql)
        if not cur.description:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except pyodbc.Error as ex:
        raise DbError("AsdaAdmin: %s" % _sql_reason(ex))
