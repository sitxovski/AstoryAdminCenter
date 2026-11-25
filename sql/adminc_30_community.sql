-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_30_community.sql — «Сообщество»: копия реестра бота Oracle (заявки в тестеры, тестеры, предупреждения /warn, баны Discord) и очередь
   команд боту (шаг А7.6, 24.11.2026; решение владельца А7 №9 — хозяин реестра заявок и тестеров остаётся бот, его state.json: панель читает
   копию и шлёт боту команды). domains/community.py, бот AstoryAdminCenter/DiscordBot/community_bot.py; отчёт
   Reports/admin_center/impl_a7_releases_20261123.md §А7.6.
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin -x -I) ПОСЛЕ adminc_23_reports (логин бота asda_reports создаёт он). Тот же файл самотест
   выполняет на LocalDB (пользователей asda_admin / asda_reports там может не быть — выдача прав пропускается). Повторный запуск безопасен.

   ПОЧЕМУ ОТДЕЛЬНАЯ ТАБЛИЦА, А НЕ transport = 'botcmd' в adm.Outbox. Путь тот же, что у очереди А7.4 (панель кладёт строку, бот забирает её
   процедурой логином asda_reports с номером захвата, журнал бота на ПК), но строка adm.Outbox — это СООБЩЕНИЕ: text_en NOT NULL, CHECK канала,
   роли-пинга и @everyone, все 9 процедур adminc_28 и экран «Очередь Discord» работают по каналу и тексту. Команде нужны цель (Discord id),
   заявка, роль, ссылка на откатываемую команду и учётка игры — ни одного из этих столбцов там нет, а текста и канала у команды нет. Вклейка
   третьего вида ослабила бы CHECK сообщений (как пришлось сделать в А7.5 с CK_adm_Outbox_route). Отдельная adm.BotCmd: свои CHECK (белый
   список команд и ролей прямо в базе) и свои процедуры, процедуры очереди публикаций строк команд не трогают.
   ★ ревизия 79 М-8 (честно): разделения по ЛОГИНУ нет — жалобы, публикации, Telegram и команды работают под одним asda_reports (один пароль в
   reports.env). Процесс с этим паролем может забрать команду (BotCmdClaim) или подменить снимок (BotSnapPut), но закрыть чужую команду не может:
   adm.BotCmdDone сверяет номер захвата. Заставить бота сделать что-то вне белого списка так нельзя: бот сверяет заявку и участника по своему
   state.json и по Discord, роль — только Beta Tester. Отдельный логин — не делался (решение координатора 24.11).

   КОПИЯ РЕЕСТРА (присылает бот раз в 5 мин и после каждой команды процедурой adm.BotSnapPut; панель только читает):
     adm.BotSnap    — одна строка: когда снят снимок (часы SQL), приём заявок открыт, локдаун, сколько участников на сервере;
     adm.BotApp     — заявки: id карточки в staff-chat (ключ), Discord id и ник подавшего, статус, когда подана, кто и когда решил. Ответы анкеты
                      (опыт, железо, часовой пояс, мотивация) в копию НЕ идут;
     adm.BotTester  — участники с ролью Beta Tester: Discord id и ник;
     adm.BotWarn    — предупреждения /warn: кому, номер, кто выдал (Discord id), причина, когда;
     adm.BotBan     — баны сервера Discord: Discord id, ник, причина бана;
     adm.BotStaff   — ★ р79 М-5 / р80 М-4: известные боту модераторы (защищённая роль или права модерации сейчас; ушедшие с сервера остаются,
                      разжалованные на сервере снимаются) — Discord id, ник, на сервере ли; бан по id участника,
                      которого нет на сервере, бот отклоняет, только если id в этом списке.
   Чего в копии нет никогда: IP, паролей (/password, playtest_accounts.txt), ответов анкеты, списка поприветствованных, токенов.

   КОМАНДЫ adm.BotCmd — одна строка = одно действие бота над одним участником:
     cmd        app_approve / app_reject (решение по заявке, как кнопки Approve / Reject), app_reopen (откат решения: заявка снова на рассмотрении),
                tester_add / tester_remove (роль Beta Tester), warns_clear / warns_restore (снять предупреждения / вернуть снятые — откат),
                ban / unban (бан сервера Discord без удаления сообщений), test (проверочная: бот отмечает «тест» и Discord не вызывает),
                check (★ р79 В-2: проверка цели перед баном с блоком учётки — бот смотрит участника и свои права, в Discord ничего не меняет);
     role_key   только beta_tester (другой роли команда назначить не может — CHECK);
     ref_id     команда, которую откатывает эта (app_reopen, warns_restore и откаты tester_* / ban / unban);
     block_uid / block_audit — учётка игры и запись журнала adm.audit операции account.block / account.unblock, сделанной вместе с баном / разбаном;
     status     7 ждёт блока учётки (бот не берёт) · 0 ждёт бота · 1 бот взял · 2 выполнено · 3 ошибка · 4 отменено · 5 просрочено · 6 тест;
     result     итог бота (что сделано или почему отказ);
     changed    ★ р79 В-1: изменила ли команда что-то на деле (0 — роль уже была, бан уже стоял и т. п.: откатывать нечего);
     undo_json  ★ р79 В-1 / М-6: что именно изменила команда (роль была / не была, статус заявки до, бан стоял / не стоял, снятые варны) — по
                этому откат восстанавливает ровно сделанное; хранится в базе, журнал бота на ПК может вытеснять старое.
   ПРЕДЕЛЫ (adm.BotCmdPut, код итога): 1 — больше 30 команд за час · 2 — больше 200 за сутки · 3 — больше 10 проверочных за час · 4 — неверные поля
     (команда, роль, заявка, ссылка, причина) · 5 — такая же команда тому же участнику уже ждёт бота · 6 — ★ р79: откатываемая команда не
     исполнена или ничего не изменила.
   СРОК: команда живёт 24 ч — позже бот её не берёт («просрочено»).
   ПРАВА
     asda_reports (бот): EXECUTE adm.BotCmdClaim / BotCmdDone / BotSnapPut — и больше ничего (DENY на таблицы и на процедуры панели).
     asda_admin (панель): SELECT семи таблиц; EXECUTE adm.BotCmdPut / BotCmdRelease / BotCmdCancel / BotCmdRetry; прямой записи нет, процедуры
                         бота — DENY.
   Проверка прав бота — adminc_30_community_verify.sql ПОД asda_reports; панели — adminc_10_verify.sql. Откат — adminc_99_rollback.sql.
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (урок adminc_14; методы XML без них не работают). Совместимость с уровнем 100:
   без THROW, IIF, CONCAT, TRY_CONVERT, FORMAT, STRING_SPLIT, CREATE OR ALTER; даты — литералами ГГГГММДД. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO
/* ─────────────── копия реестра бота ─────────────── */
IF OBJECT_ID(N'adm.BotSnap') IS NULL
CREATE TABLE adm.BotSnap (
    id            TINYINT       NOT NULL CONSTRAINT PK_adm_BotSnap PRIMARY KEY CONSTRAINT CK_adm_BotSnap_id CHECK (id = 1),
    taken_utc     DATETIME2(0)  NOT NULL,
    bot           NVARCHAR(64)  NULL,
    apps_open     BIT           NULL,
    lockdown      BIT           NULL,
    members       INT           NULL,
    n_apps        INT           NOT NULL,
    n_testers     INT           NOT NULL,
    n_warns       INT           NOT NULL,
    n_bans        INT           NOT NULL,
    note          NVARCHAR(200) NULL
);
GO
IF OBJECT_ID(N'adm.BotApp') IS NULL
CREATE TABLE adm.BotApp (
    msg_id        BIGINT        NOT NULL CONSTRAINT PK_adm_BotApp PRIMARY KEY,
    uid           BIGINT        NULL,
    user_name     NVARCHAR(100) NULL,
    status        VARCHAR(10)   NOT NULL CONSTRAINT CK_adm_BotApp_status CHECK (status IN ('pending', 'approved', 'rejected')),
    ts_utc        DATETIME2(0)  NULL,
    decided_by    NVARCHAR(100) NULL,
    decided_utc   DATETIME2(0)  NULL,
    in_guild      BIT           NULL,
    is_tester     BIT           NULL
);
GO
IF OBJECT_ID(N'adm.BotTester') IS NULL
CREATE TABLE adm.BotTester (
    uid           BIGINT        NOT NULL CONSTRAINT PK_adm_BotTester PRIMARY KEY,
    user_name     NVARCHAR(100) NULL
);
GO
IF OBJECT_ID(N'adm.BotWarn') IS NULL
CREATE TABLE adm.BotWarn (
    uid           BIGINT        NOT NULL,
    n             INT           NOT NULL,
    mod_uid       BIGINT        NULL,
    reason        NVARCHAR(300) NULL,
    ts_utc        DATETIME2(0)  NULL,
    CONSTRAINT PK_adm_BotWarn PRIMARY KEY (uid, n)
);
GO
IF OBJECT_ID(N'adm.BotBan') IS NULL
CREATE TABLE adm.BotBan (
    uid           BIGINT        NOT NULL CONSTRAINT PK_adm_BotBan PRIMARY KEY,
    user_name     NVARCHAR(100) NULL,
    reason        NVARCHAR(512) NULL
);
GO
IF OBJECT_ID(N'adm.BotStaff') IS NULL
CREATE TABLE adm.BotStaff (                          -- ★ р79 М-5: модераторы, известные боту (id для отказа в бане по id вне сервера)
    uid           BIGINT        NOT NULL CONSTRAINT PK_adm_BotStaff PRIMARY KEY,
    user_name     NVARCHAR(100) NULL,
    on_server     BIT           NULL                 -- ★ р80 М-4: 1 — сейчас на сервере и модератор, 0 — ушёл с сервера (защита по id остаётся)
);
GO
IF COL_LENGTH('adm.BotStaff', 'on_server') IS NULL ALTER TABLE adm.BotStaff ADD on_server BIT NULL;
GO
/* ─────────────── команды боту ─────────────── */
IF OBJECT_ID(N'adm.BotCmd') IS NULL
CREATE TABLE adm.BotCmd (
    id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_BotCmd PRIMARY KEY,
    cmd           VARCHAR(16)   NOT NULL CONSTRAINT CK_adm_BotCmd_cmd CHECK (cmd IN ('app_approve', 'app_reject', 'app_reopen', 'tester_add',
                                         'tester_remove', 'warns_clear', 'warns_restore', 'ban', 'unban', 'test', 'check')),
    target_uid    BIGINT        NOT NULL,
    role_key      VARCHAR(16)   NULL     CONSTRAINT CK_adm_BotCmd_role CHECK (role_key IN ('beta_tester')),
    app_msg_id    BIGINT        NULL,
    ref_id        INT           NULL,
    reason        NVARCHAR(300) NOT NULL,
    block_uid     INT           NULL,
    block_audit   INT           NULL,
    is_test       BIT           NOT NULL CONSTRAINT DF_adm_BotCmd_test DEFAULT (0),
    created_utc   DATETIME2(0)  NOT NULL CONSTRAINT DF_adm_BotCmd_created DEFAULT (SYSUTCDATETIME()),
    created_by    NVARCHAR(32)  NOT NULL,
    expires_utc   DATETIME2(0)  NOT NULL,
    status        TINYINT       NOT NULL CONSTRAINT DF_adm_BotCmd_status DEFAULT (0) CONSTRAINT CK_adm_BotCmd_status CHECK (status BETWEEN 0 AND 7),
    attempts      INT           NOT NULL CONSTRAINT DF_adm_BotCmd_attempts DEFAULT (0),
    claim_nonce   UNIQUEIDENTIFIER NULL,
    claimed_utc   DATETIME2(0)  NULL,
    done_utc      DATETIME2(0)  NULL,
    result        NVARCHAR(400) NULL,
    changed_by    NVARCHAR(32)  NULL,
    changed_utc   DATETIME2(0)  NULL,
    changed       BIT           NULL,
    undo_json     NVARCHAR(MAX) NULL,
    -- цель — Discord id (15–20 цифр), у проверочной — 0; роль — только у команд роли; заявка — только у команд заявки; ссылка — у откатов
    CONSTRAINT CK_adm_BotCmd_target CHECK ((cmd = 'test' AND target_uid = 0) OR (cmd <> 'test' AND target_uid BETWEEN 100000000000000 AND 9223372036854775807)),
    CONSTRAINT CK_adm_BotCmd_rolereq CHECK ((cmd IN ('app_approve', 'tester_add', 'tester_remove') AND role_key = 'beta_tester')
                                            OR (cmd NOT IN ('app_approve', 'tester_add', 'tester_remove') AND role_key IS NULL)),
    CONSTRAINT CK_adm_BotCmd_app CHECK ((cmd IN ('app_approve', 'app_reject', 'app_reopen') AND app_msg_id IS NOT NULL)
                                        OR (cmd NOT IN ('app_approve', 'app_reject', 'app_reopen') AND app_msg_id IS NULL)),
    CONSTRAINT CK_adm_BotCmd_ref CHECK (cmd NOT IN ('app_reopen', 'warns_restore') OR ref_id IS NOT NULL),
    CONSTRAINT CK_adm_BotCmd_reason CHECK (LEN(reason) >= 3)
);
GO
/* ★ р79: доводка таблицы, созданной первой версией шага (24.11 02:22): столбцы итога и белый список с командой check */
IF COL_LENGTH('adm.BotCmd', 'changed') IS NULL ALTER TABLE adm.BotCmd ADD changed BIT NULL;
GO
IF COL_LENGTH('adm.BotCmd', 'undo_json') IS NULL ALTER TABLE adm.BotCmd ADD undo_json NVARCHAR(MAX) NULL;
GO
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_adm_BotCmd_cmd' AND definition NOT LIKE N'%''check''%')
    ALTER TABLE adm.BotCmd DROP CONSTRAINT CK_adm_BotCmd_cmd;
