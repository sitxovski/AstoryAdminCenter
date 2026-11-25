# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""logs.py — «Живое управление → Журналы стойки»: хвост серверных журналов, ТОЛЬКО ЧТЕНИЕ (шаг А5.6, 21.11.2026; разбор и
инвентаризация — Reports/admin_center/impl_a5_live_20261121.md §«А5.6»).

Что: выбор источника (журнал патчей наших DLL, стоковые журналы GameServer / NpcServer / Relay / …, EacServer, gp7, LogDrop, служба
панели, прогоны restart_stack), процесса-копии и файла; хвост N строк; поиск по подстроке и уровню; «следить» — опрос с отметкой
«размер:время» (данные открываются, только когда они изменились); ссылки на карточку игрока по номеру учётки / имени в строке.

Как читается, чтобы не мешать серверам (реверс А5.6 §1, урок Н-1 ревизии 44):
  * путь собирается ТОЛЬКО из белого списка (источник → копии → подпапка → шаблон имени файла); имя файла, копия и вид журнала
    сверяются регулярными выражениями без разделителей пути — произвольного пути и «..» нет;
  * размер и время — по ПУТИ (os.stat: дескриптор только атрибутов, на общий доступ не влияет; с ПК — FileInfo.Refresh). Листинг
    каталога не годится: у файла, который держит писатель, в записи каталога размер 0 (проверено на стойке 21.11 — Ping/Net/eac);
  * данные открываются на время чтения с FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE (служба — CreateFileW, ПК — FileShare
    ReadWrite, Delete) и сразу закрываются; при опросе «следить» — только если размер или время изменились;
  * Event\\EventLog.txt GameServer / NpcServer пишется CreateFileA(GENERIC_WRITE, share 0) (GameServer.c:10209, NpcServer.exe.c:19965):
    чужой дескриптор данных в этот миг — потерянная строка журнала. Поэтому у него нет «следить», а читается он, только если не менялся
    QUIET_S секунд (запись — короткая вспышка при чтении Event.dat).
