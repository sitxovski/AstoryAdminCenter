# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
r"""admin_center_ctl.py — запуск, остановка и состояние службы админ-центра Astory на сервере (только SSH). 24.11.2026.

Батник для двойного клика — AstoryAdminCenter/bat/AdminCenter.bat (описание там же, README.md).

КОМАНДЫ
  status              задача планировщика AsdaAdminCenter, процессы службы, ответ панели (GET /api/me → 401 = жива)
  start               запустить задачу (если служба уже работает — ничего не делает) и дождаться ответа панели
  stop [--yes]        остановить задачу и процессы службы (как шаг 3 deploy_admin_center.py); без --yes спросит подтверждение
  restart [--yes]     stop, затем start
  tunnel [--no-browser]   панель на этом ПК по адресу https://localhost:17890/ — SSH-туннель 127.0.0.1:17890 → сервер 127.0.0.1:17890
                      (25.11.2026: системный прокси ПК не пускает браузер к адресу VPN, localhost он обходит). Держится, пока открыто
                      окно (Ctrl+C — закрыть). Сертификат службы уже выписан и на localhost, заголовок Host localhost служба принимает.
                      Для службы вход идёт с 127.0.0.1 сервера (доверенный, как VPN): без ключа SSH туннеля нет.

Трогает ТОЛЬКО службу панели (задача AsdaAdminCenter, cmd run_service.bat и его python asda_admin.py serve).
Игровую стойку, задачу, брандмауэр, права и файлы службы не меняет. Бот Oracle на ПК (Discord, Telegram) — отдельно, не трогается.
Код возврата: 0 — ок; 1 — служба не отвечает / не поднялась; 2 — ошибка SSH; 3 — отменено.
Побочных эффектов при импорте нет.
"""
import os
import sys

STATE_PS = r"""
$t = '%(t)s'
$q = cmd /c "schtasks /Query /TN $t /FO LIST /V 2>&1"
$st = ($q | Select-String '^(Status|Состояние):' | Select-Object -First 1)
$last = ($q | Select-String '^(Last Run Time|Время прошлого запуска):' | Select-Object -First 1)
if ($LASTEXITCODE) { 'TASK=нет' } else { 'TASK=' + ($st -replace '^[^:]+:\s*','') ; 'LAST=' + ($last -replace '^[^:]+:\s*','') }
$py = @(Get-CimInstance Win32_Process | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*asda_admin.py*serve*' })
$wr = @(Get-CimInstance Win32_Process | ? { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*AdminCenter\run_service.bat*' })
'PY=' + (($py | %% { $_.ProcessId }) -join ',')
'WRAP=' + (($wr | %% { $_.ProcessId }) -join ',')
if ($py) { 'SINCE=' + ($py[0].CreationDate.ToString('yyyy-MM-dd HH:mm:ss')) }
"""

START_PS = r"""cmd /c "schtasks /Run /TN %(t)s 2>&1"; if ($LASTEXITCODE) { throw "schtasks /Run: код $LASTEXITCODE" }"""

# = шаг 3 deploy_admin_center.py: задача, затем python службы, затем обёртка run_service.bat с детьми (иначе она перезапустит python через 10 с)
STOP_PS = r"""
cmd /c "schtasks /End /TN %(t)s >nul 2>&1"
Get-CimInstance Win32_Process | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*asda_admin.py*serve*' } | %% { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process | ? { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*AdminCenter\run_service.bat*' } | %% { $c=$_.ProcessId; Get-CimInstance Win32_Process | ? { $_.ParentProcessId -eq $c } | %% { Stop-Process -Id $_.ProcessId -Force }; Stop-Process -Id $c -Force }
'остановлено'
"""


