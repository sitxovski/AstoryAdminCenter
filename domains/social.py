# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""social.py — общий каркас операций «соулмейт, друзья, клан» (волна А1, план §4.Б). 18.11.2026.

ЗАЧЕМ ОТДЕЛЬНО. Три раздела (domains/soulmate.py, friends.py, clan.py) пишут строки без первичного ключа (SoulMate, CharFriend),
целые наборы строк (роспуск клана) и строки с текстом в кодировке игровой базы (имена, объявления). Каркас один:
  * строка = dict столбец → значение; числа — int, текст — ШЕСТНАДЦАТЕРИЧНЫЕ байты столбца (CONVERT(varbinary, 2): сравнение и
    возврат байт в байт, без перекодировки Arabic/cp1251 — как rename.py хранит старое имя), дата — строка стиля 121;
  * изменение = [таблица, было, стало]: было None — вставка, стало None — удаление, иначе обновление ИЗМЕНЁННЫХ столбцов при
    условии «строка всё ещё как было» (иначе отказ «изменилось при записи»); значение «NOW» — GETDATE() сервера, IDENTITY —
    номер выдаёт база (OUTPUT); после записи «стало» перечитывается — журнал панели хранит то, что реально записано;
  * откат = те же изменения в обратном порядке (стало → было) с той же сверкой.
