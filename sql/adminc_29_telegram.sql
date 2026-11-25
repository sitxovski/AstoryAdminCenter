-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_29_telegram.sql — уведомления владельцу в Telegram через ту же очередь adm.Outbox (шаг А7.5, 23.11.2026; решение владельца А7 №3 —
   только владельцу, через бота @@@ASTORY_TELEGRAM_BOT@@, только отправка, с ПК; канала для игроков нет; флаги суточного отчёта античита — только на
   экране, А6 №9). domains/notify.py, отправитель — AstoryAdminCenter/DiscordBot/tg_bot.py в боте Oracle на ПК; отчёт
   Reports/admin_center/impl_a7_releases_20261123.md §А7.5.
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin -x -I) ПОСЛЕ adminc_28_outbox. Тот же файл самотест выполняет на LocalDB (пользователей
   asda_admin / asda_reports там может не быть — выдача прав пропускается). Повторный запуск безопасен.

   ПОЧЕМУ ТА ЖЕ ОЧЕРЕДЬ. Сервер Telegram не видит (с @@ASTORY_SERVER_HOSTNAME@@ — тайм-аут, разбор А7 §0 п.1). Служба панели находит событие и кладёт
   строку в adm.Outbox с transport = 'telegram', отправитель на ПК забирает её процедурой adm.TgClaim ТЕМ ЖЕ логином asda_reports, что ответы на
   жалобы и очередь Discord. Токена бота в базе нет и не будет: он лежит только на ПК (telegram.env рядом с ботом). Адресат — один, чат
   владельца из того же файла на ПК; в строке очереди его нет.

   ЧТО ДОБАВЛЯЕТСЯ К adm.Outbox (строки Discord не меняются):
     transport   'telegram' (кроме 'discord'); channel_key 'owner' (единственный адресат Telegram); kind 'notify' (уведомление о событии) и
                 'ping' (настоящее проверочное сообщение по кнопке владельца); 'test' — проверочная запись без сообщения;
     event_key   вид события (список — CHECK ниже = domains/notify.RULES); dedup_key — что именно случилось (склейка повторов);
     repeats     сколько раз то же событие склеено в ещё не отправленную строку; quiet — событие «не срочное»: ночью (23:00–08:00 по часам ПК)
                 отправитель шлёт его без звука (disable_notification), но не задерживает;
     tg_message_id — номер отправленного сообщения в чате владельца.
   ТАБЛИЦЫ
     adm.NotifyRule  — вкл/выкл: строка '_master' — общий выключатель (НЕТ строки = ВЫКЛЮЧЕНО: до слова владельца ничего не ставится), строка
                       вида события — его выключатель (нет строки = включено). Меняет только процедура adm.TgRuleSet (операция владельца).
     adm.NotifyState — память событий: активно ли состояние (EacServer лежит, квота > 80 %), когда последний раз ставилось сообщение, сколько
                       повторов подавлено пределом, курсоры журнала (val). Пишут только процедуры adm.TgNotifyPut / adm.TgStateSet.
     adm.NotifyBeat  — одна строка: служба панели отметилась (проход поиска событий), отправитель на ПК отметился (adm.TgBeatGet). По отметке
                       службы ПК понимает, что служба панели не отвечает.
   ПРЕДЕЛЫ (adm.TgNotifyPut, код итога, не исключение): 0 поставлено · 1 больше 10 уведомлений за час · 2 больше 40 за сутки · 4 неверные поля ·
     5 выключено (общий выключатель или вид события) · 6 склеено с ещё не отправленным тем же событием · 7 подавлено: то же событие ставилось
     меньше @gap_min минут назад (счётчик подавленных — в следующем сообщении). adm.TgTestPut: 3 — больше 10 проверок или 3 настоящих
     проверочных сообщений за час.
   ОТПРАВИТЕЛЬ: adm.TgClaim (UPDLOCK, READPAST, номер захвата), adm.TgDone (итог; @retry = 1 — точный отказ Telegram, строка снова «ждёт», не
     больше 3 попыток), adm.TgBeatGet (отметка службы, выключатели — для «служба панели не отвечает»).
   ПРАВА
     asda_reports (отправитель): EXECUTE adm.TgClaim / TgDone / TgBeatGet / TgLocalNote (★ р77 К-3) — и больше ничего (DENY на таблицы и процедуры панели).
     asda_admin (панель): SELECT adm.NotifyRule / NotifyState / NotifyBeat (adm.Outbox — уже с adminc_28); EXECUTE adm.TgRuleSet / TgNotifyPut /
                         TgStateSet / TgBeatSet / TgTestPut; прямой записи нет (DENY), процедуры отправителя — DENY.
   Проверка прав отправителя — adminc_29_telegram_verify.sql ПОД asda_reports; панели — adminc_10_verify.sql. Откат — adminc_99_rollback.sql.
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (урок adminc_14). Совместимость с уровнем 100: без THROW, IIF, CONCAT,
   TRY_CONVERT, FORMAT, STRING_SPLIT, CREATE OR ALTER; даты — литералами ГГГГММДД. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.Outbox') IS NULL
    RAISERROR(N'adminc_29: нет adm.Outbox — сначала adminc_28_outbox.sql', 16, 1);
