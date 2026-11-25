-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_28_outbox.sql — очередь исходящих сообщений adm.Outbox: объявления в Discord (шаг А7.4, 23.11.2026; решение владельца А7 №2 —
   в Discord только по флажку «и в Discord» в форме объявления, тексты EN/RU/AR оператор пишет сам, канал и роль выбирает из списка;
   domains/outbox.py, domains/live.py (live.announce), бот AstoryAdminCenter/DiscordBot/outbox_bot.py; отчёт
   Reports/admin_center/impl_a7_releases_20261123.md §А7.4).
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin -x -I) ПОСЛЕ adminc_23_reports (логин бота asda_reports создаёт он). Тот же файл самотест
   выполняет на LocalDB (пользователей asda_admin / asda_reports там может не быть — выдача прав пропускается). Повторный запуск безопасен.

   ПОЧЕМУ ОЧЕРЕДЬ. Сервер не видит Discord (с @@ASTORY_SERVER_HOSTNAME@@ discord.com — тайм-аут, разбор А7 §0 п.1), бот Oracle работает на ПК владельца и ходит в
   Discord через прокси ПК. Панель кладёт сообщение сюда, бот забирает его процедурой — тот же путь, что ответы на жалобы А6.11
   (adm.ReportReplyClaim / Done). Бот ходит ТЕМ ЖЕ логином asda_reports: пароль уже лежит рядом с ботом (reports.env), второго секрета на ПК
   нет; у логина — только EXECUTE процедур бота ниже, таблицу он не видит.

   ТАБЛИЦА adm.Outbox — одна запись = одно сообщение в один канал Discord:
     kind         — вид: announce (объявление из формы «Объявление всем»); test — проверочная запись (бот её НЕ публикует, только отмечает);
     channel_key  — канал из белого списка: announcements (новости), updates (форум, ветка с заголовком), test-info (тестерам);
     role_key     — роль-пинг из белого списка: news (News Ping), patch (Patch Ping), playtest (Playtest Ping) или NULL (без упоминания);
                    @everyone и @here не существуют как значение и запрещены в текстах (CHECK ниже, бот проверяет ещё раз);
     title        — заголовок (для форума — имя ветки): текст объявления в игру;
     text_en / text_ru / text_ar — тексты оператора как он их написал (EN обязателен, RU и AR — по желанию);
     expires_utc  — срок годности: бот не публикует позже (статус «просрочено»);
     status       — 7 ждёт объявления в игру (бот не берёт) · 0 ждёт бота · 1 бот взял · 2 опубликовано · 3 ошибка · 4 отменено ·
                    5 просрочено · 6 тест (не публиковалось);
     attempts     — сколько раз бот брал запись; error — последняя ошибка; discord_channel_id / discord_message_id — где опубликовано
                    (для форума — ветка и её первое сообщение);
     del_status   — удаление опубликованного (операция владельца): NULL нет · 0 ждёт бота · 1 бот взял · 2 удалено · 3 ошибка удаления.
   ПРЕДЕЛЫ (adm.OutboxPut, код итога, не исключение): 1 — больше 6 объявлений за час · 2 — больше 30 за сутки · 3 — больше 10 проверочных за
     час · 4 — неверные поля (канал, роль, длины, срок, @everyone / @here) · 5 — имя ветки форума updates за сутки уже было (★ р83).
   ИДЕМПОТЕНТНОСТЬ. Бот берёт запись процедурой (UPDLOCK, READPAST), а перед отправкой пишет номер записи в свой журнал на ПК
     (outbox_ledger.json) — повтор того же номера (сбой по дороге, кнопка «повторить») бот не публикует; у сообщения в канале — ещё и nonce
     Discord. Дубль возможен только при сбое шлюза Discord в форуме updates (у ветки nonce нет, ★ ревизия 76 М-2).
     ★ р76 К2: kind announce всегда ставится в статус 7 (боту — только через adm.OutboxRelease после объявления в игру), @hold — только у test.
     Захват — с номером захвата @nonce, как у ответов на жалобы (ревизия 67 Н-4): повтор тем же номером возвращает те же строки.
   ПРАВА
     asda_reports (бот): EXECUTE adm.OutboxClaim / OutboxDone / OutboxDelClaim / OutboxDelDone — и больше ничего (DENY на таблицу и на процедуры
                         панели).
     asda_admin (панель): SELECT adm.Outbox; EXECUTE adm.OutboxPut / OutboxRelease / OutboxCancel / OutboxRetry / OutboxDelete; прямой записи
                         нет (DENY INSERT / UPDATE / DELETE), процедуры бота — DENY.
   Проверка прав бота — adminc_28_outbox_verify.sql ПОД asda_reports; панели — adminc_10_verify.sql. Откат — adminc_99_rollback.sql.
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (урок adminc_14). Совместимость с уровнем 100: без THROW, IIF, CONCAT,
   TRY_CONVERT, FORMAT, STRING_SPLIT, CREATE OR ALTER; даты — литералами ГГГГММДД.
   ★ А7.5 (23.11): в той же таблице — строки Telegram владельцу (transport = 'telegram', adminc_29_telegram.sql). Все процедуры этого файла
   работают ТОЛЬКО со строками transport = 'discord' (пределы, захват, итог, отмена, повтор, удаление): бот Discord строк Telegram не видит. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'adm.Outbox') IS NULL
