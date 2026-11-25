# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""charcopy.py — копия персонажа на служебную учётку (волна А1, §4.Б «копия»; решение владельца 18.11). 18.11.2026.

РАЗБОР — Reports/admin_center/research_a1_char_rest.md §7. ЗАПИСЬ — своя процедура Joy1.adm.CharCopy (sql/adminc_08_charcopy.sql,
по образцу adm.CharRestore): одна транзакция; состав — UPDeleteChar + CharRefine + CharFameHigh (33 таблицы); без связей с другими
игроками и деньгами; каждому предмету новый Uuid (и Uc1…4), карта «старый → новый» — adm.CharCopyItemMap; JoyLog1 не пишется.
В той же транзакции панель: обе учётки (источник и цель) не в игре под блокировкой (items.online_state — «кик + запись» моста P127),
цель — служебная учётка ≤ 5000, у неё < 3 персонажей и свободный слот 10–12, новое имя по правилам смены имени (rename._check_name, A13).
ОТКАТ — удаление копии (adm.CharCopyDelete по отметке adm.CharCopied): только служебная учётка, слот всё ещё с этим именем, у копии нет
друзей, клана, лотов и почты. Побочных эффектов при импорте нет.
"""
import json
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import charrestore, items, rename

SLOTS = (10, 11, 12)
MAX_CHARS = 3
OPERATOR_MAX_UID = 5000
# строки слота, которые копия не пишет (остались от прежнего владельца слота — достанутся копии); ★ ревизия 26 С-1: всё, что UPDeleteChar
# стирает у слота и копия не пишет, + GM-флаг слота
_UC = "Userindex = ? AND Charidx = ?"
LEFTOVER = (("CharGmInfo", _UC), ("ItemPostBox", _UC), ("AttendanceCount", _UC), ("AttendanceDetail", _UC), ("CharFriend", _UC),
            ("ClanMember", _UC), ("CharinPos", _UC), ("CharIntroduce", _UC), ("FamePointRank", _UC), ("Exitem", _UC),
            ("SoulJewel", "Userindex1 = ? AND Charidx1 = ?"), ("SellitemAlarm", "BUserindex = ? AND Bcharidx = ?"))
REPLACED = ("CharRefine", "CharFameHigh")       # UPDeleteChar их не удаляет — копия заменяет остаток прежнего владельца слота
NOT_COPIED = ("не копируются (связи с другими игроками и деньгами): друзья, клан, соулмейт, камни душ, почтовый ящик, аукцион, "
              "посещаемость, место в рейтинге, «о себе», GM-флаг слота")


def _args(p):
    try:
        uid, idx, to = int(p["uid"]), int(p["idx"]), int(p["to"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры копии")
    return uid, idx, to


def plan(w, p, lock=False, role=None):
    """→ dict(uid, idx, to, slot, name, text, warnings, sig)."""
    uid, idx, to = _args(p)
    if role != "owner":
        raise OpRefused("копию персонажа делает только владелец")
    if not 1 <= to <= OPERATOR_MAX_UID:
        raise OpRefused("копировать можно только на служебную учётку (номер до %d)" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    src = w.rows("SELECT Charname, Lvl FROM dbo.Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, idx))
    if not src:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    if not w.rows("SELECT Userindex FROM AsdaStoryOp.dbo.Us_member WHERE Userindex = ?", (to,)):
        raise OpRefused("учётки %d нет" % to)
    live = w.rows("SELECT Charidx, Charname FROM dbo.Charinfo%s WHERE Userindex = ?" % hint, (to,))
    if len(live) >= MAX_CHARS:
        raise OpRefused("у учётки %d уже %d персонажа — четвёртый сломал бы вход (сервер отдаёт клиенту не больше трёх)" % (to, len(live)))
    used = {int(x["Charidx"]) for x in live} | {int(x["Charidx"]) for x in w.rows("SELECT Charidx FROM dbo.CharPos%s WHERE Userindex = ?" % hint, (to,))}
    free = [s for s in SLOTS if s not in used]
    want = p.get("slot")
    if want in (None, ""):
        slot = free[0] if free else None
    else:
        try:
            slot = int(want)
        except (TypeError, ValueError):
            raise OpRefused("неверный слот")
    if slot not in free:
        raise OpRefused("слот %s занят или недопустим (свободны: %s)" % (slot, ", ".join(map(str, free)) or "нет"))
    raw = p.get("name")
    name = raw.strip() if isinstance(raw, str) else ""
    if not name:
        raise OpRefused("у копии должно быть новое имя")
    why = rename._check_name(w, to, slot, name, b"")
    if why:
        raise OpRefused(why)
    n_items = w.rows("SELECT COUNT(*) AS n FROM dbo.Item WHERE Userindex = ? AND Charidx = ?", (uid, idx))[0]["n"]
    camp = w.rows("SELECT TOP 1 Campidx FROM dbo.CharCamp WHERE Userindex = ? AND Campidx <> -1 ORDER BY Charidx", (to,))
    text = "копия персонажа %s (%d/%d, ур. %s) → учётка %d, слот %d, имя %s: предметов %d" % (
        src[0]["Charname"], uid, idx, src[0]["Lvl"], to, slot, name, int(n_items))
    warn = [NOT_COPIED, "каждому предмету — новый номер (Uuid), соответствие хранится в журнале копий; в журналы игры копия не пишется",
            "питомцы получат новые номера (как у восстановления)",
            "армия копии — армия учётки %d (%s), как сервер ставит армию всем персонажам учётки" % (to, camp[0]["Campidx"]) if camp else "у учётки %d нет армии — копия будет без армии (очки чести сохранятся)" % to]
    if uid > OPERATOR_MAX_UID:
        warn.append("источник — персонаж игрока: он не меняется, копия — на служебной учётке")
    sig = {"to": to, "slot": slot, "name": name, "live": sorted(int(x["Charidx"]) for x in live), "items": int(n_items)}
    return {"uid": uid, "idx": idx, "to": to, "slot": slot, "name": name, "src": src[0]["Charname"], "text": text, "warnings": warn, "sig": sig}


def _leftovers(to, slot, tables=LEFTOVER):
    out = []
    with db.GameReader("joy1") as r:
        for x in tables:
            t, where = x if isinstance(x, tuple) else (x, _UC)
            try:
                n = r.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE %s" % (t, where), (to, slot))["n"]
            except db.DbError:
                continue
            if n:
                out.append("%s: %d" % (t, n))
    return out


def _refuse_db(ex, proc):
    m = re.search(proc.replace(".", r"\.") + r": ([^\[\]]+?)(?: \(\d+\))?$", str(ex))
    return OpRefused(("отказ сервера: " + m.group(1)) if m else "ошибка базы: %s" % ex)


@register
class CharCopy(Operation):
    name, title, perm, reversible = "char.copy", "Персонаж: копия на служебную учётку", "players.copy", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = charrestore._Adapter(r)
                pl = plan(ad, p, role=ctx.role)
                for u in sorted({pl["uid"], pl["to"]}):
                    ok, why = items.online_state(ad, u)
                    if not ok:
                        raise OpRefused("копировать можно только когда обе учётки не в игре: учётка %d — %s" % (u, why))
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        warn = list(pl["warnings"])
        left = _leftovers(pl["to"], pl["slot"])
        if left:
            warn.append("в слоте %d остались строки прежнего владельца слота — достанутся копии: %s" % (pl["slot"], ", ".join(left)))
        rep = _leftovers(pl["to"], pl["slot"], REPLACED)
        if rep:
            warn.append("в слоте %d остались строки удалённого персонажа (сервер их не стирает) — копия их заменит, снимок сохраняется, удаление "
                        "копии их вернёт: %s" % (pl["slot"], ", ".join(rep)))
        if any(items.recently_left(u) for u in {pl["uid"], pl["to"]}):
            warn.append(items.RECENT_WARN)
        return {"text": pl["text"], "expect": pl["sig"], "warnings": warn, "slot": pl["slot"]}

    def apply(self, ctx, p, prev):
        uid0, _i, to0 = _args(p)
        w = db.GameWriter("joy1")
        try:
            for u in sorted({uid0, to0}):                                   # порядок блокировок — по номеру учётки
                ok, why = items.online_state(w, u, lock=True)
                if not ok:
                    raise OpRefused("копировать можно только когда обе учётки не в игре: учётка %d — %s" % (u, why))
            pl = plan(w, dict(p, slot=prev["expect"]["slot"]), lock=True, role=ctx.role)
            if pl["sig"] != prev["expect"] or ("expect" in p and p["expect"] != pl["sig"]):
                raise OpRefused("пока вы смотрели предпросмотр, учётка-цель или персонаж изменились — повторите")
            try:
                r = w.rows("EXEC adm.CharCopy ?, ?, ?, ?, ?, ?", (pl["uid"], pl["idx"], pl["to"], pl["slot"], pl["name"],
                                                                  ("panel:%s" % (ctx.login or ""))[:64]))
            except db.DbError as ex:
                raise _refuse_db(ex, "adm.CharCopy")
            if not r:
                raise OpRefused("процедура копии не ответила — ничего не записано")
            cid, n = int(r[0]["CopyId"]), int(r[0]["Items"])
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": pl["uid"], "idx": pl["idx"]},
                "after": {"copy": cid, "to": pl["to"], "slot": pl["slot"], "name": pl["name"], "items": n},
                "message": pl["text"] + " (копия №%d)" % cid, "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        cid, to = a.get("copy"), a.get("to")
        if not cid or not to:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, int(to), lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            try:
                w.rows("EXEC adm.CharCopyDelete ?, ?", (int(cid), ("panel:%s" % (ctx.login or ""))[:64]))
            except db.DbError as ex:
                raise _refuse_db(ex, "adm.CharCopyDelete")
        except BaseException:
            w.close()
            raise
        return {"before": {"copy": cid, "to": to, "slot": a.get("slot")}, "after": {"deleted": cid},
                "message": "копия №%s удалена (учётка %s, слот %s)" % (cid, to, a.get("slot")), "_commit": w.commit, "_close": w.close}


def targets():
    """Служебные учётки (≤ 5000) со свободными слотами — для окна копии."""
    with db.GameReader("joy1") as r:
        rows = r.rows("SELECT Userindex, Charidx, Charname FROM dbo.Charinfo WHERE Userindex <= ? ORDER BY Userindex, Charidx", (OPERATOR_MAX_UID,))
    with db.GameReader("asdastoryop") as r:
        accs = [int(x["Userindex"]) for x in r.rows("SELECT Userindex FROM dbo.Us_member WHERE Userindex <= ? ORDER BY Userindex", (OPERATOR_MAX_UID,))]
    out = []
    for u in accs:
        cs = [x for x in rows if int(x["Userindex"]) == u]
        used = {int(x["Charidx"]) for x in cs}
        out.append({"uid": u, "chars": [{"idx": x["Charidx"], "name": x["Charname"]} for x in cs], "free": [s for s in SLOTS if s not in used]
                    if len(cs) < MAX_CHARS else []})
    return {"targets": out}
