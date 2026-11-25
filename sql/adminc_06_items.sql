-- Copyright (c) 2026 @sitxovski (Discord)
-- ═══════════════════════════════════════════════════════════════════════════
-- adminc_06_items.sql — выдача и изъятие предметов персонажа НЕ В ИГРЕ для админ-центра (волна А1, 18.11.2026).
-- Разбор: Reports/admin_center/research_item_give.md. Решения владельца 18.11: своя процедура adm (как adm.CharRestore);
-- сумки 1, 2 И склад (Plate 5); опции выбирает оператор (или «Случайно» — как сервер), основной камень — из таблицы предмета;
-- откат изъятия — в ту же ячейку, занята — в первую свободную той же сумки; журнал — свой (adm.ItemLedger) И стоковый
-- JoyLog1.dbo.AdminitemLog.
--
-- ПОЧЕМУ НЕ СТОКОВЫЕ UPRewardItem / UPGmItemAdd: у первой нет транзакции, она двигает CharEpisode и пишет EpisodeEventitem,
--   её ветка стопки обновляет ячейку без сверки Code; вторая вставляет в сумку 1 вслепую. EXECUTE на dbo у asda_ops запрещён.
-- Uuid новой строки — NEWID() (так делают все процедуры сервера; GameServer Uuid не знает — research §1.3). Строку ищем
--   всегда по ключу ячейки + Code + Uuid: Uuid в живой базе не уникален (исторический дюп у 2/11).
-- Что проверяет процедура (атомарно, под UPDLOCK, HOLDLOCK): персонаж есть; сумка 1/2/5 и ячейка в пределах ёмкости
--   (сумка 1 — 60 только при метке «инвентарь ×2», склад — min(WareCount, 270)); код не золото; «новая» — ячейка пуста;
--   «стопка» — в ячейке тот же код с ожидаемым количеством и это ПЕРВАЯ ячейка этого кода в сумке (как sub_4D6CE0 сервера),
--   вес строки ≤ 32 767; «заряды» (P100) — ячейка того же ключа AsdaChargeGroup, итог ≤ потолка, вес не растёт.
--   Правило кода (сумка, стопка, вес, прочность, опции, камень), вес персонажа и «учётка не в игре» — панель, в той же
--   транзакции до вызова (domains/itemgive.py). Отказ — THROW (с XACT_ABORT откатывает и транзакцию панели).
-- Изъятие в dbo.Del_Item НЕ пишется: это корзина удалённого персонажа — восстановление сочло бы строку частью набора.
-- Права: asda_ops — EXECUTE только adm.ItemGive / ItemTake / ItemUndo / ItemRecover (19.11), SELECT adm.ItemLedger (sql/adminc_04_ops.sql);
--   цепочка владения dbo внутри Joy1; JoyLog1 — у asda_ops свой пользователь с INSERT одной таблицы AdminitemLog
--   (межбазовые цепочки выключены у всех баз — research §2).
-- Откат выкладки: adminc_99_rollback.sql (процедуры и таблицы adm.Item*).
-- ═══════════════════════════════════════════════════════════════════════════
USE [Joy1];
GO
IF SCHEMA_ID('adm') IS NULL EXEC('CREATE SCHEMA adm AUTHORIZATION dbo');
GO
IF OBJECT_ID('adm.ItemLedger', 'U') IS NULL
CREATE TABLE adm.ItemLedger (
	Id            INT IDENTITY(1, 1) NOT NULL CONSTRAINT PK_ItemLedger PRIMARY KEY,
	Kind          VARCHAR(12)      NOT NULL,      -- give | stack | charge | take | takepart | undo
	Userindex     INT              NOT NULL,
	Charidx       TINYINT          NOT NULL,
	Plate         TINYINT          NOT NULL,
	Posx          SMALLINT         NOT NULL,
	Code          INT              NOT NULL,
	Uuid          UNIQUEIDENTIFIER NOT NULL,
	AmountBefore  INT              NULL,          -- NULL — строки не было (новая) / не стало (изъята целиком)
	AmountAfter   INT              NULL,
	WeightBefore  SMALLINT         NULL,
	WeightAfter   SMALLINT         NULL,
	FdateAfter    DATETIME         NULL,          -- Fdate строки после записи: детектор «с тех пор менялась» для отката
	FdateBefore   DATETIME         NULL,          -- Fdate строки до записи: откат стопки/зарядов/части возвращает его (живой самотест 18.11)
	UndoOf        INT              NULL,          -- для Kind = undo: какую запись откатили
	UndoneBy      INT              NULL,          -- запись undo, откатившая эту
	Operator      VARCHAR(64)      NULL,
	At            DATETIME         NOT NULL CONSTRAINT DF_ItemLedger_At DEFAULT (GETDATE())
);
GO
-- снимок изъятой строки — те же 36 столбцов, что у dbo.Item (типы берутся у самой таблицы), + номер записи журнала
-- живой самотест 18.11: откат прибавки к стопке ставил строке НОВОЕ время, и более ранняя запись той же строки больше не
-- откатывалась («предмет с тех пор менялся») — теперь журнал хранит и прежнее время, откат возвращает его
IF COL_LENGTH('adm.ItemLedger', 'FdateBefore') IS NULL ALTER TABLE adm.ItemLedger ADD FdateBefore DATETIME NULL;
GO
-- перепроверка 18 М4: Uuid в базе не уникален (исторический дубль) — откат изъятия сверяет число строк с этим Uuid «как было»,
-- а не «нет нигде» (иначе изъятая копия дубля не вернулась бы никогда)
IF COL_LENGTH('adm.ItemLedger', 'UuidItems') IS NULL ALTER TABLE adm.ItemLedger ADD UuidItems INT NULL, UuidDel INT NULL;
GO
-- 19.11 «вернуть удалённое по журналам» (adm.ItemRecover): списанное золото продажи (откат возвращает) и строка-источник журнала
IF COL_LENGTH('adm.ItemLedger', 'GoldTaken') IS NULL ALTER TABLE adm.ItemLedger ADD GoldTaken INT NULL, Source VARCHAR(80) NULL;
GO
IF OBJECT_ID('adm.ItemTaken', 'U') IS NULL
BEGIN
	SELECT TOP 0 * INTO adm.ItemTaken FROM dbo.Item;
	ALTER TABLE adm.ItemTaken ADD LedgerId INT NOT NULL CONSTRAINT DF_ItemTaken_L DEFAULT (0);
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ItemTaken_Ledger' AND object_id = OBJECT_ID('adm.ItemTaken'))
	CREATE UNIQUE INDEX IX_ItemTaken_Ledger ON adm.ItemTaken (LedgerId);