GO
/* ─────────────── adm.Outbox: столбцы и ограничения Telegram ─────────────── */
IF COL_LENGTH(N'adm.Outbox', N'event_key') IS NULL ALTER TABLE adm.Outbox ADD event_key VARCHAR(24) NULL;
IF COL_LENGTH(N'adm.Outbox', N'dedup_key') IS NULL ALTER TABLE adm.Outbox ADD dedup_key NVARCHAR(100) NULL;
IF COL_LENGTH(N'adm.Outbox', N'repeats') IS NULL ALTER TABLE adm.Outbox ADD repeats INT NOT NULL CONSTRAINT DF_adm_Outbox_repeats DEFAULT (0);
IF COL_LENGTH(N'adm.Outbox', N'quiet') IS NULL ALTER TABLE adm.Outbox ADD quiet BIT NOT NULL CONSTRAINT DF_adm_Outbox_quiet DEFAULT (0);
IF COL_LENGTH(N'adm.Outbox', N'tg_message_id') IS NULL ALTER TABLE adm.Outbox ADD tg_message_id BIGINT NULL;
-- ★ ревизия 77 М-3: числа подавленных повторов и не поставленных из-за предела — в столбцах (текст сообщения собирает отправитель), склейка их
--   не теряет
IF COL_LENGTH(N'adm.Outbox', N'supp_n') IS NULL ALTER TABLE adm.Outbox ADD supp_n INT NOT NULL CONSTRAINT DF_adm_Outbox_supp DEFAULT (0);
IF COL_LENGTH(N'adm.Outbox', N'over_n') IS NULL ALTER TABLE adm.Outbox ADD over_n INT NOT NULL CONSTRAINT DF_adm_Outbox_over DEFAULT (0);
GO
IF OBJECT_ID(N'adm.CK_adm_Outbox_kind', N'C') IS NOT NULL ALTER TABLE adm.Outbox DROP CONSTRAINT CK_adm_Outbox_kind;
IF OBJECT_ID(N'adm.CK_adm_Outbox_transport', N'C') IS NOT NULL ALTER TABLE adm.Outbox DROP CONSTRAINT CK_adm_Outbox_transport;
IF OBJECT_ID(N'adm.CK_adm_Outbox_channel', N'C') IS NOT NULL ALTER TABLE adm.Outbox DROP CONSTRAINT CK_adm_Outbox_channel;
GO
IF OBJECT_ID(N'adm.CK_adm_Outbox_route', N'C') IS NOT NULL ALTER TABLE adm.Outbox DROP CONSTRAINT CK_adm_Outbox_route;
GO
ALTER TABLE adm.Outbox ADD CONSTRAINT CK_adm_Outbox_route CHECK (
        -- ★ А7.7 (24.11): вид 'notes' — заметки к выпуску (adminc_31_notes.sql, adm.NotesPublishPut), только форум updates
        (transport = 'discord' AND kind IN ('announce', 'test', 'notes') AND channel_key IN ('announcements', 'updates', 'test-info') AND event_key IS NULL
         AND (kind <> 'notes' OR channel_key = 'updates'))
     OR (transport = 'telegram' AND kind IN ('notify', 'ping', 'test', 'local') AND channel_key = 'owner' AND role_key IS NULL
         AND (kind <> 'notify' OR event_key IN ('task_failed', 'stack', 'eac_down', 'backup_failed', 'changeset_apply', 'logdrop_quota',
                                                'release_sign', 'crash_new', 'report_stale'))));
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_Outbox_tg' AND object_id = OBJECT_ID(N'adm.Outbox'))
    CREATE INDEX IX_adm_Outbox_tg ON adm.Outbox (transport, status, id);
