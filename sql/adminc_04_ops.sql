-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_04_ops.sql — админ-центр, волна А1 (начало): логин asda_ops для ПРАВОК ПРЕДМЕТОВ персонажа не в игре. 16.11.2026.

   ЗАЧЕМ. Владелец 16.11: «нужна возможность двигать предметы и надевать/снимать снаряжение». Панельный логин asda_admin
   остаётся строго «только чтение» (DENY на уровне игровых баз); для записи — ОТДЕЛЬНЫЙ логин с минимальными правами,
   которым служба пользуется только внутри операций core/ops (журнал adm.audit, предпросмотр, откат).

   ПРАВА asda_ops (ничего сверх перечисленного; db_datareader НЕ даётся):
     Joy1         SELECT dbo.Item, dbo.Charinfo, dbo.CharPos, dbo.AsdaMigrationLog (если есть);
                  UPDATE только столбцов Plate, Posx, Owner, MaxupCnt таблицы dbo.Item (перестановка/надевание = смена
                  места; Owner и MaxupCnt сервер правит при надевании сам — GameServer.c:82469-82478, повторяем 1:1);
                  + Amount, Durability, Weight, Upcount, Opidx/OpValue 1, 2, 4, 5, Cell1…4 (золото и свойства экземпляра,
                  16.11 вечер) + AcuUpcnt, Uc1…4, Fdate (ступень вместе со счётчиками заточки, самоцвет с Uuid и временем —
                  перепроверка А1) + Updamage («+N%» заточки, 16.11 ночь); Code, Userindex, Charidx, Uuid, пара 3 и прочее — НЕТ;
                  на уровне базы DENY INSERT, DELETE, EXECUTE, ALTER, CREATE * (EXECUTE через public — ревизия А0 №6).
     AsdaStoryOp  SELECT dbo.Us_member (проверка «учётка не в игре» внутри транзакции записи); блок учётки (16.11 ночь):
                  UPDATE (us_block; Flag, UserNum; us_pw* — пароль 17.11), INSERT через представление adm_NewAccount (создание учётки 17.11), SELECT/INSERT/DELETE BlockList, SELECT/INSERT BlockHistory; запись больше ни на что;
                  DENY ALTER/REFERENCES/CREATE * на уровне базы, EXECUTE — на схему dbo; EXECUTE только adm.ServiceAccountCreate
                  (служебная учётка ≤ 5000, 19.11). Joy1 CharGmInfo — SELECT, INSERT, DELETE (GM-флаг, 19.11).
   Пароль — переменной окружения OpsPw (из secrets\asda_admin.ini, ключ OPS_PASSWORD), в файлах его нет.
   Запуск — deploy/deploy_admin_center.py (sqlcmd -S lpc:.\SQLEXPRESS -E). Проверка — adminc_11_verify_ops.sql под asda_ops.
   Откат: DROP USER asda_ops в Joy1 и AsdaStoryOp, DROP LOGIN asda_ops (adminc_99_rollback.sql).
*/
SET NOCOUNT ON;
USE [master];
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'asda_ops')
    CREATE LOGIN [asda_ops] WITH PASSWORD = N'$(OpsPw)', DEFAULT_DATABASE = [Joy1], CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    ALTER LOGIN [asda_ops] WITH PASSWORD = N'$(OpsPw)', CHECK_POLICY = ON;
ALTER LOGIN [asda_ops] ENABLE;
GO

USE [Joy1];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') CREATE USER [asda_ops] FOR LOGIN [asda_ops];
GRANT SELECT ON dbo.Item     TO [asda_ops];
GRANT SELECT ON dbo.Charinfo TO [asda_ops];
GRANT SELECT ON dbo.CharPos  TO [asda_ops];
IF OBJECT_ID(N'dbo.AsdaMigrationLog', N'U') IS NOT NULL GRANT SELECT ON dbo.AsdaMigrationLog TO [asda_ops];
GRANT UPDATE (Plate, Posx, Owner, MaxupCnt) ON dbo.Item TO [asda_ops];
/* 16.11.2026 вечер: правка золота и свойств экземпляра (domains/itemedit.py) — ровно столбцы, которые правит панель */
GRANT UPDATE (Amount, Durability, Weight, Upcount, Opidx1, OpValue1, Opidx2, OpValue2, Opidx4, Opvalue4, OPidx5, Opvalue5,
              Cell1, Cell2, Cell3, Cell4) ON dbo.Item TO [asda_ops];
