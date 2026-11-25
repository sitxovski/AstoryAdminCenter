-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_16_dbbackup.sql — бэкапы баз панелью (шаг А5.7 «Бэкапы БД», план §4 Д, §5.1; отчёт
   Reports/admin_center/impl_a5_live_20261121.md, раздел А5.7). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ adminc_03_grants,
   под Windows-входом Administrator через shared memory (sqlcmd -S lpc:.\SQLEXPRESS -E — sysadmin). Тот же файл самотест выполняет на LocalDB
   (там пользователя asda_admin нет — выдача прав пропускается). Повторный запуск безопасен. 21.11.2026.

   ЧТО ДЕЛАЕТ ПАНЕЛЬ: только полный BACKUP DATABASE … WITH COPY_ONLY, CHECKSUM (COPY_ONLY — чужую цепочку полных / разностных / журнальных бэкапов
   не трогает) и RESTORE VERIFYONLY … WITH CHECKSUM; баз — только из белого списка adm.dbbackup_db; файл — только в папку adm.dbbackup_cfg;
   BACKUP LOG, RESTORE DATABASE, смена модели восстановления — НЕТ (восстановление — только на стенд LocalDB ПК, domains/dbstand.py).
   ПРАВА (без sysadmin у служебных логинов). BACKUP DATABASE требует db_backupoperator (или db_owner / sysadmin) в КАЖДОЙ базе, VERIFYONLY —
   CREATE DATABASE, место на диске — VIEW SERVER STATE, история msdb — SELECT в msdb. Ничего из этого asda_admin НЕ выдаётся: процедуры
   adm.DbBackupRun / DbBackupVerify / DbBackupState / DbBackupAbort / DbBackupBusy (★ ревизия 47) подписаны сертификатом adm_dbbackup_cert; из сертификата (его открытой
   части в master) — логин adm_dbbackup_signer (войти им нельзя) с VIEW SERVER STATE и CREATE ANY DATABASE, его пользователь в каждой базе
   списка — в db_backupoperator, в msdb — SELECT двух таблиц истории. Закрытый ключ сертификата после подписи СТИРАЕТСЯ (REMOVE PRIVATE KEY) —
   подписать другой код им нельзя; правка процедуры снимает подпись (повторный запуск файла пересоздаёт сертификат и подпись).
   asda_admin: EXECUTE на процедуры adm.DbBackup*, SELECT на adm.dbbackup*, прямой записи в таблицы нет.
   ЗАЩИТА ФАЙЛОВ: имена <база>_<ГГГГММДД>_<ЧЧММСС>_<номер>.bak (UTC), добавление в файл (NOINIT, NOSKIP) — существующий файл не затирается;
   удаление файлов — только служба (domains/dbbackup.py, ротация) и только строк этой таблицы. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.dbbackup_cfg') IS NULL
CREATE TABLE adm.dbbackup_cfg (
    id              TINYINT        NOT NULL CONSTRAINT PK_adm_dbbackup_cfg PRIMARY KEY CONSTRAINT CK_adm_dbbackup_cfg_one CHECK (id = 1),
    folder          NVARCHAR(200)  NOT NULL,                       -- папка бэкапов панели (на сервере; права — SQL Server, SYSTEM, Administrators)
    free_factor     INT            NOT NULL CONSTRAINT DF_adm_dbbackup_cfg_ff DEFAULT 2,     -- свободно ≥ данные базы × free_factor + free_reserve_mb
    free_reserve_mb INT            NOT NULL CONSTRAINT DF_adm_dbbackup_cfg_fr DEFAULT 1024
);
GO
IF NOT EXISTS (SELECT 1 FROM adm.dbbackup_cfg) INSERT adm.dbbackup_cfg (id, folder) VALUES (1, N'@@ASTORY_SERVER_ROOT@@\DbBackup');
GO
IF OBJECT_ID(N'adm.dbbackup_db') IS NULL
CREATE TABLE adm.dbbackup_db (name SYSNAME NOT NULL CONSTRAINT PK_adm_dbbackup_db PRIMARY KEY);
GO
INSERT adm.dbbackup_db (name)
SELECT d.name FROM sys.databases d WHERE d.name IN (N'AsdaAdmin', N'AsdaStoryLogin', N'AsdaStoryOp', N'Joy1', N'joylog1')
  AND NOT EXISTS (SELECT 1 FROM adm.dbbackup_db x WHERE x.name = d.name COLLATE DATABASE_DEFAULT);   -- сортировка сервера ≠ базы (стенд LocalDB)
