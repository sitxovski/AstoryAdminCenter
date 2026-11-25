#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Роль User: убрать лишнее право manage_messages и выдать роль всем участникам (кроме ботов)."""

import asyncio

import discord

from botctl import connect, norm_name


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        user_role = roles["user"]

        # 1. Убрать «Управление сообщениями» у обычных участников
        if user_role.permissions.manage_messages:
            perms = user_role.permissions
            perms.update(manage_messages=False)
            await user_role.edit(permissions=perms,
                                 reason="лишнее право: обычные участники не должны удалять чужие сообщения")
            print("  User: manage_messages убран")
        else:
            print("  User: manage_messages уже отсутствует")

        # 2. Выдать роль всем людям (боты пропускаются)
        given = skipped = 0
        after = 0
        while True:
            page = await client.http.get_members(guild.id, 1000, after)
            if not page:
                break
            for m in page:
                uid = int(m["user"]["id"])
                if m["user"].get("bot"):
                    continue
                if str(user_role.id) in m.get("roles", []) or user_role.id in [int(r) for r in m.get("roles", [])]:
                    skipped += 1
                    continue
                await client.http.add_role(guild.id, uid, user_role.id,
                                           reason="базовая членская роль всем участникам")
                given += 1
            after = int(page[-1]["user"]["id"])
        print(f"  роль User выдана: {given}, уже была: {skipped}")
    except discord.Forbidden:
        raise SystemExit(
            "Discord не пустил к списку участников: включи в Developer Portal -> Bot "
            "тумблер 'Server Members Intent' и запусти скрипт ещё раз.")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