/* перепроверка А1: ступень — вместе со счётчиком попыток (AcuUpcnt); самоцвет — с Uuid экземпляра (Uc1…4) и временем Fdate,
   как пишет UPCellobMove */
GRANT UPDATE (AcuUpcnt, Uc1, Uc2, Uc3, Uc4, Fdate) ON dbo.Item TO [asda_ops];
/* 16.11 ночь: «+N%» заточки (Updamage, +27) правится вместе со ступенью — это и есть сила предмета у клиента (атака/защита =
   Updamage × множитель + основа); владелец: «сменилось только качество, +n% нет». */
GRANT UPDATE (Updamage) ON dbo.Item TO [asda_ops];
/* 17.11, А1 «смена профессии» (domains/jobchange.py): навыки профессии и звание — вставкой строк CharSkill / CharFame / CharFameBank.
   Запрет INSERT/DELETE на уровне базы снят (он перекрыл бы выдачу на таблицы); роль public в Joy1 записи не имеет (проверено 17.11
   sys.database_permissions), у asda_ops ролей нет — вставка/удаление возможны ТОЛЬКО в трёх таблицах ниже (проверка adminc_11). */
REVOKE INSERT, DELETE FROM [asda_ops];
/* 18.11, А1 «восстановление персонажа» (решение владельца): EXECUTE запрещён на схему dbo, а не на всю базу (запрет на базу
   перекрыл бы выдачу на объект); выполнять можно ТОЛЬКО adm.CharRestore (sql/adminc_05_restore.sql; проверка adminc_11). */
REVOKE EXECUTE FROM [asda_ops];
DENY ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_ops];
DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];
GRANT EXECUTE ON adm.CharRestore TO [asda_ops];
/* 18.11, А1 «выдать / изъять предмет» (domains/itemgive.py, sql/adminc_06_items.sql; решение владельца — своя процедура adm):
   INSERT/DELETE на dbo.Item НЕ даются — вставка и удаление идут внутри процедур по цепочке владения dbo; журнал процедур
   adm.ItemLedger / снимки adm.ItemTaken панель только читает (предпросмотр отката). */
GRANT EXECUTE ON adm.ItemGive TO [asda_ops];
GRANT EXECUTE ON adm.ItemTake TO [asda_ops];
GRANT EXECUTE ON adm.ItemUndo TO [asda_ops];
GRANT EXECUTE ON adm.ItemRecover TO [asda_ops];   -- 19.11: вернуть удалённое по журналам (тот же Uuid, защита от дюпа — в процедуре)
GRANT SELECT ON adm.ItemLedger TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.ItemLedger TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.ItemTaken TO [asda_ops];
IF OBJECT_ID(N'dbo.AsdaChargeGroup', N'U') IS NOT NULL GRANT SELECT ON dbo.AsdaChargeGroup TO [asda_ops];   -- правило P100 (заряды)
/* 18.11, А1 «подарок / премиум-почта» (domains/gifts.py): строки элитного почтового ящика — как кладёт покупка UPCashitemBuy;
   DELETE — только откат неотзабранного (панель удаляет ровно свои строки, получатели не в игре). */
GRANT SELECT, INSERT, DELETE ON dbo.ItemPostBox TO [asda_ops];
/* 18.11, А1 «звания, слава, очки чести» (domains/titles.py, research_titles_honor.md §4.5): как AddFameBit / SubFameBit сервера —
   любой бит маски, надетые слоты, опции записи звания, маска «найдено», старшая половина P22; очки чести CharCamp.CampPoint.
   EXECUTE процедур званий и запись в таблицы рейтинга — нет. */
GRANT UPDATE (Fame2, Fame3, Fame4, Fmidx1, Fmidx2) ON dbo.CharFameBank TO [asda_ops];
GRANT UPDATE (Opidx1, Opvalue11, Opvalue12, Opidx2, Opvalue21, Opvalue22, Opidx3, Opvalue31, Opvalue32,
              Opidx4, Opvalue41, Opvalue42, Opidx5, Opvalue51, Opvalue52, Opidx6, Opvalue61, Opvalue62) ON dbo.CharFame TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharFameProgress TO [asda_ops];
