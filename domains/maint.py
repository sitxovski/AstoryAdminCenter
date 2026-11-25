# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""maint.py — режим обслуживания: вход в игру только служебным учёткам 1…5000 (волна А5.3 «Живое управление», план §4.Д, §5.1; 21.11.2026).

РЕВЕРС (AstoryServer/Docs/LoginManager/L09-login-maintenance.md):
  допуск входа решает Joy1.dbo.UPUserLogin — LoginManager (обработчик 1003 sub_406C20, LoginManager.c:2405-2733) только переводит её
  статус в ответ клиенту. Своего «режима обслуживания» у стока нет — есть список адресов AcceptIp.ini (по IP, только при старте
  LoginManager, отказ 4101 код 28 = нотис клиента 7017 «Идут профилактические работы на сервере»). Поэтому:
  SQL L09 (AstoryServer/Docs/SQL/l09_01_migrate.sql) — таблица Joy1.adm.LoginMaintenance (Mode 0/1, счётчики), процедура
    adm.LoginMaintenanceSet и врезка [L09-GATE] в UPUserLogin: при Mode = 1 учётке вне 1…5000 (пароль верен, блока нет) — статус 28,
    вошедшей она не помечается. Служебные учётки 1…5000 входят как обычно. Рестарт не нужен.
  DLL L09 (LoginPatch v11, 98e5308b… — ревизия 43б; прежние d5e97e0c и 3cbfea52 не выкладывать) — статус 28 уходит клиенту стоковым
    4101 код 28 (нотис 7017, вход не закрывается); без неё — 1004/28 (клиент: «ошибка входа» с числом). Отказ входа действует и без DLL,
    меняется только текст у игрока; вход в мир с выбора персонажа закрывает только DLL (второй гейт, adm.LoginMaintenanceGate).
  «Вход в мир закрыт» панель пишет только когда сходится всё (★ ревизия 43б Н-4): в последнем запуске LoginManager «[OK] L09» И строка
    установки с «WorldGate=1», md5 DLL — сборка L09 из L09_DLL_MD5, процедура adm.LoginMaintenanceGate есть в Joy1. Сбой запроса гейта
    (★ Н-3: строка «[L09-GATE-FAIL]» в журнале патчей) — показывается: последний сбой без «[L09-GATE-OK]» после него = «гейт сейчас не работает».
  Обе части НЕ применяются панелью (SQL и DLL — только по слову владельца): панель честно показывает, чего не хватает.
ОПЕРАЦИИ (право server.maintenance — владелец и администратор):
  maint.on  — включить. Подтверждение (confirm = maint); объявление в игру мостом (live.announce) ДО включения — обязательно, кроме
              явного «без объявления» (silent = silent); из браузера — свежий код второго фактора; уже вошедших НЕ отключает, кроме явного
              выбора kick = players (существующий кик мостом P127, право players.kick, учётки сессий вне 1…5000).
  maint.off — выключить (подтверждение; объявление по желанию).
  Обе ставятся в задания (adm.job, исполнитель — служба) — включение и выключение по расписанию.
  Перед записью — перепроверка состояния (могло смениться после предпросмотра), после — чтение итога (verify).
СОСТОЯНИЕ (state, /api/maint, «Состояние»): SQL-часть (таблица, врезка — VIEW DEFINITION на dbo.UPUserLogin у asda_admin), режим, кто и
  когда включил, отказы и допуски; DLL — по журналу патчей LoginManager (последний запуск, «[OK] L09_LoginMaintenance»); кто в игре по
  мосту (не прочитано ≠ «никого»), вошедшие по БД (Us_member.Flag = 1), учётки вне 1…5000 со строкой CharGmInfo (их режим не пускает).
