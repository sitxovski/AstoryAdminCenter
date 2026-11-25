# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""accountnew.py — создать игровую учётку (волна А1, план §4.А «создание»). 17.11.2026.

РАЗБОР — P52 (AstoryServer/Docs/SQL/ac1_01_migrate.sql §5 UP_AC_CreateAccount, ac1_password_check.md; памятка login-password-check-p52):
  автосоздания при входе нет (P52 убрал); учётка = одна строка AsdaStoryOp.dbo.Us_member — те же столбцы и значения, что
  UP_AC_CreateAccount (сток при первом входе ставил Poridx 3, UserNum −1): Us_block 0, Us_rdate сейчас, igsNID 0, Seridx/Gsidx/
  Threadidx/Channel 0, Poridx 3, UserNum −1, Flag 0, соль и хеш пароля, us_pwset сейчас (Realcash/BonusCash/us_pwfail — умолчания
  таблицы). Живая база 17.11: учётки 75234–75239, созданные процедурой, входили в игру и завели персонажей — других строк не нужно.
  логин     как UP_AC_CreateAccount и проверка входа P51: RTRIM, непустой, ≤ 32 (поле логина клиента LOGIN_EDIT00 LimitText 32),
            только [A-Za-z0-9_.@-]; дубль ищется без учёта регистра (коллация Us_id Arabic_CI_AS — как при входе).
  пароль    domains/password.md5hex (правила клиента и FN_AC_PwMd5Hex), хеш password.pw_hash (= FN_AC_PwHash).
ЗАПИСЬ — asda_ops: INSERT через представление dbo.adm_NewAccount (решение владельца 17.11.2026; перепроверка 15 М2 — на саму
  таблицу INSERT и DELETE запрещены, представление закрепляет значения WITH CHECK OPTION). Проверка дубля и вставка — одна
