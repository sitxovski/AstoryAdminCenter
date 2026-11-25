# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""auth.py — вход в панель, роли, сессии, второй фактор. 16.11.2026.

ПАРОЛИ   PBKDF2-HMAC-SHA256, соль 16 б, PW_ITER итераций (число хранится в строке — можно поднять без миграции).
         Сравнение — hmac.compare_digest. Пароль нигде не печатается и в журнал не попадает.
ЗАМОК    login_fail_limit неудач подряд с ОДНОГО адреса (неверный пароль или код) → замок этой пары (логин, IP) на
         login_lock_minutes; удачный вход сбрасывает; сброс пароля и включение владельцем снимают замки логина.
ВТОРОЙ ФАКТОР  TOTP (RFC 6238: SHA-1, 30 с, 6 цифр, окно ±1 шаг). Обязателен ролям owner и admin: до включения
         сессия «только настройка кода». Секрет в базе зашифрован: XOR с HMAC-SHA256(TOTP_KEY, nonce) — ключ TOTP_KEY
         лежит только в файле секретов сервера; nonce 12 б хранится перед шифротекстом.
СЕССИИ   токен 32 б (cookie HttpOnly, SameSite=Strict), в базе — только SHA-256 токена; CSRF-токен на сессию
         (заголовок X-Asda-Csrf на каждый изменяющий запрос). Срок: session_hours без действий, session_abs_hours всего.
