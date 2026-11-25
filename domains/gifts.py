# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""gifts.py — подарок позиции витрины и премиум-почта в элитный почтовый ящик (волна А1, план §4.В «премиум-почта одному /
учётке / всем; подарок из витрин»; перенос вкладки «Подарки» и команды send-post старой утилиты AstoryAdminCenter/tools/Admin —
asda_gifts.py, asda_give.post_spec/postbox_write). 18.11.2026.

ЧТО ПОЛУЧИТ ИГРОК — то же, что при покупке (разбор и доказательства — шапка asda_gifts.py, Reports/cash_gift/re/billing.md):
  подарок (kind gift) — позиция витрин 6000/15300 (каталог data/ref/gift_catalog.json — тот же, что у старой утилиты):
    проверки покупки 5070 CharChargeShopBuy@0x511DA0 — код в SellItemTable (иначе 14); item_list — item_table t24 ∈ {0, 3};
    функциональный — своя ветка; шлюз gp7 resolvePremiumItem — код выдачи из premium_item_map.json, иначе сам код; код выдачи
    вне item_list — шлюз отказывает (такая позиция не продаётся и не дарится); функциональный товар — только коробкой;
    строки ящика как у UPCashitemBuy: штука = строка Amount 1, iType = тип покупки (1 «Shell Item» / 0 «Functional Item»),
    до 7 штук под одним Orderidx (строка окна ящика);
  премиум-почта (kind mail) — любой код (как send-post): строка iType 1, Amount = копий (≤ 7 в строке).
  Забор игрок делает сам (окно 69000, 11006): ячейку выбирает сервер — поэтому ВЫДАВАТЬ можно при запущенном сервере и игроку
  в игре. Стопочный — только при P98 на всех GS (иначе придёт количество 0); колчан/наживка — отказ (придут пустыми).
ЗАПИСЬ — asda_ops: SELECT/INSERT/DELETE dbo.ItemPostBox (куча без индексов). Номер заказа — наименьший свободный у персонажа под
  замком приложения sp_getapplock «AsdaAdmin.ItemPostBox.Orders» (тот же, что у старой утилиты; покупки и забор его не берут).
  Получатели: персонаж | все персонажи учётки | все игроки (учётки > 5000, без блока). ОТКАТ — удаление ровно этих строк, только
  пока подарок не забран и ТОЛЬКО когда получатели не в игре (забор идёт при игроке в игре — удаление «под ним» дало бы гонку).
