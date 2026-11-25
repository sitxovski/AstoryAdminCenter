# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
r"""gen_charcopy_sql.py — собрать sql/adminc_08_charcopy.sql (копия персонажа на служебную учётку + обёртка пересчёта рейтинга чести).
18.11.2026, волна А1 (решения владельца 18.11; разбор Reports/admin_center/research_a1_char_rest.md §7, §3).

ВХОД: выгрузка столбцов таблиц Joy1 (sys.columns, по порядку column_id) строками «таблица|номер|столбец|тип|длина|identity|null|computed»:
  sqlcmd -S lpc:.\SQLEXPRESS -E -d Joy1 -s "|" -y 0 -Q "SET NOCOUNT ON; SELECT t.name, c.column_id, c.name, ty.name, c.max_length,
    c.is_identity, c.is_nullable, c.is_computed FROM sys.tables t JOIN sys.columns c ON c.object_id = t.object_id
    JOIN sys.types ty ON ty.user_type_id = c.user_type_id WHERE SCHEMA_NAME(t.schema_id) = 'dbo' ORDER BY t.name, c.column_id"
ЗАПУСК: python tools/gen_charcopy_sql.py <выгрузка столбцов> sql/adminc_08_charcopy.sql
СОСТАВ КОПИИ — разбор §7: всё, что UPDeleteChar считает принадлежащим слоту, + CharRefine и CharFameHigh (их удаление не трогает);
  БЕЗ связей с другими игроками и деньгами (друзья, клан, соулмейт, камни душ, почта, аукцион, посещаемость, рейтинг, интро, GM-флаг).
Побочных эффектов при импорте нет.
"""
import sys

# таблица → {столбец: выражение} (подмены при копии); столбцы identity пропускаются сами
COPY = [
    ("Charinfo", {"Uid": "@Uid", "Charname": "@Name", "Share": "0"}),           # Share — соулмейт (связь с другим игроком): 0
    ("CharPos", {"Uid": "@Uid", "Charname": "@Name", "Usernum": "-1", "Partyidx": "-1", "Captain": "0", "State": "0",
                 "SoulState": "0", "pState": "0"}),                             # как у всех офлайн-строк живой базы 18.11 (-1/0/0/0/0)
    ("CharAppr", {}), ("CharChat", {}), ("CharConstellation", {}), ("CharEpisode", {}), ("EpisodeTime", {}), ("VillagePos", {}),
    ("CharQuest", {}), ("CharSkill", {}), ("CharSkillitem", {}), ("CharSlot", {}), ("CharStatus", {}), ("CharSmStatus", {}),
    ("CharFame", {}), ("CharFameBank", {}), ("CharFameProgress", {}), ("CharFameHigh", {}),
    ("CharCamp", {"Campidx": "@Camp"}),                                         # армия — учётки-цели (сток: армия на всю учётку)
    ("CharPlusPackage", {}), ("CharFish", {}), ("CharFishBookInfo", {}), ("CRT_CharCraftInfo", {}), ("CRT_LimitationQuest", {}),
    ("CRT_MainLimitationQuest", {}), ("CharTutorial", {}), ("CharRefine", {}), ("SoulGuardian", {}),
    ("ItemCoolTime", {}), ("SkillCoolTime", {}), ("SMSkillCoolTime", {}), ("CharPetList", {}),
]
# UPDeleteChar эти строки НЕ удаляет (research_char_restore.md §1.2) — после удаления персонажа они остаются в слоте навсегда; проверка
# «слот пуст» по ним сделала бы слот непригодным для копии. Копия их ЗАМЕНЯЕТ (DELETE + INSERT), панель предупреждает в предпросмотре.
REPLACE = {"CharRefine", "CharFameHigh"}
# ★ ревизия 26 С-1: что ещё стирает UPDeleteChar у персонажа слота (строки, которые появляются, когда копией играют): удаление копии
# стирает их так же; связи с ДРУГИМИ игроками (обе стороны) — отказ удаления с перечнем
EXTRA_DELETE = [("AttendanceCount", "Userindex", "Charidx"), ("AttendanceDetail", "Userindex", "Charidx"), ("CharinPos", "Userindex", "Charidx"),
                ("Charintroduce", "Userindex", "Charidx"), ("FamePointRank", "Userindex", "Charidx")]
