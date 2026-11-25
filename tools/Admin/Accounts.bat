@echo off
rem Copyright (c) 2026 @sitxovski (Discord)
rem Учётки игроков (dev-БД): создание, смена пароля, выдача золота и предметов, подарки из витрин магазинов (вкладка «Подарки»). Окно; консоль — python asda_accounts.py create|passwd|info <логин>, give-gold|give-item (см. шапку)
chcp 65001 >nul
where python >nul 2>&1 || (echo Python не найден в PATH & pause & exit /b 1)
python "%~dp0asda_accounts.py" %*
if errorlevel 1 pause
