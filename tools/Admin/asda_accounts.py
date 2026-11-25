# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""asda_accounts.py — администрирование учёток игроков (dev-БД, SQL Server @@ASTORY_SERVER_VPN_IP@@). 18.10.2026.

ЧТО УМЕЕТ
  * создать учётку (логин + пароль) → статус и ID пользователя (Userindex);
  * сменить пароль существующей учётке (заодно снимает замок неудачных входов) → статус и ID;
  * найти учётку: ID, блок, дата создания, когда задан пароль, счётчик неудач;
  * ★ 19.10.2026 выдача (вкладка «Выдача», модуль asda_give.py): золото отдельной кнопкой и предметы по коду —
    персонажу по имени, всем персонажам учётки или всем игрокам (кроме служебных ≤ 5000); к текущему значению
    ПРИБАВЛЯЕТСЯ выданное; флаг «в игре» не проверяется — сервер должен быть выключен; предпросмотр без записи. Устройство — шапка asda_give.py.
  * ★ 01.11.2026 подарки (вкладка «Подарки», модуль asda_gifts.py): любая позиция витрин премиум-магазина 6000 и магазина
    бустеров 15300 (с иконками) — бесплатно, в элитный почтовый ящик ровно так, как её положила бы покупка; можно при
    запущенном сервере. Устройство — шапка asda_gifts.py, инструкция — ПОДАРКИ_ИНСТРУКЦИЯ.md.

КАК РАБОТАЕТ
  Только через служебные процедуры P52 (AstoryServer/Docs/SQL/ac1_01_migrate.sql, док ac1_password_check.md):
    Joy1.dbo.UP_AC_CreateAccount @id, @Plain   — проверка логина/пароля, вставка в AsdaStoryOP.dbo.Us_member,
                                                 возврат Userindex;  коды: 2 логин, 3 пароль, 4 уже есть;
    Joy1.dbo.UP_AC_SetPassword  @id, @Plain   — новый солёный хеш, сброс замка;  коды: 2 нет учётки, 3 пароль.
  MD5 от пароля считает та же функция БД (dbo.FN_AC_PwMd5Hex), что и проверка при входе (UPUserLogin), —
  правило одно. Пароль нигде не печатается и не пишется в файлы; журнал действий — без паролей.
  Подключение — общий помощник AstoryServer/Tools/Anticheat/db_connect.py (пароль SQL читается с шары PasswordSQL.txt).

ПРАВИЛА (как в БД)
  логин: 1–32 символа [A-Za-z0-9_.@-];  пароль: печатный ASCII (без кириллицы), ведущие пробелы срезаются,
  до 50 символов. Вход в игру: клиент шлёт MD5 пароля, сравнение — в UPUserLogin.

ЗАПУСК
  окно:           python AstoryAdminCenter/tools/Admin/asda_accounts.py            (или AstoryAdminCenter/tools/Admin/Accounts.bat)
  консоль:        python AstoryAdminCenter/tools/Admin/asda_accounts.py create <логин>      (пароль спросит дважды, без эха)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py passwd <логин>
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py info <логин>
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py give-gold <кому> <сколько> [--dry]
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py give-item <кому> <код> <количество> [--dry]
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py give-honor <кому> <сколько> [--dry]   (очки чести)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py send-post <кому> <код> <количество> [--dry]   (премиум-почта)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py gift <кому> <код витрины> [штук] [--dry]       (подарок, вкладка «Подарки»)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py gift-catalog [поиск]                          (витрина: можно ли подарить)
                      <кому>: char:<имя персонажа> | login:<логин> | all     (--dry — только проверить, без записи)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py exp-info <имя персонажа>          (уровень и % опыта)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py set-exp99 <имя персонажа> [--dry] (опыт = 99 % текущего уровня)
                  python AstoryAdminCenter/tools/Admin/asda_accounts.py selftest [--only gifts] [--localdb <экземпляр>] [--live-write]
                      (записи с ОТКАТОМ — только на копии в SQL LocalDB (--localdb, экземпляр проверяется до записи);
                       выдача/почта на живой БД — только с --live-write; подарки — только на LocalDB; --only gifts)
  Нужен pyodbc и ODBC-драйвер SQL Server (на машине владельца есть).