Побочных эффектов при импорте нет.
"""
import json
import os

from core import db
from core.ops import Operation, OpRefused, register
from domains import itemgive, items, refdata, srvtables

CATALOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ref", "gift_catalog.json")
SELL_TABLE = r"GameServer\ItemTable_Info\SellItemTable.txt"
PACKAGE_TABLE = r"GameServer\ItemTable_Info\PackageItem_Table.txt"
PREMIUM_MAP = r"gp7-server\premium_item_map.json"
ITEM_LIST_LO = 20551
BUY_SHELL, BUY_FUNC = 1, 0
PER_ORDER = 7                     # штук в одном заказе — строка окна ящика (клиент рисует ≤ 7)
MAX_QTY = 60                      # больше не поместится ни в одну сумку
APPLOCK = "AsdaAdmin.ItemPostBox.Orders"
BANNED = os.path.join(os.path.dirname(CATALOG), "banned_players.md")   # копия AstoryAdminCenter/DiscordBot/BANNED_PLAYERS.md (кладёт выкладка)
INSERT_ROWS = 300                 # строк в одном INSERT (6 параметров на строку, предел SQL Server — 2100)
OPERATOR_MAX_UID = 5000
_cat = {}


def catalog():
    if "c" not in _cat:
        with open(CATALOG, encoding="utf-8") as f:
            _cat["c"] = json.load(f)
    return _cat["c"]


def catalog_rows(text="", limit=60):
    """Позиции витрин по части названия RU/EN или коду: [{code, name, places, hidden, icon}]."""
    from core import i18n
    cat, t, out, seen = catalog(), (text or "").strip().lower(), [], set()
    for r in cat["rows"]:
        k = str(r["code"])
        it = cat["items"][k]
        if t and not (t == k or t in it["name_ru"].lower() or t in it["name_en"].lower()):
            continue
        if k in seen:
            continue
        seen.add(k)
        places = [x for x in cat["rows"] if str(x["code"]) == k]
        out.append({"code": r["code"], "name": (it["name_en"] or it["name_ru"]) if i18n.is_en() else (it["name_ru"] or it["name_en"]),
                    "places": [{"shop": x["shop"], "path": x["path_en"] if i18n.is_en() else x["path_ru"], "hidden": bool(x["hidden"])}
                               for x in places],
                    "hidden": all(x["hidden"] for x in places), "icon": refdata.item(r["code"])["icon"]})
        if len(out) >= limit:
            break
    return out


class Rules:
    """Живые данные стойки для зеркала покупки (как asda_gifts.ServerRules, источники — с диска сервера)."""

    def __init__(self):
        self.it = srvtables.table("Item_Table.txt")
        self.fn = srvtables.table("Function_Table.txt")
        self.it_max = srvtables.table_max("Item_Table.txt")             # sub_532A90: 20551…счёт+20550
        sell = srvtables.stack_text(SELL_TABLE).split()
        self.sell_max = int(sell[0])                                     # заголовок «макс_код  число» (GameServer.c:68424)
        self.sell = {int(x) for x in sell[2:] if x.lstrip("-").isdigit()}
        self.pkg = {}
        for ln in srvtables.stack_text(PACKAGE_TABLE).splitlines()[1:]:
            t = ln.split()
            if len(t) >= 3 and t[0].isdigit():
                self.pkg[int(t[0])] = [(int(t[i]), int(t[i + 1])) for i in range(1, len(t) - 1, 2)
                                       if t[i].lstrip("-").isdigit() and t[i + 1].lstrip("-").isdigit() and int(t[i]) > 0]
        src = json.loads(srvtables.stack_text(PREMIUM_MAP).lstrip("﻿"))
        self.pmap = {}
        for k, v in src.items():
            v = v if isinstance(v, dict) else {"deliveryItemCode": v}
            self.pmap[int(k)] = (int(v["deliveryItemCode"]), int(v.get("price", -1)))
        self.p98 = srvtables.patch_on_all("P98_PremiumStackAmount")
        self.p100 = srvtables.patch_on_all("P100_ChargeStack")

    def is_item(self, code):
        return ITEM_LIST_LO <= code <= self.it_max

    def is_func(self, code):
        return code <= 558 or code in self.fn           # isFunctionItem шлюза gp7 (server.js) — 558 у шлюза буквально

    def box_contents(self, code):
        f = self.it.get(code)
        if not f or srvtables._i(f, 16) != 11 or srvtables._i(f, 17) != 200:
            return []
        return self.pkg.get(srvtables._i(f, 39), [])

    def landing(self, delivery, notes):
        """Как код выдачи ляжет при заборе из ящика (sub_5340B0 + P98). → spec или OpRefused."""
        s = itemgive.item_spec(delivery)
        if s["kind"] == "quiver":
            raise OpRefused("колчан/наживка при заборе из ящика приходят пустыми — выдайте кнопкой «Выдать предмет»")
        if s["stack"]:
            off = [k for k, v in self.p98.items() if not v]
            if off:
                raise OpRefused("стопочный предмет без P98_PremiumStackAmount (выключен на %s) придёт с количеством 0 — "
                                "выдайте кнопкой «Выдать предмет»" % ", ".join(off))
            notes.append("стопочный: каждая штука придёт отдельной стопкой из 1 шт. (P98 включён на всех GS)")
        return s

    def offer(self, code):
        """Подарок позиции витрины → dict(code, delivery, price, buy_type, contents, notes) или OpRefused."""
        code = int(code)
        if str(code) not in catalog()["items"]:
            raise OpRefused("кода %d нет на витринах 6000/15300 — подарить можно только позицию магазина" % code)
        if code > self.sell_max or code not in self.sell:
            raise OpRefused("кода нет в SellItemTable сервера — магазин его не продаёт (ответ 5071 код 14)")
        if self.is_item(code):
            f = self.it.get(code)
            if not f:
                raise OpRefused("кода нет в item_table сервера")
            if srvtables._i(f, 24) not in (0, 3):
                raise OpRefused("item_table ток.24 = %d (не 0/3) — сервер отказывает в покупке (5071 код 0)" % srvtables._i(f, 24))
            bt = BUY_SHELL
        elif self.is_func(code) and code in self.fn:
            bt = BUY_FUNC
        else:
            raise OpRefused("код вне item_list и Function_Table сервера — витрина его не продаёт")
        if code in self.pmap:
            dlv, price = self.pmap[code]
        elif self.is_func(code):
            dlv, price = code, srvtables._i(self.fn[code], 20)
        else:
            dlv, price = code, srvtables._i(self.it[code], 26)
        if not self.is_item(dlv):
            raise OpRefused("шлюз gp7 не выдаёт код %d (вне item_list) — в магазине эта позиция не продаётся" % dlv)
        contents = self.box_contents(dlv)
        if bt == BUY_FUNC and dlv != code and not contents:
            raise OpRefused("карта шлюза выдаёт за код %d предмет %d — не коробку с ним (расхождение данных магазина)" % (code, dlv))
        notes = []
        self.landing(dlv, notes)
        if contents:
            notes.append("коробка: игрок откроет её как купленную (состав — PackageItem_Table сервера)")
            charged = [c for c, _ in contents if c in self.fn and srvtables._i(self.fn[c], 8) == 2
                       and srvtables._i(self.fn[c], 9) > 0 and srvtables._i(self.fn[c], 25) == 0]
            if charged:
                notes.append(("спецпредмет с зарядами: заряды сложит с лежащим сервер (P100 включён на всех GS)"
                              if all(self.p100.values()) else "спецпредмет с зарядами: P100 включён не на всех GS — придёт "
                              "отдельной ячейкой, как при покупке"))
        return {"code": code, "delivery": dlv, "price": price, "buy_type": bt, "contents": contents, "notes": notes}


def describe(kind, code):
    """Что получит игрок (окно подарка / премиум-почты)."""
    r = Rules()
    code = int(code)
    if kind == "gift":
        o = r.offer(code)
    elif kind == "mail":
        notes = []
        r.landing(code, notes)
        o = {"code": code, "delivery": code, "price": None, "buy_type": BUY_SHELL, "contents": [], "notes": notes}
    else:
        raise OpRefused("неверный вид отправки")
    o["name"] = refdata.item(o["delivery"])["name"] or itemgive._name(o["delivery"])
    o["contents"] = [{"code": c, "n": n, "name": refdata.item(c)["name"] or itemgive._name(c)} for c, n in o["contents"]]
    return o


def banned():
    """{Userindex: логин} из реестра банов (строки markdown-таблиц, как asda_give.banned_accounts) или None — копии нет."""
    # на ПК (самотест) — сам реестр, если копии нет; ★ 25.11 (С-3, М-2): от корня клона (data/ref → корень), а не по имени папки
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(CATALOG))), "DiscordBot", "BANNED_PLAYERS.md")
    try:
        lines = open(BANNED if os.path.exists(BANNED) else src, encoding="utf-8").read().splitlines()
    except OSError:
        return None
    out, cols = {}, None
    for ln in lines:
        if not ln.strip().startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if "Userindex" in cells and "Игровой логин" in cells:
            cols = (cells.index("Userindex"), cells.index("Игровой логин"))
        elif cols and len(cells) > cols[0] and cells[cols[0]].isdigit():
            out[int(cells[cols[0]])] = cells[cols[1]] if len(cells) > cols[1] else ""
    return out


def _targets(w, p, role):
    """Получатели → [{uid, idx, name}]."""
    mode = p.get("to") or "char"
    try:
        if mode == "char":
            uid, idx = int(p["uid"]), int(p["idx"])
            rows = w.rows("SELECT Userindex, Charidx, Charname FROM Charinfo WHERE Userindex = ? AND Charidx = ?", (uid, idx))
        elif mode == "account":
            uid = int(p["uid"])
            rows = w.rows("SELECT Userindex, Charidx, Charname FROM Charinfo WHERE Userindex = ? ORDER BY Charidx", (uid,))
        elif mode == "all":
            uid = None
            rows = w.rows("SELECT c.Userindex, c.Charidx, c.Charname FROM Charinfo c JOIN AsdaStoryOp.dbo.Us_member m "
                          "ON m.Userindex = c.Userindex WHERE c.Userindex > ? AND m.us_block = 0 ORDER BY c.Userindex, c.Charidx",
                          (OPERATOR_MAX_UID,))
        else:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise OpRefused("неверные параметры отправки")
    if uid is not None and uid <= OPERATOR_MAX_UID and role != "owner":
        raise OpRefused("служебные учётки (номер ≤ %d) правит только владелец" % OPERATOR_MAX_UID)
    tg = [{"uid": int(r["Userindex"]), "idx": int(r["Charidx"]), "name": r["Charname"]} for r in rows]
    # перепроверка 19 М1: реестр банов (как старая утилита, split_banned): «всем» — забаненные исключаются, иначе — предупреждение
    ban, warn = banned(), []
    if ban is None:
        if mode == "all":
            raise OpRefused("нет копии реестра банов на сервере — «всем игрокам» не отправляется (создайте DiscordBot/BANNED_PLAYERS.md "
                            "по образцу BANNED_PLAYERS.example.md, пустая таблица — банов нет, и выложите панель заново)")
        warn.append("копии реестра банов на сервере нет — проверка бана не выполнена")
    else:
        hit = sorted({t["uid"] for t in tg if t["uid"] in ban})
        if mode == "all":
            tg = [t for t in tg if t["uid"] not in ban]
            if hit:
                warn.append("исключено по реестру банов: учёток %d" % len(hit))
        elif hit:
            warn.append("учётка в реестре банов — отправка по явному выбору")
    if not tg:
        raise OpRefused("получателей нет")
    return mode, tg, warn


def plan(w, p, role=None):
    kind = p.get("kind") or "gift"
    try:
        code, qty = int(p["code"]), int(str(p.get("qty", 1)).strip())
    except (KeyError, TypeError, ValueError):
        raise OpRefused("код и количество — целые числа")
    if not 1 <= qty <= MAX_QTY:
        raise OpRefused("количество — от 1 до %d (каждая штука займёт ячейку сумки)" % MAX_QTY)
    try:
        o = describe(kind, code)
    except OpRefused:
        raise
    except Exception as ex:
        raise OpRefused("таблицы сервера не прочитаны: %s" % ex)
    mode, tg, twarn = _targets(w, p, role)
    chunks = [min(PER_ORDER, qty - i) for i in range(0, qty, PER_ORDER)]
    # строки заказа: подарок — штука = строка Amount 1 (UPCashitemBuy premrows); почта — одна строка Amount = копий (send-post)
    # перепроверка 19 В1: списки, не кортежи — отпечаток возвращается из браузера через JSON и сравнивается как есть
    orders = [[[o["buy_type"], o["delivery"], 1] for _ in range(c)] if kind == "gift" else [[BUY_SHELL, o["delivery"], c]] for c in chunks]
    who = ("персонаж " + tg[0]["name"] + " (%d/%d)" % (tg[0]["uid"], tg[0]["idx"])) if mode == "char" else (
        "все персонажи учётки %d (%d)" % (tg[0]["uid"], len(tg)) if mode == "account" else "все игроки (%d персонажей)" % len(tg))
    text = "%s: %s (%d) × %d → элитный почтовый ящик: %s" % (
        "подарок" if kind == "gift" else "премиум-почта", o["name"], o["delivery"], qty, who)
    warn = list(o["notes"]) + twarn
    if kind == "gift" and o["delivery"] != code:
        warn.append("в ящик ляжет код выдачи шлюза %d (за позицию витрины %d)" % (o["delivery"], code))
    warn.append("игрок заберёт сам из ящика; пока не забрал — можно откатить (когда получатели не в игре)")
    sig = {"kind": kind, "code": code, "delivery": o["delivery"], "qty": qty, "orders": orders,
           "targets": [[t["uid"], t["idx"]] for t in tg]}
    return {"o": o, "targets": tg, "orders": orders, "text": text, "warnings": warn, "sig": sig, "mode": mode}


def _free_orders(used, need):
    out, n = [], 1
    while len(out) < need:
        if n not in used:
            out.append(n)
        n += 1
    return out


def _reused_check(row, sent):
    """Перепроверка 19 В2: номер заказа — наименьший свободный, поэтому после забора подарка тот же номер получает следующая
    отправка панели. Если более поздняя (не откаченная) отправка взяла номер этого заказа у того же персонажа — наш заказ уже
    забран, а строки с этим номером чужие: откат отказывает, чтобы не удалить чужой подарок."""
    from core import audit
    mine = {(s["uid"], s["idx"], r[1]) for s in sent for r in s["rows"]}
    for a in audit.query(action_prefix="items.post", limit=1000):
        if int(a["id"]) <= int(row["id"]) or a.get("result") != "ok" or a.get("undone_by"):
            continue
        try:
            later = json.loads(a.get("after_json") or "{}").get("sent") or []
        except ValueError:
            continue
        if any((s["uid"], s["idx"], r[1]) in mine for s in later for r in s.get("rows", [])):
            raise OpRefused("заказ уже забран, и его номер заняла более поздняя отправка (журнал №%s) — откат не выполнен" % a["id"])


@register
class PostSend(Operation):
    name, title, perm, reversible = "items.post", "Предмет: подарок / премиум-почта в ящик", "players.items_give", True

    def target(self, p):
        to = p.get("to") or "char"
        return {"char": "char:%s/%s" % (p.get("uid"), p.get("idx")), "account": "account:%s" % p.get("uid")}.get(to, "all")

    def preview(self, ctx, p):
        try:
            with db.GameReader("joy1") as r:
                pl = plan(items._ReaderAdapter(r), p, role=ctx.role)
        except db.DbError as ex:
            raise OpRefused("ошибка базы: %s" % ex)
        return {"text": pl["text"], "expect": pl["sig"], "warnings": pl["warnings"], "count": len(pl["targets"])}

    def apply(self, ctx, p, prev):
        w = db.GameWriter("joy1")
        try:
            pl = plan(w, p, role=ctx.role)
            if pl["sig"] != prev["expect"] or ("expect" in p and p["expect"] != pl["sig"]):
                raise OpRefused("пока вы смотрели предпросмотр, получатели или правила магазина изменились — повторите")
            rc = w.rows("DECLARE @rc INT; EXEC @rc = sp_getapplock @Resource = ?, @LockMode = 'Exclusive', "
                        "@LockOwner = 'Transaction', @LockTimeout = 15000; SELECT @rc AS rc", (APPLOCK,))
            if not rc or int(rc[0]["rc"]) < 0:
                raise OpRefused("замок выдачи в ящик не получен — другая выдача идёт слишком долго")
            # перепроверка 19 М2: номера заказов — одним чтением, строки — пачками INSERT (транзакция короткая: забор из ящика
            # у других игроков сканирует ту же кучу и ждёт её конца)
            if pl["mode"] == "all":
                got = w.rows("SELECT Userindex, Charidx, Orderidx FROM dbo.ItemPostBox")
            else:
                got = w.rows("SELECT Userindex, Charidx, Orderidx FROM dbo.ItemPostBox WHERE Userindex = ?", (pl["targets"][0]["uid"],))
            used = {}
            for r in got:
                used.setdefault((int(r["Userindex"]), int(r["Charidx"])), set()).add(int(r["Orderidx"]))
            done, flat = [], []
            for t in pl["targets"]:
                nums = _free_orders(used.get((t["uid"], t["idx"]), set()), len(pl["orders"]))
                rows = [[it, n, code, amt] for n, rows_ in zip(nums, pl["orders"]) for it, code, amt in rows_]
                done.append({"uid": t["uid"], "idx": t["idx"], "rows": rows})
                flat += [(it, n, t["uid"], t["idx"], code, amt) for it, n, code, amt in rows]
            for i in range(0, len(flat), INSERT_ROWS):
                part = flat[i:i + INSERT_ROWS]
                if w.execute("INSERT INTO dbo.ItemPostBox (iType, Orderidx, Userindex, Charidx, Code, Amount) VALUES "
                             + ", ".join(["(?, ?, ?, ?, ?, ?)"] * len(part)), [v for r in part for v in r]) != len(part):
                    raise OpRefused("вставлено не то, что ожидалось — ничего не записано")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"kind": pl["sig"]["kind"], "code": pl["sig"]["code"], "qty": pl["sig"]["qty"]},
                "after": {"sent": done, "delivery": pl["o"]["delivery"]}, "message": pl["text"],
                "_commit": w.commit, "_close": w.close}

    def undo(self, ctx, row):
        a = json.loads(row["after_json"] or "{}")
        sent = a.get("sent") or []
        if not sent:
            raise OpRefused("в журнале нет данных для отката")
        _reused_check(row, sent)
        w = db.GameWriter("joy1")
        try:
            for uid in sorted({s["uid"] for s in sent}):
                ok, why = items.online_state(w, uid, lock=True)
                if not ok:
                    raise OpRefused("откат только когда получатели не в игре: " + why)
            for s in sent:
                by = {}
                for it, n, code, amt in s["rows"]:
                    by.setdefault((it, n, code, amt), 0)
                    by[(it, n, code, amt)] += 1
                for (it, n, code, amt), cnt in by.items():
                    have = w.rows("SELECT COUNT(*) AS c FROM dbo.ItemPostBox WHERE Userindex = ? AND Charidx = ? AND Orderidx = ? "
                                  "AND iType = ? AND Code = ? AND Amount = ?", (s["uid"], s["idx"], n, it, code, amt))[0]["c"]
                    if int(have) != cnt:
                        raise OpRefused("подарок персонажу %s/%s уже забран (целиком или частично) — откат не выполнен" % (s["uid"], s["idx"]))
                    if w.execute("DELETE FROM dbo.ItemPostBox WHERE Userindex = ? AND Charidx = ? AND Orderidx = ? AND iType = ? "
                                 "AND Code = ? AND Amount = ?", (s["uid"], s["idx"], n, it, code, amt)) != cnt:
                        raise OpRefused("ящик изменился при откате — ничего не удалено")
        except db.DbError as ex:
            w.close()
            raise OpRefused("ошибка базы: %s" % ex)
        except BaseException:
            w.close()
            raise
        return {"before": {"sent": sent}, "after": {"removed": len(sent)}, "message": "отправка в ящик откачена",
                "_commit": w.commit, "_close": w.close}
