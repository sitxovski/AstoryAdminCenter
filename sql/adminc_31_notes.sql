-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_31_notes.sql — «Заметки к выпуску»: changelog для игроков (шаг А7.7, 24.11.2026; решение владельца А7 №7 — черновик заметок для
   игроков в панели и публикация кнопкой; №2 — тексты EN / RU / AR пишутся руками, канал и роль выбираются; domains/notes.py, web/notes.js;
   отчёт Reports/admin_center/impl_a7_releases_20261123.md §А7.7).
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin -x -I) ПОСЛЕ adminc_28_outbox и adminc_29_telegram (в CK_adm_Outbox_route — вид 'notes').
   Тот же файл самотест выполняет на LocalDB (пользователей asda_admin / asda_reports там может не быть — выдача прав пропускается). Повторный
   запуск безопасен.

   ОТКУДА ТЕКСТ. Changelog лежит на ПК владельца (Docs\Changelog, файлы только дописываются). Консоль ПК (asda_admin.py notes push или
   задание ПК notes.push) читает текущий файл и пишет его как есть в adm.NotesSnap логином asda_admin по VPN — тем же путём, что снимок выпуска
   А7.1 (adm.ReleasePcStatus). SMB не используется. Тот же md5 и файл, что у последней строки, — только отметка «ПК присылал». Разбор записей —
   в панели (domains/notes.py). Панель changelog не пишет: ни файла на ПК, ни снимка (снимок пишет только консоль ПК).
   ТАБЛИЦЫ
     adm.NotesSnap      — снимки changelog с ПК (имя файла, текст, md5, машина, кто, когда). Хранятся последние 30 разных (adm.NotesSnapPut).
     adm.NotesDraft     — один черновик заметок (строка id = 1): JSON полей формы (отмеченные записи, заголовок ветки, тексты EN / RU / AR, роль,
                          срок). Пишет adm.NotesDraftSet.
     adm.NotesPost      — публикация заметок: kind 'discord' — запись очереди adm.Outbox (kind 'notes', форум updates); kind 'manual' — отметка
                          «уже опубликовано вне панели» (с причиной, снимается откатом: revoked_utc).
     adm.NotesPostEntry — какие записи changelog вошли в публикацию: устойчивый ключ записи (16 hex, правило ключа — domains/notes.py key_text:
                          нормализованный заголовок без меток и скобок статуса, ★ р83), дата и заголовок (для экрана).
   ЧТО СЧИТАЕТСЯ «ОПУБЛИКОВАНО» (по итогу бота, а не по постановке в очередь): запись changelog опубликована, если она входит в
     * отметку 'manual', которую не сняли, или
     * публикацию 'discord', у которой запись очереди НЕ проверочная, статус 2 «опубликовано» и сообщение не удалено (del_status <> 2).
     «Занята» (второй раз в публикацию не берётся): опубликована, или её запись очереди ждёт бота / бот взял (статусы 0, 1, 7), или «итог
     неизвестен» (статус 3 с текстом бота «итог неизвестен» / «проверьте канал», ★ р82). Точная ошибка, отменено, просрочено, удалено из Discord,
     проверочная — свободна.
   ★ РЕВИЗИЯ 82 (24.11): реестр записей adm.NotesEntry — записи changelog живут в базе постоянно (не только последний снимок): неопубликованная
     запись прежнего файла видна, пока её не опубликуют или не скроют (adm.NotesEntryHide); ключ — нормализованный заголовок + дата
     (без меток […] и пометок «перенесено …»), прежние ключи публикаций переводятся на новые (adm.NotesEntrySync, @v1). Ошибка публикации
     освобождает записи сразу; «итог неизвестен» держит их, пока оператор не решит «ветки нет» (adm.NotesOutboxClose) или «ветка есть»
     (отметка вне панели); повтор записи очереди вида notes запрещён (adm.OutboxRetry, adminc_28) — повтор = новая публикация. Заголовок
     ветки за сутки не повторяется (код 7): бот ищет свою прерванную ветку по имени.
   ★ РЕВИЗИЯ 83 (24.11): имя ветки занято и записью, которую бот брал, а потом её закрыли (статус 4 / 5 с claimed_utc) — та же проверка и в
     adm.OutboxPut для updates (код 5); у реестра второй признак what_hash («Что стало»); у снимка отметка полноты реестра (reg_count,
     reg_done_utc — adm.NotesSnapDone последним шагом); «ветки нет» по «бот взял» — только после срока годности записи или отчёта бота по
     другим записям (adm.NotesOutboxClose @exists = 0).
   ★ РЕВИЗИЯ 84 (24.11): у записи публикации хранится хэш «Что стало» на момент публикации (NotesPostEntry.what_hash; прежние строки — из реестра).
     Тот же ключ, но другой хэш — запись не «опубликована», а «похожа на опубликованное» (и не занята в adm.NotesEntryPut); реестр не
     перезаписывает текст опубликованной записи текстом другой с тем же ключом. Отметка полноты реестра сбрасывается в начале push / resync
     (adm.NotesSnapDone @n = NULL).
   ПРЕДЕЛЫ (adm.NotesPublishPut, код итога): общие с adm.OutboxPut — 1 больше 6 в час · 2 больше 30 в сутки · 3 больше 10 проверочных в час ·
     4 неверные поля; 5 — запись changelog уже опубликована или в очереди (adm.NotesEntryPut) · 6 — публикации нет или она не той природы ·
     7 — ветка с таким заголовком за сутки уже была (★ р82 М-3).
   ПРАВА
     asda_admin (панель): SELECT пяти таблиц; EXECUTE adm.NotesSnapPut / NotesDraftSet / NotesPublishPut / NotesMarkPut / NotesEntryPut /
                          NotesMarkRevoke / NotesEntrySync / NotesEntryHide / NotesOutboxClose; прямой записи нет (DENY INSERT / UPDATE / DELETE).
     asda_reports (бот): ничего — DENY таблиц и процедур (бот видит запись очереди только через adm.OutboxClaim, как любую другую).
   Проверка прав бота — adminc_31_notes_verify.sql ПОД asda_reports; панели — adminc_10_verify.sql. Откат — adminc_99_rollback.sql.
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (урок adminc_14). Совместимость с уровнем 100: без THROW, IIF, CONCAT,
   TRY_CONVERT, FORMAT, STRING_SPLIT, CREATE OR ALTER; даты — литералами ГГГГММДД. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'adm.Outbox', N'U') IS NULL
    RAISERROR(N'adminc_31: нет adm.Outbox — сначала adminc_28_outbox.sql и adminc_29_telegram.sql', 16, 1);