Побочных эффектов при импорте нет (закон tools-no-import-side-effects).
"""
import datetime
import getpass
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))   # ★ 25.11 (С-2): tools/Admin → AstoryAdminCenter → папка с клонами
AC_DIR = os.path.join(PORT, "AstoryServer", "Tools", "Anticheat")   # db_connect.py
LOG_PATH = os.path.join(HERE, "logs", "accounts.log")   # журнал действий: время, действие, логин, ID, итог (без паролей)

LOGIN_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,32}$")      # то же правило, что в UP_AC_CreateAccount / UPUserLogin
PW_MAX = 50                                             # ширина @Plain NVARCHAR(50)

# Коды возврата процедур P52 → понятный текст.
CREATE_CODES = {0: "создана", 2: "логин пустой, длиннее 32 или с недопустимыми символами",
                3: "пароль не подходит (пустой или не печатный ASCII)", 4: "такая учётка уже есть"}
PASSWD_CODES = {0: "пароль изменён (замок неудач снят)", 2: "учётка не найдена",
                3: "пароль не подходит (пустой или не печатный ASCII)"}


class AdminError(Exception):
    """Отказ операции с понятной причиной для показа пользователю."""


_DB_OVERRIDE = None   # ★ 01.11.2026: фабрика соединения вместо живой БД (самотест на LocalDB: selftest --localdb <экземпляр>)


def _db():
    """Соединение с Joy1 через общий помощник AstoryServer/Tools/Anticheat/db_connect.py (autocommit); в самотесте на LocalDB —
    через _DB_OVERRIDE."""
    if _DB_OVERRIDE:
        return _DB_OVERRIDE()
    if AC_DIR not in sys.path:
        sys.path.insert(0, AC_DIR)
    import db_connect
    return db_connect.connect("Joy1")


def check_login(login):
    """Логин после снятия хвостовых пробелов (как RTRIM в БД) или AdminError."""
    s = (login or "").rstrip(" ")
    if not LOGIN_RE.match(s):
        raise AdminError("логин: 1–32 символа, только латиница, цифры и _ . @ -")
    return s


def check_password(pw, pw2):
    """Пароль, совпадающий с повтором и подходящий под правило БД, или AdminError."""
    if pw != pw2:
        raise AdminError("пароль и повтор не совпадают")
    core = (pw or "").lstrip(" ")   # ведущие пробелы БД срезает (как клиент), хвостовые — часть пароля
    if not core:
        raise AdminError("пароль пустой")
    if len(pw) > PW_MAX:
        raise AdminError("пароль длиннее %d символов" % PW_MAX)
    if any(not (" " <= ch <= "~") for ch in pw):
        raise AdminError("пароль: только печатные латинские символы (без кириллицы и спецсимволов вне ASCII)")
    return pw


def _sql_reason(ex):
    """Текст RAISERROR из исключения pyodbc без служебного префикса драйвера."""
    msg = str(ex.args[-1] if getattr(ex, "args", None) else ex)
    i = msg.rfind("[SQL Server]")                       # текст после последней метки драйвера — сам RAISERROR
    if i >= 0:
        msg = msg[i + len("[SQL Server]"):]
    return re.sub(r"\s*\(\d+\)\s*(\(SQLExecDirectW\))?\s*$", "", msg).strip()   # хвост «(50000) (SQLExecDirectW)»


def _log(action, login, uid, result):
    """Строка в журнал действий (без пароля). Сбой записи журнала операцию не ломает."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s\t%s\t%s\t%s\t%s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                              action, login, "" if uid is None else uid, result))
    except OSError:
        pass


def find_account(cn, login):
    """Сведения об учётке или None: dict(id, login, block, created, pwset, pwfail, pwfail_at, has_pw)."""
    cur = cn.cursor()
    cur.execute("SELECT Userindex, us_id, us_block, us_rdate, us_pwset, us_pwfail, us_pwfail_at, "
                "CASE WHEN us_pwhash IS NULL THEN 0 ELSE 1 END "
                "FROM AsdaStoryOP.dbo.Us_member WHERE us_id = ?", login)
    r = cur.fetchone()
    if not r:
        return None
    return dict(id=int(r[0]), login=str(r[1]).rstrip(), block=r[2], created=r[3], pwset=r[4],
                pwfail=r[5], pwfail_at=r[6], has_pw=bool(r[7]))


def _exec_rc(cn, sql, params):
    """EXEC процедуры с кодом возврата: (код, последний набор строк). RAISERROR → AdminError с причиной из БД."""
    import pyodbc
    cur = cn.cursor()
    try:
        cur.execute("SET NOCOUNT ON; DECLARE @rc INT; " + sql + "; SELECT @rc AS rc", params)
        rows_before = []
        while True:
            if cur.description:
                rows = cur.fetchall()
                if [c[0] for c in cur.description] == ["rc"]:
                    return int(rows[0][0]), rows_before
                rows_before = rows
            if not cur.nextset():
                break
    except pyodbc.Error as ex:
        raise AdminError(_sql_reason(ex))
    raise AdminError("процедура не вернула код результата")


def create_account(login, pw, pw2):
    """Создаёт учётку. Возврат (ID, текст статуса). Отказ — AdminError."""
    login = check_login(login)
    check_password(pw, pw2)
    cn = _db()
    try:
        if find_account(cn, login):
            raise AdminError("такая учётка уже есть: %s" % login)
        rc, rows = _exec_rc(cn, "EXEC @rc = dbo.UP_AC_CreateAccount @id = ?, @Plain = ?", (login, pw))
        if rc != 0:
            raise AdminError(CREATE_CODES.get(rc, "код %d" % rc))
        acc = find_account(cn, login)   # ID из самой таблицы — сверка, что строка действительно есть
        uid = acc["id"] if acc else (int(rows[0][0]) if rows else None)
        if uid is None:
            raise AdminError("процедура ответила «создано», но учётка в таблице не найдена")
        _log("create", login, uid, "ok")
        return uid, "Учётка «%s» создана. ID пользователя: %d" % (login, uid)
    except AdminError as ex:
        _log("create", login, None, "отказ: %s" % ex)
        raise
    finally:
        cn.close()