GRANT UPDATE (Fame1, Fame2, Fame3, Fame4) ON dbo.CharFameProgress TO [asda_ops];
IF OBJECT_ID(N'dbo.CharFameHigh', N'U') IS NOT NULL GRANT SELECT, INSERT, DELETE ON dbo.CharFameHigh TO [asda_ops];
IF OBJECT_ID(N'dbo.CharFameHigh', N'U') IS NOT NULL
    GRANT UPDATE (BankHi1, BankHi2, BankHi3, BankHi4, ProgHi1, ProgHi2, ProgHi3, ProgHi4, UpdateDate) ON dbo.CharFameHigh TO [asda_ops];
IF OBJECT_ID(N'dbo.FameRatingHolder', N'U') IS NOT NULL GRANT SELECT ON dbo.FameRatingHolder TO [asda_ops];
GRANT SELECT ON dbo.CharCamp TO [asda_ops];
GRANT UPDATE (CampPoint) ON dbo.CharCamp TO [asda_ops];
/* 18.11, А1 «навыки и питомцы» (domains/skills.py, pets.py; research_skills_pets.md E): навыки пишутся вставкой/удалением строк
   (уже есть SELECT/INSERT/DELETE CharSkill), шаблоны полного сброса — чтение; питомцы — как UPPetRename / UPCharPetDel. */
GRANT SELECT ON dbo.Fighter TO [asda_ops];
GRANT SELECT ON dbo.Ranger TO [asda_ops];
GRANT SELECT ON dbo.Mage TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharPetList TO [asda_ops];
GRANT UPDATE (PetName, NameFlag, PetLvl, PetExp) ON dbo.CharPetList TO [asda_ops];
/* 18.11, А1 «задания и эпизоды» (domains/quests.py): выдача / снятие / завершение (как UPEpisodeRewardGain, UPEpisodeDump,
   UPEpisodeDestory + UPQuestUP), доска — только Quest_Flag (как CRT_UPLimitationDel). Награда — уже выданными правами
   (Charinfo опыт/уровень, Item Amount/Fdate золота, EXEC adm.ItemGive). SELECT CharEpisode выдан выше. */
GRANT INSERT, DELETE ON dbo.CharEpisode TO [asda_ops];
GRANT SELECT, INSERT ON dbo.CharQuest TO [asda_ops];
GRANT UPDATE (Quest1, Quest2, Quest3, Quest4, Quest5, Quest6, Quest7, Quest8, Quest9, Quest10,
              Quest11, Quest12, Quest13, Quest14, Quest15, Quest16, Quest17, Quest18, Quest19, Quest20) ON dbo.CharQuest TO [asda_ops];
GRANT SELECT ON dbo.CRT_LimitationQuest TO [asda_ops];
GRANT UPDATE (Quest_Flag) ON dbo.CRT_LimitationQuest TO [asda_ops];
GRANT SELECT ON dbo.Del_Charinfo TO [asda_ops];            -- набор корзины (проверки в транзакции восстановления)
GRANT SELECT ON dbo.Del_Item TO [asda_ops];
GRANT SELECT ON adm.CharRestored TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharSkill TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharFame TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharFameBank TO [asda_ops];
GRANT SELECT ON dbo.CharEpisode TO [asda_ops];             -- взятые эпизоды (предупреждение о квесте смены профессии)
GRANT UPDATE (Fame1, Fmpoint) ON dbo.CharFameBank TO [asda_ops];
GRANT UPDATE (Condition1, Condition2) ON dbo.CharFame TO [asda_ops];      -- строка звания уже есть: как UPCharFameUp (перепроверка 12 М7)
/* 20.11, А4.6 «Звания» (domains/cs_kinds/titledata.py after_server): после выкладки / отката FameInfo.txt — привести очки званий в
   dbo.AsdaFamePoints (ac0w: по ней UPCharFameBitDis вычитает славу) к живому файлу. Только UPDATE столбца Point; ключ, вставка и
   удаление — нет (таблицу целиком пересобирает ac0w_01_migrate.sql). Таблицы нет (ac0w не применён) — права не выдаются. */
IF OBJECT_ID(N'dbo.AsdaFamePoints', N'U') IS NOT NULL
BEGIN
    GRANT SELECT ON dbo.AsdaFamePoints TO [asda_ops];
    GRANT UPDATE (Point) ON dbo.AsdaFamePoints TO [asda_ops];
