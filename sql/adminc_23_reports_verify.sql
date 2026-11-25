-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_23_reports_verify.sql — проверка прав asda_reports (бот Discord, жалобы игроков, шаг А6.11, 22.11.2026). Запуск ПОД ЛОГИНОМ
   asda_reports в базе AsdaAdmin (deploy делает сам). Ожидание: только четыре процедуры бота (очистка скриншотов adm.ReportFilePurge — нет, ★ ревизия 67); ни таблиц жалоб, ни журнала и пользователей
   панели, ни игровых баз, ни прав sysadmin. */
SET NOCOUNT ON;
SELECT 'adm.ReportSubmit EXEC'          AS chk, HAS_PERMS_BY_NAME('adm.ReportSubmit','OBJECT','EXECUTE')     AS v, 1 AS want
UNION ALL SELECT 'adm.ReportFileAdd EXEC',      HAS_PERMS_BY_NAME('adm.ReportFileAdd','OBJECT','EXECUTE'),    1
UNION ALL SELECT 'adm.ReportReplyClaim EXEC',   HAS_PERMS_BY_NAME('adm.ReportReplyClaim','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.ReportReplyDone EXEC',    HAS_PERMS_BY_NAME('adm.ReportReplyDone','OBJECT','EXECUTE'),  1
UNION ALL SELECT 'adm.PlayerReport SELECT',     HAS_PERMS_BY_NAME('adm.PlayerReport','OBJECT','SELECT'),      0
UNION ALL SELECT 'adm.PlayerReport UPDATE',     HAS_PERMS_BY_NAME('adm.PlayerReport','OBJECT','UPDATE'),      0
UNION ALL SELECT 'adm.PlayerReport DELETE',     HAS_PERMS_BY_NAME('adm.PlayerReport','OBJECT','DELETE'),      0
UNION ALL SELECT 'adm.PlayerReportFile SELECT', HAS_PERMS_BY_NAME('adm.PlayerReportFile','OBJECT','SELECT'),  0
UNION ALL SELECT 'adm.PlayerReportReply SELECT', HAS_PERMS_BY_NAME('adm.PlayerReportReply','OBJECT','SELECT'), 0
UNION ALL SELECT 'adm.PlayerReportReply INSERT', HAS_PERMS_BY_NAME('adm.PlayerReportReply','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.ReportFilePurge EXEC',    HAS_PERMS_BY_NAME('adm.ReportFilePurge','OBJECT','EXECUTE'),  0
UNION ALL SELECT 'adm.audit SELECT',            HAS_PERMS_BY_NAME('adm.audit','OBJECT','SELECT'),             0
UNION ALL SELECT 'adm.users SELECT',            HAS_PERMS_BY_NAME('adm.users','OBJECT','SELECT'),             0
UNION ALL SELECT 'adm.NameReview SELECT',       ISNULL(HAS_PERMS_BY_NAME('adm.NameReview','OBJECT','SELECT'), 0), 0
UNION ALL SELECT 'adm.BridgeEnqueue EXEC',      ISNULL(HAS_PERMS_BY_NAME('adm.BridgeEnqueue','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'Joy1 CONNECT',                ISNULL(HAS_PERMS_BY_NAME('Joy1',NULL,'CONNECT'), 0),          0
UNION ALL SELECT 'joylog1 CONNECT',             ISNULL(HAS_PERMS_BY_NAME('joylog1',NULL,'CONNECT'), 0),       0
UNION ALL SELECT 'AsdaStoryOp CONNECT',         ISNULL(HAS_PERMS_BY_NAME('AsdaStoryOp',NULL,'CONNECT'), 0),   0
UNION ALL SELECT 'sysadmin',                    IS_SRVROLEMEMBER('sysadmin'),                                 0;
