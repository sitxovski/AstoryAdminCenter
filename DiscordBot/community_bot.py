#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""community_bot.py — «Сообщество» админ-центра Astory: копия реестра бота в панель и команды панели боту (шаг А7.6, 24.11.2026; решение
владельца А7 №9 — хозяин реестра заявок и тестеров остаётся бот: state.json и роли сервера Discord; панель читает копию и шлёт боту команды).

КОПИЯ РЕЕСТРА. Раз в SNAP_S и сразу после каждой выполненной команды бот собирает снимок (build_snapshot) и отдаёт его процедурой
  adm.BotSnapPut ТЕМ ЖЕ логином asda_reports, что жалобы и очередь Discord (пароль — reports.env, player_reports.Store). В снимок идут ТОЛЬКО:
    заявки   — id карточки в staff-chat, Discord id и ник подавшего, статус, когда подана, кто и когда решил, на сервере ли он, тестер ли;
    тестеры  — Discord id и ник участников с ролью Beta Tester;
    варны    — Discord id, номер, кто выдал (Discord id), причина, когда;
    баны     — Discord id, ник, причина бана сервера Discord;
    модераторы — ★ р79 М-5: Discord id и ник участников с защищённой ролью или правами модерации (известные боту, community_staff.json);
    сводка   — приём заявок открыт, локдаун, участников на сервере.
  НЕ идут никогда: ответы анкеты (опыт, железо, часовой пояс, мотивация), список поприветствованных, панели, статус-канал, IP (у бота их нет),
  пароли /password и playtest_accounts.txt (этот модуль их не открывает), токены. Самотест сверяет поля снимка со списком SNAP_FIELDS.
КОМАНДЫ. Панель кладёт строку в adm.BotCmd, бот раз в TICK_S забирает её adm.BotCmdClaim и отмечает adm.BotCmdDone своим номером захвата.
Защиты (все — в коде):
  * белый список команд CMDS и ролей ROLES (только Beta Tester) — чего нет в списке, бот не исполняет; произвольной роли нет ни в базе, ни здесь;
  * цель: защищённая роль (PROTECTED из oracle_bot.py, по имени без эмодзи), права модерации (administrator, ban_members, kick_members,
    manage_roles, moderate_members), верхняя роль не ниже роли бота, бот, владелец сервера или сам Oracle — отказ (★ р79 М-5); участника нет на
    сервере — бан по id допустим, кроме id из списка известных модераторов;
  * check (★ р79 В-2) — проверка цели перед баном с блоком учётки: те же условия плюс право бота банить; в Discord ничего не меняется;
  * бан — всегда без удаления сообщений (delete_message_seconds = 0): история участника остаётся; удалить её этим путём нельзя;
  * что команда изменила (★ р79 В-1): итог несёт признак changed и данные отката (роль была / не была, статус заявки до, бан стоял / не стоял,
    снятые варны) — они хранятся в adm.BotCmd; обратная команда восстанавливает ровно сделанное, «ничего не изменила» — откатывать нечего;
  * повтор безопасен (★ р79 М-6): журнал бота community_ledger.json — «выполняется» до Discord, «выполнено» после; намерение («роль была ли»,
    «личное сообщение отправляется») пишется ДО вызова Discord, поэтому после сбоя второе личное сообщение не уходит, а роль ставится повторно
    без вреда; данные отката живут в базе, поэтому вытеснение старых записей журнала откат не ломает;
  * проверочные команды (test и любые с is_test) Discord не трогают вовсе: только отметка «тест»;
  * предел частоты: не больше PER_HOUR исполнений за скользящий час (поверх 30 / час и 200 / сутки базы).
