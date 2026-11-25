# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""patchcfg_src.py — КАТАЛОГ ключей ini наших серверных DLL по ИСХОДНИКАМ (шаг А5.5 «patches.ini и конфиги», 21.11.2026; разбор
Reports/admin_center/impl_a5_live_20261121.md §«А5.5»; ★ ревизия 45 — §«А5.5 — исправления по ревизии 45»).

Источник правды — сами исходники DLL:
  * какие файлы собираются в DLL — список «cl … *.cpp» её build.bat (★ ревизия 45 С-1: AcJournal.cpp, Log.cpp, Hook.cpp из
    ..\\AsdaPatch\\src собираются и в AddonNPC / LoginPatch / DBPatch; patches_db AsdaPatch в AsdaPatch не собирается); каталоги «/I» —
    заголовки с константами;
  * Config.cpp — декларативный шаблон ini (IniKey / IniSection kSections: секции, ключи, умолчания, комментарии; Version = kVersion
    Config.h). Этот же шаблон DLL дописывает в живой ini при старте (Config::MergeMissing — только недостающие ключи, существующие
    значения не трогает; Version поднимается до kVersion);
  * места чтения — Config::GetInt / GetBool / GetStr(секция, ключ, умолчание …) во всех собираемых файлах: тип ключа, файл и строка;
    предел значения (★ ревизия 45 С-1 / В-3) — Clamp(…, a, b), маска «& Nu», «… ? 1 : 0», тернарный предел «x = x < a ? a : (x > b ? b :
    x)», условия «if (x < a || x > b || x == c)» с числами и с constexpr-константами файла и заголовков (kHardMax, kStockSlots,
    kOpenHardMax, AsdaWire::kMaxSlots…) и с несколькими прочитанными переменными в одном условии (P120 MineMap / ExitTo / Range /
    RefuseCode). Тело условия определяет смысл: присваивание переменной — значение вне предела заменяется (предел), «return
    PatchResult::Failed» — патч не встанет (предел), «return PatchResult::Disabled» — значение ВЫКЛЮЧАЕТ патч (off_when: P30 MaxMaps ≤ 23);
    «==» в отвергающем условии — недопустимое значение (P40 RefuseCode = 1). Ключи, читаемые циклом по построенным именам, — ручная
    таблица MANUAL (с местом в коде);
  * длина строки (★ ревизия 45 Н-6) — размер буфера GetStr (ARRAYSIZE(buf) / число / MAX_PATH): длиннее — DLL молча обрежет;
  * «только просмотр» по типу значения (★ ревизия 45 В-4): буфер GetStr идёт в строку подключения (DRIVER= / SERVER= / UID= / DSN=),
    в путь файла (CreateFileW / GetPrivateProfile* / GetFullPathNameW / _wfopen) или в адрес (inet_* / getaddrinfo); умолчание шаблона —
    адрес, «хост,порт», путь или строка подключения;
  * зависимости — (а) вызовы символов другого патча (P25_RunRecalc в P127, L04c_* в L09…): сведения; (б) ★ ревизия 45 В-2 — чтение
    ЧУЖОЙ секции (Config::Get*(L"P47_…", …) в файле P55): «if (!GetBool(чужая, Enabled)) return Failed / Disabled» — ЖЁСТКАЯ (выключение
    поставщика снимает пользователя), прочие — сведения с ключом. Файл → секция — по реестру патчей (Registry.cpp: {L"секция", …,
    &Функция}) и определению функции в файле; без него — по номеру в имени файла (p55_… → P55_…), затем по константе секции файла.
Описание секции — строки реестра AstoryServer/Docs/INDEX.md с «**<номер>**» (P40, L09, N24…) и ссылка на документ.

