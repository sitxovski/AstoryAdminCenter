# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""acdaily_en.py — английский вид суточного отчёта античита (шаг А6.6, 22.11.2026; domains/acdaily.py). Тексты отчёта формирует исходник
AstoryServer/Tools/Anticheat (ac_daily_report / ac_metrics_logs / ac_metrics_db / ac_common) по-русски — здесь их шаблоны в форме printf исходника
(%s, %d, %.1f …) и английские с {0}, {1}…; nested — номера подстановок, которые переводятся тем же словарём (подписи внутри флагов).
Нет шаблона — текст уходит как есть (данные журналов: ники, функции, виды из базы). Markdown исходника не переводится — это сам отчёт.
Самотест (tests/selftest_acdaily_a6.py) сверяет: у каждой русской строки исходника, которая попадает в отчёт, есть шаблон, и EN-вид
синтетического отчёта без русских букв. Побочных эффектов при импорте нет.
"""
import re

from core import i18n

# (русский шаблон исходника, английский, переводимые подстановки)
TABLE = [
    # ---- ac_daily_report.py: названия метрик (на случай падения метрики — safe()), статусы, итог
    ("Опыт в час", "Experience per hour", ()), ("Сделки между парой", "Deals within a pair", ()), ("Дубли предметов", "Item duplicates", ()),
    ("Перемещение", "Movement", ()), ("Скорость атаки", "Attack speed", ()), ("Спидхак по пингу", "Speed hack by ping", ()),
    ("Подделка пакетов", "Packet forgery", ()), ("Исключительные отключения", "Exception disconnects", ()), ("Мультиаккаунт", "Multi-account", ()),
    ("Длительность сессий", "Session length", ()), ("Действия GM", "GM actions", ()), ("Перебор паролей", "Password guessing", ()),
    ("Повторный вход", "Repeated sign-in", ()), ("Журнал joylog1.ac", "joylog1.ac journal", ()),
    ("ok", "ok", ()), ("нет данных", "no data", ()), ("ошибка", "error", ()), ("данные есть", "data present", ()), ("событий нет", "no events", ()),
    ("см. README.md", "see README.md", ()),
    ("нет модуля %s (при `python -I` пользовательский pyodbc не виден - запустить без -I).",
     "no module {0} (with `python -I` the user pyodbc is not visible - run without -I).", ()),
    ("БД отключена (--no-db).", "database off (--no-db).", ()), ("LogInfo: БД отключена (--no-db).", "LogInfo: database off (--no-db).", ()),
    ("БД недоступна: %s (при `python -I` пользовательский pyodbc не виден - запустить без -I).",
     "database unavailable: {0} (with `python -I` the user pyodbc is not visible - run without -I).", ()),
    ("LogInfo недоступна: %s: %s", "LogInfo unavailable: {0}: {1}", (1,)),
    ("LogInfo за окно: %d входов, из них с пустым MAC %d (LoginManager MAC в UPUserLogin не передаёт - 04 §1.6).",
     "LogInfo for the window: {0} sign-ins, {1} of them with an empty MAC (LoginManager does not pass the MAC to UPUserLogin - 04 §1.6).", ()),
    ("Замена ui:N на логины не выполнена: %s", "Replacing ui:N with logins failed: {0}", (0,)),
    # ---- ac_common.py
    ("По видам", "By kind", ()), ("Вид", "Kind", ()), ("Событий", "Events", ()),
    ("%s: %d за %d мин (с %s)", "{0}: {1} in {2} min (from {3})", (0,)),
    ("%s: %d событий вне списка владельца", "{0}: {1} events outside the owner list", (0,)),
    # ---- ac_metrics_logs.py: M5
    ("Телепорт/ускорение перемещения (`CharMove|CharReMove Hack Position`)", "Teleport / movement speed-up (`CharMove|CharReMove Hack Position`)", ()),
    ("число строк на ник; флаг: >= %d за %d мин", "lines per nick; flag: >= {0} in {1} min", ()),
    ("серия отката позиции", "position rollback series", ()), ("позиция", "position", ()),
    ("Сервер сам откатывает позицию (4007 тип 5), санкции нет; координат в строке нет.",
     "The server rolls the position back itself (4007 type 5), no sanction; the line has no coordinates.", ()),
    # M6
    ("Скорость атаки (NpcServer `SpeedHack Check....!`)", "Attack speed (NpcServer `SpeedHack Check....!`)", ()),
    ("все NpcServer стойки (%s)/Error_Log/SpeedHack_YYYYMMDD.txt (только нужные дни, потоково)",
     "all stack NpcServers ({0})/Error_Log/SpeedHack_YYYYMMDD.txt (only the needed days, streamed)", ()),
    ("Duration/PDuration < %.1f многократно (>= %d на ник); Count > %d = порог отключения 8905",
     "Duration/PDuration < {0} repeatedly (>= {1} per nick); Count > {2} = disconnect threshold 8905", ()),
    ("атака быстрее допуска (ratio<%.1f): %d раз", "attack faster than allowed (ratio<{0}): {1} times", ()),
    ("Count %d > %d (порог отключения 8905)", "Count {0} > {1} (disconnect threshold 8905)", ()), ("скорость атаки", "attack speed", ()),
    ("Строки отключения по 8905 (sendSpeedHackDisConnect) в просмотренных каналах GameServer не найдены.",
     "Disconnect lines by 8905 (sendSpeedHackDisConnect) were not found in the GameServer channels read.", ()),
    # M6b
    ("Спидхак по пингу (GameServer `Log_SpeedHack`: Warning / HackCheck)", "Speed hack by ping (GameServer `Log_SpeedHack`: Warning / HackCheck)", ()),
    ("два пинга ближе 6 с = Warning; 4 подряд = HackCheck. По 04 §2.1 детектор шумный, реакции нет",
     "two pings closer than 6 s = Warning; 4 in a row = HackCheck. Per 04 §2.1 the detector is noisy, no reaction", ()),
    ("(без ника)", "(no nick)", ()), ("tick %d->%d dt=%d мс", "tick {0}->{1} dt={2} ms", ()),
    ("HackCheck: %d раз вне списка владельца", "HackCheck: {0} times outside the owner list", ()),
    ("Warning с ником: %d (остальные Warning - без ника: ник проставляется только со 2-й строки серии).",
     "Warning with a nick: {0} (other Warnings have no nick: the nick is set only from the 2nd line of a series).", ()),
    ("HackCheck пишется, но в срезе кода никем не читается; шум от легитимного клиента владельца.",
     "HackCheck is written but no code in the slice reads it; noise from the owner's legitimate client.", ()),
    # M7
    ("Подделка пакетов (`Log_Secret`, MD5 в `Log_Exception_Asm`, ошибки `Log_Item`, кик LoginManager)",
     "Packet forgery (`Log_Secret`, MD5 in `Log_Exception_Asm`, `Log_Item` errors, LoginManager kick)", ()),
    ("любое ненулевое значение вне списка владельца - сильный сигнал (порт должен быть «чистым»)",
     "any non-zero value outside the owner list - a strong signal (the port must be “clean”)", ()),
    ("(нет ника)", "(no nick)", ()), ("MD5-несовпадение", "MD5 mismatch", ()), ("неизвестный/хак-пакет", "unknown / hack packet", ()),
    ("ошибка предмета", "item error", ()),
    ("подделка", "forgery", ()),
    ("%s x%d (в источнике нет ника; пример: %s)", "{0} x{1} (the source has no nick; example: {2})", (0,)),
    ("Ошибки Log_Item считаются по userindex (ui:N), ника в строке нет; штатные Refine/ServerNotice не считаются.",
     "Log_Item errors are counted by userindex (ui:N), the line has no nick; regular Refine/ServerNotice are not counted.", ()),
    ("LoginManager: плановых отключений по счётчику Ping за период - %d (в метрику не входят).",
     "LoginManager: planned disconnects by the Ping counter in the period - {0} (not part of the metric).", ()),
    # M7d
    ("Исключительные отключения (`___ExceptionDisConnetUser___ CallFunc, CharN, IP`)", "Exception disconnects (`___ExceptionDisConnetUser___ CallFunc, CharN, IP`)", ()),
    ("справочно: функция-причина, ник, IP; Ping TimeOut - плановая очистка", "for reference: cause function, nick, IP; Ping TimeOut - planned cleanup", ()),
    ("По функциям-причинам", "By cause function", ()), ("отключение %s вне списка владельца", "disconnect {0} outside the owner list", ()),
    # M9
    ("Бот-поведение: длительность сессий (`Log_LevelUp` вход/выход)", "Bot behaviour: session length (`Log_LevelUp` sign-in / sign-out)", ()),
    ("GameServer/Log/Log_LevelUp (+ Login_Check для сверки числа входов)", "GameServer/Log/Log_LevelUp (+ Login_Check to check the number of sign-ins)", ()),
    ("сессия > %.0f ч или онлайн за сутки >= %.0f ч; сессии портала склеены (разрыв <= %d с)",
     "session > {0} h or online per day >= {1} h; portal sessions are merged (gap <= {2} s)", ()),
    ("сессия", "session", ()), ("%.2f ч, L%d->L%d", "{0} h, L{1}->L{2}", ()),
    ("сессия %.1f ч (%s - %s)", "session {0} h ({1} - {2})", ()), ("онлайн %.1f ч за %s", "online {0} h on {1}", ()),
    ("Сессии по нику (топ-15 по времени онлайн)", "Sessions by nick (top 15 by online time)", ()), ("Ник", "Nick", ()), ("Сессий", "Sessions", ()),
    ("Онлайн, ч", "Online, h", ()), ("Макс. сессия, ч", "Max session, h", ()),
    ("Сессий в окне (по времени выхода): %d; запросов входа GM_LOGON_REQ в Login_Check: %d (ника в этих строках нет).",
     "Sessions in the window (by sign-out time): {0}; GM_LOGON_REQ sign-in requests in Login_Check: {1} (these lines have no nick).", ()),
    ("Без выхода (нет DisConnectUser): %d; выходов без входа: %d; перезаписей входа: %d.",
     "Without sign-out (no DisConnectUser): {0}; sign-outs without sign-in: {1}; sign-in overwrites: {2}.", ()),
    # M1
    ("Опыт в час (`Log_LevelUp` Exp на входе/выходе)", "Experience per hour (`Log_LevelUp` Exp at sign-in / sign-out)", ()),
    ("(Exp_выхода - Exp_входа) / длительность, сессии >= %d с; флаг: > %.1f x медианы уровня (группа >= %d сессий)",
     "(Exp_out - Exp_in) / duration, sessions >= {0} s; flag: > {1} x the level median (group >= {2} sessions)", ()),
    ("dExp=%d за %.2f ч = %.0f/ч", "dExp={0} in {1} h = {2}/h", ()),
    ("опыт %.0f/ч на уровне %d (медиана %.0f, x%.1f), сессия до %s", "experience {0}/h at level {1} (median {2}, x{3}), session until {4}", ()),
    ("Медиана опыта/ч по уровню входа (группы >= %d сессий)", "Experience/h median by the sign-in level (groups >= {0} sessions)", ()),
    ("Уровень", "Level", ()), ("Медиана/ч", "Median/h", ()),
    ("Exp в журнале накопительный (не сбрасывается при повышении уровня), дельта корректна и через уровни.",
     "Exp in the log is cumulative (not reset on level-up), the delta is correct across levels too.", ()),
    ("Порог по уровням работает при достаточной выборке; на малом окне видны лишь топ-5 по ставке. GM-выдача опыта (ники GM_*) искажает ставку.",
     "The per-level threshold works with a large enough sample; on a small window only the top 5 by rate are seen. GM experience grants (GM_* nicks) distort the rate.", ()),
    # M11
    ("Действия GM (`Log_Operator`: ItemGive, Kick, Kill, Move, Summon, чат)", "GM actions (`Log_Operator`: ItemGive, Kick, Kill, Move, Summon, chat)", ()),
    ("ItemGive/любая команда не-владельческого ника - флаг; Hide - рутина, в итог не входит",
     "ItemGive / any command of a non-owner nick - flag; Hide - routine, not part of the total", ()),
    ("ItemGive отказ", "ItemGive refused", ()),
    ("ItemGive от %s: Code=%s x%s (%s)", "ItemGive from {0}: Code={1} x{2} ({3})", ()),
    ("ItemGive выдан не-владельческим ником", "ItemGive by a non-owner nick", ()),
    ("GM-команда %s вне списка владельца", "GM command {0} outside the owner list", ()),
    ("По командам", "By command", ()), ("Команда", "Command", ()), ("ItemGive OK (последние 15)", "ItemGive OK (last 15)", ()),
    ("Время", "Time", ()), ("От", "From", ()), ("Кому", "To", ()), ("Кол-во", "Qty", ()),
    ("Send_HideCommand за период: %d (рутина, в итог не входит). Строки `___ExceptionDisConnetUser___` - в M7d.",
     "Send_HideCommand in the period: {0} (routine, not part of the total). `___ExceptionDisConnetUser___` lines - in M7d.", ()),
    # M12 / M12o
    ("Перебор паролей / вход в заблокированную учётку (OTP_Report + `[LOGIN] Failed Count / Block User`)",
     "Password guessing / sign-in to a blocked account (OTP_Report + `[LOGIN] Failed Count / Block User`)", ()),
    ("LoginManager/Log/LoginMngError (OTP_Report: live %d, архив %d файлов; LoginProc)", "LoginManager/Log/LoginMngError (OTP_Report: live {0}, archive {1} files; LoginProc)", ()),
    ("неудачи (status 2/3/5, Failed Count, Block User) с одного IP/логина: > %d за %d мин",
     "failures (status 2/3/5, Failed Count, Block User) from one IP / login: > {0} in {1} min", ()),
    ("(нет логина)", "(no login)", ()), ("(нет IP)", "(no IP)", ()),
    ("неудачных входов с IP", "failed sign-ins from an IP", ()), ("неудачных входов на логин", "failed sign-ins per login", ()),
    ("Попытки по status (OTP_Report): 1=вход, 2/3=неверный ID/пароль, 4=уже в игре, 5=блок",
     "Attempts by status (OTP_Report): 1=sign-in, 2/3=wrong ID / password, 4=already in game, 5=block", ()),
    ("Записей", "Records", ()),
    ("OTP_Report за период нет ни в LoginMngError, ни в архиве (архив не задан): M8 / M12 / M12o без записей входа LoginManager.",
     "No OTP_Report for the period in LoginMngError or in the archive (no archive set): M8 / M12 / M12o without LoginManager sign-in records.", ()),
    ("OTP_Report за период нет ни в LoginMngError, ни в архиве (%s): M8 / M12 / M12o без записей входа LoginManager.",
     "No OTP_Report for the period in LoginMngError or in the archive ({0}): M8 / M12 / M12o without LoginManager sign-in records.", ()),
    ("общий источник метрики не прочитан:", "the metric's shared source was not read:", ()),
    ("LoginProc не прочитан: %s: %s", "LoginProc was not read: {0}: {1}", (1,)),
    ("В dev `UPUserLogin` не проверяет пароль (04 §0 п.5): статусы 2/3 недостижимы, Failed Count мёртв - ожидается 0.",
     "On dev `UPUserLogin` does not check the password (04 §0 item 5): statuses 2/3 are unreachable, Failed Count is dead - 0 expected.", ()),
    ("Вход при уже открытой сессии (OTP status 4 / `[LOGIN] Overlap User Error`)", "Sign-in with a session already open (OTP status 4 / `[LOGIN] Overlap User Error`)", ()),
    ("справочно: повторный вход той же учётки; много по разным логинам - признак передачи учётки/бота",
     "for reference: repeated sign-in of the same account; many on different logins - a sign of account sharing / a bot", ()),
    ("повторный вход", "repeated sign-in", ()),
    # M8
    ("Мультиаккаунт: граф учётка - IP - MAC (OTP_Report; БД `JoyLog1.LogInfo` добавляется отдельно)",
     "Multi-account: account - IP - MAC graph (OTP_Report; the `JoyLog1.LogInfo` database is added separately)", ()),
    ("OTP_Report (MAC попадает в строку случайно), JoyLog1.dbo.LogInfo", "OTP_Report (the MAC gets into the line by chance), JoyLog1.dbo.LogInfo", ()),
    (">= %d учётки на IP или MAC, >= %d IP на учётку. В dev-LAN все 192.168.10.x - IP слабый признак",
     ">= {0} accounts per IP or MAC, >= {1} IPs per account. In the dev LAN all are 192.168.10.x - the IP is a weak sign", ()),
    ("IP %s делят %d логинов", "IP {0} is shared by {1} logins", ()), ("MAC %s делят %d логинов", "MAC {0} is shared by {1} logins", ()),
    ("логин входил с %d IP: %s", "the login signed in from {0} IPs: {1}", ()),
    ("IP -> число логинов (топ-10)", "IP -> number of logins (top 10)", ()), ("MAC -> число логинов (топ-10)", "MAC -> number of logins (top 10)", ()),
    ("Логинов", "Logins", ()), ("Логины", "Logins list", ()),
    ("Подключений к LoginManager по IP (LoginProc, топ-10)", "LoginManager connections by IP (LoginProc, top 10)", ()), ("Подключений", "Connections", ()),
    # ---- ac_metrics_db.py: M3
    ("Сделки между одной парой (JoyLog1 `Trade*`, `PersonalStore*`)", "Deals within one pair (JoyLog1 `Trade*`, `PersonalStore*`)", ()),
    ("JoyLog1.dbo.Trade*/PersonalStore* (без зеркальных ...To)", "JoyLog1.dbo.Trade*/PersonalStore* (without the mirror ...To)", ()),
    ("GROUP BY Userindex,Tuserindex за окно отчёта и за 7 дней; флаг: >= %d записей пары или золото >= %d в одну сторону",
     "GROUP BY Userindex,Tuserindex for the report window and for 7 days; flag: >= {0} pair records or gold >= {1} one way", ()),
    ("таблиц Trade*/PersonalStore* с нужными столбцами (Edate, Userindex, Tuserindex, Fromname, Toname) нет",
     "no Trade*/PersonalStore* tables with the needed columns (Edate, Userindex, Tuserindex, Fromname, Toname)", ()),
    ("Таблиц найдено: %d (учитывается %d без зеркальных ...To); строк во всех: %d.", "Tables found: {0} ({1} counted without the mirror ...To); rows in all: {2}.", ()),
    ("Направление и сумма - по реверсу процедур Joy1 (22.11.2026): Trade* - Userindex отдал, Tuserindex получил; лавка - вещь продавец (Userindex) "
     "-> покупатель (Tuserindex), золото PersonalStoreGoldFrom - покупатель -> продавец; сумма - переданное (дельта баланса владельца строки), а не "
     "баланс «было»; золото - таблицы с `Gold` в имени и строки Code 20551 (стопка золота целиком в TradeItemFrom), остальное - предметы.",
     "Direction and amount - per the reverse of the Joy1 procedures (22.11.2026): Trade* - Userindex gave, Tuserindex received; store - the item goes "
     "seller (Userindex) -> buyer (Tuserindex), PersonalStoreGoldFrom gold - buyer -> seller; the amount is what was passed (the balance delta of the "
     "row owner), not the “before” balance; gold - tables with `Gold` in the name and Code 20551 rows (a whole gold stack in TradeItemFrom), the rest - items.", ()),
    ("все таблицы сделок пусты (журнал обмена/лавки на dev ещё не заполнялся).", "all deal tables are empty (the trade / store log on dev has not been filled yet).", ()),
    ("окно отчёта", "report window", ()), ("7 дней до конца окна", "7 days to the end of the window", ()), ("пара", "pair", ()),
    ("записей=%d, предметов %d/%d, золота %d/%d", "records={0}, items {1}/{2}, gold {3}/{4}", ()),
    ("Пары, %s (предметов a->b / b->a, золота a->b / b->a)", "Pairs, {0} (items a->b / b->a, gold a->b / b->a)", (0,)),
    ("Пара", "Pair", ()), ("Пред. a->b", "Items a->b", ()), ("Пред. b->a", "Items b->a", ()), ("Золото a->b", "Gold a->b", ()), ("Золото b->a", "Gold b->a", ()),
    ("[%s] %s", "[{0}] {1}", (0, 1)),
    ("пара %s<->%s: %d записей сделок за окно", "pair {0}<->{1}: {2} deal records in the window", ()),
    ("пара %s: золото %d в одну сторону, обратно золота нет (предметов обратно: %d) - асимметрия",
     "pair {0}: gold {1} one way, no gold back (items back: {2}) - asymmetry", ()),
    # M4
    ("Дубли предметов (`Joy1.Item.Uuid`, `Del_item`, цепочки `Serial` в JoyLog1)", "Item duplicates (`Joy1.Item.Uuid`, `Del_item`, `Serial` chains in JoyLog1)", ()),
    ("Uuid встречается > 1 раза в Item; Uuid одновременно в Item и Del_item; Serial передан >= %d раз за окно",
     "Uuid occurs > 1 time in Item; Uuid both in Item and Del_item; Serial passed >= {0} times in the window", ()),
    ("дубль Uuid", "Uuid duplicate", ()), ("Uuid и в Item, и в Del_item", "Uuid both in Item and in Del_item", ()), ("цепочка Serial", "Serial chain", ()),
    ("Uuid=%s x%d, Code=%s, userindex %s..%s, GainDate %s..%s (унаследовано из исходной базы)",
     "Uuid={0} x{1}, Code={2}, userindex {3}..{4}, GainDate {5}..{6} (inherited from the original database)", ()),
    ("Uuid %s встречается %d раз (Code=%s), GainDate до 2026 - унаследовано", "Uuid {0} occurs {1} times (Code={2}), GainDate before 2026 - inherited", ()),
    ("Uuid %s встречается %d раз (Code=%s)", "Uuid {0} occurs {1} times (Code={2})", ()),
    ("Предметов в Joy1.Item: %d; Uuid с повторами: %d.", "Items in Joy1.Item: {0}; Uuid with repeats: {1}.", ()),
    ("Uuid=%s, удалён %s", "Uuid={0}, deleted {1}", ()), ("Uuid %s есть и в Item, и в Del_item", "Uuid {0} is both in Item and in Del_item", ()),
    ("Пересечение Item и Del_item: %d.", "Item and Del_item overlap: {0}.", ()), ("Del_item недоступна: %s", "Del_item unavailable: {0}", ()),
    ("Serial=%s передан %d раз", "Serial={0} passed {1} times", ()), ("Serial %s передан %d раз за окно (%s)", "Serial {0} passed {1} times in the window ({2})", ()),
    ("Таблиц сделок со столбцом Serial проверено: %d; серийников с цепочкой >= %d: %d.",
     "Deal tables with a Serial column checked: {0}; serials with a chain >= {1}: {2}.", ()),
    ("Тип «Nostack» серийника не имеет - в проверку не входит.", "The “Nostack” type has no serial - not part of the check.", ()),
    # ACJ
    ("Журнал античита в БД (`joylog1.ac`, P53)", "Anti-cheat journal in the database (`joylog1.ac`, P53)", ()),
    ("joylog1.ac.* и представления v_events / v_top_offenders / v_account_daily", "joylog1.ac.* and the views v_events / v_top_offenders / v_account_daily", ()),
    ("справочно: события серверных проверок (кик, автоблок, повтор подписи, откат позиции, отказы GM), без служебных строк «журнал:»",
     "for reference: server check events (kick, auto-block, signature replay, position rollback, GM refusals), without the service “журнал:” lines", ()),
    ("Таблицы ac.* (всего строк за всё время)", "ac.* tables (all rows for all time)", ()), ("Таблица", "Table", ()), ("Строк", "Rows", ()),
    ("Первое", "First", ()), ("Последнее", "Last", ()),
    ("Служебных строк журнала («журнал: старт/проблемы»): %d, последняя %s - журнал жив.",
     "Service journal lines (“журнал: start / problems”): {0}, last {1} - the journal is alive.", ()),
    ("Служебных строк журнала («журнал: старт/проблемы»): %d, последняя %s - журнал ещё не писался (процессы с P53 не выложены).",
     "Service journal lines (“журнал: start / problems”): {0}, last {1} - the journal has not been written yet (processes with P53 not deployed).", ()),
    ("событий нарушений в окне нет (таблицы пусты или процессы с P53 ещё не выложены).",
     "no violation events in the window (the tables are empty or processes with P53 are not deployed yet).", ()),
    ("События в окне по видам", "Events in the window by kind", ()), ("Топ нарушителей за всё время (v_top_offenders)", "Top offenders for all time (v_top_offenders)", ()),
    ("Логин", "Login", ()), ("Всего", "Total", ()), ("Кики", "Kicks", ()), ("Автоблоки", "Auto-blocks", ()), ("Повтор подписи", "Signature replay", ()),
    ("Откат позиции", "Position rollback", ()),
    # ---- domains/acdaily.py: причины падения метрики (open частной копии, подключение исходника отключено)
    ("суточный отчёт открывает журналы только на чтение", "the daily report opens logs read-only", ()),
    ("файл вне белого списка суточного отчёта: %s", "a file outside the daily report allow-list: {0}", ()),
    ("код вне дерева службы не исполняется: %s", "code outside the service tree is not executed: {0}", ()),
    ("файла %s нет в манифесте выкладки — код не исполняется", "file {0} is not in the deployment manifest — the code is not executed", ()),
    ("файл %s не совпадает с манифестом выкладки (md5) — код не исполняется", "file {0} does not match the deployment manifest (md5) — the code is not executed", ()),
    ("подключение исходника к базе в панели отключено — база читается логином службы asda_admin",
     "the source's database connection is off in the panel — the database is read with the service login asda_admin", ()),
    # ---- короткие общие шаблоны — В КОНЕЦ (иначе перехватили бы длинные: «кик %s x%d (в источнике нет ника …)»)
    ("кик %s", "kick {0}", ()),
]

_NUM = r"(-?(?:[0-9]+(?:\.[0-9]*)?|nan|inf))"


def _rx(ru):
    """printf-шаблон исходника → регулярное выражение целой строки."""
    s = re.escape(ru).replace("%%", "%")
    s = re.sub(r"%\\\.\d+f|%\.\d+f", lambda _m: _NUM, s)
    s = s.replace("%d", r"(-?\d+)").replace("%s", "(.*?)")
    return re.compile("^" + s + "$", re.S)


_COMPILED = [(_rx(ru), en, nested) for ru, en, nested in TABLE]
_EXC = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*): (.*)$", re.S)
_UNITS = ((re.compile(r": ([0-9.]+) ч(?=,|$)"), r": \1 h"), (re.compile(r"/ч(?=,|$)"), "/h"))
_NON = re.compile(r"^(\d+) \(\+(\d+) без ника\)$")
_NICKLESS = (("(без ника)", "(no nick)"), ("(нет ника)", "(no nick)"), ("(нет логина)", "(no login)"), ("(нет IP)", "(no IP)"))


def tr(s, depth=0):
    """Текст отчёта на английском (нет шаблона — как есть; «Тип: текст» исключения — тип как есть, текст переводится)."""
    if not isinstance(s, str) or not s or depth > 4:
        return s
    for rx, en, nested in _COMPILED:
        m = rx.match(s)
        if m:
            g = [tr(x, depth + 1) if i in nested else x for i, x in enumerate(m.groups())]
            return re.sub(r"\{(\d)\}", lambda mo: g[int(mo.group(1))] or "", en)
    m = _EXC.match(s)
    if m and depth == 0:
        inner = tr(m.group(2), depth + 1)
        return "%s: %s" % (m.group(1), inner if inner != m.group(2) else i18n.tr(m.group(2)))
    return s


def tr_summary(row):
    """Строка «Итог» исходника: метрика, всего, субъектов, среднее / макс., топ-5 (единицы «ч», «/ч»), вне владельца («+N без ника»),
    флаги, статус."""
    r = list(row)
    if len(r) >= 8:
        top = str(r[4])
        for rx, rep in _UNITS:
            top = rx.sub(rep, top)
        for ru, en in _NICKLESS:                       # подписи субъектов без ника внутри «Топ-5» (ник — данные, подпись — исходника)
            top = top.replace(ru, en)
        r[4] = top
        m = _NON.match(str(r[5]))
        if m:
            r[5] = "%s (+%s without a nick)" % (m.group(1), m.group(2))
        r[7] = tr(r[7])
    return r


def view(rep):
    """Отчёт (ответ acdaily.report) → английский вид: названия, источники, формулы, статусы, заметки, флаги, таблицы, последние события."""
    for m in rep.get("metrics") or []:
        for k in ("title", "source", "formula", "status"):
            m[k] = tr(m.get(k))
        m["notes"] = [tr(x) for x in m.get("notes") or []]
        m["summary"] = tr_summary(m.get("summary") or [])
        m["flags"] = [[f[0], tr(f[1])] + list(f[2:]) for f in m.get("flags") or []]
        m["bg_top"] = [[tr(x[0])] + list(x[1:]) for x in m.get("bg_top") or []]
        m["tables"] = [[tr(t[0]), [tr(h) for h in t[1]], [[tr(c) if isinstance(c, str) else c for c in row] for row in t[2]]]
                       for t in m.get("tables") or []]
        m["last"] = [_ev(e) for e in m.get("last") or []]
    return rep


def _ev(e):
    """Строка события [время, источник, субъект, вид, деталь, …] — субъект, вид и деталь по шаблонам."""
    e = list(e)
    for i in (2, 3, 4):
        if i < len(e):
            e[i] = tr(e[i])
    return e


def rows(ev):
    """Страница событий → английский вид."""
    return [_ev(e) for e in ev]
