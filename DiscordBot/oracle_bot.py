#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""Oracle v2 — демон Discord-сервера Astory Remake Project.

Функционал:
  БАЗА     : инвариант «язык ⇔ User», снятие метки Onboarding Pending.
  ЖИВОСТЬ  : приветствие после онбординга, поздравление бустеров,
             ежедневная сводка по Pending в staff-chat.
  ПЛЕЙТЕСТ : панель заявок в тестеры (модалка → карточка в staff-chat →
             кнопки Approve/Reject), панель баг-репортов (модалка →
             оформленный пост + дубль в файл Reports).
  МОДЕРАЦИЯ: лог удалённых/изменённых сообщений в mod-log,
             /warn /warns /clearwarns с эскалацией (3 варна → таймаут 24ч),
             /lockdown и /unlock.
  ЖАЛОБЫ   : /report — жалоба на игрока (категория, скриншоты, окно формы) → база
             админ-центра (player_reports.py, логин asda_reports — только процедуры);
             ответ оператора из панели — личным сообщением автору (цикл report_reply_loop).

Требует в Dev Portal: Server Members Intent + Message Content Intent.
Запуск: python oracle_bot.py (вотчдог: ensure_oracle.ps1 в планировщике).
"""

import asyncio
import datetime as dt
import json
import logging
import os
import re
import socket
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import bot_daily  # ★ ревизия 67 Н-3: сводка в staff-chat не чаще раза в 23 ч (перезапуск её не публикует)
import live_status
import player_reports  # ★ А6.11 (22.11.2026): жалобы игроков на игроков → база админ-центра (логин asda_reports, только процедуры)
import outbox_bot  # ★ А7.4 (23.11.2026): объявления из панели → Discord (очередь adm.Outbox, тот же логин, только процедуры; белые списки в коде)
import community_bot  # ★ А7.6 (24.11.2026): «Сообщество» — копия реестра (заявки, тестеры, варны, баны) в панель и команды панели (белый список команд, роль только Beta Tester, PROTECTED — отказ)
import botcfg  # ★ 25.11 (публичный клон): прокси только из окружения, ID каналов без падения при незаменённой заглушке
import account_register  # ★ 25.11.2026: /register — настоящая игровая учётка (AsdaStoryOp adm.BotAccountRegister, тот же логин бота, только процедура); пароль для /password — в playtest_accounts.txt
import tg_bot  # ★ А7.5 (23.11.2026): уведомления панели владельцу в Telegram (та же очередь, transport telegram; только sendMessage и getMe; секрет — telegram.env)

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
PROXY = botcfg.proxy("DISCORD_PROXY", "HTTPS_PROXY")   # ★ 25.11 (К-5): не задан / пусто / none — без прокси

LANG_ROLES = ("English", "Русский", "العربية", "中文")
USER_ROLE = "User"
PENDING_ROLE = "Onboarding Pending"
TESTER_ROLE = "Beta Tester"
PROTECTED = ("Oracle", "Head of Development", "Administrator",
             "Community Administrator", "Community Director", "Moderator")

CH = {  # фиксированные ID каналов сервера
    "general": botcfg.discord_id("@@ASTORY_DISCORD_GENERAL@@", "general"),
    "lobby": botcfg.discord_id("@@ASTORY_DISCORD_LOBBY_CH@@", "lobby"),
    "support": botcfg.discord_id("@@ASTORY_DISCORD_SUPPORT_CH@@", "support"),
    "bug_reports": botcfg.discord_id("@@ASTORY_DISCORD_BUG_REPORTS@@", "bug_reports"),   # форум: тестеры создают посты-баги
    "staff_chat": botcfg.discord_id("@@ASTORY_DISCORD_STAFF_CHAT@@", "staff_chat"),
    "mod_log": botcfg.discord_id("@@ASTORY_DISCORD_MOD_LOG@@", "mod_log"),
    "chat_category": botcfg.discord_id("@@ASTORY_DISCORD_CHAT_CATEGORY@@", "chat_category"),
}
BUG_FILE = Path(r"@@ASTORY_DEV_ROOT@@\Reports\discord_bug_reports.md")
STATE_FILE = ROOT / "state.json"
ACCOUNTS_FILE = ROOT / "playtest_accounts.txt"   # учётки для /password: прежние тестовые и созданные командой /register
WARN_TIMEOUT_AT = 3           # варнов до таймаута
WARN_TIMEOUT_HOURS = 24
LOCAL_TZ = dt.datetime.now().astimezone().tzinfo   # для ежедневных задач по местному времени

_handlers: list[logging.Handler] = [logging.FileHandler(ROOT / "oracle_bot.log",
                                                        encoding="utf-8")]
if sys.stderr is not None:  # под pythonw stderr отсутствует
    _handlers.append(logging.StreamHandler())
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", handlers=_handlers)
log = logging.getLogger("oracle")
botcfg.log_unset(log)                              # ★ 25.11 (С-4): незаданные ID каналов — в журнал

_instance_sock: socket.socket | None = None


def acquire_single_instance() -> None:
    """Гарантия одного экземпляра: держим локальный порт; занят — выходим."""
    global _instance_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 47653))
        s.listen(1)
    except OSError:
        raise SystemExit("Oracle уже запущен (порт 47653 занят) — второй экземпляр не нужен")
    _instance_sock = s


# ---------------------------------------------------------------- состояние

class State:
    """Простое персистентное состояние в JSON (welcomed/warns/lockdown/pending)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.data: dict = {"welcomed": [], "warns": {}, "lockdown": None,
                           "pending_yesterday": None, "applications": []}
        if STATE_FILE.exists():
            try:
                self.data.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                log.warning("state.json повреждён, начинаю с чистого")

    async def save(self) -> None:
        async with self._lock:
            STATE_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=1),
                                  encoding="utf-8")


# ---------------------------------------------------------------- модалки/кнопки

class ApplyModal(discord.ui.Modal, title="Closed Playtest Application"):
    """Анкета заявки в тестеры."""

    experience = discord.ui.TextInput(
        label="Did you play Asda Story before? Where?",
        placeholder="e.g. official EU server 2009-2012, private servers…",
        max_length=200)
    hardware = discord.ui.TextInput(
        label="Your PC specs (CPU / GPU / RAM)",
        placeholder="e.g. i5-12400 / RTX 3060 / 16 GB", max_length=150)
    timezone = discord.ui.TextInput(
        label="Timezone & usual play hours",
        placeholder="e.g. UTC+3, evenings 19:00-23:00", max_length=100)
    motivation = discord.ui.TextInput(
        label="Why do you want to join the playtest?",
        style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, bot: "OracleBot") -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, itx: discord.Interaction) -> None:
        e = discord.Embed(title="🧪 Playtest application",
                          colour=discord.Colour.green(),
                          timestamp=dt.datetime.now(dt.timezone.utc))
        e.add_field(name="Applicant", value=f"{itx.user.mention} (`{itx.user}`)", inline=False)
        e.add_field(name="Experience", value=str(self.experience), inline=False)
        e.add_field(name="Hardware", value=str(self.hardware), inline=False)
        e.add_field(name="Timezone / hours", value=str(self.timezone), inline=False)
        e.add_field(name="Motivation", value=str(self.motivation), inline=False)
        e.set_footer(text=f"uid:{itx.user.id}")
        staff = self.bot.channel("staff_chat")
        card = await staff.send(embed=e, view=DecisionView())
        await self.bot.record_application({
            "uid": itx.user.id, "user": str(itx.user), "msg_id": card.id,
            "experience": str(self.experience), "hardware": str(self.hardware),
            "timezone": str(self.timezone), "motivation": str(self.motivation),
            "status": "pending",
            "ts": dt.datetime.now(dt.timezone.utc).isoformat()})
        await itx.response.send_message(
            "✅ Application sent! The team will review it — you'll get the "
            "🧪 Beta Tester role if approved. / Заявка отправлена, при одобрении "
            "получишь роль 🧪 Beta Tester.", ephemeral=True)


