# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""discordlinks.py — привязка «логин игры ↔ Discord» и реестр банов Discord для карточки учётки (А1 «Учётки», 19.11.2026).

ИСТОЧНИК ИСТИНЫ — бот AstoryAdminCenter/DiscordBot (research_accounts_rest.md §6): в базах сервера Discord нет ни одного столбца.
  playtest_accounts.txt  строки «Discord-имя (@handle) [discord_id] - логин/пароль» (и закомментированные «# BANNED дата …»).
                         ⚠ В файле ПАРОЛИ открытым текстом — панель его не копирует и не читает. Выкладка (deploy_admin_center.py)
                         разбирает его на ПК функцией parse_playtest() и кладёт в пакет data/ref/discord_links.json ТОЛЬКО
                         @handle, Discord ID, логин и пометку бана — без паролей и без ника на сервере Discord.
  BANNED_PLAYERS.md      реестр исключённых (копия data/ref/banned_players.md — domains/gifts.banned()).
ПАНЕЛЬ: поиск по Discord ID (15–20 цифр) и @handle; в карточке — привязка и «в реестре банов»; расхождение «в Discord бан, а вход
  в игру не заблокирован» — в карточке и списком (discord_bans) с кнопкой блока; блокирует оператор, сама панель — нет.
Запись привязки из панели не делается (источник истины — бот). Побочных эффектов при импорте нет.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LINKS = os.path.join(os.path.dirname(HERE), "data", "ref", "discord_links.json")
# «[# BANNED 2026-10-27 ]Имя (@handle) [123…] - логин/…» — после «/» (пароль) ничего не захватывается
LINE_RX = re.compile(r"^\s*(?:#\s*BANNED\s+(\d{4}-\d{2}-\d{2})\s+)?.*?\(@([^)\s]+)\)\s*\[(\d{15,20})\]\s*-\s*([A-Za-z0-9_.@-]{1,32})/")
DISCORD_ID_RX = re.compile(r"^\d{15,20}$")
HANDLE_RX = re.compile(r"^@[A-Za-z0-9_.]{2,32}$")


def parse_playtest(lines):
    """Строки playtest_accounts.txt → [{handle, discord_id, login, banned}] (пароль не захватывается регуляркой)."""
    out = []
    for ln in lines:
        m = LINE_RX.match(ln)
        if not m:
            continue
        if ln.lstrip().startswith("#") and not m.group(1):
            continue                                          # прочие комментарии — не привязки
        out.append({"handle": m.group(2), "discord_id": m.group(3), "login": m.group(4), "banned": m.group(1)})
    return out


def build_json(src_path):
    """Файл бота → текст discord_links.json (для выкладки)."""
    with open(src_path, encoding="utf-8") as f:
        links = parse_playtest(f.read().splitlines())
    return json.dumps({"source": "playtest_accounts.txt (без паролей)", "links": links}, ensure_ascii=False, indent=1)


_cache = {}


def links(path=None):
    """[{handle, discord_id, login, banned}] из копии; копии нет — []."""
    p = path or LINKS
    try:
        st = os.stat(p)
    except OSError:
        return []
    key = (p, st.st_mtime, st.st_size)
    if _cache.get("k") != key:
        try:
            with open(p, encoding="utf-8") as f:
                _cache.update(k=key, v=json.load(f).get("links") or [])
        except (OSError, ValueError):
            _cache.update(k=key, v=[])
    return _cache["v"]


def by_login(login, items=None):
    """Привязка по логину (без учёта регистра) или None."""
    if not login:
        return None
    lo = login.lower()
    return next((x for x in (items if items is not None else links()) if (x.get("login") or "").lower() == lo), None)


def find(q, items=None):
    """Запрос поиска → логины: Discord ID — точно, @handle — по началу (без учёта регистра). Не похоже на Discord — []."""
    q = (q or "").strip()
    items = items if items is not None else links()
    if DISCORD_ID_RX.match(q):
        return [(x["login"], "Discord ID") for x in items if x.get("discord_id") == q]
    if HANDLE_RX.match(q):
        h = q[1:].lower()
        return [(x["login"], "Discord @" + x["handle"]) for x in items if (x.get("handle") or "").lower().startswith(h)]
    return []


def card(uid, login, block, items=None, banned=None):
    """Блок «Discord» карточки учётки: привязка, реестр банов, расхождение с блоком входа."""
    if banned is None:
        from domains import gifts
        banned = gifts.banned()
    ln = by_login(login, items)
    in_reg = bool(banned) and int(uid) in banned
    active = bool(block) and block.get("state") == "active"
    return {"handle": ln["handle"] if ln else None, "discord_id": ln["discord_id"] if ln else None,
            "list_banned": ln["banned"] if ln else None, "banned_registry": in_reg,
            "registry_known": banned is not None, "mismatch": in_reg and not active}
