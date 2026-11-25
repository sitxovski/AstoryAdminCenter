# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""crashes.py — раздел «Сбои клиента»: пакеты падений игры из LogDrop, группы по месту, частота, версии, квота LogDrop, срок хранения .alog
(шаг А7.2, 23.11.2026; разбор Reports/admin_center/research_a7_releases_20261123.md §3 А7.2; решения владельца А7 №1 — сбои
расшифровываются только на ПК, ключ LogSeal на сервер не кладётся, в панель уходит только сводка; №8 — .alog хранятся 60 дней, .acrash без
срока, удаление — отдельной операцией owner).

ТРИ ЧАСТИ
  * ПК (только ПК — config.port_code): pc_collect забирает новые .acrash с сервера ТЕМ ЖЕ кодом, что FetchAndDecrypt владельца
    (AstoryClient/Tools/LogSeal/fetch_and_decrypt.fetch_new: список по SSH, scp, сверка SHA-256 с .json приёмника, расшифровка в @@ASTORY_DEV_ROOT_ESC@@\\_player_logs),
    читает каждый пакет в памяти общим модулем AstoryClient/Tools/asda_logseal.py (parse, segment_info) и строит сводку: код исключения,
    адрес, текст ошибки, кадры, подпись места, время падения, версию «по времени» (releases.log). Наружу — только сводка (push_pc, логин asda_admin
    процедурами adm.ClientCrashPut / adm.ClientCrashSyncAdd, тем же путём, что releases push А7.1). Перед записью — проверка утечек (leaks).
  * Служба (сервер): view() — группы, частота за сутки и 7 суток, последний случай, версии, учётки (ссылка на карточку — Userindex по
    Us_member), квота LogDrop (logdrop_stats: сама служба читает папку на своей машине, ключ для этого не нужен — только размеры и даты).
  * Срок хранения: операция owner crash.alog_prune — удалить .alog (и их .json) старше ALOG_KEEP_DAYS суток: предпросмотр (число, размер),
    слово подтверждения и второй фактор, журнал adm.audit. .acrash не удаляются никогда (проверка в Python и в PowerShell). Автоматической
    чистки нет — только кнопка (обоснование — отчёт §А7.2).
ПОДПИСЬ МЕСТА = код исключения + первые SIG_FRAMES кадров нашего exe (AsdaReborn-Win64-Shipping.exe+RVA). RVA — у своей сборки: та же ошибка
  в другой сборке даёт другую подпись, пока нет символов. Символов нет: PDB Shipping хранится только у последней сборки (Build/EAC — без PDB,
  разбор §0 п.4) — в сводке «символов нет» (symbols = none), имена функций даст шаг А7.3.
ВЕРСИЯ — по времени: выпуск канала alpha из releases.log, действовавший на начало игровой сессии (лаунчер обновляет игру перед «Играть»);
  нет времени сессии — на время падения; пакет переноса старой папки падения UE (вид 5) — на время упаковки (падение раньше). Выпуск меньше
  чем за BOUNDARY_H часов до этого времени — пометка «на границе выпусков» (выгрузка 4_Upload идёт после сборки, игроки обновляются не сразу).
ПОВТОРЫ: ключ строки — SHA-256 пакета (.json приёмника; нет .json — SHA-256 файла). Второй способ — само падение: вид 4 — (pid, время
  падения), вид 5 — CrashGUID движка; совпало у разных пакетов — второй в сводку не идёт (счётчик «повторов»).
Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import json
import os
import re
import socket
import threading
import time

from core import config, db, hostshell
from core.ops import Operation, OpRefused, register

OUR_EXE = "AsdaReborn-Win64-Shipping.exe"                    # наш модуль в стеке (AsdaLogSealRetail.cpp DescribeAddress: имя файла модуля)
SIG_FRAMES = 3                                               # кадров нашего exe в подписи места
FRAMES_KEEP = 12                                             # кадров в сводке (все — модуль+RVA)
ERROR_MAX = 300                                              # длина текста ошибки в сводке (= adm.ClientCrash.error_text)
BOUNDARY_H = 12                                              # выпуск ближе этого к началу сессии — «на границе выпусков»
LOGDROP_ROOT = config.STACK_ROOT + r"\LogDrop"               # хранилище приёмника (LogDrop.ini Root=)
LOGDROP_INI = LOGDROP_ROOT + r"\service\LogDrop.ini"         # QuotaBytes / QuotaWarnPercent приёмника
QUOTA_DEFAULT, QUOTA_WARN_DEFAULT = 5368709120, 80           # = LogDrop.ini (deploy), если ini не прочитан
ALOG_KEEP_DAYS = 60                                          # решение владельца А7 №8
PRUNE_CONFIRM = "alogprune"                                  # слово подтверждения удаления
PRUNE_MAX = 5000                                             # файлов за одно удаление (больше — повторить)
STATS_CACHE_S, STATS_FORCE_S = 600, 30                       # квота LogDrop: кэш 10 мин, «обновить» — не чаще раза в 30 с
PC_STALE_H = 48                                              # ПК не присылал сводку дольше — предупреждение
FORMAT = "asda-crash/1"
NOT_INSTALLED = "таблиц adm.ClientCrash нет (sql/adminc_27_crashes.sql не установлен)"
LOGIN_RE = re.compile(r"^[a-z0-9_][a-z0-9_.@-]{0,31}$")            # ★ р75 К-8: не «.» / «..»

# Имена кодов — как у клиента (AsdaLogSealRetail.cpp ExceptionName), чтобы показ не зависел от текста в присланной сводке.
CODE_NAMES = {0xC0000005: "EXCEPTION_ACCESS_VIOLATION", 0xC00000FD: "EXCEPTION_STACK_OVERFLOW", 0xC000001D: "EXCEPTION_ILLEGAL_INSTRUCTION",
              0xC0000094: "EXCEPTION_INT_DIVIDE_BY_ZERO", 0xC0000096: "EXCEPTION_PRIV_INSTRUCTION", 0xC0000006: "EXCEPTION_IN_PAGE_ERROR",
              0x80000003: "EXCEPTION_BREAKPOINT", 0xC000008C: "EXCEPTION_ARRAY_BOUNDS_EXCEEDED", 0x80000002: "EXCEPTION_DATATYPE_MISALIGNMENT",
              0xC000008E: "EXCEPTION_FLT_DIVIDE_BY_ZERO", 0xC0000409: "STATUS_STACK_BUFFER_OVERRUN", 0xC0000374: "STATUS_HEAP_CORRUPTION",
              0xE06D7363: "исключение C++", 0x4000: "assert/фатальная ошибка UE (AssertExceptionCode)",
              0x8000: "падение GPU UE (GPUCrashExceptionCode)", 0x6000: "нехватка памяти UE (OutOfMemoryExceptionCode)"}
UE_TYPES = {"Crash": "падение (отчёт движка)", "Assert": "assert (отчёт движка)", "Ensure": "ensure (отчёт движка)",
            "GPUCrash": "падение GPU (отчёт движка)", "Hang": "зависание (отчёт движка)", "OutOfMemory": "нехватка памяти (отчёт движка)"}
STATUS = ("ok", "unread", "nosummary", "notfetched")