GO
/* ─────────────── снимки changelog с ПК ─────────────── */
IF OBJECT_ID(N'adm.NotesSnap') IS NULL
CREATE TABLE adm.NotesSnap (
    id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_NotesSnap PRIMARY KEY,
    file_name      NVARCHAR(80)   NOT NULL CONSTRAINT CK_adm_NotesSnap_file CHECK (file_name LIKE N'CHANGELOG[_]%.md' AND file_name NOT LIKE N'%[\/:]%'),
    payload        NVARCHAR(MAX)  NOT NULL,
    payload_md5    CHAR(32)       NOT NULL,
    host           NVARCHAR(64)   NOT NULL,
    pushed_by      NVARCHAR(32)   NOT NULL,
    collected_utc  DATETIME2(0)   NOT NULL,
    pushed_utc     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotesSnap_pushed DEFAULT (SYSUTCDATETIME()),
    seen_utc       DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotesSnap_seen DEFAULT (SYSUTCDATETIME()),
    seen_count     INT            NOT NULL CONSTRAINT DF_adm_NotesSnap_count DEFAULT (1),
    CONSTRAINT CK_adm_NotesSnap_size CHECK (LEN(payload) BETWEEN 1 AND 4000000),
    CONSTRAINT CK_adm_NotesSnap_md5 CHECK (payload_md5 NOT LIKE '%[^0-9a-f]%' AND LEN(payload_md5) = 32),
    CONSTRAINT CK_adm_NotesSnap_count CHECK (seen_count >= 1)
);
GO
-- ★ р83 М-4: отметка «реестр по снимку записан целиком» (число записей и время) — пишет adm.NotesSnapDone последним шагом push / resync
IF COL_LENGTH(N'adm.NotesSnap', N'reg_count') IS NULL ALTER TABLE adm.NotesSnap ADD reg_count INT NULL;
IF COL_LENGTH(N'adm.NotesSnap', N'reg_done_utc') IS NULL ALTER TABLE adm.NotesSnap ADD reg_done_utc DATETIME2(0) NULL;
GO
/* ─────────────── черновик (одна строка) ─────────────── */
IF OBJECT_ID(N'adm.NotesDraft') IS NULL
CREATE TABLE adm.NotesDraft (
    id           TINYINT        NOT NULL CONSTRAINT PK_adm_NotesDraft PRIMARY KEY CONSTRAINT CK_adm_NotesDraft_one CHECK (id = 1),
    payload      NVARCHAR(MAX)  NOT NULL CONSTRAINT CK_adm_NotesDraft_size CHECK (LEN(payload) BETWEEN 2 AND 100000),
    snap_id      INT            NULL,
    changed_by   NVARCHAR(32)   NOT NULL,
    changed_utc  DATETIME2(0)   NOT NULL
);
GO
/* ─────────────── публикации и их записи ─────────────── */
IF OBJECT_ID(N'adm.NotesPost') IS NULL
CREATE TABLE adm.NotesPost (
    id           INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_NotesPost PRIMARY KEY,
    kind         VARCHAR(8)     NOT NULL CONSTRAINT CK_adm_NotesPost_kind CHECK (kind IN ('discord', 'manual')),
    outbox_id    INT            NULL CONSTRAINT FK_adm_NotesPost_outbox REFERENCES adm.Outbox (id),
    is_test      BIT            NOT NULL CONSTRAINT DF_adm_NotesPost_test DEFAULT (0),
    snap_id      INT            NULL,
    title        NVARCHAR(100)  NOT NULL,
    note         NVARCHAR(200)  NULL,
    created_by   NVARCHAR(32)   NOT NULL,
    created_utc  DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotesPost_created DEFAULT (SYSUTCDATETIME()),
    revoked_by   NVARCHAR(32)   NULL,
    revoked_utc  DATETIME2(0)   NULL,
    CONSTRAINT CK_adm_NotesPost_shape CHECK ((kind = 'discord' AND outbox_id IS NOT NULL AND revoked_utc IS NULL)
                                          OR (kind = 'manual' AND outbox_id IS NULL AND is_test = 0 AND LEN(ISNULL(note, N'')) >= 3))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_NotesPost_outbox' AND object_id = OBJECT_ID(N'adm.NotesPost'))
    CREATE INDEX IX_adm_NotesPost_outbox ON adm.NotesPost (outbox_id);
GO
IF OBJECT_ID(N'adm.NotesPostEntry') IS NULL
CREATE TABLE adm.NotesPostEntry (
    post_id      INT            NOT NULL CONSTRAINT FK_adm_NotesPostEntry_post REFERENCES adm.NotesPost (id),
    entry_key    CHAR(16)       NOT NULL CONSTRAINT CK_adm_NotesPostEntry_key CHECK (entry_key NOT LIKE '%[^0-9a-f]%' AND LEN(entry_key) = 16),
    entry_date   VARCHAR(10)    NOT NULL,
    entry_title  NVARCHAR(200)  NOT NULL,
    CONSTRAINT PK_adm_NotesPostEntry PRIMARY KEY (post_id, entry_key)
);
GO
-- ★ р84 М-1: хэш «Что стало» на момент публикации (заполняет adm.NotesEntryPut; прежние строки — из реестра, ниже после adm.NotesEntry)
IF COL_LENGTH(N'adm.NotesPostEntry', N'what_hash') IS NULL ALTER TABLE adm.NotesPostEntry ADD what_hash CHAR(16) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_NotesPostEntry_key' AND object_id = OBJECT_ID(N'adm.NotesPostEntry'))
    CREATE INDEX IX_adm_NotesPostEntry_key ON adm.NotesPostEntry (entry_key, post_id);
GO
/* ─────────────── ★ р82 В-2: реестр записей changelog (постоянный, по ключу) ─────────────── */
IF OBJECT_ID(N'adm.NotesEntry') IS NULL
CREATE TABLE adm.NotesEntry (
    entry_key    CHAR(16)       NOT NULL CONSTRAINT PK_adm_NotesEntry PRIMARY KEY
                                CONSTRAINT CK_adm_NotesEntry_key CHECK (entry_key NOT LIKE '%[^0-9a-f]%' AND LEN(entry_key) = 16),
    entry_date   VARCHAR(10)    NOT NULL,
    title        NVARCHAR(200)  NOT NULL,
    area         VARCHAR(8)     NOT NULL CONSTRAINT CK_adm_NotesEntry_area CHECK (area IN ('client', 'server', 'release', 'clarify', 'service')),
    status       VARCHAR(12)    NOT NULL,
    rel          VARCHAR(40)    NULL,
    sens         NVARCHAR(300)  NULL,
    ru           NVARCHAR(MAX)  NULL,
    body         NVARCHAR(MAX)  NULL,
    file_name    NVARCHAR(80)   NOT NULL,
    first_snap   INT            NOT NULL,
    last_snap    INT            NOT NULL,
    first_utc    DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotesEntry_first DEFAULT (SYSUTCDATETIME()),
    last_utc     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotesEntry_last DEFAULT (SYSUTCDATETIME()),
    hidden_by    NVARCHAR(32)   NULL,
    hidden_utc   DATETIME2(0)   NULL,
    hidden_note  NVARCHAR(200)  NULL
);
GO
-- ★ р83 В-1: второй признак записи — хэш нормализованного «Что стало» (запись с другим ключом и тем же «Что стало» — «похоже на опубликованное»)
IF COL_LENGTH(N'adm.NotesEntry', N'what_hash') IS NULL ALTER TABLE adm.NotesEntry ADD what_hash CHAR(16) NULL;
GO
-- ★ р84 М-1: перенос для строк публикаций до ревизии 84 — хэш из реестра (повторный прогон ничего не меняет: только NULL)
UPDATE e SET what_hash = n.what_hash FROM adm.NotesPostEntry e JOIN adm.NotesEntry n ON n.entry_key = e.entry_key
WHERE e.what_hash IS NULL AND n.what_hash IS NOT NULL;
GO
/* ─────────────── ПК: записать снимок changelog (тот же файл и md5 — только отметка; хранится 30 последних) ─────────────── */
IF OBJECT_ID(N'adm.NotesSnapPut', N'P') IS NOT NULL DROP PROCEDURE adm.NotesSnapPut;
GO
CREATE PROCEDURE adm.NotesSnapPut
    @file NVARCHAR(80), @payload NVARCHAR(MAX), @md5 CHAR(32), @host NVARCHAR(64), @by NVARCHAR(32), @collected DATETIME2(0),
    @id INT OUTPUT, @new BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @last INT, @lmd5 CHAR(32), @lfile NVARCHAR(80);
    BEGIN TRAN;
    SELECT TOP 1 @last = id, @lmd5 = payload_md5, @lfile = file_name FROM adm.NotesSnap WITH (UPDLOCK, HOLDLOCK) ORDER BY id DESC;
    IF @last IS NOT NULL AND @lmd5 = @md5 AND @lfile = @file
    BEGIN
        UPDATE adm.NotesSnap SET seen_utc = SYSUTCDATETIME(), seen_count = seen_count + 1 WHERE id = @last;
        SET @id = @last; SET @new = 0;
    END
    ELSE
    BEGIN
        INSERT adm.NotesSnap (file_name, payload, payload_md5, host, pushed_by, collected_utc)
        VALUES (@file, @payload, @md5, LEFT(ISNULL(@host, N''), 64), LEFT(ISNULL(@by, N''), 32), @collected);
        SET @id = SCOPE_IDENTITY(); SET @new = 1;
        -- хранить 30 последних снимков, кроме тех, на которые ссылаются публикации (по ним видно, из какого текста публиковали)
        DELETE FROM adm.NotesSnap WHERE id NOT IN (SELECT TOP (30) id FROM adm.NotesSnap ORDER BY id DESC)
            AND id NOT IN (SELECT snap_id FROM adm.NotesPost WHERE snap_id IS NOT NULL)
            AND id NOT IN (SELECT snap_id FROM adm.NotesDraft WHERE snap_id IS NOT NULL);
    END
    COMMIT;
END
GO
/* ─────────────── панель: черновик ─────────────── */
IF OBJECT_ID(N'adm.NotesDraftSet', N'P') IS NOT NULL DROP PROCEDURE adm.NotesDraftSet;
GO
CREATE PROCEDURE adm.NotesDraftSet @payload NVARCHAR(MAX), @snap_id INT, @by NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRAN;
    IF EXISTS (SELECT 1 FROM adm.NotesDraft WITH (UPDLOCK, HOLDLOCK) WHERE id = 1)
        UPDATE adm.NotesDraft SET payload = @payload, snap_id = @snap_id, changed_by = LEFT(@by, 32), changed_utc = SYSUTCDATETIME() WHERE id = 1;
    ELSE
        INSERT adm.NotesDraft (id, payload, snap_id, changed_by, changed_utc) VALUES (1, @payload, @snap_id, LEFT(@by, 32), SYSUTCDATETIME());
    COMMIT;
    SELECT 1 AS n;
END
GO
/* ─────────────── панель: публикация заметок — запись очереди (kind notes, форум updates) + публикация ─────────────── */
IF OBJECT_ID(N'adm.NotesPublishPut', N'P') IS NOT NULL DROP PROCEDURE adm.NotesPublishPut;
GO
CREATE PROCEDURE adm.NotesPublishPut
    @title NVARCHAR(200), @en NVARCHAR(2000), @ru NVARCHAR(2000), @ar NVARCHAR(2000), @role VARCHAR(16), @ttl_min INT, @by NVARCHAR(32),
    @test BIT, @snap_id INT, @id INT OUTPUT, @post INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @id = NULL; SET @post = NULL; SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    SET @test = ISNULL(@test, 0);
    SET @title = LTRIM(RTRIM(ISNULL(@title, N''))); SET @en = LTRIM(RTRIM(ISNULL(@en, N'')));
    SET @ru = NULLIF(LTRIM(RTRIM(ISNULL(@ru, N''))), N''); SET @ar = NULLIF(LTRIM(RTRIM(ISNULL(@ar, N''))), N'');
    IF @role = '' SET @role = NULL;
    IF (@role IS NOT NULL AND @role <> 'patch')
       OR LEN(@title) < 1 OR LEN(@title) > 100 OR LEN(@en) < 1 OR LEN(@en) > 1800 OR LEN(ISNULL(@ru, N'')) > 1800 OR LEN(ISNULL(@ar, N'')) > 1800
       OR @ttl_min IS NULL OR @ttl_min < 5 OR @ttl_min > 1440 OR LEN(ISNULL(@by, N'')) < 1
       OR (@title + N' ' + @en + N' ' + ISNULL(@ru, N'') + N' ' + ISNULL(@ar, N'')) LIKE N'%@everyone%'
       OR (@title + N' ' + @en + N' ' + ISNULL(@ru, N'') + N' ' + ISNULL(@ar, N'')) LIKE N'%@here%'
    BEGIN
        SET @code = 4; RETURN;
    END
    BEGIN TRAN;
    DECLARE @lk INT;
    -- тот же замок, что у adm.OutboxPut: пределы частоты общие для всех записей Discord; держится до фиксации внешней транзакции панели
    EXEC @lk = sp_getapplock @Resource = N'adm.OutboxPut', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0
    BEGIN
        ROLLBACK; RAISERROR(N'очередь исходящих занята, повторите через минуту', 16, 1); RETURN;
    END
    IF @test = 0 AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'discord' AND is_test = 0 AND created_utc > DATEADD(HOUR, -1, @now)) >= 6
        SET @code = 1;
    ELSE IF @test = 0 AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'discord' AND is_test = 0 AND created_utc > DATEADD(DAY, -1, @now)) >= 30
        SET @code = 2;
    ELSE IF @test = 1 AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'discord' AND is_test = 1 AND created_utc > DATEADD(HOUR, -1, @now)) >= 10
        SET @code = 3;
    -- ★ р82 М-3: бот ищет свою прерванную ветку по имени — имя ветки в форуме updates за сутки не повторяется (отменённое и просроченное не в счёт)
    ELSE IF @test = 0 AND EXISTS (SELECT 1 FROM adm.Outbox WHERE transport = 'discord' AND channel_key = 'updates' AND is_test = 0 AND title = @title
                                  AND NOT (status IN (4, 5) AND claimed_utc IS NULL) AND created_utc > DATEADD(DAY, -1, @now))   -- ★ р83 М-2
        SET @code = 7;
    ELSE
    BEGIN
        INSERT adm.Outbox (kind, channel_key, role_key, title, text_en, text_ru, text_ar, is_test, created_utc, created_by, expires_utc, status)
        VALUES ('notes', 'updates', @role, @title, @en, @ru, @ar, @test, @now, LEFT(@by, 32), DATEADD(MINUTE, @ttl_min, @now), 0);
        SET @id = SCOPE_IDENTITY();
        INSERT adm.NotesPost (kind, outbox_id, is_test, snap_id, title, created_by, created_utc) VALUES ('discord', @id, @test, @snap_id, @title, LEFT(@by, 32), @now);
        SET @post = SCOPE_IDENTITY();
        SET @code = 0;
    END
    COMMIT;
