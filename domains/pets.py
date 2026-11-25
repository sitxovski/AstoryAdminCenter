# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""pets.py — питомцы персонажа НЕ В ИГРЕ: кличка, уровень, удаление (волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_skills_pets.md (C). РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11: уровень — НЕ выше PetMaxLvl (потолок снимает
платный предмет — панель его не обходит); журналы JoyLog1 (PetDelEvent, PetLevelUp) не пишутся — только журнал панели.
CharPetList: PetUnique (IDENTITY), Petindex (порода), PetName varchar(16) (поле клиента — 14), FullNess, PetLvl, PetMaxLvl, PetExp
  (накопительный; в памяти GS — WORD), NameFlag, Active. Больше 30 строк — сервер при входе отбрасывает весь список.
  pet.rename — как UPPetRename: 1…14 знаков A–Z a–z 0–9 - _ (наш фильтр процедуры 21.10), слово не из LewdWordList, NameFlag = 0;
  pet.level  — PetLvl = L (1 … PetMaxLvl), PetExp = E(L) = int(PetExp_Table[L] × PetInfo[порода].кол5 / 10) — начало уровня
               (sub_456D90 :35255); звание 224 за уровень не выдаётся (как и у уровня персонажа);
  pet.delete — как UPCharPetDel: строка удаляется; снимок — в журнале панели; откат вставляет питомца заново — с НОВЫМ PetUnique
               (IDENTITY_INSERT требует ALTER, у asda_ops его нет; ссылок на PetUnique вне журналов нет — разбор C.1).
