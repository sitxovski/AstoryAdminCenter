# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/skilldata.py — область «Навыки и классы» (волна А4.7, 20.11.2026; разбор Reports/admin_center/research_a4_data.md §1.4,
§3, §5; навыки — research_skills_pets.md A.2–A.5; уровень и характеристики — research_level_job.md).

Только правка СУЩЕСТВУЮЩИХ записей (решение владельца 19.11): навыков, классов, уровней и строк не добавляется, номера не меняются,
размер файлов не меняется. Правятся ТОЛЬКО поля, которые сервер читает (декомпил), остальное — отказ «смысл не подтверждён».

НАВЫКИ — SkillInfo.sif, запись 209 б, индекс записи = номер навыка (у всех 1120 записей +0 i16 = индекс), навыки игроков — 500…N−1 с маской
классов +123 ≠ 0 (454 на dev). ШЕСТЬ копий одной базы (dev 20.11 у всех 1ACB5EAA): GameServer\\SkillTable_Info\\SkillInfo.sif ×3 (загрузчик
GameServer.c:71562) и NpcServer\\Skill\\Skillinfo.sif ×3 (NpcServer.exe.c:10068 открывает «.//Skill//SkillInfo.sif»; NpcServer считает по нему
эффект навыка игрока по мобу — NpcServer.exe.c:12578…12587, 12719…12728). Политика per_copy: правка ложится на каждую копию по её байтам,
у копии с другим прежним значением поля — отказ (отличия не затираются).
  skill.num — числа уровня. Сервер (sub_4760E0 GameServer.c:47924…47953, начальный уровень — sub_475650 :47788…47819, уровень 0 —
     sub_475F20 :47865): +47 i32 откат, +53 u8 дальность (ещё IsCheckAreaMember sub_473360 :47078), +55 u8 область, +58/+60 i16 расход MP
     (база / шаг на уровень; < 0 → 0), +62/+64 i16 сила Evalue, +66/+67 u8 шанс SkillPer (> 100 → 100), +68/+69 u8 шанс SubSkillPer
     (> 100 → 100), эффекты 1–3: +74/+76 i16 значение, +78/+82 i32 длительность (+91/+93, +95/+99; +108/+110, +112/+116); значение
     уровня N = N·шаг + база (16/8/32 бита — перенос через край отказом). Эффект k без состояния (+72/+89/+106 < 0) — значения не
     применяются (sub_477F60 :48580 / sub_479220 :48953 берут состояние оттуда; в живой таблице значений у пустого эффекта нет) — отказ.
     ПАРА: клиент порта skill_info.csv (DataHex 273 б, байты +41…+208 = серверной записи у всех 454 навыков игроков — второй метод 20.11;
     читает AsdaSkillDatabase.cpp те же смещения) + ведомость _value_overlay/skill_info.sif.csv (поля decode_item_db ledger_fields).
     ⚠ Изученный навык держит числа своего уровня в Joy1.dbo.CharSkill (вход в мир берёт их как есть — sub_475290 :47713), новые числа
     игрок получит при следующем повышении навыка или сбросе; часть путей эффекта (sub_479220) берёт значения из таблицы по уровню сразу.
  skill.req — +43 u8 максимальный уровень (повышение 5253 Recv_SkillPoint_SkillActive :48345, код 2) и +190 u8 «нужно вложить в дерево»
     (там же, код 6; открытие «следующих» sub_47E9B0 :50826). ПАРА: клиент MaxLevel +43, GradeNum +190 (AsdaSkillDatabase.cpp).
     Изученное игроками (Joy1.dbo.CharSkill, только чтение) не делается невалидным: макс. уровень ниже уровня держателя — ОТКАЗ;
     ниже уровня, на котором этот навык открывает «следующий» (+193/+196/+199) или нужен предшественником (+202/+205/+208), — ОТКАЗ;
     +190 из 0 в > 0 у навыка с держателями — ОТКАЗ (сброс дерева sub_480F20 :51264 и полный сброс sub_4803A0 / UPCharSkillinit ac0x по
     Joy1.dbo.AsdaSkillBase.Need удаляют такой навык, а стартовые навыки сервер выдаёт только при смене профессии); смена 0 ↔ > 0 —
     сильная всегда (type); рост требования выше вложенного у держателей — предупреждение со списком.
  ПОСЛЕ ВЫКЛАДКИ И ОТКАТА: Joy1.dbo.AsdaSkillBase (ac0x: Need и 13 полей уровня 0, по ним UPCharSkillinit сохраняет навыки при полном
     сбросе) приводится к живому SkillInfo.sif (after_server; asda_ops — UPDATE этих столбцов).
ОЧКИ ДЕРЕВА — SkillTable_Info\\SkillPointTable.spt (14 б: +0 i8 дерево, +1 i8 порог, 6 × i16 навыков; загрузчик :71620, NpcServer его не
  читает — строки нет в NpcServer.exe). skill.spt — порог: навыки строки выдаются, когда сумма дерева СТАЛА РАВНА порогу (sub_47E9B0 :50845,
  первая подходящая строка — break), проверки «уже изучен» там НЕТ — sub_475650 + 2102 UPSkillAdd ставят уровень 0. Поэтому: снижение
  порога, при котором у персонажа сумма уже в [новый, прежний) и навыка строки нет, — ОТКАЗ (не получит никогда); повышение, при котором
  у персонажа сумма в [прежний, новый) и навык строки уже с уровнем > 0, — ОТКАЗ (на новом пороге уровень обнулится); строка с тем же
  деревом и порогом — ОТКАЗ (одна из них не сработает). Только сервер (GS ×3).
КЛАССЫ — ConfigSet\\ClassStat.txt (N, затем записи «класс уровень Str Agi Hea Spe Men For», загрузчик sub_4AC850 :69181, __int16): база
  характеристик = ClassStat[Class][Lvl] — при повышении (sub_43AF30 :81069) и ЗАНОВО при каждом входе (CharMake → sub_548B20 :124113).
  class.stat — только сервер (клиент получает характеристики от сервера).
ОПЫТ — ConfigSet\\ExpTable.txt (N, затем «уровень опыт», запись i = уровень i по позиции, sub_4AC640 :69114). level.exp — накопленный опыт
  начала уровня L; строго растёт (P75_ExpTableGrows и повышение по одному уровню). ПАРА: клиент charexp.csv (строка L−1: CumExp/Zero2 —
  int64, ExpToNext строк L−1 и L — разность, с 68-й строки делённая на 40; asda_charexp_sync.py) + ведомость _value_overlay/charexp.csv.
  Персонаж уровня L с опытом ниже нового порога — ОТКАЗ.
Ни один AsdaPatch не переписывает эти поля в памяти (сверено по исходникам 20.11: P110 читает +0xBD дерево, P92 — +52 враждебность, P29
  — длину ExpTable/ClassStat, P75 — ExpTable[TargetLevel]); длины таблиц панель не меняет.
НЕ ПРАВЯТСЯ (смысл/структура): вид +42, пассив +44, цель/враждебность +52, +54, элемент/группа состояния +70/+71, состояния эффектов
  +72/+89/+106 и их такт/вид, маски +123/+131/+143/+151, список +167, +184/+185, дерево +189, связи «следующий»/предшественник +191…+208;
  стартовые навыки ChangeJobAddSkillTable (строки 1/12/23 = шаблоны dbo.Fighter/Ranger/Mage, строки подклассов — P87/P89), списки
  SkillMaxPointTable, PassiveSkillEffectTable, навыки мобов (MonsterSkill — область монстров, в А4.3 не вошли).