END
GO
/* ─────────────── панель: отметка «уже опубликовано вне панели» (без Discord) ─────────────── */
IF OBJECT_ID(N'adm.NotesMarkPut', N'P') IS NOT NULL DROP PROCEDURE adm.NotesMarkPut;
GO
CREATE PROCEDURE adm.NotesMarkPut @note NVARCHAR(200), @by NVARCHAR(32), @snap_id INT, @post INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @post = NULL; SET @code = NULL;
    SET @note = LTRIM(RTRIM(ISNULL(@note, N'')));
    IF LEN(@note) < 3 OR LEN(ISNULL(@by, N'')) < 1
    BEGIN
        SET @code = 4; RETURN;
    END
    BEGIN TRAN;
    DECLARE @lk INT;
    EXEC @lk = sp_getapplock @Resource = N'adm.OutboxPut', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0
    BEGIN
        ROLLBACK; RAISERROR(N'очередь исходящих занята, повторите через минуту', 16, 1); RETURN;
    END
    INSERT adm.NotesPost (kind, outbox_id, is_test, snap_id, title, note, created_by) VALUES ('manual', NULL, 0, @snap_id, N'(вне панели)', @note, LEFT(@by, 32));
    SET @post = SCOPE_IDENTITY();
    SET @code = 0;
    COMMIT;