CREATE TABLE adm.Outbox (
    id                  INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_Outbox PRIMARY KEY,
    kind                VARCHAR(16)    NOT NULL CONSTRAINT CK_adm_Outbox_kind CHECK (kind IN ('announce', 'test')),
    transport           VARCHAR(16)    NOT NULL CONSTRAINT DF_adm_Outbox_transport DEFAULT ('discord')
                                                CONSTRAINT CK_adm_Outbox_transport CHECK (transport IN ('discord')),
    channel_key         VARCHAR(32)    NOT NULL CONSTRAINT CK_adm_Outbox_channel CHECK (channel_key IN ('announcements', 'updates', 'test-info')),
    role_key            VARCHAR(16)    NULL     CONSTRAINT CK_adm_Outbox_role CHECK (role_key IN ('news', 'patch', 'playtest')),
    title               NVARCHAR(100)  NOT NULL,
    text_en             NVARCHAR(1800) NOT NULL,
    text_ru             NVARCHAR(1800) NULL,
    text_ar             NVARCHAR(1800) NULL,
    is_test             BIT            NOT NULL CONSTRAINT DF_adm_Outbox_test DEFAULT (0),
    created_utc         DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_Outbox_created DEFAULT (SYSUTCDATETIME()),
    created_by          NVARCHAR(32)   NOT NULL,
    expires_utc         DATETIME2(0)   NOT NULL,
    status              TINYINT        NOT NULL CONSTRAINT DF_adm_Outbox_status DEFAULT (0)
                                                CONSTRAINT CK_adm_Outbox_status CHECK (status BETWEEN 0 AND 7),
    attempts            INT            NOT NULL CONSTRAINT DF_adm_Outbox_attempts DEFAULT (0),
    claim_nonce         UNIQUEIDENTIFIER NULL,
    claimed_utc         DATETIME2(0)   NULL,
    done_utc            DATETIME2(0)   NULL,
    error               NVARCHAR(400)  NULL,
    discord_channel_id  BIGINT         NULL,
    discord_message_id  BIGINT         NULL,
    changed_by          NVARCHAR(32)   NULL,
    changed_utc         DATETIME2(0)   NULL,
    del_status          TINYINT        NULL     CONSTRAINT CK_adm_Outbox_del CHECK (del_status BETWEEN 0 AND 3),
    del_by              NVARCHAR(32)   NULL,
    del_utc             DATETIME2(0)   NULL,
    del_nonce           UNIQUEIDENTIFIER NULL,
    del_claimed_utc     DATETIME2(0)   NULL,
    del_done_utc        DATETIME2(0)   NULL,
    del_error           NVARCHAR(400)  NULL,
    CONSTRAINT CK_adm_Outbox_texts CHECK (text_en NOT LIKE N'%@everyone%' AND text_en NOT LIKE N'%@here%'
        AND ISNULL(text_ru, N'') NOT LIKE N'%@everyone%' AND ISNULL(text_ru, N'') NOT LIKE N'%@here%'
        AND ISNULL(text_ar, N'') NOT LIKE N'%@everyone%' AND ISNULL(text_ar, N'') NOT LIKE N'%@here%'
        AND title NOT LIKE N'%@everyone%' AND title NOT LIKE N'%@here%')
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_Outbox_status' AND object_id = OBJECT_ID(N'adm.Outbox'))
    CREATE INDEX IX_adm_Outbox_status ON adm.Outbox (status, id);
GO
/* ─────────────── панель: поставить запись (пределы и белые списки — здесь же, их не обойти кодом панели) ─────────────── */
IF OBJECT_ID(N'adm.OutboxPut', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxPut;
GO
CREATE PROCEDURE adm.OutboxPut
    @kind VARCHAR(16), @channel VARCHAR(32), @role VARCHAR(16), @title NVARCHAR(200),
    @en NVARCHAR(2000), @ru NVARCHAR(2000), @ar NVARCHAR(2000), @ttl_min INT, @by NVARCHAR(32), @hold BIT,
    @id INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @id = NULL; SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME(), @test BIT = CASE WHEN @kind = 'test' THEN 1 ELSE 0 END;
    SET @title = LTRIM(RTRIM(ISNULL(@title, N''))); SET @en = LTRIM(RTRIM(ISNULL(@en, N'')));
    SET @ru = NULLIF(LTRIM(RTRIM(ISNULL(@ru, N''))), N''); SET @ar = NULLIF(LTRIM(RTRIM(ISNULL(@ar, N''))), N'');
    IF @role = '' SET @role = NULL;
    IF ISNULL(@kind, '') NOT IN ('announce', 'test') OR ISNULL(@channel, '') NOT IN ('announcements', 'updates', 'test-info')
       OR (@role IS NOT NULL AND @role NOT IN ('news', 'patch', 'playtest'))
       OR LEN(@title) < 1 OR LEN(@title) > 100 OR LEN(@en) < 1 OR LEN(@en) > 1800 OR LEN(ISNULL(@ru, N'')) > 1800 OR LEN(ISNULL(@ar, N'')) > 1800
       OR @ttl_min IS NULL OR @ttl_min < 5 OR @ttl_min > 1440 OR LEN(ISNULL(@by, N'')) < 1
       OR (@title + N' ' + @en + N' ' + ISNULL(@ru, N'') + N' ' + ISNULL(@ar, N'')) LIKE N'%@everyone%'
       OR (@title + N' ' + @en + N' ' + ISNULL(@ru, N'') + N' ' + ISNULL(@ar, N'')) LIKE N'%@here%'
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
    IF @test = 0 AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'discord' AND is_test = 0 AND created_utc > DATEADD(HOUR, -1, @now)) >= 6
        SET @code = 1;
    ELSE IF @test = 0 AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'discord' AND is_test = 0 AND created_utc > DATEADD(DAY, -1, @now)) >= 30
        SET @code = 2;
    ELSE IF @test = 1 AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'discord' AND is_test = 1 AND created_utc > DATEADD(HOUR, -1, @now)) >= 10
        SET @code = 3;
    -- ★ р83 М-2 (А7.7): имя ветки форума updates за сутки не повторяется (объявления и заметки к выпуску вместе, под тем же замком) — бот ищет
    --   свою прерванную ветку по имени; отменённое и просроченное не в счёт, только если бот его не брал
    ELSE IF @test = 0 AND @channel = 'updates' AND EXISTS (SELECT 1 FROM adm.Outbox WHERE transport = 'discord' AND channel_key = 'updates' AND is_test = 0
                       AND title = @title AND NOT (status IN (4, 5) AND claimed_utc IS NULL) AND created_utc > DATEADD(DAY, -1, @now))
        SET @code = 5;
    ELSE
    BEGIN
        INSERT adm.Outbox (kind, channel_key, role_key, title, text_en, text_ru, text_ar, is_test, created_utc, created_by, expires_utc, status)
        VALUES (@kind, @channel, @role, @title, @en, @ru, @ar, @test, @now, LEFT(@by, 32), DATEADD(MINUTE, @ttl_min, @now),
                CASE WHEN @kind = 'announce' OR @hold = 1 THEN 7 ELSE 0 END);   -- ★ р76 К2: объявление — всегда «ждёт игры», @hold — только у test
        SET @id = SCOPE_IDENTITY();
        SET @code = 0;
    END
    COMMIT;
