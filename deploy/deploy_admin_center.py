# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
r"""deploy_admin_center.py — выкладка админ-центра на dev-сервер @@ASTORY_SERVER_HOSTNAME@@ (только SSH). 16.11.2026.

ШАГИ (каждый печатает итог; любой сбой — остановка с кодом ≠ 0):
  1. самотест без сети (tests/selftest.py) — не прошёл → не выкладываем;
  2. архив службы (код, панель, SQL, справочники data/ref) → scp в @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter\\_incoming;
  2б. ★ ревизия 57: пробный импорт нового пакета НА СЕРВЕРЕ (распаковка в _incoming\probe_<метка>, все разделы, API, планировщик) —
     не прошёл → код 6, прежняя служба не остановлена;
  3. на сервере: остановить задачу AsdaAdminCenter и её python; прежнюю установку (без secrets/_backup/logs) —
     в @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter\\_backup\\<метка>; распаковать новую;
  4. секреты (только при первом запуске): secrets\\asda_admin.ini — PASSWORD (пароль логина БД asda_admin) и TOTP_KEY
     (ключ шифрования секретов второго фактора); права файла — только Administrators и SYSTEM, наследование снято;
  5. SQL под Windows-входом Administrator через shared memory (sqlcmd -S lpc:.\SQLEXPRESS -E — sysadmin; у devgsaccount
     прав CREATE DATABASE/LOGIN нет, проверено 16.11.2026): adminc_01_database → adminc_02_schema (-d AsdaAdmin) →
     adminc_03_grants; пароль нового логина — переменной окружения AdminPw (не в командной строке); затем
     adminc_10_verify ПОД asda_admin (TCP, пароль — через SQLCMDPASSWORD) — каждая строка должна совпасть с ожиданием;
     волна А1: adminc_05_restore, adminc_06_items, adminc_08_charcopy и adminc_09_accounts (процедуры adm — до выдачи прав на них), adminc_04_ops (логин правок
     asda_ops, пароль OPS_PASSWORD) и adminc_11_verify_ops ПОД asda_ops;
     волна А2: adminc_07_bridge (мост P127: таблицы/процедуры adm.Bridge*, логин asda_bridge — пароль BRIDGE_PASSWORD) и
     adminc_12_verify_bridge ПОД asda_bridge (15 проверок «только процедуры узла»);
     волна А3 (19.11): adminc_13_changeset (наборы изменений adm.changeset / changeset_item, -d AsdaAdmin, после 03);
     волна А5.1 (20.11): adminc_14_jobs (задания планировщика adm.job, -d AsdaAdmin, после 03);
     шаг А5.4 (21.11): adminc_15_events (Joy1 adm.LimitationReset — сброс ежедневных заданий доски, до adminc_04_ops — там права);
     шаг А5.7 (21.11): adminc_16_dbbackup (бэкапы БД: adm.dbbackup*, подписанные процедуры adm.DbBackup*, логин подписи
     adm_dbbackup_signer — db_backupoperator в базах списка; -d AsdaAdmin, после 03); до него шаг 4в — папка @@ASTORY_SERVER_ROOT_ESC@@\\DbBackup
     (права Administrators, SYSTEM, NT SERVICE\\MSSQL$SQLEXPRESS; существующие файлы не трогаются);
     шаг А5.8 (21.11): adminc_17_bakdrop (каталог служебных копий adm.bakdrop_obj, журнал удалений adm.bakdrop_log, подписанные
     adm.BakScan / adm.BakDrop, логин подписи adm_bakdrop_signer — VIEW DEFINITION и CONTROL только на копии «можно убрать»; -d AsdaAdmin,
     после adminc_16 — нужны adm.dbbackup*); сам файл ничего не удаляет;
     шаг А6.3 (21.11): adminc_18_econ (суточный снимок золота adm.EconDaily / adm.EconDailyChar, права asda_admin SELECT и INSERT;
     -d AsdaAdmin, после adminc_17); игровые базы не трогает;
     шаг А6.6 (22.11): adminc_19_acdaily (суточный отчёт античита adm.AcDaily, права asda_admin SELECT и INSERT; -d AsdaAdmin, после
     adminc_18); игровые базы не трогает;
     шаг А6.11 (22.11): adminc_20_names (отметки очереди имён adm.NameReview, права asda_admin SELECT и INSERT; -d AsdaAdmin, после
     adminc_19); игровые базы не трогает;
     шаг А6.11 «жалобы» (22.11): adminc_23_reports (жалобы игроков из бота Discord adm.PlayerReport / File / Reply, процедуры adm.Report*,
     логин бота asda_reports — пароль REPORTS_PASSWORD, только EXECUTE четырёх процедур; копия пароля одной строкой — secrets\\reports_bot.ini
     для бота на ПК; -d AsdaAdmin, после adminc_20) и adminc_23_reports_verify ПОД asda_reports (19 проверок); игровые базы не трогает;
     шаг А6.9 (22.11): adminc_22_gp7adjust (AsdaStoryLogin: схема adm, журнал корректировок adm.GP7AdjustLog, процедура adm.GP7Adjust,
     пользователь asda_ops только с EXECUTE adm.GP7Adjust; после adminc_04 и adminc_21); проверки — в adminc_10 и adminc_11;
     шаг А6.12 (22.11): adminc_24_chat (joylog1.chat журнала чата P129: asda_admin — SELECT, asda_ops — EXECUTE UP_ChatMuteSet / UP_ChatMuteLift
     и SELECT chat.mute; sqlcmd -x -I; после adminc_21); схемы chat ещё нет — «adminc_24: пропущено», код 0, строка итога «ПРОПУЩЕНО»;
     проверки — в adminc_10 и adminc_11 (без схемы — строка-отметка);
     шаг А6.10 (23.11): adminc_25_attendance (Joy1: журнал ручных отметок adm.AttendanceAdjustLog, процедура adm.AttendanceAdjust, asda_ops —
     только EXECUTE; sqlcmd -x -I; после adminc_04); проверки — в adminc_10 и adminc_11;
     шаг А7.1 (23.11): adminc_26_releases (снимок конвейера выпуска с ПК adm.ReleasePcStatus; asda_admin — SELECT, INSERT, UPDATE только
     seen_utc / seen_count, без DELETE; -d AsdaAdmin -x -I, после adminc_23); игровые базы не трогает; проверки — в adminc_10;
     шаг А7.2 (23.11): adminc_27_crashes (сводка сбоев клиента с ПК adm.ClientCrash / ClientCrashSig / ClientCrashSync; asda_admin — SELECT
     и EXECUTE adm.ClientCrashPut / adm.ClientCrashSyncAdd, прямой записи нет; -d AsdaAdmin -x -I, после adminc_26); проверки — в adminc_10;
     шаг А7.4 (23.11): adminc_28_outbox (очередь объявлений в Discord adm.Outbox; бот asda_reports — только EXECUTE adm.OutboxClaim / Done /
     DelClaim / DelDone, asda_admin — SELECT и EXECUTE пяти процедур панели; -d AsdaAdmin -x -I, после adminc_27) и adminc_28_outbox_verify ПОД
     asda_reports (15 проверок); проверки панели — в adminc_10;
     шаг А7.5 (23.11): adminc_29_telegram (Telegram владельцу в той же очереди adm.Outbox, transport telegram; выключатели adm.NotifyRule —
     общий по умолчанию выключен, память adm.NotifyState, отметки adm.NotifyBeat; отправитель asda_reports — только EXECUTE adm.TgClaim / TgDone /
     TgBeatGet, asda_admin — SELECT трёх таблиц и EXECUTE пяти процедур панели; -d AsdaAdmin -x -I, после adminc_28) и
     adminc_29_telegram_verify ПОД asda_reports (17 проверок); проверки панели — в adminc_10; токена Telegram на сервере нет;
     шаг А7.6 (24.11): adminc_30_community (копия реестра бота adm.BotSnap / BotApp / BotTester / BotWarn / BotBan и очередь команд боту
     adm.BotCmd; бот asda_reports — только EXECUTE adm.BotCmdClaim / BotCmdDone / BotSnapPut, asda_admin — SELECT шести таблиц и EXECUTE четырёх
     процедур панели; -d AsdaAdmin -x -I, после adminc_29) и adminc_30_community_verify ПОД asda_reports (★ р79 М-3: 36 проверок — каждое GRANT и
     DENY шага); проверки панели — в adminc_10;
     шаг А7.7 (24.11): adminc_31_notes (заметки к выпуску: снимки changelog с ПК adm.NotesSnap, черновик adm.NotesDraft, публикации
     adm.NotesPost / NotesPostEntry; asda_admin — SELECT четырёх таблиц и EXECUTE шести процедур панели, прямой записи нет; бот asda_reports —
     ничего; в CK_adm_Outbox_route вид notes — adminc_29; -d AsdaAdmin -x -I, после adminc_30) и adminc_31_notes_verify ПОД asda_reports
     (★ р83: 17 проверок, все 0); проверки панели — в adminc_10;
     25.11: adminc_32_botreg (команда бота /register: AsdaStoryOp adm.BotAccountRegister и привязка adm.BotAccount; бот asda_reports —
     только EXECUTE; -x -I, после adminc_09 и adminc_23) и adminc_32_botreg_verify ПОД asda_reports (16 проверок);
     экземпляр SQL Server — SQLEXPRESS (как у AstoryServer/Prerequisites/setup_server.ps1); другой — переменная окружения
     ASTORY_SQL_INSTANCE на ПК выкладки (имя экземпляра, MSSQLSERVER — экземпляр по умолчанию);
  4б. сертификат HTTPS (только при первом запуске): самоподписанный ECDSA P-256 на 10 лет, адреса VPN/LAN/внешний —
     делается на ПК (pip cryptography), по scp в secrets\tls.crt / secrets\tls.key, ключ на ПК стирается;
  6. брандмауэр: входящий TCP 17890 с любых адресов (решение владельца 16.11.2026; правило AsdaAdminCenter, пересоздаётся);
  7. задача планировщика AsdaAdminCenter: при старте машины, от SYSTEM, run_service.bat (перезапуск при падении,
     ожидание адреса VPN); запуск сейчас;
  8. проверка снаружи: GET https://@@ASTORY_SERVER_VPN_IP@@:17890/api/me → 401 JSON (служба жива и требует входа).
     ★ ревизия 57: не поднялась → хвост журнала, возврат прежней версии из _backup\<метка> и повторная проверка (код 4 — откат,
     прежняя отвечает; 5 — не поднялась и прежняя).
Откат: schtasks /Delete /TN AsdaAdminCenter /F; netsh advfirewall firewall delete rule name=AsdaAdminCenter;
       папку @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter удалить (или вернуть из _backup). Скрипта отката SQL в публичном репозитории нет:
       база панели — DROP DATABASE AsdaAdmin, логины asda_admin / asda_ops / asda_bridge / asda_reports — DROP LOGIN, объекты adm.* в
       игровых базах — DROP по списку из sql/adminc_*.sql (sqlcmd -S lpc:.\SQLEXPRESS -E).
Игровую стойку (процессы, файлы v2, игровые таблицы) скрипт не трогает.
ЗАПУСК: python AstoryAdminCenter/deploy/deploy_admin_center.py [--skip-selftest]
  --skip-selftest  не запускать шаг 1 (самотест уже прошёл этим же кодом);
  --help, -h       эта справка, выкладка НЕ запускается; неизвестный ключ — справка и код 2 без действий (20.11.2026).
"""
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core import config, hostshell  # noqa: E402

