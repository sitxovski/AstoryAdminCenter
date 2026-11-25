-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_24_chat.sql — админ-центр, шаг А6.12 «Журнал чата и заглушки» (часть «панель», 22.11.2026): права логинов панели на схему joylog1.chat
   журнала чата P129 (AsdaPatch v86; AstoryServer/Docs/GameServer/chat-log-p129.md, схема — AstoryServer/Docs/SQL/chat_01_migrate.sql).
   Решение владельца №5 (ADMIN_TOOL_PLAN.md §6 п.5): журнал + заглушка, 90 дней. Код панели — domains/chatlog.py.

   ЧТО ВЫДАЁТСЯ
     asda_admin (служба панели, только чтение): SELECT chat.message, chat.mute, chat.v_recent, chat.v_mute_active (у логина в joylog1 и так
                db_datareader — выдача явная, чтобы проверка adminc_10 не зависела от роли); запись и процедуры chat — DENY.
     asda_ops   (логин правок): EXECUTE chat.UP_ChatMuteSet и chat.UP_ChatMuteLift — поставить и снять заглушку (запись в chat.mute делает
                процедура: владелец dbo, цепочка владения); SELECT chat.mute — сверка «заглушки цели не изменились с предпросмотра» внутри
                транзакции записи (UPDLOCK). Прямая запись chat.mute, журнал chat.message, кэш DLL UP_ChatMuteActive и очистка
                UP_ChatJournalPurge — DENY.
   СХЕМЫ НЕТ (P129 ещё не выложен) — ПРОПУСК с отметкой «adminc_24: пропущено …» (код 0: выкладка панели не останавливается); права
   выдаёт следующая выкладка панели (deploy/deploy_admin_center.py) или выкладчик P129 сразу после chat_01_migrate.sql
   (AstoryServer/Patches/AsdaPatch/tools/deploy_p129.py, шаг panel_grants — исполняет копию этого файла из @@ASTORY_SERVER_ROOT@@\AdminCenter\sql).
   Схема неполная (есть, но нет таблицы, процедуры или представления) — отказ RAISERROR без выдачи прав (код ≠ 0).
   Выдачи — внутри EXEC(): без схемы их текст не компилируется. Повторный запуск безопасен.
   Запуск: sqlcmd -S lpc:.\SQLEXPRESS -E -b -x -I -f 65001 -i adminc_24_chat.sql (ПОСЛЕ adminc_03_grants, adminc_04_ops и adminc_21_san:
   adminc_21 снимает запрет EXECUTE на базу joylog1 у asda_ops). Своих $(…) переменных в файле нет (-x — как у chat_*.sql).
   Проверка — adminc_10_verify.sql (под asda_admin) и adminc_11_verify_ops.sql (под asda_ops): без схемы — строка-отметка и ожидания
   «как без схемы». Откат — adminc_99_rollback.sql (снимает выдачи, если схема есть; при откате самого P129 chat_99_rollback.sql удаляет
   схему вместе с выдачами).
*/
SET NOCOUNT ON;
GO
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
USE [joylog1];
GO
IF SCHEMA_ID(N'chat') IS NULL
    PRINT N'adminc_24: пропущено — в joylog1 нет схемы chat (P129 не установлен); права выдаст следующая выкладка панели или deploy_p129.py после chat_01_migrate.sql';
ELSE IF OBJECT_ID(N'chat.message', N'U') IS NULL OR OBJECT_ID(N'chat.mute', N'U') IS NULL
     OR OBJECT_ID(N'chat.UP_ChatMuteSet', N'P') IS NULL OR OBJECT_ID(N'chat.UP_ChatMuteLift', N'P') IS NULL
     OR OBJECT_ID(N'chat.UP_ChatMuteActive', N'P') IS NULL OR OBJECT_ID(N'chat.UP_ChatJournalPurge', N'P') IS NULL
     OR OBJECT_ID(N'chat.v_recent', N'V') IS NULL OR OBJECT_ID(N'chat.v_mute_active', N'V') IS NULL
    RAISERROR(N'adminc_24: схема chat неполная (нужны chat.message, chat.mute, 4 процедуры, 2 представления — chat_01_migrate.sql) - права не выданы', 16, 1);
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin') EXEC(N'CREATE USER [asda_admin] FOR LOGIN [asda_admin]');
    IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') EXEC(N'CREATE USER [asda_ops] FOR LOGIN [asda_ops]');
    /* служба панели: чтение журнала и заглушек */
    EXEC(N'GRANT SELECT ON chat.message TO [asda_admin];
GRANT SELECT ON chat.mute TO [asda_admin];
GRANT SELECT ON chat.v_recent TO [asda_admin];
GRANT SELECT ON chat.v_mute_active TO [asda_admin];
DENY INSERT, UPDATE, DELETE ON chat.message TO [asda_admin];
DENY INSERT, UPDATE, DELETE ON chat.mute TO [asda_admin];
DENY EXECUTE ON chat.UP_ChatMuteSet TO [asda_admin];
DENY EXECUTE ON chat.UP_ChatMuteLift TO [asda_admin];
DENY EXECUTE ON chat.UP_ChatMuteActive TO [asda_admin];
DENY EXECUTE ON chat.UP_ChatJournalPurge TO [asda_admin];');
    /* логин правок: поставить / снять заглушку только процедурами; чтение заглушек — для сверки в транзакции */
    EXEC(N'GRANT EXECUTE ON chat.UP_ChatMuteSet TO [asda_ops];
GRANT EXECUTE ON chat.UP_ChatMuteLift TO [asda_ops];
GRANT SELECT ON chat.mute TO [asda_ops];
DENY INSERT, UPDATE, DELETE ON chat.mute TO [asda_ops];
DENY SELECT, INSERT, UPDATE, DELETE ON chat.message TO [asda_ops];
DENY EXECUTE ON chat.UP_ChatMuteActive TO [asda_ops];
DENY EXECUTE ON chat.UP_ChatJournalPurge TO [asda_ops];');
    PRINT N'adminc_24: OK — asda_admin SELECT chat.* (4), asda_ops EXECUTE chat.UP_ChatMuteSet / UP_ChatMuteLift и SELECT chat.mute';
END
GO
