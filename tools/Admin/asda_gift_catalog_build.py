# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""asda_gift_catalog_build.py — выгрузка витрины подарков для вкладки «Подарки» утилиты учёток (01.11.2026).

ЧТО ДЕЛАЕТ (один раз и после каждого нового товара магазина; без редактора UE и без сети)
  * берёт ВСЕ строки двух витрин порта — те же файлы, из которых собираются DataTable клиента:
      окно 6000 (премиум-магазин) — RawAssets/Data/NPC/PremiumShopBin.json → DT_PremiumShopBin
                                     (PremiumShop.BIN + хвосты маунтов и коробок, импортёр asda_import_premium_shop_bin.py);
      окно 15300 (магазин бустеров) — RawAssets/Data/NPC/BoosterShopList.json → DT_BoosterShopList
                                     (Bpremium.BIN/Fpremium.BIN, импортёр asda_import_booster_shop.py);
  * названия RU — клиентские таблицы предметов (RawAssets/Data/ItemDB: item_list / special_itemlist / sowell_list),
    EN — оверлеи RawAssets/Text/L10N/en/DT_Loc_<таблица>_en.csv (ключ «_row.колонка»; нет строки → RU, как цепочка
    языков клиента en → ru); подписи категорий — GameText 10401…10448 (RU) и DT_Loc_GameText_en.csv (EN);
  * иконка каждого кода — ТЕМ ЖЕ правилом, что в клиенте порта: UAsdaItemTableSubsystem::GetItemIcon
    (Source/AsdaReborn/Private/Items/AsdaItemTableSubsystem.cpp) + формулы namespace AsdaItemIcon
    (Public/Items/AsdaItemTableSubsystem.h) + заворот UV по модулю AsdaUi::ApplyItemIcon (bWrap, AsdaUiHelpers.cpp):
      самоцвет (код в диапазоне sowell_list)      — атлас = IconPath, левый-верхний квадрат 32×32;
      спецпредмет (диапазон special_itemlist)     — атлас = IconPath, ячейка IconCell, сетка 8 × 64 px;
      обычный предмет (item_list)                 — запись item_img_table № ImgIndex (позиция строки), мужской вариант
                                                    (витрины 6000/15300 рисуют bMale=true): IconSmallFlag 1 → 32 px и
                                                    16 колонок, иначе 64 px и 8 колонок;
    атлас — исходник текстуры /Game/AsdaAssets/Textures/JUI/<имя> = RawAssets/Textures/JUI/<имя>.png (из него
    импортируется ассет: asda_reimport_icon_atlases.py). Логический размер атласа = размер PNG: иконочных атласов в
    DT_AtlasSourceSize нет (там 22 других JUI-текстуры, список — ATLAS_UPSCALED; если атлас из списка — отказ с
    причиной, координаты не пересчитываются наугад).
  * пишет data/icons/<код>.png (вырезка ячейки как есть) и data/gift_catalog.json (строки витрин, названия, иконки,
    покрытие). Серверная часть (код выдачи, цена, тип покупки, можно ли продать) сюда НЕ входит — её утилита берёт с
    сервера при каждом запуске (asda_gifts.py).

