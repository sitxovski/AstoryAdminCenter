# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_autoblock_a6.py — самотест шага А6.8, часть «чтение» (22.11.2026; domains/autoblock.py, /api/autoblock/*, web/autoblock.js,
консоль autoblock).

offline(check)  — сверка лестницы ТЕМ ЖЕ кодом, что ac_case.py ladder --check (результат панели = результату функций исходника на тех же
                  ini: всё совпадает, одно расхождение, копия не прочитана, паритет Ch2 нарушен, значения секций расходятся), счётчики P48 / P69
                  (формат DLL, путь CounterFile без выхода за v2), режим секций по журналу патчей; на сервере — только копия ext/ с манифестом
                  (нет файлов — понятный отказ, подмена — отказ сверки md5); происхождение блока по причине, пара «блок ↔ событие» bisect'ом,
                  категория служебных, отказы ввода (даты ГГГГММДД параметром, период, svc), тексты отказов без «; », права, маршруты,
                  переводы EN (shadowed_translations = 0), веб без innerHTML, консоль, выкладка ext/anticheat (ac_case.py + конфиг).
eac_point(check) — ★ А6.8 (вторая часть): «EAC сейчас» против ПОДСТАВНОЙ точки статуса AsdaEacServer (http.server на 127.0.0.1): ответ, нет
                  точки, нет / короткий / неверный секрет, 401, 429, 503, чужая схема, таймаут; IP только с players.view_net; секрет не в ответе.
sandbox(check, ldb) — СВОИ базы LocalDB: настоящие миграции схемы ac (acdb_01 …), AsdaStoryOp (Us_member, BlockList, BlockHistory), AsdaAdmin
                  (adminc_02: adm.audit). Синтетика с ФИКСИРОВАННЫМИ датами (январь 2026, сроки 2000 / 2999 — не от времени запуска): кики и автоблок
                  P48, ступень P69, блоки всех видов происхождения, блок и снятие панелью; история за период, по учётке, svc, нет таблицы — строка
                  ошибки; EAC по учётке на подменах снимка процессов и лестницы.
live(check)     — только чтение живой dev: сверка = функциям исходника на тех же байтах ini (второй путь — прямое чтение), история = COUNT(*)
                  живых таблиц за период, EAC по учётке; служба на сервере (SSH, stdin) — код из ext/ с тем же md5, что исходник ПК; без входа — 401.
Ничего не пишет ни в игровые базы, ни на сервер. Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
AC_DIR = os.path.join(PORT, "AstoryServer", "Tools", "Anticheat")
BS = "\\"
CYR = re.compile("[А-Яа-яЁё]")


def _refused(fn):
    """Текст отказа OpRefused или None."""
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


class _Req:
    def __init__(self, query, role="owner"):
        self.query, self.session = dict(query), {"user": {"role": role, "login": "selftest"}}