GO
IF OBJECT_ID(N'adm.dbbackup') IS NULL
CREATE TABLE adm.dbbackup (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_dbbackup PRIMARY KEY,
    db              SYSNAME        NOT NULL,
    file_path       NVARCHAR(400)  NOT NULL,
    status          VARCHAR(10)    NOT NULL CONSTRAINT DF_adm_dbbackup_status DEFAULT 'running',
    verified        BIT            NULL,                           -- NULL — не проверялся, 1 — VERIFYONLY прошёл, 0 — не прошёл
    verified_at     DATETIME2(0)   NULL,
    started_at      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_dbbackup_started DEFAULT SYSUTCDATETIME(),
    finished_at     DATETIME2(0)   NULL,
    by_login        NVARCHAR(64)   NOT NULL,
    job_id          INT            NULL,
    data_bytes      BIGINT         NULL,                           -- размер файлов данных базы на момент бэкапа (оценка места)
    free_bytes      BIGINT         NULL,                           -- свободно на томе папки перед бэкапом
    backup_bytes    BIGINT         NULL,                           -- msdb.backupset.backup_size
    position        INT            NULL,                           -- номер набора в файле (RESTORE … FILE =)
    backup_set_id   INT            NULL,
    checkpoint_lsn  NUMERIC(25,0)  NULL,
    file_bytes      BIGINT         NULL,                           -- длина файла (служба, после проверки)
    md5             CHAR(32)       NULL,                           -- md5 файла (служба; стенд сверяет скачанное)
    counts          NVARCHAR(MAX)  NULL,                           -- JSON: строк в таблицах сразу после бэкапа (служба, asda_admin)
    message         NVARCHAR(2000) NULL,
    stand_at        DATETIME2(0)   NULL,
    stand_ok        BIT            NULL,
    stand_result    NVARCHAR(MAX)  NULL,                           -- JSON итога стенда LocalDB (CHECKDB, строки)
    deleted_at      DATETIME2(0)   NULL,
    deleted_by      NVARCHAR(64)   NULL,
    deleted_why     NVARCHAR(400)  NULL,
    CONSTRAINT CK_adm_dbbackup_status CHECK (status IN ('running','done','failed','deleted'))
);
GO
/* ★ ревизия 47 Н-4: метка вызова (её даёт служба) — строку итога ищут по ней, а не по часам ПК */
IF COL_LENGTH(N'adm.dbbackup', N'run_tag') IS NULL ALTER TABLE adm.dbbackup ADD run_tag UNIQUEIDENTIFIER NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_dbbackup_db' AND object_id = OBJECT_ID(N'adm.dbbackup'))
    CREATE INDEX IX_adm_dbbackup_db ON adm.dbbackup (db, id DESC);
GO
/* одновременно — один бэкап панели (строка running одна); зависшую строку (служба / SQL упали посреди) снимает следующий запуск, если BACKUP
   на сервере сейчас не идёт (sys.dm_exec_requests) */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_adm_dbbackup_running' AND object_id = OBJECT_ID(N'adm.dbbackup'))
    CREATE UNIQUE INDEX UX_adm_dbbackup_running ON adm.dbbackup (status) WHERE status = 'running';
GO

/* ---------- снятие прежней подписи (повторный запуск): процедуры пересоздаются ниже, сертификат и его логин — тоже ---------- */
DECLARE @d SYSNAME, @q NVARCHAR(MAX);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' AND is_read_only = 0 AND name NOT IN (N'tempdb', N'model');
OPEN c; FETCH c INTO @d;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @q = N'EXEC ' + QUOTENAME(@d) + N'.sys.sp_executesql @s';
    EXEC sys.sp_executesql @q, N'@s NVARCHAR(MAX)', N'IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N''adm_dbbackup_u'') DROP USER adm_dbbackup_u;';
    FETCH c INTO @d;