def change_password(login, pw, pw2):
    """Меняет пароль. Возврат (ID, текст статуса). Отказ — AdminError."""
    login = check_login(login)
    check_password(pw, pw2)
    cn = _db()
    try:
        acc = find_account(cn, login)
        if not acc:
            raise AdminError("учётка не найдена: %s" % login)
        rc, _ = _exec_rc(cn, "EXEC @rc = dbo.UP_AC_SetPassword @id = ?, @Plain = ?", (login, pw))
        if rc != 0:
            raise AdminError(PASSWD_CODES.get(rc, "код %d" % rc))
        after = find_account(cn, login)
        if not after or not after["has_pw"] or after["pwset"] == acc["pwset"]:
            raise AdminError("процедура ответила «изменён», но в таблице пароль не обновился")
        _log("passwd", login, acc["id"], "ok")
        return acc["id"], "Пароль учётки «%s» изменён (замок неудач снят). ID пользователя: %d" % (login, acc["id"])
    except AdminError as ex:
        _log("passwd", login, acc["id"] if "acc" in locals() and acc else None, "отказ: %s" % ex)
        raise
    finally:
        cn.close()


def account_chars(cn, uid):
    """Персонажи учётки: [(слот Charidx, имя, уровень)] по возрастанию слота (удалённые — в Del_Charinfo, сюда не входят)."""
    cur = cn.cursor()
    cur.execute("SELECT Charidx, Charname, Lvl FROM dbo.Charinfo WHERE Userindex = ? ORDER BY Charidx", uid)
    return [(int(r[0]), str(r[1]).rstrip(), int(r[2] or 0)) for r in cur.fetchall()]


def account_info(login):
    """Текст сведений об учётке (с персонажами). Отказ — AdminError."""
    return account_info_ex(login)[0]


def account_info_ex(login):
    """(текст сведений об учётке, [имена персонажей]) — имена для копирования в окне. Отказ — AdminError."""
    login = check_login(login)
    cn = _db()
    try:
        a = find_account(cn, login)
        chars = account_chars(cn, a["id"]) if a else []
    finally:
        cn.close()
    if not a:
        raise AdminError("учётка не найдена: %s" % login)
    text = _account_text(a)
    if chars:
        text += "\nПерсонажи (%d): %s" % (len(chars), ", ".join("%s (ур. %d)" % (n, lv) for _, n, lv in chars))
    else:
        text += "\nПерсонажей нет"
    return text, [n for _, n, _ in chars]


def _account_text(a):
    """Строки сведений об учётке из find_account."""
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M") if d else "—"
    block = "нет" if not a["block"] else "ДА (код %s)" % a["block"]
    return ("ID пользователя: %d\nЛогин: %s\nБлок: %s\nСоздана: %s\nПароль задан: %s (%s)\nНеудачных входов: %s%s"
            % (a["id"], a["login"], block, fmt(a["created"]), "да" if a["has_pw"] else "НЕТ — вход невозможен",
               fmt(a["pwset"]), a["pwfail"] or 0,
               (" (последняя %s)" % fmt(a["pwfail_at"])) if a["pwfail_at"] else ""))


# ═════════════════════════════ окно ═════════════════════════════

