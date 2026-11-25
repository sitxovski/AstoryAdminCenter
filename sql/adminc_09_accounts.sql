-- Copyright (c) 2026 @sitxovski (Discord)
-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_09_accounts.sql — служебная учётка (номер Userindex ≤ 5000) для админ-центра (волна А1 «Учётки», 19.11.2026).
-- Разбор: Reports/admin_center/research_accounts_rest.md; решение владельца 19.11 п.5 — «создание СЛУЖЕБНОЙ учётки».
--
-- ПОЧЕМУ ПРОЦЕДУРА. AsdaStoryOp.dbo.Us_member.Userindex — IDENTITY(1, 1) (живая база 19.11: IDENT_CURRENT 75246, служебные
--   заняты только 1 и 2). Обычное создание (domains/accountnew.py → представление dbo.adm_NewAccount) берёт следующий номер
--   счётчика, то есть > 75000. Явный номер требует SET IDENTITY_INSERT, а он проверяет право ALTER на таблицу у ВЫЗЫВАЮЩЕГО —
--   цепочка владения его не покрывает. Давать asda_ops ALTER на Us_member нельзя (это и смена схемы), поэтому — своя процедура
--   adm.ServiceAccountCreate, ПОДПИСАННАЯ сертификатом (как UPEacAuth* EacServer, AstoryServer/EacServer/sql/eac_auth_r3.sql):
--   пользователь сертификата adm_SvcAccSign_u имеет ТОЛЬКО ALTER на dbo.Us_member (ревизия 28 К-2: SELECT/INSERT идут по цепочке
--   владения dbo → dbo и не проверяются; ALTER не сужается — IDENTITY_INSERT требует ALTER на таблицу или владение); закрытый ключ после подписи
--   удаляется (подписать им что-то ещё нельзя), пароль ключа — одноразовый случайный, нигде не хранится; при каждой выкладке
--   процедура пересоздаётся и подписывается заново. EXECUTE AS OWNER не годится: владелец базы AsdaStoryOp на dev — «сирота»
--   (живой самотест 19.11: ошибка 15517 «участник dbo не существует»). INSERT идёт по цепочке владения dbo → dbo.
-- ЧТО ПИШЕТ — ровно строку обычного создания (те же столбцы и значения, что UP_AC_CreateAccount / adm_NewAccount: Us_block 0,
--   Us_rdate сейчас, igsNID 0, Seridx/Gsidx/Threadidx/Channel 0, Poridx 3, UserNum −1, Flag 0, соль и хеш пароля, us_pwset сейчас;
--   Realcash/BonusCash/us_pwfail — умолчания таблицы) + явный номер. Других таблиц обычное создание не трогает (персонажей
--   учётка заводит сама в игре; [user] сайта gp7 заводит сам при первом обращении).
-- Номер меньше текущего счётчика — счётчик IDENTITY не сдвигается (SQL Server сдвигает его только на большее значение).
-- Проверки (под UPDLOCK, HOLDLOCK, в транзакции): номер 1…5000, номер свободен, логин свободен (без учёта регистра — коллация
--   Us_id, как при входе), логин — [A-Za-z0-9_.@-] до 32 знаков, соль 16 б и хеш 32 б заданы. Отказ — THROW (с XACT_ABORT
--   откатывает и транзакцию панели). Выбор номера («наименьший свободный после занятых служебных») и права владельца — панель.
-- Права: asda_ops — EXECUTE только этой процедуры в AsdaStoryOp (sql/adminc_04_ops.sql; EXECUTE на схему dbo запрещён).
-- Откат: DROP PROCEDURE adm.ServiceAccountCreate (схему adm в AsdaStoryOp — если пуста). Созданные учётки остаются.
-- ═══════════════════════════════════════════════════════════════════════════
USE [AsdaStoryOp];
GO
-- 25.11 (публичный клон, С-5): процедура пишет столбцы пароля P52; если их в базе нет — шаг пропускается (SET NOEXEC до конца файла),
--   служебная учётка панелью недоступна, выдача EXECUTE в adminc_04 тоже пропускается (IF OBJECT_ID)
IF COL_LENGTH('dbo.Us_member', 'us_pwsalt') IS NULL OR COL_LENGTH('dbo.Us_member', 'us_pwhash') IS NULL OR COL_LENGTH('dbo.Us_member', 'us_pwset') IS NULL
BEGIN
    PRINT 'adminc_09_accounts: пропущено - в dbo.Us_member нет столбцов пароля P52 (us_pwsalt, us_pwhash, us_pwset)';
    SET NOEXEC ON;
