# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""online.py — снять ЗАЛИПШИЙ признак «в игре» у учётки (волна А1, план §4.А «снятие залипшего „в игре“»). 17.11.2026.

ЗАЧЕМ. Признаки «в игре» (Joy1.dbo.CharPos.UserNum ≠ −1 / State 1, AsdaStoryOP.dbo.Us_member.Flag ≠ 0 / UserNum ≠ −1) после
обрыва остаются: LoginManager закрывает сессию только пакетом выхода; при падении/рестарте карты UpGameServerStart зовёт лишь
RelayServer при разрыве (research_online_persist.md §1.1; charpos_fix_20261026.sql). Залипший признак мешает: панель не даёт
править предметы, вход отвечает «двойной вход», друзья видят «в сети». Брошенный портальный переход уже чистит сам сервер
(P94, UPSameUser раз в ~60 с); остальное — здесь.

ПРАВИЛО «ТОЧНО НЕ В ИГРЕ» (снимается ТОЛЬКО доказанное; иначе — отказ с причиной: снять живую сессию = дюп/потеря):
  персонаж  CharPos.UserNum ≠ −1 или State 1, и CharPos.LastDate раньше старта КАЖДОГО работающего GameServer (LastDate
            ставят только вход в мир UPUserNumUp, выход и портал — пока персонаж в мире, она не меняется; значит, карта, где
            он был, с тех пор перезапускалась) — или GameServer не запущен ни один;
  учётка    Us_member.Flag ≠ 0 / UserNum ≠ −1 без персонажа в мире (после снятия выше), и вход этой сессии
            (JoyLog1.LogInfo.idx = Us_member.Loginidx) раньше старта LoginManager — или LoginManager не запущен.
