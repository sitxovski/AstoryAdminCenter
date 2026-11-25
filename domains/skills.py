# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""skills.py — навыки и очки навыков персонажа НЕ В ИГРЕ (волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_skills_pets.md (A). РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11: полный сброс — ИСПРАВЛЕННЫЙ (навыки, которые
сервер после сброса держит в памяти уровнем 0, пишутся и в базу — у стока они пропадают после перезахода), серверная процедура
UPCharSkillinit чинится тем же правилом (патч ac0x); журналы JoyLog1 не пишутся — только журнал панели.
CharSkill (Userindex, Charidx, Skillidx): Lvl и 13 рабочих полей (кэш боя: GS при входе берёт их как есть). Навык появляется у сервера
  только уровнем 0 с сырыми полями нулевого уровня (sub_475F20, как UPSkillAdd 2102) — так же выдаёт панель.
ОПЕРАЦИИ:
  skill.grant      — навык уровнем 0 (500 ≤ id < N SkillInfo; навык игрока — маска +123 ≠ 0, имя не «-»; маска совпадает с Job
                     или Subjob персонажа — при входе сервер этого не проверяет, поэтому проверяет панель; уже изученный — отказ);
  skill.remove     — снять навык (у сервера нет): строка удаляется, SkillPoint += Lvl (как сброс дерева);
  skill.reset_tree — как свиток дерева sub_480F20 (:51264): по навыкам дерева (id > 500) SkillPoint += Lvl; +190 ≠ 0 → строка
                     удаляется, иначе уровень 0 и поля нулевого уровня;
  skill.reset_all  — как полный сброс sub_4803A0 (:51055) + UPCharSkillinit: SkillPoint += Σ Lvl (id > 500), все строки удаляются,
                     при JobCount ≥ 1 — шаблон класса (dbo.Fighter / Ranger / Mage); ИСПРАВЛЕНИЕ: изученные навыки с +190 = 0 и маской
                     Job/Subjob остаются уровнем 0 (у сервера они так в памяти и живут); у Class 0 — отказ («Tenderfoot Not Use»);
  skill.points     — очки навыков Charinfo.SkillPoint (0…32 767).
ЗАПИСЬ — asda_ops (SELECT/INSERT/DELETE CharSkill, UPDATE SkillPoint), одна транзакция, «не в игре» под блокировкой; набор строк
  «было → стало», откат возвращает «было», если строки с тех пор не менялись. Побочных эффектов при импорте нет.
