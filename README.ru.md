<div align="center">

[English](README.md) · **Русский** · [العربية](README.ar.md)

### ❤️ Нравится проект? Поддержите труд на [**Boosty**](https://boosty.to/sitxovski_yurii)

# Astory Admin Center

**Веб-панель для управления игровым сервером Astory — игроки, античит, события, выпуски и сообщество в одном месте**

[Astory Client](https://github.com/sitxovski/AstoryClient) · [Astory Server](https://github.com/sitxovski/AstoryServer) · [Astory Admin Center](https://github.com/sitxovski/AstoryAdminCenter)

</div>

---

> ⚠️ **Дисклеймер.** Этот пакет (Только репозиторий. Проект - ручная работа с помощью ИИ) собран с помощью **Claude Code** и может содержать ошибки. Пишите мне в личные сообщения в Discord (**@sitxovski**) — помогу.

## Что умеет

- 👤 **Игроки** — учётки, персонажи, инвентарь, история предметов, поиск дюпов, кто в игре
- 🛡️ **Античит** — журнал, суточный отчёт, автоблоки, дела, журнал чата, проверка имён
- 🎉 **Игра** — события на опыт и добычу, рейтинги, режим обслуживания, магазины и данные игры с откатом
- 🚀 **Выпуски** — статус выпусков, сбои клиента, заметки к выпуску
- 💬 **Сообщество** — объявления и команды в Discord, жалобы игроков, уведомления владельцу в Telegram
- 📜 **Безопасность** — роли, вход со вторым фактором, журнал всех действий с откатом

Панель работает на игровом сервере (HTTPS) и выкладывается с вашего ПК по SSH. Внешне она похожа на окна игры.

## Быстрый старт

1. **Установка** — `Prerequisites\install_prerequisites.bat` на ПК и `... -Server` на сервере ([подробно](Prerequisites/README.md)).
2. **Настройка** — `_setup\configure.bat` (адрес сервера, ключ SSH, ID Discord — [где их взять](_setup/SETUP.md)).
   Запустите его во **всех трёх** клонах (AstoryClient, AstoryServer, AstoryAdminCenter): панель и бот берут `AstoryClient\Tools\asda_paths.py`
   и `AstoryServer\Tools\Anticheat\db_connect.py`; ответы переиспользуются, в других клонах спросят только новое.
3. **Выкладка** — `python deploy\deploy_admin_center.py --skip-selftest`
   Она сама копирует панель на сервер и ставит её объекты SQL (`sql\*.sql`) — вручную их запускать не нужно.
   (без `--skip-selftest` выкладка сначала гоняет офлайн-самотест: ему нужен SQL Server **LocalDB** на ПК, а проверки, которым нужны
   файлы рабочей среды автора, он пропускает с пометкой SKIP — см. [Prerequisites](Prerequisites/README.md#3-deploy--build)).
   После первой выкладки запустите на сервере `AstoryServer\Prerequisites\setup_server.ps1 -SyncAdminBridge` и перезапустите стек — он передаёт игровым серверам ключи моста панели.
4. **Открыть** — `bat\AdminCenter.bat` → *tunnel*, затем `https://localhost:17890/`

Полное руководство: [`GUIDE.md`](GUIDE.md).

Работает вместе с [Astory Server](https://github.com/sitxovski/AstoryServer) (сервер, которым управляет)
и [Astory Client](https://github.com/sitxovski/AstoryClient) (выпуски и отчёты о сбоях).

## Автор

Автор — **@sitxovski** (Discord).

Можно использовать свободно и без ограничений — [лицензия MIT](LICENSE). **Только укажите автора — @sitxovski (Discord) —
и ссылку на этот репозиторий, когда копируете, форкаете или используете любую часть проекта.**

---

<div align="center">

### ❤️ Поддержите труд на [**Boosty**](https://boosty.to/sitxovski_yurii)

</div>