Discord-часть — DiscordAdapter (тонкая обёртка над discord.Guild); всё остальное проверяется подменами (test_community_bot.py) без сети.
Побочных эффектов при импорте нет (discord и pyodbc — лениво, внутри функций).
"""

import asyncio
import datetime as dt
import json
import os
import re
import time
import unicodedata
import uuid
from xml.sax.saxutils import escape

import outbox_bot
import player_reports

TICK_S = 30                      # период цикла
SNAP_S = 300                     # снимок реестра не реже раза в 5 мин
CLAIM_MAX = 3                    # команд за проход
PER_HOUR = 30                    # исполнений за скользящий час (у базы — 30 / час, 200 / сутки)
LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_ledger.json")   # журнал исполнения на ПК
STAFF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_staff.json")     # ★ р79 М-5: известные модераторы
BOT_NAME = "oracle/community_bot 2"                                                                # подпись снимка в adm.BotSnap

# ★ белые списки — ключи те же, что CHECK adm.BotCmd и domains/community.py (самотест панели сверяет)
CMDS = ("app_approve", "app_reject", "app_reopen", "tester_add", "tester_remove", "warns_clear", "warns_restore", "ban", "unban", "test",
        "check")
ROLES = {"beta_tester": "Beta Tester"}          # ключ команды → имя роли на сервере (= oracle_bot.TESTER_ROLE, самотест сверяет)
ROLE_CMDS = ("app_approve", "tester_add", "tester_remove")             # команды с ролью (role_key обязателен)
APP_CMDS = ("app_approve", "app_reject", "app_reopen")                 # команды по заявке (номер карточки обязателен)
APP_STATUSES = ("pending", "approved", "rejected")                     # статусы заявок, которые идут в снимок
MOD_PERMS = ("administrator", "ban_members", "kick_members", "manage_roles", "moderate_members")   # ★ р79 М-5: права модерации цели
# поля снимка: вид → атрибуты XML (и ничего больше — самотест сверяет с тем, что реально уходит и что читает adm.BotSnapPut)
SNAP_FIELDS = {"s": ("apps_open", "lockdown", "members", "note"), "a": ("m", "u", "n", "s", "t", "db", "dt", "g", "bt"),
               "t": ("u", "n"), "w": ("u", "i", "m", "r", "t"), "b": ("u", "n", "r"), "p": ("u", "n", "c")}
APPROVE_DM = ("🎉 Your Astory Remake playtest application was approved! "
              "You now have access to the 🧪 TESTING category.")      # тот же текст, что у кнопки Approve (oracle_bot.DecisionView)
_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")     # символы, недопустимые в XML 1.0


def norm(name):
    """Имя роли → только латиница и цифры в нижнем регистре (как outbox_bot.norm)."""
    kept = "".join(ch for ch in str(name or "") if unicodedata.category(ch)[0] in ("L", "N"))
    return re.sub(r"[^a-z0-9]", "", kept.casefold())


def has_role(info, name):
    """Есть ли у участника роль (по имени без эмодзи и регистра)."""
    return any(norm(r) == norm(name) for r in (info or {}).get("roles") or [])


def iso(v):
    """Время из state.json (ISO с поясом) → «ГГГГ-ММ-ДДTЧЧ:ММ:СС» UTC или None."""
    if not v:
        return None
    try:
        t = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def now_iso():
    """Текущее время UTC в ISO (как пишет сам oracle_bot)."""
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _txt(v, limit):
    """Значение → одна строка без недопустимых в XML символов, не длиннее limit."""
    s = _XML_BAD.sub(" ", str(v if v is not None else "")).replace("\r", " ").replace("\n", " ").strip()
    return s[:limit]


def _int(v):
    """Значение → int или None."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def build_snapshot(data, member_ids, testers, bans, members=None, staff=()):
    """state.json (dict) + сервер → снимок {s, a, t, w, b, p} ТОЛЬКО с полями SNAP_FIELDS. member_ids — Discord id участников сервера, testers —
    [(id, ник)] с ролью Beta Tester, bans — [(id, ник, причина)], staff — [(id, ник[, на сервере 1 / 0])] известных модераторов."""
    tset = {int(u) for u, _n in testers}
    apps = []
    for r in data.get("applications") or []:
        m, u, s = _int(r.get("msg_id")), _int(r.get("uid")), r.get("status")
        if m is None or s not in APP_STATUSES:
            continue
        apps.append({"m": m, "u": u, "n": _txt(r.get("user"), 100), "s": s, "t": iso(r.get("ts")), "db": _txt(r.get("decided_by"), 100) or None,
                     "dt": iso(r.get("decided_ts")), "g": 1 if u in member_ids else 0, "bt": 1 if u in tset else 0})
    seen = {}
    for a in apps:                                   # один ключ — одна строка (повтор msg_id в state.json — последняя запись)
        seen[a["m"]] = a
    warns = []
    for uid, lst in (data.get("warns") or {}).items():
        u = _int(uid)
        if u is None:
            continue
        for i, w in enumerate(lst or []):
            warns.append({"u": u, "i": i + 1, "m": _int((w or {}).get("mod")), "r": _txt((w or {}).get("reason"), 300), "t": iso((w or {}).get("ts"))})
    return {"s": {"apps_open": 1 if data.get("apps_open") else 0, "lockdown": 1 if data.get("lockdown") else 0,
                  "members": members if members is not None else len(member_ids), "note": None},
            "a": list(seen.values()), "t": [{"u": int(u), "n": _txt(n, 100)} for u, n in testers],
            "w": warns, "b": [{"u": int(u), "n": _txt(n, 100), "r": _txt(r, 512) or None} for u, n, r in bans],
            "p": [{"u": int(x[0]), "n": _txt(x[1], 100), "c": (x[2] if len(x) > 2 else None)} for x in staff]}


UNDO_BOOL = ("role_added", "role_removed", "banned", "unbanned")      # признаки данных отката
UNDO_MAX = 190000                                                   # ★ р80 М-6 / р81 М-5: предел данных отката в единицах UTF-16 (база — 200 000, запас)
WARN_REASON_MAX = 6000                                              # ★ р81 М-5: длина причины /warn (предел Discord для опции)
APP_LIST_MAX, WARN_LIST_MAX = 500, 200                              # ★ р80 М-1: пределы списков в данных отката


def undo_shape_error(u):
    """★ р80 М-1: проверка вида данных отката из базы → None (годны) или причина. Признаки — bool, заявки — [[номер, статус]], снятые варны —
    [{mod: int, ts: str, reason: str ≤ WARN_REASON_MAX}] (как пишет /warn)."""
    if not isinstance(u, dict):
        return "не объект"
    if u.get("_too_long"):
        return "данные отката не сохранены — были длиннее предела"
    for k in UNDO_BOOL:
        if k in u and not isinstance(u[k], bool):
            return "%s не да / нет" % k
    for k in ("apps_changed", "apps_restored"):
        v = u.get(k)
        if v is None:
            continue
        if not isinstance(v, list) or len(v) > APP_LIST_MAX:
            return "%s — не список или длиннее %d" % (k, APP_LIST_MAX)
        for x in v:
            ok = (isinstance(x, list) and len(x) == 2 and isinstance(x[0], int) and x[1] in APP_STATUSES) or (k == "apps_restored" and isinstance(x, int))
            if not ok:
                return "%s — неверный элемент" % k
    rm = u.get("removed")
    if rm is not None:
        if not isinstance(rm, list) or len(rm) > WARN_LIST_MAX:
            return "removed — не список или длиннее %d" % WARN_LIST_MAX
        for w in rm:
            if not (isinstance(w, dict) and set(w) <= {"mod", "reason", "ts"} and isinstance(w.get("mod"), int) and isinstance(w.get("ts"), str)
                    and isinstance(w.get("reason"), str) and len(w["reason"]) <= WARN_REASON_MAX):
                return "removed — неверное предупреждение"
    return None


def _attrs(d, keys):
    """Атрибуты XML из d только по списку keys (None пропускается), значения экранированы."""
    out = []
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        out.append('%s="%s"' % (k, escape(str(v), {'"': "&quot;"})))
    return " ".join(out)


def to_xml(snap):
    """Снимок → XML для adm.BotSnapPut (только атрибуты из SNAP_FIELDS)."""
    parts = ["<s %s>" % _attrs(snap["s"], SNAP_FIELDS["s"])]
    for kind in ("a", "t", "w", "b", "p"):
        for row in snap.get(kind) or []:
            parts.append("<%s %s/>" % (kind, _attrs(row, SNAP_FIELDS[kind])))
    parts.append("</s>")
    return "".join(parts)


class AdapterError(Exception):
    """Отказ Discord или проверки адаптера (текст — в итог команды). definite=True — Discord ответил отказом, действие точно НЕ выполнено;
    False — ответа нет (тайм-аут, обрыв), итог неизвестен (★ р80 В-1)."""

    def __init__(self, text, definite=True):
        """text — причина, definite — исход известен."""
        super().__init__(text)
        self.definite = definite


