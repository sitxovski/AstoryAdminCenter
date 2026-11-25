-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_19_acdaily.sql — суточный отчёт античита в базе панели (шаг А6.6, 22.11.2026; domains/acdaily.py, отчёт
   Reports/admin_center/impl_a6_econ_20261121.md §А6.6). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ adminc_03_grants.
   Тот же файл самотест выполняет на LocalDB (там пользователя asda_admin нет — выдача прав пропускается). Повторный запуск безопасен.

   adm.AcDaily — один прогон отчёта AstoryServer/Tools/Anticheat/ac_daily_report.py (код исходника без правок, md5 — code_md5): окно day_from…day_to
                 (ГГГГММДД, сутки по часам сервера), пороги прогона (thr_json — все, thr_over_json — отличные от прежних), итоги
                 (флаги вне списка владельца / фон владельца, метрик с ошибкой и «нет данных»), разбор по метрикам (summary_json: итог,
                 флаги, заметки, таблицы, последние события), все события метрик (events_json, не больше 5000 на метрику — CSV
                 исходника) и текст Markdown исходника (report_md) как есть.
   Пишет служба (core/sched.py DAILY ac.daily 00:20, задание adm.job или оператор с правом ac.daily_run); игровые базы только читаются.
   Права asda_admin: SELECT, INSERT (менять и удалять нельзя: история).
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (у sqlcmd по умолчанию QUOTED_IDENTIFIER OFF, урок adminc_14). */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.AcDaily') IS NULL
CREATE TABLE adm.AcDaily (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_AcDaily PRIMARY KEY,
    day_from        CHAR(8)        NOT NULL,
    day_to          CHAR(8)        NOT NULL,
    days            INT            NOT NULL,
    made_local      DATETIME2(3)   NOT NULL,
    made_utc        DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_AcDaily_utc DEFAULT SYSUTCDATETIME(),
    taken_by        NVARCHAR(32)   NOT NULL,
    via             VARCHAR(8)     NOT NULL,
    job_id          INT            NULL,
    elapsed_ms      INT            NOT NULL,
    metrics_n       INT            NOT NULL,
    flags_out       INT            NOT NULL,
    flags_bg        INT            NOT NULL,
    errors_n        INT            NOT NULL,
    nodata_n        INT            NOT NULL,
    log_files       INT            NOT NULL,
    log_bytes       BIGINT         NOT NULL,
    code_md5        CHAR(32)       NOT NULL,
    thr_json        NVARCHAR(4000) NOT NULL,
    thr_over_json   NVARCHAR(4000) NOT NULL,
    summary_json    NVARCHAR(MAX)  NOT NULL,
    events_json     NVARCHAR(MAX)  NOT NULL,
    report_md       NVARCHAR(MAX)  NOT NULL,
    CONSTRAINT CK_adm_AcDaily_from CHECK (day_from LIKE '[12][0-9][0-9][0-9][01][0-9][0-3][0-9]'),
    CONSTRAINT CK_adm_AcDaily_to CHECK (day_to LIKE '[12][0-9][0-9][0-9][01][0-9][0-3][0-9]'),
    CONSTRAINT CK_adm_AcDaily_days CHECK (days BETWEEN 1 AND 31 AND day_from <= day_to)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_AcDaily_day' AND object_id = OBJECT_ID(N'adm.AcDaily'))
    CREATE INDEX IX_adm_AcDaily_day ON adm.AcDaily (day_to, made_local);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_AcDaily_by' AND object_id = OBJECT_ID(N'adm.AcDaily'))
    CREATE INDEX IX_adm_AcDaily_by ON adm.AcDaily (taken_by, made_utc);
GO
/* ★ ревизия 56 Н-4 (22.11.2026): срок хранения. У asda_admin DELETE запрещён — очистка только этой процедурой (EXECUTE; цепочка владения
   adm → adm.AcDaily): прогоны службы (via = 'sched') старше 400 суток, ручные и задания — старше 90 суток (по made_utc). Сроки зашиты здесь,
   параметров удаления нет: ночную историю не меньше года не стереть ни из панели, ни из консоли. Зовёт служба после ночного прогона. */
IF OBJECT_ID(N'adm.AcDailyPurge', N'P') IS NOT NULL DROP PROCEDURE adm.AcDailyPurge;
GO
CREATE PROCEDURE adm.AcDailyPurge @Sched INT = NULL OUTPUT, @Manual INT = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM adm.AcDaily WHERE via = 'sched' AND made_utc < DATEADD(DAY, -400, SYSUTCDATETIME());
    SET @Sched = @@ROWCOUNT;
    DELETE FROM adm.AcDaily WHERE via <> 'sched' AND made_utc < DATEADD(DAY, -90, SYSUTCDATETIME());
    SET @Manual = @@ROWCOUNT;
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT, INSERT   ON adm.AcDaily TO [asda_admin];
    DENY  UPDATE, DELETE   ON adm.AcDaily TO [asda_admin];
    GRANT EXECUTE          ON adm.AcDailyPurge TO [asda_admin];
END
GO
PRINT 'adminc_19_acdaily: OK';