END
GO
IF SCHEMA_ID('adm') IS NULL EXEC('CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID('adm.ServiceAccountCreate', 'P') IS NOT NULL DROP PROCEDURE adm.ServiceAccountCreate;
GO
CREATE PROCEDURE adm.ServiceAccountCreate
	@Userindex INT,
	@Us_id     VARCHAR(61),          -- ревизия 28 К-1: как столбец; длиннее 32 — отказ ниже, а не молчаливое обрезание
	@Salt      BINARY(16),
	@Hash      BINARY(32)
AS
BEGIN
	SET NOCOUNT ON;
	SET XACT_ABORT ON;
	IF @Userindex IS NULL OR @Userindex < 1 OR @Userindex > 5000
		THROW 51091, 'adm.ServiceAccountCreate: service account number must be 1..5000', 1;
	IF @Us_id IS NULL OR LEN(@Us_id) = 0 OR DATALENGTH(@Us_id) > 32
	   OR @Us_id COLLATE Latin1_General_BIN LIKE '%[^A-Za-z0-9_.@-]%'
		THROW 51092, 'adm.ServiceAccountCreate: login must be 1..32 of [A-Za-z0-9_.@-]', 1;
	IF @Salt IS NULL OR @Hash IS NULL OR DATALENGTH(@Salt) <> 16 OR DATALENGTH(@Hash) <> 32
		THROW 51093, 'adm.ServiceAccountCreate: password salt/hash missing', 1;
	BEGIN TRAN;
	IF EXISTS (SELECT 1 FROM dbo.Us_member WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @Userindex)
		THROW 51094, 'adm.ServiceAccountCreate: account number is taken', 1;
	IF EXISTS (SELECT 1 FROM dbo.Us_member WITH (UPDLOCK, HOLDLOCK) WHERE Us_id = @Us_id)
		THROW 51095, 'adm.ServiceAccountCreate: login is taken', 1;
	SET IDENTITY_INSERT dbo.Us_member ON;
	INSERT INTO dbo.Us_member (Userindex, Us_id, Us_block, Us_rdate, igsNID, Seridx, Gsidx, Threadidx, Channel, Poridx, UserNum, Flag,
	                           us_pwsalt, us_pwhash, us_pwset)
	VALUES (@Userindex, @Us_id, 0, GETDATE(), 0, 0, 0, 0, 0, 3, -1, 0, @Salt, @Hash, GETDATE());
	SET IDENTITY_INSERT dbo.Us_member OFF;
	COMMIT;
	SELECT @Userindex AS Userindex;
END
GO
-- подпись: сертификат с одноразовым паролем → подпись → закрытый ключ удалён; пользователь сертификата — только Us_member
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'adm_SvcAccSign_u') DROP USER adm_SvcAccSign_u;
IF CERT_ID('adm_SvcAccSign') IS NOT NULL DROP CERTIFICATE adm_SvcAccSign;
GO
DECLARE @pw NVARCHAR(80) = N'Aa1!' + CONVERT(NVARCHAR(36), NEWID()) + CONVERT(NVARCHAR(36), NEWID());
DECLARE @q NVARCHAR(MAX) =
    N'CREATE CERTIFICATE adm_SvcAccSign ENCRYPTION BY PASSWORD = ''' + @pw + N''' WITH SUBJECT = ''Astory admin center: service account create'', '
  + N'EXPIRY_DATE = ''20361231''; '
  + N'ADD SIGNATURE TO adm.ServiceAccountCreate BY CERTIFICATE adm_SvcAccSign WITH PASSWORD = ''' + @pw + N'''; '
  + N'ALTER CERTIFICATE adm_SvcAccSign REMOVE PRIVATE KEY;';
EXEC sys.sp_executesql @q;
SET @pw = NULL; SET @q = NULL;
CREATE USER adm_SvcAccSign_u FROM CERTIFICATE adm_SvcAccSign;
GRANT ALTER ON dbo.Us_member TO adm_SvcAccSign_u;
GO
-- ревизия 28 К-3: самопроверка выкладки (sysadmin; asda_ops сертификаты не видит): подпись есть, закрытого ключа нет, у пользователя
-- сертификата — ровно CONNECT и ALTER на Us_member
IF NOT EXISTS (SELECT 1 FROM sys.crypt_properties cp JOIN sys.certificates c ON c.thumbprint = cp.thumbprint
               WHERE cp.major_id = OBJECT_ID('adm.ServiceAccountCreate') AND c.name = 'adm_SvcAccSign')
    THROW 51096, 'adminc_09: adm.ServiceAccountCreate is not signed', 1;
IF EXISTS (SELECT 1 FROM sys.certificates WHERE name = 'adm_SvcAccSign' AND pvt_key_encryption_type <> 'NA')
    THROW 51097, 'adminc_09: adm_SvcAccSign still has a private key', 1;
IF (SELECT COUNT(*) FROM sys.database_permissions WHERE grantee_principal_id = USER_ID('adm_SvcAccSign_u') AND state IN ('G', 'W')
      AND NOT (permission_name = 'CONNECT' AND class = 0)) <> 1
   OR NOT EXISTS (SELECT 1 FROM sys.database_permissions WHERE grantee_principal_id = USER_ID('adm_SvcAccSign_u') AND state = 'G'
      AND permission_name = 'ALTER' AND class = 1 AND major_id = OBJECT_ID('dbo.Us_member') AND minor_id = 0)
    THROW 51098, 'adminc_09: adm_SvcAccSign_u must have exactly ALTER on dbo.Us_member', 1;
GO
PRINT 'adminc_09_accounts: OK';
GO
SET NOEXEC OFF;
GO
