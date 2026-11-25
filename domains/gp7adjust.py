# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""gp7adjust.py — раздел «Деньги»: начисление и списание баланса gp7 (шаг А6.9, 22.11.2026; решение владельца — ADMIN_TOOL_PLAN.md §6 п.5 №4,
спецификация — research_a6_economy_20261121.md §3 строка А6.9; отчёт impl_a6_econ_20261121.md §А6.9).

ОПЕРАЦИЯ money.adjust (право money.adjust — только owner; core/auth.PERMS):
  параметры: login (учётка сайта gp7 — логин сайта, или логин / номер игровой учётки, как фильтр раздела), kind credit | debit,
  amount (целое 1…100 000), reason (5…300 знаков), req (ключ запроса UUID — один на предпросмотр и применение, идемпотентность),
  confirm_amount и confirm_login (второе подтверждение: сумма и логин сайта набраны заново), totp (из браузера — свежий код второго фактора),
  expect (отпечаток предпросмотра — баланс «было»).
  Пишет ТОЛЬКО процедура AsdaStoryLogin.adm.GP7Adjust (sql/adminc_22_gp7adjust.sql) логином asda_ops: баланс dbo.GP7Balance и строка журнала
  adm.GP7AdjustLog одной транзакцией. Предпросмотр — та же процедура с @dry = 1 (те же проверки и часы суток лимита, ничего не пишет).
  Фиксация — после записи журнала панели adm.audit (core/ops._finish); сбой журнала или фиксации — откат транзакции (деньги не двигаются);
  фиксация, ответ которой потерян, сверяется по ключу запроса (строка журнала корректировок есть — значит записано).
  Откат (ops.undo) — обратная корректировка со ссылкой undo_of на исходную (один раз; лимиты на откат не идут — он ровно обратный уже учтённой).
ЛИМИТЫ И ОТКАЗЫ — главное внутри процедуры под замком (см. шапку adminc_22); здесь — проверка ввода до базы и тексты отказов.
ПРЕДУПРЕЖДЕНИЕ testFixedBalance: шлюз при testFixedBalance > 0 показывает игроку фиксированный баланс (server.js readAccountBalance) —
  правку в базе игрок не увидит; значение — только чтение настройки шлюза белым списком (money.test_fixed_balance).
ЖУРНАЛ КОРРЕКТИРОВОК (adjustments) — чтение логином asda_admin (db_datareader AsdaStoryLogin), право money.view; корректировки — не выручка
  (в dbo.GP7PurchaseLog их нет, итоги покупок раздела не меняются).
