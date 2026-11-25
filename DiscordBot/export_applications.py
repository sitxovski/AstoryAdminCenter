#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Выгрузка заявок плейтеста в md-файл с обогащением данными участника.

Для каждой pending-заявки подтягивает с сервера: языковые роли, статусные роли
(Booster/Early Supporter/Translator), дату входа на сервер. Пишет
Reports/playtest_selection_2026-10-17.md (таблица + полные анкеты).
"""

import asyncio
import json
from pathlib import Path

from botctl import connect

OUT = Path(r"@@ASTORY_DEV_ROOT@@\Reports\playtest_selection_2026-10-17.md")
LANGS = ("English", "Русский", "العربية", "中文")
BADGES = ("Server Booster", "Early Supporter", "Translator", "Beta Tester",
          "Moderator", "Administrator", "Community Administrator")


async def main() -> None:
    state = json.loads(Path("state.json").read_text(encoding="utf-8"))
    apps = [a for a in state.get("applications", []) if a.get("status") == "pending"]
    client, guild = await connect()
    try:
        # участники одним пакетным проходом REST
        members: dict[int, dict] = {}
        after = 0
        while True:
            page = await client.http.get_members(guild.id, 1000, after)
            if not page:
                break
            for m in page:
                members[int(m["user"]["id"])] = m
            after = int(page[-1]["user"]["id"])
        roles_by_id = {r.id: r.name for r in await guild.fetch_roles()}

        rows = []
        for a in apps:
            m = members.get(a.get("uid") or 0)
            langs, badges, joined = [], [], "покинул сервер?"
            if m:
                names = [roles_by_id.get(int(r), "?") for r in m.get("roles", [])]
                # имена ролей без эмодзи-префиксов
                clean = [n.split(" ", 1)[-1] if n[:1] in "🛠⚙🛡🧪🌍⭐📢" else n for n in names]
                langs = [l for l in LANGS if l in names or l in clean]
                badges = [b for b in BADGES if b in names or b in clean]
                joined = (m.get("joined_at") or "?")[:10]
            rows.append({**a, "langs": langs, "badges": badges, "joined": joined,
                         "on_server": m is not None})

        rows.sort(key=lambda r: r["ts"])
        nl = "\n"
        out = ["# Заявки на Closed Playtest — срез 2026-10-17",
               "",
               f"Всего pending: **{len(rows)}** (из {len(state.get('applications', []))} "
               f"в реестре; отклонённые не включены). Нужно отобрать **15**.",
               "",
               "| № | Игрок | Подал | На сервере с | Языки | Статусы | Часовой пояс | Железо (кратко) |",
               "|--:|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rows, 1):
            hw = (r.get("hardware") or "?").replace("|", "/")[:40]
            tz = (r.get("timezone") or "?").replace("|", "/")[:30]
            out.append(f"| {i} | {r.get('user','?')} | {r['ts'][:10]} | {r['joined']} | "
                       f"{', '.join(r['langs']) or '—'} | {', '.join(r['badges']) or '—'} | "
                       f"{tz} | {hw} |")
        out += ["", "---", "", "## Полные анкеты", ""]
        for i, r in enumerate(rows, 1):
            out += [f"### {i}. {r.get('user','?')} (uid {r.get('uid')})"
                    + ("" if r["on_server"] else " — ⚠️ ПОКИНУЛ СЕРВЕР"),
                    f"- Подал: {r['ts'][:16]} | на сервере с {r['joined']}",
                    f"- Языки: {', '.join(r['langs']) or '—'} | статусы: {', '.join(r['badges']) or '—'}",
                    f"- Опыт: {r.get('experience','?')}",
                    f"- Железо: {r.get('hardware','?')}",
                    f"- Часовой пояс: {r.get('timezone','?')}",
                    f"- Мотивация: {r.get('motivation','?')}",
                    ""]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(nl.join(out) + nl, encoding="utf-8")
        print("записан:", OUT, "| строк:", len(rows))
        left = [r.get("user") for r in rows if not r["on_server"]]
        if left:
            print("покинули сервер:", left)
    finally:
        await client.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
