#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Убрать эмодзи из названий ролей: иконки ролей теперь показывают эмодзи сами,
и в шапках групп списка участников он двоится."""

import asyncio

import discord
from discord.http import Route

from botctl import connect, norm_name

RENAMES = {
    "head of development": "Head of Development",
    "administrator": "Administrator",
    "moderator": "Moderator",
    "beta tester": "Beta Tester",
    "translator": "Translator",
    "early supporter": "Early Supporter",
}


async def main() -> None:
    client, guild = await connect()
    try:
        raw = await client.http.get_roles(guild.id)
        roles = {norm_name(r["name"]): r for r in raw}
        for key, newname in RENAMES.items():
            r = roles.get(key)
            if r is None:
                print(f"  ! не найдена: {key}")
                continue
            if r["name"] != newname:
                await client.http.request(
                    Route("PATCH", "/guilds/{guild_id}/roles/{role_id}",
                          guild_id=guild.id, role_id=int(r["id"])),
                    json={"name": newname},
                    reason="иконка роли показывает эмодзи — из имени убираем дубль")
                print(f"  {r['name']!r} -> {newname!r}")
            else:
                print(f"  без изменений: {newname!r}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
