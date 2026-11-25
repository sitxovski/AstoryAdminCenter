# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""clan.py — клан: состав (чтение), исключить, сменить главу, распустить, сбросить эмблему, объявления (волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_clan.md (живые тексты процедур Joy1 сняты 18.11). Таблицы: ClanData (карточка, эмблема —
6 чисел MarkFlag/Markidx/MarkColor/MarkBorder/MarkBdColor/MarkBgColor), ClanMember (Grade: 1 глава, 2 зам., 4 бывший глава, 5 принят,
10 заявка), ClanNotice (доска, ≤ 5), CampClanData (очки лагеря), CampOwnerData.MvpClanIndex.
GameServer держит КЭШ ClanData (CThreadManager, 10 001 слот; перечитывает при входе ЛЮБОГО члена — charLogonCommunityRes_0
@0x5285F0 → DBM 2172 UpClaninfo) и блоб клана у каждого онлайн-персонажа; права главы и полный слот (UPClanUpdate) пишутся ИЗ КЭША.
Поэтому исключение, смена главы, роспуск и сброс эмблемы — только когда ВСЕ члены клана не в игре (_require_offline под блокировкой
в транзакции записи, по учётке — строже стока: учётка члена не должна быть в мире ни одним персонажем). Состав и доска читаются
сервером живьём (DBM 2175 / 2502) — объявления можно и при членах в игре (решение владельца 18.11).
ОПЕРАЦИИ (решения владельца 18.11):
  clan.kick         — как UPClanSecede: строка члена удаляется, JoinCnt − 1; заявка (Grade 10) — как UPClanWaitCancel, без JoinCnt;
                      главу нельзя (сначала сменить главу); JoinCnt не ниже 1;
  clan.captain      — как UPClanOwnerTransfer: ClanData.Captain/Capuserindex/CapCharidx = новый (имя — Charinfo.Charname), старый
                      глава Grade 4, новый Grade 1; новый — член клана с Grade < 10;
  clan.disband      — как UPClanBreakUp, но при любом JoinCnt: ClanMember, ClanData, CampClanData + ClanNotice (ИСПРАВЛЕНИЕ ДЕФЕКТА
                      ОРИГИНАЛА: сток оставляет объявления-сироты) + CampOwnerData.MvpClanIndex → −1, где MVP — этот клан
                      (решение владельца; −1 — «нет MVP», как читает UPCampOwner);
  clan.mark_reset   — 6 чисел эмблемы → 0 (так у живых кланов без эмблемы); предмет-эмблема, съеденный UPClanMarkUpdate, не
                      возвращается;
  clan.notice_add   — как UPClanNoticeUp: при 5 записях удаляется самая старая (меньший idx); автор ≤ 20 байт, текст ≤ 500 байт cp1251;
  clan.notice_delete — как UPClanNoticeDel.
