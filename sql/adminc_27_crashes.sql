-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_27_crashes.sql — сводка сбоев клиента для раздела «Сбои клиента» (шаг А7.2, 23.11.2026; domains/crashes.py, отчёт
   Reports/admin_center/impl_a7_releases_20261123.md §А7.2; решения владельца А7 №1 — сбои расшифровываются только на ПК, ключ LogSeal на
   сервер не кладётся, в панель уходит только сводка; №8 — .acrash хранятся без срока).
   Запуск в контексте AsdaAdmin (sqlcmd -d AsdaAdmin -x -I) ПОСЛЕ adminc_03_grants. Тот же файл самотест выполняет на LocalDB (там пользователя
   asda_admin нет — выдача прав пропускается). Повторный запуск безопасен.

   ОТКУДА ДАННЫЕ. Пакеты падений .acrash лежат в LogDrop на сервере зашифрованными (ключа на сервере нет). Консоль ПК (asda_admin.py crashes sync
   или задание ПК crash.sync) забирает их по scp, расшифровывает на ПК и присылает сюда ТОЛЬКО сводку, логином asda_admin по VPN — тем же путём,
   каким консоль ПК пишет adm.ReleasePcStatus (А7.1). В сводке нет памяти процесса (minidump), хвоста журнала (session_tail.txt), путей, IP,
   имён пользователей Windows, id установки; логин игрока — только заявленный клиентом и найденный приёмником (account_status ok).

   ТАБЛИЦЫ
     adm.ClientCrash      — один пакет падения (ключ — SHA-256 пакета из .json приёмника; повторная выгрузка того же пакета — та же строка):
                            серверное имя файла, логин (заявлен клиентом, не доказан), время падения / начала сессии / приёма, итог разбора
                            (ok — сводка прочитана; unread — не расшифрован; nosummary — нет сводки; notfetched — не забран с сервера), код исключения,
                            адрес, текст ошибки (до 300 знаков, пути вырезаны), кадры нашего exe (модуль+RVA), подпись места (sig), версия
                            «по времени» с основанием и пометкой, символы (сейчас всегда «нет»: PDB хранится только у последней сборки — шаг А7.3).
     adm.ClientCrashSig   — группа «место падения»: подпись = код исключения + первые 3 кадра AsdaReborn-Win64-Shipping.exe (или первые кадры
                            стека, если кадров exe нет); первое и последнее падение, число, учёток. Пересчитывается процедурой из adm.ClientCrash
                            при каждой отправке ПК (adm.ClientCrashSyncAdd).
     adm.ClientCrashSync  — отправки ПК: когда собрано, хост, итог (пакетов на сервере, новых, не прочитанных, повторов); одинаковая сводка второй
                            раз не пишется — только отметка «ПК присылал» (seen_utc, seen_count); история — 200 последних отправок.
   ПРАВА asda_admin: SELECT трёх таблиц, EXECUTE adm.ClientCrashPut и adm.ClientCrashSyncAdd; INSERT / UPDATE / DELETE напрямую — DENY (запись
     только процедурами, цепочка владения dbo). Удалять сбои некому: .acrash хранятся без срока (решение №8).
   ★ QUOTED_IDENTIFIER / ANSI_NULLS ON — отдельным пакетом до CREATE (у sqlcmd по умолчанию QUOTED_IDENTIFIER OFF, урок adminc_14). Совместимость
   с уровнем 100: без TRY_CONVERT, IIF, FORMAT, THROW, STRING_SPLIT, ISJSON. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO
SET NOCOUNT ON;
IF OBJECT_ID(N'adm.ClientCrash') IS NULL
CREATE TABLE adm.ClientCrash (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_ClientCrash PRIMARY KEY,
    pkg_sha256      CHAR(64)       NOT NULL,
    file_name       NVARCHAR(96)   NOT NULL,
    login           NVARCHAR(32)   NULL,
    pkg_kind        TINYINT        NOT NULL,
    crash_utc       DATETIME2(0)   NULL,
    session_utc     DATETIME2(0)   NULL,
    received_utc    DATETIME2(0)   NULL,
    status          VARCHAR(12)    NOT NULL,
    status_note     NVARCHAR(200)  NOT NULL CONSTRAINT DF_adm_ClientCrash_note DEFAULT N'',
    exc_code        VARCHAR(24)    NULL,
    exc_addr        NVARCHAR(96)   NULL,
    access          NVARCHAR(96)   NULL,
    error_text      NVARCHAR(300)  NULL,
    frames          NVARCHAR(1000) NULL,
    exe_frames      INT            NOT NULL CONSTRAINT DF_adm_ClientCrash_exe DEFAULT 0,
    sig             CHAR(12)       NULL,
    version         NVARCHAR(40)   NULL,
    version_basis   VARCHAR(12)    NOT NULL CONSTRAINT DF_adm_ClientCrash_vb DEFAULT 'none',
    version_note    NVARCHAR(200)  NOT NULL CONSTRAINT DF_adm_ClientCrash_vn DEFAULT N'',
    symbols         VARCHAR(8)     NOT NULL CONSTRAINT DF_adm_ClientCrash_sym DEFAULT 'none',
    row_md5         CHAR(32)       NOT NULL,
    pushed_utc      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ClientCrash_pushed DEFAULT SYSUTCDATETIME(),
    updated_utc     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ClientCrash_upd DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_adm_ClientCrash_sha UNIQUE (pkg_sha256),
    CONSTRAINT CK_adm_ClientCrash_sha CHECK (pkg_sha256 NOT LIKE '%[^0-9a-f]%' AND LEN(pkg_sha256) = 64),
    CONSTRAINT CK_adm_ClientCrash_md5 CHECK (row_md5 NOT LIKE '%[^0-9a-f]%' AND LEN(row_md5) = 32),
    CONSTRAINT CK_adm_ClientCrash_status CHECK (status IN ('ok', 'unread', 'nosummary', 'notfetched')),
    CONSTRAINT CK_adm_ClientCrash_vb CHECK (version_basis IN ('session', 'crash', 'sealed', 'received', 'none')),
    CONSTRAINT CK_adm_ClientCrash_sym CHECK (symbols IN ('none', 'pdb'))
);
GO
IF OBJECT_ID(N'adm.ClientCrash') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_adm_ClientCrash_sig')
    CREATE INDEX IX_adm_ClientCrash_sig ON adm.ClientCrash (sig, crash_utc);
GO
IF OBJECT_ID(N'adm.ClientCrashSig') IS NULL
CREATE TABLE adm.ClientCrashSig (
    sig             CHAR(12)       NOT NULL CONSTRAINT PK_adm_ClientCrashSig PRIMARY KEY,
    exc_code        VARCHAR(24)    NULL,
    frames          NVARCHAR(1000) NULL,
    first_utc       DATETIME2(0)   NULL,
    last_utc        DATETIME2(0)   NULL,
    n               INT            NOT NULL,
    accounts        INT            NOT NULL,
    updated_utc     DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ClientCrashSig_upd DEFAULT SYSUTCDATETIME()
);
GO
IF OBJECT_ID(N'adm.ClientCrashSync') IS NULL
CREATE TABLE adm.ClientCrashSync (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_adm_ClientCrashSync PRIMARY KEY,
    payload         NVARCHAR(4000) NOT NULL,
    payload_md5     CHAR(32)       NOT NULL,
    host            NVARCHAR(64)   NOT NULL,
    pushed_by       NVARCHAR(32)   NOT NULL,
    collected_utc   DATETIME2(0)   NOT NULL,
    pushed_utc      DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ClientCrashSync_pushed DEFAULT SYSUTCDATETIME(),
    seen_utc        DATETIME2(0)   NOT NULL CONSTRAINT DF_adm_ClientCrashSync_seen DEFAULT SYSUTCDATETIME(),
    seen_count      INT            NOT NULL CONSTRAINT DF_adm_ClientCrashSync_count DEFAULT 1,
    CONSTRAINT CK_adm_ClientCrashSync_md5 CHECK (payload_md5 NOT LIKE '%[^0-9a-f]%' AND LEN(payload_md5) = 32)
);
GO
/* Один пакет: нет строки — новая (@Result 1); есть и тот же отпечаток разбора — ничего (0); есть, отпечаток другой (пакет дочитан после
   import-backup ключа, releases.log дополнился) — строка переписывается (2). Ключ строки — SHA-256 пакета: повторная выгрузка того же
   пакета второй строки не даёт. */
