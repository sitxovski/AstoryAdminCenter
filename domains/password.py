# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""password.py — пароль игровой учётки (волна А1, план §4.А «пароль»). 17.11.2026.

РАЗБОР — P52 (AstoryServer/Docs/SQL/ac1_password_check.md, ac1_01_migrate.sql; памятка login-password-check-p52):
  хранение  AsdaStoryOp.dbo.Us_member: us_pwsalt BINARY(16), us_pwhash BINARY(32) = SHA2_256(us_pwsalt + LOWER(md5hex)) —
            dbo.FN_AC_PwHash; us_pwset — когда задан; us_pwfail / us_pwfail_at — неудачи подряд (замок UPUserLogin:
            us_pwfail ≥ 10 и последняя неудача моложе 15 мин → статус 3 даже верному паролю; успешный вход обнуляет).
  провод    клиент шлёт MD5(пароль) hex (cred+81), LoginManager не хеширует; перед MD5 клиент снимает ТОЛЬКО ведущие
            пробелы (TrimCredential@0xF153C0; порт AsdaLoginGameMode_Login.cpp), поле пароля — до 50 знаков (login_jui.ini
            LOGIN_EDIT01 LimitText 50). Пароль — только печатный ASCII (MD5 у клиента от ANSI-байтов, у базы Arabic).
  служебное UP_AC_SetPassword делает то же самое; панель пишет столбцы сама (EXECUTE у asda_ops запрещён на уровне базы):
            соль — os.urandom(16), хеш — sha256(соль + md5hex), правила — как dbo.FN_AC_PwMd5Hex. Совпадение формулы с
            FN_AC_PwHash проверяет живой самотест (HASHBYTES на стороне SQL Server).
ОПЕРАЦИИ
  account.set_password  новый пароль: соль, хеш, us_pwset = сейчас, замок снят (как UP_AC_SetPassword). НЕОБРАТИМО: прежний
                        хеш панель не хранит (журнал панели секретов не держит) — вернуть можно только новым паролем.
  account.pw_unlock     снять замок неудач (us_pwfail = 0, us_pwfail_at = NULL); откат возвращает прежние значения.
Пароль в журнал не попадает (ключ «password» — audit.SECRET_KEYS), в тексты и предпросмотр — тоже. Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import os

from core import db
from core.ops import Operation, OpRefused, register

OPERATOR_MAX_UID = 5000                   # служебные учётки (players.OPERATOR_MAX_UID): только владелец
PW_MAX = 50                               # LOGIN_EDIT01 LimitText (окно входа) = @Plain NVARCHAR(50) у UP_AC_SetPassword
PW_SHORT = 6                              # короче — только предупреждение (сервер нижнего предела не ставит)
LOCK_FAILS, LOCK_MIN = 10, 15             # константы замка в теле UPUserLogin (@MaxFail, @LockMin)


def md5hex(plain):
    """Как клиент и dbo.FN_AC_PwMd5Hex: ведущие пробелы снять, только печатный ASCII → MD5 hex (нижний регистр)."""
    if not isinstance(plain, str):
        raise OpRefused("пароль не задан")
    s = plain.lstrip(" ")
    if not s:
        raise OpRefused("пароль пустой")
    if any(not (" " <= c <= "~") for c in s):
        raise OpRefused("пароль — только латиница, цифры и печатные знаки ASCII (клиент считает MD5 от байтов ANSI)")
    if len(s) > PW_MAX:
        raise OpRefused("пароль длиннее %d знаков — в поле входа клиента столько не ввести" % PW_MAX)
    return hashlib.md5(s.encode("ascii")).hexdigest()


def pw_hash(salt, hexs):
    """= dbo.FN_AC_PwHash: SHA2_256(соль + CONVERT(VARBINARY, LOWER(md5hex)))."""
    return hashlib.sha256(bytes(salt) + hexs.lower().encode("ascii")).digest()


