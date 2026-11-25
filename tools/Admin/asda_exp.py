# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""asda_exp.py — опыт персонажа: показать уровень и % опыта уровня, выставить 99 % текущего уровня. 27.10.2026.

Часть утилиты учёток (asda_accounts.py: вкладка «Опыт» и консольные команды exp-info / set-exp99).

КАК СЧИТАЕТ
  Опыт в БД накопительный: Joy1.dbo.Charinfo.Expe. Уровень L занимает отрезок [E[L], E[L+1]), где E — таблица сервера
  GameServer\\ConfigSet\\ExpTable.txt (строка «N<TAB>E» = начало уровня N; одинакова у GameServer/Indun/Ch2, md5 da383cae…).
  Копия — data/ExpTable.txt (снята с сервера 27.10.2026; при смене таблицы на сервере — обновить копию).
  99 % = E[L] + floor(0.99 × (E[L+1] − E[L])) — меньше E[L+1], уровень не меняется.

КАК ПИШЕТ
  UPDATE Charinfo SET Expe WHERE Userindex/Charidx И уровень/опыт всё ещё прежние (иначе — отказ «изменился, найдите
  заново»); после записи — сверка в той же транзакции, иначе откат. Журнал — logs/accounts.log (asda_accounts._log).

ВАЖНО: пока персонаж В ИГРЕ, GameServer держит опыт в памяти и при выходе перезапишет правку. Утилита показывает,
  в игре ли персонаж (Us_member.Flag / CharPos.Usernum), и при «в игре» просит подтверждение.

Побочных эффектов при импорте нет.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXP_TABLE = os.path.join(HERE, "data", "ExpTable.txt")   # копия GameServer\ConfigSet\ExpTable.txt
TARGET_PCT = 0.99


class ExpError(Exception):
    """Отказ операции с понятной причиной для показа пользователю."""


