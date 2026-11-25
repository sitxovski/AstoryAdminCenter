# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""titles.py — звания, слава и очки чести персонажа НЕ В ИГРЕ (волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_titles_honor.md (GameServer.c, DBManager, FameInfo.txt, живая Joy1). РЕШЕНИЯ
ВЛАДЕЛЬЦА 18.11: выдать/снять звание; «очки чести» = CharCamp.CampPoint (очки войны фракций — метка 10082 окна персонажа);
слава — только «пересчитать как сервер при входе» (ручная слава живёт до входа: recvDB пересчитывает Fmpoint по маске, 2274).
ХРАНЕНИЕ: CharFame (Userindex, Charidx, Fameidx) — счётчик Condition1/2 и 6 опций; CharFameBank — Fmpoint, надетые Fmidx1/2, маска
  «получено» Fame1…4 (биты 0…255: слово id/64 + 1, бит id % 64; бит 63 — знаковый в bigint); CharFameProgress — маска «найдено»
  Fame1…4; CharFameHigh (P22) — биты 256…511 обеих масок (BankHi1…4, ProgHi1…4). FameInfo.txt — srvtables.fame_info().
ВЫДАТЬ — как AddFameBit после sub_54B260 (GameServer.c:126507, :126900–127050): строка CharFame (Condition1 = max(текущее,
  цель); у 47…55 и 237…244 ещё Condition2 = max(текущее, параметр) — их условие выдачи двойное; опции — коды FameInfo), бит маски,
  Fmpoint += очки (кол. 42), бит «найдено» по правилу второй ступени (кол. 43/44, ветки по id), каскад наборов sub_54A610 (цели
  133…136 — без строки CharFame, как у сервера). id ≥ 256 — CharFameHigh (как P21 HighAdd + P22), строка CharFame не пишется.
  Отказ: рейтинговые 65…69 (хозяин — P23: снимет/выдаст сам), выключенные, чужой класс, уже есть, строк CharFame > 256.
СНЯТЬ — как DeleteFameInfo → SubFameBit (:126571): бит снят, Fmpoint −= очки (не ниже 0), CharFame = 0/0, опции −1/0 (upsert),
  бит «найдено» ставится, надетое (Fmidx) снимается. Наборы не снимаются (у сервера тоже). Отказ: 65…69, звания нет.
ЗАПИСЬ — asda_ops, одна транзакция, «не в игре» под блокировкой (items.online_state); строки — набор «было → стало», откат
  возвращает «было», если строки с тех пор не менялись. Побочных эффектов при импорте нет.
