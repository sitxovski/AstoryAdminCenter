# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cs_kinds/monsters.py — область «Монстры и добыча» (волна А4.3, 20.11.2026; разбор Reports/admin_center/research_a4_data.md
§1.2, §3, §5; правила розыгрыша — Reports/drop_tables_tournament_maps.md §0, квест-дроп — Reports/quest_item_source.md).

ТОЛЬКО СЕРВЕР (клиент дроп и опыт не знает; справка порта DT_MobQuestDrop игрой не читается — только предупреждение). Только правка
СУЩЕСТВУЮЩИХ записей (решение владельца 19.11): мобы не добавляются, размер файлов не меняется, вставок в середину нет.

Monster.ai — запись MONINFO 479 б, ключ = поле +0 (id типа), размер кратен 479 (иначе MessageBox у GameServer, GameServer.c:16130, и
отказ NpcServer, NpcServer.exe.c:57265; NpcServer кладёт запись в массив по id: unk_4DD7A8 + 479·id). ШЕСТЬ копий, ДВЕ базы:
GameServer\\MonsterData_Info, Ch2_GameServer\\MonsterData_Info и NpcServer\\Monster ×3 — одна база (dev 19.11: 2B746793);
Indun_GameServer\\MonsterData_Info — своя (17D95B3A: у 19 мобов другие квест-записи +403…+462). Одна логическая правка ложится на
каждую копию по её байтам: прежнее значение правимого поля у копии обязано совпасть с полем (GameServer), иначе — отказ с объяснением
(отличия Indun не затираются; Ch2 = поле — паритет проверяет движок).
Поля (смещения от записи; экземпляр NpcServer = MONINFO + 30808 — Process_MonsterDead sub_437A30, NpcServer.exe.c:41420…41850):
  +0x35 i32 опыт (лог «Ex : %05d», p91_monster_exp OFF_EXP);
  +167 u8 режим (1 = «рулетка»: гейт +168 i8 из 100, затем ОДИН бросок 0…99 999 по накопительным порогам строк; иначе каждая строка
       бросается независимо); +169/+171 i16 деньги min/max, +173 i8 шанс денег из 100 (сумма min + rand()%(max−min+1), код 20551);
  +174 основной дроп: 20 × (i32 itemId, i32 rate, u16 count), конец — первый itemId = −1; шанс строки (rate+1)/100 000 (rate ≥ 99 999 —
       всегда) — «чистый», без множителя ивента/статов sub_42E3A0;
  +394 i16 индекс записи WorldDropItem.itm (−1 — нет), +396 i16 сколько раз (цикл v121 < count, бросок секции ОДИН — тот же предмет),
  +398 i32 гейт из 100 000; WorldDropItem.itm (NpcServer\\ItemTable, 162 б: +0 i16 свой индекс, 20 × (i32 itemId, i32 накопительный
       порог)): предмет — первая секция с v ≤ порог;
  +402 u8 гейт квест-дропа (≠ 1 — выход), +403 5 × 12 б (i32 задание, i8 шаг, i16 условие, i32 itemId, i8 шанс из 100; > 100 —
       гарантированно и только добившему), конец — задание −1. Задание/шаг/условие не правятся (связь с таблицами заданий — А4.5).