GO
/* ─────────────── выключатели, память событий, отметки ─────────────── */
IF OBJECT_ID(N'adm.NotifyRule') IS NULL
CREATE TABLE adm.NotifyRule (
    event_key    VARCHAR(24)   NOT NULL CONSTRAINT PK_adm_NotifyRule PRIMARY KEY
                               CONSTRAINT CK_adm_NotifyRule_key CHECK (event_key IN ('_master', 'panel_down', 'task_failed', 'stack', 'eac_down',
                                   'backup_failed', 'changeset_apply', 'logdrop_quota', 'release_sign', 'crash_new', 'report_stale')),
    enabled      BIT           NOT NULL,
    changed_by   NVARCHAR(32)  NOT NULL,
    changed_utc  DATETIME2(0)  NOT NULL CONSTRAINT DF_adm_NotifyRule_changed DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'adm.NotifyState') IS NULL
CREATE TABLE adm.NotifyState (
    event_key        VARCHAR(24)    NOT NULL,
    item_key         NVARCHAR(100)  NOT NULL,
    active           BIT            NOT NULL CONSTRAINT DF_adm_NotifyState_active DEFAULT (0),
    val              BIGINT         NULL,
    first_utc        DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotifyState_first DEFAULT (SYSUTCDATETIME()),
    changed_utc      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NotifyState_changed DEFAULT (SYSUTCDATETIME()),
    last_put_utc     DATETIME2(0)   NULL,
    last_put_id      INT            NULL,
    suppressed       INT            NOT NULL CONSTRAINT DF_adm_NotifyState_supp DEFAULT (0),
    CONSTRAINT PK_adm_NotifyState PRIMARY KEY (event_key, item_key)
);
GO
-- ★ ревизия 77 М-6: в этом эпизоде уведомление действительно поставлено — только тогда «снова работает»
IF COL_LENGTH(N'adm.NotifyState', N'sent') IS NULL ALTER TABLE adm.NotifyState ADD sent BIT NOT NULL CONSTRAINT DF_adm_NotifyState_sent DEFAULT (0);
GO
IF OBJECT_ID(N'adm.NotifyBeat') IS NULL
CREATE TABLE adm.NotifyBeat (
    id           TINYINT        NOT NULL CONSTRAINT PK_adm_NotifyBeat PRIMARY KEY CONSTRAINT CK_adm_NotifyBeat_one CHECK (id = 1),
    beat_utc     DATETIME2(0)   NULL,
    host         NVARCHAR(64)   NULL,
    note         NVARCHAR(200)  NULL,
    pc_seen_utc  DATETIME2(0)   NULL
);
GO
/* ─────────────── панель ─────────────── */
IF OBJECT_ID(N'adm.TgRuleSet', N'P') IS NOT NULL DROP PROCEDURE adm.TgRuleSet;
GO
CREATE PROCEDURE adm.TgRuleSet @event VARCHAR(24), @enabled BIT, @by NVARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;
    IF @enabled IS NULL OR LEN(ISNULL(@by, N'')) < 1
    BEGIN
        RAISERROR(N'выключатель: нет значения или автора', 16, 1); RETURN;
    END
    UPDATE adm.NotifyRule SET enabled = @enabled, changed_by = LEFT(@by, 32), changed_utc = SYSUTCDATETIME() WHERE event_key = @event;
    IF @@ROWCOUNT = 0
        INSERT adm.NotifyRule (event_key, enabled, changed_by) VALUES (@event, @enabled, LEFT(@by, 32));   -- неизвестный вид — отказ CHECK
    SELECT 1 AS n;