СБРОС — поля штатного сброса UP_AsdaCharPosReset / стокового выхода UPLogOutCharacter: CharPos UserNum −1, Partyidx −1,
Captain 0, SoulState 0, State 0 (State 3 сохраняется); Us_member Flag 0, UserNum −1.
ЗАПИСЬ — asda_ops (sql/adminc_04_ops.sql: UPDATE только этих столбцов), одна транзакция, строки под UPDLOCK; сверка с
предпросмотром по «было» (Loginidx и LastDate — свежий вход меняет их → отказ). Откат возвращает прежние значения, если
строки с тех пор не менялись. Побочных эффектов при импорте нет.
"""
import datetime

from core import bridge, db
from core.ops import Operation, OpRefused, register

CP_COLS = ("UserNum", "Partyidx", "Captain", "SoulState", "State")
OPERATOR_MAX_UID = 5000                     # служебные учётки (players.OPERATOR_MAX_UID): только владелец (перепроверка 9 М8)
FMT = "%d.%m %H:%M:%S"


def _ms(v):
    """datetime → «ГГГГ-ММ-ДД ЧЧ:ММ:СС.ммм» (как CONVERT(varchar(23), …, 121))."""
    return v.strftime("%Y-%m-%d %H:%M:%S.") + "%03d" % (v.microsecond // 1000) if v else None


def _starts():
    """Старты GameServer и LoginManager. Перепроверка 9 В1: процессы ищутся ПО ИМЕНИ в любой папке (снимок status.named);
    снимок без процесса SQL Server — неисправен → отказ; GameServer не найден, а журнал карт (Joy1.dbo.SameUser, DBManager
    пишет раз в ~60 с, пока на карте есть игроки) свежее 120 с — отказ: «не найден» ≠ «не запущен».
    → (самый ранний старт GameServer | None, самый ранний старт LoginManager | None, отпечаток)."""
    from domains import status
    s = status.snapshot(force=True, max_age=10)        # свежее 10 с — из кэша (один сбор на операцию), иначе собрать сейчас
    named = s.get("named") or {}
    if s.get("host_error") or not named.get("sqlservr"):
        raise OpRefused("нет исправного снимка процессов сервера — без него нельзя доказать, что игрок не в игре")
    p = lambda v: datetime.datetime.strptime(v, "%Y-%m-%d %H:%M:%S") if v else None
    gs = [p(v) for v in named.get("gameserver") or [] if v]
    lm = [p(v) for v in named.get("loginmanager") or [] if v]
    if not gs:
        with db.GameReader("joy1") as r:
            x = r.one("SELECT MAX(Edate) AS e FROM dbo.SameUser")
        if x and x["e"] and x["e"] > datetime.datetime.now() - datetime.timedelta(seconds=120):
            raise OpRefused("GameServer не найден среди процессов, но журнал карт обновлялся %s — снимок ненадёжен, ничего не снято"
                            % x["e"].strftime(FMT))
    return (min(gs) if gs else None), (min(lm) if lm else None)


def _login_time(loginidx):
    if not loginidx:
        return None
    with db.GameReader("joylog1") as r:
        x = r.one("SELECT Login FROM dbo.LogInfo WHERE idx = ?", (int(loginidx),))
    return x["Login"] if x else None


def _portal_time(portalidx):
    """Вход на карту текущей сессии учётки (UPUserNumUp → JoyLog1.UPPortalLogin, Us_member.Portalidx)."""
    if not portalidx:
        return None
    with db.GameReader("joylog1") as r:
        x = r.one("SELECT InDate FROM dbo.Portalinfo WHERE idx = ?", (int(portalidx),))
    return x["InDate"] if x else None


def plan(w, uid, gs_start, lm_start, login_at, lock=False, portal_in=None):
    """→ (учётка, строки_CharPos[{Charidx, было, стало, почему}], учётка{было, стало, почему}|None, оставлено[str], отпечаток)."""
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    m = w.rows("SELECT Userindex, Us_id, Flag, UserNum, Loginidx, Portalidx FROM AsdaStoryOp.dbo.Us_member%s WHERE Userindex = ?"
               % hint, (uid,))
    if not m:
        raise OpRefused("учётки %d нет" % uid)
    m = m[0]
    rows = w.rows("SELECT Charidx, Charname, UserNum, Partyidx, Captain, SoulState, State, LastDate FROM dbo.CharPos%s "
                  "WHERE Userindex = ? AND (UserNum <> -1 OR State = 1)" % hint, (uid,))
    fix, keep = [], []
    # перепроверка 9 М2: учётка «в мире» по своей строке и вход на карту её сессии — после старта GameServer: живой вход
    # (UPUserNumUp сначала обновляет учётку, потом персонажа — LastDate персонажа на миг ещё старая) — ничего не трогаем
    live_portal = (m.get("UserNum") not in (-1, None) and portal_in is not None and gs_start is not None and portal_in >= gs_start)
    for r in rows:
        if live_portal:
            keep.append("персонаж %s (слот %s): учётка вошла на карту %s — после старта GameServer: может быть в игре"
                        % (r["Charname"], r["Charidx"], portal_in.strftime(FMT)))
            continue
        if gs_start is None:
            why = "GameServer не запущен"
        elif r["LastDate"] and r["LastDate"] < gs_start:
            why = "вошёл в мир %s — раньше старта GameServer %s" % (r["LastDate"].strftime(FMT), gs_start.strftime(FMT))
        else:
            keep.append("персонаж %s (слот %s) вошёл в мир %s — после старта GameServer: может быть в игре"
                        % (r["Charname"], r["Charidx"], r["LastDate"].strftime(FMT) if r["LastDate"] else "?"))
            continue
        new = {"UserNum": -1, "Partyidx": -1, "Captain": 0, "SoulState": 0, "State": 3 if r["State"] == 3 else 0}
        fix.append({"Charidx": r["Charidx"], "Charname": r["Charname"], "before": {k: r[k] for k in CP_COLS},
                    "after": new, "why": why, "LastDate": _ms(r["LastDate"])})
    acc = None
    if m["Flag"] not in (0,) or m["UserNum"] not in (-1, None):
        if keep:
            keep.append("признак учётки оставлен: у неё персонаж, который может быть в игре")
        elif lm_start is None:
            acc = "LoginManager не запущен"
        elif m["Flag"] is None:
            # перепроверка 9 М1: при Flag NULL UPUserLogin Loginidx не обновляет — время входа не доказательство
            keep.append("признак учётки Flag = NULL: время входа по нему не определить — оставлено")
        elif login_at and login_at < lm_start:
            acc = "вход %s — раньше старта LoginManager %s" % (login_at.strftime(FMT), lm_start.strftime(FMT))
        else:
            keep.append("учётка вошла %s — после старта LoginManager: игрок может быть на выборе персонажа"
                        % (login_at.strftime(FMT) if login_at else "?"))
        if acc:
            acc = {"before": {"Flag": m["Flag"], "UserNum": m["UserNum"]}, "after": {"Flag": 0, "UserNum": -1}, "why": acc,
                   "Loginidx": m["Loginidx"], "Portalidx": m.get("Portalidx")}
    # перепроверка 9 М3: в отпечатке и само решение (что снимается и по каким стартам)
    sig = {"loginidx": m["Loginidx"], "portalidx": m.get("Portalidx"), "acc": [m["Flag"], m["UserNum"]],
           "rows": [[r["Charidx"], r["UserNum"], r["State"], _ms(r["LastDate"])] for r in rows],
           "fix": [f["Charidx"] for f in fix], "fix_acc": bool(acc),
           "gs": gs_start.isoformat(sep=" ") if gs_start else None, "lm": lm_start.isoformat(sep=" ") if lm_start else None}
    return m, fix, acc, keep, sig


def _text(m, fix, acc):
    parts = ["персонаж %s (слот %s): %s" % (f["Charname"], f["Charidx"], f["why"]) for f in fix]
    if acc:
        parts.append("учётка: %s" % acc["why"])
    return "снять «в игре» у учётки %s (%s): %s" % (m["Us_id"], m["Userindex"], "; ".join(parts))


@register
class ClearOnline(Operation):
    name, title, perm, reversible = "account.clear_online", "Учётка: снять залипший «в игре»", "players.clear_online", True

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _ctx(self, p):
        try:
            uid = int(p["uid"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры")
        if uid <= OPERATOR_MAX_UID and ctx_role(p) != "owner":
            raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
        # ★ А2 (мост P127, 18.11.2026): мост видит учётку в игре на живом GameServer — признак НЕ залипший, снимать нельзя
        live = bridge.presence(uid)
        if live:
            raise OpRefused("учётка в игре по данным моста (%s) — это живая сессия, не залипший признак"
                            % ", ".join("%s на %s" % (r["charname"], r["node"]) for r in live))
        gs, lm = _starts()
        with db.GameReader("asdastoryop") as r:
            x = r.one("SELECT Loginidx, Portalidx FROM Us_member WHERE Userindex = ?", (uid,))
        return uid, gs, lm, _login_time(x["Loginidx"] if x else None), _portal_time(x["Portalidx"] if x else None)

    def preview(self, ctx, p):
        p = dict(p, _role=ctx.role)
        uid, gs, lm, login_at, portal_in = self._ctx(p)
        try:
            with db.GameReader("joy1") as r:
                m, fix, acc, keep, sig = plan(_Adapter(r), uid, gs, lm, login_at, portal_in=portal_in)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not fix and not acc:
            raise OpRefused("снимать нечего: " + ("; ".join(keep) if keep else "признаков «в игре» у учётки нет"))
        return {"text": _text(m, fix, acc), "expect": sig, "warnings": keep,
                "gs_start": str(gs) if gs else None, "lm_start": str(lm) if lm else None}

    def apply(self, ctx, p, prev):
        uid, gs, lm, login_at, portal_in = self._ctx(dict(p, _role=ctx.role))
        w = db.GameWriter("joy1")
        try:
            m, fix, acc, keep, sig = plan(w, uid, gs, lm, login_at, lock=True, portal_in=portal_in)
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("пока вы смотрели предпросмотр, состояние учётки изменилось (вход, выход или переход) — повторите")
            for f in fix:
                n = w.execute("UPDATE dbo.CharPos SET UserNum = ?, Partyidx = ?, Captain = ?, SoulState = ?, State = ? "
                              "WHERE Userindex = ? AND Charidx = ? AND UserNum = ? AND State = ?",
                              tuple(f["after"][k] for k in CP_COLS) + (uid, f["Charidx"], f["before"]["UserNum"], f["before"]["State"]))
                if n != 1:
                    raise OpRefused("строка персонажа изменилась при записи — ничего не записано")
            if acc:
                n = w.execute("UPDATE AsdaStoryOp.dbo.Us_member SET Flag = 0, UserNum = -1 WHERE Userindex = ? AND "
                              "(Flag = ? OR (Flag IS NULL AND ? IS NULL)) AND (UserNum = ? OR (UserNum IS NULL AND ? IS NULL))",
                              (uid, acc["before"]["Flag"], acc["before"]["Flag"], acc["before"]["UserNum"], acc["before"]["UserNum"]))
                if n != 1:
                    raise OpRefused("строка учётки изменилась при записи — ничего не записано")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "chars": [{"Charidx": f["Charidx"], **f["before"]} for f in fix],
                           "acc": acc["before"] if acc else None},
                "after": {"uid": uid, "chars": fix, "acc": acc}, "message": _text(m, fix, acc),
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid = a.get("uid")
        if not uid:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            w.rows("SELECT Flag FROM AsdaStoryOp.dbo.Us_member WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ?", (uid,))
            for f in a.get("chars") or []:
                b, s = f["before"], f["after"]
                # перепроверка 9 В2: «как записали» — мало (обычный выход даёт те же значения); LastDate ставят вход,
                # выход и портал — если сессия была, она другая → отказ, призрак «в игре» не воскрешается
                n = w.execute("UPDATE dbo.CharPos SET UserNum = ?, Partyidx = ?, Captain = ?, SoulState = ?, State = ? "
                              "WHERE Userindex = ? AND Charidx = ? AND UserNum = ? AND Partyidx = ? AND Captain = ? AND "
                              "SoulState = ? AND State = ? AND (CONVERT(varchar(23), LastDate, 121) = ? OR (LastDate IS NULL AND ? IS NULL))",
                              tuple(b[k] for k in CP_COLS) + (uid, f["Charidx"]) + tuple(s[k] for k in CP_COLS)
                              + (f.get("LastDate"), f.get("LastDate")))
                if n != 1:
                    raise OpRefused("персонаж с тех пор входил или выходил — откат не выполнен")
            acc = a.get("acc")
            if acc:
                n = w.execute("UPDATE AsdaStoryOp.dbo.Us_member SET Flag = ?, UserNum = ? WHERE Userindex = ? AND Flag = 0 AND UserNum = -1 "
                              "AND (Loginidx = ? OR (Loginidx IS NULL AND ? IS NULL)) AND (Portalidx = ? OR (Portalidx IS NULL AND ? IS NULL))",
                              (acc["before"]["Flag"], acc["before"]["UserNum"], uid, acc.get("Loginidx"), acc.get("Loginidx"),
                               acc.get("Portalidx"), acc.get("Portalidx")))
                if n != 1:
                    raise OpRefused("учётка с тех пор входила — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": {}, "after": {}, "message": "признаки «в игре» учётки %s возвращены откатом" % uid,
                "_commit": w.commit, "_close": w.close}


def ctx_role(p):
    return p.get("_role")


class _Adapter:
    """GameReader → интерфейс писателя для предпросмотра (без подсказок блокировки)."""

    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql.replace(" WITH (UPDLOCK, HOLDLOCK)", ""), params)