GO

-- ─────────────────────────── ёмкость сумки (общая проверка) ───────────────────────────
IF OBJECT_ID('adm.ItemPlateCap', 'FN') IS NOT NULL DROP FUNCTION adm.ItemPlateCap;
GO
CREATE FUNCTION adm.ItemPlateCap (@Plate TINYINT, @Ware INT) RETURNS INT
AS
BEGIN
	-- сумка 1: 60 ячеек только после волны «инвентарь ×2» (метка AsdaMigrationLog; старый DBManager срезал бы 30…59);
	-- панель дополнительно сужает до 30, если на стойке выключен P96 (передаёт @Cap)
	RETURN CASE @Plate
		WHEN 1 THEN CASE WHEN EXISTS (SELECT 1 FROM dbo.AsdaMigrationLog WHERE MigKey = 'inventory_x2_weight') THEN 60 ELSE 30 END
		WHEN 2 THEN 60
		WHEN 5 THEN CASE WHEN ISNULL(@Ware, 0) < 270 THEN ISNULL(@Ware, 0) ELSE 270 END
		ELSE 0 END;
END
GO

-- ─────────────────────────── выдать ───────────────────────────
IF OBJECT_ID('adm.ItemGive', 'P') IS NOT NULL DROP PROCEDURE adm.ItemGive;
GO
CREATE PROCEDURE adm.ItemGive @Userindex INT, @Charidx TINYINT, @Plate TINYINT, @Posx SMALLINT, @Cap SMALLINT,
	@Mode VARCHAR(8),                 -- new | stack | charge
	@Code INT, @Amount INT, @Durability TINYINT, @Weight SMALLINT,
	@Cell1 SMALLINT = 0, @Upcount TINYINT = 0, @MaxupCnt TINYINT = 0,
	@Opidx1 SMALLINT = -1, @OpValue1 SMALLINT = 0, @Opidx2 SMALLINT = -1, @OpValue2 SMALLINT = 0, @Owner TINYINT = 0,
	@ExpectAmount INT = NULL,         -- stack/charge: количество в ячейке на предпросмотре
	@ChargeCap INT = 30000,           -- charge: потолок зарядов P100 (patches.ini Cap; не выше 30 000 — сверки крафта SMALLINT)
	@Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @name VARCHAR(20), @ware INT, @u UNIQUEIDENTIFIER, @c0 INT, @a0 INT, @w0 INT, @a1 INT, @w1 INT, @fd DATETIME,
		@id INT, @k0 INT, @k1 INT, @f0 DATETIME;
	SET @fd = GETDATE();
	BEGIN TRANSACTION;
	SELECT @name = Charname, @ware = WareCount FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK)
	 WHERE Userindex = @Userindex AND Charidx = @Charidx;
	IF @name IS NULL THROW 51101, 'adm.ItemGive: персонажа нет', 1;
	IF @Plate NOT IN (1, 2, 5) THROW 51102, 'adm.ItemGive: выдавать можно только в сумки 1, 2 и склад', 1;
	IF @Cap IS NULL OR @Cap < 1 OR @Cap > adm.ItemPlateCap(@Plate, @ware) THROW 51103, 'adm.ItemGive: неверная ёмкость сумки', 1;
	IF @Posx IS NULL OR @Posx < 0 OR @Posx >= @Cap THROW 51104, 'adm.ItemGive: ячейка вне сумки', 1;
	IF @Code IS NULL OR @Code < 1 OR @Code = 20551 THROW 51105, 'adm.ItemGive: недопустимый код (золото — своей операцией)', 1;
	IF @Amount IS NULL OR @Amount < 0 OR @Weight IS NULL OR @Weight < 0 THROW 51106, 'adm.ItemGive: неверное количество или вес', 1;
	IF @Mode = 'new'
	BEGIN
		IF EXISTS (SELECT 1 FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
		            WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx)
			THROW 51107, 'adm.ItemGive: ячейка занята', 1;
		SET @u = NEWID();
		-- столбцы — как ветка «новая строка» UPRewardItem: Uc1 = NEWID() при самоцвете, пары 3–5 −1/0, Refine 0, Rdate NULL
		INSERT INTO dbo.Item (Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2,
			Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3,
			Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate)
		VALUES (@Userindex, @Charidx, @u, @Code, @Plate, @Posx, @Amount, ISNULL(@Durability, 0), @Weight,
			CASE WHEN @Cell1 > 0 THEN CONVERT(VARCHAR(36), NEWID()) END, ISNULL(@Cell1, 0), NULL, 0, NULL, 0, NULL, 0,
			ISNULL(@Upcount, 0), 0, ISNULL(@MaxupCnt, 0), 0, ISNULL(@Opidx1, -1), ISNULL(@OpValue1, 0), ISNULL(@Opidx2, -1),
			ISNULL(@OpValue2, 0), -1, 0, -1, 0, -1, 0, 0, ISNULL(@Owner, 0), @fd, @fd, NULL);
		SELECT @a1 = @Amount, @w1 = @Weight;
	END
	ELSE IF @Mode IN ('stack', 'charge')
	BEGIN
		SELECT @u = Uuid, @c0 = Code, @a0 = Amount, @w0 = Weight, @f0 = Fdate FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
		 WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx;
		IF @u IS NULL OR @a0 <> @ExpectAmount OR @ExpectAmount IS NULL
			THROW 51108, 'adm.ItemGive: ячейка изменилась после предпросмотра', 1;
		IF @Mode = 'stack'
		BEGIN
			IF @c0 <> @Code THROW 51109, 'adm.ItemGive: в ячейке другой предмет', 1;
			-- сервер кладёт в ПЕРВУЮ ячейку того же кода (sub_4D6CE0)
			IF EXISTS (SELECT 1 FROM dbo.Item WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @Userindex AND Charidx = @Charidx
			            AND Plate = @Plate AND Code = @Code AND Posx < @Posx)
				THROW 51110, 'adm.ItemGive: есть более ранняя стопка того же предмета', 1;
			IF CAST(@a0 AS BIGINT) + @Amount > 2147483647 OR @w0 + CAST(@Weight AS INT) > 32767
				THROW 51111, 'adm.ItemGive: стопка переполнится', 1;
			SELECT @a1 = @a0 + @Amount, @w1 = @w0 + @Weight;
		END
		ELSE
		BEGIN
			-- P100: ключ слияния — группа + привязка (зеркало charge_groups.txt); код ячейки не меняется, вес не растёт
			SELECT @k0 = GroupKey FROM dbo.AsdaChargeGroup WHERE Code = @c0;
			SELECT @k1 = GroupKey FROM dbo.AsdaChargeGroup WHERE Code = @Code;
			IF @k0 IS NULL OR @k1 IS NULL OR @k0 <> @k1 OR @k0 = 0 THROW 51112, 'adm.ItemGive: в ячейке не тот вид зарядов', 1;
			-- перепроверка 18 М1: на складе P100 сливает только одинаковый код (P100_PROJECT §7 п.2)
			IF @Plate = 5 AND @c0 <> @Code THROW 51112, 'adm.ItemGive: в ячейке не тот вид зарядов', 1;
			IF @ChargeCap IS NULL OR @ChargeCap < 1 OR @ChargeCap > 30000 OR CAST(@a0 AS BIGINT) + @Amount > @ChargeCap
				THROW 51113, 'adm.ItemGive: заряды выше потолка', 1;
			SELECT @a1 = @a0 + @Amount, @w1 = @w0;
		END
		UPDATE dbo.Item SET Amount = @a1, Weight = @w1, Fdate = @fd
		 WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx AND Uuid = @u AND Amount = @a0;
		IF @@ROWCOUNT <> 1 THROW 51114, 'adm.ItemGive: ячейка изменилась при записи', 1;
	END
	ELSE THROW 51115, 'adm.ItemGive: неверный режим', 1;

	INSERT INTO adm.ItemLedger (Kind, Userindex, Charidx, Plate, Posx, Code, Uuid, AmountBefore, AmountAfter, WeightBefore,
		WeightAfter, FdateAfter, FdateBefore, Operator)
	VALUES (CASE @Mode WHEN 'new' THEN 'give' ELSE @Mode END, @Userindex, @Charidx, @Plate, @Posx, @Code, @u, @a0, @a1, @w0,
		@w1, @fd, @f0, @Operator);
	SET @id = SCOPE_IDENTITY();
	-- стоковый журнал выдач оператора (тот же, что у GM-команды UPGmItemAdd): Amount — было (0 у новой), Ramount — стало
	INSERT INTO JoyLog1.dbo.AdminitemLog (Edate, Userindex, Charidx, Fromname, Suserindex, Scharidx, Toname, Code, Serial, Amount,
		Ramount, Durability, Cell1, Cell2, Cell3, Cell4, Upcount, Opidx1, Opvalue1, Opidx2, Opvalue2, State)
	VALUES (@fd, @Userindex, @Charidx, LEFT(ISNULL(@Operator, 'admin'), 20), 0, 0, @name, @Code, CONVERT(VARCHAR(36), @u),
		ISNULL(@a0, 0), @a1, ISNULL(@Durability, 0), ISNULL(@Cell1, 0), 0, 0, 0, ISNULL(@Upcount, 0), ISNULL(@Opidx1, -1),
		ISNULL(@OpValue1, 0), ISNULL(@Opidx2, -1), ISNULL(@OpValue2, 0), 'Item Add(Admin)');
	COMMIT TRANSACTION;
	SELECT @id AS LedgerId, CONVERT(VARCHAR(36), @u) AS Uuid, @a0 AS AmountBefore, @a1 AS AmountAfter,
		CONVERT(VARCHAR(23), @fd, 121) AS Fdate;
