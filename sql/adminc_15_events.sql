-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_15_events.sql — админ-центр, шаг А5.4 «События и сбросы»: сброс ежедневных заданий доски ДЛЯ ВСЕХ из панели. 21.11.2026.

   ЗАЧЕМ. План §4.Д «сброс ежедневных заданий». Ежедневные = задания доски объявлений (LimitationQuest, Quest_Type = 1) в
   Joy1.dbo.CRT_LimitationQuest. Реверс: GameServer обнуляет их ТОЛЬКО в памяти игроков в игре (TimeSyncProcess@0x539A00, смена дня
   при часе ≥ 6, RunProcess GameServer.c:77443) и шлёт DB 2659, которого DBManager не обрабатывает; в БД сброс делает наш
   dbo.CRT_AsdaLimitationDailyReset (волна board_quest 28.10: задача ОС ASDA_LimitationDailyReset 06:02 + страховка в
   CRT_UPLimitationList; журнал dbo.AsdaLimitationResetLog; разбор Reports/board_quest/SERVER.md §3). Свой сброс панель НЕ
   выдумывает: режим 0 — ровно вызов этой процедуры (догнать пропущенный за границу 06:00; идемпотентно), режим 1 — то же тело
   (Quest_Type = 1: Quest_Flag 3 → 0, Quest_Count → 0; Flag 1/2 и типы 0/2/3 не трогаются) под тем же замком sp_getapplock, но вне
   метки «сброс за границу сделан» (Done = 2 — внеочередной; суточная логика смотрит только Done = 1 и не меняется).
   Одному персонажу — уже есть операция craft.daily_reset (domains/charrest.py, А1) — здесь не дублируется.
   Игроки в игре увидят внеочередной сброс после смены карты (GS берёт состояние из БД — CRT_UPLimitationList → 6588) или
   перезахода — в памяти GS у них прежнее состояние до 06:00 (так у сервера, панель предупреждает).

   EXECUTE на схему dbo у asda_ops запрещён (adminc_04_ops.sql) — поэтому обёртка в схеме adm (цепочка владения dbo, как
   adm.CampPointRank). Права — adminc_04_ops.sql (GRANT EXECUTE ON adm.LimitationReset), проверка — adminc_11_verify_ops.sql.
   Запуск — deploy/deploy_admin_center.py (sqlcmd -S lpc:.\SQLEXPRESS -E), ДО adminc_04_ops.sql.
   Откат: DROP PROCEDURE Joy1.adm.LimitationReset (adminc_99_rollback.sql); строки журнала Source admin* безвредны.
*/
SET NOCOUNT ON;
GO
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
USE [Joy1];
GO
IF SCHEMA_ID('adm') IS NULL EXEC('CREATE SCHEMA adm AUTHORIZATION dbo');
GO
/* @Mode: 0 — догнать суточный сброс (dbo.CRT_AsdaLimitationDailyReset @Source = 'admin': 1 сделан, 0 уже был за границу, -1 замок);
          1 — внеочередной сброс всех.
   Итог — одна строка: rc (1 сделано, 0 уже был, -1 замок не взят за 5 с, -3 неверный режим), flag_rows, count_rows, boundary. */
CREATE OR ALTER PROCEDURE adm.LimitationReset @Mode TINYINT
AS
SET NOCOUNT ON;
SET LOCK_TIMEOUT 5000;
DECLARE @r INT, @f INT = 0, @c INT = 0, @lock INT, @b DATETIME, @d DATETIME = DATEADD(MINUTE, -1, GETDATE());
SET @b = DATEADD(HOUR, 6, CAST(CAST(@d AS DATE) AS DATETIME));              -- граница суток — как в CRT_AsdaLimitationDailyReset
IF @d < @b SET @b = DATEADD(DAY, -1, @b);
IF @Mode IS NULL OR @Mode NOT IN (0, 1)
BEGIN
    SELECT -3 AS rc, 0 AS flag_rows, 0 AS count_rows, @b AS boundary;
    RETURN 0;
END
IF @Mode = 0
BEGIN
    EXEC @r = dbo.CRT_AsdaLimitationDailyReset @Source = 'admin';
    SELECT @r AS rc,
           ISNULL((SELECT TOP 1 FlagRows FROM dbo.AsdaLimitationResetLog WHERE Boundary = @b AND Source = 'admin' ORDER BY Id DESC), 0) AS flag_rows,
           ISNULL((SELECT TOP 1 CountRows FROM dbo.AsdaLimitationResetLog WHERE Boundary = @b AND Source = 'admin' ORDER BY Id DESC), 0) AS count_rows,
           @b AS boundary;
    RETURN 0;
END
BEGIN TRY
    BEGIN TRANSACTION;
    EXEC @lock = sp_getapplock @Resource = 'AsdaLimitationDailyReset', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 5000;
    IF @lock < 0
    BEGIN
        ROLLBACK;
        SELECT -1 AS rc, 0 AS flag_rows, 0 AS count_rows, @b AS boundary;
        RETURN 0;
    END
    UPDATE dbo.CRT_LimitationQuest SET Quest_Flag = 0 WHERE Quest_Type = 1 AND Quest_Flag = 3;
    SET @f = @@ROWCOUNT;
    UPDATE dbo.CRT_LimitationQuest SET Quest_Count = 0 WHERE Quest_Type = 1 AND Quest_Count <> 0;
    SET @c = @@ROWCOUNT;
    INSERT dbo.AsdaLimitationResetLog (Boundary, Source, Done, FlagRows, CountRows) VALUES (@b, 'admin-force', 2, @f, @c);
    COMMIT;
    SELECT 1 AS rc, @f AS flag_rows, @c AS count_rows, @b AS boundary;
    RETURN 0;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK;
    THROW;
END CATCH
GO
PRINT 'adminc_15_events: OK';
GO