class DecisionView(discord.ui.View):
    """Кнопки решения по заявке (persistent)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @staticmethod
    def _uid(itx: discord.Interaction) -> int | None:
        for e in itx.message.embeds:
            if e.footer and e.footer.text and e.footer.text.startswith("uid:"):
                return int(e.footer.text[4:])
        return None

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success,
                       custom_id="oracle:app_approve")
    async def approve(self, itx: discord.Interaction, _b: discord.ui.Button) -> None:
        uid = self._uid(itx)
        member = itx.guild.get_member(uid) or await itx.guild.fetch_member(uid)
        role = discord.utils.get(itx.guild.roles, name=TESTER_ROLE)
        await member.add_roles(role, reason=f"заявка одобрена: {itx.user}")
        e = itx.message.embeds[0]
        e.colour = discord.Colour.gold()
        e.title = "🧪 Playtest application — APPROVED"
        await itx.message.edit(embed=e, view=None)
        await itx.client.set_application_status(itx.message.id, uid, "approved", itx.user)
        await itx.response.send_message(
            f"✅ {member.mention} принят в тестеры • accepted as tester • "
            f"تم قبوله كمختبِر — {itx.user.mention}")
        try:
            await member.send("🎉 Your Astory Remake playtest application was approved! "
                              "You now have access to the 🧪 TESTING category.")
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger,
                       custom_id="oracle:app_reject")
    async def reject(self, itx: discord.Interaction, _b: discord.ui.Button) -> None:
        uid = self._uid(itx)
        e = itx.message.embeds[0]
        e.colour = discord.Colour.dark_grey()
        e.title = "🧪 Playtest application — rejected"
        await itx.message.edit(embed=e, view=None)
        await itx.client.set_application_status(itx.message.id, uid, "rejected", itx.user)
        await itx.response.send_message(
            f"❌ Заявка отклонена • Application rejected • تم رفض الطلب — "
            f"{itx.user.mention}")


class ApplyView(discord.ui.View):
    """Публичная кнопка «подать заявку» (persistent)."""

    def __init__(self, bot: "OracleBot") -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🧪 Apply for Closed Playtest",
                       style=discord.ButtonStyle.primary, custom_id="oracle:apply")
    async def apply(self, itx: discord.Interaction, _b: discord.ui.Button) -> None:
        if not self.bot.state.data.get("apps_open", False):
            await itx.response.send_message(
                "⛔ Applications are closed for now — recruitment will be announced "
                "in 📣┃announcements. / Приём заявок пока закрыт — о наборе объявим "
                "в 📣┃announcements. / التقديم مغلق حالياً — سيُعلن عن التسجيل في "
                "📣┃announcements. / 目前不接受申請 — 正式招募將在 📣┃announcements 公布。",
                ephemeral=True)
            return
        await itx.response.send_modal(ApplyModal(self.bot))


# ★ А6.11 (22.11.2026, решение владельца №6): жалоба на игрока — /report (категория + до 3 скриншотов) → окно формы (ник, когда,
# описание, ссылки) → база админ-центра AsdaAdmin (player_reports.Store: логин asda_reports, только процедуры adm.Report*). Игроку —
# подтверждение с номером только ему (ephemeral); в каналы Discord бот ничего не пишет. Разбор — панель, раздел «Жалобы игроков».
class ReportModal(discord.ui.Modal, title="Report a player / Жалоба на игрока"):
    """Форма жалобы. Категория и скриншоты пришли параметрами команды /report."""

    nick = discord.ui.TextInput(label="Character nickname / Ник персонажа", max_length=player_reports.NICK_MAX)
    when = discord.ui.TextInput(label="When (approx.) / Когда (примерно)", required=False,
                                placeholder="e.g. today ~21:00 UTC+3, map Kordova", max_length=player_reports.WHEN_MAX)
    body = discord.ui.TextInput(label="What happened? / Что случилось?", style=discord.TextStyle.paragraph,
                                min_length=player_reports.BODY_MIN, max_length=player_reports.BODY_MAX)
    links = discord.ui.TextInput(label="Discord links (optional) / Ссылки Discord", required=False,
                                 style=discord.TextStyle.paragraph, max_length=player_reports.LINKS_MAX,
                                 placeholder="message or attachment links, one per line")

    def __init__(self, bot: "OracleBot", category: str, files: list) -> None:
        super().__init__()
        self.bot, self.category, self.files = bot, category, files

    async def on_submit(self, itx: discord.Interaction) -> None:
        f, errs = player_reports.validate(str(self.nick), str(self.when), str(self.body), str(self.links), self.category)
        if errs:
            await itx.response.send_message("❌ " + "\n".join(player_reports.both(e) for e in errs), ephemeral=True)
            return
        wait = self.bot.report_cooldown.left(itx.user.id)
        if wait:
            await itx.response.send_message(f"⏳ Please wait {wait} s / Подожди {wait} с.", ephemeral=True)
            return
        self.bot.report_cooldown.mark(itx.user.id)
        await itx.response.defer(ephemeral=True, thinking=True)
        try:
            code, rid = await asyncio.to_thread(self.bot.reports.submit, itx.user.id, str(itx.user), f)
        except Exception as e:
            self.bot.report_cooldown.last.pop(itx.user.id, None)   # не записана — не считать подачей
            log.error("жалоба от %s (%s) не записана: %s", itx.user, itx.user.id, type(e).__name__)
            await itx.followup.send("⚠️ The report could not be saved right now — please try again later. / "
                                    "Жалобу сейчас не удалось сохранить — попробуй позже.", ephemeral=True)
            return
        if code != 0:
            await itx.followup.send("⛔ " + player_reports.both(player_reports.SUBMIT_TEXT.get(code, ("Refused.", "Отказ.")), id=rid),
                                    ephemeral=True)
            log.info("жалоба от %s (%s) — отказ, код %d", itx.user, itx.user.id, code)
            return
        notes = []
        for a in self.files:
            try:
                data = await a.read()
                fc = await asyncio.to_thread(self.bot.reports.add_file, rid, itx.user.id, a.filename, data)
            except Exception as e:
                log.warning("жалоба №%d: скриншот %s не сохранён: %s", rid, a.filename, type(e).__name__)
                fc = None
            if fc:
                notes.append(f"• {a.filename}: " + player_reports.both(player_reports.FILE_TEXT.get(fc, ("not saved", "не сохранён"))))
            elif fc is None:
                notes.append(f"• {a.filename}: not saved / не сохранён")
        log.info("жалоба №%d от %s (%s): %s на %s, скриншотов %d", rid, itx.user, itx.user.id, f["category"], f["nick"], len(self.files))
        await itx.followup.send(
            f"✅ Report #{rid} received — the team will review it. If they reply, you'll get a direct message from me. / "
            f"Жалоба №{rid} принята — команда её рассмотрит. Если ответят, я пришлю личное сообщение."
            + ("\n" + "\n".join(notes) if notes else ""), ephemeral=True)


# Баг-репорты: форум — тестеры создают посты сами; бот дублирует в файл
# (см. OracleBot.on_thread_create). Старая кнопка-модалка удалена вместе
# с текстовым каналом 17.10.


# ---------------------------------------------------------------- бот

class OracleBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.guild_messages = True
        intents.message_content = True   # привилегированный: лог удалённых сообщений
        super().__init__(intents=intents, proxy=PROXY, max_messages=5000)
        self.tree = app_commands.CommandTree(self)
        self.state = State()
        self.lang_ids: set[int] = set()
        self.user_role: discord.Role | None = None
        self.pending_role: discord.Role | None = None
        self.protected_ids: set[int] = set()
        self._busy: set[int] = set()   # участники, чей reconcile уже идёт (защита от гонок)
        self.live_snap: live_status.Snapshot | None = None   # последний опрос сервера
        self._live_msg: discord.Message | None = None        # сообщение панели #server-status
        self._live_ensured = False                           # каналы статуса проверены в этом процессе
        self._live_ensure_at = 0.0                           # время последней проверки каналов
        self._live_rename: asyncio.Task | None = None        # фоновое переименование счётчика
        self.reports = player_reports.Store()                # ★ А6.11: жалобы → AsdaAdmin (логин asda_reports)
        self.report_cooldown = player_reports.Cooldown()     # ★ А6.11: одна подача в минуту на участника (поверх пределов базы)
        self.accounts = account_register.Store()             # ★ 25.11: /register → AsdaStoryOp adm.BotAccountRegister (логин asda_reports)
        self.register_cooldown = player_reports.Cooldown(seconds=15)   # ★ 25.11: одна попытка /register в 15 с на участника
        self.register_lock = asyncio.Lock()                  # ★ 25.11: регистрации по одной (запись базы и файла учёток — одним шагом)
        self.outbox = outbox_bot.Worker(outbox_bot.Store(), log=log.info)   # ★ А7.4: очередь объявлений панели (журнал бота outbox_ledger.json)
        self.tg = tg_bot.Worker(tg_bot.Store(), log=log.info, proxy=PROXY)  # ★ А7.5: Telegram владельцу (журнал tg_ledger.json; нет telegram.env — молчит)
        self.community = community_bot.Worker(community_bot.Store(), self.state, log=log.info, apps_md=self.APPS_MD)  # ★ А7.6: журнал community_ledger.json

    # ---------- утилиты
    def guild_(self) -> discord.Guild:
        return self.get_guild(GUILD_ID)

    def channel(self, key: str) -> "discord.abc.GuildChannel | None":
        """Канал по ключу CH; ID не задан (0, botcfg.discord_id) или канала нет — None: функция с ним выключена (★ 25.11, С-4)."""
        return self.guild_().get_channel(CH[key]) if CH[key] else None

    async def send_to(self, key: str, *args, **kwargs):
        """Отправить в канал CH[key]; канала нет — предупреждение в журнал, без исключения (★ 25.11, С-4)."""
        ch = self.channel(key)
        if ch is None:
            log.warning("канал «%s» не найден (ID %s) — сообщение не отправлено", key, CH[key])
            return None
        return await ch.send(*args, **kwargs)

    async def setup_hook(self) -> None:
        self.add_view(DecisionView())
        self.add_view(ApplyView(self))
        # кнопка «Все игроки» на панели статуса переживает перезапуск бота
        self.add_view(live_status.LivePanelView(None, 0, self.on_live_all_players))
        # старт здесь, а не в on_ready: сбой любого шага on_ready не должен оставить статус без цикла
        # (before_loop сам ждёт готовности клиента)
        self.live_loop.start()
        self.report_reply_loop.start()     # ★ А6.11: ответы операторов авторам жалоб (только поставленные кнопкой в панели)
        self.outbox_loop.start()           # ★ А7.4: объявления из панели (только поставленные флажком «и в Discord»; пусто — ничего не публикует)
        self.tg_loop.start()               # ★ А7.5: уведомления владельцу в Telegram (Discord не нужен — без ожидания готовности клиента)
        self.community_loop.start()        # ★ А7.6: команды панели «Сообщество» (только поставленные оператором; пусто — ничего не делает) и снимок реестра
        register_commands(self)
        try:
            await self.tree.sync(guild=discord.Object(GUILD_ID))
            log.info("слэш-команды синхронизированы")
        except discord.HTTPException as e:
            log.error("слэш-команды не синхронизировались (%s) — вероятно, бот приглашён "
                      "без scope applications.commands; перепригласи: "
                      "https://discord.com/oauth2/authorize?client_id=%s"
                      "&scope=bot+applications.commands&permissions=8", e.status, self.user.id)

    # ---------- готовность
    async def on_ready(self) -> None:
        guild = self.guild_()
        by_name = {r.name: r for r in guild.roles}
        self.lang_ids = {by_name[n].id for n in LANG_ROLES if n in by_name}
        self.user_role = by_name.get(USER_ROLE)
        self.pending_role = by_name.get(PENDING_ROLE)
        self.protected_ids = {by_name[n].id for n in PROTECTED if n in by_name}
        log.info("готов: %s | языковых: %d", guild.name, len(self.lang_ids))

        if not guild.chunked:
            await guild.chunk()
        added = removed = 0
        for m in guild.members:
            act = await self.reconcile(m, reason="стартовый реконсайл", welcome=False)
            added += act == "add"
            removed += act == "remove"
        log.info("стартовый реконсайл: +%d/-%d", added, removed)
        await self.ensure_panels()
        await self.backfill_applications()
        if not self.daily_report.is_running():
            self.daily_report.start()
        if not self.cleanup_welcomes.is_running():
            self.cleanup_welcomes.start()

    # ---------- live-статус сервера (#server-status + счётчик в списке каналов)
    async def ensure_live_channels(self) -> None:
        """Категория вверху списка с #server-status (только чтение). Счётчик онлайна —
        ИМЯ категории: голосовой канал-счётчик нельзя сделать каналом онбординга по умолчанию
        (Discord требует, чтобы @everyone мог в него зайти), а без этого новички его не видят.
        ID — в state.json; при отсутствии канала создаёт заново."""
        guild = self.guild_()
        live = self.state.data.setdefault("live", {})
        ev = guild.default_role
        ro_text = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=False,
            send_messages_in_threads=False, create_public_threads=False,
            create_private_threads=False, add_reactions=False)
        me = guild.me
        bot_ow = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                             manage_channels=True, connect=True)

        async def get_or_create(key, factory):
            ch = guild.get_channel(live.get(key) or 0)
            if ch is None:
                ch = await factory()
                live[key] = ch.id
                log.info("live-статус: создан %s", ch.name)
            return ch

        cat = await get_or_create("category", lambda: guild.create_category(
            "⚠️ Status unavailable", position=0, overwrites={ev: ro_text, me: bot_ow},
            reason="live-статус сервера"))
        status = await get_or_create("status", lambda: guild.create_text_channel(
            "📊┃server-status", category=cat, position=0,
            topic="Live server status & online players · Статус сервера и онлайн",
            overwrites={ev: ro_text, me: bot_ow}, reason="панель статуса"))
        if status.category_id != cat.id:
            # пересоздали только категорию — без канала внутри она невидима участникам
            await status.edit(category=cat, position=0, reason="live-статус: канал в категорию-счётчик")
            log.info("live-статус: #server-status перенесён в категорию-счётчик")
        # голосовой счётчик первой версии (20.10) — удалить, если остался
        old = guild.get_channel(live.pop("counter", None) or 0)
        if old is not None:
            await old.delete(reason="счётчик перенесён в имя категории")
            log.info("live-статус: удалён голосовой счётчик %s", old.name)
        await self.state.save()

        # новички должны видеть #server-status сразу после онбординга (а с ним — и категорию-счётчик)
        ob = await guild.onboarding()
        ids = set(ob.default_channel_ids)
        if status.id not in ids:
            # по ID, а не из кэша: только что созданного канала в кэше может ещё не быть
            await guild.edit_onboarding(
                default_channels=[discord.Object(id=i) for i in ids | {status.id}],
                reason="live-статус в каналах по умолчанию")
            log.info("live-статус: #server-status добавлен в онбординг")

    @tasks.loop(seconds=60)
    async def live_loop(self) -> None:
        # исключение остановило бы задачу навсегда — ловим здесь, следующий тик через минуту
        try:
            await self._live_tick()
        except Exception:
            log.exception("live-статус: ошибка тика")

    async def _live_tick(self) -> None:
        guild = self.guild_()
        live = self.state.data.setdefault("live", {})
        now = dt.datetime.now(dt.timezone.utc).timestamp()

        # каналы: при первом тике и если их удалили — пересоздать (повтор не чаще раза в 10 мин)
        missing = (guild.get_channel(live.get("status") or 0) is None
                   or guild.get_channel(live.get("category") or 0) is None)
        if (not self._live_ensured or missing) and now - self._live_ensure_at >= 600:
            self._live_ensure_at = now
            try:
                await self.ensure_live_channels()
                self._live_ensured = True
            except discord.HTTPException as e:
                log.error("live-статус: каналы не созданы/не проверены: %s", e)

        try:
            snap = await asyncio.wait_for(asyncio.to_thread(live_status.fetch_snapshot), 120)
        except asyncio.TimeoutError:
            log.warning("live-статус: опрос дольше 120 с — тик пропущен")
            return
        prev = self.live_snap
        self.live_snap = snap
        if prev is None or prev.server != snap.server or prev.db_ok != snap.db_ok:
            log.info("live-статус: сервер %s, БД %s, в мире %d, отсеяно %d %s",
                     snap.server, "ок" if snap.db_ok else "НЕДОСТУПНА",
                     len(snap.players), snap.stale, snap.error)

        dirty = False
        today = dt.datetime.now().astimezone().date().isoformat()   # местная дата с учётом перехода времени
        peak = live.setdefault("peak", {"date": today, "value": 0})
        if peak.get("date") != today:
            peak.update(date=today, value=0)
            dirty = True
        if snap.server == "online" and snap.db_ok and len(snap.players) > peak.get("value", 0):
            peak["value"] = len(snap.players)
            dirty = True

        status = guild.get_channel(live.get("status") or 0)
        if status is not None:
            dirty |= await self._live_update_panel(status, live, snap, peak["value"])

        # счётчик — имя категории. Снижение — только подтверждённое двумя опросами подряд
        # (первый вошедший на пустую карту виден в SameUser лишь через ≤80 с).
        count = None
        if (prev is not None and snap.server == prev.server == "online"
                and snap.db_ok and prev.db_ok):
            count = max(len(snap.players), len(prev.players))
        name = live_status.counter_name(snap, count)
        counter = guild.get_channel(live.get("category") or 0)
        # Discord даёт менять имя не чаще 2 раз за 10 мин: не чаще раза в 5 мин, только при изменении,
        # и отдельной задачей — на 429 библиотека спит до ~10 мин, панель ждать не должна
        if (counter is not None and counter.name != name and now - live.get("renamed_at", 0) >= 300
                and (self._live_rename is None or self._live_rename.done())):
            live["renamed_at"] = now
            dirty = True
            self._live_rename = asyncio.create_task(self._live_rename_counter(counter, name))
        if dirty:
            await self.state.save()

    async def _live_update_panel(self, status: discord.TextChannel, live: dict,
                                 snap: live_status.Snapshot, peak: int) -> bool:
        """Правка панели (или новая, если старой нет). True — изменились ID в state."""
        view = live_status.LivePanelView(snap, peak, self.on_live_all_players)
        no_ping = discord.AllowedMentions.none()   # имя персонажа «@everyone» никого не пингует
        msg = self._live_msg
        if msg is None and live.get("panel_msg"):
            try:
                msg = await status.fetch_message(live["panel_msg"])
            except discord.NotFound:
                msg = None
            except discord.HTTPException as e:
                log.warning("live-статус: панель не прочитана: %s", e)
                return False
        try:
            if msg is None:
                msg = await status.send(view=view, allowed_mentions=no_ping)
                live["panel_msg"] = msg.id
                self._live_msg = msg
                return True
            self._live_msg = await msg.edit(view=view, allowed_mentions=no_ping)
            return False
        except (discord.NotFound, discord.Forbidden) as e:
            # удалена или не правится — на следующем тике поставим новую
            log.warning("live-статус: панель заменяется новой: %s", e)
            self._live_msg = None
            live.pop("panel_msg", None)
            return True
        except discord.HTTPException as e:
            if e.status == 400:              # постоянная ошибка формы — старую не лечить, ставить новую
                log.warning("live-статус: панель заменяется новой (400): %s", e)
                self._live_msg = None
                live.pop("panel_msg", None)
                return True
            log.warning("live-статус: панель не обновлена: %s", e)
            return False

    async def _live_rename_counter(self, counter: discord.abc.GuildChannel, name: str) -> None:
        try:
            await counter.edit(name=name, reason="счётчик онлайна")
        except discord.HTTPException as e:
            log.warning("live-статус: счётчик не переименован: %s", e)

    @live_loop.before_loop
    async def _live_wait(self) -> None:
        await self.wait_until_ready()

    # ---------- ★ А6.11: ответы авторам жалоб (текст оператора из панели, кнопка «Ответить автору»; автоответов нет)
    @tasks.loop(seconds=60)
    async def report_reply_loop(self) -> None:
        # ★ ревизия 67 Н-4: без внешнего тайм-аута (wait_for бросал результат ещё идущего потока — взятые строки терялись); пределы — у входа
        #   (15 с) и запроса (30 с). Сбой захвата — номер захвата сохраняется, следующий тик вернёт те же строки, а не потеряет их
        try:
            items = await asyncio.to_thread(self.reports.claim)
        except Exception as e:                       # база недоступна — следующий тик через минуту, ответы ждут в очереди
            log.warning("жалобы: очередь ответов не прочитана: %s", type(e).__name__)
            return
        for it in items:
            ok, result = False, ""
            try:
                user = self.get_user(it["reporter_id"]) or await self.fetch_user(it["reporter_id"])
                await user.send(player_reports.reply_message(it["report_id"], it["category"], it["target"], it["text"]),
                                allowed_mentions=discord.AllowedMentions.none())
                ok, result = True, "отправлено"
            except discord.Forbidden:
                result = "личные сообщения автора закрыты"
            except discord.NotFound:
                result = "автора нет в Discord"
            except discord.HTTPException as e:
                result = f"Discord HTTP {e.status}"
            except Exception as e:                   # цикл не должен остановиться навсегда из-за одного ответа
                result = f"сбой отправки: {type(e).__name__}"
            try:
                await asyncio.to_thread(self.reports.done, it["id"], ok, result)
            except Exception as e:
                log.warning("жалобы: итог ответа №%d не записан (%s): %s", it["id"], result, type(e).__name__)
            log.info("жалоба №%d: ответ №%d — %s", it["report_id"], it["id"], result)
        self.reports.claimed_ok()                    # ★ ревизия 67 Н-4: строки захвата обработаны — новый номер на следующий захват

    @report_reply_loop.before_loop
    async def _report_wait(self) -> None:
        await self.wait_until_ready()

    # ---------- ★ А7.4: очередь объявлений панели → Discord (outbox_bot.py: белые списки каналов и ролей, без @everyone / @here, срок
    #   годности, один раз по номеру записи — журнал outbox_ledger.json, предел частоты). Публикует ТОЛЬКО то, что оператор поставил в панели.
    @tasks.loop(seconds=outbox_bot.TICK_S)
    async def outbox_loop(self) -> None:
        try:                                         # исключение остановило бы задачу навсегда — следующий проход через TICK_S
            await self.outbox.tick(outbox_bot.DiscordAdapter(self.guild_()))
        except Exception as e:
            log.warning("очередь Discord: проход не выполнен: %s", type(e).__name__)

    @outbox_loop.before_loop
    async def _outbox_wait(self) -> None:
        await self.wait_until_ready()

    # ---------- ★ А7.6: «Сообщество» панели (community_bot.py): команды из adm.BotCmd по белому списку (заявка, роль Beta Tester, варны, бан без
    #   удаления сообщений), цель под PROTECTED — отказ; снимок реестра для панели раз в 5 мин и после каждой команды — только нужные поля
    #   (без анкеты, без поприветствованных, без паролей /password).
    @tasks.loop(seconds=community_bot.TICK_S)
    async def community_loop(self) -> None:
        try:                                         # исключение остановило бы задачу навсегда — следующий проход через TICK_S
            await self.community.tick(community_bot.DiscordAdapter(self.guild_(), CH["staff_chat"], CH["mod_log"], DecisionView,
                                                                   PROTECTED, TESTER_ROLE))
        except Exception as e:
            log.warning("команды панели: проход не выполнен: %s", type(e).__name__)

    @community_loop.before_loop
    async def _community_wait(self) -> None:
        await self.wait_until_ready()

    # ---------- ★ А7.5: очередь панели → Telegram владельцу (tg_bot.py: только sendMessage и getMe, один чат владельца из telegram.env, один раз по
    #   номеру записи — журнал tg_ledger.json, предел частоты, тихие часы без звука; «служба панели не отвечает» — по отметке службы). Апдейты
    #   бота не читаются: этим ботом агенты спрашивают владельца.
    @tasks.loop(seconds=tg_bot.TICK_S)
    async def tg_loop(self) -> None:
        try:                                         # исключение остановило бы задачу навсегда — следующий проход через TICK_S
            await self.tg.tick()
        except Exception as e:
            log.warning("Telegram: проход не выполнен: %s", type(e).__name__)

    async def on_live_all_players(self, itx: discord.Interaction) -> None:
        """Кнопка «Все игроки»: личный список со страницами (видит только нажавший)."""
        snap = self.live_snap
        if snap is None or snap.server == "offline" or not snap.db_ok:
            await itx.response.send_message(
                "⏳ No player data right now · Сейчас нет данных об игроках · "
                "لا توجد بيانات حالياً · 目前沒有玩家資料", ephemeral=True)
            return
        await itx.response.send_message(view=live_status.PlayerListView(snap), ephemeral=True)

    async def ensure_panels(self) -> None:
        """Панели с кнопками: создать, если ещё не стоят."""
        panels = [
            ("support", "oracle:apply", ApplyView(self),
             "## 🧪 Closed Playtest\n"
             "**EN** — Want to test the game before everyone else? Apply below!\n"
             "**RU** — Хочешь попасть в закрытый плейтест? Подай заявку кнопкой ниже!\n"
             "**AR** — تريد تجربة اللعبة قبل الجميع؟ قدّم طلبك بالزر أدناه!\n"
             "**中文** — 想搶先體驗遊戲?點下方按鈕申請!"),
        ]
        panel_ids = self.state.data.setdefault("panels", {})
        for key, cid, view, text in panels:
            ch = self.channel(key)
            if ch is None:                                   # ★ 25.11 (С-4): ID канала не задан — панели в нём нет
                log.warning("панель %s: канал «%s» не найден (ID %s) — пропущена", cid, key, CH[key])
                continue
            # 1) быстрый путь: панель по сохранённому ID (живёт при любом объёме канала)
            saved = panel_ids.get(cid)
            if saved:
                try:
                    await ch.fetch_message(saved)
                    continue
                except discord.NotFound:
                    pass  # панель удалили — переставим
            # 2) поиск по истории (первичная постановка/миграция)
            found = None
            async for m in ch.history(limit=100):
                if m.author == self.user and any(
                        c.custom_id == cid for row in m.components for c in row.children):
                    found = m
                    break
            if found is None:
                found = await ch.send(text, view=view,
                                      allowed_mentions=discord.AllowedMentions.none())
                log.info("панель поставлена в #%s", ch.name)
            panel_ids[cid] = found.id
        await self.state.save()

    # ---------- инвариант ролей + приветствие
    async def reconcile(self, m: discord.Member, *, reason: str,
                        welcome: bool = True) -> str | None:
        if m.bot or self.user_role is None or m.id in self._busy:
            return None
        role_ids = {r.id for r in m.roles}
        if role_ids & self.protected_ids:
            return None
        has_lang = bool(role_ids & self.lang_ids)
        has_user = self.user_role.id in role_ids
        self._busy.add(m.id)
        try:
            if has_lang and self.pending_role is not None and self.pending_role.id in role_ids:
                await m.remove_roles(self.pending_role, reason=f"онбординг пройден ({reason})")
            if has_lang and not has_user:
                await m.add_roles(self.user_role, reason=f"язык выбран ({reason})")
                log.info("+User %s", m)
                if welcome:
                    await self.welcome(m)
                return "add"
            if not has_lang and has_user:
                await m.remove_roles(self.user_role, reason=f"нет языка ({reason})")
                log.info("-User %s", m)
                return "remove"
        except discord.HTTPException as e:
            log.warning("reconcile %s: %s", m, e)
        finally:
            self._busy.discard(m.id)
        return None

    # приветствия по языку участника; приоритет: арабский → 中文 → русский → английский
    WELCOME_TEXTS = {
        "العربية": "👋 أهلاً بك يا {m}! أكملت خطوات الانضمام — الخادم كله صار مفتوحاً لك. "
                   "ألقِ التحية، وتفقّد <id:guide> للتعرف على المكان! 🎮",
        "中文":     "👋 歡迎 {m}!入門設定完成 — 整個伺服器都為你敞開。"
                   "來打個招呼吧,也看看 <id:guide> 認識一下這裡!🎮",
        "Русский":  "👋 Добро пожаловать, {m}! Онбординг пройден — сервер в твоём "
                   "распоряжении. Заходи знакомиться и загляни в <id:guide>! 🎮",
        "English":  "👋 Welcome, {m}! Onboarding complete — the server is yours. "
                   "Say hi, and check <id:guide> to look around! 🎮",
    }
    WELCOME_PRIORITY = ("العربية", "中文", "Русский", "English")

    async def welcome(self, m: discord.Member) -> None:
        """Приветствие в general — один раз, на языке из выбранных участником."""
        if m.id in self.state.data["welcomed"]:
            return
        self.state.data["welcomed"].append(m.id)
        await self.state.save()
        member_roles = {r.name for r in m.roles}
        lang = next((n for n in self.WELCOME_PRIORITY if n in member_roles), "English")
        await self.send_to("general", 
            self.WELCOME_TEXTS[lang].format(m=m.mention),
            allowed_mentions=discord.AllowedMentions(users=[m]))

    # ---------- реестр заявок в плейтест
    APPS_MD = Path('@@ASTORY_DEV_ROOT_FWD@@/Reports/playtest_applications.md')

    async def record_application(self, rec: dict) -> None:
        """Зафиксировать поданную заявку в state.json и md-журнале."""
        self.state.data.setdefault("applications", []).append(rec)
        await self.state.save()
        try:
            self.APPS_MD.parent.mkdir(parents=True, exist_ok=True)
            with self.APPS_MD.open("a", encoding="utf-8") as f:
                nl = "\n"
                f.write(nl + f"## {rec['ts'][:16]} — {rec['user']} ({rec['uid']}) — PENDING" + nl
                        + f"- Опыт: {rec.get('experience', '?')}" + nl
                        + f"- Железо: {rec.get('hardware', '?')}" + nl
                        + f"- Часовой пояс: {rec.get('timezone', '?')}" + nl
                        + f"- Мотивация: {rec.get('motivation', '?')}" + nl)
        except OSError as e:
            log.warning("md-журнал заявок: %s", e)
        log.info("заявка зафиксирована: %s", rec["user"])

    async def set_application_status(self, msg_id: int, uid: int | None, status: str,
                                     mod: discord.abc.User) -> None:
        """Обновить статус заявки (approve/reject) в реестре и журнале."""
        apps = self.state.data.setdefault("applications", [])
        rec = next((a for a in reversed(apps) if a.get("msg_id") == msg_id), None)
        if rec is None:
            rec = next((a for a in reversed(apps)
                        if a.get("uid") == uid and a.get("status") == "pending"), None)
        if rec is None:
            rec = {"uid": uid, "user": str(uid), "msg_id": msg_id, "status": "pending",
                   "ts": dt.datetime.now(dt.timezone.utc).isoformat()}
            apps.append(rec)
        rec["status"] = status
        rec["decided_by"] = str(mod)
        rec["decided_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
        await self.state.save()
        try:
            with self.APPS_MD.open("a", encoding="utf-8") as f:
                f.write(f"- {rec['decided_ts'][:16]}: {rec['user']} ({uid}) -> "
                        f"{status.upper()} ({mod})" + "\n")
        except OSError:
            pass
        log.info("заявка %s -> %s (%s)", rec["user"], status, mod)

    async def backfill_applications(self) -> None:
        """Догнать заявки, поданные/решённые, пока демон не работал (скан staff-chat)."""
        apps = self.state.data.setdefault("applications", [])
        known = {a.get("msg_id") for a in apps}
        added = 0
        staff = self.channel("staff_chat")
        if staff is None:                                    # ★ 25.11 (С-4): ID staff-chat не задан — догонять нечего
            log.warning("бэкфилл заявок: канал staff_chat не найден (ID %s) — пропущен", CH["staff_chat"])
            return
        async for m in staff.history(limit=200):
            if m.author.id != self.user.id or not m.embeds:
                continue
            e = m.embeds[0]
            title = e.title or ""
            if "Playtest application" not in title or m.id in known:
                continue
            uid = None
            if e.footer and e.footer.text and e.footer.text.startswith("uid:"):
                uid = int(e.footer.text[4:])
            fields = {f.name: f.value for f in e.fields}
            status = ("approved" if "APPROVED" in title
                      else "rejected" if "rejected" in title else "pending")
            apps.append({"uid": uid, "user": fields.get("Applicant", "?"), "msg_id": m.id,
                         "experience": fields.get("Experience", "?"),
                         "hardware": fields.get("Hardware", "?"),
                         "timezone": fields.get("Timezone / hours", "?"),
                         "motivation": fields.get("Motivation", "?"),
                         "status": status, "ts": m.created_at.isoformat()})
            added += 1
        if added:
            await self.state.save()
            log.info("бэкфилл заявок: добавлено %d", added)

    # ---------- события
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if {r.id for r in before.roles} != {r.id for r in after.roles}:
            await self.reconcile(after, reason="изменение ролей")
        if before.premium_since is None and after.premium_since is not None:
            await self.send_to("general", 
                f"💎 {after.mention} just **boosted the server** — huge thanks for "
                f"supporting the project! 💜",
                allowed_mentions=discord.AllowedMentions(users=[after]))

    async def on_member_join(self, member: discord.Member) -> None:
        await self.reconcile(member, reason="вход на сервер")

    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Новый пост в форуме баг-репортов → дубль в файловый трекер."""
        if thread.parent_id != CH["bug_reports"]:
            return
        body = ""
        try:
            starter = await thread.fetch_message(thread.id)
            body = starter.content
        except discord.HTTPException:
            pass
        now = dt.datetime.now(dt.timezone.utc)
        try:
            BUG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with BUG_FILE.open("a", encoding="utf-8") as f:
                f.write(f"\n## {now:%Y-%m-%d %H:%M} UTC — {thread.owner} "
                        f"({thread.owner_id}) — {thread.name}\n"
                        f"{body}\n- Discord: {thread.jump_url}\n")
        except OSError as ex:
            log.warning("не записал баг в файл: %s", ex)
        log.info("баг-пост: %s — %s", thread.owner, thread.name)

    async def on_message_delete(self, msg: discord.Message) -> None:
        if msg.author.bot or msg.guild is None or msg.channel.id == CH["mod_log"]:
            return
        e = discord.Embed(title="🗑️ Сообщение удалено", colour=discord.Colour.orange(),
                          timestamp=dt.datetime.now(dt.timezone.utc),
                          description=msg.content[:2000] or "*без текста (вложение?)*")
        e.add_field(name="Автор", value=f"{msg.author.mention} (`{msg.author}`)")
        e.add_field(name="Канал", value=msg.channel.mention)
        if msg.attachments:
            e.add_field(name="Вложения", value="\n".join(a.filename for a in msg.attachments),
                        inline=False)
        await self.send_to("mod_log", embed=e)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or before.guild is None or before.content == after.content:
            return
        e = discord.Embed(title="✏️ Сообщение изменено", colour=discord.Colour.blue(),
                          timestamp=dt.datetime.now(dt.timezone.utc))
        e.add_field(name="Автор", value=f"{before.author.mention}")
        e.add_field(name="Канал", value=before.channel.mention)
        e.add_field(name="Было", value=before.content[:1000] or "-", inline=False)
        e.add_field(name="Стало", value=after.content[:1000] or "-", inline=False)
        e.add_field(name="Ссылка", value=after.jump_url, inline=False)
        await self.send_to("mod_log", embed=e)

    # ---------- ежедневная сводка
    # ★ ревизия 67 Н-3: проверка раз в час, сводка — только если с прошлой прошло ≥ 23 ч (state.json «daily_last_utc», bot_daily.decide);
    #   раньше loop(hours=24) слал сводку сразу при каждом старте бота
    @tasks.loop(minutes=bot_daily.CHECK_MINUTES)
    async def daily_report(self) -> None:
        if self.pending_role is None:
            return
        go, mark = bot_daily.decide(self.state.data.get("daily_last_utc"), dt.datetime.now(dt.timezone.utc))
        if mark is not None:
            self.state.data["daily_last_utc"] = mark
            await self.state.save()
            log.info("сводка: отметки не было — при старте не публикуется, отсчёт с %s", mark)
        if not go:
            return
        now = len(self.pending_role.members)
        prev = self.state.data.get("pending_yesterday")
        d = now - prev if isinstance(prev, int) else None
        delta_ru = f" ({d:+d} за сутки)" if d is not None else ""
        delta_en = f" ({d:+d} today)" if d is not None else ""
        delta_ar = f" ({d:+d} اليوم)" if d is not None else ""
        total = sum(1 for m in self.guild_().members if not m.bot)
        await self.send_to("staff_chat", 
            f"📊 **RU** — Сводка: участников **{total}**, не прошли онбординг "
            f"**{now}**{delta_ru}.\n"
            f"📊 **EN** — Summary: **{total}** members, **{now}** pending "
            f"onboarding{delta_en}.\n"
            f"📊 **AR** — الملخص: **{total}** عضواً، **{now}** لم يكملوا "
            f"الانضمام{delta_ar}.")
        self.state.data["pending_yesterday"] = now
        self.state.data["daily_last_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        await self.state.save()
        log.info("сводка отправлена в staff-chat")

    @daily_report.before_loop
    async def _wait_ready(self) -> None:
        await self.wait_until_ready()

    # ---------- уборка приветствий в general
    async def purge_welcomes(self) -> int:
        """Удалить все приветствия бота (👋) из general; вернуть количество."""
        ch = self.channel("general")
        deleted = 0
        if ch is None:                                       # ★ 25.11 (С-4): ID general не задан
            log.warning("уборка приветствий: канал general не найден (ID %s)", CH["general"])
            return deleted
        async for m in ch.history(limit=500):
            if m.author.id == self.user.id and m.content.startswith("👋"):
                try:
                    await m.delete()
                    deleted += 1
                except discord.HTTPException:
                    pass
        if deleted:
            log.info("уборка приветствий: удалено %d", deleted)
        return deleted

    @tasks.loop(time=dt.time(hour=23, minute=59, tzinfo=LOCAL_TZ))
    async def cleanup_welcomes(self) -> None:
        await self.purge_welcomes()

    @cleanup_welcomes.before_loop
    async def _wait_ready2(self) -> None:
        await self.wait_until_ready()


# ---------------------------------------------------------------- тестовые учётки

_ACCOUNT_LINE = re.compile(
    r"\(@(?P<handle>[^)]+)\)\s*(?:\[(?P<uid>\d+)\])?\s*-\s*(?P<login>[^/\s]+)/(?P<pw>\S+)\s*$")


def find_playtest_account(user: discord.abc.User) -> tuple[str, str] | None:
    """Найти (логин, пароль) участника в ACCOUNTS_FILE. Файл читается при каждом вызове.

    Приоритет — совпадение по Discord ID. По @handle — только для строк без ID:
    иначе занявший освободившийся ник получил бы чужой пароль.
    """
    try:
        lines = ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        log.warning("не прочитать %s: %s", ACCOUNTS_FILE.name, e)
        return None
    by_handle = None
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        m = _ACCOUNT_LINE.search(line)
        if m is None:
            continue
        if m["uid"]:
            if int(m["uid"]) == user.id:
                return m["login"], m["pw"]
        elif by_handle is None and m["handle"].lower() == user.name.lower():
            by_handle = (m["login"], m["pw"])
    return by_handle


# ---------------------------------------------------------------- слэш-команды

def register_commands(bot: OracleBot) -> None:
    g = discord.Object(GUILD_ID)

    # ★ 25.11.2026: регистрация игровой учётки. Параметры слэш-команды видит только сам участник; ответ — ephemeral.
    @bot.tree.command(name="register",
                      description="Create your game account (only you see the reply)", guild=g)
    @app_commands.describe(login="Login: 3-32 chars, Latin letters, digits and _ . @ -",
                           password="Password: 6-50 chars, Latin letters, digits, symbols, no spaces")
    async def register(itx: discord.Interaction, login: str, password: str):
        await itx.response.defer(ephemeral=True, thinking=True)
        lg, pw, errs = account_register.validate(login, password)
        if errs:
            await itx.followup.send("❌ " + "\n".join(account_register.both(e) for e in errs), ephemeral=True)
            return
        try:
            status, acc = account_register.file_status(ACCOUNTS_FILE.read_text(encoding="utf-8"), itx.user.id)
        except OSError as e:
            log.warning("/register: не прочитать %s: %s", ACCOUNTS_FILE.name, e)
            status, acc = None, None
        if status == "banned":
            log.info("/register: %s (%s) — отказ, забанен", itx.user, itx.user.id)
            await itx.followup.send("⛔ " + account_register.both(account_register.BANNED_TEXT), ephemeral=True)
            return
        if status == "have":
            await itx.followup.send("ℹ️ " + account_register.both(account_register.HAVE_TEXT, login=acc[0]), ephemeral=True)
            return
        wait = bot.register_cooldown.left(itx.user.id)
        if wait:
            await itx.followup.send(f"⏳ Please wait {wait} s / Подожди {wait} с.", ephemeral=True)
            return
        bot.register_cooldown.mark(itx.user.id)
        salt, pwhash = account_register.make_secret(pw)
        async with bot.register_lock:
            try:
                code, uid, got = await asyncio.to_thread(bot.accounts.register, itx.user.id, str(itx.user), lg, salt, pwhash)
            except Exception as e:
                log.error("/register: %s (%s) — учётка не создана: %s", itx.user, itx.user.id, type(e).__name__)
                await itx.followup.send("⚠️ The account could not be created right now — please try again later. / "
                                        "Учётку сейчас не удалось создать — попробуй позже.", ephemeral=True)
                return
            if code != 0:
                log.info("/register: %s (%s) — отказ, код %d", itx.user, itx.user.id, code)
                await itx.followup.send("⛔ " + account_register.both(
                    account_register.REGISTER_TEXT.get(code, ("Refused.", "Отказ.")), login=got or lg), ephemeral=True)
                return
            saved = True
            try:
                account_register.append_account(ACCOUNTS_FILE, itx.user.name, itx.user.id, lg, pw)
            except Exception as e:   # учётка уже создана — пароль показываем сейчас, /password его не узнает
                saved = False
                log.error("/register: учётка %s (№%s) создана, но в %s не записана: %s", lg, uid, ACCOUNTS_FILE.name, type(e).__name__)
        log.info("/register: %s (%s) — создана учётка %s (№%s)", itx.user, itx.user.id, lg, uid)
        await itx.followup.send(account_register.success_message(lg, pw, saved), ephemeral=True)

    @bot.tree.command(name="password",
                      description="Your game account login & password (only you see it)",
                      guild=g)
    async def password(itx: discord.Interaction):
        acc = find_playtest_account(itx.user)
        if acc is None:
            log.info("/password: %s (%s) — учётки нет", itx.user, itx.user.id)
            await itx.response.send_message(
                "❌ **EN** — You have no game account yet. Create one: /register LOGIN PASSWORD\n"
                "**RU** — У тебя ещё нет игровой учётки. Создай её: /register ЛОГИН ПАРОЛЬ\n"
                "**AR** — ليس لديك حساب لعبة بعد. أنشئ حسابًا: /register LOGIN PASSWORD\n"
                "**中文** — 你還沒有遊戲帳號。建立帳號：/register LOGIN PASSWORD",
                ephemeral=True)
            return
        login, pw = acc
        log.info("/password: %s (%s) — выдана учётка %s", itx.user, itx.user.id, login)
        await itx.response.send_message(
            "🔐 **Game account / Игровая учётка / حساب اللعبة / 遊戲帳號**\n"
            f"Login: `{login}`\nPassword: `{pw}`\n"
            "-# Only you can see this message. Don't share it. / Видно только тебе — "
            "никому не передавай.",
            ephemeral=True)

    # ★ А6.11: жалоба на игрока — категория и скриншоты параметрами, остальное — в окне формы (ReportModal)
    @bot.tree.command(name="report",
                      description="Report a player to the Astory team (only you see the reply)", guild=g)
    @app_commands.describe(category="What kind of violation", screenshot1="Screenshot (optional)",
                           screenshot2="Screenshot (optional)", screenshot3="Screenshot (optional)")
    @app_commands.choices(category=[app_commands.Choice(name=f"{en} / {ru}", value=k)
                                    for k, (en, ru) in player_reports.CATEGORIES.items()])
    async def report(itx: discord.Interaction, category: app_commands.Choice[str],
                     screenshot1: discord.Attachment | None = None, screenshot2: discord.Attachment | None = None,
                     screenshot3: discord.Attachment | None = None):
        # ★ ревизия 67 С-1: только участник с ролью User (онбординг пройден) и не меньше MIN_MEMBER_DAYS суток на сервере
        member = itx.user if isinstance(itx.user, discord.Member) else None
        why_not = player_reports.may_report(member is not None and bot.user_role is not None and bot.user_role in member.roles,
                                            member.joined_at if member is not None else None)
        if why_not:
            await itx.response.send_message("⛔ " + player_reports.both(why_not), ephemeral=True)
            return
        files = [a for a in (screenshot1, screenshot2, screenshot3) if a is not None]
        for a in files:
            why = player_reports.check_attachment(a.content_type, a.size)
            if why:
                await itx.response.send_message(f"❌ {a.filename}: " + player_reports.both(why), ephemeral=True)
                return
        wait = bot.report_cooldown.left(itx.user.id)
        if wait:
            await itx.response.send_message(f"⏳ Please wait {wait} s / Подожди {wait} с.", ephemeral=True)
            return
        await itx.response.send_modal(ReportModal(bot, category.value, files))

    def warns_of(uid: int) -> list:
        return bot.state.data["warns"].setdefault(str(uid), [])

    @bot.tree.command(name="warn", description="Выдать предупреждение участнику",
                      guild=g)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(member="Кому", reason="За что")
    async def warn(itx: discord.Interaction, member: discord.Member, reason: str):
        if member.bot or {r.id for r in member.roles} & bot.protected_ids:
            await itx.response.send_message("Этого участника варнить нельзя.",
                                            ephemeral=True)
            return
        lst = warns_of(member.id)
        lst.append({"mod": itx.user.id, "reason": reason,
                    "ts": dt.datetime.now(dt.timezone.utc).isoformat()})
        await bot.state.save()
        n = len(lst)
        text = (f"⚠️ {member.mention}, предупреждение **{n}/{WARN_TIMEOUT_AT}**: {reason}")
        if n >= WARN_TIMEOUT_AT:
            await member.timeout(dt.timedelta(hours=WARN_TIMEOUT_HOURS),
                                 reason=f"{WARN_TIMEOUT_AT} предупреждения")
            text += f"\n⏳ Автоматический таймаут на {WARN_TIMEOUT_HOURS} ч."
            bot.state.data["warns"][str(member.id)] = []
            await bot.state.save()
        await itx.response.send_message(text)
        await bot.channel("mod_log").send(
            f"⚠️ warn: {member} ← {itx.user}: {reason} (№{n})")
        try:
            await member.send(f"⚠️ You received a warning on Astory Remake Project: "
                              f"{reason} ({n}/{WARN_TIMEOUT_AT})")
        except discord.HTTPException:
            pass

    @bot.tree.command(name="warns", description="Показать предупреждения участника",
                      guild=g)
    @app_commands.default_permissions(moderate_members=True)
    async def warns(itx: discord.Interaction, member: discord.Member):
        lst = warns_of(member.id)
        if not lst:
            await itx.response.send_message(f"У {member.mention} нет предупреждений.",
                                            ephemeral=True)
            return
        lines = [f"{i+1}. {w['reason']} — <@{w['mod']}> ({w['ts'][:10]})"
                 for i, w in enumerate(lst)]
        await itx.response.send_message(
            f"Предупреждения {member.mention}:\n" + "\n".join(lines), ephemeral=True)

    @bot.tree.command(name="clearwarns", description="Снять все предупреждения", guild=g)
    @app_commands.default_permissions(moderate_members=True)
    async def clearwarns(itx: discord.Interaction, member: discord.Member):
        bot.state.data["warns"][str(member.id)] = []
        await bot.state.save()
        await itx.response.send_message(f"Предупреждения {member.mention} сняты.")
        await bot.channel("mod_log").send(f"♻️ clearwarns: {member} ← {itx.user}")

    @bot.tree.command(name="applications", description="Статус заявок в плейтест",
                      guild=g)
    @app_commands.default_permissions(moderate_members=True)
    async def applications(itx: discord.Interaction):
        apps = bot.state.data.get("applications", [])
        pend = [a for a in apps if a["status"] == "pending"]
        ap = sum(1 for a in apps if a["status"] == "approved")
        rj = sum(1 for a in apps if a["status"] == "rejected")
        nl = "\n"
        lines = nl.join(f"• <@{a['uid']}> — {a['ts'][:16]}" for a in pend[:20]) or "—"
        await itx.response.send_message(
            f"🧪 Заявки: всего **{len(apps)}**, на рассмотрении **{len(pend)}**, "
            f"одобрено **{ap}**, отклонено **{rj}**.{nl}На рассмотрении:{nl}{lines}",
            ephemeral=True)

    @bot.tree.command(name="remind-pending",
                      description="Пинг в lobby тем, кто не прошёл онбординг (EN/RU/AR)",
                      guild=g)
    @app_commands.default_permissions(manage_messages=True)
    async def remind_pending(itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        guild = bot.guild_()
        pending = discord.utils.get(guild.roles, name=PENDING_ROLE)
        if pending is None:
            pending = await guild.create_role(name=PENDING_ROLE, mentionable=False,
                                              reason="метка напоминания об онбординге")
        tagged = 0
        for m in guild.members:
            if m.bot:
                continue
            rids = {r.id for r in m.roles}
            if rids & bot.lang_ids or (bot.user_role and bot.user_role.id in rids):
                continue
            if pending.id not in rids:
                await m.add_roles(pending, reason="напоминание об онбординге")
                tagged += 1
        total = len(pending.members)
        await bot.channel("lobby").send(
            f"📣 {pending.mention} — friendly reminder / напоминание / تذكير!\n\n"
            "**EN** — You haven't finished onboarding, so chat is locked for you. "
            "Open <id:customize>, pick your language — 10 seconds, and everything "
            "unlocks.\n\n"
            "**RU** — Ты ещё не прошёл онбординг, поэтому чат закрыт. Открой "
            "<id:customize>, выбери язык — 10 секунд, и всё откроется.\n\n"
            "**AR** — لم تُكمل خطوات الانضمام بعد، لذا الدردشة مغلقة لديك. افتح "
            "<id:customize> واختر لغتك — ثوانٍ وتنفتح كل القنوات.",
            allowed_mentions=discord.AllowedMentions(roles=[pending]))
        await itx.followup.send(
            f"📣 Отправлено. Помечено новых: **{tagged}**, всего с меткой: **{total}**.",
            ephemeral=True)
        await bot.channel("mod_log").send(
            f"📣 remind-pending: {itx.user} (+{tagged}, всего {total})")

    @bot.tree.command(name="clear-welcomes",
                      description="Удалить приветственные сообщения бота из general",
                      guild=g)
    @app_commands.default_permissions(manage_messages=True)
    async def clear_welcomes(itx: discord.Interaction):
        await itx.response.defer(ephemeral=True)
        n = await bot.purge_welcomes()
        await itx.followup.send(f"🧹 Удалено приветствий: **{n}** • deleted **{n}** • "
                                f"حُذف **{n}**", ephemeral=True)
        await bot.channel("mod_log").send(f"🧹 clear-welcomes: {itx.user} удалил {n}")

    @bot.tree.command(name="playtest-apps",
                      description="Открыть или закрыть приём заявок в плейтест", guild=g)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(mode=[app_commands.Choice(name="open", value="open"),
                                app_commands.Choice(name="close", value="close")])
    async def playtest_apps(itx: discord.Interaction, mode: app_commands.Choice[str]):
        opened = mode.value == "open"
        bot.state.data["apps_open"] = opened
        await bot.state.save()
        pid = bot.state.data.get("panels", {}).get("oracle:apply")
        if pid:
            msg = await bot.channel("support").fetch_message(pid)
            view = ApplyView(bot)
            btn = view.children[0]
            btn.disabled = not opened
            btn.label = ("🧪 Apply for Closed Playtest" if opened
                         else "⛔ Applications closed / Заявки закрыты")
            btn.style = (discord.ButtonStyle.primary if opened
                         else discord.ButtonStyle.secondary)
            await msg.edit(view=view)
        await itx.response.send_message(
            f"🧪 Приём заявок: {'открыт' if opened else 'закрыт'} • "
            f"applications {'open' if opened else 'closed'} • "
            f"{'التقديم مفتوح' if opened else 'التقديم مغلق'}")
        await bot.channel("mod_log").send(
            f"🧪 playtest-apps {mode.value}: {itx.user}")

    @bot.tree.command(name="lockdown",
                      description="Экстренно закрыть письмо во всех чатах (антирейд)",
                      guild=g)
    @app_commands.default_permissions(manage_guild=True)
    async def lockdown(itx: discord.Interaction):
        guild = bot.guild_()
        cat = bot.channel("chat_category")
        await itx.response.defer()
        ow = cat.overwrites
        ev = ow.get(guild.default_role, discord.PermissionOverwrite())
        ev.update(send_messages=False, send_messages_in_threads=False)
        ow[guild.default_role] = ev
        # запретить письмо и ролям-носителям на время локдауна
        for name in (*LANG_ROLES, USER_ROLE):
            r = discord.utils.get(guild.roles, name=name)
            o = ow.get(r, discord.PermissionOverwrite())
            o.update(send_messages=False, send_messages_in_threads=False)
            ow[r] = o
        await cat.edit(overwrites=ow, reason=f"lockdown: {itx.user}")
        for c in cat.channels:
            if isinstance(c, discord.TextChannel):
                await c.edit(sync_permissions=True)
        bot.state.data["lockdown"] = True
        await bot.state.save()
        await itx.followup.send("🔒 **Lockdown**: письмо закрыто во всех чат-каналах. "
                                "Снять: `/unlock`.")
        await bot.channel("mod_log").send(f"🔒 lockdown включил {itx.user}")

    @bot.tree.command(name="unlock", description="Снять локдаун", guild=g)
    @app_commands.default_permissions(manage_guild=True)
    async def unlock(itx: discord.Interaction):
        guild = bot.guild_()
        cat = bot.channel("chat_category")
        await itx.response.defer()
        ow = cat.overwrites
        ow.pop(guild.default_role, None)
        for name in (*LANG_ROLES, USER_ROLE):
            r = discord.utils.get(guild.roles, name=name)
            ow.pop(r, None)
        await cat.edit(overwrites=ow, reason=f"unlock: {itx.user}")
        for c in cat.channels:
            if isinstance(c, discord.TextChannel):
                await c.edit(sync_permissions=True)
        # лобби должно снова писаться @everyone
        lobby = bot.channel("lobby")
        await lobby.edit(overwrites={guild.default_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            add_reactions=True)}, reason="unlock: восстановление lobby")
        bot.state.data["lockdown"] = None
        await bot.state.save()
        await itx.followup.send("🔓 Локдаун снят, чаты снова открыты.")
        await bot.channel("mod_log").send(f"🔓 unlock: {itx.user}")


def _safe_tb(ex: BaseException, secret: str) -> str:
    """★ ревизия 84 М-2 (А7.7): трасса исключения для журнала — токен (если вдруг попал в текст) заменён на «***»."""
    import traceback
    text = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__))
    return text.replace(secret, "***") if secret else text


def run_logged(bot, token: str) -> None:
    """★ ревизия 84 М-2 (А7.7): под pythonw stderr нет — исключение из run() (например, вход в Discord без сети) пишется в oracle_bot.log с
    трассой (без токена), процесс выходит с ненулевым кодом; вотчдог ensure_oracle.ps1 поднимет бота снова."""
    try:
        bot.run(token, log_handler=None)
    except SystemExit:
        raise
    except BaseException as ex:            # noqa: BLE001 — любое завершение с исключением должно попасть в журнал
        log.error("бот завершился исключением %s:\n%s", type(ex).__name__, _safe_tb(ex, token))
        raise SystemExit(1)
    log.info("бот завершил работу (run вернулся)")


if __name__ == "__main__":
    if not TOKEN or "ВСТАВЬ" in TOKEN:
        raise SystemExit("нет токена в .env")
    acquire_single_instance()
    run_logged(OracleBot(), TOKEN)
