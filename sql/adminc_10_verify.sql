-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_10_verify.sql — проверка прав asda_admin после setup. Запуск ПОД ЛОГИНОМ asda_admin (deploy делает сам).
   Ожидание: чтение игровых баз есть, запись — нет ни в одну таблицу; журнал нельзя стереть. 16.11.2026. */
SET NOCOUNT ON;
SELECT 'Joy1.Charinfo SELECT'   AS chk, HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','SELECT')          AS v, 1 AS want
UNION ALL SELECT 'Joy1.Charinfo UPDATE',   HAS_PERMS_BY_NAME('Joy1.dbo.Charinfo','OBJECT','UPDATE'),       0
UNION ALL SELECT 'Joy1.Item INSERT',       HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','INSERT'),           0
UNION ALL SELECT 'Joy1.Item DELETE',       HAS_PERMS_BY_NAME('Joy1.dbo.Item','OBJECT','DELETE'),           0
UNION ALL SELECT 'Joy1.UPRewardItem EXEC', HAS_PERMS_BY_NAME('Joy1.dbo.UPRewardItem','OBJECT','EXECUTE'),  0
UNION ALL SELECT 'Op.Us_member SELECT',    HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','SELECT'), 1
UNION ALL SELECT 'Op.Us_member UPDATE',    HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.Us_member','OBJECT','UPDATE'), 0
UNION ALL SELECT 'log.LogInfo SELECT',     HAS_PERMS_BY_NAME('joylog1.dbo.LogInfo','OBJECT','SELECT'),     1
UNION ALL SELECT 'log.LogInfo DELETE',     HAS_PERMS_BY_NAME('joylog1.dbo.LogInfo','OBJECT','DELETE'),     0
UNION ALL SELECT 'gp7.GP7Balance SELECT',  HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7Balance','OBJECT','SELECT'), 1
UNION ALL SELECT 'gp7.GP7Balance UPDATE',  HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.GP7Balance','OBJECT','UPDATE'), 0
UNION ALL SELECT 'gp7.user.password',      HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.[user]','OBJECT','SELECT','password','COLUMN'), 0
UNION ALL SELECT 'adm.audit INSERT',       HAS_PERMS_BY_NAME('AsdaAdmin.adm.audit','OBJECT','INSERT'),     1
UNION ALL SELECT 'adm.audit DELETE',       HAS_PERMS_BY_NAME('AsdaAdmin.adm.audit','OBJECT','DELETE'),     0
UNION ALL SELECT 'adm.audit UPDATE msg',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.audit','OBJECT','UPDATE','message','COLUMN'), 0
UNION ALL SELECT 'adm.pw_saved INSERT',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.pw_saved','OBJECT','INSERT'),  1
UNION ALL SELECT 'adm.pw_saved UPDATE',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.pw_saved','OBJECT','UPDATE'),  0
UNION ALL SELECT 'adm.users UPDATE',       HAS_PERMS_BY_NAME('AsdaAdmin.adm.users','OBJECT','UPDATE'),     1
UNION ALL SELECT 'Op.sp_creatediagram EXEC',  HAS_PERMS_BY_NAME('AsdaStoryOp.dbo.sp_creatediagram','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'gp7.sp_creatediagram EXEC', HAS_PERMS_BY_NAME('AsdaStoryLogin.dbo.sp_creatediagram','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'log.ac.other INSERT',       HAS_PERMS_BY_NAME('joylog1.ac.other','OBJECT','INSERT'), 0
UNION ALL SELECT 'log.san.cases UPDATE',      HAS_PERMS_BY_NAME('joylog1.san.cases','OBJECT','UPDATE'), 0
-- ★ 22.11 А6.7: дела san.* пишет только asda_ops (adminc_21_san.sql); у логина службы — чтение дел, записи и процедур san нет
UNION ALL SELECT 'log.san.cases SELECT',      HAS_PERMS_BY_NAME('joylog1.san.cases','OBJECT','SELECT'), 1
UNION ALL SELECT 'log.san.case_log INSERT',   HAS_PERMS_BY_NAME('joylog1.san.case_log','OBJECT','INSERT'), 0
UNION ALL SELECT 'log.san.evidence INSERT',   HAS_PERMS_BY_NAME('joylog1.san.evidence','OBJECT','INSERT'), 0
UNION ALL SELECT 'log.san.UP_SAN_SetStatus EXEC', HAS_PERMS_BY_NAME('joylog1.san.UP_SAN_SetStatus','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.changeset INSERT',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.changeset','OBJECT','INSERT'), 1
UNION ALL SELECT 'adm.changeset DELETE',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.changeset','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.changeset_item DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.changeset_item','OBJECT','DELETE'), 1
UNION ALL SELECT 'adm.job INSERT',         HAS_PERMS_BY_NAME('AsdaAdmin.adm.job','OBJECT','INSERT'),       1
UNION ALL SELECT 'adm.job UPDATE',         HAS_PERMS_BY_NAME('AsdaAdmin.adm.job','OBJECT','UPDATE'),       1
UNION ALL SELECT 'adm.job DELETE',         HAS_PERMS_BY_NAME('AsdaAdmin.adm.job','OBJECT','DELETE'),       0
-- ★ 21.11 А5.3: тело UPUserLogin — только просмотр (врезка L09), исполнять нельзя; режим обслуживания панель пишет логином asda_ops
UNION ALL SELECT 'Joy1.UPUserLogin VIEW DEFINITION', HAS_PERMS_BY_NAME('Joy1.dbo.UPUserLogin','OBJECT','VIEW DEFINITION'), 1
UNION ALL SELECT 'Joy1.UPUserLogin EXEC',  HAS_PERMS_BY_NAME('Joy1.dbo.UPUserLogin','OBJECT','EXECUTE'),   0
-- ★ 25.11: процедура второго гейта L09 видна панели (иначе «нет процедуры» ложно); NULL — L09 не применён
UNION ALL SELECT 'Joy1.LoginMaintenanceGate VIEW DEFINITION', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenanceGate','OBJECT','VIEW DEFINITION'), 1), 1
UNION ALL SELECT 'Joy1.LoginMaintenanceGate EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenanceGate','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'Joy1.LoginMaintenanceSet EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.LoginMaintenanceSet','OBJECT','EXECUTE'), 0), 0
-- ★ 21.11 А5.7: бэкапы — только подписанной процедурой; своих прав на BACKUP / VERIFYONLY / состояние сервера у asda_admin нет
UNION ALL SELECT 'adm.DbBackupRun EXEC',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.DbBackupRun','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.DbBackupState EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.DbBackupState','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.dbbackup INSERT',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.dbbackup','OBJECT','INSERT'),  0
UNION ALL SELECT 'adm.dbbackup UPDATE',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.dbbackup','OBJECT','UPDATE'),  0
UNION ALL SELECT 'adm.dbbackup_cfg UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.dbbackup_cfg','OBJECT','UPDATE'), 0
UNION ALL SELECT 'Joy1 BACKUP DATABASE',   HAS_PERMS_BY_NAME('Joy1','DATABASE','BACKUP DATABASE'),         0
UNION ALL SELECT 'Joy1 BACKUP LOG',        HAS_PERMS_BY_NAME('Joy1','DATABASE','BACKUP LOG'),              0
UNION ALL SELECT 'CREATE ANY DATABASE',    HAS_PERMS_BY_NAME(NULL, NULL, 'CREATE ANY DATABASE'),           0
UNION ALL SELECT 'VIEW SERVER STATE',      HAS_PERMS_BY_NAME(NULL, NULL, 'VIEW SERVER STATE'),             0
-- ★ 21.11 А5.8: служебные копии — удаление только подписанной процедурой; своих прав DROP / ALTER у asda_admin нет, каталог и журнал — только чтение
UNION ALL SELECT 'adm.BakState EXEC',      HAS_PERMS_BY_NAME('AsdaAdmin.adm.BakState','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BakDrop EXEC',       HAS_PERMS_BY_NAME('AsdaAdmin.adm.BakDrop','OBJECT','EXECUTE'),  1
UNION ALL SELECT 'adm.bakdrop_obj UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.bakdrop_obj','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.bakdrop_log INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.bakdrop_log','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.bakdrop_log DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.bakdrop_log','OBJECT','DELETE'), 0
UNION ALL SELECT 'Joy1 ALTER ANY SCHEMA',  HAS_PERMS_BY_NAME('Joy1','DATABASE','ALTER ANY SCHEMA'),        0
UNION ALL SELECT 'Joy1 CONTROL',           HAS_PERMS_BY_NAME('Joy1','DATABASE','CONTROL'),                 0
UNION ALL SELECT 'Joy1.AsdaProcBackup CONTROL', ISNULL(HAS_PERMS_BY_NAME('Joy1.dbo.AsdaProcBackup','OBJECT','CONTROL'), 0), 0
-- ★ 21.11 А6.3: снимок золота — только добавление (история не правится и не удаляется)
UNION ALL SELECT 'adm.EconDaily INSERT',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDaily','OBJECT','INSERT'),  1
UNION ALL SELECT 'adm.EconDaily UPDATE',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDaily','OBJECT','UPDATE'),  0
UNION ALL SELECT 'adm.EconDaily DELETE',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDaily','OBJECT','DELETE'),  0
UNION ALL SELECT 'adm.EconDailyChar INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDailyChar','OBJECT','INSERT'), 1
UNION ALL SELECT 'adm.EconDailyChar DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDailyChar','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.EconDailyChar UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDailyChar','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.EconDaily SELECT',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDaily','OBJECT','SELECT'),  1
UNION ALL SELECT 'adm.EconDailyChar SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.EconDailyChar','OBJECT','SELECT'), 1
-- ★ 22.11 А6.6: суточный отчёт античита — только добавление (история не правится и не удаляется)
UNION ALL SELECT 'adm.AcDaily SELECT',     HAS_PERMS_BY_NAME('AsdaAdmin.adm.AcDaily','OBJECT','SELECT'),    1
UNION ALL SELECT 'adm.AcDaily INSERT',     HAS_PERMS_BY_NAME('AsdaAdmin.adm.AcDaily','OBJECT','INSERT'),    1
UNION ALL SELECT 'adm.AcDaily UPDATE',     HAS_PERMS_BY_NAME('AsdaAdmin.adm.AcDaily','OBJECT','UPDATE'),    0
UNION ALL SELECT 'adm.AcDaily DELETE',     HAS_PERMS_BY_NAME('AsdaAdmin.adm.AcDaily','OBJECT','DELETE'),    0
UNION ALL SELECT 'adm.AcDailyPurge EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.AcDailyPurge','OBJECT','EXECUTE'), 1
-- ★ 22.11 А6.11: отметки очереди имён — только добавление (последняя отметка персонажа действует, история не правится)
UNION ALL SELECT 'adm.NameReview SELECT',  HAS_PERMS_BY_NAME('AsdaAdmin.adm.NameReview','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NameReview INSERT',  HAS_PERMS_BY_NAME('AsdaAdmin.adm.NameReview','OBJECT','INSERT'), 1
UNION ALL SELECT 'adm.NameReview UPDATE',  HAS_PERMS_BY_NAME('AsdaAdmin.adm.NameReview','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.NameReview DELETE',  HAS_PERMS_BY_NAME('AsdaAdmin.adm.NameReview','OBJECT','DELETE'), 0
-- ★ 22.11 А6.11 (жалобы игроков из бота Discord, adminc_23_reports.sql): чтение, разбор — только столбцы разбора, ответ — добавление;
--   саму жалобу и скриншоты пишет только бот процедурами (asda_reports), удаления нет
UNION ALL SELECT 'adm.PlayerReport SELECT',        HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.PlayerReport UPDATE status', HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','UPDATE','status','COLUMN'), 1
UNION ALL SELECT 'adm.PlayerReport UPDATE case_no', HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','UPDATE','case_no','COLUMN'), 1
UNION ALL SELECT 'adm.PlayerReport UPDATE body',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','UPDATE','body','COLUMN'), 0
UNION ALL SELECT 'adm.PlayerReport UPDATE reporter_id', HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','UPDATE','reporter_id','COLUMN'), 0
UNION ALL SELECT 'adm.PlayerReport INSERT',        HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.PlayerReport DELETE',        HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReport','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.PlayerReportFile SELECT',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportFile','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.PlayerReportFile INSERT',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportFile','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.PlayerReportFile DELETE',    HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportFile','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.PlayerReportReply SELECT',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportReply','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.PlayerReportReply INSERT',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportReply','OBJECT','INSERT'), 1
UNION ALL SELECT 'adm.PlayerReportReply UPDATE',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportReply','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.PlayerReportReply DELETE',   HAS_PERMS_BY_NAME('AsdaAdmin.adm.PlayerReportReply','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.ReportSubmit EXEC',          HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReportSubmit','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.ReportReplyClaim EXEC',      HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReportReplyClaim','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.ReportFilePurge EXEC',       HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReportFilePurge','OBJECT','EXECUTE'), 1   -- ★ ревизия 67 С-2
-- ★ 22.11 А6.9: журнал корректировок баланса gp7 — только чтение; корректирует только процедура логином asda_ops (adminc_22_gp7adjust.sql)
UNION ALL SELECT 'gp7.adm.GP7AdjustLog SELECT', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLog','OBJECT','SELECT'), 1
UNION ALL SELECT 'gp7.adm.GP7AdjustLog INSERT', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLog','OBJECT','INSERT'), 0
UNION ALL SELECT 'gp7.adm.GP7AdjustLog UPDATE', HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7AdjustLog','OBJECT','UPDATE'), 0
UNION ALL SELECT 'gp7.adm.GP7Adjust EXEC',   HAS_PERMS_BY_NAME('AsdaStoryLogin.adm.GP7Adjust','OBJECT','EXECUTE'), 0
-- ★ 22.11 А6.12 (adminc_24_chat.sql): журнал чата P129 — только чтение; заглушки ставит asda_ops процедурами. Схемы chat ещё нет (P129 не
--   выложен) — строка-отметка «нет схемы» и ожидания «как без схемы» (v = want); схема есть — настоящие права (нет объекта — -1, не сойдётся)
UNION ALL SELECT 'chat (P129): schema ' + CASE WHEN EXISTS (SELECT 1 FROM joylog1.sys.schemas WHERE name = N'chat') THEN 'present' ELSE 'absent - chat checks skipped' END, 0, 0
UNION ALL SELECT 'log.chat.message SELECT', CASE WHEN NOT EXISTS (SELECT 1 FROM joylog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.message','OBJECT','SELECT'), -1) END, 1
UNION ALL SELECT 'log.chat.mute SELECT', CASE WHEN NOT EXISTS (SELECT 1 FROM joylog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.mute','OBJECT','SELECT'), -1) END, 1
UNION ALL SELECT 'log.chat.v_recent SELECT', CASE WHEN NOT EXISTS (SELECT 1 FROM joylog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.v_recent','OBJECT','SELECT'), -1) END, 1
UNION ALL SELECT 'log.chat.v_mute_active SELECT', CASE WHEN NOT EXISTS (SELECT 1 FROM joylog1.sys.schemas WHERE name = N'chat') THEN 1 ELSE ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.v_mute_active','OBJECT','SELECT'), -1) END, 1
UNION ALL SELECT 'log.chat.message INSERT', ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.message','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'log.chat.mute INSERT',    ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.mute','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'log.chat.mute UPDATE',    ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.mute','OBJECT','UPDATE'), 0), 0
UNION ALL SELECT 'log.chat.message DELETE', ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.message','OBJECT','DELETE'), 0), 0
UNION ALL SELECT 'log.chat.UP_ChatMuteSet EXEC',  ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.UP_ChatMuteSet','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'log.chat.UP_ChatMuteLift EXEC', ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.UP_ChatMuteLift','OBJECT','EXECUTE'), 0), 0
UNION ALL SELECT 'log.chat.UP_ChatJournalPurge EXEC', ISNULL(HAS_PERMS_BY_NAME('joylog1.chat.UP_ChatJournalPurge','OBJECT','EXECUTE'), 0), 0
-- ★ 23.11 А6.10 (adminc_25_attendance.sql): журнал ручных отметок посещаемости — только чтение (пишет asda_ops процедурой adm.AttendanceAdjust)
UNION ALL SELECT 'Joy1.adm.AttendanceAdjustLog SELECT', CASE WHEN OBJECT_ID(N'Joy1.adm.AttendanceAdjustLog', N'U') IS NULL THEN 1 ELSE HAS_PERMS_BY_NAME('Joy1.adm.AttendanceAdjustLog','OBJECT','SELECT') END, 1
UNION ALL SELECT 'Joy1.adm.AttendanceAdjustLog INSERT', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.AttendanceAdjustLog','OBJECT','INSERT'), 0), 0
UNION ALL SELECT 'Joy1.adm.AttendanceAdjust EXEC', ISNULL(HAS_PERMS_BY_NAME('Joy1.adm.AttendanceAdjust','OBJECT','EXECUTE'), 0), 0
-- ★ 23.11 А7.1 (adminc_26_releases.sql): снимок конвейера выпуска с ПК — добавление и отметка «ПК присылал», без удаления и без правки снимка
UNION ALL SELECT 'adm.ReleasePcStatus SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.ReleasePcStatus INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','INSERT'), 1
UNION ALL SELECT 'adm.ReleasePcStatus UPDATE seen_utc', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','UPDATE','seen_utc','COLUMN'), 1
UNION ALL SELECT 'adm.ReleasePcStatus UPDATE payload', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','UPDATE','payload','COLUMN'), 0
UNION ALL SELECT 'adm.ReleasePcStatus DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcStatus','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.ReleasePcPrune EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ReleasePcPrune','OBJECT','EXECUTE'), 1   -- ★ р74 М-4: предел истории (не ниже 100)
-- ★ 23.11 А7.2 (adminc_27_crashes.sql): сводка сбоев клиента с ПК — только чтение и две процедуры записи, прямой записи в таблицы нет
UNION ALL SELECT 'adm.ClientCrash SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.ClientCrash INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.ClientCrash UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.ClientCrash DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrash','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.ClientCrashSig SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashSig','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.ClientCrashSig INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashSig','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.ClientCrashSync SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashSync','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.ClientCrashSync DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashSync','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.ClientCrashPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.ClientCrashSyncAdd EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.ClientCrashSyncAdd','OBJECT','EXECUTE'), 1
-- ★ 23.11 А7.4 (adminc_28_outbox.sql): очередь исходящих (Discord) — чтение и пять процедур панели, прямой записи и процедур бота нет
UNION ALL SELECT 'adm.Outbox SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.Outbox','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.Outbox INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.Outbox','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.Outbox UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.Outbox','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.Outbox DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.Outbox','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.OutboxPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.OutboxRelease EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxRelease','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.OutboxCancel EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxCancel','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.OutboxRetry EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxRetry','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.OutboxDelete EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxDelete','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.OutboxClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxClaim','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.OutboxDone EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxDone','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.OutboxDelClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxDelClaim','OBJECT','EXECUTE'), 0   -- ★ р76 К3
UNION ALL SELECT 'adm.OutboxDelDone EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxDelDone','OBJECT','EXECUTE'), 0
-- ★ 23.11 А7.5 (adminc_29_telegram.sql): Telegram владельцу — чтение выключателей, памяти и отметок, процедуры панели; прямой записи и процедур отправителя нет
UNION ALL SELECT 'adm.NotifyRule SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotifyRule','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NotifyRule UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotifyRule','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.NotifyState INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotifyState','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.NotifyBeat SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotifyBeat','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.TgNotifyPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgNotifyPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.TgRuleSet EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgRuleSet','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.TgTestPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgTestPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.TgClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgClaim','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.TgDone EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgDone','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.TgBeatGet EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgBeatGet','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.TgLocalNote EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgLocalNote','OBJECT','EXECUTE'), 0
-- ★ 24.11 А7.6 (adminc_30_community.sql): «Сообщество» — ★ р79 М-3: каждое GRANT / DENY панели — SELECT семи таблиц да, запись нет, четыре процедуры панели да, три процедуры бота нет
UNION ALL SELECT 'adm.BotCmd SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmd','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotCmd INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmd','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotCmd UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmd','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotCmd DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmd','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotSnap SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotSnap','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotSnap INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotSnap','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotSnap UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotSnap','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotSnap DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotSnap','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotApp SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotApp','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotApp INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotApp','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotApp UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotApp','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotApp DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotApp','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotTester SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotTester','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotTester INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotTester','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotTester UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotTester','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotTester DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotTester','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotWarn SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotWarn','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotWarn INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotWarn','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotWarn UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotWarn','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotWarn DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotWarn','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotBan SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotBan','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotBan INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotBan','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotBan UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotBan','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotBan DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotBan','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotStaff SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotStaff','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.BotStaff INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotStaff','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.BotStaff UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotStaff','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.BotStaff DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotStaff','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.BotCmdPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmdPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BotCmdRelease EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmdRelease','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BotCmdCancel EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmdCancel','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BotCmdRetry EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmdRetry','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BotCmdClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmdClaim','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.BotCmdDone EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotCmdDone','OBJECT','EXECUTE'), 0
UNION ALL SELECT 'adm.BotSnapPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.BotSnapPut','OBJECT','EXECUTE'), 0
-- ★ А7.7 (24.11): заметки к выпуску (adminc_31_notes.sql) — чтение и шесть процедур панели, прямой записи нет
UNION ALL SELECT 'adm.NotesSnap SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesSnap','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NotesSnap INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesSnap','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.NotesSnap UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesSnap','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.NotesDraft SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesDraft','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NotesDraft UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesDraft','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.NotesPost SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPost','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NotesPost INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPost','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.NotesPost UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPost','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.NotesPost DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPost','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.NotesPostEntry SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPostEntry','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NotesPostEntry INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPostEntry','OBJECT','INSERT'), 0
UNION ALL SELECT 'adm.NotesPostEntry DELETE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPostEntry','OBJECT','DELETE'), 0
UNION ALL SELECT 'adm.NotesEntry SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesEntry','OBJECT','SELECT'), 1
UNION ALL SELECT 'adm.NotesEntry UPDATE', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesEntry','OBJECT','UPDATE'), 0
UNION ALL SELECT 'adm.NotesEntrySync EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesEntrySync','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesEntryHide EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesEntryHide','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesSnapDone EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesSnapDone','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesOutboxClose EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesOutboxClose','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesSnapPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesSnapPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesDraftSet EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesDraftSet','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesPublishPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPublishPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesMarkPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesMarkPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesEntryPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesEntryPut','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.NotesMarkRevoke EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesMarkRevoke','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'sysadmin',              IS_SRVROLEMEMBER('sysadmin'),                                   0;
