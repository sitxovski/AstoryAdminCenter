# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""asda_gifts.py — вкладка «Подарки» утилиты учёток: подарок игроку любой позиции витрин премиум-магазина (окно 6000)
и магазина бустеров (15300) — бесплатно, без списания и без шлюза gp7. 01.11.2026.

Часть утилиты asda_accounts.py (вкладка «Подарки», консольные команды gift / gift-catalog, самотест). Получатели, правила
предметов, копии таблиц сервера по SSH и запись в ящик переиспользуются из asda_give.py (вкладка «Выдача»).

КАТАЛОГ (что можно подарить) — ровно строки витрин клиента:
  data/gift_catalog.json + data/icons/*.png — строит asda_gift_catalog_build.py из источников DataTable порта
  (PremiumShopBin.json / BoosterShopList.json, названия RU/EN, иконки — правилом клиента GetItemIcon).

ЧТО ПОЛУЧИТ ИГРОК — то же, что при покупке этой позиции (зеркало сервера, по ЖИВЫМ файлам стойки, копии по SSH):
  * проверки покупки 5070 CharChargeShopBuy@0x511DA0 (GameServer.c:104590–104829): код в SellItemTable.txt (иначе
    сервер отвечает 14); item_list (20551…20550+счёт item_table) — байт +36 записи = item_table ток.24 ∈ {0, 3} (иначе 0);
    функциональный код (есть в Function_Table) — своя ветка; самоцветы витрина не продаёт;
  * шлюз gp7 resolvePremiumItem (gp7-server/server.js:254): код выдачи и цена — строка premium_item_map.json, иначе
    функциональный — свой код по цене FT ток.20, иначе item_table ток.26; код выдачи вне item_list → шлюз отказывает
    (undeliverable-item-code) — такая позиция в магазине не продаётся, подарить её тоже нельзя;
  * доставка покупки — DB 2601 UPCashitemBuy → строки Joy1.dbo.ItemPostBox (разбор Reports/cash_gift/re/billing.md
    §1.5): iType = тип покупки (1 «Shell Item» — каталожный код item_list, 0 «Functional Item» — функциональный, GS
    v34 в CharChargeShopBuy), Code = код выдачи (коробка/набор — сам ящик-коробка, игрок откроет его как купленную),
    Amount 1 на штуку, штуки одного заказа — один Orderidx (корзина premrows, ≤ 7 строк = строка окна ящика).
  * Забор игрок делает сам (окно 69000, 11006): ячейку выбирает сервер по своей памяти — поэтому дарить можно при
    ЗАПУЩЕННОМ сервере и игрокам в игре. Стопочный item_list: с P98 на всех GS — стопка из 1 шт. в каждой ячейке
    (без P98 — отказ: пришло бы Amount 0); колчан/наживка — отказ (забор даёт пустой, P98 их не трогает). Заряды
    спецпредметов складывает при заборе сервер, если на нём включён P100 (утилита сама в Item ничего не пишет).
  * Подписи отправителя у ящика НЕТ: в ItemPostBox столбцы только iType, Orderidx, Userindex, Charidx, Code, Amount,
    запись 11005 клиенту — Order, ItemIndex, Count, BuyType (AsdaPremiumPostSubsystem.cpp); имя дарителя оригинал
    передаёт только в подарке 5076/5078 (окно 6000, путь P101 — ещё не выложен).

КАНАЛ ДОСТАВКИ — расширяемая точка: CHANNELS (ключ → объект с title / deliver()). Работающий канал сейчас один —
  «postbox» (элитный почтовый ящик). Подарок P101 (5076/5078 с именем дарителя) добавляется новым классом в CHANNELS.

ЖУРНАЛ ВЫДАЧ — logs/gifts.tsv (UTF-8, TAB): время, кто (учётка Windows@машина), канал, получатель (персонаж, учётка,
  Userindex/Charidx), каталожный код, код выдачи, название, штук, iType, номера заказов, итог. «Проверка» (--dry) в журнал
  не пишется. Строка дублируется в общий logs/accounts.log. Пароли нигде не участвуют.
Побочных эффектов при импорте нет (закон tools-no-import-side-effects).
"""
import datetime
import getpass
import json
import os
import platform

import asda_give as G

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_JSON = os.path.join(HERE, "data", "gift_catalog.json")   # витрина (asda_gift_catalog_build.py)
ICON_ROOT = os.path.join(HERE, "data")                           # корень относительных путей иконок каталога
JOURNAL = os.path.join(HERE, "logs", "gifts.tsv")                # журнал подарков
PREMIUM_MAP = "gp7-server/premium_item_map.json"                 # карта шлюза (от корня стойки)
SELL_TABLE = "SellItemTable.txt"                                 # белый список покупки 5070 (ItemTable_Info)
PACKAGE_TABLE = "PackageItem_Table.txt"                          # состав коробок (ItemTable_Info)
ITEM_LIST_LO = 20551                                             # первый код item_list (sub_532A90)
BUY_TYPE_SHELL, BUY_TYPE_FUNC = 1, 0                             # iType покупки: «Shell Item» / «Functional Item»
MAX_QTY = G.POST_MAX_QTY                                         # штук за раз одному персонажу (ячеек сумки)
PER_ORDER = G.POST_MAX_PER_ROW                                   # штук в одном заказе (строка окна ящика)
JOURNAL_HEAD = ("время", "кто", "канал", "персонаж", "учётка", "Userindex", "Charidx", "код", "код выдачи", "название",
                "штук", "iType", "заказы", "итог")


class GiftError(G.GiveError):
    """Отказ подарка с понятной причиной."""


# ═════════════════════════════ каталог ═════════════════════════════

_CATALOG = None   # кэш каталога на процесс


def load_catalog():
    """Каталог витрин (dict из gift_catalog.json). Нет файла — GiftError с подсказкой."""
    global _CATALOG
    if _CATALOG is None:
        if not os.path.exists(CATALOG_JSON):
            raise GiftError("нет каталога %s — запустите asda_gift_catalog_build.py" % CATALOG_JSON)
        with open(CATALOG_JSON, encoding="utf-8") as f:
            _CATALOG = json.load(f)
    return _CATALOG


def catalog_rows(text="", shops=(6000, 15300), with_hidden=True):
    """Позиции витрины (одна на код, в порядке витрин): [dict(code, name_ru, name_en, icon, places[...], hidden)].
    text — часть названия RU/EN или код."""
    cat = load_catalog()
    t = (text or "").strip().lower()
    by_code, order = {}, []
    for r in cat["rows"]:
        if r["shop"] not in shops or (r["hidden"] and not with_hidden):
            continue
        k = str(r["code"])
        it = cat["items"][k]
        if t and not (t == k or t in it["name_ru"].lower() or t in it["name_en"].lower()):
            continue
        if k not in by_code:
            by_code[k] = dict(code=r["code"], name_ru=it["name_ru"], name_en=it["name_en"], icon=it["icon"],
                              places=[], hidden=True)
            order.append(k)
        by_code[k]["places"].append(dict(shop=r["shop"], path_ru=r["path_ru"], path_en=r["path_en"], hidden=r["hidden"]))
        by_code[k]["hidden"] &= bool(r["hidden"])
    return [by_code[k] for k in order]


def icon_path(code):
    """Абсолютный путь PNG иконки кода витрины или None."""
    it = load_catalog()["items"].get(str(code))
    return os.path.join(ICON_ROOT, it["icon"]) if it and it.get("icon") else None


# ═════════════════════════════ правила сервера (покупка 5070 + шлюз gp7) ═════════════════════════════

_RULES = None   # кэш правил на процесс (строится и обновляется под G.SRV_LOCK — потоки окна)


class ServerRules:
    """Живые данные стойки для зеркала покупки: item_table, Function_Table, SellItemTable, PackageItem_Table,
    premium_item_map.json шлюза, состояние P98/P100 в patches.ini трёх GS."""

    def __init__(self):
        self.it = G._read_table("Item_Table.txt")
        self.fn = G._read_table("Function_Table.txt")
        raw = open(G.srv_file(G.SRV_TABLES + "/Item_Table.txt"), "rb").read(64).decode("latin1")
        self.it_max = 20550 + int(raw.split()[0])                 # sub_532A90 / isDeliverableItemCode: 20551…счёт+20550
        sell = open(G.srv_file(G.SRV_TABLES + "/" + SELL_TABLE), "rb").read().decode("latin1").split()
        self.sell_max = int(sell[0])                               # заголовок «макс_код  число» (GameServer.c:68424)
        self.sell = {int(x) for x in sell[2:] if x.lstrip("-").isdigit()}
        self.pkg = {}                                              # строка PackageItem_Table → [(код, штук)]
        for ln in open(G.srv_file(G.SRV_TABLES + "/" + PACKAGE_TABLE), "rb").read().decode("latin1").splitlines()[1:]:
            t = ln.split()
            if len(t) >= 3 and t[0].isdigit():
                self.pkg[int(t[0])] = [(int(t[i]), int(t[i + 1])) for i in range(1, len(t) - 1, 2)
                                       if t[i].lstrip("-").isdigit() and t[i + 1].lstrip("-").isdigit() and int(t[i]) > 0]
        self.load_volatile()

    def load_volatile(self):
        """Часто меняемое: карта шлюза premium_item_map.json и включённость P98/P100 (patches.ini трёх GS).
        Перечитывается перед каждой настоящей выдачей (ревизия п.5) и кнопкой «Обновить правила сервера»."""
        with open(G.srv_file(PREMIUM_MAP), encoding="utf-8-sig") as f:
            src = json.load(f)
        pmap = {}                                                  # каталожный код → (код выдачи, цена) — как loadPremiumItemMap
        for k, v in src.items():
            v = v if isinstance(v, dict) else {"deliveryItemCode": v}
            pmap[int(k)] = (int(v["deliveryItemCode"]), int(v.get("price", -1)))
        self.pmap = pmap
        self.p98 = G.patch_enabled("P98_PremiumStackAmount")
        self.p100 = G.patch_enabled("P100_ChargeStack")

    def is_item(self, code):
        """Код item_list сервера (sub_532A90)."""
        return ITEM_LIST_LO <= code <= self.it_max

    def is_func(self, code):
        """Функциональный код (isFunctionItem шлюза: ≤ 558 или есть в Function_Table)."""
        return code <= 558 or code in self.fn

    def box_contents(self, code):
        """Состав коробки (item_table ток.16 = 11, ток.17 = 200 → строка PackageItem_Table ток.39) или []."""
        f = self.it.get(code)
        if not f or G._int(f, 16) != 11 or G._int(f, 17) != 200:
            return []
        return self.pkg.get(G._int(f, 39), [])

    def offer(self, code):
        """Что получит игрок за позицию витрины. → dict(code, delivery, price, buy_type, spec, contents, ok, why, notes)."""
        o = dict(code=code, delivery=0, price=None, buy_type=None, spec=None, contents=[], ok=False, why="", notes=[])
        # 1) GameServer CharChargeShopBuy: белый список и ветка таблицы.
        if code > self.sell_max or code not in self.sell:
            o["why"] = "кода нет в SellItemTable сервера — магазин его не продаёт (ответ 5071 код 14)"
            return o
        if self.is_item(code):
            f = self.it.get(code)
            if not f:
                o["why"] = "кода нет в item_table сервера"
                return o
            if G._int(f, 24) not in (0, 3):
                o["why"] = "item_table ток.24 = %d (не 0/3) — сервер отказывает в покупке (5071 код 0)" % G._int(f, 24)
                return o
            o["buy_type"] = BUY_TYPE_SHELL
        elif self.is_func(code) and code in self.fn:
            o["buy_type"] = BUY_TYPE_FUNC
        else:
            o["why"] = "код вне item_list и Function_Table сервера — витрина его не продаёт"
            return o
        # 2) Шлюз gp7 resolvePremiumItem: код выдачи и цена.
        if code in self.pmap:
            o["delivery"], o["price"] = self.pmap[code]
        elif self.is_func(code):
            o["delivery"], o["price"] = code, G._int(self.fn[code], 20)
        else:
            o["delivery"], o["price"] = code, G._int(self.it[code], 26)
        if not self.is_item(o["delivery"]):
            o["why"] = ("шлюз gp7 не выдаёт код %d (вне item_list, undeliverable-item-code) — в магазине эта позиция не "
                        "продаётся" % o["delivery"])
            return o
        if o["buy_type"] == BUY_TYPE_FUNC and o["delivery"] != code and not self.box_contents(o["delivery"]):
            # Функциональный товар оригинал продаёт КОРОБКОЙ (item_table 11/200 → PackageItem_Table, server.js:136).
            #   Строка карты шлюза, ведущая не на коробку, выдала бы другой предмет — расхождение данных, не дарим.
            o["why"] = ("карта шлюза premium_item_map.json выдаёт за код %d предмет %d «%s» — не коробку с ним "
                        "(расхождение данных магазина; подарок отклонён, чтобы игрок не получил чужой предмет)"
                        % (code, o["delivery"], G.item_name(o["delivery"])))
            return o
        return self.landing(o)

    def landing(self, o):
        """Шаг 3 offer(): как код выдачи ляжет при заборе из ящика (правила sub_5340B0 + P98). Отдельно — для самотеста."""
        try:
            s = G.item_spec(o["delivery"])
        except G.GiveError as ex:
            o["why"] = "код выдачи %d: %s" % (o["delivery"], ex)
            return o
        o["spec"] = s
        o["contents"] = self.box_contents(o["delivery"])
        if s["kind"] == "quiver":
            o["why"] = ("колчан/наживка: при заборе из ящика сервер кладёт его пустым (Amount 0; P98 тип 10 не трогает) — "
                        "подарить нельзя, выдайте вкладкой «Выдача» кнопкой «Выдать предмет» при выключенном сервере")
            return o
        if s["stack"]:
            if not all(self.p98.values()):
                off = ", ".join(k for k, v in self.p98.items() if not v)
                o["why"] = ("стопочный предмет: без P98_PremiumStackAmount (выключен на %s) забор из ящика даёт количество "
                            "0 — подарить нельзя, выдайте вкладкой «Выдача»" % off)
                return o
            o["notes"].append("стопочный: каждая штука придёт отдельной стопкой из 1 шт. (P98 включён на всех GS)")
        if o["contents"]:
            o["notes"].append("коробка: игрок откроет её как купленную (состав — PackageItem_Table сервера)")
            # Спецпредмет с зарядами (CHARGES_RE.md §1.1): FT ток.8 = 2 (расход «−1 заряд»), ток.9 > 0 (заряды при выдаче),
            #   ток.25 = 0 (бессрочный) — именно такие P100 складывает с лежащим.
            charged = [c for c, _ in o["contents"] if c in self.fn and G._int(self.fn[c], 8) == 2
                       and G._int(self.fn[c], 9) > 0 and G._int(self.fn[c], 25) == 0]
            if charged:
                o["notes"].append("спецпредмет с зарядами (%s): %s" % (", ".join(map(str, charged)), (
                    "заряды сложит с лежащим сервер (P100 включён на всех GS)" if all(self.p100.values())
                    else "P100 на сервере не включён — придёт отдельной ячейкой, как при покупке")))
        o["ok"] = True
        return o


def rules(refresh=False):
    """Правила сервера (кэш на процесс; refresh=True — заново скопировать ВСЕ файлы стойки). Потокобезопасно."""
    global _RULES
    with G.SRV_LOCK:
        if _RULES is None or refresh:
            if refresh:
                G.srv_reset()
            _RULES = ServerRules()
        return _RULES


def rules_fresh_volatile():
    """Правила с заново скопированными картой шлюза и patches.ini (перед настоящей выдачей). Потокобезопасно."""
    with G.SRV_LOCK:
        r = rules()
        for rel in [PREMIUM_MAP] + [gs + "/ConfigSet/patches.ini" for gs in G.STACK_GS]:
            G.srv_file(rel, refresh=True)
        r.load_volatile()
        return r


def describe_offer(o, lang="ru"):
    """Многострочное описание позиции для карточки окна / консоли."""
    it = load_catalog()["items"].get(str(o["code"]), {})
    name = it.get("name_ru" if lang == "ru" else "name_en") or G.item_name(o["code"])
    out = ["%d — %s" % (o["code"], name)]
    if it.get("name_en") and lang == "ru":
        out.append("EN: %s" % it["name_en"])
    if o["price"] is not None:
        out.append("цена в магазине: %d GXP (для справки, игрок ничего не платит)" % o["price"])
    if o["delivery"]:
        k = {BUY_TYPE_SHELL: "1 «Shell Item»", BUY_TYPE_FUNC: "0 «Functional Item»"}.get(o["buy_type"], "?")
        dn = load_catalog()["items"].get(str(o["delivery"]), {}).get("name_ru") or G.item_name(o["delivery"])
        out.append("в ящик ляжет: код %d «%s», тип покупки %s" % (o["delivery"], dn, k))
    if o["spec"]:
        out.append("при заборе: " + G.describe_spec(o["delivery"]))
    for c, n in o["contents"]:
        out.append("  в коробке: %d «%s» × %d" % (c, G.item_name(c), n))
    out += ["• " + n for n in o["notes"]]
    out.append(("✔ можно подарить" if o["ok"] else "✖ нельзя: " + o["why"]))
    return "\n".join(out)


# ═════════════════════════════ каналы доставки ═════════════════════════════

def _free_orders(used, need):
    """Наименьшие свободные номера заказа у персонажа (как send-post): ящик показывает 7 заказов по возрастанию номера —
    подарок встаёт первым, номер уникален среди строк персонажа."""
    return G._free_orders(used, need)


class PostboxChannel:
    """Элитный почтовый ящик Joy1.dbo.ItemPostBox — строки как у покупки (UPCashitemBuy premrows): штука = строка
    Amount 1, до PER_ORDER штук под одним Orderidx. Игрок забирает сам; ячейку выбирает сервер (онлайн можно)."""
    key = "postbox"
    title = "Элитный почтовый ящик (как покупка в магазине)"
    online_ok = True   # можно при запущенном сервере

    def deliver(self, cn, t, o, qty, dry, commit=True):
        """Строки ящика одному персонажу: одна короткая транзакция, замок приложения, один INSERT
        (G.postbox_write). → (ok, текст, [номера заказов])."""
        chunks = [min(PER_ORDER, qty - i) for i in range(0, qty, PER_ORDER)]
        ok, text, orders = G.postbox_write(cn, t, [[(o["buy_type"], o["delivery"], 1)] * c for c in chunks], dry, commit)
        return ok, ("в ящик легло бы: " if dry else ("в ящик: " if ok else "")) + text, orders


# Каналы доставки: ключ → объект (title, online_ok, deliver(cn, t, offer, qty, dry, commit) → (ok, текст, заказы)).
#   Подарок P101 (5076/5078 с именем дарителя) появится здесь новым классом; пока единственный рабочий — ящик.
CHANNELS = {PostboxChannel.key: PostboxChannel()}
DEFAULT_CHANNEL = PostboxChannel.key


# ═════════════════════════════ журнал ═════════════════════════════

def operator():
    """Кто выдаёт: учётка Windows@машина."""
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME", "?")
    return "%s@%s" % (user, platform.node())


def journal_write(rec, path=None):
    """Строка журнала подарков (TAB-разделённая, с шапкой в новом файле). → True/False; сбой записи не ломает выдачу,
    но вызывающий обязан показать предупреждение."""
    path = path or JOURNAL
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8", newline="") as f:
            if new:
                f.write("\t".join(JOURNAL_HEAD) + "\n")
            f.write("\t".join(str(rec.get(k, "")).replace("\t", " ").replace("\n", " ") for k in JOURNAL_HEAD) + "\n")
        return True
    except OSError:
        return False


# ═════════════════════════════ подарок ═════════════════════════════

def gift(mode, value, code, qty=1, dry=False, progress=None, channel=DEFAULT_CHANNEL, journal=None, commit=True, db=None):
    """Подарок позиции витрины: qty штук каждому получателю. → (выдано, пропущено, строки отчёта).
    mode/value — как у «Выдачи»: 'char' имя | 'login' логин | 'all' (без служебных Userindex ≤ 5000 и без учёток из
    реестра банов). db — фабрика соединения (самотест передаёт свою, проверенную на LocalDB); по умолчанию — _db утилиты."""
    from asda_accounts import _db, _log
    db = db or _db
    try:
        code, qty = int(code), int(qty)
    except (TypeError, ValueError):
        raise GiftError("код и количество — целые числа")
    if not 1 <= qty <= MAX_QTY:
        raise GiftError("количество — от 1 до %d (каждая штука займёт ячейку сумки)" % MAX_QTY)
    if str(code) not in load_catalog()["items"]:
        raise GiftError("кода %d нет на витринах 6000/15300 — дарить можно только позиции магазина" % code)
    ch = CHANNELS.get(channel)
    if not ch:
        raise GiftError("неизвестный канал доставки: %s" % channel)
    # Отказ по коду — до обращения к получателям. Для настоящей выдачи карта шлюза и P98/P100 перечитываются с сервера.
    o = (rules() if dry or not commit else rules_fresh_volatile()).offer(code)
    if not o["ok"]:
        raise GiftError(o["why"])
    name = load_catalog()["items"][str(code)]["name_ru"]
    cn = db()
    try:
        targets, ban_lines = G.split_banned(G.resolve_targets(cn, mode, value), mode)
        ok_n, skip_n, lines, jfail = 0, 0, list(ban_lines), 0
        label = "подарок: %d × %d «%s» (в ящик код %d)" % (qty, code, name, o["delivery"])
        for i, t in enumerate(targets):
            if progress:
                progress(i, len(targets))
            try:
                ok, text, orders = ch.deliver(cn, t, o, qty, dry, commit=commit)
            except Exception as ex:   # ошибка SQL у одного — не останавливает остальных
                ok, text, orders = False, ("ошибка: %s — если связь оборвалась после записи, подарок мог уже лечь: "
                                           "проверьте ящик персонажа перед повтором" % ex), []
            who = "%s (учётка %s, ID %d/%d)" % (t["name"], t["login"], t["uid"], t["cidx"])
            lines.append(("✔ " if ok else "✖ ") + who + ": " + text)
            ok_n, skip_n = ok_n + (1 if ok else 0), skip_n + (0 if ok else 1)
            if not dry:
                jfail += 0 if journal_write(dict(zip(JOURNAL_HEAD, (
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), operator(), ch.key, t["name"], t["login"],
                    t["uid"], t["cidx"], code, o["delivery"], name, qty, o["buy_type"], ",".join(map(str, orders)),
                    ("ok" if ok else "пропуск") + ("" if commit else " (откат самотеста)") + ": " + text))), journal) else 1
                if commit:
                    _log("gift", t["login"], t["uid"], "%s, перс. %s/%d: %s — %s" % (
                        label, t["name"], t["cidx"], "ok" if ok else "пропуск", text))
        head = "%s%s: подарено %d, пропущено %d%s" % ("ПРОВЕРКА (без записи) — " if dry else "", label, ok_n, skip_n,
                                                      ", исключено по реестру банов %d" % len(ban_lines)
                                                      if mode == "all" and ban_lines else "")
        warn = ["⚠ ЖУРНАЛ НЕ ЗАПИСАН (%d строк): %s — подарки в ящике есть, запишите их вручную" % (jfail, journal or JOURNAL)
                ] if jfail else []
        return ok_n, skip_n, [head] + warn + G.SRV_WARN[:] + lines
    finally:
        cn.close()


# ═════════════════════════════ консоль ═════════════════════════════

def cli_catalog(text=""):
    """gift-catalog [поиск]: позиции витрин с решением «можно / нельзя» по живым правилам сервера."""
    r = rules()
    rows = catalog_rows(text)
    out = []
    for x in rows:
        o = r.offer(x["code"])
        where = "; ".join("%d: %s%s" % (p["shop"], p["path_ru"], " (скрыта)" if p["hidden"] else "") for p in x["places"])
        out.append("%6d  %-44s %s  %s%s" % (x["code"], x["name_ru"][:44],
                                            ("%6d GXP" % o["price"]) if o["price"] is not None else "     — ",
                                            "можно" if o["ok"] else "НЕЛЬЗЯ: " + o["why"], "  [%s]" % where))
    out.append("позиций: %d, можно подарить: %d" % (len(rows), sum(1 for x in rows if r.offer(x["code"])["ok"])))
    return out + G.SRV_WARN[:]


# ═════════════════════════════ вкладка окна ═════════════════════════════

def build_tab(nb, root):
    """Вкладка «Подарки»: витрина с иконками и поиском, карточка позиции, получатель, количество, канал, проверка, отчёт."""
    import threading
    import tkinter as tk
    from tkinter import messagebox, ttk

    f = ttk.Frame(nb, padding=10)
    nb.add(f, text="Подарки")
    images = {}   # код → PhotoImage (держим ссылки, иначе Tk их выбросит)

    # ── витрина ──
    left = ttk.LabelFrame(f, text="Витрина магазинов (6000 премиум, 15300 бустеры)", padding=6)
    left.grid(row=0, column=0, rowspan=2, sticky="nsew")
    search, shop = tk.StringVar(), tk.StringVar(value="все")
    hidden = tk.BooleanVar(value=True)
    ttk.Label(left, text="Найти (название RU/EN или код):").grid(row=0, column=0, sticky="w")
    sentry = ttk.Entry(left, textvariable=search, width=26)
    sentry.grid(row=0, column=1, sticky="w", padx=4)
    ttk.Combobox(left, textvariable=shop, values=("все", "6000", "15300"), width=6, state="readonly").grid(
        row=0, column=2, sticky="w")
    ttk.Checkbutton(left, text="со скрытыми вкладками", variable=hidden).grid(row=0, column=3, sticky="w", padx=4)
    style = ttk.Style(f)
    style.configure("Gift.Treeview", rowheight=36)
    tree = ttk.Treeview(left, columns=("code", "name", "where"), height=14, style="Gift.Treeview", selectmode="browse")
    tree.heading("#0", text="")
    tree.column("#0", width=48, stretch=False)
    for c, txt, w in (("code", "Код", 60), ("name", "Название", 250), ("where", "Где на витрине", 260)):
        tree.heading(c, text=txt)
        tree.column(c, width=w, stretch=(c != "code"))
    tree.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(6, 0))
    sb = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    sb.grid(row=1, column=4, sticky="ns", pady=(6, 0))
    tree.configure(yscrollcommand=sb.set)
    count = ttk.Label(left, text="", foreground="#555555")
    count.grid(row=2, column=0, columnspan=4, sticky="w")

    def img(code, big=False):
        """PhotoImage иконки (32/64 px → 32 в списке, 64 в карточке)."""
        key = (code, big)
        if key not in images:
            p = icon_path(code)
            if not p:
                return ""
            im = tk.PhotoImage(file=p)
            w = im.width()
            want = 64 if big else 32
            if w > want:
                im = im.subsample(max(1, w // want))
            elif w < want:
                im = im.zoom(max(1, want // w))
            images[key] = im
        return images[key]

    def fill(*_):
        """Перестроить список витрины по поиску, магазину и флажку скрытых вкладок."""
        tree.delete(*tree.get_children())
        shops = (6000, 15300) if shop.get() == "все" else (int(shop.get()),)
        try:
            rows = catalog_rows(search.get(), shops, hidden.get())
        except G.GiveError as ex:
            count.config(text="✖ " + str(ex), foreground="#c62828")
            return
        for x in rows:
            where = " | ".join(p["path_ru"] + (" (скрыта в клиенте)" if p["hidden"] else "") for p in x["places"])
            tree.insert("", "end", iid=str(x["code"]), image=img(x["code"]), values=(x["code"], x["name_ru"], where))
        count.config(text="позиций: %d" % len(rows), foreground="#555555")
    for v in (search, shop, hidden):
        v.trace_add("write", fill)

    # ── карточка ──
    card = ttk.LabelFrame(f, text="Выбранная позиция", padding=6)
    card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    cicon = tk.Label(card, width=64, height=64)
    cicon.grid(row=0, column=0, sticky="nw")
    cinfo = tk.Label(card, text="Выберите позицию в витрине.", justify="left", anchor="nw", wraplength=380)
    cinfo.grid(row=0, column=1, sticky="nw", padx=(8, 0))
    sel = {"code": None, "offer": None}

    def on_select(*_):
        """Выбор позиции: большая иконка сразу, правила сервера — в фоне (первый раз копируются файлы стойки)."""
        s = tree.selection()
        if not s:
            return
        code = int(s[0])
        sel["code"] = code
        cicon.config(image=img(code, big=True))
        cinfo.config(text="… правила сервера", fg="#555555")

        def work():
            """Фоновый поток: решение «можно / нельзя» по правилам сервера."""
            try:
                o = rules().offer(code)
                root.after(0, show, code, o, None)
            except Exception as ex:   # SSH/таблицы — показать, не уронить окно
                root.after(0, show, code, None, str(ex))
        threading.Thread(target=work, daemon=True).start()

    def show(code, o, err):
        """Карточка позиции (в потоке окна); устаревший ответ — если уже выбрана другая позиция — не показывается."""
        if sel["code"] != code:
            return
        sel["offer"] = o
        if err:
            cinfo.config(text="✖ " + err, fg="#c62828")
            return
        where = "\n".join("%d: %s%s" % (p["shop"], p["path_ru"], " (вкладка скрыта в клиенте)" if p["hidden"] else "")
                          for x in catalog_rows(str(code)) if x["code"] == code for p in x["places"])
        text = describe_offer(o) + "\nна витрине:\n" + where + ("\n⚠ " + "\n⚠ ".join(G.SRV_WARN) if G.SRV_WARN else "")
        cinfo.config(text=text, fg="#1a1a1a" if o["ok"] else "#c62828")
    tree.bind("<<TreeviewSelect>>", on_select)

    # ── кому / сколько / канал ──
    box = ttk.LabelFrame(f, text="Кому и сколько", padding=6)
    box.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(6, 0))
    mode, target, qty = tk.StringVar(value="char"), tk.StringVar(), tk.StringVar(value="1")
    for i, (val, text) in enumerate((("char", "Персонаж (имя)"), ("login", "Учётка (логин) — все её персонажи"),
                                     ("all", "Все игроки (кроме служебных ≤ 5000 и забаненных)"))):
        ttk.Radiobutton(box, text=text, value=val, variable=mode).grid(row=i, column=0, columnspan=3, sticky="w")
    ttk.Label(box, text="Имя / логин:").grid(row=3, column=0, sticky="w", pady=(4, 0))
    tentry = ttk.Entry(box, textvariable=target, width=24)
    tentry.grid(row=3, column=1, sticky="w", pady=(4, 0))
    mode.trace_add("write", lambda *_: tentry.state(["disabled"] if mode.get() == "all" else ["!disabled"]))
    ttk.Label(box, text="Штук (1–%d):" % MAX_QTY).grid(row=4, column=0, sticky="w", pady=(4, 0))
    ttk.Spinbox(box, from_=1, to=MAX_QTY, textvariable=qty, width=6).grid(row=4, column=1, sticky="w", pady=(4, 0))
    chan = tk.StringVar(value=CHANNELS[DEFAULT_CHANNEL].title)
    ttk.Label(box, text="Канал доставки:").grid(row=5, column=0, sticky="w", pady=(4, 0))
    ttk.Combobox(box, textvariable=chan, values=[c.title for c in CHANNELS.values()], width=44, state="readonly").grid(
        row=5, column=1, columnspan=2, sticky="w", pady=(4, 0))
    dry = tk.BooleanVar(value=False)
    ttk.Checkbutton(box, text="Только проверить (без записи)", variable=dry).grid(row=6, column=0, columnspan=2,
                                                                                  sticky="w", pady=(4, 0))
    gbtn = ttk.Button(box, text="Подарить")
    gbtn.grid(row=6, column=2, sticky="e", pady=(4, 0))
    # ★ 02.11.2026 (ревизия п.5): правила не живут до закрытия окна — кнопка копирует все файлы стойки заново
    #   (карта шлюза и patches.ini и так перечитываются перед каждой настоящей выдачей).
    rbtn = ttk.Button(box, text="Обновить правила сервера")
    rbtn.grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))
    status = tk.Label(f, text="Подарок ложится в элитный почтовый ящик — сервер можно не выключать; игрок забирает сам.",
                      anchor="w", fg="#555555")
    status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
    out = tk.Text(f, height=8, width=120, wrap="word")
    out.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(4, 0))

    def run():
        """«Подарить»: подтверждение (кроме проверки), затем подарок в фоновом потоке."""
        code = sel["code"]
        if code is None:
            messagebox.showwarning("Подарки", "Сначала выберите позицию в витрине.")
            return
        key = next(k for k, c in CHANNELS.items() if c.title == chan.get())
        m, val, n = mode.get(), target.get(), qty.get()
        if not dry.get():
            who = {"char": "персонажу «%s»" % val, "login": "всем персонажам учётки «%s»" % val,
                   "all": "ВСЕМ персонажам всех игроков"}[m]
            name = load_catalog()["items"][str(code)]["name_ru"]
            if not messagebox.askyesno("Подтверждение", "Подарить %s × «%s» (код %d) %s?\nКанал: %s.\nИгрок заберёт сам." % (
                    n, name, code, who, CHANNELS[key].title)):
                return
        gbtn.state(["disabled"])
        status.config(text="… выполняется", fg="#555555")
        out.delete("1.0", "end")

        def work():
            """Фоновый поток подарка; итог — в done() через очередь окна."""
            try:
                prog = lambda i, k: root.after(0, status.config, {"text": "… %d из %d" % (i + 1, k)})
                ok_n, skip_n, lines = gift(m, val, code, n, dry=dry.get(), progress=prog, channel=key)
                root.after(0, done, True, "\n".join(lines), skip_n == 0)
            except G.GiveError as ex:
                root.after(0, done, False, str(ex), False)
            except Exception as ex:   # драйвер, сеть, права — показать, а не уронить окно
                root.after(0, done, False, "ошибка: %s" % ex, False)
        threading.Thread(target=work, daemon=True).start()

    def done(ok, text, clean):
        """Итог подарка: строка состояния и полный отчёт по получателям."""
        gbtn.state(["!disabled"])
        first = text.split("\n", 1)[0]
        status.config(text=("✔ " if ok and clean else ("⚠ " if ok else "✖ ")) + first,
                      fg="#1a7f37" if ok and clean else ("#b26a00" if ok else "#c62828"))
        out.insert("end", text)
    gbtn.config(command=run)

    def refresh():
        """«Обновить правила сервера»: заново скопировать файлы стойки и перерисовать карточку выбранной позиции."""
        rbtn.state(["disabled"])
        status.config(text="… копирую правила сервера", fg="#555555")

        def work():
            """Фоновый поток обновления правил."""
            try:
                r = rules(refresh=True)
                text = "✔ правила сервера обновлены: P98 %s, P100 %s%s" % (
                    "вкл" if all(r.p98.values()) else "ВЫКЛ", "вкл" if all(r.p100.values()) else "выкл",
                    ("; ⚠ " + "; ".join(G.SRV_WARN)) if G.SRV_WARN else "")
            except Exception as ex:   # SSH/таблицы — показать, не уронить окно
                text = "✖ правила не обновлены: %s" % ex
            root.after(0, refreshed, text)
        threading.Thread(target=work, daemon=True).start()

    def refreshed(text):
        """Итог обновления правил (в потоке окна)."""
        rbtn.state(["!disabled"])
        status.config(text=text, fg="#c62828" if text.startswith("✖") else "#1a7f37")
        if sel["code"] is not None:
            on_select()
    rbtn.config(command=refresh)
    f.columnconfigure(0, weight=1)
    f.rowconfigure(3, weight=1)
    fill()
    return f