GO

-- ─────────────────────────── изъять ───────────────────────────
IF OBJECT_ID('adm.ItemTake', 'P') IS NOT NULL DROP PROCEDURE adm.ItemTake;
GO
CREATE PROCEDURE adm.ItemTake @Userindex INT, @Charidx TINYINT, @Plate TINYINT, @Posx SMALLINT, @Code INT, @Uuid UNIQUEIDENTIFIER,
	@ExpectAmount INT, @ExpectFdate VARCHAR(23),     -- строка на предпросмотре (Fdate — CONVERT 121; NULL — пусто)
	@Take INT = NULL,                                -- NULL — вся строка; иначе — часть стопки (итог ≥ 1)
	@TakeWeight INT = 0,                             -- вес снимаемой части (стопка — n × вес единицы; заряды — 0)
	@Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @name VARCHAR(20), @n INT, @a0 INT, @w0 INT, @a1 INT, @w1 INT, @fd DATETIME, @id INT, @f0 DATETIME, @ui INT, @ud INT,
		@dur INT, @c1 INT, @c2 INT, @c3 INT, @c4 INT, @up INT, @o1 INT, @v1 INT, @o2 INT, @v2 INT;
	SET @fd = GETDATE();
	BEGIN TRANSACTION;
	SELECT @name = Charname FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @Userindex AND Charidx = @Charidx;
	IF @name IS NULL THROW 51201, 'adm.ItemTake: персонажа нет', 1;
	IF @Plate NOT IN (1, 2, 5) THROW 51202, 'adm.ItemTake: изымать можно только из сумок 1, 2 и склада', 1;
	SELECT @n = COUNT(*) FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
	 WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx AND Code = @Code AND Uuid = @Uuid
	   AND Amount = @ExpectAmount
	   AND (CONVERT(VARCHAR(23), Fdate, 121) = @ExpectFdate OR (Fdate IS NULL AND @ExpectFdate IS NULL));
	IF @n <> 1 THROW 51203, 'adm.ItemTake: предмет изменился после предпросмотра', 1;
	SELECT @a0 = Amount, @w0 = Weight, @f0 = Fdate, @dur = Durability, @c1 = Cell1, @c2 = Cell2, @c3 = Cell3, @c4 = Cell4, @up = Upcount,
		@o1 = Opidx1, @v1 = OpValue1, @o2 = Opidx2, @v2 = OpValue2
	  FROM dbo.Item WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx;
	IF @Take IS NOT NULL AND (@Take < 1 OR @Take >= @a0 OR @TakeWeight < 0 OR @TakeWeight > @w0)
		THROW 51204, 'adm.ItemTake: неверная часть стопки', 1;
	-- сколько строк с этим Uuid в живой базе и в корзине удалённых — для отката (М4); без UPDLOCK: индекса по Uuid нет (М5)
	SELECT @ui = COUNT(*) FROM dbo.Item WHERE Uuid = @Uuid;
	SELECT @ud = COUNT(*) FROM dbo.Del_Item WHERE Uuid = @Uuid;
	SELECT @a1 = CASE WHEN @Take IS NULL THEN NULL ELSE @a0 - @Take END,
	       @w1 = CASE WHEN @Take IS NULL THEN NULL ELSE @w0 - @TakeWeight END;
	INSERT INTO adm.ItemLedger (Kind, Userindex, Charidx, Plate, Posx, Code, Uuid, AmountBefore, AmountAfter, WeightBefore,
		WeightAfter, FdateAfter, FdateBefore, UuidItems, UuidDel, Operator)
	VALUES (CASE WHEN @Take IS NULL THEN 'take' ELSE 'takepart' END, @Userindex, @Charidx, @Plate, @Posx, @Code, @Uuid, @a0, @a1,
		@w0, @w1, CASE WHEN @Take IS NULL THEN NULL ELSE @fd END, @f0, @ui, @ud, @Operator);
	SET @id = SCOPE_IDENTITY();
	IF @Take IS NULL
	BEGIN
		INSERT INTO adm.ItemTaken (Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2,
			Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3,
			Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate, LedgerId)
		SELECT Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2,
			Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3,
			Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate, @id
		  FROM dbo.Item WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx AND Uuid = @Uuid;
		IF @@ROWCOUNT <> 1 THROW 51205, 'adm.ItemTake: снимок не записан', 1;
		DELETE FROM dbo.Item WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx
		   AND Uuid = @Uuid AND Amount = @a0;
		IF @@ROWCOUNT <> 1 THROW 51206, 'adm.ItemTake: предмет изменился при записи', 1;
	END
	ELSE
	BEGIN
		-- часть стопки — как UPItemDump (ветка «выбросить часть»): Amount −= n, Weight −= вес части
		UPDATE dbo.Item SET Amount = @a1, Weight = @w1, Fdate = @fd
		 WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx AND Uuid = @Uuid AND Amount = @a0;
		IF @@ROWCOUNT <> 1 THROW 51206, 'adm.ItemTake: предмет изменился при записи', 1;
	END
	INSERT INTO JoyLog1.dbo.AdminitemLog (Edate, Userindex, Charidx, Fromname, Suserindex, Scharidx, Toname, Code, Serial, Amount,
		Ramount, Durability, Cell1, Cell2, Cell3, Cell4, Upcount, Opidx1, Opvalue1, Opidx2, Opvalue2, State)
	VALUES (@fd, @Userindex, @Charidx, LEFT(ISNULL(@Operator, 'admin'), 20), 0, 0, @name, @Code, CONVERT(VARCHAR(36), @Uuid),
		@a0, ISNULL(@a1, 0), ISNULL(@dur, 0), @c1, @c2, @c3, @c4, ISNULL(@up, 0), ISNULL(@o1, -1), ISNULL(@v1, 0), ISNULL(@o2, -1),
		ISNULL(@v2, 0), 'Item Del(Admin)');
	COMMIT TRANSACTION;
	SELECT @id AS LedgerId, @a0 AS AmountBefore, @a1 AS AmountAfter, CONVERT(VARCHAR(23), @fd, 121) AS Fdate;
