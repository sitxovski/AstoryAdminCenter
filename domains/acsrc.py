# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""acsrc.py — откуда служба берёт чужой код (исходник античита AstoryServer/Tools/Anticheat, сверка подарков gp7) — ★ ревизия 56 С-1 (22.11.2026).

БЫЛО: «исходник на ПК, иначе копия ext/ архива выкладки» — путь исходника считался от корня службы: на сервере PORT = H:\\, исходник =
  H:\\AstoryServer\\Tools\\Anticheat. Папки нет, но в корень H:\\ может писать любой локальный пользователь (BUILTIN\\Users — AppendData / CreateFiles), и
  служба (SYSTEM) исполнила бы подложенные .py в 00:20 с доступом к секрету asda_admin.
СТАЛО:
  * на сервере (config.on_server) — ТОЛЬКО копия в дереве службы ext/ (@@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter\\ext — без прав Users), и каждый файл перед
    исполнением сверяется с манифестом выкладки ext/MANIFEST.json (md5, пишет deploy_admin_center.build_zip); нет манифеста, нет записи,
    md5 другой — отказ SourceError, код не исполняется;
  * на ПК — исходник порта (рабочая копия владельца), как прежде; копия ext/ — только если исходника нет (тогда с той же сверкой);
  * код исполняется из ПРОВЕРЕННЫХ байтов (compile в памяти, без повторного чтения файла и без __pycache__) с отдельным состоянием:
    свой __builtins__ (__import__ отдаёт частные модули набора, open — подстановка вызывающего), свой sys (копия sys.path — исходник может
    вставлять пути, общий sys.path и sys.modules не меняются: без гонок с другими потоками службы).
★ ревизия 57 (мелочи 2, 3): это НЕ песочница — исполняемый код может добраться до настоящих встроенных и sys.modules. Граница доверия —
  манифест выкладки (согласованная, не порченая копия) плюс ACL дерева службы @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter (только SYSTEM и Administrators,
  наследование снято): записать в ext/ и манифест может только администратор. От администратора манифест не защищает и не должен.
Побочных эффектов при импорте нет.
"""
import builtins
import hashlib
import json
import os
import sys
import types

from core import config
from core.ops import OpRefused

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # AstoryAdminCenter (служба — @@ASTORY_SERVER_ROOT@@\AdminCenter)
PORT = os.path.dirname(ROOT)                           # папка с клонами (только на ПК)
EXT = os.path.join(ROOT, "ext")                                         # копии чужого кода в архиве выкладки
MANIFEST = os.path.join(EXT, "MANIFEST.json")                           # {путь от ext/ через «/»: md5} — пишет выкладка
AC_SRC = os.path.join(PORT, "AstoryServer", "Tools", "Anticheat")                       # исходник античита на ПК
AC_EXT = os.path.join(EXT, "anticheat")                                 # его копия в дереве службы


class SourceError(OpRefused):
    """Чужой код не прошёл проверку (не из дерева службы, нет в манифесте, md5 не тот) — не исполняется. ★ ревизия 57 (мелочь 7): отказ
    (OpRefused — в журнале refused, ответ 409 с понятным текстом), а не внутренняя ошибка 500."""


def pick(src, ext):
    """Папка / файл кода: на сервере — только ext; на ПК — src, если он есть, иначе ext."""
    if config.get().on_server:
        return ext
    return src if os.path.exists(src) else ext


def _under(path, root):
    p, r = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return p.startswith(r + os.sep)


def manifest():
    """Манифест выкладки {путь: md5} или {} (нет файла)."""
    try:
        with open(MANIFEST, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except FileNotFoundError:
        return {}


def read_verified(path):
    """Байты файла кода. Файл из ext/ — только с записью манифеста и тем же md5; на сервере — только из ext/."""
    in_ext = _under(path, EXT)
    if config.get().on_server and not in_ext:
        raise SourceError("код вне дерева службы не исполняется: %s" % path)
    with open(path, "rb") as f:
        data = f.read()
    if in_ext:
        rel = os.path.relpath(path, EXT).replace("\\", "/")
        want = manifest().get(rel)
        if not want:
            raise SourceError("файла %s нет в манифесте выкладки — код не исполняется" % rel)
        if hashlib.md5(data).hexdigest() != want:
            raise SourceError("файл %s не совпадает с манифестом выкладки (md5) — код не исполняется" % rel)
    return data


class _Sys(types.ModuleType):
    """Частный sys набора: своя копия path, остальное — настоящий sys."""

    def __init__(self):
        super().__init__("sys")
        self.path = list(sys.path)

    def __getattr__(self, name):
        return getattr(sys, name)


def load(d, names, prefix, open_fn=None, extra=None):
    """Исполнить модули names (порядок — зависимости раньше) из папки d в частном пространстве → ({имя: модуль}, md5 набора).
    extra — готовые частные модули ({имя: объект}, например stack_layout); open_fn — подстановка встроенного open."""
    mods = dict(extra or {})
    mods["sys"] = _Sys()
    real = builtins.__import__

    def imp(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in mods:
            return mods[name]
        return real(name, globals, locals, fromlist, level)
    bi = dict(builtins.__dict__)
    bi["__import__"] = imp
    if open_fn is not None:
        bi["open"] = open_fn
    h = hashlib.md5()
    for n in names:
        path = os.path.join(d, n + ".py")
        data = read_verified(path)
        h.update(n.encode("ascii") + b".py\0" + data + b"\0")
        m = types.ModuleType(prefix + n)
        m.__file__ = path
        m.__dict__["__builtins__"] = bi
        mods[n] = m
        exec(compile(data, path, "exec"), m.__dict__)
    return mods, h.hexdigest()
