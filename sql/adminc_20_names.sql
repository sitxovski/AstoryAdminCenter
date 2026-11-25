-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_20_names.sql — отметки очереди имён в базе панели (шаг А6.11, часть «имена», 22.11.2026; domains/namereview.py, отчёт
   Reports/admin_center/impl_a6_econ_20261121.md §А6.11). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ adminc_03_grants.
   Тот же файл самотест выполняет на LocalDB (там пользователя asda_admin нет — выдача прав пропускается). Повторный запуск безопасен.

   adm.NameReview — отметка «ок / сменить» имени персонажа (операция names.mark, право names.review): учётка и слот, БАЙТЫ имени на момент
                    отметки (name_bin — как CAST(Charname AS varbinary(20)) Joy1.Charinfo; имя изменилось — отметка недействительна), решение
                    (ok — имя годно, rename — сменить: смену делает операция char.rename), код проверки на момент отметки (0, r1…r7, oper,
                    charset), пояснение, кто и откуда. Новая отметка не правит старую — дописывается (последняя по id — действующая).
   Пишет только служба панели; игровые базы не трогаются.
   Права asda_admin: SELECT, INSERT (менять и удалять нельзя: история).
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (у sqlcmd по умолчанию QUOTED_IDENTIFIER OFF, урок adminc_14). */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.NameReview') IS NULL
CREATE TABLE adm.NameReview (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_NameReview PRIMARY KEY,
    Userindex       INT            NOT NULL,
    Charidx         TINYINT        NOT NULL,
    name_bin        VARBINARY(20)  NOT NULL,
    verdict         VARCHAR(8)     NOT NULL,
    rule_at_mark    VARCHAR(8)     NULL,
    note            NVARCHAR(200)  NOT NULL CONSTRAINT DF_adm_NameReview_note DEFAULT N'',
    marked_by       NVARCHAR(32)   NOT NULL,
    via             VARCHAR(8)     NOT NULL,
    marked_local    DATETIME2(3)   NOT NULL CONSTRAINT DF_adm_NameReview_local DEFAULT SYSDATETIME(),
    marked_utc      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_NameReview_utc DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_adm_NameReview_verdict CHECK (verdict IN ('ok', 'rename')),
    CONSTRAINT CK_adm_NameReview_uid CHECK (Userindex >= 1)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_NameReview_char' AND object_id = OBJECT_ID(N'adm.NameReview'))
    CREATE INDEX IX_adm_NameReview_char ON adm.NameReview (Userindex, Charidx, id);
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT, INSERT   ON adm.NameReview TO [asda_admin];
    DENY  UPDATE, DELETE   ON adm.NameReview TO [asda_admin];
END
GO
PRINT 'adminc_20_names: OK';
