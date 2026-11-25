-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_22_gp7adjust.sql — админ-центр, шаг А6.9 «Баланс gp7: начислить и списать». 22.11.2026.

   ЗАЧЕМ. Решение владельца 22.11 (ADMIN_TOOL_PLAN.md §6 п.5, №4): начисление и списание баланса gp7 делать сейчас, только owner, причина
   обязательна, второе подтверждение, журнал корректировок в AsdaStoryLogin рядом с GP7*, лимиты 100 000 за операцию и 500 000 в сутки.
   Спецификация — Reports/admin_center/research_a6_economy_20261121.md §3 строка А6.9. Шлюз gp7 НЕ меняется: баланс он читает из SQL
   на каждый запрос (AstoryServer/Patches/Gp7Gateway/server.js readSqlAccountBalance → dbo.GP7_GetBalance), при testFixedBalance > 0 игрок
   видит фиксированный баланс шлюза, а не базу (server.js readAccountBalance) — правка в базе тогда невидима игроку.

   ЧТО СОЗДАЁТСЯ (база AsdaStoryLogin, схема adm — владелец dbo, как adm в Joy1 / AsdaStoryOp):
     adm.GP7AdjustLog   — журнал корректировок: строка на каждую корректировку (delta > 0 — начислено, < 0 — списано), «было → стало»,
                          причина, оператор панели, ключ запроса (идемпотентность), ссылка на исходную для отката (undo_of / undone_by).
                          Корректировка НЕ пишется в dbo.GP7PurchaseLog — это не выручка и не покупка.
     adm.GP7AdjustLock  — одна строка: замок суточного лимита (UPDLOCK на ней сериализует все корректировки, сумма за сутки считается под ним).
     adm.GP7AdjustNow() — часы суток лимита: SYSDATETIME() (местные часы SQL-сервера, как сутки раздела «Деньги»). Самотест на своём LocalDB
                          подменяет её фиксированными часами; этот установщик при каждой выкладке пересоздаёт её (CREATE OR ALTER), живой
                          самотест читает её определение по SSH (sysadmin, только SELECT OBJECT_DEFINITION).
     adm.GP7Adjust      — корректировка одной транзакцией (или внутри транзакции панели — фиксирует панель после записи журнала adm.audit).
   ПОРЯДОК ЗАМКОВ (как у процедур шлюза, без взаимоблокировки с ними): adm.GP7AdjustLock → строка журнала по ключу → dbo.[user] (UPDLOCK,
     HOLDLOCK — как GP7_Purchase / GP7_GiftHold) → dbo.GP7Balance (UPDLOCK, HOLDLOCK) → dbo.GP7GiftLog (чтение: открытый HOLD учётки;
     GP7_GiftSettle держит U на строке подарка, чтение S с ним совместимо, а новый HOLD ждёт замок [user]).
     Тестовый режим шлюза (testFixedBalance > 0) — с 22.11.2026 16:27 тот же порядок: пополнение перед покупкой берёт [user] UPDLOCK,
     HOLDLOCK и идёт одной транзакцией с покупкой (server.js 1CBA5CC9, ревизия 63 М-5 / Н-3; до этого корзина брала GP7Balance раньше
     [user]). На любой остаток панель уступает: DEADLOCK_PRIORITY LOW, ошибки 1205 / 1222 — понятный отказ «баланс занят шлюзом»
     (domains/gp7adjust._call), деньги не двигаются (XACT_ABORT, откат).
   РЕЗУЛЬТАТ одной строкой: status (1 — записано, 2 — повтор ключа без движения денег, 3 — предпросмотр @dry = 1 прошёл, 0 — отказ) | reason |
     log_id | user_id | balance_before | balance_after | day_used (сумма суток с этой) | day_max | op_max.
   ОТКАЗЫ (строкой результата, ничего не записано): bad-args, bad-reason, over-op-limit, key-conflict, no-site-account, ambiguous-account,
     open-hold, balance-changed, below-zero, overflow, over-day-limit, undo-not-found, undo-is-undo, undo-repeat, undo-mismatch.
   ЛИМИТЫ — внутри процедуры под замком: |delta| ≤ 100 000 за операцию; сумма |delta| всех корректировок (кроме откатов) за сутки по часам
     adm.GP7AdjustNow() + эта ≤ 500 000 (общий на всех операторов: право money.adjust — только у owner). Откат (undo_of) в лимит не идёт:
     он ровно обратный уже учтённой корректировке и делается один раз; исходная остаётся в счёте суток.
   ПРАВА: asda_ops — EXECUTE adm.GP7Adjust (цепочка владения dbo внутри базы); EXECUTE на схему dbo (процедуры шлюза) — DENY; прямой записи
     в dbo.GP7Balance / журнал — нет (DENY); столбца password не видит (SELECT на [user] не выдан, DENY password). Журнал читает asda_admin
     (db_datareader AsdaStoryLogin, adminc_03). Подписи сертификатом не нужно: объекты одной базы, одного владельца (не как adm.DbBackup*).
   Запуск — deploy/deploy_admin_center.py ПОСЛЕ adminc_04_ops.sql (логин asda_ops уже есть; sqlcmd -S lpc:.\SQLEXPRESS -E). Проверка —
   adminc_11_verify_ops.sql под asda_ops и adminc_10_verify.sql под asda_admin. Откат — adminc_99_rollback.sql (процедура, функция, права;
   журнал adm.GP7AdjustLog НЕ удаляется — по нему видно, кому и сколько начислено).
   Нет таблиц шлюза (dbo.[user], dbo.GP7Balance, dbo.GP7GiftLog) — отказ установки без изменений.