Побочных эффектов при импорте нет.
"""
import json
import threading
import time

from core import auth, bridge, config, db, hostshell
from core.ops import Operation, OpRefused, register, run as ops_run

OPERATOR_MAX_UID = 5000          # служебные учётки 1…5000 (оператор стока sub_52ECF0 — 0…5000, номер 0 не выдаётся)
STATUS = 28                      # статус UPUserLogin в режиме обслуживания = код 4101 (стоковый «Идут профилактические работы»)
GATE_MARK = "[L09-GATE]"
# LoginPatch v11 с L09 и гейтом входа в мир (ревизии 43 С-1 и 43б; AstoryServer/Patches/LoginPatch/tools/l09_data). Прежние сборки —
#   d5e97e0c (без гейта входа в мир) и 3cbfea52 (гейт на DSN группы, режим 2 после смены личности, сбой молча на 60 с) — не выкладывались и
#   сюда не входят (с ними «вход в мир закрыт» было бы неправдой или не всей правдой).
L09_DLL_MD5 = ("98e5308b8d7f292ff397087b9021e4c9",)
CONFIRM = "maint"
SILENT = "silent"
PARTIAL = "partial"              # ★ ревизия 43 Н-3: включить, даже если объявление дошло не до всех узлов
KICK = "players"
REASON_MAX = 200
DLL_TTL_S = 60                   # кэш чтения журнала патчей LoginManager
ANNOUNCE_RGB = [255, 210, 0]

NEED_SQL = ("SQL-часть L09 не применена (AstoryServer/Docs/SQL/l09_01_migrate.sql: таблица adm.LoginMaintenance и врезка в UPUserLogin) — "
            "режим обслуживания не включается, применение — по слову владельца")
NEED_DLL = ("LoginPatch v11 с L09 (98e5308b) на LoginManager не действует — отказ входа всё равно сработает, но игрок увидит «ошибка "
            "входа 28», а не стоковое «Идут профилактические работы на сервере», и вход в мир с выбора персонажа не закрыт (нужна выкладка "
            "DLL рестартом стойки — по слову владельца)")
DLL_UNREAD = "журнал патчей LoginManager не прочитан (%s) — какой текст увидит игрок и закрыт ли вход в мир с выбора персонажа, неизвестно"
# ★ ревизия 43 С-1: что режим делает с уже вошедшими — честно по состоянию DLL (гейт входа в мир — LoginPatch L09, adm.LoginMaintenanceGate)
WORLD_CLOSED = ("вход в мир с выбора персонажа закрыт (LoginPatch L09): кто вошёл до включения и стоит на выборе персонажа, в мир не войдёт, "
                "а кто уже на игровом сервере, играет дальше и переходит между картами и каналами, пока его не отключат")
WORLD_OPEN = ("вход в мир с выбора персонажа НЕ закрыт (LoginPatch L09 не действует): вошедшие по БД вне 1…5000 (%s) смогут войти в мир — "
              "галочка «отключить игроков» их не достаёт, мост видит только игроков на игровом сервере")
SESSIONS_NOTE = WORLD_CLOSED     # прежнее имя (тесты и консоль)
# ★ ревизия 43б Н-4: «закрыт» — только когда сходится всё; иначе — чего именно не хватает, или «неизвестно»
WORLD_OPEN_NOGATE = ("вход в мир с выбора персонажа НЕ закрыт (L09 стоит без гейта входа в мир, WorldGate=0): вошедшие по БД вне 1…5000 (%s) "
                     "смогут войти в мир")
WORLD_OPEN_DLL = ("вход в мир с выбора персонажа НЕ закрыт (LoginPatch.dll на стойке %s — не сборка L09 с гейтом %s): вошедшие по БД вне "
                  "1…5000 (%s) смогут войти в мир")
WORLD_OPEN_PROC = ("вход в мир с выбора персонажа НЕ закрыт (в Joy1 нет процедуры adm.LoginMaintenanceGate — SQL L09 без второго гейта): "
                   "вошедшие по БД вне 1…5000 (%s) смогут войти в мир")
WORLD_UNKNOWN = "закрыт ли вход в мир с выбора персонажа, неизвестно (%s)"
WORLD_WHY_LOG = "журнал патчей LoginManager не прочитан"
WORLD_WHY_LINE = "в журнале патчей нет строки установки L09"
WORLD_WHY_SQL = "наличие процедуры adm.LoginMaintenanceGate не прочитано"
# ★ ревизия 43б Н-3: сбой запроса гейта (строка «[L09-GATE-FAIL]» журнала патчей) — вход в мир в это время открыт (fail-open), но видно
GATE_FAIL_NOW = ("гейт входа в мир сейчас НЕ работает: последний сбой запроса adm.LoginMaintenanceGate в %s (сбоев с запуска LoginManager: %d) "
                 "— пока он не восстановится, вход в мир с выбора персонажа открыт")
GATE_FAIL_PAST = ("гейт входа в мир с запуска LoginManager давал сбой запроса %d раз (последний в %s) — на эти секунды вход в мир был открыт, "
                  "сейчас гейт работает")
ON_DONE = "режим обслуживания включён: вход только служебным учёткам 1…5000"
OVERLAP_NOTE ="игрок вне 1…5000, который уже в игре и входит повторно, получит отказ, а не выбивание прежней сессии (прежняя сессия остаётся)"

# подмены для самотеста (None — настоящие)
DLL_READ = None                  # () → dict как dll_state()
_dll_cache = {"at": 0.0, "data": None}
_dll_lock = threading.Lock()


# ─────────────────────────────── состояние ───────────────────────────────

def sql_state():
    """SQL-часть: {"read", "error", "table", "gate", "mode", "changed_at", "changed_by", "reason", "refused", "last_refused_at",
    "last_refused_uid", "admitted", "last_admitted_at", "last_admitted_uid", "installed_at"}. gate None — тело UPUserLogin не видно
    (нет VIEW DEFINITION): «не прочитано», а не «нет»."""
    out = {"read": False, "error": "", "table": None, "gate": None, "mode": None, "world_gate": None}
    try:
        with db.GameReader("joy1") as j:
            r = j.one("SELECT CASE WHEN OBJECT_ID(N'adm.LoginMaintenance', N'U') IS NULL THEN 0 ELSE 1 END AS t, "
                      "CASE WHEN OBJECT_ID(N'adm.LoginMaintenanceGate', N'P') IS NULL THEN 0 ELSE 1 END AS wg, "
                      "CASE WHEN OBJECT_ID(N'dbo.UPUserLogin', N'P') IS NULL THEN 0 ELSE 1 END AS p, "
                      "CASE WHEN OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin')) IS NULL THEN 0 ELSE 1 END AS v, "
                      "CHARINDEX(N'[L09-GATE]', OBJECT_DEFINITION(OBJECT_ID(N'dbo.UPUserLogin'))) AS g")
            out["table"] = bool(r["t"])
            out["world_gate"] = bool(r["wg"])           # ★ ревизия 43б Н-4: процедура второго гейта (вход в мир) есть
            out["gate"] = (int(r["g"] or 0) > 0) if r["v"] else None
            if not r["p"]:
                out["error"] = "нет процедуры dbo.UPUserLogin"
            if out["table"]:
                m = j.one("SELECT Mode, ChangedAt, ChangedBy, Reason, Refused, LastRefusedAt, LastRefusedUid, Admitted, LastAdmittedAt, "
                          "LastAdmittedUid, GateInstalledAt, WorldRefused, LastWorldRefusedAt FROM adm.LoginMaintenance WHERE Id = 1")
                if m:
                    out.update(mode=int(m["Mode"]), changed_at=_s(m["ChangedAt"]), changed_by=m["ChangedBy"] or "", reason=m["Reason"] or "",
                               refused=int(m["Refused"] or 0), last_refused_at=_s(m["LastRefusedAt"]), last_refused_uid=m["LastRefusedUid"],
                               admitted=int(m["Admitted"] or 0), last_admitted_at=_s(m["LastAdmittedAt"]),
                               last_admitted_uid=m["LastAdmittedUid"], installed_at=_s(m["GateInstalledAt"]),
                               world_refused=int(m["WorldRefused"] or 0), last_world_refused_at=_s(m["LastWorldRefusedAt"]))
                else:
                    out["error"] = "в adm.LoginMaintenance нет строки Id = 1"
            out["read"] = not out["error"]
    except db.DbError as ex:
        out["error"] = str(ex)[:300]
    return out


def _s(v):
    return str(v) if v is not None else None


_PS_DLL = r"""
$ErrorActionPreference = 'Stop'
$root = '__ROOT__\LoginManager'
function Md5Of([string]$p) {
  if (-not (Test-Path -LiteralPath $p)) { return 'none' }
  $fs = [IO.File]::Open($p, 'Open', 'Read', 'ReadWrite')
  try { $h = [Security.Cryptography.MD5]::Create().ComputeHash($fs) } finally { $fs.Close() }
  return ([BitConverter]::ToString($h) -replace '-', '').ToLower()
}
$res = [ordered]@{ dll = (Md5Of "$root\LoginPatch.dll"); lm = ''; file = ''; head = ''; ok = $false; total = ''; found = $false;
                   world = ''; fail = 0; fail_last = ''; fail_now = $false }
