# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""Собрать AstoryAdminCenter/sql/adminc_05_restore.sql из текста Joy1.dbo.OpCharacterRestore (выгрузка 18.11.2026)."""
import hashlib
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
raw = open(src, "rb").read()
md5 = hashlib.md5(raw).hexdigest()
lines = [l for l in raw.decode("utf-8").replace("\r", "").split("\n") if l.strip()]
a = next(i for i, l in enumerate(lines) if l.startswith("INSERT INTO dbo.CharAppr"))
b = next(i for i, l in enumerate(lines) if l.startswith("DECLARE @Level"))
body = lines[a:b]
body = [re.sub(r"(?i)\s*with\s*\(\s*nolock\s*\)", "", l).rstrip() for l in body]
targets = []
for l in body:
    m = re.match(r"(?i)\s*INSERT INTO dbo\.(\w+)", l)
    if m and m.group(1).lower() not in [t.lower() for t in targets] and m.group(1).lower() != "charoption":
        targets.append(m.group(1))
busy = "\n".join("\tIF EXISTS (SELECT 1 FROM dbo.%s WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'%s';" % (t, t)
                 for t in targets)
stock = "\n".join("\t" + l for l in body)

sql = r"""-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_05_restore.sql — восстановление удалённого персонажа для админ-центра (волна А1, 18.11.2026; решение владельца:
-- «своя процедура adm»). Разбор: Reports/admin_center/research_char_restore.md.
-- СОБРАН ПРОГРАММОЙ из текста Joy1.dbo.OpCharacterRestore (выгрузка 18.11.2026, MD5 выгрузки %(md5)s): вставки штатной
-- процедуры взяты без изменений (сняты только подсказки NOLOCK — чтение внутри своей транзакции), блок CharacterStat
-- (межбазовый, со старым Charidx и Seridx без +1 — дефект оригинала) убран: эту строку пишет панель в той же транзакции.
-- ДОБАВЛЕНО (штатная процедура ничего этого не делает — повторный вызов клонирует предметы, занятый слот смешивает данные):
--   одна транзакция, XACT_ABORT, отказ — THROW (откатывает и транзакцию вызывающего); набор корзины существует и ещё не восстановлен (adm.CharRestored, ключ Userindex+Charidx+Edate);
--   у учётки меньше 3 персонажей (4-й ломает вход: LoginManager «Character Count Over»); слот 10–12 и пуст во ВСЕХ таблицах,
--   куда идёт вставка; Uuid предметов набора не встречаются в живом Item; новое имя (если задано) — в Charinfo и CharPos.
--   Правило и занятость имени, «учётка не в игре» — панель проверяет в той же транзакции до вызова (domains/charrestore.py).
-- Права: asda_ops — EXECUTE только этой процедуры (sql/adminc_04_ops.sql); цепочка владения dbo → таблицы dbo.
-- ═══════════════════════════════════════════════════════════════════════════
USE [Joy1];
GO
IF SCHEMA_ID('adm') IS NULL EXEC('CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID('adm.CharRestored', 'U') IS NULL
CREATE TABLE adm.CharRestored (
	Userindex   INT          NOT NULL,
	Charidx     TINYINT      NOT NULL,
	Edate       DATETIME     NOT NULL,          -- ключ набора корзины (Del_*.Edate)
	NewCharidx  TINYINT      NOT NULL,
	NewName     VARCHAR(20)  NULL,              -- NULL — прежнее имя
	RestoredAt  DATETIME     NOT NULL CONSTRAINT DF_CharRestored_At DEFAULT (GETDATE()),
	Operator    VARCHAR(64)  NULL,
	CONSTRAINT PK_CharRestored PRIMARY KEY (Userindex, Charidx, Edate)
);
GO
IF OBJECT_ID('adm.CharRestore', 'P') IS NOT NULL DROP PROCEDURE adm.CharRestore;
GO
CREATE PROCEDURE adm.CharRestore @Userindex INT, @Charidx TINYINT, @Edate DATETIME, @NewCharidx TINYINT,
	@NewName VARCHAR(20) = NULL, @Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @busy NVARCHAR(64), @n INT;
	BEGIN TRANSACTION;
	-- блокировки: учётку (Us_member, CharPos) панель уже держит (items.online_state); здесь — персонажи учётки и отметка набора
	-- (ключ PK_CharRestored). Корзина (куча) и Item (без индекса по Uuid) — без UPDLOCK/HOLDLOCK: иначе диапазон держал бы всю
	-- таблицу до фиксации (перепроверка 16 М1/М2); повтор уже сериализован отметкой и блокировкой учётки.
	SELECT @n = COUNT(*) FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @Userindex;
	IF NOT EXISTS (SELECT 1 FROM dbo.Del_Charinfo WHERE Userindex = @Userindex AND Charidx = @Charidx AND Edate = @Edate)
	THROW 50002, N'adm.CharRestore: набора корзины нет', 1;
	IF EXISTS (SELECT 1 FROM adm.CharRestored WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @Userindex AND Charidx = @Charidx AND Edate = @Edate)
	THROW 50003, N'adm.CharRestore: этот набор уже восстановлен', 1;
	IF @n >= 3
	THROW 50004, N'adm.CharRestore: у учётки уже 3 персонажа', 1;
	IF @NewCharidx NOT IN (10, 11, 12)
	THROW 50005, N'adm.CharRestore: слот только 10, 11 или 12', 1;
	SET @busy = NULL;
%(busy)s
	IF @busy IS NOT NULL
	BEGIN DECLARE @m NVARCHAR(200) = CONCAT(N'adm.CharRestore: слот ', @NewCharidx, N' занят (таблица ', @busy, N')'); THROW 50006, @m, 1; END;
	IF EXISTS (SELECT 1 FROM dbo.Del_Item d JOIN dbo.Item i ON i.Uuid = d.Uuid
	           WHERE d.Userindex = @Userindex AND d.Charidx = @Charidx AND d.Edate = @Edate)
	THROW 50007, N'adm.CharRestore: предметы набора уже есть в игре (тот же Uuid)', 1;
	-- ▼ вставки штатной Joy1.dbo.OpCharacterRestore (без изменений)
	;
%(stock)s
	-- ▲
	IF @NewName IS NOT NULL
	BEGIN
		UPDATE dbo.Charinfo SET Charname = @NewName WHERE Userindex = @Userindex AND Charidx = @NewCharidx;
		UPDATE dbo.CharPos SET Charname = @NewName WHERE Userindex = @Userindex AND Charidx = @NewCharidx;
	END;
	IF NOT EXISTS (SELECT 1 FROM dbo.Charinfo WHERE Userindex = @Userindex AND Charidx = @NewCharidx)
	   OR NOT EXISTS (SELECT 1 FROM dbo.CharPos WHERE Userindex = @Userindex AND Charidx = @NewCharidx)
	THROW 50008, N'adm.CharRestore: Charinfo/CharPos не восстановились', 1;
	INSERT INTO adm.CharRestored (Userindex, Charidx, Edate, NewCharidx, NewName, Operator)
	VALUES (@Userindex, @Charidx, @Edate, @NewCharidx, @NewName, @Operator);
	COMMIT;
	SELECT 1 AS ok;
	RETURN 0;
GO
PRINT 'adminc_05_restore: OK';
GO
""" % {"md5": md5, "busy": busy, "stock": stock}
open(dst, "w", encoding="utf-8", newline="\n").write(sql)
print("targets:", ", ".join(targets))