Маскировка: секреты (весь список аргументов процедур входа / паролей, ключи по шаблону имени — любой префикс и суффикс, JSON, массивы
заголовков, Basic / Bearer, «Pass x», длинные шестнадцатеричные) — всегда и ДО поиска (подстрокой секрет не нащупать); адреса IP, MAC и
идентификатор установки клиента — без права logs.view_ip. UTF-16 распознаётся по началу файла и декодируется до разбиения.
Лимиты: строк ≤ LINES_MAX, длина строки ≤ LINE_MAX, ответ ≤ OUT_MAX, окно поиска ≤ SCAN_MAX, опрос одного файла — не чаще MIN_GAP_S
(ключ без учёта регистра), на пользователя — PER_MIN запросов и BYTES_USER_MIN байт в минуту, на службу — BYTES_ALL_MIN байт в минуту
и READERS одновременных чтений. С ПК (SSH) файл читается в память и закрывается ДО передачи; тишина EventLog — по часам сервера.
Никаких удалений, ротации и записи. Побочных эффектов при импорте нет.
"""
import base64
import os
import re
import threading
import time

from core import config, hostshell
from core.ops import OpRefused
from domains import shopdata as E

LINES_DEF, LINES_MAX = 200, 2000          # строк хвоста по умолчанию / не больше
LINE_MAX = 1000                           # знаков строки (дальше — «…»)
OUT_MAX = 512 * 1024                      # знаков текста в ответе (старые строки отбрасываются первыми)
SCAN_DEF, SCAN_MAX = 256 * 1024, 4 * 1024 * 1024    # байт хвоста файла: просто хвост / поиск (окно поиска не больше)
FOLLOW_MAX = 256 * 1024                   # байт прироста за один опрос «следить» (больше — берётся конец, пропуск помечается)
FILES_MAX = 60                            # файлов в списке (новые сверху)
QUIET_S = 10                              # EventLog.txt: не менялся столько секунд — можно прочитать
MIN_GAP_S = 2.0                           # опрос одного и того же файла одним пользователем — не чаще
PER_MIN = 60                              # запросов журналов одного пользователя в минуту

# Копии процессов — состав стойки из stack_layout (через shopdata.folders), прочие — по живому листингу v2 (А5.6 §1).
def _gs():
    return E.folders("GS")


def _npc():
    return E.folders("NPC")


def _relay():
    return E.folders("SDB")[:3]


DLL_PROCS = lambda: _gs() + _npc() + _relay() + ["ItemRelayServer", "OperationServer", "LoginManager", "DBManager"]
STOCK_IOCP = lambda: _gs() + _npc() + _relay() + ["ItemRelayServer", "OperationServer", "LoginManager", "DBManager", "ChannelManager",
                                                  "OverlapCheckServer"]

# Источник → описание. root: v2 (корень стойки), svc (служба панели на сервере), data (папка данных панели на ЭТОЙ машине).
#   sub — подпапка копии; kinds — подпапки вида (GameServer Log\\Log_<Вид>); rx — шаблон имени файла; enc — запасная кодировка строки,
#   если она не UTF-8 (наши DLL — cp1251 WriteCp1251, сток — cp949 корейский); writer — shared (пишет с общим доступом на чтение)
#   или exclusive (share 0 — см. шапку); lv — разбор уровня строки.
SOURCES = {
    "patch": {"title": "Журнал патчей наших DLL (Log_Patch)", "root": "v2", "procs": DLL_PROCS, "sub": "Log\\Log_Patch",
              "rx": r"PatchLog_\d{8}\.txt", "enc": "cp1251", "writer": "shared", "lv": "patch",
              "rotation": "файл на запуск процесса (дата старта), пишется до остановки", "how": "CreateFileW FILE_APPEND_DATA, общий доступ RW (Log.cpp:61)"},
    "boot": {"title": "Загрузка DLL (*_boot.log)", "root": "v2", "procs": DLL_PROCS, "sub": "",
             "rx": r"(asdapatch|loginpatch|dbpatch|srvdbpatch)_boot\.log", "enc": "cp1251", "writer": "shared", "lv": "patch",
             "rotation": "переписывается при каждом старте", "how": "CreateFileW GENERIC_WRITE, общий доступ на чтение (dllmain.cpp)"},
    "acjournal": {"title": "Запасной журнал античита P53 (.sql)", "root": "v2", "procs": lambda: _gs() + ["LoginManager"],
                  "sub": "Log\\Log_AcJournal", "rx": r"AcJournal_\d{8}\.sql", "enc": "cp1251", "writer": "shared", "lv": "generic",
                  "rotation": "по дням; пишется, только когда база журнала недоступна", "how": "CreateFileW FILE_APPEND_DATA, общий доступ RW (AcJournal.cpp:773)"},
    "gslog": {"title": "Журналы GameServer (сток, Log\\Log_*)", "root": "v2", "procs": _gs, "sub": "Log", "kinds": r"Log_[A-Za-z_]+",
              "kinds_skip": ("log_patch", "log_acjournal"), "rx": r"[A-Za-z0-9]+_\d{8}\.txt", "enc": "cp949", "writer": "shared", "lv": "generic",
              "rotation": "по дням (имя_ГГГГММДД)", "how": "CreateFileA GENERIC_WRITE, общий доступ на чтение, держится весь день (GameServer.c:140190)"},
    "errlog": {"title": "Error_Log (сток: NpcServer, Relay, ItemRelay, Operation, ChannelManager)", "root": "v2",
               "procs": lambda: _npc() + _relay() + ["ItemRelayServer", "OperationServer", "ChannelManager"], "sub": "Error_Log",
               "rx": r"[A-Za-z0-9_]+_\d{8,10}\.txt", "enc": "cp949", "writer": "shared", "lv": "generic",
               "rotation": "по дням (у OperationServer CUserList — по часам)", "how": "_open O_APPEND на каждую строку, общий доступ RW (NpcServer.exe.c:6570)"},
    "iocp": {"title": "Сеть Log_IocpNet (сток)", "root": "v2", "procs": STOCK_IOCP, "sub": "Log_IocpNet", "rx": r"(Net|Flag)_\d{8}\.txt",
             "enc": "cp949", "writer": "shared", "lv": "generic", "rotation": "по дням",
             "how": "CreateFileA GENERIC_WRITE, общий доступ на чтение, держится весь день (NpcServer.exe.c:4966)"},
    "oledb": {"title": "Ошибки базы OLEDB_LOG (сток)", "root": "v2", "procs": lambda: _relay() + ["ItemRelayServer", "OperationServer",
                                                                                                    "LoginManager", "DBManager"],
              "sub": "OLEDB_LOG", "rx": r"LOG_FILE_\d{8}\.txt", "enc": "cp949", "writer": "shared", "lv": "generic", "rotation": "по дням",
              "how": "стоковый журнал ODBC (аргументы входа UPUserLogin маскируются)"},
    "eventlog": {"title": "Event\\EventLog.txt (чтение событий, сток)", "root": "v2", "procs": lambda: _gs() + _npc(), "sub": "Event",
                 "rx": r"EventLog\.txt", "enc": "cp949", "writer": "exclusive", "lv": "generic", "rotation": "не ротируется (растёт)",
                 "how": "CreateFileA GENERIC_WRITE, share 0 — коротко при чтении Event.dat (GameServer.c:10209, NpcServer.exe.c:19965)"},
    "eac": {"title": "EacServer (сайдкар EAC)", "root": "v2", "procs": lambda: ["EacServer"], "sub": "logs", "rx": r"eac_\d{8}\.log",
            "enc": "cp1251", "writer": "shared", "lv": "eac", "rotation": "по дням",
            "how": "_wfsopen «ab» _SH_DENYWR — читать можно (EacServer Log.cpp:98)"},
    "caddy": {"title": "caddy (HTTPS перед EacServer)", "root": "v2", "procs": lambda: ["EacServer"], "sub": "caddy\\logs",
              "rx": r"caddy(-[0-9T.\-]+)?\.log", "enc": "cp1251", "writer": "shared", "lv": "caddy", "rotation": "по размеру (caddy)",
              "how": "Go, общий доступ RW"},
    "gp7": {"title": "gp7-server (баланс и витрина)", "root": "v2", "procs": lambda: ["gp7-server"], "sub": "logs", "rx": r"gp7-\d{8}\.log",
            "enc": "cp1251", "writer": "shared", "lv": "generic", "rotation": "по дням (~6 МБ в сутки: пульс каждые секунды)",
            "how": "Node.js, общий доступ RW"},
    "logdrop": {"title": "LogDrop (приём журналов клиентов)", "root": "v2", "procs": lambda: ["LogDrop"], "sub": "service\\logs",
                "rx": r"(accepted|rejects|service)_\d{8}\.log", "enc": "cp1251", "writer": "shared", "lv": "generic", "rotation": "по дням",
                "how": "FileStream Append на каждую запись, FileShare.Read (AsdaLogDrop.cs:167)"},
    "panel": {"title": "Служба панели (service.log)", "root": "svc", "procs": lambda: ["AdminCenter"], "sub": "logs",
              "rx": r"service\.log(\.1)?", "enc": "cp1251", "writer": "shared", "lv": "generic",
              "rotation": "по размеру 20 МБ → service.log.1 (run_service.bat при старте службы)", "how": "cmd «>>», общий доступ RW"},
    "stack_runs": {"title": "Прогоны restart_stack (data\\stack_runs)", "root": "data", "procs": lambda: ["stack_runs"], "sub": "",
                   "rx": r"[A-Za-z0-9_.\-]+\.log", "enc": "cp1251", "writer": "shared", "lv": "generic",
                   "rotation": "файл на прогон", "how": "пишет панель (domains/stack.py), только на машине, где шёл restart_stack — на ПК"},
}
NAME_RX = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")      # копия / вид / файл: без разделителей пути
LEVELS = ("err", "warn", "info", "debug")

# ---------------------------------------------------------------------------------------------------------------- маскировка
# ★ ревизия 46 В-1: процедуры, в аргументах которых логин / пароль. Реверс (все форматы EXEC / {call} в декомпилах RE/ida/*_work):
#   пароль несёт только UPUserLogin (LoginManager.c:2582 «EXEC UPUserLogin '%s','%s','%s', %d, …» — логин и пароль без экранирования);
#   прочие стоковые процедуры с '%s' (UPCharUserid, UPUserBlock, UPUserChat, UPUserState) паролей не несут. Маскируется ВЕСЬ список
#   аргументов процедуры, имя которой содержит login / pass / pwd / auth / regist (любая форма: EXEC[UTE], {call …(…)}, dbo., [скобки],
#   без EXEC с префиксом UP), до последнего « :: » строки (хвост стока «:: Execute Error») или до конца строки — апострофы и «','»
#   внутри логина / пароля границу не сдвигают.
_PROC_RX = re.compile(r"(?i)(?:\bEXEC(?:UTE)?\s+|\{\s*(?:\?\s*=\s*)?call\s+|(?<![A-Za-z0-9_])(?=UP[A-Za-z]*(?:login|pass|pwd|auth|regist)))"
                      r"((?:\[?\w+\]?\.){0,2}\[?(\w*)\]?)")
_PROC_SENS = re.compile(r"(?i)login|logon|pass|pwd|auth|regist|createuser|joinuser|credential")
# ★ ревизия 46 С-1: ключ секрета — по шаблону ИМЕНИ (любой префикс / суффикс, snake / camel / kebab, в кавычках JSON), значение — после
#   «=» / «:» (кавычки, массив заголовков [...], «Basic / Bearer / Digest …», иначе до разделителя).
_KV_RX = re.compile(r"(?<![A-Za-z0-9_\-])([\"']?)([A-Za-z][A-Za-z0-9_\-]{0,63})\1(\s*[=:]\s*)"
                    r"((?:bearer|basic|digest|negotiate)\s+[^\s\"',;\]]+|\"(?:[^\"\\]|\\.)*\"|'[^']*'|\[[^\]]*\]|[^\s;,&)\]]+)", re.I)
_KEY_SENS = re.compile(r"(?i)pwd|passw|passphrase|^pass$|_pass$|pass_|secret|token|api[_\-]?key|private[_\-]?key|access[_\-]?key|"
                       r"secret[_\-]?key|signing|hmac|signature|^sig$|_sig$|cookie|csrf|xsrf|^otp$|_otp$|totp|authorization|^auth$|"
                       r"auth[_\-]?(token|key|code|header)|session[_\-]?(id|key|token)|bearer|credential|^keys?$|^keyids?$|[_\-]key$|"
                       r"[a-z]Key$|[_\-]keyids?$")
_BARE_AUTH = re.compile(r"(?i)\b(Bearer|Basic|Digest)(\s+)([A-Za-z0-9+/=._~\-]{8,})")
# «Pass x/y», «password x» без «=» (формат LoginManager.c:2551 «Login User ID %s/%s, Pass %s/%s» — сейчас вне белого списка)
_WORD_PW = re.compile(r"(?i)\b(pass(?:word|wd|phrase)?|pwd)\b(\s+)(?![=:])([^\s,;]+)")
_LONG_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{48,}(?![0-9A-Za-z])")                   # подписи, ключи, HMAC (md5 32 — остаётся)
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6 = re.compile(r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}(?![0-9a-f:])")
_MAC = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5}(?![0-9A-Fa-f])")
# ★ ревизия 46 Н-2: идентификатор установки клиента (LogDrop inst=, заголовок caddy X-Asda-Install) — того же рода, что MAC
_INSTALL = re.compile(r"(?i)((?<![A-Za-z0-9_])(?:inst|install(?:_?id)?|installid|x-asda-install)\"?\s*[=:]\s*\[?\"?)([0-9A-Fa-f]{16,})")
MASK = "•••"


def _mask_procs(s):
    """В-1: аргументы процедур входа / паролей → «<аргументы скрыты>»; → (строка, замен)."""
    n, pos, out = 0, 0, []
    for m in _PROC_RX.finditer(s):
        if m.start() < pos or not _PROC_SENS.search(m.group(2) or ""):
            continue
        rest = s[m.end():]
        cut = rest.rfind(" :: ")
        tail = rest[cut:] if cut >= 0 else ""
        out.append(s[pos:m.end()] + " <аргументы скрыты>" + tail)
        pos, n = len(s), n + 1
        break                                          # всё до конца строки уже закрыто
    out.append(s[pos:])
    return "".join(out), n


def mask_line(s, show_ip):
    """Строка журнала → (строка без секретов [и адресов], число замен). Секреты — всегда; IP / MAC / ID установки — если show_ip ложно."""
    s, n = _mask_procs(s)

    def _kv(m):
        nonlocal n
        if not _KEY_SENS.search(m.group(2)):
            return m.group(0)
        n += 1
        return m.group(1) + m.group(2) + m.group(1) + m.group(3) + MASK

    s = _KV_RX.sub(_kv, s)

    def _rep3(m):
        nonlocal n
        if MASK in m.group(3):
            return m.group(0)
        n += 1
        return m.group(1) + m.group(2) + MASK

    s = _BARE_AUTH.sub(_rep3, s)
    s = _WORD_PW.sub(_rep3, s)

    def _hex(m):
        nonlocal n
        n += 1
        return "<hex %d>" % len(m.group(0))

    s = _LONG_HEX.sub(_hex, s)
    if not show_ip:
        s, k = _INSTALL.subn(lambda m: m.group(1) + "ID" + MASK, s)
        n += k
        s, k = _IPV4.subn("IP" + MASK, s)
        n += k
        s, k = _MAC.subn("MAC" + MASK, s)
        n += k

        def _v6(m):                                   # время «05:19:24:346» стоковых журналов — не адрес: нужен «::» или буква a-f
            nonlocal n
            g = m.group(0)
            if "::" not in g and not re.search(r"(?i)[a-f]", g):
                return g
            n += 1
            return "IP" + MASK

        s = _IPV6.sub(_v6, s)
    return s, n


# ---------------------------------------------------------------------------------------------------------------- уровень, ссылки
_LV_PATCH_ERR = re.compile(r"\[(ОШИБКА|MISMATCH)\]|ошибк|сбой|не встал|failed|error", re.I)
_LV_PATCH_WARN = re.compile(r"\[ВЫКЛ\]|предупрежд|нарушени|отказ|не поддерживается|warn", re.I)
_LV_GEN_ERR = re.compile(r"exception|error|fail|\bERR\b|ошибк|сбой", re.I)
_LV_GEN_WARN = re.compile(r"\bwarn|warning|\bWRN\b|предупрежд|reject|отказ", re.I)
_LV_EAC = re.compile(r"^\S+ \S+ \[(ERR|WRN|INF|DBG)\]")
_LV_CADDY = re.compile(r"\"level\"\s*:\s*\"(\w+)\"")


def level_of(kind, s):
    """Уровень строки: err / warn / info / debug (разбор по источнику, как пишет его писатель)."""
    if kind == "eac":
        m = _LV_EAC.match(s)
        if m:
            return {"ERR": "err", "WRN": "warn", "INF": "info", "DBG": "debug"}[m.group(1)]
    if kind == "caddy":
        m = _LV_CADDY.search(s)
        if m:
            v = m.group(1).lower()
            return "err" if v in ("error", "fatal", "panic", "dpanic") else "warn" if v == "warn" else "debug" if v == "debug" else "info"
    if kind == "patch":
        return "err" if _LV_PATCH_ERR.search(s) else "warn" if _LV_PATCH_WARN.search(s) else "info"
    return "err" if _LV_GEN_ERR.search(s) else "warn" if _LV_GEN_WARN.search(s) else "info"


# ссылки на карточку: номер учётки (UserIndex / userIdx) — надёжно; имя — только из размеченного поля (CharName, Nick, UserName …) —
# переход в поиск игроков (там видно совпадение), не сразу в карточку
_LINK_UID = re.compile(r"(?i)\b(?:user_?index|useridx)\b\s*[:=]?\s*(\d{1,9})\b")
_LINK_NAME = re.compile(r"(?:\bCharName\t|\bUserName = |\bUserNick |\bNick\t?\s?|\bname=|\baccount=\")([A-Za-z0-9_]{2,20})\b")


def links_of(s):
    """[{"k": "account", "v": номер} | {"k": "name", "v": имя}] — не больше трёх на строку."""
    out, seen = [], set()
    for m in _LINK_UID.finditer(s):
        v = int(m.group(1))
        if v > 0 and ("a", v) not in seen:
            seen.add(("a", v))
            out.append({"k": "account", "v": v})
    for m in _LINK_NAME.finditer(s):
        v = m.group(1)
        if v.lower() not in ("null", "none") and ("n", v.lower()) not in seen:
            seen.add(("n", v.lower()))
            out.append({"k": "name", "v": v})
    return out[:3]


# ---------------------------------------------------------------------------------------------------------------- путь (белый список)
def source(key):
    s = SOURCES.get(key)
    if not s:
        raise OpRefused("неизвестный источник журнала «%s»" % str(key)[:40])
    return s


def procs_of(key):
    return list(source(key)["procs"]())


def _check_name(what, v):
    if not isinstance(v, str) or not NAME_RX.match(v) or v in (".", "..") or ".." in v:
        raise OpRefused("недопустимое имя (%s) — только буквы, цифры, «_», «-», «.» без «..»" % what)
    return v


def _root(src):
    return {"v2": config.STACK_ROOT, "svc": config.SERVICE_ROOT, "data": config.DATA_DIR}[src["root"]]


def _dir_of(key, proc, kind):
    """Папка журнала: корень источника \\ копия \\ подпапка [\\ вид] — только из белого списка; → (абсолютный путь, показ)."""
    src = source(key)
    if proc not in procs_of(key):
        raise OpRefused("копии «%s» у источника «%s» нет" % (str(proc)[:40], key))
    parts = [] if src["root"] in ("svc", "data") else [proc]
    if src["sub"]:
        parts.append(src["sub"])
    if src.get("kinds"):
        _check_name("вид журнала", kind or "")
        if not re.fullmatch(src["kinds"], kind) or kind.lower() in src.get("kinds_skip", ()):
            raise OpRefused("вида журнала «%s» нет в белом списке (Log\\Log_<имя>, кроме Log_Patch и Log_AcJournal — у них свои источники)" % kind)
        parts.append(kind)
    elif kind:
        raise OpRefused("у источника «%s» нет видов журнала" % key)
    if src["root"] == "data":
        parts = ["stack_runs"]
    rel = "\\".join(parts)
    return _root(src) + ("\\" + rel if rel else ""), rel


def _file_ok(key, name):
    _check_name("файл", name or "")
    if not re.fullmatch(source(key)["rx"], name, re.I):
        raise OpRefused("файл «%s» не подходит под шаблон источника «%s»" % (name, key))
    return name


def _local(src):
    return config.get().on_server or src["root"] == "data"


# ---------------------------------------------------------------------------------------------------------------- чтение: служба
def _open_shared(path):
    """Открыть файл на чтение с общим доступом READ | WRITE | DELETE (писатель не встречает отказа) → файловый объект (rb).
    Нарушение общего доступа (писатель держит файл без общего доступа) — OpRefused «занят»; нет файла — OpRefused «нет»."""
    if os.name != "nt":
        return open(path, "rb")
    import ctypes
    import msvcrt
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    GENERIC_READ, SHARE_ALL, OPEN_EXISTING = 0x80000000, 0x1 | 0x2 | 0x4, 3
    h = k32.CreateFileW(path, GENERIC_READ, SHARE_ALL, None, OPEN_EXISTING, 0x80, None)
    if h is None or h == ctypes.c_void_p(-1).value:                   # NULL / INVALID_HANDLE_VALUE
        err = ctypes.get_last_error()
        if err == 32:
            raise OpRefused("файл занят процессом-писателем (открыт им без общего доступа) — повторите через несколько секунд")
        if err in (2, 3):
            raise OpRefused("файла журнала нет (удалён или ещё не создан)")
        raise OpRefused("журнал не открылся (код Windows %d)" % err)
    try:
        fd = msvcrt.open_osfhandle(h, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except OSError:
        k32.CloseHandle(wintypes.HANDLE(h))
        raise OpRefused("журнал не открылся (дескриптор)")
    return os.fdopen(fd, "rb")


def _stat_local(path):
    """(размер, время записи в мс, «сейчас» по часам этой машины в мс) по ПУТИ — os.stat (дескриптор только атрибутов) | None."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as ex:
        raise OpRefused("журнал не прочитан (атрибуты: %s)" % ex)
    return st.st_size, st.st_mtime_ns // 1000000, int(time.time() * 1000)