END
GO
/* объявление в игру ушло (@ok = 1) — запись отпускается боту; не ушло — отменяется с пометкой. Только из статуса 7. */
IF OBJECT_ID(N'adm.OutboxRelease', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxRelease;
GO
CREATE PROCEDURE adm.OutboxRelease @id INT, @ok BIT, @by NVARCHAR(32), @note NVARCHAR(400)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.Outbox SET status = CASE WHEN @ok = 1 THEN 0 ELSE 4 END, error = CASE WHEN @ok = 1 THEN NULL ELSE LEFT(ISNULL(@note, N''), 400) END,
           changed_by = LEFT(@by, 32), changed_utc = SYSUTCDATETIME()
    WHERE id = @id AND status = 7 AND transport = 'discord';
    SELECT @@ROWCOUNT AS n;
END
GO
/* отменить до публикации: из «ждёт бота» и «ждёт объявления в игру» */
IF OBJECT_ID(N'adm.OutboxCancel', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxCancel;
GO
CREATE PROCEDURE adm.OutboxCancel @id INT, @by NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.Outbox SET status = 4, changed_by = LEFT(@by, 32), changed_utc = SYSUTCDATETIME()
    WHERE id = @id AND status IN (0, 7) AND transport = 'discord';
    SELECT @@ROWCOUNT AS n;
END
GO
/* повторить: после ошибки или если бот взял и не отчитался дольше @stuck_min минут; срок годности ещё не прошёл, попыток меньше 5.
   Второй публикации не будет и при живом боте: бот не публикует номер, который уже есть в его журнале на ПК. */
IF OBJECT_ID(N'adm.OutboxRetry', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxRetry;
GO
CREATE PROCEDURE adm.OutboxRetry @id INT, @by NVARCHAR(32), @stuck_min INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    UPDATE adm.Outbox SET status = 0, claim_nonce = NULL, changed_by = LEFT(@by, 32), changed_utc = @now
    WHERE id = @id AND transport = 'discord' AND expires_utc > @now AND attempts < 5
      AND kind <> 'notes'      -- ★ р82 М-2 (А7.7): заметки повторяются новой публикацией, не повтором записи (её записи могли уже уйти в другую)
      AND (status = 3 OR (status = 1 AND claimed_utc < DATEADD(MINUTE, -ISNULL(@stuck_min, 10), @now)));
    SELECT @@ROWCOUNT AS n;
END
GO
/* удалить опубликованное (операция владельца): бот удалит сообщение (у форума — ветку). Повтор — только после ошибки удаления. */
IF OBJECT_ID(N'adm.OutboxDelete', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxDelete;
GO
CREATE PROCEDURE adm.OutboxDelete @id INT, @by NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.Outbox SET del_status = 0, del_by = LEFT(@by, 32), del_utc = SYSUTCDATETIME(), del_nonce = NULL, del_error = NULL
    WHERE id = @id AND transport = 'discord' AND status = 2 AND discord_message_id IS NOT NULL AND (del_status IS NULL OR del_status = 3);
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── бот: забрать записи и отметить итог ─────────────── */
IF OBJECT_ID(N'adm.OutboxClaim', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxClaim;
GO
CREATE PROCEDURE adm.OutboxClaim @max INT, @nonce UNIQUEIDENTIFIER = NULL, @test_only BIT = 0
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @max IS NULL OR @max < 1 OR @max > 10
    BEGIN
        RAISERROR(N'очередь исходящих: за раз — от 1 до 10', 16, 1); RETURN;
    END
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    DECLARE @t TABLE (id INT PRIMARY KEY);
    BEGIN TRAN;
    -- просроченное не отдаётся никогда: «ждёт бота» после срока → «просрочено»
    UPDATE adm.Outbox WITH (UPDLOCK, READPAST) SET status = 5, done_utc = @now, error = N'просрочено: бот не забрал запись до срока годности'
    WHERE transport = 'discord' AND status = 0 AND expires_utc <= @now AND (ISNULL(@test_only, 0) = 0 OR is_test = 1);
    -- повтор захвата тем же номером (сбой по дороге): строки, уже взятые этим номером и ещё без итога
    IF @nonce IS NOT NULL
        INSERT @t (id) SELECT id FROM adm.Outbox WITH (UPDLOCK) WHERE transport = 'discord' AND status = 1 AND claim_nonce = @nonce;
    UPDATE o SET status = 1, claimed_utc = @now, claim_nonce = @nonce, attempts = attempts + 1
    OUTPUT INSERTED.id INTO @t
    FROM adm.Outbox o WITH (UPDLOCK, READPAST)
    WHERE o.id IN (SELECT TOP (@max) id FROM adm.Outbox WITH (UPDLOCK, READPAST)
                   WHERE transport = 'discord' AND status = 0 AND expires_utc > @now AND (ISNULL(@test_only, 0) = 0 OR is_test = 1) ORDER BY id);
    COMMIT;
    SELECT o.id, o.kind, o.channel_key, o.role_key, o.title, o.text_en, o.text_ru, o.text_ar, o.is_test, o.expires_utc, o.attempts, @now AS now_utc
    FROM @t t JOIN adm.Outbox o ON o.id = t.id
    ORDER BY o.id;
END
GO
IF OBJECT_ID(N'adm.OutboxDone', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxDone;
GO
CREATE PROCEDURE adm.OutboxDone @id INT, @ok BIT, @expired BIT, @error NVARCHAR(400), @channel_id BIGINT, @message_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.Outbox SET status = CASE WHEN @ok = 1 AND is_test = 1 THEN 6 WHEN @ok = 1 THEN 2 WHEN @expired = 1 THEN 5 ELSE 3 END,
           done_utc = SYSUTCDATETIME(), error = CASE WHEN @ok = 1 THEN NULL ELSE LEFT(ISNULL(@error, N''), 400) END,
           discord_channel_id = CASE WHEN @ok = 1 AND is_test = 0 THEN @channel_id ELSE NULL END,
           discord_message_id = CASE WHEN @ok = 1 AND is_test = 0 THEN @message_id ELSE NULL END
    WHERE id = @id AND status = 1 AND transport = 'discord';
    SELECT @@ROWCOUNT AS n;           -- 0 — запись не в статусе «бот взял» (повторный итог не пишется)
END
GO
IF OBJECT_ID(N'adm.OutboxDelClaim', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxDelClaim;
GO
CREATE PROCEDURE adm.OutboxDelClaim @max INT, @nonce UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @max IS NULL OR @max < 1 OR @max > 10
    BEGIN
        RAISERROR(N'удаление: за раз — от 1 до 10', 16, 1); RETURN;
    END
    DECLARE @t TABLE (id INT PRIMARY KEY);
    BEGIN TRAN;
    IF @nonce IS NOT NULL
        INSERT @t (id) SELECT id FROM adm.Outbox WITH (UPDLOCK) WHERE del_status = 1 AND del_nonce = @nonce;
    UPDATE o SET del_status = 1, del_claimed_utc = SYSUTCDATETIME(), del_nonce = @nonce
    OUTPUT INSERTED.id INTO @t
    FROM adm.Outbox o WITH (UPDLOCK, READPAST)
    WHERE o.id IN (SELECT TOP (@max) id FROM adm.Outbox WITH (UPDLOCK, READPAST) WHERE transport = 'discord' AND del_status = 0 AND status = 2 ORDER BY id);
    COMMIT;
    SELECT o.id, o.channel_key, o.discord_channel_id, o.discord_message_id FROM @t t JOIN adm.Outbox o ON o.id = t.id ORDER BY o.id;
END
GO
IF OBJECT_ID(N'adm.OutboxDelDone', N'P') IS NOT NULL DROP PROCEDURE adm.OutboxDelDone;
GO
CREATE PROCEDURE adm.OutboxDelDone @id INT, @ok BIT, @error NVARCHAR(400)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.Outbox SET del_status = CASE WHEN @ok = 1 THEN 2 ELSE 3 END, del_done_utc = SYSUTCDATETIME(),
           del_error = CASE WHEN @ok = 1 THEN NULL ELSE LEFT(ISNULL(@error, N''), 400) END
    WHERE id = @id AND del_status = 1 AND transport = 'discord';
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── права ─────────────── */
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_reports')
BEGIN
    GRANT EXECUTE ON adm.OutboxClaim    TO [asda_reports];
    GRANT EXECUTE ON adm.OutboxDone     TO [asda_reports];
    GRANT EXECUTE ON adm.OutboxDelClaim TO [asda_reports];
    GRANT EXECUTE ON adm.OutboxDelDone  TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.Outbox TO [asda_reports];
    DENY  EXECUTE ON adm.OutboxPut      TO [asda_reports];
    DENY  EXECUTE ON adm.OutboxRelease  TO [asda_reports];
    DENY  EXECUTE ON adm.OutboxCancel   TO [asda_reports];
    DENY  EXECUTE ON adm.OutboxRetry    TO [asda_reports];
    DENY  EXECUTE ON adm.OutboxDelete   TO [asda_reports];
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.Outbox TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.Outbox TO [asda_admin];
    GRANT EXECUTE ON adm.OutboxPut      TO [asda_admin];
    GRANT EXECUTE ON adm.OutboxRelease  TO [asda_admin];
    GRANT EXECUTE ON adm.OutboxCancel   TO [asda_admin];
    GRANT EXECUTE ON adm.OutboxRetry    TO [asda_admin];
    GRANT EXECUTE ON adm.OutboxDelete   TO [asda_admin];
    DENY  EXECUTE ON adm.OutboxClaim    TO [asda_admin];
    DENY  EXECUTE ON adm.OutboxDone     TO [asda_admin];
    DENY  EXECUTE ON adm.OutboxDelClaim TO [asda_admin];
    DENY  EXECUTE ON adm.OutboxDelDone  TO [asda_admin];
END
GO
PRINT 'adminc_28_outbox: OK';
