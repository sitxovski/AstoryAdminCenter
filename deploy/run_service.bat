@echo off
rem Copyright (c) 2026 @sitxovski (Discord)
rem AsdaAdminCenter service wrapper (scheduled task AsdaAdminCenter, SYSTEM, at startup).
rem ASCII only on purpose: cmd misparses UTF-8 batch files (multi-byte lines shift the parser).
rem Restarts the panel 10 s after any exit (e.g. VPN address not up yet at boot). Log: logs\service.log
cd /d "%~dp0"
set PY=@@ASTORY_SERVER_PYTHON@@
set PYTHONIOENCODING=utf-8
:loop
for %%F in (logs\service.log) do if %%~zF GTR 20000000 move /y logs\service.log logs\service.log.1 >nul
echo %date% %time% start>> logs\service.log
"%PY%" -u asda_admin.py serve >> logs\service.log 2>&1
echo %date% %time% exit code %errorlevel%, restart in 10 s>> logs\service.log
ping -n 11 127.0.0.1 >nul
goto loop
