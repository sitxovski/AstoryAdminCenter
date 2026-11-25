# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""accountclose.py — «удалить учётку» = ЗАКРЫТЬ (волна А1 «Учётки», решение владельца 19.11 п.2). 19.11.2026.

РАЗБОР — Reports/admin_center/research_accounts_rest.md §7: процедуры удаления учётки у сервера нет ни в одной базе; на
  Userindex ссылаются LogInfo, ac.*, gp7 (по логину), реестр Discord, журнал панели; IDENTITY номер не переиспользует. Поэтому
  строки НЕ удаляются: закрытие = блок «навсегда» существующим механизмом панели (domains/accounts.py: us_block = 5 + строка
  BlockList, CloseDate = сейчас + 30 лет — как UPUserBlock @Time = −1) и, по желанию, новый СЛУЧАЙНЫЙ пароль (как
  domains/password.py / UP_AC_SetPassword: соль, хеш, us_pwset, замок неудач снят; пароль никто не знает и нигде не печатается).
  Персонажи, склад, gp7, Discord — не трогаются (снятие блока возвращает всё как было).
ИГРОК В ИГРЕ — «кик + запись» через мост P127 (core/ops.py: предпросмотр кладёт учётку в план кика, run кикает и строит новый
  предпросмотр на подтверждение); моста нет — блок всё равно ставится: доиграет до выхода, вход и смена карты будут отклонены.
ОТКАТ (по образцу account.block и account.pw_unlock): удаляется ровно вставленная строка блока, us_block — как было (если других
  строк нет); если пароль менялся — возвращаются прежние соль, хеш и us_pwset, но только если с тех пор пароль не меняли (соль
  та, что поставило закрытие). Прежние соль и хеш хранятся в AsdaAdmin.adm.pw_saved (журнал adm.audit секретов не держит и
  виден в интерфейсе; это те же байты, что лежат в Us_member, — логин панели их и так читает); откат строку удаляет.
