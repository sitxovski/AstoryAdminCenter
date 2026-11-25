# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""quests.py — задания и эпизоды персонажа НЕ В ИГРЕ (волна А1, план §4.Б «задания и эпизоды»). 18.11.2026.

РАЗБОР — Reports/admin_center/research_quests_episodes.md. «Эпизод» = задание (Episodeidx), цепочка = предшественники (+53).
CharEpisode (Userindex, Charidx, Code, Posx) — взятые (≤ 12), CharQuest Quest1…20 — маска «выполнено» (бит idx: Quest(idx/64+1),
разряд idx % 64, разряд 63 — знак), CRT_LimitationQuest — доска (Code ≥ 20000). NpcServer своей БД не имеет — правка офлайн
подхватывается при входе (8106). GS при входе согласованность не проверяет — её проверяет панель.
РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11: завершение — С НАГРАДОЙ (запись RepayTable ячейки «завершить», оператор выбирает вариант); 18 эпизодов смены
профессии — строго (выдать — только законную следующую ступень, завершить — только узаконить уже достигнутую, «выполнено» не снимать);
цепочки — отказ со списком; выдача — только как NPC (условия CheckCondition); доска — только снятие; JoyLog1 не пишется.
ОПЕРАЦИИ:
  quest.give        — как Start_Quest + GS sub_45CA70 + UPEpisodeRewardGain: первый свободный Posx, State 2, шаг 0, предметы-цели
                      книги (+8/+12/+16) количеством 1; отказ — по кодам CheckCondition/Start_Quest;
  quest.drop        — как отказ игрока (UPEpisodeDump + CRT_UPLimitationDel): строка удаляется, у доски Quest_Flag = 0;
  quest.complete    — слот удаляется, бит ставится (как UPEpisodeDestory + UPQuestUP) и выдаётся награда как sub_45DEE0: опыт со
                      штрафом за уровень одним событием (не выше одного уровня, на потолке — ничего; Recv_…Exp_1 :81009), золото
                      (Item 20551, как UPRewardGm), предметы — правилами items.give (adm.ItemGive), очки навыков; профессия — только
                      у эпизода смены, и то не выдаётся (ступень уже достигнута); харизма / книга / слава — в живых данных нет, отказ;
  quest.uncomplete  — снять бит; отказ у эпизодов смены и при выполненных/взятых зависимых.
ОТЛИЧИЯ ОТ СЕРВЕРА (помечено в предупреждениях): усилители опыта (события, зелья — GetExpUpDownValue) не применяются; предметы
  награды кладутся правилами выдачи панели (стопки/заряды P100), а не всегда новой строкой; при нехватке места — отказ целиком.
