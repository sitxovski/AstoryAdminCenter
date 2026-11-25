# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""otp_archive_push.py — архив старых OTP_Report LoginManager → данные службы админ-центра на сервере (★ ревизия 56 Н-2, 22.11.2026).

Зачем: живые OTP_Report в LoginMngError стойки начинаются с 17.10.2026, более старые (24.07–11.10) лежат только на ПК владельца
(@@ASTORY_DEV_ROOT_ESC@@\\_backup\\2026-10-12_otp_report_archive). Суточный отчёт панели (domains/acdaily) читает их как --otp-archive исходника.
Что делает:
  1. копирует архив во временную папку, МАСКИРУЯ хеши паролей: в поле «Pass …» строки «Login User ID …» каждая последовательность из 32
     шестнадцатеричных знаков заменяется на «*». MAC в хвосте поля (его берёт исходник, MAC_TAIL) остаётся; логин, IP и статус — как были.
     Хешей в копии быть не должно (проверка — отказ);
  2. (без --dry) scp в @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter\\otp_archive (дерево службы: права Administrators / SYSTEM, выкладка папку не трогает),
     сверка md5 каждого файла по SSH, атрибут «только чтение».
Запуск: python tools/otp_archive_push.py [--src ПАПКА] [--dry ПАПКА_ВЫВОДА]. Побочных эффектов при импорте нет.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = r"@@ASTORY_DEV_ROOT@@\_backup\2026-10-12_otp_report_archive"
NAME_RX = re.compile(r"^OTP_Report[^\\/]*\d{8}\.txt$", re.I)
PASS_RX = re.compile(rb"(Login User ID \S+?/\S*, Pass )(\S*)(, IP \S+)")
HEX32 = re.compile(rb"[0-9A-Fa-f]{32}")


def sanitize(data):
    """Байты файла → (байты без хешей в поле Pass, сколько хешей замаскировано)."""
    n = [0]

    def fix(m):
        val, k = HEX32.subn(b"*", m.group(2))
        n[0] += k
        return m.group(1) + val + m.group(3)
    return PASS_RX.sub(fix, data), n[0]


def build(src, out):
    """Копия архива без хешей → [(имя, md5, замаскировано)]. Остаток 32-hex в поле Pass — RuntimeError."""
    os.makedirs(out, exist_ok=True)
    res = []
    for name in sorted(os.listdir(src)):
        if not NAME_RX.match(name):
            continue
        with open(os.path.join(src, name), "rb") as f:
            data, k = sanitize(f.read())
        if any(HEX32.search(m.group(2)) for m in PASS_RX.finditer(data)):
            raise RuntimeError("в %s остался хеш в поле Pass" % name)
        with open(os.path.join(out, name), "wb") as f:
            f.write(data)
        res.append((name, hashlib.md5(data).hexdigest().upper(), k))
    return res


def push(files, tmp):
    sys.path.insert(0, HERE)
    from core import config, hostshell
    dst = config.SERVICE_ROOT + r"\otp_archive"
    hostshell.powershell("New-Item -ItemType Directory -Force -Path '%s' | Out-Null; Get-ChildItem '%s' -File | ForEach-Object { $_.IsReadOnly = $false }"
                         % (dst, dst), timeout=60)
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
    for name, _md5, _k in files:
        r = subprocess.run([exe if os.path.exists(exe) else "scp", "-q", "-i", config.SSH_KEY, "-o", "BatchMode=yes", os.path.join(tmp, name),
                            "%s:%s" % (config.SSH_HOST, (dst + "\\" + name).replace("\\", "/"))], capture_output=True, timeout=120)
        if r.returncode:
            raise RuntimeError("scp %s: %s" % (name, r.stderr.decode("utf-8", "replace")[:200]))
    out = hostshell.powershell("Get-ChildItem '%s' -File | ForEach-Object { $_.IsReadOnly = $true; (Get-FileHash -Algorithm MD5 $_.FullName).Hash + ' ' + $_.Name }"
                               % dst, timeout=120)
    got = dict(reversed(x.strip().split(" ", 1)) for x in out.splitlines() if len(x.strip().split(" ", 1)) == 2)
    bad = [n for n, m, _k in files if got.get(n) != m]
    return dst, len(files) - len(bad), bad


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = list(sys.argv[1:] if argv is None else argv)
    src, dry = DEFAULT_SRC, None
    while a:
        k = a.pop(0)
        if k in ("--src", "--dry") and a:
            if k == "--src":
                src = a.pop(0)
            else:
                dry = a.pop(0)
        else:
            print("ключи: [--src ПАПКА] [--dry ПАПКА_ВЫВОДА]")
            return 2
    tmp = dry or tempfile.mkdtemp(prefix="otp_arch_")
    files = build(src, tmp)
    print("файлов %d, хешей замаскировано %d → %s" % (len(files), sum(k for _n, _m, k in files), tmp))
    if dry:
        return 0
    dst, ok, bad = push(files, tmp)
    print("на сервере %s: md5 совпал у %d из %d%s" % (dst, ok, len(files), (", расхождения: " + ", ".join(bad)) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
