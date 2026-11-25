#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Свип: выдать User всем, у кого есть языковая роль (EN/RU/AR/ZH), но нет User.

Запускать периодически, пока нет демона Oracle с автовыдачей по событию.
"""

import asyncio

from botctl import connect, norm_name

LANG_KEYS = ("english", "русский", "العربية", "中文")


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        lang_ids = {roles[k].id for k in LANG_KEYS}
        user_role = roles["user"]
        given = ok = nolang = 0
        after = 0
        while True:
            page = await client.http.get_members(guild.id, 1000, after)
            if not page:
                break
            for m in page:
                if m["user"].get("bot"):
                    continue
                mroles = {int(r) for r in m.get("roles", [])}
                if mroles & lang_ids:
                    if user_role.id in mroles:
                        ok += 1
                    else:
                        await client.http.add_role(
                            guild.id, int(m["user"]["id"]), user_role.id,
                            reason="есть языковая роль: User = полноценный участник")
                        given += 1
                else:
                    nolang += 1
            after = int(page[-1]["user"]["id"])
        print(f"User выдана: {given} | уже была: {ok} | без языка: {nolang}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