CREATE OR ALTER PROCEDURE adm.ClientCrashPut
    @Sha CHAR(64), @File NVARCHAR(96), @Login NVARCHAR(32), @Kind TINYINT,
    @CrashUtc DATETIME2(0), @SessionUtc DATETIME2(0), @ReceivedUtc DATETIME2(0),
    @Status VARCHAR(12), @StatusNote NVARCHAR(200),
    @ExcCode VARCHAR(24), @ExcAddr NVARCHAR(96), @Access NVARCHAR(96), @ErrorText NVARCHAR(300),
    @Frames NVARCHAR(1000), @ExeFrames INT, @Sig CHAR(12),
    @Version NVARCHAR(40), @VersionBasis VARCHAR(12), @VersionNote NVARCHAR(200), @Symbols VARCHAR(8),
    @RowMd5 CHAR(32),
    @Result INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Result = 0;
    DECLARE @old CHAR(32), @oldStatus VARCHAR(12);
    SELECT @old = row_md5, @oldStatus = status FROM adm.ClientCrash WITH (UPDLOCK, HOLDLOCK) WHERE pkg_sha256 = @Sha;
    /* Прочитанная строка не ухудшается: ПК без ключа (другая учётка Windows, S4U без DPAPI) или без копии пакета пришлёт «не прочитан» /
       «не забран» — прежний разбор остаётся. */
    IF @oldStatus = 'ok' AND @Status <> 'ok'
        RETURN;
    IF @old IS NULL
    BEGIN
        INSERT adm.ClientCrash (pkg_sha256, file_name, login, pkg_kind, crash_utc, session_utc, received_utc, status, status_note, exc_code,
                                exc_addr, access, error_text, frames, exe_frames, sig, version, version_basis, version_note, symbols, row_md5)
        VALUES (@Sha, @File, @Login, @Kind, @CrashUtc, @SessionUtc, @ReceivedUtc, @Status, ISNULL(@StatusNote, N''), @ExcCode,
                @ExcAddr, @Access, @ErrorText, @Frames, ISNULL(@ExeFrames, 0), @Sig, @Version, ISNULL(@VersionBasis, 'none'),
                ISNULL(@VersionNote, N''), ISNULL(@Symbols, 'none'), @RowMd5);
        SET @Result = 1;
    END
    ELSE IF @old <> @RowMd5
    BEGIN
        UPDATE adm.ClientCrash SET file_name = @File, login = @Login, pkg_kind = @Kind, crash_utc = @CrashUtc, session_utc = @SessionUtc,
               received_utc = @ReceivedUtc, status = @Status, status_note = ISNULL(@StatusNote, N''), exc_code = @ExcCode, exc_addr = @ExcAddr,
               access = @Access, error_text = @ErrorText, frames = @Frames, exe_frames = ISNULL(@ExeFrames, 0), sig = @Sig, version = @Version,
               version_basis = ISNULL(@VersionBasis, 'none'), version_note = ISNULL(@VersionNote, N''), symbols = ISNULL(@Symbols, 'none'),
               row_md5 = @RowMd5, updated_utc = SYSUTCDATETIME()
        WHERE pkg_sha256 = @Sha;
        SET @Result = 2;
    END
END
GO
/* Итог отправки ПК + пересчёт групп. Та же сводка (md5) — только отметка у последней строки; другая — новая строка, история — 200 последних.
   Группы пересчитываются целиком из adm.ClientCrash (строк — десятки, пересчёт дешевле, чем учёт приращений). */
