# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds — РЕЕСТР ВИДОВ позиций наборов изменений (волна А4.0, 19.11.2026; разбор Reports/admin_center/research_a4_data.md §0).

Движок наборов — общий: хранение adm.changeset (domains/shopcs.py: таблица переходов, выкладка рестартом стойки, откаты, записи) и
оценка/план клиента/расхождения/ведомости ItemDB (domains/shopdata.py — историческое имя модуля движка). Специфика ОБЛАСТИ — в модуле
этого пакета (по одному на область):
  AREA, TITLE           — ключ и подпись области;
  PERM_EDIT, PERM_APPLY — права правки и применения (магазины А3 — shop.edit / shop.apply, данные А4 — data.edit / data.apply);
  KINDS                 — {вид: (подпись, поля, «срочно» допустимо)};
  norm(kind, p), target_key(kind, p) — канонические параметры и цель позиции;
  k_<вид>(ev, p, rep)   — применение позиции к рабочим копиям таблиц и проверки (повтор загрузчиков и гейтов сервера);
  SRV_FILES             — [(семья, подпуть, политика)] серверных таблиц: семья GS (stack_layout.GS_FOLDERS), NPC (NPC_FOLDERS) или
                          ★ А4.8 GSF (только копии ПОЛЯ GameServer + Ch2_GameServer — файл, которого у Indun нет, OpenMapInfo.ini;
                          выкладчик пускает его только в копиях поля, FIELD_GS deploy_changeset);
                          политика same (у всех копий одна база), per_copy (у Indun своя база — правка по базе каждой копии, отличия
                          Indun не затираются; Ch2 = поле), own (у каждой копии свой файл, база не сравнивается);
  CLIENT_FILES, DT, IMPORTERS — клиентские файлы порта, точечные DT (asda_ml_dt_point), импортёры со сторожем ручной правки;
  snapshot() / parse(cli, d) — часть снимка клиента для службы на сервере; cross(ev), divergence(ev, cli, sec), plan(ctx) — по желанию;
  SRV_FILES_LAZY        — ★ А4.3: таблицы, чьи md5 область дочитывает сама (Snap.extend), — только политика копий.
Модули областей импортируются движком в КОНЦЕ domains/shopdata.py (без циклов при импорте). Побочных эффектов при импорте нет.
"""
AREA_MODULES = ("shops", "equipshop", "honorshop", "hairshop", "texts",     # ★ А4.2: тексты RU / EN (только клиент)
                "monsters",                                                # ★ А4.3: монстры и добыча (только сервер)
                "itemdata",                                                # ★ А4.4: предметы (пара item_table + item_list, Cellob + sowell_list)
                "questtables",                                             # ★ А4.5: задания (награды RepayTable ↔ RewardTable, доска LimitationQuest)
                "titledata",                                               # ★ А4.6: звания (FameInfo.txt ↔ title_list: очки, включено, условия, бонусы)
                "skilldata",                                               # ★ А4.7: навыки и классы (SkillInfo ×6 ↔ skill_info, SkillPointTable, ClassStat, ExpTable ↔ charexp)
                "mapdata",                                                 # ★ А4.8: карты (MapWarpCost ×3 GS, OpenMapInfo копий поля ↔ реестр карт порта)
                "eventdata",                                               # ★ А5.4: счастливые часы (GameServerEvent.txt ×3 GS, только сервер)
                "patchcfg")                                                # ★ А5.5: ini наших DLL (patches.ini ×3 GS / ×3 NPC / LoginManager, dbpatch, srvdbpatch ×5) и конфиги стойки
# порядок = порядок разделов в справке и расхождениях
