# Задачи планировщика ПК владельца для админ-центра Astory

Здесь лежат файлы задач. Сами задачи **не созданы**: это настройка системы, её делает владелец.

В файлах — заглушки, их заполняет `_setup\configure.bat` (он понимает UTF-16):

| Заглушка | Где | Что вписать |
|---|---|---|
| `@@ASTORY_DEV_PC@@\@@ASTORY_DEV_USER@@` | `<UserId>`, два места в каждом файле | имя ПК и учётка Windows, под которой идут задачи (`whoami`) |
| `@@ASTORY_DEV_ROOT@@\AstoryAdminCenter` | `<WorkingDirectory>` | папка этого клона (`ASTORY_DEV_ROOT` — папка, где рядом лежат клоны Astory) |
| `@@ASTORY_DEV_PYTHON@@` | `<Arguments>` | полный путь к `python.exe` на этом ПК (`where python`), например `C:\Program Files\Python313\python.exe` |

Если `configure` не спросил `ASTORY_DEV_PYTHON` (пропущен или не задан), впишите путь руками. Нужен полный путь, а не просто
`python`: задача запускается без вашего сеанса, и PATH у неё может быть другим.

Файлы сохранены в UTF-16 с меткой BOM, как требует `schtasks /XML` при `encoding="UTF-16"`. Правьте их редактором, который сохраняет UTF-16.

| Файл | Задача | Что делает | Режим | Когда |
|---|---|---|---|---|
| `release_push.xml` | `Astory\ReleasePush` | `asda_admin.py releases push` — снимок конвейера выпуска в раздел «Выпуски» (А7.1) | **S4U** — без входа и без хранения пароля. DPAPI не нужен: снимок только проверяет наличие файлов | при входе +5 мин и каждые 4 ч |
| `crash_sync.xml` | `Astory\CrashSync` | `asda_admin.py crashes sync` — новые `.acrash` по scp, расшифровка на ПК, сводка в раздел «Сбои клиента» (А7.2) | **только при входе** (InteractiveToken) | при входе +5 мин и каждые 4 ч (со сдвигом 20 мин от ReleasePush), пока вы в системе |

Почему `crash_sync` не под S4U (ревизия 75):
- закрытый ключ LogSeal лежит под DPAPI вашей учётки;
- под S4U у DPAPI нет ключей пользователя, и ключ не откроется;
- `crashes sync` в таком случае сам откажет **до** scp: «ключ LogSeal не открывается … ничего не забрано и не записано».

Объединять обе команды в одну задачу нельзя.

Под «только при входе» на время запуска может мигнуть окно консоли.

## Создать (из `@@ASTORY_DEV_ROOT@@\AstoryAdminCenter\deploy\schtasks`, обычная консоль, не от администратора)

```
schtasks /Create /TN "Astory\ReleasePush" /XML release_push.xml
schtasks /Create /TN "Astory\CrashSync" /XML crash_sync.xml
```

S4U может потребовать консоль от администратора. Если `schtasks` ответит «Отказано в доступе», запустите ту же команду в консоли
«от имени администратора».

## Проверить

```
schtasks /Run /TN "Astory\ReleasePush"
schtasks /Run /TN "Astory\CrashSync"
schtasks /Query /TN "Astory\ReleasePush" /V /FO LIST
schtasks /Query /TN "Astory\CrashSync" /V /FO LIST
type "%LOCALAPPDATA%\AstoryAdmin\release_push.log"
type "%LOCALAPPDATA%\AstoryAdmin\crash_sync.log"
```

Что должно получиться:
- в `release_push.log` — «снимок ПК записан: №N» или «не изменился»;
- в `crash_sync.log` — «сводка сбоев записана: новых N, изменилось N, без изменений N (отправка №N…)»;
- в панели обновятся «ПК присылал» в «Выпусках» и «Сводка №N … ПК присылал» в «Сбоях клиента».

Каждый запуск — одна запись в журнале действий (до 6 в сутки на задачу).

## Убрать

```
schtasks /Delete /TN "Astory\ReleasePush" /F
schtasks /Delete /TN "Astory\CrashSync" /F
```
