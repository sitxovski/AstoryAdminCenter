# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_texts_a4.py — самотест шага А4.2 «Данные игры → Тексты» (19.11.2026): вид text.set (cs_kinds/texts.py), проверки текста,
план клиентской половины на КОПИЯХ файлов порта (рецепт имён, CSV/JSON ItemDB, реестр карт → Map_info, QuestBook + ru_dt_overrides,
EN-оверлеи и ведомости loc/en), сторожа «мимо ведомости», путь набора в песочнице (применение и откат), живой сухой план.
Настоящие инструменты порта (asda_apply_name_overlay.load_overlay, asda_ledger.classify, asda_ru_dt_overrides.apply_rows,
asda_map_registry.render_map_info_csv) — в процессе; декодер ItemDB офлайн подменён (живой прогон — настоящий). Побочных эффектов нет.
"""
import hashlib
import json
import os
import shutil
import tempfile

CRLF = "\r\n"


def _w(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data.encode("utf-8") if isinstance(data, str) else data)


def _md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def fixtures(d):
    """Копии-образцы файлов порта для вида text.set в каталоге d → словарь путей P модуля texts."""
    from domains.cs_kinds import texts as TX
    MR = TX._tool("asda_map_registry")
    P = {"itemdb": os.path.join(d, "ItemDB"), "overlay": os.path.join(d, "_out", "item_name_overlay.csv"),
         "mobnames": os.path.join(d, "gen", "DT_MobNames.csv"), "npcnames": os.path.join(d, "gen", "DT_NpcNames.csv"),
         "map_reg": os.path.join(d, "data", "asda_map_registry.json"), "map_info": os.path.join(d, "World", "Map_info.csv"),
         "quest": os.path.join(d, "Quest", "QuestBook.json"), "ru_dt": os.path.join(d, "data", "ru_dt_overrides.json"),
         "en_dir": os.path.join(d, "L10N", "en"), "en_led": os.path.join(d, "data", "loc", "en")}
    I = P["itemdb"]
    _w(os.path.join(I, "item_list.csv"), CRLF.join(["_row,ItemCode,ItemName,Price", "0,20551,Меч,10", "1,20552,Щит,5", ""]))
    _w(os.path.join(I, "item_list.json"), json.dumps([{"_row": 0, "ItemCode": 20551, "ItemName": "Меч"}, {"_row": 1, "ItemCode": 20552,
                                                                                                       "ItemName": "Щит"}], ensure_ascii=False, indent=0).replace("\n", CRLF))
    _w(os.path.join(I, "item_tooltip.csv"), CRLF.join(["_row,ItemCode,Description", '0,20551,"Острый, %d урона\\nстрока"', "1,20552,Круглый",
                                                       "2,20552,Дубль", ""]))
    for t, kc in (("skill_info", "SkillCode"), ("skilltooltip", "Id")):
        _w(os.path.join(I, t + ".csv"), CRLF.join(["_row,%s,Name,Text" % kc, "0,0,Оледенение,Лёд", ""]))
    _w(os.path.join(I, "title_list.csv"), CRLF.join(["_row,Id,Name,Desc", "0,0,Зануда,Ищет отряд", ""]))
    _w(P["overlay"], "﻿table,key,column,old_value,new_value,source,reason,note\nitem_list,20551,ItemName,-,Меч,en,ru_missing,\n")
    _w(P["mobnames"], CRLF.join(["---,Name,Model", "0,Степной волк,mon_a", ""]))
    _w(P["npcnames"], CRLF.join(["---,Name,Model", "1,Луа,", ""]))
    reg = {"_comment": "образец", "maps": [{"id": 0, "dir": "silalis", "loc_name": "Силарис"}, {"id": 1, "dir": "rein", "loc_name": "Река Дождя"}]}
    _w(P["map_reg"], json.dumps(reg, ensure_ascii=False, indent=2) + "\n")
    _w(P["map_info"], MR.render_map_info_csv(reg))
    q = [{"FileName": "1_Qst_1", "Title": "\"Пропажа\"", "Desc": "Найди\r\nВуди", "Name": "1_Qst_1"}]
    _w(P["quest"], json.dumps(q, ensure_ascii=False, indent=0))
    _w(P["ru_dt"], json.dumps({"_comment": "образец", "rows": [{"row": "0", "field": "Name", "index": None, "sub": None, "was": "Степ волк", "now": "Степной волк",
                                                               "dt": "/Game/AsdaAssets/Data/Mob/DT_MobNames"},
                                                              {"row": "9npc", "field": "Text", "index": None, "sub": None, "was": "a", "now": "б",
                                                               "dt": "/Game/AsdaAssets/Data/NPC/DT_NpcNsrPage"}]}, ensure_ascii=False, indent=1).replace("\n", CRLF))
    en = {"item_list": ["0.ItemName,Sword"], "item_tooltip": ['0.Description,"Sharp, %d damage\\nline"'],
          "MobNames": ["0.Name,FieldWolf"], "Map_info": ["0.name,Silaris", "1.name,Rein River"], "QuestBook": ["1_Qst_1.Title,\"\"\"Lost\"\"\"", "1_Qst_1.Desc,\"Find\""],
          "skill_info": ["0.Name,Ice"], "skilltooltip": ["0.Name,Ice", "0.Text,Ice"], "title_list": ["0.Name,Boring"], "NpcNames": ["1.Name,Lua"]}
    for t, rows in en.items():
        raw = "﻿" + CRLF.join(["Name,Text"] + rows + [""])
        _w(os.path.join(P["en_dir"], "DT_Loc_%s_en.csv" % t), raw)
        _w(os.path.join(P["en_dir"], "_imported", "DT_Loc_%s_en.csv" % t), raw)
    _w(os.path.join(P["en_led"], "item_list.json"), json.dumps({"_comment": "образец", "rows": [
        {"key": "0.ItemName", "value": "Sword", "was": "Swrd", "why": "опечатка", "source": "typo_fix"}]}, ensure_ascii=False, indent=2) + "\n")
    return P


FAKE = {"excl": set(), "qst": {}}          # подмены извлечения EN и разбора .QST (тест задаёт расхождения)


def _qst_fake():
    """Подставной разбор .QST: строки фикстуры QuestBook.json без ведомости (или подмена FAKE["qst"])."""
    from domains.cs_kinds import texts as TX
    rows = json.loads(open(TX.P["quest"], "rb").read().decode("utf-8-sig"))
    for r in rows:
        r.update(FAKE["qst"].get(r["FileName"], {}))
    return rows


def _ext_fake(table, files):
    """Подставное извлечение EN: значения EN-CSV на диске, у ключей ведомости — её was; FAKE["excl"] — ключи, которые извлечение
    исключило (EN = RU / нет источника)."""
    from domains.cs_kinds import texts as TX
    import csv as _c
    import io as _io
    out = {r[0]: r[1] for r in list(_c.reader(_io.StringIO(open(TX.en_csv(table), "rb").read().decode("utf-8-sig"), newline="")))[1:]}
    lp = TX.en_ledger(table)
    if os.path.isfile(lp):
        for r in json.load(open(lp, encoding="utf-8"))["rows"]:
            if r.get("was") is not None:
                out[r["key"]] = r["was"]
    return {k: v for k, v in out.items() if (table, k) not in FAKE["excl"]}


def _regen_fake(binname):
    """Подставной декодер: значения «до слоя имён» (как дал бы архив Bin.bbz + ведомости)."""
    return {"item_list.bin": [{"_row": 0, "ItemCode": 20551, "ItemName": "-"}, {"_row": 1, "ItemCode": 20552, "ItemName": "Щит"}],
            "item_tooltip.bin": [{"_row": 0, "ItemCode": 20551, "Description": "Острый, %d урона\\nстрока"}],
            "skill_info.sif": [{"_row": 0, "SkillCode": 0, "Name": "Оледенение"}],
            "skilltooltip.bin": [{"_row": 0, "Id": 0, "Name": "Оледенение", "Text": "Лёд"}]}[binname]


class _Ev:
    def __init__(self):
        self.client = []


def _rep():
    return {"warnings": [], "errors": [], "client": []}


def _pos(ent, key, ru=None, en=None):
    from domains.cs_kinds import texts as TX
    ev, rep = _Ev(), _rep()
    TX.k_text_set(ev, TX.norm("text.set", {"entity": ent, "key": key, "ru": ru, "en": en}), rep)
    return ev, rep


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


class patched:
    """Подмена путей и декодера модуля texts на время блока (кэш снимка — сброс)."""

    def __init__(self, P):
        self.P = P

    def __enter__(self):
        from domains.cs_kinds import texts as TX
        self.saved = (dict(TX.P), TX._regen, TX._qst_parse, TX._en_extract)
        TX.P.clear()
        TX.P.update(self.P)
        TX._regen, TX._qst_parse, TX._en_extract = _regen_fake, _qst_fake, _ext_fake
        FAKE["excl"], FAKE["qst"] = set(), {}
        TX._cache.clear()
        return TX

    def __exit__(self, *a):
        from domains.cs_kinds import texts as TX
        TX.P.clear()
        TX.P.update(self.saved[0])
        TX._regen, TX._qst_parse, TX._en_extract = self.saved[1:]
        TX._cache.clear()
        return False


def offline(check):
    from domains import shopdata as SD
    tmp = tempfile.mkdtemp(prefix="asda_st_texts_")
    try:
        P = fixtures(tmp)
        check("А4.2 реестр: область «texts» (5-я), вид text.set, права data.edit / data.apply, title_list — в ведомостях ItemDB",
              SD.AREAS[4].AREA == "texts" and "text.set" in SD.KINDS and SD.area_perm("text.set", "apply") == "data.apply"
              and SD.area_perm("text.set", "edit") == "data.edit" and SD.LEDGER_TABLES.get("title_list") == "title_list.bin")
        with patched(P) as TX:
            ev, rep = _pos("item.name", "20551", "Меч героя", "Hero sword")
            e = ev.client[0]
            check("text.set: оба языка одной позицией — было → станет RU и EN, ключ EN = _row.колонка",
                  e["ru"] == ["Меч", "Меч героя"] and e["en"] == ["Sword", "Hero sword"] and e["en_key"] == "0.ItemName"
                  and "RU: «Меч» → «Меч героя»; EN: «Sword» → «Hero sword»" in rep["text"], (e, rep["text"]))
            ev1, rep1 = _pos("mob.name", "0", "Волк степей", None)
            check("text.set: один язык — явная пометка «EN не меняется»", ev1.client[0]["en"] is None
                  and any(w.startswith("EN не меняется") for w in rep1["warnings"]) and "EN не меняется" in rep1["text"], rep1)
            ev2, _r2 = _pos("title.name", "0", "Скука", None)
            check("text.set: звание RU — ещё и csv_cell title_list (движок: ведомость _value_overlay + генератор)",
                  [x["type"] for x in ev2.client] == ["text_set", "csv_cell"] and ev2.client[1]["new"] == "Скука", ev2.client)
            bad = {
                "ключа нет": _refused(lambda: _pos("item.name", "99999", "А")),
                "дубль ключа": _refused(lambda: _pos("item.desc", "20552", "А")),
                "перевод строки в имени": _refused(lambda: _pos("item.name", "20551", "Меч\nгероя")),
                "управляющий символ": _refused(lambda: _pos("item.name", "20551", "Меч\x07")),
                "пустой": _refused(lambda: _pos("item.name", "20551", "  ")),
                "пробел в конце": _refused(lambda: _pos("item.name", "20551", "Меч ")),
                "подстановка %d потеряна": _refused(lambda: _pos("item.desc", "20551", "Острый")),
                "звание > 63 байт cp1251": _refused(lambda: _pos("title.name", "0", "Я" * 64)),
                "звание вне cp1251": _refused(lambda: _pos("title.name", "0", "Зануда ☃")),
                "ничего не меняется": _refused(lambda: _pos("item.name", "20551", "Меч", "Sword")),
                "оба null": _refused(lambda: _pos("item.name", "20551")),
                "EN-строки нет": _refused(lambda: _pos("item.name", "20552", None, "Board")),
            }
            check("text.set: отказы (ключа нет, дубль, перевод строки, управляющий, пустой, пробел, подстановка, cp1251/ширина звания, "
                  "без изменений, оба null, EN-строки нет)", all(bad.values()), [k for k, v in bad.items() if not v])
            _e3, rep3 = _pos("item.desc", "20551", "Острый, %d урона\nвторая", None)
            check("text.set: перевод строки — в виде источника («\\n» двумя символами), подстановка сохранена",
                  _e3.client[0]["ru"][1] == "Острый, %d урона\\nвторая", _e3.client[0])
            _e4, rep4 = _pos("item.name", "20551", None, "Меч")
            check("text.set: EN с кириллицей — предупреждение", any("кириллица" in w for w in rep4["warnings"]), rep4["warnings"])
            # план клиентской половины на копиях
            edits = []
            for ent, key, ru, en in (("item.name", "20551", "Меч героя", "Hero sword"), ("item.desc", "20551", "Острый, %d урона\nвторая", None),
                                     ("mob.name", "0", "Волк степей", "Steppe wolf"), ("map.name", "1", "Дождливая река", "Rain River"),
                                     ("quest.title", "1_Qst_1", "\"Кража\"", None), ("skilltip.text", "0", "Холод", "Cold")):
                edits += _pos(ent, key, ru, en)[0].client
            tracked = [os.path.join(b, f) for b, _d, fs in os.walk(tmp) for f in fs]
            before = {p: _md5(p) for p in tracked}
            plan = SD.client_plan(edits, 77)
            after = {p: _md5(p) for p in tracked}
            nb = {os.path.relpath(p, tmp).replace("\\", "/"): plan["_bytes"][p].decode("utf-8-sig") for p in plan["files"]}
            ov = nb.get("_out/item_name_overlay.csv", "")
            check("план текстов: без ошибок, файлы порта не тронуты (md5 до = после)", not plan["errors"] and before == after, plan["errors"])
            check("план: рецепт имён — строка 20551 переписана на месте (old_value прежний «-», source=owner), строка описания дописана; "
                  "CSV и JSON ItemDB правлены", "item_list,20551,ItemName,-,Меч героя,owner,admin_cs" in ov
                  and "item_tooltip,20551,Description" in ov and ov.count("\n") == 4 and "Меч героя" in nb.get("ItemDB/item_list.json", "")
                  and "0,20551,Меч героя,10" in nb.get("ItemDB/item_list.csv", ""), ov)
            led = json.loads(nb.get("data/loc/en/item_list.json", "{}") or "{}")
            r0 = (led.get("rows") or [{}])[0]
            check("план: EN — DT_Loc_item_list_en.csv и ведомость loc/en (was прежний «Swrd», prev += «Sword», value новое); "
                  "ведомость MobNames заведена", r0.get("was") == "Swrd" and r0.get("prev") == ["Sword"] and r0.get("value") == "Hero sword"
                  and "0.ItemName,Hero sword" in nb.get("L10N/en/DT_Loc_item_list_en.csv", "")
                  and json.loads(nb["data/loc/en/MobNames.json"])["rows"][0]["was"] == "FieldWolf", (r0, sorted(nb)))
            check("план: карта — реестр loc_name и Map_info.csv рендером настоящего asda_map_registry",
                  '"loc_name": "Дождливая река"' in nb.get("data/asda_map_registry.json", "") and "1,1,Дождливая река" in nb.get("World/Map_info.csv", ""))
            rd = json.loads(nb.get("data/ru_dt_overrides.json", "{}"))
            check("план: задание — QuestBook.json + строка ru_dt_overrides (was = разбор, now = новое), JSON-точка DT_QuestBook",
                  rd["rows"][-1] == {"row": "1_Qst_1", "field": "Title", "index": None, "sub": None, "was": "\"Пропажа\"", "now": "\"Кража\"",
                                     "dt": TX.DT_QUEST} and plan["json_jobs"][0]["edits"][0]["now"] == "\"Кража\""
                  and nb.get("data/ru_dt_overrides.json", "").count(CRLF) > 3, rd["rows"][-1])
            dts = {j["dt"].rsplit("/", 1)[1]: j["allow_rows"] for j in plan["dt_jobs"]}
            check("план: точечные DT — по строкам (DT_item_list 0, DT_item_tooltip 0, DT_MobNames 0, DT_Map_info 1, DT_skilltooltip 0, "
                  "DT_Loc_*_en по ключам)", dts.get("DT_item_list") == ["0"] and dts.get("DT_item_tooltip") == ["0"] and dts.get("DT_MobNames") == ["0"]
                  and dts.get("DT_Map_info") == ["1"] and dts.get("DT_Loc_item_list_en") == ["0.ItemName"] and dts.get("DT_skilltooltip") == ["0"]
                  and dts.get("DT_Loc_skilltooltip_en") == ["0.Text"], dts)
            # сторожа
            e1 = _pos("item.name", "20551", "Меч героя", None)[0].client
            ovp = P["overlay"]
            keep = open(ovp, "rb").read()
            _w(ovp, keep.decode("utf-8").replace(",-,Меч,", ",-,Клинок,"))
            g1 = SD.client_plan(e1, 77)["errors"]
            _w(ovp, keep)
            TX._regen = lambda b: [{"_row": 0, "ItemCode": 20551, "ItemName": "Другое"}]
            g2 = SD.client_plan(e1, 77)["errors"]
            TX._regen = _regen_fake
            imp = os.path.join(P["en_dir"], "_imported", "DT_Loc_MobNames_en.csv")
            keep2 = open(imp, "rb").read()
            _w(imp, keep2 + b"9.Name,X\r\n")
            g3 = SD.client_plan(_pos("mob.name", "0", None, "Wolf")[0].client, 77)["errors"]
            _w(imp, keep2)
            keep3 = open(P["map_info"], "rb").read()
            _w(P["map_info"], keep3 + b"9,9,X\r\n")
            g4 = SD.client_plan(_pos("map.name", "0", "Силарис-2")[0].client, 77)["errors"]
            _w(P["map_info"], keep3)
            stale = _pos("npc.name", "1", "Луа-2")[0].client
            _w(P["npcnames"], CRLF.join(["---,Name,Model", "1,Луа (правка владельца),", ""]))
            g5 = SD.client_plan(stale, 77)["errors"]
            check("сторожа плана: CSV мимо рецепта, генератор ≠ «было» рецепта, EN-CSV ≠ _imported, Map_info ≠ реестру, источник сменился "
                  "после проверки — отказ", any("мимо рецепта" in x for x in g1) and any("генератор даёт" in x for x in g2)
                  and any("_imported" in x for x in g3) and any("рендеру реестра" in x for x in g4) and any("пересоберите" in x for x in g5),
                  (g1, g2, g3, g4, g5))
            # ★ ревизия 34
            g = {}
            imp = os.path.join(P["en_dir"], "_imported", "DT_Loc_QuestBook_en.csv")
            keep_i = open(imp, "rb").read()
            _w(imp, keep_i.decode("utf-8").replace('"Find"', "Find"))         # те же значения, другие байты (как после csv.writer)
            g["М-1 значения = копии"] = not SD.client_plan(_pos("quest.desc", "1_Qst_1", None, "Find it")[0].client, 77)["errors"]
            _w(imp, keep_i)
            FAKE["qst"] = {"1_Qst_1": {"Title": "\"Иное\""}}
            e_q = SD.client_plan(_pos("quest.title", "1_Qst_1", "\"Кража\"")[0].client, 77)["errors"]
            g["М-3 задание: JSON ≠ разбору .QST — отказ"] = any("разбор .QST даёт" in x for x in e_q)
            FAKE["qst"] = {}
            FAKE["excl"] = {("item_list", "0.ItemName")}
            e_en = SD.client_plan(_pos("item.name", "20551", None, "Hero")[0].client, 77)["errors"]
            g["М-3 EN: извлечение ≠ was ведомости — отказ"] = any("генерация оверлеев встала бы" in x for x in e_en)
            FAKE["excl"] = {("Map_info", "1.name")}           # у карт EN ищется по RU-тексту: после правки RU извлечение строки не даёт
            pm = SD.client_plan(_pos("map.name", "1", "Дождливая река", "Rain River")[0].client, 77)
            lm = json.loads(pm["_bytes"].get(os.path.join(P["en_led"], "Map_info.json"), b"{}").decode("utf-8") or "{}")
            g["М-3 карта RU + EN: новая строка loc/en получает was = извлечению «станет» (null), генерация не встанет"] = \
                not pm["errors"] and lm and lm["rows"][0]["was"] is None
            FAKE["excl"] = {("MobNames", "0.Name")}
            pl = SD.client_plan(_pos("mob.name", "0", "FieldWolf")[0].client, 77)
            g["К-4 RU = EN: строка пропадёт — предупреждение"] = any("строка пропадёт" in w for w in pl["warnings"])
            FAKE["excl"] = set()
            rdm = json.loads(pl["_bytes"].get(P["ru_dt"], b"{}").decode("utf-8") or "{}")
            g["К-1 строка DT_MobNames в ru_dt_overrides: now = новое"] = rdm and rdm["rows"][0]["now"] == "FieldWolf"
            _ev2, rk = _pos("npc.name", "1", "Луа-2")
            g["К-2 npc.name: предупреждение про DT_NpcNsrHeader"] = any("DT_NpcNsrHeader" in w for w in rk["warnings"])
            _ev3, rk5 = _pos("mob.name", "0", "Волк")
            g["К-5 DT_MobQuestDrop: предупреждение"] = any("DT_MobQuestDrop" in w for w in rk5["warnings"])
            _ev4, rk4 = _pos("mob.name", "0", "FieldWolf")
            g["К-4 RU = EN: предупреждение позиции"] = any("RU = EN" in w for w in rk4["warnings"])
            g["К-3 позиция несёт снимок (md5 источников)"] = bool(_ev4.client[0]["snap"]["md5"])
            ET = TX._tool("extract_text_tables")
            g["М-2 extract_text_tables не пишет Map_info.csv"] = not any(x[0] == "Map_info.BIN" for x in ET.TABLES)
            check("ревизия 34: М-1, М-2, М-3 (задания и EN), К-1…К-5", all(g.values()), [k for k, v in g.items() if not v])
            s = TX.search("item.name", "щит")
            check("поиск: по тексту без регистра и по коду", [r["key"] for r in s["rows"]] == ["20552"]
                  and TX.search("item.name", "20551")["rows"][0]["en"] == "Sword", s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sandbox(check, ldb):
    """Путь набора «Тексты» через операции (LocalDB, подменная стойка): создать → позиции → проверить → утвердить → сухой прогон
    клиента → применить (бэкап, файлы, точечные DT и JSON-точка DT_QuestBook через подставную очередь UE) → откат (всё вернулось);
    ассет правил владелец — применение отказывает."""
    import selftest_shops_sandbox as X
    from core import ops
    from domains import shopcs, shopdata as SD
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with X.sandbox(ldb) as (st, env):
        d = os.path.join(env["tmp"], "texts")
        P = fixtures(d)
        with patched(P) as TX:
            real = shopcs._ue_run
            jp = []

            def ue_run(script, log, marker, env=None, expect=None, require=None):
                if script == "asda_dt_json_point.py":
                    jobs = json.load(open(env["ASDA_JP_JOBS"], encoding="utf-8"))
                    if not env.get("ASDA_JP_DRYRUN"):
                        jp.append(jobs)
                    return 0, "ЗАВЕРШЕНО: JSON-точечные DT"
                rc, out = real(script, log, marker, env, expect, require)
                if script == "asda_ml_dt_point.py" and rc == 0 and not env.get("ASDA_PT_DRYRUN"):
                    # как настоящий asda_ml_dt_point.py:132 — копия _imported оверлея теми же ячейками (настоящий overlay_snapshot_apply)
                    L = TX._tool("asda_ledger")
                    for j in json.load(open(env["ASDA_PT_JOBS"], encoding="utf-8")):
                        a, b = TX._loc_values(open(j["csv_old"], "rb").read()), TX._loc_values(open(j["csv_new"], "rb").read())
                        L.overlay_snapshot_apply(j["dt"], {k: b[k] for k in b if a.get(k) != b[k]}, lambda m: None,
                                                 root=os.path.dirname(P["en_dir"]))
                return rc, out
            shopcs._ue_run = ue_run
            try:
                for dtp, f in ((TX.ENT["item.name"]["dt"], os.path.join(P["itemdb"], "item_list.csv")),
                               ("/Game/AsdaAssets/Text/L10N/en/DT_Loc_item_list_en", TX.en_csv("item_list")),
                               (TX.ENT["mob.name"]["dt"], P["mobnames"]),
                               ("/Game/AsdaAssets/Text/L10N/en/DT_Loc_QuestBook_en", TX.en_csv("QuestBook"))):
                    st.assets[dtp] = open(f, "rb").read()
                tracked = [os.path.join(b, f) for b, _d, fs in os.walk(d) for f in fs]
                orig = {p: _md5(p) for p in tracked}
                cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.2", note="самотест песочницы текстов")["result"]["id"]
                X._run(ctx, "shop.cs_item_add", cs=cid, kind="text.set", params={"entity": "item.name", "key": "20551", "ru": "Меч героя", "en": "Hero sword"})
                X._run(ctx, "shop.cs_item_add", cs=cid, kind="text.set", params={"entity": "quest.title", "key": "1_Qst_1", "ru": "\"Кража\"", "en": None})
                X._run(ctx, "shop.cs_check", cs=cid)
                cs = shopcs.get(cid)
                X._run(ctx, "shop.cs_approve", cs=cid)
                X._run(ctx, "shop.cs_client_dry", cs=cid)
                X._run(ctx, "shop.cs_client_apply", cs=cid)
                csv1 = open(os.path.join(P["itemdb"], "item_list.csv"), encoding="utf-8").read()
                check("песочница А4.2: проверен (без сервера), утверждён, клиент применён — CSV, рецепт, JSON-точка DT_QuestBook, точечные DT",
                      cs["check"]["ok"] and not cs["check"]["server_needed"] and shopcs.get(cid)["client_state"] == "applied"
                      and "Меч героя" in csv1 and "Меч героя" in open(P["overlay"], encoding="utf-8").read() and len(jp) == 1
                      and st.assets[TX.ENT["item.name"]["dt"]] == open(os.path.join(P["itemdb"], "item_list.csv"), "rb").read(),
                      (cs["check"]["errors"], jp))
                X._run(ctx, "shop.cs_client_rollback", cs=cid)
                now = {p: _md5(p) for p in tracked}
                check("песочница А4.2: откат клиента — все файлы прежние (md5), JSON-точка обратно (was ↔ now)",
                      now == orig and len(jp) == 2 and jp[1][0]["edits"][0]["now"] == "\"Пропажа\"",
                      [os.path.relpath(p, d) for p in tracked if now[p] != orig[p]])
                # ★ ревизия 34 М-1: две позиции EN заданий подряд (после первой заливки копия _imported переписана csv.writer-ом)
                ok_seq = []
                for n, txt in enumerate(("Find it", "Find it now")):
                    c3 = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.2 — EN %d" % n, note="самотест: EN заданий подряд")["result"]["id"]
                    X._run(ctx, "shop.cs_item_add", cs=c3, kind="text.set", params={"entity": "quest.desc", "key": "1_Qst_1", "ru": None, "en": txt})
                    X._run(ctx, "shop.cs_check", cs=c3)
                    X._run(ctx, "shop.cs_approve", cs=c3)
                    _r3, no3 = X._try(ctx, "shop.cs_client_dry", cs=c3)
                    if not no3:
                        _r3, no3 = X._try(ctx, "shop.cs_client_apply", cs=c3)
                    ok_seq.append(no3)
                imp = open(os.path.join(P["en_dir"], "_imported", "DT_Loc_QuestBook_en.csv"), "rb").read()
                check("ревизия 34 М-1: вторая позиция EN заданий после первой заливки проходит (копия _imported переписана настоящим "
                      "overlay_snapshot_apply, байты ≠ CSV, значения =)", ok_seq == [None, None]
                      and imp != open(TX.en_csv("QuestBook"), "rb").read() and "Find it now" in imp.decode("utf-8"), ok_seq)
                cid2 = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.2 — ассет", note="самотест: ассет правил владелец")["result"]["id"]
                X._run(ctx, "shop.cs_item_add", cs=cid2, kind="text.set", params={"entity": "mob.name", "key": "0", "ru": "Волк", "en": None})
                X._run(ctx, "shop.cs_check", cs=cid2)
                X._run(ctx, "shop.cs_approve", cs=cid2)
                X._run(ctx, "shop.cs_client_dry", cs=cid2)
                own = "---,Name,Model\r\n0,Волк владельца,mon_a\r\n".encode("utf-8")
                st.assets[TX.ENT["mob.name"]["dt"]] = own
                _r, no = X._try(ctx, "shop.cs_client_apply", cs=cid2)
                check("песочница А4.2: DT_MobNames правил владелец (ассет ≠ прежнему CSV) — применение отказывает, ассет не тронут",
                      no and "DT_MobNames" in no and st.assets[TX.ENT["mob.name"]["dt"]] == own, no)
            finally:
                shopcs._ue_run = real


def live(check):
    """Только чтение: снимок текстов порта, поиск, оценка позиции по каждому виду и план клиентской половины с НАСТОЯЩИМ декодером
    ItemDB и инструментами порта — файлы порта md5 до = после."""
    from core import config
    from domains import shopdata as SD
    from domains.cs_kinds import texts as TX
    if config.get().on_server:
        return check("живой самотест текстов — с ПК (порт)", True)
    d, src = TX.texts(force=True)
    n = {k: len(v) for k, v in d["ent"].items()}
    check("живой снимок текстов порта: 12 видов, у каждого есть записи", src == "port" and len(n) == 12 and all(n.values()), n)
    edits, errs = [], []
    for ent in TX.ENT:
        k, v = next((k, v) for k, v in d["ent"][ent].items() if v[2] is not None and v[3] == 1 and len(v[0]) > 3)
        m = TX.ENT[ent]["multi"]
        try:
            edits += _pos(ent, k, v[0] + ("\nX" if m else " X") if TX.ENT[ent]["src"] != "vo" else v[0][:30] + " X", v[2] + ("\nY" if m else " Y"))[0].client
        except Exception as ex:
            errs.append("%s %s: %s" % (ent, k, ex))
    paths = set(TX._sources()) | {TX.P["overlay"], TX.P["ru_dt"], TX.P["map_reg"]} | {TX.en_ledger(e["en"][0]) for e in TX.ENT.values()}
    paths |= set(SD.all_ledger_paths()) | {os.path.join(TX.P["itemdb"], e["table"] + ".json") for e in TX.ENT.values() if e["src"] == "ov"}
    paths = [p for p in paths if os.path.isfile(p)]
    before = {p: _md5(p) for p in paths}
    plan = SD.client_plan(edits, 0)
    after = {p: _md5(p) for p in paths}
    check("живой план текстов (12 видов, RU + EN): настоящий декодер ItemDB, рецепт имён, реестр карт, ru_dt_overrides, loc/en — без "
          "ошибок; ничего не записано (md5 до = после)", not errs and not plan["errors"] and before == after and len(plan["dt_jobs"]) >= 15
          and len(plan["json_jobs"]) == 2, (errs, plan["errors"][:4], len(plan["dt_jobs"])))
