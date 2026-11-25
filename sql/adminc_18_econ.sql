-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_18_econ.sql — суточный снимок золота на руках (шаг А6.3 «Экономика: золото», 21.11.2026; domains/econ.py, отчёт
   Reports/admin_center/impl_a6_econ_20261121.md §А6.3). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ adminc_03_grants.
   Тот же файл самотест выполняет на LocalDB (там пользователя asda_admin нет — выдача прав пропускается). Повторный запуск безопасен.

   adm.EconDaily     — строка снимка: сумма Joy1.dbo.Item.Amount (Code = 20551) по категориям учёток (игроки > 5000, служебные ≤ 5000),
                       число персонажей и строк Item, время чтения taken_local — часы SQL-сервера (та же шкала, что Edate журналов JoyLog1).
   adm.EconDailyChar — золото каждого персонажа в момент снимка (для «неучтённого» по персонажам: снимок − журналы между снимками).
   Снимок делает служба (core/sched.py DAILY, операция econ.snapshot) или оператор с правом econ.snapshot; игровые базы только читаются.
   Права asda_admin: SELECT, INSERT (менять и удалять нельзя: история).
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (у sqlcmd по умолчанию QUOTED_IDENTIFIER OFF, урок adminc_14). */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.EconDaily') IS NULL
CREATE TABLE adm.EconDaily (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_EconDaily PRIMARY KEY,
    snap_day        CHAR(8)        NOT NULL,
    taken_local     DATETIME2(3)   NOT NULL,
    taken_utc       DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_EconDaily_utc DEFAULT SYSUTCDATETIME(),
    total           BIGINT         NOT NULL,
    players         BIGINT         NOT NULL,
    service         BIGINT         NOT NULL,
    chars_players   INT            NOT NULL,
    chars_service   INT            NOT NULL,
    item_rows       INT            NOT NULL,
    taken_by        NVARCHAR(32)   NOT NULL,
    via             VARCHAR(8)     NOT NULL,
    job_id          INT            NULL,
    CONSTRAINT CK_adm_EconDaily_total CHECK (total = players + service),
    CONSTRAINT CK_adm_EconDaily_day CHECK (snap_day LIKE '[12][0-9][0-9][0-9][01][0-9][0-3][0-9]')
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_EconDaily_taken' AND object_id = OBJECT_ID(N'adm.EconDaily'))
    CREATE INDEX IX_adm_EconDaily_taken ON adm.EconDaily (taken_local);
GO
IF OBJECT_ID(N'adm.EconDailyChar') IS NULL
CREATE TABLE adm.EconDailyChar (
    snap_id         INT            NOT NULL CONSTRAINT FK_adm_EconDailyChar_snap REFERENCES adm.EconDaily (id),
    Userindex       INT            NOT NULL,
    Charidx         TINYINT        NOT NULL,
    amount          BIGINT         NOT NULL,
    CONSTRAINT PK_adm_EconDailyChar PRIMARY KEY (snap_id, Userindex, Charidx)
);
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT, INSERT   ON adm.EconDaily     TO [asda_admin];
    DENY  UPDATE, DELETE   ON adm.EconDaily     TO [asda_admin];
    GRANT SELECT, INSERT   ON adm.EconDailyChar TO [asda_admin];
    DENY  UPDATE, DELETE   ON adm.EconDailyChar TO [asda_admin];
END
GO
PRINT 'adminc_18_econ: OK';
