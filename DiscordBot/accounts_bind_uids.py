#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Вписать Discord ID в playtest_accounts.txt: «(@handle)» → «(@handle) [uid]».

Привязка по ID защищает от смены ника: освободившийся ник может занять другой
человек и получить чужой пароль. Идемпотентно: строки с [uid] не трогаются.
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from botctl import connect

FILE = Path(__file__).parent / "playtest_accounts.txt"
HANDLE = re.compile(r"\(@([^)]+)\)(?!\s*\[\d+\])")


async def main() -> None:
    client, guild = await connect()
    try:
        by_handle: dict[str, str] = {}
        after = 0
        while True:
            page = await client.http.get_members(guild.id, 1000, after)
            if not page:
                break
            for m in page:
                by_handle[m["user"]["username"].lower()] = m["user"]["id"]
            after = int(page[-1]["user"]["id"])

        out, bound, missing = [], 0, []
        for line in FILE.read_text(encoding="utf-8").splitlines():
            mt = HANDLE.search(line)
            if line.startswith("#") or mt is None:
                out.append(line)
                continue
            uid = by_handle.get(mt.group(1).lower())
            if uid is None:
                missing.append(mt.group(1))
                out.append(line)
                continue
            out.append(line[:mt.end()] + f" [{uid}]" + line[mt.end():])
            bound += 1
        FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"привязано по ID: {bound}")
        print(f"не найдены на сервере: {missing or '—'}")
    finally:
        await client.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
