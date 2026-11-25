-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_26_releases.sql — снимок конвейера выпуска с ПК владельца для раздела «Выпуски» (шаг А7.1, 23.11.2026; domains/releases.py, отчёт
   Reports/admin_center/impl_a7_releases_20261123.md §А7.1, решение владельца А7 №6 — панель только показывает статус).
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin -x -I) ПОСЛЕ adminc_03_grants. Тот же файл самотест выполняет на LocalDB (там пользователя
   asda_admin нет — выдача прав пропускается). Повторный запуск безопасен.

   adm.ReleasePcStatus — что видит ПК и не видит сервер: releases.log, Build\EAC\latest.json, содержимое DEPLOY\Patch\Inbox, итоги последних
                         прогонов DEPLOY (Patch\Logs, Build\Logs), ключи выпуска «есть / срок» (без ключей и путей к секретам), подписанные на ПК
                         каналы. Пишет консоль ПК (asda_admin.py releases push или задание ПК release.push) логином asda_admin по VPN — тем же
                         путём, каким консоль ПК пишет adm.job. Снимок не изменился (тот же md5) — новая строка не пишется, у последней
                         только отметка «ПК присылал» (seen_utc, seen_count). Изменился — новая строка.
   collected_utc — часы ПК при сборе снимка; pushed_utc / seen_utc — часы сервера SQL (по ним считается «данные ПК от …»).
   Права asda_admin: SELECT, INSERT, UPDATE только seen_utc и seen_count, EXECUTE adm.ReleasePcPrune; прямого DELETE нет. Новая строка — только
   при изменении снимка (прогон батника, смена Inbox); история ограничена 100 последними снимками (adm.ReleasePcPrune, ★ ревизия 74 М-4).
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (у sqlcmd по умолчанию QUOTED_IDENTIFIER OFF, урок adminc_14). Совместимость
   с уровнем 100: без ISJSON, TRY_CONVERT, IIF, FORMAT, THROW. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.ReleasePcStatus') IS NULL
CREATE TABLE adm.ReleasePcStatus (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_ReleasePcStatus PRIMARY KEY,
    payload         NVARCHAR(MAX)  NOT NULL,
    payload_md5     CHAR(32)       NOT NULL,
    host            NVARCHAR(64)   NOT NULL,
    pushed_by       NVARCHAR(32)   NOT NULL,
    collected_utc   DATETIME2(0)   NOT NULL,
    pushed_utc      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ReleasePcStatus_pushed DEFAULT SYSUTCDATETIME(),
    seen_utc        DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ReleasePcStatus_seen DEFAULT SYSUTCDATETIME(),
    seen_count      INT            NOT NULL CONSTRAINT DF_adm_ReleasePcStatus_count DEFAULT 1,
    CONSTRAINT CK_adm_ReleasePcStatus_size CHECK (LEN(payload) BETWEEN 2 AND 400000),
    CONSTRAINT CK_adm_ReleasePcStatus_md5 CHECK (payload_md5 NOT LIKE '%[^0-9a-f]%' AND LEN(payload_md5) = 32),
    CONSTRAINT CK_adm_ReleasePcStatus_count CHECK (seen_count >= 1)
);
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT, INSERT                 ON adm.ReleasePcStatus TO [asda_admin];
    GRANT UPDATE (seen_utc, seen_count)  ON adm.ReleasePcStatus TO [asda_admin];
    DENY  DELETE                         ON adm.ReleasePcStatus TO [asda_admin];
END
GO
/* ★ ревизия 74 М-4: предел истории — служба раз в сутки (операция release.prune) оставляет @Keep последних снимков. Процедура не даёт
   опустить предел ниже 100 (asda_admin не может стереть историю целиком); прямого DELETE у asda_admin нет — удаление только здесь
   (цепочка владения dbo). */
CREATE OR ALTER PROCEDURE adm.ReleasePcPrune
    @Keep INT,
    @Deleted INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    IF @Keep IS NULL OR @Keep < 100 SET @Keep = 100;
    DELETE FROM adm.ReleasePcStatus
    WHERE id NOT IN (SELECT TOP (@Keep) id FROM adm.ReleasePcStatus ORDER BY id DESC);
    SET @Deleted = @@ROWCOUNT;
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
    GRANT EXECUTE ON adm.ReleasePcPrune TO [asda_admin];
GO
PRINT 'adminc_26_releases: OK';
