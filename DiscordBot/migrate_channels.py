#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Одноразовая миграция каналов сервера Astory Remake Project к согласованному макету.

Что делает (согласовано с владельцем 2026-08-14):
  - переименовывает существующие каналы в стиль «Эмодзи┃Имя С Больших Букв»
  - чинит права IMPORTANT (возвращает чтение истории, даёт Administrator право постить)
  - создаёт: Donations, Suggestions(форум, закрыт), Support(закрыт),
    категории TESTING (для тестеров) и STAFF (для команды), голосовые
  - удаляет пустую категорию «Текстовые каналы»
  - расставляет категории по порядку, назначает AFK-канал
  - публикует согласованные посты-заглушки в Suggestions и Support

Запуск: python migrate_channels.py
"""

import asyncio

import discord

from botctl import connect, norm_name

# Тексты согласованных постов-заглушек (EN + RU)
SUGGESTIONS_POST_TITLE = "💡 Suggestions — opens at Closed Playtest"
SUGGESTIONS_POST = (
    "**EN** — This forum is closed for now. We will open suggestions when the project "
    "reaches the **Closed Playtest** stage, so ideas can be tested against a playable build. "
    "Follow 📣┃Announcements for updates!\n\n"
    "**RU** — Форум пока закрыт. Мы откроем приём предложений, когда проект дойдёт до "
    "стадии **закрытого плейтеста**, чтобы идеи можно было проверять на живом билде. "
    "Следите за 📣┃Announcements!"
)
SUPPORT_POST = (
    "**EN** — The support/ticket system is not live yet. It will open together with the "
    "**Closed Playtest**. Until then, feel free to ask questions in 💬┃General.\n\n"
    "**RU** — Система поддержки/тикетов ещё не запущена — она откроется вместе с "
    "**закрытым плейтестом**. А пока задавайте вопросы в 💬┃General."
)


def ow(**kwargs) -> discord.PermissionOverwrite:
    """Короткий конструктор оверрайда прав."""
    return discord.PermissionOverwrite(**kwargs)


# Оверрайд «только чтение» для @everyone: видно, читается, реакции — писать нельзя
READONLY_EVERYONE = ow(
    view_channel=True, read_message_history=True, add_reactions=True,
    send_messages=False, send_messages_in_threads=False,
    create_public_threads=False, create_private_threads=False,
)
# Оверрайд «штатный постер» для Administrator в read-only каналах
POSTER_ADMIN = ow(
    view_channel=True, send_messages=True, embed_links=True, attach_files=True,
    mention_everyone=True, pin_messages=True, manage_messages=True,
)


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        chans = {norm_name(c.name): c for c in await guild.fetch_channels()}

        r_admin = roles["administrator"]
        r_mod = roles["moderator"]
        r_tester = roles["beta tester"]

        # ---------- 1. Переименования (ID сохраняются, история не теряется)
        def get_any(*keys):
            """Найти канал по любому из нормализованных ключей (до/после переименования)."""
            for k in keys:
                if k in chans:
                    return chans[k]
            return None

        # ключ = norm_name старого ИЛИ нового имени (дефисы нормализация выкидывает)
        renames = [
            (("rules",), "📜┃Rules"),
            (("announcements",), "📣┃Announcements"),
            (("patches",), "⚙️┃Patches"),
            (("behindthescenes",), "🏗️┃Behind-The-Scenes"),
            (("devchat",), "💬┃Dev-Chat"),
            (("general",), "💬┃General"),
            (("russian", "русский"), "🇷🇺┃Русский"),
            (("arabic", "العربية"), "🇸🇦┃العربية"),
            (("english",), "🇬🇧┃English"),
            (("taiwanese", "中文"), "🇹🇼┃中文"),
            (("голосовые каналы", "voice"), "🔊 VOICE"),
        ]
        for keys, new_name in renames:
            ch = get_any(*keys)
            if ch is None:
                print(f"  ! не найден канал для переименования: {keys}")
                continue
            if ch.name != new_name and ch.name.casefold() != new_name.casefold():
                ch = await ch.edit(name=new_name, reason="миграция: единый стиль имён")
                print(f"  переименован: {new_name!r} -> фактически {ch.name!r}")
            for k in keys:
                chans[k] = ch

        cat_support = chans["project support"]
        cat_important = chans["important"]
        cat_dev = chans["developments"]
        cat_chat = chans["chat"]
        cat_voice = get_any("голосовые каналы", "voice")

        # ---------- 2. Права IMPORTANT: категория + синхронизация детей
        await cat_important.edit(
            overwrites={guild.default_role: READONLY_EVERYONE, r_admin: POSTER_ADMIN},
            reason="миграция: read-only с читаемой историей, постят HoD/Administrator",
        )
        for key in ("rules", "announcements", "patches"):
            await chans[key].edit(sync_permissions=True, reason="миграция: sync с IMPORTANT")
        print("  IMPORTANT: права исправлены (история читается), дети синхронизированы")

        # Project Support — тот же read-only шаблон
        await cat_support.edit(
            overwrites={guild.default_role: READONLY_EVERYONE, r_admin: POSTER_ADMIN},
            reason="миграция: read-only категория донатов",
        )

        # ---------- 3. Новые каналы (идемпотентно: существующие пропускаем)
        async def ensure(kind, name, **kw):
            """Создать канал, если его ещё нет (безопасный перезапуск скрипта)."""
            k = norm_name(name)
            if k in chans:
                print(f"  существует, пропуск: {chans[k].name}")
                return chans[k]
            creator = {"text": guild.create_text_channel,
                       "voice": guild.create_voice_channel,
                       "forum": guild.create_forum,
                       "category": guild.create_category}[kind]
            c = await creator(name, **kw)
            chans[k] = c
            return c

        suggestions_is_new = norm_name("💡┃Suggestions") not in chans
        support_is_new = norm_name("🎫┃Support") not in chans

        donations = await ensure(
            "text", "💰┃Donations", category=cat_support, reason="миграция: канал реквизитов")
        await donations.edit(sync_permissions=True)

        # Suggestions: форум, закрыт до Closed Playtest
        suggestions = await ensure(
            "forum", "💡┃Suggestions", category=cat_dev, reason="миграция: форум предложений (закрыт)",
            overwrites={
                guild.default_role: ow(
                    view_channel=True, read_message_history=True, add_reactions=True,
                    send_messages=False, send_messages_in_threads=False,
                    create_public_threads=False, create_private_threads=False),
                r_admin: POSTER_ADMIN,
            })
        support = await ensure(
            "text", "🎫┃Support", category=cat_dev, reason="миграция: поддержка (закрыта)",
            overwrites={
                guild.default_role: READONLY_EVERYONE,
                r_admin: POSTER_ADMIN,
            })

        # Behind-The-Scenes: посты создаёт команда, отвечать могут все
        await chans["behindthescenes"].edit(
            overwrites={
                guild.default_role: ow(
                    view_channel=True, read_message_history=True, add_reactions=True,
                    send_messages_in_threads=True,
                    create_public_threads=False, create_private_threads=False),
                r_admin: POSTER_ADMIN,
            },
            reason="миграция: devlog-посты только от команды")

        # ---------- 4. Категория TESTING (Beta Tester + Moderator + Administrator)
        cat_testing = await ensure(
            "category", "🧪 TESTING", reason="миграция: закрытая зона тестов",
            overwrites={
                guild.default_role: ow(view_channel=False),
                r_tester: ow(view_channel=True),
                r_mod: ow(view_channel=True),
                r_admin: ow(view_channel=True),
            })
        test_info = await ensure(
            "text", "📋┃Test-Info", category=cat_testing, reason="миграция: инструкции тестов",
            overwrites={
                guild.default_role: ow(view_channel=False),
                r_tester: ow(view_channel=True, send_messages=False),
                r_mod: ow(view_channel=True, send_messages=False),
                r_admin: POSTER_ADMIN,
            })
        playtest_chat = await ensure(
            "text", "🧪┃Playtest-Chat", category=cat_testing, reason="миграция")
        await playtest_chat.edit(sync_permissions=True)
        bug_reports = await ensure(
            "text", "🐞┃Bug-Reports", category=cat_testing, reason="миграция")
        await bug_reports.edit(sync_permissions=True)
        test_voice = await ensure(
            "voice", "🧪 Test Voice", category=cat_testing, reason="миграция")
        await test_voice.edit(sync_permissions=True)

        # ---------- 5. Категория STAFF (Moderator + Administrator; HoD/бот проходят как админы)
        cat_staff = await ensure(
            "category", "🔒 STAFF", reason="миграция: зона команды",
            overwrites={
                guild.default_role: ow(view_channel=False),
                r_mod: ow(view_channel=True),
                r_admin: ow(view_channel=True),
            })
        staff_chat = await ensure(
            "text", "👮┃Staff-Chat", category=cat_staff, reason="миграция")
        await staff_chat.edit(sync_permissions=True)
        mod_log = await ensure(
            "text", "📝┃Mod-Log", category=cat_staff, reason="миграция: журнал модерации (пишет бот)",
            overwrites={
                guild.default_role: ow(view_channel=False),
                r_mod: ow(view_channel=True, send_messages=False),
                r_admin: ow(view_channel=True, send_messages=False),
            })
        discord_updates = await ensure(
            "text", "🔔┃Discord-Updates", category=cat_staff, reason="миграция: служебные сообщения Discord",
            overwrites={
                guild.default_role: ow(view_channel=False),
                r_mod: ow(view_channel=True, send_messages=False),
                r_admin: ow(view_channel=True, send_messages=False),
            })

        # ---------- 6. Голосовые
        await ensure("voice", "🔊 General", category=cat_voice, reason="миграция")
        await ensure("voice", "🎙️ Dev Talk", category=cat_voice, reason="миграция")
        for i in (1, 2, 3):
            await ensure("voice", f"Room {i}", category=cat_voice, reason="миграция")
        afk = await ensure("voice", "💤 AFK", category=cat_voice, reason="миграция")
        await guild.edit(afk_channel=afk, afk_timeout=900, reason="миграция: AFK 15 минут")

        # ---------- 7. Удаление пустой категории по умолчанию
        empty_cat = chans.get("текстовые каналы")
        if empty_cat is not None:
            live = await guild.fetch_channels()
            children = [c for c in live if c.category_id == empty_cat.id]
            if children:
                print(f"  ! «Текстовые каналы» не пуста ({[c.name for c in children]}), не удаляю")
            else:
                await empty_cat.delete(reason="миграция: пустая категория по умолчанию")
                print("  удалена пустая категория «Текстовые каналы»")

        # ---------- 8. Порядок категорий
        order = [cat_support, cat_important, cat_dev, cat_chat, cat_testing, cat_voice, cat_staff]
        for pos, cat in enumerate(order):
            await cat.edit(position=pos)
        print("  порядок категорий выставлен")

        # ---------- 9. Согласованные посты-заглушки (только при первом создании каналов)
        if suggestions_is_new:
            thread = await suggestions.create_thread(
                name=SUGGESTIONS_POST_TITLE, content=SUGGESTIONS_POST,
                allowed_mentions=discord.AllowedMentions.none())
            print(f"  пост в Suggestions: {thread.thread.jump_url}")
        if support_is_new:
            sup_msg = await support.send(SUPPORT_POST, allowed_mentions=discord.AllowedMentions.none())
            await sup_msg.pin(reason="миграция: закреплён пост о статусе поддержки")
            print(f"  пост в Support: {sup_msg.jump_url}")

        print("\nГотово. Новые ID:")
        for label, c in [("Donations", donations), ("Suggestions", suggestions),
                         ("Support", support), ("Test-Info", test_info),
                         ("Playtest-Chat", playtest_chat), ("Bug-Reports", bug_reports),
                         ("Staff-Chat", staff_chat), ("Mod-Log", mod_log),
                         ("Discord-Updates", discord_updates), ("AFK", afk)]:
            print(f"  {label}: {c.id}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
