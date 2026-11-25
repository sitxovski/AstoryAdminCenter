#!/usr/bin/env python3
# Copyright (c) 2026 @sitxovski (Discord)
"""test_community_bot.py — модульные тесты «Сообщества» бота (А7.6, 24.11.2026; ★ ревизия 79) БЕЗ подключения к Discord и к базе.

Запуск: python -I AstoryAdminCenter/DiscordBot/test_community_bot.py  (код 0 — всё прошло).
Discord подменён: Worker — подставным адаптером (записывает вызовы, ничего не отправляет), DiscordAdapter — подставной гильдией (настоящие классы
discord.py только для Object / Colour / AllowedMentions / исключений — сеть не трогается). Подставная база (FakeStore) отдаёт откату данные
откатываемой команды так же, как adm.BotCmdClaim (ref_changed, ref_undo). Что проверяется: снимок реестра — только поля SNAP_FIELDS; белый
список команд и ролей; цель под защищённой ролью (и с эмодзи), с правами модерации, выше бота, бот, владелец, сам Oracle — отказ; бан по id
вне сервера — отказ только для известных модераторов; проверка цели (check) без действий в Discord; решения по заявке как кнопки и откат;
★ р79 В-1: «ничего не изменила» (бан уже стоял, роли не было) → changed = 0, откат восстанавливает ровно сделанное; ★ М-6: личное сообщение
не повторяется после сбоя; ★ М-7: снятие тестера у ушедшего участника отклоняет заявки; варны и их возврат; разбан; проверочные команды
Discord не трогают; модуль не открывает playtest_accounts.txt; по исходнику oracle_bot.py (ast) — цикл в setup_hook, PROTECTED / TESTER_ROLE.
Связка с настоящими процедурами (LocalDB, adminc_30) — в самотесте tests/selftest_community_a7.py.
"""

import ast
import asyncio
import os
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import community_bot as C  # noqa: E402
import outbox_bot  # noqa: E402

PROT = ("Oracle", "Head of Development", "Administrator", "Community Administrator", "Community Director", "Moderator")   # = oracle_bot.PROTECTED
ME, OWNER = 900, 901                                     # id бота и владельца сервера в подставной гильдии
A, B, S, R, GONE, MODX = 111111111111111111, 222222222222222222, 111111111111111108, 111111111111111109, 111111111111111110, 111111111111111111


class FakeState:
    """Подставное состояние бота (data + save)."""

    def __init__(self, data):
        """data — словарь как state.json."""
        self.data, self.saves = data, 0

    async def save(self):
        """Считает сохранения."""
        self.saves += 1


class FakeStore:
    """Подставная база: очередь команд, итоги (с changed / undo) и снимки; откату отдаёт данные откатываемой команды, как BotCmdClaim."""

    def __init__(self, items=()):
        """items — команды в очереди."""
        self.items, self.done, self.snaps, self.by_id = list(items), [], [], {}

    def cmd_claim(self, n=3, test_only=False):
        """Отдать до n команд, у откатов — ref_changed / ref_undo из итога откатываемой."""
        out, self.items = self.items[:n], self.items[n:]
        for it in out:
            if it.get("ref") and "ref_undo" not in it:
                d = self.by_id.get(it["ref"]) or {}
                it["ref_changed"], it["ref_undo"] = d.get("changed"), d.get("undo") or {}
        return out

    def cmd_claimed_ok(self):
        """Конец прохода."""

    def cmd_done(self, cid, ok, result="", changed=None, undo=None):
        """Запомнить итог."""
        self.done.append((cid, ok, result))
        self.by_id[cid] = {"ok": ok, "changed": changed, "undo": undo}
        return 1

    def snap_put(self, xml):
        """Запомнить снимок."""
        self.snaps.append(xml)
        return (0, 0, 0, 0)


