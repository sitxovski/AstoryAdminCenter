#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""botctl — управление Discord-сервером Astory Remake Project через REST.

Работает без гейтвея и привилегированных интентов: чистый HTTP через discord.py.
Токен и ID сервера берутся из .env рядом со скриптом.

Команды:
  python botctl.py audit                 — снять полную структуру сервера в audit.json
  python botctl.py apply-roles [--dry]   — привести роли к server_plan.yaml (без удалений)
  python botctl.py enable-community --rules <channel_id> --updates <channel_id>
  python botctl.py post --channel <channel_id> --file <text.md>
  python botctl.py botinfo               — кто я: роль бота, права, позиция в иерархии
"""

import argparse
import asyncio
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import discord
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent          # папка DiscordBot
load_dotenv(ROOT / ".env")
TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
PLAN_PATH = ROOT / "server_plan.yaml"  # декларативный план сервера
AUDIT_PATH = ROOT / "audit.json"       # результат команды audit


def norm_name(name: str) -> str:
    """Нормализация имени роли: без эмодзи/символов, один пробел, casefold."""
    kept = "".join(ch for ch in name if unicodedata.category(ch)[0] in ("L", "N") or ch.isspace())
    return re.sub(r"\s+", " ", kept).strip().casefold()


def perms_from_list(names: list[str]) -> discord.Permissions:
    """Собрать Permissions из списка имён прав discord.py (например manage_roles)."""
    valid = dict(discord.Permissions.none())  # имя права -> False
    for n in names:
        if n not in valid:
            raise SystemExit(f"Неизвестное право в плане: {n}")
    return discord.Permissions(**{n: True for n in names})


def perm_names(p: discord.Permissions) -> list[str]:
    """Обратное преобразование: Permissions -> отсортированный список имён включённых прав."""
    return sorted(name for name, on in p if on)


def color_from(value) -> discord.Colour:
    """Цвет из '#RRGGBB' либо null (цвет по умолчанию)."""
    if value in (None, "", "default"):
        return discord.Colour.default()
    return discord.Colour(int(str(value).lstrip("#"), 16))


async def connect() -> tuple[discord.Client, discord.Guild]:
    """Логин по REST и получение гильдии (без gateway)."""
    if not TOKEN or "ВСТАВЬ" in TOKEN:
        raise SystemExit("Сначала вставь токен бота в AstoryAdminCenter/DiscordBot/.env (DISCORD_TOKEN=...)")
    # ★ 25.11 (К-5): прокси — только из DISCORD_PROXY / HTTPS_PROXY (.env); не задан, пусто или none — прямое соединение
    import botcfg
    proxy = botcfg.proxy("DISCORD_PROXY", "HTTPS_PROXY")
    client = discord.Client(intents=discord.Intents.none(), proxy=proxy)
    await client.login(TOKEN)
    guild = await client.fetch_guild(GUILD_ID, with_counts=True)
    return client, guild


# ---------------------------------------------------------------- audit

async def cmd_audit(_args) -> None:
    """Полный слепок сервера: гильдия, роли, каналы с оверрайдами — в audit.json."""
    client, guild = await connect()
    try:
        roles = await guild.fetch_roles()
        channels = await guild.fetch_channels()
        me = await guild.fetch_member(client.user.id)

        role_by_id = {r.id: r for r in roles}
        data = {
            "guild": {
                "id": guild.id,
                "name": guild.name,
                "features": guild.features,                      # смотреть COMMUNITY
                "verification_level": str(guild.verification_level),
                "default_notifications": str(guild.default_notifications),
                "member_count": guild.approximate_member_count,
            },
            "bot": {
                "name": str(me),
                "top_role": me.top_role.name if me.top_role else None,
                "top_role_position": me.top_role.position if me.top_role else None,
                "guild_permissions": perm_names(me.guild_permissions),
            },
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "position": r.position,
                    "color": f"#{r.colour.value:06X}",
                    "hoist": r.hoist,
                    "mentionable": r.mentionable,
                    "managed": r.managed,               # интеграционная роль (бота/буста)
                    "permissions": perm_names(r.permissions),
                }
                for r in sorted(roles, key=lambda r: -r.position)
            ],
            "channels": [
                {
                    "id": c.id,
                    "name": c.name,
                    "type": str(c.type),
                    "position": c.position,
                    "category_id": c.category_id,
                    "overwrites": [
                        {
                            "target": role_by_id[t_id].name if t_id in role_by_id else str(t_id),
                            "allow": perm_names(discord.Permissions(ow.pair()[0].value)),
                            "deny": perm_names(discord.Permissions(ow.pair()[1].value)),
                        }
                        for t_id, ow in (
                            (t.id if hasattr(t, "id") else t, ow)
                            for t, ow in c.overwrites.items()
                        )
                    ],
                }
                for c in sorted(channels, key=lambda c: (c.type is not discord.ChannelType.category, c.position))
            ],
        }
        AUDIT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Сервер: {guild.name} | участников ~{guild.approximate_member_count}")
        print(f"COMMUNITY: {'да' if 'COMMUNITY' in guild.features else 'НЕТ'}")
        print(f"Бот: {me} | верхняя роль: {me.top_role.name} (поз. {me.top_role.position}) | "
              f"admin: {me.guild_permissions.administrator}")
        print(f"Ролей: {len(roles)} | каналов: {len(channels)}")
        print(f"Слепок: {AUDIT_PATH}")
    finally:
        await client.close()


# ---------------------------------------------------------------- botinfo

async def cmd_botinfo(_args) -> None:
    """Короткая справка: кем бот является на сервере и что ему позволено."""
    client, guild = await connect()
    try:
        me = await guild.fetch_member(client.user.id)
        print(f"Бот: {me} (id {me.id})")
        print(f"Роли бота: {', '.join(r.name for r in me.roles if r.name != '@everyone') or 'нет'}")
        print(f"Позиция верхней роли: {me.top_role.position}")
        print(f"Administrator: {me.guild_permissions.administrator}")
        print(f"Ключевые права: " + ", ".join(n for n in (
            "manage_guild", "manage_roles", "manage_channels", "manage_messages",
            "kick_members", "ban_members", "moderate_members") if getattr(me.guild_permissions, n)))
    finally:
        await client.close()


# ---------------------------------------------------------------- apply-roles

async def cmd_apply_roles(args) -> None:
    """Синхронизация ролей с server_plan.yaml. Создаёт/правит/упорядочивает, не удаляет."""
    plan = yaml.safe_load(PLAN_PATH.read_text(encoding="utf-8"))
    specs = plan["roles"]
    ignore = {norm_name(n) for n in plan.get("ignore_roles", [])}

    client, guild = await connect()
    try:
        me = await guild.fetch_member(client.user.id)
        roles = await guild.fetch_roles()
        existing = {norm_name(r.name): r for r in roles if not r.is_default()}
        changed, created = [], []

        for spec in specs:
            key = norm_name(spec["name"])
            want_perms = perms_from_list(spec.get("permissions") or [])
            want_color = color_from(spec.get("color"))
            role = existing.get(key)

            if role is None:
                if args.dry:
                    created.append(spec["name"])
                    continue
                role = await guild.create_role(
                    name=spec["name"], colour=want_color, hoist=spec.get("hoist", False),
                    mentionable=spec.get("mentionable", False), permissions=want_perms,
                    reason="botctl apply-roles",
                )
                existing[key] = role
                created.append(role.name)
            else:
                diffs = {}
                if role.name != spec["name"]:
                    diffs["name"] = spec["name"]
                if role.colour != want_color:
                    diffs["colour"] = want_color
                if role.hoist != spec.get("hoist", False):
                    diffs["hoist"] = spec.get("hoist", False)
                if role.mentionable != spec.get("mentionable", False):
                    diffs["mentionable"] = spec.get("mentionable", False)
                if role.permissions != want_perms:
                    diffs["permissions"] = want_perms
                if diffs:
                    if role.managed:
                        print(f"  ! {role.name}: интеграционная роль, пропуск")
                    elif role.position >= me.top_role.position:
                        print(f"  ! {role.name}: выше роли бота, не могу править — подними роль бота")
                    elif args.dry:
                        changed.append(f"{role.name}: {', '.join(diffs)}")
                    else:
                        await role.edit(reason="botctl apply-roles", **diffs)
                        changed.append(f"{role.name}: {', '.join(diffs)}")

        # Порядок: роли плана сверху вниз, сразу под верхней ролью бота
        if not args.dry:
            desired = [existing[norm_name(s["name"])] for s in specs
                       if norm_name(s["name"]) in existing]
            movable = [r for r in desired
                       if not r.managed and r.position < me.top_role.position]
            top = me.top_role.position
            positions = {r: top - 1 - i for i, r in enumerate(movable)}
            positions = {r: max(p, 1) for r, p in positions.items()}
            await guild.edit_role_positions(positions, reason="botctl apply-roles: порядок")

        # Лишние роли — только отчёт
        plan_keys = {norm_name(s["name"]) for s in specs}
        extras = [r.name for k, r in existing.items()
                  if k not in plan_keys and k not in ignore and not r.managed]

        print(f"Создано: {created or '—'}")
        print(f"Исправлено: {changed or '—'}")
        if extras:
            print(f"Вне плана (не тронуты): {extras}")
        if args.dry:
            print("(dry-run: на сервере ничего не менялось)")
    finally:
        await client.close()


# ---------------------------------------------------------------- enable-community

async def cmd_enable_community(args) -> None:
    """Включить режим сообщества: правила + канал отчётов модерации + безопасные дефолты."""
    client, guild = await connect()
    try:
        channels = {c.id: c for c in await guild.fetch_channels()}
        rules = channels.get(args.rules)
        updates = channels.get(args.updates)
        if not rules or not updates:
            raise SystemExit("Каналы не найдены: проверь --rules и --updates (ID каналов)")
        await guild.edit(
            community=True,
            rules_channel=rules,
            public_updates_channel=updates,
            verification_level=discord.VerificationLevel.medium,
            default_notifications=discord.NotificationLevel.only_mentions,
            explicit_content_filter=discord.ContentFilter.all_members,
            reason="botctl enable-community",
        )
        print(f"Сообщество включено. Правила: #{rules.name}, отчёты Discord: #{updates.name}")
    finally:
        await client.close()


# ---------------------------------------------------------------- post

async def cmd_post(args) -> None:
    """Отправить текст из файла в канал (для правил/анонсов; использовать по согласованию)."""
    text = Path(args.file).read_text(encoding="utf-8")
    if len(text) > 2000:
        raise SystemExit(f"Текст {len(text)} символов (>2000) — разбей на части")
    client, guild = await connect()
    try:
        channel = await client.fetch_channel(args.channel)
        msg = await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        print(f"Отправлено в #{channel.name}: {msg.jump_url}")
    finally:
        await client.close()


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("audit")
    sub.add_parser("botinfo")

    p = sub.add_parser("apply-roles")
    p.add_argument("--dry", action="store_true", help="показать изменения, не применять")

    p = sub.add_parser("enable-community")
    p.add_argument("--rules", type=int, required=True, help="ID канала правил")
    p.add_argument("--updates", type=int, required=True, help="ID канала для сообщений Discord модераторам")

    p = sub.add_parser("post")
    p.add_argument("--channel", type=int, required=True, help="ID канала")
    p.add_argument("--file", required=True, help="файл с текстом сообщения")

    args = ap.parse_args()
    handler = {
        "audit": cmd_audit,
        "botinfo": cmd_botinfo,
        "apply-roles": cmd_apply_roles,
        "enable-community": cmd_enable_community,
        "post": cmd_post,
    }[args.cmd]
    asyncio.run(handler(args))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
