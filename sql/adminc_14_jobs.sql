-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_14_jobs.sql — задания планировщика и прогоны управления стойкой (волна А5.1 «Живое управление», план §3.2 «adm.job — с А5»,
   §5.1; отчёт Reports/admin_center/impl_a5_live_20261121.md). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ
   adminc_03_grants. Тот же файл самотест выполняет на LocalDB (там пользователя asda_admin нет — выдача прав пропускается).
   Повторный запуск безопасен. 20.11.2026.

   Задание (adm.job) — операция core/ops (op + params JSON), время запуска run_at (UTC), исполнитель runner:
     service — поток планировщика службы на сервере (core/sched.py), pc — консоль ПК владельца (asda_admin.py jobs run-due):
     управление стойкой идёт только restart_stack.py, а он работает с ПК (ключ SSH, бот Discord).
   repeat_mode: '' — разово, daily / weekly — после прогона ставится следующее задание (новая строка, prev_id).
   Статусы: pending → running → done | failed | refused; pending → cancelled (оператор) | missed (просрочено больше допуска —
   поздно не запускается). Прямой запуск стойки консолью тоже пишется сюда строкой running (взаимоисключение: одновременно —
   одно управление стойкой, уникальный индекс UX_adm_job_stack_running).
   Права asda_admin: SELECT/INSERT/UPDATE (удалять нельзя: история).
   ★ Сохраняемый вычисляемый столбец с индексом требует QUOTED_IDENTIFIER ON и ANSI_NULLS ON — у sqlcmd по умолчанию QUOTED_IDENTIFIER
   OFF (выкладка 20.11 упала с ошибкой 1934), поэтому SET — отдельным пакетом до CREATE (параметр действует при разборе пакета).
   Соединения службы (ODBC) ставят оба ON сами. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.job') IS NULL
CREATE TABLE adm.job (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_job PRIMARY KEY,
    op              VARCHAR(48)    NOT NULL,
    params          NVARCHAR(MAX)  NOT NULL CONSTRAINT DF_adm_job_params DEFAULT N'{}',
    runner          VARCHAR(8)     NOT NULL,
    run_at          DATETIME2(0)   NOT NULL,
    repeat_mode     VARCHAR(8)     NOT NULL CONSTRAINT DF_adm_job_repeat DEFAULT '',
    status          VARCHAR(10)    NOT NULL CONSTRAINT DF_adm_job_status DEFAULT 'pending',
    note            NVARCHAR(400)  NOT NULL CONSTRAINT DF_adm_job_note DEFAULT N'',
    created_by      NVARCHAR(32)   NOT NULL,
    created_uid     INT            NULL,
    created_role    VARCHAR(16)    NOT NULL,
    created_at      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_job_created DEFAULT SYSUTCDATETIME(),
    started_at      DATETIME2(0)   NULL,
    finished_at     DATETIME2(0)   NULL,
    host            NVARCHAR(64)   NULL,
    result          NVARCHAR(2000) NULL,
    audit_id        BIGINT         NULL,
    prev_id         INT            NULL,
    stack_lock      AS (CASE WHEN status = 'running' AND op LIKE 'stack.%' THEN 0 ELSE -id END) PERSISTED,
    CONSTRAINT CK_adm_job_runner CHECK (runner IN ('service','pc')),
    CONSTRAINT CK_adm_job_repeat CHECK (repeat_mode IN ('','daily','weekly')),
    CONSTRAINT CK_adm_job_status CHECK (status IN ('pending','running','done','failed','refused','cancelled','missed'))
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_job_due' AND object_id = OBJECT_ID(N'adm.job'))
    CREATE INDEX IX_adm_job_due ON adm.job (status, runner, run_at);
GO
/* одновременно — не больше одного управления стойкой: вычисляемый stack_lock = 0 только у running stack.*, у остальных строк −id
   (уникален сам по себе); фильтр индекса по вычисляемому столбцу SQL Server не допускает, поэтому уникальность — без фильтра */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_adm_job_stack_running' AND object_id = OBJECT_ID(N'adm.job'))
    CREATE UNIQUE INDEX UX_adm_job_stack_running ON adm.job (stack_lock);
GO
/* ★ Ревизия 41 (20.11.2026): срок повтора (Н-3 — повтор стойки не вечен) и машина постановки (Н-5 — задание консоли исполняет
   только машина, на которой его поставили). */
IF COL_LENGTH(N'adm.job', N'repeat_until') IS NULL ALTER TABLE adm.job ADD repeat_until DATETIME2(0) NULL;
IF COL_LENGTH(N'adm.job', N'created_host') IS NULL ALTER TABLE adm.job ADD created_host NVARCHAR(64) NULL;
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT, INSERT, UPDATE ON adm.job TO [asda_admin];
    DENY  DELETE                 ON adm.job TO [asda_admin];
END
GO
PRINT 'adminc_14_jobs: OK';