ЖУРНАЛ — JoyLog1.dbo.ClanLog (как пишут UPClanBreakUp / UPClanMarkUpdate: Edate, Userindex, Charidx, Clanidx, Cname ≤ 16, Gm 0,
State) с пометкой «Panel …»; плюс журнал панели. Откат объявлений и роспуска возвращает объявления с НОВЫМ номером (IDENTITY_INSERT
требует ALTER — у asda_ops его нет), как pets.py.
Побочных эффектов при импорте нет.
"""
from core import db
from core.ops import OpRefused, register
from domains import items, social

OPERATOR_MAX_UID = 5000
NOTICE_MAX = 5
MARK = ("MarkFlag", "Markidx", "MarkColor", "MarkBorder", "MarkBdColor", "MarkBgColor")
LOGC = ["Edate", "Userindex", "Charidx", "Clanidx", "Cname", "Gm", "State"]


def _require_offline(w, uids, lock):
    """Все члены клана не в игре. ЕДИНАЯ точка раздела: онлайн-путь (мост AdminBridge, волна А2) подключается здесь."""
    social.offline(w, uids, lock, lambda u, why: "клан правится, только когда все члены клана не в игре: учётка %d — %s" % (u, why))


def _require_offline_undo(w, uids, lock):
    social.offline(w, uids, lock, lambda u, why: "откат только когда учётки не в игре: учётка %d — %s" % (u, why))


def _no_offline(w, uids, lock):
    """Объявления — без проверки «не в игре» (доску сервер читает живьём, решение владельца 18.11)."""
    return None


def _cid(p):
    try:
        c = int(p["clan"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры клана")
    return c


def _clan(w, c, lock):
    r = social.read(w, "ClanData", "Clanidx = ?", (c,), lock)
    if not r:
        raise OpRefused("клана %d нет" % c)
    return r[0]


def _members(w, c, lock):
    return social.read(w, "ClanMember", "Clanidx = ?", (c,), lock)


def _service(role, uids):
    if role != "owner" and any(u <= OPERATOR_MAX_UID for u in uids):
        raise OpRefused("в клане служебные учётки (номер ≤ %d) — правит только владелец" % OPERATOR_MAX_UID)


def _log(c, uid, idx, cname_hex, state):
    return ["ClanLog", LOGC, [social.NOW, uid, idx, c, ("hex", (cname_hex or "")[:32], 16), 0, state]]


def _name(d):
    return social.hex_text(d["Cname"])


def plan_kick(w, p, lock=False, role=None):
    c = _cid(p)
    try:
        u, i = int(p["uid"]), int(p["idx"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры клана")
    d = _clan(w, c, lock)
    mem = _members(w, c, lock)
    _service(role, [m["Userindex"] for m in mem])
    m = next((x for x in mem if x["Userindex"] == u and x["Charidx"] == i), None)
    if not m:
        raise OpRefused("персонажа %d/%d нет в клане %d" % (u, i, c))
    if m["Grade"] == 1 or (d["Capuserindex"], d["CapCharidx"]) == (u, i):
        raise OpRefused("главу клана исключить нельзя — сначала смените главу")
    changes = [["ClanMember", m, None]]
    wait = m["Grade"] == 10
    if not wait:
        if d["JoinCnt"] <= 1:
            raise OpRefused("в клане по счётчику JoinCnt один член — исключение увело бы его ниже 1")
        changes.append(["ClanData", d, dict(d, JoinCnt=d["JoinCnt"] - 1)])
    text = "исключить из клана %s (%d): %s (%d/%d, ступень %d)%s" % (_name(d), c, social.hex_text(m["Charname"]), u, i, m["Grade"],
                                                                    " — заявка, счётчик не меняется" if wait else ", членов %d → %d" % (d["JoinCnt"], d["JoinCnt"] - 1))
    return {"uids": [x["Userindex"] for x in mem], "changes": changes, "text": text,
            "warn": ["права и состав онлайн-игроков обновятся при их входе (сервер перечитывает клан при входе любого члена)"],
            "logs": [_log(c, u, i, d["Cname"], "Panel Member Secede")], "ulogs": [_log(c, u, i, d["Cname"], "Panel Undo Member Secede")]}


def plan_captain(w, p, lock=False, role=None):
    c = _cid(p)
    try:
        u, i = int(p["uid"]), int(p["idx"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры клана")
    d = _clan(w, c, lock)
    mem = _members(w, c, lock)
    _service(role, [m["Userindex"] for m in mem])
    new = next((x for x in mem if x["Userindex"] == u and x["Charidx"] == i), None)
    if not new:
        raise OpRefused("персонажа %d/%d нет в клане %d" % (u, i, c))
    if new["Grade"] >= 10:
        raise OpRefused("новый глава должен быть членом клана, а не заявкой (Grade 10)")
    if (d["Capuserindex"], d["CapCharidx"]) == (u, i):
        raise OpRefused("персонаж уже глава клана")
    old = next((x for x in mem if x["Userindex"] == d["Capuserindex"] and x["Charidx"] == d["CapCharidx"]), None)
    if not old:
        raise OpRefused("глава из ClanData (%d/%d) не числится в составе — панель такое не правит" % (d["Capuserindex"], d["CapCharidx"]))
    nm = w.rows("SELECT CONVERT(varchar(60), CAST(Charname AS varbinary(20)), 2) AS h FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?"
                % (" WITH (UPDLOCK, HOLDLOCK)" if lock else ""), (u, i))
    if not nm:
        raise OpRefused("персонажа %d/%d нет" % (u, i))
    changes = [["ClanData", d, dict(d, Captain=nm[0]["h"], Capuserindex=u, CapCharidx=i)],
               ["ClanMember", old, dict(old, Grade=4)], ["ClanMember", new, dict(new, Grade=1)]]
    text = "сменить главу клана %s (%d): %s (%d/%d) → %s (%d/%d)" % (_name(d), c, social.hex_text(d["Captain"]), d["Capuserindex"],
                                                                    d["CapCharidx"], social.hex_text(nm[0]["h"]), u, i)
    warn = ["прежний глава получает ступень 4, как при передаче в игре"]
    if new["Grade"] == 2:
        warn.append("новый глава был заместителем — место заместителя освобождается")
    return {"uids": [x["Userindex"] for x in mem], "changes": changes, "text": text, "warn": warn,
            "logs": [_log(c, u, i, d["Cname"], "Panel Owner Transfer")],
            "ulogs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Undo Owner Transfer")]}


def plan_disband(w, p, lock=False, role=None):
    c = _cid(p)
    d = _clan(w, c, lock)
    mem = _members(w, c, lock)
    _service(role, [m["Userindex"] for m in mem])
    refs = w.rows("SELECT Clanidx FROM dbo.ClanData WHERE Clanidx <> ? AND (Aidx1 = ? OR Aidx2 = ? OR Aidx3 = ? OR Waridx = ?)",
                  (c, c, c, c, c))
    if refs:                                           # перепроверка 23 М3: союз / война других кланов (решение владельца: отказ со списком)
        raise OpRefused("на клан %d ссылаются другие кланы (союз или война): %s — роспуск не выполнен"
                        % (c, ", ".join(str(r["Clanidx"]) for r in refs)))
    notes = social.read(w, "ClanNotice", "Clanidx = ?", (c,), lock)
    camp = social.read(w, "CampClanData", "ClanIndex = ?", (c,), lock)
    mvp = social.read(w, "CampOwnerData", "MvpClanIndex = ?", (c,), lock)
    changes = ([["ClanMember", m, None] for m in mem] + [["ClanNotice", n, None] for n in notes] + [["CampClanData", x, None] for x in camp]
               + [["CampOwnerData", x, dict(x, MvpClanIndex=-1)] for x in mvp] + [["ClanData", d, None]])
    text = "распустить клан %s (%d): членов %d, объявлений %d, строк лагеря %d%s" % (
        _name(d), c, len(mem), len(notes), len(camp), (", снять MVP лагеря %s" % ", ".join(str(x["CampType"]) for x in mvp)) if mvp else "")
    warn = ["деньги за создание клана не возвращаются (у сервера тоже)"]
    if notes:
        warn.append("объявления удаляются вместе с кланом — исправление дефекта оригинала (сток оставлял их без клана)")
    if mvp:
        warn.append("клан был MVP лагеря — MVP снимается (−1), лагерь останется без MVP до пересчёта")
    warn.append("слот клана в памяти GameServer останется до рестарта или до нового клана с этим номером — игрокам не виден")
    return {"uids": [m["Userindex"] for m in mem], "changes": changes, "text": text, "warn": warn,
            "logs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Clan Break Up")],
            "ulogs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Undo Clan Break Up")]}


def plan_mark_reset(w, p, lock=False, role=None):
    c = _cid(p)
    d = _clan(w, c, lock)
    mem = _members(w, c, lock)
    _service(role, [m["Userindex"] for m in mem])
    if all((d[k] or 0) == 0 for k in MARK):
        raise OpRefused("эмблемы у клана нет")
    text = "сбросить эмблему клана %s (%d): %s → 0" % (_name(d), c, "/".join(str(d[k]) for k in MARK))
    return {"uids": [m["Userindex"] for m in mem], "changes": [["ClanData", d, dict(d, **{k: 0 for k in MARK})]], "text": text,
            "warn": ["предмет-эмблема, израсходованный при установке, не возвращается"],
            "logs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Crest Reset")],
            "ulogs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Undo Crest Reset")]}


def plan_notice_add(w, p, lock=False, role=None):
    c = _cid(p)
    d = _clan(w, c, lock)
    _service(role, [m["Userindex"] for m in _members(w, c, False)])     # перепроверка 23 К1
    body = social.text_hex(p.get("text"), 500, "notice")
    author = social.text_hex(p.get("author"), 20, "author")
    notes = sorted(social.read(w, "ClanNotice", "Clanidx = ?", (c,), lock), key=lambda n: n["idx"])
    if len(notes) > NOTICE_MAX:
        raise OpRefused("у клана %d объявлений — больше 5, как сервер не допускает; сначала удалите лишние" % len(notes))
    changes, warn = [], ["у игроков с открытой доской список обновится при следующем открытии"]
    if len(notes) == NOTICE_MAX:
        changes.append(["ClanNotice", notes[0], None])
        warn.append("на доске уже 5 объявлений — самое старое (%d) удаляется, как у сервера" % notes[0]["idx"])
    changes.append(["ClanNotice", None, {"Clanidx": c, "idx": social.NEW, "Charname": author, "Edate": social.NOW, "Notice": body}])
    text = "объявление клана %s (%d) от %s: %s" % (_name(d), c, social.hex_text(author), social.hex_text(body)[:120])
    return {"uids": [], "changes": changes, "text": text, "warn": warn,
            "logs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Notice Add")],
            "ulogs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Undo Notice Add")]}


def plan_notice_delete(w, p, lock=False, role=None):
    c = _cid(p)
    try:
        n = int(p["notice"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры клана")
    d = _clan(w, c, lock)
    _service(role, [m["Userindex"] for m in _members(w, c, False)])     # перепроверка 23 К1
    r = social.read(w, "ClanNotice", "Clanidx = ? AND idx = ?", (c, n), lock)
    if not r:
        raise OpRefused("объявления %d у клана нет" % n)
    text = "удалить объявление %d клана %s (%d): %s" % (n, _name(d), c, social.hex_text(r[0]["Notice"])[:120])
    return {"uids": [], "changes": [["ClanNotice", r[0], None]], "text": text,
            "warn": ["откат вернёт объявление с новым номером"],
            "logs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Notice Del")],
            "ulogs": [_log(c, d["Capuserindex"], d["CapCharidx"], d["Cname"], "Panel Undo Notice Del")]}


def _undo_uids(w, a):
    """При откате держать и тех, кто сейчас в клане (состав мог измениться), и тех, кто был."""
    us = set(a.get("uids") or [])
    cl = {x[1]["Clanidx"] for x in a.get("changes") or [] if x[0] in ("ClanData", "ClanMember") and x[1]}
    for c in cl:
        us |= {int(r["Userindex"]) for r in w.rows("SELECT Userindex FROM dbo.ClanMember WHERE Clanidx = ?", (c,))}
    return sorted(us)


def _undo_check(w, a):
    """Возвращаемые члены не состоят в другом клане; возвращаемый клан — номер и имя свободны."""
    for t, b, af in a.get("changes") or []:
        if t == "ClanMember" and b and af is None:
            if w.rows("SELECT TOP 1 Clanidx FROM dbo.ClanMember WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ?",
                      (b["Userindex"], b["Charidx"])):
                raise OpRefused("персонаж %d/%d с тех пор в клане — откат не выполнен" % (b["Userindex"], b["Charidx"]))
        if t == "ClanData" and b and af is None:
            if w.rows("SELECT TOP 1 Clanidx FROM dbo.ClanData WITH (UPDLOCK, HOLDLOCK) WHERE Clanidx = ? OR "
                      "Cname = CONVERT(varchar(17), CONVERT(varbinary(17), ?, 2))", (b["Clanidx"], b["Cname"])):
                raise OpRefused("номер или имя клана с тех пор заняты — откат не выполнен")


class _ClanOp(social.SocialOp):
    perm = "players.clan"
    require_offline = staticmethod(_require_offline)
    undo_offline = staticmethod(_require_offline_undo)
    undo_uids = staticmethod(_undo_uids)
    undo_check = staticmethod(_undo_check)

    def target(self, p):
        return "clan:%s" % p.get("clan")


@register
class ClanKick(_ClanOp):
    name, title = "clan.kick", "Клан: исключить члена"
    planner = staticmethod(plan_kick)


@register
class ClanCaptain(_ClanOp):
    name, title = "clan.captain", "Клан: сменить главу"
    planner = staticmethod(plan_captain)


@register
class ClanDisband(_ClanOp):
    name, title = "clan.disband", "Клан: распустить"
    planner = staticmethod(plan_disband)


@register
class ClanMarkReset(_ClanOp):
    name, title = "clan.mark_reset", "Клан: сбросить эмблему"
    planner = staticmethod(plan_mark_reset)


@register
class ClanNoticeAdd(_ClanOp):
    name, title = "clan.notice_add", "Клан: добавить объявление"
    planner = staticmethod(plan_notice_add)
    require_offline = staticmethod(_no_offline)
    undo_offline = staticmethod(_no_offline)


@register
class ClanNoticeDelete(_ClanOp):
    name, title = "clan.notice_delete", "Клан: удалить объявление"
    planner = staticmethod(plan_notice_delete)
    require_offline = staticmethod(_no_offline)
    undo_offline = staticmethod(_no_offline)


def search(q):
    """Кланы по номеру или части имени (до 50)."""
    q = (q or "").strip()
    with db.GameReader("joy1") as r:
        if q.isdigit():
            rows = r.rows("SELECT TOP 50 Clanidx, Cname, Captain, JoinCnt, Maxcnt FROM dbo.ClanData WHERE Clanidx = ?", (int(q),))
        elif q:
            rows = r.rows("SELECT TOP 50 Clanidx, Cname, Captain, JoinCnt, Maxcnt FROM dbo.ClanData WHERE Cname LIKE ? ORDER BY Clanidx",
                          ("%" + r.text(q).replace("[", "[[]").replace("%", "[%]").replace("_", "[_]") + "%",))
        else:
            rows = r.rows("SELECT TOP 50 Clanidx, Cname, Captain, JoinCnt, Maxcnt FROM dbo.ClanData ORDER BY Clanidx")
    return rows


def describe(c):
    """Окно клана: карточка, состав (уровень, профессия, в игре), объявления, лагерь, MVP."""
    c = int(c)
    with db.GameReader("joy1") as r:
        d = r.rows("SELECT Clanidx, Cname, Ctype, Captain, Capuserindex, CapCharidx, Maxcnt, JoinCnt, Maxgrade, State, Lvl, TotActPoint, "
                   "UseActPoint, %s FROM dbo.ClanData WHERE Clanidx = ?" % ", ".join(MARK), (c,))
        if not d:
            raise OpRefused("клана %d нет" % c)
        mem = r.rows("SELECT m.Userindex, m.Charidx, m.Charname, m.Grade, m.DonationPoint, m.Callname, i.Lvl, i.Job, i.Subjob, "
                     "CASE WHEN EXISTS (SELECT 1 FROM dbo.CharPos p WHERE p.Userindex = m.Userindex AND p.UserNum <> -1) THEN 1 ELSE 0 END AS online "
                     "FROM dbo.ClanMember m LEFT JOIN dbo.Charinfo i ON i.Userindex = m.Userindex AND i.Charidx = m.Charidx "
                     "WHERE m.Clanidx = ? ORDER BY m.Grade, m.Charname", (c,))
        notes = r.rows("SELECT idx, Charname, CONVERT(varchar(16), Edate, 120) AS Edate, Notice FROM dbo.ClanNotice WHERE Clanidx = ? ORDER BY idx DESC",
                       (c,))
        camp = r.rows("SELECT CampType, EnterPoint0, EnterPoint1, EnterPoint2 FROM dbo.CampClanData WHERE ClanIndex = ?", (c,))
        mvp = r.rows("SELECT CampType FROM dbo.CampOwnerData WHERE MvpClanIndex = ?", (c,))
    out = dict(d[0])
    out.update({"members": mem, "notices": notes, "camp": camp, "mvp": [x["CampType"] for x in mvp],
                "online": sum(1 for m in mem if m["online"]), "notice_max": NOTICE_MAX})
    return out