END
GO
/* уведомление о событии: выключатели, склейка, подавление повторов, пределы — здесь, под замком (их не обойти кодом панели).
   ★ ревизия 77 В-1: срочные (stack, eac_down, backup_failed) — вне общего предела и не тратят его, у каждого свой — 6 в час. М-2: упор в предел —
   тоже «попытка» (last_put_utc), напоминание не бьётся в предел каждый проход. М-3: числа подавленных и не поставленных — в столбцах supp_n /
   over_n, склейка их прибавляет. */
IF OBJECT_ID(N'adm.TgNotifyPut', N'P') IS NOT NULL DROP PROCEDURE adm.TgNotifyPut;
GO
CREATE PROCEDURE adm.TgNotifyPut
    @event VARCHAR(24), @key NVARCHAR(100), @title NVARCHAR(100), @text NVARCHAR(1800), @gap_min INT, @quiet BIT, @ttl_min INT, @by NVARCHAR(32),
    @id INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @id = NULL; SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME(), @supp INT, @over INT, @last DATETIME2(0), @pend INT,
            @urgent BIT = CASE WHEN @event IN ('stack', 'eac_down', 'backup_failed') THEN 1 ELSE 0 END;
    SET @key = LTRIM(RTRIM(ISNULL(@key, N''))); SET @title = LTRIM(RTRIM(ISNULL(@title, N''))); SET @text = LTRIM(RTRIM(ISNULL(@text, N'')));
    IF ISNULL(@event, '') NOT IN ('task_failed', 'stack', 'eac_down', 'backup_failed', 'changeset_apply', 'logdrop_quota', 'release_sign',
                                  'crash_new', 'report_stale')
       OR LEN(@key) < 1 OR LEN(@title) < 1 OR LEN(@title) > 100 OR LEN(@text) < 1 OR LEN(@text) > 1500
       OR @gap_min IS NULL OR @gap_min < 0 OR @gap_min > 10080 OR @ttl_min IS NULL OR @ttl_min < 10 OR @ttl_min > 1440 OR LEN(ISNULL(@by, N'')) < 1
       OR (@title + N' ' + @text) LIKE N'%@everyone%' OR (@title + N' ' + @text) LIKE N'%@here%'
    BEGIN
        SET @code = 4; RETURN;
    END
    BEGIN TRAN;
    DECLARE @lk INT;
    EXEC @lk = sp_getapplock @Resource = N'adm.TgNotifyPut', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0
    BEGIN
        ROLLBACK; RAISERROR(N'очередь Telegram занята, повтор в следующем проходе', 16, 1); RETURN;
    END
    IF NOT EXISTS (SELECT 1 FROM adm.NotifyRule WHERE event_key = '_master' AND enabled = 1)
       OR EXISTS (SELECT 1 FROM adm.NotifyRule WHERE event_key = @event AND enabled = 0)
    BEGIN
        COMMIT; SET @code = 5; RETURN;
    END
    IF NOT EXISTS (SELECT 1 FROM adm.NotifyState WHERE event_key = @event AND item_key = @key)
        INSERT adm.NotifyState (event_key, item_key) VALUES (@event, @key);
    IF NOT EXISTS (SELECT 1 FROM adm.NotifyState WHERE event_key = '_overflow' AND item_key = N'all')
        INSERT adm.NotifyState (event_key, item_key) VALUES ('_overflow', N'all');
    SELECT @over = suppressed FROM adm.NotifyState WHERE event_key = '_overflow' AND item_key = N'all';
    -- то же событие ещё не отправлено — склеить: текст свежий, повторов + 1, накопленное «не поставлено из-за предела» — в ту же строку
    SELECT TOP 1 @pend = id FROM adm.Outbox WITH (UPDLOCK)
    WHERE transport = 'telegram' AND kind = 'notify' AND event_key = @event AND dedup_key = @key AND status = 0 ORDER BY id DESC;
    IF @pend IS NOT NULL
    BEGIN
        UPDATE adm.Outbox SET text_en = @text, repeats = repeats + 1, over_n = over_n + ISNULL(@over, 0), changed_by = LEFT(@by, 32), changed_utc = @now
        WHERE id = @pend;
        UPDATE adm.NotifyState SET suppressed = 0 WHERE event_key = '_overflow' AND item_key = N'all';
        COMMIT; SET @id = @pend; SET @code = 6; RETURN;
    END
    SELECT @last = last_put_utc, @supp = suppressed FROM adm.NotifyState WHERE event_key = @event AND item_key = @key;
    IF @last IS NOT NULL AND @last > DATEADD(MINUTE, -@gap_min, @now)
    BEGIN
        UPDATE adm.NotifyState SET suppressed = suppressed + 1 WHERE event_key = @event AND item_key = @key;
        COMMIT; SET @code = 7; RETURN;
    END
    IF @urgent = 1
    BEGIN
        IF @key NOT LIKE N'%:up' AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'notify' AND event_key = @event
                                              AND dedup_key NOT LIKE N'%:up' AND created_utc > DATEADD(HOUR, -1, @now)) >= 6
            SET @code = 1;                         -- ★ р78 К-4: «снова работает» (…:up) не считается и не режется
    END
    ELSE IF (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'notify' AND event_key NOT IN ('stack', 'eac_down', 'backup_failed')
                                              AND created_utc > DATEADD(HOUR, -1, @now)) >= 10
        SET @code = 1;
    ELSE IF (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'notify' AND event_key NOT IN ('stack', 'eac_down', 'backup_failed')
                                                   AND created_utc > DATEADD(DAY, -1, @now)) >= 40
        SET @code = 2;
    IF @code IS NOT NULL
    BEGIN
        -- предел: одно событие — одно число в «не поставлено» (следующее сообщение), попытка запоминается (не повторять каждый проход)
        UPDATE adm.NotifyState SET suppressed = suppressed + 1 WHERE event_key = '_overflow' AND item_key = N'all';
        -- ★ р78 К-4: срочное попытку не запоминает (следующий проход попробует снова); К-6: last_put_id = NULL — «первое не ушло»
        UPDATE adm.NotifyState SET last_put_utc = CASE WHEN @urgent = 1 THEN last_put_utc ELSE @now END, last_put_id = NULL
        WHERE event_key = @event AND item_key = @key;
        COMMIT; RETURN;
    END
    -- ★ р78 К-6: прошлая попытка упёрлась в предел (сообщение не ушло) — подавленные повторы не «ещё», а тоже «не поставлено»
    IF @last IS NOT NULL AND (SELECT last_put_id FROM adm.NotifyState WHERE event_key = @event AND item_key = @key) IS NULL
    BEGIN
        SET @over = ISNULL(@over, 0) + ISNULL(@supp, 0); SET @supp = 0;
    END
    INSERT adm.Outbox (kind, transport, channel_key, role_key, title, text_en, is_test, created_utc, created_by, expires_utc, status,
                       event_key, dedup_key, quiet, supp_n, over_n)
    VALUES ('notify', 'telegram', 'owner', NULL, @title, @text, 0, @now, LEFT(@by, 32), DATEADD(MINUTE, @ttl_min, @now), 0,
            @event, @key, ISNULL(@quiet, 0), ISNULL(@supp, 0), ISNULL(@over, 0));
    SET @id = SCOPE_IDENTITY();
    UPDATE adm.NotifyState SET last_put_utc = @now, last_put_id = @id, suppressed = 0 WHERE event_key = @event AND item_key = @key;
    UPDATE adm.NotifyState SET suppressed = 0 WHERE event_key = '_overflow' AND item_key = N'all';
    SET @code = 0;
    COMMIT;