GO

-- ─────────────────────────── вернуть удалённое по журналам (19.11) ───────────────────────────
-- Решение владельца 19.11 (research_items_trace.md §4): выброшенное / проданное NPC / разобранное / снятое по таймауту аукциона
-- возвращается ТЕМ ЖЕ номером (Uuid). Строку собирает панель (domains/itemrecover.py) из строки журнала + правила кода
-- (itemgive.item_spec); процедура атомарно проверяет, что экземпляра нигде нет (иначе — дюп), кладёт строку в свободную ячейку,
-- при возврате проданного списывает золото продажи и пишет журналы. Откат — adm.ItemUndo (вид 'recover': убрать строку, вернуть золото).
IF OBJECT_ID('adm.ItemRecover', 'P') IS NOT NULL DROP PROCEDURE adm.ItemRecover;
GO
CREATE PROCEDURE adm.ItemRecover @Userindex INT, @Charidx TINYINT, @Plate TINYINT, @Posx SMALLINT, @Cap SMALLINT,
	@Uuid UNIQUEIDENTIFIER, @Code INT, @Amount INT, @Durability TINYINT, @Weight SMALLINT,
	@Cell1 SMALLINT = 0, @Cell2 SMALLINT = 0, @Cell3 SMALLINT = 0, @Cell4 SMALLINT = 0,
	@Upcount TINYINT = 0, @AcuUpcnt TINYINT = 0, @MaxupCnt TINYINT = 0, @Updamage SMALLINT = 0,
	@Opidx1 SMALLINT = -1, @OpValue1 SMALLINT = 0, @Opidx2 SMALLINT = -1, @OpValue2 SMALLINT = 0, @Opidx3 SMALLINT = -1, @Opvalue3 SMALLINT = 0,
	@Opidx4 SMALLINT = -1, @Opvalue4 SMALLINT = 0, @OPidx5 SMALLINT = -1, @Opvalue5 SMALLINT = 0, @Owner TINYINT = 0,
	@GainDate DATETIME = NULL,        -- дата получения (первое событие следа); NULL — сейчас
	@Source VARCHAR(80),              -- строка журнала-источника «таблица | время 121» (повтор того же источника — отказ)
	@GoldTake INT = 0,                -- возврат проданного NPC: сколько золота списать (0 — не списывать)
	@GoldExpect INT = NULL,           -- золото в сумке на предпросмотре (сверка)
	@Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @name VARCHAR(20), @ware INT, @fd DATETIME, @id INT, @us VARCHAR(36), @gu UNIQUEIDENTIFIER, @g0 INT, @gx SMALLINT;
	SET @fd = GETDATE();
	SET @us = CONVERT(VARCHAR(36), @Uuid);
	BEGIN TRANSACTION;
	SELECT @name = Charname, @ware = WareCount FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK)
	 WHERE Userindex = @Userindex AND Charidx = @Charidx;
	IF @name IS NULL THROW 51401, 'adm.ItemRecover: персонажа нет', 1;
	IF @Plate NOT IN (1, 2, 5) THROW 51402, 'adm.ItemRecover: возвращать можно только в сумки 1, 2 и склад', 1;
	IF @Cap IS NULL OR @Cap < 1 OR @Cap > adm.ItemPlateCap(@Plate, @ware) THROW 51403, 'adm.ItemRecover: неверная ёмкость сумки', 1;
	IF @Posx IS NULL OR @Posx < 0 OR @Posx >= @Cap THROW 51404, 'adm.ItemRecover: ячейка вне сумки', 1;
	IF @Uuid IS NULL OR @Code IS NULL OR @Code < 1 OR @Code = 20551 THROW 51405, 'adm.ItemRecover: недопустимый предмет', 1;
	IF @Amount IS NULL OR @Amount < 0 OR @Weight IS NULL OR @Weight < 0 OR @Source IS NULL OR @GoldTake IS NULL OR @GoldTake < 0
		THROW 51406, 'adm.ItemRecover: неверные параметры', 1;
	IF EXISTS (SELECT 1 FROM dbo.Item WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = @Plate AND Posx = @Posx)
		THROW 51407, 'adm.ItemRecover: ячейка занята', 1;
	-- ★ ревизия 27 М-2: сначала мьютекс всех возвратов (замок приложения на транзакцию), затем проверки — иначе два возврата одного
	--   номера из РАЗНЫХ источников у разных владельцев могли бы оба пройти «нигде нет» (индекса по Uuid нет, строк для блокировки нет).
	--   Тот же замок берёт adm.ItemUndo при возврате изъятого (он тоже вставляет тот же номер).
	DECLARE @lk INT;
	EXEC @lk = sp_getapplock @Resource = 'AsdaAdmin.ItemUuidInsert', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 15000;
	IF @lk < 0 THROW 51413, 'adm.ItemRecover: другой возврат идёт слишком долго — повторите', 1;
	IF EXISTS (SELECT 1 FROM adm.ItemLedger WHERE Kind = 'recover' AND Uuid = @Uuid AND Source = @Source AND UndoneBy IS NULL)
		THROW 51409, 'adm.ItemRecover: эта запись журнала уже возвращена', 1;
	-- защита от дюпа: этого экземпляра нет НИГДЕ — в сумках, на аукционе, в оправе совела (Uc), в корзинах удалённых персонажей
	-- (Del_Item и лоты Del_ExItem — ★ ревизия 27 М-5, вместе с их Uc), в снимках изъятого панелью (и их Uc), пока изъятие не откачено.
	-- Без UPDLOCK по всей таблице (индекса по Uuid нет — держал бы всю Item; как adm.ItemUndo, перепроверка 18 М5); гонку закрывает замок выше.
	IF EXISTS (SELECT 1 FROM dbo.Item WHERE Uuid = @Uuid)
	   OR EXISTS (SELECT 1 FROM dbo.Exitem WHERE Eid = @Uuid)
	   OR EXISTS (SELECT 1 FROM dbo.Item WHERE Uc1 = @us OR Uc2 = @us OR Uc3 = @us OR Uc4 = @us)
	   OR EXISTS (SELECT 1 FROM dbo.Exitem WHERE Uc1 = @us OR Uc2 = @us OR Uc3 = @us OR Uc4 = @us)
	   OR EXISTS (SELECT 1 FROM dbo.Del_Item WHERE Uuid = @Uuid OR Uc1 = @us OR Uc2 = @us OR Uc3 = @us OR Uc4 = @us)
	   OR EXISTS (SELECT 1 FROM dbo.Del_ExItem WHERE Eid = @Uuid OR Uc1 = @us OR Uc2 = @us OR Uc3 = @us OR Uc4 = @us)
	   OR EXISTS (SELECT 1 FROM adm.ItemTaken t JOIN adm.ItemLedger l ON l.Id = t.LedgerId
	               WHERE l.UndoneBy IS NULL AND (t.Uuid = @Uuid OR t.Uc1 = @us OR t.Uc2 = @us OR t.Uc3 = @us OR t.Uc4 = @us))
		THROW 51408, 'adm.ItemRecover: этот экземпляр уже есть в базе — возврат дал бы дюп', 1;
	IF @GoldTake > 0
	BEGIN
		-- золото — отдельная строка сумки 2 (Code 20551); списание — как продажа наоборот, без ухода в минус
		SELECT @gu = Uuid, @g0 = Amount, @gx = Posx FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
		 WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = 2 AND Code = 20551;
		IF @gu IS NULL OR @g0 < @GoldTake THROW 51410, 'adm.ItemRecover: у персонажа нет золота продажи', 1;
		IF @GoldExpect IS NULL OR @g0 <> @GoldExpect THROW 51411, 'adm.ItemRecover: золото изменилось после предпросмотра', 1;
		UPDATE dbo.Item SET Amount = Amount - @GoldTake          -- время строки золота не трогаем: откат вернёт строку ровно как была
		 WHERE Userindex = @Userindex AND Charidx = @Charidx AND Plate = 2 AND Posx = @gx AND Uuid = @gu AND Amount = @g0;
		IF @@ROWCOUNT <> 1 THROW 51412, 'adm.ItemRecover: золото изменилось при записи', 1;
	END
	INSERT INTO dbo.Item (Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2,
		Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3,
		Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate)
	VALUES (@Userindex, @Charidx, @Uuid, @Code, @Plate, @Posx, @Amount, ISNULL(@Durability, 0), @Weight,
		-- номера вставленных совелов в журналах нет — новые (как UPRewardItem при самоцвете)
		CASE WHEN @Cell1 > 0 THEN CONVERT(VARCHAR(36), NEWID()) END, CASE WHEN @Cell1 > 0 THEN @Cell1 ELSE 0 END,
		CASE WHEN @Cell2 > 0 THEN CONVERT(VARCHAR(36), NEWID()) END, CASE WHEN @Cell2 > 0 THEN @Cell2 ELSE 0 END,
		CASE WHEN @Cell3 > 0 THEN CONVERT(VARCHAR(36), NEWID()) END, CASE WHEN @Cell3 > 0 THEN @Cell3 ELSE 0 END,
		CASE WHEN @Cell4 > 0 THEN CONVERT(VARCHAR(36), NEWID()) END, CASE WHEN @Cell4 > 0 THEN @Cell4 ELSE 0 END,
		ISNULL(@Upcount, 0), ISNULL(@AcuUpcnt, 0), ISNULL(@MaxupCnt, 0), ISNULL(@Updamage, 0), ISNULL(@Opidx1, -1), ISNULL(@OpValue1, 0),
		ISNULL(@Opidx2, -1), ISNULL(@OpValue2, 0), ISNULL(@Opidx3, -1), ISNULL(@Opvalue3, 0), ISNULL(@Opidx4, -1), ISNULL(@Opvalue4, 0),
		ISNULL(@OPidx5, -1), ISNULL(@Opvalue5, 0), 0, ISNULL(@Owner, 0), ISNULL(@GainDate, @fd), @fd, NULL);
	INSERT INTO adm.ItemLedger (Kind, Userindex, Charidx, Plate, Posx, Code, Uuid, AmountBefore, AmountAfter, WeightBefore,
		WeightAfter, FdateAfter, GoldTaken, Source, Operator)
	VALUES ('recover', @Userindex, @Charidx, @Plate, @Posx, @Code, @Uuid, NULL, @Amount, NULL, @Weight, @fd,
		CASE WHEN @GoldTake > 0 THEN @GoldTake END, @Source, @Operator);
	SET @id = SCOPE_IDENTITY();
	INSERT INTO JoyLog1.dbo.AdminitemLog (Edate, Userindex, Charidx, Fromname, Suserindex, Scharidx, Toname, Code, Serial, Amount,
		Ramount, Durability, Cell1, Cell2, Cell3, Cell4, Upcount, Opidx1, Opvalue1, Opidx2, Opvalue2, State)
	VALUES (@fd, @Userindex, @Charidx, LEFT(ISNULL(@Operator, 'admin'), 20), 0, 0, @name, @Code, @us, 0, @Amount, ISNULL(@Durability, 0),
		CASE WHEN @Cell1 > 0 THEN @Cell1 ELSE 0 END, CASE WHEN @Cell2 > 0 THEN @Cell2 ELSE 0 END, CASE WHEN @Cell3 > 0 THEN @Cell3 ELSE 0 END,
		CASE WHEN @Cell4 > 0 THEN @Cell4 ELSE 0 END, ISNULL(@Upcount, 0), ISNULL(@Opidx1, -1), ISNULL(@OpValue1, 0), ISNULL(@Opidx2, -1),
		ISNULL(@OpValue2, 0), 'Item Recover(Admin)');
	IF @GoldTake > 0
		INSERT INTO JoyLog1.dbo.AdminitemLog (Edate, Userindex, Charidx, Fromname, Suserindex, Scharidx, Toname, Code, Serial, Amount,
			Ramount, Durability, Cell1, Cell2, Cell3, Cell4, Upcount, Opidx1, Opvalue1, Opidx2, Opvalue2, State)
		VALUES (@fd, @Userindex, @Charidx, LEFT(ISNULL(@Operator, 'admin'), 20), 0, 0, @name, 20551, CONVERT(VARCHAR(36), @gu), @g0,
			@g0 - @GoldTake, 0, 0, 0, 0, 0, 0, -1, 0, -1, 0, 'Gold Take(Admin Recover)');
	COMMIT TRANSACTION;
	SELECT @id AS LedgerId, @us AS Uuid, CONVERT(VARCHAR(23), @fd, 121) AS Fdate;
