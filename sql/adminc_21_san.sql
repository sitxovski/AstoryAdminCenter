-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_21_san.sql — админ-центр, шаг А6.7 «Дела античита»: права логина операций asda_ops на журнал дел joylog1.san.*. 22.11.2026.

   ЗАЧЕМ. Решение владельца 22.11 (ADMIN_TOOL_PLAN.md §6 п.5, №1–3): дела AC-NNNN ведутся в панели (domains/cases.py исполняет код
   AstoryServer/Tools/Anticheat/ac_case.py), а пишет исходник ТОЛЬКО в схему san (assert_san_write). До этого шага у asda_ops в joylog1 была запись
   ровно пяти стоковых журналов (adminc_04_ops.sql) и запрет EXECUTE на всю базу.

   ЧТО ВЫДАЁТСЯ (ровно то, что пишет ac_case.py — сверено по тексту: db.w / set_status / log / attach_* / register_generated /
   apply_block / mark_executed / cmd_* ; самотест tests/selftest_cases_a6.py сверяет список с исходником):
     SELECT  san.cases, san.case_log, san.case_event, san.evidence, san.case_block (чтение дела внутри транзакции записи, UPDLOCK);
     INSERT  san.case_log (log), san.case_event (attach_events), san.evidence (attach_file / register_generated),
             san.case_block (apply_block);
     UPDATE  san.cases — только столбцы решения / исполнения / апелляции / закрытия / папки (status, case_id, учётка, логин, «открыто» —
             НЕТ: статус меняет только san.UP_SAN_SetStatus); san.case_block — только столбцы снятия (lifted_*, lift_*, in_history);
     EXECUTE san.UP_SAN_CaseOpen, san.UP_SAN_SetStatus (процедуры и таблицы — одного владельца dbo, запись внутри — цепочкой владения).
   DELETE — нигде (материалы дела не удаляются; INSTEAD OF триггеры san_01 — второй рубеж). INSERT san.cases — нет (только процедурой).
   Запрет EXECUTE на БАЗУ joylog1 перекрыл бы выдачу на процедуру — он снимается (REVOKE), вместо него EXECUTE запрещён на схемы dbo и ac
   (там процедуры сервера и UP_AC_JournalPurge); исполнять в joylog1 можно ровно две процедуры san (проверка adminc_11).
   Запуск — deploy/deploy_admin_center.py ПОСЛЕ adminc_04_ops.sql (sqlcmd -S lpc:.\SQLEXPRESS -E). Проверка — adminc_11_verify_ops.sql
   под asda_ops (и adminc_10 под asda_admin: записи в san у него нет). Откат — adminc_99_rollback.sql (выдачи ниже; пользователь asda_ops
   в joylog1 уходит там же). Схема san — san_01_migrate.sql (AstoryServer/Docs/SQL); её нет — отказ без выдачи прав.
*/
SET NOCOUNT ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
USE [joylog1];
GO
IF OBJECT_ID(N'san.cases', N'U') IS NULL OR OBJECT_ID(N'san.case_log', N'U') IS NULL OR OBJECT_ID(N'san.case_event', N'U') IS NULL
   OR OBJECT_ID(N'san.evidence', N'U') IS NULL OR OBJECT_ID(N'san.case_block', N'U') IS NULL
   OR OBJECT_ID(N'san.UP_SAN_CaseOpen', N'P') IS NULL OR OBJECT_ID(N'san.UP_SAN_SetStatus', N'P') IS NULL
    RAISERROR(N'adminc_21: в joylog1 нет схемы дел san (сначала AstoryServer/Docs/SQL/san_01_migrate.sql) - права не выданы', 16, 1);
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') CREATE USER [asda_ops] FOR LOGIN [asda_ops];
GO
/* EXECUTE: с базы на схемы (иначе выдача на процедуру не действует) */
REVOKE EXECUTE FROM [asda_ops];
DENY EXECUTE ON SCHEMA::dbo TO [asda_ops];
IF SCHEMA_ID(N'ac') IS NOT NULL DENY EXECUTE ON SCHEMA::ac TO [asda_ops];
GRANT EXECUTE ON san.UP_SAN_CaseOpen TO [asda_ops];
GRANT EXECUTE ON san.UP_SAN_SetStatus TO [asda_ops];
GO
/* чтение дела */
GRANT SELECT ON san.cases TO [asda_ops];
GRANT SELECT ON san.case_log TO [asda_ops];
GRANT SELECT ON san.case_event TO [asda_ops];
GRANT SELECT ON san.evidence TO [asda_ops];
GRANT SELECT ON san.case_block TO [asda_ops];
/* запись: только дописывание истории, событий, файлов и блоков */
GRANT INSERT ON san.case_log TO [asda_ops];
GRANT INSERT ON san.case_event TO [asda_ops];
GRANT INSERT ON san.evidence TO [asda_ops];
GRANT INSERT ON san.case_block TO [asda_ops];
/* правка дела — столбцы, которые правит исходник (cmd_open: evidence_dir; decide / withdraw: решение; mark_executed: исполнение и срок
   апелляции; cmd_appeal: апелляция и пересмотр; cmd_close / appeal overturned: итог и закрытие; везде updated_at) */
GRANT UPDATE (evidence_dir, ladder_step, decision_kind, block_hours, decision_text, decided_by, decided_at,
              executed_by, executed_at, execution_text, appeal_until, appeal_by, appeal_at, appeal_text, appeal_result,
              appeal_reviewed_by, appeal_reviewed_at, outcome, closed_by, closed_at, close_text, updated_at) ON san.cases TO [asda_ops];
GRANT UPDATE (lifted_by, lifted_at, lift_via, lift_text, in_history) ON san.case_block TO [asda_ops];
/* явные запреты (запас прочности поверх отсутствия выдачи) */
DENY DELETE ON san.cases TO [asda_ops];
DENY DELETE ON san.case_log TO [asda_ops];
DENY DELETE ON san.case_event TO [asda_ops];
DENY DELETE ON san.evidence TO [asda_ops];
DENY DELETE ON san.case_block TO [asda_ops];
DENY INSERT ON san.cases TO [asda_ops];
DENY UPDATE ON san.case_log TO [asda_ops];
DENY UPDATE ON san.case_event TO [asda_ops];
DENY UPDATE ON san.evidence TO [asda_ops];
DENY UPDATE (status, case_id, user_index, login, char_idx, char_name, title, hypothesis, is_training, opened_by, opened_at) ON san.cases TO [asda_ops];
DENY ALTER ON SCHEMA::san TO [asda_ops];
GO
PRINT N'adminc_21: asda_ops — дела san.* (SELECT 5 таблиц, INSERT 4, UPDATE столбцов cases / case_block, EXEC 2 процедуры san)';
GO
