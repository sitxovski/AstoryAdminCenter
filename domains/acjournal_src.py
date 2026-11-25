# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""acjournal_src.py — КАТАЛОГ видов журнала античита joylog1.ac.* по ИСХОДНИКУ (шаг А6.1 «Античит», 21.11.2026; разбор
Reports/admin_center/research_a6_economy_20261121.md §1, §3 строка А6.1; отчёт impl_a6_econ_20261121.md §А6.1).

В базе вид хранится ТОЛЬКО текстом (`event_kind` / `refusal_kind` / `logon_kind` / `check_result`), номер живёт в коде писателя
(AstoryServer/Docs/GameServer/ac-journal-p53.md §9). Источник правды для «текст → номер» — `KindText(table, kind)` общего модуля
журнала `AstoryServer/Patches/AsdaPatch/src/AcJournal.cpp` (собирается и в AddonNPC, DBPatch, LoginPatch — patchcfg_src.py, ревизия 45
С-1). Разбор: `case AcJournal::k<Таблица>:` → `case N: return L"текст";` и тернарные `return kind == 2 ? L"A" : L"B";`
(identity_mismatch, kick_block). Номер вида, который пишет только SQL (60, A11c), — из §9.1 (в коде номер не занят — `SQL_ONLY`).

Патч по номеру — диапазоны §9 / §9.1 и дописки к ним того же файла (`RANGES`, строка документа рядом). Служебная строка — сервер о себе,
а не действие игрока (`service_of`, у каждой причины — опора в §9 или в тексте вида). Каталог строится на ПК (исходник есть только там)
и кладётся выкладчиком службы в data/ref/ac_kinds.json (служба на сервере исходников не видит). Только чтение файлов.
Побочных эффектов при импорте нет.
"""
import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))       # AstoryAdminCenter
PORT = os.path.dirname(HERE)                            # port
SRC = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "src", "AcJournal.cpp")
CATALOG_REF = os.path.join(HERE, "data", "ref", "ac_kinds.json")

# enum AcJournal::Table (AcJournal.h:27–37) → имя таблицы joylog1.ac.*
TABLE_OF_ENUM = {"kOperatorRefusal": "operator_refusal", "kIdentityMismatch": "identity_mismatch", "kLoginCheck": "login_check_refusal",
                 "kKickBlock": "kick_block", "kSignReplay": "sign_replay", "kMoveCombat": "move_combat", "kOther": "other",
                 "kPacketValidator": "packet_validator"}
TABLES = tuple(TABLE_OF_ENUM.values())

# Виды, которые пишет только SQL (в KindText номера нет): ac-journal-p53.md §9.1 строка «ac.other 60 — A11c SQL CATCH»
SQL_ONLY = {("other", 60): "SQL: ошибка процедуры, откат (A11c)"}

# Патч по номеру вида — ac-journal-p53.md §9.1 (стр. 207–234 файла) и дописки после неё (P69 62, sec2 63–65, P72 76, P73 77–84, P76 85–87,
# P81 88–90, P82 91–93, P85 100–102, P87…P98, P100 153–157, P101 158–163, P102 164–167, P103 168–170, P110…P114, N24 177–180).
# sign_replay 1–5 — площадки стока P53 (§4, таблица «VA вызова»); operator_refusal / identity_mismatch — P47; login_check — P50; kick_block — P48 (§1).
RANGES = {
    "operator_refusal": [(1, 6, "P47")],
    "identity_mismatch": [(1, 2, "P47")],
    "login_check_refusal": [(1, 3, "P50")],
    "kick_block": [(1, 2, "P48")],
    "sign_replay": [(1, 5, "P53")],
    "packet_validator": [(1, 4, "P55")],
    "move_combat": [(1, 3, "P53"), (4, 5, "N13"), (6, 11, "P56"), (12, 13, "N14"), (14, 20, "P57"), (21, 22, "N15"), (23, 23, "P56b"),
                    (24, 30, "P66"), (103, 105, "N19")],
    "other": [(1, 3, "P53"), (4, 5, "P59"), (10, 14, "P53"), (20, 29, "P60"), (30, 34, "P62"), (35, 39, "P63"), (40, 44, "P64"),
              (45, 48, "P65"), (50, 52, "P67"), (53, 54, "P68"), (55, 55, "A13"), (56, 59, "В7d"), (60, 60, "A11c"), (61, 61, "fix2d"),
              (62, 62, "P69"), (63, 65, "sec2"), (66, 75, "P70"), (76, 76, "P72"), (77, 84, "P73"), (85, 87, "P76"), (88, 90, "P81"),
              (91, 93, "P82"), (100, 102, "P85"), (106, 108, "P87"), (109, 111, "P88"), (112, 114, "P89"), (115, 117, "N20"),
              (118, 120, "P91"), (121, 123, "P92"), (130, 132, "P94"), (140, 144, "P95"), (145, 147, "P96"), (150, 152, "P98"),
              (153, 157, "P100"), (158, 163, "P101"), (164, 167, "P102"), (168, 170, "P103"), (171, 173, "P110"), (174, 176, "P111"),
              (177, 180, "N24"), (181, 183, "P112"), (184, 184, "P114")],
}

# Служебные строки ac.other по номеру. ★ Ревизия 50 (п.1–2): служебной считается ТОЛЬКО строка, которая доказуемо не относится к действиям
#   учётки: строки самого журнала (старт, итоги, база), состояние сервера (мост EAC, выключение патча при старте), события без учётки.
#   Всё, что пишется на действии игрока (с учёткой), — НЕ служебное, даже если это исключение кода или ошибка SQL (NOT_SERVICE_WHY ниже).
SERVICE_OTHER = {
    10: "§9: строка самого журнала (старт)", 11: "§9: строка самого журнала (отброшено)", 12: "§9: строка самого журнала (база недоступна)",
    13: "§9: строка самого журнала (база снова доступна)", 14: "§9: строка самого журнала (очистка)",
    61: "§9.1 fix2d: кадр не доставлен сервером — без учётки (dev 21.11: 61 строка, user_index пуст), не нарушение клиента",
    77: "§9 P73: мост EAC подключён — состояние сервера", 78: "§9 P73: мост EAC потерян — состояние сервера",
    82: "§9 P73: очередь моста EAC переполнена — состояние сервера", 84: "§9 P73: нарушение протокола моста сайдкаром — сервер о сервере",
    100: "§9 P85: корзина передана шлюзу gp7 — без учётки (dev 21.11: 253 строки, user_index пуст)",
    157: "§9 P100: патч выключен при старте", 163: "§9 P101: патч выключен или настройка исправлена при старте",
}

# ★ Ревизия 50: виды, которые раньше скрывались как служебные, — теперь события учётки; у каждого причина (пишутся на действии игрока)
NOT_SERVICE_WHY = {
    60: "A11c / A14: CATCH процедуры предметов и премиум-почты на действии игрока (dev 21.11: 102 из 102 строк с учёткой; повтор ключа PK_Item_1, переполнения) — возможный след гонки или дюпа",
    91: "P82: восстановление отката предмета персонажа (вход / портал) — строка персонажа", 92: "P82: сохранение отката предмета персонажа — строка персонажа",
    93: "P82: таблица откатов персонажа заполнена (применение 5450 / ответ БД / восстановление) — строка персонажа",
    102: "P85: список премиум-почты игрока больше 49 записей — ответ на запрос игрока",
    108: "P87: исключение при выдаче навыков 4-й профессии — на смене профессии игрока",
    111: "P88: исключение в событии звания — на действии игрока", 114: "P89: исключение в гейте 4-й профессии — на изучении навыка игроком",
    116: "N20: исключение при зажиме доли отряда — на убийстве монстра отрядом игрока", 119: "P91: исключение при потолке опыта — на убийстве монстра игроком",
    123: "P92: исключение при сверке отношения — на навыке игрока", 132: "P94: исключение при сверке получателя сообщения пары — на сообщении игрока",
    144: "P95: исключение при сверке предмета или коробки — на использовании предмета игроком",
    152: "P98: исключение при сверке шаблона премиум-почты — на получении почты игроком",
    156: "P100: расхождение памяти и БД / исключение при слиянии — перемещение предмета игроком, пока запрос в БД в полёте (dev 21.11: 5 из 5 с учёткой)",
    166: "P102: исключение при исправлении — на действии игрока", 170: "P103: исключение при исправлении — на действии игрока",
    173: "P110: исключение при проверке пулов очков — на изучении навыка игроком",
    175: "P111: исключение при проверке добавки вылупления — на вылуплении питомца игроком",
    180: "N24: исключение при проверке лута — на убийстве монстра игроком", 183: "P112: исключение при расчёте разброса отряда — на опыте отряда игрока",
    184: "P114: исключение при усилении опыта задания доски — на сдаче задания игроком",
}
SERVICE_PREFIX = "журнал:"          # текст не из каталога: строка самого журнала (сравнение без учёта регистра — как LIKE в CI-сортировке)

# ★ Ревизия 50 (п.3): 145–147 выданы P96 в реестре (ac-journal-p53.md §9), но P96 их НЕ пишет — в p96_inventory_x2.cpp:73–75 только
#   неиспользуемые константы (ни AcJournal::Clear, ни Push в файле нет); в KindText их нет. Строка «?» — вид без текста (теоретически:
#   номер, не заведённый в KindText); у живой базы таких строк нет.
UNKNOWN_TEXT = "?"
UNKNOWN_HINT = "вид без текста в KindText (номер, не заведённый в каталоге видов) — номер по базе не восстановить"


def patch_of(table, n, text=None):
    """Патч вида: по диапазону номеров §9; без номера — по началу текста («P73: …», «N24: …», «… (P56)»)."""
    if n is not None:
        for lo, hi, p in RANGES.get(table, ()):
            if lo <= n <= hi:
                return p
    if text:
        m = re.match(r"(P\d+[a-z]?|N\d+|L\d+|В7d|sec2|fix2d)\b", text) or re.search(r"\((P\d+[a-z]?|N\d+)\)\s*$", text)
        if m:
            return m.group(1)
    return None


def service_of(table, n, text):
    """Причина «служебная строка» или None (нарушение / событие игрока)."""
    if table == "other" and n in SERVICE_OTHER:
        return SERVICE_OTHER[n]
    if n is None and text and text.lower().startswith(SERVICE_PREFIX):   # так считает и AstoryServer/Tools/Anticheat/ac_daily_report («служебные «журнал:»»)
        return "§9: строка самого журнала"
    return None


_CASE_T = re.compile(r"^\s*case\s+AcJournal::(k\w+)\s*:")
_CASE_N = re.compile(r'^\s*case\s+(\d+)\s*:\s*return\s+L"([^"]*)"\s*;')
_TERN = re.compile(r'^\s*return\s+kind\s*==\s*(\d+)\s*\?\s*L"([^"]*)"\s*:\s*L"([^"]*)"\s*;')


def parse(text):
    """Тело KindText → {таблица: {номер: текст}}; [(строка, причина)] нераспознанного внутри функции."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(r"const\s+wchar_t\*\s+KindText\s*\(\s*int\s+table\s*,\s*int\s+kind\s*\)", ln)), None)
    if start is None:
        raise ValueError("в AcJournal.cpp нет KindText(int table, int kind)")
    out, bad, table = {}, [], None
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if re.match(r"^    }\s*$", ln):                           # конец функции (отступ 4 — тело namespace)
            break
        m = _CASE_T.match(ln)
        if m:
            table = TABLE_OF_ENUM.get(m.group(1))
            if table is None:
                bad.append((i + 1, "неизвестная таблица %s" % m.group(1)))
            out.setdefault(table, {})
            continue
        m = _CASE_N.match(ln)
        if m and table:
            n = int(m.group(1))
            if n in out[table]:
                bad.append((i + 1, "номер %d в %s повторён" % (n, table)))
            out[table][n] = m.group(2)
            continue
        m = _TERN.match(ln)
        if m and table:
            k = int(m.group(1))
            out[table][k] = m.group(2)
            out[table][1 if k != 1 else 2] = m.group(3)
            continue
        if 'L"' in ln and not ln.strip().startswith("//") and "return L\"?\"" not in ln:
            bad.append((i + 1, "строка с текстом не разобрана"))
    else:
        raise ValueError("KindText не закрыта")
    return out, bad


