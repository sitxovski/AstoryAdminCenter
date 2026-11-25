# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/patchcfg.py — область «Настройки серверных патчей и конфиги стойки» (шаг А5.5 «patches.ini и конфиги», 21.11.2026; разбор
Reports/admin_center/impl_a5_live_20261121.md §«А5.5»).

ТОЛЬКО СЕРВЕР, только набором изменений и рестартом стойки (restart_stack.py: объявление, 3 мин, остановка, deploy_changeset.py с
перепроверкой после остановки, паритет Ch2, старт). Живые ini напрямую не пишутся никогда.

Виды:
  patch.set  — значение ключа ini нашей DLL: AsdaPatch (GameServer ×3, ConfigSet\\patches.ini, UTF-16 LE с BOM), AddonNPC (NpcServer ×3),
               LoginPatch (LoginManager), DBPatch (DBManager, dbpatch.ini), SrvDbPatch (RelayServer ×3 + ItemRelayServer + OperationServer,
               srvdbpatch.ini). Ключ и секция — только из шаблона DLL (каталог domains/patchcfg_src: Config.cpp) И из живого файла (ключа
               нет в файле — живая DLL его не знает: MergeMissing дописал бы все ключи своей сборки). Значение — по типу и пределу места
               чтения в исходнике (GetBool — 0/1, GetInt — целое в пределе Clamp / if, GetStr — строка без перевода строки).
               Охват копий: all (все копии семьи), field (поле + Ch2), indun (только Indun) — у GameServer / NpcServer; пары «поле — Ch2»
               всегда вместе (restart_stack код 6). Каждая копия правится по СВОЕЙ базе (Indun не затирается).
  config.set — значение стокового конфига стойки из белого списка CONFIGS (разбор реверсом, см. CONFIGS); прочие конфиги — только
               просмотр (domains/patchcfg.py: адреса, порты, DSN, потоки), секреты не показываются вовсе.
