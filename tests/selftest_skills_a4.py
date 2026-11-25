# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_skills_a4.py — самотест шага А4.7 «Навыки и классы» (20.11.2026, domains/cs_kinds/skilldata.py).

offline(check)       — подменная стойка selftest_shops.synthetic() + свои SkillInfo.sif ×6 (у Indun другой «следующий» навык 504), SkillPointTable,
                       ClassStat, ExpTable трёх GS, клиентский снимок skill_info / charexp, подставные персонажи Joy1: числа навыка, макс. уровень и
                       требование дерева, порог дерева, характеристики класса, опыт уровня; отказы (эффекта нет, перенос через край, отличия копии,
                       не навык игрока, максимум ниже уровня держателя и ниже открытия «следующего», требование 0 → > 0 у изученного, пороги
                       SPT вниз и вверх, дубль строки SPT, опыт ниже порога и не растущая таблица, Joy1 не прочитан), итог набора по копиям
                       (after_run), «опыт до следующего» соседних уровней одной правкой, перепроверка перед выкладкой и откатом (apply_guard),
                       AsdaSkillBase после выкладки (after_server), план клиента (ведомости, подставной генератор), расхождения, справка,
                       переводы службы и веба.
sandbox(check, ldb)  — путь набора целиком: создать → проверить → утвердить (сильная — второе подтверждение) → НАСТОЯЩИЙ сухой прогон
                       deploy_changeset (SkillInfo ×6 копий, ExpTable ×3) → клиент (копии skill_info.csv и charexp.csv, ведомости, DT подставной
                       очередью UE) → выкладка (появился персонаж с опытом ниже нового порога — отказ до объявления) → выкладка →
                       AsdaSkillBase → откат сервера и клиента (всё вернулось).
live(check)          — только чтение и сухие прогоны: md5 копий, справка (держатели из Joy1), живая оценка набора, план клиента НАСТОЯЩИМ
                       генератором ItemDB (md5 порта до = после), НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH, перепроверка по манифесту,
                       расхождения (AsdaSkillBase = SkillInfo).
Ни рестартов стойки, ни записи в таблицы стойки или порта, ни записи в Joy1. Побочных эффектов при импорте нет.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile

BS = "\\"
GS3 = ("GameServer", "Indun_GameServer", "Ch2_GameServer")
NPC3 = ("NpcServer", "Indun_NpcServer", "Ch2_NpcServer")
SIF_GS, SIF_NPC = "SkillTable_Info" + BS + "SkillInfo.sif", "Skill" + BS + "Skillinfo.sif"
SPT, CSTAT, EXPT = "SkillTable_Info" + BS + "SkillPointTable.spt", "ConfigSet" + BS + "ClassStat.txt", "ConfigSet" + BS + "ExpTable.txt"
N = 520
ET = [0, 200, 600, 1200, 2000, 3000, 4200, 5600, 7200, 9000]        # ET[k−1] = опыт начала уровня k


def _md5(b):
    return hashlib.md5(b).hexdigest()


def sif(indun=False):
    b = bytearray(209 * N)
    for i in range(N):
        o = 209 * i
        struct.pack_into("<h", b, o, i)
        b[o + 2:o + 2 + len(b"skill%d" % i)] = b"skill%d" % i
        for x in (72, 89, 106, 191, 194, 197, 200, 203, 206):
            struct.pack_into("<h", b, o + x, -1)
        if 500 <= i <= 509:
            struct.pack_into("<Q", b, o + 123, 0 if i == 508 else 2)      # бит 1 = Job 1; 508 — не навык игрока
            b[o + 189], b[o + 43], b[o + 190] = 1, 5, 0 if i <= 502 else 5
            struct.pack_into("<i", b, o + 47, 5000)
            b[o + 53], b[o + 55] = 3, 1
            struct.pack_into("<hh", b, o + 58, 10, 2)
            struct.pack_into("<hh", b, o + 62, 100, 20)
            b[o + 66], b[o + 68] = 90, 50
            struct.pack_into("<h", b, o + 72, 10)
            struct.pack_into("<hh", b, o + 74, 5, 1)
            struct.pack_into("<ii", b, o + 78, 3000, 100)
    struct.pack_into("<hB", b, 209 * 503 + 191, 505, 3)                    # 503 открывает 505 на уровне 3
    struct.pack_into("<hB", b, 209 * 506 + 200, 503, 4)                    # 506 нужен 503 уровня 4
    if indun:
        struct.pack_into("<hB", b, 209 * 504 + 191, 507, 4)                # только у Indun: 504 открывает 507 на уровне 4
    return bytes(b)


def spt():
    rows = [(1, 5, [503]), (1, 10, [504]), (2, 5, [505])]
    return b"".join(struct.pack("<bb6h", t, s, *(sk + [-1] * (6 - len(sk)))) for t, s, sk in rows)


def cstat():
    lines = ["20"] + ["%d\t%d\t%s" % (c, l, "\t".join(str(10 * l + c + k) for k in range(6))) for c in range(4) for l in range(1, 6)]
    return ("\r\n".join(lines) + "\r\n").encode("latin-1")


def expt():
    return ("\r\n".join(["10"] + ["%d\t%d " % (k + 1, v) for k, v in enumerate(ET)]) + "\r\n").encode("latin-1")


CJAST = "SkillTable_Info" + BS + "ChangeJobAddSkillTable.txt"


def cjast():
    """ChangeJobAddSkillTable: строка 1 (новичок → боец) — 500; строка 4 (подкласс) — 501 (ревизия 39 С-3: требование 0, держателей нет)."""
    return b"1\t1\t500\r\n4\t1\t501\r\n"


def stack_files():
    out = {}
    for g in GS3:
        out[g + BS + SIF_GS] = sif(indun=g == "Indun_GameServer")
        out[g + BS + SPT], out[g + BS + CSTAT], out[g + BS + EXPT] = spt(), cstat(), expt()
        out[g + BS + CJAST] = cjast()
    for n in NPC3:
        out[n + BS + SIF_NPC] = sif(indun=n == "Indun_NpcServer")
    return out


def cli_data():
    b = sif()
    sk = {i: [i, b[209 * i + 41:209 * (i + 1)].hex()] for i in range(500, 510)}
    c = bytearray(bytes.fromhex(sk[509][1]))
    struct.pack_into("<i", c, 47 - 41, 7000)                               # клиент 509 уже расходился (откат)
    sk[509][1] = bytes(c).hex()
    ex = {}
    for r, v in enumerate(ET):
        ex[r] = [v - (ET[r - 1] if r else 0), v, 0]
    return sk, ex


JOY = {(75001, 1): {"name": "Alice", "lvl": 8, "exp": 6000, "cls": 1, "job": 1, "sub": 0, "skills": {503: 5, 500: 3}},
       (75002, 1): {"name": "Bob", "lvl": 5, "exp": 2100, "cls": 1, "job": 1, "sub": 0, "skills": {503: 2}},
       (75003, 1): {"name": "Carl", "lvl": 3, "exp": 650, "cls": 1, "job": 1, "sub": 0, "skills": {}}}


TPL = {502: ["dbo.Fighter"]}                     # подставные шаблоны UPCharSkillinit (ревизия 39 С-3)


class _Joy:
    """Подмена персонажей Joy1 на время блока; extra — «появившиеся после проверки» (when — с какого момента: ревизия 39 Н-3);
    tpl / tpl_fail — шаблоны Joy1.dbo.Fighter/Ranger/Mage (ревизия 39 С-3)."""

    def __init__(self, extra=None, fail=False, when=None, tpl=None, tpl_fail=False):
        self.extra, self.fail, self.when = dict(extra or {}), fail, when
        self.tpl, self.tpl_fail = dict(TPL if tpl is None else tpl), tpl_fail

    def __enter__(self):
        from domains.cs_kinds import skilldata as K
        self.saved = (K.joy_chars, K.joy_templates)
        me = self

        def joy_chars():
            if me.fail:
                joy_chars.last_error = "нет связи с Joy1 (самотест)"
                return None
            joy_chars.last_error = None
            d = json.loads(json.dumps({"%d/%d" % k: v for k, v in JOY.items()}))
            out = {}
            for k, v in d.items():
                v["skills"] = {int(s): l for s, l in v["skills"].items()}
                out[tuple(int(x) for x in k.split("/"))] = v
            if me.when is None or me.when():
                out.update({k: dict(v, skills=dict(v["skills"])) for k, v in me.extra.items()})
            return out

        def joy_templates():
            if me.tpl_fail:
                joy_templates.last_error = "нет связи с Joy1 (самотест)"
                return None
            joy_templates.last_error = None
            return {k: list(v) for k, v in me.tpl.items()}
        joy_chars.last_error = joy_templates.last_error = None
        K.joy_chars, K.joy_templates = joy_chars, joy_templates
        return self

    def __exit__(self, *a):
        from domains.cs_kinds import skilldata as K
        K.joy_chars, K.joy_templates = self.saved
        return False


_EVS = []                                         # оценки наборов (ревизия 39: перевод всех их отказов и предупреждений)