Каталог строится на ПК (исходники и реестр есть только там) и кладётся выкладчиком службы в data/ref/patchcfg_catalog.json (служба на
сервере исходников не видит). Только чтение файлов. Побочных эффектов при импорте нет.
"""
import glob
import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))       # AstoryAdminCenter
PORT = os.path.dirname(HERE)                            # port
PATCHES = os.path.join(PORT, "AstoryServer", "Patches")
INDEX_MD = os.path.join(PORT, "AstoryServer", "Docs", "INDEX.md")
CATALOG_REF = os.path.join(HERE, "data", "ref", "patchcfg_catalog.json")

# DLL → (файл ini от папки процесса, семья копий панели, подпапка исходников). Семьи: GSP — все GameServer (поле, Indun, Ch2; правка
# парами «поле = Ch2», у Indun своя база), NPCP — все NpcServer (так же), LM — LoginManager, DBM — DBManager, SDB — RelayServer ×3 +
# ItemRelayServer + OperationServer (srvdbpatch.ini; живой листинг 21.11 — 5 копий 5762 б).
DLLS = {
    "AsdaPatch":  ("ConfigSet\\patches.ini", "GSP"),
    "AddonNPC":   ("ConfigSet\\patches.ini", "NPCP"),
    "LoginPatch": ("ConfigSet\\patches.ini", "LM"),
    "DBPatch":    ("ConfigSet\\dbpatch.ini", "DBM"),
    "SrvDbPatch": ("ConfigSet\\srvdbpatch.ini", "SDB"),
}

# ★ ревизия 45 С-1: ключи, которые DLL читает циклом по ПОСТРОЕННЫМ именам (поиск чтения по литералу их не видит) — тип и предел по
#   коду цикла: (DLL, секция, шаблон ключа) → (тип, lo, hi, где, правило). Правило «p69_stages» проверяет область (cs_kinds/patchcfg).
MANUAL = [
    ("AsdaPatch", "P55_PacketValidator", r"Rate\w+PerSec", "int", 0, 10000, "p55_packet_validator.cpp:438-441 (цикл kRateKeys: < 0 → 0, "
     "> 10000 → 10000)", None),
    ("AsdaPatch", "P55_PacketValidator", r"Rate\w+Burst", "int", 1, 100000, "p55_packet_validator.cpp:439-443 (цикл kRateKeys: < 1 → 1, "
     "> 100000 → 100000)", None),
    ("AsdaPatch", "P63_InFlightLock", r"Lock\d+", "bool", 0, 1, "p63_inflight_lock.cpp:602 (цикл kFam: GetBool)", None),
    ("AsdaPatch", "P69_IntegrityAutoBlock", r"Stage[123]Count", "int", 1, None, "p69_integrity_autoblock.cpp:419-430 (порог ≥ 1 и по "
     "возрастанию ступеней, иначе ВСЕ ступени — умолчания 20/24, 50/720, 51/-1)", "p69_stages"),
    ("AsdaPatch", "P69_IntegrityAutoBlock", r"Stage[123]Hours", "int", -1, None, "p69_integrity_autoblock.cpp:419-430 (срок ≠ 0 и ≥ -1, "
     "иначе ВСЕ ступени — умолчания)", "p69_stages"),
    ("AsdaPatch", "P64_StatePreamble", r"(Mask|Opcodes)(Economy|Pets|Combat|Fishing|Quest|Misc)", "str", None, None,
     "p64_state_preamble.cpp:374-376 (цикл kFam, буфер 1024; неизвестные слова маски молча пропускаются, пустая маска снимает запреты)",
     "maxlen:1023"),
    ("AsdaPatch", "P88_TitleEvents", r"Threshold\d+", "int", 1, 1000000, "p88_title_events.cpp:664-668 (цикл g_goals: вне 1…1000000 — "
     "умолчание)", None),
    ("AsdaPatch", "P88_TitleEvents", r"(PotionCodes|TicketCodes|Zones\w+)", "str", None, None, "p88_title_events.cpp:619-643 (ReadRanges / "
     "ReadZones, буфер 512; не разобрано — умолчание)", "maxlen:511"),
]

# ---------------------------------------------------------------------------------------------------------------------
# Разбор C++ (минимальный лексер: строки L"…", идентификаторы, числа, знаки; комментарии // и /* */ пропускаются)
# ---------------------------------------------------------------------------------------------------------------------
_ESC = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0"}


def _lex(text):
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n﻿":
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == '"' or (c == "L" and i + 1 < n and text[i + 1] == '"'):
            i += 2 if c == "L" else 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    e = text[i + 1]
                    if e == "x":
                        m = re.match(r"[0-9a-fA-F]+", text[i + 2:i + 6])
                        buf.append(chr(int(m.group(0), 16)) if m else "x")
                        i += 2 + (len(m.group(0)) if m else 0)
                        continue
                    buf.append(_ESC.get(e, e))
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            out.append(("s", "".join(buf)))
            i += 1
        elif c.isalpha() or c == "_":
            m = re.match(r"[A-Za-z_]\w*", text[i:i + 200])
            out.append(("i", m.group(0)))
            i += len(m.group(0))
        elif c.isdigit():
            m = re.match(r"\w+", text[i:i + 60])
            out.append(("n", m.group(0)))
            i += len(m.group(0))
        else:
            out.append(("p", c))
            i += 1
    return out


def _groups(toks, start):
    """С позиции «{» → (список групп верхнего уровня «{ … }», позиция после закрывающей «}»)."""
    assert toks[start] == ("p", "{")
    depth, i, groups, cur = 0, start, [], None
    while i < len(toks):
        t = toks[i]
        if t == ("p", "{"):
            depth += 1
            if depth == 2:
                cur = []
            elif depth > 2:
                cur.append(t)
        elif t == ("p", "}"):
            depth -= 1
            if depth == 1:
                groups.append(cur)
                cur = None
            elif depth == 0:
                return groups, i + 1
            else:
                cur.append(t)
        elif cur is not None:
            cur.append(t)
        i += 1
    raise ValueError("незакрытая «{»")


def _fields(group):
    """Поля группы по запятым верхнего уровня → [[токены]]."""
    out, cur, depth = [], [], 0
    for t in group:
        if t in (("p", "("), ("p", "{")):
            depth += 1
        elif t in (("p", ")"), ("p", "}")):
            depth -= 1
        if t == ("p", ",") and depth == 0:
            out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def _str(field):
    """Поле из строк (склейка «L"…" L"…"») или nullptr → текст | None."""
    if not field or field == [("i", "nullptr")] or field == [("n", "0")]:
        return None
    if all(t[0] == "s" for t in field):
        return "".join(t[1] for t in field)
    return None


def parse_config(path):
    """Config.cpp → (секции [{name, comment, keys: [{key, def, comment}]}], kVersion из Config.h | None)."""
    text = open(path, encoding="utf-8-sig", errors="replace").read()
    toks = _lex(text)
    arrays, sections = {}, None
    i = 0
    while i < len(toks) - 4:
        t = toks[i]
        if t == ("i", "IniKey") and toks[i + 1][0] == "i" and toks[i + 2] == ("p", "[") and toks[i + 3] == ("p", "]"):
            name = toks[i + 1][1]
            j = i + 4
            while toks[j] != ("p", "{"):
                j += 1
            groups, i = _groups(toks, j)
            keys = []
            for g in groups:
                f = _fields(g)
                if len(f) >= 2 and _str(f[0]) is not None:
                    keys.append({"key": _str(f[0]), "def": _str(f[1]) if _str(f[1]) is not None else "",
                                 "comment": _str(f[2]) if len(f) > 2 else None})
            arrays[name] = keys
            continue
        if t == ("i", "IniSection") and toks[i + 1] == ("i", "kSections"):
            j = i + 2
            while toks[j] != ("p", "{"):
                j += 1
            groups, i = _groups(toks, j)
            sections = []
            for g in groups:
                f = _fields(g)
                if len(f) < 3:
                    continue
                arr = next((x[1] for x in f[2] if x[0] == "i"), None)
                sections.append({"name": _str(f[0]), "comment": _str(f[1]), "keys": [dict(k) for k in arrays.get(arr, [])],
                                 "array": arr})
            continue
        i += 1
    if sections is None:
        raise ValueError("%s: нет kSections" % path)
    ver = None
    h = os.path.join(os.path.dirname(path), "Config.h")
    if os.path.isfile(h):
        m = re.search(r"constexpr\s+int\s+kVersion\s*=\s*(\d+)", open(h, encoding="utf-8-sig", errors="replace").read())
        ver = int(m.group(1)) if m else None
    for s in sections:                                         # ★ ревизия 45 (мелочь): Version — выражение в шаблоне, умолчание = kVersion
        for k in s["keys"]:
            if s["name"] == "General" and k["key"] == "Version" and not k["def"] and ver is not None:
                k["def"] = str(ver)
    return sections, ver


# ---------------------------------------------------------------------------------------------------------------------
# Что собирается в DLL (build.bat) и константы
# ---------------------------------------------------------------------------------------------------------------------
def dll_sources(dll):
    """→ (файлы .cpp, которые собирает build.bat DLL — абсолютные пути, каталоги «/I»). Без build.bat — src/**/*.cpp и src."""
    root = os.path.join(PATCHES, dll)
    bat = os.path.join(root, "build.bat")
    files, incs = [], []
    if os.path.isfile(bat):
        for ln in open(bat, encoding="utf-8", errors="replace"):
            s = ln.strip()
            if s.lower().startswith(("rem", "echo", "::")):
                continue
            for m in re.finditer(r"/I\s+(\S+)", s):
                incs.append(os.path.normpath(os.path.join(root, m.group(1).replace("\\", os.sep))))
            for tok in re.findall(r"[\w\.\\/\*\-]+\.cpp\b", s):
                for p in sorted(glob.glob(os.path.join(root, tok.replace("\\", os.sep)))):
                    p = os.path.normpath(p)
                    if p not in files:
                        files.append(p)
    if not files:
        src = os.path.join(root, "src")
        files = [p for p in sorted(glob.glob(os.path.join(src, "**", "*.cpp"), recursive=True)) if ".bak" not in p]
        incs = [src]
    incs = list(dict.fromkeys(incs + [os.path.dirname(p) for p in files]))
    return files, incs


_CONST = re.compile(r"\b(?:static\s+)?(?:constexpr|const)\s+(?:unsigned\s+|signed\s+)?(?:int|DWORD|WORD|BYTE|UINT|LONG|long|short|size_t|"
                    r"uint32_t|int32_t|uint16_t|int16_t|unsigned|char)\s+(\w+)\s*=\s*(-?(?:0x[0-9A-Fa-f]+|\d+))[uUlL]*\s*[;,]")
_DEFINE = re.compile(r"^\s*#\s*define\s+(\w+)\s+\(?(-?(?:0x[0-9A-Fa-f]+|\d+))[uUlL]*\)?\s*$", re.M)
BUILTIN_CONSTS = {"MAX_PATH": 260}


def file_consts(text):
    out = {}
    for rx in (_CONST, _DEFINE):
        for m in rx.finditer(text):
            out.setdefault(m.group(1), int(m.group(2), 0))
    return out


def all_consts(files, incs):
    """{имя: {значения}} по собираемым файлам и заголовкам каталогов «/I» (имя без пространства имён)."""
    out = {}
    paths = list(files)
    for d in incs:
        paths += sorted(glob.glob(os.path.join(d, "*.h")))
    for p in dict.fromkeys(paths):
        if ".bak" in p or not os.path.isfile(p):
            continue
        for k, v in file_consts(open(p, encoding="utf-8-sig", errors="replace").read()).items():
            out.setdefault(k, set()).add(v)
    for k, v in BUILTIN_CONSTS.items():
        out.setdefault(k, set()).add(v)
    return out


def _num(tok, fc, gc):
    """Число или константа (файла, затем общая — если значение одно) → int | None."""
    t = (tok or "").strip().strip("()").strip()
    t = re.sub(r"(?<=[0-9A-Fa-f])[uUlL]+$", "", t)
    if re.fullmatch(r"-?(?:0x[0-9A-Fa-f]+|\d+)", t):
        return int(t, 0)
    if not re.fullmatch(r"[A-Za-z_][\w:]*", t):
        return None
    name = t.split("::")[-1]
    if name in fc:
        return fc[name]
    vs = gc.get(name)
    return next(iter(vs)) if vs and len(vs) == 1 else None


# ---------------------------------------------------------------------------------------------------------------------
# Места чтения ключей и пределы
# ---------------------------------------------------------------------------------------------------------------------
_READ = re.compile(r'Config::Get(Int|Bool|Str)\s*\(\s*(L"([^"]+)"|(\w+))\s*,\s*L"([^"]+)"\s*,\s*')
_ASSIGN_SEC = r'\b%s\s*(?:\[\s*\])?\s*=\s*L"([^"]+)"'
_CLAMP = re.compile(r'Clamp\s*\(\s*(?:\(\w+\)\s*)?Config::GetInt\s*\([^)]*\)\s*,\s*([\w:\-]+)\s*,\s*([\w:\-]+)\s*\)')
_MASK = re.compile(r'Config::GetInt\s*\([^)]*\)\s*&\s*(0x[0-9a-fA-F]+|\d+)u?')
_BOOLISH = re.compile(r'Config::GetInt\s*\([^)]*\)\s*(?:==\s*1\s*)?\?\s*1\s*:\s*0')
_VAR = re.compile(r'([A-Za-z_][\w\.]*(?:\[\w*\])?(?:->\w+)?)\s*=\s*(?:\(\w+\)\s*)?Config::Get(?:Int|Bool)\s*\(')
_HINT = re.compile(r'(?:[Дд]опустим[оы]|[Дд]иапазон|[Пп]редел)\s*:?\s*(-?\d+)\s*(?:\.\.\.|…|\.\.|–|-)\s*(-?\d+)')
_TERM = re.compile(r"^\(*\s*([A-Za-z_][\w\.]*(?:->\w+)?)\s*(<=|>=|<|>|==)\s*([\w:\-]+)\s*\)*$")
_TERM_R = re.compile(r"^\(*\s*([\w:\-]+)\s*(<=|>=|<|>|==)\s*([A-Za-z_][\w\.]*(?:->\w+)?)\s*\)*$")
_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "=="}
_STR_ARGS = re.compile(r'Config::GetStr\s*\([^;]*?,\s*(\w+)\s*,\s*(ARRAYSIZE\s*\(\s*\w+\s*\)|_countof\s*\(\s*\w+\s*\)|[\w:]+)\s*\)')
_CONN_FMT = re.compile(r"(DRIVER|SERVER|DATABASE|UID|PWD|DSN|Data Source|Initial Catalog|User ID)\s*=", re.I)
_PATH_SINK = re.compile(r"\b(CreateFileW|CreateFileA|GetPrivateProfile\w+|WritePrivateProfile\w+|GetFullPathNameW|_wfopen\w*|fopen\w*|"
                        r"PathCombineW|GetFileAttributesW|CreateDirectoryW|SHCreateDirectory\w*|LoadLibraryW|DeleteFileW|MoveFile\w*)\s*\(")
_ADDR_SINK = re.compile(r"\b(inet_pton|InetPtonW|inet_addr|getaddrinfo|GetAddrInfoW|WSAStringToAddressW)\s*\(")


def _short(var):
    return re.split(r"\.|->", var.split("[")[0])[-1] if var else var


def _paren(text, start):
    """text[start] = «(» → (содержимое, позиция после «)») | (None, None). Строки "…" пропускаются (скобки в тексте журнала)."""
    depth, j, n = 0, start, len(text)
    while j < n:
        c = text[j]
        if c == '"':
            j += 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:j], j + 1
        j += 1
    return None, None


def _nocomment(ln):
    """Строка без «// …» вне строковых литералов."""
    q = False
    for j, c in enumerate(ln):
        if c == '"' and (j == 0 or ln[j - 1] != "\\"):
            q = not q
        elif not q and ln.startswith("//", j):
            return ln[:j]
    return ln


