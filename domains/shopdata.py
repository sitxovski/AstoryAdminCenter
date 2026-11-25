# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""shopdata.py — ДВИЖОК наборов изменений данных игры (волна А3 «Данные: магазины», 19.11.2026; с А4.0 — общий для всех областей).

Имя модуля историческое (А3). С А4.0 (19.11.2026, разбор Reports/admin_center/research_a4_data.md §0, §5) специфика каждой
ОБЛАСТИ данных — в реестре видов domains/cs_kinds/<область>.py (магазины — cs_kinds/shops.py; витрина 6800 — equipshop.py; магазин
чести — honorshop.py; парикмахерская — hairshop.py). Здесь — общее:
  * снимок стойки (md5 + сырые байты таблиц всех копий; семьи GS и NpcServer, база КАЖДОЙ копии — своя, у Indun отличия сохраняются),
  * рабочие копии таблиц в памяти (неизменённые строки — байт в байт), применение позиций через реестр видов, общие проверки
    («все копии семьи меняются», политика баз: same / per_copy / own, паритет Ch2), итог «было → станет»,
  * клиентские таблицы порта (на ПК — с диска, на сервере — снимок data/ref/shop_client.json, его кладёт выкладка),
  * план клиентской половины; ★ таблицы ItemDB (item_list, packagetable, booster_list, hairtable) — правка пишется в ВЕДОМОСТИ
    RawAssets/ItemDB/_value_overlay | _tail_append (правило itemdb-ledger-overlays: перегенерация decode_item_db.py не сотрёт правку),
    CSV порта правится той же правкой, и доказывается, что перегенерация (декод архива + ведомости + item_dedup) даёт ровно план,
  * общий механизм «сильной правки баланса» (значение меняется больше чем в 2 раза; стопка/тип) — двойное подтверждение при
    утверждении с показом «сколько на руках у игроков» (Joy1.dbo.Item) — для областей с BALANCE_GATE (А4; магазины А3 — только
    сведения, поведение А3 не меняется),
  * расхождения сервер/клиент (разделы областей).