REMOTE = config.SERVICE_ROOT                                   # @@ASTORY_SERVER_ROOT@@\AdminCenter
PACK_DIRS = ("core", "domains", "api", "web", "sql", "data/ref")          # ★ ревизия 57 (мелочь 1): tests/ на сервер не выкладывается (самотест — только ПК)
PACK_FILES = ("asda_admin.py", "README.md", "deploy/run_service.bat")
TASK = "AsdaAdminCenter"
BACKUP_DIR = r"@@ASTORY_SERVER_ROOT@@\DbBackup"                               # ★ А5.7: папка бэкапов БД панели (= adm.dbbackup_cfg.folder по умолчанию)
# Открытый сертификат службы (без ключа) — поставить в «Доверенные корневые центры» своих устройств (ревизия 16.11
# вечер В3: иначе подмену сертификата не отличить от обычного предупреждения браузера). Перезаписывается при новом.
PUBLIC_CRT = os.path.join(HERE, "asda_admin_center.crt")
PORT = 17890


def step(t):
    """Заголовок шага."""
    print("\n== " + t, flush=True)


def ps(script, timeout=180):
    """PowerShell на сервере (ошибка → исключение)."""
    return hostshell.powershell("$ErrorActionPreference='Stop';" + script, timeout=timeout)


BUILT_REF = {"data/ref/ac_kinds.json"}                         # ★ А6.1: справочники, которые build_zip строит сам (локальная копия не берётся)