def _list_local(d, rx, kinds_rx=None, skip=()):
    if not os.path.isdir(d):
        return None, []
    files, kinds = [], []
    try:
        names = os.listdir(d)
    except OSError as ex:
        raise OpRefused("журнал не прочитан (папка: %s)" % ex)
    for nm in names:
        p = os.path.join(d, nm)
        if kinds_rx is not None:
            if re.fullmatch(kinds_rx, nm) and nm.lower() not in skip and os.path.isdir(p):
                kinds.append(nm)
            continue
        if re.fullmatch(rx, nm, re.I) and os.path.isfile(p):
            st = _stat_local(p)                       # не scandir: в записи каталога у открытого писателем файла размер 0
            if st:
                files.append({"name": nm, "size": st[0], "mtime": st[1]})
    return files, sorted(kinds, key=str.lower)


def _read_local(path, start, length, head=0):
    """→ (первые head байт, байты [start, start+length)) — одно открытие, дескриптор закрывается сразу после чтения."""
    with _open_shared(path) as f:
        hb = f.read(head) if head else b""
        f.seek(start)
        return hb, f.read(length)


# ---------------------------------------------------------------------------------------------------------------- чтение: ПК → SSH
def _ps_q(s):
    return "'" + s.replace("'", "''") + "'"


