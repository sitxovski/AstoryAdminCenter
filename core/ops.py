# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""ops.py — операция: единица любого изменения в админ-центре. 16.11.2026.

ЖИЗНЬ ОПЕРАЦИИ  (run): права → preview → [dry: вернуть предпросмотр] → apply → журнал «ok» → фиксация → verify.
  preview(ctx, p)          → dict: что изменится («было → станет», кто пропущен и почему, expect — отпечаток). Ничего не пишет.
  apply(ctx, p, prev)      → dict(before=…, after=…, message=…[, _commit, _close]). Операция с отложенной фиксацией
                             (_commit) пишет в открытой транзакции; _finish сначала пишет журнал, затем фиксирует; сбой
                             фиксации — отдельная запись «error»; при ошибке apply транзакция закрывается без фиксации.
  verify(ctx, p, res)      → None или исключение; идёт ПОСЛЕ фиксации — сбой проверки пишется в журнал, записанное
                             остаётся (откатывается через журнал).
  undo(ctx, row)           → dict как у apply; только для reversible = True. Новая запись журнала с undo_of; метка
                             «откачено» у исходной записи ставится после фиксации отката (mark_undone_by).
Отказ по правилам — OpRefused (итог refused), сбой — любое другое исключение (итог error). Обе ветки пишутся в журнал.
ИСКЛЮЧЕНИЕ ИЗ «сначала журнал, потом фиксация» (★ А6.10, ревизии 72–73): обратимая операция может зафиксировать запись в apply (без
  _commit), если (1) правка атомарно пишет СВОЙ журнал с ключом запроса, оператором и причиной и (2) есть путь отката по этому журналу без
  adm.audit. Сбой audit.write после такой фиксации НЕ даёт записи «error» (_finish вызывается вне try, AsdaAdmin может быть недоступна).
  Сейчас так делает только посещаемость (domains/attendance.py: heap-таблица счёта стока — X-замок до фиксации держал бы штатные отметки
  всех игроков; откат — attendance.undo_log по adm.AttendanceAdjustLog, строки без записи «ok» помечены в разделе).
Реестр операций — REGISTRY (имя → экземпляр); разделы регистрируют свои операции декоратором @register.
Побочных эффектов при импорте нет.
"""
import traceback

from . import audit, auth, bridge

REGISTRY = {}   # имя операции → экземпляр Operation


class OpRefused(Exception):
    """Отказ по правилам (неверные данные, нет прав, цель в неподходящем состоянии)."""


class Ctx:
    """Кто выполняет: пользователь панели, откуда, каким путём."""

    def __init__(self, user_id, login, role, ip="", via="web"):
        self.user_id = user_id
        self.login = login
        self.role = role
        self.ip = ip
        self.via = via

    def can(self, perm):
        """Есть ли право у роли."""
        return auth.can(self.role, perm)


class Operation:
    """База операции. Наследник задаёт name, title, perm, reversible и методы."""
    name = ""            # машинное имя (раздел.действие)
    title = ""           # подпись для журнала и интерфейса
    perm = ""            # право из auth.PERMS
    reversible = False   # есть ли undo

    def target(self, p):
        """Строка цели для журнала (переопределяется)."""
        return ""

    def preview(self, ctx, p):
        raise NotImplementedError

    def apply(self, ctx, p, prev):
        raise NotImplementedError

    def verify(self, ctx, p, res):
        return None

    def undo(self, ctx, row):
        raise OpRefused("операция «%s» не откатывается" % self.title)


def register(cls):
    """Декоратор: добавить операцию в реестр."""
    inst = cls()
    if not inst.name or inst.name in REGISTRY:
        raise RuntimeError("операция без имени или дубль: %r" % inst.name)
    REGISTRY[inst.name] = inst
    return cls


def run(ctx, name, params, dry=False):
    """Выполнить операцию → dict(ok, dry, preview, result, audit_id, message)."""
    op = REGISTRY.get(name)
    if not op:
        raise OpRefused("неизвестная операция %s" % name)
    params = params or {}
    tgt = ""
    try:
        if not ctx.can(op.perm):
            raise OpRefused("нет права «%s»" % op.perm)
        tgt = op.target(params)
        # ★ А2 (мост P127, 18.11.2026): «кик + запись» одним действием. Предпросмотр в рамке плана: игрок в игре, а мост может его
        #   вывести → не отказ, а план кика; при применении — кик и ожидание штатного выхода с записью ДО apply (запись под
        #   блокировкой не должна ждать выхода). Моста нет → прежний отказ «не в игре» из самого раздела.
        with bridge.kick_plan() as plan:
            prev = op.preview(ctx, params)
        kick = sorted(plan["uids"])
        if kick and isinstance(prev, dict):
            prev["bridge_kick"] = kick
            prev["warnings"] = list(prev.get("warnings") or []) + [bridge.plan_warning(kick)]
        if dry:
            return {"ok": True, "dry": True, "preview": prev, "result": None, "audit_id": None, "message": ""}
        # ★ ревизия 25 М-2: подтверждённый предпросмотр и путь применения — один и тот же. Живой (expect.live) — применять только
        #   живым путём и тем же отпечатком; офлайн-предпросмотр, а путь стал живым или «кик + запись» — тоже отказ «повторите»
        _same_path(params, prev, kick)
        if kick:
            # ★ ревизия 24 М-1/М-3: кик — своим правом и своей записью журнала; после выхода данные игрока другие (UPLogOutGame пишет
            #   уровень, опыт, позицию, LastDate), поэтому запись по показанному ранее предпросмотру НЕ делается: строится новый
            #   предпросмотр и возвращается оператору на подтверждение (повторный запрос — обычная офлайн-запись).
            return _kick_then_confirm(ctx, op, name, tgt, params, kick)
        res = op.apply(ctx, params, prev) or {}
    except (OpRefused, auth.AuthError) as ex:      # правила (в т.ч. пароля/логина) — отказ, не сбой
        if not dry:
            audit.write(ctx, name, tgt, params, result="refused", message=str(ex))
        raise OpRefused(str(ex)) from None
    except Exception as ex:
        if not dry:
            audit.write(ctx, name, tgt, params, result="error",
                        message="%s: %s" % (ex.__class__.__name__, str(ex)[:600]))
        traceback.print_exc()
        raise
    aid = _finish(ctx, name, tgt, params, res, undo_of=None)
    try:
        op.verify(ctx, params, res)
    except Exception as ex:
        audit.write(ctx, name, tgt, params, result="error", message="проверка после записи №%s: %s" % (aid, str(ex)[:500]))
        raise
    return {"ok": True, "dry": False, "preview": prev, "result": res.get("after"), "audit_id": aid,
            "message": res.get("message", "")}


KICK_PERM = "players.kick"           # право «отключить игрока с сервера» (мост P127)
PATH_CHANGED = "состояние персонажа или узла изменилось с предпросмотра (игрок вошёл/вышел, сервер ответил иначе) — повторите предпросмотр"


def _norm(v):
    """Отпечаток для сравнения: числа как int (JSON браузера), списки/словари — рекурсивно."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and float(v).is_integer():
        return int(v)
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def _same_path(params, prev, kick):
    """Отказ, если путь применения (живой / офлайн / кик) не тот, что был в подтверждённом предпросмотре (expect из браузера)."""
    if "expect" not in params:
        return
    want = params["expect"]
    want_live = isinstance(want, dict) and "live" in want
    got_live = isinstance(prev, dict) and bool(prev.get("live"))
    if want_live != got_live or (want_live and kick):
        raise OpRefused(PATH_CHANGED)
    if want_live and _norm(want) != _norm(prev.get("expect")):
        raise OpRefused(PATH_CHANGED)