def lock_state(m, now=None):
    """→ (заперто ли сейчас, до какого времени | None)."""
    fails, at = int(m.get("us_pwfail") or 0), m.get("us_pwfail_at")
    if fails < LOCK_FAILS or not at:
        return False, None
    until = at + datetime.timedelta(minutes=LOCK_MIN)
    return until > (now or datetime.datetime.now()), until


def _uid(p, ctx):
    try:
        uid = int(p["uid"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры")
    if uid <= 0:
        raise OpRefused("неверные параметры")
    if uid <= OPERATOR_MAX_UID and (ctx is None or ctx.role != "owner"):
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return uid


def _member(w, uid, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Userindex, Us_id, Flag, UserNum, Loginidx, Portalidx, us_pwset, us_pwfail, us_pwfail_at, "
               "CASE WHEN us_pwhash IS NULL THEN 0 ELSE 1 END AS has_pw FROM dbo.Us_member%s WHERE Userindex = ?" % hint, (uid,))
    if not r:
        raise OpRefused("учётки %d нет" % uid)
    return r[0]


def _ms(v):
    return v.strftime("%Y-%m-%d %H:%M:%S.") + "%03d" % (v.microsecond // 1000) if v else None


def _sig(m, fails=True):
    """Отпечаток для сверки с предпросмотром. Смене пароля счётчик неудач не важен (замок всё равно снимается; перепроверка 14 М:
    при подборе пароля каждая неудача меняла отпечаток и смена отказывала)."""
    s = {"pwset": _ms(m["us_pwset"]), "has_pw": int(m["has_pw"])}
    if fails:
        s.update(fail=int(m["us_pwfail"] or 0), fail_at=_ms(m["us_pwfail_at"]))
    return s


class _Adapter:
    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)


def _online(m):
    if (m.get("Flag") not in (None, 0)) or (m.get("UserNum") not in (None, -1)):
        return ["игрок сейчас в игре: текущая сессия не прервётся, новый пароль понадобится при следующем входе"]
    return []


@register
class AccountSetPassword(Operation):
    name, title, perm, reversible = "account.set_password", "Учётка: сменить пароль", "players.password", False

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _plan(self, w, p, ctx, lock=False):
        uid = _uid(p, ctx)
        hexs = md5hex(p.get("password"))
        m = _member(w, uid, lock)
        text = "новый пароль учётки %s (%d)" % (m["Us_id"], uid)
        return uid, hexs, m, text

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                uid, hexs, m, text = self._plan(_Adapter(r), p, ctx)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = ["прежний пароль перестанет подходить; отменить смену нельзя — только задать пароль ещё раз"]
        if len(str(p.get("password")).lstrip(" ")) < PW_SHORT:
            warn.append("пароль короче %d знаков — его легко подобрать" % PW_SHORT)
        if not m["has_pw"]:
            warn.append("у учётки пароля не было — войти в неё до сих пор было нельзя")
        if lock_state(m)[0]:
            warn.append("замок неудач будет снят")
        return {"text": text, "expect": _sig(m, False), "warnings": warn + _online(m)}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("asdastoryop")
        try:
            uid, hexs, m, text = self._plan(w, p, ctx, lock=True)
            if _sig(m, False) != prev["expect"] or ("expect" in p and p["expect"] != _sig(m, False)):
                raise OpRefused("пока вы смотрели предпросмотр, пароль учётки изменился — повторите")
            salt = os.urandom(16)
            if w.execute("UPDATE dbo.Us_member SET us_pwsalt = ?, us_pwhash = ?, us_pwset = GETDATE(), us_pwfail = 0, "
                         "us_pwfail_at = NULL WHERE Userindex = ?", (salt, pw_hash(salt, hexs), uid)) != 1:
                raise OpRefused("учётка не найдена при записи")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "pwset": _ms(m["us_pwset"]), "fail": int(m["us_pwfail"] or 0)},
                "after": {"uid": uid, "pw_changed": True}, "message": text, "_commit": w.commit, "_close": w.close}


