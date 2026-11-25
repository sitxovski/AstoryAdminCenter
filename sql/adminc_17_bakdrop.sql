-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_17_bakdrop.sql — уборка служебных копий (*_bak_*, AsdaProcBak*, …) панелью (шаг А5.8, план §4 Д, §5.1; отчёт
   Reports/admin_center/impl_a5_live_20261121.md, раздел А5.8). Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin) ПОСЛЕ adminc_16_dbbackup
   (нужны adm.dbbackup_db и adm.dbbackup), под Windows-входом Administrator через shared memory (sqlcmd -S lpc:.\SQLEXPRESS -E — sysadmin).
   Тот же файл самотест выполняет на LocalDB под SET LANGUAGE Russian (там пользователя asda_admin может не быть — выдача прав пропускается).
   Повторный запуск безопасен. 21.11.2026.

   КАТАЛОГ adm.bakdrop_obj — ЕДИНСТВЕННЫЙ источник решения «можно убрать / нужна откату / неизвестно» (засевается ниже, правится только этим
   файлом и ревизией): verdict = 'drop' — только то, что доказано лишним (откат копию не читает, её содержимое дословно есть в файле отката
   репозитория или пусто); 'rollback' — копию читает откат (ref_file) — НЕ удаляется никогда; 'unknown' — сток / происхождение не установлено.
   Объект с «копийным» именем, которого нет в каталоге, — «неизвестно» (панель его показывает, удалить не даёт).
   ПРАВА (без sysadmin / db_owner у служебных логинов). adm.BakScan и adm.BakDrop подписаны сертификатом adm_bakdrop_cert (закрытый ключ после
   подписи стирается); из открытой части в master — логин adm_bakdrop_signer (войти им нельзя), его пользователь adm_bakdrop_u в базах списка:
   VIEW DEFINITION и SELECT sys.sql_expression_dependencies (поиск ссылок на копию), IMPERSONATE на adm_bakdrop_x; в msdb — SELECT истории
   бэкапов и шагов заданий. adm_bakdrop_x — пользователь БЕЗ входа в каждой игровой базе: CONTROL ТОЛЬКО на объекты каталога с verdict = 'drop',
   существующие на момент запуска файла, — белый список на уровне прав: копию «нужна откату» не удалить даже в обход процедуры. DROP идёт от его
   имени (EXECUTE AS USER … REVERT на одну инструкцию): у вызывающего asda_admin в игровых базах DENY ALTER, а DENY сильнее CONTROL подписи (3701).
   asda_admin: EXECUTE adm.BakState / adm.BakDrop, SELECT таблиц adm.bakdrop*, прямой записи нет.
   УДАЛЕНИЕ (adm.BakDrop): слово bakdrop; база из списка панели (не AsdaAdmin); имена — только каталог 'drop'; свежий (≤ fresh_hours) проверенный
   (VERIFYONLY) бэкап панели этой базы, его набор в истории msdb, объект не менялся после начала бэкапа; в ОДНОЙ транзакции — повторный поиск
   ссылок (выражения, текст модулей с границей слова, внешние ключи, триггеры, синонимы, шаги заданий SQL Agent), снимок в adm.bakdrop_log
   (DDL, строки, размер, файл бэкапа) и DROP. Отмены нет: вернуть объект — восстановить бэкап на стенд LocalDB и перенести вручную. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.bakdrop_cfg') IS NULL
CREATE TABLE adm.bakdrop_cfg (
    id          TINYINT NOT NULL CONSTRAINT PK_adm_bakdrop_cfg PRIMARY KEY CONSTRAINT CK_adm_bakdrop_cfg_one CHECK (id = 1),
    fresh_hours INT     NOT NULL CONSTRAINT DF_adm_bakdrop_cfg_fresh DEFAULT 6 CONSTRAINT CK_adm_bakdrop_cfg_fresh CHECK (fresh_hours BETWEEN 1 AND 48)
);
GO
IF NOT EXISTS (SELECT 1 FROM adm.bakdrop_cfg) INSERT adm.bakdrop_cfg (id) VALUES (1);
GO
IF OBJECT_ID(N'adm.bakdrop_obj') IS NULL
CREATE TABLE adm.bakdrop_obj (
    db        SYSNAME        NOT NULL,
    sch       SYSNAME        NOT NULL,
    name      SYSNAME        NOT NULL,
    kind      CHAR(2)        NOT NULL,                               -- sys.objects.type: 'U ' таблица, 'P ' процедура
    verdict   VARCHAR(10)    NOT NULL CONSTRAINT CK_adm_bakdrop_obj_verdict CHECK (verdict IN ('drop', 'rollback', 'unknown')),
    origin    NVARCHAR(400)  NOT NULL,                               -- кто и когда создал (миграция / инструмент)
    needed_by NVARCHAR(400)  NULL,                                   -- 'rollback': чей откат читает копию
    ref_file  NVARCHAR(400)  NULL,                                   -- файл репозитория (от port\), который читает копию / где её дословный текст
    evidence  NVARCHAR(800)  NOT NULL,                               -- почему такой вердикт (проверка 21.11)
    CONSTRAINT PK_adm_bakdrop_obj PRIMARY KEY (db, sch, name)
);
GO
IF OBJECT_ID(N'adm.bakdrop_log') IS NULL
CREATE TABLE adm.bakdrop_log (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_bakdrop_log PRIMARY KEY,
    batch           UNIQUEIDENTIFIER NOT NULL,                       -- одно удаление (одна транзакция) — один batch
    db              SYSNAME        NOT NULL,
    sch             SYSNAME        NOT NULL,
    name            SYSNAME        NOT NULL,
    kind            CHAR(2)        NOT NULL,
    ddl             NVARCHAR(MAX)  NULL,                             -- текст процедуры / CREATE TABLE по sys.columns (снимок до DROP)
    rows_n          BIGINT         NULL,
    kb              BIGINT         NULL,
    created_utc     DATETIME2(0)   NULL,
    modified_utc    DATETIME2(0)   NULL,
    origin          NVARCHAR(400)  NULL,
    backup_id       INT            NOT NULL,                         -- adm.dbbackup.id — бэкап, из которого объект возвращается на стенд
    backup_file     NVARCHAR(400)  NOT NULL,
    backup_finished DATETIME2(0)   NOT NULL,
    by_login        NVARCHAR(64)   NOT NULL,
    dropped_at      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_bakdrop_log_at DEFAULT SYSUTCDATETIME()
);
GO

/* ---------- каталог (решение — по проверке 21.11: SSH-чтение sys.*, ссылки в репозитории, сверка текстов) ---------- */
DECLARE @k TABLE (db SYSNAME, sch SYSNAME, name SYSNAME, kind CHAR(2), verdict VARCHAR(10), origin NVARCHAR(400), needed_by NVARCHAR(400),
                  ref_file NVARCHAR(400), evidence NVARCHAR(800));