"""
import json
import os

from core import bridge, db
from core.ops import Operation, OpRefused, register
from domains import items, srvtables

RATING = set(range(65, 70))
SET_TARGETS = {133, 134, 135, 136}
DOUBLE = set(range(47, 56)) | set(range(237, 245))       # условие выдачи — Condition1 и Condition2
MAX_FAME_ROWS = 256                                         # DBManager обрезает загрузку UPCharFame до 256 строк
OPERATOR_MAX_UID = 5000
OPT_COLS = [("Opidx%d" % m, "Opvalue%d1" % m, "Opvalue%d2" % m) for m in range(1, 7)]
TABLES = {
    "CharFame": (("Userindex", "Charidx", "Fameidx"), ["Condition1", "Condition2"] + [c for t in OPT_COLS for c in t]),
    "CharFameBank": (("Userindex", "Charidx"), ["Fmpoint", "Fmidx1", "Fmidx2", "Fame1", "Fame2", "Fame3", "Fame4"]),
    "CharFameProgress": (("Userindex", "Charidx"), ["Fame1", "Fame2", "Fame3", "Fame4"]),
    "CharFameHigh": (("UserIndex", "CharIdx"), ["BankHi1", "BankHi2", "BankHi3", "BankHi4", "ProgHi1", "ProgHi2", "ProgHi3", "ProgHi4"]),
}
_names = {}


def names():
    """{id: [ru, en, ClassReq, Group, Position, Enabled, Point]} — data/ref/titles.json (tools/build_ref_data.py --titles)."""
    if "t" not in _names:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ref", "titles.json")
        try:
            with open(p, encoding="utf-8") as f:
                _names["t"] = {int(k): v for k, v in json.load(f).items()}
        except OSError:
            _names["t"] = {}
    return _names["t"]


def title_name(i):
    from core import i18n
    r = names().get(int(i))
    if not r:
        return "звание %d" % i
    return (r[1] or r[0]) if i18n.is_en() else (r[0] or r[1])


def _s64(v):
    v &= 0xFFFFFFFFFFFFFFFF
    return v - (1 << 64) if v >= 1 << 63 else v


def _bit(row, prefix, i):
    w = int((row or {}).get("%s%d" % (prefix, i // 64 + 1)) or 0)
    return bool((w >> (i % 64)) & 1)


def _set_bit(row, prefix, i, on):
    k = "%s%d" % (prefix, i // 64 + 1)
    w = int(row.get(k) or 0) & 0xFFFFFFFFFFFFFFFF
    w = (w | (1 << (i % 64))) if on else (w & ~(1 << (i % 64)))
    row[k] = _s64(w)


def _row(w, table, key, lock):
    kc, cols = TABLES[table]
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT %s FROM dbo.%s%s WHERE %s" % (", ".join(cols), table, hint, " AND ".join("%s = ?" % k for k in kc)), key)
    return {c: (int(r[0][c]) if r[0][c] is not None else None) for c in cols} if r else None


def _found(fi, i, c1, c2):
    """Бит «найдено» при выдаче — вторая ступень sub_54B260 (кол. 43 вид, 44 порог; ветки по id :126900–127030)."""
    r = fi[i]
    kind, thr, tgt = r[43], r[44], r[3]
    # перепроверка 20 К1: звание 21 считается в ветке default (v43 не ставится), id ≥ 256 — вне гейта v23 < 4 (:127040)
    if not kind or i == 21 or i >= 256:
        return False
    if i in range(47, 56):
        return c1 == tgt and (c2 >= thr if kind == 1 else (tgt > 0 and thr <= c2 * 100.0 / tgt))
    if i in range(237, 245):
        return (c1 >= thr and c2 >= thr) if kind == 1 else (tgt > 0 and thr <= c1 * 100.0 / tgt)
    if kind == 1:
        return c1 >= thr
    return tgt <= 0 or thr <= c1 * 100.0 / tgt


def _load(w, uid, idx, lock):
    ch = w.rows("SELECT Charname, Class FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?"
                % (" WITH (UPDLOCK, HOLDLOCK)" if lock else ""), (uid, idx))
    if not ch:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    st = {"bank": _row(w, "CharFameBank", (uid, idx), lock), "prog": _row(w, "CharFameProgress", (uid, idx), lock),
          "high": _row(w, "CharFameHigh", (uid, idx), lock)}
    return ch[0], st


def _plan_args(p, role):
    try:
        uid, idx, tid = int(p["uid"]), int(p["idx"]), int(p["title"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры звания")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return uid, idx, tid


def _fi():
    try:
        return srvtables.fame_info()
    except Exception as ex:
        raise OpRefused("FameInfo.txt сервера не прочитан: %s" % ex)


def hidden_next(fi, tid):
    """★ ревизия 38 М-2: выключенные «следующие» (FameInfo кол. 10/11) звания tid. Каскад наборов sub_54A610 (GameServer.c:126411)
    после выдачи tid проверяет только предпосылки «следующего» и зовёт AddFameBit sub_54A980 — байт «включено» (+2) не проверяет никто;
    живая выдача P127 title_add зовёт тот же каскад (pFameSet 0x54A610, p127_admin_bridge.cpp:934). → [номера]."""
    r = fi[tid] if 0 <= tid < len(fi) else []
    out = []
    for n in (r[10:12] if len(r) > 11 else ()):
        if 0 <= n < len(fi) and len(fi[n]) > 1 and not fi[n][1] and n not in out:
            out.append(n)
    return out


def _empty(table):
    return {c: (-1 if c.startswith("Opidx") or c.startswith("Fmidx") else 0) for c in TABLES[table][1]}


def plan_grant(w, p, lock=False, role=None):
    uid, idx, tid = _plan_args(p, role)
    fi = _fi()
    if not 0 <= tid < len(fi):
        raise OpRefused("звания %d нет в FameInfo сервера" % tid)
    if tid in RATING:
        raise OpRefused("рейтинговые звания 65–69 выдаёт и снимает сервер (P23) — используйте пересчёт рейтинга P25")
    r = fi[tid]
    if not r[1]:
        raise OpRefused("звание %d выключено на сервере — игрой его не получить, клиент его не показывает" % tid)
    ch, st = _load(w, uid, idx, lock)
    nm = names().get(tid)
    if nm and nm[2] and int(nm[2]) != int(ch["Class"] or 0):
        raise OpRefused("звание %d — для другого класса" % tid)
    hi = tid >= 256
    if (_bit(st["high"], "BankHi", tid - 256) if hi else _bit(st["bank"], "Fame", tid)):
        raise OpRefused("звание уже получено")
    changes, warn, pts = [], [], r[42]
    bank = dict(st["bank"]) if st["bank"] else _empty("CharFameBank")
    c1 = c2 = None
    if not hi and tid not in SET_TARGETS:
        fr = _row(w, "CharFame", (uid, idx, tid), lock)
        if fr is None:
            n = w.rows("SELECT COUNT(*) AS n FROM dbo.CharFame WHERE Userindex = ? AND Charidx = ?", (uid, idx))[0]["n"]
            if int(n) + 1 > MAX_FAME_ROWS:
                raise OpRefused("у персонажа будет больше %d строк званий — сервер при входе загрузит не все" % MAX_FAME_ROWS)
        new = dict(fr) if fr else _empty("CharFame")
        # перепроверка 20 К2: у 47…55 сервер выдаёт только при Condition1 == цели (:126964), у прочих — при ≥ цели
        new["Condition1"] = r[3] if tid in range(47, 56) else max(int(new["Condition1"] or 0), r[3])
        if tid in DOUBLE:
            new["Condition2"] = max(int(new["Condition2"] or 0), r[4])
        import random
        rng = random.SystemRandom()
        for m, (oi, v1, v2) in enumerate(OPT_COLS):
            code, a1, b1, a2, b2 = r[12 + 5 * m: 17 + 5 * m]
            if code > -1:                                      # sub_54A980: опции записи — из FameInfo, значения sub_5329A0(min,max)
                new[oi], new[v1], new[v2] = code, rng.randint(min(a1, b1), max(a1, b1)), rng.randint(min(a2, b2), max(a2, b2))
        changes.append(("CharFame", [uid, idx, tid], fr, new))
        c1, c2 = new["Condition1"], new["Condition2"]
    else:
        c1, c2 = r[3], r[4]
    got = []
    if hi:
        high = dict(st["high"]) if st["high"] else _empty("CharFameHigh")
        _set_bit(high, "BankHi", tid - 256, True)
        if _found(fi, tid, c1, c2):
            _set_bit(high, "ProgHi", tid - 256, True)
    else:
        _set_bit(bank, "Fame", tid, True)
        got.append(tid)
    bank["Fmpoint"] = int(bank["Fmpoint"] or 0) + pts
    # каскад наборов (sub_54A610): «следующее» N, у которого есть предпосылки и все получены, — бит N и очки, строки CharFame нет
    for nxt in (r[10], r[11]):
        if 0 <= nxt < min(len(fi), 256) and not _bit(bank, "Fame", nxt):
            pre = [x for x in fi[nxt][5:10] if x >= 0]
            if pre and all(_bit(bank, "Fame", x) for x in pre) and fi[nxt][1]:
                _set_bit(bank, "Fame", nxt, True)
                bank["Fmpoint"] += fi[nxt][42]
                got.append(nxt)
                warn.append("собран набор — получено и звание %d «%s»" % (nxt, title_name(nxt)))
            elif pre and all(_bit(bank, "Fame", x) for x in pre):
                # ★ ревизия 38 М-2: сервер каскадом выдал бы и выключенное (sub_54A610 «включено» не проверяет) — панель скрытое не выдаёт
                warn.append("собран набор, но звание %d «%s» выключено — панель его не выдаёт (каскад сервера sub_54A610 выдал бы его "
                            "скрытым)" % (nxt, title_name(nxt)))
    prog = dict(st["prog"]) if st["prog"] else _empty("CharFameProgress")
    for g in got:
        if not _bit(prog, "Fame", g) and _found(fi, g, c1 if g == tid else fi[g][3], c2 if g == tid else fi[g][4]):
            _set_bit(prog, "Fame", g, True)
    changes.append(("CharFameBank", [uid, idx], st["bank"], bank))
    if prog != (st["prog"] or _empty("CharFameProgress")):
        changes.append(("CharFameProgress", [uid, idx], st["prog"], prog))
    if hi:
        changes.append(("CharFameHigh", [uid, idx], st["high"], high))
    if tid == 21:
        warn.append("звание 21 «30 званий» сервер считает в памяти — счётчик панель не восстанавливает")
    text = "выдать звание %d «%s» персонажу %s (%d/%d): слава %s → %s" % (
        tid, title_name(tid), ch["Charname"], uid, idx, (st["bank"] or {}).get("Fmpoint", 0), bank["Fmpoint"])
    return uid, idx, [c for c in changes if c[2] != c[3]], text, warn


def plan_revoke(w, p, lock=False, role=None):
    uid, idx, tid = _plan_args(p, role)
    fi = _fi()
    if not 0 <= tid < len(fi):
        raise OpRefused("звания %d нет в FameInfo сервера" % tid)
    if tid in RATING:
        raise OpRefused("рейтинговые звания 65–69 выдаёт и снимает сервер (P23) — используйте пересчёт рейтинга P25")
    ch, st = _load(w, uid, idx, lock)
    hi = tid >= 256
    if not (_bit(st["high"], "BankHi", tid - 256) if hi else _bit(st["bank"], "Fame", tid)):
        raise OpRefused("у персонажа нет этого звания")
    changes, warn = [], []
    if not st["bank"]:
        raise OpRefused("у персонажа нет строки славы (CharFameBank) — её создаёт сервер при входе")
    bank = dict(st["bank"])
    bank["Fmpoint"] = max(0, int(bank["Fmpoint"] or 0) - fi[tid][42])
    for k in ("Fmidx1", "Fmidx2"):
        if bank[k] == tid:
            bank[k] = -1
            warn.append("звание было надето — снято и со слота")
    if hi:
        high = dict(st["high"])
        _set_bit(high, "BankHi", tid - 256, False)
        _set_bit(high, "ProgHi", tid - 256, True)
        changes.append(("CharFameHigh", [uid, idx], st["high"], high))
    else:
        _set_bit(bank, "Fame", tid, False)
        fr = _row(w, "CharFame", (uid, idx, tid), lock)
        changes.append(("CharFame", [uid, idx, tid], fr, _empty("CharFame")))      # 0/0, опции −1/0 — иначе звание вернётся
        prog = dict(st["prog"]) if st["prog"] else _empty("CharFameProgress")
        _set_bit(prog, "Fame", tid, True)
        changes.append(("CharFameProgress", [uid, idx], st["prog"], prog))
    changes.append(("CharFameBank", [uid, idx], st["bank"], bank))
    text = "снять звание %d «%s» у персонажа %s (%d/%d): слава %s → %s" % (
        tid, title_name(tid), ch["Charname"], uid, idx, st["bank"]["Fmpoint"], bank["Fmpoint"])
    return uid, idx, [c for c in changes if c[2] != c[3]], text, warn


def fame_sum(st, fi):
    """Слава как у сервера при входе (recvDB :127077): Σ очков (кол. 42) по битам 0…255 маски «получено»; биты 256…511 (P22) —
    как после правки P21 (решение владельца 18.11)."""
    s = sum(fi[i][42] for i in range(min(256, len(fi))) if _bit(st["bank"], "Fame", i))
    s += sum(fi[i][42] for i in range(256, len(fi)) if _bit(st["high"], "BankHi", i - 256))
    return s


def plan_recalc(w, p, lock=False, role=None):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры звания")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    fi = _fi()
    ch, st = _load(w, uid, idx, lock)
    if not st["bank"]:
        raise OpRefused("у персонажа нет строки славы (CharFameBank) — её создаёт сервер при входе")
    s = fame_sum(st, fi)
    if s == st["bank"]["Fmpoint"]:
        raise OpRefused("слава уже совпадает с суммой званий (%d)" % s)
    bank = dict(st["bank"], Fmpoint=s)
    text = "пересчитать славу персонажа %s (%d/%d) по полученным званиям: %s → %s" % (ch["Charname"], uid, idx, st["bank"]["Fmpoint"], s)
    return uid, idx, [("CharFameBank", [uid, idx], st["bank"], bank)], text, ["место в рейтинге славы обновится при его пересчёте (раз в сутки или P25)"]


def _put(w, table, key, before, after, stale, stamp=None):
    """Строка «было → стало»: вставка / удаление / обновление только при совпадении «было». stamp — UpdateDate CharFameHigh,
    которое вернуть при откате (перепроверка 20 К6); без него — GETDATE(), как у P22."""
    kc, cols = TABLES[table]
    kw = " AND ".join("%s = ?" % k for k in kc)
    extra, xp = "", []
    if table == "CharFameHigh":
        extra, xp = (", UpdateDate = CONVERT(datetime, ?, 121)", [stamp]) if stamp else (", UpdateDate = GETDATE()", [])
    if before is None and after is None:
        return
    if before is None:
        n = w.execute("INSERT INTO dbo.%s (%s) VALUES (%s)" % (table, ", ".join(list(kc) + cols), ", ".join("?" * (len(kc) + len(cols)))),
                      list(key) + [after[c] for c in cols])
    else:
        cond = " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (c, c) for c in cols)
        cp = [x for c in cols for x in (before[c], before[c])]
        if after is None:
            n = w.execute("DELETE FROM dbo.%s WHERE %s AND %s" % (table, kw, cond), list(key) + cp)
        else:
            ch = [c for c in cols if before[c] != after[c]]
            n = w.execute("UPDATE dbo.%s SET %s%s WHERE %s AND %s" % (table, ", ".join("%s = ?" % c for c in ch), extra, kw, cond),
                          [after[c] for c in ch] + xp + list(key) + cp)
    if n != 1:
        raise OpRefused(stale)


JS_SAFE = 1 << 53


def _js(v):
    """Число, которое браузер не испортит: JSON.parse округляет целые > 2^53 (маски bigint) — такие идут строкой
    (перепроверка 20 В1: из браузера отпечаток с масками не совпадал никогда)."""
    if isinstance(v, bool) or not isinstance(v, int):
        return v
    return str(v) if abs(v) >= JS_SAFE else v


def _sig(changes):
    """Отпечаток для подтверждения: числа — безопасные для JS; значения опций «стало» не входят — их бросает запись
    (перепроверка 20 М1: при ненулевом диапазоне FameInfo бросок при записи иначе не совпадал бы с предпросмотром)."""
    out = []
    for t, k, b, a in changes:
        bb = {c: _js(v) for c, v in b.items()} if b else b
        aa = {c: _js(v) for c, v in a.items() if not c.startswith("Opvalue")} if a else a
        out.append([t, k, bb, aa])
    return out


def _live_title(ctx, p, kind):
    """★ А2.2: игрок в игре на узле v81 → звание выдать/снять или пересчёт славы живьём (функциями сервера); иначе None."""
    if kind == "recalc":
        try:
            uid, idx = int(p["uid"]), int(p["idx"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры звания")
        if uid <= OPERATOR_MAX_UID and ctx.role != "owner":
            raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
        tid = None
    else:
        uid, idx, tid = _plan_args(p, ctx.role)
        fi = _fi()
        if not 0 <= tid < len(fi):
            raise OpRefused("звания %d нет в FameInfo сервера" % tid)
        if tid in RATING:
            raise OpRefused("рейтинговые звания 65–69 выдаёт и снимает сервер (P23) — используйте пересчёт рейтинга P25")
        if kind == "grant" and not fi[tid][1]:
            raise OpRefused("звание %d выключено на сервере — игрой его не получить, клиент его не показывает" % tid)
        if kind == "grant":
            _live_cascade_gate(fi, tid)
    row = bridge.live_row(uid, idx)
    if not row:
        return None
    if kind == "grant":
        # ★ ревизия 25 М-3: тот же отказ по классу, что у офлайн-выдачи (класс в игре не меняется — берём из Charinfo)
        nm = names().get(tid)
        if nm and nm[2]:
            try:
                with db.GameReader("joy1") as r:
                    c = r.one("SELECT Class FROM dbo.Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, idx))
            except db.DbError as ex:
                raise OpRefused("ошибка базы: %s" % ex)
            if c and int(nm[2]) != int(c["Class"] or 0):
                raise OpRefused("звание %d — для другого класса" % tid)
        if tid >= 256:
            return None                       # старшая маска P21/P22: полный путь живьём не воспроизведён — офлайн / «кик + запись»
    if kind == "recalc":
        return {"text": "пересчитать условия званий персонажа %d/%d (%s) живьём — сервер проверит накопители в памяти" % (uid, idx, row["charname"]),
                "expect": {"live": ["fame_recalc"]}, "warnings": [bridge.LIVE_WARN],
                "live": {"op": "fame_recalc", "args": "", "row": row, "uid": uid, "idx": idx}}
    try:
        pr = bridge.probe(row, title=tid, by=ctx.login)
    except bridge.BridgeError:
        return None
    owned = int(pr.get("owned", -1))
    if owned < 0:
        return None
    if kind == "grant" and owned == 0 and int(pr.get("found", -1)) != 1:
        return None                           # ★ ревизия 25 М-3: не «найдено» — бит и 6085/2266 живьём не ставятся: «кик + запись»
    if kind == "grant" and owned == 1:
        raise OpRefused("звание %d у персонажа уже есть (по памяти сервера)" % tid)
    if kind == "revoke" and owned == 0:
        raise OpRefused("звания %d у персонажа нет (по памяти сервера)" % tid)
    return {"text": "%s звание %d персонажу %d/%d (%s) живьём" % ("выдать" if kind == "grant" else "снять", tid, uid, idx, row["charname"]),
            "expect": {"live": [kind, tid]}, "warnings": [bridge.LIVE_WARN],
            "live": {"op": "title_add" if kind == "grant" else "title_del", "args": "id=%d" % tid, "row": row, "uid": uid, "idx": idx,
                     "title": tid}}


def _live_cascade_gate(fi, tid):
    """★ ревизия 38 М-2: P127 title_add сам «включено» не проверяет (pAddFame, p127_admin_bridge.cpp:934) и после выдачи зовёт каскад
    наборов sub_54A610, который тоже не проверяет — выключенное «следующее» игрок получил бы скрытым (снять через 6069 нельзя). Гейт —
    только у панели: отказ живого пути (офлайн-выдача выключенное звание набора не ставит)."""
    nx = hidden_next(fi, tid)
    if nx:
        raise OpRefused("звание %d живьём не выдаётся: каскад наборов сервера (sub_54A610, его зовёт P127 после выдачи) выдал бы и "
                        "выключенное звание %s без проверки «включено» — выдайте, когда игрок не в игре (панель выключенное звание набора "
                        "не выдаёт)" % (tid, ", ".join(map(str, nx))))


def _live_title_apply(ctx, prev):
    lv = prev["live"]
    if lv["op"] == "title_add" and lv.get("title") is not None:
        # ★ ревизия 38 М-2: между предпросмотром и записью звание могли выключить (набор «Званий» выложен) — перечитать FameInfo
        srvtables._cfg.pop("FameInfo.txt", None)
        fi, tid = _fi(), int(lv["title"])
        if not 0 <= tid < len(fi) or not fi[tid][1]:
            raise OpRefused("звание %d выключено на сервере после предпросмотра — живая выдача не делается" % tid)
        _live_cascade_gate(fi, tid)
    try:
        r, text = bridge.live_call(lv["op"], lv["row"], lv["args"], by=ctx.login)
    except bridge.BridgeError as ex:
        raise OpRefused("живьём не выполнено: %s" % ex)
    return {"before": {"uid": lv["uid"], "idx": lv["idx"]},
            "after": {"uid": lv["uid"], "idx": lv["idx"], "live": True, "op": lv["op"], "title": lv.get("title"), "cmd": int(r["id"]),
                      "node": lv["row"]["node"]}, "message": text}


def _live_title_undo(ctx, a):
    """Откат живой правки звания — обратной живой командой, пока игрок в игре на узле v81; пересчёт славы не откатывается."""
    if a.get("op") not in ("title_add", "title_del"):
        raise OpRefused(bridge.LIVE_NO_UNDO)
    row = bridge.live_row(a["uid"], a["idx"])
    if not row:
        raise OpRefused("откат живой правки звания — только пока игрок в игре (мост); сейчас его нет — исправьте новым действием")
    inv = "title_del" if a["op"] == "title_add" else "title_add"
    try:
        r, text = bridge.live_call(inv, row, "id=%d" % int(a["title"]), by=ctx.login)
    except bridge.BridgeError as ex:
        raise OpRefused("откат живьём не выполнен: %s" % ex)
    return {"before": {"uid": a["uid"], "idx": a["idx"], "live": True}, "after": {"uid": a["uid"], "idx": a["idx"], "live": True,
            "op": inv, "cmd": int(r["id"])}, "message": text}


class _TitleOp(Operation):
    reversible = True
    planner = None
    word = "править звания"
    live_kind = None                # ★ А2.2: grant / revoke / recalc

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        if self.live_kind:
            lv = _live_title(ctx, p, self.live_kind)              # ★ А2.2: игрок в игре — живьём
            if lv:
                return lv
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, changes, text, warn = type(self).planner(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        if not changes:
            raise OpRefused("ничего не меняется")
        # опции со случайным значением — отпечаток без значений (их бросок повторится при записи; сейчас у всех званий 0)
        return {"text": text, "expect": _sig(changes), "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        if prev.get("live"):
            return _live_title_apply(ctx, prev)
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры звания")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, changes, text, warn = type(self).planner(w, p, lock=True, role=ctx.role)
            if _sig(changes) != prev["expect"] or ("expect" in p and p["expect"] != _sig(changes)):
                raise OpRefused("пока вы смотрели предпросмотр, звания персонажа изменились — повторите")
            hdate = None
            for t, k, b, a in changes:
                if t == "CharFameHigh" and b is not None and a is not None:
                    hr = w.rows("SELECT CONVERT(varchar(23), UpdateDate, 121) AS d FROM dbo.CharFameHigh WHERE UserIndex = ? AND CharIdx = ?",
                                tuple(k))
                    hdate = hr[0]["d"] if hr else None
                _put(w, t, k, b, a, "звания персонажа изменились при записи — ничего не записано")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx}, "after": {"uid": uid, "idx": idx, "changes": [[t, k, b, a] for t, k, b, a in changes], "hdate": hdate},
                "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        if a.get("live"):
            return _live_title_undo(ctx, a)
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
                _put(w, t, k, af, b, "звания персонажа с тех пор менялись — откат не выполнен",
                     stamp=a.get("hdate") if t == "CharFameHigh" else None)
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"changes": ch}, "after": {"uid": uid}, "message": "звания персонажа %s/%s возвращены" % (uid, a.get("idx")),
                "_commit": w.commit, "_close": w.close}


@register
class TitleGrant(_TitleOp):
    name, title, perm = "title.grant", "Персонаж: выдать звание", "players.titles"
    planner = staticmethod(plan_grant)
    live_kind = "grant"


@register
class TitleRevoke(_TitleOp):
    name, title, perm = "title.revoke", "Персонаж: снять звание", "players.titles"
    planner = staticmethod(plan_revoke)
    live_kind = "revoke"


@register
class FameRecalc(_TitleOp):
    name, title, perm = "fame.recalc", "Персонаж: пересчитать славу", "players.titles"
    planner = staticmethod(plan_recalc)
    live_kind = "recalc"


def plan_honor(w, p, lock=False, role=None):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        v = p["value"]
        if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit())):
            raise ValueError
        v = int(v)
    except (KeyError, TypeError, ValueError):
        raise OpRefused("очки чести — целое число от 0")
    if not 0 <= v <= 2147483647:
        raise OpRefused("очки чести — от 0 до 2 147 483 647")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT c.CampPoint, i.Charname FROM dbo.CharCamp c%s JOIN dbo.Charinfo i ON i.Userindex = c.Userindex AND "
               "i.Charidx = c.Charidx WHERE c.Userindex = ? AND c.Charidx = ?" % hint, (uid, idx))
    if not r:
        raise OpRefused("у персонажа нет фракции (нет строки CharCamp) — очков чести у него нет")
    cur = int(r[0]["CampPoint"] or 0)
    if cur == v:
        raise OpRefused("очки чести уже %d" % v)
    text = "очки чести персонажа %s (%d/%d): %d → %d" % (r[0]["Charname"], uid, idx, cur, v)
    return uid, idx, cur, v, text, ["ступень чести сервер пересчитает при входе персонажа"]


@register
class HonorSet(Operation):
    name, title, perm, reversible = "honor.set", "Персонаж: очки чести", "players.honor", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, cur, v, text, warn = plan_honor(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": [cur, v], "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, cur, v, text, warn = plan_honor(w, p, lock=True, role=ctx.role)
            if [cur, v] != prev["expect"] or ("expect" in p and p["expect"] != [cur, v]):
                raise OpRefused("пока вы смотрели предпросмотр, очки чести изменились — повторите")
            if w.execute("UPDATE dbo.CharCamp SET CampPoint = ? WHERE Userindex = ? AND Charidx = ? AND CampPoint = ?",
                         (v, uid, idx, cur)) != 1:
                raise OpRefused("очки чести изменились при записи — ничего не записано")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "camp": cur}, "after": {"uid": uid, "idx": idx, "camp": v, "old": cur},
                "message": text, "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, a.get("uid"), lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            if w.execute("UPDATE dbo.CharCamp SET CampPoint = ? WHERE Userindex = ? AND Charidx = ? AND CampPoint = ?",
                         (a["old"], a["uid"], a["idx"], a["camp"])) != 1:
                raise OpRefused("очки чести с тех пор менялись — откат не выполнен")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"camp": a.get("camp")}, "after": {"camp": a.get("old")}, "message": "очки чести возвращены",
                "_commit": w.commit, "_close": w.close}


def describe(uid, idx):
    """Звания персонажа для окна панели: все записи FameInfo с состоянием."""
    fi = srvtables.fame_info()
    with db.GameReader("joy1") as r:
        ad = items._ReaderAdapter(r)
        ch, st = _load(ad, int(uid), int(idx), False)
        hold = {int(x["TitleId"]): (int(x["CharId"]), int(x["CharIdx"])) for x in ad.rows(
            "SELECT TitleId, CharId, CharIdx FROM dbo.FameRatingHolder")} if _has_holder(ad) else {}
        camp = ad.rows("SELECT CampPoint, CampGrade FROM dbo.CharCamp WHERE Userindex = ? AND Charidx = ?", (int(uid), int(idx)))
    out = []
    for i, rec in enumerate(fi):
        nm = names().get(i) or ["", "", 0, 0, 0, 0, 0]
        got = _bit(st["high"], "BankHi", i - 256) if i >= 256 else _bit(st["bank"], "Fame", i)
        found = _bit(st["high"], "ProgHi", i - 256) if i >= 256 else _bit(st["prog"], "Fame", i)
        worn = bool(st["bank"]) and i in (st["bank"]["Fmidx1"], st["bank"]["Fmidx2"])
        out.append({"id": i, "name": title_name(i), "points": rec[42], "enabled": bool(rec[1]), "class": nm[2], "group": nm[3],
                    "position": nm[4], "got": got, "found": found, "worn": worn, "rating": i in RATING,
                    "holder": list(hold[i]) if i in hold else None})
    return {"titles": out, "fame": (st["bank"] or {}).get("Fmpoint"), "fame_sum": fame_sum(st, fi) if st["bank"] else None,
            "class": ch["Class"], "camp": camp[0] if camp else None}


def _has_holder(r):
    try:
        r.rows("SELECT TOP 0 TitleId FROM dbo.FameRatingHolder")
        return True
    except db.DbError:
        return False