# ── разбор сводки (только ПК; функции чистые — самотест гоняет их и на сервере) ──────────────────────────────────────────────────────
_EXC = re.compile(r"^исключение: 0x([0-9A-Fa-f]{1,8}) .*?, флаги 0x([0-9A-Fa-f]+), адрес (\S+)\s*$")
_ACC = re.compile(r"^доступ: (чтение|запись|исполнение) по адресу (0x[0-9A-Fa-f]+)\s*$")
_FRAME = re.compile(r"^\s*#\d+\s+(\S+?)\+0x([0-9A-Fa-f]+)\s*$")
_UE_FRAME = re.compile(r"^\s*(\S+)\s+0x[0-9A-Fa-f]+\s+\+\s+([0-9A-Fa-f]+)\s*$")
_IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")


def _norm_mod(m):
    """Имя модуля кадра → как в сводке клиента (у отчёта движка — без «.exe» / «.dll»: AsdaReborn-Win64-Shipping, ntdll)."""
    m = m.strip()
    if m == "?" or "." in m:
        return m
    return m + (".exe" if m.lower().startswith("asdareborn") else ".dll")


def _frame(mod, rva):
    return "%s+0x%X" % (_norm_mod(mod), int(rva, 16))


def mask_text(s):
    """Текст ошибки из сводки → без путей (releases._mask: X:\\…, UNC → имя файла), без IP, без управляющих, не длиннее ERROR_MAX."""
    from domains import releases
    t = releases._mask(str(s or ""))
    t = _IP.sub("<IP>", t)
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:ERROR_MAX]


def parse_summary(text):
    """summary.txt пакета падения (AsdaLogSealRetail.cpp MakeCrashSummary) → dict(code, addr, access, error, frames[модуль+0xRVA])."""
    out = {"code": None, "addr": None, "access": None, "error": None, "frames": []}
    lines = (text or "").replace("\r\n", "\n").split("\n")
    in_stack = False
    err = []
    for ln in lines:
        if in_stack:
            m = _FRAME.match(ln)
            if m:
                out["frames"].append(_frame(m.group(1), m.group(2)))
            continue
        m = _EXC.match(ln)
        if m:
            out["code"] = "0x%08X" % int(m.group(1), 16)
            a = re.match(r"^(\S+?)\+0x([0-9A-Fa-f]+)$", m.group(3))
            out["addr"] = _frame(a.group(1), a.group(2)) if a else m.group(3)[:96]
            continue
        m = _ACC.match(ln)
        if m:
            out["access"] = "%s %s" % (m.group(1), m.group(2))
            continue
        if ln.startswith("ошибка: "):
            err.append(ln[8:])
            continue
        if ln.startswith("нить: "):
            continue
        if ln.strip() == "стек:":
            in_stack = True
            continue
        if err and ln.strip():                                # продолжение многострочного текста ошибки
            err.append(ln)
    out["error"] = mask_text(" ".join(err)) if err else None
    return out


def parse_crash_context(xml):
    """CrashContext.runtime-xml (отчёт движка из старой папки падения, пакет вида 5) → dict(code «UE:<тип>», error, frames, guid)."""
    t = xml or ""

    def tag(n):
        m = re.search(r"<%s>(.*?)</%s>" % (n, n), t, re.S)
        return m.group(1) if m else None
    ctype = (tag("CrashType") or "").strip()
    err = (tag("ErrorMessage") or "").strip().split("\n")[0]
    frames = []
    for ln in (tag("PCallStack") or "").splitlines():
        m = _UE_FRAME.match(ln)
        if m:
            frames.append(_frame(m.group(1), m.group(2)))
    guid = (tag("CrashGUID") or "").strip()
    return {"code": ("UE:" + re.sub(r"[^A-Za-z]", "", ctype))[:24] if ctype else "UE:?", "addr": frames[0] if frames else None, "access": None,
            "error": mask_text(err) or None, "frames": frames, "guid": guid if re.match(r"^[\w-]{1,80}$", guid) else ""}


# ★ ревизия 75 М-3: коды, которые поднимает сам движок (RaiseException в обработчике ошибки UE), — первые кадры exe у них общий путь отчёта,
#   а не место. Сколько кадров пропускать — измерено на реальных стеках LogDrop (13 пакетов, 23.11.2026): у 0x8000 (GPU) в трёх сборках
#   (alpha-1.0.11, 3.0.2, 4.0.4) первые 3 кадра exe одинаковы у всех падений сборки (+0x1436xxx · +0x43B3xxx–0x43B5xxx · +0x43B5xxx–0x43B6xxx),
#   а два разных падения сборки 3.0.2 расходятся с 4-го (+0x43A80C4 · +0x43B1039 против +0x43A240D · +0x43A27F5). Для 0x4000 (assert / Fatal)
#   и 0x6000 (нехватка памяти) пакетов нет — глубина обработчика не измерена, поэтому кадры не пропускаются, а различает их текст ошибки.
ENGINE_SKIP = {0x8000: 3}
ENGINE_CODES = (0x4000, 0x6000, 0x8000)
GENERIC_ERRORS = ("fatal error!", "")                         # текст GErrorHist по умолчанию — не различает места


def _code_int(code):
    try:
        return int(code, 16)
    except (TypeError, ValueError):
        return None


def norm_error(err):
    """★ р75 М-3: первая строка текста ошибки без чисел, hex, адресов и кавычек содержимого — для подписи кодов движка (assert, Fatal)."""
    t = (err or "").split("\n")[0].strip()
    t = re.sub(r"0x[0-9A-Fa-f]+|\b\d+(\.\d+)?\b|<IP>", "#", t)
    t = re.sub(r"\s+", " ", t).strip().lower()[:120]
    return "" if t in GENERIC_ERRORS else t


def place_frames(code, frames):
    """Кадры exe, которые входят в подпись места (после пропуска общего пути отчёта движка) → (кадры, пропущено)."""
    exe = [f for f in frames if f.lower().startswith(OUR_EXE.lower() + "+")]
    skip = ENGINE_SKIP.get(_code_int(code), 0) if len(exe) > ENGINE_SKIP.get(_code_int(code), 0) else 0
    return exe[skip:skip + SIG_FRAMES], skip


def signature(code, frames, error=None):
    """Подпись места: код + SIG_FRAMES кадров нашего exe (у кодов движка — после общего пути отчёта, ENGINE_SKIP) + у кодов движка — текст
    ошибки без чисел, если он не «Fatal error!» → (sig 12 hex, текст, кадров exe). Кадров exe нет — первые кадры стека (с пометкой)."""
    exe = [f for f in frames if f.lower().startswith(OUR_EXE.lower() + "+")]
    use, skip = place_frames(code, frames)
    if exe:
        text = "%s | %s%s" % (code or "?", "пропущено %d кадра обработчика | " % skip if skip else "", " ".join(use))
    else:
        text = "%s | кадров exe нет | %s" % (code or "?", " ".join(frames[:SIG_FRAMES]) or "стека нет")
    ne = norm_error(error) if _code_int(code) in ENGINE_CODES or (code or "").startswith("UE:") else ""
    if ne:
        text += " | " + ne
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12], text, len(exe)


def code_name(code):
    """Подпись кода для экрана (по коду, не по тексту присланной сводки)."""
    if not code:
        return ""
    if code.startswith("UE:"):
        return UE_TYPES.get(code[3:], "отчёт движка: %s" % code[3:])
    try:
        return CODE_NAMES.get(int(code, 16), "исключение")
    except ValueError:
        return ""