INSERT @k VALUES
-- можно убрать: откат копию не читает, её текст дословно в файле отката (сверка нормализованного текста 21.11) / копия пуста
(N'Joy1', N'dbo', N'UPUserLogin_bak_20261012_ac0', 'P', 'drop', N'ac0_01_migrate.sql (12.10.2026, P51): копия стокового UPUserLogin', NULL,
 N'Server\Docs\SQL\ac0_99_rollback.sql', N'тело копии дословно = ac0_99_rollback.sql (откат копию не читает), состояние вытеснено ac0r → ac1 → L09'),
(N'Joy1', N'dbo', N'UPUserLogin_bak_20261012_ac0r', 'P', 'drop', N'ac0r_01_migrate.sql (12.10.2026): копия UPUserLogin перед ac0r', NULL,
 N'Server\Docs\SQL\ac0r_99_rollback.sql', N'тело копии дословно = ac0r_99_rollback.sql (откат копию не читает), вытеснено ac1 → L09'),
(N'Joy1', N'dbo', N'UPUserLogin_bak_20261012_ac1', 'P', 'drop', N'ac1_01_migrate.sql (12.10.2026, P52): копия UPUserLogin перед ac1', NULL,
 N'Server\Docs\SQL\ac1_99_rollback.sql', N'тело копии дословно = ac1_99_rollback.sql, шапка отката: копия — архив, не часть патча'),
(N'Joy1', N'dbo', N'UP_AC_IdentityCheck_bak_20261012_ac0r', 'P', 'drop', N'ac0r_01_migrate.sql (12.10.2026): копия UP_AC_IdentityCheck перед ac0r', NULL,
 N'Server\Docs\SQL\ac0r_99_rollback.sql', N'тело копии дословно = ac0r_99_rollback.sql (откат копию не читает)'),
(N'Joy1', N'dbo', N'cashgift_bak_procs_20261101', 'U', 'drop', N'Reports\cash_gift\sql\02_backup.sql (02.11.2026): тексты процедур до cash_gift', NULL,
 N'Reports\cash_gift\sql\05_rollback.sql', N'2 строки, обе «absent» (процедур до правки не было), 05_rollback только удаляет новые процедуры'),
-- нужна откату: копию читает откат — НЕ удалять никогда
(N'Joy1', N'dbo', N'AsdaProcBackup', 'U', 'rollback', N'ac0x / ac0y / ac0z _01_migrate.sql (18–19.11.2026): прежние тексты процедур',
 N'откат ac0x, ac0y, ac0z (UPCharSkillinit, UPClanActPointDonation, UPTimeoutDeleteItem)', N'Server\Docs\SQL\ac0y_99_rollback.sql', N'откаты читают Definition по Patch / ProcName'),
(N'Joy1', N'dbo', N'AsdaProcBak_jlpresm_20261102', 'U', 'rollback', N'deploy_jl_presm.py (02.11.2026): текст UPPreSMConnect',
 N'откат jl_presm (deploy_jl_presm.py --rollback)', N'Server\Patches\AsdaPatch\tools\deploy_jl_presm.py', N'откат возвращает текст из копии'),
(N'Joy1', N'dbo', N'AsdaProcBak_p100_20261101', 'U', 'rollback', N'P100 01_backup_procs.sql (01.11.2026): живые тексты 17 процедур',
 N'откат P100 (09_rollback_procs.sql, запасной путь)', N'Server\SQL\p100_charge_stack\README.md', N'README P100: запасной путь отката процедур — тексты в копии'),
(N'Joy1', N'dbo', N'Item_bak_charge_20261101', 'U', 'rollback', N'P100 11_stack_backup.sql (01.11.2026)', N'откат укладки P100 (19_stack_rollback.sql)',
 N'Server\SQL\p100_charge_stack\19_stack_rollback.sql', N'откат возвращает строки из копии'),
(N'Joy1', N'dbo', N'CharSlot_bak_charge_20261101', 'U', 'rollback', N'P100 11_stack_backup.sql (01.11.2026)', N'откат укладки P100 (19_stack_rollback.sql)',
 N'Server\SQL\p100_charge_stack\19_stack_rollback.sql', N'откат возвращает строки из копии'),
(N'Joy1', N'dbo', N'Item_chargeDel_20261101', 'U', 'rollback', N'P100 12_stack_apply.sql (01.11.2026): затронутые персонажи', N'откат укладки P100 (19_stack_rollback.sql)',
 N'Server\SQL\p100_charge_stack\19_stack_rollback.sql', N'откат берёт персонажей из таблицы'),
(N'Joy1', N'dbo', N'Item_bak_p102_20261104', 'U', 'rollback', N'deploy_p102_all.py (04.11.2026)', N'откат P102 (p102_sql/05_rollback.sql)',
 N'Reports\item_dedup\p102_sql\05_rollback.sql', N'откат возвращает строки из копии'),
(N'Joy1', N'dbo', N'Item_bak_veteran_20261107', 'U', 'rollback', N'deploy_veteran_delete_20261107.py (07.11.2026)', N'откат удаления Veteran Reindeer (--rollback)',
 N'Server\Patches\AsdaPatch\tools\deploy_veteran_delete_20261107.py', N'откат возвращает 5 строк из копии'),
(N'Joy1', N'dbo', N'Item_bak_costumesowel_20261110', 'U', 'rollback', N'deploy_p124_sql.py (10.11.2026, P124)', N'откат SQL P124 (вручную из копии)',
 N'Server\Patches\AsdaPatch\tools\deploy_p124_sql.py', N'шапка выкладчика: SQL откатывается из копии вручную'),
(N'Joy1', N'dbo', N'P45_Backup_PetName', 'U', 'rollback', N'P45 часть В 03_legacy_arabic_marker.sql (08.10.2026)', N'откат P45-В (97_rollback_legacy_marker.sql)',
 N'Server\Docs\_Common\P45_multilang_text\SQL\97_rollback_legacy_marker.sql', N'откат возвращает клички из копии'),
(N'Joy1', N'dbo', N'Item_bak_sowelfill_20261031', 'U', 'rollback', N'db_sowel_fill.py --backup (31.10.2026)', N'откат заполнения сауэла (db_sowel_fill.py --rollback)',
 N'Reports\armor_capacity\db_sowel_fill.py', N'--rollback проверяет наличие копий'),
(N'Joy1', N'dbo', N'Exitem_bak_sowelfill_20261031', 'U', 'rollback', N'db_sowel_fill.py --backup (31.10.2026)', N'откат заполнения сауэла (db_sowel_fill.py --rollback)',
 N'Reports\armor_capacity\db_sowel_fill.py', N'--rollback проверяет наличие копий'),
(N'Joy1', N'dbo', N'SowelFill_log_20261031', 'U', 'rollback', N'db_sowel_fill.py --apply (31.10.2026): журнал изменённых строк', N'откат заполнения сауэла (db_sowel_fill.py --rollback)',
 N'Reports\armor_capacity\db_sowel_fill.py', N'обратный UPDATE идёт по журналу'),
(N'Joy1', N'dbo', N'Del_Charinfo_bak_20261118_ac0v', 'U', 'rollback', N'ac0v_01_migrate.sql (18.11.2026)', N'откат ac0v (шапка: копия не удаляется)',
 N'Server\Docs\SQL\ac0v_99_rollback.sql', N'шапка отката прямо запрещает удаление копии'),