def _remote(script, timeout=90):
    try:
        out = hostshell.powershell(script, timeout)
    except hostshell.HostError as ex:
        raise OpRefused("журнал не прочитан (SSH): %s" % ex)
    if "END|" not in out:
        raise OpRefused("чтение журнала оборвалось (нет метки конца)")
    return [ln.strip() for ln in out.splitlines()]


def _list_remote(d, rx, kinds_rx=None, skip=()):
    ps = ("$d=%s; if (-not (Test-Path -LiteralPath $d -PathType Container)) { Write-Output 'NODIR|'; Write-Output 'END|'; return }; "
          "Get-ChildItem -LiteralPath $d -ErrorAction Stop | ForEach-Object { if ($_.PSIsContainer) { Write-Output ('D|' + $_.Name) } "
          "else { $i = New-Object IO.FileInfo($_.FullName); $i.Refresh(); Write-Output ('F|' + $_.Name + '|' + $i.Length + '|' + "
          "[DateTimeOffset]::new($i.LastWriteTimeUtc).ToUnixTimeMilliseconds()) } }; Write-Output 'END|'" % _ps_q(d))
    lines = _remote(ps)
    if "NODIR|" in lines:
        return None, []
    files, kinds = [], []
    for ln in lines:
        p = ln.split("|")
        if p[0] == "D" and kinds_rx is not None and len(p) > 1 and re.fullmatch(kinds_rx, p[1]) and p[1].lower() not in skip:
            kinds.append(p[1])
        elif p[0] == "F" and kinds_rx is None and len(p) >= 4 and re.fullmatch(rx, p[1], re.I):
            files.append({"name": p[1], "size": int(p[2]), "mtime": int(p[3])})
    return files, sorted(kinds, key=str.lower)


