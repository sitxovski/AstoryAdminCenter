# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""community.py — «Сообщество»: заявки в тестеры, тестеры, предупреждения /warn, баны Discord и команды боту (шаг А7.6, 24.11.2026; решение
владельца А7 №9 — хозяин реестра заявок и тестеров остаётся бот Oracle: его state.json и роли сервера Discord; панель читает КОПИЮ и шлёт боту
команды; разбор Reports/admin_center/research_a7_releases_20261123.md §3 А7.6; отчёт impl_a7_releases_20261123.md §А7.6, ревизия 79).

ОТКУДА ДАННЫЕ. Бот на ПК раз в 5 мин и после каждой команды присылает снимок (AstoryAdminCenter/DiscordBot/community_bot.py → adm.BotSnapPut):
  заявки (Discord id и ник, статус, когда подана, кто и когда решил), тестеры (роль Beta Tester), предупреждения, баны сервера Discord, известные
  модераторы (★ р79 М-5). Ответов анкеты, IP и паролей в копии нет. Панель копию только читает (adm.BotSnap / BotApp / BotTester / BotWarn /
  BotBan / BotStaff — sql/adminc_30_community.sql).
ВСТРОЕНО, НЕ ПРОДУБЛИРОВАНО:
  привязка Discord ↔ логин игры — domains/discordlinks.py (копия playtest_accounts.txt без паролей): по Discord id строки показывают логин;
  реестр исключённых BANNED_PLAYERS.md против блока входа — players.discord_bans() и его же блок экрана discordBans() из web/app.js;
  блок / снятие блока учётки — существующие операции account.block / account.unblock (своя запись журнала, свой откат);
  жалобы игроков — раздел «Жалобы игроков» (А6.11, domains/reports.py), здесь только ссылка.
КОМАНДЫ (очередь adm.BotCmd, исполняет бот на ПК раз в 30 с; права — core/auth.py):
  community.app.decide   — принять или отклонить заявку (как кнопки Approve / Reject); откат — заявка снова на рассмотрении (роль, выданная
                           решением, снимается; личное сообщение «принят» не отзывается);
  community.tester.add / community.tester.remove — роль Beta Tester (снятие — как remove_tester.py: одобренные заявки → отклонены); откат — обратная;
  community.warns.clear  — снять предупреждения (снятые бот кладёт в данные отката); откат — вернуть их;
  community.ban.check    — ★ р79 В-2: проверка цели ботом перед баном с блоком (есть ли участник, нет ли защиты, хватает ли прав) — без Discord;
  community.ban          — бан сервера Discord (без удаления сообщений) + по флажку блок учётки игры account.block — только после прошедшей проверки
                           цели; откат — разбан (блок снимается откатом своей записи журнала account.block);
  community.unban        — разбан + по флажку снятие блока account.unblock; откат — бан;
  community.cmd.cancel / community.cmd.retry — отменить до исполнения, повторить после ошибки (у бана и разбана — право community.ban, ★ р79 М-4);
  community.test         — проверочная команда: бот отмечает «тест», Discord не вызывает.
  У любой команды есть параметр test: команда идёт той же очередью с отметкой «тест», бот её НЕ исполняет (живой самотест так и проверяет путь).
ОТКАТ (★ р79 В-1): бот возвращает признак «изменила ли команда что-то» и данные отката (adm.BotCmd.changed / undo_json). Откат разрешён только у
  команды, которая что-то изменила, и восстанавливает ровно сделанное; «ничего не изменила» (роль уже была, бан уже стоял) — откатывать нечего,
  в журнале действий кнопки отката у такой записи нет (undo_note).
БЕЛЫЕ СПИСКИ — в коде (здесь, у бота и в CHECK adm.BotCmd; самотест сверяет): команды CMDS, роль — только Beta Tester; цель под защищённой ролью,
  с правами модерации или выше бота бот отклоняет.
