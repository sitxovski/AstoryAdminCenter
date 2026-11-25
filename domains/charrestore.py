# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""charrestore.py — восстановить удалённого персонажа (волна А1, план §4.Б «удаление и восстановление»). 18.11.2026.

РАЗБОР — Reports/admin_center/research_char_restore.md (LoginManager sub_40CC50 → Joy1.UPDeleteChar; Del_*; OpCharacterRestore):
  удаление (пакет 1018 → UPDeleteChar) копирует ~20 таблиц в Del_* (ключ набора — Userindex, Charidx, Edate) и стирает без копии
  лагерь, созвездие, друзей, почтовый ящик, баффы наборов и др.; отложенного удаления и чистки корзины нет. Штатная
  OpCharacterRestore без проверок и транзакции и корзину не помечает (повторный вызов = дюп предметов с теми же Uuid).
ЗАПИСЬ — своя процедура Joy1.adm.CharRestore (sql/adminc_05_restore.sql, решение владельца 18.11): вставки штатной процедуры
  в одной транзакции + проверки (набор есть и не восстановлен — adm.CharRestored; у учётки < 3 персонажей — 4-й ломает вход;
  слот 10–12 пуст во всех таблицах вставки; Uuid предметов не в игре) + новое имя. В той же транзакции панель: «учётка не в игре»
  под блокировкой (items.online_state), правило и занятость имени (rename._check_name — A13, как смена имени), строка
  AsdaStoryOp.CharacterStat с НОВЫМ слотом и Seridx 1 (штатная писала старый слот и Seridx без +1 — дефект оригинала).