ЗАПУСК:  python AstoryAdminCenter/tools/Admin/asda_gift_catalog_build.py          (нужен Pillow)
Побочных эффектов при импорте нет (закон tools-no-import-side-effects): вся работа — в main().
"""
import csv
import datetime
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORT_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "AstoryClient", "Tools")   # ★ 25.11 (С-2): папка с клонами / AstoryClient/Tools — там asda_paths.py
# ★ 02.11.2026 (ревизия п.7): asda_paths подключается в main() (_load_paths), импорт этого файла ничего не меняет.
_P = None            # модуль asda_paths (после _load_paths)
RAW = ITEMDB = NPC_DIR = L10N_EN = GAMETEXT_RU = JUI_PNG = None   # пути данных порта (после _load_paths)
OUT_DIR = os.path.join(HERE, "data")                         # данные утилиты
ICON_DIR = os.path.join(OUT_DIR, "icons")                    # иконки витрины (PNG по коду)
OUT_JSON = os.path.join(OUT_DIR, "gift_catalog.json")        # каталог для вкладки «Подарки»


def _load_paths():
    """Подключить единый реестр путей asda_paths.py и вычислить пути данных порта (вызывается из main/build)."""
    global _P, RAW, ITEMDB, NPC_DIR, L10N_EN, GAMETEXT_RU, JUI_PNG
    if _P is not None:
        return
    if PORT_TOOLS not in sys.path:
        sys.path.insert(0, PORT_TOOLS)
    import asda_paths
    _P = asda_paths
    RAW = os.path.join(_P.PORT_DIR, "AstoryClient", "RawAssets")
    ITEMDB = os.path.join(RAW, "Data", "ItemDB")                 # клиентские таблицы предметов (источники DataTable)
    NPC_DIR = os.path.join(RAW, "Data", "NPC")                   # витрины магазинов (источники DataTable)
    L10N_EN = os.path.join(RAW, "Text", "L10N", "en")            # EN-оверлеи текстов
    GAMETEXT_RU = os.path.join(RAW, "Text", "GameText.csv")      # RU-тексты окон (GameText)
    JUI_PNG = os.path.join(RAW, "Textures", "JUI")               # исходники атласов иконок (PNG)


# JUI-текстуры с исходным размером в DT_AtlasSourceSize (увеличенные; UV клиента делятся на ИСХОДНЫЙ размер).
ATLAS_UPSCALED = {"ad_img00", "ad_img01", "ad_img02", "bar", "capback", "christmas_01", "im_sb_am_00", "im_sb_am_01",
                  "im_sb_am_03", "im_sb_cb_00", "im_sb_cb_01", "im_sb_cb_03", "im_sb_oh_00", "im_sb_oh_01", "im_sb_oh_03",
                  "ne_banner", "ne_booster_border80", "ne_boosting_bg", "ne_fish_big", "ne_fish_nomal", "ne_fish_small",
                  "ne_fish_special"}

# Подписи вкладок окна 6000 (loc 10401+k полосы 58200, 10421+m полосы 58201, 10426+n класс, 10441+ii полоса 58203):
#   Category записи → вкладка (kCatToField порта AsdaPremiumShopSubsystem.cpp: вкладки 2…7 = Category 1…6).
CAT_LOC = {1: 10403, 2: 10404, 3: 10405, 4: 10406, 5: 10407, 6: 10408}
TOOL_SUB_LOC = {1: 10422, 2: 10423, 3: 10424, 4: 10425}               # Category 1: Sub1 1…4
CLASS_LOC = {1: 10426, 2: 10427, 3: 10428}                            # Category 2: Sub1 = класс
EQ_SUB2_LOC = {9: 10442, 0: 10443, 1: 10444, 4: 10445, 2: 10446, 3: 10447, 11: 10448}   # kSub2ToField порта
HOT_LOC, NEW_LOC = 10401, 10402                                        # NewFlag 1 / 2
# Магазин бустеров 15300: категория витрины (+0x44 Bpremium) 9 оружие / 12 доспех / 13 инструмент (PassesCategory порта);
#   подписи — те же слова из GameText окна 6000.
BOOSTER_CAT_LOC = {9: 10442, 12: 10444, 13: 10403}
# Вкладки окна 6000, скрытые в клиенте порта по умолчанию (asda.PremiumMall.Show{New,Hair,Sundry}Category = 0).
HIDDEN_CATS = {3: "вкладка «Волосы» в клиенте скрыта (asda.PremiumMall.ShowHairCategory 0)",
               6: "вкладка «Лавка мелочей» в клиенте скрыта (asda.PremiumMall.ShowSundryCategory 0)"}
HIDDEN_NEW = "вкладка «Новинка!» в клиенте скрыта (asda.PremiumMall.ShowNewCategory 0)"


def _md5(path):
    """md5 файла (для отметки источников в каталоге)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _csv_rows(path):
    """Строки CSV как словари (UTF-8 с BOM)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _loc_csv(path):
    """Ключ → текст из CSV «Name,Text» (оверлей L10N) или «Key,SourceString» (GameText)."""
    out = {}
    if not os.path.exists(path):
        return out
    for r in _csv_rows(path):
        k = r.get("Name") if "Name" in r else r.get("Key")
        v = r.get("Text") if "Text" in r else r.get("SourceString")
        if k is not None and v is not None:
            out[k.strip()] = v
    return out


class Tables:
    """Клиентские таблицы предметов порта: записи по коду, позиционная item_img_table, EN-оверлеи, тексты окон."""

    def __init__(self):
        self.item = {}       # код item_list → строка CSV
        self.special = {}    # код special_itemlist → строка
        self.sowel = {}      # код sowell_list → строка
        for r in _csv_rows(os.path.join(ITEMDB, "item_list.csv")):
            if r["ItemCode"].strip().lstrip("-").isdigit():
                self.item[int(r["ItemCode"])] = r          # при дублях — последняя строка (BuildKeyIndex порта)
        for r in _csv_rows(os.path.join(ITEMDB, "special_itemlist.csv")):
            if r["Code"].strip().isdigit():
                self.special[int(r["Code"])] = r
        for r in _csv_rows(os.path.join(ITEMDB, "sowell_list.csv")):
            if r["Id"].strip().isdigit():
                self.sowel[int(r["Id"])] = r
        self.img = {}        # № строки (_row) item_img_table → строка (позиционный кэш BuildOrderedCache)
        for r in _csv_rows(os.path.join(ITEMDB, "item_img_table.csv")):
            if r["_row"].strip().isdigit():
                self.img[int(r["_row"])] = r
        # Границы кодовых пространств — min/max кода таблицы (RangeOf порта).
        self.sp_lo, self.sp_hi = (min(self.special), max(self.special)) if self.special else (0, -1)
        self.sw_lo, self.sw_hi = (min(self.sowel), max(self.sowel)) if self.sowel else (0, -1)
        self.en = {"item_list": _loc_csv(os.path.join(L10N_EN, "DT_Loc_item_list_en.csv")),
                   "special_itemlist": _loc_csv(os.path.join(L10N_EN, "DT_Loc_special_itemlist_en.csv")),
                   "sowell_list": _loc_csv(os.path.join(L10N_EN, "DT_Loc_sowell_list_en.csv"))}
        self.gt_ru = _loc_csv(GAMETEXT_RU)
        self.gt_en = _loc_csv(os.path.join(L10N_EN, "DT_Loc_GameText_en.csv"))

    def text(self, loc):
        """(RU, EN) строки GameText; EN нет — RU."""
        ru = self.gt_ru.get(str(loc), "")
        return ru, self.gt_en.get(str(loc), ru)

    def names(self, code):
        """(RU, EN, таблица) названия кода; нет записи — ('', '', '')."""
        if self.sw_lo <= code <= self.sw_hi:
            r, tab, col = self.sowel.get(code), "sowell_list", "Name"
        elif self.sp_lo <= code <= self.sp_hi:
            r, tab, col = self.special.get(code), "special_itemlist", "Name"
        else:
            r, tab, col = self.item.get(code), "item_list", "ItemName"
        if not r:
            return "", "", ""
        ru = (r.get(col) or "").strip()
        en = (self.en[tab].get("%s.%s" % (r["_row"].strip(), col)) or "").strip() or ru
        return ru, en, tab

    def icon(self, code):
        """Иконка кода по правилу GetItemIcon порта: dict(atlas, x, y, size) или (None, причина)."""
        if self.sw_lo <= code <= self.sw_hi:
            r = self.sowel.get(code)
            if not r:
                return None, "нет записи sowell_list"
            path = (r.get("IconPath") or "").strip()
            if not path:
                return None, "у записи sowell_list пустой IconPath"
            return dict(atlas=path, x=0, y=0, size=32, whole=True), ""   # 07.11.2026: иконка совела — вся картинка (исходник 32, апскейл 64)
        if self.sp_lo <= code <= self.sp_hi:
            r = self.special.get(code)
            if not r:
                return None, "нет записи special_itemlist"
            path = (r.get("IconPath") or "").strip()
            if not path:
                return None, "у записи special_itemlist пустой IconPath"
            cell = int(r.get("IconCell") or 0)
            return dict(atlas=path, x=64 * (cell % 8), y=64 * (cell // 8), size=64), ""
        r = self.item.get(code)
        if not r:
            return None, "кода нет в item_list клиента"
        idx = int(r.get("ImgIndex") or -1)
        img = self.img.get(idx)
        if not img:
            return None, "нет записи item_img_table № %d" % idx
        atlas = (img.get("IconAtlasMale") or "").strip()
        if not atlas:
            return None, "у записи item_img_table № %d пустой атлас" % idx
        cell = int(img.get("IconCellMale") or 0)
        small = (img.get("IconSmallFlag") or "").strip() == "1"
        size, cols = (32, 16) if small else (64, 8)
        return dict(atlas=atlas, x=size * (cell % cols), y=size * (cell // cols), size=size), ""


def _png_index():
    """Имя атласа (нижний регистр) → путь PNG исходника."""
    return {os.path.splitext(n)[0].lower(): os.path.join(JUI_PNG, n)
            for n in os.listdir(JUI_PNG) if n.lower().endswith(".png")}


def _cut_icon(png_path, ic, cache):
    """Вырезка ячейки атласа (с заворотом по модулю, как bWrap клиента) → PIL.Image или (None, причина)."""
    from PIL import Image
    im = cache.get(png_path)
    if im is None:
        im = Image.open(png_path).convert("RGBA")
        cache[png_path] = im
    if ic.get("whole"):   # логический размер 32 в DT_AtlasSourceSize, файл больше: ячейка = весь файл
        return im.copy(), ""
    w, h = im.size
    x, y, s = ic["x"] % w, ic["y"] % h, ic["size"]
    if x + s > w or y + s > h:
        return None, "ячейка (%d,%d,%d) выходит за атлас %d×%d" % (x, y, s, w, h)
    cell = im.crop((x, y, x + s, y + s))
    if cell.getextrema()[3][1] == 0:
        return None, "ячейка (%d,%d) атласа %s пустая (полностью прозрачная)" % (x, y, os.path.basename(png_path))
    return cell, ""


def build():
    """Собирает каталог и иконки. → (каталог, строки отчёта)."""
    _load_paths()
    t = Tables()
    prem = json.load(open(os.path.join(NPC_DIR, "PremiumShopBin.json"), encoding="utf-8"))
    boost = json.load(open(os.path.join(NPC_DIR, "BoosterShopList.json"), encoding="utf-8"))
    rows = []
    for r in prem:
        code = int(r["ItemId"])
        if code <= 0:
            continue   # пустая запись файла (ItemId 0) — клиент карточку по ней не строит (нет предмета)
        cat, s1, s2, nf = int(r["Category"]), int(r["Sub1"]), int(r["Sub2"]), int(r["NewFlag"])
        path_ru, path_en = [], []
        for loc in ([HOT_LOC] if nf == 1 else []) + ([NEW_LOC] if nf == 2 else []) + [CAT_LOC.get(cat)] + (
                [TOOL_SUB_LOC.get(s1)] if cat == 1 else []) + ([CLASS_LOC.get(s1), EQ_SUB2_LOC.get(s2)] if cat == 2 else []):
            if loc:
                ru, en = t.text(loc)
                path_ru.append(ru)
                path_en.append(en)
        hidden = HIDDEN_CATS.get(cat, "")
        if nf == 2 and not hidden and cat not in CAT_LOC:
            hidden = HIDDEN_NEW
        rows.append(dict(code=code, shop=6000, row=int(r["_row"]), cat=cat, sub1=s1, sub2=s2, new_flag=nf,
                         path_ru=" / ".join(path_ru), path_en=" / ".join(path_en), hidden=hidden))
    for r in boost:
        code = int(r["ItemCode"])
        ru, en = t.text(BOOSTER_CAT_LOC.get(int(r["ItemType"]) & 0xFF, 10448))
        b_ru, b_en = t.text(10448)
        rows.append(dict(code=code, shop=15300, row=int(r["Order"]), cat=int(r["ItemType"]), sub1=0, sub2=0,
                         new_flag=int(r["Badge"]), path_ru="%s / %s" % (b_ru, ru), path_en="%s / %s" % (b_en, en),
                         hidden="", discount=int(r["DiscountPct"])))

    os.makedirs(ICON_DIR, exist_ok=True)
    pngs, cache = _png_index(), {}
    items, no_icon = {}, []
    for code in sorted({r["code"] for r in rows}):
        ru, en, tab = t.names(code)
        ic, why = t.icon(code)
        icon_file = None
        if ic:
            atlas = ic["atlas"].lower()
            if atlas in ATLAS_UPSCALED:
                why = "атлас %s увеличен (DT_AtlasSourceSize) — исходный размер в данных порта не выгружен" % ic["atlas"]
            elif atlas not in pngs:
                why = "нет исходника атласа RawAssets/Textures/JUI/%s.png" % ic["atlas"]
            else:
                cell, why = _cut_icon(pngs[atlas], ic, cache)
                if cell is not None:
                    icon_file = "icons/%d.png" % code
                    cell.save(os.path.join(OUT_DIR, icon_file))
        if not icon_file:
            no_icon.append((code, ru, why))
        items[str(code)] = dict(name_ru=ru, name_en=en, table=tab, icon=icon_file, icon_why=why if not icon_file else "",
                                atlas=ic["atlas"] if ic else "", cell=[ic["x"], ic["y"], ic["size"]] if ic else None)
    n_rows = len(rows)
    rows_icon = sum(1 for r in rows if items[str(r["code"])]["icon"])
    cat = dict(
        _comment="Витрина подарков вкладки «Подарки» (asda_accounts.py). Собрана asda_gift_catalog_build.py — не править руками.",
        built=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        sources={os.path.relpath(p, _P.PORT_DIR): _md5(p) for p in (
            os.path.join(NPC_DIR, "PremiumShopBin.json"), os.path.join(NPC_DIR, "BoosterShopList.json"),
            os.path.join(ITEMDB, "item_list.csv"), os.path.join(ITEMDB, "special_itemlist.csv"),
            os.path.join(ITEMDB, "sowell_list.csv"), os.path.join(ITEMDB, "item_img_table.csv"))},
        coverage=dict(rows=n_rows, rows_with_icon=rows_icon, codes=len(items), codes_with_icon=len(items) - len(no_icon),
                      without_icon=[dict(code=c, name=n, why=w) for c, n, w in no_icon]),
        rows=rows, items=items)
    # ★ 02.11.2026 (ревизия п.7): каталог пишется атомарно (временный файл + замена), иконки снятых с витрины кодов
    #   удаляются — в папке остаются ровно иконки каталога.
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_JSON)
    keep = {os.path.basename(v["icon"]) for v in items.values() if v["icon"]}
    stale = [n for n in os.listdir(ICON_DIR) if n.lower().endswith(".png") and n not in keep]
    for n in stale:
        os.remove(os.path.join(ICON_DIR, n))
    rep = ["строк витрин: %d (6000: %d, 15300: %d), кодов: %d" % (
        n_rows, sum(1 for r in rows if r["shop"] == 6000), sum(1 for r in rows if r["shop"] == 15300), len(items)),
        "с иконкой: строк %d из %d (%.1f %%), кодов %d из %d" % (rows_icon, n_rows, 100.0 * rows_icon / max(1, n_rows),
                                                                 len(items) - len(no_icon), len(items))]
    rep += ["  без иконки: %d «%s» — %s" % x for x in no_icon]
    rep.append("удалено иконок снятых с витрины кодов: %d" % len(stale))
    return cat, rep


def main(argv=None):
    """Точка входа: собрать каталог и иконки, напечатать покрытие. Код возврата 0 — все строки с иконкой."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cat, rep = build()
    print("\n".join(rep))
    print("каталог:", OUT_JSON)
    return 0 if not cat["coverage"]["without_icon"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
