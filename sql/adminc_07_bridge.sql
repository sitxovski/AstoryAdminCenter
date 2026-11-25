-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_07_bridge.sql — АДМИН-МОСТ P127 (волна А2 «живой канал», 18.11.2026): очередь команд «админ-центр → работающий GameServer»,
   присутствие «кто в игре» от самих GameServer и пульс узлов. Разбор: Reports/admin_center/research_admin_bridge.md §2.3–§2.4;
   документ: AstoryServer/Docs/GameServer/admin-bridge-p127.md.

   РЕШЕНИЯ ВЛАДЕЛЬЦА 18.11: транспорт — очередь в базе AsdaAdmin (фоновая нить AsdaPatch опрашивает своим ODBC, как P53 AcJournal);
   логин asda_bridge — ТОЛЬКО EXECUTE на adm.Bridge* (ни одной таблицы напрямую, ни одной игровой базы); HMAC команды (ключ — в файле
   секретов службы и в ConfigSet\admin_bridge.ini каждого GameServer, в репозитории его нет); каждая команда — не больше одного раза
   (номер строки, атомарный захват UPDATE … OUTPUT, срок); игрок вышел до выполнения — статус 4 «нет на сервере».

   ЗАПУСК: deploy/deploy_admin_center.py — sqlcmd -S lpc:.\SQLEXPRESS -E -d AsdaAdmin, пароль нового логина — переменная окружения
   BridgePw (из secrets\asda_admin.ini, ключ BRIDGE_PASSWORD; в файлах и командной строке его нет). Тот же файл создаёт схему во
   временной базе самотеста LocalDB (tests/selftest.py подставляет $(BridgePw) сам). Повторный запуск безопасен.
   Проверка прав — adminc_12_verify_bridge.sql ПОД asda_bridge. Откат — adminc_99_rollback.sql (блок «мост P127»).

   СТАТУСЫ adm.bridge_cmd.status: 0 новая · 1 захвачена узлом · 2 выполнена · 3 отказ (подпись, данные, правило) · 4 нет на сервере
   (игрок вышел/переехал до такта) · 5 просрочена (никто не взял до deadline) · 6 журнал (узел в режиме Mode=0 «только слушать»).
   Строка в статусе 1 без результата = «неизвестно — проверьте» (сбой узла между выполнением и записью): повторно её не берёт никто.
*/
SET NOCOUNT ON;
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO

/* Узел = процесс GameServer (имя — папка exe: GameServer / Ch2_GameServer / Indun_GameServer). Пульс старше 15 с — «моста нет». */
IF OBJECT_ID(N'adm.bridge_node') IS NULL
CREATE TABLE adm.bridge_node (
    node        VARCHAR(32)   NOT NULL CONSTRAINT PK_adm_bridge_node PRIMARY KEY,
    pid         INT           NOT NULL,
    ver         INT           NOT NULL,               -- Config::kVersion DLL
    proto       INT           NOT NULL,               -- версия протокола моста (1)
    mode        TINYINT       NOT NULL,               -- 0 только слушать, 1 исполнять
    started     DATETIME2(0)  NOT NULL,
    heartbeat   DATETIME2(0)  NOT NULL,
    claimed     INT           NOT NULL CONSTRAINT DF_adm_bridge_node_cl DEFAULT 0,
    done        INT           NOT NULL CONSTRAINT DF_adm_bridge_node_dn DEFAULT 0,
    errors      INT           NOT NULL CONSTRAINT DF_adm_bridge_node_er DEFAULT 0,
    present     INT           NOT NULL CONSTRAINT DF_adm_bridge_node_pr DEFAULT 0
);
GO

