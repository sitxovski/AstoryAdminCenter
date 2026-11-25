-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_25_attendance.sql — админ-центр, шаг А6.10 «Посещаемость: засчитать и снять день». 23.11.2026.

   ЗАЧЕМ. Решение владельца 23.11 (ADMIN_TOOL_PLAN.md §5.2 строка А6.10): сводка посещаемости и ручные «засчитать день» / «снять день» с
   откатом, причиной и журналом; права owner и admin, gm только смотрит. Награда (предмет 68788) и патчи сервера НЕ меняются.

   РЕВЕРС ПОТОКА (Reports/admin_center/impl_a6_econ_20261121.md §А6.10):
     NPC → GS EventNcpProcessReq@0x553C70 → DB 2250 → DBManager sub_42F510 «EXEC OP_Attendance %d, %d» → GS 2251 (ОДИН байт — флаг)
     → eventNpcProcessRes@0x553DC0: флаг 1 — выдать 68788; выдал — клиенту 6060 и DB 2252 → sub_42F6F0 «EXEC OP_Attendance_insert».
     dbo.OP_Attendance: персонажа нет — 3; есть строка dbo.AttendanceDetail (Step = 2) с ДАТОЙ GETDATE() (convert(varchar(10), …, 21)) — 2
       («сегодня уже получено»); иначе 1. Учёт — по ПЕРСОНАЖУ (Userindex, Charidx), сутки — календарная дата часов SQL-сервера.
     dbo.OP_Attendance_Insert: та же проверка; затем dbo.AttendanceCount (Step = 2): строки нет — INSERT (ACount = 1, Step = 2), есть —
       ACount + 1; и строка dbo.AttendanceDetail (Step = 2, RegistDay = GETDATE()).
     В памяти GS (CUser) посещаемость не хранится: каждый визит к NPC — свежий запрос к базе. ACount игра не читает (DBManager отдаёт GS
     только флаг) — это счётчик для людей; на живой dev 23.11 у всех 18 строк ACount = числу строк Detail (Step 2). Индексов и PK нет.
   ЧТО ЗНАЧИТ «ЗАСЧИТАТЬ» И «СНЯТЬ» (так, чтобы GS не выдал награду дважды и не лишил её):
     засчитать день D — то, что сделал бы OP_Attendance_Insert в день D: строка Detail (Step 2, RegistDay = D 00:00, Note = «adm #N»)
       и ACount + 1 (строки счёта нет — INSERT, как сток). Только ПРОШЕДШИЙ день (D < сегодня): сегодняшний засчитывает сам сервер вместе с
       наградой — отметка «сегодня» из панели лишила бы игрока сегодняшней награды. Не старше 365 суток. День уже засчитан — отказ.
     снять день D — удалить строку Detail этого дня (Step 2) и ACount − 1. Только ПРОШЕДШИЙ день: снятие сегодняшней отметки сервер
       понял бы как «сегодня ещё не было» и выдал бы 68788 второй раз.
     Откат — ровно обратное по журналу: снятая строка возвращается с прежними RegistDay и Note (номер ADNo — новый, IDENTITY), засчитанная
       удаляется по своему ADNo или по Note «adm #N» (если её снимали и вернули откатом — ADNo уже новый); строку счёта, созданную засчитыванием, откат удаляет, если счёт снова 0 (как было до неё).

   ЧТО СОЗДАЁТСЯ (база Joy1, схема adm — владелец dbo):
     adm.AttendanceAdjustLog — журнал ручных отметок: строка на каждое засчитывание / снятие / откат (delta +1 / −1), счёт «было → стало»,
                               строка Detail (ADNo, RegistDay, Note), строка счёта (ACNo, создана / удалена), причина, оператор, ключ
                               запроса (идемпотентность), undo_of / undone_by.
     adm.AttendanceAdjust    — правка одной транзакцией (или внутри транзакции службы — служба фиксирует сразу после процедуры, до
                               adm.audit, ревизия 72 М-1; откат без журнала действий — attendance.undo_log, ревизия 73);
                               @Dry = 1 — те же проверки, ничего не пишет (предпросмотр).
   РЕЗУЛЬТАТ одной строкой: status (1 — записано, 2 — повтор ключа, 3 — предпросмотр прошёл, 0 — отказ) | reason | log_id | count_before |
     count_after | adno | regist | today.
   ОТКАЗЫ: bad-args, bad-reason, bad-day, not-past (сегодня или будущее), too-old, no-char, count-ambiguous (строк счёта Step 2 больше
     одной), count-changed (счёт изменился с предпросмотра), day-present, day-absent, day-ambiguous, count-low, key-conflict,
     undo-not-found, undo-is-undo, undo-repeat, undo-mismatch, undo-row-gone.
   ЗАМКИ (★ ревизия 72 М-1): у dbo.AttendanceCount / dbo.AttendanceDetail нет индексов (heap) — UPDLOCK / HOLDLOCK на них взял бы всю
     таблицу до фиксации панели (а она — после записи adm.audit), и вставка 2252 ВСЕХ игроков ждала бы. Поэтому: правки панели одного
     персонажа сериализует sp_getapplock «adm.att:<учётка>/<слот>» (владелец — транзакция, ожидание ≤ 5 с — иначе отказ busy), чтения
     таблиц стока — без замковых подсказок (read committed, S-замки снимаются сразу), запись — точечно по ACNo / ADNo (X на одной
     строке этого персонажа до фиксации); счёт «стало» берётся из самой UPDATE (ACount = ACount ± 1 — сток мог прибавить сегодняшний
     день параллельно). Вставки 2252 других игроков и Detail этого персонажа панель не держит; UPDATE счёта ЭТОГО персонажа штатным
     визитом ждёт фиксации панели (миллисекунды). Строка журнала по ключу — UPDLOCK, HOLDLOCK (своя таблица, индекс UNIQUE).
   ПРЕДЕЛ СТОКА (★ ревизия 72 М-2): OP_Attendance_Insert читает счёт под READUNCOMMITTED без замка — если первый визит к NPC персонажа
     без строки счёта совпадёт с засчитыванием панели, у него окажутся две строки счёта (дальше — отказ count-ambiguous). Поэтому служба
     засчитывает персонажу без строки счёта, только когда игрок не в игре (domains/attendance._first_visit_guard).
   ПРАВА: asda_ops — только EXECUTE adm.AttendanceAdjust (цепочка владения dbo); прямой записи в dbo.Attendance* и журнал — нет
     (adminc_11_verify_ops: «AttendanceDetail DELETE» / «AttendanceCount UPDATE» = 0 остаются). Журнал читает asda_admin (db_datareader Joy1).
   Запуск — deploy/deploy_admin_center.py ПОСЛЕ adminc_04_ops.sql (sqlcmd -S lpc:.\SQLEXPRESS -E -x -I). Проверка — adminc_10 / adminc_11.
   Откат — adminc_99_rollback.sql (процедура и право; журнал adm.AttendanceAdjustLog НЕ удаляется — по нему видно, что и кому отмечено).
   Нет таблиц посещаемости (dbo.AttendanceCount / dbo.AttendanceDetail) — отказ установки без изменений.
*/
SET NOCOUNT ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
SET ANSI_NULLS ON;
GO
USE [Joy1];
GO
IF OBJECT_ID(N'dbo.AttendanceCount', N'U') IS NULL OR OBJECT_ID(N'dbo.AttendanceDetail', N'U') IS NULL OR OBJECT_ID(N'dbo.Charinfo', N'U') IS NULL
    RAISERROR(N'adminc_25: в Joy1 нет таблиц посещаемости (dbo.AttendanceCount, dbo.AttendanceDetail) или dbo.Charinfo - ничего не создано', 16, 1);
GO
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'adm.AttendanceAdjustLog', N'U') IS NULL
CREATE TABLE adm.AttendanceAdjustLog (
    id              BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_AttendanceAdjustLog PRIMARY KEY,
    req_key         UNIQUEIDENTIFIER NOT NULL CONSTRAINT UQ_AttendanceAdjustLog_Key UNIQUE,   -- ключ запроса: повтор ничего не пишет второй раз
    userindex       INT             NOT NULL,                                                -- учётка
    charidx         TINYINT         NOT NULL,                                                -- слот персонажа
    day             DATE            NOT NULL,                                                -- засчитанный / снятый день
    delta           SMALLINT        NOT NULL CONSTRAINT CK_AttendanceAdjustLog_Delta CHECK (delta IN (-1, 1)),   -- +1 засчитан, −1 снят
    count_before    INT             NOT NULL,                                                -- ACount было (строки нет — 0)
    count_after     INT             NOT NULL,                                                -- ACount стало
    adno            INT             NULL,                                                    -- строка AttendanceDetail: вставленная / удалённая
    regist          DATETIME        NULL,                                                    -- её RegistDay (для возврата снятой)
    note            VARCHAR(50)     NULL,                                                    -- её Note (для возврата снятой)
    acno            INT             NULL,                                                    -- строка AttendanceCount
    count_created   BIT             NOT NULL CONSTRAINT DF_AttendanceAdjustLog_Created DEFAULT (0),   -- строку счёта создала эта правка
    count_deleted   BIT             NOT NULL CONSTRAINT DF_AttendanceAdjustLog_Deleted DEFAULT (0),   -- строку счёта удалил этот откат
    reason          NVARCHAR(400)   NOT NULL CONSTRAINT CK_AttendanceAdjustLog_Reason CHECK (LEN(reason) > 0),   -- причина (обязательна)
    operator        VARCHAR(64)     NOT NULL,                                                -- логин панели
    via             VARCHAR(8)      NOT NULL,                                                -- web | cli | test
    undo_of         BIGINT          NULL CONSTRAINT FK_AttendanceAdjustLog_Undo REFERENCES adm.AttendanceAdjustLog(id),   -- откат какой строки
    undone_by       BIGINT          NULL,                                                    -- строка-откат этой
    created_at      DATETIME2(0)    NOT NULL CONSTRAINT DF_AttendanceAdjustLog_At DEFAULT (SYSUTCDATETIME()),   -- UTC
    created_local   DATETIME        NOT NULL CONSTRAINT DF_AttendanceAdjustLog_Local DEFAULT (GETDATE())        -- часы сервера (сутки OP_Attendance)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'adm.AttendanceAdjustLog') AND name = N'IX_AttendanceAdjustLog_Char')
    CREATE INDEX IX_AttendanceAdjustLog_Char ON adm.AttendanceAdjustLog (userindex, charidx, id);
