# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""jobchange.py — смена профессии персонажа не в игре (волна А1, план §4.Б «профессия и подкласс»). 17.11.2026.

РАЗБОР — Reports/admin_center/research_level_job.md §4, research_job_change_write.md (GameServer.c, DBManager, таблицы, Joy1);
конспект — Docs/Port/systems/CHARACTER_PROGRESSION.md. Панель повторяет награду квеста ПО СТУПЕНЯМ (каждая — как отдельная награда):
  лестница   боец Job 1→2→3, лучник 12→13→14, маг 23→24→25 (sub_460CE0 :39106: Class по ветке, Subjob 0, JobCount + 1);
             4-я — Subjob 4/6 · 15/17 · 26/28 из Job 3/14/25, Job и Class прежние, JobCount = 4 (sub_461010 :39225);
  очки       только при ПЕРВОЙ смене (JobCount был 0): SkillPoint += 2 на 5-м уровне, 2·ур. − 8 выше, 0 ниже (sub_52E900 :114960);
  база       при первой смене класс меняется — Strength…Fortune и P2 = ClassStat[Class][Lvl] (sub_43B040); HP/MP/атаки/*P — GS при входе;
  звание     при переходе на Job 3/14/25 и на 4-й (если прошёл её гейт) — 24/25/26, если бита ещё нет (sub_54A050 :126114): CharFame
             (Condition1 1, Condition2 0, опции 0), CharFameBank.Fame1 |= бит, Fmpoint += очки звания (FameInfo, 36);
  навыки     строка ChangeJobAddSkillTable[Job] (1–3-я) или [Subjob] (4-я); навык выдаётся, если предшественники +200/+203/+206 изучены
             на уровень ≥ +202/+205/+208 (неизученный = 0) и сумма уровней своей категории (+189) ≥ +190 (sub_48A8C0 :55510) —
             строкой CharSkill уровнем 0 с полями нулевого уровня SkillInfo (UPSkillAdd);
  4-я гейт   Σ уровней в категориях своей ветки (1–3 / 4–6 / 7–9) ≥ 60 и 0 в своей категории 4-й (10 / 11 / 12; P87 + P89 Mode 1),
             строка подкласса не «вся уже есть» (SkipOwnedRow) — иначе ни навыков, ни звания (сервер выдаст при изучении).
ИСПРАВЛЕНИЯ ДЕФЕКТОВ ОРИГИНАЛА (помечено): UPSkillAdd — upsert, у УЖЕ изученного навыка строки сервер ставит уровень 0 и не возвращает
  очки; панель уже имеющиеся навыки не трогает — вставляет только недостающие. При первой смене сервер пишет в БД только ПРИБАВКУ очков
  (у новичка, у которого очки уже были, они теряются при выходе) — панель пишет итог (перепроверка 12 М3).
ВЗЯТЫЙ КВЕСТ СМЕНЫ (research_jobchange_quests.md): 18 эпизодов JOB_EPISODES; отказ, если цель взятого не будет законной следующей
  ступенью после правки (сервер при сдаче профессию не сверяет — иначе неверное сочетание).
НЕ ДЕЛАЕТ: звание 21 «30 званий» (счётчик сервер растит только в памяти; восстановление при входе не доказано).
Уровень при смене сервер не проверяет (условие квеста в NpcServer) — панель тоже. Журналы JoyLog1.JobChange/SkillEvent не пишет (нет
доступа) — запись в adm.audit. ЗАПИСЬ — asda_ops, одна транзакция, «не в игре» под блокировкой; откат удаляет вставленное и
возвращает прежние значения, если с тех пор ничего не менялось. Побочных эффектов при импорте нет.
"""
from core import db
from core.ops import Operation, OpRefused, register
from domains import items, srvtables

LADDER = {1: (1, 2, 3), 2: (12, 13, 14), 3: (23, 24, 25)}
SUB4 = {3: (4, 6), 14: (15, 17), 25: (26, 28)}
FAME3 = {3: 24, 14: 25, 25: 26}
BRANCH_TREES = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9)}
OWN4_TREE = {4: 10, 6: 10, 15: 11, 17: 11, 26: 12, 28: 12}
STATS = ("Strength", "Agility", "Health", "Spell", "Mentality", "Fortune")
CI_COLS = ("Class", "JobCount", "Job", "Subjob", "SkillPoint") + STATS + tuple(s + "P2" for s in STATS)
ZERO = ("Cooltime", "Distance", "Scope", "Mpvalue", "Evalue", "SkillPer", "SubSkillPer", "SubValue1", "SubTime1", "SubValue2",
        "SubTime2", "SubValue3", "SubTime3")
OPERATOR_MAX_UID = 5000
# Эпизоды, награда которых — смена профессии (Reports/admin_center/research_jobchange_quests.md: награду выбирает NpcServer по
# QuestNpcTable/ConditionTable, GameServer применяет без проверки профессии; смена — только на последнем шаге; «взят» = строка
# CharEpisode). Episodeidx → (вид, цель): ("job", Job) или ("sub", Subjob).
JOB_EPISODES = {21: ("job", 1), 22: ("job", 12), 23: ("job", 23), 55: ("job", 2), 56: ("job", 13), 57: ("job", 24),
                301: ("job", 3), 302: ("job", 14), 303: ("job", 25),
                176: ("sub", 4), 180: ("sub", 6), 185: ("sub", 15), 192: ("sub", 26), 196: ("sub", 28), 199: ("sub", 17),
                461: ("sub", 4), 464: ("sub", 15), 467: ("sub", 26)}


def next_steps(job, sub):
    """Законные следующие ступени из состояния (Job, Subjob): множество ("job", x) / ("sub", x)."""
    job, sub = int(job or 0), int(sub or 0)
    if sub:
        return set()
    if job == 0:
        return {("job", 1), ("job", 12), ("job", 23)}
    for l in LADDER.values():
        if job in l:
            k = l.index(job)
            return {("job", l[k + 1])} if k < 2 else {("sub", x) for x in SUB4[job]}
    return set()


def _ep_target(e):
    kind, x = JOB_EPISODES[e]
    return ("Job %d" % x) if kind == "job" else ("подкласс %d" % x)


JOB_NAMES = {1: "боец 1", 2: "боец 2", 3: "боец 3", 12: "лучник 1", 13: "лучник 2", 14: "лучник 3", 23: "маг 1", 24: "маг 2", 25: "маг 3"}


def targets(ci):
    """Куда можно сменить профессию из текущего состояния (только вверх по лестнице одной ветки; новичок — в любую)."""
    jc, job, sub = int(ci["JobCount"] or 0), int(ci["Job"] or 0), int(ci["Subjob"] or 0)
    if jc == 0 or job == 0:
        return [{"job": j} for b in (1, 2, 3) for j in LADDER[b]] + [{"job": j, "subjob": s} for b in (1, 2, 3) for j, s in
                                                                      [(LADDER[b][2], x) for x in SUB4[LADDER[b][2]]]]
    branch = next((b for b, l in LADDER.items() if job in l), None)
    if branch is None or sub:
        return []
    pos = LADDER[branch].index(job)
    out = [{"job": j} for j in LADDER[branch][pos + 1:]]
    out += [{"job": LADDER[branch][2], "subjob": s} for s in SUB4[LADDER[branch][2]]]
    return out


def _steps(ci, tgt):
    """Ступени от текущей до цели: [(Job, Subjob, JobCount)]."""
    want_job, want_sub = int(tgt.get("job") or 0), int(tgt.get("subjob") or 0)
    if {"job": want_job, **({"subjob": want_sub} if want_sub else {})} not in targets(ci):
        raise OpRefused("так профессию сменить нельзя: только вверх по лестнице своей ветки (новичок — в любую)")
    branch = next(b for b, l in LADDER.items() if want_job in l)
    job, jc = int(ci["Job"] or 0), int(ci["JobCount"] or 0)
    start = LADDER[branch].index(job) + 1 if job in LADDER[branch] else 0
    steps = [(j, 0, k + 1) for k, j in enumerate(LADDER[branch]) if k >= start and k <= LADDER[branch].index(want_job)]
    if want_sub:
        steps.append((LADDER[branch][2], want_sub, 4))
    return branch, steps


def plan(w, p, lock=False, role=None):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        tgt = p["target"] if isinstance(p.get("target"), dict) else None
        if not tgt:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры смены профессии")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Charname, Lvl, %s FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?" % (", ".join(CI_COLS), hint), (uid, idx))
    if not r:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    ci = r[0]
    # перепроверка 12 М2: данные должны быть согласованы с лестницей (сервер на каждой ступени ставит Class и JobCount + 1;
    # на правленых руками строках панель и сервер разошлись бы)
    jc0, job0, sub0 = int(ci["JobCount"] or 0), int(ci["Job"] or 0), int(ci["Subjob"] or 0)
    exp_jc = 0 if not job0 else (4 if sub0 else next((l.index(job0) + 1 for l in LADDER.values() if job0 in l), -1))
    exp_cls = next((b for b, l in LADDER.items() if job0 in l), 0)
    if jc0 != exp_jc or (job0 and int(ci["Class"] or 0) != exp_cls):
        raise OpRefused("данные персонажа не согласованы с лестницей профессий (Job %s, Subjob %s, JobCount %s, Class %s) — "
                        "сервер так не записывает; панель такого персонажа не меняет" % (job0, sub0, jc0, ci["Class"]))
    branch, steps = _steps(ci, tgt)
    try:
        cjr = srvtables.change_job_rows()
        cs = srvtables.class_stat()
        ini = srvtables.patches_ini()
        p87, p89 = srvtables.patch_on("P87_Job4StartSkills", ini), srvtables.patch_on("P89_Job4GateBranch", ini)
        p89_mode = srvtables._atol(ini.get("P89_Job4GateBranch", {}).get("mode", "1"))
        skip_owned = str(ini.get("P89_Job4GateBranch", {}).get("skipownedrow", "1")).startswith("1")
        srvtables.skill_info(500)
    except Exception as ex:                                       # перепроверка 12 М6: сбой чтения — отказ, не ошибка 500
        raise OpRefused("таблицы сервера не прочитаны: %s" % ex)
    have = {int(x["Skillidx"]): int(x["Lvl"] or 0) for x in w.rows(
        "SELECT Skillidx, Lvl FROM dbo.CharSkill%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))}
    tree_sum = {}
    for s, lv in have.items():
        if s >= 500:
            si = srvtables.skill_info(s)
            if si:
                tree_sum[si["tree"]] = tree_sum.get(si["tree"], 0) + lv
    bank = w.rows("SELECT Fmpoint, Fame1 FROM dbo.CharFameBank%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    fame1 = int(bank[0]["Fame1"] or 0) if bank else 0
    lvl = int(ci["Lvl"] or 0)
    new = {k: ci[k] for k in CI_COLS}
    add_skills, titles, notes = [], [], []
    for job, sub, jc in steps:
        if int(new["JobCount"] or 0) == 0:                         # первая смена: очки и класс
            new["SkillPoint"] = int(new["SkillPoint"] or 0) + (2 if lvl == 5 else (2 * lvl - 8 if lvl > 5 else 0))
            new["Class"] = branch
            base = cs.get((branch, lvl))
            if not base:
                raise OpRefused("нет строки ClassStat для класса %d уровня %d" % (branch, lvl))
            for i, s in enumerate(STATS):
                new[s], new[s + "P2"] = base[i], base[i]
        new["Job"], new["Subjob"], new["JobCount"] = job, sub, jc
        if sub:                                                    # 4-я: гейт, затем звание и навыки подкласса
            if not p87:
                # перепроверка 12 М1: без P87 сток навыков 4-й профессии при смене не выдаёт (и звания тоже)
                notes.append("4-я профессия: патч P87 выключен — сервер навыки подкласса при смене не выдаёт")
                continue
            main = sum(tree_sum.get(t, 0) for t in BRANCH_TREES[branch])
            # P89 Mode 1: своя категория 10/11/12; иначе (сток) — пара 10/11 · 12/13 · 14/15 по ветке (:51482/:51508/:51534)
            own_trees = (OWN4_TREE[sub],) if (p89 and p89_mode == 1) else {1: (10, 11), 2: (12, 13), 3: (14, 15)}[branch]
            own = sum(tree_sum.get(t, 0) for t in own_trees)
            row = cjr.get(sub) or cjr.get(job, [])                 # М5: строки подкласса нет — P87 берёт строку Job
            if main < 60 or own > 0:
                if main < 60 and own == 0:
                    notes.append("4-я профессия: в основных деревьях ветки вложено %d (нужно ≥ 60) — навыки и звание сервер выдаст, "
                                 "когда сумма при изучении станет ровно 60" % main)
                else:
                    notes.append("4-я профессия: в основных деревьях ветки %d, в дереве 4-й профессии %d (нужно 0) — сервер навыки и звание "
                                 "подкласса уже не выдаст сам (только новой наградой)" % (main, own))
                continue
            if skip_owned and row and all(s in have for s in row):
                notes.append("все навыки подкласса уже изучены — сервер ничего не выдаёт (SkipOwnedRow)")
                continue
            fame, row_skills = FAME3[job], row
        else:
            fame, row_skills = FAME3.get(job), cjr.get(job, [])
        if fame and not (fame1 >> fame) & 1:
            fame1 |= 1 << fame
            titles.append(fame)
        for s in row_skills:
            si = srvtables.skill_info(s)
            if not si:
                continue
            ok = all(rq < 0 or have.get(rq, 0) >= rl for rq, rl in si["req"]) and tree_sum.get(si["tree"], 0) >= si["need"]
            if ok and s not in have:
                have[s] = 0
                add_skills.append((s, si["zero"]))
            elif ok:
                notes.append("навык %d уже изучен — оставлен как есть (сервер сбросил бы его уровень в 0 — дефект оригинала)" % s)
    changed = {k: v for k, v in new.items() if ci.get(k) != v}
    if not changed:
        raise OpRefused("профессия не меняется")
    if int(new["SkillPoint"] or 0) > 32767:
        raise OpRefused("очки навыков вышли бы за предел поля (%s)" % new["SkillPoint"])
    # перепроверка 12 В1 (закрыто разбором research_jobchange_quests.md): взятый эпизод смены профессии, цель которого после правки
    # не будет законной следующей ступенью, при сдаче даст неверное сочетание (сервер профессию не сверяет) — отказ
    eps = sorted(int(x["Episodeidx"]) for x in w.rows(
        "SELECT Episodeidx FROM dbo.CharEpisode%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx)))
    nxt = next_steps(new["Job"], new["Subjob"])
    bad = [e for e in eps if e in JOB_EPISODES and JOB_EPISODES[e] not in nxt]
    if bad:
        raise OpRefused("у персонажа взят квест смены профессии (эпизод %s → %s) — после этой правки его сдача даст неверное "
                        "сочетание; сначала пусть игрок сдаст или отменит квест" % (
                            ", ".join(map(str, bad)), ", ".join(_ep_target(e) for e in bad)))
    ok_eps = [e for e in eps if e in JOB_EPISODES]
    if ok_eps:
        notes.append("взят квест смены профессии (эпизод %s) — его цель остаётся следующей ступенью, сдавать можно"
                     % ", ".join(map(str, ok_eps)))
    pts = sum(srvtables.fame_points(t) or 0 for t in titles)
    text = "профессия персонажа %d/%d (%s): %s → %s%s; навыков добавится %d%s" % (
        uid, idx, ci["Charname"], _jname(ci["Job"], ci["Subjob"]), _jname(new["Job"], new["Subjob"]),
        (", очки навыков %s → %s" % (ci["SkillPoint"], new["SkillPoint"])) if "SkillPoint" in changed else "",
        len(add_skills), (", звание %s" % ", ".join(map(str, titles))) if titles else "")
    sig = {"ci": {k: [ci.get(k), v] for k, v in changed.items()}, "skills": sorted(s for s, _ in add_skills),
           # перепроверка 20 В1 (тот же дефект, что у званий): маска bigint > 2^53 из браузера возвращается округлённой — строкой
           "titles": titles, "bank": [bank[0]["Fmpoint"], str(bank[0]["Fame1"])] if bank else None}
    return {"uid": uid, "idx": idx, "before": {k: ci[k] for k in changed}, "changed": changed, "skills": add_skills,
            "titles": titles, "fame_pts": pts, "bank": bank[0] if bank else None, "fame1_new": fame1}, sig, text, notes


def _jname(job, sub):
    base = JOB_NAMES.get(int(job or 0), "новичок" if not job else "Job %s" % job)
    return base + (" · подкласс %s" % sub if sub else "")


@register
class CharJobChange(Operation):
    name, title, perm, reversible = "char.job_change", "Персонаж: сменить профессию", "players.progress", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                pl, sig, text, notes = plan(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, pl["uid"])
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        warn = notes + ["HP/MP и атаку сервер пересчитает при входе в мир; журналы сервера JobChange/SkillEvent не пишутся (только журнал панели)"]
        return {"text": text, "expect": sig, "warnings": warn + ([items.RECENT_WARN] if items.recently_left(pl["uid"]) else [])}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры смены профессии")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            pl, sig, text, notes = plan(w, p, lock=True, role=ctx.role)
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("пока вы смотрели предпросмотр, персонаж изменился — повторите")
            uid, idx, ch, b = pl["uid"], pl["idx"], pl["changed"], pl["before"]
            sets = ", ".join("%s = ?" % k for k in ch)
            where = " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (k, k) for k in ch)
            if w.execute("UPDATE dbo.Charinfo SET %s WHERE Userindex = ? AND Charidx = ? AND %s" % (sets, where),
                         list(ch.values()) + [uid, idx] + [x for k in ch for x in (b[k], b[k])]) != 1:
                raise OpRefused("персонаж изменился при записи — ничего не записано")
            for s, z in pl["skills"]:
                w.execute("INSERT INTO dbo.CharSkill (Userindex, Charidx, Skillidx, Lvl, %s) VALUES (?, ?, ?, 0, %s)"
                          % (", ".join(ZERO), ", ".join("?" * len(ZERO))), [uid, idx, s] + [z[k] for k in ZERO])
            new_fame_rows, fame_upd = [], []
            for t in pl["titles"]:
                ex = w.rows("SELECT Condition1, Condition2 FROM dbo.CharFame WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ? "
                            "AND Fameidx = ?", (uid, idx, t))
                if ex:
                    # перепроверка 12 М7: строка уже есть — как UPCharFameUp (upsert): Condition1 = 1, Condition2 = 0
                    if (ex[0]["Condition1"], ex[0]["Condition2"]) != (1, 0):
                        w.execute("UPDATE dbo.CharFame SET Condition1 = 1, Condition2 = 0 WHERE Userindex = ? AND Charidx = ? AND Fameidx = ?",
                                  (uid, idx, t))
                        fame_upd.append([t, ex[0]["Condition1"], ex[0]["Condition2"]])
                else:
                    w.execute("INSERT INTO dbo.CharFame (Userindex, Charidx, Fameidx, Condition1, Condition2, Opidx1, Opvalue11, Opvalue12, "
                              "Opidx2, Opvalue21, Opvalue22, Opidx3, Opvalue31, Opvalue32, Opidx4, Opvalue41, Opvalue42, Opidx5, Opvalue51, "
                              "Opvalue52, Opidx6, Opvalue61, Opvalue62) VALUES (?, ?, ?, 1, 0, 0,0,0, 0,0,0, 0,0,0, 0,0,0, 0,0,0, 0,0,0)",
                              (uid, idx, t))
                    new_fame_rows.append(t)
            bank_before, bank_new = None, False
            if pl["titles"]:
                if pl["bank"]:
                    bank_before = {"Fmpoint": pl["bank"]["Fmpoint"], "Fame1": pl["bank"]["Fame1"]}
                    if w.execute("UPDATE dbo.CharFameBank SET Fame1 = ?, Fmpoint = Fmpoint + ? WHERE Userindex = ? AND Charidx = ? AND Fame1 = ?",
                                 (pl["fame1_new"], pl["fame_pts"], uid, idx, pl["bank"]["Fame1"])) != 1:
                        raise OpRefused("звания персонажа изменились при записи — ничего не записано")
                else:
                    w.execute("INSERT INTO dbo.CharFameBank (Userindex, Charidx, Fmpoint, Fmidx1, Fmidx2, Fame1, Fame2, Fame3, Fame4) "
                              "VALUES (?, ?, ?, -1, -1, ?, 0, 0, 0)", (uid, idx, pl["fame_pts"], pl["fame1_new"]))
                    bank_new = True
        except BaseException:
            w.close()
            raise
        after = {"uid": uid, "idx": idx, "values": ch, "before": b, "skills": [s for s, _ in pl["skills"]], "fame_rows": new_fame_rows,
                 "fame_upd": fame_upd, "titles": pl["titles"],
                 "bank_before": bank_before, "bank_new": bank_new, "fame1_new": pl["fame1_new"] if pl["titles"] else None,
                 "fame_pts": pl["fame_pts"]}
        return {"before": {"uid": uid, "idx": idx, "values": b}, "after": after, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
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
            ch, b = a["values"], a["before"]
            sets = ", ".join("%s = ?" % k for k in b)
            where = " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (k, k) for k in ch)
            if any(k not in CI_COLS for k in ch) or set(ch) != set(b):
                raise OpRefused("в журнале неожиданные столбцы — откат не выполнен")
            if w.execute("UPDATE dbo.Charinfo SET %s WHERE Userindex = ? AND Charidx = ? AND %s" % (sets, where),
                         list(b.values()) + [uid, idx] + [x for k in ch for x in (ch[k], ch[k])]) != 1:
                raise OpRefused("персонаж с тех пор менялся — откат не выполнен")
            for s in a.get("skills") or []:
                # вставленный навык убираем, только если он не изучался (уровень 0)
                if w.execute("DELETE FROM dbo.CharSkill WHERE Userindex = ? AND Charidx = ? AND Skillidx = ? AND Lvl = 0", (uid, idx, s)) != 1:
                    raise OpRefused("навык %s с тех пор изучали — откат не выполнен" % s)
            # перепроверка 12 В2: звание снимается, только если его не надели и строки не менялись; иначе — отказ (не «успех»)
            if a.get("titles"):
                bk = w.rows("SELECT Fmidx1, Fmidx2, Fame1 FROM dbo.CharFameBank WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ?",
                            (uid, idx))
                if bk and (bk[0]["Fmidx1"] in a["titles"] or bk[0]["Fmidx2"] in a["titles"]):
                    raise OpRefused("выданное звание сейчас надето — откат не выполнен (сначала снять звание в игре)")
            for t in a.get("fame_rows") or []:
                if w.execute("DELETE FROM dbo.CharFame WHERE Userindex = ? AND Charidx = ? AND Fameidx = ? AND Condition1 = 1",
                             (uid, idx, t)) != 1:
                    raise OpRefused("строка звания %s с тех пор менялась — откат не выполнен" % t)
            for t, c1, c2 in a.get("fame_upd") or []:
                w.execute("UPDATE dbo.CharFame SET Condition1 = ?, Condition2 = ? WHERE Userindex = ? AND Charidx = ? AND Fameidx = ?",
                          (c1, c2, uid, idx, t))
            if a.get("bank_new"):
                if w.execute("DELETE FROM dbo.CharFameBank WHERE Userindex = ? AND Charidx = ? AND Fame1 = ? AND Fmpoint = ?",
                             (uid, idx, a["fame1_new"], a.get("fame_pts") or 0)) != 1:
                    raise OpRefused("звания персонажа с тех пор менялись — откат не выполнен")
            elif a.get("bank_before"):
                if w.execute("UPDATE dbo.CharFameBank SET Fame1 = ?, Fmpoint = Fmpoint - ? WHERE Userindex = ? AND Charidx = ? AND Fame1 = ?",
                             (a["bank_before"]["Fame1"], a.get("fame_pts") or 0, uid, idx, a["fame1_new"])) != 1:
                    raise OpRefused("звания персонажа с тех пор менялись — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": a["values"], "after": a["before"], "message": "профессия персонажа %s/%s возвращена" % (uid, idx),
                "_commit": w.commit, "_close": w.close}
