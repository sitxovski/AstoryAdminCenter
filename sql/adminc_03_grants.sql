-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_03_grants.sql — права логина asda_admin: AsdaAdmin точечно, игровые базы только чтение (см. шапку 01). 16.11.2026. */
SET NOCOUNT ON;
USE [AsdaAdmin];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
    CREATE USER [asda_admin] FOR LOGIN [asda_admin] WITH DEFAULT_SCHEMA = adm;
GRANT SELECT, INSERT, UPDATE, DELETE ON adm.users    TO [asda_admin];
GRANT SELECT, INSERT, UPDATE, DELETE ON adm.sessions TO [asda_admin];
GRANT SELECT, INSERT                 ON adm.audit    TO [asda_admin];
GRANT UPDATE (undone_by)             ON adm.audit    TO [asda_admin];
DENY  DELETE                         ON adm.audit    TO [asda_admin];
GRANT SELECT, INSERT, DELETE         ON adm.pw_saved TO [asda_admin];   -- 19.11: прежний пароль закрытой учётки (accountclose.py)
DENY  UPDATE                         ON adm.pw_saved TO [asda_admin];
GO

/* Игровые базы — только чтение: db_datareader + DENY на уровне базы всего, что пишет или исполняет (DENY сильнее
   любых GRANT, в т.ч. унаследованных через public — например EXECUTE на sp_*diagram в AsdaStoryOp/AsdaStoryLogin). */
USE [Joy1];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin') CREATE USER [asda_admin] FOR LOGIN [asda_admin];
ALTER ROLE db_datareader ADD MEMBER [asda_admin];
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_admin];   -- ревизия А0 №6: через public было EXECUTE на sp_creatediagram и др.
/* 21.11, А5.3 «режим обслуживания» (domains/maint.py): прочитать тело dbo.UPUserLogin, чтобы подтвердить врезку L09 ([L09-GATE]) — без этого
   «врезки нет» и «не видно» неотличимы. Только эта одна процедура, только просмотр текста (секретов в теле нет); EXECUTE запрещён выше. */
GRANT VIEW DEFINITION ON dbo.UPUserLogin TO [asda_admin];
/* 25.11.2026: второй гейт L09 (вход в мир) — без VIEW DEFINITION OBJECT_ID под asda_admin даёт NULL, и панель писала «в Joy1 нет процедуры
   adm.LoginMaintenanceGate», хотя она есть. Только просмотр; EXECUTE запрещён выше. Процедуры нет (L09 не применён) — выдачи нет. */
IF OBJECT_ID(N'adm.LoginMaintenanceGate', N'P') IS NOT NULL GRANT VIEW DEFINITION ON adm.LoginMaintenanceGate TO [asda_admin];
GO
USE [AsdaStoryOp];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin') CREATE USER [asda_admin] FOR LOGIN [asda_admin];
ALTER ROLE db_datareader ADD MEMBER [asda_admin];
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_admin];   -- ревизия А0 №6: через public было EXECUTE на sp_creatediagram и др.
GO
USE [joylog1];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin') CREATE USER [asda_admin] FOR LOGIN [asda_admin];
ALTER ROLE db_datareader ADD MEMBER [asda_admin];
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_admin];   -- ревизия А0 №6: через public было EXECUTE на sp_creatediagram и др.
GO
USE [AsdaStoryLogin];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin') CREATE USER [asda_admin] FOR LOGIN [asda_admin];
ALTER ROLE db_datareader ADD MEMBER [asda_admin];
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER, REFERENCES, CREATE TABLE, CREATE PROCEDURE, CREATE FUNCTION, CREATE VIEW TO [asda_admin];   -- ревизия А0 №6: через public было EXECUTE на sp_creatediagram и др.
GO
/* AsdaStoryLogin.dbo.[user] хранит пароли сайта открытым текстом (столбец password) — инструменту он не нужен. */
DENY SELECT ON dbo.[user] (password) TO [asda_admin];
GO
PRINT 'adminc_03_grants: OK';