LINKS = [("CharFriend", "(Userindex = @DstU AND Charidx = @DstC) OR (FUserindex = @DstU AND FCharidx = @DstC)"),
         ("ClanMember", "Userindex = @DstU AND Charidx = @DstC"), ("Exitem", "Userindex = @DstU AND Charidx = @DstC"),
         ("ItemPostBox", "Userindex = @DstU AND Charidx = @DstC"),
         ("SoulJewel", "(Userindex1 = @DstU AND Charidx1 = @DstC) OR (Userindex2 = @DstU AND Charidx2 = @DstC)"),
         ("SellitemAlarm", "(BUserindex = @DstU AND Bcharidx = @DstC) OR (SUserindex = @DstU AND Scharidx = @DstC)")]
ITEM = "Item"                                                               # отдельно: новые Uuid и Uc1…4, карта в adm.CharCopyItemMap


def load(path):
    cols = {}
    for ln in open(path, encoding="utf-8", errors="replace"):
        f = [x.strip() for x in ln.rstrip("\n").split("|")]
        if len(f) < 8 or not f[1].isdigit():
            continue
        cols.setdefault(f[0].lower(), []).append({"name": f[2], "type": f[3], "len": f[4], "ident": f[5] == "1", "computed": f[7] == "1",
                                                  "null": f[6] == "1"})
    return cols


def table_cols(cols, t):
    c = cols.get(t.lower())
    if not c:
        raise SystemExit("в выгрузке нет таблицы %s" % t)
    if c[0]["name"].lower() != "userindex" or c[1]["name"].lower() != "charidx":
        raise SystemExit("%s: первые столбцы не Userindex/Charidx" % t)
    return [x for x in c if not x["ident"] and not x["computed"]]