Побочных эффектов при импорте нет.
"""
import contextlib
import csv
import datetime
import hashlib
import importlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading

from core import config, hostshell
from core.ops import OpRefused
from domains import refdata, srvtables

ROOT = config.HERE                                                        # AstoryAdminCenter
PORT = os.path.dirname(ROOT)                             # папка с клонами (= @@ASTORY_DEV_ROOT@@)
AREA = os.path.dirname(PORT)                                              # родитель папки клонов — база относительных путей показа (rel_area)
UPROJ = os.path.join(PORT, "AstoryClient")
UE_TOOLS = os.path.join(UPROJ, "Tools")
ITEMDB = os.path.join(UPROJ, "RawAssets", "Data", "ItemDB")
NPC_DIR = os.path.join(UPROJ, "RawAssets", "Data", "NPC")
HIDDEN_CSV = os.path.join(UE_TOOLS, "data", "npc_shop_hidden.csv")
PANEL_TAIL = os.path.join(NPC_DIR, "PremiumShopBin_tail_panel.json")   # ведомость хвоста 6000 ЭТОГО генератора (панели)
SRV_TOOLS = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "tools")
DEPLOY_SCRIPT = "deploy_changeset.py"                                    # обёртка deploy_premium_boxes (манифест из окружения)
CS_DIR = os.path.join(config.DATA_DIR, "changesets")                     # рабочие файлы наборов на ПК (srv_out, манифест, журналы)
BACKUP_DIR = os.path.join(PORT, "_backup")                                # бэкапы клиентской половины: @@ASTORY_DEV_ROOT@@\_backup\<дата>_cs<№> (★ 25.11, М-9)
CACHE = os.path.join(config.DATA_DIR, "cs_cache")                        # снимки таблиц стойки на ПК (имя = md5)
SNAPSHOT = os.path.join(config.DATA_DIR, "ref", "shop_client.json")      # снимок клиентских таблиц (строит ПК, кладёт выкладка)
RELEASES_LOG = os.path.join(PORT, "Releases", "releases.log")
GIFT_CHECK = os.path.join(PORT, "Reports", "premium_circle_bike", "gift_check.py")
GW_SERVER_JS = os.path.join(PORT, "AstoryServer", "Patches", "Gp7Gateway", "server.js")
# ★ А4.0: ведомости ItemDB (правило itemdb-ledger-overlays) и генератор CSV (на уровень выше порта: AstoryClient/Tools/ItemDB)
LEDGER_ROOT = os.path.join(UPROJ, "RawAssets", "ItemDB")                 # _value_overlay/<т>.csv, _tail_append/<т>.csv
DECODER_DIR = os.path.join(PORT, "AstoryClient", "Tools", "ItemDB")                      # decode_item_db.py (реестр раскладок + ведомости)
LEDGER_TABLES = {"item_list": "item_list.bin", "packagetable": "packagetable.bin", "booster_list": "booster_list.bin",
                 "hairtable": "hairtable.bin",
                 "title_list": "title_list.bin",                          # CSV порта → запись архива Bin.bbz (★ А4.2: RU званий)
                 "sowell_list": "sowell_list.bin",                        # ★ А4.4: уровень самоцвета (value_ledger реестра с 20.11)
                 # ★ А4.7: навыки (ключ = имя записи архива: ведомость декодера — _value_overlay/skill_info.sif.csv) и пороги опыта
                 "skill_info.sif": "skill_info.sif", "charexp": "charexp.bin"}
LEDGER_COLS = ["row", "column", "was", "now", "source", "reason"]        # = decode_item_db.VALUE_LEDGER_COLS

GS = list(srvtables.STACK_GS)                                            # GameServer, Indun_GameServer, Ch2_GameServer
PREMIUM_MAP = r"gp7-server\premium_item_map.json"
ITEM_FIRST = 20551                    # sub_532A90: item_list с 20551
PRICE_OFF = 0xA4                      # item_list.Price в записи DataHex (сверено: 59 390 из 59 390)
PARAMS_MAX = 200000                   # символов JSON позиции (пул гачи 3000 строк ≈ 40 тыс.; столбец NVARCHAR(MAX), ревизия 30 М-2)
BALANCE_RATIO = 2.0                   # решение владельца 19.11: значение меняется больше чем в 2 раза → двойное подтверждение

# Заполняются областями реестра (конец модуля); ОДИН объект на процесс (самотесты подменяют содержимое на месте)
CLIENT_FILES, DT, IMPORTERS, KINDS = {}, {}, {}, {}
AREAS, AREA_OF, SRV_POLICY = [], {}, {}
SRV_FAMILY = {}                       # ★ А4.8: подпуть таблицы → семья копий из SRV_FILES (GS / NPC / GSF — только копии поля)


def rel_area(path):
    """Путь от @@ASTORY_DEV_ROOT_ESC@@ (для показа и журнала)."""
    try:
        return os.path.relpath(path, AREA).replace("\\", "/")
    except ValueError:                    # другой диск (временная папка самотеста) — путь целиком
        return path.replace("\\", "/")


def area_rel(path):
    """Путь от корня проекта (AREA) для раскладки бэкапа; другой диск — путь без буквы диска."""
    try:
        return os.path.relpath(path, AREA)
    except ValueError:
        return os.path.splitdrive(os.path.abspath(path))[1].lstrip("\\/")


def spd_dir():
    """Каталог лавок NPC клиента: <Donors>/AsdaChroniclesInterlude_MINE/Data/NPC/Shop (asda_paths.DATA)."""
    return os.path.join(data_dir(), "NPC", "Shop")


def data_dir():
    """Каталог Data клиента-донора _MINE (asda_paths.DATA): исходники импортёров витрин (.spd, .she, Honor_price_table.bin)."""
    config.port_code(UE_TOOLS)                  # ★ ревизия 56 С-1: только ПК
    if UE_TOOLS not in sys.path:
        sys.path.insert(0, UE_TOOLS)
    import asda_paths as _P                     # noqa: E402 — модуль путей проекта без побочных эффектов
    return _P.DATA


def md5b(b):
    return hashlib.md5(b).hexdigest()


def md5f(path):
    with open(path, "rb") as f:
        return md5b(f.read())


class _LayoutCopy:
    """★ А4.3 (20.11.2026, найдено проверкой службы на сервере): в пакете службы нет AstoryServer/…/stack_layout.py — оценка набора с
    правкой таблиц (family / folders / паритет Ch2) падала ModuleNotFoundError. Копия нужных полей; самотест сверяет её с настоящим
    stack_layout (расхождение — ошибка самотеста)."""
    GS_FOLDERS = ["GameServer", "Indun_GameServer", "Ch2_GameServer"]
    NPC_FOLDERS = ["NpcServer", "Indun_NpcServer", "Ch2_NpcServer"]
    RELAY_FOLDERS = ["RelayServer", "Indun_RelayServer", "Ch2_RelayServer"]          # ★ А5.5: srvdbpatch.ini (SrvDbPatch)
    TWINS = {"Ch2_GameServer": "GameServer", "Ch2_NpcServer": "NpcServer", "Ch2_RelayServer": "RelayServer"}


# ★ А5.5 (21.11.2026): семьи копий ini наших DLL (domains/patchcfg_src.DLLS): GSP / NPCP — все GameServer / NpcServer, правка ПАРАМИ
#   «поле = Ch2» (Indun — своей базой, можно отдельно); LM — LoginManager; DBM — DBManager; SDB — RelayServer ×3 + ItemRelayServer +
#   OperationServer (SrvDbPatch, srvdbpatch.ini). Пара «поле — Ch2» — stack_layout.TWINS.
ONE_FAMILIES = {"LM": ["LoginManager"], "DBM": ["DBManager"]}
SDB_EXTRA = ["ItemRelayServer", "OperationServer"]
PAIR_FAMILIES = {"GSP": "GS", "NPCP": "NPC"}


def _layout():
    if config.get().on_server:            # ★ ревизия 56 С-1: на сервере H:\\Server\\… вне дерева службы — только копия полей (самотест сверяет)
        return _LayoutCopy
    if SRV_TOOLS not in sys.path:
        sys.path.insert(0, SRV_TOOLS)
    try:
        import stack_layout               # noqa: E402 — единый состав стойки, без побочных эффектов
    except ImportError:                   # служба на сервере: выкладчиков стойки в пакете нет
        return _LayoutCopy
    return stack_layout


def family(folder):
    """Семья копии: GS | NPC (stack_layout); ★ А5.5: LM / DBM / SDB — копии процессов с ini наших DLL вне GameServer / NpcServer."""
    lay = _layout()
    if folder in lay.NPC_FOLDERS:
        return "NPC"
    for fam, fl in ONE_FAMILIES.items():
        if folder in fl:
            return fam
    if folder in getattr(lay, "RELAY_FOLDERS", []) or folder in SDB_EXTRA:
        return "SDB"
    return "GS"


def folders(fam):
    """Копии семьи: GS — все GameServer, NPC — все NpcServer, ★ А4.8 GSF — копии GameServer ПОЛЯ (GameServer и его пара Ch2 по
    stack_layout.TWINS): таблица, которой у Indun нет (MapData_Info\\OpenMapInfo.ini — Indun_GameServer работает без неё, byte_5F5EF6 = 0).
    ★ А5.5: GSP / NPCP — те же копии, что GS / NPC (правка парами, см. pair_ok); LM, DBM — одна копия; SDB — Relay ×3 + ItemRelay + Operation."""
    if fam == "GSF":
        lay = _layout()
        return [g for g in GS if g == GS[0] or lay.TWINS.get(g) == GS[0]]
    fam = PAIR_FAMILIES.get(fam, fam)
    if fam in ONE_FAMILIES:
        return list(ONE_FAMILIES[fam])
    if fam == "SDB":
        return list(getattr(_layout(), "RELAY_FOLDERS", _LayoutCopy.RELAY_FOLDERS)) + list(SDB_EXTRA)
    return list(_layout().NPC_FOLDERS) if fam == "NPC" else list(GS)


def pair_ok(fam, touched, name=None):
    """★ А5.5: для семьи «парами» (GSP / NPCP) набор копий годен, если у каждой пары «поле — Ch2» правятся обе или ни одной (паритет Ch2,
    restart_stack код 6); Indun — отдельно. → None | текст отказа (★ ревизия 45 В-1: с name — полный текст «<таблица>: … — пересоберите
    набор»)."""
    lay = _layout()
    allf = set(folders(fam))
    if not touched or not set(touched) <= allf:
        a = (", ".join(sorted(touched)), fam, ", ".join(sorted(allf)))
        return ("%s: копии %s — не из семьи %s (%s) — пересоберите набор" % ((name,) + a)) if name else "копии %s — не из семьи %s (%s)" % a
    for twin, field in lay.TWINS.items():
        if twin in allf and ((twin in touched) != (field in touched)):
            a = (twin if twin in touched else field, field if twin in touched else twin)
            return (("%s: правка %s без пары %s (паритет Ch2 — restart_stack код 6) — пересоберите набор" % ((name,) + a)) if name
                    else "правка %s без пары %s (паритет Ch2 — restart_stack код 6)" % a)
    return None


def srv_family_of(folder, sub):
    """★ А5.5: семья таблицы с учётом того, что один подпуть бывает у разных процессов (ConfigSet\\patches.ini — у GameServer, NpcServer и
    LoginManager): сначала ключ (семья копии, подпуть), затем подпуть (как до А5.5), затем семья копии."""
    base = family(folder)
    return SRV_FAMILY.get((base, sub)) or SRV_FAMILY.get(sub) or base


def srv_policy_of(folder, sub):
    base = family(folder)
    return SRV_POLICY.get((base, sub)) or SRV_POLICY.get(sub, "same")


def rel_of(folder, table):
    """Путь от v2: таблица ItemTable_Info (имя без «\\») или подпуть копии."""
    return folder + "\\" + (table if "\\" in table else "ItemTable_Info\\" + table)


def split_rel(rel):
    """Путь от v2 → (копия, таблица): ItemTable_Info\\<имя> → имя (как в А3), иначе подпуть."""
    folder, sub = rel.split("\\", 1)
    return folder, (sub[len("ItemTable_Info\\"):] if sub.startswith("ItemTable_Info\\") and sub.count("\\") == 1 else sub)


# =====================================================================================================================
# СЕРВЕР: снимок таблиц стойки
# =====================================================================================================================
def srv_rels(tables=None):
    """Таблицы магазинов во всех GS (по умолчанию — 6 × 3, как в А3)."""
    return [g + "\\ItemTable_Info\\" + t for g in GS for t in (tables or SRV_TABLES)]


def srv_rels_for(areas):
    """Все пути таблиц областей (семья × подпуть)."""
    out = []
    for a in areas:
        for fam, sub, _pol in getattr(a, "SRV_FILES", ()):
            for f in folders(fam):
                r = f + "\\" + sub
                if r not in out:
                    out.append(r)
    return out


def live_md5(rels):
    """{путь от v2: md5 | 'none'} — одним вызовом (на сервере — с диска, на ПК — PowerShell по SSH)."""
    cfg = config.get()
    if cfg.on_server:
        out = {}
        for r in rels:
            p = config.STACK_ROOT + "\\" + r
            out[r] = md5f(p) if os.path.isfile(p) else "none"
        return out
    lst = ",".join("'%s'" % r.replace("'", "''") for r in rels)
    txt = hostshell.powershell(
        "$v2='%s'; foreach($r in @(%s)){ $p=Join-Path $v2 $r; if(Test-Path -LiteralPath $p){ $h=(Get-FileHash -LiteralPath $p "
        "-Algorithm MD5).Hash.ToLower() } else { $h='none' }; Write-Output ($r+'|'+$h) }" % (config.STACK_ROOT, lst), timeout=120)
    out = {}
    for ln in txt.splitlines():
        if "|" in ln:
            r, h = ln.strip().rsplit("|", 1)
            out[r] = h
    miss = [r for r in rels if r not in out]
    if miss:
        raise hostshell.HostError("md5 таблиц стойки не получены: %s" % ", ".join(miss[:3]))
    return out


def _fetch(rel, want):
    """Байты файла стойки с проверкой md5 (на ПК — scp в кэш по md5)."""
    cfg = config.get()
    if cfg.on_server:
        with open(config.STACK_ROOT + "\\" + rel, "rb") as f:
            b = f.read()
    else:
        os.makedirs(CACHE, exist_ok=True)
        dst = os.path.join(CACHE, want + ".bin")
        if not (os.path.isfile(dst) and md5f(dst) == want):
            exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "scp.exe")
            r = subprocess.run([exe if os.path.exists(exe) else "scp", "-q", "-i", config.SSH_KEY, "-o", "BatchMode=yes",
                                "-o", "ConnectTimeout=15", "%s:%s/%s" % (config.SSH_HOST, config.STACK_ROOT.replace("\\", "/"),
                                                                        rel.replace("\\", "/")), dst + ".part"],
                               capture_output=True, timeout=600)
            if r.returncode != 0:
                raise hostshell.HostError("таблица стойки %s не скопирована: %s" % (rel, r.stderr.decode("utf-8", "replace")[:200]))
            os.replace(dst + ".part", dst)
        with open(dst, "rb") as f:
            b = f.read()
    if md5b(b) != want:
        raise hostshell.HostError("таблица стойки %s изменилась во время чтения (md5 %s ≠ %s) — повторите" % (rel, md5b(b), want))
    return b


class Snap:
    """Снимок таблиц всех копий: md5 и байты (байты — по запросу; одинаковые копии читаются один раз)."""

    def __init__(self, md5=None):
        self.md5 = md5 or live_md5(srv_rels())
        self._b = {}

    def extend(self, rels):
        """★ А4.0: дочитать md5 таблиц других областей (магазинный снимок — прежние 18 файлов)."""
        need = [r for r in rels if r not in self.md5]
        if need:
            self.md5.update(live_md5(need))

    def raw(self, rel):
        h = self.md5.get(rel)
        if not h or h == "none":
            raise OpRefused("на стойке нет файла %s" % rel)
        if h not in self._b:
            self._b[h] = _fetch(rel, h)
        return self._b[h]


def _split(raw):
    sep = b"\r\n" if b"\r\n" in raw else b"\n"
    return raw.split(sep), sep


def _f(line):
    """Поля строки таблицы (разделитель TAB, как у загрузчиков и asda_give)."""
    return [x.strip() for x in line.decode("latin-1").split("\t")]


def _int(s, d=0):
    m = re.match(r"\s*([+-]?\d+)", s or "")
    return int(m.group(1)) if m else d


def set_token(field, val):
    """Число в поле строки таблицы (байты) — с прежними пробелами вокруг (как k_price А3)."""
    return re.sub(rb"[+-]?\d+", str(val).encode("ascii"), field, count=1)


class Table:
    """Строки одной таблицы одной копии для правки на месте (неизменённые строки остаются байт в байт)."""

    def __init__(self, rel, raw):
        self.rel, self.base_md5 = rel, md5b(raw)
        self.lines, self.sep = _split(raw)
        self.changed = {}                         # номер строки → прежние байты
        self._idx = None

    def index(self):
        """{первое поле (int): номер строки} для строк тела."""
        if self._idx is None:
            self._idx = {}
            for i, ln in enumerate(self.lines[1:], 1):
                t = ln.split(b"\t", 1)[0].strip()
                if t.lstrip(b"-").isdigit():
                    self._idx.setdefault(int(t), i)
        return self._idx

    def set_line(self, i, new):
        if i not in self.changed:
            self.changed[i] = self.lines[i]
        self.lines[i] = new

    def data(self):
        return self.sep.join(self.lines)

    def diff(self, limit=40):
        """[(номер строки, было, стало)] — по изменённым строкам (у SellItemTable — вся правка по смыслу)."""
        out = []
        for i in sorted(self.changed):
            old = self.changed[i].decode("latin-1")
            new = self.lines[i].decode("latin-1") if i < len(self.lines) else ""
            if old != new:
                out.append([i + 1, old[:300], new[:300]])
        return out[:limit]


def record_line(t, k, per_record):
    """★ ревизия 33 К-4: строка k-й ЗАПИСИ таблицы «число N, затем N записей потоком слов» — как читает сервер (по порядку, не по
    значению первого слова). Проверка построчности: слов ровно 1 + per_record·N и в каждой непустой строке тела per_record слов;
    иначе — None (порядок слов сервера и строк файла не совпадают — правка не делается)."""
    n = _int(t.lines[0].decode("latin-1"))
    body = [i for i in range(1, len(t.lines)) if t.lines[i].strip()]
    if n < 0 or len(body) < n or any(len(t.lines[i].split()) != per_record for i in body[:n]):
        return None
    if len(b" ".join(t.lines).split()) != 1 + per_record * n:
        return None
    return body[k] if 0 <= k < n else -1


class SellTable(Table):
    """SellItemTable: шапка «макс<TAB>число», код на строку. Правка: добавить в конец / убрать строку; шапка — пересчёт."""

    def __init__(self, rel, raw):
        Table.__init__(self, rel, raw)
        head = self.lines[0].split()
        self.head_max, self.head_cnt = int(head[0]), int(head[1])
        self.tail = b""
        while self.lines and not self.lines[-1].strip():
            self.lines.pop()
            self.tail = self.sep
        self.codes = [int(x) for x in self.lines[1:] if x.strip()]
        self.orig = list(self.codes)
        self.orig_head = (self.head_max, self.head_cnt)
        self.added, self.removed = [], []

    def has(self, code):
        return code in self.codes

    def allow(self, code):
        if code in self.codes:
            return False
        self.codes.append(code)
        self.added.append(code)
        self.head_max = max(self.head_max, code)
        return True

    def deny(self, code):
        if code not in self.codes:
            return False
        self.codes = [c for c in self.codes if c != code]
        self.removed.append(code)
        return True

    def data(self):
        body = [("%d\t%d" % (self.head_max, len(self.codes))).encode("ascii")] + [str(c).encode("ascii") for c in self.codes]
        if (self.head_max, len(self.codes)) == self.orig_head and self.codes == self.orig:
            return Table.data(self) + self.tail      # без правок — исходные байты
        return self.sep.join(body) + self.sep

    def diff(self, limit=40):
        out = []
        if (self.head_max, len(self.codes)) != self.orig_head:
            out.append([1, "%d\t%d" % self.orig_head, "%d\t%d" % (self.head_max, len(self.codes))])
        out += [["+", "", str(c)] for c in self.added] + [["-", str(c), ""] for c in self.removed]
        return out[:limit]


class GachaPool(Table):
    """PrimiumGaChaTable: строки «индекс слот код кол-во»; пул слота заменяется целиком, индексы — заново строго +1 от 0."""

    def __init__(self, rel, raw):
        Table.__init__(self, rel, raw)
        self.rows = []
        for ln in self.lines[1:]:
            t = ln.split()
            if len(t) >= 4:
                self.rows.append([_int(t[1].decode()), _int(t[2].decode()), _int(t[3].decode())])
        self.orig_rows = [list(r) for r in self.rows]
        self.orig_count = _int(self.lines[0].decode("latin-1"))
        self.replaced = {}

    def slot_rows(self, slot):
        return [[c, q] for s, c, q in self.rows if s == slot]

    def replace(self, slot, rows):
        first = next((i for i, r in enumerate(self.rows) if r[0] == slot), None)
        keep = [r for r in self.rows if r[0] != slot]
        new = [[slot, c, q] for c, q in rows]
        if first is None:
            self.rows = keep + new
        else:
            before = sum(1 for r in self.rows[:first] if r[0] != slot)
            self.rows = keep[:before] + new + keep[before:]
        self.replaced[slot] = (len([1 for r in self.orig_rows if r[0] == slot]), len(rows))

    def data(self):
        if self.rows == self.orig_rows:
            return Table.data(self)
        body = [str(len(self.rows)).encode("ascii")] + [("%d\t%d\t%d\t%d" % (i, s, c, q)).encode("ascii")
                                                         for i, (s, c, q) in enumerate(self.rows)]
        return self.sep.join(body) + self.sep

    def diff(self, limit=40):
        out = []
        if len(self.rows) != self.orig_count:
            out.append([1, str(self.orig_count), str(len(self.rows))])
        for s, (a, b) in sorted(self.replaced.items()):
            out.append(["слот %d" % s, "строк %d" % a, "строк %d" % b])
        return out[:limit]


class BinTable:
    """★ А4.3 (20.11.2026): двоичная таблица стойки (Monster.ai 479 б × N, MiningItemTable\\*.mng 1402 б × N, WorldDropItem.itm
    162 б × N) — правка на месте по смещению, размер не меняется (вставок нет). Неизменённые байты — как были. diff — по записям
    смысла, которые сообщает область (note), иначе — по изменённым байтам."""

    def __init__(self, rel, raw):
        self.rel, self.base_md5 = rel, md5b(raw)
        self.orig = bytes(raw)
        self.buf = bytearray(raw)
        self.changed = {}
        self.notes = []

    def put(self, off, fmt, *vals):
        """struct.pack_into на месте; длина файла не меняется (выход за конец — отказ)."""
        n = struct.calcsize(fmt)
        if off < 0 or off + n > len(self.buf):
            raise OpRefused("%s: запись за концом файла (+%d, %d б) — правка не делается" % (self.rel, off, n))
        self.changed.setdefault(off, self.orig[off:off + n])
        struct.pack_into(fmt, self.buf, off, *vals)

    def get(self, off, fmt):
        return struct.unpack_from(fmt, self.buf, off)

    def note(self, where, old, new):
        self.notes.append([where, str(old)[:300], str(new)[:300]])

    def data(self):
        return bytes(self.buf)

    def diff(self, limit=40):
        if self.notes:
            return self.notes[:limit]
        out = []
        for i, (a, b) in enumerate(zip(self.orig, self.buf)):
            if a != b:
                out.append(["+%d" % i, "%02x" % a, "%02x" % b])
        return out[:limit]


BIN_EXT = (".ai", ".mng", ".itm",       # ★ А4.3: двоичные таблицы NpcServer / GameServer — BinTable
           ".sif", ".spt")              # ★ А4.7: SkillInfo.sif (209 б × N), SkillPointTable.spt (14 б × N)


class SrvState:
    """Рабочие копии таблиц всех копий (ленивая загрузка из Snap). get(копия, таблица): таблица ItemTable_Info — по имени
    (как в А3), иначе — подпуть копии (NpcServer: «Monster\\Monster.ai» и т. п.)."""

    KIND = {"SellItemTable.txt": SellTable, "PrimiumGaChaTable.txt": GachaPool}

    def __init__(self, snap):
        self.snap = snap
        self.t = {}

    def get(self, gs, name):
        rel = rel_of(gs, name)
        if rel not in self.t:
            cls = BinTable if name.lower().endswith(BIN_EXT) else self.KIND.get(name, Table)
            self.t[rel] = cls(rel, self.snap.raw(rel))
        return self.t[rel]

    def touched(self):
        return {rel: t for rel, t in self.t.items() if t.data() != self.snap.raw(rel)}


# =====================================================================================================================
# КЛИЕНТ: таблицы порта (ПК) или снимок (сервер)
# =====================================================================================================================
def _read_csv(path):
    csv.field_size_limit(1 << 30)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _hex_price(h, off=PRICE_OFF):
    try:
        b = bytes.fromhex(h)
        return struct.unpack_from("<i", b, off)[0] if len(b) >= off + 4 else None
    except ValueError:
        return None


def client_sources_present():
    """Есть ли на этом ПК клиентские таблицы (AstoryClient/RawAssets: item_list.csv). На публичном клоне AstoryClient папки RawAssets
    нет — снимок не строится, выкладка идёт без него, а разделы данных клиента честно отвечают «снимок не собран» (Client.load)."""
    return os.path.isfile(CLIENT_FILES.get("item_list") or os.path.join(ITEMDB, "item_list.csv"))


def build_client_snapshot():
    """Снимок клиентских таблиц порта для службы на сервере (её диск не видит RawAssets) → dict. Только ПК."""
    md5 = {k: (md5f(p) if os.path.isfile(p) else "none") for k, p in CLIENT_FILES.items()}
    snap = {"built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "md5": md5}
    for a in AREAS:
        a.snapshot(snap)
    return snap


_cli_lock = threading.Lock()
_cli_cache = {}


class Client:
    """Клиентские таблицы: на ПК — живые файлы порта (source = port), на сервере — снимок выкладки (source = snapshot)."""

    def __init__(self, d, source):
        self.d, self.source = d, source
        for a in AREAS:
            a.parse(self, d)
        self.md5 = d["md5"]
        self.built = d.get("built")

    @classmethod
    def load(cls, force=False):
        cfg = config.get()
        with _cli_lock:
            if cfg.on_server or not os.path.isfile(CLIENT_FILES["item_list"]):
                if not os.path.isfile(SNAPSHOT):
                    raise OpRefused("снимок клиентских таблиц не собран (data/ref/shop_client.json): на ПК выкладки нет AstoryClient/RawAssets — "
                                    "разделы данных клиента недоступны")
                mt = os.path.getmtime(SNAPSHOT)
                hit = _cli_cache.get("snap")
                if force or not hit or hit[0] != mt:
                    _cli_cache["snap"] = (mt, cls(json.load(open(SNAPSHOT, encoding="utf-8")), "snapshot"))
                return _cli_cache["snap"][1]
            key = tuple(os.path.getmtime(p) if os.path.isfile(p) else 0 for p in CLIENT_FILES.values())
            key += (os.path.getmtime(PANEL_TAIL) if os.path.isfile(PANEL_TAIL) else 0,)
            hit = _cli_cache.get("port")
            if force or not hit or hit[0] != key:
                _cli_cache["port"] = (key, cls(build_client_snapshot(), "port"))
            return _cli_cache["port"][1]

    def on_premium(self, code):
        """Карточка кода на витринах 6000 / 15300 (включая хвост панели)."""
        return code in self.p6000 or code in self.tail or code in self.b15300

    def npc_shown(self, code):
        return sorted(n for n, v in self.npc.items() if code in (v.get("shown") or []))

    def price(self, code):
        r = self.items.get(int(code))
        return r[1] if r else None


# =====================================================================================================================
# ПОЗИЦИИ НАБОРА (логические) — через реестр видов
# =====================================================================================================================
def _ival(p, k, lo, hi):
    try:
        v = int(str(p.get(k, "")).strip())
    except (TypeError, ValueError):
        raise OpRefused("поле «%s»: нужно целое число" % k)
    if not lo <= v <= hi:
        raise OpRefused("поле «%s»: от %d до %d" % (k, lo, hi))
    return v


def norm(kind, p):
    """Позиция → канонические параметры (отказ — OpRefused с причиной)."""
    if kind not in KINDS:
        raise OpRefused("неизвестный вид позиции %s" % kind)
    return AREA_OF[kind].norm(kind, p or {})


def target_key(kind, p):
    """Цель позиции (две позиции на одну цель в наборе — отказ)."""
    return AREA_OF[kind].target_key(kind, p)


def area_perm(kind, which):
    """Право области вида: which = edit | apply (магазины — shop.*, данные А4 — data.*)."""
    a = AREA_OF.get(kind)
    return getattr(a, "PERM_APPLY" if which == "apply" else "PERM_EDIT", "shop.apply" if which == "apply" else "shop.edit") if a else None


def _name(code):
    if not code:
        return "—"
    inf = refdata.item(code)
    return inf["name"] or inf["ru"] or inf["en"] or "без названия"


def nm(code):
    return "%s (%d)" % (_name(code), code)


# =====================================================================================================================
# ОЦЕНКА НАБОРА: применение позиций к копиям таблиц + проверки
# =====================================================================================================================
class Eval:
    """Итог оценки набора. errors/warnings — общие; positions — по позициям; server — файлы; client — правки порта."""

    def __init__(self, items, urgent, snap=None, cli=None):
        self.items = items
        self.urgent = bool(urgent)
        self.snap = snap or Snap()
        self.areas = [a for a in AREAS if a is AREAS[0] or any(AREA_OF.get(it["kind"]) is a for it in items)]
        self.snap.extend(srv_rels_for(self.areas[1:]))              # ★ А4.0: таблицы других областей (магазинные — как в А3)
        self.cli = cli or Client.load()
        self.st = SrvState(self.snap)
        self.errors, self.warnings, self.positions, self.client = [], [], [], []
        self.sim = {}
        self.balance = []
        self.fn = srvtables.table("Function_Table.txt")
        self.cel = srvtables.table("Cellob_Table.txt")
        try:
            src = json.loads(srvtables.stack_text(PREMIUM_MAP).lstrip("\ufeff"))
        except Exception as ex:
            raise OpRefused("карта шлюза gp7 не прочитана: %s" % ex)
        self.pmap = {int(k): (v if isinstance(v, dict) else {"deliveryItemCode": v}) for k, v in src.items()}

    # ---- общие сведения о кодах (по item_table GameServer РАБОЧЕЙ копии) ----
    def it_fields(self, code, gs="GameServer"):
        t = self.st.get(gs, "item_table.txt")
        i = t.index().get(int(code))
        return _f(t.lines[i]) if i else None

    def exists(self, code):
        if ITEM_FIRST <= code:
            return self.it_fields(code) is not None
        if srvtables.CELLOB_BASE <= code < ITEM_FIRST:
            return code in self.cel
        return code in self.fn

    def _t39(self):
        """[(код, ток.16, ток.17, ток.39)] item_table GameServer (ток.39 позиции набора не меняют) — один разбор на оценку."""
        if not hasattr(self, "_t39c"):
            t = self.st.get("GameServer", "item_table.txt")
            self._t39c = []
            for code, i in t.index().items():
                f = _f(t.lines[i])
                if len(f) > 39:
                    self._t39c.append((code, _int(f[16]), _int(f[17]), _int(f[39])))
        return self._t39c

    def booster_users(self, row):
        """Предметы-бустеры строки: ток.39 = строка, подтип не 200/201 (Recv_GachaItemUse)."""
        return sorted(c for c, _t, st, r in self._t39() if r == row and st not in (200, 201))

    def box_users(self, row):
        """Коробки строки пакета: 11/200 и ток.39 = строка (Recv_OpenPackageItem)."""
        return sorted(c for c, t, st, r in self._t39() if r == row and t == 11 and st == 200)

    def _npc_rules(self, code, rep=None):
        """Правила CharItemBuy@0x50F170 (cs_kinds/shops.npc_rules)."""
        return AREAS[0].npc_rules(self, code)

    def run(self):
        seen = {}
        for it in self.items:
            kind, p = it["kind"], it["params"]
            rep = {"pos": it["pos"], "kind": kind, "params": p, "text": "", "errors": [], "warnings": [], "client": [],
                   "urgent_ok": KINDS.get(kind, ("", (), False))[2]}
            self.positions.append(rep)
            try:
                p = norm(kind, p)
            except OpRefused as ex:
                rep["errors"].append(str(ex))
                continue
            key = target_key(kind, p)
            if key in seen:
                rep["errors"].append("две позиции набора на одну цель (позиция %d)" % seen[key])
                continue
            seen[key] = it["pos"]
            try:
                getattr(AREA_OF[kind], "k_" + kind.replace(".", "_"))(self, p, rep)
            except OpRefused as ex:
                rep["errors"].append(str(ex))
        self.cross()
        for a in self.areas:
            if hasattr(a, "after_run"):
                a.after_run(self)
        if self.urgent:
            bad = [r["pos"] for r in self.positions if not r["urgent_ok"]]
            if bad:
                self.errors.append("«срочно, только сервер» — только запрет продажи и веса бустеров без смены кодов (позиции %s)"
                                   % ", ".join(map(str, bad)))
        for r in self.positions:
            self.errors += ["позиция %d: %s" % (r["pos"], e) for e in r["errors"]]
        if not self.items:
            self.errors.append("в наборе нет позиций")
        self.balance = balance_of(self)
        return self

    # ---- сквозные проверки по итоговому состоянию ----
    @property
    def _premium_new(self):
        return AREAS[0].premium_new(self)

    def cross(self):
        for a in self.areas:
            if hasattr(a, "cross_pre"):
                a.cross_pre(self)
        # все копии семьи меняются (выкладчик требует все GameServer / все NpcServer; Ch2 = копия поля); базы — по политике таблицы
        touched = self.st.touched()
        by_table = {}
        for rel in touched:
            g, name = split_rel(rel)
            by_table.setdefault((name, family(g)), set()).add(g)        # ★ А5.5: таблица × семья процесса (patches.ini — у трёх процессов)
        for (name, base), gs in by_table.items():
            sub = rel_of("X", name)[2:]
            fam = srv_family_of(sorted(gs)[0], sub)          # ★ А4.8: семья по таблице (GSF — копии поля); ★ А5.5: и по процессу копии
            want = folders(fam)
            if fam in PAIR_FAMILIES:                         # ★ А5.5: ini DLL — парами «поле = Ch2», Indun отдельно
                why = pair_ok(fam, gs, name)
                if why:
                    self.errors.append(why)          # ★ ревизия 45 В-1: полный текст (перевод — полным шаблоном, не общим «%s: %s — …»)
                want = [g for g in want if g in gs]
            if gs != set(want):
                if fam in ONE_FAMILIES or fam == "SDB":
                    self.errors.append("%s меняется не во всех копиях (%s) — выкладчик требует %s, пересоберите набор"
                                       % (name, ", ".join(sorted(gs)), ", ".join(want)))
                elif fam == "GSF":
                    self.errors.append("%s меняется не во всех копиях поля (%s) — выкладчик требует %s, пересоберите набор"
                                       % (name, ", ".join(sorted(gs)), ", ".join(want)))
                elif fam == "GS":
                    self.errors.append("%s меняется не во всех GameServer (%s) — выкладчик требует все %d; пересоберите набор"
                                       % (name, ", ".join(sorted(gs)), len(want)))
                else:
                    self.errors.append("%s меняется не во всех NpcServer (%s) — выкладчик требует все %d; пересоберите набор"
                                       % (name, ", ".join(sorted(gs)), len(want)))
            pol = srv_policy_of(sorted(gs)[0], sub)            # ★ А5.5: политика по (семья процесса, подпуть)
            if pol == "same":
                base = {self.snap.md5[rel_of(g, name)] for g in want}
                if len(base) > 1:
                    self.errors.append("%s на GameServer стойки разные (md5 %s) — правка вслепую запрещена" % (name, ", ".join(sorted(base))))
            elif pol == "per_copy":
                lay = _layout()
                for twin, field in lay.TWINS.items():
                    if twin in want and self.snap.md5.get(rel_of(twin, name)) != self.snap.md5.get(rel_of(field, name)):
                        self.errors.append("%s: у %s база ≠ %s (паритет Ch2) — сначала stack_parity" % (name, twin, field))
        for a in self.areas:
            if hasattr(a, "cross_post"):
                a.cross_post(self)
        if self.cli.source == "snapshot":
            self.warnings.append("клиентские таблицы — по снимку выкладки панели от %s; клиентская половина сверяется с портом на ПК"
                                 % self.cli.built)
        self.warnings.append("код проверен по таблицам порта, не по паку выпущенного клиента")

    # ---- итог ----
    def summary(self):
        srv = {}
        for rel, t in sorted(self.st.touched().items()):
            srv[rel] = {"base": t.base_md5, "new": md5b(t.data()), "diff": t.diff()}
        groups = {}
        for rel, v in srv.items():
            g, name = split_rel(rel)
            groups.setdefault((name, v["base"], v["new"]), []).append(g)
        files = [{"table": k[0], "gs": gs, "base": k[1], "new": k[2], "diff": srv[rel_of(gs[0], k[0])]["diff"]}
                 for k, gs in groups.items()]
        return {"ok": not self.errors, "errors": self.errors, "warnings": self.warnings,
                "positions": [{k: v for k, v in r.items() if not k.startswith("_")} for r in self.positions],
                "server": {"files": files, "count": len(srv)}, "client": self.client, "sim": self.sim,
                "base": {rel: self.snap.md5[rel] for rel in srv} or {}, "base_all": self.snap.md5,
                "client_md5": self.cli.md5, "client_source": self.cli.source, "client_built": self.cli.built,
                "urgent_ok": all(r["urgent_ok"] for r in self.positions),
                "sale_codes": sorted({c for r in self.positions for c in r.get("_codes", [])}),
                "server_needed": bool(srv), "client_needed": any(not e.get("optional") for e in self.client),
                "balance": self.balance, "balance_strong": any(b["strong"] and b["gate"] for b in self.balance)}

    def new_bytes(self):
        return {rel: t.data() for rel, t in self.st.touched().items()}


# =====================================================================================================================
# БАЛАНС: сильная правка → двойное подтверждение (решение владельца 19.11)
# =====================================================================================================================
def is_strong(old, new):
    """Значение меняется больше чем в BALANCE_RATIO раз (в любую сторону); из нуля / в ноль — сильная."""
    try:
        o, n = float(old), float(new)
    except (TypeError, ValueError):
        return True
    if o == n:
        return False
    if o == 0 or n == 0:
        return True
    r = abs(n / o)
    return r > BALANCE_RATIO or r < 1.0 / BALANCE_RATIO


def balance_of(ev):
    """Правки баланса позиций: [{pos, what, old, new, codes, kind, strong, gate}]. kind = value (число) | stack | type | swap
    (стопка / тип / замена предмета у кода, что может быть у игроков — сильная всегда). gate — область требует второго
    подтверждения (BALANCE_GATE; магазины А3 — только сведения)."""
    out = []
    for r in ev.positions:
        if r["errors"]:
            continue
        gate = bool(getattr(AREA_OF.get(r["kind"]), "BALANCE_GATE", False))
        for b in r.get("_balance") or []:
            kind = b.get("kind", "value")
            strong = kind != "value" or is_strong(b.get("old"), b.get("new"))
            out.append({"pos": r["pos"], "what": b["what"], "old": b.get("old"), "new": b.get("new"), "codes": list(b.get("codes") or []),
                        "kind": kind, "strong": strong, "gate": gate, "totp": bool(b.get("totp"))})   # ★ ревизия 45 Н-5: второй фактор
    return out


HELD_TABLES = ("Item", "Exitem", "ItemPostBox", "gifts")   # ★ ревизия 33 М-2 / 36 М-2: места хранения Joy1 dbo.* (см. held_counts)
HELD_MAX = 900                                      # кодов в одном запросе (IN-список); остальные — «не прочитано», с причиной


def stack_flags(ev, codes):
    """{код: стопочный} по item_table GameServer рабочей копии (правило asda_premium_box_add.verify: ток.3 = 4, ток.23 = 1,
    ток.24 = 1, ток.16 ≠ 10); коды вне item_table — не стопочные."""
    out = {}
    for c in codes:
        f = ev.it_fields(c) if int(c) >= ITEM_FIRST else None
        out[int(c)] = bool(f) and f[3] == "4" and f[23] == "1" and f[24] == "1" and f[16] != "10"
    return out


def held_counts(codes, stack=None):
    """Сколько кодов на руках у игроков → {код: {"rows": записей (экземпляров), "amount": сумма Amount, "stack": стопочный,
    "where": {таблица: записей}}}, или None (не прочитано; причина — в held_counts.last_error).
    ★ ревизия 33 М-2: живые места хранения Joy1 — Item (все Plate: сумки, склад, надетое, питомец…), Exitem (лоты аукциона: вещь
    у продавца, вернётся ему или уйдёт покупателю) и ItemPostBox (почта: ещё не забранные вложения). Del_* (удалённое, журнал
    восстановления) — не «на руках» и не считаются. ★ ревизия 36 М-2: ещё dbo.gifts (отложенные подарки, Code/Amount), неоткаченные
    снимки adm.ItemTaken (ItemLedger.UndoneBy IS NULL — adm.ItemUndo вернёт строку с прежними Amount и Weight) и неурегулированные
    подарки AsdaStoryLogin.dbo.GP7GiftLog (state 'H', code1…code7; считаются записи). Нет таблицы или столбцов — «не прочитано»
    (None), не тихий пропуск. Для нестопочных количество = число записей (Amount у них — не штуки), для стопочных — сумма Amount."""
    held_counts.last_error = None
    codes = sorted({int(c) for c in codes if int(c) > 0})
    if not codes:
        return {}
    cut = codes[HELD_MAX:]
    codes = codes[:HELD_MAX]
    stack = stack or {}
    try:
        from core import db
        out = {c: {"rows": 0, "amount": 0, "max": 0, "stack": bool(stack.get(c)), "where": {}} for c in codes}
        inl = ",".join(str(c) for c in codes)

        def add(t, rows):
            for r in rows:
                o = out[int(r["Code"])]
                o["rows"] += int(r["n"] or 0)
                o["amount"] += int(r["a"] or 0)
                o["max"] = max(o["max"], int(r["mx"] or 0))
                o["where"][t] = o["where"].get(t, 0) + int(r["n"] or 0)

        def need(reader, obj, cols):
            # ★ ревизия 36 М-2: нет таблицы или столбцов — «не прочитано» (отказ у вызывающих), а не тихий пропуск
            have = {r["name"].lower() for r in reader.rows("SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(?)", (obj,))}
            miss = [c for c in cols if c.lower() not in have]
            if miss:
                raise RuntimeError("%s: нет таблицы или столбцов %s" % (obj, ", ".join(miss)))

        with db.GameReader("joy1") as j:
            for t in HELD_TABLES:
                need(j, "dbo." + t, ("Code", "Amount"))
                # ★ А4.4: max — самая большая строка (стопка) по коду: правка веса стопочного предмета (Weight SMALLINT = n × вес)
                add(t, j.rows("SELECT Code, COUNT(*) AS n, SUM(CAST(Amount AS bigint)) AS a, MAX(CAST(Amount AS bigint)) AS mx "
                              "FROM dbo.%s WHERE Code IN (%s) GROUP BY Code" % (t, inl)))
            # ★ ревизия 36 М-2: неоткаченные снимки изъятия — adm.ItemUndo вернёт строку с ПРЕЖНИМИ Amount и Weight
            need(j, "adm.ItemTaken", ("Code", "Amount", "LedgerId"))
            need(j, "adm.ItemLedger", ("Id", "UndoneBy"))
            add("ItemTaken", j.rows("SELECT t.Code, COUNT(*) AS n, SUM(CAST(t.Amount AS bigint)) AS a, MAX(CAST(t.Amount AS bigint)) AS mx "
                                    "FROM adm.ItemTaken t JOIN adm.ItemLedger l ON l.Id = t.LedgerId "
                                    "WHERE l.UndoneBy IS NULL AND t.Code IN (%s) GROUP BY t.Code" % inl))
        # ★ ревизия 36 М-2: неурегулированные подарки GP7 (state 'H' — заморожены, предмет ещё не выдан; amount — цена, не штуки)
        with db.GameReader("asdastorylogin") as g:
            need(g, "dbo.GP7GiftLog", ("state",) + tuple("code%d" % k for k in range(1, 8)))
            for k in range(1, 8):
                add("GP7GiftLog", g.rows("SELECT code{0} AS Code, COUNT(*) AS n, 0 AS a, 0 AS mx FROM dbo.GP7GiftLog "
                                         "WHERE state = 'H' AND code{0} IN ({1}) GROUP BY code{0}".format(k, inl)))
        if cut:
            held_counts.last_error = "кодов больше %d — %d не прочитаны" % (HELD_MAX, len(cut))
        return out
    except Exception as ex:
        held_counts.last_error = str(ex)[:200]
        return None


held_counts.last_error = None


def held_text(held):
    if held is None:
        return "не прочитано (%s)" % (held_counts.last_error or "нет связи с Joy1")
    if not held:
        return "предметов нет"
    parts = []
    for c, v in sorted(held.items()):
        if v.get("stack"):
            parts.append("%d: %d шт. в %d стопках" % (c, v["amount"], v["rows"]))
        else:
            parts.append("%d: %d экз." % (c, v["rows"]))
    return ", ".join(parts)


def balance_report(s):
    """Сильные правки с гейтом → (строки, коды). Для предпросмотра утверждения и проверки."""
    strong = [b for b in s.get("balance") or [] if b["strong"] and b["gate"]]
    codes = sorted({c for b in strong for c in b["codes"]})
    lines = ["позиция %d: %s: %s → %s" % (b["pos"], b["what"], b["old"], b["new"]) for b in strong]
    return lines, codes


# =====================================================================================================================
# ВЕДОМОСТИ ItemDB (правило itemdb-ledger-overlays): правка CSV порта → строка ведомости + доказательство перегенерацией
# =====================================================================================================================
_regen_lock = threading.Lock()


def ledger_paths(key):
    """(_value_overlay/<т>.csv, _tail_append/<т>.csv) для CSV порта key."""
    return (os.path.join(LEDGER_ROOT, "_value_overlay", key + ".csv"), os.path.join(LEDGER_ROOT, "_tail_append", key + ".csv"))


def all_ledger_paths():
    return [p for k in LEDGER_TABLES for p in ledger_paths(k)]


def itemdb_regen(key, value_dir, tail_dir):
    """Декод записи архива Bin.bbz НАСТОЯЩИМ генератором decode_item_db.py с ведомостями из value_dir / tail_dir и шагом item_dedup
    (как при перегенерации боевого каталога, без слоя имён) → список строк {колонка: значение}. Только ПК."""
    import zipfile
    with _regen_lock:
        config.port_code(DECODER_DIR)       # ★ ревизия 56 С-1: только ПК
        if DECODER_DIR not in sys.path:
            sys.path.insert(0, DECODER_DIR)
        import decode_item_db as D          # noqa: E402 — генератор ItemDB (при импорте ничего не делает)
        z = zipfile.ZipFile(D.DEFAULT_BBZ)
        names = {n.lower(): n for n in z.namelist()}
        name = LEDGER_TABLES[key]
        saved = (D.VALUE_LEDGER_DIR, D.TAIL_LEDGER_DIR)
        D.VALUE_LEDGER_DIR, D.TAIL_LEDGER_DIR = value_dir, tail_dir
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                res = D.decode_table(name, z.read(names[name]), D.REGISTRY[name], True, D._DD.load_map())
        finally:
            D.VALUE_LEDGER_DIR, D.TAIL_LEDGER_DIR = saved
        return res["rows"]


def itemdb_cols(key):
    """Раскладка записи таблицы ItemDB из реестра генератора: {колонка: (смещение в DataHex, тип)} (только ПК)."""
    with _regen_lock:
        config.port_code(DECODER_DIR)       # ★ ревизия 56 С-1: только ПК
        if DECODER_DIR not in sys.path:
            sys.path.insert(0, DECODER_DIR)
        import decode_item_db as D          # noqa: E402
        spec = D.REGISTRY[LEDGER_TABLES[key]]
        out = {nm: (off, typ) for off, typ, nm in spec["cols"]}
        out.update(spec.get("ledger_fields", {}))
        return out


_PACK = {"i32": "<i", "u32": "<I", "i16": "<h", "u16": "<H", "i8": "<b", "u8": "<B", "f32": "<f"}


def rebuild_hex(key, hexstr, cells):
    """DataHex записи с новыми значениями колонок cells (как decode_item_db.apply_fixes: правка ложится на байты записи)."""
    lay = itemdb_cols(key)
    b = bytearray(bytes.fromhex(hexstr))
    for c, v in cells.items():
        if c not in lay:
            raise ValueError("колонки %s нет в раскладке %s" % (c, LEDGER_TABLES[key]))
        off, typ = lay[c]
        if typ.startswith("s"):
            w = int(typ[1:])
            enc = str(v).encode("cp1251")
            if len(enc) >= w:
                raise ValueError("%s: %d б не входит в %s" % (c, len(enc), typ))
            b[off:off + w] = enc + b"\0" * (w - len(enc))
        else:
            struct.pack_into(_PACK[typ], b, off, float(v) if typ == "f32" else int(v))
    return bytes(b).hex()


def _csv_rows(raw):
    """Байты CSV → (заголовок, {_row: строка-словарь}, порядок строк)."""
    csv.field_size_limit(1 << 30)
    text = raw.decode("utf-8-sig") if raw else ""
    rd = csv.DictReader(io.StringIO(text, newline=""))
    rows = list(rd)
    return list(rd.fieldnames or []), {r["_row"]: r for r in rows if r.get("_row") not in (None, "")}, rows


def _cell(v, col):
    s = "" if v is None else str(v)
    return s.lower() if col == "DataHex" else s


def ledger_plan(key, old_csv, new_csv, load, cs_id, reason, errors, fixes=None):
    """Правка CSV порта key (байты было → станет) → правки ведомостей через load(тег, путь) ([прежние, новые] байты; пишет
    client_write вместе с CSV, с бэкапом). Строка из хвоста (_tail_append) правится на месте; строка архива — новой строкой
    _value_overlay «было (текущее) → стало» В КОНЕЦ (ведомости только дописываются; декодер накладывает строки по порядку).
    Доказательство: перегенерация с прежними ведомостями = прежний CSV по правленым ячейкам (иначе CSV правили мимо ведомости —
    отказ), с новыми — ровно план, прочие строки не задеты."""
    head, old_rows, _ = _csv_rows(old_csv)
    _h2, new_rows, _ = _csv_rows(new_csv)
    changed = {}
    for r, nr in new_rows.items():
        orow = old_rows.get(r)
        if orow is None:
            errors.append("%s: строки _row=%s нет в прежнем CSV — дописывание строк в А4 не делается" % (key, r))
            continue
        cells = {c: (orow.get(c), nr.get(c)) for c in head if orow.get(c) != nr.get(c)}
        if cells:
            changed[r] = cells
    if not changed:
        return
    vo_path, ta_path = ledger_paths(key)
    vo = load("ledger_vo:" + key, vo_path)
    ta = load("ledger_ta:" + key, ta_path)
    t_head, t_rows, t_list = _csv_rows(ta[1]) if ta[1] else ([], {}, [])
    vo_text = vo[1].decode("utf-8") if vo[1] else ""
    nl = "\r\n" if "\r\n" in vo_text or not vo_text else "\n"
    add = []
    tail_hit = False
    # ★ А4.4 (20.11.2026): поля ведомости без колонки CSV (реестр декодера ledger_fields: item_list Weight +72, Field68 +68 …) правятся
    #   только в байтах DataHex — их «было → стало» берётся из DataHex и пишется строкой ведомости по имени поля (декодер патчит те же
    #   байты); после перегенерации каждое такое поле сверяется с планом (иначе DataHex генератора молча вернул бы прежнее значение)
    hexf = {}
    for r, cells in changed.items():
        if "DataHex" in cells:
            lay = itemdb_cols(key)
            for nm, (off, typ) in lay.items():
                if nm in head:
                    continue
                o, n = _hex_val(cells["DataHex"][0], off, typ), _hex_val(cells["DataHex"][1], off, typ)
                if o != n:
                    hexf.setdefault(r, {})[nm] = (o, n, off, typ)
    for r, cells in sorted(changed.items(), key=lambda x: int(x[0])):
        for nm, (o, n, _off, _typ) in sorted((hexf.get(r) or {}).items()):
            if r not in t_rows:
                add.append([r, nm, str(o), str(n), "админ-центр, набор изменений №%s" % cs_id, reason])
        if r in t_rows:
            tail_hit = True
            for c, (_o, n) in cells.items():
                if c in t_head:
                    t_rows[r][c] = n
            # ★ ревизия 33 В-1: у таблиц с DataHex (dump_hex) декодер append_tail сверяет колонки ведомости с байтами DataHex и при
            #   расхождении отвергает ХВОСТ ЦЕЛИКОМ — байты правленых колонок пересобираются по раскладке реестра декодера
            if "DataHex" in t_head and t_rows[r].get("DataHex"):
                try:
                    hx = rebuild_hex(key, t_rows[r]["DataHex"], {c: n for c, (_o, n) in cells.items() if c not in ("DataHex", "_row")})
                except Exception as ex:
                    errors.append("%s _row=%s: DataHex строки хвоста не пересобран: %s" % (key, r, str(ex)[:160]))
                    continue
                t_rows[r]["DataHex"] = hx
                if fixes is not None:
                    fixes[r] = hx.upper() if str(new_rows[r].get("DataHex") or "").isupper() else hx
            continue
        for c, (o, n) in cells.items():
            if c in ("DataHex", "_row"):
                continue                    # DataHex декодер патчит сам (правка ложится на байты записи)
            add.append([r, c, o, n, "админ-центр, набор изменений №%s" % cs_id, reason])
    if add:
        if not vo_text:
            vo_text = _csv_join(LEDGER_COLS) + nl
        elif not vo_text.endswith(("\n", "\r")):
            vo_text += nl
        vo_text += "".join(_csv_join(x) + nl for x in add)
        vo[1] = vo_text.encode("utf-8")
    if tail_hit:
        b = io.StringIO()
        w = csv.DictWriter(b, fieldnames=t_head, lineterminator="\r\n" if b"\r\n" in ta[1] else "\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(t_list)
        ta[1] = b.getvalue().encode("utf-8")
    # доказательство перегенерацией
    tmp = tempfile.mkdtemp(prefix="asda_cs_ledger_")
    try:
        vd, td = os.path.join(tmp, "vo"), os.path.join(tmp, "ta")
        os.makedirs(vd)
        os.makedirs(td)
        for d, cur in ((vd, vo), (td, ta)):
            if cur[1] is not None:
                open(os.path.join(d, key + ".csv"), "wb").write(cur[1])
        rows0 = {str(x["_row"]): x for x in itemdb_regen(key, os.path.dirname(vo_path), os.path.dirname(ta_path))}
        rowsN = {str(x["_row"]): x for x in itemdb_regen(key, vd, td)}
    except Exception as ex:
        errors.append("%s: перегенерация ItemDB для проверки ведомости не прошла: %s" % (key, str(ex)[:200]))
        return
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(rows0) != len(old_rows) or len(rowsN) != len(new_rows):
        errors.append("%s: перегенерация даёт строк %d (прежние ведомости) / %d (новые), в CSV порта %d — хвост или CSV не из генератора; "
                      "правка отменена" % (key, len(rows0), len(rowsN), len(old_rows)))
        return
    for r, cells in changed.items():
        a, b, o, n = rows0.get(r) or {}, rowsN.get(r) or {}, old_rows[r], new_rows[r]
        for c in head:
            if c not in a:
                continue
            if _cell(a.get(c), c) == _cell(o.get(c), c):
                if _cell(b.get(c), c) != _cell(n.get(c), c) and c == "DataHex" and fixes is not None:
                    # ★ А4.0 (найдено живым прогоном генератора): у таблиц с dump_hex колонки записи лежат и в DataHex
                    #   (booster_list: коды и веса). Правка колонок без DataHex давала CSV, которого генератор не выдаёт
                    #   (дефект клиентской половины А3); DataHex берётся у генератора — CSV = перегенерация
                    h = str(b.get(c))
                    fixes[r] = h.upper() if str(n.get(c) or "").isupper() else h
                elif _cell(b.get(c), c) != _cell(n.get(c), c):
                    errors.append("%s _row=%s: перегенерация с ведомостью даст %s=%s, а план — %s" % (key, r, c, str(b.get(c))[:40], str(n.get(c))[:40]))
            elif o.get(c) != n.get(c):
                errors.append("%s _row=%s: %s в CSV порта (%s) ≠ генератору (%s) — CSV правили мимо ведомости; разберите до правки"
                              % (key, r, c, str(o.get(c))[:40], str(a.get(c))[:40]))
    for r, fl in sorted(hexf.items()):
        b = rowsN.get(r) or {}
        for nm, (o, n, off, typ) in sorted(fl.items()):
            got = _hex_val(b.get("DataHex"), off, typ)
            if got != n:
                errors.append("%s _row=%s: перегенерация с ведомостью даст %s=%s, а план — %s" % (key, r, nm, got, n))
    other = [r for r in rows0 if r not in changed and rows0[r] != rowsN.get(r)]
    if other:
        errors.append("%s: новая ведомость задевает чужие строки (%s) — правка отменена" % (key, ", ".join(other[:5])))


def _hex_val(hexstr, off, typ):
    """Значение поля записи по DataHex (тип раскладки реестра декодера); нет байтов — None."""
    try:
        b = bytes.fromhex(str(hexstr or ""))
    except ValueError:
        return None
    if typ.startswith("s"):
        w = int(typ[1:])
        return b[off:off + w].split(b"\0", 1)[0].decode("cp1251", "replace") if len(b) >= off + w else None
    fmt = _PACK[typ]
    return struct.unpack_from(fmt, b, off)[0] if len(b) >= off + struct.calcsize(fmt) else None


# =====================================================================================================================
# КЛИЕНТСКАЯ ПОЛОВИНА: план правок порта (ПК) — сухой прогон и запись
# =====================================================================================================================
def _csv_line(line):
    return next(csv.reader([line]))


def _csv_join(cells):
    b = io.StringIO()
    csv.writer(b, lineterminator="").writerow(cells)
    return b.getvalue()


def client_plan(edits, cs_id, reason=""):
    """Правки порта → {"files": {путь: {"old", "new", "diff"}}, "errors": [...], "dt_jobs": [...], "importers": [...]}.
    Ничего не пишет. Старые значения правок сверяются с живыми файлами (порт сменился — отказ «пересоберите»). Таблицы ItemDB —
    ещё и ведомости (ledger_plan)."""
    if config.get().on_server:
        raise OpRefused("клиентская половина — только на ПК владельца (служба на сервере не видит RawAssets/UE)")
    errors, files, dt_rows, imp = [], {}, {}, set()
    text = {}

    def load(key, path):
        if path not in text:
            raw = open(path, "rb").read() if os.path.isfile(path) else None
            text[path] = [raw, raw]
        return text[path]

    by_file = {}
    for e in edits:
        by_file.setdefault(e["file"], []).append(e)
    for key in [k for a in AREAS for k in getattr(a, "CSV_KEYS", ())]:
        es = by_file.get(key)
        if not es:
            continue
        path = CLIENT_FILES[key]
        cur = load(key, path)
        bom = cur[0].startswith(b"\xef\xbb\xbf")
        body = cur[0][3:] if bom else cur[0]
        nl = "\r\n" if b"\r\n" in body else "\n"
        lines = body.decode("utf-8").split(nl)
        head = _csv_line(lines[0])
        for e in es:
            kc = head.index(e["key_col"])
            hit = None
            for i in range(1, len(lines)):
                if not lines[i]:
                    continue
                cells = _csv_line(lines[i])
                if len(cells) > kc and cells[kc] == e["key"]:
                    hit = (i, cells)
                    break
            if not hit:
                errors.append("%s: строки %s=%s нет" % (key, e["key_col"], e["key"]))
                continue
            i, cells = hit
            if e["type"] == "csv_cell":
                ci = head.index(e["col"])
                if cells[ci] != e["old"]:
                    errors.append("%s %s=%s: %s сейчас %s, при проверке было %s — пересоберите набор"
                                  % (key, e["key_col"], e["key"], e["col"], cells[ci], e["old"]))
                    continue
                cells[ci] = e["new"]
            elif e["type"] == "csv_hex_i32":
                ci = head.index(e["col"])
                b = bytearray(bytes.fromhex(cells[ci]))
                if struct.unpack_from("<i", b, e["off"])[0] != int(e["old"]):
                    errors.append("%s %s=%s: DataHex +%s ≠ %s — пересоберите набор" % (key, e["key_col"], e["key"], hex(e["off"]), e["old"]))
                    continue
                struct.pack_into("<i", b, e["off"], int(e["new"]))
                h = bytes(b).hex()
                cells[ci] = h.upper() if cells[ci].isupper() else h
            elif e["type"] == "csv_hex_bytes":         # ★ А4.7: участок байтов записи DataHex (поля u8 / i16 / i32 навыка — одной правкой)
                ci = head.index(e["col"])
                b = bytearray(bytes.fromhex(cells[ci]))
                o, ob, nb = int(e["off"]), bytes.fromhex(e["old"]), bytes.fromhex(e["new"])
                if len(ob) != len(nb) or bytes(b[o:o + len(ob)]) != ob:
                    errors.append("%s %s=%s: DataHex +%d…+%d изменились с проверки — пересоберите набор"
                                  % (key, e["key_col"], e["key"], o, o + len(ob) - 1))
                    continue
                b[o:o + len(nb)] = nb
                h = bytes(b).hex()
                cells[ci] = h.upper() if cells[ci].isupper() else h
            elif e["type"] == "csv_cells":
                bad = [c for c, (o, _n) in e["cells"].items() if cells[head.index(c)] != o]
                if bad:
                    errors.append("%s %s=%s: столбцы %s изменились с проверки — пересоберите набор"
                                  % (key, e["key_col"], e["key"], ", ".join(bad[:4])))
                    continue
                for c, (_o, n) in e["cells"].items():
                    cells[head.index(c)] = n
            lines[i] = _csv_join(cells)
            dt_rows.setdefault(key, set()).add(cells[0])
        new = (b"\xef\xbb\xbf" if bom else b"") + nl.join(lines).encode("utf-8")
        cur[1] = new
        if key in LEDGER_TABLES and cur[1] != cur[0]:
            fixes = {}
            ledger_plan(key, cur[0], cur[1], load, cs_id, reason or "набор изменений №%s админ-центра (причина — в карточке набора и "
                        "changelog)" % cs_id, errors, fixes)
            if fixes and "DataHex" in head:                 # DataHex строк — как у генератора (см. ledger_plan)
                hi = head.index("DataHex")
                for i in range(1, len(lines)):
                    if lines[i]:
                        cells = _csv_line(lines[i])
                        if cells[0] in fixes:
                            cells[hi] = fixes[cells[0]]
                            lines[i] = _csv_join(cells)
                cur[1] = (b"\xef\xbb\xbf" if bom else b"") + nl.join(lines).encode("utf-8")
    # ★ А4.2: область может добавить свои точечные DT (dt_rows {(DT, файл): строки}), JSON-точки вложенных DT (json_jobs —
    #   asda_dt_json_point.py) и предупреждения плана
    pc = {"by_file": by_file, "load": load, "errors": errors, "importers": imp, "cs_id": cs_id, "dt_rows": {}, "json_jobs": [],
          "warnings": [], "files": text}                 # ★ ревизия 34 М-3: files — все правки плана ([было, станет] байты по пути)
    for a in AREAS:
        if hasattr(a, "plan"):
            a.plan(pc)
    for path, (old, new) in text.items():
        if old == new:
            continue
        files[path] = {"old": md5b(old) if old else "none", "new": md5b(new),
                       "diff": _text_diff(old, new, binary=path.lower().endswith((".spd", ".she", ".bin")))}
    merged = {}                                          # ★ А4.2: один DT — одно задание (правки разных областей сливаются)
    for k, v in dt_rows.items():
        merged.setdefault((DT[k], os.path.normcase(os.path.abspath(CLIENT_FILES[k]))), [CLIENT_FILES[k], set()])[1].update(v)
    for (dt, f), v in pc["dt_rows"].items():
        merged.setdefault((dt, os.path.normcase(os.path.abspath(f))), [f, set()])[1].update(v)
    dts = [dt for dt, _f in merged]
    if len(set(dts)) != len(dts):
        errors.append("один DT из двух разных файлов: %s — план не собирается" % ", ".join(sorted({d for d in dts if dts.count(d) > 1})))
    jobs = [{"dt": dt, "file": f, "allow_rows": sorted(v)} for (dt, _n), (f, v) in merged.items()]
    return {"files": files, "errors": errors, "dt_jobs": jobs, "json_jobs": pc["json_jobs"], "warnings": pc["warnings"],
            "importers": sorted(imp), "_bytes": {p: v[1] for p, v in text.items()}}


def _text_diff(old, new, limit=30, binary=False):
    """Построчный дифф (двоичные .spd / .she / .bin — по смыслу области или как изменённые байты)."""
    import difflib
    if binary and old is not None:
        if len(old) >= 8 and len(old) == 8 + 4 * struct.unpack_from("<I", old, 4)[0] and len(new) >= 8:
            oc = list(struct.unpack_from("<%dI" % struct.unpack_from("<I", old, 4)[0], old, 8))
            nc = list(struct.unpack_from("<%dI" % struct.unpack_from("<I", new, 4)[0], new, 8))
            return ["+ %d" % c for c in nc if c not in oc] + ["- %d" % c for c in oc if c not in nc]
        out = ["байт +%d: %02x → %02x" % (i, a, b) for i, (a, b) in enumerate(zip(old, new)) if a != b]
        return out[:limit] + (["длина %d → %d" % (len(old), len(new))] if len(old) != len(new) else [])
    a = (old or b"").decode("utf-8", "replace").splitlines()
    b = new.decode("utf-8", "replace").splitlines()
    out = [ln[:300] for ln in difflib.unified_diff(a, b, lineterm="", n=0) if not ln.startswith(("---", "+++"))]
    return out[:limit]


# =====================================================================================================================
# РАСХОЖДЕНИЯ «сервер знает — клиент нет» и наоборот (разбор А3 §3.7; разделы областей)
# =====================================================================================================================
def divergence(limit=200, areas=None):
    """Экран расхождений (живая стойка + клиент порта / снимок). areas — ключи областей; по умолчанию — магазины (7 разделов А3);
    "all" — все области реестра."""
    want = [a for a in AREAS if (areas == "all" or a.AREA in (areas or ("shops",))) and hasattr(a, "divergence")]
    snap = Snap()
    snap.extend(srv_rels_for(want))
    cli = Client.load()
    ev = Eval([], False, snap, cli)
    out = {"client_source": cli.source, "client_built": cli.built, "sections": []}

    def sec(key, title, rows, note=""):
        out["sections"].append({"key": key, "title": title, "count": len(rows), "rows": rows[:limit], "note": note})

    for a in want:
        a.divergence(ev, cli, sec)
    return out


def gateway_stand(ev):
    """Стенд шлюза gp7 до/после (cs_kinds/shops.gateway_stand)."""
    return AREAS[0].gateway_stand(ev)


def utc_now():
    """Метка времени набора — UTC без пояса (ревизия 31 Н-В3: server_at / client_at / released_at везде в UTC; GP7PurchaseLog.
    created_at — SYSUTCDATETIME(), проверено на dev)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def to_utc(text):
    """ISO-время с поясом (releases.log: «…+00:00») → UTC без пояса; без пояса — считается UTC."""
    at = datetime.datetime.fromisoformat(text)
    return at.astimezone(datetime.timezone.utc).replace(tzinfo=None) if at.tzinfo else at


