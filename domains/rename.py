# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""rename.py — смена имени персонажа не в игре (волна А1, план §4.Б «смена имени: UPCharRename + сторож A13 + занятость»). 17.11.2026.

КАК У СЕРВЕРА (Joy1.dbo.UPCharRename, текст с правкой A13 — Reports/anticheat/wA13_logs/sql/UPCharRename_a13state.sql):
  отказ, если персонаж в клане (ClanMember: глава — код 2, член — 3) или у него лоты аукциона (Exitem — хранят имя, код 4);
  правило имени — сторож A13 область 2 (domains/charname.py: правила 1–5 сверены с корпусом и с SQL-функцией, 6 LewdWordList,
  7 занятость); учётка-оператор (A13_NameRuleConfig.ExemptOperators = 1 и CharGmInfo.GMFlag NOT NULL, решение a13b)
  освобождена от правил СИМВОЛОВ — длина (столбец varchar(20)), печатный ASCII и занятость проверяются всегда;
  запись: Charinfo.Charname и CharPos.Charname.
ОТЛИЧИЕ ОТ ОРИГИНАЛА (помечено): сервер УДАЛЯЕТ у других игроков дружбу с переименованным (DELETE CharFriend WHERE
  Fuserindex/Fcharidx — в строке хранится старое имя); панель вместо этого ОБНОВЛЯЕТ CharFriend.Charname — дружба не теряется
  (так же делают операторские процедуры оригинала UPNickUpdate и OPCharinfoModify; список друзей клиенту отдаёт UPFriendList
  из F.Charname — перепроверка 10).
СТРОЖЕ СЕРВЕРА (сознательно): отказ всегда (сервер в A13 Mode 0 только пишет журнал); занятость — и по Charinfo и удалённым
  (Del_Charinfo); оператору — только A-Z a-z 0-9 «_» не в конце (у сервера — любые символы). Смена только регистра своего имени
  разрешена. Остаются со старым именем (на игру не влияет — перепроверка 10): журналы, ClanNotice (только показ),
  SellitemAlarm, FameRating* (журнал), почта/соулмейт/рейтинги — по индексам.
  Расходный предмет «смена имени» панель не списывает (это операторское действие), событие Rename в JoyLog1.CharEvent не пишет
  (у логина записи нет доступа к журналам) — запись в adm.audit.
