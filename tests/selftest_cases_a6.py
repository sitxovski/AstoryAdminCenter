# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_cases_a6.py — самотест шага А6.7 «Античит: дела» (22.11.2026; domains/cases.py, /api/cases/*, операции case.*, web/cases.js,
консоль cases, sql/adminc_21_san.sql, выкладка: каталог доказательств и SQL-шаг).

offline(check)  — исходник дел — тот же ac_case.py (ПК) / ext/anticheat с манифестом (сервер); выдача прав adminc_21 = записи исходника (таблицы,
                  столбцы UPDATE, процедуры — по тексту ac_case.py); отказы ввода без базы (номер дела, окно ГГГГММДД, события, выдержка, решение,
                  апелляция, лишний параметр), на ПК без хранилища — понятный отказ; права ролей и маршруты; тексты отказов без «; »; переводы EN
                  (shadowed_translations = 0); веб без innerHTML; консоль; выкладка (adminc_21 после adminc_04, каталог cases в $keep, ACL по SID).
sandbox(check, ldb) — СВОИ базы LocalDB: настоящие san_01_migrate.sql и миграции схемы ac, AsdaStoryOp / Joy1 / AsdaAdmin; НАСТОЯЩИЙ adminc_21_san.sql
                  и запись дел под пользователем asda_ops (EXECUTE AS USER — права логина проверяются самим SQL Server); даты синтетики
                  фиксированные (январь 2026). Полный цикл учебного дела на служебной учётке 7 (owner1): open → decide без доказательств (отказ) →
                  attach события → decide ступень 3 (отказ: один источник) → выдержка журнала стойки (подмена чтения logs.IO) → export →
                  rollback_report → decide 1 → withdraw → decide 3 (подтверждение номером дела) = account.block (us_block 5, строка BlockList, своя
                  запись журнала) → appeal → пересмотр тем же лицом (отказ) → другим owner2 (в силе) → lift = account.unblock → close → verify.
                  Отказы: gm decide, admin / gm на служебной учётке, снятие двух источников не владельцем, файл > max_file_mb, нет подтверждения,
                  блок не встал (триггер сбрасывает us_block) — блок откатан своим undo, дело не исполнено; ручная ступень → execute → close.
live(check)     — только чтение живой dev: права asda_ops / asda_admin по adminc_11 / adminc_10 (через sqlcmd по SSH не нужен — HAS_PERMS_BY_NAME
                  читает asda_admin о себе), список дел = san.cases, AC-0001 целиком (show), служба на сервере: verify AC-0001 из каталога службы
                  (sha256 = реестру), ext/ с md5 исходника, без входа — 401. Ничего не пишет (дел и блоков на живой не создаёт).