Отказы (k_*): секция / ключ не из шаблона; ключа нет в живом файле; путь / секрет / Version / адрес — только просмотр; значение вне типа и
предела; уже стоит; выключение патча, от которого зависят включённые (HARD_DEPS — проверены по коду), если зависимые не выключаются
этим же набором; P127 (мост панели) — выключение и Mode≠1 отказ всегда; секция повторяется в файле (правка неоднозначна); ожидающий
набор с той же целью и другим значением (cross_post). Сильная правка (второе подтверждение владельца при утверждении, BALANCE_GATE):
MasterEnable, выключение патча (Enabled 1 → 0), Mode, ключи патчей защиты (STRONG_SECTIONS).
Формат ini сохраняется: кодировка и BOM, концы строк, комментарии, порядок, пробелы вокруг «=», Version не трогается.
Побочных эффектов при импорте нет.
"""
import re

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "patchcfg", "Настройки серверных патчей и конфиги стойки"
PERM_EDIT, PERM_APPLY = "patchcfg.edit", "patchcfg.apply"
BALANCE_GATE = True
CLIENT_FILES, DT, IMPORTERS, CSV_KEYS = {}, {}, {}, ()

# DLL → (ini, семья) — = patchcfg_src.DLLS (самотест сверяет)
DLL_INI = {"AsdaPatch": ("ConfigSet\\patches.ini", "GSP"), "AddonNPC": ("ConfigSet\\patches.ini", "NPCP"),
           "LoginPatch": ("ConfigSet\\patches.ini", "LM"), "DBPatch": ("ConfigSet\\dbpatch.ini", "DBM"),
           "SrvDbPatch": ("ConfigSet\\srvdbpatch.ini", "SDB")}

# Стоковые конфиги, которые оператор правит наборами (реверс А5.5 §1.3): файл → {(секция, шаблон ключа): (lo, hi, что, где читается)}.
#   ini\\Collection.ini NpcServer ×3 — CollectionTypeAniTime<NN> (WORD, мс): NpcServer sub_44E7D0 (NpcServer.exe.c:53196) читает
#   при старте, CItemManager::GetCollectionAniTime (:28043) — длительность сбора типа NN (копание). CollectionTypeCount не правится (число
#   типов = число таблиц MiningItemTable\\<карта><NN>.mng — их нет для нового типа).
COLLECTION_NOTE = ("CollectionTypeAniTime<NN> — время сбора (копания) типа NN в мс (WORD), NpcServer читает его при старте (sub_44E7D0, "
                   "NpcServer.exe.c:53196) и отдаёт GetCollectionAniTime (:28043)")
CONFIGS = {
    "ini\\Collection.ini": {"family": "NPC", "keys": {("COLLECTION_INFO", r"CollectionTypeAniTime\d\d"): (
        100, 65535, "время сбора (копания) типа NN, мс — WORD", "NpcServer sub_44E7D0 (NpcServer.exe.c:53196) при старте; "
        "GetCollectionAniTime (:28043)")}},
}

# Секции патчей защиты и античита: любая правка — сильная (второе подтверждение владельца). ★ ревизия 45 С-3: список — по реестру
#   INDEX.md (античит, защита от дюпа / подмены / выхода за границы, валидаторы, SQL-инъекции, шифрование, мост панели, режим
#   обслуживания) + ЛЮБАЯ секция с ключом Mode в шаблоне (режим «журнал / действует» есть только у защитных патчей) + имя секции со
#   словами защиты (STRONG_NAME: Guard, Bounds, Integrity, Validator, InFlight, Uniqueness, …) — см. strong_section().
STRONG_SECTIONS = {"P46_StoreShoutOverflow", "P47_IdentityOperatorGate", "P48_KickAutoBlock", "P49_OriginalChecksRestore",
                   "P53_AcJournal", "P55_PacketValidator", "P61_TrafficEncryption", "P69_IntegrityAutoBlock", "P72_HiddenWipeDisarm",
                   "P73_EacBridge", "P127_AdminBridge", "L03_LoginSqlRefuse", "L07_TrafficEncryption", "P28_SqlArgEscape",
                   "P26_SoulmateNoteSqli", "L04_LoginIdentity", "L09_LoginMaintenance", "P50_IdentityCheck",
                   # ★ ревизия 45 С-3 — дополнено по реестру
                   "P44_ExchangeIntegrity", "P62_SlotUniqueness", "P63_InFlightLock", "P64_StatePreamble", "P56_CombatLimits",
                   "P57_MoveGuard", "P60_ValueGuard", "P66_PositionGuard", "P81_ActionCodeGuard", "P92_HostileTargetGuard",
                   "P95_ItemUseGuard", "P107_CantActGate", "N14_CombatLimits", "N15_SkillArea", "N20_PartyShareClamp",
                   "N06_HateSearchOob", "P10_SectorIndexBoundsGuard", "P15_FunctionItemCodeBounds", "P18_WarehouseDupeAndBounds",
                   "P19_AuctionRecordBounds", "P76_SowelSlotBounds", "P68_CharNameGuard", "P121_CharRenameGuard",
                   "P118_AuctionTradeBlock", "P43_StorePriceCap", "P14_ChatMessageLength", "P103_InFlightFixes", "P65_ConsumableType",
                   "P04_InvincibleGmGate", "P40_CrystalTeleportGate", "L05_LogoutMd5Len", "L06_LoginMac"}
STRONG_NAME = re.compile(r"(Guard|Bounds|Integrity|Validator|InFlight|Uniqueness|Escape|Sqli|Encryption|Identity|Refuse|AutoBlock|"
                         r"Limits|Disarm|ChecksRestore|AcJournal|EacBridge|AdminBridge|Maintenance|Overflow|TradeBlock|Gate|Clamp|Oob)")

# Жёсткие зависимости (проверены по исходникам А5.5): (DLL, секция-поставщик) → [(секция-пользователь, ключи поставщика, почему)].
#   Выключение поставщика (Enabled = 0, ключ из списка = 0 или ★ ревизия 45 В-3 — значение из off_when каталога: P30 MaxMaps ≤ 23) при
#   включённом пользователе — отказ, если пользователь не выключается этим же набором. ★ ревизия 45 В-2: к ручному списку добавляются
#   зависимости из каталога — «if (!Config::GetBool(L"<чужая секция>", L"Enabled")) return Failed / Disabled» (P55 / P64 → P47,
#   N14 / N15 → P53 AddonNPC) — hard_deps().
HARD_DEPS = {
    ("AsdaPatch", "P30_MapSlots"): [
        ("P120_MineTravel", ("Enabled", "MaxMaps"), "слот карты 23 (шахта) даёт P30 (p120_mine_travel.cpp:7)"),
        ("P40_CrystalTeleportGate", ("Enabled", "MaxMaps"), "карты 0…29 — по пределу P30 (p40_crystal_teleport_gate.cpp:120-131)")],
    ("AsdaPatch", "P25_GmRatingRecalc"): [
        ("P127_AdminBridge", ("Enabled",), "rank_recalc моста — общая точка P25_RunRecalc, при выключенном P25 она отвечает −1 "
                                          "(p25_gm_rating_recalc.cpp:888)")],
    ("LoginPatch", "L04_LoginIdentity"): [
        ("L09_LoginMaintenance", ("Enabled", "CheckSoulMate"), "гейт входа в мир режима 2 L09 ставит через L04c (L04c_IsInstalled / "
                                                              "L04c_SetMaintGate, l09_login_maintenance.cpp:354)")],
}
# P127 — живой канал панели (live.*, режим обслуживания с киком, события 6038/6040, рейтинги 6020, монстры): выключение — отказ всегда.
#   ★ ревизия 45 С-2: [General] MasterEnable=0 у AsdaPatch снимает и P127 — тоже отказ (то же самое, что P127 Enabled=0).
PANEL_NEEDS = {("AsdaPatch", "P127_AdminBridge"): {"Enabled": "1", "Mode": "1"}, ("AsdaPatch", "General"): {"MasterEnable": "1"}}
# ★ ревизия 45 С-2: MasterEnable=0 у LoginPatch снимает L09 (режим обслуживания панели) и защиту входа (L03 / L04 / L07) — не отказ
#   (режим обслуживания включается только по слову владельца, мост панели от LoginPatch не зависит), а особая сильная правка с явным
#   текстом и вторым фактором при утверждении из браузера.
MASTER_LOSS = {"LoginPatch": "режим обслуживания панели (L09: вход только служебным учёткам) перестанет работать, защита входа L03 / L04 / "
                             "L07 снимется"}

# Ключи только для просмотра: пути, адреса, подключения к базе, секреты, имя узла; значения секретов не показываются (patchcfg.py)
#   (имена — по каталогу 21.11: 509 разных ключей; «…Ip» / «…Pass» у числовых ключей вроде MaxPendingPerIp, MaxGrantsPerPass — не адреса).
#   ★ ревизия 45 В-4: главное правило — по ТИПУ ЗНАЧЕНИЯ, не по имени: каталог (patchcfg_src) помечает view_only ключ, чей буфер GetStr
#   уходит в строку подключения / путь / адрес или чьё умолчание — адрес, «хост,порт», путь, строка подключения; при правке проверяется и
#   ЖИВОЕ значение копии (value_kind). Имена ниже — запасной слой (server / login / driver / uid / user / host / dsn / address).
VIEW_ONLY_KEYS = {"version", "connectionstring", "database", "dbconfigsection", "servername", "nodename", "port", "gameport",
                  "server", "login", "driver", "uid", "user", "username", "userid", "host", "hostname", "dsn", "address", "addr", "ip",
                  "password", "pwd"}
VIEW_ONLY_SEC_KEYS = {("p12_defaultserverip", "value")}               # адрес сервера по умолчанию (P12)
_VIEW_ONLY = re.compile(r"[a-z](File|Dir|Path|Folder)$")               # пути: CounterFile, SecretFile, KeyFile, FileDir, GradeTableFile…
_SECRET = re.compile(r"^(ConnectionString|\w*Password|\w*Secret|\w*Token|\w*Hmac)$", re.I)
STR_MAX = 511                                             # GetStr у DLL — буферы 64…512 знаков; ★ ревизия 45 Н-6: точный — maxlen каталога

KINDS = {
    "patch.set": ("Настройка серверного патча: ключ ini DLL (все копии процесса; действует после рестарта стойки)",
                  ("dll", "section", "key", "value", "scope"), False),
    "config.set": ("Конфиг стойки: ключ стокового ini из белого списка (действует после рестарта стойки)",
                   ("file", "section", "key", "value"), False),
}
SRV_FILES = [("GSP", "ConfigSet\\patches.ini", "per_copy"), ("NPCP", "ConfigSet\\patches.ini", "per_copy"),
             ("LM", "ConfigSet\\patches.ini", "own"), ("DBM", "ConfigSet\\dbpatch.ini", "own"),
             ("SDB", "ConfigSet\\srvdbpatch.ini", "per_copy"), ("NPC", "ini\\Collection.ini", "same")]


def view_only_why(key, section="", kd=None, value=None):
    """★ ревизия 45 В-4: почему ключ только для просмотра → текст | None. По типу значения (каталог kd["view_only"]: буфер уходит в
    подключение / путь / адрес, умолчание — адрес / путь / строка подключения; живое значение value того же вида), затем по имени."""
    k = key or ""
    if kd and kd.get("view_only"):
        return kd["view_only"]
    if value is not None:
        from domains import patchcfg_src
        vk = patchcfg_src.value_kind(value)
        if vk and (not kd or kd.get("type") in ("str", "mixed", None)):
            return "%s (живое значение)" % vk
    if k.lower() in VIEW_ONLY_KEYS:
        return "подключение, адрес, имя узла или Version (по имени ключа)"
    if _VIEW_ONLY.search(k):
        return "путь (по имени ключа)"
    if ((section or "").lower(), k.lower()) in VIEW_ONLY_SEC_KEYS:
        return "адрес сервера по умолчанию (P12)"
    return None


def is_view_only(key, section="", kd=None, value=None):
    return view_only_why(key, section, kd, value) is not None


def is_secret(key):
    return bool(_SECRET.search(key or ""))


def strong_section(dll, sec):
    """★ ревизия 45 С-3: секция защитная (любая правка — сильная)? sec — dict секции каталога или имя."""
    name = sec["name"] if isinstance(sec, dict) else sec
    keys = (sec.get("keys") or []) if isinstance(sec, dict) else []
    return name in STRONG_SECTIONS or bool(STRONG_NAME.search(name or "")) or any(k["key"] == "Mode" for k in keys)


def hard_deps(dll):
    """Жёсткие зависимости DLL: HARD_DEPS + из каталога (чтение чужой секции «if (!GetBool(…, Enabled)) return Failed / Disabled»)
    → {(dll, поставщик): [(пользователь, ключи, почему)]}."""
    out = {k: list(v) for k, v in HARD_DEPS.items() if k[0] == dll}
    d = catalog()["dlls"].get(dll) or {}
    for s in d.get("sections") or []:
        for f in s.get("reads_foreign") or []:
            if f.get("hard") and f.get("key") == "Enabled":
                lst = out.setdefault((dll, f["section"]), [])
                if not any(u == s["name"] for u, _k, _w in lst):
                    tpl = ("без [%s] Enabled патч %s не встанет (%s:%d)" if f["hard"] == "не встанет" else
                           "без [%s] Enabled патч %s выключится (%s:%d)")
                    lst.append((s["name"], ("Enabled",), tpl % (f["section"], s["name"], f["file"].split("/")[-1], f["line"])))
    return out


def off_by_value(kd, value):
    """★ ревизия 45 В-3: значение ВЫКЛЮЧАЕТ патч (off_when каталога: «if (cap < kStockSlots) return Disabled») → текст | None."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    for op, v, where in kd.get("off_when") or []:
        if {"<": n < v, "<=": n <= v, ">": n > v, ">=": n >= v, "==": n == v}.get(op):
            return "%s=%d: при %s %s %d патч выключается (%s)" % (kd["key"], n, kd["key"], op, v, where.split("/")[-1])
    return None