GO
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_adm_BotCmd_cmd')
    ALTER TABLE adm.BotCmd ADD CONSTRAINT CK_adm_BotCmd_cmd CHECK (cmd IN ('app_approve', 'app_reject', 'app_reopen', 'tester_add',
        'tester_remove', 'warns_clear', 'warns_restore', 'ban', 'unban', 'test', 'check'));
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_BotCmd_status' AND object_id = OBJECT_ID(N'adm.BotCmd'))
    CREATE INDEX IX_adm_BotCmd_status ON adm.BotCmd (status, id);
GO
/* ─────────────── панель: поставить команду (белые списки и пределы — здесь же, их не обойти кодом панели) ─────────────── */
IF OBJECT_ID(N'adm.BotCmdPut', N'P') IS NOT NULL DROP PROCEDURE adm.BotCmdPut;
GO
CREATE PROCEDURE adm.BotCmdPut
    @cmd VARCHAR(16), @target BIGINT, @role VARCHAR(16), @app_msg BIGINT, @ref INT, @reason NVARCHAR(400), @block_uid INT,
    @by NVARCHAR(32), @hold BIT, @test BIT, @id INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @id = NULL; SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    SET @reason = LTRIM(RTRIM(ISNULL(@reason, N'')));
    IF @role = '' SET @role = NULL;
    IF ISNULL(@cmd, '') NOT IN ('app_approve', 'app_reject', 'app_reopen', 'tester_add', 'tester_remove', 'warns_clear', 'warns_restore', 'ban', 'unban',
                                'test', 'check')
       OR @target IS NULL OR (@cmd = 'test' AND @target <> 0) OR (@cmd <> 'test' AND (@target < 100000000000000 OR @target > 9223372036854775807))
       OR (@cmd IN ('app_approve', 'tester_add', 'tester_remove') AND ISNULL(@role, '') <> 'beta_tester')
       OR (@cmd NOT IN ('app_approve', 'tester_add', 'tester_remove') AND @role IS NOT NULL)
       OR (@cmd IN ('app_approve', 'app_reject', 'app_reopen') AND @app_msg IS NULL)
       OR (@cmd NOT IN ('app_approve', 'app_reject', 'app_reopen') AND @app_msg IS NOT NULL)
       OR (@cmd IN ('app_reopen', 'warns_restore') AND @ref IS NULL)
       OR LEN(@reason) < 3 OR LEN(@reason) > 300 OR LEN(ISNULL(@by, N'')) < 1
       OR (@cmd = 'test' AND ISNULL(@test, 0) = 0)
    BEGIN
        SET @code = 4; RETURN;
    END
    -- ★ р79 В-1: откатывать можно только выполненную команду, которая что-то изменила (или проверочную);
    -- ★ р80 М-2: откат — той же цели, с тем же признаком «тест», обратной командой из пары, и сам не откат; у app_reopen — та же карточка;
    --   у выполненной (не проверочной) — с сохранёнными данными отката
    IF @ref IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM adm.BotCmd r WHERE r.id = @ref AND r.target_uid = @target AND r.is_test = ISNULL(@test, 0) AND r.ref_id IS NULL
          AND (r.status = 6 OR (r.status = 2 AND r.changed = 1 AND r.undo_json IS NOT NULL))
          AND ((@cmd = 'app_reopen' AND r.cmd IN ('app_approve', 'app_reject') AND r.app_msg_id = @app_msg)
               OR (@cmd = 'tester_add' AND r.cmd = 'tester_remove') OR (@cmd = 'tester_remove' AND r.cmd = 'tester_add')
               OR (@cmd = 'warns_restore' AND r.cmd = 'warns_clear') OR (@cmd = 'unban' AND r.cmd = 'ban') OR (@cmd = 'ban' AND r.cmd = 'unban')))
    BEGIN
        SET @code = 6; RETURN;
    END
    BEGIN TRAN;
    DECLARE @lk INT;
    EXEC @lk = sp_getapplock @Resource = N'adm.BotCmdPut', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0
    BEGIN
        ROLLBACK; RAISERROR(N'очередь команд боту занята, повторите через минуту', 16, 1); RETURN;
    END
    IF ISNULL(@test, 0) = 0 AND (SELECT COUNT(*) FROM adm.BotCmd WHERE is_test = 0 AND created_utc > DATEADD(HOUR, -1, @now)) >= 30
        SET @code = 1;
    ELSE IF ISNULL(@test, 0) = 0 AND (SELECT COUNT(*) FROM adm.BotCmd WHERE is_test = 0 AND created_utc > DATEADD(DAY, -1, @now)) >= 200
        SET @code = 2;
    ELSE IF ISNULL(@test, 0) = 1 AND (SELECT COUNT(*) FROM adm.BotCmd WHERE is_test = 1 AND created_utc > DATEADD(HOUR, -1, @now)) >= 10
        SET @code = 3;
    ELSE IF @cmd <> 'test' AND EXISTS (SELECT 1 FROM adm.BotCmd WHERE cmd = @cmd AND target_uid = @target AND is_test = ISNULL(@test, 0)
                                       AND status IN (0, 1, 7) AND ISNULL(app_msg_id, 0) = ISNULL(@app_msg, 0))
        SET @code = 5;
    ELSE
    BEGIN
        INSERT adm.BotCmd (cmd, target_uid, role_key, app_msg_id, ref_id, reason, block_uid, is_test, created_utc, created_by, expires_utc, status)
        VALUES (@cmd, @target, @role, @app_msg, @ref, LEFT(@reason, 300), @block_uid, ISNULL(@test, 0), @now, LEFT(@by, 32),
                DATEADD(HOUR, 24, @now), CASE WHEN @hold = 1 THEN 7 ELSE 0 END);
        SET @id = SCOPE_IDENTITY();
        SET @code = 0;
    END
    COMMIT;