def _split_top(s, sep):
    out, depth, cur, i = [], 0, [], 0
    while i < len(s):
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if depth == 0 and s.startswith(sep, i):
            out.append("".join(cur))
            cur = []
            i += len(sep)
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def _strip_logs(body):
    """Тело без вызовов Log::Line(…) / Log::… и комментариев — для классификации."""
    out, i = [], 0
    body = re.sub(r"//[^\n]*", " ", body)
    while i < len(body):
        m = re.match(r"(?:Log::\w+|OutputDebugString\w*|DbgLog\w*)\s*\(", body[i:])
        if m:
            _in, end = _paren(body, i + m.end() - 1)
            if end is None:
                break
            i = end
            while i < len(body) and body[i] in " \t\r\n;":
                i += 1
            continue
        out.append(body[i])
        i += 1
    return " ".join("".join(out).split())


def _body_kind(body, var):
    """Классификация тела условия → 'fail' | 'off' | 'clamp' | None (только простые тела: присваивания и return PatchResult)."""
    b = _strip_logs(body).strip()
    if b.startswith("{") and b.endswith("}"):
        b = b[1:-1].strip()
    if not b:
        return None
    m = re.fullmatch(r"(?:[\w\.\[\]>\-]+\s*=\s*[^;=][^;]*;\s*)*return\s+PatchResult::(Failed|Disabled)\s*;", b)
    if m:
        return "fail" if m.group(1) == "Failed" else "off"
    if re.fullmatch(r"(?:[\w\.\[\]>\-]+\s*=\s*[^;=][^;]*;\s*)+", b):
        names = {_short(x) for x in re.findall(r"([\w\.\[\]>\-]+)\s*=\s*[^=]", b)}
        if var in names or any(n.lower().endswith("ok") for n in names):
            return "clamp"
    return None


