# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""charrest.py — оставшиеся правки персонажа §4.Б (волна А1): внешность, баффы наборов, лагерь, ремесло, рыбалка, обучение;
посещаемость — только показ. 18.11.2026.

РАЗБОР — Reports/admin_center/research_a1_char_rest.md (живая Joy1, процедуры сервера, GameServer.c, таблицы стойки).
Выход персонажа эти таблицы НЕ перезаписывает (§0), но GS держит значения в памяти и часть процедур пишет их АБСОЛЮТНО при
следующем событии (CRT_UPCraftEnter, UPCharTutorialUpdate, UPCharCampUpdate) — поэтому правка только «не в игре»; игрок в игре —
«кик + запись» моста P127 (точка items.online_state → ops.run). Живых команд моста здесь нет.
РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11:
  appearance.set     — CharAppr: причёска и цвет — пара из ItemTable_Info\\HairTypeTable.txt ДЛЯ ПОЛА персонажа и «в продаже» (+68 = 1,
                       как проверяет парикмахерская Recv_HairShopBuy), лицо — значения своего пола: на сервере списка лиц нет (смены
                       лица у сервера нет), берём цикл окна создания клиента (муж. 0…10, жен. 0…9; AsdaLoginGameMode_Create.cpp:936);
                       прежнее значение остаётся допустимым. Журналы покупки SaleHair/HairChange не пишутся.
  plus.remove/set/extend — CharPlusPackage (одна строка на персонажа — UPPlusPackageitemUse обновляет без iType): снять (DELETE),
                       выдать тип из PlusPackageTable.txt (срок — минуты таблицы, StartTime = сейчас, как UPPlusPackageitemUse),
                       продлить (EndTime += N, BuffPeriod += N). Вход: UPCharPackageBuff сам удаляет истёкшие, остаток = EndTime − сейчас.
  camp.penalty_clear — CharCamp.CampPenaltyTime = 0 (штраф в тиках сервера; GS читает при входе).
  camp.set_army      — Campidx у ВСЕЙ учётки (как UPCharCampSelect / UPCharCampReset): строки есть — UPDATE, нет и армия ≥ 0 — INSERT
                       (0, 0, 0, 0) для каждого персонажа; только когда вся учётка не в игре. CampData (счётчики RelayServer) не трогаем.
  camp.rank_rebuild  — EXEC adm.CampPointRank (обёртка штатного UP_CampPointRank, sql/adminc_08_charcopy.sql); ещё раз в сутки — служба
                       (core/sched.py). UP_CampDataReset НЕ запускается (разбор Relay не сделан).
  craft.set_level    — CRT_CharCraftInfo iLevel/iExp: уровень 1…N CraftLevel.txt, опыт — в границах уровня по порогам (кол. 1).
  craft.daily_reset  — как суточный сброс (CRT_AsdaLimitationDailyReset / CRT_UPLimitationInit) одному персонажу: Quest_Type = 1:
                       Quest_Flag 3 → 0, Quest_Count → 0. Рецепты (iBit1…9) — только показ.
  fish.set_skill     — CharFish.FishingSkill (строки нет — INSERT, как первый улов UPCharFishIngProgress); fishbook.delete — строка
                       книги (как UPCharFishBookDelete, без журнала CharFishBook); счётчики рыбы не правятся.
  tutorial.set       — CharTutorial Tutorial1…4 (биты шагов 0…N−1, N — строк Tutorial_ExpInfo.txt; старшие биты не трогаются;
                       строки нет — INSERT, как UPCharTutorialUpdate). Снятый шаг сервер наградит опытом ещё раз — предупреждение.