Побочных эффектов при импорте нет.
"""
import datetime
import hashlib
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
SQL_DIR = os.path.join(PORT, "AstoryServer", "Docs", "SQL")
CYR = re.compile("[А-Яа-яЁё]")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _refused(fn):
    """Текст отказа OpRefused или None."""
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _route(path, meth="GET"):
    from api import server
    for m, rx, fn, perm, _full in server.ROUTES:
        if m == meth and rx.match(path):
            return fn, perm
    return None, None


def _ctx(login, role):
    from core import ops
    return ops.Ctx(None, login, role, "127.0.0.1", "test")


def source_writes(text):
    """Что пишет ac_case.py в san.* (по тексту исходника): {"insert": {таблица}, "update": {таблица: {столбцы}}, "exec": {процедура}}."""
    ins = set(re.findall(r"INSERT INTO joylog1\.san\.(\w+)", text))
    upd = {}
    for t, body in re.findall(r'UPDATE joylog1\.san\.(\w+) SET (.+?)WHERE', text.replace('"\n', "").replace('" "', "").replace('"', ""), re.S):
        upd.setdefault(t, set()).update(re.findall(r"(\w+) = ", body))
    ex = set(re.findall(r"EXEC joylog1\.san\.(\w+)", text))
    return {"insert": ins, "update": upd, "exec": ex}


def grants(sql):
    """Выдачи adminc_21_san.sql: {"insert": {…}, "update": {таблица: {столбцы}}, "exec": {…}, "select": {…}}."""
    g = {"insert": set(re.findall(r"^GRANT INSERT ON san\.(\w+)", sql, re.M)), "select": set(re.findall(r"^GRANT SELECT ON san\.(\w+)", sql, re.M)),
         "exec": set(re.findall(r"^GRANT EXECUTE ON san\.(\w+)", sql, re.M)), "update": {}}
    for cols, t in re.findall(r"^GRANT UPDATE \(([^)]+)\) ON san\.(\w+)", sql, re.M | re.S):
        g["update"][t] = {c.strip() for c in cols.split(",")}
    return g


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, config, i18n
    from domains import acsrc, cases as C
    import domains
    domains.load_all()
    m, cfg, src = C.source()
    check("дела: исходник — тот же ac_case.py ПК (команды open … rollback-report), конфиг = ac_case.load_config() (лестница 0…6, два источника со ступени 3)",
          src["where"] == "port" and set(m.COMMANDS) >= {"open", "attach", "export", "decide", "execute", "withdraw", "lift", "appeal", "close", "verify",
                                                          "rollback-report"} and cfg["two_sources_from_step"] == 3 and sorted(m.ladder_map(cfg)) == list(range(7))
          and src["config_md5"] == hashlib.md5(open(os.path.join(AC_DIR, "ac_case_config.json"), "rb").read()).hexdigest(), src)
    # ---- выдача прав adminc_21 = записи исходника
    text = open(os.path.join(AC_DIR, "ac_case.py"), encoding="utf-8").read()
    sw = source_writes(text[:text.index("def selftest_offline")])          # самопроверка исходника пишет образцы отказов — не в счёт
    sql = open(os.path.join(ROOT, "sql", "adminc_21_san.sql"), encoding="utf-8").read()
    g = grants(sql)
    panel = open(os.path.join(ROOT, "domains", "cases.py"), encoding="utf-8").read()
    pw = source_writes(panel)
    ok_upd = all(t in g["update"] and cols <= g["update"][t] for t, cols in list(sw["update"].items()) + list(pw["update"].items()))
    check("дела SQL: adminc_21 выдаёт asda_ops ровно записи исходника и панели — INSERT %s, UPDATE столбцов %s, EXEC %s; SELECT 5 таблиц; "
          "status / учётка — не правятся (только процедурой), DELETE — нигде"
          % (sorted(sw["insert"] | pw["insert"]), {t: len(c) for t, c in g["update"].items()}, sorted(g["exec"])),
          g["insert"] == sw["insert"] | pw["insert"] and set(g["update"]) == set(sw["update"]) | set(pw["update"]) and ok_upd
          and g["exec"] == {"UP_SAN_CaseOpen", "UP_SAN_SetStatus"} == sw["exec"] | {"UP_SAN_CaseOpen"} and len(g["select"]) == 5
          and "status" not in g["update"]["cases"] and not re.search(r"^GRANT [^\n]*DELETE", sql, re.M)
          and "DENY UPDATE (status" in sql and "REVOKE EXECUTE FROM [asda_ops]" in sql, (sw, pw, g))
    check("дела SQL: QUOTED_IDENTIFIER отдельным пакетом, нет схемы san — отказ RAISERROR, запрет EXECUTE снят с базы и поставлен на схемы dbo и ac",
          re.search(r"^SET QUOTED_IDENTIFIER ON;\s*\nGO", sql, re.M) and "RAISERROR(N'adminc_21" in sql
          and "DENY EXECUTE ON SCHEMA::dbo TO [asda_ops]" in sql and "DENY EXECUTE ON SCHEMA::ac" in sql)
    a04 = open(os.path.join(ROOT, "sql", "adminc_04_ops.sql"), encoding="utf-8").read()
    v11 = open(os.path.join(ROOT, "sql", "adminc_11_verify_ops.sql"), encoding="utf-8").read()
    v10 = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    r99 = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    blk = a04[a04.index("USE [JoyLog1];"):a04.index("USE [AsdaStoryOp];", a04.index("USE [JoyLog1];"))]
    check("дела SQL: adminc_04 в JoyLog1 больше не запрещает EXECUTE на базу (иначе выдача adminc_21 пропала бы на следующей выкладке); проверки "
          "adminc_11 (исполняемых 2, вне san 0, san по таблицам и столбцам) и adminc_10 (asda_admin — чтение san, записи нет); откат adminc_99",
          "DENY EXECUTE, ALTER" not in blk and "DENY EXECUTE ON SCHEMA::dbo TO [asda_ops]" in blk
          and "'ops.log executable objects'" in v11 and re.search(r"'ops\.log executable objects'.+\), 2(?: \+ CASE WHEN EXISTS \(SELECT 1 FROM JoyLog1\.sys\.schemas WHERE name = N'chat'\) THEN 2 ELSE 0 END)?\r?\n", v11)   # ★ А6.12: + 2 процедуры chat
          and "'ops.log executable outside san'" in v11 and "'ops.san.cases UPDATE status'" in v11 and "'ops.san other tables write'" in v11
          and "'log.san.cases SELECT'" in v10 and "'log.san.UP_SAN_SetStatus EXEC'" in v10 and (r99 is None or "REVOKE EXECUTE ON san.UP_SAN_SetStatus FROM [asda_ops]" in r99))
    # ---- отказы без базы
    from core.ops import OpRefused
    owner, admin, gm = _ctx("owner1", "owner"), _ctx("admin2", "admin"), _ctx("gm3", "gm")
    from core import ops
    A = lambda name, p, c=owner: _refused(lambda: ops.REGISTRY[name]._check(c, p))   # noqa: E731
    why = [A("case.open", {"title": "x"}), A("case.open", {"uid": 7, "login": "a", "title": "x"}), A("case.open", {"uid": 7}),
           A("case.open", {"uid": "x", "title": "t"}), A("case.open", {"login": "a'b", "title": "t"}), A("case.open", {"uid": 7, "title": "t", "bogus": 1}),
           A("case.attach", {"case": "AC-X"}), A("case.attach", {"case": 1}), A("case.attach", {"case": 1, "events": ["x"]}),
           A("case.attach", {"case": 1, "from": "2026-01-01", "to": "20260102"}), A("case.attach", {"case": 1, "from": "20260230", "to": "20260301"}),
           A("case.attach", {"case": 1, "from": "20260105", "to": "20260101"}),
           A("case.attach", {"case": 1, "log": {"source": "gslog", "proc": "GameServer", "name": "x.txt"}, "needles": ["ab"]}),
           A("case.attach", {"case": 1, "log": {"source": "gslog", "proc": "GameServer", "name": "x.txt"}, "needles": [], "label": "L"}),
           A("case.attach", {"case": 1, "log": {"source": "gslog", "proc": "GameServer", "name": "x.txt"}, "needles": ["ab"], "label": "L"}, gm),
           A("case.attach", {"case": 1, "needles": ["ab"]}),
           A("case.decide", {"case": 1, "step": 7, "text": "t"}), A("case.decide", {"case": 1, "step": 3}),
           A("case.decide", {"case": 1, "step": 3, "text": "t", "reason_en": "кириллица"}),
           A("case.decide", {"case": 1, "step": 3, "text": "t", "override_two_sources": "x"}, admin),
           A("case.close", {"case": 1, "outcome": "x", "text": "t"}), A("case.close", {"case": 1, "outcome": "sanctioned", "text": "t", "force_unverified": "x"}, admin),
           A("case.appeal", {"case": 1, "text": "t", "resolve": "maybe"}), A("case.export", {"case": 1, "format": "xml"}),
           A("case.rollback_report", {"case": 1, "serials": ["not-guid"]}), A("case.rollback_report", {"case": 1})]
    check("дела: отказы ввода без базы — учётка (номер или логин, одно), суть, номер дела, события, окно ГГГГММДД (форма, нет даты, порядок), выдержка "
          "(метка, подстроки, право logs.view), ступень, основание, причина латиницей, снятие двух источников и закрытие без проверки — только "
          "владелец, итог, апелляция, формат, Serial, лишний параметр (%d)" % len(why), all(why), why)
    check("дела: тексты отказов без «; »", all("; " not in x for x in why if x), [x for x in why if x and "; " in x])
    sv = (C.STORE_OVERRIDE, config.get().on_server)
    try:
        C.STORE_OVERRIDE, config.get().on_server = None, False
        w_pc = _refused(lambda: C.store_root(True))
        lad = C.ladder(owner)
    finally:
        C.STORE_OVERRIDE, config.get().on_server = sv
    check("дела на ПК: хранилище — каталог службы на сервере (запись — понятный отказ, не 500), лестница читается, can_write = нет",
          w_pc == C.STORE_PC and not lad["can_write"] and lad["store_note"] == C.STORE_PC and len(lad["ladder"]) == 7 and C.CASES_ROOT == r"@@ASTORY_SERVER_ROOT@@\AdminCenter\cases")
    # ---- на сервере: только ext/ с манифестом
    tmp = tempfile.mkdtemp(prefix="cs_ext_")
    sv2 = (acsrc.EXT, acsrc.MANIFEST, C.AC_EXT, config.get().on_server)
    try:
        acsrc.EXT, acsrc.MANIFEST, C.AC_EXT = tmp, os.path.join(tmp, "MANIFEST.json"), os.path.join(tmp, "anticheat")
        config.get().on_server = True
        w0 = _refused(lambda: C.source())
        os.makedirs(C.AC_EXT)
        man = {}
        for f in C.AC_FILES:
            b = open(os.path.join(AC_DIR, f), "rb").read()
            open(os.path.join(C.AC_EXT, f), "wb").write(b)
            man["anticheat/" + f] = hashlib.md5(b).hexdigest()
        open(acsrc.MANIFEST, "w", encoding="utf-8").write(json.dumps(man))
        _m2, _c2, src2 = C.source()
        with open(os.path.join(C.AC_EXT, "ac_case.py"), "ab") as f:
            f.write(b"\n# x\n")
        w2 = _refused(lambda: C.source())
    finally:
        acsrc.EXT, acsrc.MANIFEST, C.AC_EXT, config.get().on_server = sv2
        shutil.rmtree(tmp, ignore_errors=True)
    check("дела на сервере: нет копии ext/ — понятный отказ; копия с манифестом — исполняется (md5 = исходнику ПК); подмена кода — отказ манифеста",
          w0 and w0.startswith("исходник дел ac_case не прочитан") and src2["where"] == "ext" and src2["code_md5"] == src["code_md5"]
          and w2 and "манифест" in w2, (w0, src2, w2))
    # ---- права и маршруты
    roles = ("owner", "admin", "gm", "support")
    rp = {p: {r for r in roles if auth.can(r, p)} for p in ("ac.case", "ac.decide_low", "ac.decide", "ac.appeal")}
    ops_perm = {n: ops.REGISTRY[n].perm for n in ops.REGISTRY if n.startswith("case.")}
    check("дела: права — ac.case owner/admin/gm (open, attach, export, rollback_report), ac.decide_low owner/admin/gm (decide, execute, withdraw "
          "ступеней 0–2; ревизия 59 Н-2), ac.decide owner/admin (со ступени 3, lift, close), ac.appeal owner/admin; операций case.* 10",
          rp == {"ac.case": {"owner", "admin", "gm"}, "ac.decide_low": {"owner", "admin", "gm"}, "ac.decide": {"owner", "admin"},
                 "ac.appeal": {"owner", "admin"}} and C.DECIDE_HIGH == 3
          and ops_perm == {"case.open": "ac.case", "case.attach": "ac.case", "case.export": "ac.case", "case.rollback_report": "ac.case",
                           "case.decide": "ac.decide_low", "case.execute": "ac.decide_low", "case.withdraw": "ac.decide_low", "case.lift": "ac.decide",
                           "case.close": "ac.decide", "case.appeal": "ac.appeal"}, (rp, ops_perm))
    rt = {p: _route(p) for p in ("/api/cases/ladder", "/api/cases/list", "/api/cases/show", "/api/cases/verify")}
    check("дела: маршруты /api/cases/ladder | list | show | verify — GET, право ac.view", all(fn and perm == "ac.view" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})
    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in why if x] + [C.STORE_PC, w0, w2] + [x["name"] for x in cfg["ladder"]] + [x["mechanism"] for x in cfg["ladder"]] + [
            o.title for n, o in ops.REGISTRY.items() if n.startswith("case.")] + [x.strip() for x in RU_SAMPLES]
        miss = [x for x in ru if CYR.search(i18n.tr(x))]
        check("дела EN: отказы, заметки, тексты исходника (отказы и строки вывода — %d образцов), названия операций — без русских слов" % len(ru),
              not miss, miss[:8])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n = P.shadowed_translations()
    check("дела: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n, not sh, sh[:5])
    # ---- веб
    js = open(os.path.join(ROOT, "web", "cases.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    acj = open(os.path.join(ROOT, "web", "acjournal.js"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    check("дела веб: раздел #/cases с правом ac.view, маршрут viewCases, скрипт после acjournal.js; ссылка «к делу» из ленты «Античит» и «Дела» из "
          "карточки учётки (#/cases?uid=)",
          '["#/cases", "Античит: дела", "ac.view"' in app and 'case "cases": return viewCases(my, q);' in app
          and 0 < idx.index("/acjournal.js") < idx.index("/cases.js") and "#/cases?uid=" in acj and "#/cases?uid=" in app and "&ev=" in acj)
    check("дела веб: без innerHTML, данные — текстовыми узлами (acText), действия — op(case.*) с предпросмотром, подтверждение номером дела",
          "innerHTML" not in js and "acText(" in js and 'op("case.' not in js and "csOp(" in js and "confirm:" in js)
    labels = set(re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|div|option)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) \
        | set(re.findall(r'\["([^"\]]+)", (?:r|c|b|e|x|v|l) =>', js)) | set(re.findall(r'T\("([^"]+)"', js)) \
        | set(re.findall(r':\s*"([^"]+)"', js[js.index("CS_STATUS"):js.index("function csBadge")]))
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("дела веб EN: у подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack, lack[:8])
    try:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", "cases.js")], capture_output=True, timeout=60)
        check("дела: node --check web/cases.js", r.returncode == 0, r.stderr[-300:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("дела: node --check web/cases.js (node не запустился)", False, str(ex))
    # ---- консоль и выкладка
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "cases"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    c1, o1 = con("list", "--bogus")
    c2, o2 = con("show")
    c3, o3 = con("nope")
    c4, o4 = con("decide", "AC-0001", "--step")
    c5, o5 = con("appeal", "AC-0001", "--text", "x", "--resolve", "upheld")
    w_cli = _refused(lambda: ops.REGISTRY["case.appeal"]._go(ops.Ctx(None, "cli:x@pc", "owner", "", "cli"), {"case": 1, "text": "x"}, True))
    check("дела консоль (ревизия 59 Н-3): действие без --as <логин панели> — отказ до базы; консольный контекст без учётки панели — отказ операции",
          c5 and "--as <логин панели>" in o5 and w_cli == C.CLI_AS, (o5[-200:], w_cli))
    check("дела консоль: неизвестный ключ, нет номера дела, неизвестное действие, ключ без значения — отказ без обращения к базе",
          c1 and "неизвестный аргумент --bogus" in o1 and c2 and "номер дела" in o2 and c3 and "нужно действие" in o3 and c4 and "нет значения" in o4,
          (o1[-200:], o2[-200:], o3[-200:], o4[-200:]))
    adm = open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read()
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    r6 = dep.index("Run 'adminc_04_ops.sql' $null")
    check("дела выкладка: adminc_21 — после adminc_04 в шаге 5, каталог cases — в $keep (оба места), шаг 3б создаёт его с проверкой ACL по SID "
          "(Administrators S-1-5-32-544, SYSTEM S-1-5-18, только наследование); консоль описана в справке",
          dep.index("Run 'adminc_21_san.sql' $null") > r6 and dep.count("'otp_archive','cases'") == 2 and "S-1-5-32-544" in dep and "S-1-5-18" in dep
          and "AreAccessRulesProtected" in dep and "IsInherited" in dep and "  cases …" in adm)


# образцы строк исходника и панели для проверки перевода (тексты отказов ac_case.py и строки вывода — с данными латиницей)
RU_SAMPLES = (
    "AC-0001 в статусе open: решение выносится по собранным доказательствам (evidence) или при пересмотре (appeal)",
    "ступень 3 требует доказательств из двух независимых источников, есть: ac.other",
    "ступень 3 требует доказательств из двух независимых источников, есть: нет",
    "AC-0001 закрыто - сначала апелляция", "AC-0001 закрыто - материалы не дополняются (сначала апелляция)",
    "дела 5 нет", "учётка не найдена: abc", "в деле нет событий журнала",
    "события ac.other #5 нет (очищено журналом или неверный номер)", "таблица журнала: одна из operator_refusal, identity_mismatch",
    "AC-0001 в статусе open — исполнить можно только вынесенное решение", "блок исполняется командой decide (штатным скриптом), не вручную",
    "AC-0001 в статусе executed — отозвать можно только неисполненное решение (decision)",
    "по делу действует блок - решение исполнено, отмена только через апелляцию", "AC-0001: активных блоков по делу нет",
    "AC-0001 не на апелляции", "решение отменяется, но блок дела ещё действует - сначала lift AC-0001",
    "AC-0001 в статусе open — апелляция - на исполненное или закрытое решение", "AC-0001 закрыто без санкции (acquitted) - обжаловать нечего",
    "срок апелляции истёк 2026-01-01 00:00:00 — принять всё равно - --late \"почему\"", "AC-0001 уже закрыто",
    "на апелляции - закрывается решением appeal --resolve", "итог sanctioned - только после исполненного решения",
    "решение уже исполнено - его отмена только через апелляцию (overturned)", "overturned ставит только appeal --resolve",
    "у дела действует блок - сначала lift", "целостность доказательств нарушена - закрытие отклонено (--force-unverified \"почему\" - под запись)",
    "откат по Serial: сначала rollback-report AC-0001 (отчёт «что откатить»)", "--hours только для блока на срок (ступени 3, 4)",
    "у учётки abc нет персонажа x (есть: y)", "нечего прикладывать (нужны --event / --events-auto / --file)", "ступень 0..6",
    "событие: ТАБЛИЦА:event_id, например move_combat:7158", "для файла нужна метка источника --source (например «NpcServer SpeedHack»)",
    "нет серийников (--serial GUID ... или --window FROM TO)", "логин учётки изменился с открытия дела (abc -> abd)",
    "апелляцию пересматривает другое лицо — решение по делу выносил owner1", "подтвердите номером дела AC-0001",
    "дела служебных учёток (номер ≤ 5000) ведёт только владелец", "параметр override_two_sources — только владелец",
    "журнал больше 200 МБ (max_file_mb) - выдержка из него не делается", "блок не встал (блок не удержался: сервер в этот момент снял истёкшие блоки при входе игрока (UP_AC_LiftExpiredBlock) — поставьте блок ещё раз) - блок откатывается, дело не исполнено",
    "после account.block нет строки BlockList / us_block != 5 - блок откатывается, дело не исполнено",
    "у учётки есть блоки не этого дела - снятие (как OPBlockDel) снимет ВСЕ, подтвердите флагом «снять и чужие блоки» (all_blocks)",
    "account.block: служебные учётки (номер ≤ 5000) блокирует только владелец", "нет файла: GameServer\\Log\\Log_SpeedHack\\SpeedHack_20260112.txt",
    "в окне 300 событий учётки — больше 200, сузьте окно", "база дел отказала: UP_SAN_SetStatus: status closed (expected open)",
    "дела: нет подключения к joylog1: x", "дела не прочитаны: x", "конфиг дел ac_case_config.json не разобран: x",
    "слишком много тяжёлых действий с делами — не больше 30 в час на пользователя, подождите",
    "журнал «gslog» пишется без общего доступа - выдержка из него не делается",
    "журнал больше 16 МБ - выдержка читает файл целиком, такой файл не читается",
    "блок дела — операция account.block, нужно право «players.block»", "снятие блока дела — операция account.unblock, нужно право «players.unblock»",
    "после account.unblock us_block = 5, строк BlockList 1 - снятие откатывается",
    "дело не записано (x) — и откат блока не выполнен: y", "x — и откат блока не выполнен: y — проверьте учётку вручную",
    "штатные скрипты блока в панели не исполняются - блок только операцией account.block",
    "решение со ступени 3 — только администратор или владелец (gm — ступени 0–2)", "блок поставлен делом AC-0001 — снимите через дело (case.lift)",
    "блок снят делом AC-0001 — откатом журнала не возвращается, новый блок — решением по делу (case.decide)",
    "дело не записано — и откат блока не выполнен: account.block №5: x — проверьте учётку вручную",
    "консоль: действия с делами — от имени учётки панели, укажите --as <логин панели> (апелляцию пересматривает другое лицо — сверка по учётке панели)",
    # строки вывода
    "AC-0002 открыто: учётка 7 (svc7), персонаж Hero; папка C:/x/AC-0002", "AC-0002 открыто: учётка 7 (svc7); папка C:/x/AC-0002",
    "  уже в деле: ac.other #3", "  выдержка: 2 строк", "  + excerpt files/001_SpeedHack_20260112.txt.excerpt.txt  sha256 ab12",
    "событий в окне 2026-01-05 00:00:00 .. 2026-01-06 00:00:00 по учётке/персонажам: 2",
    "AC-0002: событий +1, файлов +0; источники: ac.other", "AC-0002: событий +0, файлов +1; источники: ac.other; файл: NpcServer SpeedHack",
    "AC-0002: выгружено событий 1 -> C:/x/events.json, C:/x/events.csv", "  прошлое дело AC-0001: ступень 3, итог sanctioned",
    "  BlockList: 2026-01-01 00:00:00 .. 2026-01-02 00:00:00  Speed Hack", "  в т.ч. автоблоков/GM-6094 (UPHackBlock, причина «Speed Hack»): 1",
    "ВНИМАНИЕ: правило двух источников снято вручную: test", "AC-0002: учётка 7 (svc7); ступень 3 «Блок на сутки», срок 24 ч; источники: ac.other; файл: x",
    "AC-0002: учётка 7 (svc7); ступень 1 «Предупреждение»; источники: ac.other", "  ВНИМАНИЕ: по прошлым санкциям лестница предлагает ступень не ниже 4",
    "  срок 2 ч вне лестницы (ступень 3 = 24 ч) - записывается в дело",
    "решение записано; исполнение - вручную (GM-нотис (чат 6028/6029) вручную, затем ac_case.py execute), затем: ac_case.py execute AC-0002 --text \"...\"",
    "ВНИМАНИЕ: учётка числится в игре - блок не выкидывает (нужен GM Kick 6018 или выход игрока)",
    "исполнено: блок: us_block = 5, BlockList 2026-01-05 10:00:00 .. 2026-01-06 10:00:00, причина «AC-0002 s3 24h» (панель account.block, журнал №5)",
    "AC-0002: исполнено (warned)", "AC-0002: решение отозвано, дело снова на доказательствах", "  чужой блок: 2026-01-01 .. 2026-01-02 «Speed Hack»",
    "AC-0002: блок снят; BlockList -> BlockHistory; us_block = 0", "AC-0002: апелляция - upheld",
    "AC-0002: апелляция принята к рассмотрению; пересмотр - другим лицом: appeal AC-0002 --resolve upheld|overturned",
    "AC-0002 закрыто: sanctioned. Хранить материалы не меньше 180 дней.", "AC-0002: отчёт отката (без записи) по 1 серийникам -> C:/x/r.md",
    "предпросмотр: блок учётки svc7 (7) на 24 ч: AC-0002 s3 24h", "предпросмотр: выдержка из GameServer\\Log\\x.txt (10 б) по подстрокам: ab | cd",
    "предпросмотр: снять блок учётки svc7 (7): строк блока 1, us_block 5 → 0",
    "предпросмотр: строк BlockList нет, us_block = 0 - блок уже снят (истёк при входе или вне дела), отмечается в деле",
    "  вход по данным БД возможен: us_block 0, BlockList пуст, пароль задан, замка нет", "  строк BlockList: 1 (действующих 1)",
    "  us_block = 5 -> статус 5 (блок)", "  пароль не задан (us_pwhash/us_pwsalt NULL) -> статус 3",
    "  Flag = 1 (числится в игре) -> первый вход даст статус 4 (сброс), второй пройдёт",
    "AC-0002 [closed]: файлов 3, проверено 3, ошибок 0; событий в журнале 1, очищено журналом 0 (снимки целы)",
    "  FAIL файл files/001_a.txt: файла нет", "  FAIL файл files/001_a.txt: sha256 ab12, в БД cd34", "  FAIL файл files/001_a.txt: размер 5, в БД 6",
    "  ЗАМЕЧАНИЕ лишний файл (нет в реестре): files/002_x.txt", "  ЗАМЕЧАНИЕ manifest.json расходится с реестром БД (перезапишется следующей записью)",
    "  ЗАМЕЧАНИЕ нет manifest.json", "  FAIL снимок ac.other #3 не совпал со своим sha256", "  FAIL строка журнала ac.other #3 ИЗМЕНИЛАСЬ после привязки",
    "  ЗАМЕЧАНИЕ блок «AC-0001 s3 1h» не снят по делу, но строки BlockList нет (снят вне дела или истёк при входе)",
    "  FAIL снятый блок «AC-0001 s3 1h»: строки BlockHistory нет",
    "ac.move_combat",
)


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _sub(text, names):
    for a, b in (("joylog1", names["J"]), ("JoyLog1", names["J"]), ("AsdaStoryOp", names["O"]), ("Joy1", names["Y"])):
        text = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % a, b, text)
    return text


def sandbox(check, ldb):
    """Свои базы LocalDB: настоящие san_01 + adminc_21, запись дел под пользователем asda_ops (EXECUTE AS USER), полный цикл и отказы."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_ac_a6 as S6
    from core import audit, db, ops
    from domains import cases as C, logs as LG
    import domains
    domains.load_all()
    tag = secrets.token_hex(3)
    names = {"J": "AsdaCsJ_" + tag, "O": "AsdaCsO_" + tag, "Y": "AsdaCsY_" + tag, "A": "AsdaCsA_" + tag}
    mst = ldb("master")
    for k, n in names.items():
        mst.cursor().execute("CREATE DATABASE [%s] COLLATE %s" % (n, "Cyrillic_General_CI_AS" if k == "A" else "Arabic_CI_AS"))
    store = tempfile.mkdtemp(prefix="cs_store_")
    saved = (C.STORE_OVERRIDE, C.XLAT, LG.IO, LG.procs_of)
    try:
        a = ldb(names["A"])
        for b in _batches(open(os.path.join(ROOT, "sql", "adminc_02_schema.sql"), encoding="utf-8").read()):
            a.cursor().execute(b)
        o = ldb(names["O"]).cursor()
        o.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(61), us_block TINYINT, Flag TINYINT, UserNum INT, "
                  "us_pwhash VARCHAR(64), us_pwsalt VARCHAR(32), us_pwfail INT, us_pwfail_at DATETIME)")
        o.execute("INSERT dbo.Us_member VALUES (7, 'svc7', 0, 0, -1, 'h', 's', 0, NULL), (8, 'svc8', 0, 0, -1, 'h', 's', 0, NULL), "
                  "(9001, 'alpha', 0, 0, -1, 'h', 's', 0, NULL)")
        for t in ("BlockList", "BlockHistory"):
            o.execute("CREATE TABLE dbo.%s (Userindex INT, Uid VARCHAR(61), Cou TINYINT, grade TINYINT, BlackDate SMALLDATETIME, "
                      "CloseDate SMALLDATETIME, Reason VARCHAR(300))" % t)
        y = ldb(names["Y"]).cursor()
        y.execute("CREATE TABLE dbo.Charinfo (Userindex INT, Charidx TINYINT, Charname VARCHAR(32))")
        y.execute("INSERT dbo.Charinfo VALUES (7, 10, 'Hero7'), (8, 10, 'Hero8'), (9001, 10, 'Alpha1')")
        y.execute("CREATE TABLE dbo.Item (Userindex INT, Charidx TINYINT, Code INT, Plate INT, Posx INT, Amount INT, Durability INT, Upcount INT, "
                  "Refine INT, GainDate DATETIME, Uuid VARCHAR(40))")
        y.execute("CREATE TABLE dbo.Del_item (Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Amount INT, Uuid VARCHAR(40))")
        g1 = "11111111-2222-3333-4444-555555555555"
        y.execute("INSERT dbo.Item VALUES (7, 10, 20571, 1, 3, 1, 100, 0, 0, '2026-01-05T09:00:00', ?)", (g1,))
        jc = ldb(names["J"]).cursor()
        jc.execute("CREATE TABLE dbo.Loginfo (Userindex INT, Login DATETIME, State TINYINT)")
        jc.execute("CREATE TABLE dbo.ItemMoveLog (Edate DATETIME, Userindex INT, Charidx TINYINT, Code INT, Serial VARCHAR(40))")
        jc.execute("INSERT dbo.ItemMoveLog VALUES ('2026-01-05T09:00:00', 7, 10, 20571, ?), ('2026-01-07T09:00:00', 9001, 10, 20571, ?)",
                   (g1, "99999999-2222-3333-4444-555555555555"))
        ldb(names["Y"]).cursor().execute("CREATE TABLE dbo.SoulMate (Userindex INT, Ouserindex INT, State TINYINT)")
        for f in S6.MIGRATIONS:
            for b in _batches(S6._subst(open(os.path.join(S6.SQL_DIR, f), encoding="utf-8-sig").read(), {"J": names["J"], "O": names["O"], "Y": names["Y"]})):
                jc.execute(b)
        for b in _batches(_sub(open(os.path.join(SQL_DIR, "san_01_migrate.sql"), encoding="utf-8").read(), names)):
            jc.execute(b)
        jc.execute("CREATE USER asda_ops WITHOUT LOGIN")
        for b in _batches(_sub(open(os.path.join(ROOT, "sql", "adminc_21_san.sql"), encoding="utf-8").read(), names)):
            jc.execute(b)
        for when, uid in (("2026-01-05T10:00:00", 7), ("2026-01-05T10:05:00", 7), ("2026-01-06T10:00:00", 8), ("2026-01-07T10:00:00", 9001)):
            jc.execute("INSERT ac.other (ev_utc, ev_local, server_name, user_index, char_slot, char_name, ip, opcode, event_kind, value1, detail) "
                       "VALUES (?, ?, 'GameServer', ?, 10, 'Hero', '10.0.0.7', 4101, N'test kind', 1, N'speed x2')", (when, when, uid))
        jc.execute("INSERT ac.kick_block (ev_utc, ev_local, server_name, user_index, char_slot, char_name, opcode, event_kind) VALUES "
                   "('2026-01-05T10:06:00', '2026-01-05T10:06:00', 'GameServer', 7, 10, 'Hero', 4101, N'кик'), "
                   "('2026-01-07T10:06:00', '2026-01-07T10:06:00', 'GameServer', 9001, 10, 'Alpha1', 4101, N'кик')")
        perms = {r[0]: r[1] for r in jc.execute(
            "EXECUTE AS USER = 'asda_ops'; SELECT 'ins_log', HAS_PERMS_BY_NAME('san.case_log','OBJECT','INSERT') UNION ALL "
            "SELECT 'upd_status', HAS_PERMS_BY_NAME('san.cases','OBJECT','UPDATE','status','COLUMN') UNION ALL "
            "SELECT 'del_log', HAS_PERMS_BY_NAME('san.case_log','OBJECT','DELETE') UNION ALL "
            "SELECT 'exec_set', HAS_PERMS_BY_NAME('san.UP_SAN_SetStatus','OBJECT','EXECUTE') UNION ALL "
            "SELECT 'exec_purge', HAS_PERMS_BY_NAME('ac.UP_AC_JournalPurge','OBJECT','EXECUTE') UNION ALL "
            "SELECT 'sel_ac', HAS_PERMS_BY_NAME('ac.other','OBJECT','SELECT') UNION ALL "
            "SELECT 'ins_cases', HAS_PERMS_BY_NAME('san.cases','OBJECT','INSERT'); REVERT;").fetchall()}
        check("дела стенд: НАСТОЯЩИЙ adminc_21 на san_01 — asda_ops: INSERT case_log да, UPDATE status нет, DELETE нет, EXEC UP_SAN_SetStatus да, "
              "EXEC ac.UP_AC_JournalPurge нет, SELECT ac.* нет, INSERT san.cases нет",
              perms == {"ins_log": 1, "upd_status": 0, "del_log": 0, "exec_set": 1, "exec_purge": 0, "sel_ac": 0, "ins_cases": 0}, perms)
        mp = {"joylog1": names["J"], "AsdaStoryOp": names["O"], "Joy1": names["Y"]}

        class _Imp:
            """Связь «под asda_ops» (EXECUTE AS USER): перед закрытием — REVERT (иначе пул драйвера не сбросит сеанс)."""

            def __init__(self, cn):
                object.__setattr__(self, "_cn", cn)

            def __getattr__(self, k):
                return getattr(self._cn, k)

            def __setattr__(self, k, v):
                setattr(self._cn, k, v)

            def close(self):
                try:
                    self._cn.rollback()
                    self._cn.cursor().execute("REVERT")
                except Exception:
                    pass
                self._cn.close()

        def ops_cn(database):
            cn = ldb(mp.get(database, database))
            if database == "joylog1":
                cn.cursor().execute("EXECUTE AS USER = 'asda_ops'")
                return _Imp(cn)
            return cn
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("ops", ops_cn)
        db.set_override("admin", lambda database: ldb(names["A"]))
        C.STORE_OVERRIDE, C.XLAT = store, mp
        C._heavy.clear()
        # журнал стойки — подмена чтения (белый список logs тот же)
        LG.procs_of = lambda key: ["GameServer", "NpcServer"]
        body = ("1 Mon 5 Day 10 hou 0 min 1 sec : SpeedHack GM_x Hero7 Count 3 md5 0123456789abcdef0123456789ABCDEF pass s3cret\r\n"
                "1 Mon 5 Day 10 hou 0 min 2 sec : other line\r\n1 Mon 5 Day 10 hou 0 min 3 sec : speedhack Hero7 again password=hunter2x\r\n").encode("cp949")
        files = {}

        def path_of(name):
            return LG._dir_of("gslog", "GameServer", "Log_SpeedHack")[0] + "\\" + name
        files[path_of("SpeedHack_20260105.txt")] = body
        files[path_of("SpeedHack_20260106.txt")] = b"x" * 10
        big = {"n": 0}

        def stat(path):
            if path.endswith("SpeedHack_20260106.txt"):
                return (201 << 20, 1767600000000, 1767600000000)
            return (len(files[path]), 1767600000000, 1767600000000) if path in files else None

        def read(path, start, length, head=0):
            b = files[path]
            big["n"] += length
            return b[:head], b[start:start + length]
        LG.IO = {"stat": stat, "read": read, "list": lambda *a: (None, [])}
        o1, o2, adm, gm = _ctx("owner1", "owner"), _ctx("owner2", "owner"), _ctx("admin2", "admin"), _ctx("gm3", "gm")
        R = lambda c, name, p, dry=False: ops.run(c, name, p, dry)     # noqa: E731
        F = lambda c, name, p, dry=False: _refused(lambda: ops.run(c, name, p, dry))   # noqa: E731

        def case(no):
            return ldb(names["J"]).cursor().execute("SELECT status, ladder_step, outcome, decided_by FROM san.cases WHERE case_no = ?", (no,)).fetchone()

        def ub(uid):
            r = ldb(names["O"]).cursor().execute("SELECT us_block, (SELECT COUNT(*) FROM dbo.BlockList WHERE Userindex = ?), "
                                                 "(SELECT COUNT(*) FROM dbo.BlockHistory WHERE Userindex = ?) FROM dbo.Us_member WHERE Userindex = ?",
                                                 (uid, uid, uid)).fetchone()
            return tuple(r)

        def audits(action):
            return [tuple(r) for r in ldb(names["A"]).cursor().execute("SELECT result, login, target FROM adm.audit WHERE action = ? ORDER BY id",
                                                                       (action,)).fetchall()]
        # ---- права и служебные
        w_gm_svc = F(gm, "case.open", {"uid": 7, "title": "x"})
        w_adm_svc = F(adm, "case.open", {"uid": 7, "title": "x"})
        w_gm_dec = F(gm, "case.lift", {"case": 1, "text": "t"})
        check("дела стенд: служебная учётка 7 — gm и admin отказ «только владелец»; gm lift — нет права ac.decide (отказ в журнале)",
              w_gm_svc and "только владелец" in w_gm_svc and w_adm_svc and "только владелец" in w_adm_svc and w_gm_dec == "нет права «ac.decide»"
              and ("refused", "gm3", "") in audits("case.lift"), (w_gm_svc, w_adm_svc, w_gm_dec))
        # ---- полный цикл (owner1, служебная 7)
        pv = R(o1, "case.open", {"uid": 7, "char": "Hero7", "title": "training case", "hypothesis": "speed", "training": True}, True)
        n_after_dry = ldb(names["J"]).cursor().execute("SELECT COUNT(*) FROM san.cases").fetchone()[0]
        check("дела стенд: предпросмотр open — текст исходника «AC-0001 открыто…», в базе дел 0, папки нет",
              pv["preview"]["text"].startswith("AC-0001 открыто: учётка 7 (svc7), персонаж Hero7") and n_after_dry == 0
              and not os.path.exists(os.path.join(store, "AC-0001")), (pv["preview"], n_after_dry))
        r1 = R(o1, "case.open", {"uid": 7, "char": "Hero7", "title": "training case", "hypothesis": "speed", "training": True})
        check("дела стенд: open — AC-0001 (open), папка files / exports / reports и manifest.json, запись журнала case.open",
              r1["result"]["case_no"] == "AC-0001" and r1["result"]["status"] == "open"
              and all(os.path.isdir(os.path.join(store, "AC-0001", s)) for s in ("files", "exports", "reports"))
              and os.path.isfile(os.path.join(store, "AC-0001", "manifest.json")) and audits("case.open")[-1] == ("ok", "owner1", "account:7"), r1)
        w1 = F(o1, "case.decide", {"case": "AC-0001", "step": 3, "text": "t", "confirm": "AC-0001"})
        ev = ldb(names["J"]).cursor().execute("SELECT event_id FROM ac.other WHERE user_index = 7 ORDER BY event_id").fetchall()
        R(o1, "case.attach", {"case": 1, "events": ["other:%d" % ev[0][0]], "note": "first"})
        w2 = F(o1, "case.decide", {"case": 1, "step": 3, "text": "t", "confirm": "AC-0001"})
        check("дела стенд: decide без доказательств — отказ исходника (статус open); после события ac.other — статус evidence, decide ступень 3 — "
              "отказ «двух независимых источников» (есть: ac.other)",
              w1 and "решение выносится по собранным доказательствам" in w1 and case("AC-0001")[0] == "evidence"
              and w2 == "ступень 3 требует доказательств из двух независимых источников, есть: ac.other", (w1, w2))
        w_ov = F(adm, "case.decide", {"case": 1, "step": 3, "text": "t", "override_two_sources": "x"})
        lg = {"source": "gslog", "proc": "GameServer", "kind": "Log_SpeedHack", "name": "SpeedHack_20260105.txt"}
        w_big = F(o1, "case.attach", {"case": 1, "log": dict(lg, name="SpeedHack_20260106.txt"), "needles": ["speedhack"], "label": "GS SpeedHack"})
        pv2 = R(o1, "case.attach", {"case": 1, "log": lg, "needles": ["SpeedHack"], "label": "GS SpeedHack"}, True)
        read_dry = big["n"]
        R(o1, "case.attach", {"case": 1, "log": lg, "needles": ["SpeedHack"], "label": "GS SpeedHack"})
        exf = [f for f in os.listdir(os.path.join(store, "AC-0001", "files"))]
        exb = open(os.path.join(store, "AC-0001", "files", exf[0]), encoding="utf-8").read() if exf else ""
        evr = ldb(names["J"]).cursor().execute("SELECT kind, source_label, source_sha256, sha256, size_bytes FROM san.evidence WHERE case_id = 1").fetchall()
        check("дела стенд: снять два источника не владельцем — отказ; журнал > max_file_mb — отказ; предпросмотр выдержки файл не читает",
              w_ov == "параметр override_two_sources — только владелец" and w_big and "max_file_mb" in w_big and read_dry == 0
              and any(x.startswith("предпросмотр: выдержка") for x in pv2["preview"]["case_lines"]), (w_ov, w_big, read_dry, pv2["preview"]))
        check("дела стенд: выдержка — 2 строки из 3 (регистр не важен), MD5 32-hex и пароль замаскированы ДО отбора, шапка с sha256 источника, "
              "реестр: excerpt, метка, sha256 файла = в базе",
              len(exf) == 1 and exb.count("\n1\t") + exb.count("\n3\t") == 2 and "\n2\t" not in exb and "0123456789abcdef" not in exb
              and "hunter2x" not in exb and "s3cret" not in exb and "<md5 скрыт>" in exb and hashlib.sha256(body).hexdigest() in exb
              and [(r[0], r[1], r[2]) for r in evr] == [("excerpt", "GS SpeedHack", hashlib.sha256(body).hexdigest())]
              and evr[0][3] == hashlib.sha256(open(os.path.join(store, "AC-0001", "files", exf[0]), "rb").read()).hexdigest(), (exf, exb[:400], evr))
        R(o1, "case.export", {"case": 1, "format": "json,csv"})
        R(o1, "case.rollback_report", {"case": 1, "from": "20260101", "to": "20260131"})
        item_after = ldb(names["Y"]).cursor().execute("SELECT COUNT(*) FROM dbo.Item WHERE Uuid = ?", (g1,)).fetchone()[0]
        kinds = sorted(r[0] for r in ldb(names["J"]).cursor().execute("SELECT kind FROM san.evidence WHERE case_id = 1").fetchall())
        check("дела стенд: export json+csv и rollback_report (.json + .md) в реестре; Joy1.Item не изменён (отчёт — только чтение)",
              kinds == ["excerpt", "export", "export", "report", "report"] and item_after == 1, kinds)
        R(o1, "case.decide", {"case": 1, "step": 1, "text": "warn first"})
        R(o1, "case.withdraw", {"case": 1, "text": "test withdraw"})
        st_w = case("AC-0001")
        w_cf = F(o1, "case.decide", {"case": 1, "step": 3, "hours": 2, "text": "two sources", "reason_en": "training"})
        pv3 = R(o1, "case.decide", {"case": 1, "step": 3, "hours": 2, "text": "two sources", "reason_en": "training"}, True)
        ub_dry = ub(7)
        r3 = R(o1, "case.decide", {"case": 1, "step": 3, "hours": 2, "text": "two sources", "reason_en": "training", "confirm": "ac-0001"})
        blk = ldb(names["O"]).cursor().execute("SELECT Reason, DATEDIFF(MINUTE, BlackDate, CloseDate) FROM dbo.BlockList WHERE Userindex = 7").fetchall()
        cb = ldb(names["J"]).cursor().execute("SELECT reason, hours, apply_via, lifted_at FROM san.case_block WHERE case_id = 1").fetchall()
        check("дела стенд: decide 1 → withdraw — снова evidence без ступени; decide 3 без подтверждения — отказ «подтвердите номером дела»; "
              "предпросмотр — план account.block, учётка не тронута",
              st_w[0] == "evidence" and st_w[1] is None and w_cf == "подтвердите номером дела AC-0001"
              and "предпросмотр: блок учётки svc7 (7) на 2 ч: AC-0001 s3 2h: training" in pv3["preview"]["case_lines"] and ub_dry == (0, 0, 0),
              (st_w, w_cf, pv3["preview"], ub_dry))
        check("дела стенд: decide 3 (2 ч) = account.block — us_block 5, одна строка BlockList «AC-0001 s3 2h: training» на 120 мин, san.case_block со "
              "ссылкой на запись журнала account.block, дело executed",
              r3["result"]["status"] == "executed" and ub(7) == (5, 1, 0) and [tuple(x) for x in blk] == [("AC-0001 s3 2h: training", 120)]
              and len(cb) == 1 and cb[0][0] == "AC-0001 s3 2h: training" and cb[0][1] == 2 and "account.block, журнал №" in cb[0][2]
              and audits("account.block")[-1] == ("ok", "owner1", "account:7"), (r3["result"], ub(7), blk, cb))
        R(o1, "case.appeal", {"case": 1, "text": "not me", "who": "player"})
        w_same = F(o1, "case.appeal", {"case": 1, "text": "x", "resolve": "upheld"})
        R(o2, "case.appeal", {"case": 1, "text": "evidence holds", "resolve": "upheld"})
        st_a = case("AC-0001")
        check("дела стенд: апелляция — пересмотр тем же лицом (owner1 выносил решение) — отказ; другим (owner2) — в силе, снова executed",
              w_same == "апелляцию пересматривает другое лицо — решение по делу выносил owner1" and st_a[0] == "executed", (w_same, st_a))
        w_cl = F(o1, "case.close", {"case": 1, "outcome": "acquitted", "text": "x"})
        w_lc = F(o1, "case.lift", {"case": 1, "text": "lift"})
        R(o1, "case.lift", {"case": 1, "text": "lift", "confirm": "AC-0001"})
        cb2 = ldb(names["J"]).cursor().execute("SELECT lifted_by, in_history, lift_via FROM san.case_block WHERE case_id = 1").fetchone()
        check("дела стенд: закрыть «оправдан» при исполненном блоке — отказ исходника; lift без подтверждения — отказ; lift = account.unblock — "
              "us_block 0, BlockList пуст, строка в BlockHistory, san.case_block снят (in_history 1)",
              w_cl and "апелляцию" in w_cl and w_lc == "подтвердите номером дела AC-0001" and ub(7) == (0, 0, 1)
              and tuple(cb2)[:2] == ("owner1", True) and "account.unblock" in cb2[2] and audits("account.unblock")[-1][0] == "ok", (w_cl, w_lc, ub(7), cb2))
        R(o1, "case.close", {"case": 1, "outcome": "sanctioned", "text": "training done"})
        V = C.verify(o1, "AC-0001")
        check("дела стенд: close sanctioned — closed; verify — целостность (файлов 5, ошибок 0)",
              case("AC-0001")[0] == "closed" and V["cases"][0]["ok"] and "файлов 5, проверено 5, ошибок 0" in V["cases"][0]["lines"][0], V)
        with open(os.path.join(store, "AC-0001", "files", exf[0]), "ab") as f:
            f.write(b"!")
        V2 = C.verify(o1, "AC-0001")
        check("дела стенд: порча файла доказательства — verify находит (sha256 / размер)", not V2["cases"][0]["ok"] and V2["bad"] == ["AC-0001"], V2)
        S = C.show(o1, "AC-0001")
        hist = [x["action"] for x in S["log"]]
        check("дела стенд: show — история (open, attach_event, attach, attach_file, export, report, decide, withdraw, decide, block, appeal, "
              "appeal_resolve, lift, close), события, 5 файлов, блок, источники ac.other + файл; md исходника",
              hist[:4] == ["open", "attach_event", "attach", "attach_file"] and "block" in hist and "appeal_resolve" in hist and hist[-1] == "close"
              and len(S["events"]) == 1 and len(S["evidence"]) == 5 and len(S["blocks"]) == 1 and S["sources"] == ["ac.other", "файл: GS SpeedHack"]
              and S["md"].startswith("# AC-0001 — training case (УЧЕБНОЕ)") and S["service"], hist)
        L = C.case_list(o1, {"account": "7"})
        check("дела стенд: список по учётке — AC-0001 closed, событий 1, файлов 5", len(L["rows"]) == 1 and L["rows"][0]["n_evidence"] == 5
              and L["rows"][0]["status"] == "closed", L)
        # ---- блок не встал: триггер сбрасывает us_block (как гонка со снятием истёкших при входе)
        R(o1, "case.open", {"uid": 8, "title": "no hold"})
        ev8 = ldb(names["J"]).cursor().execute("SELECT event_id FROM ac.other WHERE user_index = 8").fetchone()[0]
        R(o1, "case.attach", {"case": 2, "events": ["other:%d" % ev8]})
        R(o1, "case.attach", {"case": 2, "log": lg, "needles": ["Hero"], "label": "GS SpeedHack"})
        ldb(names["O"]).cursor().execute("CREATE TRIGGER dbo.TR_reset ON dbo.Us_member AFTER UPDATE AS UPDATE m SET us_block = 0 FROM dbo.Us_member m "
                                         "JOIN inserted i ON i.Userindex = m.Userindex WHERE i.us_block = 5 AND i.Userindex = 8")
        w_hold = F(o1, "case.decide", {"case": 2, "step": 3, "text": "t", "confirm": "AC-0002"})
        ldb(names["O"]).cursor().execute("DROP TRIGGER dbo.TR_reset")
        nb = audits("account.block")
        nu = audits("account.block.undo")
        check("дела стенд: блок не встал (us_block ≠ 5 после фиксации) — отказ «блок не встал», блок откатан своим undo (account.block.undo ok), "
              "строки BlockList нет, дело осталось evidence без ступени, case_block нет",
              w_hold and w_hold.startswith("блок не встал") and ub(8)[:2] == (0, 0) and nu and nu[-1][0] == "ok" and nb[-1][2] == "account:8"
              and case("AC-0002")[0] == "evidence" and case("AC-0002")[1] is None
              and ldb(names["J"]).cursor().execute("SELECT COUNT(*) FROM san.case_block WHERE case_id = 2").fetchone()[0] == 0, (w_hold, ub(8), nu))
        # ---- ревизия 59 Н-1: упала запись журнала самой case.decide ПОСЛЕ зафиксированного account.block — блок откатывается undo
        real_write = audit.write

        def bad_write(ctx, action, *a, **k):
            if action == "case.decide" and k.get("result", "ok") == "ok":
                raise RuntimeError("AsdaAdmin недоступна (имитация)")
            return real_write(ctx, action, *a, **k)
        audit.write = bad_write
        try:
            try:
                R(o1, "case.decide", {"case": 2, "step": 3, "text": "t", "confirm": "AC-0002"})
                e_aw = None
            except Exception as ex:
                e_aw = str(ex)
        finally:
            audit.write = real_write
        nb2, nu2 = audits("account.block"), audits("account.block.undo")
        check("дела стенд (ревизия 59 Н-1): запись журнала case.decide упала после account.block — отказ, блок снят undo (account.block.undo ok), "
              "us_block 0, строк BlockList нет, дело осталось evidence", e_aw and "AsdaAdmin" in e_aw and ub(8)[:2] == (0, 0)
              and len(nu2) == len(nu) + 1 and nu2[-1][0] == "ok" and nb2[-1] == ("ok", "owner1", "account:8") and case("AC-0002")[0] == "evidence"
              and case("AC-0002")[1] is None, (e_aw, ub(8), nu2[-2:], case("AC-0002")))
        # ---- ревизия 59 Н-5: блок / снятие, сделанные делом, из журнала действий не откатываются
        ab = ldb(names["A"]).cursor().execute("SELECT TOP 1 id FROM adm.audit WHERE action = 'account.block' AND target = 'account:7' AND result = 'ok' "
                                              "ORDER BY id").fetchone()[0]
        au = ldb(names["A"]).cursor().execute("SELECT TOP 1 id FROM adm.audit WHERE action = 'account.unblock' AND target = 'account:7' AND result = 'ok' "
                                              "ORDER BY id").fetchone()[0]
        w_ub = _refused(lambda: ops.undo(o2, ab))
        w_uu = _refused(lambda: ops.undo(o2, au))
        check("дела стенд (ревизия 59 Н-5): откат из журнала account.block дела — отказ «снимите через дело (case.lift)», account.unblock дела — "
              "отказ «новый блок — решением по делу»; учётка не тронута",
              w_ub == "блок поставлен делом AC-0001 — снимите через дело (case.lift)"
              and w_uu == "блок снят делом AC-0001 — откатом журнала не возвращается, новый блок — решением по делу (case.decide)" and ub(7) == (0, 0, 1),
              (w_ub, w_uu, ub(7)))
        # ---- ревизия 59 Н-2: gm решает ступени 0–2, со ступени 3 — admin / owner (игрок 9001 — синтетика стенда)
        R(adm, "case.open", {"login": "alpha", "title": "manual"})
        ev9 = ldb(names["J"]).cursor().execute("SELECT event_id FROM ac.other WHERE user_index = 9001").fetchone()[0]
        kb9 = ldb(names["J"]).cursor().execute("SELECT event_id FROM ac.kick_block WHERE user_index = 9001").fetchone()[0]
        R(gm, "case.attach", {"case": 3, "events": ["other:%d" % ev9, "kick_block:%d" % kb9]})
        w_ex = F(adm, "case.execute", {"case": 3, "text": "x"})
        w_g3 = F(gm, "case.decide", {"case": 3, "step": 3, "text": "x", "confirm": "AC-0003"})
        R(adm, "case.rollback_report", {"case": 3, "from": "20260101", "to": "20260131"})
        R(adm, "case.decide", {"case": 3, "step": 6, "text": "rollback"})
        w_ge6 = F(gm, "case.execute", {"case": 3, "text": "x"})
        w_gw6 = F(gm, "case.withdraw", {"case": 3, "text": "x"})
        R(adm, "case.withdraw", {"case": 3, "text": "not yet"})
        R(gm, "case.decide", {"case": 3, "step": 2, "text": "kick"})
        st_g2 = case("AC-0003")
        R(gm, "case.withdraw", {"case": 3, "text": "warn instead"})
        R(gm, "case.decide", {"case": 3, "step": 1, "text": "warn"})
        R(gm, "case.execute", {"case": 3, "text": "warned in chat"})
        w_gcl = F(gm, "case.close", {"case": 3, "outcome": "sanctioned", "text": "warned"})
        R(adm, "case.close", {"case": 3, "outcome": "sanctioned", "text": "warned"})
        hi = "решение со ступени 3 — только администратор или владелец (gm — ступени 0–2)"
        check("дела стенд (ревизия 59 Н-2): gm — решение ступени 3 отказ; исполнение и отзыв решения ступени 6 — отказ; ступени 2 и 1 — решает, "
              "отзывает, исполняет сам; закрыть — admin (gm — нет права ac.decide); execute не вынесенного решения — отказ исходника",
              w_g3 == hi and w_ge6 == hi and w_gw6 == hi and st_g2[0] == "decision" and st_g2[1] == 2 and st_g2[3] == "gm3"
              and w_gcl == "нет права «ac.decide»" and case("AC-0003")[0] == "closed" and case("AC-0003")[3] == "gm3"
              and w_ex and "исполнить можно только вынесенное решение" in w_ex and ub(9001) == (0, 0, 0), (w_g3, w_ge6, w_gw6, st_g2, w_gcl, case("AC-0003")))
        # ---- ревизия 59 Н-4: одна и та же выдержка с другой меткой — не второй источник; М-1: предпросмотр бюджет не списывает
        R(adm, "case.open", {"login": "alpha", "title": "labels"})
        R(adm, "case.attach", {"case": 4, "log": lg, "needles": ["Hero"], "label": "label A"})
        R(adm, "case.attach", {"case": 4, "log": lg, "needles": ["Hero"], "label": "label B"})
        w_lab = F(adm, "case.decide", {"case": 4, "step": 3, "text": "t", "confirm": "AC-0004"})
        h0 = len(C._heavy.get("admin2", []))
        R(adm, "case.attach", {"case": 4, "from": "20260101", "to": "20260131"}, True)
        h1 = len(C._heavy.get("admin2", []))
        check("дела стенд (ревизия 59 Н-4, М-1): две выдержки ОДНОГО журнала с разными метками — один источник (решение ступени 3 — отказ, "
              "есть: файл: label A); предпросмотр окна событий не списывает тяжёлое действие",
              w_lab == "ступень 3 требует доказательств из двух независимых источников, есть: файл: label A" and h1 == h0, (w_lab, h0, h1))
        # ---- на ПК без хранилища запись — отказ; журнал на каждое действие
        C.STORE_OVERRIDE = None
        w_pc = F(o1, "case.open", {"uid": 8, "title": "x"})
        C.STORE_OVERRIDE = store
        acts = {r[0] for r in ldb(names["A"]).cursor().execute("SELECT DISTINCT action FROM adm.audit").fetchall()}
        check("дела стенд: без хранилища (ПК) — понятный отказ; журнал adm.audit — запись на каждое действие case.* (и account.block / unblock / undo)",
              w_pc == C.STORE_PC and {"case.open", "case.attach", "case.export", "case.rollback_report", "case.decide", "case.withdraw", "case.appeal",
                                       "case.lift", "case.close", "case.execute", "account.block", "account.unblock", "account.block.undo"} <= acts, (w_pc, acts))
        # ---- API
        from api import server as _srv
        fs, _p = _route("/api/cases/show")

        class _Req:
            def __init__(self, q, role):
                self.query, self.session, self.client_ip = q, {"user": {"role": role, "login": "t", "id": None}}, ""
        api = fs(_Req({"case": "AC-0001"}, "gm"), None)
        try:
            fs(_Req({"case": "AC-9"}, "gm"), None)
            code = None
        except _srv.HttpError as ex:
            code = ex.code
        check("дела API: gm видит дело (ac.view), нет дела — 409 с понятным текстом", api["case"]["case_no"] == "AC-0001" and code == 409, code)
        nlog = ldb(names["J"]).cursor().execute("SELECT COUNT(*) FROM san.case_log").fetchone()[0]
        w_del = None
        try:
            c2 = ops_cn("joylog1")
            c2.cursor().execute("DELETE FROM san.case_log")
        except Exception as ex:
            w_del = str(ex)
        finally:
            c2.close()
        check("дела стенд: удалить историю под asda_ops нельзя (нет права DELETE)", w_del and "DELETE" in w_del.upper()
              and ldb(names["J"]).cursor().execute("SELECT COUNT(*) FROM san.case_log").fetchone()[0] == nlog, w_del)
    finally:
        db.set_override("game", None)
        db.set_override("ops", None)
        db.set_override("admin", None)
        C.STORE_OVERRIDE, C.XLAT, LG.IO, LG.procs_of = saved
        shutil.rmtree(store, ignore_errors=True)
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
    from domains import cases as C
    if config.get().on_server:
        return check("живой самотест А6.7 — с ПК", True)
    own = _ctx("selftest", "owner")
    with db.GameReader("joylog1") as lg:
        n = lg.one("SELECT COUNT(*) AS n FROM san.cases")["n"]
        ev = lg.rows("SELECT rel_path, size_bytes, sha256 FROM san.evidence WHERE case_id = 1 ORDER BY evidence_id")
        pr = lg.one("SELECT HAS_PERMS_BY_NAME('san.cases','OBJECT','SELECT') AS s, HAS_PERMS_BY_NAME('san.cases','OBJECT','UPDATE') AS u, "
                    "HAS_PERMS_BY_NAME('san.UP_SAN_SetStatus','OBJECT','EXECUTE') AS e")
    L = C.case_list(own, {})
    check("живое: список дел = COUNT(*) san.cases (%d), asda_admin — чтение san да, записи и EXEC нет" % n, len(L["rows"]) == n
          and (pr["s"], pr["u"], pr["e"]) == (1, 0, 0), (len(L["rows"]), n, pr))
    S = C.show(own, "AC-0001")
    check("живое: AC-0001 — учебное, closed, учётка 1 (служебная), файлов %d, событий %d, источники ≥ 2" % (len(S["evidence"]), len(S["events"])),
          S["case"]["case_no"] == "AC-0001" and S["case"]["is_training"] and S["case"]["status"] == "closed" and S["service"]
          and len(S["evidence"]) == len(ev) and len(S["sources"]) >= 2, S["case"])
    want = json.dumps([[r["rel_path"], r["size_bytes"], r["sha256"]] for r in ev])
    probe = ("import sys, json, hashlib, os\nsys.path.insert(0, '.')\nfrom core import ops\nfrom domains import cases as C\n"
             "c = ops.Ctx(None, 'selftest', 'owner', '', 'test')\nV = C.verify(c, 'AC-0001')\nm, cfg, src = C.source()\n"
             "d = os.path.join(C.CASES_ROOT, 'AC-0001')\nw = json.loads(%r)\n"
             "same = all(hashlib.sha256(open(os.path.join(d, *r[0].split('/')), 'rb').read()).hexdigest() == r[2] for r in w)\n"
             "print('CSPROBE ok=%%s bad=%%d where=%%s md5=%%s same=%%s' %% (V['cases'][0]['ok'], len(V['bad']), src['where'], src['code_md5'], same))\n" % want)
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    try:
        p = subprocess.run([exe if os.path.exists(exe) else "ssh", "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                            r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                            r'@@ASTORY_SERVER_PYTHON@@ -"'],
                           input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (p.stdout + p.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"CSPROBE ok=(\w+) bad=(\d+) where=(\w+) md5=(\w+) same=(\w+)", out)
    m, _cfg, src = C.source()
    check("служба на сервере (SSH): AC-0001 в каталоге службы — verify без ошибок, sha256 всех файлов = реестру san.evidence; код дел из ext/ с md5 исходника ПК",
          bool(mm) and mm.group(1) == "True" and mm.group(2) == "0" and mm.group(3) == "ext" and mm.group(4) == src["code_md5"] and mm.group(5) == "True",
          out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/cases/list" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/cases/list без входа — 401", code == 401, code)