КОПАНИЕ — NpcServer\\MiningItemTable\\<ServerName_NNN из ini\\MapInfo.ini><тип %02d>.mng (загрузчик sub_44F5E0, NpcServer.exe.c:53100…
53280; типов — ini\\Collection.ini CollectionTypeCount = 2), размер кратен 1402. Запись 1402 б = сектор карты: +0 i16 номер сектора,
45 записей по 30 б с +2 (i8 мин. уровень, i8 макс. уровень, i32 опыт, i32 itemId (−1 — конец), i32 мин. кол-во, i32 макс. кол-во,
i32 НАКОПИТЕЛЬНЫЙ порог из 100 000, u64 маска классов), хвост 50 б не читается. Предмет — sub_44F430: первая запись с
порог(k−1) < v ≤ порог(k), v = 0…99 999. ★ Количество (sub_44F170, сверено дизассемблером): min из текущего сектора, а max — по адресу
base + 0x598·k + 0x10, то есть из СЕКТОРА k, СТРОКИ k (1432 = 1402 + 30; дефект оригинала) — поэтому правка копания всегда одинакова во
ВСЕХ секторах файла, файл с разными секторами не правится, и строк не может быть больше, чем секторов (ревизия 35 М-1: строка k ≥ числа
секторов — чтение кучи за таблицей, мусорный max, а при max = min − 1 — rand() % 0 в sub_4089C0 и падение NpcServer). Уровень и маска
класса проверяются после выбора (не подошли — ничего, без переброса).
Предел 20 выпадений за моба (sub_437A30, счётчик v109 < 20) общий: сначала основной дроп (≤ 20 строк — не срезается), затем групповой
(+374), затем мировой — повторы мирового сверх остатка слотов не выпадают; «в среднем шт.» мирового — верхняя оценка (ревизия 35 К-7).
Побочных эффектов при импорте нет.
"""
import re
import struct

from core.ops import OpRefused
from domains import shopdata as E

AREA, TITLE = "monsters", "Монстры и добыча"
PERM_EDIT, PERM_APPLY = "data.edit", "data.apply"
BALANCE_GATE = True
AI_GS, AI_NPC = "MonsterData_Info\\Monster.ai", "Monster\\Monster.ai"
ITM, MAPINFO, COLLECTION = "ItemTable\\WorldDropItem.itm", "ini\\MapInfo.ini", "ini\\Collection.ini"
SRV_FILES = [("GS", AI_GS, "per_copy"), ("NPC", AI_NPC, "per_copy")]
# Карты копания = ServerName_000…023 ini\MapInfo.ini NpcServer (dev 19.11, MapCount = 24; P120 добавил ^MineWar^). Сервер строит имя
# sprintf "%s%02d.mng" из ServerName (ФС Windows без учёта регистра), а здесь — РЕГИСТР ИМЁН ФАЙЛОВ НА ДИСКЕ стойки (листинг SSH 20.11,
# все 3 NpcServer одинаковы; ревизия 35 К-5): у 6 карт он не совпадает с MapInfo (Castle_of_Chess → castle_of_chess, LostValley →
# Lostvalley, t_Palace_of_Queen → t_palace_of_queen, t_Castle_of_chess → t_castle_of_chess, Flabis → flabis, Castle_of_Chaos →
# castle_of_chaos) — чтобы заливка и .bak_* шли под тем же именем, что лежит на диске. Сверка с MapInfo — без учёта регистра;
# живой самотест сверяет список с диском С учётом регистра. Список = белый список deploy_changeset.MINING_MAPS.
MINING_MAPS = ("Sillaris", "Rein", "Conquester", "Alpen", "Night_Valley", "Lostvalley", "SunnyCoast", "Flammio", "palace_of_queen",
               "castle_of_chess", "t_palace_of_queen", "t_castle_of_chess", "MountainFlamion", "flabis", "StagnantDesert", "DragonLaiR",
               "firewayforest", "castle_of_chaos", "Inferion", "battlefield", "eventfield", "fieldofhonor", "quizstage", "^MineWar^")
MINE_TYPES = 2


def mine_sub(name, typ):
    return "MiningItemTable\\%s%02d.mng" % (name, typ)


SRV_FILES_LAZY = [("NPC", mine_sub(m, t), "per_copy") for m in MINING_MAPS for t in range(MINE_TYPES)]
CLIENT_FILES, DT, IMPORTERS, CSV_KEYS = {}, {}, {}, ()

REC = 479
O_ID, O_NAME, O_LVL, O_HP, O_EXP = 0, 5, 4, 0x2D, 0x35
O_MODE, O_RGATE, O_MMIN, O_MMAX, O_MCH = 167, 168, 169, 171, 173
O_DROP, DROP_N, DROP_SZ = 174, 20, 10
O_WIDX, O_WCNT, O_WGATE = 394, 396, 398
O_QGATE, O_Q, Q_N, Q_SZ = 402, 403, 5, 12
WREC, WSEC = 162, 20
MREC, MENT, MN = 1402, 30, 45
MFMT = "<bbiiiiiQ"                       # уровень min/max, опыт, itemId, кол-во min/max, порог, маска классов (30 б)
EMPTY_MINE = (0, 0, 0, -1, 0, 0, 0, 0)    # пустая запись после конца списка (как в файлах оригинала: только itemId = −1)
RND = 100000                             # sub_408BE0(0x186A0): перестановка 0…99 999
MASK_ALL = (1 << 64) - 1

KINDS = {
    "mob.drop": ("Монстр: основной дроп (Monster.ai +174, до 20 строк)", ("mob", "rows"), False),
    "mob.money": ("Монстр: деньги (Monster.ai +169…+173)", ("mob", "min", "max", "chance"), False),
    "mob.world": ("Монстр: мировой дроп (Monster.ai +394/+396/+398)", ("mob", "index", "count", "gate"), False),
    "mob.qdrop": ("Монстр: квестовый дроп (Monster.ai +402/+403: предмет и шанс)", ("mob", "gate", "rows"), False),
    "mob.exp": ("Монстр: опыт (Monster.ai +0x35)", ("mob", "exp"), False),
    "mine.drop": ("Копание: таблица добычи карты (MiningItemTable)", ("map", "type", "rows"), False),
}


# =====================================================================================================================
# Шансы (правила розыгрыша — drop_tables_tournament_maps.md §0)
# =====================================================================================================================
def _span(lo, hi):
    """Число исходов v ∈ [0, 99 999] с lo < v ≤ hi."""
    return max(0, min(hi, RND - 1) - max(lo, -1))


def p_rate(rate):
    """Независимая строка (основной дроп, гейты): rate ≥ v, v = 0…99 999 → (rate+1)/100 000."""
    return _span(-1, rate) / float(RND)


def p_pct(rate):
    """Процентный бросок (деньги, квест-дроп, гейт «рулетки»): rate ≥ v, v = 0…99 → (rate+1)/100."""
    return max(0, min(rate, 99) + 1) / 100.0 if rate >= 0 else 0.0


def p_cumulative(rates):
    """Накопительные пороги (рулетка, мировая секция, копание): строка k — первая с v ≤ порог(k) → доли [p_k]."""
    out, top = [], -1
    for r in rates:
        out.append(_span(top, r) / float(RND))
        top = max(top, r)
    return out


def pct(p):
    """Шанс для показа: проценты, до 4 знаков."""
    if p >= 1:
        return "100 %"
    if p <= 0:
        return "0 %"
    s = ("%.4f" % (p * 100)).rstrip("0").rstrip(".")
    return s + " %"


def main_odds(mode, rgate, rows):
    """Шансы строк основного дропа: обычный режим — независимо, «рулетка» (+167 = 1) — гейт × доля порога."""
    if mode == 1:
        g = p_pct(rgate)
        return [g * x for x in p_cumulative([r[1] for r in rows])]
    return [p_rate(r[1]) for r in rows]


# =====================================================================================================================
# Чтение записей
# =====================================================================================================================
def ai_index(t):
    """{id: смещение записи} Monster.ai (ключ — поле +0); размер не кратен 479 — отказ."""
    if not hasattr(t, "_mob_idx"):
        n = len(t.buf)
        if n == 0 or n % REC:
            raise OpRefused("%s: размер %d не кратен 479 — сервер файл не примет, правка не делается" % (t.rel, n))
        idx = {}
        for i in range(n // REC):
            mid = struct.unpack_from("<i", t.orig, i * REC)[0]
            if mid in idx:
                raise OpRefused("%s: id %d встречается дважды — правка не однозначна" % (t.rel, mid))
            idx[mid] = i * REC
        t._mob_idx = idx
    return t._mob_idx


def drop_rows(b, off):
    out = []
    for k in range(DROP_N):
        it, rt, c = struct.unpack_from("<iiH", b, off + O_DROP + DROP_SZ * k)
        if it == -1:
            break
        out.append([it, rt, c])
    return out


def quest_rows(b, off):
    """5 квест-записей: [задание, шаг, условие, itemId, шанс] (как в файле, с концом −1)."""
    return [list(struct.unpack_from("<ibhib", b, off + O_Q + Q_SZ * k)) for k in range(Q_N)]


def quest_len(rows):
    for k, r in enumerate(rows):
        if r[0] == -1:
            return k
    return len(rows)


def money(b, off):
    return [struct.unpack_from("<h", b, off + O_MMIN)[0], struct.unpack_from("<h", b, off + O_MMAX)[0],
            struct.unpack_from("<b", b, off + O_MCH)[0]]


def world(b, off):
    return [struct.unpack_from("<h", b, off + O_WIDX)[0], struct.unpack_from("<h", b, off + O_WCNT)[0],
            struct.unpack_from("<i", b, off + O_WGATE)[0]]


def world_rows(itm, idx):
    """Секции записи idx WorldDropItem.itm: [[itemId, порог]] до первого itemId ≤ −1; записи нет — None."""
    if idx < 0 or (idx + 1) * WREC > len(itm):
        return None
    out = []
    for k in range(WSEC):
        it, rt = struct.unpack_from("<ii", itm, idx * WREC + 2 + 8 * k)
        if it <= -1:
            break
        out.append([it, rt])
    return out


def mine_rows(rec):
    out = []
    for k in range(MN):
        e = struct.unpack_from(MFMT, rec, 2 + MENT * k)
        if e[3] == -1:
            break
        out.append(list(e))
    return out


def ko_name(b, off):
    return b[off + O_NAME:off + O_NAME + 40].split(b"\0")[0].decode("cp949", "replace")


_names = {}


def _mob_names():
    """{строка DT_MobNames: [RU, ключ EN, EN, n]} из текстов порта / снимка (domains/cs_kinds/texts), кэш 60 с."""
    import time
    hit = _names.get("t")
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        from domains.cs_kinds import texts as TX
        d, _src = TX.texts()
        rows = d.get("ent", {}).get("mob.name") or {}
    except Exception:
        rows = {}
    _names["t"] = (time.time(), rows)
    return rows


def mob_name(mid):
    """Имя моба порта (DT_MobNames, строка id − 1 — как Mob_list) на языке запроса; нет — пусто."""
    from core import i18n
    v = _mob_names().get(str(int(mid) - 1))
    if not v:
        return ""
    return v[2] if i18n.is_en() and v[2] else (v[0] or "")


def mlabel(mid):
    n = mob_name(mid)
    return "%d «%s»" % (mid, n) if n else str(mid)


# =====================================================================================================================
# Позиции
# =====================================================================================================================
def _rows_param(p, key, width, nmax, ranges):
    v = p.get(key)
    if not isinstance(v, list) or len(v) > nmax:
        raise OpRefused("поле «%s»: список строк, не больше %d" % (key, nmax))
    out = []
    for i, r in enumerate(v):
        if not isinstance(r, (list, tuple)) or len(r) != width:
            raise OpRefused("поле «%s», строка %d: нужно %d чисел" % (key, i, width))
        row = []
        for j, (x, (lo, hi)) in enumerate(zip(r, ranges)):
            try:
                n = int(str(x).strip())
            except (TypeError, ValueError):
                raise OpRefused("поле «%s», строка %d: нужно целое число" % (key, i))
            if not lo <= n <= hi:
                raise OpRefused("поле «%s», строка %d, столбец %d: от %d до %d" % (key, i, j + 1, lo, hi))
            row.append(n)
        out.append(row)
    return out


def norm(kind, p):
    mob = lambda: E._ival(p, "mob", 0, 2000000000)
    if kind == "mob.drop":
        return {"mob": mob(), "rows": _rows_param(p, "rows", 3, DROP_N, [(-2147483647, 2147483647), (-1, RND), (1, 32767)])}
    if kind == "mob.money":
        return {"mob": mob(), "min": E._ival(p, "min", 0, 32767), "max": E._ival(p, "max", 0, 32767), "chance": E._ival(p, "chance", -1, 100)}
    if kind == "mob.world":
        return {"mob": mob(), "index": E._ival(p, "index", -1, 32767), "count": E._ival(p, "count", -1, 20), "gate": E._ival(p, "gate", -1, RND)}
    if kind == "mob.qdrop":
        return {"mob": mob(), "gate": E._ival(p, "gate", 0, 255),
                "rows": _rows_param(p, "rows", 2, Q_N, [(-2147483647, 2147483647), (-128, 127)])}
    if kind == "mob.exp":
        return {"mob": mob(), "exp": E._ival(p, "exp", 0, 2000000000)}
    name = str(p.get("map") or "").strip()
    canon = next((m for m in MINING_MAPS if m.lower() == name.lower()), None)
    if canon is None:
        raise OpRefused("карты копания «%s» нет в списке карт NpcServer (MapInfo.ini)" % name[:40])
    rows = p.get("rows")
    if isinstance(rows, list):                       # маска классов — 16 hex-цифр строкой (u64 не помещается в число JS)
        for i, r in enumerate(rows):                 # ★ ревизия 35 К-6: лишние столбцы — отказ, а не молчаливое отбрасывание
            if isinstance(r, (list, tuple)) and len(r) not in (7, 8):
                raise OpRefused("копание, строка %d: нужно 7 чисел и маска классов (8-й столбец, можно опустить), а дано %d" % (i, len(r)))
        rows = [list(r[:7]) + [_mask(r[7]) if len(r) > 7 else MASK_ALL] if isinstance(r, (list, tuple)) else r for r in rows]
    rows = _rows_param({"rows": rows}, "rows", 8, MN, [(-2147483647, 2147483647), (0, 127), (0, 127), (1, 32767), (1, 32767),
                                                       (0, RND), (0, 2000000000), (0, MASK_ALL)])
    rows = [[r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]] for r in rows]
    return {"map": canon, "type": E._ival(p, "type", 0, MINE_TYPES - 1), "rows": rows}


def _mask(v):
    if isinstance(v, int):
        return v
    s = str(v).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{1,16}", s):
        raise OpRefused("маска классов: до 16 шестнадцатеричных цифр")
    return int(s, 16)


def target_key(kind, p):
    if kind == "mine.drop":
        return "mine:%s:%d" % (p["map"].lower(), p["type"])
    return "mob:%d:%s" % (p["mob"], kind.split(".", 1)[1])


def copies():
    """Шесть копий Monster.ai: (копия, подпуть); первая — поле (GameServer) — её значение и есть «было»."""
    return [(g, AI_GS) for g in E.GS] + [(n, AI_NPC) for n in E.folders("NPC")]


def _each(ev, mid, what, read, write):
    """Логическая правка ко всем копиям: read(t, off) копии = read у поля, иначе отказ; write(t, off) → «было» поля."""
    ref, todo = None, []
    for fold, sub in copies():                        # сначала проверка ВСЕХ копий — отказ до первой записи
        t = ev.st.get(fold, sub)
        off = ai_index(t).get(mid)
        if off is None:
            raise OpRefused("моба %d нет в %s\\%s — в А4 только правка существующих" % (mid, fold, sub))
        cur = read(t.buf, off)
        if ref is None:
            ref = cur
        elif cur != ref:
            raise OpRefused("%s\\%s: %s моба %d другой, чем у GameServer (%s ≠ %s) — отличия копии не затираются, правка не однозначна"
                            % (fold, sub, what, mid, _short(cur), _short(ref)))
        todo.append((t, off))
    for t, off in todo:
        write(t, off)
    return ref


def _short(v):
    return str(v).replace(" ", "")[:160]


def _field(ev, mid):
    t = ev.st.get(E.GS[0], AI_GS)
    off = ai_index(t).get(mid)
    if off is None:
        raise OpRefused("моба %d нет в Monster.ai — в А4 только правка существующих" % mid)
    return t, off


def _item(ev, code, rep, where, count=1):
    """Код предмета в дропе: есть на сервере; проверки «дюп и экономика» (разбор §4 п.5) — предупреждения, сильная правка — гейтом."""
    if code <= 0:
        raise OpRefused("%s: код предмета должен быть больше 0" % where)
    if not ev.exists(code):
        raise OpRefused("%s: предмета %d нет на сервере (item_table / Function_Table / Cellob_Table)" % (where, code))
    if code == E.ITEM_FIRST:
        rep["warnings"].append("%s: золото (20551) — его даёт канал денег (+169…+173); строка дропа выдаст %d золота" % (where, count))
    try:
        sell = ev.st.get(E.GS[0], "SellItemTable.txt").has(code)
    except OpRefused:
        sell = False
    if sell or ev.pmap.get(code) or ev.cli.on_premium(code):
        rep["warnings"].append("%s: %s продаётся за GXP (премиум) — дроп раздаёт платный предмет бесплатно" % (where, E.nm(code)))
    f = ev.it_fields(code) if code >= E.ITEM_FIRST else None
    if f and len(f) > 39 and E._int(f[16]) == 11 and E._int(f[17]) == 200:
        rep["warnings"].append("%s: %s — коробка пакета (строка %s): при открытии даст предметы пакета" % (where, E.nm(code), f[39]))
    if count > 1 and not E.stack_flags(ev, [code]).get(code) and code != E.ITEM_FIRST:
        rep["warnings"].append("%s: %s не стопочный, а количество %d — как сервер выдаст нестопочный предмет количеством больше 1, "
                               "разбором не подтверждено" % (where, E.nm(code), count))


def _odds_by_code(rows, odds, cnt_col=2):
    """{код: [шанс хотя бы одного, ожидаемое количество за моба]} по строкам."""
    out = {}
    for r, p in zip(rows, odds):
        a = out.setdefault(r[0], [0.0, 0.0])
        a[0] = 1 - (1 - a[0]) * (1 - p)
        a[1] += p * (r[cnt_col] if cnt_col is not None else 1)
    return out


def _p100(p):
    return round(p * 100, 4)


def _bal_codes(rep, what, old, new):
    """Правки баланса по кодам (числа — для порога ×2): шанс, % было → стало и «в среднем шт.»; новый код — замена (сильная всегда),
    убранный — в ноль (сильная)."""
    b = rep.setdefault("_balance", [])
    for c in sorted(set(old) | set(new)):
        o, n = old.get(c), new.get(c)
        if o is None:
            b.append({"what": "%s: новый предмет %s, шанс, %%" % (what, E.nm(c)), "old": "—", "new": _p100(n[0]), "codes": [c], "kind": "swap"})
            continue
        n = n or [0.0, 0.0]
        if abs(o[0] - n[0]) > 1e-12:
            b.append({"what": "%s: %s, шанс, %%" % (what, E.nm(c)), "old": _p100(o[0]), "new": _p100(n[0]), "codes": [c]})
        if abs(o[1] - n[1]) > 1e-12 and n[0] > 0:
            b.append({"what": "%s: %s, в среднем шт. за раз" % (what, E.nm(c)), "old": round(o[1], 4), "new": round(n[1], 4), "codes": [c]})


def _row_text(r, p):
    return "%s × %d — %s (rate %d)" % (E.nm(r[0]), r[2], pct(p), r[1])


def k_mob_drop(ev, p, rep):
    mid, new = p["mob"], p["rows"]
    t0, off0 = _field(ev, mid)
    mode, rgate = t0.orig[off0 + O_MODE], struct.unpack_from("<b", t0.orig, off0 + O_RGATE)[0]
    old = drop_rows(t0.orig, off0)
    if new == old:
        raise OpRefused("основной дроп моба %d уже такой — менять нечего" % mid)
    for i, r in enumerate(new):
        if r[0] == -1:
            raise OpRefused("строка %d: itemId −1 — это конец списка; лишние строки уберите из списка" % i)
        if r[0] not in [x[0] for x in old]:          # новый для моба код — проверки сервера и «дюп/экономика»
            _item(ev, r[0], rep, "строка %d" % i, r[2])
    if mode == 1:
        rates = [r[1] for r in new]
        bad = [i for i in range(1, len(rates)) if rates[i] <= rates[i - 1]]
        if bad:
            rep["warnings"].append("режим «рулетка» (+167 = 1): пороги строк должны расти — строки %s недостижимы" % bad)

    def write(t, off):
        for k, r in enumerate(new):
            t.put(off + O_DROP + DROP_SZ * k, "<iiH", r[0], r[1], r[2])
        if len(new) < DROP_N:
            t.put(off + O_DROP + DROP_SZ * len(new), "<i", -1)
        t.note("моб %d: основной дроп" % mid, "; ".join("%d×%d r%d" % (r[0], r[2], r[1]) for r in old) or "—",
               "; ".join("%d×%d r%d" % (r[0], r[2], r[1]) for r in new) or "—")
    _each(ev, mid, "основной дроп", lambda b, off: drop_rows(b, off), write)
    oo, no = main_odds(mode, rgate, old), main_odds(mode, rgate, new)
    rep["text"] = ("моб %s: основной дроп — строк %d → %d (сервер: Monster.ai ×%d копий, режим «рулетка»)" if mode == 1 else
                   "моб %s: основной дроп — строк %d → %d (сервер: Monster.ai ×%d копий)") % (mlabel(mid), len(old), len(new), len(copies()))
    rep["lines"] = (["было: %s" % _row_text(r, q) for r, q in zip(old, oo)] or ["было: пусто"]) + \
                   (["станет: %s" % _row_text(r, q) for r, q in zip(new, no)] or ["станет: пусто"])
    _bal_codes(rep, "моб %d, основной дроп" % mid, _odds_by_code(old, oo), _odds_by_code(new, no))


def k_mob_money(ev, p, rep):
    mid = p["mob"]
    if p["min"] > p["max"]:
        raise OpRefused("деньги: минимум %d больше максимума %d" % (p["min"], p["max"]))
    new = [p["min"], p["max"], p["chance"]]
    t0, off0 = _field(ev, mid)
    old = money(t0.orig, off0)
    if old == new:
        raise OpRefused("деньги моба %d уже такие — менять нечего" % mid)

    def write(t, off):
        t.put(off + O_MMIN, "<hhb", *new)
        t.note("моб %d: деньги" % mid, old, new)
    _each(ev, mid, "деньги", money, write)
    rep["text"] = "моб %s: деньги %d…%d, шанс %s → %d…%d, шанс %s" % (mlabel(mid), old[0], old[1], pct(p_pct(old[2])), new[0], new[1],
                                                                    pct(p_pct(new[2])))
    avg = lambda m: p_pct(m[2]) * (m[0] + m[1]) / 2.0
    rep["_balance"] = [{"what": "моб %d: деньги в среднем за моба" % mid, "old": round(avg(old), 2), "new": round(avg(new), 2), "codes": []}]


def _itm(ev):
    """WorldDropItem.itm NpcServer (все копии одинаковы — иначе отказ) → байты."""
    rels = [n + "\\" + ITM for n in E.folders("NPC")]
    ev.snap.extend(rels)
    hs = {ev.snap.md5.get(r) for r in rels}
    if len(hs) != 1 or "none" in hs:
        raise OpRefused("WorldDropItem.itm в копиях NpcServer разный или его нет (%s) — мировой дроп не правится" % sorted(hs))
    return ev.snap.raw(rels[0])


def world_odds(gate, rows):
    g = p_rate(gate)
    return g, [g * x for x in p_cumulative([r[1] for r in rows])]


def k_mob_world(ev, p, rep):
    mid = p["mob"]
    new = [p["index"], p["count"], p["gate"]]
    t0, off0 = _field(ev, mid)
    old = world(t0.orig, off0)
    if old == new:
        raise OpRefused("мировой дроп моба %d уже такой — менять нечего" % mid)
    itm = _itm(ev)
    nrec = len(itm) // WREC
    if len(itm) % WREC:
        raise OpRefused("WorldDropItem.itm: размер %d не кратен 162" % len(itm))
    if new[0] >= nrec:
        raise OpRefused("записи %d в WorldDropItem.itm нет (записей %d) — сервер пишет «GetWorldItemIndex() Exception»" % (new[0], nrec))
    if new[0] < 0 and new[1] > 0 and new[2] >= 0:    # ★ ревизия 35 К-1: отказ (не предупреждение) — см. текст
        raise OpRefused("мировой дроп: индекс −1 при «сколько раз» %d > 0 и гейте %d ≥ 0 — сервер после гейта на каждом повторе пишет "
                        "«GetWorldItemIndex() Exception… iIndex -1» (NpcServer.exe.c:41700), предмета не даёт; чтобы выключить мировой "
                        "дроп, поставьте «сколько раз» 0 или гейт −1" % (new[1], new[2]))
    if new[0] >= 0 and struct.unpack_from("<h", itm, new[0] * WREC)[0] != new[0]:
        rep["warnings"].append("запись %d WorldDropItem.itm несёт другой свой индекс — сервер берёт ПОЗИЦИЮ" % new[0])

    def write(t, off):
        t.put(off + O_WIDX, "<hhi", *new)
        t.note("моб %d: мировой дроп (индекс, раз, гейт)" % mid, old, new)
    _each(ev, mid, "мировой дроп", world, write)
    ro = world_rows(itm, old[0]) or []
    rn = world_rows(itm, new[0]) or []
    go, oo = world_odds(old[2], ro)
    gn, no = world_odds(new[2], rn)
    times = lambda c: max(0, c)
    rep["text"] = "моб %s: мировой дроп — запись %d, раз %d, гейт %s → запись %d, раз %d, гейт %s" % (
        mlabel(mid), old[0], old[1], pct(go), new[0], new[1], pct(gn))
    rep["lines"] = ["было: %s — %s" % (E.nm(r[0]), pct(q)) for r, q in zip(ro, oo)] + \
                   ["станет: %s — %s" % (E.nm(r[0]), pct(q)) for r, q in zip(rn, no)]
    if not rn or new[1] <= 0 or new[0] < 0:
        rep["lines"].append("станет: мировой дроп не выпадает (нет записи, раз ≤ 0)")
    elif new[1] > 0:                                  # ★ ревизия 35 К-7: общий предел 20 выпадений за моба
        nmain = len(drop_rows(t0.orig, off0))
        rep["lines"].append("«в среднем шт.» мирового дропа — верхняя оценка: предел 20 выпадений за моба общий (sub_437A30, v109 < 20), "
                            "основной (строк %d) и групповой дроп занимают слоты раньше" % nmain)
        if nmain + new[1] > 20:
            rep["warnings"].append("мировой дроп: строк основного дропа %d + повторов %d > 20 — если выпадет весь основной дроп, до %d "
                                   "повторов мирового не выпадут (предел 20 слотов)" % (nmain, new[1], nmain + new[1] - 20))
    o = _odds_by_code([[r[0], r[1], times(old[1])] for r in ro] if old[0] >= 0 and old[1] > 0 else [], oo)
    n = _odds_by_code([[r[0], r[1], times(new[1])] for r in rn] if new[0] >= 0 and new[1] > 0 else [], no)
    _bal_codes(rep, "моб %d, мировой дроп" % mid, o, n)
    if new[0] != old[0] and new[0] >= 0:
        rep.setdefault("_balance", []).append({"what": "моб %d: мировой дроп — другая запись WorldDropItem (%d → %d)" % (mid, old[0], new[0]),
                                               "old": old[0], "new": new[0], "codes": sorted({r[0] for r in rn}), "kind": "swap"})


def k_mob_qdrop(ev, p, rep):
    mid, gate, new = p["mob"], p["gate"], p["rows"]
    t0, off0 = _field(ev, mid)
    qr = quest_rows(t0.orig, off0)
    n = quest_len(qr)
    og = t0.orig[off0 + O_QGATE]
    if len(new) != n:
        raise OpRefused("квест-дроп моба %d: строк %d, а в позиции %d — строки не добавляются и не убираются (связь с заданиями — А4.5)"
                        % (mid, n, len(new)))
    changed = [k for k in range(n) if [qr[k][3], qr[k][4]] != new[k]]
    if not changed and gate == og:
        raise OpRefused("квест-дроп моба %d уже такой — менять нечего" % mid)
    for k in changed:
        if new[k][0] != qr[k][3]:
            _item(ev, new[k][0], rep, "квест-строка %d" % k)
    read = lambda b, off: ([b[off + O_QGATE]] if gate != og else []) + [quest_rows(b, off)[k] for k in changed]

    def write(t, off):
        if gate != og:
            t.put(off + O_QGATE, "<B", gate)
        for k in changed:
            t.put(off + O_Q + Q_SZ * k + 7, "<ib", new[k][0], new[k][1])
        t.note("моб %d: квест-дроп (гейт; строка: задание/шаг → предмет, шанс)" % mid,
               "%d; " % og + "; ".join("%d/%d → %d, %d" % (qr[k][0], qr[k][1], qr[k][3], qr[k][4]) for k in changed),
               "%d; " % gate + "; ".join("%d/%d → %d, %d" % (qr[k][0], qr[k][1], new[k][0], new[k][1]) for k in changed))
    _each(ev, mid, "квест-дроп", read, write)
    qp = lambda r: "гарантированно, только добившему" if r > 100 else pct(p_pct(r))
    rep["text"] = "моб %s: квест-дроп — гейт %d → %d, строк изменено %d" % (mlabel(mid), og, gate, len(changed))
    rep["lines"] = ["строка %d (задание %d, шаг %d): %s, %s → %s, %s" % (k, qr[k][0], qr[k][1], E.nm(qr[k][3]), qp(qr[k][4]),
                                                                       E.nm(new[k][0]), qp(new[k][1])) for k in changed]
    if gate != 1:
        rep["warnings"].append("гейт квест-дропа ≠ 1 — квест-предметы с этого моба падать не будут (NpcServer.exe.c:41794)")
    rep["warnings"].append("справка порта DT_MobQuestDrop игрой не читается — не обновляется; asda_import_mob_quest_drop --check покажет "
                           "расхождение с сервером")
    b = rep.setdefault("_balance", [])
    for k in changed:
        if new[k][0] != qr[k][3]:
            b.append({"what": "моб %d, квест-строка %d: предмет %d → %d" % (mid, k, qr[k][3], new[k][0]), "old": qr[k][3], "new": new[k][0],
                      "codes": [qr[k][3], new[k][0]], "kind": "swap"})
        if new[k][1] != qr[k][4]:
            b.append({"what": "моб %d, квест-строка %d: шанс, %%" % (mid, k), "old": _p100(p_pct(qr[k][4])), "new": _p100(p_pct(new[k][1])),
                      "codes": [new[k][0]]})
    if gate != og:
        b.append({"what": "моб %d: квест-дроп включён (гейт +402 = 1)" % mid, "old": 1 if og == 1 else 0, "new": 1 if gate == 1 else 0,
                  "codes": []})


def k_mob_exp(ev, p, rep):
    mid, new = p["mob"], p["exp"]
    t0, off0 = _field(ev, mid)
    old = struct.unpack_from("<i", t0.orig, off0 + O_EXP)[0]
    if old == new:
        raise OpRefused("опыт моба %d уже %d — менять нечего" % (mid, new))

    def write(t, off):
        t.put(off + O_EXP, "<i", new)
        t.note("моб %d: опыт +0x35" % mid, old, new)
    _each(ev, mid, "опыт", lambda b, off: struct.unpack_from("<i", b, off + O_EXP)[0], write)
    rep["text"] = "моб %s: опыт %d → %d (база: GameServer умножает на события, отряд и потолок 1/9 уровня — P91)" % (mlabel(mid), old, new)
    rep["_balance"] = [{"what": "моб %d: опыт" % mid, "old": old, "new": new, "codes": []}]


def _ini_map(ev):
    """ServerName_NNN ini\\MapInfo.ini и CollectionTypeCount ini\\Collection.ini всех NpcServer (одинаковы — иначе отказ)."""
    rels = [n + "\\" + x for n in E.folders("NPC") for x in (MAPINFO, COLLECTION)]
    ev.snap.extend(rels)
    seen = set()
    for n in E.folders("NPC"):
        mi = ev.snap.raw(n + "\\" + MAPINFO).decode("latin-1")
        co = ev.snap.raw(n + "\\" + COLLECTION).decode("latin-1")
        names = tuple(m.group(2) for m in sorted(re.finditer(r'ServerName_(\d+)\s*=\s*"?([^"\r\n]*?)"?\s*$', mi, re.M),
                                                  key=lambda m: int(m.group(1))))
        tc = re.search(r"CollectionTypeCount\s*=\s*(\d+)", co)
        seen.add((names, int(tc.group(1)) if tc else 0))
    if len(seen) != 1:
        raise OpRefused("MapInfo.ini / Collection.ini в копиях NpcServer разные — копание не правится")
    return seen.pop()


def mine_check_file(t):
    """Записи сектора 0 файла копания; все сектора одинаковы (кроме номера) — иначе отказ (см. шапку: max кол-ва из сектора k)."""
    raw = t.orig
    if not raw or len(raw) % MREC:
        raise OpRefused("%s: размер %d не кратен 1402 — NpcServer не стартует, правка не делается" % (t.rel, len(raw)))
    n = len(raw) // MREC
    body = raw[2:MREC]
    bad = [s for s in range(n) if raw[s * MREC + 2:(s + 1) * MREC] != body]
    if bad:
        raise OpRefused("%s: сектора различаются (%d из %d, первый %d) — сервер берёт макс. количество из сектора с номером записи, правка "
                        "по секторам не делается" % (t.rel, len(bad), n, bad[0]))
    return mine_rows(raw[:MREC]), n


def mine_odds(rows):
    return p_cumulative([r[6] for r in rows])


def _mine_text(r, q):
    """Строка копания (порядок полей файла MFMT) для показа."""
    return "%s × %d…%d, ур. %d…%d — %s (порог %d)" % (E.nm(r[3]), r[4], r[5], r[0], r[1], pct(q), r[6])


def _mine_bal_rows(rep, what, old, new):
    """★ ревизия 35 М-2: баланс строк копания с парой по коду (i-е вхождение кода было ↔ i-е стало): опыт копания — число (порог ×2,
    из нуля / в ноль — сильная); смена диапазона уровней или маски классов — kind «type» (сильная всегда: кто может добыть предмет)."""
    b = rep.setdefault("_balance", [])
    seen_o, seen_n = {}, {}
    pair_o = {}
    for r in old:
        k = (r[3], seen_o.setdefault(r[3], 0))
        seen_o[r[3]] += 1
        pair_o[k] = r
    for r in new:
        k = (r[3], seen_n.setdefault(r[3], 0))
        seen_n[r[3]] += 1
        o = pair_o.get(k)
        if o is None:
            continue
        if o[2] != r[2]:
            b.append({"what": "%s: %s, опыт копания" % (what, E.nm(r[3])), "old": o[2], "new": r[2], "codes": [r[3]]})
        if (o[0], o[1]) != (r[0], r[1]):
            b.append({"what": "%s: %s, уровни копателя" % (what, E.nm(r[3])), "old": "%d…%d" % (o[0], o[1]),
                      "new": "%d…%d" % (r[0], r[1]), "codes": [r[3]], "kind": "type"})
        if o[7] != r[7]:
            b.append({"what": "%s: %s, маска классов" % (what, E.nm(r[3])), "old": "%016x" % o[7], "new": "%016x" % r[7], "codes": [r[3]],
                      "kind": "type"})


def k_mine_drop(ev, p, rep):
    name, typ = p["map"], p["type"]
    new = [[r[1], r[2], r[6], r[0], r[3], r[4], r[5], r[7]] for r in p["rows"]]      # параметры → порядок полей файла (MFMT)
    names, tcount = _ini_map(ev)
    if name.lower() not in [x.lower() for x in names]:
        raise OpRefused("карты «%s» нет в MapInfo.ini NpcServer — этот файл сервер не читает" % name)
    if typ >= tcount:
        raise OpRefused("типа копания %d нет (CollectionTypeCount = %d)" % (typ, tcount))
    sub = mine_sub(name, typ)
    ev.snap.extend([n + "\\" + sub for n in E.folders("NPC")])
    for i, r in enumerate(new):
        if r[0] > r[1]:
            raise OpRefused("строка %d: мин. уровень %d больше макс. %d" % (i, r[0], r[1]))
        if r[4] > r[5]:
            raise OpRefused("строка %d: мин. количество %d больше макс. %d (сервер делит на max − min + 1)" % (i, r[4], r[5]))
        if i and r[6] <= new[i - 1][6]:
            raise OpRefused("строка %d: порог %d не больше предыдущего %d — строка недостижима (пороги накопительные, растут)" % (i, r[6], new[i - 1][6]))
    old, todo = None, []
    for n in E.folders("NPC"):                        # сначала проверка ВСЕХ копий — отказ до первой записи
        t = ev.st.get(n, sub)
        rows, nsec = mine_check_file(t)
        if nsec == 0 or len(new) > nsec:              # ★ ревизия 35 М-1 (см. шапку: max количества — сектор k, строка k)
            raise OpRefused("%s\\%s: строк %d, а секторов %d — сервер (sub_44F170) берёт макс. количество строки k из СЕКТОРА k, поэтому строка "
                            "с номером ≥ числа секторов читается за концом таблицы (мусорный максимум, при max = min − 1 — rand() %% 0 "
                            "и падение NpcServer), правка не делается" % (n, sub, len(new), nsec))
        if old is None:
            old = rows
            if new == old:
                raise OpRefused("копание %s, тип %d уже такое — менять нечего" % (name, typ))
            for i, r in enumerate(new):
                if r[3] not in [x[3] for x in old]:
                    _item(ev, r[3], rep, "копание, строка %d" % i, r[5])
        elif rows != old:
            raise OpRefused("%s\\%s: записи копания другие, чем у NpcServer — отличия копии не затираются, правка не однозначна" % (n, sub))
        todo.append((t, nsec))
    for t, nsec in todo:
        for s in range(nsec):
            base = s * MREC + 2
            for k in range(MN):
                if k < len(new):
                    t.put(base + MENT * k, MFMT, *new[k])
                elif k < max(len(old), len(new)) + 1:
                    t.put(base + MENT * k, MFMT, *EMPTY_MINE)
        t.note("копание %s, тип %d: все %d секторов" % (name, typ, nsec), "строк %d" % len(old), "строк %d" % len(new))
    oo, no = mine_odds(old), mine_odds(new)
    rep["text"] = "копание %s, тип %d: строк %d → %d (сервер: %s ×%d NpcServer, все сектора)" % (name, typ, len(old), len(new), sub,
                                                                                               len(E.folders("NPC")))
    rep["lines"] = ["было: %s" % _mine_text(r, q) for r, q in zip(old, oo)] + ["станет: %s" % _mine_text(r, q) for r, q in zip(new, no)]
    mi = lambda rows, odds: _odds_by_code([[r[3], r[6], (r[4] + r[5]) / 2.0] for r in rows], odds)
    _bal_codes(rep, "копание %s/%d" % (name, typ), mi(old, oo), mi(new, no))
    _mine_bal_rows(rep, "копание %s/%d" % (name, typ), old, new)
    if sum(no) < 1 - 1e-9:
        rep["warnings"].append("копание: сумма долей %s — в остатке добыча пустая" % pct(sum(no)))


# =====================================================================================================================
# Справка редактору (только чтение) и расхождения
# =====================================================================================================================
def _ref_state(rels):
    sn = E.Snap(md5=E.live_md5(rels))
    return sn, E.SrvState(sn)


def search(q, limit=80):
    """Мобы по id или части имени (RU/EN порта, корейское из записи)."""
    sn, st = _ref_state([E.GS[0] + "\\" + AI_GS])
    t = st.get(E.GS[0], AI_GS)
    q = (q or "").strip().lower()
    out = []
    for mid, off in sorted(ai_index(t).items()):
        nm, ko = mob_name(mid), ko_name(t.orig, off)
        if q and q != str(mid) and q not in nm.lower() and q not in ko.lower():
            continue
        out.append({"id": mid, "name": nm, "ko": ko, "level": t.orig[off + O_LVL], "exp": struct.unpack_from("<i", t.orig, off + O_EXP)[0],
                    "drops": len(drop_rows(t.orig, off))})
        if len(out) >= limit:
            break
    return {"rows": out, "total": len(ai_index(t))}


def lookup_mob(mid):
    rels = [r for f, s in copies() for r in [f + "\\" + s]]
    npc = E.folders("NPC")
    sn, st = _ref_state(rels + [n + "\\" + ITM for n in npc])
    t = st.get(E.GS[0], AI_GS)
    off = ai_index(t).get(mid)
    if off is None:
        raise OpRefused("моба %d нет в Monster.ai" % mid)
    b = t.orig
    mode, rgate = b[off + O_MODE], struct.unpack_from("<b", b, off + O_RGATE)[0]
    rows = drop_rows(b, off)
    odds = main_odds(mode, rgate, rows)
    m = money(b, off)
    w = world(b, off)
    itm = sn.raw(npc[0] + "\\" + ITM)
    wr = world_rows(itm, w[0]) or []
    g, wo = world_odds(w[2], wr)
    qr = quest_rows(b, off)
    nq = quest_len(qr)
    diff = {}
    for f, s in copies()[1:]:
        tt = st.get(f, s)
        o2 = ai_index(tt).get(mid)
        offs = [] if o2 is None else [i for i in range(REC) if tt.orig[o2 + i] != b[off + i]]
        diff[f] = {"missing": o2 is None, "same": o2 is not None and not offs, "offs": ",".join(map(str, offs))[:120]}
    nm = lambda c: E._name(c) if c > 0 else "—"
    return {"id": mid, "name": mob_name(mid), "ko": ko_name(b, off), "level": b[off + O_LVL], "hp": struct.unpack_from("<i", b, off + O_HP)[0],
            "exp": struct.unpack_from("<i", b, off + O_EXP)[0], "mode": mode, "rgate": rgate,
            "money": {"min": m[0], "max": m[1], "chance": m[2], "p": p_pct(m[2])},
            "drop": [{"item": r[0], "name": nm(r[0]), "rate": r[1], "count": r[2], "p": q} for r, q in zip(rows, odds)],
            "world": {"index": w[0], "count": w[1], "gate": w[2], "p_gate": g, "records": len(itm) // WREC,
                      "items": [{"item": r[0], "name": nm(r[0]), "rate": r[1], "p": q} for r, q in zip(wr, wo)]},
            "quest": {"gate": b[off + O_QGATE], "rows": [{"quest": r[0], "step": r[1], "cond": r[2], "item": r[3], "name": nm(r[3]),
                                                          "rate": r[4], "p": p_pct(r[4])} for r in qr[:nq]]},
            "copies": diff, "md5": {r: sn.md5.get(r, "")[:8] for r in rels}}


def lookup_world(idx):
    npc = E.folders("NPC")
    sn, _st = _ref_state([npc[0] + "\\" + ITM])
    itm = sn.raw(npc[0] + "\\" + ITM)
    wr = world_rows(itm, idx)
    if wr is None:
        raise OpRefused("записи %d в WorldDropItem.itm нет (записей %d)" % (idx, len(itm) // WREC))
    sh = p_cumulative([r[1] for r in wr])
    return {"index": idx, "records": len(itm) // WREC, "items": [{"item": r[0], "name": E._name(r[0]), "rate": r[1], "share": q}
                                                                for r, q in zip(wr, sh)]}


def lookup_mine(ident):
    name, _sep, typ = str(ident).partition(":")
    canon = next((m for m in MINING_MAPS if m.lower() == name.strip().lower()), None)
    out = {"maps": list(MINING_MAPS), "types": MINE_TYPES}
    if canon is None:
        return out
    typ = _ident_int(typ or "0", "тип копания: нужно целое число")       # ★ ревизия 35 К-4: тип вне 0…MINE_TYPES−1 — отказ 409, а не 500
    if not 0 <= typ < MINE_TYPES:
        raise OpRefused("типа копания %d нет (типов %d: 0…%d)" % (typ, MINE_TYPES, MINE_TYPES - 1))
    npc = E.folders("NPC")
    sub = mine_sub(canon, typ)
    sn, st = _ref_state([n + "\\" + sub for n in npc])
    t = st.get(npc[0], sub)
    same = len({sn.md5.get(n + "\\" + sub) for n in npc}) == 1
    why = ""
    try:
        rows, nsec = mine_check_file(t)
    except OpRefused as ex:
        from core import i18n
        rows, nsec, why = mine_rows(t.orig[:MREC]), len(t.orig) // MREC, i18n.tr(str(ex))
    odds = mine_odds(rows)
    out.update({"map": canon, "type": typ, "file": sub, "sectors": nsec, "uniform": not why, "why": why, "copies_same": same,
                "rows": [{"item": r[3], "name": E._name(r[3]), "lvmin": r[0], "lvmax": r[1], "exp": r[2], "cmin": r[4], "cmax": r[5],
                          "rate": r[6], "mask": "%016x" % r[7], "p": q} for r, q in zip(rows, odds)]})
    return out


def _ident_int(v, msg):
    """Число из запроса справки; не число — OpRefused(msg) (409), а не ValueError (500)."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        raise OpRefused(msg)


