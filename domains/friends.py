# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""friends.py — список друзей персонажа НЕ В ИГРЕ: удалить, добавить, обновить устаревшие имена (волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_soulmate_friends.md §1.2, §2.5 (живые тексты UPFriendAdd / UPFriendDelete сняты 18.11).
dbo.CharFriend (Userindex, Charidx, Fuserindex, Fcharidx, Charname — имя ДРУГА), PK нет; дружба взаимна — по строке у каждого.
Списка друзей в памяти GameServer нет (окно 4156 → DBM 2219 UPFriendList, RelayServer читает ту же процедуру) — правка базы
действует сразу. РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11: владелец списка — не в игре (_require_offline под блокировкой); друг МОЖЕТ быть в игре —
предупреждение (у него строка в окне обновится при следующем открытии списка). Стоковые журналы дружбы процедуры не пишут —
только журнал панели.
  friend.delete — как UPFriendDelete: строка владельца обязана быть; удаляются обе стороны;
  friend.add    — как UPFriendAdd: недостающие стороны, лимит 50 у каждого (коды 4/5/6 → отказ), уже взаимны (код 7) → отказ.
                  ИМЯ — из Charinfo (сток берёт CharPos.Charname; у живых 2/11 и 2/12 в CharPos старое имя — отличие, пометка);
                  друзья в пределах ОДНОЙ учётки — отказ (в игре недостижимо: на учётке в мире один персонаж);
  friend.names  — сверка F3: Charname строки ← нынешнее Charinfo.Charname друга (байт в байт; на живых данных НЕ применять —
                  владелец).
