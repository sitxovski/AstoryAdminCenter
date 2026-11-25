# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""itemrecover.py — вернуть удалённый предмет по журналам ТЕМ ЖЕ номером (волна А1, решение владельца 19.11 п.3). 19.11.2026.

РАЗБОР — Reports/admin_center/research_items_trace.md §4. Полной копии строки предмета при обычном уничтожении нет нигде —
только строка журнала. Источник возврата — ОДНА строка журнала-уничтожения (feed.DEATH с признаком «можно вернуть»):
  выброс (Wastebasket*), продажа NPC (SellNPC*), разбор (DisassembleUse), снятие лота по таймауту (ExchangeEvent 'Time Out-Delete'
  + поля предмета из ExchangeRegi* того же номера). Конец срока (TimeExpired) и расход ремеслом (Item_Delete) — не возвращаются:
  это не потеря.
СТРОКА — из журнала то, что в нём есть (количество / заряды, гнёзда Cell1–4, ступень, AcuUpcnt, MaxupCnt, Updamage, опции 1–5), остальное
  — по правилу кода (itemgive.item_spec, как сервер sub_5340B0): сумка, прочность (максимальная), вес (стопка — количество × вес,
  снаряжение — свой вес + вес камней в гнёздах), привязка Owner; номера вставленных совелов (Uc) — новые; Refine 0; срок (Rdate) — нет;
  GainDate — первое событие следа. Окно показывает ЯВНЫЙ список полей, которые не восстановятся (LOST).
ЗАЩИТА ОТ ДЮПА — номер нигде не живёт (adm.ItemRecover проверяет атомарно: Item, Exitem.Eid, Uc1–4 в Item и Exitem, Del_item,
  неоткаченные снимки adm.ItemTaken); после события-источника номер больше нигде не встречается (иначе предмет «вернулся» другим путём);
  этот же источник не возвращён. Почтовый ящик (ItemPostBox) номера не хранит — проверить его нельзя (там и не может быть экземпляра).
ПРОДАННОЕ NPC — при возврате списывается золото продажи (SellNPC*.Gm; флажок charge_gold, по умолчанию включён; не хватает — отказ).
ЗАПИСЬ — как выдача: «учётка не в игре» под блокировкой (мост P127 — «кик + запись»), план заново под блокировкой и сверка с
  предпросмотром, EXEC adm.ItemRecover; журналы adm.ItemLedger (вид recover) и JoyLog1.AdminitemLog 'Item Recover(Admin)'.
  Откат — adm.ItemUndo (убрать строку, если не менялась; вернуть списанное золото). Право — players.items_give (только владелец).