# =====================================================================================================================
# ini с сохранением формата (повтор правил GetPrivateProfileStringW)
# =====================================================================================================================
class IniTable:
    """ini одной копии: кодировка по BOM (FF FE — UTF-16 LE, EF BB BF — UTF-8, иначе cp1251), строки с их концами. Поиск — как у Win-ini:
    секция «[имя]» без учёта регистра, ключ «имя=…» до следующей секции, значение — после «=» без пробелов по краям (кавычки по краям —
    одна пара, как GetPrivateProfileString). Правка меняет только значение в строке ключа: пробелы вокруг, комментарии, прочие строки,
    концы строк и BOM — как были."""

    def __init__(self, rel, raw):
        self.rel, self.base_md5 = rel, E.md5b(raw)
        if raw.startswith(b"\xff\xfe"):
            self.enc, self.bom, body = "utf-16-le", raw[:2], raw[2:]
        elif raw.startswith(b"\xef\xbb\xbf"):
            self.enc, self.bom, body = "utf-8", raw[:3], raw[3:]
        else:
            self.enc, self.bom, body = "cp1251", b"", raw
        self.orig = raw
        self.text = body.decode(self.enc, "replace")
        self.lines = self.text.splitlines(keepends=True)
        self.changed = {}
        # ★ ревизия 45 Н-1: файл без правки должен собираться обратно в те же байты (неверный UTF-16, байт cp1251 0x98, нечётная длина
        #   UTF-16) — иначе правка одной строки переписала бы и эти места; такой файл панелью не правится (просмотр — как есть)
        self.bad = None if self.data() == raw else self.enc       # кодировка файла, который не собирается обратно байт в байт

    @staticmethod
    def _head(ln):
        s = ln.strip()
        if s.startswith("[") and "]" in s:
            return s[1:s.index("]")].strip()
        return None

    def sections(self, name):
        """Номера строк заголовков секции name (без учёта регистра)."""
        n = name.lower()
        return [i for i, ln in enumerate(self.lines) if (self._head(ln) or "\x00").lower() == n]

    def find(self, section, key):
        """→ (номер строки ключа | None, значение | None, число заголовков секции)."""
        heads = self.sections(section)
        if not heads:
            return None, None, 0
        k = key.lower()
        for i in range(heads[0] + 1, len(self.lines)):
            ln = self.lines[i]
            if self._head(ln) is not None:
                break
            s = ln.strip()
            if not s or s.startswith(";") or "=" not in s:
                continue
            if s.split("=", 1)[0].strip().lower() == k:
                v = s.split("=", 1)[1].strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                return i, v, len(heads)
        return None, None, len(heads)

    def get(self, section, key):
        return self.find(section, key)[1]

    def set(self, section, key, value):
        if self.bad:
            raise OpRefused("%s: файл не собирается обратно байт в байт (кодировка %s) — правка переписала бы и чужие места" % (self.rel, self.bad))
        i, _old, _n = self.find(section, key)
        if i is None:
            raise OpRefused("%s: ключа [%s] %s в файле нет — правка не делается" % (self.rel, section, key))
        ln = self.lines[i]
        body = ln.rstrip("\r\n")
        end = ln[len(body):]
        eq = body.index("=")
        tail = body[eq + 1:]
        lead = tail[:len(tail) - len(tail.lstrip())]
        trail = tail[len(tail.rstrip()):]
        val = tail.strip()
        q = val[0] if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'" else ""
        new = body[:eq + 1] + lead + q + value + q + trail + end
        if new != ln:
            self.changed.setdefault(i, ln)
            self.lines[i] = new

    def data(self):
        return self.bom + "".join(self.lines).encode(self.enc, "replace")

    def diff(self, limit=40):
        out = []
        for i in sorted(self.changed):
            if self.changed[i] != self.lines[i]:
                out.append([i + 1, self.changed[i].rstrip("\r\n")[:300], self.lines[i].rstrip("\r\n")[:300]])
        return out[:limit]


