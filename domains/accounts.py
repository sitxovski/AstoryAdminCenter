# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""accounts.py — операции над учёткой игрока (волна А1, продолжение по плану): блок и снятие блока. 16.11.2026.

ЗАЧЕМ. План ADMIN_TOOL_PLAN.md §4.А: «блок и разблок с причиной и сроком» — вместо ручных ac0_block_user.sql /
ac0_unblock_user.sql (sqlcmd с паролем devgsaccount).

КАК У СЕРВЕРА (всё — из живых процедур и наших проверенных патчей, ничего своего):
  блок      us_block = 5 + строка AsdaStoryOP.dbo.BlockList (Userindex, Uid, Cou 1, grade 1, BlackDate = сейчас, CloseDate,
            Reason) — ровно как UPHackBlock / UPUserBlock / ac0_block_user.sql; −1 часов = 30 лет (как UPUserBlock @Time = −1).
            Срок истекает сам: вход (UPUserLogin, P51) и сверка личности (UP_AC_IdentityCheck, P50) снимают блок, у которого
            все CloseDate прошли (UP_AC_LiftExpiredBlock; Server/Docs/SQL/ac0_login_guard.md §1.2, §5.3).
            Игрок в игре доигрывает до выхода: вход и смена карты (P50) будут отклонены; выкинуть сейчас — живой канал А2.
  снятие    как штатный AsdaStoryOP.dbo.OPBlockDel: строки BlockList → BlockHistory, удаление из BlockList, us_block = 0.
            OPBlockDel ищет строки по Uid, панель — по Userindex: так же делает снятие истёкших при входе (P51,
            UP_AC_LiftExpiredBlock), Uid строки = Us_id учётки (перепроверка 6 М6 — так задумано).
ПРАВА (перепроверка 6 В3): блок — owner/admin/gm (players.block), снятие — owner/admin (players.unblock); служебные учётки
            (номер ≤ OPERATOR_MAX_UID) блокирует только владелец.
ГОНКА (перепроверка 6 В1): UP_AC_LiftExpiredBlock проверяет строки ДО своей транзакции и переносит все строки учётки — если
            у учётки висят истёкшие строки и игрок входит в момент нашего блока, новая строка может уйти в историю.
            Закрыто серверным патчем ac0t (17.11, Server/Docs/SQL/ac0t_01_migrate.sql: проверка и перенос в одной
            транзакции под UPDLOCK, переносятся только истёкшие строки); verify после записи оставлен как страховка.