GO

-- ─────────────────────────── откатить запись журнала ───────────────────────────
IF OBJECT_ID('adm.ItemUndo', 'P') IS NOT NULL DROP PROCEDURE adm.ItemUndo;
GO
CREATE PROCEDURE adm.ItemUndo @LedgerId INT,
	@Cap SMALLINT = NULL,             -- откат изъятия: ёмкость сумки (как у выдачи; ячейка занята — первая свободная до @Cap)
	@Operator VARCHAR(64) = NULL
AS
	SET NOCOUNT ON
	SET XACT_ABORT ON
	DECLARE @kind VARCHAR(12), @uid INT, @idx TINYINT, @plate TINYINT, @posx SMALLINT, @code INT, @u UNIQUEIDENTIFIER,
		@ab INT, @aa INT, @wb INT, @wa INT, @fa VARCHAR(23), @done INT, @name VARCHAR(20), @ware INT, @n INT, @x INT,
		@curp TINYINT, @curx SMALLINT, @fd DATETIME, @id INT, @ra INT, @fb DATETIME, @fr DATETIME, @ui INT, @ud INT, @gt INT, @gu UNIQUEIDENTIFIER,
		@g0 INT, @gx SMALLINT;
	SET @fd = GETDATE();
	BEGIN TRANSACTION;
	SELECT @kind = Kind, @uid = Userindex, @idx = Charidx, @plate = Plate, @posx = Posx, @code = Code, @u = Uuid,
		@ab = AmountBefore, @aa = AmountAfter, @wb = WeightBefore, @wa = WeightAfter, @fa = CONVERT(VARCHAR(23), FdateAfter, 121),
		@done = UndoneBy, @fb = FdateBefore, @ui = UuidItems, @ud = UuidDel, @gt = GoldTaken
	  FROM adm.ItemLedger WITH (UPDLOCK, HOLDLOCK) WHERE Id = @LedgerId;
	IF @kind IS NULL OR @kind = 'undo' THROW 51301, 'adm.ItemUndo: нет такой записи', 1;
	IF @done IS NOT NULL THROW 51302, 'adm.ItemUndo: запись уже откачена', 1;
	SELECT @name = Charname, @ware = WareCount FROM dbo.Charinfo WITH (UPDLOCK, HOLDLOCK) WHERE Userindex = @uid AND Charidx = @idx;
	IF @name IS NULL THROW 51303, 'adm.ItemUndo: персонажа нет', 1;
	IF @kind IN ('give', 'stack', 'charge', 'takepart', 'recover')
	BEGIN
		-- строка та же (Uuid + код), количество и время — как записала панель; ячейка — текущая (панель могла переставить:
		-- items.move Fdate не трогает), но только в сумках/складе
		SELECT @n = COUNT(*), @curp = MIN(Plate), @curx = MIN(Posx) FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
		 WHERE Userindex = @uid AND Charidx = @idx AND Uuid = @u AND Code = @code AND Plate IN (1, 2, 5)
		   AND Amount = @aa AND Weight = @wa AND CONVERT(VARCHAR(23), Fdate, 121) = @fa;
		IF @n <> 1 THROW 51304, 'adm.ItemUndo: предмет с тех пор менялся', 1;
		IF @kind IN ('give', 'recover')
		BEGIN
			DELETE FROM dbo.Item WHERE Userindex = @uid AND Charidx = @idx AND Plate = @curp AND Posx = @curx AND Uuid = @u AND Amount = @aa;
			IF @@ROWCOUNT <> 1 THROW 51305, 'adm.ItemUndo: предмет изменился при записи', 1;
			SET @ra = 0;
			-- 19.11: возврат проданного — золото продажи, списанное возвратом, возвращается в строку золота сумки 2
			IF @kind = 'recover' AND ISNULL(@gt, 0) > 0
			BEGIN
				SELECT @gu = Uuid, @g0 = Amount, @gx = Posx FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
				 WHERE Userindex = @uid AND Charidx = @idx AND Plate = 2 AND Code = 20551;
				-- ★ ревизия 27 К-4: как сервер — продажа без строки золота у UPSellitem тоже отказ (строка золота создаётся при
				--   создании персонажа и не удаляется); откат целиком не выполняется, предмет остаётся у игрока
				IF @gu IS NULL THROW 51312, 'adm.ItemUndo: у персонажа нет строки золота (сервер её не удаляет) — откат не выполнен, предмет остаётся', 1;
				IF CAST(@g0 AS BIGINT) + @gt > 2147483647 THROW 51313, 'adm.ItemUndo: золото переполнится', 1;
				UPDATE dbo.Item SET Amount = Amount + @gt
				 WHERE Userindex = @uid AND Charidx = @idx AND Plate = 2 AND Posx = @gx AND Uuid = @gu AND Amount = @g0;
				IF @@ROWCOUNT <> 1 THROW 51305, 'adm.ItemUndo: предмет изменился при записи', 1;
			END
		END
		ELSE
		BEGIN
			-- stack/charge: снять прибавленное; takepart: вернуть снятое (в обоих случаях — к «было» записи, и время — прежнее:
			-- иначе более ранняя запись той же строки не откатилась бы)
			SET @fr = ISNULL(@fb, @fd);
			UPDATE dbo.Item SET Amount = @ab, Weight = @wb, Fdate = @fr
			 WHERE Userindex = @uid AND Charidx = @idx AND Plate = @curp AND Posx = @curx AND Uuid = @u AND Amount = @aa;
			IF @@ROWCOUNT <> 1 THROW 51305, 'adm.ItemUndo: предмет изменился при записи', 1;
			SET @ra = @ab;
		END
		SELECT @plate = @curp, @posx = @curx;
	END
	ELSE IF @kind = 'take'
	BEGIN
		-- ★ ревизия 27 М-2: тот же замок, что у adm.ItemRecover (оба вставляют прежний номер)
		DECLARE @lk2 INT;
		EXEC @lk2 = sp_getapplock @Resource = 'AsdaAdmin.ItemUuidInsert', @LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 15000;
		IF @lk2 < 0 THROW 51314, 'adm.ItemUndo: другой возврат идёт слишком долго — повторите', 1;
		-- тот же экземпляр (тот же Uuid) — только если строк с ним столько же, сколько было без изъятой (живая база и корзина
		-- удалённых; иначе — дюп). Перепроверка 18: М4 — счёт «как было», а не «нет нигде» (исторический дубль Uuid);
		-- М5 — без UPDLOCK/HOLDLOCK (индекса по Uuid нет — держал бы всю таблицу). Старые записи без счёта — «нет нигде».
		IF (SELECT COUNT(*) FROM dbo.Item WHERE Uuid = @u) <> ISNULL(@ui, 1) - 1
		   OR (SELECT COUNT(*) FROM dbo.Del_Item WHERE Uuid = @u) <> ISNULL(@ud, 0)
			THROW 51306, 'adm.ItemUndo: этот экземпляр уже есть в базе', 1;
		IF @Cap IS NULL OR @Cap < 1 OR @Cap > adm.ItemPlateCap(@plate, @ware) THROW 51307, 'adm.ItemUndo: неверная ёмкость сумки', 1;
		SET @x = NULL;
		IF @posx < @Cap AND NOT EXISTS (SELECT 1 FROM dbo.Item WITH (UPDLOCK, HOLDLOCK)
		                                 WHERE Userindex = @uid AND Charidx = @idx AND Plate = @plate AND Posx = @posx)
			SET @x = @posx;
		ELSE
		BEGIN
			-- решение владельца 18.11: ячейка занята — первая свободная той же сумки
			SELECT @x = MIN(v.n) FROM (SELECT a.d + 10 * b.d + 100 * c.d AS n
			                             FROM (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)) a (d)
			                            CROSS JOIN (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)) b (d)
			                            CROSS JOIN (VALUES (0), (1), (2)) c (d)) v
			 WHERE v.n < @Cap AND NOT EXISTS (SELECT 1 FROM dbo.Item i WITH (UPDLOCK, HOLDLOCK)
			                    WHERE i.Userindex = @uid AND i.Charidx = @idx AND i.Plate = @plate AND i.Posx = v.n);
		END
		IF @x IS NULL THROW 51308, 'adm.ItemUndo: в сумке нет свободной ячейки', 1;
		INSERT INTO dbo.Item (Userindex, Charidx, Uuid, Code, Plate, Posx, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2,
			Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3,
			Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate)
		SELECT Userindex, Charidx, Uuid, Code, Plate, @x, Amount, Durability, Weight, Uc1, Cell1, Uc2, Cell2,
			Uc3, Cell3, Uc4, Cell4, Upcount, AcuUpcnt, MaxupCnt, Updamage, Opidx1, OpValue1, Opidx2, OpValue2, Opidx3, Opvalue3,
			Opidx4, Opvalue4, OPidx5, Opvalue5, Refine, Owner, GainDate, Fdate, Rdate
		  FROM adm.ItemTaken WHERE LedgerId = @LedgerId AND Uuid = @u AND Userindex = @uid AND Charidx = @idx;
		IF @@ROWCOUNT <> 1 THROW 51309, 'adm.ItemUndo: снимка нет', 1;
		SELECT @posx = @x, @ra = @ab;
	END
	ELSE THROW 51310, 'adm.ItemUndo: неизвестный вид записи', 1;

	INSERT INTO adm.ItemLedger (Kind, Userindex, Charidx, Plate, Posx, Code, Uuid, AmountBefore, AmountAfter, WeightBefore,
		WeightAfter, FdateAfter, UndoOf, Operator)
	VALUES ('undo', @uid, @idx, @plate, @posx, @code, @u, @aa, CASE WHEN @kind IN ('give', 'recover') THEN NULL ELSE @ab END, @wa,
		CASE WHEN @kind IN ('give', 'recover') THEN NULL ELSE @wb END, ISNULL(@fr, @fd), @LedgerId, @Operator);
	SET @id = SCOPE_IDENTITY();
	UPDATE adm.ItemLedger SET UndoneBy = @id WHERE Id = @LedgerId AND UndoneBy IS NULL;
	IF @@ROWCOUNT <> 1 THROW 51311, 'adm.ItemUndo: запись уже откачена', 1;
	INSERT INTO JoyLog1.dbo.AdminitemLog (Edate, Userindex, Charidx, Fromname, Suserindex, Scharidx, Toname, Code, Serial, Amount,
		Ramount, Durability, Cell1, Cell2, Cell3, Cell4, Upcount, Opidx1, Opvalue1, Opidx2, Opvalue2, State)
	VALUES (@fd, @uid, @idx, LEFT(ISNULL(@Operator, 'admin'), 20), 0, 0, @name, @code, CONVERT(VARCHAR(36), @u),
		ISNULL(@aa, 0), ISNULL(@ra, 0), 0, 0, 0, 0, 0, 0, -1, 0, -1, 0, 'Item Undo(Admin)');
	COMMIT TRANSACTION;
	SELECT @id AS LedgerId, @kind AS Kind, @plate AS Plate, @posx AS Posx;
GO
PRINT 'adminc_06_items: OK';
