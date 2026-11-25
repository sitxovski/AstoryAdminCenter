# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest.py — самопроверка админ-центра. 16.11.2026.

БЕЗ СЕТИ (всегда):
  A. примитивы — TOTP по векторам RFC 6238, шифрование секрета TOTP, PBKDF2 и правила пароля, рубеж «только чтение»,
     перекодировка Arabic ↔ cp1251, вычистка секретов из журнала;
  B. служба целиком на временной базе LocalDB ((localdb)\\MSSQLLocalDB, база AsdaAdminSelftest_<случайное>, схема —
     тот же sql/adminc_02_schema.sql): вход, CSRF, Host, второй фактор, роли, операции, откат через журнал, замок,
     статика и обход каталога. База удаляется в конце.
С --live (после выкладки): чтение живых баз логином asda_admin — права (sql/adminc_10_verify.sql), состояние стойки,
  поиск, карточки учётки и персонажа, лента, след предмета. Ничего не пишет в игровые базы (права это и не дают).
Код возврата 0 — всё прошло.
"""
import datetime
import http.client
import json
import os
import re
import secrets
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import audit, auth, config, db, ops  # noqa: E402
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика

RESULTS = []   # (имя, ок, подробность)
_SRV = []      # служба части B (для проверок счётчика соединений)


def check(name, cond, detail=""):
    """Записать результат проверки."""
    RESULTS.append((name, bool(cond), detail))
    print("%s %s%s" % ("ok  " if cond else "FAIL", name, (" — " + str(detail)) if detail and not cond else ""))
    return bool(cond)


def raises(fn, exc=Exception):
    """Бросает ли fn исключение exc."""
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# ------------------------------------------------------------------ A. примитивы

def part_a():
    sec = b"12345678901234567890"                                  # RFC 6238, приложение B (SHA-1)
    check("TOTP t=59", auth.totp_code(sec, 59 // 30) == "287082")
    check("TOTP t=1111111109", auth.totp_code(sec, 1111111109 // 30) == "081804")
    check("TOTP t=2000000000", auth.totp_code(sec, 2000000000 // 30) == "279037")
    check("TOTP окно ±1", auth.totp_check(sec, "287082", now=59 + 30) and not auth.totp_check(sec, "287082", now=59 + 95))
    check("TOTP мусор", not auth.totp_check(sec, "abc") and not auth.totp_check(sec, "") and not auth.totp_check(sec, "1234567"))
    key = os.urandom(32)
    s2 = auth.totp_new_secret()
    blob = auth.totp_seal(s2, key)
    check("TOTP шифр туда-обратно", auth.totp_open(blob, key) == s2 and blob[12:] != s2 and len(blob) == 32)
    check("TOTP шифр: свежий nonce", auth.totp_seal(s2, key) != blob)
    h, salt, it = auth.hash_password("Пароль-тест-123", iters=1000)
    check("PBKDF2 верно", auth.verify_password("Пароль-тест-123", h, salt, it))
    check("PBKDF2 неверно", not auth.verify_password("Пароль-тест-124", h, salt, it))
    check("пароль: короткий", raises(lambda: auth.check_password_rules("short1"), auth.AuthError))
    check("пароль: = логину", raises(lambda: auth.check_password_rules("ownerowner", "OwnerOwner"), auth.AuthError))
    check("пароль: однообразный", raises(lambda: auth.check_password_rules("aaaaaaaaaaaa"), auth.AuthError))
    check("логин: плохой", raises(lambda: auth.check_login_rules("a b"), auth.AuthError))
    ok_sql = ["SELECT 1", "WITH x AS (SELECT 1 a) SELECT a FROM x", "SELECT 'DROP TABLE x' AS s",
              "SELECT 1 -- DELETE\n", "SET NOCOUNT ON; SELECT 1"]
    bad_sql = ["DELETE FROM Item", "SELECT 1; DROP TABLE Item", "UPDATE Charinfo SET Lvl=1", "EXEC sp_who",
               "SELECT * INTO #t FROM Item", "select 1 /* */; truncate table x", "WAITFOR DELAY '00:00:05'",
               "SELECT * FROM OPENROWSET('a','b','c')", "INSERT Item VALUES (1)",
               "SELECT '--'; DELETE FROM Item", "SELECT 1; UPDATETEXT x", "SELECT NEXT VALUE FOR s", "SELECT 'a",
               "SELECT [a--b] FROM t; DELETE t", "SELECT 1 /* x", "SELECT 1DELETE FROM t", "SELECT 1TRUNCATE TABLE t",
               "SELECT 1UPDATE t SET a=2", "SELECT 1e1DELETE FROM t"]
    check("только чтение: пропускает", all(not raises(lambda q=q: db.assert_select_only(q), db.DbError) for q in ok_sql))
    check("только чтение: отказывает", all(raises(lambda q=q: db.assert_select_only(q), db.DbError) for q in bad_sql),
          [q for q in bad_sql if not raises(lambda q=q: db.assert_select_only(q), db.DbError)])
    ru = "Привет, Мир! ёЁ №"
    arab = db.to_db_text(ru)
    check("Arabic↔cp1251 туда-обратно", db.fix_text(arab) == ru and arab != ru)
    check("Arabic: все 256 байт", all(db.fix_text(bytes([b]).decode("cp1256")) == bytes([b]).decode("cp1251", "replace")
                                      for b in range(256)))
    from api import server
    m = server.mask_net({"row_json": '{"ip":"9.165.147.34","mac":"2c-f0-5d-a1-e6-24"}', "IpAddress": "1.2.3.4",
                         "Code": 202, "detail": "x"})
    check("маска IP/MAC для ролей без сети", "9.165" not in m["row_json"] and "2c-f0" not in m["row_json"]
          and m["IpAddress"] == "—" and m["Code"] == 202)
    line = '"GET /api/players/search?q=1.2.3.4 HTTP/1.1" 200 -'
    check("журнал доступа без строки запроса", "1.2.3.4" not in server.strip_query(line) and "/api/players/search" in server.strip_query(line))
    from domains import players
    check("связи учёток: заглушки и частные IP не в счёт", not players._linkable_ip("0") and
          not players._linkable_ip("192.168.1.1") and not players._linkable_ip("@@ASTORY_SERVER_WAN_IP@@") and players._linkable_ip("9.165.147.34"))
    check("связи учёток: MAC", players._linkable_mac("2c-f0-5d-a1-e6-24") and not players._linkable_mac("00-00-00-00-00-00")
          and not players._linkable_mac(""))
    _qr_check()
    from core import i18n
    from domains import items
    i18n.set_lang("en")
    check("перевод: шаблон с подстановкой", i18n.tr("пароль короче 10 символов") == "password shorter than 10 characters"
          and i18n.tr("нет права «users.manage»") == "no permission “users.manage”" and i18n.tr("непереведённое") == "непереведённое")
    # перепроверка 4 М24: КАЖДЫЙ текст отказа и предупреждения из кода имеет шаблон (подстановки — образцы)
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    texts = set()
    calls = ("OpRefused", "append", "HttpError", "DbError", "HostError", "AuthError", "NotFound", "Busy", "ValueError")
    files = list((root / "domains").rglob("*.py")) + list((root / "core").glob("*.py")) + [root / "api" / "server.py"]   # ★ А4.0: и domains/cs_kinds
    for f in files:                                       # перепроверка 5 М7: и служебные ошибки core/api
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in calls and node.args:
                for a in node.args[:2]:
                    if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Mod):
                        a = a.left
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and any("а" <= ch <= "я" for ch in a.value.lower()):
                        texts.add(a.value.replace("%%", "\x00").replace("%d", "1").replace("%s", "X").replace("\x00", "%"))
    texts.add(items.RECENT_WARN)
    # составные тексты «… %s …» % (вариант | вариант) — проверяются готовыми вариантами
    texts.update({"уже отключён", "уже включён", "прибавка достигает 88 %: при разборе предмет даст камень заточки",
                  "прибавка опускается ниже 88 %: при разборе предмет больше не даст камня заточки"})
    texts.discard("уже X")
    texts.discard("прибавка X 88 %: при разборе предмет X")
    miss = sorted(t for t in texts if i18n.tr(t) == t)
    check("перевод: у всех текстов отказов и предупреждений есть шаблон (%d текстов)" % len(texts), not miss, "; ".join(miss[:5]))
    _src = (root / "core" / "i18n.py").read_text(encoding="utf-8")
    check("перевод: в шаблонах нет управляющих байтов вместо обратных ссылок (перепроверка 18 М6)", not any(ord(ch) < 9 for ch in _src))
    check("перевод: имя персонажа не переводится (М18)", i18n.tr("персонаж щит") == "character щит"
          and i18n.tr("персонаж логин") == "character логин")
    check("перевод: колчан — свой шаблон (М23)", "quiver" in i18n.tr(
        "сервер не дал бы надеть: этот колчан не подходит к надетому оружию (код 3)"))
    check("перевод: вложенная причина", i18n.tr("откат только когда игрок не в игре: персонаж не найден")
          == "undo only while the player is offline: character not found")
    i18n.set_lang("ru")
    check("перевод: RU — как есть", i18n.tr("пароль короче 10 символов") == "пароль короче 10 символов")
    # перепроверка 4 М24: запись свойств без базы — формат времени, отпечаток, текст UPDATE
    import datetime
    from domains import itemedit
    check("свойства: _ms как CONVERT 121", itemedit._ms(datetime.datetime(2026, 11, 16, 20, 22, 0, 997000)) == "2026-11-16 20:22:00.997"
          and itemedit._ms(datetime.datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02 03:04:05.000")
    sig = itemedit._sig({"Upcount": 3, "Cell1": 0}, {"Upcount": 5, "Cell1": 7001, "Uc1": "U", "Fdate": datetime.datetime.now()})
    check("свойства: отпечаток «было → стало» без Uc/Fdate, переживает JSON",
          sig == {"Upcount": [3, 5], "Cell1": [0, 7001]} and json.loads(json.dumps(sig)) == sig)

    class _W:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
            return 1
    w = _W()
    itemedit._apply(w, 1, 10, "U", {"Cell1": 0, "Fdate": "2026-11-16 20:22:00.997", "Uc1": None},
                    {"Cell1": 7001, "Fdate": datetime.datetime(2026, 11, 16, 21, 0), "Uc1": "N"})
    check("свойства: UPDATE — Fdate через CONVERT 121, NULL-безопасное сравнение",
          "CONVERT(varchar(23), Fdate, 121) = ?" in w.sql and "2026-11-16 20:22:00.997" in w.params
          and "(Uc1 = ? OR (Uc1 IS NULL AND ? IS NULL))" in w.sql)
    from domains import accounts
    wh, pr = accounts._row_where({"Userindex": 2, "Uid": "x", "Cou": 1, "grade": 1, "BlackDate": "2026-11-16 23:10:00.000",
                                  "CloseDate": "2026-11-17 00:10:00.000", "Reason": "r"})
    check("блок: условие строки — дата из журнала как datetime", isinstance(pr[4], datetime.datetime) and pr[4].minute == 10
          and "BlackDate = ?" in wh)
    check("блок: действующие строки — только не истёкшие", len(accounts._active([{"CloseDate": "2000-01-01 00:00:00.000"},
                                                                                 {"CloseDate": datetime.datetime(2999, 1, 1)}])) == 1)
    from domains import players as _pl
    check("блок: состояние как у сервера (5 + все строки истекли → истёк; 5 без строк → действует; 0 → нет)",
          _pl.block_state(5, 1, 0, None)["state"] == "expired" and _pl.block_state(5, 2, 1, None)["state"] == "active"
          and _pl.block_state(5, 0, 0, None)["state"] == "active" and _pl.block_state(0, 0, 0, None)["state"] == "none"
          and _pl.block_state(1, 1, 0, None)["state"] == "active")
    # смена имени: правило A13 (набор 0) — весь корпус P68 (тот же, на котором дым A13 сверил SQL-функцию: 0 расхождений)
    from domains import charname as _cn
    corp = pathlib.Path(__file__).resolve().parents[2] / "AstoryServer" / "Patches" / "AsdaPatch" / "tools" / "name_corpus_p68.txt"   # ★ 25.11 (М-3)
    if not corp.exists():
        P.skip("имя: правило A13 против корпуса P68", "нет файла %s" % corp)
    else:
        bad, n = [], 0
        for ln in corp.read_text(encoding="utf-8").splitlines():
            q = ln.split()
            if len(q) >= 3 and q[0] == "0":
                n += 1
                got = _cn.rule(bytes.fromhex(q[2]) if q[2] != "-" else b"", [])
                if got != int(q[1]):
                    bad.append(q[2])
        check("имя: правило A13 (набор 0) совпадает с корпусом P68 (%d имён)" % n, n > 1000 and not bad, ", ".join(bad[:5]))
    check("имя: запрещённое слово — правило 5, регистр как в оригинале", _cn.rule(b"xBuyasdastory1", [b"Buyasdastory"]) == 0
          and _cn.rule(b"xbuyasdastory1", [b"buyasdastory"]) == 5 and _cn.rule(b"XBUYASDASTORY", [b"buyasdastory"]) == 5)
    from domains import rename as _rn

    class _NR:
        """Подставной читатель для правила имени: настройки A13, слова, оператор, занятость."""
        def __init__(self, oper=False, lewd=(), taken=()):
            self.oper, self.lewd, self.taken = oper, list(lewd), list(taken)

        def rows(self, sql, params=()):
            if "A13_NameRuleConfig" in sql:
                return [{"Mode": 0, "Charset": 0, "CurseWords": True, "RenameLewdDup": True, "ExemptOperators": True}]
            if "A13_CurseWord" in sql:
                return [{"Word": b"buyasdastory"}]
            if "LewdWordList" in sql:
                return [{"LewdWord": w} for w in self.lewd]
            if "CharGmInfo" in sql:
                return [{"x": 1}] if self.oper else []
            return self.taken
    ck = lambda nr, name, cur=b"Old1": _rn._check_name(nr, 9, 1, name, cur)
    check("имя: LewdWordList без учёта регистра (В3)", (ck(_NR(lewd=["fuck"]), "FUCKer1") or "").endswith("(правило 6)"))
    check("имя: оператору — только латиница, цифры, «_» не в конце (В4)", ck(_NR(oper=True), "GM_Bob") is None
          and ck(_NR(oper=True), "GM Bob").startswith("имя оператора") and ck(_NR(oper=True), "GMBob_").startswith("имя оператора")
          and ck(_NR(oper=True), "O'Neil").startswith("имя оператора"))
    check("имя: не-оператору «_» нельзя (правило 4)", (ck(_NR(), "GM_Bob") or "").endswith("(правило 4)"))
    check("имя: занято удалённым — отказ", (ck(_NR(taken=[{"Userindex": 5, "Charidx": 2, "Charname": "Bob", "deleted": 1}]), "Bob") or "")
          .startswith("имя занято удалённым"))
    check("имя: смена регистра своего имени — можно", ck(_NR(taken=[{"Userindex": 9, "Charidx": 1, "Charname": "bob", "deleted": 0}]),
                                                       "Bob", b"bob") is None)
    check("имя: пустое и с пробелами по краям — отказ (М5)", raises(lambda: _rn.plan(_NR(), {"uid": 9, "idx": 1, "name": None}), ops.OpRefused)
          and raises(lambda: _rn.plan(_NR(), {"uid": 9, "idx": 1, "name": " Bob"}), ops.OpRefused))
    # уровень: правило повышения как у сервера (research_level_job.md) — на подставных таблицах
    from domains import progress as _pg, srvtables as _sv
    _keep = (_sv.class_stat, _sv.exp_table, _sv.max_level, _sv.stat_points_top)
    _sv.class_stat = lambda: {(1, 60): [10, 11, 12, 13, 14, 15], (1, 61): [20, 21, 22, 23, 24, 25], (1, 100): [9] * 6}
    _sv.exp_table = lambda: {60: 1000, 61: 2000, 62: 3000, 100: 9000, 101: 9999}
    _sv.max_level = lambda: 100
    _sv.stat_points_top = lambda: 100

    class _LR:
        def __init__(self, job, exp=500):
            self.r = {"Charname": "t", "Class": 1, "Job": job, "Lvl": 59, "Expe": exp, "SkillPoint": 4, **{k: 1 for k in _pg.COLS[3:]}}

        def rows(self, sql, params=()):
            return [self.r]
    try:
        _u, _i, b, ch, sg, tx, wn = _pg.plan(_LR(3), {"uid": 9, "idx": 1, "level": 61}, role="owner")
        check("уровень: 59→61 — Lvl, опыт = начало уровня, +2 очка за уровень, база и P2 = ClassStat",
              ch["Lvl"] == 61 and ch["Expe"] == 2000 and ch["SkillPoint"] == 8 and ch["Strength"] == 20 and ch["FortuneP2"] == 25)
        _u, _i, b, ch, sg, tx, wn = _pg.plan(_LR(0), {"uid": 9, "idx": 1, "level": 60}, role="owner")
        check("уровень: без профессии очки навыков не растут", "SkillPoint" not in ch)
        _u, _i, b, ch, sg, tx, wn = _pg.plan(_LR(3, exp=1500), {"uid": 9, "idx": 1, "level": 60}, role="owner")
        check("уровень: опыт уже в пределах нового уровня — остаётся", "Expe" not in ch)
        check("уровень: понижение и выше потолка — отказ", raises(lambda: _pg.plan(_LR(3), {"uid": 9, "idx": 1, "level": 50}, role="owner"), ops.OpRefused)
              and raises(lambda: _pg.plan(_LR(3), {"uid": 9, "idx": 1, "level": 101}, role="owner"), ops.OpRefused))
        check("уровень: HP/MP, атака и *P не пишутся", not ({"Hp", "Mp", "MaxHp", "MaxMp", "StrengthP"} & set(_pg.COLS)))
        _sv.stat_points_top = lambda: 59                             # P29 StatPoints = 0: очки только до 59-го (перепроверка 11 М2)
        _u, _i, b, ch, sg, tx, wn = _pg.plan(_LR(3), {"uid": 9, "idx": 1, "level": 61}, role="owner")
        check("уровень: StatPoints 0 — очков за 60+ нет", "SkillPoint" not in ch)
        _sv.stat_points_top = lambda: 100
        _r99 = _LR(3)
        _r99.r["Lvl"] = 99
        _u, _i, b, ch, sg, tx, wn = _pg.plan(_r99, {"uid": 9, "idx": 1, "level": 100}, role="owner")
        check("уровень: 99 → 100 (потолок) — +2 очка, база 100-го", ch["Lvl"] == 100 and ch["SkillPoint"] == 6 and ch["Strength"] == 9)
        check("уровень: дробный уровень — отказ, а не 60 (М6)", raises(lambda: _pg.plan(_LR(3), {"uid": 9, "idx": 1, "level": 60.5},
                                                                                    role="owner"), ops.OpRefused))
    finally:
        _sv.class_stat, _sv.exp_table, _sv.max_level, _sv.stat_points_top = _keep
    from core import hostshell as _hs
    check("файлы сервера: patches.ini в UTF-16 читается (перепроверка 11 В1)",
          _hs.decode_text(b"\xff\xfe" + "[P29_LevelCap]\r\nEnabled=1".encode("utf-16-le")).startswith("[P29_LevelCap]")
          and _hs.decode_text(b"\xef\xbb\xbf[A]") == "[A]" and _hs.decode_text("Привет".encode("cp1251")) == "Привет")
    from domains import jobchange as _jc
    nb = {"JobCount": 0, "Job": 0, "Subjob": 0}
    check("профессия: новичку — 9 ступеней и 6 подклассов", len(_jc.targets(nb)) == 15)
    m2 = {"JobCount": 2, "Job": 24, "Subjob": 0}
    check("профессия: маг 2 → только маг 3 и подклассы 26/28", _jc.targets(m2) == [{"job": 25}, {"job": 25, "subjob": 26},
                                                                                  {"job": 25, "subjob": 28}])
    check("профессия: ступени маг 2 → подкласс 28 = маг 3, затем подкласс", _jc._steps(m2, {"job": 25, "subjob": 28})
          == (3, [(25, 0, 3), (25, 28, 4)]))
    check("профессия: понижение и чужая ветка — отказ", raises(lambda: _jc._steps(m2, {"job": 23}), ops.OpRefused)
          and raises(lambda: _jc._steps(m2, {"job": 3}), ops.OpRefused))
    check("профессия: с подклассом дальше некуда", _jc.targets({"JobCount": 4, "Job": 3, "Subjob": 4}) == [])
    # план на подставных данных (перепроверка 12 М10): новичок 10-го уровня → боец 1
    from domains import srvtables as _sv2
    _k2 = (_sv2.change_job_rows, _sv2.class_stat, _sv2.patches_ini, _sv2.skill_info)
    zero = {k: 1 for k in _jc.ZERO}
    _sv2.change_job_rows = lambda: {1: [501, 502], 3: [601]}
    _sv2.class_stat = lambda: {(1, 10): [5, 6, 7, 8, 9, 10]}
    _sv2.patches_ini = lambda: {"General": {"masterenable": "1"}, "P87_Job4StartSkills": {"enabled": "1"},
                                "P89_Job4GateBranch": {"enabled": "1", "mode": "1", "skipownedrow": "1"}}
    _sv2.skill_info = lambda s: {500: {"tree": 1, "need": 0, "req": [(-1, 0)] * 3, "zero": zero},
                                 501: {"tree": 1, "need": 0, "req": [(-1, 0)] * 3, "zero": zero},
                                 502: {"tree": 1, "need": 5, "req": [(-1, 0)] * 3, "zero": zero}}.get(s)

    class _JR:
        def rows(self, sql, params=()):
            if "FROM dbo.Charinfo" in sql:
                return [{"Charname": "t", "Lvl": 10, "Class": 0, "JobCount": 0, "Job": 0, "Subjob": 0, "SkillPoint": 0,
                         **{k: 1 for k in _jc.STATS}, **{k + "P2": 1 for k in _jc.STATS}}]
            return []
    try:
        pl, sg, tx, nt = _jc.plan(_JR(), {"uid": 9, "idx": 1, "target": {"job": 1}}, role="owner")
        check("профессия: новичок 10 → боец 1 — очки 2·10−8, класс, база ClassStat, навык без требований (502 — нет: нужно 5 очков)",
              pl["changed"]["SkillPoint"] == 12 and pl["changed"]["Class"] == 1 and pl["changed"]["Strength"] == 5
              and [s for s, _ in pl["skills"]] == [501] and pl["changed"]["JobCount"] == 1)
        check("профессия: несогласованные данные — отказ (М2)", raises(lambda: _jc.plan(type("R", (), {"rows": lambda self, q, p=(): [
            {"Charname": "t", "Lvl": 10, "Class": 2, "JobCount": 1, "Job": 1, "Subjob": 0, "SkillPoint": 0,
             **{k: 1 for k in _jc.STATS}, **{k + "P2": 1 for k in _jc.STATS}}] if "Charinfo" in q else []})(),
            {"uid": 9, "idx": 1, "target": {"job": 2}}, role="owner"), ops.OpRefused))
        # перепроверка 12 В1: взятый квест смены профессии (research_jobchange_quests.md)
        check("профессия: следующие ступени — новичок / боец 1 / боец 3 / с подклассом",
              _jc.next_steps(0, 0) == {("job", 1), ("job", 12), ("job", 23)} and _jc.next_steps(1, 0) == {("job", 2)}
              and _jc.next_steps(3, 0) == {("sub", 4), ("sub", 6)} and _jc.next_steps(3, 4) == set())

        class _JE(_JR):
            def __init__(self, eps):
                self.eps = eps

            def rows(self, sql, params=()):
                return [{"Episodeidx": e} for e in self.eps] if "CharEpisode" in sql else _JR.rows(self, sql, params)
        tg = {"uid": 9, "idx": 1, "target": {"job": 1}}
        check("профессия: взят квест «→ боец 1» (21) или «→ лучник 1» (22) — после смены в боец 1 отказ",
              raises(lambda: _jc.plan(_JE([21]), tg, role="owner"), ops.OpRefused)
              and raises(lambda: _jc.plan(_JE([7, 22]), tg, role="owner"), ops.OpRefused))
        # перепроверка 13 М5: многоступенчатая смена и 4-я ступень (по next_steps итогового состояния)
        check("профессия: новичок → боец 3 при взятом 21 — отказ (промежуточная ступень)",
              raises(lambda: _jc.plan(_JE([21]), {"uid": 9, "idx": 1, "target": {"job": 3}}, role="owner"), ops.OpRefused))
        check("профессия: итог Job 3 — эпизод 176 (→ подкласс 4) допустим, 301 (→ Job 3) нет; итог с подклассом — 176 нет",
              ("sub", 4) in _jc.next_steps(3, 0) and ("job", 3) not in _jc.next_steps(3, 0)
              and _jc.JOB_EPISODES[176] not in _jc.next_steps(3, 4))
        _p, _s, _t2, nt2 = _jc.plan(_JE([7, 55]), tg, role="owner")
        check("профессия: взят квест «→ боец 2» (55) — смена в боец 1 разрешена с пометкой; чужой эпизод 7 не мешает",
              any("эпизод 55" in n for n in nt2) and not any("эпизод 7" in n for n in nt2))
        try:
            _jc.plan(_JE([176]), tg, role="owner")
            msg = ""
        except ops.OpRefused as ex:
            msg = str(ex)
        i18n.set_lang("en")
        try:
            en = i18n.tr(msg)
        finally:
            i18n.set_lang("ru")
        check("профессия: отказ по квесту переводится (подкласс → subclass)", "subclass 4" in en and "episode 176" in en)
    finally:
        _sv2.change_job_rows, _sv2.class_stat, _sv2.patches_ini, _sv2.skill_info = _k2
    # пароль игровой учётки (domains/password.py, P52)
    from domains import password as _pw
    import hashlib as _hl
    check("пароль: ведущие пробелы снимаются, MD5 hex как у клиента",
          _pw.md5hex("  abc123") == _hl.md5(b"abc123").hexdigest() and _pw.md5hex("abc 1 ") == _hl.md5(b"abc 1 ").hexdigest())
    check("пароль: хвостовые пробелы остаются, табуляция и DEL — отказ (перепроверка 14)",
          _pw.md5hex("abc123  ") == _hl.md5(b"abc123  ").hexdigest()
          and raises(lambda: _pw.md5hex("abc\t123"), ops.OpRefused) and raises(lambda: _pw.md5hex("abc\x7f123"), ops.OpRefused))
    check("пароль: отпечаток смены пароля не зависит от счётчика неудач",
          _pw._sig({"us_pwset": None, "has_pw": 1, "us_pwfail": 3, "us_pwfail_at": datetime.datetime(2026, 11, 17)}, False)
          == _pw._sig({"us_pwset": None, "has_pw": 1, "us_pwfail": 4, "us_pwfail_at": None}, False))
    check("пароль: пустой / кириллица / 51 знак / не строка — отказ",
          all(raises(lambda v=v: _pw.md5hex(v), ops.OpRefused) for v in ("", "   ", "пароль12", "a" * 51, None, 123456))
          and _pw.md5hex("a" * 50) == _hl.md5(b"a" * 50).hexdigest() and _pw.md5hex("~!@#$%^&*") is not None)
    _salt = bytes(range(16))
    check("пароль: хеш = SHA-256(соль + md5hex в нижнем регистре), как FN_AC_PwHash",
          _pw.pw_hash(_salt, "ABCDEF" + "0" * 26) == _hl.sha256(_salt + ("abcdef" + "0" * 26).encode()).digest())
    _n = datetime.datetime(2026, 11, 17, 12, 0)
    check("пароль: замок — ≥ 10 неудач и последняя моложе 15 мин",
          _pw.lock_state({"us_pwfail": 10, "us_pwfail_at": _n - datetime.timedelta(minutes=5)}, _n)[0]
          and not _pw.lock_state({"us_pwfail": 10, "us_pwfail_at": _n - datetime.timedelta(minutes=16)}, _n)[0]
          and not _pw.lock_state({"us_pwfail": 9, "us_pwfail_at": _n}, _n)[0] and not _pw.lock_state({"us_pwfail": 0}, _n)[0])
    from domains import accountnew as _an
    check("учётка: логин — RTRIM, ≤ 32, только [A-Za-z0-9_.@-]",
          _an.login_of({"login": "Ab_1.x@y-z  "}) == "Ab_1.x@y-z" and _an.login_of({"login": "a" * 32}) == "a" * 32
          and all(raises(lambda v=v: _an.login_of({"login": v}), ops.OpRefused)
                  for v in ("", "   ", "a" * 33, "имя", "a b", " ab", "a'b", None, "a;b", "abc\n", "abc\r", "abc\t")))
    check("учётка: в цель журнала — только проверенный логин",
          _an.AccountCreate().target({"login": "Secret pass!"}) == "account:new"
          and _an.AccountCreate().target({"login": "abc  "}) == "account:new:abc")

    class _AE:
        def __init__(self, row):
            self.row = row

        def rows(self, sql, params=()):
            return [self.row] if self.row else []
    check("учётка: занятый логин — отказ, свободный — план",
          raises(lambda: _an.AccountCreate()._plan(_AE({"Userindex": 7, "Us_id": "AbC"}), {"login": "abc", "password": "x1y2z3w4"}),
                 ops.OpRefused)
          and _an.AccountCreate()._plan(_AE(None), {"login": "abc", "password": "x1y2z3w4"})[0] == "abc")
    # восстановление удалённого персонажа (domains/charrestore.py)
    from domains import charrestore as _cr

    class _RR:
        def __init__(self, live, restored=False, taken=False):
            self.live, self.restored, self.taken = live, restored, taken

        def rows(self, sql, params=()):
            if "FROM dbo.Del_Charinfo" in sql and "UNION" not in sql:
                return [{"Userindex": 7001, "Charidx": params[1], "Uid": "u", "Charname": "Oldie", "Lvl": 30, "Job": 2,
                         "ekey": params[2]}]
            if "adm.CharRestored" in sql:
                return [{"x": 1}] if self.restored else []
            if "UNION" in sql:
                return [{"Userindex": 7001, "Charidx": 10, "Charname": "Oldie", "deleted": 0}] if self.taken else []
            if "FROM dbo.Charinfo" in sql or "FROM dbo.CharPos" in sql:
                return [{"Charidx": c, "Charname": "x%d" % c} for c in self.live]
            return []
    _ek = {"uid": 7001, "idx": 12, "edate": "2026-10-19 16:36:50.027"}
    _p1 = _cr.plan(_RR([10, 11]), dict(_ek), role="owner")
    check("восстановление: 2 персонажа, свой слот 12 свободен — в 12, имя прежнее",
          _p1["slot"] == 12 and _p1["new"] is None and _p1["name"] == "Oldie")
    _p2 = _cr.plan(_RR([12]), dict(_ek), role="owner")
    check("восстановление: свой слот занят — первый свободный (10) с пометкой", _p2["slot"] == 10
          and any("слот 10" in w for w in _p2["warnings"]))
    check("восстановление: 3 персонажа / уже восстановлен / имя занято / слот занят / плохая дата — отказ",
          raises(lambda: _cr.plan(_RR([10, 11, 12]), dict(_ek), role="owner"), ops.OpRefused)
          and raises(lambda: _cr.plan(_RR([10], restored=True), dict(_ek), role="owner"), ops.OpRefused)
          and raises(lambda: _cr.plan(_RR([10], taken=True), dict(_ek), role="owner"), ops.OpRefused)
          and raises(lambda: _cr.plan(_RR([10, 11]), dict(_ek, slot=11), role="owner"), ops.OpRefused)
          and raises(lambda: _cr.plan(_RR([]), dict(_ek, edate="2026-10-19"), role="owner"), ops.OpRefused)
          and raises(lambda: _cr.plan(_RR([]), dict(_ek, uid=2), role="admin"), ops.OpRefused))
    # перенос персонажа (domains/charmove.py)
    from domains import charmove as _cm

    class _MV:
        def __init__(self, vp=None, pos=(23, 50, 60), state=0):
            self.vp, self.pos, self.state = vp, pos, state

        def rows(self, sql, params=()):
            if "FROM dbo.CharPos" in sql:
                return [{"Charname": "t", "UserNum": -1, "State": self.state, "Poridx": self.pos[0], "Cporidx": self.pos[0],
                         "Posx": self.pos[1], "Posy": self.pos[2], "lastdate": "2026-11-18 01:00:00.000"}]
            if "FROM dbo.VillagePos" in sql:
                return [{"Villageidx": self.vp[0], "Posx": self.vp[1], "Posy": self.vp[2]}] if self.vp else []
            return []
    _m = {"uid": 7001, "idx": 10}
    _om0 = _cm.srvtables.open_maps
    _cm.srvtables.open_maps = lambda: set(range(19))          # как dev: 19–22 Use 0, MapCount 21
    try:
        check("перенос: своя точка — карта 21/19 (сервер не поднимает) и 10 — отказ, 2 и 12 — можно; gm — отказ",
              raises(lambda: _cm.plan(_MV(), dict(_m, mode="custom", map=21, x=5, y=5), role="owner"), ops.OpRefused)
              and raises(lambda: _cm.plan(_MV(), dict(_m, mode="custom", map=10, x=5, y=5), role="owner"), ops.OpRefused)
              and _cm.plan(_MV(), dict(_m, mode="custom", map=2, x=5, y=5), role="admin")[3]["Poridx"] == 2
              and _cm.plan(_MV(), dict(_m, mode="custom", map=12, x=5, y=5), role="owner")[3]["Poridx"] == 12
              and raises(lambda: _cm.plan(_MV(), dict(_m, mode="custom", map=3, x=5, y=5), role="gm"), ops.OpRefused))
    except Exception:
        _cm.srvtables.open_maps = _om0
        raise
    _pv = _cm.plan(_MV(vp=(0, 0, 0)), dict(_m, mode="village"), role="gm")
    check("перенос: точка возрождения с клеткой 0,0 или не в городе — точка сервера 3, 125,390 с пометкой",
          _pv[3] == {"Poridx": 3, "Cporidx": 3, "Posx": 125, "Posy": 390} and any("негодна" in w for w in _pv[5])
          and _cm.plan(_MV(vp=(12, 50, 50)), dict(_m, mode="village"), role="gm")[3]["Poridx"] == 3)
    check("перенос: своя точка возрождения / её нет → 3, 125,390 / город 0 / как новый",
          _cm.plan(_MV(vp=(0, 393, 397)), dict(_m, mode="village"), role="owner")[3] == {"Poridx": 0, "Cporidx": 0, "Posx": 393, "Posy": 397}
          and _cm.plan(_MV(), dict(_m, mode="village"), role="owner")[3] == {"Poridx": 3, "Cporidx": 3, "Posx": 125, "Posy": 390}
          and _cm.plan(_MV(), dict(_m, mode="town", map=0), role="owner")[3]["Posx"] == 393
          and _cm.plan(_MV(), dict(_m, mode="new"), role="owner")[3] == {"Poridx": 3, "Cporidx": 3, "Posx": 0, "Posy": 0})
    check("перенос: подземелье/спецкарта/23/клетка 0 или 512/город 5/неизвестный режим/уже там/служебная — отказ",
          all(raises(lambda q=q: _cm.plan(_MV(), dict(_m, **q), role="owner"), ops.OpRefused) for q in (
              {"mode": "custom", "map": 10, "x": 5, "y": 5}, {"mode": "custom", "map": 19, "x": 5, "y": 5},
              {"mode": "custom", "map": 23, "x": 5, "y": 5}, {"mode": "custom", "map": 3, "x": 0, "y": 5},
              {"mode": "custom", "map": 3, "x": 5, "y": 512}, {"mode": "town", "map": 5}, {"mode": "fly"}))
          and raises(lambda: _cm.plan(_MV(pos=(3, 125, 390)), dict(_m, mode="town", map=3), role="owner"), ops.OpRefused)
          and raises(lambda: _cm.plan(_MV(), {"uid": 2, "idx": 10, "mode": "new"}, role="gm"), ops.OpRefused))
    check("перенос: State 3 — пометка, состояние не меняется",
          any("State 3" in w for w in _cm.plan(_MV(state=3), dict(_m, mode="new"), role="owner")[5])
          and "State" not in _cm.plan(_MV(state=3), dict(_m, mode="new"), role="owner")[3])
    _cm.srvtables.open_maps = _om0
    # выдать / изъять предмет (domains/itemgive.py)
    from domains import itemgive as _ig

    class _GW:
        """Подставной читатель для выдачи: сумки персонажа 7001/10, группы зарядов, вес."""
        def __init__(self, rows=(), ware=30, cur_w=100, max_w=5000):
            self.items, self.ware, self.cur_w, self.max_w = list(rows), ware, cur_w, max_w

        def rows(self, sql, params=()):
            if "SUM(CAST(Weight" in sql:
                return [{"s": self.cur_w}]
            if "SELECT MaxWeight" in sql:
                return [{"MaxWeight": self.max_w}]
            if "FROM Charinfo" in sql:
                return [{"Userindex": 7001, "Charidx": 10, "Charname": "t", "Lvl": 50, "Class": 1, "Job": 1, "Subjob": 0,
                         "JobCount": 1, "WareCount": self.ware}]
            if "OBJECT_ID('dbo.AsdaMigrationLog'" in sql:
                return [{"t": 1}]
            if "AsdaMigrationLog WHERE MigKey" in sql:
                return [{"n": 1}]
            if "AsdaChargeGroup WHERE Code" in sql:
                return [{"GroupKey": 12}] if params[0] in (1, 2) else []
            if "AsdaChargeGroup WHERE GroupKey" in sql:
                return [{"Code": 1, "GroupKey": 12}, {"Code": 2, "GroupKey": 12}]
            if "SELECT Posx, Code, Amount, Weight FROM Item" in sql:
                return [{"Posx": r[1], "Code": r[2], "Amount": r[3], "Weight": r[4]} for r in self.items if r[0] == params[2]]
            if "FROM Item" in sql:
                return [{"Uuid": "U%d" % i, "Code": r[2], "Plate": r[0], "Posx": r[1], "Amount": r[3], "Durability": 0, "Owner": 0,
                         "MaxupCnt": 0, "Cell1": 0, "Cell2": 0, "Cell3": 0, "Cell4": 0} for i, r in enumerate(self.items)]
            return []
    _p96_0, _cc0 = items.p96_enabled, _ig.srvtables.charge_cap
    items.p96_enabled = lambda: True
    _ig.srvtables.charge_cap = lambda: 30000
    try:
        _g = {"uid": 7001, "idx": 10}
        _pl = _ig.plan_give(_GW([(2, 3, 20571, 5, 115), (2, 9, 20571, 2, 46)]), dict(_g, code=20571, qty=4))
        check("выдача: стопка — в ПЕРВУЮ ячейку того же кода, вес = количество × вес",
              _pl["ops"] == [{"mode": "stack", "posx": 3, "amount": 4, "weight": 4 * 23, "expect": 5}])
        _pl = _ig.plan_give(_GW([(2, 0, 20551, 100, 0)]), dict(_g, code=20571, qty=4))
        check("выдача: стопки нет — новая ячейка (первая свободная)", _pl["ops"][0]["mode"] == "new" and _pl["ops"][0]["posx"] == 1)
        _st0 = _ig.srvtables.creation_choices(24893)["stones"][0][0]
        _pt = _ig._pair_lists(24893)[1][0]
        _pl = _ig.plan_give(_GW([(1, 0, 30000, 0, 852)]), dict(_g, code=24893, qty=2, opts={
            "pairs": {"1": {"type": _pt["type"], "value": _pt["values"][0]["value"]}}, "stone": _st0, "upcount": 0}))
        _w1 = _ig.item_spec(24893)["unit_weight"] + _ig.srvtables.cellob(_st0)["weight"]
        check("выдача: снаряжение × 2 — по ячейке на штуку, вес с самоцветом, опция 1 как выбрана",
              [e["posx"] for e in _pl["ops"]] == [1, 2] and all(e["weight"] == _w1 for e in _pl["ops"])
              and _pl["opts"]["Opidx1"] == _pt["type"] and _pl["opts"]["Cell1"] == _st0)
        check("выдача: самоцвет не из таблицы / ступень +5 / чужая опция / опции у расходника — отказ",
              raises(lambda: _ig.plan_give(_GW(), dict(_g, code=24893, opts={"stone": 7001})), ops.OpRefused)
              and raises(lambda: _ig.plan_give(_GW(), dict(_g, code=24893, opts={"stone": _st0, "upcount": 5})), ops.OpRefused)
              and raises(lambda: _ig.plan_give(_GW(), dict(_g, code=24893, opts={"stone": _st0, "pairs": {"1": {"type": 9999, "value": 1}}})), ops.OpRefused)
              and raises(lambda: _ig.plan_give(_GW(), dict(_g, code=20571, opts={"stone": 1})), ops.OpRefused))
        check("выдача: золото, книга заданий 2001, код вне таблиц, количество 0 — отказ",
              all(raises(lambda q=q: _ig.plan_give(_GW(), dict(_g, **q)), ops.OpRefused) for q in (
                  {"code": 20551}, {"code": 2001}, {"code": 99999999}, {"code": 20571, "qty": 0}, {"code": 20571, "qty": "x"})))
        _pl = _ig.plan_give(_GW([(1, 0, 1, 29995, 1)]), dict(_g, code=2, qty=2))
        check("выдача: заряды P100 — сверх потолка в новую ячейку, вторая штука туда же (ключ группы, вес не растёт)",
              _pl["ops"] == [{"mode": "new", "posx": 1, "amount": 20, "weight": 1, "expect": None}])
        _pl = _ig.plan_give(_GW([(1, 4, 1, 100, 1)]), dict(_g, code=2, qty=3))
        check("выдача: заряды P100 — в первую ячейку ключа (код ячейки не меняется)",
              _pl["ops"] == [{"mode": "charge", "posx": 4, "amount": 30, "weight": 0, "expect": 100}])
        check("выдача: перегруз и склад без ёмкости — отказ",
              raises(lambda: _ig.plan_give(_GW(cur_w=4990), dict(_g, code=20571, qty=1)), ops.OpRefused)
              and raises(lambda: _ig.plan_give(_GW(ware=0), dict(_g, code=20571, to="ware")), ops.OpRefused))
        _pl = _ig.plan_give(_GW([(5, 4, 1, 100, 1)]), dict(_g, code=2, qty=1, to="ware"))
        check("выдача: заряды на складе — только в ячейку ТОГО ЖЕ кода (перепроверка 18 М1)", _pl["ops"][0]["mode"] == "new")
        check("выдача: снаряжение сумки 1 по t24 == 3 (тип 11) — с выбором опций (перепроверка 18 М2)",
              _ig.item_spec(73353)["gear"] and "pairs" in _ig.describe(73353))
        _pl = _ig.plan_give(_GW(cur_w=4990), dict(_g, code=20571, qty=1, to="ware"))
        check("выдача: в склад — Plate 5, вес персонажа не считается", _pl["plate"] == 5 and _pl["cap"] == 30)
    finally:
        items.p96_enabled, _ig.srvtables.charge_cap = _p96_0, _cc0
    _items_v2_offline(_GW)
    _oc = _ig.srvtables._outcomes([30000, 0, 50000])
    check("создание: шансы броска 0…100000 (как sub_5329A0) складываются в 1, ноль весов — исход «нет»",
          abs(sum(_oc.values()) - 1) < 1e-9 and _oc.get(1) is None and abs(_oc[None] - 20000 / 100001) < 1e-9
          and _ig.srvtables._pick_index([0, 0, 5], 0) == 0 and _ig.srvtables._pick_index([0, 0, 5], 6) is None)
    _rl = [_ig.srvtables.roll_creation(24893) for _ in range(20)]
    check("создание: «Случайно» — самоцвет и ступень только из исходов таблицы, опции из группы",
          all(r["stone"] == _st0 and r["upcount"] == 0 for r in _rl)
          and all(r["pairs"][1] is None or r["pairs"][1]["type"] in [t["type"] for t in _ig._pair_lists(24893)[1]] for r in _rl))

    class _TW:
        def __init__(self, code=20571, amount=5, weight=115):
            self.r = {"Uuid": "AB", "Code": code, "Amount": amount, "Weight": weight, "fd": "2026-11-18 10:00:00.000"}

        def rows(self, sql, params=()):
            if "FROM Charinfo" in sql:
                return [{"Charname": "t"}]
            if "AsdaChargeGroup" in sql:
                return []
            return [self.r]
    _t = {"uid": 7001, "idx": 10, "plate": 2, "posx": 3, "uuid": "ab"}
    _ig.srvtables.charge_cap = lambda: None
    try:
        _tp = _ig.plan_take(_TW(), dict(_t, qty=2))
        check("изъятие: часть стопки — вес части = n × вес единицы", _tp["sig"]["take"] == 2 and _tp["sig"]["weight"] == 46)
        check("изъятие: всё — без части", _ig.plan_take(_TW(), _t)["sig"]["take"] is None
              and _ig.plan_take(_TW(), dict(_t, qty=5))["sig"]["take"] is None)
        check("изъятие: часть у нестопочного, больше чем есть, золото, надетое, другой Uuid — отказ",
              raises(lambda: _ig.plan_take(_TW(code=24893, amount=3), dict(_t, qty=1)), ops.OpRefused)
              and raises(lambda: _ig.plan_take(_TW(), dict(_t, qty=6)), ops.OpRefused)
              and raises(lambda: _ig.plan_take(_TW(code=20551), _t), ops.OpRefused)
              and raises(lambda: _ig.plan_take(_TW(), dict(_t, plate=3)), ops.OpRefused)
              and raises(lambda: _ig.plan_take(_TW(), dict(_t, uuid="CD")), ops.OpRefused))
    finally:
        _ig.srvtables.charge_cap = _cc0
    # опыт уровня, % (domains/progress.py char.exp_set)
    from domains import progress as _pg

    class _EW:
        def __init__(self, lvl=10, exp=1500):
            self.r = {"Charname": "t", "Lvl": lvl, "Expe": exp}

        def rows(self, sql, params=()):
            return [self.r]
    _et0, _ml0 = _pg.srvtables.exp_table, _pg.srvtables.max_level
    _pg.srvtables.exp_table = lambda: {10: 1000, 11: 2000, 12: 3500}
    _pg.srvtables.max_level = lambda: 100            # ★ ревизия 25 К-1: на потолке опыт не копится — проверяется отдельно ниже
    try:
        _e = _pg.plan_exp(_EW(), {"uid": 7001, "idx": 10, "percent": 99}, role="owner")
        check("опыт: 99 % уровня = E[L] + ⌊0,99 × (E[L+1] − E[L])⌋, уровень не меняется", _e[3] == {"Lvl": 10, "Expe": 1990})
        check("опыт: 0 % — начало уровня; 100, −1, 50.5, служебная учётка у не-владельца, тот же опыт — отказ",
              _pg.plan_exp(_EW(), {"uid": 7001, "idx": 10, "percent": "0"}, role="owner")[3]["Expe"] == 1000
              and all(raises(lambda q=q: _pg.plan_exp(_EW(), dict({"uid": 7001, "idx": 10}, percent=q), role="owner"), ops.OpRefused)
                      for q in (100, -1, "50.5", True))
              and raises(lambda: _pg.plan_exp(_EW(), {"uid": 2, "idx": 10, "percent": 1}, role="admin"), ops.OpRefused)
              and raises(lambda: _pg.plan_exp(_EW(exp=1500), {"uid": 7001, "idx": 10, "percent": 50}, role="owner"), ops.OpRefused)
              and raises(lambda: _pg.plan_exp(_EW(lvl=12), {"uid": 7001, "idx": 10, "percent": 5}, role="owner"), ops.OpRefused))
    finally:
        _pg.srvtables.exp_table, _pg.srvtables.max_level = _et0, _ml0
    # подарок / премиум-почта (domains/gifts.py)
    from domains import gifts as _gf

    class _PW:
        def rows(self, sql, params=()):
            if "WHERE Userindex = ? AND Charidx = ?" in sql:
                return [{"Userindex": params[0], "Charidx": params[1], "Charname": "t"}]
            if "WHERE Userindex = ? ORDER BY" in sql:
                return [{"Userindex": params[0], "Charidx": 10, "Charname": "a"}, {"Userindex": params[0], "Charidx": 11, "Charname": "b"}]
            return [{"Userindex": 7001, "Charidx": 10, "Charname": "a"}]
    _ds0 = _gf.describe
    _gf.describe = lambda kind, code: {"code": code, "delivery": code + (1 if kind == "gift" else 0), "price": 1, "notes": [],
                                       "buy_type": 0 if kind == "gift" else 1, "contents": [], "name": "x"}
    try:
        _pp = _gf.plan(_PW(), {"kind": "gift", "code": 100, "qty": 9, "uid": 7001, "idx": 10})
        check("подарок: штука = строка Amount 1, по 7 в заказе (как покупка), код выдачи и тип покупки шлюза",
              [len(o) for o in _pp["orders"]] == [7, 2] and all(r == [0, 101, 1] for o in _pp["orders"] for r in o)
              and json.loads(json.dumps(_pp["sig"])) == _pp["sig"])
        _pp = _gf.plan(_PW(), {"kind": "mail", "code": 20571, "qty": 9, "uid": 7001, "idx": 10})
        check("почта: строка Amount = копий (≤ 7), iType 1", _pp["orders"] == [[[1, 20571, 7]], [[1, 20571, 2]]])
        check("подарок: получатели — учётка (все персонажи), все игроки; служебная у не-владельца, 0 и 61 шт., мусор — отказ",
              len(_gf.plan(_PW(), {"kind": "gift", "code": 1, "to": "account", "uid": 7001})["targets"]) == 2
              and _gf.plan(_PW(), {"kind": "gift", "code": 1, "to": "all"})["mode"] == "all"
              and raises(lambda: _gf.plan(_PW(), {"kind": "gift", "code": 1, "uid": 2, "idx": 10}, role="admin"), ops.OpRefused)
              and all(raises(lambda q=q: _gf.plan(_PW(), dict({"kind": "gift", "code": 1, "uid": 7001, "idx": 10}, **q)), ops.OpRefused)
                      for q in ({"qty": 0}, {"qty": 61}, {"qty": "x"}, {"to": "planet"})))
    finally:
        _gf.describe = _ds0
    check("подарок: номер заказа — наименьший свободный у персонажа", _gf._free_orders({1, 2, 4}, 3) == [3, 5, 6])
    from core import audit as _ad
    _q0 = _ad.query
    _ad.query = lambda **k: [{"id": 12, "result": "ok", "undone_by": None,
                              "after_json": json.dumps({"sent": [{"uid": 7001, "idx": 10, "rows": [[1, 1, 5, 1]]}]})}]
    try:
        _snt = [{"uid": 7001, "idx": 10, "rows": [[1, 1, 5, 1]]}]
        check("подарок: откат, когда номер заказа заняла более поздняя отправка, — отказ (перепроверка 19 В2)",
              raises(lambda: _gf._reused_check({"id": 10}, _snt), ops.OpRefused)
              and _gf._reused_check({"id": 13}, _snt) is None
              and _gf._reused_check({"id": 10}, [{"uid": 7001, "idx": 11, "rows": [[1, 1, 5, 1]]}]) is None)
    finally:
        _ad.query = _q0
    _bn = _gf.banned()
    check("подарок: реестр банов читается (учёток %s)" % (len(_bn) if _bn is not None else "нет"), _bn is not None and len(_bn) > 0)
    # звания, слава, очки чести (domains/titles.py)
    from domains import titles as _tt

    def _fr(i, en=1, tgt=10, pts=5, nxt=(-1, -1), pre=(-1,) * 5, k43=1, k44=1, p4=0):
        return [i, en, 0, tgt, p4] + list(pre) + list(nxt) + [0, 0, 0, 0, 0] * 6 + [pts, k43, k44, 0]
    _fi = [_fr(i) for i in range(70)]
    _fi[3] = _fr(3, nxt=(10, -1))
    _fi[4] = _fr(4, nxt=(10, -1))
    _fi[10] = _fr(10, tgt=0, pts=7, pre=(3, 4, -1, -1, -1))
    _fi[11] = _fr(11, en=0)
    _fi[63] = _fr(63, pts=2)

    class _TWR:
        def __init__(self, bank, prog=None, fame=None, cls=1):
            self.bank, self.prog, self.fame, self.cls = bank, prog, fame or {}, cls

        def rows(self, sql, params=()):
            if "FROM dbo.Charinfo" in sql:
                return [{"Charname": "t", "Class": self.cls}]
            if "FROM dbo.CharFameBank" in sql:
                return [dict(self.bank)] if self.bank else []
            if "FROM dbo.CharFameProgress" in sql:
                return [dict(self.prog)] if self.prog else []
            if "FROM dbo.CharFameHigh" in sql:
                return []
            if "COUNT(*)" in sql:
                return [{"n": len(self.fame)}]
            if "FROM dbo.CharFame " in sql or "FROM dbo.CharFame%s" in sql or "FROM dbo.CharFame WITH" in sql or sql.startswith("SELECT Condition1"):
                r = self.fame.get(params[2])
                return [dict(r)] if r else []
            return []
    _b = {"Fmpoint": 3, "Fmidx1": 2, "Fmidx2": -1, "Fame1": 0b100, "Fame2": 0, "Fame3": 0, "Fame4": 0}
    _fio, _nm0 = _tt.srvtables.fame_info, _tt.names
    _tt.srvtables.fame_info = lambda: _fi
    _tt.names = lambda: {66: ["", "", 2, 1, 0, 1, 0], 24: ["", "", 2, 0, 1, 1, 36]}
    try:
        _u, _i, _c, _t, _w = _tt.plan_grant(_TWR(_b), {"uid": 7001, "idx": 10, "title": 0}, role="owner")
        _cm = {x[0]: x for x in _c}
        check("звание: выдать — бит, слава + очки, строка CharFame с целью и опциями FameInfo, бит «найдено»",
              _cm["CharFameBank"][3]["Fame1"] == 0b101 and _cm["CharFameBank"][3]["Fmpoint"] == 8
              and _cm["CharFame"][2] is None and _cm["CharFame"][3]["Condition1"] == 10 and _cm["CharFame"][3]["Opidx1"] == 0
              and _cm["CharFameProgress"][3]["Fame1"] == 1)
        _b2 = dict(_b, Fame1=0b1000)
        _u, _i, _c, _t, _w = _tt.plan_grant(_TWR(_b2), {"uid": 7001, "idx": 10, "title": 4}, role="owner")
        _cm = {x[0]: x for x in _c}
        check("звание: набор — последняя предпосылка даёт и цель набора (бит, очки, без строки CharFame)",
              _cm["CharFameBank"][3]["Fame1"] == 0b1000 | 0b10000 | (1 << 10) and _cm["CharFameBank"][3]["Fmpoint"] == 3 + 5 + 7)
        _u, _i, _c, _t, _w = _tt.plan_grant(_TWR(_b), {"uid": 7001, "idx": 10, "title": 63}, role="owner")
        check("звание: бит 63 — знаковый bigint", {x[0]: x for x in _c}["CharFameBank"][3]["Fame1"] == _tt._s64(0b100 | (1 << 63)))
        check("звание: 65–69, выключенное, чужой класс, уже есть, служебная у не-владельца — отказ",
              all(raises(lambda q=q: _tt.plan_grant(_TWR(_b, cls=1), dict({"uid": 7001, "idx": 10}, title=q), role="owner"), ops.OpRefused)
                  for q in (65, 69, 11, 24, 2, 999))
              and raises(lambda: _tt.plan_grant(_TWR(_b), {"uid": 2, "idx": 10, "title": 0}, role="admin"), ops.OpRefused))
        _u, _i, _c, _t, _w = _tt.plan_revoke(_TWR(_b, fame={2: dict(_tt._empty("CharFame"), Condition1=10, Opidx1=0)}),
                                             {"uid": 7001, "idx": 10, "title": 2}, role="owner")
        _cm = {x[0]: x for x in _c}
        check("звание: снять — бит снят, слава не ниже 0, CharFame 0/0 и опции −1, «найдено», надетое снято",
              _cm["CharFameBank"][3]["Fame1"] == 0 and _cm["CharFameBank"][3]["Fmpoint"] == 0 and _cm["CharFameBank"][3]["Fmidx1"] == -1
              and _cm["CharFame"][3]["Condition1"] == 0 and _cm["CharFame"][3]["Opidx1"] == -1 and _cm["CharFameProgress"][3]["Fame1"] == 0b100)
        check("звание: снять рейтинговое / отсутствующее — отказ",
              raises(lambda: _tt.plan_revoke(_TWR(dict(_b, Fame2=2)), {"uid": 7001, "idx": 10, "title": 65}, role="owner"), ops.OpRefused)
              and raises(lambda: _tt.plan_revoke(_TWR(_b), {"uid": 7001, "idx": 10, "title": 5}, role="owner"), ops.OpRefused))
        check("слава: пересчёт = Σ очков полученных званий (как сервер при входе)",
              _tt.plan_recalc(_TWR(dict(_b, Fmpoint=222)), {"uid": 7001, "idx": 10}, role="owner")[2][0][3]["Fmpoint"] == 5
              and raises(lambda: _tt.plan_recalc(_TWR(dict(_b, Fmpoint=5)), {"uid": 7001, "idx": 10}, role="owner"), ops.OpRefused))
        _sg = _tt._sig(_tt.plan_grant(_TWR(_b), {"uid": 7001, "idx": 10, "title": 0}, role="owner")[2])
        def _browser(v):                                     # как JSON.parse браузера: целые > 2^53 округляются (double)
            if isinstance(v, bool):
                return v
            if isinstance(v, int):
                return int(float(v))
            if isinstance(v, list):
                return [_browser(x) for x in v]
            if isinstance(v, dict):
                return {k: _browser(x) for k, x in v.items()}
            return v
        _big = _tt._sig([("CharFameBank", [1, 10], dict(_b, Fame1=703687458555841), dict(_b, Fame1=-9223372036854775807))])
        check("звание: отпечаток переживает браузер (маски > 2^53 — строкой; перепроверка 20 В1)",
              _browser(json.loads(json.dumps(_sg))) == _sg and _browser(json.loads(json.dumps(_big))) == _big)
    finally:
        _tt.srvtables.fame_info, _tt.names = _fio, _nm0
    # навыки и питомцы (domains/skills.py, pets.py)
    from domains import skills as _sk, pets as _pt

    def _si(i, tree=1, need=0, mask=1 << 2, mx=5):
        return {"tree": tree, "need": need, "name": "s%d" % i, "kind": 0, "max": mx, "passive": 0, "mask": mask, "pmask": 0,
                "next": [], "req": [(-1, 0)] * 3, "zero": {k: 7 for k in _sk.ZERO}}
    _sinfo = {600: _si(600), 601: _si(601, need=3), 602: _si(602, tree=2), 603: _si(603, mask=1 << 13), 608: _si(608)}

    class _SR:
        def __init__(self, learned, ch=None):
            self.l, self.ch = learned, ch or {"Charname": "t", "Class": 1, "Job": 2, "Subjob": 0, "JobCount": 1, "SkillPoint": 4}

        def rows(self, sql, params=()):
            if "FROM dbo.Charinfo" in sql:
                return [dict(self.ch)]
            if "FROM dbo.Fighter" in sql:
                return [dict({c: 1 for c in _sk.COLS}, Skillidx=600)]
            if "FROM dbo.CharSkill" in sql:
                return [dict({c: 0 for c in _sk.COLS}, Skillidx=s, Lvl=l) for s, l in self.l.items()]
            return []
    _o1, _o2 = _sk.srvtables.skill_info, _sk.srvtables.skill_count
    _sk.srvtables.skill_info = lambda i: _sinfo.get(int(i))
    _sk.srvtables.skill_count = lambda: 1120
    try:
        _g = {"uid": 7001, "idx": 10}
        _c = _sk.plan_grant(_SR({}), dict(_g, skill=600), role="owner")[2]
        check("навык: выдать — уровень 0, поля нулевого уровня SkillInfo", _c == [("CharSkill", [7001, 10, 600], None,
              dict({"Lvl": 0}, **{k: 7 for k in _sk.ZERO}))])
        check("навык: чужая профессия, заглушка, вне таблицы, уже изучен, служебная у не-владельца — отказ",
              all(raises(lambda q=q: _sk.plan_grant(_SR({601: 0}), dict(_g, skill=q), role="owner"), ops.OpRefused) for q in (603, 608, 499, 601))
              and raises(lambda: _sk.plan_grant(_SR({}), {"uid": 2, "idx": 10, "skill": 600}, role="admin"), ops.OpRefused))
        _c = _sk.plan_remove(_SR({601: 3}), dict(_g, skill=601), role="owner")[2]
        check("навык: снять — строка удалена, очки += уровень", _c[0][3] is None and _c[1][3] == {"SkillPoint": 7})
        _c = _sk.plan_reset_tree(_SR({600: 2, 601: 3, 602: 1}), dict(_g, tree=1), role="owner")[2]
        _cm = {x[1][2] if x[0] == "CharSkill" else "SP": x for x in _c}
        check("навык: сброс дерева — +190≠0 удалён, +190=0 уровень 0, чужое дерево не тронуто, очки += 5",
              _cm[601][3] is None and _cm[600][3]["Lvl"] == 0 and 602 not in _cm and _cm["SP"][3] == {"SkillPoint": 9})
        _c = _sk.plan_reset_all(_SR({600: 2, 601: 3, 602: 1}), _g, role="owner")[2]
        _cm = {x[1][2] if x[0] == "CharSkill" else "SP": x for x in _c}
        check("навык: полный сброс (исправленный) — шаблон класса + навыки без требований по маске уровнем 0, прочие удалены, очки += Σ",
              _cm[600][3]["Lvl"] == 0 and _cm[601][3] is None and _cm[602][3] == dict({"Lvl": 0}, **{k: 7 for k in _sk.ZERO})
              and _cm["SP"][3] == {"SkillPoint": 10})
        check("навык: сброс у новичка (класс 0) — отказ; очки 32768 — отказ",
              raises(lambda: _sk.plan_reset_all(_SR({}, dict(_SR({}).ch, Class=0)), _g, role="owner"), ops.OpRefused)
              and raises(lambda: _sk.plan_points(_SR({}), dict(_g, value=32768), role="owner"), ops.OpRefused))
        # перепроверка 21 М8: ветки полного сброса — без профессии (JobCount 0), по подклассу, чужой навык
        _c = _sk.plan_reset_all(_SR({600: 2, 601: 3, 603: 1}, dict(_SR({}).ch, JobCount=0)), _g, role="owner")[2]
        _cm = {x[1][2] if x[0] == "CharSkill" else "SP": x for x in _c}
        check("навык: полный сброс без профессии (JobCount 0) — шаблона нет, +190=0 по маске уровнем 0, чужой (603) удалён",
              _cm[600][3] == dict({"Lvl": 0}, **{k: 7 for k in _sk.ZERO}) and _cm[601][3] is None and _cm[603][3] is None
              and _cm["SP"][3] == {"SkillPoint": 10})
        _c = _sk.plan_reset_all(_SR({603: 4}, dict(_SR({}).ch, Subjob=13, JobCount=4)), _g, role="owner")[2]
        _cm = {x[1][2] if x[0] == "CharSkill" else "SP": x for x in _c}
        check("навык: полный сброс — навык подкласса (Subjob 13) остаётся уровнем 0, шаблон добавлен",
              _cm[603][3]["Lvl"] == 0 and _cm[600][2] is None and _cm[600][3]["Lvl"] == 0 and _cm["SP"][3] == {"SkillPoint": 8})
    finally:
        _sk.srvtables.skill_info, _sk.srvtables.skill_count = _o1, _o2
    _nm1 = _sk.refdata.names
    from core import i18n as _i18
    _en0 = _i18.is_en
    try:
        _sk.refdata.names = lambda kind: {"640": ["нет", "нет"], "641": ["Удар", ""], "642": ["Удар", "Strike"]}
        _i18.is_en = lambda: True
        _en = [_sk.skill_name(i) for i in (640, 641, 642)]
        _i18.is_en = lambda: False
        _ru = [_sk.skill_name(i) for i in (640, 641, 642)]
        check("навык: имя — «нет» = без имени, в EN без русского (перепроверка 21 К3/К4)",
              _en == ["skill 640", "skill 641", "Strike"] and _ru == ["навык 640", "Удар", "Удар"])
    finally:
        _sk.refdata.names, _i18.is_en = _nm1, _en0

    class _PR:
        def __init__(self, row):
            self.row = row

        def rows(self, sql, params=()):
            if "LewdWordList" in sql:
                return [{"x": 1}] if "TOP 1" in sql and "bad" in str(params[0]).lower() else []
            return [dict(self.row, Charname="t")]
    _pr = {"Plate": 1, "Petindex": 1, "PetName": "Dog", "FullNess": 50, "PetLvl": 2, "PetMaxLvl": 4, "PetExp": 400, "NameFlag": 1, "Active": 0}
    _pe0 = _pt.srvtables.pet_level_exp
    _pt.srvtables.pet_level_exp = lambda b, l: {1: 0, 2: 333, 3: 733, 4: 1233}.get(int(l))
    try:
        _q = {"uid": 7001, "idx": 10, "pet": 5}
        check("питомец: кличка — NameFlag 0; кириллица, 15 знаков, пусто, запрещённое слово — отказ",
              _pt.plan_rename(_PR(_pr), dict(_q, name="Rex_1"), role="owner")[4]["NameFlag"] == 0
              and all(raises(lambda n=n: _pt.plan_rename(_PR(_pr), dict(_q, name=n), role="owner"), ops.OpRefused)
                      for n in ("Шарик", "A" * 15, "", "badword")))
        _n = _pt.plan_level(_PR(_pr), dict(_q, level=4), role="owner")[4]
        check("питомец: уровень — опыт начала уровня; выше потолка и 0 — отказ (решение владельца)",
              _n["PetLvl"] == 4 and _n["PetExp"] == 1233 and _n["PetMaxLvl"] == 4
              and raises(lambda: _pt.plan_level(_PR(_pr), dict(_q, level=5), role="owner"), ops.OpRefused)
              and raises(lambda: _pt.plan_level(_PR(_pr), dict(_q, level=0), role="owner"), ops.OpRefused))
        check("питомец: удалить — «стало» нет", _pt.plan_delete(_PR(_pr), _q, role="owner")[4] is None)
    finally:
        _pt.srvtables.pet_level_exp = _pe0

    class _PW:
        """Подставной писатель для отката удаления питомца: n — строк у персонажа, act — есть ли другой призванный."""
        def __init__(self, n, act):
            self.n, self.act, self.sql = n, act, []

        def rows(self, sql, params=()):
            self.sql.append((sql, list(params)))
            if "COUNT(*)" in sql:
                return [{"n": self.n}]
            if "Active = 1" in sql:
                return [{"x": 1}] if self.act else []
            if sql.startswith("INSERT"):
                return [{"PetUnique": 99}]
            return []

        def close(self):
            pass

        def commit(self):
            pass
    _gw0, _os0 = _pt.db.GameWriter, _pt.items.online_state
    _pt.items.online_state = lambda w, uid, lock=False: (True, "")
    try:
        _jr = {"after_json": json.dumps({"uid": 7001, "idx": 10, "pet": 5, "row": None, "before": dict(_pr, Active=1),
                                         "edate": "2026-10-01 12:00:00.000"})}
        _w = _PW(3, True)
        _pt.db.GameWriter = lambda name: _w
        _r = _pt.PetDelete().undo(None, _jr)
        _ins = [x for x in _w.sql if x[0].startswith("INSERT")]
        check("питомец: откат удаления — вставка с прежней датой Edate, при другом призванном Active 0 (перепроверка 21 К5, М8)",
              len(_ins) == 1 and "Edate" in _ins[0][0] and _ins[0][1][-1] == "2026-10-01 12:00:00.000"
              and _ins[0][1][2 + list(_pt.COLS).index("Active")] == 0 and _r["after"]["row"]["Active"] == 0)
        _w = _PW(_pt.MAX_PETS, False)
        _pt.db.GameWriter = lambda name: _w
        check("питомец: откат удаления при 30 питомцах — отказ", raises(lambda: _pt.PetDelete().undo(None, _jr), ops.OpRefused))
        _jr2 = {"after_json": json.dumps({"uid": 7001, "idx": 10, "pet": 5, "row": None, "before": _pr})}
        _w = _PW(1, False)
        _pt.db.GameWriter = lambda name: _w
        _pt.PetDelete().undo(None, _jr2)
        _ins = [x for x in _w.sql if x[0].startswith("INSERT")]
        check("питомец: откат удаления по старой записи журнала (без Edate) — без Edate", len(_ins) == 1 and "Edate" not in _ins[0][0])
    finally:
        _pt.db.GameWriter, _pt.items.online_state = _gw0, _os0

    class _TW:
        def __init__(self):
            self.ex = []

        def execute(self, sql, params=()):
            self.ex.append((sql, list(params)))
            return 1
    _tw = _TW()
    _hb = dict.fromkeys(_tt.TABLES["CharFameHigh"][1], 0)
    _tt._put(_tw, "CharFameHigh", [7001, 10], _hb, dict(_hb, BankHi1=1), "x", stamp="2026-11-01 10:00:00.000")
    _tt._put(_tw, "CharFameHigh", [7001, 10], _hb, dict(_hb, BankHi1=1), "x")
    check("звание: откат CharFameHigh возвращает прежний UpdateDate, запись — GETDATE() (перепроверка 20 К6)",
          "CONVERT(datetime, ?, 121)" in _tw.ex[0][0] and "2026-11-01 10:00:00.000" in _tw.ex[0][1] and "GETDATE()" in _tw.ex[1][0])
    # задания и эпизоды (domains/quests.py, questdata.py)
    from domains import quests as _qs, questdata as _qd
    _C = lambda **k: _qd._class_ok(dict({"job": 0, "job_case": 0}, **k), k.pop("J", 0) if False else k.get("_J", 0), k.get("_S", 0))
    def _cls(job, case, J, S):
        return _qd._class_ok({"job": job, "job_case": case}, J, S)
    check("задание: класс как CheckCondition (99, ветки 40/43, «не ниже», вариант 2)",
          _cls(99, 0, 0, 0) == 5 and _cls(99, 0, 1, 0) == 0 and _cls(40, 0, 12, 0) == 0 and _cls(40, 0, 2, 0) == 5
          and _cls(43, 1, 3, 6) == 0 and _cls(43, 1, 3, 5) == 0 and _cls(25, 0, 25, 0) == 0 and _cls(13, 1, 14, 0) == 0
          and _cls(13, 1, 12, 0) == 5 and _cls(43, 2, 3, 0) == 0 and _cls(40, 2, 1, 0) == 5 and _cls(24, 2, 23, 0) == 0
          and _cls(24, 2, 12, 0) == 5 and _cls(-1, 0, 1, 0) == 4)
    _rp = dict.fromkeys(_qd.REPAY_KEYS, -1)
    _rp.update(pen_flag=1, pen_base=5, exp=1000, gold=40, a_flag=1, b_flag=0, a_sp=0, b_sp=0, job=-1, item1=36753, item1n=2,
               a_charisma=0, a_book=-1, a_fame=-1, b_charisma=-1, b_book=-1, b_fame=-1)
    check("задание: опыт со штрафом за уровень (база 5: ур. 9 — ×1, 12 — ×0.9, 40 — ×0.5; без флага — ×1)",
          _qd.penalized_exp(_rp, 9) == 1000 and _qd.penalized_exp(_rp, 12) == 899 and _qd.penalized_exp(_rp, 40) == 500
          and _qd.penalized_exp(dict(_rp, pen_flag=0), 40) == 1000)
    _pt0 = _qd.reward_parts(_rp)
    check("задание: части награды — опыт, золото, предметы блока A; блок B без флага не идёт",
          _pt0["exp"] == 1000 and _pt0["gold"] == 40 and _pt0["items"] == [(36753, 2)] and not _pt0["unsupported"]
          and _qd.reward_parts(dict(_rp, b_flag=1, item4=5, item4n=1, b_fame=3))["unsupported"] == ["слава"])

    def _cd(key, **k):
        c = {"key": key, "stop": 0, "reward_flag": 0, "rewards": [0] * 5, "action": 0, "lvl_flag": 1, "lvl_min": 1, "lvl_max": 150,
             "cls_flag": 0, "job": 0, "job_case": 0, "qblock": 1, "A": 0xFFFFFFFF, "P": 0xFFFFFFFF, "J": 0xFFFFFFFF,
             "B": 0xFFFFFFFF, "J_step": -1, "items_flag": 0, "items_none": 0, "items_any": 0, "ids": [-1] * 5, "cnts": [0] * 5,
             "kind140": 0, "time142": 0}
        c.update(k)
        return c
    _conds = {0: _cd(0, lvl_flag=0, qblock=0), 10: _cd(10, A=50, lvl_min=10, reward_flag=1, book=2050),
              11: _cd(11, A=51, P=50, reward_flag=1, book=2051), 12: _cd(12, A=52, P=51, reward_flag=1, book=2052),
              20: _cd(20, action=2, reward_flag=1, rewards=[7, 8, 0, 0, 0]), 21: _cd(21, action=2, reward_flag=1, rewards=[9, 0, 0, 0, 0]),
              13: _cd(13, A=21, reward_flag=1, book=2021), 30: _cd(30, J=60, items_flag=1, ids=[555, -1, -1, -1, -1], cnts=[3, 0, 0, 0, 0])}
    _cells = ({50: [(1, 0, [10, 0, 0, 0, 0]), (9, 0, [0, 0, 0, 0, 0])], 51: [(1, 1, [11, 0, 0, 0, 0])], 52: [(1, 2, [12, 0, 0, 0, 0])], 21: [(2, 0, [13, 0, 0, 0, 0])]},
              {50: [(1, 0, 1, [20, 0, 0, 0, 0])], 51: [(1, 1, 1, [21, 0, 0, 0, 0])], 52: [(1, 2, 0, [21, 0, 0, 0, 0])], 21: [(2, 0, 1, [21, 0, 0, 0, 0])]})
    _sl = [None] * 12
    _sl[0] = {"Episodeidx": 60, "Stepidx": 0, "items": [(555, 2), (-1, 0), (-1, 0), (-1, 0), (-1, 0)]}
    check("задание: CheckCondition — предметы-цели слота (нужно 3, есть 2 → 8; есть 3 → 0)",
          _qd.check(_conds[30], {"Lvl": 10, "Job": 1, "Subjob": 0}, lambda q: False, _sl) == 8
          and _qd.check(_conds[30], {"Lvl": 10, "Job": 1, "Subjob": 0}, lambda q: False,
                        [dict(_sl[0], items=[(555, 3)] + [(-1, 0)] * 4)] + [None] * 11) == 0)

    class _QR:
        def __init__(self, lvl=20, job=1, sub=0, eps=(), mask=None, gold=100):
            self.ch = {"Charname": "t", "Class": 1, "JobCount": 1, "Job": job, "Subjob": sub, "Lvl": lvl, "Expe": 1000, "SkillPoint": 3}
            for c in _qs.progress.COLS:
                self.ch.setdefault(c, 1)
            self.eps, self.mask, self.gold = list(eps), mask, gold

        def rows(self, sql, params=()):
            if "FROM dbo.Charinfo" in sql:
                return [dict(self.ch)]
            if "FROM dbo.CharEpisode" in sql:
                return [dict(e) for e in self.eps]
            if "FROM dbo.CharQuest" in sql:
                return [dict(self.mask)] if self.mask else []
            if "CRT_LimitationQuest" in sql:
                return []
            if "FROM dbo.Item" in sql:
                return [{"Uuid": "U1", "Amount": self.gold}] if self.gold is not None else []
            return []
    _ep = lambda q, code, posx, step=0: dict({"Code": code, "Posx": posx, "State": 2, "Episodeidx": q, "Stepidx": step, "Etime": 0},
                                             **{"Eitem%d" % k: -1 for k in range(1, 6)}, **{"Amount%d" % k: 0 for k in range(1, 6)})
    _m50 = dict({"Quest%d" % k: 0 for k in range(1, 21)}, Quest1=1 << 50)
    _sv = (_qd.cells, _qd.cond, _qd.quest_book, _qd.repay, _qs.itemgive.plan_give, _qs.srvtables.max_level, _qs.srvtables.exp_table,
           _qs.srvtables.class_stat, _qs.srvtables.stat_points_top, _qs.refdata.quest)
    _reps = {7: dict(_rp, exp=300, pen_flag=0), 8: dict(_rp, exp=0, gold=0, item1=-1), 9: dict(_rp, exp=5000, gold=0, item1=-1)}
    _qd.cells = lambda: _cells
    _qd.cond = lambda k: _conds.get(k)
    _qd.quest_book = lambda: ({2050: {"idx": 50, "goals": [31094, 0, 0]}, 2051: {"idx": 51, "goals": [0, 0, 0]},
                               2052: {"idx": 52, "goals": [0, 0, 0]}, 2021: {"idx": 21, "goals": [0, 0, 0]}},
                              {50: 2050, 51: 2051, 52: 2052, 21: 2021})
    _qd.repay = lambda rid: _reps.get(int(rid))
    _qs.itemgive.plan_give = lambda w, p, lock=False: {"ops": []}
    _qs.srvtables.max_level = lambda: 100
    _qs.srvtables.exp_table = lambda: {20: 0, 21: 1500, 22: 4000, 100: 10 ** 9, 101: 2 * 10 ** 9}
    _qs.srvtables.class_stat = lambda: {(1, 21): (5, 5, 5, 5, 5, 5)}
    _qs.srvtables.stat_points_top = lambda: 100
    _qs.refdata.quest = lambda q: "q%d" % q
    try:
        _g = {"uid": 7001, "idx": 10}
        _c = _qs.plan_give(_QR(), dict(_g, quest=50), role="owner")[2]
        check("задание: выдать как NPC — первое свободное место, шаг 0, State 2, предмет-цель книги ×1",
              _c[0][0] == "CharEpisode" and _c[0][1] == [7001, 10, 2050, 0] and _c[0][3]["Stepidx"] == 0 and _c[0][3]["State"] == 2
              and _c[0][3]["Eitem1"] == 31094 and _c[0][3]["Amount1"] == 1 and _c[0][3]["Eitem2"] == -1)
        check("задание: выдать — уровень ниже, без предшественника, уже выполнено, эпизод смены не по ступени — отказ",
              raises(lambda: _qs.plan_give(_QR(lvl=5), dict(_g, quest=50), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_give(_QR(), dict(_g, quest=51), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_give(_QR(mask=_m50), dict(_g, quest=50), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_give(_QR(job=2), dict(_g, quest=21), role="owner"), ops.OpRefused)
              and _qs.plan_give(_QR(job=0), dict(_g, quest=21), role="owner")[2][0][3]["Episodeidx"] == 21)
        _c = _qs.plan_drop(_QR(eps=[_ep(50, 2050, 3)]), dict(_g, posx=3), role="owner")[2]
        check("задание: ячейка с ключами 0 (без книги) не выдаёт и не обходит условия (перепроверка 22 В1)",
              raises(lambda: _qs.plan_give(_QR(lvl=5), dict(_g, quest=50), role="owner"), ops.OpRefused)
              and _qd.predecessors(50) == [set()] and _qd.dependents(50) == {51})
        check("задание: завершить не взятое — проверка как у NPC (уровень ниже — отказ; перепроверка 22 М1)",
              raises(lambda: _qs.plan_complete(_QR(lvl=5), dict(_g, quest=50, reward=7), role="owner"), ops.OpRefused))
        check("задание: снять — строка удалена, «выполнено» не тронуто", len(_c) == 1 and _c[0][3] is None and _c[0][1][3] == 3)
        _c = _qs.plan_complete(_QR(eps=[_ep(50, 2050, 0, step=1)]), dict(_g, quest=50, reward=7), role="owner")
        _cm = {x[0]: x for x in _c[2]}
        check("задание: завершить с наградой 7 — слот удалён, бит 50, опыт +300 (без повышения), золото +40, снаряжение — одна штука",
              _cm["CharEpisode"][3] is None and (_cm["CharQuest"][3]["Quest1"] >> 50) & 1 and _cm["Charinfo"][3] == {"Expe": 1300}
              and _cm["Item"][3] == {"Amount": 140} and _c[3] == [[36753, 1]])   # не-стопка — одна штука (К3)
        _c = _qs.plan_complete(_QR(mask=_m50), dict(_g, quest=51, reward=9), role="owner")
        _cm = {x[0]: x for x in _c[2]}
        check("задание: завершить — опыт сверх уровня: +1 уровень (ClassStat, очки +2), остаток сохранён; «было» CharQuest — маска до правки",
              _cm["Charinfo"][3]["Lvl"] == 21 and _cm["Charinfo"][3]["Expe"] == 2500 and _cm["Charinfo"][3]["SkillPoint"] == 5
              and _cm["Charinfo"][3]["Strength"] == 5 and _cm["CharQuest"][2] == _m50)
        check("задание: завершить — неизвестный вариант, без предшественника, уже выполнено, эпизод смены не достигнут — отказ",
              raises(lambda: _qs.plan_complete(_QR(eps=[_ep(50, 2050, 0, step=1)]), dict(_g, quest=50, reward=99), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_complete(_QR(), dict(_g, quest=52), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_complete(_QR(mask=_m50), dict(_g, quest=50), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_complete(_QR(job=0), dict(_g, quest=21), role="owner"), ops.OpRefused)
              and _qs.plan_complete(_QR(job=1), dict(_g, quest=21), role="owner")[2][0][0] == "CharQuest")
        check("задание: снять «выполнено» — зависимое выполнено, эпизод смены, не выполнено — отказ; иначе бит снят",
              raises(lambda: _qs.plan_uncomplete(_QR(mask=dict(_m50, Quest1=(1 << 50) | (1 << 51))), dict(_g, quest=50), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_uncomplete(_QR(mask=dict(_m50, Quest1=1 << 21)), dict(_g, quest=21), role="owner"), ops.OpRefused)
              and raises(lambda: _qs.plan_uncomplete(_QR(), dict(_g, quest=50), role="owner"), ops.OpRefused)
              and _qs.plan_uncomplete(_QR(mask=_m50), dict(_g, quest=50), role="owner")[2][0][3]["Quest1"] == 0)
        _b = dict(_m50, Quest1=-(1 << 63))
        _sg = _qs._sig([("CharQuest", [1, 10], _b, _qs._set(_b, 5, True))], [])
        check("задание: отпечаток переживает браузер (маска со знаковым разрядом — строкой)", json.loads(json.dumps(_sg)) == _sg
              and isinstance(_sg[0][2]["Quest1"], str))
    finally:
        (_qd.cells, _qd.cond, _qd.quest_book, _qd.repay, _qs.itemgive.plan_give, _qs.srvtables.max_level, _qs.srvtables.exp_table,
         _qs.srvtables.class_stat, _qs.srvtables.stat_points_top, _qs.refdata.quest) = _sv
    from core import audit as _au
    check("пароль: в журнал не попадает", _au.scrub({"uid": 7, "password": "secret1"})["password"] == "***")
    from domains import online as _on

    class _FW:
        """Подставной писатель: Us_member и CharPos учётки 7."""
        def __init__(self, flag, usernum, rows):
            self.m, self.cp = {"Userindex": 7, "Us_id": "t", "Flag": flag, "UserNum": usernum, "Loginidx": 1}, rows

        def rows(self, sql, params=()):
            return [self.m] if "Us_member" in sql else self.cp
    _t = datetime.datetime
    gs0, lm0 = _t(2026, 11, 15, 18, 0), _t(2026, 11, 15, 18, 0)
    old = {"Charidx": 1, "Charname": "a", "UserNum": 3, "Partyidx": 5, "Captain": 1, "SoulState": 0, "State": 1,
           "LastDate": _t(2026, 11, 14, 10, 0)}
    new = dict(old, Charidx=2, Charname="b", LastDate=_t(2026, 11, 16, 10, 0))
    _m, fx, ac, kp, _sg = _on.plan(_FW(1, 3, [old]), 7, gs0, lm0, _t(2026, 11, 14, 9, 0))
    check("в игре: персонаж вошёл раньше старта GS и вход раньше LM → снимаются оба", len(fx) == 1 and ac is not None
          and fx[0]["after"]["UserNum"] == -1 and fx[0]["after"]["State"] == 0)
    _m, fx, ac, kp, _sg = _on.plan(_FW(1, 3, [old, new]), 7, gs0, lm0, _t(2026, 11, 14, 9, 0))
    check("в игре: персонаж вошёл после старта GS — не трогается, и признак учётки тоже", len(fx) == 1 and ac is None and len(kp) == 2)
    _m, fx, ac, kp, _sg = _on.plan(_FW(1, -1, []), 7, gs0, lm0, _t(2026, 11, 16, 9, 0))
    check("в игре: учётка вошла после старта LM (может быть на выборе персонажа) — не трогается", not fx and ac is None and kp)
    _m, fx, ac, kp, _sg = _on.plan(_FW(1, 3, [new]), 7, None, None, None)
    check("в игре: GameServer и LoginManager не запущены → снимается всё", len(fx) == 1 and ac is not None)
    _m, fx, ac, kp, _sg = _on.plan(_FW(0, -1, [dict(old, State=3, UserNum=2)]), 7, gs0, lm0, None)
    check("в игре: State 3 сохраняется при сбросе", fx and fx[0]["after"]["State"] == 3)
    # перепроверка 9 М7
    _m, fx, ac, kp, _sg = _on.plan(_FW(1, 3, [dict(old, LastDate=None)]), 7, gs0, lm0, _t(2026, 11, 14, 9, 0))
    check("в игре: LastDate неизвестна — не трогается", not fx and ac is None and kp)
    _m, fx, ac, kp, _sg = _on.plan(_FW(None, -1, []), 7, gs0, lm0, _t(2026, 11, 14, 9, 0))
    check("в игре: Flag NULL при работающем LoginManager — не трогается (М1)", ac is None and kp)
    _m, fx, ac, kp, _sg = _on.plan(_FW(1, 3, [old]), 7, gs0, lm0, _t(2026, 11, 14, 9, 0), portal_in=_t(2026, 11, 16, 9, 0))
    check("в игре: вход на карту после старта GS (окно внутри UPUserNumUp) — ничего не трогается (М2)", not fx and ac is None)
    _m, fx, ac, kp, s1 = _on.plan(_FW(1, 3, [old]), 7, gs0, lm0, _t(2026, 11, 14, 9, 0))
    _m, fx, ac, kp, s2 = _on.plan(_FW(1, 3, [old]), 7, _t(2026, 11, 13, 0, 0), lm0, _t(2026, 11, 14, 9, 0))
    check("в игре: решение и старты — в отпечатке (М3)", s1 != s2 and s1["fix"] == [1] and s2["fix"] == [])
    _f1 = _on.plan(_FW(1, 3, [old]), 7, gs0, lm0, _t(2026, 11, 14, 9, 0))
    check("в игре: для отката сохраняются LastDate персонажа и Loginidx/Portalidx учётки (В2)",
          _f1[1][0]["LastDate"] == "2026-11-14 10:00:00.000" and _f1[2]["Loginidx"] == 1 and "Portalidx" in _f1[2]
          and _on._ms(_t(2026, 11, 14, 10, 0, 0, 997000)) == "2026-11-14 10:00:00.997")
    from domains import srvtables as _st
    _r = {"steps": [3, 5, 6, 8, 10], "sure_steps": [10], "boost_max": 5, "max_normal": 15}
    check("заточка: достижимость суммы (+1: 3 да, 4 нет; +20: 0 нет)", _st.updamage_reachable(_r, 1, 3)
          and not _st.updamage_reachable(_r, 1, 4) and not _st.updamage_reachable(_r, 20, 0))
    check("свойства: чужой столбец в журнале — отказ", raises(lambda: itemedit._apply(w, 1, 10, "U", {"Code": 1}, {"Code": 2}),
                                                            ops.OpRefused))
    ch = lambda cls, job, sub, cnt: {"Class": cls, "Job": job, "Subjob": sub, "JobCount": cnt}
    r = lambda req, t=1: {"job_req": req, "type": t}
    check("класс (sub_4CDDA0): без требования — можно", items.job_ok(r(0), ch(0, 0, 0, 0)))
    check("класс: 2 — класс 1 и профессия ≥ 2", items.job_ok(r(2), ch(1, 2, 0, 1)) and not items.job_ok(r(2), ch(1, 1, 0, 1))
          and not items.job_ok(r(2), ch(2, 13, 0, 1)))
    check("класс: 13 — класс 2 и профессия ≥ 13", items.job_ok(r(13), ch(2, 13, 0, 1)) and not items.job_ok(r(13), ch(2, 12, 0, 1)))
    check("класс: 4 — подкласс 4…5, 5 — только 5", items.job_ok(r(4), ch(1, 1, 5, 1)) and not items.job_ok(r(4), ch(1, 1, 6, 1))
          and items.job_ok(r(5), ch(1, 1, 5, 1)) and not items.job_ok(r(5), ch(1, 1, 4, 1)))
    check("класс: оружие 41 — смен профессии ≥ 2", items.job_ok(r(41, 9), ch(1, 1, 0, 2)) and not items.job_ok(r(41, 9), ch(1, 1, 0, 1))
          and not items.job_ok(r(4, 9), ch(1, 1, 4, 5)))
    sc = audit.scrub({"login": "x", "password": "p", "params": {"new_password": "n", "totp_code": "1"}, "code": 20551})
    check("журнал без секретов", sc["password"] == "***" and sc["params"]["new_password"] == "***"
          and sc["params"]["totp_code"] == "***" and sc["code"] == 20551)

    class _C:                                                       # настройки как у службы на сервере
        bind_host, bind_port = "0.0.0.0", 17890
        public_hosts = ",".join([config.SERVER_VPN_IP, config.SERVER_LAN_IP, config.SERVER_WAN_IP, "@@ASTORY_SERVER_HOSTNAME@@", "localhost", "127.0.0.1"])
    good = ["@@ASTORY_SERVER_VPN_IP@@:17890", "@@ASTORY_SERVER_LAN_IP@@:17890", "@@ASTORY_SERVER_WAN_IP@@:17890", "@@ASTORY_SERVER_HOSTNAME@@:17890", "localhost:17890"]
    bad = ["evil.example:17890", "@@ASTORY_SERVER_VPN_IP@@:80", "@@ASTORY_SERVER_VPN_IP@@", "0.0.0.0:17890", "", "@@ASTORY_SERVER_LAN_IP@@:17890x",
           "@@ASTORY_SERVER_VPN_IP@@.evil.example:17890"]
    check("Host: все адреса сервера пускает", all(server.host_allowed(x, _C) for x in good),
          [x for x in good if not server.host_allowed(x, _C)])
    check("Host: чужое имя/порт — нет", not any(server.host_allowed(x, _C) for x in bad),
          [x for x in bad if server.host_allowed(x, _C)])
    _social_offline()
    _charrest_offline()


class _RestStore:
    """Подставная Joy1 для domains/charrest.py и charcopy.py: строки таблиц в памяти, разбор ровно тех SELECT / INSERT / UPDATE /
    DELETE, которые пишут планы и _put (подставные читатели — как у _social_offline)."""
    NOW = "2026-11-18 12:00"

    def __init__(self):
        self.t = {"Charinfo": [], "CharAppr": [], "CharPlusPackage": [], "CharCamp": [], "CRT_CharCraftInfo": [], "CRT_LimitationQuest": [],
                  "CharFish": [], "CharFishBookInfo": [], "CharTutorial": [], "CharPos": [], "Item": []}
        self.sql = []

    @staticmethod
    def _where(where, params):
        conds, q = [], list(params)
        for cl in where.split(" AND "):
            cl = cl.strip()
            m = re.match(r"CONVERT\(varchar\(16\), (\w+), 120\) = \?$", cl) or re.match(r"(\w+) = \?$", cl)
            if m:
                conds.append((m.group(1), q.pop(0)))
                continue
            m = re.match(r"(\w+) = (-?\d+)$", cl)
            if m:
                conds.append((m.group(1), int(m.group(2))))
                continue
            m = re.match(r"(\w+) <> (-?\d+)$", cl)
            if m:
                conds.append((m.group(1), ("<>", int(m.group(2)))))
                continue
            raise AssertionError("подставная база: условие %r" % cl)
        return conds, q

    @staticmethod
    def _ok(r, conds):
        for c, v in conds:
            if isinstance(v, tuple):
                if r.get(c) == v[1]:
                    return False
            elif r.get(c) != v:
                return False
        return True

    def rows(self, sql, params=()):
        self.sql.append(sql)
        s = sql.replace(" WITH (UPDLOCK, HOLDLOCK)", "")
        if "GETDATE()" in s:
            return [{"n": self.NOW}]
        m = re.match(r"SELECT (.+?) FROM (?:dbo\.|AsdaStoryOp\.dbo\.)(\w+) WHERE (.+?)(?: ORDER BY .+)?$", s)
        if not m:
            raise AssertionError("подставная база: запрос %r" % sql)
        cols, table, where = m.group(1), m.group(2), m.group(3)
        if table == "Us_member":
            return [{"Userindex": params[0]}] if params[0] in (1, 2, 3, 7) else []
        conds, _rest = self._where(where, params)
        hit = [dict(r) for r in self.t[table] if self._ok(r, conds)]
        if cols.startswith("COUNT(*)"):
            return [{"n": len(hit)}]
        if cols.startswith("TOP 1 "):
            hit = hit[:1]
        return hit

    def execute(self, sql, params=()):
        self.sql.append(sql)
        p = list(params)
        m = re.match(r"INSERT INTO dbo\.(\w+) \((.+?)\) VALUES", sql)
        if m:
            self.t[m.group(1)].append(dict(zip([c.strip() for c in m.group(2).split(",")], p)))
            return 1
        m = re.match(r"DELETE FROM dbo\.(\w+) WHERE (.+)$", sql)
        if m:
            conds, _r = self._where(m.group(2), p)
            hit = [r for r in self.t[m.group(1)] if self._ok(r, conds)]
            for r in hit:
                self.t[m.group(1)].remove(r)
            return len(hit)
        m = re.match(r"UPDATE dbo\.(\w+) SET (.+?) WHERE (.+)$", sql)
        if m:
            sets = re.findall(r"(\w+) = (?:\?|CONVERT\(smalldatetime, \?, 120\))", m.group(2))
            vals, rest = p[:len(sets)], p[len(sets):]
            conds, _r = self._where(m.group(3), rest)
            hit = [r for r in self.t[m.group(1)] if self._ok(r, conds)]
            for r in hit:
                r.update(dict(zip(sets, vals)))
            return len(hit)
        raise AssertionError("подставная база: запись %r" % sql)


def _charrest_offline():
    """А1 «внешность, баффы, лагерь, ремесло, рыбалка, обучение, копия» (domains/charrest.py, charcopy.py, core/sched.py): планы на
    подставной базе, запись _put и откат «стало → было» (строки как были), отказы, отпечаток через JSON браузера, права, EN."""
    import copy as _copy
    import datetime as _dtm
    from core import i18n, sched
    from domains import charcopy as _cc, charrest as _cr, rename as _rn
    S = _RestStore()
    S.t["Charinfo"] += [{"Userindex": 9001, "Charidx": 10, "Charname": "Tst", "Gender": 1, "JobCount": 2, "Lvl": 50},
                        {"Userindex": 9001, "Charidx": 11, "Charname": "Tst2", "Gender": 2, "JobCount": 1, "Lvl": 9},
                        {"Userindex": 7, "Charidx": 10, "Charname": "Svc", "Gender": 1, "JobCount": 1, "Lvl": 1}]
    S.t["CharAppr"] += [{"Userindex": 9001, "Charidx": 10, "HairStyle": 0, "HairColor": 0, "FaceType": 1},
                        {"Userindex": 9001, "Charidx": 11, "HairStyle": 4, "HairColor": 1, "FaceType": 3}]
    S.t["CharPlusPackage"] += [{"Userindex": 9001, "Charidx": 10, "iType": 1, "StartTime": "2026-11-10 10:00", "BuffPeriod": 43200, "EndTime": "2026-12-10 10:00"}]
    S.t["CharCamp"] += [{"Userindex": 9001, "Charidx": 10, "Campidx": 1, "CampPoint": 300, "CampGrade": 2, "CampFlag": 0, "CampPenaltyTime": 123456}]
    S.t["CRT_CharCraftInfo"] += [{"Userindex": 9001, "Charidx": 10, "iLevel": 2, "iExp": 50}]
    S.t["CRT_LimitationQuest"] += [{"Userindex": 9001, "Charidx": 10, "Quest_Index": 20040, "Quest_Type": 1, "Quest_Count": 4, "Quest_Flag": 3},
                                   {"Userindex": 9001, "Charidx": 10, "Quest_Index": 20042, "Quest_Type": 1, "Quest_Count": 0, "Quest_Flag": 1},
                                   {"Userindex": 9001, "Charidx": 10, "Quest_Index": 20500, "Quest_Type": 2, "Quest_Count": 2, "Quest_Flag": 3}]
    book = {"Userindex": 9001, "Charidx": 10, "BookCode": 5, "Complete": 0, "BookType": 0}
    book.update({"FishItemCode%d" % i: (69577 + i if i < 2 else -1) for i in range(30)})
    book.update({"FishCount%d" % i: (3 if i < 2 else 0) for i in range(30)})
    S.t["CharFishBookInfo"].append(book)
    S.t["CharTutorial"] += [{"Userindex": 9001, "Charidx": 10, "Tutorial1": 2612 - (1 << 63), "Tutorial2": 0, "Tutorial3": 0, "Tutorial4": -(1 << 62)}]
    keep = {"hair": _cr.hair_rows, "plus": _cr.plus_types, "craft": _cr.craft_levels, "tut": _cr.tutorial_exp, "name": _rn._check_name}
    _cr.hair_rows = lambda: [(0, 1, 0, 1, 19, 0, 0), (1, 1, 0, 1, 19, 4, 1), (2, 1, 0, 0, 1, 5, 0), (3, 2, 0, 1, 19, 4, 1), (4, 1, 0, 1, 29, 37, 2)]
    _cr.plus_types = lambda: {0: [1, 0], 1: [43200, 10000], 2: [10080, 10000], 5: [4320, 10000], 6: [0, 1]}
    _cr.craft_levels = lambda: [(1, 40, 40), (2, 112, 72), (3, 270, 158), (4, 680, 410), (5, 1992, 1312), (6, 6977, 4985), (7, 6977, 0)]
    _cr.tutorial_exp = lambda: [0, 0, 20, 0, 40, 59, 0, 0, 70, 103, 59, 103]
    _rn._check_name = lambda w, uid, idx, new, cur, own_deleted=None: "имя занято: Svc (учётка 7, слот 10)" if new == "Svc" else None
    try:
        snap0 = _copy.deepcopy(S.t)
        ok_plans = []

        def plan(fn, p, role="owner"):
            return fn(S, dict(p), role=role)

        def run(fn, p, role="owner"):
            """План → запись (как apply) → снимок → откат (как undo) — строки как были; → (план, строки после записи)."""
            uids, changes, text, warn = plan(fn, p, role)
            sig = _cr._sig(changes)
            check("charrest: отпечаток %s переживает JSON браузера" % fn.__name__, json.loads(json.dumps(sig)) == sig and _cr._sig(plan(fn, p, role)[1]) == sig)
            ch = _cr._strip(changes)
            for t, k, b, a in ch:
                _cr._put(S, t, k, b, a, "stale")
            after = _copy.deepcopy(S.t)
            ch2 = json.loads(json.dumps([[t, k, b, a] for t, k, b, a in ch]))           # журнал → откат
            for t, k, b, af in reversed(ch2):
                _cr._put(S, t, k, af, b, "stale")
            check("charrest: %s — после отката строки как были" % fn.__name__, S.t == snap0, text)
            ok_plans.append(fn.__name__)
            return (uids, changes, text, warn), after

        def refused(fn, p, role="owner", part=""):
            try:
                plan(fn, p, role)
            except ops.OpRefused as ex:
                return part in str(ex)
            return False

        P = {"uid": 9001, "idx": 10}
        # внешность
        (_u, ch, _t, w), aft = run(_cr.plan_appearance, dict(P, hair=4, color=1, face=10))
        check("внешность: пара пола и лицо 10 (муж.)", next(r for r in aft["CharAppr"] if r["Charidx"] == 10) == {"Userindex": 9001, "Charidx": 10, "HairStyle": 4,
              "HairColor": 1, "FaceType": 10} and any("смены лица" in x for x in w))
        check("внешность: отказы — чужой пол, не в продаже, лицо 10 у жен., без изменений, служебная не владельцем",
              refused(_cr.plan_appearance, dict(P, hair=4, color=2, face=1), part="для пола 1 нет")
              and refused(_cr.plan_appearance, dict(P, hair=5, color=0, face=1), part="не продаётся")
              and refused(_cr.plan_appearance, {"uid": 9001, "idx": 11, "hair": 4, "color": 1, "face": 10}, part="не из лиц пола 2")
              and refused(_cr.plan_appearance, dict(P, hair=0, color=0, face=1), part="не меняется")
              and refused(_cr.plan_appearance, {"uid": 7, "idx": 10, "hair": 0, "color": 0, "face": 0}, role="admin", part="только владелец")
              and refused(_cr.plan_appearance, dict(P, hair="x", color=0, face=0), part="целое число"))
        check("внешность: прежнее значение допустимо (лицо 9 у жен. остаётся)", plan(_cr.plan_appearance, {"uid": 9001, "idx": 11, "hair": 4, "color": 1, "face": 9})[1])
        # баффы
        (_u, ch, _t, w), aft = run(_cr.plan_plus_set, dict(P, type=2))
        r = aft["CharPlusPackage"][0]
        check("бафф: выдать тип 2 — срок таблицы с «сейчас», одна строка", len(aft["CharPlusPackage"]) == 1 and r["iType"] == 2 and r["BuffPeriod"] == 10080
              and r["StartTime"] == S.NOW and r["EndTime"] == "2026-11-25 12:00" and any("заменяется" in x for x in w))
        sig = _cr._sig(ch)
        check("бафф: в отпечатке выдачи нет времени (его ставит запись)", "StartTime" not in sig[0][3] and "EndTime" not in sig[0][3] and "_set" not in sig[0][3])
        (_u, ch, _t, w), aft = run(_cr.plan_plus_extend, dict(P, minutes=90))
        check("бафф: продлить на 90 мин", aft["CharPlusPackage"][0]["EndTime"] == "2026-12-10 11:30" and aft["CharPlusPackage"][0]["BuffPeriod"] == 43290)
        (_u, ch, _t, w), aft = run(_cr.plan_plus_remove, P)
        check("бафф: снять — строки нет", not aft["CharPlusPackage"])
        check("бафф: отказы — тип вне таблицы, тип без срока, продлить 0, нет бафа",
              refused(_cr.plan_plus_set, dict(P, type=3), part="нет в PlusPackageTable") and refused(_cr.plan_plus_set, dict(P, type=6), part="нет срока")
              and refused(_cr.plan_plus_extend, dict(P, minutes=0), part="от 1 до") and refused(_cr.plan_plus_remove, {"uid": 9001, "idx": 11}, part="нет бафа"))
        S.t["CharPlusPackage"].append({"Userindex": 9001, "Charidx": 11, "iType": 1, "StartTime": "2026-10-01 10:00", "BuffPeriod": 60, "EndTime": "2026-10-01 11:00"})
        snap0 = _copy.deepcopy(S.t)
        check("бафф: истёкший не продлевается", refused(_cr.plan_plus_extend, {"uid": 9001, "idx": 11, "minutes": 5}, part="истёк"))
        (_u, ch, _t, w), aft = run(_cr.plan_plus_set, {"uid": 9001, "idx": 11, "type": 5})
        check("бафф: выдать поверх истёкшего — без предупреждения о замене", not any("заменяется" in x for x in w))
        # лагерь
        (_u, ch, _t, w), aft = run(_cr.plan_penalty, P)
        check("лагерь: штраф → 0", aft["CharCamp"][0]["CampPenaltyTime"] == 0)
        (_u, ch, _t, w), aft = run(_cr.plan_army, dict(P, army=2))
        c10 = next(r for r in aft["CharCamp"] if r["Charidx"] == 10)
        c11 = next(r for r in aft["CharCamp"] if r["Charidx"] == 11)
        check("лагерь: армия всей учётке (UPDATE + INSERT 0/0/0/0 недостающему)", c10["Campidx"] == 2 and c10["CampPoint"] == 300 and c11 == {
              "Userindex": 9001, "Charidx": 11, "Campidx": 2, "CampPoint": 0, "CampGrade": 0, "CampFlag": 0, "CampPenaltyTime": 0})
        (_u, ch, _t, w), aft = run(_cr.plan_army, dict(P, army=-1))
        check("лагерь: снять армию — без вставки", len(aft["CharCamp"]) == 1 and aft["CharCamp"][0]["Campidx"] == -1)
        S.t["Charinfo"][0]["JobCount"] = 1
        check("лагерь: отказы — армия 3, уже та же, нет второй профессии", refused(_cr.plan_army, dict(P, army=3), part="−1 (снять)")
              and refused(_cr.plan_army, dict(P, army=0), part="второй профессии"))
        S.t["Charinfo"][0]["JobCount"] = 2
        # ремесло
        (_u, ch, _t, w), aft = run(_cr.plan_craft_level, dict(P, level=3))
        check("ремесло: уровень 3 — опыт начала уровня 112", aft["CRT_CharCraftInfo"][0]["iLevel"] == 3 and aft["CRT_CharCraftInfo"][0]["iExp"] == 112)
        (_u, ch, _t, w), aft = run(_cr.plan_craft_level, dict(P, level=7, exp=6977))
        check("ремесло: уровень 7 — опыт ровно порог, предупреждение", aft["CRT_CharCraftInfo"][0]["iExp"] == 6977 and w)
        check("ремесло: границы опыта (1: 0…39, 6: 1992…6976, 7: 6977)", _cr.craft_bounds(1, _cr.craft_levels()) == (0, 39)
              and _cr.craft_bounds(6, _cr.craft_levels()) == (1992, 6976) and _cr.craft_bounds(7, _cr.craft_levels()) == (6977, 6977))
        check("ремесло: отказы — уровень 8 вне таблицы, опыт вне уровня, нет строки", refused(_cr.plan_craft_level, dict(P, level=8), part="от 1 до 7")
              and refused(_cr.plan_craft_level, dict(P, level=2, exp=39), part="от 40 до 111")
              and refused(_cr.plan_craft_level, {"uid": 9001, "idx": 11, "level": 2}, part="строки ремесла"))
        (_u, ch, _t, w), aft = run(_cr.plan_craft_daily, P)
        q = {r["Quest_Index"]: r for r in aft["CRT_LimitationQuest"]}
        check("ремесло: суточный сброс — тип 1: флаг 3 → 0, счётчик → 0; флаг 1 и тип 2 не трогаются", q[20040]["Quest_Flag"] == 0 and q[20040]["Quest_Count"] == 0
              and q[20042]["Quest_Flag"] == 1 and q[20500] == snap0["CRT_LimitationQuest"][2])
        # рыбалка
        (_u, ch, _t, w), aft = run(_cr.plan_fish_skill, dict(P, value=77))
        check("рыбалка: навык без строки — вставка", aft["CharFish"] == [{"Userindex": 9001, "Charidx": 10, "FishingSkill": 77}])
        check("рыбалка: 0 без строки — отказ", refused(_cr.plan_fish_skill, dict(P, value=0), part="уже 0"))
        (_u, ch, _t, w), aft = run(_cr.plan_fishbook_delete, dict(P, book=5))
        check("книга рыб: удалить (снимок всех столбцов для отката)", not aft["CharFishBookInfo"] and len(ch[0][2]) == 62)
        check("книга рыб: нет книги — отказ", refused(_cr.plan_fishbook_delete, dict(P, book=6), part="книги рыб 6"))
        # обучение
        (_u, ch, _t, w), aft = run(_cr.plan_tutorial, dict(P, steps=[0, 2, 4, 5, 9, 11]))
        t = aft["CharTutorial"][0]
        check("обучение: поставить 0, снять 2… нет — шаги 0…11, старшие биты и слова 2…4 не трогаются", (t["Tutorial1"] & 0xFFF) == 0b101000110101
              and (t["Tutorial1"] >> 12) == (snap0["CharTutorial"][0]["Tutorial1"] >> 12) and t["Tutorial4"] == -(1 << 62))
        (_u, ch, _t, w), aft = run(_cr.plan_tutorial, dict(P, steps=[4]))
        check("обучение: снятые шаги — предупреждение о повторном опыте", any("ещё раз" in x and "2 (+20)" in x for x in w))
        sig = _cr._sig(ch)
        check("обучение: bigint ≥ 2^53 в отпечатке строкой", any(isinstance(v, str) for v in sig[0][2].values()))
        (_u, ch, _t, w), aft = run(_cr.plan_tutorial, {"uid": 9001, "idx": 11, "steps": [1]})
        check("обучение: строки нет — вставка", any(r["Charidx"] == 11 and r["Tutorial1"] == 2 for r in aft["CharTutorial"]))
        check("обучение: отказы — шаг вне таблицы, не список, без изменений", refused(_cr.plan_tutorial, dict(P, steps=[12]), part="шага обучения 12")
              and refused(_cr.plan_tutorial, dict(P, steps="1"), part="список") and refused(_cr.plan_tutorial, {"uid": 9001, "idx": 11, "steps": []}, part="не меняются"))
        check("charrest: каждое действие проверено записью и откатом (%d)" % len(ok_plans), len(ok_plans) >= 15)
        # _put: «было» не совпало — отказ, ничего не записано
        b = dict(snap0["CharAppr"][0])
        try:
            _cr._put(S, "CharAppr", [9001, 10], dict(b, HairStyle=9), dict(b, HairStyle=1), "stale-test")
            st = False
        except ops.OpRefused as ex:
            st = str(ex) == "stale-test"
        check("charrest: _put при чужом «было» — отказ, строки как были", st and S.t == snap0)
        check("charrest: в журнале неожиданная таблица — отказ", raises(lambda: _cr._put(S, "CharAppr", [9001, 10], None, b, "x"), ops.OpRefused))
        # ★ ревизия 26
        S.t["CharPlusPackage"] = [r for r in S.t["CharPlusPackage"] if r["Charidx"] != 10] + [
                                   {"Userindex": 9001, "Charidx": 10, "iType": 1, "StartTime": "2026-11-10 10:00", "BuffPeriod": 60, "EndTime": "2026-12-10 10:00"},
                                   {"Userindex": 9001, "Charidx": 10, "iType": 2, "StartTime": "2026-11-10 10:00", "BuffPeriod": 60, "EndTime": "2026-12-10 10:00"}]
        snap0 = _copy.deepcopy(S.t)
        S.sql.clear()
        (_u, ch, _t, w), aft = run(_cr.plan_plus_set, dict(P, type=2))
        mine = [r for r in aft["CharPlusPackage"] if r["Charidx"] == 10]
        check("р26 М-1: выдача при двух строках — сначала удаление лишней, потом обновление; итог одна строка с новым типом (PK не нарушен)",
              ch[0][3] is None and ch[0][2]["iType"] == 2 and ch[-1][2]["iType"] == 1 and ch[-1][3]["iType"] == 2 and len(mine) == 1 and mine[0]["iType"] == 2)
        check("р26 М-2: чтение строк с ORDER BY ключа (у бафа — и iType)", any("FROM dbo.CharPlusPackage" in q and q.endswith("ORDER BY Userindex, Charidx, iType")
                                                                          for q in S.sql))
        S.t["CharPlusPackage"] = [r for r in S.t["CharPlusPackage"] if r["Charidx"] != 10]
        snap0 = _copy.deepcopy(S.t)
        check("р26 М-6: строгий разбор целого («--1», «1.5», «+3» — отказ, « 7 » — 7)", all(raises(lambda v=v: _cr._int(v, "x"), ops.OpRefused)
              for v in ("--1", "1.5", "+3", "", "1e3")) and _cr._int(" 7 ", "x") == 7 and _cr._int("-2", "x") == -2)
        t0 = _dtm.datetime(2026, 11, 18, 6, 10)
        rows = [{"id": 9, "result": "error", "message": "запись №8 НЕ зафиксирована в игровой базе: сбой", "at": t0},
                {"id": 8, "result": "ok", "message": "", "at": t0}, {"id": 5, "result": "ok", "message": "", "at": _dtm.datetime(2026, 11, 17, 6, 10)}]
        check("р26 М-3: «ok» без фиксации (следом error «запись №N НЕ зафиксирована») успехом не считается", sched.last_ok(rows) == _dtm.datetime(2026, 11, 17, 6, 10)
              and sched.last_ok(rows[1:]) == t0 and sched.last_ok([]) is None)
        sched._tried.clear()
        # ★ А6.3: в DAILY есть и econ.snapshot 00:05 — проверка поведения ведётся на одной задаче (рейтинг чести 06:10)
        _daily_saved = list(sched.DAILY)
        sched.DAILY[:] = [x for x in _daily_saved if x[0] == "camp.rank_rebuild"]
        sched._quiet.clear()
        calls = []

        def _down(name):
            raise RuntimeError("AsdaAdmin недоступна")
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            r1 = sched.run_once(_dtm.datetime(2026, 11, 18, 6, 20), last=_down, runner=lambda n: calls.append(n) or {"message": "x"})
            r2 = sched.run_once(_dtm.datetime(2026, 11, 18, 6, 21), last=_down, runner=lambda n: calls.append(n) or {"message": "x"})
        sched._tried.clear()
        r3 = sched.run_once(_dtm.datetime(2026, 11, 18, 6, 5), last=_down, runner=lambda n: calls.append(n) or {"message": "x"})
        with contextlib.redirect_stdout(buf):
            r4 = sched.run_once(_dtm.datetime(2026, 11, 18, 6, 20), last=lambda n: None, runner=lambda n: calls.append(n) or {"message": "x"})
        sched._tried.clear()
        check("р26 М-4: журнал недоступен — одна строка без трассировки, повтор не раньше часа, до 06:10 журнал не спрашивается",
              r1 == [("camp.rank_rebuild", "журнал недоступен")] and r2 == [] and r3 == [] and buf.getvalue().count("журнал недоступен") == 1
              and "Traceback" not in buf.getvalue() and r4 == [("camp.rank_rebuild", "x")] and calls == ["camp.rank_rebuild"])
        sched.DAILY[:] = _daily_saved
        from api import server as _srv
        check("р26 М-5: ошибки таблиц стойки (errors) переводятся сервером", "errors" in _srv.TR_KEYS)
        lo = {t for t, _w in _cc.LEFTOVER}
        check("р26 С-1: предупреждение об остатках слота — все таблицы UPDeleteChar, которые копия не пишет", {"AttendanceCount", "AttendanceDetail",
              "CharinPos", "CharIntroduce", "FamePointRank", "SoulJewel", "SellitemAlarm", "CharFriend", "ClanMember", "ItemPostBox", "Exitem"} <= lo)
        sq8 = open(os.path.join(ROOT, "sql", "adminc_08_charcopy.sql"), encoding="utf-8").read()
        cd = sq8.split("CREATE PROCEDURE adm.CharCopyDelete", 1)[1].split("\nGO", 1)[0]
        cc = sq8.split("CREATE PROCEDURE adm.CharCopy ", 1)[1].split("\nGO", 1)[0]
        check("р26 С-1: удаление копии стирает и посещаемость, CharinPos, «о себе», рейтинг славы; связи (в т.ч. камни душ, оповещения) — отказ с перечнем",
              all("DELETE FROM dbo.%s WHERE" % t in cd for t in ("AttendanceCount", "AttendanceDetail", "CharinPos", "Charintroduce", "FamePointRank"))
              and all("FROM dbo.%s WHERE" % t in cd for t in ("SoulJewel", "SellitemAlarm", "CharFriend", "ClanMember", "Exitem", "ItemPostBox"))
              and cd.count("SET @busy = CONCAT(@busy") == 6)
        i_snap, i_del = cc.find("INSERT INTO adm.CharCopyReplaced_CharRefine"), cc.find("DELETE FROM dbo.CharRefine")
        check("р26 С-2: остатки CharRefine/CharFameHigh — снимок с номером копии ДО замены, удаление копии их возвращает",
              0 <= i_snap < i_del and cc.find("SET @id = SCOPE_IDENTITY()") < i_snap and "INSERT INTO adm.CharCopyReplaced_CharFameHigh" in cc
              and "FROM adm.CharCopyReplaced_CharRefine WHERE CopyId = @CopyId" in cd and "FROM adm.CharCopyReplaced_CharFameHigh WHERE CopyId = @CopyId" in cd
              and cd.find("DELETE FROM dbo.CharRefine") < cd.find("INSERT INTO dbo.CharRefine"))
        check("р26 М-7: у источника нет строки лагеря, у цели армия есть — строка (армия, 0, 0, 0, 0)",
              "IF @Camp <> -1 AND NOT EXISTS (SELECT 1 FROM dbo.CharCamp WHERE Userindex = @DstU AND Charidx = @DstC)" in cc)
        _rb99 = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")      # ★ 25.11 (К-3): в публичном репозитории файла нет — SKIP
        if _rb99 is None:
            P.skip("р26 М-8: откат adminc_99 говорит, как вернуть рейтинг чести", "нет sql/adminc_99_rollback.sql")
        else:
            check("р26 М-8: откат adminc_99 говорит, как вернуть рейтинг чести", "DELETE FROM Joy1.dbo.CampPointRank" in _rb99)
        g4 = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read()
        check("р26 С-2: снимки — asda_ops только читает", all("DENY INSERT, UPDATE, DELETE ON adm.CharCopyReplaced_%s TO [asda_ops]" % t in g4
                                                               for t in ("CharRefine", "CharFameHigh")))
        # копия
        S.t["Charinfo"].append({"Userindex": 7, "Charidx": 11, "Charname": "Svc2", "Gender": 1, "JobCount": 1, "Lvl": 1})
        S.t["CharPos"] += [{"Userindex": 7, "Charidx": 10}, {"Userindex": 7, "Charidx": 11}]
        S.t["CharCamp"].append({"Userindex": 7, "Charidx": 10, "Campidx": 0, "CampPoint": 0, "CampGrade": 0, "CampFlag": 0, "CampPenaltyTime": 0})
        S.t["Item"] += [{"Userindex": 9001, "Charidx": 10}] * 3
        pl = _cc.plan(S, {"uid": 9001, "idx": 10, "to": 7, "name": "CopyA"}, role="owner")
        check("копия: план — свободный слот 12, имя, предметов 3, армия цели", pl["slot"] == 12 and pl["sig"] == {"to": 7, "slot": 12, "name": "CopyA", "live": [10, 11], "items": 3}
              and any("армия учётки 7 (0)" in x for x in pl["warnings"]) and json.loads(json.dumps(pl["sig"])) == pl["sig"])

        def cref(p, role="owner", part=""):
            try:
                _cc.plan(S, p, role=role)
            except ops.OpRefused as ex:
                return part in str(ex)
            return False
        check("копия: отказы — не владелец, цель > 5000, слот занят, без имени, имя занято, нет учётки",
              cref({"uid": 9001, "idx": 10, "to": 7, "name": "CopyA"}, role="admin", part="только владелец")
              and cref({"uid": 9001, "idx": 10, "to": 9001, "name": "CopyA"}, part="служебную учётку")
              and cref({"uid": 9001, "idx": 10, "to": 7, "slot": 11, "name": "CopyA"}, part="слот 11 занят")
              and cref({"uid": 9001, "idx": 10, "to": 7, "name": "  "}, part="новое имя")
              and cref({"uid": 9001, "idx": 10, "to": 7, "name": "Svc"}, part="имя занято")
              and cref({"uid": 9001, "idx": 10, "to": 4, "name": "CopyA"}, part="учётки 4 нет"))
        S.t["Charinfo"].append({"Userindex": 7, "Charidx": 12, "Charname": "Svc3", "Gender": 1, "JobCount": 1, "Lvl": 1})
        check("копия: у цели 3 персонажа — отказ", cref({"uid": 9001, "idx": 10, "to": 7, "name": "CopyA"}, part="уже 3 персонажа"))
        check("копия: только владелец (права)", auth.can("owner", "players.copy") and not auth.can("admin", "players.copy"))
        # SQL копии и рейтинга: состав и проверки
        sq = open(os.path.join(ROOT, "sql", "adminc_08_charcopy.sql"), encoding="utf-8").read()
        dele = sq.split("CREATE PROCEDURE adm.CharCopyDelete", 1)[1].split("GO", 1)[0]
        check("adminc_08: копия 33 таблиц + удаление тех же 33 и ещё 5 как UPDeleteChar (р26), новые Uuid и Uc, без JoyLog1",
              len(re.findall(r"^\tINSERT INTO dbo\.\w+ \(", sq.split("CREATE PROCEDURE adm.CharCopy ", 1)[1].split("GO", 1)[0], re.M)) == 33
              and len(re.findall(r"^\tDELETE FROM dbo\.\w+ WHERE", dele, re.M)) == 38 and "NEWID()" in sq and "JoyLog1" not in sq.split("USE [Joy1];", 1)[1]
              and "TRUNCATE" not in sq.split("CREATE PROCEDURE adm.CampPointRank", 1)[1])
        v = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
        g = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read()
        ex = set(re.findall(r"GRANT EXECUTE ON (adm\.\w+) TO", g)) - {"adm.ServiceAccountCreate"}
        # ★ 21.11 А5.3: adm.LoginMaintenanceSet выдаётся только при применённом SQL L09 (IF OBJECT_ID) — проверка adminc_11 условная (+1)
        cond = {"adm.LoginMaintenanceSet"}
        check("права: каждый EXECUTE adm.* проверяется и их ровно 9 (19.11: + adm.ItemRecover; 21.11 А5.4: + adm.LimitationReset) + условный "
              "adm.LoginMaintenanceSet (А5.3)",
              len(ex - cond) == 9 and cond <= ex
              and all(("'Joy1.%s','OBJECT','EXECUTE'), 1" % e in v) or ("'Joy1.%s','OBJECT','EXECUTE'), 0), 1" % e in v) for e in ex - cond)
              and "= 1), 9 + CASE WHEN OBJECT_ID(N'Joy1.adm.LoginMaintenanceSet'" in v
              and "ELSE HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenanceSet','OBJECT','EXECUTE') END, 1" in v and "adm.ItemRecover" in ex)
        # 19.11 «Учётки»: в AsdaStoryOp исполнять можно ровно adm.ServiceAccountCreate; EXECUTE запрещён на схему dbo, не на базу
        _op_part = g.split("USE [AsdaStoryOp];", 1)[1]
        check("права AsdaStoryOp: EXECUTE только adm.ServiceAccountCreate (adminc_09), запрет на схему dbo, проверка adminc_11",
              "GRANT EXECUTE ON adm.ServiceAccountCreate TO [asda_ops];" in _op_part and "DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];" in _op_part
              and "REVOKE EXECUTE, ALTER FROM [asda_ops];" in _op_part and not re.search(r"DENY (?:[A-Z ]+, )*ALTER(?:,| TO)", _op_part.split("GO", 1)[0])
              and "'AsdaStoryOp.adm.ServiceAccountCreate','OBJECT','EXECUTE'), 1" in v and "ops.Op executable objects" in v
              and "GRANT INSERT, DELETE ON dbo.CharGmInfo TO [asda_ops];" in g and "'ops.CharGmInfo INSERT'" in v
              and "'ops.Op.OPCharGMDelete EXEC'" in v)
        _s9 = open(os.path.join(ROOT, "sql", "adminc_09_accounts.sql"), encoding="utf-8").read()
        check("adminc_09: процедура служебной учётки — подписана сертификатом (ключ удалён), номер 1…5000, IDENTITY_INSERT включается и выключается, "
              "столбцы как у adm_NewAccount", "ADD SIGNATURE TO adm.ServiceAccountCreate" in _s9 and "REMOVE PRIVATE KEY" in _s9
              and "WITH EXECUTE AS OWNER" not in _s9 and "GRANT ALTER ON dbo.Us_member TO adm_SvcAccSign_u;" in _s9
              and "@Userindex > 5000" in _s9
              and _s9.count("SET IDENTITY_INSERT dbo.Us_member ON") == 1 and _s9.count("SET IDENTITY_INSERT dbo.Us_member OFF") == 1
              and "VALUES (@Userindex, @Us_id, 0, GETDATE(), 0, 0, 0, 0, 0, 3, -1, 0, @Salt, @Hash, GETDATE())" in _s9
              and "adminc_09_accounts.sql" in open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
              and (_rb99 is None or "adm.ServiceAccountCreate" in _rb99))
        # планировщик службы
        at = _dtm.time(6, 10)
        check("планировщик: раз в сутки после 06:10", sched.due(_dtm.datetime(2026, 11, 18, 6, 11), at, None)
              and not sched.due(_dtm.datetime(2026, 11, 18, 6, 9), at, None)
              and not sched.due(_dtm.datetime(2026, 11, 18, 23, 0), at, _dtm.datetime(2026, 11, 18, 6, 10, 30))
              and sched.due(_dtm.datetime(2026, 11, 19, 6, 10), at, _dtm.datetime(2026, 11, 18, 6, 10, 30)))
        # права и операции
        names = {"appearance.set": "players.appearance", "plus.remove": "players.plus", "plus.set": "players.plus", "plus.extend": "players.plus",
                 "camp.penalty_clear": "players.camp", "camp.set_army": "players.camp", "camp.rank_rebuild": "players.camp",
                 "craft.set_level": "players.craft", "craft.daily_reset": "players.craft", "fish.set_skill": "players.craft",
                 "fishbook.delete": "players.craft", "tutorial.set": "players.tutorial", "char.copy": "players.copy"}
        check("операции зарегистрированы со своими правами (owner+admin, копия — owner)", all(n in ops.REGISTRY and ops.REGISTRY[n].perm == pm
              for n, pm in names.items()) and all(auth.PERMS[pm] == ({"owner"} if pm == "players.copy" else {"owner", "admin"}) for pm in set(names.values()))
              and not ops.REGISTRY["camp.rank_rebuild"].reversible and ops.REGISTRY["char.copy"].reversible)
        i18n.set_lang("en")
        tr = [i18n.tr("армия учётки 2: Свет, Тьма → Хаос (персонажей 3)"), i18n.tr("отказ сервера: у копии появились связи (таблица CharFriend)"),
              i18n.tr("Персонаж: внешность: возвращено"), i18n.tr("внешность персонажа щит (1/10): причёска 1/2 → 3/0, лицо 1 → 2")]
        i18n.set_lang("ru")
        check("перевод: армия, отказ процедуры (вложенно), откат, имя персонажа без подстановок",
              tr == ["army of account 2: Light, Darkness → Chaos (characters 3)", "server refused: the copy has links now (table CharFriend)",
                     "Character: appearance: restored", "appearance of character щит (1/10): hairstyle 1/2 → 3/0, face 1 → 2"], tr)
    finally:
        _cr.hair_rows, _cr.plus_types, _cr.craft_levels, _cr.tutorial_exp, _rn._check_name = (keep["hair"], keep["plus"], keep["craft"], keep["tut"],
                                                                                              keep["name"])


def _social_offline():
    """А1 «соулмейт, друзья, клан» (domains/social.py, soulmate.py, friends.py, clan.py): планы на подставных строках, SQL записи,
    отпечаток через JSON браузера, тексты EN."""
    from domains import social as _so, soulmate as _sm, friends as _fr, clan as _cl
    import re as _re

    def _sm_row(s, u, o, st=1, lvl=1, exp=0, fs=0, rd="2026-10-01 00:00:00.000"):
        return {"Smidx": s, "Userindex": u, "Ouserindex": o, "info": 1, "State": st, "SmLvl": lvl, "SmExp": exp, "FriendShip": fs,
                "AppleRate": 0, "AppleValue": 0, "FinalDate": None, "Regdate": rd}

    class _Store:
        def __init__(self):
            self.t = {k: [] for k in _so.TABLES}
            self.item, self.enroll, self.chars, self.online, self.pool = [], {}, {}, set(), 1

    def _match(table, where, params, rows):
        p = list(params)
        if "NOT EXISTS" in where and table == "Charinfo":
            act = {r["Userindex"] for r in S.t["SoulMate"] if r["State"] == 1}
            out = [r for r in rows if r["Share"] != 0 and r["Userindex"] not in act]
            return [r for r in out if not p or r["Userindex"] == p[0]]
        if " OR " in where:
            return [r for r in rows if p[0] in (r["Userindex"], r["Ouserindex"])]
        out = []
        for r in rows:
            q, ok = list(p), True
            for cl in where.split(" AND "):
                cl = cl.strip()
                m = _re.match(r"(\w+) IN \((.+)\)$", cl)
                if m:
                    n = m.group(2).count("?")
                    vals, q = q[:n], q[n:]
                    ok = ok and r[m.group(1)] in vals
                    continue
                m = _re.match(r"(\w+) (=|<>) (\?|-?\d+)$", cl)
                v = q.pop(0) if m.group(3) == "?" else int(m.group(3))
                ok = ok and ((r[m.group(1)] == v) if m.group(2) == "=" else (r[m.group(1)] != v))
            if ok:
                out.append(r)
        return out

    def _read(w, table, where, params=(), lock=False, alias=""):
        return [dict(r) for r in _match(table, where, params, S.t[table])]

    class _W:
        def rows(self, sql, params=()):
            p = list(params)
            if "Aidx1 = ?" in sql:                       # перепроверка 23 М3: ссылки других кланов
                return [{"Clanidx": x["Clanidx"]} for x in S.t.get("ClanData", []) if x["Clanidx"] != p[0]
                        and p[0] in (x.get("Aidx1"), x.get("Aidx2"), x.get("Aidx3"), x.get("Waridx"))]
            if "Share <> 0" in sql:                      # перепроверка 23 М2
                return [{"Userindex": u} for u in p if any(r.get("Share") for r in S.t.get("Charinfo", []) if r.get("Userindex") == u)]
            if "Code BETWEEN 21097 AND 21106" in sql:
                return [{"Userindex": x["Userindex"]} for x in S.item if x["Userindex"] in p and 21097 <= x["Code"] <= 21106
                        and x.get("Owner") == 1]
            if "FROM dbo.Item" in sql:
                return [dict(x) for x in S.item if x["Userindex"] in p[:2]]
            if "TOP 1 1 AS x FROM dbo.Charinfo" in sql:
                return [{"x": 1}] if p[0] in {u for u, _i in S.chars} else []
            if "FROM dbo.CharOption" in sql:
                return [{"Userindex": u, "SmEnroll": S.enroll.get(u, 1)} for u in p]
            if "MIN(i.Smidx)" in sql:
                return [{"s": S.pool}]
            if "FROM dbo.CharPos" in sql:
                return [{"x": 1}] if (p[0], p[1]) in S.online else []
            if "COUNT(*) AS n FROM dbo.CharFriend" in sql:
                return [{"n": sum(1 for r in S.t["CharFriend"] if (r["Userindex"], r["Charidx"]) == (p[0], p[1]))}]
            if "FROM dbo.Charinfo" in sql and "AS h" in sql:
                k = (p[0], p[1])
                return [{"Charname": S.chars[k], "h": S.chars[k].encode("cp1251").hex().upper()}] if k in S.chars else []
            if "FROM dbo.CharFriend f" in sql:
                out = []
                for r in S.t["CharFriend"]:
                    cur = S.chars.get((r["Fuserindex"], r["Fcharidx"]))
                    if cur is not None and cur.encode("cp1251").hex().upper() != r["Charname"]:
                        out.append(dict(r, cur=cur.encode("cp1251").hex().upper()))
                return out
            raise AssertionError("неожиданный запрос: " + sql[:80])

    S = _Store()
    W = _W()
    _r0, _pt0, _et0, _iw0 = _so.read, _sm.itemgive.plan_take, _sm.exp_table, _so.in_world
    _so.read = _read
    _sm.itemgive.plan_take = lambda w, p, lock=False: {"uid": p["uid"], "idx": p["idx"], "plate": p["plate"], "posx": p["posx"], "code": 21100,
                                                       "sig": {"uuid": p["uuid"], "code": 21100, "amount": 0, "fdate": None, "take": None, "weight": 0}}
    _sm.exp_table = lambda: {i + 1: [0, 10, 25, 45, 70][i] if i < 5 else 70 + 30 * i for i in range(30)}
    _so.in_world = lambda w, u, i=None: (u, i) in S.online
    try:
        # --- соулмейт
        S.t["SoulMate"] = [_sm_row(1, 7001, 7002, lvl=3, exp=30, fs=12), _sm_row(1, 7002, 7001, lvl=3, exp=30, fs=12)]
        S.t["Charinfo"] = [{"Userindex": 7001, "Charidx": 10, "Share": 1}, {"Userindex": 7002, "Charidx": 11, "Share": 1}]
        S.item = [{"Userindex": 7002, "Charidx": 11, "Plate": 1, "Posx": 4, "Uuid": "U1", "Code": 21100}]
        pl = _sm.plan_break(W, {"uid": 7001}, role="owner")
        check("соулмейт: разрыв — State 0 обеих строк, Share 0 у обеих учёток, кристалл — изъятием, журнал «Panel Breakup»",
              [c[2]["State"] for c in pl["changes"] if c[0] == "SoulMate"] == [0, 0]
              and [c[2]["Share"] for c in pl["changes"] if c[0] == "Charinfo"] == [0, 0] and len(pl["takes"]) == 1
              and pl["logs"][0][2][-1] == "Panel Breakup" and sorted(pl["uids"]) == [7001, 7002])
        S.item[0]["Plate"] = 3
        check("соулмейт: кристалл не в сумке — отказ; нет связи — отказ; служебная учётка у не-владельца — отказ",
              raises(lambda: _sm.plan_break(W, {"uid": 7001}, role="owner"), ops.OpRefused)
              and raises(lambda: _sm.plan_break(W, {"uid": 7009}, role="owner"), ops.OpRefused)
              and raises(lambda: (S.t["SoulMate"].extend([_sm_row(9, 2, 3), _sm_row(9, 3, 2)]), _sm.plan_break(W, {"uid": 2}, role="admin")),
                         ops.OpRefused))
        S.item = []
        pl = _sm.plan_level(W, {"uid": 7002, "level": 4}, role="owner")
        check("соулмейт: уровень — SmLvl и SmExp = начало уровня по SoulMateExpTable (запись L) у обеих строк, журнал SoulMateLevelUp",
              all(c[2]["SmLvl"] == 4 and c[2]["SmExp"] == 45 for c in pl["changes"]) and len(pl["changes"]) == 2
              and pl["logs"][0][0] == "SoulMateLevelUp" and pl["ulogs"][0][2][2] == 3)
        check("соулмейт: уровень 0 и 31 — отказ; тот же уровень с другим опытом — опыт ставится на начало уровня",
              raises(lambda: _sm.plan_level(W, {"uid": 7002, "level": 31}, role="owner"), ops.OpRefused)
              and raises(lambda: _sm.plan_level(W, {"uid": 7002, "level": 0}, role="owner"), ops.OpRefused)
              and raises(lambda: _sm.plan_level(W, {"uid": 7002, "level": 3}, role="owner"), ops.OpRefused) is False
              and _sm.plan_level(W, {"uid": 7002, "level": 3}, role="owner")["changes"][0][2]["SmExp"] == 25)
        pl = _sm.plan_friendship(W, {"uid": 7001, "value": "40"}, role="owner")
        check("соулмейт: дружба — FriendShip обеих строк, FinalDate NULL, журнал SoulMateinfo «FriendShip-Panel»; 256 и -1 — отказ",
              all(c[2]["FriendShip"] == 40 and c[2]["FinalDate"] is None for c in pl["changes"])
              and pl["logs"][0][2][-1] == "FriendShip-Panel" and pl["logs"][0][2][2:4] == [12, 40]
              and raises(lambda: _sm.plan_friendship(W, {"uid": 7001, "value": 256}, role="owner"), ops.OpRefused)
              and raises(lambda: _sm.plan_friendship(W, {"uid": 7001, "value": -1}, role="owner"), ops.OpRefused))
        S.chars = {(7001, 10): "A", (7002, 11): "B", (7003, 10): "C", (7004, 10): "D"}
        check("соулмейт: связать — с собой, при активной связи — отказ",
              raises(lambda: _sm.plan_link(W, {"uid": 7001, "uid2": 7001}, role="owner"), ops.OpRefused)
              and raises(lambda: _sm.plan_link(W, {"uid": 7001, "uid2": 7003}, role="owner"), ops.OpRefused))
        S.t["SoulMate"] = [_sm_row(1, 7001, 7002, st=0, lvl=5, exp=99), _sm_row(1, 7002, 7001, st=0, lvl=5, exp=99)]
        pl = _sm.plan_link(W, {"uid": 7002, "uid2": 7001}, role="owner")
        check("соулмейт: связать прежнюю пару — обе строки истории State 1, Regdate сейчас, уровень сохранён (как UPSoulMateOk)",
              [(c[1]["Smidx"], c[2]["State"], c[2]["Regdate"], c[2]["SmLvl"]) for c in pl["changes"]] == [(1, 1, _so.NOW, 5)] * 2
              and pl["logs"][0][2][-1] == "Panel Restore")
        S.t["SoulMate"] = [_sm_row(1, 7001, 7002, st=0, lvl=5, exp=99), _sm_row(4, 7002, 7005, st=0, rd="2026-01-01 00:00:00.000"),
                           _sm_row(5, 7002, 7006, st=0), _sm_row(6, 7002, 7007, st=0)]
        pl = _sm.plan_link(W, {"uid": 7002, "uid2": 7001}, role="owner")
        kinds = [(c[1] is None, c[2] is None, (c[1] or c[2])["Smidx"]) for c in pl["changes"]]
        check("соулмейт: связать, строка только у одной — у второй вытесняется самая старая история (пара 4), вставка с теми же уровнем и "
              "опытом, «Panel Active-OneSide» (первая учётка журнала — та, у кого строка была)",
              kinds == [(False, True, 4), (True, False, 1), (False, False, 1)] and pl["changes"][1][2]["Userindex"] == 7002
              and pl["changes"][1][2]["SmLvl"] == 5 and pl["changes"][1][2]["SmExp"] == 99 and pl["logs"][0][2][2:] == [7001, 7002, "Panel Active-OneSide"])
        S.t["SoulMate"], S.pool = [], 17
        S.enroll = {7004: 0}
        pl = _sm.plan_link(W, {"uid": 7003, "uid2": 7004}, role="owner")
        check("соулмейт: связать новых — номер из пула, две строки уровень 1 опыт 0 дружба 0 info 1, «Panel Birth»; SmEnroll 0 — предупреждение",
              [(c[1], c[2]["Smidx"], c[2]["Userindex"], c[2]["Ouserindex"], c[2]["SmLvl"], c[2]["SmExp"], c[2]["info"]) for c in pl["changes"]]
              == [(None, 17, 7003, 7004, 1, 0, 1), (None, 17, 7004, 7003, 1, 0, 1)] and pl["logs"][0][2][-1] == "Panel Birth"
              and any("SmEnroll" in x for x in pl["warn"]))
        S.t["Charinfo"] = [{"Userindex": 7001, "Charidx": 10, "Share": 1}, {"Userindex": 7003, "Charidx": 10, "Share": 0}]
        pl = _sm.plan_share_fix(W, {}, role="owner")
        check("соулмейт: сверка S5 — Share 0 у персонажа учётки без активной связи; нечего — отказ",
              [(c[1]["Userindex"], c[2]["Share"]) for c in pl["changes"]] == [(7001, 0)]
              and raises(lambda: _sm.plan_share_fix(W, {"uid": 7003}, role="owner"), ops.OpRefused))
        # --- друзья
        S.chars = {(7001, 10): "Alpha", (7002, 11): "Beta", (7001, 11): "Gamma"}
        hx = lambda s: s.encode("cp1251").hex().upper()
        S.t["CharFriend"] = [{"Userindex": 7001, "Charidx": 10, "Fuserindex": 7002, "Fcharidx": 11, "Charname": hx("OldBeta")},
                             {"Userindex": 7002, "Charidx": 11, "Fuserindex": 7001, "Fcharidx": 10, "Charname": hx("Alpha")}]
        pl = _fr.plan_delete(W, {"uid": 7001, "idx": 10, "fuid": 7002, "fidx": 11}, role="owner")
        check("друзья: удалить — обе стороны (как UPFriendDelete), проверка «не в игре» — только владелец",
              [c[2] for c in pl["changes"]] == [None, None] and pl["uids"] == [7001])
        S.online = {(7002, 11)}
        check("друзья: друг в игре — предупреждение, не отказ; нет строки — отказ",
              any("в игре" in x for x in _fr.plan_delete(W, {"uid": 7001, "idx": 10, "fuid": 7002, "fidx": 11}, role="owner")["warn"])
              and raises(lambda: _fr.plan_delete(W, {"uid": 7001, "idx": 11, "fuid": 7002, "fidx": 11}, role="owner"), ops.OpRefused))
        S.online = set()
        check("друзья: добавить — уже взаимны, одна учётка, нет персонажа — отказ",
              raises(lambda: _fr.plan_add(W, {"uid": 7001, "idx": 10, "fuid": 7002, "fidx": 11}, role="owner"), ops.OpRefused)
              and raises(lambda: _fr.plan_add(W, {"uid": 7001, "idx": 10, "fuid": 7001, "fidx": 11}, role="owner"), ops.OpRefused)
              and raises(lambda: _fr.plan_add(W, {"uid": 7001, "idx": 10, "fuid": 7009, "fidx": 1}, role="owner"), ops.OpRefused))
        S.t["CharFriend"] = S.t["CharFriend"][1:]
        pl = _fr.plan_add(W, {"uid": 7001, "idx": 10, "fuid": 7002, "fidx": 11}, role="owner")
        check("друзья: добавить при односторонней строке — дописывается недостающая сторона, имя — из Charinfo",
              len(pl["changes"]) == 1 and pl["changes"][0][2] == {"Userindex": 7001, "Charidx": 10, "Fuserindex": 7002, "Fcharidx": 11,
                                                                     "Charname": hx("Beta")})
        S.t["CharFriend"] += [{"Userindex": 7001, "Charidx": 10, "Fuserindex": 8000 + k, "Fcharidx": 10, "Charname": "00"} for k in range(50)]
        check("друзья: у владельца уже 50 — отказ (лимит UPFriendAdd)",
              raises(lambda: _fr.plan_add(W, {"uid": 7001, "idx": 10, "fuid": 7002, "fidx": 11}, role="owner"), ops.OpRefused))
        S.t["CharFriend"] = [{"Userindex": 7001, "Charidx": 10, "Fuserindex": 7002, "Fcharidx": 11, "Charname": hx("OldBeta")}]
        pl = _fr.plan_names(W, {}, role="owner")
        check("друзья: сверка F3 — устаревшее имя → нынешнее из Charinfo байт в байт",
              [(c[1]["Charname"], c[2]["Charname"]) for c in pl["changes"]] == [(hx("OldBeta"), hx("Beta"))])
        # --- клан
        def _clan_row(**kw):
            d = {c: 0 for c, _k in _so.TABLES["ClanData"][1]}
            d.update(Clanidx=5, Cname=hx("Wolves"), Captain=hx("Alpha"), Capuserindex=7001, CapCharidx=10, JoinCnt=3, Maxcnt=50, Notice=None,
                     MarkFlag=1, Markidx=2, MarkColor=4278190080, Aname1="", Aname2="", Aname3="", Warname="")
            d.update(kw)
            return d

        def _mem(u, i, g, nm):
            return {"Clanidx": 5, "Userindex": u, "Charidx": i, "Cname": hx("Wolves"), "Charname": hx(nm), "Grade": g, "DonationPoint": 0,
                    "Callname": "", "Memo": ""}
        S.chars = {(7001, 10): "Alpha", (7002, 11): "Beta", (7003, 10): "Gamma"}
        S.t["ClanData"] = [_clan_row()]
        S.t["ClanMember"] = [_mem(7001, 10, 1, "Alpha"), _mem(7002, 11, 5, "Beta"), _mem(7003, 10, 2, "Gamma"), _mem(7004, 10, 10, "Req")]
        S.t["ClanNotice"] = [{"Clanidx": 5, "idx": k, "Charname": hx("Alpha"), "Edate": "2026-11-0%d 00:00:00.000" % k, "Notice": hx("n%d" % k)}
                             for k in range(1, 6)]
        S.t["CampClanData"] = [{"CampType": 1, "ClanIndex": 5, "EnterPoint0": 3, "EnterPoint1": 0, "EnterPoint2": 0}]
        S.t["CampOwnerData"] = [{"CampType": 1, "MvpClanIndex": 5}, {"CampType": 2, "MvpClanIndex": 0}]
        pl = _cl.plan_kick(W, {"clan": 5, "uid": 7002, "idx": 11}, role="owner")
        check("клан: исключить — строка члена удалена, JoinCnt − 1 (как UPClanSecede), «не в игре» — все члены, ClanLog «Panel Member Secede»",
              pl["changes"][0][2] is None and pl["changes"][1][2]["JoinCnt"] == 2 and sorted(set(pl["uids"])) == [7001, 7002, 7003, 7004]
              and pl["logs"][0][0] == "ClanLog" and pl["logs"][0][2][-1] == "Panel Member Secede")
        pl = _cl.plan_kick(W, {"clan": 5, "uid": 7004, "idx": 10}, role="owner")
        check("клан: заявка (Grade 10) — как UPClanWaitCancel, без JoinCnt; главу — отказ",
              len(pl["changes"]) == 1 and raises(lambda: _cl.plan_kick(W, {"clan": 5, "uid": 7001, "idx": 10}, role="owner"), ops.OpRefused))
        pl = _cl.plan_captain(W, {"clan": 5, "uid": 7003, "idx": 10}, role="owner")
        ch = {(c[0], (c[1] or {}).get("Userindex")): c[2] for c in pl["changes"]}
        check("клан: сменить главу — Captain/Capuserindex/CapCharidx, старый Grade 4, новый Grade 1 (как UPClanOwnerTransfer)",
              ch[("ClanData", None)]["Captain"] == hx("Gamma") and ch[("ClanData", None)]["Capuserindex"] == 7003
              and ch[("ClanMember", 7001)]["Grade"] == 4 and ch[("ClanMember", 7003)]["Grade"] == 1
              and raises(lambda: _cl.plan_captain(W, {"clan": 5, "uid": 7004, "idx": 10}, role="owner"), ops.OpRefused))
        pl = _cl.plan_disband(W, {"clan": 5}, role="owner")
        cnt = {}
        for c in pl["changes"]:
            cnt[c[0]] = cnt.get(c[0], 0) + 1
        check("клан: распустить — состав, объявления (исправление дефекта), лагерь, MVP → −1, карточка последней; ClanLog «Panel Clan Break Up»",
              cnt == {"ClanMember": 4, "ClanNotice": 5, "CampClanData": 1, "CampOwnerData": 1, "ClanData": 1}
              and pl["changes"][-1][0] == "ClanData" and [c[2] for c in pl["changes"] if c[0] == "CampOwnerData"] == [{"CampType": 1, "MvpClanIndex": -1}]
              and pl["logs"][0][2][-1] == "Panel Clan Break Up")
        S.t["ClanData"].append(dict(_clan_row(), Clanidx=9, Aidx1=5))
        check("клан: роспуск, когда другой клан ссылается союзом/войной — отказ со списком (перепроверка 23 М3)",
              raises(lambda: _cl.plan_disband(W, {"clan": 5}, role="owner"), ops.OpRefused))
        S.t["ClanData"].pop()
        pl = _cl.plan_mark_reset(W, {"clan": 5}, role="owner")
        check("клан: сбросить эмблему — 6 чисел в 0; без эмблемы — отказ",
              all(pl["changes"][0][2][k] == 0 for k in _cl.MARK)
              and raises(lambda: (S.t["ClanData"].__setitem__(0, _clan_row(MarkFlag=0, Markidx=0, MarkColor=0)),
                                  _cl.plan_mark_reset(W, {"clan": 5}, role="owner")), ops.OpRefused))
        pl = _cl.plan_notice_add(W, {"clan": 5, "author": "GM", "text": "Привет"}, role="owner")
        check("клан: объявление при 5 — удаляется самое старое (idx 1), новое — номер базы, текст cp1251; без «не в игре»",
              pl["changes"][0][1]["idx"] == 1 and pl["changes"][0][2] is None and pl["changes"][1][2]["idx"] == _so.NEW
              and pl["changes"][1][2]["Notice"] == hx("Привет") and pl["uids"] == [])
        check("клан: объявление — пусто, 501 байт, автор 21 байт, знак вне cp1251 — отказ",
              all(raises(lambda q=q: _cl.plan_notice_add(W, dict({"clan": 5, "author": "GM", "text": "x"}, **q), role="owner"), ops.OpRefused)
                  for q in ({"text": " "}, {"text": "x" * 501}, {"author": "a" * 21}, {"text": "日本"})))
        check("клан: не-владелец при служебных учётках в составе — отказ",
              raises(lambda: (S.t["ClanMember"].append(_mem(2, 10, 5, "Svc")), _cl.plan_kick(W, {"clan": 5, "uid": 7002, "idx": 11}, role="admin")),
                     ops.OpRefused))
    finally:
        _so.read, _sm.itemgive.plan_take, _sm.exp_table, _so.in_world = _r0, _pt0, _et0, _iw0
    # --- запись: SQL каркаса на записывающем подставном писателе
    class _Rec:
        def __init__(self, n=1, back=None):
            self.q, self.n, self.back = [], n, back or []

        def execute(self, sql, params=()):
            self.q.append((sql, list(params)))
            return self.n

        def rows(self, sql, params=()):
            self.q.append((sql, list(params)))
            if "OUTPUT inserted" in sql:
                return [{"ident": 42}]
            return [dict(x) for x in self.back]
    b = _sm_row(3, 7001, 7002, st=0)
    rw = _Rec(back=[dict(b, State=1, Regdate="2026-11-18 10:00:00.000")])
    got = _so.put(rw, "SoulMate", b, dict(b, State=1, Regdate=_so.NOW), "stale")
    check("запись: обновление — только изменённые столбцы, NOW = GETDATE(), сверка «было» по всем столбцам, «стало» перечитано из базы",
          rw.q[0][0].startswith("UPDATE dbo.SoulMate SET State = ?, Regdate = GETDATE() WHERE") and "CONVERT(varchar(23), FinalDate, 121)" in rw.q[0][0]
          and got["Regdate"] == "2026-11-18 10:00:00.000")
    rw = _Rec(back=[{"Clanidx": 5, "idx": 42, "Charname": "4142", "Edate": "2026-11-18 10:00:00.000", "Notice": "41"}])
    got = _so.put(rw, "ClanNotice", None, {"Clanidx": 5, "idx": _so.NEW, "Charname": "4142", "Edate": _so.NOW, "Notice": "41"}, "stale")
    check("запись: вставка с IDENTITY — без idx, OUTPUT inserted.idx, текст — байты hex (CONVERT varbinary стиль 2)",
          "OUTPUT inserted.idx" in rw.q[0][0] and "(Clanidx, Charname, Edate, Notice) OUTPUT" in rw.q[0][0] and "CONVERT(varbinary(500), ?, 2)" in rw.q[0][0]
          and got["idx"] == 42)
    check("запись: «строка изменилась» (0 строк) — отказ",
          raises(lambda: _so.put(_Rec(n=0), "CharFriend", {"Userindex": 1, "Charidx": 1, "Fuserindex": 2, "Fcharidx": 2, "Charname": "41"}, None, "stale"),
                 ops.OpRefused))
    sg = _so.sig([["ClanData", {"MarkColor": 9007199254740993, "Clanidx": 5}, None]], [["take", {"uuid": "x"}]])
    check("отпечаток: переживает JSON браузера (кортежей нет, целые ≥ 2^53 — строкой)", json.loads(json.dumps(sg)) == sg
          and sg[0][1]["MarkColor"] == "9007199254740993")
    from core import i18n as _i18
    _i18.set_lang("en")
    try:
        samples = ["разорвать связь соулмейта 1: учётки 1 и 2 (уровень 1, опыт 0, дружба 0)",
                   "клан правится, только когда все члены клана не в игре: учётка 7 — учётки нет в Us_member",
                   "Друзья: удалить: возвращено", "персонаж уже глава клана",
                   "распустить клан Щит (3): членов 1, объявлений 0, строк лагеря 0, снять MVP лагеря 1"]
        en = [_i18.tr(x) for x in samples]
        check("перевод: тексты соулмейта, друзей и клана (имя клана «Щит» — без подстановки, вложенная причина — переведена)",
              en[0].startswith("break soulmate bond 1") and en[1].endswith("account 7 — account not in Us_member")
              and en[2] == "Friends: delete: restored" and en[3] == "the character is already the clan leader"
              and en[4] == "disband clan Щит (3): members 1, notices 0, camp rows 0, remove MVP of camp 1", en)
    finally:
        _i18.set_lang("ru")

def _qr_check():
    """QR второго фактора: матрица бит в бит как у пакета qrcode (если он есть — на ПК), иначе — только устройство."""
    from core import qr
    uri = "otpauth://totp/Astory:sitxovski?secret=ABCDEFGHIJKLMNOPQRSTUVWXYZ234567&issuer=Astory&digits=6&period=30"
    m = qr.matrix(uri)
    n = len(m)
    check("QR: квадрат, размер версии, искатели на месте", n in range(21, 58, 4) and all(len(r) == n for r in m)
          and m[0][:7] == "1111111" and m[6][:7] == "1111111" and m[0][n - 7:] == "1111111" and m[n - 1][:7] == "1111111")
    try:
        import qrcode
        import qrcode.util
    except ImportError:
        print("-- QR: сверка с пакетом qrcode пропущена (нет пакета)")
        return
    bad = []
    for text in (uri, "hi", "x" * 150, "Привет" * 8):
        v = (len(qr.matrix(text)) - 17) // 4
        for mask in range(8):
            q = qrcode.QRCode(version=v, error_correction=qrcode.constants.ERROR_CORRECT_M, mask_pattern=mask, border=0)
            q.add_data(qrcode.util.QRData(text.encode("utf-8"), mode=qrcode.util.MODE_8BIT_BYTE))
            q.make(fit=False)
            ref = ["".join("1" if x else "0" for x in r) for r in q.get_matrix()]
            if ref != qr.matrix(text, mask=mask, version=v):
                bad.append((len(text), v, mask))
    check("QR: бит в бит как у пакета qrcode (4 длины × 8 масок)", not bad, bad)


# ------------------------------------------------------------------ A2. HTTPS на живом сокете

# ------------------------------------------------------------------ A3. мост P127 (без сети и без GameServer)

class _FakeBridge:
    """Подставной мост для core/bridge.py: узлы, присутствие, очередь; итог команды — сразу (как после такта узла).
    state — «база» игрока: exited() по достижении exit_after переводит её в «вышел» и меняет уровень (как UPLogOutGame)."""

    def __init__(self, mode=1, age=1, present=None, outcome=2, exit_after=1):
        self.mode, self.age, self.outcome, self.exit_after = mode, age, outcome, exit_after
        self.present = present if present is not None else [
            {"node": "GameServer", "user_num": 5, "Userindex": 77, "Charidx": 1, "session_uid": 77, "charname": "Тест", "map": 3,
             "x": 10, "z": 20, "mode": mode}]
        self.cmds, self.exit_polls, self.log, self.exit_rows = [], 0, [], None
        self.state = {"inworld": True, "lvl": 10}

    def nodes(self):
        return [{"node": "GameServer", "mode": self.mode, "age_s": self.age}]

    def presence(self, uid=None):
        return [r for r in self.present if uid is None or r["Userindex"] == uid or r["session_uid"] == uid]

    def enqueue(self, nonce, op, uid, idx, node, args, ttl, mac, by, audit_id, deadline):
        self.cmds.append(dict(nonce=nonce, op=op, uid=uid, idx=idx, node=node, args=args, ttl=ttl, mac=mac, deadline=deadline))
        self.log.append("enqueue:" + op)
        return len(self.cmds), "2026-11-18 12:00:00"

    def get(self, cid):
        return {"id": cid, "status": self.outcome, "result": "итог стенда"}

    def exited(self, rows, since):
        self.exit_polls += 1
        self.exit_rows = rows
        self.log.append("exited?")
        if self.exit_polls >= self.exit_after:
            self.state.update(inworld=False, lvl=11)          # выход записал уровень из памяти GameServer
            return True
        return False


def part_bridge():
    """Мост P127: подпись (вектор DLL), план «кик + запись», kick_and_wait, ops.run/undo в два шага, выход по хозяину, SQL на LocalDB."""
    from core import bridge
    from domains import items
    key = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
    # тот же вектор проверяет stand_p127 на DLL (BCrypt): строки подписи v2 (со сроком) совпадают байт в байт
    check("мост: подпись v2 = вектор DLL (stand_p127)", bridge.sign(key, "00000000-0000-4000-8000-000000000001", "kick", 77, 1, "",
          "text=Привет;x", 30, 1900000000) == "de97762b01eb93f7540813905fb86003d6eaafab75598f5a41e4560438506f2e")
    check("мост: срок входит в подпись", bridge.sign(key, "n", "kick", 77, 1, "", "", 30, 1900000000)
          != bridge.sign(key, "n", "kick", 77, 1, "", "", 30, 1900000001))
    db._pw["BRIDGE_HMAC_KEY"] = key.hex()
    settle = bridge.SETTLE_S
    bridge.SETTLE_S = 0

    class W:                                  # «учётка в игре» для items.online_state; источник — state подставного моста
        def __init__(self, state):
            self.state = state

        def rows(self, sql, params=()):
            inworld = self.state["inworld"]
            if "Us_member" in sql:
                return [{"Flag": 1 if inworld else 0, "UserNum": 3 if inworld else -1}]
            if "UserNum <> -1" in sql:
                return [{"Charidx": 1}] if inworld else []
            return []
    try:
        fb = _FakeBridge()
        bridge.set_fake(fb)
        check("мост: без рамки операции — прежний отказ «в игре»", not items.online_state(W(fb.state), 77)[0])
        with bridge.kick_plan() as plan:
            ok1, _ = items.online_state(W(fb.state), 77)
            ok2, _ = items.online_state(W(fb.state), 77, lock=True)
        check("мост: предпросмотр в рамке — не отказ, учётка в плане кика", ok1 and plan["uids"] == {77})
        check("мост: под блокировкой — отказ (кик не внутри транзакции), учётка в «blocked»", not ok2 and plan["blocked"] == {77})
        check("мост: рамка закрыта — снова прежний отказ", not items.online_state(W(fb.state), 77)[0])
        for name, f in (("Mode=0", _FakeBridge(mode=0)), ("пульс старый", _FakeBridge(age=60)), ("игрок не виден мосту", _FakeBridge(present=[]))):
            bridge.set_fake(f)
            with bridge.kick_plan() as plan:
                ok, why = items.online_state(W(f.state), 77)
            check("мост: %s — прежний отказ, плана нет" % name, not ok and not plan["uids"] and why)
        # kick_and_wait: кик каждой сессии, подпись со сроком, ожидание записи выхода
        fb = _FakeBridge(exit_after=3)
        bridge.set_fake(fb)
        t0 = int(time.time())
        done = bridge.kick_and_wait([77], by="selftest")
        c = fb.cmds[0]
        check("мост: kick_and_wait — команда kick узлу присутствия, подпись v2 со сроком верная",
              len(fb.cmds) == 1 and c["op"] == "kick" and c["node"] == "GameServer" and c["uid"] == 77 and c["idx"] == 1
              and t0 + c["ttl"] - 1 <= c["deadline"] <= int(time.time()) + c["ttl"]
              and c["mac"] == bridge.sign(key, c["nonce"], "kick", 77, 1, "GameServer", "", c["ttl"], c["deadline"]) and done[0]["status"] == 2)
        check("мост: kick_and_wait ждёт записи выхода (3 опроса) по кикнутым строкам", fb.exit_polls == 3 and fb.exit_rows[0]["Userindex"] == 77)
        for st, name in ((3, "отказ узла"), (6, "журнал Mode=0"), (5, "просрочена")):
            bridge.set_fake(_FakeBridge(outcome=st))
            check("мост: кик — %s → BridgeError (запись не начинается)" % name, raises(lambda: bridge.kick_and_wait([77]), bridge.BridgeError))
        bridge.set_fake(_FakeBridge(outcome=4))
        check("мост: кик — «нет на сервере» (уже вышел) годится", bridge.kick_and_wait([77])[0]["status"] == 4)
        fb = _FakeBridge(exit_after=10 ** 6)
        bridge.set_fake(fb)
        try:
            bridge.kick_and_wait([77], exit_timeout=1)
            ex_k = None
        except bridge.BridgeError as ex:
            ex_k = ex
        check("мост: выход не записан за срок → BridgeError с перечнем уже отключённых", ex_k is not None and len(ex_k.kicked) == 1)

        # ревизия 24 М-2: вход соулмейтом — правится учётка СЕССИИ 88, персонаж хозяина 77: выход ждём по хозяину (CharPos/Us_member/LogInfo 77)
        class R:
            def __init__(self, data):
                self.data, self.q = data, []

            def rows(self, sql, params=()):
                self.q.append((sql, params))
                for k, v in self.data.items():
                    if k in sql and params and params[0] == v[0]:
                        return v[1]
                return []
        joy = R({"CharPos": (77, [{"UserNum": -1}])})
        op = R({"Us_member": (77, [{"Flag": 0, "UserNum": -1}])})
        lg = R({"LogInfo": (77, [{"Logout": "x"}])})
        rows = [{"Userindex": 77, "Charidx": 1, "session_uid": 88}]
        ok_owner = bridge.exit_written(joy, op, lg, rows, "2026-11-18 12:00:00")
        check("мост: выход соулмейта — ждём по хозяину персонажа (77), не по учётке сессии (88)", ok_owner
              and all(q[1][0] == 77 for r in (joy, op, lg) for q in r.q))
        lg2 = R({"LogInfo": (77, [])})
        check("мост: нет строки LogInfo хозяина после кика — «ещё не записан»", not bridge.exit_written(joy, op, lg2, rows, "2026-11-18 12:00:00"))
        check("мост: строка LogInfo — строго не раньше кика (без допуска −2 с)", any(">= ?" in q[0] and "DATEADD" not in q[0] for q in lg.q))

        # ops.run: кик, затем НОВЫЙ предпросмотр на подтверждение (без записи); права; журнал кика
        calls = []

        class Probe(ops.Operation):
            name, title, perm, reversible = "selftest.bridge_probe", "самотест моста", "status.view", True

            def preview(self, ctx, p):
                st = _fake_state()
                ok, why = items.online_state(W(st), 77)
                if not ok:
                    raise ops.OpRefused("править можно только когда игрок не в игре: " + why)
                return {"text": "уровень %d" % st["lvl"], "warnings": [], "expect": st["lvl"]}

            def apply(self, ctx, p, prev):
                calls.append("apply")
                return {"before": None, "after": {"x": 1}, "message": "записано"}

            def undo(self, ctx, row):
                ok, why = items.online_state(W(_fake_state()), 77, lock=True)
                if not ok:
                    raise ops.OpRefused("откат только когда игрок не в игре: " + why)
                calls.append("undo")
                return {"before": None, "after": None, "message": "откачено"}

        def _fake_state():
            return bridge._fake["t"].state
        ops.REGISTRY[Probe.name] = Probe()
        wrote = []
        orig_write, orig_get, orig_mark = audit.write, audit.get, audit.mark_undone_by
        audit.write = lambda ctx, action, *a, **k: wrote.append((action, k.get("result", "ok"), k.get("message", ""))) or len(wrote)
        audit.get = lambda aid: {"result": "ok", "undone_by": None, "undo_of": None, "action": Probe.name, "target": "", "after_json": "{}"}
        audit.mark_undone_by = lambda *a: None
        ctx = ops.Ctx(1, "selftest", "owner")
        try:
            fb = _FakeBridge()
            bridge.set_fake(fb)
            r = ops.run(ctx, Probe.name, {}, dry=True)
            check("мост: ops.run dry — предупреждение «мост отключит», кика нет",
                  r["preview"]["bridge_kick"] == [77] and any("ОТКЛЮЧИТ" in w for w in r["preview"]["warnings"]) and not fb.cmds)
            fb.log.clear()
            r = ops.run(ctx, Probe.name, {})
            check("мост: ops.run — кик, выход, затем НОВЫЙ предпросмотр на подтверждение; записи нет (М-1)",
                  fb.log[:2] == ["enqueue:kick", "exited?"] and not calls and r["dry"] and r["kicked"]
                  and r["preview"]["expect"] == 11 and bridge.KICKED_WARN in r["preview"]["warnings"])
            check("мост: кик — своя запись журнала live.kick (М-3)", any(w[0] == "live.kick" and w[1] == "ok" for w in wrote))
            r2 = ops.run(ctx, Probe.name, {})
            check("мост: подтверждение — обычная офлайн-запись, повторного кика нет", calls == ["apply"] and len(fb.cmds) == 1 and not r2["dry"])
            calls.clear()
            bridge.set_fake(_FakeBridge())
            sup = ops.Ctx(2, "selftest2", "support")
            check("мост: без права players.kick — отказ, кика нет (М-3)",
                  raises(lambda: ops.run(sup, Probe.name, {}), ops.OpRefused) and not bridge._fake["t"].cmds and not calls)
            fb = _FakeBridge(outcome=3)
            bridge.set_fake(fb)
            wrote.clear()
            check("мост: ops.run — кик не удался → отказ, apply не звался, журнал live.kick «refused»",
                  raises(lambda: ops.run(ctx, Probe.name, {}), ops.OpRefused) and not calls
                  and any(w[0] == "live.kick" and w[1] == "refused" for w in wrote) and wrote[-1][1] == "refused")
            bridge.set_fake(_FakeBridge(mode=0))
            check("мост: ops.run — моста нет (Mode=0) → прежний отказ раздела", raises(lambda: ops.run(ctx, Probe.name, {}), ops.OpRefused))
            # откат: отказ «в игре» под блокировкой → кик → «повторите откат» (без автоматического повтора)
            fb = _FakeBridge()
            bridge.set_fake(fb)
            calls.clear()
            r = ops.undo(ctx, 1)
            check("мост: ops.undo — кик и ответ «повторите откат», откат сам не повторяется (М-1)",
                  r["dry"] and r["kicked"] and not calls and len(fb.cmds) == 1)
            r = ops.undo(ctx, 1)
            check("мост: ops.undo повторно — обычный откат", calls == ["undo"] and not r["dry"])
        finally:
            audit.write, audit.get, audit.mark_undone_by = orig_write, orig_get, orig_mark
            ops.REGISTRY.pop(Probe.name, None)
    finally:
        bridge.set_fake(None)
        bridge.SETTLE_S = settle
        db._pw.pop("BRIDGE_HMAC_KEY", None)
    _bridge_sql()


class _FakeLive(_FakeBridge):
    """Подставной мост v81: probe отвечает снимком памяти сервера; итог живых правок — «выполнена»."""

    def __init__(self, ver=81, owned=0, lvl=5, exp=5200, found=1, cap=100, **kw):
        _FakeBridge.__init__(self, **kw)
        for r in self.present:
            r["ver"] = ver
        self.snap = {"lvl": lvl, "exp": exp, "owned": owned, "found": found, "cap": cap}

    def get(self, cid):
        c = self.cmds[cid - 1]
        if c["op"] == "probe":
            t = "title=" in c["args"]
            return {"id": cid, "status": 2, "result": "lvl=%d;exp=%d;map=3;x=10;z=20;owned=%d;found=%d;cap=%d" % (
                self.snap["lvl"], self.snap["exp"], self.snap["owned"] if t else -1, self.snap["found"] if t else -1, self.snap["cap"])}
        return {"id": cid, "status": self.outcome, "result": "итог узла: %s %s" % (c["op"], c["args"])}


class _FakeGive(_FakeLive):
    """★ А2.3: подставной мост v82 — give/jump отвечают итогом узла в разметке DLL (given/units/plate/stop/cells; x/z/map)."""

    def __init__(self, give="given=2;q=2;units=2;plate=1;stop=0;cells=5.0.0,6.0.0", jump="x=51;z=60;map=3", **kw):
        _FakeLive.__init__(self, **kw)
        self.give, self.jump, self.rcode = give, jump, 0

    def get(self, cid):
        c = self.cmds[cid - 1]
        if c["op"] == "give":
            return {"id": cid, "status": self.outcome, "result": self.give, "result_code": self.rcode}
        if c["op"] == "jump":
            return {"id": cid, "status": self.outcome, "result": self.jump, "result_code": self.rcode}
        return _FakeLive.get(self, cid)


class _GiveW:
    """Подставной GameWriter для отката живой выдачи: учётка не в игре, ячейки Item, ключ P100, EXEC adm.ItemTake (запоминает)."""

    def __init__(self, cells, inworld=False, key=None):
        self.cells, self.inworld, self.key, self.takes, self.closed = cells, inworld, key, [], False

    def rows(self, sql, params=()):
        if "Us_member" in sql:
            return [{"Flag": 1 if self.inworld else 0, "UserNum": 3 if self.inworld else -1}]
        if "UserNum <> -1" in sql:
            return [{"Charidx": 1}] if self.inworld else []
        if "AsdaChargeGroup" in sql:
            return [{"GroupKey": self.key}] if self.key else []
        if sql.startswith("SELECT Uuid, Code, Amount, Weight") or sql.startswith("SELECT Posx, Uuid, Code, Amount, Weight"):
            if "Posx <> ?" in sql:                                       # двойники того же кода (М-1)
                return [self._row(x, c) for x, c in self.cells.items() if x != int(params[4]) and c[0] == int(params[3])]
            c = self.cells.get(int(params[3]))
            return [self._row(int(params[3]), c)] if c else []
        if sql.startswith("EXEC adm.ItemTake"):
            self.takes.append(tuple(params))
            return [{"LedgerId": 900 + len(self.takes)}]
        return []

    def _row(self, x, c):
        fp = c[3] if len(c) > 3 else {}
        return dict(Posx=x, Uuid=fp.get("Uuid", "AAAA-%d" % x), Code=c[0], Amount=c[1], Weight=c[2], fd="2026-11-19 10:00:00.000",
                    Opidx1=fp.get("Opidx1", -1), OpValue1=fp.get("OpValue1", 0), Opidx2=fp.get("Opidx2", -1), OpValue2=fp.get("OpValue2", 0),
                    Cell1=fp.get("Cell1", -1), Upcount=fp.get("Upcount", 0), MaxUpcnt=fp.get("MaxUpcnt"))

    def commit(self):
        pass

    def close(self):
        self.closed = True


def part_bridge_give():
    """★ А2.3: items.give и char.move (своя карта) живьём на узле v82; v81 — прежний путь; откат выдачи — «кик + изъятие»."""
    from core import bridge
    from domains import charmove as _cm, itemgive as _ig, srvtables
    key = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
    db._pw["BRIDGE_HMAC_KEY"] = key.hex()
    saved = (audit.write, audit.get, audit.mark_undone_by, db.GameWriter, srvtables.charge_cap)
    wrote = []
    audit.write = lambda ctx, action, *a, **k: wrote.append((action, k.get("result", "ok"), k.get("after"))) or len(wrote)
    audit.mark_undone_by = lambda *a: None
    ctx = ops.Ctx(1, "selftest", "owner")
    dflt = _ig.describe(24893)["default"]                     # самоцвет и ступень по умолчанию (у 24893 гнездо 0 без камня не бывает)
    gp = {"uid": 77, "idx": 1, "code": 24893, "qty": 2, "to": "bag", "opts": {"pairs": {}, "stone": dflt["stone"], "upcount": dflt["upcount"]}}
    try:
        bridge.set_fake(_FakeGive(ver=81))
        check("мост v82: узел v81 — живой выдачи нет (прежний путь «кик + запись»)", _ig._live_give(ctx, gp) is None)
        check("мост v82: узел v81 — перенос в своей карте не живьём", _cm._live_row(77, 1, {"Poridx": 3, "Posx": 50, "Posy": 60}) is None)
        fb = _FakeGive(ver=82)
        bridge.set_fake(fb)
        lv = _ig._live_give(ctx, gp)
        check("мост v82: items.give — живой предпросмотр, аргументы узлу (код, кол-во, сумка, пары −1/0, самоцвет, ступень)",
              lv and lv["live"]["args"] == "code=24893;q=2;ware=0;plate=1;o1=-1;v1=0;o2=-1;v2=0;gem=%d;up=%d" % (dflt["stone"], dflt["upcount"])
              and lv["expect"] == {"live": ["give", lv["live"]["args"]]} and _ig.LIVE_GIVE_WARN in lv["warnings"])
        check("мост v82: спецпредмет на склад — не живьём (у стока GM-выдача F только в сумку)",
              _ig._live_give(ctx, dict(gp, code=46, to="ware", opts=None)) is None)
        check("мост v82: больше 30 штук за раз — не живьём", _ig._live_give(ctx, dict(gp, qty=31)) is None)
        check("мост v82: стопка 570 — живьём, 571 — нет", _ig._live_give(ctx, dict(gp, code=20571, qty=570, opts=None)) is not None
              and _ig._live_give(ctx, dict(gp, code=20571, qty=571, opts=None)) is None)
        check("мост v82: опции у не-снаряжения — отказ, как офлайн", raises(lambda: _ig._live_give(ctx, dict(gp, code=46, opts={"stone": 1})), ops.OpRefused))
        r = ops.run(ctx, "items.give", gp, dry=True)
        check("мост v82: ops.run dry — живой предпросмотр, команд узлу нет", r["preview"].get("live") and not fb.cmds)
        r = ops.run(ctx, "items.give", dict(gp, expect=r["preview"]["expect"]))
        c = fb.cmds[-1]
        check("мост v82: items.give — команда give, журнал: «живьём», номер команды, ячейки итога узла",
              c["op"] == "give" and r["result"]["live"] and r["result"]["cmd"] == len(fb.cmds) and r["result"]["cells"] == [[5, 0, 0], [6, 0, 0]]
              and "выдано живьём 2 из 2" in r["message"])
        check("мост v82: ItemLedger панелью не пишется (журнал — UPGmItemAdd сервера), в журнале панели — операция",
              "ledger" not in r["result"] and wrote and wrote[-1][0] == "items.give")
        check("мост v82: офлайн-отпечаток при живом пути — отказ «повторите предпросмотр»",
              raises(lambda: ops.run(ctx, "items.give", dict(gp, expect={"code": 24893, "plate": 1, "ops": [], "opts": {}})), ops.OpRefused))
        fb.give = "given=1;q=2;units=1;plate=1;stop=2;cells=5.0.0"
        r = ops.run(ctx, "items.give", dict(gp, expect={"live": ["give", lv["live"]["args"]]}))
        check("мост v82: узел выдал часть — итог «выдано 1 из 2» и причина остановки, журнал — выданная ячейка",
              "выдано живьём 1 из 2" in r["message"] and "нет свободной ячейки в сумке" in r["message"] and r["result"]["cells"] == [[5, 0, 0]])
        fb.outcome = 3
        check("мост v82: отказ узла — отказ операции", raises(lambda: ops.run(ctx, "items.give", dict(gp, expect={"live": ["give", lv["live"]["args"]]})),
                                                             ops.OpRefused))
        fb.outcome = 2
        # откат живой выдачи: офлайн — изъятие по ячейкам итога (снаряжение — вся ячейка; заряды/стопка — выданное количество)
        gw = _GiveW({5: (24893, 0, 683), 6: (24893, 0, 683)})
        db.GameWriter = lambda name: gw
        gop = {"Opidx1": -1, "OpValue1": 0, "Opidx2": -1, "OpValue2": 0, "Cell1": 0, "Upcount": 0}
        u = _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "live": True, "code": 24893, "plate": 1, "cells": [[5, 0, 0], [6, 0, 0]], "opts": gop})
        check("откат живой выдачи: снаряжение — изъятие обеих ячеек целиком (adm.ItemTake, часть = NULL)",
              len(gw.takes) == 2 and gw.takes[0][3] == 6 and gw.takes[1][3] == 5 and gw.takes[0][8] is None and u["after"]["ledger"] == [901, 902])
        srvtables.charge_cap = lambda: 30000
        gw = _GiveW({3: (46, 25, 1)}, key=10)
        db.GameWriter = lambda name: gw
        _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "code": 46, "plate": 1, "cells": [[3, 10, 1]]})
        check("откат живой выдачи: заряды P100 (слито в стопку 25) — изъятие 10 зарядов, вес 0", gw.takes and gw.takes[0][8] == 10 and gw.takes[0][9] == 0)
        gw = _GiveW({7: (20571, 3, 69)})
        db.GameWriter = lambda name: gw
        check("откат живой выдачи: в стопке меньше выданного — отказ",
              raises(lambda: _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "code": 20571, "plate": 2, "cells": [[7, 7, 1]]}), ops.OpRefused) and not gw.takes)
        gw = _GiveW({5: (24894, 0, 683)})
        db.GameWriter = lambda name: gw
        check("откат живой выдачи: в ячейке другой предмет — отказ", raises(lambda: _ig._live_give_undo(
            ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0]]}), ops.OpRefused) and not gw.takes)
        # ★ ревизия 29 М-1: штучное — только ИМЕННО выданный предмет (Uuid или полный отпечаток), без двойников
        gw = _GiveW({5: (24893, 0, 683, {"Opidx1": 7, "OpValue1": 3})})
        db.GameWriter = lambda name: gw
        check("М-1 откат: в ячейке тот же код, но с другими опциями (свой старый предмет) — отказ, ничего не изъято",
              raises(lambda: _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0]], "opts": gop}), ops.OpRefused)
              and not gw.takes)
        gw = _GiveW({5: (24893, 0, 683), 9: (24893, 0, 683)})
        db.GameWriter = lambda name: gw
        check("М-1 откат: такой же предмет и в другой ячейке, Uuid выдачи неизвестен — отказ «не опознан однозначно»",
              raises(lambda: _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0]], "opts": gop}), ops.OpRefused)
              and not gw.takes)
        gw = _GiveW({5: (24893, 0, 683, {"Uuid": "U-OTHER"}), 9: (24893, 0, 683, {"Uuid": "U-GIVEN"})})
        db.GameWriter = lambda name: gw
        check("М-1 откат: Uuid выдачи известен, в ячейке другой Uuid (переложили) — отказ",
              raises(lambda: _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0, "U-GIVEN"]], "opts": gop}),
                     ops.OpRefused) and not gw.takes)
        gw = _GiveW({5: (24893, 0, 683, {"Uuid": "U-GIVEN"}), 9: (24893, 0, 683)})
        db.GameWriter = lambda name: gw
        _ig._live_give_undo(ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0, "U-GIVEN"]], "opts": gop})
        check("М-1 откат: Uuid совпал — изъята ровно ячейка 5 (двойник в 9 не мешает)", len(gw.takes) == 1 and gw.takes[0][3] == 5
              and gw.takes[0][5] == "U-GIVEN")
        check("К-4 откат: список ячеек неполный (trunc) — отказ", raises(lambda: _ig._live_give_undo(
            ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0]], "trunc": True}), ops.OpRefused))
        gw = _GiveW({5: (24893, 0, 683)}, inworld=True)
        db.GameWriter = lambda name: gw
        check("откат живой выдачи: игрок в игре — отказ под блокировкой (ops.undo отключит его и попросит повторить)", raises(lambda: _ig._live_give_undo(
            ctx, {"uid": 77, "idx": 1, "code": 24893, "plate": 1, "cells": [[5, 0, 0]]}), ops.OpRefused) and not gw.takes)
        db.GameWriter = saved[3]
        # ★ ревизия 29 М-2: итог «неизвестен» — запись журнала с номером команды; поздний итог — из adm.bridge_cmd; повтор до него — отказ
        w0 = bridge.wait
        bridge.wait = lambda cid, timeout=20.0, step=0.25: {"id": cid, "status": 1, "result": None}
        try:
            r = ops.run(ctx, "items.give", dict(gp, expect={"live": ["give", lv["live"]["args"]]}))
        finally:
            bridge.wait = w0
        pa = r["result"]
        check("М-2: итог неизвестен — запись «ok» с номером команды и признаком pending, сообщение «узел мог выдать»",
              pa.get("pending") and pa.get("cmd") == len(fb.cmds) and "итог живой выдачи неизвестен" in r["message"] and wrote[-1][0] == "items.give")
        fb.outcome = 1
        q0 = audit.query
        audit.query = lambda *a, **k: [{"id": 55, "target": "char:77/1", "result": "ok", "after_json": json.dumps(pa)}]
        try:
            check("М-2: пока итог не пришёл — новая живая выдача этому персонажу отказывает «ещё не подтверждена»",
                  raises(lambda: _ig._live_give(ctx, gp), ops.OpRefused))
            check("М-2: откат до итога — отказ «итог ещё не пришёл»", raises(lambda: _ig._live_give_undo(ctx, pa), ops.OpRefused))
            fb.outcome, fb.give = 2, "given=1;q=2;units=1;plate=1;stop=2;after2231=0;fault=-1;trunc=0;cells=5.0.0"
            st, b = _ig.late_result(pa)
            check("М-2: поздний итог подтянут из журнала моста — выдано 1, ячейка 5", st == "done" and b["cells"] == [[5, 0, 0]]
                  and "выдано 1, ячейки 5" in (_ig.pending_note(json.dumps(pa)) or ""))
            check("М-2: после позднего итога новая живая выдача снова возможна", _ig._live_give(ctx, gp) is not None)
            gw = _GiveW({5: (24893, 0, 683, dict(pa["opts"]))})          # в ячейке — выданное (отпечаток = аргументы выдачи)
            db.GameWriter = lambda name: gw
            _ig._live_give_undo(ctx, pa)
            check("М-2: откат «неизвестной» выдачи — по позднему итогу (ячейка 5)", len(gw.takes) == 1 and gw.takes[0][3] == 5)
            fb.outcome = 3
            check("М-2: узел не выдал — откат «откатывать нечего»", raises(lambda: _ig._live_give_undo(ctx, pa), ops.OpRefused) and len(gw.takes) == 1)
            fb.outcome = 2
        finally:
            audit.query = q0
            db.GameWriter = saved[3]
        # ★ ревизия 29 К-1: отказ узла 20 (сумка не та) / 11 (функции не сошлись) → следующий предпросмотр — «кик + запись»
        fb.outcome, fb.rcode = 3, 20
        check("К-1: отказ узла 20 — отказ с предложением «кик + запись»", raises(lambda: ops.run(ctx, "items.give", dict(gp, expect={"live": ["give", lv["live"]["args"]]})),
                                                                             ops.OpRefused))
        check("К-1: после отказа 20 живой предпросмотр этому персонажу/коду не предлагается", _ig._live_give(ctx, gp) is None)
        _ig._live_off.clear()
        fb.outcome, fb.rcode = 2, 0
        # перенос в своей карте
        lr = _cm._live_row(77, 1, {"Poridx": 3, "Posx": 50, "Posy": 60})
        lr2 = _cm._live_row(77, 1, {"Poridx": 4, "Posx": 50, "Posy": 60})
        check("мост v82: char.move — своя карта → jump, другая → move", lr and lr["_op"] == "jump" and lr2 and lr2["_op"] == "move")
        new = {"Poridx": 3, "Posx": 50, "Posy": 60, "Cporidx": 3}
        prev = {"live": {"node": "GameServer", "uid": 77, "idx": 1, "from_map": 3, "op": "jump"}, "expect": {"before": {}, "after": new, "live": ["jump", 3, 50, 60]}}
        res = _cm.CharMove().apply(ctx, {"uid": 77, "idx": 1}, prev)
        c = fb.cmds[-1]
        check("мост v82: jump узлу map=3;x=50;z=60, итог — клетка сервера 51,60, журнал «живьём»",
              c["op"] == "jump" and c["args"] == "map=3;x=50;z=60" and "клетка 51,60" in res["message"] and res["after"]["live"] and res["after"]["op"] == "jump")
        check("мост v82: живой перенос — отпечаток с ключом live проходит сверку пути, офлайн-отпечаток — нет",
              not raises(lambda: ops._same_path({"expect": prev["expect"]}, prev, None), ops.OpRefused)
              and raises(lambda: ops._same_path({"expect": {"before": {}, "after": new}}, prev, None), ops.OpRefused))
    finally:
        bridge.set_fake(None)
        audit.write, audit.get, audit.mark_undone_by, db.GameWriter, srvtables.charge_cap = saved
        db._pw.pop("BRIDGE_HMAC_KEY", None)


def part_bridge_live():
    """★ А2.2: выбор пути «игрок в игре и узел v81 → живьём; иначе — офлайн/кик + запись», журнал и откат живых правок."""
    from core import bridge
    from domains import live, progress, srvtables, titles  # noqa: F401 — регистрация live.notice
    key = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
    db._pw["BRIDGE_HMAC_KEY"] = key.hex()
    saved = (srvtables.max_level, srvtables.exp_table, titles._fi, audit.write, audit.get, audit.mark_undone_by)
    srvtables.max_level = lambda: 100
    srvtables.exp_table = lambda: {l: l * 1000 for l in range(0, 102)}
    titles._fi = lambda: [[i, 1] for i in range(300)]
    wrote = []
    audit.write = lambda ctx, action, *a, **k: wrote.append((action, k.get("result", "ok"), k.get("after"))) or len(wrote)
    audit.mark_undone_by = lambda *a: None
    ctx = ops.Ctx(1, "selftest", "owner")
    try:
        bridge.set_fake(_FakeLive(ver=80))
        check("мост v81: узел v80 — живого пути нет (live_row None → прежний путь)", bridge.live_row(77, 1) is None)
        fb = _FakeLive()
        bridge.set_fake(fb)
        check("мост v81: узел v81, Mode=1, персонаж виден — живой путь есть", bridge.live_row(77, 1) is not None)
        r = ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 7}, dry=True)
        check("мост v81: char.level_up dry — живьём, уровень по памяти сервера 5 → 7", r["preview"].get("live") and "5 → 7" in r["preview"]["text"]
              and fb.cmds[-1]["op"] == "probe")
        r = ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 7})
        c = fb.cmds[-1]
        check("мост v81: char.level_up — команда exp level=7 узлу, журнал «живьём» с номером команды",
              c["op"] == "exp" and c["args"] == "level=7" and r["result"]["live"] and r["result"]["cmd"] == len(fb.cmds) and not r["dry"])
        check("мост v81: понижение по памяти сервера — отказ", raises(lambda: ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 4}),
                                                                       ops.OpRefused))
        audit.get = lambda aid: {"result": "ok", "undone_by": None, "undo_of": None, "action": "char.level_up", "target": "",
                                 "after_json": json.dumps({"uid": 77, "idx": 1, "live": True})}
        check("мост v81: откат живого уровня — честный отказ «новым действием»", raises(lambda: ops.undo(ctx, 1), ops.OpRefused))
        n0 = len(fb.cmds)
        r = ops.run(ctx, "char.exp_set", {"uid": 77, "idx": 1, "percent": 50})
        check("мост v81: char.exp_set прибавка — живьём exp=5500", fb.cmds[-1]["op"] == "exp" and fb.cmds[-1]["args"] == "exp=5500"
              and len(fb.cmds) == n0 + 2)
        bridge.set_fake(_FakeLive(exp=5900))
        lv = progress.live_exp(ctx, {"uid": 77, "idx": 1, "percent": 50})
        check("мост v81: char.exp_set уменьшение — живого пути нет (→ кик + запись)", lv is None)
        fb = _FakeLive(owned=0)
        bridge.set_fake(fb)
        r = ops.run(ctx, "title.grant", {"uid": 77, "idx": 1, "title": 10})
        check("мост v81: title.grant (звания нет по памяти) — живьём title_add id=10", fb.cmds[-1]["op"] == "title_add"
              and fb.cmds[-1]["args"] == "id=10" and r["result"]["live"])
        audit.get = lambda aid: {"result": "ok", "undone_by": None, "undo_of": None, "action": "title.grant", "target": "",
                                 "after_json": json.dumps(r["result"])}
        ops.undo(ctx, 1)
        check("мост v81: откат живой выдачи — обратной живой командой title_del", fb.cmds[-1]["op"] == "title_del" and fb.cmds[-1]["args"] == "id=10")
        bridge.set_fake(_FakeLive(owned=1))
        check("мост v81: title.grant, звание уже есть по памяти — отказ", raises(lambda: ops.run(ctx, "title.grant", {"uid": 77, "idx": 1, "title": 10}),
                                                                             ops.OpRefused))
        check("мост v81: рейтинговое 65 — отказ и живьём", raises(lambda: ops.run(ctx, "title.grant", {"uid": 77, "idx": 1, "title": 65}), ops.OpRefused))
        fb = _FakeLive(owned=1)
        bridge.set_fake(fb)
        ops.run(ctx, "title.revoke", {"uid": 77, "idx": 1, "title": 11})
        check("мост v81: title.revoke — живьём title_del", fb.cmds[-1]["op"] == "title_del" and fb.cmds[-1]["args"] == "id=11")
        ops.run(ctx, "fame.recalc", {"uid": 77, "idx": 1})
        check("мост v81: fame.recalc — живьём fame_recalc", fb.cmds[-1]["op"] == "fame_recalc")
        r = ops.run(ctx, "live.notice", {"uid": 77, "text": "Привет", "rgb": [1, 2, 3]})
        check("мост v81: live.notice — notice r=1;g=2;b=3;text=Привет узлу персонажа", fb.cmds[-1]["op"] == "notice"
              and fb.cmds[-1]["args"] == "r=1;g=2;b=3;text=Привет")
        bridge.set_fake(_FakeLive(ver=80))
        check("мост v81: live.notice на узле v80 — отказ", raises(lambda: ops.run(ctx, "live.notice", {"uid": 77, "text": "x"}), ops.OpRefused))
        # ★ ревизия 25 М-2: подтверждённый живой предпросмотр и путь применения — одни и те же
        fb = _FakeLive()
        bridge.set_fake(fb)
        pv = ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 7}, dry=True)["preview"]
        fb.snap["lvl"] = 6
        n0 = len(fb.cmds)
        check("мост r25: уровень сменился после предпросмотра — отказ «повторите», команды exp нет",
              raises(lambda: ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 7, "expect": pv["expect"]}), ops.OpRefused)
              and not any(c["op"] == "exp" for c in fb.cmds[n0:]))
        fb.snap["lvl"] = 5
        r = ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 7, "expect": pv["expect"]})
        check("мост r25: тот же отпечаток — живая правка проходит", fb.cmds[-1]["op"] == "exp" and r["result"]["live"])
        check("мост r25: офлайн-предпросмотр, а путь стал живым — отказ", raises(lambda: ops.run(
            ctx, "title.grant", {"uid": 77, "idx": 1, "title": 10, "expect": [["CharFame", [77, 1], None, 1]]}), ops.OpRefused))
        pv = ops.run(ctx, "title.grant", {"uid": 77, "idx": 1, "title": 10}, dry=True)["preview"]
        fb.present = []
        n0 = len(fb.cmds)
        check("мост r25: живой предпросмотр, а игрок вышел — отказ «повторите», не «кик + запись» без предупреждения",
              raises(lambda: ops.run(ctx, "title.grant", {"uid": 77, "idx": 1, "title": 10, "expect": pv["expect"]}), ops.OpRefused)
              and not any(c["op"] == "kick" for c in fb.cmds[n0:]))
        # ★ ревизия 25 М-3: класс, «найдено», 256+
        bridge.set_fake(_FakeLive(found=0))
        check("мост r25: звание не «найдено» — живого пути нет (→ офлайн / кик + запись)",
              titles._live_title(ctx, {"uid": 77, "idx": 1, "title": 10}, "grant") is None)
        bridge.set_fake(_FakeLive())
        check("мост r25: звание 256+ — живого пути нет", titles._live_title(ctx, {"uid": 77, "idx": 1, "title": 260}, "grant") is None)

        class _R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def one(self, sql, params=()):
                return {"Class": 1}
        saved_names, saved_gr = titles.names, titles.db.GameReader
        titles.names = lambda: {10: (10, "x", 3)}
        titles.db.GameReader = lambda key: _R()
        try:
            check("мост r25: звание другого класса — тот же отказ, что офлайн", raises(
                lambda: titles._live_title(ctx, {"uid": 77, "idx": 1, "title": 10}, "grant"), ops.OpRefused))
        finally:
            titles.names, titles.db.GameReader = saved_names, saved_gr
        # ★ ревизия 25 К-1: на потолке — отказ, как у сервера
        bridge.set_fake(_FakeLive(lvl=100, exp=100500, cap=100))
        check("мост r25: опыт на потолке уровня — отказ (сервер опыт не копит)", raises(
            lambda: progress.live_exp(ctx, {"uid": 77, "idx": 1, "percent": 50}), ops.OpRefused))
        bridge.set_fake(_FakeLive(outcome=3))
        check("мост v81: отказ узла живой правки — отказ операции", raises(lambda: ops.run(ctx, "char.level_up", {"uid": 77, "idx": 1, "level": 7}),
                                                                         ops.OpRefused))
    finally:
        (srvtables.max_level, srvtables.exp_table, titles._fi, audit.write, audit.get, audit.mark_undone_by) = saved
        bridge.set_fake(None)
        db._pw.pop("BRIDGE_HMAC_KEY", None)


def _bridge_sql():
    """sql/adminc_07_bridge.sql на временной базе LocalDB: захват ровно одним узлом, итог только своей захваченной, права asda_bridge;
    core/bridge.py (_Sql) читает узлы и присутствие."""
    import pyodbc
    from core import bridge
    name = "AsdaBridgeSelftest_" + secrets.token_hex(4)
    try:
        m = _ldb("master")
    except pyodbc.Error as ex:
        return check("мост SQL: LocalDB доступна", False, ex)
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    try:
        cn = _ldb(name)
        text = open(os.path.join(ROOT, "sql", "adminc_07_bridge.sql"), encoding="utf-8").read()
        text = text.replace("$(BridgePw)", "Aa1-" + secrets.token_hex(12)).replace("$(BridgeDb)", name)
        for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
            if batch.strip():
                cn.cursor().execute(batch)
        check("мост SQL: adminc_07 на LocalDB", True)
        cur = cn.cursor()
        cur.execute("EXEC adm.BridgeNodeStart 'GameServer', 11, 80, 1, 1")
        cur.execute("EXEC adm.BridgeNodeStart 'Ch2_GameServer', 12, 80, 1, 1")
        cur.execute("EXEC adm.BridgePresenceSet 'GameServer', 5, 77, 1, 77, N'Тест', 3, 10, 20")
        ids = []
        for idx in (1, 1, 2):
            cur.execute("SET NOCOUNT ON; DECLARE @id BIGINT, @dl BIGINT = DATEDIFF(second, '19700101', SYSUTCDATETIME()) + 30; EXEC adm.BridgeEnqueue ?, 'kick', 77, ?, NULL, N'', 30, ?, N'st', NULL, @dl, @id OUTPUT; "
                        "SELECT @id", str(uuid.uuid4()), idx, "0" * 64)
            ids.append(int(cur.fetchone()[0]))
        other = cur.execute("EXEC adm.BridgeClaim 'Ch2_GameServer', 16").fetchall()
        mine = cur.execute("EXEC adm.BridgeClaim 'GameServer', 16").fetchall()
        again = cur.execute("EXEC adm.BridgeClaim 'GameServer', 16").fetchall()
        check("мост SQL: захват — только узел, где цель в игре; ровно один раз",
              not other and [int(r[0]) for r in mine] == ids[:2] and not again)
        check("мост SQL: захват отдаёт подписанный срок (11-й столбец, UNIX UTC)", all(len(r) == 11 and int(r[10]) > 1700000000 for r in mine))
        check("мост SQL: срок вне «сейчас…+300 с» — отказ процедуры", raises(lambda: cur.execute(
            "DECLARE @id BIGINT; EXEC adm.BridgeEnqueue ?, 'kick', 77, 1, NULL, N'', 30, ?, N'st', NULL, 100, @id OUTPUT",
            str(uuid.uuid4()), "0" * 64)))
        n1 = cur.execute("EXEC adm.BridgeResult ?, 'GameServer', 2, 0, N'ok'", ids[0]).fetchone()[0]
        n2 = cur.execute("EXEC adm.BridgeResult ?, 'GameServer', 2, 0, N'ok'", ids[0]).fetchone()[0]
        n3 = cur.execute("EXEC adm.BridgeResult ?, 'Ch2_GameServer', 2, 0, N'ok'", ids[1]).fetchone()[0]
        check("мост SQL: итог — один раз и только захватившим узлом", n1 == 1 and n2 == 0 and n3 == 0)
        check("мост SQL: неизвестная команда — отказ процедуры", raises(lambda: cur.execute(
            "DECLARE @id BIGINT, @dl BIGINT = DATEDIFF(second, '19700101', SYSUTCDATETIME()) + 30; EXEC adm.BridgeEnqueue ?, 'drop', 77, 1, NULL, N'', 30, ?, N'st', NULL, @dl, @id OUTPUT",
            str(uuid.uuid4()), "0" * 64)))
        def twice():
            for _ in range(2):
                cur.execute("DECLARE @id BIGINT, @dl BIGINT = DATEDIFF(second, '19700101', SYSUTCDATETIME()) + 30; EXEC adm.BridgeEnqueue ?, 'kick', 77, 1, NULL, N'', 30, ?, N'st', NULL, @dl, @id OUTPUT",
                            "00000000-0000-4000-8000-000000000009", "0" * 64)
        check("мост SQL: повтор nonce — отказ (UNIQUE)", raises(twice))
        cur.execute("EXECUTE AS USER = 'asda_bridge'")
        deny_sel = raises(lambda: cur.execute("SELECT COUNT(*) FROM adm.bridge_cmd").fetchall())
        deny_enq = raises(lambda: cur.execute("DECLARE @id BIGINT, @dl BIGINT = DATEDIFF(second, '19700101', SYSUTCDATETIME()) + 30; EXEC adm.BridgeEnqueue ?, 'kick', 77, 1, NULL, N'', 30, ?, N'st', NULL, @dl, @id OUTPUT",
                                              str(uuid.uuid4()), "0" * 64))
        cur.execute("REVERT")
        cur.execute("EXECUTE AS USER = 'asda_bridge'")
        ok_claim = not raises(lambda: cur.execute("EXEC adm.BridgeClaim 'GameServer', 1").fetchall())
        cur.execute("REVERT")
        check("мост SQL: asda_bridge — только процедуры узла (таблицы и BridgeEnqueue закрыты)", deny_sel and deny_enq and ok_claim)
        cn.close()
        db.set_override("admin", lambda database: _ldb(name))
        try:
            nd = {n["node"]: n for n in bridge.nodes()}
            pr = bridge.presence(77)
            check("мост: панель читает узлы (пульс свежий) и присутствие", nd.get("GameServer", {}).get("fresh") and len(pr) == 1
                  and pr[0]["charname"] == "Тест" and bridge.available(1))
        finally:
            db.set_override("admin", None)
    finally:
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
            m.cursor().execute("IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'asda_bridge') DROP LOGIN [asda_bridge]")
        except pyodbc.Error as ex:
            print("! временная база %s не удалена: %s" % (name, ex))
        m.close()


def part_tls():
    """Служба с TLS: страница по HTTPS, Secure у cookie, мусор вместо рукопожатия не роняет и не держит приём."""
    import socket
    import ssl
    import tempfile
    try:
        sys.path.insert(0, os.path.join(ROOT, "deploy"))
        import deploy_admin_center as dep
    except ImportError as ex:
        return check("TLS: модуль выкладки", False, ex)
    try:
        crt, key = dep.make_tls_cert("selftest")
    except ImportError:                             # нет pip cryptography (на сервере его нет) — часть пропускается
        print("-- TLS: пропуск (нет pip cryptography; на ПК, откуда идёт выкладка, он есть)")
        return None
    from api import server
    cfg = config.get()
    saved = (cfg.bind_host, cfg.bind_port, cfg.tls_cert, cfg.tls_key)
    cfg.tls_cert, cfg.tls_key = crt, key
    srv = None
    try:
        ctx = server.tls_context(cfg)
        check("TLS: контекст из сертификата", ctx is not None)
        srv = server.Server(("127.0.0.1", 0), server.Handler)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
        cfg.bind_host, cfg.bind_port = "127.0.0.1", srv.server_address[1]
        server._tls_active = True
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
        port = cfg.bind_port
        hang = socket.create_connection(("127.0.0.1", port))          # клиент, который молчит (не шлёт ClientHello)
        junk = socket.create_connection(("127.0.0.1", port))
        junk.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")             # обычный HTTP на порт HTTPS
        cli = ssl.create_default_context(cafile=crt)
        cli.check_hostname = False                                    # имя 127.0.0.1 есть в SAN, но проверяем цепочку
        t0 = time.time()
        c = http.client.HTTPSConnection("127.0.0.1", port, timeout=10, context=cli)
        c.request("GET", "/", headers={"Host": "127.0.0.1:%d" % port})
        r = c.getresponse()
        body = r.read()
        check("TLS: страница по HTTPS при молчащем клиенте", r.status == 200 and b"<html" in body and time.time() - t0 < 5,
              (r.status, round(time.time() - t0, 1)))
        check("TLS: сертификат проходит проверку цепочки", c.sock.getpeercert() is not None)
        c.close()
        check("TLS: cookie сессии с Secure (настоящая функция Set-Cookie)",
              server.session_cookie("t", 5).endswith("; Secure") and "HttpOnly" in server.session_cookie("", 0))
        p = socket.create_connection(("127.0.0.1", port), timeout=5)
        p.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")       # обычный HTTP на порт HTTPS
        try:
            got = p.recv(100)
        except (ConnectionError, socket.timeout):
            got = b""
        p.close()
        check("TLS: обычный HTTP на порту HTTPS — без ответа HTTP", not got.startswith(b"HTTP/"), got[:20])
        old = ssl.create_default_context(cafile=crt)
        old.check_hostname = False
        old.minimum_version = old.maximum_version = ssl.TLSVersion.TLSv1_1
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw_s:
                with old.wrap_socket(raw_s):
                    tls11 = True
        except (ssl.SSLError, OSError):
            tls11 = False
        check("TLS: версия ниже 1.2 отвергается", not tls11)
        hang.close()
        junk.close()
        timers0 = sum(1 for t in threading.enumerate() if isinstance(t, threading.Timer))
        for _ in range(5):                                            # мусор вместо ClientHello — рукопожатие рвётся
            with socket.create_connection(("127.0.0.1", port)) as z:
                z.sendall(b"\x16\x03\x01\x00\x05hello")
                try:
                    z.recv(10)
                except OSError:
                    pass
        time.sleep(0.5)
        timers1 = sum(1 for t in threading.enumerate() if isinstance(t, threading.Timer))
        check("TLS: сорванное рукопожатие не оставляет таймер сторожа", timers1 <= timers0, (timers0, timers1))
        time.sleep(0.3)
        check("TLS: счётчик соединений вернулся к нулю", not srv._conn, dict(srv._conn))
        cfg.tls_cert = cfg.tls_key = os.path.join(tempfile.gettempdir(), "asda_no_such_cert.pem")
        saved_tls = cfg.tls
        cfg.tls = True
        try:
            check("serve(): без сертификата не стартует (SystemExit)", raises(lambda: server.serve("127.0.0.1", 0), SystemExit))
        finally:
            cfg.tls = saved_tls
    finally:
        server._tls_active = False
        cfg.bind_host, cfg.bind_port, cfg.tls_cert, cfg.tls_key = saved
        if srv:
            srv.shutdown()
            srv.server_close()
        for f in (crt, key):
            if os.path.exists(f):
                os.remove(f)


# ------------------------------------------------------------------ B. служба на LocalDB

LOCALDB = r"(localdb)\MSSQLLocalDB"


def _ldb(database):
    import pyodbc
    return pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=%s;DATABASE=%s;Trusted_Connection=yes;" %
                          (LOCALDB, database), autocommit=True, timeout=30)


def _run_sql_file(cn, path):
    """Выполнить файл T-SQL по пакетам GO."""
    text = open(path, encoding="utf-8").read()
    for batch in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I):
        if batch.strip():
            cn.cursor().execute(batch)


class Client:
    """HTTP-клиент самотеста: cookie сессии и CSRF."""

    def __init__(self, port):
        self.port = port
        self.cookie = None
        self.csrf = ""

    def req(self, method, path, body=None, csrf=True, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        hd = {"Host": host or "127.0.0.1:%d" % self.port}
        if self.cookie:
            hd["Cookie"] = self.cookie
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hd["Content-Type"] = "application/json"
            if csrf:
                hd["X-Asda-Csrf"] = "login" if path == "/api/login" else self.csrf
        c.request(method, path, body=data, headers=hd)
        r = c.getresponse()
        raw = r.read()
        sc = r.getheader("Set-Cookie")
        if sc:
            v = sc.split(";", 1)[0]
            self.cookie = None if v.endswith("=") else v
        try:
            j = json.loads(raw.decode("utf-8"))
        except ValueError:
            j = {"_raw": raw[:200]}
        return r.status, j, r

    def login(self, login, pw, code=""):
        st, j, _ = self.req("POST", "/api/login", {"login": login, "password": pw, "totp_code": code})
        if st == 200 and j.get("csrf"):
            self.csrf = j["csrf"]
        return st, j


def part_b():
    import pyodbc
    name = "AsdaAdminSelftest_" + secrets.token_hex(4)
    try:
        m = _ldb("master")
    except pyodbc.Error as ex:
        return check("LocalDB доступна", False, ex)
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    try:
        cn = _ldb(name)
        _run_sql_file(cn, os.path.join(ROOT, "sql", "adminc_02_schema.sql"))
        cn.close()
        check("схема adminc_02 на LocalDB", True)
        db.set_override("admin", lambda database: _ldb(name))
        db._pw["TOTP_KEY"] = os.urandom(32).hex()
        auth.PW_ITER_SAVE = auth.PW_ITER
        _flow(name)
    finally:
        db.set_override("admin", None)
        db._pw.pop("TOTP_KEY", None)
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
        except pyodbc.Error as ex:
            print("! временная база %s не удалена: %s" % (name, ex))
        m.close()


def _flow(dbname):
    from api import server
    from domains import load_all
    load_all()
    cfg = config.get()
    cfg.bind_host, cfg.login_fail_limit = "127.0.0.1", 5
    srv = server.Server(("127.0.0.1", 0), server.Handler)
    _SRV[:] = [srv]
    cfg.bind_port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    th.start()
    try:
        _flow_body(cfg.bind_port)
    finally:
        srv.shutdown()
        srv.server_close()


def _flow_body(port):
    cli = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    own_pw, gm_pw = "Owner-Pass-" + secrets.token_hex(4), "Gm-Pass-" + secrets.token_hex(4)
    r = ops.run(cli, "users.create", {"login": "owner1", "role": "owner", "password": own_pw})
    check("консоль: создан владелец", r["ok"] and r["audit_id"])
    check("консоль: дубль логина — отказ", raises(lambda: ops.run(cli, "users.create",
                                                                   {"login": "owner1", "role": "gm", "password": own_pw}), ops.OpRefused))
    c = Client(port)
    st, j, _ = c.req("GET", "/api/me")
    check("без входа → 401", st == 401)
    st, j, _ = c.req("GET", "/api/me", host="evil.example:%d" % port)
    check("чужой Host → 421", st == 421)
    st, j, _ = c.req("POST", "/api/login", {"login": "owner1", "password": own_pw}, csrf=False)
    check("вход без X-Asda-Csrf → 403", st == 403)
    st, j = c.login("owner1", "wrong-password-1")
    wrong_msg = j.get("error", "")
    check("неверный пароль → 403", st == 403 and "неверный" in wrong_msg)
    st, j = c.login("nobody", "wrong-password-1")
    check("нет пользователя → тот же ответ", st == 403 and j.get("error") == wrong_msg)
    st, j = c.login("owner1", own_pw)
    check("вход владельца", st == 200 and j.get("need_totp_setup") is True and c.cookie)
    st, j, _ = c.req("GET", "/api/status")
    check("без 2FA разделы закрыты → 403", st == 403 and "второй фактор" in j.get("error", ""))
    st, j, _ = c.req("POST", "/api/self/totp/begin", {}, csrf=False)
    check("POST без CSRF → 403", st == 403)
    st, j, _ = c.req("POST", "/api/self/totp/begin", {})
    check("2FA: секрет и QR выданы", st == 200 and j.get("secret") and j.get("uri", "").startswith("otpauth://")
          and len(j.get("qr") or []) >= 21 and len(j["qr"]) == len(j["qr"][0]))
    import base64
    sec = base64.b32decode(j["secret"] + "=" * (-len(j["secret"]) % 8))
    st, j, _ = c.req("POST", "/api/self/totp/enable", {"totp_code": "000000" if auth.totp_check(sec, "111111") else "111111"})
    check("2FA: неверный код → отказ", st == 409)
    enable_code = auth.totp_code(sec, int(time.time() // 30))   # тот же код — ниже, «уже использован» (не пересчитывать: шаг мог смениться)
    st, j, _ = c.req("POST", "/api/self/totp/enable", {"totp_code": enable_code})
    check("2FA: включён", st == 200 and j.get("ok"))
    st, j, _ = c.req("POST", "/api/logout", {})
    check("выход", st == 200 and not c.cookie)
    st, j = c.login("owner1", own_pw)
    check("после 2FA вход без кода → тот же общий отказ (пароль не подтверждается)",
          st == 403 and j.get("error") == wrong_msg and "need_totp" not in j and not c.cookie)
    auth.clear_locks("owner1")
    st, j = c.login("owner1", own_pw, "123")
    check("неверный код → 403 (тот же ответ)", st == 403 and j.get("error") == wrong_msg)
    auth.clear_locks("owner1")
    st, j = Client(port).login("owner1", own_pw, enable_code)
    check("код включения 2FA уже использован → 403", st == 403)
    used = auth.totp_code(sec, int(time.time() // 30) + 1)      # следующий шаг (окно ±1)
    st, j = c.login("owner1", own_pw, used)
    check("вход с кодом", st == 200 and j.get("need_totp_setup") is False)
    st, j = Client(port).login("owner1", own_pw, used)
    check("тот же код второй раз → 403 (одноразовый)", st == 403 and j.get("error") == wrong_msg)
    st, j, _ = c.req("GET", "/api/me")
    check("/api/me: права владельца", st == 200 and "users.manage" in j.get("perms", []))
    st, j, _ = c.req("POST", "/api/ops/users.create", {"params": {"login": "gm1", "role": "gm", "password": gm_pw}, "dry": True})
    check("операция: предпросмотр без записи", st == 200 and j.get("dry") and not j.get("audit_id"))
    st, j, _ = c.req("POST", "/api/ops/users.create", {"params": {"login": "gm1", "role": "gm", "password": gm_pw}})
    check("операция: создан GM", st == 200 and j.get("audit_id"))
    st, j, _ = c.req("POST", "/api/ops/users.create", {"params": {"login": "gm2", "role": "gm", "password": "short"}})
    check("операция: плохой пароль → 409", st == 409)
    st, j, _ = c.req("POST", "/api/ops/users.set_role", {"params": {"login": "gm1", "role": "support"}})
    rid = j.get("audit_id")
    check("смена роли", st == 200 and j["result"]["role"] == "support")
    st, j, _ = c.req("POST", "/api/ops/users.set_role", {"params": {"login": "owner1", "role": "gm"}})
    check("последнего владельца не понизить", st == 409)
    st, j, _ = c.req("GET", "/api/audit?action=users.")
    row = next((x for x in j.get("items", []) if x["id"] == rid), None)
    check("журнал: запись смены роли, откатываемая", row and row["reversible"] and row["login"] == "owner1")
    check("журнал: пароль вычищен", all("Gm-Pass" not in (x.get("params") or "") for x in j.get("items", [])))
    st, j, _ = c.req("POST", "/api/audit/%d/undo" % rid, {})
    check("откат через журнал", st == 200 and j["result"]["role"] == "gm")
    st, j, _ = c.req("POST", "/api/audit/%d/undo" % rid, {})
    check("повторный откат → 409", st == 409)
    st, j, _ = c.req("POST", "/api/ops/self.password", {"params": {}})
    check("self.* через /api/ops → 404", st == 404)
    st, j, _ = c.req("POST", "/api/ops/users.set_disabled", {"params": {"login": "owner1", "disabled": True}})
    check("себя не отключить", st == 409)
    g = Client(port)
    st, j = g.login("gm1", gm_pw)
    check("вход GM (2FA не обязателен)", st == 200 and j.get("need_totp_setup") is False)
    cn = db.admin()
    try:
        check("GM без 2FA снаружи VPN/частной сети — отказ тем же ответом",
              raises(lambda: auth.authenticate(cn, "gm1", gm_pw, "", "203.0.113.5"), auth.AuthError))
    finally:
        cn.close()
    auth.clear_locks("gm1")
    check("доверенные: только VPN и локальный; домашняя сеть (возможный SNAT роутера) и внешний — нет",
          auth.trusted_ip("100.95.42.54") and auth.trusted_ip("127.0.0.1") and auth.trusted_ip("::ffff:100.64.0.1")
          and not auth.trusted_ip("192.168.1.1") and not auth.trusted_ip("10.0.0.1") and not auth.trusted_ip("@@ASTORY_SERVER_WAN_IP@@")
          and not auth.trusted_ip("8.8.8.8") and not auth.trusted_ip("bad"))
    auth._user_tries.clear()
    hits = [auth._user_window_hit("victim", "198.51.100.%d" % i) for i in range(auth.USER_WINDOW_MAX + 1)]
    check("окно на логин: со многих внешних адресов не больше USER_WINDOW_MAX попыток",
          hits[-1] and not any(hits[:-1]), hits)
    check("окно на логин не действует из VPN (владельца снаружи не запереть)", not auth._user_window_hit("victim", "100.95.42.54"))
    auth._user_tries.clear()
    st, j, _ = g.req("GET", "/api/users")
    check("GM: пользователи панели закрыты → 403", st == 403)
    st, j, _ = g.req("POST", "/api/ops/users.create", {"params": {"login": "x1", "role": "owner", "password": gm_pw}})
    check("GM: операция владельца → 409", st == 409 and "нет права" in j.get("error", ""))
    g2 = Client(port)
    g2.login("gm1", gm_pw)
    st, j, _ = g.req("POST", "/api/self/password", {"old_password": gm_pw, "new_password": gm_pw + "-2"})
    check("GM: смена своего пароля", st == 200)
    check("смена пароля гасит другие сессии, своя жива", g2.req("GET", "/api/me")[0] == 401 and g.req("GET", "/api/me")[0] == 200)
    st, j, _ = c.req("POST", "/api/ops/users.set_disabled", {"params": {"login": "gm1", "disabled": True}})
    check("отключение GM", st == 200)
    st, j, _ = g.req("GET", "/api/me")
    check("отключённый: сессия погашена → 401", st == 401)
    from api import server as _srv
    _srv._rate.clear()                         # предел попыток с IP (10/мин) проверяется отдельно ниже
    st, j = g.login("gm1", gm_pw + "-2")
    check("отключённый: вход закрыт", st == 403 and "отключена" in j.get("error", ""))
    c.req("POST", "/api/ops/users.set_disabled", {"params": {"login": "gm1", "disabled": False}})
    from api import server
    server._rate.clear()                       # предел попыток с IP проверяется отдельно ниже
    for _ in range(5):
        g.login("gm1", "bad-password-0")
    st, j = g.login("gm1", gm_pw + "-2")
    check("замок после 5 неудач (и верный пароль не пускает, ответ тот же)", st == 403 and j.get("error") == wrong_msg)
    check("замок — только для пары логин+IP (чужой адрес не запирает)", auth._locked("gm1", "127.0.0.1")
          and not auth._locked("gm1", "100.64.0.9"))
    server._rate.clear()
    codes = [g.login("gm1", "bad-password-0")[0] for _ in range(server.LOGIN_RATE + 1)]
    check("предел попыток входа с IP → 429", codes[-1] == 429 and 429 not in codes[:-1], codes)
    server._rate.clear()
    st, j, r = c.req("GET", "/")
    check("статика: панель", st == 200 and r.getheader("Content-Security-Policy", "").startswith("default-src 'self'"))
    st, j, _ = c.req("GET", "/..%2f..%2fcore%2fdb.py")
    check("статика: обход каталога → 404", st == 404)
    st, j, _ = c.req("GET", "/app.js::$DATA")
    check("статика: поток NTFS → 404", st == 404)
    st, j, _ = Client(port).req("GET", "/ref/atlas/x.png")
    check("атлас без входа → 401", st == 401)
    from domains import refdata
    name = next(iter(refdata._load("atlases.json")), None)
    if name:
        st, j, r = c.req("GET", "/ref/atlas/%s.png" % name)
        check("атлас с входом", st == 200 and r.getheader("Content-Type") == "image/png")
    st, j, _ = c.req("POST", "/api/ops/users.create", {"params": {}}, host=None)
    check("операция без параметров → 409", st == 409)
    big = {"x": "a" * (70 * 1024)}
    st, j, _ = c.req("POST", "/api/ops/users.create", big)
    check("большое тело → 413", st == 413)
    _raw_checks(port)


def _raw(port, data, wait=5.0):
    """Сырые байты в службу → ответ (b'' — соединение закрыто без ответа)."""
    import socket
    s = socket.create_connection(("127.0.0.1", port), timeout=wait)
    try:
        if data:
            s.sendall(data)
        out = b""
        while True:
            try:
                ch = s.recv(65536)
            except (socket.timeout, ConnectionError):
                break
            if not ch:
                break
            out += ch
            if b"\r\n\r\n" in out and b"Content-Length" in out:
                head, _, body = out.partition(b"\r\n\r\n")
                n = int(re.search(rb"Content-Length: (\d+)", head).group(1))
                if len(body) >= n:
                    break
        return out
    finally:
        s.close()


def _raw_checks(port):
    """Ревизия 16.11 вечер: С1 (Content-Length), В1 (пределы соединений, сторож медленного клиента)."""
    import socket
    from api import server
    head = "POST /api/login HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Asda-Csrf: login\r\nContent-Type: application/json\r\n" % port
    t0 = time.time()
    r = _raw(port, (head + "Content-Length: -1\r\n\r\n").encode() + b"x" * 100000, wait=5)
    check("Content-Length: -1 → 400 сразу (тело не читается до конца соединения)",
          r.startswith(b"HTTP/1.1 400") and time.time() - t0 < 3, r[:40])
    r = _raw(port, (head + "Content-Length: abc\r\n\r\n").encode())
    check("Content-Length: мусор → 400", r.startswith(b"HTTP/1.1 400"), r[:40])
    r = _raw(port, (head + "Content-Length: ²\r\n\r\nGET / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % port).encode("latin-1"))
    check("Content-Length: не-ASCII цифра → 400 и одно соединение = один ответ",
          r.startswith(b"HTTP/1.1 400") and r.count(b"HTTP/1.1 ") == 1, r[:40])
    r = _raw(port, (head + "Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n").encode())
    check("Transfer-Encoding → 411", r.startswith(b"HTTP/1.1 411"), r[:40])
    r = _raw(port, ("POST /api/login HTTP/1.1\r\nHost: evil.example:%d\r\nContent-Length: 5\r\n\r\n"
                    "GET / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % (port, port)).encode())
    check("421 закрывает соединение (тело не становится следующим запросом)",
          r.startswith(b"HTTP/1.1 421") and r.count(b"HTTP/1.1 ") == 1, r[:60])
    held = [socket.create_connection(("127.0.0.1", port)) for _ in range(server.MAX_CONN_IP)]
    try:
        time.sleep(0.3)
        extra = socket.create_connection(("127.0.0.1", port), timeout=3)
        extra.sendall(("GET / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % port).encode())
        try:
            got = extra.recv(100)
        except (ConnectionError, socket.timeout):
            got = b""
        extra.close()
        check("предел соединений с адреса: лишнее закрывается без ответа", got == b"", got[:40])
    finally:
        for x in held:
            x.close()
    time.sleep(0.5)
    saved = server.HEADER_DEADLINE_S
    server.HEADER_DEADLINE_S = 1
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1")                  # заголовок «по байту» и замолчал
        t0 = time.time()
        try:
            got = s.recv(100)
        except (ConnectionError, socket.timeout):
            got = b"timeout"
        s.close()
        check("сторож: недосланный запрос рвётся по сроку", got == b"" and time.time() - t0 < 4, (got[:20], round(time.time() - t0, 1)))
    finally:
        server.HEADER_DEADLINE_S = saved
    time.sleep(0.5)
    check("счётчик соединений вернулся к нулю (нет утечки)", not _SRV[0]._conn, dict(_SRV[0]._conn))
    st, j, r = Client(port).req("GET", "/skin/win_mg.png")
    check("скин отдаётся и кэшируется", st == 200 and "max-age" in (r.getheader("Cache-Control") or ""))


# ------------------------------------------------------------------ C. живые базы

def part_live():
    from domains import feed, load_all, players, status
    load_all()
    with db.GameReader("joy1") as j:
        cur = j.cn.cursor()
        text = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
        cur.execute(text)
        rows = cur.fetchall()
    bad = [(r[0], r[1], r[2]) for r in rows if (r[1] or 0) != r[2]]
    check("права asda_admin (adminc_10_verify)", not bad and len(rows) >= 21, bad)
    check("запись в игровую базу запрещена", raises(lambda: db.GameReader("joy1").cn.cursor().execute(
        "UPDATE Charinfo SET Lvl = Lvl WHERE 1 = 0")))
    s = status.snapshot(force=True)
    check("состояние: снимок процессов", not s["host_error"] and s["summary"]["total"] == len(status.STACK), s["host_error"])
    check("состояние: игроки по БД", s["players"]["error"] == "", s["players"]["error"])
    found = players.search("sitx", net=True)
    check("поиск «sitx»", any(a["Userindex"] == 1 for a in found), [a["Userindex"] for a in found])
    acc = players.account(1, net=True)
    check("карточка учётки 1", acc["account"]["Userindex"] == 1 and acc["chars"] and acc["net"] is not None)
    ch = players.character(1, 10)
    check("карточка персонажа 1/10", ch["char"]["Charname"] == "GM_sitxovski" and ch["bags"], ch["char"].get("Charname"))
    named = [i for b in ch["bags"] for i in b["items"] if i["name"]]
    check("предметы с названиями и иконками", named and any(i["icon"] for i in named))
    fd = feed.feed(1, 10, days=3650, limit=200)
    check("лента 1/10 по журналам", fd["total"] > 0 and not fd["errors"], fd["errors"][:3])
    check("каталог журналов", len(feed.catalog()) >= 230, len(feed.catalog()))
    some = next((i["Uuid"] for b in ch["bags"] for i in b["items"] if i.get("Uuid")), None)
    if some:
        tr = feed.trace(str(some))
        check("след предмета", tr["now"]["item"] and not tr["errors"], tr["errors"][:3])
    ru = [c for c in acc["chars"] if re.search("[А-Яа-я]", c["Charname"] or "")]
    check("кириллица в именах читается (если есть)", True if not ru else all("?" not in c["Charname"] for c in ru))
    _live_block()
    _live_online()
    _live_rename()
    _live_level()
    _live_jobchange()
    _live_password()
    _live_accounts()
    _live_restore()
    _live_move()
    _live_give()
    _live_post()
    _live_titles()
    _live_skills()
    _live_quests()
    _live_charrest()
    _live_charcopy()
    _live_soulmate()
    _live_friends()
    _live_clan()
    _live_recover()
    from domains import items as _it
    with db.GameReader("joy1") as _r:
        _ok, _why = _it.online_state(_it._ReaderAdapter(_r), 1)
    if not _ok:
        print("     (учётка 1 в игре — запись предметов не проверяется: %s)" % _why)
        check("предметы: запись при игроке в игре — отказ", raises(lambda: ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"),
              "gold.set", {"uid": 1, "idx": 10, "amount": 1}, dry=True), ops.OpRefused))
    else:
        _live_items()


def _live_items():
    """Волна А1: список игроков, правила предметов (как у сервера), запись и откат через журнал (персонаж не в игре)."""
    from domains import items, players
    lst = players.list_accounts(1)
    check("список игроков: страница 20, всего > 0", lst["total"] > 0 and len(lst["items"]) == min(20, lst["total"]) and lst["pages"] >= 1,
          (lst["total"], len(lst["items"])))
    l2 = players.list_accounts(2) if lst["pages"] > 1 else None
    check("список игроков: страницы не пересекаются", not l2 or not ({a["Userindex"] for a in lst["items"]} & {a["Userindex"] for a in l2["items"]}))
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("joy1") as r:
        rows = r.rows("SELECT Code, Plate, Posx FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate IN (1, 2, 3)")
    eq = {x["Posx"]: x for x in rows if x["Plate"] == 3}
    b1 = sorted((x for x in rows if x["Plate"] == 1), key=lambda x: x["Posx"])
    used1 = {x["Posx"] for x in b1}
    with db.GameReader("joy1") as r:
        cap1 = items._load(items._ReaderAdapter(r), 1, 10, False)[2][1]          # ёмкость сумки 1 — как у службы
    pv = lambda p: ops.run(ctx, "items.move", p, dry=True)["preview"]
    if b1:
        free = next(x for x in range(cap1) if x not in used1)
        p = pv({"uid": 1, "idx": 10, "src": {"plate": 1, "posx": b1[0]["Posx"]}, "dst": {"plate": 1, "posx": free}})
        check("предметы: предпросмотр переставить", p["kind"] == "move" and p["moves"][0]["to"] == [1, free])
        check("предметы: 1 → 2 запрещено (как у сервера)", raises(lambda: pv({"uid": 1, "idx": 10, "src": {"plate": 1, "posx": b1[0]["Posx"]},
                                                                            "dst": {"plate": 2, "posx": 59}}), ops.OpRefused))
    cons = next((x for x in rows if x["Plate"] in (1, 2) and (srvtables_type(x["Code"]) == 11)), None)
    if cons:
        try:
            pv({"uid": 1, "idx": 10, "src": {"plate": cons["Plate"], "posx": cons["Posx"]}, "dst": {"plate": 3}})
            check("предметы: расходник не надевается (код 12)", False)
        except ops.OpRefused as ex:
            check("предметы: расходник не надевается (код 12)", "код 12" in str(ex), str(ex))
    if 9 in eq:
        p = pv({"uid": 1, "idx": 10, "src": {"plate": 3, "posx": 9}, "dst": {"plate": 0}})
        check("предметы: снять оружие — в родную сумку 1", p["kind"] == "unequip" and p["moves"][-1]["to"][0] == 1)
    if 5 in eq:
        p = pv({"uid": 1, "idx": 10, "src": {"plate": 3, "posx": 5}, "dst": {"plate": 0}})
        check("предметы: снять кольцо двойным щелчком — в его сумку 2, первую свободную", p["moves"][0]["to"][0] == 2)
    # запись и откат: только если учётка не в игре (иначе сервер держит инвентарь в памяти — не трогаем)
    with db.GameReader("joy1") as r:
        ok, why = items.online_state(items._ReaderAdapter(r), 1)
    if not ok or not b1:
        print("-- предметы: запись/откат пропущены (%s)" % (why or "нет предметов"))
        return
    src = b1[-1]["Posx"]
    free = next(x for x in range(cap1) if x not in used1)
    res = ops.run(ctx, "items.move", {"uid": 1, "idx": 10, "src": {"plate": 1, "posx": src}, "dst": {"plate": 1, "posx": free}})
    with db.GameReader("joy1") as r:
        moved = r.one("SELECT Code FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 1 AND Posx = ?", (free,))
    check("предметы: запись (переставить) прошла", res["ok"] and moved and moved["Code"] == b1[-1]["Code"])
    u = ops.undo(ctx, res["audit_id"])
    with db.GameReader("joy1") as r:
        back = r.one("SELECT Code FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 1 AND Posx = ?", (src,))
        gone = r.one("SELECT Code FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 1 AND Posx = ?", (free,))
    check("предметы: откат через журнал вернул предмет", u["ok"] and back and back["Code"] == b1[-1]["Code"] and not gone)
    _live_more(ctx, b1, eq, cap1, used1)


def _live_more(ctx, b1, eq, cap1, used1):
    """Ревизия А1 + правка свойств: обмен, снять/надеть, золото, свойства — каждое с откатом; откат «после чужой правки»."""
    from domains import itemedit
    run = lambda name, p: ops.run(ctx, name, dict(p, expect=ops.run(ctx, name, p, dry=True)["preview"]["expect"]))
    # обмен двух предметов сумки 1 и откат
    if len(b1) >= 2:
        a, b = b1[0], b1[1]
        res = run("items.move", {"uid": 1, "idx": 10, "src": {"plate": 1, "posx": a["Posx"]}, "dst": {"plate": 1, "posx": b["Posx"]}})
        with db.GameReader("joy1") as r:
            x = r.one("SELECT Code FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 1 AND Posx = ?", (b["Posx"],))
        check("предметы: обмен прошёл", x and x["Code"] == a["Code"])
        check("предметы: откат обмена", ops.undo(ctx, res["audit_id"])["ok"])
    # снять оружие и надеть обратно — каждое с откатом; откат после чужой правки — отказ
    if 9 in eq:
        res = run("items.move", {"uid": 1, "idx": 10, "src": {"plate": 3, "posx": 9}, "dst": {"plate": 0}})
        with db.GameReader("joy1") as r:
            gone = r.one("SELECT Code FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 3 AND Posx = 9")
        check("предметы: снять оружие записано", res["ok"] and not gone)
        moved = res["result"]["moves"][0]["to"]
        res2 = run("items.move", {"uid": 1, "idx": 10, "src": {"plate": moved[0], "posx": moved[1]}, "dst": {"plate": 3}})
        check("предметы: надеть обратно записано", res2["ok"])
        check("предметы: откат «снять» после повторного надевания — отказ (предмет менялся)",
              raises(lambda: ops.undo(ctx, res["audit_id"]), ops.OpRefused))
        check("предметы: откат «надеть» и затем «снять» — исходное состояние",
              ops.undo(ctx, res2["audit_id"])["ok"] and ops.undo(ctx, res["audit_id"])["ok"])
        with db.GameReader("joy1") as r:
            back = r.one("SELECT Code FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 3 AND Posx = 9")
        check("предметы: оружие снова надето", back and back["Code"] == eq[9]["Code"])
    # золото
    with db.GameReader("joy1") as r:
        g = r.one("SELECT Amount FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 2 AND Code = 20551")
    if g:
        res = run("gold.set", {"uid": 1, "idx": 10, "amount": int(g["Amount"]) - 1 if g["Amount"] else 1})
        check("золото: записано", res["ok"])
        check("золото: откат", ops.undo(ctx, res["audit_id"])["ok"])
        with db.GameReader("joy1") as r:
            g2 = r.one("SELECT Amount FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 2 AND Code = 20551")
        check("золото: вернулось как было", g2["Amount"] == g["Amount"])
        check("золото: больше INT — отказ", raises(lambda: ops.run(ctx, "gold.set", {"uid": 1, "idx": 10, "amount": 2147483648}, dry=True), ops.OpRefused))
    # свойства: доп-опция заточки пересчитывается со ступенью; недопустимая опция и самоцвет — отказ
    arm = next((x for k, x in eq.items() if k in (0, 1, 2, 3, 4)), None)
    if arm:
        with db.GameReader("joy1") as r:
            uu = str(r.one("SELECT Uuid FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 3 AND Posx = ?", (arm["Posx"],))["Uuid"])
        d = itemedit.describe(1, 10, uu)
        check("свойства: описание с вариантами", "pairs" in d and len(d["cells"]) == 4)
        check("свойства: чужая опция — отказ", raises(lambda: ops.run(ctx, "items.edit", {"uid": 1, "idx": 10, "uuid": uu,
              "set": {"pairs": {"1": {"type": 9999, "value": 1}}}}, dry=True), ops.OpRefused))
        check("свойства: недопустимый самоцвет — отказ", raises(lambda: ops.run(ctx, "items.edit", {"uid": 1, "idx": 10, "uuid": uu,
              "set": {"cells": {"0": 7001 + 3000}}}, dry=True), ops.OpRefused))
        check("свойства: гнёзда списком — отказ (только словарь «гнездо → самоцвет»)", raises(lambda: ops.run(ctx, "items.edit",
              {"uid": 1, "idx": 10, "uuid": uu, "set": {"cells": [None, None, None, None]}}, dry=True), ops.OpRefused))
        # ПЕРЕПРОВЕРКА А1 К1: правка одного поля не трогает остальные
        dur = int(d["durability"] or 0)
        nd = dur - 1 if dur > 0 else min(1, d["durability_max"])
        if nd != dur:
            pv = ops.run(ctx, "items.edit", {"uid": 1, "idx": 10, "uuid": uu, "set": {"durability": nd}}, dry=True)["preview"]
            check("свойства К1: правка прочности меняет только прочность", set(pv["changes"]) == {"Durability"})
        # ПЕРЕПРОВЕРКА А1 В1: ступень — вместе с MaxupCnt/AcuUpcnt
        newup = d["upcount"] + 1 if d["upcount"] < 20 else d["upcount"] - 1
        pv = ops.run(ctx, "items.edit", {"uid": 1, "idx": 10, "uuid": uu, "set": {"upcount": newup}}, dry=True)["preview"]
        from domains import srvtables
        t44 = srvtables.sowel_maxup(d["code"])
        mx = pv["changes"].get("MaxupCnt", d["maxup"])
        acu = pv["changes"].get("AcuUpcnt", d["acu"])
        check("свойства В1: MaxupCnt = max(t44, ступень)", mx == max(t44, newup))
        check("свойства В7: AcuUpcnt = новой ступени (без «лишних попыток»)", acu == newup)
        def why(p):
            """Текст отказа операции (перепроверка 4 М24: проверять ПРИЧИНУ, а не сам факт отказа)."""
            try:
                ops.run(ctx, "items.edit", p, dry=True)
            except ops.OpRefused as ex:
                return str(ex)
            return ""
        c0 = d["cells"][0]
        alt0 = next((o["code"] for o in c0["options"] if o["code"] != c0["cur"]), None) if c0["enabled"] else None
        if alt0:
            check("свойства М16: ключ гнезда «00» — отказ «неверные параметры» (а не правка гнезда 0)",
                  why({"uid": 1, "idx": 10, "uuid": uu, "set": {"cells": {"00": alt0}}}) == "неверные параметры правки предмета")
        empty = next((k for k in ("1", "2", "5") if not d["pairs"][int(k)]["cur"]), None)
        if empty:
            a_, b_ = itemedit.PAIRS[int(empty)]
            with db.GameReader("joy1") as r:
                raw = r.one("SELECT %s AS t, %s AS v FROM Item WHERE Uuid = ?" % (a_, b_), (uu,))
            check("свойства М21: «нет» у пустой пары (%s/%s) — ничего не меняется" % (raw["t"], raw["v"]),
                  why({"uid": 1, "idx": 10, "uuid": uu, "set": {"pairs": {empty: None}}}) == "ничего не меняется")
        check("свойства М17: отпечаток — «было → стало»", all(isinstance(v, list) and len(v) == 2 for v in pv["expect"].values()))
        # 16.11 ночь: «+N%» (Updamage) — вместе со ступенью; вне шагов свитков — отказ
        urule = srvtables.upgrade_rule(d["code"])
        want_d = itemedit.auto_updamage({"Upcount": d["upcount"], "Updamage": d["updamage"]}, newup, urule)
        check("заточка: Updamage меняется со ступенью (+%d → +%d%%)" % (newup, want_d),
              pv["changes"].get("Updamage", d["updamage"]) == want_d and (newup == 0 or want_d > 0))
        steps = itemedit.per_step(urule)
        check("заточка: процент вне шагов свитков — отказ",
              why({"uid": 1, "idx": 10, "uuid": uu, "set": {"upcount": newup, "updamage": newup * steps[-1] + 1}}).startswith("процент заточки"))
        pv2 = ops.run(ctx, "items.edit", {"uid": 1, "idx": 10, "uuid": uu, "set": {"upcount": newup, "updamage": newup * steps[0]}},
                      dry=True)["preview"]
        check("заточка: явный процент принят", pv2["changes"].get("Updamage", d["updamage"]) == newup * steps[0])
        check("заточка: предел ступени — t44 + шаги OverUpgrade обычными свитками, 255 — 100%-м свитком (тип 91)",
              d["upgrade"]["max_normal"] == urule["t44"] + srvtables.over_upgrade_steps()
              and d["upcount_max"] == (255 if urule["sure_steps"] else urule["max_normal"]))
        pv3 = ops.run(ctx, "items.edit", {"uid": 1, "idx": 10, "uuid": uu, "set": {"upcount": newup, "upstep": steps[0]}},
                      dry=True)["preview"]
        check("заточка: шаг за ступень → сумма, набираемая свитками",
              srvtables.updamage_reachable(urule, newup, pv3["changes"].get("Updamage", d["updamage"])))
        res = run("items.edit", {"uid": 1, "idx": 10, "uuid": uu, "set": {"upcount": newup}})
        check("свойства: ступень записана", res["ok"])
        check("свойства: откат", ops.undo(ctx, res["audit_id"])["ok"])
        d2 = itemedit.describe(1, 10, uu)
        check("свойства: всё вернулось", d2["upcount"] == d["upcount"] and d2["pairs"][4]["cur"] == d["pairs"][4]["cur"]
              and d2["acu"] == d["acu"] and d2["maxup"] == d["maxup"] and d2["updamage"] == d["updamage"])
    # ПЕРЕПРОВЕРКА А1 В2: самоцвет в гнездо — с Uc и Fdate, откат возвращает всё
    for k, x in sorted(eq.items()):
        with db.GameReader("joy1") as r:
            uu = str(r.one("SELECT Uuid FROM Item WHERE Userindex = 1 AND Charidx = 10 AND Plate = 3 AND Posx = ?", (x["Posx"],))["Uuid"])
        d = itemedit.describe(1, 10, uu)
        c0 = d["cells"][0]
        alt = [o["code"] for o in c0["options"] if o["code"] != c0["cur"]]
        if not c0["enabled"] or not alt:
            continue
        with db.GameReader("joy1") as r:
            was = r.one("SELECT Cell1, Uc1, Fdate, Weight FROM Item WHERE Uuid = ?", (uu,))
        res = run("items.edit", {"uid": 1, "idx": 10, "uuid": uu, "set": {"cells": {"0": alt[0]}}})
        with db.GameReader("joy1") as r:
            now = r.one("SELECT Cell1, Uc1, Fdate, Weight FROM Item WHERE Uuid = ?", (uu,))
        check("гнёзда В2: самоцвет вставлен, Uc1 = новый Uuid", now["Cell1"] == alt[0] and now["Uc1"] and now["Uc1"] != was["Uc1"])
        check("гнёзда В2: откат", ops.undo(ctx, res["audit_id"])["ok"])
        with db.GameReader("joy1") as r:
            back = r.one("SELECT Cell1, Uc1, Fdate, Weight FROM Item WHERE Uuid = ?", (uu,))
        check("гнёзда В2: Cell1/Uc1/Fdate/вес как были", dict(back) == dict(was))
        break


def _live_block():
    """А1 «блок учётки» на ВТОРОЙ учётке владельца (Rimy, 2): блок → снять → откат снятия → откат блока; в конце как было."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    run = lambda name, p: ops.run(ctx, name, dict(p, expect=ops.run(ctx, name, p, dry=True)["preview"]["expect"]))
    st = lambda: _block_state(2)
    was = st()
    check("блок: кириллица в причине — отказ", raises(lambda: ops.run(ctx, "account.block", {"uid": 2, "hours": 1, "reason": "тест"},
                                                                     dry=True), ops.OpRefused))
    check("блок: срок 0 — отказ", raises(lambda: ops.run(ctx, "account.block", {"uid": 2, "hours": 0, "reason": "x"}, dry=True),
                                         ops.OpRefused))
    if was["rows"] or was["us_block"]:
        print("     (учётка 2 уже заблокирована — запись блока не проверяется)")
        return
    with db.GameReader("asdastoryop") as r:
        on = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if (on["Flag"] not in (None, 0)) or (on["UserNum"] not in (None, -1)):       # перепроверка 6 В2
        print("     (учётка 2 в игре — запись блока не проверяется)")
        return
    b = u = None
    try:
        b = run("account.block", {"uid": 2, "hours": 1, "reason": "admin center selftest"})
        s1 = st()
        check("блок: записан (us_block 5, одна строка BlockList)", b["ok"] and s1["us_block"] == 5 and s1["rows"] == 1)
        u = run("account.unblock", {"uid": 2})
        s2 = st()
        check("блок: снят как OPBlockDel (строка ушла в историю, us_block 0)", u["ok"] and s2["us_block"] == 0 and s2["rows"] == 0
              and s2["hist"] == was["hist"] + 1)
        ok_u = ops.undo(ctx, u["audit_id"])["ok"]
        u = None
        check("блок: откат снятия (строка снова действует, история не стирается)", ok_u and st()["rows"] == 1
              and st()["hist"] == was["hist"] + 1)
        check("блок: откат блока", ops.undo(ctx, b["audit_id"])["ok"])
        b = None
        check("блок: учётка как была (кроме одной строки истории)", dict(st(), hist=was["hist"]) == was)
    finally:
        # при любом сбое — учётку владельца не оставлять в блоке
        for rec in (u, b):
            if rec:
                try:
                    ops.undo(ctx, rec["audit_id"])
                except Exception as ex:
                    print("     !! откат после сбоя: %s" % ex)
        if st()["us_block"] or st()["rows"]:
            print("     !! учётка 2 осталась в блоке — снимите: ops account.unblock uid=2")


def _live_online():
    """А1 «снять залипший „в игре“»: у учётки без признаков — отказ «снимать нечего» (записи нет)."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    with db.GameReader("joy1") as r:
        cp = r.one("SELECT COUNT(*) AS n FROM CharPos WHERE Userindex = 2 AND (UserNum <> -1 OR State = 1)")["n"]
    if m["Flag"] == 0 and m["UserNum"] == -1 and not cp:
        try:
            ops.run(ctx, "account.clear_online", {"uid": 2}, dry=True)
            check("в игре: у учётки без признаков — отказ «снимать нечего»", False)
        except ops.OpRefused as ex:
            check("в игре: у учётки без признаков — отказ «снимать нечего»", str(ex).startswith("снимать нечего"))
    else:
        print("     (у учётки 2 есть признаки «в игре» — проверка отказа пропущена)")


def _live_rename():
    """А1 «смена имени»: отказы (предпросмотр) и запись с откатом на персонаже учётки 2 (только не в игре, не в клане)."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")

    def why(p):
        try:
            ops.run(ctx, "char.rename", p, dry=True)
        except ops.OpRefused as ex:
            return str(ex)
        return ""
    with db.GameReader("joy1") as r:
        ch = r.rows("SELECT c.Charidx, c.Charname FROM Charinfo c WHERE c.Userindex = 2 AND NOT EXISTS (SELECT 1 FROM ClanMember m "
                    "WHERE m.Userindex = c.Userindex AND m.Charidx = c.Charidx) AND NOT EXISTS (SELECT 1 FROM Exitem e WHERE "
                    "e.Userindex = c.Userindex AND e.Charidx = c.Charidx) AND EXISTS (SELECT 1 FROM CharPos p WHERE "
                    "p.Userindex = c.Userindex AND p.Charidx = c.Charidx)")
        other = r.one("SELECT TOP 1 Charname FROM CharPos WHERE Userindex <> 2 AND Charname COLLATE Arabic_BIN NOT LIKE '%[^ -~]%'")
        nonop = r.one("SELECT TOP 1 c.Userindex, c.Charidx FROM Charinfo c WHERE c.Userindex > 5000 AND NOT EXISTS (SELECT 1 FROM "
                      "CharGmInfo g WHERE g.Userindex = c.Userindex AND g.GMFlag IS NOT NULL)")
    if nonop:
        check("имя: пробел у не-оператора — отказ правило 4", "правило 4" in why({"uid": nonop["Userindex"], "idx": nonop["Charidx"], "name": "a b"})
              or "в игре" in why({"uid": nonop["Userindex"], "idx": nonop["Charidx"], "name": "a b"}))
    if not ch:
        print("     (у учётки 2 нет персонажа вне клана — запись имени не проверяется)")
        return
    c = ch[0]
    if other:
        w = why({"uid": 2, "idx": c["Charidx"], "name": other["Charname"].upper()})
        check("имя: чужое имя в другом регистре — «имя занято»", w.startswith("имя занято") or "в игре" in w)
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — запись имени не проверяется)")
        return
    new = ("Ren" + (c["Charname"] or "x"))[:12] + "T7"
    res = None
    try:
        res = ops.run(ctx, "char.rename", dict({"uid": 2, "idx": c["Charidx"], "name": new},
                      expect=ops.run(ctx, "char.rename", {"uid": 2, "idx": c["Charidx"], "name": new}, dry=True)["preview"]["expect"]))
        with db.GameReader("joy1") as r:
            a = r.one("SELECT Charname FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))["Charname"]
            b = r.one("SELECT Charname FROM CharPos WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))["Charname"]
        check("имя: записано в Charinfo и CharPos", a == new and b == new)
        ok = ops.undo(ctx, res["audit_id"])["ok"]
        res = None
        with db.GameReader("joy1") as r:
            a2 = r.one("SELECT Charname FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))["Charname"]
        check("имя: откат вернул прежнее", ok and a2 == c["Charname"])
    finally:
        if res:
            try:
                ops.undo(ctx, res["audit_id"])
            except Exception as ex:
                print("     !! откат имени после сбоя: %s" % ex)


def _live_level():
    """А1 «поднять уровень»: +1 уровень персонажу учётки 2 и откат (только не в игре)."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — запись уровня не проверяется)")
        return
    from domains import progress as _pg
    with db.GameReader("joy1") as r:
        c = r.one("SELECT TOP 1 Charidx, %s FROM Charinfo WHERE Userindex = 2 AND Lvl < 99 ORDER BY Charidx" % ", ".join(_pg.COLS))
    if not c:
        print("     (у учётки 2 нет персонажа ниже 99 — запись уровня не проверяется)")
        return
    p = {"uid": 2, "idx": c["Charidx"], "level": c["Lvl"] + 1}
    res = None
    try:
        res = ops.run(ctx, "char.level_up", dict(p, expect=ops.run(ctx, "char.level_up", p, dry=True)["preview"]["expect"]))
        with db.GameReader("joy1") as r:
            n = r.one("SELECT Lvl FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))["Lvl"]
        check("уровень: записан (+1)", n == c["Lvl"] + 1)
        ok = ops.undo(ctx, res["audit_id"])["ok"]
        res = None
        with db.GameReader("joy1") as r:
            back = r.one("SELECT Charidx, %s FROM Charinfo WHERE Userindex = 2 AND Charidx = ?" % ", ".join(_pg.COLS), (c["Charidx"],))
        check("уровень: откат вернул все поля", ok and dict(back) == dict(c))
    finally:
        if res:
            try:
                ops.undo(ctx, res["audit_id"])
            except Exception as ex:
                print("     !! откат уровня после сбоя: %s" % ex)


def _live_password():
    """А1 «пароль»: формула панели = HASHBYTES/FN_AC_PwHash на SQL Server; предпросмотр на учётке 2 (без записи)."""
    from domains import password as _pw
    import os as _os
    salt, hexs = _os.urandom(16), _pw.md5hex("Selftest-" + secrets.token_hex(4))
    with db.GameReader("asdastoryop") as r:
        # @Md5Hex у FN_AC_PwHash — VARCHAR(32); pyodbc шлёт str как NVARCHAR (UTF-16) — привести явно, как параметр функции
        x = r.one("SELECT HASHBYTES('SHA2_256', CONVERT(VARBINARY(16), ?) + CONVERT(VARBINARY(32), LOWER(CONVERT(VARCHAR(32), ?)))) AS h",
                  (salt, hexs))
    check("пароль: хеш панели = HASHBYTES SQL Server (как FN_AC_PwHash с VARCHAR)", bytes(x["h"]) == _pw.pw_hash(salt, hexs))
    try:
        with db.GameReader("joy1") as r:
            f = r.one("SELECT dbo.FN_AC_PwHash(CONVERT(BINARY(16), ?), ?) AS h", (salt, hexs))
        check("пароль: хеш панели = dbo.FN_AC_PwHash (как сверяет UPUserLogin)", bytes(f["h"]) == _pw.pw_hash(salt, hexs))
    except db.DbError as ex:
        print("     (FN_AC_PwHash читателю недоступна: %s — сверено по HASHBYTES)" % str(ex)[:80])
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    pv = ops.run(ctx, "account.set_password", {"uid": 2, "password": "Selftest-preview"}, dry=True)
    txt = json.dumps(pv, default=str, ensure_ascii=False)
    check("пароль: предпросмотр на учётке 2 — без пароля в ответе", "Selftest-preview" not in txt and "expect" in txt)
    with db.GameReader("asdastoryop") as r:
        l2 = r.one("SELECT Us_id FROM Us_member WHERE Userindex = 2")["Us_id"]
    check("учётка: создать с занятым логином (учётка 2, другой регистр) — отказ",
          raises(lambda: ops.run(ctx, "account.create", {"login": l2.swapcase(), "password": "Selftest-1"}, dry=True), ops.OpRefused))
    check("учётка: предпросмотр свободного логина — без пароля в ответе",
          "Selftest-2" not in json.dumps(ops.run(ctx, "account.create", {"login": "st" + secrets.token_hex(6), "password": "Selftest-2"},
                                                  dry=True), default=str, ensure_ascii=False))
    check("пароль: короткий — предупреждение, не отказ",
          any("короче" in w for w in ops.run(ctx, "account.set_password", {"uid": 2, "password": "abc"}, dry=True)
              .get("preview", {}).get("warnings", [])))


def _pw_state(uid):
    with db.GameReader("asdastoryop") as r:
        return r.one("SELECT us_block, us_pwsalt, us_pwhash, CONVERT(varchar(23), us_pwset, 121) AS pwset, us_pwfail, "
                     "CONVERT(varchar(23), us_pwfail_at, 121) AS pwfail_at FROM Us_member WHERE Userindex = ?", (uid,))


def _gm_rows(uid):
    with db.GameReader("joy1") as r:
        return r.rows("SELECT Charidx, GMFlag, CONVERT(varchar(23), GMDate, 121) AS d FROM CharGmInfo WHERE UserIndex = ? ORDER BY Charidx", (uid,))


def _live_accounts():
    """19.11 «Учётки» на живой базе: служебная учётка — в транзакции с откатом (следов нет); закрытие с новым паролем и GM-флаг —
    записью и откатом журналом на учётке 2 (владельца; только не в игре и не в блоке); учётку 1 (GM_sitxovski) не трогаем.
    Чтение: сводка античита, gp7 страницами, реестр банов Discord, поиск по Discord, связи «одна машина»."""
    import tempfile
    from domains import accountclose, accountnew, discordlinks, players
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    run = lambda name, p: ops.run(ctx, name, dict(p, expect=ops.run(ctx, name, p, dry=True)["preview"]["expect"]))
    # служебная учётка: предпросмотр (номер — следующий после занятых служебных), запись в транзакции и откат
    with db.GameReader("asdastoryop") as r:
        svc = [x["Userindex"] for x in r.rows("SELECT Userindex FROM Us_member WHERE Userindex BETWEEN 1 AND 5000")]
        ident0 = r.one("SELECT CONVERT(bigint, IDENT_CURRENT('dbo.Us_member')) AS v")["v"]
    login = "st" + secrets.token_hex(5)
    prm = {"login": login, "password": "Selftest-" + secrets.token_hex(4)}
    pv = ops.run(ctx, "account.create_service", prm, dry=True)["preview"]
    want = accountnew.next_service_uid(svc)
    check("служебная учётка: предпросмотр — номер %s (после занятых служебных), без пароля в ответе" % want,
          pv["expect"] == {"login": login, "uid": want} and prm["password"] not in json.dumps(pv, ensure_ascii=False, default=str))
    check("служебная учётка: не владельцу — отказ", raises(lambda: ops.run(ops.Ctx(None, "cli:selftest", "admin", "", "cli"),
                                                                        "account.create_service", prm, dry=True), ops.OpRefused))
    op = accountnew.AccountCreateService()
    try:
        res = op.apply(ctx, prm, pv)
    except (ops.OpRefused, db.DbError) as ex:
        res = None
        check("служебная учётка: процедура adm.ServiceAccountCreate вставила номер %s (транзакция панели)" % want, False, ex)
    if res:
        try:
            check("служебная учётка: процедура adm.ServiceAccountCreate вставила номер %s (транзакция панели)" % want,
                  res["after"]["uid"] == want)
        finally:
            res["_close"]()                             # без фиксации — откат: учётка не создаётся
    with db.GameReader("asdastoryop") as r:
        left = r.rows("SELECT Userindex FROM Us_member WHERE Us_id = ? OR Userindex = ?", (login, want))
        ident1 = r.one("SELECT CONVERT(bigint, IDENT_CURRENT('dbo.Us_member')) AS v")["v"]
    check("служебная учётка: после отката следов нет, счётчик IDENTITY не сдвинут", not left and ident1 == ident0, (left, ident0, ident1))
    # закрыть учётку 2 со сменой пароля → откат (пароль, счётчик неудач и блок — как были)
    with db.GameReader("asdastoryop") as r:
        on = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    was, gm0 = _pw_state(2), _gm_rows(2)
    blk0 = _block_state(2)
    if (on["Flag"] not in (None, 0)) or (on["UserNum"] not in (None, -1)) or blk0["rows"] or blk0["us_block"]:
        print("     (учётка 2 в игре или в блоке — закрытие и GM-флаг не пишутся)")
    else:
        c = None
        try:
            c = run("account.close", {"uid": 2, "reason": "admin center selftest", "password_reset": True, "kick": False})
            s1 = _pw_state(2)
            check("закрыть: учётка 2 — блок навсегда, пароль сменён, учётка закрыта в карточке",
                  c["ok"] and s1["us_block"] == 5 and bytes(s1["us_pwsalt"]) != bytes(was["us_pwsalt"] or b"")
                  and players.account(2)["closed"])
            u = ops.undo(ctx, c["audit_id"])
            c = None
            s2 = _pw_state(2)
            check("закрыть: откат — блок снят, прежние соль, хеш, дата пароля и счётчик неудач",
                  u["ok"] and s2 == was and _block_state(2) == blk0, (was, s2))
        finally:
            if c:
                try:
                    ops.undo(ctx, c["audit_id"])
                except Exception as ex:
                    print("     !! откат закрытия после сбоя: %s — снимите блок учётки 2 и верните пароль" % ex)
        # GM-флаг учётки 2: снять → откат (строка с прежней датой); если флага нет — выдать → откат
        g = None
        try:
            g = run("account.gm_revoke" if gm0 else "account.gm_grant", {"uid": 2})
            check("GM-флаг: учётка 2 — %s записано" % ("снятие" if gm0 else "выдача"), g["ok"] and bool(_gm_rows(2)) != bool(gm0))
            u = ops.undo(ctx, g["audit_id"])
            g = None
            check("GM-флаг: откат — строки CharGmInfo учётки 2 как были (с датой)", u["ok"] and _gm_rows(2) == gm0, (gm0, _gm_rows(2)))
        finally:
            if g:
                try:
                    ops.undo(ctx, g["audit_id"])
                except Exception as ex:
                    print("     !! откат GM-флага после сбоя: %s — проверьте CharGmInfo учётки 2" % ex)
    check("GM-флаг: игровой учётке (> 5000) — отказ", raises(lambda: ops.run(ctx, "account.gm_grant", {"uid": 75215}, dry=True), ops.OpRefused))
    try:
        ops.run(ctx, "account.gm_revoke", {"uid": 75215}, dry=True)
        why = ""
    except ops.OpRefused as ex:
        why = str(ex)
    check("ревизия 28 М-1: снятие у игровой учётки 75215 номером не запрещено (строки нет — «GM-флага нет»)", "GM-флага нет" in why, why)
    check("ревизия 28 К-5: чистка adm.pw_saved на живой базе выполняется", isinstance(accountclose.vault_gc(), int))
    # чтение: античит, gp7, Discord, связи
    e = players.eac_summary(1)
    check("античит: сводка ac.* по учётке 1 без ошибок", not e["errors"] and isinstance(e["tables"], list), e["errors"][:3])
    gp = players.gp7_page(1, "purchases", 1)
    gf = players.gp7_page(1, "gifts", 1)
    check("gp7: покупки и подарки страницами", gp["page"] == 1 and len(gp["items"]) <= gp["size"] and gf["kind"] == "gifts", (gp["total"], gf["total"]))
    bans = players.discord_bans()
    if bans is None:                                   # ★ 25.11 (С-3): реестра DiscordBot/BANNED_PLAYERS.md нет (git-ignore) — SKIP
        P.skip("Discord: реестр банов против блока входа", "нет DiscordBot/BANNED_PLAYERS.md (образец — BANNED_PLAYERS.example.md)")
    else:
        from domains import gifts as _gifts
        check("Discord: реестр банов против блока входа (расхождения первыми; строк = учёток реестра)", len(bans) == len(_gifts.banned() or {})
              and all(("mismatch" in x) for x in bans), len(bans))
    src = os.path.join(ROOT, "DiscordBot", "playtest_accounts.txt")         # ★ 25.11 (М-2): от корня клона
    if os.path.exists(src):
        tmp = os.path.join(tempfile.mkdtemp(), "discord_links.json")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(discordlinks.build_json(src))
        old = discordlinks.LINKS
        discordlinks.LINKS = tmp
        try:
            lk = [x for x in discordlinks.links() if not x["banned"]]
            if lk:
                found = players.search(lk[0]["discord_id"])
                check("Discord: поиск по Discord ID находит учётку", any((a["Us_id"] or "").lower() == lk[0]["login"].lower() for a in found),
                      [a["Us_id"] for a in found])
        finally:
            discordlinks.LINKS = old
            os.remove(tmp)
    acc1 = players.account(1, net=True)
    check("связи: у каждой связанной учётки — степень (MAC+IP / MAC / IP …), карточка с Discord и сводкой EAC",
          all(l.get("degree") in players.LINK_TITLES for l in acc1["net"]["linked"]) and "discord" in acc1 and "eac" in acc1["net"])
    with db.GameReader("joylog1") as lg:
        vm = {r["Userindex"] for r in lg.rows("SELECT DISTINCT Userindex FROM LogInfo WHERE Mac LIKE '00-15-5D%'")}
        macs = {}
        for r in lg.rows("SELECT DISTINCT Userindex, Mac FROM LogInfo WHERE Userindex IN (%s)" % ",".join("?" * len(vm)), sorted(vm)) if vm else []:
            if players._linkable_mac(r["Mac"]):
                macs.setdefault(r["Userindex"], set()).add(r["Mac"].strip().upper())
    if len(vm) >= 2:
        u0 = sorted(vm)[0]
        lk0 = {l["Userindex"]: l for l in players.account(u0, net=True)["net"]["linked"]}
        only_vm = [v for v in vm if v != u0 and not (macs.get(v, set()) & macs.get(u0, set()))]
        check("связи: учётки с общим только MAC Hyper-V (00-15-5D) не связаны по MAC (%d таких пар)" % len(only_vm),
              all(not (lk0.get(v) or {}).get("by_mac") for v in only_vm))


def _live_move():
    """А1 «перенос»: запись и откат на персонаже учётки 2 (если не в игре)."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — перенос не проверяется)")
        return
    with db.GameReader("joy1") as r:
        c = r.one("SELECT TOP 1 Charidx, Poridx, Cporidx, Posx, Posy FROM CharPos WHERE Userindex = 2 ORDER BY Charidx")
    tgt = {"mode": "town", "map": 7} if (c["Poridx"], c["Posx"], c["Posy"]) != (7, 135, 188) else {"mode": "town", "map": 0}
    res = None
    try:
        res = ops.run(ctx, "char.move", dict(tgt, uid=2, idx=c["Charidx"]))
        with db.GameReader("joy1") as r:
            a = r.one("SELECT Poridx, Cporidx, Posx, Posy FROM CharPos WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))
        check("перенос: записан (карта %s, клетка %s,%s)" % (a["Poridx"], a["Posx"], a["Posy"]),
              a["Poridx"] == tgt["map"] and a["Cporidx"] == tgt["map"] and (a["Posx"], a["Posy"]) == _move_town(tgt["map"]))
    finally:
        if res:
            ops.undo(ctx, res["audit_id"])
            with db.GameReader("joy1") as r:
                b = r.one("SELECT Poridx, Cporidx, Posx, Posy FROM CharPos WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))
            check("перенос: откат вернул позицию", all(b[k] == c[k] for k in ("Poridx", "Cporidx", "Posx", "Posy")))


def _items_v2_offline(GW):
    """19.11: след v2 (feed.trace), дюпы (dupes.py), возврат по журналам (itemrecover.py, adm.ItemRecover), ac0z (UPTimeoutDeleteItem)."""
    import datetime as _d
    from domains import dupes as _du, feed as _fd, itemgive as _ig, itemrecover as _ir
    _ir_later = _ir._later_events
    # ── след v2: запрос без CAST по столбцу, номер — GUID
    check("след v2: номер — GUID в верхнем регистре, мусор — отказ",
          _fd._norm_serial("{3b7bbcdd-cc1d-4327-af2f-963cd7326d13}") == "3B7BBCDD-CC1D-4327-AF2F-963CD7326D13"
          and raises(lambda: _fd._norm_serial("3B7BBCDD"), ValueError) and raises(lambda: _fd._norm_serial("x' OR 1=1 --"), ValueError))
    check("след v2: сравнение без CAST по столбцу (varchar — CAST параметра, uniqueidentifier — TRY_CAST параметра)",
          _fd._in_list("Serial", "varchar", 2) == "[Serial] IN (CAST(? AS varchar(36)), CAST(? AS varchar(36)))"
          and _fd._in_list("Uuid", "uniqueidentifier", 1) == "[Uuid] IN (TRY_CAST(? AS uniqueidentifier))"
          and _fd._in_list("t.Uuid", "uniqueidentifier", 1).startswith("t.Uuid IN ("))
    cat = [{"name": "dbo.TradeitemTo", "sch": "dbo", "tab": "TradeitemTo", "group": "обмен", "users": ["Userindex"], "char": "Charidx",
            "time": "Edate", "serial": "Serial", "code": "Code", "cols": [], "serials": [("Serial", "varchar"), ("Tserial", "varchar")]},
           {"name": "dbo.BuyNPC", "sch": "dbo", "tab": "BuyNPC", "group": "покупка у NPC", "users": ["Userindex"], "char": "Charidx",
            "time": "Edate", "serial": "Serial", "code": None, "cols": [], "serials": [("Serial", "varchar")]},
           {"name": "dbo.SellNPCGear", "sch": "dbo", "tab": "SellNPCGear", "group": "продажа NPC", "users": ["Userindex"], "char": "Charidx",
            "time": "Edate", "serial": "Serial", "code": None, "cols": [], "serials": [("Serial", "varchar")]},
           {"name": "dbo.Item_Delete", "sch": "dbo", "tab": "Item_Delete", "group": "предметы", "users": ["Userindex"], "char": "Charidx",
            "time": "Time", "serial": "Uuid", "code": None, "cols": [], "serials": [("Uuid", "uniqueidentifier")]}]
    A, B = "AAAAAAAA-0000-0000-0000-000000000001", "BBBBBBBB-0000-0000-0000-000000000002"
    t0 = _d.datetime(2026, 11, 1, 10, 0, 0)
    J = {"dbo.BuyNPC": [{"Edate": t0, "Userindex": 7, "Charidx": 10, "Serial": A, "__at": "2026-11-01 10:00:00.000"}],
         "dbo.TradeitemTo": [{"Edate": t0 + _d.timedelta(hours=1), "Userindex": 8, "Charidx": 10, "Serial": B, "Tserial": A, "__at": "2026-11-01 11:00:00.000"}],
         "dbo.SellNPCGear": [{"Edate": t0 + _d.timedelta(hours=2), "Userindex": 8, "Charidx": 10, "Serial": B, "Gm": 50, "__at": "2026-11-01 12:00:00.000"}],
         "dbo.Item_Delete": []}
    plans = []

    def fake_batched(lg, plan, errors):
        plans.extend(plan)
        out = []
        for ent, sql, args in plan:
            want = {str(a).upper() for a in args}
            out.append((ent, [r for r in J[ent["name"]] if any(str(r.get(c) or "").upper() in want for c, _t in ent["serials"])]))
        return out

    class _NoDb:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    _sv = (_fd.catalog, _fd._batched, _fd.where_now, _fd.db.GameReader, _fd.explain_no_birth)
    _fd.catalog, _fd._batched, _fd.db.GameReader = (lambda refresh=False: cat), fake_batched, _NoDb
    _fd.where_now = lambda serials: {"item": [], "socket": [], "deleted": [], "deleted_socket": [], "lots": [], "lot_socket": [],
                                     "taken": [], "ledger": [], "copies": []}
    _fd.explain_no_birth = lambda s, now: ["X"]
    try:
        tr = _fd.trace(A.lower())
        check("след v2: цепочка через неполный обмен (TradeitemTo Serial↔Tserial) — продажа под новым номером найдена",
              tr["chain"] == [A, B] and [e["table"] for e in tr["events"]] == ["dbo.BuyNPC", "dbo.TradeitemTo", "dbo.SellNPCGear"], tr["chain"])
        ev = tr["events"]
        check("след v2: ярлыки — появление (BuyNPC), связь, уничтожение «продан NPC» с возвратом; последнее событие и «не жив»",
              ev[0].get("birth") and ev[1].get("link") == {"Serial": B, "Tserial": A} and ev[2].get("death") == "продан NPC"
              and ev[2].get("recoverable") and tr["summary"]["last"]["death"] == "продан NPC" and not tr["summary"]["alive"]
              and ev[2]["key"] == "2026-11-01 12:00:00.000")
        check("след v2: в запросах нет CAST по столбцу, у uniqueidentifier — TRY_CAST параметра, время — CONVERT 121",
              plans and all("CAST([" not in p[1] for p in plans) and any("[Uuid] IN (TRY_CAST(" in p[1] for p in plans)
              and all("CONVERT(varchar(23), [" in p[1] for p in plans))
        check("р27 К-5: TOP 500 — последние по времени (ORDER BY … DESC)", all("ORDER BY [" in p[1] and p[1].endswith("DESC") for p in plans))
        _, la, _ = _ir_later(A, "2026-11-01 10:30:00.000", tr)
        _, lb, _ = _ir_later(B, "2026-11-01 11:30:00.000", tr)
        check("р27 М-1: «номер встречается после источника» — только события самого номера (продажа под номером получателя не мешает)",
              not [e for e in la if e["table"] == "dbo.SellNPCGear"] and [e["table"] for e in lb] == ["dbo.SellNPCGear"], (la, lb))
        J["dbo.BuyNPC"] = []
        tr = _fd.trace(A)
        check("след v2: нет события появления — объяснение", tr["summary"]["explain"] == ["X"])
        check("след v2: ExchangeEvent — уничтожение только 'Time Out-Delete'; конец срока / ремесло — без возврата",
              _fd.death_of("dbo.ExchangeEvent", {"State": "Time Out-Delete"}) == ("снят с аукциона по таймауту", True)
              and _fd.death_of("dbo.ExchangeEvent", {"State": "Registration Cancel"}) is None
              and _fd.death_of("dbo.ExchangeEvent", {"State": "Time Out-Return"}) is None
              and _fd.death_of("dbo.TimeExpired", {})[1] is False and _fd.death_of("dbo.Item_Delete", {})[1] is False)
    finally:
        _fd.catalog, _fd._batched, _fd.where_now, _fd.db.GameReader, _fd.explain_no_birth = _sv
    # ── возврат по журналам: план (подставной журнал и сумки)
    S1 = "CCCCCCCC-0000-0000-0000-000000000003"
    src = {"Edate": t0, "Userindex": 7001, "Charidx": 10, "Code": 24893, "Serial": S1, "Cell1": 0, "Cell2": -1, "Cell3": -1, "Cell4": -1,
           "Upcount": 2, "AcuUpcnt": 1, "MaxUPcnt": 4, "UPdamage": 300, "Opidx1": 5, "OpValue1": 7, "Opidx2": -1, "OpValue2": 0, "Opidx3": -1,
           "OPvalue3": 0, "OPidx4": -1, "Opvalue4": 0, "OPidx5": -1, "Opvalue5": 0, "Gm": 500, "__at": "2026-11-01 10:00:00.000"}
    ents = {t: {"name": "dbo." + t, "tab": t, "sch": "dbo", "time": "Edate", "serials": [("Serial", "varchar")]} for t in
            ("SellNPCGear", "Wastebasketitem", "ExchangeEvent", "TimeExpired")}
    cur = {"row": src, "ent": ents["SellNPCGear"], "reg": None}
    _sv2 = (_ir.source_row, _ir.items.p96_enabled)
    _ir.source_row = lambda table, serial, at: (cur["ent"], cur["row"], cur["reg"])
    _ir.items.p96_enabled = lambda: True

    class _RW(GW):
        """Сумки + строка золота сумки 2."""
        def __init__(self, gold=1000, **kw):
            super().__init__(**kw)
            self.gold = gold

        def rows(self, sql, params=()):
            if "Plate = 2 AND Code = ?" in sql:
                return [{"Amount": self.gold}] if self.gold is not None else []
            return GW.rows(self, sql, params)
    tc = ({"events": [{"at": t0, "key": "2026-11-01 10:00:00.000", "table": "dbo.SellNPCGear"}]}, [], [])
    p0 = {"serial": S1, "table": "dbo.SellNPCGear", "at": "2026-11-01 10:00:00.000"}
    try:
        pl = _ir.plan_recover(_RW(), p0, trace_cache=tc)
        sp = _ig.item_spec(24893)
        check("возврат: проданное NPC — тот же номер, поля из журнала (ступень, опция, MaxupCnt, Updamage), прочность и вес по таблице",
              pl["sig"]["uuid"] == S1 and pl["row"]["Upcount"] == 2 and pl["row"]["Opidx1"] == 5 and pl["row"]["MaxupCnt"] == 4
              and pl["row"]["Updamage"] == 300 and pl["row"]["Durability"] == sp["dur"] and pl["row"]["Weight"] == sp["unit_weight"]
              and pl["row"]["Cell2"] == 0 and pl["plate"] == 1, pl["row"])
        check("возврат: золото продажи списывается (флажок по умолчанию), сверка золота на предпросмотре",
              pl["gold"] == {"take": 500, "expect": 1000} and pl["sig"]["gold"] == [500, 1000] and "списать золото продажи 500" in pl["text"])
        pl = _ir.plan_recover(_RW(), dict(p0, charge_gold=False), trace_cache=tc)
        check("возврат: без списания — предупреждение «игрок получит и золото, и предмет»",
              pl["gold"] is None and any("НЕ списывается" in w for w in pl["warnings"]))
        check("возврат: золота не хватает / нет строки золота — отказ",
              raises(lambda: _ir.plan_recover(_RW(gold=100), p0, trace_cache=tc), ops.OpRefused)
              and raises(lambda: _ir.plan_recover(_RW(gold=None), p0, trace_cache=tc), ops.OpRefused))
        check("возврат: список «не восстановится» — прочность, привязка, Refine, срок, дата получения",
              all(x in pl["lost"] for x in _ir.LOST_COMMON))
        check("возврат: после источника номер встречается снова — отказ (предмет жив / уже вернулся)",
              raises(lambda: _ir.plan_recover(_RW(), p0, trace_cache=(tc[0], [{"table": "dbo.Pick", "at": t0}], [])), ops.OpRefused))
        full = [(1, x, 30000, 0, 1) for x in range(60)]
        check("возврат: в сумке нет места — отказ", raises(lambda: _ir.plan_recover(_RW(rows=full), p0, trace_cache=tc), ops.OpRefused))
        _wt = _ir.plan_recover(_RW(), p0, trace_cache=tc)["row"]["Weight"]
        check("р27 К-7: вес как у GameServer — ровно до предела можно, на 1 больше — отказ (GameServer.c:85371, :109000)",
              _ir.plan_recover(_RW(cur_w=5000 - _wt), p0, trace_cache=tc) is not None
              and raises(lambda: _ir.plan_recover(_RW(cur_w=5001 - _wt), p0, trace_cache=tc), ops.OpRefused)
              and _ig.plan_give(GW(cur_w=5000 - 23), {"uid": 7001, "idx": 10, "code": 20571, "qty": 1}) is not None)
        cur.update(ent=ents["Wastebasketitem"], row={"Edate": t0, "Userindex": 7001, "Charidx": 10, "Code": 20571, "Serial": S1, "Amount": 5,
                                                     "Ramount": 2, "__at": src["__at"]})
        check("возврат: выброшена часть стопки (остаток > 0) — отказ без дюпа",
              raises(lambda: _ir.plan_recover(_RW(), dict(p0, table="dbo.Wastebasketitem"), trace_cache=tc), ops.OpRefused))
        cur["row"] = dict(cur["row"], Ramount=0)
        pl = _ir.plan_recover(_RW(), dict(p0, table="dbo.Wastebasketitem"), trace_cache=tc)
        check("возврат: выброшенная стопка целиком — количество из журнала, вес = количество × вес, сумка 2, без золота",
              pl["row"]["Amount"] == 5 and pl["row"]["Weight"] == 5 * _ig.item_spec(20571)["unit_weight"] and pl["plate"] == 2 and pl["gold"] is None)
        reg = {"Edate": t0, "Serial": S1, "Code": 24893, "Cell1": 0, "Cell2": -1, "Cell3": -1, "Cell4": -1, "Upcount": 1, "AcuUPcnt": 0,
               "MaxUpCnt": 6, "Updamage": 0, "Opidx1": 9, "OPvalue1": 3, "OPidx2": -1, "Opvalue2": 0, "OPidx3": -1, "OPvalue3": 0,
               "OPidx4": -1, "Opvalue4": 0, "OPidx5": -1, "OPvalue5": 0}
        cur.update(ent=ents["ExchangeEvent"], row={"Edate": t0, "Userindex": 7001, "Charidx": 10, "Code": 24893, "Serial": S1, "Amount": 0,
                                                   "Upcount": 1, "Opidx1": 9, "OpValue1": 3, "Opidx2": -1, "OpValue2": 0, "State": "Time Out-Delete",
                                                   "Gm": 0, "__at": src["__at"]}, reg=("ExchangeRegiGear", reg))
        pl = _ir.plan_recover(_RW(), dict(p0, table="dbo.ExchangeEvent"), trace_cache=tc)
        check("возврат: лот по таймауту — поля снаряжения из журнала выставления ExchangeRegiGear, золото не трогается",
              pl["row"]["MaxupCnt"] == 6 and pl["row"]["Opidx1"] == 9 and pl["row"]["OpValue1"] == 3 and pl["gold"] is None
              and pl["kind"] == "снят с аукциона по таймауту")
    finally:
        _ir.source_row, _ir.items.p96_enabled = _sv2
    _sv3 = _ir.feed.catalog
    _ir.feed.catalog = lambda refresh=False: [dict(e, cols=[]) for e in ents.values()]
    try:
        check("возврат: по концу срока (TimeExpired) и по таблице не из списка — отказ",
              raises(lambda: _ir.source_row("dbo.TimeExpired", S1, "2026-11-01 10:00:00.000"), ops.OpRefused)
              and raises(lambda: _ir.source_row("dbo.Pick", S1, "2026-11-01 10:00:00.000"), ops.OpRefused))
    finally:
        _ir.feed.catalog = _sv3
    op = ops.REGISTRY.get("items.recover")
    check("возврат: операция items.recover — право players.items_give (только владелец), с откатом",
          op is not None and op.perm == "players.items_give" and op.reversible and auth.can("owner", op.perm) and not auth.can("admin", op.perm))
    # ── SQL adm.ItemRecover / ItemUndo / права / откат выкладки
    sq = open(os.path.join(ROOT, "sql", "adminc_06_items.sql"), encoding="utf-8").read()
    rec = sq.split("CREATE PROCEDURE adm.ItemRecover", 1)[1].split("\nGO", 1)[0]
    und = sq.split("CREATE PROCEDURE adm.ItemUndo", 1)[1].split("\nGO", 1)[0]
    check("adm.ItemRecover: номер нигде не живёт — Item, Exitem.Eid, Uc1–4 в Item и Exitem, Del_Item, неоткаченный adm.ItemTaken",
          all(x in rec for x in ("FROM dbo.Item WHERE Uuid = @Uuid", "FROM dbo.Exitem WHERE Eid = @Uuid", "FROM dbo.Item WHERE Uc1 = @us",
                                 "FROM dbo.Exitem WHERE Uc1 = @us", "FROM dbo.Del_Item WHERE Uuid = @Uuid", "adm.ItemTaken t JOIN adm.ItemLedger",
                                 "THROW 51408")))
    check("adm.ItemRecover: повтор источника — отказ, золото без минуса и со сверкой, журналы ledger 'recover' и AdminitemLog",
          "Source = @Source AND UndoneBy IS NULL" in rec and "@g0 < @GoldTake" in rec and "@g0 <> @GoldExpect" in rec
          and "'recover'" in rec and "'Item Recover(Admin)'" in rec and "XACT_ABORT ON" in rec and "SET Amount = Amount - @GoldTake" in rec)
    check("adm.ItemUndo: вид 'recover' — убрать строку, вернуть списанное золото",
          "IN ('give', 'recover')" in und and "Amount = Amount + @gt" in und and "@gt = GoldTaken" in und)
    g4 = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read()
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")            # ★ 25.11 (К-3): нет файла — условие отката не проверяется
    v11 = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
    check("adm.ItemRecover: EXECUTE asda_ops, проверка выкладки, откат выкладки",
          "GRANT EXECUTE ON adm.ItemRecover TO [asda_ops]" in g4 and (rb is None or "DROP PROCEDURE adm.ItemRecover" in rb)
          and "'Joy1.adm.ItemRecover','OBJECT','EXECUTE'), 1" in v11)
    # ── серверный патч ac0z (UPTimeoutDeleteItem: таймаут лота → возврат владельцу)
    sd = os.path.join(os.path.dirname(ROOT), "AstoryServer", "Docs", "SQL")
    mg, sm, rbz = (P.dev_text(sd, f) for f in ("ac0z_01_migrate.sql", "ac0z_10_smoke.sql", "ac0z_99_rollback.sql"))   # ★ 25.11 (К-3)
    if mg is None or sm is None or rbz is None:
        P.skip("ac0z: миграция, smoke и откат UPTimeoutDeleteItem", "нет AstoryServer/Docs/SQL/ac0z_*.sql")
    else:
        body = mg.split("ALTER PROC [dbo].[UPTimeoutDeleteItem]", 1)[1]
        check("ac0z: прежний текст в AsdaProcBackup, возврат путём отмены (Uuid = Eid), 'Time Out-Return', владелец в игре / нет места / вес — Flag 0",
              "AsdaProcBackup" in mg and "'Time Out-Return'" in body and "AsdaStoryOp.dbo.Us_member" in body and "CharPos" in body
              and "@CurW + ISNULL(@Weight, 0) > ISNULL(@MaxW, 0)" in body and body.count("SELECT CAST(0 AS TINYINT) AS Flag") >= 3
              and "'Time Out-Delete'" in body and "INSERT INTO dbo.Item" in body)
        check("ac0z: smoke в транзакции с откатом, откат патча — из AsdaProcBackup",
              "BEGIN TRANSACTION" in sm and "ROLLBACK TRANSACTION" in sm and "COMMIT" not in sm.replace("COMMIT TRAN", "")
              and "AsdaProcBackup WHERE Patch = 'ac0z'" in rbz)
    # ── дюпы (подставная база)
    K = "90D7C266-1097-4336-B1FC-5A57D07BEB94"
    rows_same = [{"u": K, "src": "Item", "Userindex": 2, "Charidx": 11, "Code": 23227, "Plate": 2, "Posx": 1, "Amount": 5, "d": t0},
                 {"u": K, "src": "Item", "Userindex": 2, "Charidx": 11, "Code": 23227, "Plate": 5, "Posx": 1, "Amount": 5, "d": t0},
                 {"u": A, "src": "Item", "Userindex": 3, "Charidx": 10, "Code": 24893, "Plate": 1, "Posx": 1, "Amount": 0, "d": t0},
                 {"u": A, "src": "Exitem", "Userindex": 4, "Charidx": 10, "Code": 24893, "Plate": 1, "Posx": 7, "Amount": 0, "d": t0},
                 {"u": B, "src": "Item", "Userindex": 3, "Charidx": 10, "Code": 20571, "Plate": 2, "Posx": 1, "Amount": 3, "d": t0},
                 {"u": B, "src": "Exitem", "Userindex": 3, "Charidx": 10, "Code": 20571, "Plate": 2, "Posx": 8, "Amount": 2, "d": t0}]
    items_rows = [{"Userindex": 3, "Charidx": 10, "Plate": 1, "Posx": 0, "Code": 24893, "Amount": 2, "Uuid": A},
                  {"Userindex": 3, "Charidx": 10, "Plate": 1, "Posx": 1, "Code": 1, "Amount": 999, "Uuid": B},
                  {"Userindex": 3, "Charidx": 10, "Plate": 1, "Posx": 2, "Code": 2, "Amount": 99, "Uuid": S1}]

    class _DR:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def one(self, sql, params=()):
            return {"t": 1}
        def rows(self, sql, params=()):
            if sql.startswith("WITH x AS"):
                return [dict(r) for r in rows_same]
            if "FROM adm.CharRestored" in sql:
                return []
            if "AsdaChargeGroup WHERE GroupKey <> 0" in sql:
                return [{"Code": 2}]
            if "FROM Item WHERE Code <> ?" in sql:
                return [dict(r) for r in items_rows]
            return []
    _sv4 = (_du.db.GameReader, _du.srvtables.charge_cap, _ig.item_spec)
    specs = {24893: dict(kind="gear", stack=False, amount_each=0), 20571: dict(kind="stack", stack=True, amount_each=0),
             23227: dict(kind="stack", stack=True, amount_each=0), 1: dict(kind="function", stack=False, amount_each=10),
             2: dict(kind="function", stack=False, amount_each=10)}
    _du.db.GameReader, _du.srvtables.charge_cap = _DR, (lambda: 30000)
    _ig.item_spec = lambda c: specs[int(c)]
    try:
        su = {g["uuid"]: g["kind"] for g in _du.same_uuid()}
        check("дюпы: одинаковый номер — снаряжение в двух местах «подозрение», стопка «штатно», 90D7C266 — «известный»",
              su == {A: "suspect", B: "stack", K: "known"}, su)
        ba = _du.bad_amounts()
        why = {r["Uuid"]: r["why"] for r in ba["rows"]}
        check("дюпы: количества — снаряжение 2 и заряды вне P100 — нарушение, заряды P100 в пределах потолка — законно",
              set(why) == {A, B} and ba["p100_merged"] == 1 and "P100" in why[B], why)
    finally:
        _du.db.GameReader, _du.srvtables.charge_cap, _ig.item_spec = _sv4
    from domains import players as _pp
    lots = [{"Gaindate": t0, "Fdate": t0 + _d.timedelta(hours=24)}]
    _pp._lots_more(lots)
    _now = _d.datetime.now()
    check("р27 М-4: лот, срок реле прошёл (Fdate + 14 сут), а он в Exitem — «ждёт рестарта реле или отмены владельцем»; будущий срок — нет",
          _fd.lot_overdue({"relay_due": _now - _d.timedelta(days=2), "relay_due_late": _now - _d.timedelta(days=1)}) == _fd.LOT_OVERDUE
          and _fd.lot_overdue({"relay_due": _now - _d.timedelta(days=1), "relay_due_late": _now + _d.timedelta(hours=1)}) is None)
    i_lk, i_09, i_08 = rec.index("sp_getapplock"), rec.index("THROW 51409"), rec.index("THROW 51408")
    check("р27 М-2: возврат — сначала замок возвратов, потом 51409 и 51408; откат изъятия берёт тот же замок",
          i_lk < i_09 < i_08 and "'AsdaAdmin.ItemUuidInsert'" in und.split("ELSE IF @kind = 'take'", 1)[1])
    check("р27 М-5: дюп-проверка видит Del_ExItem (Eid и Uc), Uc в Del_Item и в неоткаченных снимках ItemTaken; след и дюпы — Del_ExItem",
          "dbo.Del_ExItem WHERE Eid = @Uuid OR Uc1 = @us" in rec and "dbo.Del_Item WHERE Uuid = @Uuid OR Uc1 = @us" in rec
          and "t.Uc1 = @us" in rec and "FROM Del_ExItem" in open(_fd.__file__, encoding="utf-8").read()
          and "FROM Del_ExItem" in open(_du.__file__, encoding="utf-8").read())
    check("р27 К-4: откат возврата проданного без строки золота — понятный отказ (как сервер: строку золота не создаёт)",
          "нет строки золота (сервер её не удаляет)" in und)
    _cat3 = [{"name": "dbo.ExchangeEvent", "sch": "dbo", "tab": "ExchangeEvent", "time": "Edate", "cols": ["Edate", "Serial", "State"],
              "serials": [("Serial", "varchar")]}]
    _t1, _t2 = _d.datetime(2026, 11, 4), _d.datetime(2026, 11, 20)
    _rows3 = [{"s": A, "t": _t2, "tod": _t1}, {"s": B, "t": _t2, "tod": _t2}]
    _sv5 = (_du.feed.catalog, _du.feed._batched)
    _du.feed.catalog = lambda refresh=False: _cat3
    _du.feed._batched = lambda lg, plan, errors: [(dict(_cat3[0], _col="Serial"), _rows3)]
    _sv6 = _du.db.GameReader
    _du.db.GameReader = _DR
    try:
        last, _born, _part = _du._serial_index([])
        check("р27 М-3: ExchangeEvent — «уничтожен» только если последняя строка номера — таймаут (позже — возврат/отмена/выставление)",
              last[A][2] is False and last[B][2] is True, last)
    finally:
        (_du.feed.catalog, _du.feed._batched), _du.db.GameReader = _sv5, _sv6
    bz = mg.split("ALTER PROC [dbo].[UPTimeoutDeleteItem]", 1)[1]
    check("р27 К-3: ac0z — порядок блокировок как у панели: Us_member → CharPos → Charinfo → Item",
          bz.index("AsdaStoryOp.dbo.Us_member WITH (UPDLOCK") < bz.index("dbo.CharPos WITH (UPDLOCK") < bz.index("dbo.Charinfo WITH (UPDLOCK")
          < bz.index("FROM dbo.Item i WITH (UPDLOCK"))
    check("р27 К-1/К-2/К-6: ac0z — условие P96 и куча Exitem описаны; smoke — служебная 2…5000, давно не входившая, в одной транзакции",
          "P96" in mg and "куча без индексов" in mg and "BETWEEN 2 AND 5000" in sm and "LogInfo" in sm)
    check("карточка: лот — «истёк» и когда реле снимет (ItemDeleteTime 14 суток; при рестарте реле — от конца продажи)",
          lots[0]["expired"] and lots[0]["relay_due"] == t0 + _d.timedelta(days=14) and lots[0]["relay_due_late"] == t0 + _d.timedelta(days=15))


def _live_recover():
    """19.11: след v2, дюпы и «вернуть по журналу» на служебной учётке 2 (не в игре): возврат выброшенного тем же номером, повтор —
    отказ (дюп), откат — строки персонажа как были; проданное NPC — со списанием золота и возвратом его откатом."""
    from domains import dupes as _du, feed as _fd, itemrecover as _ir
    tr = _fd.trace("90D7C266-1097-4336-B1FC-5A57D07BEB94")
    check("след v2 живьём: известный дубль — 2 строки в сумках, объяснение «до начала журналов»",
          len(tr["now"]["item"]) == 2 and any("до начала журналов" in x for x in tr["summary"]["explain"]) and not tr["errors"], tr["errors"][:2])
    lot = _fd.trace("C99C59B7-6D39-4A69-990F-E5010DDB6190")
    check("след v2 живьём: «где сейчас» видит лот аукциона (Exitem.Eid) с оценкой снятия реле",
          lot["now"]["lots"] and lot["now"]["lots"][0]["relay_due"] is not None or not lot["now"]["lots"])
    du = _du.report(full=False)
    check("дюпы живьём: 90D7C266 — «известный», невозможных количеств нет",
          any(g["uuid"] == "90D7C266-1097-4336-B1FC-5A57D07BEB94" and g["kind"] == "known" for g in du["same_uuid"])
          and not [g for g in du["same_uuid"] if g["kind"] == "suspect"], [g["uuid"] for g in du["same_uuid"]])
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — возврат по журналу не проверяется)")
        return
    with db.GameReader("joylog1") as lg:
        cands = lg.rows("SELECT TOP 40 t, Serial FROM (SELECT 'dbo.WastebasketGear' AS t, Serial, Edate FROM WastebasketGear WHERE Userindex = 2 "
                        "UNION ALL SELECT 'dbo.WastebasketSowel', Serial, Edate FROM WastebasketSowel WHERE Userindex = 2 "
                        "UNION ALL SELECT 'dbo.SellNPCGear', Serial, Edate FROM SellNPCGear WHERE Userindex = 2 AND Gm > 0 "
                        "UNION ALL SELECT 'dbo.SellNPC', Serial, Edate FROM SellNPC WHERE Userindex = 2 AND Ramount = 0 AND Gm > 0) x "
                        "ORDER BY CASE WHEN t LIKE '%SellNPC%' THEN 0 ELSE 1 END, Edate DESC")
    picked = {}
    for c in cands:
        if c["t"].startswith("dbo.SellNPC") in picked:
            continue
        try:
            got = _ir.sources(c["Serial"])
        except Exception:
            continue
        ok = [x for x in got["sources"] if x["table"] == c["t"] and not x.get("refused")]
        if ok and not got["alive"]:
            picked[c["t"].startswith("dbo.SellNPC")] = (c["Serial"].upper(), ok[0])
        if len(picked) == 2:
            break
    if not picked:
        print("     (у учётки 2 нет выброшенного / проданного без следа после — возврат не проверяется)")
        return
    for sell, (serial, src) in sorted(picked.items()):
        p = {"serial": serial, "table": src["table"], "at": src["at"]}
        with db.GameReader("joylog1") as lg:
            row = lg.one("SELECT TOP 1 Charidx FROM [dbo].[%s] WHERE Serial = ?" % src["table"].split(".")[1], (serial,))
        idx = int(row["Charidx"])
        snap = ("SELECT CONVERT(varchar(36), Uuid) AS u, Code, Plate, Posx, Amount, Weight, CONVERT(varchar(23), Fdate, 121) AS f FROM Item "
                "WHERE Userindex = 2 AND Charidx = ? ORDER BY Plate, Posx")
        with db.GameReader("joy1") as r:
            before = r.rows(snap, (idx,))
        aid = None
        try:
            res = ops.run(ctx, "items.recover", p)
            aid = res["audit_id"]
            with db.GameReader("joy1") as r:
                got = r.rows("SELECT Plate, Posx, Code FROM Item WHERE Userindex = 2 AND Charidx = ? AND Uuid = ?", (idx, serial))
                led = r.one("SELECT Kind, GoldTaken, Source FROM adm.ItemLedger WHERE Id = ?", (res_ledger(res),))
            with db.GameReader("joylog1") as lg:
                al = lg.one("SELECT TOP 1 State FROM AdminitemLog WHERE Serial = ? ORDER BY Edate DESC", (serial,))
            check("возврат живьём (%s): тот же номер в сумке, журнал панели recover%s, AdminitemLog «Item Recover(Admin)»"
                  % (src["table"], ", золото списано %s" % led["GoldTaken"] if sell else ""),
                  len(got) == 1 and led["Kind"] == "recover" and al and al["State"] == "Item Recover(Admin)"
                  and (not sell or (led["GoldTaken"] or 0) > 0), (got, led, al))
            check("возврат живьём: повтор того же источника — отказ (номер уже в базе)",
                  raises(lambda: ops.run(ctx, "items.recover", p), ops.OpRefused))
        finally:
            if aid:
                try:
                    ops.undo(ctx, aid)
                except ops.OpRefused as ex:
                    check("возврат живьём: откат", False, str(ex))
            with db.GameReader("joy1") as r:
                after = r.rows(snap, (idx,))
            check("возврат живьём (%s): после отката строки персонажа как были (%d строк, золото тоже)" % (src["table"], len(before)),
                  after == before, [x for x in after if x not in before][:3])


def _live_give():
    """А1 «выдать / изъять предмет»: на персонаже учётки 2 (если не в игре) — стопка, снаряжение с опцией, склад; изъятие целиком и
    части; откаты в обратном порядке; итог — инвентарь как был."""
    from domains import itemgive as _ig, srvtables as _st
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — выдача не проверяется)")
        return
    snap_sql = ("SELECT CONVERT(varchar(36), Uuid) AS u, Code, Plate, Posx, Amount, Weight, Cell1, Opidx1, OpValue1, "
                "CONVERT(varchar(23), Fdate, 121) AS f FROM Item "
                "WHERE Userindex = 2 AND Charidx = ? ORDER BY Plate, Posx")
    with db.GameReader("joy1") as r:
        c = r.one("SELECT TOP 1 Charidx, WareCount FROM Charinfo WHERE Userindex = 2 ORDER BY Charidx")
        before = r.rows(snap_sql, (c["Charidx"],))
    idx, done = c["Charidx"], []
    try:
        res = ops.run(ctx, "items.give", {"uid": 2, "idx": idx, "code": 20571, "qty": 3})
        done.append(res["audit_id"])
        with db.GameReader("joy1") as r:
            led = r.one("SELECT Kind, Plate, Posx, AmountBefore, AmountAfter FROM adm.ItemLedger WHERE Id = ?", (res_ledger(res),))
        check("выдача: стопка записана (%s, ячейка %s, %s → %s)" % (led["Kind"], led["Posx"], led["AmountBefore"], led["AmountAfter"]),
              led["Kind"] in ("give", "stack") and led["AmountAfter"] == (led["AmountBefore"] or 0) + 3)
        st0 = _st.creation_choices(24893)["stones"][0][0]
        pt = _ig._pair_lists(24893)[1][0]
        opts = {"pairs": {"1": {"type": pt["type"], "value": pt["values"][0]["value"]}}, "stone": st0, "upcount": 0}
        res = ops.run(ctx, "items.give", {"uid": 2, "idx": idx, "code": 24893, "qty": 1, "opts": opts})
        done.append(res["audit_id"])
        lid = res_ledger(res)
        with db.GameReader("joy1") as r:
            led = r.one("SELECT Plate, Posx, CONVERT(varchar(36), Uuid) AS u FROM adm.ItemLedger WHERE Id = ?", (lid,))
            row = r.one("SELECT CONVERT(varchar(36), Uuid) AS u, Code, Cell1, Uc1, Opidx1, OpValue1, Rdate, Owner, MaxupCnt, Durability, Weight "
                        "FROM Item WHERE Userindex = 2 AND Charidx = ? AND Plate = ? AND Posx = ?", (idx, led["Plate"], led["Posx"]))
        with db.GameReader("joylog1") as r:
            lg = r.one("SELECT TOP 1 State, Code, Cell1, Opidx1 FROM AdminitemLog WHERE Serial = ? ORDER BY Edate DESC", (led["u"],))
        sp = _ig.item_spec(24893)
        check("выдача: снаряжение — код, самоцвет с Uc, опция, Rdate NULL, Owner 0, прочность/MaxupCnt/вес как у сервера",
              row and row["Code"] == 24893 and row["Cell1"] == st0 and row["Uc1"] and row["Opidx1"] == pt["type"] and row["Rdate"] is None
              and row["Owner"] == 0 and row["Durability"] == sp["dur"] and row["MaxupCnt"] == sp["maxup"]
              and row["Weight"] == sp["unit_weight"] + _st.cellob(st0)["weight"], row)
        check("выдача: запись в стоковом журнале AdminitemLog", lg and lg["State"] == "Item Add(Admin)" and lg["Code"] == 24893, lg)
        tk = ops.run(ctx, "items.take", {"uid": 2, "idx": idx, "plate": led["Plate"], "posx": led["Posx"], "uuid": row["u"]})
        with db.GameReader("joy1") as r:
            gone = not r.rows("SELECT 1 AS x FROM Item WHERE Userindex = 2 AND Charidx = ? AND Uuid = ?", (idx, row["u"]))
            snap = r.rows("SELECT Code FROM adm.ItemTaken WHERE LedgerId = ?", (res_ledger(tk),))
        check("изъятие: строки нет, снимок сохранён", gone and snap and snap[0]["Code"] == 24893)
        ops.undo(ctx, tk["audit_id"])
        with db.GameReader("joy1") as r:
            back = r.rows("SELECT Plate, Posx FROM Item WHERE Userindex = 2 AND Charidx = ? AND Uuid = ?", (idx, row["u"]))
        check("изъятие: откат вернул тот же экземпляр (тот же Uuid) в ту же ячейку",
              back and (back[0]["Plate"], back[0]["Posx"]) == (led["Plate"], led["Posx"]))
        check("изъятие: повторный откат — отказ", raises(lambda: ops.undo(ctx, tk["audit_id"]), ops.OpRefused))
        if (c["WareCount"] or 0) > 0:
            res = ops.run(ctx, "items.give", {"uid": 2, "idx": idx, "code": 20571, "qty": 2, "to": "ware"})
            done.append(res["audit_id"])
            with db.GameReader("joy1") as r:
                wl = r.one("SELECT Plate, Posx, AmountAfter, CONVERT(varchar(36), Uuid) AS u FROM adm.ItemLedger WHERE Id = ?", (res_ledger(res),))
            check("выдача: в склад (Plate 5)", wl["Plate"] == 5)
            if wl["AmountAfter"] > 1:
                tp = ops.run(ctx, "items.take", {"uid": 2, "idx": idx, "plate": 5, "posx": wl["Posx"], "uuid": wl["u"], "qty": 1})
                with db.GameReader("joy1") as r:
                    a = r.one("SELECT Amount FROM Item WHERE Userindex = 2 AND Charidx = ? AND Plate = 5 AND Posx = ?", (idx, wl["Posx"]))
                check("изъятие: часть стопки на складе", a["Amount"] == wl["AmountAfter"] - 1)
                ops.undo(ctx, tp["audit_id"])
    finally:
        for a in reversed(done):
            try:
                ops.undo(ctx, a)
            except ops.OpRefused as ex:
                check("выдача: откат записи журнала %s" % a, False, str(ex))
        with db.GameReader("joy1") as r:
            after = r.rows(snap_sql, (idx,))
        check("выдача: после откатов инвентарь как был (%d строк)" % len(before), after == before,
              [x for x in after if x not in before][:3])


def res_ledger(res):
    """Номер последней записи adm.ItemLedger операции (её after — ops.run → result)."""
    return ((res.get("result") or {}).get("ledger") or [None])[-1]


def _live_post():
    """А1 «подарок / премиум-почта» и «опыт, %»: на персонаже учётки 2 — запись в ящик и откат; опыт 99 % и откат."""
    from domains import gifts as _gf
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — подарок и опыт не проверяются)")
        return
    with db.GameReader("joy1") as r:
        idx = r.one("SELECT TOP 1 Charidx FROM Charinfo WHERE Userindex = 2 ORDER BY Charidx")["Charidx"]
        box0 = r.rows("SELECT iType, Orderidx, Code, Amount FROM ItemPostBox WHERE Userindex = 2 AND Charidx = ? ORDER BY 1, 2, 3", (idx,))
        e0 = r.one("SELECT Lvl, Expe FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (idx,))
    code = next(x["code"] for x in _gf.catalog_rows("", limit=1000) if _ok_offer(x["code"]))
    for kind, c, q, rows_want in (("gift", code, 9, 9), ("mail", 20571, 3, 1)):
        _pp = {"kind": kind, "code": c, "qty": q, "uid": 2, "idx": idx}
        _pv = ops.run(ctx, "items.post", _pp, dry=True)          # как браузер: отпечаток проходит JSON (перепроверка 19 В1)
        res = ops.run(ctx, "items.post", dict(_pp, expect=json.loads(json.dumps(_pv["preview"]["expect"]))))
        sent = res["result"]["sent"][0]["rows"]
        with db.GameReader("joy1") as r:
            box = r.rows("SELECT iType, Orderidx, Code, Amount FROM ItemPostBox WHERE Userindex = 2 AND Charidx = ? ORDER BY 1, 2, 3", (idx,))
        check("%s: в ящике %d строк (%d шт.)" % (kind, len(sent), q), len(box) == len(box0) + rows_want and len(sent) == rows_want
              and sum(x[3] for x in sent) == q)
        ops.undo(ctx, res["audit_id"])
        with db.GameReader("joy1") as r:
            box = r.rows("SELECT iType, Orderidx, Code, Amount FROM ItemPostBox WHERE Userindex = 2 AND Charidx = ? ORDER BY 1, 2, 3", (idx,))
        check("%s: откат убрал ровно свои строки" % kind, box == box0)
    try:
        res = ops.run(ctx, "char.exp_set", {"uid": 2, "idx": idx, "percent": 99})
    except ops.OpRefused:                                   # опыт уже ровно 99 % — берём 50 %
        res = ops.run(ctx, "char.exp_set", {"uid": 2, "idx": idx, "percent": 50})
    with db.GameReader("joy1") as r:
        e1 = r.one("SELECT Lvl, Expe FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (idx,))
    check("опыт: процент уровня записан, уровень тот же (%s → %s)" % (e0["Expe"], e1["Expe"]), e1["Lvl"] == e0["Lvl"] and e1["Expe"] != e0["Expe"])
    ops.undo(ctx, res["audit_id"])
    with db.GameReader("joy1") as r:
        e2 = r.one("SELECT Lvl, Expe FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (idx,))
    check("опыт: откат вернул прежний опыт", e2 == e0)


def _ok_offer(code):
    from domains import gifts as _gf
    try:
        _gf.describe("gift", code)
        return True
    except ops.OpRefused:
        return False


def _live_titles():
    """А1 «звания, очки чести»: на персонаже учётки 2 — выдать, снять, очки чести; откаты; итог — строки как были."""
    from domains import titles as _tt
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — звания не проверяются)")
        return

    def snap():
        with db.GameReader("joy1") as r:
            return [r.rows("SELECT * FROM %s WHERE Userindex = 2 AND Charidx = 10 ORDER BY 3" % t) for t in
                    ("CharFame", "CharFameBank", "CharFameProgress", "CharCamp")]
    s0 = snap()
    d = _tt.describe(2, 10)
    give = next(t["id"] for t in d["titles"] if not t["got"] and t["enabled"] and not t["rating"] and t["id"] < 256
                and t["class"] in (0, d["class"]) and t["id"] not in _tt.SET_TARGETS)
    take = next(t["id"] for t in d["titles"] if t["got"] and not t["rating"] and t["id"] < 256)
    done = []
    try:
        for name, tid in (("title.grant", give), ("title.revoke", take)):
            pv = ops.run(ctx, name, {"uid": 2, "idx": 10, "title": tid}, dry=True)
            done.append(ops.run(ctx, name, {"uid": 2, "idx": 10, "title": tid, "expect": json.loads(json.dumps(pv["preview"]["expect"]))})["audit_id"])
        d2 = _tt.describe(2, 10)
        g = {t["id"]: t for t in d2["titles"]}
        check("звания: выдано %d и снято %d; слава = сумме званий" % (give, take), g[give]["got"] and not g[take]["got"]
              and d2["fame"] == d2["fame_sum"])
        if d["camp"]:
            done.append(ops.run(ctx, "honor.set", {"uid": 2, "idx": 10, "value": d["camp"]["CampPoint"] + 123})["audit_id"])
            check("очки чести: записаны", _tt.describe(2, 10)["camp"]["CampPoint"] == d["camp"]["CampPoint"] + 123)
    finally:
        for a in reversed(done):
            ops.undo(ctx, a)
        check("звания: после откатов строки как были (CharFame, CharFameBank, CharFameProgress, CharCamp)", snap() == s0)


def _live_quests():
    """А1 «задания»: на персонаже учётки 2 — выдать (как NPC), снять, завершить с наградой, снять «выполнено»; откаты; строки как были."""
    from domains import quests as _qs
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — задания не проверяются)")
        return
    with db.GameReader("joy1") as r:
        chars = [x["Charidx"] for x in r.rows("SELECT Charidx FROM Charinfo WHERE Userindex = 2 ORDER BY Charidx")]

    def snap(idx):
        with db.GameReader("joy1") as r:
            return (r.rows("SELECT * FROM CharEpisode WHERE Userindex = 2 AND Charidx = ? ORDER BY Posx", (idx,)),
                    r.rows("SELECT * FROM CharQuest WHERE Userindex = 2 AND Charidx = ?", (idx,)),
                    r.rows("SELECT %s FROM Charinfo WHERE Userindex = 2 AND Charidx = ?" % ", ".join(_qs.progress.COLS), (idx,)),
                    r.rows("SELECT Plate, Posx, Code, Amount, Uuid FROM Item WHERE Userindex = 2 AND Charidx = ? ORDER BY Plate, Posx, Code", (idx,)))
    steps, idx = [], None
    for c in chars:
        d = _qs.describe(2, c)
        if d["available"] and d["free"]:
            idx = c
            break
    if idx is None:
        print("     (у персонажей учётки 2 нет доступных заданий — запись не проверяется)")
        return
    base = {"uid": 2, "idx": idx}
    q_give = d["available"][0]["quest"]
    steps.append(("quest.give", dict(base, quest=q_give)))
    if d["taken"]:
        t = next((x for x in d["taken"] if not x["board"]), None)
        if t:
            steps.append(("quest.drop", dict(base, posx=t["posx"])))
            rw = t["rewards"][0]["id"] if t["rewards"] else None
            steps.append(("quest.complete", dict(base, quest=t["quest"], **({"reward": rw} if rw else {}))))
    busy = {y["quest"] for y in d["done"]} | {y["quest"] for y in d["taken"]} | {q_give}      # зависимые — выполненные и взятые (и выданное выше)
    un = next((x for x in d["done"] if not x["job"] and not (_qs.qd.dependents(x["quest"]) & busy)), None)
    if un:
        steps.append(("quest.uncomplete", dict(base, quest=un["quest"])))
    s0 = snap(idx)
    done = []
    try:
        for name, prm in steps:
            if name == "quest.complete":                  # завершить снятое выше — снова взятым нельзя: завершаем то, что взяли первым
                prm = dict(base, quest=q_give)
            pv = ops.run(ctx, name, prm, dry=True)
            done.append(ops.run(ctx, name, dict(prm, expect=json.loads(json.dumps(pv["preview"]["expect"]))))["audit_id"])
        check("задания: записано %d операций (%s) на %d/%d" % (len(done), ", ".join(n for n, _p in steps), 2, idx), len(done) == len(steps))
    finally:
        for a in reversed(done):
            ops.undo(ctx, a)
        check("задания: после откатов строки как были (CharEpisode, CharQuest, Charinfo, Item)", snap(idx) == s0)


def _acc_free(uid):
    """Учётка не в игре и не на выборе персонажа (Us_member.Flag 0, UserNum −1, ни одного CharPos.UserNum ≠ −1)."""
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = ?", (uid,))
    if not m or m["Flag"] != 0 or m["UserNum"] != -1:
        return False
    with db.GameReader("joy1") as r:
        return not r.rows("SELECT TOP 1 1 AS x FROM CharPos WHERE Userindex = ? AND UserNum <> -1", (uid,))


def _live_charrest():
    """А1 «внешность, баффы, лагерь, ремесло, рыбалка, обучение» на учётке 2 (только не в игре): каждая операция записью и откатом
    журналом; итог — строки всех таблиц учётки как были (снимок до и после). Пересчёт рейтинга — только предпросмотр (его делает служба)."""
    from domains import charrest as _cr
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    if not _acc_free(2):
        print("     (учётка 2 в игре — внешность/баффы/лагерь/ремесло не проверяются)")
        return
    tabs = ("CharAppr", "CharPlusPackage", "CharCamp", "CRT_CharCraftInfo", "CRT_LimitationQuest", "CharFish", "CharFishBookInfo", "CharTutorial")

    def snap():
        with db.GameReader("joy1") as r:
            return [r.rows("SELECT * FROM %s WHERE Userindex = 2 ORDER BY 1, 2, 3" % t) for t in tabs]
    s0 = snap()
    d12, d11, d10 = _cr.describe(2, 12), _cr.describe(2, 11), _cr.describe(2, 10)
    steps = []
    a = d12["appearance"]
    if a:
        h = next(x for x in d12["hair"] if (x["style"], x["color"]) != (a["HairStyle"], a["HairColor"]))
        steps.append(("appearance.set", {"uid": 2, "idx": 12, "hair": h["style"], "color": h["color"],
                                         "face": next(f for f in d12["faces"] if f != a["FaceType"])}))
    if any(b["active"] for b in d12["plus"]):
        steps.append(("plus.extend", {"uid": 2, "idx": 12, "minutes": 60}))
    steps.append(("plus.set", {"uid": 2, "idx": 12, "type": d12["plus_types"][1]["type"] if len(d12["plus_types"]) > 1 else 1}))
    steps.append(("plus.remove", {"uid": 2, "idx": 12}))
    cur = d12["camp"]["Campidx"] if d12["camp"] else -1
    steps.append(("camp.set_army", {"uid": 2, "idx": 12, "army": 0 if cur != 0 else 2}))
    if d10["craft"]:
        steps.append(("craft.set_level", {"uid": 2, "idx": 10, "level": 3 if d10["craft"]["level"] != 3 else 2}))
    steps.append(("fish.set_skill", {"uid": 2, "idx": 12, "value": (d12["fish"] or 0) + 5}))
    if d11["fish_books"]:
        steps.append(("fishbook.delete", {"uid": 2, "idx": 11, "book": d11["fish_books"][-1]["book"]}))
    done_steps = [s["step"] for s in d12["tutorial"] if s["done"]]
    flip = [s["step"] for s in d12["tutorial"] if not s["done"]][:1] + done_steps[1:]
    steps.append(("tutorial.set", {"uid": 2, "idx": 12, "steps": flip}))
    done = []
    try:
        for name, prm in steps:
            pv = ops.run(ctx, name, prm, dry=True)
            done.append(ops.run(ctx, name, dict(prm, expect=json.loads(json.dumps(pv["preview"]["expect"]))))["audit_id"])
        d12b = _cr.describe(2, 12)
        check("внешность/баффы/лагерь/ремесло: записано %d операций (%s)" % (len(done), ", ".join(n for n, _p in steps)), len(done) == len(steps)
              and not d12b["plus"] and (d12b["fish"] or 0) == (d12["fish"] or 0) + 5)
        check("лагерь: армия всей учётки сменилась", {x["Campidx"] for x in d12b["account_camp"]} == {0 if cur != 0 else 2})
    finally:
        for a_id in reversed(done):
            ops.undo(ctx, a_id)
        check("внешность/баффы/лагерь/ремесло: после откатов строки учётки 2 как были (%s)" % ", ".join(tabs), snap() == s0)
    try:
        pv = ops.run(ctx, "camp.rank_rebuild", {}, dry=True)
        check("рейтинг чести: предпросмотр (запись делает служба в 06:10)", "рейтинг чести" in pv["preview"]["text"], pv["preview"]["text"])
    except ops.OpRefused as ex:
        check("рейтинг чести: предпросмотр", False, ex)
    check("ремесло: суточный сброс без сданных — отказ с причиной", raises(lambda: ops.run(ctx, "craft.daily_reset", {"uid": 2, "idx": 12}, dry=True), ops.OpRefused))


def _live_charcopy():
    """А1 «копия»: (1) предпросмотр копии 1/10 → учётка 2 — отказ «уже 3 персонажа» (у служебных учёток свободных слотов нет);
    (2) процедуры adm.CharCopy / CharCopyDelete целиком — в ОДНОЙ транзакции с ROLLBACK на сервере (sysadmin, sqlcmd): слот 2/11
    освобождается штатным UPDeleteChar, копия 1/10 → 2/11, сверка (новые Uuid, карта, Share 0), удаление копии, повторное удаление —
    отказ; после отката — строки учётки 2 как были. Только когда учётки 1 и 2 не в игре (учётка 1 — персонаж владельца)."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    if not _acc_free(1) or not _acc_free(2):
        print("     (учётка 1 или 2 в игре — копия не проверяется: учётку 1 — персонажа владельца — панель не выводит из игры ради теста)")
        return
    try:
        ops.run(ctx, "char.copy", {"uid": 1, "idx": 10, "to": 2, "name": "CopyTst1"}, dry=True)
        ok = False
    except ops.OpRefused as ex:
        ok = "персонажа" in str(ex) or "слот" in str(ex)
    check("копия: предпросмотр на заполненную учётку 2 — отказ с причиной", ok)
    import subprocess
    from core import hostshell

    def counts():
        with db.GameReader("joy1") as r:
            return [r.one("SELECT COUNT(*) AS n FROM %s WHERE Userindex = 2" % t)["n"] for t in
                    ("Charinfo", "CharPos", "Item", "CharSkill", "CharRefine", "CharFameHigh", "CharPetList", "CharCamp")] + [
                r.one("SELECT COUNT(*) AS n FROM adm.CharCopied")["n"]]
    c0 = counts()
    script = r"""SET NOCOUNT ON; SET XACT_ABORT OFF;
USE [Joy1];
BEGIN TRANSACTION;
DECLARE @r TABLE (CopyId INT, Items INT, Camp SMALLINT);
SELECT * INTO #ref0 FROM dbo.CharRefine WHERE Userindex = 2 AND Charidx = 11;
EXEC dbo.UPDeleteChar 0, 2, 11;
INSERT @r EXEC adm.CharCopy 1, 10, 2, 11, 'CopyTst1', 'selftest';
DECLARE @id INT = (SELECT CopyId FROM @r);
SELECT 'R|items|' + CAST((SELECT COUNT(*) FROM dbo.Item WHERE Userindex = 2 AND Charidx = 11) AS VARCHAR) + '|' + CAST((SELECT COUNT(*) FROM dbo.Item WHERE Userindex = 1 AND Charidx = 10) AS VARCHAR);
SELECT 'R|sameuuid|' + CAST((SELECT COUNT(*) FROM dbo.Item a JOIN dbo.Item b ON a.Uuid = b.Uuid WHERE a.Userindex = 1 AND a.Charidx = 10 AND b.Userindex = 2 AND b.Charidx = 11) AS VARCHAR) + '|0';
SELECT 'R|map|' + CAST((SELECT COUNT(*) FROM adm.CharCopyItemMap WHERE CopyId = @id AND Kind = 0) AS VARCHAR) + '|' + CAST((SELECT Items FROM @r) AS VARCHAR);
SELECT 'R|share|' + CAST((SELECT Share FROM dbo.Charinfo WHERE Userindex = 2 AND Charidx = 11 AND Charname = 'CopyTst1') AS VARCHAR) + '|0';
EXEC adm.CharCopyDelete @id, 'selftest';
SELECT 'R|deleted|' + CAST((SELECT COUNT(*) FROM dbo.Charinfo WHERE Userindex = 2 AND Charidx = 11) AS VARCHAR) + '|0';
SELECT 'R|refine|' + CAST((SELECT COUNT(*) FROM (SELECT * FROM #ref0 EXCEPT SELECT * FROM dbo.CharRefine WHERE Userindex = 2 AND Charidx = 11) x)
  + (SELECT COUNT(*) FROM (SELECT * FROM dbo.CharRefine WHERE Userindex = 2 AND Charidx = 11 EXCEPT SELECT * FROM #ref0) y) AS VARCHAR) + '|0';
BEGIN TRY EXEC adm.CharCopyDelete @id, 'selftest'; SELECT 'R|twice|0|1'; END TRY BEGIN CATCH SELECT 'R|twice|1|1'; END CATCH
IF @@TRANCOUNT > 0 ROLLBACK;
"""
    loc = os.path.join(os.environ.get("TEMP", "."), "asda_selftest_charcopy.sql")
    with open(loc, "w", encoding="utf-8") as f:
        f.write(script)
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
    remote = config.SERVICE_ROOT + r"\_incoming\selftest_charcopy.sql"
    try:
        r = subprocess.run([exe if os.path.exists(exe) else "scp", "-i", config.SSH_KEY, "-o", "BatchMode=yes", loc,
                            "%s:%s" % (config.SSH_HOST, remote.replace("\\", "/"))], capture_output=True, timeout=120)
        if r.returncode != 0:
            return check("копия: процедуры в транзакции с откатом", False, r.stderr[:200])
        out = hostshell.powershell("$ErrorActionPreference='Continue'; $o = & sqlcmd -S lpc:.\\SQLEXPRESS -E -f 65001 -h -1 -W -i '%s' 2>&1; "
                                   "Remove-Item '%s'; ($o | Out-String)" % (remote, remote), timeout=300)
    finally:
        os.remove(loc)
    res = {p[1]: (p[2], p[3]) for p in (l.strip().split("|") for l in out.splitlines() if l.strip().startswith("R|")) if len(p) == 4}
    check("копия: процедуры в транзакции с откатом — предметов как у источника, новые Uuid, карта, Share 0, удаление, остаток CharRefine возвращён, повтор — отказ",
          len(res) == 7 and res["items"][0] == res["items"][1] and int(res["items"][0]) > 0 and all(res[k][0] == res[k][1] for k in
                                                                                                  ("sameuuid", "map", "share", "deleted", "twice", "refine")), out[-600:])
    check("копия: после отката строки учётки 2 и журнал копий как были", counts() == c0)


def _social_free(*uids):
    with db.GameReader("asdastoryop") as r:
        for u in uids:
            m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = ?", (u,))
            if not m or m["Flag"] != 0 or m["UserNum"] != -1:
                return False
    with db.GameReader("joy1") as r:
        return not r.rows("SELECT TOP 1 1 AS x FROM CharPos WHERE Userindex IN (%s) AND UserNum <> -1" % ", ".join("?" * len(uids)), uids)


def _soc_run(ctx, name, prm):
    pv = ops.run(ctx, name, prm, dry=True)
    return ops.run(ctx, name, dict(prm, expect=json.loads(json.dumps(pv["preview"]["expect"]))))["audit_id"]


def _panel_logs(table):
    with db.GameReader("joylog1") as r:
        return r.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE State LIKE 'Panel%%'" % table)["n"]


def _live_soulmate():
    """А1 «соулмейт» на учётках владельца 1 и 2: уровень, дружба, разорвать, связать (восстановить из истории); откаты; строки как были.
    Сверка S5 — только предпросмотр (решение владельца: на живых данных не применять)."""
    from domains import items as _it, social as _so
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    try:
        pv = ops.run(ctx, "soulmate.share_fix", {}, dry=True)["preview"]
        print("     предпросмотр S5 (не применяется): %s" % pv["text"])
    except ops.OpRefused as ex:
        print("     предпросмотр S5: %s" % ex)
    if not _social_free(1, 2):
        print("     (учётка 1 или 2 в игре — соулмейт не проверяется)")
        return

    def snap():
        with db.GameReader("joy1") as r:
            ad = _it._ReaderAdapter(r)
            return (sorted([tuple(sorted(x.items())) for x in _so.read(ad, "SoulMate", "Userindex IN (1, 2) OR Ouserindex IN (1, 2)")]),
                    _so.read(ad, "Charinfo", "Userindex IN (1, 2)"),
                    r.rows("SELECT Userindex, Charidx, Plate, Posx, Code FROM Item WHERE Userindex IN (1, 2) AND Code BETWEEN 21097 AND 21106"))
    with db.GameReader("joy1") as r:
        act = {x["Userindex"]: x for x in r.rows("SELECT Userindex, Ouserindex FROM SoulMate WHERE Userindex IN (1, 2) AND State = 1")}
    s0, l0 = snap(), _panel_logs("SoulMate")
    done = []
    try:
        if not act:
            done.append(_soc_run(ctx, "soulmate.link", {"uid": 1, "uid2": 2}))
        elif act.get(1, {}).get("Ouserindex") != 2:
            print("     (у учётки 1 или 2 связь с другой учёткой — соулмейт не проверяется)")
            return
        with db.GameReader("joy1") as r:
            lv = r.one("SELECT SmLvl, FriendShip FROM SoulMate WHERE Userindex = 1 AND State = 1")
        done.append(_soc_run(ctx, "soulmate.level", {"uid": 1, "level": 2 if lv["SmLvl"] != 2 else 3}))
        done.append(_soc_run(ctx, "soulmate.friendship", {"uid": 2, "value": 7 if lv["FriendShip"] != 7 else 8}))
        done.append(_soc_run(ctx, "soulmate.break", {"uid": 1}))
        with db.GameReader("joy1") as r:
            br = r.rows("SELECT State FROM SoulMate WHERE Userindex IN (1, 2) AND Ouserindex IN (1, 2)")
            sh = r.rows("SELECT Share FROM Charinfo WHERE Userindex IN (1, 2) AND Share <> 0")
        check("соулмейт: разрыв — обе строки State 0, Share 0 у обеих учёток", br and all(x["State"] == 0 for x in br) and not sh)
        done.append(_soc_run(ctx, "soulmate.link", {"uid": 2, "uid2": 1}))
        with db.GameReader("joy1") as r:
            rs = r.rows("SELECT State, SmLvl FROM SoulMate WHERE Userindex IN (1, 2) AND Ouserindex IN (1, 2)")
        check("соулмейт: связать прежнюю пару — восстановлена из истории с уровнем (как UPSoulMateOk)",
              len(rs) == 2 and all(x["State"] == 1 and x["SmLvl"] in (2, 3) for x in rs), rs)
        check("соулмейт: записано %d операций; журнал JoyLog1.SoulMate «Panel …» пишется" % len(done), _panel_logs("SoulMate") >= l0 + 2)
    finally:
        for a in reversed(done):
            ops.undo(ctx, a)
        check("соулмейт: после откатов строки как были (SoulMate, Share, кристаллы)", snap() == s0)


def _live_friends():
    """А1 «друзья»: персонажи учёток 1 и 2 — добавить, удалить; откаты; строки как были. Сверка F3 — только предпросмотр."""
    from domains import items as _it, social as _so
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    try:
        pv = ops.run(ctx, "friend.names", {}, dry=True)["preview"]
        print("     предпросмотр F3 (не применяется): %s" % pv["text"])
    except ops.OpRefused as ex:
        print("     предпросмотр F3: %s" % ex)
    if not _social_free(1, 2):
        print("     (учётка 1 или 2 в игре — друзья не проверяются)")
        return
    with db.GameReader("joy1") as r:
        c1 = [x["Charidx"] for x in r.rows("SELECT Charidx FROM Charinfo WHERE Userindex = 1 ORDER BY Charidx")]
        c2 = [x["Charidx"] for x in r.rows("SELECT Charidx FROM Charinfo WHERE Userindex = 2 ORDER BY Charidx")]
        busy = {(x["Charidx"], x["Fcharidx"]) for x in r.rows("SELECT Charidx, Fcharidx FROM CharFriend WHERE Userindex = 1 AND Fuserindex = 2")}
    pair = next(((a, b) for a in c1 for b in c2 if (a, b) not in busy), None)
    if not pair:
        print("     (нет свободной пары персонажей 1/2 — друзья не проверяются)")
        return

    def snap():
        with db.GameReader("joy1") as r:
            return sorted(tuple(sorted(x.items())) for x in _so.read(_it._ReaderAdapter(r), "CharFriend", "Userindex IN (1, 2) OR Fuserindex IN (1, 2)"))
    s0 = snap()
    prm = {"uid": 1, "idx": pair[0], "fuid": 2, "fidx": pair[1]}
    done = []
    try:
        done.append(_soc_run(ctx, "friend.add", prm))
        with db.GameReader("joy1") as r:
            n = r.one("SELECT COUNT(*) AS n FROM CharFriend WHERE (Userindex = 1 AND Charidx = ? AND Fuserindex = 2 AND Fcharidx = ?) OR "
                      "(Userindex = 2 AND Charidx = ? AND Fuserindex = 1 AND Fcharidx = ?)", (pair[0], pair[1], pair[1], pair[0]))["n"]
        check("друзья: добавить — обе стороны (как UPFriendAdd)", n == 2)
        done.append(_soc_run(ctx, "friend.delete", dict(prm, uid=2, idx=pair[1], fuid=1, fidx=pair[0])))
        check("друзья: удалить — обе стороны (как UPFriendDelete)", snap() == s0)
    finally:
        for a in reversed(done):
            ops.undo(ctx, a)
        check("друзья: после откатов строки как были (CharFriend учёток 1 и 2)", snap() == s0)


def _live_clan():
    """А1 «клан»: клан учётки 1 (только служебные члены) — объявление, роспуск; откаты; строки как были. Исключить и сменить главу —
    в транзакции с откатом (временный член клана 2/x вставляется и убирается той же транзакцией — в базе ничего не остаётся)."""
    from domains import clan as _cl, items as _it, social as _so
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("joy1") as r:
        cs = r.rows("SELECT d.Clanidx FROM ClanData d WHERE d.Capuserindex = 1 AND NOT EXISTS (SELECT 1 FROM ClanMember m WHERE m.Clanidx = d.Clanidx "
                    "AND m.Userindex > 5000)")
        c2 = r.rows("SELECT TOP 1 c.Charidx FROM Charinfo c WHERE c.Userindex = 2 AND NOT EXISTS (SELECT 1 FROM ClanMember m WHERE m.Userindex = 2 "
                    "AND m.Charidx = c.Charidx) ORDER BY c.Charidx")
    if not cs:
        print("     (у учётки 1 нет клана без игроков — клан не проверяется)")
        return
    cid = int(cs[0]["Clanidx"])
    d = _cl.describe(cid)
    check("клан: состав читается (%s, членов %d)" % (cid, len(d["members"])), d["members"] and d["Clanidx"] == cid)
    if not _social_free(1, 2):
        print("     (учётка 1 или 2 в игре — запись клана не проверяется)")
        return

    def snap():
        with db.GameReader("joy1") as r:
            ad = _it._ReaderAdapter(r)
            nt = [dict(x, idx=None) for x in _so.read(ad, "ClanNotice", "Clanidx = ?", (cid,))]
            return (_so.read(ad, "ClanData", "Clanidx = ?", (cid,)), sorted(tuple(sorted(x.items())) for x in _so.read(ad, "ClanMember", "Clanidx = ?", (cid,))),
                    sorted(tuple(sorted(x.items())) for x in nt), _so.read(ad, "CampClanData", "ClanIndex = ?", (cid,)),
                    _so.read(ad, "CampOwnerData", "CampType >= ?", (0,)))
    s0, l0 = snap(), _panel_logs("ClanLog")
    done = []
    try:
        done.append(_soc_run(ctx, "clan.notice_add", {"clan": cid, "author": "GM", "text": "selftest: объявление панели"}))
        check("клан: объявление добавлено", len(_cl.describe(cid)["notices"]) == min(len(d["notices"]) + 1, 5))
        ops.undo(ctx, done.pop())
        done.append(_soc_run(ctx, "clan.disband", {"clan": cid}))
        with db.GameReader("joy1") as r:
            gone = not r.rows("SELECT 1 AS x FROM ClanData WHERE Clanidx = ?", (cid,)) and not r.rows("SELECT 1 AS x FROM ClanMember WHERE Clanidx = ?", (cid,))
        check("клан: распущен — карточки и состава нет", gone)
        check("клан: журнал JoyLog1.ClanLog «Panel …» пишется", _panel_logs("ClanLog") >= l0 + 3)
    finally:
        for a in reversed(done):
            ops.undo(ctx, a)
        check("клан: после откатов строки как были (ClanData, ClanMember, ClanNotice без номера, лагерь, MVP)", snap() == s0)
    if not c2:
        print("     (у учётки 2 нет персонажа вне клана — исключение и смена главы не проверяются)")
        return
    x = int(c2[0]["Charidx"])
    w = db.GameWriter("joy1")
    try:
        _cl._require_offline(w, [1, 2], True)
        cn = _so.read(w, "ClanData", "Clanidx = ?", (cid,), True)[0]
        w.execute("INSERT INTO dbo.ClanMember (Clanidx, Cname, Userindex, Charidx, Charname, Grade, DonationPoint, Callname, Memo) "
                  "SELECT ?, d.Cname, 2, ?, c.Charname, 5, 0, '', '' FROM dbo.ClanData d JOIN dbo.Charinfo c ON c.Userindex = 2 AND c.Charidx = ? "
                  "WHERE d.Clanidx = ?", (cid, x, x, cid))
        w.execute("UPDATE dbo.ClanData SET JoinCnt = JoinCnt + 1 WHERE Clanidx = ?", (cid,))
        pl = _cl.plan_captain(w, {"clan": cid, "uid": 2, "idx": x}, lock=True, role="owner")
        for t, b, a in pl["changes"]:
            _so.put(w, t, b, a, "stale")
        for lg in pl["logs"]:
            _so.log(w, *lg)
        g = {(int(m["Userindex"]), int(m["Charidx"])): int(m["Grade"]) for m in w.rows("SELECT Userindex, Charidx, Grade FROM dbo.ClanMember WHERE Clanidx = ?", (cid,))}
        c = w.rows("SELECT Capuserindex, CapCharidx FROM dbo.ClanData WHERE Clanidx = ?", (cid,))[0]
        check("клан: сменить главу (в транзакции с откатом) — новый Grade 1, старый 4, Cap* нового",
              g.get((2, x)) == 1 and g.get((cn["Capuserindex"], cn["CapCharidx"])) == 4 and (int(c["Capuserindex"]), int(c["CapCharidx"])) == (2, x))
        pl = _cl.plan_kick(w, {"clan": cid, "uid": cn["Capuserindex"], "idx": cn["CapCharidx"]}, lock=True, role="owner")
        for t, b, a in pl["changes"]:
            _so.put(w, t, b, a, "stale")
        jc = w.rows("SELECT JoinCnt FROM dbo.ClanData WHERE Clanidx = ?", (cid,))[0]["JoinCnt"]
        check("клан: исключить прежнего главу (в транзакции с откатом) — строки нет, JoinCnt − 1",
              not w.rows("SELECT 1 AS x FROM dbo.ClanMember WHERE Clanidx = ? AND Userindex = ? AND Charidx = ?", (cid, cn["Capuserindex"], cn["CapCharidx"]))
              and int(jc) == int(cn["JoinCnt"]))
    finally:
        w.close()                                   # без commit — откат всей транзакции
    check("клан: после транзакции с откатом строки как были", snap() == s0)

def _live_skills():
    """А1 «навыки, питомцы»: на персонаже учётки 2 — выдать, снять, сбросить дерево и все навыки, очки, питомцы; откаты; строки как были."""
    from domains import skills as _sk, pets as _pt
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — навыки не проверяются)")
        return
    with db.GameReader("joy1") as r:
        idx = r.one("SELECT TOP 1 c.Charidx FROM Charinfo c WHERE c.Userindex = 2 AND c.Class <> 0 AND EXISTS (SELECT 1 FROM CharSkill s "
                    "WHERE s.Userindex = 2 AND s.Charidx = c.Charidx) ORDER BY c.Charidx")["Charidx"]

    def snap():
        with db.GameReader("joy1") as r:
            return (r.rows("SELECT * FROM CharSkill WHERE Userindex = 2 AND Charidx = ? ORDER BY Skillidx", (idx,)),
                    r.one("SELECT SkillPoint FROM Charinfo WHERE Userindex = 2 AND Charidx = ?", (idx,)),
                    r.rows("SELECT PetUnique, PetName, PetLvl, PetExp, NameFlag FROM CharPetList WHERE Userindex = 2 AND Charidx = ? ORDER BY 1", (idx,)))
    # перепроверка 21 М4: таблицы серверных патчей = живые файлы стойки (ac0x — SkillInfo.sif, ac0w — FameInfo.txt)
    from domains import srvtables as _st
    with db.GameReader("joy1") as r:
        try:
            base = r.rows("SELECT Skillidx, Need, Mask, Cooltime, Mpvalue, SubTime3 FROM dbo.AsdaSkillBase")
            fpts = r.rows("SELECT FameIdx, Point FROM dbo.AsdaFamePoints")
        except db.DbError:
            base, fpts = None, None
    if base is not None:
        bad = [b["Skillidx"] for b in base if (lambda si: not si or si["need"] != b["Need"] or (si["mask"] - (1 << 64) if si["mask"] >= 1 << 63 else si["mask"]) != b["Mask"]
               or si["zero"]["Cooltime"] != b["Cooltime"] or si["zero"]["Mpvalue"] != b["Mpvalue"] or si["zero"]["SubTime3"] != b["SubTime3"])(_st.skill_info(b["Skillidx"]))]
        fi = _st.fame_info()
        badf = [f["FameIdx"] for f in fpts if f["FameIdx"] >= len(fi) or fi[f["FameIdx"]][42] != f["Point"]]
        check("патчи ac0x/ac0w: AsdaSkillBase = SkillInfo.sif (%d), AsdaFamePoints = FameInfo.txt (%d) — иначе пересобрать" % (len(base), len(fpts)),
              not bad and not badf and len(fpts) == len(fi), (bad[:5], badf[:5]))
    s0 = snap()
    d = _sk.describe(2, idx)
    base = {"uid": 2, "idx": idx}
    steps = []
    if d["available"]:
        steps.append(("skill.grant", dict(base, skill=d["available"][0]["id"])))
    steps.append(("skill.remove", dict(base, skill=d["learned"][-1]["id"])))
    if d["trees"]:
        steps.append(("skill.reset_tree", dict(base, tree=int(next(iter(d["trees"]))))))
    steps.append(("skill.reset_all", dict(base)))
    steps.append(("skill.points", dict(base, value=(d["skill_point"] or 0) + 7)))
    pts = _pt.describe(2, idx)["pets"]
    if pts:
        steps.append(("pet.rename", dict(base, pet=pts[0]["PetUnique"], name="Selftest")))
        if pts[0]["PetMaxLvl"] and pts[0]["PetLvl"] != 1:
            steps.append(("pet.level", dict(base, pet=pts[0]["PetUnique"], level=1)))
    done = []
    try:
        for name, prm in steps:
            pv = ops.run(ctx, name, prm, dry=True)
            done.append(ops.run(ctx, name, dict(prm, expect=json.loads(json.dumps(pv["preview"]["expect"]))))["audit_id"])
        check("навыки и питомцы: записано %d операций (%s)" % (len(done), ", ".join(n for n, _p in steps)), len(done) == len(steps))
    finally:
        for a in reversed(done):
            ops.undo(ctx, a)
        check("навыки и питомцы: после откатов строки как были (CharSkill, SkillPoint, CharPetList)", snap() == s0)
    if not pts:
        print("     (у персонажа нет питомцев — pet.delete не проверяется)")
        return

    def psnap():                                     # без PetUnique: откат удаления даёт новый номер (по замыслу)
        with db.GameReader("joy1") as r:
            return r.rows("SELECT %s, CONVERT(varchar(23), Edate, 121) AS Edate FROM CharPetList WHERE Userindex = 2 AND Charidx = ? "
                          "ORDER BY Plate, Petindex, PetName" % ", ".join(_pt.COLS), (idx,))
    p0 = psnap()
    prm = dict(base, pet=pts[-1]["PetUnique"])
    pv = ops.run(ctx, "pet.delete", prm, dry=True)
    a = ops.run(ctx, "pet.delete", dict(prm, expect=json.loads(json.dumps(pv["preview"]["expect"]))))["audit_id"]
    try:
        check("питомец: удалён (перепроверка 21 М8)", len(psnap()) == len(p0) - 1)
    finally:
        ops.undo(ctx, a)
    check("питомец: откат удаления — питомец как был, вместе с датой получения Edate (новый PetUnique)", psnap() == p0)


def _move_town(m):
    from domains import charmove as _cm
    return _cm.TOWNS[m]


def _live_restore():
    """А1 «восстановление»: предпросмотр (без записи) на каждом наборе корзины — либо план, либо отказ с причиной, не сбой."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    with db.GameReader("joy1") as r:
        sets = r.rows("SELECT Userindex, Charidx, CONVERT(varchar(23), Edate, 121) AS e FROM Del_Charinfo")
    out = []
    for s in sets:
        try:
            pv = ops.run(ctx, "char.restore", {"uid": s["Userindex"], "idx": s["Charidx"], "edate": s["e"]}, dry=True)
            out.append(("plan", pv["preview"]["slot"]))
        except ops.OpRefused as ex:
            out.append(("refused", str(ex)[:40]))
    check("восстановление: предпросмотр на %d наборах корзины — план или отказ с причиной" % len(sets), sets and len(out) == len(sets),
          out)


def _live_jobchange():
    """А1 «смена профессии»: предпросмотр на живых персонажах (без записи) и запись с откатом на учётке 2, если есть цель."""
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    from domains import jobchange as _jc, srvtables as _st
    with db.GameReader("joy1") as r:
        rows = r.rows("SELECT Skillidx, %s FROM CharSkill WHERE Lvl = 0 AND Cooltime > 0" % ", ".join(_jc.ZERO))
    bad = [x["Skillidx"] for x in rows if not _st.skill_info(x["Skillidx"])
           or any(_st.skill_info(x["Skillidx"])["zero"][k] != x[k] for k in _jc.ZERO)]
    check("профессия: поля нулевого уровня SkillInfo = живые строки CharSkill (%d)" % len(rows), rows and not bad, bad[:5])
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT Flag, UserNum FROM Us_member WHERE Userindex = 2")
    if m["Flag"] != 0 or m["UserNum"] != -1:
        print("     (учётка 2 в игре — запись профессии не проверяется)")
        return
    with db.GameReader("joy1") as r:
        chars = r.rows("SELECT Charidx, Lvl, Class, Job, Subjob, JobCount FROM Charinfo WHERE Userindex = 2")
    c, t = None, None
    for x in chars:
        for tt in _jc.targets(x):
            try:
                ops.run(ctx, "char.job_change", {"uid": 2, "idx": x["Charidx"], "target": tt}, dry=True)
                c, t = x, tt
                break
            except ops.OpRefused:
                continue
        if c:
            break
    if not c:
        print("     (у персонажей учётки 2 нет допустимой смены профессии — запись не проверяется)")
        return

    def snap():
        with db.GameReader("joy1") as r:
            ci = r.one("SELECT %s FROM Charinfo WHERE Userindex = 2 AND Charidx = ?" % ", ".join(_jc.CI_COLS), (c["Charidx"],))
            sk = sorted((x["Skillidx"], x["Lvl"]) for x in r.rows("SELECT Skillidx, Lvl FROM CharSkill WHERE Userindex = 2 AND Charidx = ?",
                                                                 (c["Charidx"],)))
            fm = sorted(x["Fameidx"] for x in r.rows("SELECT Fameidx FROM CharFame WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],)))
            bk = r.rows("SELECT Fmpoint, Fame1 FROM CharFameBank WHERE Userindex = 2 AND Charidx = ?", (c["Charidx"],))
        return dict(ci), sk, fm, [dict(x) for x in bk]
    was = snap()
    p = {"uid": 2, "idx": c["Charidx"], "target": t}
    res = None
    try:
        res = ops.run(ctx, "char.job_change", dict(p, expect=ops.run(ctx, "char.job_change", p, dry=True)["preview"]["expect"]))
        now = snap()
        check("профессия: записана (Job %s → %s)" % (c["Job"], t["job"]), now[0]["Job"] == t["job"] and now != was)
        ok = ops.undo(ctx, res["audit_id"])["ok"]
        res = None
        check("профессия: откат вернул Charinfo, навыки и звания", ok and snap() == was)
    finally:
        if res:
            try:
                ops.undo(ctx, res["audit_id"])
            except Exception as ex:
                print("     !! откат профессии после сбоя: %s" % ex)


def _block_state(uid):
    with db.GameReader("asdastoryop") as r:
        m = r.one("SELECT us_block FROM Us_member WHERE Userindex = ?", (uid,))
        n = r.one("SELECT COUNT(*) AS n FROM BlockList WHERE Userindex = ?", (uid,))["n"]
        hst = r.one("SELECT COUNT(*) AS n FROM BlockHistory WHERE Userindex = ?", (uid,))["n"]
    return {"us_block": m["us_block"], "rows": n, "hist": hst}


def srvtables_type(code):
    from domains import srvtables
    r = srvtables.item_rule(code)
    return r["type"] if r else None


class _AccW:
    """Подставной писатель AsdaStoryOp/Joy1 для «Учёток» (19.11): Us_member одной строкой, BlockList, CharGmInfo — в памяти."""

    def __init__(self, st):
        self.st, self.done = st, False

    def rows(self, sql, params=()):
        st = self.st
        if "FROM dbo.Us_member" in sql and "BETWEEN 1 AND" in sql:
            return [{"Userindex": u} for u in st.get("service", [])]
        if "FROM dbo.Us_member" in sql and "Us_id = ?" in sql:
            return []
        if "FROM dbo.Us_member" in sql or "FROM AsdaStoryOp.dbo.Us_member" in sql:
            return [dict(st["m"])] if st.get("m") and params and int(params[0]) == st["m"]["Userindex"] else []
        if "FROM dbo.BlockList" in sql:
            return [dict(b) for b in st["blocks"]]
        if sql.startswith("INSERT INTO dbo.BlockList"):
            b = {"Userindex": params[0], "Uid": params[1], "Cou": 1, "grade": 1, "BlackDate": datetime.datetime(2026, 11, 19, 10, 0),
                 "CloseDate": datetime.datetime(2056, 11, 19, 10, 0), "Reason": params[2]}
            st["blocks"].append(b)
            return [dict(b)]
        if "FROM dbo.CharGmInfo" in sql:
            return [dict(r) for r in st["gm"]]
        if "FROM dbo.CharPos" in sql:
            return []
        if sql.startswith("INSERT INTO dbo.CharGmInfo"):
            r = {"UserIndex": params[0], "Charidx": params[1], "GMFlag": 1, "GMDate": datetime.datetime(2026, 11, 19, 10, 0, 0, 123000)}
            st["gm"].append(r)
            return [dict(r)]
        if sql.startswith("EXEC adm.ServiceAccountCreate"):
            st["created"] = params[0]
            return [{"Userindex": params[0]}]
        raise AssertionError("неожиданный запрос: " + sql[:80])

    def execute(self, sql, params=()):
        st = self.st
        if sql.startswith("UPDATE dbo.Us_member SET us_block"):
            st["m"]["us_block"] = params[0] if "= ?" in sql.split("WHERE")[0] else 5
            return 1
        if sql.startswith("UPDATE dbo.Us_member SET us_pwsalt = ?, us_pwhash = ?, us_pwset = GETDATE()"):
            st["m"].update(us_pwsalt=params[0], us_pwhash=params[1], us_pwset=datetime.datetime(2026, 11, 19, 10, 0), us_pwfail=0,
                           us_pwfail_at=None)
            return 1
        if sql.startswith("UPDATE dbo.Us_member SET us_pwsalt = ?, us_pwhash = ?, us_pwset = ?"):
            if bytes(st["m"]["us_pwsalt"]) != params[6]:
                return 0
            st["m"].update(us_pwsalt=params[0], us_pwhash=params[1], us_pwset=params[2], us_pwfail=params[3], us_pwfail_at=params[4])
            return 1
        if sql.startswith("DELETE TOP (1) FROM dbo.BlockList"):
            n = len(st["blocks"])
            st["blocks"] = [b for b in st["blocks"] if b["Reason"] != params[6]]
            return n - len(st["blocks"])
        if sql.startswith("DELETE FROM dbo.CharGmInfo WHERE UserIndex = ? AND"):
            n = len(st["gm"])
            st["gm"] = [r for r in st["gm"] if not (r["Charidx"] == params[1] and r["GMFlag"] == params[2])]
            return n - len(st["gm"])
        if sql.startswith("DELETE FROM dbo.CharGmInfo"):
            n = len(st["gm"])
            st["gm"] = []
            return n
        if sql.startswith("INSERT INTO dbo.CharGmInfo"):
            st["gm"].append({"UserIndex": params[0], "Charidx": params[1], "GMFlag": params[2], "GMDate": params[3]})
            return 1
        raise AssertionError("неожиданная запись: " + sql[:80])

    def commit(self):
        self.done = True

    def close(self):
        pass


def _vault_gc_check():
    """Ревизия 28 К-5: чистка adm.pw_saved на LocalDB — сирота старше часа удаляется, нужная откату и свежая — остаются."""
    import pyodbc
    from domains import accountclose
    name = "AsdaAdminSelftestGc_" + secrets.token_hex(4)
    try:
        m = _ldb("master")
    except pyodbc.Error as ex:
        return check("К-5: LocalDB доступна", False, ex)
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    try:
        cn = _ldb(name)
        _run_sql_file(cn, os.path.join(ROOT, "sql", "adminc_02_schema.sql"))
        keep, orphan, fresh = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        for t, age in ((keep, 120), (orphan, 120), (fresh, 1)):
            cn.cursor().execute("INSERT adm.pw_saved (token, uid, new_salt, at) VALUES (?, 7001, 0x01, DATEADD(MINUTE, ?, SYSDATETIME()))", t, -age)
        cn.cursor().execute("INSERT adm.audit (login, via, action, after_json, result) VALUES ('t', 'cli', 'account.close', ?, 'ok')",
                            json.dumps({"pw_token": keep.upper()}))
        cn.close()
        db.set_override("admin", lambda database: _ldb(name))
        try:
            n = accountclose.vault_gc()
        finally:
            db.set_override("admin", None)
        cn = _ldb(name)
        left = {str(r[0]).lower() for r in cn.cursor().execute("SELECT token FROM adm.pw_saved").fetchall()}
        cn.close()
        check("ревизия 28 К-5: чистка хранилища пароля — удалена только сирота старше часа", n == 1 and left == {keep, fresh}, (n, left))
    finally:
        try:
            m.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [%s]" % (name, name))
        except pyodbc.Error:
            pass
        m.close()


def _accounts_offline():
    """19.11 «Учётки»: закрыть, GM-флаг, служебная учётка, Discord, связи «одна машина» — без сети (подставные писатели)."""
    from domains import accountclose, accountnew, discordlinks, gmflag, players
    ctx_o, ctx_a = ops.Ctx(None, "t", "owner"), ops.Ctx(None, "t", "admin")
    check("учётки 19.11: права — закрыть owner/admin, GM-флаг и служебная учётка — только owner",
          auth.can("owner", "accounts.close") and auth.can("admin", "accounts.close") and not auth.can("gm", "accounts.close")
          and auth.can("owner", "accounts.gm_flag") and not auth.can("admin", "accounts.gm_flag")
          and auth.can("owner", "accounts.create_service") and not auth.can("admin", "accounts.create_service")
          and auth.can("gm", "players.view_net"))
    # служебная учётка: номер
    nx = accountnew.next_service_uid
    check("служебная учётка: номер — после занятых служебных (1, 2 → 3), пусто → 1, 5000 занят → наименьшая дыра, всё занято → нет",
          nx([1, 2]) == 3 and nx([]) == 1 and nx([1, 2, 75000]) == 3 and nx([1, 5000]) == 2
          and nx([u for u in range(1, 5001) if u != 77]) == 77 and nx(range(1, 5001)) is None and nx([0, 2]) == 3)
    st = {"service": [1, 2]}
    pl = accountnew.AccountCreateService()._plan(_AccW(st), {"login": "svc_test", "password": "Svc-12345"})
    check("служебная учётка: план — логин, номер 3, текст", pl[0] == "svc_test" and pl[2] == 3 and "номер 3" in pl[3])
    check("служебная учётка: свободных нет — отказ", raises(lambda: accountnew.AccountCreateService()._plan(
        _AccW({"service": list(range(1, 5001))}), {"login": "svc_x", "password": "Svc-12345"}), ops.OpRefused))
    _gw = db.GameWriter
    try:
        db.GameWriter = lambda key: _AccW(st)
        res = accountnew.AccountCreateService().apply(ctx_o, {"login": "svc_test", "password": "Svc-12345"},
                                                     {"expect": {"login": "svc_test", "uid": 3}})
        check("служебная учётка: запись — процедура adm.ServiceAccountCreate с номером 3, пароля в ответе нет",
              st.get("created") == 3 and res["after"] == {"uid": 3, "login": "svc_test", "service": True}
              and "Svc-12345" not in json.dumps({k: v for k, v in res.items() if not k.startswith("_")}, default=str))
        check("служебная учётка: номер сменился с предпросмотра — отказ", raises(lambda: accountnew.AccountCreateService().apply(
            ctx_o, {"login": "svc_test", "password": "Svc-12345"}, {"expect": {"login": "svc_test", "uid": 4}}), ops.OpRefused))
        # закрыть учётку: блок навсегда + случайный пароль; откат возвращает пароль
        salt0, hash0 = b"\x01" * 16, b"\x02" * 32
        pw0 = datetime.datetime(2026, 10, 1, 12, 0)
        st2 = {"m": {"Userindex": 7001, "Us_id": "victim", "us_block": 0, "Flag": 0, "UserNum": -1, "us_pwsalt": salt0,
                     "us_pwhash": hash0, "us_pwset": pw0, "us_pwfail": 3, "us_pwfail_at": datetime.datetime(2026, 11, 18, 9, 0, 0, 250000)},
               "blocks": [], "gm": []}
        db.GameWriter = lambda key: _AccW(st2)
        vault = {}
        _vp, _vg, _vd = accountclose._vault_put, accountclose._vault_get, accountclose._vault_drop
        accountclose._vault_put = lambda uid, m, ns: vault.setdefault("t1", {"uid": uid, "old_salt": m["us_pwsalt"], "old_hash": m["us_pwhash"],
                                                                         "old_pwset": m["us_pwset"], "new_salt": ns}) and "t1"
        accountclose._vault_get = lambda t: vault.get(t)
        accountclose._vault_drop = lambda t: vault.pop(t, None)
        try:
            op = accountclose.AccountClose()
            check("закрыть: служебную (≤ 5000) — только владелец; причина кириллицей — отказ",
                  raises(lambda: op._plan(_AccW({"m": dict(st2["m"], Userindex=2), "blocks": []}), {"uid": 2}, ctx_a), ops.OpRefused)
                  and raises(lambda: op._plan(_AccW(st2), {"uid": 7001, "reason": "читер"}, ctx_a), ops.OpRefused)
                  and raises(lambda: op._plan(_AccW(st2), {"uid": 7001, "reason": "x" * 290}, ctx_a), ops.OpRefused))
            p = {"uid": 7001, "reason": "cheating", "password_reset": True}
            sig = accountclose._sig(st2["m"], [])
            res = op.apply(ctx_a, p, {"expect": sig})
            res.pop("_commit")()
            m = st2["m"]
            check("закрыть: блок навсегда (us_block 5, причина «account closed: …», 30 лет), новый пароль, прежний — в хранилище",
                  m["us_block"] == 5 and len(st2["blocks"]) == 1 and st2["blocks"][0]["Reason"] == "account closed: cheating"
                  and m["us_pwsalt"] != salt0 and m["us_pwhash"] != hash0 and vault["t1"]["old_hash"] == hash0
                  and res["after"]["pw_token"] == "t1" and "old_hash" not in json.dumps(res["after"], default=str)
                  and accountclose.closed_state(st2["blocks"], datetime.datetime(2026, 11, 20)))
            row = {"after_json": audit.to_json(res["after"])}
            u = op.undo(ctx_o, row)
            u.pop("_commit")()
            check("закрыть: откат — блок снят, прежние соль/хеш/дата пароля, копия из хранилища удалена",
                  m["us_block"] == 0 and not st2["blocks"] and m["us_pwsalt"] == salt0 and m["us_pwhash"] == hash0 and m["us_pwset"] == pw0
                  and "t1" not in vault and u["after"]["pw_restored"] and m["us_pwfail"] == 3
                  and m["us_pwfail_at"] == datetime.datetime(2026, 11, 18, 9, 0, 0, 250000))
            # пароль сменили после закрытия — откат отказывает
            res = op.apply(ctx_a, p, {"expect": accountclose._sig(m, [])})
            res.pop("_commit")()
            m["us_pwsalt"] = b"\x09" * 16
            check("закрыть: пароль с тех пор меняли — откат отказ, ничего не вернули",
                  raises(lambda: op.undo(ctx_o, {"after_json": audit.to_json(res["after"])}), ops.OpRefused))
            # без смены пароля — хранилище не трогается
            st2.update(blocks=[])
            m.update(us_block=0)
            vault.clear()
            res = op.apply(ctx_a, {"uid": 7001}, {"expect": accountclose._sig(m, [])})
            check("закрыть без смены пароля: причина «account closed», пароль прежний, хранилище пусто",
                  st2["blocks"][-1]["Reason"] == "account closed" and m["us_pwsalt"] == b"\x09" * 16 and not vault and res["after"]["pw_token"] is None)
        finally:
            accountclose._vault_put, accountclose._vault_get, accountclose._vault_drop = _vp, _vg, _vd
        # GM-флаг
        st3 = {"m": {"Userindex": 2, "Us_id": "Rimy", "Flag": 0, "UserNum": -1}, "gm": []}
        db.GameWriter = lambda key: _AccW(st3)
        check("GM-флаг: игровой учётке (> 5000) — отказ; неверный номер — отказ",
              raises(lambda: gmflag._uid({"uid": 5001}), ops.OpRefused) and raises(lambda: gmflag._uid({"uid": "x"}), ops.OpRefused)
              and gmflag._uid({"uid": 5000}) == 5000)
        g = gmflag.GmGrant()
        res = g.apply(ctx_o, {"uid": 2}, {"expect": gmflag._sig([])})
        res.pop("_commit")()
        check("GM-флаг: выдача — строка (2, слот 0, флаг 1) как OPCharGMUpdate режим 0",
              st3["gm"] and st3["gm"][0]["Charidx"] == 0 and st3["gm"][0]["GMFlag"] == 1 and res["after"]["row"]["GMDate"] == "2026-11-19 10:00:00.123")
        check("GM-флаг: повторная выдача — отказ «уже есть»", raises(lambda: g._plan(_AccW(st3), {"uid": 2}), ops.OpRefused))
        u = g.undo(ctx_o, {"after_json": audit.to_json(res["after"])})
        u.pop("_commit")()
        check("GM-флаг: откат выдачи — строки нет", not st3["gm"])
        st3["gm"] = [{"UserIndex": 2, "Charidx": 0, "GMFlag": 1, "GMDate": datetime.datetime(2010, 7, 8, 17, 45, 10, 793000)}]
        rv = gmflag.GmRevoke()
        res = rv.apply(ctx_o, {"uid": 2}, {"expect": gmflag._sig(gmflag._rows(_AccW(st3), 2))})
        res.pop("_commit")()
        check("GM-флаг: снятие — все строки учётки удалены, снимок с датой", not st3["gm"] and res["after"]["rows"][0]["GMDate"] == "2010-07-08 17:45:10.793")
        u = rv.undo(ctx_o, {"after_json": audit.to_json(res["after"])})
        u.pop("_commit")()
        check("GM-флаг: откат снятия — строка с прежней датой 2010-07-08 17:45:10.793",
              len(st3["gm"]) == 1 and st3["gm"][0]["GMDate"] == datetime.datetime(2010, 7, 8, 17, 45, 10, 793000))
        check("GM-флаг: снятие при пустой учётке — отказ; откат снятия при новых строках — отказ",
              raises(lambda: rv._plan(_AccW({"m": st3["m"], "gm": []}), {"uid": 2}), ops.OpRefused)
              and raises(lambda: rv.undo(ctx_o, {"after_json": audit.to_json(res["after"])}), ops.OpRefused))
    finally:
        db.GameWriter = _gw
    # ревизия 28 М-1: снятие у игровой учётки (> 5000) — можно (owner), выдача — нет; откат снятия предупреждает об обходах
    st4 = {"m": {"Userindex": 75215, "Us_id": "Player54", "Flag": 0, "UserNum": -1},
           "gm": [{"UserIndex": 75215, "Charidx": 0, "GMFlag": 1, "GMDate": datetime.datetime(2026, 11, 1, 10, 0)}]}
    _gw2 = db.GameWriter
    try:
        db.GameWriter = lambda key: _AccW(st4)
        rv4 = gmflag.GmRevoke()
        pl4 = rv4._plan(_AccW(st4), {"uid": 75215})
        res4 = rv4.apply(ctx_o, {"uid": 75215}, {"expect": gmflag._sig(pl4[2])})
        res4.pop("_commit")()
        u4 = rv4.undo(ctx_o, {"after_json": audit.to_json(res4["after"])})
        check("ревизия 28 М-1: снятие GM-флага у учётки 75215 — можно, выдача — отказ; откат снятия предупреждает об обходах",
              gmflag._uid({"uid": 75215}, grant=False) == 75215 and raises(lambda: gmflag._uid({"uid": 75215}), ops.OpRefused)
              and raises(lambda: gmflag.GmGrant()._plan(_AccW(dict(st4, gm=[])), {"uid": 75215}), ops.OpRefused)
              and len(st4["gm"]) == 1 and "снова обходит" in u4["message"] and "откат этого снятия" in gmflag.UNDO_GAME_WARN)
    finally:
        db.GameWriter = _gw2
    # ревизия 28 М-2: открытая сессия игрока в игре длится до «сейчас»
    _t = lambda h: datetime.datetime(2026, 11, 1, h)
    me_open = players.mark_open([{"IpAddress": "9.165.147.34", "Mac": "", "Login": _t(10), "Logout": None}], True)
    me_dead = players.mark_open([{"IpAddress": "9.165.147.34", "Mac": "", "Login": _t(10), "Logout": None}], False)
    th = [{"IpAddress": "9.165.147.34", "Mac": "", "Login": _t(11), "Logout": _t(12)}]
    check("ревизия 28 М-2: игрок в игре с 10:00, вторая учётка 11–12 с того же IP → «общая сеть»; незакрытая строка после сбоя — точка",
          players.link_degree(me_open, th, {"9.165.147.34": 2}, _t(13))[0] == "ip_net"
          and players.link_degree(me_dead, th, {"9.165.147.34": 2}, _t(13))[0] == "ip_apart" and me_open[0].get("_open"))
    _pl = open(os.path.join(ROOT, "domains", "players.py"), encoding="utf-8").read()
    _s9 = open(os.path.join(ROOT, "sql", "adminc_09_accounts.sql"), encoding="utf-8").read()
    _g4 = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read().split("USE [AsdaStoryOp];", 1)[1]
    _v11 = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
    _dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("ревизия 28 К-1/К-2: логин процедуры VARCHAR(61) с проверкой ≤ 32; у пользователя сертификата только ALTER Us_member (+самопроверка)",
          "@Us_id     VARCHAR(61)" in _s9 and "DATALENGTH(@Us_id) > 32" in _s9 and "GRANT ALTER ON dbo.Us_member TO adm_SvcAccSign_u;" in _s9
          and "GRANT SELECT, INSERT" not in _s9 and "THROW 51098" in _s9 and "THROW 51097" in _s9)
    check("ревизия 28 К-3: явные DENY ALTER ANY USER/ROLE/CERTIFICATE, CREATE SCHEMA, ALTER схемы adm; проверки adminc_11",
          "ALTER ANY USER, ALTER ANY ROLE" in _g4 and "CREATE SCHEMA" in _g4 and "DENY ALTER ON SCHEMA::adm TO [asda_ops];" in _g4
          and "ALTER ANY SCHEMA" not in _g4.split("*/")[-1] and all(x in _v11 for x in ("'ops.Op DATABASE ALTER'", "'ops.Op ALTER ANY USER'",
                                                                                         "'ops.Op CREATE SCHEMA'", "'ops.Op CONTROL'")))
    check("ревизия 28 К-6/К-7: подарки gp7 — имена через to_db_text / fix_text; TOP 20000 с ORDER BY",
          "db.to_db_text(r[\"Charname\"])" in _pl and "db.fix_text(r[\"recipient_name\"])" in _pl and "ORDER BY idx DESC\" % (ip_in, mac_in)" in _pl)
    check("ревизия 28 К-8: сбой шага SQL/прав — прежняя установка возвращается и задача запускается",
          "def restore_previous(stamp):" in _dep and "restore_previous(stamp)\n        return 2" in _dep and "Start-ScheduledTask" in _dep.split("def restore_previous", 1)[1])
    _vault_gc_check()
    src = open(os.path.join(ROOT, "domains", "gmflag.py"), encoding="utf-8").read()
    check("GM-флаг: стоковые OPCharGMDelete / OPCharGMUpdate панель не вызывает",
          not re.search(r"(rows|execute)\(\s*\"[^\"]*EXEC", src) and "OPCharGMDelete" in src and not re.search(r"\bOPCharGMDelete\s*@", src))
    # Discord
    lines = ["# Формат: Discord-имя (@handle) [discord_uid] - логин/пароль",
             "Some Name (@some.one) [123456789012345678]   -   login_a/SecretPw1",
             "# BANNED 2026-10-27 ! Bad (@._bad) [223456789012345678]   -    bad_b/AnotherSecret",
             "garbage line"]
    lk = discordlinks.parse_playtest(lines)
    js = json.dumps(lk)
    check("Discord: разбор файла бота — @handle, ID, логин, пометка бана; ПАРОЛЕЙ в результате нет",
          lk == [{"handle": "some.one", "discord_id": "123456789012345678", "login": "login_a", "banned": None},
                 {"handle": "._bad", "discord_id": "223456789012345678", "login": "bad_b", "banned": "2026-10-27"}]
          and "SecretPw1" not in js and "AnotherSecret" not in js)
    check("Discord: поиск по ID (точно) и @handle (по началу, без регистра); номер учётки — не Discord",
          discordlinks.find("123456789012345678", lk) == [("login_a", "Discord ID")]
          and discordlinks.find("@SOME", lk) == [("login_a", "Discord @some.one")] and discordlinks.find("75215", lk) == []
          and discordlinks.find("@", lk) == [])
    bl = {"state": "none"}
    check("Discord: в реестре банов и вход открыт — расхождение; заблокирован — нет",
          discordlinks.card(75219, "login_a", bl, lk, {75219: "x"})["mismatch"]
          and not discordlinks.card(75219, "login_a", {"state": "active"}, lk, {75219: "x"})["mismatch"]
          and not discordlinks.card(75220, "LOGIN_A", bl, lk, {75219: "x"})["mismatch"]
          and discordlinks.card(1, "LOGIN_A", bl, lk, {})["handle"] == "some.one")
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("Discord: выкладка кладёт discord_links.json через разбор, файл бота с паролями в пакет не идёт",
          "discordlinks.build_json(pt)" in dep and "z.write(pt" not in dep)
    # связи «одна машина»
    check("связи: MAC Hyper-V 00-15-5D, VMware, VirtualBox и локально назначенный (02-…) — не в счёт; реальный — в счёт",
          not players._linkable_mac("00-15-5D-01-02-03") and not players._linkable_mac("00-50-56-aa-bb-cc")
          and not players._linkable_mac("08-00-27-11-22-33") and not players._linkable_mac("02-11-22-33-44-55")
          and not players._linkable_mac("DA-A1-19-00-00-01") and players._linkable_mac("74-56-3C-11-22-33"))
    T = lambda h1, h2: (datetime.datetime(2026, 11, 1, h1), datetime.datetime(2026, 11, 1, h2))
    ses = lambda ip, mac, t: {"IpAddress": ip, "Mac": mac, "Login": t[0], "Logout": t[1]}
    me = [ses("9.165.147.34", "74-56-3C-11-22-33", T(10, 12))]
    check("связи: MAC и IP → «MAC+IP»; только MAC → «MAC»",
          players.link_degree(me, [ses("9.165.147.34", "74-56-3C-11-22-33", T(13, 14))], {"9.165.147.34": 2})[0] == "mac_ip"
          and players.link_degree(me, [ses("8.8.4.4", "74-56-3C-11-22-33", T(13, 14))], {})[0] == "mac")
    check("связи: общий IP, сессии не пересекались → «IP (не пересекались)»; одновременно → «IP (общая сеть)» (разные машины за NAT)",
          players.link_degree(me, [ses("9.165.147.34", "2C-F0-5D-00-00-01", T(13, 14))], {"9.165.147.34": 2})[0] == "ip_apart"
          and players.link_degree(me, [ses("9.165.147.34", "2C-F0-5D-00-00-01", T(11, 13))], {"9.165.147.34": 2})[0] == "ip_net")
    check("связи: на IP больше 5 учёток → «IP (общая сеть)»; общий только виртуальный MAC → связи нет",
          players.link_degree(me, [ses("9.165.147.34", "2C-F0-5D-00-00-01", T(13, 14))], {"9.165.147.34": 6})[0] == "ip_net"
          and players.link_degree([ses("0", "00-15-5D-01-02-03", T(10, 12))], [ses("0", "00-15-5D-01-02-03", T(13, 14))], {})[0] is None)


LIVE_BLOCKS = {   # ★ А4.7: живые блоки для выборочного прогона (--live --only …)
    "shops": "selftest_shops", "data": "selftest_data_a4", "texts": "selftest_texts_a4", "monsters": "selftest_monsters_a4",
    "items": "selftest_items_a4", "quests": "selftest_quests_a4", "titles": "selftest_titles_a4", "skills": "selftest_skills_a4",
    "maps": "selftest_maps_a4",                                         # ★ А4.8
    "stack": "selftest_stack_a5",                                       # ★ А5.1 (20.11): стойка и планировщик adm.job
    "live": "selftest_live_a5",                                         # ★ А5.2 (21.11): кто в игре, перенос к персонажу, монстры 6045/6046
    "maint": "selftest_maint_a5",                                       # ★ А5.3 (21.11): режим обслуживания (SQL L09, DLL L09) — только чтение
    "events": "selftest_events_a5",                                     # ★ А5.4 (21.11): события, счастливые часы, рейтинги, ежедневные — только чтение
    "patchcfg": "selftest_patchcfg_a5",                                 # ★ А5.5 (21.11): ini DLL всех копий, журналы патчей, конфиги — только чтение
    "logs": "selftest_logs_a5",                                         # ★ А5.6 (21.11): хвост серверных журналов — только чтение
    "dbbackup": "selftest_dbbackup_a5",                                 # ★ А5.7 (21.11): бэкапы БД — чтение и состояние, новых бэкапов не делает
    "bakdrop": "selftest_bakdrop_a5",                                   # ★ А5.8 (21.11): служебные копии — список и сухой предпросмотр, ничего не удаляет
    "acjournal": "selftest_ac_a6",                                      # ★ А6.1 (21.11): журнал античита ac.* — только чтение
    "money": "selftest_money_a6",                                       # ★ А6.2 (21.11): деньги gp7 — только чтение
    "econ": "selftest_econ_a6",                                         # ★ А6.3 (21.11): экономика — золото; снимок пишет только AsdaAdmin
    "trade": "selftest_trade_a6",                                       # ★ А6.4 (22.11): передачи, аукцион, лавки — только чтение
    "odds": "selftest_odds_a6",                                         # ★ А6.5 (22.11): шансы — выпало против заявленного, только чтение
    "acdaily": "selftest_acdaily_a6",                                   # ★ А6.6 (22.11): суточный отчёт античита — чтение, предпросмотр без записи
    "autoblock": "selftest_autoblock_a6",                               # ★ А6.8 (22.11): лестница против patches.ini, история автоблоков, EAC — только чтение
    "names": "selftest_names_a6",                                       # ★ А6.11 (22.11): очередь имён — чтение, предпросмотр отметки без записи
    "cases": "selftest_cases_a6",                                       # ★ А6.7 (22.11): дела san.* — только чтение (список, AC-0001, verify службы)
    "reports": "selftest_reports_a6",                                   # ★ А6.11 (22.11): жалобы игроков — только чтение (права, путь бота, очередь, служба)
    "chat": "selftest_chat_a6",                                         # ★ А6.12 (22.11): журнал чата — только чтение (состояние схемы chat, режим P129, права asda_admin)
    "attendance": "selftest_attendance_a6",                             # ★ А6.10 (23.11): посещаемость — сверка процедур сервера, права, сводка; запись с откатом только учётке 2
    "releases": "selftest_releases_a7",                                 # ★ А7.1 (23.11): выпуски — сервер обновлений, права adm.ReleasePcStatus, release.push с ПК (только AsdaAdmin), служба
    "crashes": "selftest_crashes_a7",                                   # ★ А7.2 (23.11): сбои клиента — список LogDrop по SSH = квоте, права adm.ClientCrash*, crash.sync с ПК (только AsdaAdmin), служба
    "outbox": "selftest_outbox_a7",                                     # ★ А7.4 (23.11): очередь Discord — права adm.Outbox*, путь бота asda_reports, только проверочная запись (в Discord ничего), служба
    "telegram": "selftest_telegram_a7",                                 # ★ А7.5 (23.11): Telegram владельцу — права adm.Notify* / adm.Tg*, путь отправителя asda_reports, только проверка selftest (Telegram не вызывается), служба
    "community": "selftest_community_a7",                               # ★ А7.6 (24.11): «Сообщество» — права adm.Bot*, путь бота asda_reports, свежесть копии реестра, только команды «тест» (в Discord ничего), служба
    "notes": "selftest_notes_a7",                                       # ★ А7.7 (24.11): заметки к выпуску — права adm.Notes*, путь бота asda_reports, снимок changelog с ПК (только AsdaAdmin), только публикация «тест» (в Discord ничего), служба
    "opdoc": "selftest_opdoc_a7"}                                       # ★ А7.10 (24.11): справка по операциям — каталог службы полон по её реестру (SSH), /api/opdoc без входа — 401
PROBE = r'''# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
from domains import shopdata
from domains.cs_kinds import skilldata as K
import domains.shopview as V
r = V.lookup("skill", "503")
s = V.lookup("skills", "")
m = V.lookup("maps", "")
c = V.lookup("map", "3")
print("PROBE_OK areas=%d kinds=%d levels=%d client=%s holders=%s skills=%d" % (
    len(shopdata.AREAS), len(shopdata.KINDS), len(r["levels"]), r["client"] is not None, r["holders"] is not None, len(s["rows"])))
print("PROBE_MAPS maps=%d cfg=%s crystals=%d captions=%d holders=%s" % (
    len(m["rows"]), m["cfg_error"] is None, len(c["crystals"] or []), len(c["captions"]), c["holders"] is not None))
'''


def part_live_quick():
    """★ А4.7: быстрые живые проверки службы — ответ 401 без входа (HTTPS, VPN) и справка новой области в коде службы НА СЕРВЕРЕ
    (SSH, python службы, проба через stdin — без файлов на сервере; только чтение: lookup навыка 503 и поиск — таблицы стойки, снимок
    клиента, Joy1 SELECT)."""
    import ssl
    import subprocess
    import urllib.error
    import urllib.request
    from core import config
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    code = None
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/me" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/me без входа — 401 (служба жива и требует входа)", code == 401, code)
    # ★ А6.13 (22.11): длинный скрипт (> hostshell.LONG_ENC знаков base64 — путь через stdin) по SSH выполняется и отдаёт вывод целиком
    #   (было: [Console]::In.ReadToEnd() по SSH ждал конца ввода до таймаута — живые блоки с md5 сотен файлов падали «не уложилась в N с»)
    import base64 as _b64
    from core import hostshell
    _long = "$n = 0\n" + "$n += 1\n" * 1500 + "'LONG|' + $n + '|кириллица'"
    _t0 = time.time()
    try:
        _out = hostshell.powershell(_long, timeout=60).strip()
    except hostshell.HostError as ex:
        _out = "ОТКАЗ: %s" % ex
    check("хост (живьём, SSH): длинный скрипт через stdin (%d знаков base64 > %d) выполнен целиком за %.1f с, вывод UTF-8 верный"
          % (len(_b64.b64encode(_long.encode("utf-16-le"))), hostshell.LONG_ENC, time.time() - _t0),
          _out.endswith("LONG|1500|кириллица"), _out[-200:])
    # ★ ревизия 39 Н-4: проба — через stdin (python -), без файла на сервере: только чтение, никакой записи (прежде проба копировалась
    #   временным файлом в профиль Administrator и удалялась — это была запись на сервер)
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH")
    ssh = os.path.join(exe, "ssh.exe") if os.path.isdir(exe) else "ssh"
    opt = ["-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    try:
        r = subprocess.run([ssh] + opt + [config.SSH_HOST, r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                                                          r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=PROBE.encode("utf-8"), capture_output=True, timeout=600)
        out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    m = re.search(r"PROBE_OK areas=(\d+) kinds=(\d+) levels=(\d+) client=(\w+) holders=(\w+) skills=(\d+)", out)
    check("служба на сервере (код службы, SSH): 13 областей / 40 видов (★ А5.4: + «Счастливые часы»; ★ А5.5: + «Настройки патчей»), справка «Навыки и классы» — навык 503 "
          "(уровни, клиент из снимка, держатели из Joy1), поиск ≥ 400 навыков", bool(m) and m.group(1) == "13" and m.group(2) == "40" and int(m.group(3)) > 0
          and m.group(4) == "True" and m.group(5) == "True" and int(m.group(6)) >= 400, out[-600:])
    mm = re.search(r"PROBE_MAPS maps=(\d+) cfg=(\w+) crystals=(\d+) captions=(\d+) holders=(\w+)", out)
    check("служба на сервере (код службы, SSH): справка «Карты» — ≥ 24 карт, patches.ini прочитан, у Альпии кристаллы P40 и подписи кнопок из "
          "снимка клиента, персонажи из Joy1", bool(mm) and int(mm.group(1)) >= 24 and mm.group(2) == "True" and int(mm.group(3)) > 0
          and int(mm.group(4)) > 0 and mm.group(5) == "True", out[-600:])


def _guard(name, fn, *args):
    """★ 25.11 (К-3): блок самотеста; нет файла только среды разработчика — SKIP остатка блока (selftest_public.guard), прочее — как раньше."""
    return P.guard(name, fn, *args)


def main_only(blocks):
    """★ А4.7: выборочный живой прогон — быстрые проверки службы и названные живые блоки (офлайн не гоняется)."""
    import importlib
    bad_names = [b for b in blocks if b not in LIVE_BLOCKS]
    if bad_names:
        raise SystemExit("неизвестные живые блоки %s (есть: %s)" % (", ".join(bad_names), ", ".join(LIVE_BLOCKS)))
    print("== C0. служба: быстрые живые проверки")
    part_live_quick()
    for b in blocks:
        print("== C. живой блок %s" % b)
        importlib.import_module(LIVE_BLOCKS[b]).live(check)
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГ: %d проверок, ошибок %d (выборочно: %s)" % (len(RESULTS), len(bad), ", ".join(blocks)))
    return 1 if bad else 0


def main(live=False, only=None):
    if only is not None and not (live and only):       # ★ ревизия 39 Н-4: не молча в полный прогон
        raise SystemExit("--only — только с --live и непустым списком блоков")
    if live and only:
        return main_only(only)
    print("== A. примитивы")
    _guard("part_a", part_a)
    print("== A1. учётки 19.11 (закрыть, GM-флаг, служебная учётка, Discord, связи)")
    _guard("_accounts_offline", _accounts_offline)
    print("== A3. мост P127 (подставной мост, LocalDB)")
    _guard("part_bridge", part_bridge)
    print("== A3b. мост v81: живые правки (подставной мост)")
    _guard("part_bridge_live", part_bridge_live)
    print("== A3c. мост v82: выдача предмета и перенос в своей карте живьём")
    _guard("part_bridge_give", part_bridge_give)
    print("== A2. HTTPS")
    _guard("part_tls", part_tls)
    print("== A4. магазины: наборы изменений (А3 19.11; подменная стойка, LocalDB)")
    import selftest_shops
    _guard("selftest_shops.offline", selftest_shops.offline, check, _ldb)
    print("== A5. данные игры А4.0/А4.1: реестр видов, ведомости ItemDB, баланс, 6800 / честь / причёски (19.11)")
    import selftest_data_a4
    _guard("selftest_data_a4.offline", selftest_data_a4.offline, check, _ldb)
    if _ldb:
        _guard("selftest_data_a4.sandbox_a4", selftest_data_a4.sandbox_a4, check, _ldb)
    print("== A6. данные игры А4.2: тексты RU / EN (вид text.set, ведомости, план на копиях, песочница)")
    import selftest_texts_a4
    _guard("selftest_texts_a4.offline", selftest_texts_a4.offline, check)
    if _ldb:
        _guard("selftest_texts_a4.sandbox", selftest_texts_a4.sandbox, check, _ldb)
    print("== A7. данные игры А4.3: монстры и добыча (дроп, деньги, мировой, квестовый, опыт, копание; песочница выкладки)")
    import selftest_monsters_a4
    _guard("selftest_monsters_a4.offline", selftest_monsters_a4.offline, check)
    if _ldb:
        _guard("selftest_monsters_a4.sandbox", selftest_monsters_a4.sandbox, check, _ldb)
    print("== A8. данные игры А4.4: предметы (item_table + item_list, Cellob + sowell_list; дюпы, баланс, ведомости, песочница)")
    import selftest_items_a4
    _guard("selftest_items_a4.offline", selftest_items_a4.offline, check)
    if _ldb:
        _guard("selftest_items_a4.sandbox", selftest_items_a4.sandbox, check, _ldb)
    print("== A9. данные игры А4.5: задания (награды RepayTable ↔ RewardTable, доска LimitationQuest; перепроверка, песочница)")
    import selftest_quests_a4
    _guard("selftest_quests_a4.offline", selftest_quests_a4.offline, check)
    if _ldb:
        _guard("selftest_quests_a4.sandbox", selftest_quests_a4.sandbox, check, _ldb)
    print("== A10. данные игры А4.6: звания (FameInfo ↔ title_list: очки, включено, условия, бонусы; держатели, перепроверка, песочница)")
    import selftest_titles_a4
    _guard("selftest_titles_a4.offline", selftest_titles_a4.offline, check)
    if _ldb:
        _guard("selftest_titles_a4.sandbox", selftest_titles_a4.sandbox, check, _ldb)
    print("== A11. данные игры А4.7: навыки и классы (SkillInfo ×6 ↔ skill_info, SkillPointTable, ClassStat, ExpTable ↔ charexp; Joy1, "
          "перепроверка, AsdaSkillBase, песочница)")
    import selftest_skills_a4
    _guard("selftest_skills_a4.offline", selftest_skills_a4.offline, check)
    if _ldb:
        _guard("selftest_skills_a4.sandbox", selftest_skills_a4.sandbox, check, _ldb)
    print("== A12. данные игры А4.8: карты (MapWarpCost ×3 GS, OpenMapInfo копий поля ↔ реестр карт порта; P40, потоки, персонажи на карте, "
          "перепроверка, песочница)")
    import selftest_maps_a4
    _guard("selftest_maps_a4.offline", selftest_maps_a4.offline, check)
    if _ldb:
        _guard("selftest_maps_a4.sandbox", selftest_maps_a4.sandbox, check, _ldb)
    print("== A13. живое управление А5.1: стойка (restart_stack на подменах, отсчёт в игре, --stop-only) и планировщик adm.job (LocalDB)")
    import selftest_stack_a5
    _guard("selftest_stack_a5.offline", selftest_stack_a5.offline, check)
    if _ldb:
        _guard("selftest_stack_a5.sandbox", selftest_stack_a5.sandbox, check, _ldb)
    print("== A14. живое управление А5.2: кто в игре, перенос к персонажу (6012/6014), монстры 6045/6046 (мост v83, подмены)")
    import selftest_live_a5
    _guard("selftest_live_a5.offline", selftest_live_a5.offline, check)
    print("== A15. живое управление А5.3: режим обслуживания (операции на подменах, задания, DLL по журналу патчей; стенд SQL L09 на своём "
          "экземпляре LocalDB — живое тело UPUserLogin, миграция, все ветки входа, права, откат байт в байт)")
    import selftest_maint_a5
    _guard("selftest_maint_a5.offline", selftest_maint_a5.offline, check)
    if _ldb:
        _guard("selftest_maint_a5.sandbox", selftest_maint_a5.sandbox, check, _ldb)
    print("== A16. живое управление А5.4: события 6038/6040 и рейтинги 6020 (мост v84, подмены), счастливые часы (набор изменений), "
          "ежедневные задания доски (стенд adm.LimitationReset на LocalDB)")
    import selftest_events_a5
    _guard("selftest_events_a5.offline", selftest_events_a5.offline, check)
    if _ldb:
        _guard("selftest_events_a5.sandbox", selftest_events_a5.sandbox, check, _ldb)
    print("== A17. живое управление А5.5: настройки серверных патчей (каталог по исходникам DLL, ini с сохранением формата, patch.set / "
          "config.set на подставной стойке, состояние по журналу патчей, конфиги без секретов; песочница — НАСТОЯЩИЙ deploy_changeset)")
    import selftest_patchcfg_a5
    _guard("selftest_patchcfg_a5.offline", selftest_patchcfg_a5.offline, check)
    if _ldb:
        _guard("selftest_patchcfg_a5.sandbox", selftest_patchcfg_a5.sandbox, check, _ldb)
    print("== A18. живое управление А5.6: журналы стойки (белый список пути, маскировка секретов и IP, кодировки, хвост, «следить» без "
          "открытия данных, EventLog share 0, открытие файла против писателей с режимами доступа серверов, пределы, веб, консоль)")
    import selftest_logs_a5
    _guard("selftest_logs_a5.offline", selftest_logs_a5.offline, check)
    print("== A19. живое управление А5.7: бэкапы БД (план уборки, пути, права, отказы, переводы; свой экземпляр LocalDB — настоящий "
          "adminc_16 с подписью, бэкап и VERIFYONLY под asda_admin, задание службы, уборка, испорченный файл, стенд RESTORE … WITH MOVE + CHECKDB)")
    import selftest_dbbackup_a5
    _guard("selftest_dbbackup_a5.offline", selftest_dbbackup_a5.offline, check)
    if _ldb:
        _guard("selftest_dbbackup_a5.sandbox", selftest_dbbackup_a5.sandbox, check, _ldb)
    print("== A20. живое управление А5.8: уборка служебных копий *_bak_* (каталог и файлы откатов, имена вне кода DLL, права, отказы, "
          "переводы; свой экземпляр LocalDB — настоящие adminc_16 + adminc_17, отказы процедуры в обход панели, откат транзакции, снимок)")
    import selftest_bakdrop_a5
    _guard("selftest_bakdrop_a5.offline", selftest_bakdrop_a5.offline, check)
    if _ldb:
        _guard("selftest_bakdrop_a5.sandbox", selftest_bakdrop_a5.sandbox, check, _ldb)
    print("== A21. А6.1 «Античит»: журнал joylog1.ac.* (каталог видов по KindText, служебные строки, фильтры и отказы, права, маршруты, "
          "переводы, веб, консоль; свои базы LocalDB — настоящие миграции схемы ac, синтетика 8 таблиц, лента, сводка, таблицы нет)")
    import selftest_ac_a6
    _guard("selftest_ac_a6.offline", selftest_ac_a6.offline, check)
    if _ldb:
        _guard("selftest_ac_a6.sandbox", selftest_ac_a6.sandbox, check, _ldb)
    print("== A22. А6.2 «Деньги: чтение»: монетизация gp7 (проверка ввода и отказы, право money.view, маршруты, переводы, веб, консоль, выкладка "
          "сверки; свои базы LocalDB — настоящий установщик шлюза, синтетика покупок, подарков и стока, висящие против gift_reconcile, нет таблицы)")
    import selftest_money_a6
    _guard("selftest_money_a6.offline", selftest_money_a6.offline, check)
    if _ldb:
        _guard("selftest_money_a6.sandbox", selftest_money_a6.sandbox, check, _ldb)
    print("== A23. А6.3 «Экономика: золото»: каталог источников по реверсу (знак, владелец строки), отказы, права econ.view / econ.snapshot, "
          "маршруты, планировщик, переводы, веб, консоль, выкладка adminc_18; свои базы LocalDB — снимки, потоки, неучтённое, богатейшие, редкое)")
    import selftest_econ_a6
    _guard("selftest_econ_a6.offline", selftest_econ_a6.offline, check)
    if _ldb:
        _guard("selftest_econ_a6.sandbox", selftest_econ_a6.sandbox, check, _ldb)
    print("== A24. А6.4 «Передачи и рынок»: каталог «кто кому» по реверсу, зеркала и правило M3 (тот же ac_metrics_db), цепочки, отказы, право "
          "econ.view, маршруты, переводы, веб, консоль, выкладка ext/anticheat; свои базы LocalDB — пары, сеть по праву, рынок, лавки, нет таблицы)")
    import selftest_trade_a6
    _guard("selftest_trade_a6.offline", selftest_trade_a6.offline, check)
    if _ldb:
        _guard("selftest_trade_a6.sandbox", selftest_trade_a6.sandbox, check, _ldb)
    print("== A25. А6.5 «Шансы: выпало против заявленного»: формулы без SciPy на известных значениях, критерий на синтетике генератором сервера, "
          "свитки и шанс заточки по реверсу, Log_GachaItem, журнал шлюза, отказы, право econ.view, переводы, веб, консоль; своя база LocalDB)")
    import selftest_odds_a6
    _guard("selftest_odds_a6.offline", selftest_odds_a6.offline, check)
    if _ldb:
        _guard("selftest_odds_a6.sandbox", selftest_odds_a6.sandbox, check, _ldb)
    print("== A26. А6.6 «Античит: суточный отчёт»: --selftest исходника, поведение то же (Markdown панели = исходнику на синтетике, занятый файл, "
          "нет журнала), белый список, частные пороги, отказы, права, планировщик 00:20, переводы, веб, консоль, выкладка; своя база LocalDB — "
          "запись adm.AcDaily, M3 / M4 / M8 / ACJ по базе, бюджет, один прогон за раз)")
    import selftest_acdaily_a6
    _guard("selftest_acdaily_a6.offline", selftest_acdaily_a6.offline, check)
    if _ldb:
        _guard("selftest_acdaily_a6.sandbox", selftest_acdaily_a6.sandbox, check, _ldb)
    print("== A27. А6.8 «Античит: автоблок и EAC» (часть «чтение»): сверка лестницы тем же кодом, что ac_case.py ladder --check (совпадает, "
          "расхождение, копия не прочитана, паритет), счётчики, на сервере — только ext/ с манифестом, происхождение блока, отказы, права, "
          "переводы, веб, консоль, выкладка; свои базы LocalDB — история за период, блок и снятие панелью, EAC по учётке на подменах)")
    import selftest_autoblock_a6
    _guard("selftest_autoblock_a6.offline", selftest_autoblock_a6.offline, check)
    if _ldb:
        _guard("selftest_autoblock_a6.sandbox", selftest_autoblock_a6.sandbox, check, _ldb)
    print("== A28. А6.11 «Очередь имён» (часть «имена»): корпус P68 1590 тем же кодом, что char.rename, правила 4–7, оператор, отметки, отказы, "
          "права names.review, переводы, веб, консоль, adminc_20; свои базы LocalDB — очередь за период и все имена, names.mark, stale)")
    import selftest_names_a6
    _guard("selftest_names_a6.offline", selftest_names_a6.offline, check)
    if _ldb:
        _guard("selftest_names_a6.sandbox", selftest_names_a6.sandbox, check, _ldb)
    print("== A29. А6.7 «Античит: дела»: тот же ac_case.py (ПК / ext с манифестом), права adminc_21 = записям исходника, отказы, права ac.case / "
          "ac.decide / ac.appeal, переводы, веб, консоль, выкладка; свои базы LocalDB — настоящие san_01 + adminc_21 под asda_ops, полный цикл "
          "учебного дела на служебной учётке (блок = account.block, снятие = account.unblock), пересмотр другим лицом, блок не встал — откат)")
    import selftest_cases_a6
    _guard("selftest_cases_a6.offline", selftest_cases_a6.offline, check)
    if _ldb:
        _guard("selftest_cases_a6.sandbox", selftest_cases_a6.sandbox, check, _ldb)
    print("== A30. А6.9 «Баланс gp7: начислить и списать»: проверка ввода и отказы, право money.adjust (только owner), операция и откат, переводы, веб "
          "(окно подтверждения), консоль, adminc_22 / проверки / откат / выкладка; свои базы LocalDB — настоящий установщик шлюза и adminc_22 под "
          "asda_ops, фиксированные часы суток лимита, все отказы, второе подтверждение и второй фактор, HOLD, гонка, сбой после записи)")
    import selftest_gp7adjust_a6
    _guard("selftest_gp7adjust_a6.offline", selftest_gp7adjust_a6.offline, check)
    if _ldb:
        _guard("selftest_gp7adjust_a6.sandbox", selftest_gp7adjust_a6.sandbox, check, _ldb)
    print("== A31. А6.11 «Жалобы игроков» (часть «жалобы», решение №6 — бот Discord): права reports.*, отказы, правила ссылок и картинок = бот, "
          "переводы, веб, консоль, adminc_23 и выкладка, модульные тесты бота; свои базы LocalDB — бот player_reports.Store под asda_reports "
          "(пределы, скриншоты), очередь, карточка, report.take / close / case / reply, ответ через очередь бота один раз)")
    import selftest_reports_a6
    _guard("selftest_reports_a6.offline", selftest_reports_a6.offline, check)
    if _ldb:
        _guard("selftest_reports_a6.sandbox", selftest_reports_a6.sandbox, check, _ldb)
    print("== A32. А6.12 «Журнал чата» (часть «панель», решение №5 — журнал + заглушка, 90 дней): права chat.*, отказы, режим P129, text_raw, переводы, "
          "веб, консоль, adminc_24 и проверки / откат / выкладка, шаг panel_grants выкладчика P129; свои базы LocalDB — без схемы (пропуск, «не установлен»), "
          "настоящий chat_01_migrate.sql, поиск, кодировки, заглушка / снятие / откат под asda_admin и asda_ops, служебные, права")
    import selftest_chat_a6
    _guard("selftest_chat_a6.offline", selftest_chat_a6.offline, check)
    if _ldb:
        _guard("selftest_chat_a6.sandbox", selftest_chat_a6.sandbox, check, _ldb)
    print("== A33. А6.10 «Посещаемость» (решение владельца 23.11): права attendance.*, отказы ввода, коды процедуры, переводы, веб, adminc_25 и проверки / "
          "откат / выкладка; свои базы LocalDB — НАСТОЯЩИЕ OP_Attendance / OP_Attendance_Insert, adminc_25 под asda_ops: засчитать / снять / откат, "
          "сегодня и будущее — отказ, сервер после правки отвечает как положено, отпечаток, повтор ключа, права, сводка)")
    import selftest_attendance_a6
    _guard("selftest_attendance_a6.offline", selftest_attendance_a6.offline, check)
    if _ldb:
        _guard("selftest_attendance_a6.sandbox", selftest_attendance_a6.sandbox, check, _ldb)
    print("== A34. А7.1 «Выпуски: статус» (решение владельца А7 №6 — только статус): права releases.*, release.push (задание ПК), корень = лаунчеру, "
          "Ed25519 на чистом Python (RFC 8032, = cryptography), указатели настоящих Releases и подмены, сроки 14 / 3 суток, подставной сервер "
          "обновлений, снимок ПК без путей и секретов, предупреждения, переводы, веб, adminc_26 и выкладка; своя база LocalDB — запись снимка, "
          "отметка seen, чтение, release.push через журнал, маршрут)")
    import selftest_releases_a7
    _guard("selftest_releases_a7.offline", selftest_releases_a7.offline, check)
    if _ldb:
        _guard("selftest_releases_a7.sandbox", selftest_releases_a7.sandbox, check, _ldb)
    print("== A35. А7.2 «Сбои клиента» (решения владельца А7 №1, №8): права crash.*, операции crash.sync (задание ПК) и crash.alog_prune (слово, "
          "второй фактор), разбор summary.txt и CrashContext, подпись места, версия по времени, свои пакеты своим ключом, повторы, scp на подменах "
          "(SHA-256 против .json), утечки, настоящие PowerShell-скрипты квоты и удаления на своей папке, переводы, веб, adminc_27 и выкладка; своя база "
          "LocalDB — запись сводки, группы, частота, операции через журнал, маршрут)")
    import selftest_crashes_a7
    _guard("selftest_crashes_a7.offline", selftest_crashes_a7.offline, check)
    if _ldb:
        _guard("selftest_crashes_a7.sandbox", selftest_crashes_a7.sandbox, check, _ldb)
    print("== A36. А7.4 «Очередь исходящих + Discord» (решение владельца А7 №2 — только по флажку «и в Discord»): права outbox.* / community.*, "
          "белые списки панели = бота = CHECK, отказы полей, job.add, переводы, веб, adminc_28 и выкладка, модульные тесты бота (Discord подменён); "
          "своя база LocalDB — настоящий outbox_bot.Store под asda_reports и Worker с подставным Discord: один раз, просрочка, тест, отмена, удаление)")
    import selftest_outbox_a7
    _guard("selftest_outbox_a7.offline", selftest_outbox_a7.offline, check)
    if _ldb:
        _guard("selftest_outbox_a7.sandbox", selftest_outbox_a7.sandbox, check, _ldb)
    print("== A37. А7.5 «Telegram владельцу» (решение владельца А7 №3 — только владельцу, только отправка, с ПК): права notify.*, события = CHECK базы, "
          "нет флагов суточного отчёта (А6 №9), отправитель — только sendMessage и getMe, токена нет в коде, переводы, веб, adminc_29 и выкладка, "
          "разделение очередей, модульные тесты отправителя (Telegram подменён); своя база LocalDB — общий выключатель ВЫКЛ по умолчанию, события, "
          "склейка, пауза, предел, настоящий tg_bot.Store под asda_reports с подставным HTTP)")
    import selftest_telegram_a7
    _guard("selftest_telegram_a7.offline", selftest_telegram_a7.offline, check)
    if _ldb:
        _guard("selftest_telegram_a7.sandbox", selftest_telegram_a7.sandbox, check, _ldb)
    print("== A38. А7.6 «Сообщество» (решение владельца А7 №9 — хозяин реестра заявок и тестеров — бот): права community.*, белые списки команд и "
          "ролей панели = бота = CHECK, поля снимка = adm.BotSnapPut, снимок настоящего state.json без анкеты, переводы, веб, adminc_30 и выкладка, "
          "модульные тесты бота (Discord подменён); своя база LocalDB — настоящий community_bot.Store под asda_reports и Worker с подставным Discord: "
          "решение и откат, тестер, варны, бан + блок учётки, защищённая роль, «тест», отмена, повтор, пределы)")
    import selftest_community_a7
    _guard("selftest_community_a7.offline", selftest_community_a7.offline, check)
    if _ldb:
        _guard("selftest_community_a7.sandbox", selftest_community_a7.sandbox, check, _ldb)
    print("== A39. А7.7 «Заметки к выпуску» (решение владельца А7 №7 — черновик в панели и кнопка «Опубликовать»; №2 — тексты руками): права notes.* / "
          "community.post, разбор changelog (ключи, вид, состояние, выпуск, «Что стало» без «Причины»), настоящий текущий changelog, текущий файл по "
          "AGENT_RULES_PORT.md, секреты, отказы полей, переводы, веб, adminc_31 / 29 / 10 / 99 и выкладка; своя база LocalDB — снимок, черновик, "
          "публикация через очередь, настоящий outbox_bot.Store под asda_reports и Worker с подставным Discord: «опубликовано» по итогу бота, повтор — "
          "отказ, откат = удаление ветки (только owner), тест без Discord, отмена, отметка «вне панели», пределы)")
    import selftest_notes_a7
    _guard("selftest_notes_a7.offline", selftest_notes_a7.offline, check)
    if _ldb:
        _guard("selftest_notes_a7.sandbox", selftest_notes_a7.sandbox, check, _ldb)
    print("== A40. А7.10 «Справка по операциям»: полнота справки по реестру (writes / restart / undo / help, RU и EN, reversible ↔ откат журналом) — "
          "новая операция без справки роняет самотест; сверка с признаками кода (Discord, Telegram, мост, удаление, рестарт стойки, клиентские файлы), "
          "явный список необратимых и пишущих наружу, права = auth.PERMS, /api/opdoc, справка в предпросмотре, #/help, окно подтверждения, переводы)")
    import selftest_opdoc_a7
    _guard("selftest_opdoc_a7.offline", selftest_opdoc_a7.offline, check)
    print("== B. служба на LocalDB")
    _guard("part_b", part_b)
    if live:
        print("== C. живые базы (чтение; запись с откатом — учётки владельца 1 и 2, только не в игре)")
        _guard("part_live", part_live)
        print("== C2. магазины: живое чтение стойки и порта, сухие прогоны половин, путь тестового набора (отменяется)")
        _guard("selftest_shops.live", selftest_shops.live, check)
        print("== C3. данные игры А4: живое чтение таблиц и порта, сухой план с настоящим генератором ItemDB")
        _guard("selftest_data_a4.live", selftest_data_a4.live, check)
        print("== C4. тексты А4.2: живой снимок и сухой план с настоящими инструментами порта")
        _guard("selftest_texts_a4.live", selftest_texts_a4.live, check)
        print("== C5. монстры и добыча А4.3: живое чтение шести копий, справка, сухой прогон выкладчика по SSH")
        _guard("selftest_monsters_a4.live", selftest_monsters_a4.live, check)
        print("== C6. предметы А4.4: живое чтение таблиц и Joy1, справка, план клиента с настоящим генератором ItemDB, сухой прогон по SSH")
        _guard("selftest_items_a4.live", selftest_items_a4.live, check)
        print("== C7. задания А4.5: живое чтение копий, справка и Joy1, план клиента настоящими импортёрами, сухой прогон по SSH")
        _guard("selftest_quests_a4.live", selftest_quests_a4.live, check)
        print("== C8. звания А4.6: живое чтение копий, справка и Joy1, план клиента с настоящим генератором ItemDB, сухой прогон по SSH")
        _guard("selftest_titles_a4.live", selftest_titles_a4.live, check)
        print("== C9. навыки и классы А4.7: живое чтение копий, справка и Joy1, план клиента с настоящим генератором ItemDB, сухой прогон по SSH")
        _guard("selftest_skills_a4.live", selftest_skills_a4.live, check)
        print("== C10. карты А4.8: живое чтение копий, справка и Joy1, план клиента настоящим asda_map_registry, сухой прогон по SSH")
        _guard("selftest_maps_a4.live", selftest_maps_a4.live, check)
        print("== C11. стойка и планировщик А5.1: счёт процессов, adm.job и права, задание с отменой, сухой предпросмотр рестарта")
        _guard("selftest_stack_a5.live", selftest_stack_a5.live, check)
        print("== C12. живьём А5.2: узлы и присутствие, сухие предпросмотры призыва и переноса к персонажу")
        _guard("selftest_live_a5.live", selftest_live_a5.live, check)
        print("== C13. режим обслуживания А5.3: состояние SQL L09 и DLL L09, права asda_admin, сухой предпросмотр (режим не включается)")
        _guard("selftest_maint_a5.live", selftest_maint_a5.live, check)
        print("== C14. события и сбросы А5.4: Event.dat ×3, счастливые часы ×3, журнал сброса, сухие предпросмотры (ничего не включается)")
        _guard("selftest_events_a5.live", selftest_events_a5.live, check)
        print("== C15. настройки патчей А5.5: ini всех копий DLL и журналы патчей по SSH, конфиги без секретов, сухая оценка позиции")
        _guard("selftest_patchcfg_a5.live", selftest_patchcfg_a5.live, check)
        print("== C16. журналы стойки А5.6: каталог, файлы и хвост по SSH, размер по пути, «следить» без изменений, маскировка, отказы")
        _guard("selftest_logs_a5.live", selftest_logs_a5.live, check)
        print("== C17. бэкапы БД А5.7: состояние подписанной процедурой, права asda_admin, md5 файлов, папка, чужие бэкапы, сухой предпросмотр")
        _guard("selftest_dbbackup_a5.live", selftest_dbbackup_a5.live, check)
        print("== C18. служебные копии А5.8: список подписанной процедурой, вердикты, права asda_admin, сухой предпросмотр (ничего не удаляется)")
        _guard("selftest_bakdrop_a5.live", selftest_bakdrop_a5.live, check)
        print("== C19. античит А6.1: права asda_admin на ac.*, виды живой базы в каталоге и переводах, лента = COUNT(*), сводка, служба на сервере")
        _guard("selftest_ac_a6.live", selftest_ac_a6.live, check)
        print("== C20. деньги А6.2: права asda_admin (password — нет), итоги и журналы = COUNT / SUM живой, висящие, сток, служба на сервере")
        _guard("selftest_money_a6.live", selftest_money_a6.live, check)
        print("== C21. экономика А6.3: права asda_admin на adm.EconDaily*, чтение = COUNT / SUM живой, снимок только в AsdaAdmin, служба 401")
        _guard("selftest_econ_a6.live", selftest_econ_a6.live, check)
        print("== C22. передачи А6.4: строк источников и зеркал = COUNT(*) за период, все таблицы Trade* / PersonalStore* разобраны, рынок, лавки, служба")
        _guard("selftest_trade_a6.live", selftest_trade_a6.live, check)
        print("== C23. шансы А6.5: попыток и призов = COUNT(*) живой, коробки = строкам журнала шлюза по SSH, служба читает таблицы локально, 401")
        _guard("selftest_odds_a6.live", selftest_odds_a6.live, check)
        print("== C24. суточный отчёт А6.6: права asda_admin на adm.AcDaily, прогон службы тем же кодом (md5), предпросмотр на сервере без записи, 401")
        _guard("selftest_acdaily_a6.live", selftest_acdaily_a6.live, check)
        print("== C25. автоблок А6.8: сверка = функциям ac_case.py на байтах ini, история = COUNT(*) живой, EAC по учётке, служба из ext/ (md5), 401")
        _guard("selftest_autoblock_a6.live", selftest_autoblock_a6.live, check)
        print("== C26. очередь имён А6.11: права adm.NameReview, очередь = источникам, перепроверка char.rename настоящим читателем, предпросмотр, 401")
        _guard("selftest_names_a6.live", selftest_names_a6.live, check)
        print("== C27. дела А6.7: список = san.cases, AC-0001 целиком, asda_admin — чтение san без записи, служба: verify AC-0001 из каталога службы, 401")
        _guard("selftest_cases_a6.live", selftest_cases_a6.live, check)
        print("== C28. жалобы А6.11: права asda_admin по столбцам, путь бота (пароль по SSH, asda_reports по VPN = adminc_23_reports_verify), очередь, служба, 401")
        _guard("selftest_reports_a6.live", selftest_reports_a6.live, check)
        print("== C29. журнал чата А6.12: состояние (схема chat — «установлен» / «не установлен»), режим P129 по копиям, строки adminc_10 о чате, служба, 401")
        _guard("selftest_chat_a6.live", selftest_chat_a6.live, check)
        print("== C30. посещаемость А6.10: процедуры сервера = копиям стенда, права asda_ops, сводка = COUNT(*) живой, запись с откатом учётке 2 слот 12, служба, 401")
        _guard("selftest_attendance_a6.live", selftest_attendance_a6.live, check)
        print("== C31. выпуски А7.1: сервер обновлений = второму пути, права asda_admin на adm.ReleasePcStatus, release.push с ПК и чтение, служба, 401")
        _guard("selftest_releases_a7.live", selftest_releases_a7.live, check)
        print("== C32. сбои А7.2: список LogDrop по SSH = квоте службы, права asda_admin на adm.ClientCrash*, crash.sync с ПК и чтение, служба, 401")
        _guard("selftest_crashes_a7.live", selftest_crashes_a7.live, check)
        print("== C33. очередь Discord А7.4: права asda_admin на adm.Outbox*, путь бота (asda_reports по VPN = adminc_28_outbox_verify), проверочная запись "
              "до «бот взял» и «тест» (в Discord ничего), служба, 401")
        _guard("selftest_outbox_a7.live", selftest_outbox_a7.live, check)
        print("== C34. Telegram А7.5: права asda_admin на adm.Notify* / adm.Tg*, путь отправителя (asda_reports по VPN = adminc_29_telegram_verify), "
              "отметка службы, проверочная запись selftest до «тест» (Telegram не вызывается), служба, 401")
        _guard("selftest_telegram_a7.live", selftest_telegram_a7.live, check)
        print("== C35. «Сообщество» А7.6: права asda_admin на adm.Bot*, путь бота (asda_reports по VPN = adminc_30_community_verify), свежесть копии "
              "реестра, команды с отметкой «тест» до «тест» (в Discord ничего), служба, 401")
        _guard("selftest_community_a7.live", selftest_community_a7.live, check)
        print("== C36. заметки к выпуску А7.7: права asda_admin на adm.Notes*, путь бота (asda_reports по VPN = adminc_31_notes_verify), снимок changelog "
              "с ПК (notes.push), публикация «тест» до «тест» (в Discord ничего, запись не «опубликована»), служба, 401")
        _guard("selftest_notes_a7.live", selftest_notes_a7.live, check)
        print("== C37. справка А7.10: каталог службы полон по её реестру (SSH), /api/opdoc без входа — 401")
        _guard("selftest_opdoc_a7.live", selftest_opdoc_a7.live, check)
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГ: %d проверок, ошибок %d" % (len(RESULTS), len(bad)))
    if P.SKIPS:                                       # ★ 25.11 (К-3): пропущенное на публичном клоне — отдельной строкой, не ошибка
        print(P.summary())
    return 1 if bad else 0


def parse_only(args):
    """★ ревизия 39 Н-4: ключ --only <блоки через запятую> → (список | None, текст отказа | None). --only без значения (или значение —
    другой ключ, пустые имена) и --only без --live — отказ: выборочный режим есть только у живого прогона, полный живой — решение владельца."""
    if "--only" not in args:
        return None, None
    i = args.index("--only")
    val = args[i + 1] if i + 1 < len(args) else ""
    names = [x.strip() for x in val.split(",")] if val and not val.startswith("--") else []
    if not names or not all(names):
        return None, "--only без списка блоков (например --only skills; есть: %s) — полный прогон так не запускается" % ", ".join(LIVE_BLOCKS)
    if "--live" not in args:
        return None, "--only — только с --live (выборочный живой прогон); офлайн-самотест гоняется целиком без --only"
    return names, None


def utf8_stdout():
    """★ р82 М-7 / р83 М-6 (А7.7): консоль cp1251 не должна ронять самотест на «→» и «★» — вывод в UTF-8 с заменой неизвестного (как
    asda_admin.py main). Зовут __main__ этого файла и каждого tests/selftest_*.py, у которого свой __main__."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


if __name__ == "__main__":
    utf8_stdout()
    _only, _why = parse_only(sys.argv[1:])
    if _why:
        raise SystemExit(_why)
    sys.exit(main(live="--live" in sys.argv, only=_only))
