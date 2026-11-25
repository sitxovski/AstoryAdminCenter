# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""progress.py — поднять уровень персонажа не в игре (волна А1, план §4.Б «уровень и опыт»). 17.11.2026.

РАЗБОР — Reports/admin_center/research_level_job.md (GameServer.c, DBManager, живые таблицы и Joy1):
  повышение (Recv_BattleServerFromCharParamExp_1 :80955 → 2005 → UPLevelUp): Lvl + 1; база Strength…Fortune = ClassStat[Class][Lvl]
  (sub_43AF30); SkillPoint + 2, если Job ≠ 0 и уровень ≤ потолка (sub_52E8A0 :114939); P2 = база (sub_443A80); производные (MaxHp,
  MaxMp, атака, защита, *P) GS ПЕРЕСЧИТЫВАЕТ при входе в мир (CharMake → sub_548B20 :125681) — в Charinfo это кэш.
  Опыт: E[L] из ExpTable — накопленный опыт начала уровня; уровень L ⇔ E[L] ≤ Expe < E[L+1] (:81036). Потолок — P29 MaxLevel (100).
  Понижения уровня у сервера НЕТ — панель его не делает (решение за владельцем).
ЗАПИСЬ — Lvl, Expe, SkillPoint, Strength…Fortune, StrengthP2…FortuneP2 (asda_ops: UPDATE только этих столбцов Charinfo), одна
транзакция, «не в игре» под блокировкой; Hp/Mp/MaxHp/MaxMp/атаки/*P НЕ трогаются. Журналы JoyLog1.LevelUp/SkillEvent панель не пишет
(нет доступа) — запись в adm.audit. Звания «за уровень» (6–10) выдаются сервером только в момент настоящего повышения.
Откат возвращает прежние значения, если строка с тех пор не менялась. Побочных эффектов при импорте нет.
"""
from core import bridge, db
from core.ops import Operation, OpRefused, register
from domains import items, srvtables

STATS = ("Strength", "Agility", "Health", "Spell", "Mentality", "Fortune")
COLS = ("Lvl", "Expe", "SkillPoint") + STATS + tuple(s + "P2" for s in STATS)
OPERATOR_MAX_UID = 5000


def plan(w, p, lock=False, role=None):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        lv = p["level"]
        if isinstance(lv, bool) or not (isinstance(lv, int) or (isinstance(lv, str) and lv.strip().isdigit())):
            raise ValueError                                   # перепроверка 11 М6: 60.5 не превращать молча в 60
        n = int(lv)
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры уровня")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Charname, Class, Job, %s FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?" % (", ".join(COLS), hint), (uid, idx))
    if not r:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    r = r[0]
    cur = int(r["Lvl"] or 0)
    try:
        top = srvtables.max_level()
        sp_top = srvtables.stat_points_top()
        cs, et = srvtables.class_stat(), srvtables.exp_table()
    except Exception as ex:                                     # перепроверка 11 М7: таблицы не прочитаны — отказ, не сбой
        raise OpRefused("таблицы сервера не прочитаны: %s" % ex)
    if n <= cur:
        raise OpRefused("понижения уровня у сервера нет — панель только повышает (сейчас %d)" % cur)
    if n > top:
        raise OpRefused("уровень выше потолка сервера (%d, P29 MaxLevel)" % top)
    base = cs.get((int(r["Class"] or 0), n))
    if not base or n not in et or (n + 1) not in et:
        raise OpRefused("нет строки ClassStat/ExpTable для класса %s уровня %d" % (r["Class"], n))
    exp = int(r["Expe"] or 0)
    new = {"Lvl": n, "Expe": exp if et[n] <= exp < et[n + 1] else et[n],
           # +2 за каждый уровень ≤ потолка очков (P29 StatPoints; 0 — стоковые 59) и только с профессией (sub_52E8A0)
           "SkillPoint": int(r["SkillPoint"] or 0) + (2 * max(0, min(n, sp_top) - cur) if int(r["Job"] or 0) != 0 else 0)}
    for i, s in enumerate(STATS):
        new[s] = base[i]
        new[s + "P2"] = base[i]
    if new["SkillPoint"] > 32767:
        raise OpRefused("очки навыков вышли бы за предел поля (%d)" % new["SkillPoint"])
    before = {k: r[k] for k in COLS}
    changed = {k: v for k, v in new.items() if before.get(k) != v}
    warn = ["звания «за уровень» сервер выдаёт только в момент настоящего повышения — персонаж получит их при следующем повышении"
            + (" (на %d-м уровне — никогда)" % top if n == top else ""),
            "HP/MP и атаку сервер пересчитает при входе в мир; до входа экран выбора персонажа покажет старые HP/MP"]
    if int(r["Job"] or 0) == 0:
        warn.append("у персонажа нет профессии — очков навыков за уровни сервер не даёт")
    warn.append("в отличие от настоящего повышения: HP/MP не станут полными, кувшин души не наполнится, журналы LevelUp/SkillEvent "
                "сервера не пишутся (только журнал панели)")
    # перепроверка 11 В2: рейтинг уровня (UPTopLevelAll / UPTopLevel<класс>, раз в 10 мин) берёт лидера по Charinfo.Lvl — звания 65–68
    lead = w.rows("SELECT MAX(CASE WHEN 1 = 1 THEN Lvl END) AS a, MAX(CASE WHEN Class = ? THEN Lvl END) AS c FROM dbo.Charinfo "
                  "WHERE NOT (Userindex = ? AND Charidx = ?)", (r["Class"], uid, idx))
    la, lc = (lead[0].get("a"), lead[0].get("c")) if lead else (None, None)
    if (la is not None and n > la) or (lc is not None and n > lc):
        warn.append("персонаж станет лидером рейтинга уровня (%s) — рейтинговые звания 65–68 перейдут к нему при пересчёте (раз в 10 мин)"
                    % ("общего и класса" if la is not None and n > la else "своего класса"))
    text = "уровень персонажа %d/%d (%s): %d → %d, опыт %s → %s, очки навыков %s → %s" % (
        uid, idx, r["Charname"], cur, n, r["Expe"], new["Expe"], r["SkillPoint"], new["SkillPoint"])
    sig = {k: [before[k], v] for k, v in changed.items()}
    return uid, idx, before, changed, sig, text, warn


def _apply(w, uid, idx, before, after, stale):
    if any(k not in COLS for k in after) or set(before) != set(after):
        raise OpRefused("в журнале неожиданные столбцы — откат не выполнен")
    sets = ", ".join("%s = ?" % k for k in after)
    where = " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (k, k) for k in after)
    params = list(after.values()) + [uid, idx] + [x for k in after for x in (before[k], before[k])]
    if w.execute("UPDATE dbo.Charinfo SET %s WHERE Userindex = ? AND Charidx = ? AND %s" % (sets, where), params) != 1:
        raise OpRefused(stale)


def _live_args(p, role, key):
    """uid, idx и целое значение key из параметров (те же отказы, что у офлайн-плана)."""
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        v = p[key]
        if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit())):
            raise ValueError
        v = int(v)
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры уровня" if key == "level" else "неверные параметры опыта")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return uid, idx, v


def live_level(ctx, p):
    """★ А2.2: игрок в игре на узле v81 → уровень живьём (событиями сервера по одному уровню); иначе None (офлайн / кик + запись)."""
    uid, idx, n = _live_args(p, ctx.role, "level")
    row = bridge.live_row(uid, idx)
    if not row:
        return None
    try:
        pr = bridge.probe(row, by=ctx.login)
    except bridge.BridgeError:
        return None
    cur, cap = int(pr.get("lvl", -1)), int(pr.get("cap", -1))
    if cur < 0 or cap < 0:
        return None                                               # узел без P75 — путь «кик + запись»
    if n <= cur:
        raise OpRefused("понижения уровня у сервера нет — панель только повышает (сейчас %d по памяти сервера)" % cur)
    try:
        top = min(srvtables.max_level(), cap)
    except Exception:
        top = cap
    if n > top:
        raise OpRefused("уровень выше потолка сервера (%d, P29 MaxLevel)" % top)
    text = "уровень персонажа %d/%d (%s) живьём: %d → %d — сервер поднимет событиями по одному уровню (как настоящее повышение)" % (
        uid, idx, row["charname"], cur, n)
    return {"text": text, "expect": {"live": ["level", n, cur]}, "warnings": [bridge.LIVE_WARN],
            "live": {"op": "exp", "args": "level=%d" % n, "row": row, "uid": uid, "idx": idx, "from": cur}}


def live_exp(ctx, p):
    """★ А2.2: опыт уровня, % — живьём только ПРИБАВКА внутри уровня; иначе None (офлайн / кик + запись)."""
    uid, idx, pc = _live_args(p, ctx.role, "percent")
    if not (0 <= pc <= 99):
        raise OpRefused("опыт уровня — от 0 до 99 %")
    row = bridge.live_row(uid, idx)
    if not row:
        return None
    try:
        pr = bridge.probe(row, by=ctx.login)
        et = srvtables.exp_table()
    except (bridge.BridgeError, Exception):
        return None
    lv, exp, cap = int(pr.get("lvl", -1)), int(pr.get("exp", -1)), int(pr.get("cap", -1))
    if lv < 0 or lv not in et or (lv + 1) not in et:
        return None
    if cap > 0 and lv >= cap:
        raise OpRefused("персонаж на потолке уровня (%d) — сервер опыт не копит" % cap)
    target = et[lv] + (et[lv + 1] - et[lv]) * pc // 100
    if target <= exp:
        return None                                               # уменьшение — у сервера нет такого события: «кик + запись»
    text = "опыт персонажа %d/%d (%s) живьём, уровень %d: %s → %s (%d %%)" % (uid, idx, row["charname"], lv, exp, target, pc)
    return {"text": text, "expect": {"live": ["exp", pc, lv]}, "warnings": [bridge.LIVE_WARN],
            "live": {"op": "exp", "args": "exp=%d" % target, "row": row, "uid": uid, "idx": idx, "from": exp}}


def live_apply(ctx, prev):
    """★ А2.2: выполнить живую правку из предпросмотра → dict для журнала (без записи в базу панелью)."""
    lv = prev["live"]
    try:
        r, text = bridge.live_call(lv["op"], lv["row"], lv["args"], by=ctx.login)
    except bridge.BridgeError as ex:
        raise OpRefused("живьём не выполнено: %s" % ex)
    return {"before": {"uid": lv["uid"], "idx": lv["idx"], "live_from": lv.get("from")},
            "after": {"uid": lv["uid"], "idx": lv["idx"], "live": True, "op": lv["op"], "args": lv["args"], "cmd": int(r["id"]),
                      "node": lv["row"]["node"]}, "message": text}


@register
class CharLevelUp(Operation):
    name, title, perm, reversible = "char.level_up", "Персонаж: поднять уровень", "players.progress", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        lv = live_level(ctx, p)                                   # ★ А2.2: игрок в игре — живьём
        if lv:
            return lv
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, before, changed, sig, text, warn = plan(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "changes": changed, "expect": sig,
                "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        if prev.get("live"):
            return live_apply(ctx, prev)
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры уровня")
            ok, why = items.online_state(w, uid0, lock=True)              # порядок блокировок как у входа в игру
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, before, changed, sig, text, warn = plan(w, p, lock=True, role=ctx.role)
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("пока вы смотрели предпросмотр, персонаж изменился — повторите")
            b = {k: before[k] for k in changed}
            _apply(w, uid, idx, b, changed, "персонаж изменился при записи — ничего не записано")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "values": b},
                "after": {"uid": uid, "idx": idx, "values": changed, "before": b}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json as _json
        if (_json.loads(row["after_json"] or "{}")).get("live"):
            raise OpRefused(bridge.LIVE_NO_UNDO)
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, idx = a.get("uid"), a.get("idx")
        if not uid or not a.get("values"):
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            _apply(w, uid, idx, a["values"], a["before"], "персонаж с тех пор менялся (уровень, опыт или очки) — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": a["values"], "after": a["before"], "message": "уровень персонажа %s/%s возвращён" % (uid, idx),
                "_commit": w.commit, "_close": w.close}


def plan_exp(w, p, lock=False, role=None):
    """Опыт внутри текущего уровня, % (перенос вкладки «Опыт» старой утилиты asda_exp.py, 18.11.2026): Expe = E[L] +
    ⌊% × (E[L+1] − E[L]) / 100⌋ — меньше E[L+1], уровень не меняется (так уровень читает сервер, :81036)."""
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        pc = p["percent"]
        if isinstance(pc, bool) or not (isinstance(pc, int) or (isinstance(pc, str) and pc.strip().isdigit())):
            raise ValueError
        pc = int(pc)
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры опыта")
    if not (0 <= pc <= 99):
        raise OpRefused("опыт уровня — от 0 до 99 %")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Charname, Lvl, Expe FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    if not r:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    r = r[0]
    lv, exp = int(r["Lvl"] or 0), int(r["Expe"] or 0)
    try:
        et = srvtables.exp_table()
        top = srvtables.max_level()
    except Exception as ex:
        raise OpRefused("таблицы сервера не прочитаны: %s" % ex)
    if lv >= top:
        # ★ ревизия 25 К-1: как у сервера (GameServer.c:81029 — на потолке опыт не копится) и как живой путь
        raise OpRefused("персонаж на потолке уровня (%d) — сервер опыт не копит" % top)
    if lv not in et or (lv + 1) not in et:
        raise OpRefused("нет строки ExpTable для уровня %d" % lv)
    lo, hi = et[lv], et[lv + 1]
    new = lo + (hi - lo) * pc // 100
    if new == exp:
        raise OpRefused("опыт уже такой")
    warn = []
    if not (lo <= exp < hi):
        warn.append("сейчас опыт не соответствует уровню (вне отрезка таблицы) — будет поставлен в отрезок уровня")
    cur_pc = (exp - lo) * 100 // (hi - lo) if lo <= exp < hi else None
    text = "опыт персонажа %d/%d (%s), уровень %d: %s%s → %s (%d %%)" % (
        uid, idx, r["Charname"], lv, exp, (" (%d %%)" % cur_pc) if cur_pc is not None else "", new, pc)
    before, after = {"Lvl": lv, "Expe": r["Expe"]}, {"Lvl": lv, "Expe": new}
    return uid, idx, before, after, {"Expe": [r["Expe"], new], "Lvl": lv}, text, warn


@register
class CharExpSet(Operation):
    name, title, perm, reversible = "char.exp_set", "Персонаж: опыт уровня, %", "players.progress", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        lv = live_exp(ctx, p)                                     # ★ А2.2: игрок в игре и прибавка — живьём
        if lv:
            return lv
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, before, after, sig, text, warn = plan_exp(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": sig, "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        if prev.get("live"):
            return live_apply(ctx, prev)
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры опыта")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, before, after, sig, text, warn = plan_exp(w, p, lock=True, role=ctx.role)
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("пока вы смотрели предпросмотр, персонаж изменился — повторите")
            # уровень — в условии записи (UPDATE … WHERE Lvl = прежний), меняется только Expe
            _apply(w, uid, idx, before, after, "персонаж изменился при записи — ничего не записано")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "values": before},
                "after": {"uid": uid, "idx": idx, "values": after, "before": before}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json as _json
        if (_json.loads(row["after_json"] or "{}")).get("live"):
            raise OpRefused(bridge.LIVE_NO_UNDO)
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, idx = a.get("uid"), a.get("idx")
        if not uid or not a.get("values"):
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            _apply(w, uid, idx, a["values"], a["before"], "персонаж с тех пор менялся (уровень или опыт) — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": a["values"], "after": a["before"], "message": "опыт персонажа %s/%s возвращён" % (uid, idx),
                "_commit": w.commit, "_close": w.close}