ПРАВА: accounts.close — owner, admin; служебные учётки (≤ 5000) закрывает только владелец; откат — audit.undo (owner).
ЗАПИСЬ — asda_ops (UPDATE us_block и us_pw*, INSERT/DELETE BlockList — права блока и пароля, sql/adminc_04_ops.sql), одна транзакция.
Побочных эффектов при импорте нет.
"""
import datetime
import json
import os
import secrets
import uuid

from core import bridge, db
from core.ops import Operation, OpRefused, register
from domains import accounts as acc
from domains import password as pw

CLOSE_REASON = "account closed"          # причина строки BlockList (латиница — кодировка столбца Reason, как у блока)


def _reason(p):
    extra = str(p.get("reason") or "").strip()
    reason = CLOSE_REASON + (": " + extra if extra else "")
    if not acc.REASON_RX.match(reason):
        raise OpRefused("причина — до 280 знаков латиницей (столбец Reason в кодировке базы)")
    return reason


def _member(w, uid, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Userindex, Us_id, us_block, Flag, UserNum, us_pwsalt, us_pwhash, us_pwset, us_pwfail, us_pwfail_at FROM dbo.Us_member%s "
               "WHERE Userindex = ?" % hint, (uid,))
    if not r:
        raise OpRefused("учётки %d нет" % uid)
    return r[0]


def _sig(m, rows):
    return {"us_block": m["us_block"], "rows": len(rows), "pwset": pw._ms(m["us_pwset"])}


def _vault_put(uid, m, new_salt):
    """Прежние соль/хеш/us_pwset → AsdaAdmin.adm.pw_saved → токен (строкой) для журнала."""
    tok = str(uuid.uuid4())
    cn = db.admin()
    try:
        db.admin_rows(cn, "INSERT adm.pw_saved (token, uid, old_salt, old_hash, old_pwset, new_salt) VALUES (?, ?, ?, ?, ?, ?)",
                      (tok, uid, m["us_pwsalt"], m["us_pwhash"], m["us_pwset"], new_salt))
    finally:
        cn.close()
    return tok


VAULT_GC_AGE_MIN = 60     # строка моложе часа не трогается (операция может ещё идти: запись журнала, фиксация)


def vault_gc():
    """Ревизия 28 К-5: удалить строки adm.pw_saved, которые не нужны ни одному откату — token не встречается в успешной
    неоткаченной записи account.close (сироты: журнал не записался или фиксация игровой базы не прошла). → число удалённых."""
    cn = db.admin()
    try:
        r = db.admin_rows(cn, "SET NOCOUNT ON; DELETE p OUTPUT deleted.token FROM adm.pw_saved p WHERE p.at < DATEADD(MINUTE, ?, SYSDATETIME()) "
                              "AND NOT EXISTS (SELECT 1 FROM adm.audit a WHERE a.action = 'account.close' AND a.result = 'ok' "
                              "AND a.undone_by IS NULL AND LOWER(a.after_json) LIKE '%' + LOWER(CONVERT(varchar(36), p.token)) + '%')",
                          (-VAULT_GC_AGE_MIN,))
    finally:
        cn.close()
    return len(r)


def _vault_get(tok):
    cn = db.admin()
    try:
        r = db.admin_rows(cn, "SELECT uid, old_salt, old_hash, old_pwset, new_salt FROM adm.pw_saved WHERE token = ?", (tok,))
    finally:
        cn.close()
    return r[0] if r else None


def _vault_drop(tok):
    cn = db.admin()
    try:
        db.admin_rows(cn, "DELETE FROM adm.pw_saved WHERE token = ?", (tok,))
    finally:
        cn.close()


def _random_md5hex():
    """Случайный пароль (печатный ASCII, 32 знака) → md5hex по правилам клиента; сам пароль нигде не сохраняется."""
    return pw.md5hex(secrets.token_urlsafe(24)[:32])


@register
class AccountClose(Operation):
    name, title, perm, reversible = "account.close", "Учётка: закрыть", "accounts.close", True

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _plan(self, w, p, ctx, lock=False):
        uid = acc._uid(p)
        if uid <= acc.OPERATOR_MAX_UID and (ctx is None or ctx.role != "owner"):
            raise OpRefused("служебные учётки (номер ≤ %d) закрывает только владелец" % acc.OPERATOR_MAX_UID)
        reason = _reason(p)
        reset = bool(p.get("password_reset"))
        m = _member(w, uid, lock)
        rows = acc._blocks(w, uid, lock)
        text = "закрыть учётку %s (%d): блок навсегда (30 лет)%s" % (m["Us_id"], uid, ", новый случайный пароль" if reset else "")
        return uid, reason, reset, m, rows, text

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                uid, reason, reset, m, rows, text = self._plan(acc._Adapter(r), p, ctx)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = ["строки учётки не удаляются: персонажи, склад и журналы остаются; откат журналом снимает блок%s"
                % (" и возвращает прежний пароль" if reset else "")]
        if reset:
            warn.append("новый пароль случайный и нигде не показывается — войти в учётку нельзя, пока её не откроют")
        if acc._active(rows):
            warn.append("у учётки уже %d действующих строк блока — добавится ещё одна" % len(acc._active(rows)))
        online = acc._online_note(m)
        if online and not (p.get("kick", True) and bridge.plan_offer(uid, False)):
            warn += online
        return {"text": text, "expect": _sig(m, rows), "warnings": warn}

    def apply(self, ctx, p, prev):
        if p.get("password_reset"):
            try:
                vault_gc()                                   # ревизия 28 К-5: сироты прежних закрытий (best effort)
            except db.DbError:
                pass
        w = db.GameWriter("asdastoryop")
        tok = None
        try:
            uid, reason, reset, m, rows, text = self._plan(w, p, ctx, lock=True)
            if _sig(m, rows) != prev["expect"] or ("expect" in p and p["expect"] != _sig(m, rows)):
                raise OpRefused("пока вы смотрели предпросмотр, учётка изменилась — повторите")
            ins = w.rows("INSERT INTO dbo.BlockList (Userindex, Uid, Cou, grade, BlackDate, CloseDate, Reason) "
                         "OUTPUT inserted.Userindex, inserted.Uid, inserted.Cou, inserted.grade, inserted.BlackDate, "
                         "inserted.CloseDate, inserted.Reason VALUES (?, ?, 1, 1, GETDATE(), DATEADD(YEAR, 30, GETDATE()), ?)",
                         (uid, m["Us_id"], reason))
            if len(ins) != 1:
                raise OpRefused("строка блока не записана")
            if w.execute("UPDATE dbo.Us_member SET us_block = 5 WHERE Userindex = ?", (uid,)) != 1:
                raise OpRefused("учётка не найдена при записи")
            if reset:
                salt = os.urandom(16)
                if w.execute("UPDATE dbo.Us_member SET us_pwsalt = ?, us_pwhash = ?, us_pwset = GETDATE(), us_pwfail = 0, "
                             "us_pwfail_at = NULL WHERE Userindex = ?", (salt, pw.pw_hash(salt, _random_md5hex()), uid)) != 1:
                    raise OpRefused("учётка не найдена при записи")
                tok = _vault_put(uid, m, salt)              # до фиксации: сбой сохранения — ничего не записано
        except BaseException:
            w.close()
            if tok:
                try:
                    _vault_drop(tok)
                except Exception:
                    pass
            raise
        return {"before": {"uid": uid, "us_block": m["us_block"], "pwset": pw._ms(m["us_pwset"])},
                "after": {"uid": uid, "us_block": 5, "us_block_before": m["us_block"], "row": ins[0], "pw_reset": reset,
                          "pw_token": tok, "pwfail": int(m["us_pwfail"] or 0), "pwfail_at": pw._ms(m["us_pwfail_at"])},
                "message": text, "_commit": w.commit, "_close": w.close}

    def verify(self, ctx, p, res):
        acc.AccountBlock().verify(ctx, p, res)

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        uid, r0, tok = a.get("uid"), a.get("row"), a.get("pw_token")
        if not uid or not r0:
            raise OpRefused("в журнале нет данных для отката")
        v = None
        if tok:
            v = _vault_get(tok)
            if not v or int(v["uid"]) != int(uid):
                raise OpRefused("прежний пароль учётки не сохранён — откат не выполнен (снимите блок операцией «Снять блок»)")
        w = db.GameWriter("asdastoryop")
        try:
            m = _member(w, uid, lock=True)
            where, params = acc._row_where(r0)
            if w.execute("DELETE TOP (1) FROM dbo.BlockList WHERE %s" % where, params) != 1:
                raise OpRefused("строки этого блока уже нет (сняли или истёк) — откат не выполнен")
            left = acc._blocks(w, uid)
            back = m["us_block"] if left else a.get("us_block_before", 0)
            w.execute("UPDATE dbo.Us_member SET us_block = ? WHERE Userindex = ?", (back, uid))
            if v:
                if m["us_pwsalt"] is None or bytes(m["us_pwsalt"]) != bytes(v["new_salt"]):
                    raise OpRefused("пароль учётки с тех пор меняли — откат не выполнен (снимите блок операцией «Снять блок»)")
                # счётчик неудач — как был до закрытия, если с тех пор неудач не было (закрытие его обнулило)
                at = datetime.datetime.strptime(a["pwfail_at"], "%Y-%m-%d %H:%M:%S.%f") if a.get("pwfail_at") else None
                if w.execute("UPDATE dbo.Us_member SET us_pwsalt = ?, us_pwhash = ?, us_pwset = ?, "
                             "us_pwfail = CASE WHEN us_pwfail = 0 AND us_pwfail_at IS NULL THEN ? ELSE us_pwfail END, "
                             "us_pwfail_at = CASE WHEN us_pwfail = 0 AND us_pwfail_at IS NULL THEN ? ELSE us_pwfail_at END "
                             "WHERE Userindex = ? AND us_pwsalt = ?",
                             (v["old_salt"], v["old_hash"], v["old_pwset"], int(a.get("pwfail") or 0), at, uid, bytes(v["new_salt"]))) != 1:
                    raise OpRefused("строка учётки изменилась при записи — ничего не записано")
        except BaseException:
            w.close()
            raise

        def commit():
            w.commit()
            if tok:                                          # прежний пароль возвращён — копия больше не нужна
                try:
                    _vault_drop(tok)
                except Exception:
                    pass
        msg = "учётка %s открыта откатом%s" % (uid, ": прежний пароль возвращён" if v else "")
        return {"before": {"us_block": m["us_block"]}, "after": {"us_block": back, "pw_restored": bool(v)}, "message": msg,
                "_commit": commit, "_close": w.close}


def closed_state(blocks, now=None):
    """Учётка закрыта панелью: есть действующая строка блока с причиной «account closed…» (для карточки)."""
    now = now or datetime.datetime.now()
    return any((b.get("Reason") or "").startswith(CLOSE_REASON) and b.get("CloseDate") and b["CloseDate"] > now for b in blocks)