def _stat_remote(path):
    """С ПК: (размер, время записи, «сейчас» по часам СЕРВЕРА) — ревизия 46 С-3: тишина EventLog считается по часам сервера."""
    ps = ("$p=%s; if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { Write-Output 'NONE|' } else { $i = New-Object IO.FileInfo($p); "
          "$i.Refresh(); Write-Output ('S|' + $i.Length + '|' + [DateTimeOffset]::new($i.LastWriteTimeUtc).ToUnixTimeMilliseconds() + '|' + "
          "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) }; Write-Output 'END|'" % _ps_q(path))
    for ln in _remote(ps, 60):
        p = ln.split("|")
        if p[0] == "S" and len(p) >= 4:
            return int(p[1]), int(p[2]), int(p[3])
    return None


def _read_remote(path, start, length, head=0):
    """С ПК по SSH. ★ ревизия 46 С-3: файл читается в память и ЗАКРЫВАЕТСЯ до кодирования и передачи вывода по SSH."""
    ps = ("$p=%s; try { $fs = [IO.File]::Open($p, 'Open', 'Read', 'ReadWrite, Delete') } catch { $h = $_.Exception.HResult -band 0xFFFF; "
          "Write-Output ('E|' + $h); Write-Output 'END|'; return }; $hb = New-Object byte[] %d; $hg = 0; $b = New-Object byte[] %d; $g = 0; "
          "try { while ($hg -lt %d) { $r = $fs.Read($hb, $hg, %d - $hg); if ($r -le 0) { break }; $hg += $r }; [void]$fs.Seek(%d, 'Begin'); "
          "while ($g -lt %d) { $r = $fs.Read($b, $g, %d - $g); if ($r -le 0) { break }; $g += $r } } finally { $fs.Close() }; "
          "Write-Output ('H|' + [Convert]::ToBase64String($hb, 0, $hg)); Write-Output ('B|' + [Convert]::ToBase64String($b, 0, $g)); "
          "Write-Output 'END|'" % (_ps_q(path), head, length, head, head, start, length, length))
    hb, data = None, None
    for ln in _remote(ps, 120):
        p = ln.split("|", 1)
        if p[0] == "E":
            code = int(p[1]) if p[1].isdigit() else -1
            if code == 32:
                raise OpRefused("файл занят процессом-писателем (открыт им без общего доступа) — повторите через несколько секунд")
            if code in (2, 3):
                raise OpRefused("файла журнала нет (удалён или ещё не создан)")
            raise OpRefused("журнал не открылся (код Windows %d)" % code)
        if p[0] == "H":
            hb = base64.b64decode(p[1]) if len(p) > 1 else b""
        if p[0] == "B":
            data = base64.b64decode(p[1]) if len(p) > 1 else b""
    if data is None or hb is None:
        raise OpRefused("журнал не прочитан (нет данных в ответе)")
    return hb, data


