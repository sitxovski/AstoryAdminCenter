-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_29_telegram_verify.sql — проверка прав asda_reports на очередь Telegram (отправитель на ПК в боте Oracle, шаг А7.5, 23.11.2026). Запуск ПОД
   ЛОГИНОМ asda_reports в базе AsdaAdmin (deploy делает сам, самотест — тем же путём, что отправитель). Ожидание: четыре процедуры отправителя (★ р77 К-3: + TgLocalNote) — да;
   таблицы выключателей, памяти и отметок, процедуры панели — нет; sysadmin — нет. */
SET NOCOUNT ON;
SELECT 'adm.TgClaim EXEC'              AS chk, HAS_PERMS_BY_NAME('adm.TgClaim','OBJECT','EXECUTE')      AS v, 1 AS want
UNION ALL SELECT 'adm.TgDone EXEC',            HAS_PERMS_BY_NAME('adm.TgDone','OBJECT','EXECUTE'),       1
UNION ALL SELECT 'adm.TgBeatGet EXEC',         HAS_PERMS_BY_NAME('adm.TgBeatGet','OBJECT','EXECUTE'),    1
UNION ALL SELECT 'adm.TgLocalNote EXEC',       HAS_PERMS_BY_NAME('adm.TgLocalNote','OBJECT','EXECUTE'),  1
UNION ALL SELECT 'adm.NotifyRule SELECT',      HAS_PERMS_BY_NAME('adm.NotifyRule','OBJECT','SELECT'),    0
UNION ALL SELECT 'adm.NotifyRule UPDATE',      HAS_PERMS_BY_NAME('adm.NotifyRule','OBJECT','UPDATE'),    0
UNION ALL SELECT 'adm.NotifyState SELECT',     HAS_PERMS_BY_NAME('adm.NotifyState','OBJECT','SELECT'),   0
UNION ALL SELECT 'adm.NotifyState INSERT',     HAS_PERMS_BY_NAME('adm.NotifyState','OBJECT','INSERT'),   0
UNION ALL SELECT 'adm.NotifyBeat SELECT',      HAS_PERMS_BY_NAME('adm.NotifyBeat','OBJECT','SELECT'),    0
UNION ALL SELECT 'adm.NotifyBeat UPDATE',      HAS_PERMS_BY_NAME('adm.NotifyBeat','OBJECT','UPDATE'),    0
UNION ALL SELECT 'adm.Outbox SELECT',          HAS_PERMS_BY_NAME('adm.Outbox','OBJECT','SELECT'),        0
UNION ALL SELECT 'adm.TgRuleSet EXEC',         HAS_PERMS_BY_NAME('adm.TgRuleSet','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'adm.TgNotifyPut EXEC',       HAS_PERMS_BY_NAME('adm.TgNotifyPut','OBJECT','EXECUTE'),  0
UNION ALL SELECT 'adm.TgStateSet EXEC',        HAS_PERMS_BY_NAME('adm.TgStateSet','OBJECT','EXECUTE'),   0
UNION ALL SELECT 'adm.TgBeatSet EXEC',         HAS_PERMS_BY_NAME('adm.TgBeatSet','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'adm.TgTestPut EXEC',         HAS_PERMS_BY_NAME('adm.TgTestPut','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'sysadmin',                   IS_SRVROLEMEMBER('sysadmin'),                             0;