class StaffBook:
    """★ р79 М-5 / ★ р80 М-4: известные модераторы, сохраняются на ПК (community_staff.json: Discord id → {n: ник, seen: когда бот последний раз
    видел у него защищённую роль или права модерации}). Список отражает текущее состояние: при каждом снимке тот, кто на сервере и сейчас без
    защиты и без прав, из списка снимается (разжалованного можно банить); ушедший с сервера модератор остаётся — бан по id ему запрещён.
    Ручная правка (если нужно разрешить бан ушедшего бывшего модератора): остановить бота, удалить его id из community_staff.json, запустить бота
    через ensure_oracle.ps1."""

    def __init__(self, path=STAFF_PATH):
        """Загрузить список (нет файла — пусто; повреждён — исключение: без списка защита по id не работает). Старый вид «id → ник» — читается."""
        self.path, self.data = path, {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                self.data[str(k)] = v if isinstance(v, dict) else {"n": str(v), "seen": None}

    def _save(self):
        """Записать файл атомарно."""
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=0)
            os.replace(tmp, self.path)

    def update(self, staff_now, member_ids):
        """Снимок: staff_now — [(id, ник)] модераторов сейчас, member_ids — все участники сервера. Добавить текущих, снять тех, кто на сервере и
        уже не модератор; ушедших оставить."""
        now = now_iso()
        cur = {str(u): str(n) for u, n in staff_now}
        members = {str(u) for u in member_ids}
        new = {k: {"n": n, "seen": now} for k, n in cur.items()}
        for k, v in self.data.items():
            if k not in cur and k not in members:
                new[k] = v                               # ушёл с сервера — защита по id остаётся
        old, self.data = self.data, new
        if set(new) != set(old) or any(old[k].get("n") != v["n"] for k, v in new.items() if k in old):
            self._save()

    def add(self, pairs):
        """Добавить [(id, ник)] (для тестов и ручного пополнения)."""
        for u, n in pairs:
            self.data[str(u)] = {"n": str(n), "seen": now_iso()}
        self._save()

    def __contains__(self, uid):
        """Есть ли Discord id в списке."""
        return str(uid) in self.data

    def items(self, member_ids=()):
        """[(id, ник, на сервере сейчас)] — для снимка."""
        mem = {str(u) for u in member_ids}
        return [(int(k), v.get("n"), 1 if k in mem else 0) for k, v in self.data.items()]


class Store(outbox_bot.Store):
    """Процедуры adm.BotCmd* / adm.BotSnapPut под логином asda_reports (соединение и секрет — как у жалоб). connect — подставная фабрика."""

    def __init__(self, *a, **kw):
        """Как outbox_bot.Store; свой номер захвата команд."""
        super().__init__(*a, **kw)
        self.cmd_nonce = None

    def cmd_claim(self, n=CLAIM_MAX, test_only=False):
        """Забрать до n команд → [dict]; у отката — ref_changed и ref_undo (что сделала откатываемая команда)."""
        if self.cmd_nonce is None:
            self.cmd_nonce = str(uuid.uuid4())
        rows = self._rows("EXEC adm.BotCmdClaim ?, ?, ?", int(n), self.cmd_nonce, 1 if test_only else 0)
        keys = ("id", "cmd", "target", "role", "app_msg", "ref", "reason", "test", "by", "attempts", "expires_utc", "now_utc", "ref_changed", "ref_undo")
        out = []
        for r in rows:
            d = dict(zip(keys, tuple(r)))
            try:
                d["ref_undo"] = json.loads(d["ref_undo"]) if d.get("ref_undo") else {}
            except ValueError:
                d["ref_undo"] = {}
            out.append(d)
        return out

    def cmd_claimed_ok(self):
        """Проход закончен: следующий захват — с новым номером."""
        self.cmd_nonce = None

    def cmd_done(self, cid, ok, result="", changed=None, undo=None):
        """Итог команды своим номером захвата (★ р79 М-8) → 1 записано, 0 — не моя или уже с итогом."""
        uj = json.dumps(undo, ensure_ascii=False) if undo else None
        if uj is not None and len(uj.encode("utf-16-le")) // 2 > UNDO_MAX:   # ★ р80 М-6 / р81 М-5: длина — как LEN / DATALENGTH базы
            uj = json.dumps({"_too_long": True})
        r = self._rows("EXEC adm.BotCmdDone ?, ?, ?, ?, ?, ?", int(cid), 1 if ok else 0, player_reports.clean_line(result, 400), self.cmd_nonce,
                       None if changed is None else (1 if changed else 0), uj)
        return int(r[0][0])

    def snap_put(self, xml):
        """Отдать снимок реестра → (заявок, тестеров, варнов, банов)."""
        r = self._rows("EXEC adm.BotSnapPut ?, ?", xml, BOT_NAME)
        return tuple(r[0]) if r else None


