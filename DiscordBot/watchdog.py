#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Вотчдог Oracle без консольного окна (запускать через pythonw из планировщика).

Проверка живости — подключение к замку-порту 47653, который держит сам бот:
порт отвечает → бот жив, ничего не делаем; порт закрыт → поднимаем демона.
"""

import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CREATE_NO_WINDOW = 0x08000000

try:
    s = socket.create_connection(("127.0.0.1", 47653), timeout=2)
    s.close()                      # бот жив
except OSError:
    subprocess.Popen([sys.executable, str(ROOT / "oracle_bot.py")],
                     cwd=ROOT, creationflags=CREATE_NO_WINDOW)
