# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""refdata.py — справочники панели (data/ref/, собирает tools/build_ref_data.py): предметы, классы, карты, навыки,
питомцы. Загружаются один раз на процесс, лениво. 16.11.2026.

Нет файла справочника — названия пустые, но карточки работают (код предмета показывается всегда).
Побочных эффектов при импорте нет.
"""
import json
import os
import threading

from core import config

REF = os.path.join(config.DATA_DIR, "ref")
GOLD_CODE = 20551                       # золото — предмет сумки 2 (asda_give.GOLD_CODE)

# Сумки (Item.Plate): назначение по правилам выдачи asda_give.py и разбору research_item_props.md.
PLATES = {1: "Сумка 1 (снаряжение)", 2: "Сумка 2 (расходники)", 3: "Надето", 4: "Книга заданий",
          5: "Склад", 11: "Аукцион (замок)", 12: "Аукцион (замок)"}

_lock = threading.Lock()
_data = {}


def _load(name):
    """JSON справочника (кэш)."""
    with _lock:
        if name not in _data:
            p = os.path.join(REF, name)
            try:
                with open(p, encoding="utf-8") as f:
                    _data[name] = json.load(f)
            except (OSError, ValueError):
                _data[name] = {}
        return _data[name]


def item(code):
    """Справка о предмете → dict(code, ru, en, table, icon{atlas,x,y,size,whole,w,h} | None)."""
    rec = _load("items.json").get(str(int(code)))
    if not rec:
        return {"code": int(code), "ru": "", "en": "", "table": "", "icon": None, "name": ""}   # перепроверка 5 К1
    ru, en, tab, atlas, x, y, size, whole = rec
    icon = None
    if atlas:
        wh = _load("atlases.json").get(atlas) or [0, 0]
        if wh[0] and wh[1]:            # заворот по модулю, как bWrap клиента (asda_gift_catalog_build._cut_icon)
            x, y = x % wh[0], y % wh[1]
        icon = {"atlas": atlas, "x": x, "y": y, "size": size, "whole": bool(whole), "w": wh[0], "h": wh[1]}
    # name — на языке запроса (владелец 16.11: «в английском режиме много предметов по-русски»)
    return {"code": int(code), "ru": ru, "en": en, "table": tab, "icon": icon, "name": _pick([ru, en]) or ru}


def names(kind):
    """Словарь имён: jobs | maps | skills | pets → {id(str): [ru, en, …]}."""
    return _load("names.json").get(kind, {})


def _pick(r):
    """Название на языке запроса (core.i18n): [ru, en, …]; нет EN — RU."""
    if not r:
        return ""
    from core import i18n
    if i18n.is_en() and len(r) > 1:
        en = (r[1] or "").strip()
        # перепроверка 5 М4: в EN-таблицах клиента бывает заглушка «нет» — это не название
        return "" if en in ("", "нет") else en
    return r[0]


def option_name(oid, value=None):
    """Название опции предмета (шаблон itemoptiontable клиента; %d → значение) на языке запроса."""
    r = names("options").get(str(int(oid)))
    from core import i18n
    t = _pick(r) or (("option %s" if i18n.is_en() else "опция %s") % oid)
    if value is not None:
        t = t.replace("%d", str(value)).replace("%%", "%")
    return t


def job(jid):
    """Название профессии по Charinfo.Job."""
    r = names("jobs").get(str(jid))
    return _pick(r)


def map_name(mid):
    """Название карты по номеру (CharPos.Poridx)."""
    r = names("maps").get(str(mid))
    return _pick(r)


def skill(sid):
    """Название навыка."""
    r = names("skills").get(str(sid))
    from core import i18n
    return _pick(r) or (("skill %s" if i18n.is_en() else "навык %s") % sid)


def pet(pid):
    """Название вида питомца (CharPetList.Petindex)."""
    r = names("pets").get(str(pid))
    return _pick(r)


def search_items(text, limit=50):
    """Поиск предмета по коду или части названия RU/EN → [item()]."""
    t = (text or "").strip().lower()
    if not t:
        return []
    out = []
    for k, rec in _load("items.json").items():
        if t == k or t in (rec[0] or "").lower() or t in (rec[1] or "").lower():
            out.append(int(k))
            if len(out) >= limit:
                break
    return [item(c) for c in sorted(out)]


def manifest():
    """Сведения о сборке справочников."""
    return _load("manifest.json")


def atlas_path(name):
    """Путь PNG атласа по имени (только из списка атласов — защита от обхода каталога)."""
    if name not in _load("atlases.json"):
        return None
    p = os.path.join(REF, "atlases", name + ".png")
    return p if os.path.exists(p) else None


def quest(qid):
    """Название задания (Episodeidx) — как у клиента (QuestBook.json / DT_Loc_QuestBook_en.csv); нет — «задание N»."""
    r = _load("quests.json").get(str(int(qid)))
    from core import i18n
    return _pick(r) or (("quest %s" if i18n.is_en() else "задание %s") % qid)