*/
SET NOCOUNT ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
SET ANSI_NULLS ON;
GO
USE [AsdaStoryLogin];
GO
IF OBJECT_ID(N'dbo.[user]', N'U') IS NULL OR OBJECT_ID(N'dbo.GP7Balance', N'U') IS NULL OR OBJECT_ID(N'dbo.GP7GiftLog', N'U') IS NULL
    RAISERROR(N'adminc_22: в AsdaStoryLogin нет таблиц шлюза gp7 (dbo.[user], dbo.GP7Balance, dbo.GP7GiftLog — install_gp7_balance.sql) - ничего не создано', 16, 1);
GO
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'adm.GP7AdjustLog', N'U') IS NULL
CREATE TABLE adm.GP7AdjustLog (
    id              BIGINT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_GP7AdjustLog PRIMARY KEY,
    req_key         UNIQUEIDENTIFIER NOT NULL CONSTRAINT UQ_GP7AdjustLog_Key UNIQUE,      -- ключ запроса: повтор не двигает деньги второй раз
    user_id         BIGINT          NOT NULL CONSTRAINT FK_GP7AdjustLog_User REFERENCES dbo.[user](id),   -- учётка сайта
    username        VARCHAR(50)     NOT NULL,                                               -- её логин на момент корректировки
    delta           BIGINT          NOT NULL CONSTRAINT CK_GP7AdjustLog_Delta CHECK (delta <> 0 AND delta BETWEEN -4294967295 AND 4294967295),
    balance_before  BIGINT          NOT NULL,                                               -- было
    balance_after   BIGINT          NOT NULL CONSTRAINT CK_GP7AdjustLog_After CHECK (balance_after BETWEEN 0 AND 4294967295),   -- стало
    reason          NVARCHAR(400)   NOT NULL CONSTRAINT CK_GP7AdjustLog_Reason CHECK (LEN(reason) > 0),   -- причина (обязательна)
    operator        VARCHAR(64)     NOT NULL,                                               -- логин панели
    via             VARCHAR(8)      NOT NULL,                                               -- web | cli
    undo_of         BIGINT          NULL CONSTRAINT FK_GP7AdjustLog_Undo REFERENCES adm.GP7AdjustLog(id),   -- откат: какую корректировку
    undone_by       BIGINT          NULL,                                                   -- корректировка-откат этой строки
    created_at      DATETIME2(0)    NOT NULL CONSTRAINT DF_GP7AdjustLog_At DEFAULT (SYSUTCDATETIME()),   -- UTC
    created_local   DATETIME2(0)    NOT NULL                                                -- часы суток лимита (adm.GP7AdjustNow)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'adm.GP7AdjustLog') AND name = N'IX_GP7AdjustLog_User')
    CREATE INDEX IX_GP7AdjustLog_User ON adm.GP7AdjustLog (user_id, id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'adm.GP7AdjustLog') AND name = N'IX_GP7AdjustLog_Day')
    CREATE INDEX IX_GP7AdjustLog_Day ON adm.GP7AdjustLog (created_local) INCLUDE (delta, undo_of);
