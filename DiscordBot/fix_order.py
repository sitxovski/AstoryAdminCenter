#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Финальная расстановка порядка: категории каналов и иерархия ролей."""

import asyncio

from botctl import connect, norm_name

# Категории сверху вниз
CATEGORY_ORDER = ["project support", "important", "developments", "chat",
                  "testing", "voice", "staff"]

# Роли сверху вниз (бот Oracle не трогаем — он выше всех)
ROLE_ORDER = ["head of development", "administrator", "moderator",
              "beta tester", "translator", "early supporter",
              "server booster", "user",
              "news ping", "patch ping", "playtest ping",
              "english", "русский", "العربية", "中文"]


async def main() -> None:
    client, guild = await connect()
    try:
        # ---------- категории: одним bulk-запросом, без каскадных сдвигов
        cats = {norm_name(c.name): c for c in await guild.fetch_channels()
                if str(c.type) == "category"}
        payload = [{"id": cats[k].id, "position": pos}
                   for pos, k in enumerate(CATEGORY_ORDER) if k in cats]
        await client.http.bulk_channel_update(guild.id, payload,
                                              reason="порядок категорий")
        print("  категории упорядочены")

        # ---------- роли: позиции сверху вниз под ролью бота
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        me = await guild.fetch_member(client.user.id)
        top = me.top_role.position                     # позиция роли Oracle
        listed = [roles[k] for k in ROLE_ORDER if k in roles]
        positions = {r: top - 1 - i for i, r in enumerate(listed)}
        positions = {r: max(p, 1) for r, p in positions.items()}
        await guild.edit_role_positions(positions, reason="иерархия ролей")
        print("  роли упорядочены")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