def _func_end(line):
    return line.startswith("}") or bool(re.match(r"^(?:PatchResult|static|void|bool|int|DWORD|BOOL|extern)\b.*\)\s*(?:\{.*)?$", line))


def analyze(lines, i, reads_pos, fc, gc):
    """Пределы ключа, прочитанного в строке i: reads_pos [(строка, переменная, ключ)] — чтения в окне; условие относится к ПОСЛЕДНЕМУ
    чтению переменной до него (переменную прочитали заново — дальше не её предел). → {ключ: {lo, hi, excl, off: [(оп, число, строка)],
    how}} только для чтений строки i. Окно — до 40 строк после чтения, до конца функции."""
    out = {}
    mine = {v for ln_, v, _k in reads_pos if ln_ == i}

    def gov(var, at):
        """Ключ чтения var, действующего в строке at (последнее чтение не позже at) → ключ | None (не строки i — None)."""
        best = None
        for ln_, v, k_ in reads_pos:
            if v == var and ln_ <= at and (best is None or ln_ > best[0]):
                best = (ln_, k_)
        return best[1] if best and best[0] == i else None

    reads_here = {v: True for v in mine}

    def put(key, op, v, kind, ln):
        e = out.setdefault(key, {"lo": None, "hi": None, "excl": [], "off": [], "how": set()})
        if kind == "off":
            e["off"].append((op, v, ln + 1))
            e["how"].add("выключает (строка %d)" % (ln + 1))
            return
        if op == "<":
            e["lo"] = v if e["lo"] is None else max(e["lo"], v)
        elif op == "<=":
            e["lo"] = v + 1 if e["lo"] is None else max(e["lo"], v + 1)
        elif op == ">":
            e["hi"] = v if e["hi"] is None else min(e["hi"], v)
        elif op == ">=":
            e["hi"] = v - 1 if e["hi"] is None else min(e["hi"], v - 1)
        elif op == "==":
            e["excl"].append(v)
        e["how"].add(("не встанет" if kind == "fail" else "заменяется") + " (строка %d)" % (ln + 1))

    k = i
    end = min(len(lines), i + 40)
    while k < end:
        ln = _nocomment(lines[k])
        if k > i and _func_end(ln):
            break
        # тернарный предел: «x = x < A ? A : (x > B ? B : x)» (в т. ч. на строке чтения после «;»)
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*=\s*\1\s*(<=|<|>=|>)", ln):
            var = m.group(1)
            key = gov(var, k) if var in reads_here else None
            if not key:
                continue
            rhs = ln[m.start():].split(";", 1)[0]
            lo_done = hi_done = False
            for t in re.finditer(r"\b%s\s*(<=|<|>=|>)\s*([\w:\-]+)\s*\?\s*\(?\s*([\w:\-]+)" % re.escape(var), rhs):
                op, mapped = t.group(1), _num(t.group(3), fc, gc)
                if mapped is None:
                    continue
                e = out.setdefault(key, {"lo": None, "hi": None, "excl": [], "off": [], "how": set()})
                if op in ("<", "<=") and not lo_done:
                    e["lo"] = mapped if e["lo"] is None else max(e["lo"], mapped)
                    e["how"].add("тернарный предел (строка %d)" % (k + 1))
                    lo_done = True
                elif op in (">", ">=") and not hi_done:
                    e["hi"] = mapped if e["hi"] is None else min(e["hi"], mapped)
                    e["how"].add("тернарный предел (строка %d)" % (k + 1))
                    hi_done = True
        m = re.search(r"\bif\s*\(", ln)
        if not m:
            k += 1
            continue
        text = " ".join(_nocomment(x) for x in lines[k:min(len(lines), k + 30)])
        st = text.find("(", m.start())
        cond, after = _paren(text, st)
        if cond is None:
            k += 1
            continue
        rest = text[after:].lstrip()
        if rest.startswith("{"):
            depth, j = 0, 0
            for j, c in enumerate(rest):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
            body = rest[:j + 1]
        else:
            body = rest.split(";", 1)[0] + ";"
        for term in _split_top(cond, "||"):
            term = term.strip()
            if "&&" in term:
                continue                               # «и» внутри слагаемого — ненадёжно, не разбирается
            tm = _TERM.match(term)
            var = op = rhs = None
            if tm:
                var, op, rhs = _short(tm.group(1)), tm.group(2), tm.group(3)
            else:
                tm = _TERM_R.match(term)
                if tm:
                    var, op, rhs = _short(tm.group(3)), _FLIP[tm.group(2)], tm.group(1)
            key = gov(var, k) if var in reads_here else None
            if not key:
                continue
            v = _num(rhs, fc, gc)
            if v is None:
                continue
            kind = _body_kind(body, var)
            if kind:
                put(key, op, v, kind, k)
        k += 1
    return out