ЗАПИСЬ — asda_ops, одна транзакция, «не в игре» под блокировкой; набор строк «было → стало», откат — если с тех пор не менялось.
Побочных эффектов при импорте нет.
"""
import json

from core import db
from core.ops import Operation, OpRefused, register
from domains import items, itemgive, jobchange, progress, questdata as qd, refdata, srvtables

EP_COLS = ("State", "Episodeidx", "Stepidx", "Etime") + tuple("Eitem%d" % k for k in range(1, 6)) + tuple("Amount%d" % k for k in range(1, 6))
QCOLS = tuple("Quest%d" % k for k in range(1, 21))
GOLD_CODE = 20551
INT_MAX = 2147483647
SP_MAX = 32767
OPERATOR_MAX_UID = 5000
TABLES = {
    "CharEpisode": (("Userindex", "Charidx", "Code", "Posx"), EP_COLS),
    "CharQuest": (("Userindex", "Charidx"), QCOLS),
    "CRT_LimitationQuest": (("Userindex", "Charidx", "Quest_Index"), ("Quest_Flag",)),
    "Charinfo": (("Userindex", "Charidx"), progress.COLS),
    "Item": (("Userindex", "Charidx", "Uuid"), ("Amount",)),
}


def _s64(v):
    v &= 0xFFFFFFFFFFFFFFFF
    return v - (1 << 64) if v >= 1 << 63 else v


def _args(p, role, *names):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        vals = [int(p[n]) for n in names]
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры задания")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return [uid, idx] + vals


def _load(w, uid, idx, lock):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    ch = w.rows("SELECT Charname, Class, JobCount, Job, Subjob, %s FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?"
                % (", ".join(progress.COLS), hint), (uid, idx))
    if not ch:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    eps = w.rows("SELECT Code, Posx, %s FROM dbo.CharEpisode%s WHERE Userindex = ? AND Charidx = ? ORDER BY Posx"
                 % (", ".join(EP_COLS), hint), (uid, idx))
    qr = w.rows("SELECT %s FROM dbo.CharQuest%s WHERE Userindex = ? AND Charidx = ?" % (", ".join(QCOLS), hint), (uid, idx))
    board = w.rows("SELECT Quest_Index, Quest_Flag FROM dbo.CRT_LimitationQuest%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    eps = [{k: (int(r[k]) if r[k] is not None else None) for k in ("Code", "Posx") + EP_COLS} for r in eps]
    mask = {c: int(qr[0][c] or 0) for c in QCOLS} if qr else None
    return ch[0], eps, mask, {int(b["Quest_Index"]): int(b["Quest_Flag"] or 0) for b in board}


def _done(mask, q):
    if not mask or not 0 <= q <= qd.QMAX:
        return False
    return bool((int(mask["Quest%d" % (q // 64 + 1)]) >> (q % 64)) & 1)


def _set(mask, q, on):
    m = dict(mask or {c: 0 for c in QCOLS})
    k = "Quest%d" % (q // 64 + 1)
    v = int(m[k]) & 0xFFFFFFFFFFFFFFFF
    m[k] = _s64((v | (1 << (q % 64))) if on else (v & ~(1 << (q % 64))))
    return m


def _slots(eps):
    """Журнал NpcServer: 12 мест по Posx (как DBM sub_424080: Posx вне 0…11 — отброшена)."""
    s = [None] * qd.SLOTS
    for e in eps:
        if 0 <= e["Posx"] < qd.SLOTS:
            s[e["Posx"]] = {"Episodeidx": e["Episodeidx"], "Stepidx": e["Stepidx"],
                            "items": [(e["Eitem%d" % k], e["Amount%d" % k]) for k in range(1, 6)]}
    return s


def _name(q):
    return "%d «%s»" % (q, refdata.quest(q))


def _job_achieved(ch, q):
    kind, x = jobchange.JOB_EPISODES[q]
    J, S = int(ch["Job"] or 0), int(ch["Subjob"] or 0)
    if kind == "sub":
        return S == x
    for l in jobchange.LADDER.values():
        if x in l:
            return J in l and l.index(J) >= l.index(x)
    return False


def _book(q):
    try:
        by_code, by_idx = qd.quest_book()
    except Exception as ex:
        raise OpRefused("таблицы сервера не прочитаны: %s" % ex)
    code = by_idx.get(q)
    if code is None:
        raise OpRefused("задания %d нет в QuestBook сервера" % q)
    return code, by_code[code]


def _ep_change(uid, idx, e, after=None):
    """Строка CharEpisode: удалить e (after None) или вставить after (e None)."""
    row = e or after
    return ("CharEpisode", [uid, idx, row["Code"], row["Posx"]], {c: e[c] for c in EP_COLS} if e else None,
            {c: after[c] for c in EP_COLS} if after else None)


def plan_give(w, p, lock=False, role=None):
    uid, idx, q = _args(p, role, "quest")
    if q >= qd.BOARD_MIN:                              # перепроверка 22 К4: у доски Episodeidx = Code, в QuestBook их нет
        raise OpRefused("задания доски выдаёт доска — здесь только снятие")
    ch, eps, mask, board = _load(w, uid, idx, lock)
    code, book = _book(q)
    if any(e["Episodeidx"] == q or e["Code"] == code for e in eps):
        raise OpRefused("задание %s уже в журнале" % _name(q))
    if q in jobchange.JOB_EPISODES:
        tgt = jobchange.JOB_EPISODES[q]
        if tgt not in jobchange.next_steps(ch["Job"], ch["Subjob"]):
            raise OpRefused("эпизод смены профессии %s: цель (%s) — не следующая ступень персонажа (решение владельца: строго)"
                            % (_name(q), jobchange._ep_target(q)))
    gives, takes = qd.cells()
    if not gives.get(q):
        raise OpRefused("задание %s у NPC не выдаётся (нет ячейки «ВЫДАЁТ»)" % _name(q))
    if not takes.get(q):
        raise OpRefused("задание %s нельзя сдать (нет ячейки «ПРИНИМАЕТ») — выдавать бессмысленно" % _name(q))
    ok, why = qd.start_check(q, ch, lambda x: _done(mask, x), _slots(eps))
    if not ok:
        raise OpRefused("NPC не выдал бы задание %s: %s" % (_name(q), "; ".join(sorted({qd.REASONS.get(c, "код %d" % c) for c in why}))))
    if why[2] is not None and why[2] != code:           # перепроверка 22 В1: книга — та, что даёт прошедшее условие
        code, book = why[2], qd.quest_book()[0][why[2]]
    free = [x for x in range(qd.SLOTS) if x not in {e["Posx"] for e in eps}]
    if not free:
        raise OpRefused("в журнале нет свободного места (12)")
    new = {"Code": code, "Posx": free[0], "State": 2, "Episodeidx": q, "Stepidx": 0, "Etime": 0}
    for k in range(1, 6):
        g = book["goals"][k - 1] if k <= 3 else 0
        new["Eitem%d" % k], new["Amount%d" % k] = (g, 1) if g > 0 else (-1, 0)
    text = "выдать задание %s персонажу %s (%d/%d): книга %d, место %d" % (_name(q), ch["Charname"], uid, idx, code, free[0])
    warn = ["шаг 0, прогресс с нуля — дальше задание идёт по обычным правилам сервера (награды выдаст сервер при сдаче)"]
    return uid, idx, [_ep_change(uid, idx, None, new)], [], text, warn


def plan_drop(w, p, lock=False, role=None):
    uid, idx, posx = _args(p, role, "posx")
    ch, eps, mask, board = _load(w, uid, idx, lock)
    e = next((x for x in eps if x["Posx"] == posx), None)
    if not e:
        raise OpRefused("в месте %d журнала задания нет" % posx)
    changes = [_ep_change(uid, idx, e)]
    if e["Code"] >= qd.BOARD_MIN and board.get(e["Code"]):
        changes.append(("CRT_LimitationQuest", [uid, idx, e["Code"]], {"Quest_Flag": board[e["Code"]]}, {"Quest_Flag": 0}))
    text = "снять задание %s (место %d, шаг %s) у персонажа %s (%d/%d)" % (_name(e["Episodeidx"]), posx, e["Stepidx"], ch["Charname"], uid, idx)
    warn = ["как отказ игрока: прогресс задания теряется, награды прошлых шагов остаются у игрока; «выполнено» не ставится"]
    if e["Episodeidx"] in jobchange.JOB_EPISODES:
        warn.append("это эпизод смены профессии — после снятия его можно взять снова, если пройдут условия NPC")
    return uid, idx, changes, [], text, warn


def reward_variants(q, step=None):
    """→ [{id, exp, gold, items[[code, n, name]], sp, job, unsupported}] по ячейкам «завершить» (без повторов)."""
    out, seen = [], set()
    for npc, cell, st, key, rids in qd.finish_rewards(q, step):
        for rid in rids:
            if rid in seen:
                continue
            seen.add(rid)
            r = qd.repay(rid)
            if not r:
                continue
            pt = qd.reward_parts(r)
            out.append(dict(pt, id=rid, step=st, items=[[c, n, refdata.item(c)["name"] or str(c)] for c, n in pt["items"]], raw=r))
    return out


def _exp_change(ch, r):
    """Награда-опыт (sub_45DEE0 → Recv_BattleServerFromCharParamExp_1): одно событие. → (before, after, текст) или None."""
    lv = int(ch["Lvl"] or 0)
    gain = qd.penalized_exp(r, lv)
    if gain <= 0:
        return None, None
    try:
        top, et, cs, sp_top = srvtables.max_level(), srvtables.exp_table(), srvtables.class_stat(), srvtables.stat_points_top()
    except Exception as ex:
        raise OpRefused("таблицы сервера не прочитаны: %s" % ex)
    if lv >= top:
        return None, "опыт награды (%d) не начислен: персонаж на потолке уровня %d (у сервера так же)" % (gain, top)
    if lv not in et or (lv + 1) not in et:
        raise OpRefused("нет строки ExpTable для уровня %d" % lv)
    step = et[lv + 1] - et[lv]
    step = step if step > 0 else 1
    g = min(gain, step)
    cur = int(ch["Expe"] or 0)
    new = cur + g
    before = {k: ch[k] for k in progress.COLS}
    after = dict(before, Expe=new)
    note = "опыт +%d (таблица %d, со штрафом за уровень %d%s)" % (g, r["exp"], gain, ", зажат длиной уровня" if g < gain else "")
    if new >= et[lv + 1]:
        n = lv + 1
        base = cs.get((int(ch["Class"] or 0), n))
        if not base:
            raise OpRefused("нет строки ClassStat для класса %s уровня %d" % (ch["Class"], n))
        after["Lvl"] = n
        for i, s in enumerate(progress.STATS):
            after[s] = base[i]
            after[s + "P2"] = base[i]
        if int(ch["Job"] or 0) != 0:
            after["SkillPoint"] = int(ch["SkillPoint"] or 0) + 2 * max(0, min(n, sp_top) - lv)
        note += ", новый уровень %d" % n
    return (before, after), note


def plan_complete(w, p, lock=False, role=None):
    uid, idx, q = _args(p, role, "quest")
    if q >= qd.BOARD_MIN:
        raise OpRefused("задания доски завершает доска — здесь только снятие")
    ch, eps, mask, board = _load(w, uid, idx, lock)
    code, book = _book(q)
    e = next((x for x in eps if x["Episodeidx"] == q), None)
    if _done(mask, q) and not e:
        raise OpRefused("задание %s уже выполнено" % _name(q))
    warn = []
    if q in jobchange.JOB_EPISODES and not _job_achieved(ch, q):
        raise OpRefused("эпизод смены профессии %s: завершить можно, только чтобы узаконить уже достигнутую ступень (%s) — сначала "
                        "смените профессию операцией «Сменить профессию» (решение владельца: строго)" % (_name(q), jobchange._ep_target(q)))
    if not e:
        paths = qd.predecessors(q)
        if not paths:
            raise OpRefused("задание %s у NPC не выдаётся — завершать нечего" % _name(q))
        if not any(all(_done(mask, x) for x in ps) for ps in paths):
            miss = sorted({x for ps in paths for x in ps if not _done(mask, x)})
            raise OpRefused("не выполнены предшествующие задания: %s (решение владельца: отказ со списком)" % ", ".join(_name(x) for x in miss))
        # перепроверка 22 М1: не взятое завершается, только если NPC выдал бы его сейчас (уровень, класс, взаимоисключение +61);
        # полный журнал завершению не мешает — проверка идёт как при свободном месте
        sl = _slots(eps)
        if all(sl):
            sl[-1] = None
        ok, why = qd.start_check(q, ch, lambda x: _done(mask, x), sl)
        if not ok:
            raise OpRefused("NPC не выдал бы задание %s — завершать нельзя: %s" % (
                _name(q), "; ".join(sorted({qd.REASONS.get(c, "код %d" % c) for c in why}))))
    mid = [st for st, _r in qd.step_rewards(q) if not e or st >= int(e["Stepidx"] or 0)]
    if mid:                                              # перепроверка 22 М2
        warn.append("награды промежуточных шагов (%s) не выдаются — только награда завершения" % ", ".join(str(x) for x in sorted(set(mid))))
    var = reward_variants(q, e["Stepidx"] if e else None)
    if e and not var:
        var = reward_variants(q)
        if var:
            warn.append("у шага %d ячейки «завершить» нет — награда взята из ячейки другого шага" % e["Stepidx"])
    changes, give = [], []
    if e:
        changes.append(_ep_change(uid, idx, e))
    changes.append(("CharQuest", [uid, idx], mask, _set(mask, q, True)))
    rtext = "без награды (у ячеек «завершить» её нет)"
    chosen = None
    if var:
        want = p.get("reward")
        if want in (None, ""):
            chosen = var[0]
        else:
            try:
                chosen = next(v for v in var if v["id"] == int(want))
            except (StopIteration, TypeError, ValueError):
                raise OpRefused("такого варианта награды у задания нет (есть: %s)" % ", ".join(str(v["id"]) for v in var))
        if chosen["unsupported"]:
            raise OpRefused("в награде %d есть то, что панель не выдаёт: %s" % (chosen["id"], ", ".join(chosen["unsupported"])))
        if chosen["job"]:
            if q not in jobchange.JOB_EPISODES:
                raise OpRefused("награда %d меняет профессию, а задание не из списка эпизодов смены — панель не выдаёт" % chosen["id"])
            warn.append("смена профессии из награды не выполняется: ступень уже достигнута (узаконивание)")
        bits = []
        ec, note = _exp_change(ch, chosen["raw"])
        if note:
            bits.append(note) if ec else warn.append(note)
        info = dict(ch)
        if ec:
            info.update(ec[1])
        if chosen["sp"]:
            spv = int(info["SkillPoint"] or 0) + chosen["sp"]
            if spv > SP_MAX:
                raise OpRefused("очки навыков вышли бы за предел поля (%d)" % spv)
            if not ec:
                ec = ({k: ch[k] for k in progress.COLS}, {k: ch[k] for k in progress.COLS})
            ec[1]["SkillPoint"] = spv
            bits.append("очки навыков +%d" % chosen["sp"])
        if ec:
            b, a = ec
            ch_cols = [k for k in progress.COLS if b[k] != a[k]]
            if ch_cols:
                changes.append(("Charinfo", [uid, idx], {k: b[k] for k in ch_cols}, {k: a[k] for k in ch_cols}))
        if chosen["gold"]:
            g = w.rows("SELECT Uuid, Amount FROM dbo.Item%s WHERE Userindex = ? AND Charidx = ? AND Plate = 2 AND Code = ?"
                       % (" WITH (UPDLOCK, HOLDLOCK)" if lock else ""), (uid, idx, GOLD_CODE))
            if len(g) != 1:
                raise OpRefused("у персонажа нет строки золота (или их несколько) — сервер тоже не выдал бы золото")
            a0 = int(g[0]["Amount"] or 0)
            if a0 + chosen["gold"] > INT_MAX:
                raise OpRefused("золото вышло бы за предел (%d)" % INT_MAX)
            changes.append(("Item", [uid, idx, str(g[0]["Uuid"])], {"Amount": a0}, {"Amount": a0 + chosen["gold"]}))
            bits.append("золото +%d" % chosen["gold"])
        for c, n, nm in chosen["items"]:
            n = n if itemgive.item_spec(c)["stack"] else 1         # перепроверка 22 К3: не-стопка — одна штука, как у сервера
            for gp in _give_params(uid, idx, c, n):
                itemgive.plan_give(w, gp, lock=lock)       # место / вес — отказ сразу
            give.append([c, n])
            bits.append("%s (%d) × %d" % (nm, c, n))
        rtext = "награда %d: %s" % (chosen["id"], ", ".join(bits) if bits else "пусто")
        if len(var) > 1:
            warn.append("у задания %d вариантов награды (%s) — выбран %d" % (len(var), ", ".join(str(v["id"]) for v in var), chosen["id"]))
        warn.append("усилители опыта (события, зелья) не применяются — персонаж не в игре")
        if any(itemgive.item_spec(c)["gear"] for c, _n in give):
            warn.append("опции и самоцвет снаряжения награды бросаются при записи, как у сервера при сдаче")
        if give:
            warn.append("предметы награды кладутся правилами выдачи панели (стопки, заряды); места проверены для каждого по отдельности — "
                        "при записи не хватит места на все — отказ целиком")
    deps = sorted(x for x in qd.dependents(q))
    text = "завершить задание %s персонажу %s (%d/%d)%s; %s" % (_name(q), ch["Charname"], uid, idx, " (снять из журнала, место %d)" % e["Posx"]
                                                            if e else "", rtext)
    if deps:
        warn.append("откроются зависимые задания: %s" % ", ".join(_name(x) for x in deps[:8]) + (" …" if len(deps) > 8 else ""))
    return uid, idx, changes, give, text, warn


def plan_uncomplete(w, p, lock=False, role=None):
    uid, idx, q = _args(p, role, "quest")
    ch, eps, mask, board = _load(w, uid, idx, lock)
    if not 0 <= q <= qd.QMAX or not _done(mask, q):
        raise OpRefused("задание %d не выполнено" % q)
    if q in jobchange.JOB_EPISODES:
        raise OpRefused("эпизод смены профессии %s: «выполнено» не снимается — повторная сдача снова сменила бы профессию "
                        "(решение владельца: строго)" % _name(q))
    if any(e["Episodeidx"] == q for e in eps):
        raise OpRefused("задание %s в журнале — сначала снимите его" % _name(q))
    deps = sorted(x for x in qd.dependents(q) if _done(mask, x) or any(e["Episodeidx"] == x for e in eps))
    if deps:
        raise OpRefused("от задания %s зависят выполненные или взятые: %s — сначала снимите их (решение владельца: отказ со списком)"
                        % (_name(q), ", ".join(_name(x) for x in deps)))
    text = "снять отметку «выполнено» с задания %s у персонажа %s (%d/%d)" % (_name(q), ch["Charname"], uid, idx)
    warn = ["NPC снова даст взять задание и при сдаче выдаст награду ещё раз"]
    return uid, idx, [("CharQuest", [uid, idx], mask, _set(mask, q, False))], [], text, warn


def _give_params(uid, idx, c, n):
    """Параметры items.give для предмета награды. Снаряжение сервер создаёт с броском опций и самоцвета (sub_45DEE0 :38866 —
    sub_4A7EE0 / sub_4A7FC0 / sub_4B7B00) — каждая штука своим броском, как кнопка «Случайно»; прочее — n штук без опций."""
    sp = itemgive.item_spec(c)
    if sp["gear"]:                     # перепроверка 22 К3: не-стопку сервер создаёт одной штукой (количество не читает, GS:38855–38900)
        return [{"uid": uid, "idx": idx, "code": c, "qty": 1, "opts": srvtables.roll_creation(c)}]
    return [{"uid": uid, "idx": idx, "code": c, "qty": n if sp["stack"] else 1}]


def _js(v):
    return str(v) if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 1 << 53 else v


def _sig(changes, give):
    jd = lambda d: None if d is None else {k: _js(v) for k, v in d.items()}
    return [[t, list(k), jd(b), jd(a)] for t, k, b, a in changes] + [["give", g] for g in give]


def _put(w, table, key, before, after, stale):
    kc, cols = TABLES[table]
    cols = [c for c in cols if c in (after or before)]
    kw = " AND ".join("%s = ?" % k for k in kc)
    if before is None and after is None:
        return
    extra = ", Fdate = GETDATE()" if table == "Item" else ""           # как UPRewardGm
    if before is None:
        if table not in ("CharEpisode", "CharQuest"):
            raise OpRefused("в журнале неожиданная вставка — откат не выполнен")
        n = w.execute("INSERT INTO dbo.%s (%s) VALUES (%s)" % (table, ", ".join(list(kc) + cols), ", ".join("?" * (len(kc) + len(cols)))),
                      list(key) + [after[c] for c in cols])
    else:
        cond = " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (c, c) for c in cols)
        cp = [x for c in cols for x in (before[c], before[c])]
        if after is None:
            if table != "CharEpisode":
                raise OpRefused("в журнале неожиданное удаление — откат не выполнен")
            n = w.execute("DELETE FROM dbo.%s WHERE %s AND %s" % (table, kw, cond), list(key) + cp)
        else:
            ch = [c for c in cols if before[c] != after[c]]
            if not ch:
                return
            n = w.execute("UPDATE dbo.%s SET %s%s WHERE %s AND %s" % (table, ", ".join("%s = ?" % c for c in ch), extra, kw, cond),
                          [after[c] for c in ch] + list(key) + cp)
    if n != 1:
        raise OpRefused(stale)


def _ep_free(w, uid, idx, key, row):
    """Перед вставкой строки CharEpisode (выдача / откат снятия): место свободно, мест < 12, того же Code/Episodeidx нет."""
    r = w.rows("SELECT Code, Posx, Episodeidx FROM dbo.CharEpisode WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ?", (uid, idx))
    if len(r) >= qd.SLOTS or any(int(x["Posx"]) == key[3] or int(x["Code"]) == key[2] or int(x["Episodeidx"]) == row["Episodeidx"] for x in r):
        raise OpRefused("журнал заданий персонажа с тех пор изменился — записать нельзя")


class _QuestOp(Operation):
    reversible = True
    perm = "players.quests"
    planner = None

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, changes, give, text, warn = type(self).planner(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": _sig(changes, give), "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры задания")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, changes, give, text, warn = type(self).planner(w, p, lock=True, role=ctx.role)
            sg = _sig(changes, give)
            if sg != prev["expect"] or ("expect" in p and p["expect"] != sg):
                raise OpRefused("пока вы смотрели предпросмотр, данные персонажа изменились — повторите")
            for t, k, b, a in changes:
                if t == "CharEpisode" and b is None:
                    _ep_free(w, uid, idx, k, a)
                _put(w, t, k, b, a, "данные персонажа изменились при записи — ничего не записано")
            ledger, cells = [], []
            ccap, oper = srvtables.charge_cap() or 30000, ("panel:%s" % (ctx.login or ""))[:64]
            for gp in [x for c, n in give for x in _give_params(uid, idx, c, n)]:   # по одному, каждый видит предыдущие
                c = gp["code"]
                pl = itemgive.plan_give(w, gp, lock=True)
                s, o = pl["spec"], pl["opts"]
                for e in pl["ops"]:
                    try:
                        r = w.rows("EXEC adm.ItemGive ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                                   (uid, idx, pl["plate"], e["posx"], pl["cap"], e["mode"], c, e["amount"], s["dur"], e["weight"],
                                    o["Cell1"], o["Upcount"], s["maxup"], o["Opidx1"], o["OpValue1"], o["Opidx2"], o["OpValue2"],
                                    s["owner"], e["expect"], ccap, oper))
                    except db.DbError as ex:
                        raise itemgive._refuse_db(ex, "adm.ItemGive")
                    if not r:
                        raise OpRefused("процедура выдачи не ответила — ничего не записано")
                    ledger.append(int(r[0]["LedgerId"]))
                    cells.append("%d: %s/%d" % (c, items.PLATE_NAMES.get(pl["plate"], pl["plate"]), e["posx"]))
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        msg = text + (" (предметы: %s)" % ", ".join(cells) if cells else "")
        return {"before": {"uid": uid, "idx": idx},
                "after": {"uid": uid, "idx": idx, "changes": [[t, k, b, a] for t, k, b, a in changes], "ledger": ledger},
                "message": msg, "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        uid, idx, ch, ledger = a.get("uid"), a.get("idx"), a.get("changes") or [], a.get("ledger") or []
        if not uid or not ch:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            if ledger:
                _c, _cells, caps = items._load(w, uid, idx, lock=True)
                oper = ("panel:%s" % (ctx.login or ""))[:64]
                for lid in reversed(ledger):
                    led = w.rows("SELECT Plate FROM adm.ItemLedger WHERE Id = ?", (lid,))
                    if not led:
                        raise OpRefused("записи %s нет в журнале предметов" % lid)
                    try:
                        w.rows("EXEC adm.ItemUndo ?, ?, ?", (lid, caps.get(int(led[0]["Plate"]), 0), oper))
                    except db.DbError as ex:
                        raise itemgive._refuse_db(ex, "adm.ItemUndo")
            for t, k, b, af in reversed(ch):
                if t not in TABLES:
                    raise OpRefused("в журнале неожиданная таблица — откат не выполнен")
                if t == "CharEpisode" and af is None:
                    _ep_free(w, uid, idx, k, b)
                if t == "CharQuest" and b is None:                # строки не было — вернуть нули (сервер такую строку читает как пустую)
                    b = {c: 0 for c in QCOLS}
                _put(w, t, k, af, b, "данные персонажа с тех пор менялись — откат не выполнен")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"changes": ch}, "after": {"uid": uid}, "message": "задания персонажа %s/%s возвращены" % (uid, idx),
                "_commit": w.commit, "_close": w.close}


@register
class QuestGive(_QuestOp):
    name, title = "quest.give", "Задание: выдать"
    planner = staticmethod(plan_give)


@register
class QuestDrop(_QuestOp):
    name, title = "quest.drop", "Задание: снять из журнала"
    planner = staticmethod(plan_drop)


@register
class QuestComplete(_QuestOp):
    name, title = "quest.complete", "Задание: завершить с наградой"
    perm = "players.items_give"            # награда — предметы и золото: как выдача предмета (owner)
    planner = staticmethod(plan_complete)


@register
class QuestUncomplete(_QuestOp):
    name, title = "quest.uncomplete", "Задание: снять «выполнено»"
    planner = staticmethod(plan_uncomplete)


def describe(uid, idx):
    """Окно «Задания»: журнал, выполненные, что можно выдать, предупреждения о несогласованности."""
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        ch, eps, mask, board = _load(ad, uid, idx, False)
    by_code, by_idx = qd.quest_book()
    gives, takes = qd.cells()
    slots = _slots(eps)
    done = [q for q in range(qd.QMAX + 1) if _done(mask, q)]
    steps = lambda q: sorted({st for _n, _c, st, _k in takes.get(q, [])})
    taken = []
    warn = []
    for e in eps:
        q = e["Episodeidx"]
        bk = by_code.get(e["Code"])
        if e["Code"] < qd.BOARD_MIN and (not bk or bk["idx"] != q):
            warn.append("место %d: книга %d не соответствует заданию %d по QuestBook" % (e["Posx"], e["Code"], q))
        if _done(mask, q) and not qd.repeatable(q):
            warn.append("задание %s взято, но уже выполнено" % _name(q))
        if e["Code"] >= qd.BOARD_MIN and board.get(e["Code"]) != 1:
            warn.append("место %d: задание доски без флага «взято»" % e["Posx"])
        st = steps(q)
        taken.append({"posx": e["Posx"], "code": e["Code"], "quest": q, "name": refdata.quest(q) if e["Code"] < qd.BOARD_MIN else "",
                      "step": e["Stepidx"], "steps": st, "board": e["Code"] >= qd.BOARD_MIN, "job": q in jobchange.JOB_EPISODES,
                      "goals": [[e["Eitem%d" % k], e["Amount%d" % k], refdata.item(e["Eitem%d" % k])["name"]] for k in range(1, 6)
                                if e["Eitem%d" % k] not in (None, -1)],
                      "rewards": [{"id": v["id"], "exp": v["exp"], "gold": v["gold"], "items": v["items"], "step": v["step"]}
                                  for v in (reward_variants(q, e["Stepidx"]) or reward_variants(q))]
                      if e["Code"] < qd.BOARD_MIN else []})
    for q in done:
        paths = qd.predecessors(q)
        if paths and not any(all(_done(mask, x) for x in ps) for ps in paths):
            warn.append("задание %s выполнено без предшествующего" % _name(q))
    avail = []
    dn = lambda x: _done(mask, x)
    if len(eps) < qd.SLOTS:
        for q in sorted(gives):
            code = by_idx.get(q)
            if code is None or code >= qd.BOARD_MIN or not takes.get(q) or any(e["Episodeidx"] == q for e in eps):
                continue
            if q in jobchange.JOB_EPISODES and jobchange.JOB_EPISODES[q] not in jobchange.next_steps(ch["Job"], ch["Subjob"]):
                continue
            ok, _w = qd.start_check(q, ch, dn, slots)
            if ok:
                avail.append({"quest": q, "name": refdata.quest(q)})
    return {"uid": uid, "idx": idx, "name": ch["Charname"], "level": ch["Lvl"], "job": ch["Job"], "subjob": ch["Subjob"],
            "taken": taken, "free": qd.SLOTS - len(eps),
            "done": [{"quest": q, "name": refdata.quest(q), "job": q in jobchange.JOB_EPISODES, "repeatable": qd.repeatable(q)}
                     for q in done],
            "available": avail, "warnings": warn, "has_row": mask is not None}
