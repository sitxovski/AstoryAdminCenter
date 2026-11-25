-- Copyright (c) 2026 @sitxovski (Discord)
-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_08_charcopy.sql — копия персонажа на служебную учётку (≤ 5000) и обёртка пересчёта рейтинга чести. Волна А1, 18.11.2026.
-- СОБРАН ПРОГРАММОЙ tools/gen_charcopy_sql.py из выгрузки столбцов Joy1 (sys.columns 18.11.2026). Разбор:
-- Reports/admin_center/research_a1_char_rest.md §7 (копия), §3 (рейтинг чести). Решения владельца 18.11:
--   копия — своя процедура adm.CharCopy (по образцу adm.CharRestore), asda_ops — только EXECUTE; цель — служебная учётка ≤ 5000,
--   свободный слот 10–12, новое имя; состав — UPDeleteChar + CharRefine + CharFameHigh (33 таблиц), БЕЗ связей с другими игроками
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
IF OBJECT_ID('adm.CharCopyReplaced_CharFameHigh', 'U') IS NULL
CREATE TABLE adm.CharCopyReplaced_CharFameHigh (
	CopyId INT NOT NULL,
	UserIndex INT NOT NULL,
	CharIdx TINYINT NOT NULL,
	BankHi1 BIGINT NOT NULL,
	BankHi2 BIGINT NOT NULL,
	BankHi3 BIGINT NOT NULL,
	BankHi4 BIGINT NOT NULL,
	ProgHi1 BIGINT NOT NULL,
	ProgHi2 BIGINT NOT NULL,
	ProgHi3 BIGINT NOT NULL,
	ProgHi4 BIGINT NOT NULL,
	UpdateDate DATETIME NOT NULL
);
GO
IF OBJECT_ID('adm.CharCopyReplaced_CharRefine', 'U') IS NULL
CREATE TABLE adm.CharCopyReplaced_CharRefine (
	CopyId INT NOT NULL,
	Userindex INT NOT NULL,
	Charidx TINYINT NOT NULL,
	pLvl SMALLINT NOT NULL,
	pExp INT NOT NULL,
	aLvl SMALLINT NOT NULL,
	aExp INT NOT NULL,
	mLvl SMALLINT NOT NULL,
	mExp INT NOT NULL
);
GO
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
	IF EXISTS (SELECT 1 FROM dbo.Charinfo WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'Charinfo';
	IF EXISTS (SELECT 1 FROM dbo.CharPos WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharPos';
	IF EXISTS (SELECT 1 FROM dbo.CharAppr WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharAppr';
	IF EXISTS (SELECT 1 FROM dbo.CharChat WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharChat';
	IF EXISTS (SELECT 1 FROM dbo.CharConstellation WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharConstellation';
	IF EXISTS (SELECT 1 FROM dbo.CharEpisode WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharEpisode';
	IF EXISTS (SELECT 1 FROM dbo.EpisodeTime WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'EpisodeTime';
	IF EXISTS (SELECT 1 FROM dbo.VillagePos WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'VillagePos';
	IF EXISTS (SELECT 1 FROM dbo.CharQuest WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharQuest';
	IF EXISTS (SELECT 1 FROM dbo.CharSkill WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharSkill';
	IF EXISTS (SELECT 1 FROM dbo.CharSkillitem WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharSkillitem';
	IF EXISTS (SELECT 1 FROM dbo.CharSlot WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharSlot';
	IF EXISTS (SELECT 1 FROM dbo.CharStatus WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharStatus';
	IF EXISTS (SELECT 1 FROM dbo.CharSmStatus WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharSmStatus';
	IF EXISTS (SELECT 1 FROM dbo.CharFame WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharFame';
	IF EXISTS (SELECT 1 FROM dbo.CharFameBank WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharFameBank';
	IF EXISTS (SELECT 1 FROM dbo.CharFameProgress WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharFameProgress';
	IF EXISTS (SELECT 1 FROM dbo.CharCamp WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharCamp';
	IF EXISTS (SELECT 1 FROM dbo.CharPlusPackage WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharPlusPackage';
	IF EXISTS (SELECT 1 FROM dbo.CharFish WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharFish';
	IF EXISTS (SELECT 1 FROM dbo.CharFishBookInfo WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharFishBookInfo';
	IF EXISTS (SELECT 1 FROM dbo.CRT_CharCraftInfo WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CRT_CharCraftInfo';
	IF EXISTS (SELECT 1 FROM dbo.CRT_LimitationQuest WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CRT_LimitationQuest';
	IF EXISTS (SELECT 1 FROM dbo.CRT_MainLimitationQuest WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CRT_MainLimitationQuest';
	IF EXISTS (SELECT 1 FROM dbo.CharTutorial WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharTutorial';
	IF EXISTS (SELECT 1 FROM dbo.SoulGuardian WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'SoulGuardian';
	IF EXISTS (SELECT 1 FROM dbo.ItemCoolTime WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'ItemCoolTime';
	IF EXISTS (SELECT 1 FROM dbo.SkillCoolTime WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'SkillCoolTime';
	IF EXISTS (SELECT 1 FROM dbo.SMSkillCoolTime WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'SMSkillCoolTime';
	IF EXISTS (SELECT 1 FROM dbo.CharPetList WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'CharPetList';
	IF EXISTS (SELECT 1 FROM dbo.Item WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = N'Item';
	IF @busy IS NOT NULL
	BEGIN DECLARE @m NVARCHAR(200) = CONCAT(N'adm.CharCopy: слот ', @DstC, N' занят (таблица ', @busy, N')'); THROW 50028, @m, 1; END;
	SET @Camp = ISNULL((SELECT TOP 1 Campidx FROM dbo.CharCamp WHERE Userindex = @DstU AND Campidx <> -1 ORDER BY Charidx), -1);
	-- номер копии — до вставок (им помечаются снимки заменённых строк); число предметов дописывается в конце
	INSERT INTO adm.CharCopied (SrcUserindex, SrcCharidx, SrcName, DstUserindex, DstCharidx, NewName, Items, Operator)
	VALUES (@SrcU, @SrcC, @SrcName, @DstU, @DstC, @Name, 0, @Operator);
	SET @id = SCOPE_IDENTITY();
	-- ▼ копия строк слота (Userindex/Charidx — цели; подмены — см. tools/gen_charcopy_sql.py COPY)
	INSERT INTO dbo.Charinfo (Userindex, Charidx, Uid, Charname, Gender, Lvl, Expe, JobCount, Class, Job, Subjob, SkillPoint, MaxWeight, Weight, MaxHp, MaxMp, Hp, Mp, ActPoint, DonationPoint, Strength, Agility, Health, Spell, Mentality, Fortune, StrengthP, AgilityP, HealthP, SpellP, MentalityP, FortuneP, StrengthP2, AgilityP2, HealthP2, SpellP2, MentalityP2, FortuneP2, MinAttack, MaxAttack, MinMagicAtt, MaxMagicAtt, MagicDefense, MinDefense1, MaxDefense1, MinDefense2, MaxDefense2, Getitem, BlockMin, BlockMax, BlockDamage, Critical, Evasion, Pcrirate, Mcrirate, Fire, Water, Earth, Climate, Light, Dark, FireR, WaterR, EarthR, ClimateR, LightR, DarkR, WareCount, CwareCount, PetCount, Share)
	SELECT @DstU, @DstC, @Uid, @Name, Gender, Lvl, Expe, JobCount, Class, Job, Subjob, SkillPoint, MaxWeight, Weight, MaxHp, MaxMp, Hp, Mp, ActPoint, DonationPoint, Strength, Agility, Health, Spell, Mentality, Fortune, StrengthP, AgilityP, HealthP, SpellP, MentalityP, FortuneP, StrengthP2, AgilityP2, HealthP2, SpellP2, MentalityP2, FortuneP2, MinAttack, MaxAttack, MinMagicAtt, MaxMagicAtt, MagicDefense, MinDefense1, MaxDefense1, MinDefense2, MaxDefense2, Getitem, BlockMin, BlockMax, BlockDamage, Critical, Evasion, Pcrirate, Mcrirate, Fire, Water, Earth, Climate, Light, Dark, FireR, WaterR, EarthR, ClimateR, LightR, DarkR, WareCount, CwareCount, PetCount, 0
	FROM dbo.Charinfo WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharPos (Userindex, Charidx, Uid, Charname, Usernum, Poridx, Posx, Posy, Gsidx, Threadidx, Channel, Cporidx, Partyidx, Captain, State, SoulState, pState, LastDate)
	SELECT @DstU, @DstC, @Uid, @Name, -1, Poridx, Posx, Posy, Gsidx, Threadidx, Channel, Cporidx, -1, 0, 0, 0, 0, LastDate
	FROM dbo.CharPos WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharAppr (Userindex, Charidx, HairStyle, HairColor, FaceType)
	SELECT @DstU, @DstC, HairStyle, HairColor, FaceType
	FROM dbo.CharAppr WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharChat (Userindex, Charidx, npc1, npc2, npc3, npc4, npc5, npc6, npc7, npc8, npc9, npc10, npc11, npc12, npc13, npc14, npc15, npc16, npc17, npc18, npc19, npc20, npc21, npc22, npc23, npc24, npc25, npc26, npc27, npc28, npc29, npc30, npc31, npc32, npc33, npc34, npc35, npc36, npc37, npc38, npc39, npc40, npc41, npc42, npc43, npc44, npc45, npc46, npc47, npc48, npc49, npc50, npc51, npc52, npc53, npc54, npc55, npc56, npc57, npc58, npc59, npc60, npc61, npc62, npc63, npc64, npc65, npc66, npc67, npc68, npc69, npc70, npc71, npc72, npc73, npc74, npc75, npc76, npc77, npc78, npc79, npc80, npc81, npc82, npc83, npc84, npc85, npc86, npc87, npc88, npc89, npc90, npc91, npc92, npc93, npc94, npc95, npc96, npc97, npc98, npc99, npc100, npc101, npc102, npc103, npc104, npc105, npc106, npc107, npc108, npc109, npc110, npc111, npc112, npc113, npc114, npc115, npc116, npc117, npc118, npc119, npc120, npc121, npc122, npc123, npc124, npc125, npc126, npc127, npc128, npc129, npc130, npc131, npc132, npc133, npc134, npc135, npc136, npc137, npc138, npc139, npc140, npc141, npc142, npc143, npc144, npc145, npc146, npc147, npc148, npc149, npc150, npc151, npc152, npc153, npc154, npc155, npc156, npc157, npc158, npc159, npc160, npc161, npc162, npc163, npc164, npc165, npc166, npc167, npc168, npc169, npc170, npc171, npc172, npc173, npc174, npc175, npc176, npc177, npc178, npc179, npc180, npc181, npc182, npc183, npc184, npc185, npc186, npc187, npc188, npc189, npc190, npc191, npc192, npc193, npc194, npc195, npc196, npc197, npc198, npc199, npc200)
	SELECT @DstU, @DstC, npc1, npc2, npc3, npc4, npc5, npc6, npc7, npc8, npc9, npc10, npc11, npc12, npc13, npc14, npc15, npc16, npc17, npc18, npc19, npc20, npc21, npc22, npc23, npc24, npc25, npc26, npc27, npc28, npc29, npc30, npc31, npc32, npc33, npc34, npc35, npc36, npc37, npc38, npc39, npc40, npc41, npc42, npc43, npc44, npc45, npc46, npc47, npc48, npc49, npc50, npc51, npc52, npc53, npc54, npc55, npc56, npc57, npc58, npc59, npc60, npc61, npc62, npc63, npc64, npc65, npc66, npc67, npc68, npc69, npc70, npc71, npc72, npc73, npc74, npc75, npc76, npc77, npc78, npc79, npc80, npc81, npc82, npc83, npc84, npc85, npc86, npc87, npc88, npc89, npc90, npc91, npc92, npc93, npc94, npc95, npc96, npc97, npc98, npc99, npc100, npc101, npc102, npc103, npc104, npc105, npc106, npc107, npc108, npc109, npc110, npc111, npc112, npc113, npc114, npc115, npc116, npc117, npc118, npc119, npc120, npc121, npc122, npc123, npc124, npc125, npc126, npc127, npc128, npc129, npc130, npc131, npc132, npc133, npc134, npc135, npc136, npc137, npc138, npc139, npc140, npc141, npc142, npc143, npc144, npc145, npc146, npc147, npc148, npc149, npc150, npc151, npc152, npc153, npc154, npc155, npc156, npc157, npc158, npc159, npc160, npc161, npc162, npc163, npc164, npc165, npc166, npc167, npc168, npc169, npc170, npc171, npc172, npc173, npc174, npc175, npc176, npc177, npc178, npc179, npc180, npc181, npc182, npc183, npc184, npc185, npc186, npc187, npc188, npc189, npc190, npc191, npc192, npc193, npc194, npc195, npc196, npc197, npc198, npc199, npc200
	FROM dbo.CharChat WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharConstellation (Userindex, Charidx, Constellation)
	SELECT @DstU, @DstC, Constellation
	FROM dbo.CharConstellation WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharEpisode (Userindex, Charidx, Code, Posx, State, Episodeidx, Stepidx, Etime, Eitem1, Amount1, Eitem2, Amount2, Eitem3, Amount3, Eitem4, Amount4, Eitem5, Amount5)
	SELECT @DstU, @DstC, Code, Posx, State, Episodeidx, Stepidx, Etime, Eitem1, Amount1, Eitem2, Amount2, Eitem3, Amount3, Eitem4, Amount4, Eitem5, Amount5
	FROM dbo.CharEpisode WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.EpisodeTime (Userindex, Charidx, Etime1, Etime2, Etime3, Etime4, Etime5, Etime6, Etime7, Etime8, Etime9, Etime10, Etime11, Etime12)
	SELECT @DstU, @DstC, Etime1, Etime2, Etime3, Etime4, Etime5, Etime6, Etime7, Etime8, Etime9, Etime10, Etime11, Etime12
	FROM dbo.EpisodeTime WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.VillagePos (Userindex, Charidx, Villageidx, Posx, Posy, Ipaddress, Port)
	SELECT @DstU, @DstC, Villageidx, Posx, Posy, Ipaddress, Port
	FROM dbo.VillagePos WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharQuest (Userindex, Charidx, Quest1, Quest2, Quest3, Quest4, Quest5, Quest6, Quest7, Quest8, Quest9, Quest10, Quest11, Quest12, Quest13, Quest14, Quest15, Quest16, Quest17, Quest18, Quest19, Quest20)
	SELECT @DstU, @DstC, Quest1, Quest2, Quest3, Quest4, Quest5, Quest6, Quest7, Quest8, Quest9, Quest10, Quest11, Quest12, Quest13, Quest14, Quest15, Quest16, Quest17, Quest18, Quest19, Quest20
	FROM dbo.CharQuest WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharSkill (Userindex, Charidx, Skillidx, Lvl, Cooltime, Distance, Scope, Mpvalue, Evalue, SkillPer, SubSkillPer, SubValue1, SubTime1, SubValue2, SubTime2, SubValue3, SubTime3)
	SELECT @DstU, @DstC, Skillidx, Lvl, Cooltime, Distance, Scope, Mpvalue, Evalue, SkillPer, SubSkillPer, SubValue1, SubTime1, SubValue2, SubTime2, SubValue3, SubTime3
	FROM dbo.CharSkill WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharSkillitem (Userindex, Charidx, Code1, Time1, Value1, Code2, Time2, Value2, Code3, Time3, Value3, Code4, Time4, Value4, Code5, Time5, Value5, Code6, Time6, Value6, Code7, Time7, Value7, Code8, Time8, Value8, Code9, Time9, Value9, Code10, Time10, Value10, Code11, Time11, Value11, Code12, Time12, Value12, Code13, Time13, Value13, Code14, Time14, Value14, Code15, Time15, Value15, Code16, Time16, Value16, Code17, Time17, Value17, Code18, Time18, Value18, Code19, Time19, Value19, Code20, Time20, Value20, Code21, Time21, Value21, Code22, Time22, Value22, Code23, Time23, Value23, Code24, Time24, Value24, Code25, Time25, Value25, Code26, Time26, Value26, Code27, Time27, Value27, Code28, Time28, Value28, Code29, Time29, Value29, Code30, Time30, Value30)
	SELECT @DstU, @DstC, Code1, Time1, Value1, Code2, Time2, Value2, Code3, Time3, Value3, Code4, Time4, Value4, Code5, Time5, Value5, Code6, Time6, Value6, Code7, Time7, Value7, Code8, Time8, Value8, Code9, Time9, Value9, Code10, Time10, Value10, Code11, Time11, Value11, Code12, Time12, Value12, Code13, Time13, Value13, Code14, Time14, Value14, Code15, Time15, Value15, Code16, Time16, Value16, Code17, Time17, Value17, Code18, Time18, Value18, Code19, Time19, Value19, Code20, Time20, Value20, Code21, Time21, Value21, Code22, Time22, Value22, Code23, Time23, Value23, Code24, Time24, Value24, Code25, Time25, Value25, Code26, Time26, Value26, Code27, Time27, Value27, Code28, Time28, Value28, Code29, Time29, Value29, Code30, Time30, Value30
	FROM dbo.CharSkillitem WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharSlot (Userindex, Charidx, Slotidx, Type, Plate, Posx, Amount, eindex)
	SELECT @DstU, @DstC, Slotidx, Type, Plate, Posx, Amount, eindex
	FROM dbo.CharSlot WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharStatus (Userindex, Charidx, Skillidx1, MSkillidx1, Sub1, Count1, Type1, Time1, Lvl1, Evalue1, Skillidx2, MSkillidx2, Sub2, Count2, Type2, Time2, Lvl2, Evalue2, Skillidx3, MSkillidx3, Sub3, Count3, Type3, Time3, Lvl3, Evalue3, Skillidx4, Mskillidx4, Sub4, Count4, Type4, Time4, Lvl4, Evalue4, Skillidx5, Mskillidx5, Sub5, Count5, Type5, Time5, Lvl5, Evalue5, Skillidx6, Mskillidx6, Sub6, Count6, Type6, Time6, Lvl6, Evalue6, Skillidx7, Mskillidx7, Sub7, Count7, Type7, Time7, Lvl7, Evalue7, Skillidx8, Mskillidx8, Sub8, Count8, Type8, Time8, Lvl8, Evalue8, Skillidx9, Mskillidx9, Sub9, Count9, Type9, Time9, Lvl9, Evalue9, Skillidx10, Mskillidx10, Sub10, Count10, Type10, Time10, Lvl10, Evalue10, Skillidx11, Mskillidx11, Sub11, Count11, Type11, Time11, Lvl11, Evalue11, Skillidx12, Mskillidx12, Sub12, Count12, Type12, Time12, Lvl12, Evalue12, Skillidx13, Mskillidx13, Sub13, Count13, Type13, Time13, Lvl13, Evalue13, Skillidx14, Mskillidx14, Sub14, Count14, Type14, Time14, Lvl14, Evalue14, Skillidx15, Mskillidx15, Sub15, Count15, Type15, Time15, Lvl15, Evalue15, Skillidx16, Mskillidx16, Sub16, Count16, Type16, Time16, Lvl16, Evalue16, Skillidx17, Mskillidx17, Sub17, Count17, Type17, Time17, Lvl17, Evalue17, Skillidx18, Mskillidx18, Sub18, Count18, Type18, Time18, Lvl18, Evalue18, Skillidx19, Mskillidx19, Sub19, Count19, Type19, Time19, Lvl19, Evalue19, Skillidx20, Mskillidx20, Sub20, Count20, Type20, Time20, Lvl20, Evalue20, Skillidx21, Mskillidx21, Sub21, Count21, Type21, Time21, Lvl21, Evalue21, Skillidx22, Mskillidx22, Sub22, Count22, Type22, Time22, Lvl22, Evalue22, Skillidx23, Mskillidx23, Sub23, Count23, Type23, Time23, Lvl23, Evalue23, Skillidx24, Mskillidx24, Sub24, Count24, Type24, Time24, Lvl24, Evalue24, Skillidx25, Mskillidx25, Sub25, Count25, Type25, Time25, Lvl25, Evalue25, Skillidx26, Mskillidx26, Sub26, Count26, Type26, Time26, Lvl26, Evalue26, Skillidx27, Mskillidx27, Sub27, Count27, Type27, Time27, Lvl27, Evalue27, Skillidx28, Mskillidx28, Sub28, Count28, Type28, Time28, Lvl28, Evalue28)
	SELECT @DstU, @DstC, Skillidx1, MSkillidx1, Sub1, Count1, Type1, Time1, Lvl1, Evalue1, Skillidx2, MSkillidx2, Sub2, Count2, Type2, Time2, Lvl2, Evalue2, Skillidx3, MSkillidx3, Sub3, Count3, Type3, Time3, Lvl3, Evalue3, Skillidx4, Mskillidx4, Sub4, Count4, Type4, Time4, Lvl4, Evalue4, Skillidx5, Mskillidx5, Sub5, Count5, Type5, Time5, Lvl5, Evalue5, Skillidx6, Mskillidx6, Sub6, Count6, Type6, Time6, Lvl6, Evalue6, Skillidx7, Mskillidx7, Sub7, Count7, Type7, Time7, Lvl7, Evalue7, Skillidx8, Mskillidx8, Sub8, Count8, Type8, Time8, Lvl8, Evalue8, Skillidx9, Mskillidx9, Sub9, Count9, Type9, Time9, Lvl9, Evalue9, Skillidx10, Mskillidx10, Sub10, Count10, Type10, Time10, Lvl10, Evalue10, Skillidx11, Mskillidx11, Sub11, Count11, Type11, Time11, Lvl11, Evalue11, Skillidx12, Mskillidx12, Sub12, Count12, Type12, Time12, Lvl12, Evalue12, Skillidx13, Mskillidx13, Sub13, Count13, Type13, Time13, Lvl13, Evalue13, Skillidx14, Mskillidx14, Sub14, Count14, Type14, Time14, Lvl14, Evalue14, Skillidx15, Mskillidx15, Sub15, Count15, Type15, Time15, Lvl15, Evalue15, Skillidx16, Mskillidx16, Sub16, Count16, Type16, Time16, Lvl16, Evalue16, Skillidx17, Mskillidx17, Sub17, Count17, Type17, Time17, Lvl17, Evalue17, Skillidx18, Mskillidx18, Sub18, Count18, Type18, Time18, Lvl18, Evalue18, Skillidx19, Mskillidx19, Sub19, Count19, Type19, Time19, Lvl19, Evalue19, Skillidx20, Mskillidx20, Sub20, Count20, Type20, Time20, Lvl20, Evalue20, Skillidx21, Mskillidx21, Sub21, Count21, Type21, Time21, Lvl21, Evalue21, Skillidx22, Mskillidx22, Sub22, Count22, Type22, Time22, Lvl22, Evalue22, Skillidx23, Mskillidx23, Sub23, Count23, Type23, Time23, Lvl23, Evalue23, Skillidx24, Mskillidx24, Sub24, Count24, Type24, Time24, Lvl24, Evalue24, Skillidx25, Mskillidx25, Sub25, Count25, Type25, Time25, Lvl25, Evalue25, Skillidx26, Mskillidx26, Sub26, Count26, Type26, Time26, Lvl26, Evalue26, Skillidx27, Mskillidx27, Sub27, Count27, Type27, Time27, Lvl27, Evalue27, Skillidx28, Mskillidx28, Sub28, Count28, Type28, Time28, Lvl28, Evalue28
	FROM dbo.CharStatus WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharSmStatus (Userindex, Charidx, skidx1, Stime1, Lvl1, Skidx2, Stime2, Lvl2, Skidx3, Stime3, Lvl3, Skidx4, Stime4, Lvl4, Skidx5, Stime5, Lvl5, Skidx6, Stime6, Lvl6, Skidx7, Stime7, Lvl7, Skidx8, Stime8, Lvl8, Skidx9, Stime9, Lvl9, Skidx10, Stime10, Lvl10, Skidx11, Stime11, Lvl11, Skidx12, Stime12, Lvl12, Skidx13, Stime13, Lvl13, Skidx14, Stime14, Lvl14, Skidx15, Stime15, Lvl15, Skidx16, Stime16, Lvl16, Skidx17, Stime17, Lvl17, Skidx18, Stime18, Lvl18, Skidx19, Stime19, Lvl19, Skidx20, Stime20, Lvl20, Skidx21, Stime21, Lvl21, Skidx22, Stime22, Lvl22, Skidx23, Stime23, Lvl23, Skidx24, Stime24, Lvl24, Skidx25, Stime25, Lvl25, Skidx26, Stime26, Lvl26, Skidx27, Stime27, Lvl27, Skidx28, Stime28, Lvl28, Skidx29, Stime29, Lvl29, Skidx30, Stime30, Lvl30)
	SELECT @DstU, @DstC, skidx1, Stime1, Lvl1, Skidx2, Stime2, Lvl2, Skidx3, Stime3, Lvl3, Skidx4, Stime4, Lvl4, Skidx5, Stime5, Lvl5, Skidx6, Stime6, Lvl6, Skidx7, Stime7, Lvl7, Skidx8, Stime8, Lvl8, Skidx9, Stime9, Lvl9, Skidx10, Stime10, Lvl10, Skidx11, Stime11, Lvl11, Skidx12, Stime12, Lvl12, Skidx13, Stime13, Lvl13, Skidx14, Stime14, Lvl14, Skidx15, Stime15, Lvl15, Skidx16, Stime16, Lvl16, Skidx17, Stime17, Lvl17, Skidx18, Stime18, Lvl18, Skidx19, Stime19, Lvl19, Skidx20, Stime20, Lvl20, Skidx21, Stime21, Lvl21, Skidx22, Stime22, Lvl22, Skidx23, Stime23, Lvl23, Skidx24, Stime24, Lvl24, Skidx25, Stime25, Lvl25, Skidx26, Stime26, Lvl26, Skidx27, Stime27, Lvl27, Skidx28, Stime28, Lvl28, Skidx29, Stime29, Lvl29, Skidx30, Stime30, Lvl30
	FROM dbo.CharSmStatus WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharFame (Userindex, Charidx, Fameidx, Condition1, Condition2, Opidx1, Opvalue11, Opvalue12, Opidx2, Opvalue21, Opvalue22, Opidx3, Opvalue31, Opvalue32, Opidx4, Opvalue41, Opvalue42, Opidx5, Opvalue51, Opvalue52, Opidx6, Opvalue61, Opvalue62)
	SELECT @DstU, @DstC, Fameidx, Condition1, Condition2, Opidx1, Opvalue11, Opvalue12, Opidx2, Opvalue21, Opvalue22, Opidx3, Opvalue31, Opvalue32, Opidx4, Opvalue41, Opvalue42, Opidx5, Opvalue51, Opvalue52, Opidx6, Opvalue61, Opvalue62
	FROM dbo.CharFame WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharFameBank (Userindex, Charidx, Fmpoint, Fmidx1, Fmidx2, Fame1, Fame2, Fame3, Fame4)
	SELECT @DstU, @DstC, Fmpoint, Fmidx1, Fmidx2, Fame1, Fame2, Fame3, Fame4
	FROM dbo.CharFameBank WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharFameProgress (Userindex, Charidx, Fame1, Fame2, Fame3, Fame4)
	SELECT @DstU, @DstC, Fame1, Fame2, Fame3, Fame4
	FROM dbo.CharFameProgress WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO adm.CharCopyReplaced_CharFameHigh (CopyId, UserIndex, CharIdx, BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate) SELECT @id, UserIndex, CharIdx, BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate FROM dbo.CharFameHigh WHERE UserIndex = @DstU AND CharIdx = @DstC;
	DELETE FROM dbo.CharFameHigh WHERE UserIndex = @DstU AND CharIdx = @DstC;          -- остаток прежнего владельца слота (снимок выше)
	INSERT INTO dbo.CharFameHigh (UserIndex, CharIdx, BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate)
	SELECT @DstU, @DstC, BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate
	FROM dbo.CharFameHigh WHERE UserIndex = @SrcU AND CharIdx = @SrcC;
	INSERT INTO dbo.CharCamp (Userindex, Charidx, Campidx, CampPoint, CampGrade, CampFlag, CampPenaltyTime)
	SELECT @DstU, @DstC, @Camp, CampPoint, CampGrade, CampFlag, CampPenaltyTime
	FROM dbo.CharCamp WHERE Userindex = @SrcU AND Charidx = @SrcC;
	IF @Camp <> -1 AND NOT EXISTS (SELECT 1 FROM dbo.CharCamp WHERE Userindex = @DstU AND Charidx = @DstC)
		INSERT INTO dbo.CharCamp (Userindex, Charidx, Campidx, CampPoint, CampGrade, CampFlag, CampPenaltyTime) VALUES (@DstU, @DstC, @Camp, 0, 0, 0, 0);
	INSERT INTO dbo.CharPlusPackage (Userindex, Charidx, iType, StartTime, BuffPeriod, EndTime)
	SELECT @DstU, @DstC, iType, StartTime, BuffPeriod, EndTime
	FROM dbo.CharPlusPackage WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharFish (Userindex, Charidx, FishingSkill)
	SELECT @DstU, @DstC, FishingSkill
	FROM dbo.CharFish WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharFishBookInfo (Userindex, Charidx, BookCode, Complete, BookType, FishItemCode0, FishItemCode1, FishItemCode2, FishItemCode3, FishItemCode4, FishItemCode5, FishItemCode6, FishItemCode7, FishItemCode8, FishItemCode9, FishItemCode10, FishItemCode11, FishItemCode12, FishItemCode13, FishItemCode14, FishItemCode15, FishItemCode16, FishItemCode17, FishItemCode18, FishItemCode19, FishItemCode20, FishItemCode21, FishItemCode22, FishItemCode23, FishItemCode24, FishItemCode25, FishItemCode26, FishItemCode27, FishItemCode28, FishItemCode29, FishCount0, FishCount1, FishCount2, FishCount3, FishCount4, FishCount5, FishCount6, FishCount7, FishCount8, FishCount9, FishCount10, FishCount11, FishCount12, FishCount13, FishCount14, FishCount15, FishCount16, FishCount17, FishCount18, FishCount19, FishCount20, FishCount21, FishCount22, FishCount23, FishCount24, FishCount25, FishCount26, FishCount27, FishCount28, FishCount29, FishMaxSize0, FishMaxSize1, FishMaxSize2, FishMaxSize3, FishMaxSize4, FishMaxSize5, FishMaxSize6, FishMaxSize7, FishMaxSize8, FishMaxSize9, FishMaxSize10, FishMaxSize11, FishMaxSize12, FishMaxSize13, FishMaxSize14, FishMaxSize15, FishMaxSize16, FishMaxSize17, FishMaxSize18, FishMaxSize19, FishMaxSize20, FishMaxSize21, FishMaxSize22, FishMaxSize23, FishMaxSize24, FishMaxSize25, FishMaxSize26, FishMaxSize27, FishMaxSize28, FishMaxSize29, FishMinSize0, FishMinSize1, FishMinSize2, FishMinSize3, FishMinSize4, FishMinSize5, FishMinSize6, FishMinSize7, FishMinSize8, FishMinSize9, FishMinSize10, FishMinSize11, FishMinSize12, FishMinSize13, FishMinSize14, FishMinSize15, FishMinSize16, FishMinSize17, FishMinSize18, FishMinSize19, FishMinSize20, FishMinSize21, FishMinSize22, FishMinSize23, FishMinSize24, FishMinSize25, FishMinSize26, FishMinSize27, FishMinSize28, FishMinSize29)
	SELECT @DstU, @DstC, BookCode, Complete, BookType, FishItemCode0, FishItemCode1, FishItemCode2, FishItemCode3, FishItemCode4, FishItemCode5, FishItemCode6, FishItemCode7, FishItemCode8, FishItemCode9, FishItemCode10, FishItemCode11, FishItemCode12, FishItemCode13, FishItemCode14, FishItemCode15, FishItemCode16, FishItemCode17, FishItemCode18, FishItemCode19, FishItemCode20, FishItemCode21, FishItemCode22, FishItemCode23, FishItemCode24, FishItemCode25, FishItemCode26, FishItemCode27, FishItemCode28, FishItemCode29, FishCount0, FishCount1, FishCount2, FishCount3, FishCount4, FishCount5, FishCount6, FishCount7, FishCount8, FishCount9, FishCount10, FishCount11, FishCount12, FishCount13, FishCount14, FishCount15, FishCount16, FishCount17, FishCount18, FishCount19, FishCount20, FishCount21, FishCount22, FishCount23, FishCount24, FishCount25, FishCount26, FishCount27, FishCount28, FishCount29, FishMaxSize0, FishMaxSize1, FishMaxSize2, FishMaxSize3, FishMaxSize4, FishMaxSize5, FishMaxSize6, FishMaxSize7, FishMaxSize8, FishMaxSize9, FishMaxSize10, FishMaxSize11, FishMaxSize12, FishMaxSize13, FishMaxSize14, FishMaxSize15, FishMaxSize16, FishMaxSize17, FishMaxSize18, FishMaxSize19, FishMaxSize20, FishMaxSize21, FishMaxSize22, FishMaxSize23, FishMaxSize24, FishMaxSize25, FishMaxSize26, FishMaxSize27, FishMaxSize28, FishMaxSize29, FishMinSize0, FishMinSize1, FishMinSize2, FishMinSize3, FishMinSize4, FishMinSize5, FishMinSize6, FishMinSize7, FishMinSize8, FishMinSize9, FishMinSize10, FishMinSize11, FishMinSize12, FishMinSize13, FishMinSize14, FishMinSize15, FishMinSize16, FishMinSize17, FishMinSize18, FishMinSize19, FishMinSize20, FishMinSize21, FishMinSize22, FishMinSize23, FishMinSize24, FishMinSize25, FishMinSize26, FishMinSize27, FishMinSize28, FishMinSize29
	FROM dbo.CharFishBookInfo WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CRT_CharCraftInfo (Userindex, Charidx, CashCount, iLevel, iExp, iBit1, iBit2, iBit3, iBit4, iBit5, iBit6, iBit7, iBit8, iBit9)
	SELECT @DstU, @DstC, CashCount, iLevel, iExp, iBit1, iBit2, iBit3, iBit4, iBit5, iBit6, iBit7, iBit8, iBit9
	FROM dbo.CRT_CharCraftInfo WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CRT_LimitationQuest (Userindex, Charidx, Quest_Index, Quest_Type, Quest_Count, Quest_Flag)
	SELECT @DstU, @DstC, Quest_Index, Quest_Type, Quest_Count, Quest_Flag
	FROM dbo.CRT_LimitationQuest WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CRT_MainLimitationQuest (Userindex, Charidx, OldDay)
	SELECT @DstU, @DstC, OldDay
	FROM dbo.CRT_MainLimitationQuest WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharTutorial (Userindex, Charidx, Tutorial1, Tutorial2, Tutorial3, Tutorial4)
	SELECT @DstU, @DstC, Tutorial1, Tutorial2, Tutorial3, Tutorial4
	FROM dbo.CharTutorial WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO adm.CharCopyReplaced_CharRefine (CopyId, Userindex, Charidx, pLvl, pExp, aLvl, aExp, mLvl, mExp) SELECT @id, Userindex, Charidx, pLvl, pExp, aLvl, aExp, mLvl, mExp FROM dbo.CharRefine WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharRefine WHERE Userindex = @DstU AND Charidx = @DstC;          -- остаток прежнего владельца слота (снимок выше)
	INSERT INTO dbo.CharRefine (Userindex, Charidx, pLvl, pExp, aLvl, aExp, mLvl, mExp)
	SELECT @DstU, @DstC, pLvl, pExp, aLvl, aExp, mLvl, mExp
	FROM dbo.CharRefine WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.SoulGuardian (Userindex, Charidx, GuardMode, Guardidx, SkillType, Coin1, Coin2, Coin3)
	SELECT @DstU, @DstC, GuardMode, Guardidx, SkillType, Coin1, Coin2, Coin3
	FROM dbo.SoulGuardian WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.ItemCoolTime (Userindex, Charidx, Idx1, Time1, Idx2, Time2, Idx3, Time3, Idx4, Time4, Idx5, Time5, Idx6, Time6, Idx7, Time7, Idx8, Time8, Idx9, Time9, Idx10, Time10, Idx11, Time11, Idx12, Time12, Idx13, Time13, Idx14, Time14, Idx15, Time15, Idx16, Time16, Idx17, Time17, Idx18, Time18, Idx19, Time19, Idx20, Time20, Idx21, Time21, Idx22, Time22, Idx23, Time23, Idx24, Time24, Idx25, Time25, Idx26, Time26, Idx27, Time27, Idx28, Time28, Idx29, Time29, Idx30, Time30)
	SELECT @DstU, @DstC, Idx1, Time1, Idx2, Time2, Idx3, Time3, Idx4, Time4, Idx5, Time5, Idx6, Time6, Idx7, Time7, Idx8, Time8, Idx9, Time9, Idx10, Time10, Idx11, Time11, Idx12, Time12, Idx13, Time13, Idx14, Time14, Idx15, Time15, Idx16, Time16, Idx17, Time17, Idx18, Time18, Idx19, Time19, Idx20, Time20, Idx21, Time21, Idx22, Time22, Idx23, Time23, Idx24, Time24, Idx25, Time25, Idx26, Time26, Idx27, Time27, Idx28, Time28, Idx29, Time29, Idx30, Time30
	FROM dbo.ItemCoolTime WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.SkillCoolTime (Userindex, Charidx, Idx1, Time1, Idx2, Time2, Idx3, Time3, Idx4, Time4, Idx5, Time5, Idx6, Time6, Idx7, Time7, Idx8, Time8, Idx9, Time9, Idx10, Time10, Idx11, Time11, Idx12, Time12, Idx13, Time13, Idx14, Time14, Idx15, Time15, Idx16, Time16, Idx17, Time17, Idx18, Time18, Idx19, Time19, Idx20, Time20, Idx21, Time21, Idx22, Time22, Idx23, Time23, Idx24, Time24, Idx25, Time25, Idx26, Time26, Idx27, Time27, Idx28, Time28, Idx29, Time29, Idx30, Time30)
	SELECT @DstU, @DstC, Idx1, Time1, Idx2, Time2, Idx3, Time3, Idx4, Time4, Idx5, Time5, Idx6, Time6, Idx7, Time7, Idx8, Time8, Idx9, Time9, Idx10, Time10, Idx11, Time11, Idx12, Time12, Idx13, Time13, Idx14, Time14, Idx15, Time15, Idx16, Time16, Idx17, Time17, Idx18, Time18, Idx19, Time19, Idx20, Time20, Idx21, Time21, Idx22, Time22, Idx23, Time23, Idx24, Time24, Idx25, Time25, Idx26, Time26, Idx27, Time27, Idx28, Time28, Idx29, Time29, Idx30, Time30
	FROM dbo.SkillCoolTime WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.SMSkillCoolTime (Userindex, Charidx, Idx1, Time1, Idx2, Time2, Idx3, Time3, Idx4, Time4, Idx5, Time5, Idx6, Time6, Idx7, Time7, Idx8, Time8, Idx9, Time9, Idx10, Time10, Idx11, Time11, Idx12, Time12, Idx13, Time13, Idx14, Time14, Idx15, Time15, Idx16, Time16, Idx17, Time17, Idx18, Time18, Idx19, Time19, Idx20, Time20, Idx21, Time21, Idx22, Time22, Idx23, Time23, Idx24, Time24, Idx25, Time25, Idx26, Time26, Idx27, Time27, Idx28, Time28, Idx29, Time29, Idx30, Time30)
	SELECT @DstU, @DstC, Idx1, Time1, Idx2, Time2, Idx3, Time3, Idx4, Time4, Idx5, Time5, Idx6, Time6, Idx7, Time7, Idx8, Time8, Idx9, Time9, Idx10, Time10, Idx11, Time11, Idx12, Time12, Idx13, Time13, Idx14, Time14, Idx15, Time15, Idx16, Time16, Idx17, Time17, Idx18, Time18, Idx19, Time19, Idx20, Time20, Idx21, Time21, Idx22, Time22, Idx23, Time23, Idx24, Time24, Idx25, Time25, Idx26, Time26, Idx27, Time27, Idx28, Time28, Idx29, Time29, Idx30, Time30
	FROM dbo.SMSkillCoolTime WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.CharPetList (Userindex, Charidx, Plate, Petindex, PetName, FullNess, PetLvl, PetMaxLvl, PetExp, NameFlag, Active, Edate)
	SELECT @DstU, @DstC, Plate, Petindex, PetName, FullNess, PetLvl, PetMaxLvl, PetExp, NameFlag, Active, Edate
	FROM dbo.CharPetList WHERE Userindex = @SrcU AND Charidx = @SrcC;
	-- ▼ предметы: новый Uuid каждому, новые Uc1…4 там, где они не пусты
	SELECT CAST(Uuid AS VARCHAR(36)) AS OldUuid, NEWID() AS NewUuid,
	       Uc1 AS OldUc1, CASE WHEN Uc1 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc1,
	       Uc2 AS OldUc2, CASE WHEN Uc2 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc2,
	       Uc3 AS OldUc3, CASE WHEN Uc3 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc3,
	       Uc4 AS OldUc4, CASE WHEN Uc4 IS NULL THEN NULL ELSE CONVERT(VARCHAR(36), NEWID()) END AS NewUc4,
	       Code, Plate, Posx, Amount, Durability, Weight, Cell1, Cell2, Cell3, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3, Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate
	INTO #it FROM dbo.Item WHERE Userindex = @SrcU AND Charidx = @SrcC;
	INSERT INTO dbo.Item (Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2, Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3, Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate)
	SELECT @DstU, @DstC, NewUuid, Code, Plate, Posx, Amount, Durability, Weight, NewUc1, Cell1, NewUc2, Cell2, NewUc3, Cell3, NewUc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3, Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate
	FROM #it;
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
	IF EXISTS (SELECT 1 FROM dbo.CharFriend WHERE (Userindex = @DstU AND Charidx = @DstC) OR (FUserindex = @DstU AND FCharidx = @DstC)) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'CharFriend');
	IF EXISTS (SELECT 1 FROM dbo.ClanMember WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'ClanMember');
	IF EXISTS (SELECT 1 FROM dbo.Exitem WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'Exitem');
	IF EXISTS (SELECT 1 FROM dbo.ItemPostBox WHERE Userindex = @DstU AND Charidx = @DstC) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'ItemPostBox');
	IF EXISTS (SELECT 1 FROM dbo.SoulJewel WHERE (Userindex1 = @DstU AND Charidx1 = @DstC) OR (Userindex2 = @DstU AND Charidx2 = @DstC)) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'SoulJewel');
	IF EXISTS (SELECT 1 FROM dbo.SellitemAlarm WHERE (BUserindex = @DstU AND Bcharidx = @DstC) OR (SUserindex = @DstU AND Scharidx = @DstC)) SET @busy = CONCAT(@busy, CASE WHEN @busy = N'' THEN N'' ELSE N', ' END, N'SellitemAlarm');
	IF @busy <> N''
	BEGIN DECLARE @m NVARCHAR(400) = CONCAT(N'adm.CharCopyDelete: у копии появились связи (таблица ', @busy, N')'); THROW 50034, @m, 1; END;
	-- всё, что стирает UPDeleteChar у персонажа слота (таблицы копии + посещаемость, позиция в подземелье, «о себе», рейтинг славы)
	DELETE FROM dbo.Charinfo WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharPos WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharAppr WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharChat WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharConstellation WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharEpisode WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.EpisodeTime WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.VillagePos WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharQuest WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharSkill WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharSkillitem WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharSlot WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharStatus WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharSmStatus WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharFame WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharFameBank WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharFameProgress WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharFameHigh WHERE UserIndex = @DstU AND CharIdx = @DstC;
	DELETE FROM dbo.CharCamp WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharPlusPackage WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharFish WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharFishBookInfo WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CRT_CharCraftInfo WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CRT_LimitationQuest WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CRT_MainLimitationQuest WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharTutorial WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharRefine WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.SoulGuardian WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.ItemCoolTime WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.SkillCoolTime WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.SMSkillCoolTime WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.CharPetList WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.Item WHERE Userindex = @DstU AND Charidx = @DstC;
	DELETE FROM dbo.AttendanceCount WHERE Userindex = @DstU AND Charidx = @DstC;          -- как UPDeleteChar
	DELETE FROM dbo.AttendanceDetail WHERE Userindex = @DstU AND Charidx = @DstC;          -- как UPDeleteChar
	DELETE FROM dbo.CharinPos WHERE Userindex = @DstU AND Charidx = @DstC;          -- как UPDeleteChar
	DELETE FROM dbo.Charintroduce WHERE Userindex = @DstU AND Charidx = @DstC;          -- как UPDeleteChar
	DELETE FROM dbo.FamePointRank WHERE Userindex = @DstU AND Charidx = @DstC;          -- как UPDeleteChar
	-- ★ ревизия 26 С-2: вернуть строки удалённого персонажа, которые копия заменила
	INSERT INTO dbo.CharFameHigh (UserIndex, CharIdx, BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate) SELECT UserIndex, CharIdx, BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate FROM adm.CharCopyReplaced_CharFameHigh WHERE CopyId = @CopyId;
	INSERT INTO dbo.CharRefine (Userindex, Charidx, pLvl, pExp, aLvl, aExp, mLvl, mExp) SELECT Userindex, Charidx, pLvl, pExp, aLvl, aExp, mLvl, mExp FROM adm.CharCopyReplaced_CharRefine WHERE CopyId = @CopyId;
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
