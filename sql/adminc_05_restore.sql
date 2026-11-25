-- Copyright (c) 2026 @sitxovski (Discord)
-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_05_restore.sql — восстановление удалённого персонажа для админ-центра (волна А1, 18.11.2026; решение владельца:
-- «своя процедура adm»). Разбор: Reports/admin_center/research_char_restore.md.
-- СОБРАН ПРОГРАММОЙ из текста Joy1.dbo.OpCharacterRestore (выгрузка 18.11.2026, MD5 выгрузки 7d985e3d4f1e3747003d35835b0c7a7d): вставки штатной
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
	IF EXISTS (SELECT 1 FROM dbo.CharAppr WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharAppr';
	IF EXISTS (SELECT 1 FROM dbo.CharChat WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharChat';
	IF EXISTS (SELECT 1 FROM dbo.CharConstellation WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharConstellation';
	IF EXISTS (SELECT 1 FROM dbo.charepisode WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'charepisode';
	IF EXISTS (SELECT 1 FROM dbo.CharFame WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharFame';
	IF EXISTS (SELECT 1 FROM dbo.CharFameBank WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharFameBank';
	IF EXISTS (SELECT 1 FROM dbo.CharFameProgress WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharFameProgress';
	IF EXISTS (SELECT 1 FROM dbo.CharFish WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharFish';
	IF EXISTS (SELECT 1 FROM dbo.CharFishBookInfo WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharFishBookInfo';
	IF EXISTS (SELECT 1 FROM dbo.CharInfo WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharInfo';
	IF EXISTS (SELECT 1 FROM dbo.CharPetList WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharPetList';
	IF EXISTS (SELECT 1 FROM dbo.CharPos WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharPos';
	IF EXISTS (SELECT 1 FROM dbo.Charquest WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'Charquest';
	IF EXISTS (SELECT 1 FROM dbo.CharSkill WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharSkill';
	IF EXISTS (SELECT 1 FROM dbo.CharSlot WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharSlot';
	IF EXISTS (SELECT 1 FROM dbo.CharTutorial WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharTutorial';
	IF EXISTS (SELECT 1 FROM dbo.CRT_CharCraftinfo WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CRT_CharCraftinfo';
	IF EXISTS (SELECT 1 FROM dbo.CRT_LimitationQuest WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CRT_LimitationQuest';
	IF EXISTS (SELECT 1 FROM dbo.CRT_MainLimitationQuest WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CRT_MainLimitationQuest';
	IF EXISTS (SELECT 1 FROM dbo.Item WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'Item';
	IF EXISTS (SELECT 1 FROM dbo.VillagePos WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'VillagePos';
	IF EXISTS (SELECT 1 FROM dbo.CharStatus WHERE Userindex = @Userindex AND Charidx = @NewCharidx) SET @busy = N'CharStatus';
	IF @busy IS NOT NULL
	BEGIN DECLARE @m NVARCHAR(200) = CONCAT(N'adm.CharRestore: слот ', @NewCharidx, N' занят (таблица ', @busy, N')'); THROW 50006, @m, 1; END;
	IF EXISTS (SELECT 1 FROM dbo.Del_Item d JOIN dbo.Item i ON i.Uuid = d.Uuid
	           WHERE d.Userindex = @Userindex AND d.Charidx = @Charidx AND d.Edate = @Edate)
	THROW 50007, N'adm.CharRestore: предметы набора уже есть в игре (тот же Uuid)', 1;
	-- ▼ вставки штатной Joy1.dbo.OpCharacterRestore (без изменений)
	;
	INSERT INTO dbo.CharAppr
	SELECT @Userindex,@newCharidx,HairStyle,HairColor,FaceType
	FROM dbo.Del_CharAppr
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharChat
	SELECT @Userindex,@newCharidx,npc1, npc2, npc3, npc4, npc5, npc6, npc7, npc8, npc9, npc10, npc11, npc12, npc13, npc14, npc15, npc16, npc17, npc18, npc19, npc20,
				npc21, npc22, npc23, npc24, npc25, npc26, npc27, npc28, npc29, npc30, npc31, npc32, npc33, npc34, npc35, npc36, npc37, npc38, npc39, npc40,
				npc41, npc42, npc43, npc44, npc45, npc46, npc47, npc48, npc49, npc50, npc51, npc52, npc53, npc54, npc55, npc56, npc57, npc58, npc59, npc60,
				npc61, npc62, npc63, npc64, npc65, npc66, npc67, npc68, npc69, npc70, npc71, npc72, npc73, npc74, npc75, npc76, npc77, npc78, npc79, npc80,
				npc81, npc82, npc83, npc84, npc85, npc86, npc87, npc88, npc89, npc90, 	npc91, npc92, npc93, npc94, npc95, npc96, npc97, npc98, npc99, npc100,
				npc101, npc102, npc103, npc104, npc105, npc106, npc107, npc108, npc109, npc110,	npc111, npc112, npc113, npc114, npc115, npc116, npc117, npc118, npc119, npc120,
				npc121, npc122, npc123, npc124, npc125, npc126, npc127, npc128, npc129, npc130,	npc131, npc132, npc133, npc134, npc135, npc136, npc137, npc138, npc139, npc140,
				npc141, npc142, npc143, npc144, npc145, npc146, npc147, npc148, npc149, npc150,	npc151, npc152, npc153, npc154, npc155, npc156, npc157, npc158, npc159, npc160,
				npc161, npc162, npc163, npc164, npc165, npc166, npc167, npc168, npc169, npc170,	npc171, npc172, npc173, npc174, npc175, npc176, npc177, npc178, npc179, npc180,
				npc181, npc182, npc183, npc184, npc185, npc186, npc187, npc188, npc189, npc190,	npc191, npc192, npc193, npc194, npc195, npc196, npc197, npc198, npc199, npc200
	FROM dbo.del_CharChat
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharConstellation
	VALUES(@Userindex,@NewCharidx,1)
	INSERT INTO dbo.charepisode
	SELECT @Userindex,@newCharidx,Code,Posx,State,Episodeidx,Stepidx,Etime,Eitem1,Amount1,Eitem2,Amount2,Eitem3,Amount3,Eitem4,Amount4,Eitem5,Amount5
	FROM dbo.Del_charepisode
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharFame
	SELECT @Userindex,@newCharidx,Fameidx, Condition1, condition2,Opidx1,Opvalue11,Opvalue12,OPidx2, OPvalue21, OPvalue22,OPidx3, OPvalue31,OPvalue32,OPidx4,OPvalue41,OPvalue42,OPidx5,OPvalue51,OPvalue52,OPidx6,OPvalue61,OPvalue62
	FROM dbo.Del_CharFame
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharFameBank
	SELECT @Userindex,@newCharidx,Fmpoint,Fmidx1,Fmidx2, Fame1, FAme2, Fame3,FAme4
	FROM dbo.del_charfamebank
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharFameProgress
	SELECT @Userindex,@newCharidx,FAme1, FAme2, Fame3, FAme4
	FROM dbo.del_CharfameProgress
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharFish
	SELECT @Userindex,@newCharidx,FishingSkill
	FROM dbo.del_CharFish
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharFishBookInfo
	SELECT @Userindex,@newCharidx,BookCode,Complete,BookType,
			FishItemCode0,FishItemCode1,FishItemCode2,FishItemCode3,FishItemCode4,FishItemCode5,FishItemCode6,FishItemCode7,FishItemCode8,
			FishItemCode9,FishItemCode10,FishItemCode11,FishItemCode12,FishItemCode13,FishItemCode14,FishItemCode15,FishItemCode16,FishItemCode17,
			FishItemCode18,FishItemCode19,FishItemCode20,FishItemCode21,FishItemCode22,FishItemCode23,FishItemCode24,FishItemCode25,
			FishItemCode26,FishItemCode27,FishItemCode28,FishItemCode29,FishCount0,FishCount1,FishCount2,FishCount3,FishCount4,FishCount5,FishCount6,FishCount7,FishCount8,FishCount9,FishCount10,
			FishCount11,FishCount12,FishCount13,FishCount14,FishCount15,FishCount16,FishCount17,FishCount18,FishCount19,FishCount20,
			FishCount21,FishCount22,FishCount23,FishCount24,FishCount25,FishCount26,FishCount27,FishCount28,FishCount29,FishMaxSize0,FishMaxSize1,
			FishMaxSize2,FishMaxSize3,FishMaxSize4,FishMaxSize5,FishMaxSize6,FishMaxSize7,FishMaxSize8,FishMaxSize9,
			FishMaxSize10,FishMaxSize11,FishMaxSize12,FishMaxSize13,FishMaxSize14,FishMaxSize15,FishMaxSize16,FishMaxSize17,FishMaxSize18,
			FishMaxSize19,FishMaxSize20,FishMaxSize21,FishMaxSize22,FishMaxSize23,FishMaxSize24,FishMaxSize25,FishMaxSize26,FishMaxSize27,
			FishMaxSize28,FishMaxSize29,FishMinSize0,FishMinSize1,FishMinSize2,FishMinSize3,FishMinSize4,FishMinSize5,FishMinSize6,FishMinSize7,FishMinSize8,FishMinSize9,
			FishMinSize10,FishMinSize11,FishMinSize12,FishMinSize13,FishMinSize14,FishMinSize15,FishMinSize16,FishMinSize17,FishMinSize18,
			FishMinSize19,FishMinSize20,FishMinSize21,FishMinSize22,FishMinSize23,FishMinSize24,FishMinSize25,FishMinSize26,FishMinSize27,
			FishMinSize28,FishMinSize29
	From del_CharFishBookInfo
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharInfo
	SELECT @Userindex,@newCharidx,uid,charname,gender,lvl,expe,jobcount,class,job,subjob,skillpoint,maxweight,weight,Maxhp, Maxmp, Hp, Mp, actpoint,donationpoint,
	strength,agility,health,spell,mentality,fortune,strengthp,agilityp,healthp,spellp,mentalityp,fortunep,
	strengthp2,agilityp2,healthp2,spellp2,mentalityp2,fortunep2,
	MinAttack, MaxAttack, MinMagicAtt, MaxMagicAtt, MagicDefense, MinDefense1, MaxDefense1,
	MinDefense2, MaxDefense2, Getitem, BlockMin, BlockMax, BlockDamage,Critical, Evasion,PcriRate,McriRate,
		Fire,Water,Earth,Climate,Light,Dark,FireR,WaterR,EarthR,ClimateR,LightR,DarkR,warecount,cwarecount,petcount,share
	FROM dbo.Del_CharInfo
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharPetList(Userindex,charidx,plate,petindex,petname,fullness,petlvl,PetMaxLvl,petexp,nameflag,active,edate)
	SELECT @Userindex,@newCharidx,plate,petindex,petname,fullness,petlvl,PetMaxLvl,petexp,nameflag,active,cdate
	FROM dbo.Del_CharPetList
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharPos
	SELECT @Userindex,@newCharidx,uid,charname,-1,poridx,posx,posy,gsidx,threadidx,channel,cporidx,partyidx,captain,state,soulstate,pstate,lastdate
	FROM dbo.Del_CharPos
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.Charquest
	SELECT @Userindex,@newCharidx, Quest1, Quest2, Quest3, Quest4, Quest5, Quest6, Quest7, Quest8, Quest9, Quest10,
		Quest11, Quest12, Quest13, Quest14, Quest15, Quest16, Quest17, Quest18, Quest19, Quest20
	FROM dbo.Del_CharQuest
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharSkill
	SELECT @Userindex,@newCharidx,Skillidx,Lvl,cooltime,distance,scope,mpvalue,evalue,skillper,subskillper,subvalue1,subtime1,subvalue2,subtime2,subvalue3,subtime3
	FROM dbo.Del_CharSkill
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharSlot
	SELECT @Userindex,@newCharidx,slotidx,type,plate,posx,amount,eindex
	FROM dbo.Del_CharSlot
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharTutorial
	SELECT @Userindex,@newCharidx,Tutorial1,Tutorial2,Tutorial3,Tutorial4
	FROM dbo.Del_CharTutorial
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CRT_CharCraftinfo
	SELECT @Userindex,@newCharidx,CashCount,iLevel,iExp,iBit1,iBit2,iBit3,iBit4,iBit5,iBit6,iBit7,iBit8,iBit9
	FROM dbo.Del_CRT_CharCraftinfo
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CRT_LimitationQuest
	SELECT @Userindex,@newCharidx,Quest_index,Quest_Type,Quest_Count,Quest_flag
	FROM dbo.Del_CRT_LimitationQuest
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CRT_MainLimitationQuest
	SELECT @Userindex,@newCharidx,OldDay
	FROM dbo.Del_CRT_MainLimitationQuest
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.Item
	SELECT @Userindex,@newCharidx,Uuid, code,plate,posx,amount,durability,weight,uc1,cell1,uc2,cell2,uc3,cell3,uc4,cell4,upcount,acuupcnt,maxupcnt,updamage,opidx1,opvalue1,opidx2,opvalue2,opidx3,opvalue3,opidx4,opvalue4,opidx5,opvalue5,refine,owner,gaindate,fdate,rdate
	FROM dbo.Del_Item
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.VillagePos
	SELECT @Userindex,@newCharidx,Villageidx,Posx,Posy,ipaddress,port
	FROM dbo.Del_VillagePos
	WHERE userindex=@Userindex AND Charidx=@Charidx AND Edate=@Edate
	INSERT INTO dbo.CharStatus VALUES (@Userindex, @newCharidx,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,
	-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,
	-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,
	-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,
	-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,
	-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1,-1,-1,0,0,0,-1,0,-1)
		IF NOT EXISTS ( SELECT Userindex FROM dbo.CharOption WHERE Userindex=@Userindex )
		BEGIN
			INSERT INTO dbo.CharOption ( Userindex, NormalChat,SmChat,FriendChat,PartyChat,GuildChat,Whisper,Acv,SmEnroll,FriendEnroll,PartyEnroll,GuildEnroll,Change,SChange,Monster,Charname, Hat, SoulAttack,ClanAttack,UserAttack)
			VALUES ( @Userindex, 1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1 )
		END
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
