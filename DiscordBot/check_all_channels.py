#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Сверка эффективных прав всех каналов с эталоном зон.

Discord считает права ТОЛЬКО по оверрайдам самого канала (категория — шаблон),
поэтому проверяем каждый канал отдельно. Находки печатаются списком.
"""

import asyncio

import discord

from botctl import connect, norm_name

PRIVATE_CATS = {"testing", "staff"}          # @everyone не должен видеть
LOBBY = "lobby"                              # единственный канал письма @everyone


def eff(ow: discord.PermissionOverwrite | None, attr: str, base: bool) -> bool:
    """Эффективное значение права: явный оверрайд или базовое из роли."""
    if ow is None:
        return base
    v = getattr(ow, attr)
    return base if v is None else v


async def main() -> None:
    client, guild = await connect()
    problems: list[str] = []
    try:
        roles = {norm_name(r.name): r for r in await guild.fetch_roles()}
        ev = guild.default_role
        base_view = ev.permissions.read_messages
        base_hist = ev.permissions.read_message_history
        base_send = ev.permissions.send_messages
        r_tester, r_mod, r_admin = roles["beta tester"], roles["moderator"], roles["administrator"]

        chans = await guild.fetch_channels()
        cats = {c.id: c for c in chans if isinstance(c, discord.CategoryChannel)}
        for c in chans:
            if isinstance(c, discord.CategoryChannel):
                continue
            cat_key = norm_name(cats[c.category_id].name) if c.category_id else ""
            o_ev = c.overwrites.get(ev)
            view = eff(o_ev, "view_channel", base_view)
            hist = eff(o_ev, "read_message_history", base_hist)
            send = eff(o_ev, "send_messages", base_send)
            is_private = cat_key in PRIVATE_CATS
            name = c.name

            if is_private:
                if view:
                    problems.append(f"{name}: ПРИВАТНЫЙ, но @everyone видит канал")
                for r, label in ((r_tester, "Beta Tester") if cat_key == "testing" else (r_mod, "Moderator"),
                                 (r_mod, "Moderator") if cat_key == "testing" else (r_admin, "Administrator")):
                    o = c.overwrites.get(r)
                    if not eff(o, "view_channel", False):
                        problems.append(f"{name}: роль {label} НЕ видит канал")
            else:
                if not view:
                    problems.append(f"{name}: публичный, но @everyone НЕ видит")
                if not hist and not isinstance(c, discord.VoiceChannel):
                    problems.append(f"{name}: @everyone не может читать ИСТОРИЮ")
                if norm_name(name) == LOBBY:
                    if not send:
                        problems.append(f"{name}: lobby должен быть писабельным для @everyone")
                elif send and not isinstance(c, discord.VoiceChannel):
                    problems.append(f"{name}: @everyone может ПИСАТЬ (не должен, писать можно только в lobby)")

        if problems:
            print("НАЙДЕНЫ ПРОБЛЕМЫ:")
            for p in problems:
                print("  ✗", p)
        else:
            print("Все каналы в порядке: видимость, история, письмо — по эталону зон.")
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