def lookup(what, ident):
    if what == "mobs":
        return search(ident)
    if what == "mob":
        return lookup_mob(_ident_int(ident, "моб: нужно целое число"))
    if what == "world":
        return lookup_world(_ident_int(ident, "запись WorldDropItem: нужно целое число"))
    return lookup_mine(ident)


def snapshot(snap):
    """Клиентской половины у области нет."""


def parse(cli, d):
    """Клиентской половины у области нет."""


def divergence(ev, cli, sec):
    """Копии Monster.ai: у копий одной базы записи обязаны совпадать; у Indun_GameServer — своя база (список мобов с отличиями)."""
    rows = []
    t0 = ev.st.get(E.GS[0], AI_GS)
    i0 = ai_index(t0)
    for f, s in copies()[1:]:
        t = ev.st.get(f, s)
        try:
            ii = ai_index(t)
        except OpRefused as ex:
            rows.append({"id": f, "why": str(ex)})
            continue
        dif = [m for m, o in sorted(ii.items()) if m not in i0 or t.orig[o:o + REC] != t0.orig[i0[m]:i0[m] + REC]]
        miss = sorted(set(i0) - set(ii))
        if dif or miss:
            rows.append({"id": f, "why": "%s: записей с отличиями %d (%s), нет записей %d — своя база копии" % (
                s, len(dif), ", ".join(map(str, dif[:12])), len(miss))})
    sec("mobs", "монстры: копии Monster.ai отличаются от GameServer", rows,
        "Indun_GameServer — своя база (квест-записи); правка ложится на каждую копию по её байтам")
