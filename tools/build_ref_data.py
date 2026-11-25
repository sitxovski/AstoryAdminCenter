# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""build_ref_data.py — справочники панели из данных порта: предметы (названия RU/EN + иконки), классы, карты,
навыки, питомцы. 16.11.2026.

ЗАЧЕМ. Служба на сервере не видит RawAssets порта. Скрипт один раз (и после каждого выпуска с новыми предметами)
собирает компактные справочники в AdminCenter/data/ref/ и выкладывается вместе со службой.

ОТКУДА (те же файлы, из которых собираются DataTable клиента — названия и иконки совпадают с игрой):
  предметы  — RawAssets/Data/ItemDB/{item_list, special_itemlist, sowell_list, item_img_table}.csv + EN-оверлеи
              RawAssets/Text/L10N/en/DT_Loc_*_en.csv; правило иконки — Tables.icon() из
              AstoryAdminCenter/tools/Admin/asda_gift_catalog_build.py (= UAsdaItemTableSubsystem::GetItemIcon клиента);
  атласы    — RawAssets/Textures/JUI/<имя>.png: копируются только атласы, на которые ссылается хоть одна иконка;
              панель вырезает ячейку сама (CSS background-position), поэтому 60 тыс. отдельных картинок не нужны;
  классы    — ItemDB/jobtype.csv + DT_Loc_jobtype_en.csv;
  карты     — AsdaReborn/Tools/data/asda_map_registry.json (единый реестр карт) + DT_Loc_MapTable_en.csv;
  навыки    — ItemDB/skill_info.csv + DT_Loc_skill_info_en.csv;  питомцы — ItemDB/pettable.csv + DT_Loc_pettable_en.csv.

ВЫХОД: data/ref/items.json  {код: [ru, en, таблица, атлас, x, y, размер, целиком(0/1)]},
       data/ref/atlases.json {атлас: [ширина, высота]}, data/ref/atlases/<атлас>.png,
       data/ref/names.json  {jobs, maps, skills, pets}, data/ref/manifest.json (md5 источников, счётчики).
ЗАПУСК: python AstoryAdminCenter/tools/build_ref_data.py      (нужен Pillow)
Побочных эффектов при импорте нет: вся работа в main().
"""
import csv
import datetime
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                         # AstoryAdminCenter
TOOLS = HERE                                                         # AstoryAdminCenter/tools (там Admin/asda_gift_catalog_build.py) — ★ 25.11
OUT = os.path.join(ROOT, "data", "ref")
RAW = os.path.join(os.path.dirname(ROOT), "AstoryClient", "RawAssets")   # данные клиента (в публичном AstoryClient их нет)


def _csv(path):
    """Строки CSV (UTF-8 с BOM)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _loc(path):
    """EN-оверлей {ключ «_row.колонка»: текст}; нет файла — пусто."""
    if not os.path.exists(path):
        return {}
    return {r["Name"].strip(): r["Text"] for r in _csv(path) if r.get("Name")}


