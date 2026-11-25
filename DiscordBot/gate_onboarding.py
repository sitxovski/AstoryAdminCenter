#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Гейт онбординга + путеводитель.

1. @everyone теряет права письма; их выдают роли User и языковые (выдаются онбордингом).
   Итог: новичок не может писать, пока не пройдёт онбординг; старички пишут через User.
2. В 📜┃rules — закреплённое объяснение «почему не могу писать» со ссылкой <id:customize>.
3. Экран приветствия (welcome screen) с описанием и подсказкой.
4. Путеводитель по серверу (server guide) через недокументированный эндпоинт; при отказе — инструкция.
"""

import asyncio

import discord
from discord.http import Route

from botctl import connect, norm_name

# Права «письма», которые переезжают с @everyone на роли-носители
WRITE_PERMS = ("send_messages", "send_messages_in_threads",
               "create_public_threads", "create_private_threads",
               "send_voice_messages")
# Роли-носители письма: User (старички) + языковые (выдаёт обязательный вопрос онбординга)
CARRIER_ROLES = ("user", "english", "русский", "العربية", "中文")

CANT_TYPE_POST = """\
# ✍️ Can't type? / Не можешь писать? / لا يمكنك الكتابة؟

**EN** — Chat unlocks after a 10-second onboarding: open <id:customize>, pick your \
language (and pings if you like) — and you can write right away! Lost? Check <id:guide>.

**RU** — Чат открывается после короткого онбординга: открой <id:customize>, выбери свой \
язык (и пинги по желанию) — и сразу сможешь писать! Не знаешь, с чего начать — загляни в <id:guide>.

**AR** — تُفتح الدردشة بعد خطوات سريعة: افتح <id:customize> واختر لغتك — وستتمكن من الكتابة فوراً! \
للتعرف على السيرفر راجع <id:guide>.
"""

WELCOME_DESCRIPTION = ("Fan remake of the classic MMORPG Asda Story. "
                       "Complete the quick onboarding to unlock chat — pick your language and jump in!")


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        # голосовые в карту не берём: «🔊 General» иначе затирает текстовый «💬┃general»
        chans = {norm_name(c.name): c for c in await guild.fetch_channels()
                 if str(c.type) not in ("voice", "category")}

        # ---------- 1. Гейт прав
        everyone = guild.default_role
        ev_perms = everyone.permissions
        if any(getattr(ev_perms, p) for p in WRITE_PERMS):
            ev_perms.update(**{p: False for p in WRITE_PERMS})
            await everyone.edit(permissions=ev_perms,
                                reason="гейт онбординга: письмо только после онбординга")
            print("  @everyone: права письма сняты")
        for key in CARRIER_ROLES:
            r = roles[key]
            perms = r.permissions
            missing = {p: True for p in WRITE_PERMS if not getattr(perms, p)}
            if missing:
                perms.update(**missing)
                await r.edit(permissions=perms, reason="гейт онбординга: роль-носитель письма")
                print(f"  {r.name}: письмо разрешено")

        # ---------- 2. Объяснение в правилах
        rules = chans["rules"]
        already = [m async for m in rules.history(limit=10)
                   if "<id:customize>" in m.content]
        if not already:
            msg = await rules.send(CANT_TYPE_POST,
                                   allowed_mentions=discord.AllowedMentions.none())
            await msg.pin(reason="объяснение гейта онбординга")
            print(f"  Rules: пост-объяснение закреплён {msg.jump_url}")
        else:
            print("  Rules: объяснение уже есть")

        # ---------- 3. Экран приветствия
        wc = [
            {"channel_id": chans["rules"].id, "emoji_name": "📜",
             "description": "Rules & how to unlock chat"},
            {"channel_id": chans["announcements"].id, "emoji_name": "📣",
             "description": "Project news"},
            {"channel_id": chans["general"].id, "emoji_name": "💬",
             "description": "Chat with the community"},
            {"channel_id": chans["devchat"].id, "emoji_name": "🛠️",
             "description": "Talk about the development"},
        ]
        await client.http.request(
            Route("PATCH", "/guilds/{guild_id}/welcome-screen", guild_id=guild.id),
            json={"enabled": True, "description": WELCOME_DESCRIPTION,
                  "welcome_channels": wc},
            reason="экран приветствия")
        print("  Welcome screen включён")

        # ---------- 4. Путеводитель (недокументированный API — пробуем)
        try:
            guide_payload = {
                "enabled": True,
                "welcome_message": {
                    "author_ids": [guild.owner_id],
                    "message": ("Welcome to Astory Remake Project! 🎮 We're rebuilding the classic "
                                "MMORPG Asda Story. Complete onboarding to unlock chat, then come say hi!"),
                },
                "new_member_actions": [
                    {"channel_id": chans["rules"].id, "action_type": 0, "title": "Read the rules",
                     "description": "…and learn how to unlock chat", "emoji": {"name": "📜"}},
                    {"channel_id": chans["general"].id, "action_type": 1, "title": "Say hello",
                     "description": "Introduce yourself to the community", "emoji": {"name": "👋"}},
                    {"channel_id": chans["announcements"].id, "action_type": 0,
                     "title": "Catch up on the news",
                     "description": "Project announcements & progress", "emoji": {"name": "📣"}},
                ],
                "resource_channels": [
                    {"channel_id": chans["behindthescenes"].id, "title": "Devlog",
                     "description": "Behind the scenes of the remake", "emoji": {"name": "🏗️"}},
                    {"channel_id": chans["donations"].id, "title": "Support the project",
                     "description": "Voluntary donations", "emoji": {"name": "💰"}},
                ],
            }
            await client.http.request(
                Route("PUT", "/guilds/{guild_id}/new-member-welcome", guild_id=guild.id),
                json=guide_payload)
            print("  Путеводитель включён")
        except discord.HTTPException as e:
            print(f"  ! Путеводитель через API не дался ({e.status}): настроить вручную — "
                  "Настройки сервера -> Онбординг -> Путеводитель по серверу")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