def run_gui():
    """Окно с вкладками «Создать учётку», «Сменить пароль», «Найти». Операции — в фоновом потоке."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Asda — учётки и выдача (dev)")
    root.resizable(False, False)
    nb = ttk.Notebook(root)
    nb.pack(padx=10, pady=10, fill="both")

    def form(title, fields, button, action, names_box=False):
        """Вкладка: поля (подпись, пароль?), кнопка, строка статуса и поле ID. names_box — ещё поле имён персонажей
        (по одному в строке, выделяется и копируется) и кнопка «Копировать имена»; action тогда возвращает (ID, текст, имена)."""
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text=title)
        vars_ = []
        for i, (label, secret) in enumerate(fields):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar()
            ttk.Entry(f, textvariable=v, width=32, show="•" if secret else "").grid(row=i, column=1, pady=3)
            vars_.append(v)
        n = len(fields)
        btn = ttk.Button(f, text=button)
        btn.grid(row=n, column=0, columnspan=2, pady=(10, 6), sticky="ew")
        status = tk.Label(f, text="", justify="left", anchor="w", wraplength=360, font=("Segoe UI", 10))
        status.grid(row=n + 1, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="ID пользователя:").grid(row=n + 2, column=0, sticky="w", pady=(8, 0))
        idv = tk.StringVar(value="—")
        ttk.Entry(f, textvariable=idv, width=32, state="readonly").grid(row=n + 2, column=1, pady=(8, 0))
        names = None
        if names_box:   # ★ 19.10.2026 (владелец): имена персонажей учётки — с возможностью скопировать
            ttk.Label(f, text="Персонажи (копируются):").grid(row=n + 3, column=0, sticky="nw", pady=(8, 0))
            names = tk.Text(f, height=5, width=32, wrap="none", font=("Segoe UI", 10))
            names.grid(row=n + 3, column=1, pady=(8, 0), sticky="w")
            # Только чтение, но выделение и Ctrl+C / Ctrl+A работают (state=disabled в Tk запрещает и выделение копированием).
            names.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a")) else "break")

            def copy_names():
                txt = names.get("1.0", "end").strip()
                if txt:
                    root.clipboard_clear()
                    root.clipboard_append(txt)
            ttk.Button(f, text="Копировать имена", command=copy_names).grid(row=n + 4, column=1, sticky="w", pady=(4, 0))

        def done(ok, text, uid, clear, char_names=None):
            status.config(text=("✔ " if ok else "✖ ") + text, fg="#1a7f37" if ok else "#c62828")
            idv.set(str(uid) if uid is not None else "—")
            if names is not None:
                names.delete("1.0", "end")
                names.insert("1.0", "\n".join(char_names or []))
            btn.state(["!disabled"])
            if ok and clear:
                for v in vars_[1:]:
                    v.set("")   # пароли стираем из полей после успеха

        def run():
            vals = [v.get() for v in vars_]
            btn.state(["disabled"])
            status.config(text="… выполняется", fg="#555555")
            idv.set("—")

            def work():
                try:
                    res = action(*vals)
                    root.after(0, done, True, res[1], res[0], True, res[2] if len(res) > 2 else None)
                except AdminError as ex:
                    root.after(0, done, False, str(ex), None, False)
                except Exception as ex:   # нет драйвера, сеть, права — показать, а не уронить окно
                    root.after(0, done, False, "ошибка: %s" % ex, None, False)
            threading.Thread(target=work, daemon=True).start()
        btn.config(command=run)

    form("Создать учётку", [("Логин", False), ("Пароль", True), ("Повтор пароля", True)],
         "Создать", create_account)
    form("Сменить пароль", [("Логин", False), ("Новый пароль", True), ("Повтор пароля", True)],
         "Сменить пароль", change_password)

    def info(login):
        text, char_names = account_info_ex(login)
        return int(text.split("\n", 1)[0].split(":")[1]), text, char_names
    form("Найти", [("Логин", False)], "Показать", info, names_box=True)

    import asda_give   # ★ 19.10.2026: вкладка «Выдача» (золото и предметы)
    asda_give.build_tab(nb, root)
    import asda_exp    # ★ 27.10.2026: вкладка «Опыт» (уровень, % опыта, «Установить 99%»)
    asda_exp.build_tab(nb, root)
    import asda_gifts  # ★ 01.11.2026: вкладка «Подарки» (витрина магазинов с иконками → элитный почтовый ящик)
    asda_gifts.build_tab(nb, root)

    ttk.Label(root, text="Логин: латиница, цифры, _ . @ - (до 32).  Пароль: латиница/цифры/знаки, без кириллицы.",
              foreground="#666666").pack(padx=10, pady=(0, 10))
    root.mainloop()


# ═════════════════════════════ консоль ═════════════════════════════

def _localdb_factory(inst):
    """Фабрика соединения с Joy1 экземпляра SQL LocalDB (Windows-вход, autocommit) — для самотеста на копии.
    Каждое соединение сразу проверяется is_localdb(): не LocalDB — AdminError, соединение закрывается."""
    import pyodbc
    drv = sorted([d for d in pyodbc.drivers() if "SQL Server" in d], key=lambda d: ("ODBC Driver" not in d, d))
    if not drv:
        raise AdminError("нет ODBC-драйвера SQL Server")
    cs = "DRIVER={%s};SERVER=(localdb)\\%s;DATABASE=Joy1;Trusted_Connection=yes;TrustServerCertificate=yes" % (drv[0], inst)

    def connect():
        """Соединение с LocalDB, проверенное до возврата."""
        cn = pyodbc.connect(cs, autocommit=True, timeout=30)
        ok, who = is_localdb(cn)
        if not ok:
            cn.close()
            raise AdminError("самотест: соединение ведёт НЕ в LocalDB (%s) — запись запрещена" % who)
        return cn
    return connect


def is_localdb(cn):
    """(True, описание) — соединение ведёт в экземпляр SQL LocalDB (InstanceName «LOCALDB#…», редакция Express).
    ★ 02.11.2026 (ревизия п.1): проверяется ПЕРЕД первой записью самотеста — отказ, если это не LocalDB."""
    cur = cn.cursor()
    cur.execute("SELECT @@SERVERNAME, CAST(SERVERPROPERTY('InstanceName') AS NVARCHAR(128)), "
                "CAST(SERVERPROPERTY('Edition') AS NVARCHAR(128))")
    name, inst, edition = (str(v or "") for v in cur.fetchone())
    return inst.upper().startswith("LOCALDB#") and "Express" in edition, "%s / %s / %s" % (name, inst, edition)


def selftest(only="", localdb="", live_write=False):
    """Связь и отказы БЕЗ записи: недопустимый логин (код 2), чужая несуществующая учётка (код 2), повтор логина (4);
    выдача и почта — с ОТКАТОМ, только на LocalDB или с явным live_write; подарки — ТОЛЬКО на LocalDB.
    only='gifts' — только подарки; localdb — экземпляр SQL LocalDB с копией таблиц."""
    global _DB_OVERRIDE
    if localdb:
        _DB_OVERRIDE = _localdb_factory(localdb)
        cn = _db()   # фабрика сама проверяет, что это LocalDB
        print("БД: SQL LocalDB (localdb)\\%s — %s" % (localdb, is_localdb(cn)[1]))
        cn.close()
    if only == "gifts":
        ok = _selftest_gifts()
        print("SELFTEST", "OK" if ok else "FAIL")
        return 0 if ok else 1
    cn = _db()
    ok = True
    try:
        rc, _ = _exec_rc(cn, "EXEC @rc = dbo.UP_AC_SetPassword @id = ?, @Plain = ?", ("__no_such_user__", "x"))
        print("SetPassword несуществующей: код", rc); ok &= rc == 2
    except AdminError as ex:
        print("SetPassword несуществующей: отказ БД —", ex); ok &= "не найдена" in str(ex)
    try:
        rc, _ = _exec_rc(cn, "EXEC @rc = dbo.UP_AC_CreateAccount @id = ?, @Plain = ?", ("bad login!", "x"))
        print("CreateAccount плохой логин: код", rc); ok &= rc == 2
    except AdminError as ex:
        print("CreateAccount плохой логин: отказ БД —", ex); ok &= "логин" in str(ex)
    cur = cn.cursor()
    cur.execute("SELECT TOP 1 us_id FROM AsdaStoryOP.dbo.Us_member ORDER BY Userindex")
    existing = str(cur.fetchone()[0]).rstrip()
    try:
        rc, _ = _exec_rc(cn, "EXEC @rc = dbo.UP_AC_CreateAccount @id = ?, @Plain = ?", (existing, "x"))
        print("CreateAccount существующий логин: код", rc); ok &= rc == 4
    except AdminError as ex:
        print("CreateAccount существующий логин: отказ БД —", ex); ok &= "уже есть" in str(ex)
    a = find_account(cn, existing)
    print("Найти существующую: ID", a["id"] if a else None); ok &= bool(a)
    cn.close()
    for bad in [("", "a", "a"), ("ok", "пароль", "пароль"), ("ok", "a", "b")]:
        try:
            check_login(bad[0]); check_password(bad[1], bad[2]); ok = False; print("проверка НЕ поймала", bad[0] or "<пусто>")
        except AdminError as ex:
            print("локальная проверка:", ex)
    # ★ 02.11.2026 (ревизия п.2): запись с откатом в ЖИВУЮ БД держит замки ящика/инвентаря и видна NOLOCK-чтению —
    #   только по явному флагу --live-write (решение владельца); на LocalDB — всегда.
    if localdb or live_write:
        ok &= _selftest_give()
        ok &= _selftest_post()
    else:
        print("выдача/почта с записью: пропущено (живая БД; нужен --localdb <экземпляр> или --live-write)")
    if localdb:
        ok &= _selftest_gifts()
    else:
        print("подарки с записью: пропущено (только на LocalDB: --localdb <экземпляр>)")
    print("SELFTEST", "OK" if ok else "FAIL")
    return 0 if ok else 1


def _selftest_give():
    """Выдача по-настоящему, но с ОТКАТОМ: персонаж служебной учётки получает золото, стопку, предмет снаряжения;
    сверка «было + выдано», затем откат и проверка, что в БД всё как было. Отказ: код вне таблиц."""
    import asda_give as G
    ok = True
    cn = _db()
    try:
        cur = cn.cursor()
        cur.execute("SELECT c.Userindex, c.Charidx, c.Charname, m.us_id FROM dbo.Charinfo c "
                    "JOIN AsdaStoryOP.dbo.Us_member m ON m.Userindex = c.Userindex "
                    "WHERE c.Userindex <= ? ORDER BY c.Userindex, c.Charidx", G.OPERATOR_MAX_UID)
        r = cur.fetchone()
        if not r:
            print("выдача: нет персонажа служебной учётки — проверка записи пропущена")
            return True
        t = dict(uid=int(r[0]), cidx=int(r[1]), name=str(r[2]).rstrip(), login=str(r[3]).rstrip())

        def snap():
            cur.execute("SELECT Plate, Posx, Code, Amount, Weight FROM dbo.Item WHERE Userindex = ? AND Charidx = ? "
                        "ORDER BY Plate, Posx", t["uid"], t["cidx"])
            items = [tuple(x) for x in cur.fetchall()]
            cur.execute("SELECT Fmpoint FROM dbo.CharFameBank WHERE Userindex = ? AND Charidx = ?", t["uid"], t["cidx"])
            return items, [tuple(x) for x in cur.fetchall()]   # инвентарь и очки чести
        before = snap()
        for what, code, qty in (("gold", 0, 12345), ("honor", 0, 500), ("item", 20571, 3), ("item", 20724, 1), ("item", 37, 2)):
            res, text = G._give_one(cn, t, what, code, qty, dry=False, commit=False)
            print("выдача с откатом %s %s×%d → %s: %s" % (what, code or "", qty, "ok" if res else "ОТКАЗ", text))
            ok &= res
        after = snap()
        print("после отката инвентарь как был:", after == before); ok &= after == before
        try:
            G.item_spec(600); ok = False; print("код 600 НЕ отвергнут")
        except G.GiveError as ex:
            print("код вне таблиц:", ex)
    finally:
        cn.close()
    return ok


def _selftest_post():
    """Премиум-почта по-настоящему, но с ОТКАТОМ: персонаж служебной учётки получает 9 копий (строки 7 + 2); список ящика
    процедурой сервера UPCashitemList видит подарок первым; затем откат и проверка, что ящик как был. Отказ стопочного кода."""
    import asda_give as G
    ok = True
    cn = _db()
    try:
        cur = cn.cursor()
        cur.execute("SELECT TOP 1 c.Userindex, c.Charidx, c.Charname, m.us_id FROM dbo.Charinfo c JOIN AsdaStoryOP.dbo.Us_member m "
                    "ON m.Userindex = c.Userindex WHERE c.Userindex <= ? ORDER BY c.Userindex, c.Charidx", G.OPERATOR_MAX_UID)
        r = cur.fetchone()
        if not r:
            print("почта: нет персонажа служебной учётки — проверка пропущена")
            return True
        t = dict(uid=int(r[0]), cidx=int(r[1]), name=str(r[2]).rstrip(), login=str(r[3]).rstrip())

        def box():
            cur.execute("SELECT iType, Orderidx, Code, Amount FROM dbo.ItemPostBox WHERE Userindex = ? AND Charidx = ?",
                        t["uid"], t["cidx"])
            return sorted(tuple(x) for x in cur.fetchall())
        before = box()
        # Список глазами сервера (UPCashitemList) — внутри транзакции, затем откат.
        cn.autocommit = False
        used = {x[1] for x in before}
        want = G._free_orders(used, 2)
        for o, c in zip(want, (7, 2)):
            cur.execute("INSERT INTO dbo.ItemPostBox (iType, Orderidx, Userindex, Charidx, Code, Amount) VALUES (?, ?, ?, ?, ?, ?)",
                        G.POST_BUY_TYPE, o, t["uid"], t["cidx"], 20724, c)
        cur.execute("EXEC dbo.UPCashitemList ?, ?", t["uid"], t["cidx"])
        lst = [tuple(x) for x in cur.fetchall()]
        cn.rollback()
        cn.autocommit = True
        first = lst[:2] == [(want[0], 20724, 7, G.POST_BUY_TYPE), (want[1], 20724, 2, G.POST_BUY_TYPE)]
        print("почта: UPCashitemList показывает подарок первым %s: %s" % (lst[:3], first)); ok &= first
        res, text = G._post_one(cn, t, 20724, 9, dry=False, commit=False)
        print("почта с откатом 20724×9 → %s: %s" % ("ok" if res else "ОТКАЗ", text)); ok &= res
        after = box()
        print("почта: после отката ящик как был:", after == before); ok &= after == before
        # ★ 01.11.2026: стопочный 20571 почтой разрешён, если на всех GS включён P98 (стопка из 1 шт. на ячейку);
        #   колчан 20563 — отказ всегда (P98 тип 10 не трогает).
        p98 = G.p98_on()
        for bad, must_refuse in ((20571, not p98), (20563, True)):
            try:
                G.post_spec(bad)
                print("почта: код %d принят (P98 %s)" % (bad, "включён" if p98 else "выключен")); ok &= not must_refuse
            except G.GiveError as ex:
                print("почта: код %d отвергнут: %s" % (bad, ex)); ok &= must_refuse
    finally:
        cn.close()
    return ok


def _selftest_gifts():
    """Подарки: каталог и иконки; позиции коробка / набор / спецпредмет с зарядами по живым правилам сервера; стопочный
    (по P98 — верное количество или отказ) и колчан (отказ); запись в ящик по-настоящему с ОТКАТОМ (commit=False) —
    строки как у покупки, UPCashitemList видит подарок первым, после отката ящик как был; «все игроки» без ≤ 5000;
    журнал; «проверка» (dry) ничего не пишет."""
    import tempfile
    import asda_gifts as A
    import asda_give as G
    ok = True

    def check(cond, text):
        """Строка самотеста «ok / FAIL» и накопление итога."""
        nonlocal ok
        print(("  ok   " if cond else "  FAIL ") + text)
        ok &= bool(cond)

    print("подарки:")
    cat = A.load_catalog()
    cov = cat["coverage"]
    miss = [c for c, it in cat["items"].items() if not it["icon"] or not os.path.exists(os.path.join(A.ICON_ROOT, it["icon"]))]
    check(cov["rows"] > 0 and not miss, "каталог: строк %d, кодов %d, иконок на диске %d из %d" % (
        cov["rows"], cov["codes"], cov["codes"] - len(miss), cov["codes"]))
    r = A.rules()
    print("  P98 %s, P100 %s" % (r.p98, r.p100))
    rows = A.catalog_rows()
    offers = {x["code"]: r.offer(x["code"]) for x in rows}
    sets = [x["code"] for x in rows if offers[x["code"]]["ok"] and offers[x["code"]]["contents"]
            and any(p["path_ru"].startswith("Элитный набор") for p in x["places"])]
    boxes = [c for c, o in offers.items() if o["ok"] and o["buy_type"] == A.BUY_TYPE_SHELL and o["contents"]
             and c not in sets]
    charged = [c for c, o in offers.items() if o["ok"] and o["buy_type"] == A.BUY_TYPE_FUNC and any(
        "заряд" in n for n in o["notes"])]
    one = lambda o: A.describe_offer(o).replace("\n", " | ")
    check(bool(boxes), "коробка: %s" % (one(offers[boxes[0]]) if boxes else "НЕТ"))
    check(bool(sets), "набор: %s" % (one(offers[sets[0]]) if sets else "НЕТ"))
    if charged:
        o = offers[charged[0]]
        check(o["delivery"] != o["code"] and o["buy_type"] == A.BUY_TYPE_FUNC, "спецпредмет с зарядами: %s" % one(o))
    else:
        check(False, "спецпредмет с зарядами: на витрине не найден")
    # Стопочных и колчанов на витрине нет — правило забора проверяется на их кодах выдачи напрямую.
    for code, kind in ((20571, "stack"), (20563, "quiver")):
        o = r.landing(dict(code=code, delivery=code, price=None, buy_type=A.BUY_TYPE_SHELL, spec=None, contents=[],
                           ok=False, why="", notes=[]))
        if kind == "stack":
            want = all(r.p98.values())
            check(o["ok"] == want and (want or "P98" in o["why"]),
                  "стопочный %d: %s" % (code, ("можно, " + "; ".join(o["notes"])) if o["ok"] else "отказ: " + o["why"]))
        else:
            check(not o["ok"] and "колчан" in o["why"], "колчан %d: отказ: %s" % (code, o["why"]))
    refused = [c for c, o in offers.items() if not o["ok"]]
    print("  витрина: можно %d, нельзя %d (%s)" % (len(offers) - len(refused), len(refused), ", ".join(map(str, refused))))
    cn = _db()
    try:
        is_ldb, who = is_localdb(cn)
        check(is_ldb, "соединение самотеста подарков — LocalDB: %s" % who)
        if not is_ldb:
            print("  СТОП: запись подарков разрешена только на LocalDB")
            return False
        cur = cn.cursor()
        raw_all = G.resolve_targets(cn, "all", "")
        all_t, ban_lines = G.split_banned(raw_all, "all")
        ban = G.banned_accounts()
        check(not any(t["uid"] in ban for t in all_t) and len(ban_lines) == sum(1 for t in raw_all if t["uid"] in ban),
              "«все игроки»: реестр банов %d учёток, исключено персонажей %d, осталось %d" % (
                  len(ban), len(ban_lines), len(all_t)))
        cur.execute("SELECT COUNT(*) FROM dbo.Charinfo WHERE Userindex <= ?", G.OPERATOR_MAX_UID)
        n_op = int(cur.fetchone()[0])
        check(all_t and min(t["uid"] for t in all_t) > G.OPERATOR_MAX_UID,
              "«все игроки»: %d персонажей, наименьший Userindex %d, служебных (≤ %d) в базе %d — исключены" % (
                  len(all_t), min(t["uid"] for t in all_t), G.OPERATOR_MAX_UID, n_op))
        cur.execute("SELECT TOP 1 c.Userindex, c.Charidx, c.Charname, m.us_id FROM dbo.Charinfo c JOIN AsdaStoryOP.dbo.Us_member m "
                    "ON m.Userindex = c.Userindex WHERE c.Userindex <= ? ORDER BY c.Userindex, c.Charidx", G.OPERATOR_MAX_UID)
        x = cur.fetchone()
        if not x:
            check(False, "нет персонажа служебной учётки для записи с откатом")
            return ok
        t = dict(uid=int(x[0]), cidx=int(x[1]), name=str(x[2]).rstrip(), login=str(x[3]).rstrip())

        def box():
            """Снимок ящика проверяемого персонажа (отсортированные строки)."""
            cur.execute("SELECT iType, Orderidx, Code, Amount FROM dbo.ItemPostBox WHERE Userindex = ? AND Charidx = ?",
                        t["uid"], t["cidx"])
            return sorted(tuple(int(v) for v in y) for y in cur.fetchall())
        before = box()
        ch = A.CHANNELS[A.DEFAULT_CHANNEL]
        for code in [boxes[0], sets[0]] + charged[:1]:
            o = offers[code]
            # Запись и список «глазами сервера» (UPCashitemList) в одной транзакции, затем откат.
            cn.autocommit = False
            want = A._free_orders({y[1] for y in before}, 2)
            for n, c in zip(want, (7, 2)):
                for _ in range(c):
                    cur.execute("INSERT INTO dbo.ItemPostBox (iType, Orderidx, Userindex, Charidx, Code, Amount) "
                                "VALUES (?, ?, ?, ?, ?, 1)", o["buy_type"], n, t["uid"], t["cidx"], o["delivery"])
            cur.execute("EXEC dbo.UPCashitemList ?, ?", t["uid"], t["cidx"])
            lst = [tuple(int(v) for v in y) for y in cur.fetchall()]
            cn.rollback()
            cn.autocommit = True
            exp = [(want[0], o["delivery"], 1, o["buy_type"])] * 7 + [(want[1], o["delivery"], 1, o["buy_type"])] * 2
            check(lst[:9] == exp, "UPCashitemList (процедура сервера) видит подарок %d первым: заказы %s, строк %d" % (
                code, want, sum(1 for y in lst if y[0] in want)))
            res, text, orders = ch.deliver(cn, t, o, 9, dry=False, commit=False)
            check(res and orders == want, "запись с откатом %d ×9 → %s" % (code, text))
            check(box() == before, "после отката ящик как был")
        # Публичный путь gift(): «проверка» ничего не пишет; журнал — во временный файл (commit=False, откат).
        jpath = os.path.join(tempfile.mkdtemp(prefix="gifts_selftest_"), "gifts.tsv")
        n_ok, n_skip, lines = A.gift("char", t["name"], boxes[0], 3, dry=True, journal=jpath, db=_db)
        check(n_ok == 1 and box() == before and not os.path.exists(jpath),
              "проверка (dry): %s; ящик не изменился, журнал не писался" % lines[-1])
        n_ok, n_skip, lines = A.gift("char", t["name"], boxes[0], 3, dry=False, journal=jpath, commit=False, db=_db)
        jrows = open(jpath, encoding="utf-8").read().splitlines() if os.path.exists(jpath) else []
        rec = dict(zip(A.JOURNAL_HEAD, jrows[1].split("\t"))) if len(jrows) == 2 else {}
        check(n_ok == 1 and box() == before and rec.get("персонаж") == t["name"] and rec.get("код") == str(boxes[0])
              and rec.get("штук") == "3" and rec.get("заказы") and rec.get("кто"),
              "журнал: %s" % (" | ".join("%s=%s" % kv for kv in rec.items()) if rec else "строки нет"))
        try:
            A.gift("char", t["name"], refused[0] if refused else 999999, 1, dry=True, db=_db)
            check(False, "отказная позиция НЕ отвергнута")
        except G.GiveError as ex:
            check(True, "отказная позиция отвергнута до записи: %s" % ex)
    finally:
        cn.close()
    return ok


def _gift_cli(cmd, args):
    """Консоль подарков: gift <кому> <код витрины> [штук] [--dry] | gift-catalog [поиск]."""
    import asda_gifts
    if cmd == "gift-catalog":
        try:
            print("\n".join(asda_gifts.cli_catalog(" ".join(args))))
            return 0
        except asda_gifts.G.GiveError as ex:
            print("ОТКАЗ:", ex)
            return 1
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]
    if len(args) not in (2, 3) or not (args[0] == "all" or args[0].startswith(("char:", "login:"))):
        print(__doc__)
        return 2
    mode, _, value = args[0].partition(":") if args[0] != "all" else ("all", "", "")
    try:
        print(asda_gifts.describe_offer(asda_gifts.rules().offer(int(args[1]))))
        ok_n, skip_n, lines = asda_gifts.gift(mode, value, args[1], args[2] if len(args) == 3 else 1, dry=dry)
    except (asda_gifts.G.GiveError, AdminError, ValueError) as ex:
        print("ОТКАЗ:", ex)
        return 1
    print("\n".join(lines))
    return 0 if skip_n == 0 else 1


def _give_cli(cmd, args):
    """Консольная выдача: give-gold <кому> <сколько> | give-item <кому> <код> <количество>; --dry — без записи."""
    import asda_give
    dry = "--dry" in args
    args = [a for a in args if a != "--dry"]
    need = 2 if cmd in ("give-gold", "give-honor") else 3   # give-item / send-post: <кому> <код> <количество>
    if len(args) != need or not (args[0] == "all" or args[0].startswith(("char:", "login:"))):
        print(__doc__)
        return 2
    mode, _, value = args[0].partition(":") if args[0] != "all" else ("all", "", "")
    if not dry and cmd != "send-post":   # ящик сервер читает сам — для почты выключать его не нужно
        print("ВНИМАНИЕ:", asda_give.SERVER_OFF_WARNING)
    try:
        if cmd in ("give-gold", "give-honor"):
            ok_n, skip_n, lines = asda_give.give(mode, value, "gold" if cmd == "give-gold" else "honor", args[1], dry=dry)
        elif cmd == "send-post":
            ok_n, skip_n, lines = asda_give.send_post(mode, value, args[1], args[2], dry=dry)
        else:
            ok_n, skip_n, lines = asda_give.give(mode, value, "item", args[2], args[1], dry=dry)
    except (asda_give.GiveError, AdminError) as ex:
        print("ОТКАЗ:", ex)
        return 1
    print("\n".join(lines))
    return 0 if skip_n == 0 else 1


def main(argv):
    """Без аргументов — окно; create/passwd/info <логин>; give-gold/give-item; selftest."""
    # ★ 02.11.2026 (ревизия п.1): при запуске файлом модуль зовётся «__main__», а asda_give/asda_gifts/asda_exp делают
    #   `from asda_accounts import _db` — без этой строки грузилась ВТОРАЯ копия модуля со своим _DB_OVERRIDE = None, и
    #   самотест «на LocalDB» уходил в живую БД. Теперь «asda_accounts» — этот же модуль.
    sys.modules.setdefault("asda_accounts", sys.modules[__name__])
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if not argv:
        run_gui()
        return 0
    cmd = argv[0]
    if cmd == "selftest":
        rest = argv[1:]
        only = rest[rest.index("--only") + 1] if "--only" in rest and rest.index("--only") + 1 < len(rest) else ""
        inst = rest[rest.index("--localdb") + 1] if "--localdb" in rest and rest.index("--localdb") + 1 < len(rest) else ""
        return selftest(only=only, localdb=inst, live_write="--live-write" in rest)
    if cmd in ("give-gold", "give-honor", "give-item", "send-post"):
        return _give_cli(cmd, argv[1:])
    if cmd in ("gift", "gift-catalog"):   # ★ 01.11.2026: подарки (asda_gifts.py)
        return _gift_cli(cmd, argv[1:])
    if cmd in ("exp-info", "set-exp99"):   # ★ 27.10.2026: опыт персонажа (asda_exp.py)
        import asda_exp
        rest = [a for a in argv[1:] if a != "--dry"]
        if len(rest) != 1:
            print(__doc__)
            return 2
        try:
            if cmd == "exp-info":
                print(asda_exp.exp_info(rest[0])[1])
            else:
                print(asda_exp.set_exp_99(rest[0], dry="--dry" in argv)[1])
            return 0
        except (asda_exp.ExpError, AdminError) as ex:
            print("ОТКАЗ:", ex)
            return 1
    if cmd not in ("create", "passwd", "info") or len(argv) != 2:
        print(__doc__)
        return 2
    try:
        if cmd == "info":
            print(account_info(argv[1]))
            return 0
        pw = getpass.getpass("Пароль: ")
        pw2 = getpass.getpass("Повтор: ")
        uid, text = (create_account if cmd == "create" else change_password)(argv[1], pw, pw2)
        print("OK:", text)
        print("ID:", uid)
        return 0
    except AdminError as ex:
        print("ОТКАЗ:", ex)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