ЗАПИСЬ — asda_ops (UPDATE только столбца Charname в Charinfo, CharPos, CharFriend), одна транзакция, «не в игре» под блокировкой
(items.online_state), сверка с предпросмотром; откат возвращает старое имя, если новое с тех пор не меняли и старое не занято.
Побочных эффектов при импорте нет.
"""
from core import db
from core.ops import Operation, OpRefused, register
from domains import charname, items

OPERATOR_MAX_UID = 5000
OPER_RX = __import__("re").compile(r"^[A-Za-z0-9_]{1,19}$")   # оператор: латиница, цифры, «_» (перепроверка 10 В4)


def _check_name(r, uid, idx, new, cur_bytes, own_deleted=None):
    """Правило имени (A13 область 2) + занятость → None или текст отказа."""
    try:
        b = new.encode("cp1256")
    except UnicodeEncodeError:
        return "имя: %s (правило 4)" % charname.RULES[4]
    cfg, words, lewd = charname.load_config(r)
    oper = bool(cfg.get("ExemptOperators")) and bool(r.rows(
        "SELECT TOP 1 1 AS x FROM dbo.CharGmInfo WHERE Userindex = ? AND GMFlag IS NOT NULL", (uid,)))
    if oper:
        # оператор (a13b): без правил символов клиента, но только A-Z a-z 0-9 «_» и не «_» в конце — апостроф/пробел ломают
        # шёпот, отряд, союз душ и GM-команды по имени (P28 меняет «'» в DBManager), «_» в конце ловит UPCharNameCheck
        if not b:
            v = 1
        elif len(b) >= 20:
            v = 2
        elif any(c < 32 or c == 127 for c in b):
            v = 3
        elif not OPER_RX.match(new) or new.endswith("_"):
            return "имя оператора: только латиница, цифры и «_» (не в конце), до 19 знаков"
        else:
            v = 0
    elif cfg.get("Charset", 0) != 0:
        return "набор символов имени на сервере — не латиница (A13 Charset = %s): такое имя панель не проверит, смените его в игре" % cfg.get("Charset")
    else:
        v = charname.rule(b, words)
        # LewdWordList: CHARINDEX в коллации Arabic_CI_AS — без учёта регистра (перепроверка 10 В3)
        if not v and any(w and str(w).lower() in new.lower() for w in lewd):
            v = 6
    if v:
        return "имя: %s (правило %d)" % (charname.RULES[v], v)
    if b == cur_bytes:
        return "имя не меняется"
    hit = [h for h in r.rows(charname.taken_sql(), (new,) * 6) if not (h["Userindex"] == uid and h["Charidx"] == idx and not h.get("deleted"))
           and not (own_deleted and h.get("deleted") and (h["Userindex"], h["Charidx"]) == tuple(own_deleted))]   # восстановление: своя корзина
    if hit:
        h = hit[0]
        return ("имя занято удалённым персонажем: %s (учётка %s, слот %s) — его восстановление дало бы двойника" if h.get("deleted")
                else "имя занято: %s (учётка %s, слот %s)") % (h["Charname"], h["Userindex"], h["Charidx"])
    return None


def plan(w, p, lock=False, role=None):
    raw = p.get("name") if isinstance(p, dict) else None
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры смены имени")
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise OpRefused("имя: пустое или с пробелами по краям")          # перепроверка 10 М5: без «None» и молчаливой обрезки
    new = raw
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    # имя — и байтами: у «кривых» имён (кириллица, арабица 0x98, мусор) текст после перекодировки с базой не сравнить
    # (перепроверка 10 В1) — запись идёт по ключу персонажа, откат возвращает БАЙТЫ
    c = w.rows("SELECT Charname, CAST(Charname AS varbinary(20)) AS cb FROM dbo.Charinfo%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    if not c:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    cur, cur_b = c[0]["Charname"], bytes(c[0]["cb"] or b"")
    pos = w.rows("SELECT Charname, CAST(Charname AS varbinary(20)) AS cb FROM dbo.CharPos%s WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    if len(pos) != 1:
        raise OpRefused("у персонажа нет строки CharPos — сервер такое имя не сменил бы (UPCharRename: отказ 0)")
    pos_b = bytes(pos[0]["cb"] or b"")
    _clan_exitem(w, uid, idx)
    why = _check_name(w, uid, idx, new, cur_b)
    if why:
        raise OpRefused(why)
    friends = w.rows("SELECT Userindex, Charidx FROM dbo.CharFriend%s WHERE Fuserindex = ? AND Fcharidx = ?" % hint, (uid, idx))
    sig = {"cur": cur_b.hex(), "pos": pos_b.hex(), "friends": len(friends), "new": new}
    text = "имя персонажа %d/%d: %s → %s" % (uid, idx, cur, new)
    warn = ["в %d списках друзей имя тоже обновится (сервер дружбу удалил бы)" % len(friends)] if friends else []
    if pos_b != cur_b:
        warn.append("в CharPos было другое имя (%s) — тоже станет новым" % pos[0]["Charname"])
    return uid, idx, cur, cur_b, pos_b, new, len(friends), sig, text, warn


def _clan_exitem(w, uid, idx):
    """Отказы UPCharRename: клан (2/3), лоты аукциона (4) — и для отката (перепроверка 10 В2: ClanMember/Exitem хранят имя,
    выход из клана UPClanmemberdelete ищет по нему)."""
    grade = w.rows("SELECT Grade FROM dbo.ClanMember WHERE Userindex = ? AND Charidx = ?", (uid, idx))
    if grade:
        raise OpRefused("персонаж в клане (%s) — сервер не меняет имя членам клана (UPCharRename: код %d); сначала выход из клана"
                        % ("глава" if grade[0]["Grade"] == 1 else "член", 2 if grade[0]["Grade"] == 1 else 3))
    ex = w.rows("SELECT COUNT(*) AS n FROM dbo.Exitem WHERE Userindex = ? AND Charidx = ?", (uid, idx))[0]["n"]
    if ex:
        raise OpRefused("у персонажа %d лотов на аукционе — сервер не меняет имя (UPCharRename: код 4); сначала снять лоты" % ex)


@register
class CharRename(Operation):
    name, title, perm, reversible = "char.rename", "Персонаж: сменить имя", "players.rename", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                uid, idx, cur, cur_b, pos_b, new, nf, sig, text, warn = plan(ad, p, role=ctx.role)
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": sig, "warnings": warn + ([items.RECENT_WARN] if items.recently_left(uid) else [])}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            # порядок блокировок как у входа в игру: сначала учётка и CharPos (online_state), потом Charinfo (перепроверка 10 М2)
            try:
                uid0 = int(p["uid"])
            except (KeyError, TypeError, ValueError):
                raise OpRefused("неверные параметры смены имени")
            ok, why = items.online_state(w, uid0, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            uid, idx, cur, cur_b, pos_b, new, nf, sig, text, warn = plan(w, p, lock=True, role=ctx.role)
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("пока вы смотрели предпросмотр, имя или друзья изменились — повторите")
            if w.execute("UPDATE dbo.Charinfo SET Charname = ? WHERE Userindex = ? AND Charidx = ?", (new, uid, idx)) != 1:
                raise OpRefused("имя изменилось при записи — ничего не записано")
            if w.execute("UPDATE dbo.CharPos SET Charname = ? WHERE Userindex = ? AND Charidx = ?", (new, uid, idx)) != 1:
                raise OpRefused("строка CharPos изменилась при записи — ничего не записано")
            n = w.execute("UPDATE dbo.CharFriend SET Charname = ? WHERE Fuserindex = ? AND Fcharidx = ?", (new, uid, idx))
            if n != nf:
                raise OpRefused("списки друзей изменились при записи — ничего не записано")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "name": cur, "name_hex": cur_b.hex(), "pos_hex": pos_b.hex()},
                "after": {"uid": uid, "idx": idx, "name": new, "old": cur, "old_hex": cur_b.hex(), "pos_hex": pos_b.hex(),
                          "friends": nf}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, idx, new, old = a.get("uid"), a.get("idx"), a.get("name"), a.get("old")
        old_b = bytes.fromhex(a["old_hex"]) if a.get("old_hex") is not None else (old or "").encode("cp1256", "replace")
        pos_b = bytes.fromhex(a["pos_hex"]) if a.get("pos_hex") is not None else old_b
        if not uid or not old_b:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            cur = w.rows("SELECT CAST(Charname AS varbinary(20)) AS cb FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) "
                         "WHERE Userindex = ? AND Charidx = ?", (uid, idx))
            if not cur or bytes(cur[0]["cb"] or b"") != new.encode("cp1256", "replace"):
                raise OpRefused("имя персонажа с тех пор меняли — откат не выполнен")
            _clan_exitem(w, uid, idx)
            hit = [h for h in w.rows("SELECT Userindex, Charidx FROM dbo.Charinfo WHERE Charname = CONVERT(varchar(20), ?) UNION ALL "
                                     "SELECT Userindex, Charidx FROM dbo.CharPos WHERE Charname = CONVERT(varchar(20), ?)",
                                     (old_b, old_b)) if not (h["Userindex"] == uid and h["Charidx"] == idx)]
            if hit:
                raise OpRefused("старое имя %s с тех пор занял другой персонаж — откат не выполнен" % old)
            w.execute("UPDATE dbo.Charinfo SET Charname = CONVERT(varchar(20), ?) WHERE Userindex = ? AND Charidx = ?", (old_b, uid, idx))
            w.execute("UPDATE dbo.CharPos SET Charname = CONVERT(varchar(20), ?) WHERE Userindex = ? AND Charidx = ?", (pos_b, uid, idx))
            w.execute("UPDATE dbo.CharFriend SET Charname = CONVERT(varchar(20), ?) WHERE Fuserindex = ? AND Fcharidx = ? AND Charname = ?",
                      (old_b, uid, idx, new))
        except BaseException:
            w.close()
            raise
        return {"before": {"name": new}, "after": {"name": old}, "message": "имя персонажа %s/%s возвращено: %s" % (uid, idx, old),
                "_commit": w.commit, "_close": w.close}
