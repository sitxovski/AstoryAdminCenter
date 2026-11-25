#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Live-статус игрового сервера для Discord: данные (БД + процессы) и вид панели.

Данные (синхронно, вызывать из потока):
  • кто в мире — Joy1.dbo.CharPos.UserNum <> -1 (пишет сервер при входе персонажа);
  • зависшие сессии отсеиваются по Joy1.dbo.SameUser (счётчик людей на карте, сервер
    обновляет его каждые ≤80 с): игрок засчитывается, если у его карты и канала есть свежая
    строка (карты 10/11 — турнирные, их SameUser учитывает иначе, берутся без сверки);
  • «сервер работает» — по процессам LoginManager + DBManager + хотя бы один GameServer
    (SSH к dev-серверу, только чтение; сокеты игры не трогаем).
  Разбор признаков: Reports/admin_items/research_online_persist.md §1.

Вид (discord.py Components V2): общая панель (одно сообщение, бот правит раз в минуту) и
личный список со страницами и фильтром по классу (эфемерно — видит только нажавший).
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

import discord

ROOT = Path(__file__).parent                       # AstoryAdminCenter/DiscordBot
PORT_ROOT = ROOT.parents[1]                        # папка с клонами AstoryClient / AstoryServer / AstoryAdminCenter
sys.path.insert(0, str(PORT_ROOT / "AstoryServer" / "Tools" / "Anticheat"))   # ★ 25.11 (К-4): db_connect.py — в клоне AstoryServer
import db_connect  # noqa: E402  общий помощник чтения БД (только SELECT, пароль с шары)

MAP_REGISTRY = PORT_ROOT / "AstoryClient" / "Tools" / "data" / "asda_map_registry.json"
SERVER_HOST = "Administrator@@@ASTORY_SERVER_VPN_IP@@"
SSH_EXE = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
SSH_KEY = Path(os.environ.get("USERPROFILE", "")) / ".ssh" / "@@ASTORY_SSH_KEY_NAME@@"
CREATE_NO_WINDOW = 0x08000000                      # бот живёт под pythonw: без консольных окон
TOURNAMENT_MAPS = (10, 11)                         # SameUser не держит их построчно — без сверки
SAMEUSER_FRESH_S = 180                             # строка SameUser старше — карта «мертва»
PANEL_TOP = 10                                     # игроков на общей панели
PAGE_SIZE = 10                                     # игроков на странице личного списка
SHOW_MAP = True                                    # решение владельца 20.10: карта без координат

# Класс — Charinfo.Class: группа, сверено с диапазонами Job мини-статуса оригинала
# (hudRefreshClassAndElementIcons@0xE79850: 0 новичок, 1..7 воин, 12..18 лучник, 23..29 маг).
CLASSES: dict[int, tuple[str, str]] = {
    0: ("Tenderfoot", "🌱"),
    1: ("Warrior", "⚔️"),
    2: ("Archer", "🏹"),
    3: ("Wizard", "🔮"),
}

ONLINE_SQL = """
SELECT c.Charname, c.Lvl, c.Class, p.CPoridx, p.Channel,
       CASE WHEN p.CPoridx IN (10, 11)
              OR EXISTS (SELECT 1 FROM dbo.SameUser s WITH (READUNCOMMITTED)
                         WHERE s.Channel = p.Channel AND s.Poridx = p.CPoridx
                           AND s.JoinCount > 0
                           AND s.Edate > DATEADD(second, -%d, GETDATE()))
            THEN 1 ELSE 0 END AS Live
FROM dbo.CharPos p WITH (READUNCOMMITTED)
JOIN dbo.Charinfo c WITH (READUNCOMMITTED)
  ON c.Userindex = p.Userindex AND c.Charidx = p.Charidx
WHERE p.UserNum <> -1
""" % SAMEUSER_FRESH_S