def build_zip():
    """Архив службы в памяти → bytes."""
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in PACK_DIRS:
            for base, dirs, files in os.walk(os.path.join(ROOT, d)):
                dirs[:] = [x for x in dirs if x != "__pycache__"]
                for f in files:
                    full = os.path.join(base, f)
                    arc = os.path.relpath(full, ROOT).replace("\\", "/")
                    if arc in BUILT_REF:                   # ★ ревизия 50 п.10: строится ниже из исходников — без дубля записи в архиве
                        continue
                    z.write(full, arc)
                    n += 1
        # перепроверка 19 М1: копия реестра банов (подарок «всем игрокам» исключает забаненных, как старая утилита)
        ban = os.path.join(ROOT, "DiscordBot", "BANNED_PLAYERS.md")          # ★ 25.11 (М-2): от корня клона, а не по имени папки
        if os.path.exists(ban):
            z.write(ban, "data/ref/banned_players.md")
            n += 1
        # 19.11 (А1 «Учётки», research_accounts_rest.md §6): привязки «логин ↔ Discord» из файла бота — БЕЗ паролей (в
        # playtest_accounts.txt они открытым текстом; разбор domains/discordlinks.parse_playtest захватывает только @handle,
        # Discord ID, логин и пометку бана). Сам файл бота в пакет не попадает.
        pt = os.path.join(os.path.dirname(ban), "playtest_accounts.txt")
        if os.path.exists(pt):
            from domains import discordlinks
            z.writestr("data/ref/discord_links.json", discordlinks.build_json(pt))
            n += 1
        # 19.11 (А3 «Данные: магазины»): снимок клиентских таблиц магазинов порта — служба на сервере не видит RawAssets
        #   (domains/shopdata.Client: витрины 6000/15300, лавки NPC, item_list.Price, packagetable, booster_list, гача); строится тут, на ПК
        #   25.11 (публичный клон, К-2): нет AstoryClient/RawAssets (публичный AstoryClient его не несёт) — снимок не строится, выкладка идёт
        #   дальше с предупреждением; на сервере разделы данных клиента отвечают «снимок клиентских таблиц не собран» (shopdata.Client.load)
        from domains import shopdata
        if shopdata.client_sources_present():
            z.writestr("data/ref/shop_client.json", json.dumps(shopdata.build_client_snapshot(), ensure_ascii=False, separators=(",", ":")))
            n += 1
        else:
            print("ПРЕДУПРЕЖДЕНИЕ: нет %s (AstoryClient/RawAssets) — снимок клиентских таблиц data/ref/shop_client.json не собран; "
                  "разделы данных клиента на сервере покажут «снимок не собран»" % shopdata.CLIENT_FILES.get("item_list", shopdata.ITEMDB))
        # 19.11 (А4.2 «Данные игры → Тексты»): снимок текстов RU / EN порта (названия и описания предметов, навыков, званий, мобов, NPC,
        #   карт, заданий) — для поиска и оценки позиций «Тексты» службой на сервере; строится тут, на ПК (domains/cs_kinds/texts.py)
        #   25.11 (публичный клон, К-2): без текстов клиента (AstoryClient/RawAssets) снимок не строится — предупреждение, выкладка дальше
        from domains.cs_kinds import texts as _texts
        if _texts.sources_present():
            z.writestr("data/ref/text_client.json", json.dumps(_texts.build_snapshot(), ensure_ascii=False, separators=(",", ":")))
            n += 1
        else:
            print("ПРЕДУПРЕЖДЕНИЕ: нет %s (AstoryClient/RawAssets) — снимок текстов data/ref/text_client.json не собран; "
                  "раздел «Тексты» на сервере покажет «снимок не собран»" % _texts.ru_csv("item.name"))
        # 21.11 (А5.5 «Настройки патчей»): каталог ключей ini серверных DLL по исходникам (Config.cpp, места чтения, пределы, зависимости,
        #   реестр INDEX.md) — служба на сервере исходников не видит; строится тут, на ПК (domains/patchcfg_src.py)
        from domains import patchcfg_src as _pcs
        z.writestr("data/ref/patchcfg_catalog.json", json.dumps(_pcs.build(), ensure_ascii=False, separators=(",", ":")))
        n += 1
        # ★ А6.1 (21.11): каталог видов журнала античита ac.* по AcJournal.cpp KindText (номер, патч, служебная) — служба на сервере
        #   исходников не видит; строится тут, на ПК (domains/acjournal_src.py); проблемы разбора — отказ выкладки, а не немой каталог
        from domains import acjournal_src as _acs
        _acat = _acs.build()
        if _acat["problems"]:
            raise SystemExit("каталог видов ac.* разобран с ошибками: %s" % " | ".join(_acat["problems"][:5]))
        z.writestr("data/ref/ac_kinds.json", json.dumps(_acat, ensure_ascii=False, separators=(",", ":")))
        n += 1
        # ★ А6.2 (21.11): сверка висящих подарков gp7 — та же gift_reconcile.py шлюза (AstoryServer/Patches/Gp7Gateway/tools), что у консоли:
        #   раздел «Деньги» зовёт её hint (domains/money.reconcile); служба исходников порта не видит — копия кладётся в ext/ без правок
        from domains import money as _money
        if not os.path.isfile(_money.RECONCILE_SRC):
            raise SystemExit("нет %s — раздел «Деньги» без сверки подарков не выкладывается" % _money.RECONCILE_SRC)
        _b = _readb(_money.RECONCILE_SRC)                 # ★ ревизия 57 (мелочь 4): одно чтение — в архив и в манифест одни и те же байты
        z.writestr("ext/gift_reconcile.py", _b)
        _ext_md5 = {"gift_reconcile.py": hashlib.md5(_b).hexdigest()}     # ★ ревизия 56 С-1: манифест копий ext/
        n += 1
        # ★ А6.4 (22.11): правило M3 (пары сделок, зеркала «…To») — тот же AstoryServer/Tools/Anticheat/ac_metrics_db.py с его ac_common.py и db_connect.py
        #   (импорт без побочных эффектов); раздел «Передачи и рынок» (domains/trade.m3) берёт его из ext/anticheat/ — копия без правок
        # ★ А6.6 (22.11): суточный отчёт (domains/acdaily) исполняет те же файлы и ещё ac_daily_report.py, ac_metrics_logs.py — копия без правок
        # ★ А6.8 (22.11): сверка лестницы (domains/autoblock) исполняет ac_case.py и читает ac_case_config.json — копия без правок
        from domains import acdaily as _acd, autoblock as _ab, trade as _trade
        for _f in sorted(set(_trade.AC_FILES) | set(_acd.AC_FILES) | set(_ab.AC_FILES)):
            _src = os.path.join(_trade.AC_SRC, _f)
            if not os.path.isfile(_src):
                raise SystemExit("нет %s — раздел «Передачи и рынок» без правила M3 не выкладывается, «Античит: суточный отчёт» — без исходника "
                                 "отчёта, «Античит: автоблок и EAC» — без лестницы ac_case" % _src)
            _b = _readb(_src)
            z.writestr("ext/anticheat/" + _f, _b)
            _ext_md5["anticheat/" + _f] = hashlib.md5(_b).hexdigest()
            n += 1
        # ★ ревизия 56 С-1: служба исполняет копии ext/ только при совпадении md5 с этим манифестом (domains/acsrc.read_verified)
        z.writestr("ext/MANIFEST.json", json.dumps(_ext_md5, ensure_ascii=False, sort_keys=True, indent=1))
        n += 1
        for f in PACK_FILES:
            arc = os.path.basename(f) if f.startswith("deploy/") else f
            z.write(os.path.join(ROOT, f), arc)
            n += 1
    print("файлов в архиве: %d, размер %.1f МБ" % (n, buf.tell() / 1048576))
    return buf.getvalue()


def _readb(path):
    """Байты файла (одно чтение: архив и манифест копий ext/ получают одно и то же)."""
    with open(path, "rb") as f:
        return f.read()


PY_SERVER = r"@@ASTORY_SERVER_PYTHON@@"   # = run_service.bat
# ★ 25.11 (М-7): экземпляр SQL Server на сервере — как -SqlInstance у AstoryServer/Prerequisites/setup_server.ps1 (по умолчанию SQLEXPRESS);
#   другой — переменная окружения ASTORY_SQL_INSTANCE на ПК выкладки (MSSQLSERVER — экземпляр по умолчанию)
SQL_INSTANCE = (os.environ.get("ASTORY_SQL_INSTANCE") or "SQLEXPRESS").strip().lstrip(".\\")
SQL_LPC = "lpc:." if SQL_INSTANCE.upper() == "MSSQLSERVER" else "lpc:.\\" + SQL_INSTANCE          # sqlcmd -S (shared memory)
SQL_SVC = "NT SERVICE\\MSSQLSERVER" if SQL_INSTANCE.upper() == "MSSQLSERVER" else "NT SERVICE\\MSSQL$" + SQL_INSTANCE   # служба SQL — права папки бэкапов
# ★ ревизия 57 Н-2: пробный импорт НОВОГО пакета на самом сервере (настоящий on_server, путей порта там нет) — все разделы, сервер API,
#   планировщик; без подключения к базе (импорт без побочных эффектов). Нет PROBE_OK — выкладка останавливается ДО остановки прежней службы.
PROBE_CODE = ("import sys; sys.path.insert(0, '.'); import domains; domains.load_all(); from api import server; from core import sched, config; "
              "print('PROBE_OK on_server=%s routes=%d ops=%d' % (config.get().on_server, len(server.ROUTES), len(__import__('core.ops', "
              "fromlist=['x']).REGISTRY)))")


