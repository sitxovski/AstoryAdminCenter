#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Точечное напоминание непрошедшим онбординг: роль-метка + пинг в lobby.

1. Создаёт роль «Onboarding Pending» (без прав и цвета).
2. Вешает её всем людям без языковой роли.
3. Публикует в lobby напоминание с пингом этой роли (уведомление получат только они).
Метку снимает демон Oracle при выборе языка.
"""

import asyncio

import discord

from botctl import connect, norm_name
from botcfg import discord_id

PENDING = "Onboarding Pending"
LANG_KEYS = ("english", "русский", "العربية", "中文")
LOBBY_CH = discord_id("@@ASTORY_DISCORD_LOBBY_CH@@", "lobby")   # ★ 25.11 (С-4): заглушка не заменена — 0 с предупреждением

TEXT = """\
📣 {mention} — friendly reminder / дружеское напоминание!

**EN** — You haven't finished onboarding, so chat is still locked for you. \
Open <id:customize>, pick your language — 10 seconds, and everything unlocks.

**RU** — Ты ещё не прошёл онбординг, поэтому чат пока закрыт. \
Открой <id:customize>, выбери язык — 10 секунд, и всё откроется.

**AR** — لم تُكمل خطوات الانضمام بعد، لذا الدردشة مغلقة لديك. \
افتح <id:customize> واختر لغتك — ثوانٍ وتنفتح كل القنوات.

**中文** — 你還沒完成入門設定,聊天目前對你是鎖定的。\
打開 <id:customize> 選擇語言 — 十秒鐘就能解鎖全部頻道。
"""


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        pending = roles.get(norm_name(PENDING))
        if pending is None:
            pending = await guild.create_role(
                name=PENDING, mentionable=False,
                reason="метка для точечного напоминания об онбординге")
            print("роль создана:", pending.id)
        lang_ids = {roles[k].id for k in LANG_KEYS}

        tagged = skipped = 0
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
                    continue
                if pending.id in mroles:
                    skipped += 1
                    continue
                await client.http.add_role(guild.id, int(m["user"]["id"]), pending.id,
                                           reason="нет языковой роли: напоминание")
                tagged += 1
            after = int(page[-1]["user"]["id"])
        print(f"метка выдана: {tagged}, уже была: {skipped}")

        lobby = await client.fetch_channel(LOBBY_CH)
        msg = await lobby.send(
            TEXT.format(mention=pending.mention),
            allowed_mentions=discord.AllowedMentions(roles=[pending], everyone=False,
                                                     users=False))
        print("отправлено:", msg.jump_url)
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