# PowerShell на сервере: какие процессы игры запущены (имя → количество).
# ★ `exit 0` обязателен: без него отсутствие любого из процессов даёт код 1 ($? = false),
#   и выключенный сервер было бы не отличить от сбоя SSH.
_PROC_PS = ("$ProgressPreference='SilentlyContinue'; "
            "Get-Process LoginManager,DBManager,GameServer -ErrorAction SilentlyContinue "
            "| Group-Object ProcessName | ForEach-Object { '{0}={1}' -f $_.Name, $_.Count }; exit 0")
SQL_TIMEOUT_S = 20                                 # таймаут запроса (connect ограничивает только вход)


@dataclass
class Player:
    """Персонаж в мире."""
    name: str
    level: int
    class_id: int
    map_id: int
    channel: int


@dataclass
class Snapshot:
    """Снимок состояния сервера на момент опроса."""
    server: str                       # "online" | "offline" | "unknown"
    players: list[Player] = field(default_factory=list)
    stale: int = 0                    # отсеянных зависших сессий
    db_ok: bool = True
    at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    error: str = ""                   # для журнала бота, на панель не выводится


# ---------------------------------------------------------------- справочники

_maps_cache: dict[int, str] | None = None


def _pretty_map(raw: str) -> str:
    """Имя карты сервера (MapInfo) → читаемое: подчёркивания, ^…^, слитный CamelCase."""
    s = raw.strip("^").replace("_", " ")
    tournament = s.startswith("t ")
    if tournament:
        s = s[2:]
    s = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", s).strip()
    s = s[:1].upper() + s[1:]
    return f"{s} (Tournament)" if tournament else s


def map_name(map_id: int) -> str:
    """Название карты по номеру из реестра карт порта (имя сервера MapInfo)."""
    global _maps_cache
    if _maps_cache is None:
        # кэш — только после успешного разбора: сбой чтения повторится на следующем вызове
        try:
            reg = json.loads(MAP_REGISTRY.read_text(encoding="utf-8"))
            names = {}
            for m in reg.get("maps", []):
                raw = (m.get("server") or {}).get("mapinfo_name") or m.get("display") or ""
                if raw:
                    names[int(m["id"])] = _pretty_map(raw)
            _maps_cache = names
        except (OSError, ValueError, KeyError):
            return f"Map {map_id}"
    return _maps_cache.get(map_id, f"Map {map_id}")


def class_label(class_id: int) -> str:
    name, icon = CLASSES.get(class_id, (f"Class {class_id}", "❔"))
    return f"{icon} {name}"


# ---------------------------------------------------------------- данные