class DiscordAdapter:
    """Тонкая обёртка над discord.Guild — единственное место, где команды панели касаются Discord."""

    def __init__(self, guild, staff_id, mod_log_id, view_factory=None, protected=(), tester_role="Beta Tester"):
        """guild — сервер, staff_id / mod_log_id — каналы, view_factory — кнопки карточки заявки, protected — PROTECTED из oracle_bot."""
        self.guild, self.staff_id, self.mod_log_id, self.view_factory = guild, staff_id, mod_log_id, view_factory
        self.protected, self.tester_role = tuple(protected), tester_role
        self._m = {}                                 # участники, найденные member_info (fetch_member не кладёт их в кэш гильдии)

    @property
    def me_id(self):
        """Discord id самого бота."""
        return self.guild.me.id

    @property
    def owner_id(self):
        """Discord id владельца сервера."""
        return self.guild.owner_id

    def me_perms(self):
        """★ р79 В-2: права самого бота на сервере, нужные командам."""
        p = self.guild.me.guild_permissions
        return {"ban_members": bool(p.ban_members), "manage_roles": bool(p.manage_roles)}

    def _info(self, m):
        """Участник → {id, name, bot, roles, mod (права модерации), above_bot (верхняя роль не ниже роли бота)}."""
        p = m.guild_permissions
        return {"id": m.id, "name": str(m), "bot": bool(m.bot), "roles": [r.name for r in m.roles],
                "mod": [k for k in MOD_PERMS if getattr(p, k, False)], "above_bot": m.top_role >= self.guild.me.top_role}

    async def member_info(self, uid):
        """Участник по id (кэш или запрос) → _info или None (не на сервере)."""
        import discord
        m = self.guild.get_member(uid)
        if m is None:
            try:
                m = await self.guild.fetch_member(uid)
            except discord.NotFound:
                return None
            except discord.HTTPException as ex:
                raise AdapterError("Discord HTTP %s при поиске участника" % ex.status) from None
        self._m[uid] = m
        return self._info(m)

    def _member(self, uid):
        """Найденный ранее участник (для правки ролей)."""
        m = self._m.get(uid) or self.guild.get_member(uid)
        if m is None:
            raise AdapterError("участника %d нет на сервере Discord" % uid)
        return m

    def role_id(self, name):
        """id роли по имени без эмодзи — ровно одна, иначе отказ."""
        rs = [r.id for r in self.guild.roles if norm(r.name) == norm(name)]
        if len(rs) != 1:
            raise AdapterError("роль «%s»: на сервере Discord найдено %d (нужна ровно одна)" % (name, len(rs)))
        return rs[0]

    async def _call(self, coro, what):
        """Вызов Discord: сбой → AdapterError с понятным текстом."""
        import discord
        try:
            return await coro
        except discord.Forbidden:
            raise AdapterError("Discord: нет прав на «%s»" % what) from None
        except discord.HTTPException as ex:
            raise AdapterError("Discord HTTP %s на «%s»" % (ex.status, what)) from None
        except (OSError, asyncio.TimeoutError) as ex:
            raise AdapterError("сбой связи с Discord (%s) на «%s»" % (type(ex).__name__, what), definite=False) from None

    async def add_role(self, uid, role_id, reason):
        """Выдать роль (повторная выдача той же роли в Discord безвредна)."""
        import discord
        await self._call(self._member(uid).add_roles(discord.Object(id=role_id), reason=reason[:500]), "выдать роль")

    async def remove_role(self, uid, role_id, reason):
        """Снять роль."""
        import discord
        await self._call(self._member(uid).remove_roles(discord.Object(id=role_id), reason=reason[:500]), "снять роль")

    async def edit_card(self, msg_id, mode):
        """Карточка заявки в staff-chat (сообщение этого бота): approved / rejected / removed / reopened → True; нет или чужая → False."""
        import discord
        ch = self.guild.get_channel(self.staff_id)
        if ch is None:
            return False
        try:
            msg = await ch.fetch_message(msg_id)
        except discord.NotFound:
            return False
        except discord.HTTPException as ex:
            raise AdapterError("Discord HTTP %s при чтении карточки" % ex.status) from None
        if msg.author.id != self.me_id or not msg.embeds:
            return False
        e = msg.embeds[0]
        look = {"approved": (discord.Colour.gold(), "🧪 Playtest application — APPROVED", None),
                "rejected": (discord.Colour.dark_grey(), "🧪 Playtest application — rejected", None),
                "removed": (discord.Colour.dark_grey(), "🧪 Playtest application — rejected (removed from testers)", None),
                "reopened": (discord.Colour.green(), "🧪 Playtest application", self.view_factory() if self.view_factory else None)}[mode]
        e.colour, e.title = look[0], look[1]
        await self._call(msg.edit(embed=e, view=look[2]), "исправить карточку заявки")
        return True

    async def dm(self, uid, text):
        """Личное сообщение участнику → True / False (личка закрыта или участника нет)."""
        import discord
        m = self._m.get(uid) or self.guild.get_member(uid)
        if m is None:
            return False
        try:
            await m.send(text)
        except discord.HTTPException:
            return False
        return True

    async def mod_log(self, text):
        """Строка в mod-log без упоминаний (AllowedMentions.none)."""
        import discord
        ch = self.guild.get_channel(self.mod_log_id)
        if ch is None:
            return False
        try:
            await ch.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            return False
        return True

    async def is_banned(self, uid):
        """Стоит ли бан сервера на этом id."""
        import discord
        try:
            await self.guild.fetch_ban(discord.Object(id=uid))
        except discord.NotFound:
            return False
        except discord.HTTPException as ex:
            raise AdapterError("Discord HTTP %s при проверке бана" % ex.status) from None
        return True

    async def ban(self, uid, reason):
        """Бан сервера по id — всегда без удаления сообщений."""
        import discord
        await self._call(self.guild.ban(discord.Object(id=uid), reason=reason[:500], delete_message_seconds=0), "бан")

    async def unban(self, uid, reason):
        """Снять бан сервера по id."""
        import discord
        await self._call(self.guild.unban(discord.Object(id=uid), reason=reason[:500]), "разбан")

    # ---- снимок
    def member_ids(self):
        """Discord id всех участников сервера (кэш гильдии)."""
        return {m.id for m in self.guild.members}

    def member_count(self):
        """Число участников сервера."""
        return self.guild.member_count

    def testers(self):
        """[(id, ник)] участников с ролью Beta Tester (роль ровно одна, иначе пусто)."""
        rid = [r for r in self.guild.roles if norm(r.name) == norm(self.tester_role)]
        if len(rid) != 1:
            return []
        return [(m.id, str(m)) for m in rid[0].members]

    def staff(self):
        """★ р79 М-5: [(id, ник)] участников с защищённой ролью или правами модерации (кроме ботов)."""
        pn = {norm(x) for x in self.protected}
        out = []
        for m in self.guild.members:
            if m.bot:
                continue
            p = m.guild_permissions
            if any(norm(r.name) in pn for r in m.roles) or any(getattr(p, k, False) for k in MOD_PERMS):
                out.append((m.id, str(m)))
        return out

    async def bans(self):
        """[(id, ник, причина)] банов сервера."""
        import discord
        out = []
        try:
            async for b in self.guild.bans(limit=None):
                out.append((b.user.id, str(b.user), b.reason))
        except discord.HTTPException as ex:
            raise AdapterError("Discord HTTP %s при чтении банов" % ex.status) from None
        return out


class Refused(Exception):
    """Бот отказывается исполнять команду (причина — в итог)."""


