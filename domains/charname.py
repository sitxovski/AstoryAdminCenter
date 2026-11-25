# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""charname.py — правило имени персонажа как у сервера (A13), для смены имени из панели. 17.11.2026.

ИСТОЧНИК. Joy1.dbo.fn_A13_NameRule (Server/Docs/SQL/a13_01_migrate.sql) + dbo.A13_NameGuard область 2 (UPCharRename):
правила 1 пусто, 2 длина ≥ 20 байт, 3 управляющий байт 0x01..0x1F/0x7F, 4 символ вне набора, 5 слово CurseTable.bin (A13_CurseWord,
только ascii; имя A-Z → a-z, слова НЕ понижаются, поиск подстроки), 6 слово LewdWordList (CHARINDEX), 7 имя занято
(CharPos.Charname = имя и fn_AsdaNameEq). Логин панели не может вызывать функции (DENY EXECUTE на уровне базы), поэтому
правило повторено здесь ТОЛЬКО для набора 0 (A-Z a-z 0-9 — действующая настройка A13_NameRuleConfig.Charset = 0) и сверено со
всем корпусом name_corpus_p68.txt (9 198 строк, тот же корпус, на котором дым A13 сверил SQL-функцию: 0 расхождений) —
tests/selftest.py. Набор 1 панель не угадывает: отказ «смените имя в игре».
Занятость для ASCII-имени (правило 4 гарантирует ASCII) — fn_AsdaNameEq: байты равны ИЛИ оба имени — печатный ASCII
(тогда совпадение коллации Arabic_CI_AS = равенство без учёта регистра); выражение повторено в SQL без вызова функции.
Панель строже сервера: занятость проверяется и по Charinfo (у сервера — только CharPos; рассинхрон 2/11 известен — a13b).
Побочных эффектов при импорте нет.
"""
RULES = {1: "пустое имя", 2: "длина 20 байт и больше", 3: "управляющий символ", 4: "символ вне набора (только A-Z, a-z, 0-9)",
         5: "запрещённое слово (CurseTable клиента)", 6: "запрещённое слово (LewdWordList)", 7: "имя занято"}


def rule(name_bytes, curse_words):
    """fn_A13_NameRule для Charset 0 → номер правила (0 — допустимо). name_bytes — байты имени, curse_words — ascii-слова."""
    b = bytes(name_bytes)
    n = len(b)
    if n == 0:
        return 1
    if n >= 20:
        return 2
    for c in b:
        if c < 32 or c == 127:
            return 3
    for c in b:
        if not (48 <= c <= 57 or 65 <= c <= 90 or 97 <= c <= 122):
            return 4
    low = bytes(c + 32 if 65 <= c <= 90 else c for c in b)
    for w in curse_words:
        wb = w.encode("latin-1", "replace") if isinstance(w, str) else bytes(w)
        if wb and wb in low:
            return 5
    return 0


def load_config(r):
    """A13_NameRuleConfig, ascii-слова A13_CurseWord и LewdWordList (чтение логином панели)."""
    cfg = (r.rows("SELECT Mode, Charset, CurseWords, RenameLewdDup, ExemptOperators FROM dbo.A13_NameRuleConfig WHERE Id = 1")
           or [{}])[0]
    words = [x["Word"] for x in r.rows("SELECT Word FROM dbo.A13_CurseWord WHERE Enc = 'ascii'")] if cfg.get("CurseWords") else []
    lewd = [x["LewdWord"] for x in r.rows("SELECT LewdWord FROM dbo.LewdWordList")]
    return cfg, words, lewd


def taken_sql():
    """SQL: кто носит это имя (как UPNickCheck/A13 правило 7 для ASCII-имени) — по CharPos и Charinfo, и по удалённым (Del_Charinfo:
    восстановление OpCharacterRestore дало бы двойника — панель строже сервера, перепроверка 10). Параметр имени — 6 раз; свою
    строку вызывающий отбрасывает сам (смена регистра своего имени — не занятость)."""
    cond = ("Charname = ? AND (CAST(RTRIM(Charname) AS varbinary(64)) = CAST(RTRIM(?) AS varbinary(64)) "
            "OR Charname COLLATE Arabic_BIN NOT LIKE '%[^ -~]%')")
    return ("SELECT Userindex, Charidx, Charname, deleted FROM (SELECT Userindex, Charidx, Charname, 0 AS deleted FROM dbo.CharPos WHERE %s "
            "UNION ALL SELECT Userindex, Charidx, Charname, 0 FROM dbo.Charinfo WHERE %s "
            "UNION ALL SELECT Userindex, Charidx, Charname, 1 FROM dbo.Del_Charinfo WHERE %s) x" % (cond, cond, cond))
