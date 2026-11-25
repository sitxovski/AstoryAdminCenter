# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""panel_users.py — пользователи самой панели (не игроки): создание, роль, отключение, сброс пароля и кода. 16.11.2026.

Все изменения — операции core.ops (журнал, откат там, где он осмыслен):
  users.create          создать (владелец задаёт временный пароль; пользователь меняет его сам)  — откат = отключить
  users.set_role        сменить роль                                                             — откат = прежняя роль
  users.set_disabled    отключить / включить (отключение отзывает все сессии)                     — откат = прежнее
  users.reset_password  новый временный пароль + отзыв сессий                                     — не откатывается
  users.reset_totp      снять второй фактор (потерян телефон)                                     — не откатывается
  self.password         сменить свой пароль (нужен текущий)                                       — не откатывается
  self.totp_enable      включить свой второй фактор (секрет выдан totp_begin)                     — не откатывается
Последнего действующего владельца нельзя отключить, понизить или лишить себя прав.
Побочных эффектов при импорте, кроме регистрации операций, нет.
"""
from core import auth, config, db
from core.ops import Operation, OpRefused, register


def _user(cn, login):
    """Пользователь по логину или отказ."""
    u = auth.get_user(cn, login=login)
    if not u:
        raise OpRefused("пользователя панели %s нет" % login)
    return u


def _active_owners(cn, except_id=None):
    """Число включённых владельцев (кроме except_id)."""
    r = db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.users WHERE role = 'owner' AND disabled = 0 AND id <> ?",
                      (except_id or 0,))
    return r[0]["n"]


def _snap(u):
    """Снимок пользователя для журнала (без секретов)."""
    return {"login": u["login"], "role": u["role"], "disabled": bool(u["disabled"]), "totp_on": bool(u["totp_on"])}


def list_users():
    """Все пользователи панели (без секретов) + число активных сессий."""
    cn = db.admin()
    try:
        rows = db.admin_rows(cn, "SELECT %s, (SELECT COUNT(*) FROM adm.sessions s WHERE s.user_id = u.id AND s.revoked = 0 "
                                 "AND s.expires_abs > SYSDATETIME()) AS sessions FROM adm.users u ORDER BY u.id"
                             % ", ".join("u." + c.strip() for c in auth.USER_COLS.split(",")))
        return [auth.public_user(r) for r in rows]
    finally:
        cn.close()


@register
class CreateUser(Operation):
    name, title, perm, reversible = "users.create", "Создать пользователя панели", "users.manage", True

    def target(self, p):
        return "panel:" + str(p.get("login", ""))

    def preview(self, ctx, p):
        auth.check_login_rules(p.get("login"))
        if p.get("role") not in auth.ROLES:
            raise OpRefused("роль должна быть одной из: " + ", ".join(auth.ROLES))
        auth.check_password_rules(p.get("password"), p.get("login"))
        cn = db.admin()
        try:
            if auth.get_user(cn, login=p["login"]):
                raise OpRefused("логин %s уже занят" % p["login"])
        finally:
            cn.close()
        return {"login": p["login"], "role": p["role"], "display": (p.get("display") or "")[:64]}

    def apply(self, ctx, p, prev):
        h, s, it = auth.hash_password(p["password"])
        cn = db.admin()
        try:
            db.admin_rows(cn, "INSERT adm.users (login, display, role, pw_hash, pw_salt, pw_iter, created_by) "
                              "VALUES (?,?,?,?,?,?,?)", (prev["login"], prev["display"], prev["role"], h, s, it,
                                                         ctx.login[:64]))
            u = auth.get_user(cn, login=prev["login"])
        finally:
            cn.close()
        return {"before": None, "after": _snap(u), "message": "создан %s (%s)" % (u["login"], auth.ROLE_TITLES[u["role"]])}

    def verify(self, ctx, p, res):
        cn = db.admin()
        try:
            if not auth.get_user(cn, login=p["login"]):
                raise RuntimeError("пользователь не найден после создания")
        finally:
            cn.close()

    def undo(self, ctx, row):
        import json
        login = json.loads(row["after_json"])["login"]
        cn = db.admin()
        try:
            u = _user(cn, login)
            if u["role"] == "owner" and not _active_owners(cn, u["id"]):
                raise OpRefused("это последний владелец — отключить нельзя")
            db.admin_rows(cn, "UPDATE adm.users SET disabled = 1 WHERE id = ?", (u["id"],))
            auth.session_revoke(cn, user_id=u["id"])
            return {"before": _snap(u), "after": _snap(_user(cn, login)), "message": "создание отменено: %s отключён" % login}
        finally:
            cn.close()


@register
class SetRole(Operation):
    name, title, perm, reversible = "users.set_role", "Сменить роль", "users.manage", True

    def target(self, p):
        return "panel:" + str(p.get("login", ""))

    def preview(self, ctx, p):
        if p.get("role") not in auth.ROLES:
            raise OpRefused("роль должна быть одной из: " + ", ".join(auth.ROLES))
        cn = db.admin()
        try:
            u = _user(cn, p.get("login"))
            if u["role"] == p["role"]:
                raise OpRefused("роль уже %s" % p["role"])
            if u["role"] == "owner" and not _active_owners(cn, u["id"]):
                raise OpRefused("это последний владелец — понизить нельзя")
            return {"login": u["login"], "from": u["role"], "to": p["role"]}
        finally:
            cn.close()

    def apply(self, ctx, p, prev):
        cn = db.admin()
        try:
            u = _user(cn, prev["login"])
            db.admin_rows(cn, "UPDATE adm.users SET role = ? WHERE id = ? AND role = ?", (prev["to"], u["id"], prev["from"]))
            auth.session_revoke(cn, user_id=u["id"])        # права сессии считаются при входе — пусть войдёт заново
            return {"before": _snap(u), "after": _snap(_user(cn, prev["login"])),
                    "message": "%s: %s → %s" % (u["login"], prev["from"], prev["to"])}
        finally:
            cn.close()

    def verify(self, ctx, p, res):
        if res["after"]["role"] != p["role"]:
            raise RuntimeError("роль не изменилась (изменена параллельно?)")

    def undo(self, ctx, row):
        import json
        b = json.loads(row["before_json"])
        prev = self.preview(ctx, {"login": b["login"], "role": b["role"]})
        return self.apply(ctx, {}, prev)


@register
class SetDisabled(Operation):
    name, title, perm, reversible = "users.set_disabled", "Отключить / включить пользователя", "users.manage", True

    def target(self, p):
        return "panel:" + str(p.get("login", ""))

    def preview(self, ctx, p):
        want = bool(p.get("disabled"))
        cn = db.admin()
        try:
            u = _user(cn, p.get("login"))
            if bool(u["disabled"]) == want:
                raise OpRefused("уже %s" % ("отключён" if want else "включён"))
            if want and u["role"] == "owner" and not _active_owners(cn, u["id"]):
                raise OpRefused("это последний владелец — отключить нельзя")
            if want and u["id"] == ctx.user_id:
                raise OpRefused("себя отключить нельзя")
            return {"login": u["login"], "disabled": want}
        finally:
            cn.close()

    def apply(self, ctx, p, prev):
        cn = db.admin()
        try:
            u = _user(cn, prev["login"])
            db.admin_rows(cn, "UPDATE adm.users SET disabled = ?, fail_count = 0, locked_until = NULL WHERE id = ?",
                          (1 if prev["disabled"] else 0, u["id"]))
            if prev["disabled"]:
                auth.session_revoke(cn, user_id=u["id"])
            else:
                auth.clear_locks(u["login"])
            return {"before": _snap(u), "after": _snap(_user(cn, prev["login"])),
                    "message": "%s %s" % (u["login"], "отключён" if prev["disabled"] else "включён")}
        finally:
            cn.close()

    def undo(self, ctx, row):
        import json
        b = json.loads(row["before_json"])
        prev = self.preview(ctx, {"login": b["login"], "disabled": b["disabled"]})
        return self.apply(ctx, {}, prev)


@register
class ResetPassword(Operation):
    name, title, perm, reversible = "users.reset_password", "Сбросить пароль пользователя", "users.manage", False

    def target(self, p):
        return "panel:" + str(p.get("login", ""))

    def preview(self, ctx, p):
        cn = db.admin()
        try:
            u = _user(cn, p.get("login"))
        finally:
            cn.close()
        auth.check_password_rules(p.get("password"), u["login"])
        return {"login": u["login"]}

    def apply(self, ctx, p, prev):
        h, s, it = auth.hash_password(p["password"])
        cn = db.admin()
        try:
            u = _user(cn, prev["login"])
            db.admin_rows(cn, "UPDATE adm.users SET pw_hash = ?, pw_salt = ?, pw_iter = ?, pw_changed_at = SYSDATETIME(), "
                              "fail_count = 0, locked_until = NULL WHERE id = ?", (h, s, it, u["id"]))
            auth.session_revoke(cn, user_id=u["id"])
            auth.clear_locks(u["login"])
            return {"before": _snap(u), "after": _snap(u), "message": "пароль %s сброшен, сессии и замки входа сняты" % u["login"]}
        finally:
            cn.close()


@register
class ResetTotp(Operation):
    name, title, perm, reversible = "users.reset_totp", "Снять второй фактор", "users.manage", False

    def target(self, p):
        return "panel:" + str(p.get("login", ""))

    def preview(self, ctx, p):
        cn = db.admin()
        try:
            u = _user(cn, p.get("login"))
        finally:
            cn.close()
        if not u["totp_on"] and not u["totp_enc"]:
            raise OpRefused("второй фактор не настроен")
        return {"login": u["login"]}

    def apply(self, ctx, p, prev):
        cn = db.admin()
        try:
            u = _user(cn, prev["login"])
            db.admin_rows(cn, "UPDATE adm.users SET totp_enc = NULL, totp_on = 0, totp_last = NULL WHERE id = ?", (u["id"],))
            auth.session_revoke(cn, user_id=u["id"])
            return {"before": _snap(u), "after": _snap(_user(cn, prev["login"])),
                    "message": "второй фактор %s снят; при входе будет предложено настроить заново" % u["login"]}
        finally:
            cn.close()


@register
class SelfPassword(Operation):
    name, title, perm, reversible = "self.password", "Сменить свой пароль", "self.manage", False

    def target(self, p):
        return "panel:self"

    def preview(self, ctx, p):
        cn = db.admin()
        try:
            u = auth.get_user(cn, uid=ctx.user_id)
        finally:
            cn.close()
        # перепроверка В2-н4: под тем же семафором и замком (логин, IP), что и вход — подбор по украденной cookie
        if not u or auth._locked(u["login"], ctx.ip):
            raise OpRefused("текущий пароль неверен")
        try:
            ok = auth.verify_limited(p.get("old_password") or "", u["pw_hash"], u["pw_salt"], u["pw_iter"], ctx.ip)
        except auth.Busy as ex:
            raise OpRefused(str(ex))
        if not ok:
            cn = db.admin()
            try:
                auth._fail(cn, u, config.get(), ctx.ip)
            finally:
                cn.close()
            raise OpRefused("текущий пароль неверен")
        auth.check_password_rules(p.get("new_password"), u["login"])
        if p.get("new_password") == p.get("old_password"):
            raise OpRefused("новый пароль совпадает с текущим")
        return {"login": u["login"]}

    def apply(self, ctx, p, prev):
        h, s, it = auth.hash_password(p["new_password"])
        cn = db.admin()
        try:
            db.admin_rows(cn, "UPDATE adm.users SET pw_hash = ?, pw_salt = ?, pw_iter = ?, pw_changed_at = SYSDATETIME() "
                              "WHERE id = ?", (h, s, it, ctx.user_id))
            return {"message": "пароль изменён"}
        finally:
            cn.close()


def totp_begin(ctx):
    """Выдать новый (ещё не включённый) секрет второго фактора текущему пользователю → (uri, base32)."""
    cn = db.admin()
    try:
        u = auth.get_user(cn, uid=ctx.user_id)
        if u["totp_on"]:
            raise OpRefused("второй фактор уже включён; снять его может владелец")
        sec = auth.totp_new_secret()
        db.admin_rows(cn, "UPDATE adm.users SET totp_enc = ?, totp_last = NULL WHERE id = ? AND totp_on = 0", (auth.totp_seal(sec), u["id"]))
        return auth.totp_uri(sec, u["login"]), auth.totp_b32(sec)
    finally:
        cn.close()


@register
class SelfTotpEnable(Operation):
    name, title, perm, reversible = "self.totp_enable", "Включить второй фактор", "self.manage", False

    def target(self, p):
        return "panel:self"

    def preview(self, ctx, p):
        cn = db.admin()
        try:
            u = auth.get_user(cn, uid=ctx.user_id)
        finally:
            cn.close()
        if u["totp_on"]:
            raise OpRefused("второй фактор уже включён")
        if not u["totp_enc"]:
            raise OpRefused("сначала получите секрет (шаг 1)")
        step = auth.totp_match(auth.totp_open(u["totp_enc"]), p.get("totp_code"))
        if step is None:
            raise OpRefused("код не подошёл — проверьте время на телефоне и введите свежий код")
        return {"login": u["login"], "step": step}

    def apply(self, ctx, p, prev):
        cn = db.admin()
        try:
            # код включения сразу считается использованным (перепроверка А0 №10: он ещё ~60 с годился для входа)
            db.admin_rows(cn, "UPDATE adm.users SET totp_on = 1, totp_last = ? WHERE id = ? AND totp_enc IS NOT NULL",
                          (prev["step"], ctx.user_id))
            return {"after": {"totp_on": True}, "message": "второй фактор включён"}
        finally:
            cn.close()