END
/* 20.11, А4.7 «Навыки и классы» (domains/cs_kinds/skilldata.py after_server): после выкладки / отката SkillInfo.sif — привести
   dbo.AsdaSkillBase (ac0x: по ней UPCharSkillinit сохраняет навыки при полном сбросе) к живому файлу. Только UPDATE требования дерева и
   13 полей уровня 0; ключ, маска, вставка и удаление — нет (таблицу целиком пересобирает ac0x_01_migrate.sql). Таблицы нет — права не выдаются. */
IF OBJECT_ID(N'dbo.AsdaSkillBase', N'U') IS NOT NULL
BEGIN
    GRANT SELECT ON dbo.AsdaSkillBase TO [asda_ops];
    GRANT UPDATE (Need, Cooltime, Distance, Scope, Mpvalue, Evalue, SkillPer, SubSkillPer, SubValue1, SubTime1, SubValue2, SubTime2,
                  SubValue3, SubTime3) ON dbo.AsdaSkillBase TO [asda_ops];
END
/* 17.11, А1 «смена имени» (domains/rename.py): запрет UPDATE на всю Charinfo снят (на объект он перекрыл бы выдачу на столбец);
   пишется ТОЛЬКО Charname (как UPCharRename) — в Charinfo, CharPos и CharFriend (имя друга вместо удаления дружбы). Чтение —
   таблиц, которые проверяет UPCharRename и сторож A13. */
REVOKE UPDATE ON dbo.Charinfo FROM [asda_ops];
GRANT UPDATE (Charname) ON dbo.Charinfo TO [asda_ops];
GRANT UPDATE (Class, JobCount, Job, Subjob) ON dbo.Charinfo TO [asda_ops];      -- смена профессии (17.11); ПОСЛЕ REVOKE UPDATE ON Charinfo
/* 17.11, А1 «поднять уровень» (domains/progress.py, research_level_job.md): как повышение у сервера — уровень, опыт, очки навыков,
   база характеристик и её копия P2; HP, MP, атаки, защиты и поля P сервер пересчитывает при входе — их НЕ пишем. */
GRANT UPDATE (Lvl, Expe, SkillPoint, Strength, Agility, Health, Spell, Mentality, Fortune,
              StrengthP2, AgilityP2, HealthP2, SpellP2, MentalityP2, FortuneP2) ON dbo.Charinfo TO [asda_ops];
GRANT UPDATE (Charname) ON dbo.CharFriend TO [asda_ops];
GRANT SELECT ON dbo.CharFriend TO [asda_ops];
GRANT SELECT ON dbo.ClanMember TO [asda_ops];
GRANT SELECT ON dbo.Exitem TO [asda_ops];
GRANT SELECT ON dbo.CharGmInfo TO [asda_ops];
/* 19.11, А1 «Учётки» — GM-флаг (domains/gmflag.py; решение владельца 19.11 п.4: выдать/снять только служебным ≤ 5000, право owner).
   Как OPCharGMUpdate сервера: режим 0 — INSERT (UserIndex, Charidx, GMFlag 1), иначе DELETE строк учётки; стоковую OPCharGMDelete
   (стёрла бы ВСЕ строки старше 31 дня — обоих живых операторов) панель не зовёт, EXECUTE на dbo запрещён. INSERT/DELETE по столбцам
   в SQL Server не сужаются; UPDATE не даётся (проверка adminc_11). */
GRANT INSERT, DELETE ON dbo.CharGmInfo TO [asda_ops];
GRANT SELECT ON dbo.A13_NameRuleConfig TO [asda_ops];
GRANT SELECT ON dbo.A13_CurseWord TO [asda_ops];
GRANT SELECT ON dbo.LewdWordList TO [asda_ops];
GRANT SELECT ON dbo.Del_Charinfo TO [asda_ops];          -- занятость имени и удалёнными (перепроверка 10)
/* 17.11, А1 «снять залипший „в игре“» (domains/online.py): запрет UPDATE на всю CharPos снят (на объект он перекрыл бы выдачу
   на столбцы); пишутся ТОЛЬКО поля штатного сброса UP_AsdaCharPosReset / выхода UPLogOutCharacter. */