def _ev(items):
    from domains import shopdata as SD
    e = SD.Eval([{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], False).run()
    _EVS.append(e)
    return e


def _errs(ev):
    return [e for r in ev.positions for e in r["errors"]]


def _cs_man(e, cid, items):
    from domains import shopcs
    cs = {"id": cid, "items": [{"pos": i + 1, "kind": k, "params": p} for i, (k, p) in enumerate(items)], "check": e.summary()}
    _mp, m = shopcs.build_server_out(cs, e)
    cs["server_tag"] = m["tag"]
    return cs, m


class _FakeWriter:
    """Подставной db.GameWriter (asda_ops): AsdaSkillBase в памяти."""
    table, updates, force, committed = {}, [], {}, False

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def rows(self, sql, params=()):
        return [dict(v, Skillidx=k) for k, v in sorted(_FakeWriter.table.items())]

    def execute(self, sql, params=()):
        cols = re.search(r"SET (.+) WHERE", sql).group(1).split(", ")
        cols = [c.split(" = ")[0] for c in cols]
        n = len(cols)
        new, sid, old = params[:n], params[n], params[n + 1:]
        if sid in _FakeWriter.force:
            return _FakeWriter.force[sid]
        row = _FakeWriter.table.get(sid)
        if row is None or [row[c] for c in cols] != list(old):
            return 0
        row.update(dict(zip(cols, new)))
        _FakeWriter.updates.append((sid, dict(zip(cols, new))))
        return 1

    def commit(self):
        _FakeWriter.committed = True


def _base_rows(buf):
    from domains.cs_kinds import skilldata as K
    return {s: {c: struct.unpack_from(f, buf, s * 209 + o)[0] for c, o, f in K.BASE_COLS} for s in range(500, 510) if s != 508}


# ---------------------------------------------------------------------------------------------------------- офлайн
def offline(check):
    import selftest_shops as T
    from domains import shopdata as SD
    from domains.cs_kinds import skilldata as K
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    check("А4.7 реестр: область «skilldata» (за ней — только «Карты» А4.8), виды skill.num / skill.req / skill.spt / class.stat / level.exp, права data.edit / "
          "data.apply, гейт баланса; SkillInfo GS и NpcServer, SPT, ClassStat, ExpTable — per_copy; выкладчик пускает их во всех копиях; "
          "ведомости skill_info.sif / charexp — в реестре движка",
          SD.AREAS[SD.AREAS.index(K) + 1:] == [a for a in SD.AREAS if a.AREA in ("mapdata", "events", "patchcfg")]   # ★ А4.8: за ней — «Карты»; ★ А5.4 — «Счастливые часы»
          and set(K.KINDS) == {"skill.num", "skill.req", "skill.spt", "class.stat", "level.exp"}
          and SD.area_perm("skill.num", "apply") == "data.apply" and SD.area_perm("level.exp", "edit") == "data.edit" and K.BALANCE_GATE
          and all(SD.SRV_POLICY[x] == "per_copy" for x in (SIF_GS, SIF_NPC, SPT, CSTAT, EXPT))
          and all(g + BS + x in dc.ALLOWED for g in GS3 for x in (SIF_GS, SPT, CSTAT, EXPT)) and all(n + BS + SIF_NPC in dc.ALLOWED for n in NPC3)
          and SD.LEDGER_TABLES.get("skill_info.sif") == "skill_info.sif" and SD.LEDGER_TABLES.get("charexp") == "charexp.bin"
          and SD.ledger_paths("skill_info.sif")[0].endswith("skill_info.sif.csv"))
    bad = []
    for kind, p in (("skill.num", {"id": 499, "fields": {"mp0": 1}}), ("skill.num", {"id": 503, "fields": {"mp0": -1}}),
                    ("skill.num", {"id": 503, "fields": {"tree": 2}}), ("skill.num", {"id": 503, "fields": {}}),
                    ("skill.num", {"id": 503, "fields": {"dist": 256}}), ("skill.req", {"id": 503, "fields": {"max": 0}}),
                    ("skill.req", {"id": 503, "fields": {"mp0": 3}}), ("skill.spt", {"row": 0, "sum": 128}), ("skill.spt", {"row": 0, "sum": 0}),
                    ("class.stat", {"cls": 4, "lvl": 1, "fields": {"str": 1}}), ("class.stat", {"cls": 1, "lvl": 1, "fields": {"str": 40000}}),
                    ("level.exp", {"lvl": 1, "exp": 5}), ("level.exp", {"lvl": 3, "exp": 0})):
        try:
            SD.norm(kind, p)
            bad.append((kind, p))
        except Exception:
            pass
    check("А4.7 позиции: неверные параметры — отказ (навык < 500, отрицательное число, неизвестное или пустое поле, u8 > 255, макс. уровень 0, "
          "поле не своего вида, порог SPT вне 1…127, класс 4, характеристика > 32767, уровень 1 и опыт 0)", not bad, bad)
    v = K.vals(sif(), 503 * 209)
    check("А4.7 значения уровня — как sub_4760E0: MP 10 + 2·N, сила 100 + 20·N, шанс > 100 зажимается до 100, перенос через край i16 — "
          "неисправность записи", K.level_row(v, 5)["mp"] == 20 and K.level_row(v, 5)["ev"] == 200
          and K.level_row(dict(v, sp0=95, spN=3), 5)["sp"] == 100 and "ovf_mp" in K.issues(503, dict(v, mpN=8000))
          and K.issues(503, v, sif()) == {})
    with T.synthetic() as (raw, md5, cli):
        for rel, b in stack_files().items():
            raw[rel], md5[rel] = b, _md5(b)
        cli.skillcli, cli.expcli = cli_data()
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tempfile.mkdtemp(prefix="asda_t47_cs_")
        real_joy = K.joy_chars                         # настоящий — для проверки слияния корзины (ревизия 39 С-1)
        try:
            with _Joy():
                _offline_num(check)
                _offline_req(check)
                _offline_spt_cls_exp(check)
                _offline_guard(check, raw, md5)
                _offline_fix39(check, raw, md5, real_joy)
                d = {s["key"]: s for s in SD.divergence(areas=("skilldata",))["sections"]}
                rows = d["skills"]["rows"]
                check("А4.7 расхождения: раздел skills — клиент 509 ≠ сервер (откат), Indun SkillInfo и NpcServer Indun — своя база копии",
                      list(d) == ["skills"] and any(r["id"] == 509 and "cool" in r.get("field", "") for r in rows)
                      and any("Indun_GameServer" in r["why"] for r in rows) and any("Indun_NpcServer" in r["why"] for r in rows), rows[:4])
                lk = K.lookup("skill", "503")
                sr = K.lookup("skills", "")
                ls = K.lookup("spt", "")
                lc = K.lookup("classstat", "1")
                le = K.lookup("exptable", "")
                check("А4.7 справка: карточка навыка 503 (поля, значения уровней 0…5, «открывает 505 на ур. 3», «нужен 506 ур. 4», держатели, "
                      "поля эффекта 2 — с причиной «эффекта нет»), поиск — 9 навыков игрока (508 — нет), SPT 3 строки, класс 1 — 5 уровней, "
                      "опыт — 10 уровней = клиенту",
                      len(lk["levels"]) == 6 and lk["levels"][5]["mp"] == 20 and lk["next"] == [(505, 3)] and lk["users"] == [(506, 4)]
                      and len(lk["holders"]) == 2 and any(f[0] == "s2v0" and f[6] for f in lk["fields"]) and len(sr["rows"]) == 9
                      and len(ls["rows"]) == 3 and len(lc["rows"]) == 5 and len(le["rows"]) == 10
                      and all(r["exp"] == r["client"] for r in le["rows"]), (len(sr["rows"]), lk.get("next"), lk.get("users")))
            _offline_after_server(check, raw, md5)
            _offline_plan(check)
        finally:
            shutil.rmtree(SD.CS_DIR, ignore_errors=True)
            SD.CS_DIR = saved_dir
    _offline_tr(check)


def _line(raw, k):
    return raw.split(b"\r\n")[1 + k].split(b"\t")


def _offline_num(check):
    from domains.cs_kinds import skilldata as K
    e = _ev([("skill.num", {"id": 503, "fields": {"mp0": 30, "cool": 6000, "s1v0": 6}})])
    nb = e.new_bytes()
    p = e.positions[0]
    ok6 = len(nb) == 6 and all(struct.unpack_from("<h", b, 503 * 209 + 58)[0] == 30 and struct.unpack_from("<i", b, 503 * 209 + 47)[0] == 6000
                               for b in nb.values())
    check("А4.7 числа навыка: правка на 6 копий (3 GS + 3 NpcServer) по байтам, Indun сохранил свой «следующий» у 504; клиент — три правки "
          "csv_hex_bytes skill_info (+47, +58, +74); держатели — предупреждение со списком; MP ×3 — сильная правка",
          not _errs(e) and ok6 and struct.unpack_from("<h", nb["Indun_GameServer" + BS + SIF_GS], 504 * 209 + 191)[0] == 507
          and sorted(c["off"] for c in p["client"]) == [47, 58, 74] and all(c["type"] == "csv_hex_bytes" for c in p["client"])
          and any("Alice (75001/1, ур. 8, навык ур. 5)" in w for w in p["warnings"])
          and any(b["strong"] for b in e.balance if "MP" in b["what"]), (_errs(e), p["warnings"], e.balance))
    refuse = {
        "эффекта 2 нет": ("skill.num", {"id": 503, "fields": {"s2v0": 3}}),
        "перенос через край": ("skill.num", {"id": 503, "fields": {"mpN": 8000}}),
        "не навык игрока": ("skill.num", {"id": 508, "fields": {"mp0": 3}}),
        "менять нечего": ("skill.num", {"id": 503, "fields": {"mp0": 10}}),
        "навыка 530 нет": ("skill.num", {"id": 530, "fields": {"mp0": 3}}),
        "нет в skill_info клиента": ("skill.num", {"id": 505, "fields": {"mp0": 3}}),
    }
    from domains import shopdata as SD
    cl = SD.Client.load()
    got = {}
    for k, (kind, pr) in refuse.items():
        hid = cl.skillcli.pop(505) if k == "нет в skill_info клиента" else None
        try:
            ee = _ev([(kind, pr)])
        finally:
            if hid is not None:
                cl.skillcli[505] = hid
        got[k] = any(k in x for x in _errs(ee)) and not ee.new_bytes()
    check("А4.7 числа навыка — 6 отказов: поле эффекта без состояния (смысл не подтверждён), перенос через край на макс. уровне, не навык "
          "игрока, «менять нечего», навыка нет в таблице, навыка нет у клиента — стойка не тронута", all(got.values()), got)
    e = _ev([("skill.num", {"id": 509, "fields": {"cool": 6000, "mp0": 11}})])
    check("А4.7 клиент уже расходился (509: откат клиента 7000 ≠ 5000): предупреждение «уже расходился (cool)», клиент — оба поля позиции",
          not _errs(e) and any("уже расходился с сервером (cool)" in w for w in e.positions[0]["warnings"])
          and sorted(c["off"] for c in e.positions[0]["client"]) == [47, 58], (_errs(e), e.positions[0]["warnings"]))


def _offline_req(check):
    refuse = {
        "уровень выше нового максимума 4": ("skill.req", {"id": 503, "fields": {"max": 4}}),
        "навык 505 открывается на уровне 3": ("skill.req", {"id": 503, "fields": {"max": 2}}),
        "сброс навыков сломался бы": ("skill.req", {"id": 500, "fields": {"need": 5}}),
    }
    got = {}
    for k, (kind, pr) in refuse.items():
        ee = _ev([(kind, pr)])
        got[k] = any(k in x for x in _errs(ee)) and not ee.new_bytes()
    with _Joy(fail=True):
        ef = _ev([("skill.req", {"id": 503, "fields": {"max": 4}})])
    check("А4.7 требования — отказы: максимум ниже уровня держателя (Alice 5 > 4), максимум ниже уровня, на котором навык открывает 505, "
          "требование дерева 0 → 5 у изученного навыка 500 (сброс удалил бы его), Joy1 не прочитан — «не прочитаны»",
          all(got.values()) and any("не прочитаны" in x for x in _errs(ef)), (got, _errs(ef)))
    # ★ ревизия 39 С-2: 503 стоит в строке 0 SkillPointTable — его требование > 0 → 0 теперь отказ; «> 0 → 0» проверяется на 506 (не в SPT)
    e = _ev([("skill.req", {"id": 506, "fields": {"need": 0, "max": 7}}), ("skill.req", {"id": 504, "fields": {"need": 9}})])
    a, b = e.positions
    check("А4.7 требования: 506 требование 5 → 0 (сильная всегда, type) и макс. 5 → 7 — правка 6 копий, клиент +43 и +190; предупреждения "
          "«останется изученным уровнем 0» и «проверьте числа уровней»; 504 требование 5 → 9 — правка (у держателей 504 нет) и предупреждение "
          "«порог строки 1 SkillPointTable (10) и требование 9 разошлись» (ревизия 39 С-2)",
          not _errs(e) and sorted(c["off"] for c in a["client"]) == [43, 190] and any(x["kind"] == "type" and x["strong"] for x in e.balance)
          and any("уровнем 0" in w for w in a["warnings"]) and any("проверьте числа уровней 6…7" in w for w in a["warnings"])
          and any("строка 1 SkillPointTable (дерево 1) выдаёт навык 504 при сумме 10, а его требование дерева 9 — порог строки" in w
                  for w in b["warnings"])
          and all(bb[506 * 209 + 43] == 7 and bb[504 * 209 + 190] == 9 for bb in e.new_bytes().values()), (_errs(e), e.balance, b["warnings"]))
    e = _ev([("skill.req", {"id": 503, "fields": {"need": 9}})])
    check("А4.7 требование растёт выше вложенного у держателей: предупреждение со списком (Bob, сумма дерева 2 < 9)",
          not _errs(e) and any("Bob (75002/1" in w and "5254 код 6" in w for w in e.positions[0]["warnings"]), e.positions[0]["warnings"])
    e = _ev([("skill.req", {"id": 504, "fields": {"max": 3}})])
    check("А4.7 итог набора (after_run): макс. 504 → 3 — у GameServer нет «следующего», а у Indun 504 открывает 507 на уровне 4 — отказ "
          "«копия Indun_GameServer: навык 507 открывается на уровне 4…» (и NpcServer Indun)",
          any(x.startswith("копия Indun_GameServer: навык 507 открывается на уровне 4") for x in _errs(e))
          and any(x.startswith("копия Indun_NpcServer: ") for x in _errs(e)), _errs(e))


def _offline_spt_cls_exp(check):
    refuse = {
        "не получат их никогда": ("skill.spt", {"row": 1, "sum": 7}),
        "снова уровнем 0": ("skill.spt", {"row": 0, "sum": 9}),
        "одна из двух не сработает": ("skill.spt", {"row": 1, "sum": 5}),
        "порог уже 5": ("skill.spt", {"row": 0, "sum": 5}),
        "строки 9 нет": ("skill.spt", {"row": 9, "sum": 5}),
        "опыт меньше (Bob (75002/1))": ("level.exp", {"lvl": 5, "exp": 2200}),
        "должна строго расти": ("level.exp", {"lvl": 6, "exp": 1500}),
        "записи «класс 1, уровень 9» нет": ("class.stat", {"cls": 1, "lvl": 9, "fields": {"str": 1}}),
    }
    got = {}
    for k, (kind, pr) in refuse.items():
        ee = _ev([(kind, pr)])
        got[k] = any(k in x for x in _errs(ee)) and not ee.new_bytes()
    check("А4.7 SPT / опыт / класс — 8 отказов: снижение порога (Alice сумма 8 в [7, 10), навыка 504 нет), повышение (Alice сумма 8 в [5, 9) "
          "с изученным 503 — обнулился бы), дубль дерева и порога, «менять нечего», строки нет, опыт ниже у персонажа уровня, таблица не "
          "растёт, записи класса нет", all(got.values()), got)
    e = _ev([("skill.spt", {"row": 0, "sum": 1}), ("class.stat", {"cls": 1, "lvl": 3, "fields": {"str": 99, "for": 50}}),
             ("level.exp", {"lvl": 7, "exp": 3100}), ("level.exp", {"lvl": 8, "exp": 4300})])
    nb = e.new_bytes()
    pc = e.positions[1]
    ce = [c for r in e.positions for c in r["client"]]
    e2n = {int(c["key"]): int(c["new"]) for c in ce if c["col"] == "ExpToNext"}
    check("А4.7 SPT / класс / опыт: порог 5 → 1 (сервер ×3 GS, клиента нет; предупреждение «навык 503 выдаётся раньше, чем его можно "
          "повышать» — ревизия 39 С-2); класс 1 ур. 3 — Сила и Удача ×3 GS, предупреждение «Carl … базу "
          "сервер возьмёт заново при входе»; опыт уровней 7 и 8 — ExpTable ×3, клиент CumExp строк 6 и 7 и «опыт до следующего» строк 6, 7, 8 "
          "одной правкой каждой (по итоговой таблице)",
          not _errs(e) and any("выдаёт навык 503 при сумме 1, а его требование дерева 5 — навык выдаётся раньше" in w
                               for w in e.positions[0]["warnings"]) and len([r for r in nb if r.endswith("SkillPointTable.spt")]) == 3 and nb["GameServer" + BS + SPT][1] == 1
          and _line(nb["GameServer" + BS + CSTAT], 7)[2] == b"99" and _line(nb["GameServer" + BS + CSTAT], 7)[7] == b"50" and any("Carl (75003/1, ур. 3)" in w for w in pc["warnings"])
          and _line(nb["Indun_GameServer" + BS + EXPT], 6)[1] == b"3100 " and e2n == {6: 3100 - 3000, 7: 4300 - 3100, 8: 7200 - 4300}
          and len(ce) == len({(c["key"], c["col"]) for c in ce}), (_errs(e), e2n, pc["warnings"]))


def _offline_guard(check, raw, md5):
    from domains.cs_kinds import skilldata as K
    items = [("skill.req", {"id": 504, "fields": {"max": 4}}), ("level.exp", {"lvl": 7, "exp": 4300}), ("skill.spt", {"row": 0, "sum": 1})]
    e = _ev(items)
    cs, m = _cs_man(e, 9471, items)
    ok0 = K.apply_guard(cs, "apply")
    late = {(75010, 1): {"name": "Late", "lvl": 7, "exp": 4250, "cls": 1, "job": 1, "sub": 0, "skills": {504: 5}},
            (75011, 1): {"name": "Late2", "lvl": 4, "exp": 1300, "cls": 1, "job": 1, "sub": 0, "skills": {500: 1}}}
    with _Joy(extra=late):
        ap = K.apply_guard(cs, "apply")
    with _Joy(fail=True):
        apf = K.apply_guard(cs, "apply")
    for rel, f in m["files"].items():
        raw[rel + ".bak_" + m["tag"]] = raw[rel]
        md5[rel + ".bak_" + m["tag"]] = f["base"]
        raw[rel] = open(f["local"], "rb").read()
        md5[rel] = f["new"]
    try:
        rb = K.apply_guard(cs, "rollback")
    finally:
        for rel in m["files"]:
            raw[rel] = raw.pop(rel + ".bak_" + m["tag"])
            md5[rel] = md5.pop(rel + ".bak_" + m["tag"])
    check("А4.7 перепроверка (уроки ревизий 36–38): по манифесту набора — чисто; после проверки появились держатель 504 уровня 5 (макс. → 4), "
          "персонаж уровня 7 с опытом 4250 (< 4300) и Late2 с суммой дерева 1 в [1, 5) без навыка 503 — выкладка: три причины; не прочитано — "
          "«не прочитаны»; откат (живая = набор, база в .bak): порог 1 → 5 при сумме дерева 2 у Bob с изученным 503 — причина «снова уровнем 0» "
          "(опыт и максимум назад — не опасно)",
          ok0 == [] and len(ap) == 3 and any("уровень выше нового максимума 4" in x for x in ap) and any("Late (75010/1)" in x and "опыт" in x for x in ap)
          and any("не получат их никогда" in x for x in ap) and apf and "не прочитаны" in apf[0] and len(rb) == 1 and "снова уровнем 0" in rb[0]
          and "Bob (75002/1)" in rb[0], (ok0, ap, apf, rb))


DEL_A = (75030, 1, "2026-11-01 10:00:00.000")
DEL_B = (75031, 2, "2026-11-02 11:00:00.000")
TRASH = {DEL_A: {"name": "Dora [Del_Charinfo 2026-11-01 10:00]", "lvl": 4, "exp": 1250, "cls": 1, "job": 1, "sub": 0, "skills": {504: 5},
                 "deleted": DEL_A[2]},
         DEL_B: {"name": "Edda [Del_Charinfo 2026-11-02 11:00]", "lvl": 6, "exp": 3500, "cls": 1, "job": 1, "sub": 0, "skills": {500: 4, 501: 4},
                 "deleted": DEL_B[2]}}


class _FakeReader:
    """Подставной db.GameReader (asda_admin): Charinfo / CharSkill и корзина Del_* (ревизия 39 С-1)."""
    sqls = []

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def rows(self, sql, params=()):
        _FakeReader.sqls.append(sql)
        if "Del_CharSkill" in sql:
            return [{"u": 75030, "c": 1, "ek": DEL_A[2], "s": 504, "lv": 5}, {"u": 75030, "c": 9, "ek": DEL_A[2], "s": 503, "lv": 1}]
        if "Del_Charinfo" in sql:
            return [{"u": 75030, "c": 1, "ek": DEL_A[2], "nm": "Dora", "lv": 4, "ex": 1250, "cl": 1, "jb": 1, "sb": 0}]
        if "CharSkill" in sql:
            return [{"u": 75030, "c": 1, "s": 500, "lv": 2}]
        return [{"u": 75030, "c": 1, "nm": "Dora2", "lv": 9, "ex": 9999, "cl": 1, "jb": 1, "sb": 0}]


def _offline_fix39(check, raw, md5, real_joy):
    """★ ревизия 39 (20.11): корзина удалённых в держателях (С-1), SPT-навык > 0 → 0 (С-2), будущие держатели (С-3), строка клиента до
    записи (К-1), повторная выдача уровнем 0 (К-2), отказы без «; » (Н-2), перепроверка после остановки в выкладчике (Н-3), --only (Н-4),
    закомментированные проверки (Н-1)."""
    import ast
    import contextlib
    import io
    from core import db, i18n
    from domains import shopcs, shopdata as SD
    from domains.cs_kinds import skilldata as K
    n_ev = len(_EVS)
    # --- С-1: настоящий joy_chars на подставном GameReader — корзина отдельным ключом, имя с меткой, навыки по ключу набора
    saved_r = db.GameReader
    db.GameReader, _FakeReader.sqls = _FakeReader, []
    try:
        jc = real_joy()
    finally:
        db.GameReader = saved_r
    dsql = [s for s in _FakeReader.sqls if "Del_" in s]
    check("ревизия 39 С-1: Joy1 — живые (Charinfo/CharSkill) и невосстановленная корзина (Del_Charinfo/Del_CharSkill без adm.CharRestored, ключ "
          "Userindex+Charidx+Edate): удалённый — отдельный держатель с меткой «[Del_Charinfo дата]», его навыки не смешаны с живым того же слота",
          jc and jc[(75030, 1)]["skills"] == {500: 2} and jc[(75030, 1, DEL_A[2])]["skills"] == {504: 5}
          and jc[(75030, 1, DEL_A[2])]["name"] == "Dora [Del_Charinfo 2026-11-01 10:00]" and jc[(75030, 1, DEL_A[2])]["deleted"]
          and len(dsql) == 2 and all("NOT EXISTS" in s and "adm.CharRestored" in s and "Edate" in s for s in dsql), (jc, dsql))
    with _Joy(extra=TRASH):
        got = {}
        for k, (kind, pr) in {"Dora [Del_Charinfo": ("skill.req", {"id": 504, "fields": {"max": 4}}),
                              "Edda [Del_Charinfo": ("skill.spt", {"row": 1, "sum": 7}),
                              "Dora [Del_Charinfo 2026-11-01 10:00] (75030/1)": ("level.exp", {"lvl": 4, "exp": 1300})}.items():
            ee = _ev([(kind, pr)])
            got[kind] = any(k in x for x in _errs(ee)) and not ee.new_bytes()
        lk = K.lookup("skill", "504")
    check("ревизия 39 С-1: корзина — держатель во всех проверках: макс. 504 → 4 (у Dora в корзине ур. 5, живых держателей нет), порог строки 1 "
          "10 → 7 (у Edda в корзине сумма 8 без 504), опыт начала уровня 4 → 1300 (у Dora 1250) — отказ с именем «[Del_Charinfo …]»; справка "
          "навыка помечает держателя из корзины", all(got.values()) and any(x["deleted"] for x in lk["holders"]), (got, lk["holders"]))
    # --- С-2: навык строки SPT, требование > 0 → 0 — отказ
    e = _ev([("skill.req", {"id": 503, "fields": {"need": 0}})])
    check("ревизия 39 С-2: навык 503 в строке 0 SkillPointTable — требование дерева 5 → 0 отказ (сброс оставит уровень 0, на пороге sub_47E9B0 "
          "выдаст его повторно уровнем 0)", any("выдаёт строка 0 SkillPointTable (дерево 1, порог 5)" in x for x in _errs(e)) and not e.new_bytes(),
          _errs(e))
    # --- С-3: будущие держатели по источнику
    got = {}
    for k, sid in (("ChangeJobAddSkillTable строка 4", 501), ("dbo.Fighter", 502), ("сброс навыков сломался бы", 500)):
        ee = _ev([("skill.req", {"id": sid, "fields": {"need": 5}})])
        got[k] = any(k in x for x in _errs(ee)) and not ee.new_bytes()
    with _Joy(tpl_fail=True):
        ef = _ev([("skill.req", {"id": 501, "fields": {"need": 5}})])
    hid = {r: raw.pop(r) for r in list(raw) if r.endswith(CJAST)}
    hm = {r: md5.pop(r) for r in list(md5) if r.endswith(CJAST)}
    try:
        em = _ev([("skill.req", {"id": 501, "fields": {"need": 5}})])
    finally:
        raw.update(hid)
        md5.update(hm)
    check("ревизия 39 С-3: требование 0 → 5 у навыка без держателей, который сервер выдаёт сам — отказ: 501 (ChangeJobAddSkillTable строка 4, "
          "подкласс), 502 (шаблон dbo.Fighter); 500 с держателем — прежний отказ; шаблоны не прочитаны и ChangeJobAddSkillTable нет — «вслепую "
          "не делается»", all(got.values()) and any("шаблоны Joy1.dbo.Fighter/Ranger/Mage не прочитаны" in x for x in _errs(ef))
          and any("ChangeJobAddSkillTable.txt не прочитан" in x for x in _errs(em)), (got, _errs(ef), _errs(em)))
    # --- К-2: повторная выдача уровнем 0
    jz = {(1, 1): {"name": "Zed", "lvl": 3, "skills": {503: 0, 500: 6}}, (2, 1): {"name": "Ann", "lvl": 3, "skills": {503: 5, 500: 1}},
          (3, 1): {"name": "Moe", "lvl": 3, "skills": {500: 6}}}
    z = K.spt_zero_regrant(jz, sif(), 1, [503], 5, 9)
    check("ревизия 39 К-2: порог 5 → 9 — персонаж с суммой 6 и навыком строки уровня 0 попадает в предупреждение «выдаст его снова» (уровень > 0 — "
          "отказ block_spt, без навыка — не касается); порог вниз — нет", z == [(1, 1, "Zed", 3)] and K.spt_zero_regrant(jz, sif(), 1, [503], 9, 5) == [],
          z)
    # --- К-1: строка клиента до записи ExpTable (соседняя позиция не видит записанный уровень)
    cl = SD.Client.load()
    keep = cl.expcli.pop(6)
    try:
        e = _ev([("level.exp", {"lvl": 7, "exp": 4300}), ("level.exp", {"lvl": 8, "exp": 4250})])
    finally:
        cl.expcli[6] = keep
    a, b = e.positions
    check("ревизия 39 К-1: строки 6 нет в charexp клиента — уровень 7 отказ ДО записи ExpTable: соседняя позиция уровня 8 (4250 > прежних 4200) "
          "проходит, итог набора по таблице без уровня 7", any("строки 6 нет в charexp" in x for x in a["errors"]) and not b["errors"]
          and _line(e.new_bytes()["GameServer" + BS + EXPT], 6)[1].strip() == b"4200", (a["errors"], b["errors"]))
    # --- Н-2: отказы без «; », переводятся целиком
    e1 = _ev([("level.exp", {"lvl": 6, "exp": 1500})])
    e2 = _ev([("level.exp", {"lvl": 10, "exp": 7000})])
    msgs = e1.errors + e2.errors
    allm = sorted({m for x in _EVS[n_ev:] for m in x.errors + [w for r in x.positions for w in r["warnings"]]})
    zero_w = ("у 2 перс. сумма дерева в [5, 9) и навык строки изучен уровнем 0: Zed (1/1, ур. 3); Dora [Del_Charinfo 2026-11-01 10:00] (75030/1, "
              "ур. 4) — на новом пороге сервер выдаст его снова (уровень останется 0, лишняя запись списка навыков боя — sub_475650)")
    stop_n = ("выкладка не выполнена, стойка не изменена: restart_stack.py вернул код 4; СТОП: перепроверка набора после остановки стойки не "
              "прошла — файлы не тронуты: опыт начала уровня 80 → 9 040: у 1 перс. этого уровня опыт меньше (Late (75020/1)) — их опыт оказался "
              "бы ниже начала их уровня, правка не делается")
    i18n.set_lang("en")
    try:
        en = [i18n.tr(x) for x in msgs]
        en_all = [(x, i18n.tr(x)) for x in allm + [zero_w, stop_n.replace("9 040", "9040")]]
    finally:
        i18n.set_lang("ru")
    left = [(a, b) for a, b in en_all if re.search("[А-Яа-яЁё]{3}", re.sub("«[^»]*»", "", b).replace("нет связи с Joy1 (самотест)", ""))]
    check("ревизия 39: переводы — все отказы и предупреждения оценок С-1…К-1 (корзина, SPT, источники навыка, «не прочитан»), предупреждение "
          "К-2 со списком через «; » и заметка отказа перепроверки после остановки — EN без русского", allm and not left, left[:3])
    src = open(K.__file__, encoding="utf-8").read()
    semi = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and getattr(node.exc.func, "id", "") == "OpRefused":
            semi += [c.value for c in ast.walk(node.exc) if isinstance(c, ast.Constant) and isinstance(c.value, str) and "; " in c.value]
    check("ревизия 39 Н-2: «таблица должна строго расти» — без «; », соседний уровень в шаблоне (и вариант последнего уровня); в EN внутри "
          "«позиция N: …» нет русского; ни один текст OpRefused в skilldata.py не содержит «; »",
          len(msgs) == 2 and not any("; " in x for x in msgs) and "уровень 7 — 4200)" in msgs[0] and "уровень 9 — 7200)" in msgs[1]
          and not any(re.search("[А-Яа-яЁё]{3}", x) for x in en) and not semi, (msgs, en, semi))
    _offline_h3_h4(check, shopcs, SD, contextlib, io)


def _offline_h3_h4(check, shopcs, SD, contextlib, io):
    # --- Н-3: перепроверка после остановки — выкладчик зовёт команду ASDA_CHANGESET_GUARD до копирования
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import deploy_changeset as dc
    import stack_layout
    tmp = tempfile.mkdtemp(prefix="asda_t47_g_")
    mp = os.path.join(tmp, "manifest.json")
    json.dump({"tag": "t", "files": {g + BS + SIF_GS: {"local": "x", "base": "a", "new": "b"} for g in stack_layout.GS_FOLDERS}},
              open(mp, "w", encoding="utf-8"))
    keys = ("ASDA_CHANGESET_MANIFEST", "ASDA_CHANGESET_MODE", "ASDA_CHANGESET_GUARD")
    saved = (sys.argv, {k: os.environ.get(k) for k in keys}, dc.base.main, getattr(dc.base, "MANIFEST", None), dc.base.flush,
             dc.base.check_roots)
    calls = []
    fail = json.dumps([sys.executable, "-c", "print('ПРИЧИНА: держатель появился (тест)'); raise SystemExit(1)"])
    ok = json.dumps([sys.executable, "-c", "raise SystemExit(0)"])
    res = {}
    try:
        dc.base.main = lambda: calls.append(list(sys.argv)) or 0
        for name, guard, argv, mode in (("отказ", fail, ["--apply"], ""), ("чисто", ok, ["--apply"], ""), ("без команды", None, ["--apply"], ""),
                                        ("сухой прогон", fail, [], ""), ("откат", fail, ["--apply"], "rollback")):
            os.environ["ASDA_CHANGESET_MANIFEST"], os.environ["ASDA_CHANGESET_MODE"] = mp, mode
            if guard:
                os.environ["ASDA_CHANGESET_GUARD"] = guard
            else:
                os.environ.pop("ASDA_CHANGESET_GUARD", None)
            sys.argv = ["deploy_changeset.py"] + argv
            n0, buf = len(calls), io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = dc.main()
            res[name] = (rc, len(calls) - n0, buf.getvalue())
    finally:
        sys.argv = saved[0]
        for k, v in saved[1].items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        dc.base.main, dc.base.MANIFEST, dc.base.flush, dc.base.check_roots = saved[2:]
        shutil.rmtree(tmp, ignore_errors=True)
    stop = "СТОП: перепроверка набора после остановки стойки не прошла — файлы не тронуты: держатель появился (тест)"
    ga = shopcs.guard_argv(12, "rollback", True)
    adm = open(shopcs.ADMIN_PY, encoding="utf-8").read()
    check("ревизия 39 Н-3: deploy_changeset — команда ASDA_CHANGESET_GUARD перед копированием: отказ — код 10, «СТОП: перепроверка…» с "
          "причиной, выкладчик не звался; чисто / без команды — выкладка; сухой прогон её не зовёт; откат тоже перепроверяется; команда панели — "
          "asda_admin.py changeset guard N --rollback --held-ok",
          res["отказ"][0] == 10 and res["отказ"][1] == 0 and stop in res["отказ"][2] and res["чисто"][:2] == (0, 1)
          and res["без команды"][:2] == (0, 1) and res["сухой прогон"][:2] == (0, 1) and res["откат"][:2] == (10, 0)
          and ga[1:] == [shopcs.ADMIN_PY, "changeset", "guard", "12", "--rollback", "--held-ok"] and 'sub == "guard"' in adm
          and stop.split(":")[1].strip().startswith(shopcs.GUARD_MARK), {k: v[:2] for k, v in res.items()})
    # --- Н-4: --only
    import inspect
    import selftest as ST
    cases = {"--live --only": ["--live", "--only"], "--only skills": ["--only", "skills"], "--live --only --x": ["--live", "--only", "--x"],
             "--live --only ,": ["--live", "--only", ","]}
    bad = {k: ST.parse_only(v) for k, v in cases.items()}
    good = ST.parse_only(["--live", "--only", "skills,data"])
    try:
        ST.main(live=False, only=["skills"])
        refused = False
    except SystemExit:
        refused = True
    srcq = inspect.getsource(ST.part_live_quick)
    check("ревизия 39 Н-4: --only без значения, без --live, со значением-ключом или пустыми именами — отказ (не полный прогон); --live --only "
          "skills,data — выборочно; main(--only без --live) — отказ; проба службы — stdin (python -), без scp и файла на сервере",
          all(v[0] is None and v[1] for v in bad.values()) and good == (["skills", "data"], None) and ST.parse_only([]) == (None, None)
          and refused and "input=PROBE" in srcq and "scp" not in srcq and "asda_a47_probe.py" not in srcq, (bad, good))
    # --- Н-1: условия самотестов не уходят в комментарий
    root = os.path.dirname(os.path.abspath(__file__))
    hits = []
    for fn in sorted(os.listdir(root)):
        if fn.endswith(".py"):
            for i, ln in enumerate(open(os.path.join(root, fn), encoding="utf-8"), 1):
                m = re.search(r"\)\s+#\s(.*)$|\]\s+#\s(.*)$|\w\s+#\s(.*)$", ln)
                tail = m and (m.group(1) or m.group(2) or m.group(3)) or ""
                if re.search(r"\b(and|or)\s+(set|SD\.\w+|len|all|any)\(|==\s*\{", tail):
                    hits.append("%s:%d" % (fn, i))
    check("ревизия 39 Н-1: в самотестах нет условий, съеденных комментарием («# … and set(…) == {…}»)", not hits, hits[:5])


def _offline_after_server(check, raw, md5):
    from core import db
    from domains.cs_kinds import skilldata as K
    saved = db.GameWriter
    _FakeWriter.table = _base_rows(raw["GameServer" + BS + SIF_GS])
    _FakeWriter.table[503]["Mpvalue"] = 9
    _FakeWriter.table.pop(505)
    _FakeWriter.table[600] = dict(_FakeWriter.table[500])
    _FakeWriter.updates, _FakeWriter.force, _FakeWriter.committed = [], {}, False
    db.GameWriter = _FakeWriter
    try:
        notes = K.after_server({"id": 1, "items": [{"pos": 1, "kind": "skill.num", "params": {"id": 503}}]}, "sync")
        none = K.after_server({"id": 2, "items": [{"pos": 1, "kind": "level.exp", "params": {}}]}, "sync")
        u1 = list(_FakeWriter.updates)
        _FakeWriter.table[503]["Mpvalue"] = 9
        _FakeWriter.force, _FakeWriter.committed = {503: 2}, False
        bad = K.after_server({"id": 3, "items": [{"pos": 1, "kind": "skill.req", "params": {"id": 503}}]}, "sync")
        c_bad = _FakeWriter.committed
    finally:
        db.GameWriter = saved
        _FakeWriter.force = {}
    check("А4.7 после выкладки: Joy1.dbo.AsdaSkillBase приводится к живому SkillInfo.sif — пишется только различающийся столбец (503 Mpvalue 9 → 10), "
          "нет строки 505 и лишняя 600 — заметки «пересоберите»; набор без навыков — ничего; UPDATE затронул 2 строки — без commit, «повторите "
          "changeset server-sync 3»",
          u1 == [(503, {"Mpvalue": 10})] and any("строк изменено 1" in n for n in notes) and any("нет навыков 505" in n for n in notes)
          and any("лишние строки 600" in n for n in notes) and none == [] and not c_bad and len(bad) == 1 and "server-sync 3" in bad[0],
          (notes, u1, bad))


def _offline_plan(check):
    """План клиента на НАСТОЯЩИХ CSV порта (только чтение) с подставным генератором (ведомости во временной папке)."""
    import selftest_shops as T
    from domains import shopdata as SD
    real_s, real_e = SD.CLIENT_FILES["skill_info.sif"], SD.CLIENT_FILES["charexp"]
    if not (os.path.isfile(real_s) and os.path.isfile(real_e)):
        return check("А4.7 план клиента — skill_info.csv и charexp.csv порта есть", False, (real_s, real_e))
    before = (SD.md5f(real_s), SD.md5f(real_e))
    rs = {r["SkillCode"]: r for r in csv.DictReader(open(real_s, encoding="utf-8-sig", newline=""))}["503"]
    hx = bytes.fromhex(rs["DataHex"])
    re_ = {r["_row"]: r for r in csv.DictReader(open(real_e, encoding="utf-8-sig", newline=""))}["10"]
    saved = dict(T.FAKE_COLS)
    T.FAKE_COLS["skill_info.sif"] = {"mpBase": (58, "i16"), "maxLevel": (43, "u8")}
    T.FAKE_COLS["charexp"] = {}
    try:
        with T.ledger_fixture():
            edits = [{"type": "csv_hex_bytes", "file": "skill_info.sif", "key_col": "SkillCode", "key": "503", "col": "DataHex", "off": 58,
                      "old": hx[58:60].hex(), "new": struct.pack("<h", struct.unpack_from("<h", hx, 58)[0] + 1).hex(), "src": "skilldata"},
                     {"type": "csv_cell", "file": "charexp", "key_col": "_row", "key": "10", "col": "CumExp", "old": re_["CumExp"],
                      "new": str(int(re_["CumExp"]) + 40), "src": "skilldata"}]
            plan = SD.client_plan(edits, 0)
            vo = [p for p in plan["files"] if p.replace("\\", "/").endswith("_value_overlay/skill_info.sif.csv")]
            ve = [p for p in plan["files"] if p.replace("\\", "/").endswith("_value_overlay/charexp.csv")]
            led = plan["_bytes"][vo[0]].decode("utf-8") if vo else ""
            bad = [dict(edits[0], old="ffff")]
            plan2 = SD.client_plan(bad, 0)
    finally:
        T.FAKE_COLS.clear()
        T.FAKE_COLS.update(saved)
    check("А4.7 план клиента (подставной генератор): skill_info.csv — DataHex +58 навыка 503, ведомость _value_overlay/skill_info.sif.csv — строка "
          "«503,mpBase,…», charexp — CumExp строки 10 и своя ведомость, DT_skill_info и DT_charexp точечно; старые байты не совпали — "
          "«изменились с проверки»; файлы порта md5 до = после",
          not plan["errors"] and vo and ve and re.search(r"(?m)^503,mpBase,", led)
          and {j["dt"].rsplit("/", 1)[1] for j in plan["dt_jobs"]} == {"DT_skill_info", "DT_charexp"}
          and any("изменились с проверки" in x for x in plan2["errors"]) and (SD.md5f(real_s), SD.md5f(real_e)) == before,
          (plan["errors"], list(plan["files"]), plan2["errors"]))


def _offline_tr(check):
    from core import i18n
    samples = [
        "навык 503 «x»: чисел 2 (сервер SkillInfo.sif ×6 копий: 3 GameServer + 3 NpcServer, клиент skill_info + ведомость)",
        "расход MP: база: 10 → 30", "на уровне 5: расход MP 20 → 40",
        "навык 503 «x» есть у 2 перс.: Alice (75001/1, ур. 8, навык ур. 5); Bob (75002/1, ур. 5, навык ур. 2) — числа своего уровня у них лежат в "
        "CharSkill (вход берёт их как есть, sub_475290), новые они получат при следующем повышении навыка или сбросе; часть путей эффекта "
        "(sub_479220) берёт значения из таблицы по уровню сразу",
        "позиция 1: навык 503: эффекта 2 нет (состояние +89 = -1) — его значения сервер не применяет (sub_477F60 / sub_479220 берут состояние "
        "оттуда), смысл не подтверждён, правка не делается",
        "позиция 1: навык 503, итог правки: расход MP на уровне 5 = 40010 — больше предела поля (32767): sub_4760E0 записал бы перенос через "
        "край — правка не делается",
        "позиция 1: навык 503 «x»: у 1 перс. уровень выше нового максимума 4 (Alice (75001/1)) — изученное стало бы невалидным (уровень > +43), "
        "правка не делается",
        "позиция 1: навык 500 «x» есть у 1 перс. (Alice (75001/1)): с требованием дерева > 0 сброс дерева (sub_480F20) и полный сброс "
        "(sub_4803A0, UPCharSkillinit по AsdaSkillBase.Need) удалят его, а стартовые навыки сервер выдаёт только при смене профессии — сброс "
        "навыков сломался бы, правка не делается",
        "навык 503 «x»: нужно очков в дереве 5 → 0; макс. уровень 5 → 7 (сервер SkillInfo.sif ×6 копий, клиент skill_info + ведомость)",
        "требование дерева растёт до 9: у 1 перс. вложено меньше — навык у них остаётся, но повышать его они не смогут (5254 код 6), пока не "
        "вложат: Bob (75002/1, ур. 5, навык ур. 2)",
        "позиция 1: порог дерева 1 снижается 10 → 7: у 1 перс. сумма дерева уже в [7, 10) и навыков строки нет (Alice (75001/1)) — сервер "
        "выдаёт их только при РАВЕНСТВЕ суммы порогу (sub_47E9B0), они не получат их никогда, правка не делается",
        "позиция 1: порог дерева 1 повышается 5 → 9: у 1 перс. сумма дерева в [5, 9) и навык строки уже изучен (Alice (75001/1)) — на новом "
        "пороге сервер выдаст его снова уровнем 0 (проверки «уже изучен» у SkillPointTable нет: sub_475650 + UPSkillAdd), правка не делается",
        "класс 1 (боец), уровень 3: Сила 31 → 99; Удача 36 → 50 (сервер ClassStat.txt ×3 GS; клиент характеристики получает от сервера)",
        "класс 1 уровня 3 сейчас у 1 перс.: Carl (75003/1, ур. 3) — базу сервер возьмёт заново при входе (CharMake → sub_43AF30); база на "
        "момент пересчёта (P2) в Joy1 у них прежняя до первого пересчёта бонусов — до следующего входа процентный бонус может посчитаться от "
        "прежней базы",
        "опыт начала уровня 7: 4200 → 3100 (сервер ExpTable.txt ×3 GS, клиент charexp + ведомость)",
        "позиция 1: опыт начала уровня 6 → 2200: у 1 перс. этого уровня опыт меньше (Bob (75002/1)) — их опыт оказался бы ниже начала их "
        "уровня, правка не делается",
        "позиция 1: копия Indun_GameServer: навык 507 открывается на уровне 4 этого навыка (+191…+199), а макс. уровень 3 — не откроется никогда",
        "Joy1.dbo.AsdaSkillBase приведена к SkillInfo.sif: строк изменено 1",
        "Joy1.dbo.AsdaSkillBase не приведена к SkillInfo.sif (навык 503: UPDATE затронул 2 строк вместо 1 — ничего не записано) — повторите "
        "changeset server-sync 3",
        "навыки и классы: персонажи не прочитаны (нет связи с Joy1) — вслепую не делается",
        "навык 503: расход MP: база", "SkillPointTable строка 0: порог", "класс 1 ур. 3: Сила", "уровень 7: опыт начала",
        "навыки и опыт: сервер ≠ клиент", "Навык: макс. уровень и требование дерева (SkillInfo.sif +43, +190; пара с skill_info)"]
    i18n.set_lang("en")
    try:
        tr = [i18n.tr(x) for x in samples]
    finally:
        i18n.set_lang("ru")
    left = [(a, b) for a, b in zip(samples, tr) if a == b or re.search("[А-Яа-яЁё]{3}", b.replace("«x»", ""))]
    check("А4.7 переводы службы: позиции, держатели, отказы, итог набора, AsdaSkillBase, подписи баланса — EN без русского (вложенные «позиция N: "
          "копия …: …» и списки через «; » тоже)", not left, left[:2])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, "web", "skilldata.js"), encoding="utf-8").read()
    en = open(os.path.join(root, "web", "i18n.js"), encoding="utf-8").read()
    shops = open(os.path.join(root, "web", "shops.js"), encoding="utf-8").read()
    STR = r'"([^"\n]*)"'
    have = set(re.findall(STR + r"\s*:", en))
    need = {x for x in re.findall(r"T\(" + STR, js)} | {x for x in re.findall(STR, js) if re.search("[А-Яа-яЁё]", x)}
    from domains.cs_kinds import skilldata as K
    srv = {v[2] for v in K.NUM.values()} | {v[2] for v in K.REQ.values()} | {n for _k, n in K.STATS} | set(K.CLASSES.values())
    help_ = set(re.findall(r'"(?:skill\.num|skill\.req|skill\.spt|class\.stat|level\.exp|title\.enabled)":\s*' + STR, shops))
    miss = sorted((need | srv | help_) - have)
    block = en.split("// А4.7 20.11", 1)[1] if "// А4.7 20.11" in en else ""
    keys = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", block, re.M)
    allk = re.findall(r"(?:^|[{,])\s*" + STR + r"\s*:", en, re.M)
    check("А4.7 веб: skilldata.js подключён (index.html, вкладка и маршрут в shops.js), все его строки, подписи полей службы и справка видов "
          "(в т. ч. title.enabled — запрет выключения звания из наборов) есть в I18N_EN, ключи блока А4.7 не повторяют прежние",
          "/skilldata.js" in open(os.path.join(root, "web", "index.html"), encoding="utf-8").read() and "#/shops/skills" in shops
          and "viewSkillData" in shops and "выдаёт набор" in shops and not miss and keys and all(allk.count(k) == 1 for k in keys), miss[:5])


