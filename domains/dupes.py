# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""dupes.py — поиск дюпов предметов (только чтение; волна А1, решение владельца 19.11 п.2). 19.11.2026.

ПРАВИЛА — Reports/admin_center/research_items_trace.md §3 (выведены из того, как номер живёт у сервера, §2.2):
  (а) одинаковый Uuid в нескольких местах Joy1 (Item / Del_item / Exitem.Eid). У СТОПКИ это штатно (неполный лот: у продавца строка
      остаётся с тем же Uuid, лот получает тот же Eid; покупка вставляет Uuid = Eid; отмена лота возвращает Uuid = Eid) — «стопка»,
      отдельно от снаряжения / совела / одиночного — «подозрение». Восстановленный панелью персонаж: корзина Del_item хранит копию,
      пока есть отметка adm.CharRestored — «восстановлен». Известный дубль 90D7C266… (uid 2 слот 11, наследие 2010–2012) — решение
      владельца 19.11 «оставить», показывается как известный.
  (б) невозможные количества (по правилу кода itemgive.item_spec — как сервер sub_5340B0): функциональный — заряды выше Function_Table,
      кроме кодов P100 (dbo.AsdaChargeGroup, GroupKey ≠ 0) в пределах потолка; снаряжение / совел / одиночный — Amount > 1; колчан —
      выше ёмкости t29; кода нет в таблицах сервера. Стопки — без ограничения (сервер — до INT).
  (в) без следа появления — ОТДЕЛЬНЫМ списком, с пометкой категории: стартовый набор (CharEventCreate ±5 с от GainDate), совел (возврат
      из оправы журнала не пишет), до начала журналов (< 10.2026), копия / восстановление панелью; иначе «не объяснено».
  (г) последнее событие номера — уничтожение (выброс, продажа, разбор, таймаут лота, конец срока, ремесло), а строка в Item жива.
      Частичный выброс / продажа стопки (Ramount > 0) — норма, помечается.