def scan_reads(files, consts=None, own=None):
    """{(секция, ключ): [{"type", "file", "line", "lo", "hi", "excl", "off", "how", "maxlen", "vo", "foreign", "hard"}]} по собираемым
    файлам (без Config.cpp). files — список путей (или папка src — как до ревизии 45). own — {файл: {свои секции}}."""
    if isinstance(files, str):
        files = [p for p in sorted(glob.glob(os.path.join(files, "**", "*.cpp"), recursive=True)) if ".bak" not in p]
    consts = consts or {}
    own = own or {}
    out = {}
    for p in files:
        b = os.path.basename(p)
        if ".bak" in p or b == "Config.cpp":
            continue
        text = open(p, encoding="utf-8-sig", errors="replace").read()
        lines = text.splitlines()
        fc = file_consts(text)
        rel = os.path.relpath(p, PATCHES).replace("\\", "/")
        mine = own.get(rel, set())
        for i, ln in enumerate(lines):
            ms = list(_READ.finditer(ln))
            if not ms:
                continue
            # чтения в окне (12 строк до и 40 после): условие с несколькими ключами (P120) и повторное чтение той же переменной
            reads_pos = []
            for k2 in range(max(0, i - 12), min(len(lines), i + 40)):
                for vm in re.finditer(r"([A-Za-z_][\w\.]*(?:\[\w*\])?(?:->\w+)?)\s*=\s*(?:\(\w+\)\s*)?Config::Get(?:Int|Bool)\s*\(\s*"
                                      r"(?:L\"[^\"]+\"|\w+)\s*,\s*L\"([^\"]+)\"", lines[k2]):
                    reads_pos.append((k2, _short(vm.group(1)), vm.group(2)))
            lim = analyze(lines, i, reads_pos, fc, consts)
            for m in ms:
                typ, lit, ident, key = m.group(1).lower(), m.group(3), m.group(4), m.group(5)
                sec = lit or _sec_of(lines, i, ident)
                if not sec:
                    continue
                lo = hi = None
                how, excl, off = set(), [], []
                if typ == "int":
                    seg = ln[m.start():]
                    cm = _CLAMP.search(ln)
                    if cm and m.start() >= ln.find("Clamp"):
                        a, z = _num(cm.group(1), fc, consts), _num(cm.group(2), fc, consts)
                        if a is not None and z is not None:
                            lo, hi = a, z
                            how.add("Clamp")
                    mm = _MASK.match(seg)
                    if mm:
                        lo, hi = 0, int(mm.group(1), 0)
                        how.add("маска")
                    if _BOOLISH.match(seg):
                        lo, hi = 0, 1
                        how.add("? 1 : 0")
                    e = lim.get(key)
                    vm = _VAR.search(ln[:m.end()])
                    if e and (vm or len(ms) == 1):
                        lo = e["lo"] if lo is None else (lo if e["lo"] is None else max(lo, e["lo"]))
                        hi = e["hi"] if hi is None else (hi if e["hi"] is None else min(hi, e["hi"]))
                        excl, off = sorted(set(e["excl"])), e["off"]
                        how |= e["how"]
                maxlen, vo = None, None
                if typ == "str":
                    am = _STR_ARGS.search(ln[m.start():])
                    if am:
                        buf, size = am.group(1), am.group(2)
                        sm = re.match(r"(?:ARRAYSIZE|_countof)\s*\(\s*(\w+)\s*\)", size)
                        n = None
                        if sm:
                            for k2 in range(i, max(-1, i - 80), -1):        # «wchar_t a[64], b[128];» — объявление нескольких буферов
                                if re.search(r"\b(?:wchar_t|WCHAR|char|TCHAR)\b", lines[k2]):
                                    dm = re.search(r"\b%s\s*\[\s*([\w:]+)\s*\]" % re.escape(sm.group(1)), lines[k2])
                                    if dm:
                                        n = _num(dm.group(1), fc, consts)
                                        break
                        else:
                            n = _num(size, fc, consts)
                        if n:
                            maxlen = n - 1
                        # куда уходит значение: строка подключения / путь / адрес — по строкам использования буфера (и предыдущей:
                        #   вызов на две строки)
                        for k2 in range(i + 1, min(len(lines), i + 60)):
                            if _func_end(lines[k2]):
                                break
                            if not re.search(r"\b%s\b" % re.escape(buf), lines[k2]) or _READ.search(lines[k2]):
                                continue
                            stmt = lines[k2 - 1] + " " + lines[k2]
                            sk = _PATH_SINK.search(stmt) or _ADDR_SINK.search(stmt)
                            if _CONN_FMT.search(stmt):
                                vo = "подключение к базе (часть строки подключения, %s:%d)" % (os.path.basename(rel), k2 + 1)
                            elif sk:
                                vo = "%s (значение уходит в %s, %s:%d)" % ("сетевой адрес" if _ADDR_SINK.search(stmt) else "файл / секция файла",
                                                                         sk.group(1), os.path.basename(rel), k2 + 1)
                            if vo:
                                break
                foreign = bool(mine) and sec not in mine
                hard = None
                if foreign and typ == "bool" and key == "Enabled":
                    if re.search(r"\bif\s*\(\s*!\s*Config::GetBool\s*\(\s*L\"%s\"" % re.escape(sec), ln):
                        t2 = " ".join(lines[i:min(len(lines), i + 12)])
                        st = t2.find("(", re.search(r"\bif\s*\(", t2).start())
                        _c, aft = _paren(t2, st)
                        if aft:
                            rest = t2[aft:].lstrip()
                            body = rest[:rest.find("}") + 1] if rest.startswith("{") else rest.split(";", 1)[0] + ";"
                            kind = _body_kind(body, "")
                            if kind in ("fail", "off"):
                                hard = "не встанет" if kind == "fail" else "выключится"
                out.setdefault((sec, key), []).append({
                    "type": typ, "file": rel, "line": i + 1, "lo": lo, "hi": hi, "excl": excl, "off": off,
                    "how": ", ".join(sorted(how)) or None, "maxlen": maxlen, "vo": vo, "foreign": foreign, "hard": hard,
                    "user": sorted(mine)})
    return out


