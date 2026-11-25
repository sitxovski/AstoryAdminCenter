# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/texts.py — область «Тексты RU / EN» (волна А4.2, 19.11.2026; разбор Reports/admin_center/research_a4_data.md §1.7, §5).

ТОЛЬКО КЛИЕНТ. Сервер этих текстов игроку не отдаёт: ItemTable_Info\\ItemName_Table.txt GameServer грузит (GameServer.c:68325 →
dword_5F5E94), но в срезе декомпила ссылок на таблицу, кроме загрузки и освобождения (:66379), нет — пары с сервером не делается.
Только правка СУЩЕСТВУЮЩИХ текстов (решение владельца 19.11: без новых записей). Одна позиция — оба языка: «ru» / «en» — новый текст
или null = «этот язык не меняется» (явная пометка в итоге проверки).

Каждый вид пишет туда, откуда текст переживает перегенерацию (правило itemdb-ledger-overlays, owner-asset-edits-never-lose):
  RU предметы / навыки (item_list.ItemName, item_tooltip.Description, skill_info.Name, skilltooltip.Name/Text) — СЛОЙ-РЕЦЕПТ ИМЁН
     Tools/_out/itemdb_overlay/item_name_overlay.csv (строка source=owner: asda_build_name_overlay.py её сохраняет; накладывает
     asda_apply_name_overlay.py — сам декодер decode_item_db при выгрузке) + CSV/JSON ItemDB порта + точечный DT;
     доказательство — НАСТОЯЩИЙ декодер (значение до слоя) и НАСТОЯЩИЙ load_overlay/classify рецепта;
  RU звания (title_list.Name/Desc) — ведомость _value_overlay/title_list.csv (движок shopdata.ledger_plan, доказательство генератором;
     строка ложится в БАЙТЫ записи: cp1251, меньше 64 байт);
  RU мобы / NPC (Tools/generated/DT_MobNames.csv, DT_NpcNames.csv) — генератора в Tools нет, файл сам источник → правка на месте + DT;
  RU карты — реестр Tools/data/asda_map_registry.json (loc_name) → Map_info.csv рендером НАСТОЯЩЕГО asda_map_registry → DT_Map_info;
  RU задания (QuestBook.json Title/Desc) — ведомость Tools/data/ru_dt_overrides.json (импортёр asda_import_quest_tables применяет её
     после разбора .QST; проверка настоящим asda_ru_dt_overrides.apply_rows) + DT_QuestBook через asda_dt_json_point.py;
  EN все виды — ведомость Tools/data/loc/en/<Т>.json (extract_text_lang применяет её после извлечения; решение — настоящий
     asda_ledger.classify_row) + RawAssets/Text/L10N/en/DT_Loc_<Т>_en.csv + точечный DT_Loc_<Т>_en (asda_ml_dt_point обновляет и
     копию _imported — сторож import_text_lang).