END
CLOSE c; DEALLOCATE c;
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'adm_dbbackup_signer') DROP LOGIN adm_dbbackup_signer;
EXEC master.sys.sp_executesql N'IF EXISTS (SELECT 1 FROM sys.certificates WHERE name = N''adm_dbbackup_cert'') DROP CERTIFICATE adm_dbbackup_cert;';
IF OBJECT_ID(N'adm.DbBackupRun') IS NOT NULL DROP PROCEDURE adm.DbBackupRun;
IF OBJECT_ID(N'adm.DbBackupVerify') IS NOT NULL DROP PROCEDURE adm.DbBackupVerify;
IF OBJECT_ID(N'adm.DbBackupState') IS NOT NULL DROP PROCEDURE adm.DbBackupState;
IF OBJECT_ID(N'adm.DbBackupAbort') IS NOT NULL DROP PROCEDURE adm.DbBackupAbort;
IF OBJECT_ID(N'adm.DbBackupBusy') IS NOT NULL DROP PROCEDURE adm.DbBackupBusy;
IF EXISTS (SELECT 1 FROM sys.certificates WHERE name = N'adm_dbbackup_cert') DROP CERTIFICATE adm_dbbackup_cert;
GO

/* Свободное место на томе папки бэкапов (по тому, где лежат файлы баз; другой том — NULL = «не прочитано», не «нет места»). */
CREATE OR ALTER FUNCTION adm.DbBackupFree () RETURNS TABLE AS RETURN
SELECT TOP 1 CAST(vs.available_bytes AS BIGINT) AS free_bytes, CAST(vs.total_bytes AS BIGINT) AS total_bytes, vs.volume_mount_point AS volume
FROM sys.master_files f CROSS APPLY sys.dm_os_volume_stats(f.database_id, f.file_id) vs
CROSS JOIN adm.dbbackup_cfg c
WHERE c.id = 1 AND LEFT(c.folder, LEN(vs.volume_mount_point)) = vs.volume_mount_point COLLATE DATABASE_DEFAULT
ORDER BY LEN(vs.volume_mount_point) DESC;
GO

/* ★ ревизия 47 С-1: «один бэкап панели за раз» — блокировка приложения adm.dbbackup (владелец — сеанс). Её держит идущий DbBackupRun /
   DbBackupVerify всё время, от проверок до итога; сеанс оборвался (служба, SQL, сервер упали) — блокировка снимается сама. Строка running при
   свободной блокировке — зависшая. Занято (1): блокировку держит ДРУГОЙ сеанс или на сервере сейчас идёт BACKUP / RESTORE. */
CREATE PROCEDURE adm.DbBackupBusy
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @held BIT = CASE WHEN APPLOCK_TEST(N'public', N'adm.dbbackup', N'Exclusive', N'Session') = 0 THEN 1 ELSE 0 END;
    DECLARE @cmd BIT = CASE WHEN EXISTS (SELECT 1 FROM sys.dm_exec_requests WHERE session_id <> @@SPID
                                         AND (command LIKE N'BACKUP%' OR command LIKE N'RESTORE%')) THEN 1 ELSE 0 END;
    SELECT @held AS lock_held, @cmd AS server_backup, (SELECT COUNT(*) FROM adm.dbbackup WHERE status = 'running') AS running_rows,
           (SELECT MIN(id) FROM adm.dbbackup WHERE status = 'running') AS running_id;
END
GO

/* Зависшая строка running (блокировка свободна и BACKUP / RESTORE на сервере не идёт) → failed → 0; занято → 1, строка не трогается.
   Вызывают DbBackupRun / DbBackupVerify (под своей блокировкой — тогда своя блокировка не считается занятостью), служба после сбоя запроса
   (с текстом ошибки) и операция db.release (снять вручную). */
