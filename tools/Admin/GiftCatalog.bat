@echo off
rem Copyright (c) 2026 @sitxovski (Discord)
rem Витрина подарков (вкладка «Подарки» утилиты учёток): каталог data\gift_catalog.json и иконки data\icons из данных порта. Запускать после новых товаров магазина. Нужен Pillow.
chcp 65001 >nul
where python >nul 2>&1 || (echo Python не найден в PATH & pause & exit /b 1)
python -c "import PIL" >nul 2>&1 || (echo Нет Pillow: python -m pip install pillow & pause & exit /b 1)
python "%~dp0asda_gift_catalog_build.py" %*
if errorlevel 1 pause