def _parse_utc(s):
    """«2026-10-25T20:59:59.379Z» / «2026-10-25 20:59:59» → datetime UTC без долей | None."""
    if not isinstance(s, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})", s.strip())
    if not m:
        return None
    try:
        return datetime.datetime(*map(int, m.groups()))
    except ValueError:
        return None


def session_utc(info):
    """Начало игровой сессии в UTC: имя журнала сессии (session=ГГГГММДД-ччммсс_pid.alog — местное время игрока) минус смещение
    (time — местное, time_utc — UTC того же мгновения, округление до 15 мин) → datetime | None."""
    m = re.match(r"^(\d{8})-(\d{6})_\d+", info.get("session") or "")
    loc = re.match(r"^(\d{4})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2}):(\d{2})$", info.get("time") or "")
    utc = _parse_utc(info.get("time_utc"))
    if not (m and loc and utc):
        return None
    try:
        s_loc = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        now_loc = datetime.datetime(*map(int, loc.groups()))
    except ValueError:
        return None
    off = round((now_loc - utc).total_seconds() / 900.0) * 900
    s = s_loc - datetime.timedelta(seconds=off)
    return s if s <= utc + datetime.timedelta(minutes=1) and utc - s < datetime.timedelta(days=3) else None


def alpha_releases(text):
    """releases.log → [(время UTC, версия)] канала alpha по возрастанию (тот же разбор, что «Выпуски»: releases.parse_releases_log)."""
    from domains import releases
    out = []
    for r in releases.parse_releases_log(text, limit=10 ** 6):
        t = _parse_utc((r.get("time") or "").replace("+00:00", ""))
        if t and str(r.get("version") or "").startswith("alpha-"):
            out.append((t, r["version"]))
    return sorted(out)


def version_at(t, rels, basis):
    """Версия по времени → (версия | None, основание, пометка)."""
    if t is None or not rels:
        return None, "none", "версия не определена: нет времени" if t is None else "версия не определена: releases.log пуст"
    prev = [r for r in rels if r[0] <= t]
    if not prev:
        return None, basis, "раньше первого выпуска в releases.log (%s)" % rels[0][1]
    cur = prev[-1]
    hrs = (t - cur[0]).total_seconds() / 3600.0
    base = {"session": "по времени начала сессии", "crash": "по времени падения", "sealed": "по времени упаковки (падение раньше)",
            "received": "по времени приёма"}[basis]
    if hrs < BOUNDARY_H and len(prev) >= 2:
        return cur[1], basis, "%s, на границе: выпуск за %s ч до этого, возможна прежняя %s" % (base, "%.1f" % hrs, prev[-2][1])
    return cur[1], basis, base


def _members(segs, ls, want):
    """Файлы пакета в памяти (без записи на диск): имена, удовлетворяющие want(имя), не больше 1 МБ каждый → {имя: байты}."""
    out, cur = {}, None
    for s in segs:
        if s.kind not in ls.FILE_KINDS:
            continue
        for t, b in s.records:
            if t == ls.REC_FBEGIN:
                cur = None
                if len(b) >= 2 and len(b) >= 2 + int.from_bytes(b[0:2], "little") + 8:
                    n = b[2:2 + int.from_bytes(b[0:2], "little")].decode("utf-8", "replace")
                    if want(n):
                        cur = n
                        out[n] = bytearray()
            elif t == ls.REC_FDATA and cur is not None:
                if len(out[cur]) < (1 << 20):
                    out[cur] += b
            elif t == ls.REC_FEND:
                cur = None
    return {k: bytes(v) for k, v in out.items()}


def read_package(path, ls, keys, meta=None):
    """Один .acrash → сырая запись разбора (без версии): sha, file, login, kind, времена, итог, код, адрес, кадры, подпись, ключ падения."""
    with open(path, "rb") as f:
        data = f.read()
    meta = meta or {}
    sha = meta.get("sha256") if isinstance(meta.get("sha256"), str) and re.match(r"^[0-9a-f]{64}$", meta.get("sha256") or "") else None
    rec = {"sha": sha or hashlib.sha256(data).hexdigest(), "file": os.path.basename(path)[:96], "login": None, "kind": 4,
           "crash_utc": None, "session_utc": None, "received_utc": _parse_utc(meta.get("received_utc")), "status": "ok", "status_note": "",
           "code": None, "addr": None, "access": None, "error": None, "frames": [], "exe_frames": 0, "sig": None, "sig_text": None,
           "basis_time": None, "basis": "none", "key": None}
    lg = str(meta.get("account_claimed") or "").lower()
    if meta.get("account_status") == "ok" and LOGIN_RE.match(lg):
        rec["login"] = lg                                    # только найденная приёмником учётка (заявлена клиентом — не доказательство)
    try:
        segs = ls.parse(data, keys)
    except Exception as ex:                                  # разбор не должен ронять всю отправку
        return dict(rec, status="unread", status_note="пакет не разобран: %s" % ex.__class__.__name__)
    bad = [s.error for s in segs if s.error]
    good = [s for s in segs if s.records]
    if not good:
        why = bad[0] if bad else "нет сегментов"
        why = "нет закрытого ключа на этом ПК" if "нет закрытого ключа" in why else ("тег GCM не сошёлся (порча или подмена)" if "GCM" in why else why)
        return dict(rec, status="unread", status_note="пакет не расшифрован: %s" % mask_text(why)[:160])
    info = ls.segment_info(good[0])
    rec["kind"] = good[0].kind if good[0].kind in (4, 5) else 4
    t = _parse_utc(info.get("time_utc"))
    mem = _members(good, ls, lambda n: n == "summary.txt" or n.endswith("CrashContext.runtime-xml"))
    if rec["kind"] == 5:
        x = next((v for k, v in mem.items() if k.endswith("CrashContext.runtime-xml")), None)
        p = parse_crash_context(x.decode("utf-8", "replace")) if x else None
        rec.update(basis_time=t, basis="sealed")
        if p and p["guid"]:
            rec["key"] = "ue:" + p["guid"]
    else:
        x = mem.get("summary.txt")
        p = parse_summary(x.decode("utf-8", "replace")) if x else None
        rec["crash_utc"] = t
        su = session_utc(info)
        rec["session_utc"] = su
        rec.update(basis_time=su or t, basis="session" if su else ("crash" if t else "none"))
        if t and str(info.get("pid") or "").isdigit():
            rec["key"] = "k4:%s:%s" % (info["pid"], info.get("time_utc"))
    if bad:
        rec["status_note"] = "часть сегментов не прочитана: %s" % mask_text(bad[0])[:160]
    if not p:
        rec["status"] = "nosummary"
        rec["status_note"] = rec["status_note"] or ("в пакете нет CrashContext движка" if rec["kind"] == 5 else "в пакете нет summary.txt")
        return rec
    sig, text, nexe = signature(p["code"], p["frames"], p["error"])
    rec.update(code=p["code"], addr=p["addr"], access=p["access"], error=p["error"], frames=p["frames"][:FRAMES_KEEP], exe_frames=nexe,
               sig=sig, sig_text=text)
    return rec


def _ts(v):
    return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else (str(v) if v is not None else None)