def _sec_of(lines, i, ident):
    """Значение константы секции ident — ближайшее присваивание L"…" выше строки i (в том же файле)."""
    rx = re.compile(_ASSIGN_SEC % re.escape(ident))
    for k in range(i, -1, -1):
        m = rx.search(lines[k])
        if m:
            return m.group(1)
    return None


# определение функции патча: «тип Имя(…)» в начале строки, тело «{» на этой же или следующей строке (extern "C" … __cdecl — у LoginPatch),
# объявление «…);» — не определение
_DEF = re.compile(r'^(?:extern\s+"C"\s+)?[\w\s\*&:<>]*?\b((?:P|L|N|D)\d+[a-z]?_\w+)\s*\([^;{]*\)\s*(?:const\s*)?(?:\{.*)?$')
_REG = re.compile(r'\{\s*L"([^"]+)"\s*,\s*(?:L"(?:[^"\\]|\\.)*"\s*)+,\s*&\s*(\w+)', re.S)
_ID = re.compile(r"^([A-Z]+\d+[a-z]?)_")


def own_sections(files, names):
    """★ ревизия 45 В-2: файл → его секции. По реестру патчей (Registry.cpp: {L"секция", L"…", &Функция}) и файлу, где Функция
    определена; файл без функции реестра — по номеру в имени (p55_… → P55_…); затем — секции, читаемые через константу файла (kSec)."""
    reg, defs, texts = {}, {}, {}
    for p in files:
        if ".bak" in p:
            continue
        rel = os.path.relpath(p, PATCHES).replace("\\", "/")
        text = open(p, encoding="utf-8-sig", errors="replace").read()
        texts[rel] = text
        if os.path.basename(p) == "Registry.cpp":
            for m in _REG.finditer(text):
                reg[m.group(2)] = m.group(1)
        for ln in text.splitlines():
            if ln.startswith((" ", "\t")):
                continue
            m = _DEF.match(ln)
            if m:
                defs.setdefault(rel, set()).add(m.group(1))
    by_id = {}
    for n in names:
        m = _ID.match(n or "")
        if m:
            by_id.setdefault(m.group(1).upper(), []).append(n)
    out = {}
    for rel, text in texts.items():
        s = {reg[f] for f in defs.get(rel, ()) if f in reg and reg[f] in names}
        if not s:
            m = re.match(r"^([a-z]+\d+[a-z]?)_", os.path.basename(rel))
            if m and len(by_id.get(m.group(1).upper(), [])) == 1:
                s = set(by_id[m.group(1).upper()])
        if not s:
            for m in re.finditer(r'\b\w+\s*(?:\[\s*\])?\s*=\s*L"([^"]+)"', text):
                if m.group(1) in names and re.search(r"Config::Get\w+\s*\(\s*\w+\s*,", text):
                    s.add(m.group(1))
                    break
        if s:
            out[rel] = s
    return out