class Worker:
    """Проход цикла: команды (по белому списку), затем снимок реестра. state — объект состояния бота (data + async save())."""

    def __init__(self, store, state, ledger=None, limiter=None, log=None, mono=time.monotonic, apps_md=None, staff=None):
        """store — Store (или подмена), ledger — outbox_bot.Ledger, staff — StaffBook, apps_md — md-журнал заявок oracle_bot (или None)."""
        self.store, self.state, self.log, self.mono, self.apps_md = store, state, log, mono, apps_md
        self.limiter = limiter or outbox_bot.Limiter(gap=0, per_hour=PER_HOUR, clock=mono)
        self._ledger = ledger
        self._staff = staff
        self.last_snap = None
        self.dirty = True
        self.done = 0

    @property
    def ledger(self):
        """Журнал исполнения на ПК (создаётся при первом обращении)."""
        if self._ledger is None:
            self._ledger = outbox_bot.Ledger(LEDGER_PATH)
        return self._ledger

    @property
    def staff_book(self):
        """Список известных модераторов (создаётся при первом обращении)."""
        if self._staff is None:
            self._staff = StaffBook()
        return self._staff

    def _say(self, text):
        """Строка в журнал бота (oracle_bot.log)."""
        if self.log:
            self.log(text)

    def _led(self, cid, **kw):
        """Дописать поля в запись журнала по номеру команды."""
        cur = dict(self.ledger.get(cid) or {})
        cur.pop("utc", None)
        cur.update(kw)
        self.ledger.put(cid, **cur)

    def check(self, it):
        """Проверка строки до Discord → None или причина."""
        if it["cmd"] not in CMDS:
            return "команда «%s» не из белого списка бота" % it["cmd"]
        if it["cmd"] in ROLE_CMDS and it.get("role") not in ROLES:
            return "роль «%s» не из белого списка бота (можно только Beta Tester)" % it.get("role")
        if it["cmd"] not in ROLE_CMDS and it.get("role"):
            return "у команды «%s» роли быть не может" % it["cmd"]
        if it["cmd"] in APP_CMDS and not it.get("app_msg"):
            return "у команды по заявке нет номера карточки"
        if it["cmd"] in ("app_reopen", "warns_restore") and not it.get("ref"):
            return "у отката нет номера откатываемой команды"
        if len(str(it.get("reason") or "").strip()) < 3:
            return "нет причины"
        return None

    def _reason(self, it):
        """Причина для журнала аудита Discord: номер команды, кто поставил, причина оператора."""
        return "Astory panel #%d (%s): %s" % (it["id"], it.get("by") or "?", player_reports.clean_line(it.get("reason"), 300))

    async def _guard(self, adapter, it, need_member, staff_check=False):
        """Цель команды → info участника или None (не на сервере). Отказ (Refused): бот или владелец сервера, бот-участник, защищённая роль,
        права модерации, верхняя роль не ниже роли бота; не на сервере — id из списка известных модераторов (★ р79 М-5)."""
        uid = int(it["target"])
        if uid in (adapter.me_id, getattr(adapter, "owner_id", None)):
            raise Refused("цель — сам бот или владелец сервера Discord")
        info = await adapter.member_info(uid)
        if info is None:
            if need_member:
                raise Refused("участника %d нет на сервере Discord" % uid)
            if staff_check and uid in self.staff_book:
                raise Refused("участника %d нет на сервере, но он в списке известных модераторов — бот такие команды не исполняет" % uid)
            return None
        if info["bot"]:
            raise Refused("цель — бот")
        pn = {norm(x) for x in adapter.protected}
        prot = sorted(r for r in info["roles"] if norm(r) in pn)     # по имени без эмодзи: «🛡️ Moderator» — тоже защищённая
        if prot:
            raise Refused("у цели защищённая роль (%s) — бот такие команды не исполняет" % ", ".join(prot))
        if info.get("mod"):
            raise Refused("у цели права модерации (%s) — бот такие команды не исполняет" % ", ".join(info["mod"]))
        if info.get("above_bot"):
            raise Refused("верхняя роль цели не ниже роли бота — бот такие команды не исполняет")
        return info

    def _app(self, it):
        """Заявка команды из state.json: карточка есть и подана этим участником, иначе отказ."""
        apps = self.state.data.setdefault("applications", [])
        rec = next((a for a in reversed(apps) if _int(a.get("msg_id")) == int(it["app_msg"])), None)
        if rec is None:
            raise Refused("заявки с карточкой %s в реестре бота нет" % it["app_msg"])
        if _int(rec.get("uid")) != int(it["target"]):
            raise Refused("заявка %s подана другим участником (%s)" % (it["app_msg"], rec.get("uid")))
        return rec

    def _md(self, line):
        """Строка в md-журнал заявок oracle_bot (если он задан)."""
        if not self.apps_md:
            return
        try:
            with open(self.apps_md, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    async def _log(self, adapter, it, text):
        """Строка в mod-log Discord: номер команды, кто поставил, что сделано, причина."""
        await adapter.mod_log("🛠 Astory panel #%d (%s): %s — %s" % (it["id"], it.get("by") or "?", text,
                                                                     player_reports.clean_line(it.get("reason"), 300)))

    def _ref_undo(self, it):
        """★ р80 М-1: данные отката откатываемой команды. Берутся из СВОЕГО журнала (запись «выполнено» по её номеру); база должна с ним
        совпасть, иначе отказ. Журнал уже вытеснил запись — из базы, но только проверенного вида."""
        if not it.get("ref"):
            return {}
        db_undo = it.get("ref_undo") or {}
        own = self.ledger.get(int(it["ref"])) or {}
        if own.get("state") == "done":
            mine = own.get("undo") or {}
            if mine != db_undo:
                raise Refused("данные отката команды №%s в базе не совпадают с журналом бота — откат не исполняется" % it["ref"])
            return mine
        # ★ р81 М-1: из базы — только если запись действительно вытеснена (журнал полон и номер старше самого старого в нём); иначе эту команду
        #   исполнял не бот (итог мог записать чужой процесс под тем же логином)
        keys = [int(k) for k in self.ledger.data] if hasattr(self.ledger, "data") else []
        if not (len(keys) >= outbox_bot.LEDGER_MAX and keys and int(it["ref"]) < min(keys)):
            raise Refused("бот команду №%s не исполнял (в его журнале её нет) — откат не исполняется" % it["ref"])
        why = undo_shape_error(db_undo)
        if why:
            raise Refused("данные отката команды №%s из базы не прошли проверку (%s) — откат не исполняется" % (it["ref"], why))
        return db_undo

    async def _dm_once(self, it, uid, led):
        """★ р79 М-6: личное сообщение не больше одного раза: намерение — в журнал ДО отправки; прерванная отправка повторно не делается."""
        cid = it["id"]
        if led.get("dm") is not None:
            return led["dm"]
        if led.get("dm_pending"):
            self._led(cid, dm=None)
            return None
        self._led(cid, dm_pending=True)
        ok = await self._dm_send(uid)
        self._led(cid, dm=ok)
        return ok

    async def _dm_send(self, uid):
        """Отправить личное сообщение «заявка одобрена» (адаптер задаётся в run_cmd)."""
        return await self._adapter.dm(uid, APPROVE_DM)

    async def run_cmd(self, adapter, it):
        """Исполнить команду → (текст итога, изменила ли что-то, данные отката). Отказ — Refused, сбой Discord — AdapterError."""
        self._adapter = adapter
        cmd, uid, cid = it["cmd"], int(it["target"]), it["id"]
        led = self.ledger.get(cid) or {}
        reason = self._reason(it)
        ref = self._ref_undo(it)
        # ★ р79 М-7 / ★ р80 М-3: снятие тестера и откат снятия не требуют участника на сервере (роль — только если он есть)
        need = cmd == "app_approve" or (cmd == "tester_add" and not it.get("ref")) or (cmd == "tester_remove" and bool(it.get("ref")))
        info = await self._guard(adapter, it, need_member=need, staff_check=cmd in ("ban", "check"))
        data = self.state.data
        tester = ROLES["beta_tester"]
        if cmd == "check":
            perms = adapter.me_perms()
            if not perms.get("ban_members"):
                raise Refused("у бота нет права банить на сервере Discord")
            if info is None:
                return ("проверка прошла: участника нет на сервере, в списке известных модераторов его нет — бан по id возможен", False, None)
            return ("проверка прошла: участник на сервере, защищённых ролей и прав модерации нет, роль бота выше, у бота есть право бана", False, None)
        if cmd == "app_approve":
            rec = self._app(it)
            if rec.get("status") == "approved" and led.get("state") == "sending":
                pass                                   # повтор той же команды: заявка уже одобрена этим номером — доделать остальное
            elif rec.get("status") != "pending":
                raise Refused("заявка уже «%s» — решения нет" % rec.get("status"))
            prev = led.get("prev_status") or rec.get("status")
            rid = adapter.role_id(ROLES[it["role"]])
            # ★ р80 В-1: «роль выдала эта команда» — только если Discord подтвердил выдачу (role_add_done). Иначе состояние читается заново:
            #   роль уже есть (выдал кто-то другой после нашего упавшего вызова) — она не наша, откат её не снимет
            if not led.get("role_add_done"):
                self._led(cid, role_had=has_role(info, tester), prev_status=prev)
                led = self.ledger.get(cid) or {}
            if not has_role(info, tester):
                self._led(cid, role_add_pending=True)
                await adapter.add_role(uid, rid, reason)
                self._led(cid, role_add_done=True, role_had=False)
                led = self.ledger.get(cid) or {}
            card = await adapter.edit_card(int(it["app_msg"]), "approved")
            rec.update(status="approved", decided_by="panel %s" % it.get("by"), decided_ts=now_iso())
            await self.state.save()
            self._md("- %s: %s (%s) -> APPROVED (panel %s)" % (rec["decided_ts"][:16], rec.get("user"), uid, it.get("by")))
            dm = await self._dm_once(it, uid, led)
            await self._log(adapter, it, "заявка %s одобрена, роль Beta Tester — %s" % (it["app_msg"], info["name"]))
            had = bool(led.get("role_had"))
            unk = had and led.get("role_add_pending") and not led.get("role_add_done")   # ★ р81 М-2: прошлая выдача без ответа Discord
            return ("заявка одобрена, роль Beta Tester %s, карточка %s, личное сообщение %s"
                    % ("есть, но выдала ли её эта команда, неизвестно (прошлая попытка без ответа Discord) — откатом не снимается, снять можно "
                       "операцией «Снять роль Beta Tester»" if unk else "уже была" if had else "выдана", "исправлена" if card else "не найдена (статус в реестре записан)",
                       "отправлено" if dm else ("не дошло (личка закрыта)" if dm is False else "итог неизвестен (повторно не отправляется)")),
                    True, {"role_added": not had, "prev_status": prev})
        if cmd == "app_reject":
            rec = self._app(it)
            if rec.get("status") != "pending" and not (rec.get("status") == "rejected" and led.get("state") == "sending"):
                raise Refused("заявка уже «%s» — решения нет" % rec.get("status"))
            card = await adapter.edit_card(int(it["app_msg"]), "rejected")
            rec.update(status="rejected", decided_by="panel %s" % it.get("by"), decided_ts=now_iso())
            await self.state.save()
            self._md("- %s: %s (%s) -> REJECTED (panel %s)" % (rec["decided_ts"][:16], rec.get("user"), uid, it.get("by")))
            await self._log(adapter, it, "заявка %s отклонена" % it["app_msg"])
            return ("заявка отклонена, карточка %s, игроку бот не пишет (как кнопка Reject)" % ("исправлена" if card else "не найдена"),
                    True, {"prev_status": "pending"})
        if cmd == "app_reopen":
            rec = self._app(it)
            if rec.get("status") == "pending":
                return "заявка уже на рассмотрении — менять нечего", False, None
            removed = False
            if ref.get("role_added") and info is not None and has_role(info, tester):
                await adapter.remove_role(uid, adapter.role_id(tester), reason)
                removed = True
            prev = {"status": rec.get("status"), "decided_by": rec.get("decided_by"), "decided_ts": rec.get("decided_ts")}
            rec["status"] = "pending"
            rec.pop("decided_by", None)
            rec.pop("decided_ts", None)
            rec.update(reopened_by="panel %s" % it.get("by"), reopened_ts=now_iso())
            await self.state.save()
            card = await adapter.edit_card(int(it["app_msg"]), "reopened")
            self._md("- %s: %s (%s) -> PENDING again (panel %s, undo #%s)" % (rec["reopened_ts"][:16], rec.get("user"), uid, it.get("by"), it["ref"]))
            await self._log(adapter, it, "заявка %s снова на рассмотрении (откат команды №%s)" % (it["app_msg"], it["ref"]))
            undo = {"prev": prev, "role_removed": removed}
            if removed:
                return ("заявка снова на рассмотрении, кнопки Approve / Reject на карточке %s, роль Beta Tester снята (её выдала откатываемая команда)"
                        % ("вернулись" if card else "не вернулись (карточки нет)"), True, undo)
            return ("заявка снова на рассмотрении, кнопки Approve / Reject на карточке %s" % ("вернулись" if card else "не вернулись (карточки нет)"),
                    True, undo)
        if cmd == "tester_add":
            has = has_role(info, tester)
            restore = bool(it.get("ref"))
            # ★ р79 В-1: откат выдаёт роль, только если её сняла исходная; ★ р80 М-3: участника нет на сервере — роль не выдаётся, заявки — да
            add = info is not None and not has and (not restore or bool(ref.get("role_removed")))
            if add:
                await adapter.add_role(uid, adapter.role_id(tester), reason)
            changed = []
            if restore:                                # откат снятия: вернуть заявкам прежний статус (данные отката — из базы)
                for mid, prev in ref.get("apps_changed") or []:
                    rec = next((a for a in data.get("applications") or [] if _int(a.get("msg_id")) == int(mid)), None)
                    if rec is not None and rec.get("status") == "rejected":
                        rec.update(status=prev, decided_by="panel %s (undo #%s)" % (it.get("by"), it["ref"]), decided_ts=now_iso())
                        await adapter.edit_card(int(mid), "approved" if prev == "approved" else "reopened")
                        changed.append(mid)
                if changed:
                    await self.state.save()
            word = ("выдана" if add else "уже была" if has else "не выдана (участника нет на сервере)" if info is None
                    else "не выдавалась (откатываемая команда её не снимала)")
            await self._log(adapter, it, "роль Beta Tester %s%s — %s" % (word, ", заявкам возвращён статус: %d" % len(changed) if changed else "",
                                                                         (info or {}).get("name") or uid))   # ★ р81 М-4: только сделанное
            undo = {"role_added": add, "apps_restored": changed}
            if changed:
                return "роль Beta Tester %s, заявкам возвращён прежний статус: %d" % (word, len(changed)), True, undo
            return "роль Beta Tester %s" % word, add, undo
        if cmd == "tester_remove":
            has = has_role(info, tester)
            undoing = bool(it.get("ref"))
            rm = has and (not undoing or bool(ref.get("role_added")))         # ★ р79 В-1: откат снимает роль, только если её выдала исходная
            if rm:
                await adapter.remove_role(uid, adapter.role_id(tester), reason)
            changed = []
            if not undoing:                            # как remove_tester.py: одобренные заявки → отклонены (и если участника нет на сервере)
                if led.get("apps_changed") is not None:
                    changed = led["apps_changed"]
                else:
                    plan = [[_int(r.get("msg_id")), "approved"] for r in data.get("applications") or []
                            if _int(r.get("uid")) == uid and r.get("status") == "approved"]
                    self._led(cid, apps_changed=plan)   # ★ р79 М-6: намерение — до правки
                    for mid, _p in plan:
                        rec = next((a for a in data.get("applications") or [] if _int(a.get("msg_id")) == mid), None)
                        rec.update(status="rejected", decided_by="panel %s (removed)" % it.get("by"), decided_ts=now_iso())
                    if plan:
                        await self.state.save()
                    for mid, _p in plan:
                        await adapter.edit_card(mid, "removed")
                    changed = plan
            word = "снята" if rm else ("уже не было" if not has else "не снималась (откатываемая команда её не выдавала)")
            await self._log(adapter, it, "роль Beta Tester %s%s — %s" % (word, ", одобренных заявок отклонено: %d" % len(changed) if changed else "",
                                                                         (info or {}).get("name") or uid))   # ★ р81 М-4: только сделанное
            undo = {"role_removed": rm, "apps_changed": changed}
            if changed:
                return "роль Beta Tester %s, одобренных заявок отклонено: %d" % (word, len(changed)), True, undo
            return "роль Beta Tester %s" % word, rm, undo
        if cmd == "warns_clear":
            if led.get("removed") is not None:
                removed = led["removed"]
            else:
                removed = list((data.setdefault("warns", {})).get(str(uid)) or [])
                self._led(cid, removed=removed)          # ДО очистки: снятые не теряются и при сбое по дороге
            data.setdefault("warns", {})[str(uid)] = []
            await self.state.save()
            await self._log(adapter, it, "снято предупреждений: %d — %d" % (len(removed), uid))
            return "снято предупреждений: %d" % len(removed), bool(removed), {"removed": removed}
        if cmd == "warns_restore":
            removed = ref.get("removed")
            if removed is None:
                raise Refused("в журнале бота нет снятых предупреждений команды №%s — вернуть нечего" % it["ref"])
            if led.get("restored") is not None:
                return "предупреждения уже возвращены этой командой", bool(led["restored"]), {"restored": led["restored"]}
            cur = list((data.setdefault("warns", {})).get(str(uid)) or [])
            keys = {(w.get("mod"), w.get("ts"), w.get("reason")) for w in cur}
            back = [w for w in removed if (w.get("mod"), w.get("ts"), w.get("reason")) not in keys]
            data["warns"][str(uid)] = back + cur
            await self.state.save()
            self._led(cid, restored=len(back))
            await self._log(adapter, it, "возвращено предупреждений: %d — %d (откат команды №%s)" % (len(back), uid, it["ref"]))
            return "возвращено предупреждений: %d (автотаймаут при этом не ставится)" % len(back), bool(back), {"restored": len(back)}
        if cmd == "ban":
            if it.get("ref") and not ref.get("unbanned"):
                return "откатываемая команда бан не снимала — банить нечего", False, {"banned": False}
            if await adapter.is_banned(uid):
                if led.get("ban_done"):                # ★ р80 В-1: бан наш, только если Discord подтвердил его нашей прошлой попыткой
                    return "бан сервера Discord поставлен (сообщения не удалялись)", True, {"banned": True}
                if led.get("ban_pending"):              # ★ р81 М-2: прошлая попытка без ответа Discord — бан мог поставить и бот
                    return ("бан стоит, но поставила ли его эта команда, неизвестно (прошлая попытка без ответа Discord) — откатом не снимается, "
                            "при необходимости снимите бан операцией «Разбан»", False, {"banned": False})
                return "бан уже стоял — повторно не банится, откатывать нечего", False, {"banned": False}
            self._led(cid, ban_pending=True)           # ★ р79 М-6: намерение — до бана
            await adapter.ban(uid, reason)
            self._led(cid, ban_done=True)
            await self._log(adapter, it, "бан сервера Discord без удаления сообщений — %s" % ((info or {}).get("name") or uid))
            if info is None:
                return "бан сервера Discord поставлен (сообщения не удалялись), участника на сервере не было", True, {"banned": True}
            return "бан сервера Discord поставлен (сообщения не удалялись)", True, {"banned": True}
        if cmd == "unban":
            if it.get("ref") and not ref.get("banned"):
                return "откатываемая команда бан не ставила — снимать нечего", False, {"unbanned": False}
            if not await adapter.is_banned(uid):
                if led.get("unban_done"):              # ★ р80 В-1: разбан наш, только если Discord подтвердил его нашей прошлой попыткой
                    return "бан снят: участник может зайти снова по приглашению, роли и онбординг — заново", True, {"unbanned": True}
                if led.get("unban_pending"):            # ★ р81 М-2
                    return ("бана нет, но сняла ли его эта команда, неизвестно (прошлая попытка без ответа Discord) — откатом не ставится, "
                            "при необходимости забаньте операцией «Бан»", False, {"unbanned": False})
                return "бана нет — снимать нечего, откатывать нечего", False, {"unbanned": False}
            self._led(cid, unban_pending=True)
            await adapter.unban(uid, reason)
            self._led(cid, unban_done=True)
            await self._log(adapter, it, "бан сервера Discord снят — %d" % uid)
            return "бан снят: участник может зайти снова по приглашению, роли и онбординг — заново", True, {"unbanned": True}
        raise Refused("команда «%s» не из белого списка бота" % cmd)

    async def _done(self, it, ok, text, changed=None, undo=None):
        """Записать итог в базу (сбой записи — в журнал бота; команда останется «бот взял», повтор безопасен)."""
        try:
            return await asyncio.to_thread(self.store.cmd_done, it["id"], ok, text, changed, undo)
        except Exception as e:
            self._say("команды панели: итог №%d не записан (%s)" % (it["id"], type(e).__name__))
            return 0

    async def one(self, adapter, it):
        """Одна команда: проверочная — только отметка; уже выполненная по журналу — тот же итог; иначе «выполняется» → Discord → «выполнено»."""
        cid = it["id"]
        if it.get("test") or it["cmd"] == "test":
            self._say("команды панели №%d: проверочная — Discord не вызывался" % cid)
            return await self._done(it, True, "тест — бот команду не исполнял, Discord не вызывался")
        led = self.ledger.get(cid) or {}
        if led.get("state") == "done":
            return await self._done(it, True, led.get("result") or "выполнено (журнал бота)", led.get("changed"), led.get("undo"))
        why = self.check(it)
        if why:
            self._led(cid, state="refused", result=why)
            return await self._done(it, False, why)
        self._led(cid, state="sending")              # ★ р79 М-6: «выполняется» — ДО действия в Discord
        self.limiter.mark()
        try:
            text, changed, undo = await self.run_cmd(adapter, it)
        except Refused as e:
            self._led(cid, state="refused", result=str(e))
            self._say("команды панели №%d (%s): отказ — %s" % (cid, it["cmd"], e))
            return await self._done(it, False, str(e))
        except AdapterError as e:
            if getattr(e, "definite", True):           # ★ р80 В-1: Discord ответил отказом — действие не выполнено, намерения снимаются
                cur = dict(self.ledger.get(cid) or {})
                for k in ("ban_pending", "unban_pending", "role_had", "role_add_pending"):
                    cur.pop(k, None)
                cur.pop("utc", None)
                self.ledger.put(cid, **cur)
            self._say("команды панели №%d (%s): %s" % (cid, it["cmd"], e))
            return await self._done(it, False, str(e))
        except Exception as e:
            self._say("команды панели №%d (%s): сбой %s" % (cid, it["cmd"], type(e).__name__))
            return await self._done(it, False, "сбой бота: %s" % type(e).__name__)
        self._led(cid, state="done", result=text, changed=bool(changed), undo=undo)
        self.done += 1
        self.dirty = True
        self._say("команды панели №%d (%s): %s" % (cid, it["cmd"], text))
        return await self._done(it, True, text, bool(changed), undo)

    async def snapshot(self, adapter):
        """Собрать и отдать снимок реестра → (заявок, тестеров, варнов, банов) или None."""
        bans = await adapter.bans()
        mids = adapter.member_ids()
        self.staff_book.update(adapter.staff(), mids)
        snap = build_snapshot(self.state.data, mids, adapter.testers(), bans, adapter.member_count(), self.staff_book.items(mids))
        xml = to_xml(snap)
        res = await asyncio.to_thread(self.store.snap_put, xml)
        self.last_snap, self.dirty = self.mono(), False
        return res

    async def tick(self, adapter):
        """Проход: команды (сколько позволяет предел), затем снимок, если он грязный или старше SNAP_S."""
        if self.limiter.ok():
            try:
                items = await asyncio.to_thread(self.store.cmd_claim, CLAIM_MAX)
            except Exception as e:
                self._say("команды панели: не прочитаны (%s)" % type(e).__name__)
                items = None
            if items is not None:
                for it in items:
                    await self.one(adapter, it)
                self.store.cmd_claimed_ok()
        if self.dirty or self.last_snap is None or self.mono() - self.last_snap >= SNAP_S:
            try:
                await self.snapshot(adapter)
            except Exception as e:
                self.last_snap = self.mono()           # не долбить базу каждые 30 с при сбое: следующий раз через SNAP_S
                self._say("снимок реестра для панели не отдан (%s)" % type(e).__name__)