ЗАПИСЬ — asda_ops (SELECT, INSERT, DELETE, UPDATE(Charname) CharFriend), одна транзакция; откат — строки «стало → было».
Побочных эффектов при импорте нет.
"""
from core import db
from core.ops import OpRefused, register
from domains import items, social

LIMIT = 50
OPERATOR_MAX_UID = 5000


def _require_offline(w, uids, lock):
    """Владелец списка не в игре. ЕДИНАЯ точка раздела: онлайн-путь (мост AdminBridge, волна А2) подключается здесь."""
    social.offline(w, uids, lock, lambda u, why: "править можно только когда игрок не в игре: %s" % why)


def _require_offline_undo(w, uids, lock):
    social.offline(w, uids, lock, lambda u, why: "откат только когда игрок не в игре: %s" % why)


def _args(p, role):
    try:
        v = [int(p[k]) for k in ("uid", "idx", "fuid", "fidx")]
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры друга")
    if role != "owner" and (v[0] <= OPERATOR_MAX_UID or v[2] <= OPERATOR_MAX_UID):
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return v


def _char(w, u, i, lock):
    r = w.rows("SELECT Charname, CONVERT(varchar(60), CAST(Charname AS varbinary(20)), 2) AS h FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?"
               % (" WITH (UPDLOCK, HOLDLOCK)" if lock else ""), (u, i))
    if not r:
        raise OpRefused("персонажа %d/%d нет" % (u, i))
    return r[0]["Charname"], r[0]["h"]


def _row(w, u, i, f, fi, lock):
    r = social.read(w, "CharFriend", "Userindex = ? AND Charidx = ? AND Fuserindex = ? AND Fcharidx = ?", (u, i, f, fi), lock)
    if len(r) > 1:
        raise OpRefused("строка дружбы %d/%d → %d/%d повторяется — панель такое не правит" % (u, i, f, fi))
    return r[0] if r else None


def _count(w, u, i, lock):
    return int(w.rows("SELECT COUNT(*) AS n FROM dbo.CharFriend%s WHERE Userindex = ? AND Charidx = ?"
                      % (" WITH (UPDLOCK, HOLDLOCK)" if lock else ""), (u, i))[0]["n"])


def _friend_warn(w, f, fi):
    return ["друг сейчас в игре: у него строка в окне друзей обновится при следующем открытии списка"] if social.in_world(w, f, fi) else []


def plan_delete(w, p, lock=False, role=None):
    u, i, f, fi = _args(p, role)
    a = _row(w, u, i, f, fi, lock)
    if not a:
        raise OpRefused("персонажа %d/%d нет в списке друзей %d/%d" % (f, fi, u, i))
    b = _row(w, f, fi, u, i, lock)
    nm = social.hex_text(a["Charname"])
    changes = [["CharFriend", a, None]] + ([["CharFriend", b, None]] if b else [])
    text = "удалить из друзей: %s (%d/%d) у персонажа %d/%d%s" % (nm, f, fi, u, i, " и обратную строку" if b else "")
    return {"uids": [u], "changes": changes, "text": text, "warn": _friend_warn(w, f, fi)}


def plan_add(w, p, lock=False, role=None):
    u, i, f, fi = _args(p, role)
    if u == f:
        raise OpRefused("друзья в пределах одной учётки недостижимы в игре — панель их не добавляет")
    _n1, h1 = _char(w, u, i, lock)
    n2, h2 = _char(w, f, fi, lock)
    a, b = _row(w, u, i, f, fi, lock), _row(w, f, fi, u, i, lock)
    if a and b:
        raise OpRefused("они уже друзья (обе строки есть)")
    ca, cb = _count(w, u, i, lock), _count(w, f, fi, lock)
    full = [x for x, need, c in (("%d/%d" % (u, i), not a, ca), ("%d/%d" % (f, fi), not b, cb)) if need and c >= LIMIT]
    if full:
        raise OpRefused("в списке друзей уже %d: %s (лимит сервера UPFriendAdd)" % (LIMIT, ", ".join(full)))
    changes = []
    if not a:
        changes.append(["CharFriend", None, {"Userindex": u, "Charidx": i, "Fuserindex": f, "Fcharidx": fi, "Charname": h2}])
    if not b:
        changes.append(["CharFriend", None, {"Userindex": f, "Charidx": fi, "Fuserindex": u, "Fcharidx": i, "Charname": h1}])
    text = "добавить в друзья: %s (%d/%d) персонажу %d/%d%s" % (n2, f, fi, u, i, "" if len(changes) == 2 else " (дописывается недостающая сторона)")
    warn = _friend_warn(w, f, fi) + ["имена в строках — нынешние из Charinfo (сервер берёт из CharPos, там бывает старое имя)"]
    return {"uids": [u], "changes": changes, "text": text, "warn": warn}


def plan_names(w, p, lock=False, role=None):
    """Сверка F3: Charname строк ≠ нынешнему имени друга. uid/idx — только список этого персонажа; без них — вся база."""
    where, prm = ("CONVERT(varchar(60), CAST(f.Charname AS varbinary(20)), 2) <> CONVERT(varchar(60), CAST(c.Charname AS varbinary(20)), 2)"), []
    if p.get("uid") not in (None, ""):
        try:
            where += " AND f.Userindex = ? AND f.Charidx = ?"
            prm = [int(p["uid"]), int(p["idx"])]
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры друга")
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    rows = w.rows("SELECT %s, CONVERT(varchar(60), CAST(c.Charname AS varbinary(20)), 2) AS cur FROM dbo.CharFriend f%s JOIN dbo.Charinfo c "
                  "ON c.Userindex = f.Fuserindex AND c.Charidx = f.Fcharidx WHERE %s ORDER BY f.Userindex, f.Charidx, f.Fuserindex, f.Fcharidx"
                  % (social.select_list("CharFriend", "f"), hint, where), prm)
    if not rows:
        raise OpRefused("устаревших имён в списках друзей нет")
    uids = sorted({int(r["Userindex"]) for r in rows})
    if role != "owner" and any(x <= OPERATOR_MAX_UID for x in uids + [int(r["Fuserindex"]) for r in rows]):
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    changes = []
    for r in rows:
        b = {k: (int(r[k]) if k != "Charname" else r[k]) for k in ("Userindex", "Charidx", "Fuserindex", "Fcharidx", "Charname")}
        changes.append(["CharFriend", b, dict(b, Charname=r["cur"])])
    text = "обновить устаревшие имена в списках друзей: %d строк (%s)" % (len(rows), "; ".join(
        "%d/%d → %d/%d: %s → %s" % (c[1]["Userindex"], c[1]["Charidx"], c[1]["Fuserindex"], c[1]["Fcharidx"], social.hex_text(c[1]["Charname"]),
                                    social.hex_text(c[2]["Charname"])) for c in changes[:20]))
    return {"uids": uids, "changes": changes, "text": text,
            "warn": ["сверка: имя в строке друга видно только в окне друзей; сервер связь ищет по номерам, не по имени"]}


def _undo_uids(w, a):
    return a.get("uids") or []


def _undo_check_delete(w, a):
    """Откат удаления: строк ещё нет, лимит 50 у каждой стороны не превышен."""
    for t, b, _af in a.get("changes") or []:
        if t != "CharFriend" or not b:
            continue
        if _row(w, b["Userindex"], b["Charidx"], b["Fuserindex"], b["Fcharidx"], True):
            raise OpRefused("дружба с тех пор восстановлена — откат не выполнен")
        if _count(w, b["Userindex"], b["Charidx"], True) >= LIMIT:
            raise OpRefused("в списке друзей %d/%d уже %d — откат не выполнен" % (b["Userindex"], b["Charidx"], LIMIT))


class _FrOp(social.SocialOp):
    perm = "players.friends"
    require_offline = staticmethod(_require_offline)
    undo_offline = staticmethod(_require_offline_undo)
    undo_uids = staticmethod(_undo_uids)

    def target(self, p):
        return "char:%s/%s" % (p.get("uid", "*"), p.get("idx", "*"))


@register
class FriendDelete(_FrOp):
    name, title = "friend.delete", "Друзья: удалить"
    planner = staticmethod(plan_delete)
    undo_check = staticmethod(_undo_check_delete)


@register
class FriendAdd(_FrOp):
    name, title = "friend.add", "Друзья: добавить"
    planner = staticmethod(plan_add)


@register
class FriendNames(_FrOp):
    name, title = "friend.names", "Друзья: обновить имена"
    planner = staticmethod(plan_names)


def describe(uid, idx):
    """Окно «Друзья» персонажа: строки владельца (взаимность, онлайн друга, устаревшее имя) и строки «на него» без пары."""
    uid, idx = int(uid), int(idx)
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        rows = ad.rows("SELECT f.Fuserindex, f.Fcharidx, f.Charname, c.Charname AS cur, c.Lvl, "
                       "CASE WHEN CAST(f.Charname AS varbinary(20)) = CAST(c.Charname AS varbinary(20)) THEN 0 ELSE 1 END AS stale, "
                       "CASE WHEN EXISTS (SELECT 1 FROM dbo.CharFriend b WHERE b.Userindex = f.Fuserindex AND b.Charidx = f.Fcharidx "
                       "AND b.Fuserindex = f.Userindex AND b.Fcharidx = f.Charidx) THEN 1 ELSE 0 END AS mutual, "
                       "CASE WHEN p.UserNum IS NOT NULL AND p.UserNum <> -1 THEN 1 ELSE 0 END AS online "
                       "FROM dbo.CharFriend f LEFT JOIN dbo.Charinfo c ON c.Userindex = f.Fuserindex AND c.Charidx = f.Fcharidx "
                       "LEFT JOIN dbo.CharPos p ON p.Userindex = f.Fuserindex AND p.Charidx = f.Fcharidx "
                       "WHERE f.Userindex = ? AND f.Charidx = ? ORDER BY f.Charname", (uid, idx))
        orphan = ad.rows("SELECT f.Userindex, f.Charidx, c.Charname FROM dbo.CharFriend f LEFT JOIN dbo.Charinfo c ON c.Userindex = f.Userindex "
                         "AND c.Charidx = f.Charidx WHERE f.Fuserindex = ? AND f.Fcharidx = ? AND NOT EXISTS (SELECT 1 FROM dbo.CharFriend b "
                         "WHERE b.Userindex = f.Fuserindex AND b.Charidx = f.Fcharidx AND b.Fuserindex = f.Userindex AND b.Fcharidx = f.Charidx)",
                         (uid, idx))
    return {"uid": uid, "idx": idx, "limit": LIMIT, "friends": rows, "one_sided_to_me": orphan}