def scan_deps(files, own):
    """Зависимости по коду: символ «Pnn_…/Lnn_…/Nnn_…», определённый в файле патча X и вызываемый в файле Y → {секция Y: {секция X:
    [символы]}}. own — {файл: {секции}} (own_sections)."""
    defs, texts = {}, {}
    for p in files:
        if ".bak" in p:
            continue
        rel = os.path.relpath(p, PATCHES).replace("\\", "/")
        lines = open(p, encoding="utf-8-sig", errors="replace").read().splitlines()
        texts[rel] = "\n".join(lines)
        for ln in lines:
            if ln.startswith((" ", "\t")):
                continue
            m = _DEF.match(ln)
            if m:
                defs.setdefault(m.group(1), set()).add(rel)
    out = {}
    for rel, text in texts.items():
        mes = own.get(rel) or set()
        if not mes:
            continue
        called = set(re.findall(r"\b((?:P|L|N|D)\d+[a-z]?_\w+)\s*\(", text))      # один проход по файлу (не регулярка на символ)
        for sym in sorted(called & set(defs)):
            where = defs[sym]
            if rel in where:
                continue
            for w in where:
                for prov in own.get(w) or ():
                    for me in mes:
                        if prov != me:
                            out.setdefault(me, {}).setdefault(prov, set()).add(sym)
    return {k: {p: sorted(v) for p, v in d.items()} for k, d in out.items()}


# ---------------------------------------------------------------------------------------------------------------------
# «Только просмотр» по значению (★ ревизия 45 В-4)
# ---------------------------------------------------------------------------------------------------------------------
_IP = re.compile(r"^\s*\d{1,3}(\.\d{1,3}){3}\s*([,:]\s*\d{1,5})?\s*$")
_HOSTPORT = re.compile(r"^\s*[A-Za-z0-9_\-\.\\]*[A-Za-z\.\\][A-Za-z0-9_\-\.\\]*\s*[,:]\s*\d{2,5}\s*$")     # «хост,порт» (не список чисел «204,206»)
_PATHV = re.compile(r"(^[A-Za-z]:[\\/])|(^\.\.?[\\/])|([\\/])|(\.(ini|txt|key|dat|log|dll|exe|csv|json|bin|pem|cfg)\s*$)", re.I)
_CONNV = re.compile(r"(DRIVER|SERVER|DATABASE|UID|PWD|DSN|Data Source|Initial Catalog|User ID|Password)\s*=", re.I)


def value_kind(v):
    """Вид значения → 'адрес' | 'путь' | 'подключение' | None."""
    v = (v or "").strip().strip("\"'")
    if not v:
        return None
    if _CONNV.search(v):
        return "подключение"
    if _IP.match(v) or _HOSTPORT.match(v):
        return "адрес"
    if _PATHV.search(v) and not re.fullmatch(r"[\d,;:\-\s\.]+", v):
        return "путь"
    return None


# ---------------------------------------------------------------------------------------------------------------------
# Описание из реестра INDEX.md
# ---------------------------------------------------------------------------------------------------------------------
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def index_rows(path=INDEX_MD):
    """{номер патча: [{"text", "docs"}]} — строки сводной таблицы и ленты INDEX.md, где номер выделен «**P40**»."""
    out, weak = {}, {}
    if not os.path.isfile(path):
        return out
    for ln in open(path, encoding="utf-8", errors="replace"):
        if not ln.lstrip().startswith(("|", "- ")):
            continue
        docs = sorted({d for _t, d in _MD_LINK.findall(ln) if d.endswith(".md")})
        text = re.sub(r"\s*\|\s*", " · ", _MD_LINK.sub(r"\1", ln.strip().strip("|-* ")).replace("**", ""))[:600]
        bold = set(re.findall(r"\*\*([A-Z]+\d+[a-z]?)\b", ln))           # «**P40**», «**P40 …**» — строка этого патча
        for pid in set(re.findall(r"(?<![A-Za-z0-9_])([PLN]\d+[a-z]?)(?![0-9])", ln)):
            rows = (out if pid in bold else weak).setdefault(pid, [])
            if len(rows) < 4 and not any(r["text"] == text for r in rows):
                rows.append({"text": text, "docs": docs[:3]})
    for pid, rows in weak.items():                                        # без выделения — только если выделенных строк нет
        if pid not in out:
            out[pid] = rows[:2]
    return out