def releases_after(stamp):
    """Первый выпуск клиента (Releases/releases.log, время с поясом) позже метки stamp (UTC) или None; «at» — UTC."""
    if not os.path.isfile(RELEASES_LOG) or not stamp:
        return None
    for ln in open(RELEASES_LOG, encoding="utf-8", errors="replace").read().splitlines():
        t = ln.split("\t")
        try:
            at = to_utc(t[0])
        except (ValueError, IndexError):
            continue
        if at > stamp:
            return {"at": at.strftime("%Y-%m-%d %H:%M:%S"), "version": t[1] if len(t) > 1 else ""}
    return None


# =====================================================================================================================
# РЕЕСТР ВИДОВ (domains/cs_kinds): области подключаются ПОСЛЕДНИМИ — их модули берут общее отсюда
# =====================================================================================================================
from domains import cs_kinds as _K                                       # noqa: E402

_MULTI_SUB = set()                                                       # ★ А5.5: подпути, общие у разных семей
for _n in _K.AREA_MODULES:
    _a = importlib.import_module("domains.cs_kinds." + _n)
    AREAS.append(_a)
    for _k in _a.KINDS:
        if _k in KINDS:
            raise RuntimeError("вид позиции %s объявлен дважды (cs_kinds.%s)" % (_k, _n))
        KINDS[_k] = _a.KINDS[_k]
        AREA_OF[_k] = _a
    CLIENT_FILES.update(getattr(_a, "CLIENT_FILES", {}))
    DT.update(getattr(_a, "DT", {}))
    IMPORTERS.update(getattr(_a, "IMPORTERS", {}))
    for _fam, _sub, _pol in getattr(_a, "SRV_FILES", ()):
        # ★ А5.5: ключ (семья процесса, подпуть) — один подпуть бывает у разных процессов (ConfigSet\\patches.ini: GameServer, NpcServer,
        #   LoginManager); прежний ключ «подпуть» остаётся, пока подпуть у одной семьи (иначе убирается — он был бы неоднозначен)
        _base = "GS" if _fam == "GSF" else PAIR_FAMILIES.get(_fam, _fam)
        SRV_POLICY[(_base, _sub)] = _pol
        SRV_FAMILY[(_base, _sub)] = _fam
        if _sub in _MULTI_SUB or (_sub in SRV_FAMILY and SRV_FAMILY[_sub] != _fam):
            _MULTI_SUB.add(_sub)
            SRV_POLICY.pop(_sub, None)
            SRV_FAMILY.pop(_sub, None)
        else:
            SRV_POLICY[_sub] = _pol
            SRV_FAMILY[_sub] = _fam
    SrvState.KIND.update(getattr(_a, "TABLE_CLASSES", {}))     # ★ А5.5: свой класс таблицы для подпути (ini UTF-16 с BOM — IniTable)
    # ★ А4.3: таблицы, чьи md5 область дочитывает сама по мере надобности (Snap.extend в k_<вид>; 48 файлов копания × 3 NpcServer
    #   не читаются в каждой оценке) — только политика копий
    for _fam, _sub, _pol in getattr(_a, "SRV_FILES_LAZY", ()):
        SRV_POLICY[_sub] = _pol
_SH = AREAS[0]
SRV_TABLES = _SH.SRV_TABLES
SELL_CEIL, I16_MAX, SET_WEIGHT_CAP, GACHA_SLOTS_MAX, SPECIAL_MAX, ROLLS = (
    _SH.SELL_CEIL, _SH.I16_MAX, _SH.SET_WEIGHT_CAP, _SH.GACHA_SLOTS_MAX, _SH.SPECIAL_MAX, _SH.ROLLS)
booster_odds, booster_sim = _SH.booster_odds, _SH.booster_sim
del _n, _a, _k
