# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""audit.py — журнал действий админ-центра (AsdaAdmin.adm.audit). 16.11.2026.

Каждая запись: время, кто (id и логин панели), откуда (IP, web/cli), действие, цель, параметры, снимки «было/стало»,
итог (ok / refused / error), сообщение, связь отката (undo_of / undone_by). Запись идёт ОТДЕЛЬНЫМ соединением
с автокоммитом — она остаётся, даже если сама операция откатилась. Логину asda_admin журнал доступен только на
дописывание (DELETE запрещён, UPDATE — только undone_by), см. sql/adminc_01…03.
Пароли и секреты в журнал не попадают: параметры проходят scrub().
Побочных эффектов при импорте нет.
"""
import datetime
import decimal
import json
import uuid

from . import db

SECRET_KEYS = ("password", "pw", "pw2", "new_password", "old_password", "totp_code", "totp", "secret", "token", "csrf")


def scrub(params):
    """Копия параметров без секретов (ключи из SECRET_KEYS → «***»)."""
    if isinstance(params, dict):
        return {k: ("***" if str(k).lower() in SECRET_KEYS else scrub(v)) for k, v in params.items()}
    if isinstance(params, (list, tuple)):
        return [scrub(v) for v in params]
    return params


def _default(o):
    """Сериализация типов pyodbc/SQL в JSON."""
    if isinstance(o, (datetime.datetime, datetime.date)):
        # миллисекунды, не микросекунды: значение из журнала при откате уходит обратно в столбец datetime SQL Server
        return o.isoformat(sep=" ", timespec="milliseconds") if isinstance(o, datetime.datetime) else o.isoformat()
    if isinstance(o, decimal.Decimal):
        return int(o) if o == int(o) else float(o)
    if isinstance(o, (bytes, bytearray)):
        return "0x" + bytes(o).hex()
    if isinstance(o, uuid.UUID):
        return str(o)
    return str(o)


def to_json(v):
    """JSON (UTF-8, без экранирования кириллицы) или None."""
    if v is None:
        return None
    return json.dumps(v, ensure_ascii=False, default=_default)


def write(ctx, action, target="", params=None, before=None, after=None, result="ok", message="", undo_of=None,
          mark_undone=True):
    """Дописать запись журнала → id. Ошибка журнала не глотается: действие без записи считается сбоем."""
    cn = db.admin()
    try:
        r = db.admin_rows(cn, "SET NOCOUNT ON; INSERT adm.audit (user_id, login, ip, via, action, target, params, "
                              "before_json, after_json, result, message, undo_of) "
                              "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (ctx.user_id, ctx.login[:32], (ctx.ip or "")[:45], ctx.via[:8], action[:64],
                           (target or "")[:200], to_json(scrub(params)) if params else None,
                           to_json(before), to_json(after), result[:16], (message or "")[:1000], undo_of))
        rid = int(r[0]["id"])
        if undo_of and mark_undone:
            mark_undone_by(undo_of, rid, cn)
        return rid
    finally:
        cn.close()


def mark_undone_by(undo_of, rid, cn=None):
    """Пометить запись undo_of откаченной записью rid (после фиксации отката — перепроверка А1 В3)."""
    own = cn is None
    cn = cn or db.admin()
    try:
        db.admin_rows(cn, "UPDATE adm.audit SET undone_by = ? WHERE id = ? AND undone_by IS NULL", (rid, undo_of))
    finally:
        if own:
            cn.close()


def query(action_prefix="", login="", target="", since=None, limit=200, before_id=None):
    """Записи журнала (новые сверху) с фильтрами."""
    where, args = [], []
    if action_prefix:
        where.append("action LIKE ?")
        args.append(action_prefix.replace("%", "") + "%")
    if login:
        where.append("login = ?")
        args.append(login)
    if target:
        where.append("target LIKE ?")
        args.append("%" + target.replace("%", "") + "%")
    if since:
        where.append("at >= ?")
        args.append(since)
    if before_id:
        where.append("id < ?")
        args.append(int(before_id))
    sql = ("SELECT TOP (%d) id, at, user_id, login, ip, via, action, target, params, before_json, after_json, result, "
           "message, undo_of, undone_by FROM adm.audit %s ORDER BY id DESC" %
           (max(1, min(int(limit), 1000)), ("WHERE " + " AND ".join(where)) if where else ""))
    cn = db.admin()
    try:
        return db.admin_rows(cn, sql, tuple(args))
    finally:
        cn.close()


def get(rid):
    """Одна запись журнала или None."""
    cn = db.admin()
    try:
        r = db.admin_rows(cn, "SELECT * FROM adm.audit WHERE id = ?", (int(rid),))
        return r[0] if r else None
    finally:
        cn.close()