END
GO
/* блок учётки встал (@ok = 1) — команда отпускается боту с номером записи журнала блока; не встал — отменяется с пометкой. Только из статуса 7. */
IF OBJECT_ID(N'adm.BotCmdRelease', N'P') IS NOT NULL DROP PROCEDURE adm.BotCmdRelease;
GO
CREATE PROCEDURE adm.BotCmdRelease @id INT, @ok BIT, @by NVARCHAR(32), @note NVARCHAR(400), @block_audit INT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.BotCmd SET status = CASE WHEN @ok = 1 THEN 0 ELSE 4 END, block_audit = CASE WHEN @ok = 1 THEN @block_audit ELSE block_audit END,
           result = CASE WHEN @ok = 1 THEN result ELSE LEFT(ISNULL(@note, N''), 400) END, changed_by = LEFT(@by, 32), changed_utc = SYSUTCDATETIME()
    WHERE id = @id AND status = 7;
    SELECT @@ROWCOUNT AS n;
END
GO
/* отменить до исполнения: из «ждёт бота» и «ждёт блока» */
IF OBJECT_ID(N'adm.BotCmdCancel', N'P') IS NOT NULL DROP PROCEDURE adm.BotCmdCancel;
GO
CREATE PROCEDURE adm.BotCmdCancel @id INT, @by NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.BotCmd SET status = 4, changed_by = LEFT(@by, 32), changed_utc = SYSUTCDATETIME()
    WHERE id = @id AND status IN (0, 7);
    SELECT @@ROWCOUNT AS n;