END
GO
/* ─────────────── панель: запись changelog в публикацию (в той же транзакции, под тем же замком) ─────────────── */
IF OBJECT_ID(N'adm.NotesEntryPut', N'P') IS NOT NULL DROP PROCEDURE adm.NotesEntryPut;
GO
CREATE PROCEDURE adm.NotesEntryPut @post INT, @key CHAR(16), @date VARCHAR(10), @title NVARCHAR(200), @code INT OUTPUT, @what CHAR(16) = NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME(), @ptest BIT;
    SELECT @ptest = is_test FROM adm.NotesPost WHERE id = @post AND revoked_utc IS NULL;
    IF @ptest IS NULL
    BEGIN
        SET @code = 6; RETURN;
    END
    IF @key IS NULL OR LEN(@key) <> 16 OR @key LIKE '%[^0-9a-f]%' OR LEN(ISNULL(@title, N'')) < 1
    BEGIN
        SET @code = 4; RETURN;
    END
    -- проверочная публикация никого не занимает и не проверяется на «занято»: бот её не публикует
    IF @ptest = 0 AND EXISTS (
        SELECT 1 FROM adm.NotesPostEntry e
        JOIN adm.NotesPost p ON p.id = e.post_id
        LEFT JOIN adm.Outbox o ON o.id = p.outbox_id
        WHERE e.entry_key = @key AND p.id <> @post AND p.is_test = 0 AND (
              -- опубликовано — занято, только если «Что стало» то же (★ р84 М-1: другой хэш — «похоже», решает оператор)
              (((p.kind = 'manual' AND p.revoked_utc IS NULL) OR (p.kind = 'discord' AND o.is_test = 0 AND o.status = 2 AND ISNULL(o.del_status, 9) <> 2))
               AND (e.what_hash IS NULL OR @what IS NULL OR e.what_hash = @what))
           OR (p.kind = 'discord' AND o.is_test = 0 AND (
                   o.status IN (0, 1, 7)
                -- ★ р82 М-2: ошибка освобождает сразу, «итог неизвестен» держит, пока оператор не решит
                OR (o.status = 3 AND (o.error LIKE N'%итог неизвестен%' OR o.error LIKE N'%проверьте канал%'))))))
    BEGIN
        SET @code = 5; RETURN;
    END
    INSERT adm.NotesPostEntry (post_id, entry_key, entry_date, entry_title, what_hash) VALUES (@post, @key, LEFT(ISNULL(@date, ''), 10), LEFT(@title, 200), @what);
    SET @code = 0;