РОЛИ     owner — всё; admin — всё, кроме пользователей панели; gm — игроки и состояние; support — то же без IP/MAC.
Побочных эффектов при импорте нет.
"""
import base64
import datetime
import hashlib
import hmac
import ipaddress
import os
import secrets
import struct
import threading
import time

from . import config, db

PW_ITER = 600000          # итераций PBKDF2 (рекомендация OWASP 2023 для SHA-256)
PW_MIN = 10               # минимальная длина пароля панели
LOGIN_MAX = 32            # длина логина панели
TOTP_STEP = 30            # шаг TOTP, с
TOTP_DIGITS = 6           # цифр в коде
ROLES = ("owner", "admin", "gm", "support")
ROLE_TITLES = {"owner": "владелец", "admin": "администратор", "gm": "GM", "support": "поддержка"}
TOTP_REQUIRED = {"owner", "admin"}
LOGIN_FAIL = "неверный логин, пароль или код (после %d ошибок подряд вход закрывается на %d мин)"

# Ревизия 16.11 вечер В2 (панель открыта в интернет): защита от перебора со МНОГИХ адресов.
USER_WINDOW_S = 600          # окно счёта попыток на логин, с
USER_WINDOW_MAX = 12         # попыток на логин за окно — сверх него вход этого логина снаружи сети закрыт до конца окна
HASH_SLOTS = 2               # одновременных проверок пароля НЕ из VPN (PBKDF2 ≈0,4 с ядра) — перебор не съедает ядра
HASH_WAIT_S = 10             # сколько ждать свободного слота, иначе отказ «занято»
_hash_sem = threading.BoundedSemaphore(HASH_SLOTS)
_hash_sem_vpn = threading.BoundedSemaphore(1)    # свой слот для VPN/локальных — интернет не отрезает владельца (В2-н1)
_user_tries = {}             # логин (нижний регистр) → [время попыток снаружи доверенной сети]
# Доверенная сеть — ТОЛЬКО VPN Tailscale (+ loopback). Домашняя сеть НЕ доверенная (перепроверка 16.11 вечер): если роутер
# при пробросе порта подменяет адрес источника на свой 192.168.x.x, «доверенным» стал бы весь интернет.
_TRUSTED_NETS = [ipaddress.ip_network("100.64.0.0/10")]


def trusted_ip(ip):
    """Адрес из VPN (Tailscale 100.64/10) или локальный: для него нет окна на логин, свой слот проверки пароля и не нужен
    второй фактор у ролей без обязательного 2FA. Перебор снаружи не может запереть владельца, сидящего в VPN."""
    try:
        a = ipaddress.ip_address((ip or "").split("%")[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    # явный список: ipaddress.is_private считает «частными» и документационные/служебные сети (203.0.113/24 и т.п.)
    return a.is_loopback or any(a in n for n in _TRUSTED_NETS if n.version == a.version)



def _user_window_hit(login, ip):
    """Засчитать попытку логина снаружи; True — окно логина исчерпано (вход снаружи закрыт до конца окна)."""
    if trusted_ip(ip):
        return False
    now = time.time()
    with _lock_mx:
        if len(_user_tries) > 5000:                    # перепроверка В2-н3: ключ — присланный логин, чистить устаревшие
            for k in [k for k, v in _user_tries.items() if not v or now - v[-1] >= USER_WINDOW_S]:
                del _user_tries[k]
            for k in [k for k, v in _fails.items() if v[1] < now and v[0] == 0]:
                del _fails[k]
        lst = [t for t in _user_tries.get(login.lower(), []) if now - t < USER_WINDOW_S]
        full = len(lst) >= USER_WINDOW_MAX
        if not full:
            lst.append(now)
        _user_tries[login.lower()] = lst
        return full


class Busy(Exception):
    """Все слоты проверки пароля заняты (вероятно, перебор) — отказ без проверки."""


def verify_limited(pw, h, salt, iters, ip):
    """verify_password под семафором: снаружи VPN — общий HASH_SLOTS, из VPN — свой слот."""
    sem = _hash_sem_vpn if trusted_ip(ip) else _hash_sem
    if not sem.acquire(timeout=HASH_WAIT_S):
        raise Busy("служба занята проверкой входов; повторите через минуту")
    try:
        return verify_password(pw, h, salt, iters)
    finally:
        sem.release()


def _burn(pw, ip):
    """Ответ «как будто проверили пароль» для несуществующего логина — настоящий хеш (время то же), под семафором."""
    sem = _hash_sem_vpn if trusted_ip(ip) else _hash_sem
    if not sem.acquire(timeout=HASH_WAIT_S):
        raise Busy("служба занята проверкой входов; повторите через минуту")
    try:
        hash_password(pw or "x")
    finally:
        sem.release()

# Права → роли. Новые разделы добавляют сюда свои права (одно место правды для API и интерфейса).
PERMS = {
    "status.view":      {"owner", "admin", "gm", "support"},
    "players.view":     {"owner", "admin", "gm", "support"},
    "players.view_net": {"owner", "admin", "gm"},            # IP, MAC, связанные учётки
    "players.items_edit": {"owner", "admin"},                # двигать / надеть / снять предметы персонажа не в игре (А1)
    "players.items_props": {"owner"},                        # золото и свойства экземпляра (заточка, опции, самоцветы) — экономика; перепроверка А1 В6
    "players.items_give": {"owner"},                         # выдать / изъять предмет персонажа не в игре (А1, 18.11; adm.ItemGive/ItemTake) — экономика, как свойства
    "players.titles": {"owner", "admin"},                    # звания: выдать / снять, пересчитать славу (А1, 18.11; domains/titles.py)
    "players.honor": {"owner"},                              # очки чести CharCamp.CampPoint — валюта магазина чести, экономика (18.11)
    "players.skills": {"owner", "admin"},                    # навыки: выдать / снять / сбросить, очки навыков (А1, 18.11; domains/skills.py)
    "players.quests": {"owner", "admin"},                    # задания: выдать (как NPC), снять, снять «выполнено» (А1, 18.11; domains/quests.py)
    "players.pets": {"owner", "admin"},                      # питомцы: кличка, уровень (до потолка), удалить (А1, 18.11; domains/pets.py)
    "players.soulmate": {"owner", "admin"},                  # соулмейт: разорвать, связать, уровень, дружба, сверка Share (А1, 18.11; domains/soulmate.py)
    "players.friends": {"owner", "admin"},                   # друзья: удалить / добавить (обе стороны), обновить имена (А1, 18.11; domains/friends.py)
    "players.clan": {"owner", "admin"},                      # клан: исключить, глава, роспуск, эмблема, объявления (А1, 18.11; domains/clan.py)
    "players.appearance": {"owner", "admin"},                # внешность: причёска, цвет, лицо своего пола (А1, 18.11; domains/charrest.py)
    "players.plus": {"owner", "admin"},                      # баффы наборов CharPlusPackage: снять / выдать / продлить (А1, 18.11)
    "players.camp": {"owner", "admin"},                      # лагерь: штраф, армия учётки, пересчёт рейтинга чести (А1, 18.11)
    "players.craft": {"owner", "admin"},                     # ремесло (уровень, суточный сброс), навык рыбалки, книга рыб (А1, 18.11)
    "players.tutorial": {"owner", "admin"},                  # отметки шагов обучения CharTutorial (А1, 18.11)
    "players.copy": {"owner"},                               # копия персонажа на служебную учётку ≤ 5000 (А1, 18.11; adm.CharCopy)
    "players.block":    {"owner", "admin", "gm"},                # блок учётки (А1, 16.11); служебные — только owner
    "players.unblock":  {"owner", "admin"},                      # снятие блока (перепроверка 6 В3: gm не снимает, в т.ч. автоблок P48)
    "players.clear_online": {"owner", "admin"},              # снять залипший «в игре» (А1, 17.11; только доказанно мёртвые признаки)
    "players.rename":   {"owner", "admin"},                      # сменить имя персонажа не в игре (А1, 17.11)
    "players.password": {"owner", "admin"},                      # пароль игровой учётки и снятие замка неудач (А1, 17.11)
    "players.create":   {"owner", "admin"},                      # создать игровую учётку (А1, 17.11; удалять панель не может)
    "players.restore":  {"owner", "admin"},                      # восстановить удалённого персонажа (А1, 18.11; adm.CharRestore)
    "accounts.close":   {"owner", "admin"},                      # закрыть учётку: вечный блок (+ по желанию новый пароль), строки не удаляются (19.11, решение п.2)
    "accounts.gm_flag": {"owner"},                               # GM-флаг CharGmInfo: выдать / снять только служебным ≤ 5000 (19.11, решение п.4)
    "accounts.create_service": {"owner"},                        # создать СЛУЖЕБНУЮ учётку с номером ≤ 5000 (19.11, решение п.5; adm.ServiceAccountCreate)
    "shop.view":        {"owner", "admin"},                      # магазины: наборы изменений, расхождения сервер/клиент (А3, 19.11; domains/shopcs.py)
    "shop.edit":        {"owner", "admin"},                      # набор изменений магазинов: черновик, позиции, проверка, утверждение, отмена черновика
    "shop.apply":       {"owner"},                               # применение половин набора (сервер — рестарт стойки с объявлением; клиент — RawAssets/DT) и их откат
    "data.view":        {"owner", "admin"},                      # данные игры (А4, 19.11; реестр видов domains/cs_kinds): витрина 6800, магазин чести, парикмахерская…
    "data.edit":        {"owner", "admin"},                      # позиции данных игры в наборе изменений: черновик, проверка, утверждение, отмена (вместе с shop.edit)
    "data.apply":       {"owner"},                               # применение и откат половин набора с позициями данных игры (вместе с shop.apply)
    "players.move":     {"owner", "admin", "gm"},
    "players.kick":     {"owner", "admin", "gm"},                # отключить игрока с сервера живьём (мост P127, А2 18.11)
    "server.monsters":  {"owner", "admin"},                      # ★ А5.2: призыв / возврат группы монстров 6045/6046 от служебного персонажа (мост v83)
    "server.announce":  {"owner", "admin"},                     # объявление всем игрокам живьём (мост P127, 3113)                # перенести персонажа не в игре (А1, 18.11); «своя точка» — owner/admin
    "players.progress": {"owner"},                               # уровень персонажа (А1, 17.11) — экономика, как свойства предметов
    "stack.control":    {"owner"},                               # рестарт / остановка / запуск стойки — ТОЛЬКО restart_stack.py с ПК (А5.1, 20.11; domains/stack.py)
    "server.maintenance": {"owner", "admin"},                    # ★ А5.3: режим обслуживания — вход только служебным 1…5000 (maint.on / maint.off; SQL L09)
    "server.events":    {"owner", "admin"},                      # ★ А5.4: события опыта/добычи 6038/6040 мостом (сильные рейты > ×2 и < ×1 — только владелец)
    "server.ranks":     {"owner", "admin"},                      # ★ А5.4: пересчитать рейтинги сейчас (6020 / P25 мостом)
    "server.daily":     {"owner", "admin"},                      # ★ А5.4: сброс ежедневных заданий доски (adm.LimitationReset)
    "patchcfg.view":    {"owner", "admin"},                      # ★ А5.5: настройки серверных патчей (ini DLL всех копий, журнал патчей) и конфиги стойки — только чтение, секреты скрыты
    "patchcfg.edit":    {"owner", "admin"},                      # ★ А5.5: позиции patch.set / config.set в наборе изменений (вместе с shop.edit)
    "patchcfg.apply":   {"owner"},                               # ★ А5.5: выкладка / откат таких наборов рестартом стойки и второе подтверждение сильной правки (вместе с shop.apply)
    "logs.view":        {"owner", "admin"},                      # ★ А5.6: хвост серверных журналов стойки — только чтение; в журналах вся стойка (DSN, адреса узлов, чужие игроки, дампы пакетов gp7) — это работа администратора (§3.5), не GM / поддержки (им — карточка и лента игрока)
    "logs.view_ip":     {"owner", "admin"},                      # ★ А5.6: IP / MAC в строках журналов без маски (без права — «IP•••»); секреты маскируются всегда
    "db.view":          {"owner", "admin"},                      # ★ А5.7: бэкапы БД — состояние баз, последние бэкапы (любые, по истории msdb), место на диске
    "db.backup":        {"owner", "admin"},                      # ★ А5.7: сделать бэкап (COPY_ONLY + CHECKSUM + VERIFYONLY) и перепроверить — только читает базы, чужую цепочку не трогает
    "db.prune":         {"owner"},                               # ★ А5.7: ручная уборка бэкапов панели (удаление файлов; последний проверенный и чужие — никогда)
    "db.stand":         {"owner"},                               # ★ А5.7: восстановить бэкап на стенд LocalDB ПК (данные игроков на ПК — только владелец, только консолью)
    "db.release":       {"owner"},                               # ★ ревизия 47 В-1: снять зависшее «идёт» бэкапа (строка adm.dbbackup и задания db.*), если бэкап не идёт
    "db.bakdrop":       {"owner"},                               # ★ А5.8: удалить служебные копии *_bak_* (каталог «можно убрать», свежий проверенный бэкап, слово + второй фактор)
    "ac.view":          {"owner", "admin", "gm"},                # ★ А6.1: экран «Античит» — журнал joylog1.ac.* целиком, сводки; только чтение (IP — только с players.view_net)
    "ac.daily_run":     {"owner", "admin"},                      # ★ А6.6: суточный отчёт античита вручную или заданием (пишет только AsdaAdmin adm.AcDaily; служба — сама раз в сутки); просмотр — ac.view
    "ac.case":          {"owner", "admin", "gm"},                # ★ А6.7: дела античита san.* — открыть, приложить события / выдержки, выгрузка, отчёт отката (решение владельца №3: gm открывает и прикладывает); дела служебных ≤ 5000 — только owner
    "ac.decide_low":    {"owner", "admin", "gm"},                # ★ А6.7 (ревизия 59 Н-2, решение владельца №3): решение, исполнение и отзыв ступеней 0–2 (наблюдение, предупреждение, кик)
    "ac.decide":        {"owner", "admin"},                      # ★ А6.7: решение со ступени 3 (блок account.block, откат по Serial), снятие блока дела, закрытие
    "ac.appeal":        {"owner", "admin"},                      # ★ А6.7: апелляция; пересматривает ДРУГОЕ лицо, не выносившее решение
    "names.review":     {"owner", "admin", "gm"},                # ★ А6.11: очередь имён (новые и сменённые за период, правила A13) и отметка «ок / сменить» (пишет только AsdaAdmin adm.NameReview); смена имени — players.rename
    "reports.view":     {"owner", "admin", "gm"},                # ★ А6.11 (решение владельца №6): жалобы игроков на игроков из бота Discord — очередь, карточка, скриншоты
    "reports.handle":   {"owner", "admin", "gm"},                # ★ А6.11: взять, закрыть с итогом, связать с делом, ответ автору через бота (пишет только AsdaAdmin adm.PlayerReport*)
    "chat.view":        {"owner", "admin", "gm"},                # ★ А6.12 (решение владельца №5): журнал чата joylog1.chat.message (P129) и список заглушек; только чтение
    "chat.mute":        {"owner", "admin", "gm"},                # ★ А6.12: заглушка чата на срок с причиной (chat.UP_ChatMuteSet); gm — не дольше суток (★ р71 Н-3, chatlog.ROLE_LIMITS, решение координатора до слова владельца); служебные ≤ 5000 — только owner
    "chat.unmute":      {"owner", "admin", "gm"},                # ★ А6.12: снять заглушку досрочно (chat.UP_ChatMuteLift); gm — только свои (★ р71 Н-3, chatlog.ROLE_LIMITS); служебные — только owner
    "money.view":       {"owner", "admin"},                     # ★ А6.2: раздел «Деньги» — покупки и подарки gp7 всех учёток, висящие подарки, продажи по дням и позициям, сток; только чтение
    "money.adjust":     {"owner"},                               # ★ А6.9 (решение владельца №4): начисление и списание баланса gp7 — причина, второе подтверждение, лимиты, журнал adm.GP7AdjustLog
    "attendance.view":  {"owner", "admin", "gm"},                # ★ А6.10 (решение владельца 23.11): сводка посещаемости — счёт, «сегодня уже получено», дни AttendanceDetail, журнал ручных отметок; только чтение
    "attendance.undo_log": {"owner"},                            # ★ А6.10 р73: откат правки посещаемости по журналу отметок (нет записи в журнале действий — сбой adm.audit после фиксации)
    "attendance.edit":  {"owner", "admin"},                      # ★ А6.10: засчитать / снять ПРОШЕДШИЙ день (Joy1.adm.AttendanceAdjust, причина, журнал, откат); служебные ≤ 5000 — только owner; gm только смотрит
    "econ.view":        {"owner", "admin"},                      # ★ А6.3: «Экономика: золото» — потоки по журналам, богатейшие, редкое на руках, снимки и неучтённое; только чтение
    "econ.snapshot":    {"owner", "admin"},                      # ★ А6.3: снять снимок золота на руках (пишет только AsdaAdmin adm.EconDaily*; служба — сама раз в сутки)
    "releases.view":    {"owner", "admin"},                      # ★ А7.1 (решение владельца А7 №6 — только статус): раздел «Выпуски» — каналы снаружи, срок подписи, снимок ПК (releases.log, Inbox, итоги батников, ключи «есть / срок»); gm нет — это кухня выпуска (ошибки сборок, ключи), как logs.view, а версию игроку GM видит в лаунчере
    "releases.push":    {"owner"},                               # ★ А7.1: задание ПК release.push — консоль ПК владельца присылает снимок конвейера (пишет только AsdaAdmin adm.ReleasePcStatus)
    "crash.view":       {"owner", "admin"},                      # ★ А7.2 (решения владельца А7 №1, №8): «Сбои клиента» — группы мест падения, частота, версии, квота LogDrop; gm нет — логин в пакете заявлен клиентом и не доказан (README LogDrop), а разбор падений — кухня сборки, как logs.view и releases.view; помочь игроку GM может по его словам и карточке
    "crash.sync":       {"owner"},                               # ★ А7.2: задание ПК crash.sync — консоль ПК владельца забирает .acrash по scp, расшифровывает на ПК и присылает только сводку (adm.ClientCrash*)
    "crash.prune":      {"owner"},                               # ★ А7.2 (решение №8): удалить на сервере .alog старше 60 суток (.acrash — никогда), слово и второй фактор, журнал
    "outbox.view":      {"owner", "admin"},                      # ★ А7.4 (решение владельца А7 №2): «Очередь Discord» — записи adm.Outbox, статусы, ошибки
    "community.post":   {"owner", "admin"},                      # ★ А7.4: «и в Discord» у объявления, отмена и повтор записи, проверочная запись; gm нет — публикация видна всему серверу Discord и не откатывается (удалить может только owner), а объявление в игру gm и так не делает (server.announce)
    "community.delete": {"owner"},                               # ★ А7.4: удалить уже опубликованное сообщение из Discord (бот удаляет; отката нет)
    "community.view":   {"owner", "admin", "gm"},                # ★ А7.6 (решение владельца А7 №9): «Сообщество» — копия реестра бота (заявки, тестеры, предупреждения, баны Discord) и очередь команд; только чтение. gm видит: заявки и варны нужны ему для разбора жалоб и игроков, а Discord id и ник — то, что модераторы и так видят в Discord
    "community.manage": {"owner", "admin"},                      # ★ А7.6: команды боту — решение по заявке, роль Beta Tester, снять предупреждения, отмена / повтор, проверочная; gm нет — по умолчанию только просмотр: решение по заявке и роль меняют доступ к закрытому тесту, а в Discord этим занимаются Administrator / Moderator
    "community.ban":    {"owner", "admin"},                      # ★ А7.6: бан / разбан сервера Discord (+ account.block / account.unblock по флажку — своим правом players.block / players.unblock); gm нет — бан выгоняет с сервера и роли не возвращаются
    "notes.view":       {"owner", "admin"},                      # ★ А7.7 (решение владельца А7 №7): «Заметки к выпуску» — снимок changelog с ПК, записи и что уже опубликовано, черновик, история публикаций; gm нет — как outbox.view: черновик ещё не публичен, а записи changelog — кухня порта
    "notes.draft":      {"owner", "admin"},                      # ★ А7.7: сохранить черновик заметок (adm.NotesDraft) — ничего не публикует; публикация и отметка «опубликовано вне панели» — community.post
    "notes.push":       {"owner"},                               # ★ А7.7: задание ПК notes.push — консоль ПК владельца присылает текущий changelog как есть (пишет только AsdaAdmin adm.NotesSnap), как releases.push
    "notify.view":      {"owner"},                               # ★ А7.5 (решение владельца А7 №3 — Telegram только владельцу): раздел «Telegram владельцу» — выключатели, события, очередь Telegram, отметки службы и отправителя на ПК; admin нет — это личный канал владельца
    "notify.manage":    {"owner"},                               # ★ А7.5: включить / выключить уведомления (общий выключатель и каждое событие), проверка (getMe, без сообщения), проверочное сообщение (настоящая отправка)
    "jobs.view":        {"owner", "admin"},                    # задания планировщика adm.job (А5.1)
    "jobs.manage":      {"owner", "admin"},                      # поставить / отменить задание (вместе с правом самой операции)
    "jobs.release":     {"owner"},                               # снять зависшее «идёт» (ПК упал посреди прогона)
    "feed.view":        {"owner", "admin", "gm", "support"},
    "audit.view":       {"owner", "admin"},
    "audit.undo":       {"owner"},
    "users.manage":     {"owner"},
    "self.manage":      {"owner", "admin", "gm", "support"},   # свой пароль и второй фактор
}


class AuthError(Exception):
    """Отказ входа/прав с понятной причиной."""


def can(role, perm):
    """Есть ли у роли право perm."""
    return role in PERMS.get(perm, set())


def perms_of(role):
    """Список прав роли (для интерфейса)."""
    return sorted(p for p, rs in PERMS.items() if role in rs)


# ---------- пароли ----------

def hash_password(pw, salt=None, iters=PW_ITER):
    """→ (hash32, salt16, iters)."""
    salt = salt or os.urandom(16)
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters), salt, iters


def check_password_rules(pw, login=""):
    """Пароль панели: не короче PW_MIN, не равен логину, не из одного символа."""
    if not isinstance(pw, str) or len(pw) < PW_MIN:
        raise AuthError("пароль короче %d символов" % PW_MIN)
    if len(pw) > 256:
        raise AuthError("пароль длиннее 256 символов")
    if login and pw.lower() == login.lower():
        raise AuthError("пароль совпадает с логином")
    if len(set(pw)) < 4:
        raise AuthError("в пароле меньше 4 разных символов")


def check_login_rules(login):
    """Логин панели: 3–32 символа, латиница, цифры, _ . -"""
    import re
    if not isinstance(login, str) or not re.match(r"^[A-Za-z0-9_.-]{3,%d}$" % LOGIN_MAX, login):
        raise AuthError("логин: 3–%d символов, латиница, цифры, _ . -" % LOGIN_MAX)


def verify_password(pw, h, salt, iters):
    """Совпадает ли пароль с хешем (постоянное время сравнения)."""
    calc, _, _ = hash_password(pw, bytes(salt), int(iters))
    return hmac.compare_digest(calc, bytes(h))


# ---------- TOTP ----------

def totp_new_secret():
    """Новый секрет TOTP (20 б)."""
    return os.urandom(20)


def totp_b32(secret):
    """Секрет в base32 (для ручного ввода в приложение)."""
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def totp_uri(secret, login):
    """otpauth:// для приложений-аутентификаторов."""
    from urllib.parse import quote
    return "otpauth://totp/AsdaAdmin:%s?secret=%s&issuer=AsdaAdmin&digits=%d&period=%d" % (
        quote(login), totp_b32(secret), TOTP_DIGITS, TOTP_STEP)