END
GO
/* память события без сообщения: состояние (active), курсор журнала (val) */
IF OBJECT_ID(N'adm.TgStateSet', N'P') IS NOT NULL DROP PROCEDURE adm.TgStateSet;
GO
CREATE PROCEDURE adm.TgStateSet @event VARCHAR(24), @key NVARCHAR(100), @active BIT, @val BIGINT, @sent BIT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF ISNULL(@event, '') NOT IN ('_cursor', 'task_failed', 'stack', 'eac_down', 'backup_failed', 'changeset_apply', 'logdrop_quota', 'release_sign',
                                  'crash_new', 'report_stale') OR LEN(ISNULL(@key, N'')) < 1 OR LEN(@key) > 100
    BEGIN
        RAISERROR(N'память событий: неверный вид или ключ', 16, 1); RETURN;
    END
    UPDATE adm.NotifyState SET active = ISNULL(@active, active), val = @val, sent = ISNULL(@sent, sent),
           changed_utc = CASE WHEN @active IS NOT NULL AND @active <> active THEN SYSUTCDATETIME() ELSE changed_utc END
    WHERE event_key = @event AND item_key = @key;
    IF @@ROWCOUNT = 0
        INSERT adm.NotifyState (event_key, item_key, active, val, sent) VALUES (@event, @key, ISNULL(@active, 0), @val, ISNULL(@sent, 0));
    SELECT 1 AS n;