Проверка «не в игре» — в КАЖДОМ разделе своя функция _require_offline (решение владельца 18.11: туда же позже подключится
онлайн-путь через мост AdminBridge, волна А2); здесь — только общий примитив offline().
Побочных эффектов при импорте нет.
"""
import json

from core import db
from core.ops import Operation, OpRefused
from domains import items, itemgive

# таблица → (ключ, [(столбец, вид)]); вид: i — целое, s<N> — varchar(N), d — datetime, sd — smalldatetime; IDENTITY — отдельно
TABLES = {
    "SoulMate": (("Smidx", "Userindex"), [("Ouserindex", "i"), ("info", "i"), ("State", "i"), ("SmLvl", "i"), ("SmExp", "i"),
                                          ("FriendShip", "i"), ("AppleRate", "i"), ("AppleValue", "i"), ("FinalDate", "d"),
                                          ("Regdate", "d")]),
    "Charinfo": (("Userindex", "Charidx"), [("Share", "i")]),
    "CharFriend": (("Userindex", "Charidx", "Fuserindex", "Fcharidx"), [("Charname", "s20")]),
    "ClanData": (("Clanidx",), [("Cname", "s17"), ("Ctype", "i"), ("Captain", "s20"), ("Capuserindex", "i"), ("CapCharidx", "i"),
                                ("Maxcnt", "i"), ("JoinCnt", "i"), ("Maxgrade", "i"), ("State", "i"), ("Lvl", "i"), ("TotActPoint", "i"),
                                ("UseActPoint", "i"), ("Authority1", "i"), ("Authority2", "i"), ("Authority3", "i"), ("Authority4", "i"),
                                ("MarkFlag", "i"), ("Markidx", "i"), ("MarkColor", "i"), ("MarkBorder", "i"), ("MarkBdColor", "i"),
                                ("MarkBgColor", "i"), ("Mapidx", "i"), ("Aidx1", "i"), ("Aname1", "s17"), ("Amark1", "i"),
                                ("Aidx2", "i"), ("Aname2", "s17"), ("Amark2", "i"), ("Aidx3", "i"), ("Aname3", "s17"), ("Amark3", "i"),
                                ("Waridx", "i"), ("Warname", "s17"), ("Warmark", "i"), ("Notice", "s256")]),
    "ClanMember": (("Clanidx", "Userindex", "Charidx"), [("Cname", "s17"), ("Charname", "s20"), ("Grade", "i"), ("DonationPoint", "i"),
                                                        ("Callname", "s9"), ("Memo", "s64")]),
    "ClanNotice": (("Clanidx", "idx"), [("Charname", "s20"), ("Edate", "sd"), ("Notice", "s500")]),
    "CampClanData": (("CampType", "ClanIndex"), [("EnterPoint0", "i"), ("EnterPoint1", "i"), ("EnterPoint2", "i")]),
    "CampOwnerData": (("CampType",), [("MvpClanIndex", "i")]),
}
IDENTITY = {"ClanNotice": "idx"}          # номер строки выдаёт база (IDENTITY_INSERT требует ALTER — у asda_ops его нет)
NOW = "NOW"
NEW = "NEW"


def _kind(table, col):
    keys, cols = TABLES[table]
    return "i" if col in keys else dict(cols)[col]


def _rd(col, kind):
    """Выражение чтения столбца в каноническом виде."""
    if kind.startswith("s") and kind != "sd":
        return "CONVERT(varchar(1100), CAST(%s AS varbinary(%s)), 2)" % (col, kind[1:])
    if kind in ("d", "sd"):
        return "CONVERT(varchar(23), %s, 121)" % col
    return col


def _wr(kind):
    """Выражение записи параметра."""
    if kind.startswith("s") and kind != "sd":
        return "CONVERT(varchar(%s), CONVERT(varbinary(%s), ?, 2))" % (kind[1:], kind[1:])
    if kind == "d":
        return "CONVERT(datetime, ?, 121)"
    if kind == "sd":
        return "CONVERT(smalldatetime, ?, 121)"
    return "?"


def select_list(table, alias=""):
    keys, cols = TABLES[table]
    a = alias + "." if alias else ""
    return ", ".join("%s AS %s" % (_rd(a + c, _kind(table, c)), c) for c in list(keys) + [c for c, _k in cols])


def read(w, table, where, params=(), lock=False, alias=""):
    """Строки таблицы в каноническом виде (текст — hex заглавными, дата — стиль 121)."""
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    rows = w.rows("SELECT %s FROM dbo.%s%s%s WHERE %s" % (select_list(table, alias), table, (" " + alias) if alias else "", hint, where),
                  params)
    out = []
    for r in rows:
        d = {}
        for c in r:
            v = r[c]
            d[c] = int(v) if isinstance(v, (int, bool)) or (v is not None and _kind(table, c) == "i") else v
        out.append(d)
    return out


TEXT_MSG = {    # поле → (пусто, не та кодировка, длиннее %d байт) — готовые тексты, чтобы у каждого был шаблон EN
    "notice": ("текст объявления пуст", "в тексте объявления есть знаки, которых нет в кодировке игры (cp1251)", "текст объявления длиннее %d байт"),
    "author": ("автор объявления не указан", "в имени автора объявления есть знаки, которых нет в кодировке игры (cp1251)",
               "имя автора объявления длиннее %d байт"),
}


def text_hex(s, nbytes, what):
    """Текст оператора → hex байт игры (cp1251, как видит клиент); пусто / непредставимо / длиннее поля — отказ."""
    m = TEXT_MSG[what]
    s = (s or "").strip()
    if not s:
        raise OpRefused(m[0])
    try:
        b = s.encode("cp1251")
    except UnicodeEncodeError:
        raise OpRefused(m[1])
    if len(b) > nbytes:
        raise OpRefused(m[2] % nbytes)
    return b.hex().upper()


def hex_text(h):
    """hex байт игры → строка для показа (как fix_text)."""
    if h is None:
        return None
    try:
        return bytes.fromhex(h).decode("cp1251", "replace")
    except ValueError:
        return h


def _cond(table, row):
    keys, cols = TABLES[table]
    parts, params = [], []
    for c in list(keys) + [c for c, _k in cols]:
        if c == IDENTITY.get(table) and row.get(c) in (None, NEW):
            continue
        parts.append("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (_rd(c, _kind(table, c)), c))
        params += [row[c], row[c]]
    return " AND ".join(parts), params


def _keyw(table, row):
    keys = TABLES[table][0]
    return " AND ".join("%s = ?" % k for k in keys), [row[k] for k in keys]


def put(w, table, before, after, stale):
    """Записать одно изменение «было → стало» → «стало» как записано (NOW и IDENTITY — из базы). Не та строка — OpRefused(stale)."""
    if table not in TABLES:
        raise OpRefused("в журнале неожиданная таблица — откат не выполнен")
    if before is None and after is None:
        return None
    keys, cols = TABLES[table]
    allc = list(keys) + [c for c, _k in cols]
    ident = IDENTITY.get(table)
    if before is None:
        ins = [c for c in allc if c in after and c != ident]
        vals, params = [], []
        for c in ins:
            if after[c] == NOW:
                vals.append("GETDATE()")
            else:
                vals.append(_wr(_kind(table, c)))
                params.append(after[c])
        out = " OUTPUT inserted.%s AS ident" % ident if ident else ""
        r = w.rows("INSERT INTO dbo.%s (%s)%s VALUES (%s)" % (table, ", ".join(ins), out, ", ".join(vals)), params) if ident else None
        if not ident:
            n = w.execute("INSERT INTO dbo.%s (%s) VALUES (%s)" % (table, ", ".join(ins), ", ".join(vals)), params)
            if n != 1:
                raise OpRefused(stale)
        elif not r:
            raise OpRefused(stale)
        after = dict(after)
        if ident:
            after[ident] = int(r[0]["ident"])
    elif after is None:
        cw, cp = _cond(table, before)
        if w.execute("DELETE FROM dbo.%s WHERE %s" % (table, cw), cp) != 1:
            raise OpRefused(stale)
        return None
    else:
        ch = [c for c in after if c not in keys and after[c] != before.get(c)]
        if not ch:
            return after
        sets, params = [], []
        for c in ch:
            if after[c] == NOW:
                sets.append("%s = GETDATE()" % c)
            else:
                sets.append("%s = %s" % (c, _wr(_kind(table, c))))
                params.append(after[c])
        cw, cp = _cond(table, before)
        if w.execute("UPDATE dbo.%s SET %s WHERE %s" % (table, ", ".join(sets), cw), params + cp) != 1:
            raise OpRefused(stale)
    kw, kp = _keyw(table, after)
    got = read(w, table, kw, kp)
    if len(got) != 1:
        raise OpRefused(stale)
    return {c: got[0][c] for c in after}


def js(v):
    """Число, которое браузер не испортит (целые ≥ 2^53 — строкой, как titles._js)."""
    if isinstance(v, bool) or not isinstance(v, int):
        return v
    return str(v) if abs(v) >= 1 << 53 else v


def sig(changes, extra=()):
    """Отпечаток плана для подтверждения: списки (кортежи JSON браузера не переживают), числа — безопасные для JS."""
    jd = lambda d: None if d is None else {k: js(v) for k, v in sorted(d.items())}
    return [[t, jd(b), jd(a)] for t, b, a in changes] + [list(x) for x in extra]


def offline(w, uids, lock, refuse):
    """Все учётки uids не в игре (items.online_state; под блокировкой — в порядке номеров, чтобы два оператора не сцепились).
    refuse(uid, why) → текст отказа."""
    for u in sorted({int(x) for x in uids}):
        ok, why = items.online_state(w, u, lock=lock)
        if not ok:
            raise OpRefused(refuse(u, why))


def in_world(w, uid, idx=None):
    """Персонаж (или любая строка учётки) в игре по CharPos — для предупреждений, без блокировки."""
    if idx is None:
        return bool(w.rows("SELECT TOP 1 1 AS x FROM dbo.CharPos WHERE Userindex = ? AND UserNum <> -1", (uid,)))
    return bool(w.rows("SELECT TOP 1 1 AS x FROM dbo.CharPos WHERE Userindex = ? AND Charidx = ? AND UserNum <> -1", (uid, idx)))


def log(w, table, cols, values):
    """Строка стокового журнала JoyLog1 (asda_ops: только INSERT нужных таблиц; межбазовые цепочки выключены — право вызывающего).
    values: число, None, («hex», hex, N) — байты varchar(N), «NOW» — GETDATE()."""
    vals, params = [], []
    for v in values:
        if v == NOW:
            vals.append("GETDATE()")
        elif isinstance(v, (list, tuple)) and v and v[0] == "hex":
            vals.append("CONVERT(varchar(%d), CONVERT(varbinary(%d), ?, 2))" % (v[2], v[2]))
            params.append(v[1])
        else:
            vals.append("?")
            params.append(v)
    w.execute("INSERT INTO JoyLog1.dbo.%s (%s) VALUES (%s)" % (table, ", ".join(cols), ", ".join(vals)), params)


STALE_W = "строки изменились при записи — ничего не записано"
STALE_U = "строки с тех пор менялись — откат не выполнен"
CHANGED = "пока вы смотрели предпросмотр, данные изменились — повторите"


def take_crystal(w, pl, login):
    """Удалить строку предмета как изъятие панели (EXEC adm.ItemTake: снимок строки, журнал adm.ItemLedger и JoyLog1.AdminitemLog,
    откат — adm.ItemUndo) → номер записи журнала предметов."""
    sg = pl["sig"]
    try:
        r = w.rows("EXEC adm.ItemTake ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                   (pl["uid"], pl["idx"], pl["plate"], pl["posx"], pl["code"], sg["uuid"], sg["amount"], sg["fdate"], None, 0,
                    ("panel:%s" % (login or ""))[:64]))
    except db.DbError as ex:
        raise itemgive._refuse_db(ex, "adm.ItemTake")
    if not r:
        raise OpRefused("процедура изъятия не ответила — ничего не записано")
    return int(r[0]["LedgerId"])


def untake(w, ledger, login):
    """Откат изъятий по журналу предметов (в ту же ячейку; занята — в первую свободную той же сумки, как items.take)."""
    oper = ("panel:%s" % (login or ""))[:64]
    for lid in reversed(ledger or []):
        led = w.rows("SELECT Userindex, Charidx, Plate, Kind, WeightBefore, WeightAfter FROM adm.ItemLedger WHERE Id = ?", (lid,))
        if not led:
            raise OpRefused("записи %s нет в журнале предметов" % lid)
        u0, i0 = int(led[0]["Userindex"]), int(led[0]["Charidx"])
        caps = items._load(w, u0, i0, lock=True)[2]
        k = led[0]["Kind"]
        if k in ("take", "takepart") and int(led[0]["Plate"]) != 5:     # перепроверка 23 М1: вес — как itemgive._undo_ledger
            cur_w, max_w = itemgive._weights(w, u0, i0, True)
            wt = int(led[0]["WeightBefore"] or 0) - (int(led[0]["WeightAfter"] or 0) if k == "takepart" else 0)
            if cur_w + wt >= max_w or cur_w + wt > itemgive.WEIGHT_MAX:
                raise OpRefused("перегруз: вернуть предмет нельзя (вес %d + %d ≥ %d)" % (cur_w, wt, max_w))
        try:
            w.rows("EXEC adm.ItemUndo ?, ?, ?", (lid, caps.get(int(led[0]["Plate"]), 0), oper))
        except db.DbError as ex:
            raise itemgive._refuse_db(ex, "adm.ItemUndo")


class SocialOp(Operation):
    """Каркас операции раздела: planner(w, p, lock, role) → план dict(uids, changes [[таблица, было, стало]], takes, logs, ulogs,
    text, warn); require_offline(w, uids, lock) — проверка «не в игре» раздела (одна функция на раздел — сюда подключится мост А2);
    undo_check(w, after) — что ещё проверить перед откатом; undo_uids(w, after) — чьи учётки держать при откате."""
    reversible = True
    planner = None
    require_offline = None
    undo_offline = None
    undo_check = None
    undo_uids = None

    def target(self, p):
        return ""

    def _plan(self, w, p, lock, role):
        pl = type(self).planner(w, p, lock=lock, role=role)
        pl.setdefault("takes", [])
        pl.setdefault("logs", [])
        pl.setdefault("ulogs", [])
        pl.setdefault("warn", [])
        return pl

    @staticmethod
    def _sig(pl):
        return sig(pl["changes"], [["take", t["sig"]] for t in pl["takes"]])

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                pl = self._plan(ad, p, False, ctx.role)
                type(self).require_offline(ad, pl["uids"], False)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not pl["changes"] and not pl["takes"]:
            raise OpRefused("ничего не меняется")
        warn = list(pl["warn"])
        if any(items.recently_left(u) for u in sorted(set(pl["uids"]))):
            warn.append(items.RECENT_WARN)
        return {"text": pl["text"], "expect": self._sig(pl), "warnings": warn}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            pre = self._plan(w, p, False, ctx.role)                 # чьи учётки держать — по данным без блокировки
            type(self).require_offline(w, pre["uids"], True)        # сначала учётки (порядок входа в игру), потом строки
            pl = self._plan(w, p, True, ctx.role)
            sg = self._sig(pl)
            if sorted(set(pl["uids"])) != sorted(set(pre["uids"])) or sg != prev["expect"] or ("expect" in p and p["expect"] != sg):
                raise OpRefused(CHANGED)
            done = []
            for t, b, a in pl["changes"]:
                done.append([t, b, put(w, t, b, a, STALE_W)])
            ledger = [take_crystal(w, t, ctx.login) for t in pl["takes"]]
            for lg in pl["logs"]:
                log(w, *lg)
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"params": {k: v for k, v in p.items() if k != "expect"}},
                "after": {"uids": sorted(set(pl["uids"])), "changes": done, "ledger": ledger, "ulogs": pl["ulogs"]},
                "message": pl["text"], "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        ch = a.get("changes")
        if not ch and not a.get("ledger"):
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            uids = type(self).undo_uids(w, a) if type(self).undo_uids else a.get("uids") or []
            type(self).undo_offline(w, uids, True)
            if type(self).undo_check:
                type(self).undo_check(w, a)
            for t, b, af in reversed(ch or []):
                put(w, t, af, b, STALE_U)
            untake(w, a.get("ledger"), ctx.login)
            for lg in a.get("ulogs") or []:
                log(w, *lg)
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"changes": ch}, "after": {"uids": a.get("uids")}, "message": "%s: возвращено" % self.title,
                "_commit": w.commit, "_close": w.close}