GO
IF OBJECT_ID(N'adm.GP7AdjustLock', N'U') IS NULL
CREATE TABLE adm.GP7AdjustLock (
    id      TINYINT      NOT NULL CONSTRAINT PK_GP7AdjustLock PRIMARY KEY CONSTRAINT CK_GP7AdjustLock_One CHECK (id = 1),   -- одна строка
    note    VARCHAR(80)  NOT NULL                                                                                  -- зачем строка
);
GO
IF NOT EXISTS (SELECT 1 FROM adm.GP7AdjustLock WHERE id = 1)
    INSERT adm.GP7AdjustLock (id, note) VALUES (1, 'UPDLOCK: serializes adm.GP7Adjust (daily limit)');
GO
CREATE OR ALTER FUNCTION adm.GP7AdjustNow() RETURNS DATETIME2(0)
AS
BEGIN
    -- сутки лимита — местные часы SQL-сервера (как сутки раздела «Деньги»); самотест подменяет эту функцию на своём LocalDB
    RETURN SYSDATETIME();
END
GO
CREATE OR ALTER PROCEDURE adm.GP7Adjust
    @username       VARCHAR(50),           -- учётка сайта (dbo.[user].username)
    @delta          BIGINT,                -- > 0 начислить, < 0 списать
    @reason         NVARCHAR(400),         -- причина (5…300 знаков)
    @operator       VARCHAR(64),           -- логин панели
    @via            VARCHAR(8),            -- web | cli
    @req_key        UNIQUEIDENTIFIER,      -- ключ запроса (идемпотентность)
    @expect_before  BIGINT = NULL,         -- баланс на предпросмотре (NULL — не сверять; откат не сверяет)
    @undo_of        BIGINT = NULL,         -- откат: номер исходной корректировки (delta = −её delta)
    @dry            BIT = 0                -- 1 — только проверки и «было → станет» (предпросмотр панели), ничего не пишется
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @op_max BIGINT = 100000;       -- лимит за операцию (решение владельца 22.11)
    DECLARE @day_max BIGINT = 500000;      -- лимит за сутки, общий (решение владельца 22.11)
    DECLARE @own BIT = CASE WHEN @@TRANCOUNT = 0 THEN 1 ELSE 0 END;   -- своя транзакция или транзакция панели (фиксирует панель)
    DECLARE @reason2 NVARCHAR(400) = LTRIM(RTRIM(ISNULL(@reason, N'')));   -- причина без пробелов по краям
    DECLARE @uid BIGINT, @n INT, @bal BIGINT, @after BIGINT, @have BIT = 0, @now DATETIME2(0), @d0 DATETIME2(0), @day BIGINT;
    DECLARE @k_id BIGINT, @k_user BIGINT, @k_delta BIGINT, @k_undo BIGINT, @k_before BIGINT, @k_after BIGINT;   -- строка с тем же ключом
    DECLARE @o_user BIGINT, @o_delta BIGINT, @o_undo BIGINT, @o_by BIGINT;   -- исходная строка отката
    DECLARE @id BIGINT;

    IF @username IS NULL OR LEN(@username) = 0 OR @delta IS NULL OR @delta = 0 OR @delta < -4294967295 OR @delta > 4294967295
       OR @req_key IS NULL OR @operator IS NULL OR LEN(@operator) = 0 OR @via IS NULL OR @via NOT IN ('web', 'cli')
    BEGIN
        SELECT CAST(0 AS INT) AS status, 'bad-args' AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS BIGINT) AS user_id,
               CAST(NULL AS BIGINT) AS balance_before, CAST(NULL AS BIGINT) AS balance_after, CAST(NULL AS BIGINT) AS day_used,
               @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;
    IF LEN(@reason2) < 5 OR LEN(@reason2) > 300
    BEGIN
        SELECT CAST(0 AS INT) AS status, 'bad-reason' AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS BIGINT) AS user_id,
               CAST(NULL AS BIGINT) AS balance_before, CAST(NULL AS BIGINT) AS balance_after, CAST(NULL AS BIGINT) AS day_used,
               @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;
    IF @undo_of IS NULL AND ABS(@delta) > @op_max
    BEGIN
        SELECT CAST(0 AS INT) AS status, 'over-op-limit' AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS BIGINT) AS user_id,
               CAST(NULL AS BIGINT) AS balance_before, CAST(NULL AS BIGINT) AS balance_after, CAST(NULL AS BIGINT) AS day_used,
               @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;

    IF @own = 1 BEGIN TRANSACTION;
    -- 1. замок всех корректировок (суточный лимит считается под ним)
    SELECT @n = COUNT(*) FROM adm.GP7AdjustLock WITH (UPDLOCK, HOLDLOCK) WHERE id = 1;
    SET @now = adm.GP7AdjustNow();
    SET @d0 = CAST(CAST(@now AS DATE) AS DATETIME2(0));
    -- 2. ключ запроса: повтор того же — прежний результат без движения денег; другой запрос с этим ключом — отказ
    SELECT @k_id = id, @k_user = user_id, @k_delta = delta, @k_undo = undo_of, @k_before = balance_before, @k_after = balance_after
      FROM adm.GP7AdjustLog WITH (UPDLOCK, HOLDLOCK) WHERE req_key = @req_key;
    IF @k_id IS NOT NULL
    BEGIN
        SELECT @uid = id FROM dbo.[user] WHERE username = @username;
        SELECT @day = ISNULL(SUM(ABS(delta)), 0) FROM adm.GP7AdjustLog WHERE created_local >= @d0 AND created_local < DATEADD(DAY, 1, @d0) AND undo_of IS NULL;
        IF @own = 1 COMMIT TRANSACTION;
        IF @k_user = @uid AND @k_delta = @delta AND ISNULL(@k_undo, 0) = ISNULL(@undo_of, 0)
            SELECT CAST(2 AS INT) AS status, 'repeat' AS reason, @k_id AS log_id, @k_user AS user_id, @k_before AS balance_before,
                   @k_after AS balance_after, @day AS day_used, @day_max AS day_max, @op_max AS op_max;
        ELSE
            SELECT CAST(0 AS INT) AS status, 'key-conflict' AS reason, CAST(NULL AS BIGINT) AS log_id, CAST(NULL AS BIGINT) AS user_id,
                   CAST(NULL AS BIGINT) AS balance_before, CAST(NULL AS BIGINT) AS balance_after, @day AS day_used, @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;
    -- 3. учётка сайта (замок как у GP7_Purchase: новый HOLD / покупка этой учётки ждут конца корректировки)
    SELECT @n = COUNT(*), @uid = MIN(id) FROM dbo.[user] WITH (UPDLOCK, HOLDLOCK) WHERE username = @username;
    IF @n <> 1
    BEGIN
        IF @own = 1 COMMIT TRANSACTION;
        SELECT CAST(0 AS INT) AS status, CASE WHEN @n = 0 THEN 'no-site-account' ELSE 'ambiguous-account' END AS reason, CAST(NULL AS BIGINT) AS log_id,
               CAST(NULL AS BIGINT) AS user_id, CAST(NULL AS BIGINT) AS balance_before, CAST(NULL AS BIGINT) AS balance_after,
               CAST(NULL AS BIGINT) AS day_used, @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;
    -- 4. баланс (строки нет — было 0, строка появится при записи, как у GP7_GetBalance)
    SELECT @bal = balance, @have = 1 FROM dbo.GP7Balance WITH (UPDLOCK, HOLDLOCK) WHERE user_id = @uid;
    SET @bal = ISNULL(@bal, 0);
    SET @after = @bal + @delta;
    SELECT @day = ISNULL(SUM(ABS(delta)), 0) FROM adm.GP7AdjustLog WHERE created_local >= @d0 AND created_local < DATEADD(DAY, 1, @d0) AND undo_of IS NULL;
    -- 5. отказы по состоянию (ничего ещё не записано)
    DECLARE @why VARCHAR(32) = NULL;
    IF EXISTS (SELECT 1 FROM dbo.GP7GiftLog WHERE sender_user_id = @uid AND state = 'H')
        SET @why = 'open-hold';
    ELSE IF @expect_before IS NOT NULL AND @expect_before <> @bal
        SET @why = 'balance-changed';
    ELSE IF @after < 0
        SET @why = 'below-zero';
    ELSE IF @after > 4294967295
        SET @why = 'overflow';
    ELSE IF @undo_of IS NULL AND @day + ABS(@delta) > @day_max
        SET @why = 'over-day-limit';
    IF @why IS NULL AND @undo_of IS NOT NULL
    BEGIN
        SELECT @o_user = user_id, @o_delta = delta, @o_undo = undo_of, @o_by = undone_by FROM adm.GP7AdjustLog WITH (UPDLOCK, HOLDLOCK) WHERE id = @undo_of;
        SET @why = CASE WHEN @o_user IS NULL THEN 'undo-not-found' WHEN @o_undo IS NOT NULL THEN 'undo-is-undo' WHEN @o_by IS NOT NULL THEN 'undo-repeat'
                        WHEN @o_user <> @uid OR @o_delta <> -@delta THEN 'undo-mismatch' END;
    END;
    IF @why IS NOT NULL
    BEGIN
        IF @own = 1 COMMIT TRANSACTION;
        SELECT CAST(0 AS INT) AS status, @why AS reason, CAST(NULL AS BIGINT) AS log_id, @uid AS user_id, @bal AS balance_before,
               @after AS balance_after, @day AS day_used, @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;
    IF @dry = 1
    BEGIN
        IF @own = 1 COMMIT TRANSACTION;
        SELECT CAST(3 AS INT) AS status, 'dry-ok' AS reason, CAST(NULL AS BIGINT) AS log_id, @uid AS user_id, @bal AS balance_before,
               @after AS balance_after, @day + CASE WHEN @undo_of IS NULL THEN ABS(@delta) ELSE 0 END AS day_used, @day_max AS day_max, @op_max AS op_max;
        RETURN;
    END;
    -- 6. запись: баланс, строка журнала, отметка отката у исходной
    IF @have = 1
        UPDATE dbo.GP7Balance SET balance = @after, updated_at = SYSUTCDATETIME() WHERE user_id = @uid;
    ELSE
        INSERT dbo.GP7Balance (user_id, balance, present) VALUES (@uid, @after, 0);
    INSERT adm.GP7AdjustLog (req_key, user_id, username, delta, balance_before, balance_after, reason, operator, via, undo_of, created_local)
    VALUES (@req_key, @uid, @username, @delta, @bal, @after, @reason2, @operator, @via, @undo_of, @now);
    SET @id = CAST(SCOPE_IDENTITY() AS BIGINT);
    IF @undo_of IS NOT NULL
        UPDATE adm.GP7AdjustLog SET undone_by = @id WHERE id = @undo_of AND undone_by IS NULL;
    IF @own = 1 COMMIT TRANSACTION;
    SELECT CAST(1 AS INT) AS status, 'ok' AS reason, @id AS log_id, @uid AS user_id, @bal AS balance_before, @after AS balance_after,
           @day + CASE WHEN @undo_of IS NULL THEN ABS(@delta) ELSE 0 END AS day_used, @day_max AS day_max, @op_max AS op_max;
END
GO
/* права логина операций панели asda_ops: только процедура корректировки */
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') CREATE USER [asda_ops] FOR LOGIN [asda_ops];
GO
DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [asda_ops];
DENY SELECT ON dbo.[user] (password) TO [asda_ops];
DENY ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.GP7AdjustLog TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON adm.GP7AdjustLock TO [asda_ops];
DENY ALTER ON SCHEMA::adm TO [asda_ops];
GRANT EXECUTE ON adm.GP7Adjust TO [asda_ops];
GO
PRINT N'adminc_22: AsdaStoryLogin adm.GP7AdjustLog / GP7AdjustLock / GP7AdjustNow / GP7Adjust; asda_ops — EXECUTE только adm.GP7Adjust';
GO