транзакция, поиск логина под UPDLOCK/HOLDLOCK (диапазон индекса IX_Us_member — второй такой же логин ждёт и получает отказ).
НЕОБРАТИМО: удалять учётки панель не может (DELETE запрещён); учётку, созданную по ошибке, — заблокировать. Пароль в журнал не попадает.
Побочных эффектов при импорте нет.
"""
import os
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import password as pw

LOGIN_MAX = 32
LOGIN_RX = re.compile(r"[A-Za-z0-9_.@-]+")          # fullmatch: «$» пропустил бы хвостовой перевод строки (перепроверка 15 М1)


def login_of(p):
    v = p.get("login")
    if not isinstance(v, str):
        raise OpRefused("логин не задан")
    v = v.rstrip(" ")
    if not v:
        raise OpRefused("логин пустой")
    if len(v) > LOGIN_MAX:
        raise OpRefused("логин длиннее %d знаков — в поле входа клиента столько не ввести" % LOGIN_MAX)
    if not LOGIN_RX.fullmatch(v):
        raise OpRefused("логин — только латиница, цифры и знаки _ . @ - (как проверяет вход в игру)")
    return v


def _exists(w, login, lock=False):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Userindex, Us_id FROM dbo.Us_member%s WHERE Us_id = ?" % hint, (login,))
    return r[0] if r else None


class _Adapter:
    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)


@register
class AccountCreate(Operation):
    name, title, perm, reversible = "account.create", "Учётка: создать", "players.create", False

    def target(self, p):
        # перепроверка 15: в журнал — только прошедший проверку логин (пароль, введённый в поле логина по ошибке, туда не попадёт)
        try:
            return "account:new:%s" % login_of(p)
        except OpRefused:
            return "account:new"

    def _plan(self, w, p, lock=False):
        login = login_of(p)
        hexs = pw.md5hex(p.get("password"))
        x = _exists(w, login, lock)
        if x:
            raise OpRefused("логин «%s» уже занят (учётка %d)" % (x["Us_id"], x["Userindex"]))
        return login, hexs, "новая учётка «%s»" % login

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                login, hexs, text = self._plan(_Adapter(r), p)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = ["удалить учётку панель не может — созданную по ошибке можно только заблокировать"]
        if len(str(p.get("password")).lstrip(" ")) < pw.PW_SHORT:
            warn.append("пароль короче %d знаков — его легко подобрать" % pw.PW_SHORT)
        return {"text": text, "expect": {"login": login}, "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("asdastoryop")
        try:
            login, hexs, text = self._plan(w, p, lock=True)
            if {"login": login} != prev["expect"] or ("expect" in p and p["expect"] != {"login": login}):
                raise OpRefused("логин изменился после предпросмотра — повторите")
            salt = os.urandom(16)
            # через представление adm_NewAccount (sql/adminc_04_ops.sql): значения закреплены WITH CHECK OPTION
            ins = w.rows("INSERT INTO dbo.adm_NewAccount (Us_id, Us_block, Us_rdate, igsNID, Seridx, Gsidx, Threadidx, Channel, Poridx, "
                         "UserNum, Flag, us_pwsalt, us_pwhash, us_pwset) OUTPUT inserted.Userindex "
                         "VALUES (?, 0, GETDATE(), 0, 0, 0, 0, 0, 3, -1, 0, ?, ?, GETDATE())", (login, salt, pw.pw_hash(salt, hexs)))
            if len(ins) != 1:
                raise OpRefused("учётка не записана")
            uid = int(ins[0]["Userindex"])
        except BaseException:
            w.close()
            raise
        return {"before": None, "after": {"uid": uid, "login": login}, "message": "%s — номер %d" % (text, uid), "uid": uid,
                "_commit": w.commit, "_close": w.close}


# ───────────── служебная учётка (номер ≤ 5000; решение владельца 19.11 п.5; sql/adminc_09_accounts.sql) ─────────────
# Userindex — IDENTITY(1, 1) (живая база 19.11: счётчик 75246, служебные — 1 и 2). Обычное создание получает номер счётчика;
# служебной нужен явный номер, а SET IDENTITY_INSERT требует ALTER на таблицу — поэтому вставка идёт процедурой
# AsdaStoryOp.adm.ServiceAccountCreate (подписана сертификатом adm_SvcAccSign — у него только ALTER Us_member; та же строка, что у обычного создания, + номер).
# Номер — наименьший свободный ПОСЛЕ занятых служебных (сейчас 3); если после последнего занятого места нет (5000 занят) —
# наименьший свободный 1…5000; свободных нет — отказ. Номер 0 не выдаётся. Счётчик IDENTITY не сдвигается (номер меньше него).
OPERATOR_MAX_UID = 5000


def next_service_uid(taken):
    """Номер новой служебной учётки по занятым номерам ≤ 5000 → int | None (свободных нет)."""
    taken = {int(x) for x in taken if 1 <= int(x) <= OPERATOR_MAX_UID}
    top = max(taken, default=0)
    if top < OPERATOR_MAX_UID:
        return top + 1
    for n in range(1, OPERATOR_MAX_UID + 1):
        if n not in taken:
            return n
    return None


@register
class AccountCreateService(Operation):
    name, title, perm, reversible = "account.create_service", "Учётка: создать служебную", "accounts.create_service", False

    def target(self, p):
        try:
            return "account:new:service:%s" % login_of(p)
        except OpRefused:
            return "account:new:service"

    def _plan(self, w, p, lock=False):
        login = login_of(p)
        hexs = pw.md5hex(p.get("password"))
        x = _exists(w, login, lock)
        if x:
            raise OpRefused("логин «%s» уже занят (учётка %d)" % (x["Us_id"], x["Userindex"]))
        hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
        uid = next_service_uid(r["Userindex"] for r in w.rows("SELECT Userindex FROM dbo.Us_member%s WHERE Userindex BETWEEN 1 AND ?"
                                                                 % hint, (OPERATOR_MAX_UID,)))
        if uid is None:
            raise OpRefused("свободных номеров служебных учёток (1…%d) нет" % OPERATOR_MAX_UID)
        return login, hexs, uid, "новая служебная учётка «%s» — номер %d" % (login, uid)

    def preview(self, ctx, p):
        try:
            with db.GameReader("asdastoryop") as r:
                login, hexs, uid, text = self._plan(_Adapter(r), p)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = ["служебная учётка (номер ≤ %d) — операторская: GM-команды сервер даёт ей только вместе с GM-флагом "
                "(отдельная операция владельца)" % OPERATOR_MAX_UID,
                "удалить учётку панель не может — созданную по ошибке можно только закрыть"]
        if len(str(p.get("password")).lstrip(" ")) < pw.PW_SHORT:
            warn.append("пароль короче %d знаков — его легко подобрать" % pw.PW_SHORT)
        return {"text": text, "expect": {"login": login, "uid": uid}, "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("asdastoryop")
        try:
            login, hexs, uid, text = self._plan(w, p, lock=True)
            sig = {"login": login, "uid": uid}
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("логин или свободный номер изменились после предпросмотра — повторите")
            salt = os.urandom(16)
            r = w.rows("EXEC adm.ServiceAccountCreate ?, ?, ?, ?", (uid, login, salt, pw.pw_hash(salt, hexs)))
            if len(r) != 1 or int(r[0]["Userindex"]) != uid:
                raise OpRefused("учётка не записана")
        except BaseException:
            w.close()
            raise
        return {"before": None, "after": {"uid": uid, "login": login, "service": True}, "message": text, "uid": uid,
                "_commit": w.commit, "_close": w.close}
