# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""gmflag.py — GM-флаг учётки (Joy1.dbo.CharGmInfo): выдать / снять (волна А1 «Учётки», решение владельца 19.11 п.4). 19.11.2026.

РАЗБОР — research_accounts_rest.md §3 (живые процедуры и патчи):
  чтение   Joy1.dbo.UPCharGMInfo @Userindex (DBManager при загрузке персонажа, ответ 2801 → CUser+0x40B9F): 1, если у учётки есть
           ЛЮБАЯ строка CharGmInfo (Charidx и GMFlag не важны). Признак учётки; действует со следующей загрузки персонажа.
  гейт     операторские опкоды — номер 0…5000 (sub_52ECF0) И флаг (P47 A, P123). Только флаг — общая точка P47_IsGmUser:
           P73 ExemptOperators (EAC не кикает), P69 (не считается в автоблок целостности), P68 OperatorExempt (без правил имени),
           P81 (действия 300/301 — «скрытый оператор»), P25/P41 (скрытие, рейтинг), SQL A13_NameGuard.
  запись   как AsdaStoryOp.dbo.OPCharGMUpdate: режим 0 — INSERT (UserIndex, Charidx, GMFlag 1), GMDate — умолчание getdate();
           режим 1 — DELETE по (Userindex, Charidx). Панель снимает ВСЕ строки учётки (иначе флаг остался бы — UPCharGMInfo
           смотрит любую строку). ⚠ Стоковую OPCharGMDelete (стирает ВСЕ строки старше 31 дня — оба живых оператора 2010 и 2012)
           панель НЕ вызывает; EXECUTE процедур dbo у asda_ops нет.
ПРАВИЛА (решение владельца): ВЫДАЧА — только учётки 1…5000 (служебные); СНЯТИЕ — любой учётке (ревизия 28 М-1) — у учётки > 5000 флаг не даёт GM-команд, но даёт обходы выше;
  только владелец (право accounts.gm_flag). Учётка > 5000 со строкой CharGmInfo — карточка показывает предупреждение.
ИГРОК В ИГРЕ — флаг сменится со следующей загрузки персонажа; по желанию (kick) — «кик + запись» мостом P127 (core/ops.py).
ОТКАТ — по снимку журнала: выдача — удаляется ровно вставленная строка; снятие — строки возвращаются с прежними GMDate, если у
  учётки с тех пор не появилось новых.