# подмена для самотеста: IO = {"list": f, "stat": f, "read": f} | None (настоящие)
IO = None


def _io(src, what):
    if IO and what in IO:
        return IO[what]
    loc = _local(src)
    return {"list": _list_local if loc else _list_remote, "stat": _stat_local if loc else _stat_remote,
            "read": _read_local if loc else _read_remote}[what]


# ---------------------------------------------------------------------------------------------------------------- лимиты
_thr_lock = threading.Lock()
_thr_file = {}                            # (пользователь, нормализованный ключ файла) → время последнего чтения
_thr_user = {}                            # пользователь → [времена запросов]
_budget = {}                              # пользователь | "*" (вся служба) → [(время, байт)]
BYTES_USER_MIN = 32 * 1024 * 1024         # ★ ревизия 46 С-2: байт окна чтения на пользователя в минуту
BYTES_ALL_MIN = 96 * 1024 * 1024          # … и на всю службу в минуту
READERS = 2                               # одновременных чтений журналов на службу
READ_WAIT_S = 8                           # ждать свободного места чтения не дольше
_SEM = threading.BoundedSemaphore(READERS)


class Throttled(OpRefused):
    """Слишком частые / тяжёлые запросы журналов (служба отвечает 429)."""


def norm_key(*parts):
    """★ ревизия 46 С-2: ключ предела «один файл» — без учёта регистра (имена сверяются с re.I, пауза не обходится сменой регистра)."""
    return tuple(str(x or "").lower() for x in parts)


def throttle(user, file_key=None, now=None):
    """Предел частоты: на пользователя PER_MIN в минуту; один файл — не чаще MIN_GAP_S. Превышение — Throttled."""
    now = time.monotonic() if now is None else now
    if file_key is not None:
        file_key = norm_key(*file_key)
    with _thr_lock:
        if len(_thr_user) > 2000:
            for k in [k for k, v in _thr_user.items() if not v or now - v[-1] > 60]:
                _thr_user.pop(k, None)
            for k in [k for k, v in _thr_file.items() if now - v > 60]:
                _thr_file.pop(k, None)
        lst = [t for t in _thr_user.get(user, []) if now - t < 60]
        if len(lst) >= PER_MIN:
            raise Throttled("слишком много запросов журналов — не больше %d в минуту, подождите" % PER_MIN)
        if file_key is not None:
            last = _thr_file.get((user, file_key))
            if last is not None and now - last < MIN_GAP_S:
                raise Throttled("слишком частый опрос журнала — один файл не чаще раза в %d с" % int(MIN_GAP_S))
            _thr_file[(user, file_key)] = now
        lst.append(now)
        _thr_user[user] = lst