ЗАПИСЬ — asda_ops, одна транзакция, «не в игре» под блокировкой; откат — если строка с тех пор не менялась. Побочных эффектов нет.
"""
import json
import re

from core import db
from core.ops import Operation, OpRefused, register
from domains import items, refdata, srvtables

COLS = ("Plate", "Petindex", "PetName", "FullNess", "PetLvl", "PetMaxLvl", "PetExp", "NameFlag", "Active")
NAME_RX = re.compile(r"[A-Za-z0-9_-]{1,14}")
MAX_PETS = 30
PET_LVL_MAX = 10
OPERATOR_MAX_UID = 5000


def _args(p, role):
    try:
        uid, idx, pet = int(p["uid"]), int(p["idx"]), int(p["pet"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры питомца")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    return uid, idx, pet


def _row(w, uid, idx, pet, lock):
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT p.%s, c.Charname FROM dbo.CharPetList p%s JOIN dbo.Charinfo c ON c.Userindex = p.Userindex AND c.Charidx = p.Charidx "
               "WHERE p.Userindex = ? AND p.Charidx = ? AND p.PetUnique = ?" % (", p.".join(COLS), hint), (uid, idx, pet))
    if not r:
        raise OpRefused("питомца %d у персонажа нет" % pet)
    r = r[0]
    return {c: r[c] for c in COLS}, r["Charname"]


def _breed(i):
    return refdata.pet(i) or "порода %s" % i


def plan_rename(w, p, lock=False, role=None):
    uid, idx, pet = _args(p, role)
    name = str(p.get("name") or "").strip()
    if not NAME_RX.fullmatch(name):
        raise OpRefused("кличка — от 1 до 14 знаков: латиница, цифры, «-» и «_»")
    row, cn = _row(w, uid, idx, pet, lock)
    if row["PetName"] == name:
        raise OpRefused("кличка уже такая")
    bad = w.rows("SELECT TOP 1 1 AS x FROM dbo.LewdWordList WHERE LEN(Lewdword) > 0 AND CHARINDEX(LOWER(CAST(Lewdword AS VARCHAR(64))), LOWER(CAST(? AS VARCHAR(64)))) > 0",
                 (name,)) if _has_lewd(w) else []
    if bad:
        raise OpRefused("кличка содержит запрещённое слово (LewdWordList)")
    new = dict(row, PetName=name, NameFlag=0)
    text = "кличка питомца %d (%s) персонажа %s (%d/%d): %s → %s" % (pet, _breed(row["Petindex"]), cn, uid, idx, row["PetName"], name)
    return uid, idx, pet, row, new, text, ["игрок после этого сам кличку сменить не сможет (NameFlag 0, как после смены в игре)"]


def _has_lewd(w):
    try:
        w.rows("SELECT TOP 0 Lewdword FROM dbo.LewdWordList")
        return True
    except db.DbError:
        return False


def plan_level(w, p, lock=False, role=None):
    uid, idx, pet = _args(p, role)
    try:
        lv = int(p["level"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры питомца")
    row, cn = _row(w, uid, idx, pet, lock)
    top = min(int(row["PetMaxLvl"] or 0), PET_LVL_MAX)
    if not 1 <= lv <= top:
        raise OpRefused("уровень питомца — от 1 до его потолка %d (потолок поднимает предмет в игре)" % top)
    try:
        e = srvtables.pet_level_exp(row["Petindex"], lv)
    except Exception as ex:
        raise OpRefused("таблицы питомцев сервера не прочитаны: %s" % ex)
    if e is None:
        raise OpRefused("нет строки PetExp_Table/PetInfo_Table для породы %s уровня %d" % (row["Petindex"], lv))
    if e > 32767:
        raise OpRefused("опыт уровня %d выше предела сервера (%d)" % (lv, e))
    new = dict(row, PetLvl=lv, PetExp=e)
    if new == row:
        raise OpRefused("питомец уже на этом уровне")
    text = "уровень питомца %d (%s) персонажа %s (%d/%d): %s → %d, опыт %s → %d" % (
        pet, _breed(row["Petindex"]), cn, uid, idx, row["PetLvl"], lv, row["PetExp"], e)
    return uid, idx, pet, row, new, text, ["опции питомца сервер пересчитает при входе по породе и уровню"]


def plan_delete(w, p, lock=False, role=None):
    uid, idx, pet = _args(p, role)
    row, cn = _row(w, uid, idx, pet, lock)
    text = "удалить питомца %d (%s «%s», уровень %s) у персонажа %s (%d/%d)" % (pet, _breed(row["Petindex"]), row["PetName"],
                                                                              row["PetLvl"], cn, uid, idx)
    return uid, idx, pet, row, None, text, ["откат вернёт питомца с НОВЫМ внутренним номером (PetUnique) — остальное как было"]


def _dbv(c, v):
    """Кличка — в кодировке базы (арабская, cp1256): прочитанное fix_text значение сравнивается/пишется обратно через to_db_text
    (перепроверка 21 М2)."""
    return db.to_db_text(v) if c == "PetName" and isinstance(v, str) else v


def _cond(row):
    return " AND ".join("(%s = ? OR (%s IS NULL AND ? IS NULL))" % (c, c) for c in COLS), [_dbv(c, x) for c in COLS for x in (row[c], row[c])]


class _PetOp(Operation):
    reversible = True
    perm = "players.pets"
    planner = None

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, pet, b, a, text, warn = type(self).planner(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": [b, a], "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры питомца")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, pet, b, a, text, warn = type(self).planner(w, p, lock=True, role=ctx.role)
            if [b, a] != prev["expect"] or ("expect" in p and p["expect"] != [b, a]):
                raise OpRefused("пока вы смотрели предпросмотр, питомец изменился — повторите")
            cond, cp = _cond(b)
            edate = None
            if a is None:                                  # перепроверка 21 К5: дата получения питомца — для отката
                er = w.rows("SELECT CONVERT(varchar(23), Edate, 121) AS e FROM dbo.CharPetList WHERE Userindex = ? AND Charidx = ? "
                            "AND PetUnique = ?", (uid, idx, pet))
                edate = er[0]["e"] if er else None
                n = w.execute("DELETE FROM dbo.CharPetList WHERE Userindex = ? AND Charidx = ? AND PetUnique = ? AND " + cond,
                              [uid, idx, pet] + cp)
            else:
                ch = [c for c in COLS if a[c] != b[c]]
                n = w.execute("UPDATE dbo.CharPetList SET %s WHERE Userindex = ? AND Charidx = ? AND PetUnique = ? AND %s"
                              % (", ".join("%s = ?" % c for c in ch), cond), [_dbv(c, a[c]) for c in ch] + [uid, idx, pet] + cp)
            if n != 1:
                raise OpRefused("питомец изменился при записи — ничего не записано")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "pet": pet, "row": b},
                "after": {"uid": uid, "idx": idx, "pet": pet, "row": a, "before": b, "edate": edate}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        uid, idx, pet, b, af = a.get("uid"), a.get("idx"), a.get("pet"), a.get("before"), a.get("row")
        if not uid or not b:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            if af is None:                                     # удаление → вставка заново (новый PetUnique)
                n = w.rows("SELECT COUNT(*) AS n FROM dbo.CharPetList WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ?",
                           (uid, idx))[0]["n"]
                if int(n) >= MAX_PETS:
                    raise OpRefused("у персонажа уже %d питомцев — сервер при входе отбросил бы весь список" % MAX_PETS)
                if b.get("Active") and w.rows("SELECT 1 AS x FROM dbo.CharPetList WHERE Userindex = ? AND Charidx = ? AND Active = 1",
                                              (uid, idx)):
                    b = dict(b, Active=0)                  # перепроверка 21 К5: другой питомец уже призван — вернуть отозванным
                ed = a.get("edate")                        # перепроверка 21 К5: прежняя дата получения (нет в старых записях — getdate())
                r = w.rows("INSERT INTO dbo.CharPetList (Userindex, Charidx, %s%s) OUTPUT inserted.PetUnique VALUES (?, ?, %s%s)"
                           % (", ".join(COLS), ", Edate" if ed else "", ", ".join("?" * len(COLS)), ", CONVERT(datetime, ?, 121)" if ed else ""),
                           [uid, idx] + [_dbv(c, b[c]) for c in COLS] + ([ed] if ed else []))
                msg = "питомец возвращён (новый номер %s)" % (r[0]["PetUnique"] if r else "?")
            else:
                cond, cp = _cond(af)
                ch = [c for c in COLS if af[c] != b[c]]
                if w.execute("UPDATE dbo.CharPetList SET %s WHERE Userindex = ? AND Charidx = ? AND PetUnique = ? AND %s"
                             % (", ".join("%s = ?" % c for c in ch), cond), [_dbv(c, b[c]) for c in ch] + [uid, idx, pet] + cp) != 1:
                    raise OpRefused("питомец с тех пор менялся — откат не выполнен")
                msg = "питомец %s возвращён" % pet
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"row": af}, "after": {"row": b}, "message": msg, "_commit": w.commit, "_close": w.close}


@register
class PetRename(_PetOp):
    name, title = "pet.rename", "Питомец: кличка"
    planner = staticmethod(plan_rename)


@register
class PetLevel(_PetOp):
    name, title = "pet.level", "Питомец: уровень"
    planner = staticmethod(plan_level)


@register
class PetDelete(_PetOp):
    name, title = "pet.delete", "Питомец: удалить"
    planner = staticmethod(plan_delete)


def describe(uid, idx):
    with db.GameReader("joy1") as r:
        rows = r.rows("SELECT PetUnique, %s FROM dbo.CharPetList WHERE Userindex = ? AND Charidx = ? ORDER BY PetUnique"
                      % ", ".join(COLS), (int(uid), int(idx)))
    return {"pets": [dict(x, breed=_breed(x["Petindex"])) for x in rows]}
