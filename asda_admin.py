# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""asda_admin.py — админ-центр Astory: точка входа службы и консоли. 16.11.2026.

План и архитектура — Docs/Port/plan/ADMIN_TOOL_PLAN.md; устройство — README.md рядом.

КОМАНДЫ
  serve [--host H] [--port P]       запустить панель (на сервере слушает только адрес VPN, на ПК — 127.0.0.1)
  user-add <логин> --role R         создать пользователя панели (пароль спросит дважды, без эха);
                                    R: owner | admin | gm | support. Первый пользователь — владелец.
  user-list                         пользователи панели
  user-passwd <логин>               новый пароль пользователю (сессии отзываются)
  user-reset-totp <логин>           снять второй фактор (потерян телефон)
  status                            состояние стойки (то же, что раздел «Состояние»)
  find <строка>                     поиск учётки (логин, номер, персонаж, IP, MAC)
  audit [N]                         последние N записей журнала действий
  ref-build                         пересобрать справочники предметов/иконок (tools/build_ref_data.py)
  selftest [--live [--only блоки]]  самопроверка: без сети; --live — ещё и чтение живых баз через asda_admin; --only skills,… —
                                    только с --live: быстрые проверки службы и названные живые блоки (без значения / без --live — отказ)
  changeset …                       наборы изменений данных игры (А3 магазины, А4 данные; domains/shopcs.py, cs_kinds/*):
      list | show N | diverge [--all]                     --all — и разделы данных игры А4 (витрина 6800, честь, причёски)
      new "заголовок" [--note T] [--order together|client_first|server_first] [--urgent]
      add N <вид> '<json параметров>' | del N <позиция> | check N | approve N [--balance-ok] | reopen N | cancel N
                                                          --balance-ok — второе подтверждение сильной правки баланса (А4)
      server-dry N | client-dry N                         сухие прогоны половин (ничего не пишут в стойку и порт)
      client-apply N | client-rollback N | released N     клиентская половина (только ПК; выпуск клиента — не делается)
      server-apply N --confirm-restart [--unsynced-ok]    серверная половина рестартом стойки с объявлением (только владелец);
                                                          --unsynced-ok — сервер раньше ВЫПУСКА клиента
      server-rollback N --confirm-restart [--irreversible-ok] [--held-ok]   откат; после продаж затронутых кодов — второе
                                                          подтверждение; --held-ok — коды со сменой стопки/веса стопки на руках
      server-sync N                                       состояние серверной половины по md5 стойки (после сбоя чтения)
      guard N [--rollback] [--held-ok]                    перепроверка набора (держатели, «на руках», правила областей) — её зовёт
                                                          deploy_changeset.py после остановки стойки, до копирования (код 0 — чисто)
  stack …                           управление стойкой (А5.1; ТОЛЬКО restart_stack.py: объявление Discord EN/AR/RU, 3 мин с отсчётом в игре;
                                    только ПК, право stack.control; domains/stack.py):
      state                                               счёт процессов стойки (все копии), идущее управление
      restart --confirm-restart | stop --confirm-stop | start --confirm-start
      tick --kind restart|stop <секунд>                   отсчёт в игре (объявление мостом) — его зовёт restart_stack.py, вручную не нужен
  maint …                           режим обслуживания — вход только служебным учёткам 1…5000 (А5.3; domains/maint.py; SQL L09,
                                    право server.maintenance):
      state                                               SQL-часть L09, режим и счётчики, DLL L09 по журналу патчей, кто в игре
      on --confirm-maint (--announce "текст" | --silent) [--kick-players] [--partial-ok] [--reason "текст"]
                                                          включить: объявление в игру ДО включения (или явно --silent);
                                                          не дошло до всех узлов моста — не включает (--partial-ok — всё равно);
                                                          --kick-players — отключить мостом игроков вне 1…5000 (иначе играют дальше)
      off --confirm-maint [--announce "текст"] [--reason "текст"]   выключить
      по расписанию: jobs add maint.on --at "…" --confirm-maint '{"announce": "…"}'
  events …                          события и сбросы (А5.4; domains/events.py; мост v84 — от персонажа служебной учётки ≤ 5000 с GM-флагом
                                    в игре; права server.events / server.ranks / server.daily):
      state [--daily]                                     события Event.dat всех NpcServer, счастливые часы ×3 GS, предупреждения
      set --type 0|1 --value X --start "ГГГГ-ММ-ДД ЧЧ:ММ" --end "…" --confirm-event [--chan -1|3] [--map N] [--minlv N] [--maxlv N]
          [--replace] [--rate-ok] [--no-auto-off] [--uid N --idx N] [--dry]
                                                          6038: тип 0 — добыча и золото (шансы), 1 — опыт; время — часы СЕРВЕРА; окно без года —
                                                          после конца ставится задание event.off (кроме --no-auto-off)
      off --type 0|1 --confirm-event [--chan -1|3] [--map N] [--uid N --idx N] [--dry]   6040
      rank [--what 0|1|2|3] --confirm-rank [--uid N --idx N] [--dry]   6020 (P25): 0 — всё, 1 — звания 65…69, 2 — топ славы, 3 — условия званий
      daily catchup|force [--confirm-daily] [--dry]       сброс ежедневных заданий доски: догнать суточный / внеочередной всем
      счастливые часы (GameServerEvent.txt) — набором изменений: changeset item-add N lucky.add '{…}' (область «Счастливые часы»)
  patchcfg …                        настройки серверных патчей и конфиги стойки (А5.5; domains/patchcfg.py; только чтение, право patchcfg.view):
      state [--dll AsdaPatch|AddonNPC|LoginPatch|DBPatch|SrvDbPatch] [--all]   копии ini, Version, последний запуск по журналу патчей,
                                                          секции не в режиме «действует» (--all — все), расхождения копий
      show <DLL> <секция>                                 ключи секции: умолчание, тип и предел по исходнику, значение в каждой копии
      configs                                             стоковые конфиги стойки (что читается и когда; секреты без содержимого)
      правка — набором изменений: changeset add N patch.set '{"dll": "AsdaPatch", "section": "…", "key": "…", "value": "…",
      "scope": "all|field|indun"}' или config.set '{"file": "ini\\Collection.ini", …}'; действует после server-apply (рестарт стойки)
  logs …                            хвост серверных журналов стойки (А5.6; domains/logs.py; только чтение, право logs.view):
      sources                                             источники: копии, подпапка, кодировка, ротация, как пишет процесс
      files <источник> <копия> [--kind Log_<вид>]          файлы журнала (новые сверху); у gslog без --kind — список видов
      tail <источник> <копия> [<файл>] [--kind Log_<вид>] [--lines N] [--grep ТЕКСТ] [--level err|warn|info|debug] [--scan БАЙТ]
          [--follow [--minutes N]]                        хвост (без файла — самый новый); секреты скрыты; --follow — опрос раз
                                                          в 10 с, данные открываются только при смене размера / времени (N ≤ 30 мин)
  ac …                              журнал античита joylog1.ac.* (А6.1; domains/acjournal.py; только чтение, право ac.view):
      events [--account N|логин] [--char ИМЯ] [--ip A.B.C.D] [--table T] [--kind "таблица:текст"] [--server S]
          [--from ГГГГММДД] [--to ГГГГММДД] [--service] [--page N] [--size N]
                                                          лента всех 8 таблиц по времени: вид текстом, номер и патч по
                                                          KindText; служебные строки — только с --service
      summary [--day ГГГГММДД]                            виды за сутки, топ нарушителей за 7 суток, учётки за сутки
      kinds [--table T]                                   каталог видов (номер, патч, служебная) по AcJournal.cpp
  acdaily …                         суточный отчёт античита (А6.6; domains/acdaily.py — код AstoryServer/Tools/Anticheat/ac_daily_report без правок;
                                    просмотр — право ac.view, прогон — ac.daily_run; служба считает сама в 00:20 за вчера):
      list [--day ГГГГММДД]                               прогоны (новые сверху): окно, флаги вне владельца / фон, ошибки, пороги
      show [--id N | --day ГГГГММДД]                      итог по метрикам, флаги вне списка владельца, фон владельца
      events --metric M [--id N | --day ГГГГММДД] [--page N] [--size N]   события метрики (то, что исходник пишет в CSV)
      md [--id N | --day ГГГГММДД]                        Markdown исходника этого прогона как есть
      run [--date ГГГГММДД] [--days N] [--thr КЛЮЧ=ЗНАЧЕНИЕ …] [--dry]
                                                          посчитать и записать в AsdaAdmin (только на сервере: журналы стойки
                                                          читаются там локально); --dry — предпросмотр; пороги по умолчанию прежние
  autoblock …                       автоблок и EAC (А6.8, часть «чтение»; domains/autoblock.py; только чтение, право ac.view):
      ladder                                              лестница ac_case_config.json против patches.ini P48 / P69 всех копий
                                                          GameServer тем же кодом, что ac_case.py ladder --check; паритет, режимы,
                                                          счётчики; правка — набором patch.set (changeset … patch.set)
      history [--from ГГГГММДД] [--to ГГГГММДД] [--account N|логин] [--service-in]
                                                          кики и автоблоки P48, ступени P69, BlockList / BlockHistory с причиной,
                                                          сроком, происхождением и снятием (по умолчанию 30 суток)
      eac --uid N [--net]                                 EAC по учётке: процесс и порты, мост P73, KICK-события, блок, счётчики;
                                                          состояние сессии EAC сейчас — точка статуса AsdaEacServer 127.0.0.1
                                                          (только на сервере; на ПК — пометка); --net — с IP канала EAC и игры
  names …                           очередь имён (А6.11, часть «имена»; domains/namereview.py; право names.review):
      queue [--from ГГГГММДД] [--to ГГГГММДД] [--all] [--state all|bad|open|ok|rename|stale] [--account N|логин]
          [--service-in] [--page N] [--size N]            новые и сменённые имена за период, проверка как у char.rename (A13)
      marks --uid N --idx N                               история отметок персонажа
      mark --uid N --idx N --verdict ok|rename [--note ТЕКСТ] [--dry]
                                                          отметка «ок / сменить» (пишет только AsdaAdmin adm.NameReview; имя не
                                                          меняется — смена: операция char.rename)
  reports …                         жалобы игроков на игроков из бота Discord (А6.11, часть «жалобы»; domains/reports.py; просмотр — право
                                    reports.view, действия — reports.handle; пишется только AsdaAdmin adm.PlayerReport*):
      list [--status open|new|taken|closed|all] [--category cheat|scam|abuse|rmt|other] [--target НИК] [--reporter DISCORD_ID]
          [--page N] [--size N]                           очередь жалоб
      show --id N                                         жалоба целиком: описание, ссылки, скриншоты, цель, автор ↔ учётка, ответы
      (действия ниже — только с --as <логин панели>: роль — учётки панели; любое — с --dry предпросмотр)
      take --id N   |   close --id N --outcome action|case|no_violation|duplicate|insufficient --note ТЕКСТ
      case --id N --case AC-NNNN                          связать с делом (дело открывает cases open)
      reply --id N --text ТЕКСТ                           ответ автору — бот на ПК отправит личным сообщением («\\n» — перевод строки)
  chat …                            журнал чата и заглушки (А6.12; domains/chatlog.py; журнал joylog1.chat.* пишет P129 / AsdaPatch v86; просмотр —
                                    право chat.view, заглушки — chat.mute / chat.unmute; служебные ≤ 5000 — только владелец):
      log [--from ГГГГММДД] [--to ГГГГММДД] [--channel 1,2,…] [--account N|логин] [--char ИМЯ] [--char-uid N --char-slot N]
          [--text ПОДСТРОКА] [--map N] [--server ИМЯ] [--mute any|0|1|2] [--mute-id N] [--raw] [--page N] [--size N]
                                                          сообщения (новые сверху; без дат — последние 2 суток; каналы: 1 обычный,
                                                          2 глобальный, 3 широкий, 4 шёпот, 5 отряд, 6 клан, 7 армия, 8 лавка,
                                                          9 крик лавки, 10 крик предметом; --raw — байты text_raw и прочтения)
      mutes [--state active|expired|lifted|all] [--account N|логин] [--page N] [--size N]   заглушки
      (действия ниже — только с --as <логин панели>: роль — учётки панели; любое — с --dry предпросмотр; до GameServer доходит
       не позже чем через 15 с)
      mute (--uid N | --login Л) [--slot N] | --char ИМЯ   --minutes N --reason ТЕКСТ
                                                          заглушка на учётку (без --slot) или персонажа (--slot / --char)
      unmute --mute-id N --reason ТЕКСТ                   снять заглушку досрочно
      undo --audit N                                      откат записи журнала chat.mute (снять) или chat.unmute (поставить снова
                                                          на остаток срока) — право audit.undo
  cases …                           дела античита AC-NNNN (А6.7; domains/cases.py — код AstoryServer/Tools/Anticheat/ac_case.py; хранилище доказательств —
                                    каталог службы на сервере: запись — только консолью / панелью НА СЕРВЕРЕ; консоль — роль владельца;
                                    блок дела — операция account.block, снятие — account.unblock; любое действие — с --dry предпросмотр):
      list [--status S] [--account N|логин] [--training 0|1]   дела (новые сверху)
      show AC-NNNN                                        дело целиком (текст исходника render_case)
      ladder                                              лестница и правила дел (ac_case_config.json)
      verify [AC-NNNN]                                    целостность хранилища и связей (одно дело или все)
      (действия ниже — только с --as <логин панели>: роль и «лицо» — учётки панели; две учётки панели одного человека не различаются)
      open (--uid N | --login L) --title ТЕКСТ [--char ИМЯ] [--hypothesis ТЕКСТ] [--training]
      attach AC-NNNN [--event ТАБЛИЦА:N …] [--from ГГГГММДД --to ГГГГММДД] [--log ИСТОЧНИК/КОПИЯ[/ВИД]/ФАЙЛ --needle ТЕКСТ … --label МЕТКА]
          [--note ТЕКСТ]                                  события ac.* (списком или окном по учётке) и выдержка журнала стойки
      export AC-NNNN [--format json|csv|json,csv]   |   rollback-report AC-NNNN [--serial GUID …] [--from … --to …] [--max N]
      decide AC-NNNN --step 0..6 --text ТЕКСТ [--hours N] [--reason-en ТЕКСТ] [--override-two-sources ПОЧЕМУ] [--confirm AC-NNNN]
      execute AC-NNNN --text ТЕКСТ   |   withdraw AC-NNNN --text ПОЧЕМУ   |   lift AC-NNNN [--text ТЕКСТ] [--all-blocks] [--confirm AC-NNNN]
      appeal AC-NNNN --text ТЕКСТ [--who ИГРОК] [--late ПОЧЕМУ] [--resolve upheld|overturned]
      close AC-NNNN --outcome sanctioned|acquitted|no_action --text ТЕКСТ [--force-unverified ПОЧЕМУ]
  money …                           деньги gp7 (А6.2; domains/money.py; только чтение, право money.view; служебные учётки ≤ 5000 —
                                    отдельной строкой, --service-in — в общем итоге):
      summary [--service-in] [--minutes N]                итоги покупок по категориям учёток, подарки, висящие, балансы, сток рядом,
                                                          testFixedBalance шлюза
      purchases [--account N|логин] [--code N] [--kind buy|gift|refund|fail] [--who player|service|nolink] [--test 0|1]
          [--from ГГГГММДД] [--to ГГГГММДД] [--service-in] [--page N] [--size N]   журнал покупок gp7 всех учёток (новые сверху)
      gifts [--state H|C|R] [--test 0|1] [--hanging] [--minutes N] [--account …] [--from …] [--to …] [--page N] [--size N]
      holds [--minutes N] [--window СЕКУНД]               висящие 'H' старше N минут — сверка как gift_reconcile.py (ничего не применяет)
      sales [--from ГГГГММДД] [--to ГГГГММДД] [--who …] [--service-in]   продажи по дням и позициям (по умолчанию 30 суток), сток рядом
      accounts [--account …] [--who …] [--page N] [--size N]   учётка сайта gp7 ↔ игровая: баланс, покупки
      undelivered [--who …] [--from …] [--to …] [--minutes N] [--service-in] [--no-logs]
                                                          оплачено, не выдано: заказы gp7 без стока и ящика, причина A / B по
                                                          журналам GameServer и шлюза (только чтение)
      adjustments [--account N|логин] [--page N] [--size N]   журнал корректировок баланса gp7 (А6.9; не выручка), сутки лимита
      (действия ниже — только с --as <логин панели> роли owner, право money.adjust; любое — с --dry предпросмотр)
      adjust --login ЛОГИН --kind credit|debit --amount N --reason ТЕКСТ --confirm-amount N --confirm-login ЛОГИН_САЙТА [--req UUID]
          [--expect-before N]                             («было» из --dry; без ключа — предпросмотр той же команды)
                                                          начислить / списать баланс gp7 (до 100 000 за операцию, 500 000 в сутки
                                                          по часам сервера; adm.GP7Adjust, журнал adm.GP7AdjustLog)
      undo --audit N                                      откат корректировки — обратная корректировка со ссылкой (один раз)
  econ …                            экономика: золото (А6.3; domains/econ.py; право econ.view, снимок — econ.snapshot; служебные ≤ 5000 —
                                    отдельной строкой, --service-in — в общем итоге):
      summary [--service-in]                              золото на руках, последний снимок и неучтённое, каталог источников (знак по
                                                          реверсу процедур Joy1), не считающиеся таблицы
      flows [--from ГГГГММДД] [--to ГГГГММДД] [--source КЛЮЧ] [--service-in]   потоки по дням и источникам (по умолчанию 30 суток)
      richest [--n N] [--service-in]                      богатейшие персонажи (Item.Code = 20551)
      rare [--n N] [--service-in]                         редкое на руках (таблица редкого P11/P59), события P59 за 30 суток
      unaccounted [--id N] [--service-in]                 снимки и «снимок − журналы» = неучтённое (золото с моба журналов не пишет)
      snapshot                                            снять снимок золота сейчас (пишет только AsdaAdmin; служба — сама в 00:05)
  trade …                           передачи, аукцион, лавки (А6.4; domains/trade.py; только чтение, право econ.view; служебные ≤ 5000 —
                                    отдельно, --service-in — в общем списке; период по умолчанию — 30 суток):
      graph [--from ГГГГММДД] [--to ГГГГММДД] [--account N|логин] [--group trade|store|auction|gift] [--service-in]
                                                          кто кому: пары по правилу M3 (ac_metrics_db), цепочки, серийники, один
                                                          IP / MAC — разные учётки, зеркала «…To» (не считаются), ящик сейчас
      transfers [--from …] [--to …] [--account …] [--pair N-N] [--group …] [--service-in] [--page N] [--size N]
                                                          передачи построчно (новые сверху)
      market [--from …] [--to …] [--page N] [--service-in]   живые лоты Exitem, цены, история аукциона, налог
      stores [--from …] [--to …] [--no-logs] [--service-in]   сделки лавок, журнал Log_SelfStore и сверка по дням
  odds …                            шансы: выпало против заявленного (А6.5; domains/odds.py; только чтение, право econ.view;
                                    служебные ≤ 5000 — отдельно, --service-in — в общем; период по умолчанию — 90 суток;
                                    --alpha 0.05|0.01|0.001 — уровень значимости, поправка Холма):
      upgrade [--from ГГГГММДД] [--to ГГГГММДД] [--alpha A] [--service-in]
                                                          заточка по ступени и свитку против ItemUpgrade / OverUpgrade,
                                                          высшая переработка, перенос (порог 60), извлечение
      boosters [--from …] [--to …] [--alpha A] [--no-logs] [--service-in]
                                                          призы бустеров против весов GachaItemRateTable, Log_GachaItem
      boxes [--from …] [--to …] [--alpha A] [--service-in]   премиум-коробки gp7 против равномерного пула
  db …                              бэкапы баз (А5.7; domains/dbbackup.py, dbstand.py; права db.view / db.backup / db.prune / db.stand):
      state                                               базы (модель, размеры, последний бэкап любого инструмента по msdb), бэкапы
                                                          панели, место на томе папки, предупреждения
      backup (--all | --db Joy1[,AsdaStoryOp…])           бэкап сейчас: COPY_ONLY + CHECKSUM + RESTORE VERIFYONLY, ждёт итога; затем
                                                          уборка старых бэкапов панели; по расписанию: jobs add db.backup --at "…"
                                                          --repeat daily '{"dbs": "all"}' (исполнитель — служба)
      verify --id N                                       перепроверить файл бэкапа панели (RESTORE VERIFYONLY)
      prune [--db Joy1] --confirm-prune [--dry]            убрать старые бэкапы панели (последние проверенные и чужие — никогда)
      stand --id N [--keep] [--drop-kept]                 восстановить на стенд LocalDB этого ПК: scp + md5, RESTORE … WITH MOVE,
                                                          DBCC CHECKDB, строки таблиц; файл бэкапа с ПК удаляется всегда, база стенда —
                                                          если не --keep; оставленные --keep базы следующие прогоны не трогают,
                                                          удалить их — --drop-kept
      restore                                             на живой сервер — НЕ делается (отказ с объяснением)
      release --confirm-release                           снять зависшее «идёт» (строка бэкапа и задания db.*), если бэкап не идёт
                                                          на самом деле (блокировка свободна); только владелец
      bak [--all]                                         служебные копии *_bak_* (А5.8; domains/bakdrop.py): вердикт каталога
                                                          (можно убрать / нужна откату / неизвестно), размер, ссылки; --all — и
                                                          отсутствующие на сервере строки каталога
      bakdrop --db Joy1 --obj dbo.a[,dbo.b…] [--backup N] --confirm-bakdrop [--dry]
                                                          удалить копии «можно убрать» одной транзакцией (только владелец; нужен
                                                          свежий проверенный бэкап этой базы); снимок DDL и строк — adm.bakdrop_log
  jobs …                         задания планировщика adm.job (А5.1; core/jobs.py):
      list [--all] | cancel N | release N --confirm-release
      add <операция> --at "ГГГГ-ММ-ДД ЧЧ:ММ" [--repeat daily|weekly] [--note T] [--confirm-<слово>] ['<json параметров>']
                                                          время без пояса — местное этой машины
      run-due                                             один проход исполнителя «ПК» (задания стойки)
      watch --minutes N                                   проходы раз в минуту N минут (выход по сроку или Ctrl+C)
  releases …                        выпуски: статус, только чтение (А7.1; domains/releases.py; решение владельца А7 №6 — выпуск только
                                    батниками DEPLOY на ПК; просмотр — право releases.view, отправка снимка — releases.push):
      show                                                указатели сервера обновлений (версия, seq, min_version, срок и проверка подписи)
                                                          и последний снимок ПК в AsdaAdmin, предупреждения
      push [--dry]                                        только ПК: собрать снимок (releases.log, Build/EAC/latest.json, Inbox, итоги
                                                          батников, ключи «есть / срок» — без ключей и путей) и записать в
                                                          adm.ReleasePcStatus (операция release.push; --dry — только показать)
  crashes …                         сбои клиента (А7.2; domains/crashes.py; решения владельца А7 №1 — расшифровка только на ПК, №8 — срок
                                    хранения; просмотр — crash.view, отправка — crash.sync, удаление старых .alog — crash.prune):
      show                                                сводка в AsdaAdmin: группы мест падения, частота за сутки и 7 суток, версии,
                                                          квота LogDrop, предупреждения
      sync [--dry] [--no-fetch]                           только ПК: забрать новые .acrash по scp, расшифровать на ПК, прислать сводку в
                                                          adm.ClientCrash* (операция crash.sync; --no-fetch — без сервера, по уже забранным;
                                                          --dry — показать по уже забранным, ничего не забирая и не записывая; без ключа
                                                          LogSeal на этом ПК — отказ до scp)
      prune [--confirm alogprune]                         удалить на сервере .alog старше 60 суток и их .json (.acrash — никогда); без
                                                          ключа — только предпросмотр (число, размер); операция crash.alog_prune
  notes …                           заметки к выпуску (А7.7; domains/notes.py; решение владельца А7 №7 — черновик и публикация в панели;
                                    просмотр — notes.view, отправка changelog — notes.push; публикует только панель кнопкой):
      show                                                последний снимок changelog в AsdaAdmin: записи, вид, «опубликовано» / нет
      push [--dry]                                        только ПК: прочитать текущий changelog (имя — из AGENT_RULES_PORT.md) и записать
                                                          как есть в adm.NotesSnap (операция notes.push; --dry — только показать); файлы
                                                          changelog не меняются
      resync [--dry]                                      перечитать реестр записей по последнему снимку (операция notes.resync; после
                                                          обновления разбора — переводит прежние ключи публикаций на новые)
Консоль действует от имени «cli:<пользователь Windows>@<машина>» с ролью владельца: доступ к ней уже требует ключа
SSH сервера (пароль логина БД читается с сервера). Всё, что меняет данные, пишется в журнал adm.audit.
Побочных эффектов при импорте нет.
"""
import getpass
import json
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _cli_ctx():
    """Контекст операций консоли."""
    from core import ops
    return ops.Ctx(None, ("cli:%s@%s" % (getpass.getuser(), socket.gethostname()))[:32], "owner", "", "cli")


def _ask_pw(login):
    """Пароль дважды без эха."""
    a = getpass.getpass("Пароль для %s: " % login)
    b = getpass.getpass("Ещё раз: ")
    if a != b:
        raise SystemExit("пароли не совпали")
    return a


def main(argv):
    for s in (sys.stdout, sys.stderr):   # консоль Windows (cp1251/cp866) не должна ронять вывод на «→», «↔» и т.п.
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    from domains import load_all
    load_all()
    from core import ops
    if cmd == "serve":
        from api import server
        host = args[args.index("--host") + 1] if "--host" in args else None
        port = int(args[args.index("--port") + 1]) if "--port" in args else None
        server.serve(host, port)
        return 0
    if cmd == "user-add":
        if not args or "--role" not in args:
            raise SystemExit("user-add <логин> --role owner|admin|gm|support")
        login, role = args[0], args[args.index("--role") + 1]
        r = ops.run(_cli_ctx(), "users.create", {"login": login, "role": role, "password": _ask_pw(login)})
        print(r["message"])
        if role in ("owner", "admin"):
            print("При первом входе в панель будет предложено включить второй фактор (приложение-аутентификатор).")
        return 0
    if cmd == "user-list":
        from domains import panel_users
        for u in panel_users.list_users():
            print("%-4s %-20s %-8s %s %s вход: %s" % (u["id"], u["login"], u["role"], "ОТКЛ" if u["disabled"] else "вкл ",
                                                      "2FA" if u["totp_on"] else "   ", u["last_login_at"] or "—"))
        return 0
    if cmd == "user-passwd":
        login = args[0]
        print(ops.run(_cli_ctx(), "users.reset_password", {"login": login, "password": _ask_pw(login)})["message"])
        return 0
    if cmd == "user-reset-totp":
        print(ops.run(_cli_ctx(), "users.reset_totp", {"login": args[0]})["message"])
        return 0
    if cmd == "status":
        from domains import status
        s = status.snapshot(force=True)
        if s["host_error"]:
            print("!", s["host_error"])
        for p in s["stack"]:
            print("%-3s %-34s pid %-14s порты %s/%s" % ("OK" if p["ports_ok"] else ("~" if p["running"] else "НЕТ"),
                                                      p["title"], ",".join(map(str, p["pids"])) or "—",
                                                      ",".join(map(str, p["listening"])) or "—", ",".join(map(str, p["ports"]))))
        pl = s["players"]
        print("в игре по БД: %s; входов за сутки: %s" % (pl["online_db"], pl["logins_24h"]))
        return 0
    if cmd == "find":
        from domains import players
        for a in players.search(" ".join(args), net=True):
            print("%-7s %-20s блок=%s %s | %s" % (a["Userindex"], a["Us_id"], a["us_block"], a["match"],
                                                ", ".join("%s(%s)" % (c["Charname"], c["Lvl"]) for c in a["chars"])))
        return 0
    if cmd == "audit":
        from core import audit
        for r in reversed(audit.query(limit=int(args[0]) if args else 30)):
            print("%s #%s %-22s %-24s %-7s %s %s" % (r["at"], r["id"], r["login"], r["action"], r["result"], r["target"],
                                                     r["message"]))
        return 0
    if cmd == "ref-build":
        sys.path.insert(0, os.path.join(HERE, "tools"))
        import build_ref_data
        return build_ref_data.main()
    if cmd == "changeset":
        return _changeset(args)
    if cmd == "stack":
        return _stack(args)
    if cmd == "jobs":
        return _jobs(args)
    if cmd == "maint":
        return _maint(args)
    if cmd == "events":
        return _events(args)
    if cmd == "patchcfg":
        return _patchcfg(args)
    if cmd == "logs":
        return _logs(args)
    if cmd == "ac":
        return _ac(args)
    if cmd == "acdaily":
        return _acdaily(args)
    if cmd == "autoblock":
        return _autoblock(args)
    if cmd == "names":
        return _names(args)
    if cmd == "cases":
        return _cases(args)
    if cmd == "reports":
        return _reports(args)
    if cmd == "chat":
        return _chat(args)
    if cmd == "money":
        return _money(args)
    if cmd == "econ":
        return _econ(args)
    if cmd == "trade":
        return _trade(args)
    if cmd == "odds":
        return _odds(args)
    if cmd == "db":
        return _db(args)
    if cmd == "releases":
        return _releases(args)
    if cmd == "crashes":
        return _crashes(args)
    if cmd == "notes":
        return _notes(args)
    if cmd == "selftest":
        from core import config as _cfg
        if _cfg.get().on_server:              # ★ ревизия 57 (мелочь 1): самотест исполняет код из путей порта (на сервере — H:\…, вне дерева службы)
            raise SystemExit("самотест на сервере не запускается: он исполняет код из путей порта, которые на сервере вне дерева службы — "
                             "запускайте его на ПК (asda_admin.py selftest [--live --only …])")
        sys.path.insert(0, os.path.join(HERE, "tests"))
        import selftest
        # ★ А4.7 (решение владельца 20.11): --live --only <блоки через запятую> — офлайн не гоняется, живьём только быстрые проверки
        #   службы и названные блоки (data, texts, monsters, items, quests, titles, skills, shops); без --only — как прежде
        #   ★ ревизия 39 Н-4: --only без значения и --only без --live — отказ (а не тихий полный прогон)
        only, why = selftest.parse_only(args)
        if why:
            raise SystemExit(why)
        return selftest.main(live="--live" in args, only=only)
    raise SystemExit("неизвестная команда %s (help — список)" % cmd)


def _stack(args):
    """★ А5.1: консоль управления стойкой (domains/stack.py)."""
    from core import ops
    from domains import stack
    sub = args[0] if args else "state"
    if sub == "state":
        s = stack.state()
        print("стойка: %s; полная: %s (ожидается %s)" % (s["text"], "да" if s["complete"] else "НЕТ",
                                                       ", ".join("%s=%d" % kv for kv in sorted(s["expect"].items()))))
        r = s["running"]
        print("идёт управление стойкой: %s" % ("нет" if not r else r.get("error") or "задание №%s %s с %s на %s" % (
            r["id"], r["op"], r["started_at"], r["host"])))
        return 0
    if sub == "tick":
        kind = args[args.index("--kind") + 1] if "--kind" in args else "restart"
        left = int(args[-1])
        # ★ ревизия 41 С-2: срок команды 8 с на все узлы сразу — тик (с записью журнала) укладывается в предел вызова restart_stack 30 с
        r = ops.run(_cli_ctx(), "live.announce", {"text": stack.tick_text(kind, left), "rgb": [255, 210, 0], "ttl": stack.TICK_TTL})
        print(r["message"])
        return 0
    name = {"restart": "stack.restart", "stop": "stack.stop", "start": "stack.start"}.get(sub)
    if not name:
        raise SystemExit("stack: неизвестное действие %s (help — список)" % sub)
    prm = {"confirm": sub} if ("--confirm-" + sub) in args else {}
    r = ops.run(_cli_ctx(), name, prm)
    print(r["message"], "(журнал №%s)" % r["audit_id"])
    for ln in (r.get("result") or {}).get("lines") or []:
        print("  ", ln)
    return 0


MAINT_FLAGS = {"--confirm-maint": None, "--silent": None, "--kick-players": None, "--partial-ok": None, "--announce": "text", "--reason": "text"}


def maint_args(args):
    """★ А5.3: ключи «maint on|off» → параметры операции. Неизвестный ключ, ключ без значения, лишнее слово — SystemExit (ничего не делается)."""
    prm, i = {}, 0
    while i < len(args):
        a = args[i]
        if a not in MAINT_FLAGS:
            raise SystemExit("maint: неизвестный ключ %s (help — список)" % a)
        if MAINT_FLAGS[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("maint: у ключа %s нет значения" % a)
            prm[a[2:]] = args[i + 1]
            i += 2
            continue
        prm.update({"--confirm-maint": {"confirm": "maint"}, "--silent": {"silent": "silent"}, "--kick-players": {"kick": "players"},
                    "--partial-ok": {"partial": "partial"}}[a])
        i += 1
    return prm


def _maint(args):
    """★ А5.3: консоль режима обслуживания (domains/maint.py)."""
    from core import ops
    from domains import maint
    sub = args[0] if args else "state"
    if sub == "state":
        if len(args) > 1:
            raise SystemExit("maint state: лишние ключи %s" % " ".join(args[1:]))
        s = maint.state(force=True)
        q, d, p = s["sql"], s["dll"], s["players"]
        if not q["read"]:
            print("SQL L09: не прочитано (%s)" % q["error"])
        else:
            print("SQL L09: таблица %s, врезка в UPUserLogin %s" % ("есть" if q["table"] else "НЕТ",
                                                                 "не прочитана" if q["gate"] is None else "есть" if q["gate"] else "НЕТ"))
            if q["table"]:
                print("режим обслуживания: %s (с %s, %s%s), отказано входов %s, допущено служебных %s" % (
                    "ВКЛЮЧЁН" if q["mode"] == 1 else "выключен", q.get("changed_at") or "—", q.get("changed_by") or "—",
                    (", " + q["reason"]) if q.get("reason") else "", q.get("refused"), q.get("admitted")))
        if not d.get("read") or d.get("active") is None:
            print("DLL L09: не прочитано (%s)" % (d.get("error") or "?"))
        else:
            print("DLL L09: %s (LoginPatch.dll %s%s, LoginManager с %s, журнал %s)" % (
                "действует" if d["active"] else "НЕ действует", d["dll_md5"], " = сборка L09" if d["dll_known"] else "",
                d["lm_start"] or "—", d["log_file"]))
        w = s.get("world") or {}                     # ★ ревизия 43б Н-4 / Н-3: вход в мир и сбои гейта — как в карточке
        if w:
            print("вход в мир с выбора персонажа: %s" % w["text"])
            if w.get("note"):
                print("сбои гейта входа в мир: %s" % w["note"])
        if p["bridge_read"]:
            print("в игре по мосту: вне 1…5000 — %d, служебных — %d" % (len(p["players"]), len(p["operators"])))
        else:
            print("в игре по мосту: не прочитано (%s)" % p["bridge_error"])
        if p["db_read"]:
            print("вошли по БД (Us_member.Flag = 1) вне 1…5000: %d, CharGmInfo вне 1…5000: %s" % (
                p["db_logged"], ", ".join(map(str, p["gm_outside"])) or "нет"))
        return 0
    name = {"on": "maint.on", "off": "maint.off"}.get(sub)
    if not name:
        raise SystemExit("maint: неизвестное действие %s (help — список)" % sub)
    r = ops.run(_cli_ctx(), name, maint_args(args[1:]))
    for w in (r.get("preview") or {}).get("warnings") or []:
        print("  ~", w)
    print(r["message"], "(журнал №%s)" % r["audit_id"])
    return 0


EVENT_FLAGS = {"--type": "type", "--value": "value", "--start": "start", "--end": "end", "--chan": "chan", "--map": "map",
               "--minlv": "minlv", "--maxlv": "maxlv", "--uid": "uid", "--idx": "idx", "--what": "what",
               "--confirm-event": None, "--confirm-daily": None, "--confirm-rank": None, "--replace": None, "--rate-ok": None, "--no-auto-off": None,
               "--dry": None}
EVENT_SUBS = {"set": ("event.set", {"--type", "--value", "--start", "--end", "--chan", "--map", "--minlv", "--maxlv", "--uid", "--idx",
                                    "--confirm-event", "--replace", "--rate-ok", "--no-auto-off", "--dry"}),
              "off": ("event.off", {"--type", "--chan", "--map", "--uid", "--idx", "--confirm-event", "--dry"}),
              "rank": ("rank.recalc", {"--what", "--uid", "--idx", "--confirm-rank", "--dry"}),
              "daily": ("daily.reset", {"--confirm-daily", "--dry"})}


def events_args(sub, args):
    """★ А5.4: ключи «events set|off|rank|daily» → (параметры операции, dry). Неизвестный / чужой ключ, ключ без значения, лишнее слово —
    SystemExit (ничего не делается)."""
    allowed = EVENT_SUBS[sub][1]
    prm, i, dry = {}, 0, False
    if sub == "daily":
        if not args or args[0] not in ("catchup", "force"):
            raise SystemExit("events daily: нужен режим catchup или force (help — список)")
        prm["mode"], args = args[0], args[1:]
    while i < len(args):
        a = args[i]
        if a not in EVENT_FLAGS or a not in allowed:
            raise SystemExit("events %s: неизвестный ключ %s (help — список)" % (sub, a))
        if EVENT_FLAGS[a]:
            if i + 1 >= len(args) or (args[i + 1].startswith("--") and not args[i + 1][2:3].isdigit()):
                raise SystemExit("events %s: у ключа %s нет значения" % (sub, a))
            prm[EVENT_FLAGS[a]] = args[i + 1]
            i += 2
            continue
        if a == "--dry":
            dry = True
        else:
            prm.update({"--confirm-event": {"confirm": "event"}, "--confirm-daily": {"confirm": "daily"}, "--confirm-rank": {"confirm": "rank"},
                        "--replace": {"replace": "replace"},
                        "--rate-ok": {"rate_ok": "rate"}, "--no-auto-off": {"auto_off": "0"}}[a])
        i += 1
    return prm, dry


def _events(args):
    """★ А5.4: консоль событий, рейтингов и сброса ежедневных (domains/events.py)."""
    from core import ops
    from domains import events
    sub = args[0] if args else "state"
    if sub == "state":
        extra = [a for a in args[1:] if a != "--daily"]
        if extra:
            raise SystemExit("events state: лишние ключи %s" % " ".join(extra))
        s = events.state()
        print("время сервера: %s (UTC %s); карт NpcServer: %s" % (s["server_now"], s["server_utc"], s["map_count"]))
        for n, v in s["npc"].items():
            print("  %-16s Event.dat %s" % (n, ("%s, %d б" % (v["md5"][:8], v["size"])) if v["read"] else "не прочитан"))
        for w in s["windows"]:
            print("  событие: %s %s, карт %d (%s), копии %s" % (w["type_name"], w["window"], len(w["maps"]), w["phase"], ",".join(w["copies"])))
        if not s["windows"]:
            print("  событий в Event.dat нет")
        for g, v in s["lucky"].items():
            print("  %-16s GameServerEvent.txt %s строк %s, %s…%s, сейчас %s" % (
                g, (v["md5"] or "—")[:8], v["rows"], v["first"], v["last"], ("+%s" % v["now"][5]) if v["now"] else "нет"))
        # ★ А5.10: P128 (DLL v85+) — значок события видят все игроки; ниже — только оператор
        print("  значок события у игроков: %s" % ", ".join("%s — %s" % (g, t) for g, t in s["badge_text"].items()))   # ★ ревизия 49 Н-1
        for w in s["warnings"]:
            print("  ~", w)
        if "--daily" in args[1:]:
            d = events.daily_state()
            print("ежедневные: граница %s, суточный сброс %s, строк к сбросу %d, задача ОС %s" % (
                d["boundary"], ("сделан (%s, %s)" % (d["done"]["source"], d["done"]["at"])) if d["done"] else "НЕ сделан",
                d["pending_rows"], ("%s, итог %s" % (d["task"]["last"], d["task"]["result"])) if d["task"] else "не прочитана"))
        return 0
    if sub not in EVENT_SUBS:
        raise SystemExit("events: неизвестное действие %s (help — список)" % sub)
    prm, dry = events_args(sub, args[1:])
    r = ops.run(_cli_ctx(), EVENT_SUBS[sub][0], prm, dry=dry)
    pv = r.get("preview") or {}
    if dry:
        print("предпросмотр (ничего не сделано):", pv.get("text") or "")
    for w in pv.get("warnings") or []:
        print("  ~", w)
    if not dry:
        print(r["message"], "(журнал №%s)" % r["audit_id"])
    return 0


MODE_RU = {"active": "действует", "journal": "журнал (Mode=0)", "off": "выключен", "self_off": "в ini включён, установка сама выключила",
           "pending_on": "включён в ini после старта — ждёт рестарта", "pending_off": "выключен в ini после старта — ждёт рестарта",
           "failed": "НЕ ВСТАЛ ([MISMATCH] / [ОШИБКА])", "nolog": "нет в журнале запуска", "absent": "секции нет в файле",
           "unread": "не прочитано", "general": "—"}


def _patchcfg(args):
    """★ А5.5: настройки серверных патчей и конфиги стойки — только чтение (domains/patchcfg.py)."""
    from domains import patchcfg
    from domains.cs_kinds import patchcfg as K
    if not args or args[0] not in ("state", "show", "configs"):
        raise SystemExit("patchcfg: нужно действие state | show <DLL> <секция> | configs")
    sub, rest = args[0], args[1:]
    if sub == "configs":
        if rest:
            raise SystemExit("patchcfg configs: лишние ключи %s" % " ".join(rest))
        for c in patchcfg.configs()["configs"]:
            tag = "правится наборами" if c["edit"] else ("секрет — содержимое скрыто" if c["secret"] else "только просмотр")
            print("%-18s %-34s %s — %s%s" % (c["folder"], c["file"], tag, c["what"], (" (%s)" % c["why"]) if c["why"] else ""))
        return 0
    if sub == "show":
        if len(rest) != 2 or rest[0] not in K.DLL_INI:
            raise SystemExit("patchcfg show <DLL> <секция> (DLL: %s)" % ", ".join(K.DLL_INI))
        s = patchcfg.state(dll_only=rest[0])
        sec = next((x for x in s["dlls"][0]["sections"] if x["name"].lower() == rest[1].lower()), None)
        if not sec:
            raise SystemExit("patchcfg show: секции %s нет в шаблоне %s" % (rest[1], rest[0]))
        print("[%s] %s" % (sec["name"], (sec["index"][0]["text"] if sec["index"] else "в реестре INDEX.md строки нет")[:300]))
        print("  режим: " + ", ".join("%s %s" % (g, MODE_RU.get(m, m)) for g, m in sec["modes"].items()))
        if sec["needs"]:
            print("  вызывает код: " + ", ".join(sec["needs"]))
        if sec["hard_users"] or sec["panel"]:
            print("  от него зависят: " + ", ".join(sec["hard_users"] + (["панель (мост P127)"] if sec["panel"] else [])))
        for k in sec["keys"]:
            rng = "" if k["lo"] is None and k["hi"] is None else " %s…%s" % ("" if k["lo"] is None else k["lo"], "" if k["hi"] is None else k["hi"])
            print("  %-28s %-5s%-14s умолч. %-10s %s%s%s" % (k["key"], k["type"], rng, k["def"], ", ".join("%s=%s" % (g, v) for g, v in k["values"].items()),
                                                     "  РАСХОДЯТСЯ" if k["diverge"] else "", "" if k["edit"] else "  (только просмотр)"))
        return 0
    want, allm, i = None, False, 0
    while i < len(rest):
        if rest[i] == "--dll" and i + 1 < len(rest) and rest[i + 1] in K.DLL_INI:
            want, i = rest[i + 1], i + 2
        elif rest[i] == "--all":
            allm, i = True, i + 1
        else:
            raise SystemExit("patchcfg state: неизвестный ключ %s" % rest[i])
    s = patchcfg.state(force=True, dll_only=want)
    for d in s["dlls"]:
        print("%s — %s (исходник Version %s)" % (d["dll"], d["ini"], d["version_src"]))
        for c in d["copies"]:
            r = c["run"] or {}
            print("  %-18s %s Version %s MasterEnable %s; запуск %s, итог %s" % (
                c["folder"], (c["md5"] or "не прочитан")[:8], c.get("version"), c.get("master"), r.get("start") or c["log"], r.get("total")))
        for sec in d["sections"]:
            ms = set(sec["modes"].values())
            if allm or ms - {"active", "general"} or any(k["diverge"] for k in sec["keys"]):
                print("    [%s] %s%s" % (sec["name"], ", ".join(sorted({MODE_RU.get(m, m) for m in ms})),
                                         "; ключи расходятся: " + ", ".join(k["key"] for k in sec["keys"] if k["diverge"]) if any(k["diverge"] for k in sec["keys"]) else ""))
    for w in s["warnings"]:
        print("  ~", w)
    return 0


LOGS_FOLLOW_POLL_S = 10                   # ★ ревизия 46 Н-3: опрос «следить» консоли (с ПК — SSH + PowerShell на сервере на каждый опрос)
LOGS_FOLLOW_MAX_MIN = 30                  # … и не дольше (≤ 180 опросов)
LOGS_KEYS = {"--kind": True, "--lines": True, "--grep": True, "--level": True, "--scan": True, "--follow": False, "--minutes": True}


def logs_args(args):
    """★ А5.6: разбор ключей logs → (позиционные, {ключ: значение}); неизвестный ключ / ключ без значения — SystemExit."""
    pos, opt, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if a not in LOGS_KEYS:
                raise SystemExit("logs: неизвестный ключ %s (есть: %s)" % (a, " ".join(LOGS_KEYS)))
            if LOGS_KEYS[a]:
                if i + 1 >= len(args) or args[i + 1].startswith("--"):
                    raise SystemExit("logs: у ключа %s нет значения" % a)
                opt[a], i = args[i + 1], i + 2
                continue
            opt[a] = True
        else:
            pos.append(a)
        i += 1
    if "--minutes" in opt and "--follow" not in opt:
        raise SystemExit("logs: --minutes — только вместе с --follow")
    return pos, opt


AC_KEYS = {"events": {"--account": True, "--char": True, "--ip": True, "--table": True, "--kind": True, "--server": True, "--from": True,
                      "--to": True, "--service": False, "--page": True, "--size": True},
           "summary": {"--day": True}, "kinds": {"--table": True}}


def ac_args(sub, args):
    """★ А6.1: разбор ключей ac <действие> → {ключ: значение}; неизвестный ключ, ключ без значения, позиционный аргумент — SystemExit."""
    keys, opt, i = AC_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("ac %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys)))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("ac %s: у ключа %s нет значения" % (sub, a))
            opt[a], i = args[i + 1], i + 2
            continue
        opt[a], i = True, i + 1
    return opt


def _ac(args):
    """★ А6.1: журнал античита — только чтение (domains/acjournal.py). Консоль — роль владельца: IP видны."""
    from domains import acjournal
    if not args or args[0] not in AC_KEYS:
        raise SystemExit("ac: нужно действие events | summary | kinds (help — ключи)")
    sub = args[0]
    opt = ac_args(sub, args[1:])
    if sub == "kinds":
        cat = acjournal.catalog_public()
        if opt.get("--table") and opt["--table"] not in acjournal.TABLE_NAMES:
            raise SystemExit("ac kinds: таблицы %s нет (есть: %s)" % (opt["--table"], " ".join(acjournal.TABLE_NAMES)))
        print("каталог: %s (md5 %s)" % (cat["source"], cat["md5"]))
        for t in cat["tables"]:
            if opt.get("--table") and t["name"] != opt["--table"]:
                continue
            print("ac.%s — %s (столбец %s), видов %d" % (t["name"], t["title"], t["kind_col"], len(t["kinds"])))
            for k in t["kinds"]:
                print("  %4d %-6s %s%s" % (k["n"], k["patch"] or "?", k["kind"], "  [служебная: %s]" % k["service"] if k["service"] else ""))
        return 0
    if sub == "summary":
        s = acjournal.summary(opt.get("--day"))
        print("сутки %s: событий %d, из них служебных %d" % (s["day"], s["kinds_total"], s["kinds_service"]))
        for k in s["kinds"]:
            print("  %6d  учёток %3d  ac.%-19s %4s %-6s %s%s" % (k["n"], k["users"], k["table"], k["num"] if k["num"] is not None else "?",
                                                         k["patch"] or "?", k["kind_text"], "  [служебная]" if k["service"] else ""))
        print("топ нарушителей за 7 суток (нарушений без служебных / всего строк по ac.v_top_offenders):")
        for r in s["top"]:
            print("  №%-7s %-20s %4d / %4d  блок %s  последнее %s  %s" % (r["user_index"], r["login"] or "—", r["violations"], r["total"] or 0,
                                                                     r["us_block_now"], r["last_local"], r["char_names"] or ""))
        print("учётки за сутки (ac.v_account_daily): %d" % len(s["daily"]))
        for r in s["daily"]:
            print("  №%-7s %-20s всего %4d  кики %d  автоблоки %d" % (r["user_index"], r["login"] or "—", r["total"], r["kicks"], r["autoblocks"]))
        for e in s["errors"]:
            print("  ! ошибка:", e)
        return 0
    q = {"account": opt.get("--account"), "char": opt.get("--char"), "ip": opt.get("--ip"), "table": opt.get("--table"),
         "kind": opt.get("--kind"), "server": opt.get("--server"), "from": opt.get("--from"), "to": opt.get("--to"),
         "service": "1" if opt.get("--service") else "0", "page": opt.get("--page"), "size": opt.get("--size")}
    r = acjournal.events(q, True)
    print("событий %d (страница %d из %d по %d)%s" % (r["total"], r["page"], r["pages"], r["size"],
                                                    "" if r["service"] else ", служебные скрыты (--service — показать)"))
    for e in r["rows"]:
        print("  %s  ac.%-19s %4s %-6s %-16s №%-7s %-14s %-16s %s%s" % (
            e["ev_local"], e["table"], e["n"] if e["n"] is not None else "?", e["patch"] or "?", e["server"] or "", e["uid"] or "—",
            e["login"] or "", e["char"] or "", e["kind_text"], ("  ip %s" % e["ip"]) if e["ip"] else ""))
    for e in r["errors"]:
        print("  ! ошибка:", e)
    return 0


AB_KEYS = {"ladder": {}, "history": {"--from": True, "--to": True, "--account": True, "--service-in": False},
           "eac": {"--uid": True, "--net": False}}
NM_KEYS = {"queue": {"--from": True, "--to": True, "--all": False, "--state": True, "--account": True, "--service-in": False, "--page": True,
                     "--size": True},
           "marks": {"--uid": True, "--idx": True}, "mark": {"--uid": True, "--idx": True, "--verdict": True, "--note": True, "--dry": False}}
# ★ А6.11 (22.11, часть «жалобы»): «reports <действие>» — ключи; действия (take, close, case, reply) — только от имени учётки панели (--as)
RP_KEYS = {"list": {"--status": True, "--category": True, "--target": True, "--reporter": True, "--page": True, "--size": True},
           "show": {"--id": True},
           "take": {"--id": True, "--as": True, "--dry": False},
           "close": {"--id": True, "--outcome": True, "--note": True, "--as": True, "--dry": False},
           "case": {"--id": True, "--case": True, "--as": True, "--dry": False},
           "reply": {"--id": True, "--text": True, "--as": True, "--dry": False}}


def kv_args(cmd, keys, sub, args):
    """★ А6.8 / А6.11: разбор ключей «<команда> <действие>» → {ключ: значение}; неизвестный ключ, ключ без значения, позиционный аргумент —
    SystemExit (без обращения к базе и стойке)."""
    keys, opt, i = keys[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("%s %s: неизвестный аргумент %s (есть: %s)" % (cmd, sub, a, " ".join(keys) or "—"))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("%s %s: у ключа %s нет значения" % (cmd, sub, a))
            opt[a], i = args[i + 1], i + 2
            continue
        opt[a], i = True, i + 1
    return opt


def _autoblock(args):
    """★ А6.8: автоблок и EAC — только чтение (domains/autoblock.py)."""
    from domains import autoblock
    if not args or args[0] not in AB_KEYS:
        raise SystemExit("autoblock: нужно действие ladder | history | eac (help — ключи)")
    sub = args[0]
    opt = kv_args("autoblock", AB_KEYS, sub, args[1:])
    if sub == "ladder":
        L = autoblock.ladder()
        print("код %s (%s), конфиг %s; прочитано %s UTC" % (L["source"]["code_md5"], L["source"]["where"], L["source"]["config_md5"], L["read_at"]))
        for x in L["ladder"]:
            print("  %d %-12s %-26s срок %-5s %-7s %s" % (x["step"], x["code"], x["name"], "" if x["hours"] is None else x["hours"], x["exec"], x["mechanism"]))
        for c in L["check"]:
            print("  %-16s ступень %d  %-36s ini=%-5s лестница=%-5s %s" % (c["server"], c["step"], c["key"], c["ini"], c["ladder"],
                                                                     "не прочитано" if c["unread"] else ("OK" if c["ok"] else "РАСХОЖДЕНИЕ")))
        print("ИТОГ: расхождений %d, не прочитано %d (как ladder --check: %d)" % (L["mismatches"], L["unread_checks"], L["ladder_check_bad"]))
        for p in L["parity"]:
            print("  паритет %s ↔ %s: %s" % (p["pair"][0], p["pair"][1], "совпадает" if p["same"] else "НАРУШЕН"))
        for d in L["diverge"]:
            print("  расходится [%s] %s: %s" % (d["section"], d["key"], d["values"]))
        for s, m in L["modes"].items():
            print("  режим %-24s %s" % (s, ", ".join("%s=%s" % kv for kv in m.items())))
        for s, xs in L["counters"].items():
            for x in xs:
                print("  счётчик %-24s %s: учёток %s" % (s, x["file"], x["accounts"] if x["read"] else "файла нет"))
        for e in L["errors"]:
            print("  ! ошибка:", e)
        print("правка автоблока — набором patch.set «Настроек патчей» и рестартом стойки")
        return 1 if L["mismatches"] else 0
    if sub == "history":
        r = autoblock.history({"from": opt.get("--from"), "to": opt.get("--to"), "account": opt.get("--account"),
                               "svc": "in" if opt.get("--service-in") else "sep"}, "console")
        print("период %s — %s; киков %s, засчитано %s, автоблоков P48 %s" % (r["from"], r["to"], r["sums"]["kicks"], r["sums"]["counted"], r["sums"]["autoblocks"]))
        for x in r["not_counted"]:
            print("  не засчитано %4d: %s" % (x["n"], x["reason_db"] or "—"))
        for b in r["blocks"]:
            print("  №%-7s %-16s %-8s %-7s %s → %s  %-7s %-6s %s" % (b["uid"], b["login"] or "", b["cat"], b["origin"], b["black"],
                                                                 "бессрочно" if b["perm"] else b["close"], b["state"], b["lift"] or "", b["reason"]))
        for k in r["kicks"]:
            print("  %s №%-7s %-10s %s/%s %s" % (k["ev_local"], k["uid"], k["kind"], k["kick_count"], k["kick_threshold"], k["reason_text"] or ""))
        for k in r["p69"]:
            print("  P69 %s №%-7s ступень %s нарушений %s часов %s 2271=%s" % (k["ev_local"], k["uid"], k["stage"], k["count"], k["hours"], k["sent"]))
        for e in r["errors"]:
            print("  ! ошибка:", e)
        return 0
    if not opt.get("--uid"):
        raise SystemExit("autoblock eac: нужен --uid N")
    r = autoblock.eac(opt["--uid"], can_net=bool(opt.get("--net")))
    print("учётка %s (%s), блок %s" % (r["uid"], r["login"], (r["block"] or {}).get("state")))
    lv = r.get("live") or {}
    if lv.get("state") != "ok":
        print("  EAC сейчас: %s — %s" % (lv.get("state"), lv.get("note")))
    else:
        sv, a = lv.get("server") or {}, lv.get("account")
        print("  EAC сейчас (точка %s, снимок %s мс): Mode=%s FailOpen=%s EOS=%s; 15901 %s (аутентифицировано %s), игровых сессий %s (защищено %s)"
              % (sv.get("version"), sv.get("age_ms"), sv.get("mode"), sv.get("fail_open") or "нет", "есть" if sv.get("eos_session") else "нет",
                 (sv.get("eac") or {}).get("registered"), (sv.get("eac") or {}).get("authenticated"), (sv.get("games") or {}).get("sessions"),
                 (sv.get("games") or {}).get("protected")))
        if not a:
            print("  учётки в таблицах EacServer нет (не в игре и без EAC-сессии)")
        else:
            e = a.get("eac")
            print("  EAC-сессия: %s" % ("нет" if not e else "%s, %s, с %s, PING %s мс назад, BIND %s%s" % (
                e.get("state"), "Authenticated" if e.get("authenticated") else "НЕ аутентифицирована", e.get("registered_at"), e.get("last_ping_ago_ms"),
                e.get("binds"), (", IP " + (e.get("net") or {}).get("ip", "")) if e.get("net") else "")))
            for g in a.get("games") or []:
                print("  игра %s pid %s userNum %s: %s%s%s%s" % (g.get("server"), g.get("pid"), g.get("user_num"), "защищена" if g.get("protected") else "НЕ защищена",
                      (", срок " + g["deadline_at"]) if g.get("deadline_at") else "", (", решение %s (%s) %s" % (g.get("decided"), g.get("decided_code"), g.get("decided_why") or "")) if g.get("decided") else "",
                      (", IP " + (g.get("net") or {}).get("ip", "")) if g.get("net") else ""))
            for x in a.get("events") or []:
                print("    %s %-12s %s" % (x.get("at"), x.get("kind"), x.get("text")))
    print("  AsdaEacServer: %s" % (r["service"] or "—"))
    for f, x in r["p73"].items():
        print("  P73 %-16s Enabled=%s Mode=%s по журналу %s" % (f, x["enabled"], x["mode"], x["mode_log"]))
    print("  KICK: %s" % (r["summary"].get("kicks") or {}))
    print("  счётчики: %s" % (r["counters"] or "—"))
    for e in r["errors"]:
        print("  ! ошибка:", e)
    return 0


def _names(args):
    """★ А6.11: очередь имён (domains/namereview.py); отметка — операция names.mark (пишет только AsdaAdmin)."""
    from core import ops
    from domains import namereview
    if not args or args[0] not in NM_KEYS:
        raise SystemExit("names: нужно действие queue | marks | mark (help — ключи)")
    sub = args[0]
    opt = kv_args("names", NM_KEYS, sub, args[1:])
    if sub == "queue":
        r = namereview.queue({"from": opt.get("--from"), "to": opt.get("--to"), "all": "1" if opt.get("--all") else "0", "state": opt.get("--state"),
                              "account": opt.get("--account"), "svc": "in" if opt.get("--service-in") else "sep", "page": opt.get("--page"),
                              "size": opt.get("--size")})
        print("период %s — %s: в очереди %d (страница %d из %d); итоги %s" % (r["from"], r["to"], r["total"], r["page"], r["pages"], r["totals"]))
        for it in r["rows"]:
            print("  №%-7s %-3s %-16s %-20s %-6s %-7s %s" % (it["uid"], it["idx"], it.get("login") or "", it["name"] or "—", it["rule"], it["state"],
                                                          it["why"] or ""))
        for n in r["notes"]:
            print("  ·", n)
        for e in r["errors"]:
            print("  ! ошибка:", e)
        return 0
    if not opt.get("--uid") or opt.get("--idx") is None:
        raise SystemExit("names %s: нужны --uid N и --idx N" % sub)
    if sub == "marks":
        for m in namereview.marks_of(opt["--uid"], opt["--idx"]):
            print("  №%-5s %s %-20s %-7s %-6s %s %s" % (m["id"], m["at"], m["name"], m["verdict"], m["rule_at_mark"], m["by"], m["note_text"]))
        return 0
    if opt.get("--verdict") not in namereview.VERDICTS:
        raise SystemExit("names mark: --verdict ok | rename")
    p = {"uid": opt["--uid"], "idx": opt["--idx"], "verdict": opt["--verdict"], "note": opt.get("--note") or ""}
    r = ops.run(_cli_ctx(), "names.mark", p, dry=bool(opt.get("--dry")))
    if r["dry"]:
        print("предпросмотр:", r["preview"]["text"])
        for w in r["preview"].get("warnings") or []:
            print("  ·", w)
        return 0
    print(r["message"], "(журнал №%s)" % r["audit_id"])
    return 0


def _reports(args):
    """★ А6.11: жалобы игроков из бота Discord (domains/reports.py); просмотр — без записи, действия — операции report.* от имени учётки панели."""
    from core import ops
    from domains import reports
    if not args or args[0] not in RP_KEYS:
        raise SystemExit("reports: нужно действие list | show | take | close | case | reply (help — ключи)")
    sub = args[0]
    opt = kv_args("reports", RP_KEYS, sub, args[1:])
    if sub == "list":
        r = reports.report_list({"status": opt.get("--status"), "category": opt.get("--category"), "target": opt.get("--target"),
                                 "reporter": opt.get("--reporter"), "page": opt.get("--page"), "size": opt.get("--size")})
        print("жалоб по фильтру %d (страница %d из %d); новых %d, в работе %d, закрытых %d" % (
            r["total"], r["page"], r["pages"], r["counts"]["new"], r["counts"]["taken"], r["counts"]["closed"]))
        for x in r["rows"]:
            print("  №%-6s %-6s %-5s %-20s %-24s %s %s %s" % (x["id"], x["status"], x["category"], x["target"], x["reporter_name"], x["created"],
                                                         x["taken_by"] or "", x["outcome"] or ""))
        return 0
    if not opt.get("--id"):
        raise SystemExit("reports %s: нужен --id N" % sub)
    if sub == "show":
        x = reports.show(opt["--id"])
        print("жалоба №%s: %s, %s на «%s», подана %s UTC, автор %s (Discord ID %s)" % (x["id"], x["status"], x["category"], x["target"], x["created"],
                                                                                 x["reporter_name"], x["reporter_id"]))
        print("  когда:", x["happened"] or "—")
        print("  описание:", x["body"])
        for ln in x["links"]:
            print("  ссылка:", ln["url"], "" if ln["ok"] else "(не по правилам)")
        for f in x["files"]:
            print("  скриншот №%s %s %s %d байт sha256 %s" % (f["id"], f["name"], f["mime"], f["size"], f["sha256"]))
        for t in x["targets"]:
            print("  цель: учётка №%s %s, персонаж %s/%s %s%s" % (t["uid"], t["login"] or "", t["uid"], t["idx"], t["name"], " (удалён)" if t["deleted"] else ""))
        rp = x["reporter"]
        print("  автор ↔ учётка:", ("%s (№%s)" % (rp["login"], rp["uid"])) if rp.get("linked") else "не привязан")
        print("  ведёт: %s · итог: %s %s · дело: %s" % (x["taken_by"] or "—", x["outcome"] or "—", x["outcome_note"] or "", x["case_no"] or "—"))
        for y in x["replies"]:
            print("  ответ №%s %s %s: %s" % (y["id"], y["by"], y["state"], y["text"]))
        for e in x["errors"]:
            print("  ! ошибка:", e)
        return 0
    if not opt.get("--as"):
        raise SystemExit("reports %s: действия с жалобами — от имени учётки панели: --as <логин панели>" % sub)
    p = {"id": opt["--id"]}
    if sub == "close":
        if opt.get("--outcome") not in reports.OUTCOMES:
            raise SystemExit("reports close: --outcome %s" % " | ".join(reports.OUTCOMES))
        p.update(outcome=opt["--outcome"], note=opt.get("--note") or "")
    elif sub == "case":
        p["case"] = opt.get("--case") or ""
    elif sub == "reply":
        p["text"] = (opt.get("--text") or "").replace("\\n", "\n")
    ctx = _cases_ctx(opt["--as"])
    r = ops.run(ctx, "report." + sub, p, dry=bool(opt.get("--dry")))
    if r["dry"]:
        print("предпросмотр:", r["preview"]["text"])
        for w in r["preview"].get("warnings") or []:
            print("  ·", w)
        return 0
    print(r["message"], "(журнал №%s)" % r["audit_id"])
    return 0


# ★ А6.12 (22.11): «chat <действие>» — ключи; действия (mute, unmute, undo) — только от имени учётки панели (--as)
CH_KEYS = {"log": {"--from": True, "--to": True, "--channel": True, "--account": True, "--char": True, "--char-uid": True, "--char-slot": True,
                   "--text": True, "--map": True, "--server": True, "--mute": True, "--mute-id": True, "--raw": False, "--page": True, "--size": True},
           "mutes": {"--state": True, "--account": True, "--page": True, "--size": True},
           "mute": {"--uid": True, "--login": True, "--slot": True, "--char": True, "--minutes": True, "--reason": True, "--as": True, "--dry": False},
           "unmute": {"--mute-id": True, "--reason": True, "--as": True, "--dry": False},
           "undo": {"--audit": True, "--as": True}}


def _chat(args):
    """★ А6.12: журнал чата и заглушки (domains/chatlog.py); просмотр — без записи, действия — операции chat.mute / chat.unmute и их откат
    (ops.undo) от имени учётки панели. Ошибки ключей — SystemExit без обращения к базе."""
    from core import ops
    from domains import chatlog
    if not args or args[0] not in CH_KEYS:
        raise SystemExit("chat: нужно действие log | mutes | mute | unmute | undo (help — ключи)")
    sub = args[0]
    opt = kv_args("chat", CH_KEYS, sub, args[1:])
    if sub == "log":
        r = chatlog.messages({"from": opt.get("--from"), "to": opt.get("--to"), "channel": opt.get("--channel"), "account": opt.get("--account"),
                              "char": opt.get("--char"), "char_uid": opt.get("--char-uid"), "char_slot": opt.get("--char-slot"), "text": opt.get("--text"),
                              "map": opt.get("--map"), "server": opt.get("--server"), "mute": opt.get("--mute"), "mute_id": opt.get("--mute-id"),
                              "raw": "1" if opt.get("--raw") else "", "page": opt.get("--page"), "size": opt.get("--size")}, user="console")
        if not r["installed"]:
            print(r["note"])
            return 0
        print("сообщений по фильтру %d%s (страница %d из %d)%s" % (r["total"], "+" if r["more"] else "", r["page"], r["pages"],
                                                                  "; без дат — последние %d суток" % r["default_days"] if r["default_days"] else ""))
        for x in r["rows"]:
            print("  №%-8s %s %-16s карта %-4s %-14s учётка №%s %s персонаж %s/%s %s%s%s: %s" % (
                x["id"], x["local"], x["server"], x["map"], x["channel_title"], x["uid"], x["login"] or "", x["owner"], x["slot"], x["char"] or "",
                (" → " + x["to"]) if x["to"] else "", (" [%s №%s]" % (x["mute_title"], x["mute_id"])) if x["mute_state"] else "", x["chat_text"]))
            if x.get("raw"):
                print("      байты (%d): %s | cp1251: %s | utf-8: %s | cp1256: %s" % (x["raw"]["len"], x["raw"]["hex"], x["raw"]["cp1251"],
                                                                                   x["raw"]["utf8"], x["raw"]["cp1256"]))
        for e in r["errors"]:
            print("  ! ошибка:", e)
        return 0
    if sub == "mutes":
        r = chatlog.mutes({"state": opt.get("--state"), "account": opt.get("--account"), "page": opt.get("--page"), "size": opt.get("--size")})
        if not r["installed"]:
            print(r["note"])
            return 0
        print("заглушек по фильтру %d (страница %d из %d); действуют %d, истекли %d, сняты %d" % (
            r["total"], r["page"], r["pages"], r["counts"]["active"], r["counts"]["expired"], r["counts"]["lifted"]))
        for x in r["rows"]:
            print("  №%-6s %-8s %-9s учётка №%s %s%s до %s UTC, поставил %s %s: %s%s" % (
                x["id"], x["state"], x["scope_title"], x["uid"], x["login"] or "", (" слот %s %s" % (x["slot"], x["char"] or "")) if x["scope"] == 2 else "",
                x["until"], x["by"], x["created"], x["reason"], (" · снял %s %s: %s" % (x["lifted_by"], x["lifted"], x["lift_reason"] or "")) if x["lifted"] else ""))
        return 0
    if not opt.get("--as"):
        raise SystemExit("chat %s: действия с заглушками — от имени учётки панели: --as <логин панели>" % sub)
    if sub == "undo":
        if not str(opt.get("--audit") or "").isdigit():
            raise SystemExit("chat undo: --audit N — номер записи журнала панели (операции chat.mute или chat.unmute)")
        from core import audit
        row = audit.get(int(opt["--audit"]))
        if not row or row["action"] not in ("chat.mute", "chat.unmute"):
            raise SystemExit("chat undo: запись №%s — не заглушка чата (chat.mute / chat.unmute)%s" % (opt["--audit"], "" if not row else ": %s" % row["action"]))
        r = ops.undo(_cases_ctx(opt["--as"]), int(opt["--audit"]))
        print(r["message"], "(журнал №%s)" % r["audit_id"])
        return 0
    if sub == "mute":
        if opt.get("--char") and (opt.get("--uid") or opt.get("--login")):
            raise SystemExit("chat mute: --char ИМЯ или --uid / --login (с --slot для персонажа) — не вместе")
        if not (opt.get("--char") or opt.get("--uid") or opt.get("--login")):
            raise SystemExit("chat mute: нужна цель — --uid N, --login Л (учётка; с --slot — персонаж) или --char ИМЯ")
        if not opt.get("--minutes") or not opt.get("--reason"):
            raise SystemExit("chat mute: нужны --minutes N и --reason ТЕКСТ")
        char = bool(opt.get("--char") or opt.get("--slot") is not None)
        p = {"scope": "char" if char else "account", "uid": opt.get("--uid"), "login": opt.get("--login"), "idx": opt.get("--slot"),
             "char": opt.get("--char"), "minutes": opt["--minutes"], "reason": opt["--reason"]}
    else:
        if not opt.get("--mute-id") or not opt.get("--reason"):
            raise SystemExit("chat unmute: нужны --mute-id N и --reason ТЕКСТ")
        p = {"mute_id": opt["--mute-id"], "reason": opt["--reason"]}
    p = {k: v for k, v in p.items() if v is not None}
    ctx = _cases_ctx(opt["--as"])
    r = ops.run(ctx, "chat." + sub, p, dry=bool(opt.get("--dry")))
    if r["dry"]:
        print("предпросмотр:", r["preview"]["text"])
        for w in r["preview"].get("warnings") or []:
            print("  ·", w)
        return 0
    print(r["message"], "(журнал №%s)" % r["audit_id"])
    return 0


# ★ А6.7: «cases <действие>» — ключи (True — со значением; списочные — повторяемые)
CS_KEYS = {"list": {"--status": True, "--account": True, "--training": True}, "show": {}, "ladder": {}, "verify": {},
           "open": {"--uid": True, "--login": True, "--title": True, "--char": True, "--hypothesis": True, "--training": False, "--dry": False},
           "attach": {"--event": True, "--from": True, "--to": True, "--log": True, "--needle": True, "--label": True, "--note": True, "--dry": False},
           "export": {"--format": True, "--dry": False},
           "rollback-report": {"--serial": True, "--from": True, "--to": True, "--max": True, "--dry": False},
           "decide": {"--step": True, "--text": True, "--hours": True, "--reason-en": True, "--override-two-sources": True, "--confirm": True,
                      "--dry": False},
           "execute": {"--text": True, "--dry": False}, "withdraw": {"--text": True, "--dry": False},
           "lift": {"--text": True, "--all-blocks": False, "--confirm": True, "--dry": False},
           "appeal": {"--text": True, "--who": True, "--late": True, "--resolve": True, "--dry": False},
           "close": {"--outcome": True, "--text": True, "--force-unverified": True, "--dry": False}}
CS_LISTS = ("--event", "--needle", "--serial")
for _s in CS_KEYS:                       # ★ ревизия 59 Н-3: действия — от имени учётки панели (--as <логин>)
    if _s not in ("list", "show", "ladder", "verify"):
        CS_KEYS[_s]["--as"] = True
CS_NO_CASE = ("list", "ladder", "open", "verify")


def cases_args(sub, args):
    """★ А6.7: позиционный номер дела + ключи → (номер | None, {ключ: значение | [значения]}); ошибки — SystemExit без обращения к базе."""
    keys = CS_KEYS[sub]
    no = None
    if args and not args[0].startswith("--"):
        no, args = args[0], args[1:]
    if no is None and sub not in CS_NO_CASE:
        raise SystemExit("cases %s: нужен номер дела AC-NNNN" % sub)
    if no is not None and sub in ("list", "ladder", "open"):
        raise SystemExit("cases %s: номер дела не нужен" % sub)
    opt, i = {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("cases %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys) or "—"))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("cases %s: у ключа %s нет значения" % (sub, a))
            if a in CS_LISTS:
                opt.setdefault(a, []).append(args[i + 1])
            else:
                opt[a] = args[i + 1]
            i += 2
            continue
        opt[a], i = True, i + 1
    return no, opt


def _cases_ctx(login):
    """★ ревизия 59 Н-3: действие с делом из консоли — от имени УЧЁТКИ ПАНЕЛИ (её роль и логин; «другое лицо» апелляции сверяется по ней).
    Без --as, учётки нет или она отключена — отказ до обращения к игровым базам."""
    from core import auth, db, ops
    if not login:
        raise SystemExit("cases: действия с делами — от имени учётки панели: --as <логин панели>")
    cn = db.admin()
    try:
        u = auth.get_user(cn, login=login)
    finally:
        cn.close()
    if not u or u.get("disabled"):
        raise SystemExit("cases: учётки панели %s нет или она отключена" % login)
    return ops.Ctx(u["id"], u["login"], u["role"], "", "cli")


def _cases(args):
    """★ А6.7: дела античита (domains/cases.py); действия — операции case.* (журнал adm.audit), просмотр — без записи."""
    from core import ops
    from domains import cases
    if not args or args[0] not in CS_KEYS:
        raise SystemExit("cases: нужно действие %s (help — ключи)" % " | ".join(CS_KEYS))
    sub = args[0]
    no, opt = cases_args(sub, args[1:])
    ctx = _cli_ctx()
    if sub == "list":
        r = cases.case_list(ctx, {"status": opt.get("--status"), "account": opt.get("--account"), "training": opt.get("--training")})
        for c in r["rows"]:
            print("%-8s %-9s №%-7s %-16s ступень %-4s итог %-11s событий %-4s файлов %-4s блоков %s(%s) %s%s" % (
                c["case_no"], c["status"], c["user_index"], c["login"] or "", "" if c["ladder_step"] is None else c["ladder_step"],
                c["outcome"] or "", c["n_events"], c["n_evidence"], c["n_blocks"], c["n_blocks_active"], c["title"], " [учебное]" if c["is_training"] else ""))
        print("дел: %d%s" % (len(r["rows"]), " (показаны последние)" if r["more"] else ""))
        return 0
    if sub == "show":
        print(cases.show(ctx, no)["md"])
        return 0
    if sub == "ladder":
        L = cases.ladder(ctx)
        for x in L["ladder"]:
            print("  %d %-12s %-26s срок %-5s исполнение %-7s %s" % (x["step"], x["code"], x["name"], "" if x["hours"] is None else x["hours"],
                                                                 x["exec"], x["mechanism"]))
        print("апелляция %s дн., хранение >= %s дн., два источника со ступени %s, файл до %s МБ; хранилище: %s" % (
            L["appeal_days"], L["retention_days"], L["two_sources_from_step"], L["max_file_mb"], L["store"] or L["store_note"]))
        return 0
    if sub == "verify":
        r = cases.verify(ctx, no)
        for c in r["cases"]:
            for ln in c["lines"]:
                print(ln)
        print("ИТОГ verify: дел %d, с ошибками %d%s" % (len(r["cases"]), len(r["bad"]), (": " + ", ".join(r["bad"])) if r["bad"] else ""))
        return 1 if r["bad"] else 0
    g = lambda k: opt.get(k)     # noqa: E731
    ctx = _cases_ctx(g("--as"))
    p = {"case": no} if no else {}
    if sub == "open":
        p.update({"uid": g("--uid"), "login": g("--login"), "title": g("--title"), "char": g("--char"), "hypothesis": g("--hypothesis"),
                  "training": bool(g("--training"))})
    elif sub == "attach":
        p.update({"events": g("--event"), "from": g("--from"), "to": g("--to"), "label": g("--label"), "note": g("--note")})
        if g("--log"):
            parts = g("--log").split("/")
            if len(parts) not in (3, 4):
                raise SystemExit("cases attach: --log ИСТОЧНИК/КОПИЯ[/ВИД]/ФАЙЛ (как в «Журналах стойки»)")
            p["log"] = {"source": parts[0], "proc": parts[1], "name": parts[-1], "kind": parts[2] if len(parts) == 4 else None}
            p["needles"] = g("--needle")
    elif sub == "export":
        p["format"] = g("--format")
    elif sub == "rollback-report":
        p.update({"serials": g("--serial"), "from": g("--from"), "to": g("--to")})
        if g("--max"):
            p["max"] = g("--max")
    elif sub == "decide":
        p.update({"step": g("--step"), "text": g("--text"), "hours": g("--hours"), "reason_en": g("--reason-en"),
                  "override_two_sources": g("--override-two-sources"), "confirm": g("--confirm")})
    elif sub in ("execute", "withdraw"):
        p["text"] = g("--text")
    elif sub == "lift":
        p.update({"text": g("--text"), "all_blocks": bool(g("--all-blocks")), "confirm": g("--confirm")})
    elif sub == "appeal":
        p.update({"text": g("--text"), "who": g("--who"), "late": g("--late"), "resolve": g("--resolve")})
    elif sub == "close":
        p.update({"outcome": g("--outcome"), "text": g("--text"), "force_unverified": g("--force-unverified")})
    p = {k: v for k, v in p.items() if v not in (None, False, [])}
    name = "case." + sub.replace("-", "_")
    r = ops.run(ctx, name, p, dry=bool(g("--dry")))
    if r["dry"]:
        for ln in r["preview"].get("case_lines") or [r["preview"].get("text")]:
            print(ln if ln.startswith("предпросмотр") else "предпросмотр: " + ln)
        return 0
    for ln in (r.get("result") or {}).get("case_lines") or []:
        print(ln)
    print("готово (журнал №%s)" % r["audit_id"])
    return 0


ACD_KEYS = {"list": {"--day": True}, "show": {"--id": True, "--day": True}, "md": {"--id": True, "--day": True},
            "events": {"--metric": True, "--id": True, "--day": True, "--page": True, "--size": True},
            "run": {"--date": True, "--days": True, "--thr": True, "--dry": False}}


def acdaily_args(sub, args):
    """★ А6.6: ключи «acdaily <действие>» → {ключ: значение} (--thr — список «КЛЮЧ=ЗНАЧЕНИЕ»); неизвестный ключ, ключ без значения,
    позиционный аргумент — SystemExit (без обращения к базе и журналам)."""
    keys, opt, i = ACD_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("acdaily %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys)))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("acdaily %s: у ключа %s нет значения" % (sub, a))
            if a == "--thr":
                k, sep, v = args[i + 1].partition("=")
                if not sep or not k:
                    raise SystemExit("acdaily run: порог — КЛЮЧ=ЗНАЧЕНИЕ (например m5_burst_n=3)")
                opt.setdefault("thr", {})[k] = v
            else:
                opt[a[2:]] = args[i + 1]
            i += 2
            continue
        opt[a[2:]], i = True, i + 1
    return opt


def _acdaily(args):
    """★ А6.6: суточный отчёт античита (domains/acdaily.py). Консоль — роль владельца: IP видны."""
    from core import ops
    from domains import acdaily
    if not args or args[0] not in ACD_KEYS:
        raise SystemExit("acdaily: нужно действие %s" % " | ".join(ACD_KEYS))
    sub = args[0]
    opt = acdaily_args(sub, args[1:])
    if sub == "run":
        p = {k: opt[k] for k in ("date", "days", "thr") if k in opt}
        r = ops.run(_cli_ctx(), "ac.daily", p, dry=bool(opt.get("dry")))
        if r["dry"]:
            print(r["preview"]["text"])
            for w in r["preview"].get("warnings") or []:
                print("  !", w)
        else:
            print(r["message"])
        return 0
    if sub == "list":
        r = acdaily.reports(opt)
        print("служба считает отчёт за вчера в %s; ручных прогонов — не больше %d в час на пользователя" % (r["run_at"], r["runs_per_hour"]))
        for x in r["reports"]:
            win = x["day_to"] if x["days"] == 1 else "%s–%s" % (x["day_from"], x["day_to"])
            print("  №%-5d %-17s %s  %-22s %-5s флагов вне %3d / фон %3d  ошибок %d  нет данных %d  %s%s" % (
                x["id"], win, str(x["made_local"])[:19], x["by"], x["via"], x["flags_out"], x["flags_bg"], x["errors"], x["nodata"],
                "%.1f с" % (x["elapsed_ms"] / 1000.0), ("  пороги " + ", ".join("%s=%s" % kv for kv in sorted(x["thr_over"].items()))) if x["thr_over"] else ""))
        return 0
    q = {k: opt[k] for k in ("id", "day", "metric", "page", "size") if k in opt}
    if sub == "md":
        print(acdaily.markdown(q)["md"])
        return 0
    if sub == "events":
        r = acdaily.events(q)
        print("отчёт №%d, %s: событий %d (страница %d из %d)" % (r["id"], r["metric"], r["total"], r["page"], r["pages"]))
        for e in r["rows"]:
            print("  " + " | ".join(str(x) for x in e))
        return 0
    r = acdaily.report(q)
    mt = r["meta"]
    print("отчёт №%d за %s (%d сут.), сформирован %s (%s, %s), прогон %.1f с, журналов %d (%d байт), код %s%s" % (
        r["id"], r["day_to"] if r["days"] == 1 else "%s–%s" % (r["day_from"], r["day_to"]), r["days"], str(r["made_local"])[:19], r["by"],
        r["via"], r["elapsed_ms"] / 1000.0, r["log_files"], r["log_bytes"], r["code_md5"][:8],
        "" if r["code_md5"] == r["code_now"] else " (сейчас выложен другой код %s)" % r["code_now"][:8]))
    print("список владельца (regex): %s" % mt["owner_re"])
    print("  %-5s %7s %9s %14s  %-11s %s" % ("метр.", "всего", "субъектов", "флагов вне/фон", "вне влад.", "статус"))
    for m in r["metrics"]:
        s = m["summary"]
        print("  %-5s %7s %9s %14s  %-11s %s" % (s[0], s[1], s[2], s[6], s[5], s[7]))
    print("флаги вне списка владельца:")
    n = 0
    for m in r["metrics"]:
        for f in m["flags"]:
            if not f[2]:
                n += 1
                print("  %-5s %s — %s" % (m["mid"], f[0] or "?", f[1]))
    if not n:
        print("  нет")
    print("фон владельца (справочно):")
    for m in r["metrics"]:
        b = sum(1 for f in m["flags"] if f[2])
        if b:
            print("  %-5s %d флагов; по нику: %s" % (m["mid"], b, ", ".join("%s: %d" % (x[0], x[1]) for x in m["bg_top"])))
    return 0


_MONEY_COMMON = {"--account": True, "--from": True, "--to": True, "--page": True, "--size": True}
MONEY_KEYS = {"summary": {"--service-in": False, "--minutes": True},
              "purchases": dict(_MONEY_COMMON, **{"--code": True, "--kind": True, "--who": True, "--test": True, "--service-in": False}),
              "gifts": dict(_MONEY_COMMON, **{"--state": True, "--test": True, "--hanging": False, "--minutes": True}),
              "holds": {"--minutes": True, "--window": True},
              "sales": {"--from": True, "--to": True, "--who": True, "--service-in": False},
              "accounts": {"--account": True, "--who": True, "--page": True, "--size": True},
              "undelivered": {"--who": True, "--from": True, "--to": True, "--minutes": True, "--service-in": False, "--no-logs": False},
              # ★ А6.9 (22.11): журнал корректировок (чтение) и корректировка / откат — от имени учётки панели (--as, как cases)
              "adjustments": {"--account": True, "--page": True, "--size": True},
              "adjust": {"--login": True, "--kind": True, "--amount": True, "--reason": True, "--confirm-amount": True, "--confirm-login": True,
                         "--req": True, "--expect-before": True, "--as": True, "--dry": False},
              "undo": {"--audit": True, "--as": True}}
MONEY_OPS = ("adjust", "undo")           # ★ А6.9: действия с записью — разбор ключей своими правилами (_money_op)


def money_args(sub, args):
    """★ А6.2: ключи «money <действие>» → строка запроса домена; неизвестный ключ, ключ без значения, позиционный аргумент — SystemExit."""
    keys, q, i = MONEY_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("money %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys)))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("money %s: у ключа %s нет значения" % (sub, a))
            q[a[2:]], i = args[i + 1], i + 2
            continue
        q.update({"--service-in": {"svc": "in"}, "--hanging": {"hanging": "1"}, "--no-logs": {"logs": "0"}}[a])
        i += 1
    return q


def _money_op(sub, args):
    """★ А6.9: корректировка баланса gp7 (операция money.adjust) и её откат (ops.undo) — от имени УЧЁТКИ ПАНЕЛИ (--as <логин>, роль owner;
    как cases, ревизия 59 Н-3); второе подтверждение — --confirm-amount и --confirm-login (сумма и логин сайта набраны заново); --dry —
    предпросмотр без записи. Ошибки ключей — SystemExit без обращения к базе."""
    import uuid
    from core import ops
    keys, opt, i = MONEY_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("money %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys)))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("money %s: у ключа %s нет значения" % (sub, a))
            opt[a], i = args[i + 1], i + 2
            continue
        opt[a], i = True, i + 1
    if not opt.get("--as"):
        raise SystemExit("money %s: действия с балансом gp7 — от имени учётки панели: --as <логин панели>" % sub)
    if sub == "undo":
        if not str(opt.get("--audit") or "").isdigit():
            raise SystemExit("money undo: --audit N — номер записи журнала панели (операции money.adjust)")
        from core import audit
        row = audit.get(int(opt["--audit"]))           # ★ ревизия 63 М-1: здесь — только откат корректировки баланса
        if not row or row["action"] != "money.adjust":
            raise SystemExit("money undo: запись №%s — не корректировка баланса gp7 (money.adjust)%s" % (
                opt["--audit"], "" if not row else ": %s" % row["action"]))
        r = ops.undo(_cases_ctx(opt.get("--as")), int(opt["--audit"]))
        print(r["message"])
        print("готово (журнал №%s)" % r["audit_id"])
        return 0
    ctx = _cases_ctx(opt.get("--as"))
    p = {"login": opt.get("--login"), "kind": opt.get("--kind"), "amount": opt.get("--amount"), "reason": opt.get("--reason"),
         "confirm_amount": opt.get("--confirm-amount"), "confirm_login": opt.get("--confirm-login"), "req": opt.get("--req") or str(uuid.uuid4())}
    p = {k: v for k, v in p.items() if v is not None}
    if opt.get("--expect-before") is not None:          # ★ ревизия 63 М-2: «было», которое оператор видел в --dry
        if not str(opt["--expect-before"]).isdigit():
            raise SystemExit("money adjust: --expect-before N — баланс «было» из предпросмотра (целое)")
        p["expect"] = {"balance": int(opt["--expect-before"])}
    r = ops.run(ctx, "money.adjust", p, dry=bool(opt.get("--dry")))
    pv = r["preview"] or {}
    if r["dry"]:
        print("предпросмотр: " + pv.get("text", ""))
        print("  сутки (часы сервера): %s из %s после этой; ключ запроса %s" % (pv.get("day_used"), pv.get("day_max"), pv.get("req")))
        for w in pv.get("warnings") or []:
            print("  ! " + w)
        print("  применить: тот же вызов без --dry с --req %s --expect-before %s --confirm-amount %s --confirm-login %s" % (
            pv.get("req"), pv.get("balance_before"), pv.get("amount"), (pv.get("account") or {}).get("username")))
        return 0
    print(r["message"])
    print("готово (журнал №%s)" % r["audit_id"])
    return 0


def _cat_ru(c):
    """Категория учётки для печати."""
    return {"player": "игрок", "service": "служебная", "nolink": "без игровой"}.get(c, c)


def _money(args):
    """★ А6.2: деньги gp7 — только чтение (domains/money.py)."""
    from domains import money
    if not args or args[0] not in MONEY_KEYS:
        raise SystemExit("money: нужно действие %s (help — ключи)" % " | ".join(MONEY_KEYS))
    sub = args[0]
    if sub in MONEY_OPS:
        return _money_op(sub, args[1:])
    q = money_args(sub, args[1:])
    if sub == "adjustments":
        from domains import gp7adjust
        r = gp7adjust.adjustments(q)
        if r.get("day"):
            print("сутки %s (часы сервера): корректировок %d, сумма %d из %d (осталось %d); за операцию — до %d" % (
                r["day"]["day"], r["day"]["n"], r["day"]["used"], r["day_max"], r["day"]["left"], r["op_max"]))
        if r.get("tfb_warning"):
            print("  ! " + r["tfb_warning"])
        print("корректировок %d (страница %d из %d); это не выручка — в журнал покупок gp7 не входят" % (r["total"], r["page"], r["pages"]))
        for x in r["rows"]:
            print("  №%-6s %s  %-16s №%-7s %+8d  %8d → %-8d %-10s %s%s%s" % (
                x["id"], x["created_local"], x["username"], x["Userindex"] or "—", x["delta"], x["balance_before"], x["balance_after"],
                x["operator"], x["reason"], "  [откат №%s]" % x["undo_of"] if x["undo_of"] else "",
                "  [откачено №%s]" % x["undone_by"] if x["undone_by"] else ""))
        for e in r["errors"]:
            print("  ! ошибка:", e)
        return 0
    if sub == "summary":
        s = money.summary(q)
        print("testFixedBalance шлюза: %s" % ("не прочитан" if s["test_fixed_balance"] is None else s["test_fixed_balance"]))
        p = s["purchases"]
        if p:
            print("покупки gp7 (%s — %s, часы сервера): строк / списано / возвращено / итого:" % (s["first"], s["last"]))
            for c in money.WHO:
                x = p["cats"][c]
                print("  %-12s %6d  %14d  %10d  %14d  отказов %d  возвратов %d  тестовых подарков %d%s" % (
                    _cat_ru(c), x["n"], x["gross"], x["refunded"], x["sum"], x["fails"], x["refunds"], x["test_gifts"],
                    "" if money._in_total(c, s["svc"]) else "  (не в общем итоге)"))
            print("  %-12s %6d  %14d  %10d  %14d" % ("ОБЩИЙ ИТОГ", p["total"]["n"], p["total"]["gross"], p["total"]["refunded"], p["total"]["sum"]))
        for gft in s["gifts"]:
            print("подарки: состояние %s%s — %d шт., %d" % (gft["state"], " (тест)" if gft["test_mode"] else "", gft["n"], gft["s"] or 0))
        print("висящих 'H' старше %d мин: %s" % (s["minutes"], s["hanging"]))
        for st in s["stock"]:
            print("сток %-15s строк %6d  сумма %d (как записал сток, в итог gp7 не входит)" % (st["table"], st["n"], st["sum"]))
    elif sub == "purchases":
        r = money.purchases(q)
        print("строк %d (страница %d из %d по %d)" % (r["total"], r["page"], r["pages"], r["size"]))
        if r["totals"]:
            print("  по фильтру: %s; общий итог%s: %d строк, %d" % (
                ", ".join("%s %d / %d" % (_cat_ru(c), r["totals"]["cats"][c]["n"], r["totals"]["cats"][c]["sum"]) for c in money.WHO),
                "" if r["totals"]["service_in_total"] else " (служебные отдельно)", r["totals"]["total"]["n"], r["totals"]["total"]["sum"]))
        for x in r["rows"]:
            print("  №%-7s %s  %-6s %-11s %-16s №%-7s %6s  %-6s %8d  %s%s" % (
                x["id"], x["created_local"], x["kind"], _cat_ru(x["cat"]), x["site_login"] or "—", x["Userindex"] or "—", x["item_code"],
                x["pos"]["delivery"] or "", x["amount"], x["pos"]["name"] or "", "  [тест]" if x["test"] else ""))
    elif sub == "gifts":
        r = money.gifts(q)
        print("подарков %d (страница %d из %d)" % (r["total"], r["page"], r["pages"]))
        for x in r["rows"]:
            print("  заказ %-7s %s  %s%s  %s → %s  %d  %s%s" % (x["order_id"], x["created_local"], x["state"], " тест" if x["test_mode"] else "",
                                                             x["sender_name"], x["recipient_name"], x["amount"],
                                                             ", ".join("%d %s" % (i["code"], i["name"]) for i in x["items"]),
                                                             "  [висит]" if x["hanging"] else ""))
    elif sub == "holds":
        r = money.holds(q)
        print("висящие 'H' старше %d мин (окно ±%d с; всего 'H' %s): %d" % (r["minutes"], r["window"], (r["counts"] or {}).get("H"), len(r["holds"])))
        for h in r["holds"]:
            print("  заказ %d [%s] возраст %d мин, сумма %d%s — %s → %s (UserIndex %s): %s" % (
                h["order_id"], h["hint"], h["age_min"], h["amount"], "  (test_mode: возврат меняет только state)" if h["test_mode"] else "",
                h["sender_name"], h["recipient_name"], h["r_userindex"] or "—", h["hint_why"]))
    elif sub == "sales":
        r = money.sales(q)
        if r.get("period"):
            print("период %s — %s (сутки по часам SQL-сервера)" % (r["period"]["from"], r["period"]["to"]))
        for d in r["days"]:
            print("  %s  покупок %4d  сумма %10d  (служебные %d / %d)" % (d["day"], d["total"]["n"], d["total"]["sum"], d["cats"]["service"]["n"],
                                                                       d["cats"]["service"]["sum"]))
        for c in r["codes"]:
            print("  код %-6s %-40s %5d  %10d  учёток %d" % (c["item_code"], c["pos"]["name"] or "", c["total_n"], c["total_s"], c["users"]))
        if r["cross"]:
            print("сверка заказов gp7 со стоком своей процедуры: gp7 %(gp7_orders)d; CashUse %(stock_orders)d (сведено %(both)d); SaleHair %(hair_orders)s "
                  "(сведено %(hair_both)d); только gp7 %(gp7_only)d (в ящике ItemPostbox %(in_postbox)s); только сток %(stock_only)d" % r["cross"])
    elif sub == "undelivered":
        r = money.undelivered(q, "console")
        t = r["totals"]
        if t:
            print("оплачено, не выдано (заказы gp7 без строки стока своей процедуры и без ящика; моложе %d мин не сверяются; в ящике сейчас %d):"
                  % (r["minutes"], r["in_postbox"]))
            for c in money.WHO:
                x = t["cats"][c]
                print("  %-12s %5d / %10d   сверка по номеру неприменима: %5d / %10d%s" % (
                    _cat_ru(c), x["n"], x["sum"], x["na_n"], x["na_sum"], "" if money._in_total(c, t["svc"]) else "  (не в общем итоге)"))
            print("  %-12s %5d / %10d   неприменима: %5d / %10d" % ("ОБЩИЙ ИТОГ", t["total"]["n"], t["total"]["sum"], t["total"]["na_n"], t["total"]["na_sum"]))
        if r.get("cutoff"):
            print("первый номер gp7 в CashUse: №%s (%s, часы сервера) — раньше сверка по номеру неприменима" % (r["cutoff"]["id"], r["cutoff"]["local"]))
        print("причины: A %(A)d, B %(B)d, не установлена %(unknown)d, неприменима %(na)d" % r["by_reason"] if r["logs"] else "причины не разбирались (--no-logs)")
        for x in r["rows"]:
            print("  №%-7s %s  %-11s %-16s №%-7s %6s %8d  %-8s %s" % (
                x["id"], x["created_local"], _cat_ru(x["cat"]), x["site_login"] or "—", x["Userindex"] or "—", x["item_code"], x["amount"],
                {"A": "A", "B": "B", "unknown": "не уст.", "na": "неприм."}.get(x["reason"], "—"), x["reason_why"] or ""))
        if r["capped"]:
            print("  … показаны %d новых из %d" % (len(r["rows"]), r["total"]))
    else:
        r = money.accounts(q)
        print("учёток сайта %d (страница %d из %d); игровых без строки сайта: %s" % (r["total"], r["page"], r["pages"], r["game_without_site"]))
        for x in r["rows"]:
            print("  сайт №%-4s %-18s игра №%-7s %-18s %-11s баланс %-8s покупок %-5s %s" % (
                x["id"], x["username"], x["Userindex"] or "—", x["Us_id"] or "—", _cat_ru(x["cat"]), x["balance"], x["purchases"], x["spent"] or 0))
    for e in r["errors"] if sub != "summary" else s["errors"]:
        print("  ! ошибка:", e)
    return 0


ECON_KEYS = {"summary": {"--service-in": False}, "flows": {"--from": True, "--to": True, "--source": True, "--service-in": False},
             "richest": {"--n": True, "--service-in": False}, "rare": {"--n": True, "--service-in": False},
             "unaccounted": {"--id": True, "--service-in": False}, "snapshot": {}}


def econ_args(sub, args):
    """★ А6.3: ключи «econ <действие>» → строка запроса домена; неизвестный ключ, ключ без значения, позиционный аргумент — SystemExit."""
    keys, q, i = ECON_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("econ %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys) or "—"))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("econ %s: у ключа %s нет значения" % (sub, a))
            q[a[2:]], i = args[i + 1], i + 2
            continue
        q["svc"] = "in"
        i += 1
    return q


def _gold_cell(x):
    """Ячейка потока: строк, поступило, списано, итог."""
    return "строк %d, +%d, -%d, итог %+d" % (x["n"], x["inflow"], x["outflow"], x["delta"])


def _econ(args):
    """★ А6.3: экономика — золото (domains/econ.py): чтение игровых баз; snapshot пишет только AsdaAdmin."""
    from core import ops
    from domains import econ
    if not args or args[0] not in ECON_KEYS:
        raise SystemExit("econ: нужно действие %s" % " | ".join(ECON_KEYS))
    sub = args[0]
    q = econ_args(sub, args[1:])
    if sub == "snapshot":
        r = ops.run(_cli_ctx(), "econ.snapshot", {})
        print(r["message"])
        return 0
    econ.check_input(q, sub)
    r = getattr(econ, sub)(q)
    svc_note = lambda c: "" if econ._in_total(c, r["svc"]) else "  (не в общем итоге)"
    if sub == "summary":
        h = r["held"]
        if h:
            for c in econ.CATS:
                print("на руках %-10s %15d у %d персонажей%s" % (_cat_ru(c), h["cats"][c]["sum"], h["cats"][c]["chars"], svc_note(c)))
            print("на руках итого     %15d (часы сервера %s)" % (h["total"]["sum"], str(h["at"])[:19]))
        print("снимков: %d%s" % (r["snapshots"], (", последний №%s %s: %d" % (r["last"]["id"], str(r["last"]["taken_local"])[:19], r["last"]["total"]))
                                 if r["last"] else ""))
        if r["pair"]:
            t = r["pair"]["total"]
            print("неучтённое №%s → №%s: снимок %+d, журналы %+d, неучтённое %+d" % (r["pair"]["from_id"], r["pair"]["to_id"], t["snap"], t["journal"],
                                                                                 t["unaccounted"]))
        print("источники (дельта = Ramount − Amount, владелец — столбец):")
        for x in r["sources"]:
            if not x.get("read"):
                print("  %-22s не прочитан" % x["key"])
                continue
            print("  %-22s %s %-10s %s%s  — %s" % (x["key"], x["sign"], x["owner"], _gold_cell(x["total"]),
                                                 ("  ПРОТИВ ЗНАКА %d" % x["against"]) if x["against"] else "", x["title"]))
        for x in r["skipped"]:
            print("  не считается %-20s строк %s — %s" % (x["table"], x["rows"] if x["rows"] is not None else "?", x["why_text"]))
        for x in r["other"]:
            print("  вне каталога: %s — строк с золотом %d (знак не снят, не считается)" % (x["table"], x["rows"]))
        for x in r["sources"]:
            if x["key"] == "panel" and x.get("unknown"):
                print("  правки панели без суммы (восстановление, копия персонажа): %d" % x["unknown"])
        for x in r["unlogged"]:
            print("  без журнала (в неучтённое): %s — %s" % (x["title"], x["proc"]))
    elif sub == "flows":
        print("период %s — %s" % (r["period"]["from"], r["period"]["to"]) if r["period"] else "период не определён")
        for c in econ.CATS:
            print("  %-10s %s%s" % (_cat_ru(c), _gold_cell(r["cats"][c]), svc_note(c)))
        print("  итого      %s" % _gold_cell(r["total"]))
        for d in r["days"]:
            print("  %s  %s" % (d["day"], _gold_cell(d["total"])))
        for x in r["sources"]:
            if x.get("read") and x["total"]["n"]:
                print("  %-22s %s" % (x["key"], _gold_cell(x["total"])))
                for y in x.get("subs") or []:
                    print("      %-30s %s" % (y["sub"], _gold_cell(y["total"])))
    elif sub == "richest":
        for k in ("players", "service", "all"):
            for x in r[k]:
                print("  №%-7s %-3s %-18s %-16s ур.%-3s %-10s %15d" % (x["uid"], x["idx"], x["char"] or "—", x["login"] or "—", x["lvl"] or "—",
                                                                     _cat_ru(x["cat"]), x["gold"]))
    elif sub == "rare":
        print("таблица %s: кодов %d, на руках %d%s" % (r["table"], r["rare_codes"], r["present"], ", показаны первые" if r["capped"] else ""))
        for x in r["rows"]:
            print("  %-6d %-30s записей %d, штук %d, персонажей %d (служебные: %d)%s" % (
                x["code"], x["name"] or "—", x["total"]["rows"], x["total"]["amount"], x["total"]["chars"], x["cats"]["service"]["rows"],
                ("  P59 выпало %d, подобрано %d" % (x["p59"]["drop"], x["p59"]["pickup"])) if x["p59"] else ""))
    elif sub == "unaccounted":
        for p in r["pairs"]:
            t = p["total"]
            print("  №%s → №%s (%s → %s): снимок %+d, журналы %+d, неучтённое %+d" % (p["from_id"], p["to_id"], str(p["from"])[:19], str(p["to"])[:19],
                                                                                   t["snap"], t["journal"], t["unaccounted"]))
        if not r["pairs"]:
            print("  нужно два снимка (econ snapshot; служба снимает сама в 00:05)")
        for x in r["chars"]:
            print("    №%-7s %-3s %-18s %-10s было %s стало %s журналы %+d неучтённое %+d%s" % (
                x["uid"], x["idx"], x["char"] or "—", _cat_ru(x["cat"]), x["before"], x["after"], x["journal"], x["unaccounted"],
                ("  (персонажа нет в Charinfo)" if x["gone"] else "") + (("  панель: " + ", ".join(x["panel"])) if x.get("panel") else "")))
    for e in r["errors"]:
        print("  ! ошибка:", e)
    return 0


TRADE_KEYS = {"graph": {"--from": True, "--to": True, "--account": True, "--group": True, "--service-in": False},
              "transfers": {"--from": True, "--to": True, "--account": True, "--pair": True, "--group": True, "--service-in": False,
                            "--page": True, "--size": True},
              "market": {"--from": True, "--to": True, "--page": True, "--service-in": False},
              "stores": {"--from": True, "--to": True, "--no-logs": False, "--service-in": False}}


def trade_args(sub, args):
    """★ А6.4: ключи «trade <действие>» → строка запроса домена; неизвестный ключ, ключ без значения, позиционный аргумент — SystemExit."""
    keys, q, i = TRADE_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("trade %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys)))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("trade %s: у ключа %s нет значения" % (sub, a))
            q[a[2:]], i = args[i + 1], i + 2
            continue
        if a == "--no-logs":
            q["logs"] = "0"
        else:
            q["svc"] = "in"
        i += 1
    return q


def _trade(args):
    """★ А6.4: передачи, аукцион, лавки (domains/trade.py) — только чтение. Консоль — роль владельца: сеть (LogInfo) показывается."""
    from domains import trade
    if not args or args[0] not in TRADE_KEYS:
        raise SystemExit("trade: нужно действие %s" % " | ".join(TRADE_KEYS))
    sub = args[0]
    q = trade_args(sub, args[1:])
    trade.check_input(q, sub)
    lg = lambda r, u: "%s%s" % (u, (" " + r["logins"][str(u)]) if r.get("logins", {}).get(str(u)) else "")
    if sub == "graph":
        r = trade.graph(q, can_net=True)
        print("период %s — %s; передач %d; правило M3 (%s): пара ≥ %d записей или золото ≥ %d в одну сторону; серийник ≥ %d передач" % (
            r["period"]["from"], r["period"]["to"], r["totals"]["edges"], r["m3_from"], r["thr"]["m3_pair_deals"], r["thr"]["m3_gold_oneway"],
            r["thr"]["m4_chain"]))
        for s in r["sources"]:
            print("  %-24s %-8s %-5s строк %s%s" % (s["key"], s["group"], s["what"], "не прочитан" if s["rows"] is None else s["rows"],
                                                 "  (обрезано)" if s["capped"] else ""))
        for m in r["mirrors"]:
            print("  зеркало %-20s (пара %s): строк %s — не считается" % (m["table"] + (" Sold out" if m["sold"] else ""), m["of"],
                                                                        "?" if m["rows"] is None else m["rows"]))
        for title, lst in (("пары", r["pairs"]), ("пары со служебной стороной (не в общем списке)", r["service_pairs"])):
            if lst:
                print(title + ":")
            for p in lst:
                fl = "; ".join(("%d записей" % x["value"]) if x["type"] == "deals" else (
                    ("золото %d: %d → %d, обратно нет" % (x["value"], x["from"], x["to"])) if x["type"] == "oneway" else x.get("raw", ""))
                    for x in p["flags"])
                print("  %s ↔ %s: записей %d, золото %d / %d, вещи %d / %d, %s%s%s" % (
                    lg(r, p["a"]), lg(r, p["b"]), p["deals"], p["gold_ab"], p["gold_ba"], p["items_ab"], p["items_ba"],
                    ", ".join("%s %d" % kv for kv in sorted(p["groups"].items())), ("  ФЛАГ: " + fl) if fl else "",
                    ("  связь: " + p["link_title"]) if p.get("link_title") else ""))
        for title, lst in (("цепочки", r["chains"]), ("цепочки со служебной учёткой", r["service_chains"])):
            if lst:
                print(title + ":")
            for c in lst[:20]:
                print("  %s  (золото %d, вещей %d, %s — %s)" % (" → ".join(lg(r, u) for u in c["nodes"]), c["gold"], c["items"],
                                                              str(c["hops"][0]["t"])[:19], str(c["hops"][-1]["t"])[:19]))
        for x in r["serials"]:
            print("  серийник %s (%s %s): передан %d раз: %s" % (x["serial"], x["code"], x["name"] or "", x["n"],
                                                             " → ".join("%s>%s" % (e["fu"], e["tu"]) for e in x["path"])))
        if r["net"]:
            for kind in ("ip", "mac"):
                for g in r["net"][kind]:
                    print("  один %s %s: %s%s" % (kind.upper(), g["value"], ", ".join(lg(r, a["uid"]) for a in g["accounts"]),
                                                 "  (общая сеть)" if g["crowd"] else ""))
        if r["box"] and r["box"]["postbox"] is not None:
            print("  ящик ItemPostBox сейчас: %s; подарков gp7 в ящике %s; Joy1.gifts строк %s" % (
                ", ".join("iType %d — %d" % (x["itype"], x["rows"]) for x in r["box"]["postbox"]) or "пусто", r["box"]["gift_orders"],
                r["box"]["gifts_rows"]))
        if r["gifts"]:
            print("  подарки gp7 за период: %s, тестовых %d, получатель не найден %d" % (
                ", ".join("%s %d" % kv for kv in sorted(r["gifts"]["states"].items())) or "нет", r["gifts"]["test"], r["gifts"]["unresolved"]))
    elif sub == "transfers":
        r = trade.transfers(q)
        print("период %s — %s; передач %d (страница %d из %d)" % (r["period"]["from"], r["period"]["to"], r["total"], r["page"], r["pages"]))
        if r.get("service_total"):
            print("  со служебной стороной (не в списке ниже): %d — --service-in" % r["service_total"])
        for x in r["rows"] + r.get("service_rows", []):
            print("  %s %-7s %-22s %s/%s %s → %s/%s %s: %s %d%s" % (str(x["t"])[:19], x["group"], x["src"], x["fu"], x["fi"], x["fn"] or "",
                                                                  x["tu"], x["ti"], x["tn"] or "", "золото" if x["what"] == "gold" else
                                                                  "%s %s" % (x["code"], x.get("name") or ""), x["qty"],
                                                                  "  (служебная)" if x["cat"] == "service" else ""))
    elif sub == "market":
        r = trade.market(q)
        print("лотов сейчас %d%s" % (r["lots_total"], " (показаны первые)" if r["lots_capped"] else ""))
        for x in r["lots"] + r["service_lots"]:
            print("  %s №%s/%s %s: %s %s × %d за %d (штука %s)%s%s" % (x["eid"], x["uid"], x["slot"], x["char"] or "", x["code"], x["name"] or "",
                                                                    x["amount"], x["price"], "—" if x["unit"] is None else "%.2f" % x["unit"],
                                                                    "  ИСТЁК" if x["expired"] else "", ("  " + x["overdue"]) if x["overdue"] else ""))
        if r["tax"]:
            t = r["tax"]["total"]
            print("налог за %s — %s: сбор за выставление %d (%d), сбор с продажи %d (%d), возврат сбора %d (%d), итого %d" % (
                r["period"]["from"], r["period"]["to"], t["fee"], t["fee_n"], t["commission"], t["commission_n"], t["refund"], t["refund_n"], t["net"]))
        print("история: %d строк (%s), страница %d из %d" % (r["hist_total"], ", ".join("%s %d" % kv for kv in sorted(r["hist_counts"].items())),
                                                            r["page"], r["pages"]))
        for x in r["history"] + r["service_history"]:
            print("  %s %-26s №%s/%s %s ↔ %s %s: %s × %s, цена %s%s" % (str(x["t"])[:19], x["state"] or x["table"], x["uid"], x["slot"], x["char"] or "",
                                                                    x["ou"] if x["ou"] is not None else "", x["oname"] or "", x["code"], x["qty"],
                                                                    x["price"] if x["price"] is not None else "—", "  (зеркало)" if x["mirror"] else ""))
    else:
        r = trade.stores(q, "console")
        print("период %s — %s; сделок %d; итог: сделок %d, золото %d, вещей %d" % (r["period"]["from"], r["period"]["to"], r["sales_total"],
                                                                               r["total"]["sales"], r["total"]["gold"], r["total"]["items"]))
        print("  " + r["open_note"])
        for n in r["notes"]:
            print("  ! " + n)
        for d in r["days"]:
            print("  %s сделок в базе %d, покупок по журналу %s, подтверждено базой %s" % (d["day"], d["sales"], "—" if d["log_buy"] is None else d["log_buy"],
                                                                                    "—" if d["log_ok"] is None else d["log_ok"]))
        for s in (r["sales"] + r["service_sales"])[:50]:
            print("  %s продавец %s/%s %s → покупатель %s/%s %s: золото %d, вещи %s%s" % (
                str(s["t"])[:19], s["su"], s["si"], s["sn"] or "", s["bu"], s["bi"], s["bn"] or "", s["gold"],
                ", ".join("%s×%d" % (i["code"], i["qty"]) for i in s["items"]) or "—", "  (служебная)" if s["cat"] == "service" else ""))
        if r["log"]:
            print("журнал Log_SelfStore: файлов %d, событий %d" % (len(r["log"]["files"]), r["log"]["events_total"]))
    for e in r["errors"]:
        print("  ! ошибка:", e)
    return 0


ODDS_KEYS = {"upgrade": {"--from": True, "--to": True, "--alpha": True, "--service-in": False},
             "boosters": {"--from": True, "--to": True, "--alpha": True, "--no-logs": False, "--service-in": False},
             "boxes": {"--from": True, "--to": True, "--alpha": True, "--service-in": False}}
ODDS_VERDICT = {"ok": "согласуется", "deviation": "ОТКЛОНЕНИЕ", "few": "мало данных", "contradiction": "ПРОТИВОРЕЧИТ ТАБЛИЦЕ"}


def odds_args(sub, args):
    """★ А6.5: ключи «odds <действие>» → строка запроса домена; неизвестный ключ, ключ без значения, позиционный аргумент — SystemExit."""
    keys, q, i = ODDS_KEYS[sub], {}, 0
    while i < len(args):
        a = args[i]
        if a not in keys:
            raise SystemExit("odds %s: неизвестный аргумент %s (есть: %s)" % (sub, a, " ".join(keys)))
        if keys[a]:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise SystemExit("odds %s: у ключа %s нет значения" % (sub, a))
            q[a[2:]], i = args[i + 1], i + 2
            continue
        if a == "--no-logs":
            q["logs"] = "0"
        else:
            q["svc"] = "in"
        i += 1
    return q


def _odds_test(t):
    """Строка итога проверки."""
    pv = "" if t.get("p") is None else "  p=%.3g, с поправкой %.3g" % (t["p"], t["p_adj"])
    return "%s%s" % (ODDS_VERDICT.get(t["verdict"], t["verdict"]), pv)


def _odds(args):
    """★ А6.5: шансы — выпало против заявленного (domains/odds.py), только чтение."""
    from domains import odds
    if not args or args[0] not in ODDS_KEYS:
        raise SystemExit("odds: нужно действие %s" % " | ".join(ODDS_KEYS))
    sub = args[0]
    q = odds_args(sub, args[1:])
    odds.check_input(q, sub)
    if sub == "upgrade":
        r = odds.upgrade(q)
    elif sub == "boosters":
        r = odds.boosters(q, "console")
    else:
        r = odds.boxes(q, "console")
    if r["period"]:
        print("период %s — %s; уровень значимости %s (поправка Холма)" % (r["period"]["from"], r["period"]["to"], r["alpha"]))
    for cat, title in (("main", "игроки" if r["svc"] == "sep" else "все учётки"), ("service", "служебные ≤ 5000 (отдельно)")):
        s = r.get(cat)
        if not s:
            continue
        print("== " + title)
        if sub == "upgrade":
            print("  попыток %d: успех %d, неудача %d, откат %d, разрушение %d; вне критерия %s; неудача не по правилу %d" % (
                s["attempts"], s["outcomes"]["success"], s["outcomes"]["fail"], s["outcomes"]["reset"], s["outcomes"]["destroy"],
                ", ".join("%s %d" % kv for kv in sorted(s["excluded"].items())) or "нет", s["rule_bad"]))
            for x in s["stages"]:
                print("  ступень %s: попыток %d, успех %d (ожидалось %.1f из %d с известным шансом), неудача %d, откат %d, разрушение %d" % (
                    "?" if x["stage"] is None else x["stage"], x["n"], x["success"], x["expected"], x["known"], x["fail"], x["reset"], x["destroy"]))
            for g in s["groups"]:
                print("  свиток %s (тип %s%s) %s%s, ступени %s–%s: %d из %d, заявлено %.4f (ожидалось %.1f) — %s" % (
                    g["scroll"], g["st"], ", купон шанса +%d%%" % g["rate"] if g["rate"] else "", "зона t44" if g["zone"] == "over" else "обычная зона",
                    (" k=%d" % g["k"]) if g["k"] is not None else "", g["stage_min"], g["stage_max"], g["success"], g["n"], g["prob"], g["expected"],
                    _odds_test(g)) + (("  вне критерия: " + ", ".join("%s %d" % kv for kv in sorted(g["off"].items()))) if g.get("off") else ""))
            for x in s["refine"]:
                print("  высшая переработка, шанс %d: %d из %d — %s" % (x["c"], x["success"], x["n"], _odds_test(x)))
            for x in s["refine_loss"]:
                print("  потеря материала при неудаче, шанс %d: %d из %d — %s" % (x["c"], x["success"], x["n"], _odds_test(x)))
            b = s["bless"]
            print("  перенос (порог %d зашит в GameServer): %d из %d, заявлено %.4f — %s" % (b["c"], b["success"], b["n"], b["prob"], _odds_test(b)))
            if s["extract"]:
                print("  извлечение: %s — %s" % (s["extract"]["obs"], _odds_test(s["extract"])))
            print("  без розыгрыша: сброс ItemUpgrade %s; обмен GaChaTran* %d" % (", ".join("%s %d" % (x["state"], x["n"]) for x in s["reset"]) or "нет",
                                                                                s["tran"]))
        elif sub == "boosters":
            print("  призов %d, без приза %d, не по текущей таблице %d (вне критерия); бустер без строки таблицы: %s" % (
                s["draws"], s["lost"], s["stale"], ", ".join("%d×%d" % (x["code"], x["n"]) for x in s["no_row"]) or "нет"))
            if s.get("replay"):
                p = s["replay"]
                print("  Log_GachaItem: строк %d, сумма весов как сейчас %d (приз совпал %d, не совпал %d), другая сумма %d, без строки %d" % (
                    p["lines"], p["same_total"], p["match"], p["mismatch"], p["other_total"], p["no_row"]))
            for x in s["rows"]:
                print("  строка %d (бустеры %s): вскрытий %d, кодов %d, корзин %d — %s%s" % (
                    x["row"], ",".join(str(b["code"]) for b in x["boosters"][:5]), x["n"], x["codes"], x["bins"], _odds_test(x),
                    ("  не по текущей таблице: " + ", ".join("%d×%d" % (o["code"], o["n"]) for o in x["outside"])) if x["outside"] else ""))
        else:
            print("  розыгрышей %d; не по текущей таблице %d" % (s["draws"], s["mismatch"]))
            for x in s["boxes"]:
                print("  автомат %d: строк пула %d, розыгрышей %d, корзин %d — %s" % (x["box"], x["pool"], x["n"], x["bins"], _odds_test(x)))
    if sub == "boosters" and r.get("replay"):
        print("выпавшее — при условии «не промах и приз принят сервером»; отказы после броска (Log_CRTJIN, все учётки): %s" % (
            ", ".join("(%s) %d" % kv for kv in (r.get("refused") or {}).items()) or "нет"))
        p = r["replay"]
        print("Log_GachaItem всего: строк %d, сумма весов как сейчас %d (приз совпал %d, не совпал %d), другая сумма %d, без строки %d" % (
            p["lines"], p["same_total"], p["match"], p["mismatch"], p["other_total"], p["no_row"]))
    if sub == "boxes":
        print("сутки журнала шлюза: прочитано %d, из кэша %d, файла нет %d, не прочитано %d" % (
            r["days"]["read"], r["days"]["cached"], r["days"]["missing"], len(r["days"]["unread"])))
    for n in r.get("notes", []):
        print("  ! " + n)
    for e in r["errors"]:
        print("  ! ошибка:", e)
    return 0


def _logs(args):
    """★ А5.6: хвост серверных журналов — только чтение (domains/logs.py). Консоль — роль владельца: IP без маски, секреты скрыты."""
    import time as _t
    from core.ops import OpRefused
    from domains import logs
    if not args or args[0] not in ("sources", "files", "tail"):
        raise SystemExit("logs: нужно действие sources | files <источник> <копия> | tail <источник> <копия> [<файл>]")
    sub = args[0]
    pos, opt = logs_args(args[1:])
    who = _cli_ctx().login
    if sub == "sources":
        if pos or opt:
            raise SystemExit("logs sources: лишние аргументы")
        for s in logs.catalog()["sources"]:
            print("%-11s %s%s" % (s["key"], s["title"], "" if s["follow"] else "  (без «следить»)"))
            print("            копии: %s" % ", ".join(s["procs"]))
            print("            %s; %s" % (s["rotation"], s["how"]))
        return 0
    if len(pos) < 2 or (sub == "files" and len(pos) != 2) or len(pos) > 3:
        raise SystemExit("logs %s <источник> <копия>%s" % (sub, " [<файл>]" if sub == "tail" else ""))
    if sub == "files":
        if set(opt) - {"--kind"}:
            raise SystemExit("logs files: допустим только --kind")
        try:
            r = logs.files(pos[0], pos[1], opt.get("--kind"))
        except OpRefused as ex:
            raise SystemExit("logs files: %s" % ex)
        if r["missing"]:
            print("папки %s нет%s" % (r["dir"], (" — " + r["note"]) if r.get("note") else ""))
            return 0
        if r["kinds"]:
            print("виды (--kind): " + ", ".join(r["kinds"]))
        for f in r["files"]:
            print("%-36s %12d б  %s" % (f["name"], f["size"], _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(f["mtime"] / 1000))))
        if r["more"]:
            print("… всего %d, показаны %d новых" % (r["total"], len(r["files"])))
        return 0
    key, proc = pos[0], pos[1]
    kind = opt.get("--kind")
    try:
        name = pos[2] if len(pos) == 3 else None
        if name is None:
            fl = logs.files(key, proc, kind)
            if fl["missing"] or not fl["files"]:
                raise SystemExit("logs tail: файлов журнала нет (%s)" % fl["dir"])
            name = fl["files"][0]["name"]
        lv = opt.get("--level")
        mins = int(opt.get("--minutes", "10"))
        if not 1 <= mins <= LOGS_FOLLOW_MAX_MIN:
            raise SystemExit("logs tail: --minutes 1…%d" % LOGS_FOLLOW_MAX_MIN)
        logs.throttle(who, (key, proc, kind or "", name))
        r = logs.tail(key, proc, name, kind, opt.get("--lines"), opt.get("--grep"), lv, opt.get("--scan"), show_ip=True, user=who)
    except (OpRefused, ValueError) as ex:
        raise SystemExit("logs tail: %s" % ex)

    def show(res):
        for ln in res["lines"]:
            print(("!" if ln["lv"] == "err" else "~" if ln["lv"] == "warn" else " ") + " " + ln["t"])

    print("== %s (%d б; совпало %d, показано %d%s%s)" % (r["path"], r["size"], r["matched"], len(r["lines"]),
                                                       "; есть более ранние" if r["truncated"] else "",
                                                       "; замаскировано %d" % r["masked"] if r["masked"] else ""))
    show(r)
    if "--follow" not in opt:
        return 0
    if r["exclusive"]:
        raise SystemExit("logs tail: «следить» за этим журналом нельзя — процесс пишет его без общего доступа")
    end, off, sig, hd = _t.monotonic() + mins * 60, r["offset"], r["sig"], r["head"]
    try:
        while _t.monotonic() < end:
            _t.sleep(LOGS_FOLLOW_POLL_S)           # ★ ревизия 46 Н-3: с ПК каждый опрос — процесс PowerShell на сервере по SSH
            try:
                logs.throttle(who, (key, proc, kind or "", name))
                x = logs.tail(key, proc, name, kind, opt.get("--lines"), opt.get("--grep"), lv, None, off, sig, show_ip=True,
                              head=hd, user=who)
            except OpRefused as ex:
                print("~ опрос: %s" % ex)
                continue
            if x["unchanged"]:
                continue
            if x["reset"]:
                print("== файл стал короче (переписан) — хвост заново")
            if x["skipped"]:
                print("== пропущено %d б (прирост больше предела одного опроса)" % x["skipped"])
            show(x)
            off, sig, hd = x["offset"], x["sig"], x["head"]
    except KeyboardInterrupt:
        pass
    return 0


DB_KEYS = {"state": {}, "backup": {"--all": None, "--db": "v"}, "verify": {"--id": "v"},
           "prune": {"--db": "v", "--confirm-prune": None, "--dry": None}, "stand": {"--id": "v", "--keep": None, "--drop-kept": None}, "restore": None,
           "release": {"--confirm-release": None},                                      # ★ ревизия 47 В-1: снять зависшее «идёт»
           "bak": {"--all": None},                                                      # ★ А5.8: служебные копии
           "bakdrop": {"--db": "v", "--obj": "v", "--backup": "v", "--confirm-bakdrop": None, "--dry": None}}


def db_args(args):
    """★ А5.7: разбор ключей db → (действие, {ключ: значение | True}); неизвестное действие / ключ, ключ без значения — SystemExit."""
    sub = args[0] if args else ""
    if sub not in DB_KEYS:
        raise SystemExit("db: нужно действие %s (help — список)" % " | ".join(DB_KEYS))
    keys, opt, rest = DB_KEYS[sub], {}, args[1:]
    if keys is None:                                  # restore — любые аргументы не нужны: операция всегда отказывает
        return sub, {}
    i = 0
    while i < len(rest):
        a = rest[i]
        if a not in keys:
            raise SystemExit("db %s: неизвестный ключ %s (есть: %s)" % (sub, a, " ".join(keys) or "—"))
        if keys[a]:
            if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
                raise SystemExit("db %s: у %s нет значения" % (sub, a))
            opt[a] = rest[i + 1]
            i += 2
        else:
            opt[a] = True
            i += 1
    return sub, opt


def _db(args):
    """★ А5.7: консоль бэкапов БД (domains/dbbackup.py, dbstand.py)."""
    from core import ops
    from domains import dbbackup
    sub, opt = db_args(args)
    ctx = _cli_ctx()
    gb = lambda b: "—" if b is None else "%.1f МБ" % (b / 1048576.0)
    if sub == "state":
        s = dbbackup.state()
        if not s["read"]:
            raise SystemExit("db state: %s" % s["error"])
        print("папка панели: %s; том %s: свободно %s из %s" % (s.get("folder"), s.get("volume"), gb(s.get("free_bytes")), gb(s.get("total_bytes"))))
        for d in s["dbs"]:
            a, v = d["any"], d["panel_verified"]
            print("%-15s %-6s %-7s данные %-10s журнал %-10s | панель: %s | последний любой: %s" % (
                d["db"], d["recovery"] or "—", d["state"] or "НЕТ", gb(d["data_bytes"]), gb(d["log_bytes"]),
                "№%s %s UTC, %s, %.1f ч%s" % (v["id"], v["finished_utc"][:16], gb(v["bytes"]), v["age_h"] or 0,
                                              "" if v["stand_ok"] is None else (", стенд ок" if v["stand_ok"] else ", стенд НЕ прошёл")) if v else "нет",
                "%s UTC %s%s" % (a["finish_utc"][:16], a["device"], " (COPY_ONLY)" if a["copy_only"] else "") if a else "нет"))
            for w in d["warnings"]:
                print("    ~", w)
        for w in s["warnings"]:
            print("~", w)
        for r in s["rows"][:15]:
            print("  №%-5s %-14s %-8s %-5s %s %s" % (r["id"], r["db"], r["status"], {True: "пров.", False: "НЕ пр.", None: "—"}.get(r["verified"]),
                                                  (r["finished_at"] or r["started_at"] or "")[:16], r["file_path"]))
        return 0
    if sub == "backup":
        if bool(opt.get("--all")) == bool(opt.get("--db")):
            raise SystemExit("db backup: нужно ровно одно из --all или --db <база[,база…]>")
        r = ops.run(ctx, "db.backup", {"dbs": "all" if opt.get("--all") else opt["--db"]})
    elif sub == "verify":
        if "--id" not in opt:
            raise SystemExit("db verify --id N")
        r = ops.run(ctx, "db.verify", {"id": opt["--id"]})
    elif sub == "prune":
        r = ops.run(ctx, "db.prune", {"db": opt.get("--db") or "all", "confirm": "prune" if opt.get("--confirm-prune") else ""},
                    dry=bool(opt.get("--dry")))
        if r["dry"]:
            for x in r["preview"]["items"]:
                print("  удалить №%s %s (%s)" % (x["id"], x["file"], x["why"]))
            for w in r["preview"]["warnings"]:
                print("~", w)
            print(r["preview"]["text"], "(сухой прогон, ничего не удалено)")
            return 0
    elif sub == "stand":
        if "--id" not in opt:
            raise SystemExit("db stand --id N [--keep] [--drop-kept]")
        r = ops.run(ctx, "db.restore_stand", {"id": opt["--id"], "keep": bool(opt.get("--keep")), "drop_kept": bool(opt.get("--drop-kept"))})
    elif sub == "bak":
        return _bak_list(bool(opt.get("--all")))
    elif sub == "bakdrop":
        if not opt.get("--db") or not opt.get("--obj"):
            raise SystemExit("db bakdrop --db <база> --obj схема.имя[,…] [--backup N] --confirm-bakdrop [--dry]")
        prm = {"db": opt["--db"], "names": opt["--obj"], "backup_id": opt.get("--backup"),
               "confirm": "bakdrop" if opt.get("--confirm-bakdrop") else ""}
        r = ops.run(ctx, "db.bakdrop", prm, dry=bool(opt.get("--dry")))
        if r["dry"]:
            for x in r["preview"]["items"]:
                print("  удалить %s (%s, строк %s, %s КБ) — %s" % (x["name"], x["type"], x["rows"], x["kb"], x["evidence"]))
            for w in r["preview"]["warnings"]:
                print("~", w)
            print(r["preview"]["text"], "(сухой прогон, ничего не удалено)")
            return 0
    elif sub == "release":
        r = ops.run(ctx, "db.release", {"confirm": "release" if opt.get("--confirm-release") else ""})
    else:
        r = ops.run(ctx, "db.restore", {})
    print(r["message"], "(журнал №%s)" % r["audit_id"])
    return 0


def _bak_list(show_all):
    """★ А5.8: список служебных копий (domains/bakdrop.py, adm.BakState)."""
    from domains import bakdrop
    s = bakdrop.state()
    if not s["read"]:
        raise SystemExit("db bak: %s" % s["error"])
    word = {"drop": "можно убрать", "rollback": "нужна откату", "unknown": "неизвестно"}
    for x in s["items"]:
        if not x["present"] and not show_all:
            continue
        print("%-12s %-11s %-44s %-2s %8s стр. %7s КБ  %s%s" % (x["db"], word[x["verdict"]], "%s.%s" % (x["sch"], x["name"]), x["type"] or "",
                                                         "—" if x["rows_n"] is None else x["rows_n"], "—" if x["kb"] is None else x["kb"],
                                                         (x["created_utc"] or "нет на сервере")[:16],
                                                         ("  ← " + x["needed_by"]) if x["verdict"] == "rollback" and x["needed_by"] else ""))
        if x["blocked"] and x["verdict"] == "drop":
            print("    ~", x["blocked"])
    for name, d in sorted(s["dbs"].items()):
        f = d.get("fresh")
        print("бэкап %s: %s" % (name, ("№%s %s UTC (%s ч назад)" % (f["id"], f["finished_utc"][:16], f["age_h"])) if f
                                 else (d.get("error") or "свежего проверенного (≤ %s ч) нет" % s["fresh_hours"])))
    for x in s["log"][:10]:
        print("  удалено №%s %s.%s.%s (%s строк) %s UTC, бэкап №%s, %s" % (x["id"], x["db"], x["sch"], x["name"], x["rows_n"], str(x["dropped_at"])[:16],
                                                                      x["backup_id"], x["by_login"]))
    return 0


def _releases(args):
    """★ А7.1: выпуски — статус (domains/releases.py); push — операция release.push от имени консоли (журнал adm.audit)."""
    from core import ops
    from domains import releases
    sub = args[0] if args else "show"
    if sub == "push":
        r = ops.run(_cli_ctx(), "release.push", {}, dry="--dry" in args)
        if "--dry" in args:
            pv = r["preview"] or {}
            print(pv.get("text"))
            for w in pv.get("warnings") or []:
                print("  !", w)
            return 0
        print(r["message"])
        return 0
    if sub != "show":
        raise SystemExit("releases: нужно действие show | push [--dry] (help — ключи)")
    v = releases.view(force=True)
    o = v["outside"]
    print("сервер обновлений %s (снято %s), keyring seq %s, подпись корнем: %s" % (o["url"], o["at"], o["keyring"]["seq"], o["keyring"]["sig"]))
    for p in o["pointers"]:
        print("  %-13s %-24s seq %-4s min %-24s срок %s (%s сут, %s), подпись %s%s" % (
            p["name"], p["version"] or "—", p["seq"], p["min_version"] or "—", p["expires"] or "—", p["days_left"], p["level"], p["sig"],
            (" — " + p["error"]) if p["error"] else ""))
    pc = v["pc"]
    if pc.get("have"):
        s = pc["snap"]
        print("снимок ПК №%s от %s UTC (%s), ПК присылал %s UTC, раз %s%s" % (pc["id"], pc["collected_utc"], pc["host"], pc["seen_utc"],
                                                                         pc["seen_count"], " — УСТАРЕЛ" if pc["stale"] else ""))
        for r in (s.get("releases") or [])[:5]:
            print("  выпуск %s %s seq %s сборка %s" % (r["time"], r["version"], r["seq"], r["build"]))
        for r in s.get("runs_by_kind") or []:
            print("  %-6s %-20s %s %-10s %s" % (r["area"], r["kind"], r["started"], r["result"], r["error"]))
    else:
        print("снимка ПК нет:", pc.get("error") or "ПК ещё не присылал")
    for w in v["warnings"]:
        print("! " + w)
    return 0


def _crashes(args):
    """★ А7.2: сбои клиента (domains/crashes.py); sync — операция crash.sync, prune — crash.alog_prune от имени консоли (журнал adm.audit)."""
    from core import ops
    from domains import crashes
    sub = args[0] if args else "show"
    if sub == "sync":
        prm = {"no_fetch": True} if "--no-fetch" in args or "--dry" in args else {}   # ★ р75 К-2: --dry ничего не забирает
        r = ops.run(_cli_ctx(), "crash.sync", prm, dry="--dry" in args)
        pv = r["preview"] or {}
        if "--dry" in args:
            print(pv.get("text"))
            for x in (pv.get("snap") or {}).get("rows") or []:
                print("  %-40s %-12s %-9s %-10s %-12s %s" % (x["file"], x["login"] or "—", x["status"], x["code"] or "—", x["sig"] or "—",
                                                            x["version"] or "—"))
            for w in pv.get("warnings") or []:
                print("  !", w)
            return 0
        print(r["message"])
        return 0
    if sub == "prune":
        word = args[args.index("--confirm") + 1] if "--confirm" in args and args.index("--confirm") + 1 < len(args) else ""
        pv = ops.run(_cli_ctx(), "crash.alog_prune", {}, dry=True)["preview"]
        print(pv["text"])
        for x in pv.get("first") or []:
            print("  " + x)
        for w in pv.get("warnings") or []:
            print("  !", w)
        if not word:
            print("только предпросмотр — удалить: crashes prune --confirm %s" % crashes.PRUNE_CONFIRM)
            return 0
        r = ops.run(_cli_ctx(), "crash.alog_prune", {"confirm": word, "expect": pv["expect"]})
        print(r["message"])
        return 0
    if sub != "show":
        raise SystemExit("crashes: нужно действие show | sync [--dry] [--no-fetch] | prune [--confirm alogprune] (help — ключи)")
    v = crashes.view(force=True)
    s, ld = v["summary"], v["logdrop"]
    sy = s.get("sync")
    print("сводка ПК: %s" % ("№%s от %s UTC (%s), ПК присылал %s UTC, раз %s%s" % (sy["id"], sy["collected_utc"], sy["host"], sy["seen_utc"],
          sy["seen_count"], " — УСТАРЕЛА" if sy["stale"] else "") if sy else (s.get("error") or "ПК ещё не присылал")))
    for g in s.get("groups") or []:
        print("  %s %-10s %-44s всего %-3d сутки %-2d 7 сут %-2d учёток %-2d последний %s  %s" % (
            g["sig"], g["code"], g["code_name"][:44], g["n"], g["n_24h"], g["n_7d"], len(g["accounts"]), g["last"],
            ", ".join("%s×%d" % (x["version"], x["n"]) for x in g["versions"][:3])))
        print("      " + " ".join(g["frames"][:4]))
    if ld.get("error"):
        print("LogDrop: " + ld["error"])
    else:
        print("LogDrop: занято %.2f из %.2f ГиБ (%s%%), .alog старше %d суток: %d (%.1f МБ)" % (
            ld["used"] / 1073741824.0, ld["quota"] / 1073741824.0, ld["pct"], ld["keep_days"], ld["old_alog"]["n"], ld["old_alog"]["bytes"] / 1048576.0))
    for w in v["warnings"]:
        print("! " + w)
    return 0


def _notes(args):
    """★ А7.7: заметки к выпуску (domains/notes.py); push — операция notes.push от имени консоли (журнал adm.audit). Публикации из консоли нет."""
    from core import ops
    from domains import notes
    sub = args[0] if args else "show"
    if sub == "push":
        r = ops.run(_cli_ctx(), "notes.push", {}, dry="--dry" in args)
        if "--dry" in args:
            pv = r["preview"] or {}
            print(pv.get("text"))
            for w in pv.get("warnings") or []:
                print("  !", w)
            return 0
        print(r["message"])
        return 0
    if sub == "resync":                       # ★ р82 В-2: реестр записей по последнему снимку (перевод прежних ключей публикаций)
        print(ops.run(_cli_ctx(), "notes.resync", {}, dry="--dry" in args)["message"] or "только предпросмотр")
        return 0
    if sub != "show":
        raise SystemExit("notes: нужно действие show | push [--dry] | resync [--dry] (help — ключи)")
    v = notes.view({})
    s = v.get("snap")
    print("снимок changelog: %s" % ("№%s %s от %s UTC (%s), ПК присылал %s UTC, раз %s" % (s["id"], s["file"], s["collected"], s["host"], s["seen"],
          s["seen_count"]) if s else (v.get("error") or "ПК ещё не присылал")))
    for x in v.get("entries") or []:
        print("  %s %-10s %-8s %-10s %-11s %s%s" % (x["key"], x["date"] or "—", x["area"], x["status"], x["pub"], "* " if x["default"] else "  ",
                                                 x["title"][:100]))
    for w in v["warnings"]:
        print("! " + w)
    return 0


def _jobs(args):
    """★ А5.1: консоль заданий планировщика (core/jobs.py)."""
    import time
    from core import jobs, ops
    sub = args[0] if args else "list"
    ctx = _cli_ctx()
    if sub == "list":
        for j in reversed(jobs.list_jobs(100, active="--all" not in args)):
            print("№%-5s %-9s %-15s %-7s %s%s  %s %s" % (j["id"], j["status"], j["op"], j["runner"], jobs.fmt_utc(j["run_at"]),
                                                      (" " + j["repeat_mode"]) if j["repeat_mode"] else "", j["created_by"],
                                                      (j.get("result") or "")[:120]))
        return 0
    if sub == "add":
        rest = [a for a in args[2:]]
        prm = {"op": args[1], "at": rest[rest.index("--at") + 1] if "--at" in rest else "",
               "repeat": rest[rest.index("--repeat") + 1] if "--repeat" in rest else "",
               "note": rest[rest.index("--note") + 1] if "--note" in rest else ""}
        sub_p = json.loads(rest[-1]) if rest and rest[-1].startswith("{") else {}
        for a in rest:
            if a.startswith("--confirm-"):
                sub_p["confirm"] = a[len("--confirm-"):]
        prm["params"] = sub_p
        print(ops.run(ctx, "job.add", prm)["message"])
        return 0
    if sub == "cancel":
        print(ops.run(ctx, "job.cancel", {"id": int(args[1])})["message"])
        return 0
    if sub == "release":
        print(ops.run(ctx, "job.release", {"id": int(args[1]), "confirm": "release" if "--confirm-release" in args else ""})["message"])
        return 0
    if sub in ("run-due", "watch"):
        minutes = int(args[args.index("--minutes") + 1]) if "--minutes" in args else 0
        if sub == "watch" and not 0 < minutes <= 24 * 60:
            raise SystemExit("watch --minutes N (1…1440)")
        end = time.monotonic() + minutes * 60
        while True:
            for jid, st, text in jobs.run_due("pc"):
                print("%s задание №%s: %s %s" % (time.strftime("%H:%M:%S"), jid, st, (text or "")[:300]))
            if sub == "run-due" or time.monotonic() >= end:
                return 0
            time.sleep(min(60, max(1, end - time.monotonic())))
    raise SystemExit("jobs: неизвестное действие %s (help — список)" % sub)


CS_OPS = {"check": "shop.cs_check", "approve": "shop.cs_approve", "cancel": "shop.cs_cancel", "reopen": "shop.cs_reopen", "server-sync": "shop.cs_server_sync", "server-dry": "shop.cs_server_dry",
          "client-dry": "shop.cs_client_dry", "client-apply": "shop.cs_client_apply", "client-rollback": "shop.cs_client_rollback",
          "released": "shop.cs_released", "server-apply": "shop.cs_server_apply", "server-rollback": "shop.cs_server_rollback"}


def _print_check(c):
    """Итог проверки набора в консоль."""
    for p in c["positions"]:
        print("  %2d %-16s %s" % (p["pos"], p["kind"], p["text"] or "—"))
        for e in p["errors"]:
            print("       ОШИБКА:", e)
        for w in p["warnings"]:
            print("       ~", w)
    for f in c["server"]["files"]:
        print("  сервер %-28s %s  %s → %s" % (f["table"], "+".join(f["gs"]), f["base"][:8], f["new"][:8]))
        for d in f["diff"][:6]:
            print("       %s: %s → %s" % (d[0], str(d[1])[:90], str(d[2])[:90]))
    for e in c["client"]:
        print("  клиент", json.dumps(e, ensure_ascii=False)[:200])
    for e in c["errors"]:
        print("ОШИБКА:", e)
    for w in c["warnings"]:
        print("~", w)


def _changeset(args):
    """Консоль наборов изменений магазинов."""
    from core import ops
    from domains import shopcs, shopdata
    sub = args[0] if args else "list"
    ctx = _cli_ctx()
    if sub == "list":
        for r in shopcs.list_sets():
            print("№%-4s %-14s сервер %-11s клиент %-11s поз. %-3s %s — %s" % (r["id"], r["status"], r["server_state"], r["client_state"],
                                                                         r["n"], r["title"], r["author"]))
        return 0
    if sub == "show":
        cs = shopcs.get(int(args[1]))
        print("№%s «%s» %s, порядок %s%s, сервер %s, клиент %s" % (cs["id"], cs["title"], cs["status"], cs["order_mode"],
                                                                 ", СРОЧНО" if cs["urgent"] else "", cs["server_state"], cs["client_state"]))
        for it in cs["items"]:
            print("  %2d %-16s %s" % (it["pos"], it["kind"], json.dumps(it["params"], ensure_ascii=False)[:160]))
        if cs["check"]:
            _print_check(cs["check"])
        return 0
    if sub == "diverge":
        d = shopdata.divergence(limit=15, areas="all" if "--all" in args else None)
        print("клиент: %s (%s)" % (d["client_source"], d["client_built"]))
        for s in d["sections"]:
            print("== %s: %d %s" % (s["title"], s["count"], ("(" + s["note"] + ")") if s["note"] else ""))
            for r in s["rows"][:10]:
                print("   ", json.dumps(r, ensure_ascii=False)[:180])
        return 0
    if sub == "new":
        title = args[1] if len(args) > 1 else ""
        prm = {"title": title, "note": args[args.index("--note") + 1] if "--note" in args else "",
               "order_mode": args[args.index("--order") + 1] if "--order" in args else "together", "urgent": "--urgent" in args}
        print(ops.run(ctx, "shop.cs_create", prm)["message"])
        return 0
    if sub == "add":
        r = ops.run(ctx, "shop.cs_item_add", {"cs": int(args[1]), "kind": args[2], "params": json.loads(args[3])})
        print(r["message"])
        return 0
    if sub == "del":
        print(ops.run(ctx, "shop.cs_item_del", {"cs": int(args[1]), "pos": int(args[2])})["message"])
        return 0
    if sub == "guard":
        # ★ ревизия 39 Н-3: перепроверка набора ПОСЛЕ остановки стойки, до копирования файлов — её зовёт deploy_changeset.py
        #   (ASDA_CHANGESET_GUARD от shopcs._restart); код 0 — можно копировать, иначе выкладчик останавливается, стойка поднимается прежней
        bad = shopcs.post_stop_guard(int(args[1]), "rollback" if "--rollback" in args else "", "--held-ok" in args)
        for b in bad:
            print("ПРИЧИНА:", b)
        print("перепроверка после остановки: %s" % ("чисто" if not bad else "отказ, причин %d" % len(bad)))
        return 1 if bad else 0
    if sub in CS_OPS:
        prm = {"cs": int(args[1])}
        if "--confirm-restart" in args:
            prm["confirm"] = "restart"
        if "--unsynced-ok" in args:
            prm["unsynced_ok"] = True
        if "--irreversible-ok" in args:
            prm["irreversible_ok"] = True
        if "--held-ok" in args:                          # ★ ревизия 36 Б-1: откат сервера при предметах со сменой стопки на руках
            prm["held_ok"] = "held"
        if "--balance-ok" in args:                       # ★ А4.0: второе подтверждение сильной правки баланса
            prm["balance_ok"] = "balance"
        r = ops.run(ctx, CS_OPS[sub], prm)
        print(r["message"], "(журнал №%s)" % r["audit_id"])
        res = r.get("result") or {}
        for ln in res.get("lines") or []:
            print("  ", ln)
        for path, f in (res.get("files") or {}).items() if isinstance(res.get("files"), dict) else []:
            print("  файл %s: %s → %s" % (path, f["old"][:8], f["new"][:8]))
            for d in f["diff"][:12]:
                print("     ", d[:160])
        for j in res.get("dt_jobs") or []:
            print("  DT %s: строки %s" % (j["dt"], ", ".join(j["allow_rows"][:10])))
        for k in res.get("importers") or []:
            print("  импортёр:", shopdata.IMPORTERS[k][0])
        if sub == "check":
            _print_check(shopcs.get(int(args[1]))["check"])
        return 0
    raise SystemExit("changeset: неизвестное действие %s (help — список)" % sub)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as ex:   # консоль: понятная причина вместо трассы для ожидаемых отказов
        from core import ops, db, auth, hostshell
        if isinstance(ex, (ops.OpRefused, db.DbError, auth.AuthError, hostshell.HostError)):
            print("ОТКАЗ:", ex)
            sys.exit(2)
        from domains import stack as _stack_mod
        if isinstance(ex, _stack_mod.StackFailed):           # ★ А5.1: стойка не в ожидаемом состоянии после restart_stack
            print("СБОЙ:", ex)
            sys.exit(3)
        from domains import dbbackup as _dbb_mod
        if isinstance(ex, _dbb_mod.BackupFailed):            # ★ А5.7: бэкап / проверка / стенд не удались (текст — по базам)
            print("СБОЙ:", ex)
            sys.exit(3)
        raise