"""
import json

from core import db
from core.ops import Operation, OpRefused, register
from domains import items, refdata, srvtables

ZERO = ("Cooltime", "Distance", "Scope", "Mpvalue", "Evalue", "SkillPer", "SubSkillPer", "SubValue1", "SubTime1", "SubValue2",
        "SubTime2", "SubValue3", "SubTime3")
COLS = ("Lvl",) + ZERO
SKILL_MIN = 500
STUBS = {608, 814, 1025, 1028, 1032, 1037}            # имя «-» и в сервере, и в клиенте
MAX_BATTLE = 100                                       # больше 100 навыков в боевую таблицу при входе не попадают
OPERATOR_MAX_UID = 5000
TEMPLATE = {1: "Fighter", 2: "Ranger", 3: "Mage"}


def skill_name(i):
    from core import i18n
    r = [v if v not in ("нет", "-") else "" for v in (refdata.names("skills").get(str(int(i))) or [])]   # «нет» у 640+ — нет имени
    ru = r[0] if r else ""
    en = r[1] if len(r) > 1 else ""
    if i18n.is_en():
        return en or "skill %d" % i       # русское имя в EN не подставляется (ревизия 21, К3)
    return ru or "навык %d" % i


def _ch(w, uid, idx, lock):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Charname, Class, Job, Subjob, JobCount, SkillPoint FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?"
               % hint, (uid, idx))
    if not r:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    return r[0]


def _learned(w, uid, idx, lock):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    return {int(r["Skillidx"]): {c: (int(r[c]) if r[c] is not None else None) for c in COLS} for r in w.rows(
        "SELECT Skillidx, %s FROM dbo.CharSkill%s WHERE Userindex = ? AND Charidx = ?" % (", ".join(COLS), hint), (uid, idx))}


def _fits(si, ch):
    """Маска +123: бит = Job или Subjob (sub_4803A0 :51128, sub_482130)."""
    m = si["mask"]
    return any(0 <= int(ch[k] or 0) < 64 and (m >> int(ch[k] or 0)) & 1 for k in ("Job", "Subjob") if int(ch[k] or 0))


def _zero(si):
    return dict({"Lvl": 0}, **{k: int(si["zero"][k]) for k in ZERO})


def _args(p, role, *names):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        vals = []
        for n in names:
            v = p[n]
            if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.strip().lstrip("-").isdigit())):
                raise ValueError
            vals.append(int(v))
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры навыков")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return [uid, idx] + vals


def _tables():
    try:
        return srvtables.skill_count()
    except Exception as ex:
        raise OpRefused("SkillInfo.sif сервера не прочитан: %s" % ex)


def _sp_change(ch, uid, idx, add):
    sp = int(ch["SkillPoint"] or 0)
    if sp + add > 32767:
        raise OpRefused("очки навыков вышли бы за предел поля (%d)" % (sp + add))
    return ("SP", [uid, idx], {"SkillPoint": sp}, {"SkillPoint": sp + add})


def plan_grant(w, p, lock=False, role=None):
    uid, idx, sk = _args(p, role, "skill")
    n = _tables()
    ch = _ch(w, uid, idx, lock)
    si = srvtables.skill_info(sk) if SKILL_MIN <= sk < n else None
    if not si or not si["mask"] or sk in STUBS or si["name"].strip() == "-":
        raise OpRefused("навык %d — не навык игрока (вне таблицы сервера, без классов или заглушка)" % sk)
    if not _fits(si, ch):
        raise OpRefused("навык %d не для профессии персонажа (маска классов SkillInfo не совпадает с Job/Subjob)" % sk)
    ln = _learned(w, uid, idx, lock)
    if sk in ln:
        raise OpRefused("навык уже изучен")
    warn = ["навык выдаётся уровнем 0, как у сервера; уровень игрок поднимает очками навыков"]
    if len(ln) + 1 > MAX_BATTLE:
        warn.append("у персонажа будет больше %d навыков — сервер при входе часть не возьмёт в бой" % MAX_BATTLE)
    if si["need"]:
        warn.append("для повышения навыка нужно вложить в его дерево %d очков" % si["need"])
    miss = [r for r, l in si["req"] if r >= SKILL_MIN and (r not in ln or (ln[r]["Lvl"] or 0) < l)]
    if miss:
        warn.append("предшествующие навыки не изучены или ниже нужного уровня: %s" % ", ".join(map(str, miss)))
    text = "выдать навык %d «%s» персонажу %s (%d/%d) уровнем 0" % (sk, skill_name(sk), ch["Charname"], uid, idx)
    return uid, idx, [("CharSkill", [uid, idx, sk], None, _zero(si))], text, warn


def plan_remove(w, p, lock=False, role=None):
    uid, idx, sk = _args(p, role, "skill")
    ch = _ch(w, uid, idx, lock)
    ln = _learned(w, uid, idx, lock)
    if sk not in ln:
        raise OpRefused("у персонажа нет этого навыка")
    lv = int(ln[sk]["Lvl"] or 0)
    changes = [("CharSkill", [uid, idx, sk], ln[sk], None)]
    if lv and sk > SKILL_MIN:
        changes.append(_sp_change(ch, uid, idx, lv))
    warn = ["у сервера нет снятия одного навыка — это функция панели; очки за уровни навыка возвращаются"]
    try:
        if sk in srvtables.passive_skills() and lv:
            warn.append("навык участвует в пассивных бонусах: бонус, уже вписанный в поля других навыков, останется до их повышения")
    except Exception:
        pass
    _tables()
    deps = [s for s in ln if s != sk and (srvtables.skill_info(s) or {}).get("req") and
            any(r == sk for r, _l in srvtables.skill_info(s)["req"])]
    if deps:
        warn.append("этот навык — предшественник изученных: %s" % ", ".join(map(str, sorted(deps))))
    text = "снять навык %d «%s» (уровень %d) у персонажа %s (%d/%d)" % (sk, skill_name(sk), lv, ch["Charname"], uid, idx)
    return uid, idx, changes, text, warn


def plan_reset_tree(w, p, lock=False, role=None):
    uid, idx, tree = _args(p, role, "tree")
    if not 1 <= tree <= 12:
        raise OpRefused("дерево навыков — от 1 до 12")
    _tables()
    ch = _ch(w, uid, idx, lock)
    if not int(ch["Class"] or 0):
        raise OpRefused("у новичка (класс 0) сброс навыков сервер не делает")
    ln = _learned(w, uid, idx, lock)
    changes, back = [], 0
    for s, row in sorted(ln.items()):
        si = srvtables.skill_info(s)
        if s <= SKILL_MIN or not si or si["tree"] != tree:
            continue
        back += int(row["Lvl"] or 0)
        changes.append(("CharSkill", [uid, idx, s], row, None if si["need"] else _zero(si)))
    changes = [c for c in changes if c[2] != c[3]]
    if not changes:
        raise OpRefused("в этом дереве сбрасывать нечего")
    if back:
        changes.append(_sp_change(ch, uid, idx, back))
    text = "сбросить дерево навыков %d у персонажа %s (%d/%d): навыков %d, очков вернётся %d" % (
        tree, ch["Charname"], uid, idx, len([c for c in changes if c[0] == "CharSkill"]), back)
    return uid, idx, changes, text, ["бонусы пассивов этого дерева в полях навыков других деревьев остаются — как у сервера"]


def plan_reset_all(w, p, lock=False, role=None):
    uid, idx = _args(p, role)
    _tables()
    ch = _ch(w, uid, idx, lock)
    cls = int(ch["Class"] or 0)
    if not cls:
        raise OpRefused("у новичка (класс 0) сброс навыков сервер не делает")
    ln = _learned(w, uid, idx, lock)
    back = sum(int(r["Lvl"] or 0) for s, r in ln.items() if s > SKILL_MIN)
    keep = {}
    if int(ch["JobCount"] or 0) >= 1 and cls in TEMPLATE:
        for r in w.rows("SELECT Skillidx, %s FROM dbo.%s" % (", ".join("%s AS %s" % (c, c) for c in COLS), TEMPLATE[cls])):
            keep[int(r["Skillidx"])] = dict({c: int(r[c] or 0) for c in COLS}, Lvl=0)
    fixed = []
    for s in ln:
        si = srvtables.skill_info(s)
        if s not in keep and si and not si["need"] and si["mask"] and _fits(si, ch):
            keep[s] = _zero(si)               # исправление: сервер держит их изученными уровнем 0, сток в базу не пишет. Поля — сырые
            #                                   нулевого уровня SkillInfo (sub_475F20, как UPSkillAdd); в памяти у GS до перезахода —
            #                                   Src sub_4296F0 (Cooltime/Mpvalue/SubValue1–3, SubTime −1), после перезахода — из базы
            fixed.append(s)
    changes = [("CharSkill", [uid, idx, s], ln.get(s), keep.get(s)) for s in sorted(set(ln) | set(keep))]
    changes = [c for c in changes if c[2] != c[3]]
    if back:
        changes.append(_sp_change(ch, uid, idx, back))
    if not changes:
        raise OpRefused("сбрасывать нечего")
    warn = ["исправленный сброс (решение владельца): навыки без требования дерева (это навыки 4-й профессии и 734, 757) остаются "
            "уровнем 0 — сток их теряет (%d таких)" % len(fixed)] if fixed else []
    text = "сбросить все навыки персонажа %s (%d/%d): было навыков %d, станет %d, очков вернётся %d" % (
        ch["Charname"], uid, idx, len(ln), len(keep), back)
    return uid, idx, changes, text, warn


def plan_points(w, p, lock=False, role=None):
    uid, idx, v = _args(p, role, "value")
    if not 0 <= v <= 32767:
        raise OpRefused("очки навыков — от 0 до 32 767")
    ch = _ch(w, uid, idx, lock)
    sp = int(ch["SkillPoint"] or 0)
    if sp == v:
        raise OpRefused("очки навыков уже %d" % v)
    text = "очки навыков персонажа %s (%d/%d): %d → %d" % (ch["Charname"], uid, idx, sp, v)
    return uid, idx, [("SP", [uid, idx], {"SkillPoint": sp}, {"SkillPoint": v})], text, []


def _put(w, kind, key, before, after, stale):
    if kind == "SP":
        n = w.execute("UPDATE dbo.Charinfo SET SkillPoint = ? WHERE Userindex = ? AND Charidx = ? AND SkillPoint = ?",
                      (after["SkillPoint"], key[0], key[1], before["SkillPoint"]))
        if n != 1:
            raise OpRefused(stale)
        return
    if kind != "CharSkill":
        raise OpRefused("в журнале неожиданная таблица — откат не выполнен")
    if before is not None:
        cond = " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (c, c) for c in COLS)
        if w.execute("DELETE FROM dbo.CharSkill WHERE Userindex = ? AND Charidx = ? AND Skillidx = ? AND " + cond,
                     list(key) + [x for c in COLS for x in (before[c], before[c])]) != 1:
            raise OpRefused(stale)
    if after is not None:
        if before is None and w.rows("SELECT 1 AS x FROM dbo.CharSkill WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ? "
                                     "AND Skillidx = ?", key):
            raise OpRefused(stale)
        w.execute("INSERT INTO dbo.CharSkill (Userindex, Charidx, Skillidx, %s) VALUES (?, ?, ?, %s)"
                  % (", ".join(COLS), ", ".join("?" * len(COLS))), list(key) + [after[c] for c in COLS])


def _sig(changes):
    return [[t, k, b, a] for t, k, b, a in changes]


class _SkillOp(Operation):
    reversible = True
    perm = "players.skills"
    planner = None

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, ch, text, warn = type(self).planner(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": _sig(ch), "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры навыков")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, ch, text, warn = type(self).planner(w, p, lock=True, role=ctx.role)
            if _sig(ch) != prev["expect"] or ("expect" in p and p["expect"] != _sig(ch)):
                raise OpRefused("пока вы смотрели предпросмотр, навыки персонажа изменились — повторите")
            for t, k, b, a in ch:
                _put(w, t, k, b, a, "навыки персонажа изменились при записи — ничего не записано")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx}, "after": {"uid": uid, "idx": idx, "changes": _sig(ch)}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        uid, ch = a.get("uid"), a.get("changes") or []
        if not uid or not ch:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            for t, k, b, af in reversed(ch):
                _put(w, t, k, af, b, "навыки персонажа с тех пор менялись — откат не выполнен")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"changes": ch}, "after": {"uid": uid}, "message": "навыки персонажа %s/%s возвращены" % (uid, a.get("idx")),
                "_commit": w.commit, "_close": w.close}


@register
class SkillGrant(_SkillOp):
    name, title = "skill.grant", "Персонаж: выдать навык"
    planner = staticmethod(plan_grant)


@register
class SkillRemove(_SkillOp):
    name, title = "skill.remove", "Персонаж: снять навык"
    planner = staticmethod(plan_remove)


@register
class SkillResetTree(_SkillOp):
    name, title = "skill.reset_tree", "Персонаж: сбросить дерево навыков"
    planner = staticmethod(plan_reset_tree)


@register
class SkillResetAll(_SkillOp):
    name, title = "skill.reset_all", "Персонаж: сбросить все навыки"
    planner = staticmethod(plan_reset_all)


@register
class SkillPoints(_SkillOp):
    name, title = "skill.points", "Персонаж: очки навыков"
    perm = "players.progress"                # перепроверка 21 М6: очки навыков — как уровень (owner), не «навыки» (admin)
    planner = staticmethod(plan_points)


def describe(uid, idx):
    """Навыки персонажа и что можно выдать (окно «Навыки»)."""
    n = srvtables.skill_count()
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        ch = _ch(ad, int(uid), int(idx), False)
        ln = _learned(ad, int(uid), int(idx), False)
    learned, avail, trees = [], [], {}
    for s, row in sorted(ln.items()):
        si = srvtables.skill_info(s) or {}
        learned.append({"id": s, "name": skill_name(s), "lvl": row["Lvl"], "max": si.get("max"), "tree": si.get("tree"),
                        "fits": bool(si) and _fits(si, ch)})
        if si.get("tree"):
            trees[si["tree"]] = trees.get(si["tree"], 0) + int(row["Lvl"] or 0)
    for s in range(SKILL_MIN, n):
        if s in ln or s in STUBS:
            continue
        si = srvtables.skill_info(s)
        if si and si["mask"] and si["name"].strip() != "-" and _fits(si, ch):
            avail.append({"id": s, "name": skill_name(s), "max": si["max"], "tree": si["tree"]})
    return {"learned": learned, "available": avail, "trees": trees, "skill_point": ch["SkillPoint"], "class": ch["Class"],
            "job": ch["Job"], "subjob": ch["Subjob"]}