CREATE PROCEDURE adm.DbBackupAbort @msg NVARCHAR(2000) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF APPLOCK_TEST(N'public', N'adm.dbbackup', N'Exclusive', N'Session') = 0
        RETURN 1;                                                    -- блокировку держит другой сеанс — бэкап идёт
    IF APPLOCK_MODE(N'public', N'adm.dbbackup', N'Session') = N'NoLock'
       AND EXISTS (SELECT 1 FROM sys.dm_exec_requests WHERE session_id <> @@SPID AND (command LIKE N'BACKUP%' OR command LIKE N'RESTORE%'))
        RETURN 1;                                                    -- без своей блокировки: идёт чей-то BACKUP / RESTORE (откат обрыва) — ждём
    UPDATE adm.dbbackup SET status = 'failed', finished_at = SYSUTCDATETIME(),
           message = LEFT(COALESCE(@msg, N'прервано: бэкап не завершился (служба или SQL Server остановлены посреди)'), 2000)
    WHERE status = 'running';
    RETURN 0;
END
GO

/* Снять свою блокировку (служба зовёт на том же соединении после обрыва запроса — соединение уходит в пул ODBC живым). Без подписи. */
CREATE OR ALTER PROCEDURE adm.DbBackupUnlock
AS
BEGIN
    SET NOCOUNT ON;
    WHILE APPLOCK_MODE(N'public', N'adm.dbbackup', N'Session') <> N'NoLock'
        EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
END
GO

