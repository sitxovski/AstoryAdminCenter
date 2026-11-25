-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_31_notes_verify.sql — проверка прав asda_reports на «Заметки к выпуску» (шаг А7.7, 24.11.2026). Запуск ПОД ЛОГИНОМ asda_reports в базе
   AsdaAdmin (deploy делает сам). Ожидание: бот не видит ни таблиц заметок, ни процедур панели — всё 0 (запись очереди kind notes бот берёт
   только через adm.OutboxClaim, как любую другую); sysadmin — нет. */
SET NOCOUNT ON;
SELECT 'adm.NotesSnap SELECT'          AS chk, HAS_PERMS_BY_NAME('adm.NotesSnap','OBJECT','SELECT')         AS v, 0 AS want
UNION ALL SELECT 'adm.NotesDraft SELECT',      HAS_PERMS_BY_NAME('adm.NotesDraft','OBJECT','SELECT'),         0
UNION ALL SELECT 'adm.NotesPost SELECT',       HAS_PERMS_BY_NAME('adm.NotesPost','OBJECT','SELECT'),          0
UNION ALL SELECT 'adm.NotesPost INSERT',       HAS_PERMS_BY_NAME('adm.NotesPost','OBJECT','INSERT'),          0
UNION ALL SELECT 'adm.NotesPostEntry SELECT',  HAS_PERMS_BY_NAME('adm.NotesPostEntry','OBJECT','SELECT'),     0
UNION ALL SELECT 'adm.NotesSnapPut EXEC',      HAS_PERMS_BY_NAME('adm.NotesSnapPut','OBJECT','EXECUTE'),      0
UNION ALL SELECT 'adm.NotesDraftSet EXEC',     HAS_PERMS_BY_NAME('adm.NotesDraftSet','OBJECT','EXECUTE'),     0
UNION ALL SELECT 'adm.NotesPublishPut EXEC',   HAS_PERMS_BY_NAME('adm.NotesPublishPut','OBJECT','EXECUTE'),   0
UNION ALL SELECT 'adm.NotesMarkPut EXEC',      HAS_PERMS_BY_NAME('adm.NotesMarkPut','OBJECT','EXECUTE'),      0
UNION ALL SELECT 'adm.NotesEntryPut EXEC',     HAS_PERMS_BY_NAME('adm.NotesEntryPut','OBJECT','EXECUTE'),     0
UNION ALL SELECT 'adm.NotesMarkRevoke EXEC',   HAS_PERMS_BY_NAME('adm.NotesMarkRevoke','OBJECT','EXECUTE'),   0
UNION ALL SELECT 'adm.NotesEntry SELECT',      HAS_PERMS_BY_NAME('adm.NotesEntry','OBJECT','SELECT'),         0
UNION ALL SELECT 'adm.NotesEntrySync EXEC',    HAS_PERMS_BY_NAME('adm.NotesEntrySync','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'adm.NotesEntryHide EXEC',    HAS_PERMS_BY_NAME('adm.NotesEntryHide','OBJECT','EXECUTE'),    0
UNION ALL SELECT 'adm.NotesOutboxClose EXEC',  HAS_PERMS_BY_NAME('adm.NotesOutboxClose','OBJECT','EXECUTE'),  0
UNION ALL SELECT 'adm.NotesSnapDone EXEC',     HAS_PERMS_BY_NAME('adm.NotesSnapDone','OBJECT','EXECUTE'),     0
UNION ALL SELECT 'sysadmin',                   IS_SRVROLEMEMBER('sysadmin'),                                   0;