def check_server() -> str:
    """'online' — LoginManager, DBManager и ≥1 GameServer запущены; 'offline' — нет;
    'unknown' — сервер недоступен по SSH (не знаем)."""
    enc = base64.b64encode(_PROC_PS.encode("utf-16-le")).decode()
    try:
        r = subprocess.run(
            [str(SSH_EXE), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-i", str(SSH_KEY),
             SERVER_HOST, f"powershell -NoProfile -EncodedCommand {enc}"],
            capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if r.returncode != 0:          # скрипт всегда выходит с 0 — ненулевой код = сбой самого ssh
        return "unknown"
    procs = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            procs[k] = int(v) if v.isdigit() else 0
    ok = procs.get("LoginManager", 0) >= 1 and procs.get("DBManager", 0) >= 1 \
        and procs.get("GameServer", 0) >= 1
    return "online" if ok else "offline"


def fetch_snapshot() -> Snapshot:
    """Полный опрос: процессы сервера + список персонажей в мире. Блокирующий — звать из потока."""
    server = check_server()
    if server == "offline":
        return Snapshot(server="offline")
    try:
        cn = db_connect.connect("Joy1")
        cn.timeout = SQL_TIMEOUT_S     # иначе запрос под блокировкой схемы висел бы вечно
        try:
            _, rows = db_connect.query(cn, ONLINE_SQL)
        finally:
            cn.close()
    except Exception as e:  # БД недоступна — панель покажет «данные недоступны»
        return Snapshot(server=server, db_ok=False, error=f"{type(e).__name__}: {e}")
    players, stale = [], 0
    for name, lvl, cls, cpor, chan, live in rows:
        if not live:
            stale += 1
            continue
        players.append(Player(str(name).strip(), int(lvl or 0), int(cls or 0),
                              int(cpor or 0), int(chan or 0)))
    players.sort(key=lambda p: (-p.level, p.name.lower()))
    return Snapshot(server=server, players=players, stale=stale)


# ---------------------------------------------------------------- вид

ACCENT = {"online": 0x2ECC71, "offline": 0xE74C3C, "unknown": 0x95A5A6}
STATUS_LINE = {
    "online": "🟢 **Server online** · Сервер работает · الخادم يعمل · 伺服器運作中",
    "offline": "🔴 **Server offline** · Сервер выключен · الخادم متوقف · 伺服器離線",
    "unknown": "⚠️ **Server status unknown** · Статус сервера неизвестен · حالة الخادم غير معروفة · 伺服器狀態未知",
}


def counter_name(snap: Snapshot, count: int | None = None) -> str:
    """Имя категории-счётчика вверху списка каналов. count — число для показа, если вызывающий
    сглаживает его (по умолчанию — игроки снимка)."""
    if snap.server == "offline":
        return "🔴 Server offline"
    if snap.server != "online" or not snap.db_ok:   # не знаем — зелёным не красим
        return "⚠️ Status unavailable"
    return f"🟢 Online: {len(snap.players) if count is None else count}"


def _player_line(i: int, p: Player) -> str:
    where = f" · {map_name(p.map_id)}" if SHOW_MAP else ""
    return (f"`{i:>2}.` **{discord.utils.escape_markdown(p.name)}** — "
            f"Lv. {p.level} {class_label(p.class_id)}{where}")


def _class_breakdown(players: list[Player]) -> str:
    counts: dict[int, int] = {}
    for p in players:
        counts[p.class_id] = counts.get(p.class_id, 0) + 1
    order = [1, 2, 3, 0] + sorted(k for k in counts if k not in CLASSES)
    parts = [f"{class_label(k)} **{counts[k]}**" for k in order if counts.get(k)]
    return " · ".join(parts)


class LivePanelView(discord.ui.LayoutView):
    """Общая панель #server-status. Кнопка «Все игроки» — постоянная (custom_id)."""

    ALL_PLAYERS_ID = "oracle:live_all"

    def __init__(self, snap: Snapshot | None, peak: int,
                 on_all_players: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=None)
        state = snap.server if snap else "unknown"
        box = discord.ui.Container(accent_colour=ACCENT.get(state, ACCENT["unknown"]))
        box.add_item(discord.ui.TextDisplay("## 🌍 Astory Remake — Live Status"))
        box.add_item(discord.ui.TextDisplay(STATUS_LINE.get(state, STATUS_LINE["unknown"])))

        if snap is not None and snap.server != "offline":
            box.add_item(discord.ui.Separator())
            if not snap.db_ok:
                box.add_item(discord.ui.TextDisplay(
                    "⚠️ Player data unavailable · Данные игроков недоступны · "
                    "بيانات اللاعبين غير متاحة · 玩家資料暫時無法取得"))
            else:
                n = len(snap.players)
                stats = [f"# {n}",
                         "**Players online** · Игроков онлайн · لاعبون متصلون · 在線玩家",
                         f"📈 Peak today · Пик за сегодня · ذروة اليوم · 今日高峰: **{peak}**"]
                breakdown = _class_breakdown(snap.players)
                if breakdown:
                    stats.append(breakdown)
                box.add_item(discord.ui.TextDisplay("\n".join(stats)))
                if snap.players:
                    box.add_item(discord.ui.Separator())
                    top = snap.players[:PANEL_TOP]
                    lines = [_player_line(i, p) for i, p in enumerate(top, 1)]
                    box.add_item(discord.ui.TextDisplay("\n".join(lines)))
                    if n > PANEL_TOP:
                        box.add_item(discord.ui.TextDisplay(
                            f"-# Showing {PANEL_TOP} of {n} · Показаны {PANEL_TOP} из {n}"))

        when = snap.at if snap else dt.datetime.now(dt.timezone.utc)
        box.add_item(discord.ui.TextDisplay(
            f"-# Updated {discord.utils.format_dt(when, 'R')} · every 60 s · "
            f"обновляется каждые 60 с"))

        btn = discord.ui.Button(label="All players / Все игроки", emoji="👥",
                                style=discord.ButtonStyle.secondary,
                                custom_id=self.ALL_PLAYERS_ID)
        btn.callback = on_all_players
        box.add_item(discord.ui.ActionRow(btn))
        self.add_item(box)


class PlayerListView(discord.ui.LayoutView):
    """Личный список (эфемерный): страницы + фильтр по классу. Данные — снимок на момент нажатия."""

    def __init__(self, snap: Snapshot, page: int = 0, class_filter: int | None = None) -> None:
        # эфемерное сообщение можно править 15 мин — держим кнопки живыми почти всё это время
        super().__init__(timeout=840)
        self.snap, self.class_filter = snap, class_filter
        players = [p for p in snap.players if class_filter is None or p.class_id == class_filter]
        pages = max(1, -(-len(players) // PAGE_SIZE))
        self.page = min(max(page, 0), pages - 1)

        box = discord.ui.Container(accent_colour=ACCENT.get(snap.server, ACCENT["unknown"]))
        title = "all classes" if class_filter is None else class_label(class_filter)
        box.add_item(discord.ui.TextDisplay(
            f"## 👥 Online players · Игроки онлайн — {len(players)}\n-# {title}"))
        box.add_item(discord.ui.Separator())
        chunk = players[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]
        if chunk:
            box.add_item(discord.ui.TextDisplay("\n".join(
                _player_line(self.page * PAGE_SIZE + i, p) for i, p in enumerate(chunk, 1))))
        else:
            box.add_item(discord.ui.TextDisplay("Nobody here · Никого нет"))
        box.add_item(discord.ui.TextDisplay(
            f"-# Page {self.page + 1}/{pages} · Страница {self.page + 1}/{pages} · "
            f"data from {discord.utils.format_dt(snap.at, 'T')}"))

        sel = discord.ui.Select(placeholder="Class filter · Фильтр по классу", options=[
            discord.SelectOption(label="All classes / Все классы", value="all",
                                 default=class_filter is None),
            *[discord.SelectOption(label=name, value=str(cid), emoji=icon,
                                   default=class_filter == cid)
              for cid, (name, icon) in sorted(CLASSES.items(), key=lambda kv: (kv[0] == 0, kv[0]))],
        ])
        sel.callback = self._on_filter
        box.add_item(discord.ui.ActionRow(sel))

        prev = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary,
                                 disabled=self.page == 0)
        nxt = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary,
                                disabled=self.page >= pages - 1)
        prev.callback = self._on_prev
        nxt.callback = self._on_next
        box.add_item(discord.ui.ActionRow(prev, nxt))
        self.add_item(box)

    async def _on_filter(self, itx: discord.Interaction) -> None:
        v = itx.data.get("values", ["all"])[0]
        cls = None if v == "all" else int(v)
        await itx.response.edit_message(view=PlayerListView(self.snap, 0, cls))

    async def _on_prev(self, itx: discord.Interaction) -> None:
        await itx.response.edit_message(
            view=PlayerListView(self.snap, self.page - 1, self.class_filter))

    async def _on_next(self, itx: discord.Interaction) -> None:
        await itx.response.edit_message(
            view=PlayerListView(self.snap, self.page + 1, self.class_filter))