/* Бэкап одной базы: проверки → строка running → BACKUP … COPY_ONLY, CHECKSUM → история msdb → VERIFYONLY → итог (одна строка adm.dbbackup). */
CREATE PROCEDURE adm.DbBackupRun @db SYSNAME, @by NVARCHAR(64), @job INT = NULL, @tag UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @folder NVARCHAR(200), @ff INT, @fr INT, @data BIGINT, @free BIGINT, @id INT, @file NVARCHAR(400), @name NVARCHAR(128),
            @pos INT, @bsid INT, @size BIGINT, @lsn NUMERIC(25,0), @chk BIT, @msg NVARCHAR(2048), @lk INT, @canon SYSNAME;
    -- ★ ревизия 47 (мелочь 1): «=» в T-SQL не видит хвостовых пробелов — имя только из букв, цифр и «_», дальше — каноническое из списка
    IF @db IS NULL OR @db LIKE N'%[^A-Za-z0-9_]%' OR DATALENGTH(@db) = 0
        THROW 50701, N'база вне списка бэкапов панели (adm.dbbackup_db) — бэкап не начат', 1;
    SELECT @canon = name FROM adm.dbbackup_db WHERE name = @db;
    IF @canon IS NULL
        THROW 50701, N'база вне списка бэкапов панели (adm.dbbackup_db) — бэкап не начат', 1;
    SET @db = @canon;
    IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = @db AND state_desc = N'ONLINE')
        THROW 50702, N'база не в состоянии ONLINE — бэкап не начат', 1;
    SELECT @folder = folder, @ff = free_factor, @fr = free_reserve_mb FROM adm.dbbackup_cfg WHERE id = 1;
    -- ★ ревизия 47 (мелочь 2): то же правило, что FOLDER_RX службы — полный путь, без «..» и без кавычек и знаков оболочки
    IF @folder IS NULL OR @folder NOT LIKE N'[A-Za-z]:\%' OR @folder LIKE N'%..%' OR @folder LIKE N'%[''"`$;&|<>*?]%'
        THROW 50703, N'папка бэкапов панели не задана или задана не полным путём — бэкап не начат', 1;
    -- ★ ревизия 47 С-1: одна за раз — блокировка приложения на сеанс (держится до итога, при обрыве сеанса снимается сама)
    EXEC @lk = sp_getapplock @Resource = N'adm.dbbackup', @LockMode = N'Exclusive', @LockOwner = N'Session', @LockTimeout = 0;
    IF @lk < 0
        THROW 50704, N'уже идёт бэкап или восстановление на сервере — бэкап не начат', 1;
    IF EXISTS (SELECT 1 FROM adm.dbbackup WHERE status = 'running')       -- под блокировкой: чужой строки running быть не может — зависшая
        UPDATE adm.dbbackup SET status = 'failed', finished_at = SYSUTCDATETIME(),
               message = N'прервано: бэкап не завершился (служба или SQL Server остановлены посреди)' WHERE status = 'running';
    SELECT @data = SUM(CAST(size AS BIGINT)) * 8192 FROM sys.master_files WHERE database_id = DB_ID(@db) AND type = 0;
    SELECT @free = free_bytes FROM adm.DbBackupFree();
    IF @data IS NULL OR @free IS NULL OR @free < @data * @ff + CAST(@fr AS BIGINT) * 1048576
        EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
    IF @data IS NULL
        THROW 50705, N'размер файлов базы не прочитан — бэкап не начат', 1;
    IF @free IS NULL
        THROW 50706, N'свободное место на томе папки бэкапов не прочитано (папка не на томе файлов баз) — бэкап не начат', 1;
    IF @free < @data * @ff + CAST(@fr AS BIGINT) * 1048576
    BEGIN
        SET @msg = N'мало места на томе папки бэкапов: свободно ' + CAST(@free / 1048576 AS NVARCHAR(20)) + N' МБ, нужно не меньше '
                 + CAST((@data * @ff) / 1048576 + @fr AS NVARCHAR(20)) + N' МБ (данные базы × ' + CAST(@ff AS NVARCHAR(12)) + N' + запас '
                 + CAST(@fr AS NVARCHAR(12)) + N' МБ) — бэкап не начат';
        THROW 50707, @msg, 1;
    END
    INSERT adm.dbbackup (db, file_path, by_login, job_id, data_bytes, free_bytes, run_tag) VALUES (@db, N'', LEFT(@by, 64), @job, @data, @free, @tag);
    SET @id = SCOPE_IDENTITY();
    SET @file = @folder + CASE WHEN RIGHT(@folder, 1) = N'\' THEN N'' ELSE N'\' END + @db + N'_'
              + FORMAT(SYSUTCDATETIME(), 'yyyyMMdd_HHmmss') + N'_' + CAST(@id AS NVARCHAR(10)) + N'.bak';
    SET @name = N'Astory panel #' + CAST(@id AS NVARCHAR(10));
    UPDATE adm.dbbackup SET file_path = @file WHERE id = @id;
    BACKUP DATABASE @db TO DISK = @file WITH COPY_ONLY, CHECKSUM, NOINIT, NOSKIP, NAME = @name, DESCRIPTION = N'Astory admin center (COPY_ONLY)';
    IF @@ERROR <> 0
    BEGIN
        UPDATE adm.dbbackup SET status = 'failed', finished_at = SYSUTCDATETIME(), message = N'BACKUP DATABASE не выполнен (текст ошибки — у вызывающего)'
        WHERE id = @id AND status = 'running';
        EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
        SELECT * FROM adm.dbbackup WHERE id = @id;
        RETURN 1;
    END
    SELECT TOP 1 @pos = b.position, @bsid = b.backup_set_id, @size = CAST(b.backup_size AS BIGINT), @lsn = b.checkpoint_lsn, @chk = b.has_backup_checksums
    FROM msdb.dbo.backupset b JOIN msdb.dbo.backupmediafamily m ON m.media_set_id = b.media_set_id
    WHERE b.database_name = @db AND b.name = @name AND m.physical_device_name = @file ORDER BY b.backup_set_id DESC;
    IF @pos IS NULL
    BEGIN
        UPDATE adm.dbbackup SET status = 'failed', finished_at = SYSUTCDATETIME(), message = N'бэкап записан, но набора в истории msdb нет — проверка не делалась'
        WHERE id = @id AND status = 'running';
        EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
        SELECT * FROM adm.dbbackup WHERE id = @id;
        RETURN 1;
    END
    UPDATE adm.dbbackup SET position = @pos, backup_set_id = @bsid, backup_bytes = @size, checkpoint_lsn = @lsn, finished_at = SYSUTCDATETIME(),
           status = 'done', message = CASE WHEN @chk = 1 THEN N'бэкап записан (COPY_ONLY, CHECKSUM)' ELSE N'бэкап записан, но без контрольных сумм' END
    WHERE id = @id AND status = 'running';
    RESTORE VERIFYONLY FROM DISK = @file WITH FILE = @pos, CHECKSUM;
    IF @@ERROR <> 0
    BEGIN
        UPDATE adm.dbbackup SET verified = 0, verified_at = SYSUTCDATETIME(), message = N'бэкап записан, но RESTORE VERIFYONLY не прошёл'
        WHERE id = @id AND status = 'done';
        EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
        SELECT * FROM adm.dbbackup WHERE id = @id;
        RETURN 1;
    END
    UPDATE adm.dbbackup SET verified = CASE WHEN @chk = 1 THEN 1 ELSE 0 END, verified_at = SYSUTCDATETIME(),
           message = CASE WHEN @chk = 1 THEN N'бэкап записан и проверен (COPY_ONLY, CHECKSUM, VERIFYONLY)' ELSE N'VERIFYONLY прошёл, но контрольных сумм в наборе нет' END
    WHERE id = @id AND status = 'done';
    EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
    SELECT * FROM adm.dbbackup WHERE id = @id;
    RETURN 0;