# ---------------------------------------------------------------------------------------------------------- песочница
def sandbox(check, ldb):
    """Набор «Навыки и классы» целиком: пара сервер + клиент, второе подтверждение сильной правки, перепроверка, AsdaSkillBase, откаты."""
    import selftest_shops_sandbox as X
    from core import db, ops
    from domains import shopcs, shopdata as SD
    ctx = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    real_s, real_e = SD.CLIENT_FILES["skill_info.sif"], SD.CLIENT_FILES["charexp"]
    mirror = os.path.join(SD.SRV_TOOLS, "_srv_mirror", "v2", "GameServer", "SkillTable_Info", "SkillInfo.sif")
    if not (os.path.isfile(real_s) and os.path.isfile(real_e) and os.path.isfile(mirror)):
        return check("песочница А4.7 — skill_info.csv, charexp.csv порта и зеркало SkillInfo.sif есть", False, (real_s, real_e, mirror))
    md0 = (SD.md5f(real_s), SD.md5f(real_e))
    sifb = open(mirror, "rb").read()
    cum = [((int(r["Zero2"]) & 0xFFFFFFFF) << 32) | (int(r["CumExp"]) & 0xFFFFFFFF)
           for r in csv.DictReader(open(real_e, encoding="utf-8-sig", newline=""))]
    exp_txt = ("\r\n".join([str(len(cum))] + ["%d\t%d " % (i + 1, v) for i, v in enumerate(cum)]) + "\r\n").encode("latin-1")
    saved_w = db.GameWriter
    import selftest_shops as T
    saved_cols = dict(T.FAKE_COLS)                     # подставной генератор: поле ведомости skill_info без колонки CSV — по байтам DataHex
    T.FAKE_COLS["skill_info.sif"] = {"mpBase": (58, "i16")}
    T.FAKE_COLS["charexp"] = {}
    try:
        _sandbox(check, ldb, X, db, ops, shopcs, SD, ctx, real_s, real_e, sifb, cum, exp_txt, saved_w)
    finally:
        T.FAKE_COLS.clear()
        T.FAKE_COLS.update(saved_cols)
    check("песочница А4.7: настоящие skill_info.csv и charexp.csv порта — md5 до = после", md0 == (SD.md5f(real_s), SD.md5f(real_e)))


