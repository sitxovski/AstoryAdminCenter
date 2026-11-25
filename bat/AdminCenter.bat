@echo off
rem Copyright (c) 2026 @sitxovski (Discord)
rem Astory admin center on the dev server: start / stop / restart / status (via SSH).
rem ASCII only on purpose: cmd misparses UTF-8 batch files. Logic: AstoryAdminCenter\deploy\admin_center_ctl.py
rem Usage: AdminCenter.bat [status|start|stop|restart|tunnel] [--yes] [--no-browser]   (no argument = menu)
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set CTL=%~dp0..\deploy\admin_center_ctl.py
where python >nul 2>&1 || (echo Python not found in PATH & pause & exit /b 1)
if "%~1"=="" goto menu
python "%CTL%" %*
exit /b %errorlevel%
:menu
echo.
echo  Astory admin center
echo    1 - status
echo    2 - start
echo    3 - stop
echo    4 - restart
echo    5 - open panel on https://localhost:17890/ (SSH tunnel, keep window open)
echo    0 - exit
set CH=
set /p CH=Choice: 
if "%CH%"=="1" python "%CTL%" status
if "%CH%"=="2" python "%CTL%" start
if "%CH%"=="3" python "%CTL%" stop
if "%CH%"=="4" python "%CTL%" restart
if "%CH%"=="5" python "%CTL%" tunnel
if "%CH%"=="0" exit /b 0
goto menu
