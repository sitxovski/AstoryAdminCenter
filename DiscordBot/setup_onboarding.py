#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Настройка онбординга: экран языков (роли EN/RU/AR/ZH) и экран пингов.

Плюс: конвертация 📣┃announcements и ⚙️┃patches в Announcement-каналы
(доступно только после включения режима сообщества).
"""

import asyncio

import discord

from botctl import connect, norm_name


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        chans = {norm_name(c.name): c for c in await guild.fetch_channels()}

        # ---------- 1. Announcement-тип для новостных каналов
        for key in ("announcements", "patches"):
            ch = chans[key]
            if ch.type is not discord.ChannelType.news:
                await ch.edit(type=discord.ChannelType.news,
                              reason="онбординг: Announcement-канал (подписки других серверов)")
                print(f"  {ch.name}: теперь Announcement-канал")

        # ---------- 2. Онбординг
        lang_prompt = discord.OnboardingPrompt(
            type=discord.OnboardingPromptType.multiple_choice,
            title="Which languages do you speak? / На каких языках говоришь?",
            single_select=False,
            required=True,
            in_onboarding=True,
            options=[
                discord.OnboardingPromptOption(
                    title="English", emoji="🇬🇧", roles=[roles["english"]],
                    channels=[chans["english"]]),
                discord.OnboardingPromptOption(
                    title="Русский", emoji="🇷🇺", roles=[roles["русский"]],
                    channels=[chans["русский"]]),
                discord.OnboardingPromptOption(
                    title="العربية", emoji="🇸🇦", roles=[roles["العربية"]],
                    channels=[chans["العربية"]]),
                discord.OnboardingPromptOption(
                    title="中文", emoji="🇹🇼", roles=[roles["中文"]],
                    channels=[chans["中文"]]),
            ])

        ping_prompt = discord.OnboardingPrompt(
            type=discord.OnboardingPromptType.multiple_choice,
            title="What news do you want to be pinged about?",
            single_select=False,
            required=False,
            in_onboarding=True,
            options=[
                discord.OnboardingPromptOption(
                    title="Project news", emoji="📢", description="Announcements & devlog",
                    roles=[roles["news ping"]]),
                discord.OnboardingPromptOption(
                    title="Patch notes", emoji="⚙️", description="Client & server updates",
                    roles=[roles["patch ping"]]),
                discord.OnboardingPromptOption(
                    title="Playtests", emoji="🧪", description="Closed playtest invites",
                    roles=[roles["playtest ping"]]),
            ])

        # Каналы, которые видят все новички по умолчанию
        default_keys = ["rules", "announcements", "patches", "donations",
                        "behindthescenes", "suggestions", "support", "devchat",
                        "general", "english", "русский", "العربية", "中文"]
        default_channels = [chans[k] for k in default_keys]

        await guild.edit_onboarding(
            prompts=[lang_prompt, ping_prompt],
            default_channels=default_channels,
            enabled=True,
            mode=discord.OnboardingMode.default,
            reason="настройка онбординга: языки + пинги",
        )
        print("  онбординг включён: 2 экрана (языки, пинги), "
              f"каналов по умолчанию: {len(default_channels)}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