END
GO
/* ─────────────── панель: снять отметку «опубликовано вне панели» (откат notes.mark) ─────────────── */
IF OBJECT_ID(N'adm.NotesMarkRevoke', N'P') IS NOT NULL DROP PROCEDURE adm.NotesMarkRevoke;
GO
CREATE PROCEDURE adm.NotesMarkRevoke @post INT, @by NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.NotesPost SET revoked_by = LEFT(@by, 32), revoked_utc = SYSUTCDATETIME() WHERE id = @post AND kind = 'manual' AND revoked_utc IS NULL;
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── ★ р82 В-2: реестр — записать / обновить запись, перевести ключ прежней публикации (@v1 → @key) ─────────────── */
IF OBJECT_ID(N'adm.NotesEntrySync', N'P') IS NOT NULL DROP PROCEDURE adm.NotesEntrySync;
GO
CREATE PROCEDURE adm.NotesEntrySync
    @key CHAR(16), @v1 CHAR(16), @date VARCHAR(10), @title NVARCHAR(200), @area VARCHAR(8), @status VARCHAR(12), @rel VARCHAR(40),
    @sens NVARCHAR(300), @ru NVARCHAR(MAX), @body NVARCHAR(MAX), @file NVARCHAR(80), @snap INT, @what CHAR(16) = NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRAN;
    -- ★ р84 М-1: тот же ключ опубликован с другим «Что стало», а с этим — нет: текст прежней опубликованной записи не перезаписывается
    DECLARE @keep BIT = 0;
    IF @what IS NOT NULL AND EXISTS (SELECT 1 FROM adm.NotesPostEntry e JOIN adm.NotesPost p ON p.id = e.post_id LEFT JOIN adm.Outbox o ON o.id = p.outbox_id
                                     WHERE e.entry_key = @key AND p.is_test = 0 AND ((p.kind = 'manual' AND p.revoked_utc IS NULL) OR (p.kind = 'discord' AND o.is_test = 0 AND o.status = 2 AND ISNULL(o.del_status, 9) <> 2)) AND e.what_hash IS NOT NULL AND e.what_hash <> @what)
       AND NOT EXISTS (SELECT 1 FROM adm.NotesPostEntry e JOIN adm.NotesPost p ON p.id = e.post_id LEFT JOIN adm.Outbox o ON o.id = p.outbox_id
                       WHERE e.entry_key = @key AND p.is_test = 0 AND ((p.kind = 'manual' AND p.revoked_utc IS NULL) OR (p.kind = 'discord' AND o.is_test = 0 AND o.status = 2 AND ISNULL(o.del_status, 9) <> 2)) AND (e.what_hash IS NULL OR e.what_hash = @what))
        SET @keep = 1;
    IF @keep = 1
        UPDATE adm.NotesEntry SET last_snap = @snap, last_utc = SYSUTCDATETIME() WHERE entry_key = @key;
    ELSE IF EXISTS (SELECT 1 FROM adm.NotesEntry WITH (UPDLOCK, HOLDLOCK) WHERE entry_key = @key)
        UPDATE adm.NotesEntry SET entry_date = ISNULL(@date, ''), title = LEFT(@title, 200), area = @area, status = LEFT(@status, 12), rel = @rel,
               sens = @sens, ru = @ru, body = @body, file_name = @file, last_snap = @snap, last_utc = SYSUTCDATETIME(), what_hash = @what
        WHERE entry_key = @key;
    ELSE
        INSERT adm.NotesEntry (entry_key, entry_date, title, area, status, rel, sens, ru, body, file_name, first_snap, last_snap, what_hash)
        VALUES (@key, ISNULL(@date, ''), LEFT(@title, 200), @area, LEFT(@status, 12), @rel, @sens, @ru, @body, @file, @snap, @snap, @what);
    -- перевод ключа: записи публикаций, сохранённые по прежней формуле ключа (v1), получают новый ключ
    IF @v1 IS NOT NULL AND @v1 <> @key
        UPDATE e SET entry_key = @key FROM adm.NotesPostEntry e
        WHERE e.entry_key = @v1 AND NOT EXISTS (SELECT 1 FROM adm.NotesPostEntry x WHERE x.post_id = e.post_id AND x.entry_key = @key);
    -- ★ р83 В-1: строка реестра прежнего ключа той же записи сливается с новой (скрытие переходит) и удаляется — иначе она висела бы
    --   «записью прежнего файла»
    IF @v1 IS NOT NULL AND @v1 <> @key AND EXISTS (SELECT 1 FROM adm.NotesEntry WHERE entry_key = @v1)
    BEGIN
        UPDATE n SET hidden_by = o.hidden_by, hidden_utc = o.hidden_utc, hidden_note = o.hidden_note, first_snap = o.first_snap, first_utc = o.first_utc
        FROM adm.NotesEntry n JOIN adm.NotesEntry o ON o.entry_key = @v1 WHERE n.entry_key = @key AND n.hidden_utc IS NULL;
        DELETE FROM adm.NotesEntry WHERE entry_key = @v1;
    END
    COMMIT;
    SELECT 1 AS n;