def _load():
    """Общие части выкладки (ps, wait_up, TASK, адрес) — импорт здесь, а не при загрузке модуля."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import deploy_admin_center as d
    return d


def state(d):
    """Состояние на сервере → dict(TASK, LAST, PY, WRAP, SINCE)."""
    out = d.ps(STATE_PS % {"t": d.TASK}, timeout=60)
    r = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            r[k.strip()] = v.strip()
    return r


def show(d, s):
    """Печать состояния."""
    print("Сервер:        %s (SSH)" % d.config.SERVER_VPN_IP)
    print("Задача:        %s — %s" % (d.TASK, s.get("TASK", "?")))
    if s.get("LAST"):
        print("Прошлый запуск: %s" % s["LAST"])
    print("Процесс панели: %s" % ("PID " + s["PY"] + (", с " + s["SINCE"] if s.get("SINCE") else "") if s.get("PY") else "нет"))
    print("Обёртка:       %s" % ("PID " + s["WRAP"] if s.get("WRAP") else "нет"))


def probe(d, tries):
    """Ответ панели → код 0 (жива) / 1."""
    code, msg = d.wait_up(tries=tries, pause=2.0)
    print("Панель:        %s" % (msg if code == 0 else "не отвечает (%s)" % msg))
    return 0 if code == 0 else 1


def confirm(yes, what):
    """Подтверждение остановки (панель станет недоступна, задания планировщика панели не идут)."""
    if yes:
        return True
    print("%s: панель станет недоступна всем пользователям, задания по расписанию панели не выполнятся до запуска." % what)
    try:
        return input("Продолжить? Введите ДА: ").strip().upper() in ("ДА", "YES", "Y", "Д")
    except EOFError:
        return False


def do_start(d):
    s = state(d)
    if s.get("PY"):
        print("Служба уже работает.")
        show(d, s)
        return probe(d, 1)
    print("Запуск задачи %s…" % d.TASK)
    d.ps(START_PS % {"t": d.TASK}, timeout=60)
    rc = probe(d, 20)
    show(d, state(d))
    return rc


def do_stop(d):
    print(d.ps(STOP_PS % {"t": d.TASK}, timeout=90).strip())
    s = state(d)
    show(d, s)
    return 1 if s.get("PY") or s.get("WRAP") else 0


LOCAL_PORT = 17890


def do_tunnel(d, browser):
    """SSH-туннель localhost → служба на сервере; ждёт, пока ssh не завершится (окно закрыто / Ctrl+C / обрыв)."""
    import socket
    import subprocess
    import threading
    import time
    import webbrowser
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", LOCAL_PORT)) == 0:
            print("Порт %d на этом ПК уже занят (туннель уже открыт в другом окне?). Откройте https://localhost:%d/" % (LOCAL_PORT, LOCAL_PORT))
            return 1
    cmd = [d.hostshell._ssh_exe(), "-i", d.config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
           "-N", "-L", "127.0.0.1:%d:127.0.0.1:%d" % (LOCAL_PORT, d.PORT), d.config.SSH_HOST]
    p = subprocess.Popen(cmd)
    url = "https://localhost:%d/" % LOCAL_PORT

    def ready():
        for _ in range(30):
            if p.poll() is not None:
                return
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", LOCAL_PORT)) == 0:
                    print("Туннель открыт: %s  (окно не закрывать; Ctrl+C — закрыть туннель)" % url, flush=True)
                    if browser:
                        webbrowser.open(url)
                    return
            time.sleep(0.5)
        print("Туннель не открылся за 15 с", flush=True)

    threading.Thread(target=ready, daemon=True).start()
    try:
        rc = p.wait()
    except KeyboardInterrupt:
        p.terminate()
        rc = 0
    print("Туннель закрыт (код ssh %s)." % rc)
    return 0 if rc in (0, None) else 2


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = [a for a in argv if not a.startswith("--")]
    yes = "--yes" in argv
    cmd = (args[0] if args else "status").lower()
    if cmd not in ("status", "start", "stop", "restart", "tunnel"):
        print(__doc__)
        return 3
    d = _load()
    try:
        if cmd == "status":
            s = state(d)
            show(d, s)
            return probe(d, 1)
        if cmd == "start":
            return do_start(d)
        if cmd == "tunnel":
            return do_tunnel(d, "--no-browser" not in argv)
        if not confirm(yes, "Остановка" if cmd == "stop" else "Перезапуск"):
            print("Отменено.")
            return 3
        rc = do_stop(d)
        if cmd == "stop" or rc:
            return rc
        return do_start(d)
    except Exception as ex:
        print("ОШИБКА: %s: %s" % (ex.__class__.__name__, str(ex)[:800]))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