END
GO
/* повторить: после ошибки или если бот взял и не отчитался дольше @stuck_min минут; срок не прошёл, попыток меньше 5. Команды бота повторяемы
   (роль, бан и решение по заявке проверяются по текущему состоянию, снятые предупреждения — по журналу бота на ПК). */
IF OBJECT_ID(N'adm.BotCmdRetry', N'P') IS NOT NULL DROP PROCEDURE adm.BotCmdRetry;
GO
CREATE PROCEDURE adm.BotCmdRetry @id INT, @by NVARCHAR(32), @stuck_min INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    UPDATE adm.BotCmd SET status = 0, claim_nonce = NULL, changed_by = LEFT(@by, 32), changed_utc = @now
    WHERE id = @id AND expires_utc > @now AND attempts < 5
      AND (status = 3 OR (status = 1 AND claimed_utc < DATEADD(MINUTE, -ISNULL(@stuck_min, 10), @now)));
    SELECT @@ROWCOUNT AS n;
END
GO
/* ─────────────── бот: забрать команды, отметить итог, прислать снимок реестра ─────────────── */
IF OBJECT_ID(N'adm.BotCmdClaim', N'P') IS NOT NULL DROP PROCEDURE adm.BotCmdClaim;
GO
CREATE PROCEDURE adm.BotCmdClaim @max INT, @nonce UNIQUEIDENTIFIER = NULL, @test_only BIT = 0
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @max IS NULL OR @max < 1 OR @max > 10
    BEGIN
        RAISERROR(N'команды боту: за раз — от 1 до 10', 16, 1); RETURN;
    END
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    DECLARE @t TABLE (id INT PRIMARY KEY);
    BEGIN TRAN;
    UPDATE adm.BotCmd WITH (UPDLOCK, READPAST) SET status = 5, done_utc = @now, result = N'просрочено: бот не забрал команду за 24 ч'
    WHERE status = 0 AND expires_utc <= @now AND (ISNULL(@test_only, 0) = 0 OR is_test = 1);
    IF @nonce IS NOT NULL
        INSERT @t (id) SELECT id FROM adm.BotCmd WITH (UPDLOCK) WHERE status = 1 AND claim_nonce = @nonce;
    UPDATE c SET status = 1, claimed_utc = @now, claim_nonce = @nonce, attempts = attempts + 1
    OUTPUT INSERTED.id INTO @t
    FROM adm.BotCmd c WITH (UPDLOCK, READPAST)
    WHERE c.id IN (SELECT TOP (@max) id FROM adm.BotCmd WITH (UPDLOCK, READPAST)
                   WHERE status = 0 AND expires_utc > @now AND (ISNULL(@test_only, 0) = 0 OR is_test = 1) ORDER BY id);
    COMMIT;
    -- ★ р79 В-1: у отката — что сделала откатываемая команда (ref_changed, ref_undo): бот восстанавливает ровно это
    SELECT c.id, c.cmd, c.target_uid, c.role_key, c.app_msg_id, c.ref_id, c.reason, c.is_test, c.created_by, c.attempts, c.expires_utc, @now AS now_utc,
           r.changed AS ref_changed, r.undo_json AS ref_undo
    FROM @t t JOIN adm.BotCmd c ON c.id = t.id LEFT JOIN adm.BotCmd r ON r.id = c.ref_id
    ORDER BY c.id;
