# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""hostshell.py — команды на машине сервера: локально (служба на @@ASTORY_SERVER_HOSTNAME@@) или по SSH (консоль на ПК). 16.11.2026.

Только SSH, шара \\\\@@ASTORY_SERVER_HOSTNAME@@ не используется (правило владельца 22.10: шара висит без таймаута).
PowerShell-скрипт передаётся через -EncodedCommand (UTF-16LE base64) — без проблем с кавычками; вывод — UTF-8.
Побочных эффектов при импорте нет.
"""
import base64
import os
import subprocess

from . import config

LONG_ENC = 7000           # ★ А5.9: длиннее (знаков base64) — скрипт через stdin, не в командной строке (предел cmd.exe на сервере 8191)
_NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW: без всплывающих окон консоли


class HostError(Exception):
    """Команда на сервере не выполнилась (код, таймаут, нет SSH)."""


def _ssh_exe():
    """Путь к ssh.exe (системный OpenSSH, иначе из PATH)."""
    p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    return p if os.path.exists(p) else "ssh"


def powershell(script, timeout=None):
    """Выполнить PowerShell-скрипт на сервере → stdout (str). Ошибка/таймаут → HostError."""
    cfg = config.get()
    timeout = timeout or cfg.ssh_timeout_s
    wrapped = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';" + script
    enc = base64.b64encode(wrapped.encode("utf-16-le")).decode("ascii")
    ps = ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc]
    feed = None
    if len(enc) > LONG_ENC:
        # ★ А5.9 (21.11): длинный скрипт (md5 сотен файлов стойки) в -EncodedCommand превышает предел командной строки cmd.exe на сервере
        #   (8191 знак — «Слишком длинная командная строка», код 1): тот же base64 идёт через stdin, короткая команда его читает и исполняет
        # ★ А6.13 (22.11): читатель — конвейер $input, не [Console]::In.ReadToEnd(): по SSH (sshd сервера, PowerShell 5.1) ReadToEnd и
        #   OpenStandardInput конец ввода не получают и ждут до таймаута (проверено 22.11: оба висят, $input и findstr — нет); на самом сервере
        #   (служба, без SSH) работают оба. Каждый длинный скрипт с ПК падал «не уложилась в N с» (живой блок data, md5 таблиц стойки)
        reader = "$b=@($input) -join ''; iex ([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($b.Trim())))"
        ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command", reader]
        feed = enc.encode("ascii")           # одна строка без переводов: $input отдаёт её целиком (join — на случай разбиения)
    if cfg.on_server:
        cmd = ps
    else:
        cmd = [_ssh_exe(), "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               config.SSH_HOST, " ".join(ps[:-1] + ['"%s"' % ps[-1]] if feed else ps)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW, input=feed)
    except subprocess.TimeoutExpired:
        raise HostError("команда на сервере не уложилась в %d с" % timeout)
    except OSError as ex:
        raise HostError("не удалось запустить %s: %s" % (cmd[0], ex))
    out = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip() or out.strip()
        raise HostError("код %d: %s" % (r.returncode, err[:400]))
    return out


def decode_text(b):
    """Байты файла → текст по метке кодировки (перепроверка 11 В1: patches.ini AsdaPatch пишет в UTF-16 LE с FF FE — как UTF-8 его
    секции не находились: потолок уровня читался 59, P96 «выключен»). Без метки — UTF-8, не вышло — cp1251."""
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16-le", "replace")
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "replace")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1251", "replace")


def read_server_file(path, timeout=None):
    """Текст файла на сервере (кодировка — по метке BOM, decode_text; для секретов и конфигов)."""
    cfg = config.get()
    if cfg.on_server:
        with open(path, "rb") as f:
            return decode_text(f.read())
    import base64
    raw = powershell("[Convert]::ToBase64String([IO.File]::ReadAllBytes('%s'))" % path.replace("'", "''"), timeout)
    return decode_text(base64.b64decode(raw.strip()))           # те же байты и то же правило, что на сервере


def read_server_bytes(path, timeout=None):
    """Сырые байты файла на сервере (двоичные таблицы, например SkillInfo.sif)."""
    cfg = config.get()
    if cfg.on_server:
        with open(path, "rb") as f:
            return f.read()
    import base64
    raw = powershell("[Convert]::ToBase64String([IO.File]::ReadAllBytes('%s'))" % path.replace("'", "''"), timeout)
    return base64.b64decode(raw.strip())
