#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Убрать игрока из тестеров: снять Beta Tester + отклонить заявку в реестре/карточке."""

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import discord

from botctl import connect, norm_name
from botcfg import discord_id

TARGET = sys.argv[1] if len(sys.argv) > 1 else "lolipopcan"
STAFF = discord_id("@@ASTORY_DISCORD_STAFF_CHAT@@", "staff_chat")   # ★ 25.11 (С-4): заглушка не заменена — 0 с предупреждением
STATE = Path(__file__).parent / "state.json"


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        tester = roles["beta tester"]
        uid = None
        after = 0
        while True:
            page = await client.http.get_members(guild.id, 1000, after)
            if not page:
                break
            for m in page:
                if m["user"]["username"] == TARGET:
                    uid = int(m["user"]["id"])
                    if str(tester.id) in [str(r) for r in m.get("roles", [])]:
                        await client.http.remove_role(
                            guild.id, uid, tester.id,
                            reason="исключён из плейтеста владельцем 2026-10-17")
                        print("роль Beta Tester снята")
                    else:
                        print("роли уже не было")
            after = int(page[-1]["user"]["id"])
        if uid is None:
            print("игрок не найден на сервере")
            return
        st = json.loads(STATE.read_text(encoding="utf-8"))
        staff = await client.fetch_channel(STAFF)
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        changed = 0
        for a in st["applications"]:
            if a.get("uid") == uid and a.get("status") != "rejected":
                a["status"] = "rejected"
                a["decided_by"] = "owner decision 2026-10-17 (removed)"
                a["decided_ts"] = now
                changed += 1
                try:
                    msg = await staff.fetch_message(a["msg_id"])
                    if msg.embeds:
                        e = msg.embeds[0]
                        e.colour = discord.Colour.dark_grey()
                        e.title = "🧪 Playtest application — removed by owner"
                        await msg.edit(embed=e, view=None)
                except discord.HTTPException:
                    pass
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"реестр: заявок отклонено {changed}")
    finally:
        await client.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
