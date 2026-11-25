#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Добавить 中文 (традиционный) во все публичные посты: rules, can't-type, donations,
suggestions, support, lobby. Идемпотентно: пропускает, где 中文 уже есть."""

import asyncio

import discord

from botctl import connect
from botcfg import discord_id  # ★ 25.11 (С-4): заглушка не заменена — 0 с предупреждением, без падения при импорте

RULES_ZH = """\
# 🌟 歡迎來到 Astory Remake Project!

我們正在重製經典 MMORPG **Asda Story** — 而你也是其中的一份子。\
幾條簡單的規則,讓大家都舒服:

1. 🤝 **友善待人。** 禁止辱罵、騷擾與仇恨言論。
2. 📢 **未經管理團隊許可,禁止廣告與自我宣傳**(包括私訊)。
3. 🚫 **禁止刷屏**、洗版與濫用提及。
4. 🌍 **請遵守語言頻道:** 💬┃general 可使用任何語言,各語言另有專屬頻道。
5. 🔞 **禁止 NSFW** 與令人不適的內容。
6. ⚖️ **禁止政治與宗教話題。**
7. 🛡️ **管理團隊的決定為最終決定。** 有問題請私訊版主,勿在公開頻道爭論。
8. 💙 **發現問題?** 🎫┃support 將於封閉測試開放,在那之前請聯絡版主。

違規處理:警告 → 禁言 → 封鎖。祝你玩得開心!✨
"""

CANT_TYPE_ZH = ("\n\n**中文** — 完成快速入門後即可聊天:打開 <id:customize>,"
                "選擇你的語言(想要的話也可以選通知)— 馬上就能發言!迷路了?看看 <id:guide>。")

DONATIONS_ZH = ("**中文** — Astory Remake 是粉絲用熱情打造的專案。捐助永遠是**自願的** — "
                "它們幫助我們支付伺服器與開發工具的費用。感謝你對專案的信任!💙\n\n")

SUGGESTIONS_ZH = ("\n\n**中文** — 此論壇暫時關閉。當專案進入**封閉測試**階段時,"
                  "我們將開放建議區,讓想法能在可遊玩的版本上驗證。請關注 📣┃Announcements!")

SUPPORT_ZH = ("\n\n**中文** — 客服/工單系統尚未上線,將與**封閉測試**一同開放。"
              "在此之前,歡迎在 💬┃General 提問。")

LOBBY_ZH = ("\n\n**中文** — 選擇語言後即可解鎖聊天:打開 <id:customize>,"
            "回答幾個簡單問題(語言是關鍵)— 所有頻道將立即開放。不知道從哪開始?看看 <id:guide>。")

RULES_CH = discord_id("@@ASTORY_DISCORD_RULES_CH@@", "rules")
DONATIONS_CH = discord_id("@@ASTORY_DISCORD_DONATIONS_CH@@", "donations")
DONATIONS_MSG = discord_id("@@ASTORY_DISCORD_DONATIONS_MSG@@", "donations: сообщение")
SUGGESTIONS_CH = discord_id("@@ASTORY_DISCORD_SUGGESTIONS_CH@@", "suggestions")
SUPPORT_CH = discord_id("@@ASTORY_DISCORD_SUPPORT_CH@@", "support")
LOBBY_CH = discord_id("@@ASTORY_DISCORD_LOBBY_CH@@", "lobby")
NO_PING = discord.AllowedMentions.none()


async def append(msg: discord.Message, block: str, label: str) -> None:
    """Дописать блок в конец сообщения, если 中文 ещё нет."""
    if "中文** —" in msg.content or "**中文**" in msg.content:
        print(f"  {label}: 中文 уже есть")
        return
    new = msg.content + block
    assert len(new) <= 2000, f"{label}: {len(new)} символов"
    await msg.edit(content=new, allowed_mentions=NO_PING)
    print(f"  {label}: дополнено")


async def main() -> None:
    client, guild = await connect()
    try:
        # 1. Правила: отдельное 中文-сообщение
        rules = await client.fetch_channel(RULES_CH)
        history = [m async for m in rules.history(limit=20)]
        if not any("歡迎來到" in m.content for m in history):
            await rules.send(RULES_ZH, allowed_mentions=NO_PING)
            print("  Rules: 中文-версия опубликована")
        else:
            print("  Rules: 中文 уже есть")

        # 2. Закреп «Can't type?» в правилах
        cant = next(m for m in history if "<id:customize>" in m.content)
        await append(cant, CANT_TYPE_ZH, "Can't-type")

        # 3. Donations: блок перед реквизитами
        don = await (await client.fetch_channel(DONATIONS_CH)).fetch_message(DONATIONS_MSG)
        if "中文" in don.content:
            print("  Donations: 中文 уже есть")
        else:
            idx = don.content.find("\U0001FA99")  # 🪙
            new = don.content[:idx] + DONATIONS_ZH + don.content[idx:]
            assert len(new) <= 2000, len(new)
            await don.edit(content=new, allowed_mentions=NO_PING)
            print("  Donations: дополнено")

        # 4. Suggestions: стартовое сообщение треда-заглушки
        threads = (await guild.active_threads())
        sug_thread = next(t for t in threads if t.parent_id == SUGGESTIONS_CH)
        starter = await sug_thread.fetch_message(sug_thread.id)
        await append(starter, SUGGESTIONS_ZH, "Suggestions")

        # 5. Support: закреплённый пост
        support = await client.fetch_channel(SUPPORT_CH)
        pin = [m async for m in support.history(limit=5, oldest_first=True)][0]
        await append(pin, SUPPORT_ZH, "Support")

        # 6. Lobby: закреплённый пост
        lobby = await client.fetch_channel(LOBBY_CH)
        lpin = next(m async for m in lobby.history(limit=10) if "<id:customize>" in m.content)
        await append(lpin, LOBBY_ZH, "Lobby")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