def load_exp_table(path=EXP_TABLE):
    """Таблица опыта: {уровень: начало уровня (накопительный опыт)}."""
    table = {}
    with open(path, encoding="ascii", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                table[int(parts[0])] = int(parts[1])
    if not table:
        raise ExpError("таблица опыта пуста: %s" % path)
    return table


def level_span(table, lvl):
    """(начало уровня, начало следующего) или отказ, если уровень последний/неизвестен."""
    if lvl not in table or lvl + 1 not in table:
        raise ExpError("уровня %d нет в таблице опыта (или он последний)" % lvl)
    return table[lvl], table[lvl + 1]


def find_char(cn, name):
    """Персонаж по точному имени: dict(uid, idx, name, lvl, expe, login, online) или отказ."""
    name = (name or "").strip()
    if not name:
        raise ExpError("введите имя персонажа")
    cur = cn.cursor()
    cur.execute("SELECT c.Userindex, c.Charidx, c.Charname, c.Lvl, c.Expe, m.Us_id, m.Flag, ISNULL(p.Usernum, -1) "
                "FROM dbo.Charinfo c JOIN AsdaStoryOP.dbo.Us_member m ON m.Userindex = c.Userindex "
                "LEFT JOIN dbo.CharPos p ON p.Userindex = c.Userindex AND p.Charidx = c.Charidx "
                "WHERE c.Charname = ?", name)
    rows = cur.fetchall()
    if not rows:
        raise ExpError("персонаж «%s» не найден" % name)
    if len(rows) > 1:
        raise ExpError("найдено несколько персонажей «%s» — уточните имя" % name)
    r = rows[0]
    return {"uid": int(r[0]), "idx": int(r[1]), "name": r[2], "lvl": int(r[3]), "expe": int(r[4]),
            "login": r[5], "online": (r[6] or 0) != 0 or int(r[7]) != -1}


def describe(ch, table):
    """Текст для показа: уровень, опыт, % уровня, в игре ли."""
    lo, hi = level_span(table, ch["lvl"])
    pct = (ch["expe"] - lo) * 100.0 / (hi - lo)
    return ("Персонаж: %s (учётка %s, ID %d, слот %d)\nУровень: %d\nОпыт: %s из %s (%.2f %% уровня)\nВ игре: %s"
            % (ch["name"], ch["login"], ch["uid"], ch["idx"], ch["lvl"], format(ch["expe"] - lo, ",").replace(",", " "),
               format(hi - lo, ",").replace(",", " "), pct, "ДА — сервер перезапишет опыт при выходе" if ch["online"] else "нет"))


def exp_info(name):
    """(персонаж, текст) по имени."""
    from asda_accounts import _db
    table = load_exp_table()
    cn = _db()
    try:
        ch = find_char(cn, name)
        return ch, describe(ch, table)
    finally:
        cn.close()


def set_exp_99(name, dry=False):
    """Выставить опыт 99 % текущего уровня. → (персонаж после, текст). dry — только посчитать."""
    from asda_accounts import _db, _log
    table = load_exp_table()
    cn = _db()
    try:
        ch = find_char(cn, name)
        lo, hi = level_span(table, ch["lvl"])
        target = lo + int(TARGET_PCT * (hi - lo))
        if dry:
            return ch, "Будет: опыт %d → %d (99 %% уровня %d)" % (ch["expe"], target, ch["lvl"])
        cn.autocommit = False
        cur = cn.cursor()
        try:
            cur.execute("UPDATE dbo.Charinfo SET Expe = ? WHERE Userindex = ? AND Charidx = ? AND Lvl = ? AND Expe = ?",
                        target, ch["uid"], ch["idx"], ch["lvl"], ch["expe"])
            if cur.rowcount != 1:
                raise ExpError("уровень или опыт персонажа изменился — найдите его заново")
            cur.execute("SELECT Lvl, Expe FROM dbo.Charinfo WHERE Userindex = ? AND Charidx = ?", ch["uid"], ch["idx"])
            lvl, expe = cur.fetchone()
            if int(lvl) != ch["lvl"] or int(expe) != target:
                raise ExpError("сверка после записи не сошлась — откат")
            cn.commit()
        except Exception:
            cn.rollback()
            raise
        finally:
            cn.autocommit = True
        _log("set-exp99", ch["login"], ch["uid"], "%s: %d → %d (ур. %d)" % (ch["name"], ch["expe"], target, ch["lvl"]))
        after = dict(ch, expe=target)
        return after, "Опыт выставлен: %d → %d (99 %% уровня %d)\n\n%s" % (ch["expe"], target, ch["lvl"], describe(after, table))
    finally:
        cn.close()


def build_tab(nb, root):
    """Вкладка «Опыт»: имя → Найти (уровень, % опыта, в игре) → «Установить 99%»."""
    import threading
    import tkinter as tk
    from tkinter import ttk, messagebox

    f = ttk.Frame(nb, padding=12)
    nb.add(f, text="Опыт")
    name = tk.StringVar()
    ttk.Label(f, text="Имя персонажа:").grid(row=0, column=0, sticky="w")
    ttk.Entry(f, textvariable=name, width=24).grid(row=0, column=1, sticky="w", padx=(4, 8))
    fbtn = ttk.Button(f, text="Найти")
    fbtn.grid(row=0, column=2, sticky="w")
    info = tk.Label(f, text="", justify="left", anchor="w", wraplength=420, font=("Segoe UI", 10))
    info.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 6))
    sbtn = ttk.Button(f, text="Установить 99%")
    sbtn.grid(row=2, column=0, columnspan=3, sticky="ew")
    sbtn.state(["disabled"])
    found = {"ch": None}

    def show(ok, text, ch=None):
        info.config(text=("" if ok else "✖ ") + text, fg="#1a1a1a" if ok else "#c62828")
        found["ch"] = ch
        fbtn.state(["!disabled"])
        sbtn.state(["!disabled"] if ch else ["disabled"])

    def bg(fn, *a):
        fbtn.state(["disabled"])
        sbtn.state(["disabled"])
        info.config(text="… выполняется", fg="#555555")

        def work():
            try:
                ch, text = fn(*a)
                root.after(0, show, True, text, ch)
            except ExpError as ex:
                root.after(0, show, False, str(ex))
            except Exception as ex:   # нет драйвера, сеть, права — показать, а не уронить окно
                root.after(0, show, False, "ошибка: %s" % ex)
        threading.Thread(target=work, daemon=True).start()

    def do_find():
        bg(exp_info, name.get())

    def do_set():
        ch = found["ch"]
        if not ch:
            return
        if ch["online"] and not messagebox.askyesno(
                "Персонаж в игре", "%s сейчас в игре: сервер перезапишет опыт при выходе.\nЗаписать всё равно?" % ch["name"]):
            return
        bg(set_exp_99, ch["name"])

    fbtn.config(command=do_find)
    sbtn.config(command=do_set)
