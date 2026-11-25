# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
r"""dbstand.py — восстановление бэкапа панели на СТЕНД LocalDB ПК владельца (шаг А5.7, операция db.restore_stand; 21.11.2026).

ТОЛЬКО СТЕНД. Цель — отдельный экземпляр LocalDB этого ПК STAND_INSTANCE ((localdb)\AstoryDbStand), база <имя>_stand_<номер бэкапа>.
  Живой сервер целью не бывает: строка подключения стенда собирается только здесь, из константы (localdb), а имя базы стенда обязано
  иметь вид <база>_stand_<число> и не совпадать ни с одной базой списка бэкапов. Восстановления на живой сервер нет вовсе (dbbackup.db.restore).
ШАГИ (консолью ПК, право db.stand — только владелец; служба на сервере и браузер — отказ):
  1. строка adm.dbbackup: готовый, проверенный (VERIFYONLY) бэкап; md5 из строки (нет — снимается на сервере по SSH);
  2. место на диске стенда: файл бэкапа + файлы базы в размерах из RESTORE FILELISTONLY (журнал восстанавливается полного размера) + запас;
  3. скачивание scp в папку стенда STAND_DIR (профиль пользователя, не репозиторий), сверка md5 — не совпало: файл стирается, отказ;
  4. RESTORE DATABASE … WITH MOVE (файлы — в папку стенда), DBCC CHECKDB … WITH NO_INFOMSGS, число строк таблиц против снимка службы
     сразу после бэкапа (снимок снят через секунды после бэкапа живой базы — расхождения в живых таблицах показываются, не считаются ошибкой);
  5. итог — в adm.dbbackup (stand_ok, stand_result) и журнал; файл бэкапа с ПК удаляется ВСЕГДА (данные игроков), база стенда удаляется,
     если не задан keep (тогда в итоге — где она лежит).
Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess

from core import config, db
from core.ops import Operation, OpRefused, register
from domains import dbbackup as B

STAND_INSTANCE = "AstoryDbStand"
STAND_SERVER = "(localdb)\\" + STAND_INSTANCE
STAND_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Astory", "AdminCenter", "db_stand")
RESERVE_BYTES = 5 << 30          # запас места на диске стенда
SCP_TIMEOUT_S = 6 * 3600
RESTORE_TIMEOUT_S = 6 * 3600
NAME_RX = re.compile(r"^[A-Za-z0-9]+_stand_\d+$")

# подмены самотеста (None — настоящие): DOWNLOAD(remote, local) → None; CONNECT(database) → соединение pyodbc с автофиксацией
DOWNLOAD = None
CONNECT = None
LOG = print                      # ход стенда (консоль); самотест подменяет


def stand_name(dbname, bid):
    """Имя базы стенда → строка; не того вида или совпадает с базой списка — отказ."""
    n = "%s_stand_%d" % (re.sub(r"[^A-Za-z0-9]", "", dbname), int(bid))
    if not NAME_RX.match(n) or n.lower() in {x.lower() for x in B.allowed()}:
        raise OpRefused("имя базы стенда %s недопустимо — восстановление не начато" % n)
    return n


def _connect(database="master"):
    """Соединение со стендом LocalDB (Windows-вход владельца ПК). Строка — только из константы (localdb)."""
    if CONNECT:
        return CONNECT(database)
    import pyodbc
    if not STAND_SERVER.lower().startswith("(localdb)\\"):
        raise OpRefused("стенд — только LocalDB этого ПК")
    subprocess.run(["sqllocaldb", "create", STAND_INSTANCE], capture_output=True, timeout=120)
    subprocess.run(["sqllocaldb", "start", STAND_INSTANCE], capture_output=True, timeout=120)
    # своя строка на соединение (APP=…): пул ODBC не отдаёт повторно соединение, убитое ROLLBACK IMMEDIATE прошлой уборки
    cn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=%s;DATABASE=%s;Trusted_Connection=yes;APP=AstoryDbStand-%s;"
                        % (STAND_SERVER, database, os.urandom(4).hex()),
                        autocommit=True, timeout=60)
    cn.timeout = RESTORE_TIMEOUT_S
    return cn


def _scp(remote, local):
    if DOWNLOAD:
        return DOWNLOAD(remote, local)
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
    r = subprocess.run([exe if os.path.exists(exe) else "scp", "-i", config.SSH_KEY, "-o", "BatchMode=yes",
                        "%s:%s" % (config.SSH_HOST, remote.replace("\\", "/")), local], capture_output=True, timeout=SCP_TIMEOUT_S)
    if r.returncode != 0:
        raise OpRefused("скачивание бэкапа не удалось (scp, код %d): %s" % (r.returncode, r.stderr.decode("utf-8", "replace").strip()[:300]))


def _gb(b):
    return "%.1f" % (b / 1073741824.0)


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _q(cn, sql, *params):
    cur = cn.cursor()
    cur.execute(sql, *params)
    rows = []
    while True:
        if cur.description and not rows:
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not cur.nextset():
            break
    return rows


def _drop(cn, name):
    """Удалить базу стенда и её файлы в STAND_DIR. ★ ревизия 47 В-2: база после оборванного RESTORE — в состоянии RESTORING, ALTER DATABASE
    ей запрещён (5052, воспроизведено на LocalDB) — тогда DROP DATABASE без ALTER; файлы <имя>_* удаляются и при ошибке DROP (→ ошибки)."""
    errs = []
    if not NAME_RX.match(name):
        raise OpRefused("имя базы стенда %s недопустимо — восстановление не начато" % name)
    try:
        st = _q(cn, "SELECT state_desc FROM sys.databases WHERE name = ?", name)
        if st:
            if st[0]["state_desc"] == "ONLINE":
                cn.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            cn.cursor().execute("DROP DATABASE [%s]" % name)
    except Exception as ex:
        errs.append("DROP %s: %s" % (name, B._reason(ex) if ex.__class__.__module__ == "pyodbc" else ex))
    errs += _rm_files(name + "_")
    return errs


def _rm_files(prefix="", spare=()):
    """Удалить файлы папки стенда (с префиксом или все, кроме файлов баз spare) → [ошибки]. Папка — только наша (профиль пользователя)."""
    errs = []
    if not os.path.isdir(STAND_DIR):
        return errs
    for f in os.listdir(STAND_DIR):
        p = os.path.join(STAND_DIR, f)
        if any(f.startswith(k + "_") for k in spare):
            continue
        if os.path.isfile(p) and f.startswith(prefix):
            try:
                os.remove(p)
            except OSError as ex:
                errs.append("%s: %s" % (f, ex))
    return errs


KEPT_PROP = "astory_kept"       # ★ ревизия 48 Н-5: метка базы стенда, оставленной --keep (свойство базы; уборка её не трогает без --drop-kept)


def kept_dbs(cn):
    """Базы стенда, оставленные --keep (метка KEPT_PROP) → [имя]."""
    out = []
    for r in _q(cn, "SELECT name FROM sys.databases WHERE name LIKE '%[_]stand[_]%' AND state_desc = 'ONLINE'"):
        if NAME_RX.match(r["name"]) and _q(cn, "SELECT 1 AS k FROM [%s].sys.extended_properties WHERE class = 0 AND name = ?" % r["name"], KEPT_PROP):
            out.append(r["name"])
    return out


def mark_kept(cn, name):
    if not NAME_RX.match(name):
        raise OpRefused("имя базы стенда %s недопустимо — восстановление не начато" % name)
    cn.cursor().execute("EXEC [%s].sys.sp_addextendedproperty @name = ?, @value = ?" % name, KEPT_PROP, B.utc_now().isoformat(sep=" "))


def cleanup_leftovers(cn, log=print, drop_kept=False):
    """★ ревизия 47 В-2: хвосты прошлых прогонов (процесс убит, ПК выключен посреди) — базы <…>_stand_<№> экземпляра стенда и файлы папки
    стенда → {"dbs": [...], "files": n, "errors": [...], "kept": [...]}. ★ ревизия 48 Н-5: базы, оставленные --keep (для ручного переноса),
    и их файлы НЕ трогаются, если не задан drop_kept (--drop-kept)."""
    out = {"dbs": [], "files": 0, "errors": [], "kept": []}
    spare = [] if drop_kept else kept_dbs(cn)
    out["kept"] = spare
    if os.path.isdir(STAND_DIR):                       # сколько файлов было (до удаления баз — с их файлами)
        out["files"] = len([f for f in os.listdir(STAND_DIR) if os.path.isfile(os.path.join(STAND_DIR, f))
                            and not any(f.startswith(k + "_") for k in spare)])
    for r in _q(cn, "SELECT name FROM sys.databases WHERE name LIKE '%[_]stand[_]%'"):
        if NAME_RX.match(r["name"]) and r["name"] not in spare:
            out["errors"] += _drop(cn, r["name"])
            out["dbs"].append(r["name"])
    out["errors"] += _rm_files("", spare)
    if spare:
        log("оставлены базы стенда (--keep, без --drop-kept): %s" % ", ".join(spare))
    if out["dbs"] or out["files"]:
        log("убраны остатки прошлых прогонов стенда: баз %d, файлов %d" % (len(out["dbs"]), out["files"]))
    return out


def compare_counts(snap, got):
    """Снимок службы после бэкапа против стенда → (не хватает таблиц, [(таблица, снимок, стенд)] расхождений, совпало)."""
    missing = sorted(t for t in snap if t not in got)
    diff = sorted((t, snap[t], got[t]) for t in snap if t in got and int(snap[t]) != int(got[t]))
    return missing, diff, len(snap) - len(missing) - len(diff)


def run_stand(row, by, keep=False, log=print, drop_kept=False):
    """Стенд одного бэкапа (строка adm.dbbackup) → dict итога (ok, …). Отказы — OpRefused до скачивания."""
    name = stand_name(row["db"], row["id"])
    remote = row["file_path"]
    os.makedirs(STAND_DIR, exist_ok=True)
    local = os.path.join(STAND_DIR, os.path.basename(remote.replace("\\", "/")))
    md5 = row.get("md5")
    size = row.get("file_bytes")
    if not md5 or not size:
        log("md5 файла в журнале нет — снимаю на сервере…")
        size, md5 = B._file_info(remote)
    free = shutil.disk_usage(STAND_DIR).free
    if free < int(size) * 2 + RESERVE_BYTES:
        raise OpRefused("мало места на диске стенда (%s): свободно %s ГБ, нужно для начала не меньше %s ГБ — восстановление не начато"
                        % (STAND_DIR, _gb(free), _gb(int(size) * 2 + RESERVE_BYTES)))
    res = {"ok": False, "stand": STAND_SERVER, "database": name, "kept": False, "md5": md5, "checkdb": None, "counts": None, "error": None,
           "at_utc": B.utc_now().isoformat(sep=" ")}
    cn = None
    try:
        cn = _connect("master")
        if not drop_kept and name in kept_dbs(cn):
            raise OpRefused("база стенда %s оставлена прошлым прогоном (--keep) — заменить её можно только с ключом --drop-kept, восстановление не начато"
                            % name)
        res["leftovers"] = cleanup_leftovers(cn, log, drop_kept)   # ★ ревизия 47 В-2: хвосты прошлых прогонов — до скачивания
        log("скачиваю %s (%.1f МБ) в папку стенда…" % (remote, int(size) / 1048576.0))
        _scp(remote, local)
        got = _md5(local)
        if got != md5:
            raise OpRefused("md5 скачанного файла не совпал (%s, на сервере %s) — файл стёрт, восстановление не начато" % (got, md5))
        log("md5 совпал: %s" % got)
        files = _q(cn, "RESTORE FILELISTONLY FROM DISK = ? WITH FILE = ?", local, int(row.get("position") or 1))
        need = sum(int(f["Size"]) for f in files) + RESERVE_BYTES
        free = shutil.disk_usage(STAND_DIR).free
        if free < need:
            raise OpRefused("мало места на диске стенда под файлы базы (журнал восстанавливается полного размера): свободно %s ГБ, нужно %s ГБ "
                            "— восстановление не начато" % (_gb(free), _gb(need)))
        errs = _drop(cn, name)
        if errs:
            raise RuntimeError("прежняя база стенда %s не удалена: %s" % (name, ", ".join(errs)[:300]))
        moves, params = [], []
        for i, f in enumerate(files):
            ext = {"L": ".ldf", "D": ".mdf" if i == 0 else ".ndf"}.get(str(f["Type"]), ".ndf")
            moves.append("MOVE ? TO ?")
            params += [f["LogicalName"], os.path.join(STAND_DIR, "%s_%d%s" % (name, i, ext))]
        log("RESTORE в %s.%s (файлов %d, %.1f ГБ)…" % (STAND_SERVER, name, len(files), need / 1073741824.0))
        cur = cn.cursor()
        cur.execute("RESTORE DATABASE [%s] FROM DISK = ? WITH FILE = ?, %s, RECOVERY, CHECKSUM" % (name, ", ".join(moves)),
                    local, int(row.get("position") or 1), *params)
        while cur.nextset():                              # ошибки RESTORE приходят при разборе сообщений
            pass
        if not _q(cn, "SELECT state_desc FROM sys.databases WHERE name = ? AND state_desc = 'ONLINE'", name):
            raise RuntimeError("база стенда после RESTORE не в состоянии ONLINE")
        log("DBCC CHECKDB…")
        bad = check_db(cn, name)                          # ★ ревизия 47 Н-2: все наборы и сообщения CHECKDB
        res["checkdb"] = "ok" if not bad else bad[:20]
        if bad:
            raise RuntimeError("DBCC CHECKDB нашёл ошибки: %s" % "; ".join(bad)[:300])
        sc = _connect(name)
        try:
            stand = {str(x["t"]): int(x["n"] or 0) for x in _q(sc, B.COUNT_SQL)}
        finally:
            sc.close()
        snap = json.loads(row["counts"]) if row.get("counts") else None
        if snap is None:
            res["counts"] = {"tables": len(stand), "snapshot": False}
        else:
            missing, diff, same = compare_counts(snap, stand)
            res["counts"] = {"tables": len(stand), "snapshot": True, "same": same, "missing": missing[:50],
                             "diff": [{"t": t, "snap": a, "stand": b} for t, a, b in diff[:50]], "diff_n": len(diff)}
            if missing:
                raise RuntimeError("в базе стенда нет таблиц из снимка: %s" % ", ".join(missing[:10]))
        res["ok"] = True
    except OpRefused as ex:
        res["error"] = str(ex)
        raise
    except Exception as ex:
        res["error"] = "%s: %s" % (ex.__class__.__name__, (B._reason(ex) if ex.__class__.__module__ == "pyodbc" else str(ex))[:600])
    finally:
        # ★ ревизия 47 В-2: каждая уборка — своим try (исходная ошибка не вытесняется), итог в журнал пишется всегда
        clean = []
        try:
            if os.path.exists(local):
                os.remove(local)                             # данные игроков на ПК не оставляем
        except OSError as ex:
            clean.append("%s: %s" % (os.path.basename(local), ex))
        if cn is not None:
            if keep and res["ok"]:
                try:
                    mark_kept(cn, name)                      # ★ ревизия 48 Н-5: следующий прогон стенда её не удалит без --drop-kept
                    res["kept"] = True
                except Exception as ex:
                    clean.append("метка --keep %s: %s" % (name, ex))
            else:
                try:
                    errs = _drop(cn, name)
                    if errs:                                 # соединение могло оборваться (SINGLE_USER … ROLLBACK IMMEDIATE, сбой) — ещё раз новым
                        c2 = _connect("master")
                        try:
                            errs = _drop(c2, name)
                        finally:
                            c2.close()
                    clean += errs
                except Exception as ex:
                    clean.append("DROP %s: %s" % (name, ex))
            try:
                cn.close()
            except Exception:
                pass
        if clean:
            res["cleanup_errors"] = clean[:10]
            if res["ok"]:
                res["ok"] = False
                res["error"] = "проверка прошла, но уборка стенда не удалась: %s" % ", ".join(clean)[:300]   # ревизия 48 (мелочь 7): без «; »
        try:
            B._rows("SET NOCOUNT ON; EXEC adm.DbBackupStand @id = ?, @ok = ?, @result = ?",
                    (int(row["id"]), 1 if res["ok"] else 0, json.dumps(res, ensure_ascii=False, default=str)))
        except Exception as ex:
            res["record_error"] = str(ex)[:300]
    return res


def check_db(cn, name):
    """DBCC CHECKDB … WITH NO_INFOMSGS, ALL_ERRORMSGS, TABLERESULTS: все наборы (строка набора — ошибка согласованности) и ошибки драйвера
    → [тексты ошибок] (пусто — база цела)."""
    import pyodbc
    bad = []
    cur = cn.cursor()
    try:
        cur.execute("DBCC CHECKDB ([%s]) WITH NO_INFOMSGS, ALL_ERRORMSGS, TABLERESULTS" % name)
        while True:
            if cur.description:
                cols = [d[0] for d in cur.description]
                for r in cur.fetchall():
                    d = dict(zip(cols, r))
                    bad.append("%s: %s" % (d.get("Error"), str(d.get("MessageText") or "")[:200]))
            if not cur.nextset():
                break
    except pyodbc.Error as ex:
        bad.append(B._reason(ex)[:500])
    return bad


@register
class DbRestoreStand(Operation):
    name, title, perm, reversible = "db.restore_stand", "Бэкапы БД: восстановить на стенд LocalDB ПК (проверка восстановимости)", "db.stand", False

    def target(self, p):
        return "dbbackup:%s" % p.get("id")

    def preview(self, ctx, p):
        if ctx.via != "cli" or config.get().on_server:
            raise OpRefused("стенд LocalDB — только консолью на ПК владельца: python asda_admin.py db stand --id N")
        try:
            bid = int(p.get("id"))
        except (TypeError, ValueError):
            raise OpRefused("не указан номер бэкапа")
        r = B.get(bid)
        if not r or r["status"] != "done":
            raise OpRefused("готового бэкапа панели №%s нет (удалён, не завершён или не панели)" % bid)
        if not r["verified"]:
            raise OpRefused("бэкап №%d не прошёл проверку VERIFYONLY — на стенд не восстанавливается" % bid)
        if not B.safe_file(B.folder()["folder"], r):              # скачиваем только файл панели из её папки (путь — в команду scp)
            raise OpRefused("файл бэкапа №%d не в папке панели или с чужим именем — на стенд не восстанавливается" % bid)
        name = stand_name(r["db"], bid)
        warn = ["в бэкапе данные игроков: файл скачивается в %s и стирается после проверки%s"
                % (STAND_DIR, "" if p.get("keep") else ", база стенда тоже удаляется"),
                "живой сервер не затрагивается: только скачивание файла по SSH"]
        try:                                           # ★ ревизия 48 Н-5: что станет с оставленными --keep базами — заранее
            cn = _connect("master")
            try:
                kept = kept_dbs(cn)
            finally:
                cn.close()
        except Exception as ex:
            kept = None
            warn.append("оставленные --keep базы стенда не прочитаны (%s)" % ex.__class__.__name__)
        if kept and p.get("drop_kept"):
            warn.append("будут удалены оставленные --keep базы стенда: %s" % ", ".join(kept))
        elif kept:
            warn.append("оставленные --keep базы стенда не трогаются: %s (удалить — ключ --drop-kept)" % ", ".join(kept))
            if name in kept:
                raise OpRefused("база стенда %s оставлена прошлым прогоном (--keep) — заменить её можно только с ключом --drop-kept, восстановление не начато"
                                % name)
        return {"text": "восстановить бэкап №%d (%s, %s) на стенд %s, база %s" % (bid, r["db"], B._mb(r["backup_bytes"]), STAND_SERVER, name),
                "id": bid, "warnings": warn}

    def apply(self, ctx, p, prev):
        r = B.get(prev["id"])
        res = run_stand(r, ctx.login, keep=bool(p.get("keep")), log=LOG, drop_kept=bool(p.get("drop_kept")))
        if not res["ok"]:
            raise B.BackupFailed("стенд бэкапа №%d: %s" % (prev["id"], res["error"]))
        c = res["counts"] or {}
        tail = ("база стенда оставлена: %s.%s" % (STAND_SERVER, res["database"])) if res["kept"] else "файл и база стенда удалены с ПК"
        if c.get("snapshot"):
            msg = ("стенд бэкапа №%d: восстановлен, CHECKDB без ошибок, таблиц %d, совпало со снимком %d, расхождений в живых таблицах %d — %s"
                   % (prev["id"], c["tables"], c["same"], c["diff_n"], tail))
        else:
            msg = "стенд бэкапа №%d: восстановлен, CHECKDB без ошибок, таблиц %d, снимка строк нет — %s" % (prev["id"], c.get("tables") or 0, tail)
        return {"before": None, "after": res, "message": msg}