TABLE_CLASSES = {"ConfigSet\\patches.ini": IniTable, "ConfigSet\\dbpatch.ini": IniTable, "ConfigSet\\srvdbpatch.ini": IniTable,
                 "ini\\Collection.ini": IniTable}


# =====================================================================================================================
# Каталог
# =====================================================================================================================
_CAT = {}


def catalog():
    """Каталог ключей (domains/patchcfg_src.load; подмена самотеста — CAT_OVERRIDE)."""
    if CAT_OVERRIDE is not None:
        return CAT_OVERRIDE
    if "c" not in _CAT:
        from domains import patchcfg_src
        _CAT["c"] = patchcfg_src.load()
    return _CAT["c"]


CAT_OVERRIDE = None


def find_key(dll, section, key):
    """(секция шаблона, ключ шаблона) по имени без учёта регистра → (sec dict, key dict) или отказ."""
    d = catalog()["dlls"].get(dll)
    if not d:
        raise OpRefused("DLL «%s» нет в каталоге (AsdaPatch, AddonNPC, LoginPatch, DBPatch, SrvDbPatch)" % dll)
    sec = next((s for s in d["sections"] if (s["name"] or "").lower() == section.lower()), None)
    if not sec:
        raise OpRefused("секции [%s] нет в шаблоне %s (Config.cpp) — неизвестная секция" % (section, dll))
    k = next((x for x in sec["keys"] if x["key"].lower() == key.lower()), None)
    if not k:
        raise OpRefused("ключа %s нет в секции [%s] шаблона %s (Config.cpp) — неизвестный ключ" % (key, sec["name"], dll))
    return sec, k


def copies(dll, scope):
    ini, fam = DLL_INI[dll]
    allf = E.folders(fam)
    if fam not in E.PAIR_FAMILIES:
        if scope not in ("", "all"):
            raise OpRefused("поле «scope»: у %s одна семья копий — только all" % dll)
        return allf
    lay = E._layout()
    indun = [g for g in allf if g not in lay.TWINS and g not in lay.TWINS.values()]
    field = [g for g in allf if g not in indun]
    return {"": allf, "all": allf, "field": field, "indun": indun}[scope]


def check_value(k, value):
    """Значение по типу и пределу места чтения → нормализованная строка или отказ."""
    v = str(value).strip()
    t = k.get("type")
    if "\r" in v or "\n" in v:
        raise OpRefused("значение с переводом строки — ini его не прочтёт")
    if t == "bool":
        if v not in ("0", "1"):
            raise OpRefused("ключ %s читается GetBool — только 0 или 1" % k["key"])
        return v
    if t in ("int", "mixed"):
        if not re.match(r"^-?\d{1,10}$", v):
            raise OpRefused("ключ %s читается GetInt — нужно целое число" % k["key"])
        n = int(v)
        if not -2147483648 <= n <= 2147483647:
            raise OpRefused("ключ %s: число вне 32 бит" % k["key"])
        lo, hi = k.get("lo"), k.get("hi")
        if lo is not None and n < lo or hi is not None and n > hi:
            raise OpRefused("ключ %s: допустимо %s…%s (%s) — %d вне предела" % (
                k["key"], "−∞" if lo is None else lo, "∞" if hi is None else hi, k.get("range_src") or "исходник", n))
        if n in (k.get("excl") or []):                              # ★ ревизия 45 С-1: P40 RefuseCode=1 — DLL молча берёт 0
            raise OpRefused("ключ %s: значение %d недопустимо — DLL его не примет и возьмёт умолчание (условие в месте чтения)" % (k["key"], n))
        if lo is None and n < 0 and not str(k.get("def", "")).startswith("-"):
            raise OpRefused("ключ %s: отрицательное значение, а умолчание шаблона неотрицательное и предел в исходнике не найден" % k["key"])
        return str(n)
    mx = k.get("maxlen") or STR_MAX                                 # ★ ревизия 45 Н-6: размер буфера GetStr места чтения
    if len(v) > mx:
        raise OpRefused("ключ %s: строка длиннее %d знаков (буфер чтения в DLL) — DLL молча обрезала бы её" % (k["key"], mx))
    if any(ord(c) < 32 for c in v):
        raise OpRefused("ключ %s: управляющие символы в строке" % k["key"])
    return v