def build(path=SRC):
    """Каталог из исходника: {source, md5, tables: {таблица: [{n, text, patch, service}]}, problems}."""
    with open(path, "rb") as f:
        raw = f.read()
    kinds, bad = parse(raw.decode("utf-8-sig"))
    for (t, n), txt in SQL_ONLY.items():
        if n in kinds.get(t, {}):
            bad.append((0, "номер %d в %s занят и в коде, и в SQL_ONLY" % (n, t)))
        kinds.setdefault(t, {})[n] = txt
    tables, dup = {}, []
    for t in TABLES:
        rows, seen = [], {}
        for n in sorted(kinds.get(t, {})):
            txt = kinds[t][n]
            if txt in seen:
                dup.append("%s: текст номеров %d и %d одинаков" % (t, seen[txt], n))
            seen[txt] = n
            rows.append({"n": n, "text": txt, "patch": patch_of(t, n, txt), "service": service_of(t, n, txt),
                         "sql": (t, n) in SQL_ONLY})
        tables[t] = rows
    return {"source": os.path.relpath(path, PORT).replace("\\", "/"), "md5": hashlib.md5(raw).hexdigest(), "tables": tables,
            "problems": ["стр. %d: %s" % b for b in bad] + dup}


def load(prefer_source=True):
    """Каталог: на ПК (есть исходник) — из исходника; иначе (служба) — data/ref/ac_kinds.json."""
    # ★ ревизия 57 Н-3: на сервере SRC = H:\Server\… вне дерева службы — только справочник выкладки data/ref
    from core import config
    if prefer_source and not config.get().on_server and os.path.isfile(SRC):
        return build()
    with open(CATALOG_REF, encoding="utf-8") as f:
        return json.load(f)


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    if args in (["--help"], ["-h"]):
        print("acjournal_src.py [--summary] — каталог видов журнала античита ac.* по AcJournal.cpp KindText (только чтение, ничего не пишет; "
              "data/ref/ac_kinds.json кладёт только выкладчик службы в архив)")
        return 0
    if args not in ([], ["--summary"]):            # ★ ревизия 50 п.10: --write убран (файл на ПК не читается, а в архиве дал бы дубль записи)
        print("неизвестный ключ: %s" % " ".join(args))
        return 1
    cat = build()
    for t, rows in cat["tables"].items():
        print("%-20s видов %3d, служебных %2d, без патча %d" % (t, len(rows), sum(1 for r in rows if r["service"]),
                                                                sum(1 for r in rows if not r["patch"])))
        if args != ["--summary"]:
            for r in rows:
                print("   %4d %-6s %s %s" % (r["n"], r["patch"] or "?", "С" if r["service"] else " ", r["text"][:110]))
    for p in cat["problems"]:
        print("ПРОБЛЕМА:", p)
    return 1 if cat["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