Столбец password не читается (у asda_admin DENY, у asda_ops SELECT на [user] не выдан). Побочных эффектов при импорте нет.
"""
import json
import uuid

from core import auth, db
from core.ops import Operation, OpRefused, register
from domains import money, players

OP_MAX = 100000                   # лимит за операцию (дублирует процедуру: отказ до базы; авторитет — adm.GP7Adjust)
DAY_MAX = 500000                  # лимит за сутки, общий (только для показа; считает процедура)
REASON_MIN, REASON_MAX = 5, 300   # длина причины
KINDS = {"credit": 1, "debit": -1}   # начислить / списать → знак delta
PAGE, PAGE_MAX = 50, 200          # журнал корректировок: строк на страницу
TEST_ONLY_MAX_UID = None          # самотест ставит players.OPERATOR_MAX_UID: учётки вне 1…N (и сайт без игровой) — отказ до базы
PROC = "SET NOCOUNT ON; EXEC adm.GP7Adjust @username = ?, @delta = ?, @reason = ?, @operator = ?, @via = ?, @req_key = ?, " \
       "@expect_before = ?, @undo_of = ?, @dry = ?"
LOCK_BUSY = "баланс учётки сейчас занят шлюзом gp7 (покупка или подарок идут) — повторите через минуту"
REASONS = {                       # причина отказа процедуры → текст оператору
    "bad-args": "процедура корректировки отказала: неверные параметры",
    "bad-reason": "причина обязательна — от %d до %d знаков" % (REASON_MIN, REASON_MAX),
    "over-op-limit": "сумма выше лимита операции %d" % OP_MAX,
    "key-conflict": "ключ запроса уже занят другой корректировкой — откройте окно корректировки заново",
    "no-site-account": "учётки сайта gp7 нет — начислять некуда (строку сайта заводит шлюз при первом входе игрока в магазин)",
    "ambiguous-account": "учёток сайта gp7 с этим логином несколько — корректировка не делается",
    "open-hold": "у учётки открыт подарок gp7 (заморожено, не выдано) — сначала его выдача или возврат (раздел «Висящие подарки»)",
    "balance-changed": "баланс учётки изменился с предпросмотра — повторите предпросмотр",
    "below-zero": "баланс ушёл бы ниже 0",
    "overflow": "баланс превысил бы 4294967295",
    "over-day-limit": "превышен суточный лимит корректировок %d (по часам сервера)" % DAY_MAX,
    "undo-not-found": "исходной корректировки нет в журнале корректировок — откат невозможен",
    "undo-is-undo": "это запись отката — повторите исходное действие вместо отката отката",
    "undo-repeat": "корректировка уже откачена",
    "undo-mismatch": "откат не совпадает с исходной корректировкой (учётка или сумма)",
}


# ---------------------------------------------------------------- проверка ввода

def _int(v, msg, lo, hi):
    """Целое из строки в [lo, hi], иначе отказ msg (только цифры, без знака и пробелов внутри)."""
    s = str(v if v is not None else "").strip()
    if not s.isdigit() or len(s) > 12:
        raise OpRefused(msg)
    n = int(s)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def plan(p):
    """Параметры операции → {login, kind, amount, delta, reason, key}; отказ — до обращения к базе."""
    p = p or {}
    login = str(p.get("login") or "").strip()
    if not login:
        raise OpRefused("укажите учётку сайта gp7 (логин сайта, логин или номер игровой учётки)")
    if len(login) > 50:
        raise OpRefused("логин — не длиннее 50 знаков")
    kind = str(p.get("kind") or "").strip()
    if kind not in KINDS:
        raise OpRefused("вид корректировки — credit (начислить) или debit (списать)")
    s = str(p.get("amount") if p.get("amount") is not None else "").strip()
    if s.lstrip("-").isdigit() and int(s) <= 0:
        raise OpRefused("сумма должна быть больше 0")
    if s.isdigit() and len(s) <= 12 and int(s) > OP_MAX:
        raise OpRefused("сумма выше лимита операции %d" % OP_MAX)
    amount = _int(s, "сумма — целое число от 1 до %d" % OP_MAX, 1, OP_MAX)
    reason = " ".join(str(p.get("reason") or "").split())
    if len(reason) < REASON_MIN or len(reason) > REASON_MAX:
        raise OpRefused("причина обязательна — от %d до %d знаков" % (REASON_MIN, REASON_MAX))
    try:
        key = str(uuid.UUID(str(p.get("req") or "").strip()))
    except ValueError:
        raise OpRefused("нет ключа запроса (req — UUID): откройте окно корректировки заново")
    return {"login": login, "kind": kind, "amount": amount, "delta": KINDS[kind] * amount, "reason": reason, "key": key}


def account(login):
    """Учётка сайта для корректировки → {site_id, username, role, uid, us_id, cat}; ровно одна строка сайта, иначе отказ."""
    acc = money.resolve_account(login)                 # нет ни в игре, ни на сайте — отказ (текст раздела «Деньги»)
    site = sorted(set(acc["site"]))
    if not site:
        raise OpRefused("у учётки «%s» нет строки сайта gp7 — начислять некуда (строку заводит шлюз при первом входе в магазин)" % login[:40])
    if len(site) > 1:
        raise OpRefused("логину «%s» соответствуют несколько учёток сайта gp7 (%s) — укажите логин сайта точно" % (
            login[:40], ", ".join(str(x) for x in site[:6])))
    try:
        with db.GameReader("asdastorylogin") as g:
            u = g.one("SELECT id, username, role FROM dbo.[user] WHERE id = ?", (site[0],))
        with db.GameReader("asdastoryop") as op:
            m = op.one("SELECT TOP (1) Userindex, Us_id FROM Us_member WHERE Us_id = ? ORDER BY Userindex", (op.text(u["username"]),))
    except db.DbError as ex:
        raise OpRefused("ошибка базы: %s" % ex)
    uid = int(m["Userindex"]) if m else None
    cat = "nolink" if uid is None else ("service" if uid <= players.OPERATOR_MAX_UID else "player")
    if TEST_ONLY_MAX_UID is not None and (uid is None or uid > TEST_ONLY_MAX_UID):
        raise OpRefused("самотест: корректировка только служебной учётке 1…%d (у «%s» — %s)" % (
            TEST_ONLY_MAX_UID, u["username"], "нет игровой" if uid is None else "игровая %d" % uid))
    return {"site_id": int(u["id"]), "username": u["username"], "role": u["role"], "uid": uid, "us_id": m["Us_id"] if m else None, "cat": cat}


def _state(site_id):
    """Баланс, открытые подарки, последние корректировки учётки (чтение asda_admin)."""
    try:
        with db.GameReader("asdastorylogin") as g:
            b = g.one("SELECT balance, present FROM dbo.GP7Balance WHERE user_id = ?", (site_id,))
            holds = int(g.one("SELECT COUNT(*) AS n FROM dbo.GP7GiftLog WHERE sender_user_id = ? AND state = 'H'", (site_id,))["n"])
            last = g.rows("SELECT TOP (5) id, delta, balance_before, balance_after, operator, created_local, undo_of, undone_by FROM adm.GP7AdjustLog "
                          "WHERE user_id = ? ORDER BY id DESC", (site_id,))
    except db.DbError as ex:
        raise OpRefused("ошибка базы: %s" % ex)
    return {"balance": int(b["balance"]) if b else 0, "present": int(b["present"]) if b else 0, "row": b is not None, "holds": holds, "last": last}


def _call(w, username, delta, reason, operator, via, key, expect=None, undo_of=None, dry=False):
    """EXEC adm.GP7Adjust внутри транзакции w → строка результата; занятый замок — понятный отказ, прочий сбой базы — исключение."""
    try:
        rows = w.rows(PROC, (username, int(delta), reason, operator[:64], via if via in ("web", "cli") else "cli", key,
                             None if expect is None else int(expect), undo_of, 1 if dry else 0))
    except db.DbError as ex:
        # ★ ревизия 63 Н-3: 1205 (выбрана жертвой взаимоблокировки — панель уступает шлюзу, DEADLOCK_PRIORITY LOW) — тот же понятный отказ
        t = str(ex)
        if any(x in t for x in ("1222", "1205", "Lock request time out", "deadlock")) or "превышено время ожидания" in t.lower()                 or "взаимоблокиров" in t.lower():
            raise OpRefused(LOCK_BUSY)
        raise
    if not rows:
        raise RuntimeError("adm.GP7Adjust не вернула результат")
    return rows[0]


def _refuse(r):
    """Строка отказа процедуры → OpRefused с понятным текстом (сумма суток — в тексте лимита)."""
    why = r["reason"]
    text = REASONS.get(why, "процедура корректировки отказала: %s" % why)
    if why == "over-day-limit" and r.get("day_used") is not None:
        text += ": за сутки уже %d" % int(r["day_used"])
    if why == "below-zero" and r.get("balance_before") is not None:
        text += ": было %d" % int(r["balance_before"])
    raise OpRefused(text)


def _logged(key):
    """Строка журнала корректировок с этим ключом (после неясной фиксации) → dict или None."""
    with db.GameReader("asdastorylogin") as g:
        return g.one("SELECT id, balance_before, balance_after, undo_of FROM adm.GP7AdjustLog WHERE req_key = ?", (key,))


def _commit_fn(w, key):
    """Фиксация транзакции корректировки; сбой фиксации — сверка по ключу: строка есть — записано (ответ потерян), нет — сбой."""
    def commit():
        try:
            w.commit()
        except Exception:
            try:
                w.cn.rollback()
            except Exception:
                pass
            w.done = True
            if _logged(key):
                return
            raise
    return commit


def _tfb_warning():
    """Предупреждение testFixedBalance (или ошибка чтения настройки) → строка или None."""
    tfb, err = money.test_fixed_balance()
    if err:
        return "%s — видит ли игрок правку, неизвестно" % err
    if tfb:
        return "testFixedBalance > 0 — игрок правку не увидит (шлюз показывает всем %d)" % tfb
    return None


def _who(a):
    """Учётка для текста: логин сайта и игровая."""
    if a["uid"] is None:
        return "%s (сайт №%d, игровой учётки нет)" % (a["username"], a["site_id"])
    return "%s (сайт №%d, игровая %d%s)" % (a["username"], a["site_id"], a["uid"], ", служебная" if a["cat"] == "service" else "")


@register
class MoneyAdjust(Operation):
    name, title, perm, reversible = "money.adjust", "Деньги: корректировка баланса gp7", "money.adjust", True
    two_factor = True                     # из браузера — свежий код второго фактора (auth.totp_confirm)

    def target(self, p):
        return "gp7:%s" % str((p or {}).get("login") or "")[:50]

    def preview(self, ctx, p):
        pl = plan(p)
        a = account(pl["login"])
        st = _state(a["site_id"])
        w = db.GameWriter("asdastorylogin")
        try:
            r = _call(w, a["username"], pl["delta"], pl["reason"], ctx.login, ctx.via, pl["key"], dry=True)
        finally:
            w.close()
        if int(r["status"]) == 2:
            raise OpRefused("запрос уже выполнен: корректировка №%d (было %d → стало %d) — повтор не двигает деньги" % (
                int(r["log_id"]), int(r["balance_before"]), int(r["balance_after"])))
        if int(r["status"]) != 3:
            _refuse(r)
        warn = []
        tw = _tfb_warning()
        if tw:
            warn.append(tw)
        if a["cat"] == "nolink":
            warn.append("у учётки сайта нет игровой учётки — баланс увидят только на сайте")
        if a["cat"] == "service":
            warn.append("служебная учётка 1…%d" % players.OPERATOR_MAX_UID)
        warn.append("корректировка — не выручка: в журнал покупок gp7 не пишется, итоги покупок не меняются")
        verb = "начислить" if pl["delta"] > 0 else "списать"
        return {"text": "%s %d gp7 учётке %s: было %d → станет %d" % (verb, pl["amount"], _who(a), int(r["balance_before"]), int(r["balance_after"])),
                "warnings": warn, "account": a, "kind": pl["kind"], "amount": pl["amount"], "delta": pl["delta"], "reason": pl["reason"],
                "req": pl["key"], "balance_before": int(r["balance_before"]), "balance_after": int(r["balance_after"]),
                "day_used": int(r["day_used"]), "day_max": int(r["day_max"]), "op_max": int(r["op_max"]), "last": st["last"],
                "present": st["present"], "confirm": "наберите сумму %d и логин сайта %s заново" % (pl["amount"], a["username"]),
                "expect": {"balance": int(r["balance_before"]), "site_id": a["site_id"]}}

    def apply(self, ctx, p, prev):
        pl = plan(p)
        a = prev["account"]
        # второе подтверждение: сумма и логин сайта набраны заново (не копия полей формы)
        if str(p.get("confirm_amount") or "").strip() != str(pl["amount"]):
            raise OpRefused("второе подтверждение: набранная сумма не совпала с суммой корректировки")
        if str(p.get("confirm_login") or "").strip().casefold() != a["username"].casefold():
            raise OpRefused("второе подтверждение: набранный логин не совпал с логином сайта %s" % a["username"])
        # ★ ревизия 63 М-2: сверка «было» обязательна — из браузера отпечаток предпросмотра (expect.balance) обязателен; консоль — свой
        #   --expect-before (его печатает --dry) или предпросмотр той же команды
        exp = p.get("expect") if isinstance(p.get("expect"), dict) else None
        if exp is None or exp.get("balance") is None:
            if ctx.via == "web":
                raise OpRefused("нет отпечатка предпросмотра (было) — повторите предпросмотр")
            exp = prev["expect"]
        try:
            exp = {"balance": int(exp["balance"]), "site_id": exp.get("site_id")}
        except (TypeError, ValueError):
            raise OpRefused("нет отпечатка предпросмотра (было) — повторите предпросмотр")
        if exp.get("site_id") not in (None, a["site_id"]):
            raise OpRefused("учётка сайта изменилась с предпросмотра — повторите предпросмотр")
        if ctx.via == "web":
            auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())
        w = db.GameWriter("asdastorylogin")
        try:
            r = _call(w, a["username"], pl["delta"], pl["reason"], ctx.login, ctx.via, pl["key"], expect=exp.get("balance"))
            if int(r["status"]) == 2:
                raise OpRefused("запрос уже выполнен: корректировка №%d (было %d → стало %d) — повтор не двигает деньги" % (
                    int(r["log_id"]), int(r["balance_before"]), int(r["balance_after"])))
            if int(r["status"]) != 1:
                _refuse(r)
        except BaseException:
            w.close()
            raise
        lid = int(r["log_id"])
        verb = "начислено" if pl["delta"] > 0 else "списано"
        after = {"log_id": lid, "site_id": a["site_id"], "username": a["username"], "uid": a["uid"], "delta": pl["delta"], "req": pl["key"],
                 "balance_before": int(r["balance_before"]), "balance_after": int(r["balance_after"]), "day_used": int(r["day_used"])}
        tw = _tfb_warning()
        msg = "%s %d gp7 учётке %s: было %d → стало %d (корректировка №%d)" % (verb, pl["amount"], _who(a), after["balance_before"],
                                                                               after["balance_after"], lid)
        if tw:
            msg += " (%s)" % tw
        return {"before": {"site_id": a["site_id"], "balance": after["balance_before"]}, "after": after, "message": msg,
                "_commit": _commit_fn(w, pl["key"]), "_close": w.close}

    def verify(self, ctx, p, res):
        a = res.get("after") or {}
        row = _logged(a.get("req"))
        # ★ ревизия 63 Н-1: «стало» = 0 (списание всего баланса) — нормальное значение, расхождение — только другое число или его нет
        if not row or a.get("balance_after") is None or int(row["id"]) != int(a.get("log_id") or 0)                 or int(row["balance_after"]) != int(a["balance_after"]):
            raise RuntimeError("после записи строки корректировки №%s в журнале корректировок нет или она другая" % a.get("log_id"))

    def undo_guard(self, row):
        a = json.loads(row.get("after_json") or "{}")
        if not a.get("log_id"):
            raise OpRefused("в журнале нет данных для отката")
        lg = _logged(a.get("req"))
        if not lg or int(lg["id"]) != int(a["log_id"]):
            raise OpRefused("корректировки №%s нет в журнале корректировок (запись не зафиксирована) — откатывать нечего" % a["log_id"])

    def undo(self, ctx, row):
        a = json.loads(row.get("after_json") or "{}")
        lid, delta = int(a["log_id"]), int(a["delta"])
        key = str(uuid.uuid4())
        reason = "откат корректировки №%d (журнал панели №%d)" % (lid, int(row["id"]))
        w = db.GameWriter("asdastorylogin")
        try:
            r = _call(w, a["username"], -delta, reason, ctx.login, ctx.via, key, undo_of=lid)
            if int(r["status"]) != 1:
                _refuse(r)
        except BaseException:
            w.close()
            raise
        nid = int(r["log_id"])
        after = {"log_id": nid, "undo_of": lid, "site_id": a.get("site_id"), "username": a["username"], "delta": -delta, "req": key,
                 "balance_before": int(r["balance_before"]), "balance_after": int(r["balance_after"])}
        msg = "откат корректировки №%d учётке %s: %s %d gp7, было %d → стало %d (корректировка №%d)" % (
            lid, a["username"], "списано" if delta > 0 else "начислено", abs(delta), after["balance_before"], after["balance_after"], nid)
        return {"before": {"log_id": lid, "balance": after["balance_before"]}, "after": after, "message": msg,
                "_commit": _commit_fn(w, key), "_close": w.close}


# ---------------------------------------------------------------- журнал корректировок (money.view)

def adjustments(q):
    """Журнал корректировок adm.GP7AdjustLog страницами (новые сверху): {rows, total, page, pages, size, day, errors}. Фильтр account —
    как у раздела «Деньги». Сутки лимита — по часам SQL-сервера (сумма |delta| без откатов за сегодня)."""
    q = q or {}
    size = money._int(q.get("size") or PAGE, "строк на странице журнала корректировок — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = money._int(q.get("page") or 1, "страница журнала корректировок — целое от 1 до 1000000", 1, 1000000)
    acc = money.resolve_account(q.get("account"))
    out = {"rows": [], "total": 0, "page": 1, "pages": 1, "size": size, "day": None, "errors": [], "op_max": OP_MAX, "day_max": DAY_MAX}
    args, cond = [], []
    if acc is not None:
        cond.append(money._in("a.user_id", acc["site"], args))
    w = (" WHERE " + " AND ".join(cond)) if cond else ""
    try:
        with db.GameReader("asdastorylogin") as g:
            if g.one("SELECT OBJECT_ID(?) AS o", ("adm.GP7AdjustLog",))["o"] is None:
                out["errors"].append("журнала корректировок adm.GP7AdjustLog нет (sql/adminc_22_gp7adjust.sql не установлен)")
                return out
            total = int(g.one("SELECT COUNT(*) AS n FROM adm.GP7AdjustLog a%s" % w, args)["n"])
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages)
            rows = g.rows("SELECT a.id, a.user_id, a.username, a.delta, a.balance_before, a.balance_after, a.reason, a.operator, a.via, a.undo_of, "
                          "a.undone_by, a.created_local, OUTER_M.Userindex, OUTER_M.Us_id FROM adm.GP7AdjustLog a OUTER APPLY (SELECT TOP (1) x.Userindex, "
                          "x.Us_id FROM %s.dbo.Us_member x WHERE x.Us_id = a.username COLLATE Arabic_CI_AS ORDER BY x.Userindex) OUTER_M%s ORDER BY a.id DESC "
                          "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % (money._op_db(), w), args + [(page - 1) * size, size])
            d = g.one("SELECT CONVERT(char(8), SYSDATETIME(), 112) AS d, ISNULL(SUM(ABS(delta)), 0) AS used, COUNT(*) AS n FROM adm.GP7AdjustLog "
                      "WHERE undo_of IS NULL AND created_local >= CAST(CAST(SYSDATETIME() AS DATE) AS DATETIME2(0)) AND created_local < "
                      "DATEADD(DAY, 1, CAST(CAST(SYSDATETIME() AS DATE) AS DATETIME2(0)))")
    except db.DbError as ex:
        out["errors"].append("журнал корректировок не прочитан: %s" % ex)
        return out
    for r in rows:
        r["Us_id"] = db.fix_text(r["Us_id"])
        r["cat"] = "nolink" if r["Userindex"] is None else ("service" if int(r["Userindex"]) <= players.OPERATOR_MAX_UID else "player")
    out.update(rows=rows, total=total, page=page, pages=pages, day={"day": d["d"], "used": int(d["used"]), "n": int(d["n"]),
                                                                   "left": max(0, DAY_MAX - int(d["used"]))})
    tw = _tfb_warning()
    out["tfb_warning"] = tw
    return out
