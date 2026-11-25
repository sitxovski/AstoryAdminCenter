#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Диагностика: фактические оверрайды IMPORTANT и его каналов + онбординг-дефолты."""

import asyncio

import discord
from botctl import connect, perm_names
from botcfg import discord_id

IMPORTANT_CAT = discord_id("@@ASTORY_DISCORD_IMPORTANT_CAT@@", "категория IMPORTANT")   # ★ 25.11 (С-4)


async def main() -> None:
    client, guild = await connect()
    try:
        chans = await guild.fetch_channels()
        cat = next(c for c in chans if c.id == IMPORTANT_CAT)
        print("== Категория IMPORTANT ==")
        for t, ow in cat.overwrites.items():
            a, d = ow.pair()
            print(f"  {getattr(t, 'name', t)}: allow={perm_names(a)} deny={perm_names(d)}")
        for c in chans:
            if c.category_id == cat.id:
                print(f"\n== {c.name} ({c.type}) synced={c.permissions_synced} ==")
                for t, ow in c.overwrites.items():
                    a, d = ow.pair()
                    print(f"  {getattr(t, 'name', t)}: allow={perm_names(a)} deny={perm_names(d)}")
        ob = await guild.onboarding()
        names = {c.id: c.name for c in chans}
        print("\n== Онбординг: каналы по умолчанию ==")
        for i in ob.default_channel_ids:
            print(f"  {names.get(i, '?удалён?')} ({i})")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