# ★ А6.7: каталог доказательств дел — создать, если нет; права — только наследование от корня службы; проверка: явных записей нет, в списке
#   доступа только Administrators и SYSTEM (иначе — отказ шага, служба возвращается на прежнюю версию)
CASES_DIR_PS = r"""
$d = Join-Path '%(r)s' 'cases'
New-Item -ItemType Directory -Force -Path $d | Out-Null
icacls $d /reset /C /Q | Out-Null
if ($LASTEXITCODE) { throw "icacls reset $d" }
$acl = Get-Acl -LiteralPath $d
$who = @($acl.Access | %% { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } | Sort-Object -Unique)
$own = @($acl.Access | ? { -not $_.IsInherited })
$bad = @($who | ? { $_ -ne 'S-1-5-32-544' -and $_ -ne 'S-1-5-18' })      # Administrators, SYSTEM (по SID: имена на сервере локализованы)
if ($acl.AreAccessRulesProtected -or $own.Count -or $bad.Count -or $who.Count -lt 2) { throw ("права " + $d + ": " + ($who -join ', ') + "; свои записи " + $own.Count + "; защищено " + $acl.AreAccessRulesProtected) }
'CASESACL ' + $d + ': ' + ($who -join ', ') + ' (наследуются от корня службы); дел-папок ' + @(Get-ChildItem $d -Directory).Count
(icacls $d | Out-String).Trim()
"""


# ★ 25.11.2026: справочники data/ref — 54 из 56 МБ пакета; по VPN издалека (RTT 300 мс) пакет шёл >10 мин и scp падал по таймауту.
#   Если каждый файл data/ref пакета совпадает по md5 с установленным на сервере (и набор файлов тот же) — пакет едет без data/ref,
#   а проба и установка берут справочники из текущей установки сервера. Любое расхождение или ошибка чтения — пакет целиком, как раньше.
REF_PREFIX = "data/ref/"
REF_MD5_PS = r"""
$d = '%(r)s\data\ref'
if (-not (Test-Path -LiteralPath $d)) { 'NOREF'; return }
$n = $d.Length + 1
Get-ChildItem -LiteralPath $d -Recurse -File | %% { 'REF ' + (Get-FileHash -LiteralPath $_.FullName -Algorithm MD5).Hash.ToLower() + ' ' + $_.FullName.Substring($n).Replace('\', '/') }
"""


REF_REUSE_LIST = "data/ref_reuse.txt"   # список файлов data/ref, которые сервер берёт из прежней установки (по строке)


def ref_reuse_on_server(data, run=None):
    """Файлы data/ref пакета, которые на сервере уже лежат с тем же md5 → (список имён, текст). Пусто — пакет целиком.
    ★ 25.11.2026 (вторая правка): связь рвалась и на 4 изменённых файлах — в пакет идут только изменённые справочники."""
    run = run or ps
    z = zipfile.ZipFile(io.BytesIO(data))
    mine = {i.filename[len(REF_PREFIX):]: hashlib.md5(z.read(i)).hexdigest() for i in z.infolist()
            if i.filename.startswith(REF_PREFIX) and not i.is_dir()}
    try:
        out = run(REF_MD5_PS % {"r": REMOTE}, timeout=300)
    except Exception as ex:
        return [], "справочники сервера не прочитаны (%s) — пакет целиком" % str(ex)[:200]
    theirs = {}
    for line in out.splitlines():
        if line.startswith("REF "):
            _, h, name = line.split(" ", 2)
            theirs[name.strip()] = h
    same = sorted(n for n, h in mine.items() if theirs.get(n) == h)
    return same, "справочники data/ref: %d из %d совпадают с сервером по md5 (берутся из прежней установки), в пакете — %d изменённых" % (
        len(same), len(mine), len(mine) - len(same))


def strip_ref_files(data, same):
    """Пакет без файлов data/ref из списка same + список их имён (REF_REUSE_LIST) для сервера."""
    drop = set(REF_PREFIX + n for n in same)
    src, buf = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            if i.filename not in drop:
                z.writestr(i, src.read(i))
        z.writestr(REF_REUSE_LIST, "\n".join(same))
    return buf.getvalue()


def ref_same_on_server(data, run=None):
    """data/ref пакета совпадает с установленным на сервере → (True, текст) / (False, причина)."""
    run = run or ps
    z = zipfile.ZipFile(io.BytesIO(data))
    mine = {i.filename[len(REF_PREFIX):]: hashlib.md5(z.read(i)).hexdigest() for i in z.infolist()
            if i.filename.startswith(REF_PREFIX) and not i.is_dir()}
    try:
        out = run(REF_MD5_PS % {"r": REMOTE}, timeout=300)
    except Exception as ex:
        return False, "справочники сервера не прочитаны (%s) — пакет целиком" % str(ex)[:200]
    theirs = {}
    for line in out.splitlines():
        if line.startswith("REF "):
            _, h, name = line.split(" ", 2)
            theirs[name.strip()] = h
    if not mine or mine != theirs:
        diff = sorted(set(mine.items()) ^ set(theirs.items()))
        return False, "справочники изменились (%d расхождений, напр. %s) — пакет целиком" % (len(diff), diff[0][0] if diff else "набор пуст")
    return True, "справочники data/ref (%d файлов) совпадают с сервером по md5 — в пакет не кладутся" % len(mine)


def strip_ref(data):
    """Тот же пакет без data/ref/."""
    src, buf = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            if not i.filename.startswith(REF_PREFIX):
                z.writestr(i, src.read(i))
    return buf.getvalue()


def probe_package(stamp, run=None, reuse_ref=False):
    """★ ревизия 57 Н-2 (а): распаковать пакет в _incoming\\probe_<метка> и импортировать его на сервере → (ok, вывод). Папка пробы
    удаляется. run — подстановка PowerShell для самотеста."""
    run = run or ps
    try:
        out = run(r"""
$root='%(r)s'; $pd = Join-Path $root ('_incoming\probe_' + '%(s)s')
if (Test-Path $pd) { Remove-Item $pd -Recurse -Force }
Expand-Archive -LiteralPath (Join-Path $root '_incoming\pkg_%(s)s.zip') -DestinationPath $pd -Force
if ('%(reuse)s' -eq '1') {
  foreach ($n in @(Get-Content -LiteralPath (Join-Path $pd 'data\ref_reuse.txt') -Encoding UTF8 | ? { $_ })) {
    $to = Join-Path $pd ('data\ref\' + $n.Replace('/', '\')); New-Item -ItemType Directory -Force (Split-Path $to) | Out-Null
    Copy-Item -LiteralPath (Join-Path $root ('data\ref\' + $n.Replace('/', '\'))) -Destination $to -Force
  }
}
$env:PYTHONIOENCODING = 'utf-8'
Push-Location $pd
$ErrorActionPreference = 'Continue'
$o = & '%(py)s' -c "%(code)s" 2>&1 | Out-String
Pop-Location
Remove-Item $pd -Recurse -Force
$o
""" % {"r": REMOTE, "s": stamp, "py": PY_SERVER, "code": PROBE_CODE, "reuse": "1" if reuse_ref else "0"}, timeout=300)
    except Exception as ex:
        return False, "%s: %s" % (ex.__class__.__name__, str(ex)[:1500])
    import re
    return bool(re.search(r"PROBE_OK on_server=True routes=\d+", out)), out


def wait_up(tries=20, pause=2.0, opener=None):
    """Шаг 8: служба отвечает 401 на /api/me → (код, текст): 0 — ок, 3 — 200 без входа, 4 — не поднялась."""
    url = "https://%s:%d/api/me" % (config.SERVER_VPN_IP, PORT)
    if opener is None:
        import ssl
        if os.path.isfile(PUBLIC_CRT):                     # перепроверка В3: проверка цепочки по своему открытому сертификату
            nover = ssl.create_default_context(cafile=PUBLIC_CRT)
        else:
            nover = ssl.create_default_context()
            nover.check_hostname = False
            nover.verify_mode = ssl.CERT_NONE
            print("(нет %s — проверка без сертификата)" % PUBLIC_CRT)
        # без системного прокси этого ПК: он отвечает 502 за любой адрес VPN
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=nover)).open
    for i in range(tries):
        time.sleep(pause)
        try:
            opener(url, timeout=5)
            return 3, "неожиданно 200 без входа"
        except urllib.error.HTTPError as ex:
            body = ex.read().decode("utf-8", "replace")
            try:
                err = json.loads(body).get("error")
            except ValueError:
                err = None
            if ex.code == 401 and err:
                return 0, "служба отвечает: 401 «%s» — ок" % err
            print("ответ %d: %s" % (ex.code, body[:200]))
        except (urllib.error.URLError, OSError) as ex:
            print("ждём службу (%d): %s" % (i + 1, ex))
    return 4, "служба не ответила"