REVOKE UPDATE ON dbo.CharPos FROM [asda_ops];
GRANT UPDATE (UserNum, Partyidx, Captain, SoulState, State, Charname) ON dbo.CharPos TO [asda_ops];   -- Charname — смена имени (17.11); ПОСЛЕ REVOKE (он снимает и выдачи на столбцы)
GRANT UPDATE (Poridx, Cporidx, Posx, Posy) ON dbo.CharPos TO [asda_ops];   -- 18.11: перенос персонажа (domains/charmove.py)
GRANT SELECT ON dbo.VillagePos TO [asda_ops];                                -- точка возрождения (режим «своя точка возрождения»)
/* 18.11, А1 «соулмейт, друзья, клан» (domains/soulmate.py, friends.py, clan.py; research_soulmate_friends.md, research_clan.md):
   ровно то, что пишут UPSoulMateBreak / UPSoulMateOk / UPSmLevelUp / UPSmFriendShipUp, UPFriendAdd / UPFriendDelete, UPClanSecede /
   UPClanWaitCancel / UPClanOwnerTransfer / UPClanBreakUp (+ объявления и MVP — решение владельца) / UPClanNoticeUp / UPClanNoticeDel,
   и вставки отката (строки возвращаются по снимку журнала панели). EXECUTE процедур dbo — нет (запрещён на схему). */
GRANT SELECT, INSERT, DELETE ON dbo.SoulMate TO [asda_ops];
GRANT UPDATE (State, SmLvl, SmExp, FriendShip, FinalDate, Regdate) ON dbo.SoulMate TO [asda_ops];
GRANT SELECT ON dbo.SoulMateIdx TO [asda_ops];                               -- пул номеров пары (UPSoulMateOk)
GRANT SELECT (Userindex, SmEnroll) ON dbo.CharOption TO [asda_ops];         -- предупреждение «предложения соулмейта отключены»
GRANT UPDATE (Share) ON dbo.Charinfo TO [asda_ops];                          -- разрыв: Share = 0 (ПОСЛЕ REVOKE UPDATE ON Charinfo выше)
GRANT INSERT, DELETE ON dbo.CharFriend TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.ClanData TO [asda_ops];
GRANT UPDATE (JoinCnt, Captain, Capuserindex, CapCharidx, MarkFlag, Markidx, MarkColor, MarkBorder, MarkBdColor, MarkBgColor) ON dbo.ClanData TO [asda_ops];
GRANT INSERT, DELETE ON dbo.ClanMember TO [asda_ops];
GRANT UPDATE (Grade) ON dbo.ClanMember TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.ClanNotice TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CampClanData TO [asda_ops];
GRANT SELECT ON dbo.CampOwnerData TO [asda_ops];
GRANT UPDATE (MvpClanIndex) ON dbo.CampOwnerData TO [asda_ops];
/* 18.11, А1 «внешность, баффы, лагерь, ремесло, обучение» (domains/charrest.py, research_a1_char_rest.md): ровно столбцы, которые пишут
   UPHairChange (+ лицо — решение владельца), UPPlusPackageitemUse / UPCharPackageBuff, UPCharCampPenaltyUpdate / UPCharCampSelect /
   UPCharCampReset (армия учётки; CampData — нет), CRT_UPCraftEnter (уровень, опыт), суточный сброс заданий ремесла, UPCharFishIngProgress,
   UPCharFishBookDelete, UPCharTutorialUpdate; вставка/удаление — только там, где сервер вставляет строку, и для отката. EXECUTE — нет. */
GRANT SELECT ON dbo.CharAppr TO [asda_ops];
GRANT UPDATE (HairStyle, HairColor, FaceType) ON dbo.CharAppr TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharPlusPackage TO [asda_ops];
GRANT UPDATE (iType, StartTime, BuffPeriod, EndTime) ON dbo.CharPlusPackage TO [asda_ops];
GRANT INSERT, DELETE ON dbo.CharCamp TO [asda_ops];
GRANT UPDATE (CampPenaltyTime, Campidx) ON dbo.CharCamp TO [asda_ops];
GRANT SELECT ON dbo.CampPointRank TO [asda_ops];                             -- предпросмотр пересчёта рейтинга (запись — adm.CampPointRank)
GRANT SELECT ON dbo.CRT_CharCraftInfo TO [asda_ops];
GRANT UPDATE (iLevel, iExp) ON dbo.CRT_CharCraftInfo TO [asda_ops];
GRANT UPDATE (Quest_Count) ON dbo.CRT_LimitationQuest TO [asda_ops];          -- суточный сброс одному персонажу (Quest_Flag выдан выше)
GRANT SELECT, INSERT, DELETE ON dbo.CharFish TO [asda_ops];
GRANT UPDATE (FishingSkill) ON dbo.CharFish TO [asda_ops];
GRANT SELECT, INSERT, DELETE ON dbo.CharFishBookInfo TO [asda_ops];          -- удаление книги; вставка — только откат удаления
GRANT SELECT, INSERT, DELETE ON dbo.CharTutorial TO [asda_ops];
GRANT UPDATE (Tutorial1, Tutorial2, Tutorial3, Tutorial4) ON dbo.CharTutorial TO [asda_ops];
/* 18.11, А1 «копия персонажа» и «пересчёт рейтинга чести» (sql/adminc_08_charcopy.sql; решение владельца — свои процедуры adm):
   вставки копии и её удаление — внутри процедур по цепочке владения dbo; отметки копий и карту Uuid панель только читает. */
