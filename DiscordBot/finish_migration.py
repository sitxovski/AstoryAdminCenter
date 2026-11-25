#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Дочистка миграции: голосовой General + посты-заглушки в Suggestions и Support."""

import asyncio

import discord

from botctl import connect
from migrate_channels import SUGGESTIONS_POST, SUGGESTIONS_POST_TITLE, SUPPORT_POST


async def main() -> None:
    client, guild = await connect()
    try:
        chans = await guild.fetch_channels()
        by_id_name = {c.name: c for c in chans}

        # 1. Голосовой General (в первом прогоне спутан с текстовым #general)
        cat_voice = next(c for c in chans if c.name == "🔊 VOICE")
        have_voice_general = any(
            c.type is discord.ChannelType.voice and c.name == "🔊 General" for c in chans)
        if not have_voice_general:
            vc = await guild.create_voice_channel("🔊 General", category=cat_voice,
                                                  reason="дочистка миграции")
            # поставить первым в категории
            await vc.edit(position=0)
            print(f"  создан голосовой: {vc.name} ({vc.id})")

        # 2. Пост в форуме Suggestions, если форум пуст
        suggestions = by_id_name["💡┃suggestions"]
        threads = suggestions.threads  # у свежего объекта пусто; проверим через архив API
        existing = list(threads)
        if not existing:
            async for t in suggestions.archived_threads(limit=5):
                existing.append(t)
        if existing:
            print("  Suggestions: посты уже есть, пропуск")
        else:
            th = await suggestions.create_thread(
                name=SUGGESTIONS_POST_TITLE, content=SUGGESTIONS_POST,
                allowed_mentions=discord.AllowedMentions.none())
            print(f"  пост в Suggestions: {th.thread.jump_url}")

        # 3. Пост в Support, если канал пуст
        support = by_id_name["🎫┃support"]
        history = [m async for m in support.history(limit=1)]
        if history:
            print("  Support: сообщения уже есть, пропуск")
        else:
            msg = await support.send(SUPPORT_POST, allowed_mentions=discord.AllowedMentions.none())
            await msg.pin(reason="статус поддержки")
            print(f"  пост в Support: {msg.jump_url}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