ЗАПИСЬ — asda_ops: SELECT, INSERT, DELETE Joy1.dbo.CharGmInfo (sql/adminc_04_ops.sql; UPDATE нет). Побочных эффектов при импорте нет.
"""
import datetime
import json

from core import bridge, db
from core.ops import Operation, OpRefused, register

OPERATOR_MAX_UID = 5000
GM_CHARIDX = 0            # строка учётки (как вторая живая строка оператора 2: Charidx 0); UPCharGMInfo слот не смотрит
BYPASS_WARN = ("GM-флаг даёт учётке: GM-команды (номер ≤ 5000), обход EAC-кика (P73 ExemptOperators), автоблока целостности (P69), "
               "правил имени (P68, A13) и невидимость действиями 300/301 (P81)")
UNDO_GAME_WARN = ("учётка игровая (номер > 5000): откат этого снятия вернёт ей строку CharGmInfo — GM-команд она не даёт, но снова "
                  "обходит EAC-кик, автоблок и правила имени")
NEXT_LOAD = "флаг действует со следующей загрузки персонажа (вход или смена персонажа)"


def _uid(p, grant=True):
    """Номер учётки. Выдача — только служебным 1…5000; снятие — любой учётке (ревизия 28 М-1, решение координатора 19.11:
    снять строку у игровой учётки > 5000 владелец может — это убирает обходы)."""
    try:
        uid = int(p["uid"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры")
    if uid <= 0:
        raise OpRefused("неверные параметры")
    if grant and uid > OPERATOR_MAX_UID:
        raise OpRefused("GM-флаг — только служебным учёткам (номер ≤ %d): у игровой учётки флаг не даёт GM-команд, но обходит "
                        "EAC-кик, автоблок и правила имени (решение владельца)" % OPERATOR_MAX_UID)
    return uid


def _ms(v):
    return v.strftime("%Y-%m-%d %H:%M:%S.") + "%03d" % (v.microsecond // 1000) if isinstance(v, datetime.datetime) else v


def _rows(w, uid, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    return [dict(r, GMDate=_ms(r["GMDate"])) for r in
            w.rows("SELECT UserIndex, Charidx, GMFlag, GMDate FROM dbo.CharGmInfo%s WHERE UserIndex = ? ORDER BY Charidx" % hint, (uid,))]


def _login(w, uid):
    r = w.rows("SELECT Us_id, Flag, UserNum FROM AsdaStoryOp.dbo.Us_member WHERE Userindex = ?", (uid,))
    if not r:
        raise OpRefused("учётки %d нет" % uid)
    return r[0]


def _online(w, uid, m):
    return (m.get("Flag") not in (None, 0)) or (m.get("UserNum") not in (None, -1)) or bool(
        w.rows("SELECT TOP 1 Charidx FROM dbo.CharPos WHERE Userindex = ? AND UserNum <> -1", (uid,)))


class _Adapter:
    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)


def _sig(rows):
    return {"rows": [[r["Charidx"], r["GMFlag"], r["GMDate"]] for r in rows]}


class _GmOp(Operation):
    perm, reversible = "accounts.gm_flag", True
    grant = True

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _plan(self, w, p, lock=False):
        uid = _uid(p, self.grant)
        m = _login(w, uid)
        rows = _rows(w, uid, lock)
        if self.grant and rows:
            raise OpRefused("у учётки %s (%d) GM-флаг уже есть (строк CharGmInfo: %d)" % (m["Us_id"], uid, len(rows)))
        if not self.grant and not rows:
            raise OpRefused("у учётки %s (%d) GM-флага нет" % (m["Us_id"], uid))
        text = ("выдать GM-флаг учётке %s (%d)" if self.grant else "снять GM-флаг учётки %s (%d): строк CharGmInfo %d") % (
            (m["Us_id"], uid) if self.grant else (m["Us_id"], uid, len(rows)))
        return uid, m, rows, text

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = _Adapter(r)
                uid, m, rows, text = self._plan(ad, p)
                online = _online(ad, uid, m)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = [BYPASS_WARN] if self.grant else []
        if not self.grant and uid > OPERATOR_MAX_UID:
            # ревизия 28 М-1: откат этого снятия вернёт строку ИГРОВОЙ учётке — это и есть выдача с обходами
            warn.append(UNDO_GAME_WARN)
        if online and not (p.get("kick") and bridge.plan_offer(uid, False)):
            warn.append("игрок сейчас в игре: " + NEXT_LOAD)
        elif not online:
            warn.append(NEXT_LOAD)
        return {"text": text, "expect": _sig(rows), "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            uid, m, rows, text = self._plan(w, p, lock=True)
            if _sig(rows) != prev["expect"] or ("expect" in p and p["expect"] != _sig(rows)):
                raise OpRefused("пока вы смотрели предпросмотр, строки CharGmInfo изменились — повторите")
            if self.grant:
                ins = w.rows("INSERT INTO dbo.CharGmInfo (UserIndex, Charidx, GMFlag) OUTPUT inserted.UserIndex, inserted.Charidx, "
                             "inserted.GMFlag, inserted.GMDate VALUES (?, ?, 1)", (uid, GM_CHARIDX))
                if len(ins) != 1:
                    raise OpRefused("строка CharGmInfo не записана")
                after = {"uid": uid, "row": dict(ins[0], GMDate=_ms(ins[0]["GMDate"]))}
            else:
                if w.execute("DELETE FROM dbo.CharGmInfo WHERE UserIndex = ?", (uid,)) != len(rows):
                    raise OpRefused("строки CharGmInfo изменились при записи — ничего не записано")
                after = {"uid": uid, "rows": rows}
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "rows": rows}, "after": after, "message": text, "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        uid = a.get("uid")
        if not uid:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            now = _rows(w, uid, lock=True)
            if self.grant:
                r0 = a.get("row") or {}
                n = w.execute("DELETE FROM dbo.CharGmInfo WHERE UserIndex = ? AND Charidx = ? AND GMFlag = ? AND "
                              "CONVERT(varchar(23), GMDate, 121) = ?", (uid, r0.get("Charidx"), r0.get("GMFlag"), r0.get("GMDate")))
                if n != 1:
                    raise OpRefused("выданной строки CharGmInfo уже нет — откат не выполнен")
                msg = "GM-флаг учётки %s снят откатом" % uid
            else:
                if now:
                    raise OpRefused("у учётки с тех пор снова есть строки CharGmInfo — откат не выполнен")
                for r in a.get("rows") or []:
                    w.execute("INSERT INTO dbo.CharGmInfo (UserIndex, Charidx, GMFlag, GMDate) VALUES (?, ?, ?, ?)",
                              (uid, r["Charidx"], r["GMFlag"], datetime.datetime.strptime(r["GMDate"], "%Y-%m-%d %H:%M:%S.%f")
                               if r.get("GMDate") else None))
                msg = "GM-флаг учётки %s возвращён откатом" % uid
                if int(uid) > OPERATOR_MAX_UID:
                    msg = "GM-флаг игровой учётки %s возвращён откатом: она снова обходит EAC-кик, автоблок и правила имени" % uid
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "rows": now}, "after": {"uid": uid}, "message": msg, "_commit": w.commit, "_close": w.close}


@register
class GmGrant(_GmOp):
    name, title, grant = "account.gm_grant", "Учётка: выдать GM-флаг", True


@register
class GmRevoke(_GmOp):
    name, title, grant = "account.gm_revoke", "Учётка: снять GM-флаг", False