def norm(kind, p):
    if kind == "config.set":
        f = str(p.get("file", "")).strip()
        if f not in CONFIGS:
            raise OpRefused("конфиг «%s» панелью не правится (белый список: %s) — прочие только просмотр" % (f, ", ".join(sorted(CONFIGS))))
        return {"file": f, "section": str(p.get("section", "")).strip(), "key": str(p.get("key", "")).strip(),
                "value": str(p.get("value", "")).strip()}
    dll = str(p.get("dll", "")).strip()
    if dll not in DLL_INI:
        raise OpRefused("DLL «%s» панелью не правится (AsdaPatch, AddonNPC, LoginPatch, DBPatch, SrvDbPatch)" % dll)
    scope = str(p.get("scope", "") or "all").strip()
    if scope not in ("all", "field", "indun"):
        raise OpRefused("поле «scope»: all, field или indun")
    sec, k = find_key(dll, str(p.get("section", "")).strip(), str(p.get("key", "")).strip())
    why = view_only_why(k["key"], sec["name"], k)
    if why:
        raise OpRefused("ключ [%s] %s — только просмотр: %s" % (sec["name"], k["key"], why))
    if is_secret(k["key"]):
        raise OpRefused("ключ [%s] %s — секрет: только просмотр" % (sec["name"], k["key"]))
    copies(dll, scope)
    return {"dll": dll, "section": sec["name"], "key": k["key"], "value": check_value(k, p.get("value", "")), "scope": scope}


def target_key(kind, p):
    if kind == "config.set":
        return "config:%s:%s:%s" % (p["file"], p["section"].lower(), p["key"].lower())
    return "patch:%s:%s:%s:%s" % (p["dll"], p["section"].lower(), p["key"].lower(), p["scope"])


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def _touch(ev, dll, sec, key, folders):
    """Одна цель на копию в наборе (all и field на один ключ — отказ)."""
    m = ev.__dict__.setdefault("_patchcfg_targets", {})
    for g in folders:
        t = (dll, sec.lower(), key.lower(), g)
        if t in m:
            raise OpRefused("ключ [%s] %s копии %s уже правит позиция %d этого набора" % (sec, key, g, m[t]))
    return m


def _set_items(ev):
    """Позиции этого набора: {(dll, секция, ключ): значение} — чтобы зависимый, выключаемый тем же набором, не мешал."""
    out = {}
    for it in ev.items:
        if it["kind"] == "patch.set":
            p = it["params"]
            out[(str(p.get("dll")), str(p.get("section", "")).lower(), str(p.get("key", "")).lower())] = str(p.get("value", "")).strip()
    return out


def _is_off(old, new):
    return str(new).strip() == "0" and str(old).strip() not in ("0", "")


def _deps_check(ev, dll, sec, key, new, folders, rep, off=False):
    """Отказ, если выключается поставщик, а пользователь включён (и не выключается этим же набором); панель — P127. off — правка
    выключает патч (Enabled 1 → 0 или значение из off_when каталога, ★ ревизия 45 В-3)."""
    need = PANEL_NEEDS.get((dll, sec))
    if need and key in need and str(new) != need[key]:
        raise OpRefused("[%s] %s=%s — мост P127 нужен панели (кто в игре, кик, объявления, режим обслуживания с киком, события 6038/6040, "
                        "рейтинги 6020, монстры) — панелью не выключается, только вручную владельцем" % (sec, key, new))
    mine = _set_items(ev)
    for user, keys, why in hard_deps(dll).get((dll, sec), []):
        if not off and (key not in keys or str(new) != "0"):
            continue
        if mine.get((dll, user.lower(), "enabled")) == "0":
            rep["warnings"].append("зависимый %s выключается этим же набором — %s" % (user, why))
            continue
        on = []
        for g in folders:
            t = ev.st.get(g, DLL_INI[dll][0])
            v = t.get(user, "Enabled")
            if v is not None and v.strip() not in ("0", ""):
                on.append(g)
        if on:
            raise OpRefused("[%s] %s=%s — от него зависит включённый %s (%s: %s) — выключите %s этим же набором или оставьте" % (
                sec, key, new, user, ", ".join(on), why, user))
    for (pdll, psec), users in hard_deps(dll).items():            # включение пользователя при выключенном поставщике — предупреждение
        if pdll != dll:
            continue
        for user, keys, why in users:
            if user == sec and key == "Enabled" and str(new) == "1":
                for g in folders:
                    pv = ev.st.get(g, DLL_INI[dll][0]).get(psec, "Enabled")
                    if pv is not None and pv.strip() == "0" and mine.get((dll, psec.lower(), "enabled")) != "1":
                        rep["warnings"].append("%s включается, а поставщик %s у %s выключен — %s" % (sec, psec, g, why))
    hard_users = {u for u, _k, _w in hard_deps(dll).get((dll, sec), [])}
    for s in catalog()["dlls"][dll]["sections"]:                  # мягкие зависимости по коду — сведения
        if s["name"] not in hard_users and sec in (s.get("needs") or {}) and off:
            rep["warnings"].append("код %s вызывает функции %s (%s) — проверьте, что без него он работает" % (
                s["name"], sec, ", ".join(s["needs"][sec][:3])))
        for f in s.get("reads_foreign") or []:                    # ★ ревизия 45 В-2: этот же ключ читает другой патч
            if f["section"] == sec and f["key"].lower() == key.lower() and not f.get("hard") and s["name"] != sec:
                rep["warnings"].append("ключ [%s] %s читает и %s (%s:%d) — правка меняет и его поведение" % (
                    sec, f["key"], s["name"], f["file"].split("/")[-1], f["line"]))


