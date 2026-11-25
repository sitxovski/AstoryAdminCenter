# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""charmove.py — перенести персонажа не в игре в безопасную точку («вытащить застрявшего»; волна А1, план §4.Б). 18.11.2026.

РАЗБОР — Reports/admin_center/research_char_move.md:
  вход решают ТОЛЬКО CharPos.Poridx, Posx, Posy (UPCharPos: LoginManager.c:4227, DBManager.exe.c:3033); Gsidx/Threadidx/Channel пишет
  вход (UPUserNumUp) и никто не читает; Cporidx — текущая карта; State 3 — «вышел мёртвым» (GS DisConnectUser) — НЕ трогаем
  (обработка при входе не доказана). LoginManager sub_40AD30: клетка 0,0 → карта 3; карты 19/20/22 → подмена на Charinpos;
  иначе Game_<Poridx> (на dev GAMECOUNT 23 — карта 23 не загружена). GS CharMake@0x543A10: клетка вне карты → старт MapInfo →
  125,390 на ТЕКУЩЕЙ карте → спираль к ближайшей проходимой (sub_41EC30). Точка возрождения — VillagePos (нет строки → 3, 125,390,
  charLogOnRes@0x5277D0). Стоковый AsdaStoryOp.OPCharPosModify неисполним (Msg 245) — не используем.
РЕЖИМЫ: village — своя точка возрождения VillagePos (нет — Альпия 125,390); new — как новый персонаж (3, 0,0 → старт MapInfo
  Альпии); town — город 0 (Силарис 393,397), 3 (Альпия 125,390), 7 (Пламения 135,188) — точки сервера (умолчание GS,
  Total_PortalConfig); custom (owner/admin) — карта, которую поднимает GameServer (OpenMapInfo.ini), кроме 10/11/19/20/22, клетка 1…511;
  ★ А5.2: char (owner/admin) — клетка другого персонажа в игре по мосту (to_uid, to_idx; аналог стоковых 6012 / 6014), правила — как custom.
ЗАПИСЬ — asda_ops UPDATE (Poridx, Cporidx, Posx, Posy) CharPos; одна транзакция; «учётка не в игре» под блокировкой Us_member и
  CharPos учётки (items.online_state — уровень учётки: LoginManager читает CharPos дважды); строка — WHERE UserNum = −1. Откат
  возвращает прежние значения, если позиция с тех пор не менялась. Побочных эффектов при импорте нет.
