#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Аудит безопасности сервера: роли, права, видимость каналов, вебхуки, инвайты,
AutoMod, настройки гильдии, боты. Результат — в security_report.txt и stdout."""

import asyncio
import json
from pathlib import Path

import discord
from botctl import connect

DANGEROUS = ("administrator", "manage_guild", "manage_roles", "manage_channels",
             "manage_webhooks", "manage_messages", "mention_everyone", "ban_members",
             "kick_members", "moderate_members", "manage_nicknames", "manage_threads")

OUT = Path(__file__).parent / "security_report.txt"


async def main() -> None:
    client, guild = await connect()
    lines: list[str] = []
    p = lines.append
    try:
        # ---------- гильдия
        g = await client.http.request(
            discord.http.Route("GET", "/guilds/{guild_id}", guild_id=guild.id))
        p(f"[ГИЛЬДИЯ] verification={g.get('verification_level')} (0=none..4=highest)")
        p(f"[ГИЛЬДИЯ] mfa_level={g.get('mfa_level')} (0=2FA для модерации НЕ требуется, 1=требуется)")
        p(f"[ГИЛЬДИЯ] explicit_content_filter={g.get('explicit_content_filter')} (2=фильтр для всех)")
        p(f"[ГИЛЬДИЯ] default_notifications={g.get('default_message_notifications')} (1=only mentions)")
        p(f"[ГИЛЬДИЯ] owner_id={g.get('owner_id')}")

        # ---------- роли: опасные права
        roles = await guild.fetch_roles()
        p("\n[РОЛИ] опасные права:")
        for r in sorted(roles, key=lambda r: -r.position):
            bad = [n for n in DANGEROUS if getattr(r.permissions, n)]
            flags = []
            if r.mentionable:
                flags.append("MENTIONABLE")
            if bad or flags:
                p(f"  {r.position:2} {r.name!r}: {', '.join(bad) or '-'} {' '.join(flags)}")

        # ---------- каналы: эффективная видимость/письмо для @everyone
        chans = await guild.fetch_channels()
        cats = {c.id: c for c in chans if isinstance(c, discord.CategoryChannel)}
        ev = guild.default_role
        p("\n[КАНАЛЫ] эффективные права @everyone (view/write):")
        base_view = ev.permissions.read_messages
        base_write = ev.permissions.send_messages
        for c in sorted(chans, key=lambda c: (c.category_id or 0, c.position)):
            if isinstance(c, discord.CategoryChannel):
                continue
            src = c.overwrites.get(ev)
            if src is None and c.category_id:
                src = cats[c.category_id].overwrites.get(ev)
            view, write = base_view, base_write
            if src is not None:
                if src.view_channel is not None:
                    view = src.view_channel
                if src.send_messages is not None:
                    write = src.send_messages
            cat = cats[c.category_id].name if c.category_id else "-"
            p(f"  {'V' if view else '.'}{'W' if write else '.'} [{cat}] {c.name} ({c.type})")

        # ---------- вебхуки
        p("\n[ВЕБХУКИ]:")
        hooks = await guild.webhooks()
        if not hooks:
            p("  нет")
        for h in hooks:
            p(f"  {h.name!r} в #{h.channel} | тип {h.type} | создатель {h.user}")

        # ---------- инвайты
        p("\n[ИНВАЙТЫ]:")
        invites = await guild.invites()
        for i in invites:
            p(f"  {i.code}: канал #{i.channel}, автор {i.inviter}, "
              f"исп. {i.uses}, max_age={i.max_age}, temporary={i.temporary}")

        # ---------- AutoMod
        p("\n[AUTOMOD] правила:")
        try:
            rules = await guild.fetch_automod_rules()
            if not rules:
                p("  НЕТ ПРАВИЛ")
            for r in rules:
                p(f"  {r.name!r}: enabled={r.enabled}, trigger={r.trigger.type.name}")
        except discord.HTTPException as e:
            p(f"  не прочитать: {e.status}")

        # ---------- боты
        p("\n[БОТЫ] на сервере:")
        after = 0
        while True:
            page = await client.http.get_members(guild.id, 1000, after)
            if not page:
                break
            for m in page:
                if m["user"].get("bot"):
                    p(f"  {m['user']['username']} (id {m['user']['id']}), роли: {m.get('roles')}")
            after = int(page[-1]["user"]["id"])

        text = "\n".join(lines)
        OUT.write_text(text, encoding="utf-8")
        print(text)
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