def k_patch_set(ev, p, rep):
    dll, scope = p["dll"], p["scope"]
    ini, fam = DLL_INI[dll]
    sec, k = find_key(dll, p["section"], p["key"])
    folders = copies(dll, scope)
    tg = _touch(ev, dll, sec["name"], k["key"], folders)
    ev.snap.extend([E.rel_of(g, ini) for g in folders])
    olds = {}
    cat_ver = catalog()["dlls"][dll].get("version")
    for g in folders:                                             # сначала проверка ВСЕХ копий — отказ до первой записи
        t = ev.st.get(g, ini)
        if not isinstance(t, IniTable):
            raise OpRefused("%s\\%s: не ini (движок взял %s) — правка не делается" % (g, ini, type(t).__name__))
        if t.bad:                                                 # ★ ревизия 45 Н-1
            raise OpRefused("%s\\%s: файл не собирается обратно байт в байт (кодировка %s) — правка переписала бы и чужие места" % (g, ini, t.bad))
        # ★ ревизия 45 С-5 / С-6: Version в ini пишет при старте сама DLL (MergeMissing → kVersion) — это версия ЖИВОЙ сборки. Каталог
        #   (тип, предел, зависимости) — по исходнику другой версии: проверка была бы по чужому коду, а выкладка новой DLL после набора
        #   переписала бы ini (MergeMissing) — откат набора стал бы невозможен. Порядок: сначала DLL отдельным рестартом, потом наборы.
        lv = (t.get("General", "Version") or "").strip()
        if cat_ver is not None and lv != str(cat_ver):
            if lv.isdigit() and int(lv) > int(cat_ver):
                raise OpRefused("%s\\%s: Version в ini %s (живая DLL) новее каталога панели (исходник Version %s) — каталог устарел, "
                                "выложите панель с исходником этой сборки, потом правьте настройки" % (g, ini, lv, cat_ver))
            raise OpRefused("%s\\%s: Version в ini %s (живая DLL), каталог панели — по исходнику Version %s — тип и предел ключа проверены "
                            "бы по чужой сборке, а выкладка новой DLL переписала бы ini после набора. Сначала выложите DLL Version %s "
                            "отдельным рестартом стойки, потом правьте настройки" % (g, ini, lv or "?", cat_ver, cat_ver))
        i, v, nh = t.find(sec["name"], k["key"])
        if nh == 0:
            raise OpRefused("%s\\%s: секции [%s] нет — живая DLL её не знает (Version %s), после выкладки её DLL допишет сама" % (
                g, ini, sec["name"], t.get("General", "Version")))
        if nh > 1:
            raise OpRefused("%s\\%s: секция [%s] встречается %d раза — правка неоднозначна, сначала уберите повтор вручную" % (
                g, ini, sec["name"], nh))
        if i is None:
            raise OpRefused("%s\\%s: ключа [%s] %s нет — живая DLL его не знает (Version %s)" % (g, ini, sec["name"], k["key"],
                                                                                              t.get("General", "Version")))
        olds[g] = v
    if all(v == p["value"] for v in olds.values()):
        raise OpRefused("[%s] %s=%s уже стоит во всех копиях (%s) — менять нечего" % (sec["name"], k["key"], p["value"], ", ".join(folders)))
    for g, v in olds.items():                                    # ★ ревизия 45 В-4: живое значение — адрес / путь / подключение
        why = view_only_why(k["key"], sec["name"], k, v)
        if why:
            raise OpRefused("ключ [%s] %s — только просмотр: %s" % (sec["name"], k["key"], why))
    off_val = off_by_value(k, p["value"])                         # ★ ревизия 45 В-3: значение выключает патч (P30 MaxMaps ≤ 23)
    off_val = off_val if off_val and any(off_by_value(k, v) is None for v in olds.values()) else None
    off = bool(off_val) or (k["key"].lower() == "enabled" and any(_is_off(v, p["value"]) for v in olds.values()))
    if k["key"].lower() == "masterenable" and str(p["value"]) == "0":
        off = True
    _deps_check(ev, dll, sec["name"], k["key"], p["value"], folders, rep, off)
    for g in folders:
        ev.st.get(g, ini).set(sec["name"], k["key"], p["value"])
        tg[(dll, sec["name"].lower(), k["key"].lower(), g)] = rep["pos"]
    was = sorted(set(olds.values()))
    rep["text"] = "%s [%s] %s: %s → %s (%s: %s; действует после рестарта стойки)" % (
        dll, sec["name"], k["key"], " / ".join(was), p["value"], ini, ", ".join(folders))
    if len(was) > 1:
        rep["warnings"].append("копии расходились: %s — станет одно значение" % ", ".join("%s=%s" % (g, v) for g, v in sorted(olds.items())))
    rep["warnings"].append("DLL читает %s только при старте процесса (DllMain: Config::Init → MergeMissing → установка) — действует после "
                           "рестарта стойки" % ini)
    unconfirmed = None                                            # ★ ревизия 45 С-1: предел не подтверждён — правка только сильная
    if not k.get("reads"):
        rep["warnings"].append("место чтения ключа %s поиском не найдено — тип по умолчанию шаблона (%s)" % (k["key"], k.get("type")))
        unconfirmed = "место чтения не найдено"
    elif k.get("lo") is None and k.get("hi") is None and k.get("type") in ("int", "mixed"):
        rep["warnings"].append("предел ключа %s в исходнике не найден — проверяется только целое (%s)" % (
            k["key"], ", ".join("%s:%d" % (r["file"], r["line"]) for r in k["reads"][:2])))
        unconfirmed = "целое без предела в коде"
    elif k.get("type") == "str" and not (sec["name"] == "P40_CrystalTeleportGate" and k["key"].lower() == "crystals"):
        rep["warnings"].append("строка ключа %s по грамматике патча не проверяется — только длина и управляющие символы" % k["key"])
        unconfirmed = "строка без проверки грамматики"
    if off_val:
        rep["warnings"].append(off_val)
    for f in [r for r in k.get("reads") or [] if r.get("foreign")][:3]:
        rep["warnings"].append("ключ читает и чужой патч (%s:%d)" % (f["file"].split("/")[-1], f["line"]))
    if sec["name"] == "P40_CrystalTeleportGate" and k["key"].lower() == "crystals":
        from domains.cs_kinds import mapdata
        if mapdata.parse_crystals(p["value"]) is None:
            raise OpRefused("[P40_CrystalTeleportGate] Crystals: строка не разбирается так, как её разбирает P40 (тип:карты,…;…) — патч не встал бы")
    strong, totp = [], False
    if k["key"].lower() == "masterenable":
        strong.append("MasterEnable — главный выключатель всех патчей %s" % dll)
        if str(p["value"]) == "0":
            totp = True
            if dll in MASTER_LOSS:
                strong.append("MasterEnable=0 — %s" % MASTER_LOSS[dll])
                rep["warnings"].append("MasterEnable=0 у %s — %s" % (dll, MASTER_LOSS[dll]))
    if k["key"].lower() == "enabled" and any(_is_off(v, p["value"]) for v in olds.values()):
        strong.append("выключение патча %s" % sec["name"])
        if sec["name"] == "L09_LoginMaintenance":
            strong.append("L09 Enabled=0 — режим обслуживания панели перестанет работать")
        totp = totp or strong_section(dll, sec)
    if off_val:
        strong.append("значение выключает патч %s (%s)" % (sec["name"], off_val))
    if k["key"].lower() == "mode":
        strong.append("смена режима %s (журнал / действует)" % sec["name"])
        totp = totp or str(p["value"]) == "0"
    if strong_section(dll, sec):
        strong.append("патч защиты / античита %s" % sec["name"])
    if unconfirmed:
        strong.append("предел не подтверждён (%s)" % unconfirmed)
    if strong:
        rep["_balance"] = [{"what": "%s [%s] %s — сильная правка: %s" % (dll, sec["name"], k["key"], why), "old": " / ".join(was), "new": p["value"],
                            "codes": [], "kind": "patch", "totp": totp} for why in strong]
    rep["_patchcfg"] = {"dll": dll, "section": sec["name"], "key": k["key"], "value": p["value"], "copies": folders, "rule": k.get("rule")}