ЗАПИСЬ — asda_ops, одна транзакция, «не в игре» под блокировкой; строки «было → стало», откат — если с тех пор не менялись.
Побочных эффектов при импорте нет.
"""
import datetime
import json
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import items, srvtables

OPERATOR_MAX_UID = 5000
INT_MAX = 2147483647
FACES = {1: tuple(range(11)), 2: tuple(range(10))}           # цикл лица окна создания клиента (муж. 11, жен. 10)
ARMY_NAMES = {-1: "без армии", 0: "Свет", 1: "Тьма", 2: "Хаос"}  # loc 10191+армия (Reports/faction_select/FLOW.md)
PLUS_COLS = ("iType", "StartTime", "BuffPeriod", "EndTime")
DATE_COLS = {"StartTime", "EndTime"}                          # smalldatetime: строкой «ГГГГ-ММ-ДД чч:мм» (CONVERT 120, 16 знаков)
TABLES = {
    "CharAppr": (("Userindex", "Charidx"), ("HairStyle", "HairColor", "FaceType")),
    "CharPlusPackage": (("Userindex", "Charidx"), PLUS_COLS),
    "CharCamp": (("Userindex", "Charidx"), ("Campidx", "CampPoint", "CampGrade", "CampFlag", "CampPenaltyTime")),
    "CRT_CharCraftInfo": (("Userindex", "Charidx"), ("iLevel", "iExp")),
    "CRT_LimitationQuest": (("Userindex", "Charidx", "Quest_Index"), ("Quest_Type", "Quest_Count", "Quest_Flag")),
    "CharFish": (("Userindex", "Charidx"), ("FishingSkill",)),
    "CharFishBookInfo": (("Userindex", "Charidx", "BookCode"), None),        # все столбцы строки (снимок для отката)
    "CharTutorial": (("Userindex", "Charidx"), ("Tutorial1", "Tutorial2", "Tutorial3", "Tutorial4")),
}
INSERTABLE = {"CharPlusPackage", "CharCamp", "CharFish", "CharFishBookInfo", "CharTutorial"}
DELETABLE = {"CharPlusPackage", "CharCamp", "CharFish", "CharFishBookInfo", "CharTutorial"}


def _s64(v):
    v &= 0xFFFFFFFFFFFFFFFF
    return v - (1 << 64) if v >= 1 << 63 else v


def _js(v):
    """Число, которое переживёт JSON.parse браузера (bigint масок ≥ 2^53 — строкой, как titles._js)."""
    return str(v) if isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 1 << 53 else v


def _int(v, msg):
    """Целое из параметра; иначе отказ msg (готовый текст — у каждого свой шаблон перевода)."""
    # ★ ревизия 26 М-6: строгий разбор («--1», «1.5», «١» — отказ, а не исключение)
    if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and re.fullmatch(r"-?[0-9]+", v.strip()))):
        raise OpRefused(msg)
    return int(v)


def _args(p, role, *names):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры персонажа")
    vals = []
    for n in names:
        if n not in p or p[n] in (None, ""):
            raise OpRefused("не задан параметр «%s»" % n)
        vals.append(_int(p[n], "параметр «%s» — целое число" % n))
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return [uid, idx] + vals


def _hint(lock):
    return " WITH (UPDLOCK, HOLDLOCK)" if lock else ""


def _sel_cols(cols):
    return ", ".join("CONVERT(varchar(16), %s, 120) AS %s" % (c, c) if c in DATE_COLS else c for c in cols)


def _norm(r, cols):
    return {c: (r[c] if c in DATE_COLS or not isinstance(r[c], (int, float)) or isinstance(r[c], bool) else int(r[c])) for c in cols}


def _rows(w, table, where, params, lock):
    kc, cols = TABLES[table]
    sel = "*" if cols is None else ", ".join(list(kc) + [_sel_cols(cols)])
    out = []
    # ★ ревизия 26 М-2: порядок строк задан (ключ; у бафа — ещё iType) — предпросмотр и запись под блокировкой видят одно и то же
    order = list(kc) + (["iType"] if table == "CharPlusPackage" else [])
    for r in w.rows("SELECT %s FROM dbo.%s%s WHERE %s ORDER BY %s" % (sel, table, _hint(lock), where, ", ".join(order)), params):
        cc = cols or [c for c in r.keys() if c not in kc]
        out.append(({k: int(r[k]) for k in kc}, _norm(r, cc)))
    return out


def _char(w, uid, idx, lock):
    ch = w.rows("SELECT Charname, Gender, JobCount FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?" % _hint(lock), (uid, idx))
    if not ch:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    return ch[0]


def _now(w):
    return w.rows("SELECT CONVERT(varchar(16), GETDATE(), 120) AS n")[0]["n"]


def _dt(s):
    return datetime.datetime.strptime(s[:16], "%Y-%m-%d %H:%M")


def _ds(d):
    return d.strftime("%Y-%m-%d %H:%M")


def _put(w, table, key, before, after, stale):
    """Строка «было → стало»: вставка / удаление / обновление только при совпадении «было» по всем столбцам."""
    kc, cols = TABLES[table]
    if before is None and after is None:
        return
    cols = list(cols) if cols else list((after or before).keys())
    val = lambda c: "CONVERT(smalldatetime, ?, 120)" if c in DATE_COLS else "?"
    kw = " AND ".join("%s = ?" % k for k in kc)
    if before is None:
        if table not in INSERTABLE:
            raise OpRefused("в журнале неожиданная вставка — откат не выполнен")
        n = w.execute("INSERT INTO dbo.%s (%s) VALUES (%s)" % (table, ", ".join(list(kc) + cols), ", ".join(["?"] * len(kc) + [val(c) for c in cols])),
                      list(key) + [after[c] for c in cols])
    else:
        cond = " AND ".join(("CONVERT(varchar(16), %s, 120) = ?" % c) if c in DATE_COLS else "%s = ?" % c for c in cols)
        cp = [before[c] for c in cols]
        if after is None:
            if table not in DELETABLE:
                raise OpRefused("в журнале неожиданное удаление — откат не выполнен")
            n = w.execute("DELETE FROM dbo.%s WHERE %s AND %s" % (table, kw, cond), list(key) + cp)
        else:
            ch = [c for c in cols if before[c] != after[c]]
            if not ch:
                return
            n = w.execute("UPDATE dbo.%s SET %s WHERE %s AND %s" % (table, ", ".join("%s = %s" % (c, val(c)) for c in ch), kw, cond),
                          [after[c] for c in ch] + list(key) + cp)
    if n != 1:
        raise OpRefused(stale)


def _sig(changes):
    """Отпечаток для подтверждения: bigint — строкой; у бафа «стало» без StartTime/EndTime (их ставит время записи)."""
    out = []
    for t, k, b, a in changes:
        bb = {c: _js(v) for c, v in b.items()} if b else b
        aa = {c: _js(v) for c, v in a.items() if not (t == "CharPlusPackage" and c in DATE_COLS and (b is None or a.get("_set")))} if a else a
        if aa:
            aa.pop("_set", None)
        out.append([t, list(k), bb, aa])
    return out


def _strip(changes):
    """Служебные пометки плана (_set) не пишутся в базу и журнал."""
    return [(t, k, b, {c: v for c, v in a.items() if c != "_set"} if a else a) for t, k, b, a in changes]


# ---------------------------------------------------------------------------------------------------------------- таблицы стойки
def hair_rows():
    """[(номер, пол, уровень, в продаже, цена, стиль, цвет)] — HairTypeTable.txt (Recv_HairShopBuy: +66 пол, +67 уровень, +68 в продаже,
    +69 цена, +73 стиль, +74 цвет)."""
    try:
        t = srvtables.table("HairTypeTable.txt")
    except Exception as ex:
        raise OpRefused("HairTypeTable.txt сервера не прочитан: %s" % ex)
    out = []
    for k, f in sorted(t.items()):
        if len(f) >= 8:
            out.append(tuple([k] + [srvtables._i(f, i) for i in (2, 3, 4, 5, 6, 7)]))
    return out


def plus_types():
    """{тип: [минуты, множители…]} — PlusPackageTable.txt (тип 0 — пусто; recvDBPlusPakege: iType ≥ строк → −1)."""
    try:
        t = srvtables.table("PlusPackageTable.txt")
    except Exception as ex:
        raise OpRefused("PlusPackageTable.txt сервера не прочитан: %s" % ex)
    return {k: [srvtables._i(f, i) for i in range(1, len(f))] for k, f in t.items()}


def craft_levels():
    """[(уровень, порог опыта, прирост)] — CraftLevel.txt (загрузчик GameServer.c:74798: N, записи по 4 числа, номер подряд)."""
    try:
        t = srvtables.table("CraftLevel.txt")
    except Exception as ex:
        raise OpRefused("CraftLevel.txt сервера не прочитан: %s" % ex)
    rows = [(k, srvtables._i(f, 1), srvtables._i(f, 2)) for k, f in sorted(t.items())]
    if not rows or [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        raise OpRefused("CraftLevel.txt сервера не согласован (номера уровней не подряд)")
    return rows


def craft_bounds(lv, levels):
    """Опыт уровня lv: [порог предыдущего, порог уровня − 1] (уровни 7…10 с тем же порогом — ровно этот порог)."""
    lo = levels[lv - 2][1] if lv >= 2 else 0
    hi = max(lo, levels[lv - 1][1] - 1)
    return lo, min(hi, 65535)                                 # GS держит опыт словом (+264463, GameServer.c:120899)


def tutorial_exp():
    """[опыт шага] — ConfigSet\\Tutorial_ExpInfo.txt (N, затем пары «номер опыт»; N = word_5F5F64, предел номера шага)."""
    try:
        toks = srvtables._cfg_text("Tutorial_ExpInfo.txt").split()
    except Exception as ex:
        raise OpRefused("Tutorial_ExpInfo.txt сервера не прочитан: %s" % ex)
    n = srvtables._atol(toks[0]) if toks else 0
    out = []
    for i in range(n):
        rec = toks[1 + 2 * i: 3 + 2 * i]
        if len(rec) < 2:
            break
        out.append(srvtables._atol(rec[1]))
    if not out:
        raise OpRefused("Tutorial_ExpInfo.txt сервера пуст")
    return out


# ---------------------------------------------------------------------------------------------------------------- планы
def plan_appearance(w, p, lock=False, role=None):
    uid, idx, hs, hc, ft = _args(p, role, "hair", "color", "face")
    ch = _char(w, uid, idx, lock)
    r = _rows(w, "CharAppr", "Userindex = ? AND Charidx = ?", (uid, idx), lock)
    if not r:
        raise OpRefused("у персонажа нет строки внешности (CharAppr) — её создаёт сервер при создании персонажа")
    cur = r[0][1]
    g = int(ch["Gender"] or 0)
    if (hs, hc) != (cur["HairStyle"], cur["HairColor"]):
        rows = [x for x in hair_rows() if x[1] in (g, 0) and x[5] == hs and x[6] == hc]
        if not rows:
            raise OpRefused("причёски (стиль %d, цвет %d) для пола %d нет в HairTypeTable сервера" % (hs, hc, g))
        if not any(x[3] == 1 for x in rows):
            raise OpRefused("причёска (стиль %d, цвет %d) не продаётся (HairTypeTable +68 ≠ 1) — у клиента может не быть её модели" % (hs, hc))
    if ft != cur["FaceType"] and ft not in FACES.get(g, ()):
        raise OpRefused("лицо %d — не из лиц пола %d (окно создания клиента: %s)" % (ft, g, "0…%d" % (len(FACES.get(g, (0,))) - 1)))
    new = {"HairStyle": hs, "HairColor": hc, "FaceType": ft}
    if new == cur:
        raise OpRefused("внешность не меняется")
    text = "внешность персонажа %s (%d/%d): причёска %d/%d → %d/%d, лицо %d → %d" % (
        ch["Charname"], uid, idx, cur["HairStyle"], cur["HairColor"], hs, hc, cur["FaceType"], ft)
    warn = ["журналы покупки причёски (SaleHair, HairChange) не пишутся — это не покупка"]
    if ft != cur["FaceType"]:
        warn.append("смены лица у сервера нет (лицо задаётся при создании) — клиент покажет новое лицо после входа")
    return [uid], [("CharAppr", [uid, idx], cur, new)], text, warn


def _plus(w, uid, idx, lock):
    return _rows(w, "CharPlusPackage", "Userindex = ? AND Charidx = ?", (uid, idx), lock)


def plan_plus_remove(w, p, lock=False, role=None):
    uid, idx = _args(p, role)
    ch = _char(w, uid, idx, lock)
    rows = _plus(w, uid, idx, lock)
    if not rows:
        raise OpRefused("у персонажа нет бафа набора")
    changes = [("CharPlusPackage", [uid, idx], b, None) for _k, b in rows]
    b = rows[0][1]
    text = "снять бафф набора у персонажа %s (%d/%d): тип %d, до %s" % (ch["Charname"], uid, idx, b["iType"], b["EndTime"])
    return [uid], changes, text, []


def plan_plus_set(w, p, lock=False, role=None):
    uid, idx, it = _args(p, role, "type")
    types = plus_types()
    if it not in types or it < 1:
        raise OpRefused("типа бафа %d нет в PlusPackageTable сервера (есть: %s)" % (it, ", ".join(str(x) for x in sorted(types) if x >= 1)))
    mins = types[it][0] if types[it] else 0
    if mins <= 0:
        raise OpRefused("у типа бафа %d в PlusPackageTable нет срока" % it)
    ch = _char(w, uid, idx, lock)
    rows = _plus(w, uid, idx, lock)
    now = _now(w)
    new = {"iType": it, "StartTime": now, "BuffPeriod": mins, "EndTime": _ds(_dt(now) + datetime.timedelta(minutes=mins)), "_set": True}
    warn = []
    if rows:
        b = rows[0][1]
        # ★ ревизия 26 М-1: сначала удалить лишние строки, потом обновить первую — PK (Userindex, Charidx, iType) не нарушится, если
        # выдаваемый тип уже стоит в лишней строке; откат идёт в обратном порядке (вернуть первую, затем вставить лишние)
        changes = [("CharPlusPackage", [uid, idx], x, None) for _k, x in rows[1:]] + [("CharPlusPackage", [uid, idx], b, new)]
        if b["EndTime"] > now:
            warn.append("действующий бафф (тип %d, до %s) заменяется — срок считается заново, как при применении набора" % (b["iType"], b["EndTime"]))
        if rows[1:]:
            warn.append("лишние строки бафа персонажа удаляются (сервер держит одну)")
    else:
        changes = [("CharPlusPackage", [uid, idx], None, new)]
    text = "выдать бафф набора тип %d персонажу %s (%d/%d): %d мин" % (it, ch["Charname"], uid, idx, mins)
    return [uid], changes, text, warn + ["журнал применения набора (UsePlusPackage) не пишется — предмет не тратится"]


def plan_plus_extend(w, p, lock=False, role=None):
    uid, idx, n = _args(p, role, "minutes")
    if not 1 <= n <= 525600:
        raise OpRefused("продлить — от 1 до 525600 минут (год)")
    ch = _char(w, uid, idx, lock)
    rows = _plus(w, uid, idx, lock)
    if not rows:
        raise OpRefused("у персонажа нет бафа набора — сначала выдайте его")
    b = rows[0][1]
    now = _now(w)
    if b["EndTime"] <= now:
        raise OpRefused("бафф истёк (%s) — сервер удалит его при входе; выдайте новый" % b["EndTime"])
    if int(b["BuffPeriod"] or 0) + n > INT_MAX:
        raise OpRefused("срок бафа вышел бы за предел поля")
    end = _dt(b["EndTime"]) + datetime.timedelta(minutes=n)
    if end.year > 2078:
        raise OpRefused("срок бафа вышел бы за предел smalldatetime (2079 год)")
    a = dict(b, BuffPeriod=int(b["BuffPeriod"] or 0) + n, EndTime=_ds(end))
    text = "продлить бафф набора персонажа %s (%d/%d) на %d мин: до %s → до %s" % (ch["Charname"], uid, idx, n, b["EndTime"], a["EndTime"])
    return [uid], [("CharPlusPackage", [uid, idx], b, a)], text, []


def _camp(w, uid, idx, lock):
    r = _rows(w, "CharCamp", "Userindex = ? AND Charidx = ?", (uid, idx), lock)
    return r[0][1] if r else None


def plan_penalty(w, p, lock=False, role=None):
    uid, idx = _args(p, role)
    ch = _char(w, uid, idx, lock)
    c = _camp(w, uid, idx, lock)
    if not c:
        raise OpRefused("у персонажа нет строки лагеря (CharCamp) — штрафа нет")
    if not c["CampPenaltyTime"]:
        raise OpRefused("штрафа лагеря нет")
    text = "снять штраф лагеря персонажа %s (%d/%d): %d → 0" % (ch["Charname"], uid, idx, c["CampPenaltyTime"])
    return [uid], [("CharCamp", [uid, idx], c, dict(c, CampPenaltyTime=0))], text, [
        "штраф хранится в тиках сервера (GetTickCount) — после перезапуска GameServer старый штраф и так теряет смысл"]


def plan_army(w, p, lock=False, role=None):
    uid, _idx, army = _args(p, role, "army")
    if army not in ARMY_NAMES:
        raise OpRefused("армия — −1 (снять), 0, 1 или 2")
    chars = w.rows("SELECT Charidx, Charname, JobCount FROM dbo.Charinfo%s WHERE Userindex = ? ORDER BY Charidx" % _hint(lock), (uid,))
    if not chars:
        raise OpRefused("у учётки %d нет персонажей" % uid)
    have = {k["Charidx"]: b for k, b in _rows(w, "CharCamp", "Userindex = ?", (uid,), lock)}
    if army >= 0 and not any(int(c["JobCount"] or 0) >= 2 for c in chars):
        raise OpRefused("ни у одного персонажа учётки нет второй профессии — сервер не дал бы выбрать армию (User_Game_SelectSquad: JobCount < 2)")
    changes = []
    for c in chars:
        i = int(c["Charidx"])
        b = have.get(i)
        if b is not None and b["Campidx"] != army:
            changes.append(("CharCamp", [uid, i], b, dict(b, Campidx=army)))
        elif b is None and army >= 0:
            changes.append(("CharCamp", [uid, i], None, {"Campidx": army, "CampPoint": 0, "CampGrade": 0, "CampFlag": 0, "CampPenaltyTime": 0}))
    if not changes:
        raise OpRefused("армия учётки уже %s" % ARMY_NAMES[army])
    olds = sorted({ARMY_NAMES.get(b["Campidx"], str(b["Campidx"])) for b in have.values()}) or [ARMY_NAMES[-1]]
    text = "армия учётки %d: %s → %s (персонажей %d)" % (uid, ", ".join(olds), ARMY_NAMES[army], len(chars))
    warn = ["счётчики армий CampData (их ведёт RelayServer) не меняются — они уже расходятся с базой; очки чести остаются, как при смене армии предметом"]
    if any(b["Campidx"] != army and b["CampPoint"] for b in have.values()):
        warn.append("у персонажей учётки есть очки чести — они остаются за новой армией")
    return [uid], changes, text, warn


def plan_craft_level(w, p, lock=False, role=None):
    uid, idx, lv = _args(p, role, "level")
    levels = craft_levels()
    if not 1 <= lv <= len(levels):
        raise OpRefused("уровень ремесла — от 1 до %d (CraftLevel сервера)" % len(levels))
    lo, hi = craft_bounds(lv, levels)
    ex = lo if p.get("exp") in (None, "") else _int(p["exp"], "опыт ремесла — целое число")
    if not lo <= ex <= hi:
        raise OpRefused("опыт ремесла уровня %d — от %d до %d (пороги CraftLevel сервера)" % (lv, lo, hi))
    ch = _char(w, uid, idx, lock)
    r = _rows(w, "CRT_CharCraftInfo", "Userindex = ? AND Charidx = ?", (uid, idx), lock)
    if not r:
        raise OpRefused("у персонажа нет строки ремесла — её создаёт сервер при входе (CRT_UPCraftInfoList)")
    b = r[0][1]
    a = {"iLevel": lv, "iExp": ex}
    if a == b:
        raise OpRefused("уровень и опыт ремесла не меняются")
    text = "ремесло персонажа %s (%d/%d): уровень %d → %d, опыт %d → %d" % (ch["Charname"], uid, idx, b["iLevel"], lv, b["iExp"], ex)
    warn = []
    if lv >= 7:
        warn.append("уровни 7…10 в CraftLevel без роста опыта (порог %d) — как сервер поднимает их опытом, не проверено; обычно — свитком" % levels[5][1])
    return [uid], [("CRT_CharCraftInfo", [uid, idx], b, a)], text, warn


def plan_craft_daily(w, p, lock=False, role=None):
    uid, idx = _args(p, role)
    ch = _char(w, uid, idx, lock)
    changes = []
    for k, b in _rows(w, "CRT_LimitationQuest", "Userindex = ? AND Charidx = ? AND Quest_Type = 1", (uid, idx), lock):
        a = dict(b, Quest_Flag=0 if b["Quest_Flag"] == 3 else b["Quest_Flag"], Quest_Count=0)
        if a != b:
            changes.append(("CRT_LimitationQuest", [uid, idx, k["Quest_Index"]], b, a))
    if not changes:
        raise OpRefused("сбрасывать нечего: ежедневных заданий ремесла со сданным флагом или счётчиком нет")
    text = "суточный сброс заданий ремесла персонажа %s (%d/%d): строк %d" % (ch["Charname"], uid, idx, len(changes))
    return [uid], changes, text, ["как суточный сброс сервера: флаг «сдано» (3) → 0 и счётчик → 0 у ежедневных (Quest_Type 1); взятые задания остаются"]


def plan_fish_skill(w, p, lock=False, role=None):
    uid, idx, v = _args(p, role, "value")
    if not 0 <= v <= INT_MAX:
        raise OpRefused("навык рыбалки — от 0 до 2 147 483 647")
    ch = _char(w, uid, idx, lock)
    r = _rows(w, "CharFish", "Userindex = ? AND Charidx = ?", (uid, idx), lock)
    b = r[0][1] if r else None
    cur = b["FishingSkill"] if b else 0
    if cur == v and (b or v == 0):
        raise OpRefused("навык рыбалки уже %d" % v)
    text = "навык рыбалки персонажа %s (%d/%d): %d → %d" % (ch["Charname"], uid, idx, cur, v)
    return [uid], [("CharFish", [uid, idx], b, {"FishingSkill": v})], text, []


def plan_fishbook_delete(w, p, lock=False, role=None):
    uid, idx, book = _args(p, role, "book")
    ch = _char(w, uid, idx, lock)
    r = _rows(w, "CharFishBookInfo", "Userindex = ? AND Charidx = ? AND BookCode = ?", (uid, idx, book), lock)
    if not r:
        raise OpRefused("книги рыб %d у персонажа нет" % book)
    b = r[0][1]
    got = sum(1 for i in range(30) if int(b.get("FishCount%d" % i) or 0) > 0)
    text = "удалить книгу рыб %d персонажа %s (%d/%d): сдано видов %d" % (book, ch["Charname"], uid, idx, got)
    return [uid], [("CharFishBookInfo", [uid, idx, book], b, None)], text, [
        "как удаление книги сервером: сданная в книгу рыба и награда за неё пропадут (вернуть — откатом)"]


def _tut_bit(row, i):
    return bool(((int(row["Tutorial%d" % (i // 64 + 1)]) & 0xFFFFFFFFFFFFFFFF) >> (i % 64)) & 1) if row else False


def plan_tutorial(w, p, lock=False, role=None):
    uid, idx = _args(p, role)
    raw = p.get("steps")
    if not isinstance(raw, list):
        raise OpRefused("шаги обучения — список номеров")
    exp = tutorial_exp()
    n = len(exp)
    want = set()
    for x in raw:
        s = _int(x, "номер шага обучения — целое число")
        if not 0 <= s < n:
            raise OpRefused("шага обучения %d нет (Tutorial_ExpInfo сервера: 0…%d)" % (s, n - 1))
        want.add(s)
    ch = _char(w, uid, idx, lock)
    r = _rows(w, "CharTutorial", "Userindex = ? AND Charidx = ?", (uid, idx), lock)
    b = r[0][1] if r else None
    a = dict(b) if b else {"Tutorial1": 0, "Tutorial2": 0, "Tutorial3": 0, "Tutorial4": 0}
    for i in range(n):
        k = "Tutorial%d" % (i // 64 + 1)
        v = int(a[k]) & 0xFFFFFFFFFFFFFFFF
        a[k] = _s64((v | (1 << (i % 64))) if i in want else (v & ~(1 << (i % 64))))
    if a == (b or {"Tutorial1": 0, "Tutorial2": 0, "Tutorial3": 0, "Tutorial4": 0}) and (b or not want):
        raise OpRefused("отметки обучения не меняются")
    on = sorted(i for i in want if not _tut_bit(b, i))
    off = sorted(i for i in range(n) if _tut_bit(b, i) and i not in want)
    text = "обучение персонажа %s (%d/%d): поставить %s, снять %s" % (
        ch["Charname"], uid, idx, ", ".join(map(str, on)) or "—", ", ".join(map(str, off)) or "—")
    warn = []
    again = [i for i in off if exp[i] > 0]
    if again:
        warn.append("снятые шаги сервер наградит опытом ещё раз, когда игрок пройдёт их снова: %s"
                    % ", ".join("%d (+%d)" % (i, exp[i]) for i in again))
    if on:
        warn.append("поставленные шаги опыта не дают (опыт сервер начисляет только при прохождении)")
    return [uid], [("CharTutorial", [uid, idx], b, a)], text, warn


# ---------------------------------------------------------------------------------------------------------------- операции
class _RowOp(Operation):
    """Каркас: предпросмотр → запись под блокировкой учёток → откат по «было» (как titles / quests)."""
    reversible = True
    planner = None

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uids, changes, text, warn = type(self).planner(ad, p, role=ctx.role)
                for u in uids:
                    ok, why = items.online_state(ad, u)
                    if not ok:
                        raise OpRefused("править можно только когда игрок не в игре: " + why)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        rec = [items.RECENT_WARN] if any(items.recently_left(u) for u in uids) else []
        return {"text": text, "expect": _sig(changes), "warnings": warn + rec}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры персонажа")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uids, changes, text, warn = type(self).planner(w, p, lock=True, role=ctx.role)
            sg = _sig(changes)
            if sg != prev["expect"] or ("expect" in p and p["expect"] != sg):
                raise OpRefused("пока вы смотрели предпросмотр, данные персонажа изменились — повторите")
            changes = _strip(changes)
            for t, k, b, a in changes:
                _put(w, t, k, b, a, "данные персонажа изменились при записи — ничего не записано")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uids[0], "idx": p.get("idx")},
                "after": {"uid": uids[0], "idx": p.get("idx"), "changes": [[t, k, b, a] for t, k, b, a in changes]},
                "message": text, "_commit": w.commit, "_close": w.close}

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
                if t not in TABLES:
                    raise OpRefused("в журнале неожиданная таблица — откат не выполнен")
                if int(k[0]) != int(uid):
                    raise OpRefused("в журнале строка другой учётки — откат не выполнен")
                _put(w, t, k, af, b, "данные персонажа с тех пор менялись — откат не выполнен")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"changes": ch}, "after": {"uid": uid, "idx": a.get("idx")},
                "message": "%s: возвращено" % self.title, "_commit": w.commit, "_close": w.close}


@register
class AppearanceSet(_RowOp):
    name, title, perm = "appearance.set", "Персонаж: внешность", "players.appearance"
    planner = staticmethod(plan_appearance)


@register
class PlusRemove(_RowOp):
    name, title, perm = "plus.remove", "Персонаж: снять бафф набора", "players.plus"
    planner = staticmethod(plan_plus_remove)


@register
class PlusSet(_RowOp):
    name, title, perm = "plus.set", "Персонаж: выдать бафф набора", "players.plus"
    planner = staticmethod(plan_plus_set)


@register
class PlusExtend(_RowOp):
    name, title, perm = "plus.extend", "Персонаж: продлить бафф набора", "players.plus"
    planner = staticmethod(plan_plus_extend)


@register
class CampPenaltyClear(_RowOp):
    name, title, perm = "camp.penalty_clear", "Персонаж: снять штраф лагеря", "players.camp"
    planner = staticmethod(plan_penalty)


@register
class CampSetArmy(_RowOp):
    name, title, perm = "camp.set_army", "Учётка: сменить армию", "players.camp"
    planner = staticmethod(plan_army)

    def target(self, p):
        return "account:%s" % p.get("uid")


@register
class CraftSetLevel(_RowOp):
    name, title, perm = "craft.set_level", "Персонаж: уровень ремесла", "players.craft"
    planner = staticmethod(plan_craft_level)


@register
class CraftDailyReset(_RowOp):
    name, title, perm = "craft.daily_reset", "Персонаж: суточный сброс заданий ремесла", "players.craft"
    planner = staticmethod(plan_craft_daily)


@register
class FishSetSkill(_RowOp):
    name, title, perm = "fish.set_skill", "Персонаж: навык рыбалки", "players.craft"
    planner = staticmethod(plan_fish_skill)


@register
class FishBookDelete(_RowOp):
    name, title, perm = "fishbook.delete", "Персонаж: удалить книгу рыб", "players.craft"
    planner = staticmethod(plan_fishbook_delete)


@register
class TutorialSet(_RowOp):
    name, title, perm = "tutorial.set", "Персонаж: отметки обучения", "players.tutorial"
    planner = staticmethod(plan_tutorial)


def rank_state(r):
    """Кандидаты и строки рейтинга чести (как отбирает UP_CampPointRank: CampPoint > 0, Userindex > 5000)."""
    c = r.rows("SELECT COUNT(*) AS n FROM dbo.CharCamp WHERE CampPoint > 0 AND Userindex > 5000")[0]["n"]
    k = r.rows("SELECT COUNT(*) AS n FROM dbo.CampPointRank")[0]["n"]
    return int(c), int(k)


@register
class CampRankRebuild(Operation):
    """Пересчёт рейтинга чести — EXEC adm.CampPointRank (штатный UP_CampPointRank). Не откатывается: рейтинг производный
    (его можно пересчитать в любой момент); GS читает Per только при входе (UPCharCamp)."""
    name, title, perm, reversible = "camp.rank_rebuild", "Лагерь: пересчитать рейтинг чести", "players.camp", False

    def target(self, p):
        return "camp:rank"

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                c, k = rank_state(items._ReaderAdapter(r))
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        return {"text": "пересчитать рейтинг чести: персонажей с очками %d, строк в рейтинге сейчас %d" % (c, k), "expect": [c, k],
                "warnings": ["ступень чести изменится у персонажей при следующем входе (сервер читает рейтинг при входе); служебные учётки (≤ 5000) в рейтинг не входят, как у сервера"]}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            c, k = rank_state(w)
            if "expect" in p and p["expect"] != [c, k]:
                raise OpRefused("пока вы смотрели предпросмотр, очки чести изменились — повторите")
            r = w.rows("EXEC adm.CampPointRank")
            n = int(r[0]["Ranked"]) if r else -1
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"candidates": c, "ranked": k}, "after": {"ranked": n},
                "message": "рейтинг чести пересчитан: строк %d (было %d)" % (n, k), "_commit": w.commit, "_close": w.close}


def describe(uid, idx):
    """Окно «Внешность, баффы, лагерь, ремесло, обучение»: текущие значения и допустимые варианты."""
    uid, idx = int(uid), int(idx)
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        ch = _char(ad, uid, idx, False)
        appr = _rows(ad, "CharAppr", "Userindex = ? AND Charidx = ?", (uid, idx), False)
        plus = _plus(ad, uid, idx, False)
        now = _now(ad)
        camp = _camp(ad, uid, idx, False)
        acc_camp = [dict(b, idx=k["Charidx"]) for k, b in _rows(ad, "CharCamp", "Userindex = ?", (uid,), False)]
        rank = ad.rows("SELECT Ranking, Per FROM dbo.CampPointRank WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        craft = ad.rows("SELECT CashCount, iLevel, iExp, iBit1, iBit2, iBit3, iBit4, iBit5, iBit6, iBit7, iBit8, iBit9 FROM dbo.CRT_CharCraftInfo "
                        "WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        lim = [dict(b, Quest_Index=k["Quest_Index"]) for k, b in _rows(ad, "CRT_LimitationQuest", "Userindex = ? AND Charidx = ?", (uid, idx), False)]
        fish = _rows(ad, "CharFish", "Userindex = ? AND Charidx = ?", (uid, idx), False)
        books = [{"book": k["BookCode"], "complete": b.get("Complete"), "type": b.get("BookType"),
                  "fish": [[b.get("FishItemCode%d" % i), b.get("FishCount%d" % i)] for i in range(30) if (b.get("FishItemCode%d" % i) or -1) >= 0]}
                 for k, b in _rows(ad, "CharFishBookInfo", "Userindex = ? AND Charidx = ?", (uid, idx), False)]
        tut = _rows(ad, "CharTutorial", "Userindex = ? AND Charidx = ?", (uid, idx), False)
        att = ad.rows("SELECT ACount, Step, CONVERT(varchar(19), RegistDay, 120) AS RegistDay FROM dbo.AttendanceCount WHERE Userindex = ? AND Charidx = ?",
                      (uid, idx))
        days = ad.rows("SELECT TOP 60 CONVERT(varchar(19), RegistDay, 120) AS d FROM dbo.AttendanceDetail WHERE Userindex = ? AND Charidx = ? "
                       "ORDER BY RegistDay DESC", (uid, idx))
        chars = ad.rows("SELECT Charidx, Charname, JobCount FROM dbo.Charinfo WHERE Userindex = ? ORDER BY Charidx", (uid,))
    g = int(ch["Gender"] or 0)
    out = {"uid": uid, "idx": idx, "name": ch["Charname"], "gender": g, "now": now, "errors": []}
    a = appr[0][1] if appr else None
    out["appearance"] = a
    try:
        out["hair"] = [{"id": x[0], "style": x[5], "color": x[6], "level": x[2], "price": x[4]} for x in hair_rows() if x[1] in (g, 0) and x[3] == 1]
    except OpRefused as ex:
        out["hair"], out["errors"] = [], out["errors"] + [str(ex)]
    out["faces"] = list(FACES.get(g, ()))
    try:
        out["plus_types"] = [{"type": k, "minutes": v[0] if v else 0, "mult": v[1:]} for k, v in sorted(plus_types().items()) if k >= 1]
    except OpRefused as ex:
        out["plus_types"], out["errors"] = [], out["errors"] + [str(ex)]
    out["plus"] = [dict(b, active=b["EndTime"] > now) for _k, b in plus]
    out["camp"] = camp
    out["army_names"] = {str(k): v for k, v in ARMY_NAMES.items()}
    out["account_camp"] = acc_camp
    out["account_chars"] = [{"idx": c["Charidx"], "name": c["Charname"], "jobcount": c["JobCount"]} for c in chars]
    out["rank"] = rank[0] if rank else None
    if craft:
        c = craft[0]
        bits = []
        for k in range(1, 10):
            v = int(c["iBit%d" % k] or 0) & 0xFFFFFFFFFFFFFFFF
            bits += [(k - 1) * 64 + b for b in range(64) if (v >> b) & 1]
        out["craft"] = {"level": c["iLevel"], "exp": c["iExp"], "cash": c["CashCount"], "recipe_bits": bits}
    else:
        out["craft"] = None
    try:
        lv = craft_levels()
        out["craft_levels"] = [{"level": x[0], "threshold": x[1], "lo": craft_bounds(x[0], lv)[0], "hi": craft_bounds(x[0], lv)[1]} for x in lv]
    except OpRefused as ex:
        out["craft_levels"], out["errors"] = [], out["errors"] + [str(ex)]
    out["craft_daily"] = lim
    out["fish"] = fish[0][1]["FishingSkill"] if fish else None
    out["fish_books"] = books
    tb = tut[0][1] if tut else None
    try:
        ex = tutorial_exp()
        out["tutorial"] = [{"step": i, "exp": ex[i], "done": _tut_bit(tb, i)} for i in range(len(ex))]
    except OpRefused as e:
        out["tutorial"], out["errors"] = [], out["errors"] + [str(e)]
    out["tutorial_raw"] = {k: _js(v) for k, v in tb.items()} if tb else None
    out["attendance"] = {"count": att[0] if att else None, "days": [d["d"] for d in days]}
    return out