def charge(user, nbytes, now=None):
    """★ ревизия 46 С-2: бюджет просканированных байт — BYTES_USER_MIN на пользователя и BYTES_ALL_MIN на всю службу в минуту."""
    now = time.monotonic() if now is None else now
    with _thr_lock:
        for who, cap, text in ((user or "?", BYTES_USER_MIN, "слишком много прочитано журналов за минуту — не больше %d МБ на пользователя, подождите"),
                               ("*", BYTES_ALL_MIN, "служба прочитала слишком много журналов за минуту — не больше %d МБ на всех, подождите")):
            lst = [x for x in _budget.get(who, []) if now - x[0] < 60]
            _budget[who] = lst
            if sum(b for _, b in lst) + nbytes > cap:
                raise Throttled(text % (cap // (1024 * 1024)))
        for who in (user or "?", "*"):
            _budget[who].append((now, nbytes))


# ---------------------------------------------------------------------------------------------------------------- API
def catalog():
    """Источники: ключ, название, копии, кодировка, ротация, как пишется, можно ли «следить», есть ли виды."""
    out = []
    for k, s in SOURCES.items():
        out.append({"key": k, "title": s["title"], "procs": procs_of(k), "kinds": bool(s.get("kinds")), "enc": s["enc"],
                    "rotation": s["rotation"], "how": s["how"], "follow": s["writer"] != "exclusive",
                    "local_only": s["root"] == "data"})
    return {"sources": out, "on_server": config.get().on_server, "limits": {
        "lines_max": LINES_MAX, "line_max": LINE_MAX, "scan_max": SCAN_MAX, "min_gap_s": MIN_GAP_S, "per_min": PER_MIN, "quiet_s": QUIET_S}}


def files(key, proc, kind=None):
    """Файлы журнала копии (новые сверху, не больше FILES_MAX) и виды (для GameServer Log\\Log_*). Папки нет — missing (не «пусто»)."""
    src = source(key)
    if src.get("kinds") and not kind:
        if proc not in procs_of(key):
            raise OpRefused("копии «%s» у источника «%s» нет" % (str(proc)[:40], key))
        base = _root(src) + "\\" + proc + "\\" + src["sub"]
        got, kinds = _io(src, "list")(base, src["rx"], src["kinds"], src.get("kinds_skip", ()))
        return {"source": key, "proc": proc, "kind": None, "dir": proc + "\\" + src["sub"], "missing": got is None, "kinds": kinds,
                "files": [], "more": False}
    d, rel = _dir_of(key, proc, kind)
    got, _ = _io(src, "list")(d, src["rx"])
    if got is None:
        return {"source": key, "proc": proc, "kind": kind, "dir": rel, "missing": True, "kinds": [], "files": [], "more": False,
                "note": "папки на машине службы нет — прогоны restart_stack пишутся на ПК, где он шёл (консоль: logs tail stack_runs …)"
                if src["root"] == "data" and config.get().on_server else None}
    got.sort(key=lambda x: (x["mtime"], x["name"]), reverse=True)
    return {"source": key, "proc": proc, "kind": kind, "dir": rel, "missing": False, "kinds": [], "files": got[:FILES_MAX],
            "more": len(got) > FILES_MAX, "total": len(got)}


def _is_utf16(head):
    """★ ревизия 46 Н-4: UTF-16 LE — метка FF FE или NUL в нечётных байтах начала файла."""
    if head.startswith(b"\xff\xfe"):
        return True
    odd = head[1::2]
    return len(odd) >= 8 and odd.count(0) * 10 >= len(odd) * 8


def _decode(raw, enc, utf16=False):
    """Байты → строки: UTF-16 — целиком до разбиения; иначе каждая строка — UTF-8, не вышло — запасная кодировка источника
    (cp1251 наших DLL / cp949 стока)."""
    if utf16:
        t = raw.decode("utf-16-le", "replace").lstrip("\ufeff")
        return [x.rstrip("\r") for x in t.split("\n")]
    out = []
    for b in raw.split(b"\n"):
        b = b.rstrip(b"\r")
        try:
            out.append(b.decode("utf-8"))
        except UnicodeDecodeError:
            out.append(b.decode(enc, "replace"))
    return out


def _last_nl(raw, utf16):
    """Индекс конца последнего перевода строки (+1 — длина целых строк) или 0."""
    if not utf16:
        return raw.rfind(b"\n") + 1
    i = len(raw)
    while True:
        i = raw.rfind(b"\n\x00", 0, i)
        if i < 0:
            return 0
        if i % 2 == 0:
            return i + 2


def head_fp(head, upto):
    """★ ревизия 46 Н-1: отпечаток начала файла — первые min(64, upto) байт (у дописываемого файла не меняются)."""
    import hashlib
    return hashlib.md5(head[:max(0, min(HEAD, upto))]).hexdigest()[:12]


HEAD = 64


def _clip(s):
    s = "".join(ch if ch >= " " or ch == "\t" else "·" for ch in s)       # управляющие символы недоверенного текста — точкой
    return s if len(s) <= LINE_MAX else s[:LINE_MAX] + "…[+%d]" % (len(s) - LINE_MAX)


def _want(lv, level):
    if not level:
        return True
    return LEVELS.index(lv) <= LEVELS.index(level)


def tail(key, proc, name, kind=None, lines=LINES_DEF, q=None, level=None, scan=None, since=None, sig=None, show_ip=False, now_ms=None,
         head=None, user=None):
    """Хвост файла журнала (см. шапку). since + sig (+ head — отпечаток начала) — опрос «следить»: тот же «размер:время» — unchanged без
    открытия данных; прирост — только новые целые строки; файл стал короче или его начало другое (переписан) — заново хвост (reset).
    user — для бюджета байт (charge); чтение и разбор — под общим семафором службы (READERS). → словарь ответа."""
    src = source(key)
    d, rel = _dir_of(key, proc, kind)
    _file_ok(key, name)
    path = d + "\\" + name
    try:
        lines = max(1, min(LINES_MAX, int(lines or LINES_DEF)))
        scan = max(16 * 1024, min(SCAN_MAX, int(scan or (SCAN_MAX if (q or level) else SCAN_DEF))))
    except (TypeError, ValueError):
        raise OpRefused("число строк и окно — целые")
    if level and level not in LEVELS:
        raise OpRefused("уровень — один из err, warn, info, debug")
    q = (q or "").strip()[:200]
    exclusive = src["writer"] == "exclusive"
    if since is not None and exclusive:
        raise OpRefused("«следить» за Event\\EventLog.txt нельзя: процесс пишет его без общего доступа — откройте хвост вручную")
    st = _io(src, "stat")(path)
    if st is None:
        raise OpRefused("файла журнала нет (удалён или ещё не создан)")
    size, mtime = st[0], st[1]
    srv_now = st[2] if len(st) > 2 else None
    cur_sig = "%d:%d" % (size, mtime)
    base = {"source": key, "proc": proc, "kind": kind, "file": name, "path": rel + "\\" + name if rel else name, "size": size,
            "mtime": mtime, "sig": cur_sig, "exclusive": exclusive, "ip_masked": not show_ip, "lines": [], "masked": 0,
            "unchanged": False, "reset": False, "skipped": 0, "truncated": False, "head": head}
    if since is not None:
        try:
            since = int(since)
        except (TypeError, ValueError):
            raise OpRefused("отметка «следить» — целое")
        if sig == cur_sig:
            return dict(base, unchanged=True, offset=since)                 # данные не открывались
    if exclusive:
        now = now_ms if now_ms is not None else srv_now if srv_now is not None else int(time.time() * 1000)   # С-3: часы сервера
        age = (now - mtime) / 1000.0
        if age < QUIET_S:
            raise OpRefused("Event\\EventLog.txt писался %d с назад — его пишет процесс без общего доступа, откройте через %d с"
                            % (max(0, int(age)), QUIET_S))
    if not _SEM.acquire(timeout=READ_WAIT_S):
        raise Throttled("служба занята чтением журналов (одновременно не больше %d) — повторите через несколько секунд" % READERS)
    try:
        return _tail_body(src, path, base, size, scan, lines, q, level, since, head, show_ip, user)
    finally:
        _SEM.release()


SCAN_FILE_MAX = 16 * 1024 * 1024          # ★ 22.11: scan — файл целиком не больше (журнал шлюза gp7 ~7–9 МБ в сутки)


def stat(key, proc, name, kind=None):
    """★ 22.11: (размер, время записи в мс) файла журнала из белого списка (путь — _dir_of / _file_ok, атрибуты — по пути) или None —
    файла нет. Список файлов (files) для этого не годится: он обрезан FILES_MAX новыми файлами всех видов."""
    src = source(key)
    d, _rel = _dir_of(key, proc, kind)
    _file_ok(key, name)
    st = _io(src, "stat")(d + "\\" + name)
    return None if st is None else (st[0], st[1])


def scan(key, proc, name, kind=None, needles=(), show_ip=False, user=None, size=None):
    """★ 22.11 (сверка «Оплачено, не выдано», domains/money.py): ВЕСЬ файл журнала из белого списка — строки, где есть одна из
    подстрок needles (константы вызывающего кода, не ввод пользователя), уже замаскированные mask_line. Путь — только _dir_of / _file_ok,
    чтение — теми же _io (общий доступ, файл закрывается сразу), кусками по SCAN_MAX, под семафором службы и бюджетом байт charge.
    size — размер из листинга (без лишнего stat по SSH). Файла нет — missing. → {"lines", "size", "mtime", "missing", "truncated"}."""
    src = source(key)
    d, _rel = _dir_of(key, proc, kind)
    _file_ok(key, name)
    if src["writer"] == "exclusive":
        raise OpRefused("журнал «%s» пишется без общего доступа — целиком не читается" % key)
    path = d + "\\" + name
    mtime = None
    if size is None:
        st = _io(src, "stat")(path)
        if st is None:
            return {"lines": [], "size": 0, "mtime": None, "missing": True, "truncated": False}
        size, mtime = st[0], st[1]
    total = min(size, SCAN_FILE_MAX)
    if not _SEM.acquire(timeout=READ_WAIT_S):
        raise Throttled("служба занята чтением журналов (одновременно не больше %d) — повторите через несколько секунд" % READERS)
    try:
        charge(user, total + HEAD)
        rd = _io(src, "read")
        out, carry, pos, utf16 = [], b"", 0, False
        while pos < total:
            hb, raw = rd(path, pos, min(SCAN_MAX, total - pos), HEAD if pos == 0 else 0)
            if pos == 0:
                utf16 = _is_utf16(hb)
            if not raw:
                break
            pos += len(raw)
            raw = carry + raw
            cut = _last_nl(raw, utf16) if pos < total else len(raw)
            carry = raw[cut:]
            for t in _decode(raw[:cut], src["enc"], utf16):
                # подстроки — константы кода (не поиск пользователя): отбор до маски не открывает секретов, маска — у каждой отобранной
                if any(n in t for n in needles):
                    out.append(mask_line(t, show_ip)[0])
    finally:
        _SEM.release()
    return {"lines": out, "size": size, "mtime": mtime, "missing": False, "truncated": size > SCAN_FILE_MAX}


def _tail_body(src, path, base, size, scan, lines, q, level, since, head, show_ip, user):
    rd = _io(src, "read")
    follow = since is not None and 0 <= since <= size
    texts, start, offset, hb, utf16 = [], 0, size, b"", False
    if follow:
        start = since if size - since <= FOLLOW_MAX else size - FOLLOW_MAX
        charge(user, size - start + HEAD)
        hb, raw = rd(path, start, size - start, HEAD)
        utf16 = _is_utf16(hb)
        if head and head_fp(hb, since) != head:                              # Н-1: начало другое — файл переписан
            follow = False
        else:
            if utf16 and start % 2:
                raw, start = raw[1:], start + 1
            skipped = start - since
            cut = _last_nl(raw, utf16)
            offset = start + cut
            texts = _decode(raw[:cut], src["enc"], utf16) if cut else []
            if texts and texts[-1] == "":
                texts.pop()
            if skipped and texts:
                texts = texts[1:]                                             # первая строка после пропуска — обрывок
            base["skipped"] = skipped
    if not follow:
        start = max(0, size - scan)
        charge(user, size - start + HEAD)
        hb, raw = rd(path, start, size - start, HEAD)
        utf16 = _is_utf16(hb)
        if utf16 and start % 2:
            raw, start = raw[1:], start + 1
        texts = _decode(raw, src["enc"], utf16)
        if start > 0 and texts:
            texts = texts[1:]                                                 # первая строка окна — обрывок
        if texts and texts[-1] == "":
            texts.pop()
        offset = size
        base["reset"] = since is not None
    base["head"] = head_fp(hb, offset)
    base["utf16"] = utf16
    ql = q.lower()
    picked, total_masked = [], 0
    for t in texts:
        t, n = mask_line(t, show_ip)
        total_masked += n
        lv = level_of(src["lv"], t)
        if not _want(lv, level):
            continue
        if ql and ql not in t.lower():
            continue
        picked.append((t, lv))
    base["matched"] = len(picked)
    base["truncated"] = len(picked) > lines or (not follow and start > 0)
    picked = picked[-lines:]
    out, used = [], 0
    for t, lv in reversed(picked):
        t = _clip(t)
        used += len(t) + 1
        if used > OUT_MAX:
            base["truncated"] = True
            break
        out.append({"t": t, "lv": lv, "ln": links_of(t)})
    out.reverse()
    base.update(lines=out, masked=total_masked, offset=offset, scan_start=start)
    return base