Перед выкладкой и откатом опасные переходы (держатели, суммы деревьев, опыт) ПЕРЕЧИТЫВАЮТСЯ (apply_guard) по итоговому состоянию
«живая + файлы набора» / «живая, файлы набора — базой». Побочных эффектов при импорте нет.
"""
import os
import struct

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "skilldata", "Навыки и классы"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
SIF_GS, SIF_NPC = "SkillTable_Info\\SkillInfo.sif", "Skill\\Skillinfo.sif"
SPT = "SkillTable_Info\\SkillPointTable.spt"
CSTAT, EXPT = "ConfigSet\\ClassStat.txt", "ConfigSet\\ExpTable.txt"
SRV_FILES = [("GS", SIF_GS, "per_copy"), ("NPC", SIF_NPC, "per_copy"), ("GS", SPT, "per_copy"), ("GS", CSTAT, "per_copy"),
             ("GS", EXPT, "per_copy")]
CLI_SKILL, CLI_EXP = "skill_info.sif", "charexp"           # ключи = имена записей архива (ведомости decode_item_db)
CLIENT_FILES = {CLI_SKILL: os.path.join(E.ITEMDB, "skill_info.csv"), CLI_EXP: os.path.join(E.ITEMDB, "charexp.csv")}
DT = {CLI_SKILL: "/Game/AsdaAssets/Data/ItemDB/DT_skill_info", CLI_EXP: "/Game/AsdaAssets/Data/ItemDB/DT_charexp"}
IMPORTERS = {}
CSV_KEYS = (CLI_SKILL, CLI_EXP)

REC, SKILL_MIN = 209, 500
CLI_FROM = 41                                    # байты клиента +41…+208 = серверной записи (сверка 20.11)
SPT_REC = 14
STUBS = {608, 814, 1025, 1028, 1032, 1037}       # имя «-» и в сервере, и в клиенте (research_skills_pets.md A.2)
DIV40_FROM = 68                                  # charexp: с этой строки ExpToNext делён на 40 (asda_charexp_sync.py)
NO_JOY1 = "нет связи с Joy1"
TOP = {"<B": 255, "<h": 32767, "<i": 2147483647}
# поле → (смещение, формат, подпись, поле ведомости клиента)
NUM = {
    "cool": (47, "<i", "откат, мс", "cooldownMs"), "dist": (53, "<B", "дальность", "rangeMeters"),
    "scope": (55, "<B", "область", "aoeRadius"),
    "mp0": (58, "<h", "расход MP: база", "mpBase"), "mpN": (60, "<h", "расход MP: за уровень", "mpPerLevel"),
    "ev0": (62, "<h", "сила: база", "msBase"), "evN": (64, "<h", "сила: за уровень", "msPerLevel"),
    "sp0": (66, "<B", "шанс навыка, %: база", "skillPerBase"), "spN": (67, "<B", "шанс навыка: за уровень", "skillPerPerLevel"),
    "ssp0": (68, "<B", "шанс эффекта, %: база", "srBase"), "sspN": (69, "<B", "шанс эффекта: за уровень", "srPerLevel"),
    "s1v0": (74, "<h", "эффект 1: значение, база", "s1Base"), "s1vN": (76, "<h", "эффект 1: значение за уровень", "s1PerLevel"),
    "s1t0": (78, "<i", "эффект 1: длительность, мс, база", "buff0Duration"),
    "s1tN": (82, "<i", "эффект 1: длительность за уровень", "buff0DurPerLevel"),
    "s2v0": (91, "<h", "эффект 2: значение, база", "s2Base"), "s2vN": (93, "<h", "эффект 2: значение за уровень", "s2PerLevel"),
    "s2t0": (95, "<i", "эффект 2: длительность, мс, база", "buff1Duration"),
    "s2tN": (99, "<i", "эффект 2: длительность за уровень", "buff1DurPerLevel"),
    "s3v0": (108, "<h", "эффект 3: значение, база", "s3Base"), "s3vN": (110, "<h", "эффект 3: значение за уровень", "s3PerLevel"),
    "s3t0": (112, "<i", "эффект 3: длительность, мс, база", "buff2Duration"),
    "s3tN": (116, "<i", "эффект 3: длительность за уровень", "buff2DurPerLevel"),
}
REQ = {"max": (43, "<B", "макс. уровень", "maxLevel"), "need": (190, "<B", "нужно очков в дереве", "needPoints")}
SLOT_STATE = {1: 72, 2: 89, 3: 106}              # i16 состояние эффекта k (−1 — эффекта нет)
SLOT_FIELDS = {k: tuple(f % k for f in ("s%dv0", "s%dvN", "s%dt0", "s%dtN")) for k in SLOT_STATE}
# значение уровня N = N·шаг + база (sub_4760E0): (имя, база, шаг, формат, зажим)
LEVEL = (("mp", "mp0", "mpN", "<h", "0"), ("ev", "ev0", "evN", "<h", ""), ("sp", "sp0", "spN", "<B", "100"), ("ssp", "ssp0", "sspN", "<B", "100"),
         ("s1v", "s1v0", "s1vN", "<h", "0"), ("s1t", "s1t0", "s1tN", "<i", "0"), ("s2v", "s2v0", "s2vN", "<h", "0"),
         ("s2t", "s2t0", "s2tN", "<i", "0"), ("s3v", "s3v0", "s3vN", "<h", "0"), ("s3t", "s3t0", "s3tN", "<i", "0"))
LEVEL_LABEL = {"mp": "расход MP", "ev": "сила", "sp": "шанс навыка", "ssp": "шанс эффекта", "s1v": "эффект 1: значение",
               "s1t": "эффект 1: длительность", "s2v": "эффект 2: значение", "s2t": "эффект 2: длительность", "s3v": "эффект 3: значение",
               "s3t": "эффект 3: длительность"}
STATS = (("str", "Сила"), ("agi", "Ловкость"), ("hea", "Здоровье"), ("spe", "Заклинания"), ("men", "Разум"), ("for", "Удача"))
CLASSES = {0: "новичок", 1: "боец", 2: "лучник", 3: "маг"}
# база AsdaSkillBase (ac0x) ← поля записи
BASE_COLS = (("Need", 190, "<B"), ("Cooltime", 47, "<i"), ("Distance", 53, "<B"), ("Scope", 55, "<B"), ("Mpvalue", 58, "<h"),
             ("Evalue", 62, "<h"), ("SkillPer", 66, "<B"), ("SubSkillPer", 68, "<B"), ("SubValue1", 74, "<h"), ("SubTime1", 78, "<i"),
             ("SubValue2", 91, "<h"), ("SubTime2", 95, "<i"), ("SubValue3", 108, "<h"), ("SubTime3", 112, "<i"))
EXP_MAX = (1 << 62)

KINDS = {
    "skill.num": ("Навык: числа уровня (SkillInfo.sif +47…+116 — откат, дальность, область, MP, сила, шансы, эффекты; пара с skill_info)",
                  ("id", "fields"), False),
    "skill.req": ("Навык: макс. уровень и требование дерева (SkillInfo.sif +43, +190; пара с skill_info)", ("id", "fields"), False),
    "skill.spt": ("Очки дерева: порог открытия навыков (SkillPointTable.spt +1, только сервер)", ("row", "sum"), False),
    "class.stat": ("Класс: базовые характеристики уровня (ClassStat.txt, только сервер)", ("cls", "lvl", "fields"), False),
    "level.exp": ("Уровень: опыт начала уровня (ExpTable.txt + charexp клиента)", ("lvl", "exp"), False),
}


def rng_num(k):
    return (0, TOP[NUM[k][1]])


def rng_req(k):
    return (1, 255) if k == "max" else (0, 255)


def rng_stat(_k):
    return (0, 32767)


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def norm(kind, p):
    from domains.cs_kinds.questtables import _fields
    if kind in ("skill.num", "skill.req"):
        sid = E._ival(p, "id", SKILL_MIN, 32767)
        return {"id": sid, "fields": _fields(p, tuple(NUM), rng_num) if kind == "skill.num" else _fields(p, tuple(REQ), rng_req)}
    if kind == "skill.spt":
        return {"row": E._ival(p, "row", 0, 100000), "sum": E._ival(p, "sum", 1, 127)}
    if kind == "class.stat":
        return {"cls": E._ival(p, "cls", 0, 3), "lvl": E._ival(p, "lvl", 1, 32767), "fields": _fields(p, tuple(k for k, _n in STATS), rng_stat)}
    return {"lvl": E._ival(p, "lvl", 2, 32767), "exp": E._ival(p, "exp", 1, EXP_MAX)}


def target_key(kind, p):
    if kind in ("skill.num", "skill.req"):
        return "skill:%d:%s" % (p["id"], kind.split(".")[1])
    if kind == "skill.spt":
        return "spt:%d" % p["row"]
    if kind == "class.stat":
        return "cstat:%d:%d" % (p["cls"], p["lvl"])
    return "exp:%d" % p["lvl"]


# =====================================================================================================================
# Записи навыков
# =====================================================================================================================
def sif_copies():
    """Шесть копий SkillInfo.sif: (копия, подпуть); первая — поле (GameServer)."""
    return [(g, SIF_GS) for g in E.GS] + [(n, SIF_NPC) for n in E.folders("NPC")]


def rec_off(buf, sid, where):
    if len(buf) % REC:
        raise OpRefused("%s: размер %d не кратен 209 — раскладка записей не доказана, правка не делается" % (where, len(buf)))
    n = len(buf) // REC
    if not SKILL_MIN <= sid < n:
        raise OpRefused("навыка %d нет в %s (навыки 500…%d) — в А4 только правка существующих" % (sid, where, n - 1))
    off = sid * REC
    if struct.unpack_from("<h", buf, off)[0] != sid:
        raise OpRefused("%s: у записи %d номер %d — номер навыка = позиция записи, правка не делается"
                        % (where, sid, struct.unpack_from("<h", buf, off)[0]))
    return off


def vals(buf, off):
    """Поля записи навыка (по байтам buf с записью по смещению off)."""
    v = {k: struct.unpack_from(f, buf, off + o)[0] for k, (o, f, _l, _c) in list(NUM.items()) + list(REQ.items())}
    i16 = lambda o: struct.unpack_from("<h", buf, off + o)[0]
    v.update({"mask": struct.unpack_from("<Q", buf, off + 123)[0], "kind": buf[off + 42], "passive": buf[off + 44], "tree": buf[off + 189],
              "st": [i16(SLOT_STATE[k]) for k in (1, 2, 3)], "next": [(i16(o), buf[off + o + 2]) for o in (191, 194, 197)],
              "req": [(i16(o), buf[off + o + 2]) for o in (200, 203, 206)],
              "name": bytes(buf[off + 2:off + 42]).split(b"\0", 1)[0].decode("cp949", "replace")})
    return v


def is_player(v, sid):
    return bool(v["mask"]) and sid not in STUBS and v["name"].strip() != "-"


def level_raw(v, n):
    """Значения уровня n до зажимов сервера: {имя: число} (python int — без переноса)."""
    return {nm: n * v[s] + v[b] for nm, b, s, _f, _c in LEVEL}


def level_row(v, n):
    """Значения уровня n, как их кладёт sub_4760E0 (перенос через край — как у сервера, зажимы < 0 → 0 и > 100 → 100)."""
    out = {}
    for nm, b, s, f, c in LEVEL:
        raw = n * v[s] + v[b]
        bits = {"<B": 8, "<h": 16, "<i": 32}[f]
        x = raw & ((1 << bits) - 1)
        if f != "<B" and x >= 1 << (bits - 1):
            x -= 1 << bits
        if c == "0" and x < 0:
            x = 0
        if c == "100" and x > 100:
            x = 100
        out[nm] = x
    return out


def users_of(buf, sid):
    """Навыки таблицы, которым sid — предшественник (+200…+208): [(навык, нужный уровень)]."""
    out = []
    for r in range(SKILL_MIN, len(buf) // REC):
        for o in (200, 203, 206):
            if struct.unpack_from("<h", buf, r * REC + o)[0] == sid:
                out.append((r, buf[r * REC + o + 2]))
    return out


def issues(sid, v, buf=None):
    """Неисправности записи навыка игрока, которые сервер читает (итоговое состояние) → {код: текст}."""
    out = {}
    mx = v["max"]
    if v["mask"] and mx == 0:
        out["max0"] = "макс. уровень 0 у навыка игрока — повысить его нельзя (5254 код 2)"
    for nm, b, s, f, _c in LEVEL:
        for n in range(mx + 1):
            raw = n * v[s] + v[b]
            if raw > TOP[f]:
                out["ovf_" + nm] = ("%s на уровне %d = %d — больше предела поля (%d): sub_4760E0 записал бы перенос через край"
                                    % (LEVEL_LABEL[nm], n, raw, TOP[f]))
                break
    for k in (1, 2, 3):
        if v["st"][k - 1] < 0 and any(v[f] for f in SLOT_FIELDS[k]):
            out["slot%d" % k] = ("эффект %d: состояния нет (+%d = %d), а значения заданы — сервер их не применяет"
                                 % (k, SLOT_STATE[k], v["st"][k - 1]))
    for nid, lv in v["next"]:
        if nid >= 0 and lv > mx:
            out["next%d" % nid] = ("навык %d открывается на уровне %d этого навыка (+191…+199), а макс. уровень %d — не откроется никогда"
                                   % (nid, lv, mx))
    if buf is not None:
        for r, lv in users_of(buf, sid):
            if lv > mx:
                out["user%d" % r] = ("навыку %d нужен этот навык уровня %d (+200…+208), а макс. уровень %d — тот не откроется никогда"
                                     % (r, lv, mx))
    return out


def skill_label(sid):
    from domains import skills as SK
    return "%d «%s»" % (sid, SK.skill_name(sid))


# =====================================================================================================================
# Персонажи (Joy1, только чтение)
# =====================================================================================================================
DEL_MARK = "Del_Charinfo"                         # метка набора корзины в имени (латиницей — одинаково в RU и EN)
# ★ ревизия 39 С-1: невосстановленные наборы корзины (Del_Charinfo / Del_CharSkill без строки adm.CharRestored; ключ набора — Userindex,
#   Charidx, Edate) — adm.CharRestore (sql/adminc_05_restore.sql) возвращает их CharSkill и Charinfo КАК ЕСТЬ, поэтому они — такие же
#   держатели для всех проверок (макс. уровень, опыт уровня, суммы дерева SPT). Чтение — asda_admin (db_datareader Joy1).
_DEL_CHARS = ("SELECT d.Userindex AS u, d.Charidx AS c, CONVERT(varchar(23), d.Edate, 121) AS ek, d.Charname AS nm, d.Lvl AS lv, d.Expe AS ex, "
              "d.Class AS cl, d.Job AS jb, d.Subjob AS sb FROM dbo.Del_Charinfo d WHERE NOT EXISTS (SELECT 1 FROM adm.CharRestored r "
              "WHERE r.Userindex = d.Userindex AND r.Charidx = d.Charidx AND r.Edate = d.Edate)")
_DEL_SKILLS = ("SELECT d.Userindex AS u, d.Charidx AS c, CONVERT(varchar(23), d.Edate, 121) AS ek, d.Skillidx AS s, d.Lvl AS lv "
               "FROM dbo.Del_CharSkill d WHERE NOT EXISTS (SELECT 1 FROM adm.CharRestored r WHERE r.Userindex = d.Userindex "
               "AND r.Charidx = d.Charidx AND r.Edate = d.Edate)")


def _char(r, deleted=None):
    nm = r["nm"] or ""
    return {"name": ("%s [%s %s]" % (nm, DEL_MARK, deleted[:16])) if deleted else nm, "lvl": int(r["lv"] or 0), "exp": int(r["ex"] or 0),
            "cls": int(r["cl"] or 0), "job": int(r["jb"] or 0), "sub": int(r["sb"] or 0), "skills": {}, "deleted": deleted}


def joy_chars():
    """{ключ: {"name", "lvl", "exp", "cls", "job", "sub", "skills": {навык: уровень}, "deleted"}} или None (причина — last_error).
    Ключ — (учётка, персонаж) у живых и (учётка, персонаж, Edate) у невосстановленных наборов корзины (их имя — с меткой
    «[Del_Charinfo дата]», deleted = Edate): восстановление вернёт их навыки и опыт как есть (ревизия 39 С-1)."""
    joy_chars.last_error = None
    try:
        from core import db
        with db.GameReader("joy1") as j:
            ch = j.rows("SELECT Userindex AS u, Charidx AS c, Charname AS nm, Lvl AS lv, Expe AS ex, Class AS cl, Job AS jb, Subjob AS sb "
                        "FROM dbo.Charinfo")
            sk = j.rows("SELECT Userindex AS u, Charidx AS c, Skillidx AS s, Lvl AS lv FROM dbo.CharSkill")
            dch = j.rows(_DEL_CHARS)
            dsk = j.rows(_DEL_SKILLS)
    except Exception as ex:
        joy_chars.last_error = str(ex)[:200]
        return None
    out = {}
    for r in ch:
        out[(int(r["u"]), int(r["c"]))] = _char(r)
    for r in dch:
        out[(int(r["u"]), int(r["c"]), str(r["ek"]))] = _char(r, str(r["ek"]))
    for r in sk:
        c = out.get((int(r["u"]), int(r["c"])))
        if c is not None:
            c["skills"][int(r["s"])] = int(r["lv"] or 0)
    for r in dsk:
        c = out.get((int(r["u"]), int(r["c"]), str(r["ek"])))
        if c is not None:
            c["skills"][int(r["s"])] = int(r["lv"] or 0)
    return out


joy_chars.last_error = None


def _joy(ev):
    if "_skill_joy" not in ev.__dict__:
        ev.__dict__["_skill_joy"] = joy_chars()
    return ev.__dict__["_skill_joy"]


def holders(joy, sid):
    """[(учётка, персонаж, имя, уровень персонажа, уровень навыка, ключ joy)] — у кого навык изучен (и в корзине — ревизия 39 С-1)."""
    return sorted((k[0], k[1], x["name"], x["lvl"], x["skills"][sid], k) for k, x in joy.items() if sid in x["skills"])


def tree_sums(joy, buf):
    """{(учётка, персонаж): {дерево: сумма уровней}} — как вход в мир (sub_475290: сумма дерева += Lvl навыков 500…N−1)."""
    n = len(buf) // REC
    out = {}
    for key, x in joy.items():
        t = {}
        for s, lv in x["skills"].items():
            if SKILL_MIN <= s < n:
                tr = buf[s * REC + 189]
                t[tr] = t.get(tr, 0) + lv
        out[key] = t
    return out


def _fits(mask, x):
    return any(0 < x[k] < 64 and (mask >> x[k]) & 1 for k in ("job", "sub"))


def _who(lst, extra=None):
    """Список персонажей для предупреждения (через «; » — переводчик переводит каждую часть)."""
    parts = ["%s (%d/%d, ур. %d%s)" % (x[2] or "?", x[0], x[1], x[3], (", " + extra(x)) if extra else "") for x in lst[:10]]
    if len(lst) > 10:
        parts.append("и ещё %d" % (len(lst) - 10))
    return "; ".join(parts)


def _who_err(lst):
    """Список персонажей для ОТКАЗА (через запятую — без «; »)."""
    return ", ".join("%s (%d/%d)" % (x[2] or "?", x[0], x[1]) for x in lst[:10]) + (" +%d" % (len(lst) - 10) if len(lst) > 10 else "")


# ---------------------------------------------------------------------------------------------------------------------
# Правила «изученное не становится невалидным» (одни и те же — для позиции и для перепроверки перед выкладкой и откатом)
# ---------------------------------------------------------------------------------------------------------------------
def block_max(joy, sid, new):
    """Макс. уровень навыка понижается до new: держатели с уровнем выше → текст отказа или None."""
    over = [h for h in holders(joy, sid) if h[4] > new]
    if over:
        return ("навык %s: у %d перс. уровень выше нового максимума %d (%s) — изученное стало бы невалидным (уровень > +43), правка не делается"
                % (skill_label(sid), len(over), new, _who_err(over)))
    return None


def block_need(joy, sid, old, new, sources=None):
    """Требование дерева 0 → > 0 у навыка с держателями (и у навыка, который сервер выдаёт сам, — будущие держатели, ревизия 39 С-3)
    → текст отказа или None. sources — [откуда сервер выдаёт навык] (skill_sources)."""
    if old == 0 and new > 0:
        h = holders(joy, sid)
        if h:
            return ("навык %s есть у %d перс. (%s): с требованием дерева > 0 сброс дерева (sub_480F20) и полный сброс (sub_4803A0, UPCharSkillinit "
                    "по AsdaSkillBase.Need) удалят его, а стартовые навыки сервер выдаёт только при смене профессии — сброс навыков сломался "
                    "бы, правка не делается" % (skill_label(sid), len(h), _who_err(h)))
        if sources:
            return ("навык %s сервер выдаёт сам (%s): у будущих держателей с требованием дерева > 0 сброс дерева (sub_480F20) удалит его, а "
                    "вернёт его только смена профессии или гейт 4-й профессии (sub_481CE0 — лишь при сумме основных деревьев от 60 и пустых "
                    "деревьях 4-й профессии) — поток не подтверждён, правка не делается" % (skill_label(sid), ", ".join(sources)))
    return None


def spt_skills(buf, j):
    return [x for x in struct.unpack_from("<6h", buf, j * SPT_REC + 2) if x > -1]


def spt_rows_of(buf, sid):
    """Строки SkillPointTable, которые выдают навык sid → [(строка, дерево, порог)]."""
    return [(j, buf[j * SPT_REC], struct.unpack_from("<b", buf, j * SPT_REC + 1)[0]) for j in range(len(buf) // SPT_REC) if sid in spt_skills(buf, j)]


def spt_need_note(j, tree, thr, sid, need):
    """★ ревизия 39 С-2: порог строки SPT и требование дерева её навыка разошлись → предупреждение или None (сравнение — только если навык
    в том же дереве, что и строка; в живой таблице у всех 132 строк порог = требованию её навыков)."""
    if thr < need:
        return ("строка %d SkillPointTable (дерево %d) выдаёт навык %d при сумме %d, а его требование дерева %d — навык выдаётся раньше, чем его "
                "можно повышать (5254 код 6)" % (j, tree, sid, thr, need))
    if thr > need:
        return ("строка %d SkillPointTable (дерево %d) выдаёт навык %d при сумме %d, а его требование дерева %d — порог строки и требование "
                "навыка разошлись (в живой таблице они равны)" % (j, tree, sid, thr, need))
    return None


CJAST = "SkillTable_Info\\ChangeJobAddSkillTable.txt"
TEMPLATES = ("Fighter", "Ranger", "Mage")        # шаблоны UPCharSkillinit (domains/skills.py TEMPLATE) = строки 1/12/23 ChangeJobAddSkillTable


def cjast_rows(raw):
    """{строка: [навыки]} ChangeJobAddSkillTable.txt — как загрузчик GameServer.c:71620 (и srvtables.change_job_rows): строка 1…39,
    количество > 0, иначе конец."""
    toks = raw.decode("latin-1").split()
    out, i = {}, 0
    while i + 1 < len(toks):
        row, n = E._int(toks[i]), E._int(toks[i + 1])
        if row <= 0 or row > 39 or n <= 0:
            break
        out[row] = [E._int(x) for x in toks[i + 2:i + 2 + n]]
        i += 2 + n
    return out


def joy_templates():
    """{навык: [шаблон]} — Joy1.dbo.Fighter / Ranger / Mage (UPCharSkillinit выдаёт их при полном сбросе) или None (last_error)."""
    joy_templates.last_error = None
    out = {}
    try:
        from core import db
        with db.GameReader("joy1") as j:
            for t in TEMPLATES:
                for r in j.rows("SELECT Skillidx AS s FROM dbo.%s" % t):
                    out.setdefault(int(r["s"]), []).append("dbo." + t)
    except Exception as ex:
        joy_templates.last_error = str(ex)[:200]
        return None
    return out


joy_templates.last_error = None


def skill_sources(ev, sid):
    """★ ревизия 39 С-3: откуда сервер выдаёт навык сам (будущие держатели) → [источник]; не прочитано — OpRefused.
    ChangeJobAddSkillTable всех GameServer (смена профессии, 4-я — P87/P89 по строке подкласса) и шаблоны Joy1.dbo.Fighter/Ranger/Mage."""
    out = []
    for g in E.GS:
        rel = E.rel_of(g, CJAST)
        try:
            ev.snap.extend([rel])
            rows = cjast_rows(ev.snap.raw(rel))
        except Exception as ex:
            raise OpRefused("навык %d: %s не прочитан (%s) — вслепую не делается" % (sid, rel, str(ex)[:120]))
        for row, lst in sorted(rows.items()):
            src = "ChangeJobAddSkillTable строка %d" % row
            if sid in lst and src not in out:
                out.append(src)
    if "_skill_tpl" not in ev.__dict__:
        ev.__dict__["_skill_tpl"] = joy_templates()
    tpl = ev.__dict__["_skill_tpl"]
    if tpl is None:
        raise OpRefused("навык %d: шаблоны Joy1.dbo.Fighter/Ranger/Mage не прочитаны (%s) — вслепую не делается"
                        % (sid, joy_templates.last_error or NO_JOY1))
    return out + tpl.get(sid, [])


def spt_zero_regrant(joy, sif, tree, skills, old, new):
    """★ ревизия 39 К-2: порог вверх, сумма дерева в [прежний, новый), навык строки изучен уровнем 0 → [(учётка, персонаж, имя, ур.)]:
    на новом пороге сервер выдаст его снова (уровень останется 0, лишняя запись списка боя — sub_475650 +359)."""
    if not new > old:
        return []
    sums = tree_sums(joy, sif)
    return [(k[0], k[1], x["name"], x["lvl"]) for k, x in sorted(joy.items())
            if old <= sums.get(k, {}).get(tree, 0) < new and any(s in x["skills"] and x["skills"][s] == 0 for s in skills)
            and not any(x["skills"].get(s, 0) > 0 for s in skills)]


def block_spt(joy, sif, tree, skills, old, new):
    """Порог строки SkillPointTable old → new → текст отказа или None (суммы деревьев по Joy1)."""
    sums = tree_sums(joy, sif)
    bad, why = [], None
    for key, x in sorted(joy.items()):
        s = sums.get(key, {}).get(tree, 0)
        if new < old and new <= s < old:
            miss = [k for k in skills if k not in x["skills"] and k < len(sif) // REC
                    and _fits(struct.unpack_from("<Q", sif, k * REC + 123)[0], x)]
            if miss:
                bad.append((key[0], key[1], x["name"], x["lvl"]))
                why = "low"
        elif new > old and old <= s < new and any(x["skills"].get(k, 0) > 0 for k in skills):
            bad.append((key[0], key[1], x["name"], x["lvl"]))
            why = "high"
    if not bad:
        return None
    if why == "low":
        return ("порог дерева %d снижается %d → %d: у %d перс. сумма дерева уже в [%d, %d) и навыков строки нет (%s) — сервер выдаёт их только "
                "при РАВЕНСТВЕ суммы порогу (sub_47E9B0), они не получат их никогда, правка не делается"
                % (tree, old, new, len(bad), new, old, _who_err(bad)))
    return ("порог дерева %d повышается %d → %d: у %d перс. сумма дерева в [%d, %d) и навык строки уже изучен (%s) — на новом пороге сервер "
            "выдаст его снова уровнем 0 (проверки «уже изучен» у SkillPointTable нет: sub_475650 + UPSkillAdd), правка не делается"
            % (tree, old, new, len(bad), old, new, _who_err(bad)))


def block_exp(joy, lvl, new):
    """Опыт начала уровня lvl → new: персонажи уровня lvl с опытом ниже → текст отказа или None."""
    low = sorted((k[0], k[1], x["name"], x["lvl"]) for k, x in joy.items() if x["lvl"] == lvl and x["exp"] < new)
    if low:
        return ("опыт начала уровня %d → %d: у %d перс. этого уровня опыт меньше (%s) — их опыт оказался бы ниже начала их уровня, правка не "
                "делается" % (lvl, new, len(low), _who_err(low)))
    return None


# =====================================================================================================================
# Клиент
# =====================================================================================================================
def _cli_skill(ev, sid):
    r = (getattr(ev.cli, "skillcli", None) or {}).get(sid)
    if r is None:
        raise OpRefused("навыка %d нет в skill_info клиента — в А4 только правка существующих записей" % sid)
    b = bytes.fromhex(r[1])
    if len(b) != REC - CLI_FROM:
        raise OpRefused("skill_info клиента: у навыка %d DataHex короче записи — строка клиента не согласована" % sid)
    return r[0], b


def cli_val(b, k):
    o, f = (NUM.get(k) or REQ[k])[:2]
    return struct.unpack_from(f, b, o - CLI_FROM)[0]


def _cli_edit(ev, rep, sid, k, oldb, new):
    o, f = (NUM.get(k) or REQ[k])[:2]
    n = struct.calcsize(f)
    nb = struct.pack(f, new)
    e = {"type": "csv_hex_bytes", "file": CLI_SKILL, "key_col": "SkillCode", "key": str(sid), "col": "DataHex", "off": o,
         "old": oldb[o - CLI_FROM:o - CLI_FROM + n].hex(), "new": nb.hex(), "src": AREA}
    rep["client"].append(e)
    ev.client.append(e)


# =====================================================================================================================
# Применение позиций
# =====================================================================================================================
def _each_sif(ev, sid, fields):
    """Проверка ВСЕХ шести копий до записи: запись есть, прежние значения полей = поля (GameServer) → [(таблица, смещение)], поля GS."""
    ref, todo = None, []
    for fold, sub in sif_copies():
        t = ev.st.get(fold, sub)
        off = rec_off(t.buf, sid, "%s\\%s" % (fold, sub))
        v = vals(t.buf, off)
        if ref is None:
            ref = v
        else:
            diff = [k for k in fields if v[k] != ref[k]]
            if diff:
                raise OpRefused("копия %s\\%s: у навыка %d поля %s = %s, а в GameServer %s — отличия копии не затираются, правка не делается"
                                % (fold, sub, sid, ", ".join(diff), ", ".join(str(v[k]) for k in diff), ", ".join(str(ref[k]) for k in diff)))
        todo.append((t, off))
    if not is_player(ref, sid):
        raise OpRefused("навык %d — не навык игрока (маска классов +123 = 0 или заглушка «-») — правка не делается" % sid)
    return todo, ref


def _write_sif(todo, sid, want, old):
    spec = dict(NUM, **REQ)
    for t, off in todo:
        for k, v in want.items():
            o, f = spec[k][:2]
            t.put(off + o, f, v)
            t.note("навык %d: %s (+%d)" % (sid, spec[k][2], o), old[k], v)


def k_skill_num(ev, p, rep):
    sid, want = p["id"], p["fields"]
    todo, cur = _each_sif(ev, sid, list(want))
    for k in (1, 2, 3):
        hit = [f for f in SLOT_FIELDS[k] if f in want]
        if hit and cur["st"][k - 1] < 0:
            raise OpRefused("навык %d: эффекта %d нет (состояние +%d = %d) — его значения сервер не применяет (sub_477F60 / sub_479220 берут "
                            "состояние оттуда), смысл не подтверждён, правка не делается" % (sid, k, SLOT_STATE[k], cur["st"][k - 1]))
    changes = [(k, cur[k], v) for k, v in want.items() if cur[k] != v]
    _row, cb = _cli_skill(ev, sid)
    cdiff = [k for k in want if cli_val(cb, k) != cur[k]]
    if not changes and not cdiff:
        raise OpRefused("у навыка %d эти числа уже такие — менять нечего" % sid)
    new = dict(cur, **want)
    bad = {k: x for k, x in issues(sid, new).items() if k not in issues(sid, cur)}
    if bad:
        raise OpRefused("навык %d, итог правки: %s — правка не делается" % (sid, sorted(bad.values())[0]))
    _write_sif(todo, sid, want, cur)
    rep["text"] = "навык %s: чисел %d (сервер SkillInfo.sif ×%d копий: 3 GameServer + 3 NpcServer, клиент skill_info + ведомость)" % (
        skill_label(sid), len(changes), len(todo))
    rep["lines"] = ["%s: %d → %d" % (NUM[k][2], o, n) for k, o, n in changes]
    mx = cur["max"]
    a, b = level_row(cur, mx), level_row(new, mx)
    rep["lines"] += ["на уровне %d: %s %d → %d" % (mx, LEVEL_LABEL[nm], a[nm], b[nm]) for nm in LEVEL_LABEL if a[nm] != b[nm]]
    rep["_balance"] = [{"what": "навык %d: %s" % (sid, NUM[k][2]), "old": o, "new": n, "codes": []} for k, o, n in changes]
    if cdiff:
        rep["warnings"].append("у клиента навык %d уже расходился с сервером (%s) — правка ставит обоим новое значение" % (sid, ", ".join(cdiff)))
    for k in want:
        if cli_val(cb, k) != want[k]:
            _cli_edit(ev, rep, sid, k, cb, want[k])
    if any(level_raw(new, n)[nm] > 100 for n in range(mx + 1) for nm in ("sp", "ssp")):
        rep["warnings"].append("шанс выше 100 % — сервер зажимает его до 100 (sub_4760E0)")
    if cur["passive"] in (3, 4):
        rep["warnings"].append("навык пассивный: по его полям сервер пересчитывает поля других навыков (sub_47C6A0 / sub_47DAD0, "
                               "PassiveSkillEffectTable) — у них новые значения появятся при следующем повышении")
    _holder_note(ev, rep, sid)


def _holder_note(ev, rep, sid):
    joy = _joy(ev)
    if joy is None:
        rep["warnings"].append("держатели навыка — не прочитано (%s)" % (joy_chars.last_error or NO_JOY1))
        return
    h = holders(joy, sid)
    if h:
        rep["warnings"].append("навык %s есть у %d перс.: %s — числа своего уровня у них лежат в CharSkill (вход берёт их как есть, sub_475290), "
                               "новые они получат при следующем повышении навыка или сбросе; часть путей эффекта (sub_479220) берёт значения "
                               "из таблицы по уровню сразу" % (skill_label(sid), len(h), _who(h, lambda x: "навык ур. %d" % x[4])))


def k_skill_req(ev, p, rep):
    sid, want = p["id"], p["fields"]
    todo, cur = _each_sif(ev, sid, list(want))
    _row, cb = _cli_skill(ev, sid)
    changes = [(k, cur[k], v) for k, v in want.items() if cur[k] != v]
    cdiff = [k for k in want if cli_val(cb, k) != cur[k]]
    if not changes and not cdiff:
        raise OpRefused("у навыка %d эти требования уже такие — менять нечего" % sid)
    new = dict(cur, **want)
    gs = todo[0][0].buf
    bad = {k: x for k, x in issues(sid, new, gs).items() if k not in issues(sid, cur, gs)}
    if bad:
        raise OpRefused("навык %d, итог правки: %s — правка не делается" % (sid, sorted(bad.values())[0]))
    joy = _joy(ev)
    lower_max = "max" in want and want["max"] < cur["max"]
    need_on = "need" in want and cur["need"] == 0 and want["need"] > 0
    if (lower_max or need_on) and joy is None:
        raise OpRefused("навык %d: держатели не прочитаны (%s) — вслепую не делается" % (sid, joy_chars.last_error or NO_JOY1))
    why = (block_max(joy, sid, want["max"]) if lower_max else None) or (
        block_need(joy, sid, cur["need"], want["need"], skill_sources(ev, sid)) if need_on else None)
    if why:
        raise OpRefused(why)
    # ★ ревизия 39 С-2: навык строки SkillPointTable (любой копии GS) с требованием > 0 → 0 — сброс дерева оставит его уровнем 0, а на
    #   пороге строки sub_47E9B0 выдаст его повторно уровнем 0 (проверки «уже изучен» нет) — вложенные уровни пропадут
    spt_hits = []
    for g in E.GS:
        for j, tr_, thr in spt_rows_of(_spt(ev, g).buf, sid):
            if (j, tr_, thr) not in spt_hits:
                spt_hits.append((j, tr_, thr))
    if "need" in want and cur["need"] > 0 and want["need"] == 0 and spt_hits:
        j, tr_, thr = spt_hits[0]
        raise OpRefused("навык %s выдаёт строка %d SkillPointTable (дерево %d, порог %d): с требованием дерева 0 сброс дерева (sub_480F20) оставит "
                        "его изученным уровнем 0, а когда сумма дерева снова станет равна порогу, сервер выдаст его повторно уровнем 0 "
                        "(sub_47E9B0 — проверки «уже изучен» нет) и вложенные уровни пропадут, правка не делается" % (skill_label(sid), j, tr_, thr))
    _write_sif(todo, sid, want, cur)
    if "need" in want and want["need"] != cur["need"]:
        for j, tr_, thr in spt_hits:
            w = spt_need_note(j, tr_, thr, sid, want["need"]) if tr_ == cur["tree"] else None
            if w:
                rep["warnings"].append(w)
    rep["text"] = "навык %s: %s (сервер SkillInfo.sif ×%d копий, клиент skill_info + ведомость)" % (
        skill_label(sid), "; ".join("%s %d → %d" % (REQ[k][2], o, n) for k, o, n in changes) or "клиент приводится к серверу", len(todo))
    bal = []
    for k, o, n in changes:
        kind = "type" if k == "need" and (o == 0) != (n == 0) else "value"
        bal.append({"what": "навык %d: %s" % (sid, REQ[k][2]), "old": o, "new": n, "codes": [], "kind": kind})
    rep["_balance"] = bal
    if cdiff:
        rep["warnings"].append("у клиента навык %d уже расходился с сервером (%s) — правка ставит обоим новое значение" % (sid, ", ".join(cdiff)))
    for k in want:
        if cli_val(cb, k) != want[k]:
            _cli_edit(ev, rep, sid, k, cb, want[k])
    if "need" in want and cur["need"] > 0 and want["need"] == 0:
        rep["warnings"].append("требование дерева станет 0: при сбросе дерева и полном сбросе навык останется изученным уровнем 0 (sub_480F20, "
                               "sub_4803A0; UPCharSkillinit — по AsdaSkillBase.Need, панель приведёт её после выкладки)")
    if joy is None:
        rep["warnings"].append("держатели навыка — не прочитано (%s)" % (joy_chars.last_error or NO_JOY1))
    elif "need" in want and want["need"] > cur["need"]:
        sums = tree_sums(joy, gs)
        low = [h for h in holders(joy, sid) if sums.get(h[5], {}).get(cur["tree"], 0) < want["need"]]
        if low:
            rep["warnings"].append("требование дерева растёт до %d: у %d перс. вложено меньше — навык у них остаётся, но повышать его они не смогут "
                                   "(5254 код 6), пока не вложат: %s" % (want["need"], len(low), _who(low, lambda x: "навык ур. %d" % x[4])))
    if "max" in want and want["max"] > cur["max"]:
        rep["warnings"].append("макс. уровень растёт: новые уровни игрок купит очками навыков (лимит пула P110 — как раньше); проверьте числа "
                               "уровней %d…%d в справке" % (cur["max"] + 1, want["max"]))


def _spt(ev, g):
    t = ev.st.get(g, SPT)
    if len(t.buf) % SPT_REC:
        raise OpRefused("%s\\%s: размер %d не кратен 14 — правка не делается" % (g, SPT, len(t.buf)))
    return t


def k_skill_spt(ev, p, rep):
    j, new = p["row"], p["sum"]
    ref, todo = None, []
    for g in E.GS:
        t = _spt(ev, g)
        if j >= len(t.buf) // SPT_REC:
            raise OpRefused("строки %d нет в %s\\%s (строк %d) — в А4 только правка существующих" % (j, g, SPT, len(t.buf) // SPT_REC))
        cur = struct.unpack_from("<bb6h", t.buf, j * SPT_REC)
        if ref is None:
            ref = cur
        elif cur[:2] != ref[:2]:
            raise OpRefused("копия %s: у строки %d SkillPointTable дерево/порог %d/%d, а в GameServer %d/%d — отличия копии не затираются, "
                            "правка не делается" % (g, j, cur[0], cur[1], ref[0], ref[1]))
        todo.append(t)
    tree, old = ref[0], ref[1]
    if old == new:
        raise OpRefused("у строки %d порог уже %d — менять нечего" % (j, new))
    buf0 = todo[0].buf
    for k in range(len(buf0) // SPT_REC):
        if k != j and buf0[k * SPT_REC] == tree and struct.unpack_from("<b", buf0, k * SPT_REC + 1)[0] == new:
            raise OpRefused("у строки %d то же дерево %d и порог %d: сервер берёт первую подходящую строку (sub_47E9B0 — break), одна из двух не "
                            "сработает никогда, правка не делается" % (k, tree, new))
    skills = spt_skills(buf0, j)
    joy = _joy(ev)
    if joy is None:
        raise OpRefused("порог дерева: суммы деревьев персонажей не прочитаны (%s) — вслепую не делается" % (joy_chars.last_error or NO_JOY1))
    sif = ev.st.get(E.GS[0], SIF_GS).buf
    why = block_spt(joy, sif, tree, skills, old, new)
    if why:
        raise OpRefused(why)
    for t in todo:
        t.put(j * SPT_REC + 1, "<b", new)
        t.note("SkillPointTable строка %d: порог (+1)" % j, old, new)
    rep["text"] = "очки дерева: строка %d (дерево %d, навыки %s): порог %d → %d (сервер SkillPointTable.spt ×%d GS; у клиента таблицы нет)" % (
        j, tree, ", ".join(map(str, skills)) or "—", old, new, len(todo))
    rep["_balance"] = [{"what": "SkillPointTable строка %d: порог" % j, "old": old, "new": new, "codes": []}]
    rep["warnings"].append("NpcServer\\Skill\\SkillPointTable.spt NpcServer не читает (строки нет в NpcServer.exe) — копия там не меняется")
    n = len(sif) // REC
    for s in skills:                                   # ★ ревизия 39 С-2: порог строки ↔ требование дерева её навыков
        if SKILL_MIN <= s < n and sif[s * REC + 189] == tree:
            w = spt_need_note(j, tree, new, s, sif[s * REC + 190])
            if w:
                rep["warnings"].append(w)
    zero = spt_zero_regrant(joy, sif, tree, skills, old, new)
    if zero:
        rep["warnings"].append("у %d перс. сумма дерева в [%d, %d) и навык строки изучен уровнем 0: %s — на новом пороге сервер выдаст его снова "
                               "(уровень останется 0, лишняя запись списка навыков боя — sub_475650)" % (len(zero), old, new, _who(zero)))


def records(t, per):
    """Строки записей таблицы «N, затем N записей потоком слов» — как shopdata.record_line (одна проверка построчности на всю таблицу,
    кэш на объекте таблицы до её правки) → [номер строки] или None."""
    key = ("_recs", per, len(t.changed))
    hit = t.__dict__.get("_recs_cache")
    if hit and hit[0] == key:
        return hit[1]
    n = E._int(t.lines[0].decode("latin-1"))
    body = [i for i in range(1, len(t.lines)) if t.lines[i].strip()]
    ok = (n >= 0 and len(body) >= n and all(len(t.lines[i].split()) == per for i in body[:n])
          and len(b" ".join(t.lines).split()) == 1 + per * n)
    out = body[:n] if ok else None
    t.__dict__["_recs_cache"] = (key, out)
    return out


def _cstat_rec(t, cls, lvl, where):
    recs = records(t, 8)
    if recs is None:
        raise OpRefused("таблица %s: слова не ложатся построчно по 8 на запись — порядок записей сервера не доказан, правка не делается" % where)
    hit = []
    for k, i in enumerate(recs):
        f = t.lines[i].split(b"\t")
        if len(f) != 8:
            raise OpRefused("таблица %s: запись %d — поля TAB не совпадают со словами сервера, правка не делается" % (where, k))
        if E._int(f[0].decode("latin-1")) == cls and E._int(f[1].decode("latin-1")) == lvl:
            hit.append((i, f))
    if not hit:
        raise OpRefused("записи «класс %d, уровень %d» нет в %s — в А4 только правка существующих" % (cls, lvl, where))
    if len(hit) > 1:
        raise OpRefused("в %s запись «класс %d, уровень %d» встречается %d раз (сервер возьмёт последнюю) — правка не однозначна" % (where, cls, lvl, len(hit)))
    return hit[0]


def k_class_stat(ev, p, rep):
    cls, lvl, want = p["cls"], p["lvl"], p["fields"]
    idx = {k: 2 + i for i, (k, _n) in enumerate(STATS)}
    ref, todo = None, []
    for g in E.GS:
        t = ev.st.get(g, CSTAT)
        i, f = _cstat_rec(t, cls, lvl, "%s\\%s" % (g, CSTAT))
        cur = {k: E._int(f[idx[k]].decode("latin-1")) for k, _n in STATS}
        if ref is None:
            ref = cur
        else:
            diff = [k for k in want if cur[k] != ref[k]]
            if diff:
                raise OpRefused("копия %s: у класса %d уровня %d характеристики %s отличаются от GameServer — отличия копии не затираются, правка "
                                "не делается" % (g, cls, lvl, ", ".join(diff)))
        todo.append((t, i, f))
    changes = [(k, ref[k], v) for k, v in want.items() if ref[k] != v]
    if not changes:
        raise OpRefused("у класса %d уровня %d эти характеристики уже такие — менять нечего" % (cls, lvl))
    for t, i, f in todo:
        for k, v in want.items():
            f[idx[k]] = E.set_token(f[idx[k]], v)
        t.set_line(i, b"\t".join(f))
    nm = dict(STATS)
    rep["text"] = "класс %d (%s), уровень %d: %s (сервер ClassStat.txt ×%d GS; клиент характеристики получает от сервера)" % (
        cls, CLASSES[cls], lvl, "; ".join("%s %d → %d" % (nm[k], o, n) for k, o, n in changes), len(todo))
    rep["_balance"] = [{"what": "класс %d ур. %d: %s" % (cls, lvl, nm[k]), "old": o, "new": n, "codes": []} for k, o, n in changes]
    joy = _joy(ev)
    if joy is None:
        rep["warnings"].append("персонажи класса — не прочитано (%s)" % (joy_chars.last_error or NO_JOY1))
        return
    who = sorted((k[0], k[1], x["name"], x["lvl"]) for k, x in joy.items() if x["cls"] == cls and x["lvl"] == lvl and not x.get("deleted"))
    if who:
        rep["warnings"].append("класс %d уровня %d сейчас у %d перс.: %s — базу сервер возьмёт заново при входе (CharMake → sub_43AF30); "
                               "база на момент пересчёта (P2) в Joy1 у них прежняя до первого пересчёта бонусов — до следующего входа процентный "
                               "бонус может посчитаться от прежней базы" % (cls, lvl, len(who), _who(who)))


def _exp_rec(t, lvl, where):
    recs = records(t, 2)
    if recs is None:
        raise OpRefused("таблица %s: слова не ложатся построчно по 2 на запись — порядок записей сервера не доказан, правка не делается" % where)
    if not 1 <= lvl <= len(recs):
        raise OpRefused("уровня %d нет в %s — в А4 только правка существующих" % (lvl, where))
    i = recs[lvl - 1]
    f = t.lines[i].split(b"\t")
    if len(f) != 2 or E._int(f[0].decode("latin-1")) != lvl:
        raise OpRefused("таблица %s: запись %d — не «%d<TAB>опыт» (уровень = позиция записи), правка не делается" % (where, lvl, lvl))
    return i, f


def exp_value(t, lvl, where):
    return E._int(_exp_rec(t, lvl, where)[1][1].decode("latin-1"))


def _i32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def _e2n(row, cum_row, cum_prev):
    d = cum_row - cum_prev
    return d // 40 if row >= DIV40_FROM else d


def k_level_exp(ev, p, rep):
    lvl, new = p["lvl"], p["exp"]
    ref, todo = None, []
    for g in E.GS:
        t = ev.st.get(g, EXPT)
        where = "%s\\%s" % (g, EXPT)
        i, f = _exp_rec(t, lvl, where)
        cur = E._int(f[1].decode("latin-1"))
        if ref is None:
            ref = cur
        elif cur != ref:
            raise OpRefused("копия %s: опыт уровня %d = %d, а в GameServer %d — отличия копии не затираются, правка не делается" % (g, lvl, cur, ref))
        todo.append((t, i, f))
    old = ref
    t0 = todo[0][0]
    n = E._int(t0.lines[0].decode("latin-1"))
    prev = exp_value(t0, lvl - 1, E.GS[0])
    nxt = exp_value(t0, lvl + 1, E.GS[0]) if lvl < n else None
    if old == new:
        raise OpRefused("у уровня %d опыт уже %d — менять нечего" % (lvl, new))
    near = set()                                       # соседние уровни, которые правит этот же набор, — рост проверит after_run по итогу
    for it in ev.items:
        try:
            if it["kind"] == "level.exp" and int((it.get("params") or {}).get("lvl")) in (lvl - 1, lvl + 1):
                near.add(int(it["params"]["lvl"]))
        except (TypeError, ValueError):
            pass
    if (lvl - 1 not in near and not prev < new) or (nxt is not None and lvl + 1 not in near and not new < nxt):
        # ★ ревизия 39 Н-2: без «; » (i18n.tr режет вложенное по нему) и без непереводимой подстановки — два целых шаблона
        if nxt is None:
            raise OpRefused("опыт уровня %d = %d: таблица должна строго расти (уровень %d — %d), повышение идёт по одному уровню "
                            "(P75_ExpTableGrows) — правка не делается" % (lvl, new, lvl - 1, prev))
        raise OpRefused("опыт уровня %d = %d: таблица должна строго расти (уровень %d — %d, уровень %d — %d), повышение идёт по одному уровню "
                        "(P75_ExpTableGrows) — правка не делается" % (lvl, new, lvl - 1, prev, lvl + 1, nxt))
    joy = _joy(ev)
    if joy is None:
        raise OpRefused("опыт уровня: персонажи не прочитаны (%s) — вслепую не делается" % (joy_chars.last_error or NO_JOY1))
    why = block_exp(joy, lvl, new)
    if why:
        raise OpRefused(why)
    # ★ ревизия 39 К-1: строка клиента проверяется ДО записи ExpTable в состояние набора
    cli = getattr(ev.cli, "expcli", None) or {}
    row = lvl - 1
    r = cli.get(row)
    if r is None:
        raise OpRefused("строки %d нет в charexp клиента — в А4 только правка существующих" % row)
    for t, i, f in todo:
        f[1] = E.set_token(f[1], new)
        t.set_line(i, b"\t".join(f))
    rep["text"] = "опыт начала уровня %d: %d → %d (сервер ExpTable.txt ×%d GS, клиент charexp + ведомость)" % (lvl, old, new, len(todo))
    rep["_balance"] = [{"what": "уровень %d: опыт начала" % lvl, "old": old, "new": new, "codes": []}]
    up = sorted((k[0], k[1], x["name"], x["lvl"]) for k, x in joy.items() if x["lvl"] == lvl - 1 and x["exp"] >= new and not x.get("deleted"))
    if up:
        rep["warnings"].append("у %d перс. уровня %d опыт уже не меньше нового порога: %s — сервер повысит их при следующем получении опыта"
                               % (len(up), lvl - 1, _who(up)))
    try:
        from domains import srvtables
        ini = srvtables.patches_ini()
        # ★ ревизия 39 К-5: зелье начисляет ExpTable[TargetLevel] − опыт — касается только правки самого уровня TargetLevel
        if srvtables.patch_on("P75_LevelUpPotion", ini) and srvtables._atol(ini["P75_LevelUpPotion"].get("targetlevel", "70")) == lvl:
            rep["warnings"].append("зелье повышения уровня (P75) начисляет ExpTable[TargetLevel] − опыт — оно возьмёт новое значение")
    except Exception:
        pass
    # клиент: строка L−1 — CumExp/Zero2; ExpToNext строк L−1 и L (asda_charexp_sync.build_rows); строка проверена до записи
    ccum = ((r[2] & 0xFFFFFFFF) << 32) | (r[1] & 0xFFFFFFFF)
    if ccum != old:
        rep["warnings"].append("у клиента порог уровня %d уже расходился (%d, сервер %d) — правка ставит обоим новое значение" % (lvl, ccum, old))
    # ExpToNext строк L−1 и L зависит от соседних уровней — его правки собирает after_run по ИТОГОВОЙ таблице (две позиции соседних уровней
    # иначе правили бы одну ячейку дважды)
    for rr, col, o, nv in ((row, "CumExp", r[1], _i32(new)), (row, "Zero2", r[2], new >> 32)):
        if o != nv:
            _exp_edit(ev, rep, rr, col, o, nv)


def _exp_edit(ev, rep, row, col, old, new):
    e = {"type": "csv_cell", "file": CLI_EXP, "key_col": "_row", "key": str(row), "col": col, "old": str(old), "new": str(new), "src": AREA}
    rep["client"].append(e)
    ev.client.append(e)


def _exp_after(ev, ex):
    """«Опыт до следующего» клиента (charexp ExpToNext) строк, соседних с правлеными уровнями, — по итоговой ExpTable поля."""
    t = ev.st.get(E.GS[0], EXPT)
    cli = getattr(ev.cli, "expcli", None) or {}
    reps = {lvl: rs[0] for lvl, rs in ex.items() if not rs[0]["errors"]}
    if not reps:
        return
    inexact = False
    for row in sorted({x for lvl in reps for x in (lvl - 1, lvl)}):
        r = cli.get(row)
        if r is None or row < 1:
            continue
        try:
            cur, prev = exp_value(t, row + 1, E.GS[0]), exp_value(t, row, E.GS[0])
        except OpRefused:
            continue
        nv = _e2n(row, cur, prev)
        if row >= DIV40_FROM and (cur - prev) % 40:
            inexact = True
        if r[0] != nv:
            _exp_edit(ev, reps.get(row + 1) or reps.get(row), row, "ExpToNext", r[0], nv)
    if inexact:
        (reps.get(min(reps)))["warnings"].append("с 68-й строки клиент хранит «опыт до следующего» делённым на 40 — разность не делится нацело, "
                                                 "клиент покажет полосу с округлением (порт это поле не читает, CumExp — точно)")


# =====================================================================================================================
# Итог набора, перепроверка, после выкладки
# =====================================================================================================================
def _touched(ev, kinds):
    out = {}
    for r in ev.positions:
        if r["kind"] in kinds and not r["errors"] and isinstance(r.get("params"), dict):
            try:
                key = int(r["params"]["id"]) if r["kind"].startswith("skill.") and r["kind"] != "skill.spt" else (
                    int(r["params"]["row"]) if r["kind"] == "skill.spt" else int(r["params"]["lvl"]))
            except (KeyError, TypeError, ValueError):
                continue
            out.setdefault(key, []).append(r)
    return out


def _err(rs, bad):
    for r in rs:
        for b in bad:
            if b not in r["errors"]:
                r["errors"].append(b)


def after_run(ev):
    """По ИТОГОВОМУ состоянию набора (все позиции применены — порядок не важен): у каждого тронутого навыка в каждой копии нет НОВЫХ
    неисправностей (сравнение с базой копии; перенос через край на любом уровне, макс. уровень ниже открытий и требований других
    навыков); у SkillPointTable нет новых пар «дерево + порог»; ExpTable строго растёт; изученное по Joy1 не становится невалидным."""
    sk = _touched(ev, ("skill.num", "skill.req"))
    for sid, rs in sorted(sk.items()):
        bad = []
        for fold, sub in sif_copies():
            try:
                t = ev.st.get(fold, sub)
                now = vals(t.buf, rec_off(t.buf, sid, sub))
                base = ev.snap.raw(t.rel)
                was = vals(base, rec_off(base, sid, sub))
            except OpRefused as ex:
                bad.append(str(ex))
                continue
            new = issues(sid, now, t.buf)
            old = issues(sid, was, base)
            bad += ["копия %s: %s" % (fold, v) for k, v in sorted(new.items()) if k not in old]
        _err(rs, bad)
    for j, rs in sorted(_touched(ev, ("skill.spt",)).items()):
        bad = []
        for g in E.GS:
            t = ev.st.get(g, SPT)
            base = ev.snap.raw(t.rel)
            pairs = lambda b: [(b[k * SPT_REC], struct.unpack_from("<b", b, k * SPT_REC + 1)[0]) for k in range(len(b) // SPT_REC)]
            pn, pb = pairs(t.buf), pairs(base)
            dup = sorted({x for x in pn if pn.count(x) > 1} - {x for x in pb if pb.count(x) > 1})
            if dup:
                bad.append("копия %s: у SkillPointTable две строки с одним деревом и порогом (%s) — одна не сработает" % (
                    g, ", ".join("%d/%d" % x for x in dup)))
        _err(rs, bad)
    ex = _touched(ev, ("level.exp",))
    if ex:
        bad = []
        for g in E.GS:
            t = ev.st.get(g, EXPT)
            n = E._int(t.lines[0].decode("latin-1"))
            try:
                seq = [exp_value(t, k, g) for k in range(1, n + 1)]
            except OpRefused as e:
                bad.append(str(e))
                continue
            if any(not a < b for a, b in zip(seq, seq[1:])):
                bad.append("копия %s: ExpTable после набора не растёт строго — повышение по одному уровню сломалось бы" % g)
        _err([r for rs in ex.values() for r in rs], bad)
        if not bad:
            _exp_after(ev, ex)
    if sk:
        ev.warnings.append("после выкладки и отката панель приведёт Joy1.dbo.AsdaSkillBase (ac0x: по ней UPCharSkillinit сохраняет навыки при "
                           "полном сбросе) к живому SkillInfo.sif")


def _guard_rels():
    return [E.rel_of(g, s) for s in (SIF_GS, SPT, EXPT) for g in E.GS[:1]]


def _guard_state(cs, mode):
    """Таблицы поля (SkillInfo, SkillPointTable, ExpTable GameServer), какими они СТАНУТ (apply — живые + файлы ЭТОГО набора из манифеста
    сухого прогона, md5 = утверждённому; rollback — живые, файлы набора — базой: живая = база или .bak_<метка> = база) и какими они есть
    сейчас → ({путь: байты}, {путь: байты}). Не сходится — исключение (у вызывающего «не прочитаны» → отказ)."""
    import json
    rels = _guard_rels()
    files = {}
    for f in ((cs.get("check") or {}).get("server") or {}).get("files") or []:
        for g in f["gs"]:
            files[E.rel_of(g, f["table"])] = (f["base"], f["new"])
    man = None
    if any(r in files for r in rels) and cs.get("id") is not None:
        from domains import shopcs
        mp = shopcs.manifest_path(cs["id"])
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                man = json.load(fh)
    tag = (man or {}).get("tag") or cs.get("server_tag")
    baks = {r: r + ".bak_" + tag for r in rels if r in files} if mode == "rollback" and tag else {}
    md5 = E.live_md5(rels + list(baks.values()))
    sn = E.Snap(dict(md5))
    now, after = {}, {}
    for r in rels:
        now[r] = sn.raw(r)
        if r not in files:
            after[r] = now[r]
            continue
        base, new = files[r]
        if mode == "apply":
            if md5.get(r) == new:
                after[r] = now[r]
            elif md5.get(r) == base:
                lp = (((man or {}).get("files") or {}).get(r) or {}).get("local")
                if not lp or not os.path.isfile(lp):
                    raise RuntimeError("нет файла набора %s — сначала changeset server-dry" % r)
                with open(lp, "rb") as fh:
                    b = fh.read()
                if E.md5b(b) != new:
                    raise RuntimeError("файл набора %s ≠ утверждённому — повторите server-dry" % r)
                after[r] = b
            else:
                raise RuntimeError("%s на стойке — не база и не файл набора" % r)
        elif md5.get(r) == base:
            after[r] = now[r]
        elif r in baks and md5.get(baks[r]) == base:
            after[r] = sn.raw(baks[r])
        else:
            raise RuntimeError("%s: базы набора нет ни на месте, ни в .bak" % r)
    return after, now


def transitions(after, now, ids):
    """Опасные переходы «сейчас → станет» по таблицам поля: [(вид, параметры)] — макс. уровень вниз, требование дерева 0 → > 0, порог
    SkillPointTable, опыт уровня (вверх). ids — {вид: {номера}} позиций набора."""
    out = []
    rs, rp, re_ = (E.rel_of(E.GS[0], s) for s in (SIF_GS, SPT, EXPT))
    sa, sn = after[rs], now[rs]
    for sid in sorted(ids.get("skill", ())):
        try:
            va, vn = vals(sa, rec_off(sa, sid, rs)), vals(sn, rec_off(sn, sid, rs))
        except OpRefused:
            continue
        if va["max"] < vn["max"]:
            out.append(("max", sid, va["max"], vn["max"]))
        if vn["need"] == 0 and va["need"] > 0:
            out.append(("need", sid, vn["need"], va["need"]))
    pa, pn = after[rp], now[rp]
    for j in sorted(ids.get("spt", ())):
        if (j + 1) * SPT_REC <= min(len(pa), len(pn)):
            a, b = struct.unpack_from("<bb", pa, j * SPT_REC), struct.unpack_from("<bb", pn, j * SPT_REC)
            if a[1] != b[1]:
                out.append(("spt", j, a[0], b[1], a[1]))
    ta, tn = E.Table(re_, after[re_]), E.Table(re_, now[re_])
    for lvl in sorted(ids.get("exp", ())):
        try:
            a, b = exp_value(ta, lvl, re_), exp_value(tn, lvl, re_)
        except OpRefused:
            continue
        if a > b:
            out.append(("exp", lvl, a))
    return out


def apply_guard(cs, mode):
    """Перед выкладкой (apply) и откатом (rollback) сервера: опасные переходы по итоговому состоянию — держатели, суммы деревьев и опыт
    персонажей ПЕРЕЧИТЫВАЮТСЯ (Joy1) → [причины]. Не прочитано — причина с «не прочитаны» (откат и с ключом --held-ok не делается)."""
    ids = {}
    for it in cs.get("items") or []:
        k, pr = it["kind"], it.get("params") or {}
        try:
            if k in ("skill.num", "skill.req"):
                ids.setdefault("skill", set()).add(int(pr["id"]))
            elif k == "skill.spt":
                ids.setdefault("spt", set()).add(int(pr["row"]))
            elif k == "level.exp":
                ids.setdefault("exp", set()).add(int(pr["lvl"]))
        except (KeyError, TypeError, ValueError):
            pass
    if not ids:
        return []
    try:
        after, now = _guard_state(cs, mode)
        tr = transitions(after, now, ids)
    except Exception as ex:
        return ["навыки и классы: таблицы стойки не прочитаны (%s) — вслепую не делается" % str(ex)[:160]]
    if not tr:
        return []
    joy = joy_chars()
    if joy is None:
        return ["навыки и классы: персонажи не прочитаны (%s) — вслепую не делается" % (joy_chars.last_error or NO_JOY1)]
    out = []
    sif = after[E.rel_of(E.GS[0], SIF_GS)]
    spt = now[E.rel_of(E.GS[0], SPT)]
    for t in tr:
        if t[0] == "max":
            w = block_max(joy, t[1], t[2])
        elif t[0] == "need":
            w = block_need(joy, t[1], t[2], t[3])
        elif t[0] == "spt":
            w = block_spt(joy, sif, t[2], spt_skills(spt, t[1]), t[3], t[4])
        else:
            w = block_exp(joy, t[1], t[2])
        if w:
            out.append(w)
    return out


def after_server(cs, mode):
    """После выкладки / отката (и server-sync): Joy1.dbo.AsdaSkillBase (ac0x) = живой GameServer\\SkillTable_Info\\SkillInfo.sif по Need и 13 полям
    уровня 0 → [заметки]. Пишет только различающиеся строки (asda_ops: UPDATE этих столбцов), каждая — ровно одна строка, иначе откат всей
    транзакции."""
    if not any(it["kind"] in ("skill.num", "skill.req") for it in cs.get("items") or []):
        return []
    cols = [c for c, _o, _f in BASE_COLS]
    try:
        rel = E.rel_of(E.GS[0], SIF_GS)
        sn = E.Snap(dict(E.live_md5([rel])))
        buf = sn.raw(rel)
        n = len(buf) // REC
        from core import db
        with db.GameWriter("joy1") as w:
            cur = {int(r["Skillidx"]): r for r in w.rows("SELECT Skillidx, %s FROM dbo.AsdaSkillBase WITH (UPDLOCK, HOLDLOCK)" % ", ".join(cols))}
            fix, extra = [], []
            for sid, r in sorted(cur.items()):
                if not SKILL_MIN <= sid < n:
                    extra.append(sid)
                    continue
                live = {c: struct.unpack_from(f, buf, sid * REC + o)[0] for c, o, f in BASE_COLS}
                old = {c: int(r[c]) for c in cols}
                if live != old:
                    fix.append((sid, old, live))
            for sid, old, live in fix:
                ch = [c for c in cols if old[c] != live[c]]
                n_ = w.execute("UPDATE dbo.AsdaSkillBase SET %s WHERE Skillidx = ? AND %s" % (
                    ", ".join("%s = ?" % c for c in ch), " AND ".join("%s = ?" % c for c in ch)),
                    [live[c] for c in ch] + [sid] + [old[c] for c in ch])
                if n_ != 1:
                    raise RuntimeError("навык %d: UPDATE затронул %s строк вместо 1 — ничего не записано" % (sid, n_))
            w.commit()
        miss = [s for s in range(SKILL_MIN, n) if s not in cur and struct.unpack_from("<Q", buf, s * REC + 123)[0]]
    except Exception as ex:
        return ["Joy1.dbo.AsdaSkillBase не приведена к SkillInfo.sif (%s) — повторите changeset server-sync %s" % (str(ex)[:160], cs.get("id"))]
    out = ["Joy1.dbo.AsdaSkillBase приведена к SkillInfo.sif: строк изменено %d" % len(fix)]
    if miss:
        out.append("в Joy1.dbo.AsdaSkillBase нет навыков %s — пересоберите её (ac0x_01_migrate.sql)" % ", ".join(map(str, miss[:10])))
    if extra:
        out.append("в Joy1.dbo.AsdaSkillBase лишние строки %s — пересоберите её (ac0x_01_migrate.sql)" % ", ".join(map(str, extra[:10])))
    return out


# =====================================================================================================================
# Клиент: снимок для службы и сверка плана
# =====================================================================================================================
def snapshot(snap):
    p = E.CLIENT_FILES.get(CLI_SKILL)
    sk = {}
    if p and os.path.isfile(p):
        for r in E._read_csv(p):
            try:
                code = int(r["SkillCode"])
            except (KeyError, TypeError, ValueError):
                continue
            hx = (r.get("DataHex") or "").lower()
            if code >= SKILL_MIN and len(hx) >= 2 * REC:
                sk[str(code)] = [int(r["_row"]), hx[2 * CLI_FROM:2 * REC]]
    snap["skillcli"] = sk
    p = E.CLIENT_FILES.get(CLI_EXP)
    snap["expcli"] = ({r["_row"]: [E._int(r.get("ExpToNext")), E._int(r.get("CumExp")), E._int(r.get("Zero2"))] for r in E._read_csv(p)}
                      if p and os.path.isfile(p) else {})


def parse(cli, d):
    cli.skillcli = {int(k): v for k, v in (d.get("skillcli") or {}).items()}
    cli.expcli = {int(k): v for k, v in (d.get("expcli") or {}).items()}


def plan(pc):
    """Сверка итога плана: у строк skill_info / charexp, которые правит область, ПОСЛЕ ведомости и DataHex генератора байты и ячейки — ровно как
    в позиции (поле без строки ведомости генератор молча вернул бы) — иначе отказ плана."""
    for key in CSV_KEYS:
        es = [e for e in pc["by_file"].get(key, []) if e.get("src") == AREA]
        if not es:
            continue
        cur = pc["files"].get(E.CLIENT_FILES[key])
        if not cur or cur[1] is None:
            pc["errors"].append("%s: план не изменил файл, а правки области «Навыки и классы» есть" % key)
            continue
        _h, _by, rows = E._csv_rows(cur[1])
        by = {r.get(es[0]["key_col"]): r for r in rows}
        for e in es:
            r = by.get(e["key"])
            if r is None:
                continue
            if e["type"] == "csv_cell" and r.get(e["col"]) != e["new"]:
                pc["errors"].append("%s %s=%s: %s после плана %s, а позиция — %s" % (key, e["key_col"], e["key"], e["col"], r.get(e["col"]), e["new"]))
            elif e["type"] == "csv_hex_bytes":
                try:
                    got = bytes.fromhex(r.get("DataHex") or "")[int(e["off"]):int(e["off"]) + len(e["new"]) // 2].hex()
                except ValueError:
                    got = ""
                if got != e["new"]:
                    pc["errors"].append("%s %s=%s: DataHex +%s после плана %s, а позиция — %s (правка потерялась бы при перегенерации)"
                                        % (key, e["key_col"], e["key"], e["off"], got, e["new"]))


# =====================================================================================================================
# Справка редактору (только чтение) и расхождения
# =====================================================================================================================
def _ref(rels):
    sn = E.Snap(E.live_md5(rels))
    return sn, E.SrvState(sn)


def search(q, limit=600):
    q = (q or "").strip().lower()
    rel = E.rel_of(E.GS[0], SIF_GS)
    sn, st = _ref([rel])
    buf = st.get(E.GS[0], SIF_GS).buf
    rows = []
    for sid in range(SKILL_MIN, len(buf) // REC):
        v = vals(buf, sid * REC)
        if not is_player(v, sid):
            continue
        nm = skill_label(sid)
        if q and not (q == str(sid) or q in nm.lower() or q in v["name"].lower()):
            continue
        rows.append({"id": sid, "name": nm, "tree": v["tree"], "max": v["max"], "need": v["need"], "mp": v["mp0"], "ev": v["ev0"],
                     "cool": v["cool"]})
        if len(rows) >= limit:
            break
    return {"rows": rows, "total": len(rows)}


def lookup_skill(sid):
    rels = [f + "\\" + s for f, s in sif_copies()]
    sn, st = _ref(rels)
    t = st.get(E.GS[0], SIF_GS)
    off = rec_off(t.buf, sid, E.GS[0] + "\\" + SIF_GS)
    v = vals(t.buf, off)
    if not is_player(v, sid):
        raise OpRefused("навык %d — не навык игрока (маска классов +123 = 0 или заглушка «-»)" % sid)
    copies = {}
    for f, s in sif_copies()[1:]:
        b = st.get(f, s).buf
        o2 = sid * REC
        copies[f] = {"same": len(b) == len(t.buf) and b[o2:o2 + REC] == t.buf[off:off + REC]}
    cli = E.Client.load()
    cr = (getattr(cli, "skillcli", None) or {}).get(sid)
    client = None
    if cr is not None:
        cb = bytes.fromhex(cr[1])
        client = {k: cli_val(cb, k) for k in list(NUM) + list(REQ)} if len(cb) == REC - CLI_FROM else None
    joy = joy_chars()
    h = None if joy is None else holders(joy, sid)
    fields = []
    for k, (o, f, lab, _c) in NUM.items():
        why = None
        for s_ in (1, 2, 3):
            if k in SLOT_FIELDS[s_] and v["st"][s_ - 1] < 0:
                why = "эффекта нет (состояние −1) — значения сервер не применяет, правка не делается"
        fields.append([k, lab, o, 0, TOP[f], v[k], why])
    req = [[k, lab, o, rng_req(k)[0], rng_req(k)[1], v[k], None] for k, (o, f, lab, _c) in REQ.items()]
    return {"id": sid, "name": skill_label(sid), "ko": v["name"], "tree": v["tree"], "passive": v["passive"], "kind": v["kind"],
            "mask": "%016x" % v["mask"], "states": v["st"], "next": [x for x in v["next"] if x[0] >= 0],
            "prereq": [x for x in v["req"] if x[0] >= 0], "users": users_of(t.buf, sid),
            "fields": fields, "req": req, "levels": [dict(level_row(v, n), lvl=n) for n in range(v["max"] + 1)],
            "client": client, "client_source": cli.source, "copies": copies,
            "holders": None if h is None else [{"uid": u, "idx": c, "name": nm, "lvl": lv, "slvl": sl, "deleted": len(k) > 2}
                                               for u, c, nm, lv, sl, k in h],
            "holders_error": joy_chars.last_error}


def lookup_spt():
    rels = [E.rel_of(g, SPT) for g in E.GS]
    sn, st = _ref(rels + [E.rel_of(E.GS[0], SIF_GS)])
    b = st.get(E.GS[0], SPT).buf
    return {"rows": [{"row": j, "tree": b[j * SPT_REC], "sum": struct.unpack_from("<b", b, j * SPT_REC + 1)[0],
                      "skills": [[s, skill_label(s)] for s in spt_skills(b, j)]} for j in range(len(b) // SPT_REC)],
            "copies_same": len({sn.md5[r] for r in rels}) == 1}


def lookup_cstat(cls):
    rels = [E.rel_of(g, CSTAT) for g in E.GS]
    sn, st = _ref(rels)
    t = st.get(E.GS[0], CSTAT)
    n = E._int(t.lines[0].decode("latin-1"))
    rows = []
    recs = records(t, 8)
    for i in (recs or [])[:n]:
        f = [E._int(x.decode("latin-1")) for x in t.lines[i].split(b"\t")]
        if len(f) == 8 and f[0] == cls:
            rows.append({"lvl": f[1], "stats": f[2:]})
    return {"cls": cls, "name": CLASSES.get(cls, ""), "stats": [[k, nm] for k, nm in STATS], "rows": rows,
            "copies_same": len({sn.md5[r] for r in rels}) == 1}


def lookup_exp():
    rels = [E.rel_of(g, EXPT) for g in E.GS]
    sn, st = _ref(rels)
    t = st.get(E.GS[0], EXPT)
    n = E._int(t.lines[0].decode("latin-1"))
    cli = E.Client.load()
    ce = getattr(cli, "expcli", None) or {}
    rows = []
    for lvl in range(1, n + 1):
        try:
            se = exp_value(t, lvl, E.GS[0])
        except OpRefused:
            break
        r = ce.get(lvl - 1)
        rows.append({"lvl": lvl, "exp": se, "client": None if r is None else ((r[2] & 0xFFFFFFFF) << 32) | (r[1] & 0xFFFFFFFF)})
    return {"rows": rows, "copies_same": len({sn.md5[r] for r in rels}) == 1, "client_source": cli.source}


def _ident_int(v, msg):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)


def lookup(what, ident):
    if what == "skills":
        return search(ident)
    if what == "skill":
        return lookup_skill(_ident_int(ident, "номер навыка — целое число"))
    if what == "spt":
        return lookup_spt()
    if what == "classstat":
        c = _ident_int(ident or "1", "класс — целое число 0…3")
        if not 0 <= c <= 3:
            raise OpRefused("класс — целое число 0…3")
        return lookup_cstat(c)
    return lookup_exp()


def skill_base_db():
    """{Skillidx: {столбец: значение}} из Joy1.dbo.AsdaSkillBase или None (причина — last_error); только чтение."""
    skill_base_db.last_error = None
    try:
        from core import db
        with db.GameReader("joy1") as j:
            return {int(r["Skillidx"]): {c: int(r[c]) for c, _o, _f in BASE_COLS} for r in j.rows(
                "SELECT Skillidx, %s FROM dbo.AsdaSkillBase" % ", ".join(c for c, _o, _f in BASE_COLS))}
    except Exception as ex:
        skill_base_db.last_error = str(ex)[:200]
        return None


skill_base_db.last_error = None


def divergence(ev, cli, sec):
    rows = []
    t = ev.st.get(E.GS[0], SIF_GS)
    buf = t.buf
    cs = getattr(cli, "skillcli", None) or {}
    players = [s for s in range(SKILL_MIN, len(buf) // REC) if is_player(vals(buf, s * REC), s)]
    for sid in players:
        c = cs.get(sid)
        if c is None:
            rows.append({"id": sid, "why": "навыка нет у клиента"})
            continue
        cb = bytes.fromhex(c[1])
        sb = bytes(buf[sid * REC + CLI_FROM:(sid + 1) * REC])
        if cb != sb:
            known = [k for k in list(NUM) + list(REQ) if len(cb) == len(sb) and cli_val(cb, k) != struct.unpack_from(
                (NUM.get(k) or REQ[k])[1], sb, (NUM.get(k) or REQ[k])[0] - CLI_FROM)[0]]
            rows.append({"id": sid, "field": ", ".join(known) or "байты", "why": "навык: клиент skill_info ≠ сервер SkillInfo.sif"})
    for f, s in sif_copies()[1:]:
        if ev.snap.md5.get(E.rel_of(f, s)) != ev.snap.md5.get(E.rel_of(E.GS[0], SIF_GS)):
            rows.append({"id": "—", "why": "%s\\%s ≠ GameServer (своя база копии)" % (f, s)})
    db_ = skill_base_db()
    if db_ is None:
        rows.append({"id": "—", "why": "Joy1.dbo.AsdaSkillBase не прочитана (%s)" % (skill_base_db.last_error or NO_JOY1)})
    else:
        for sid in players:
            live = {c: struct.unpack_from(f_, buf, sid * REC + o)[0] for c, o, f_ in BASE_COLS}
            if sid not in db_:
                rows.append({"id": sid, "field": "AsdaSkillBase", "why": "в Joy1.dbo.AsdaSkillBase нет строки навыка"})
            elif db_[sid] != live:
                rows.append({"id": sid, "field": "AsdaSkillBase", "why": "Joy1.dbo.AsdaSkillBase ≠ SkillInfo.sif (%s) — changeset server-sync" % ", ".join(
                    c for c in live if live[c] != db_[sid][c])})
    te = ev.st.get(E.GS[0], EXPT)
    ce = getattr(cli, "expcli", None) or {}
    n = E._int(te.lines[0].decode("latin-1"))
    for lvl in range(2, n + 1):
        try:
            se = exp_value(te, lvl, E.GS[0])
        except OpRefused as ex:
            rows.append({"id": lvl, "why": str(ex)})
            break
        r = ce.get(lvl - 1)
        if r is None:
            rows.append({"id": lvl, "field": "опыт", "why": "строки уровня нет в charexp клиента"})
        elif ((r[2] & 0xFFFFFFFF) << 32) | (r[1] & 0xFFFFFFFF) != se:
            rows.append({"id": lvl, "field": "опыт", "client": ((r[2] & 0xFFFFFFFF) << 32) | (r[1] & 0xFFFFFFFF), "server": se,
                         "why": "опыт начала уровня: клиент charexp ≠ сервер ExpTable"})
    for name in (SPT, CSTAT, EXPT):
        for g in E.GS[1:]:
            if ev.snap.md5.get(E.rel_of(g, name)) != ev.snap.md5.get(E.rel_of(E.GS[0], name)):
                rows.append({"id": "—", "why": "%s: %s ≠ GameServer (своя база копии)" % (g, name)})
    sec("skills", "навыки и опыт: сервер ≠ клиент", rows)