"""
import time

from core import bridge, db
from core.ops import Operation, OpRefused, register
from domains import items, refdata, srvtables

OPERATOR_MAX_UID = 5000
TOWNS = {0: (393, 397), 3: (125, 390), 7: (135, 188)}
NEW_POS = (3, 0, 0)                        # UPCreateChar: карта 3, клетка 0,0 (LoginManager/GS ставят старт MapInfo Альпии)
VILLAGE_DEFAULT = (3, 125, 390)            # charLogOnRes: строки VillagePos нет
BAD_MAPS = {10, 11, 19, 20, 22}            # 10/11 — подземелья P108 (к выходу портала), 19/20/22 — подмена Charinpos (LoginManager)
CUSTOM_ROLES = {"owner", "admin"}          # перепроверка 17 М4: «своя точка» (в т.ч. подземелья атрибута 3) — не gm
MAX_MAP, MAX_CELL = 22, 511
COLS = ("Poridx", "Cporidx", "Posx", "Posy")


def _int(v, what):
    if isinstance(v, bool):
        raise OpRefused("неверное значение: %s" % what)
    try:
        return int(v)
    except (TypeError, ValueError):
        raise OpRefused("неверное значение: %s" % what)


def _allowed_maps():
    """Карты для «своей точки»: поднятые GameServer (OpenMapInfo.ini Use = 1, n < MapCount) без BAD_MAPS."""
    try:
        return srvtables.open_maps() - BAD_MAPS
    except Exception as ex:
        raise OpRefused("список карт сервера не прочитан: %s" % ex)


def target_pos(w, uid, idx, p, role=None, warn=None):
    """→ (карта, x, y, описание)."""
    mode = p.get("mode")
    if mode == "village":
        v = w.rows("SELECT Villageidx, Posx, Posy FROM dbo.VillagePos WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        if v and v[0]["Villageidx"] is not None:
            m, x, y = int(v[0]["Villageidx"]), int(v[0]["Posx"] or 0), int(v[0]["Posy"] or 0)
            # перепроверка 17 В3: как charLogOnRes (GameServer.c:112380) — точка из базы только при X, Y > 0; и только город
            if m in TOWNS and 0 < x <= MAX_CELL and 0 < y <= MAX_CELL:
                return m, x, y, "своя точка возрождения"
            if warn is not None:
                warn.append("своя точка возрождения негодна (карта %s, клетка %s,%s) — взята точка сервера" % (m, x, y))
        m, x, y = VILLAGE_DEFAULT
        return m, x, y, "своя точка возрождения (своей нет — как у сервера)"
    if mode == "new":
        m, x, y = NEW_POS
        return m, x, y, "как новый персонаж"
    if mode == "town":
        m = _int(p.get("map"), "город")
        if m not in TOWNS:
            raise OpRefused("город — только 0, 3 или 7")
        x, y = TOWNS[m]
        return m, x, y, "город"
    if mode == "custom":
        if role not in CUSTOM_ROLES:
            raise OpRefused("своя точка — только владельцу и администратору")
        m, x, y = _int(p.get("map"), "карта"), _int(p.get("x"), "клетка X"), _int(p.get("y"), "клетка Y")
        ok = _allowed_maps()
        if m not in ok:
            raise OpRefused("карта %d не подходит: только карты, которые сервер поднимает, кроме подземелий 10/11 (можно: %s)"
                            % (m, ", ".join(map(str, sorted(ok)))))
        if not (1 <= x <= MAX_CELL and 1 <= y <= MAX_CELL):
            raise OpRefused("клетка — от 1 до %d" % MAX_CELL)
        return m, x, y, "своя точка"
    if mode == "char":
        # ★ А5.2 (21.11.2026): «к персонажу» — клетка другого персонажа, который сейчас в игре (по данным моста). Это то, что делают
        #   стоковые 6012 Summon (цель — к GM) и 6014 Meet (GM — к цели): сток берёт клетку и карту другого персонажа и переносит
        #   (Reports/gm_original_commands/group1_spec.md §2–3). Без живого оператора: перенос — тем же путём char.move (мост move / jump
        #   или запись CharPos, если переносимый не в игре). Правила карты — как у «своей точки».
        if role not in CUSTOM_ROLES:
            raise OpRefused("перенос к персонажу — только владельцу и администратору")
        tu, ti = _int(p.get("to_uid"), "учётка цели"), _int(p.get("to_idx"), "слот цели")
        if (tu, ti) == (_int(p.get("uid"), "учётка"), _int(p.get("idx"), "слот")):
            raise OpRefused("нельзя перенести персонажа к самому себе")
        rows = [r for r in bridge.presence(tu) if int(r["Userindex"]) == tu and int(r["Charidx"]) == ti]
        fresh = {n["node"] for n in bridge.nodes() if n["fresh"]}
        rows = [r for r in rows if r["node"] in fresh]
        if len(rows) != 1:
            raise OpRefused("персонажа %d/%d нет в игре по данным моста — его клетка неизвестна" % (tu, ti))
        r = rows[0]
        m, x, y = int(r["map"]), int(r["x"] or 0), int(r["z"] or 0)
        ok = _allowed_maps()
        if m not in ok:
            raise OpRefused("персонаж %s на карте %d — туда перенос не делается (только карты, которые сервер поднимает, кроме подземелий 10/11)"
                            % (r["charname"], m))
        if not (1 <= x <= MAX_CELL and 1 <= y <= MAX_CELL):
            raise OpRefused("клетка персонажа %s (%d,%d) вне 1…%d" % (r["charname"], x, y, MAX_CELL))
        # ★ ревизия 42 С-2: переносит узел ПЕРЕНОСИМОГО (jump / move 5055 — внутри его канала); цель на другом узле (Ch1 ↔ Ch2,
        #   поле ↔ Indun) — перенос между каналами мостом не делается: отказ, а не «прыжок в ту же клетку своего канала»
        mu, mi = _int(p.get("uid"), "учётка"), _int(p.get("idx"), "слот")
        moved = [q for q in bridge.presence(mu) if int(q["Userindex"]) == mu and int(q["Charidx"]) == mi and q["node"] in fresh]
        if moved and moved[0]["node"] != r["node"]:
            raise OpRefused("персонаж %s на другом узле (%s, переносимый — на %s) — перенос между каналами мостом не делается"
                            % (r["charname"], r["node"], moved[0]["node"]))
        if warn is not None:
            warn.append("клетка взята у персонажа %s в момент предпросмотра — он мог отойти" % r["charname"])
            if not moved:
                warn.append("переносимый не в игре: меняется позиция для входа, канал (%s или другой) при входе выберет игрок" % r["node"])
        return m, x, y, "к персонажу %s" % r["charname"]
    raise OpRefused("неверный режим переноса")


def plan(w, p, lock=False, role=None):
    try:
        uid, idx = int(p["uid"]), int(p["idx"])
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры переноса")
    if uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Charname, UserNum, State, CONVERT(varchar(23), LastDate, 121) AS lastdate, %s FROM dbo.CharPos%s WHERE Userindex = ? AND Charidx = ?" % (", ".join(COLS), hint),
               (uid, idx))
    if not r:
        raise OpRefused("персонажа %d/%d нет" % (uid, idx))
    r = r[0]
    warn = []
    m, x, y, how = target_pos(w, uid, idx, p, role=role, warn=warn)
    new = {"Poridx": m, "Cporidx": m, "Posx": x, "Posy": y}
    before = {k: r[k] for k in COLS}
    if before == new:
        raise OpRefused("персонаж уже в этой точке")
    if int(r["State"] or 0) == 3:
        warn.append("персонаж вышел мёртвым (State 3) — состояние не меняется, сервер обработает его при входе как обычно")
    if m == 3 and (x, y) == (0, 0):
        warn.append("клетка 0,0: при входе сервер поставит персонажа в стартовую точку Альпии")
    if p.get("mode") == "custom":
        warn.append("своя точка: если клетка непроходима, сервер при входе сдвинет персонажа к ближайшей проходимой")
    text = "перенести персонажа %s (%d/%d): карта %s (%s) %s,%s → карта %s (%s) %d,%d — %s" % (
        r["Charname"], uid, idx, before["Poridx"], refdata.map_name(before["Poridx"]) or "?", before["Posx"], before["Posy"],
        m, refdata.map_name(m) or "?", x, y, how)
    return uid, idx, before, new, text, warn, r["lastdate"]


def _apply(w, uid, idx, before, after, stale):
    sets = ", ".join("%s = ?" % k for k in COLS)
    where = " AND ".join("%s = ?" % k for k in COLS)
    n = w.execute("UPDATE dbo.CharPos SET %s WHERE Userindex = ? AND Charidx = ? AND UserNum = -1 AND %s" % (sets, where),
                  [after[k] for k in COLS] + [uid, idx] + [before[k] for k in COLS])
    if n != 1:
        raise OpRefused(stale)


_jump_off = {}                     # ★ ревизия 29 К-1: (uid, idx) → до какого времени перенос в своей карте не живьём (узел ответил 11)


def _live_row(uid, idx, new):
    """Строка присутствия персонажа, если его можно перенести живьём: мост с Mode=1 видит его; другая карта — op move (5055, P123),
    ★ А2.3: та же карта — op jump (узел v82+: гейты CharJumpCommandPosition и стоковая CharJumpCommandPosition_0). Иначе None."""
    rows = [r for r in bridge.can_kick(uid) if int(r["Userindex"]) == uid and int(r["Charidx"]) == idx]
    if len(rows) != 1 or new["Posx"] <= 0 or new["Posy"] <= 0:
        return None
    r = dict(rows[0])
    if int(r["map"]) != int(new["Poridx"]):
        r["_op"] = "move"
    elif int(r.get("ver") or 0) >= bridge.GIVE_VER and _jump_off.get((uid, idx), 0) <= time.time():
        r["_op"] = "jump"
    else:
        return None
    return r


class _Adapter:
    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql, params)


@register
class CharMove(Operation):
    name, title, perm, reversible = "char.move", "Персонаж: перенести (вытащить застрявшего)", "players.move", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = _Adapter(r)
                uid, idx, before, new, text, warn, _ld = plan(ad, p, role=ctx.role)
                # ★ А2.2 (мост P127): игрок в игре на узле с Mode=1 и цель — ДРУГАЯ карта → перенос живьём (5055 код 1, как P123);
                #   своя карта живьём не переносится (у стока нет 5055 на свою карту) — тогда «кик + запись» (ops.run)
                live = _live_row(uid, idx, new)
                if live:
                    # ★ ревизия А2.3: отпечаток живого пути — с ключом "live" (иначе ops._same_path отказывал подтверждению из браузера)
                    exp = {"before": before, "after": new, "live": [live["_op"], int(new["Poridx"]), int(new["Posx"]), int(new["Posy"])]}
                    if live["_op"] == "jump":
                        t = ("%s — игрок в игре (%s): перенос ЖИВЬЁМ мостом в пределах карты %d, клетка %d,%d (сервер поставит на "
                             "ближайшую проходимую)" % (text, live["node"], new["Poridx"], new["Posx"], new["Posy"]))
                    else:
                        t = ("%s — игрок в игре (%s): перенос ЖИВЬЁМ мостом на карту %d, клетка %d,%d (5055)"
                             % (text, live["node"], new["Poridx"], new["Posx"], new["Posy"]))
                    return {"text": t, "expect": exp, "warnings": warn,
                            "live": {"node": live["node"], "uid": uid, "idx": idx, "from_map": int(live["map"]), "op": live["_op"]}}
                ok, why = items.online_state(ad, uid)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("переносить можно только когда игрок не в игре: " + why)
        return {"text": text, "expect": {"before": before, "after": new}, "warnings": warn}

    def apply(self, ctx, p, prev):
        try:
            uid0 = int(p["uid"])
        except (KeyError, TypeError, ValueError):
            raise OpRefused("неверные параметры переноса")
        if prev.get("live"):
            lv, new = prev["live"], prev["expect"]["after"]
            try:
                row = bridge.call(lv.get("op") or "move", lv["uid"], lv["idx"], lv["node"],
                                  "map=%d;x=%d;z=%d" % (new["Poridx"], new["Posx"], new["Posy"]), ttl=20, by=ctx.login)
            except bridge.BridgeError as ex:
                if lv.get("op") == "jump" and getattr(ex, "code", None) == 11:
                    _jump_off[(lv["uid"], lv["idx"])] = time.time() + 600          # К-1: узел не умеет — следующий раз «кик + запись»
                    raise OpRefused("перенос живьём не выполнен: %s — повторите предпросмотр: перенос пойдёт прежним путём «кик + запись»" % ex)
                raise OpRefused("перенос живьём не выполнен: %s" % ex)
            msg = row.get("result") or "перенос живьём отправлен"
            if lv.get("op") == "jump":
                kv = bridge.parse_kv(msg)
                msg = "перенесён живьём в пределах карты %s: клетка %s,%s" % (kv.get("map", new["Poridx"]), kv.get("x", "?"), kv.get("z", "?"))
            return {"before": {"uid": lv["uid"], "idx": lv["idx"], "live_from_map": lv["from_map"]},
                    "after": {"uid": lv["uid"], "idx": lv["idx"], "live": True, "op": lv.get("op") or "move", "cmd": int(row["id"]), "to": new},
                    "message": msg}
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid0, lock=True)              # уровень учётки: Us_member и CharPos под блокировкой
            if not ok:
                raise OpRefused("переносить можно только когда игрок не в игре: " + why)
            uid, idx, before, new, text, warn, ld = plan(w, p, lock=True, role=ctx.role)
            sig = {"before": before, "after": new}
            if sig != prev["expect"] or ("expect" in p and p["expect"] != sig):
                raise OpRefused("пока вы смотрели предпросмотр, позиция персонажа изменилась — повторите")
            _apply(w, uid, idx, before, new, "персонаж изменился при записи — ничего не записано")
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "pos": before},
                "after": {"uid": uid, "idx": idx, "pos": new, "before": before, "lastdate": ld}, "message": text,
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        import json
        a = json.loads(row["after_json"] or "{}")
        uid, idx = a.get("uid"), a.get("idx")
        if a.get("live"):
            raise OpRefused("перенос живьём (мост) не откатывается журналом — перенесите персонажа обратно новым действием")
        if not uid or not a.get("pos") or not a.get("before"):
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            ok, why = items.online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            # перепроверка 17 М3: LastDate пишут вход и выход (панель — нет) — вошёл и вышел на том же месте = «входил»
            if "lastdate" in a and not w.rows("SELECT 1 AS x FROM dbo.CharPos WHERE Userindex = ? AND Charidx = ? AND "
                                              "(CONVERT(varchar(23), LastDate, 121) = ? OR (LastDate IS NULL AND ? IS NULL))",
                                              (uid, idx, a["lastdate"], a["lastdate"])):
                raise OpRefused("персонаж с тех пор входил или переносился — откат не выполнен")
            _apply(w, uid, idx, a["pos"], a["before"], "персонаж с тех пор входил или переносился — откат не выполнен")
        except BaseException:
            w.close()
            raise
        return {"before": a["pos"], "after": a["before"], "message": "позиция персонажа %s/%s возвращена" % (uid, idx),
                "_commit": w.commit, "_close": w.close}