END
GO

/* Повторная проверка уже сделанного бэкапа панели (файл мог испортиться на диске). */
CREATE PROCEDURE adm.DbBackupVerify @id INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @file NVARCHAR(400), @pos INT, @lk INT;
    SELECT @file = file_path, @pos = position FROM adm.dbbackup WHERE id = @id AND status = 'done' AND position IS NOT NULL;
    IF @file IS NULL
        THROW 50711, N'такого готового бэкапа панели нет (удалён, не завершён или не панели) — проверка не делалась', 1;
    -- ★ ревизия 47 Н-5: перепроверка не идёт параллельно с бэкапом — та же блокировка
    EXEC @lk = sp_getapplock @Resource = N'adm.dbbackup', @LockMode = N'Exclusive', @LockOwner = N'Session', @LockTimeout = 0;
    IF @lk < 0
        THROW 50704, N'уже идёт бэкап или восстановление на сервере — бэкап не начат', 1;
    RESTORE VERIFYONLY FROM DISK = @file WITH FILE = @pos, CHECKSUM;
    IF @@ERROR <> 0
    BEGIN
        UPDATE adm.dbbackup SET verified = 0, verified_at = SYSUTCDATETIME(), message = N'повторная проверка RESTORE VERIFYONLY не прошла' WHERE id = @id;
        EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
        SELECT * FROM adm.dbbackup WHERE id = @id;
        RETURN 1;
    END
    UPDATE adm.dbbackup SET verified = 1, verified_at = SYSUTCDATETIME(), message = N'повторная проверка RESTORE VERIFYONLY прошла' WHERE id = @id;
    EXEC sp_releaseapplock @Resource = N'adm.dbbackup', @LockOwner = N'Session';
    SELECT * FROM adm.dbbackup WHERE id = @id;
    RETURN 0;
END
GO