GRANT EXECUTE ON adm.CharCopy TO [asda_ops];
GRANT EXECUTE ON adm.CharCopyDelete TO [asda_ops];
GRANT EXECUTE ON adm.CampPointRank TO [asda_ops];
/* 21.11, А5.4 «сброс ежедневных заданий доски» (sql/adminc_15_events.sql): только процедура adm.LimitationReset (догнать суточный
   сброс = вызов dbo.CRT_AsdaLimitationDailyReset, внеочередной — то же тело под тем же замком); таблицы заданий напрямую — нельзя. */
IF OBJECT_ID(N'adm.LimitationReset', N'P') IS NOT NULL GRANT EXECUTE ON adm.LimitationReset TO [asda_ops];
/* 21.11, А5.3 «режим обслуживания» (domains/maint.py; SQL L09 AstoryServer/Docs/SQL/l09_01_migrate.sql — применяется ОТДЕЛЬНО, по слову
   владельца): режим меняется ТОЛЬКО процедурой adm.LoginMaintenanceSet; таблицу напрямую — нельзя. L09 не применён — выдачи нет. */
IF OBJECT_ID(N'adm.LoginMaintenanceSet', N'P') IS NOT NULL GRANT EXECUTE ON adm.LoginMaintenanceSet TO [asda_ops];
IF OBJECT_ID(N'adm.LoginMaintenance', N'U') IS NOT NULL DENY INSERT, UPDATE, DELETE ON adm.LoginMaintenance TO [asda_ops];
GRANT SELECT ON adm.CharCopied TO [asda_ops];
GRANT SELECT ON adm.CharCopyItemMap TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.CharCopied TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.CharCopyItemMap TO [asda_ops];
/* ★ ревизия 26 С-2: снимки строк удалённого персонажа, которые копия заменила (пишут и возвращают только процедуры) */
GRANT SELECT ON adm.CharCopyReplaced_CharRefine TO [asda_ops];
GRANT SELECT ON adm.CharCopyReplaced_CharFameHigh TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.CharCopyReplaced_CharRefine TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.CharCopyReplaced_CharFameHigh TO [asda_ops];
GO

/* 18.11, А1 «выдать / изъять предмет» (решение владельца: писать и в стоковый журнал JoyLog1.dbo.AdminitemLog). Межбазовые
   цепочки владения выключены (is_db_chaining_on = 0 у всех баз), поэтому процедуре Joy1 нужно право ВЫЗЫВАЮЩЕГО в JoyLog1:
   свой пользователь asda_ops — только INSERT этой одной таблицы, больше ничего (проверка adminc_11). */
USE [JoyLog1];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') CREATE USER [asda_ops] FOR LOGIN [asda_ops];
/* ★ А6.7 (22.11): запрет EXECUTE — на схемы dbo и ac, а не на базу (запрет на базу перекрыл бы выдачу на две процедуры журнала дел
   san.UP_SAN_* — sql/adminc_21_san.sql); исполняемых объектов у asda_ops в JoyLog1 ровно эти две (проверка adminc_11). */