(N'Joy1', N'dbo', N'UPUserLogin_bak_20261121_l09', 'P', 'rollback', N'l09_01_migrate.sql (21.11.2026, L09): копия UPUserLogin', N'откат L09 (l09_99_rollback.sql)',
 N'Server\Docs\SQL\l09_99_rollback.sql', N'откат берёт тело из копии'),
(N'joylog1', N'dbo', N'Stat_UpgradeSeparation_bak_20261101', 'U', 'rollback', N'upgrade_separation_stat_rollback_20261101.sql (01.11.2026)',
 N'возврат статистики разделения улучшений', N'Server\SQL\upgrade_separation_stat_rollback_20261101.sql', N'копия строк перед DROP таблицы статистики'),
-- неизвестно: сток оригинала или происхождение не установлено — панелью не удаляется
(N'Joy1', N'dbo', N'UPUserLogin_BAk', 'P', 'unknown', N'сток оригинала (создан 11.06.2010, изменён 18.06.2026 — кем, не установлено)', NULL, NULL,
 N'не наша копия: имя стоковое, упоминается проверками ac0 / ac1 / L09'),
(N'AsdaStoryOp', N'dbo', N'OpStat_SaleItem_Original', 'P', 'unknown', N'сток оригинала (11.06.2010)', NULL, NULL, N'не наша копия: процедура стока');
-- 15 таблиц копий правки item_dedup 01.11 (stage2) и 15 — её второго прохода F1 (…b): читают откаты stage2 / sql_f1
INSERT @k SELECT N'Joy1', N'dbo', t.n + N'_bak_dedup_20261101' + s.sfx, 'U', 'rollback',
       CASE WHEN s.sfx = N'' THEN N'item_dedup stage2 02_backup.sql (01.11.2026)' ELSE N'item_dedup stage2 sql_f1 02_backup.sql (02.11.2026)' END,
       CASE WHEN s.sfx = N'' THEN N'откат item_dedup stage2 (05_rollback.sql)' ELSE N'откат item_dedup F1 (sql_f1/05_rollback.sql)' END
       + CASE WHEN s.sfx = N'b' AND t.n = N'Item' THEN N', условие P100 12_stack_apply.sql' ELSE N'' END,
       CASE WHEN s.sfx = N'' THEN N'Reports\item_dedup\stage2\sql\05_rollback.sql' ELSE N'Reports\item_dedup\stage2\sql_f1\05_rollback.sql' END,
       N'откат возвращает таблицу целиком из копии'
FROM (VALUES (N'Item'), (N'Exitem'), (N'Del_item'), (N'Del_Exitem'), (N'ItemPostBox'), (N'gifts'), (N'CharEpisode'), (N'Del_CharEpisode'),
             (N'CharSkillitem'), (N'ItemCoolTime'), (N'CharFishBookInfo'), (N'Del_CharFishBookInfo'), (N'CharSlot'), (N'Del_CharSlot'),
             (N'SellitemAlarm')) t(n)
CROSS JOIN (VALUES (N''), (N'b')) s(sfx);
MERGE adm.bakdrop_obj AS t
USING @k AS s ON t.db = s.db AND t.sch = s.sch AND t.name = s.name
WHEN MATCHED THEN UPDATE SET kind = s.kind, verdict = s.verdict, origin = s.origin, needed_by = s.needed_by, ref_file = s.ref_file, evidence = s.evidence
WHEN NOT MATCHED BY TARGET THEN INSERT (db, sch, name, kind, verdict, origin, needed_by, ref_file, evidence)
     VALUES (s.db, s.sch, s.name, s.kind, s.verdict, s.origin, s.needed_by, s.ref_file, s.evidence)
WHEN NOT MATCHED BY SOURCE THEN DELETE;
GO

/* ---------- снятие прежней подписи (повторный запуск): процедуры, сертификат, логин и пользователи пересоздаются ниже ---------- */
DECLARE @d SYSNAME, @q NVARCHAR(MAX);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM sys.databases WHERE state_desc = 'ONLINE' AND is_read_only = 0 AND name NOT IN (N'tempdb', N'model');
OPEN c; FETCH c INTO @d;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @q = N'EXEC ' + QUOTENAME(@d) + N'.sys.sp_executesql @s';
    EXEC sys.sp_executesql @q, N'@s NVARCHAR(MAX)', N'IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N''adm_bakdrop_u'') DROP USER adm_bakdrop_u;
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N''adm_bakdrop_x'') DROP USER adm_bakdrop_x;';
    FETCH c INTO @d;
END
CLOSE c; DEALLOCATE c;
IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'adm_bakdrop_signer') DROP LOGIN adm_bakdrop_signer;
EXEC master.sys.sp_executesql N'IF EXISTS (SELECT 1 FROM sys.certificates WHERE name = N''adm_bakdrop_cert'') DROP CERTIFICATE adm_bakdrop_cert;';
IF OBJECT_ID(N'adm.BakScan') IS NOT NULL DROP PROCEDURE adm.BakScan;
IF OBJECT_ID(N'adm.BakState') IS NOT NULL DROP PROCEDURE adm.BakState;
IF OBJECT_ID(N'adm.BakDrop') IS NOT NULL DROP PROCEDURE adm.BakDrop;
IF EXISTS (SELECT 1 FROM sys.certificates WHERE name = N'adm_bakdrop_cert') DROP CERTIFICATE adm_bakdrop_cert;
GO

/* Поиск копий и ссылок на них. Вызывающий создаёт #bak, #bakref и #bakwarn (их видят вложенный вызов и его динамический SQL). @db — копии
   только этой базы (NULL — всех баз списка, кроме AsdaAdmin); ссылки ищутся во ВСЕХ базах списка (в том числе AsdaAdmin), в master и msdb
   (модули и шаги заданий) и в серверных триггерах. ★ ревизия 48 С-1: база, где ссылки прочитать нельзя (не ONLINE, нет пользователя подписи
   adm_bakdrop_u, есть модули без текста WITH ENCRYPTION), — строка #bakwarn («не прочитано» ≠ «ссылок нет»); BakDrop при ней отказывает.
   Имена «копийные»: _bak…, …backup…, _ГГГГММДД…, _Original, _old, а также всё из каталога. Схема adm (объекты самой панели) не смотрится.
   Время объектов — UTC (sys.objects хранит местное). Только чтение. */
CREATE PROCEDURE adm.BakScan @db SYSNAME = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @d SYSNAME, @q NVARCHAR(MAX), @x NVARCHAR(300), @tz INT = DATEDIFF(MINUTE, SYSDATETIME(), SYSUTCDATETIME());
    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
        SELECT l.name FROM adm.dbbackup_db l JOIN sys.databases s ON s.name = l.name COLLATE DATABASE_DEFAULT
        WHERE s.state_desc = N'ONLINE' AND l.name <> N'AsdaAdmin' AND (@db IS NULL OR l.name = @db);
    OPEN c; FETCH c INTO @d;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @x = QUOTENAME(@d);
        SET @q = N'INSERT #bak (db, sch, name, oid, type, type_desc, created, modified, rows_n, kb)
