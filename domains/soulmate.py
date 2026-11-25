# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""soulmate.py — соулмейт (Друг) учёток НЕ В ИГРЕ: разорвать, связать, уровень, дружба пары, сверка Share (волна А1, план §4.Б).
18.11.2026.

РАЗБОР — Reports/admin_center/research_soulmate_friends.md (живые тексты процедур Joy1 сняты 18.11). Связь — на УЧЁТКУ:
две зеркальные строки dbo.SoulMate с одним Smidx (State 1 — активна, 0 — история, не больше 3 строк на учётку).
РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11:
  soulmate.break      — как UPSoulMateBreak: State 0 обеих строк, Charinfo.Share = 0 у ВСЕХ персонажей обеих учёток, кристаллы
                        опыта Друга (Item.Code 21097…21106, Owner = 1) обеих учёток удаляются — через adm.ItemTake (снимок, откат);
                        журнал JoyLog1.SoulMate «Panel Breakup» (сток пишет «SoulMate Breakup»);
  soulmate.link       — связать ЛЮБЫЕ две учётки, как сервер при согласии обоих (UPSoulMateOk): обе строки пары в истории — State 1,
                        Regdate = сейчас (уровень, опыт, дружба прежней пары возвращаются); строка только у одной — вторая вставляется
                        с теми же SmLvl/SmExp/FriendShip/Apple*/FinalDate («Active-OneSide»); иначе новый Smidx из пула SoulMateIdx
                        (наименьший свободный — сток берёт TOP 1 без ORDER BY), обе строки SmLvl 1, SmExp 0, FriendShip 0, info 1.
                        История > 2 строк — самая старая строка State 0 этой учётки удаляется (как сток). Журнал JoyLog1.SoulMate
                        «Panel Birth» / «Panel Active-OneSide» / «Panel Restore» (у стока при восстановлении журнала нет — отличие);
  soulmate.level      — SmLvl = L обеих строк, SmExp = опыт начала уровня L по ConfigSet\\SoulMateExpTable.txt (запись L, как
                        sub_4AF060; повышение — newExp ≥ записи L+1, GameServer.c:79774; уровни 1…30 — дальше сервер не растит,
                        :79757); журнал JoyLog1.SoulMateLevelUp (столбца пометки у таблицы нет — строка как у UPSmLevelUp);
  soulmate.friendship — FriendShip обеих строк, FinalDate = NULL (иначе UPCharSoulMate при входе спишет затухание); 0…255 (байт
                        CUser+99095; предела в GameServer не найдено); журнал JoyLog1.SoulMateinfo «FriendShip-Panel»;
  soulmate.share_fix  — сверка S5: Share = 0 у персонажей учёток без активной связи (на живых данных НЕ применять — владелец).