/* Кто в игре — по событиям самого GameServer (вход 4001/5058, разрыв слота) и снимку CUser на такте игрока. Ключ — (узел, слот). */
IF OBJECT_ID(N'adm.bridge_presence') IS NULL
CREATE TABLE adm.bridge_presence (
    node        VARCHAR(32)   NOT NULL,
    user_num    SMALLINT      NOT NULL,               -- слот соединения (userNum)
    Userindex   INT           NOT NULL,               -- CUser+0x174 — учётка-владелец персонажа
    Charidx     TINYINT       NOT NULL,               -- CUser+0x18C — слот персонажа
    session_uid INT           NOT NULL,               -- учётка СЕССИИ (вход соулмейтом — партнёр, P48_IdentityOf), иначе = Userindex
    charname    NVARCHAR(32)  NOT NULL,
    map         INT           NOT NULL,
    x           SMALLINT      NOT NULL,
    z           SMALLINT      NOT NULL,
    since       DATETIME2(0)  NOT NULL,
    seen        DATETIME2(0)  NOT NULL,
    CONSTRAINT PK_adm_bridge_presence PRIMARY KEY (node, user_num)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_bridge_presence_uid' AND object_id = OBJECT_ID(N'adm.bridge_presence'))
    CREATE INDEX IX_adm_bridge_presence_uid ON adm.bridge_presence (Userindex, Charidx);
GO

/* Очередь команд. mac = HMAC-SHA256(ключ, "v2|nonce|op|Userindex|Charidx|node|args|ttl|deadline") — hex, нижний регистр;
   deadline — секунды UNIX UTC, ставит панель и подписывает (ревизия 24 К-2: повтор строки с прежней подписью после срока не пройдёт). */
IF OBJECT_ID(N'adm.bridge_cmd') IS NULL
CREATE TABLE adm.bridge_cmd (
    id          BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_bridge_cmd PRIMARY KEY,
    nonce       UNIQUEIDENTIFIER NOT NULL CONSTRAINT UQ_adm_bridge_cmd_nonce UNIQUE,
    audit_id    BIGINT        NULL,                   -- запись adm.audit, ради которой команда (если есть)
    op          VARCHAR(24)   NOT NULL,
    Userindex   INT           NOT NULL,               -- 0 — команда узлу (объявление)
    Charidx     INT           NOT NULL,               -- −1 — любой персонаж учётки на узле
    node        VARCHAR(32)   NULL,                   -- узел-исполнитель (NULL — тот, на котором цель в игре)
    args        NVARCHAR(400) NOT NULL CONSTRAINT DF_adm_bridge_cmd_args DEFAULT N'',
    ttl         INT           NOT NULL,
    mac         CHAR(64)      NOT NULL,
    created_by  NVARCHAR(64)  NOT NULL,
    created     DATETIME2(3)  NOT NULL CONSTRAINT DF_adm_bridge_cmd_created DEFAULT SYSUTCDATETIME(),
    deadline    DATETIME2(3)  NOT NULL,
    status      TINYINT       NOT NULL CONSTRAINT DF_adm_bridge_cmd_status DEFAULT 0,
    claimed_node VARCHAR(32)  NULL,
    claimed     DATETIME2(3)  NULL,
    done        DATETIME2(3)  NULL,
    result_code INT           NULL,
    result      NVARCHAR(400) NULL,
    CONSTRAINT CK_adm_bridge_cmd_status CHECK (status BETWEEN 0 AND 6)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_bridge_cmd_queue' AND object_id = OBJECT_ID(N'adm.bridge_cmd'))
    CREATE INDEX IX_adm_bridge_cmd_queue ON adm.bridge_cmd (status, deadline) INCLUDE (node, Userindex, Charidx);
GO

/* ─────────────── панель: поставить команду ─────────────── */
IF OBJECT_ID(N'adm.BridgeEnqueue', N'P') IS NOT NULL DROP PROCEDURE adm.BridgeEnqueue;
GO
CREATE PROCEDURE adm.BridgeEnqueue
    @nonce UNIQUEIDENTIFIER, @op VARCHAR(24), @Userindex INT, @Charidx INT, @node VARCHAR(32), @args NVARCHAR(400),
    @ttl INT, @mac CHAR(64), @by NVARCHAR(64), @audit_id BIGINT = NULL, @deadline_unix BIGINT = NULL, @id BIGINT OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    -- ★ А2.2 (v81): + probe, exp, title_add, title_del, fame_recalc, notice (узел v80 их отклонит кодом 2 — панель шлёт их только узлам ver ≥ 81)
    -- ★ А5.2 (v83, 21.11.2026): + mob_pop, mob_return (6045 / 6046; узел v82 отклонит кодом 2 — панель шлёт их только узлам ver ≥ 83)
    -- ★ А5.4 (v84, 21.11.2026): + event_set, event_off (6038 / 6040), rank_recalc (6020; узел v83 и ниже отклонит кодом 2 — панель шлёт их
    --   только узлам ver ≥ 84)
    IF @op NOT IN ('kick', 'ping', 'announce', 'move', 'probe', 'exp', 'title_add', 'title_del', 'fame_recalc', 'notice', 'give', 'jump',
                   'mob_pop', 'mob_return', 'event_set', 'event_off', 'rank_recalc')   -- ★ А2.3: + give, jump (v82)
        THROW 51001, N'мост: неизвестная команда', 1;
    IF @ttl IS NULL OR @ttl < 2 OR @ttl > 300 THROW 51002, N'мост: срок команды вне 2…300 с', 1;
    DECLARE @now BIGINT = DATEDIFF(second, '19700101', SYSUTCDATETIME());
    IF @deadline_unix IS NULL OR @deadline_unix <= @now OR @deadline_unix > @now + 300
        THROW 51006, N'мост: подписанный срок (deadline) вне «сейчас…+300 с»', 1;
    IF @mac IS NULL OR LEN(@mac) <> 64 OR @mac LIKE '%[^0-9a-f]%' THROW 51003, N'мост: подпись не hex-64', 1;
    IF @op = 'announce' AND (@node IS NULL OR @Userindex <> 0) THROW 51004, N'мост: объявление ставится узлу (node), без учётки', 1;
    IF @op <> 'announce' AND @Userindex <= 0 THROW 51005, N'мост: нет учётки цели', 1;
    INSERT adm.bridge_cmd (nonce, audit_id, op, Userindex, Charidx, node, args, ttl, mac, created_by, deadline)
    VALUES (@nonce, @audit_id, @op, @Userindex, @Charidx, @node, ISNULL(@args, N''), @ttl, LOWER(@mac), @by,
            DATEADD(second, CAST(@deadline_unix AS INT), CAST('19700101' AS DATETIME2(3))));
    SET @id = SCOPE_IDENTITY();
END
GO

/* ─────────────── узел: старт, пульс, присутствие ─────────────── */
IF OBJECT_ID(N'adm.BridgeNodeStart', N'P') IS NOT NULL DROP PROCEDURE adm.BridgeNodeStart;
GO
CREATE PROCEDURE adm.BridgeNodeStart @node VARCHAR(32), @pid INT, @ver INT, @proto INT, @mode TINYINT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRAN;
    -- присутствие прежнего процесса этого узла недействительно: мост сейчас пришлёт всех заново
    DELETE adm.bridge_presence WHERE node = @node;
    MERGE adm.bridge_node AS t
    USING (SELECT @node AS node) AS s ON t.node = s.node
    WHEN MATCHED THEN UPDATE SET pid = @pid, ver = @ver, proto = @proto, mode = @mode, started = SYSUTCDATETIME(),
                                 heartbeat = SYSUTCDATETIME(), claimed = 0, done = 0, errors = 0, present = 0
    WHEN NOT MATCHED THEN INSERT (node, pid, ver, proto, mode, started, heartbeat)
                          VALUES (@node, @pid, @ver, @proto, @mode, SYSUTCDATETIME(), SYSUTCDATETIME());
    -- команды, захваченные ПРЕЖНИМ процессом узла и не завершённые, остаются в статусе 1 («неизвестно — проверьте»):
    -- повтор запрещён (могли успеть выполниться) — это решает оператор по журналам игры
    COMMIT;
END
GO
IF OBJECT_ID(N'adm.BridgeHeartbeat', N'P') IS NOT NULL DROP PROCEDURE adm.BridgeHeartbeat;
GO
CREATE PROCEDURE adm.BridgeHeartbeat @node VARCHAR(32), @pid INT, @mode TINYINT, @claimed INT, @done INT, @errors INT, @present INT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.bridge_node SET heartbeat = SYSUTCDATETIME(), mode = @mode, claimed = @claimed, done = @done, errors = @errors,
                               present = @present
    WHERE node = @node AND pid = @pid;
    SELECT @@ROWCOUNT AS n;          -- 0 — строку узла перехватил другой процесс с тем же именем (мост сам заново зовёт NodeStart)
END
GO
IF OBJECT_ID(N'adm.BridgePresenceSet', N'P') IS NOT NULL DROP PROCEDURE adm.BridgePresenceSet;
GO
CREATE PROCEDURE adm.BridgePresenceSet @node VARCHAR(32), @num SMALLINT, @uid INT, @idx TINYINT, @suid INT, @name NVARCHAR(32),
                                       @map INT, @x SMALLINT, @z SMALLINT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE adm.bridge_presence
    SET since = CASE WHEN Userindex = @uid AND Charidx = @idx THEN since ELSE SYSUTCDATETIME() END,
        Userindex = @uid, Charidx = @idx, session_uid = @suid, charname = @name, map = @map, x = @x, z = @z, seen = SYSUTCDATETIME()
    WHERE node = @node AND user_num = @num;
    IF @@ROWCOUNT = 0
        INSERT adm.bridge_presence (node, user_num, Userindex, Charidx, session_uid, charname, map, x, z, since, seen)
        VALUES (@node, @num, @uid, @idx, @suid, @name, @map, @x, @z, SYSUTCDATETIME(), SYSUTCDATETIME());
END
GO
IF OBJECT_ID(N'adm.BridgePresenceDel', N'P') IS NOT NULL DROP PROCEDURE adm.BridgePresenceDel;
GO
CREATE PROCEDURE adm.BridgePresenceDel @node VARCHAR(32), @num SMALLINT
AS
BEGIN
    SET NOCOUNT ON;
    DELETE adm.bridge_presence WHERE node = @node AND user_num = @num;
END
GO

/* ─────────────── узел: захват и результат ─────────────── */
IF OBJECT_ID(N'adm.BridgeClaim', N'P') IS NOT NULL DROP PROCEDURE adm.BridgeClaim;
GO
CREATE PROCEDURE adm.BridgeClaim @node VARCHAR(32), @max INT = 16
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @max IS NULL OR @max < 1 SET @max = 1;
    IF @max > 64 SET @max = 64;
    -- просрочка: не взятые до срока — статус 5 (кем бы ни были назначены)
    UPDATE adm.bridge_cmd SET status = 5, done = SYSUTCDATETIME(), result_code = 0, result = N'просрочена: ни один узел не взял до срока'
    WHERE status = 0 AND deadline <= SYSUTCDATETIME();
    -- захват ОДНИМ оператором UPDATE: строка со status = 0 достаётся ровно одному узлу (UPDLOCK + повторная проверка предиката)
    ;WITH q AS (
        SELECT TOP (@max) c.*
        FROM adm.bridge_cmd c WITH (UPDLOCK, READPAST, ROWLOCK)
        WHERE c.status = 0 AND c.deadline > SYSUTCDATETIME()
          AND (c.node = @node
               OR (c.node IS NULL AND EXISTS (SELECT 1 FROM adm.bridge_presence p
                                              WHERE p.node = @node AND p.Userindex = c.Userindex
                                                AND (c.Charidx < 0 OR p.Charidx = c.Charidx))))
        ORDER BY c.id
    )
    UPDATE q SET status = 1, claimed_node = @node, claimed = SYSUTCDATETIME()
    OUTPUT inserted.id, inserted.op, inserted.Userindex, inserted.Charidx, ISNULL(inserted.node, '') AS node, inserted.args,
           LOWER(CONVERT(CHAR(36), inserted.nonce)) AS nonce, inserted.ttl, inserted.mac,
           DATEDIFF(second, SYSUTCDATETIME(), inserted.deadline) AS left_s,
           CAST(DATEDIFF(second, '19700101', inserted.deadline) AS BIGINT) AS deadline_unix;
END
GO
IF OBJECT_ID(N'adm.BridgeResult', N'P') IS NOT NULL DROP PROCEDURE adm.BridgeResult;
GO
CREATE PROCEDURE adm.BridgeResult @id BIGINT, @node VARCHAR(32), @status TINYINT, @code INT, @result NVARCHAR(400)
AS
BEGIN
    SET NOCOUNT ON;
    IF @status NOT IN (2, 3, 4, 6) THROW 51010, N'мост: недопустимый итог команды', 1;
    UPDATE adm.bridge_cmd SET status = @status, done = SYSUTCDATETIME(), result_code = @code, result = @result
    WHERE id = @id AND claimed_node = @node AND status = 1;          -- только своя захваченная и ещё без итога
    SELECT @@ROWCOUNT AS n;
END
GO

/* ─────────────── права ─────────────── */
-- Логин моста: пароль — переменная BridgePw (secrets\asda_admin.ini, BRIDGE_PASSWORD). Только этот файл его создаёт.
-- BridgeDb — имя этой базы (AsdaAdmin; у самотеста — временная база LocalDB)
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'asda_bridge')
    CREATE LOGIN [asda_bridge] WITH PASSWORD = N'$(BridgePw)', DEFAULT_DATABASE = [$(BridgeDb)], CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    ALTER LOGIN [asda_bridge] WITH PASSWORD = N'$(BridgePw)', CHECK_POLICY = ON;
ALTER LOGIN [asda_bridge] ENABLE;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_bridge')
    CREATE USER [asda_bridge] FOR LOGIN [asda_bridge] WITH DEFAULT_SCHEMA = adm;
GO
-- мосту: ТОЛЬКО процедуры узла (ни таблиц, ни BridgeEnqueue — команды ставит только панель)
GRANT EXECUTE ON adm.BridgeNodeStart   TO [asda_bridge];
GRANT EXECUTE ON adm.BridgeHeartbeat   TO [asda_bridge];
GRANT EXECUTE ON adm.BridgePresenceSet TO [asda_bridge];
GRANT EXECUTE ON adm.BridgePresenceDel TO [asda_bridge];
GRANT EXECUTE ON adm.BridgeClaim       TO [asda_bridge];
GRANT EXECUTE ON adm.BridgeResult      TO [asda_bridge];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.bridge_cmd      TO [asda_bridge];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.bridge_presence TO [asda_bridge];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.bridge_node     TO [asda_bridge];
DENY  EXECUTE ON adm.BridgeEnqueue TO [asda_bridge];
GO
-- панели (asda_admin): ставить команды и читать очередь/присутствие/узлы; итог команды пишет только узел
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT EXECUTE ON adm.BridgeEnqueue TO [asda_admin];
    GRANT SELECT ON adm.bridge_cmd      TO [asda_admin];
    GRANT SELECT ON adm.bridge_presence TO [asda_admin];
    GRANT SELECT ON adm.bridge_node     TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.bridge_cmd TO [asda_admin];
    DENY  EXECUTE ON adm.BridgeResult TO [asda_admin];
    DENY  EXECUTE ON adm.BridgeClaim  TO [asda_admin];
END
GO
PRINT 'adminc_07_bridge: OK';
