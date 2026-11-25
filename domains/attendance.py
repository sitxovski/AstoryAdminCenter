# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""attendance.py — раздел «Посещаемость»: сводка и ручные «засчитать день» / «снять день» (шаг А6.10, 23.11.2026; решение владельца 23.11 —
ADMIN_TOOL_PLAN.md §5.2 строка А6.10; разбор потока и решения — Reports/admin_center/impl_a6_econ_20261121.md §А6.10).

ПОТОК СЕРВЕРА (реверс; шапка sql/adminc_25_attendance.sql): NPC → GS 2250 → DBManager «EXEC OP_Attendance» → GS 2251 (только флаг: 1 — можно,
  2 — сегодня уже получено, 3 — нет персонажа) → флаг 1: GS выдаёт предмет 68788, затем 2252 → «EXEC OP_Attendance_insert» (+1 к
  AttendanceCount.ACount и строка AttendanceDetail, Step 2). Учёт — по ПЕРСОНАЖУ (Userindex, Charidx), сутки — календарная дата часов
  SQL-сервера. В памяти GS посещаемости нет — правка видна при следующем визите к NPC, игрока в игре выводить не нужно.
СВОДКА (summary, право attendance.view — owner, admin, gm): по учётке (номер или логин), персонажу (имя точно; из карточки — учётка и слот)
  и периоду ГГГГММДД — счёт ACount, строк Detail всего и за период, первый и последний день, «сегодня уже получено» (как OP_Attendance),
  расхождение «счёт ≠ строкам», история строк Detail за период (страницы; Note «adm #N» — строка, засчитанная панелью) и журнал ручных
  отметок adm.AttendanceAdjustLog. Карточка персонажа (charrest.describe) показывает счёт и 60 дней — раздел её не дублирует, а
  продолжает (переход «Посещаемость» из карточки).
ОПЕРАЦИИ (право attendance.edit — owner, admin; служебные учётки ≤ 5000 — только owner; откат — журнал действий):
  attendance.credit  — засчитать ПРОШЕДШИЙ день (не старше 365 суток), которого нет: строка Detail (RegistDay = день 00:00, Note «adm #N»)
                       и ACount + 1 (строки счёта нет — создаётся, как у стока). Награда 68788 не выдаётся (решение №8 — награда как есть).
  attendance.revoke  — снять ПРОШЕДШИЙ засчитанный день: строка Detail этого дня удаляется, ACount − 1. Выданный предмет остаётся у игрока.
  Сегодняшний день — отказ в обе стороны: «засчитать сегодня» лишило бы игрока сегодняшней награды (OP_Attendance ответил бы «уже было»),
  «снять сегодня» дало бы её второй раз.
  Пишет ТОЛЬКО процедура Joy1.adm.AttendanceAdjust логином asda_ops (строка журнала, счёт, Detail — одной транзакцией); предпросмотр — та
  же процедура с @Dry = 1. ★ ревизия 72 М-1: фиксация — сразу после процедуры (_commit_now), ДО adm.audit: замок строки счёта держится
  миллисекунды; журнал отметок пишется атомарно с правкой. Ответ фиксации потерян — сверка по ключу запроса.
  ★ ревизия 73 М-1: сбой adm.audit ПОСЛЕ фиксации — записи в журнале действий НЕТ (ядро зовёт _finish вне try, и AsdaAdmin в этот момент
  может быть недоступна); правка видна в журнале отметок с меткой «нет в журнале действий», откат — операцией владельца
  attendance.undo_log по номеру строки adm.AttendanceAdjustLog (та же процедура, @UndoOf). Исключение записано в шапке core/ops.py.
  ★ ревизия 72 М-2: засчитать персонажу без строки счёта — только когда игрок не в игре (_first_visit_guard, предел стока).
  Откат — обратная правка процедурой со ссылкой undo_of (один раз): снятая строка возвращается с прежними RegistDay и Note.
TEST_ONLY_MAX_UID — самотест ставит 5000: учётки живых игроков (> 5000) операции не трогают (как gp7adjust). Побочных эффектов при импорте нет.
"""
import datetime
import json
import re
import uuid

from core import db
from core.ops import Operation, OpRefused, register

SVC_MAX = 5000                    # служебные учётки (players.OPERATOR_MAX_UID): правит только владелец
MAX_AGE_DAYS = 365                # засчитать — не старше (дублирует процедуру: отказ до базы; авторитет — adm.AttendanceAdjust)
REASON_MIN, REASON_MAX = 5, 300   # длина причины
REWARD_ITEM = 68788               # награда визита (Daily Attendance Package2) — выдаёт GS, панель не выдаёт и не меняет
PAGE, PAGE_MAX = 50, 200          # история: строк на страницу
WINDOW_MAX = 3660                 # окно периода, суток
DEFAULT_DAYS = 30                 # без дат — последние 30 суток
CHARS_MAX = 500                   # персонажей в сводке
TEST_ONLY_MAX_UID = None          # самотест ставит 5000: учётки вне 1…N — отказ до базы
PROC = "SET NOCOUNT ON; EXEC adm.AttendanceAdjust @Userindex = ?, @Charidx = ?, @Day = ?, @Delta = ?, @Reason = ?, @Operator = ?, @Via = ?, " \
       "@ReqKey = ?, @ExpectCount = ?, @UndoOf = ?, @Dry = ?"
NOT_INSTALLED = "журнала ручных отметок adm.AttendanceAdjustLog нет (sql/adminc_25_attendance.sql не установлен)"
LOCK_BUSY = "строки посещаемости персонажа сейчас заняты сервером — повторите через минуту"
REASONS = {                       # причина отказа процедуры → текст оператору
    "bad-args": "процедура посещаемости отказала: неверные параметры",
    "bad-reason": "причина обязательна — от %d до %d знаков" % (REASON_MIN, REASON_MAX),
    "bad-day": "день — дата ГГГГММДД",
    "not-past": "сегодняшний и будущие дни панель не трогает — сегодняшнюю отметку ставит сервер вместе с наградой",
    "too-old": "засчитать можно день не старше %d суток" % MAX_AGE_DAYS,
    "no-char": "персонажа нет",
    "count-ambiguous": "у персонажа несколько строк счёта посещаемости (Step 2) — правка не делается. Так бывает, если первый визит к NPC совпал "
                       "с правкой (сток читает счёт без замка). Исправить вручную в базе: оставить одну строку Step 2 с ACount = числу дней",
    "busy": "посещаемость этого персонажа сейчас правит другой оператор — повторите через минуту",
    "count-changed": "счёт посещаемости изменился с предпросмотра — повторите предпросмотр",
    "day-present": "этот день уже засчитан",
    "day-absent": "этот день не засчитан — снимать нечего",
    "day-ambiguous": "за этот день несколько строк посещаемости — правка не делается, нужен разбор",
    "count-low": "счёт посещаемости уже 0 — снять день нельзя (строки счёта и дней разошлись, нужен разбор)",
    "key-conflict": "ключ запроса уже занят другой правкой — откройте окно заново",
    "undo-not-found": "исходной правки нет в журнале ручных отметок — откат невозможен",
    "undo-is-undo": "это запись отката — повторите исходное действие вместо отката отката",
    "undo-repeat": "правка уже откачена",
    "undo-mismatch": "откат не совпадает с исходной правкой (персонаж, день или знак)",
    "undo-row-gone": "засчитанной панелью строки дня уже нет (её сняли позже) — откатывать нечего",
}
KINDS = {"attendance.credit": 1, "attendance.revoke": -1}


# ---------------------------------------------------------------- ввод

def _int(v, msg, lo, hi):
    """Целое из строки или числа в [lo, hi], иначе отказ msg (только цифры, без знака)."""
    if isinstance(v, bool):
        raise OpRefused(msg)
    s = str(v if v is not None else "").strip()
    if not s.isdigit() or len(s) > 10:
        raise OpRefused(msg)
    n = int(s)
    if n < lo or n > hi:
        raise OpRefused(msg)
    return n


def day_of(s, msg="день — дата ГГГГММДД"):
    """Строка ГГГГММДД → datetime.date; иначе отказ."""
    s = str(s or "").strip()
    if not re.fullmatch(r"[12][0-9]{7}", s):
        raise OpRefused(msg)
    try:
        return datetime.datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        raise OpRefused(msg)


def plan(p, role=None):
    """Параметры операции → {uid, idx, day, reason, key}; отказ — до обращения к базе."""
    p = p or {}
    uid = _int(p.get("uid"), "учётка — номер от 1 до 2147483647", 1, 2147483647)
    idx = _int(p.get("idx"), "слот персонажа — число от 0 до 255", 0, 255)
    d = day_of(p.get("day"))
    reason = " ".join(str(p.get("reason") or "").split())
    if len(reason) < REASON_MIN or len(reason) > REASON_MAX:
        raise OpRefused("причина обязательна — от %d до %d знаков" % (REASON_MIN, REASON_MAX))
    try:
        key = str(uuid.UUID(str(p.get("req") or "").strip()))
    except ValueError:
        raise OpRefused("нет ключа запроса (req — UUID): откройте окно заново")
    if uid <= SVC_MAX and role != "owner":
        raise OpRefused("посещаемость служебных учёток (номер ≤ %d) правит только владелец" % SVC_MAX)
    if TEST_ONLY_MAX_UID is not None and uid > TEST_ONLY_MAX_UID:
        raise OpRefused("самотест: правка только служебной учётке 1…%d (у цели — учётка %d)" % (TEST_ONLY_MAX_UID, uid))
    return {"uid": uid, "idx": idx, "day": d.strftime("%Y%m%d"), "date": d, "reason": reason, "key": key}


def _iso(day8):
    """ГГГГММДД → ГГГГ-ММ-ДД (для текста)."""
    return "%s-%s-%s" % (day8[:4], day8[4:6], day8[6:8])


# ---------------------------------------------------------------- чтение

def _char_state(uid, idx):
    """Имя персонажа, счёт, сегодня ли получено (как OP_Attendance), строка дня-цели не читается здесь (её читает процедура)."""
    try:
        with db.GameReader("joy1") as r:
            ch = r.one("SELECT Charname FROM dbo.Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, idx))
            if not ch:
                raise OpRefused("персонажа %d/%d нет" % (uid, idx))
            t = r.one("SELECT CONVERT(char(8), GETDATE(), 112) AS d, "
                      "(SELECT COUNT(*) FROM dbo.AttendanceDetail WHERE Userindex = ? AND Charidx = ? AND Step = 2 AND "
                      "CONVERT(varchar(10), RegistDay, 21) = CONVERT(varchar(10), GETDATE(), 21)) AS today_n", (uid, idx))
    except db.DbError as ex:
        raise OpRefused("посещаемость не прочитана: %s" % ex)
    return {"name": ch["Charname"], "today": t["d"], "today_got": int(t["today_n"]) > 0}


FIRST_VISIT = ("персонаж в игре (%s), а строки счёта посещаемости у него ещё нет — засчитайте, когда игрок выйдет. Иначе первый визит к NPC "
               "может совпасть с правкой и дать вторую строку счёта (сервер читает счёт без замка). Если игрок не в игре — признак мог "
               "остаться после падения сервера: пусть войдёт и выйдет")


def _in_game(uid):
    """Тот же признак «в игре», что items.online_state (research_online_persist.md §1.4: CharPos.UserNum ≠ −1 или Us_member Flag ≠ 0 /
    UserNum ≠ −1), но без моста P127: кикать игрока ради отметки посещаемости не нужно → (в_игре, пояснение)."""
    with db.GameReader("joy1") as r:
        inworld = r.rows("SELECT Charidx FROM CharPos WHERE Userindex = ? AND UserNum <> -1", (uid,))
    with db.GameReader("asdastoryop") as o:
        m = o.rows("SELECT Flag, UserNum FROM Us_member WHERE Userindex = ?", (uid,))
    if inworld:
        return True, "в мире слот %s" % ", ".join(str(x["Charidx"]) for x in inworld)
    # ★ ревизия 73 К-2: строки Us_member нет — войти этой учёткой нельзя (вход UPUserLogin ищет её там), значит и в игре её нет;
    #   items.online_state в этом случае отказывает в ЛЮБОЙ правке, а здесь вопрос один — может ли идти визит к NPC прямо сейчас
    if not m:
        return False, ""
    if m[0]["Flag"] is None or m[0]["UserNum"] is None or m[0]["Flag"] != 0 or m[0]["UserNum"] != -1:
        return True, "учётка вошла в игру или на выбор персонажа: Flag %s, UserNum %s" % (m[0]["Flag"], m[0]["UserNum"])
    return False, ""


def _first_visit_guard(uid, idx):
    """★ ревизия 72 М-2: засчитать (или вернуть снятый день) персонажу БЕЗ строки счёта — только когда игрок не в игре (предел стока:
    OP_Attendance_Insert читает счёт под READUNCOMMITTED и вставил бы вторую строку). Есть строка счёта — проверка не нужна."""
    try:
        with db.GameReader("joy1") as r:
            n = int(r.one("SELECT COUNT(*) AS n FROM dbo.AttendanceCount WHERE Userindex = ? AND Charidx = ? AND Step = 2", (uid, idx))["n"])
        if n:
            return
        busy, why = _in_game(uid)
    except db.DbError as ex:
        raise OpRefused("посещаемость не прочитана: %s" % ex)
    if busy:
        raise OpRefused(FIRST_VISIT % why)


def _who(uid, idx, name):
    return "%s (учётка %d, слот %d)" % (name, uid, idx)


def _call(w, pl, delta, operator, via, expect=None, undo_of=None, dry=False):
    """EXEC adm.AttendanceAdjust в транзакции w → строка результата; занятый замок — понятный отказ, прочий сбой базы — исключение."""
    try:
        rows = w.rows(PROC, (pl["uid"], pl["idx"], pl["day"], int(delta), pl["reason"], operator[:64], via if via in ("web", "cli", "test") else "cli",
                             pl["key"], None if expect is None else int(expect), undo_of, 1 if dry else 0))
    except db.DbError as ex:
        t = str(ex)
        if any(x in t for x in ("1222", "1205", "Lock request time out", "deadlock")) or "превышено время ожидания" in t.lower() \
                or "взаимоблокиров" in t.lower():
            raise OpRefused(LOCK_BUSY)
        if "(2812)" in t or "Could not find stored procedure 'adm.AttendanceAdjust'" in t:   # ★ ревизия 72 К-2: точный код «процедуры нет»
            raise OpRefused("процедуры adm.AttendanceAdjust нет (sql/adminc_25_attendance.sql не установлен)")
        raise
    if not rows:
        raise RuntimeError("adm.AttendanceAdjust не вернула результат")
    return rows[0]


def _refuse(r):
    """Строка отказа процедуры → OpRefused с понятным текстом."""
    raise OpRefused(REASONS.get(r["reason"], "процедура посещаемости отказала: %s" % r["reason"]))


def _logged(key):
    """Строка журнала ручных отметок с этим ключом → dict или None."""
    with db.GameReader("joy1") as g:
        return g.one("SELECT id, count_after, adno, undo_of FROM adm.AttendanceAdjustLog WHERE req_key = ?", (key,))


def _commit_now(w, key):
    """★ ревизия 72 М-1: фиксация СРАЗУ после процедуры, до журнала панели adm.audit — замок строки счёта персонажа (heap: сканирующий
    UPDATE стока любого игрока ждал бы его) держится миллисекунды, а не всё время записи в AsdaAdmin. Правку вместе с оператором и
    причиной атомарно пишет журнал adm.AttendanceAdjustLog в той же транзакции. ★ ревизия 73 М-1: сбой adm.audit после фиксации — записи в
    журнале действий НЕТ (ни «ok», ни «error»); правка видна в журнале отметок с меткой «нет в журнале действий», откат — attendance.undo_log.
    Сбой самой фиксации — сверка по ключу (как _commit_fn)."""
    try:
        _commit_fn(w, key)()
    finally:
        w.close()


def _commit_fn(w, key):
    """Фиксация; сбой фиксации — сверка по ключу: строка журнала есть — записано (ответ потерян), нет — сбой."""
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


class _AttOp(Operation):
    """Каркас засчитать / снять (знак — KINDS по имени операции)."""
    perm, reversible = "attendance.edit", True

    def target(self, p):
        p = p or {}
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        pl = plan(p, ctx.role)
        st = _char_state(pl["uid"], pl["idx"])
        delta = KINDS[self.name]
        if delta > 0:
            _first_visit_guard(pl["uid"], pl["idx"])
        w = db.GameWriter("joy1")
        try:
            r = _call(w, pl, delta, ctx.login, ctx.via, dry=True)
        except db.DbError as ex:
            raise OpRefused("посещаемость не прочитана: %s" % ex)
        finally:
            w.close()
        if int(r["status"]) == 2:
            raise OpRefused("запрос уже выполнен: правка №%d — повтор ничего не пишет" % int(r["log_id"]))
        if int(r["status"]) != 3:
            _refuse(r)
        who = _who(pl["uid"], pl["idx"], st["name"])
        cb, ca = int(r["count_before"]), int(r["count_after"])
        warn = ["правка видна сразу и при игроке в игре: сервер не держит посещаемость в памяти, а спрашивает базу при каждом визите к NPC"]
        if delta > 0:
            text = "засчитать день %s персонажу %s: отметок %d → %d" % (_iso(pl["day"]), who, cb, ca)
            warn.append("награда за этот день (предмет %d) не выдаётся — засчитывается только отметка" % REWARD_ITEM)
        else:
            text = "снять день %s у персонажа %s: отметок %d → %d" % (_iso(pl["day"]), who, cb, ca)
            warn.append("строка дня №%s от %s удаляется (вернуть — откатом)" % (r["adno"], str(r["regist"] or "")[:19]))
            warn.append("предмет %d, выданный за этот день, остаётся у игрока" % REWARD_ITEM)
        warn.append(("сегодня (%s) награда уже получена" if st["today_got"] else "сегодня (%s) награда ещё не получена") % _iso(st["today"]))
        if pl["uid"] <= SVC_MAX:
            warn.append("служебная учётка 1…%d" % SVC_MAX)
        return {"text": text, "warnings": warn, "uid": pl["uid"], "idx": pl["idx"], "day": pl["day"], "reason": pl["reason"], "req": pl["key"],
                "count_before": cb, "count_after": ca, "adno": r["adno"], "expect": {"count": cb}}

    def apply(self, ctx, p, prev):
        pl = plan(p, ctx.role)
        delta = KINDS[self.name]
        if delta > 0:
            _first_visit_guard(pl["uid"], pl["idx"])
        exp = p.get("expect") if isinstance(p.get("expect"), dict) else None
        if exp is None or exp.get("count") is None:
            if ctx.via == "web":
                raise OpRefused("нет отпечатка предпросмотра (счёт) — повторите предпросмотр")
            exp = prev["expect"]
        try:
            expect = int(exp["count"])
        except (TypeError, ValueError):
            raise OpRefused("нет отпечатка предпросмотра (счёт) — повторите предпросмотр")
        w = db.GameWriter("joy1")
        try:
            r = _call(w, pl, delta, ctx.login, ctx.via, expect=expect)
            if int(r["status"]) == 2:
                raise OpRefused("запрос уже выполнен: правка №%d — повтор ничего не пишет" % int(r["log_id"]))
            if int(r["status"]) != 1:
                _refuse(r)
        except db.DbError as ex:
            w.close()
            raise OpRefused("посещаемость не записана: %s" % ex)
        except BaseException:
            w.close()
            raise
        _commit_now(w, pl["key"])
        lid = int(r["log_id"])
        after = {"log_id": lid, "uid": pl["uid"], "idx": pl["idx"], "day": pl["day"], "delta": delta, "req": pl["key"],
                 "count_before": int(r["count_before"]), "count_after": int(r["count_after"]), "adno": r["adno"], "regist": r["regist"]}
        msg = "%s %s персонажу %s/%s: отметок %d → %d (правка №%d)" % ("засчитан день" if delta > 0 else "снят день", _iso(pl["day"]), pl["uid"], pl["idx"],
                                                                       after["count_before"], after["count_after"], lid)
        return {"before": {"uid": pl["uid"], "idx": pl["idx"], "count": after["count_before"]}, "after": after, "message": msg,
                }

    def verify(self, ctx, p, res):
        a = res.get("after") or {}
        row = _logged(a.get("req"))
        if not row or int(row["id"]) != int(a.get("log_id") or 0) or int(row["count_after"]) != int(a.get("count_after", -1)):
            raise RuntimeError("после записи строки правки №%s в журнале ручных отметок нет или она другая" % a.get("log_id"))

    def undo_guard(self, row):
        a = json.loads(row.get("after_json") or "{}")
        if not a.get("log_id"):
            raise OpRefused("в журнале нет данных для отката")
        lg = _logged(a.get("req"))
        if not lg or int(lg["id"]) != int(a["log_id"]):
            raise OpRefused("правки №%s нет в журнале ручных отметок (запись не зафиксирована) — откатывать нечего" % a["log_id"])

    def undo(self, ctx, row):
        a = json.loads(row.get("after_json") or "{}")
        if not a.get("log_id"):
            raise OpRefused("в журнале нет данных для отката")
        lid, delta = int(a["log_id"]), int(a["delta"])
        uid = int(a["uid"])
        if uid <= SVC_MAX and ctx.role != "owner":
            raise OpRefused("посещаемость служебных учёток (номер ≤ %d) правит только владелец" % SVC_MAX)
        if TEST_ONLY_MAX_UID is not None and uid > TEST_ONLY_MAX_UID:
            raise OpRefused("самотест: правка только служебной учётке 1…%d (у цели — учётка %d)" % (TEST_ONLY_MAX_UID, uid))
        if -delta > 0:
            _first_visit_guard(uid, int(a["idx"]))
        pl = {"uid": uid, "idx": int(a["idx"]), "day": a["day"], "key": str(uuid.uuid4()),
              "reason": "откат правки №%d (журнал панели №%d)" % (lid, int(row["id"]))}
        w = db.GameWriter("joy1")
        try:
            r = _call(w, pl, -delta, ctx.login, ctx.via, undo_of=lid)
            if int(r["status"]) != 1:
                _refuse(r)
        except db.DbError as ex:
            w.close()
            raise OpRefused("откат не записан: %s" % ex)
        except BaseException:
            w.close()
            raise
        _commit_now(w, pl["key"])
        nid = int(r["log_id"])
        after = {"log_id": nid, "undo_of": lid, "uid": uid, "idx": pl["idx"], "day": pl["day"], "delta": -delta, "req": pl["key"],
                 "count_before": int(r["count_before"]), "count_after": int(r["count_after"]), "adno": r["adno"], "regist": r["regist"]}
        msg = "откат правки №%d: %s %s персонажу %s/%s, отметок %d → %d (правка №%d)" % (
            lid, "снова засчитан день" if delta < 0 else "снят день", _iso(pl["day"]), uid, pl["idx"], after["count_before"], after["count_after"], nid)
        return {"before": {"log_id": lid, "count": after["count_before"]}, "after": after, "message": msg,
                }


@register
class AttendanceCredit(_AttOp):
    name, title = "attendance.credit", "Посещаемость: засчитать день"


@register
class AttendanceRevoke(_AttOp):
    name, title = "attendance.revoke", "Посещаемость: снять день"


def audited_log_ids():
    """Номера строк adm.AttendanceAdjustLog, у которых есть запись adm.audit «ok» (правка, откат из журнала действий или attendance.undo_log;
    номер — after.log_id) → set. AsdaAdmin не читается — DbError."""
    cn = db.admin()
    try:
        rows = db.admin_rows(cn, "SELECT after_json FROM adm.audit WHERE result = 'ok' AND action LIKE 'attendance.%'")
    finally:
        cn.close()
    out = set()
    for r in rows:
        try:
            v = json.loads(r["after_json"] or "{}").get("log_id")
        except ValueError:
            continue
        if isinstance(v, int):
            out.add(v)
    return out


@register
class AttendanceUndoLog(Operation):
    """★ ревизия 73 М-1: откат правки по номеру строки журнала отметок — для правок, у которых нет записи «ok» в журнале действий (сбой
    adm.audit после фиксации). Только владелец, с причиной; та же процедура (@UndoOf) со всеми проверками (undo-repeat, undo-row-gone,
    count-changed, отпечаток счёта). Пишет свою запись журнала действий; повторить исходное — новой правкой (своего отката нет)."""
    name, title, perm, reversible = "attendance.undo_log", "Посещаемость: откат по журналу отметок", "attendance.undo_log", False

    def target(self, p):
        return "attlog:%s" % str((p or {}).get("log_id"))[:12]

    def _plan(self, ctx, p):
        p = p or {}
        lid = _int(p.get("log_id"), "номер строки журнала отметок — целое от 1", 1, 2 ** 62)
        reason = " ".join(str(p.get("reason") or "").split())
        if len(reason) < REASON_MIN or len(reason) > REASON_MAX:
            raise OpRefused("причина обязательна — от %d до %d знаков" % (REASON_MIN, REASON_MAX))
        try:
            key = str(uuid.UUID(str(p.get("req") or "").strip()))
        except ValueError:
            raise OpRefused("нет ключа запроса (req — UUID): откройте окно заново")
        try:
            with db.GameReader("joy1") as r:
                o = r.one("SELECT id, userindex, charidx, CONVERT(char(8), day, 112) AS day, delta, undo_of, undone_by FROM adm.AttendanceAdjustLog "
                          "WHERE id = ?", (lid,))
            seen = audited_log_ids()
        except db.DbError as ex:
            raise OpRefused("посещаемость не прочитана: %s" % ex)
        if not o:
            raise OpRefused("строки №%d в журнале отметок нет" % lid)
        if o["undo_of"] is not None:
            raise OpRefused(REASONS["undo-is-undo"])
        if o["undone_by"] is not None:
            raise OpRefused(REASONS["undo-repeat"])
        if lid in seen:
            raise OpRefused("правка №%d есть в журнале действий — откат там (кнопка «Откатить» у её записи)" % lid)
        uid, idx = int(o["userindex"]), int(o["charidx"])
        if TEST_ONLY_MAX_UID is not None and uid > TEST_ONLY_MAX_UID:
            raise OpRefused("самотест: правка только служебной учётке 1…%d (у цели — учётка %d)" % (TEST_ONLY_MAX_UID, uid))
        if -int(o["delta"]) > 0:
            _first_visit_guard(uid, idx)
        return {"uid": uid, "idx": idx, "day": o["day"], "key": key, "reason": reason, "log_id": lid, "delta": -int(o["delta"])}

    def preview(self, ctx, p):
        pl = self._plan(ctx, p)
        w = db.GameWriter("joy1")
        try:
            r = _call(w, pl, pl["delta"], ctx.login, ctx.via, undo_of=pl["log_id"], dry=True)
        except db.DbError as ex:
            raise OpRefused("посещаемость не прочитана: %s" % ex)
        finally:
            w.close()
        if int(r["status"]) != 3:
            _refuse(r)
        text = "откатить правку №%d (нет в журнале действий): %s %s персонажу %d/%d, отметок %d → %d" % (
            pl["log_id"], "снять день" if pl["delta"] < 0 else "снова засчитать день", _iso(pl["day"]), pl["uid"], pl["idx"],
            int(r["count_before"]), int(r["count_after"]))
        return {"text": text, "warnings": ["правка №%d не попала в журнал действий (сбой записи журнала после сохранения) — откат по журналу отметок" % pl["log_id"]],
                "log_id": pl["log_id"], "expect": {"count": int(r["count_before"])}}

    def apply(self, ctx, p, prev):
        pl = self._plan(ctx, p)
        exp = p.get("expect") if isinstance(p.get("expect"), dict) else None
        if exp is None or exp.get("count") is None:
            if ctx.via == "web":
                raise OpRefused("нет отпечатка предпросмотра (счёт) — повторите предпросмотр")
            exp = prev["expect"]
        try:
            expect = int(exp["count"])
        except (TypeError, ValueError):
            raise OpRefused("нет отпечатка предпросмотра (счёт) — повторите предпросмотр")
        w = db.GameWriter("joy1")
        try:
            r = _call(w, pl, pl["delta"], ctx.login, ctx.via, expect=expect, undo_of=pl["log_id"])
            if int(r["status"]) == 2:
                raise OpRefused("запрос уже выполнен: правка №%d — повтор ничего не пишет" % int(r["log_id"]))
            if int(r["status"]) != 1:
                _refuse(r)
        except db.DbError as ex:
            w.close()
            raise OpRefused("откат не записан: %s" % ex)
        except BaseException:
            w.close()
            raise
        _commit_now(w, pl["key"])
        nid = int(r["log_id"])
        after = {"log_id": nid, "undo_of": pl["log_id"], "uid": pl["uid"], "idx": pl["idx"], "day": pl["day"], "delta": pl["delta"], "req": pl["key"],
                 "count_before": int(r["count_before"]), "count_after": int(r["count_after"]), "adno": r["adno"], "regist": r["regist"]}
        msg = "откат правки №%d: %s %s персонажу %s/%s, отметок %d → %d (правка №%d)" % (
            pl["log_id"], "снят день" if pl["delta"] < 0 else "снова засчитан день", _iso(pl["day"]), pl["uid"], pl["idx"],
            after["count_before"], after["count_after"], nid)
        return {"before": {"log_id": pl["log_id"], "count": after["count_before"]}, "after": after, "message": msg}

    def verify(self, ctx, p, res):
        a = res.get("after") or {}
        row = _logged(a.get("req"))
        if not row or int(row["id"]) != int(a.get("log_id") or 0):
            raise RuntimeError("после записи строки правки №%s в журнале ручных отметок нет или она другая" % a.get("log_id"))


# ---------------------------------------------------------------- сводка (attendance.view)

def _targets(q, op_db):
    """Фильтр учётки / персонажа → (условие SQL по c.Userindex / c.Charidx, параметры, описание) или (None, [], None) без фильтра."""
    acc = str(q.get("account") or "").strip()
    name = str(q.get("char") or "").strip()
    uid_s, idx_s = str(q.get("uid") or "").strip(), str(q.get("idx") or "").strip()
    if len(acc) > 50:
        raise OpRefused("логин — не длиннее 50 знаков")
    if len(name) > 20:
        raise OpRefused("имя персонажа — не длиннее 20 знаков")
    if uid_s or idx_s:
        uid = _int(uid_s, "учётка — номер от 1 до 2147483647", 1, 2147483647)
        idx = _int(idx_s, "слот персонажа — число от 0 до 255", 0, 255)
        return "c.Userindex = ? AND c.Charidx = ?", [uid, idx], "персонаж %d/%d" % (uid, idx)
    cond, args = [], []
    if acc:
        uids = []
        try:
            with db.GameReader(op_db) as r:
                c, a = "Us_id = ?", [r.text(acc)]
                if acc.isdigit() and int(acc) <= 2147483647:
                    c, a = "Userindex = ? OR " + c, [int(acc)] + a
                uids = [int(x["Userindex"]) for x in r.rows("SELECT TOP (20) Userindex FROM Us_member WHERE %s ORDER BY Userindex" % c, a)]
        except db.DbError as ex:
            raise OpRefused("учётка не найдена: %s" % ex)
        if not uids:
            raise OpRefused("учётки «%s» нет" % acc[:40])
        cond.append("c.Userindex IN (%s)" % ",".join("?" * len(uids)))
        args += uids
    if name:
        cond.append("c.Charname = ?")
        args.append(name)
    if not cond:
        return None, [], None
    return " AND ".join(cond), args, None


def summary(q):
    """Сводка: {today, from, to, chars, history{rows,total,page,pages,size}, adjustments, installed, errors}. Даты — ГГГГММДД по часам
    SQL-сервера (сутки OP_Attendance); без дат — последние DEFAULT_DAYS суток."""
    q = q or {}
    size = _int(q.get("size") or PAGE, "строк на странице — целое от 1 до %d" % PAGE_MAX, 1, PAGE_MAX)
    page = _int(q.get("page") or 1, "страница — целое от 1 до 1000000", 1, 1000000)
    d_from = day_of(q.get("from"), "дата «с» — ГГГГММДД") if q.get("from") else None
    d_to = day_of(q.get("to"), "дата «по» — ГГГГММДД") if q.get("to") else None
    if d_from and d_to and d_from > d_to:
        raise OpRefused("дата «с» позже даты «по»")
    out = {"rows_max": CHARS_MAX, "chars": [], "history": {"rows": [], "total": 0, "page": 1, "pages": 1, "size": size}, "adjustments": [],
           "installed": False, "errors": [], "svc_max": SVC_MAX, "max_age_days": MAX_AGE_DAYS, "reward_item": REWARD_ITEM}
    cond, args, _ = _targets(q, "asdastoryop")
    show_test = str(q.get("test") or "") == "1"
    out["adjustments_test"] = 0
    try:
        with db.GameReader("joy1") as r:
            today = r.one("SELECT CONVERT(char(8), GETDATE(), 112) AS d")["d"]
            t = datetime.datetime.strptime(today, "%Y%m%d").date()
            d_to = d_to or t
            d_from = d_from or (d_to - datetime.timedelta(days=DEFAULT_DAYS - 1))
            if d_from > d_to:
                raise OpRefused("дата «с» позже даты «по»")
            if (d_to - d_from).days + 1 > WINDOW_MAX:
                raise OpRefused("период — не больше %d суток" % WINDOW_MAX)
            f8, t8 = d_from.strftime("%Y%m%d"), d_to.strftime("%Y%m%d")
            out.update(today=today, **{"from": f8, "to": t8})
            if cond is None:
                where = ("(EXISTS (SELECT 1 FROM dbo.AttendanceCount x WHERE x.Userindex = c.Userindex AND x.Charidx = c.Charidx) OR "
                         "EXISTS (SELECT 1 FROM dbo.AttendanceDetail x WHERE x.Userindex = c.Userindex AND x.Charidx = c.Charidx))")
                wargs = []
            else:
                where, wargs = cond, [r.text(a) if isinstance(a, str) else a for a in args]
            rng = [f8, t8]
            chars = r.rows(
                "SELECT TOP (%d) c.Userindex, c.Charidx, c.Charname, k.n_rows, k.acount, k.acno, d.total, d.first_day, d.last_day, d.today_n, p.in_period "
                "FROM dbo.Charinfo c "
                "OUTER APPLY (SELECT COUNT(*) AS n_rows, MIN(ACount) AS acount, MIN(ACNo) AS acno FROM dbo.AttendanceCount x "
                "WHERE x.Userindex = c.Userindex AND x.Charidx = c.Charidx AND x.Step = 2) k "
                "OUTER APPLY (SELECT COUNT(*) AS total, CONVERT(char(8), MIN(RegistDay), 112) AS first_day, CONVERT(char(8), MAX(RegistDay), 112) AS last_day, "
                "SUM(CASE WHEN CONVERT(varchar(10), RegistDay, 21) = CONVERT(varchar(10), GETDATE(), 21) THEN 1 ELSE 0 END) AS today_n "
                "FROM dbo.AttendanceDetail x WHERE x.Userindex = c.Userindex AND x.Charidx = c.Charidx AND x.Step = 2) d "
                "OUTER APPLY (SELECT COUNT(*) AS in_period FROM dbo.AttendanceDetail x WHERE x.Userindex = c.Userindex AND x.Charidx = c.Charidx "
                "AND x.Step = 2 AND x.RegistDay >= CONVERT(datetime, ?, 112) AND x.RegistDay < DATEADD(DAY, 1, CONVERT(datetime, ?, 112))) p "
                "WHERE %s ORDER BY c.Userindex, c.Charidx" % (CHARS_MAX, where), rng + wargs)
            hcond = "x.RegistDay >= CONVERT(datetime, ?, 112) AND x.RegistDay < DATEADD(DAY, 1, CONVERT(datetime, ?, 112))"
            hjoin = "FROM dbo.AttendanceDetail x JOIN dbo.Charinfo c ON c.Userindex = x.Userindex AND c.Charidx = x.Charidx WHERE %s AND %s" % (
                hcond, where)
            total = int(r.one("SELECT COUNT(*) AS n %s" % hjoin, rng + wargs)["n"])
            pages = max(1, (total + size - 1) // size)
            page = min(page, pages)
            hist = r.rows("SELECT x.ADNo, x.Userindex, x.Charidx, c.Charname, x.Step, CONVERT(char(8), x.RegistDay, 112) AS day, "
                          "CONVERT(varchar(19), x.RegistDay, 120) AS regist, x.Note %s ORDER BY x.RegistDay DESC, x.ADNo DESC "
                          "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" % hjoin, rng + wargs + [(page - 1) * size, size])
            installed = r.one("SELECT OBJECT_ID(?) AS o", ("adm.AttendanceAdjustLog",))["o"] is not None
            adj = []
            if installed:
                keys = [(int(c["Userindex"]), int(c["Charidx"])) for c in chars]
                if cond is None or keys:
                    acond, aargs = "1 = 1", []
                    if cond is not None:
                        acond = "(" + " OR ".join("(a.userindex = ? AND a.charidx = ?)" for _k in keys[:CHARS_MAX]) + ")"
                        for u, i in keys[:CHARS_MAX]:
                            aargs += [u, i]
                    # ★ ревизия 73 К-3: записи живого самотеста (via 'test') отсекает сервер, флажок — параметр test=1; счётчик — по всему журналу
                    tn = int(r.one("SELECT COUNT(*) AS n FROM adm.AttendanceAdjustLog a WHERE %s AND a.via = 'test'" % acond, aargs)["n"])
                    out["adjustments_test"] = tn
                    vcond = "" if show_test else " AND a.via <> 'test'"
                    adj = r.rows("SELECT TOP (100) a.id, a.userindex, a.charidx, CONVERT(char(8), a.day, 112) AS day, a.delta, a.count_before, a.count_after, "
                                 "a.adno, a.reason, a.operator, a.via, a.undo_of, a.undone_by, CONVERT(varchar(19), a.created_local, 120) AS created "
                                 "FROM adm.AttendanceAdjustLog a WHERE %s%s ORDER BY a.id DESC" % (acond, vcond), aargs)
    except db.DbError as ex:
        out["errors"].append("посещаемость не прочитана: %s" % ex)
        return out
    logins = {}
    uids = sorted({int(c["Userindex"]) for c in chars} | {int(h["Userindex"]) for h in hist})
    if uids:
        try:
            with db.GameReader("asdastoryop") as o:
                for x in o.rows("SELECT Userindex, Us_id FROM Us_member WHERE Userindex IN (%s)" % ",".join("?" * len(uids)), uids):
                    logins[int(x["Userindex"])] = x["Us_id"]
        except db.DbError as ex:
            out["errors"].append("логины учёток не прочитаны: %s" % ex)
    for c in chars:
        u, n_rows, total_n = int(c["Userindex"]), int(c["n_rows"] or 0), int(c["total"] or 0)
        cnt = None if n_rows == 0 else int(c["acount"] or 0)
        out["chars"].append({"uid": u, "idx": int(c["Charidx"]), "name": c["Charname"], "login": logins.get(u), "service": u <= SVC_MAX,
                             "count": cnt, "count_rows": n_rows, "days_total": total_n, "in_period": int(c["in_period"] or 0),
                             "first_day": c["first_day"], "last_day": c["last_day"], "today_got": int(c["today_n"] or 0) > 0,
                             "mismatch": n_rows > 1 or (cnt or 0) != total_n})
    for x in hist:
        nt = x["Note"]
        out["history"]["rows"].append({"adno": int(x["ADNo"]), "uid": int(x["Userindex"]), "idx": int(x["Charidx"]), "name": x["Charname"],
                                       "login": logins.get(int(x["Userindex"])), "step": int(x["Step"]), "day": x["day"], "regist": x["regist"],
                                       "mark": nt, "panel": bool(nt and str(nt).startswith("adm #")), "past": x["day"] < today,
                                       "service": int(x["Userindex"]) <= SVC_MAX})
    out["history"].update(total=total, page=page, pages=pages)
    out["adjustments"] = [{"id": int(a["id"]), "uid": int(a["userindex"]), "idx": int(a["charidx"]), "day": a["day"], "delta": int(a["delta"]),
                           "count_before": int(a["count_before"]), "count_after": int(a["count_after"]), "adno": a["adno"], "reason": a["reason"],
                           "operator": a["operator"], "via": a["via"], "undo_of": a["undo_of"], "undone_by": a["undone_by"], "created": a["created"]}
                          for a in adj]
    # ★ ревизия 73 М-1: правка без записи «ok» в журнале действий (сбой adm.audit после фиксации) — метка и откат attendance.undo_log
    if adj:
        try:
            seen = audited_log_ids()
        except db.DbError as ex:
            seen = None
            out["errors"].append("журнал действий не прочитан: %s" % ex)
        for a in out["adjustments"]:
            a["in_audit"] = None if seen is None else a["id"] in seen
    out["installed"] = installed
    if not installed:
        out["errors"].append(NOT_INSTALLED)
    return out