def after_start(stamp, wait=None, restore=None, log=None):
    """★ ревизия 57 Н-2 (б): шаг 8 с откатом. Служба не поднялась → хвост журнала, возврат прежней версии из _backup\\<метка>
    (restore_previous) и повторная проверка → (код, текст): 0 — новая поднялась, 4 — откат, прежняя поднялась, 5 — не поднялась и прежняя."""
    wait = wait or wait_up
    restore = restore or restore_previous
    log = log or (lambda: print(ps("Get-Content '%s\\logs\\service.log' -Tail 40 -ErrorAction SilentlyContinue | Out-String" % REMOTE)))
    code, text = wait()
    if code != 4:
        return code, text
    print(text)
    log()
    print("служба не поднялась — возвращаю прежнюю версию из _backup\\%s" % stamp)
    restore(stamp)
    code2, text2 = wait()
    if code2 == 0:
        return 4, "ВЫКЛАДКА ОТКАЧЕНА: новая версия не поднялась, прежняя возвращена и отвечает (%s)" % text2
    return 5, "!! служба не поднялась и после возврата прежней версии (%s) — нужен ручной разбор: schtasks /Run /TN %s" % (text2, TASK)


def scp(local, remote):
    """Копия файла на сервер."""
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
    r = subprocess.run([exe if os.path.exists(exe) else "scp", "-i", config.SSH_KEY, "-o", "BatchMode=yes", local,
                        "%s:%s" % (config.SSH_HOST, remote.replace("\\", "/"))], capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError("scp: " + r.stderr.decode("utf-8", "replace")[:300])


def make_tls_cert(stamp):
    """Самоподписанный сертификат HTTPS (ECDSA P-256, 10 лет) на все адреса сервера → (путь crt, путь key) во
    временной папке ПК. Делается на ПК (pip cryptography), потому что на сервере нет openssl; ключ после scp стирается."""
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AsdaAdminCenter " + config.SERVER_HOSTNAME)])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.IPAddress(ipaddress.ip_address(a)) for a in
           (config.SERVER_VPN_IP, config.SERVER_LAN_IP, config.SERVER_WAN_IP, "127.0.0.1")]
    san += [x509.DNSName(config.SERVER_HOSTNAME.lower()), x509.DNSName("localhost")]
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    tmp = os.environ.get("TEMP", ".")
    crt_p, key_p = os.path.join(tmp, "asda_tls_%s.crt" % stamp), os.path.join(tmp, "asda_tls_%s.key" % stamp)
    try:
        with open(crt_p, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_p, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    except BaseException:
        for f in (crt_p, key_p):                       # ключ на ПК не оставляем и при сбое записи
            if os.path.exists(f):
                os.remove(f)
        raise
    print("отпечаток SHA-256: " + cert.fingerprint(hashes.SHA256()).hex(":").upper())
    return crt_p, key_p


def restore_previous(stamp):
    """Ревизия 28 К-8 (19.11): шаг SQL/проверки прав не прошёл после остановки службы — вернуть прежнюю установку из
    _backup/<метка> и запустить задачу, чтобы панель не осталась выключенной. SQL уже применённых файлов не откатывается
    (выдачи прав аддитивны; полный откат SQL — вручную, см. «Откат» в шапке файла)."""
    try:
        print(ps(r"""
$root='%(r)s'; $b = Join-Path $root ('_backup\' + '%(s)s')
$keep='_incoming','_backup','secrets','logs','config.ini','otp_archive','cases'
if (Test-Path $b) {
  Get-ChildItem $root | ? { $keep -notcontains $_.Name } | Remove-Item -Recurse -Force
  Get-ChildItem $b | Move-Item -Destination $root
  Remove-Item $b -Force -Recurse
  'прежняя установка возвращена из ' + $b
} else { 'прежней установки нет — оставлена новая' }
if (Get-ScheduledTask -TaskName %(t)s -ErrorAction SilentlyContinue) { Start-ScheduledTask -TaskName %(t)s; 'задача %(t)s запущена' } else { 'задачи %(t)s нет — запустите выкладку заново' }
""" % {"r": REMOTE, "s": stamp, "t": TASK}))
        print("ВЫКЛАДКА ОТМЕНЕНА: служба работает на прежней версии; права НЕ сверены — исправьте и выложите заново")
    except Exception as ex:
        print("!! вернуть прежнюю установку не удалось: %s — служба может быть остановлена: schtasks /Run /TN %s" % (str(ex)[:300], TASK))


KNOWN_ARGS = ("--skip-selftest",)                              # ★ 20.11.2026: всё прочее — справка и выход без действий


def parse_args(argv):
    """★ 20.11.2026: разбор ключей ДО любого действия. --help / -h / неизвестный ключ → (код, None): справка напечатана, выкладки
    нет (раньше `--help` запускал настоящую выкладку). Без ключей и с --skip-selftest — прежнее поведение → (None, ключи)."""
    if any(a in ("-h", "--help", "/?") for a in argv):
        print(__doc__)
        return 0, None
    bad = [a for a in argv if a not in KNOWN_ARGS]
    if bad:
        print("неизвестный ключ: %s — выкладка НЕ запускалась.\n%s" % (" ".join(bad), __doc__))
        return 2, None
    return None, set(argv)


def main(argv):
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    rc, _keys = parse_args(argv)
    if rc is not None:
        return rc
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if "--skip-selftest" not in argv:
        step("1. самотест без сети")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "asda_admin.py"), "selftest"], capture_output=True,
                           timeout=2400)   # ★ А6.10 (23.11): полный офлайн-самотест (стенды SQL Server LocalDB) идёт десятки минут — 900 с не хватало
        tail = r.stdout.decode("utf-8", "replace").strip().splitlines()[-1:]
        print(tail[0] if tail else "(нет вывода)")
        if r.returncode != 0:
            print(r.stdout.decode("utf-8", "replace")[-3000:])
            return 1

    step("2. архив и копирование")
    data = build_zip()
    same, why = ref_reuse_on_server(data)
    print(why)
    reuse_ref = bool(same)
    if reuse_ref:
        data = strip_ref_files(data, same)
        print("пакет: %.1f МБ" % (len(data) / 1048576))
    tmp = os.path.join(os.environ.get("TEMP", "."), "asda_admin_%s.zip" % stamp)
    with open(tmp, "wb") as f:
        f.write(data)
    ps("New-Item -ItemType Directory -Force -Path '%s\\_incoming','%s\\_backup','%s\\logs','%s\\secrets' | Out-Null"
       % (REMOTE, REMOTE, REMOTE, REMOTE))
    scp(tmp, REMOTE + "\\_incoming\\pkg_%s.zip" % stamp)
    os.remove(tmp)
    print("ок")

    step("2б. пробный импорт нового пакета на сервере (прежняя служба ещё работает)")
    ok, out = probe_package(stamp, reuse_ref=reuse_ref)
    print(out.strip()[-3000:])
    if not ok:
        print("ВЫКЛАДКА ОСТАНОВЛЕНА до остановки службы: новый пакет не импортируется в режиме сервера — прежняя версия не тронута")
        return 6

    step("3. остановка, резервная копия, распаковка")
    print(ps(r"""
$root='%(r)s'
cmd /c "schtasks /End /TN %(t)s >nul 2>&1"   # задачи может ещё не быть (PS 5.1 рвётся на stderr родной программы)
Get-CimInstance Win32_Process | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*asda_admin.py*serve*' } | %% { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process | ? { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*AdminCenter\run_service.bat*' } | %% { $c=$_.ProcessId; Get-CimInstance Win32_Process | ? { $_.ParentProcessId -eq $c } | %% { Stop-Process -Id $_.ProcessId -Force }; Stop-Process -Id $c -Force }
# Ревизия А0 №4: каталог наследовал от H:\ право BUILTIN\Users на создание файлов — подложенный, например, json.py
# выполнился бы от SYSTEM. Права каталога — только Administrators и SYSTEM (наследование снято, на всё дерево).
# Права — только на корень; всё вложенное сбрасывается на наследование (icacls /grant с (OI)(CI) и /T оставлял
# у ФАЙЛОВ пустой список доступа — распаковка падала с «Отказано в доступе»).
icacls $root /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' /C /Q | Out-Null
if ($LASTEXITCODE) { throw "icacls $root" }
cmd /c "takeown /F `"$root`" /R /A /D Y >nul 2>&1"     # файлы службы создаёт SYSTEM — без владения права не сбросить
icacls (Join-Path $root '*') /reset /T /C /Q | Out-Null
if ($LASTEXITCODE) { throw "icacls reset" }
$keep='_incoming','_backup','secrets','logs','config.ini','otp_archive','cases'
$old = Get-ChildItem $root | ? { $keep -notcontains $_.Name }
if ($old) { $b = Join-Path $root ('_backup\' + '%(s)s'); New-Item -ItemType Directory -Force $b | Out-Null; $old | Move-Item -Destination $b; "бэкап: $b" } else { 'прежней установки нет' }
Get-ChildItem (Join-Path $root '_backup') -Directory | Sort-Object Name -Descending | Select-Object -Skip 5 | Remove-Item -Recurse -Force
Get-ChildItem (Join-Path $root '_incoming') -File | Sort-Object Name -Descending | Select-Object -Skip 3 | Remove-Item -Force
Expand-Archive -LiteralPath (Join-Path $root '_incoming\pkg_%(s)s.zip') -DestinationPath $root -Force
if ('%(reuse)s' -eq '1') {   # ★ 25.11.2026: справочники не ехали в пакете — те же файлы из прежней установки (md5 сверены до выкладки)
  $rb = Join-Path $root ('_backup\' + '%(s)s' + '\data\ref')
  if (-not (Test-Path -LiteralPath $rb)) { throw "нет $rb — справочники взять неоткуда" }
  $k = 0
  foreach ($n in @(Get-Content -LiteralPath (Join-Path $root 'data\ref_reuse.txt') -Encoding UTF8 | ? { $_ })) {
    $to = Join-Path $root ('data\ref\' + $n.Replace('/', '\')); New-Item -ItemType Directory -Force (Split-Path $to) | Out-Null
    Copy-Item -LiteralPath (Join-Path $rb $n.Replace('/', '\')) -Destination $to -Force; $k++
  }
  'справочники data/ref: ' + $k + ' взяты из прежней установки, всего ' + @(Get-ChildItem (Join-Path $root 'data\ref') -Recurse -File).Count + ' файлов'
}
'распаковано: ' + (Get-ChildItem $root -Recurse -File | ? { $_.FullName -notlike '*\_backup\*' -and $_.FullName -notlike '*\_incoming\*' }).Count + ' файлов'
""" % {"r": REMOTE, "t": TASK, "s": stamp, "reuse": "1" if reuse_ref else "0"}))

    step("3б. каталог доказательств дел (А6.7)")
    # ★ А6.7 (22.11, решение владельца №1): доказательства дел AC-NNNN — в каталоге службы (domains/cases.CASES_ROOT); права — наследование
    #   от @@ASTORY_SERVER_ROOT@@\AdminCenter (только Administrators и SYSTEM, наследование от H:\ снято выше). Существующие файлы не трогаются (папка — в $keep).
    try:
        print(ps(CASES_DIR_PS % {"r": REMOTE}))
    except Exception as ex:
        print("ШАГ 3б НЕ ПРОШЁЛ: %s" % str(ex)[:600])
        restore_previous(stamp)
        return 2

    step("4. секреты")
    print(ps(r"""
$f='%(f)s'
if (Test-Path $f) { 'есть, не меняю' } else {
  $chars = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_.+'
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $b = New-Object byte[] 32; $rng.GetBytes($b); $pw = -join ($b | %% { $chars[$_ %% $chars.Length] })
  $pw = 'Aa1-' + $pw
  $k = New-Object byte[] 32; $rng.GetBytes($k); $key = -join ($k | %% { $_.ToString('x2') })
  Set-Content -LiteralPath $f -Encoding UTF8 -Value ("# секреты админ-центра (создано %(s)s); не копировать, не печатать`r`nPASSWORD = $pw`r`nTOTP_KEY = $key")
  'создан'
}
# волна А1: пароль логина правок предметов asda_ops (sql/adminc_04_ops.sql) — дописывается один раз
if (-not (Select-String -LiteralPath $f -Pattern '^\s*OPS_PASSWORD\s*=' -Quiet)) {
  $chars = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_.+'
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $b = New-Object byte[] 32; $rng.GetBytes($b); $op = 'Aa1-' + (-join ($b | %% { $chars[$_ %% $chars.Length] }))
  Add-Content -LiteralPath $f -Encoding UTF8 -Value ("OPS_PASSWORD = $op")
  'OPS_PASSWORD добавлен'
}
# волна А2 (мост P127, 18.11.2026): пароль логина моста asda_bridge и ключ подписи команд — дописываются один раз; в GameServer их
# кладёт AstoryServer/Patches/AsdaPatch/tools/deploy_p127.py (ConfigSet\admin_bridge.ini, права Administrators/SYSTEM)
if (-not (Select-String -LiteralPath $f -Pattern '^\s*BRIDGE_PASSWORD\s*=' -Quiet)) {
  $chars = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_.+'
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $b = New-Object byte[] 32; $rng.GetBytes($b); $bp = 'Aa1-' + (-join ($b | %% { $chars[$_ %% $chars.Length] }))
  Add-Content -LiteralPath $f -Encoding UTF8 -Value ("BRIDGE_PASSWORD = $bp")
  'BRIDGE_PASSWORD добавлен'
}
if (-not (Select-String -LiteralPath $f -Pattern '^\s*BRIDGE_HMAC_KEY\s*=' -Quiet)) {
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $k = New-Object byte[] 32; $rng.GetBytes($k); $hk = -join ($k | %% { $_.ToString('x2') })
  Add-Content -LiteralPath $f -Encoding UTF8 -Value ("BRIDGE_HMAC_KEY = $hk")
  'BRIDGE_HMAC_KEY добавлен'
}
# ★ А6.11 (22.11.2026, жалобы игроков): пароль логина бота Discord asda_reports (sql/adminc_23_reports.sql: только EXECUTE adm.Report*) —
#   дописывается один раз; его копия — ОДНОЙ строкой в secrets\reports_bot.ini (бот на ПК читает её по SSH, остальных паролей не видит)
if (-not (Select-String -LiteralPath $f -Pattern '^\s*REPORTS_PASSWORD\s*=' -Quiet)) {
  $chars = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_.+'
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  $b = New-Object byte[] 32; $rng.GetBytes($b); $rp = 'Aa1-' + (-join ($b | %% { $chars[$_ %% $chars.Length] }))
  Add-Content -LiteralPath $f -Encoding UTF8 -Value ("REPORTS_PASSWORD = $rp")
  'REPORTS_PASSWORD добавлен'
}
$rl = Get-Content -LiteralPath $f -Encoding UTF8 | Where-Object { $_ -match '^\s*REPORTS_PASSWORD\s*=' } | Select-Object -First 1
$rb = Join-Path (Split-Path $f) 'reports_bot.ini'
Set-Content -LiteralPath $rb -Encoding UTF8 -Value ("# пароль логина бота Discord asda_reports (только процедуры жалоб adm.Report*); не копировать, не печатать`r`n" + $rl.Trim())
icacls $rb /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' | Out-Null
'reports_bot.ini: одна строка REPORTS_PASSWORD'
icacls (Split-Path $f) /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' | Out-Null
icacls $f /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' | Out-Null
'права: только Administrators и SYSTEM'
""" % {"f": config.SECRET_FILE, "s": stamp}))

    step("4б. сертификат HTTPS")
    have = ps("if ((Test-Path '%s') -and (Test-Path '%s')) { 'есть' } else { 'нет' }" % (config.TLS_CERT, config.TLS_KEY)).strip()
    if have.endswith("есть"):
        print("есть, не меняю")
    else:
        crt, key = make_tls_cert(stamp)
        try:
            with open(crt, "rb") as f, open(PUBLIC_CRT, "wb") as g:   # открытая часть — владельцу на устройства
                g.write(f.read())
            scp(crt, config.TLS_CERT)
            scp(key, config.TLS_KEY)
        finally:
            for f in (crt, key):                       # ключ на ПК не оставляем
                if os.path.exists(f):
                    os.remove(f)
        print(ps(r"icacls '%s' /inheritance:r /grant:r 'Administrators:F' 'SYSTEM:F' | Out-Null; 'создан (10 лет), права ключа: только Administrators и SYSTEM'"
                 % config.TLS_KEY))

    step("4в. папка бэкапов БД панели")
    # ★ А5.7 (21.11.2026): бэкапы пишет SQL Server (служба NT SERVICE\MSSQL$SQLEXPRESS), читает / удаляет ротацией служба панели (SYSTEM);
    #   в файлах данные игроков — пользователям Windows доступа нет. Существующая папка и файлы в ней НЕ удаляются, только права папки.
    print(ps(r"""
$d='%(d)s'
New-Item -ItemType Directory -Force -Path $d | Out-Null
icacls $d /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' '%(svc)s:(OI)(CI)M' /C /Q | Out-Null
if ($LASTEXITCODE) { throw "icacls $d" }
'папка ' + $d + ': права Administrators, SYSTEM, SQL Server (изменение); файлов ' + (Get-ChildItem $d -File).Count
""" % {"d": BACKUP_DIR, "svc": SQL_SVC}))

    step("5. SQL: база, схема, права; проверка прав под asda_admin")
    ok_rights = False
    try:
        out = ps(r"""
$root='%(r)s'
function Sec($file, $key) { foreach ($l in Get-Content -LiteralPath $file -Encoding UTF8) { if ($l -match ('^\s*' + $key + '\s*=\s*(.+)$')) { return $Matches[1].Trim().Trim('"') } } throw "нет $key в $file" }
$env:AdminPw = Sec '%(sf)s' 'PASSWORD'
$env:OpsPw = Sec '%(sf)s' 'OPS_PASSWORD'
$env:BridgePw = Sec '%(sf)s' 'BRIDGE_PASSWORD'
$env:ReportsPw = Sec '%(sf)s' 'REPORTS_PASSWORD'
$env:BridgeDb = 'AsdaAdmin'
function Run($file, $db, [switch]$xi) {
  $ErrorActionPreference = 'Continue'      # PowerShell 5.1: stderr родной программы не должен рвать скрипт до проверки кода
  # Windows-вход Administrator через shared memory — sysadmin (у devgsaccount прав CREATE DATABASE/LOGIN нет)
  $a = @('-S','%(lpc)s','-E','-b','-f','65001','-i',(Join-Path $root ('sql\' + $file)))
  if ($db) { $a += @('-d',$db) }
  if ($xi) { $a += @('-x','-I') }          # ★ А6.12: без подстановки $(…) и с QUOTED_IDENTIFIER ON (как chat_*.sql P129)
  $o = & sqlcmd @a 2>&1; if ($LASTEXITCODE -ne 0) { throw "$file : $o" }; ($o | Out-String).Trim()
}
Run 'adminc_01_database.sql' $null
Run 'adminc_02_schema.sql' 'AsdaAdmin'
Run 'adminc_03_grants.sql' $null
Run 'adminc_13_changeset.sql' 'AsdaAdmin'
Run 'adminc_14_jobs.sql' 'AsdaAdmin'
Run 'adminc_16_dbbackup.sql' 'AsdaAdmin'
Run 'adminc_17_bakdrop.sql' 'AsdaAdmin'
Run 'adminc_18_econ.sql' 'AsdaAdmin'
Run 'adminc_19_acdaily.sql' 'AsdaAdmin'
Run 'adminc_20_names.sql' 'AsdaAdmin'
Run 'adminc_23_reports.sql' 'AsdaAdmin'   # ★ А6.11: жалобы игроков из бота Discord (adm.PlayerReport*, логин asda_reports — только процедуры)
Run 'adminc_26_releases.sql' 'AsdaAdmin' -xi   # ★ А7.1: снимок конвейера выпуска с ПК (adm.ReleasePcStatus; asda_admin — SELECT, INSERT, UPDATE seen)
Run 'adminc_27_crashes.sql' 'AsdaAdmin' -xi   # ★ А7.2: сводка сбоев клиента с ПК (adm.ClientCrash*; asda_admin — SELECT и EXECUTE двух процедур)
Run 'adminc_28_outbox.sql' 'AsdaAdmin' -xi    # ★ А7.4: очередь объявлений в Discord (adm.Outbox; бот asda_reports — 4 процедуры, панель — SELECT и 5 процедур)
Run 'adminc_29_telegram.sql' 'AsdaAdmin' -xi  # ★ А7.5: Telegram владельцу в той же очереди (отправитель asda_reports — 3 процедуры, панель — SELECT и 5 процедур)
Run 'adminc_30_community.sql' 'AsdaAdmin' -xi # ★ А7.6: «Сообщество» — копия реестра бота и очередь команд (бот asda_reports — 3 процедуры, панель — SELECT и 4 процедуры)
Run 'adminc_31_notes.sql' 'AsdaAdmin' -xi     # ★ А7.7: заметки к выпуску — снимок changelog с ПК, публикации (панель — SELECT и 6 процедур, бот — ничего)
Run 'adminc_05_restore.sql' $null
Run 'adminc_06_items.sql' $null
Run 'adminc_08_charcopy.sql' $null
Run 'adminc_09_accounts.sql' $null
Run 'adminc_15_events.sql' $null
Run 'adminc_04_ops.sql' $null
Run 'adminc_21_san.sql' $null        # ★ А6.7: дела san.* — после adminc_04 (снимает запрет EXECUTE на базу joylog1, выдаёт права san)
Run 'adminc_22_gp7adjust.sql' $null  # ★ А6.9: корректировка баланса gp7 (AsdaStoryLogin adm.GP7Adjust, журнал adm.GP7AdjustLog) — после adminc_04 (логин asda_ops)
Run 'adminc_24_chat.sql' $null -xi   # ★ А6.12: журнал чата P129 (joylog1.chat) — после adminc_04 / adminc_21; схемы нет — «пропущено», код 0
Run 'adminc_25_attendance.sql' $null -xi   # ★ А6.10: посещаемость (Joy1 adm.AttendanceAdjust, журнал adm.AttendanceAdjustLog) — после adminc_04 (логин asda_ops)
Run 'adminc_32_botreg.sql' $null -xi   # ★ 25.11: /register бота Discord (AsdaStoryOp adm.BotAccountRegister, привязка adm.BotAccount; бот asda_reports — только EXECUTE) — после adminc_09 и adminc_23
$env:SQLCMDPASSWORD = $env:ReportsPw
$ErrorActionPreference = 'Continue'
$vg = & sqlcmd -S 127.0.0.1,1433 -U asda_reports -d AsdaStoryOp -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_32_botreg_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify botreg: $vg" }
$vgRows = @($vg | ForEach-Object { "$_" } | Where-Object { $_ -match '\|' })
$vgBad = @($vgRows | Where-Object { $p = $_.Split('|'); $p[1].Trim() -ne $p[2].Trim() })
if ($vgRows.Count -ne 16 -or $vgBad.Count) { throw ("verify botreg: строк " + $vgRows.Count + " из 16, расхождения: " + ($vgBad -join '; ')) }
'adminc_32_botreg_verify: 16 из 16'
Run 'adminc_07_bridge.sql' 'AsdaAdmin'
$env:SQLCMDPASSWORD = $env:BridgePw
$ErrorActionPreference = 'Continue'
$vb = & sqlcmd -S 127.0.0.1,1433 -U asda_bridge -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_12_verify_bridge.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify bridge: $vb" }
$env:SQLCMDPASSWORD = $env:ReportsPw
$ErrorActionPreference = 'Continue'
$vr = & sqlcmd -S 127.0.0.1,1433 -U asda_reports -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_23_reports_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify reports: $vr" }
$vx = & sqlcmd -S 127.0.0.1,1433 -U asda_reports -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_28_outbox_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify outbox: $vx" }
$vt = & sqlcmd -S 127.0.0.1,1433 -U asda_reports -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_29_telegram_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify telegram: $vt" }
$vc = & sqlcmd -S 127.0.0.1,1433 -U asda_reports -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_30_community_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify community: $vc" }
$vn = & sqlcmd -S 127.0.0.1,1433 -U asda_reports -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_31_notes_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify notes: $vn" }
$env:SQLCMDPASSWORD = $env:OpsPw
$ErrorActionPreference = 'Continue'
$vo = & sqlcmd -S 127.0.0.1,1433 -U asda_ops -d Joy1 -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_11_verify_ops.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify ops: $vo" }
$env:SQLCMDPASSWORD = $env:AdminPw
$ErrorActionPreference = 'Continue'
$v = & sqlcmd -S 127.0.0.1,1433 -U asda_admin -d AsdaAdmin -b -f 65001 -W -s '|' -h -1 -i (Join-Path $root 'sql\adminc_10_verify.sql') 2>&1
if ($LASTEXITCODE -ne 0) { throw "verify: $v" }
Remove-Item Env:SQLCMDPASSWORD, Env:AdminPw, Env:OpsPw, Env:BridgePw, Env:ReportsPw, Env:BridgeDb
'VERIFY'; $v
'VERIFYOPS'; $vo
'VERIFYBRIDGE'; $vb
'VERIFYREPORTS'; $vr
'VERIFYOUTBOX'; $vx
'VERIFYTG'; $vt
'VERIFYCOMM'; $vc
'VERIFYNOTES'; $vn
""" % {"r": REMOTE, "sf": config.SECRET_FILE, "lpc": SQL_LPC}, timeout=300)
        print(out)
        # ★ А6.12: права на журнал чата — выданы или пропущены (схемы chat P129 ещё нет) — отдельной строкой итога
        print("права журнала чата (adminc_24): %s" % (
            "ПРОПУЩЕНО — схемы chat нет (P129 не выложен), выдаст следующая выкладка панели или deploy_p129.py после chat_01_migrate.sql"
            if "adminc_24: пропущено" in out else "выданы" if "adminc_24: OK" in out else "НЕТ ОТМЕТКИ adminc_24 в выводе"))
        part_admin, rest = out.split("VERIFY", 1)[1].split("VERIFYOPS", 1)
        part_ops, rest = rest.split("VERIFYBRIDGE", 1)
        part_bridge, rest = rest.split("VERIFYREPORTS", 1)     # ★ А6.11: права логина бота жалоб asda_reports (19 проверок, ★ ревизия 67)
        part_reports, rest = rest.split("VERIFYOUTBOX", 1)              # ★ А7.4: тот же логин бота — процедуры очереди Discord (15 проверок)
        part_outbox, rest = rest.split("VERIFYTG", 1)                   # ★ А7.5: тот же логин — отправитель Telegram (17 проверок)
        part_tg, rest = rest.split("VERIFYCOMM", 1)                     # ★ А7.6: тот же логин — «Сообщество» (★ р79 М-3: 36 проверок)
        part_comm, part_notes = rest.split("VERIFYNOTES", 1)            # ★ А7.7: тот же логин — заметок не видит (★ р83: 17 проверок, все 0)
        for who, part, need in (("asda_admin", part_admin, 21), ("asda_ops", part_ops, 21), ("asda_bridge", part_bridge, 15),
                                ("asda_reports", part_reports, 19), ("asda_reports/outbox", part_outbox, 15), ("asda_reports/telegram", part_tg, 17),
                                ("asda_reports/community", part_comm, 36), ("asda_reports/notes", part_notes, 17)):
            rows = [l.split("|") for l in part.strip().splitlines() if l.count("|") == 2]
            bad = [r for r in rows if not r[1].strip().lstrip("-").isdigit() or int(r[1]) != int(r[2])]
            if len(rows) < need or bad:
                print("ПРОВЕРКА ПРАВ %s НЕ ПРОШЛА:" % who, bad or "строк %d" % len(rows))
                raise RuntimeError("проверка прав %s не прошла" % who)
            print("права %s: %d проверок совпали" % (who, len(rows)))
        ok_rights = True
    except Exception as ex:                         # ревизия 28 К-8: служба не должна остаться остановленной
        print("ШАГ 5 НЕ ПРОШЁЛ: %s" % str(ex)[:600])
        restore_previous(stamp)
        return 2

    step("6. брандмауэр")
    print(ps(r"""
cmd /c "netsh advfirewall firewall delete rule name=%(t)s >nul 2>&1"
cmd /c "netsh advfirewall firewall add rule name=%(t)s dir=in action=allow protocol=TCP localport=%(p)d remoteip=any >nul"; if ($LASTEXITCODE) { throw 'netsh add rule' }
'правило: TCP %(p)d с любых адресов (решение владельца 16.11.2026; служба — только HTTPS)'
""" % {"t": TASK, "p": PORT}))

    step("7. задача планировщика и запуск")
    print(ps(r"""
$bat = '%(r)s\run_service.bat'
# Ревизия А0 №5: у schtasks /Create лимит выполнения по умолчанию 72 ч — через трое суток планировщик снял бы службу.
# Register-ScheduledTask: лимит 0 (без предела), перезапуск задачи при сбое, без остановки на батарее.
$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c "' + $bat + '"') -WorkingDirectory '%(r)s'
$trg = New-ScheduledTaskTrigger -AtStartup
$pri = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$set = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName %(t)s -Action $act -Trigger $trg -Principal $pri -Settings $set -Force | Out-Null
Start-ScheduledTask -TaskName %(t)s
$lim = (Get-ScheduledTask -TaskName %(t)s).Settings.ExecutionTimeLimit
if ($lim -ne 'PT0S') { throw "лимит выполнения задачи: $lim" }
'задача создана (лимит выполнения: нет) и запущена'
""" % {"r": REMOTE, "t": TASK}))

    step("8. проверка снаружи")
    code, text = after_start(stamp)
    print(text)
    if code == 0:
        for a in (config.SERVER_VPN_IP, config.SERVER_LAN_IP, config.SERVER_WAN_IP):
            print("Панель: https://%s:%d/" % (a, PORT))
        print("(внешний адрес — только если на роутере проброшен TCP %d на %s)" % (PORT, config.SERVER_LAN_IP))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