END
GO
/* бот: итог команды. ★ р79 М-8: только своим номером захвата (@nonce) — чужой процесс с тем же логином чужую команду не закроет.
   @changed — изменила ли команда что-то, @undo — что именно (JSON бота для отката). ★ р80 М-6 / р81 М-5: предел 400 000 байт (200 000 единиц
   UTF-16, бот ставит пометку уже после 190 000 — запас); длиннее — итог
   НЕ пишется (0 строк, бот отмечает команду ошибкой «данные отката слишком длинные»), а не молча без данных отката. */
IF OBJECT_ID(N'adm.BotCmdDone', N'P') IS NOT NULL DROP PROCEDURE adm.BotCmdDone;
GO
CREATE PROCEDURE adm.BotCmdDone @id INT, @ok BIT, @result NVARCHAR(400), @nonce UNIQUEIDENTIFIER, @changed BIT = NULL, @undo NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.BotCmd SET status = CASE WHEN @ok = 1 AND is_test = 1 THEN 6 WHEN @ok = 1 THEN 2 ELSE 3 END,
           done_utc = SYSUTCDATETIME(), result = LEFT(ISNULL(@result, N''), 400),
           changed = CASE WHEN @ok = 1 AND is_test = 0 THEN ISNULL(@changed, 0) ELSE 0 END,
           undo_json = CASE WHEN @ok = 1 AND is_test = 0 THEN @undo ELSE NULL END
    WHERE id = @id AND status = 1 AND claim_nonce = @nonce AND (@ok = 0 OR DATALENGTH(ISNULL(@undo, N'')) <= 400000);   -- ★ р81 М-5: в байтах (UTF-16)
    SELECT @@ROWCOUNT AS n;           -- 0 — команда не в статусе «бот взял» (повторный итог не пишется)
