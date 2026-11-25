-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_23_reports.sql — жалобы игроков на игроков (шаг А6.11, часть «жалобы», 22.11.2026; решение владельца №6: канал — бот Discord;
   domains/reports.py, бот AstoryAdminCenter/DiscordBot/player_reports.py; отчёт Reports/admin_center/impl_a6_econ_20261121.md §А6.11 «жалобы»).
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ adminc_03_grants. Пароль логина бота — переменная окружения ReportsPw
   (deploy/deploy_admin_center.py берёт её из secrets\asda_admin.ini, ключ REPORTS_PASSWORD; в файлах и командной строке его нет).
   Тот же файл самотест выполняет на LocalDB (подставляет $(ReportsPw) сам). Повторный запуск безопасен.

   ПОЧЕМУ ЛОГИН, А НЕ ФАЙЛ ИЛИ API ПАНЕЛИ. Бот работает на ПК владельца и уже ходит к SQL сервера по VPN (AstoryServer/Tools/Anticheat/db_connect.py,
   только чтение). Жалобу он пишет отдельным логином asda_reports, у которого есть ТОЛЬКО EXECUTE на четыре процедуры ниже: ни одной
   таблицы напрямую, ни одной игровой базы, ни журнала панели. Предел частоты и проверка вложений — в процедурах, т.е. их не обойти даже
   ошибкой в коде бота. Ответ автору панель кладёт в очередь adm.PlayerReportReply, бот забирает его процедурой (Discord доступен только с ПК).

   ТАБЛИЦЫ
     adm.PlayerReport       — жалоба: автор (Discord ID и имя на момент подачи), на кого (ник персонажа как написал автор), категория,
                              когда (со слов автора), описание, ссылки (только discord.com/channels и cdn Discord — проверяет бот и панель),
                              статус new → taken → closed, кто взял, кто закрыл и итог, номер дела AC-NNNN.
     adm.PlayerReportFile   — скриншоты: байты (PNG / JPEG / GIF / WEBP — по сигнатуре, не по имени), sha256, размер. Ссылки вложений Discord
                              со временем перестают открываться, поэтому бот кладёт сами файлы.
     adm.PlayerReportReply  — ответ автору: текст оператора, кто, статус 0 ждёт бота · 1 бот взял · 2 отправлено · 3 не доставлено
                              (личные сообщения закрыты и т.п.). Строка в статусе 1 без итога = «неизвестно — проверьте»: повторно её не берёт никто.
   ПРЕДЕЛЫ (adm.ReportSubmit / adm.ReportFileAdd; код итога, не исключение — бот показывает игроку понятный отказ):
     ReportSubmit: 1 — больше 3 жалоб за час от автора · 2 — больше 10 за сутки · 3 — открытая жалоба того же автора на того же персонажа
                   уже есть, сколько бы ей ни было (@id — её номер; ★ ревизия 67 М-1: без ограничения «за сутки») · 4 — больше 60 жалоб за
                   сутки от всех (★ ревизия 67 С-1: было 200; жалобы принимаются только от участников с ролью User старше 7 суток на сервере —
                   проверка в боте, поэтому общий предел — потолок на всплеск, а не основная защита: при десятках честных игроков реальная
                   нагрузка — единицы в сутки, 60 — запас ×5–10).
     ReportFileAdd: 1 — жалоба не этого автора или подана больше 15 минут назад · 2 — уже 3 файла · 3 — размер вне 1 байт…8 МБ ·
                   4 — не PNG / JPEG / GIF / WEBP по сигнатуре · 5 — больше 40 МБ файлов от автора за сутки · 6 — больше 150 МБ от всех за сутки
                   (★ ревизия 67 С-2: было 500 МБ; 150 МБ ≈ 12 жалоб × 3 снимка 1080p по 4 МБ, потолок SQL Express 10 ГБ так не достигается раньше
                   ~2 месяцев даже при ежедневном максимуме, а хранение байтов — 90 дней после закрытия, adm.ReportFilePurge).
   ХРАНЕНИЕ (★ ревизия 67 С-2): adm.ReportFilePurge — байты скриншотов закрытых жалоб старше @days (90) суток после закрытия → пусто (0x),
                   purged_utc = время; имя, тип, размер и sha256 остаются (доказательство, что файл был). Запуск — задача службы панели
                   reports.purge раз в сутки (core/sched.py DAILY), право asda_admin — только EXECUTE этой процедуры.
   ОТВЕТЫ (★ ревизия 67 Н-4): ReportReplyClaim @max, @nonce — бот передаёт свой номер захвата; при сбое на пути ответа (запрос выполнился, а
                   строки до бота не дошли) бот повторяет захват ТЕМ ЖЕ номером и получает те же строки ещё раз (статус 1 этого номера, итога ещё
                   нет) — ни потери, ни второй доставки уже отмеченного ответа.
   ПРАВА
     asda_reports: EXECUTE adm.ReportSubmit, adm.ReportFileAdd, adm.ReportReplyClaim, adm.ReportReplyDone — и больше ничего (DENY на таблицы).
     asda_admin:   SELECT трёх таблиц; UPDATE adm.PlayerReport только столбцов разбора (статус, взял, закрыл, итог, дело); INSERT
                   adm.PlayerReportReply. DELETE — нигде; процедуры бота — DENY.
   Проверка прав бота — adminc_23_reports_verify.sql ПОД asda_reports; прав панели — adminc_10_verify.sql. Откат — adminc_99_rollback.sql.
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (у sqlcmd по умолчанию QUOTED_IDENTIFIER OFF, урок adminc_14). */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'adm.PlayerReport') IS NULL
CREATE TABLE adm.PlayerReport (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_PlayerReport PRIMARY KEY,
    reporter_id     BIGINT         NOT NULL,              -- Discord ID автора
    reporter_name   NVARCHAR(64)   NOT NULL,              -- имя Discord автора на момент подачи
    target_name     NVARCHAR(20)   NOT NULL,              -- ник персонажа, как написал автор
    category        VARCHAR(8)     NOT NULL,              -- cheat / scam / abuse / rmt / other
    happened        NVARCHAR(100)  NOT NULL CONSTRAINT DF_adm_PlayerReport_happened DEFAULT N'',
    body            NVARCHAR(1500) NOT NULL,
    links           NVARCHAR(1000) NOT NULL CONSTRAINT DF_adm_PlayerReport_links DEFAULT N'',
    created_utc     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_PlayerReport_created DEFAULT SYSUTCDATETIME(),
    status          VARCHAR(8)     NOT NULL CONSTRAINT DF_adm_PlayerReport_status DEFAULT 'new',
    taken_by        NVARCHAR(32)   NULL,
    taken_utc       DATETIME2(0)   NULL,
    closed_by       NVARCHAR(32)   NULL,
    closed_utc      DATETIME2(0)   NULL,
    outcome         VARCHAR(12)    NULL,
    outcome_note    NVARCHAR(500)  NULL,
    case_no         VARCHAR(8)     NULL,
    case_by         NVARCHAR(32)   NULL,
    case_utc        DATETIME2(0)   NULL,
    CONSTRAINT CK_adm_PlayerReport_reporter CHECK (reporter_id > 0),
    CONSTRAINT CK_adm_PlayerReport_category CHECK (category IN ('cheat', 'scam', 'abuse', 'rmt', 'other')),
    CONSTRAINT CK_adm_PlayerReport_status CHECK (status IN ('new', 'taken', 'closed')),
    CONSTRAINT CK_adm_PlayerReport_outcome CHECK (outcome IS NULL OR outcome IN ('action', 'case', 'no_violation', 'duplicate', 'insufficient')),
    CONSTRAINT CK_adm_PlayerReport_closed CHECK ((status = 'closed' AND outcome IS NOT NULL AND closed_by IS NOT NULL)
                                                 OR (status <> 'closed' AND outcome IS NULL)),
    CONSTRAINT CK_adm_PlayerReport_case CHECK (case_no IS NULL OR case_no LIKE 'AC-[0-9][0-9][0-9][0-9]%')
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReport_status' AND object_id = OBJECT_ID(N'adm.PlayerReport'))
    CREATE INDEX IX_adm_PlayerReport_status ON adm.PlayerReport (status, id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReport_reporter' AND object_id = OBJECT_ID(N'adm.PlayerReport'))
    CREATE INDEX IX_adm_PlayerReport_reporter ON adm.PlayerReport (reporter_id, created_utc);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReport_created' AND object_id = OBJECT_ID(N'adm.PlayerReport'))
    CREATE INDEX IX_adm_PlayerReport_created ON adm.PlayerReport (created_utc);
GO
IF OBJECT_ID(N'adm.PlayerReportFile') IS NULL
CREATE TABLE adm.PlayerReportFile (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_PlayerReportFile PRIMARY KEY,
    report_id       INT            NOT NULL CONSTRAINT FK_adm_PlayerReportFile_report REFERENCES adm.PlayerReport (id),
    name            NVARCHAR(100)  NOT NULL,
    mime            VARCHAR(10)    NOT NULL,
    size_bytes      INT            NOT NULL,
    sha256          BINARY(32)     NOT NULL,
    data            VARBINARY(MAX) NOT NULL,
    added_utc       DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_PlayerReportFile_added DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_adm_PlayerReportFile_mime CHECK (mime IN ('image/png', 'image/jpeg', 'image/gif', 'image/webp'))
);
GO
IF COL_LENGTH(N'adm.PlayerReportFile', N'purged_utc') IS NULL
    ALTER TABLE adm.PlayerReportFile ADD purged_utc DATETIME2(0) NULL;    -- ★ ревизия 67 С-2: байты удалены по сроку хранения
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReportFile_report' AND object_id = OBJECT_ID(N'adm.PlayerReportFile'))
    CREATE INDEX IX_adm_PlayerReportFile_report ON adm.PlayerReportFile (report_id) INCLUDE (size_bytes, added_utc);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReportFile_added' AND object_id = OBJECT_ID(N'adm.PlayerReportFile'))
    CREATE INDEX IX_adm_PlayerReportFile_added ON adm.PlayerReportFile (added_utc) INCLUDE (size_bytes, report_id);
GO
IF OBJECT_ID(N'adm.PlayerReportReply') IS NULL
CREATE TABLE adm.PlayerReportReply (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_PlayerReportReply PRIMARY KEY,
    report_id       INT            NOT NULL CONSTRAINT FK_adm_PlayerReportReply_report REFERENCES adm.PlayerReport (id),
    text            NVARCHAR(1500) NOT NULL,
    by_login        NVARCHAR(32)   NOT NULL,
    created_utc     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_PlayerReportReply_created DEFAULT SYSUTCDATETIME(),
    status          TINYINT        NOT NULL CONSTRAINT DF_adm_PlayerReportReply_status DEFAULT 0,
    claimed_utc     DATETIME2(0)   NULL,
    done_utc        DATETIME2(0)   NULL,
    result          NVARCHAR(200)  NULL,
    CONSTRAINT CK_adm_PlayerReportReply_status CHECK (status BETWEEN 0 AND 3)
);
GO
IF COL_LENGTH(N'adm.PlayerReportReply', N'claim_nonce') IS NULL
    ALTER TABLE adm.PlayerReportReply ADD claim_nonce UNIQUEIDENTIFIER NULL;    -- ★ ревизия 67 Н-4: номер захвата бота
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReportReply_queue' AND object_id = OBJECT_ID(N'adm.PlayerReportReply'))
    CREATE INDEX IX_adm_PlayerReportReply_queue ON adm.PlayerReportReply (status, id) INCLUDE (report_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_PlayerReportReply_report' AND object_id = OBJECT_ID(N'adm.PlayerReportReply'))
    CREATE INDEX IX_adm_PlayerReportReply_report ON adm.PlayerReportReply (report_id, id);
GO
/* ─────────────── бот: подать жалобу ─────────────── */
IF OBJECT_ID(N'adm.ReportSubmit', N'P') IS NOT NULL DROP PROCEDURE adm.ReportSubmit;
GO
CREATE PROCEDURE adm.ReportSubmit
    @reporter_id BIGINT, @reporter_name NVARCHAR(64), @target NVARCHAR(20), @category VARCHAR(8), @happened NVARCHAR(100),
    @body NVARCHAR(1500), @links NVARCHAR(1000), @id INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @id = NULL; SET @code = NULL;
    SET @target = LTRIM(RTRIM(ISNULL(@target, N'')));
    SET @body = LTRIM(RTRIM(ISNULL(@body, N'')));
    IF @reporter_id IS NULL OR @reporter_id <= 0 THROW 51101, N'жалоба: нет Discord ID автора', 1;
    IF @target = N'' THROW 51102, N'жалоба: не указан ник персонажа', 1;
    IF @category IS NULL OR @category NOT IN ('cheat', 'scam', 'abuse', 'rmt', 'other') THROW 51103, N'жалоба: неизвестная категория', 1;
    IF LEN(@body) < 10 THROW 51104, N'жалоба: описание короче 10 знаков', 1;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    BEGIN TRAN;
    -- одна подача за раз: счётчики пределов и запись — под одним замком (две подачи одновременно не проскочат предел вдвоём)
    DECLARE @lk INT;
    EXEC @lk = sp_getapplock @Resource = N'adm.ReportSubmit', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0 THROW 51105, N'жалоба: очередь подачи занята, повторите через минуту', 1;
    IF (SELECT COUNT(*) FROM adm.PlayerReport WHERE reporter_id = @reporter_id AND created_utc > DATEADD(HOUR, -1, @now)) >= 3
        SET @code = 1;
    ELSE IF (SELECT COUNT(*) FROM adm.PlayerReport WHERE reporter_id = @reporter_id AND created_utc > DATEADD(DAY, -1, @now)) >= 10
        SET @code = 2;
    ELSE
    BEGIN
        SELECT TOP (1) @id = id FROM adm.PlayerReport
        WHERE reporter_id = @reporter_id AND target_name = @target AND status <> 'closed'
        ORDER BY id DESC;
        IF @id IS NOT NULL
            SET @code = 3;
        ELSE IF (SELECT COUNT(*) FROM adm.PlayerReport WHERE created_utc > DATEADD(DAY, -1, @now)) >= 60
            SET @code = 4;
        ELSE
        BEGIN
            INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, happened, body, links, created_utc)
            VALUES (@reporter_id, LEFT(ISNULL(@reporter_name, N''), 64), @target, @category, ISNULL(@happened, N''), @body, ISNULL(@links, N''), @now);
            SET @id = SCOPE_IDENTITY();
            SET @code = 0;
        END
    END
    COMMIT;
END
GO
/* ─────────────── бот: приложить скриншот (только автор, только 15 минут после подачи) ─────────────── */
IF OBJECT_ID(N'adm.ReportFileAdd', N'P') IS NOT NULL DROP PROCEDURE adm.ReportFileAdd;
GO
CREATE PROCEDURE adm.ReportFileAdd
    @report_id INT, @reporter_id BIGINT, @name NVARCHAR(100), @data VARBINARY(MAX), @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME(), @size BIGINT = DATALENGTH(@data), @mime VARCHAR(10) = NULL;
    IF @size IS NULL OR @size < 1 OR @size > 8388608
    BEGIN
        SET @code = 3; RETURN;
    END
    IF SUBSTRING(@data, 1, 8) = 0x89504E470D0A1A0A SET @mime = 'image/png';
    ELSE IF SUBSTRING(@data, 1, 3) = 0xFFD8FF SET @mime = 'image/jpeg';
    ELSE IF SUBSTRING(@data, 1, 6) IN (0x474946383761, 0x474946383961) SET @mime = 'image/gif';
    ELSE IF SUBSTRING(@data, 1, 4) = 0x52494646 AND SUBSTRING(@data, 9, 4) = 0x57454250 SET @mime = 'image/webp';
    IF @mime IS NULL
    BEGIN
        SET @code = 4; RETURN;
    END
    BEGIN TRAN;
    DECLARE @lk INT;
    EXEC @lk = sp_getapplock @Resource = N'adm.ReportFileAdd', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0 THROW 51106, N'скриншот: очередь занята, повторите через минуту', 1;
    IF NOT EXISTS (SELECT 1 FROM adm.PlayerReport WHERE id = @report_id AND reporter_id = @reporter_id AND created_utc > DATEADD(MINUTE, -15, @now))
        SET @code = 1;
    ELSE IF (SELECT COUNT(*) FROM adm.PlayerReportFile WHERE report_id = @report_id) >= 3
        SET @code = 2;
    ELSE IF ISNULL((SELECT SUM(CAST(f.size_bytes AS BIGINT)) FROM adm.PlayerReportFile f JOIN adm.PlayerReport r ON r.id = f.report_id
                    WHERE r.reporter_id = @reporter_id AND f.added_utc > DATEADD(DAY, -1, @now)), 0) + @size > 41943040
        SET @code = 5;
    ELSE IF ISNULL((SELECT SUM(CAST(size_bytes AS BIGINT)) FROM adm.PlayerReportFile WHERE added_utc > DATEADD(DAY, -1, @now)), 0) + @size > 157286400
        SET @code = 6;
    ELSE
    BEGIN
        INSERT adm.PlayerReportFile (report_id, name, mime, size_bytes, sha256, data, added_utc)
        VALUES (@report_id, LEFT(ISNULL(NULLIF(LTRIM(RTRIM(@name)), N''), N'screenshot'), 100), @mime, CAST(@size AS INT),
                HASHBYTES('SHA2_256', @data), @data, @now);
        SET @code = 0;
    END
    COMMIT;
END
GO
/* ─────────────── бот: забрать ответы авторам (каждый — один раз) и отметить итог ─────────────── */
IF OBJECT_ID(N'adm.ReportReplyClaim', N'P') IS NOT NULL DROP PROCEDURE adm.ReportReplyClaim;
GO
CREATE PROCEDURE adm.ReportReplyClaim @max INT, @nonce UNIQUEIDENTIFIER = NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @max IS NULL OR @max < 1 OR @max > 20 THROW 51111, N'ответы: за раз — от 1 до 20', 1;
    DECLARE @t TABLE (id INT PRIMARY KEY);
    BEGIN TRAN;
    -- ★ ревизия 67 Н-4: повтор захвата тем же номером — сначала строки, уже взятые этим номером и ещё без итога (до бота они не дошли)
    IF @nonce IS NOT NULL
        INSERT @t (id) SELECT id FROM adm.PlayerReportReply WITH (UPDLOCK) WHERE status = 1 AND claim_nonce = @nonce;
    UPDATE r SET status = 1, claimed_utc = SYSUTCDATETIME(), claim_nonce = @nonce
    OUTPUT INSERTED.id INTO @t
    FROM adm.PlayerReportReply r WITH (UPDLOCK, READPAST)
    WHERE r.id IN (SELECT TOP (@max) id FROM adm.PlayerReportReply WITH (UPDLOCK, READPAST) WHERE status = 0 ORDER BY id);
    COMMIT;
    SELECT r.id, r.report_id, p.reporter_id, r.text, p.target_name, p.category
    FROM @t t JOIN adm.PlayerReportReply r ON r.id = t.id JOIN adm.PlayerReport p ON p.id = r.report_id
    ORDER BY r.id;
END
GO
IF OBJECT_ID(N'adm.ReportReplyDone', N'P') IS NOT NULL DROP PROCEDURE adm.ReportReplyDone;
GO
CREATE PROCEDURE adm.ReportReplyDone @id INT, @ok BIT, @result NVARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.PlayerReportReply SET status = CASE WHEN @ok = 1 THEN 2 ELSE 3 END, done_utc = SYSUTCDATETIME(), result = LEFT(ISNULL(@result, N''), 200)
    WHERE id = @id AND status = 1;
    SELECT @@ROWCOUNT AS n;           -- 0 — строка не в статусе «бот взял» (повторный итог не пишется)
END
GO
/* ─────────────── ★ ревизия 67 С-2: срок хранения скриншотов (служба панели, раз в сутки) ─────────────── */
IF OBJECT_ID(N'adm.ReportFilePurge', N'P') IS NOT NULL DROP PROCEDURE adm.ReportFilePurge;
GO
CREATE PROCEDURE adm.ReportFilePurge @days INT, @dry BIT = 0
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @days IS NULL OR @days < 30 OR @days > 3650 THROW 51121, N'срок хранения скриншотов — от 30 до 3650 суток', 1;
    DECLARE @cut DATETIME2(0) = DATEADD(DAY, -@days, SYSUTCDATETIME()), @n INT, @b BIGINT;
    DECLARE @ids TABLE (id INT PRIMARY KEY, size_bytes INT);
    BEGIN TRAN;
    INSERT @ids (id, size_bytes) SELECT f.id, f.size_bytes FROM adm.PlayerReportFile f WITH (UPDLOCK) JOIN adm.PlayerReport r ON r.id = f.report_id
    WHERE r.status = 'closed' AND r.closed_utc < @cut AND f.purged_utc IS NULL;
    SELECT @n = COUNT(*), @b = ISNULL(SUM(CAST(size_bytes AS BIGINT)), 0) FROM @ids;
    IF @dry = 0
        UPDATE f SET data = 0x, purged_utc = SYSUTCDATETIME() FROM adm.PlayerReportFile f JOIN @ids i ON i.id = f.id;
    COMMIT;
    SELECT @n AS files, @b AS bytes;
END
GO
/* ─────────────── логин бота: только эти четыре процедуры ─────────────── */
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'asda_reports')
    CREATE LOGIN [asda_reports] WITH PASSWORD = N'$(ReportsPw)', DEFAULT_DATABASE = [master], CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    ALTER LOGIN [asda_reports] WITH PASSWORD = N'$(ReportsPw)', CHECK_POLICY = ON;
ALTER LOGIN [asda_reports] ENABLE;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_reports')
    CREATE USER [asda_reports] FOR LOGIN [asda_reports] WITH DEFAULT_SCHEMA = adm;
GO
GRANT EXECUTE ON adm.ReportSubmit     TO [asda_reports];
GRANT EXECUTE ON adm.ReportFileAdd    TO [asda_reports];
GRANT EXECUTE ON adm.ReportReplyClaim TO [asda_reports];
GRANT EXECUTE ON adm.ReportReplyDone  TO [asda_reports];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.PlayerReport      TO [asda_reports];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.PlayerReportFile  TO [asda_reports];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.PlayerReportReply TO [asda_reports];
GO
/* ─────────────── служба панели (asda_admin): чтение, разбор, ответ — без удаления и без процедур бота ─────────────── */
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.PlayerReport      TO [asda_admin];
    GRANT SELECT ON adm.PlayerReportFile  TO [asda_admin];
    GRANT SELECT ON adm.PlayerReportReply TO [asda_admin];
    GRANT UPDATE ON adm.PlayerReport (status, taken_by, taken_utc, closed_by, closed_utc, outcome, outcome_note, case_no, case_by, case_utc) TO [asda_admin];
    GRANT INSERT ON adm.PlayerReportReply TO [asda_admin];
    DENY  INSERT, DELETE ON adm.PlayerReport      TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.PlayerReportFile TO [asda_admin];
    DENY  UPDATE, DELETE ON adm.PlayerReportReply TO [asda_admin];
    DENY  EXECUTE ON adm.ReportSubmit     TO [asda_admin];
    DENY  EXECUTE ON adm.ReportFileAdd    TO [asda_admin];
    DENY  EXECUTE ON adm.ReportReplyClaim TO [asda_admin];
    DENY  EXECUTE ON adm.ReportReplyDone  TO [asda_admin];
    GRANT EXECUTE ON adm.ReportFilePurge  TO [asda_admin];   -- ★ ревизия 67 С-2: очистка байтов по сроку (саму таблицу менять нельзя)
END
DENY EXECUTE ON adm.ReportFilePurge TO [asda_reports];
GO
PRINT 'adminc_23_reports: OK';