def section_id(name):
    m = _ID.match(name or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------------------------------------------------------------
# Каталог
# ---------------------------------------------------------------------------------------------------------------------
def _md5_files(files, incs):
    h = hashlib.md5()
    paths = list(files)
    for d in incs:
        paths += sorted(glob.glob(os.path.join(d, "*.h")))
    for p in sorted(dict.fromkeys(paths)):
        if ".bak" in p or not os.path.isfile(p):
            continue
        h.update(os.path.relpath(p, PATCHES).encode("utf-8"))
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def build(index_path=INDEX_MD):
    """Каталог всех DLL → dict (см. шапку модуля). Ошибка разбора одной DLL — исключение (каталог неполным не выходит)."""
    idx = index_rows(index_path)
    out = {"format": 2, "dlls": {}}
    for dll, (ini, fam) in DLLS.items():
        src = os.path.join(PATCHES, dll, "src")
        secs, ver = parse_config(os.path.join(src, "Config.cpp"))
        names = {s["name"] for s in secs}
        files, incs = dll_sources(dll)
        consts = all_consts(files, incs)
        own = own_sections(files, names)
        reads = scan_reads(files, consts, own)
        deps = scan_deps(files, own)
        stray = sorted("%s/%s" % k for k in reads if k[0] not in names)     # чтение секции, которой нет в шаблоне
        stray_why = {}
        for (sec, key), rr in reads.items():
            if sec not in names:
                stray_why.setdefault(sec, sorted({"%s:%d" % (r["file"], r["line"]) for r in rr})[:3])
        # чтения чужих секций → зависимости (★ ревизия 45 В-2)
        foreign = {}
        for (sec, key), rr in reads.items():
            for r in rr:
                if r["foreign"] and sec in names:
                    for u in r["user"]:
                        if u != sec:
                            foreign.setdefault(u, []).append({"section": sec, "key": key, "file": r["file"], "line": r["line"],
                                                              "hard": r["hard"]})
        for s in secs:
            sid = section_id(s["name"])
            s["id"] = sid
            s["index"] = idx.get(sid, []) if sid else []
            # документ патча из комментария шаблона («Dokument: AstoryServer/Docs/…md» / «Документ: …», «Описание: …»)
            s["docs"] = sorted(set(re.findall(r"(?:Dokument|Документ|Описание)\s*:\s*(\S+\.md)", s.get("comment") or "")))[:3]
            needs = {p: list(v) for p, v in deps.get(s["name"], {}).items()}
            fr = foreign.get(s["name"], [])
            for f in fr:
                tpl = {"не встанет": "[%s] %s (чтение %s:%d, без него не встанет)", "выключится": "[%s] %s (чтение %s:%d, без него выключится)"}.get(
                    f["hard"], "[%s] %s (чтение %s:%d)")
                needs.setdefault(f["section"], []).append(tpl % (f["section"], f["key"], os.path.basename(f["file"]), f["line"]))
            s["needs"] = {p: sorted(set(v)) for p, v in needs.items()}
            s["reads_foreign"] = fr
            s["files"] = sorted(f for f, ss in own.items() if s["name"] in ss)
            for k in s["keys"]:
                rr = reads.get((s["name"], k["key"]), [])
                mine = [r for r in rr if not r["foreign"]] or rr
                k["reads"] = [{"file": r["file"], "line": r["line"], "type": r["type"], "how": r["how"], "foreign": r["foreign"]}
                              for r in rr][:6]
                types = {r["type"] for r in rr}
                k["type"] = ("bool" if types == {"bool"} else "int" if types <= {"int", "bool"} and types else
                             "str" if types == {"str"} else ("int" if re.match(r"^-?\d+$", k["def"] or "") else "str") if not types else "mixed")
                lo = [r["lo"] for r in mine if r["lo"] is not None]
                hi = [r["hi"] for r in mine if r["hi"] is not None]
                k["lo"], k["hi"] = (max(lo) if lo else None), (min(hi) if hi else None)
                k["range_src"] = "код" if (lo or hi) else None
                k["range_how"] = "; ".join(sorted({r["how"] for r in mine if r["how"]})) or None
                k["excl"] = sorted({v for r in mine for v in r["excl"]})
                k["off_when"] = sorted({(op, v, "%s:%d" % (r["file"], ln)) for r in mine for op, v, ln in r["off"]})
                k["off_when"] = [list(x) for x in k["off_when"]]
                ml = [r["maxlen"] for r in rr if r["maxlen"]]
                k["maxlen"] = min(ml) if ml else None
                vo = next((r["vo"] for r in rr if r["vo"]), None)
                if not vo:
                    vk = value_kind(k["def"])
                    vo = ("%s (умолчание шаблона «%s»)" % (vk, (k["def"] or "")[:40])) if vk else None
                k["view_only"] = vo
                k["rule"] = None
                for mdll, msec, rx, mt, mlo, mhi, where, rule in MANUAL:
                    if mdll == dll and msec == s["name"] and re.fullmatch(rx, k["key"]):
                        k["type"], k["lo"], k["hi"], k["range_src"], k["range_how"] = mt, mlo, mhi, "код (цикл)", where
                        if rule and rule.startswith("maxlen:"):
                            k["maxlen"] = int(rule[7:])
                        else:
                            k["rule"] = rule
                        if not k["reads"]:
                            k["reads"] = [{"file": where.split(":")[0], "line": int(re.search(r":(\d+)", where).group(1)), "type": mt,
                                           "how": "цикл по построенным именам", "foreign": False}]
                if not (k["lo"] is not None or k["hi"] is not None) and k.get("comment"):
                    m = _HINT.search(k["comment"])
                    if m:
                        k["lo"], k["hi"], k["range_src"] = int(m.group(1)), int(m.group(2)), "комментарий шаблона"
        out["dlls"][dll] = {"ini": ini, "family": fam, "version": ver, "src_md5": _md5_files(files, incs), "sections": secs,
                            "reads_outside_template": stray, "outside_why": stray_why,
                            "sources": [os.path.relpath(p, PATCHES).replace("\\", "/") for p in files]}
    return out


def load(prefer_source=True):
    """Каталог: на ПК (есть исходники) — свежая сборка из исходников; иначе (служба) — data/ref/patchcfg_catalog.json."""
    # ★ ревизия 57 Н-3: на сервере PATCHES = H:\Server\Patches вне дерева службы (папку может создать любой пользователь) — только справочник
    #   выкладки data/ref; исходники — только на ПК
    from core import config
    if prefer_source and not config.get().on_server and os.path.isfile(os.path.join(PATCHES, "AsdaPatch", "src", "Config.cpp")):
        return build()
    with open(CATALOG_REF, encoding="utf-8") as f:
        return json.load(f)


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    if args in (["--help"], ["-h"]):
        print("patchcfg_src.py [--write | --summary] — каталог ключей ini серверных DLL по исходникам (только чтение; --write кладёт "
              "data/ref/patchcfg_catalog.json)")
        return 0
    if args not in ([], ["--write"], ["--summary"]):
        print("неизвестный ключ: %s" % " ".join(args))
        return 1
    cat = build()
    for dll, d in cat["dlls"].items():
        nk = sum(len(s["keys"]) for s in d["sections"])
        nr = sum(1 for s in d["sections"] for k in s["keys"] if k["reads"])
        nl = sum(1 for s in d["sections"] for k in s["keys"] if k["lo"] is not None or k["hi"] is not None)
        print("%s: Version %s, секций %d, ключей %d, найдено чтение у %d, предел у %d, чтений вне шаблона %d" % (
            dll, d["version"], len(d["sections"]), nk, nr, nl, len(d["reads_outside_template"])))
    if args == ["--write"]:
        os.makedirs(os.path.dirname(CATALOG_REF), exist_ok=True)
        with open(CATALOG_REF, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cat, f, ensure_ascii=False, indent=0)
        print("записано: %s" % CATALOG_REF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
