-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_01_database.sql — админ-центр, волна А0: база AsdaAdmin и логин asda_admin. 16.11.2026.

   Запуск — только deploy/deploy_admin_center.py на сервере (sqlcmd -S lpc:.\SQLEXPRESS -E под Windows-входом Administrator — sysadmin; пароль нового логина приходит
   переменной окружения AdminPw; в файлах и командной строке его нет). Повторный запуск безопасен (всё через IF NOT EXISTS;
   пароль логина выставляется заново тем же значением из файла секретов).

   ПРАВА asda_admin (волна А0 — игровые базы ТОЛЬКО ЧТЕНИЕ):
     Joy1, AsdaStoryOp, joylog1, AsdaStoryLogin — db_datareader (и ничего больше);
     AsdaAdmin — точечно: пользователи и сессии — чтение/запись, журнал adm.audit — только SELECT/INSERT и UPDATE одного
                 столбца undone_by (журнал дописывается, но не правится и не стирается самим инструментом).
   Порядок: 01_database → 02_schema (с -d AsdaAdmin) → 03_grants. Откат — adminc_99_rollback.sql. Проверка — adminc_10_verify.sql.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_ID(N'AsdaAdmin') IS NULL
    CREATE DATABASE [AsdaAdmin] COLLATE Cyrillic_General_CI_AS;
GO
ALTER DATABASE [AsdaAdmin] SET RECOVERY SIMPLE;
GO

USE [master];
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'asda_admin')
    CREATE LOGIN [asda_admin] WITH PASSWORD = N'$(AdminPw)', DEFAULT_DATABASE = [AsdaAdmin], CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    ALTER LOGIN [asda_admin] WITH PASSWORD = N'$(AdminPw)', CHECK_POLICY = ON;
ALTER LOGIN [asda_admin] ENABLE;
GO

PRINT 'adminc_01_database: OK';
