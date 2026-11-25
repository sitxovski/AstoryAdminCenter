# Copyright (c) 2026 @sitxovski (Discord)
r"""botcfg.py — общие настройки бота и его скриптов (25.11.2026, ревизия публичного клона: К-5, С-4).

  proxy(*имена)          — прокси из переменных окружения (.env): первая ЗАДАННАЯ из имён; пустое значение или none / off / direct —
                           явно «без прокси». Ни одна не задана — без прокси (None). Своего адреса по умолчанию нет.
  discord_id(текст, имя) — ID Discord (канал, сообщение, категория), вписанный мастером _setup\configure в виде числа. Заглушка
                           @@ASTORY_…@@ не заменена или пусто — 0 и предупреждение (журнал / stderr), без падения при импорте; функция
                           с таким каналом выключена (канал 0 Discord не найдёт).
  UNSET, log_unset(log)  — какие ID не заданы: oracle_bot пишет их в свой журнал после настройки logging.
Побочных эффектов при импорте нет.
"""
import logging
import os
import sys

_NO_PROXY = ("", "none", "off", "direct", "no")
UNSET = []                                   # имена ID, оставшихся заглушкой или пустыми


def proxy(*names):
    """Прокси из окружения по порядку имён; не задано / пусто / none — None (прямое соединение)."""
    for n in names:
        if n in os.environ:
            v = (os.environ.get(n) or "").strip()
            return None if v.lower() in _NO_PROXY else v
    return None


def discord_id(text, name):
    """Число ID Discord или 0 (заглушка не заменена / пусто / не число) с предупреждением."""
    s = str(text or "").strip()
    if s.isdigit():
        return int(s)
    UNSET.append(name)
    msg = "ID Discord «%s» не задан (запустите _setup\\configure.bat и впишите его) — функция с ним выключена" % name
    if logging.getLogger().handlers:
        logging.getLogger("oracle").warning(msg)
    elif sys.stderr is not None:             # под pythonw stderr нет
        print("ПРЕДУПРЕЖДЕНИЕ: " + msg, file=sys.stderr)
    return 0


def log_unset(log):
    """Записать в журнал бота незаданные ID (после logging.basicConfig)."""
    for n in UNSET:
        log.warning("ID Discord «%s» не задан (_setup\\configure.bat) — функция с ним выключена", n)