class FakeAdapter:
    """Подставной Discord: участники с ролями и правами, роли, карточки, баны; записывает вызовы."""

    def __init__(self):
        """Участники: alice, bob (тестер), staff (Moderator), robot (бот), modx (права модерации без защищённой роли)."""
        self.me_id, self.owner_id, self.protected, self.tester_role = ME, OWNER, PROT, "Beta Tester"
        self.members = {A: ("alice", ["User"]), B: ("bob", ["User", "Beta Tester"]), S: ("staff", ["Moderator"]), R: ("robot", []),
                        MODX: ("modx", ["Support Lead"])}
        self.bots, self.modperm, self.above = {R}, {MODX: ["ban_members"]}, set()
        self.banned = {111111111111111112}
        self.perms = {"ban_members": True, "manage_roles": True}
        self.calls = []

    def me_perms(self):
        """Права бота."""
        return dict(self.perms)

    async def member_info(self, uid):
        """Как DiscordAdapter.member_info."""
        if uid not in self.members:
            return None
        n, r = self.members[uid]
        return {"id": uid, "name": n, "bot": uid in self.bots, "roles": list(r), "mod": self.modperm.get(uid, []), "above_bot": uid in self.above}

    def role_id(self, name):
        """Только Beta Tester."""
        if name != "Beta Tester":
            raise C.AdapterError("роль %s" % name)
        return 777

    async def add_role(self, uid, rid, reason):
        """Выдать роль (запись вызова)."""
        self.calls.append(("add_role", uid, rid))
        if "Beta Tester" not in self.members[uid][1]:
            self.members[uid][1].append("Beta Tester")

    async def remove_role(self, uid, rid, reason):
        """Снять роль (запись вызова)."""
        self.calls.append(("remove_role", uid, rid))
        self.members[uid] = (self.members[uid][0], [x for x in self.members[uid][1] if "Beta Tester" not in x])

    async def edit_card(self, mid, mode):
        """Карточка (запись вызова)."""
        self.calls.append(("card", mid, mode))
        return True

    async def dm(self, uid, text):
        """Личное сообщение (запись вызова)."""
        self.calls.append(("dm", uid, text))
        return True

    async def mod_log(self, text):
        """mod-log (запись вызова)."""
        self.calls.append(("mod_log", text))
        return True

    async def is_banned(self, uid):
        """Стоит ли бан."""
        return uid in self.banned

    async def ban(self, uid, reason):
        """Бан (запись вызова)."""
        self.calls.append(("ban", uid, reason))
        self.banned.add(uid)

    async def unban(self, uid, reason):
        """Разбан (запись вызова)."""
        self.calls.append(("unban", uid, reason))
        self.banned.discard(uid)

    def member_ids(self):
        """id участников."""
        return set(self.members)

    def member_count(self):
        """Число участников."""
        return len(self.members)

    def testers(self):
        """Тестеры."""
        return [(u, n) for u, (n, r) in self.members.items() if "Beta Tester" in r]

    def staff(self):
        """Модераторы: защищённая роль или права модерации."""
        return [(u, n) for u, (n, r) in self.members.items() if set(r) & set(PROT) or u in self.modperm]

    async def bans(self):
        """Баны."""
        return [(u, "x%d" % u, "spam") for u in sorted(self.banned)]


def data():
    """state.json для тестов (с «секретными» ответами анкеты, которые не должны попасть в снимок)."""
    return {"welcomed": [1, 2, 3], "lockdown": None, "apps_open": True, "pending_yesterday": 3, "panels": {"oracle:apply": 5},
            "live": {"category": 1, "status": 2}, "daily_last_utc": "2026-11-23T19:07:37Z",
            "warns": {str(A): [{"mod": S, "reason": "spam <b>&\"x\"", "ts": "2026-11-20T10:00:00+00:00"}]},
            "applications": [
                {"uid": A, "user": "alice", "msg_id": 1001, "experience": "SECRET-EXP", "hardware": "SECRET-HW",
                 "timezone": "SECRET-TZ", "motivation": "SECRET-MOT", "status": "pending", "ts": "2026-11-20T10:00:00.123+00:00"},
                {"uid": B, "user": "bob", "msg_id": 1002, "experience": "e", "hardware": "h", "timezone": "t", "motivation": "m",
                 "status": "approved", "ts": "2026-11-19T10:00:00+00:00", "decided_by": "sitxovski", "decided_ts": "2026-11-19T11:00:00+00:00"},
                {"uid": S, "user": "staff", "msg_id": 1003, "status": "pending", "ts": "2026-11-19T10:00:00+00:00"},
                {"uid": GONE, "user": "gone", "msg_id": 1004, "status": "approved", "ts": "2026-11-18T10:00:00+00:00"}]}


def cmd(cid, name, target, **kw):
    """Строка команды как из adm.BotCmdClaim."""
    it = {"id": cid, "cmd": name, "target": target, "role": "beta_tester" if name in C.ROLE_CMDS else None, "app_msg": None, "ref": None,
          "reason": "проверка панели", "test": False, "by": "admin1", "attempts": 1}
    it.update(kw)
    return it