def totp_code(secret, counter):
    """Код HOTP для счётчика (RFC 4226 §5.3)."""
    mac = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    v = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return str(v).zfill(TOTP_DIGITS)


def totp_match(secret, code, now=None):
    """Номер шага, на котором код верен (окно ±1 шаг), иначе None."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return None
    c = int((now if now is not None else time.time()) // TOTP_STEP)
    for d in (-1, 0, 1):
        if hmac.compare_digest(totp_code(secret, c + d), code):
            return c + d
    return None


def totp_check(secret, code, now=None):
    """Код верен в окне ±1 шаг."""
    return totp_match(secret, code, now) is not None


def _totp_key():
    """Ключ шифрования секретов TOTP (из файла секретов сервера)."""
    return bytes.fromhex(db._secret("TOTP_KEY"))


def totp_seal(secret, key=None):
    """Зашифровать секрет → nonce12 + шифротекст."""
    key = key or _totp_key()
    nonce = os.urandom(12)
    ks = hmac.new(key, nonce, hashlib.sha256).digest()
    return nonce + bytes(a ^ b for a, b in zip(secret, ks))


def totp_open(blob, key=None):
    """Расшифровать секрет."""
    key = key or _totp_key()
    blob = bytes(blob)
    nonce, ct = blob[:12], blob[12:]
    ks = hmac.new(key, nonce, hashlib.sha256).digest()
    return bytes(a ^ b for a, b in zip(ct, ks))


# ---------- пользователи ----------

USER_COLS = ("id, login, display, role, pw_hash, pw_salt, pw_iter, totp_enc, totp_on, totp_last, disabled, fail_count, "
             "locked_until, created_at, created_by, pw_changed_at, last_login_at, last_login_ip")


def get_user(cn, login=None, uid=None):
    """Строка пользователя по логину или id, иначе None."""
    if uid is not None:
        r = db.admin_rows(cn, "SELECT %s FROM adm.users WHERE id = ?" % USER_COLS, (int(uid),))
    else:
        r = db.admin_rows(cn, "SELECT %s FROM adm.users WHERE login = ?" % USER_COLS, (login or "",))
    return r[0] if r else None


def public_user(u):
    """Пользователь без секретов (для API)."""
    return {k: (v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v) for k, v in u.items()
            if k not in ("pw_hash", "pw_salt", "pw_iter", "totp_enc", "totp_last")}


def count_users(cn):
    """Число пользователей панели."""
    return db.admin_rows(cn, "SELECT COUNT(*) AS n FROM adm.users")[0]["n"]


def authenticate(cn, login, pw, code, ip):
    """Проверка входа → строка пользователя; отказ → AuthError (неудача засчитывается, если пользователь есть).

    Возвращает (user, need_totp_setup). Причина отказа одна на «нет пользователя / неверный пароль / неверный код /
    замок / окно логина / вход снаружи без второго фактора» — по ответу не узнать, что логин есть и что пароль верен
    (ревизия 16.11 вечер В2: прежний ответ «нужен код» подтверждал пароль без кода)."""
    cfg = config.get()
    fail = AuthError(LOGIN_FAIL % (cfg.login_fail_limit, cfg.login_lock_minutes))
    u = get_user(cn, login=login)
    # Ревизия А0 №9: «нет логина», «неверный пароль» и «замок» дают ОДИН ответ — по нему не узнать, что логин есть.
    if not u:
        if _user_window_hit(login or "?", ip):
            time.sleep(0.4)                            # окно исчерпано — без хеша (не жечь ЦП), время ответа то же
            raise fail
        _burn(pw, ip)                                  # то же время ответа, что и для существующего логина
        raise fail
    if _locked(u["login"], ip) or _user_window_hit(u["login"], ip):
        time.sleep(0.4)                                # замок/окно — без хеша (перепроверка В2-н1: не занимать слоты)
        raise fail
    if not verify_limited(pw or "", u["pw_hash"], u["pw_salt"], u["pw_iter"], ip):
        _fail(cn, u, cfg, ip)
        raise fail
    if u["totp_on"]:
        step = totp_match(totp_open(u["totp_enc"]), code) if code else None
        # Ревизия А0 №10: код одноразовый — шаг новее уже использованного (adm.users.totp_last). Проверка и запись —
        # ОДНИМ условным UPDATE: два одновременных входа с одним кодом не пройдут оба.
        took = step is not None and db.admin_rows(
            cn, "SET NOCOUNT ON; UPDATE adm.users SET totp_last = ? OUTPUT INSERTED.id WHERE id = ? "
                "AND (totp_last IS NULL OR totp_last < ?)", (step, u["id"], step))
        if not took:
            _fail(cn, u, cfg, ip)
            raise fail
    elif not trusted_ip(ip):
        # снаружи VPN/частной сети — только со вторым фактором (любая роль); включить его можно, войдя из VPN
        _fail(cn, u, cfg, ip)
        raise fail
    if u["disabled"]:                                   # сообщается только знающему пароль и код
        raise AuthError("учётка панели отключена")
    db.admin_rows(cn, "UPDATE adm.users SET fail_count = 0, locked_until = NULL, last_login_at = SYSDATETIME(), "
                      "last_login_ip = ? WHERE id = ?", (ip[:45], u["id"]))
    clear_locks(u["login"], ip)
    return u, (u["role"] in TOTP_REQUIRED and not u["totp_on"])


def totp_confirm(uid, code):
    """★ А5.1 (20.11.2026): второй фактор для необратимого действия из браузера (постановка управления стойкой в задания) — свежий
    код TOTP этого пользователя, одноразовый: шаг новее adm.users.totp_last, проверка и запись одним условным UPDATE (как при входе).
    → None; второй фактор не включён / код не подошёл — AuthError."""
    if uid is None:
        raise AuthError("второй фактор: нет пользователя панели")
    # ★ ревизия 41 С-1: предел попыток — не чаще CONFIRM_RATE в минуту и после login_fail_limit неверных подряд — замок на
    #   login_lock_minutes (украденная cookie сессии не подберёт 6 цифр). Счётчик — в памяти службы, как замок входа; отказы и замок
    #   пишутся в adm.audit самой операцией (ops.run, итог refused).
    cfg = config.get()
    now = time.time()
    with _lock_mx:
        e = _confirm_fails.setdefault(int(uid), [0, 0.0, []])
        if e[1] > now:
            raise AuthError("второй фактор: %d неверных кодов подряд — подтверждение закрыто на %d мин"
                            % (cfg.login_fail_limit, cfg.login_lock_minutes))
        e[2] = [t for t in e[2] if t > now - 60] + [now]
        if len(e[2]) > CONFIRM_RATE:
            raise AuthError("второй фактор: слишком много попыток подтверждения — подождите минуту")
    cn = db.admin()
    try:
        u = get_user(cn, uid=uid)
        if not u or not u["totp_on"]:
            raise AuthError("второй фактор не настроен")
        step = totp_match(totp_open(u["totp_enc"]), code) if code else None
        took = step is not None and db.admin_rows(
            cn, "SET NOCOUNT ON; UPDATE adm.users SET totp_last = ? OUTPUT INSERTED.id WHERE id = ? "
                "AND (totp_last IS NULL OR totp_last < ?)", (step, u["id"], step))
        with _lock_mx:
            e = _confirm_fails[int(uid)]
            if took:
                e[0], e[1] = 0, 0.0
            else:
                e[0] += 1
                if e[0] >= cfg.login_fail_limit:
                    e[0], e[1] = 0, now + cfg.login_lock_minutes * 60
        if not took:
            raise AuthError("код второго фактора не подошёл (нужен свежий код из приложения, не тот, которым входили)")
    finally:
        cn.close()


CONFIRM_RATE = 10        # ★ ревизия 41 С-1: попыток подтверждения вторым фактором в минуту на пользователя
_confirm_fails = {}      # id пользователя → [неверных подряд, замок до (time.time()), [времена попыток за минуту]]


# Замок входа — по паре (логин, IP), в памяти службы (перепроверка ревизии А0 №9: замок «на учётку» позволял любому
# узлу VPN пятью неверными паролями держать владельца запертым бесконечно). Подбор с одного адреса по-прежнему
# упирается в замок, а со многих — в предел попыток с IP (api/server.py LOGIN_RATE). adm.users.fail_count — только счётчик.
_lock_mx = threading.Lock()
_fails = {}          # (логин в нижнем регистре, ip) → [неудач подряд, замок до (time.time())]


def _locked(login, ip):
    """Заперт ли вход этого логина с этого адреса."""
    with _lock_mx:
        e = _fails.get((login.lower(), ip))
        return bool(e and e[1] > time.time())


def clear_locks(login, ip=None):
    """Снять замки логина (с одного адреса или со всех)."""
    with _lock_mx:
        for k in [k for k in _fails if k[0] == login.lower() and (ip is None or k[1] == ip)]:
            del _fails[k]


def _fail(cn, u, cfg, ip):
    """Засчитать неудачу пары (логин, IP); на пороге — замок на login_lock_minutes."""
    with _lock_mx:
        e = _fails.setdefault((u["login"].lower(), ip), [0, 0.0])
        e[0] += 1
        if e[0] >= cfg.login_fail_limit:
            e[0], e[1] = 0, time.time() + cfg.login_lock_minutes * 60
    db.admin_rows(cn, "UPDATE adm.users SET fail_count = CASE WHEN fail_count < 255 THEN fail_count + 1 ELSE 255 END "
                      "WHERE id = ?", (u["id"],))


# ---------- сессии ----------

def _th(token):
    """SHA-256 токена сессии."""
    return hashlib.sha256(token.encode("ascii")).digest()


def session_create(cn, user, ip, ua):
    """Новая сессия → (token, csrf)."""
    cfg = config.get()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    db.admin_rows(cn, "INSERT adm.sessions (token_hash, user_id, csrf, expires_abs, ip, user_agent) "
                      "VALUES (?, ?, ?, DATEADD(hour, ?, SYSDATETIME()), ?, ?)",
                  (_th(token), user["id"], csrf, cfg.session_abs_hours, ip[:45], (ua or "")[:200]))
    return token, csrf


def session_get(cn, token):
    """Действующая сессия по токену → dict(user, csrf, need_totp_setup) или None; продлевает last_seen."""
    if not token or len(token) > 100:
        return None
    cfg = config.get()
    r = db.admin_rows(cn, "SELECT s.user_id, s.csrf, s.last_seen, s.expires_abs, s.revoked FROM adm.sessions s "
                          "WHERE s.token_hash = ?", (_th(token),))
    if not r:
        return None
    s = r[0]
    now = datetime.datetime.now()
    if s["revoked"] or s["expires_abs"] <= now or s["last_seen"] + datetime.timedelta(hours=cfg.session_hours) <= now:
        return None
    u = get_user(cn, uid=s["user_id"])
    if not u or u["disabled"]:
        return None
    if (now - s["last_seen"]).total_seconds() > 60:
        db.admin_rows(cn, "UPDATE adm.sessions SET last_seen = SYSDATETIME() WHERE token_hash = ?", (_th(token),))
    return {"user": u, "csrf": s["csrf"], "need_totp_setup": u["role"] in TOTP_REQUIRED and not u["totp_on"]}


def session_revoke(cn, token=None, user_id=None):
    """Отозвать одну сессию (по токену) или все сессии пользователя."""
    if token:
        db.admin_rows(cn, "UPDATE adm.sessions SET revoked = 1 WHERE token_hash = ?", (_th(token),))
    if user_id is not None:
        db.admin_rows(cn, "UPDATE adm.sessions SET revoked = 1 WHERE user_id = ? AND revoked = 0", (int(user_id),))


def session_revoke_others(cn, user_id, keep_token):
    """Отозвать все сессии пользователя, кроме текущей."""
    db.admin_rows(cn, "UPDATE adm.sessions SET revoked = 1 WHERE user_id = ? AND revoked = 0 AND token_hash <> ?",
                  (int(user_id), _th(keep_token or "")))


def session_cleanup(cn):
    """Удалить сессии, истёкшие больше суток назад."""
    db.admin_rows(cn, "DELETE FROM adm.sessions WHERE expires_abs < DATEADD(day, -1, SYSDATETIME()) "
                      "OR (revoked = 1 AND last_seen < DATEADD(day, -1, SYSDATETIME()))")
