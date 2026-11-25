# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""opdoc.py — справка по каждой операции админ-центра: что меняет, нужен ли перезапуск, как откатить (шаг А7.10, 24.11.2026; план
ADMIN_TOOL_PLAN.md §5.3 строка А7.10, §4 «Л. Сам инструмент» — «справка по каждой операции („что пишет и куда“)»).

ЗАЧЕМ. Оператор перед подтверждением видит не только предпросмотр «было → станет», но и честный ответ на три вопроса: куда пишет операция
  (какие базы и таблицы, файлы, процессы, Discord / Telegram), нужен ли перезапуск чего-либо и как это отменить (журналом, обратной операцией
  или никак — и что именно не вернётся). Те же ответы — на странице «Справка» панели (web/help.js) со списком всех операций.
ИСТОЧНИК. Каталог DOC ниже написан по коду операций (domains/*.py, их процедуры sql/*.sql) — ничего сверх кода. Права (perm → роли),
  исполнитель заданий (служба / ПК), второй фактор и признак «откатывается журналом» берутся из самой операции и core/auth.PERMS
  автоматически — в каталоге их нет, чтобы не разошлись.
ПОЛЯ ЗАПИСИ (короткие ключи — каталог большой):
  w   — кортеж кодов WRITES (куда пишет), wr / we — подробно по-русски / по-английски;
  r   — код RESTART, rr / re — пояснение (у r = "none" можно не писать — берётся NO_RESTART);
  u   — код UNDO: journal (откат записью журнала действий — ровно у операций с reversible = True), inverse (обратной операцией — inv),
        irreversible (необратимо — в ur / ue сказано, что не вернуть), nothing (откатывать нечего — ничего значимого не меняется);
        ur / ue — пояснение;
  inv — имена обратных операций (у u = "inverse");
  hr / he — справка: что делает и когда использовать (одна-три фразы);
  te  — название операции по-английски (русское — Operation.title).
ПОЛНОТА проверяется самотестом (tests/selftest_opdoc_a7.py, офлайн): у каждой операции core.ops.REGISTRY есть запись, все тексты RU и EN,
  коды из списков, reversible ↔ journal, обратные операции существуют, плюс выборочная сверка с признаками кода (Discord, Telegram, мост,
  удаление, рестарт стойки). Новая операция без справки — ошибка самотеста. Функция problems() — та же проверка полноты без кода разделов.
Побочных эффектов при импорте нет.
"""

# Куда пишет операция: код → (по-русски, по-английски)
WRITES = {
    "game_db": ("игровые базы", "game databases"),
    "panel_db": ("база панели AsdaAdmin", "panel database AsdaAdmin"),
    "live": ("живой сервер (мост P127)", "live server (bridge P127)"),
    "server_files": ("файлы стойки", "server stack files"),
    "stack": ("процессы стойки", "server stack processes"),
    "client": ("данные клиента на ПК (к выпуску)", "client data on the PC (for a release)"),
    "pc": ("файлы ПК владельца", "owner PC files"),
    "discord": ("Discord", "Discord"),
    "telegram": ("Telegram", "Telegram"),
    "none": ("ничего", "nothing"),
}
# Перезапуск: код → (по-русски, по-английски)
RESTART = {
    "none": ("не нужен", "not needed"),
    "relogin": ("со следующего входа персонажа", "from the next character login"),
    "stack": ("рестарт стойки", "server stack restart"),
    "release": ("выпуск клиента", "client release"),
}
# Откат: код → (по-русски, по-английски)
UNDO = {
    "journal": ("откат из журнала действий", "undo from the action journal"),
    "inverse": ("обратной операцией", "by the reverse operation"),
    "irreversible": ("необратимо", "irreversible"),
    "nothing": ("откатывать нечего", "nothing to undo"),
}
NO_RESTART = ("перезапуск не нужен — действует сразу", "no restart needed — takes effect at once")

# Разделы справки по началу имени операции: префикс → (по-русски, по-английски). Порядок — порядок разделов на странице.
SECTIONS = [
    (("account.",), ("Учётки", "Accounts")),
    (("char.", "appearance.", "camp.", "craft.", "fish.", "fishbook.", "tutorial.", "plus.", "skill.", "quest.", "title.", "fame.",
      "honor.", "pet."), ("Персонажи", "Characters")),
    (("soulmate.", "friend.", "clan."), ("Связи: соулмейт, друзья, клан", "Relations: soulmate, friends, clan")),
    (("items.", "gold."), ("Предметы и золото", "Items and gold")),
    (("attendance.",), ("Посещаемость", "Attendance")),
    (("live.",), ("Живьём (мост)", "Live (bridge)")),
    (("maint.",), ("Режим обслуживания", "Maintenance mode")),
    (("event.", "rank.", "daily."), ("События и сбросы", "Events and resets")),
    (("stack.", "job."), ("Стойка и задания", "Stack and jobs")),
    (("shop.",), ("Наборы изменений данных игры", "Game data change sets")),
    (("db.",), ("Бэкапы БД", "DB backups")),
    (("case.", "ac."), ("Античит", "Anti-cheat")),
    (("chat.",), ("Журнал чата", "Chat log")),
    (("names.",), ("Очередь имён", "Name queue")),
    (("report.", "reports."), ("Жалобы игроков", "Player reports")),
    (("money.",), ("Деньги", "Money")),
    (("econ.",), ("Экономика", "Economy")),
    (("release.",), ("Выпуски", "Releases")),
    (("crash.",), ("Сбои клиента", "Client crashes")),
    (("outbox.",), ("Очередь Discord", "Discord queue")),
    (("notes.",), ("Заметки к выпуску", "Release notes")),
    (("community.",), ("Сообщество", "Community")),
    (("notify.", "telegram."), ("Telegram владельцу", "Telegram to the owner")),
    (("users.", "self."), ("Пользователи панели", "Panel users")),
]
OTHER_SECTION = ("Прочее", "Other")


def D(w, wr, we, u, ur, ue, hr, he, te, r="none", rr="", re="", inv=()):
    """Одна запись каталога (короткие ключи — см. шапку)."""
    return {"w": tuple(w), "wr": wr, "we": we, "r": r, "rr": rr, "re": re, "u": u, "ur": ur, "ue": ue, "inv": tuple(inv),
            "hr": hr, "he": he, "te": te}


# Общие пояснения (повторяются у многих операций)
_OFF_R = ("перезапуск не нужен — персонаж не в игре, правку он увидит при входе",
          "no restart — the character is offline and sees the change on login")
_ROWS_U = ("Откат возвращает прежние строки, если с тех пор они не менялись (персонаж снова не в игре).",
           "Undo restores the previous rows if they have not changed since (the character must be offline again).")
_BOT = ("Команду исполняет бот Oracle на ПК владельца (очередь adm.BotCmd, раз в 30 с).",
        "The command is executed by the Oracle bot on the owner PC (queue adm.BotCmd, every 30 s).")
_ROWS_LOG_U = (_ROWS_U[0] + " Строки журналов JoyLog1 остаются.", _ROWS_U[1] + " The JoyLog1 log rows stay.")   # ★ р85: журналы игры откатом не стираются
# ★ ревизия 85: сброс в Joy1, который restart_stack.py делает перед каждым стартом стойки (кроме --stop-only)
_RS = ("Joy1 перед стартом: сброс точек входа данжей (UP_AsdaDungeonRelogReset) и устаревших строк CharPos / Us_member (UP_AsdaCharPosReset, журнал "
       "CharPosResetLog).", "Joy1 before the start: dungeon entry points reset (UP_AsdaDungeonRelogReset) and stale CharPos / Us_member rows "
       "(UP_AsdaCharPosReset, log CharPosResetLog).")
# ★ ревизия 85 М-2: строка бота в mod-log Discord (community_bot._log) — откатом не убирается
_ML = ("Бот пишет строку о сделанном в канал mod-log Discord — откат её не убирает.",
       "The bot writes a line about what was done to the Discord mod-log channel — an undo does not remove it.")

# Каталог: имя операции → запись D(...) (по коду операции; полнота — problems() и самотест)
DOC = {
    # ------------------------------------------------------------------ учётки
    "account.block": D(
        ["game_db"], "AsdaStoryOp: Us_member.us_block = 5 и строка BlockList (причина, конец срока, −1 часов = 30 лет), как UPUserBlock.",
        "AsdaStoryOp: Us_member.us_block = 5 and a BlockList row (reason, end date, −1 hours = 30 years), as UPUserBlock.",
        "journal", "Удаляется ровно вставленная строка BlockList, us_block — как было. Блок, поставленный делом античита, снимается только через дело.",
        "Exactly the inserted BlockList row is deleted, us_block goes back. A block set by an anti-cheat case is lifted only via the case.",
        "Заблокировать вход учётки на срок или навсегда с причиной. Срок истекает сам при следующем входе.",
        "Block an account's login for a period or forever, with a reason. The period expires by itself on the next login.",
        "Account: block",
        rr="Не нужен: вход и смена карты отклоняются сразу, игрок в игре доигрывает до выхода (отключить сейчас — мостом).",
        re="Not needed: login and map change are refused at once, a player in game plays until logout (disconnect now via the bridge)."),
    "account.unblock": D(
        ["game_db"], "AsdaStoryOp: строки BlockList переносятся в BlockHistory, us_block = 0 (как штатная OPBlockDel).",
        "AsdaStoryOp: BlockList rows move to BlockHistory, us_block = 0 (as the stock OPBlockDel).",
        "journal", "Строки возвращаются в BlockList, us_block — как было. Снятие, сделанное делом античита, — только через дело.",
        "The rows go back to BlockList, us_block as before. A lift done by an anti-cheat case is undone only via the case.",
        "Снять блок входа с учётки досрочно.", "Lift an account's login block early.", "Account: unblock"),
    "account.clear_online": D(
        ["game_db"], "Joy1.CharPos (UserNum −1, Partyidx −1, Captain, SoulState, State 0) и AsdaStoryOp.Us_member (Flag 0, UserNum −1) — только "
        "доказанно залипшие строки.", "Joy1.CharPos (UserNum −1, Partyidx −1, Captain, SoulState, State 0) and AsdaStoryOp.Us_member (Flag 0, "
        "UserNum −1) — only rows proven stale.",
        "journal", "Прежние значения возвращаются, если строки с тех пор не менялись.",
        "The previous values come back if the rows have not changed since.",
        "Снять залипший признак «в игре» после аварии сервера: вход отвечает «двойной вход», панель не даёт править предметы.",
        "Clear a stale “in game” flag after a server crash: login says “double login”, the panel refuses item edits.",
        "Account: clear stale “in game”"),
    "account.close": D(
        ["game_db", "panel_db"], "AsdaStoryOp: вечный блок (us_block 5 + BlockList на 30 лет) и по желанию новый случайный пароль (соль, хеш, "
        "us_pwset). Прежние соль и хеш — в AsdaAdmin.adm.pw_saved. Персонажи, склад, gp7 и Discord не трогаются.",
        "AsdaStoryOp: a permanent block (us_block 5 + BlockList for 30 years) and optionally a new random password (salt, hash, us_pwset). The "
        "old salt and hash go to AsdaAdmin.adm.pw_saved. Characters, warehouse, gp7 and Discord are untouched.",
        "journal", "Снимается вставленный блок, пароль возвращается, если его с тех пор не меняли.",
        "The inserted block is removed, the password comes back if it has not been changed since.",
        "«Удалить» учётку: строки не удаляются, учётка закрывается навсегда.",
        "“Delete” an account: no rows are deleted, the account is closed forever.", "Account: close"),
    "account.create": D(
        ["game_db"], "AsdaStoryOp.Us_member — одна новая строка (через представление dbo.adm_NewAccount, значения как UP_AC_CreateAccount).",
        "AsdaStoryOp.Us_member — one new row (via the view dbo.adm_NewAccount, values as UP_AC_CreateAccount).",
        "irreversible", "Удалять учётки панель не может (DELETE запрещён). Созданную по ошибке — заблокировать (account.block).",
        "The panel cannot delete accounts (DELETE is denied). One created by mistake — block it (account.block).",
        "Создать игровую учётку с паролем (автосоздания при входе нет).",
        "Create a game account with a password (there is no auto-creation on login).", "Account: create"),
    "account.create_service": D(
        ["game_db"], "AsdaStoryOp.Us_member — служебная учётка с номером 1…5000 (процедура adm.ServiceAccountCreate).",
        "AsdaStoryOp.Us_member — a service account numbered 1…5000 (procedure adm.ServiceAccountCreate).",
        "irreversible", "Удалять учётки панель не может. Лишнюю — заблокировать (account.block).",
        "The panel cannot delete accounts. A spare one — block it (account.block).",
        "Создать служебную учётку (номер ≤ 5000) для GM и проверок. GM-команды она получит только вместе с GM-флагом.",
        "Create a service account (number ≤ 5000) for GMs and tests. It gets GM commands only together with the GM flag.",
        "Account: create a service account"),
    "account.gm_grant": D(
        ["game_db"], "Joy1.CharGmInfo — строка GM-флага (только учётки 1…5000).", "Joy1.CharGmInfo — a GM flag row (accounts 1…5000 only).",
        "journal", "Удаляется ровно вставленная строка.", "Exactly the inserted row is deleted.",
        "Выдать GM-флаг служебной учётке: GM-команды, обход EAC-кика и правил имени.",
        "Grant the GM flag to a service account: GM commands, EAC kick exemption and name rule exemption.", "Account: grant GM flag",
        r="relogin", rr="Флаг действует со следующей загрузки персонажа (по желанию панель отключит игрока мостом).",
        re="The flag works from the next character load (optionally the panel disconnects the player via the bridge)."),
    "account.gm_revoke": D(
        ["game_db"], "Joy1.CharGmInfo — удаляются все строки учётки.", "Joy1.CharGmInfo — all rows of the account are deleted.",
        "journal", "Строки возвращаются с прежними GMDate, если у учётки с тех пор не появилось новых.",
        "The rows come back with the old GMDate if the account has got no new ones since.",
        "Снять GM-флаг с любой учётки.", "Remove the GM flag from any account.", "Account: revoke GM flag",
        r="relogin", rr="Действует со следующей загрузки персонажа.", re="Works from the next character load."),
    "account.pw_unlock": D(
        ["game_db"], "AsdaStoryOp.Us_member: счётчик неудач us_pwfail = 0, us_pwfail_at = NULL.", "AsdaStoryOp.Us_member: us_pwfail = 0, us_pwfail_at = NULL.",
        "journal", "Прежние значения счётчика неудач возвращаются.", "The previous failure counter values come back.",
        "Снять замок после 10 неверных паролей подряд (иначе вход закрыт на 15 минут даже верному паролю).",
        "Remove the lock after 10 wrong passwords in a row (otherwise login is closed for 15 minutes even to the right password).",
        "Account: unlock password"),
    "account.set_password": D(
        ["game_db"], "AsdaStoryOp.Us_member: новые соль и хеш пароля, us_pwset, замок неудач снят (как UP_AC_SetPassword).",
        "AsdaStoryOp.Us_member: a new password salt and hash, us_pwset, failure lock removed (as UP_AC_SetPassword).",
        "irreversible", "Прежний хеш панель не хранит (журнал секретов не держит) — вернуть можно только новым паролем.",
        "The panel does not keep the old hash (the journal holds no secrets) — it can only be replaced by a new password.",
        "Задать игроку новый пароль (утерян пароль, взлом).", "Set a new password for a player (password lost, account hacked).",
        "Account: set password"),
    # ------------------------------------------------------------------ персонаж
    "appearance.set": D(
        ["game_db"], "Joy1.CharAppr — причёска, цвет волос, лицо.", "Joy1.CharAppr — hairstyle, hair colour, face.",
        "journal", *_ROWS_U,
        hr="Сменить причёску, цвет и лицо персонажа не в игре — только варианты своего пола, как у парикмахерской и окна создания.",
        he="Change hairstyle, colour and face of an offline character — only options of its gender, as at the barber and on creation.",
        te="Character: appearance", rr=_OFF_R[0], re=_OFF_R[1]),
    "camp.penalty_clear": D(
        ["game_db"], "Joy1.CharCamp: штраф CampPenaltyTime = 0.", "Joy1.CharCamp.CampPenaltyTime = 0.", "journal", *_ROWS_U,
        hr="Снять штраф лагеря (войны фракций) персонажа не в игре.", he="Clear the camp (faction war) penalty of an offline character.",
        te="Character: clear camp penalty", rr=_OFF_R[0], re=_OFF_R[1]),
    "camp.rank_rebuild": D(
        ["game_db"], "Joy1: рейтинг чести пересчитывается штатной процедурой (EXEC adm.CampPointRank → UP_CampPointRank).",
        "Joy1: the honour ranking is rebuilt by the stock procedure (EXEC adm.CampPointRank → UP_CampPointRank).",
        "irreversible", "Прежний порядок рейтинга не хранится. Пересчитать снова можно в любой момент, служба и так пересчитывает раз в сутки.",
        "The previous ranking order is not kept. It can be rebuilt again at any time, the service rebuilds it daily anyway.",
        "Пересчитать рейтинг чести сейчас, не дожидаясь суточного пересчёта.", "Rebuild the honour ranking now instead of waiting for the daily run.",
        "Camp: rebuild honour ranking", r="relogin", rr="GameServer читает место в рейтинге при входе персонажа.",
        re="GameServer reads the ranking place on character login."),
    "camp.set_army": D(
        ["game_db"], "Joy1.CharCamp.Campidx у всех персонажей учётки (строки нет — вставляется, как UPCharCampSelect).",
        "Joy1.CharCamp.Campidx for all characters of the account (a missing row is inserted, as UPCharCampSelect).", "journal", *_ROWS_U,
        hr="Сменить армию (фракцию) всей учётки, когда вся учётка не в игре.", he="Change the army (faction) of a whole account while it is offline.",
        te="Account: change army", rr=_OFF_R[0], re=_OFF_R[1]),
    "char.copy": D(
        ["game_db"], "Joy1: копия персонажа на служебную учётку процедурой adm.CharCopy (33 таблицы, новые Uuid предметов, карта adm.CharCopyItemMap). "
        "JoyLog1 не пишется.", "Joy1: a copy of the character on a service account by adm.CharCopy (33 tables, new item Uuids, map "
        "adm.CharCopyItemMap). JoyLog1 is not written.",
        "journal", "Копия удаляется (adm.CharCopyDelete), если слот всё ещё с этим именем и у копии нет друзей, клана, лотов и почты.",
        "The copy is deleted (adm.CharCopyDelete) if the slot still has that name and the copy has no friends, clan, lots or mail.",
        "Скопировать персонажа игрока на служебную учётку (≤ 5000), чтобы воспроизвести проблему, не трогая оригинал.",
        "Copy a player's character to a service account (≤ 5000) to reproduce a problem without touching the original.",
        "Character: copy to a service account", rr=_OFF_R[0], re=_OFF_R[1]),
    "char.exp_set": D(
        ["game_db", "live"], "Joy1.Charinfo.Expe у персонажа не в игре или живьём мостом (игрок в игре).",
        "Joy1.Charinfo.Expe of an offline character, or live via the bridge (player in game).",
        "journal", "Офлайн-правка — прежнее значение, если строка не менялась. Живая правка (мост) журналом не откатывается — исправьте новым действием.",
        "An offline edit — the old value if the row has not changed. A live edit (bridge) cannot be undone from the journal — fix it with a new action.",
        "Поставить опыт в процентах текущего уровня.", "Set experience as a percentage of the current level.", "Character: set level experience, %"),
    "char.job_change": D(
        ["game_db"], "Joy1: Charinfo (Job, Subjob, Class, JobCount, SkillPoint, характеристики), CharFame, CharFameBank, CharSkill — как награда квеста по ступеням.",
        "Joy1: Charinfo (Job, Subjob, Class, JobCount, SkillPoint, stats), CharFame, CharFameBank, CharSkill — as the quest reward step by step.",
        "journal", "Вставленное удаляется, прежние значения возвращаются, если с тех пор ничего не менялось.",
        "The inserted rows are deleted and the old values come back if nothing has changed since.",
        "Сменить профессию персонажа не в игре (следующая ступень или 4-я профессия) с очками, званием и навыками, как сервер.",
        "Change the job of an offline character (next step or 4th job) with points, title and skills, as the server does.",
        "Character: change job", rr=_OFF_R[0], re=_OFF_R[1]),
    "char.level_up": D(
        ["game_db", "live"], "Joy1.Charinfo: Lvl, Expe, SkillPoint, базовые характеристики (не в игре) или живьём мостом (игрок в игре).",
        "Joy1.Charinfo: Lvl, Expe, SkillPoint, base stats (offline) or live via the bridge (player in game).",
        "journal", "Офлайн-правка — прежние значения, если строка не менялась. Живая правка (мост) журналом не откатывается — исправьте новым действием.",
        "An offline edit — the old values if the row has not changed. A live edit (bridge) cannot be undone from the journal — fix it with a new action.",
        "Поднять уровень персонажа так же, как сервер при повышении (понижения у сервера нет).",
        "Raise a character's level the way the server does on level-up (the server has no level-down).", "Character: level up"),
    "char.move": D(
        ["game_db", "live"], "Joy1.CharPos (Poridx, Cporidx, Posx, Posy) у персонажа не в игре или перенос живьём мостом.",
        "Joy1.CharPos (Poridx, Cporidx, Posx, Posy) of an offline character, or a live move via the bridge.",
        "journal", "Офлайн — прежняя позиция, если персонаж с тех пор не входил. Живой перенос журналом не откатывается — перенесите обратно новым действием.",
        "Offline — the old position if the character has not logged in since. A live move cannot be undone from the journal — move back with a new action.",
        "Вытащить застрявшего персонажа в безопасную точку: возрождение, город, старт, своя клетка или к другому персонажу.",
        "Rescue a stuck character to a safe spot: respawn point, town, start, a chosen cell or next to another character.",
        "Character: move (rescue a stuck one)"),
    "char.rename": D(
        ["game_db"], "Joy1: Charname в Charinfo, CharPos и CharFriend (у друзей имя обновляется, дружба не теряется).",
        "Joy1: Charname in Charinfo, CharPos and CharFriend (friends get the new name, friendships are kept).",
        "journal", "Старое имя возвращается, если новое с тех пор не меняли и старое не занято.",
        "The old name comes back if the new one has not changed since and the old one is free.",
        "Сменить имя персонажа не в игре по правилам A13 (не в клане, без лотов аукциона).",
        "Rename an offline character under rule A13 (not in a clan, no auction lots).", "Character: rename", rr=_OFF_R[0], re=_OFF_R[1]),
    "char.restore": D(
        ["game_db"], "Joy1: процедура adm.CharRestore вставляет персонажа из корзины Del_* в свободный слот с новым именем, AsdaStoryOp.CharacterStat.",
        "Joy1: adm.CharRestore inserts the character from the Del_* recycle tables into a free slot with a new name, AsdaStoryOp.CharacterStat.",
        "irreversible", "Восстановленный — обычный персонаж, убрать его снова можно только удалением в игре. Что при удалении стёрто без копии "
        "(друзья, лагерь, созвездие, почта, баффы наборов и др.), не вернётся.",
        "The restored one is an ordinary character, it can be removed again only by deleting in game. What deletion erased without a copy "
        "(friends, camp, constellation, mail, set buffs and more) does not come back.",
        "Восстановить удалённого персонажа из корзины.", "Restore a deleted character from the recycle bin.", "Character: restore a deleted one",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "craft.daily_reset": D(
        ["game_db"], "Joy1.CRT_LimitationQuest одного персонажа: дневные задания доски Quest_Flag 3 → 0, Quest_Count → 0.",
        "Joy1.CRT_LimitationQuest of one character: daily board quests Quest_Flag 3 → 0, Quest_Count → 0.", "journal", *_ROWS_U,
        hr="Сбросить ежедневные задания доски одному персонажу, как суточный сброс.", he="Reset one character's daily board quests like the daily reset.",
        te="Character: reset daily board quests", rr=_OFF_R[0], re=_OFF_R[1]),
    "craft.set_level": D(
        ["game_db"], "Joy1.CRT_CharCraftInfo — iLevel и iExp ремесла.", "Joy1.CRT_CharCraftInfo — craft iLevel and iExp.", "journal", *_ROWS_U,
        hr="Задать уровень и опыт ремесла в границах таблицы CraftLevel.", he="Set craft level and experience within the CraftLevel table.",
        te="Character: craft level", rr=_OFF_R[0], re=_OFF_R[1]),
    "fame.recalc": D(
        ["game_db", "live"], "Joy1.CharFameBank.Fmpoint — сумма очков по маске званий (не в игре) или пересчёт живьём мостом.",
        "Joy1.CharFameBank.Fmpoint — the sum over the title mask (offline) or a live recalculation via the bridge.",
        "journal", "Офлайн — прежнее значение, если строка не менялась. Живой пересчёт журналом не откатывается.",
        "Offline — the old value if the row has not changed. A live recalculation cannot be undone from the journal.",
        "Пересчитать славу так, как сервер пересчитывает её при входе (ручная слава живёт только до входа).",
        "Recalculate fame the way the server does on login (manually set fame lives only until login).", "Character: recalculate fame"),
    "fish.set_skill": D(
        ["game_db"], "Joy1.CharFish.FishingSkill (строки нет — вставляется, как первый улов).",
        "Joy1.CharFish.FishingSkill (a missing row is inserted, as on the first catch).", "journal", *_ROWS_U,
        hr="Задать навык рыбалки персонажа не в игре.", he="Set the fishing skill of an offline character.", te="Character: fishing skill",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "fishbook.delete": D(
        ["game_db"], "Joy1.CharFishBook — строка книги рыб удаляется (как UPCharFishBookDelete).",
        "Joy1.CharFishBook — a fish book row is deleted (as UPCharFishBookDelete).", "journal", *_ROWS_U,
        hr="Удалить запись книги рыб.", he="Delete a fish book entry.", te="Character: delete fish book entry", rr=_OFF_R[0], re=_OFF_R[1]),
    "honor.set": D(
        ["game_db"], "Joy1.CharCamp.CampPoint — очки чести (валюта магазина чести).", "Joy1.CharCamp.CampPoint — honour points (honour shop currency).",
        "journal", *_ROWS_U, hr="Задать очки чести персонажа не в игре. Ступень чести сервер пересчитает при входе.",
        he="Set honour points of an offline character. The server recalculates the honour grade on login.", te="Character: honour points",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "plus.extend": D(
        ["game_db"], "Joy1.CharPlusPackage — EndTime и BuffPeriod += N минут.", "Joy1.CharPlusPackage — EndTime and BuffPeriod += N minutes.",
        "journal", *_ROWS_U, hr="Продлить бафф набора персонажа.", he="Extend a character's set buff.", te="Character: extend set buff",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "plus.remove": D(
        ["game_db"], "Joy1.CharPlusPackage — строка баффа удаляется.", "Joy1.CharPlusPackage — the buff row is deleted.", "journal", *_ROWS_U,
        hr="Снять бафф набора персонажа.", he="Remove a character's set buff.", te="Character: remove set buff", rr=_OFF_R[0], re=_OFF_R[1]),
    "plus.set": D(
        ["game_db"], "Joy1.CharPlusPackage — бафф типа из PlusPackageTable (срок — минуты таблицы, StartTime = сейчас).",
        "Joy1.CharPlusPackage — a buff of a PlusPackageTable type (duration — table minutes, StartTime = now).", "journal", *_ROWS_U,
        hr="Выдать бафф набора, как при использовании предмета.", he="Grant a set buff as if the item were used.", te="Character: grant set buff",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "skill.grant": D(
        ["game_db"], "Joy1.CharSkill — навык уровнем 0 с полями нулевого уровня (как UPSkillAdd).",
        "Joy1.CharSkill — a skill at level 0 with level-0 fields (as UPSkillAdd).", "journal", *_ROWS_U,
        hr="Выдать навык своей профессии уровнем 0.", he="Grant a skill of the character's job at level 0.", te="Character: grant skill",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "skill.points": D(
        ["game_db"], "Joy1.Charinfo.SkillPoint — очки навыков (0…32 767).", "Joy1.Charinfo.SkillPoint (0…32,767).", "journal", *_ROWS_U,
        hr="Задать очки навыков.", he="Set skill points.", te="Character: skill points", rr=_OFF_R[0], re=_OFF_R[1]),
    "skill.remove": D(
        ["game_db"], "Joy1.CharSkill — строка навыка удаляется, Charinfo.SkillPoint += его уровень.",
        "Joy1.CharSkill — the skill row is deleted, Charinfo.SkillPoint += its level.", "journal", *_ROWS_U,
        hr="Снять навык (у сервера такого нет) с возвратом очков.", he="Remove a skill (the server has no such action) refunding the points.",
        te="Character: remove skill", rr=_OFF_R[0], re=_OFF_R[1]),
    "skill.reset_all": D(
        ["game_db"], "Joy1: все строки CharSkill удаляются (шаблон класса и навыки без требования дерева остаются уровнем 0), SkillPoint += Σ уровней.",
        "Joy1: all CharSkill rows are deleted (the class template and skills without a tree requirement stay at level 0), SkillPoint += Σ levels.",
        "journal", *_ROWS_U, hr="Полный сброс навыков, как свиток полного сброса (исправленный).",
        he="Full skill reset, like the full reset scroll (fixed version).", te="Character: reset all skills", rr=_OFF_R[0], re=_OFF_R[1]),
    "skill.reset_tree": D(
        ["game_db"], "Joy1.CharSkill по навыкам дерева: уровень 0 или строка удаляется, SkillPoint += уровни.",
        "Joy1.CharSkill for the tree's skills: level 0 or the row is deleted, SkillPoint += levels.", "journal", *_ROWS_U,
        hr="Сбросить одно дерево навыков, как свиток сброса дерева.", he="Reset one skill tree, like the tree reset scroll.",
        te="Character: reset skill tree", rr=_OFF_R[0], re=_OFF_R[1]),
    "quest.complete": D(
        ["game_db"], "Joy1: CharEpisode (слот удаляется), CharQuest (бит «выполнено»), награда — Charinfo (опыт, очки навыков) и Item (золото, предметы "
        "через adm.ItemGive).", "Joy1: CharEpisode (slot removed), CharQuest (“done” bit), reward — Charinfo (experience, skill points) and Item "
        "(gold, items via adm.ItemGive).", "journal", *_ROWS_U,
        hr="Завершить задание с наградой ячейки сдачи (вариант выбирает оператор).", he="Complete a quest with its hand-in reward (the operator picks the option).",
        te="Quest: complete with reward", rr=_OFF_R[0], re=_OFF_R[1]),
    "quest.drop": D(
        ["game_db"], "Joy1.CharEpisode — строка удаляется, у задания доски CRT_LimitationQuest.Quest_Flag = 0.",
        "Joy1.CharEpisode — the row is deleted, for a board quest CRT_LimitationQuest.Quest_Flag = 0.", "journal", *_ROWS_U,
        hr="Снять взятое задание, как отказ игрока.", he="Drop a taken quest, as the player's own abandon.", te="Quest: drop", rr=_OFF_R[0], re=_OFF_R[1]),
    "quest.give": D(
        ["game_db"], "Joy1.CharEpisode — новый слот (State 2, шаг 0), предметы-цели книги в Item.",
        "Joy1.CharEpisode — a new slot (State 2, step 0), quest book goal items in Item.", "journal", *_ROWS_U,
        hr="Выдать задание так, как выдал бы NPC (уровень, профессия, предшествующие задания).",
        he="Give a quest the way an NPC would (level, job, prerequisite quests).", te="Quest: give", rr=_OFF_R[0], re=_OFF_R[1]),
    "quest.uncomplete": D(
        ["game_db"], "Joy1.CharQuest — бит «выполнено» снимается.", "Joy1.CharQuest — the “done” bit is cleared.", "journal", *_ROWS_U,
        hr="Снять отметку «выполнено» (кроме эпизодов смены профессии и заданий с зависимыми).",
        he="Clear the “done” mark (except job change episodes and quests with dependants).", te="Quest: clear “done”", rr=_OFF_R[0], re=_OFF_R[1]),
    "title.grant": D(
        ["game_db", "live"], "Joy1: CharFame, CharFameBank (маска, Fmpoint), CharFameProgress, CharFameHigh — не в игре, или выдача живьём мостом.",
        "Joy1: CharFame, CharFameBank (mask, Fmpoint), CharFameProgress, CharFameHigh — offline, or a live grant via the bridge.",
        "journal", "Офлайн — «было», если строки не менялись. Живая выдача — обратной живой командой, пока игрок в игре.",
        "Offline — the previous rows if they have not changed. A live grant — by the reverse live command while the player is in game.",
        "Выдать звание, как сервер (строка звания, маска, слава, наборы). Рейтинговые 65–69 — только пересчётом рейтинга.",
        "Grant a title as the server does (title row, mask, fame, sets). Ranking titles 65–69 — only via ranking recalculation.", "Character: grant title"),
    "title.revoke": D(
        ["game_db", "live"], "Joy1: бит звания снимается, Fmpoint −= очки, CharFame обнуляется, надетое снимается — не в игре, или живьём мостом.",
        "Joy1: the title bit is cleared, Fmpoint −= points, CharFame reset, the worn title removed — offline, or live via the bridge.",
        "journal", "Офлайн — «было», если строки не менялись. Живое снятие — обратной живой командой, пока игрок в игре.",
        "Offline — the previous rows if they have not changed. A live revoke — by the reverse live command while the player is in game.",
        "Снять звание, как сервер.", "Revoke a title as the server does.", "Character: revoke title"),
    "tutorial.set": D(
        ["game_db"], "Joy1.CharTutorial — биты шагов обучения Tutorial1…4.", "Joy1.CharTutorial — tutorial step bits Tutorial1…4.", "journal", *_ROWS_U,
        hr="Отметить или снять шаги обучения. Снятый шаг сервер наградит опытом ещё раз.",
        he="Set or clear tutorial steps. A cleared step is rewarded with experience again by the server.", te="Character: tutorial steps",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "pet.delete": D(
        ["game_db"], "Joy1.CharPetList — строка питомца удаляется.", "Joy1.CharPetList — the pet row is deleted.",
        "journal", "Питомец вставляется заново — с новым PetUnique.", "The pet is inserted again — with a new PetUnique.",
        "Удалить питомца персонажа не в игре.", "Delete an offline character's pet.", "Pet: delete", rr=_OFF_R[0], re=_OFF_R[1]),
    "pet.level": D(
        ["game_db"], "Joy1.CharPetList — PetLvl (не выше потолка PetMaxLvl) и PetExp начала уровня.",
        "Joy1.CharPetList — PetLvl (not above PetMaxLvl) and the PetExp of the level start.", "journal", *_ROWS_U,
        hr="Задать уровень питомца в пределах его потолка.", he="Set a pet's level within its cap.", te="Pet: level", rr=_OFF_R[0], re=_OFF_R[1]),
    "pet.rename": D(
        ["game_db"], "Joy1.CharPetList — кличка PetName, NameFlag = 0.", "Joy1.CharPetList — PetName, NameFlag = 0.", "journal", *_ROWS_U,
        hr="Сменить кличку питомца (1–14 знаков, латиница, цифры, «-», «_»).", he="Rename a pet (1–14 characters: Latin letters, digits, “-”, “_”).",
        te="Pet: rename", rr=_OFF_R[0], re=_OFF_R[1]),
    # ------------------------------------------------------------------ связи
    "soulmate.break": D(
        ["game_db"], "Joy1: SoulMate (State 0 обеих строк), Charinfo.Share = 0 у всех персонажей обеих учёток, кристаллы опыта Друга изымаются "
        "(adm.ItemTake), журнал JoyLog1.SoulMate «Panel Breakup».", "Joy1: SoulMate (State 0 on both rows), Charinfo.Share = 0 for all characters "
        "of both accounts, soulmate experience crystals taken (adm.ItemTake), log JoyLog1.SoulMate “Panel Breakup”.", "journal", *_ROWS_LOG_U,
        hr="Разорвать связь соулмейтов, когда обе учётки не в игре.", he="Break a soulmate link while both accounts are offline.",
        te="Soulmate: break link", rr=_OFF_R[0], re=_OFF_R[1]),
    "soulmate.friendship": D(
        ["game_db"], "Joy1.SoulMate — FriendShip обеих строк, FinalDate = NULL, журнал JoyLog1.SoulMateinfo.",
        "Joy1.SoulMate — FriendShip on both rows, FinalDate = NULL, log JoyLog1.SoulMateinfo.", "journal", *_ROWS_LOG_U,
        hr="Задать дружбу пары (0…255).", he="Set the pair's friendship (0…255).", te="Soulmate: friendship", rr=_OFF_R[0], re=_OFF_R[1]),
    "soulmate.level": D(
        ["game_db"], "Joy1.SoulMate — SmLvl и SmExp обеих строк, журнал JoyLog1.SoulMateLevelUp.",
        "Joy1.SoulMate — SmLvl and SmExp on both rows, log JoyLog1.SoulMateLevelUp.", "journal", *_ROWS_LOG_U,
        hr="Задать уровень связи (1…30).", he="Set the link level (1…30).", te="Soulmate: link level", rr=_OFF_R[0], re=_OFF_R[1]),
    "soulmate.link": D(
        ["game_db"], "Joy1.SoulMate — пара строк (восстановление из истории или новый Smidx), журнал JoyLog1.SoulMate «Panel …».",
        "Joy1.SoulMate — a row pair (restored from history or a new Smidx), log JoyLog1.SoulMate “Panel …”.", "journal", *_ROWS_LOG_U,
        hr="Связать две учётки, как сервер при согласии обоих.", he="Link two accounts as the server does when both agree.",
        te="Soulmate: link accounts", rr=_OFF_R[0], re=_OFF_R[1]),
    "soulmate.share_fix": D(
        ["game_db"], "Joy1.Charinfo.Share = 0 у персонажей учёток без активной связи.", "Joy1.Charinfo.Share = 0 for characters of accounts without an active link.",
        "journal", *_ROWS_U, hr="Сверка Share после сбоев (на живых данных — только по слову владельца).",
        he="Share consistency fix after failures (on live data — only on the owner's word).", te="Soulmate: Share fix", rr=_OFF_R[0], re=_OFF_R[1]),
    "friend.add": D(
        ["game_db"], "Joy1.CharFriend — недостающие строки обеих сторон дружбы.", "Joy1.CharFriend — the missing rows on both sides of the friendship.",
        "journal", *_ROWS_U, hr="Добавить друга персонажу не в игре (лимит 50 у каждого).", he="Add a friend to an offline character (limit 50 each).",
        te="Friends: add", rr=NO_RESTART[0] + " (список читается сервером при открытии окна)", re=NO_RESTART[1] + " (the server reads the list when the window opens)"),
    "friend.delete": D(
        ["game_db"], "Joy1.CharFriend — строки обеих сторон удаляются.", "Joy1.CharFriend — rows on both sides are deleted.", "journal", *_ROWS_U,
        hr="Удалить друга из списка (у обоих).", he="Remove a friend from the list (for both).", te="Friends: delete"),
    "friend.names": D(
        ["game_db"], "Joy1.CharFriend.Charname ← нынешнее имя друга.", "Joy1.CharFriend.Charname ← the friend's current name.", "journal", *_ROWS_U,
        hr="Обновить устаревшие имена в списке друзей (на живых данных — только по слову владельца).",
        he="Update stale names in the friend list (on live data — only on the owner's word).", te="Friends: refresh names"),
    "clan.captain": D(
        ["game_db"], "Joy1: ClanData (глава), ClanMember (Grade: прежний глава 4, новый 1), журнал JoyLog1.ClanLog.",
        "Joy1: ClanData (leader), ClanMember (Grade: old leader 4, new 1), log JoyLog1.ClanLog.", "journal", *_ROWS_LOG_U,
        hr="Сменить главу клана, когда все члены клана не в игре.", he="Change the clan leader while all members are offline.", te="Clan: change leader",
        rr="Не нужен: все члены не в игре, GameServer перечитает клан при входе любого члена.",
        re="Not needed: all members are offline, GameServer reloads the clan when any member logs in."),
    "clan.disband": D(
        ["game_db"], "Joy1: ClanMember, ClanData, CampClanData и ClanNotice удаляются, CampOwnerData.MvpClanIndex → −1, журнал JoyLog1.ClanLog.",
        "Joy1: ClanMember, ClanData, CampClanData and ClanNotice are deleted, CampOwnerData.MvpClanIndex → −1, log JoyLog1.ClanLog.",
        "journal", "Клан возвращается из снимка (объявления — с новыми номерами), если с тех пор ничего не менялось. Строки журнала JoyLog1.ClanLog остаются.",
        "The clan comes back from the snapshot (notices with new numbers) if nothing has changed since. The JoyLog1.ClanLog rows stay.",
        "Распустить клан при любом числе членов (все не в игре).", "Disband a clan with any number of members (all offline).", "Clan: disband"),
    "clan.kick": D(
        ["game_db"], "Joy1: ClanMember (строка члена или заявки), ClanData.JoinCnt − 1, журнал JoyLog1.ClanLog.",
        "Joy1: ClanMember (member or application row), ClanData.JoinCnt − 1, log JoyLog1.ClanLog.", "journal", *_ROWS_LOG_U,
        hr="Исключить члена клана или снять заявку (главу — нельзя, сначала сменить главу).",
        he="Expel a clan member or cancel an application (not the leader — change the leader first).", te="Clan: expel member"),
    "clan.mark_reset": D(
        ["game_db"], "Joy1.ClanData — 6 чисел эмблемы → 0, журнал JoyLog1.ClanLog.", "Joy1.ClanData — the 6 emblem numbers → 0, log JoyLog1.ClanLog.",
        "journal", "Числа эмблемы возвращаются. Предмет-эмблема, израсходованный при её установке, не возвращается ни откатом, ни сбросом. Строки журнала JoyLog1.ClanLog остаются.",
        "The emblem numbers come back. The emblem item spent when it was set is not returned by either the reset or the undo. The JoyLog1.ClanLog rows stay.",
        "Сбросить эмблему клана (все члены не в игре).", "Reset a clan emblem (all members offline).", "Clan: reset emblem"),
    "clan.notice_add": D(
        ["game_db"], "Joy1.ClanNotice — новое объявление (при 5 записях удаляется самое старое).",
        "Joy1.ClanNotice — a new notice (with 5 notices the oldest is deleted).",
        "journal", "Добавленное удаляется, вытесненное возвращается — с новым номером.", "The added notice is deleted, the pushed-out one comes back with a new number.",
        "Добавить объявление на доску клана — члены могут быть в игре (доска читается живьём).",
        "Add a notice to the clan board — members may be in game (the board is read live).", "Clan: add notice"),
    "clan.notice_delete": D(
        ["game_db"], "Joy1.ClanNotice — объявление удаляется.", "Joy1.ClanNotice — the notice is deleted.",
        "journal", "Объявление возвращается — с новым номером.", "The notice comes back with a new number.",
        "Удалить объявление с доски клана.", "Delete a notice from the clan board.", "Clan: delete notice"),
    # ------------------------------------------------------------------ предметы
    "gold.set": D(
        ["game_db"], "Joy1.Item — строка золота (код 20551) в сумке 2.", "Joy1.Item — the gold row (code 20551) in bag 2.", "journal", *_ROWS_U,
        hr="Задать золото персонажа не в игре (0 … 2 147 483 647).", he="Set an offline character's gold (0 … 2,147,483,647).", te="Gold: set",
        rr=_OFF_R[0], re=_OFF_R[1]),
    "items.edit": D(
        ["game_db"], "Joy1.Item — свойства экземпляра: ступень заточки и Updamage, опции, гнёзда (самоцветы), прочность, привязка.",
        "Joy1.Item — instance properties: upgrade step and Updamage, options, sockets (gems), durability, binding.",
        "journal", "Прежние значения возвращаются по Uuid, если предмет с тех пор не менялся. Снятый самоцвет в сумку не возвращается и откатом не вернётся, "
        "если предмет менялся.", "The old values come back by Uuid if the item has not changed since. A removed gem is not put into the bag.",
        "Править характеристики снаряжения только допустимыми для этого предмета значениями.",
        "Edit gear stats only with values allowed for that item.", "Items: edit properties", rr=_OFF_R[0], re=_OFF_R[1]),
    "items.give": D(
        ["game_db", "live"], "Joy1.Item (процедура adm.ItemGive: сумки 1, 2 или склад), журналы adm.ItemLedger и JoyLog1.AdminitemLog. Игрок в игре "
        "(мост v82) — выдача живьём.", "Joy1.Item (procedure adm.ItemGive: bags 1, 2 or the warehouse), logs adm.ItemLedger and JoyLog1.AdminitemLog. "
        "Player in game (bridge v82) — a live give.",
        "journal", "Выданное изымается (adm.ItemUndo), если предмет с тех пор не менялся. Живую выдачу — после выхода игрока. Строки adm.ItemLedger и JoyLog1.AdminitemLog остаются.",
        "What was given is taken back (adm.ItemUndo) if it has not changed since. A live give — after the player logs out. The adm.ItemLedger and JoyLog1.AdminitemLog rows stay.",
        "Выдать предмет персонажу с выбором опций (или «Случайно», как сервер).", "Give an item to a character with chosen options (or “Random”, as the server).",
        "Items: give"),
    "items.move": D(
        ["game_db"], "Joy1.Item — места предметов (сумки, склад, надето), Owner и MaxupCnt как у сервера.",
        "Joy1.Item — item places (bags, warehouse, equipped), Owner and MaxupCnt as the server sets them.",
        "journal", "Места, Owner и MaxupCnt возвращаются, если предметы с тех пор не двигались.",
        "Places, Owner and MaxupCnt come back if the items have not moved since.",
        "Переставить, надеть или снять предметы персонажа не в игре по правилам сервера.",
        "Move, equip or unequip an offline character's items under the server rules.", "Items: move / equip / unequip", rr=_OFF_R[0], re=_OFF_R[1]),
    "items.post": D(
        ["game_db"], "Joy1.ItemPostBox — строки элитного почтового ящика (подарок позиции витрины или премиум-почта): персонажу, учётке или всем игрокам.",
        "Joy1.ItemPostBox — premium mailbox rows (a showcase gift or premium mail): to a character, an account or all players.",
        "journal", "Строки удаляются, пока подарок не забран и получатели не в игре.",
        "The rows are deleted while the gift is not collected and the recipients are offline.",
        "Подарить позицию витрины или прислать предмет премиум-почтой. Забирает игрок сам, в том числе в игре.",
        "Gift a showcase item or send an item by premium mail. The player collects it, also while in game.", "Items: gift / premium mail"),
    "items.recover": D(
        ["game_db"], "Joy1.Item — предмет тем же номером по журналу уничтожения (adm.ItemRecover), при продаже NPC списывается золото продажи, журналы "
        "adm.ItemLedger и JoyLog1.AdminitemLog.", "Joy1.Item — the item with the same serial from the destruction log (adm.ItemRecover), for an NPC sale "
        "the sale gold is charged, logs adm.ItemLedger and JoyLog1.AdminitemLog.",
        "journal", "Предмет убирается и списанное золото возвращается, если предмет с тех пор не менялся. Строки adm.ItemLedger и JoyLog1.AdminitemLog остаются.",
        "The item is removed and the charged gold returned if the item has not changed since. The adm.ItemLedger and JoyLog1.AdminitemLog rows stay.",
        "Вернуть выброшенный, проданный NPC, разобранный или снятый по таймауту лот тем же номером (защита от дюпа).",
        "Return an item that was dropped, sold to an NPC, disassembled or a timed-out lot, with the same serial (dupe-safe).",
        "Items: recover by logs", rr=_OFF_R[0], re=_OFF_R[1]),
    "items.take": D(
        ["game_db"], "Joy1.Item (adm.ItemTake: вся строка или часть стопки), снимок в adm.ItemLedger, журнал JoyLog1.AdminitemLog.",
        "Joy1.Item (adm.ItemTake: the whole row or part of a stack), snapshot in adm.ItemLedger, log JoyLog1.AdminitemLog.",
        "journal", "Предмет возвращается в ту же ячейку, занята — в первую свободную той же сумки. Строки adm.ItemLedger и JoyLog1.AdminitemLog остаются.",
        "The item goes back to the same cell, if taken — to the first free cell of the same bag. The adm.ItemLedger and JoyLog1.AdminitemLog rows stay.",
        "Изъять предмет из сумок или склада персонажа не в игре.", "Take an item from an offline character's bags or warehouse.", "Items: take",
        rr=_OFF_R[0], re=_OFF_R[1]),
    # ------------------------------------------------------------------ посещаемость
    "attendance.credit": D(
        ["game_db"], "Joy1: AttendanceDetail (строка дня, Note «adm #N»), AttendanceCount.ACount + 1, журнал отметок adm.AttendanceAdjustLog "
        "(процедура adm.AttendanceAdjust).", "Joy1: AttendanceDetail (a day row, Note “adm #N”), AttendanceCount.ACount + 1, adjust log "
        "adm.AttendanceAdjustLog (procedure adm.AttendanceAdjust).",
        "journal", "Обратная правка процедурой (один раз). Если записи журнала действий нет (сбой после фиксации) — attendance.undo_log.",
        "The reverse adjustment by the procedure (once). If the action journal has no record (failure after commit) — attendance.undo_log.",
        "Засчитать прошедший день посещаемости, которого нет. Награда 68788 не выдаётся.",
        "Credit a past attendance day that is missing. The 68788 reward is not given.", "Attendance: credit a day",
        rr="Не нужен: правка видна при следующем визите к NPC.", re="Not needed: the change shows on the next NPC visit."),
    "attendance.revoke": D(
        ["game_db"], "Joy1: строка AttendanceDetail этого дня удаляется, ACount − 1, журнал отметок adm.AttendanceAdjustLog.",
        "Joy1: the AttendanceDetail row of that day is deleted, ACount − 1, adjust log adm.AttendanceAdjustLog.",
        "journal", "Снятая строка возвращается с прежними RegistDay и Note. Выданный когда-то предмет остаётся у игрока и после снятия.",
        "The removed row comes back with the old RegistDay and Note. An item given earlier stays with the player even after the revoke.",
        "Снять прошедший засчитанный день.", "Revoke a past credited day.", "Attendance: revoke a day",
        rr="Не нужен: правка видна при следующем визите к NPC.", re="Not needed: the change shows on the next NPC visit."),
    "attendance.undo_log": D(
        ["game_db"], "Joy1 — та же процедура adm.AttendanceAdjust с @UndoOf по строке adm.AttendanceAdjustLog.",
        "Joy1 — the same procedure adm.AttendanceAdjust with @UndoOf by an adm.AttendanceAdjustLog row.",
        "inverse", "Своего отката нет — повторить исходное можно новой правкой.", "It has no undo of its own — repeat the original by a new adjustment.",
        "Откат правки посещаемости по журналу отметок — для правок без записи «ok» в журнале действий. Только владелец.",
        "Undo an attendance adjustment by the adjust log — for adjustments without an “ok” journal record. Owner only.",
        "Attendance: undo by the adjust log", inv=("attendance.credit", "attendance.revoke")),
    # ------------------------------------------------------------------ живьём
    "live.announce": D(
        ["live", "panel_db", "discord"], "Мост → все GameServer: объявление 3113 всем игрокам. С флажком «и в Discord» — запись AsdaAdmin.adm.Outbox, "
        "бот Oracle публикует её в выбранный канал после объявления в игру.", "Bridge → all GameServers: notice 3113 to all players. With “and in "
        "Discord” — an AsdaAdmin.adm.Outbox record, the Oracle bot posts it to the chosen channel after the in-game notice.",
        "irreversible", "Объявление уже показано игрокам. Запись Discord до публикации можно отменить (outbox.cancel), после — удалить (outbox.delete).",
        "The notice has already been shown to players. A Discord record can be cancelled before posting (outbox.cancel), deleted after (outbox.delete).",
        "Объявление всем игрокам в игре, по флажку — и в Discord. Можно по расписанию.",
        "A notice to all players in game, optionally also to Discord. Can be scheduled.", "Live: notice to all players"),
    "live.kick": D(
        ["live"], "Мост → GameServer: игрок отключается с сервера, выход пишется штатно.",
        "Bridge → GameServer: the player is disconnected, the logout is saved as usual.",
        "irreversible", "Игрок может войти снова сам.", "The player can log in again by himself.",
        "Отключить игрока с сервера (например, перед правкой персонажа).", "Disconnect a player from the server (for example before a character edit).",
        "Live: disconnect a player"),
    "live.mob_pop": D(
        ["live"], "Мост → GameServer карты: группа монстров вызывается к персонажу служебной учётки с GM-флагом (6045). Обычные мобы группы получают "
        "точку появления у оператора, событийные — возрождаются снова и снова.", "Bridge → the map's GameServer: a monster group is summoned to a "
        "GM-flagged service account character (6045). Ordinary mobs of the group get their spawn point at the operator, event mobs respawn again and again.",
        "irreversible", "Убрать живых мобов можно live.mob_return, но точка появления группы остаётся сдвинутой до рестарта NpcServer (стойки) — 6046 её не возвращает.",
        "Live mobs can be removed with live.mob_return, but the group spawn point stays moved until a NpcServer (stack) restart — 6046 does not return it.",
        "Вызвать группу монстров карты к оператору (для событий и проверок). Подтверждение — словом mobs.",
        "Summon a map monster group to the operator (for events and tests). Confirmed with the word mobs.", "Live: summon a monster group",
        r="stack", rr="Точка появления группы вернётся только после рестарта стойки.", re="The group spawn point comes back only after a stack restart."),
    "live.mob_return": D(
        ["live"], "Мост → GameServer карты: группа монстров убирается (6046) — живые мобы группы погибают.",
        "Bridge → the map's GameServer: the monster group is removed (6046) — live mobs of the group die.",
        "irreversible", "Убитых мобов 6045 не вернёт, сдвинутая точка появления остаётся до рестарта стойки.",
        "6045 does not bring back the killed mobs, a moved spawn point stays until a stack restart.",
        "Убрать (вернуть) группу монстров.", "Remove (return) a monster group.", "Live: remove a monster group",
        r="stack", rr="Сдвинутая ранее точка появления вернётся только после рестарта стойки.", re="A previously moved spawn point comes back only after a stack restart."),
    "live.notice": D(
        ["live"], "Мост → GameServer: сообщение 3113 одному игроку на всех его узлах.", "Bridge → GameServer: notice 3113 to one player on all his nodes.",
        "irreversible", "Сообщение уже показано.", "The message has already been shown.",
        "Сообщение одному игроку в игре.", "A message to one player in game.", "Live: message to one player"),
    # ------------------------------------------------------------------ обслуживание, события
    "maint.on": D(
        ["game_db", "live"], "Joy1.adm.LoginMaintenance Mode 1 (процедура adm.LoginMaintenanceSet), объявление в игру мостом до включения, по желанию — "
        "отключение мостом игроков вне 1…5000.", "Joy1.adm.LoginMaintenance Mode 1 (procedure adm.LoginMaintenanceSet), an in-game notice via the "
        "bridge before switching on, optionally disconnecting players outside 1…5000 via the bridge.",
        "inverse", "Выключить — maint.off. Показанное объявление и отключение игроков не возвращаются.",
        "Switch off — maint.off. The shown notice and disconnected players are not undone.",
        "Режим обслуживания: вход только служебным учёткам 1…5000. Уже вошедших не отключает без галочки.",
        "Maintenance mode: login only for service accounts 1…5000. Does not disconnect players already in without the tick.",
        "Login: maintenance mode on", inv=("maint.off",),
        rr="Не нужен: новые входы закрываются сразу.", re="Not needed: new logins are closed at once."),
    "maint.off": D(
        ["game_db", "live"], "Joy1.adm.LoginMaintenance Mode 0 (adm.LoginMaintenanceSet), объявление мостом — по желанию.",
        "Joy1.adm.LoginMaintenance Mode 0 (adm.LoginMaintenanceSet), a bridge notice — optional.",
        "inverse", "Включить снова — maint.on.", "Switch on again — maint.on.",
        "Выключить режим обслуживания — вход снова всем.", "Switch maintenance mode off — login open to everyone again.",
        "Login: maintenance mode off", inv=("maint.on",)),
    "event.set": D(
        ["live", "panel_db"], "Мост → NpcServer канала (6038): событие опыта или добычи пишется в Event.dat всех NpcServer и зеркало GameServer, "
        "задание выключения event.off после конца окна (AsdaAdmin.adm.job). Перекрытые задания выключения снимаются.", "Bridge → the channel's "
        "NpcServers (6038): an experience or loot event is written to Event.dat of all NpcServers and the GameServer mirror, an event.off job after the "
        "window end (AsdaAdmin.adm.job). Overlapped switch-off jobs are cancelled.",
        "inverse", "Выключить — event.off (окно без года само повторяется каждый год, поэтому выключение ставится заданием). Опыт и добыча, полученные за время события, остаются.",
        "Switch off — event.off (the window has no year and repeats every year, so the switch-off is scheduled as a job). Experience and loot earned during the event stay.",
        "Включить событие опыта или добычи на окно времени сервера.", "Switch on an experience or loot event for a server time window.",
        "Event: switch on experience / loot event", inv=("event.off",),
        rr="Не нужен: NpcServer применяет событие сразу, Event.dat переживает рестарт.",
        re="Not needed: NpcServer applies the event at once, Event.dat survives a restart."),
    "event.off": D(
        ["live"], "Мост → NpcServer канала (6040): слот события выключается в Event.dat.", "Bridge → the channel's NpcServers (6040): the event slot is switched off in Event.dat.",
        "inverse", "Включить снова — event.set.", "Switch on again — event.set.",
        "Выключить событие опыта или добычи.", "Switch off an experience or loot event.", "Event: switch off", inv=("event.set",)),
    "rank.recalc": D(
        ["live", "game_db"], "Мост → GameServer (6020, P25): пересчёт рейтинговых званий 65…69, топа славы и условий званий у игроков в игре и запись в базу.",
        "Bridge → GameServer (6020, P25): recalculation of ranking titles 65…69, the fame top and title conditions for players in game, saved to the database.",
        "irreversible", "Рейтинговые звания игроков выдаются и снимаются заново, прежнее состояние не хранится. Пересчитать снова можно в любой момент.",
        "Ranking titles of players are granted and removed anew, the previous state is not kept. It can be recalculated again at any time.",
        "Пересчитать рейтинги и рейтинговые звания сейчас.", "Recalculate rankings and ranking titles now.", "Character: recalculate rankings"),
    "daily.reset": D(
        ["game_db"], "Joy1.CRT_LimitationQuest — дневные задания доски всем (adm.LimitationReset): «выполнено» и счётчик.",
        "Joy1.CRT_LimitationQuest — daily board quests of everyone (adm.LimitationReset): “done” and the counter.",
        "irreversible", "Прежние отметки не хранятся: и «догнать» (пропущенный суточный сброс), и внеочередной сброс дают игрокам пройти дневные задания ещё раз, вернуть это нельзя.",
        "The previous marks are not kept: both “catch up” (a missed daily reset) and an extra reset let players do the daily quests once more, this cannot be undone.",
        "Догнать пропущенный суточный сброс или сделать внеочередной.", "Catch up a missed daily reset or force an extra one.",
        "Daily quests: reset the board", r="relogin", rr="Игроки в игре увидят сброс после смены карты или перезахода (память GameServer сбрасывается только в 06:00).",
        re="Players in game see the reset after a map change or relogin (GameServer memory is reset only at 06:00)."),
    # ------------------------------------------------------------------ стойка и задания
    "stack.restart": D(
        ["stack", "discord", "live", "game_db", "panel_db"], "Процессы стойки: restart_stack.py --no-deploy с ПК — объявление ботом в Discord (#test-info, EN/AR/RU), 3 мин "
        "отсчёта в игре мостом, штатная остановка, паритет Ch2, старт. %s Запись управления стойкой — AsdaAdmin.adm.job." % _RS[0],
        "Stack processes: restart_stack.py --no-deploy from the PC — a bot announcement in Discord (#test-info, EN/AR/RU), a 3 min in-game countdown "
        "via the bridge, a clean stop, Ch2 parity, start. %s The stack control record — AsdaAdmin.adm.job." % _RS[1],
        "irreversible", "Рестарт прошёл: игроки отключались, объявление в Discord, отсчёт в игре и сброс CharPos / точек входа данжей не вернуть.",
        "The restart has happened: players were disconnected, the Discord announcement, the in-game countdown and the CharPos / dungeon entry reset "
        "cannot be undone.",
        "Перезапустить стойку с объявлением (только владелец, с ПК или заданием ПК).", "Restart the stack with an announcement (owner only, from the PC or a PC job).",
        "Stack: restart with announcement", r="stack", rr="Операция сама перезапускает стойку — игроки отключаются.",
        re="The operation restarts the stack itself — players are disconnected."),
    "stack.stop": D(
        ["stack", "discord", "live", "panel_db"], "Процессы стойки: restart_stack.py --stop-only — объявление в Discord, 3 мин отсчёта в игре, штатная остановка "
        "(сброса CharPos нет — он при запуске). Запись управления стойкой — AsdaAdmin.adm.job.",
        "Stack processes: restart_stack.py --stop-only — a Discord announcement, a 3 min in-game countdown, a clean stop (no CharPos reset — it happens "
        "at start). The stack control record — AsdaAdmin.adm.job.",
        "inverse", "Запустить снова — stack.start. Объявление в Discord и отключение игроков не вернуть.",
        "Start again — stack.start. The Discord announcement and the disconnected players cannot be undone.",
        "Остановить стойку на обслуживание с объявлением.", "Stop the stack for maintenance with an announcement.", "Stack: stop with announcement",
        r="stack", rr="Операция останавливает стойку — игра недоступна до stack.start.", re="The operation stops the stack — the game is down until stack.start.",
        inv=("stack.start",)),
    "stack.start": D(
        ["stack", "game_db", "panel_db"], "Процессы стойки: restart_stack.py --start-only — запуск целиком остановленной стойки, без объявления. %s Запись "
        "управления стойкой — AsdaAdmin.adm.job." % _RS[0], "Stack processes: restart_stack.py --start-only — start of a fully stopped stack, no "
        "announcement. %s The stack control record — AsdaAdmin.adm.job." % _RS[1],
        "inverse", "Остановить снова — stack.stop. Сброс CharPos и точек входа данжей не возвращается.",
        "Stop again — stack.stop. The CharPos and dungeon entry reset is not undone.",
        "Запустить остановленную стойку (именно так, а не start.bat: иначе не будет сброса CharPos и точек входа данжей).",
        "Start the stopped stack (this way, not start.bat: otherwise there is no CharPos and dungeon entry reset).", "Stack: start the stopped stack",
        r="stack", rr="Это и есть запуск стойки.", re="This is the stack start itself.", inv=("stack.stop",)),
    "job.add": D(
        ["panel_db"], "AsdaAdmin.adm.job — задание (операция, время UTC, повтор daily / weekly, подтверждения операции).",
        "AsdaAdmin.adm.job — a job (operation, UTC time, daily / weekly repeat, the operation's confirmations).",
        "inverse", "Отменить до исполнения — job.cancel.", "Cancel before it runs — job.cancel.",
        "Поставить операцию в задания на время или по расписанию (исполнит служба или консоль ПК).",
        "Schedule an operation for a time or on a repeat (run by the service or the PC console).", "Jobs: add", inv=("job.cancel",)),
    "job.cancel": D(
        ["panel_db"], "AsdaAdmin.adm.job — задание отменено.", "AsdaAdmin.adm.job — the job is cancelled.",
        "inverse", "Поставить снова — job.add.", "Schedule again — job.add.",
        "Отменить задание до исполнения.", "Cancel a job before it runs.", "Jobs: cancel", inv=("job.add",)),
    "job.release": D(
        ["panel_db"], "AsdaAdmin.adm.job — зависшее «идёт» снимается (итог «ошибка»).", "AsdaAdmin.adm.job — a stuck “running” is cleared (result “failed”).",
        "inverse", "Само задание заново не исполняется — при нужде поставьте его снова (job.add).", "The job does not run again by itself — schedule it again if needed (job.add).",
        "Снять зависшее «идёт» у задания (после сбоя исполнителя). Если restart_stack.py ещё работает, станет возможным второе управление стойкой.",
        "Clear a stuck “running” job (after the runner failed). If restart_stack.py is still running, a second stack control becomes possible.",
        "Jobs: clear stuck “running”", inv=("job.add",)),
    # ------------------------------------------------------------------ наборы изменений
    "shop.cs_create": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — новый черновик набора изменений.", "AsdaAdmin.adm.changeset — a new change set draft.",
        "inverse", "Отменить набор — shop.cs_cancel.", "Cancel the set — shop.cs_cancel.",
        "Начать набор изменений данных игры (магазины, витрины, предметы, тексты, монстры, задания, звания, навыки, карты, настройки патчей).",
        "Start a game data change set (shops, showcases, items, texts, monsters, quests, titles, skills, maps, patch settings).",
        "Change sets: new", inv=("shop.cs_cancel",)),
    "shop.cs_edit": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — заголовок, заметка, порядок половин, «срочно».", "AsdaAdmin.adm.changeset — title, note, half order, “urgent”.",
        "inverse", "Вернуть прежние свойства той же операцией.", "Restore the previous properties with the same operation.",
        "Изменить свойства набора.", "Edit the set's properties.", "Change sets: properties", inv=("shop.cs_edit",)),
    "shop.cs_item_add": D(
        ["panel_db"], "AsdaAdmin.adm.changeset_item — позиция набора (в таблицах стойки и порта ничего не меняется).",
        "AsdaAdmin.adm.changeset_item — a set position (nothing changes in stack or port tables).",
        "inverse", "Убрать позицию — shop.cs_item_del.", "Remove the position — shop.cs_item_del.",
        "Добавить правку в набор.", "Add an edit to the set.", "Change sets: add position", inv=("shop.cs_item_del",)),
    "shop.cs_item_del": D(
        ["panel_db"], "AsdaAdmin.adm.changeset_item — позиция удаляется.", "AsdaAdmin.adm.changeset_item — the position is deleted.",
        "inverse", "Добавить снова — shop.cs_item_add.", "Add again — shop.cs_item_add.",
        "Убрать правку из набора.", "Remove an edit from the set.", "Change sets: remove position", inv=("shop.cs_item_add",)),
    "shop.cs_check": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — итог проверки по живой стойке и клиенту (таблицы не меняются).",
        "AsdaAdmin.adm.changeset — the check result against the live stack and client (tables are not changed).",
        "nothing", "Проверка ничего не пишет в таблицы — её можно повторить.", "The check writes nothing to the tables — it can be repeated.",
        "Проверить набор: ошибки, предупреждения, баланс, «на руках у игроков».", "Check the set: errors, warnings, balance, “held by players”.",
        "Change sets: check"),
    "shop.cs_approve": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — статус «утверждён».", "AsdaAdmin.adm.changeset — status “approved”.",
        "inverse", "Вернуть в черновик — shop.cs_reopen (пока ничего не применено).", "Back to draft — shop.cs_reopen (while nothing is applied).",
        "Утвердить проверенный набор (сильная правка баланса — второе подтверждение).", "Approve a checked set (a strong balance change needs a second confirmation).",
        "Change sets: approve", inv=("shop.cs_reopen",)),
    "shop.cs_reopen": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — статус «черновик».", "AsdaAdmin.adm.changeset — status “draft”.",
        "inverse", "Утвердить снова — shop.cs_check и shop.cs_approve.", "Approve again — shop.cs_check and shop.cs_approve.",
        "Вернуть набор в черновик для правки (ничего не применено).", "Return a set to draft for editing (nothing applied).",
        "Change sets: back to draft", inv=("shop.cs_check", "shop.cs_approve")),
    "shop.cs_cancel": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — набор отменён (у выпущенного — отменяется невыложенная серверная половина).",
        "AsdaAdmin.adm.changeset — the set is cancelled (for a released one — the unapplied server half is cancelled).",
        "irreversible", "Отменённый набор не возвращается — нужное соберите новым набором.", "A cancelled set does not come back — build what is needed as a new set.",
        "Отменить набор, в котором ничего не применялось.", "Cancel a set in which nothing was applied.", "Change sets: cancel"),
    "shop.cs_server_dry": D(
        ["panel_db", "pc"], "AsdaAdmin.adm.changeset — состояние сухого прогона. На ПК выкладчик собирает манифест набора и прогоняется без записи в стойку, служба "
        "только сверяет md5 базы.", "AsdaAdmin.adm.changeset — the dry run state. On the PC the deployer builds the set manifest and runs without writing to "
        "the stack, the service only checks the base md5.",
        "nothing", "Файлы стойки не меняются.", "Stack files are not changed.",
        "Сухой прогон серверной половины перед выкладкой.", "Dry run of the server half before applying.", "Change sets: server half dry run"),
    "shop.cs_client_dry": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — состояние сухого прогона клиентской половины (правки RawAssets и ведомостей — в памяти, без записи и без UE).",
        "AsdaAdmin.adm.changeset — the client half dry run state (RawAssets and sheet edits in memory, no writes, no UE).",
        "nothing", "Файлы порта не меняются.", "Port files are not changed.",
        "Сухой прогон клиентской половины (только консоль ПК).", "Dry run of the client half (PC console only).", "Change sets: client half dry run"),
    "shop.cs_server_apply": D(
        ["server_files", "stack", "discord", "live", "game_db", "panel_db", "pc"], "Стойка: restart_stack.py с ПК — объявление в Discord, 3 мин отсчёта в игре, остановка, "
        "выкладка файлов набора во все копии процессов (бэкап .bak и v2\\_backup), паритет, старт (" + _RS[0].rstrip(".") + "). На ПК — запись changelog, строка Server/Docs/INDEX.md "
        "и карточка набора. AsdaAdmin.adm.changeset — состояние по фактическим md5.", "Stack: restart_stack.py from the PC — a Discord announcement, a 3 min "
        "in-game countdown, stop, deployment of the set's files to all process copies (backups .bak and v2\\_backup), parity, start (" + _RS[1].rstrip(".") + "). On the PC — a changelog "
        "entry, a Server/Docs/INDEX.md row and the set card. AsdaAdmin.adm.changeset — state by the actual md5.",
        "inverse", "Откат — shop.cs_server_rollback (тоже с рестартом стойки). Купленное игроками по новым ценам и составу откат не вернёт — поэтому после продаж затронутых кодов откат требует второго подтверждения. Объявление в Discord, отключение игроков и сброс CharPos при рестарте не вернуть.",
        "Undo — shop.cs_server_rollback (also with a stack restart). What players bought at the new prices and contents is not returned by the undo — so after sales of affected codes the undo needs a second confirmation. The Discord announcement, disconnected players and the CharPos reset at the restart cannot be undone.",
        "Выложить серверную половину набора (только владелец, консоль ПК).", "Apply the server half of a set (owner only, PC console).",
        "Change sets: apply server half (stack restart)", r="stack", rr="Операция сама перезапускает стойку: GameServer читает таблицы только при старте.",
        re="The operation restarts the stack itself: GameServer reads the tables only at start.", inv=("shop.cs_server_rollback",)),
    "shop.cs_server_rollback": D(
        ["server_files", "stack", "discord", "live", "game_db", "panel_db", "pc"], "Стойка: restart_stack.py — объявление, остановка, возврат прежних файлов из бэкапа "
        "набора, старт (" + _RS[0].rstrip(".") + "). На ПК — запись changelog и карточки набора.", "Stack: restart_stack.py — announcement, stop, restoring the previous files from the "
        "set backup, start (" + _RS[1].rstrip(".") + "). On the PC — changelog and set card entries.",
        "inverse", "Выложить снова — shop.cs_server_apply. Откат необратим для купленного: что игроки уже купили по выложенным позициям, остаётся у них (после продаж — второе подтверждение). Объявление в Discord, отключение игроков и сброс CharPos при рестарте не вернуть.", "Apply again — shop.cs_server_apply. The rollback is irreversible for purchases: what players already bought from the applied positions stays with them (after sales — a second confirmation). The Discord announcement, disconnected players and the CharPos reset at the restart cannot be undone.",
        "Откатить серверную половину набора.", "Roll back the server half of a set.", "Change sets: roll back server half (stack restart)",
        r="stack", rr="Операция сама перезапускает стойку.", re="The operation restarts the stack itself.", inv=("shop.cs_server_apply",)),
    "shop.cs_server_sync": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — состояние серверной половины по md5 стойки (стойка только читается).",
        "AsdaAdmin.adm.changeset — the server half state by the stack md5 (the stack is only read).",
        "nothing", "Только сверка — стойка не меняется.", "Only a check — the stack is not changed.",
        "Сверить состояние серверной половины со стойкой после сбоя чтения.", "Re-sync the server half state with the stack after a read failure.",
        "Change sets: sync server half"),
    "shop.cs_client_apply": D(
        ["client", "pc", "panel_db"], "ПК: файлы RawAssets и ведомости порта, заливка DataTable через очередь UE (бэкап в @@ASTORY_DEV_ROOT_ESC@@\\_backup), запись changelog. "
        "AsdaAdmin.adm.changeset — состояние.", "PC: port RawAssets files and sheets, DataTable import via the UE queue (backup in @@ASTORY_DEV_ROOT_ESC@@\\_backup), a "
        "changelog entry. AsdaAdmin.adm.changeset — state.",
        "inverse", "Откат — shop.cs_client_rollback (пока не выпущено).", "Undo — shop.cs_client_rollback (until released).",
        "Записать клиентскую половину набора в порт (только консоль ПК, редактор UE закрыт). Выпуск клиента не делается.",
        "Write the client half of a set into the port (PC console only, UE editor closed). No client release is made.",
        "Change sets: apply client half (RawAssets / DT)", r="release", rr="До игроков дойдёт только с выпуском клиента.",
        re="It reaches players only with a client release.", inv=("shop.cs_client_rollback",)),
    "shop.cs_client_rollback": D(
        ["client", "pc", "panel_db"], "ПК: файлы порта возвращаются из бэкапа набора, DataTable перезаливается, запись changelog.",
        "PC: port files are restored from the set backup, DataTables re-imported, a changelog entry.",
        "inverse", "Применить снова — shop.cs_client_apply.", "Apply again — shop.cs_client_apply.",
        "Откатить клиентскую половину до выпуска.", "Roll back the client half before a release.", "Change sets: roll back client half",
        r="release", rr="Касается только следующего выпуска клиента.", re="Affects only the next client release.", inv=("shop.cs_client_apply",)),
    "shop.cs_released": D(
        ["panel_db"], "AsdaAdmin.adm.changeset — статус «выпущен с клиентом» (по Releases/releases.log).",
        "AsdaAdmin.adm.changeset — status “released with the client” (by Releases/releases.log).",
        "irreversible", "Отметка не снимается: после выпуска откат — только новым набором и новым выпуском.",
        "The mark is not removed: after a release a rollback is only a new set and a new release.",
        "Отметить, что клиентская половина вышла с выпуском клиента.", "Mark that the client half shipped with a client release.",
        "Change sets: mark “released with client”"),
    # ------------------------------------------------------------------ бэкапы
    "db.backup": D(
        ["server_files", "panel_db"], "Сервер: файл полного бэкапа базы в папке панели (BACKUP COPY_ONLY + RESTORE VERIFYONLY внутри подписанной adm.DbBackupRun), "
        "строка AsdaAdmin.adm.dbbackup. После бэкапа — ротация: удаляются бэкапы панели старше срока хранения. Из браузера — задание службы на «сейчас».",
        "Server: a full database backup file in the panel folder (BACKUP COPY_ONLY + RESTORE VERIFYONLY inside the signed adm.DbBackupRun), an "
        "AsdaAdmin.adm.dbbackup row. After the backup — rotation: panel backups older than the retention are deleted. From the browser — a service job “now”.",
        "irreversible", "Базу бэкап не меняет (COPY_ONLY не трогает чужую цепочку), но копии, удалённые ротацией, не вернуть. Лишний новый бэкап убирает db.prune.",
        "The backup does not change the database (COPY_ONLY leaves other chains alone), but copies deleted by rotation cannot be returned. An extra new backup is removed by db.prune.",
        "Сделать проверенный бэкап базы из белого списка (вручную или по расписанию).", "Make a verified backup of a whitelisted database (manually or scheduled).",
        "DB backups: make a backup"),
    "db.verify": D(
        ["panel_db"], "AsdaAdmin.adm.dbbackup — итог RESTORE VERIFYONLY по файлу бэкапа.", "AsdaAdmin.adm.dbbackup — the RESTORE VERIFYONLY result for a backup file.",
        "nothing", "Проверка ничего не меняет.", "The check changes nothing.",
        "Перепроверить файл бэкапа.", "Re-verify a backup file.", "DB backups: verify a file"),
    "db.prune": D(
        ["server_files", "panel_db"], "Сервер: файлы бэкапов панели в её папке удаляются по правилам хранения, строки adm.dbbackup отмечаются. Последние проверенные, "
        "недельные, месячные и чужие бэкапы — никогда.", "Server: panel backup files in its folder are deleted by the retention rules, adm.dbbackup rows are "
        "marked. The latest verified, weekly, monthly and foreign backups — never.",
        "irreversible", "Удалённые файлы бэкапов не вернуть.", "Deleted backup files cannot be returned.",
        "Убрать лишние старые бэкапы панели (только владелец, слово prune).", "Remove extra old panel backups (owner only, word prune).",
        "DB backups: remove old panel backups"),
    "db.release": D(
        ["panel_db"], "AsdaAdmin: зависшая строка adm.dbbackup «идёт» снимается (adm.DbBackupAbort), зависшие задания db.backup / db.verify в adm.job.",
        "AsdaAdmin: a stuck adm.dbbackup “running” row is cleared (adm.DbBackupAbort), stuck db.backup / db.verify jobs in adm.job.",
        "nothing", "Снимается только отметка — бэкап при нужде делается заново.", "Only the mark is cleared — make the backup again if needed.",
        "Снять зависший бэкап после сбоя.", "Clear a stuck backup after a failure.", "DB backups: clear a stuck backup"),
    "db.restore": D(
        ["none"], "Ничего: операция всегда отказывает — восстановления на живой сервер панель не делает.",
        "Nothing: the operation always refuses — the panel does not restore onto the live server.",
        "nothing", "Ничего не меняется.", "Nothing changes.",
        "Объясняет, почему восстановления на живой сервер нет, и куда идти (стенд LocalDB).",
        "Explains why there is no restore onto the live server and where to go instead (LocalDB stand).", "DB backups: restore onto the live server (refused)"),
    "db.restore_stand": D(
        ["pc", "panel_db"], "ПК: файл бэкапа скачивается в папку стенда и удаляется всегда, база <имя>_stand_<№> на LocalDB-стенде AstoryDbStand (удаляется, "
        "если не задан keep), итог в AsdaAdmin.adm.dbbackup. Живые базы не трогаются.", "PC: the backup file is downloaded to the stand folder and always "
        "deleted, a database <name>_stand_<no> on the LocalDB stand AstoryDbStand (deleted unless keep is set), the result in AsdaAdmin.adm.dbbackup. Live "
        "databases are untouched.",
        "nothing", "Живые базы не меняются, база стенда удаляется сама или вручную.", "Live databases do not change, the stand database is deleted by itself or by hand.",
        "Восстановить бэкап на стенд ПК и проверить его (CHECKDB, число строк). Только владелец, консоль ПК.",
        "Restore a backup to the PC stand and check it (CHECKDB, row counts). Owner only, PC console.", "DB backups: restore to the LocalDB stand"),
    "db.bakdrop": D(
        ["game_db", "panel_db"], "Игровые базы: DROP служебных копий таблиц и процедур с вердиктом «можно убрать» (подписанная adm.BakDrop), снимок DDL и строк — "
        "в AsdaAdmin.adm.bakdrop_log.", "Game databases: DROP of service copies of tables and procedures marked “can remove” (signed adm.BakDrop), a DDL "
        "and rows snapshot in AsdaAdmin.adm.bakdrop_log.",
        "irreversible", "Отмены нет. Вернуть объект — восстановить бэкап на стенд ПК и перенести вручную (DDL — в журнале удаления).",
        "No undo. To return an object — restore a backup to the PC stand and move it by hand (the DDL is in the drop log).",
        "Убрать доказанно лишние копии *_bak_* из игровых баз (только владелец, слово и второй фактор, свежий бэкап обязателен).",
        "Remove proven-unneeded *_bak_* copies from game databases (owner only, word and two-factor, a fresh backup is required).",
        "Service copies: drop"),
    # ------------------------------------------------------------------ античит
    "ac.daily": D(
        ["panel_db"], "AsdaAdmin.adm.AcDaily — прогон суточного отчёта античита (разбор по метрикам, события, Markdown). Файлов служба не пишет.",
        "AsdaAdmin.adm.AcDaily — a daily anti-cheat report run (metrics, events, Markdown). The service writes no files.",
        "nothing", "Отчёт только читает журналы и базы — откатывать нечего.", "The report only reads logs and databases — nothing to undo.",
        "Прогнать суточный отчёт античита за день (служба делает это сама в 00:20).", "Run the daily anti-cheat report for a day (the service does it itself at 00:20).",
        "Anti-cheat: daily report"),
    "case.open": D(
        ["game_db", "server_files"], "joylog1.san: новое дело AC-NNNN (san.UP_SAN_CaseOpen), снимок событий, manifest.json в каталоге дела службы.",
        "joylog1.san: a new case AC-NNNN (san.UP_SAN_CaseOpen), an events snapshot, manifest.json in the service case folder.",
        "inverse", "Дела не удаляются — закрыть — case.close.", "Cases are not deleted — close it — case.close.",
        "Открыть дело античита по учётке.", "Open an anti-cheat case for an account.", "Case: open", inv=("case.close",)),
    "case.attach": D(
        ["game_db", "server_files"], "joylog1.san.evidence и файлы выдержек журналов стойки (маска секретов, sha256) в каталоге дела службы на сервере.",
        "joylog1.san.evidence and server log excerpt files (secrets masked, sha256) in the service case folder on the server.",
        "irreversible", "Доказательства только дописываются, история дела не правится.", "Evidence is append-only, the case history is not edited.",
        "Приложить доказательства к делу.", "Attach evidence to a case.", "Case: attach evidence"),
    "case.export": D(
        ["server_files", "game_db"], "Файлы выгрузки событий (JSON / CSV) в каталоге дела на сервере, запись в журнале дела.",
        "Event export files (JSON / CSV) in the case folder on the server, an entry in the case log.",
        "nothing", "Выгрузка ничего не меняет в играх и решениях.", "The export changes nothing in the game or decisions.",
        "Выгрузить события дела в файлы.", "Export a case's events to files.", "Case: export events"),
    "case.decide": D(
        ["game_db", "server_files"], "joylog1.san.cases (ступень, решение), case_log, для ступени с блоком — операция account.block (своя запись журнала) и san.case_block. Обновляется manifest.json дела в каталоге службы.",
        "joylog1.san.cases (step, decision), case_log, for a blocking step — the account.block operation (its own journal record) and san.case_block. The case manifest.json in the service folder is updated.",
        "inverse", "Неисполненное решение отозвать — case.withdraw, блок дела снять — case.lift.", "Withdraw an unexecuted decision — case.withdraw, lift the case block — case.lift.",
        "Вынести решение по лестнице санкций (ступени 3+ — admin / owner, правило двух источников).",
        "Decide by the sanction ladder (steps 3+ — admin / owner, the two-sources rule).", "Case: decide", inv=("case.withdraw", "case.lift")),
    "case.execute": D(
        ["game_db", "server_files"], "joylog1.san.cases (исполнено, срок апелляции), case_log. Обновляется manifest.json дела в каталоге службы.",
        "joylog1.san.cases (executed, appeal deadline), case_log. The case manifest.json in the service folder is updated.",
        "irreversible", "Исполненное решение отменяется только апелляцией (case.appeal).", "An executed decision is reversed only by an appeal (case.appeal).",
        "Отметить ручное исполнение решения (кроме блока — его исполняет решение).", "Mark a manual execution of a decision (except a block — the decision executes it).",
        "Case: mark executed"),
    "case.withdraw": D(
        ["game_db", "server_files"], "joylog1.san.cases — решение снято, дело снова на доказательствах, запись в истории остаётся. Обновляется manifest.json дела в каталоге службы.",
        "joylog1.san.cases — the decision is withdrawn, the case is back to evidence, the history entry stays. The case manifest.json in the service folder is updated.",
        "inverse", "Вынести решение заново — case.decide.", "Decide again — case.decide.",
        "Отозвать вынесенное, но не исполненное решение.", "Withdraw a decision that has not been executed.", "Case: withdraw decision", inv=("case.decide",)),
    "case.appeal": D(
        ["game_db", "server_files"], "joylog1.san: апелляция или её решение (статус дела, case_log). Обновляется manifest.json дела в каталоге службы.",
        "joylog1.san: an appeal or its resolution (case status, case_log). The case manifest.json in the service folder is updated.",
        "irreversible", "История дела только дописывается. Пересматривает другое лицо (другая учётка панели).",
        "The case history is append-only. The review is done by another person (another panel account).",
        "Принять апелляцию или вынести по ней решение (в силе / отменено).", "Accept an appeal or resolve it (upheld / overturned).", "Case: appeal"),
    "case.lift": D(
        ["game_db", "server_files"], "Операция account.unblock (своя запись журнала: BlockList → BlockHistory, us_block 0), joylog1.san.case_block (снят), case_log. Обновляется manifest.json дела в каталоге службы.",
        "The account.unblock operation (its own journal record: BlockList → BlockHistory, us_block 0), joylog1.san.case_block (lifted), case_log. The case manifest.json in the service folder is updated.",
        "inverse", "Поставить блок снова — новым решением дела (case.decide).", "Block again — by a new case decision (case.decide).",
        "Снять блок, наложенный делом.", "Lift the block imposed by a case.", "Case: lift block", inv=("case.decide",)),
    "case.close": D(
        ["game_db", "server_files"], "joylog1.san.cases (итог, закрыто), case_log. Обновляется manifest.json дела в каталоге службы.",
        "joylog1.san.cases (outcome, closed), case_log. The case manifest.json in the service folder is updated.",
        "irreversible", "Закрытое дело пересматривается только апелляцией (case.appeal).", "A closed case is reviewed only by an appeal (case.appeal).",
        "Закрыть дело с итогом.", "Close a case with an outcome.", "Case: close"),
    "case.rollback_report": D(
        ["game_db", "server_files"], "joylog1.san.evidence — отчёт «что откатить» по Serial (вид report) и его файл в каталоге дела.",
        "joylog1.san.evidence — a “what to roll back” report by Serial (kind report) and its file in the case folder.",
        "nothing", "Отчёт только для решения — предметы игроков не трогаются.", "The report is only for the decision — player items are untouched.",
        "Составить отчёт «что откатить» по серийникам предметов.", "Build a “what to roll back” report by item serials.", "Case: rollback report by Serial"),
    # ------------------------------------------------------------------ чат, имена, жалобы
    "chat.mute": D(
        ["game_db"], "joylog1.chat.mute — заглушка на учётку или персонажа на срок (процедура chat.UP_ChatMuteSet).",
        "joylog1.chat.mute — a mute on an account or character for a period (procedure chat.UP_ChatMuteSet).",
        "journal", "Заглушка снимается (UP_ChatMuteLift).", "The mute is lifted (UP_ChatMuteLift).",
        "Заглушить чат нарушителю с причиной.", "Mute an offender's chat with a reason.", "Chat: mute",
        rr="Не нужен: действует не позже чем через 15 с (кэш AsdaPatch P129).", re="Not needed: takes effect within 15 s (AsdaPatch P129 cache)."),
    "chat.unmute": D(
        ["game_db"], "joylog1.chat.mute — досрочное снятие (chat.UP_ChatMuteLift).", "joylog1.chat.mute — early lift (chat.UP_ChatMuteLift).",
        "journal", "Заглушка ставится снова до прежнего конца срока.", "The mute is set again until the original end.",
        "Снять заглушку досрочно с причиной.", "Lift a mute early with a reason.", "Chat: unmute",
        rr="Не нужен: действует не позже чем через 15 с.", re="Not needed: takes effect within 15 s."),
    "names.mark": D(
        ["panel_db"], "AsdaAdmin.adm.NameReview — отметка «ок / сменить» с байтами имени (только добавление). Само имя не меняется.",
        "AsdaAdmin.adm.NameReview — an “ok / change” mark with the name bytes (insert only). The name itself is not changed.",
        "inverse", "Новая отметка той же операцией заменяет прежнюю (история не правится). Сменить имя — char.rename.",
        "A new mark by the same operation replaces the old one (history is not edited). To rename — char.rename.",
        "Отметить имя из очереди как допустимое или требующее смены.", "Mark a queued name as acceptable or needing a change.", "Names: mark",
        inv=("names.mark",)),
    "report.take": D(
        ["panel_db"], "AsdaAdmin.adm.PlayerReport — жалоба взята в работу (статус «взята», кто и когда).",
        "AsdaAdmin.adm.PlayerReport — the report is taken (status “taken”, who and when).",
        "irreversible", "Вернуть жалобу в «новые» нельзя — отметка остаётся, закрыть её может взявший или admin / owner.",
        "The report cannot be returned to “new” — the mark stays, the taker or admin / owner can close it.",
        "Взять жалобу в работу.", "Take a report.", "Reports: take"),
    "report.close": D(
        ["panel_db"], "AsdaAdmin.adm.PlayerReport — закрыта с итогом и пояснением. Автору ничего не отправляется.",
        "AsdaAdmin.adm.PlayerReport — closed with an outcome and an explanation. Nothing is sent to the author.",
        "irreversible", "Закрытую жалобу из панели снова не открыть — при нужде подаётся новая.", "A closed report cannot be reopened from the panel — a new one is filed if needed.",
        "Закрыть жалобу с итогом (меры, дело, нарушения нет, повтор, мало данных).", "Close a report with an outcome (action, case, no violation, duplicate, insufficient).",
        "Reports: close"),
    "report.case": D(
        ["panel_db"], "AsdaAdmin.adm.PlayerReport — связь жалобы с делом AC-NNNN (дело открывает case.open).",
        "AsdaAdmin.adm.PlayerReport — the report's link to a case AC-NNNN (the case is opened by case.open).",
        "irreversible", "Связь с делом не снимается — она только справочная.", "The case link is not removed — it is reference only.",
        "Связать жалобу с делом античита.", "Link a report to an anti-cheat case.", "Reports: link to a case"),
    "report.reply": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.PlayerReportReply — ответ в очереди, бот на ПК раз в минуту шлёт его автору личным сообщением в Discord.",
        "AsdaAdmin.adm.PlayerReportReply — a queued reply, the bot on the PC sends it to the author as a Discord direct message once a minute.",
        "irreversible", "Отправленное личное сообщение не отозвать.", "A sent direct message cannot be recalled.",
        "Ответить автору жалобы (не больше 5 ответов на жалобу и 20 в час).", "Reply to the report author (at most 5 replies per report and 20 per hour).",
        "Reports: reply to the author"),
    "reports.purge": D(
        ["panel_db"], "AsdaAdmin — байты скриншотов закрытых жалоб старше срока хранения → пусто (имя, тип, размер и sha256 остаются).",
        "AsdaAdmin — screenshot bytes of closed reports older than the retention → empty (name, type, size and sha256 stay).",
        "irreversible", "Удалённые скриншоты не вернуть.", "Deleted screenshots cannot be returned.",
        "Срок хранения скриншотов жалоб (служба делает раз в сутки).", "Report screenshot retention (the service runs it daily).", "Reports: screenshot retention"),
    # ------------------------------------------------------------------ деньги, экономика
    "money.adjust": D(
        ["game_db"], "AsdaStoryLogin: баланс dbo.GP7Balance и журнал adm.GP7AdjustLog одной транзакцией (процедура adm.GP7Adjust). Покупки и выручка не меняются.",
        "AsdaStoryLogin: the dbo.GP7Balance balance and the adm.GP7AdjustLog log in one transaction (procedure adm.GP7Adjust). Purchases and revenue do not change.",
        "journal", "Обратная корректировка со ссылкой на исходную (один раз), со свежим кодом второго фактора.",
        "A reverse adjustment referring to the original (once), with a fresh two-factor code.",
        "Начислить или списать баланс gp7 (только владелец, лимиты, второе подтверждение и второй фактор).",
        "Credit or debit a gp7 balance (owner only, limits, second confirmation and two-factor).", "Money: adjust gp7 balance"),
    "econ.snapshot": D(
        ["panel_db"], "AsdaAdmin: adm.EconDaily / adm.EconDailyChar — снимок золота персонажей.", "AsdaAdmin: adm.EconDaily / adm.EconDailyChar — a snapshot of character gold.",
        "nothing", "Снимок только читает игровые базы — откатывать нечего.", "The snapshot only reads game databases — nothing to undo.",
        "Снять снимок золота сейчас (служба делает это сама раз в сутки).", "Take a gold snapshot now (the service does it daily).", "Economy: gold snapshot"),
    # ------------------------------------------------------------------ выпуски, сбои
    "release.push": D(
        ["panel_db"], "AsdaAdmin.adm.ReleasePcStatus — снимок конвейера выпуска с ПК (releases.log, Inbox, итоги батников, ключи «есть / срок», без секретов).",
        "AsdaAdmin.adm.ReleasePcStatus — a release pipeline snapshot from the PC (releases.log, Inbox, batch results, keys “present / expiry”, no secrets).",
        "nothing", "Снимок только отражает ПК — следующая отправка его обновит.", "The snapshot only mirrors the PC — the next push updates it.",
        "Прислать службе состояние выпуска с ПК (задание ПК или консоль).", "Send the release state from the PC to the service (a PC job or the console).",
        "Releases: push PC snapshot"),
    "release.prune": D(
        ["panel_db"], "AsdaAdmin.adm.ReleasePcStatus — удаляются снимки ПК, кроме последних (процедура adm.ReleasePcPrune).",
        "AsdaAdmin.adm.ReleasePcStatus — PC snapshots are deleted except the latest ones (procedure adm.ReleasePcPrune).",
        "irreversible", "Удалённые старые снимки не вернуть (история — только последние).", "Deleted old snapshots cannot be returned (history keeps only the latest).",
        "Убрать старые снимки ПК (служба делает раз в сутки).", "Remove old PC snapshots (the service does it daily).", "Releases: remove old PC snapshots"),
    "crash.sync": D(
        ["pc", "panel_db"], "ПК: новые .acrash скачиваются с сервера (scp) в @@ASTORY_DEV_ROOT_ESC@@\\_player_logs и расшифровываются там — уже на предпросмотре (кроме "
        "«без скачивания»). AsdaAdmin.adm.ClientCrash* — только сводка, при подтверждении.", "PC: new .acrash files are downloaded from the server (scp) "
        "to @@ASTORY_DEV_ROOT_ESC@@\\_player_logs and decrypted there — already at preview (unless “no fetch”). AsdaAdmin.adm.ClientCrash* — summary only, on confirmation.",
        "nothing", "Сводка только отражает пакеты LogDrop — следующая отправка её обновит. Скачанные на ПК пакеты остаются (на сервере они не удаляются).",
        "The summary only mirrors LogDrop packages — the next push updates it. Packages downloaded to the PC stay (they are not deleted on the server).",
        "Прислать службе сводку падений клиента (задание ПК или консоль). Ключ расшифровки с ПК не уходит.",
        "Send the client crash summary to the service (a PC job or the console). The decryption key never leaves the PC.",
        "Client crashes: push summary from the PC"),
    "crash.alog_prune": D(
        ["server_files"], "Сервер, папка LogDrop: удаляются .alog и их .json старше 60 суток. Пакеты .acrash не удаляются никогда.",
        "Server, LogDrop folder: .alog files and their .json older than 60 days are deleted. .acrash packages are never deleted.",
        "irreversible", "Удалённые журналы на сервере не вернуть (расшифрованные копии на ПК владельца остаются).",
        "Deleted logs on the server cannot be returned (decrypted copies on the owner PC stay).",
        "Срок хранения журналов клиента (только владелец, слово и второй фактор, без автоматики).",
        "Client log retention (owner only, word and two-factor, no automation).", "Client crashes: delete old .alog"),
    # ------------------------------------------------------------------ Discord: очередь и заметки
    "outbox.cancel": D(
        ["panel_db"], "AsdaAdmin.adm.Outbox — запись отменена до публикации.", "AsdaAdmin.adm.Outbox — the record is cancelled before posting.",
        "nothing", "В Discord ничего не уходило — нужное объявление поставьте заново.", "Nothing reached Discord — queue the needed announcement again.",
        "Отменить объявление Discord до публикации.", "Cancel a Discord announcement before posting.", "Discord: cancel before posting"),
    "outbox.retry": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.Outbox — запись снова в очереди, бот опубликует её в Discord (опубликованный номер повторно не публикуется).",
        "AsdaAdmin.adm.Outbox — the record is queued again, the bot posts it to Discord (an already posted number is not posted twice).",
        "inverse", "До публикации — outbox.cancel, после — outbox.delete.", "Before posting — outbox.cancel, after — outbox.delete.",
        "Повторить публикацию после ошибки или долгого молчания бота.", "Retry posting after an error or a long bot silence.", "Discord: retry",
        inv=("outbox.cancel", "outbox.delete")),
    "outbox.delete": D(
        ["discord", "panel_db"], "Discord: бот удаляет опубликованное сообщение (у форума — ветку). AsdaAdmin.adm.Outbox — отметка «удалено».",
        "Discord: the bot deletes the posted message (for the forum — the thread). AsdaAdmin.adm.Outbox — marked “deleted”.",
        "irreversible", "Сообщение исчезает у всех, кто уже прочитал — не вернуть.", "The message disappears for everyone, what was already read cannot be taken back.",
        "Удалить опубликованное из Discord (только владелец).", "Delete a posted message from Discord (owner only).", "Discord: delete a posted message"),
    "outbox.test": D(
        ["panel_db"], "AsdaAdmin.adm.Outbox — проверочная запись: бот её забирает и отмечает «тест», в Discord не публикует.",
        "AsdaAdmin.adm.Outbox — a test record: the bot claims it and marks “test”, nothing is posted to Discord.",
        "nothing", "В Discord ничего не уходит.", "Nothing reaches Discord.",
        "Проверить путь бота без публикации.", "Test the bot path without posting.", "Discord: test record (not posted)"),
    "notes.push": D(
        ["panel_db"], "AsdaAdmin: adm.NotesSnap (текущий changelog как есть) и реестр adm.NotesEntry. Файлы changelog не меняются.",
        "AsdaAdmin: adm.NotesSnap (the current changelog as is) and the adm.NotesEntry registry. Changelog files are not changed.",
        "nothing", "Снимок только отражает ПК — следующая отправка его обновит.", "The snapshot only mirrors the PC — the next push updates it.",
        "Прислать службе текущий changelog с ПК (задание ПК или консоль).", "Send the current changelog from the PC to the service (a PC job or the console).",
        "Release notes: push changelog from the PC"),
    "notes.resync": D(
        ["panel_db"], "AsdaAdmin: реестр adm.NotesEntry / NotesPostEntry по последнему снимку.", "AsdaAdmin: the adm.NotesEntry / NotesPostEntry registry from the latest snapshot.",
        "nothing", "Реестр пересобирается по снимку — в Discord ничего не уходит.", "The registry is rebuilt from the snapshot — nothing reaches Discord.",
        "Перечитать реестр записей после обновления разбора.", "Re-read the entry registry after a parser update.", "Release notes: resync registry"),
    "notes.draft": D(
        ["panel_db"], "AsdaAdmin.adm.NotesDraft — черновик (отмеченные записи, заголовок, тексты EN / RU / AR, роль, срок), одна строка.",
        "AsdaAdmin.adm.NotesDraft — the draft (ticked entries, title, EN / RU / AR texts, role, expiry), a single row.",
        "irreversible", "Прежний черновик перезаписывается и не хранится. Ничего не публикуется.", "The previous draft is overwritten and not kept. Nothing is published.",
        "Сохранить черновик заметок для игроков.", "Save the player release notes draft.", "Release notes: save draft"),
    "notes.hide": D(
        ["panel_db"], "AsdaAdmin.adm.NotesEntry — записи скрываются из списка неопубликованного (с причиной) или возвращаются в него.",
        "AsdaAdmin.adm.NotesEntry — entries are hidden from the unpublished list (with a reason) or returned to it.",
        "journal", "Обратное действие: скрытые записи снова видны, возвращённые — снова скрыты.", "The reverse action: hidden entries become visible, returned ones hidden again.",
        "Скрыть записи changelog, которые игрокам публиковать не нужно, или вернуть скрытые.",
        "Hide changelog entries that should not be published to players, or return hidden ones.", "Release notes: hide or return entries"),
    "notes.mark": D(
        ["panel_db"], "AsdaAdmin.adm.NotesPost — отметка «опубликовано вне панели» для выбранных записей.",
        "AsdaAdmin.adm.NotesPost — a “published outside the panel” mark for the chosen entries.",
        "journal", "Отметка снимается — записи снова в черновике.", "The mark is removed — the entries are back in the draft.",
        "Отметить записи, опубликованные в Discord руками.", "Mark entries that were published to Discord by hand.", "Release notes: mark published outside the panel"),
    "notes.publish": D(
        ["panel_db", "discord"], "AsdaAdmin: запись adm.Outbox вида notes и учёт adm.NotesPost. Бот Oracle публикует новую ветку в форуме updates с упоминанием Patch "
        "Ping или без него.", "AsdaAdmin: an adm.Outbox record of kind notes and adm.NotesPost bookkeeping. The Oracle bot posts a new thread in the updates "
        "forum with or without a Patch Ping mention.",
        "journal", "Ждёт бота или ошибка — отмена записи очереди. Опубликовано — удаление ветки (только владелец). «Итог неизвестен» — решением notes.resolve. "
        "Кто уже прочитал — не вернуть.", "Waiting for the bot or failed — the queue record is cancelled. Published — the thread is deleted (owner only). "
        "“Outcome unknown” — by notes.resolve. What was already read cannot be taken back.",
        "Опубликовать заметки к выпуску в Discord.", "Publish release notes to Discord.", "Release notes: publish to Discord (updates forum)"),
    "notes.resolve": D(
        ["panel_db"], "AsdaAdmin: запись очереди закрывается, при «ветка есть» — записи отмечаются «опубликовано вне панели».",
        "AsdaAdmin: the queue record is closed, with “thread exists” — the entries are marked “published outside the panel”.",
        "journal", "Откатывается только «ветка есть» (отметка снимается). «Ветки нет» не откатывается — если ветка нашлась, отметьте записи notes.mark.",
        "Only “thread exists” is undone (the mark is removed). “No thread” is not undone — if the thread turns up, mark the entries with notes.mark.",
        "Решить публикацию с итогом «неизвестен»: ветки нет или ветка есть.", "Resolve a publication with an unknown outcome: no thread or thread exists.",
        "Release notes: resolve unknown outcome"),
    # ------------------------------------------------------------------ сообщество (бот Discord)
    "community.app.decide": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.BotCmd → бот в Discord: решение по заявке, при принятии — роль Beta Tester и личное сообщение автору. %s %s"
        % (_BOT[0], _ML[0]), "AsdaAdmin.adm.BotCmd → the bot in Discord: the application decision, on approval — the Beta Tester role and a direct message "
        "to the author. %s %s" % (_BOT[1], _ML[1]),
        "journal", "Заявка снова на рассмотрении, выданная решением роль снимается. Личное сообщение «принят» и строка mod-log не отзываются.",
        "The application is pending again, the role given by the decision is removed. The “accepted” direct message and the mod-log line are not recalled.",
        "Принять или отклонить заявку в тестеры (как кнопки Approve / Reject).", "Approve or reject a tester application (as the Approve / Reject buttons).",
        "Community: decide a tester application"),
    "community.tester.add": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.BotCmd → бот выдаёт роль Beta Tester в Discord. %s %s" % (_BOT[0], _ML[0]),
        "AsdaAdmin.adm.BotCmd → the bot gives the Beta Tester role in Discord. %s %s" % (_BOT[1], _ML[1]),
        "journal", "Роль снимается обратной командой (если команда её действительно выдала). Строка mod-log остаётся.",
        "The role is removed by the reverse command (if the command really gave it). The mod-log line stays.",
        "Выдать роль Beta Tester участнику Discord.", "Give the Beta Tester role to a Discord member.", "Community: give Beta Tester role"),
    "community.tester.remove": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.BotCmd → бот снимает роль Beta Tester, одобренные заявки участника → отклонены. %s %s" % (_BOT[0], _ML[0]),
        "AsdaAdmin.adm.BotCmd → the bot removes the Beta Tester role, the member's approved applications → rejected. %s %s" % (_BOT[1], _ML[1]),
        "journal", "Роль возвращается обратной командой, отклонённым заявкам — прежний статус. Строка mod-log остаётся.",
        "The role is given back by the reverse command, the rejected applications get their previous status. The mod-log line stays.",
        "Снять роль Beta Tester.", "Remove the Beta Tester role.", "Community: remove Beta Tester role"),
    "community.warns.clear": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.BotCmd → бот снимает предупреждения участника в своём реестре (снятые кладёт в данные отката). %s %s" % (_BOT[0], _ML[0]),
        "AsdaAdmin.adm.BotCmd → the bot clears the member's warnings in its registry (keeping the cleared ones for undo). %s %s" % (_BOT[1], _ML[1]),
        "journal", "Снятые предупреждения возвращаются. Строка mod-log остаётся.", "The cleared warnings come back. The mod-log line stays.",
        "Снять предупреждения /warn участника.", "Clear a member's /warn warnings.", "Community: clear warnings"),
    "community.ban.check": D(
        ["panel_db"], "AsdaAdmin.adm.BotCmd — бот проверяет цель перед баном (участник есть, защиты нет, прав хватает). В Discord ничего не меняется.",
        "AsdaAdmin.adm.BotCmd — the bot checks the target before a ban (member present, not protected, enough rights). Nothing changes in Discord.",
        "nothing", "Только проверка.", "Only a check.",
        "Проверить цель бана с блоком учётки до самого бана.", "Check the target of a ban with an account block before the ban itself.",
        "Community: check target before a ban"),
    "community.ban": D(
        ["panel_db", "discord", "game_db"], "AsdaAdmin.adm.BotCmd → бот банит участника на сервере Discord (без удаления сообщений): участник выгоняется с сервера "
        "и теряет роли. По флажку — блок учётки игры операцией account.block (своя запись журнала). %s %s" % (_BOT[0], _ML[0]),
        "AsdaAdmin.adm.BotCmd → the bot bans the member on the Discord server (no message deletion): the member is removed from the server and loses the "
        "roles. Optionally a game account block via account.block (its own journal record). %s %s" % (_BOT[1], _ML[1]),
        "journal", "Откат — разбан обратной командой: снимается только бан. Членство, роли и онбординг не возвращаются — участник заходит заново по приглашению. "
        "Блок учётки снимается откатом своей записи account.block. Строка mod-log остаётся.",
        "Undo — an unban by the reverse command: only the ban is lifted. Membership, roles and onboarding do not come back — the member rejoins by invite. "
        "The account block is lifted by undoing its own account.block record. The mod-log line stays.",
        "Забанить участника Discord и по желанию заблокировать его учётку игры.", "Ban a Discord member and optionally block his game account.",
        "Community: Discord ban (and account block)"),
    "community.unban": D(
        ["panel_db", "discord", "game_db"], "AsdaAdmin.adm.BotCmd → бот снимает бан Discord (участник может зайти заново по приглашению, роли не возвращаются), по флажку — "
        "снятие блока учётки операцией account.unblock. %s %s" % (_BOT[0], _ML[0]), "AsdaAdmin.adm.BotCmd → the bot lifts the Discord ban (the member can "
        "rejoin by invite, roles do not come back), optionally an account unblock via account.unblock. %s %s" % (_BOT[1], _ML[1]),
        "journal", "Бан обратной командой. Снятие блока — откатом своей записи account.unblock. Строка mod-log остаётся.",
        "A ban by the reverse command. The unblock — by undoing its own account.unblock record. The mod-log line stays.",
        "Разбанить участника Discord и по желанию снять блок учётки.", "Unban a Discord member and optionally lift the account block.",
        "Community: Discord unban (and account unblock)"),
    "community.cmd.cancel": D(
        ["panel_db"], "AsdaAdmin.adm.BotCmd — команда отменена до исполнения (adm.BotCmdCancel).", "AsdaAdmin.adm.BotCmd — the command is cancelled before execution (adm.BotCmdCancel).",
        "nothing", "В Discord ничего не менялось — нужную команду поставьте заново.", "Nothing changed in Discord — queue the needed command again.",
        "Отменить команду боту до исполнения.", "Cancel a bot command before it runs.", "Community: cancel a bot command"),
    "community.cmd.retry": D(
        ["panel_db", "discord"], "AsdaAdmin.adm.BotCmd — команда снова в очереди (adm.BotCmdRetry), бот исполнит её в Discord по текущему состоянию и запишет строку в mod-log.",
        "AsdaAdmin.adm.BotCmd — the command is queued again (adm.BotCmdRetry), the bot executes it in Discord against the current state and writes a mod-log line.",
        "inverse", "До исполнения — community.cmd.cancel. Исполненную — откатом исходной записи журнала.",
        "Before execution — community.cmd.cancel. An executed one — by undoing the original journal record.",
        "Повторить команду боту после ошибки или «итог неизвестен».", "Retry a bot command after an error or an unknown outcome.", "Community: retry a bot command",
        inv=("community.cmd.cancel",)),
    "community.test": D(
        ["panel_db"], "AsdaAdmin.adm.BotCmd — проверочная команда: бот её забирает и отмечает «тест», Discord не вызывает.",
        "AsdaAdmin.adm.BotCmd — a test command: the bot claims it and marks “test”, Discord is not called.",
        "nothing", "В Discord ничего не меняется.", "Nothing changes in Discord.",
        "Проверить путь команд боту.", "Test the bot command path.", "Community: test command (not executed)"),
    # ------------------------------------------------------------------ Telegram
    "notify.rule.set": D(
        ["panel_db", "telegram"], "AsdaAdmin.adm.NotifyRule — выключатель события или общий (процедура adm.TgRuleSet). При включении общего служба сразу ставит "
        "сводку разовых событий за 7 суток и дальше — уведомления, отправитель на ПК шлёт их в Telegram владельцу.", "AsdaAdmin.adm.NotifyRule — an event "
        "switch or the master one (procedure adm.TgRuleSet). When the master is switched on the service at once queues a summary of one-off events of the last "
        "7 days and then notifications, the PC sender sends them to the owner's Telegram.",
        "inverse", "Вернуть прежнее положение той же операцией. Уже отправленные сообщения (и сводку) не вернуть.",
        "Restore the previous position with the same operation. Messages already sent (and the summary) cannot be taken back.",
        "Включить или выключить уведомление владельцу в Telegram.", "Switch a Telegram notification to the owner on or off.",
        "Telegram: switch a notification", inv=("notify.rule.set",)),
    "telegram.test": D(
        ["panel_db"], "AsdaAdmin.adm.Outbox — проверочная запись Telegram: отправитель на ПК вызывает только getMe (или отмечает «тест»), сообщения в чат нет.",
        "AsdaAdmin.adm.Outbox — a Telegram test record: the PC sender calls only getMe (or marks “test”), no chat message.",
        "nothing", "Сообщения нет — откатывать нечего.", "No message — nothing to undo.",
        "Проверить, жив ли токен и связь с Telegram, без сообщения.", "Check that the token and Telegram link work, without a message.",
        "Telegram: check (getMe, no message)"),
    "telegram.ping": D(
        ["panel_db", "telegram"], "AsdaAdmin.adm.Outbox → отправитель на ПК шлёт настоящее проверочное сообщение (sendMessage) в чат владельца.",
        "AsdaAdmin.adm.Outbox → the PC sender sends a real test message (sendMessage) to the owner's chat.",
        "irreversible", "Сообщение остаётся в чате.", "The message stays in the chat.",
        "Отправить настоящее проверочное сообщение владельцу в Telegram.", "Send a real test message to the owner in Telegram.",
        "Telegram: send a test message"),
    # ------------------------------------------------------------------ пользователи панели
    "users.create": D(
        ["panel_db"], "AsdaAdmin.adm.users — новый пользователь панели с временным паролем.", "AsdaAdmin.adm.users — a new panel user with a temporary password.",
        "journal", "Пользователь отключается, его сессии отзываются.", "The user is disabled and his sessions are revoked.",
        "Создать пользователя панели с ролью.", "Create a panel user with a role.", "Panel users: create"),
    "users.set_role": D(
        ["panel_db"], "AsdaAdmin.adm.users — роль, все сессии пользователя отзываются.", "AsdaAdmin.adm.users — the role, all the user's sessions are revoked.",
        "journal", "Прежняя роль возвращается, отозванные сессии — нет (пользователь входит заново).",
        "The previous role comes back, the revoked sessions do not (the user signs in again).",
        "Сменить роль пользователя панели (последнего владельца понизить нельзя).", "Change a panel user's role (the last owner cannot be demoted).",
        "Panel users: change role"),
    "users.set_disabled": D(
        ["panel_db"], "AsdaAdmin.adm.users — отключён / включён, при отключении отзываются все сессии.",
        "AsdaAdmin.adm.users — disabled / enabled, disabling revokes all sessions.",
        "journal", "Прежнее состояние возвращается, отозванные сессии — нет.", "The previous state comes back, the revoked sessions do not.",
        "Отключить или включить пользователя панели.", "Disable or enable a panel user.", "Panel users: disable / enable"),
    "users.reset_password": D(
        ["panel_db"], "AsdaAdmin.adm.users — новый временный пароль, сессии отозваны, замки входа сняты.",
        "AsdaAdmin.adm.users — a new temporary password, sessions revoked, login locks cleared.",
        "irreversible", "Прежний пароль не хранится — пользователь меняет временный сам.", "The old password is not kept — the user changes the temporary one himself.",
        "Выдать пользователю панели новый временный пароль.", "Give a panel user a new temporary password.", "Panel users: reset password"),
    "users.reset_totp": D(
        ["panel_db"], "AsdaAdmin.adm.users — второй фактор снят, все сессии пользователя отозваны.", "AsdaAdmin.adm.users — two-factor removed, sessions revoked.",
        "inverse", "Пользователь включает второй фактор заново сам (self.totp_enable).", "The user enables two-factor again himself (self.totp_enable).",
        "Снять второй фактор (потерян телефон).", "Remove two-factor (phone lost).", "Panel users: reset two-factor", inv=("self.totp_enable",)),
    "self.password": D(
        ["panel_db"], "AsdaAdmin.adm.users — свой пароль (нужен текущий), прочие ваши сессии отзываются.",
        "AsdaAdmin.adm.users — your own password (the current one is required), your other sessions are revoked.",
        "irreversible", "Прежний пароль не хранится — его можно только задать заново.", "The old password is not kept — it can only be set again.",
        "Сменить свой пароль панели.", "Change your own panel password.", "My account: change password"),
    "self.totp_enable": D(
        ["panel_db"], "AsdaAdmin.adm.users — свой второй фактор (секрет из шага 1).", "AsdaAdmin.adm.users — your own two-factor (the secret from step 1).",
        "inverse", "Снять второй фактор может владелец (users.reset_totp).", "Two-factor can be removed by the owner (users.reset_totp).",
        "Включить свой второй фактор.", "Enable your own two-factor.", "My account: enable two-factor", inv=("users.reset_totp",)),
}


def section(name):
    """Раздел справки операции → (номер раздела, (по-русски, по-английски))."""
    for i, (prefixes, title) in enumerate(SECTIONS):
        if name.startswith(prefixes):
            return i, title
    return len(SECTIONS), OTHER_SECTION


def _pick(pair, en):
    """Нужный язык из пары (по-русски, по-английски)."""
    return pair[1] if en else pair[0]


def localized(name, op, en, role=None):
    """Справка одной операции на языке en (True — английский) для API и окна подтверждения. op — экземпляр из core.ops.REGISTRY.
    role — роль пользователя (allowed — есть ли у неё право операции). Права, исполнитель, второй фактор — из кода (core.auth, атрибуты op).
    ★ ревизия 85 М-8: подробности (writes / restart / undo — таблицы, процедуры, пути) — только тому, у кого есть право на саму операцию;
    остальным — название, раздел, help и роли (writes / restart / undo = None)."""
    from core import auth, ops
    d = DOC.get(name)
    if d is None:
        return None
    rr, re_ = (d["rr"], d["re"]) if (d["rr"] or d["re"]) else NO_RESTART
    sec_no, sec = section(name)
    perm = getattr(op, "perm", "")
    allowed = bool(role and auth.can(role, perm))
    out = {
        "name": name, "title": d["te"] if en else op.title, "section": _pick(sec, en), "section_no": sec_no, "perm": perm,
        "roles": [r for r in auth.ROLES if r in auth.PERMS.get(perm, set())], "allowed": allowed,
        "reversible": bool(op.reversible), "two_factor": bool(ops.needs_two_factor(name)),
        "runner": getattr(op, "schedule_runner", None) or "",
        "help": d["he"] if en else d["hr"], "writes": None, "restart": None, "undo": None,
    }
    if allowed:
        out["writes"] = {"codes": list(d["w"]), "labels": [_pick(WRITES[c], en) for c in d["w"]], "info": d["we"] if en else d["wr"]}
        out["restart"] = {"code": d["r"], "label": _pick(RESTART[d["r"]], en), "info": re_ if en else rr}
        out["undo"] = {"code": d["u"], "label": _pick(UNDO[d["u"]], en), "info": d["ue"] if en else d["ur"], "inverse": list(d["inv"])}
    return out


# ★ ревизия 85 В-6: строка о самом задании — в окне подтверждения job.add (справка показывается у ПЛАНИРУЕМОЙ операции)
JOB_NOTE = ("Это задание: всё перечисленное произойдёт в назначенное время (исполнитель — %s), а сейчас пишется только строка AsdaAdmin.adm.job. "
            "До срока задание отменяется операцией job.cancel — тогда ничего не произойдёт.",
            "This is a job: everything listed happens at the scheduled time (runner — %s), now only an AsdaAdmin.adm.job row is written. "
            "Before that time the job is cancelled by job.cancel — then nothing happens.")
JOB_RUNNER = {"service": ("служба на сервере", "the service on the server"), "pc": ("консоль ПК владельца", "the owner PC console")}


def for_job(params, en, role):
    """Справка для предпросмотра job.add: справка планируемой операции params["op"] с полем job (строка о задании); нет такой — справка job.add."""
    from core import ops
    name = str((params or {}).get("op") or "")
    op = ops.REGISTRY.get(name)
    if op is None or name not in DOC:
        return localized("job.add", ops.REGISTRY.get("job.add"), en, role)
    d = localized(name, op, en, role)
    runner = JOB_RUNNER.get(getattr(op, "schedule_runner", "") or "", ("—", "—"))
    d["job"] = {"info": _pick(JOB_NOTE, en) % _pick(runner, en)}
    return d


def catalog(role, en):
    """Все операции реестра со справкой (по разделам и имени) — страница «Справка»."""
    from core import ops
    items = [localized(n, o, en, role) for n, o in ops.REGISTRY.items()]
    items = [x for x in items if x is not None]
    items.sort(key=lambda x: (x["section_no"], x["name"]))
    return {"items": items, "missing": sorted(n for n in ops.REGISTRY if n not in DOC),
            "codes": {"writes": {k: _pick(v, en) for k, v in WRITES.items()}, "restart": {k: _pick(v, en) for k, v in RESTART.items()},
                      "undo": {k: _pick(v, en) for k, v in UNDO.items()}}}


def _cyr(s):
    """Есть ли в строке кириллица."""
    return any("а" <= ch <= "я" or ch == "ё" for ch in s.lower())


def problems(registry):
    """Проверка полноты каталога против реестра операций → список текстов нарушений (пусто — всё в порядке). Без кода разделов: registry —
    {имя: операция} (или {имя: признак reversible} в самотесте)."""
    bad = []
    for name, op in sorted(registry.items()):
        d = DOC.get(name)
        if d is None:
            bad.append("%s: нет справки (core/opdoc.DOC)" % name)
            continue
        rev = op if isinstance(op, bool) else bool(getattr(op, "reversible", False))
        if not d["w"] or any(c not in WRITES for c in d["w"]) or ("none" in d["w"] and len(d["w"]) > 1):
            bad.append("%s: writes — коды только из WRITES, «none» — один" % name)
        if d["r"] not in RESTART or d["u"] not in UNDO:
            bad.append("%s: restart / undo — код не из списка" % name)
        for ru, en, what in (("wr", "we", "writes"), ("ur", "ue", "undo"), ("hr", "he", "help")):
            if not d[ru].strip() or not d[en].strip():
                bad.append("%s: %s — нет текста RU или EN" % (name, what))
        if d["r"] != "none" and (not d["rr"].strip() or not d["re"].strip()):
            bad.append("%s: restart %s без пояснения RU / EN" % (name, d["r"]))
        if bool(d["rr"].strip()) != bool(d["re"].strip()):
            bad.append("%s: пояснение restart только на одном языке" % name)
        if not d["te"].strip():
            bad.append("%s: нет названия EN" % name)
        for k in ("wr", "ur", "hr") + (("rr",) if d["rr"] else ()):
            if not _cyr(d[k]):
                bad.append("%s: %s — не по-русски" % (name, k))
        for k in ("we", "ue", "he", "te") + (("re",) if d["re"] else ()):
            if _cyr(d[k]):
                bad.append("%s: %s — кириллица в английском тексте" % (name, k))
        if rev != (d["u"] == "journal"):
            bad.append("%s: reversible = %s, а undo = %s (журнал — ровно у откатываемых)" % (name, rev, d["u"]))
        if (d["u"] == "inverse") != bool(d["inv"]):
            bad.append("%s: undo inverse ↔ список обратных операций" % name)
        for x in d["inv"]:
            if x not in registry:
                bad.append("%s: обратной операции %s нет в реестре" % (name, x))
    for name in sorted(set(DOC) - set(registry)):
        bad.append("%s: справка есть, операции нет" % name)
    return bad