ЗАПИСЬ — логин asda_ops (sql/adminc_04_ops.sql: UPDATE только us_block, SELECT/INSERT/DELETE BlockList, SELECT/INSERT BlockHistory),
одна транзакция, «было» под UPDLOCK; журнал adm.audit хранит вставленные/перенесённые строки — откат возвращает их.
Побочных эффектов при импорте нет.
"""
import datetime
import re

from core import db
from core.ops import Operation, OpRefused, register

FOREVER_H = -1
MAX_HOURS = 24 * 365 * 10                 # 10 лет; дольше — «навсегда» (30 лет, как у сервера)
OPERATOR_MAX_UID = 5000                   # служебные учётки (players.OPERATOR_MAX_UID, asda_give.OPERATOR_MAX_UID)
REASON_RX = re.compile(r"^[\x20-\x7E]{1,300}$")   # Reason varchar(300) в кодировке базы — латиница, как ac0_block_user.sql
BLOCK_COLS = "Userindex, Uid, Cou, grade, BlackDate, CloseDate, Reason"


def _uid(p):
    try:
        uid = int(p["uid"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры блока")
    if uid <= 0:
        raise OpRefused("неверные параметры блока")
    return uid


def _member(w, uid, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Userindex, Us_id, us_block, Flag, UserNum FROM dbo.Us_member%s WHERE Userindex = ?" % hint, (uid,))
    if not r:
        raise OpRefused("учётки %d нет" % uid)
    return r[0]


def _blocks(w, uid, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    return w.rows("SELECT %s FROM dbo.BlockList%s WHERE Userindex = ? ORDER BY BlackDate, CloseDate" % (BLOCK_COLS, hint), (uid,))


def _online_note(m):
    """Игрок в игре — блок подействует на следующем входе/смене карты."""
    if (m.get("Flag") not in (None, 0)) or (m.get("UserNum") not in (None, -1)):
        return ["игрок сейчас в игре: доиграет до выхода, а вход и смена карты будут отклонены (выкинуть сразу — живой канал А2)"]
    return []


def _dt(v):
    """Дата из журнала (строка) → datetime для параметра (строкой SQL Server с русским языком читает ГГГГ-ДД-ММ)."""
    return datetime.datetime.fromisoformat(v) if isinstance(v, str) else v


def _row_where(r):
    return ("Userindex = ? AND Uid = ? AND Cou = ? AND grade = ? AND BlackDate = ? AND CloseDate = ? AND "
            "(Reason = ? OR (Reason IS NULL AND ? IS NULL))",
            (r["Userindex"], r["Uid"], r["Cou"], r["grade"], _dt(r["BlackDate"]), _dt(r["CloseDate"]), r["Reason"], r["Reason"]))


def _active(rows):
    """Действующие строки (срок не вышел) — перепроверка 6 М7."""
    now = datetime.datetime.now()
    return [r for r in rows if r["CloseDate"] and _dt(r["CloseDate"]) > now]


def _sig(m, rows):
    return {"us_block": m["us_block"], "rows": len(rows)}


def _case_of(row):
    """★ А6.7 (ревизия 59 Н-5): номер дела античита, если запись журнала создана делом (параметр case — ставит domains/cases.py), иначе None."""
    import json
    try:
        p = json.loads(row.get("params") or "{}")
    except (TypeError, ValueError):
        return None
    return p.get("case") if isinstance(p, dict) else None


@register
class AccountBlock(Operation):
    name, title, perm, reversible = "account.block", "Учётка: заблокировать", "players.block", True

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _plan(self, w, p, lock=False, ctx=None):
        uid = _uid(p)
        if uid <= OPERATOR_MAX_UID and ctx is not None and ctx.role != "owner":
            raise OpRefused("служебные учётки (номер ≤ %d) блокирует только владелец" % OPERATOR_MAX_UID)
        try:
            hours = int(p.get("hours"))
        except (TypeError, ValueError):
            raise OpRefused("срок блока — целое число часов или «навсегда»")
        if hours != FOREVER_H and not (1 <= hours <= MAX_HOURS):
            raise OpRefused("срок блока — от 1 до %d часов или «навсегда»" % MAX_HOURS)
        reason = str(p.get("reason") or "").strip()
        if not REASON_RX.match(reason):
            raise OpRefused("причина — от 1 до 300 знаков латиницей (столбец Reason в кодировке базы)")
        m = _member(w, uid, lock)
        rows = _blocks(w, uid, lock)
        until = "навсегда (30 лет)" if hours == FOREVER_H else "на %d ч" % hours
        text = "блок учётки %s (%d) %s: %s" % (m["Us_id"], uid, until, reason)
        return uid, hours, reason, m, rows, text

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                ad = _Adapter(r)
                uid, hours, reason, m, rows, text = self._plan(ad, p, ctx=ctx)
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры блока")
        except db.DbError as ex:                                     # перепроверка 6 М8
            raise OpRefused("ошибка базы: %s" % ex)
        warn = _online_note(m)
        act = _active(rows)
        if act:
            warn.append("у учётки уже %d действующих строк блока — добавится ещё одна" % len(act))
        if len(rows) > len(act):
            warn.append("у учётки есть истёкшие строки блока (%d): сервер перенесёт их в историю при следующем входе"
                        % (len(rows) - len(act)))
        return {"text": text, "expect": _sig(m, rows), "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("asdastoryop")
        try:
            uid, hours, reason, m, rows, text = self._plan(w, p, lock=True, ctx=ctx)
            if _sig(m, rows) != prev["expect"] or ("expect" in p and p["expect"] != _sig(m, rows)):
                raise OpRefused("пока вы смотрели предпросмотр, блок учётки изменился — повторите")
            close = "DATEADD(YEAR, 30, GETDATE())" if hours == FOREVER_H else "DATEADD(HOUR, %d, GETDATE())" % hours
            ins = w.rows("INSERT INTO dbo.BlockList (Userindex, Uid, Cou, grade, BlackDate, CloseDate, Reason) "
                         "OUTPUT inserted.Userindex, inserted.Uid, inserted.Cou, inserted.grade, inserted.BlackDate, "
                         "inserted.CloseDate, inserted.Reason VALUES (?, ?, 1, 1, GETDATE(), %s, ?)" % close,
                         (uid, m["Us_id"], reason))
            if len(ins) != 1:
                raise OpRefused("строка блока не записана")
            if w.execute("UPDATE dbo.Us_member SET us_block = 5 WHERE Userindex = ?", (uid,)) != 1:
                raise OpRefused("учётка не найдена при записи")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "us_block": m["us_block"]},
                "after": {"uid": uid, "us_block": 5, "us_block_before": m["us_block"], "row": ins[0]}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def verify(self, ctx, p, res):
        """После фиксации: строка блока на месте и us_block = 5 (перепроверка 6 В1 — гонка со снятием истёкших при входе)."""
        a = res.get("after") or {}
        with db.GameReader("asdastoryop") as r:
            ad = _Adapter(r)
            m = _member(ad, a["uid"])
            where, params = _row_where(a["row"])
            n = r.one("SELECT COUNT(*) AS n FROM dbo.BlockList WHERE %s" % where, params)["n"]
        if not n or m["us_block"] != 5:
            raise OpRefused("блок не удержался: сервер в этот момент снял истёкшие блоки при входе игрока "
                            "(UP_AC_LiftExpiredBlock) — поставьте блок ещё раз")

    def undo_guard(self, row):
        """★ ревизия 59 Н-5: блок, поставленный делом, откатом журнала не снимается — только через дело (жизненный цикл, апелляция)."""
        case = _case_of(row)
        if case:
            raise OpRefused("блок поставлен делом %s — снимите через дело (case.lift)" % case)

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, r0 = a.get("uid"), a.get("row")
        if not uid or not r0:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("asdastoryop")
        try:
            m = _member(w, uid, lock=True)
            where, params = _row_where(r0)
            if w.execute("DELETE TOP (1) FROM dbo.BlockList WHERE %s" % where, params) != 1:
                raise OpRefused("строки этого блока уже нет (сняли или истёк) — откат не выполнен")
            left = _blocks(w, uid)
            back = m["us_block"] if left else a.get("us_block_before", 0)
            w.execute("UPDATE dbo.Us_member SET us_block = ? WHERE Userindex = ?", (back, uid))
        except BaseException:
            w.close()
            raise
        return {"before": {"us_block": m["us_block"]}, "after": {"us_block": back}, "message": "блок учётки %s снят откатом" % uid,
                "_commit": w.commit, "_close": w.close}


@register
class AccountUnblock(Operation):
    name, title, perm, reversible = "account.unblock", "Учётка: снять блок", "players.unblock", True

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _plan(self, w, p, lock=False):
        uid = _uid(p)
        m = _member(w, uid, lock)
        rows = _blocks(w, uid, lock)
        if not rows and not m["us_block"]:
            raise OpRefused("учётка не заблокирована")
        text = "снять блок учётки %s (%d): строк блока %d, us_block %s → 0" % (m["Us_id"], uid, len(rows), m["us_block"])
        return uid, m, rows, text

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                uid, m, rows, text = self._plan(_Adapter(r), p)
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры блока")
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = [] if rows else ["строк BlockList нет — снимается только признак us_block = %s" % m["us_block"]]
        return {"text": text, "expect": _sig(m, rows), "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("asdastoryop")
        try:
            uid, m, rows, text = self._plan(w, p, lock=True)
            if _sig(m, rows) != prev["expect"] or ("expect" in p and p["expect"] != _sig(m, rows)):
                raise OpRefused("пока вы смотрели предпросмотр, блок учётки изменился — повторите")
            # как OPBlockDel: BlockList → BlockHistory, удаление, us_block = 0
            if rows:
                n = w.execute("INSERT INTO dbo.BlockHistory (%s) SELECT %s FROM dbo.BlockList WHERE Userindex = ?"
                              % (BLOCK_COLS, BLOCK_COLS), (uid,))
                if n != len(rows) or w.execute("DELETE FROM dbo.BlockList WHERE Userindex = ?", (uid,)) != len(rows):
                    raise OpRefused("строки блока изменились при записи — ничего не записано")
            w.execute("UPDATE dbo.Us_member SET us_block = 0 WHERE Userindex = ?", (uid,))
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "us_block": m["us_block"], "rows": rows},
                "after": {"uid": uid, "us_block": 0, "us_block_before": m["us_block"], "rows": rows}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo_guard(self, row):
        """★ ревизия 59 Н-5: блок, снятый делом, откатом журнала не возвращается — новый блок только решением по делу."""
        case = _case_of(row)
        if case:
            raise OpRefused("блок снят делом %s — откатом журнала не возвращается, новый блок — решением по делу (case.decide)" % case)

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, rows = a.get("uid"), a.get("rows") or []
        if not uid:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("asdastoryop")
        try:
            m = _member(w, uid, lock=True)
            if m["us_block"] != 0 or _blocks(w, uid, lock=True):
                raise OpRefused("учётку с тех пор снова блокировали — откат не выполнен")
            # перепроверка 6 М2: строки в истории остаются (DELETE на BlockHistory у логина нет — история блоков
            # не стирается ничем из панели); блок возвращается теми же строками в BlockList
            for r in rows:
                w.execute("INSERT INTO dbo.BlockList (%s) VALUES (?, ?, ?, ?, ?, ?, ?)" % BLOCK_COLS,
                          (r["Userindex"], r["Uid"], r["Cou"], r["grade"], _dt(r["BlackDate"]), _dt(r["CloseDate"]), r["Reason"]))
            w.execute("UPDATE dbo.Us_member SET us_block = ? WHERE Userindex = ?", (a.get("us_block_before", 5), uid))
        except BaseException:
            w.close()
            raise
        expired = len(rows) - len(_active(rows))
        msg = "блок учётки %s возвращён откатом" % uid
        if expired:                                                      # перепроверка 6 М9
            msg += "; истёкших строк %d — сервер снимет их при следующем входе" % expired
        return {"before": {"us_block": 0}, "after": {"us_block": a.get("us_block_before")}, "rows": len(rows),
                "message": msg, "_commit": w.commit, "_close": w.close}


class _Adapter:
    """GameReader → интерфейс писателя (rows) для предпросмотра."""

    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)
