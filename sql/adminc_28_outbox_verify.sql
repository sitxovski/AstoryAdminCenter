-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_28_outbox_verify.sql — проверка прав asda_reports на очередь исходящих (бот Discord Oracle, шаг А7.4, 23.11.2026). Запуск ПОД ЛОГИНОМ
   asda_reports в базе AsdaAdmin (deploy делает сам, самотест — тем же путём, что бот). Ожидание: четыре процедуры бота — да; таблица adm.Outbox и
   процедуры панели (поставить, отпустить, отменить, повторить, удалить) — нет; sysadmin — нет. */
SET NOCOUNT ON;
SELECT 'adm.OutboxClaim EXEC'          AS chk, HAS_PERMS_BY_NAME('adm.OutboxClaim','OBJECT','EXECUTE')    AS v, 1 AS want
UNION ALL SELECT 'adm.OutboxDone EXEC',        HAS_PERMS_BY_NAME('adm.OutboxDone','OBJECT','EXECUTE'),     1
UNION ALL SELECT 'adm.OutboxDelClaim EXEC',    HAS_PERMS_BY_NAME('adm.OutboxDelClaim','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.OutboxDelDone EXEC',     HAS_PERMS_BY_NAME('adm.OutboxDelDone','OBJECT','EXECUTE'),  1
UNION ALL SELECT 'adm.Outbox SELECT',          HAS_PERMS_BY_NAME('adm.Outbox','OBJECT','SELECT'),          0
UNION ALL SELECT 'adm.Outbox INSERT',          HAS_PERMS_BY_NAME('adm.Outbox','OBJECT','INSERT'),          0
UNION ALL SELECT 'adm.Outbox UPDATE',          HAS_PERMS_BY_NAME('adm.Outbox','OBJECT','UPDATE'),          0
UNION ALL SELECT 'adm.Outbox DELETE',          HAS_PERMS_BY_NAME('adm.Outbox','OBJECT','DELETE'),          0
UNION ALL SELECT 'adm.OutboxPut EXEC',         HAS_PERMS_BY_NAME('adm.OutboxPut','OBJECT','EXECUTE'),      0
UNION ALL SELECT 'adm.OutboxRelease EXEC',     HAS_PERMS_BY_NAME('adm.OutboxRelease','OBJECT','EXECUTE'),  0
UNION ALL SELECT 'adm.OutboxCancel EXEC',      HAS_PERMS_BY_NAME('adm.OutboxCancel','OBJECT','EXECUTE'),   0
UNION ALL SELECT 'adm.OutboxRetry EXEC',       HAS_PERMS_BY_NAME('adm.OutboxRetry','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'adm.OutboxDelete EXEC',      HAS_PERMS_BY_NAME('adm.OutboxDelete','OBJECT','EXECUTE'),   0
UNION ALL SELECT 'adm.audit SELECT',           HAS_PERMS_BY_NAME('adm.audit','OBJECT','SELECT'),           0
UNION ALL SELECT 'sysadmin',                   IS_SRVROLEMEMBER('sysadmin'),                               0;
