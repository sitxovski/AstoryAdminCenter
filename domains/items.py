# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""items.py — правка предметов персонажа НЕ В ИГРЕ: переставить, надеть, снять (волна А1, начало). 16.11.2026.

ЗАЧЕМ. Владелец 16.11: «нужна возможность двигать предметы и надевать/снимать снаряжение».

ПОЧЕМУ ТОЛЬКО НЕ В ИГРЕ. GameServer держит инвентарь в памяти и читает его из БД только при входе и при портале; правка
`dbo.Item` у персонажа в игре даёт отказы процедур, потерю или дюп (разбор Reports/admin_items/research_online_persist.md
§2). Поэтому запись идёт ОДНОЙ транзакцией, в которой (§5 того же разбора):
  1) строка Charinfo персонажа берётся под UPDLOCK (вход персонажа начинается с UPDATE Charinfo — он подождёт нас);
  2) предикат «учётка не в игре»: Us_member.Flag = 0 И UserNum = -1 И ни у одного персонажа учётки CharPos.UserNum ≠ −1
     (NULL — «небезопасно»); иначе отказ. Висящие после аварии флаги снимаются входом-выходом игрока или стартом карты;
  3) ячейки читаются под UPDLOCK, HOLDLOCK заново, план пересчитывается и сверяется с предпросмотром.

ПРАВИЛА — 1:1 с сервером (GameServer.c, CharItemMove → sub_4CDAA0 / sub_4CDDA0, разбор в шапке srvtables.py):
  * переставить: только внутри одной сумки — 1→1, 2→2, склад 5→5 (ветки 1↔2 у сервера нет); на занятую ячейку — обмен;
  * надеть (1/2 → 3): слот = itemType предмета (кольцо подтипа 0 — любой из 5/6); отказы как у сервера:
      10 самоцвет, 12 расходник (тип 11) или пакет (t39 > 0), 20 прочность 0 у брони/оружия, 11 не тот слот,
      13 щит (вид ≠ 4) при двуручном в руках, 15 класс (sub_4CDDA0), 14 уровень (+8 ≤ ур. или +9 < ур.) или самоцвет
      в гнезде выше уровня;
    двуручное при надетом щите: сервер требует свободную ячейку сумки 1 (GameServer.c:82450) и щит сам не снимает —
    поэтому здесь отказ «сначала снимите щит» (ничего не остаётся в несогласованном виде);
    при надевании сервер ставит привязку Owner = 1, если у предмета t35 == 1 (GameServer.c:82469), и поднимает MaxupCnt
    до SowelCombine t44 (:82477) — делаем так же; занятый слот — обмен (снятый уходит в ячейку надеваемого);
  * снять (3 → 1/2): как сервер (GameServer.c:82814-82888) — в ПЕРВУЮ СВОБОДНУЮ ячейку указанной сумки, без обмена;
    без указания сумки — «родная» сумка предмета (sub_5340B0: t24 == 3 или тип ∈ {0–4, 8, 9, 12–15} → 1, иначе 2);
  * MaxupCnt до t44: при перестановке 1→1 — обоим предметам, 2→2 и 5→5 — не поднимается; при надевании из сумки 1 —
    и снятому (GameServer.c:82423-82424, 82512-82513).