END
GO
/* ─────────────── ★ р82 В-2: скрыть / вернуть запись реестра (запись без публикации уходит из черновика) ─────────────── */
IF OBJECT_ID(N'adm.NotesEntryHide', N'P') IS NOT NULL DROP PROCEDURE adm.NotesEntryHide;
GO
CREATE PROCEDURE adm.NotesEntryHide @key CHAR(16), @hide BIT, @by NVARCHAR(32), @note NVARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;
    IF @hide = 1
        UPDATE adm.NotesEntry SET hidden_by = LEFT(@by, 32), hidden_utc = SYSUTCDATETIME(), hidden_note = LEFT(@note, 200)
        WHERE entry_key = @key AND hidden_utc IS NULL;
    ELSE
        UPDATE adm.NotesEntry SET hidden_by = NULL, hidden_utc = NULL, hidden_note = NULL WHERE entry_key = @key AND hidden_utc IS NOT NULL;
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── ★ р82 М-2: закрыть запись очереди заметок в ошибке или «итог неизвестен» (статус 4 с пометкой оператора) ─────────────── */
IF OBJECT_ID(N'adm.NotesOutboxClose', N'P') IS NOT NULL DROP PROCEDURE adm.NotesOutboxClose;
GO
CREATE PROCEDURE adm.NotesOutboxClose @id INT, @by NVARCHAR(32), @note NVARCHAR(400), @stuck_min INT, @exists BIT = 0
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    -- ★ р83 М-7: «бот взял» закрывается решением «ветки нет» только если бот точно не держит захват: срок годности прошёл или бот после захвата
    --   отчитывался по другим записям; решение «ветка есть» (@exists = 1) — после STUCK_MIN
    UPDATE o SET status = 4, error = LEFT(ISNULL(o.error + N' · ', N'') + @note, 400), changed_by = LEFT(@by, 32), changed_utc = @now
    FROM adm.Outbox o
    WHERE o.id = @id AND o.transport = 'discord' AND o.kind = 'notes'
      AND (o.status = 3 OR (o.status = 1 AND o.claimed_utc < DATEADD(MINUTE, -ISNULL(@stuck_min, 10), @now)
           AND (ISNULL(@exists, 0) = 1 OR o.expires_utc <= @now
                OR EXISTS (SELECT 1 FROM adm.Outbox x WHERE x.transport = 'discord' AND x.id <> o.id AND x.done_utc > o.claimed_utc))));
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── ★ р83 М-4: отметка полноты реестра по снимку ─────────────── */
IF OBJECT_ID(N'adm.NotesSnapDone', N'P') IS NOT NULL DROP PROCEDURE adm.NotesSnapDone;
GO
CREATE PROCEDURE adm.NotesSnapDone @id INT, @n INT
AS
BEGIN
    SET NOCOUNT ON;
    -- ★ р84 Н-2: @n = NULL — начало записи реестра (отметка сбрасывается), иначе — конец (число записей и время)
    UPDATE adm.NotesSnap SET reg_count = @n, reg_done_utc = CASE WHEN @n IS NULL THEN NULL ELSE SYSUTCDATETIME() END WHERE id = @id;
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── права ─────────────── */
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.NotesSnap      TO [asda_admin];
    GRANT SELECT ON adm.NotesDraft     TO [asda_admin];
    GRANT SELECT ON adm.NotesPost      TO [asda_admin];
    GRANT SELECT ON adm.NotesPostEntry TO [asda_admin];
    GRANT SELECT ON adm.NotesEntry     TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotesSnap      TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotesDraft     TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotesPost      TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotesPostEntry TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotesEntry     TO [asda_admin];
    GRANT EXECUTE ON adm.NotesSnapPut    TO [asda_admin];
    GRANT EXECUTE ON adm.NotesDraftSet   TO [asda_admin];
    GRANT EXECUTE ON adm.NotesPublishPut TO [asda_admin];
    GRANT EXECUTE ON adm.NotesMarkPut    TO [asda_admin];
    GRANT EXECUTE ON adm.NotesEntryPut   TO [asda_admin];
    GRANT EXECUTE ON adm.NotesMarkRevoke TO [asda_admin];
    GRANT EXECUTE ON adm.NotesEntrySync  TO [asda_admin];
    GRANT EXECUTE ON adm.NotesEntryHide  TO [asda_admin];
    GRANT EXECUTE ON adm.NotesOutboxClose TO [asda_admin];
    GRANT EXECUTE ON adm.NotesSnapDone   TO [asda_admin];
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_reports')
BEGIN
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotesSnap      TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotesDraft     TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotesPost      TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotesPostEntry TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotesEntry     TO [asda_reports];
    DENY  EXECUTE ON adm.NotesSnapPut    TO [asda_reports];
    DENY  EXECUTE ON adm.NotesDraftSet   TO [asda_reports];
    DENY  EXECUTE ON adm.NotesPublishPut TO [asda_reports];
    DENY  EXECUTE ON adm.NotesMarkPut    TO [asda_reports];
    DENY  EXECUTE ON adm.NotesEntryPut   TO [asda_reports];
    DENY  EXECUTE ON adm.NotesMarkRevoke TO [asda_reports];
    DENY  EXECUTE ON adm.NotesEntrySync  TO [asda_reports];
    DENY  EXECUTE ON adm.NotesEntryHide  TO [asda_reports];
    DENY  EXECUTE ON adm.NotesOutboxClose TO [asda_reports];
    DENY  EXECUTE ON adm.NotesSnapDone   TO [asda_reports];
END
GO
PRINT 'adminc_31_notes: OK';
