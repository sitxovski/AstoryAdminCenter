-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_32_botreg_verify.sql — проверка прав asda_reports на регистрацию учёток из бота (/register, 25.11.2026). Запуск ПОД ЛОГИНОМ
   asda_reports в базе AsdaStoryOp. Ожидание: у бота есть ТОЛЬКО EXECUTE adm.BotAccountRegister; таблицы привязки и учёток он не читает и не
   пишет, служебную учётку создать не может, чужих процедур не вызывает; sysadmin — нет. Столбец v должен совпасть с want во всех строках. */
SET NOCOUNT ON;
SELECT 'adm.BotAccountRegister EXEC'    AS chk, HAS_PERMS_BY_NAME('adm.BotAccountRegister','OBJECT','EXECUTE')   AS v, 1 AS want
UNION ALL SELECT 'adm.BotAccount SELECT',        HAS_PERMS_BY_NAME('adm.BotAccount','OBJECT','SELECT'),           0
UNION ALL SELECT 'adm.BotAccount INSERT',        HAS_PERMS_BY_NAME('adm.BotAccount','OBJECT','INSERT'),           0
UNION ALL SELECT 'adm.BotAccount UPDATE',        HAS_PERMS_BY_NAME('adm.BotAccount','OBJECT','UPDATE'),           0
UNION ALL SELECT 'adm.BotAccount DELETE',        HAS_PERMS_BY_NAME('adm.BotAccount','OBJECT','DELETE'),           0
UNION ALL SELECT 'dbo.Us_member SELECT',         HAS_PERMS_BY_NAME('dbo.Us_member','OBJECT','SELECT'),            0
UNION ALL SELECT 'dbo.Us_member INSERT',         HAS_PERMS_BY_NAME('dbo.Us_member','OBJECT','INSERT'),            0
UNION ALL SELECT 'dbo.Us_member UPDATE',         HAS_PERMS_BY_NAME('dbo.Us_member','OBJECT','UPDATE'),            0
UNION ALL SELECT 'dbo.Us_member DELETE',         HAS_PERMS_BY_NAME('dbo.Us_member','OBJECT','DELETE'),            0
UNION ALL SELECT 'adm.ServiceAccountCreate EXEC', ISNULL(HAS_PERMS_BY_NAME('adm.ServiceAccountCreate','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'schema dbo EXEC',              HAS_PERMS_BY_NAME('dbo','SCHEMA','EXECUTE'),                     0
UNION ALL SELECT 'schema dbo SELECT',            HAS_PERMS_BY_NAME('dbo','SCHEMA','SELECT'),                      0
UNION ALL SELECT 'schema adm SELECT',            HAS_PERMS_BY_NAME('adm','SCHEMA','SELECT'),                      0
UNION ALL SELECT 'database CREATE TABLE',        HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CREATE TABLE'),          0
UNION ALL SELECT 'db_owner',                     IS_MEMBER('db_owner'),                                           0
UNION ALL SELECT 'sysadmin',                     IS_SRVROLEMEMBER('sysadmin'),                                    0;