def _ac_case():
    """Исходник ac_case.py — обычным импортом из файла (как консоль ПК), для сравнения с панелью."""
    spec = importlib.util.spec_from_file_location("ac_case_selftest_ab", os.path.join(AC_DIR, "ac_case.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ini_bytes(p48_hours="24", s1="24", s2="720", s3="-1", p69_mode="0", extra="", counter=True):
    """patches.ini AsdaPatch в UTF-16 LE с BOM (как пишет DLL) с секциями P48 / P69 / P73; counter=False — без ключей CounterFile."""
    t = ("[General]\r\nVersion=85\r\nMasterEnable=1\r\n[P48_KickAutoBlock]\r\nEnabled=1\r\nKickThreshold=5\r\nBlockHours=%s ; срок\r\n"
         "CounterFile=..\\GameServer\\ConfigSet\\ac_kick_counter.ini\r\n[P69_IntegrityAutoBlock]\r\nEnabled=1\r\nMode=%s\r\nStage1Count=20\r\n"
         "Stage1Hours=%s\r\nStage2Hours=%s\r\nStage3Hours=%s\r\nCounterFile=..\\GameServer\\ConfigSet\\ac_integrity_counter.ini\r\n"
         "[P73_EacBridge]\r\nEnabled=1\r\nMode=1\r\n%s" % (p48_hours, p69_mode, s1, s2, s3, extra))
    if not counter:
        t = "".join(ln + "\r\n" for ln in t.split("\r\n") if ln and not ln.startswith("CounterFile="))
    return b"\xff\xfe" + t.encode("utf-16-le")


PATCHLOG = ("AsdaPatch — старт 2026-01-05 10:00:00, PID 4321\r\nХост   : @@ASTORY_SERVER_HOSTNAME@@\r\n  [OK]       P48_KickAutoBlock — x\r\n"
            "  [OK]       P69_IntegrityAutoBlock — x\r\n  [OK]       P73_EacBridge — x\r\n=== итог: применено 3, пропущено 0, ошибок 0 ===\r\n")


def fake_stack(inis, counters=None):
    """Подмена patchcfg._read: ini копий (rel → байты | None), журнал патчей, файлы счётчиков."""
    counters = counters or {}

    def rd(ini_rels, log_dirs, stat_rels):
        ini = {}
        for r in ini_rels:
            if r in inis:
                ini[r] = inis[r]
            elif r in counters:
                ini[r] = counters[r]
            else:
                ini[r] = None
        return ini, {d: PATCHLOG for d in log_dirs}, {r: (len(ini.get(r) or b""), "2026-01-05 09:00:00") for r in stat_rels}
    return rd


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, config, i18n
    from domains import acsrc, autoblock as A, patchcfg as V, shopdata as E
    from domains.cs_kinds import patchcfg as K
    ac = _ac_case()
    cfg = ac.load_config()
    folders = E.folders("GSP")
    rel = {g: E.rel_of(g, K.DLL_INI["AsdaPatch"][0]) for g in folders}
    check("автоблок: копии AsdaPatch — поле, Indun, Ch2 (E.folders GSP), ini ConfigSet\\patches.ini",
          folders == ["GameServer", "Indun_GameServer", "Ch2_GameServer"] and rel["GameServer"] == "GameServer\\ConfigSet\\patches.ini", folders)
    m, cfg2, src = A.source()
    check("автоблок: исходник лестницы — тот же ac_case.py ПК (функции ladder_map / parse_ini_bytes / ladder_check), конфиг = ac_case.load_config()",
          src["where"] == "port" and callable(m.ladder_check) and cfg2 == cfg
          and src["config_md5"] == hashlib.md5(open(os.path.join(AC_DIR, "ac_case_config.json"), "rb").read()).hexdigest(), src)
    saved = V._read
    counters = {"GameServer\\ConfigSet\\ac_kick_counter.ini": b"[Kicks]\r\n9001=2,1767607200\r\n9002=1,1767607300\r\n",
                "GameServer\\ConfigSet\\ac_integrity_counter.ini": b"[Mode0]\r\n9003=21,1,1767600000,1767700000\r\n[Mode1]\r\n9004=3,0,1767600000,1767600100\r\n"}

    def run(inis, cnt=counters):
        V._read = fake_stack(inis, cnt)
        try:
            return A.ladder(force=True)
        finally:
            V._read = saved

    def console(inis):
        """То, что напечатала бы консоль: ac_case.ladder_check по тем же байтам (непрочитанная копия — {} как read_stand_ini)."""
        by = {g: (ac.parse_ini_bytes(inis[rel[g]]) if inis.get(rel[g]) is not None else {}) for g in folders}
        return [(s, st, k, v, h, ok) for s, st, k, v, h, ok in ac.ladder_check(cfg, by)]
    tup = lambda L: [(c["server"], c["step"], c["key"], c["ini"], c["ladder"], c["ok"]) for c in L["check"]]
    good = {rel[g]: ini_bytes() for g in folders}
    L1 = run(good)
    check("автоблок: всё совпадает — 12 проверок (3 копии × 4 ключа ступеней 3–5) как у ac_case.py ladder --check, расхождений 0",
          tup(L1) == console(good) and len(L1["check"]) == 12 and L1["mismatches"] == 0 and L1["ladder_check_bad"] == 0 and not L1["errors"],
          (L1["mismatches"], L1["errors"]))
    bad = dict(good)
    bad[rel["Indun_GameServer"]] = ini_bytes(s2="721")
    L2 = run(bad)
    check("автоблок: Indun Stage2Hours=721 — одно расхождение (ступень 4), строки = функции исходника; значения секций копий расходятся",
          tup(L2) == console(bad) and L2["mismatches"] == 1
          and [c["key"] for c in L2["check"] if not c["ok"]] == ["P69_IntegrityAutoBlock.Stage2Hours"]
          and any(d["key"] == "Stage2Hours" and d["values"]["Indun_GameServer"] == "721" for d in L2["diverge"]), L2["diverge"])
    un = dict(good)
    un[rel["Ch2_GameServer"]] = None
    L3 = run(un)
    check("автоблок: копия Ch2 не прочитана — «не прочитано» 4 (не расхождение), консоль посчитала бы 4 «РАСХОЖДЕНИЯ» (ladder_check_bad), ошибка копии",
          tup(L3) == console(un) and L3["unread_checks"] == 4 and L3["mismatches"] == 0 and L3["ladder_check_bad"] == 4
          and any(e.startswith("Ch2_GameServer: patches.ini не прочитан") for e in L3["errors"]), L3["errors"])
    par = dict(good)
    par[rel["Ch2_GameServer"]] = ini_bytes(extra="[X]\r\nA=1\r\n")
    L4 = run(par)
    check("автоблок: Ch2 ≠ поле по md5 — паритет нарушен (ошибка с md5), сроки при этом совпадают",
          L4["mismatches"] == 0 and any(not p["same"] for p in L4["parity"]) and any("паритет Ch2 нарушен" in e for e in L4["errors"]), L4["parity"])
    check("автоблок: режим секций по журналу патчей (patchcfg.state) — P48 / P69 / P73 у всех копий, P69 Mode=0 — «журнал»",
          set(L1["modes"]) == set(A.SECTIONS) and all(L1["modes"]["P69_IntegrityAutoBlock"][g] == "journal" for g in folders)
          and all(L1["modes"]["P48_KickAutoBlock"][g] == "active" for g in folders), L1["modes"])
    p69c = L1["counters"]["P69_IntegrityAutoBlock"]
    check("автоблок: счётчики — по CounterFile копий один файл GameServer\\ConfigSet (поле, Indun, Ch2); P48 [Kicks] 2 учётки; P69 раздельно "
          "(ревизия 58 Н-2): [Mode0] наблюдение 1, [Mode1] боевой 1",
          [x["accounts"] for x in L1["counters"]["P48_KickAutoBlock"]] == [2]
          and [(x["section"], x["kind"], x["accounts"]) for x in p69c] == [("Mode0", "observe", 1), ("Mode1", "live", 1)]
          and "_rows" not in json.dumps(L1["counters"], default=str), L1["counters"])
    c1, c3, c4 = A.counters_of(9001), A.counters_of(9003), A.counters_of(9004)
    check("автоблок: счётчики учётки — P48 «счёт,начало» с окном; P69 «счёт,ступень,первое,последнее» по секции: 9003 — только наблюдение, "
          "9004 — только боевой (время UTC из секунд unix)",
          c1["P48"]["count"] == 2 and c1["P48"]["first"] == "2026-01-05 10:00:00 UTC" and c1["P48"]["section"] == "Kicks"
          and c3["P69"]["observe"]["count"] == 21 and c3["P69"]["observe"]["stage"] == 1 and "live" not in c3["P69"]
          and c4["P69"]["live"]["section"] == "Mode1" and "observe" not in c4["P69"] and A.counters_of(9999) == {}, (c1, c3, c4))
    # ★ ревизия 58 М-5: окно WindowHours (24) от первого кика — счёт сгорел / нет (время «сейчас» подменено, не от запуска)
    sv_now = A._now_unix
    try:
        A._now_unix = lambda: 1767607200 + 3600
        run(good)
        e1 = (A.counters_of(9001)["P48"], [x["expired"] for x in A.ladder()["counters"]["P48_KickAutoBlock"]])
        A._now_unix = lambda: 1767607200 + 25 * 3600
        run(good)
        e2 = (A.counters_of(9001)["P48"], [x["expired"] for x in A.ladder()["counters"]["P48_KickAutoBlock"]])
    finally:
        A._now_unix = sv_now
    check("автоблок: P48 — окно 24 ч (WindowHours): через час счёт живой, через 25 ч — «окно истекло» (у 9002 начало на 100 с позже)",
          not e1[0]["expired"] and e1[1] == [0] and e2[0]["expired"] and e2[1] == [2] and e1[0]["window_end"] == "2026-01-06 10:00:00 UTC"
          and e1[0]["window_hours"] == 24, (e1, e2))
    nok = {rel[g]: ini_bytes(counter=False) for g in folders}
    L6 = run(nok)
    check("автоблок: ключа CounterFile нет — путь по умолчанию DLL (..\\GameServer\\ConfigSet\\ac_*_counter.ini, ревизия 58 М-3)",
          [x["file"] for x in L6["counters"]["P48_KickAutoBlock"]] == ["GameServer\\ConfigSet\\ac_kick_counter.ini"]
          and {x["file"] for x in L6["counters"]["P69_IntegrityAutoBlock"]} == {"GameServer\\ConfigSet\\ac_integrity_counter.ini"}
          and L6["counters"]["P48_KickAutoBlock"][0]["accounts"] == 2, L6["counters"])
    st = {x["section"]: x for x in L1["states"]}
    L7 = run({rel[g]: ini_bytes(p69_mode="1") for g in folders})
    st7 = {x["section"]: x for x in L7["states"]}
    check("автоблок: состояние патчей по ini (ревизия 58 М-1) — P69 Mode=0 «только журнал, ступени 3–5 не исполняются» у трёх копий, P69 Mode=1 "
          "— «исполняются», P48 действует, P73 Mode=1; пометка сверки говорит, что Enabled и Mode не сверяются",
          st["P69_IntegrityAutoBlock"]["journal_only"] and "ступени 3–5 автоматически не исполняются" in st["P69_IntegrityAutoBlock"]["why"]
          and st["P69_IntegrityAutoBlock"]["copies"] == folders and not st7["P69_IntegrityAutoBlock"]["journal_only"]
          and "исполняются (блок 2271" in st7["P69_IntegrityAutoBlock"]["why"] and st["P48_KickAutoBlock"]["enabled"] == "1"
          and st["P73_EacBridge"]["mode"] == "1" and "Enabled и Mode тоже не сверяются" in A.LADDER_NOTE, (L1["states"], L7["states"]))
    check("автоблок: разбор строки Log_SpeedHack GM-блока 6094 (GameServer.c:133301)",
          A.GM_LOG_RX.match("11 Mon 10 Day 22 hou 12 min 44 sec : GM Recv_CharBlock() UserNick GM_MONSTER, Time 1").groups()
          == ("11", "10", "22", "12", "44", "GM_MONSTER", "1") and not A.GM_LOG_RX.match("x : Recv_CharBlock() UserNick a"))
    L5 = run(good, {})
    check("автоблок: файла счётчика нет — пометка «счёта ещё не было», не ошибка",
          any("счёта ещё не было" in n for n in L5["notes"]) and not L5["errors"], L5["notes"])
    check("автоблок: путь CounterFile — только внутри v2 (абсолютный, выход выше v2, пустой — не читается)",
          A._counter_rel("Indun_GameServer", "..\\GameServer\\ConfigSet\\x.ini") == "GameServer\\ConfigSet\\x.ini"
          and A._counter_rel("GameServer", "C:\\x.ini") is None and A._counter_rel("GameServer", "..\\..\\x.ini") is None
          and A._counter_rel("GameServer", "") is None and A._counter_rel("GameServer", "\\\\srv\\x") is None)
    # ---- на сервере: только ext/ с манифестом
    tmp = tempfile.mkdtemp(prefix="ab_ext_")
    sv = (acsrc.EXT, acsrc.MANIFEST, A.AC_EXT, config.get().on_server)
    try:
        acsrc.EXT, acsrc.MANIFEST, A.AC_EXT = tmp, os.path.join(tmp, "MANIFEST.json"), os.path.join(tmp, "anticheat")
        config.get().on_server = True
        w0 = _refused(lambda: A.source())
        os.makedirs(A.AC_EXT)
        man = {}
        for f in A.AC_FILES:
            b = open(os.path.join(AC_DIR, f), "rb").read()
            open(os.path.join(A.AC_EXT, f), "wb").write(b)
            man["anticheat/" + f] = hashlib.md5(b).hexdigest()
        open(acsrc.MANIFEST, "w", encoding="utf-8").write(json.dumps(man))
        m2, cfg3, src2 = A.source()
        with open(os.path.join(A.AC_EXT, "ac_case_config.json"), "ab") as f:
            f.write(b" ")
        w2 = _refused(lambda: A.source())
    finally:
        acsrc.EXT, acsrc.MANIFEST, A.AC_EXT, config.get().on_server = sv
        shutil.rmtree(tmp, ignore_errors=True)
    check("автоблок на сервере: нет копии ext/ — понятный отказ (не 500); копия с манифестом — исполняется (where=ext, md5 = исходнику ПК, "
          "конфиг тот же); подмена конфига — отказ сверки манифеста",
          w0 and w0.startswith("исходник лестницы ac_case не прочитан") and src2["where"] == "ext" and src2["code_md5"] == src["code_md5"]
          and cfg3 == cfg and w2 and "манифест" in w2, (w0, src2, w2))
    # ---- история: правила без базы
    check("автоблок: происхождение по причине — «Speed Hack» UPHackBlock, «Login Block» UPUserBlock, «AC-0001 …» дело, прочее — оператор",
          [A.origin_of(x) for x in ("Speed Hack", "Login Block", "AC-0001 s3 1h: x", "AC-1 x", "admin center selftest", None)]
          == ["hack", "user", "case", "manual", "manual", "manual"])
    d0 = datetime.datetime(2026, 1, 5, 10, 0)
    ts = sorted([d0 + datetime.timedelta(minutes=k) for k in (0, 30, 60)])
    check("автоблок: пара «блок ↔ событие» — bisect по времени учётки в пределах MATCH_MIN минут",
          A._near(ts, d0 + datetime.timedelta(minutes=4)) == d0 and A._near(ts, d0 + datetime.timedelta(minutes=15)) is None
          and A._near([], d0) is None and A._near(ts, d0 + datetime.timedelta(minutes=64)) == ts[2])
    check("автоблок: категория — служебные 1…5000, игроки > 5000, без учётки", [A.cat_of(x) for x in (1, 5000, 5001, None)]
          == ["service", "service", "player", "none"])

    class _R:
        def one(self, sql, p=()):
            return {"f": "20260101", "t": "20260130"}
    why = [_refused(lambda q=q: A._period(q, _R())) for q in ({"from": "2026-01-01"}, {"from": "20260230"}, {"from": "20260201", "to": "20260101"},
                                                           {"from": "20240101", "to": "20260101"})]
    why += [_refused(lambda: A.svc_mode({"svc": "all"})), _refused(lambda: A.eac("x")), _refused(lambda: A.eac("0"))]
    check("автоблок: отказы — дата не ГГГГММДД, нет дня, «с» позже «по», период > 366 суток, svc, номер учётки (%d)" % len(why), all(why), why)
    check("автоблок: период по умолчанию — 30 суток по часам SQL (параметром), явные даты — как есть",
          A._period({}, _R()) == ("20260101", "20260130") and A._period({"from": "20260105", "to": "20260106"}, _R()) == ("20260105", "20260106"))
    check("автоблок: тексты отказов без «; »", all("; " not in x for x in why if x), why)
    code = open(os.path.join(ROOT, "domains", "autoblock.py"), encoding="utf-8").read()
    lits = [s for s in re.findall(r'"((?:[^"\\]|\\.)*)"', code) if re.search(r"\b(SELECT|FROM|WHERE)\b", s)]
    check("автоблок: в SQL модуля нет русских букв (тексты видов — параметрами), записи нет (INSERT / UPDATE / DELETE / EXEC) — только чтение",
          lits and not any(CYR.search(s) for s in lits) and not re.search(r"\b(INSERT|UPDATE|DELETE|EXEC)\s", code.split('"""', 2)[2]), lits[:3])
    # ---- нет связи с базой — понятный отказ (409), а не 500
    from core import db as _db

    def nodb(database):
        raise _db.DbError("нет подключения к %s: Login timeout expired" % database)
    _db.set_override("game", nodb)
    try:
        wn = [_refused(lambda: A.history({"from": "20260101", "to": "20260102"})), _refused(lambda: A.eac(5))]
    finally:
        _db.set_override("game", None)
    check("автоблок: базы нет — отказ «история автоблоков не прочитана» / «EAC по учётке не прочитан» с причиной (не 500)",
          wn[0] and wn[0].startswith("история автоблоков не прочитана: нет подключения") and wn[1] and wn[1].startswith("EAC по учётке не прочитан"), wn)
    why += wn
    # ---- права, маршруты
    roles = ("owner", "admin", "gm", "support")
    rt = {p: _route(p) for p in ("/api/autoblock/ladder", "/api/autoblock/history", "/api/autoblock/eac")}
    check("автоблок: маршруты /api/autoblock/ladder | history | eac — GET, право ac.view (owner, admin, gm)",
          all(fn and perm == "ac.view" for fn, perm in rt.values()) and {r for r in roles if auth.can(r, "ac.view")} == {"owner", "admin", "gm"},
          {p: v[1] for p, v in rt.items()})
    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in why if x] + [A.LADDER_NOTE, A.EAC_NOTE, "patches.ini копий GameServer не прочитаны: ssh: нет связи",
              "Ch2_GameServer: patches.ini не прочитан (файла нет)", "GameServer: patches.ini не прочитан (ошибка чтения)",
              "режимы патчей по журналу не прочитаны: настройки патчей не прочитаны: x", "счётчики автоблоков не прочитаны: x",
              "patches.ini: GameServer ≠ Ch2_GameServer (md5 7e8e0595 ≠ 1234abcd) — паритет Ch2 нарушен",
              "P48_KickAutoBlock: файла счётчика GameServer\\ConfigSet\\ac_kick_counter.ini нет — счёта ещё не было (DLL создаёт его на первом "
              "засчитанном событии) или он не прочитан", "служебные учётки ≤ 5000 — отдельным итогом (svc=in — в общем)",
              "в каталоге видов ac.other нет вида 62 (ступень P69) — ступени P69 не показаны", "ac.kick_block: запрос к joylog1: Invalid object name",
              "AsdaStoryOp BlockList / BlockHistory: запрос к AsdaStoryOp: x", "журнал панели adm.audit: AsdaAdmin: x", "учётки 5 нет",
              "режим моста P73 и счётчики не прочитаны: исходник лестницы ac_case не прочитан: x", "снимок процессов не получен: x",
              "лестница санкций не прочитана: x", "журнал Log_SpeedHack GameServer не прочитан: слишком много прочитано журналов за минуту — не больше 32 МБ на пользователя, подождите",
              "журнал Log_SpeedHack GameServer за 20260112 в список файлов не попал (список обрезан) — GM-блок за эти сутки не опознан",
              "joylog1.san.case_block: запрос к joylog1: x"] + [x["why"] for x in L1["states"] + L7["states"]] + [
              "P73_EacBridge: Enabled=0 — патч выключен, автоблок по нему не идёт"] + [x["name"] for x in cfg["ladder"]] + [x["mechanism"] for x in cfg["ladder"]]
        miss = [x for x in ru if CYR.search(i18n.tr(x).replace("нет связи", "").replace("запрос к", ""))]
        check("автоблок EN: отказы, заметки, ошибки чтения (причина — вложенным переводом), ступени лестницы — без русских слов (%d строк)" % len(ru),
              not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("автоблок: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])
    # ---- веб
    js = open(os.path.join(ROOT, "web", "autoblock.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("автоблок веб: раздел #/autoblock с правом ac.view, маршрут viewAutoblock, скрипт после acjournal.js (помощники acText / acTable)",
          '["#/autoblock", "Античит: автоблок и EAC", "ac.view"' in app and 'case "autoblock": return viewAutoblock(my);' in app
          and 0 < idx.index("/acjournal.js") < idx.index("/autoblock.js"))
    check("автоблок веб: без innerHTML, данные — текстовыми узлами (acText), правка — ссылкой на «Настройки патчей», записи нет (op() не зовётся)",
          "innerHTML" not in js and "acText(" in js and "#/shops/patches" in js and "op(" not in js and "T(r.reason" not in js and "T(b.reason" not in js)
    labels = set(re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|div)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) | set(re.findall(r'\["([^"\]]+)", (?:r|c|b|k|x|e) =>', js)) \
        | set(re.findall(r'T\("([^"]+)"', js)) | set(re.findall(r':\s*"([^"]+)"', js[js.index("AB_MODES"):js.index("function abLabel")]))
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("автоблок веб EN: у подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack, lack[:8])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "autoblock.js")], capture_output=True, timeout=60)
        check("автоблок: node --check web/autoblock.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("автоблок: node --check web/autoblock.js (node не запустился)", False, str(ex))
    # ---- консоль и выкладка
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "autoblock"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("history", "--bogus")
    c2, o2 = con("history", "--from")
    c3, o3 = con("nope")
    c4, o4 = con("eac")
    check("автоблок консоль: неизвестный ключ, ключ без значения, неизвестное действие, eac без --uid — отказ без обращения к базе и стойке",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "нет значения" in o2 and c3 and "нужно действие" in o3 and c4 and "--uid" in o4,
          (o1[-200:], o2[-200:], o3[-200:], o4[-200:]))
    adm = open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read()
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    check("автоблок: консоль описана в справке; выкладка кладёт ac_case.py и ac_case_config.json в ext/anticheat с манифестом md5",
          "  autoblock …" in adm and "ladder  " in adm and "set(_ab.AC_FILES)" in dep and A.AC_FILES == ("ac_case.py", "ac_case_config.json")
          and 'z.writestr("ext/anticheat/" + _f, _b)' in dep and '_ext_md5["anticheat/" + _f]' in dep)
    eac_point(check)


# =====================================================================================================================
# ★ А6.8 (вторая часть, 22.11): «EAC сейчас» — подставная точка статуса AsdaEacServer (ответ, нет точки, неверный секрет, таймаут, …)
# =====================================================================================================================
POINT_KEY = "selftest-eac-point-key-0123456789abcdef0123"   # секрет подставной точки (не боевой)


def _point_answer(uid):
    """Ответ точки статуса в схеме AdminStatus.cpp (a68.1): учётка uid в игре, EAC Authenticated, событие нарушения."""
    acc = {"uid": uid, "connected": True,
           "eac": {"conn": 7, "state": "зарегистрирован", "authenticated": True, "auth_status": 2, "platform": 1, "registered_unix": 1767600000,
                   "last_ping_ago_ms": 1200, "binds": 1, "net": {"ip": "10.20.30.40"}},
           "reject_unix": None, "reg_in_window": 1,
           "games": [{"server": "GameServer", "pid": 1234, "user_num": 11, "uid": uid, "eac_uid": uid, "login_unix": 1767600010, "protected": False,
                      "ever_protected": True, "bind_zero": False, "bound": True, "orphan": False, "p61_inactive": False, "unprot_since_unix": 1767600100,
                      "deadline_unix": 1767600130, "last_kick_unix": 1767600131, "decided": 2, "decided_code": "eac_action", "decided_why": "",
                      "net": {"ip": "10.20.30.41"}}],
           "events": [{"unix": 1767600000, "kind": "reg_ok", "reason": 0, "reason_code": "", "eos": "", "text": "EAC-сессия зарегистрирована"},
                      {"unix": 1767600131, "kind": "violation", "reason": 2, "reason_code": "eac_action", "eos": "ClientViolation",
                       "text": "ClientActionRequired action=1"}]}
    return {"ok": True, "server": {"version": "a68.1", "built_unix": 1767600200, "age_ms": 15, "uptime_sec": 600, "mode": 1, "fail_open": None,
                                   "eos_session": True, "eac": {"registered": 1, "authenticated": 1, "pending": 0}, "bridges": 3, "p61_inactive": 0,
                                   "games": {"sessions": 1, "protected": 0}, "stats": {"reg_ok": 1, "reg_fail": 0, "evictions": 0, "decisions": 1, "kicks": 1},
                                   "events_on": True, "accounts": 1},
            "found": uid == 9001, "account": acc if uid == 9001 else None}


class FakePoint:
    """Подставная точка статуса на 127.0.0.1:<случайный>; mode: ok | 401 | 429 | 500 | slow | schema. Запоминает пришедший ключ."""

    def __init__(self):
        import http.server
        import threading
        me = self
        self.mode, self.keys, self.paths = "ok", [], []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                me.keys.append(self.headers.get("X-Asda-Key"))
                me.paths.append(self.path)
                code, body = 200, None
                if me.mode == "slow":
                    import time as _t
                    _t.sleep(2.0)
                if self.headers.get("X-Asda-Key") != POINT_KEY or me.mode == "401":
                    code, body = 401, {"ok": False, "error": "key"}
                elif me.mode == "429":
                    code, body = 429, {"ok": False, "error": "rate"}
                elif me.mode == "500":
                    code, body = 503, {"ok": False, "error": "snapshot"}
                else:
                    uid = int(self.path.rsplit("/", 1)[-1])
                    body = _point_answer(uid)
                    if me.mode == "schema":
                        body["server"]["version"] = "b1.0"
                raw = json.dumps(body).encode("utf-8")
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _has_key(v, name):
    """Есть ли ключ name в значении любой вложенности."""
    if isinstance(v, dict):
        return name in v or any(_has_key(x, name) for x in v.values())
    if isinstance(v, list):
        return any(_has_key(x, name) for x in v)
    return False


def eac_point(check):
    """★ А6.8: autoblock.eac_live против подставной точки (ответ, нет точки, неверный / короткий / отсутствующий секрет, 401, 429, ошибка,
    схема, таймаут), права на IP, переводы EN, консоль, веб."""
    from core import config, i18n
    from domains import autoblock as A
    tmp = tempfile.mkdtemp(prefix="ab_eac_")
    fp = FakePoint()
    sv = (A.EAC_POINT, A.EAC_TIMEOUT_S, config.get().on_server)
    try:
        config.get().on_server = False
        A.EAC_POINT = None
        pc = A.eac_live(9001)
        check("EAC сейчас: на ПК (без подставной точки) — state pc, честная пометка «только на сервере», к точке не ходим",
              pc == {"state": "pc", "note": A.EAC_NOTE} and "только на сервере" in A.EAC_NOTE and not fp.paths, pc)
        kf = os.path.join(tmp, "eac_status.key")
        A.EAC_POINT = {"port": fp.port, "secret_file": kf}
        r0 = A.eac_live(9001)
        with open(kf, "w", encoding="utf-8") as f:
            f.write("short\n")
        r1 = A.eac_live(9001)
        check("EAC сейчас: нет файла секрета / секрет короче 32 знаков — no_secret с понятной пометкой, к точке не ходим",
              r0["state"] == "no_secret" and "не прочитан" in r0["note"] and r1["state"] == "no_secret" and "короче 32" in r1["note"] and not fp.paths, (r0, r1))
        with open(kf, "w", encoding="utf-8-sig") as f:
            f.write(POINT_KEY + "\r\n")
        ok = A.eac_live(9001)
        okn = A.eac_live(9001, can_net=True)
        nf = A.eac_live(4242)
        blob = json.dumps(ok, ensure_ascii=False, default=str) + json.dumps(okn, ensure_ascii=False, default=str)
        check("EAC сейчас: ответ точки — state ok, учётка найдена, путь /eac/v1/account/9001, ключ = первой строке файла (BOM и CRLF сняты)",
              ok["state"] == "ok" and ok["found"] and ok["account"]["uid"] == 9001 and fp.paths[0] == "/eac/v1/account/9001"
              and fp.keys[0] == POINT_KEY and ok["server"]["version"] == "a68.1", (ok.get("state"), fp.paths[:1]))
        check("EAC сейчас: секрет не попадает в ответ панели", POINT_KEY not in blob)
        check("EAC сейчас: без права players.view_net полей net (IP канала EAC и игры) нет; с правом — есть",
              not _has_key(ok, "net") and "10.20.30.4" not in json.dumps(ok, default=str) and okn["account"]["eac"]["net"]["ip"] == "10.20.30.40"
              and okn["account"]["games"][0]["net"]["ip"] == "10.20.30.41" and okn["can_net"] and not ok["can_net"])
        g0 = ok["account"]["games"][0]
        check("EAC сейчас: к полям *_unix добавлено время *_at (часы машины), у событий — at",
              g0["deadline_at"] == datetime.datetime.fromtimestamp(1767600130).strftime("%Y-%m-%d %H:%M:%S") and g0["login_at"]
              and ok["account"]["eac"]["registered_at"] and ok["account"]["reject_at"] is None and all(e.get("at") for e in ok["account"]["events"]), g0)
        check("EAC сейчас: учётки нет в таблицах EacServer — found=false, account=null", nf["state"] == "ok" and not nf["found"] and nf["account"] is None, nf)
        res = {}
        for mode in ("401", "429", "500", "schema"):
            fp.mode = mode
            res[mode] = A.eac_live(9001)
        fp.mode = "ok"
        with open(kf, "w", encoding="utf-8") as f:
            f.write("wrong-key-wrong-key-wrong-key-wrong-key-00\n")
        res["wrong"] = A.eac_live(9001)
        with open(kf, "w", encoding="utf-8") as f:
            f.write(POINT_KEY + "\n")
        check("EAC сейчас: неверный секрет — bad_key; 401 — bad_key; 429 — rate; 503 — error с кодом и причиной; чужая схема — schema",
              res["wrong"]["state"] == "bad_key" and res["401"]["state"] == "bad_key" and res["429"]["state"] == "rate"
              and res["500"]["state"] == "error" and "HTTP 503 (snapshot)" in res["500"]["note"] and res["schema"]["state"] == "schema"
              and "b1.0" in res["schema"]["note"], {k: v["state"] for k, v in res.items()})
        A.EAC_TIMEOUT_S = 0.5
        fp.mode = "slow"
        t0 = datetime.datetime.now()
        to = A.eac_live(9001)
        dt_s = (datetime.datetime.now() - t0).total_seconds()
        fp.mode = "ok"
        A.EAC_TIMEOUT_S = sv[1]
        check("EAC сейчас: точка не ответила в срок — timeout за ~EAC_TIMEOUT_S (%.2f с), панель не висит" % dt_s, to["state"] == "timeout" and dt_s < 1.8, to)
        fp.close()
        closed = A.eac_live(9001)
        check("EAC сейчас: точки нет (порт закрыт) — no_point с пометкой про службу и [AdminStatus] Enabled", closed["state"] == "no_point"
              and "Enabled=0" in closed["note"], closed)
        notes = [x["note"] for x in (pc, r0, r1, res["wrong"], res["429"], res["500"], res["schema"], to, closed)]
        check("EAC сейчас: пометки без «; »", all("; " not in n for n in notes), notes)
        i18n.set_lang("en")
        try:
            miss = [n for n in notes if CYR.search(i18n.tr(n))]
        finally:
            i18n.set_lang("ru")
        check("EAC сейчас EN: все пометки переведены (%d)" % len(notes), not miss, miss[:4])
        from api import server
        src = open(server.__file__, encoding="utf-8").read()
        check("EAC сейчас API: /api/autoblock/eac передаёт право players.view_net (can_net) — IP только с правом",
              'autoblock.eac(req.query.get("uid"), can_net=auth.can(req.session["user"]["role"], "players.view_net"))' in src)
        cfg = config.get()
        check("EAC сейчас: адрес и секрет — из настроек службы панели (порт 8447, secrets\\eac_status.key службы), не из порта",
              cfg.eac_status_port == 8447 and cfg.eac_status_secret == config.SERVICE_ROOT + "\\secrets\\eac_status.key")
        js = open(os.path.join(ROOT, "web", "autoblock.js"), encoding="utf-8").read()
        check("EAC сейчас веб: abLive — данные службы текстовыми узлами (acText), IP — только при can_net, виды и причины — словарями с переводом",
              "function abLive(lv)" in js and "net && e && e.net" in js and "net && x.net" in js and "abKnown(AB_EAC_EV, x.kind)" in js
              and "abLive(r.live || {})" in js and "innerHTML" not in js)
        check("EAC сейчас (ревизия 61 М-4 / М-5): все времена блока — часы сервера с подписью (read_at — местное время, не UTC); при Mode=1 — "
              "«только журнал: KICK не отправляется» и у срока «в Mode=1 кика не будет»",
              re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", str(ok.get("read_at") or "")) is not None and "(время сервера)" in js
              and "по часам сервера" in js and "UTC" not in js[js.index("function abLive"):js.index("async function viewAutoblock")]
              and "const m1 = sv.mode === 1" in js and "в Mode=1 кика не будет" in js and "только журнал: KICK не отправляется" in js, ok.get("read_at"))
    finally:
        A.EAC_POINT, A.EAC_TIMEOUT_S, config.get().on_server = sv
        try:
            fp.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    py = sys.executable
    p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "autoblock", "eac", "--uid", "5", "--bogus"], capture_output=True, timeout=120, cwd=ROOT,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    o = (p.stdout + p.stderr).decode("utf-8", "replace")
    adm = open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read()
    check("EAC сейчас консоль: autoblock eac --uid N [--net] описан в справке, чужой ключ — отказ без обращения к базе",
          p.returncode and "неизвестный аргумент --bogus" in o and "eac --uid N [--net]" in adm, o[-200:])


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def sandbox(check, ldb):
    """Свои базы LocalDB: история автоблоков на синтетике (даты января 2026, сроки 2000 / 2999), EAC по учётке на подменах."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_ac_a6 as S6
    from core import db
    from core.ops import OpRefused
    from domains import autoblock as A, status
    tag = secrets.token_hex(3)
    names = {"J": "AsdaAbJ_" + tag, "O": "AsdaAbO_" + tag, "Y": "AsdaAbY_" + tag, "A": "AsdaAbA_" + tag}
    m = ldb("master")
    for k, n in names.items():
        m.cursor().execute("CREATE DATABASE [%s] COLLATE %s" % (n, "Cyrillic_General_CI_AS" if k == "A" else "Arabic_CI_AS"))
    try:
        a = ldb(names["A"])
        for b in _batches(open(os.path.join(ROOT, "sql", "adminc_02_schema.sql"), encoding="utf-8").read()):
            a.cursor().execute(b)
        o = ldb(names["O"]).cursor()
        o.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(61), us_block TINYINT)")
        o.execute("INSERT dbo.Us_member VALUES (7, 'svc7', 0), (9001, 'alpha', 5), (9002, 'beta', 0), (9003, 'gamma', 5), (9004, 'delta', 0), "
                  "(9005, 'eps', 0), (9006, 'zeta', 5), (9007, 'eta', 0), (9008, 'theta', 0)")
        for t in ("BlockList", "BlockHistory"):
            o.execute("CREATE TABLE dbo.%s (Userindex INT, Uid VARCHAR(61), Cou TINYINT, grade TINYINT, BlackDate SMALLDATETIME, "
                      "CloseDate SMALLDATETIME, Reason VARCHAR(300))" % t)
        o.execute("INSERT dbo.BlockList VALUES (9001, 'alpha', 1, 1, '2026-01-05T10:01:00', '2026-01-06T10:01:00', 'Speed Hack'), "
                  "(9003, 'gamma', 1, 1, '2026-01-06T12:00:00', '2000-01-01T00:00:00', 'Speed Hack'), "
                  "(9006, 'zeta', 1, 1, '2026-01-10T08:00:00', '2056-01-10T08:00:00', 'Speed Hack')")
        o.execute("INSERT dbo.BlockHistory VALUES (9007, 'eta', 1, 1, '2026-01-11T10:00:00', '2026-01-11T11:00:00', 'AC-0008 s3 1h: term'), "
                  "(9008, 'theta', 1, 1, '2026-01-12T22:13:00', '2026-01-12T23:13:00', 'Speed Hack')")
        o.execute("UPDATE dbo.BlockList SET CloseDate = '2079-01-01T00:00:00' WHERE Userindex = 9001")
        o.execute("INSERT dbo.BlockHistory VALUES (9004, 'delta', 1, 1, '2026-01-08T09:00:00', '2026-01-08T10:00:00', 'Login Block'), "
                  "(9005, 'eps', 1, 1, '2026-01-08T11:00:00', '2079-01-01T00:00:00', 'AC-0007 s3 24h: training'), "
                  "(7, 'svc7', 1, 1, '2026-01-09T10:00:00', '2026-01-09T11:00:00', 'admin center selftest'), "
                  "(9002, 'beta', 1, 1, '2025-12-01T10:00:00', '2025-12-01T11:00:00', 'Speed Hack')")
        y = ldb(names["Y"]).cursor()
        y.execute("CREATE TABLE dbo.SoulMate (Userindex INT, Ouserindex INT, State TINYINT)")
        jc = ldb(names["J"]).cursor()
        jc.execute("CREATE TABLE dbo.Loginfo (Userindex INT, Login DATETIME, State TINYINT)")
        for f in S6.MIGRATIONS:
            text = S6._subst(open(os.path.join(S6.SQL_DIR, f), encoding="utf-8-sig").read(), {"J": names["J"], "O": names["O"], "Y": names["Y"]})
            for b in _batches(text):
                jc.execute(b)
        cat = __import__("domains.acjournal", fromlist=["x"]).catalog()[0]
        k62 = next(r["text"] for r in cat["tables"]["other"] if r["n"] == 62)

        def kb(when, uid, kind, counted, why, kc, kt, bh, sent):
            jc.execute("INSERT ac.kick_block (ev_utc, ev_local, server_name, server_port, user_index, char_slot, char_name, ip, user_num, opcode, "
                       "repeat_suppressed, event_kind, disc_type, disc_type_name, reason, counted, not_counted_reason, kick_count, kick_threshold, "
                       "block_hours, block_sent) VALUES (?, ?, 'GameServer', 15601, ?, 10, N'Имя', '10.0.0.1', 1, 4101, 0, ?, 3, N'Hack Packet', "
                       "N'причина', ?, ?, ?, ?, ?, ?)", (when, when, uid, kind, counted, why, kc, kt, bh, sent))
        d = datetime.datetime
        for i in range(4):
            kb(d(2026, 1, 5, 9, 50 + i), 9001, "кик", 1, None, i + 1, 5, None, None)
        kb(d(2026, 1, 5, 10, 1), 9001, "автоблок", 1, None, 5, 5, 24, 1)
        for i in range(3):
            kb(d(2026, 1, 7, 9, i), 9002, "кик", 0, "тип кика не считается (CountTypes)", None, None, None, None)
        kb(d(2026, 1, 7, 10, 0), 7, "кик", 1, None, 1, 5, None, None)
        kb(d(2025, 12, 1, 10, 0), 9002, "кик", 1, None, 1, 5, None, None)
        jc.execute("INSERT ac.other (ev_utc, ev_local, server_name, user_index, char_slot, char_name, opcode, event_kind, item_code, value1, value2, "
                   "detail) VALUES ('2026-01-06T09:00:00', '2026-01-06T12:00:00', 'GameServer', 9003, 10, N'Гамма', 2271, ?, 1, 20, 24, N'P69 Mode=1: 2271 sent')", (k62,))
        ac_ = a.cursor()
        for at, action, uid, aj, bj in (
                ("2026-01-09T10:00:05", "account.block", 7, {"uid": 7, "row": {"Userindex": 7, "BlackDate": "2026-01-09 10:00:00.000"}}, {"uid": 7}),
                ("2026-01-09T10:20:00", "account.unblock", 7, {"uid": 7, "rows": [{"Userindex": 7, "BlackDate": "2026-01-09 10:00:00.000"}]}, {})):
            ac_.execute("INSERT adm.audit (at, user_id, login, ip, via, action, target, params, before_json, after_json, result, message) "
                        "VALUES (?, NULL, 'tester', '', 'web', ?, ?, NULL, ?, ?, 'ok', '')", (at, action, "account:%d" % uid, json.dumps(bj), json.dumps(aj)))
        jc.execute("CREATE SCHEMA san")
        jc.execute("CREATE TABLE san.case_block (block_id INT IDENTITY, user_index INT, black_date SMALLDATETIME, close_date SMALLDATETIME, "
                   "applied_by NVARCHAR(64), applied_at DATETIME2(3), lifted_by NVARCHAR(64), lifted_at DATETIME2(3), lift_via NVARCHAR(200))")
        jc.execute("INSERT san.case_block (user_index, black_date, close_date, applied_by, applied_at, lifted_by, lifted_at, lift_via) VALUES "
                   "(9005, '2026-01-08T11:00:00', '2079-01-01T00:00:00', N'ag', '2026-01-08T10:59:50', N'ag', '2026-01-08T11:00:06', N'ac0_unblock_user.sql'), "
                   "(9007, '2026-01-11T10:00:00', '2026-01-11T11:00:00', N'ag', '2026-01-11T09:59:50', N'ag', '2026-01-11T11:00:30', N'UP_AC_LiftExpiredBlock')")
        mp = {"joylog1": names["J"], "AsdaStoryOp": names["O"], "Joy1": names["Y"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("admin", lambda database: ldb(names["A"]))
        # ★ ревизия 58 М-2: журнал Log_SpeedHack — подмена белого списка logs (копии, файлы, чтение с бюджетом на пользователя)
        from domains import logs as LG
        asked = []
        sv_logs = (LG.procs_of, LG.files, LG.scan)
        LG.procs_of = lambda key: ["GameServer", "Ch2_GameServer"]
        LG.files = lambda key, proc, kind=None: {"missing": proc != "GameServer", "more": False,
                                                 "files": [{"name": "SpeedHack_20260112.txt", "size": 90}, {"name": "SpeedHack_20260110.txt", "size": 1}]}

        def fscan(key, proc, name, kind=None, needles=(), show_ip=False, user=None, size=None):
            asked.append((key, proc, name, kind, needles, user))
            body = {"SpeedHack_20260112.txt": ["1 Mon 12 Day 22 hou 12 min 44 sec : GM Recv_CharBlock() UserNick GM_X, Time 1",
                                               "1 Mon 12 Day 23 hou 50 min 0 sec : GM Recv_CharBlock() UserNick GM_Y, Time 5"],
                    "SpeedHack_20260110.txt": ["1 Mon 10 Day 8 hou 0 min 10 sec : GM Recv_CharBlock() UserNick GM_Z, Time 2"]}
            return {"lines": body.get(name, []), "missing": False}
        LG.scan = fscan
        try:
            H = A.history({"from": "20260101", "to": "20260131"}, "tester_u")
            bl = {b["uid"]: b for b in H["blocks"]}
            check("автоблок стенд: блоки за январь — 8 (BlockList 3 + BlockHistory 5; декабрьский вне периода), строки без ошибок",
                  len(H["blocks"]) == 8 and set(bl) == {9001, 9003, 9006, 9004, 9005, 7, 9007, 9008} and not H["errors"], (sorted(bl), H["errors"]))
            check("автоблок стенд: происхождение — 9001 «Speed Hack» + автоблок P48 с 2271 → p48; 9003 + ступень P69 с 2271 → p69; 9008 + строка "
                  "Log_SpeedHack «GM_X, Time 1» в пределах минуты → GM-блок 6094 (ревизия 58 М-2); 9006 (бессрочный, у GM_Z другой срок) → hack; "
                  "9004 Login Block → user; 9005 / 9007 AC-… → case; 7 — блок панели по adm.audit → panel",
                  [bl[u]["origin"] for u in (9001, 9003, 9008, 9006, 9004, 9005, 9007, 7)] == ["p48", "p69", "gm6094", "hack", "user", "case", "case", "panel"]
                  and bl[9008]["block_by"]["gm"] == "GM_X" and bl[9008]["block_by"]["source"] == "Log_SpeedHack",
                  {u: (bl[u]["origin"], bl[u]["block_by"]) for u in bl})
            check("автоблок стенд: Log_SpeedHack читается только за сутки «Speed Hack» без пары (10.01 и 12.01), белым списком gslog / Log_SpeedHack, "
                  "бюджет — на пользователя запроса", sorted(a[2] for a in asked) == ["SpeedHack_20260110.txt", "SpeedHack_20260112.txt"]
                  and all(a[0] == "gslog" and a[3] == "Log_SpeedHack" and a[5] == "tester_u" for a in asked), asked)
            check("автоблок стенд: состояние и снятие (ревизия 58 Н-1) — 9001 действует; 9003 истёк (ждёт входа); 9006 бессрочный; 9004 — «срок прошёл "
                  "— по сроку или досрочно» (времени снятия нет); 9005 — досрочно по делу (san.case_block, кто и чем); 9007 — по сроку по делу; "
                  "7 снят панелью (кто и запись журнала)",
                  bl[9001]["state"] == "active" and bl[9003]["state"] == "expired" and bl[9006]["perm"] and bl[9006]["hours"] is None
                  and bl[9004]["lift"] == "unknown" and bl[9004]["hours"] == 1 and bl[9005]["lift"] == "case_early"
                  and bl[9005]["lift_by"]["via_text"] == "ac0_unblock_user.sql" and bl[9007]["lift"] == "case_term"
                  and bl[9005]["block_by"]["source"] == "san.case_block" and bl[7]["lift"] == "panel"
                  and all(b["lift"] != "term" for b in H["blocks"])
                  and bl[7]["lift_by"]["login"] == "tester" and bl[7]["block_by"]["action"] == "account.block" and bl[7]["cat"] == "service",
                  {u: (bl[u]["state"], bl[u]["lift"], bl[u]["hours"]) for u in bl})
            check("автоблок стенд: итоги киков — игроки 7 (4 засчитанных + 3 нет), служебные 1; засчитано: игроки 4, служебные 1; автоблоков P48 1; "
                  "не засчитано — 3 «тип кика не считается (CountTypes)»",
                  H["sums"]["kicks"] == {"player": 7, "service": 1, "none": 0} and H["sums"]["counted"] == {"player": 4, "service": 1, "none": 0}
                  and H["sums"]["autoblocks"]["player"] == 1 and H["not_counted"] == [{"reason_db": "тип кика не считается (CountTypes)", "n": 3}],
                  (H["sums"], H["not_counted"]))
            check("автоблок стенд: список — засчитанные кики и автоблоки (6), ступень P69 (1, 2271 отправлен), логины учёток",
                  len(H["kicks"]) == 6 and sum(1 for k in H["kicks"] if k["autoblock"]) == 1 and len(H["p69"]) == 1 and H["p69"][0]["sent"]
                  and H["p69"][0]["stage"] == 1 and H["kicks"][0]["login"] == "svc7", (len(H["kicks"]), H["p69"]))
            H2 = A.history({"from": "20260101", "to": "20260131", "account": "alpha"})
            check("автоблок стенд: фильтр по учётке (логин alpha) — только её блок и кики", [b["uid"] for b in H2["blocks"]] == [9001]
                  and all(k["uid"] == 9001 for k in H2["kicks"]) and len(H2["kicks"]) == 5, ([b["uid"] for b in H2["blocks"]], len(H2["kicks"])))
            H3 = A.history({"from": "20251201", "to": "20251231"})
            check("автоблок стенд: декабрь — один блок 9002 (снят по сроку) и один засчитанный кик", [b["uid"] for b in H3["blocks"]] == [9002]
                  and len(H3["kicks"]) == 1, ([b["uid"] for b in H3["blocks"]], len(H3["kicks"])))
            fh, _p = _route("/api/autoblock/history")
            api = fh(_Req({"from": "20260101", "to": "20260131", "svc": "in"}, "gm"), None)
            check("автоблок API: gm видит историю (svc=in), отказ ввода — 409", api["svc"] == "in" and len(api["blocks"]) == 8
                  and asked[-1][5] == "selftest")
            from api import server as _srv
            try:
                fh(_Req({"from": "20260131", "to": "20260101"}, "gm"), None)
                code = None
            except _srv.HttpError as ex:
                code = ex.code
            check("автоблок API: «с» позже «по» — 409 с понятным текстом", code == 409, code)
            # ---- EAC по учётке (подмены снимка процессов и лестницы)
            saved = (status.snapshot, A.ladder)
            try:
                status.snapshot = lambda *a, **k: {"stack": [{"key": "eac", "running": True, "ports_ok": True, "ports": [15901, 15702, 8444],
                                                               "listening": [15901, 15702, 8444], "start": "2026-01-05 09:00:00", "pids": [1]}], "host_error": ""}
                A.ladder = lambda force=False: {"copies": [{"folder": "GameServer", "read": True, "sections": {"P73_EacBridge": {"Enabled": "1", "Mode": "1"}}}],
                                                "modes": {"P73_EacBridge": {"GameServer": "active"}}}
                e1 = A.eac(9001)

                def boom(force=False):
                    raise OpRefused("исходник лестницы ac_case не прочитан: x")
                A.ladder = boom
                e2 = A.eac(9002)
                w = _refused(lambda: A.eac(424242))
                # ★ А6.8 (вторая часть): «EAC сейчас» в ответе eac() — подставная точка статуса
                fpt, tdir = FakePoint(), tempfile.mkdtemp(prefix="ab_eacs_")
                svp = A.EAC_POINT
                try:
                    with open(os.path.join(tdir, "k"), "w", encoding="utf-8") as f:
                        f.write(POINT_KEY + "\n")
                    A.EAC_POINT = {"port": fpt.port, "secret_file": os.path.join(tdir, "k")}
                    e3, e4 = A.eac(9001), A.eac(9001, can_net=True)
                finally:
                    A.EAC_POINT = svp
                    fpt.close()
                    shutil.rmtree(tdir, ignore_errors=True)
            finally:
                status.snapshot, A.ladder = saved
            check("автоблок стенд EAC сейчас: eac() несёт live из точки статуса (учётка найдена, Authenticated, решение 2), без права — без IP, "
                  "с правом — с IP; пометки нет",
                  e3["live"]["state"] == "ok" and e3["live"]["found"] and e3["live"]["account"]["eac"]["authenticated"]
                  and e3["live"]["account"]["games"][0]["decided"] == 2 and not _has_key(e3, "net") and e3["note"] is None
                  and e4["live"]["account"]["eac"]["net"]["ip"] == "10.20.30.40", (e3.get("live", {}).get("state"), e3["note"]))
            check("автоблок стенд EAC: процесс и порты AsdaEacServer, P73 по копиям, блок сейчас (действует), журнал учётки; честная пометка про "
                  "состояние сессии EAC",
                  e1["service"]["running"] and e1["p73"]["GameServer"]["mode"] == "1" and e1["block"]["state"] == "active" and e1["note"] == A.EAC_NOTE
                  and any(t["table"] == "ac.kick_block" for t in e1["summary"]["tables"]), (e1["block"], e1["p73"], e1["errors"]))
            check("автоблок стенд EAC: лестница не прочиталась — пометка в errors, остальное есть; нет учётки — отказ",
                  any("режим моста P73" in x for x in e2["errors"]) and e2["service"] and w and "424242" in w, (e2["errors"], w))
            # ---- таблицы нет — строка ошибки
            jc.execute("DROP TABLE ac.kick_block")
            H4 = A.history({"from": "20260101", "to": "20260131"})
            check("автоблок стенд: нет ac.kick_block — строка ошибки, блоки и P69 считаются", any(x.startswith("ac.kick_block:") for x in H4["errors"])
                  and len(H4["blocks"]) == 8 and len(H4["p69"]) == 1, H4["errors"])
        finally:
            db.set_override("game", None)
            db.set_override("admin", None)
            LG.procs_of, LG.files, LG.scan = sv_logs
    finally:
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def live(check):
    """Только чтение живой dev и службы на сервере. Ничего не пишет."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db
    from domains import autoblock as A, patchcfg as V, shopdata as E
    from domains.cs_kinds import patchcfg as K
    if config.get().on_server:
        return check("живой самотест А6.8 — с ПК", True)
    ac = _ac_case()
    cfg = ac.load_config()
    L = A.ladder(force=True)
    folders = E.folders("GSP")
    rels = [E.rel_of(g, K.DLL_INI["AsdaPatch"][0]) for g in folders]
    raw, _l, _s = V._read(rels, [], [])
    by = {g: ac.parse_ini_bytes(raw[r]) if raw.get(r) else {} for g, r in zip(folders, rels)}
    direct = [list(x) for x in ac.ladder_check(cfg, by)]
    mine = [[c["server"], c["step"], c["key"], c["ini"], c["ladder"], c["ok"]] for c in L["check"]]
    check("живое: сверка лестницы = функциям ac_case.py на байтах ini, прочитанных отдельно (%d проверок, расхождений %d, не прочитано %d)"
          % (len(mine), L["mismatches"], L["unread_checks"]), mine == direct and len(mine) == 12 and all(c["read"] for c in L["copies"]),
          (L["errors"], L["mismatches"]))
    check("живое: режимы P48 / P69 / P73 по журналу патчей у всех трёх копий, паритет поля и Ch2 посчитан",
          all(len(L["modes"].get(s, {})) == 3 for s in A.SECTIONS) and len(L["parity"]) == 1, (L["modes"], L["parity"]))
    with db.GameReader("joylog1") as lg:
        d = lg.one("SELECT CONVERT(char(8), DATEADD(DAY, -29, GETDATE()), 112) AS f, CONVERT(char(8), GETDATE(), 112) AS t")
        nk = lg.one("SELECT COUNT(*) AS n FROM ac.kick_block WHERE ev_local >= CONVERT(datetime2, ?, 112) AND ev_local < "
                    "DATEADD(DAY, 1, CONVERT(datetime2, ?, 112))", (d["f"], d["t"]))["n"]
    with db.GameReader("asdastoryop") as op:
        nb = sum(op.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE BlackDate >= CONVERT(datetime, ?, 112) AND BlackDate < "
                        "DATEADD(DAY, 1, CONVERT(datetime, ?, 112))" % t, (d["f"], d["t"]))["n"] for t in ("BlockList", "BlockHistory"))
    H = A.history({"from": d["f"], "to": d["t"]})
    sk = sum(H["sums"]["kicks"].values()) + sum(H["sums"]["autoblocks"].values())
    check("живое: история за 30 суток — киков и автоблоков = COUNT(*) ac.kick_block (%d), блоков = COUNT(*) BlockList + BlockHistory (%d), без ошибок"
          % (nk, nb), sk == nk and len(H["blocks"]) == nb and not H["errors"], (sk, nk, len(H["blocks"]), nb, H["errors"]))
    e = A.eac(2)
    check("живое: EAC по учётке 2 — снимок процессов (AsdaEacServer), P73 трёх копий, пометка про точку EacServer", e["service"] is not None
          and len(e["p73"]) == 3 and e["note"] == A.EAC_NOTE, (e["errors"], e["service"]))
    probe = ("import sys\nsys.path.insert(0, '.')\nfrom domains import autoblock as A\nL = A.ladder(force=True)\nH = A.history({})\n"
             "print('ABPROBE where=%s md5=%s checks=%d bad=%d unread=%d err=%d herr=%d' % (L['source']['where'], L['source']['code_md5'], "
             "len(L['check']), L['mismatches'], L['unread_checks'], len(L['errors']), len(H['errors'])))\n"
             "E2 = A.eac_live(2)\nS = E2.get('server') or {}\n"
             "hk = lambda v: isinstance(v, dict) and ('net' in v or any(hk(x) for x in v.values())) or isinstance(v, list) and any(hk(x) for x in v)\n"
             "print('ABEAC state=%s ver=%s mode=%s net=%s' % (E2['state'], S.get('version'), S.get('mode'), bool(hk(E2))))\n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        p = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                            r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"ABPROBE where=(\w+) md5=(\w+) checks=(\d+) bad=(\d+) unread=(\d+) err=(\d+) herr=(\d+)", out)
    check("служба на сервере (SSH): лестница из ext/ (манифест) с md5 = исходнику ПК, 12 проверок, итог = ПК, история без ошибок",
          bool(mm) and mm.group(1) == "ext" and mm.group(2) == L["source"]["code_md5"] and mm.group(3) == "12" and int(mm.group(4)) == L["mismatches"]
          and mm.group(5) == "0" and mm.group(7) == "0", out[-600:])
    me = re.search(r"ABEAC state=(\w+) ver=(\S+) mode=(\S+) net=(\w+)", out)
    check("служба на сервере (SSH): «EAC сейчас» — точка статуса AsdaEacServer отвечает (state ok, схема a68.*), без права IP нет",
          bool(me) and me.group(1) == "ok" and me.group(2).startswith("a68.") and me.group(4) == "False", out[-600:])
    import socket as _so
    try:
        _c = _so.create_connection((config.SERVER_VPN_IP, 8447), timeout=5)
        _c.close()
        ext = "соединение принято"
    except OSError as ex:
        ext = ex.__class__.__name__
    check("точка статуса EAC снаружи (адрес VPN сервера, порт 8447) не отвечает", ext != "соединение принято", ext)
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/autoblock/ladder" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/autoblock/ladder без входа — 401", code == 401, code)