def _sandbox(check, ldb, X, db, ops, shopcs, SD, ctx, real_s, real_e, sifb, cum, exp_txt, saved_w):
    from domains.cs_kinds import skilldata as K
    with X.sandbox(ldb) as (st, env), _Joy():
        files = {}
        for g in GS3:
            files[g + BS + SIF_GS], files[g + BS + SPT], files[g + BS + CSTAT], files[g + BS + EXPT] = sifb, spt(), cstat(), exp_txt
        for n in NPC3:
            files[n + BS + SIF_NPC] = sifb
        for rel, b in files.items():
            p = st.path(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(b)
        cdir = os.path.join(env["tmp"], "a47")
        os.makedirs(cdir)
        ds, de = os.path.join(cdir, "skill_info.csv"), os.path.join(cdir, "charexp.csv")
        shutil.copy2(real_s, ds)
        shutil.copy2(real_e, de)
        SD.CLIENT_FILES["skill_info.sif"], SD.CLIENT_FILES["charexp"] = ds, de
        orig_s, orig_e = open(ds, "rb").read(), open(de, "rb").read()
        st.assets[SD.DT["skill_info.sif"]], st.assets[SD.DT["charexp"]] = orig_s, orig_e
        _FakeWriter.table = _base_rows(sifb)
        for s in range(500, 1120):
            if s * 209 + 209 <= len(sifb) and struct.unpack_from("<Q", sifb, s * 209 + 123)[0]:
                _FakeWriter.table[s] = {c: struct.unpack_from(f, sifb, s * 209 + o)[0] for c, o, f in K.BASE_COLS}
        _FakeWriter.updates = []
        db.GameWriter = _FakeWriter
        mp0 = struct.unpack_from("<h", sifb, 503 * 209 + 58)[0]
        lv = 80
        try:
            cid = X._run(ctx, "shop.cs_create", title="ПЕСОЧНИЦА А4.7", note="самотест песочницы А4.7: навыки и классы")["result"]["id"]
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="skill.num", params={"id": 503, "fields": {"mp0": mp0 * 3}})
            X._run(ctx, "shop.cs_item_add", cs=cid, kind="level.exp", params={"lvl": lv, "exp": cum[lv - 1] + 40})
            X._run(ctx, "shop.cs_check", cs=cid)
            cs = shopcs.get(cid)
            _r, no = X._try(ctx, "shop.cs_approve", cs=cid)
            adm = ops.Ctx(7, "adm", "admin", "100.64.0.9", "web")
            _r, adm_no = X._try(adm, "shop.cs_approve", cs=cid, balance_ok="balance")
            X._run(ctx, "shop.cs_approve", cs=cid, balance_ok="balance")
            check("песочница А4.7: пара (сервер и клиент), сильная правка (MP ×3) — без второго подтверждения отказ, admin с ключом — отказ "
                  "«только владелец», владелец — утверждён", cs["check"]["ok"] and cs["check"]["client_needed"] and cs["check"]["server_needed"]
                  and no and "второе подтверждение" in no and adm_no and "только владелец" in adm_no and shopcs.get(cid)["status"] == "approved",
                  (cs["check"]["errors"], no, adm_no))
            X._run(ctx, "shop.cs_server_dry", cs=cid)
            man = json.load(open(shopcs.manifest_path(cid), encoding="utf-8"))
            want = sorted([g + BS + SIF_GS for g in GS3] + [n + BS + SIF_NPC for n in NPC3] + [g + BS + EXPT for g in GS3])
            check("песочница А4.7: сухой прогон НАСТОЯЩЕГО deploy_changeset — SkillInfo ×6 (3 GS + 3 NpcServer) и ExpTable ×3",
                  shopcs.get(cid)["server_state"] == "dry_ok" and sorted(man["files"]) == want, sorted(man["files"]))
            X._run(ctx, "shop.cs_client_dry", cs=cid)
            X._run(ctx, "shop.cs_client_apply", cs=cid)
            now_s = {r["SkillCode"]: r for r in csv.DictReader(open(ds, encoding="utf-8-sig", newline=""))}["503"]
            now_e = {r["_row"]: r for r in csv.DictReader(open(de, encoding="utf-8-sig", newline=""))}[str(lv - 1)]
            check("песочница А4.7: клиент — skill_info.csv (DataHex +58 навыка 503), charexp.csv (CumExp строки уровня), ведомости, DT подставной "
                  "очередью UE", shopcs.get(cid)["client_state"] == "applied"
                  and struct.unpack_from("<h", bytes.fromhex(now_s["DataHex"]), 58)[0] == mp0 * 3
                  and ((int(now_e["Zero2"]) & 0xFFFFFFFF) << 32 | (int(now_e["CumExp"]) & 0xFFFFFFFF)) == cum[lv - 1] + 40
                  and st.assets[SD.DT["skill_info.sif"]] == open(ds, "rb").read(), shopcs.get(cid)["client_state"])
            calls0 = len(st.calls)
            g0 = open(st.path("GameServer" + BS + EXPT), "rb").read()
            late = {(75020, 1): {"name": "Late", "lvl": lv, "exp": cum[lv - 1] + 1, "cls": 1, "job": 1, "sub": 0, "skills": {}}}
            with _Joy(extra=late):
                _r, e_g = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            check("песочница А4.7 (перепроверка): после проверки появился персонаж уровня 80 с опытом ниже нового порога — выкладка отказ "
                  "«изменились данные стойки … объявления не было» (рестарта не было, ExpTable прежний)", e_g and "изменились данные стойки" in e_g
                  and "Late" in e_g and len(st.calls) == calls0 and open(st.path("GameServer" + BS + EXPT), "rb").read() == g0, e_g)
            calls1 = len(st.calls)                     # ★ ревизия 39 Н-3: персонаж появился ЗА ВРЕМЯ объявления — после preview, до копирования
            with _Joy(extra=late, when=lambda: bool(st.calls) and st.calls[-1].startswith("deploy:")):
                _r, e_s = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            check("песочница А4.7 (ревизия 39 Н-3): персонаж с опытом ниже нового порога появился за время объявления (preview чисто) — "
                  "перепроверка после остановки: отказ «выкладка не выполнена, стойка не изменена … перепроверка набора после остановки стойки "
                  "… Late», файлы не тронуты (ExpTable прежний), прежняя стойка поднята (--start-only), состояние набора прежнее",
                  e_s and "перепроверка набора после остановки стойки" in e_s and "Late" in e_s
                  and st.calls[calls1:] == ["announce", "stop", "deploy:apply", "bring_up"]
                  and open(st.path("GameServer" + BS + EXPT), "rb").read() == g0 and shopcs.get(cid)["server_state"] == "dry_ok",
                  (e_s, st.calls[calls1:], shopcs.get(cid)["server_state"]))
            _FakeWriter.updates = []
            r, e = X._try(ctx, "shop.cs_server_apply", cs=cid, confirm="restart", unsynced_ok=True)
            ok6 = all(struct.unpack_from("<h", open(st.path(rel_), "rb").read(), 503 * 209 + 58)[0] == mp0 * 3
                      for rel_ in [g + BS + SIF_GS for g in GS3] + [n + BS + SIF_NPC for n in NPC3])
            note = shopcs.get(cid).get("server_note") or ""
            check("песочница А4.7: серверная половина выложена рестартом — MP навыка 503 во всех 6 копиях; AsdaSkillBase приведена (503 Mpvalue), "
                  "заметка в карточке набора", r and shopcs.get(cid)["server_state"] == "applied" and ok6
                  and _FakeWriter.updates == [(503, {"Mpvalue": mp0 * 3})] and "AsdaSkillBase приведена" in note, (e, note, _FakeWriter.updates))
            _FakeWriter.updates = []
            X._run(ctx, "shop.cs_server_rollback", cs=cid, confirm="restart")
            X._run(ctx, "shop.cs_client_rollback", cs=cid)
            back = all(open(st.path(rel_), "rb").read() == b for rel_, b in files.items()) and open(ds, "rb").read() == orig_s \
                and open(de, "rb").read() == orig_e
            check("песочница А4.7: откат сервера (rolled_back, AsdaSkillBase снова = SkillInfo) и клиента — 12 таблиц стойки, skill_info.csv и "
                  "charexp.csv вернулись", back and shopcs.get(cid)["server_state"] == "rolled_back"
                  and _FakeWriter.updates == [(503, {"Mpvalue": mp0})], (shopcs.get(cid)["server_state"], _FakeWriter.updates))
        except ops.OpRefused as ex:                    # отказ шага песочницы — проверка с причиной, а не обрыв всего самотеста
            check("песочница А4.7: путь набора без отказа", False, str(ex)[:400])
        finally:
            db.GameWriter = saved_w
            SD.CLIENT_FILES["skill_info.sif"], SD.CLIENT_FILES["charexp"] = real_s, real_e


