# Copyright (c) 2026 @sitxovski (Discord)
# -*- coding: utf-8 -*-
"""selftest_public.py — самотест на публичных клонах (25.11.2026, ревизия публичного клона К-3).

Часть проверок самотеста сверяет панель с файлами, которые есть только в рабочей среде разработчика и в публичные репозитории
не входят (sql/adminc_99_rollback.sql, AstoryServer/Docs/SQL, AstoryServer/SQL, AstoryClient/RawAssets, клиенты-доноры, Docs,
Releases, Reports). Такие проверки не валят прогон, а отмечаются SKIP с именем файла и попадают в итог отдельной строкой.

  dev_text(*путь)   — текст файла (utf-8) или None, если файла нет (SKIP записывается один раз на файл);
  skip(имя, почему) — отметить пропущенную проверку;
  guard(имя, fn, …) — выполнить блок самотеста; FileNotFoundError на файле «только среды разработчика» (путь вне этого репозитория
                      в папке клонов или sql/adminc_99_rollback.sql) — SKIP всего оставшегося блока, любая другая ошибка — как раньше.
Побочных эффектов при импорте нет.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                         # AstoryAdminCenter
PORT = os.path.dirname(ROOT)                         # папка с клонами AstoryClient / AstoryServer / AstoryAdminCenter
DEV_ONLY_FILES = (os.path.join(ROOT, "sql", "adminc_99_rollback.sql"),)    # файлы панели, которых в публичном репозитории нет

SKIPS = []                                           # (имя, почему)
_noted = set()


def skip(name, why):
    """Записать пропущенную проверку (печать SKIP — как ok/FAIL у check)."""
    SKIPS.append((name, why))
    print("SKIP %s — %s" % (name, why))


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def dev_only(path):
    """Путь — файл среды разработчика, которого нет на публичном клоне (и его действительно нет на диске)?"""
    if not path or os.path.exists(path):
        return False
    p = _norm(path)
    if p in {_norm(x) for x in DEV_ONLY_FILES}:
        return True
    root, port = _norm(ROOT), _norm(PORT)
    return p.startswith(port + os.sep) and not p.startswith(root + os.sep)


def _why(path):
    try:
        rel = os.path.relpath(path, PORT).replace("\\", "/")
    except ValueError:
        rel = path
    return "нет файла %s (есть только в среде разработчика, в публичных репозиториях его нет)" % rel


def dev_text(*parts):
    """Текст файла или None (файла нет — одна отметка SKIP на файл; проверки, которым он нужен, считаются пропущенными)."""
    path = os.path.join(*parts)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    if path not in _noted:
        _noted.add(path)
        skip(os.path.basename(path), _why(path) + "; зависящие от него условия проверок не проверяются")
    return None


def guard(name, fn, *args):
    """Выполнить блок самотеста; нет файла только среды разработчика — SKIP остатка блока вместо обрыва всего прогона."""
    try:
        return fn(*args)
    except (FileNotFoundError, NotADirectoryError) as e:
        path = getattr(e, "filename", None)
        if not dev_only(path):
            raise
        skip(name, _why(path) + " — остаток блока пропущен")
        return None


def summary():
    """Строка итога о пропущенном (пусто, если ничего не пропущено)."""
    if not SKIPS:
        return ""
    return "пропущено (SKIP, нет файлов среды разработчика): %d" % len(SKIPS)