def finish(rec, rels):
    """Сырая запись → строка сводки (поля adm.ClientCrash, времена строками, версия по времени, отпечаток строки)."""
    t = rec.get("basis_time") or rec.get("received_utc")
    basis = rec.get("basis") if rec.get("basis_time") else ("received" if rec.get("received_utc") else "none")
    ver, vb, note = version_at(t, rels, basis) if basis != "none" else (None, "none", "версия не определена: нет времени")
    row = {"sha": rec["sha"], "file": rec["file"], "login": rec.get("login"), "kind": int(rec.get("kind") or 4),
           "crash_utc": _ts(rec.get("crash_utc")), "session_utc": _ts(rec.get("session_utc")), "received_utc": _ts(rec.get("received_utc")),
           "status": rec["status"], "status_note": (rec.get("status_note") or "")[:200], "code": rec.get("code"),
           "addr": (rec.get("addr") or None) and rec["addr"][:96], "access": rec.get("access"), "error": rec.get("error"),
           "frames": " ".join(rec.get("frames") or [])[:1000] or None, "exe_frames": int(rec.get("exe_frames") or 0), "sig": rec.get("sig"),
           "version": ver, "version_basis": vb, "version_note": note[:200], "symbols": "none"}
    row["row_md5"] = hashlib.md5(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return row


# ── ПК: сбор ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _tools():
    """fetch_and_decrypt (AstoryClient/Tools/LogSeal) и asda_logseal (AstoryClient/Tools) — только ПК (на сервере PortCodeError)."""
    import sys
    ls_dir = config.port_code(os.path.join(os.path.dirname(config.HERE), "AstoryClient", "Tools", "LogSeal"))   # ★ 25.11 (С-1): папка клонов / AstoryClient
    if ls_dir not in sys.path:
        sys.path.insert(0, ls_dir)
    import fetch_and_decrypt as F                                   # noqa: E402 — без побочных эффектов при импорте
    import logseal as L                                              # noqa: E402
    return F, L.load()


NO_KEY = ("на этом ПК ключ LogSeal не открывается (нет в хранилище DPAPI или DPAPI недоступен — например, задача планировщика S4U) — "
          "ничего не забрано и не записано, запустите при входе в систему")


def key_ok(ls):
    """★ р75 (планировщик): открывается ли закрытый ключ LogSeal текущего keyId на этом ПК (DPAPI учётки). Сам ключ не выводится."""
    try:
        return ls.current_key() is not None
    except Exception:                                       # DPAPI без ключей пользователя (S4U) и т. п.
        return False


def _releases_log():
    from domains import releases
    p = os.path.join(releases.pc_paths()["releases"], "releases.log")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read(), ""
    except OSError as ex:
        return "", "releases.log не прочитан: %s" % ex.__class__.__name__


def local_packages(dest, F):
    """Пакеты падений в папке расшифровки (раскладка приёмника <логин>/<ГГГГ-ММ-ДД>/<имя>.acrash) → [(логин, дата, путь)]."""
    out = []
    try:
        logins = sorted(os.listdir(dest))
    except OSError:
        return out
    for lg in logins:
        lp = os.path.join(dest, lg)
        if not os.path.isdir(lp) or not F.LOGIN_DIR_RE.match(lg) or lg == F.SERVICE_DIR:
            continue
        for day in sorted(os.listdir(lp)):
            dp = os.path.join(lp, day)
            if not os.path.isdir(dp) or not F.DATE_DIR_RE.match(day):
                continue
            for n in sorted(os.listdir(dp)):
                if n.endswith(".acrash") and F.FILE_RE.match(n) and os.path.isfile(os.path.join(dp, n)):
                    out.append((lg, day, os.path.join(dp, n)))
    return out


def _meta(path):
    try:
        with open(os.path.splitext(path)[0] + ".json", encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) else {}
    except (OSError, ValueError):
        return {}


def pc_collect(fetch=True, dest=None, now=None, listing=None, tools=None, rel_text=None, log=None, keys=None):
    """Сводка сбоев на ПК → dict(format, host, collected_utc, rows[], stats{}, errors[]). fetch — сначала забрать новые .acrash с сервера
    (сервер недоступен — OpRefused: сводка без сверки с сервером не отправляется). Только ПК."""
    F, ls = tools or _tools()
    dest = dest or F.default_dest()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    errors = []
    srv = None
    if keys is None and not key_ok(ls):
        raise OpRefused(NO_KEY)
    if fetch:
        try:
            listing = listing if listing is not None else F.ssh_scan(("acrash",))
            res = F.fetch_new(("acrash",), dest=dest, log=log or (lambda s: None), ls=ls, listing=listing)
        except RuntimeError as ex:
            raise OpRefused("список пакетов на сервере не получен (%s) — сводка не собрана" % mask_text(ex))
        errors += [mask_text(e) for e in res["errors"]]
        srv = {(x[0], x[1], x[2]) for x in listing}
    text, err = rel_text if rel_text is not None else _releases_log()
    if err:
        errors.append(err)
    rels = alpha_releases(text)
    keys = keys or ls._keys_fn(None)                         # ключ — только из хранилища DPAPI этого ПК (самотест — свой)
    raw, seen_sha, seen_key, dups = [], set(), {}, 0
    have = set()
    for lg, day, p in local_packages(dest, F):
        have.add((lg, day, os.path.basename(p)))
        rec = read_package(p, ls, keys, _meta(p))
        if rec["sha"] in seen_sha:
            dups += 1
            continue
        seen_sha.add(rec["sha"])
        if rec.get("key") and rec["key"] in seen_key:
            dups += 1
            continue
        if rec.get("key"):
            seen_key[rec["key"]] = rec["sha"]
        raw.append(rec)
    missing = sorted(srv - have) if srv is not None else []
    for lg, day, n in missing:                               # на сервере есть, забрать не вышло — строкой «не забран» (sha — по имени)
        raw.append({"sha": hashlib.sha256(("notfetched:%s/%s/%s" % (lg, day, n)).encode()).hexdigest(), "file": n, "login": None, "kind": 4,
                    "received_utc": None, "status": "notfetched", "status_note": "пакет на сервере, на ПК не забран (ошибка копирования)",
                    "basis_time": None, "basis": "none"})
    rows = [finish(r, rels) for r in raw]
    rows.sort(key=lambda r: (r["crash_utc"] or r["received_utc"] or "", r["file"]))
    stats = {"on_server": len(srv) if srv is not None else None, "local": len(have), "rows": len(rows), "dups": dups,
             "unread": sum(1 for r in rows if r["status"] == "unread"), "nosummary": sum(1 for r in rows if r["status"] == "nosummary"),
             "notfetched": len(missing), "releases": len(rels), "fetched_now": (res["fetched"] if fetch else None)}
    return {"format": FORMAT, "host": socket.gethostname()[:64], "collected_utc": now.strftime("%Y-%m-%d %H:%M:%S"), "rows": rows,
            "stats": stats, "errors": errors[:20]}


def leaks(text):
    """Утечки в сводке → [что найдено]: всё, что ловит releases.leaks (пути X:\\ и X:/, \\Users\\, имя пользователя Windows и домашняя
    папка, .ssh, .dpapi, ключи, пароль), плюс IP-адреса, id установки и путь exe игрока («exe=», «Program Files»)."""
    from domains import releases
    bad = releases.leaks(text)
    t = text + "\n" + text.replace("\\\\", "\\")
    for rx, what in ((_IP, "IP"), (re.compile(r'"install"|"ip"\s*:'), "install/ip"), (re.compile(r"exe="), "exe="),
                     (re.compile(r"(?i)program files"), "Program Files"), (re.compile(r"(?i)session_tail|minidump"), "minidump")):
        if rx.search(t):
            bad.append(what)
    return bad


def payload_text(snap):
    """Сводка без строк (итог отправки) → JSON и md5 (время сбора в md5 не входит). Строки идут отдельными вызовами adm.ClientCrashPut."""
    body = {"format": snap.get("format"), "host": snap.get("host"), "stats": snap.get("stats"), "errors": snap.get("errors")}
    text = json.dumps(dict(body, collected_utc=snap.get("collected_utc")), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    md5 = hashlib.md5(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return text[:4000], md5


def _installed(cn):
    return bool(db.admin_rows(cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.ClientCrash', N'U') IS NOT NULL AND OBJECT_ID(N'adm.ClientCrashPut', N'P') IS NOT NULL"))


def _dt(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None


def push_pc(by, snap=None, cn_factory=None):
    """Сводка ПК → AsdaAdmin (логин asda_admin, процедуры) → dict(new, changed, same, sync_id, sync_new). Утечки — отказ, ничего не пишется."""
    from domains import releases
    snap = snap if snap is not None else pc_collect()
    full = json.dumps(snap, ensure_ascii=False, sort_keys=True)
    bad = leaks(full)
    if bad:
        raise OpRefused("в сводке сбоев найдено то, что наружу не отправляется (%s) — не записана" % ", ".join(sorted(set(bad))))
    for r in snap.get("rows") or []:
        if r.get("status") not in STATUS or not re.match(r"^[0-9a-f]{64}$", str(r.get("sha") or "")):
            raise OpRefused("строка сводки сбоев не прошла проверку (%s) — не записана" % str(r.get("file") or "?")[:96])
    text, md5 = payload_text(snap)
    cn = (cn_factory or db.admin)()
    try:
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        cnt = {1: 0, 2: 0, 0: 0}
        for r in snap.get("rows") or []:
            x = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @r INT; EXEC adm.ClientCrashPut @Sha = ?, @File = ?, @Login = ?, @Kind = ?, "
                                  "@CrashUtc = ?, @SessionUtc = ?, @ReceivedUtc = ?, @Status = ?, @StatusNote = ?, @ExcCode = ?, @ExcAddr = ?, "
                                  "@Access = ?, @ErrorText = ?, @Frames = ?, @ExeFrames = ?, @Sig = ?, @Version = ?, @VersionBasis = ?, "
                                  "@VersionNote = ?, @Symbols = ?, @RowMd5 = ?, @Result = @r OUTPUT; SELECT @r AS r",
                              (r["sha"], r["file"], r.get("login"), int(r.get("kind") or 4), _dt(r.get("crash_utc")), _dt(r.get("session_utc")),
                               _dt(r.get("received_utc")), r["status"], r.get("status_note") or "", r.get("code"), r.get("addr"), r.get("access"),
                               r.get("error"), r.get("frames"), int(r.get("exe_frames") or 0), r.get("sig"), r.get("version"),
                               r.get("version_basis") or "none", r.get("version_note") or "", r.get("symbols") or "none", r["row_md5"]))
            cnt[int(x[0]["r"]) if x else 0] += 1
        s = db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @id INT, @n INT; EXEC adm.ClientCrashSyncAdd @Payload = ?, @PayloadMd5 = ?, @Host = ?, "
                              "@By = ?, @CollectedUtc = ?, @Id = @id OUTPUT, @New = @n OUTPUT; SELECT @id AS id, @n AS n",
                          (text, md5, str(snap.get("host") or "")[:64], releases.safe_by(by), _dt(snap["collected_utc"])))
        return {"new": cnt[1], "changed": cnt[2], "same": cnt[0], "sync_id": int(s[0]["id"]), "sync_new": bool(s[0]["n"])}
    finally:
        cn.close()


# ── служба: квота LogDrop и срок хранения ───────────────────────────────────────────────────────────────────────────────────────────
# Сводка хранилища одним скриптом (локально на сервере или по SSH с ПК): по (виду, дню, «запись старше срока») — число, байты, самая поздняя
# запись; квота из ini. Признак «старше» — по времени записи каждого файла (как у кандидатов на удаление), не по дню целиком.
_STATS_PS = r"""
$root = '%(root)s'
$q = %(qd)d; $w = %(wd)d
try { Get-Content -LiteralPath '%(ini)s' -ErrorAction Stop | ForEach-Object { if ($_ -match '^\s*QuotaBytes\s*=\s*(\d+)') { $q = [int64]$matches[1] }
  if ($_ -match '^\s*QuotaWarnPercent\s*=\s*(\d+)') { $w = [int]$matches[1] } }; $ini = 1 } catch { $ini = 0 }
$cut = [datetime]::ParseExact('%(cut)s', 'yyyy-MM-dd HH:mm:ss', $null)
$g = @{}
Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne 'service' -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | ForEach-Object {
  Get-ChildItem -LiteralPath $_.FullName -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $d = $_.Directory.Name
    $e = $_.Extension.TrimStart('.').ToLower()
    if ($d -notmatch '^\d{4}-\d{2}-\d{2}$') { $d = '?' }
    $o = $(if ($_.LastWriteTimeUtc -lt $cut) { 1 } else { 0 })
    $k = $e + '|' + $d + '|' + $o
    if (-not $g.ContainsKey($k)) { $g[$k] = @(0, [int64]0, '') }
    $g[$k][0]++; $g[$k][1] += $_.Length
    $t = $_.LastWriteTimeUtc.ToString('yyyy-MM-dd HH:mm:ss'); if ($t -gt $g[$k][2]) { $g[$k][2] = $t }
  }
}
$rows = @($g.Keys | ForEach-Object { $p = $_.Split('|'); [pscustomobject]@{ ext=$p[0]; day=$p[1]; old=[int]$p[2]; n=$g[$_][0]; bytes=$g[$_][1]; last=$g[$_][2] } })
$v = Get-PSDrive -Name ($root.Substring(0,1)) -ErrorAction SilentlyContinue
[pscustomobject]@{ quota=$q; warn=$w; ini=$ini; rows=$rows; free=$(if ($v) { [int64]$v.Free } else { $null });
  now=(Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss') } | ConvertTo-Json -Depth 4 -Compress
"""

_stats_lock = threading.Lock()
_stats = {"at": 0.0, "data": None}


def _stats_script(now=None):
    return _STATS_PS % {"root": LOGDROP_ROOT.replace("'", "''"), "ini": LOGDROP_INI.replace("'", "''"), "qd": QUOTA_DEFAULT, "wd": QUOTA_WARN_DEFAULT,
                        "cut": _cutoff(now).strftime("%Y-%m-%d %H:%M:%S")}


def summarize_stats(j, now=None):
    """Ответ скрипта → квота, разбивка по видам, рост по полумесяцам, кандидаты на удаление (по дням: день папки и последняя запись старше)."""
    rows = j.get("rows") if isinstance(j.get("rows"), list) else ([j["rows"]] if isinstance(j.get("rows"), dict) else [])
    now = now or _parse_utc(j.get("now")) or datetime.datetime.utcnow()
    cut = now - datetime.timedelta(days=ALOG_KEEP_DAYS)
    by_ext, halves, old = {}, {}, {"n": 0, "bytes": 0, "days": 0, "oldest": None}
    total = 0
    for r in rows:
        ext, day, n, b = str(r.get("ext") or ""), str(r.get("day") or "?"), int(r.get("n") or 0), int(r.get("bytes") or 0)
        total += b
        e = by_ext.setdefault(ext if ext in ("alog", "acrash", "json") else "other", {"n": 0, "bytes": 0})
        e["n"] += n
        e["bytes"] += b
        if re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            h = day[:7] + ("-1" if int(day[8:]) <= 15 else "-2")
            halves[h] = halves.get(h, 0) + b
            dd = datetime.datetime.strptime(day, "%Y-%m-%d")
            if ext == "alog" and dd < cut and int(r.get("old") or 0) == 1:
                old["n"] += n
                old["bytes"] += b
                old["days"] += 1
            if ext == "alog" and (old["oldest"] is None or day < old["oldest"]):
                old["oldest"] = day
    q = int(j.get("quota") or QUOTA_DEFAULT)
    w = int(j.get("warn") or QUOTA_WARN_DEFAULT)
    return {"quota": q, "warn_pct": w, "ini": bool(j.get("ini")), "used": total, "pct": round(100.0 * total / q, 1) if q else None,
            "warn": bool(q) and total * 100 >= q * w, "by_ext": by_ext, "halves": [{"half": k, "bytes": halves[k]} for k in sorted(halves)],
            "old_alog": old, "keep_days": ALOG_KEEP_DAYS, "free": j.get("free"), "at": j.get("now")}


def logdrop_stats(force=False, run=None):
    """Квота и разбивка LogDrop (кэш STATS_CACHE_S; force — заново, не чаще STATS_FORCE_S). run(script) → stdout — подмена для самотеста."""
    if run is None:
        with _stats_lock:
            age = time.time() - _stats["at"]
            if _stats["data"] and (age < STATS_CACHE_S and not force or age < STATS_FORCE_S):
                return _stats["data"]
    try:
        out = (run or (lambda s: hostshell.powershell(s, timeout=120)))(_stats_script())
        res = summarize_stats(json.loads(out.strip() or "{}"))
        res["error"] = ""
    except (hostshell.HostError, ValueError, TypeError, KeyError) as ex:
        res = {"error": "квота LogDrop не прочитана: %s" % mask_text(ex)[:200]}
    if run is None:
        with _stats_lock:
            _stats.update(at=time.time(), data=res)
    return res


# Кандидаты на удаление: только .alog, день папки и время записи — оба старше срока; без reparse-точек. Вывод — «логин\tдень\tимя\tразмер».
_OLD_PS = r"""
$root = '%(root)s'
$cut = [datetime]::ParseExact('%(cut)s', 'yyyy-MM-dd HH:mm:ss', $null)
Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne 'service' -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | ForEach-Object {
  $lg = $_
  Get-ChildItem -LiteralPath $lg.FullName -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' -and $_.Name -lt $cut.ToString('yyyy-MM-dd') -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | ForEach-Object {
    $dy = $_
    Get-ChildItem -LiteralPath $dy.FullName -File -Filter '*.alog' -ErrorAction SilentlyContinue | Where-Object { $_.Extension -eq '.alog' -and $_.LastWriteTimeUtc -lt $cut } | ForEach-Object {
      $lg.Name + "`t" + $dy.Name + "`t" + $_.Name + "`t" + $_.Length
    }
  }
}
"""

# Удаление по списку: каждый путь проверяется ещё раз (под корнем, .alog, не reparse, день и время записи старше срока); .json рядом —
# только если у него нет пакета падения с тем же именем. Вывод — «ok|skip \t относительный путь \t байт \t причина».
_DEL_PS = r"""
$root = '%(root)s'
$cut = [datetime]::ParseExact('%(cut)s', 'yyyy-MM-dd HH:mm:ss', $null)
$list = @(%(list)s)
foreach ($rel in $list) {
  $p = Join-Path $root $rel
  try {
    $f = Get-Item -LiteralPath $p -ErrorAction Stop
    if ($f.Extension -ne '.alog' -or $f.FullName -notlike ($root + '\*') -or ($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        ($f.Directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -or ($f.Directory.Parent.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $f.Directory.Parent.FullName -notlike ($root + '\*') -or $f.LastWriteTimeUtc -ge $cut -or $f.Directory.Name -ge $cut.ToString('yyyy-MM-dd')) {
      "skip`t$rel`t0`tне подходит"; continue }
    $n = $f.Length
    $j = [IO.Path]::ChangeExtension($f.FullName, '.json')
    $c = [IO.Path]::ChangeExtension($f.FullName, '.acrash')
    Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
    if ((Test-Path -LiteralPath $j) -and -not (Test-Path -LiteralPath $c)) { $n += (Get-Item -LiteralPath $j).Length; Remove-Item -LiteralPath $j -Force -ErrorAction SilentlyContinue }
    "ok`t$rel`t$n`t"
  } catch { "skip`t$rel`t0`t" + $_.Exception.GetType().Name }
}
"""
_REL_RE = re.compile(r"^(_unknown|_acct_[0-9a-f]{1,64}|[a-z0-9_][a-z0-9_.@-]{0,31})\\\d{4}-\d{2}-\d{2}\\[0-9A-Za-z_.-]{1,96}\.alog$")


def _cutoff(now=None):
    now = now or datetime.datetime.utcnow()
    return (now - datetime.timedelta(days=ALOG_KEEP_DAYS)).replace(microsecond=0)


def old_alogs(now=None, run=None):
    """Кандидаты на удаление → (список относительных путей «логин\\день\\имя.alog», байт, срез UTC)."""
    cut = _cutoff(now)
    script = _OLD_PS % {"root": LOGDROP_ROOT.replace("'", "''"), "cut": cut.strftime("%Y-%m-%d %H:%M:%S")}
    out = (run or (lambda s: hostshell.powershell(s, timeout=180)))(script)
    items, total = [], 0
    for ln in out.splitlines():
        p = ln.strip("\r\n").split("\t")
        if len(p) != 4 or not p[3].isdigit():
            continue
        rel = "%s\\%s\\%s" % (p[0], p[1], p[2])
        if p[0] == "service" or not _REL_RE.match(rel) or p[1] >= cut.strftime("%Y-%m-%d"):
            continue                                         # .acrash и всё, что не .alog по правилам приёмника, сюда не попадает
        items.append(rel)
        total += int(p[3])
    items.sort()
    return items, total, cut


def delete_alogs(items, cut, run=None):
    """Удалить .alog по списку (повторная проверка на сервере) → (удалено, байт, пропущено [(путь, причина)])."""
    bad = [x for x in items if not _REL_RE.match(x) or x.lower().endswith(".acrash")]
    if bad:
        raise OpRefused("в списке на удаление не .alog по правилам приёмника (%s) — ничего не удалено" % bad[0][:120])
    script = _DEL_PS % {"root": LOGDROP_ROOT.replace("'", "''"), "cut": cut.strftime("%Y-%m-%d %H:%M:%S"),
                        "list": ",".join("'%s'" % x.replace("'", "''") for x in items)}
    out = (run or (lambda s: hostshell.powershell(s, timeout=600)))(script)
    n, b, skip, done = 0, 0, [], []
    for ln in out.splitlines():
        p = ln.strip("\r\n").split("\t")
        if len(p) != 4:
            continue
        if p[0] == "ok":
            n += 1
            b += int(p[2]) if p[2].isdigit() else 0
            done.append(p[1])
        else:
            skip.append((p[1], p[3]))
    delete_alogs.last_done = done                          # ★ р75 К-5: удалённые пути — в журнал (apply)
    return n, b, skip


# ── служба: чтение сводки ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _uids(logins):
    """Логины → {логин: Userindex} (Us_member; только для ссылки на карточку). База недоступна — пусто."""
    if not logins:
        return {}
    try:
        with db.GameReader("asdastoryop") as op:
            ls = sorted(logins)[:500]
            rows = op.rows("SELECT Userindex, Us_id FROM Us_member WHERE Us_id IN (%s)" % ",".join("?" * len(ls)), ls)
    except db.DbError:
        return {}
    return {str(r["Us_id"] or "").lower(): int(r["Userindex"]) for r in rows}


def summary(cn_factory=None, now=None, uids=None):
    """Сводка из AsdaAdmin → dict(installed, rows, groups, days, sync, error)."""
    now = now or datetime.datetime.utcnow()
    out = {"installed": True, "rows": [], "groups": [], "days": [], "sync": None, "error": ""}
    try:
        cn = (cn_factory or db.admin)()
    except db.DbError as ex:
        return dict(out, error="сводка сбоев не прочитана: %s" % ex)
    try:
        if not _installed(cn):
            return dict(out, installed=False, error=NOT_INSTALLED)
        rows = db.admin_rows(cn, "SELECT TOP 5000 id, pkg_sha256, file_name, login, pkg_kind, crash_utc, session_utc, received_utc, status, status_note, "
                                 "exc_code, exc_addr, access, error_text, frames, exe_frames, sig, version, version_basis, version_note, symbols, "
                                 "pushed_utc FROM adm.ClientCrash ORDER BY id DESC")
        sigs = {r["sig"]: r for r in db.admin_rows(cn, "SELECT sig, exc_code, frames, first_utc, last_utc, n, accounts FROM adm.ClientCrashSig")}
        sy = db.admin_rows(cn, "SELECT TOP 1 id, payload, host, collected_utc, pushed_utc, seen_utc, seen_count, "
                               "DATEDIFF(minute, seen_utc, SYSUTCDATETIME()) AS age_min FROM adm.ClientCrashSync ORDER BY id DESC")
    except db.DbError as ex:
        return dict(out, error="сводка сбоев не прочитана: %s" % ex)
    finally:
        cn.close()
    if sy:
        x = sy[0]
        try:
            st = json.loads(x["payload"]).get("stats") or {}
        except (ValueError, AttributeError):
            st = {}
        age = float(x["age_min"] or 0) / 60.0
        out["sync"] = {"id": x["id"], "host": x["host"], "collected_utc": _ts(x["collected_utc"]), "seen_utc": _ts(x["seen_utc"]),
                       "seen_count": x["seen_count"], "age_h": round(age, 1), "stale": age > PC_STALE_H, "stats": st}
    if uids is None:
        uids = _uids({r["login"] for r in rows if r["login"]})
    day_ago, week_ago = now - datetime.timedelta(days=1), now - datetime.timedelta(days=7)
    groups = {}
    days = {}
    for r in rows:
        t = r["crash_utc"] or r["received_utc"]
        item = {"id": r["id"], "file": r["file_name"], "login": r["login"], "uid": uids.get((r["login"] or "").lower()), "kind": r["pkg_kind"],
                "crash_utc": _ts(r["crash_utc"]), "session_utc": _ts(r["session_utc"]), "received_utc": _ts(r["received_utc"]),
                "status": r["status"], "status_note": r["status_note"], "code": r["exc_code"], "code_name": code_name(r["exc_code"]),
                "addr": r["exc_addr"], "access": r["access"], "error": r["error_text"], "frames": (r["frames"] or "").split(),
                "exe_frames": r["exe_frames"], "sig": r["sig"], "version": r["version"], "version_basis": r["version_basis"],
                "version_note": r["version_note"], "symbols": r["symbols"], "sha": (r["pkg_sha256"] or "")[:16]}
        out["rows"].append(item)
        if t:
            d = t.strftime("%Y-%m-%d")
            days[d] = days.get(d, 0) + 1
        if not r["sig"]:
            continue
        g = groups.get(r["sig"])
        if g is None:
            s = sigs.get(r["sig"]) or {}
            g = groups[r["sig"]] = {"sig": r["sig"], "code": r["exc_code"], "code_name": code_name(r["exc_code"]), "addr": r["exc_addr"],
                                    "error": r["error_text"], "frames": (r["frames"] or "").split()[:FRAMES_KEEP], "exe_frames": r["exe_frames"],
                                    "place": place_frames(r["exc_code"], (r["frames"] or "").split())[0],
                                    "skipped": place_frames(r["exc_code"], (r["frames"] or "").split())[1],
                                    "n": 0, "n_24h": 0, "n_7d": 0, "accounts": set(), "unknown": 0, "versions": {}, "first": None, "last": None,
                                    "last_case": None, "symbols": "none", "sig_n": s.get("n")}
        g["n"] += 1
        if t and t >= day_ago:
            g["n_24h"] += 1
        if t and t >= week_ago:
            g["n_7d"] += 1
        if r["login"]:
            g["accounts"].add(r["login"])
        else:
            g["unknown"] += 1
        v = r["version"] or "?"
        g["versions"][v] = g["versions"].get(v, 0) + 1
        ts = _ts(t)
        if ts and (g["first"] is None or ts < g["first"]):
            g["first"] = ts
        if ts and (g["last"] is None or ts >= g["last"]):
            g["last"] = ts
            g["last_case"] = item
    gl = []
    for g in groups.values():
        acc = sorted(g["accounts"])
        g["accounts"] = [{"login": a, "uid": uids.get(a)} for a in acc]
        g["versions"] = [{"version": k, "n": n} for k, n in sorted(g["versions"].items(), key=lambda kv: (-kv[1], kv[0]))]
        gl.append(g)
    gl.sort(key=lambda g: (g["last"] or ""), reverse=True)
    out["groups"] = gl
    out["days"] = [{"day": (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d"),
                    "n": days.get((now - datetime.timedelta(days=i)).strftime("%Y-%m-%d"), 0)} for i in range(13, -1, -1)]
    return out


def warnings(s, st):
    """Предупреждения раздела по сводке и квоте → [текст]."""
    w = []
    if not s.get("installed"):
        return [s.get("error") or NOT_INSTALLED]
    if s.get("error"):
        w.append(s["error"])
    sy = s.get("sync")
    if not sy and not s.get("error"):
        w.append("ПК ещё не присылал сводку сбоев (asda_admin.py crashes sync на ПК владельца)")
    elif sy and sy.get("stale"):
        w.append("сводка сбоев старше %d ч (ПК присылал %s UTC) — новые падения могли не попасть в раздел" % (PC_STALE_H, sy["seen_utc"]))
    if st and not st.get("error"):
        if st.get("warn"):
            w.append("LogDrop занят на %s%% (порог предупреждения приёмника %d%%) — при 100%% приём журналов останавливается (507)"
                     % (st["pct"], st["warn_pct"]))
        if (st.get("old_alog") or {}).get("n"):
            w.append(".alog старше %d суток: %d (%s МБ) — удалить может владелец (кнопка ниже)"
                     % (ALOG_KEEP_DAYS, st["old_alog"]["n"], "%.1f" % (st["old_alog"]["bytes"] / 1048576.0)))
        ac = ((st.get("by_ext") or {}).get("acrash") or {}).get("n")
        if sy and ac is not None and (sy.get("stats") or {}).get("on_server") is not None and ac > sy["stats"]["on_server"]:
            w.append("на сервере пакетов падений %d, в последней сводке ПК %d — запустите crashes sync на ПК" % (ac, sy["stats"]["on_server"]))
    elif st and st.get("error"):
        w.append(st["error"])
    n_un = sum(1 for r in s.get("rows") or [] if r["status"] in ("unread", "notfetched"))
    if n_un:
        w.append("пакетов не прочитано или не забрано: %d (причина — в таблице случаев)" % n_un)
    new = [g for g in s.get("groups") or [] if g["first"] and g["n_24h"] and g["n"] == g["n_24h"]]
    for g in new[:5]:
        w.append("новое место падения за сутки: %s %s (%d)" % (g["code"], g["sig"], g["n"]))
    return w


def view(force=False, cn_factory=None, stats_run=None):
    """Раздел «Сбои клиента» целиком: сводка ПК + квота LogDrop + предупреждения."""
    s = summary(cn_factory)
    st = logdrop_stats(force=force, run=stats_run)
    return {"summary": s, "logdrop": st, "warnings": warnings(s, st), "keep_days": ALOG_KEEP_DAYS, "confirm_word": PRUNE_CONFIRM,
            "pc_stale_h": PC_STALE_H, "sig_frames": SIG_FRAMES, "exe": OUR_EXE}


# ── операции ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
@register
class CrashSync(Operation):
    """★ А7.2: задание ПК — забрать новые .acrash по scp, расшифровать на ПК, прислать службе сводку (adm.ClientCrash*). Исполняет консоль ПК
    (asda_admin.py crashes sync или задание ПК crash.sync — jobs run-due / watch). Пишет только AsdaAdmin; ключ LogSeal с ПК не уходит."""
    name, title = "crash.sync", "Сбои клиента: прислать сводку с ПК"
    perm, reversible, schedule_runner = "crash.sync", False, "pc"

    def schedule_check(self, ctx, p):
        return None

    def preview(self, ctx, p):
        """На ПК предпросмотр забирает новые пакеты в _player_logs (локально, в базу ничего), кроме no_fetch — так консоль делает --dry
        (★ р75 К-2: сухой прогон ничего не забирает)."""
        if config.get().on_server:
            raise OpRefused("сбои расшифровывает только ПК владельца (ключ LogSeal — там, решение владельца А7 №1) — поставьте задание ПК")
        snap = pc_collect(fetch=not p.get("no_fetch"))
        st = snap["stats"]
        return {"text": "сводка сбоев: пакетов на сервере %s, на ПК %d, строк %d, повторов %d, не прочитано %d, не забрано %d, забрано сейчас %s"
                        % (st["on_server"] if st["on_server"] is not None else "—", st["local"], st["rows"], st["dups"], st["unread"],
                           st["notfetched"], st["fetched_now"] if st["fetched_now"] is not None else "—"),
                "warnings": sorted(set(leaks(json.dumps(snap, ensure_ascii=False)))) + list(snap["errors"]), "snap": snap}

    def apply(self, ctx, p, prev):
        r = push_pc(ctx.login, prev.get("snap"))
        tpl = ("сводка сбоев записана: новых %d, изменилось %d, без изменений %d (отправка №%d)" if r["sync_new"]
               else "сводка сбоев записана: новых %d, изменилось %d, без изменений %d (отправка №%d, итог тот же)")
        return {"after": r, "message": tpl % (r["new"], r["changed"], r["same"], r["sync_id"])}


@register
class CrashAlogPrune(Operation):
    """★ А7.2 (решение владельца А7 №8): удалить на сервере .alog старше ALOG_KEEP_DAYS суток (и их .json). .acrash не удаляются никогда.
    Только сейчас, только owner: предпросмотр (число, размер), слово alogprune и второй фактор из браузера, журнал adm.audit. Отката нет."""
    name, title = "crash.alog_prune", "Сбои клиента: удалить старые .alog в LogDrop"
    perm, reversible = "crash.prune", False
    two_factor, confirm_word = True, PRUNE_CONFIRM

    def target(self, p):
        return "logdrop:alog>%dd" % ALOG_KEEP_DAYS

    def preview(self, ctx, p):
        items, total, cut = old_alogs()
        md5 = hashlib.md5("\n".join(items).encode("utf-8")).hexdigest()
        logins = sorted({x.split("\\")[0] for x in items})
        return {"text": "удалить .alog старше %d суток (до %s UTC): %d файлов, %s МБ, учёток %d" % (ALOG_KEEP_DAYS, cut.strftime("%Y-%m-%d"),
                                                                                                 len(items), "%.1f" % (total / 1048576.0), len(logins)),
                "items_n": len(items), "bytes": total, "cut": cut.strftime("%Y-%m-%d %H:%M:%S"), "first": items[:20],
                "warnings": [".acrash (пакеты падений) не удаляются никогда — только .alog и их .json",
                             "отката нет: удалённые журналы не восстанавливаются (расшифрованные копии на ПК владельца остаются)"],
                "expect": {"n": len(items), "md5": md5}, "_items": items, "_cut": cut}

    def apply(self, ctx, p, prev):
        if str(p.get("confirm") or "") != PRUNE_CONFIRM:
            raise OpRefused("нужно подтверждение удаления: слово %s (в панели — ввести слово, в консоли — ключ --confirm %s)" % (PRUNE_CONFIRM, PRUNE_CONFIRM))
        if ctx.via not in ("web", "cli", "test"):
            raise OpRefused("удаление старых журналов — только сейчас: из браузера (слово и второй фактор) или консолью ПК, не заданием")
        want = p.get("expect")                              # ★ р75 К-6: сначала список, потом код второго фактора (не тратить код на отказ)
        if not isinstance(want, dict) or want.get("md5") != prev["expect"]["md5"]:
            raise OpRefused("список .alog изменился с предпросмотра (или предпросмотра не было) — повторите предпросмотр, ничего не удалено")
        if ctx.via == "web":
            from core import auth
            auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())
        items = prev["_items"]
        if not items:
            return {"after": {"deleted": 0, "bytes": 0}, "message": ".alog старше %d суток нет — ничего не удалено" % ALOG_KEEP_DAYS}
        rest = max(0, len(items) - PRUNE_MAX)
        items = items[:PRUNE_MAX]
        delete_alogs.last_done = []
        n, b, skip = delete_alogs(items, prev["_cut"])
        done = list(getattr(delete_alogs, "last_done", []) or [])
        with _stats_lock:
            _stats.update(at=0.0, data=None)
        by_login = {}
        for x in done:
            by_login[x.split("\\")[0]] = by_login.get(x.split("\\")[0], 0) + 1
        after = {"deleted": n, "bytes": b, "skipped": len(skip), "skip": skip[:20], "rest": rest, "by_login": by_login,
                 "paths": done if len(done) <= 200 else done[:100] + ["… ещё %d …" % (len(done) - 200)] + done[-100:]}
        msg = "удалено .alog: %d (%s МБ, с их .json), пропущено %d" % (n, "%.1f" % (b / 1048576.0), len(skip))
        if rest:
            msg = "удалено .alog: %d (%s МБ, с их .json), пропущено %d, осталось %d — повторите удаление" % (
                n, "%.1f" % (b / 1048576.0), len(skip), rest)
        return {"before": {"n": len(items) + rest, "bytes": prev["bytes"]}, "after": after, "message": msg}