Сторожа ручной правки: «было» позиции = живому файлу (иначе «пересоберите»), ведомость = файлу (иначе «правили мимо ведомости»),
EN-CSV = последней заливке _imported (иначе ассет и CSV разошлись), ассет DT = прежнему CSV/«было» (asda_ml_dt_point / dt_json_point).
Служба на сервере не видит RawAssets: оценка и поиск — по снимку data/ref/text_client.json (строит выкладка на ПК).
Побочных эффектов при импорте нет.
"""
import contextlib
import csv
import datetime
import io
import json
import os
import re
import sys
import tempfile
import threading
import zipfile

from core import config
from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "texts", "Тексты RU / EN"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = False                  # тексты баланс не меняют
SRV_FILES = []                        # сервер текстов не читает (см. шапку)
KINDS = {"text.set": ("Тексты: название / описание RU и EN (только правка существующих)", ("entity", "key", "ru", "en"), False)}
CLIENT_FILES = {"title_list": os.path.join(E.ITEMDB, "title_list.csv")}   # RU званий — общим путём движка (ведомость _value_overlay)
DT = {"title_list": "/Game/AsdaAssets/Data/ItemDB/DT_title_list"}
CSV_KEYS = ("title_list",)
SNAPSHOT = os.path.join(config.DATA_DIR, "ref", "text_client.json")         # снимок текстов для службы на сервере

# Пути порта (тест подменяет словарь целиком — песочница на копиях)
P = {
    "itemdb": E.ITEMDB,
    "overlay": os.path.join(E.UE_TOOLS, "_out", "itemdb_overlay", "item_name_overlay.csv"),
    "mobnames": os.path.join(E.UE_TOOLS, "generated", "DT_MobNames.csv"),
    "npcnames": os.path.join(E.UE_TOOLS, "generated", "DT_NpcNames.csv"),
    "map_reg": os.path.join(E.UE_TOOLS, "data", "asda_map_registry.json"),
    "map_info": os.path.join(E.UPROJ, "RawAssets", "Text", "World", "Map_info.csv"),
    "quest": os.path.join(E.UPROJ, "RawAssets", "Data", "Quest", "QuestBook.json"),
    "ru_dt": os.path.join(E.UE_TOOLS, "data", "ru_dt_overrides.json"),
    "en_dir": os.path.join(E.UPROJ, "RawAssets", "Text", "L10N", "en"),
    "en_led": os.path.join(E.UE_TOOLS, "data", "loc", "en"),
}
DTI = "/Game/AsdaAssets/Data/ItemDB/"
DT_QUEST = "/Game/AsdaAssets/Data/Quest/DT_QuestBook"
# Вид текста: src — откуда RU (ov — слой-рецепт имён ItemDB, vo — ведомость значений ItemDB, gen — CSV-источник без генератора,
# map — реестр карт, quest — QuestBook + ru_dt_overrides); table/kc/col — таблица, колонка ключа, колонка текста; en — (таблица
# оверлея, поле); multi — допускается перевод строки; max — предел символов; width — байтов поля в записи (cp1251, только vo)
ENT = {
    "item.name": dict(title="Предмет: название", src="ov", table="item_list", bin="item_list.bin", kc="ItemCode", col="ItemName",
                      en=("item_list", "ItemName"), dt=DTI + "DT_item_list", multi=False, max=120, orig=64),
    "item.desc": dict(title="Предмет: описание", src="ov", table="item_tooltip", bin="item_tooltip.bin", kc="ItemCode", col="Description",
                      en=("item_tooltip", "Description"), dt=DTI + "DT_item_tooltip", multi=True, max=4000),
    "skill.name": dict(title="Навык: название (skill_info)", src="ov", table="skill_info", bin="skill_info.sif", kc="SkillCode", col="Name",
                       en=("skill_info", "Name"), dt=DTI + "DT_skill_info", multi=False, max=120),
    "skilltip.name": dict(title="Навык: название подсказки (skilltooltip)", src="ov", table="skilltooltip", bin="skilltooltip.bin", kc="Id",
                          col="Name", en=("skilltooltip", "Name"), dt=DTI + "DT_skilltooltip", multi=False, max=120, orig=32),
    "skilltip.text": dict(title="Навык: текст подсказки (skilltooltip)", src="ov", table="skilltooltip", bin="skilltooltip.bin", kc="Id",
                          col="Text", en=("skilltooltip", "Text"), dt=DTI + "DT_skilltooltip", multi=True, max=4000),
    "title.name": dict(title="Звание: название", src="vo", table="title_list", kc="Id", col="Name", en=("title_list", "Name"),
                       dt=DTI + "DT_title_list", multi=False, max=63, width=64),
    "title.desc": dict(title="Звание: описание", src="vo", table="title_list", kc="Id", col="Desc", en=("title_list", "Desc"),
                       dt=DTI + "DT_title_list", multi=False, max=63, width=64),
    "mob.name": dict(title="Монстр: имя", src="gen", table="mobnames", kc="---", col="Name", en=("MobNames", "Name"),
                     dt="/Game/AsdaAssets/Data/Mob/DT_MobNames", multi=False, max=120),
    "npc.name": dict(title="NPC: имя", src="gen", table="npcnames", kc="---", col="Name", en=("NpcNames", "Name"),
                     dt="/Game/AsdaAssets/Data/NPC/DT_NpcNames", multi=False, max=120),
    "map.name": dict(title="Карта: название", src="map", table="map_info", kc="Name", col="name", en=("Map_info", "name"),
                     dt="/Game/AsdaAssets/Text/World/DT_Map_info", multi=False, max=120),
    "quest.title": dict(title="Задание: заголовок", src="quest", col="Title", en=("QuestBook", "Title"), dt=DT_QUEST, multi=False, max=200),
    "quest.desc": dict(title="Задание: описание", src="quest", col="Desc", en=("QuestBook", "Desc"), dt=DT_QUEST, multi=True, max=8000),
}
SHOW = 80                             # символов текста в строке итога проверки


# =====================================================================================================================
# CSV: разбор со смещениями (правка ячейки «на месте» — остальные байты файла не меняются)
# =====================================================================================================================
def _dec(raw):
    """Байты CSV → (bom, текст)."""
    bom = raw.startswith(b"\xef\xbb\xbf")
    return bom, (raw[3:] if bom else raw).decode("utf-8")


def _enc(bom, text):
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def scan(text):
    """CSV-текст → записи [(начало, конец, [(нач. поля, кон. поля, в кавычках, значение)])] — как csv.reader (excel)."""
    out, i, n = [], 0, len(text)
    while i < n:
        rs, fields = i, []
        while True:
            fs = i
            if i < n and text[i] == '"':
                j, buf = i + 1, []
                while True:
                    k = text.find('"', j)
                    if k < 0:
                        raise ValueError("незакрытая кавычка в CSV (символ %d)" % fs)
                    buf.append(text[j:k])
                    if k + 1 < n and text[k + 1] == '"':
                        buf.append('"')
                        j = k + 2
                        continue
                    i = k + 1
                    break
                fields.append((fs, i, True, "".join(buf)))
            else:
                while i < n and text[i] not in ',\r\n':
                    i += 1
                fields.append((fs, i, False, text[fs:i]))
            if i < n and text[i] == ",":
                i += 1
                continue
            break
        re_ = i
        if text.startswith("\r\n", i):
            i += 2
        elif i < n and text[i] in "\r\n":
            i += 1
        out.append((rs, re_, fields))
    return out


def _quote(v, was_quoted):
    return '"' + v.replace('"', '""') + '"' if was_quoted or any(c in v for c in ',"\r\n') or v != v.strip() else v


CR, LF, CRLF = chr(13), chr(10), chr(13) + chr(10)   # переводы строк
SLOW_MAX = 8 << 20                    # байт: разбор со смещениями (медленный, на Python) — только для небольших файлов


def _ser(rows, lt):
    b = io.StringIO()
    csv.writer(b, lineterminator=lt).writerows(rows)
    return b.getvalue()


class Csv:
    """Один CSV-файл порта в памяти: поиск записи по ключу и правка ячейки. Если csv.writer воспроизводит файл побайтно — правка через
    строки (быстро), иначе — на месте по смещениям записей (остальные байты файла не меняются)."""

    def __init__(self, raw, label):
        self.label = label
        self.bom, self.text = _dec(raw)
        self.rows = list(csv.reader(io.StringIO(self.text, newline="")))
        self.lt = CRLF if CRLF in self.text[:4096] else LF
        self.fast = _ser(self.rows, self.lt) == self.text
        if not self.fast:
            if len(raw) > SLOW_MAX:
                raise OpRefused("%s: csv-запись не воспроизводит файл, а для разбора со смещениями он велик — правка не делается" % label)
            self.recs = scan(self.text)
            if [[f[3] for f in r[2]] for r in self.recs] != self.rows:
                raise OpRefused("%s: разбор CSV со смещениями не совпал с csv.reader — правка не делается" % label)
        self.head = self.rows[0]

    def col(self, name):
        if name not in self.head:
            raise OpRefused("%s: нет колонки %s" % (self.label, name))
        return self.head.index(name)

    def find(self, kc, key):
        ki = self.col(kc)
        return [j for j, r in enumerate(self.rows[1:], 1) if len(r) > ki and r[ki] == key]

    def value(self, j, c):
        return self.rows[j][self.col(c)]

    def set(self, j, cells):
        """cells {колонка: значение} → правка одной записи."""
        if not self.fast:
            r = self.recs[j]
            t = self.text
            for (fs, fe, q, _v), v in sorted(((r[2][self.col(c)], v) for c, v in cells.items()), key=lambda x: -x[0][0]):
                t = t[:fs] + _quote(v, q) + t[fe:]
            self.text = t
            self.recs = scan(t)
        for c, v in cells.items():
            self.rows[j][self.col(c)] = v

    def append(self, cells):
        cells = [str(v) for v in cells]
        if not self.fast:
            if self.text and not self.text.endswith((LF, CR)):
                self.text += self.lt
            self.text += ",".join(_quote(v, False) for v in cells) + self.lt
            self.recs = scan(self.text)
        self.rows.append(cells)

    def data(self):
        return _enc(self.bom, _ser(self.rows, self.lt) if self.fast else self.text)


def _same_but(old_raw, new_raw, allowed, label):
    """Сверка «изменились только разрешённые ячейки»: allowed {(номер записи, колонка)}; число записей — то же (или +1 в конце)."""
    a = list(csv.reader(io.StringIO(_dec(old_raw)[1], newline="")))
    b = list(csv.reader(io.StringIO(_dec(new_raw)[1], newline="")))
    if len(b) not in (len(a), len(a) + 1) or a[0] != b[0]:
        return "%s: изменилось число строк или шапка" % label
    for j, (x, y) in enumerate(zip(a, b)):
        for c, (u, v) in enumerate(zip(x, y)):
            if u != v and (j, a[0][c]) not in allowed:
                return "%s: строка %d, колонка %s изменилась вне правки" % (label, j, a[0][c])
        if len(x) != len(y):
            return "%s: строка %d изменила число колонок" % (label, j)
    return None


# =====================================================================================================================
# Проверка текста (длина, символы, переводы строк, подстановки)
# =====================================================================================================================
_PF = re.compile(r"%(%|[-+#0]*\d*(?:\.\d+)?(?:hh|h|ll|l|I64|I32)?([diouxXfeEgGcs]))")   # = extract_text_lang._PF
_MK = re.compile(r"\[(?:ss|sd|sf)\d+\]")                                                 # = extract_text_lang._MK


def _sig(s):
    """Подстановки строки: типы printf (без %%) и маркеры [ssN]/[sdN] — их ставит код игры."""
    return [m.group(2) for m in _PF.finditer(s or "") if m.group(1) != "%"], sorted(_MK.findall(s or ""))


def fit_nl(new, old):
    """Перевод строки нового текста — в виде старого: «\\n» двумя символами, CRLF или LF."""
    new = new.replace("\r\n", "\n")
    if "\\n" in (old or "") and "\n" not in (old or ""):
        return new.replace("\n", "\\n")
    if "\r\n" in (old or ""):
        return new.replace("\n", "\r\n")
    return new


def check_text(ent, lang, new, old, rep):
    """Новый текст одного языка → нормализованный текст (отказ — OpRefused; предупреждения — в rep)."""
    e = ENT[ent]
    if not isinstance(new, str):
        raise OpRefused("%s: текст — строка" % lang)
    if "\r" in new.replace("\r\n", "") or ("\n" in new and not e["multi"]):
        raise OpRefused("%s: в этом поле перевод строки не допускается (однострочное)" % lang)
    if "\t" in new and not e["multi"]:
        raise OpRefused("%s: табуляция в однострочном поле не допускается" % lang)
    bad = sorted({"U+%04X" % ord(c) for c in new if (ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127
                  or 0xD800 <= ord(c) <= 0xDFFF or c in "﻿�​"})
    if bad:
        raise OpRefused("%s: запрещённые символы %s (управляющие, BOM, U+FFFD, суррогаты)" % (lang, ", ".join(bad[:5])))
    if not new.strip():
        raise OpRefused("%s: пустой текст не допускается" % lang)
    if not e["multi"] and new != new.strip():
        raise OpRefused("%s: пробелы в начале или в конце однострочного текста не допускаются" % lang)
    new = fit_nl(new, old)
    if len(new) > e["max"]:
        raise OpRefused("%s: %d символов — больше предела %d" % (lang, len(new), e["max"]))
    if lang == "RU" and e.get("width"):
        try:
            enc = new.encode("cp1251")
        except UnicodeEncodeError:
            raise OpRefused("RU: символ вне cp1251 — строка звания ложится в байты записи title_list (cp1251)")
        if len(enc) >= e["width"]:
            raise OpRefused("RU: %d байт cp1251 — поле записи title_list %d байт (с нулём в конце)" % (len(enc), e["width"]))
    if _sig(new) != _sig(old):
        raise OpRefused("%s: подстановки (printf и [ssN]) не совпадают с прежним текстом: было %s, станет %s — код игры подставит не то"
                        % (lang, _sig(old), _sig(new)))
    if new.count("<FC=") != new.count("</F>") and old.count("<FC=") == old.count("</F>"):
        raise OpRefused("%s: цветовые теги <FC=…> и </F> не парные" % lang)
    cp = "cp1251" if lang == "RU" else "cp1252"
    try:
        new.encode(cp)
    except UnicodeEncodeError:
        rep["warnings"].append("%s: есть символы вне %s — шрифт клиента может их не показать" % (lang, cp))
    cyr = any("а" <= c.lower() <= "я" or c in "ёЁ" for c in new)
    if lang == "RU" and not cyr and any("а" <= c.lower() <= "я" for c in old):
        rep["warnings"].append("RU: в новом тексте нет кириллицы")
    if lang == "EN" and cyr:
        rep["warnings"].append("EN: в английском тексте есть кириллица")
    if e.get("orig") and len(new) >= e["orig"]:
        rep["warnings"].append("%s: %d символов — в оригинале поле %d байт, длинный текст может не влезть в окно" % (lang, len(new), e["orig"]))
    return new


# =====================================================================================================================
# Снимок текстов (ПК — живые файлы, служба — data/ref/text_client.json)
# =====================================================================================================================
def _read_dict(path):
    csv.field_size_limit(1 << 30)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def en_csv(table):
    return os.path.join(P["en_dir"], "DT_Loc_%s_en.csv" % table)


def en_ledger(table):
    return os.path.join(P["en_led"], "%s.json" % table)


def ru_csv(ent):
    e = ENT[ent]
    if e["src"] in ("ov", "vo"):
        return os.path.join(P["itemdb"], e["table"] + ".csv")
    return P[e["table"]] if e["src"] in ("gen", "map") else P["quest"]


def _sources():
    s = {ru_csv(k) for k in ENT} | {en_csv(e["en"][0]) for e in ENT.values()}
    return sorted(s)


def sources_present():
    """Есть ли на этом ПК тексты клиента (RU CSV item_list в AstoryClient/RawAssets) — без них снимок не строится (публичный клон)."""
    return os.path.isfile(ru_csv("item.name"))


def build_snapshot():
    """{built, md5, ent: {вид: {ключ: [RU, ключ EN, EN | None, записей RU]}}} — тексты порта (только ПК)."""
    en = {}
    for e in ENT.values():
        t = e["en"][0]
        if t not in en:
            p = en_csv(t)
            en[t] = {r["Name"]: r["Text"] for r in _read_dict(p)} if os.path.isfile(p) else {}
    out = {"built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "md5": {}, "ent": {}}
    quest = None
    for k, e in ENT.items():
        p = ru_csv(k)
        out["md5"][E.rel_area(p)] = E.md5f(p) if os.path.isfile(p) else "none"
        pe = en_csv(e["en"][0])                         # ★ ревизия 34 К-3: md5 источников вида (RU, EN) — план ПК сверит с живым портом
        out.setdefault("md5e", {})[k] = [out["md5"][E.rel_area(p)], E.md5f(pe) if os.path.isfile(pe) else "none"]
        d = {}
        if e["src"] == "quest":
            if quest is None:
                quest = json.loads(open(P["quest"], "rb").read().decode("utf-8-sig")) if os.path.isfile(P["quest"]) else []
            for r in quest:
                ek = "%s.%s" % (r["Name"], e["col"])
                d[r["Name"]] = [r.get(e["col"], ""), ek, en[e["en"][0]].get(ek), 1]
        elif os.path.isfile(p):
            for r in _read_dict(p):
                key = r[e["kc"]]
                rid = r["_row"] if e["src"] in ("ov", "vo") else key
                ek = "%s.%s" % (rid, e["en"][1])
                if key in d:
                    d[key][3] += 1
                    continue
                d[key] = [r.get(e["col"], ""), ek, en[e["en"][0]].get(ek), 1]
        out["ent"][k] = d
    return out


_lock = threading.Lock()
_cache = {}


def texts(force=False):
    """Тексты для оценки и поиска: на ПК — из живых файлов (кэш по mtime), на сервере — снимок выкладки."""
    with _lock:
        if config.get().on_server or not os.path.isfile(ru_csv("item.name")):
            if not os.path.isfile(SNAPSHOT):
                raise OpRefused("снимок текстов клиента не собран (data/ref/text_client.json): на ПК выкладки нет AstoryClient/RawAssets — "
                                "раздел «Тексты» недоступен")
            mt = os.path.getmtime(SNAPSHOT)
            hit = _cache.get("snap")
            if force or not hit or hit[0] != mt:
                _cache["snap"] = (mt, json.load(open(SNAPSHOT, encoding="utf-8")), "snapshot")
            return _cache["snap"][1], "snapshot"
        key = tuple(os.path.getmtime(p) if os.path.isfile(p) else 0 for p in _sources()) + (tuple(sorted(P.items())),)
        hit = _cache.get("port")
        if force or not hit or hit[0] != key:
            _cache["port"] = (key, build_snapshot())
        return _cache["port"][1], "port"


def search(ent, q, limit=60):
    """Поиск по коду (ключу) или по тексту RU/EN (без регистра) → строки для редактора."""
    if ent not in ENT:
        raise OpRefused("неизвестный вид текста %s" % ent)
    d, source = texts()
    rows = d["ent"].get(ent, {})
    q = (q or "").strip()
    ql = q.lower()
    hit = []
    if q and q in rows:
        hit.append(q)
    for k, v in rows.items():
        if len(hit) >= limit:
            break
        if k != q and (not q or ql in k.lower() or ql in (v[0] or "").lower() or ql in (v[2] or "").lower()):
            hit.append(k)
    return {"entity": ent, "source": source, "built": d.get("built"), "total": len(rows),
            "rows": [{"key": k, "ru": rows[k][0], "en": rows[k][2], "en_key": rows[k][1], "dup": rows[k][3]} for k in hit]}


def entities():
    return [{"id": k, "title": e["title"], "multi": e["multi"], "max": e["max"], "en_table": e["en"][0]} for k, e in ENT.items()]


# =====================================================================================================================
# Позиция
# =====================================================================================================================
def norm(kind, p):
    ent = str(p.get("entity") or "").strip()
    if ent not in ENT:
        raise OpRefused("неизвестный вид текста %s" % ent)
    key = str(p.get("key") if p.get("key") is not None else "").strip()
    if not key or len(key) > 64 or any(c in key for c in ",\r\n\""):
        raise OpRefused("ключ текста: непустой, до 64 символов, без запятых, кавычек и переводов строки")
    out = {"entity": ent, "key": key}
    for lang in ("ru", "en"):
        v = p.get(lang)
        if v is not None and not isinstance(v, str):
            raise OpRefused("поле «%s»: текст или null (язык не меняется)" % lang)
        out[lang] = v
    if out["ru"] is None and out["en"] is None:
        raise OpRefused("нужен хотя бы один язык (RU или EN); null — язык не меняется")
    return out


def target_key(kind, p):
    return "text:%s:%s" % (p["entity"], p["key"])


def _short(s):
    s = (s or "").replace("\r\n", " ⏎ ").replace("\n", " ⏎ ").replace("\\n", " ⏎ ")
    return s if len(s) <= SHOW else s[:SHOW - 1] + "…"


def k_text_set(ev, p, rep):
    ent, key = p["entity"], p["key"]
    e = ENT[ent]
    d, _src = texts()
    row = d["ent"].get(ent, {}).get(key)
    if row is None:
        raise OpRefused("%s: ключа %s нет — в А4 только правка существующих" % (ent, key))
    ru0, ek, en0, n = row
    if n > 1:
        raise OpRefused("%s: у ключа %s записей %d — какую показывает игра, не однозначно; правка не делается" % (ent, key, n))
    edit = {"type": "text_set", "file": "texts", "entity": ent, "key": key, "en_key": ek, "ru": None, "en": None,
            "snap": {"source": _src, "built": d.get("built"), "md5": (d.get("md5e") or {}).get(ent)}}
    parts = []
    if p["ru"] is not None:
        new = check_text(ent, "RU", p["ru"], ru0, rep)
        if new != ru0:
            edit["ru"] = [ru0, new]
    if p["en"] is not None:
        if en0 is None:
            raise OpRefused("EN-строки %s в DT_Loc_%s_en нет (сейчас в EN показывается RU) — добавление строки оверлея — новая запись, "
                            "не в А4.2; оставьте EN null" % (ek, e["en"][0]))
        new = check_text(ent, "EN", p["en"], en0, rep)
        if new != en0:
            edit["en"] = [en0, new]
    if edit["ru"] is None and edit["en"] is None:
        raise OpRefused("%s %s: тексты уже такие — менять нечего" % (ent, key))
    if edit["ru"] and not edit["en"]:
        rep["warnings"].append("EN не меняется: «%s»" % _short(en0) if en0 is not None else
                               "EN-строки нет — в EN будет показан новый RU (цепочка язык → en → ru)")
        parts = ("тексты, %s %s — RU: «%s» → «%s»; EN не меняется" % (ent, key, _short(edit["ru"][0]), _short(edit["ru"][1])))
    elif edit["en"] and not edit["ru"]:
        rep["warnings"].append("RU не меняется: «%s»" % _short(ru0))
        parts = ("тексты, %s %s — EN: «%s» → «%s»; RU не меняется" % (ent, key, _short(edit["en"][0]), _short(edit["en"][1])))
    else:
        parts = ("тексты, %s %s — RU: «%s» → «%s»; EN: «%s» → «%s»" % (ent, key, _short(edit["ru"][0]), _short(edit["ru"][1]),
                                                                       _short(edit["en"][0]), _short(edit["en"][1])))
    # ★ ревизия 34 К-2 / К-4 / К-5
    if ent == "npc.name" and edit["ru"]:
        rep["warnings"].append("заголовок окна диалога NPC — DT_NpcNsrHeader.Title (сценарий NSR), этим видом не правится; имя на плашке — "
                               "DT_NpcNames (AsdaNpcDialogSubsystem: заголовок сценария, иначе имя NPC)")
    if ent in ("mob.name", "item.name", "quest.title"):
        rep["warnings"].append("справочная копия имени в DT_MobQuestDrop (dump_monster_quest_items) не обновляется — игра её не читает; "
                               "asda_import_mob_quest_drop --check покажет расхождение")
    fin_ru = edit["ru"][1] if edit["ru"] else ru0
    fin_en = edit["en"][1] if edit["en"] else en0
    if fin_en is not None and fin_ru == fin_en:
        rep["warnings"].append("RU = EN: извлечение EN такую строку исключает (EN = RU) — при следующей генерации EN-строка пропадёт, "
                               "в EN будет показан RU")
    rep["text"] = parts
    rep["preview"] = {"entity": ent, "key": key, "ru": edit["ru"], "en": edit["en"]}
    rep["client"] = [edit]
    if edit["ru"] and e["src"] == "vo":                 # звания — общим путём движка: ведомость _value_overlay + доказательство генератором
        rep["client"].append({"type": "csv_cell", "file": "title_list", "key_col": "Id", "key": key, "col": e["col"],
                              "old": edit["ru"][0], "new": edit["ru"][1]})
    ev.client += rep["client"]


def snapshot(snap):
    """Магазинный снимок тексты не несут (свой файл data/ref/text_client.json)."""


def parse(cli, d):
    pass


def allowed_extra(ap):
    """Пути, которые пишет клиентская половина текстов (бэкап и откат — общие client_write)."""
    paths = {ru_csv(k) for k in ENT} | {en_csv(e["en"][0]) for e in ENT.values()} | {en_ledger(e["en"][0]) for e in ENT.values()}
    paths |= {P["overlay"], P["map_reg"], P["ru_dt"]}
    paths |= {os.path.join(P["itemdb"], e["table"] + ".json") for e in ENT.values() if e["src"] == "ov"}
    return ap in {os.path.normcase(os.path.abspath(x)) for x in paths}


# =====================================================================================================================
# Клиентская половина (ПК): правки файлов + доказательства настоящими инструментами
# =====================================================================================================================
def _tool(name):
    config.port_code(E.UE_TOOLS)          # ★ ревизия 56 С-1: только ПК
    if E.UE_TOOLS not in sys.path:
        sys.path.insert(0, E.UE_TOOLS)
    return __import__(name)


def _regen(binname):
    """Строки таблицы НАСТОЯЩИМ decode_item_db (архив Bin.bbz + живые ведомости + item_dedup, без слоя имён)."""
    with E._regen_lock:
        config.port_code(E.DECODER_DIR)   # ★ ревизия 56 С-1: только ПК
        if E.DECODER_DIR not in sys.path:
            sys.path.insert(0, E.DECODER_DIR)
        import decode_item_db as D          # noqa: E402
        z = zipfile.ZipFile(D.DEFAULT_BBZ)
        names = {n.lower(): n for n in z.namelist()}
        with contextlib.redirect_stdout(io.StringIO()):
            return D.decode_table(binname, z.read(names[binname]), D.REGISTRY[binname], True, D._DD.load_map())["rows"]


def _note(cs_id):
    return "админ-центр, набор изменений №%s (А4.2 тексты; причина — карточка набора и changelog)" % cs_id


def _json_fmt(raw):
    """Формат JSON-файла (отступ, перевод строки, хвост), при котором json.dumps воспроизводит его побайтно, или None."""
    t = raw.decode("utf-8-sig")
    d = json.loads(t)
    nl = "\r\n" if "\r\n" in t[:2000] else "\n"
    for ind in (2, 1, 0, 4):
        s = json.dumps(d, ensure_ascii=False, indent=ind).replace("\n", nl)
        for tail in ("", nl):
            if s + tail == t:
                return d, (ind, nl, tail, raw.startswith(b"\xef\xbb\xbf"))
    return d, None


def _json_dump(d, fmt):
    ind, nl, tail, bom = fmt
    return (b"\xef\xbb\xbf" if bom else b"") + (json.dumps(d, ensure_ascii=False, indent=ind).replace("\n", nl) + tail).encode("utf-8")


def _loc_values(raw):
    """EN-оверлей (Name,Text) → {ключ: текст} с нормализацией перевода строки (как import_text_lang.norm)."""
    L = _tool("asda_ledger")
    return {r[0]: L.norm_text(r[1]) for r in list(csv.reader(io.StringIO(_dec(raw)[1], newline="")))[1:] if len(r) >= 2}


def _qst_parse():
    """Строки QuestBook НАСТОЯЩИМ разбором .QST (asda_import_quest_tables.read_books) ДО наложения ведомости ru_dt_overrides."""
    Q = _tool("asda_import_quest_tables")
    saved = Q._RO.apply_rows
    Q._RO.apply_rows = lambda *a, **k: {}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return Q.read_books()
    finally:
        Q._RO.apply_rows = saved


_ext_lock = threading.Lock()


def _en_extract(table, files):
    """EN-таблица оверлея НАСТОЯЩИМ extract_text_lang.extract (без ведомостей, без записи) → {ключ: значение}. RU-источники, которые
    меняет план (files: {путь: [было, станет]}), извлечение читает уже «станет» (read_csv / read_json подменяются на время вызова)."""
    X = _tool("extract_text_lang")
    over = {os.path.normcase(os.path.abspath(p)): v[1] for p, v in files.items() if v[1] is not None and v[1] != v[0]}
    rc, rj = X.read_csv, X.read_json

    def read_csv(path):
        b = over.get(os.path.normcase(os.path.abspath(path)))
        return rc(path) if b is None else list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"), newline="")))

    def read_json(path):
        b = over.get(os.path.normcase(os.path.abspath(path)))
        return rj(path) if b is None else json.loads(b.decode("utf-8-sig"))
    with _ext_lock:
        X.read_csv, X.read_json = read_csv, read_json
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                t = next(x for x in X.build_tables() if x.name == table)
                res = X.extract(t)
        finally:
            X.read_csv, X.read_json = rc, rj
    return {k: v[0] for k, v in res["out"].items()}


def _en_proof(pc, err):
    """★ ревизия 34 М-3 / К-4: ляжет ли ведомость loc/en при следующей генерации оверлеев. Для каждого EN-ключа, у которого план меняет
    EN или RU, — настоящее извлечение (по RU «станет») + настоящий asda_ledger.classify_row над НОВОЙ ведомостью: конфликт = генерация
    встала бы (RuntimeError в apply_ledgers) → отказ; строки ведомости нет, а извлечение уже не даёт EN — предупреждение."""
    L = _tool("asda_ledger")
    for t, keys in sorted(pc.get("_en_check", {}).items()):
        try:
            out = _en_extract(t, pc["files"])
        except Exception as ex:
            err.append("EN %s: извлечение extract_text_lang для проверки ведомости не прошло: %s" % (t, str(ex)[:200]))
            continue
        lp = en_ledger(t)
        lc = pc["load"]("txt:enled:" + t, lp)
        led, fmt = _json_fmt(lc[1]) if lc[1] else ({"rows": []}, None)
        rows = led["rows"]
        cur_csv = _loc_values(pc["load"]("txt:en:" + t, en_csv(t))[1])
        touched = False
        for k in sorted(keys):
            mine = [r for r in rows if str(r.get("key")) == k]
            v = out.get(k)
            for r in mine:
                if L.classify_row(r, v, exists=v is not None) != L.CONFLICT:
                    continue
                if k not in pc.get("_en_ru", {}).get(t, set()):  # конфликт не от RU этой позиции — ведомость уже не ложится
                    err.append("EN %s %s: после правки извлечение даст «%s», а ведомость ждёт «%s» — генерация оверлеев встала бы; отказ"
                               % (t, k, _short(v) if v is not None else "— (строки нет)", _short(r.get("was"))))
                    continue
                # RU этой же позиции поменял извлечение (у карт EN ищется по RU-тексту): строка ведомости приводится к извлечению
                #   «станет» — новая строка панели получает was = извлечению; у прежней строки прежнее «было» уходит в prev
                if k in pc.get("_en_new", {}).get(t, set()):
                    r["was"] = v
                elif v is not None:
                    r["prev"] = list(r.get("prev") or []) + [v]
                else:
                    r["prev"] = list(r.get("prev") or []) + ([r["was"]] if r.get("was") is not None else [])
                    r["was"] = None
                touched = True
                pc["warnings"].append("EN %s %s: правка RU меняет извлечение EN («%s») — строка ведомости loc/en приведена к нему, EN "
                                      "останется «%s»" % (t, k, _short(v) if v is not None else "—", _short(r.get("value"))))
                if L.classify_row(r, v, exists=v is not None) == L.CONFLICT or fmt is None:
                    err.append("EN %s %s: после правки извлечение даст «%s», а ведомость ждёт «%s» — генерация оверлеев встала бы; отказ"
                               % (t, k, _short(v) if v is not None else "— (строки нет)", _short(r.get("was"))))
        if touched and fmt is not None:
            lc[1] = _json_dump(led, fmt)
        for k in sorted(keys):
            mine = [r for r in rows if str(r.get("key")) == k]
            v = out.get(k)
            if not mine and v is None and k in cur_csv:
                pc["warnings"].append("EN %s %s: при следующей генерации строка пропадёт (EN-источника нет или EN = RU) — в EN будет "
                                      "показан RU" % (t, k))
            elif not mine and v is not None and L.norm_text(v) != cur_csv.get(k):
                pc["warnings"].append("EN %s %s: при следующей генерации станет «%s»" % (t, k, _short(v)))


def _plan_ov(pc, ent, key, old, new, err, allowed, dt):
    """RU через слой-рецепт имён: CSV + JSON ItemDB + строка рецепта (source=owner) + доказательства."""
    e = ENT[ent]
    t, kc, col = e["table"], e["kc"], e["col"]
    path = os.path.join(P["itemdb"], t + ".csv")
    cur = pc["load"]("txt:" + t, path)
    c = Csv(cur[1], t + ".csv")
    js = c.find(kc, key)
    if len(js) != 1:
        return err.append("%s.csv: записей %s=%s — %d (ждали 1)" % (t, kc, key, len(js)))
    j = js[0]
    if c.value(j, col) != old:
        return err.append("%s.csv %s=%s: %s сейчас «%s», при проверке было «%s» — пересоберите набор" % (t, kc, key, col, _short(c.value(j, col)), _short(old)))
    rid = c.value(j, "_row")
    c.set(j, {col: new})
    cur[1] = c.data()
    allowed.setdefault(path, set()).add((j, col))
    dt.setdefault((e["dt"], path), set()).add(rid)
    # рецепт имён
    oc = pc["load"]("txt:overlay", P["overlay"])
    ov = Csv(oc[1], "item_name_overlay.csv")
    hits = [i for i in range(1, len(ov.rows)) if [ov.value(i, x) for x in ("table", "key", "column")] == [t, key, col]]
    if len(hits) > 1:
        return err.append("рецепт имён: у %s %s.%s строк %d — правка не делается, разберите рецепт" % (t, key, col, len(hits)))
    if hits:
        i = hits[0]
        if ov.value(i, "new_value") != old:
            return err.append("рецепт имён %s %s.%s: в рецепте «%s», в CSV «%s» — CSV правили мимо рецепта; разберите до правки"
                              % (t, key, col, _short(ov.value(i, "new_value")), _short(old)))
        before = ov.value(i, "old_value")
        ov.set(i, {"new_value": new, "source": "owner", "reason": "admin_cs", "note": _note(pc["cs_id"])})
    else:
        before = old
        ov.append([t, key, col, old, new, "owner", "admin_cs", _note(pc["cs_id"])])
    oc[1] = ov.data()
    # доказательство: декодер даёт «до слоя» = old_value рецепта; настоящий load_overlay/classify даёт новое значение
    try:
        memo = pc.setdefault("_regen", {})              # одна перегенерация таблицы на план
        if e["bin"] not in memo:
            memo[e["bin"]] = _regen(e["bin"])
        rows = [r for r in memo[e["bin"]] if str(r.get(kc)) == key]
    except Exception as ex:
        return err.append("%s: перегенерация ItemDB для проверки рецепта не прошла: %s" % (t, str(ex)[:200]))
    if len(rows) != 1 or str(rows[0].get(col, "")) != before:
        return err.append("%s %s=%s: генератор даёт «%s», а «было» рецепта — «%s»; после перегенерации правка не легла бы — отказ"
                          % (t, kc, key, _short(str(rows[0].get(col, "")) if rows else "—"), _short(before)))
    NO, L = _tool("asda_apply_name_overlay"), _tool("asda_ledger")
    fd, tmp = tempfile.mkstemp(prefix="asda_cs_ov_", suffix=".csv")
    try:
        os.write(fd, oc[1])
        os.close(fd)
        ovm, _n = NO.load_overlay(tmp, {t})
    finally:
        os.remove(tmp)
    r = ovm.get(t, {}).get((key, col))
    if not r or (r.get("source") or "").strip() != "owner" or L.classify(before, r["new_value"], r["old_value"]) != L.APPLY \
            or r["new_value"] != new:
        return err.append("рецепт имён %s %s.%s: настоящий load_overlay/classify не даёт новое значение — отказ" % (t, key, col))
    # JSON-двойник (как asda_apply_name_overlay.apply_json: только если json.dumps(indent=0) воспроизводит файл)
    jp = os.path.join(P["itemdb"], t + ".json")
    if os.path.isfile(jp):
        jc = pc["load"]("txt:json:" + t, jp)
        t0 = jc[1].decode("utf-8")
        nl = "\r\n" if "\r\n" in t0[:200] else "\n"
        data = json.loads(t0)
        if json.dumps(data, ensure_ascii=False, indent=0).replace("\n", nl) != t0:
            pc["warnings"].append("%s.json: json.dumps(indent=0) не воспроизводит файл — JSON не тронут (как у asda_apply_name_overlay)" % t)
        else:
            n = 0
            for rr in data:
                if str(rr.get(kc)).strip() == key and col in rr:
                    rr[col] = new
                    n += 1
            if n:
                jc[1] = json.dumps(data, ensure_ascii=False, indent=0).replace("\n", nl).encode("utf-8")


def _plan_gen(pc, ent, key, old, new, err, allowed, dt):
    e = ENT[ent]
    path = P[e["table"]]
    cur = pc["load"]("txt:" + e["table"], path)
    c = Csv(cur[1], os.path.basename(path))
    js = c.find(e["kc"], key)
    if len(js) != 1 or c.value(js[0], e["col"]) != old:
        return err.append("%s %s: сейчас не «%s» — пересоберите набор" % (os.path.basename(path), key, _short(old)))
    c.set(js[0], {e["col"]: new})
    cur[1] = c.data()
    allowed.setdefault(path, set()).add((js[0], e["col"]))
    dt.setdefault((e["dt"], path), set()).add(key)
    # ★ ревизия 34 К-1: строка этого DT в ru_dt_overrides.json (asda_dt_json_point ASDA_JP_LEDGER=1 сверяет ассет с её now) — now = новое
    dtn = e["dt"].rsplit("/", 1)[-1]
    lc = pc["load"]("txt:ru_dt", P["ru_dt"])
    if not lc[1]:
        return
    led, lfmt = _json_fmt(lc[1])
    hit = [r for r in led["rows"] if r["dt"].rsplit("/", 1)[-1] == dtn and str(r["row"]) == key and r["field"] == e["col"]
           and r.get("index") is None and r.get("sub") is None]
    if not hit:
        return
    if lfmt is None:
        return err.append("ru_dt_overrides.json: json.dumps не воспроизводит файл — правка не делается")
    if len(hit) > 1 or hit[0]["now"] != old:
        return err.append("ru_dt_overrides.json %s %s.%s: в ведомости «%s», в CSV «%s» — правили мимо ведомости; разберите"
                          % (dtn, key, e["col"], _short(hit[0]["now"]), _short(old)))
    hit[0]["now"] = new
    lc[1] = _json_dump(led, lfmt)


def _plan_map(pc, ent, key, old, new, err, allowed, dt):
    """Реестр карт → Map_info.csv рендером НАСТОЯЩЕГО asda_map_registry (Map_info.csv обязан совпадать с рендером реестра)."""
    MR = _tool("asda_map_registry")
    rc = pc["load"]("txt:map_reg", P["map_reg"])
    mc = pc["load"]("txt:map_info", P["map_info"])
    reg = json.loads(rc[1].decode("utf-8-sig"))
    if MR.render_map_info_csv(reg) != mc[1]:
        return err.append("Map_info.csv ≠ рендеру реестра карт (asda_map_registry) — Map_info правили мимо реестра; разберите до правки")
    t = rc[1].decode("utf-8")
    m = re.search(r'\n(\s*)\{\s*"id":\s*%d,' % int(key), t)
    if not m:
        return err.append("реестр карт: записи карты %s не найдено" % key)
    end = t.find("\n" + m.group(1) + "}", m.end())
    old_j = '"loc_name": ' + json.dumps(old, ensure_ascii=False)
    at = t.find(old_j, m.end(), end if end > 0 else len(t))
    if at < 0:
        return err.append("реестр карт: у карты %s loc_name не «%s» — пересоберите набор" % (key, _short(old)))
    t2 = t[:at] + '"loc_name": ' + json.dumps(new, ensure_ascii=False) + t[at + len(old_j):]
    reg2 = json.loads(t2)
    want = json.loads(t)
    for mm in want["maps"]:
        if mm["id"] == int(key):
            mm["loc_name"] = new
    if reg2 != want:
        return err.append("реестр карт: правка задела не только loc_name карты %s — отказ" % key)
    rc[1] = t2.encode("utf-8")
    mc[1] = MR.render_map_info_csv(reg2)
    # ★ ревизия 34 М-2: второй писатель Map_info.csv (extract_text_tables, ветка Map_info.BIN) убран; сверка реестра с клиентским BIN
    #   (asda_map_registry --check, check_client) после правки имени покажет W по этой карте — это правка владельца, не дефект
    pc["warnings"].append("карта %s: asda_map_registry --check покажет «Map_info.BIN id=%s ≠ реестр loc_name» — это ожидаемо после правки "
                          "имени (владелец имени — реестр карт)" % (key, key))
    j = Csv(mc[1], "Map_info.csv").find("Name", key)
    allowed.setdefault(P["map_info"], set()).update((x, "name") for x in j)
    dt.setdefault((ENT[ent]["dt"], P["map_info"]), set()).add(key)


def _plan_quest(pc, ent, key, old, new, err, jobs):
    """QuestBook.json + ведомость ru_dt_overrides.json (проверка настоящим asda_ru_dt_overrides.apply_rows) + JSON-точка DT."""
    col = ENT[ent]["col"]
    qc = pc["load"]("txt:quest", P["quest"])
    data, fmt = _json_fmt(qc[1])
    if fmt is None:
        return err.append("QuestBook.json: json.dumps не воспроизводит файл — правка не делается")
    rows = [r for r in data if r.get("Name") == key]
    if len(rows) != 1 or rows[0].get(col) != old:
        return err.append("QuestBook.json %s.%s: сейчас не «%s» — пересоберите набор" % (key, col, _short(old)))
    fn = rows[0]["FileName"]
    rows[0][col] = new
    qc[1] = _json_dump(data, fmt)
    lc = pc["load"]("txt:ru_dt", P["ru_dt"])
    led, lfmt = _json_fmt(lc[1])
    if lfmt is None:
        return err.append("ru_dt_overrides.json: json.dumps не воспроизводит файл — правка не делается")
    hit = [r for r in led["rows"] if r["dt"].rsplit("/", 1)[-1] == "DT_QuestBook" and r["row"] == fn and r["field"] == col
           and r.get("index") is None and r.get("sub") is None]
    if len(hit) > 1:
        return err.append("ru_dt_overrides.json: у %s.%s строк %d — разберите ведомость" % (fn, col, len(hit)))
    # ★ ревизия 34 М-3: «было» — НАСТОЯЩИЙ разбор .QST импортёром (asda_import_quest_tables.read_books до наложения ведомости):
    #   при переимпорте ведомость ляжет, только если её was = разбору
    try:
        memo = pc.setdefault("_qst", {})
        if "rows" not in memo:
            memo["rows"] = {r["FileName"]: r for r in _qst_parse()}
        parsed = memo["rows"].get(fn)
    except Exception as ex:
        return err.append("разбор .QST (asda_import_quest_tables) для проверки ведомости не прошёл: %s" % str(ex)[:200])
    if parsed is None:
        return err.append("разбор .QST не даёт задания %s — переимпорт его не построит; правка не делается" % fn)
    real = parsed.get(col)
    if hit:
        if hit[0]["now"] != old:
            return err.append("ru_dt_overrides.json %s.%s: в ведомости «%s», в QuestBook.json «%s» — правили мимо ведомости; разберите"
                              % (fn, col, _short(hit[0]["now"]), _short(old)))
        if hit[0]["was"] != real:
            return err.append("ru_dt_overrides.json %s.%s: was ведомости «%s», а разбор .QST даёт «%s» — при переимпорте правка не ляжет; "
                              "разберите" % (fn, col, _short(hit[0]["was"]), _short(real)))
        hit[0]["now"] = new
    else:
        if real != old:
            return err.append("QuestBook.json %s.%s: «%s», а разбор .QST даёт «%s» — JSON правили мимо ведомости (переимпорт вернул бы "
                              "разбор); разберите" % (key, col, _short(old), _short(real)))
        led["rows"].append({"row": fn, "field": col, "index": None, "sub": None, "was": real, "now": new, "dt": DT_QUEST})
    lc[1] = _json_dump(led, lfmt)
    # настоящий apply_rows по НОВОЙ ведомости (временный файл) над строкой разбора ставит новое значение
    RO = _tool("asda_ru_dt_overrides")
    probe = [{"FileName": fn, col: real}]
    fd, tmp = tempfile.mkstemp(prefix="asda_cs_rudt_", suffix=".json")
    try:
        os.write(fd, lc[1])
        os.close(fd)
        RO.apply_rows("DT_QuestBook", probe, lambda r: r["FileName"], None, path=tmp)
    finally:
        os.remove(tmp)
    if probe[0][col] != new:
        return err.append("ru_dt_overrides.json: настоящий apply_rows не даёт новое значение %s.%s — отказ" % (fn, col))
    jobs.append({"dt": DT_QUEST, "file": P["quest"], "edits": [{"row": key, "field": col, "index": None, "sub": None, "was": old, "now": new}]})


def _plan_en(pc, ent, ek, old, new, err, allowed, dt):
    """EN: DT_Loc_<Т>_en.csv + ведомость Tools/data/loc/en/<Т>.json (решение — настоящий asda_ledger.classify_row)."""
    t = ENT[ent]["en"][0]
    path = en_csv(t)
    cur = pc["load"]("txt:en:" + t, path)
    snap = os.path.join(P["en_dir"], "_imported", os.path.basename(path))
    # ★ ревизия 34 М-1: по ЗНАЧЕНИЯМ ячеек (как import_text_lang): asda_ml_dt_point переписывает копию csv.writer-ом, и у файлов,
    #   которые панель правит по смещениям (DT_Loc_QuestBook_en), байты копии и CSV расходятся при равных значениях
    if not os.path.isfile(snap) or _loc_values(open(snap, "rb").read()) != _loc_values(cur[0]):
        return err.append("DT_Loc_%s_en.csv ≠ копии последней заливки (_imported) — CSV и ассет разошлись; сначала import_text_lang" % t)
    c = Csv(cur[1], os.path.basename(path))
    js = c.find("Name", ek)
    if len(js) != 1 or c.value(js[0], "Text") != old:
        return err.append("DT_Loc_%s_en %s: сейчас не «%s» — пересоберите набор" % (t, ek, _short(old)))
    c.set(js[0], {"Text": new})
    cur[1] = c.data()
    allowed.setdefault(path, set()).add((js[0], "Text"))
    dt.setdefault(("/Game/AsdaAssets/Text/L10N/en/DT_Loc_%s_en" % t, path), set()).add(ek)
    lp = en_ledger(t)
    lc = pc["load"]("txt:enled:" + t, lp)
    if lc[1]:
        led, fmt = _json_fmt(lc[1])
        if fmt is None:
            return err.append("%s.json (loc/en): json.dumps не воспроизводит файл — правка не делается" % t)
    else:
        led = {"_comment": "Ведомость правок EN-оверлея DT_Loc_%s_en (ключ — как в DT_Loc_%s_en.csv). Применяет Tools/extract_text_lang.py "
                           "после извлечения; was = значение извлечения. Заведена админ-центром (А4.2)." % (t, t), "rows": []}
        fmt = (2, "\n", "\n", False)
    hit = [r for r in led["rows"] if str(r.get("key")) == ek]
    if len(hit) > 1:
        return err.append("%s.json (loc/en): у ключа %s строк %d — разберите ведомость" % (t, ek, len(hit)))
    why = "%s: правка текста владельцем через админ-центр" % datetime.date.today().isoformat()
    if hit:
        r = hit[0]
        if r.get("value") != old:
            return err.append("%s.json (loc/en) %s: в ведомости «%s», в CSV «%s» — CSV правили мимо ведомости; разберите до правки"
                              % (t, ek, _short(r.get("value")), _short(old)))
        if old != r.get("was") and old not in (r.get("prev") or []):
            r["prev"] = list(r.get("prev") or []) + [old]
        r["value"], r["why"], r["source"] = new, why + " (" + _note(pc["cs_id"]) + ")", "admin_cs"
        was = r.get("was")
    else:
        r = {"key": ek, "value": new, "was": old, "why": why + " (" + _note(pc["cs_id"]) + ")", "source": "admin_cs"}
        led["rows"].append(r)
        pc.setdefault("_en_new", {}).setdefault(t, set()).add(ek)
        was = old
    lc[1] = _json_dump(led, fmt)
    pc.setdefault("_en_check", {}).setdefault(t, set()).add(ek)   # ★ ревизия 34 М-3: доказательство — настоящим извлечением (_en_proof)


def plan(pc):
    edits = pc["by_file"].get("texts", [])
    if not edits:
        return
    pc.setdefault("warnings", [])
    err = pc["errors"]
    allowed = {}
    for ed in edits:
        ent, key = ed["entity"], ed["key"]
        src = ENT[ent]["src"]
        sn = ed.get("snap") or {}
        if sn.get("md5"):                                # ★ ревизия 34 К-3: оценка была по снимку, а порт с тех пор менялся
            live = [E.md5f(x) if os.path.isfile(x) else "none" for x in (ru_csv(ent), en_csv(ENT[ent]["en"][0]))]
            if live != sn["md5"]:
                pc["warnings"].append("%s %s: проверка шла по снимку текстов от %s (%s), источники порта с тех пор изменились — «было» "
                                      "сверено с живыми файлами; выложите панель, чтобы обновить снимок службы"
                                      % (ent, key, sn.get("built") or "?", sn.get("source") or "?"))
        n0 = len(err)
        if ed.get("ru"):
            old, new = ed["ru"]
            if src == "ov":
                _plan_ov(pc, ent, key, old, new, err, allowed, pc["dt_rows"])
            elif src == "gen":
                _plan_gen(pc, ent, key, old, new, err, allowed, pc["dt_rows"])
            elif src == "map":
                _plan_map(pc, ent, key, old, new, err, allowed, pc["dt_rows"])
            elif src == "quest":
                _plan_quest(pc, ent, key, old, new, err, pc["json_jobs"])
            # src == "vo": общим путём движка (позиция csv_cell по title_list)
        if ed.get("ru"):
            pc.setdefault("_en_ru", {}).setdefault(ENT[ent]["en"][0], set()).add(ed["en_key"])
        if ed.get("en") and len(err) == n0:
            _plan_en(pc, ent, ed["en_key"], ed["en"][0], ed["en"][1], err, allowed, pc["dt_rows"])
        elif ed.get("ru") and len(err) == n0:          # ★ ревизия 34 К-4: RU сменился — переживёт ли EN этого ключа генерацию
            pc.setdefault("_en_check", {}).setdefault(ENT[ent]["en"][0], set()).add(ed["en_key"])
    if not err:
        _en_proof(pc, err)
    pc["warnings"].append("после client-apply снимок текстов службы на сервере устареет — выложите панель (deploy_admin_center.py)")
    for path, cells in allowed.items():                 # сторож: в CSV изменились только ячейки позиций
        cur = pc["load"]("txt:" + path, path)
        why = _same_but(cur[0], cur[1], cells, os.path.basename(path)) if cur[0] is not None else "нет файла"
        if why:
            err.append(why)