END
GO
/* снимок реестра: XML <s apps_open lockdown members note><a m u n s t db dt g bt/>…<t u n/>…<w u i m r t/>…<b u n r/>…<p u n c/>…</s>; замена целиком в одной
   транзакции. Пределы: текст до 4 000 000 знаков, строк каждого вида до 5000. Время снимка — часы SQL-сервера. */
IF OBJECT_ID(N'adm.BotSnapPut', N'P') IS NOT NULL DROP PROCEDURE adm.BotSnapPut;
GO
CREATE PROCEDURE adm.BotSnapPut @xml NVARCHAR(MAX), @bot NVARCHAR(64)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON; SET ARITHABORT ON;
    IF @xml IS NULL OR LEN(@xml) < 4 OR LEN(@xml) > 4000000
    BEGIN
        RAISERROR(N'снимок реестра: пусто или больше 4 000 000 знаков', 16, 1); RETURN;
    END
    DECLARE @x XML = CAST(@xml AS XML);
    IF @x.exist('/s') = 0
    BEGIN
        RAISERROR(N'снимок реестра: нет корня s', 16, 1); RETURN;
    END
    IF @x.value('count(/s/a)', 'INT') > 5000 OR @x.value('count(/s/t)', 'INT') > 5000 OR @x.value('count(/s/w)', 'INT') > 5000
       OR @x.value('count(/s/b)', 'INT') > 5000 OR @x.value('count(/s/p)', 'INT') > 5000
    BEGIN
        RAISERROR(N'снимок реестра: строк одного вида больше 5000', 16, 1); RETURN;
    END
    BEGIN TRAN;
    DELETE adm.BotApp;
    INSERT adm.BotApp (msg_id, uid, user_name, status, ts_utc, decided_by, decided_utc, in_guild, is_tester)
    SELECT n.value('@m', 'BIGINT'), n.value('@u', 'BIGINT'), LEFT(n.value('@n', 'NVARCHAR(200)'), 100), n.value('@s', 'VARCHAR(10)'),
           CONVERT(DATETIME2(0), n.value('@t', 'VARCHAR(19)'), 126), LEFT(n.value('@db', 'NVARCHAR(200)'), 100),
           CONVERT(DATETIME2(0), n.value('@dt', 'VARCHAR(19)'), 126), n.value('@g', 'BIT'), n.value('@bt', 'BIT')
    FROM @x.nodes('/s/a') AS q(n);
    DELETE adm.BotTester;
    INSERT adm.BotTester (uid, user_name) SELECT n.value('@u', 'BIGINT'), LEFT(n.value('@n', 'NVARCHAR(200)'), 100) FROM @x.nodes('/s/t') AS q(n);
    DELETE adm.BotWarn;
    INSERT adm.BotWarn (uid, n, mod_uid, reason, ts_utc)
    SELECT n.value('@u', 'BIGINT'), n.value('@i', 'INT'), n.value('@m', 'BIGINT'), LEFT(n.value('@r', 'NVARCHAR(600)'), 300),
           CONVERT(DATETIME2(0), n.value('@t', 'VARCHAR(19)'), 126)
    FROM @x.nodes('/s/w') AS q(n);
    DELETE adm.BotBan;
    INSERT adm.BotBan (uid, user_name, reason)
    SELECT n.value('@u', 'BIGINT'), LEFT(n.value('@n', 'NVARCHAR(200)'), 100), LEFT(n.value('@r', 'NVARCHAR(1024)'), 512) FROM @x.nodes('/s/b') AS q(n);
    DELETE adm.BotStaff;
    INSERT adm.BotStaff (uid, user_name, on_server)
    SELECT n.value('@u', 'BIGINT'), LEFT(n.value('@n', 'NVARCHAR(200)'), 100), n.value('@c', 'BIT') FROM @x.nodes('/s/p') AS q(n);
    DELETE adm.BotSnap;
    INSERT adm.BotSnap (id, taken_utc, bot, apps_open, lockdown, members, n_apps, n_testers, n_warns, n_bans, note)
    SELECT 1, SYSUTCDATETIME(), LEFT(@bot, 64), @x.value('(/s/@apps_open)[1]', 'BIT'), @x.value('(/s/@lockdown)[1]', 'BIT'),
           @x.value('(/s/@members)[1]', 'INT'), (SELECT COUNT(*) FROM adm.BotApp), (SELECT COUNT(*) FROM adm.BotTester),
           (SELECT COUNT(*) FROM adm.BotWarn), (SELECT COUNT(*) FROM adm.BotBan), LEFT(@x.value('(/s/@note)[1]', 'NVARCHAR(400)'), 200);
    COMMIT;
    SELECT n_apps, n_testers, n_warns, n_bans FROM adm.BotSnap WHERE id = 1;