@register
class AccountPwUnlock(Operation):
    name, title, perm, reversible = "account.pw_unlock", "Учётка: снять замок пароля", "players.password", True

    def target(self, p):
        return "account:%s" % p.get("uid")

    def _plan(self, w, p, ctx, lock=False):
        uid = _uid(p, ctx)
        m = _member(w, uid, lock)
        if not int(m["us_pwfail"] or 0) and m["us_pwfail_at"] is None:
            raise OpRefused("неудач входа нет — снимать нечего")
        locked, until = lock_state(m)
        text = "сбросить счётчик неудач входа учётки %s (%d): %d → 0%s" % (
            m["Us_id"], uid, int(m["us_pwfail"] or 0), (", замок до %s снят" % until.strftime("%d.%m %H:%M")) if locked else "")
        return uid, m, text

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                uid, m, text = self._plan(_Adapter(r), p, ctx)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        return {"text": text, "expect": _sig(m), "warnings": []}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("asdastoryop")
        try:
            uid, m, text = self._plan(w, p, ctx, lock=True)
            if _sig(m) != prev["expect"] or ("expect" in p and p["expect"] != _sig(m)):
                raise OpRefused("пока вы смотрели предпросмотр, счётчик неудач изменился — повторите")
            if w.execute("UPDATE dbo.Us_member SET us_pwfail = 0, us_pwfail_at = NULL WHERE Userindex = ?", (uid,)) != 1:
                raise OpRefused("учётка не найдена при записи")
        except BaseException:
            w.close()
            raise
        b = {"uid": uid, "us_pwfail": int(m["us_pwfail"] or 0), "us_pwfail_at": _ms(m["us_pwfail_at"]), "pwset": _ms(m["us_pwset"]),
             "loginidx": m["Loginidx"], "flag": m["Flag"], "usernum": m["UserNum"], "portalidx": m["Portalidx"]}
        return {"before": b, "after": {"uid": uid, "us_pwfail": 0, "us_pwfail_at": None, "old": b}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        b = (json.loads(row["after_json"] or "{}") or {}).get("old") or {}
        uid = b.get("uid")
        if not uid:
            raise OpRefused("в журнале нет данных для отката")
        if "flag" not in b or b.get("flag") is None:
            # перепроверка 14 М/В: при Flag NULL UPUserLogin Loginidx не обновляет — вход не заметить, откат мог бы запереть игрока
            raise OpRefused("признак входа учётки был пустым (Flag NULL) — состоявшийся вход не определить, откат не выполнен")
        at = datetime.datetime.strptime(b["us_pwfail_at"], "%Y-%m-%d %H:%M:%S.%f") if b.get("us_pwfail_at") else None
        w = db.GameWriter("asdastoryop")
        try:
            # возвращаем, только если с тех пор не было ни неудачи, ни входа (Loginidx, Flag, UserNum, Portalidx), ни смены пароля
            eq = lambda c: "(%s = ? OR (%s IS NULL AND ? IS NULL))" % (c, c)
            cols = (("Loginidx", "loginidx"), ("Flag", "flag"), ("UserNum", "usernum"), ("Portalidx", "portalidx"))
            n = w.execute("UPDATE dbo.Us_member SET us_pwfail = ?, us_pwfail_at = ? WHERE Userindex = ? AND us_pwfail = 0 "
                          "AND us_pwfail_at IS NULL AND (CONVERT(varchar(23), us_pwset, 121) = ? OR (us_pwset IS NULL AND ? IS NULL)) AND "
                          + " AND ".join(eq(c) for c, _ in cols),
                          [b["us_pwfail"], at, uid, b.get("pwset"), b.get("pwset")] + [x for _, k in cols for x in (b.get(k), b.get(k))])
            if n != 1:
                raise OpRefused("с тех пор были входы или смена пароля — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "us_pwfail": 0}, "after": b, "message": "счётчик неудач учётки %s возвращён" % uid,
                "_commit": w.commit, "_close": w.close}