Обе учётки пары — не в игре (_require_offline под блокировкой): уровень/опыт/дружбу пишет GameServer из памяти по Smidx
(Recv_BattleServerFromCharParamExp :79774, DisConnectUser → UPSmFriendShipUp), правка при партнёре в игре была бы перезаписана.
ЗАПИСЬ — asda_ops, одна транзакция; откат — строки «стало → было», если с тех пор не менялись (domains/social.py).
Побочных эффектов при импорте нет.
"""
from core import db
from core.ops import OpRefused, register
from domains import itemgive, items, social, srvtables

CRYSTALS = (21097, 21106)
OPERATOR_MAX_UID = 5000
HISTORY_MAX = 3
LEVEL_TOP = 30                    # sub_532730(...) < 0x1E — выше 30 сервер уровень связи не поднимает (GameServer.c:79757)


def _require_offline(w, uids, lock):
    """Обе учётки пары не в игре. ЕДИНАЯ точка раздела: онлайн-путь (мост AdminBridge, волна А2) подключается здесь."""
    social.offline(w, uids, lock, lambda u, why: "соулмейт правится, только когда обе учётки пары не в игре: учётка %d — %s" % (u, why))


def _require_offline_undo(w, uids, lock):
    social.offline(w, uids, lock, lambda u, why: "откат только когда учётки не в игре: учётка %d — %s" % (u, why))


def exp_table():
    """{уровень: опыт начала уровня} — ConfigSet\\SoulMateExpTable.txt как sub_4AF060: первое число — записей, далее пары
    «уровень опыт»; уровень = номер записи (по нему и сравнивает сервер), опыт — _atoi64."""
    import re
    toks = srvtables._cfg_text("SoulMateExpTable.txt").split()
    n, out = srvtables._atol(toks[0]) if toks else 0, {}
    for i in range(1, n + 1):
        rec = toks[2 * i - 1: 2 * i + 1]
        if len(rec) != 2:
            break
        m = re.match(r"\s*([+-]?\d+)", rec[1])
        out[i] = int(m.group(1)) if m else 0
    return out


def _uid(p, k="uid"):
    try:
        return int(p[k])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры соулмейта")


def _service(role, *uids):
    if role != "owner" and any(u <= OPERATOR_MAX_UID for u in uids):
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)


def _pair(w, uid, lock):
    """Активная пара учётки → (Smidx, партнёр, [строка учётки, строка партнёра])."""
    act = social.read(w, "SoulMate", "Userindex = ? AND State = 1", (uid,), lock)
    if not act:
        raise OpRefused("у учётки %d нет активной связи соулмейта" % uid)
    if len(act) > 1:
        raise OpRefused("у учётки %d несколько активных связей — панель такое не правит" % uid)
    sm, mate = act[0]["Smidx"], act[0]["Ouserindex"]
    rows = social.read(w, "SoulMate", "Smidx = ?", (sm,), lock)
    mine = [r for r in rows if r["Userindex"] == uid]
    other = [r for r in rows if r["Userindex"] == mate]
    if len(rows) != 2 or len(mine) != 1 or len(other) != 1 or other[0]["Ouserindex"] != uid or other[0]["State"] != 1:
        raise OpRefused("строки пары %d несогласованы (нужны две зеркальные активные строки) — панель такое не правит" % sm)
    return sm, mate, [mine[0], other[0]]


def plan_break(w, p, lock=False, role=None):
    uid = _uid(p)
    sm, mate, rows = _pair(w, uid, lock)
    _service(role, uid, mate)
    changes = [["SoulMate", r, dict(r, State=0)] for r in rows]
    share = social.read(w, "Charinfo", "Userindex IN (?, ?) AND Share <> 0", (uid, mate), lock)
    changes += [["Charinfo", r, dict(r, Share=0)] for r in share]
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    cr = w.rows("SELECT Userindex, Charidx, Plate, Posx, Uuid, Code FROM dbo.Item%s WHERE Userindex IN (?, ?) AND Code BETWEEN ? AND ? "
                "AND Owner = 1 ORDER BY Userindex, Charidx, Plate, Posx" % hint, (uid, mate, CRYSTALS[0], CRYSTALS[1]))
    takes = []
    for c in cr:
        if int(c["Plate"]) not in (1, 2, 5):
            raise OpRefused("кристалл опыта Друга (%d) у персонажа %d/%d лежит не в сумке и не на складе (место %d) — сначала переложите"
                            % (int(c["Code"]), int(c["Userindex"]), int(c["Charidx"]), int(c["Plate"])))
        takes.append(itemgive.plan_take(w, {"uid": int(c["Userindex"]), "idx": int(c["Charidx"]), "plate": int(c["Plate"]),
                                            "posx": int(c["Posx"]), "uuid": str(c["Uuid"])}, lock=lock))
    r0 = rows[0]
    text = "разорвать связь соулмейта %d: учётки %d и %d (уровень %d, опыт %d, дружба %d)" % (sm, uid, mate, r0["SmLvl"], r0["SmExp"],
                                                                                         r0["FriendShip"])
    warn = ["уровень, опыт и дружба остаются в истории — «связать» эту же пару вернёт их (как у сервера)"]
    if share:
        warn.append("персонажи, отданные партнёру (Share), возвращаются владельцам: %d" % len(share))
    if takes:
        warn.append("кристаллы опыта Друга удаляются, как у сервера при разрыве: %d (вернуть — откатом)" % len(takes))
    return {"uids": [uid, mate], "changes": changes, "takes": takes, "text": text, "warn": warn,
            "logs": [["SoulMate", ["Edate", "Smidx", "Userindex1", "Userindex2", "State"], [social.NOW, sm, uid, mate, "Panel Breakup"]]],
            "ulogs": [["SoulMate", ["Edate", "Smidx", "Userindex1", "Userindex2", "State"], [social.NOW, sm, uid, mate, "Panel Undo Breakup"]]]}


def _table():
    try:
        t = exp_table()
    except Exception as ex:
        raise OpRefused("SoulMateExpTable.txt сервера не прочитан: %s" % ex)
    if not t:
        raise OpRefused("SoulMateExpTable.txt сервера пуст")
    return t


def plan_level(w, p, lock=False, role=None):
    uid = _uid(p)
    try:
        lv = int(p["level"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры соулмейта")
    t = _table()
    top = min(LEVEL_TOP, max(t))
    if not 1 <= lv <= top or lv not in t:
        raise OpRefused("уровень связи — от 1 до %d (SoulMateExpTable сервера)" % top)
    sm, mate, rows = _pair(w, uid, lock)
    _service(role, uid, mate)
    e = t[lv]
    changes = [["SoulMate", r, dict(r, SmLvl=lv, SmExp=e)] for r in rows if (r["SmLvl"], r["SmExp"]) != (lv, e)]
    if not changes:
        raise OpRefused("связь уже на уровне %d с опытом %d" % (lv, e))
    text = "уровень связи соулмейта %d (учётки %d и %d): %d → %d, опыт %d → %d" % (sm, uid, mate, rows[0]["SmLvl"], lv, rows[0]["SmExp"], e)
    warn = ["опыт ставится на начало уровня по таблице сервера — дальше копится, только когда оба в игре рядом"]
    if (rows[0]["SmLvl"], rows[0]["SmExp"]) != (rows[1]["SmLvl"], rows[1]["SmExp"]):
        warn.append("строки пары расходились по уровню или опыту — станут одинаковыми")
    return {"uids": [uid, mate], "changes": changes, "text": text, "warn": warn,
            "logs": [["SoulMateLevelUp", ["Edate", "Smidx", "Af"], [social.NOW, sm, lv]]],
            "ulogs": [["SoulMateLevelUp", ["Edate", "Smidx", "Af"], [social.NOW, sm, rows[0]["SmLvl"]]]]}


def plan_friendship(w, p, lock=False, role=None):
    uid = _uid(p)
    v = p.get("value")
    if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit())):
        raise OpRefused("дружба пары — целое число от 0 до 255")
    v = int(v)
    if not 0 <= v <= 255:
        raise OpRefused("дружба пары — целое число от 0 до 255")
    sm, mate, rows = _pair(w, uid, lock)
    _service(role, uid, mate)
    changes = [["SoulMate", r, dict(r, FriendShip=v, FinalDate=None)] for r in rows if (r["FriendShip"], r["FinalDate"]) != (v, None)]
    if not changes:
        raise OpRefused("дружба пары уже %d" % v)
    b = rows[0]["FriendShip"]
    text = "дружба пары соулмейта %d (учётки %d и %d): %d → %d" % (sm, uid, mate, b, v)
    warn = ["отметка времени затухания сброшена — дружба начнёт убывать со следующего выхода второго из пары, как у сервера"]
    return {"uids": [uid, mate], "changes": changes, "text": text, "warn": warn,
            "logs": [["SoulMateinfo", ["Edate", "Smidx", "Before", "Af", "State"], [social.NOW, sm, b, v, "FriendShip-Panel"]]],
            "ulogs": [["SoulMateinfo", ["Edate", "Smidx", "Before", "Af", "State"], [social.NOW, sm, v, b, "FriendShip-Panel"]]]}


def _evict(w, u, hist, lock):
    """Как сток: в истории учётки > 2 строк — самая старая строка State 0 удаляется → изменение или None."""
    if len(hist) <= HISTORY_MAX - 1:
        return None
    old = sorted([r for r in hist if r["State"] == 0], key=lambda r: (r["Regdate"] or "", r["Smidx"]))
    if not old:
        raise OpRefused("у учётки %d в истории %d строк и ни одной разорванной — панель не связывает" % (u, len(hist)))
    return ["SoulMate", old[0], None]


def plan_link(w, p, lock=False, role=None):
    u1, u2 = _uid(p, "uid"), _uid(p, "uid2")
    if u1 == u2:
        raise OpRefused("связать учётку с самой собой нельзя")
    _service(role, u1, u2)
    for u in (u1, u2):
        if not w.rows("SELECT TOP 1 1 AS x FROM dbo.Charinfo WHERE Userindex = ?", (u,)):
            raise OpRefused("у учётки %d нет персонажей" % u)
        if social.read(w, "SoulMate", "Userindex = ? AND State = 1", (u,), lock):
            raise OpRefused("у учётки %d уже есть связь соулмейта — сначала разорвите её" % u)
    hist = {u: social.read(w, "SoulMate", "Userindex = ?", (u,), lock) for u in (u1, u2)}
    pair = [r for r in hist[u1] if r["Ouserindex"] == u2] + [r for r in hist[u2] if r["Ouserindex"] == u1]
    changes, warn, cols = [], [], ["Edate", "Smidx", "Userindex1", "Userindex2", "State"]
    if len(pair) == 2 and pair[0]["Smidx"] == pair[1]["Smidx"] and len(social.read(w, "SoulMate", "Smidx = ?", (pair[0]["Smidx"],), lock)) == 2:
        sm = pair[0]["Smidx"]
        changes = [["SoulMate", r, dict(r, State=1, Regdate=social.NOW)] for r in pair]
        text = "связать учётки %d и %d: восстановить прежнюю пару %d из истории (уровень %d, опыт %d, дружба %d)" % (
            u1, u2, sm, pair[0]["SmLvl"], pair[0]["SmExp"], pair[0]["FriendShip"])
        state = "Panel Restore"
        lu = (u1, u2)
    elif len(pair) == 1:
        r = pair[0]
        a, b = r["Userindex"], r["Ouserindex"]
        sm = r["Smidx"]
        if len(social.read(w, "SoulMate", "Smidx = ?", (sm,), lock)) != 1:
            raise OpRefused("строка пары %d есть ещё у третьей учётки — панель не связывает" % sm)
        ev = _evict(w, b, hist[b], lock)
        if ev:
            changes.append(ev)
            warn.append("у учётки %d в истории уже %d связи — самая старая (пара %d) удаляется, как у сервера" % (b, len(hist[b]), ev[1]["Smidx"]))
        new = dict(r, Userindex=b, Ouserindex=a, info=1, State=1, Regdate=social.NOW)
        changes += [["SoulMate", None, new], ["SoulMate", r, dict(r, State=1, Regdate=social.NOW)]]
        text = "связать учётки %d и %d: пара %d есть в истории только у учётки %d — вторая строка дописывается (уровень %d, опыт %d, дружба %d)" % (
            u1, u2, sm, a, r["SmLvl"], r["SmExp"], r["FriendShip"])
        state = "Panel Active-OneSide"
        lu = (a, b)
    elif not pair:
        for u in (u1, u2):
            ev = _evict(w, u, hist[u], lock)
            if ev:
                changes.append(ev)
                warn.append("у учётки %d в истории уже %d связи — самая старая (пара %d) удаляется, как у сервера" % (u, len(hist[u]), ev[1]["Smidx"]))
        hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
        r = w.rows("SELECT MIN(i.Smidx) AS s FROM dbo.SoulMateIdx i%s WHERE NOT EXISTS (SELECT 1 FROM dbo.SoulMate s%s WHERE s.Smidx = i.Smidx)"
                   % (hint, hint))
        sm = r[0]["s"] if r else None
        if sm is None:
            raise OpRefused("в пуле SoulMateIdx нет свободного номера пары")
        sm = int(sm)
        base = {"Smidx": sm, "info": 1, "State": 1, "SmLvl": 1, "SmExp": 0, "FriendShip": 0, "AppleRate": 0, "AppleValue": 0,
                "FinalDate": None, "Regdate": social.NOW}
        changes += [["SoulMate", None, dict(base, Userindex=u1, Ouserindex=u2)], ["SoulMate", None, dict(base, Userindex=u2, Ouserindex=u1)]]
        text = "связать учётки %d и %d: новая пара %d (уровень 1)" % (u1, u2, sm)
        state = "Panel Birth"
        lu = (u1, u2)
    else:
        raise OpRefused("у учёток %d и %d в истории несогласованные строки пары (%d) — панель не связывает" % (u1, u2, len(pair)))
    en = w.rows("SELECT Userindex, SmEnroll FROM dbo.CharOption WHERE Userindex IN (?, ?)", (u1, u2))
    for e in en:
        if not e["SmEnroll"]:
            warn.append("учётка %d отключила предложения соулмейта (SmEnroll = 0) — связь создаётся по решению оператора" % int(e["Userindex"]))
    warn.append("персонажей партнёру (Share) игроки отдают сами в окне соулмейта")
    return {"uids": [u1, u2], "changes": changes, "text": text, "warn": warn,
            "logs": [["SoulMate", cols, [social.NOW, sm, lu[0], lu[1], state]]],
            "ulogs": [["SoulMate", cols, [social.NOW, sm, lu[0], lu[1], "Panel Undo Link"]]]}


def plan_share_fix(w, p, lock=False, role=None):
    """Сверка S5: персонажи с Share ≠ 0 у учёток без активной связи (uid — только эта учётка)."""
    where, prm = "Share <> 0 AND NOT EXISTS (SELECT 1 FROM dbo.SoulMate s WHERE s.Userindex = c.Userindex AND s.State = 1)", ()
    if p.get("uid") not in (None, ""):
        where += " AND c.Userindex = ?"
        prm = (_uid(p),)
    rows = social.read(w, "Charinfo", where, prm, lock, alias="c")
    if not rows:
        raise OpRefused("персонажей с Share без связи соулмейта нет")
    uids = sorted({r["Userindex"] for r in rows})
    _service(role, *uids)
    text = "снять «отдан партнёру» (Share) у %d персонажей учёток без связи соулмейта: %s" % (
        len(rows), ", ".join("%d/%d" % (r["Userindex"], r["Charidx"]) for r in rows))
    return {"uids": uids, "changes": [["Charinfo", r, dict(r, Share=0)] for r in rows], "text": text,
            "warn": ["сверка: на входе сервер такие персонажи не подгружает партнёру (пары нет) — правка только убирает несогласованность"]}


def _undo_check_break(w, a):
    u = a.get("uids") or []
    if u and w.rows("SELECT TOP 1 Userindex FROM dbo.SoulMate WITH (UPDLOCK, HOLDLOCK) WHERE Userindex IN (%s) AND State = 1"
                    % ", ".join("?" * len(u)), tuple(u)):
        raise OpRefused("у одной из учёток с тех пор другая активная связь — откат не выполнен")


def _undo_check_link(w, a):
    """Перепроверка 23 М2: за время связи могли появиться отданные партнёру персонажи (Share) и кристаллы Друга (21097…21106, Owner 1) —
    откат одних строк SoulMate оставил бы несогласованность; тогда — отказ и «Разорвать» (оно убирает и это, как сервер)."""
    u = a.get("uids") or []
    if not u:
        return
    q = ", ".join("?" * len(u))
    if w.rows("SELECT TOP 1 Userindex FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex IN (%s) AND Share <> 0" % q, tuple(u)) or             w.rows("SELECT TOP 1 Userindex FROM dbo.Item WITH (UPDLOCK, HOLDLOCK) WHERE Userindex IN (%s) AND Code BETWEEN 21097 AND 21106 "
                   "AND Owner = 1" % q, tuple(u)):
        raise OpRefused("за время связи появились отданные партнёру персонажи или кристаллы Друга — откат не выполнен; используйте «Разорвать»")


class _SmOp(social.SocialOp):
    perm = "players.soulmate"
    require_offline = staticmethod(_require_offline)
    undo_offline = staticmethod(_require_offline_undo)

    def target(self, p):
        return "account:%s" % p.get("uid", "*")


@register
class SoulmateBreak(_SmOp):
    name, title = "soulmate.break", "Соулмейт: разорвать связь"
    planner = staticmethod(plan_break)
    undo_check = staticmethod(_undo_check_break)


@register
class SoulmateLink(_SmOp):
    name, title = "soulmate.link", "Соулмейт: связать учётки"
    planner = staticmethod(plan_link)
    undo_check = staticmethod(_undo_check_link)


@register
class SoulmateLevel(_SmOp):
    name, title = "soulmate.level", "Соулмейт: уровень связи"
    planner = staticmethod(plan_level)


@register
class SoulmateFriendship(_SmOp):
    name, title = "soulmate.friendship", "Соулмейт: дружба пары"
    planner = staticmethod(plan_friendship)


@register
class SoulmateShareFix(_SmOp):
    name, title = "soulmate.share_fix", "Соулмейт: сверка Share"
    planner = staticmethod(plan_share_fix)


def describe(uid):
    """Окно «Соулмейт» учётки: активная пара, история, персонажи с Share, таблица уровней."""
    uid = int(uid)
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        rows = social.read(ad, "SoulMate", "Userindex = ? OR Ouserindex = ?", (uid, uid))
        mates = sorted({x["Ouserindex"] for x in rows if x["Userindex"] == uid} | {x["Userindex"] for x in rows if x["Ouserindex"] == uid})
        chars = {}
        for u in [uid] + mates:
            chars[u] = [{"idx": int(c["Charidx"]), "name": c["Charname"], "share": int(c["Share"] or 0), "lvl": c["Lvl"],
                         "online": bool(c["online"])} for c in ad.rows(
                "SELECT c.Charidx, c.Charname, c.Share, c.Lvl, CASE WHEN p.UserNum IS NOT NULL AND p.UserNum <> -1 THEN 1 ELSE 0 END AS online "
                "FROM dbo.Charinfo c LEFT JOIN dbo.CharPos p ON p.Userindex = c.Userindex AND p.Charidx = c.Charidx "
                "WHERE c.Userindex = ? ORDER BY c.Charidx", (u,))]
        crystals = ad.rows("SELECT Userindex, Charidx, Plate, Posx, Code FROM dbo.Item WHERE Userindex = ? AND Code BETWEEN ? AND ? AND Owner = 1",
                           (uid, CRYSTALS[0], CRYSTALS[1]))
    mine = [x for x in rows if x["Userindex"] == uid]
    act = next((x for x in mine if x["State"] == 1), None)
    try:
        t = exp_table()
    except Exception:
        t = {}
    return {"uid": uid, "active": act, "history": [x for x in mine if x["State"] != 1],
            "partner_rows": [x for x in rows if x["Ouserindex"] == uid], "chars": {str(k): v for k, v in chars.items()},
            "crystals": crystals, "levels": [[k, v] for k, v in sorted(t.items()) if k <= LEVEL_TOP]}