def _snap_table(name, cols):
    """CREATE TABLE снимка заменяемых строк: CopyId + столбцы таблицы с теми же типами."""
    def typ(c):
        t = c["type"]
        if t in ("varchar", "char", "nvarchar", "nchar", "varbinary", "binary"):
            n = int(c["len"])
            return "%s(%s)" % (t.upper(), "MAX" if n < 0 else (n // 2 if t.startswith("n") else n))
        return t.upper()
    body = ",\n".join("\t%s %s %s" % (c["name"], typ(c), "NULL" if c["null"] else "NOT NULL") for c in cols)
    return ("IF OBJECT_ID('%s', 'U') IS NULL\nCREATE TABLE %s (\n\tCopyId INT NOT NULL,\n%s\n);\nGO" % (name, name, body))


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    cols = load(argv[1])
    copy_sql, busy, dele, snap_tbl, snap_back = [], [], [], [], []
    for t, sub in COPY + [(ITEM, None)]:
        c = table_cols(cols, t)
        k0, k1 = c[0]["name"], c[1]["name"]
        if t not in REPLACE:
            busy.append("\tIF EXISTS (SELECT 1 FROM dbo.%s WHERE %s = @DstU AND %s = @DstC) SET @busy = N'%s';" % (t, k0, k1, t))
        dele.append("\tDELETE FROM dbo.%s WHERE %s = @DstU AND %s = @DstC;" % (t, k0, k1))
        if t == ITEM:
            continue
        names = [x["name"] for x in c]
        low = {k.lower(): v for k, v in sub.items()}
        miss = [k for k in low if k not in [n.lower() for n in names]]
        if miss:
            raise SystemExit("%s: нет столбцов %s" % (t, miss))
        sel = ["@DstU", "@DstC"] + [low.get(n.lower(), n) for n in names[2:]]
        if t in REPLACE:
            # ★ ревизия 26 С-2: остаток удалённого персонажа — снимком в adm.CharCopyReplaced_<таблица> (с номером копии), удаление копии вернёт
            st = "adm.CharCopyReplaced_%s" % t
            snap_tbl.append(_snap_table(st, c))
            copy_sql.append("\tINSERT INTO %s (CopyId, %s) SELECT @id, %s FROM dbo.%s WHERE %s = @DstU AND %s = @DstC;"
                            % (st, ", ".join(names), ", ".join(names), t, k0, k1))
            copy_sql.append("\tDELETE FROM dbo.%s WHERE %s = @DstU AND %s = @DstC;          -- остаток прежнего владельца слота (снимок выше)" % (t, k0, k1))
            snap_back.append("\tINSERT INTO dbo.%s (%s) SELECT %s FROM %s WHERE CopyId = @CopyId;" % (t, ", ".join(names), ", ".join(names), st))
        copy_sql.append("\tINSERT INTO dbo.%s (%s)\n\tSELECT %s\n\tFROM dbo.%s WHERE %s = @SrcU AND %s = @SrcC;"
                        % (t, ", ".join(names), ", ".join(sel), t, k0, k1))
        if t == "CharCamp":
            # ★ ревизия 26 М-7: у источника строки лагеря нет, а у учётки-цели армия есть — строка (армия, 0, 0, 0, 0), как UPCharCampSelect
            # ставит армию всем персонажам учётки
            copy_sql.append("\tIF @Camp <> -1 AND NOT EXISTS (SELECT 1 FROM dbo.CharCamp WHERE Userindex = @DstU AND Charidx = @DstC)\n"
                            "\t\tINSERT INTO dbo.CharCamp (Userindex, Charidx, Campidx, CampPoint, CampGrade, CampFlag, CampPenaltyTime)"
                            " VALUES (@DstU, @DstC, @Camp, 0, 0, 0, 0);")
    ic = [x["name"] for x in table_cols(cols, ITEM)]
    for need in ("Uuid", "Uc1", "Uc2", "Uc3", "Uc4"):
        if need not in ic:
            raise SystemExit("Item: нет столбца %s" % need)
    rest = [n for n in ic[2:] if n not in ("Uuid", "Uc1", "Uc2", "Uc3", "Uc4")]
    item_sql = ("\tSELECT CAST(Uuid AS VARCHAR(36)) AS OldUuid, NEWID() AS NewUuid,\n"
                "\t       Uc1 AS OldUc1, CASE WHEN Uc1 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc1,\n"
                "\t       Uc2 AS OldUc2, CASE WHEN Uc2 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc2,\n"
                "\t       Uc3 AS OldUc3, CASE WHEN Uc3 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc3,\n"
                "\t       Uc4 AS OldUc4, CASE WHEN Uc4 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc4,\n"
                "\t       %s\n\tINTO #it FROM dbo.Item WHERE Userindex = @SrcU AND Charidx = @SrcC;\n"
                "\tINSERT INTO dbo.Item (%s)\n\tSELECT @DstU, @DstC, NewUuid, %s\n\tFROM #it;"
                % (", ".join(rest), ", ".join(ic), ", ".join(
                    ("NewUc%s" % n[2:]) if n in ("Uc1", "Uc2", "Uc3", "Uc4") else n for n in ic[3:])))
    links = "\n".join("\tIF EXISTS (SELECT 1 FROM dbo.%s WHERE %s) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'%s');"
                      % (t, w, t) for t, w in LINKS)
    extra = "\n".join("\tDELETE FROM dbo.%s WHERE %s = @DstU AND %s = @DstC;          -- как UPDeleteChar" % x for x in EXTRA_DELETE)
    out = TEMPLATE % {"busy": "\n".join(busy), "copy": "\n".join(copy_sql), "item": item_sql, "delete": "\n".join(dele) + "\n" + extra,
                      "n": len(COPY) + 1, "snap_tbl": "\n".join(snap_tbl), "links": links, "snap_back": "\n".join(snap_back)}
    with open(argv[2], "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("записано %s: таблиц копии %d" % (argv[2], len(COPY) + 1))
    return 0


TEMPLATE = r"""-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_08_charcopy.sql — копия персонажа на служебную учётку (≤ 5000) и обёртка пересчёта рейтинга чести. Волна А1, 18.11.2026.
-- СОБРАН ПРОГРАММОЙ tools/gen_charcopy_sql.py из выгрузки столбцов Joy1 (sys.columns 18.11.2026). Разбор:
-- Reports/admin_center/research_a1_char_rest.md §7 (копия), §3 (рейтинг чести). Решения владельца 18.11:
--   копия — своя процедура adm.CharCopy (по образцу adm.CharRestore), asda_ops — только EXECUTE; цель — служебная учётка ≤ 5000,
--   свободный слот 10–12, новое имя; состав — UPDeleteChar + CharRefine + CharFameHigh (%(n)d таблиц), БЕЗ связей с другими игроками
--   и деньгами (друзья, клан, соулмейт, камни душ, почта, аукцион, посещаемость, рейтинг, интро, GM-флаг слота, CharacterStat);
--   каждому предмету — новый Uuid (NEWID), непустым Uc1…4 — тоже новые; соответствие «старый → новый» — adm.CharCopyItemMap;
--   JoyLog1 не пишется (копия — не игровое событие); откат — adm.CharCopyDelete (удаление копии по отметке adm.CharCopied).
--   Рейтинг чести: штатный dbo.UP_CampPointRank делает TRUNCATE TABLE — цепочка владения его не покрывает (TRUNCATE требует ALTER),
--   EXECUTE AS OWNER на dev невозможен (владелец Joy1 без входа) — поэтому adm.CampPointRank = тело штатной процедуры с DELETE
--   вместо TRUNCATE (итог тот же), asda_ops — только EXECUTE.
-- ПРОВЕРКИ adm.CharCopy (THROW откатывает и транзакцию вызывающего): источник есть; цель ≤ 5000; у цели < 3 персонажей (4-й ломает
--   вход: LoginManager «Character Count Over»); слот 10–12 пуст во ВСЕХ таблицах копии; имя не пусто и свободно в Charinfo/CharPos/
--   Del_Charinfo. Остатки прежнего владельца слота в CharRefine / CharFameHigh (UPDeleteChar их не удаляет) заменяются копией —
--   прежде снимком в adm.CharCopyReplaced_<таблица> (ревизия 26 С-2; удаление копии их возвращает).
--   Правило имени (A13), «обе учётки не в игре» — панель в той же транзакции до вызова (domains/charcopy.py).
-- АРМИЯ копии (CharCamp.Campidx) — армия учётки-цели, если она есть, иначе −1 (как после UPCharCampReset); CampData не меняется.
-- ═══════════════════════════════════════════════════════════════════════════
USE [Joy1];
GO
IF SCHEMA_ID('adm') IS NULL EXEC('CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID('adm.CharCopied', 'U') IS NULL
CREATE TABLE adm.CharCopied (
	CopyId      INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_CharCopied PRIMARY KEY,
	SrcUserindex INT         NOT NULL,
	SrcCharidx  TINYINT      NOT NULL,
	SrcName     VARCHAR(20)  NULL,
	DstUserindex INT         NOT NULL,
	DstCharidx  TINYINT      NOT NULL,
	NewName     VARCHAR(20)  NOT NULL,
	Items       INT          NOT NULL,
	CopiedAt    DATETIME     NOT NULL CONSTRAINT DF_CharCopied_At DEFAULT (GETDATE()),
	Operator    VARCHAR(64)  NULL,
	DeletedAt   DATETIME     NULL,              -- копия удалена (откат) — строка остаётся как история
	DeletedBy   VARCHAR(64)  NULL
);
GO
IF OBJECT_ID('adm.CharCopyItemMap', 'U') IS NULL
CREATE TABLE adm.CharCopyItemMap (
	CopyId      INT          NOT NULL,
	Kind        TINYINT      NOT NULL,          -- 0 — Uuid предмета, 1…4 — Uc1…Uc4 (номер камня в гнезде)
	OldUuid     VARCHAR(36)  NOT NULL,
	NewUuid     VARCHAR(36)  NOT NULL,
	CONSTRAINT PK_CharCopyItemMap PRIMARY KEY (CopyId, Kind, NewUuid)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CharCopyItemMap_New' AND object_id = OBJECT_ID('adm.CharCopyItemMap'))
	CREATE INDEX IX_CharCopyItemMap_New ON adm.CharCopyItemMap (NewUuid);
GO
-- ★ ревизия 26 С-2: снимки строк удалённого персонажа, которые копия заменила в слоте (возвращает adm.CharCopyDelete; строки остаются историей)
%(snap_tbl)s
IF OBJECT_ID('adm.CharCopy', 'P') IS NOT NULL DROP PROCEDURE adm.CharCopy;
GO
CREATE PROCEDURE adm.CharCopy @SrcU INT, @SrcC TINYINT, @DstU INT, @DstC TINYINT, @Name VARCHAR(20), @Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @busy NVARCHAR(64), @n INT, @Uid VARCHAR(61), @Camp SMALLINT, @SrcName VARCHAR(20), @items INT, @id INT;
	BEGIN TRANSACTION;
	-- блокировки: учётки источника и цели (Us_member, CharPos) панель уже держит (items.online_state); здесь — персонажи цели
	SELECT @n = COUNT(*) FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @DstU;
	SELECT @SrcName = Charname FROM dbo.Charinfo WHERE Userindex = @SrcU AND Charidx = @SrcC;
	IF @SrcName IS NULL
	THROW 50021, N'adm.CharCopy: персонажа-источника нет', 1;
	IF @DstU > 5000 OR @DstU < 1
	THROW 50022, N'adm.CharCopy: цель — только служебная учётка (номер до 5000)', 1;
	IF @n >= 3
	THROW 50023, N'adm.CharCopy: у учётки-цели уже 3 персонажа', 1;
	IF @DstC NOT IN (10, 11, 12)
	THROW 50024, N'adm.CharCopy: слот только 10, 11 или 12', 1;
	IF @Name IS NULL OR LTRIM(RTRIM(@Name)) = ''
	THROW 50025, N'adm.CharCopy: нет нового имени', 1;
	IF EXISTS (SELECT 1 FROM dbo.Charinfo WHERE Charname = @Name) OR EXISTS (SELECT 1 FROM dbo.CharPos WHERE Charname = @Name)
	   OR EXISTS (SELECT 1 FROM dbo.Del_Charinfo WHERE Charname = @Name)
	THROW 50026, N'adm.CharCopy: имя занято', 1;
	SELECT @Uid = Us_id FROM AsdaStoryOp.dbo.Us_member WHERE Userindex = @DstU;
	IF @Uid IS NULL
	THROW 50027, N'adm.CharCopy: учётки-цели нет в Us_member', 1;
	SET @busy = NULL;
%(busy)s
	IF @busy IS NOT NULL
	BEGIN DECLARE @m NVARCHAR(200) = CONCAT(N'adm.CharCopy: слот ', @DstC, N' занят (таблица ', @busy, N')'); THROW 50028, @m, 1; END;
	SET @Camp = ISNULL((SELECT TOP 1 Campidx FROM dbo.CharCamp WHERE Userindex = @DstU AND Campidx <> -1 ORDER BY Charidx), -1);
	-- номер копии — до вставок (им помечаются снимки заменённых строк); число предметов дописывается в конце
	INSERT INTO adm.CharCopied (SrcUserindex, SrcCharidx, SrcName, DstUserindex, DstCharidx, NewName, Items, Operator)
	VALUES (@SrcU, @SrcC, @SrcName, @DstU, @DstC, @Name, 0, @Operator);
	SET @id = SCOPE_IDENTITY();
	-- ▼ копия строк слота (Userindex/Charidx — цели; подмены — см. tools/gen_charcopy_sql.py COPY)
%(copy)s
	-- ▼ предметы: новый Uuid каждому, новые Uc1…4 там, где они не пусты
%(item)s
	SET @items = (SELECT COUNT(*) FROM #it);
	IF NOT EXISTS (SELECT 1 FROM dbo.CharOption WHERE Userindex = @DstU)
		INSERT INTO dbo.CharOption (Userindex, NormalChat, SmChat, FriendChat, PartyChat, GuildChat, Whisper, Acv, SmEnroll, FriendEnroll,
			PartyEnroll, GuildEnroll, Change, SChange, Monster, Charname, Hat, SoulAttack, ClanAttack, UserAttack)
		VALUES (@DstU, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1);      -- как OpCharacterRestore / adm.CharRestore
	IF NOT EXISTS (SELECT 1 FROM dbo.Charinfo WHERE Userindex = @DstU AND Charidx = @DstC)
	   OR NOT EXISTS (SELECT 1 FROM dbo.CharPos WHERE Userindex = @DstU AND Charidx = @DstC)
	THROW 50029, N'adm.CharCopy: Charinfo/CharPos не скопировались', 1;
	UPDATE adm.CharCopied SET Items = @items WHERE CopyId = @id;
	INSERT INTO adm.CharCopyItemMap (CopyId, Kind, OldUuid, NewUuid)
	SELECT @id, 0, OldUuid, CAST(NewUuid AS VARCHAR(36)) FROM #it
	UNION ALL SELECT @id, 1, OldUc1, NewUc1 FROM #it WHERE NewUc1 IS NOT NULL
	UNION ALL SELECT @id, 2, OldUc2, NewUc2 FROM #it WHERE NewUc2 IS NOT NULL
	UNION ALL SELECT @id, 3, OldUc3, NewUc3 FROM #it WHERE NewUc3 IS NOT NULL
	UNION ALL SELECT @id, 4, OldUc4, NewUc4 FROM #it WHERE NewUc4 IS NOT NULL;
	DROP TABLE #it;
	COMMIT;
	SELECT @id AS CopyId, @items AS Items, @Camp AS Camp;
	RETURN 0;
GO
IF OBJECT_ID('adm.CharCopyDelete', 'P') IS NOT NULL DROP PROCEDURE adm.CharCopyDelete;
GO
-- откат копии: удалить персонажа-копию целиком (все таблицы копии) — только по отметке adm.CharCopied, только на служебной учётке,
-- только пока у копии не появилось связей с другими игроками (друзья, клан, аукцион, почта, камни душ, оповещения аукциона): их панель
-- за игрока не разрывает; стирает всё, что стирает UPDeleteChar у слота, и возвращает снимки заменённых копией строк (ревизия 26)
CREATE PROCEDURE adm.CharCopyDelete @CopyId INT, @Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @DstU INT, @DstC TINYINT, @Name VARCHAR(20), @busy NVARCHAR(64);
	BEGIN TRANSACTION;
	SELECT @DstU = DstUserindex, @DstC = DstCharidx, @Name = NewName FROM adm.CharCopied WITH (UPDLOCK, HOLDLOCK)
	 WHERE CopyId = @CopyId AND DeletedAt IS NULL;
	IF @DstU IS NULL
	THROW 50031, N'adm.CharCopyDelete: копии нет или она уже удалена', 1;
	IF @DstU > 5000
	THROW 50032, N'adm.CharCopyDelete: копия не на служебной учётке', 1;
	IF NOT EXISTS (SELECT 1 FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @DstU AND Charidx = @DstC AND Charname = @Name)
	THROW 50033, N'adm.CharCopyDelete: в слоте копии другой персонаж (или копия переименована)', 1;
	-- ★ ревизия 26 С-1: связи с другими игроками — отказ с ПЕРЕЧНЕМ таблиц (их панель за игрока не разрывает)
	SET @busy = N'';
%(links)s
	IF @busy <> N''
	BEGIN DECLARE @m NVARCHAR(400) = CONCAT(N'adm.CharCopyDelete: у копии появились связи (таблица ', @busy, N')'); THROW 50034, @m, 1; END;
	-- всё, что стирает UPDeleteChar у персонажа слота (таблицы копии + посещаемость, позиция в подземелье, «о себе», рейтинг славы)
%(delete)s
	-- ★ ревизия 26 С-2: вернуть строки удалённого персонажа, которые копия заменила
%(snap_back)s
	UPDATE adm.CharCopied SET DeletedAt = GETDATE(), DeletedBy = @Operator WHERE CopyId = @CopyId;
	COMMIT;
	SELECT 1 AS ok;
	RETURN 0;
GO
IF OBJECT_ID('adm.CampPointRank', 'P') IS NOT NULL DROP PROCEDURE adm.CampPointRank;
GO
-- пересчёт рейтинга чести — тело штатного dbo.UP_CampPointRank (2009-06-10) без изменений, кроме одного: TRUNCATE TABLE → DELETE.
-- TRUNCATE требует ALTER на таблицу, цепочка владения его не покрывает, а WITH EXECUTE AS OWNER на dev не работает (владелец базы
-- Joy1 не сопоставлен входу — «участник dbo не существует», проверено 18.11); у CampPointRank нет IDENTITY — итог тот же.
-- Одна транзакция (рейтинг не бывает наполовину пустым). Итог — строк в рейтинге.
CREATE PROCEDURE adm.CampPointRank
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	BEGIN TRANSACTION;
	DELETE FROM dbo.CampPointRank;
	INSERT INTO dbo.CampPointRank (Ranking,Userindex,Charidx,CampPoint,Per)
	SELECT RANK() OVER (ORDER BY CampPoint DESC),userindex,charidx,CampPoint,0
	FROM dbo.CharCamp
	WHERE CampPoint > 0 AND Userindex > 5000
	UPDATE dbo.CampPointRank
	SET Per=CAST ( cast( cast( Ranking AS Float ) / 21 AS Float)  * 1000 AS INTEGER)
	COMMIT;
	SELECT COUNT(*) AS Ranked FROM dbo.CampPointRank;
	RETURN 0;
GO
PRINT 'adminc_08_charcopy: OK';
GO
"""

if __name__ == "__main__":
    sys.exit(main(sys.argv))