НЕОБРАТИМО: восстановленный — обычный персонаж; убрать его снова — удалением в игре (новый набор корзины).
Что не вернётся (копии нет) — перечислено в предупреждении LOST. Побочных эффектов при импорте нет.
"""
import datetime
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import charname, items, rename

SLOTS = (10, 11, 12)                      # Charidx персонажей (UPCreateChar; клиент разбирает ровно 3 записи)
MAX_CHARS = 3                             # LoginManager.c:3216 «Character Count Over» при большем числе
OPERATOR_MAX_UID = 5000
EKEY_RX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")
LOST = ("не вернётся (сервер при удалении это стирает без копии): лагерь и его очки, созвездие (будет 1), друзья, почтовый ящик "
        "премиум-покупок, баффы наборов, посещаемость, откаты; соулмейт, если персонаж был последним на учётке")


def _key(p):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
        ekey = str(p["edate"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры восстановления")
    if not EKEY_RX.match(ekey):
        raise OpRefused("неверные параметры восстановления")
    return uid, idx, ekey


def plan(w, p, lock=False, role=None):
    """→ dict(uid, idx, ekey, slot, name|None, row, text, warnings, sig)."""
    uid, idx, ekey = _key(p)
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    # корзина — куча без индексов: без UPDLOCK/HOLDLOCK (держал бы всю таблицу; повтор сериализует adm.CharRestored и учётка —
    # перепроверка 16 М2)
    d = w.rows("SELECT Userindex, Charidx, Uid, Charname, Lvl, Job, CONVERT(varchar(23), Edate, 121) AS ekey FROM dbo.Del_Charinfo "
               "WHERE Userindex = ? AND Charidx = ? AND CONVERT(varchar(23), Edate, 121) = ?", (uid, idx, ekey))
    if not d:
        raise OpRefused("в корзине нет такого персонажа")
    if len(d) > 1:
        raise OpRefused("в корзине два набора с одной датой — панель такой не восстанавливает")
    d = d[0]
    if w.rows("SELECT 1 AS x FROM adm.CharRestored WHERE Userindex = ? AND Charidx = ? AND CONVERT(varchar(23), Edate, 121) = ?",
              (uid, idx, ekey)):
        raise OpRefused("этот персонаж уже восстановлен")
    live = w.rows("SELECT Charidx, Charname FROM dbo.Charinfo%s WHERE Userindex = ?" % hint, (uid,))
    if len(live) >= MAX_CHARS:
        raise OpRefused("у учётки уже %d персонажа — четвёртый сломал бы вход (сервер отдаёт клиенту не больше трёх)" % len(live))
    used = {int(x["Charidx"]) for x in live} | {int(x["Charidx"]) for x in w.rows(
        "SELECT Charidx FROM dbo.CharPos%s WHERE Userindex = ?" % hint, (uid,))}
    free = [s for s in SLOTS if s not in used]
    want = p.get("slot")
    if want in (None, ""):
        slot = idx if idx in free else (free[0] if free else None)
    else:
        try:
            slot = int(want)
        except (TypeError, ValueError):
            raise OpRefused("неверный слот")
    if slot not in free:
        raise OpRefused("слот %s занят или недопустим (свободны: %s)" % (slot, ", ".join(map(str, free)) or "нет"))
    old = str(d["Charname"] or "")
    raw = p.get("name")
    new = raw.strip() if isinstance(raw, str) and raw.strip() and raw.strip() != old else None
    warn = [LOST, "питомцы получат новые номера (как у штатного восстановления); в игре это незаметно"]
    if new is not None:
        # перепроверка 16 М3: своя строка корзины (смена только регистра) — не «двойник»
        why = rename._check_name(w, uid, slot, new, b"", own_deleted=(uid, idx))
        if why:
            raise OpRefused(why)
    else:
        hit = [h for h in w.rows(charname.taken_sql(), (db.to_db_text(old),) * 6) if not h.get("deleted")]   # М5: байты cp1251
        if hit:
            h = hit[0]
            raise OpRefused("имя «%s» теперь носит персонаж учётки %s (слот %s) — восстановите под новым именем"
                            % (old, h["Userindex"], h["Charidx"]))
    if slot != idx:
        warn.append("персонаж вернётся в слот %d (его слот %d занят)" % (slot, idx))
    name = new or old
    text = "восстановить персонажа %s (учётка %d, удалён %s) в слот %d%s" % (
        old, uid, ekey[:16], slot, (" под именем %s" % new) if new else "")
    sig = {"ekey": ekey, "slot": slot, "name": name, "live": sorted(int(x["Charidx"]) for x in live)}
    return {"uid": uid, "idx": idx, "ekey": ekey, "slot": slot, "new": new, "name": name, "row": d, "text": text,
            "warnings": warn, "sig": sig}


def _slot_leftovers(uid, slot):
    """Строки, которые удаление не трогает и которые достанутся персонажу в этом слоте (research §1.2)."""
    out = []
    with db.GameReader("joy1") as r:
        for t in ("CharRefine", "CharGmInfo", "CharFameHigh"):
            try:
                n = r.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE Userindex = ? AND Charidx = ?" % t, (uid, slot))["n"]
            except db.DbError:
                continue
            if n:
                out.append("%s: %d" % (t, n))
    return out


def _create_time(uid, idx, name):
    with db.GameReader("joylog1") as r:
        x = r.one("SELECT TOP 1 Edate FROM dbo.CharEventCreate WHERE Userindex = ? AND Charidx = ? AND Charname = ? ORDER BY Edate DESC",
                  (uid, idx, db.to_db_text(name)))
    return x["Edate"] if x else None


class _Adapter:
    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)


@register
class CharRestore(Operation):
    name, title, perm, reversible = "char.restore", "Персонаж: восстановить удалённого", "players.restore", False

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = _Adapter(r)
                pl = plan(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, pl["uid"])
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("восстанавливать можно только когда игрок не в игре: " + why)
        left = _slot_leftovers(pl["uid"], pl["slot"])
        warn = list(pl["warnings"])
        if left:
            warn.append("в слоте %d остались строки прежнего владельца слота — достанутся восстановленному: %s"
                        % (pl["slot"], ", ".join(left)))
        return {"text": pl["text"], "expect": pl["sig"], "warnings": warn, "slot": pl["slot"]}

    def apply(self, ctx, p, prev):
        try:
            uid0, idx0, _e = _key(p)
        except OpRefused:
            raise
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid0, lock=True)              # порядок блокировок как у входа в игру
            if not ok:
                raise OpRefused("восстанавливать можно только когда игрок не в игре: " + why)
            pl = plan(w, dict(p, slot=prev["expect"]["slot"]), lock=True, role=ctx.role)
            if pl["sig"] != prev["expect"] or ("expect" in p and p["expect"] != pl["sig"]):
                raise OpRefused("пока вы смотрели предпросмотр, учётка или корзина изменились — повторите")
            e = pl["ekey"].replace(" ", "T")                               # ISO 8601 — без зависимости от языка логина
            try:
                w.rows("EXEC adm.CharRestore ?, ?, ?, ?, ?, ?",
                       (pl["uid"], pl["idx"], e, pl["slot"], pl["new"], ("panel:%s" % (ctx.login or ""))[:64]))
            except db.DbError as ex:
                m = re.search(r"adm\.CharRestore: ([^\[\]]+?)(?: \(\d+\))?$", str(ex))
                raise OpRefused(("отказ сервера: " + m.group(1)) if m else "ошибка базы: %s" % ex)
            if pl["uid"] > OPERATOR_MAX_UID and not w.rows(
                    "SELECT 1 AS x FROM AsdaStoryOp.dbo.CharacterStat WHERE Userindex = ? AND Charidx = ?", (pl["uid"], pl["slot"])):
                ct = _create_time(pl["uid"], pl["idx"], pl["row"]["Charname"]) or datetime.datetime.now()
                w.execute("INSERT INTO AsdaStoryOp.dbo.CharacterStat (Userindex, Charidx, Us_id, Charname, Seridx, Create_time) "
                          "VALUES (?, ?, ?, ?, 1, ?)", (pl["uid"], pl["slot"], db.to_db_text(pl["row"]["Uid"]), db.to_db_text(pl["name"]), ct))
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": pl["uid"], "idx": pl["idx"], "edate": pl["ekey"]},
                "after": {"uid": pl["uid"], "slot": pl["slot"], "name": pl["name"]},
                "message": pl["text"], "_commit": w.commit, "_close": w.close}