Побочных эффектов при импорте нет.
"""
import json
import re

from core import audit, db
from core import ops
from core.ops import Operation, OpRefused, register

CMDS = ("app_approve", "app_reject", "app_reopen", "tester_add", "tester_remove", "warns_clear", "warns_restore", "ban", "unban", "test",
        "check")                                     # белый список команд (= CHECK adm.BotCmd = community_bot.CMDS)
ROLES = {"beta_tester": "Beta Tester"}              # единственная роль, которой касаются команды
ROLE_CMDS = ("app_approve", "tester_add", "tester_remove")   # команды с ролью
BAN_CMDS = ("ban", "unban")                          # ★ р79 М-4: их отмена и повтор — под правом community.ban
CMD_TITLES = {"app_approve": "принять заявку", "app_reject": "отклонить заявку", "app_reopen": "вернуть заявку на рассмотрение",
              "tester_add": "выдать роль Beta Tester", "tester_remove": "снять роль Beta Tester", "warns_clear": "снять предупреждения",
              "warns_restore": "вернуть снятые предупреждения", "ban": "бан сервера Discord", "unban": "разбан сервера Discord",
              "test": "проверочная команда", "check": "проверка цели перед баном"}      # подписи команд для экрана и журнала
STATUS = {7: "hold", 0: "queued", 1: "claimed", 2: "done", 3: "failed", 4: "cancelled", 5: "expired", 6: "test"}   # статусы adm.BotCmd
APP_FILTERS = ("all", "pending", "approved", "rejected")   # фильтр заявок экрана
PER_HOUR, PER_DAY, TEST_PER_HOUR = 30, 200, 10   # пределы adm.BotCmdPut (здесь — для подписей)
STUCK_MIN = 10                  # бот взял и не отчитался дольше — «итог неизвестен», можно повторить
BOT_IDLE_MIN = 5                # команда ждёт бота дольше — предупреждение
SNAP_STALE_MIN = 20             # снимок старше — предупреждение «копия устарела»
CHECK_TTL_MIN = 30              # ★ р79 В-2: прошедшая проверка цели годна для бана с блоком столько минут
MAX_ATTEMPTS = 5                # попыток у команды
PAGE_MAX = 300                  # строк очереди на экране
REASON_MIN, REASON_MAX = 3, 300  # длина причины
NOT_INSTALLED = "таблиц «Сообщества» нет (sql/adminc_30_community.sql не установлен)"
PUT_CODES = {1: "команд боту за час уже %d — предел %d в час" % (PER_HOUR, PER_HOUR),
             2: "команд боту за сутки уже %d — предел %d в сутки" % (PER_DAY, PER_DAY),
             3: "проверочных команд за час уже %d — предел %d в час" % (TEST_PER_HOUR, TEST_PER_HOUR),
             4: "команда не прошла проверку базы (команда, роль, заявка, ссылка на откатываемую команду, причина)",
             5: "такая же команда этому участнику уже ждёт бота — дождитесь итога или отмените её",
             6: "откатываемая команда не исполнена или ничего не изменила — откатывать нечего"}   # коды adm.BotCmdPut
BAN_WARN = ["бан выгоняет участника с сервера Discord: его роли пропадают, и разбан их не вернёт — участник заходит заново по приглашению и "
            "проходит онбординг",
            "история сообщений: бот банит без удаления сообщений (delete_message_seconds = 0) — переписка участника остаётся. Удаление истории "
            "при бане необратимо, поэтому панель его не предлагает",
            "бот откажет, если у цели защищённая роль (Oracle, Head of Development, Administrator, Community Administrator, Community Director, "
            "Moderator), права модерации (administrator, ban_members, kick_members, manage_roles, moderate_members) или роль не ниже роли бота, "
            "а также боту и владельцу сервера"]   # честные предупреждения бана (окно подтверждения)
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")    # управляющие символы (запрещены в причине)
_DID = re.compile(r"^\d{15,20}$")                   # вид Discord id


def _read(fn):
    """Выполнить fn(соединение AsdaAdmin); сбой базы → понятный отказ."""
    try:
        cn = db.admin()
    except db.DbError as ex:
        raise OpRefused("«Сообщество» не прочитано: %s" % ex)
    try:
        return fn(cn)
    except db.DbError as ex:
        raise OpRefused("«Сообщество» не прочитано: %s" % ex)
    finally:
        cn.close()


def _installed(cn):
    """Установлен ли шаг. ★ 24.11 (живой самотест): процедура — та, что панели РАЗРЕШЕНА (BotCmdPut): у процедур бота панели DENY EXECUTE, и под
    asda_admin OBJECT_ID(…BotSnapPut) — NULL (метаданные не видны); на стенде LocalDB (вход владельцем) этого не видно."""
    return bool(db.admin_rows(cn, "SELECT 1 AS ok WHERE OBJECT_ID(N'adm.BotCmd', N'U') IS NOT NULL AND OBJECT_ID(N'adm.BotCmdPut', N'P') IS NOT NULL"))


def _iso(v):
    """Время → строка «ГГГГ-ММ-ДД ЧЧ:ММ:СС» (или None)."""
    return v.isoformat(sep=" ") if hasattr(v, "isoformat") else (str(v) if v is not None else None)


def did(v, name="Discord id"):
    """Discord id → int (15–20 цифр) или отказ."""
    s = str(v if v is not None else "").strip()
    if not _DID.match(s) or int(s) > 2 ** 63 - 1:
        raise OpRefused("%s — 15–20 цифр" % name)
    return int(s)


def msgid(v):
    """Номер карточки заявки (id сообщения в staff-chat) → int или отказ."""
    s = str(v if v is not None else "").strip()
    if not re.match(r"^\d{1,20}$", s) or int(s) > 2 ** 63 - 1 or int(s) < 1:
        raise OpRefused("номер карточки заявки — целое до 20 цифр")
    return int(s)


def reason_of(p):
    """Причина команды: 3–300 знаков одной строкой, без управляющих символов и @everyone / @here."""
    r = (p or {}).get("reason")
    if not isinstance(r, str):
        raise OpRefused("причина — строка от %d до %d знаков" % (REASON_MIN, REASON_MAX))
    r = r.replace("\r", " ").replace("\n", " ").strip()
    if not REASON_MIN <= len(r) <= REASON_MAX:
        raise OpRefused("причина — строка от %d до %d знаков" % (REASON_MIN, REASON_MAX))
    if _CTRL.search(r):
        raise OpRefused("в причине управляющие символы")
    if "@everyone" in r.lower() or "@here" in r.lower():
        raise OpRefused("@everyone и @here в причине запрещены")
    return r


def _links():
    """Discord id → логин игры (domains/discordlinks: копия playtest_accounts.txt без паролей)."""
    from domains import discordlinks
    out = {}
    for x in discordlinks.links():
        if x.get("discord_id"):
            out.setdefault(int(x["discord_id"]), x.get("login"))
    return out


# ---------------------------------------------------------------- чтение

def snapshot(cn):
    """Сводка последнего снимка реестра (adm.BotSnap) с возрастом в секундах или None."""
    r = db.admin_rows(cn, "SELECT taken_utc, bot, apps_open, lockdown, members, n_apps, n_testers, n_warns, n_bans, note, "
                          "DATEDIFF(SECOND, taken_utc, SYSUTCDATETIME()) AS age_s FROM adm.BotSnap WHERE id = 1")
    return r[0] if r else None


def _cmd_rows(cn, where="", params=(), top=PAGE_MAX):
    """Строки очереди команд (новые сверху) по условию where (не больше top)."""
    return db.admin_rows(cn, "SELECT TOP (%d) id, cmd, target_uid, role_key, app_msg_id, ref_id, reason, block_uid, block_audit, is_test, created_utc, "
                             "created_by, expires_utc, status, attempts, claimed_utc, done_utc, result, changed_by, changed_utc, changed, "
                             "CASE WHEN undo_json IS NULL THEN 0 ELSE 1 END AS has_undo, "
                             "CASE WHEN undo_json LIKE N'%%\"[_]too_long\"%%' THEN 1 ELSE 0 END AS undo_lost FROM adm.BotCmd %s "
                             "ORDER BY id DESC" % (int(top), where), params)


def _state(r, now):
    """Статус строки для экрана (взятая и молчащая дольше STUCK_MIN — «итог неизвестен»)."""
    st = int(r["status"])
    if st == 1 and r["claimed_utc"] and (now - r["claimed_utc"]).total_seconds() > STUCK_MIN * 60:
        return "unknown"
    return STATUS.get(st, str(st))


def undo_block_reason(r):
    """★ р79 В-1: почему команду нельзя откатить (None — можно): не исполнена, ничего не изменила, нет данных отката."""
    st = int(r["status"])
    if st in (0, 1, 7):
        return "команда №%d ещё не исполнена ботом — отмените её в очереди вместо отката" % r["id"]
    if st == 6:
        return None
    if st != 2:
        return "команда №%d не исполнена (%s) — откатывать нечего" % (r["id"], STATUS.get(st, st))
    if r["cmd"] in ("app_reopen", "warns_restore", "check", "test"):
        return "команда №%d — сама откат или проверка, её не откатывают" % r["id"]
    if r.get("changed") and (not r.get("has_undo") or r.get("undo_lost")):        # ★ р80 М-6
        return "у команды №%d данные отката не сохранены — откатывать нечем" % r["id"]
    if r.get("changed") is None:
        return "у команды №%d нет данных отката (её исполнила прежняя версия бота) — откатывать нечем" % r["id"]
    if not r["changed"]:
        return "команда №%d ничего не изменила (итог бота: %s) — откатывать нечего" % (r["id"], r["result"] or "—")
    return None


def _cmd_out(r, now, links):
    """Строка очереди → dict для экрана (что, кому, статус, итог, можно ли отменить, повторить, откатить)."""
    st = _state(r, now)
    x = {"id": r["id"], "cmd": r["cmd"], "title": CMD_TITLES.get(r["cmd"], r["cmd"]), "target": str(r["target_uid"]),
         "login": links.get(int(r["target_uid"])) if r["target_uid"] else None, "app": str(r["app_msg_id"]) if r["app_msg_id"] else "",
         "ref": r["ref_id"], "reason": r["reason"], "block_uid": r["block_uid"], "block_audit": r["block_audit"], "test": bool(r["is_test"]),
         "created": _iso(r["created_utc"]), "by": r["created_by"], "expires": _iso(r["expires_utc"]), "state": st, "attempts": r["attempts"],
         "done": _iso(r["done_utc"]), "result": r["result"] or "", "changed_by": r["changed_by"] or "", "changed": _iso(r["changed_utc"]),
         "did_change": r.get("changed")}
    x["can_cancel"] = st in ("queued", "hold")
    x["can_retry"] = st in ("failed", "unknown") and r["attempts"] < MAX_ATTEMPTS and r["expires_utc"] > now
    x["ban"] = r["cmd"] in BAN_CMDS
    x["undo_note"] = (undo_block_reason(r) or "") if st == "done" else ""
    return x


def _block_stuck(cn):
    """★ р79 В-2 / ★ р80 М-7: ВСЕ незакрытые случаи «бан с блоком учётки не встал (ошибка, отмена, просрочка), а блок стоит»: запись блока не
    откачена и после неё не было снятия блока этой учётки — одним запросом → [{cmd, block_audit, uid, target, state, result}]."""
    rows = db.admin_rows(cn, "SELECT c.id, c.block_audit, c.block_uid, c.target_uid, c.status, c.result FROM adm.BotCmd c "
                             "JOIN adm.audit a ON a.id = c.block_audit WHERE c.cmd = 'ban' AND c.status IN (3, 4, 5) AND a.undone_by IS NULL "
                             "AND NOT EXISTS (SELECT 1 FROM adm.audit u WHERE u.action = 'account.unblock' AND u.result = 'ok' "
                             "AND u.target = N'account:' + CAST(c.block_uid AS NVARCHAR(12)) AND u.at > a.at) ORDER BY c.id")
    return [{"cmd": r["id"], "block_audit": int(r["block_audit"]), "uid": r["block_uid"], "target": str(r["target_uid"]),
             "state": STATUS.get(int(r["status"])), "result": r["result"] or ""} for r in rows]


def undo_notes(rows):
    """★ р80 М-7: причины «откатывать нечего» для записей журнала «Сообщества» одним запросом → {номер записи: причина}."""
    want = {}
    for r in rows:
        op = ops.REGISTRY.get(r.get("action"))
        if not isinstance(op, _CmdOp) or r.get("result") != "ok" or r.get("undo_of") or r.get("undone_by"):
            continue
        try:
            cid = int(json.loads(r.get("after_json") or "{}").get("cmd") or 0)
        except (TypeError, ValueError):
            cid = 0
        want[r["id"]] = cid
    ids = sorted({c for c in want.values() if c})
    if not want:
        return {}
    got = {}
    if ids:
        try:
            for k in range(0, len(ids), 500):          # ★ р81 М-3: все номера страницы (до 1000), без предела в 300 строк
                part = ids[k:k + 500]
                got.update({int(x["id"]): x for x in _read(lambda c, part=part: _cmd_rows(c, "WHERE id IN (%s)" % ",".join(str(i) for i in part),
                                                                                         top=len(part)))})
        except OpRefused as ex:
            return {aid: str(ex) for aid in want}
    out = {}
    for aid, cid in want.items():
        r = got.get(cid)
        why = "в журнале нет номера команды — откат не выполнен" if not cid else ("команды боту №%d нет" % cid if r is None else undo_block_reason(r))
        if why:
            out[aid] = why
    return out


def view(q=None):
    """Экран «Сообщество»: копия реестра бота, очередь команд со статусами, предупреждения, «блок стоит, бана нет». Реестр исключённых против
    блока входа экран берёт готовым маршрутом /api/players/discord_bans (players.discord_bans — как в «Учётках»)."""
    q = q or {}
    flt = str(q.get("apps") or "pending")
    if flt not in APP_FILTERS:
        raise OpRefused("неверный фильтр (можно: %s)" % ", ".join(APP_FILTERS))

    def go(cn):
        """Все чтения одним соединением."""
        if not _installed(cn):
            return None
        snap = snapshot(cn)
        apps = db.admin_rows(cn, "SELECT msg_id, uid, user_name, status, ts_utc, decided_by, decided_utc, in_guild, is_tester FROM adm.BotApp %s "
                                 "ORDER BY ts_utc DESC" % ("" if flt == "all" else "WHERE status = ?"), () if flt == "all" else (flt,))
        cnt = db.admin_rows(cn, "SELECT status, COUNT(*) AS n FROM adm.BotApp GROUP BY status")
        testers = db.admin_rows(cn, "SELECT uid, user_name FROM adm.BotTester ORDER BY user_name")
        warns = db.admin_rows(cn, "SELECT uid, n, mod_uid, reason, ts_utc FROM adm.BotWarn ORDER BY uid, n")
        bans = db.admin_rows(cn, "SELECT uid, user_name, reason FROM adm.BotBan ORDER BY user_name")
        staff = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.BotStaff")[0]["n"]
        cmds = _cmd_rows(cn)
        stuck = _block_stuck(cn)
        ccnt = db.admin_rows(cn, "SELECT status, COUNT(*) AS n FROM adm.BotCmd GROUP BY status")
        last = db.admin_rows(cn, "SELECT MAX(claimed_utc) AS c, MAX(done_utc) AS d FROM adm.BotCmd")[0]
        now = db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
        return snap, apps, cnt, testers, warns, bans, staff, cmds, stuck, ccnt, last, now
    base = {"filters": APP_FILTERS, "cmd_titles": CMD_TITLES, "limits": {"per_hour": PER_HOUR, "per_day": PER_DAY, "stuck_min": STUCK_MIN,
            "snap_stale_min": SNAP_STALE_MIN, "max_attempts": MAX_ATTEMPTS, "reason_min": REASON_MIN, "reason_max": REASON_MAX,
            "check_ttl_min": CHECK_TTL_MIN}}
    got = _read(go)
    if got is None:
        return dict(base, installed=False, error=NOT_INSTALLED, snap=None, apps=[], testers=[], warns=[], bans=[], cmds=[], counts={}, cmd_counts={},
                    block_stuck=[], staff=0, warnings=[NOT_INSTALLED])
    snap, apps, cnt, testers, warns, bans, staff, cmds, stuck, ccnt, last, now = got
    links = _links()
    warn = []
    for s in stuck:
        warn.insert(0, "учётка %s заблокирована, а бана в Discord нет: команда №%d — %s, итог бота: %s. Блок — запись журнала №%d: снимите его "
                       "кнопкой «Снять блок» или повторите бан" % (s["uid"], s["cmd"], STATUS_TITLES.get(s["state"], s["state"]), s["result"] or "—",
                                                           s["block_audit"]))
    if snap is None:
        warn.append("бот ещё не прислал копию реестра — запущен ли бот Oracle на ПК владельца (новая версия с «Сообществом»)")
    elif int(snap["age_s"] or 0) > SNAP_STALE_MIN * 60:
        warn.append("копия реестра старше %d мин (снята %s UTC) — бот Oracle на ПК, похоже, не работает: данные на экране могут отставать"
                    % (SNAP_STALE_MIN, _iso(snap["taken_utc"])))
    pend = {}
    for r in cmds:
        if int(r["status"]) in (0, 1, 7) and r["app_msg_id"]:
            pend[int(r["app_msg_id"])] = r["id"]
    tset = {int(t["uid"]) for t in testers}
    bset = {int(b["uid"]) for b in bans}
    wcnt = {}
    for w in warns:
        wcnt[int(w["uid"])] = wcnt.get(int(w["uid"]), 0) + 1
    out_apps = [{"msg_id": str(a["msg_id"]), "uid": str(a["uid"]) if a["uid"] else "", "user": a["user_name"] or "", "status": a["status"],
                 "ts": _iso(a["ts_utc"]), "decided_by": a["decided_by"] or "", "decided": _iso(a["decided_utc"]), "in_guild": bool(a["in_guild"]),
                 "tester": bool(a["is_tester"]), "login": links.get(int(a["uid"])) if a["uid"] else None, "banned": bool(a["uid"]) and int(a["uid"]) in bset,
                 "pending_cmd": pend.get(int(a["msg_id"]))} for a in apps]
    out_cmds = []
    for r in cmds:
        x = _cmd_out(r, now, links)
        if x["state"] == "queued" and (now - r["created_utc"]).total_seconds() > BOT_IDLE_MIN * 60:
            warn.append("команда №%d ждёт бота дольше %d мин — запущен ли бот Oracle на ПК владельца" % (r["id"], BOT_IDLE_MIN))
        elif x["state"] == "unknown":
            warn.append("команда №%d: бот взял её и не отчитался дольше %d мин — посмотрите итог в Discord, потом «повторить» или подождать"
                        % (r["id"], STUCK_MIN))
        elif x["state"] == "hold" and (now - r["created_utc"]).total_seconds() > STUCK_MIN * 60:
            warn.append("команда №%d ждёт блока учётки дольше %d мин — блок не подтвердился, её можно отменить" % (r["id"], STUCK_MIN))
        out_cmds.append(x)
    return dict(base, installed=True, error="",
                snap=None if snap is None else {"taken": _iso(snap["taken_utc"]), "age_s": int(snap["age_s"] or 0), "bot": snap["bot"] or "",
                                                "apps_open": snap["apps_open"], "lockdown": snap["lockdown"], "members": snap["members"],
                                                "n_apps": snap["n_apps"], "n_testers": snap["n_testers"], "n_warns": snap["n_warns"], "n_bans": snap["n_bans"]},
                apps=out_apps, counts={c["status"]: int(c["n"]) for c in cnt},
                testers=[{"uid": str(t["uid"]), "user": t["user_name"] or "", "login": links.get(int(t["uid"])), "warns": wcnt.get(int(t["uid"]), 0)}
                         for t in testers],
                warns=[{"uid": str(w["uid"]), "n": w["n"], "mod": str(w["mod_uid"]) if w["mod_uid"] else "", "reason": w["reason"] or "",
                        "ts": _iso(w["ts_utc"]), "login": links.get(int(w["uid"])), "tester": int(w["uid"]) in tset} for w in warns],
                bans=[{"uid": str(b["uid"]), "user": b["user_name"] or "", "reason": b["reason"] or "", "login": links.get(int(b["uid"]))} for b in bans],
                cmds=out_cmds, cmd_counts={STATUS.get(int(c["status"]), str(c["status"])): int(c["n"]) for c in ccnt}, block_stuck=stuck, staff=int(staff),
                bot_seen=_iso(last["c"]), bot_done=_iso(last["d"]), now=_iso(now), warnings=warn)


STATUS_TITLES = {"failed": "ошибка", "cancelled": "отменена", "expired": "просрочена"}   # исходы команды для предупреждения «блок стоит»


# ---------------------------------------------------------------- запись

def put(cmd, target, by, reason, role=None, app_msg=None, ref=None, block_uid=None, hold=False, test=False):
    """Поставить команду (своё соединение, фиксация сразу) → номер. Отказ по пределу или полям — OpRefused."""
    def go(cn):
        """Вызов adm.BotCmdPut → код и номер."""
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        return db.admin_rows(cn, "SET NOCOUNT ON; DECLARE @id INT, @code INT; EXEC adm.BotCmdPut ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, @id OUTPUT, @code OUTPUT; "
                                 "SELECT @code AS code, @id AS id",
                             (cmd, int(target), role, app_msg, ref, reason, block_uid, str(by)[:32], 1 if hold else 0, 1 if test else 0))[0]
    r = _read(go)
    code = int(r["code"])
    if code:
        raise OpRefused(PUT_CODES.get(code, "очередь команд боту: код %d" % code))
    return int(r["id"])


def release(cid, ok, by, note="", block_audit=None):
    """Команда «ждёт блока учётки» → боту (ok) или отменить."""
    r = _read(lambda c: db.admin_rows(c, "SET NOCOUNT ON; EXEC adm.BotCmdRelease ?, ?, ?, ?, ?",
                                      (int(cid), 1 if ok else 0, str(by)[:32], str(note or "")[:400], block_audit)))
    return int(r[0]["n"])


def cmd_row(cid):
    """Строка команды по номеру и время SQL-сервера → (row, now)."""
    def go(cn):
        """Чтение одной строки."""
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        r = _cmd_rows(cn, "WHERE id = ?", (int(cid),))
        if not r:
            raise OpRefused("команды боту №%d нет" % int(cid))
        return r[0], db.admin_rows(cn, "SELECT SYSUTCDATETIME() AS t")[0]["t"]
    return _read(go)


def _app_row(msg_id):
    """Заявка из копии реестра по номеру карточки или отказ."""
    def go(cn):
        """Чтение заявки."""
        if not _installed(cn):
            raise OpRefused(NOT_INSTALLED)
        return db.admin_rows(cn, "SELECT msg_id, uid, user_name, status, ts_utc FROM adm.BotApp WHERE msg_id = ?", (int(msg_id),))
    r = _read(go)
    if not r:
        raise OpRefused("заявки с карточкой %s нет в копии реестра бота — обновите экран (копия приходит раз в 5 мин)" % msg_id)
    return r[0]


def _is_tester(uid):
    """Есть ли у участника роль Beta Tester по копии реестра."""
    return bool(_read(lambda c: db.admin_rows(c, "SELECT 1 AS x FROM adm.BotTester WHERE uid = ?", (int(uid),))))


def _is_banned(uid):
    """Стоит ли бан по копии реестра."""
    return bool(_read(lambda c: db.admin_rows(c, "SELECT 1 AS x FROM adm.BotBan WHERE uid = ?", (int(uid),))))


def _is_staff(uid):
    """★ р79 М-5 / ★ р80 М-4: модератор, ушедший с сервера (adm.BotStaff, on_server = 0) — бан по id ему запрещён. Кто на сервере, того бот
    проверит сам (права и роли сейчас); разжалованных бот из списка снимает."""
    return bool(_read(lambda c: db.admin_rows(c, "SELECT 1 AS x FROM adm.BotStaff WHERE uid = ? AND ISNULL(on_server, 0) = 0", (int(uid),))))


def _in_guild_hint(uid):
    """Виден ли участник в копии реестра (заявка с «на сервере», тестер) — только подсказка для окна подтверждения."""
    return bool(_read(lambda c: db.admin_rows(c, "SELECT 1 AS x WHERE EXISTS (SELECT 1 FROM adm.BotTester WHERE uid = ?) "
                                                 "OR EXISTS (SELECT 1 FROM adm.BotApp WHERE uid = ? AND in_guild = 1)", (int(uid), int(uid)))))


def _warn_count(uid):
    """Сколько предупреждений у участника по копии реестра."""
    return int(_read(lambda c: db.admin_rows(c, "SELECT COUNT(*) AS n FROM adm.BotWarn WHERE uid = ?", (int(uid),)))[0]["n"])


def _passed_check(uid):
    """★ р79 В-2: свежая (моложе CHECK_TTL_MIN) прошедшая проверка цели ботом → строка команды check или None."""
    r = _read(lambda c: db.admin_rows(c, "SELECT TOP 1 id, done_utc, result FROM adm.BotCmd WHERE cmd = 'check' AND target_uid = ? AND is_test = 0 "
                                         "AND status = 2 AND done_utc > DATEADD(MINUTE, -?, SYSUTCDATETIME()) ORDER BY id DESC",
                                      (int(uid), CHECK_TTL_MIN)))
    return r[0] if r else None


def _test(p):
    """Отметка «тест» у параметров операции."""
    return bool((p or {}).get("test"))


def _who(uid, links=None):
    """«Discord id (логин игры …)» для текстов предпросмотра."""
    links = _links() if links is None else links
    lg = links.get(int(uid))
    return "%d%s" % (int(uid), " (логин игры %s)" % lg if lg else "")


COMMON_WARN = "исполняет бот Oracle на ПК владельца в течение 30 с, если он запущен — итог виден в очереди команд на этой странице"
TEST_WARN = "проверочная команда: бот её заберёт и отметит «тест», в Discord ничего не изменится"


def _warns(p, extra):
    """Предупреждения окна подтверждения: у проверочной — только «тест», иначе свои и общее «исполняет бот на ПК»."""
    if _test(p):
        return [TEST_WARN]
    return list(extra) + [COMMON_WARN]


class _CmdOp(Operation):
    """Общее: цель журнала — Discord id, постановка команды, откат — обратной командой (после того как бот исполнил исходную и она что-то
    изменила, ★ р79 В-1)."""
    perm = "community.manage"
    reversible = True

    def target(self, p):
        """Цель записи журнала."""
        return "discord:%s" % ((p or {}).get("uid"),)

    def _put(self, ctx, p, cmd, uid, reason, **kw):
        """Поставить команду от имени оператора (с отметкой «тест», если она есть)."""
        return put(cmd, uid, ctx.login, reason, test=_test(p), **kw)

    def _orig_row(self, row):
        """Строка исходной команды по записи журнала."""
        a = json.loads(row.get("after_json") or "{}")
        cid = a.get("cmd")
        if not cid:
            raise OpRefused("в журнале нет номера команды — откат не выполнен")
        return cmd_row(cid)[0]

    def _orig(self, row):
        """Исходная команда для отката: исполнена и что-то изменила, иначе отказ с причиной."""
        r = self._orig_row(row)
        why = undo_block_reason(r)
        if why:
            raise OpRefused(why)
        return r

    def undo_note(self, row):
        """★ р79 В-1: для экрана журнала — почему записи нет отката (None — откат есть)."""
        try:
            return undo_block_reason(self._orig_row(row))
        except OpRefused as ex:
            return str(ex)

    def undo_guard(self, row):
        """Откат запрещён у команд, которые не исполнены или ничего не изменили (ops.undo вызывает до undo)."""
        self._orig(row)

    def _undo_put(self, ctx, row, cmd, **kw):
        """Поставить обратную команду со ссылкой на исходную (бот восстановит ровно сделанное по её данным отката)."""
        r = self._orig(row)
        reason = ("откат записи журнала №%s: %s" % (row["id"], r["reason"]))[:REASON_MAX]
        cid = put(cmd, int(r["target_uid"]), ctx.login, reason, ref=int(r["id"]), test=bool(r["is_test"]), **kw)
        return {"before": {"cmd": int(r["id"])}, "after": {"cmd": cid, "undo_of_cmd": int(r["id"])},
                "message": "команда боту №%d поставлена (откат команды №%d): %s" % (cid, int(r["id"]), CMD_TITLES[cmd])}


@register
class AppDecide(_CmdOp):
    """Принять или отклонить заявку в тестеры (как кнопки Approve / Reject)."""
    name, title = "community.app.decide", "Сообщество: принять или отклонить заявку в тестеры"

    def _plan(self, p):
        """Проверить параметры → (решение, карточка, заявка из копии, причина)."""
        dec = str((p or {}).get("decision") or "")
        if dec not in ("approve", "reject"):
            raise OpRefused("решение — approve (принять) или reject (отклонить)")
        msg = msgid((p or {}).get("msg_id"))
        a = _app_row(msg)
        if a["status"] != "pending":
            raise OpRefused("заявка %s в копии реестра уже «%s» — решения нет" % (msg, a["status"]))
        if not a["uid"]:
            raise OpRefused("у заявки %s в реестре бота нет Discord id — решите её кнопкой в staff-chat" % msg)
        return dec, msg, a, reason_of(p)

    def target(self, p):
        """Цель журнала — карточка заявки."""
        return "discord-app:%s" % ((p or {}).get("msg_id"),)

    def preview(self, ctx, p):
        """Что сделает бот и что не откатывается."""
        dec, msg, a, reason = self._plan(p)
        if dec == "approve":
            w = ["бот выдаст роль Beta Tester, исправит карточку заявки в staff-chat, напишет игроку в личку «заявка одобрена» и строку в mod-log — "
                 "как кнопка Approve",
                 "отката личного сообщения нет: откат вернёт заявку на рассмотрение и снимет роль, выданную этим решением"]
        else:
            w = ["бот исправит карточку заявки в staff-chat и напишет строку в mod-log — как кнопка Reject, игроку бот не пишет",
                 "откат вернёт заявку на рассмотрение (кнопки Approve / Reject снова на карточке)"]
        return {"text": "%s: заявка %s от %s, участник %s, подана %s — причина: %s" % (CMD_TITLES["app_" + dec], msg, a["user_name"], _who(a["uid"]),
                                                                                          _iso(a["ts_utc"]), reason),
                "expect": {"status": a["status"]}, "warnings": _warns(p, w)}

    def apply(self, ctx, p, prev):
        """Поставить команду боту."""
        dec, msg, a, reason = self._plan(p)
        cid = self._put(ctx, p, "app_" + dec, int(a["uid"]), reason, role="beta_tester" if dec == "approve" else None, app_msg=msg)
        return {"before": {"app": str(msg), "status": "pending"}, "after": {"cmd": cid, "app": str(msg), "decision": dec, "test": _test(p)},
                "message": "команда боту №%d поставлена: %s %s" % (cid, CMD_TITLES["app_" + dec], msg)}

    def undo(self, ctx, row):
        """Откат — заявка снова на рассмотрении (app_reopen со ссылкой)."""
        r = self._orig(row)
        return self._undo_put(ctx, row, "app_reopen", app_msg=int(r["app_msg_id"]))


class _TesterOp(_CmdOp):
    """Общее для выдачи и снятия роли Beta Tester."""
    cmd = ""

    def _plan(self, p):
        """Проверить параметры → (Discord id, причина)."""
        return did((p or {}).get("uid")), reason_of(p)

    def preview(self, ctx, p):
        """Что сделает бот (по копии реестра) и что даст откат."""
        uid, reason = self._plan(p)
        has = _is_tester(uid)
        w = []
        if self.cmd == "tester_add":
            if has:
                w.append("в копии реестра у участника роль уже есть — бот ничего не изменит, откатывать будет нечего")
            w.append("откат — снять роль, выданную этой командой")
        else:
            if not has:
                w.append("в копии реестра роли у участника нет — бот роль не снимет, но одобренные заявки отклонит (и если участника уже нет на сервере)")
            w += ["как remove_tester.py: бот снимет роль и переведёт одобренные заявки участника в «отклонено» (карточки исправит)",
                  "откат — вернуть роль (только если её сняла эта команда) и прежний статус заявкам"]
        return {"text": "%s: участник %s — причина: %s" % (CMD_TITLES[self.cmd], _who(uid), reason), "expect": {"tester": has},
                "warnings": _warns(p, w)}

    def apply(self, ctx, p, prev):
        """Поставить команду боту."""
        uid, reason = self._plan(p)
        cid = self._put(ctx, p, self.cmd, uid, reason, role="beta_tester")
        return {"before": {"uid": str(uid), "tester": prev["expect"]["tester"]}, "after": {"cmd": cid, "uid": str(uid), "test": _test(p)},
                "message": "команда боту №%d поставлена: %s %d" % (cid, CMD_TITLES[self.cmd], uid)}

    def undo(self, ctx, row):
        """Откат — обратная команда со ссылкой."""
        return self._undo_put(ctx, row, "tester_remove" if self.cmd == "tester_add" else "tester_add", role="beta_tester")


@register
class TesterAdd(_TesterOp):
    """Выдать роль Beta Tester."""
    name, title, cmd = "community.tester.add", "Сообщество: выдать роль Beta Tester", "tester_add"


@register
class TesterRemove(_TesterOp):
    """Снять роль Beta Tester (как remove_tester.py)."""
    name, title, cmd = "community.tester.remove", "Сообщество: снять роль Beta Tester", "tester_remove"


@register
class WarnsClear(_CmdOp):
    """Снять предупреждения участника (как /clearwarns)."""
    name, title = "community.warns.clear", "Сообщество: снять предупреждения участника"

    def preview(self, ctx, p):
        """Сколько снимется по копии реестра; без варнов — отказ."""
        uid, reason = did((p or {}).get("uid")), reason_of(p)
        n = _warn_count(uid)
        if not n and not _test(p):
            raise OpRefused("в копии реестра у участника %d нет предупреждений — снимать нечего" % uid)
        return {"text": "снять предупреждения участника %s (в копии реестра: %d) — причина: %s" % (_who(uid), n, reason), "expect": {"warns": n},
                "warnings": _warns(p, ["как /clearwarns: бот очистит список и напишет строку в mod-log",
                                       "откат вернёт снятые предупреждения (бот хранит их в данных отката), автотаймаут при этом не ставится"])}

    def apply(self, ctx, p, prev):
        """Поставить команду боту."""
        uid, reason = did((p or {}).get("uid")), reason_of(p)
        cid = self._put(ctx, p, "warns_clear", uid, reason)
        return {"before": {"uid": str(uid), "warns": prev["expect"]["warns"]}, "after": {"cmd": cid, "uid": str(uid), "test": _test(p)},
                "message": "команда боту №%d поставлена: %s %d" % (cid, CMD_TITLES["warns_clear"], uid)}

    def undo(self, ctx, row):
        """Откат — вернуть снятые предупреждения."""
        return self._undo_put(ctx, row, "warns_restore")


def _account_of(uid, explicit):
    """Учётка игры для блока: по привязке Discord (discordlinks) или явный номер (если привязка есть — должен совпасть) → (Userindex, логин)."""
    login = _links().get(int(uid))
    found = None
    if login:
        with db.GameReader("asdastoryop") as r:
            row = r.one("SELECT Userindex, Us_id FROM dbo.Us_member WHERE Us_id = ?", (login,))
        if row:
            found = (int(row["Userindex"]), row["Us_id"].rstrip())
    if explicit in (None, ""):
        if not found:
            raise OpRefused("у участника %d нет привязки к учётке игры (playtest_accounts) — укажите номер учётки (Userindex) явно или снимите "
                            "флажок блока" % int(uid))
        return found
    try:
        ui = int(explicit)
    except (TypeError, ValueError):
        raise OpRefused("номер учётки — целое число")
    if found and found[0] != ui:
        raise OpRefused("учётка %d не совпадает с привязкой Discord (%s, номер %d)" % (ui, found[1], found[0]))
    with db.GameReader("asdastoryop") as r:
        row = r.one("SELECT Userindex, Us_id FROM dbo.Us_member WHERE Userindex = ?", (ui,))
    if not row:
        raise OpRefused("учётки %d нет" % ui)
    return int(row["Userindex"]), row["Us_id"].rstrip()


@register
class BanCheck(Operation):
    """★ р79 В-2: проверка цели ботом перед баном с блоком учётки — бот смотрит участника и свои права, в Discord ничего не меняет."""
    name, title, perm, reversible = "community.ban.check", "Сообщество: проверить цель перед баном", "community.ban", False

    def target(self, p):
        """Цель журнала — Discord id."""
        return "discord:%s" % ((p or {}).get("uid"),)

    def preview(self, ctx, p):
        """Что проверит бот."""
        uid = did((p or {}).get("uid"))
        if _is_staff(uid):
            raise OpRefused("участник %d — модератор, ушедший с сервера (список бота) — бан по id не делается" % uid)
        return {"text": "проверить участника %s перед баном: есть ли он на сервере, нет ли защищённой роли или прав модерации, ниже ли он роли бота, "
                        "есть ли у бота право банить" % _who(uid),
                "warnings": ["в Discord ничего не меняется: бот только смотрит. Итог — в очереди команд, проверка годна %d мин" % CHECK_TTL_MIN]}

    def apply(self, ctx, p, prev):
        """Поставить команду check."""
        uid = did((p or {}).get("uid"))
        r = str((p or {}).get("reason") or "").strip()
        cid = put("check", uid, ctx.login, reason_of({"reason": r}) if r else "проверка перед баном")
        return {"before": None, "after": {"cmd": cid, "uid": str(uid)}, "message": "команда боту №%d поставлена: %s %d" % (cid, CMD_TITLES["check"], uid)}


class _BanOp(_CmdOp):
    """Общее для бана и разбана: команда боту + по флажку блок / снятие блока учётки своей операцией (account.block / account.unblock)."""
    perm = "community.ban"
    cmd, chain = "", ""

    def _plan(self, ctx, p):
        """Проверить параметры → (Discord id, причина, учётка для блока или None)."""
        uid, reason = did((p or {}).get("uid")), reason_of(p)
        if self.cmd == "ban" and _is_staff(uid):
            raise OpRefused("участник %d — модератор, ушедший с сервера (список бота) — бан по id не делается" % uid)
        acc = None
        if (p or {}).get("account") and not _test(p):
            acc = _account_of(uid, (p or {}).get("block_uid"))
        return uid, reason, acc

    def _check_ok(self, uid):
        """★ р79 В-2: для бана с блоком — свежая прошедшая проверка цели, иначе отказ."""
        c = _passed_check(uid)
        if c is None:
            raise OpRefused("бан с блоком учётки — только после проверки цели ботом (годна %d мин): нажмите «Бан» ещё раз — окно бана само "
                            "запустит проверку, или поставьте операцию community.ban.check и дождитесь «проверка прошла»" % CHECK_TTL_MIN)
        return c

    def _chain_params(self, acc, p, cid):
        """Параметры account.block / account.unblock."""
        if self.chain == "account.block":
            hours = (p or {}).get("hours")
            return {"uid": acc[0], "hours": -1 if hours in (None, "") else hours,
                    "reason": ("Discord ban #%s (panel community.ban)" % cid) if cid else "Discord ban (panel community.ban)"}
        return {"uid": acc[0]}

    def preview(self, ctx, p):
        """Что сделает бот, что не откатывается, и (по флажку) предпросмотр блока / снятия блока."""
        uid, reason, acc = self._plan(ctx, p)
        banned = _is_banned(uid)
        w = []
        if self.cmd == "ban":
            if banned:
                w.append("в копии реестра бан уже стоит — бот ничего не изменит, откатывать будет нечего")
            w += BAN_WARN
            if not _in_guild_hint(uid):
                w.append("участника может не быть на сервере: тогда бот банит по id — защищённость проверяется только по списку известных "
                         "модераторов из снимка")
            w.append("откат — разбан (только если бан поставила эта команда), блок учётки снимается откатом своей записи журнала account.block")
        else:
            if not banned:
                w.append("в копии реестра бана нет — бот ничего не изменит, откатывать будет нечего")
            w += ["разбан не возвращает роли и участие: участник заходит заново по приглашению и проходит онбординг",
                  "откат — бан (только если бан сняла эта команда)"]
        text = "%s: участник %s — причина: %s" % (CMD_TITLES[self.cmd], _who(uid), reason)
        out = {"expect": {"banned": banned}}
        if acc:
            if self.cmd == "ban":
                c = self._check_ok(uid)
                w.insert(0, "проверка цели №%d прошла %s UTC: %s" % (c["id"], _iso(c["done_utc"]), c["result"] or ""))
            op = ops.REGISTRY[self.chain]
            if not ctx.can(op.perm):
                raise OpRefused("%s — нужно право «%s»" % (self.chain, op.perm))
            cp = op.preview(ctx, self._chain_params(acc, p, None))
            w.insert(0, "и %s для учётки %s — %s" % (self.chain, acc[1], cp["text"]))
            w += cp.get("warnings") or []
            w.append("%s пишется отдельной записью журнала сразу, команда боту уходит после неё" % self.chain)
            if self.cmd == "ban":
                w.append("если бан всё же не выполнится (бот откажет, ошибка Discord, просрочка или отмена) — блок сам не снимется: на этой странице "
                         "появится предупреждение «учётка заблокирована, бана в Discord нет» и кнопка «Снять блок»")
            out["expect"]["account"] = cp.get("expect")
        elif (p or {}).get("account") and _test(p):
            w.append("проверочная команда: учётка игры не блокируется и не разблокируется")
        out.update(text=text, warnings=_warns(p, w))
        return out

    def apply(self, ctx, p, prev):
        """Команда «ждёт блока» → блок своей записью журнала → команда боту с номером записи. Сбой блока — команда отменена, в Discord ничего."""
        uid, reason, acc = self._plan(ctx, p)
        if acc and self.cmd == "ban":
            self._check_ok(uid)
        cid = put(self.cmd, uid, ctx.login, reason, block_uid=acc[0] if acc else None, hold=bool(acc), test=_test(p))
        aid = None
        if acc:
            op = ops.REGISTRY[self.chain]
            cp = self._chain_params(acc, p, cid)
            try:
                if not ctx.can(op.perm):
                    raise OpRefused("%s — нужно право «%s»" % (self.chain, op.perm))
                cprev = op.preview(ctx, cp)
                if cprev.get("expect") != (prev.get("expect") or {}).get("account"):
                    raise OpRefused("пока вы смотрели предпросмотр, блок учётки изменился — повторите")
                res = op.apply(ctx, cp, cprev)
                aid = ops._finish(ctx, op.name, op.target(cp), cp, res, undo_of=None)
            except BaseException as ex:
                try:
                    release(cid, False, ctx.login, "%s не выполнен: %s" % (self.chain, str(ex)[:300]))
                except OpRefused:
                    pass
                raise
            try:
                op.verify(ctx, cp, res)
            except Exception as ex:                # ★ р79 М-9: как ops.run — запись «error» со ссылкой на запись журнала, пометка команды с номером
                audit.write(ctx, op.name, op.target(cp), cp, result="error", message="проверка после записи №%s: %s" % (aid, str(ex)[:500]))
                try:
                    release(cid, False, ctx.login, "%s: блок не удержался (запись журнала №%s)" % (self.chain, aid))
                except OpRefused:
                    pass
                raise OpRefused("%s: блок не удержался (запись журнала №%s) — команда боту отменена, в Discord ничего не ушло" % (self.chain, aid))
            if release(cid, True, ctx.login, block_audit=aid) != 1:
                raise OpRefused("команда №%d изменилась до отправки боту (её отменили?) — %s уже записан журналом №%d, откатите его при "
                                "необходимости" % (cid, self.chain, aid))
        if aid:
            msg = "команда боту №%d поставлена: %s %d · %s — запись журнала №%d" % (cid, CMD_TITLES[self.cmd], uid, self.chain, aid)
        else:
            msg = "команда боту №%d поставлена: %s %d" % (cid, CMD_TITLES[self.cmd], uid)
        return {"before": {"uid": str(uid), "banned": prev["expect"]["banned"]},
                "after": {"cmd": cid, "uid": str(uid), "block_audit": aid, "account": acc[0] if acc else None, "test": _test(p)}, "message": msg}

    def undo(self, ctx, row):
        """Откат — обратная команда (бот исполнит её, только если исходная что-то изменила); блок — своей записью журнала."""
        out = self._undo_put(ctx, row, "unban" if self.cmd == "ban" else "ban")
        a = json.loads(row.get("after_json") or "{}")
        if a.get("block_audit"):
            out["message"] = ("команда боту №%d поставлена (откат команды №%d): %s · %s снимается откатом записи журнала №%s"
                              % (out["after"]["cmd"], out["after"]["undo_of_cmd"], CMD_TITLES["unban" if self.cmd == "ban" else "ban"], self.chain,
                                 a["block_audit"]))
        return out


@register
class Ban(_BanOp):
    """Бан сервера Discord (и по флажку блок учётки игры)."""
    name, title, cmd, chain = "community.ban", "Сообщество: бан Discord (и блок учётки)", "ban", "account.block"


@register
class Unban(_BanOp):
    """Разбан сервера Discord (и по флажку снятие блока учётки)."""
    name, title, cmd, chain = "community.unban", "Сообщество: разбан Discord (и снятие блока учётки)", "unban", "account.unblock"


class _QueueOp(Operation):
    """Общее для отмены и повтора: номер команды, процедура базы; ★ р79 М-4 — у бана и разбана ещё и право community.ban."""
    perm, reversible, proc = "community.manage", False, ""

    def target(self, p):
        """Цель журнала — номер команды."""
        return "botcmd:%s" % ((p or {}).get("id"),)

    def _cid(self, p):
        """Номер команды из параметров."""
        try:
            v = int((p or {}).get("id"))
        except (TypeError, ValueError):
            raise OpRefused("номер команды — целое от 1")
        if v < 1 or v > 2 ** 31 - 1:
            raise OpRefused("номер команды — целое от 1")
        return v

    def _rights(self, ctx, r, retry):
        """★ р79 М-4: бан и разбан — только с community.ban; повтор бана с блоком учётки — ещё и с players.block."""
        if r["cmd"] in BAN_CMDS and not ctx.can("community.ban"):
            raise OpRefused("команда №%d — %s: нужно право «community.ban»" % (r["id"], CMD_TITLES[r["cmd"]]))
        if retry and r["cmd"] == "ban" and r["block_uid"] and not ctx.can("players.block"):
            raise OpRefused("команда №%d — бан с блоком учётки: нужно право «players.block»" % r["id"])

    def _tx(self, args, fail):
        """Вызов процедуры (одна строка изменена — иначе отказ)."""
        n = int(_read(lambda c: db.admin_rows(c, "SET NOCOUNT ON; EXEC %s %s" % (self.proc, ", ".join("?" * len(args))), args))[0]["n"])
        if n != 1:
            raise OpRefused(fail)


@register
class CmdCancel(_QueueOp):
    """Отменить команду до исполнения."""
    name, title, proc = "community.cmd.cancel", "Сообщество: отменить команду боту", "adm.BotCmdCancel"

    def preview(self, ctx, p):
        """Можно ли отменить и что останется (блок учётки)."""
        r, now = cmd_row(self._cid(p))
        self._rights(ctx, r, False)
        if int(r["status"]) not in (0, 7):
            raise OpRefused("команда №%d уже не ждёт бота (%s) — отменить нельзя" % (r["id"], _state(r, now)))
        w = ["пишется только база панели AsdaAdmin (adm.BotCmd): статус «отменено»"]
        if r["block_audit"]:
            w.append("блок учётки уже стоит (запись журнала №%d) — отмена команды его не снимает, откатите ту запись" % r["block_audit"])
        return {"text": "отменить команду боту №%d (%s, участник %d)" % (r["id"], CMD_TITLES.get(r["cmd"], r["cmd"]), r["target_uid"]),
                "expect": {"status": int(r["status"])}, "warnings": w}

    def apply(self, ctx, p, prev):
        """Отменить (права проверяются заново)."""
        cid = self._cid(p)
        self._rights(ctx, cmd_row(cid)[0], False)
        self._tx((cid, ctx.login[:32]), "команда №%d уже взята ботом или изменилась — откройте очередь заново" % cid)
        return {"before": {"id": cid, "status": prev["expect"]["status"]}, "after": {"id": cid, "status": 4},
                "message": "команда боту №%d отменена" % cid}


@register
class CmdRetry(_QueueOp):
    """Повторить команду после ошибки или «итог неизвестен»."""
    name, title, proc = "community.cmd.retry", "Сообщество: повторить команду боту", "adm.BotCmdRetry"

    def preview(self, ctx, p):
        """Можно ли повторить (статус, попытки, срок, права)."""
        r, now = cmd_row(self._cid(p))
        self._rights(ctx, r, True)
        st = _state(r, now)
        if st not in ("failed", "unknown"):
            raise OpRefused("команда №%d не в ошибке и не «итог неизвестен» (%s) — повторять нечего" % (r["id"], st))
        if r["attempts"] >= MAX_ATTEMPTS:
            raise OpRefused("у команды №%d уже %d попыток — больше нельзя, поставьте её заново" % (r["id"], r["attempts"]))
        if r["expires_utc"] <= now:
            raise OpRefused("срок команды №%d прошёл — поставьте её заново" % r["id"])
        return {"text": "повторить команду боту №%d (%s, попытка %d из %d)" % (r["id"], CMD_TITLES.get(r["cmd"], r["cmd"]), r["attempts"] + 1,
                                                                               MAX_ATTEMPTS),
                "expect": {"status": int(r["status"])},
                "warnings": ["бот проверяет текущее состояние: уже выданную роль, бан или решённую заявку второй раз не меняет, второе личное "
                             "сообщение не шлёт (журнал бота на ПК)"]}

    def apply(self, ctx, p, prev):
        """Повторить (права проверяются заново)."""
        cid = self._cid(p)
        self._rights(ctx, cmd_row(cid)[0], True)
        self._tx((cid, ctx.login[:32], STUCK_MIN), "команду №%d уже нельзя повторить (статус, срок или попытки изменились) — откройте очередь заново" % cid)
        return {"before": {"id": cid, "status": prev["expect"]["status"]}, "after": {"id": cid, "status": 0},
                "message": "команда боту №%d поставлена на повтор" % cid}


@register
class CmdTest(Operation):
    """Проверочная команда: бот забирает её тем же путём и отмечает «тест», Discord не вызывает (community_bot: is_test — без Discord)."""
    name, title, perm, reversible = "community.test", "Сообщество: проверочная команда (бот не исполняет)", "community.manage", False

    def target(self, p):
        """Цель журнала."""
        return "botcmd:test"

    def preview(self, ctx, p):
        """Что произойдёт."""
        return {"text": "поставить проверочную команду боту — бот её заберёт и отметит «тест», в Discord ничего не изменится",
                "warnings": ["пишется только база панели AsdaAdmin (adm.BotCmd, команда с отметкой «тест»)"]}

    def apply(self, ctx, p, prev):
        """Поставить проверочную команду."""
        cid = put("test", 0, ctx.login, "проверка пути команд боту", test=True)
        return {"before": None, "after": {"id": cid, "cmd": cid, "test": True}, "message": "проверочная команда боту №%d поставлена" % cid}
