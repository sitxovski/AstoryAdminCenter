<!-- Copyright (c) 2026 @sitxovski (Discord) -->
# Excluded from the playtest (ban registry) — template

Copy this file to `BANNED_PLAYERS.md` in the same folder (that file is git-ignored) and add one row per banned player.
The admin center reads every markdown table that has the columns `Userindex` and `Игровой логин` (keep these header names as is):

* `asda_admin.py` / panel «Подарки» → «всем игрокам» skips accounts listed here (without this file that mode is refused);
* panel «Сообщество» compares the registry with the login block of each account;
* `tools/Admin` (Accounts.bat) warns before giving items to a listed account.

An empty table (header only) means "no bans". Deploy the panel again after editing (`deploy/deploy_admin_center.py`).

## <date> — <reason>

| Discord (ник на сервере) | @handle | Discord ID | Игровой логин | Userindex | Персонаж (ур.) |
|---|---|---|---|---|---|