SELECT @d, s.name, o.name, o.object_id, o.type, o.type_desc, DATEADD(MINUTE, @tz, o.create_date), DATEADD(MINUTE, @tz, o.modify_date),
       (SELECT SUM(p.rows) FROM ' + @x + N'.sys.partitions p WHERE p.object_id = o.object_id AND p.index_id IN (0, 1)),
       (SELECT SUM(a.total_pages) * 8 FROM ' + @x + N'.sys.partitions p JOIN ' + @x + N'.sys.allocation_units a ON a.container_id = p.partition_id
        WHERE p.object_id = o.object_id)
FROM ' + @x + N'.sys.objects o JOIN ' + @x + N'.sys.schemas s ON s.schema_id = o.schema_id
WHERE o.is_ms_shipped = 0 AND o.type IN (''U'', ''P'', ''V'', ''FN'', ''IF'', ''TF'') AND s.name <> N''adm''
  AND (o.name LIKE N''%[_]bak%'' OR o.name LIKE N''%backup%'' OR o.name LIKE N''%[_]20[0-9][0-9][01][0-9][0-3][0-9]%''
       OR o.name LIKE N''%[_]original'' OR o.name LIKE N''%[_]old''
       OR EXISTS (SELECT 1 FROM adm.bakdrop_obj k WHERE k.db = @d AND k.sch = s.name COLLATE DATABASE_DEFAULT AND k.name = o.name COLLATE DATABASE_DEFAULT));';
        EXEC sys.sp_executesql @q, N'@d SYSNAME, @tz INT', @d, @tz;
        FETCH c INTO @d;
    END
    CLOSE c; DEALLOCATE c;
    /* ссылки: в каждой базе списка — зависимости выражений, текст модулей (имя с границей слова), синонимы; в базе копии — внешние ключи,
       триггеры на таблице. Объект сам на себя не ссылается. */
    DECLARE @st NVARCHAR(60), @ok INT, @enc INT;
    DECLARE r CURSOR LOCAL FAST_FORWARD FOR
        SELECT l.name, s.state_desc FROM (SELECT name FROM adm.dbbackup_db UNION SELECT N'master' UNION SELECT N'msdb') l
        LEFT JOIN sys.databases s ON s.name = l.name COLLATE DATABASE_DEFAULT;
    OPEN r; FETCH r INTO @d, @st;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @x = QUOTENAME(@d);
        IF @st IS NULL OR @st <> N'ONLINE'
        BEGIN
            INSERT #bakwarn (db, why) VALUES (@d, N'база не ONLINE (' + ISNULL(@st, N'нет на сервере') + N')');
            FETCH r INTO @d, @st;
            CONTINUE;
        END
        SET @q = N'SELECT @ok = CASE WHEN EXISTS (SELECT 1 FROM ' + @x + N'.sys.database_principals WHERE name = N''adm_bakdrop_u'') THEN 1 ELSE 0 END,
       @enc = (SELECT COUNT(*) FROM ' + @x + N'.sys.sql_modules WHERE definition IS NULL);';
        EXEC sys.sp_executesql @q, N'@ok INT OUTPUT, @enc INT OUTPUT', @ok OUTPUT, @enc OUTPUT;
        IF @ok = 0
            INSERT #bakwarn (db, why) VALUES (@d, N'нет пользователя подписи adm_bakdrop_u (база добавлена в список после установки adminc_17)');
        IF @enc > 0
            INSERT #bakwarn (db, why) VALUES (@d, N'модулей без текста (WITH ENCRYPTION): ' + CAST(@enc AS NVARCHAR(12)));
        IF @ok = 0 OR @enc > 0
        BEGIN
            FETCH r INTO @d, @st;
            CONTINUE;
        END
        SET @q = N'INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
SELECT b.db, b.sch, b.name, @d, ISNULL(OBJECT_SCHEMA_NAME(e.referencing_id, DB_ID(@d)), N''?''), ISNULL(OBJECT_NAME(e.referencing_id, DB_ID(@d)), N''#''
       + CAST(e.referencing_id AS NVARCHAR(12))), ISNULL(o.type, ''?''), N''expr''
FROM ' + @x + N'.sys.sql_expression_dependencies e JOIN #bak b ON b.name = e.referenced_entity_name COLLATE DATABASE_DEFAULT
LEFT JOIN ' + @x + N'.sys.objects o ON o.object_id = e.referencing_id
WHERE ((e.referenced_database_name IS NULL AND b.db = @d) OR e.referenced_database_name COLLATE DATABASE_DEFAULT = b.db)
  AND NOT (b.db = @d AND e.referencing_id = b.oid);
INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
SELECT b.db, b.sch, b.name, @d, s.name, o.name, o.type, N''text''
FROM ' + @x + N'.sys.sql_modules m JOIN ' + @x + N'.sys.objects o ON o.object_id = m.object_id JOIN ' + @x + N'.sys.schemas s ON s.schema_id = o.schema_id
JOIN #bak b ON CHARINDEX(b.name, m.definition COLLATE DATABASE_DEFAULT) > 0
  AND PATINDEX(N''%[^A-Za-z0-9_]'' + REPLACE(REPLACE(REPLACE(b.name, N''['', N''[[]''), N''_'', N''[_]''), N''%'', N''[%]'') + N''[^A-Za-z0-9_]%'',
               N'' '' + m.definition COLLATE DATABASE_DEFAULT + N'' '') > 0
WHERE NOT (b.db = @d AND m.object_id = b.oid);
INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
SELECT b.db, b.sch, b.name, @d, s.name, y.name, ''SN'', N''synonym''
FROM ' + @x + N'.sys.synonyms y JOIN ' + @x + N'.sys.schemas s ON s.schema_id = y.schema_id
JOIN #bak b ON PATINDEX(N''%[^A-Za-z0-9_]'' + REPLACE(REPLACE(REPLACE(b.name, N''['', N''[[]''), N''_'', N''[_]''), N''%'', N''[%]'') + N''[^A-Za-z0-9_]%'',
               N'' '' + y.base_object_name COLLATE DATABASE_DEFAULT + N'' '') > 0;
INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
SELECT b.db, b.sch, b.name, @d, ISNULL(OBJECT_SCHEMA_NAME(f.parent_object_id, DB_ID(@d)), N''?''), f.name, ''F'', N''fk''
FROM ' + @x + N'.sys.foreign_keys f JOIN #bak b ON b.db = @d AND (f.referenced_object_id = b.oid OR f.parent_object_id = b.oid);
INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
SELECT b.db, b.sch, b.name, @d, b.sch, t.name, ''TR'', N''trigger''
FROM ' + @x + N'.sys.triggers t JOIN #bak b ON b.db = @d AND t.parent_id = b.oid;';
        EXEC sys.sp_executesql @q, N'@d SYSNAME', @d;
        FETCH r INTO @d, @st;
    END
    CLOSE r; DEALLOCATE r;
    /* серверные триггеры (ревизия 48, мелочь 8): текст — sys.server_sql_modules (право VIEW ANY DEFINITION у логина подписи) */
    INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
    SELECT b.db, b.sch, b.name, N'(server)', N'trigger', t.name, 'TR', N'srvtrg'
    FROM sys.server_sql_modules m JOIN sys.server_triggers t ON t.object_id = m.object_id
    JOIN #bak b ON CHARINDEX(b.name, m.definition COLLATE DATABASE_DEFAULT) > 0
      AND PATINDEX(N'%[^A-Za-z0-9_]' + REPLACE(REPLACE(REPLACE(b.name, N'[', N'[[]'), N'_', N'[_]'), N'%', N'[%]') + N'[^A-Za-z0-9_]%',
                   N' ' + m.definition COLLATE DATABASE_DEFAULT + N' ') > 0;
    IF EXISTS (SELECT 1 FROM sys.server_sql_modules WHERE definition IS NULL)
        INSERT #bakwarn (db, why) VALUES (N'(server)', N'серверные триггеры без текста (WITH ENCRYPTION)');
    INSERT #bakref (db, sch, name, rdb, rsch, rname, rtype, how)
    SELECT b.db, b.sch, b.name, N'msdb', N'job', j.name + N' / ' + st.step_name, 'J', N'job'
    FROM msdb.dbo.sysjobsteps st JOIN msdb.dbo.sysjobs j ON j.job_id = st.job_id
    JOIN #bak b ON CHARINDEX(b.name, st.command COLLATE DATABASE_DEFAULT) > 0
      AND PATINDEX(N'%[^A-Za-z0-9_]' + REPLACE(REPLACE(REPLACE(b.name, N'[', N'[[]'), N'_', N'[_]'), N'%', N'[%]') + N'[^A-Za-z0-9_]%',
                   N' ' + st.command COLLATE DATABASE_DEFAULT + N' ') > 0;
END
GO

/* Список копий для панели: найденные объекты и строки каталога (в том числе отсутствующие на сервере), вердикт, ссылки. Только чтение. */
CREATE PROCEDURE adm.BakState
AS
BEGIN
    SET NOCOUNT ON;
    CREATE TABLE #bak (db SYSNAME COLLATE DATABASE_DEFAULT, sch SYSNAME COLLATE DATABASE_DEFAULT, name SYSNAME COLLATE DATABASE_DEFAULT, oid INT,
                       type CHAR(2) COLLATE DATABASE_DEFAULT, type_desc NVARCHAR(60) COLLATE DATABASE_DEFAULT, created DATETIME2(0), modified DATETIME2(0),
                       rows_n BIGINT, kb BIGINT);
    CREATE TABLE #bakref (db SYSNAME COLLATE DATABASE_DEFAULT, sch SYSNAME COLLATE DATABASE_DEFAULT, name SYSNAME COLLATE DATABASE_DEFAULT,
                          rdb SYSNAME COLLATE DATABASE_DEFAULT, rsch NVARCHAR(128) COLLATE DATABASE_DEFAULT, rname NVARCHAR(400) COLLATE DATABASE_DEFAULT,
                          rtype CHAR(2) COLLATE DATABASE_DEFAULT, how VARCHAR(10) COLLATE DATABASE_DEFAULT);
    CREATE TABLE #bakwarn (db SYSNAME COLLATE DATABASE_DEFAULT, why NVARCHAR(400) COLLATE DATABASE_DEFAULT);
    EXEC adm.BakScan NULL;
    ;WITH rf AS (SELECT DISTINCT db, sch, name, rdb, rsch, rname, rtype, how FROM #bakref),
          ra AS (SELECT db, sch, name, COUNT(*) AS refs_n,
                        LEFT(STRING_AGG(CAST(rdb + N'.' + rsch + N'.' + rname + N' (' + how + N')' AS NVARCHAR(MAX)), N', '), 2000) AS refs
                 FROM rf GROUP BY db, sch, name)
    SELECT COALESCE(b.db, k.db) AS db, COALESCE(b.sch, k.sch) AS sch, COALESCE(b.name, k.name) AS name, RTRIM(COALESCE(b.type, k.kind)) AS type,
           b.type_desc, CAST(CASE WHEN b.oid IS NULL THEN 0 ELSE 1 END AS BIT) AS present, b.created AS created_utc, b.modified AS modified_utc,
           b.rows_n, b.kb, ISNULL(k.verdict, 'unknown') AS verdict, CAST(CASE WHEN k.name IS NULL THEN 0 ELSE 1 END AS BIT) AS in_catalog,
           RTRIM(k.kind) AS kind, k.origin, k.needed_by, k.ref_file, k.evidence, ISNULL(ra.refs_n, 0) AS refs_n, ra.refs
    FROM #bak b
    FULL JOIN adm.bakdrop_obj k ON k.db = b.db AND k.sch = b.sch AND k.name = b.name
    LEFT JOIN ra ON ra.db = COALESCE(b.db, k.db) AND ra.sch = COALESCE(b.sch, k.sch) AND ra.name = COALESCE(b.name, k.name)
    ORDER BY 1, CASE ISNULL(k.verdict, 'unknown') WHEN 'drop' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END, 3;
    SELECT db, why FROM #bakwarn ORDER BY db;                          -- второй набор: базы, где ссылки не прочитаны (ревизия 48 С-1)
END
GO

/* Удаление копий одной базы одной транзакцией. @names — JSON-массив имён «схема.имя» (или «имя» — схема dbo), 1…60. */
CREATE PROCEDURE adm.BakDrop @db SYSNAME, @names NVARCHAR(MAX), @backup_id INT, @by NVARCHAR(64), @confirm NVARCHAR(20) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @counts NVARCHAR(MAX), @tz INT = DATEDIFF(MINUTE, SYSDATETIME(), SYSUTCDATETIME()), @sqlstart DATETIME2(0), @upd DATETIME2(0), @late NVARCHAR(MAX),
            @fresh INT, @msg NVARCHAR(2048), @bstart DATETIME2(0), @bfin DATETIME2(0), @bfile NVARCHAR(400), @n INT, @batch UNIQUEIDENTIFIER = NEWID(),
            @x NVARCHAR(300), @q NVARCHAR(MAX), @s SYSNAME, @o SYSNAME, @kind CHAR(2), @oid INT, @ddl NVARCHAR(MAX), @list NVARCHAR(MAX);
    IF ISNULL(@confirm, N'') <> N'bakdrop'
        THROW 50801, N'нужно подтверждение удаления служебных копий (слово bakdrop) — ничего не удалено', 1;
    -- ★ ревизия 48 (мелочь 1): только латиница / цифры / «_» (хвостовой пробел «Joy1 » сравнение = не видит), затем имя из списка как есть
    IF @db IS NULL OR @db LIKE N'%[^A-Za-z0-9_]%' OR DATALENGTH(@db) <> LEN(@db) * 2 OR @db = N'AsdaAdmin'
       OR NOT EXISTS (SELECT 1 FROM adm.dbbackup_db WHERE name = @db)
        THROW 50802, N'база вне списка панели или это база самой панели — ничего не удалено', 1;
    SELECT @db = name FROM adm.dbbackup_db WHERE name = @db;
    IF ISJSON(@names) <> 1
        THROW 50803, N'список имён копий — JSON-массив строк «схема.имя» — ничего не удалено', 1;
    CREATE TABLE #want (sch SYSNAME COLLATE DATABASE_DEFAULT NOT NULL, name SYSNAME COLLATE DATABASE_DEFAULT NOT NULL, PRIMARY KEY (sch, name));
    INSERT #want (sch, name)
    SELECT DISTINCT ISNULL(PARSENAME(j.value, 2), N'dbo'), PARSENAME(j.value, 1)
    FROM OPENJSON(@names) j WHERE j.type = 1 AND PARSENAME(j.value, 1) IS NOT NULL AND PARSENAME(j.value, 3) IS NULL;
    SELECT @n = COUNT(*) FROM #want;
    IF @n = 0 OR @n > 60 OR @n <> (SELECT COUNT(DISTINCT value) FROM OPENJSON(@names))
        THROW 50803, N'список имён копий — JSON-массив строк «схема.имя» — ничего не удалено', 1;
    SELECT @list = STRING_AGG(CAST(w.sch + N'.' + w.name AS NVARCHAR(MAX)), N', ') FROM #want w
    WHERE NOT EXISTS (SELECT 1 FROM adm.bakdrop_obj k WHERE k.db = @db AND k.sch = w.sch AND k.name = w.name);
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'неизвестный объект (нет в каталоге служебных копий панели) — ничего не удалено: ' + @list, 2048);
        THROW 50804, @msg, 1;
    END
    SELECT @list = STRING_AGG(CAST(w.sch + N'.' + w.name AS NVARCHAR(MAX)), N', ') FROM #want w            -- чей откат — в каталоге (needed_by)
    JOIN adm.bakdrop_obj k ON k.db = @db AND k.sch = w.sch AND k.name = w.name WHERE k.verdict = 'rollback';
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'копия нужна откату, панель её не удаляет — ничего не удалено: ' + @list, 2048);
        THROW 50805, @msg, 1;
    END
    SELECT @list = STRING_AGG(CAST(w.sch + N'.' + w.name AS NVARCHAR(MAX)), N', ') FROM #want w
    JOIN adm.bakdrop_obj k ON k.db = @db AND k.sch = w.sch AND k.name = w.name WHERE k.verdict <> 'drop';
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'происхождение копии не установлено, панель её не удаляет — ничего не удалено: ' + @list, 2048);
        THROW 50806, @msg, 1;
    END
    SELECT @fresh = fresh_hours FROM adm.bakdrop_cfg WHERE id = 1;
    SELECT @bstart = b.started_at, @bfin = b.finished_at, @bfile = b.file_path, @counts = b.counts
    FROM adm.dbbackup b
    WHERE b.id = @backup_id AND b.db = @db AND b.status = 'done' AND b.verified = 1 AND b.backup_set_id IS NOT NULL
      AND b.finished_at >= DATEADD(HOUR, -@fresh, SYSUTCDATETIME()) AND b.verified_at >= DATEADD(HOUR, -@fresh, SYSUTCDATETIME())
      AND EXISTS (SELECT 1 FROM msdb.dbo.backupset s JOIN msdb.dbo.backupmediafamily m ON m.media_set_id = s.media_set_id
                  WHERE s.backup_set_id = b.backup_set_id AND m.physical_device_name COLLATE DATABASE_DEFAULT = b.file_path);
    IF @bfile IS NULL
    BEGIN
        SET @msg = N'нет свежего проверенного бэкапа этой базы (не старше ' + CAST(@fresh AS NVARCHAR(12))
                 + N' ч, RESTORE VERIFYONLY пройден, набор в истории msdb) — ничего не удалено, сначала сделайте бэкап';
        THROW 50807, @msg, 1;
    END

    BEGIN TRANSACTION;
    CREATE TABLE #bak (db SYSNAME COLLATE DATABASE_DEFAULT, sch SYSNAME COLLATE DATABASE_DEFAULT, name SYSNAME COLLATE DATABASE_DEFAULT, oid INT,
                       type CHAR(2) COLLATE DATABASE_DEFAULT, type_desc NVARCHAR(60) COLLATE DATABASE_DEFAULT, created DATETIME2(0), modified DATETIME2(0),
                       rows_n BIGINT, kb BIGINT);
    CREATE TABLE #bakref (db SYSNAME COLLATE DATABASE_DEFAULT, sch SYSNAME COLLATE DATABASE_DEFAULT, name SYSNAME COLLATE DATABASE_DEFAULT,
                          rdb SYSNAME COLLATE DATABASE_DEFAULT, rsch NVARCHAR(128) COLLATE DATABASE_DEFAULT, rname NVARCHAR(400) COLLATE DATABASE_DEFAULT,
                          rtype CHAR(2) COLLATE DATABASE_DEFAULT, how VARCHAR(10) COLLATE DATABASE_DEFAULT);
    CREATE TABLE #bakwarn (db SYSNAME COLLATE DATABASE_DEFAULT, why NVARCHAR(400) COLLATE DATABASE_DEFAULT);
    EXEC adm.BakScan @db;                                             -- повторная проверка прямо перед DROP, внутри той же транзакции
    SELECT @list = STRING_AGG(CAST(db AS NVARCHAR(MAX)), N', ') FROM (SELECT DISTINCT db FROM #bakwarn) w;    -- причины — в списке панели
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'ссылки на копии прочитаны не во всех базах (причины — в списке служебных копий) — ничего не удалено: ' + @list, 2048);
        THROW 50811, @msg, 1;
    END
    SELECT @list = STRING_AGG(CAST(w.sch + N'.' + w.name AS NVARCHAR(MAX)), N', ') FROM #want w JOIN adm.bakdrop_obj k ON k.db = @db AND k.sch = w.sch AND k.name = w.name
    WHERE NOT EXISTS (SELECT 1 FROM #bak b WHERE b.db = @db AND b.sch = w.sch AND b.name = w.name AND b.type = k.kind);
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'объекта нет в базе или он другого вида — ничего не удалено: ' + @list, 2048);
        THROW 50808, @msg, 1;
    END
    SELECT @list = STRING_AGG(CAST(w.sch + N'.' + w.name AS NVARCHAR(MAX)), N', ') FROM #want w JOIN #bak b ON b.db = @db AND b.sch = w.sch AND b.name = w.name
    WHERE b.modified >= @bstart OR b.created >= @bstart;
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'объект создан или изменён после начала бэкапа №' + CAST(@backup_id AS NVARCHAR(12))
                 + N' (в бэкапе его нынешнего вида нет) — ничего не удалено, нужен новый бэкап: ' + @list, 2048);
        THROW 50809, @msg, 1;
    END
    /* ★ ревизия 48 Н-1: строки таблицы. DDL меняет modify_date, а INSERT / UPDATE / DELETE — нет: сверка с числом строк снимка бэкапа
       (adm.dbbackup.counts, служба снимает сразу после бэкапа) и с последней записью в таблицу (sys.dm_db_index_usage_stats, местное время;
       после перезапуска SQL Server её нет — если перезапуск был после начала бэкапа, это «не прочитано», отказ) */
    SELECT @sqlstart = DATEADD(MINUTE, @tz, sqlserver_start_time) FROM sys.dm_os_sys_info;
    SET @late = NULL;
    DECLARE u CURSOR LOCAL FAST_FORWARD FOR
        SELECT b.sch, b.name, b.oid FROM #want w JOIN #bak b ON b.db = @db AND b.sch = w.sch AND b.name = w.name WHERE b.type = 'U';
    OPEN u; FETCH u INTO @s, @o, @oid;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SELECT @upd = DATEADD(MINUTE, @tz, MAX(last_user_update)) FROM sys.dm_db_index_usage_stats WHERE database_id = DB_ID(@db) AND object_id = @oid;
        IF @counts IS NULL
           OR ISJSON(@counts) <> 1
           OR NOT EXISTS (SELECT 1 FROM OPENJSON(@counts) j JOIN #bak b ON b.db = @db AND b.sch = @s AND b.name = @o
                          WHERE j.[key] = @s + N'.' + @o AND TRY_CAST(j.[value] AS BIGINT) = ISNULL(b.rows_n, 0))
           OR @upd >= @bstart
           OR (@upd IS NULL AND @sqlstart >= @bstart)
            SET @late = ISNULL(@late + N', ', N'') + @s + N'.' + @o;
        FETCH u INTO @s, @o, @oid;
    END
    CLOSE u; DEALLOCATE u;
    IF @late IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'строки копии изменены после бэкапа №' + CAST(@backup_id AS NVARCHAR(12))
                 + N' или это не прочитать (число строк снимка бэкапа, последняя запись, перезапуск SQL Server) — ничего не удалено, нужен новый бэкап: '
                 + @late, 2048);
        THROW 50812, @msg, 1;
    END
    ;WITH rf AS (SELECT DISTINCT r.sch, r.name, r.rdb, r.rsch, r.rname, r.how FROM #bakref r JOIN #want w ON r.db = @db AND r.sch = w.sch AND r.name = w.name
                 WHERE NOT (r.rdb = @db AND r.how IN ('expr', 'text') AND EXISTS (SELECT 1 FROM #want w2 WHERE w2.sch = r.rsch AND w2.name = r.rname)))
    SELECT @list = STRING_AGG(CAST(sch + N'.' + name + N' ← ' + rdb + N'.' + rsch + N'.' + rname + N' (' + how + N')' AS NVARCHAR(MAX)), N', ') FROM rf;
    IF @list IS NOT NULL
    BEGIN
        SET @msg = LEFT(N'на копию ссылаются другие объекты — ничего не удалено: ' + @list, 2048);
        THROW 50810, @msg, 1;
    END
    SET @x = QUOTENAME(@db);
    DECLARE d CURSOR LOCAL FAST_FORWARD FOR
        SELECT b.sch, b.name, b.type, b.oid FROM #want w JOIN #bak b ON b.db = @db AND b.sch = w.sch AND b.name = w.name ORDER BY b.type, b.name;
    OPEN d; FETCH d INTO @s, @o, @kind, @oid;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @ddl = NULL;
        IF @kind = 'U'
        BEGIN
            SET @q = N'SELECT @ddl = N''CREATE TABLE '' + QUOTENAME(@s) + N''.'' + QUOTENAME(@o) + N'' ('' + STRING_AGG(CAST(QUOTENAME(c.name) + N'' ''
       + CASE WHEN t.is_user_defined = 1 THEN QUOTENAME(t.name) ELSE t.name END
       + CASE WHEN t.name IN (N''varchar'', N''char'', N''varbinary'', N''binary'') THEN N''('' + CASE WHEN c.max_length = -1 THEN N''MAX'' ELSE CAST(c.max_length AS NVARCHAR(10)) END + N'')''
              WHEN t.name IN (N''nvarchar'', N''nchar'') THEN N''('' + CASE WHEN c.max_length = -1 THEN N''MAX'' ELSE CAST(c.max_length / 2 AS NVARCHAR(10)) END + N'')''
              WHEN t.name IN (N''decimal'', N''numeric'') THEN N''('' + CAST(c.precision AS NVARCHAR(5)) + N'','' + CAST(c.scale AS NVARCHAR(5)) + N'')''
              WHEN t.name IN (N''datetime2'', N''time'', N''datetimeoffset'') THEN N''('' + CAST(c.scale AS NVARCHAR(5)) + N'')'' ELSE N'''' END
       + CASE WHEN c.collation_name IS NOT NULL THEN N'' COLLATE '' + c.collation_name ELSE N'''' END
       + CASE WHEN c.is_identity = 1 THEN N'' IDENTITY'' ELSE N'''' END
       + CASE WHEN c.is_nullable = 1 THEN N'' NULL'' ELSE N'' NOT NULL'' END
       + ISNULL(N'' DEFAULT '' + dc.definition, N'''') AS NVARCHAR(MAX)), N'', '') WITHIN GROUP (ORDER BY c.column_id) + N'')''
FROM ' + @x + N'.sys.columns c JOIN ' + @x + N'.sys.types t ON t.user_type_id = c.user_type_id
LEFT JOIN ' + @x + N'.sys.default_constraints dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
WHERE c.object_id = @oid;';   -- снимок: столбцы (тип, сортировка, IDENTITY, NULL, DEFAULT); ключей, индексов и CHECK в нём нет
            EXEC sys.sp_executesql @q, N'@ddl NVARCHAR(MAX) OUTPUT, @s SYSNAME, @o SYSNAME, @oid INT', @ddl OUTPUT, @s, @o, @oid;
        END
        ELSE
        BEGIN
            SET @q = N'SELECT @ddl = m.definition FROM ' + @x + N'.sys.sql_modules m WHERE m.object_id = @oid;';
            EXEC sys.sp_executesql @q, N'@ddl NVARCHAR(MAX) OUTPUT, @oid INT', @ddl OUTPUT, @oid;
        END
        INSERT adm.bakdrop_log (batch, db, sch, name, kind, ddl, rows_n, kb, created_utc, modified_utc, origin, backup_id, backup_file, backup_finished, by_login)
        SELECT @batch, @db, b.sch, b.name, b.type, @ddl, b.rows_n, b.kb, b.created, b.modified, k.origin, @backup_id, @bfile, @bfin, LEFT(@by, 64)
        FROM #bak b JOIN adm.bakdrop_obj k ON k.db = b.db AND k.sch = b.sch AND k.name = b.name
        WHERE b.db = @db AND b.sch = @s AND b.name = @o;
        /* DROP — от имени пользователя без входа adm_bakdrop_x этой базы (CONTROL только на копии «можно убрать»): в токене подписанной
           процедуры остаётся и вызывающий asda_admin, а его DENY ALTER на уровне базы запрещает DROP даже при CONTROL у логина подписи
           (3701, проверено на LocalDB); смена контекста — только на эту инструкцию, внутри той же транзакции */
        SET @q = N'EXEC ' + @x + N'.sys.sp_executesql @t';
        DECLARE @t NVARCHAR(600) = N'EXECUTE AS USER = N''adm_bakdrop_x''; '
              + CASE WHEN @kind = 'U' THEN N'DROP TABLE ' ELSE N'DROP PROCEDURE ' END + QUOTENAME(@s) + N'.' + QUOTENAME(@o) + N'; REVERT;';
        EXEC sys.sp_executesql @q, N'@t NVARCHAR(600)', @t;
        FETCH d INTO @s, @o, @kind, @oid;
    END
    CLOSE d; DEALLOCATE d;
    COMMIT TRANSACTION;
    SELECT id, batch, db, sch, name, RTRIM(kind) AS kind, rows_n, kb, LEN(ddl) AS ddl_len, backup_id, backup_file, backup_finished, by_login, dropped_at
    FROM adm.bakdrop_log WHERE batch = @batch ORDER BY id;
END
GO

/* ---------- подпись: сертификат в AsdaAdmin (закрытый ключ — только на время подписи), открытая часть — в master, логин из неё ---------- */
DECLARE @pw NVARCHAR(200) = CONVERT(NVARCHAR(36), NEWID()) + N'Aa1!' + CONVERT(NVARCHAR(36), NEWID()) + CONVERT(NVARCHAR(36), NEWID());
DECLARE @q NVARCHAR(MAX);
SET @q = N'CREATE CERTIFICATE adm_bakdrop_cert ENCRYPTION BY PASSWORD = ' + QUOTENAME(@pw, '''')
       + N' WITH SUBJECT = N''Astory admin center: service copies cleanup (A5.8)'', EXPIRY_DATE = ''20991231'';';   -- ГГГГММДД (урок А5.7: ошибка 190 у dmy)
EXEC (@q);
SET @q = N'ADD SIGNATURE TO adm.BakScan BY CERTIFICATE adm_bakdrop_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';'
       + N'ADD SIGNATURE TO adm.BakDrop BY CERTIFICATE adm_bakdrop_cert WITH PASSWORD = ' + QUOTENAME(@pw, '''') + N';';
EXEC (@q);
ALTER CERTIFICATE adm_bakdrop_cert REMOVE PRIVATE KEY;
SET @pw = NULL;
DECLARE @pub VARBINARY(MAX) = CERTENCODED(CERT_ID(N'adm_bakdrop_cert'));
SET @q = N'CREATE CERTIFICATE adm_bakdrop_cert FROM BINARY = ' + CONVERT(NVARCHAR(MAX), @pub, 1) + N';';
EXEC master.sys.sp_executesql @q;
EXEC master.sys.sp_executesql N'CREATE LOGIN adm_bakdrop_signer FROM CERTIFICATE adm_bakdrop_cert;
GRANT VIEW ANY DEFINITION TO adm_bakdrop_signer; GRANT VIEW SERVER STATE TO adm_bakdrop_signer;';
/* ★ ревизия 48: VIEW ANY DEFINITION — текст серверных триггеров (sys.server_sql_modules); VIEW SERVER STATE — последняя запись в таблицу
   (sys.dm_db_index_usage_stats) и время запуска SQL Server (Н-1). Оба — только чтение метаданных; входа у логина нет. */
GO
/* пользователь логина подписи: в каждой базе списка (кроме AsdaAdmin) — VIEW DEFINITION и CONTROL только на копии каталога с verdict = 'drop';
   в AsdaAdmin — VIEW DEFINITION (ссылки из процедур панели); в msdb — SELECT истории бэкапов и шагов заданий */
DECLARE @d SYSNAME, @q NVARCHAR(MAX), @g NVARCHAR(MAX);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT l.name FROM adm.dbbackup_db l JOIN sys.databases d ON d.name = l.name COLLATE DATABASE_DEFAULT WHERE d.state_desc = 'ONLINE';
OPEN c; FETCH c INTO @d;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @g = N'';
    SELECT @g = @g + N'IF OBJECT_ID(N''' + REPLACE(QUOTENAME(k.sch) + N'.' + QUOTENAME(k.name), N'''', N'''''') + N''', ''' + RTRIM(k.kind)
              + N''') IS NOT NULL GRANT CONTROL ON OBJECT::' + QUOTENAME(k.sch) + N'.' + QUOTENAME(k.name) + N' TO adm_bakdrop_x; '
    FROM adm.bakdrop_obj k WHERE k.db = @d AND k.verdict = 'drop' AND @d <> N'AsdaAdmin';
    SET @q = N'EXEC ' + QUOTENAME(@d) + N'.sys.sp_executesql @s';
    -- sys.sql_expression_dependencies по умолчанию читает только db_owner: отдельный SELECT на это представление (не роль).
    -- adm_bakdrop_x (без входа) — исполнитель DROP: только CONTROL на копии «можно убрать»; олицетворять его может только логин подписи
    SET @g = N'CREATE USER adm_bakdrop_u FOR LOGIN adm_bakdrop_signer; GRANT VIEW DEFINITION TO adm_bakdrop_u; '
           + N'GRANT SELECT ON sys.sql_expression_dependencies TO adm_bakdrop_u; '
           + CASE WHEN @d <> N'AsdaAdmin' THEN N'CREATE USER adm_bakdrop_x WITHOUT LOGIN; GRANT IMPERSONATE ON USER::adm_bakdrop_x TO adm_bakdrop_u; '
                  ELSE N'' END + @g;
    EXEC sys.sp_executesql @q, N'@s NVARCHAR(MAX)', @g;
    FETCH c INTO @d;
END
CLOSE c; DEALLOCATE c;
EXEC msdb.sys.sp_executesql N'CREATE USER adm_bakdrop_u FOR LOGIN adm_bakdrop_signer; GRANT SELECT ON dbo.backupset TO adm_bakdrop_u;
GRANT SELECT ON dbo.backupmediafamily TO adm_bakdrop_u; GRANT SELECT ON dbo.sysjobs TO adm_bakdrop_u; GRANT SELECT ON dbo.sysjobsteps TO adm_bakdrop_u;
GRANT VIEW DEFINITION TO adm_bakdrop_u; GRANT SELECT ON sys.sql_expression_dependencies TO adm_bakdrop_u;';
/* ★ ревизия 48 (мелочь 8): модули master тоже смотрятся на ссылки — пользователь подписи и там (только чтение метаданных) */
EXEC master.sys.sp_executesql N'CREATE USER adm_bakdrop_u FOR LOGIN adm_bakdrop_signer; GRANT VIEW DEFINITION TO adm_bakdrop_u;
GRANT SELECT ON sys.sql_expression_dependencies TO adm_bakdrop_u;';
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.bakdrop_obj TO [asda_admin];
    GRANT SELECT ON adm.bakdrop_cfg TO [asda_admin];
    GRANT SELECT ON adm.bakdrop_log TO [asda_admin];
    DENY INSERT, UPDATE, DELETE ON adm.bakdrop_obj TO [asda_admin];
    DENY INSERT, UPDATE, DELETE ON adm.bakdrop_cfg TO [asda_admin];
    DENY INSERT, UPDATE, DELETE ON adm.bakdrop_log TO [asda_admin];
    GRANT EXECUTE ON adm.BakState TO [asda_admin];
    GRANT EXECUTE ON adm.BakDrop TO [asda_admin];
END
GO
PRINT 'adminc_17_bakdrop: OK';
