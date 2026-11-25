#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Применить улучшенные стили ролей: градиенты, голографику HoD, иконки-эмодзи.

Требует буст-уровень 2+ (градиенты, иконки) и 3 (голографика) — на сервере есть.
"""

import asyncio

import discord
from discord.http import Route

from botctl import connect, norm_name

# Голографический стиль — фиксированная тройка цветов, требуемая API
HOLO = {"primary_color": 11127295, "secondary_color": 16759788, "tertiary_color": 16761760}


def grad(a: str, b: str) -> dict:
    return {"primary_color": int(a, 16), "secondary_color": int(b, 16)}


# ключ нормализованного имени -> (colors, unicode_emoji | None)
STYLES = {
    "head of development": (HOLO, "🛠️"),
    "administrator":       (grad("E74C3C", "C0392B"), "⚙️"),
    "moderator":           (grad("3498DB", "2980B9"), "🛡️"),
    "beta tester":         (grad("2ECC71", "16A085"), "🧪"),
    "translator":          (grad("1ABC9C", "3498DB"), "🌍"),
    "early supporter":     (grad("9B59B6", "E91E63"), "⭐"),
    "server booster":      (grad("FF73FA", "9B59B6"), "💎"),
    "user":                (grad("7F8C8D", "95A5A6"), None),
    "oracle":              (grad("E67E22", "F39C12"), "🔮"),
}


async def main() -> None:
    client, guild = await connect()
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        for key, (colors, emoji) in STYLES.items():
            role = roles.get(key)
            if role is None:
                print(f"  ! роль не найдена: {key}")
                continue
            payload: dict = {"colors": colors}
            if emoji is not None:
                payload["unicode_emoji"] = emoji
            try:
                await client.http.request(
                    Route("PATCH", "/guilds/{guild_id}/roles/{role_id}",
                          guild_id=guild.id, role_id=role.id),
                    json=payload, reason="стили ролей: градиенты и иконки")
                kind = "holo" if "tertiary_color" in colors else "grad"
                print(f"  {role.name}: {kind}{' + ' + emoji if emoji else ''}")
            except discord.HTTPException as e:
                print(f"  ! {role.name}: {e.status} {e.text}")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