CREATE OR ALTER PROCEDURE adm.ClientCrashSyncAdd
    @Payload NVARCHAR(4000), @PayloadMd5 CHAR(32), @Host NVARCHAR(64), @By NVARCHAR(32), @CollectedUtc DATETIME2(0),
    @Id INT OUTPUT, @New INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @New = 0;
    SELECT TOP 1 @Id = id FROM adm.ClientCrashSync WHERE payload_md5 = @PayloadMd5 AND id = (SELECT MAX(id) FROM adm.ClientCrashSync);
    IF @Id IS NOT NULL
        UPDATE adm.ClientCrashSync SET seen_utc = SYSUTCDATETIME(), seen_count = seen_count + 1 WHERE id = @Id;
    ELSE
    BEGIN
        INSERT adm.ClientCrashSync (payload, payload_md5, host, pushed_by, collected_utc) VALUES (@Payload, @PayloadMd5, @Host, @By, @CollectedUtc);
        SET @Id = SCOPE_IDENTITY();
        SET @New = 1;
        DELETE FROM adm.ClientCrashSync WHERE id NOT IN (SELECT TOP (200) id FROM adm.ClientCrashSync ORDER BY id DESC);
    END
    /* ★ ревизия 75 М-2: строка «не забран» (ключ — SHA-256 от имени файла) уходит, когда тот же пакет пришёл настоящей строкой (настоящий
       SHA-256, тот же file_name). Удаление только здесь, цепочкой владения dbo — у asda_admin прямого DELETE нет. */
    DELETE n FROM adm.ClientCrash n
    WHERE n.status = 'notfetched' AND EXISTS (SELECT 1 FROM adm.ClientCrash o WHERE o.file_name = n.file_name AND o.status <> 'notfetched');
    DELETE FROM adm.ClientCrashSig WHERE sig NOT IN (SELECT sig FROM adm.ClientCrash WHERE sig IS NOT NULL);
    UPDATE s SET exc_code = g.exc_code, frames = g.frames, first_utc = g.first_utc, last_utc = g.last_utc, n = g.n, accounts = g.accounts,
           updated_utc = SYSUTCDATETIME()
    FROM adm.ClientCrashSig s
    JOIN (SELECT sig, MAX(exc_code) AS exc_code, MAX(frames) AS frames, MIN(ISNULL(crash_utc, received_utc)) AS first_utc,
                 MAX(ISNULL(crash_utc, received_utc)) AS last_utc, COUNT(*) AS n, COUNT(DISTINCT login) AS accounts
          FROM adm.ClientCrash WHERE sig IS NOT NULL GROUP BY sig) g ON g.sig = s.sig
    WHERE s.exc_code IS NULL OR s.n <> g.n OR s.accounts <> g.accounts OR ISNULL(s.first_utc, '19000101') <> ISNULL(g.first_utc, '19000101')
          OR ISNULL(s.last_utc, '19000101') <> ISNULL(g.last_utc, '19000101') OR ISNULL(s.frames, N'') <> ISNULL(g.frames, N'');
    INSERT adm.ClientCrashSig (sig, exc_code, frames, first_utc, last_utc, n, accounts)
    SELECT sig, MAX(exc_code), MAX(frames), MIN(ISNULL(crash_utc, received_utc)), MAX(ISNULL(crash_utc, received_utc)), COUNT(*), COUNT(DISTINCT login)
    FROM adm.ClientCrash c WHERE sig IS NOT NULL AND NOT EXISTS (SELECT 1 FROM adm.ClientCrashSig s WHERE s.sig = c.sig) GROUP BY sig;
END
GO
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin')
BEGIN
    GRANT SELECT ON adm.ClientCrash     TO [asda_admin];
    GRANT SELECT ON adm.ClientCrashSig  TO [asda_admin];
    GRANT SELECT ON adm.ClientCrashSync TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.ClientCrash     TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.ClientCrashSig  TO [asda_admin];
    DENY  INSERT, UPDATE, DELETE ON adm.ClientCrashSync TO [asda_admin];
    GRANT EXECUTE ON adm.ClientCrashPut     TO [asda_admin];
    GRANT EXECUTE ON adm.ClientCrashSyncAdd TO [asda_admin];
END
GO
PRINT 'adminc_27_crashes: OK';