/* Состояние баз списка: модель восстановления, размеры, последний бэкап ЛЮБОГО инструмента по истории msdb, место на томе папки. Только чтение. */
CREATE PROCEDURE adm.DbBackupState
AS
BEGIN
    SET NOCOUNT ON;
    SELECT l.name AS db, d.state_desc AS state, d.recovery_model_desc AS recovery, d.log_reuse_wait_desc AS log_wait,
           (SELECT SUM(CAST(size AS BIGINT)) * 8192 FROM sys.master_files f WHERE f.database_id = d.database_id AND f.type = 0) AS data_bytes,
           (SELECT SUM(CAST(size AS BIGINT)) * 8192 FROM sys.master_files f WHERE f.database_id = d.database_id AND f.type = 1) AS log_bytes,
           -- ★ ревизия 47 (мелочь 6): местное время набора → UTC по поясу НА МОМЕНТ бэкапа (backupset.time_zone, шаг 15 мин; 127 — неизвестен)
           CASE WHEN lb.tz BETWEEN -56 AND 56 THEN DATEADD(MINUTE, -15 * lb.tz, lb.finish)
                ELSE DATEADD(MINUTE, DATEDIFF(MINUTE, SYSDATETIME(), SYSUTCDATETIME()), lb.finish) END AS any_finish_utc, lb.btype AS any_type, lb.copy_only AS any_copy_only, lb.checksums AS any_checksums, lb.device AS any_device,
           lb.who AS any_user, CAST(lb.size AS BIGINT) AS any_bytes,
           DATEADD(MINUTE, DATEDIFF(MINUTE, SYSDATETIME(), SYSUTCDATETIME()),
                   (SELECT MAX(b.backup_finish_date) FROM msdb.dbo.backupset b WHERE b.database_name = l.name COLLATE DATABASE_DEFAULT AND b.type = 'L')) AS log_backup_utc,
           fr.free_bytes, fr.total_bytes, fr.volume, c.folder
    FROM adm.dbbackup_db l
    CROSS JOIN adm.dbbackup_cfg c
    LEFT JOIN sys.databases d ON d.name = l.name COLLATE DATABASE_DEFAULT
    OUTER APPLY (SELECT TOP 1 b.backup_finish_date AS finish, b.type AS btype, b.is_copy_only AS copy_only, b.has_backup_checksums AS checksums,
                        m.physical_device_name AS device, b.user_name AS who, b.backup_size AS size, CAST(b.time_zone AS INT) AS tz
                 FROM msdb.dbo.backupset b JOIN msdb.dbo.backupmediafamily m ON m.media_set_id = b.media_set_id
                 WHERE b.database_name = l.name COLLATE DATABASE_DEFAULT AND b.type = 'D' ORDER BY b.backup_finish_date DESC) lb
    OUTER APPLY adm.DbBackupFree() fr
    WHERE c.id = 1
    ORDER BY l.name;
END
GO

/* Отметки службы (без подписи: только своя таблица): md5 / длина / снимок строк после бэкапа; удаление файла ротацией; итог стенда. */
CREATE OR ALTER PROCEDURE adm.DbBackupMark @id INT, @md5 CHAR(32), @bytes BIGINT, @counts NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    IF @md5 IS NOT NULL AND @md5 NOT LIKE REPLICATE('[0-9a-f]', 32)
        THROW 50721, N'md5 — 32 знака 0-9a-f', 1;
    UPDATE adm.dbbackup SET md5 = COALESCE(md5, @md5), file_bytes = COALESCE(file_bytes, @bytes), counts = COALESCE(counts, @counts)
    OUTPUT INSERTED.id WHERE id = @id AND status = 'done';
END
GO
CREATE OR ALTER PROCEDURE adm.DbBackupDeleted @id INT, @by NVARCHAR(64), @why NVARCHAR(400)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.dbbackup SET status = 'deleted', deleted_at = SYSUTCDATETIME(), deleted_by = LEFT(@by, 64), deleted_why = LEFT(@why, 400)
    OUTPUT INSERTED.id WHERE id = @id AND status IN ('done', 'failed');
END
GO
CREATE OR ALTER PROCEDURE adm.DbBackupStand @id INT, @ok BIT, @result NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.dbbackup SET stand_at = SYSUTCDATETIME(), stand_ok = @ok, stand_result = @result OUTPUT INSERTED.id WHERE id = @id;
END
GO