Только чтение; «исправить» — существующими операциями (изъять, след). Побочных эффектов при импорте нет.
"""
import datetime

from core import db
from domains import feed, refdata, srvtables

KNOWN = {"90D7C266-1097-4336-B1FC-5A57D07BEB94": "известный дубль: uid 2 слот 11, сумка и склад, наследие старой базы 2010–2012 "
                                                 "(решение владельца 19.11 — оставить)"}
GOLD_CODE = 20551


def _spec(code, cache):
    """Правило кода (itemgive.item_spec) или None, если кода нет в таблицах сервера (с причиной)."""
    from core.ops import OpRefused
    from domains import itemgive
    if code not in cache:
        try:
            cache[code] = (itemgive.item_spec(code), None)
        except OpRefused as ex:
            cache[code] = (None, str(ex))
        except Exception as ex:                       # таблицы сервера не прочитаны — не отказ всего окна
            cache[code] = (None, "правило кода не прочитано: %s" % ex.__class__.__name__)
    return cache[code]


def same_uuid():
    """(а) группы одинаковых Uuid в Item / Del_item / Exitem."""
    with db.GameReader("joy1") as j:
        rows = j.rows(
            "WITH x AS (SELECT CONVERT(varchar(36), Uuid) AS u, 'Item' AS src, Userindex, Charidx, Code, Plate, Posx, Amount, GainDate AS d "
            "FROM Item UNION ALL SELECT CONVERT(varchar(36), Uuid), 'Del_item', Userindex, Charidx, Code, Plate, Posx, Amount, Edate "
            "FROM Del_item UNION ALL SELECT CONVERT(varchar(36), Eid), 'Exitem', Userindex, Charidx, Code, Plate, idx, Amount, Gaindate "
            "FROM Exitem UNION ALL SELECT CONVERT(varchar(36), Eid), 'Del_ExItem', Userindex, Charidx, Code, Plate, idx, Amount, Edate "
            "FROM Del_ExItem) SELECT * FROM x WHERE u IN (SELECT u FROM x GROUP BY u HAVING COUNT(*) > 1) ORDER BY u, src")
        restored = {(int(r["Userindex"]), int(r["Charidx"])) for r in j.rows(
            "SELECT Userindex, Charidx FROM adm.CharRestored")} if j.one(
            "SELECT CASE WHEN OBJECT_ID('adm.CharRestored', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"] else set()
    groups, cache = {}, {}
    for r in rows:
        groups.setdefault(r["u"].upper(), []).append(r)
    out = []
    for u, g in groups.items():
        code = int(g[0]["Code"])
        sp, _why = _spec(code, cache)
        stack = bool(sp and (sp["stack"] or sp["kind"] == "function"))
        srcs = {x["src"] for x in g}
        if u in KNOWN:
            kind, note = "known", KNOWN[u]
        elif srcs <= {"Item", "Del_item", "Del_ExItem"} and "Item" in srcs and all((int(x["Userindex"]), int(x["Charidx"])) in restored for x in g if x["src"] in ("Del_item", "Del_ExItem")):
            kind, note = "restored", "персонаж восстановлен панелью: корзина Del_item хранит копию набора (adm.CharRestored)"
        elif stack:
            kind, note = "stack", "стопка / заряды: штатно после неполного лота или отмены лота (тот же Uuid у двух владельцев)"
        else:
            kind, note = "suspect", "подозрение: один экземпляр снаряжения / совела / одиночного предмета в нескольких местах"
        out.append({"uuid": u, "code": code, "name": refdata.item(code)["name"], "kind": kind, "note": note, "rows": g})
    order = {"suspect": 0, "stack": 1, "restored": 2, "known": 3}
    out.sort(key=lambda x: (order[x["kind"]], x["uuid"]))
    return out


def bad_amounts():
    """(б) невозможные количества в Item (все сумки)."""
    cap = srvtables.charge_cap() or 30000
    with db.GameReader("joy1") as j:
        rows = j.rows("SELECT Userindex, Charidx, Plate, Posx, Code, Amount, CONVERT(varchar(36), Uuid) AS Uuid FROM Item WHERE Code <> ?",
                      (GOLD_CODE,))
        charge = {int(r["Code"]) for r in j.rows("SELECT Code FROM dbo.AsdaChargeGroup WHERE GroupKey <> 0")} if j.one(
            "SELECT CASE WHEN OBJECT_ID('dbo.AsdaChargeGroup', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"] else set()
    out, cache, legal = [], {}, 0
    for r in rows:
        code, amt = int(r["Code"]), int(r["Amount"] or 0)
        sp, why = _spec(code, cache)
        if sp is None:
            out.append(dict(r, why=why or "кода нет в таблицах сервера"))
            continue
        k = sp["kind"]
        if k == "function" and amt > sp["amount_each"]:
            if code in charge and amt <= cap:
                legal += 1
                continue
            out.append(dict(r, why="заряды %d > %d (Function_Table)%s" % (amt, sp["amount_each"],
                                                                         "" if code in charge else ", код не в группах P100")))
        elif k in ("gear", "cellob", "single") and amt > 1:
            out.append(dict(r, why="количество %d у предмета без стопки" % amt))
        elif k == "quiver" and amt > sp["amount_each"]:
            out.append(dict(r, why="колчан %d > ёмкости %d" % (amt, sp["amount_each"])))
    for r in out:
        r["name"] = refdata.item(r["Code"])["name"]
    return {"rows": out, "p100_merged": legal, "cap": cap}


def _serial_index(errors):
    """По всем журналам: номер → (есть событие появления, время и таблица последнего события, последний — уничтожение?)."""
    last, born, partial = {}, set(), {}
    plan = []
    for ent in feed.catalog():
        for col, ty in ent.get("serials") or []:
            if not ent["time"]:
                continue
            short = ent["tab"]
            extra, grp = "", "[%s]" % col
            if short == "ExchangeEvent":
                # ★ ревизия 27 М-3: «таймаут» — только если ПОСЛЕДНЯЯ строка номера в журнале — 'Time Out-Delete' (сравнение времени)
                extra, grp = ", MAX(CASE WHEN State = 'Time Out-Delete' THEN [%s] END) AS tod" % ent["time"], grp
            rem = ", MIN(CASE WHEN [Ramount] > 0 THEN 1 ELSE 0 END) AS part" if "Ramount" in ent["cols"] and short in feed.DEATH else ""
            sel = "CONVERT(varchar(36), [%s])" % col if ty == "uniqueidentifier" else "[%s]" % col
            plan.append((dict(ent, _col=col), "SELECT %s AS s, MAX([%s]) AS t%s%s FROM %s WHERE [%s] IS NOT NULL GROUP BY %s"
                         % (sel, ent["time"], extra, rem, feed._q(ent), col, grp), []))
    with db.GameReader("joylog1") as lg:
        res = feed._batched(lg, plan, errors)
    for ent, rows in res:
        short = ent["tab"]
        death = short in feed.DEATH
        for r in rows:
            s = str(r["s"] or "").strip().upper()
            if not s:
                continue
            if short.startswith(feed.BIRTH_PREFIX) or (short == "TradeitemTo" and ent["_col"] == "Serial"):
                born.add(s)
            d = death or (short == "ExchangeEvent" and r.get("tod") is not None and r["tod"] == r["t"])
            cur = last.get(s)
            if r["t"] and (cur is None or r["t"] > cur[0]):
                last[s] = (r["t"], ent["name"], bool(d))
            if r.get("part"):
                partial[s] = True
    return last, born, partial


def no_trace_and_dead():
    """(в) живые предметы без события появления — по категориям; (г) живые, у которых последнее событие — уничтожение."""
    errors = []
    last, born, partial = _serial_index(errors)
    with db.GameReader("joy1") as j:
        items = j.rows("SELECT CONVERT(varchar(36), Uuid) AS Uuid, Userindex, Charidx, Code, Plate, Posx, Amount, GainDate FROM Item "
                       "WHERE Code <> ?", (GOLD_CODE,))
        copies = {str(r["NewUuid"]).upper() for r in j.rows("SELECT NewUuid FROM adm.CharCopyItemMap")} if j.one(
            "SELECT CASE WHEN OBJECT_ID('adm.CharCopyItemMap', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"] else set()
        restored = {(int(r["Userindex"]), int(r["NewCharidx"])) for r in j.rows("SELECT Userindex, NewCharidx FROM adm.CharRestored")} \
            if j.one("SELECT CASE WHEN OBJECT_ID('adm.CharRestored', 'U') IS NULL THEN 0 ELSE 1 END AS t")["t"] else set()
    with db.GameReader("joylog1") as lg:
        created = {}
        for r in lg.rows("SELECT Userindex, Charidx, Edate FROM CharEventCreate"):
            created.setdefault((int(r["Userindex"]), int(r["Charidx"])), []).append(r["Edate"])
    cats = {"стартовый набор": [], "совел (из оправы)": [], "до начала журналов": [], "копия / восстановление панелью": [],
            "не объяснено": []}
    dead = []
    five = datetime.timedelta(seconds=5)
    for it in items:
        u = it["Uuid"].upper()
        it["name"] = refdata.item(it["Code"])["name"]
        if u not in born:
            key = (int(it["Userindex"]), int(it["Charidx"]))
            g = it["GainDate"]
            if u in copies or key in restored:
                c = "копия / восстановление панелью"
            elif g and any(abs(g - e) <= five for e in created.get(key, [])):
                c = "стартовый набор"
            elif 7001 <= int(it["Code"]) < 20551:
                c = "совел (из оправы)"
            elif g and g < feed.JOURNALS_SINCE:
                c = "до начала журналов"
            else:
                c = "не объяснено"
            cats[c].append(dict(it, last=last.get(u)))
        lu = last.get(u)
        if lu and lu[2]:
            dead.append(dict(it, last_at=lu[0], last_table=lu[1], partial=bool(partial.get(u)),
                             note="часть стопки (остаток > 0) — норма" if partial.get(u) else "последнее событие — уничтожение, а строка жива"))
    return {"no_birth": {k: v for k, v in cats.items()}, "no_birth_total": sum(len(v) for v in cats.values()), "items": len(items),
            "dead_alive": dead, "errors": errors, "since": feed.JOURNALS_SINCE}


def report(full=True):
    """Окно «Дюпы»: (а) + (б) всегда, (в)/(г) — по всем журналам (full)."""
    out = {"same_uuid": same_uuid(), "amounts": bad_amounts()}
    if full:
        out.update(no_trace_and_dead())
    return out
