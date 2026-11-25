-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_13_changeset.sql — наборы изменений данных игры (волна А3 «Данные: магазины», план §3.4; разбор
   Reports/admin_center/research_a3_shops.md §3.1). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ
   adminc_03_grants (пользователь asda_admin в AsdaAdmin уже есть). Тот же файл самотест выполняет на LocalDB (там пользователя
   asda_admin нет — выдача прав пропускается). Повторный запуск безопасен. 19.11.2026.

   Набор (adm.changeset) — заголовок, автор, статус, порядок половин, итог проверки (снимок md5 стойки и порта), отметки
   применения половин. Позиции (adm.changeset_item) — ЛОГИЧЕСКИЕ (price, sell.allow, shop6000.add, npcshop.hide,
   booster.weights, package.set, gacha.pool, gacha.price…), не файловые: файлы строит служба при проверке.
   Статусы: draft → checked → approved → applied_server / applied_client → released | rolled_back.
   Права asda_admin: набор — SELECT/INSERT/UPDATE (удалять нельзя: история); позиции — ещё DELETE (правка черновика; служба
   разрешает её только в статусе draft). */
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.changeset') IS NULL
CREATE TABLE adm.changeset (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_changeset PRIMARY KEY,
    title           NVARCHAR(200)  NOT NULL,
    area            VARCHAR(16)    NOT NULL CONSTRAINT DF_adm_changeset_area DEFAULT 'shops',
    author          NVARCHAR(32)   NOT NULL,
    created_at      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_changeset_created DEFAULT SYSUTCDATETIME(),
    updated_at      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_changeset_updated DEFAULT SYSUTCDATETIME(),
    status          VARCHAR(16)    NOT NULL CONSTRAINT DF_adm_changeset_status DEFAULT 'draft',
    order_mode      VARCHAR(16)    NOT NULL CONSTRAINT DF_adm_changeset_order DEFAULT 'together',
    urgent          BIT            NOT NULL CONSTRAINT DF_adm_changeset_urgent DEFAULT 0,
    note            NVARCHAR(1000) NOT NULL CONSTRAINT DF_adm_changeset_note DEFAULT N'',
    check_json      NVARCHAR(MAX)  NULL,
    checked_at      DATETIME2(0)   NULL,
    approved_by     NVARCHAR(32)   NULL,
    approved_at     DATETIME2(0)   NULL,
    server_tag      VARCHAR(40)    NULL,
    server_state    VARCHAR(16)    NOT NULL CONSTRAINT DF_adm_changeset_srv DEFAULT 'none',
    server_at       DATETIME2(0)   NULL,
    client_state    VARCHAR(16)    NOT NULL CONSTRAINT DF_adm_changeset_cli DEFAULT 'none',
    client_at       DATETIME2(0)   NULL,
    client_backup   NVARCHAR(400)  NULL,
    released_at     DATETIME2(0)   NULL,
    last_audit      BIGINT         NULL,
    CONSTRAINT CK_adm_changeset_status CHECK (status IN ('draft','checked','approved','applied_server','applied_client','released','rolled_back')),
    CONSTRAINT CK_adm_changeset_order CHECK (order_mode IN ('together','server_first','client_first')),
    CONSTRAINT CK_adm_changeset_srv CHECK (server_state IN ('none','dry_srv','dry_ok','applied','partial','partial_apply','partial_rollback','unknown','rolled_back')),
    CONSTRAINT CK_adm_changeset_cli CHECK (client_state IN ('none','dry_ok','applying','applied','rolled_back'))
);
GO
IF OBJECT_ID(N'adm.changeset_item') IS NULL
CREATE TABLE adm.changeset_item (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_changeset_item PRIMARY KEY,
    changeset_id    INT            NOT NULL CONSTRAINT FK_adm_changeset_item_cs REFERENCES adm.changeset (id),
    pos             INT            NOT NULL,
    kind            VARCHAR(32)    NOT NULL,
    params          NVARCHAR(MAX)  NOT NULL,
    note            NVARCHAR(400)  NOT NULL CONSTRAINT DF_adm_changeset_item_note DEFAULT N'',
    added_by        NVARCHAR(32)   NOT NULL,
    added_at        DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_changeset_item_added DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_adm_changeset_item_pos UNIQUE (changeset_id, pos)
);
GO
/* Ревизия 30 (19.11): пул гачи реального слота (460 строк ≈ 5,5 тыс. символов) не влезал в NVARCHAR(4000) — М-2; состояния половин
   dry_srv (сверка службой без выкладчика, М-6), partial (выкладка/откат прошли не целиком, В-8/М-8), applying (запись клиента начата, М-7).
   Ревизия 31: partial_apply / partial_rollback (направление, К-5), unknown (после рестарта состояние файлов не прочитано, Н-М3). */
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'adm.changeset_item') AND name = N'params' AND max_length <> -1)
    ALTER TABLE adm.changeset_item ALTER COLUMN params NVARCHAR(MAX) NOT NULL;
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_adm_changeset_srv' AND definition NOT LIKE N'%unknown%')
BEGIN
    ALTER TABLE adm.changeset DROP CONSTRAINT CK_adm_changeset_srv;
    ALTER TABLE adm.changeset ADD CONSTRAINT CK_adm_changeset_srv CHECK (server_state IN ('none','dry_srv','dry_ok','applied','partial','partial_apply','partial_rollback','unknown','rolled_back'));
END
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_adm_changeset_cli' AND definition NOT LIKE N'%applying%')
BEGIN
    ALTER TABLE adm.changeset DROP CONSTRAINT CK_adm_changeset_cli;
    ALTER TABLE adm.changeset ADD CONSTRAINT CK_adm_changeset_cli CHECK (client_state IN ('none','dry_ok','applying','applied','rolled_back'));
END
IF COL_LENGTH(N'adm.changeset', N'server_note') IS NULL ALTER TABLE adm.changeset ADD server_note NVARCHAR(1000) NULL;
/* Ревизия 32 К-6: все метки набора — UTC (умолчания created_at / updated_at / added_at). */
IF EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = N'DF_adm_changeset_created' AND definition NOT LIKE N'%utc%')
BEGIN ALTER TABLE adm.changeset DROP CONSTRAINT DF_adm_changeset_created;
      ALTER TABLE adm.changeset ADD CONSTRAINT DF_adm_changeset_created DEFAULT SYSUTCDATETIME() FOR created_at; END
IF EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = N'DF_adm_changeset_updated' AND definition NOT LIKE N'%utc%')
BEGIN ALTER TABLE adm.changeset DROP CONSTRAINT DF_adm_changeset_updated;
      ALTER TABLE adm.changeset ADD CONSTRAINT DF_adm_changeset_updated DEFAULT SYSUTCDATETIME() FOR updated_at; END
IF EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = N'DF_adm_changeset_item_added' AND definition NOT LIKE N'%utc%')
BEGIN ALTER TABLE adm.changeset_item DROP CONSTRAINT DF_adm_changeset_item_added;
      ALTER TABLE adm.changeset_item ADD CONSTRAINT DF_adm_changeset_item_added DEFAULT SYSUTCDATETIME() FOR added_at; END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT, INSERT, UPDATE         ON adm.changeset      TO [asda_admin];
    DENY  DELETE                         ON adm.changeset      TO [asda_admin];
    GRANT SELECT, INSERT, UPDATE, DELETE ON adm.changeset_item TO [asda_admin];
END
GO
PRINT 'adminc_13_changeset: OK';