Побочных эффектов при импорте нет.
"""
import datetime
import json

from core import db
from core.ops import Operation, OpRefused, register
from domains import feed, items, itemgive, refdata, srvtables

GOLD_CODE = 20551
WEIGHT_MAX = 32767

# Что в журнале-источнике есть (кроме Code/Serial). Остальное — из LOST.
HAS = {
    "WastebasketGear": {"gear"}, "SellNPCGear": {"gear", "gold"}, "DisassembleUse": {"gear"},
    "WastebasketFunctional": {"amount"}, "SellNPCFunctional": {"amount", "gold"},
    "Wastebasketitem": {"amount", "rest"}, "SellNPC": {"amount", "rest", "gold"},
    "WastebasketSowel": set(), "WastebasketNostack": set(), "SellNPCSowel": {"gold"}, "SellNPCNoStack": {"gold"},
    "ExchangeEvent": {"amount", "opt12"},
}
LOST_COMMON = [
    "прочность — максимальная по таблице (в журнале её нет)",
    "привязка к персонажу (Owner) — по таблице кода, а не как была",
    "заточка Refine — 0",
    "срок (Rdate) — не восстанавливается: у сроковых пойдёт заново",
    "дата получения — по первому событию следа",
]
LOST_GEAR_NO = "гнёзда (вставленные совелы), ступень, опции 1–5, MaxupCnt — нет в журнале: как у нового предмета"
LOST_GEAR_YES = "вставленные совелы — те же камни, но с НОВЫМИ номерами (номеров камней в журнале нет)"
LOST_UPDAMAGE_TINY = "Updamage — журнал выброса хранит его байтом (tinyint), у предмета smallint: значения выше 255 не восстановятся"
LOST_OPT12 = "гнёзда, опции 3–5, AcuUpcnt, MaxupCnt — из журнала выставления (ExchangeRegi*), если он есть; иначе как у нового"
NOTE_DISASSEMBLE = "материалы, полученные при разборе (DisassembleGain*), остаются у игрока — изымите отдельно, если нужно"


def _get(r, *names, default=None):
    """Значение столбца строки журнала по любому из имён (регистр — как у таблиц: Upcount / Upcnt, OpValue1 / OPvalue1)."""
    low = {k.lower(): v for k, v in r.items()}
    for n in names:
        v = low.get(n.lower())
        if v is not None:
            return v
    return default


def _int(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def source_row(table, serial, at):
    """Строка журнала-источника: (каталожная запись, строка). Ровно одна — иначе отказ."""
    short = (table or "").split(".", 1)[-1]
    ent = next((e for e in feed.catalog() if e["tab"] == short and e["sch"] == "dbo"), None)
    if not ent or not ent["time"] or not any(c == "Serial" for c, _t in ent.get("serials") or []):
        raise OpRefused("таблица %s — не журнал уничтожения с номером" % table)
    if short not in HAS:
        raise OpRefused("по журналу %s предмет не возвращается (это не потеря: конец срока, ремесло — или не уничтожение)" % short)
    extra = " AND [State] = ?" if short == "ExchangeEvent" else ""
    args = [serial, at] + ([feed.TIMEOUT_STATE] if extra else [])
    with db.GameReader("joylog1") as lg:
        rows = lg.rows("SELECT TOP 2 *, CONVERT(varchar(23), [%s], 121) AS [__at] FROM %s WHERE [Serial] = CAST(? AS varchar(36)) "
                       "AND CONVERT(varchar(23), [%s], 121) = ?%s" % (ent["time"], feed._q(ent), ent["time"], extra), args)
        reg = None
        if short == "ExchangeEvent" and len(rows) == 1:
            # поля предмета лота — из журнала выставления того же номера (последнее до снятия)
            for t in ("ExchangeRegiGear", "ExchangeRegiFunctional", "ExchangeRegi", "ExchangeRegiSowel", "ExchangeRegiNoStack"):
                got = lg.rows("SELECT TOP 1 * FROM [dbo].[%s] WHERE [Serial] = CAST(? AS varchar(36)) AND [Edate] <= ? ORDER BY [Edate] DESC"
                              % t, (serial, rows[0]["Edate"]))
                if got:
                    reg = (t, got[0])
                    break
    if len(rows) != 1:
        raise OpRefused("строка журнала %s от %s не найдена (или не одна)" % (short, at))
    return ent, rows[0], reg


def _later_events(serial, at, tr=None):
    """События этого номера ПОСЛЕ источника (тот же номер встретился снова — предмет жив или вернулся другим путём). Время —
    строкой CONVERT 121 (сравнение строк = сравнение времени, без потери миллисекунд)."""
    tr = tr or feed.trace(serial)
    # ★ ревизия 27 М-1: только события САМОГО номера (след включает и номера цепочки — у получателя неполного обмена свой номер)
    mine = [e for e in tr["events"] if serial in (e.get("hit") or []) and e.get("key") and e["key"] > at]
    later = [e for e in mine if e["table"] != "dbo.AdminitemLog"]
    adm_after = [e for e in mine if e["table"] == "dbo.AdminitemLog"]
    return tr, later, adm_after


def plan_recover(w, p, lock=False, trace_cache=None):
    """→ dict(uid, idx, plate, posx, cap, row{…}, gold, text, warnings, lost, sig). Отказ — OpRefused."""
    try:
        serial = feed._norm_serial(p.get("serial"))
        table = str(p["table"])
        at = str(p["at"]).strip()[:23]
        datetime.datetime.strptime(at[:19], "%Y-%m-%d %H:%M:%S")
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры возврата")
    charge_gold = p.get("charge_gold", True) not in (False, 0, "0", "false", "no")
    ent, r, reg = source_row(table, serial, at)
    short = ent["tab"]
    has = HAS[short]
    if "rest" in has and _int(_get(r, "Ramount")) > 0:
        raise OpRefused("выброшена / продана только часть стопки (осталось %s) — номер живёт у владельца, вернуть нельзя без дюпа"
                        % _get(r, "Ramount"))
    uid, idx, code = _int(_get(r, "Userindex")), _int(_get(r, "Charidx")), _int(_get(r, "Code"))
    if code == GOLD_CODE or code <= 0:
        raise OpRefused("золото и пустые строки не возвращаются")
    tr, later, adm_after = trace_cache or _later_events(serial, at)
    if later:
        raise OpRefused("после этого события номер встречается снова (%s, %s) — предмет жив или уже вернулся"
                        % (later[0]["table"], str(later[0]["at"])[:19]))
    s = itemgive.item_spec(code)
    ch, cells, caps = items._load(w, uid, idx, lock)
    plate = s["plate"]
    cap = caps[plate]
    free = [x for x in range(cap) if (plate, x) not in cells]
    if not free:
        raise OpRefused("в «%s» нет свободной ячейки" % items.PLATE_NAMES.get(plate, plate))
    row = {"Cell1": 0, "Cell2": 0, "Cell3": 0, "Cell4": 0, "Upcount": 0, "AcuUpcnt": 0, "MaxupCnt": s["maxup"], "Updamage": 0,
           "Opidx1": -1, "OpValue1": 0, "Opidx2": -1, "OpValue2": 0, "Opidx3": -1, "Opvalue3": 0, "Opidx4": -1, "Opvalue4": 0,
           "OPidx5": -1, "Opvalue5": 0}
    src = r
    if short == "ExchangeEvent" and reg and reg[0] == "ExchangeRegiGear":
        src = dict(reg[1], **{k: v for k, v in r.items() if k in ("Amount",)})
    lost = list(LOST_COMMON)
    gear_fields = "gear" in has or (short == "ExchangeEvent" and reg and reg[0] == "ExchangeRegiGear")
    if s["gear"] or gear_fields:
        if gear_fields:
            for k in range(1, 5):
                row["Cell%d" % k] = max(0, _int(_get(src, "Cell%d" % k)))
            row["Upcount"] = _int(_get(src, "Upcount", "Upcnt"))
            row["AcuUpcnt"] = _int(_get(src, "AcuUpcnt", "AcuUPcnt"))
            row["MaxupCnt"] = max(_int(_get(src, "MaxupCnt", "MaxUpcnt", "MaxUPcnt")), 0)
            row["Updamage"] = _int(_get(src, "Updamage", "UPdamage"))
            for k, (o, v) in enumerate((("Opidx1", "OpValue1"), ("Opidx2", "OpValue2"), ("Opidx3", "Opvalue3"), ("Opidx4", "Opvalue4"),
                                        ("OPidx5", "Opvalue5")), 1):
                row[o] = _int(_get(src, "Opidx%d" % k, "OPidx%d" % k), -1)
                row[v] = _int(_get(src, "OpValue%d" % k, "OPvalue%d" % k, "Opvalue%d" % k), 0)
            if any(row["Cell%d" % k] for k in range(1, 5)):
                lost.append(LOST_GEAR_YES)
            if short == "WastebasketGear":
                lost.append(LOST_UPDAMAGE_TINY)
        elif "opt12" in has:
            row["Upcount"] = _int(_get(r, "Upcount"))
            row["Opidx1"], row["OpValue1"] = _int(_get(r, "Opidx1"), -1), _int(_get(r, "OpValue1"))
            row["Opidx2"], row["OpValue2"] = _int(_get(r, "Opidx2"), -1), _int(_get(r, "OpValue2"))
            lost.append(LOST_OPT12)
        else:
            lost.append(LOST_GEAR_NO)
    # количество: журнал (стопка / заряды / лот) или правило кода
    if "amount" in has:
        amount = _int(_get(r, "Amount"))
        if reg and reg[0] in ("ExchangeRegiFunctional",) and amount <= 0:
            amount = _int(_get(reg[1], "Amount"))
    else:
        amount = s["amount_each"]
        if s["kind"] == "quiver":
            lost.append("стрелы в колчане — полный колчан (в журнале количества нет)")
    if s["stack"] and amount < 1:
        raise OpRefused("в журнале нет количества стопки — вернуть нельзя")
    weight = s["unit_weight"] * (amount if s["stack"] else 1)
    for k in range(1, 5):
        c = row["Cell%d" % k]
        if c:
            cb = srvtables.cellob(c)
            if not cb:
                raise OpRefused("камня %s из гнезда %d нет в Cellob_Table сервера" % (c, k))
            weight += cb["weight"]
    if weight > WEIGHT_MAX:
        raise OpRefused("вес строки вышел бы за %d" % WEIGHT_MAX)
    cur_w, max_w = itemgive._weights(w, uid, idx, lock)
    # ★ ревизия 27 К-7: как GameServer (общая проверка веса GameServer.c:85371 «предел < текущий + вес» → отказ; отмена лота :109000
    #   «текущий + вес ≤ предел» → можно) — отказ только при превышении предела
    if cur_w + weight > max_w or cur_w + weight > WEIGHT_MAX:
        raise OpRefused("перегруз: вес %d + %d > предела %d" % (cur_w, weight, max_w))
    warn = []
    gold = None
    if "gold" in has:
        gm = _int(_get(r, "Gm"))
        if charge_gold and gm > 0:
            hint = " WITH (UPDLOCK, HOLDLOCK)" if lock else ""
            g = w.rows("SELECT Amount FROM Item%s WHERE Userindex = ? AND Charidx = ? AND Plate = 2 AND Code = ?" % hint, (uid, idx, GOLD_CODE))
            have = _int(g[0]["Amount"]) if g else 0
            if not g or have < gm:
                raise OpRefused("у персонажа нет золота продажи (нужно %d, есть %d) — снимите флажок «списать золото» или не возвращайте"
                                % (gm, have))
            gold = {"take": gm, "expect": have}
        elif gm > 0:
            warn.append("золото продажи (%d) НЕ списывается — игрок получит и золото, и предмет" % gm)
    if short == "DisassembleUse":
        warn.append(NOTE_DISASSEMBLE)
    if adm_after:
        warn.append("после события есть записи AdminitemLog с этим номером (%d) — проверьте след" % len(adm_after))
    born = next((e["at"] for e in tr["events"] if e["at"]), None)
    kind = feed.death_of(ent["name"], r)[0]
    where = items.PLATE_NAMES.get(plate, str(plate))
    text = "вернуть персонажу %s (%d/%d): %s (%d)%s — %s по журналу %s от %s → %s, ячейка %d%s" % (
        ch["Charname"], uid, idx, itemgive._name(code), code, (" × %d" % amount) if amount and (s["stack"] or s["kind"] == "function") else "",
        kind, short, at, where, free[0], ("; списать золото продажи %d" % gold["take"]) if gold else "")
    row.update(Amount=amount, Durability=s["dur"], Weight=weight, Owner=s["owner"])
    sig = {"uuid": serial, "code": code, "plate": plate, "posx": free[0], "amount": amount, "weight": weight,
           "gold": [gold["take"], gold["expect"]] if gold else None, "source": "%s | %s" % (short, at)}
    return {"uid": uid, "idx": idx, "code": code, "plate": plate, "posx": free[0], "cap": cap, "row": row, "gold": gold,
            "born": born, "text": text, "warnings": warn, "lost": lost, "sig": sig, "kind": kind}


def sources(serial):
    """Окно «вернуть»: события уничтожения номера, по каждому — можно ли вернуть (предпросмотр плана) или почему нет."""
    s = feed._norm_serial(serial)
    tr = feed.trace(s)
    out = []
    for e in tr["events"]:
        if not e.get("death"):
            continue
        rec = {"table": e["table"], "at": e["key"], "kind": e["death"], "recoverable": bool(e.get("recoverable")),
               "fields": e["fields"]}
        if e.get("recoverable"):
            try:
                with db.GameReader("joy1") as r:
                    ad = items._ReaderAdapter(r)
                    pl = plan_recover(ad, {"serial": s, "table": e["table"], "at": e["key"]}, trace_cache=_later_events(s, e["key"], tr))
                rec.update(text=pl["text"], lost=pl["lost"], warnings=pl["warnings"], gold=pl["gold"])
            except OpRefused as ex:
                rec.update(refused=str(ex))
            except db.DbError as ex:
                rec.update(refused="ошибка базы: %s" % ex)
        out.append(rec)
    return {"serial": s, "sources": out, "alive": tr["summary"]["alive"]}


@register
class ItemRecover(Operation):
    name, title, perm, reversible = "items.recover", "Предмет: вернуть удалённое по журналу", "players.items_give", True

    def target(self, p):
        return "item:%s" % (p.get("serial") or "")

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                ad = items._ReaderAdapter(r)
                pl = plan_recover(ad, p)
                ok, why = items.online_state(ad, pl["uid"])
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        if not ok:
            raise OpRefused("возвращать можно только когда игрок не в игре: " + why)
        return {"text": pl["text"], "expect": pl["sig"], "lost": pl["lost"],
                "warnings": pl["warnings"] + ["не восстановится: " + "; ".join(pl["lost"])]
                + ([items.RECENT_WARN] if items.recently_left(pl["uid"]) else [])}

    def apply(self, ctx, p, prev):
        # перед блокировками — номер «где сейчас» и события после источника (чтение журналов в транзакцию записи не входит)
        serial = feed._norm_serial(p.get("serial"))
        cache = _later_events(serial, str(p.get("at") or "").strip()[:23])
        w = db.GameWriter("joy1")
        try:
            # владелец предмета — из строки журнала (не из параметров): сначала «не в игре» под блокировкой, затем план под блокировкой
            src_ent, src_row, _reg = source_row(p.get("table"), serial, str(p.get("at") or "")[:23])
            ok, why = items.online_state(w, _int(_get(src_row, "Userindex")), lock=True)
            if not ok:
                raise OpRefused("возвращать можно только когда игрок не в игре: " + why)
            pl = plan_recover(w, p, lock=True, trace_cache=cache)
            if pl["sig"] != prev["expect"] or ("expect" in p and p["expect"] != pl["sig"]):
                raise OpRefused("пока вы смотрели предпросмотр, сумка или золото персонажа изменились — повторите")
            rw, g = pl["row"], pl["gold"] or {"take": 0, "expect": None}
            try:
                res = w.rows("EXEC adm.ItemRecover ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?",
                             (pl["uid"], pl["idx"], pl["plate"], pl["posx"], pl["cap"], serial, pl["code"], rw["Amount"], rw["Durability"],
                              rw["Weight"], rw["Cell1"], rw["Cell2"], rw["Cell3"], rw["Cell4"], rw["Upcount"], rw["AcuUpcnt"], rw["MaxupCnt"],
                              rw["Updamage"], rw["Opidx1"], rw["OpValue1"], rw["Opidx2"], rw["OpValue2"], rw["Opidx3"], rw["Opvalue3"],
                              rw["Opidx4"], rw["Opvalue4"], rw["OPidx5"], rw["Opvalue5"], rw["Owner"], pl["born"], pl["sig"]["source"][:80],
                              g["take"], g["expect"], ("panel:%s" % (ctx.login or ""))[:64]))
            except db.DbError as ex:
                raise itemgive._refuse_db(ex, "adm.ItemRecover")
            if not res:
                raise OpRefused("процедура возврата не ответила — ничего не записано")
            lid = int(res[0]["LedgerId"])
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"serial": serial, "source": pl["sig"]["source"], "gold": pl["gold"]},
                "after": {"uid": pl["uid"], "idx": pl["idx"], "code": pl["code"], "plate": pl["plate"], "posx": pl["posx"],
                          "serial": serial, "ledger": [lid], "lost": pl["lost"]},
                "message": pl["text"], "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        return itemgive._undo_ledger(ctx, a, "возврат предмета откачен")