END
GO
IF OBJECT_ID(N'adm.TgBeatSet', N'P') IS NOT NULL DROP PROCEDURE adm.TgBeatSet;
GO
CREATE PROCEDURE adm.TgBeatSet @host NVARCHAR(64), @note NVARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.NotifyBeat SET beat_utc = SYSUTCDATETIME(), host = LEFT(@host, 64), note = LEFT(@note, 200) WHERE id = 1;
    IF @@ROWCOUNT = 0
        INSERT adm.NotifyBeat (id, beat_utc, host, note) VALUES (1, SYSUTCDATETIME(), LEFT(@host, 64), LEFT(@note, 200));
    SELECT 1 AS n;
END
GO
/* проверка: 'check' — отправитель вызывает только getMe (сообщения нет), 'selftest' — отправитель только отмечает «тест» (Telegram не вызывается),
   'ping' — НАСТОЯЩЕЕ проверочное сообщение в чат владельца (кнопка владельца; общий выключатель на него не влияет — это и есть первая проверка) */
IF OBJECT_ID(N'adm.TgTestPut', N'P') IS NOT NULL DROP PROCEDURE adm.TgTestPut;
GO
CREATE PROCEDURE adm.TgTestPut @mode VARCHAR(8), @by NVARCHAR(32), @id INT OUTPUT, @code INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @id = NULL; SET @code = NULL;
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    IF ISNULL(@mode, '') NOT IN ('check', 'selftest', 'ping') OR LEN(ISNULL(@by, N'')) < 1
    BEGIN
        SET @code = 4; RETURN;
    END
    BEGIN TRAN;
    DECLARE @lk INT;
    EXEC @lk = sp_getapplock @Resource = N'adm.TgNotifyPut', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 10000;
    IF @lk < 0
    BEGIN
        ROLLBACK; RAISERROR(N'очередь Telegram занята, повторите через минуту', 16, 1); RETURN;
    END
    IF (@mode <> 'ping' AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'test' AND created_utc > DATEADD(HOUR, -1, @now)) >= 10)
       OR (@mode = 'ping' AND (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'ping' AND created_utc > DATEADD(HOUR, -1, @now)) >= 3)
        SET @code = 3;
    ELSE
    BEGIN
        INSERT adm.Outbox (kind, transport, channel_key, role_key, title, text_en, is_test, created_utc, created_by, expires_utc, status)
        VALUES (CASE WHEN @mode = 'ping' THEN 'ping' ELSE 'test' END, 'telegram', 'owner', NULL, @mode,
                CASE WHEN @mode = 'ping' THEN N'Astory: проверочное сообщение админ-центра — уведомления владельцу доходят.'
                     ELSE N'проверочная запись — сообщение не отправляется' END,
                CASE WHEN @mode = 'ping' THEN 0 ELSE 1 END, @now, LEFT(@by, 32), DATEADD(MINUTE, 30, @now), 0);
        SET @id = SCOPE_IDENTITY();
        SET @code = 0;
    END
    COMMIT;