class Base(unittest.TestCase):
    """Общая обвязка: состояние, подставные база и Discord, журнал и список модераторов во временной папке."""

    def setUp(self):
        """Свежие подмены на каждый тест."""
        self.tmp = tempfile.TemporaryDirectory()
        self.state = FakeState(data())
        self.ad = FakeAdapter()
        self.store = FakeStore()
        self.w = C.Worker(self.store, self.state, ledger=outbox_bot.Ledger(os.path.join(self.tmp.name, "l.json")),
                          staff=C.StaffBook(os.path.join(self.tmp.name, "staff.json")))

    def tearDown(self):
        """Убрать временную папку."""
        self.tmp.cleanup()

    def run1(self, it):
        """Поставить команду и выполнить один проход → (номер, ok, итог)."""
        self.store.items.append(it)
        asyncio.run(self.w.tick(self.ad))
        return self.store.done[-1]

    def undo_of(self, cid):
        """Данные отката команды cid (что записал бот)."""
        return self.store.by_id[cid]


class SnapshotTest(Base):
    """Снимок реестра."""

    def test_only_needed_fields(self):
        """Только SNAP_FIELDS, анкеты нет, XML экранирован, время UTC."""
        snap = C.build_snapshot(self.state.data, self.ad.member_ids(), self.ad.testers(), [(555, "z", "spam")], 4, [(S, "staff")])
        self.assertEqual(set(snap), {"s", "a", "t", "w", "b", "p"})
        for kind in ("a", "t", "w", "b", "p"):
            for r in snap[kind]:
                self.assertLessEqual(set(r), set(C.SNAP_FIELDS[kind]), kind)
        x = C.to_xml(snap)
        for secret in ("SECRET", "welcomed", "experience", "hardware", "motivation", "timezone", "panels", "live", "daily_last"):
            self.assertNotIn(secret, x)
        root = ET.fromstring(x)
        for el in root:
            self.assertLessEqual(set(el.attrib), set(C.SNAP_FIELDS[el.tag]))
        self.assertEqual(root.find("w").get("r"), 'spam <b>&"x"')
        a = {e.get("m"): e.attrib for e in root.findall("a")}
        self.assertEqual(a["1001"]["t"], "2026-11-20T10:00:00")
        self.assertEqual(a["1002"]["bt"], "1")
        self.assertEqual(root.find("p").get("u"), str(S))

    def test_snapshot_pushed_and_staff_kept(self):
        """Снимок при первом проходе и после выполненной команды; модераторы запоминаются на ПК."""
        asyncio.run(self.w.tick(self.ad))
        self.assertEqual(len(self.store.snaps), 1)
        self.assertIn(S, self.w.staff_book)
        self.assertIn(MODX, self.w.staff_book)
        asyncio.run(self.w.tick(self.ad))
        self.assertEqual(len(self.store.snaps), 1)
        self.run1(cmd(1, "warns_clear", A))
        self.assertEqual(len(self.store.snaps), 2)

    def test_no_password_files(self):
        """Модуль не трогает пароли плейтеста."""
        with open(os.path.join(HERE, "community_bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("playtest_accounts", src.replace("playtest_accounts.txt (этот модуль их не открывает)", ""))
        self.assertNotIn("ACCOUNTS_FILE", src)


class GuardTest(Base):
    """Белый список и защита цели."""

    def test_whitelist(self):
        """Команда и роль не из списка — отказ без Discord."""
        self.assertEqual(self.w.check(cmd(1, "kick", 1)), "команда «kick» не из белого списка бота")
        self.assertIn("Beta Tester", self.w.check(cmd(1, "tester_add", 1, role="admin")))
        self.assertIn("роли быть не может", self.w.check(cmd(1, "ban", 1, role="beta_tester")))
        self.assertEqual(C.ROLES, {"beta_tester": "Beta Tester"})
        r = self.run1(cmd(2, "role_grant", A))
        self.assertFalse(r[1])
        self.assertFalse([c for c in self.ad.calls if c[0] != "mod_log"])

    def test_protected_mod_above_bot_owner_self(self):
        """Защищённая роль, права модерации, выше бота, бот, владелец, сам Oracle — отказ, бана нет."""
        self.ad.members[B] = ("bob", ["User"])
        self.ad.above.add(B)
        for i, t in enumerate((S, R, OWNER, ME, MODX, B)):
            r = self.run1(cmd(10 + i, "ban", t))
            self.assertFalse(r[1], t)
        texts = [d[2] for d in self.store.done]
        self.assertIn("защищённая роль (Moderator)", texts[0])
        self.assertIn("права модерации (ban_members)", texts[4])
        self.assertIn("не ниже роли бота", texts[5])
        self.assertFalse([c for c in self.ad.calls if c[0] == "ban"])

    def test_emoji_role_names(self):
        """«🛡️ Moderator» — защищена, «🧪 Beta Tester» — снимается."""
        self.ad.members[S] = ("staff", ["🛡️ Moderator"])
        self.ad.members[B] = ("bob", ["User", "🧪 Beta Tester"])
        self.assertFalse(self.run1(cmd(1, "ban", S))[1])
        r2 = self.run1(cmd(2, "tester_remove", B))
        self.assertTrue(r2[1], r2)
        self.assertIn("снята", r2[2])

    def test_ban_by_id_outside_server(self):
        """Не на сервере: обычный id — бан по id; известный модератор (ушёл с сервера) — отказ."""
        asyncio.run(self.w.tick(self.ad))                 # снимок: S запомнен как модератор
        del self.ad.members[S]
        r1 = self.run1(cmd(1, "ban", S))
        self.assertFalse(r1[1])
        self.assertIn("известных модераторов", r1[2])
        r2 = self.run1(cmd(2, "ban", 111111111111111113))
        self.assertTrue(r2[1], r2)

    def test_check_command(self):
        """check: ничего не делает в Discord; без права бана у бота — не прошла; модератор — не прошла."""
        r = self.run1(cmd(1, "check", A))
        self.assertTrue(r[1], r)
        self.assertIn("проверка прошла", r[2])
        self.assertEqual(self.undo_of(1)["changed"], False)
        self.assertFalse(self.run1(cmd(2, "check", S))[1])
        self.ad.perms["ban_members"] = False
        r3 = self.run1(cmd(3, "check", A))
        self.assertFalse(r3[1])
        self.assertIn("нет права банить", r3[2])
        self.assertFalse([c for c in self.ad.calls if c[0] != "mod_log"])
        self.assertFalse([c for c in self.ad.calls if c[0] == "mod_log"])

    def test_test_commands_do_nothing(self):
        """Проверочные — только отметка «тест»."""
        r1 = self.run1(cmd(1, "test", 0, test=True))
        r2 = self.run1(cmd(2, "ban", A, test=True))
        self.assertTrue(r1[1] and r2[1])
        self.assertEqual(self.ad.calls, [])
        self.assertIn("Discord не вызывался", r2[2])


class CommandsTest(Base):
    """Исполнение и откат."""

    def test_approve_and_reopen(self):
        """Одобрение как кнопка Approve; повтор без второго сообщения; откат возвращает заявку и снимает выданную роль."""
        r = self.run1(cmd(1, "app_approve", A, app_msg=1001))
        self.assertTrue(r[1], r)
        rec = self.state.data["applications"][0]
        self.assertEqual((rec["status"], rec["decided_by"]), ("approved", "panel admin1"))
        self.assertEqual([c[0] for c in self.ad.calls], ["add_role", "card", "dm", "mod_log"])
        self.assertEqual(self.undo_of(1)["undo"], {"role_added": True, "prev_status": "pending"})
        self.w.ledger.put(1, **dict({k: v for k, v in self.w.ledger.get(1).items() if k != "utc"}, state="sending"))
        n = len(self.ad.calls)
        r2 = self.run1(cmd(1, "app_approve", A, app_msg=1001, attempts=2))
        self.assertTrue(r2[1], r2)
        self.assertFalse([c for c in self.ad.calls[n:] if c[0] == "dm"])
        self.assertEqual(self.undo_of(1)["undo"]["role_added"], True)       # ★ М-6: после повтора «роль выдала эта команда» не теряется
        self.assertFalse(self.run1(cmd(3, "app_reject", A, app_msg=1001))[1])
        r4 = self.run1(cmd(4, "app_reopen", A, app_msg=1001, ref=1))
        self.assertTrue(r4[1], r4)
        self.assertEqual(rec["status"], "pending")
        self.assertIn(("remove_role", A, 777), self.ad.calls)
        self.assertIn(("card", 1001, "reopened"), self.ad.calls)

    def test_dm_not_repeated_after_crash(self):
        """★ М-6: бот упал между отправкой и отметкой — после повтора второго личного сообщения нет, итог «неизвестен»."""
        self.w.ledger.put(5, state="sending", role_had=False, prev_status="pending", dm_pending=True)
        r = self.run1(cmd(5, "app_approve", A, app_msg=1001, attempts=2))
        self.assertTrue(r[1], r)
        self.assertFalse([c for c in self.ad.calls if c[0] == "dm"])
        self.assertIn("итог неизвестен", r[2])
        self.assertEqual(self.undo_of(5)["undo"]["role_added"], True)

    def test_app_wrong_owner(self):
        """Заявку подал другой — отказ."""
        r = self.run1(cmd(1, "app_reject", A, app_msg=1002))
        self.assertFalse(r[1])
        self.assertIn("другим участником", r[2])

    def test_tester_remove_and_undo(self):
        """Снятие как remove_tester.py и откат: роль и статусы назад."""
        r = self.run1(cmd(1, "tester_remove", B))
        self.assertTrue(r[1], r)
        rec = self.state.data["applications"][1]
        self.assertEqual(rec["status"], "rejected")
        self.assertIn(("card", 1002, "removed"), self.ad.calls)
        r2 = self.run1(cmd(2, "tester_add", B, ref=1))
        self.assertTrue(r2[1], r2)
        self.assertEqual(rec["status"], "approved")
        self.assertIn("Beta Tester", self.ad.members[B][1])

    def test_noop_tester_remove_undo_does_not_give_role(self):
        """★ В-1: снятие роли у участника без роли (и без одобренных заявок) — changed = 0, откат роль НЕ выдаёт."""
        r = self.run1(cmd(1, "tester_remove", A))
        self.assertTrue(r[1])
        self.assertIn("уже не было", r[2])
        self.assertIs(self.undo_of(1)["changed"], False)
        r2 = self.run1(cmd(2, "tester_add", A, ref=1))
        self.assertNotIn("Beta Tester", self.ad.members[A][1])
        self.assertFalse([c for c in self.ad.calls if c[0] == "add_role"])
        self.assertIn("не выдавалась", r2[2])

    def test_noop_tester_add_undo_does_not_remove(self):
        """★ В-1: выдача роли, которая уже была, — changed = 0, откат роль не снимает."""
        r = self.run1(cmd(1, "tester_add", B))
        self.assertIs(self.undo_of(1)["changed"], False)
        self.assertIn("уже была", r[2])
        self.run1(cmd(2, "tester_remove", B, ref=1))
        self.assertIn("Beta Tester", self.ad.members[B][1])

    def test_tester_remove_member_gone(self):
        """★ М-7: участника нет на сервере — роль не снимается, одобренные заявки всё равно отклоняются (как в предпросмотре)."""
        r = self.run1(cmd(1, "tester_remove", GONE))
        self.assertTrue(r[1], r)
        self.assertEqual(self.state.data["applications"][3]["status"], "rejected")
        self.assertFalse([c for c in self.ad.calls if c[0] == "remove_role"])

    def test_warns_clear_restore(self):
        """Снятые варны — в данных отката; возврат без дублей; без данных — отказ."""
        r = self.run1(cmd(1, "warns_clear", A))
        self.assertTrue(r[1])
        self.assertEqual(self.state.data["warns"][str(A)], [])
        self.assertEqual(len(self.undo_of(1)["undo"]["removed"]), 1)
        r2 = self.run1(cmd(2, "warns_restore", A, ref=1))
        self.assertTrue(r2[1], r2)
        self.assertEqual(len(self.state.data["warns"][str(A)]), 1)
        self.assertFalse(self.run1(cmd(3, "warns_restore", A, ref=99))[1])

    def test_ban_unban_and_noop_undo(self):
        """Бан, повторный бан — changed = 0; ★ В-1: откат «пустого» бана чужой бан НЕ снимает; откат настоящего — снимает."""
        r = self.run1(cmd(1, "ban", A))
        self.assertTrue(r[1], r)
        self.assertIs(self.undo_of(1)["changed"], True)
        r2 = self.run1(cmd(2, "ban", A))
        self.assertIn("уже стоял", r2[2])
        self.assertIs(self.undo_of(2)["changed"], False)
        r3 = self.run1(cmd(3, "unban", A, ref=2))
        self.assertIn(A, self.ad.banned)
        self.assertIn("бан не ставила", r3[2])
        r4 = self.run1(cmd(4, "unban", A, ref=1))
        self.assertTrue(r4[1])
        self.assertNotIn(A, self.ad.banned)
        r5 = self.run1(cmd(5, "unban", A))
        self.assertIn("бана нет", r5[2])
        self.assertIs(self.undo_of(5)["changed"], False)
        self.run1(cmd(6, "ban", A, ref=5))
        self.assertNotIn(A, self.ad.banned)                # откат «пустого» разбана никого не банит


class Review80Test(Base):
    """★ р80: чужой бан / роль после упавшего вызова не считаются своими; данные отката — из своего журнала; откат снятия у ушедшего;
    список модераторов — по текущему состоянию."""

    def _fail_once(self, name):
        """Подменить вызов адаптера: первый раз — точный отказ Discord (HTTP 500 с ответом)."""
        real = getattr(self.ad, name)
        state = {"n": 0}

        async def f(*a):
            """Первый вызов падает, дальше — настоящий."""
            state["n"] += 1
            if state["n"] == 1:
                raise C.AdapterError("Discord HTTP 500 на «%s»" % name)
            return await real(*a)
        setattr(self.ad, name, f)

    def test_ban_failed_then_manual_ban_then_retry_undo_keeps_ban(self):
        """Сценарий ревизора: бан упал → модератор банит вручную → «Повторить» → changed = 0 → откат не снимает бан модератора."""
        self._fail_once("ban")
        r1 = self.run1(cmd(1, "ban", A))
        self.assertFalse(r1[1])
        self.assertNotIn("ban_pending", self.w.ledger.get(1))
        self.ad.banned.add(A)                                       # модератор забанил сам
        r2 = self.run1(cmd(1, "ban", A, attempts=2))
        self.assertTrue(r2[1])
        self.assertIn("уже стоял", r2[2])
        self.assertIs(self.undo_of(1)["changed"], False)
        self.run1(cmd(2, "unban", A, ref=1))
        self.assertIn(A, self.ad.banned)

    def test_unban_failed_then_manual_unban_retry_undo_does_not_ban(self):
        """Зеркально: разбан упал → модератор разбанил → повтор → откат не банит."""
        U = 111111111111111112
        self._fail_once("unban")
        self.assertFalse(self.run1(cmd(1, "unban", U))[1])
        self.ad.banned.discard(U)
        r2 = self.run1(cmd(1, "unban", U, attempts=2))
        self.assertIs(self.undo_of(1)["changed"], False)
        self.assertIn("бана нет", r2[2])
        self.run1(cmd(2, "ban", U, ref=1))
        self.assertNotIn(U, self.ad.banned)

    def test_approve_role_failed_then_manual_role_retry_undo_keeps_role(self):
        """add_role упал → роль выдали вручную → повтор → role_added = False → откат решения роль не снимает."""
        self._fail_once("add_role")
        self.assertFalse(self.run1(cmd(1, "app_approve", A, app_msg=1001))[1])
        self.ad.members[A][1].append("Beta Tester")
        r2 = self.run1(cmd(1, "app_approve", A, app_msg=1001, attempts=2))
        self.assertTrue(r2[1], r2)
        self.assertEqual(self.undo_of(1)["undo"]["role_added"], False)
        self.run1(cmd(2, "app_reopen", A, app_msg=1001, ref=1))
        self.assertIn("Beta Tester", self.ad.members[A][1])

    def test_timeout_is_not_definite(self):
        """Обрыв связи — исход неизвестен: намерение остаётся, но «наш» бан — только подтверждённый (ban_done)."""
        async def boom(*a):
            """Обрыв связи."""
            raise C.AdapterError("сбой связи", definite=False)
        self.ad.ban = boom
        self.assertFalse(self.run1(cmd(1, "ban", A))[1])
        self.assertTrue(self.w.ledger.get(1).get("ban_pending"))
        self.assertFalse(self.w.ledger.get(1).get("ban_done"))

    def test_undo_data_must_match_own_journal(self):
        """Подложенные в базу данные отката (не совпадают с журналом бота) — отказ, роль не выдаётся."""
        self.run1(cmd(1, "tester_remove", A))                      # у alice роли нет: role_removed = False
        r = self.run1(cmd(2, "tester_add", A, ref=1, ref_undo={"role_removed": True, "apps_changed": []}))
        self.assertFalse(r[1])
        self.assertIn("не совпадают с журналом бота", r[2])
        self.assertNotIn("Beta Tester", self.ad.members[A][1])

    def test_undo_data_from_db_shape_checked(self):
        """Журнал вытеснил запись (★ р81: журнал полон, номер старше самого старого) — данные из базы, но только проверенного вида."""
        saved = outbox_bot.LEDGER_MAX
        outbox_bot.LEDGER_MAX = 2
        try:
            self.w.ledger.put(100, state="done")
            self.w.ledger.put(101, state="done")
            bad = {"removed": [{"mod": "x", "reason": 5}]}
            r = self.run1(cmd(3, "warns_restore", A, ref=77, ref_undo=bad))
            self.assertFalse(r[1])
            self.assertIn("не прошли проверку", r[2])
            good = {"removed": [{"mod": 1, "ts": "2026-11-20T10:00:00+00:00", "reason": "x" * 1000}]}   # ★ р81 М-5: длинная причина /warn — годна
            r2 = self.run1(cmd(4, "warns_restore", A, ref=78, ref_undo=good))
            self.assertTrue(r2[1], r2)
        finally:
            outbox_bot.LEDGER_MAX = saved
        self.assertIsNone(C.undo_shape_error({"removed": [{"mod": 1, "ts": "t", "reason": "r"}], "role_added": True}))
        self.assertIsNotNone(C.undo_shape_error({"role_added": "yes"}))
        self.assertIsNotNone(C.undo_shape_error({"apps_changed": [[1, "evil"]]}))

    def test_forged_undo_for_command_bot_never_ran(self):
        """★ р81 М-1 (сценарий ревизора): итог команды записал чужой процесс, бот её не исполнял — откат с подложенными данными отказан,
        роль не выдана, предупреждения не подложены."""
        r = self.run1(cmd(5, "tester_add", A, ref=77, ref_undo={"role_removed": True, "apps_changed": []}))
        self.assertFalse(r[1])
        self.assertIn("не исполнял", r[2])
        self.assertNotIn("Beta Tester", self.ad.members[A][1])
        forged = {"removed": [{"mod": 1, "ts": "2026-11-20T10:00:00+00:00", "reason": "fake"}] * 2}
        r2 = self.run1(cmd(6, "warns_restore", A, ref=78, ref_undo=forged))
        self.assertFalse(r2[1])
        self.assertEqual(len(self.state.data["warns"][str(A)]), 1)

    def test_unknown_after_timeout_texts(self):
        """★ р81 М-2: бан встал после тайм-аута — итог «бан стоит, чей — неизвестно… «Разбан»», откат недоступен; то же для роли."""
        async def boom(*a):
            """Обрыв связи, но бан в Discord встал."""
            self.ad.banned.add(A)
            raise C.AdapterError("сбой связи", definite=False)
        real = self.ad.ban
        self.ad.ban = boom
        self.run1(cmd(1, "ban", A))
        self.ad.ban = real
        r = self.run1(cmd(1, "ban", A, attempts=2))
        self.assertIn("неизвестно", r[2])
        self.assertIn("«Разбан»", r[2])
        self.assertIs(self.undo_of(1)["changed"], False)

        async def boom_role(uid, rid, reason):
            """Обрыв связи, но роль выдана."""
            self.ad.members[uid][1].append("Beta Tester")
            raise C.AdapterError("сбой связи", definite=False)
        self.ad.add_role = boom_role
        self.run1(cmd(2, "app_approve", A, app_msg=1001))
        r2 = self.run1(cmd(2, "app_approve", A, app_msg=1001, attempts=2))
        self.assertIn("неизвестно", r2[2])
        self.assertEqual(self.undo_of(2)["undo"]["role_added"], False)

    def test_mod_log_says_what_was_done(self):
        """★ р81 М-4: mod-log — только реально сделанное (роль не выдана — так и написано)."""
        self.run1(cmd(1, "tester_remove", GONE))
        self.run1(cmd(2, "tester_add", GONE, ref=1))
        logs = [c[1] for c in self.ad.calls if c[0] == "mod_log"]
        self.assertTrue(any("не выдана (участника нет на сервере), заявкам возвращён статус: 1" in t for t in logs), logs)
        self.assertFalse(any("роль Beta Tester выдана —" in t for t in logs))

    def test_tester_remove_gone_and_undo(self):
        """★ М-3: снятие у ушедшего — заявки отклонены; откат — заявки вернулись, роль не выдаётся (участника нет)."""
        self.run1(cmd(1, "tester_remove", GONE))
        self.assertEqual(self.state.data["applications"][3]["status"], "rejected")
        r = self.run1(cmd(2, "tester_add", GONE, ref=1))
        self.assertTrue(r[1], r)
        self.assertEqual(self.state.data["applications"][3]["status"], "approved")
        self.assertFalse([c for c in self.ad.calls if c[0] == "add_role"])

    def test_staff_book_current_state(self):
        """★ М-4: разжалованный на сервере — снимается из списка; ушедший модератор — остаётся; старый вид файла читается."""
        p = os.path.join(self.tmp.name, "old.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"%d": "staff", "%d": "gone-mod"}' % (S, 111111111111111114))
        sb = C.StaffBook(p)
        self.assertIn(S, sb)
        sb.update([], {S, A})                                       # S на сервере, но уже без прав
        self.assertNotIn(S, sb)
        self.assertIn(111111111111111114, sb)                       # ушедший — остаётся
        self.assertEqual(sb.items({A}), [(111111111111111114, "gone-mod", 0)])


class RealAdapterTest(unittest.TestCase):
    """Настоящий DiscordAdapter на подставной гильдии: бан — delete_message_seconds = 0, mod-log без упоминаний, права и иерархия цели."""

    def _discord(self):
        """discord.py (под -I — из пользовательских пакетов, откуда его берёт бот)."""
        try:
            import discord
        except ImportError:
            import site
            sys.path.append(site.getusersitepackages())
            import discord
        return discord

    def test_ban_without_message_delete(self):
        """Бан без удаления сообщений, разбан, mod-log без @everyone, роль ровно одна."""
        discord = self._discord()
        seen = {}

        class G:
            me = types.SimpleNamespace(id=ME)
            owner_id = OWNER
            roles = [types.SimpleNamespace(id=777, name="🧪 Beta Tester"), types.SimpleNamespace(id=778, name="Beta Tester old")]
            members = []
            member_count = 0

            async def ban(self, obj, reason=None, delete_message_seconds=None):
                seen["ban"] = (obj.id, delete_message_seconds, reason)

            async def unban(self, obj, reason=None):
                seen["unban"] = obj.id

            def get_channel(self, cid):
                return Ch() if cid == 2 else None

        class Ch:
            async def send(self, text, allowed_mentions=None):
                seen["log"] = (text, allowed_mentions)

        ad = C.DiscordAdapter(G(), 1, 2, None, PROT, "Beta Tester")
        asyncio.run(ad.ban(A, "r"))
        asyncio.run(ad.unban(A, "r"))
        asyncio.run(ad.mod_log("hi @everyone"))
        self.assertEqual(seen["ban"][:2], (A, 0))
        self.assertEqual(seen["unban"], A)
        self.assertIsInstance(seen["log"][1], discord.AllowedMentions)
        self.assertFalse(seen["log"][1].everyone)
        self.assertEqual(ad.role_id("Beta Tester"), 777)
        with self.assertRaises(C.AdapterError):
            C.DiscordAdapter(types.SimpleNamespace(roles=[]), 1, 2).role_id("Beta Tester")

    def test_member_perms_and_hierarchy(self):
        """★ М-5: права модерации и «выше бота» — из guild_permissions и top_role."""
        self._discord()
        perms = types.SimpleNamespace(administrator=False, ban_members=True, kick_members=False, manage_roles=False, moderate_members=False)
        m = types.SimpleNamespace(id=A, bot=False, roles=[types.SimpleNamespace(name="Support Lead")], guild_permissions=perms, top_role=5)
        g = types.SimpleNamespace(me=types.SimpleNamespace(id=ME, top_role=3, guild_permissions=perms), get_member=lambda uid: m, members=[m],
                                  owner_id=OWNER)
        ad = C.DiscordAdapter(g, 1, 2, None, PROT)
        info = asyncio.run(ad.member_info(A))
        self.assertEqual(info["mod"], ["ban_members"])
        self.assertTrue(info["above_bot"])
        self.assertEqual(ad.staff(), [(A, str(m))])
        self.assertEqual(ad.me_perms(), {"ban_members": True, "manage_roles": False})

    def test_source_guards(self):
        """В исходнике: бан только без удаления сообщений, ни kick, ни создания ролей, ни @everyone."""
        with open(os.path.join(HERE, "community_bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(src.count("delete_message_seconds=0"), 1)
        self.assertNotIn("delete_message_days", src)
        self.assertNotIn("everyone=True", src)
        self.assertNotIn(".kick(", src)
        self.assertNotIn("create_role", src)


class OracleHookTest(unittest.TestCase):
    """Связка с oracle_bot.py по исходнику (без импорта)."""

    def test_oracle_wiring(self):
        """Цикл стартует в setup_hook, адаптеру передаются PROTECTED и TESTER_ROLE из oracle_bot."""
        with open(os.path.join(HERE, "oracle_bot.py"), encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        self.assertIn("self.community_loop.start()", ast.get_source_segment(src, fns["setup_hook"]))
        body = ast.get_source_segment(src, fns["community_loop"])
        self.assertIn("PROTECTED, TESTER_ROLE", body)
        self.assertNotIn(".send(", body)
        consts = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
                  if isinstance(t, ast.Name) and t.id in ("PROTECTED", "TESTER_ROLE")}
        self.assertEqual(consts["PROTECTED"], PROT)
        self.assertEqual(consts["TESTER_ROLE"], C.ROLES["beta_tester"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