GO
CREATE OR ALTER PROCEDURE adm.AttendanceAdjust
    @Userindex      INT,                   -- учётка
    @Charidx        TINYINT,               -- слот
    @Day            CHAR(8),               -- день ГГГГММДД
    @Delta          SMALLINT,              -- +1 засчитать, −1 снять (откат: обратный знак исходной строки)
    @Reason         NVARCHAR(400),         -- причина (5…300 знаков)
    @Operator       VARCHAR(64),           -- логин панели
    @Via            VARCHAR(8),            -- web | cli | test
    @ReqKey         UNIQUEIDENTIFIER,      -- ключ запроса (идемпотентность)
    @ExpectCount    INT = NULL,            -- ACount на предпросмотре (NULL — не сверять)
    @UndoOf         BIGINT = NULL,         -- откат: номер исходной строки журнала
    @Dry            BIT = 0                -- 1 — только проверки (предпросмотр панели)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @own BIT = CASE WHEN @@TRANCOUNT = 0 THEN 1 ELSE 0 END;
    DECLARE @reason2 NVARCHAR(400) = LTRIM(RTRIM(ISNULL(@Reason, N'')));
    DECLARE @today DATE = CAST(GETDATE() AS DATE);       -- сутки — как у dbo.OP_Attendance (GETDATE, календарная дата)
    DECLARE @d DATE = CASE WHEN @Day LIKE '[12][0-9][0-9][0-9][01][0-9][0-3][0-9]' AND ISDATE(@Day) = 1 THEN CONVERT(DATE, @Day, 112) END;   -- уровень совместимости Joy1 = 100: функций TRY-приведения нет
    DECLARE @d0 DATETIME = CAST(@d AS DATETIME);
    DECLARE @why VARCHAR(32) = NULL, @n INT, @acno INT, @cnt INT, @dn INT, @adno INT, @regist DATETIME, @note VARCHAR(50), @after INT;
    DECLARE @k_id BIGINT, @k_u INT, @k_c TINYINT, @k_day DATE, @k_delta SMALLINT, @k_undo BIGINT, @k_before INT, @k_after INT, @k_adno INT;
    DECLARE @o_u INT, @o_c TINYINT, @o_day DATE, @o_delta SMALLINT, @o_undo BIGINT, @o_by BIGINT, @o_adno INT, @o_regist DATETIME, @o_note VARCHAR(50),
            @o_acno INT, @o_created BIT;
    DECLARE @id BIGINT, @created BIT = 0, @deleted BIT = 0, @newadno INT, @lr INT, @res NVARCHAR(64);

    IF @Userindex IS NULL OR @Userindex < 1 OR @Charidx IS NULL OR @Delta IS NULL OR @Delta NOT IN (-1, 1) OR @ReqKey IS NULL
       OR @Operator IS NULL OR LEN(@Operator) = 0 OR @Via IS NULL OR @Via NOT IN ('web', 'cli', 'test')
        SET @why = 'bad-args';
    ELSE IF LEN(@reason2) < 5 OR LEN(@reason2) > 300
        SET @why = 'bad-reason';
    ELSE IF @d IS NULL
        SET @why = 'bad-day';
    ELSE IF @d >= @today
        SET @why = 'not-past';
    ELSE IF @UndoOf IS NULL AND @d < DATEADD(DAY, -365, @today)
        SET @why = 'too-old';
    IF @why IS NOT NULL
    BEGIN
        SELECT CAST(0 AS INT) AS status, @why AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS INT) AS count_before, CAST(NULL AS INT) AS count_after,
               CAST(NULL AS INT) AS adno, CAST(NULL AS VARCHAR(23)) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
        RETURN;
    END;

    IF @own = 1 BEGIN TRANSACTION;
    -- 0. правки панели этого персонажа — по одной (замок приложения до конца транзакции, не таблиц стока)
    SET @res = CONCAT(N'adm.att:', @Userindex, N'/', @Charidx);
    EXEC @lr = sp_getapplock @Resource = @res, @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 5000;
    IF @lr < 0
    BEGIN
        IF @own = 1 ROLLBACK TRANSACTION;
        SELECT CAST(0 AS INT) AS status, 'busy' AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS INT) AS count_before, CAST(NULL AS INT) AS count_after,
               CAST(NULL AS INT) AS adno, CAST(NULL AS VARCHAR(23)) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
        RETURN;
    END;
    -- 1. ключ запроса: повтор того же — прежний результат без записи; другой запрос с этим ключом — отказ
    SELECT @k_id = id, @k_u = userindex, @k_c = charidx, @k_day = day, @k_delta = delta, @k_undo = undo_of, @k_before = count_before,
           @k_after = count_after, @k_adno = adno
      FROM adm.AttendanceAdjustLog WITH (UPDLOCK, HOLDLOCK) WHERE req_key = @ReqKey;
    IF @k_id IS NOT NULL
    BEGIN
        IF @own = 1 COMMIT TRANSACTION;
        IF @k_u = @Userindex AND @k_c = @Charidx AND @k_day = @d AND @k_delta = @Delta AND ISNULL(@k_undo, 0) = ISNULL(@UndoOf, 0)
            SELECT CAST(2 AS INT) AS status, 'repeat' AS reason, @k_id AS log_id, @k_before AS count_before, @k_after AS count_after, @k_adno AS adno,
                   CAST(NULL AS VARCHAR(23)) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
        ELSE
            SELECT CAST(0 AS INT) AS status, 'key-conflict' AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS INT) AS count_before,
                   CAST(NULL AS INT) AS count_after, CAST(NULL AS INT) AS adno, CAST(NULL AS VARCHAR(23)) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
        RETURN;
    END;
    -- 2. персонаж, строка счёта и строки дня под замком
    IF NOT EXISTS (SELECT 1 FROM dbo.Charinfo WHERE Userindex = @Userindex AND Charidx = @Charidx)   -- без замка: Charinfo пишет GS
        SET @why = 'no-char';
    SELECT @n = COUNT(*), @acno = MIN(ACNo), @cnt = MIN(ACount) FROM dbo.AttendanceCount
     WHERE Userindex = @Userindex AND Charidx = @Charidx AND Step = 2;
    SELECT @dn = COUNT(*), @adno = MIN(ADNo) FROM dbo.AttendanceDetail
     WHERE Userindex = @Userindex AND Charidx = @Charidx AND Step = 2 AND RegistDay >= @d0 AND RegistDay < DATEADD(DAY, 1, @d0);
    SELECT @regist = RegistDay, @note = Note FROM dbo.AttendanceDetail WHERE ADNo = @adno;
    SET @cnt = ISNULL(@cnt, 0);
    IF @why IS NULL AND @n > 1
        SET @why = 'count-ambiguous';
    ELSE IF @why IS NULL AND @ExpectCount IS NOT NULL AND @ExpectCount <> @cnt
        SET @why = 'count-changed';
    -- 3. откат: исходная строка журнала
    IF @why IS NULL AND @UndoOf IS NOT NULL
    BEGIN
        SELECT @o_u = userindex, @o_c = charidx, @o_day = day, @o_delta = delta, @o_undo = undo_of, @o_by = undone_by, @o_adno = adno, @o_regist = regist,
               @o_note = note, @o_acno = acno, @o_created = count_created
          FROM adm.AttendanceAdjustLog WITH (UPDLOCK, HOLDLOCK) WHERE id = @UndoOf;
        SET @why = CASE WHEN @o_u IS NULL THEN 'undo-not-found' WHEN @o_undo IS NOT NULL THEN 'undo-is-undo' WHEN @o_by IS NOT NULL THEN 'undo-repeat'
                        WHEN @o_u <> @Userindex OR @o_c <> @Charidx OR @o_day <> @d OR @o_delta <> -@Delta THEN 'undo-mismatch' END;
        IF @why IS NULL AND @Delta = -1        -- откат засчитывания: та самая строка Detail должна быть на месте
        BEGIN
            SELECT @adno = NULL, @regist = NULL, @note = NULL;
            SELECT @adno = ADNo, @regist = RegistDay, @note = Note FROM dbo.AttendanceDetail
             WHERE (ADNo = @o_adno OR Note = CONCAT('adm #', @UndoOf))  -- снятую и возвращённую откатом строку узнаём по Note (ADNo новый)
               AND Userindex = @Userindex AND Charidx = @Charidx AND Step = 2 AND RegistDay >= @d0 AND RegistDay < DATEADD(DAY, 1, @d0);
            IF @adno IS NULL SET @why = 'undo-row-gone';
            ELSE IF @n = 0 OR @cnt < 1 SET @why = 'count-low';
        END;
        IF @why IS NULL AND @Delta = 1 AND @dn > 0   -- откат снятия: день снова занят (засчитан позже)
            SET @why = 'day-present';
    END
    ELSE IF @why IS NULL AND @Delta = 1 AND @dn > 0
        SET @why = 'day-present';
    ELSE IF @why IS NULL AND @Delta = -1 AND @dn = 0
        SET @why = 'day-absent';
    ELSE IF @why IS NULL AND @Delta = -1 AND @dn > 1
        SET @why = 'day-ambiguous';
    ELSE IF @why IS NULL AND @Delta = -1 AND (@n = 0 OR @cnt < 1)
        SET @why = 'count-low';
    SET @after = @cnt + @Delta;
    IF @why IS NOT NULL
    BEGIN
        IF @own = 1 COMMIT TRANSACTION;
        SELECT CAST(0 AS INT) AS status, @why AS reason, CAST(NULL AS BIGINT) AS log_id, @cnt AS count_before, @after AS count_after,
               @adno AS adno, CONVERT(VARCHAR(23), @regist, 121) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
        RETURN;
    END;
    IF @Dry = 1
    BEGIN
        IF @own = 1 COMMIT TRANSACTION;
        SELECT CAST(3 AS INT) AS status, 'dry-ok' AS reason, CAST(NULL AS BIGINT) AS log_id, @cnt AS count_before, @after AS count_after,
               @adno AS adno, CONVERT(VARCHAR(23), @regist, 121) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
        RETURN;
    END;
    -- 4. запись: строка журнала (номер — в Note засчитанной строки), счёт, строка Detail
    INSERT adm.AttendanceAdjustLog (req_key, userindex, charidx, day, delta, count_before, count_after, reason, operator, via, undo_of)
    VALUES (@ReqKey, @Userindex, @Charidx, @d, @Delta, @cnt, @after, @reason2, @Operator, @Via, @UndoOf);
    SET @id = CAST(SCOPE_IDENTITY() AS BIGINT);
    IF @Delta = 1
    BEGIN
        IF @n = 0
        BEGIN
            INSERT dbo.AttendanceCount (Userindex, Charidx, ACount, Step) VALUES (@Userindex, @Charidx, 1, 2);   -- как OP_Attendance_Insert
            SET @acno = CAST(SCOPE_IDENTITY() AS INT);
            SET @created = 1;
        END
        ELSE
            UPDATE dbo.AttendanceCount SET @after = ACount = ACount + 1 WHERE ACNo = @acno;   -- «стало» — фактическое
        IF @UndoOf IS NULL
            SELECT @regist = @d0, @note = CONCAT('adm #', @id);
        ELSE
            SELECT @regist = @o_regist, @note = @o_note;                          -- откат снятия: прежние RegistDay и Note
        INSERT dbo.AttendanceDetail (Userindex, Charidx, Step, RegistDay, Note) VALUES (@Userindex, @Charidx, 2, @regist, @note);
        SET @newadno = CAST(SCOPE_IDENTITY() AS INT);
        SET @adno = @newadno;
    END
    ELSE
    BEGIN
        DELETE FROM dbo.AttendanceDetail WHERE ADNo = @adno;
        IF @UndoOf IS NOT NULL AND @o_created = 1 AND @acno = @o_acno
        BEGIN
            DELETE FROM dbo.AttendanceCount WHERE ACNo = @acno AND ACount = 1;    -- строку создало засчитывание — без неё как было
            IF @@ROWCOUNT = 1 SELECT @deleted = 1, @after = 0;                     -- (сток мог прибавить сегодня — тогда только −1)
        END;
        IF @deleted = 0
            UPDATE dbo.AttendanceCount SET @after = ACount = ACount - 1 WHERE ACNo = @acno;
    END;
    SET @cnt = @after - @Delta;                                                    -- «было» — фактическое (до этой правки)
    UPDATE adm.AttendanceAdjustLog SET adno = @adno, regist = @regist, note = @note, acno = @acno, count_created = @created, count_deleted = @deleted,
           count_before = @cnt, count_after = @after
     WHERE id = @id;
    IF @UndoOf IS NOT NULL
        UPDATE adm.AttendanceAdjustLog SET undone_by = @id WHERE id = @UndoOf AND undone_by IS NULL;
    IF @own = 1 COMMIT TRANSACTION;
    SELECT CAST(1 AS INT) AS status, 'ok' AS reason, @id AS log_id, @cnt AS count_before, @after AS count_after, @adno AS adno,
           CONVERT(VARCHAR(23), @regist, 121) AS regist, CONVERT(CHAR(8), @today, 112) AS today;
END
GO
/* права логина операций панели asda_ops: только процедура (adminc_04_ops.sql уже выдал пользователя и DENY EXECUTE на схему dbo) */
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops')
BEGIN
    DENY INSERT, UPDATE, DELETE ON adm.AttendanceAdjustLog TO [asda_ops];
    GRANT EXECUTE ON adm.AttendanceAdjust TO [asda_ops];
END
GO
PRINT N'adminc_25: Joy1 adm.AttendanceAdjustLog / adm.AttendanceAdjust; asda_ops — EXECUTE только adm.AttendanceAdjust';
GO