END
GO
/* ─────────────── отправитель на ПК ─────────────── */
IF OBJECT_ID(N'adm.TgClaim', N'P') IS NOT NULL DROP PROCEDURE adm.TgClaim;
GO
CREATE PROCEDURE adm.TgClaim @max INT, @nonce UNIQUEIDENTIFIER = NULL, @test_only BIT = 0
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @max IS NULL OR @max < 1 OR @max > 10
    BEGIN
        RAISERROR(N'очередь Telegram: за раз — от 1 до 10', 16, 1); RETURN;
    END
    DECLARE @now DATETIME2(0) = SYSUTCDATETIME();
    DECLARE @t TABLE (id INT PRIMARY KEY);
    BEGIN TRAN;
    UPDATE adm.Outbox WITH (UPDLOCK, READPAST) SET status = 5, done_utc = @now, error = N'просрочено: отправитель на ПК не забрал запись до срока годности'
    WHERE transport = 'telegram' AND status = 0 AND expires_utc <= @now AND (ISNULL(@test_only, 0) = 0 OR is_test = 1);
    IF @nonce IS NOT NULL
        INSERT @t (id) SELECT id FROM adm.Outbox WITH (UPDLOCK) WHERE transport = 'telegram' AND status = 1 AND claim_nonce = @nonce;
    UPDATE o SET status = 1, claimed_utc = @now, claim_nonce = @nonce, attempts = attempts + 1
    OUTPUT INSERTED.id INTO @t
    FROM adm.Outbox o WITH (UPDLOCK, READPAST)
    WHERE o.id IN (SELECT TOP (@max) id FROM adm.Outbox WITH (UPDLOCK, READPAST)
                   WHERE transport = 'telegram' AND status = 0 AND expires_utc > @now AND (ISNULL(@test_only, 0) = 0 OR is_test = 1)
                   -- ★ р78 К-4: срочные первыми (стойка, EacServer, бэкап), потом обычные, потом не срочные, внутри — по порядку
                   ORDER BY CASE WHEN event_key IN ('stack', 'eac_down', 'backup_failed') THEN 0 WHEN quiet = 1 THEN 2 ELSE 1 END, id);
    COMMIT;
    SELECT o.id, o.kind, o.title, o.text_en, o.is_test, o.quiet, o.event_key, o.repeats, o.expires_utc, o.attempts, @now AS now_utc,
           o.supp_n, o.over_n
    FROM @t t JOIN adm.Outbox o ON o.id = t.id
    ORDER BY CASE WHEN o.event_key IN ('stack', 'eac_down', 'backup_failed') THEN 0 WHEN o.quiet = 1 THEN 2 ELSE 1 END, o.id;
END
GO
IF OBJECT_ID(N'adm.TgDone', N'P') IS NOT NULL DROP PROCEDURE adm.TgDone;
GO
CREATE PROCEDURE adm.TgDone @id INT, @ok BIT, @expired BIT, @retry BIT, @error NVARCHAR(400), @message_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.Outbox SET
           status = CASE WHEN @ok = 1 AND is_test = 1 THEN 6 WHEN @ok = 1 THEN 2 WHEN @expired = 1 THEN 5
                         WHEN @retry = 1 AND attempts < 3 AND expires_utc > SYSUTCDATETIME() THEN 0 ELSE 3 END,
           claim_nonce = CASE WHEN @ok = 0 AND ISNULL(@expired, 0) = 0 AND @retry = 1 AND attempts < 3 AND expires_utc > SYSUTCDATETIME() THEN NULL
                              ELSE claim_nonce END,
           done_utc = SYSUTCDATETIME(), error = NULLIF(LEFT(ISNULL(@error, N''), 400), N''),
           tg_message_id = CASE WHEN @ok = 1 AND is_test = 0 THEN @message_id ELSE NULL END
    WHERE id = @id AND transport = 'telegram' AND status = 1;
    SELECT @@ROWCOUNT AS n;           -- 0 — запись не в статусе «взята» (повторный итог не пишется)
END
GO
/* ★ ревизия 77 К-3: своё сообщение ПК («служба / база не отвечает», «снова отвечает») — строкой очереди для экрана (уже отправлено или нет, kind
   local; отправитель её не берёт: статус сразу итоговый) */