def _kick(ctx, name, tgt, params, uids, why):
    """Кик учёток мостом под правом players.kick; результат (и частичный при сбое) — отдельной записью журнала «live.kick».
    → список кикнутых. Не вышло — OpRefused (с перечнем уже отключённых)."""
    if not ctx.can(KICK_PERM):
        raise OpRefused("игрок в игре: отключить его с сервера можно только с правом «%s»" % KICK_PERM)
    try:
        kicked = bridge.kick_and_wait(uids, by=ctx.login)
    except bridge.BridgeError as ex:
        done = getattr(ex, "kicked", []) or []
        audit.write(ctx, "live.kick", tgt, {"for": name, "uids": list(uids)}, after={"kicked": done},
                    result="error" if done else "refused",
                    message="%s: %s%s" % (why, ex, ("; уже отключены: " + bridge.kicked_text(done)) if done else ""))
        raise OpRefused("игрок в игре, отключить мостом не вышло: %s%s"
                        % (ex, ("; уже отключены: " + bridge.kicked_text(done)) if done else ""))
    audit.write(ctx, "live.kick", tgt, {"for": name, "uids": list(uids)}, after={"kicked": kicked}, result="ok",
                message="%s: отключены %s" % (why, bridge.kicked_text(kicked)))
    return kicked


def _kick_then_confirm(ctx, op, name, tgt, params, uids):
    """«Кик + запись», шаг 1 из 2: кик, затем НОВЫЙ предпросмотр (уже по записанному выходу) — на подтверждение оператору."""
    kicked = _kick(ctx, name, tgt, params, uids, "перед «%s»" % op.title)
    try:
        prev2 = op.preview(ctx, params)
    except OpRefused as ex:
        raise OpRefused("игрок отключён с сервера (%s), но правка теперь невозможна: %s" % (bridge.kicked_text(kicked), ex))
    if isinstance(prev2, dict):
        prev2["warnings"] = list(prev2.get("warnings") or []) + [bridge.KICKED_WARN]
        prev2["bridge_kicked"] = kicked
    return {"ok": True, "dry": True, "preview": prev2, "result": None, "audit_id": None, "kicked": kicked,
            "message": "игрок отключён с сервера (%s); данные после выхода — в предпросмотре, проверьте и подтвердите"
                       % bridge.kicked_text(kicked)}