END
GO
/* ─────────────── права ─────────────── */
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_reports')
BEGIN
    GRANT EXECUTE ON adm.BotCmdClaim   TO [asda_reports];
    GRANT EXECUTE ON adm.BotCmdDone    TO [asda_reports];
    GRANT EXECUTE ON adm.BotSnapPut    TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotCmd    TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotSnap   TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotApp    TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotTester TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotWarn   TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotBan    TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotStaff  TO [asda_reports];
    DENY  EXECUTE ON adm.BotCmdPut     TO [asda_reports];
    DENY  EXECUTE ON adm.BotCmdRelease TO [asda_reports];
    DENY  EXECUTE ON adm.BotCmdCancel  TO [asda_reports];
    DENY  EXECUTE ON adm.BotCmdRetry   TO [asda_reports];
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.BotCmd    TO [asda_admin];
    GRANT SELECT ON adm.BotSnap   TO [asda_admin];
    GRANT SELECT ON adm.BotApp    TO [asda_admin];
    GRANT SELECT ON adm.BotTester TO [asda_admin];
    GRANT SELECT ON adm.BotWarn   TO [asda_admin];
    GRANT SELECT ON adm.BotBan    TO [asda_admin];
    GRANT SELECT ON adm.BotStaff  TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotCmd    TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotSnap   TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotApp    TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotTester TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotWarn   TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotBan    TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.BotStaff  TO [asda_admin];
    GRANT EXECUTE ON adm.BotCmdPut     TO [asda_admin];
    GRANT EXECUTE ON adm.BotCmdRelease TO [asda_admin];
    GRANT EXECUTE ON adm.BotCmdCancel  TO [asda_admin];
    GRANT EXECUTE ON adm.BotCmdRetry   TO [asda_admin];
    DENY  EXECUTE ON adm.BotCmdClaim   TO [asda_admin];
    DENY  EXECUTE ON adm.BotCmdDone    TO [asda_admin];
    DENY  EXECUTE ON adm.BotSnapPut    TO [asda_admin];
END
GO
PRINT 'adminc_30_community: OK';
