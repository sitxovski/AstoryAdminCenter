#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""announce_restart — объявление о перезапуске игрового сервера в канал тестеров с упоминанием роли Beta Tester.

Слово владельца 21.10.2026: перед перезапуском стойки — сообщение в канал testing-info всем @BetaTester на английском,
арабском и русском, затем 3 минуты и перезапуск.

  python announce_restart.py --dry            — найти канал и роль, показать текст, ничего не отправлять
  python announce_restart.py [--minutes 3]    — отправить

Канал ищется по имени (без эмодзи и знаков): «test-info» (владелец называет его testing-info); роль — «beta tester». Упоминается ТОЛЬКО эта роль
(AllowedMentions: roles=[роль], без @everyone и пользователей).
"""

import argparse
import asyncio
import re

import discord

from botctl import connect, norm_name


def text_for(role_mention: str, minutes: int, kind: str = "restart") -> str:
    """Текст объявления на трёх языках. kind = stop — остановка на обслуживание без запуска (админ-центр А5.1, 20.11.2026:
    restart_stack.py --stop-only). ★ 20.11 (ревизия 41): в тексте остановки по-арабски «بعد» («через»), а не «خلال» («в течение»);
    слово «минута» согласуется с числом на всех трёх языках (при 3 минутах текст рестарта — прежний, буква в букву)."""
    n = int(minutes)
    en = "minute" if n == 1 else "minutes"
    ru = "минуту" if n % 10 == 1 and n % 100 != 11 else ("минуты" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "минут")
    ar = "دقيقة" if n == 1 else ("دقيقتين" if n == 2 else ("دقائق" if 3 <= n <= 10 else "دقيقة"))
    if kind == "stop":
        return (
            f"{role_mention}\n"
            f"🇬🇧 **The game server will be shut down for maintenance in {minutes} {en}.** Please finish what you are doing and log out safely.\n"
            f"🇸🇦 **سيتم إيقاف خادم اللعبة للصيانة بعد {minutes} {ar}.** يرجى إنهاء ما تقوم به وتسجيل الخروج بأمان.\n"
            f"🇷🇺 **Игровой сервер будет остановлен на обслуживание через {minutes} {ru}.** Пожалуйста, завершите текущие дела и безопасно выйдите из игры."
        )
    return (
        f"{role_mention}\n"
        f"🇬🇧 **The game server will be restarted in {minutes} {en}.** Please finish what you are doing and log out safely.\n"
        f"🇸🇦 **سيتم إعادة تشغيل خادم اللعبة خلال {minutes} {ar}.** يرجى إنهاء ما تقوم به وتسجيل الخروج بأمان.\n"
        f"🇷🇺 **Игровой сервер будет перезапущен через {minutes} {ru}.** Пожалуйста, завершите текущие дела и безопасно выйдите из игры."
    )


async def run(dry: bool, minutes: int, kind: str = "restart") -> None:
    client, guild = await connect()
    try:
        # ★ 10.11: fetch_channels() падает на неизвестном discord.py типе канала (20) — берём сырой список и только текстовые (type 0)
        raw = await client.http.get_all_guild_channels(guild.id)
        key = lambda n: re.sub(r"[^a-z0-9]", "", norm_name(n))
        ids = [int(d["id"]) for d in raw if d.get("type") == 0 and key(d.get("name", "")) in ("testinfo", "testinginfo")]
        chans = [await client.fetch_channel(i) for i in ids]
        roles = [r for r in await guild.fetch_roles() if norm_name(r.name) == "beta tester"]
        if len(chans) != 1 or len(roles) != 1:
            raise SystemExit(f"Нужно ровно по одному: каналов testing-info {len(chans)} ({[c.name for c in chans]}), "
                             f"ролей Beta Tester {len(roles)} ({[r.name for r in roles]})")
        channel, role = chans[0], roles[0]
        text = text_for(role.mention, minutes, kind)
        print(f"канал #{channel.name} ({channel.id}), роль {role.name} ({role.id})")
        print(text)
        if dry:
            print("--dry: ничего не отправлено")
            return
        msg = await channel.send(text, allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role]))
        print(f"Отправлено: {msg.jump_url}")
    finally:
        await client.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--minutes", type=int, default=3)
    ap.add_argument("--kind", choices=("restart", "stop"), default="restart")   # ★ 20.11 (А5.1): stop — остановка на обслуживание
    a = ap.parse_args()
    asyncio.run(run(a.dry, a.minutes, a.kind))


if __name__ == "__main__":
    main()