def k_config_set(ev, p, rep):
    spec = CONFIGS[p["file"]]
    rule = next((v for (s, rx), v in spec["keys"].items() if s.lower() == p["section"].lower() and re.fullmatch(rx, p["key"], re.I)), None)
    if not rule:
        raise OpRefused("[%s] %s в %s панелью не правится (только %s)" % (p["section"], p["key"], p["file"], ", ".join(
            "[%s] %s" % (s, rx) for s, rx in spec["keys"])))
    lo, hi, what, where = rule
    if not re.match(r"^\d{1,6}$", p["value"]) or not lo <= int(p["value"]) <= hi:
        raise OpRefused("[%s] %s: целое %d…%d (%s)" % (p["section"], p["key"], lo, hi, what))
    folders = E.folders(spec["family"])
    ev.snap.extend([E.rel_of(g, p["file"]) for g in folders])
    if p["file"] == "ini\\Collection.ini":
        for g in folders:                                  # NpcServer читает CollectionTypeAniTime00…(N−1) — N по каждой копии
            n = E._int(ev.st.get(g, p["file"]).get("COLLECTION_INFO", "CollectionTypeCount") or "", 0)
            if int(p["key"][-2:]) >= n:
                raise OpRefused("%s: типов сбора %d (CollectionTypeCount) — NpcServer этот ключ не читает" % (p["key"], n))
    olds = {}
    for g in folders:
        t = ev.st.get(g, p["file"])
        i, v, nh = t.find(p["section"], p["key"])
        if i is None or nh != 1:
            raise OpRefused("%s\\%s: ключа [%s] %s нет (или секция повторяется) — новый ключ сервер всё равно не прочтёт" % (
                g, p["file"], p["section"], p["key"]))
        olds[g] = v
    if all(v == p["value"] for v in olds.values()):
        raise OpRefused("[%s] %s=%s уже стоит — менять нечего" % (p["section"], p["key"], p["value"]))
    for g in folders:
        ev.st.get(g, p["file"]).set(p["section"], p["key"], p["value"])
    rep["text"] = "%s [%s] %s: %s → %s (%s; после рестарта стойки)" % (p["file"], p["section"], p["key"], " / ".join(sorted(set(olds.values()))),
                                                                      p["value"], ", ".join(folders))
    rep["warnings"].append(COLLECTION_NOTE)
    rep["warnings"].append("клиент показывает свою анимацию сбора — сервер ждёт новое время, клиент — прежнее (проверьте копание глазами)")
    if E.is_strong(next(iter(olds.values())), p["value"]):
        rep["_balance"] = [{"what": "%s [%s] %s" % (p["file"], p["section"], p["key"]), "old": " / ".join(sorted(set(olds.values()))),
                            "new": p["value"], "codes": [], "kind": "value"}]


# =====================================================================================================================
# Ожидающие наборы с той же целью (cross_post)
# =====================================================================================================================
PENDING_SOURCE = None        # подмена самотеста: функция () → [{"id", "status", "server_state", "kind", "params"}]


def pending_items():
    """Позиции patch.set / config.set наборов, которые ещё не выложены (черновик / проверен / утверждён / сухой прогон)."""
    if PENDING_SOURCE is not None:
        return PENDING_SOURCE()
    import json
    from domains import shopcs
    # ★ ревизия 45 Н-2: и наборы с недоделанной выкладкой / откатом (partial / partial_apply / partial_rollback / unknown) — их цель
    #   ещё может лечь на стойку
    rows = shopcs._rows("SELECT c.id, c.status, c.server_state, i.kind, i.params FROM adm.changeset c JOIN adm.changeset_item i "
                        "ON i.changeset_id = c.id WHERE i.kind IN ('patch.set', 'config.set') AND c.status <> 'rolled_back' AND ("
                        "(c.status IN ('draft', 'checked', 'approved') AND c.server_state IN ('none', 'dry_srv', 'dry_ok')) OR "
                        "c.server_state IN ('partial', 'partial_apply', 'partial_rollback', 'unknown'))")
    return [dict(r, params=json.loads(r["params"])) for r in rows]