ОТКАТ. Журнал хранит «было/стало» по Uuid предметов; откат возвращает места, Owner и MaxupCnt, если предметы с тех пор
не двигались. Побочных эффектов при импорте нет.
"""
from core import bridge, db
from core.ops import Operation, OpRefused, register
from domains import refdata, srvtables

PLATE1_TYPES = {0, 1, 2, 3, 4, 8, 9, 12, 13, 14, 15}     # itemType → сумка 1 (sub_5340B0; asda_give.PLATE1_TYPES)
ARMOR_TYPES = {0, 1, 2, 3, 4, 8, 9, 11, 12, 13, 14, 15}  # прочность 0 → отказ 20 (sub_4CDAA0:81943-81957)
EQUIP_SLOTS = 11                                         # Plate 3: 0…10 (sub_4D6910 case 3)
WARE_MAX = 270
BAG60_MIGKEY = "inventory_x2_weight"                     # метка «инвентарь ×2» (asda_give.BAG60_MIGKEY)
TMP_POSX = 32767                                         # временная ячейка при обмене (PK Userindex,Charidx,Plate,Posx)
ERR = {
    2: "персонаж не найден", 10: "самоцвет не надевается", 11: "предмет не подходит к этому слоту",
    12: "расходники и пакеты не надеваются", 13: "щит не надеть, пока в руках двуручное оружие",
    14: "не подходит уровень персонажа (или самоцвет в гнезде требует большего уровня)",
    15: "не подходит класс персонажа", 20: "прочность предмета 0 — сервер не даёт надеть",
}
SLOT_NAMES = {0: "шлем", 1: "верх", 2: "низ", 3: "обувь", 4: "перчатки", 5: "кольцо 1", 6: "кольцо 2", 7: "ожерелье",
              8: "щит", 9: "оружие", 10: "колчан"}
PLATE_NAMES = {1: "сумка 1 (снаряжение)", 2: "сумка 2 (расходники)", 3: "надето", 5: "склад"}
ROW_COLS = "Uuid, Code, Plate, Posx, Amount, Durability, Owner, MaxupCnt, Cell1, Cell2, Cell3, Cell4"
GOLD_CODE = 20551                                        # золото — отдельная строка сумки 2, не перекладывается


def natural_plate(code):
    """Сумка, в которую предмет кладёт сервер (sub_5340B0)."""
    code = int(code)
    if 1 <= code <= 558:
        return 1
    if 7001 <= code < 20551:
        return 2
    r = srvtables.item_rule(code)
    if r and (r["plate_flag"] == 3 or r["type"] in PLATE1_TYPES):
        return 1
    return 2


def job_ok(rule, ch):
    """sub_4CDDA0 (GameServer.c:82022) дословно: Class = CUser.gender_, Job = Nick_name_[12], Subjob = [13],
    JobCount = байт CurWeight+3 (iJobCount)."""
    req = rule["job_req"]
    if not req:
        return True
    cls, job, sub, cnt = ch["Class"] or 0, ch["Job"] or 0, ch["Subjob"] or 0, ch["JobCount"] or 0
    if rule["type"] == 9:                                  # оружие: '('…',' = 40…44 → JobCount ≥ 1…5
        return 40 <= req <= 44 and cnt >= req - 39
    if req in (1, 2, 3):
        return cls == 1 and job >= req and job != 0
    if req in (12, 13, 14):
        return cls == 2 and job >= req
    if req in (23, 24, 25):
        return cls == 3 and job >= req
    if req in (4, 6, 15, 17, 26, 28, 34, 36, 38):          # пара «база + продвинутый»
        return req <= sub <= req + 1
    if req in (5, 7, 16, 18, 27, 29, 35, 37, 39):          # только продвинутый
        return sub == req
    return False


def equip_error(row, slot, ch, equipped):
    """Код отказа сервера (sub_4CDAA0) для надевания row в slot; 0 — можно. equipped — {слот: строка Item}."""
    code = int(row["Code"])
    if 7001 <= code < 20551:
        return 10
    rule = srvtables.item_rule(code)
    if rule is None:
        return 11
    if rule["type"] == 11 or rule["package"] > 0:
        return 12
    if rule["type"] in ARMOR_TYPES and not row["Durability"]:
        return 20
    lvl = ch["Lvl"] or 0
    if slot == rule["type"]:
        if rule["type"] == 8 and rule["kind"] != 4:
            w = equipped.get(9)
            wr = srvtables.item_rule(w["Code"]) if w else None
            if wr and wr["two_hand"] == 2:
                return 13
        if not job_ok(rule, ch):
            return 15
        if not (rule["lvl_min"] <= lvl or rule["lvl_max"] < lvl):
            return 14
        for k in ("Cell1", "Cell2", "Cell3", "Cell4"):
            c = row.get(k)
            if c and 7001 <= int(c) < 20551 and srvtables.cellob_level(c) > lvl:
                return 14
        return 0
    if rule["subtype"] == 0 and rule["type"] == 5 and slot in (5, 6):
        if not job_ok(rule, ch):
            return 15
        return 0 if (rule["lvl_min"] <= lvl or rule["lvl_max"] < lvl) else 14
    return 11


def _load(w, uid, idx, lock):
    """Персонаж, его предметы (Plate 1/2/3/5) и ёмкости сумок; lock — под UPDLOCK в транзакции записи."""
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    r = w.rows("SELECT Userindex, Charidx, Charname, Lvl, Class, Job, Subjob, JobCount, WareCount FROM Charinfo%s "
               "WHERE Userindex = ? AND Charidx = ?" % hint, (uid, idx))
    ch = r[0] if r else None
    if not ch:
        raise OpRefused(ERR[2])
    rows = w.rows("SELECT %s FROM Item%s WHERE Userindex = ? AND Charidx = ? AND Plate IN (1, 2, 3, 5)"
                  % (ROW_COLS, hint), (uid, idx))
    mig = w.rows("SELECT CASE WHEN OBJECT_ID('dbo.AsdaMigrationLog', 'U') IS NULL THEN 0 ELSE 1 END AS t")[0]["t"]
    bag60 = bool(mig) and bool(w.rows("SELECT COUNT(*) AS n FROM dbo.AsdaMigrationLog WHERE MigKey = ?",
                                      (BAG60_MIGKEY,))[0]["n"]) and p96_enabled()
    caps = {1: 60 if bag60 else 30, 2: 60, 3: EQUIP_SLOTS, 5: min(int(ch["WareCount"] or 0), WARE_MAX)}
    cells = {}
    for r in rows:
        r["Uuid"] = str(r["Uuid"])
        cells[(int(r["Plate"]), int(r["Posx"]))] = r
    return ch, cells, caps


_p96 = {"at": 0.0, "on": None}


def p96_enabled():
    """Сумка 1 на 60 ячеек у сервера — только при включённом патче P96_InventoryX2 (GameServer\\ConfigSet\\patches.ini,
    ревизия А1 R10); иначе стоковые 30. Кэш на минуту; файл не прочитан — считаем «выключен» (30 — безопасная сторона)."""
    import time
    if _p96["on"] is not None and time.time() - _p96["at"] < 60:
        return _p96["on"]
    # перепроверка 11 В1: patches.ini — UTF-16 (раньше на сервере читался как UTF-8, секция не находилась → «выключен», сумка 30);
    # общий разбор srvtables.patches_ini / patch_on — с главным выключателем MasterEnable
    try:
        on = srvtables.patch_on("P96_InventoryX2")
    except Exception:
        on = False
    _p96.update(at=time.time(), on=on)
    return on


def online_state(w, uid, lock=False):
    """Предикат research_online_persist.md §1.4 → (можно_править, пояснение). lock — строки Us_member и CharPos учётки под
    UPDLOCK до конца транзакции записи (вход в мир — UPUserNumUp — подождёт нас; ревизия А1 R1)."""
    hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
    m = w.rows("SELECT Flag, UserNum FROM AsdaStoryOp.dbo.Us_member%s WHERE Userindex = ?" % hint, (uid,))
    if lock:
        w.rows("SELECT Charidx FROM CharPos WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ?", (uid,))
    inworld = w.rows("SELECT Charidx FROM CharPos WHERE Userindex = ? AND UserNum <> -1", (uid,))
    if not m:
        return False, "учётки нет в Us_member"
    f, n = m[0]["Flag"], m[0]["UserNum"]
    if inworld or f is None or n is None or f != 0 or n != -1:
        # ★ А2 (мост P127, 18.11.2026): внутри операции (ops.run) предпросмотр не отказывает, если мост может вывести игрока —
        #   учётка уходит в план кика, ops.run кикнет ДО записи и дождётся штатного выхода; моста нет — прежний отказ ниже
        if bridge.plan_offer(uid, lock):
            return True, ""
    if inworld:
        return False, "персонаж учётки в игре (CharPos.UserNum ≠ −1, слот %s)" % ", ".join(str(r["Charidx"]) for r in inworld)
    if f is None or n is None or f != 0 or n != -1:
        return False, "учётка вошла в игру или на выбор персонажа (Us_member.Flag = %s, UserNum = %s)" % (f, n)
    return True, ""


def _first_free(cells, plate, cap, skip=()):
    for x in range(cap):
        if (plate, x) not in cells and (plate, x) not in skip:
            return x
    return None


def plan(w, p, lock=False):
    """План перемещения → dict(kind, moves[(row, plate, posx, owner, maxup)], text, warnings). Отказ — OpRefused."""
    uid, idx = int(p["uid"]), int(p["idx"])
    sp, sx = int(p["src"]["plate"]), int(p["src"]["posx"])
    dp = int(p["dst"]["plate"])
    if sp == 3 and dp == 0:                      # «снять» без указания сумки — в родную сумку предмета (двойной щелчок)
        dp = -1
    dx = p["dst"].get("posx")
    dx = None if dx in (None, "") else int(dx)
    ch, cells, caps = _load(w, uid, idx, lock)
    src = cells.get((sp, sx))
    if not src:
        raise OpRefused("в исходной ячейке (%s, %d) предмета нет" % (PLATE_NAMES.get(sp, sp), sx))
    if p.get("uuid") and str(p["uuid"]).lower() != src["Uuid"].lower():
        raise OpRefused("в исходной ячейке уже другой предмет — обновите страницу")
    equipped = {x: r for (pl, x), r in cells.items() if pl == 3}
    if int(src["Code"]) == GOLD_CODE:
        raise OpRefused("золото не перекладывается (у сервера это отдельная строка сумки 2)")
    def name(r):
        """Название предмета на языке запроса (core.i18n)."""
        # перепроверка 5 М6: текст операции (он же запись журнала) — всегда по-русски; в EN названия подставляет
        # i18n.item_names по коду, так журнал одинаково читается на обоих языках
        inf = refdata.item(r["Code"])
        return "%s (%s)" % (inf["ru"] or inf["en"] or "без названия", r["Code"])
    moves, warn = [], []

    def bump(r):
        """MaxupCnt переносимого предмета — до SowelCombine t44: сервер делает это при ЛЮБОМ перемещении
        (GameServer.c:82477, 82762, 82831, 82875; ревизия А1 R9)."""
        m = srvtables.sowel_maxup(r["Code"]) if int(r["Code"]) >= 20551 else 0
        return max(int(r["MaxupCnt"] or 0), m)

    def bind(r):
        """Привязка при надевании — только из сумки 1 (GameServer.c:82469/82499; из сумки 2 сервер не привязывает,
        ревизия А1 R3)."""
        rule = srvtables.item_rule(r["Code"])
        return 1 if sp == 1 and rule and rule["bind"] == 1 else r["Owner"]

    if sp in (1, 2, 5) and dp == sp:                                       # переставить внутри сумки
        if dx is None or not (0 <= dx < caps[sp]):
            raise OpRefused("ячейка %s вне сумки (0…%d)" % (dx, caps[sp] - 1))
        if dx == sx:
            raise OpRefused("предмет уже в этой ячейке")
        dst = cells.get((dp, dx))
        if dst and int(dst["Code"]) == GOLD_CODE:
            raise OpRefused("в этой ячейке золото — выберите другую (ревизия А1 R8)")
        # остаток R9: при перестановке 1→1 сервер поднимает MaxupCnt обоим предметам (GameServer.c:82477, 82423-82424),
        # при 2→2 (82652-82709) и 5→5 (82596-82644) — не поднимает
        up = bump if sp == 1 else (lambda r: r["MaxupCnt"])
        moves.append((src, dp, dx, src["Owner"], up(src)))
        if dst:
            moves.append((dst, sp, sx, dst["Owner"], up(dst)))
        kind = "swap" if dst else "move"
        text = ("обмен: %s ↔ %s" % (name(src), name(dst))) if dst else \
            "%s: ячейка %d → %d (%s)" % (name(src), sx, dx, PLATE_NAMES[sp])
    elif sp in (1, 2) and dp == 3:                                         # надеть
        rule = srvtables.item_rule(src["Code"])
        if dx is None:
            if rule and rule["type"] == 5 and rule["subtype"] == 0:
                dx = 5 if 5 not in equipped else (6 if 6 not in equipped else 5)
            else:
                dx = rule["type"] if rule else -1
        e = equip_error(src, dx if 0 <= dx < EQUIP_SLOTS else -1, ch, equipped)   # порядок проверок — как у сервера
        if e:
            raise OpRefused("сервер не дал бы надеть: %s (код %d)" % (ERR[e], e))
        if rule and rule["two_hand"] == 2 and dx == 9 and 8 in equipped:
            raise OpRefused("двуручное: сначала снимите щит (сервер щит сам не снимает)")
        if dx == 10 and sp == 2 and 9 in equipped:          # колчан ↔ оружие (GameServer.c:82725-82751, отказ 3)
            wr = srvtables.item_rule(equipped[9]["Code"]) or {}
            q = rule or {}
            bow = wr.get("subtype") == 10
            if (q.get("subtype") == 204 and not (bow and wr.get("arrow_kind") == 1)) or \
               (q.get("subtype") == 36 and not (bow and wr.get("arrow_kind") == 2)) or \
               (q.get("subtype") not in (204, 36) and bow and wr.get("arrow_kind") in (1, 2)):
                raise OpRefused("сервер не дал бы надеть: этот колчан не подходит к надетому оружию (код 3)")
        dst = equipped.get(dx)
        if dst and natural_plate(dst["Code"]) != sp:
            raise OpRefused("в слоте «%s» надет %s — он снимается в «%s», а не туда, откуда надеваем; снимите его отдельно"
                            % (SLOT_NAMES.get(dx, dx), name(dst), PLATE_NAMES[natural_plate(dst["Code"])]))
        new_owner = bind(src)
        if new_owner != src["Owner"]:
            warn.append("предмет привяжется к персонажу (Owner = 1) — так делает сервер при надевании")
        moves.append((src, 3, dx, new_owner, bump(src)))
        if dst:                                            # остаток R9: при 1→3 сервер поднимает и снятому (82512-82513)
            moves.append((dst, sp, sx, dst["Owner"], bump(dst) if sp == 1 else dst["MaxupCnt"]))
        kind = "equip"
        text = "надеть %s в слот «%s»%s" % (name(src), SLOT_NAMES.get(dx, dx), ("; снять " + name(dst)) if dst else "")
    elif sp == 3 and dp in (1, 2, -1):                                     # снять
        # как сервер (GameServer.c:82814-82888): в ПЕРВУЮ СВОБОДНУЮ ячейку указанной сумки, без обмена (ревизия А1 R4);
        # сумка без указания (двойной щелчок) — «родная» сумка предмета (так выбирает клиент: слоты 5–7 → 2, иначе 1)
        if dp == -1:
            dp = natural_plate(src["Code"])
        dx = _first_free(cells, dp, caps[dp])
        if dx is None:
            raise OpRefused("в «%s» нет места" % PLATE_NAMES[dp])
        moves.append((src, dp, dx, src["Owner"], bump(src)))
        kind = "unequip"
        text = "снять %s из слота «%s» → %s, ячейка %d" % (name(src), SLOT_NAMES.get(sx, sx), PLATE_NAMES[dp], dx)
    else:
        raise OpRefused("так переносить нельзя: «%s» → «%s» (сервер разрешает только внутри одной сумки, надеть и снять)"
                        % (PLATE_NAMES.get(sp, sp), PLATE_NAMES.get(dp, dp)))
    if any(int(r["Code"]) == GOLD_CODE for r, *_ in moves):
        raise OpRefused("золото не перекладывается (у сервера это отдельная строка сумки 2)")
    return {"kind": kind, "text": text, "warnings": warn, "char": ch["Charname"],
            "moves": [{"uuid": r["Uuid"], "code": r["Code"], "from": [int(r["Plate"]), int(r["Posx"])], "to": [pl, x],
                       "owner": [r["Owner"], o], "maxup": [r["MaxupCnt"], m]} for r, pl, x, o, m in moves]}


def _apply_moves(w, uid, idx, moves, reverse=False):
    """Переложить предметы (по Uuid, через временную ячейку). reverse — вернуть «было»."""
    stage = []
    for i, mv in enumerate(moves):
        fr, to = (mv["to"], mv["from"]) if reverse else (mv["from"], mv["to"])
        ow = mv["owner"][0] if reverse else mv["owner"][1]
        mx = mv["maxup"][0] if reverse else mv["maxup"][1]
        n = w.execute("UPDATE Item SET Plate = ?, Posx = ? WHERE Userindex = ? AND Charidx = ? AND Plate = ? AND Posx = ? "
                      "AND Uuid = ?", (fr[0], TMP_POSX - i, uid, idx, fr[0], fr[1], mv["uuid"]))
        if n != 1:
            raise OpRefused("предмет %s не на месте (%s) — состояние изменилось, ничего не записано" % (mv["code"], fr))
        stage.append((fr, to, ow, mx, mv, i))
    for fr, to, ow, mx, mv, i in stage:
        n = w.execute("UPDATE Item SET Plate = ?, Posx = ?, Owner = ?, MaxupCnt = ? WHERE Userindex = ? AND Charidx = ? "
                      "AND Plate = ? AND Posx = ? AND Uuid = ?", (to[0], to[1], ow, mx, uid, idx, fr[0], TMP_POSX - i, mv["uuid"]))
        if n != 1:
            raise OpRefused("не удалось переложить %s — ничего не записано" % mv["code"])


@register
class ItemsMove(Operation):
    name, title, perm, reversible = "items.move", "Предметы: переставить / надеть / снять", "players.items_edit", True

    def target(self, p):
        return "char:%s/%s" % (p.get("uid"), p.get("idx"))

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                pl = plan(_ReaderAdapter(r), p)
                ok, why = online_state(_ReaderAdapter(r), int(p["uid"]))
        except (KeyError, TypeError, ValueError, db.DbError):
            raise OpRefused("неверные параметры перемещения")
        if not ok:
            raise OpRefused("править можно только когда игрок не в игре: " + why)
        pl["warnings"] = pl["warnings"] + [RECENT_WARN] if recently_left(int(p["uid"])) else pl["warnings"]
        pl["expect"] = signature(pl)
        return pl

    def apply(self, ctx, p, prev):
        uid, idx = int(p["uid"]), int(p["idx"])
        w = db.GameWriter("joy1")
        try:
            fresh = plan(w, p, lock=True)                                  # заново, под блокировками
            ok, why = online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("править можно только когда игрок не в игре: " + why)
            # ревизия А1 R5: сверка с тем предпросмотром, который подтвердили в браузере (expect), а не только с
            # предпросмотром, построенным заново в этом же запросе
            if signature(fresh) != prev["expect"] or ("expect" in p and p["expect"] != signature(fresh)):
                raise OpRefused("пока вы смотрели предпросмотр, сумки изменились — повторите")
            _apply_moves(w, uid, idx, fresh["moves"])
        except BaseException:
            w.close()
            raise
        return {"before": {"uid": uid, "idx": idx, "moves": fresh["moves"]}, "after": {"uid": uid, "idx": idx,
                "moves": fresh["moves"], "kind": fresh["kind"]}, "message": fresh["text"], "_commit": w.commit, "_close": w.close}

    def verify(self, ctx, p, res):
        uid, idx = res["after"]["uid"], res["after"]["idx"]
        with db.GameReader("joy1") as r:
            for m in res["after"]["moves"]:
                got = r.one("SELECT Plate, Posx FROM Item WHERE Userindex = ? AND Charidx = ? AND Uuid = ?", (uid, idx, m["uuid"]))
                if not got or [int(got["Plate"]), int(got["Posx"])] != m["to"]:
                    raise RuntimeError("проверка после записи: предмет %s не на месте" % m["code"])

    def undo(self, ctx, row):
        import json
        after = json.loads(row["after_json"] or "{}")
        uid, idx, moves = after.get("uid"), after.get("idx"), after.get("moves") or []
        if not moves:
            raise OpRefused("в журнале нет данных для отката")
        w = db.GameWriter("joy1")
        try:
            w.rows("SELECT Userindex FROM Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ?", (uid, idx))
            ok, why = online_state(w, uid, lock=True)
            if not ok:
                raise OpRefused("откат только когда игрок не в игре: " + why)
            # ревизия А1 R6: откат — только если предметы с тех пор не трогали (места, привязка, MaxupCnt как «стало»),
            # а прежние ячейки свободны или заняты ими же; иначе отказ с понятной причиной, без ошибки ключа
            ids = {m["uuid"].lower() for m in moves}
            for m in moves:
                cur = w.rows("SELECT Plate, Posx, Owner, MaxupCnt FROM Item WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? "
                             "AND Charidx = ? AND Uuid = ?", (uid, idx, m["uuid"]))
                if not cur or [int(cur[0]["Plate"]), int(cur[0]["Posx"])] != m["to"] or cur[0]["Owner"] != m["owner"][1] \
                        or cur[0]["MaxupCnt"] != m["maxup"][1]:
                    raise OpRefused("предмет %s с тех пор менялся — откат не выполнен" % m["code"])
                occ = w.rows("SELECT Uuid FROM Item WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = ? AND Charidx = ? AND Plate = ? "
                             "AND Posx = ?", (uid, idx, m["from"][0], m["from"][1]))
                if occ and str(occ[0]["Uuid"]).lower() not in ids:
                    raise OpRefused("прежняя ячейка предмета %s теперь занята — откат не выполнен" % m["code"])
            _apply_moves(w, uid, idx, moves, reverse=True)
        except BaseException:
            w.close()
            raise
        return {"before": after, "after": {"uid": uid, "idx": idx, "restored": moves}, "message": "предметы возвращены на места",
                "_commit": w.commit, "_close": w.close}


RECENT_WARN = ("игрок выходил из мира меньше 10 минут назад: если он сейчас на экране выбора персонажа и войдёт во время "
               "записи, сервер может не увидеть правку — лучше убедиться, что игрок вышел из игры совсем")


def signature(pl):
    """Отпечаток плана: какие предметы и куда (ревизия А1 R5)."""
    return [[m["uuid"].lower(), m["to"]] for m in pl["moves"]]


def recently_left(uid):
    """Недавний выход из мира (JoyLog1.LogInfo.Logout за 10 мин) — признак, что игрок может быть на экране выбора
    персонажа; там по БД он «не в игре», а вход в мир читает инвентарь до того, как упрётся в наши блокировки
    (ревизия А1 R1: UPCharInfo / UPPlateItem читают Item с READUNCOMMITTED). Закрыть это окно по БД нельзя — только
    предупредить."""
    try:
        with db.GameReader("joylog1") as lg:
            r = lg.one("SELECT TOP 1 Logout FROM LogInfo WHERE Userindex = ? AND Logout >= DATEADD(minute, -10, GETDATE()) "
                       "ORDER BY Logout DESC", (uid,))
            return bool(r)
    except db.DbError:
        return False


class _ReaderAdapter:
    """GameReader с интерфейсом rows() как у GameWriter (для общего plan())."""

    def __init__(self, r):
        self.r = r

    def rows(self, sql, params=()):
        return self.r.rows(sql.replace(" WITH (UPDLOCK, HOLDLOCK)", ""), params)