def _md5(path):
    """md5 файла (для манифеста)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def build_titles():
    """Звания: data/ref/titles.json {id: [ru, en, ClassReq, Group, Position, Enabled, Point]} (18.11.2026, операции званий).
    RU — title_list.json порта (имя в DataHex +16…+80, cp1251: поле Name в JSON испорчено), EN — DT_Loc_title_list_en.csv."""
    raw = os.path.join(os.path.dirname(ROOT), "AstoryClient", "RawAssets")
    with open(os.path.join(raw, "Data", "ItemDB", "title_list.json"), encoding="utf-8") as f:
        rows = json.load(f)
    en = {}
    for r in _csv(os.path.join(raw, "Text", "L10N", "en", "DT_Loc_title_list_en.csv")):
        k = r.get("Name", "")
        if k.endswith(".Name"):
            en[k[:-5]] = r.get("Text", "")
    out = {}
    for r in rows:
        b = bytes.fromhex(r["DataHex"])[16:80]
        ru = b.split(b"\x00", 1)[0].decode("cp1251", "replace")
        out[str(r["Id"])] = [ru, en.get(str(r["Id"]), ""), r["ClassReq"], r["Group"], r["Position"], r["Enabled"], r["Point"]]
    with open(os.path.join(OUT, "titles.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return len(out)


def main(argv=None):
    """Собрать справочники. Код возврата 0 — успех."""
    if not os.path.isdir(RAW):                    # ★ 25.11 (М-10): публичный клон — справочники data/ref в репозитории уже собраны
        print("нет %s — справочники не пересобираются (готовые data/ref лежат в репозитории)" % RAW)
        return 2
    sys.path.insert(0, os.path.join(TOOLS, "Admin"))
    import asda_gift_catalog_build as GC          # правило иконок и чтение таблиц предметов (одно на весь проект)
    from PIL import Image
    GC._load_paths()
    t = GC.Tables()
    os.makedirs(os.path.join(OUT, "atlases"), exist_ok=True)

    png = GC._png_index()                         # атлас (нижний регистр) → путь PNG
    items, used, missing = {}, {}, {}
    codes = sorted(set(t.item) | set(t.special) | set(t.sowel))
    for code in codes:
        ru, en, tab = t.names(code)
        ic, why = t.icon(code)
        rec = [ru, en, tab, "", 0, 0, 0, 0]
        if ic:
            key = ic["atlas"].lower()
            if key in png:
                used[key] = png[key]
                rec[3:8] = [key, ic["x"], ic["y"], ic["size"], 1 if ic.get("whole") else 0]
            else:
                missing[key] = missing.get(key, 0) + 1
        items[code] = rec

    atlases = {}
    for key, src in sorted(used.items()):
        with Image.open(src) as im:
            atlases[key] = list(im.size)
        dst = os.path.join(OUT, "atlases", key + ".png")
        if not os.path.exists(dst) or _md5(dst) != _md5(src):
            shutil.copyfile(src, dst)
    for n in os.listdir(os.path.join(OUT, "atlases")):          # убрать атласы, на которые больше никто не ссылается
        if os.path.splitext(n)[0] not in atlases:
            os.remove(os.path.join(OUT, "atlases", n))

    raw = GC.RAW
    itemdb = GC.ITEMDB
    l10n = GC.L10N_EN
    jobs_en = _loc(os.path.join(l10n, "DT_Loc_jobtype_en.csv"))
    jobs = {int(r["_row"]): [r["JobName"], jobs_en.get("%s.JobName" % r["_row"], r["JobName"]), r["ParentJob"]]
            for r in _csv(os.path.join(itemdb, "jobtype.csv")) if r["_row"].isdigit()}
    reg = json.load(open(os.path.join(os.path.dirname(ROOT), "AstoryClient", "Tools", "data", "asda_map_registry.json"),
                         encoding="utf-8"))
    maps_en = _loc(os.path.join(l10n, "DT_Loc_MapTable_en.csv"))
    maps = {int(m["id"]): [m.get("loc_name") or m.get("dir"), maps_en.get("%d.DisplayName" % m["id"], m.get("dir")),
                           m.get("kind", "")] for m in reg["maps"]}
    sk_en = _loc(os.path.join(l10n, "DT_Loc_skill_info_en.csv"))
    skills = {int(r["SkillCode"]): [r["Name"], sk_en.get("%s.Name" % r["_row"], r["Name"])]
              for r in _csv(os.path.join(itemdb, "skill_info.csv")) if r["SkillCode"].lstrip("-").isdigit()}
    pet_en = _loc(os.path.join(l10n, "DT_Loc_pettable_en.csv"))
    pets = {int(r["Id"]): [r["Name"], pet_en.get("%s.Name" % r["_row"], r["Name"])]
            for r in _csv(os.path.join(itemdb, "pettable.csv")) if r["Id"].lstrip("-").isdigit()}
    # названия опций предмета (шаблон с %d) — та же таблица, что у окна предмета в клиенте (itemoptiontable)
    opt_en = _loc(os.path.join(l10n, "DT_Loc_itemoptiontable_en.csv"))
    options = {int(r["OptionId"]): [r["FmtString"], opt_en.get("%s.FmtString" % r["_row"], r["FmtString"])]
               for r in _csv(os.path.join(itemdb, "itemoptiontable.csv")) if r["OptionId"].lstrip("-").isdigit()}

    def dump(name, obj):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

    dump("items.json", items)
    dump("atlases.json", atlases)
    dump("names.json", {"jobs": jobs, "maps": maps, "skills": skills, "pets": pets, "options": options})
    srcs = [os.path.join(itemdb, n) for n in ("item_list.csv", "special_itemlist.csv", "sowell_list.csv",
                                              "item_img_table.csv", "jobtype.csv", "skill_info.csv", "pettable.csv",
                                              "itemoptiontable.csv")]
    size = sum(os.path.getsize(os.path.join(OUT, "atlases", n)) for n in os.listdir(os.path.join(OUT, "atlases")))
    man = {"built": datetime.datetime.now().isoformat(timespec="seconds"),
           "sources": {os.path.relpath(p, raw): _md5(p) for p in srcs},
           "items": len(items), "with_icon": sum(1 for r in items.values() if r[3]),
           "atlases": len(atlases), "atlas_bytes": size, "missing_atlases": missing,
           "jobs": len(jobs), "maps": len(maps), "skills": len(skills), "pets": len(pets), "options": len(options)}
    man["titles"] = build_titles()
    man["quests"] = build_quests()
    dump("manifest.json", man)
    print(json.dumps(man, ensure_ascii=False, indent=1))
    return 0


def build_quests():
    """Задания: data/ref/quests.json {Episodeidx: [ru, en]} (18.11.2026, операции заданий). RU — QuestBook.json порта (BookNo =
    Episodeidx, Title; источник — клиентские Data/NPC/Episode/BOOK/*.QST), EN — DT_Loc_QuestBook_en.csv «<FileName>.Title»."""
    raw = os.path.join(os.path.dirname(ROOT), "AstoryClient", "RawAssets")
    with open(os.path.join(raw, "Data", "Quest", "QuestBook.json"), encoding="utf-8") as f:
        rows = json.load(f)
    en = _loc(os.path.join(raw, "Text", "L10N", "en", "DT_Loc_QuestBook_en.csv"))
    out = {}
    for r in rows:
        k = str(int(r["BookNo"]))
        if k not in out:                          # первая книга номера (как импорт клиента)
            out[k] = [(r.get("Title") or "").strip().strip('"').strip(), (en.get(r["FileName"] + ".Title") or "").strip()]
    with open(os.path.join(OUT, "quests.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return len(out)


if __name__ == "__main__":
    if "--quests" in sys.argv:                    # только задания
        print("заданий:", build_quests())
        sys.exit(0)
    if "--titles" in sys.argv:                    # только звания (без пересборки предметов и атласов)
        print("званий:", build_titles())
        sys.exit(0)
    sys.exit(main())