def _copies_of(p):
    """Копии цели позиции patch.set (охват) → множество папок; неизвестное — все копии DLL (пересечение считается)."""
    try:
        return set(copies(str(p.get("dll")), str(p.get("scope") or "all")))
    except Exception:
        try:
            return set(copies(str(p.get("dll")), "all"))
        except Exception:
            return set()


def _p69_check(ev):
    """★ ревизия 45 С-1: ступени P69 (Stage1…3 Count / Hours) по ИТОГУ набора — порог ≥ 1 и строго по возрастанию, срок ≠ 0 и ≥ -1;
    иначе P69 молча берёт ВСЕ умолчания (p69_integrity_autoblock.cpp:419-430)."""
    for r in ev.positions:
        if r["kind"] != "patch.set" or r["errors"]:
            continue
        pc = r.get("_patchcfg") or {}
        if pc.get("rule") != "p69_stages":
            continue
        d = {s["name"]: s for s in catalog()["dlls"][pc["dll"]]["sections"]}.get(pc["section"]) or {"keys": []}
        defs = {k["key"]: k["def"] for k in d["keys"]}
        for g in pc.get("copies") or []:
            t = ev.st.get(g, DLL_INI[pc["dll"]][0])
            vals = {}
            for n in ("Stage1Count", "Stage1Hours", "Stage2Count", "Stage2Hours", "Stage3Count", "Stage3Hours"):
                vals[n] = E._int(t.get(pc["section"], n) or defs.get(n) or "", 0)
            bad = []
            for i in (1, 2, 3):
                c, h = vals["Stage%dCount" % i], vals["Stage%dHours" % i]
                if c < 1:
                    bad.append("порог ступени %d < 1" % i)
                if i > 1 and c <= vals["Stage%dCount" % (i - 1)]:
                    bad.append("порог ступени %d не больше предыдущего" % i)
                if h == 0 or h < -1:
                    bad.append("срок ступени %d = %d" % (i, h))
            if bad:
                ev.errors.append("позиция %d: ступени P69 у %s станут негодны (%s) — P69 молча возьмёт ВСЕ умолчания 20/24, 50/720, 51/-1, "
                                 "поправьте ступени вместе одним набором" % (r["pos"], g, bad[0]))
                break


def cross_post(ev):
    _p69_check(ev)
    mine = [r for r in ev.positions if r["kind"] in KINDS and not r["errors"]]
    if not mine:
        return
    try:
        other = [x for x in pending_items() if x["id"] != getattr(ev, "cs_id", None)]
    except Exception as ex:
        ev.errors.append("ожидающие наборы с настройками патчей не прочитаны (%s) — пересечение не проверено, правка не делается" % str(ex)[:160])
        return
    for r in mine:
        p = r["params"]
        for x in other:
            q = x["params"]
            if x["kind"] != r["kind"]:
                continue
            if r["kind"] == "patch.set":
                same = (str(q.get("dll")), str(q.get("section", "")).lower(), str(q.get("key", "")).lower()) == (
                    str(p.get("dll")), str(p.get("section", "")).lower(), str(p.get("key", "")).lower()) \
                    and bool(_copies_of(p) & _copies_of(q))                     # ★ ревизия 45 Н-2: indun и field — разные копии
            else:
                same = (str(q.get("file")), str(q.get("section", "")).lower(), str(q.get("key", "")).lower()) == (
                    str(p.get("file")), str(p.get("section", "")).lower(), str(p.get("key", "")).lower())
            if not same:
                continue
            if str(q.get("value", "")).strip() != str(p.get("value", "")).strip():
                ev.errors.append("позиция %d: та же цель уже ждёт в наборе №%d («%s», значение %s) — сначала выложите или отмените его" % (
                    r["pos"], x["id"], x["status"], q.get("value")))
            else:
                ev.warnings.append("позиция %d: то же значение уже ждёт в наборе №%d («%s»)" % (r["pos"], x["id"], x["status"]))


def apply_guard(cs, mode):
    """Перед выкладкой / откатом: ожидающих наборов с той же целью и другим значением быть не должно (мог появиться после проверки)."""
    out = []
    if mode != "apply":
        return out
    try:
        other = [x for x in pending_items() if x["id"] != cs.get("id")]
    except Exception as ex:
        return ["ожидающие наборы с настройками патчей не прочитаны (%s)" % str(ex)[:160]]
    for it in cs.get("items") or []:
        if it["kind"] not in KINDS:
            continue
        p = it["params"]
        for x in other:
            q = x["params"]
            if x["kind"] == it["kind"] and all(str(q.get(f, "")).lower() == str(p.get(f, "")).lower() for f in ("dll", "file", "section", "key")) \
                    and (it["kind"] != "patch.set" or bool(_copies_of(p) & _copies_of(q))) \
                    and str(q.get("value", "")).strip() != str(p.get("value", "")).strip():
                out.append("позиция %d: та же цель ждёт в наборе №%d с другим значением (%s)" % (it["pos"], x["id"], q.get("value")))
    return out


# =====================================================================================================================
# Клиентской половины у области нет
# =====================================================================================================================
def snapshot(snap):
    """Клиентской половины у области нет."""


def parse(cli, d):
    """Клиентской половины у области нет."""


def divergence(ev, cli, sec):
    """Пары «поле — Ch2» ini DLL обязаны совпадать (паритет restart_stack)."""
    rows = []
    lay = E._layout()
    for dll, (ini, fam) in DLL_INI.items():
        if fam not in E.PAIR_FAMILIES and fam != "SDB":
            continue
        for twin, field in lay.TWINS.items():
            if twin in E.folders(fam) and field in E.folders(fam):
                a, b = ev.snap.md5.get(E.rel_of(twin, ini)), ev.snap.md5.get(E.rel_of(field, ini))
                if a and b and a != b:
                    rows.append({"id": twin, "why": "%s\\%s ≠ %s (%s ≠ %s) — restart_stack не запустит стойку (код 6)" % (twin, ini, field, a[:8], b[:8])})
    sec("patchcfg", "настройки патчей: пары «поле — Ch2» расходятся", rows, "Ch2 = поле побайтно (stack_parity)")
