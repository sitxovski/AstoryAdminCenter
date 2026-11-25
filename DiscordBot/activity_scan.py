#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Скан активности сервера: сообщения по авторам во всех текстовых каналах и
тредах + поставленные реакции (по последним REACT_SCAN сообщениям канала).

Результат: activity.json {uid: {"name", "msgs", "reacts"}}.
"""

import asyncio
import json
from collections import defaultdict
from pathlib import Path

import discord

from botctl import connect

OUT = Path(__file__).parent / "activity.json"
REACT_SCAN = 400          # сколько последних сообщений канала сканировать на реакции
SKIP = {"mod-log", "join-log", "discord-updates"}   # технические логи


async def main() -> None:
    client, guild = await connect()
    msgs: dict[int, int] = defaultdict(int)
    reacts: dict[int, int] = defaultdict(int)
    names: dict[int, str] = {}
    try:
        chans = await guild.fetch_channels()
        targets = []
        for c in chans:
            if str(c.type) in ("text", "news") and not any(s in c.name for s in SKIP):
                targets.append(c)
        # активные треды (форумы: behind-the-scenes, suggestions, updates)
        threads = await guild.active_threads()
        targets += threads

        for ch in targets:
            try:
                n = 0
                async for m in ch.history(limit=None, oldest_first=False):
                    if not m.author.bot:
                        msgs[m.author.id] += 1
                        names[m.author.id] = str(m.author)
                    if n < REACT_SCAN and m.reactions:
                        for r in m.reactions:
                            try:
                                async for u in r.users():
                                    if not u.bot:
                                        reacts[u.id] += 1
                                        names.setdefault(u.id, str(u))
                            except discord.HTTPException:
                                pass
                    n += 1
                print(f"  {ch.name}: {n} сообщений")
            except discord.Forbidden:
                print(f"  ! нет доступа: {ch.name}")

        data = {str(uid): {"name": names.get(uid, "?"), "msgs": msgs.get(uid, 0),
                           "reacts": reacts.get(uid, 0)}
                for uid in set(msgs) | set(reacts)}
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        top = sorted(data.items(), key=lambda kv: -(kv[1]["msgs"] + kv[1]["reacts"]))[:40]
        print(f"\nавторов: {len(data)} | топ-40 по (сообщения+реакции):")
        for uid, d in top:
            print(f"  {d['msgs']:5d} msg {d['reacts']:4d} rct  {d['name']}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