IF OBJECT_ID(N'adm.TgLocalNote', N'P') IS NOT NULL DROP PROCEDURE adm.TgLocalNote;
GO
CREATE PROCEDURE adm.TgLocalNote @kind VARCHAR(16), @text NVARCHAR(400), @ok BIT, @message_id BIGINT, @error NVARCHAR(400)
AS
BEGIN
    SET NOCOUNT ON;
    IF ISNULL(@kind, '') NOT IN ('panel', 'panel_up', 'db', 'db_up') OR LEN(ISNULL(@text, N'')) < 1
    BEGIN
        RAISERROR(N'сообщение ПК: неверный вид или пустой текст', 16, 1); RETURN;
    END
    -- ★ р78 К-8: не больше 30 строк ПК в час (лишние не пишутся, экран не забивается)
    IF (SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'local' AND created_utc > DATEADD(HOUR, -1, SYSUTCDATETIME())) >= 30
    BEGIN
        SELECT 0 AS n; RETURN;
    END
    INSERT adm.Outbox (kind, transport, channel_key, role_key, title, text_en, is_test, created_utc, created_by, expires_utc, status, done_utc,
                       error, tg_message_id, attempts)
    VALUES ('local', 'telegram', 'owner', NULL, @kind, LEFT(@text, 400), 0, SYSUTCDATETIME(), N'pc:tg_bot', SYSUTCDATETIME(),
            CASE WHEN @ok = 1 THEN 2 ELSE 3 END, SYSUTCDATETIME(), NULLIF(LEFT(ISNULL(@error, N''), 400), N''),
            CASE WHEN @ok = 1 THEN @message_id ELSE NULL END, 1);
    SELECT 1 AS n;
END
GO
/* отметка службы панели и выключатели — для «служба панели не отвечает» (её проверяет ПК); заодно отметка «отправитель на ПК жив» */
IF OBJECT_ID(N'adm.TgBeatGet', N'P') IS NOT NULL DROP PROCEDURE adm.TgBeatGet;
GO
CREATE PROCEDURE adm.TgBeatGet
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.NotifyBeat SET pc_seen_utc = SYSUTCDATETIME() WHERE id = 1;
    SELECT b.beat_utc, DATEDIFF(SECOND, b.beat_utc, SYSUTCDATETIME()) AS age_s,
           CAST(CASE WHEN EXISTS (SELECT 1 FROM adm.NotifyRule WHERE event_key = '_master' AND enabled = 1) THEN 1 ELSE 0 END AS BIT) AS master,
           CAST(CASE WHEN EXISTS (SELECT 1 FROM adm.NotifyRule WHERE event_key = 'panel_down' AND enabled = 0) THEN 0 ELSE 1 END AS BIT) AS panel_down,
           SYSUTCDATETIME() AS now_utc
    FROM (SELECT 1 AS one) x LEFT JOIN adm.NotifyBeat b ON b.id = 1;
END
GO
/* ─────────────── права ─────────────── */
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_reports')
BEGIN
    GRANT EXECUTE ON adm.TgClaim     TO [asda_reports];
    GRANT EXECUTE ON adm.TgDone      TO [asda_reports];
    GRANT EXECUTE ON adm.TgBeatGet   TO [asda_reports];
    GRANT EXECUTE ON adm.TgLocalNote TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotifyRule  TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotifyState TO [asda_reports];
    DENY  SELECT, INSERT, UPDATE, DELETE ON adm.NotifyBeat  TO [asda_reports];
    DENY  EXECUTE ON adm.TgRuleSet   TO [asda_reports];
    DENY  EXECUTE ON adm.TgNotifyPut TO [asda_reports];
    DENY  EXECUTE ON adm.TgStateSet  TO [asda_reports];
    DENY  EXECUTE ON adm.TgBeatSet   TO [asda_reports];
    DENY  EXECUTE ON adm.TgTestPut   TO [asda_reports];
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.NotifyRule  TO [asda_admin];
    GRANT SELECT ON adm.NotifyState TO [asda_admin];
    GRANT SELECT ON adm.NotifyBeat  TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotifyRule  TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotifyState TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.NotifyBeat  TO [asda_admin];
    GRANT EXECUTE ON adm.TgRuleSet   TO [asda_admin];
    GRANT EXECUTE ON adm.TgNotifyPut TO [asda_admin];
    GRANT EXECUTE ON adm.TgStateSet  TO [asda_admin];
    GRANT EXECUTE ON adm.TgBeatSet   TO [asda_admin];
    GRANT EXECUTE ON adm.TgTestPut   TO [asda_admin];
    DENY  EXECUTE ON adm.TgClaim     TO [asda_admin];
    DENY  EXECUTE ON adm.TgDone      TO [asda_admin];
    DENY  EXECUTE ON adm.TgBeatGet   TO [asda_admin];
    DENY  EXECUTE ON adm.TgLocalNote TO [asda_admin];
END
GO
PRINT 'adminc_29_telegram: OK';
