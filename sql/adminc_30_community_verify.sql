-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_30_community_verify.sql — проверка прав asda_reports на копию реестра и очередь команд боту (бот Oracle, шаг А7.6, 24.11.2026). Запуск ПОД
   ЛОГИНОМ asda_reports в базе AsdaAdmin (deploy делает сам, самотест — тем же путём, что бот). ★ ревизия 79 М-3: проверяется КАЖДОЕ GRANT и DENY
   adminc_30 — три процедуры бота да, четыре процедуры панели нет, семь таблиц × SELECT / INSERT / UPDATE / DELETE нет, sysadmin нет (36). */
SET NOCOUNT ON;
SELECT 'adm.BotCmdClaim EXEC'           AS chk, HAS_PERMS_BY_NAME('adm.BotCmdClaim','OBJECT','EXECUTE')      AS v, 1 AS want
UNION ALL SELECT 'adm.BotCmdDone EXEC',    HAS_PERMS_BY_NAME('adm.BotCmdDone','OBJECT','EXECUTE'),      1
UNION ALL SELECT 'adm.BotSnapPut EXEC',    HAS_PERMS_BY_NAME('adm.BotSnapPut','OBJECT','EXECUTE'),      1
UNION ALL SELECT 'adm.BotCmdPut EXEC',     HAS_PERMS_BY_NAME('adm.BotCmdPut','OBJECT','EXECUTE'),       0
UNION ALL SELECT 'adm.BotCmdRelease EXEC', HAS_PERMS_BY_NAME('adm.BotCmdRelease','OBJECT','EXECUTE'),   0
UNION ALL SELECT 'adm.BotCmdCancel EXEC',  HAS_PERMS_BY_NAME('adm.BotCmdCancel','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'adm.BotCmdRetry EXEC',   HAS_PERMS_BY_NAME('adm.BotCmdRetry','OBJECT','EXECUTE'),     0
UNION ALL SELECT 'adm.BotCmd SELECT',      HAS_PERMS_BY_NAME('adm.BotCmd','OBJECT','SELECT'),           0
UNION ALL SELECT 'adm.BotCmd INSERT',      HAS_PERMS_BY_NAME('adm.BotCmd','OBJECT','INSERT'),           0
UNION ALL SELECT 'adm.BotCmd UPDATE',      HAS_PERMS_BY_NAME('adm.BotCmd','OBJECT','UPDATE'),           0
UNION ALL SELECT 'adm.BotCmd DELETE',      HAS_PERMS_BY_NAME('adm.BotCmd','OBJECT','DELETE'),           0
UNION ALL SELECT 'adm.BotSnap SELECT',     HAS_PERMS_BY_NAME('adm.BotSnap','OBJECT','SELECT'),          0
UNION ALL SELECT 'adm.BotSnap INSERT',     HAS_PERMS_BY_NAME('adm.BotSnap','OBJECT','INSERT'),          0
UNION ALL SELECT 'adm.BotSnap UPDATE',     HAS_PERMS_BY_NAME('adm.BotSnap','OBJECT','UPDATE'),          0
UNION ALL SELECT 'adm.BotSnap DELETE',     HAS_PERMS_BY_NAME('adm.BotSnap','OBJECT','DELETE'),          0
UNION ALL SELECT 'adm.BotApp SELECT',      HAS_PERMS_BY_NAME('adm.BotApp','OBJECT','SELECT'),           0
UNION ALL SELECT 'adm.BotApp INSERT',      HAS_PERMS_BY_NAME('adm.BotApp','OBJECT','INSERT'),           0
UNION ALL SELECT 'adm.BotApp UPDATE',      HAS_PERMS_BY_NAME('adm.BotApp','OBJECT','UPDATE'),           0
UNION ALL SELECT 'adm.BotApp DELETE',      HAS_PERMS_BY_NAME('adm.BotApp','OBJECT','DELETE'),           0
UNION ALL SELECT 'adm.BotTester SELECT',   HAS_PERMS_BY_NAME('adm.BotTester','OBJECT','SELECT'),        0
UNION ALL SELECT 'adm.BotTester INSERT',   HAS_PERMS_BY_NAME('adm.BotTester','OBJECT','INSERT'),        0
UNION ALL SELECT 'adm.BotTester UPDATE',   HAS_PERMS_BY_NAME('adm.BotTester','OBJECT','UPDATE'),        0
UNION ALL SELECT 'adm.BotTester DELETE',   HAS_PERMS_BY_NAME('adm.BotTester','OBJECT','DELETE'),        0
UNION ALL SELECT 'adm.BotWarn SELECT',     HAS_PERMS_BY_NAME('adm.BotWarn','OBJECT','SELECT'),          0
UNION ALL SELECT 'adm.BotWarn INSERT',     HAS_PERMS_BY_NAME('adm.BotWarn','OBJECT','INSERT'),          0
UNION ALL SELECT 'adm.BotWarn UPDATE',     HAS_PERMS_BY_NAME('adm.BotWarn','OBJECT','UPDATE'),          0
UNION ALL SELECT 'adm.BotWarn DELETE',     HAS_PERMS_BY_NAME('adm.BotWarn','OBJECT','DELETE'),          0
UNION ALL SELECT 'adm.BotBan SELECT',      HAS_PERMS_BY_NAME('adm.BotBan','OBJECT','SELECT'),           0
UNION ALL SELECT 'adm.BotBan INSERT',      HAS_PERMS_BY_NAME('adm.BotBan','OBJECT','INSERT'),           0
UNION ALL SELECT 'adm.BotBan UPDATE',      HAS_PERMS_BY_NAME('adm.BotBan','OBJECT','UPDATE'),           0
UNION ALL SELECT 'adm.BotBan DELETE',      HAS_PERMS_BY_NAME('adm.BotBan','OBJECT','DELETE'),           0
UNION ALL SELECT 'adm.BotStaff SELECT',    HAS_PERMS_BY_NAME('adm.BotStaff','OBJECT','SELECT'),         0
UNION ALL SELECT 'adm.BotStaff INSERT',    HAS_PERMS_BY_NAME('adm.BotStaff','OBJECT','INSERT'),         0
UNION ALL SELECT 'adm.BotStaff UPDATE',    HAS_PERMS_BY_NAME('adm.BotStaff','OBJECT','UPDATE'),         0
UNION ALL SELECT 'adm.BotStaff DELETE',    HAS_PERMS_BY_NAME('adm.BotStaff','OBJECT','DELETE'),         0
UNION ALL SELECT 'sysadmin',               IS_SRVROLEMEMBER('sysadmin'),                                0;
