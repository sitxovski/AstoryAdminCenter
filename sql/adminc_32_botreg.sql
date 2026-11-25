-- Copyright (c) 2026 @sitxovski (Discord)
-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_32_botreg.sql — регистрация игровой учётки из бота Discord: команда /register (25.11.2026, задание владельца).
--
-- ЧТО ЭТО. Игрок пишет боту /register ЛОГИН ПАРОЛЬ — бот заводит настоящую игровую учётку (одна строка AsdaStoryOp.dbo.Us_member,
--   те же столбцы и значения, что UP_AC_CreateAccount (P52) / представление dbo.adm_NewAccount / adm.ServiceAccountCreate: Us_block 0,
--   Us_rdate сейчас, igsNID 0, Seridx/Gsidx/Threadidx/Channel 0, Poridx 3, UserNum −1, Flag 0, соль и хеш пароля, us_pwset сейчас;
--   Realcash/BonusCash/us_pwfail — умолчания таблицы). Номер учётки — обычный счётчик IDENTITY (номера после служебных), то есть НЕ служебный
--   (служебные 1…5000 = оператор у GameServer) — оператором через бота стать нельзя.
-- ХЕШ считает бот (как панель, domains/password.py): соль 16 случайных байт, хеш = SHA2_256(соль + LOWER(md5hex(пароль))) = dbo.FN_AC_PwHash.
--   Открытый пароль на сервер не передаётся и в базе не хранится.
-- ПРИВЯЗКА. adm.BotAccount: одна учётка на одного участника Discord (ключ — discord_id) — это и предел от массового создания, и связь
--   «участник → учётка» для команды. Проверки и вставка — одна транзакция под UPDLOCK, HOLDLOCK (второй такой же запрос ждёт и получает отказ).
-- КОДЫ @Code: 0 — создана (@Userindex, @Login); 1 — у этого участника учётка уже есть (@Userindex, @Login — её); 2 — логин занят
--   (без учёта регистра — коллация Us_id, как при входе); 3 — предел регистраций за сутки на всех (@DayMax в теле). Неверный формат — THROW
--   (бот проверяет формат сам; сюда такое дойти не должно).
-- ПРАВА. Бот — тот же логин asda_reports (adminc_23): в AsdaStoryOp у него ТОЛЬКО EXECUTE этой процедуры; на таблицы — DENY, на схему dbo —
--   DENY (INSERT в Us_member идёт по цепочке владения adm(dbo) → dbo и правами бота не проверяется). Логинам панели (asda_admin, asda_ops)
--   здесь ничего не выдаётся и не запрещается — их права не меняются. Проверка под asda_reports — adminc_32_botreg_verify.sql. Откат: DROP PROCEDURE adm.BotAccountRegister и DROP TABLE adm.BotAccount (созданные учётки остаются).
-- Запуск: sqlcmd -S lpc:.\SQLEXPRESS -E -b -x -I -i adminc_32_botreg.sql (после adminc_09 и adminc_23). Повторный запуск безопасен.
-- ═══════════════════════════════════════════════════════════════════════════
USE [AsdaStoryOp];
GO
IF SCHEMA_ID('adm') IS NULL EXEC('CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID('adm.BotAccount', 'U') IS NULL
    CREATE TABLE adm.BotAccount (
        discord_id   BIGINT        NOT NULL CONSTRAINT PK_adm_BotAccount PRIMARY KEY,      -- участник Discord (snowflake)
        discord_name NVARCHAR(64)  NOT NULL,                                               -- его имя на момент регистрации (для людей)
        Userindex    INT           NOT NULL CONSTRAINT UQ_adm_BotAccount_uid UNIQUE,       -- номер учётки Us_member
        Us_id        VARCHAR(32)   NOT NULL,                                               -- логин, как записан
        created_utc  DATETIME2(0)  NOT NULL CONSTRAINT DF_adm_BotAccount_created DEFAULT SYSUTCDATETIME()
    );
GO
IF OBJECT_ID('adm.BotAccountRegister', 'P') IS NOT NULL DROP PROCEDURE adm.BotAccountRegister;
GO
CREATE PROCEDURE adm.BotAccountRegister
	@DiscordId   BIGINT,
	@DiscordName NVARCHAR(64),
	@Us_id       VARCHAR(61),          -- как столбец; длиннее 32 — отказ ниже, а не молчаливое обрезание
	@Salt        BINARY(16),
	@Hash        BINARY(32),
	@Code        INT         OUTPUT,
	@Userindex   INT         OUTPUT,
	@Login       VARCHAR(32) OUTPUT
AS
BEGIN
	SET NOCOUNT ON;
	SET XACT_ABORT ON;
	DECLARE @DayMax INT = 200;         -- регистраций за 24 часа на всех участников вместе
	SELECT @Code = NULL, @Userindex = NULL, @Login = NULL;
	IF @DiscordId IS NULL OR @DiscordId <= 0
		THROW 51321, 'adm.BotAccountRegister: discord id missing', 1;
	IF @Us_id IS NULL OR LEN(@Us_id) < 3 OR DATALENGTH(@Us_id) > 32
	   OR @Us_id COLLATE Latin1_General_BIN LIKE '%[^A-Za-z0-9_.@-]%'
		THROW 51322, 'adm.BotAccountRegister: login must be 3..32 of [A-Za-z0-9_.@-]', 1;
	IF @Salt IS NULL OR @Hash IS NULL OR DATALENGTH(@Salt) <> 16 OR DATALENGTH(@Hash) <> 32
		THROW 51323, 'adm.BotAccountRegister: password salt/hash missing', 1;
	BEGIN TRAN;
	SELECT @Userindex = Userindex, @Login = Us_id FROM adm.BotAccount WITH (UPDLOCK, HOLDLOCK) WHERE discord_id = @DiscordId;
	IF @Userindex IS NOT NULL
	BEGIN
		SET @Code = 1; COMMIT; RETURN;
	END
	IF EXISTS (SELECT 1 FROM dbo.Us_member WITH (UPDLOCK, HOLDLOCK) WHERE Us_id = @Us_id)
	BEGIN
		SET @Code = 2; COMMIT; RETURN;
	END
	IF (SELECT COUNT(*) FROM adm.BotAccount WHERE created_utc > DATEADD(HOUR, -24, SYSUTCDATETIME())) >= @DayMax
	BEGIN
		SET @Code = 3; COMMIT; RETURN;
	END
	INSERT INTO dbo.Us_member (Us_id, Us_block, Us_rdate, igsNID, Seridx, Gsidx, Threadidx, Channel, Poridx, UserNum, Flag,
	                           us_pwsalt, us_pwhash, us_pwset)
	VALUES (@Us_id, 0, GETDATE(), 0, 0, 0, 0, 0, 3, -1, 0, @Salt, @Hash, GETDATE());
	SET @Userindex = CONVERT(INT, SCOPE_IDENTITY());
	SET @Login = @Us_id;
	INSERT INTO adm.BotAccount (discord_id, discord_name, Userindex, Us_id)
	VALUES (@DiscordId, ISNULL(NULLIF(@DiscordName, N''), N'?'), @Userindex, @Us_id);
	COMMIT;
	SET @Code = 0;
END
GO
-- права: бот — только эта процедура
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'asda_reports')
    THROW 51324, 'adminc_32: login asda_reports is missing — run adminc_23_reports.sql first', 1;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_reports')
    CREATE USER [asda_reports] FOR LOGIN [asda_reports] WITH DEFAULT_SCHEMA = adm;
GO
GRANT EXECUTE ON adm.BotAccountRegister TO [asda_reports];
DENY  SELECT, INSERT, UPDATE, DELETE ON adm.BotAccount TO [asda_reports];
DENY  SELECT, INSERT, UPDATE, DELETE, EXECUTE ON SCHEMA::dbo TO [asda_reports];
IF OBJECT_ID('adm.ServiceAccountCreate', 'P') IS NOT NULL DENY EXECUTE ON adm.ServiceAccountCreate TO [asda_reports];
GO
PRINT 'adminc_32_botreg: OK';