REVOKE EXECUTE FROM [asda_ops];
DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];
IF SCHEMA_ID(N'ac') IS NOT NULL DENY EXECUTE ON SCHEMA::ac TO [asda_ops];
DENY ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_ops];
GRANT INSERT ON dbo.AdminitemLog TO [asda_ops];
DENY SELECT, UPDATE, DELETE ON dbo.AdminitemLog TO [asda_ops];
/* 18.11, А1 «соулмейт, друзья, клан» (решение владельца: стоковые журналы — писать, с пометкой «Panel …»): ровно таблицы, которые
   пишут UPSoulMateBreak / UPSoulMateOk (SoulMate), UPSmLevelUp (SoulMateLevelUp), UPCharSoulMate (SoulMateinfo), UPClanBreakUp /
   UPClanMarkUpdate (ClanLog) — только INSERT. Журналов дружбы у стока нет. */
GRANT INSERT ON dbo.SoulMate TO [asda_ops];
GRANT INSERT ON dbo.SoulMateLevelUp TO [asda_ops];
GRANT INSERT ON dbo.SoulMateinfo TO [asda_ops];
GRANT INSERT ON dbo.ClanLog TO [asda_ops];
DENY SELECT, UPDATE, DELETE ON dbo.SoulMate TO [asda_ops];
DENY SELECT, UPDATE, DELETE ON dbo.SoulMateLevelUp TO [asda_ops];
DENY SELECT, UPDATE, DELETE ON dbo.SoulMateinfo TO [asda_ops];
DENY SELECT, UPDATE, DELETE ON dbo.ClanLog TO [asda_ops];
GO

USE [AsdaStoryOp];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') CREATE USER [asda_ops] FOR LOGIN [asda_ops];
GRANT SELECT ON dbo.Us_member TO [asda_ops];
/* 16.11 ночь, А1 «блок учётки»: запрет записи на уровне БАЗЫ перекрывал бы любую выдачу на таблицу — он снят; вместо него
   записи нет ни на что, кроме перечисленного ниже (роль public в AsdaStoryOp записи не имеет — проверено 16.11
   sys.database_permissions: только SELECT системных представлений и EXECUTE sp_*diagram, а EXECUTE запрещён ниже).
   Блок — как ac0_block_user.sql / UPHackBlock: us_block = 5 + строка BlockList; снятие — как штатный OPBlockDel:
   BlockList → BlockHistory, удаление, us_block = 0; откат панели возвращает строки обратно. */
REVOKE INSERT, UPDATE, DELETE FROM [asda_ops];
/* 19.11, А1 «служебная учётка» (sql/adminc_09_accounts.sql): запрет EXECUTE на БАЗУ перекрыл бы выдачу на процедуру — он снят
   (REVOKE снимает и прежний DENY), вместо него EXECUTE запрещён на схему dbo (там все процедуры сервера и sp_*diagram роли public);
   выполнять можно ТОЛЬКО adm.ServiceAccountCreate (проверка adminc_11: исполняемых объектов в AsdaStoryOp ровно 1).
   ALTER на базу тоже не запрещается: процедура подписана сертификатом, его пользователь даёт ALTER Us_member (SET IDENTITY_INSERT),
   а DENY вызывающего перекрыл бы это право. Своего ALTER у asda_ops нет ни на что (не выдан; проверка adminc_11 «Us_member ALTER» = 0). */
REVOKE EXECUTE, ALTER FROM [asda_ops];
DENY REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_ops];
/* ревизия 28 К-3: запас прочности вместо снятого DENY ALTER на базу — явные запреты всего, что меняет состав и права базы. ALTER ANY
   SCHEMA и ALTER на схему dbo НЕ запрещаются: они покрывают ALTER Us_member и перекрыли бы право сертификата (IDENTITY_INSERT). */
DENY ALTER ANY USER, ALTER ANY ROLE, ALTER ANY APPLICATION ROLE, ALTER ANY CERTIFICATE, ALTER ANY ASYMMETRIC KEY, ALTER ANY SYMMETRIC KEY,
     CREATE SCHEMA, CREATE TYPE, CREATE SYNONYM, ALTER ANY DATABASE DDL TRIGGER TO [asda_ops];