/* ---------- подпись: сертификат в AsdaAdmin (закрытый ключ — только на время подписи), открытая часть — в master, логин из неё ---------- */
DECLARE @pw NVARCHAR(200) = CONVERT(NVARCHAR(36), NEWID()) + N'Aa1!' + CONVERT(NVARCHAR(36), NEWID()) + CONVERT(NVARCHAR(36), NEWID());
DECLARE @q NVARCHAR(MAX);
SET @q = N'CREATE CERTIFICATE adm_dbbackup_cert ENCRYPTION BY PASSWORD = ' + QUOTENAME(@pw, '''')
       + N' WITH SUBJECT = N''Astory admin center: DB backup procedures (A5.7)'', EXPIRY_DATE = ''20991231'';';   -- ГГГГММДД: ''2099-12-31'' у русского входа (dmy) — ошибка 190 (выкладка 21.11)
EXEC (@q);
SET @q = N'ADD SIGNATURE TO adm.DbBackupRun BY CERTIFICATE adm_dbbackup_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';'
       + N'ADD SIGNATURE TO adm.DbBackupVerify BY CERTIFICATE adm_dbbackup_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';'
       + N'ADD SIGNATURE TO adm.DbBackupState BY CERTIFICATE adm_dbbackup_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';'
       + N'ADD SIGNATURE TO adm.DbBackupAbort BY CERTIFICATE adm_dbbackup_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';'
       + N'ADD SIGNATURE TO adm.DbBackupBusy BY CERTIFICATE adm_dbbackup_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';';
EXEC (@q);
ALTER CERTIFICATE adm_dbbackup_cert REMOVE PRIVATE KEY;
SET @pw = NULL;
DECLARE @pub VARBINARY(MAX) = CERTENCODED(CERT_ID(N'adm_dbbackup_cert'));
SET @q = N'CREATE CERTIFICATE adm_dbbackup_cert FROM BINARY = ' + CONVERT(NVARCHAR(MAX), @pub, 1) + N';';
EXEC master.sys.sp_executesql @q;
/* RESTORE VERIFYONLY требует CREATE DATABASE; сам код процедур баз не создаёт */
EXEC master.sys.sp_executesql N'CREATE LOGIN adm_dbbackup_signer FROM CERTIFICATE adm_dbbackup_cert;
GRANT VIEW SERVER STATE TO adm_dbbackup_signer; GRANT CREATE ANY DATABASE TO adm_dbbackup_signer;';
GO
/* пользователь логина подписи: в каждой базе списка — db_backupoperator (BACKUP DATABASE / LOG / CHECKPOINT — процедура делает только
   BACKUP DATABASE … COPY_ONLY), в msdb — SELECT истории бэкапов */
DECLARE @d SYSNAME, @q NVARCHAR(MAX);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT l.name FROM adm.dbbackup_db l JOIN sys.databases d ON d.name = l.name COLLATE DATABASE_DEFAULT WHERE d.state_desc = 'ONLINE';
OPEN c; FETCH c INTO @d;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @q = N'EXEC ' + QUOTENAME(@d) + N'.sys.sp_executesql @s';
    EXEC sys.sp_executesql @q, N'@s NVARCHAR(MAX)',
        N'CREATE USER adm_dbbackup_u FOR LOGIN adm_dbbackup_signer; ALTER ROLE db_backupoperator ADD MEMBER adm_dbbackup_u;';
    FETCH c INTO @d;
END
CLOSE c; DEALLOCATE c;
EXEC msdb.sys.sp_executesql N'CREATE USER adm_dbbackup_u FOR LOGIN adm_dbbackup_signer; GRANT SELECT ON dbo.backupset TO adm_dbbackup_u; GRANT SELECT ON dbo.backupmediafamily TO adm_dbbackup_u;';
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.dbbackup TO [asda_admin];
    GRANT SELECT ON adm.dbbackup_cfg TO [asda_admin];
    GRANT SELECT ON adm.dbbackup_db TO [asda_admin];
    DENY INSERT, UPDATE, DELETE ON adm.dbbackup TO [asda_admin];
    DENY INSERT, UPDATE, DELETE ON adm.dbbackup_cfg TO [asda_admin];
    DENY INSERT, UPDATE, DELETE ON adm.dbbackup_db TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupRun TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupVerify TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupState TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupAbort TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupMark TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupDeleted TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupStand TO [asda_admin];
    GRANT EXECUTE ON adm.DbBackupBusy TO [asda_admin];          -- ★ ревизия 47: признак «идёт» / «зависла» для предпросмотра (только чтение)
    GRANT EXECUTE ON adm.DbBackupUnlock TO [asda_admin];        -- ★ ревизия 47 С-1: снять СВОЮ блокировку после обрыва запроса
END
GO
PRINT 'adminc_16_dbbackup: OK';
