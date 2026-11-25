-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_11_verify_ops.sql — проверка прав asda_ops (запуск ПОД asda_ops; deploy делает сам). 16.11.2026.
   Ожидание: UPDATE ровно тех столбцов Item, которые пишет панель (перенос: Plate/Posx/Owner/MaxupCnt; золото: Amount;
   свойства: WRITE из domains/itemedit.py), всё остальное — нет (перепроверка 3 М19: все столбцы WRITE проверяются). Столбцы: chk | v | want. */
SET NOCOUNT ON;
SELECT 'ops.Item SELECT'            AS chk, HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','SELECT') AS v, 1 AS want
UNION ALL SELECT 'ops.Item UPDATE Plate',   HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Plate','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Posx',    HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Posx','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Owner',   HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Owner','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE MaxupCnt',HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','MaxupCnt','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Code',    HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Code','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Amount',  HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Amount','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Upcount', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Upcount','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Cell1',   HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Cell1','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Uc1',     HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Uc1','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE AcuUpcnt', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','AcuUpcnt','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Updamage', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Updamage','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opvalue3', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opvalue3','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Uuid',    HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Uuid','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Charidx', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Charidx','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Userindex', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Userindex','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Durability', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Durability','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Weight', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Weight','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opidx1', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opidx1','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE OpValue1', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','OpValue1','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opidx2', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opidx2','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE OpValue2', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','OpValue2','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opidx4', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opidx4','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opvalue4', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opvalue4','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE OPidx5', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','OPidx5','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opvalue5', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opvalue5','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Cell2', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Cell2','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Cell3', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Cell3','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Cell4', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Cell4','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Uc2', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Uc2','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Uc3', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Uc3','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Uc4', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Uc4','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Fdate', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Fdate','COLUMN'), 1
UNION ALL SELECT 'ops.Item UPDATE Opidx3', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Opidx3','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Refine', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Refine','COLUMN'), 0), 0
UNION ALL SELECT 'ops.Item INSERT',         HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.Item DELETE',         HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.Charinfo SELECT',     HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE',     HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharPos UPDATE',      HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharPos UPDATE UserNum', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','UserNum','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE State', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','State','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Poridx', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Poridx','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Posx', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Posx','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Posy', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Posy','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Cporidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Cporidx','COLUMN'), 1
UNION ALL SELECT 'ops.VillagePos SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.VillagePos','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.VillagePos UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.VillagePos','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.Charinpos UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.Charinpos','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharPos UPDATE Gsidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Gsidx','COLUMN'), 0
UNION ALL SELECT 'ops.CharPos UPDATE LastDate', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','LastDate','COLUMN'), 0
UNION ALL SELECT 'ops.CharPos UPDATE SoulState', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','SoulState','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Charname', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Charname','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Charname', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Charname','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Lvl', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Lvl','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE SkillPoint', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','SkillPoint','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Strength', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Strength','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE FortuneP2', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','FortuneP2','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Agility', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Agility','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Health', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Health','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Spell', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Spell','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Mentality', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Mentality','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Fortune', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Fortune','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE StrengthP2', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','StrengthP2','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE AgilityP2', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','AgilityP2','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE HealthP2', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','HealthP2','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE SpellP2', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','SpellP2','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE MentalityP2', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','MentalityP2','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Hp', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Hp','COLUMN'), 0
UNION ALL SELECT 'ops.Charinfo UPDATE StrengthP', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','StrengthP','COLUMN'), 0
UNION ALL SELECT 'ops.Charinfo UPDATE MaxHp', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','MaxHp','COLUMN'), 0
UNION ALL SELECT 'ops.Charinfo UPDATE Job', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Job','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Subjob', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Subjob','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE JobCount', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','JobCount','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Class', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Class','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE Expe', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Expe','COLUMN'), 1
UNION ALL SELECT 'ops.CharFriend UPDATE Charname', HAS_PERMS_BY_NAME('Joy1.dbo.CharFriend','OBJECT','UPDATE','Charname','COLUMN'), 1
UNION ALL SELECT 'ops.CharFriend UPDATE Fuserindex', HAS_PERMS_BY_NAME('Joy1.dbo.CharFriend','OBJECT','UPDATE','Fuserindex','COLUMN'), 0
UNION ALL SELECT 'ops.CharFriend DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharFriend','OBJECT','DELETE'), 1   -- 18.11: друзья (friends.py)
UNION ALL SELECT 'ops.ClanMember SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.ClanMember UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.Exitem SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.Exitem','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Exitem UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.Exitem','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharGmInfo SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharGmInfo','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharGmInfo UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.CharGmInfo','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharGmInfo INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharGmInfo','OBJECT','INSERT'), 1   -- 19.11: GM-флаг (gmflag.py)
UNION ALL SELECT 'ops.CharGmInfo DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharGmInfo','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.Op.OPCharGMDelete EXEC', ISNULL(HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.OPCharGMDelete','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.Op.OPCharGMUpdate EXEC', ISNULL(HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.OPCharGMUpdate','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.A13_NameRuleConfig SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.A13_NameRuleConfig','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.A13_NameRuleConfig UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.A13_NameRuleConfig','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.A13_CurseWord SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.A13_CurseWord','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.LewdWordList SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.LewdWordList','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Del_Charinfo SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.Del_Charinfo','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Del_Charinfo UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.Del_Charinfo','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharFriend SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharFriend','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Partyidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Partyidx','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE Captain', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','Captain','COLUMN'), 1
UNION ALL SELECT 'ops.CharPos UPDATE LastDate', HAS_PERMS_BY_NAME('Joy1.dbo.CharPos','OBJECT','UPDATE','LastDate','COLUMN'), 0
UNION ALL SELECT 'ops.Op.Us_member UPDATE Flag', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','Flag','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE UserNum', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','UserNum','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE Loginidx', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','Loginidx','COLUMN'), 0
UNION ALL SELECT 'ops.CharSkill SELECT',    HAS_PERMS_BY_NAME('Joy1.dbo.CharSkill','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharSkill INSERT',    HAS_PERMS_BY_NAME('Joy1.dbo.CharSkill','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharSkill DELETE',    HAS_PERMS_BY_NAME('Joy1.dbo.CharSkill','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharSkill UPDATE',    HAS_PERMS_BY_NAME('Joy1.dbo.CharSkill','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharFame INSERT',     HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharFame SELECT',     HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharFame DELETE',     HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharFame UPDATE',     HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharFame UPDATE Condition1', HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','UPDATE','Condition1','COLUMN'), 1
UNION ALL SELECT 'ops.CharFame UPDATE Opidx1', HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','UPDATE','Opidx1','COLUMN'), 1   -- 18.11: звания (titles.py)
UNION ALL SELECT 'ops.CharFameBank INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharFameBank DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE Fmpoint', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE','Fmpoint','COLUMN'), 1
UNION ALL SELECT 'ops.CharEpisode SELECT',  HAS_PERMS_BY_NAME('Joy1.dbo.CharEpisode','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE Fame1', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE','Fame1','COLUMN'), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE Fame2', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE','Fame2','COLUMN'), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE Fmidx1', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE','Fmidx1','COLUMN'), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE Fame4', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE','Fame4','COLUMN'), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE Userindex', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE','Userindex','COLUMN'), 0
UNION ALL SELECT 'ops.CharFame UPDATE Opvalue62', HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','UPDATE','Opvalue62','COLUMN'), 1
UNION ALL SELECT 'ops.CharFame UPDATE Fameidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharFame','OBJECT','UPDATE','Fameidx','COLUMN'), 0
UNION ALL SELECT 'ops.CharFameProgress INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameProgress','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharFameProgress UPDATE Fame1', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameProgress','OBJECT','UPDATE','Fame1','COLUMN'), 1
UNION ALL SELECT 'ops.CharFameProgress UPDATE Userindex', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameProgress','OBJECT','UPDATE','Userindex','COLUMN'), 0
UNION ALL SELECT 'ops.CharFameHigh UPDATE BankHi1', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.CharFameHigh','OBJECT','UPDATE','BankHi1','COLUMN'), 0), 1
UNION ALL SELECT 'ops.CharFameHigh UPDATE UserIndex', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.CharFameHigh','OBJECT','UPDATE','UserIndex','COLUMN'), 0), 0
UNION ALL SELECT 'ops.FameRatingHolder SELECT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.FameRatingHolder','OBJECT','SELECT'), 0), 1
UNION ALL SELECT 'ops.FameRatingHolder UPDATE', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.FameRatingHolder','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.CharCamp UPDATE CampPoint', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','UPDATE','CampPoint','COLUMN'), 1
UNION ALL SELECT 'ops.CharCamp UPDATE CampFlag', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','UPDATE','CampFlag','COLUMN'), 0
UNION ALL SELECT 'ops.CharCamp UPDATE Campidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','UPDATE','Campidx','COLUMN'), 1   -- 18.11: армия учётки (charrest.py)
UNION ALL SELECT 'ops.CharCamp INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.Fighter SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.Fighter','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Mage DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.Mage','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.CharSkill UPDATE Lvl', HAS_PERMS_BY_NAME('Joy1.dbo.CharSkill','OBJECT','UPDATE','Lvl','COLUMN'), 0
UNION ALL SELECT 'ops.CharPetList INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharPetList DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharPetList UPDATE PetName', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','PetName','COLUMN'), 1
UNION ALL SELECT 'ops.CharPetList UPDATE NameFlag', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','NameFlag','COLUMN'), 1
UNION ALL SELECT 'ops.CharPetList UPDATE PetLvl', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','PetLvl','COLUMN'), 1
UNION ALL SELECT 'ops.CharPetList UPDATE PetExp', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','PetExp','COLUMN'), 1
UNION ALL SELECT 'ops.CharPetList SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Ranger SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.Ranger','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Mage SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.Mage','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharPetList UPDATE PetUnique', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','PetUnique','COLUMN'), 0
UNION ALL SELECT 'ops.CharPetList UPDATE Active', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','Active','COLUMN'), 0
UNION ALL SELECT 'ops.CharPetList UPDATE Edate', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','Edate','COLUMN'), 0
UNION ALL SELECT 'ops.CharPetList UPDATE PetMaxLvl', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','PetMaxLvl','COLUMN'), 0
UNION ALL SELECT 'ops.CharPetList UPDATE Petindex', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','Petindex','COLUMN'), 0
UNION ALL SELECT 'ops.CharEpisode INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharEpisode','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharEpisode DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharEpisode','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharEpisode UPDATE Stepidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharEpisode','OBJECT','UPDATE','Stepidx','COLUMN'), 0
UNION ALL SELECT 'ops.CharEpisode UPDATE Posx', HAS_PERMS_BY_NAME('Joy1.dbo.CharEpisode','OBJECT','UPDATE','Posx','COLUMN'), 0
UNION ALL SELECT 'ops.CharQuest SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharQuest','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharQuest INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharQuest','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharQuest DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharQuest','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.CharQuest UPDATE Quest1', HAS_PERMS_BY_NAME('Joy1.dbo.CharQuest','OBJECT','UPDATE','Quest1','COLUMN'), 1
UNION ALL SELECT 'ops.CharQuest UPDATE Quest20', HAS_PERMS_BY_NAME('Joy1.dbo.CharQuest','OBJECT','UPDATE','Quest20','COLUMN'), 1
UNION ALL SELECT 'ops.CharQuest UPDATE Userindex', HAS_PERMS_BY_NAME('Joy1.dbo.CharQuest','OBJECT','UPDATE','Userindex','COLUMN'), 0
UNION ALL SELECT 'ops.CRT_LimitationQuest SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_LimitationQuest','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CRT_LimitationQuest UPDATE Quest_Flag', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_LimitationQuest','OBJECT','UPDATE','Quest_Flag','COLUMN'), 1
UNION ALL SELECT 'ops.CRT_LimitationQuest UPDATE Quest_Count', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_LimitationQuest','OBJECT','UPDATE','Quest_Count','COLUMN'), 1
UNION ALL SELECT 'ops.CRT_LimitationQuest INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_LimitationQuest','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.CharPetList UPDATE FullNess', HAS_PERMS_BY_NAME('Joy1.dbo.CharPetList','OBJECT','UPDATE','FullNess','COLUMN'), 0
UNION ALL SELECT 'ops.Charinfo UPDATE PetCount', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','PetCount','COLUMN'), 0
UNION ALL SELECT 'ops.UPCharSkillinit EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPCharSkillinit','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPCharPetDel EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPCharPetDel','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.CharCamp DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharCamp SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharFameProgress SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameProgress','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharFameProgress DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameProgress','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharFameHigh SELECT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.CharFameHigh','OBJECT','SELECT'), 0), 1
UNION ALL SELECT 'ops.CharFameHigh DELETE', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.CharFameHigh','OBJECT','DELETE'), 0), 1
UNION ALL SELECT 'ops.CharFameBank UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.CharFameBank','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.FameRatingRevoke INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.FameRatingRevoke','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.FameRatingRevoke UPDATE', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.FameRatingRevoke','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.UPCharFameBitDis EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.UPCharFameBitDis','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.UPCharCampUpdate EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.UPCharCampUpdate','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.Charinfo INSERT',     HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.Charinfo DELETE',     HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','DELETE'), 0
/* 17.11: вставки/удаления в Joy1 нет нигде, кроме CharSkill, CharFame, CharFameBank */
UNION ALL SELECT 'ops.Joy1 other tables insert/delete', (SELECT COUNT(*) FROM Joy1.sys.objects t JOIN Joy1.sys.schemas sc ON sc.schema_id = t.schema_id WHERE t.type IN ('U', 'V') AND NOT (sc.name = 'dbo' AND t.name IN ('CharSkill','CharFame','CharFameBank','ItemPostBox','CharFameProgress','CharFameHigh','CharPetList','CharEpisode','CharQuest','SoulMate','CharFriend','ClanData','ClanMember','ClanNotice','CampClanData','CharPlusPackage','CharCamp','CharFish','CharFishBookInfo','CharTutorial','CharGmInfo')) AND (HAS_PERMS_BY_NAME('Joy1.' + QUOTENAME(sc.name) + '.' + QUOTENAME(t.name),'OBJECT','INSERT') = 1 OR HAS_PERMS_BY_NAME('Joy1.' + QUOTENAME(sc.name) + '.' + QUOTENAME(t.name),'OBJECT','DELETE') = 1)), 0
UNION ALL SELECT 'ops.UPItemMove EXEC',     HAS_PERMS_BY_NAME('Joy1.dbo.UPItemMove','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.adm.CharRestore EXEC', HAS_PERMS_BY_NAME('Joy1.adm.CharRestore','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.OpCharacterRestore EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.OpCharacterRestore','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPDeleteChar EXEC',   HAS_PERMS_BY_NAME('Joy1.dbo.UPDeleteChar','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.adm.CharRestored INSERT', HAS_PERMS_BY_NAME('Joy1.adm.CharRestored','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.adm.CharRestored SELECT', HAS_PERMS_BY_NAME('Joy1.adm.CharRestored','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Del_Item SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.Del_Item','OBJECT','SELECT'), 1
/* 18.11: выполнять можно только adm.CharRestore, adm.ItemGive / ItemTake / ItemUndo (выдача и изъятие предметов), adm.ItemRecover (19.11) и adm.CharCopy /
   CharCopyDelete / CampPointRank (копия персонажа, рейтинг чести); ★ 21.11 А5.3 — и adm.LoginMaintenanceSet, если SQL L09 применён */
UNION ALL SELECT 'ops.Joy1 executable objects', (SELECT COUNT(*) FROM Joy1.sys.objects o JOIN Joy1.sys.schemas sc ON sc.schema_id = o.schema_id WHERE o.type IN ('P', 'PC', 'FN', 'IF', 'TF', 'X') AND HAS_PERMS_BY_NAME('Joy1.' + QUOTENAME(sc.name) + '.' + QUOTENAME(o.name),'OBJECT','EXECUTE') = 1), 9 + CASE WHEN OBJECT_ID(N'Joy1.adm.LoginMaintenanceSet', N'P') IS NULL THEN 0 ELSE 1 END + CASE WHEN OBJECT_ID(N'Joy1.adm.AttendanceAdjust', N'P') IS NULL THEN 0 ELSE 1 END
UNION ALL SELECT 'ops.adm.LoginMaintenanceSet EXEC', CASE WHEN OBJECT_ID(N'Joy1.adm.LoginMaintenanceSet', N'P') IS NULL THEN 1 ELSE HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenanceSet','OBJECT','EXECUTE') END, 1
UNION ALL SELECT 'ops.adm.LoginMaintenance UPDATE', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenance','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.adm.LoginMaintenance INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenance','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.Joy1.UPUserLogin EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPUserLogin','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.adm.ItemGive EXEC',   HAS_PERMS_BY_NAME('Joy1.adm.ItemGive','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.adm.ItemTake EXEC',   HAS_PERMS_BY_NAME('Joy1.adm.ItemTake','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.adm.ItemUndo EXEC',   HAS_PERMS_BY_NAME('Joy1.adm.ItemUndo','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.adm.ItemRecover EXEC', HAS_PERMS_BY_NAME('Joy1.adm.ItemRecover','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.adm.ItemPlateCap EXEC', HAS_PERMS_BY_NAME('Joy1.adm.ItemPlateCap','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPRewardItem EXEC',   HAS_PERMS_BY_NAME('Joy1.dbo.UPRewardItem','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPGmItemAdd EXEC',    HAS_PERMS_BY_NAME('Joy1.dbo.UPGmItemAdd','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPItemDump EXEC',     HAS_PERMS_BY_NAME('Joy1.dbo.UPItemDump','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.Item INSERT',         HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.Item DELETE',         HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.Item UPDATE Rdate',   HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Rdate','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE GainDate', HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','GainDate','COLUMN'), 0
UNION ALL SELECT 'ops.Item UPDATE Refine',  HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','UPDATE','Refine','COLUMN'), 0
UNION ALL SELECT 'ops.Del_Item INSERT',     HAS_PERMS_BY_NAME('Joy1.dbo.Del_Item','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.Del_Item DELETE',     HAS_PERMS_BY_NAME('Joy1.dbo.Del_Item','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.Del_Item UPDATE',     HAS_PERMS_BY_NAME('Joy1.dbo.Del_Item','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.adm.ItemLedger SELECT', HAS_PERMS_BY_NAME('Joy1.adm.ItemLedger','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.adm.ItemLedger INSERT', HAS_PERMS_BY_NAME('Joy1.adm.ItemLedger','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.adm.ItemLedger UPDATE', HAS_PERMS_BY_NAME('Joy1.adm.ItemLedger','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.adm.ItemLedger DELETE', HAS_PERMS_BY_NAME('Joy1.adm.ItemLedger','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.adm.ItemTaken INSERT', HAS_PERMS_BY_NAME('Joy1.adm.ItemTaken','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.adm.ItemTaken DELETE', HAS_PERMS_BY_NAME('Joy1.adm.ItemTaken','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.ItemPostBox INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.ItemPostBox','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.ItemPostBox DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.ItemPostBox','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.ItemPostBox UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.ItemPostBox','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.UPCashitemBuy EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPCashitemBuy','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.AsdaChargeGroup SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.AsdaChargeGroup','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.AsdaChargeGroup UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.AsdaChargeGroup','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.log.AdminitemLog INSERT', HAS_PERMS_BY_NAME('JoyLog1.dbo.AdminitemLog','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.log.AdminitemLog SELECT', HAS_PERMS_BY_NAME('JoyLog1.dbo.AdminitemLog','OBJECT','SELECT'), 0
UNION ALL SELECT 'ops.log.AdminitemLog DELETE', HAS_PERMS_BY_NAME('JoyLog1.dbo.AdminitemLog','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.log.AdminitemLog UPDATE', HAS_PERMS_BY_NAME('JoyLog1.dbo.AdminitemLog','OBJECT','UPDATE'), 0
/* в JoyLog1 у asda_ops — запись ровно пяти таблиц (AdminitemLog; 18.11 — журналы соулмейта и клана) и ни одного исполняемого объекта */
UNION ALL SELECT 'ops.log other tables write', (SELECT COUNT(*) FROM JoyLog1.sys.tables t WHERE t.name NOT IN ('AdminitemLog','SoulMate','SoulMateLevelUp','SoulMateinfo','ClanLog') AND (HAS_PERMS_BY_NAME('JoyLog1.dbo.' + QUOTENAME(t.name),'OBJECT','INSERT') = 1 OR HAS_PERMS_BY_NAME('JoyLog1.dbo.' + QUOTENAME(t.name),'OBJECT','DELETE') = 1 OR HAS_PERMS_BY_NAME('JoyLog1.dbo.' + QUOTENAME(t.name),'OBJECT','UPDATE') = 1)), 0
/* ★ А6.7 (22.11, adminc_21_san.sql): журнал дел san.* — исполнять в JoyLog1 можно ровно две процедуры san.UP_SAN_*, запись — только san.* по списку */
/* ★ А6.12 (22.11, adminc_24_chat.sql): + две процедуры заглушек чата chat.UP_ChatMuteSet / UP_ChatMuteLift, если схема chat (P129) уже есть */
UNION ALL SELECT 'ops.log executable objects', (SELECT COUNT(*) FROM JoyLog1.sys.objects o JOIN JoyLog1.sys.schemas sc ON sc.schema_id = o.schema_id WHERE o.type IN ('P', 'PC', 'FN', 'IF', 'TF', 'X') AND HAS_PERMS_BY_NAME('JoyLog1.' + QUOTENAME(sc.name) + '.' + QUOTENAME(o.name),'OBJECT','EXECUTE') = 1), 2 + CASE WHEN EXISTS (SELECT 1 FROM JoyLog1.sys.schemas WHERE name = N'chat') THEN 2 ELSE 0 END
UNION ALL SELECT 'ops.log executable outside san', (SELECT COUNT(*) FROM JoyLog1.sys.objects o JOIN JoyLog1.sys.schemas sc ON sc.schema_id = o.schema_id WHERE sc.name NOT IN ('san', 'chat') AND o.type IN ('P', 'PC', 'FN', 'IF', 'TF', 'X') AND HAS_PERMS_BY_NAME('JoyLog1.' + QUOTENAME(sc.name) + '.' + QUOTENAME(o.name),'OBJECT','EXECUTE') = 1), 0
UNION ALL SELECT 'ops.chat (P129): schema ' + CASE WHEN EXISTS (SELECT 1 FROM JoyLog1.sys.schemas WHERE name = N'chat') THEN 'present' ELSE 'absent - chat checks skipped' END, 0, 0
UNION ALL SELECT 'ops.chat.UP_ChatMuteSet EXEC', CASE WHEN NOT EXISTS (SELECT 1 FROM JoyLog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.UP_ChatMuteSet','OBJECT','EXECUTE'), -1) END, 1
UNION ALL SELECT 'ops.chat.UP_ChatMuteLift EXEC', CASE WHEN NOT EXISTS (SELECT 1 FROM JoyLog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.UP_ChatMuteLift','OBJECT','EXECUTE'), -1) END, 1
UNION ALL SELECT 'ops.chat.mute SELECT', CASE WHEN NOT EXISTS (SELECT 1 FROM JoyLog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.mute','OBJECT','SELECT'), -1) END, 1
UNION ALL SELECT 'ops.chat.UP_ChatMuteActive EXEC', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.UP_ChatMuteActive','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.chat.UP_ChatJournalPurge EXEC', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.UP_ChatJournalPurge','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.chat.mute INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.mute','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.chat.mute UPDATE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.mute','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.chat.mute DELETE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.mute','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'ops.chat.message SELECT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.message','OBJECT','SELECT'), 0), 0
UNION ALL SELECT 'ops.chat.message INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.message','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.chat.message DELETE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.message','OBJECT','DELETE'), 0), 0
-- ★ ревизия 71 М-3: представления chat (владелец dbo) — чтения нет: цепочка владения дала бы chat.message мимо DENY
UNION ALL SELECT 'ops.chat.v_recent SELECT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.v_recent','OBJECT','SELECT'), 0), 0
UNION ALL SELECT 'ops.chat.v_mute_active SELECT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.chat.v_mute_active','OBJECT','SELECT'), 0), 0
UNION ALL SELECT 'ops.san.UP_SAN_CaseOpen EXEC', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.UP_SAN_CaseOpen','OBJECT','EXECUTE'), 0), 1
UNION ALL SELECT 'ops.san.UP_SAN_SetStatus EXEC', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.UP_SAN_SetStatus','OBJECT','EXECUTE'), 0), 1
UNION ALL SELECT 'ops.ac.UP_AC_JournalPurge EXEC', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.ac.UP_AC_JournalPurge','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.san.cases SELECT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','SELECT'), 0), 1
UNION ALL SELECT 'ops.san.cases INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.san.cases DELETE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'ops.san.cases UPDATE status', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','UPDATE','status','COLUMN'), 0), 0
UNION ALL SELECT 'ops.san.cases UPDATE user_index', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','UPDATE','user_index','COLUMN'), 0), 0
UNION ALL SELECT 'ops.san.cases UPDATE decided_by', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','UPDATE','decided_by','COLUMN'), 0), 1
UNION ALL SELECT 'ops.san.cases UPDATE outcome', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.cases','OBJECT','UPDATE','outcome','COLUMN'), 0), 1
UNION ALL SELECT 'ops.san.case_log INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_log','OBJECT','INSERT'), 0), 1
UNION ALL SELECT 'ops.san.case_log UPDATE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_log','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.san.case_log DELETE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_log','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'ops.san.case_event INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_event','OBJECT','INSERT'), 0), 1
UNION ALL SELECT 'ops.san.case_event UPDATE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_event','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.san.evidence INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.evidence','OBJECT','INSERT'), 0), 1
UNION ALL SELECT 'ops.san.evidence UPDATE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.evidence','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.san.evidence DELETE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.evidence','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'ops.san.case_block INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_block','OBJECT','INSERT'), 0), 1
UNION ALL SELECT 'ops.san.case_block DELETE', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_block','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'ops.san.case_block UPDATE lifted_by', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_block','OBJECT','UPDATE','lifted_by','COLUMN'), 0), 1
UNION ALL SELECT 'ops.san.case_block UPDATE reason', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.san.case_block','OBJECT','UPDATE','reason','COLUMN'), 0), 0
UNION ALL SELECT 'ops.log.ac.other INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.ac.other','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.log.ac.other SELECT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.ac.other','OBJECT','SELECT'), 0), 0
UNION ALL SELECT 'ops.san other tables write', (SELECT COUNT(*) FROM JoyLog1.sys.tables t JOIN JoyLog1.sys.schemas sc ON sc.schema_id = t.schema_id WHERE sc.name = 'san' AND t.name NOT IN ('cases','case_log','case_event','evidence','case_block') AND (HAS_PERMS_BY_NAME('JoyLog1.san.' + QUOTENAME(t.name),'OBJECT','INSERT') = 1 OR HAS_PERMS_BY_NAME('JoyLog1.san.' + QUOTENAME(t.name),'OBJECT','DELETE') = 1 OR HAS_PERMS_BY_NAME('JoyLog1.san.' + QUOTENAME(t.name),'OBJECT','UPDATE') = 1)), 0
UNION ALL SELECT 'ops.log.ItemEvent INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.dbo.ItemEvent','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.Op.CharacterStat INSERT', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.CharacterStat','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.Op.Us_member SELECT', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.Op.Us_member UPDATE us_block', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','us_block','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE Us_id', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','Us_id','COLUMN'), 0
UNION ALL SELECT 'ops.Op.Us_member UPDATE us_pwhash', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','us_pwhash','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE us_pwsalt', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','us_pwsalt','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE us_pwfail', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','us_pwfail','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE us_pwset', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','us_pwset','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE us_pwfail_at', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','us_pwfail_at','COLUMN'), 1
UNION ALL SELECT 'ops.Op.Us_member UPDATE Realcash', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE','Realcash','COLUMN'), 0
UNION ALL SELECT 'ops.Op.Us_member DELETE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.Op.Us_member INSERT', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.Op.adm_NewAccount INSERT', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.adm_NewAccount','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.Op.adm_NewAccount UPDATE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.adm_NewAccount','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.Op.adm_NewAccount DELETE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.adm_NewAccount','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.Op.adm_NewAccount SELECT Us_id', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.adm_NewAccount','OBJECT','SELECT','Us_id','COLUMN'), 0
UNION ALL SELECT 'ops.Op.BlockList INSERT', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.BlockList','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.Op.BlockList DELETE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.BlockList','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.Op.BlockList UPDATE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.BlockList','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.Op.BlockHistory INSERT', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.BlockHistory','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.Op.BlockHistory DELETE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.BlockHistory','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.Op.BlockHistory UPDATE', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.BlockHistory','OBJECT','UPDATE'), 0
/* перепроверка 6 М1: записи нет больше ни на одну таблицу AsdaStoryOp (видны только таблицы, на которые есть права) */
UNION ALL SELECT 'ops.Op.other tables write', (SELECT COUNT(*) FROM AsdaStoryOp.sys.tables t WHERE t.name NOT IN ('BlockList','BlockHistory') AND ((t.name <> 'CharacterStat' AND HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.' + QUOTENAME(t.name),'OBJECT','INSERT') = 1) OR HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.' + QUOTENAME(t.name),'OBJECT','DELETE') = 1 OR HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.' + QUOTENAME(t.name),'OBJECT','UPDATE') = 1)), 0
UNION ALL SELECT 'ops.Op.OPBlockDel EXEC', ISNULL(HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.OPBlockDel','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.Op.Startinfo UPDATE', ISNULL(HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Startinfo','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.Op.sp_creatediagram EXEC', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.sp_creatediagram','OBJECT','EXECUTE'), 0
/* 19.11: служебная учётка — исполнять в AsdaStoryOp можно ровно одну процедуру adm.ServiceAccountCreate (adminc_09) */
UNION ALL SELECT 'ops.Op.adm.ServiceAccountCreate EXEC', HAS_PERMS_BY_NAME('AsdaStoryOp.adm.ServiceAccountCreate','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.Op executable objects', (SELECT COUNT(*) FROM AsdaStoryOp.sys.objects o JOIN AsdaStoryOp.sys.schemas sc ON sc.schema_id = o.schema_id WHERE o.type IN ('P', 'PC', 'FN', 'IF', 'TF', 'X') AND HAS_PERMS_BY_NAME('AsdaStoryOp.' + QUOTENAME(sc.name) + '.' + QUOTENAME(o.name),'OBJECT','EXECUTE') = 1), 1
UNION ALL SELECT 'ops.Op.UP_AC_SetPassword EXEC', ISNULL(HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.UP_AC_SetPassword','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.Op.Us_member ALTER', HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','ALTER'), 0
/* ревизия 28 К-3: в AsdaStoryOp у asda_ops нет ALTER на базу и прав менять состав/права базы */
UNION ALL SELECT 'ops.Op DATABASE ALTER', HAS_PERMS_BY_NAME('AsdaStoryOp','DATABASE','ALTER'), 0
UNION ALL SELECT 'ops.Op ALTER ANY USER', HAS_PERMS_BY_NAME('AsdaStoryOp','DATABASE','ALTER ANY USER'), 0
UNION ALL SELECT 'ops.Op ALTER ANY ROLE', HAS_PERMS_BY_NAME('AsdaStoryOp','DATABASE','ALTER ANY ROLE'), 0
UNION ALL SELECT 'ops.Op ALTER ANY CERTIFICATE', HAS_PERMS_BY_NAME('AsdaStoryOp','DATABASE','ALTER ANY CERTIFICATE'), 0
UNION ALL SELECT 'ops.Op CREATE SCHEMA', HAS_PERMS_BY_NAME('AsdaStoryOp','DATABASE','CREATE SCHEMA'), 0
UNION ALL SELECT 'ops.Op CONTROL', HAS_PERMS_BY_NAME('AsdaStoryOp','DATABASE','CONTROL'), 0
UNION ALL SELECT 'ops.Op.adm.ServiceAccountCreate ALTER', HAS_PERMS_BY_NAME('AsdaStoryOp.adm.ServiceAccountCreate','OBJECT','ALTER'), 0
UNION ALL SELECT 'ops.log.LogInfo SELECT',  ISNULL(HAS_PERMS_BY_NAME('joylog1.dbo.LogInfo','OBJECT','SELECT'), 0), 0
UNION ALL SELECT 'ops.AsdaAdmin.audit SELECT', ISNULL(HAS_PERMS_BY_NAME('AsdaAdmin.adm.audit','OBJECT','SELECT'), 0), 0
/* 18.11, А1 «соулмейт, друзья, клан»: ровно то, что пишут операции панели (domains/soulmate.py, friends.py, clan.py) */
UNION ALL SELECT 'ops.SoulMate SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.SoulMate INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.SoulMate DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE State', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','State','COLUMN'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE SmLvl', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','SmLvl','COLUMN'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE SmExp', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','SmExp','COLUMN'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE FriendShip', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','FriendShip','COLUMN'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE FinalDate', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','FinalDate','COLUMN'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE Regdate', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','Regdate','COLUMN'), 1
UNION ALL SELECT 'ops.SoulMate UPDATE Smidx', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','Smidx','COLUMN'), 0
UNION ALL SELECT 'ops.SoulMate UPDATE Userindex', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','Userindex','COLUMN'), 0
UNION ALL SELECT 'ops.SoulMate UPDATE Ouserindex', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','Ouserindex','COLUMN'), 0
UNION ALL SELECT 'ops.SoulMate UPDATE info', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMate','OBJECT','UPDATE','info','COLUMN'), 0
UNION ALL SELECT 'ops.SoulMateIdx SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMateIdx','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.SoulMateIdx DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.SoulMateIdx','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.SoulMateNote DELETE', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.SoulMateNote','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'ops.CharOption SELECT SmEnroll', HAS_PERMS_BY_NAME('Joy1.dbo.CharOption','OBJECT','SELECT','SmEnroll','COLUMN'), 1
UNION ALL SELECT 'ops.CharOption UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.CharOption','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.Charinfo UPDATE Share', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','Share','COLUMN'), 1
UNION ALL SELECT 'ops.Charinfo UPDATE DonationPoint', HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE','DonationPoint','COLUMN'), 0
UNION ALL SELECT 'ops.CharFriend INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharFriend','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.ClanData SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.ClanData INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.ClanData DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.ClanData UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.ClanData UPDATE JoinCnt', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','JoinCnt','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE Captain', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','Captain','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE Capuserindex', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','Capuserindex','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE CapCharidx', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','CapCharidx','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE MarkFlag', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','MarkFlag','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE Markidx', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','Markidx','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE MarkBgColor', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','MarkBgColor','COLUMN'), 1
UNION ALL SELECT 'ops.ClanData UPDATE Cname', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','Cname','COLUMN'), 0
UNION ALL SELECT 'ops.ClanData UPDATE Maxcnt', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','Maxcnt','COLUMN'), 0
UNION ALL SELECT 'ops.ClanData UPDATE TotActPoint', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','TotActPoint','COLUMN'), 0
UNION ALL SELECT 'ops.ClanData UPDATE Notice', HAS_PERMS_BY_NAME('Joy1.dbo.ClanData','OBJECT','UPDATE','Notice','COLUMN'), 0
UNION ALL SELECT 'ops.ClanMember INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.ClanMember DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.ClanMember UPDATE Grade', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','UPDATE','Grade','COLUMN'), 1
UNION ALL SELECT 'ops.ClanMember UPDATE Charname', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','UPDATE','Charname','COLUMN'), 0
UNION ALL SELECT 'ops.ClanMember UPDATE DonationPoint', HAS_PERMS_BY_NAME('Joy1.dbo.ClanMember','OBJECT','UPDATE','DonationPoint','COLUMN'), 0
UNION ALL SELECT 'ops.ClanNotice INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.ClanNotice','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.ClanNotice DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.ClanNotice','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.ClanNotice UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.ClanNotice','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CampClanData INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CampClanData','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CampClanData DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CampClanData','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CampClanData UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.CampClanData','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CampOwnerData UPDATE MvpClanIndex', HAS_PERMS_BY_NAME('Joy1.dbo.CampOwnerData','OBJECT','UPDATE','MvpClanIndex','COLUMN'), 1
UNION ALL SELECT 'ops.CampOwnerData UPDATE OwnerCampIndex', HAS_PERMS_BY_NAME('Joy1.dbo.CampOwnerData','OBJECT','UPDATE','OwnerCampIndex','COLUMN'), 0
UNION ALL SELECT 'ops.CampOwnerData INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CampOwnerData','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.UPSoulMateBreak EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPSoulMateBreak','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPClanBreakUp EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPClanBreakUp','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.log.SoulMate INSERT', HAS_PERMS_BY_NAME('JoyLog1.dbo.SoulMate','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.log.SoulMate SELECT', HAS_PERMS_BY_NAME('JoyLog1.dbo.SoulMate','OBJECT','SELECT'), 0
UNION ALL SELECT 'ops.log.SoulMateLevelUp INSERT', HAS_PERMS_BY_NAME('JoyLog1.dbo.SoulMateLevelUp','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.log.SoulMateinfo INSERT', HAS_PERMS_BY_NAME('JoyLog1.dbo.SoulMateinfo','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.log.ClanLog INSERT', HAS_PERMS_BY_NAME('JoyLog1.dbo.ClanLog','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.log.ClanLog DELETE', HAS_PERMS_BY_NAME('JoyLog1.dbo.ClanLog','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.log.ClanEvent INSERT', ISNULL(HAS_PERMS_BY_NAME('JoyLog1.dbo.ClanEvent','OBJECT','INSERT'), 0), 0
/* 18.11, А1 «внешность, баффы, лагерь, ремесло, обучение, копия» (domains/charrest.py, charcopy.py): ровно то, что пишут операции */
UNION ALL SELECT 'ops.CharAppr SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CharAppr UPDATE HairStyle', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','UPDATE','HairStyle','COLUMN'), 1
UNION ALL SELECT 'ops.CharAppr UPDATE HairColor', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','UPDATE','HairColor','COLUMN'), 1
UNION ALL SELECT 'ops.CharAppr UPDATE FaceType', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','UPDATE','FaceType','COLUMN'), 1
UNION ALL SELECT 'ops.CharAppr UPDATE Charidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','UPDATE','Charidx','COLUMN'), 0
UNION ALL SELECT 'ops.CharAppr INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.CharAppr DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharAppr','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.CharPlusPackage INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharPlusPackage','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharPlusPackage DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharPlusPackage','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharPlusPackage UPDATE iType', HAS_PERMS_BY_NAME('Joy1.dbo.CharPlusPackage','OBJECT','UPDATE','iType','COLUMN'), 1
UNION ALL SELECT 'ops.CharPlusPackage UPDATE EndTime', HAS_PERMS_BY_NAME('Joy1.dbo.CharPlusPackage','OBJECT','UPDATE','EndTime','COLUMN'), 1
UNION ALL SELECT 'ops.CharPlusPackage UPDATE Userindex', HAS_PERMS_BY_NAME('Joy1.dbo.CharPlusPackage','OBJECT','UPDATE','Userindex','COLUMN'), 0
UNION ALL SELECT 'ops.CharCamp UPDATE CampPenaltyTime', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','UPDATE','CampPenaltyTime','COLUMN'), 1
UNION ALL SELECT 'ops.CharCamp UPDATE CampGrade', HAS_PERMS_BY_NAME('Joy1.dbo.CharCamp','OBJECT','UPDATE','CampGrade','COLUMN'), 0
UNION ALL SELECT 'ops.CampData UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.CampData','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CampPointRank SELECT', HAS_PERMS_BY_NAME('Joy1.dbo.CampPointRank','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.CampPointRank DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CampPointRank','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.UP_CampPointRank EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UP_CampPointRank','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UP_CampDataReset EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UP_CampDataReset','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.adm.CampPointRank EXEC', HAS_PERMS_BY_NAME('Joy1.adm.CampPointRank','OBJECT','EXECUTE'), 1
-- ★ 21.11 А5.4: сброс ежедневных — только обёртка adm.LimitationReset; сток и таблицы заданий напрямую — нет
UNION ALL SELECT 'ops.adm.LimitationReset EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.LimitationReset','OBJECT','EXECUTE'), 0), 1
UNION ALL SELECT 'ops.CRT_AsdaLimitationDailyReset EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.CRT_AsdaLimitationDailyReset','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'ops.CRT_LimitationQuest UPDATE Quest_Type', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.CRT_LimitationQuest','OBJECT','UPDATE','Quest_Type','COLUMN'), 0), 0
UNION ALL SELECT 'ops.AsdaLimitationResetLog INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaLimitationResetLog','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.CRT_CharCraftInfo UPDATE iLevel', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_CharCraftInfo','OBJECT','UPDATE','iLevel','COLUMN'), 1
UNION ALL SELECT 'ops.CRT_CharCraftInfo UPDATE iExp', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_CharCraftInfo','OBJECT','UPDATE','iExp','COLUMN'), 1
UNION ALL SELECT 'ops.CRT_CharCraftInfo UPDATE iBit1', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_CharCraftInfo','OBJECT','UPDATE','iBit1','COLUMN'), 0
UNION ALL SELECT 'ops.CRT_CharCraftInfo UPDATE CashCount', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_CharCraftInfo','OBJECT','UPDATE','CashCount','COLUMN'), 0
UNION ALL SELECT 'ops.CRT_CharCraftInfo INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CRT_CharCraftInfo','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.CharFish UPDATE FishingSkill', HAS_PERMS_BY_NAME('Joy1.dbo.CharFish','OBJECT','UPDATE','FishingSkill','COLUMN'), 1
UNION ALL SELECT 'ops.CharFish INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharFish','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.CharFishBookInfo DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.CharFishBookInfo','OBJECT','DELETE'), 1
UNION ALL SELECT 'ops.CharFishBookInfo UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.CharFishBookInfo','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.CharTutorial UPDATE Tutorial1', HAS_PERMS_BY_NAME('Joy1.dbo.CharTutorial','OBJECT','UPDATE','Tutorial1','COLUMN'), 1
UNION ALL SELECT 'ops.CharTutorial UPDATE Tutorial4', HAS_PERMS_BY_NAME('Joy1.dbo.CharTutorial','OBJECT','UPDATE','Tutorial4','COLUMN'), 1
UNION ALL SELECT 'ops.CharTutorial UPDATE Charidx', HAS_PERMS_BY_NAME('Joy1.dbo.CharTutorial','OBJECT','UPDATE','Charidx','COLUMN'), 0
UNION ALL SELECT 'ops.CharTutorial INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.CharTutorial','OBJECT','INSERT'), 1
UNION ALL SELECT 'ops.AttendanceDetail DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.AttendanceDetail','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.AttendanceCount UPDATE', HAS_PERMS_BY_NAME('Joy1.dbo.AttendanceCount','OBJECT','UPDATE'), 0
-- ★ 23.11 А6.10 (adminc_25_attendance.sql): посещаемость — только процедура adm.AttendanceAdjust; прямой записи в Attendance* и журнал нет
UNION ALL SELECT 'ops.adm.AttendanceAdjust EXEC', CASE WHEN OBJECT_ID(N'Joy1.adm.AttendanceAdjust', N'P') IS NULL THEN 1 ELSE HAS_PERMS_BY_NAME('Joy1.adm.AttendanceAdjust','OBJECT','EXECUTE') END, 1
UNION ALL SELECT 'ops.AttendanceDetail INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.AttendanceDetail','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.AttendanceCount INSERT', HAS_PERMS_BY_NAME('Joy1.dbo.AttendanceCount','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.OP_Attendance_Insert EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.OP_Attendance_Insert','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.adm.AttendanceAdjustLog INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.AttendanceAdjustLog','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.adm.AttendanceAdjustLog UPDATE', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.AttendanceAdjustLog','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'ops.UPHairChange EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPHairChange','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPPlusPackageitemUse EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPPlusPackageitemUse','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.UPCharCampSelect EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPCharCampSelect','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.adm.CharCopy EXEC', HAS_PERMS_BY_NAME('Joy1.adm.CharCopy','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.adm.CharCopyDelete EXEC', HAS_PERMS_BY_NAME('Joy1.adm.CharCopyDelete','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.adm.CharCopied SELECT', HAS_PERMS_BY_NAME('Joy1.adm.CharCopied','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.adm.CharCopied INSERT', HAS_PERMS_BY_NAME('Joy1.adm.CharCopied','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.adm.CharCopied UPDATE', HAS_PERMS_BY_NAME('Joy1.adm.CharCopied','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.adm.CharCopyItemMap SELECT', HAS_PERMS_BY_NAME('Joy1.adm.CharCopyItemMap','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.adm.CharCopyItemMap DELETE', HAS_PERMS_BY_NAME('Joy1.adm.CharCopyItemMap','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.adm.CharCopyReplaced_CharRefine SELECT', HAS_PERMS_BY_NAME('Joy1.adm.CharCopyReplaced_CharRefine','OBJECT','SELECT'), 1
UNION ALL SELECT 'ops.adm.CharCopyReplaced_CharRefine INSERT', HAS_PERMS_BY_NAME('Joy1.adm.CharCopyReplaced_CharRefine','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.adm.CharCopyReplaced_CharFameHigh DELETE', HAS_PERMS_BY_NAME('Joy1.adm.CharCopyReplaced_CharFameHigh','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.SoulJewel DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.SoulJewel','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.FamePointRank DELETE', HAS_PERMS_BY_NAME('Joy1.dbo.FamePointRank','OBJECT','DELETE'), 0
UNION ALL SELECT 'ops.AsdaFamePoints SELECT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaFamePoints','OBJECT','SELECT'), 0), 1
UNION ALL SELECT 'ops.AsdaFamePoints UPDATE Point', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaFamePoints','OBJECT','UPDATE','Point','COLUMN'), 0), 1
UNION ALL SELECT 'ops.AsdaFamePoints UPDATE FameIdx', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaFamePoints','OBJECT','UPDATE','FameIdx','COLUMN'), 0), 0
UNION ALL SELECT 'ops.AsdaFamePoints INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaFamePoints','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.AsdaFamePoints DELETE', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaFamePoints','OBJECT','DELETE'), 0), 0
-- ★ 20.11 А4.7: AsdaSkillBase (ac0x) — SELECT и UPDATE требования и полей уровня 0; маска, ключ, вставка, удаление — нет
UNION ALL SELECT 'ops.AsdaSkillBase SELECT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','SELECT'), 0), 1
UNION ALL SELECT 'ops.AsdaSkillBase UPDATE Need', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','UPDATE','Need','COLUMN'), 0), 1
UNION ALL SELECT 'ops.AsdaSkillBase UPDATE Cooltime', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','UPDATE','Cooltime','COLUMN'), 0), 1
UNION ALL SELECT 'ops.AsdaSkillBase UPDATE SubTime3', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','UPDATE','SubTime3','COLUMN'), 0), 1
UNION ALL SELECT 'ops.AsdaSkillBase UPDATE Mask', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','UPDATE','Mask','COLUMN'), 0), 0
UNION ALL SELECT 'ops.AsdaSkillBase UPDATE Skillidx', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','UPDATE','Skillidx','COLUMN'), 0), 0
UNION ALL SELECT 'ops.AsdaSkillBase INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'ops.AsdaSkillBase DELETE', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaSkillBase','OBJECT','DELETE'), 0), 0
-- ★ 22.11 А6.9: AsdaStoryLogin — только процедура корректировки баланса gp7; процедуры шлюза, прямая запись баланса и журнала, password — нет
UNION ALL SELECT 'ops.gp7.adm.GP7Adjust EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7Adjust','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'ops.gp7.GP7_Purchase EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_Purchase','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.gp7.GP7_GetBalance EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_GetBalance','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.gp7.GP7_GiftSettle EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_GiftSettle','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.gp7.GP7_GiftHold EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_GiftHold','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.gp7.GP7_GiftLookup EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7_GiftLookup','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'ops.gp7.GP7Balance UPDATE', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7Balance','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.gp7.GP7Balance INSERT', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7Balance','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.gp7.GP7PurchaseLog INSERT', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7PurchaseLog','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.gp7.user.password', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.[user]','OBJECT','SELECT','password','COLUMN'), 0
UNION ALL SELECT 'ops.gp7.adm.GP7AdjustLog INSERT', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLog','OBJECT','INSERT'), 0
UNION ALL SELECT 'ops.gp7.adm.GP7AdjustLog UPDATE', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLog','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.gp7.adm.GP7AdjustLock UPDATE', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLock','OBJECT','UPDATE'), 0
UNION ALL SELECT 'ops.gp7 ALTER ANY SCHEMA', HAS_PERMS_BY_NAME('AsdaStoryLogin','DATABASE','ALTER ANY SCHEMA'), 0
UNION ALL SELECT 'ops.sysadmin',            IS_SRVROLEMEMBER('sysadmin'), 0;