DENY ALTER ON SCHEMA::adm TO [asda_ops];
DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];
-- 25.11 (публичный клон, С-5): adm.ServiceAccountCreate создаёт adminc_09 только при столбцах пароля P52 — без них выдача пропускается
IF OBJECT_ID('adm.ServiceAccountCreate', 'P') IS NOT NULL GRANT EXECUTE ON adm.ServiceAccountCreate TO [asda_ops];
GRANT UPDATE (us_block) ON dbo.Us_member TO [asda_ops];
GRANT UPDATE (Flag, UserNum) ON dbo.Us_member TO [asda_ops];           -- 17.11: снять залипший «в игре» (как UPLogOutGame)
IF COL_LENGTH('dbo.Us_member', 'us_pwsalt') IS NOT NULL AND COL_LENGTH('dbo.Us_member', 'us_pwhash') IS NOT NULL
   AND COL_LENGTH('dbo.Us_member', 'us_pwset') IS NOT NULL AND COL_LENGTH('dbo.Us_member', 'us_pwfail') IS NOT NULL
   AND COL_LENGTH('dbo.Us_member', 'us_pwfail_at') IS NOT NULL      -- столбцы пароля P52; без них смена пароля панелью недоступна
    EXEC(N'GRANT UPDATE (us_pwsalt, us_pwhash, us_pwset, us_pwfail, us_pwfail_at) ON dbo.Us_member TO [asda_ops];');
ELSE
    PRINT 'adminc_04_ops: в dbo.Us_member нет столбцов пароля P52 (us_pwsalt, us_pwhash, us_pwset, us_pwfail, us_pwfail_at) - выдача UPDATE пропущена';
GRANT SELECT, INSERT ON dbo.CharacterStat TO [asda_ops];                 -- 18.11: строка восстановленного персонажа (как UPCreateChar)  -- 17.11: пароль учётки (как UP_AC_SetPassword, P52)
GRANT SELECT, INSERT, DELETE ON dbo.BlockList TO [asda_ops];
GRANT SELECT, INSERT ON dbo.BlockHistory TO [asda_ops];          -- перепроверка 6 М2: история блоков панелью не стирается
REVOKE DELETE ON dbo.BlockHistory FROM [asda_ops];
REVOKE INSERT ON dbo.Us_member FROM [asda_ops];
DENY DELETE, INSERT ON dbo.Us_member TO [asda_ops];
GO
-- 17.11, создание учётки (решение владельца). Перепроверка 15 М2: INSERT на таблицу не сужается по столбцам, поэтому вставка
-- идёт через представление dbo (цепочка владения dbo→dbo — права таблицы не проверяются): только столбцы UP_AC_CreateAccount,
-- значения закреплены WITH CHECK OPTION; Realcash, BonusCash, Loginidx, Portalidx, us_pwfail* — умолчания таблицы.
-- 25.11 (публичный клон, С-5): нет столбцов пароля P52 — представление не создаётся (SET NOEXEC до конца блока), создание учётки панелью недоступно
IF COL_LENGTH('dbo.Us_member', 'us_pwsalt') IS NULL OR COL_LENGTH('dbo.Us_member', 'us_pwhash') IS NULL OR COL_LENGTH('dbo.Us_member', 'us_pwset') IS NULL
BEGIN
    PRINT 'adminc_04_ops: в dbo.Us_member нет столбцов пароля P52 - представление dbo.adm_NewAccount не создаётся';
    SET NOEXEC ON;
END
GO
IF OBJECT_ID('dbo.adm_NewAccount', 'V') IS NOT NULL DROP VIEW dbo.adm_NewAccount;
GO
CREATE VIEW dbo.adm_NewAccount AS
SELECT Userindex, Us_id, Us_block, Us_rdate, igsNID, Seridx, Gsidx, Threadidx, Channel, Poridx, UserNum, Flag,
       us_pwsalt, us_pwhash, us_pwset
  FROM dbo.Us_member
 WHERE Us_block = 0 AND igsNID = 0 AND Seridx = 0 AND Gsidx = 0 AND Threadidx = 0 AND Channel = 0 AND Poridx = 3
   AND UserNum = -1 AND Flag = 0 AND us_pwsalt IS NOT NULL AND us_pwhash IS NOT NULL
   AND Us_rdate BETWEEN DATEADD(MINUTE, -5, GETDATE()) AND DATEADD(MINUTE, 5, GETDATE())
   AND us_pwset BETWEEN DATEADD(MINUTE, -5, GETDATE()) AND DATEADD(MINUTE, 5, GETDATE())
WITH CHECK OPTION;
GO
GRANT INSERT ON dbo.adm_NewAccount TO [asda_ops];
GRANT SELECT (Userindex) ON dbo.adm_NewAccount TO [asda_ops];      -- для OUTPUT inserted.Userindex
GO
SET NOEXEC OFF;
GO
PRINT 'adminc_04_ops: OK';
