# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""config.py — настройки админ-центра. 16.11.2026.

Источник — файл config.ini рядом с asda_admin.py (необязателен) поверх умолчаний ниже. Секретов здесь нет:
пароль логина БД `asda_admin` лежит только на сервере (SECRET_FILE) и читается локально (служба на сервере)
или по SSH (консоль на ПК владельца), как PasswordSQL.txt у AstoryServer/Tools/Anticheat/db_connect.py.

Где работаем — определяется по имени машины: @@ASTORY_SERVER_HOSTNAME@@ = на сервере (SQL и процессы — локально),
иначе = на ПК (SQL — по адресу VPN, процессы — по SSH). Побочных эффектов при импорте нет.
"""
import configparser
import os
import socket

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # корень AdminCenter
DATA_DIR = os.path.join(HERE, "data")                                 # данные справочников (build_item_index.py)
WEB_DIR = os.path.join(HERE, "web")                                   # статика панели
CONFIG_INI = os.path.join(HERE, "config.ini")                         # необязательные переопределения

SERVER_HOSTNAME = "@@ASTORY_SERVER_HOSTNAME@@"                                            # имя машины dev-сервера
SERVER_VPN_IP = "@@ASTORY_SERVER_VPN_IP@@"                                      # адрес сервера в сети VPN (Tailscale)
SERVER_LAN_IP = "@@ASTORY_SERVER_LAN_IP@@"                                       # адрес сервера в домашней сети
SERVER_WAN_IP = "@@ASTORY_SERVER_WAN_IP@@"                                     # внешний адрес (через роутер; проброс порта — роутер владельца)
SSH_HOST = "Administrator@" + SERVER_VPN_IP                           # SSH с ПК владельца
SSH_KEY = os.path.join(os.environ.get("USERPROFILE", ""), ".ssh", "@@ASTORY_SSH_KEY_NAME@@")   # ключ SSH (как у srv_mirror)
STACK_ROOT = r"@@ASTORY_SERVER_ROOT@@\Working_ASDA\v2"                               # корень игровой стойки на сервере
SERVICE_ROOT = r"@@ASTORY_SERVER_ROOT@@\AdminCenter"                                 # куда выкладывается служба на сервере
SECRET_FILE = SERVICE_ROOT + r"\secrets\asda_admin.ini"               # пароль логина БД asda_admin (только на сервере)
TLS_CERT = SERVICE_ROOT + r"\secrets\tls.crt"                         # сертификат HTTPS (самоподписанный, deploy шаг 4)
TLS_KEY = SERVICE_ROOT + r"\secrets\tls.key"                          # его закрытый ключ (права — как у секретов)
EAC_STATUS_SECRET = SERVICE_ROOT + r"\secrets\eac_status.key"         # ★ А6.8: копия секрета точки статуса AsdaEacServer (кладёт выкладчик EacServer)



class Config:
    """Действующие настройки (умолчания + config.ini)."""

    def __init__(self, path=CONFIG_INI):
        self.on_server = socket.gethostname().upper() == SERVER_HOSTNAME       # служба запущена на самом сервере
        self.sql_server = "127.0.0.1,1433" if self.on_server else SERVER_VPN_IP + ",1433"   # адрес SQL
        self.sql_driver = "ODBC Driver 17 for SQL Server"                      # драйвер есть и на ПК, и на сервере
        self.sql_login = "asda_admin"                                          # узкий логин инструмента (не devgsaccount)
        self.admin_db = "AsdaAdmin"                                            # своя база: пользователи, сессии, журнал
        # Владелец 16.11.2026: «панель на всех интерфейсах, не только Tailscale» → на сервере 0.0.0.0 + HTTPS
        # (вне VPN трафик ничем не шифруется — пароль и cookie шли бы открытым текстом); на ПК — только локально.
        self.bind_host = "0.0.0.0" if self.on_server else "127.0.0.1"
        self.bind_port = 17890                                                 # порт панели (8800–8999 на ПК зарезервированы Windows; 15xxx — стойка)
        self.tls = self.on_server                                              # HTTPS (на сервере обязателен)
        self.tls_cert = TLS_CERT
        self.tls_key = TLS_KEY
        # Имена/адреса, которые допустимы в заголовке Host (защита от DNS-rebinding): все адреса сервера + локальные.
        # Дополнить (домен и т.п.) — ключом public_hosts в config.ini, через запятую.
        self.public_hosts = ",".join([SERVER_VPN_IP, SERVER_LAN_IP, SERVER_WAN_IP, SERVER_HOSTNAME.lower(),
                                      "localhost", "127.0.0.1"])
        self.session_hours = 12                                                # срок сессии без действий
        self.session_abs_hours = 72                                            # абсолютный предел сессии
        self.login_fail_limit = 5                                              # неудач подряд до замка учётки панели
        self.login_lock_minutes = 15                                           # длительность замка
        self.feed_limit = 300                                                  # строк в ленте журналов за запрос
        self.ssh_timeout_s = 30                                                # предел одной команды по SSH
        self.secret_file = SECRET_FILE
        # ★ 19.11 (А3, ревизия 31 К-2): ТЕКУЩИЙ changelog порта (памятка проекта changelog-current-file) — одно место; сменился —
        #   поправить здесь или ключом changelog в config.ini. Панель отказывает в записи, если есть более новый CHANGELOG_<дата>.md.
        self.changelog = "CHANGELOG_2026-11-16.md"
        # ★ 21.11 (А5.2, ревизия 42 Н-4): служебные игровые учётки ВЛАДЕЛЬЦА (через запятую) — от их персонажей монстров вызывает
        #   только владелец (живой самотест работает на учётках 1 и 2 — «учётки владельца»)
        self.owner_game_accounts = "1,2"
        # ★ 22.11 (А6.8, вторая часть): точка статуса EAC службы AsdaEacServer (AstoryServer/EacServer/src/AdminStatus.h) — только 127.0.0.1
        #   этой машины, заголовок X-Asda-Key = первая строка eac_status_secret (на ПК не используется: точки там нет)
        self.eac_status_port = 8447
        self.eac_status_secret = EAC_STATUS_SECRET
        self._load(path)

    def _load(self, path):
        """Переопределения из [admin] config.ini: ключ = имя атрибута, тип берётся у умолчания."""
        if not os.path.exists(path):
            return
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        if not cp.has_section("admin"):
            return
        for k, v in cp.items("admin"):
            if not hasattr(self, k) or k.startswith("_"):
                continue
            cur = getattr(self, k)
            if isinstance(cur, bool):
                setattr(self, k, v.strip().lower() in ("1", "true", "yes", "да"))
            elif isinstance(cur, int):
                setattr(self, k, int(v))
            else:
                setattr(self, k, v.strip())


_CFG = None   # кэш настроек на процесс

# ★ ревизия 56 С-1 (22.11.2026): код порта вне дерева службы. На сервере PORT = dirname(корня службы) = @@ASTORY_SERVER_ROOT_ESC@@ (служба —
#   @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter, один уровень вверх), и любой путь PORT\\… (AstoryClient, AstoryServer, …) — папка, которую может
#   создать локальный пользователь без прав администратора (ACL корня диска: Users — AppendData / CreateFiles); служба работает от SYSTEM. Поэтому импорт / запуск кода из таких путей —
#   только на ПК; на сервере — отказ PortCodeError (чужой код службы — только копии ext/ со сверкой манифеста, domains/acsrc).
PC_ONLY = "код порта (исходники ПК вне дерева службы) на сервере не исполняется — эта часть работает только на ПК владельца"


class PortCodeError(ImportError):
    """Попытка исполнить код порта вне дерева службы на сервере. Наследник ImportError: вызывающие, которые на сервере уже ждали ImportError
    (исходников порта там нет — работа по снимку: cs_kinds equipshop / honorshop / questtables), ведут себя как прежде."""


def port_code(path):
    """Путь к коду порта → тот же путь на ПК; на сервере — PortCodeError (ревизия 56 С-1)."""
    if get().on_server:
        raise PortCodeError(PC_ONLY)
    return path


def get():
    """Настройки процесса (читаются один раз)."""
    global _CFG
    if _CFG is None:
        _CFG = Config()
    return _CFG