def _finish(ctx, name, tgt, params, res, undo_of):
    """Журнал «ok» → фиксация записи в игровой базе (если операция отдала её отложенной: res["_commit"]).
    Ревизия А1 R7: раньше игровая база фиксировалась ДО журнала — при сбое AsdaAdmin правка оставалась без записи и
    без отката. Теперь сначала журнал; если фиксация не прошла — вторая запись «error» со ссылкой на первую."""
    commit, close = res.pop("_commit", None), res.pop("_close", None)
    try:
        aid = audit.write(ctx, name, tgt, params, before=res.get("before"), after=res.get("after"), result="ok",
                          message=res.get("message", ""), undo_of=undo_of, mark_undone=False)
        if commit:
            try:
                commit()
            except Exception as ex:
                audit.write(ctx, name, tgt, params, result="error",
                            message="запись №%s НЕ зафиксирована в игровой базе: %s" % (aid, str(ex)[:500]))
                raise
        if undo_of:                        # «откачено» — только когда откат действительно зафиксирован (перепроверка В3)
            audit.mark_undone_by(undo_of, aid)
        return aid
    finally:
        if close:
            close()


def needs_two_factor(name):
    """★ ревизия 63 С-1: нужен ли второй фактор действию name из браузера — то же правило, что у постановки в задания (domains/stack.py):
    операции стойки и операции с признаком two_factor. Правило общее — и для применения, и для отката."""
    op = REGISTRY.get(name)
    return name.startswith("stack.") or bool(op is not None and getattr(op, "two_factor", False))


def undo(ctx, audit_id, params=None):
    """Откатить запись журнала № audit_id → dict как у run. params — тело запроса отката (из браузера — totp для операций со вторым
    фактором)."""
    row = audit.get(audit_id)
    if not row:
        raise OpRefused("записи журнала №%s нет" % audit_id)
    if row["result"] != "ok":
        raise OpRefused("откатывать можно только успешные записи")
    if row["undone_by"]:
        raise OpRefused("запись уже откачена записью №%s" % row["undone_by"])
    if row["undo_of"]:
        raise OpRefused("это запись отката; повторите исходное действие вместо отката отката")
    op = REGISTRY.get(row["action"])
    if not op or not op.reversible:
        raise OpRefused("действие «%s» не откатывается" % row["action"])
    if not ctx.can("audit.undo") or not ctx.can(op.perm):
        raise OpRefused("нет права на откат")
    try:
        # ★ А6.7 (ревизия 59 Н-5): операция может запретить откат отдельных записей (блок / снятие, сделанные делом античита, — только через дело)
        guard = getattr(op, "undo_guard", None)
        if guard:
            guard(row)
        # ★ ревизия 63 С-1: откат операции со вторым фактором из браузера — тоже со свежим кодом (откат корректировки баланса — это такое же
        #   движение денег); предел попыток и замок — в auth.totp_confirm, как у применения. Консоль — без кода (как у применения).
        if needs_two_factor(row["action"]) and ctx.via == "web":
            auth.totp_confirm(ctx.user_id, str((params or {}).get("totp") or "").strip())
        # ★ А2 (ревизия 24 М-1/М-3): откат при игроке в игре — отказ «в игре» под блокировкой, а мост может вывести → кик (право
        #   players.kick, своя запись журнала) и ответ «повторите откат»: после выхода данные другие, сверку отката оператор
        #   запускает заново (автоматического повтора нет)
        with bridge.kick_plan() as plan:
            try:
                res = op.undo(ctx, row) or {}
            except OpRefused:
                if not plan["blocked"]:
                    raise
                blocked = sorted(plan["blocked"])
            else:
                blocked = []
        if blocked:
            kicked = _kick(ctx, row["action"] + ".undo", row["target"], {"audit_id": audit_id}, blocked,
                           "перед откатом записи №%s" % audit_id)
            return {"ok": True, "dry": True, "preview": None, "result": None, "audit_id": None, "kicked": kicked,
                    "message": "игрок отключён с сервера (%s); повторите откат — он сверит данные после выхода"
                               % bridge.kicked_text(kicked)}
    except (OpRefused, auth.AuthError) as ex:         # ★ ревизия 63 С-1: неверный код второго фактора — отказ, не сбой
        audit.write(ctx, row["action"] + ".undo", row["target"], {"audit_id": audit_id}, result="refused",
                    message=str(ex))
        raise OpRefused(str(ex)) from None
    except Exception as ex:                          # ревизия А1 R6: сбой отката тоже в журнал
        audit.write(ctx, row["action"] + ".undo", row["target"], {"audit_id": audit_id}, result="error",
                    message="%s: %s" % (ex.__class__.__name__, str(ex)[:600]))
        traceback.print_exc()
        raise OpRefused("откат не выполнен: %s" % str(ex)[:300]) from None
    aid = _finish(ctx, row["action"] + ".undo", row["target"], {"audit_id": audit_id}, res, undo_of=int(audit_id))
    return {"ok": True, "dry": False, "preview": None, "result": res.get("after"), "audit_id": aid,
            "message": res.get("message", "")}
