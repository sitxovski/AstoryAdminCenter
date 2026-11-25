-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_02_schema.sql — таблицы базы AsdaAdmin (схема adm). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin).
   Тот же файл создаёт схему во временной базе самотеста на LocalDB (tests/selftest.py). Повторный запуск безопасен. 16.11.2026. */
SET NOCOUNT ON;
IF SCHEMA_ID(N'adm') IS NULL EXEC(N'CREATE SCHEMA adm AUTHORIZATION dbo');
GO

/* Пользователи панели. Пароль — PBKDF2-SHA256 (соль 16 б, число итераций в строке), второй фактор — TOTP,
   секрет зашифрован ключом из файла секретов сервера (core/auth.py). */
IF OBJECT_ID(N'adm.users') IS NULL
CREATE TABLE adm.users (
    id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_users PRIMARY KEY,
    login          NVARCHAR(32)   NOT NULL CONSTRAINT UQ_adm_users_login UNIQUE,
    display        NVARCHAR(64)   NOT NULL CONSTRAINT DF_adm_users_display DEFAULT N'',
    role           VARCHAR(16)    NOT NULL,
    pw_hash        VARBINARY(32)  NOT NULL,
    pw_salt        VARBINARY(16)  NOT NULL,
    pw_iter        INT            NOT NULL,
    totp_enc       VARBINARY(64)  NULL,
    totp_on        BIT            NOT NULL CONSTRAINT DF_adm_users_totp DEFAULT 0,
    disabled       BIT            NOT NULL CONSTRAINT DF_adm_users_disabled DEFAULT 0,
    fail_count     TINYINT        NOT NULL CONSTRAINT DF_adm_users_fail DEFAULT 0,
    locked_until   DATETIME2(0)   NULL,
    created_at     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_users_created DEFAULT SYSDATETIME(),
    created_by     NVARCHAR(64)   NOT NULL CONSTRAINT DF_adm_users_createdby DEFAULT N'',
    pw_changed_at  DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_users_pwchanged DEFAULT SYSDATETIME(),
    last_login_at  DATETIME2(0)   NULL,
    last_login_ip  VARCHAR(45)    NULL,
    CONSTRAINT CK_adm_users_role CHECK (role IN ('owner','admin','gm','support'))
);
GO

/* Ревизия А0 №10: последний использованный шаг TOTP — код одноразовый. */
IF COL_LENGTH(N'adm.users', N'totp_last') IS NULL ALTER TABLE adm.users ADD totp_last BIGINT NULL;
GO

/* Сессии. В базе только SHA-256 токена (сам токен — в cookie браузера). */
IF OBJECT_ID(N'adm.sessions') IS NULL
CREATE TABLE adm.sessions (
    token_hash   VARBINARY(32)  NOT NULL CONSTRAINT PK_adm_sessions PRIMARY KEY,
    user_id      INT            NOT NULL,
    csrf         VARCHAR(64)    NOT NULL,
    created_at   DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_sessions_created DEFAULT SYSDATETIME(),
    last_seen    DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_sessions_seen DEFAULT SYSDATETIME(),
    expires_abs  DATETIME2(0)   NOT NULL,
    ip           VARCHAR(45)    NOT NULL,
    user_agent   NVARCHAR(200)  NOT NULL CONSTRAINT DF_adm_sessions_ua DEFAULT N'',
    revoked      BIT            NOT NULL CONSTRAINT DF_adm_sessions_revoked DEFAULT 0
);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_sessions_user' AND object_id = OBJECT_ID(N'adm.sessions'))
    CREATE INDEX IX_adm_sessions_user ON adm.sessions (user_id);
GO

/* Журнал действий: кто, когда, откуда, что, над чем, было/стало, итог. Дописывается, не правится. */
IF OBJECT_ID(N'adm.audit') IS NULL
CREATE TABLE adm.audit (
    id           BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_audit PRIMARY KEY,
    at           DATETIME2(3)   NOT NULL CONSTRAINT DF_adm_audit_at DEFAULT SYSDATETIME(),
    user_id      INT            NULL,
    login        NVARCHAR(32)   NOT NULL,
    ip           VARCHAR(45)    NOT NULL CONSTRAINT DF_adm_audit_ip DEFAULT '',
    via          VARCHAR(8)     NOT NULL,              -- web | cli
    action       VARCHAR(64)    NOT NULL,              -- машинное имя операции (auth.login, users.create, …)
    target       NVARCHAR(200)  NOT NULL CONSTRAINT DF_adm_audit_target DEFAULT N'',
    params       NVARCHAR(MAX)  NULL,                  -- JSON параметров (без паролей и секретов)
    before_json  NVARCHAR(MAX)  NULL,                  -- снимок «было» (для отката)
    after_json   NVARCHAR(MAX)  NULL,                  -- снимок «стало»
    result       VARCHAR(16)    NOT NULL,              -- ok | refused | error
    message      NVARCHAR(1000) NOT NULL CONSTRAINT DF_adm_audit_msg DEFAULT N'',
    undo_of      BIGINT         NULL,                  -- эта запись откатывает запись №
    undone_by    BIGINT         NULL                   -- эту запись откатила запись №
);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_audit_at' AND object_id = OBJECT_ID(N'adm.audit'))
    CREATE INDEX IX_adm_audit_at ON adm.audit (at DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_audit_action' AND object_id = OBJECT_ID(N'adm.audit'))
    CREATE INDEX IX_adm_audit_action ON adm.audit (action, at DESC);
GO

/* 19.11, А1 «Учётки» — «закрыть учётку» со сменой пароля (domains/accountclose.py; решение владельца 19.11 п.2: откат возвращает
   прежний пароль). Прежние соль и хеш учётки (те же байты, что лежат в AsdaStoryOp.Us_member — логин панели и так их читает) —
   здесь, а не в журнале adm.audit: журнал секретов не держит и виден в интерфейсе. Ключ — token из after_json записи журнала;
   строка удаляется откатом. Нигде в интерфейсе не показывается. */
IF OBJECT_ID(N'adm.pw_saved') IS NULL
CREATE TABLE adm.pw_saved (
    token        UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_adm_pw_saved PRIMARY KEY,
    uid          INT            NOT NULL,
    old_salt     VARBINARY(16)  NULL,
    old_hash     VARBINARY(32)  NULL,
    old_pwset    DATETIME2(3)   NULL,
    new_salt     VARBINARY(16)  NOT NULL,
    at           DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_pw_saved_at DEFAULT SYSDATETIME()
);
GO

PRINT 'adminc_02_schema: OK';