# ---------------------------------------------------------------------------------------------------------- живое
def live(check):
    """Только чтение и сухие прогоны на живой стойке (SSH), Joy1 (SELECT) и живом порту (настоящий генератор ItemDB)."""
    from core import config
    from domains import shopcs, shopdata as SD
    from domains.cs_kinds import skilldata as K
    if config.get().on_server:
        return check("живой самотест А4.7 — с ПК (SSH и порт)", True)
    rels = [g + BS + SIF_GS for g in GS3] + [n + BS + SIF_NPC for n in NPC3] + [g + BS + x for g in GS3 for x in (SPT, CSTAT, EXPT)]
    md = SD.live_md5(rels)
    check("живая стойка А4.7: SkillInfo ×6, SkillPointTable, ClassStat, ExpTable ×3 есть, поле = Ch2", "none" not in md.values()
          and all(md["GameServer" + BS + x] == md["Ch2_GameServer" + BS + x] for x in (SIF_GS, SPT, CSTAT, EXPT))
          and md["NpcServer" + BS + SIF_NPC] == md["Ch2_NpcServer" + BS + SIF_NPC], {r: h[:8] for r, h in md.items()})
    lk = K.lookup("skill", "503")
    sr = K.lookup("skills", "")
    le = K.lookup("exptable", "")
    check("живая справка А4.7: навык 503 (поля, уровни, держатели из Joy1, клиент), поиск — навыки игроков (≥ 400), опыт = клиенту",
          lk["client"] and lk["holders"] is not None and len(sr["rows"]) >= 400 and le["rows"] and all(r["exp"] == r["client"] for r in le["rows"]),
          (lk.get("holders_error"), len(sr["rows"])))
    cur = {f[0]: f[5] for f in lk["fields"]}
    lv = 80
    ex = [r["exp"] for r in le["rows"]]
    items = [{"pos": 1, "kind": "skill.num", "params": {"id": 503, "fields": {"mp0": cur["mp0"] + 1}}},
             {"pos": 2, "kind": "level.exp", "params": {"lvl": lv, "exp": ex[lv - 1] + 40}}]
    cli = SD.Client.load(force=True)
    ev = SD.Eval(items, False, SD.Snap(), cli).run()
    s = ev.summary()
    check("живая оценка набора А4.7 (навык 503 MP +1, опыт уровня 80 +40): без ошибок, сервер — 9 файлов (SkillInfo ×6, ExpTable ×3), клиент — "
          "skill_info +58 и charexp, держатели прочитаны", not s["errors"] and s["server"]["count"] == 9
          and {c["file"] for c in s["client"]} == {"skill_info.sif", "charexp"}
          and not any("не прочитано" in w for r in s["positions"] for w in r["warnings"]), s["errors"][:3])
    tracked = [p for p in (SD.CLIENT_FILES["skill_info.sif"], SD.CLIENT_FILES["charexp"]) + SD.ledger_paths("skill_info.sif") + SD.ledger_paths("charexp")
               if os.path.isfile(p)]
    before = {p: SD.md5f(p) for p in tracked}
    plan = SD.client_plan(s["client"], 0)
    after = {p: SD.md5f(p) for p in tracked}
    check("живой план клиента А4.7: НАСТОЯЩИЙ генератор ItemDB подтверждает ведомости skill_info.sif и charexp, точечные DT_skill_info / "
          "DT_charexp; ничего не записано (md5 порта до = после)", not plan["errors"]
          and {j["dt"].rsplit("/", 1)[1] for j in plan["dt_jobs"]} == {"DT_skill_info", "DT_charexp"} and before == after, plan["errors"][:3])
    tmp = tempfile.mkdtemp(prefix="asda_cs_a47_live_")
    try:
        man = {"tag": "20261120_a47live", "changeset": 0, "files": {}}
        for rel, data in sorted(ev.new_bytes().items()):
            lp = os.path.join(tmp, rel.replace(BS, os.sep))
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            open(lp, "wb").write(data)
            man["files"][rel] = {"local": lp.replace(BS, "/"), "base": ev.snap.md5[rel], "new": SD.md5b(data)}
        mp = os.path.join(tmp, "manifest.json")
        json.dump(man, open(mp, "w", encoding="utf-8"))
        b0m = SD.live_md5(sorted(man["files"]))
        rc, out = shopcs.run_deploy(mp)
        b1m = SD.live_md5(sorted(man["files"]))
        check("НАСТОЯЩИЙ сухой прогон deploy_changeset по SSH (SkillInfo ×6, ExpTable ×3): «всё готово к --apply», стойка не изменилась",
              rc == 0 and "всё готово" in out and b0m == b1m, (rc, out[-400:]))
        saved_dir = SD.CS_DIR
        SD.CS_DIR = tmp
        try:
            cs = {"id": 9947, "items": items, "check": s}
            _mp, mman = shopcs.build_server_out(cs, ev)
            sa, _now = K._guard_state(cs, "apply")
            sr_, _now2 = K._guard_state(cs, "rollback")
            g = K.apply_guard(cs, "apply")
        finally:
            SD.CS_DIR = saved_dir
        rg = "GameServer" + BS + EXPT
        check("живая перепроверка А4.7: выкладка — ExpTable из манифеста набора (md5 = новому), откат — живой (база); опасных переходов нет",
              SD.md5b(sa[rg]) == mman["files"][rg]["new"] and SD.md5b(sr_[rg]) == SD.live_md5([rg])[rg] and g == [], g)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    d = {x["key"]: x for x in SD.divergence(limit=2000, areas=("skilldata",))["sections"]}["skills"]["rows"]
    base = [r for r in d if r.get("field") == "AsdaSkillBase" or "AsdaSkillBase не прочитана" in r["why"]]
    check("живые расхождения А4.7: Joy1.dbo.AsdaSkillBase прочитана и = SkillInfo.sif (строк 0), копии SkillInfo одной базы",
          not base and not any("своя база копии" in r["why"] and "SkillInfo" in r["why"] for r in d), (base[:3], len(d)))