$p = @(Get-CimInstance Win32_Process -Filter "Name='LoginManager.exe'" | ? { $_.ExecutablePath -and $_.ExecutablePath -like "$root\*" })
$res.lm = ($p | % { $_.CreationDate.ToString('yyyy-MM-dd HH:mm:ss') }) -join ','
$dir = "$root\Log\Log_Patch"
$files = @()
if (Test-Path -LiteralPath $dir) { $files = @(Get-ChildItem -LiteralPath $dir -Filter 'PatchLog_*.txt' | ? { $_.Name -match '^PatchLog_\d{8}\.txt$' } | sort Name -Descending) }
foreach ($f in $files) {
  $fs = [IO.File]::Open($f.FullName, 'Open', 'Read', 'ReadWrite')
  try { $sr = New-Object IO.StreamReader($fs, [Text.Encoding]::GetEncoding(1251)); $ls = $sr.ReadToEnd() -split "`r?`n" } finally { $fs.Close() }
  $h = -1
  for ($i = $ls.Count - 1; $i -ge 0; $i--) { if ($ls[$i] -match '\d{4}-\d\d-\d\d \d\d:\d\d:\d\d, PID \d+') { $h = $i; break } }
  if ($h -lt 0) { continue }
  $res.found = $true; $res.file = $f.Name; $res.head = $ls[$h]
  # до итога — установка; после него — строки работы (сбои гейта входа в мир): читаем до конца файла (запуск — последний в файле)
  for ($k = $h + 1; $k -lt $ls.Count; $k++) {
    $l = $ls[$k]
    if ($l -match '\[OK\]\s+L09_LoginMaintenance') { $res.ok = $true }
    if (-not $res.total -and $l -match '=== ') { $res.total = $l }
    if ($l -match 'L09: .*-> L09_Send') { if ($l -match 'WorldGate=1') { $res.world = 'on' } elseif ($l -match 'WorldGate=0') { $res.world = 'off' } }
    if ($l -match '^\[(\d\d:\d\d:\d\d)\].*\[L09-GATE-FAIL\]') { $res.fail++; $res.fail_last = $matches[1]; $res.fail_now = $true }
    if ($l -match '\[L09-GATE-OK\]') { $res.fail_now = $false }
  }
  break
}
$res | ConvertTo-Json -Compress
"""


def _dll_read():
    raw = hostshell.powershell(_PS_DLL.replace("__ROOT__", config.STACK_ROOT), timeout=45)
    d = json.loads(raw.strip().splitlines()[-1])
    return {"read": True, "error": "", "dll_md5": d.get("dll") or "", "lm_start": d.get("lm") or "", "log_file": d.get("file") or "",
            "head": d.get("head") or "", "found": bool(d.get("found")), "l09_ok": bool(d.get("ok")), "total": d.get("total") or "",
            "world_line": d.get("world") or "", "gate_fail": int(d.get("fail") or 0), "gate_fail_last": d.get("fail_last") or "",
            "gate_fail_now": bool(d.get("fail_now"))}


def dll_state(force=False):
    """DLL-часть: {"read", "error", "dll_md5", "dll_known", "lm_start", "active", "log_file", "head", "total"}. active: True — в последнем
    запуске LoginManager «[OK] L09_LoginMaintenance»; False — запуск найден, L09 в нём нет; None — журнал не прочитан / запуска нет."""
    with _dll_lock:
        if not force and _dll_cache["data"] and time.time() - _dll_cache["at"] < DLL_TTL_S:
            return _dll_cache["data"]
    try:
        d = DLL_READ() if DLL_READ else _dll_read()
    except (hostshell.HostError, ValueError, KeyError, IndexError) as ex:
        d = {"read": False, "error": str(ex)[:200]}
    if d.get("read"):
        d["dll_known"] = d.get("dll_md5") in L09_DLL_MD5
        d["active"] = d["l09_ok"] if d.get("found") else None
        # ★ ревизия 43б Н-4: гейт входа в мир — по строке установки L09 («WorldGate=1» / «WorldGate=0»); строки нет — None
        d["world"] = {"on": True, "off": False}.get(d.get("world_line") or "") if d["active"] else (False if d["active"] is False else None)
        if not d.get("found"):
            d["error"] = "в журнале патчей нет запуска"
    else:
        d.update(dll_known=None, active=None, world=None)
    with _dll_lock:
        _dll_cache.update(at=time.time(), data=d)
    return d


def players_state():
    """Кто в игре по мосту (учётки сессий вне 1…5000 и служебные) и вошедшие по БД. «Не прочитано» ≠ «никого»."""
    out = {"bridge_read": False, "players": [], "operators": [], "bridge_error": "", "db_read": False, "db_logged": None,
           "db_error": "", "gm_outside": None}
    try:
        fresh = [n for n in bridge.nodes() if n["fresh"]]
        if not fresh:
            out["bridge_error"] = "нет ни одного узла моста с пульсом"
        else:
            rows = bridge._t().presence(None)                 # без «пусто при сбое» bridge.presence: сбой — исключение
            for r in rows:
                uid = int(r.get("session_uid") or r["Userindex"])
                item = {"uid": uid, "owner": int(r["Userindex"]), "char": r.get("charname"), "node": r["node"], "map": r.get("map")}
                (out["operators"] if 1 <= uid <= OPERATOR_MAX_UID else out["players"]).append(item)
            out["bridge_read"] = True
    except (db.DbError, bridge.BridgeError, KeyError, TypeError, ValueError) as ex:
        out["bridge_error"] = str(ex)[:200]
    try:
        with db.GameReader("asdastoryop") as op:
            out["db_logged"] = int(op.one("SELECT COUNT(*) AS n FROM dbo.Us_member WHERE Flag = 1 AND (Userindex < 1 OR Userindex > ?)",
                                          (OPERATOR_MAX_UID,))["n"])
        with db.GameReader("joy1") as j:
            out["gm_outside"] = [int(r["UserIndex"]) for r in j.rows("SELECT DISTINCT UserIndex FROM dbo.CharGmInfo WHERE UserIndex > ? "
                                                                      "ORDER BY UserIndex", (OPERATOR_MAX_UID,))]
        out["db_read"] = True
    except db.DbError as ex:
        out["db_error"] = str(ex)[:200]
    return out


def world_state(s, d, p=None):
    """★ ревизия 43б Н-4: закрыт ли вход в мир с выбора персонажа → {"closed": True / False / None, "text": предупреждение,
    "note": текст о сбоях гейта или None — поля text / note переводит api/server.py, TR_KEYS}. True — только при [OK] L09 + WorldGate=1 + md5 сборки L09 + процедуре adm.LoginMaintenanceGate."""
    n = (p["db_logged"] if p and p.get("db_read") and p.get("db_logged") is not None else "не прочитано")
    fail = None
    if d.get("read") and d.get("gate_fail"):
        fail = (GATE_FAIL_NOW % (d.get("gate_fail_last") or "?", d["gate_fail"]) if d.get("gate_fail_now")
                else GATE_FAIL_PAST % (d["gate_fail"], d.get("gate_fail_last") or "?"))
    if not d.get("read") or d.get("active") is None:
        return {"closed": None, "text": WORLD_UNKNOWN % WORLD_WHY_LOG, "note": fail}
    if d["active"] is False:
        return {"closed": False, "text": WORLD_OPEN % n, "note": fail}
    if not d.get("dll_known"):
        return {"closed": False, "text": WORLD_OPEN_DLL % (d.get("dll_md5") or "?", L09_DLL_MD5[0][:8], n), "note": fail}
    if d.get("world") is False:
        return {"closed": False, "text": WORLD_OPEN_NOGATE % n, "note": fail}
    if d.get("world") is None:
        return {"closed": None, "text": WORLD_UNKNOWN % WORLD_WHY_LINE, "note": fail}
    if s.get("world_gate") is None:
        return {"closed": None, "text": WORLD_UNKNOWN % WORLD_WHY_SQL, "note": fail}
    if not s["world_gate"]:
        return {"closed": False, "text": WORLD_OPEN_PROC % n, "note": fail}
    return {"closed": True, "text": WORLD_CLOSED, "note": fail}


def state(force=False):
    """Всё для «Состояния» и консоли."""
    s = sql_state()
    d = dll_state(force)
    p = players_state()
    ready = bool(s["read"] and s["table"] and s["gate"])
    return {"sql": s, "dll": d, "players": p, "ready": ready, "on": ready and s.get("mode") == 1, "world": world_state(s, d, p),
            "operator_max": OPERATOR_MAX_UID, "status": STATUS, "dll_md5": L09_DLL_MD5[0]}


# ─────────────────────────────── проверки ───────────────────────────────

def _reason(p):
    r = str(p.get("reason") or "").strip()
    if len(r) > REASON_MAX:
        raise OpRefused("причина длиннее %d символов" % REASON_MAX)
    return r


def _announce_check(ctx, p, required):
    """Текст объявления (проверка live.announce без опроса моста) → текст или ''. required — без него только с silent."""
    text = str(p.get("announce") or "").strip()
    if not text:
        if required and str(p.get("silent") or "") != SILENT:
            raise OpRefused("включение без объявления: нужен текст объявления в игру или явное «без объявления» (silent = silent)")
        return ""
    from core.ops import REGISTRY
    REGISTRY["live.announce"].schedule_check(ctx, {"text": text})
    return text


def _ready(s, want_mode):
    """Состояние входа допускает действие → None, иначе OpRefused."""
    if not s["read"]:
        raise OpRefused("состояние входа не прочитано (%s) — ничего не делаю" % (s["error"] or "Joy1"))
    if not s["table"] or s["gate"] is False:
        raise OpRefused(NEED_SQL)
    if s["gate"] is None:
        raise OpRefused("тело UPUserLogin не прочитано (нет права VIEW DEFINITION у asda_admin) — врезка L09 не подтверждена, ничего не делаю")
    if s["mode"] == want_mode and want_mode:
        raise OpRefused("режим обслуживания уже включён (с %s, %s)" % (s.get("changed_at") or "?", s.get("changed_by") or "?"))
    if s["mode"] == want_mode:
        raise OpRefused("режим обслуживания уже выключен (с %s, %s)" % (s.get("changed_at") or "?", s.get("changed_by") or "?"))


def _dll_warn(d):
    if not d.get("read"):
        return DLL_UNREAD % (d.get("error") or "?")
    if d.get("active") is None:
        return DLL_UNREAD % (d.get("error") or "запуска нет")
    if not d["active"]:
        return NEED_DLL
    return None


def _set(ctx, mode, reason):
    """adm.LoginMaintenanceSet (логин asda_ops) → строка состояния."""
    with db.GameWriter("joy1") as w:
        rows = w.rows("SET NOCOUNT ON; EXEC adm.LoginMaintenanceSet ?, ?, ?", (int(mode), ctx.login[:64], reason or None))
        w.commit()
    if not rows:
        raise RuntimeError("adm.LoginMaintenanceSet не вернула состояние")
    r = rows[0]
    return {"old": int(r["OldMode"]), "mode": int(r["Mode"]), "refused": int(r["Refused"] or 0), "admitted": int(r["Admitted"] or 0)}


class _MaintOp(Operation):
    perm, reversible, schedule_runner, confirm_word = "server.maintenance", False, "service", CONFIRM
    want = 1

    def target(self, p):
        return "login"

    def schedule_check(self, ctx, p):
        if str(p.get("confirm") or "") != CONFIRM:
            raise OpRefused("нужно подтверждение: ключ --confirm-maint (в панели — галочка подтверждения)")
        _reason(p)
        kick = str(p.get("kick") or "")
        if kick not in ("", KICK):
            raise OpRefused("неверный выбор отключения (можно: не отключать или players)")
        if kick and self.want == 0:                   # ★ ревизия 43 (мелочь 3): при постановке задания, а не только в срок
            raise OpRefused("при выключении отключать игроков незачем")
        if kick and not ctx.can("players.kick"):
            raise OpRefused("отключить игроков можно только с правом «players.kick»")
        if str(p.get("partial") or "") not in ("", PARTIAL):
            raise OpRefused("неверный выбор частичного объявления (можно: нет или partial)")
        _announce_check(ctx, p, self.want == 1)

    def verify(self, ctx, p, res):
        s = sql_state()
        if s.get("mode") != self.want:
            raise RuntimeError("после записи режим обслуживания = %s, ожидалось %d" % (s.get("mode"), self.want))


@register
class MaintOn(_MaintOp):
    name, title, two_factor = "maint.on", "Вход: включить режим обслуживания (только служебные 1…5000)", True
    want = 1

    def preview(self, ctx, p):
        self.schedule_check(ctx, p)
        s = sql_state()
        _ready(s, 1)
        d = dll_state()
        pl = players_state()
        text = _announce_check(ctx, p, True)
        warn = []
        if text:
            warn.append("сначала объявление в игру (мост): «%s»" % text)
        else:
            warn.append("без объявления в игру (выбрано явно)")
        w = _dll_warn(d)
        if w:
            warn.append(w)
        if not pl["bridge_read"]:
            warn.append("кто в игре по данным моста — не прочитано (%s)" % (pl["bridge_error"] or "?"))
            if p.get("kick"):
                raise OpRefused("выбрано отключить игроков, а кто в игре по данным моста не прочитано — ничего не делаю")
        elif pl["players"]:
            if p.get("kick"):
                warn.append("после включения будут отключены мостом игроки вне 1…5000: %d (штатный выход с записью)" % len(_uids(pl)))
            else:
                warn.append("в игре игроков вне 1…5000: %d — они НЕ отключаются (отключить — галочка «отключить игроков» или live.kick)"
                            % len(_uids(pl)))
        # ★ ревизия 43 С-1 / 43б Н-4: про уже вошедших — по состоянию гейта входа в мир: «закрыт» только если сходится всё (DLL, строка
        #   установки WorldGate=1, md5 сборки, процедура adm.LoginMaintenanceGate); Н-3 — сбои гейта отдельной строкой
        ws = world_state(s, d, pl)
        if ws["closed"] is not None or d.get("read") and d.get("active") is not None:
            warn.append(ws["text"])
        if ws["note"]:
            warn.append(ws["note"])
        warn.append(OVERLAP_NOTE)
        if pl["db_read"] and pl["db_logged"]:
            warn.append("вошли по БД (Us_member.Flag = 1) учёток вне 1…5000: %d" % pl["db_logged"])
        if text and p.get("partial") == PARTIAL:
            warn.append("объявление, дошедшее не до всех узлов моста, режим НЕ остановит (выбрано явно)")
        if pl["db_read"] and pl["gm_outside"]:
            warn.append("у учёток вне 1…5000 есть строка CharGmInfo (%s) — режим их не пустит, допуск только по номеру 1…5000"
                        % ", ".join(str(u) for u in pl["gm_outside"][:12]))
        return {"text": "включить режим обслуживания: вход только служебным учёткам 1…5000, остальным — статус %d" % STATUS,
                "warnings": warn, "announce": text, "kick": str(p.get("kick") or ""), "reason": _reason(p),
                "expect": {"mode": s["mode"]}}

    def apply(self, ctx, p, prev):
        if ctx.via == "web":
            auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())
        s = sql_state()                               # перепроверка: состояние могло смениться после предпросмотра
        _ready(s, 1)
        sent = None
        if prev["announce"]:
            try:
                ar = ops_run(ctx, "live.announce", {"text": prev["announce"], "rgb": ANNOUNCE_RGB})
            except OpRefused as ex:
                raise OpRefused("объявление не разослано (%s) — режим обслуживания НЕ включён (без объявления — явное «без объявления»)"
                                % ex)
            sent = ar["message"]
            failed = (ar.get("result") or {}).get("failed") or []
            if failed and str(p.get("partial") or "") != PARTIAL:   # ★ ревизия 43 Н-3: часть узлов не получила — не включать молча
                raise OpRefused("объявление дошло не до всех узлов моста (не вышло: %s) — режим обслуживания НЕ включён, часть игроков "
                                "объявление уже получила (включить всё равно — явный выбор partial)" % ", ".join(failed))
        r = _set(ctx, 1, prev["reason"])
        parts = []                                    # подробности — через «; » в скобках: перевод EN по частям (core/i18n.py, NESTED_AT)
        if r["old"] == 1:
            parts.append("он уже был включён к моменту записи")
        if sent:
            parts.append("объявление: %s" % sent)
        kicked = None
        if prev["kick"]:
            kicked = _kick_players(ctx)
            parts.append(kicked["text"])
        msg = ON_DONE + (" (%s)" % "; ".join(parts) if parts else "")
        return {"before": {"mode": r["old"]}, "after": {"mode": r["mode"], "announce": sent, "kicked": kicked}, "message": msg}


@register
class MaintOff(_MaintOp):
    # ★ ревизия 43 (мелочь 7) — РЕШЕНИЕ: выключение без второго фактора. Оно только возвращает обычный вход (ничего не закрывает и никого не
    #   отключает); право server.maintenance, подтверждение и журнал остаются. Второй фактор — у включения (закрывает вход всем игрокам).
    name, title, two_factor = "maint.off", "Вход: выключить режим обслуживания", False
    want = 0

    def preview(self, ctx, p):
        self.schedule_check(ctx, p)
        if p.get("kick"):
            raise OpRefused("при выключении отключать игроков незачем")
        s = sql_state()
        _ready(s, 0)
        text = _announce_check(ctx, p, False)
        warn = ["за время режима отказано входов: %d, допущено служебных: %d" % (s.get("refused") or 0, s.get("admitted") or 0)]
        if text:
            warn.append("после выключения — объявление в игру (мост): «%s»" % text)
        return {"text": "выключить режим обслуживания (включён %s, %s)" % (s.get("changed_at") or "?", s.get("changed_by") or "?"),
                "warnings": warn, "announce": text, "reason": _reason(p), "expect": {"mode": s["mode"]}}

    def apply(self, ctx, p, prev):
        s = sql_state()
        _ready(s, 0)
        r = _set(ctx, 0, prev["reason"])
        msg = "режим обслуживания выключен (отказано входов: %d, допущено служебных: %d)" % (r["refused"], r["admitted"])
        sent = None
        if prev["announce"]:
            try:
                sent = ops_run(ctx, "live.announce", {"text": prev["announce"], "rgb": ANNOUNCE_RGB})["message"]
                msg += " — объявление: %s" % sent
            except OpRefused as ex:
                msg += " — объявление не разослано: %s" % ex
        return {"before": {"mode": r["old"]}, "after": {"mode": r["mode"], "announce": sent}, "message": msg}


def _uids(pl):
    return sorted({x["uid"] for x in pl["players"]})


def _kick_players(ctx):
    """Отключить мостом всех в игре вне 1…5000 (существующий кик P127 — bridge.kick_and_wait, запись live.kick в журнал).
    Сбой — не отказ (режим уже включён): итог с перечнем."""
    from core import ops
    pl = players_state()
    if not pl["bridge_read"]:
        return {"text": "игроков не отключал: кто в игре по данным моста не прочитано (%s)" % (pl["bridge_error"] or "?"), "kicked": []}
    uids = _uids(pl)
    if not uids:
        return {"text": "отключать некого: в игре нет игроков вне 1…5000", "kicked": []}
    try:
        kicked = ops._kick(ctx, "maint.on", "login", {"kick": KICK}, uids, "режим обслуживания")
    except OpRefused as ex:
        return {"text": "отключение игроков не завершено: %s" % ex, "kicked": []}
    return {"text": "отключено мостом: %d" % len(kicked), "kicked": kicked}
