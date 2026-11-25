# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_telegram_a7.py — самотест шага А7.5 «Telegram владельцу» (23.11.2026; решение владельца А7 №3 — только владельцу, через @@@ASTORY_TELEGRAM_BOT@@,
только отправка, с ПК; domains/notify.py, sql/adminc_29_telegram.sql и adminc_29_telegram_verify.sql, /api/telegram, web/telegram.js, core/sched.py;
отправитель — AstoryAdminCenter/DiscordBot/tg_bot.py и test_tg_bot.py, цикл tg_loop в oracle_bot.py).

НИ ОДИН ПРОГОН НЕ ВЫЗЫВАЕТ TELEGRAM: офлайн и стенд — отправитель с подставным HTTP (запоминает запросы, сети нет); живой — только проверочная
запись вида selftest (отправитель её отмечает «тест» без Telegram) и захват только проверочных (@test_only = 1). Апдейты бота никто не читает.

offline(check)  — права (notify.view / notify.manage — только owner), операции без отката, маршрут, список событий = CHECK базы, тихие часы и
                  порог «служба не отвечает» панели = отправителя, нет события флагов суточного отчёта античита (решение А6 №9), отправитель знает
                  только sendMessage и getMe, токена нет в коде и в панели, тексты без «; », переводы EN, веб (без innerHTML, данные — acText),
                  adminc_29 (уровень 100, права), adminc_28 и экран Discord фильтруют transport, проверка под asda_reports, adminc_10 / 99, выкладка,
                  поток sched, импорт без побочных эффектов, модульные тесты отправителя.
sandbox(check, ldb) — СВОЯ база LocalDB: adminc_02 + 14 + 23 + 27 + 28 + 29 (29 дважды): общий выключатель по умолчанию выключен (ничего не
                  ставится), включение — только owner, события из подставных источников (EacServer, стойка, журнал, задания, квота, подпись,
                  падения, жалобы), склейка, пауза, предел частоты, выключатель события, разделение очередей Discord и Telegram; отправитель —
                  НАСТОЯЩИЙ tg_bot.Store под EXECUTE AS USER asda_reports и Worker с подставным HTTP: отправка один раз, без звука ночью, getMe у
                  проверки, проверочное сообщение, «служба не отвечает»; права asda_reports; экран; журнал adm.audit.
live(check)     — живая dev: права asda_admin, путь отправителя (asda_reports по VPN = adminc_29_telegram_verify), экран читается, проверочная запись
                  selftest → захват только проверочных → «тест» (Telegram не вызывается), отметка службы свежая, служба на сервере (SSH) видит
                  запись, без входа — 401. Общий выключатель живой самотест не трогает.
Побочных эффектов при импорте нет.
"""
import ast
import asyncio
import datetime
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
BOT = os.path.join(PORT, "AstoryAdminCenter", "DiscordBot")
CYR = re.compile("[А-Яа-яЁё]")
TOKEN_RX = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")
FORBIDDEN_METHODS = ("get" + "Updates", "set" + "Webhook", "delete" + "Webhook", "getWebhook" + "Info", "log" + "Out", "set" + "MyCommands")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def _paths():
    for p in (ROOT, BOT):
        if p not in sys.path:
            sys.path.insert(0, p)


def _refused(fn):
    from core.ops import OpRefused
    try:
        fn()
    except OpRefused as ex:
        return str(ex)
    return None


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _route(path):
    from api import server
    for meth, rx, fn, perm, _full in server.ROUTES:
        if meth == "GET" and rx.match(path):
            return fn, perm
    return None, None


def _in_list(sql, rx):
    m = re.search(rx, sql, re.S)
    return set(re.findall(r"'([a-z_]+)'", m.group(1))) if m else None


def offline(check):
    _paths()
    from core import auth, i18n, ops
    import domains
    domains.load_all()
    from domains import notify as N
    import tg_bot as G
    roles = ("owner", "admin", "gm", "support")
    who = lambda p: {r for r in roles if auth.can(r, p)}
    check("Telegram: права notify.view и notify.manage — только owner (личный канал владельца, решение А7 №3)",
          who("notify.view") == who("notify.manage") == {"owner"})
    reg = ops.REGISTRY
    check("Telegram: операции notify.rule.set, telegram.test, telegram.ping — под notify.manage, без отката",
          all(reg[n].perm == "notify.manage" and not reg[n].reversible for n in ("notify.rule.set", "telegram.test", "telegram.ping")))
    fn, perm = _route("/api/telegram")
    check("Telegram: маршрут GET /api/telegram — право notify.view", fn is not None and perm == "notify.view")
    sql = _read(ROOT, "sql", "adminc_29_telegram.sql")
    svc = set(N.SERVICE_EVENTS)
    route = _in_list(sql, r"CK_adm_Outbox_route CHECK.*?event_key IN \(([^)]*)\)")
    rule = _in_list(sql, r"CK_adm_NotifyRule_key CHECK \(event_key IN \(([^)]*)\)\)")
    put = _in_list(sql, r"CREATE PROCEDURE adm\.TgNotifyPut.*?NOT IN \(([^)]*)\)")
    sset = _in_list(sql, r"CREATE PROCEDURE adm\.TgStateSet.*?NOT IN \(([^)]*)\)")
    check("события: список панели (RULES, 10) = CHECK выключателей (+ _master) = CHECK строки очереди и adm.TgNotifyPut (события службы, 9) = "
          "adm.TgStateSet (+ _cursor); «служба не отвечает» ищет ПК",
          len(N.RULES) == 10 and rule == set(N.EVENTS) | {"_master"} and route == put == svc and sset == svc | {"_cursor"}
          and N.RULE["panel_down"]["where"] == "pc" and len(svc) == 9, (route, rule, put, sset))
    check("решение А6 №9: флагов суточного отчёта античита в Telegram нет — ни события, ни чтения adm.AcDaily / domains.acdaily",
          not [k for k in N.EVENTS if "ac" in k.split("_")] and "acdaily" not in _read(ROOT, "domains", "notify.py").lower()
          and "AcDaily" not in _read(ROOT, "domains", "notify.py"))
    check("панель = отправитель: тихие часы %d:00–%d:00, порог «служба не отвечает» %d мин" % (N.QUIET_FROM, N.QUIET_TO, N.PANEL_STALE_MIN),
          (N.QUIET_FROM, N.QUIET_TO) == G.QUIET and N.PANEL_STALE_MIN == G.PANEL_STALE_MIN)
    check("каждое событие: подпись, зачем, срочность (urgent / normal / low), пауза и напоминание — числа в коде (не в ini)",
          all(r["title"] and len(r["why"]) > 40 and r["prio"] in ("urgent", "normal", "low") and isinstance(r["gap"], int) and isinstance(r["remind"], int)
              for r in N.RULES))
    src = _read(BOT, "tg_bot.py")
    bad = [w for w in FORBIDDEN_METHODS if w in src]
    calls = set(re.findall(r'self\.call\("(\w+)"', src))
    check("отправитель: в коде ТОЛЬКО sendMessage и getMe (METHODS, вызовы self.call), нет методов чтения апдейтов, вебхука и настроек бота; чат — "
          "только личный (положительный номер)", G.METHODS == ("sendMessage", "getMe") and calls == {"sendMessage", "getMe"} and not bad
          and "self.chat <= 0" in src, (calls, bad))
    tree_files = []
    for base in (os.path.join(ROOT, "domains"), os.path.join(ROOT, "core"), os.path.join(ROOT, "api"), os.path.join(ROOT, "web"), os.path.join(ROOT, "sql")):
        for f in os.listdir(base):
            if f.endswith((".py", ".js", ".sql", ".html")):
                tree_files.append(os.path.join(base, f))
    tok_hits = [f for f in tree_files + [os.path.join(BOT, "tg_bot.py"), os.path.join(BOT, "test_tg_bot.py"), os.path.join(BOT, "oracle_bot.py")]
                if TOKEN_RX.search(_read(f).replace("123456789:" + "A" * 35, ""))]
    tg_api = [os.path.basename(f) for f in tree_files if "api.telegram.org" in _read(f)]
    check("токена бота нет ни в коде панели (domains, core, api, web, sql), ни в коде отправителя; панель Telegram не вызывает (api.telegram.org — "
          "только у отправителя на ПК); telegram.env в пакет панели не входит",
          not tok_hits and not tg_api and "api.telegram.org" in src
          and not os.path.exists(os.path.join(ROOT, "telegram.env")), (tok_hits, tg_api))
    # ---- тексты
    from domains import reports as R
    texts = ([r["title"] for r in N.RULES] + [r["why"] for r in N.RULES] + list(N.TEST_CODES.values()) + [N.NOT_INSTALLED] +
             [reg[n].title for n in ("notify.rule.set", "telegram.test", "telegram.ping")] +
             ["Telegram: база панели не прочитана: AsdaAdmin: x",
              "общий выключатель Telegram выключен — служба уведомлений не ставит (проверка и проверочное сообщение работают)",
              "служба панели не отмечалась дольше 15 мин — поиск событий не идёт",
              "отправитель на ПК (бот Oracle) не отмечался дольше 10 мин — запущен ли бот и есть ли telegram.env рядом с ним",
              "запись Telegram №5 ждёт отправителя дольше 5 мин", "запись Telegram №5: отправитель взял её и не отчитался дольше 10 мин",
              "событие не из списка (можно: _master, stack)", "enabled — true или false", "выключатель Telegram уже включён", "выключатель Telegram уже выключен",
              "включить общий выключатель Telegram", "выключить уведомление «стойка не поднялась»", "общий выключатель Telegram выключен",
              "уведомление «EacServer не работает» включено", "пишется только база панели AsdaAdmin (adm.NotifyRule)",
              "после включения служба начнёт ставить уведомления о событиях, отправитель на ПК — слать их в чат владельца (sendMessage)",
              "поставить проверочную запись Telegram — отправитель на ПК вызовет только getMe (жив ли токен и прокси), сообщения в чат не будет",
              "поставить проверочную запись Telegram — отправитель на ПК только отметит «тест», Telegram не вызывается, сообщения в чат не будет",
              "проверочная запись Telegram №5 поставлена", "проверочное сообщение Telegram №5 поставлено отправителю", "проверка Telegram: вид check или selftest",
              "отправить в Telegram владельцу проверочное сообщение «Astory: проверочное сообщение админ-центра — уведомления владельцу доходят.»",
              "это настоящая отправка: сообщение придёт в чат владельца от @@@ASTORY_TELEGRAM_BOT@@ в течение 30 с, если бот Oracle на ПК запущен",
              "отката нет — сообщение остаётся в чате",
              "просрочено: отправитель на ПК не забрал запись до срока годности", "getMe не прошёл: нет связи с Telegram (ConnectionRefusedError)",
              "getMe: @@@ASTORY_TELEGRAM_BOT@@ — токен и связь в порядке, сообщение не отправлялось", "проверочная запись — Telegram не вызывался",
              "итог неизвестен: отправка прервалась — проверьте чат, повторно эта запись не отправляется",
              "итог неизвестен: журнал отправителя не знает эту запись, а попыток уже 2 — повторно она не отправляется",
              "просрочено: срок годности прошёл до отправки", "тайм-аут ответа Telegram — итог неизвестен — проверьте чат, повторно эта запись не отправляется",
              "обрыв связи с Telegram (ConnectionResetError) — итог неизвестен — проверьте чат, повторно эта запись не отправляется",
              "Telegram HTTP 400: Bad Request: chat not found", "Telegram отказал: Forbidden", "метод Telegram x запрещён отправителю",
              "ответ Telegram оборван (IncompleteRead) — итог неизвестен — проверьте чат, повторно эта запись не отправляется",
              "сообщение ПК: служба панели не отвечает", "сообщение ПК: служба снова отмечается", "сообщение ПК: база не отвечает",
              "сообщение ПК: база снова отвечает",
              "ответ Telegram не JSON — итог неизвестен — проверьте чат, повторно эта запись не отправляется", "нет связи с Telegram (URLError)"])
    check("Telegram: тексты событий, отказов, предупреждений и итогов отправителя без «; »", all("; " not in t for t in texts), [t for t in texts if "; " in t])
    texts = texts[2 * len(N.RULES):]                  # подписи и «зачем» событий переводит интерфейс (web/i18n.js — проверка ниже)
    i18n.set_lang("en")
    try:
        miss = [(t, i18n.tr(t)) for t in texts if CYR.search(i18n.tr(t))]
    finally:
        i18n.set_lang("ru")
    check("Telegram EN: события, отказы, предупреждения и итоги отправителя — без русских слов (%d строк)" % len(texts), not miss, miss[:6])
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("Telegram: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "telegram.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("веб: раздел #/telegram с правом notify.view, viewTelegram(my), скрипт после outbox.js; без innerHTML, данные записей (текст, ошибка, заголовок "
          "записи) — acText, не T(); кнопки и выключатели — только с notify.manage",
          '["#/telegram", "Telegram владельцу", "notify.view"' in app and 'case "telegram": return viewTelegram(my);' in app
          and 0 < idx.index("/outbox.js") < idx.index("/telegram.js") and "innerHTML" not in js
          and "T(x.text" not in js and "T(x.error" not in js and "acText(x.title)" in js and 'testBtn.style.display = can ? "" : "none"' in js
          and "return can ? h(\"button\"" in js)
    q = re.compile(r'"((?:[^"\\]|\\.)*)"')
    labels = {x for x in q.findall(js) if CYR.search(x)} | {"Telegram владельцу"} | {r["title"] for r in N.RULES} | {r["why"] for r in N.RULES}
    have = set(re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(labels - have)
    check("веб EN: у русских строк раздела и у подписей событий есть перевод в web/i18n.js (%d строк)" % len(labels), not lack, lack[:8])
    keys_all = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А7.5 (23.11): «Telegram владельцу»"):]
    dup = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys_all.count(x) > 1})
    check("веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("telegram.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("Telegram: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("Telegram: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- SQL, права, выкладка
    bs = _batches(sql)
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    body = re.sub(r"--[^\n]*", "", body)
    g_rep = sorted(re.findall(r"GRANT EXECUTE ON (adm\.\w+)\s+TO \[asda_reports\]", body))
    g_adm = sorted(re.findall(r"GRANT (\w+) ON (adm\.\w+)\s+TO \[asda_admin\]", body))
    check("adminc_29: QUOTED_IDENTIFIER ON отдельным батчем до CREATE, уровень 100 (нет THROW, IIF, CONCAT, TRY_CONVERT, FORMAT, STRING_SPLIT, CREATE OR "
          "ALTER, DROP … IF EXISTS), отправитель asda_reports — EXECUTE трёх процедур и DENY таблиц и процедур панели; asda_admin — SELECT трёх таблиц и "
          "пять процедур, DENY прямой записи и процедур отправителя; общий выключатель без строки — ВЫКЛ",
          bs[0].strip().endswith("SET QUOTED_IDENTIFIER ON;") and "CREATE TABLE" not in bs[0]
          and not re.search(r"\b(TRY_CONVERT|TRY_CAST|IIF|FORMAT|THROW|STRING_SPLIT|ISJSON|OPENJSON|CONCAT|STRING_AGG)\b|CREATE OR ALTER|DROP \w+ IF EXISTS", body)
          and g_rep == ["adm.TgBeatGet", "adm.TgClaim", "adm.TgDone", "adm.TgLocalNote"]
          and g_adm == sorted([("SELECT", "adm.Notify" + t) for t in ("Rule", "State", "Beat")]
                              + [("EXECUTE", "adm.Tg" + p) for p in ("RuleSet", "NotifyPut", "StateSet", "BeatSet", "TestPut")])
          and all("DENY  SELECT, INSERT, UPDATE, DELETE ON adm.Notify%s TO [asda_reports]" % t in body for t in ("Rule ", "State", "Beat "))
          and all("DENY  EXECUTE ON adm.Tg%s TO [asda_admin]" % p in body for p in ("Claim    ", "Done     ", "BeatGet  "))
          and "IF NOT EXISTS (SELECT 1 FROM adm.NotifyRule WHERE event_key = '_master' AND enabled = 1)" in body, (g_rep, g_adm))
    code = _read(ROOT, "domains", "notify.py")
    ver = _read(ROOT, "sql", "adminc_29_telegram_verify.sql")
    check("adminc_29_telegram_verify: 17 проверок ПОД asda_reports (4 процедуры отправителя — 1, остальное — 0)",
          ver.count("UNION ALL SELECT") + 1 == 17 and len(re.findall(r",\s*1(?: AS want)?;?\s*$", ver, re.M)) == 4)
    # ---- ★ ревизия 77
    rs = _read(PORT, "AstoryServer", "Patches", "AsdaPatch", "tools", "restart_stack.py")
    rl = rs[rs.index("def run_locked():"):]
    check("р77 В-2: restart_stack.py ставит отметку «идёт управление стойкой» на сервере (тот же файл, что читает служба) — до main() на 45 мин, "
          "после — на 15 мин (после --stop-only с кодом 0 — «stopped» на 12 ч); сбой записи — только предупреждение; --help отметку не ставит",
          'ACTIVITY_FILE = r"%s"' % N.STACK_ACTIVITY_FILE in rs and "ACTIVITY_RUN_MIN, ACTIVITY_DONE_MIN, ACTIVITY_STOP_MIN = 45, 15, 720" in rs
          and rl.index("    try:") < rl.index('mark_activity("run", ACTIVITY_RUN_MIN)') < rl.index("rc = main()") < rl.index('mark_activity("done", ACTIVITY_DONE_MIN, rc)')
          and 'mark_activity("stopped", ACTIVITY_STOP_MIN, rc)' in rl and rl.index('"--help" in sys.argv') < rl.index("mark_activity(")
          and "return False" in rs[rs.index("def mark_activity"):rs.index("def read_activity")])
    urg = _in_list(sql, r"@urgent BIT = CASE WHEN @event IN \(([^)]*)\)")
    check("р77 В-1: срочные события (stack, eac_down, backup_failed) — вне общего предела и не тратят его, у каждого свой (%d в час): список "
          "панели = процедуры" % N.URGENT_PER_HOUR, urg == set(N.URGENT_EVENTS) and ") >= 6" in sql and N.URGENT_PER_HOUR == 6
          and "event_key NOT IN ('stack', 'eac_down', 'backup_failed')" in sql, urg)
    check("р77 К-1: ссылки, @имена, #теги и /команды в хвосте сообщения разорваны невидимым пробелом (Telegram не делает их ссылками)",
          "://" not in N.clean("see https://evil.example/x") and "www." not in N.clean("www.x.com") and "@bob" not in N.clean("@bob hi")
          and "#tag" not in N.clean("#tag") and "/start" not in N.clean("/start"))
    jb = code[code.index("def _jobs(S):"):code.index("def _stack_busy(S")]
    check("р77 К-4: в уведомлении о задании нет хвоста итога (там может быть имя персонажа) — только номер, операция и итог", '"result"' not in jb
          and "r[\"result\"]" not in jb)
    sc = object.__new__(N.Scan)
    sc.now = datetime.datetime(2026, 11, 24, 7, 30)               # UTC; местное = UTC+3

    class _L:
        def __init__(self, h):
            self.h = h

        def local_now(self):
            return datetime.datetime(2026, 11, 24, self.h, 30)
    sc.state = {("release_sign", "alpha"): {"last_put_utc": datetime.datetime(2026, 11, 23, 0, 0)}}
    sc.src = _L(10)
    d10 = sc.due_daily("release_sign", "alpha")
    sc.src = _L(9)
    sc.now = datetime.datetime(2026, 11, 24, 6, 30)
    d9 = sc.due_daily("release_sign", "alpha")
    sc.src, sc.now = _L(10), datetime.datetime(2026, 11, 24, 7, 30)
    sc.state = {("release_sign", "alpha"): {"last_put_utc": datetime.datetime(2026, 11, 24, 7, 1)}}
    d_after = sc.due_daily("release_sign", "alpha")
    check("р77 К-2: напоминание подписи и LogDrop — в 10:00 по местным часам (в 09:30 — нет, в 10:30 — да, уже напомнили после 10:00 — нет)",
          d10 and not d9 and not d_after, (d10, d9, d_after))
    # ★ р78: restart_stack.run_locked на подменах (SSH, замок, main) — первая отметка внутри try, коды 1 и 7 возвращают прежнюю отметку
    import importlib.util
    spec = importlib.util.spec_from_file_location("rs_a75test", os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "tools", "restart_stack.py"))
    saved_argv = sys.argv
    res = {}
    try:
        for argv, rc_main, prev in ((["x"], 7, "phase=stopped until=20261124T120000Z at=20261124T000000Z code=0 pid=5"), (["x", "--stop-only"], 0, ""),
                                    (["x"], 0, ""), (["x"], 1, ""), (["x"], "boom", "")):
            sys.argv = ["restart_stack.py"]
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            sys.argv = argv
            calls = []
            m.ssh_ps = lambda c, timeout=180, _p=prev: (calls.append(c) or (0, (_p + "\r\n") if c.startswith("if (Test-Path") else ""))
            m.acquire_lock = lambda *a, **k: (True, None)
            m.release_lock = lambda *a, **k: calls.append("release")

            def _main(rc=rc_main):
                if rc == "boom":
                    raise KeyboardInterrupt()
                return rc
            m.main = _main
            try:
                rc = m.run_locked()
            except KeyboardInterrupt:
                rc = "kbd"
            res[(tuple(argv), str(rc_main))] = (rc, [c[:400] for c in calls])
    finally:
        sys.argv = saved_argv
    r7 = res[(("x",), "7")][1]
    rs0 = res[(("x", "--stop-only"), "0")][1]
    r0 = res[(("x",), "0")][1]
    r1 = res[(("x",), "1")][1]
    rk = res[(("x",), "boom")]
    check("р78 К-1 / К-2: restart_stack.run_locked — отметка «run» внутри try, код 7 возвращает прежнюю «stopped» как была, код 1 без прежней — «run» "
          "сразу истекает (0 мин), --stop-only с кодом 0 — «stopped», обычный — «done», Ctrl+C — «done» и снятый замок",
          "phase=run" in r7[1] and "phase=stopped until=20261124T120000Z" in r7[2] and r7[-1] == "release"
          and any("phase=stopped" in c and "AddMinutes(720)" in c for c in rs0) and any("phase=done" in c and "AddMinutes(15)" in c for c in r0)
          and any("phase=done" in c and "AddMinutes(0)" in c for c in r1) and rk[0] == "kbd" and any("phase=done" in c for c in rk[1])
          and rk[1][-1] == "release", res)
    s28 = _read(ROOT, "sql", "adminc_28_outbox.sql")
    procs28 = re.findall(r"CREATE PROCEDURE (adm\.\w+)(.*?)\nEND", s28, re.S)
    nof = [n for n, b in procs28 if "transport = 'discord'" not in b]
    ob = _read(ROOT, "domains", "outbox.py")
    check("разделение очередей: все 9 процедур adminc_28 работают только со строками transport = 'discord', экран и пределы Discord (domains/outbox.py) — тоже",
          len(procs28) == 9 and not nof and "_DISCORD = \"WHERE transport = 'discord' \"" in ob
          and "WHERE transport = 'discord' AND is_test = ?" in ob and "AND transport = 'discord'\" % (_COLS" in ob, nof)
    v10, v99 = _read(ROOT, "sql", "adminc_10_verify.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    check("выкладка: adminc_29 -x -I в AsdaAdmin после adminc_28 и до adminc_10, проверка ПОД asda_reports (adminc_29_telegram_verify, 16); adminc_10 — "
          "SELECT / процедуры панели = 1, запись и процедуры отправителя = 0; adminc_99 — откат шага",
          "Run 'adminc_29_telegram.sql' 'AsdaAdmin' -xi" in dep and dep.index("Run 'adminc_28_outbox.sql'") < dep.index("Run 'adminc_29_telegram.sql'")
          < dep.index("adminc_10_verify.sql') 2>&1") and "'sql\\adminc_29_telegram_verify.sql'" in dep and '("asda_reports/telegram", part_tg, 17)' in dep
          and "\x07" not in dep
          and "'adm.NotifyRule SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotifyRule','OBJECT','SELECT'), 1" in v10
          and "'adm.TgClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgClaim','OBJECT','EXECUTE'), 0" in v10
          and "'adm.TgTestPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.TgTestPut','OBJECT','EXECUTE'), 1" in v10 and (v99 is None or "adminc_29_telegram.sql" in v99))
    sch = _read(ROOT, "core", "sched.py")
    check("поток задач службы: notify.scan_due в обычном потоке sched (не в долгом), сбой обёрнут", "notify.scan_due()" in sch.split("def loop_long")[0]
          and sch.index("notify.scan_due()") > sch.index("jobs_once(long=False)"))
    ok_top = True
    for s in (_read(ROOT, "domains", "notify.py"), src):
        tree = ast.parse(s)
        ok_top &= {type(n).__name__ for n in tree.body} <= {"Expr", "Import", "ImportFrom", "Assign", "FunctionDef", "AsyncFunctionDef", "ClassDef"}
    code = _read(ROOT, "domains", "notify.py")
    code = _read(ROOT, "domains", "notify.py")
    check("импорт domains/notify и tg_bot без побочных эффектов (верхний уровень — импорты, константы, функции, классы); панель пишет только процедурами",
          ok_top and not re.findall(r"\b(INSERT|UPDATE|DELETE)\s+adm\.(Outbox|Notify\w+)", code) and "EXEC adm.TgNotifyPut" in code)
    t = [0.0]
    calls_n = []
    N._next[0] = 0.0
    r1 = N.scan_due(mono=1000.0, runner=lambda: calls_n.append(1) or {"results": [], "errors": []})
    r2 = N.scan_due(mono=1000.0 + N.SCAN_S - 1, runner=lambda: calls_n.append(1) or {"results": [], "errors": []})
    r3 = N.scan_due(mono=1000.0 + N.SCAN_S, runner=lambda: calls_n.append(1) or {"results": [], "errors": []})
    N._next[0] = 0.0
    check("scan_due: проход не чаще раза в %d с" % N.SCAN_S, r1 is not None and r2 is None and r3 is not None and len(calls_n) == 2)
    check("clean(): адреса IP и почта в хвосте сообщения маскируются, перевод строки — пробел, длина ограничена",
          N.clean("ошибка 10.0.0.5 у a.b@c.de\nдальше") == "ошибка x.x.x.x у …@… дальше" and len(N.clean("x" * 500)) == N.ERR_MAX)
    py = sys.executable
    try:
        r = subprocess.run([py, "-I", os.path.join(BOT, "test_tg_bot.py")], capture_output=True, timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        n = re.search(r"Ran (\d+) tests", out)
        check("отправитель: модульные тесты test_tg_bot.py (%s тестов) — Telegram подменён, сети нет" % (n.group(1) if n else "?"),
              r.returncode == 0 and n and "OK" in out, out[-400:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("отправитель: модульные тесты (не запустились)", False, str(ex))


class _Http:
    """Подставной Bot API для стенда: запоминает запросы, ничего не отправляет."""

    def __init__(self):
        self.reqs, self.mid = [], 900

    def open(self, req, timeout=None):
        import io

        class _R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()
        method = req.full_url.rsplit("/", 1)[1]
        self.reqs.append((method, json.loads(req.data.decode("utf-8"))))
        if method == "getMe":
            return _R(json.dumps({"ok": True, "result": {"is_bot": True, "username": "@@ASTORY_TELEGRAM_BOT@@"}}).encode())
        self.mid += 1
        return _R(json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode())


def _snap(eac=True, gs=True):
    from domains import status
    st = []
    for key, title, path, ports in status.STACK:
        run = (eac if key == "eac" else gs if key == "gs" else True)
        st.append({"key": key, "title": title, "running": run, "ports": ports, "listening": ports if run else [], "ports_ok": run})
    return {"host_error": "", "stack": st}


def sandbox(check, ldb):
    """Своя база LocalDB: панель (поиск событий, операции) → отправитель (настоящий tg_bot.Store под asda_reports, Worker с подставным HTTP)."""
    _paths()
    from core import audit, db, ops, sched
    import domains
    domains.load_all()
    from domains import notify as N
    import outbox_bot as B
    import tg_bot as G
    name = "AsdaTg_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    tmp = tempfile.TemporaryDirectory()
    try:
        a = ldb(name)
        s23 = _read(ROOT, "sql", "adminc_23_reports.sql").replace("$(ReportsPw)", "Aa1-" + secrets.token_hex(12))
        s29 = _read(ROOT, "sql", "adminc_29_telegram.sql")
        for f in ("adminc_02_schema.sql", "adminc_14_jobs.sql"):
            for b in _batches(_read(ROOT, "sql", f)):
                a.cursor().execute(b)
        for b in _batches(s23) + _batches(_read(ROOT, "sql", "adminc_27_crashes.sql")) + _batches(_read(ROOT, "sql", "adminc_28_outbox.sql")) \
                + _batches(s29) + _batches(s29):
            a.cursor().execute(b)
        q1 = lambda sql, *p: a.cursor().execute(sql, *p).fetchone()
        check("стенд: настоящие adminc_02 + 14 + 23 + 27 + 28 + 29 (29 дважды — повтор безопасен): 9 процедур adm.Tg*, ограничение CK_adm_Outbox_route "
              "вместо трёх прежних, столбцы Telegram",
              q1("SELECT COUNT(*) FROM sys.procedures WHERE name LIKE 'Tg%'")[0] == 9 and q1("SELECT COUNT(*) FROM sys.check_constraints WHERE name = 'CK_adm_Outbox_route'")[0] == 1
              and q1("SELECT COUNT(*) FROM sys.check_constraints WHERE name IN ('CK_adm_Outbox_kind', 'CK_adm_Outbox_transport', 'CK_adm_Outbox_channel')")[0] == 0
              and q1("SELECT COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('adm.Outbox') AND name IN ('event_key', 'dedup_key', 'repeats', 'quiet', 'tg_message_id')")[0] == 5)
        db.set_override("admin", lambda database: ldb(name))

        class _AsBot:
            def __init__(self):
                self.c = ldb(name)
                self.c.cursor().execute("EXECUTE AS USER = 'asda_reports'")

            def cursor(self):
                return self.c.cursor()

            def close(self):
                try:
                    self.c.cursor().execute("REVERT")
                finally:
                    self.c.close()
        cb = _AsBot()
        deny = []
        for qq in ("SELECT COUNT(*) FROM adm.NotifyRule", "SELECT COUNT(*) FROM adm.Outbox", "EXEC adm.TgRuleSet '_master', 1, N'x'",
                   "DECLARE @i INT, @c INT; EXEC adm.TgTestPut 'ping', N'x', @i OUTPUT, @c OUTPUT", "UPDATE adm.NotifyBeat SET host = N'x'",
                   "EXEC adm.TgStateSet 'stack', N'x', 1, NULL"):
            try:
                cur = cb.cursor().execute(qq)
                if qq.startswith("SELECT"):
                    cur.fetchall()
                deny.append(qq[:40])
            except Exception:
                pass
        cb.close()
        check("стенд: asda_reports — ни чтения выключателей и очереди, ни процедур панели (включить, поставить проверку, память), только процедуры отправителя",
              not deny, deny)
        own, adm = ops.Ctx(None, "own_t", "owner", "", "web"), ops.Ctx(None, "adm_t", "admin", "", "web")
        cnt_tg = lambda: q1("SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'notify'")[0]

        class Src(N.Sources):
            def __init__(self):
                self.snap, self.ld, self.rel = _snap(), {"pct": 10.0, "used": 1, "quota": 10, "keep_days": 60, "error": ""}, {"pointers": []}

            def status(self):
                return self.snap

            def logdrop(self):
                return self.ld

            def releases(self):
                return self.rel

            def resign_hint(self, nm):
                return "6_Resign.bat"

            def host(self):
                return "SANDBOX"

            def activity(self):
                return self.act

            def local_now(self):
                return self.loc
        S = Src()
        S.act, S.loc = "", datetime.datetime(2026, 11, 24, 12, 0)

        def mk(phase, minutes):
            u = a.cursor().execute("SELECT DATEADD(MINUTE, ?, SYSUTCDATETIME())", minutes).fetchone()[0]
            return "phase=%s until=%s at=x code=0 pid=1" % (phase, u.strftime("%Y%m%dT%H%M%SZ"))
        scan = lambda: N.scan(src=S)
        r0 = scan()
        S.snap = _snap(eac=False)
        scan()
        scan()
        c5 = q1("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.TgNotifyPut 'stack', N'k', N't', N'x', 0, 0, 60, N'x', @i OUTPUT, @c OUTPUT; SELECT @c")[0]
        check("стенд: общий выключатель по умолчанию ВЫКЛЮЧЕН — EacServer лежит два прохода, уведомлений не поставлено, adm.TgNotifyPut — код 5; отметка "
              "службы пишется; курсоры журнала заведены первым проходом",
              cnt_tg() == 0 and c5 == 5 and r0["beat"] and not r0["errors"] and q1("SELECT host FROM adm.NotifyBeat WHERE id = 1")[0] == "SANDBOX"
              and q1("SELECT COUNT(*) FROM adm.NotifyState WHERE event_key = '_cursor'")[0] == 3, (r0, c5))
        w_adm = _refused(lambda: ops.run(adm, "notify.rule.set", {"event": "_master", "enabled": True}))
        pv = ops.run(own, "notify.rule.set", {"event": "_master", "enabled": True}, dry=True)["preview"]
        ops.run(own, "notify.rule.set", {"event": "_master", "enabled": True})
        w_again = _refused(lambda: ops.run(own, "notify.rule.set", {"event": "_master", "enabled": True}, dry=True))
        check("стенд: включает только owner (admin — отказ notify.manage), предпросмотр предупреждает об отправке, повтор — «уже включён»",
              w_adm and "notify.manage" in w_adm and "sendMessage" in " ".join(pv["warnings"]) and w_again == "выключатель Telegram уже включён", (w_adm, w_again))
        scan()
        rows = lambda: a.cursor().execute("SELECT id, event_key, dedup_key, title, text_en, quiet, repeats, status FROM adm.Outbox WHERE transport = 'telegram' "
                                          "AND kind = 'notify' ORDER BY id").fetchall()
        e1 = [r for r in rows() if r[1] == "eac_down"]
        check("стенд: EacServer всё ещё лежит после включения — одно уведомление (срочное, со звуком), счётчик проходов в памяти", len(e1) == 1
              and "AsdaEacServer не запущен" in e1[0][4] and not e1[0][5], [tuple(r) for r in rows()])
        scan()
        S.snap = _snap()
        scan()
        e2 = [r for r in rows() if r[1] == "eac_down"]
        check("стенд: пока лежит — второго нет (напоминание через 6 ч), поднялся — «снова работает» (ключ eac:up)",
              len(e2) == 2 and e2[1][2] == "eac:up" and "снова работает" in e2[1][4], [tuple(r) for r in e2])
        # стойка: процессы игры не работают, но владелец остановил стойку — молчит; не остановлена — уведомление
        audit.write(own, "stack.stop", "stack", {}, None, None, "ok", "остановлено")
        S.act = mk("stopped", 720)                 # ★ р78 В-1: «остановлена» — только по отметке restart_stack.py --stop-only (панельный stack.stop — тоже он)
        S.snap = _snap(gs=False)
        scan()
        scan()
        n_stop = len([r for r in rows() if r[1] == "stack"])
        audit.write(own, "stack.start", "stack", {}, None, None, "ok", "запущено")
        scan()
        scan()
        scan()
        n_quiet = len([r for r in rows() if r[1] == "stack"])
        a.cursor().execute("UPDATE adm.audit SET at = DATEADD(MINUTE, -20, at) WHERE action LIKE 'stack.%'")
        S.act = mk("run", 45)                      # прямой restart_stack.py без панели: отметка действует
        scan()
        scan()
        scan()
        n_mark = len([r for r in rows() if r[1] == "stack"])
        S.act = "phase=done until=20000101T000000Z at=x code=0 pid=1"     # отметка истекла
        scan()
        scan()
        n_two = len([r for r in rows() if r[1] == "stack"])
        scan()
        st1 = [r for r in rows() if r[1] == "stack"]
        S.snap = _snap()
        scan()
        # ★ р78 В-1 / К-3: «stopped» снимает полная стойка; срок дальше 13 ч — не верим; бессрочного признака по журналу нет
        S.act = mk("stopped", 720)
        scan()                                     # стойка полная — «stopped» больше не глушит
        S.snap = _snap(eac=False)
        a.cursor().execute("UPDATE adm.NotifyState SET last_put_utc = DATEADD(HOUR, -2, last_put_utc) WHERE event_key = 'eac_down'")
        a.cursor().execute("UPDATE adm.Outbox SET status = 2 WHERE transport = 'telegram' AND status = 0")
        n_e0 = len([r for r in rows() if r[1] == "eac_down"])
        scan()
        scan()
        n_e1 = len([r for r in rows() if r[1] == "eac_down"]) - n_e0
        S.snap = _snap()
        scan()
        busy_far = N._stack_busy(type("X", (), {"cn": a, "src": type("Y", (), {"activity": lambda self: mk("run", 60 * 20)})(),
                                                  "now": a.cursor().execute("SELECT SYSUTCDATETIME()").fetchone()[0]})())
        S.act = ""
        check("р78 В-1 / К-3: после «stopped» стойку подняли не панелью (снимок полный) — EacServer упал: уведомление приходит; отметка со сроком "
              "дальше 13 ч — не действует; в журнале панели последняя stack.stop больше не глушит", n_e1 == 1 and busy_far == (False, False)
              and "stack.stop\"" not in _read(ROOT, "domains", "notify.py").split("def _stack_busy")[1].split("def _state_event")[0].replace('!= "stack.stop"', ""), (n_e1, busy_far))
        check("р77 В-2: после успешного stack.* панели 15 мин тишины, пока действует отметка restart_stack.py — тишина; после отметки два прохода — ещё "
              "нет, третий — уведомление", n_quiet == 0 and n_mark == 0 and n_two == 0 and len(st1) == 1, (n_quiet, n_mark, n_two, len(st1)))
        check("стенд: стойка остановлена владельцем (stack.stop ok) — процессы не работают, уведомления нет; после запуска GameServer лежит три прохода — "
              "«не работают процессы стойки», в тексте процесс, не игроки",
              n_stop == 0 and len(st1) == 1 and "GameServer (мир, канал 1)" in st1[0][4] and "(1 из 15)" in st1[0][4], [tuple(r) for r in st1])
        # журнал: суточная задача, стойка, бэкап, набор изменений
        dctx = ops.Ctx(None, sched.LOGIN, "owner", "", "sched")
        audit.write(dctx, "econ.snapshot", "", {}, None, None, "error", "AsdaAdmin: тайм-аут 10.1.2.3")
        audit.write(own, "stack.restart", "stack", {}, None, None, "error", "StackFailed: GameServer не поднялся")
        audit.write(own, "db.backup", "Joy1", {}, None, None, "error", "BACKUP DATABASE failed")
        audit.write(own, "shop.cs_server_apply", "cs:7", {}, None, None, "ok", "применено, стойка перезапущена")
        audit.write(own, "players.view", "", {}, None, None, "error", "не уведомлять")
        scan()
        ev = {r[1]: r for r in rows()}
        check("стенд: из журнала — суточная задача (адрес IP скрыт), сбой рестарта стойки, сбой бэкапа, итог серверной половины набора; прочие действия — нет",
              "econ.snapshot" in ev["task_failed"][4] and "x.x.x.x" in ev["task_failed"][4] and "10.1.2.3" not in ev["task_failed"][4]
              and "StackFailed" in [r for r in rows() if r[2] == "op:stack.restart"][0][4] and "BACKUP" in ev["backup_failed"][4]
              and "cs:7" in ev["changeset_apply"][4] and "готово" in ev["changeset_apply"][4]
              and not [r for r in rows() if "не уведомлять" in r[4]], {k: v[4][:80] for k, v in ev.items()})
        # склейка и пауза (★ р77 М-1: суточная задача — одно в сутки; М-3: числа — в столбцах)
        audit.write(dctx, "econ.snapshot", "", {}, None, None, "error", "второй сбой")
        scan()
        tf = [r for r in rows() if r[1] == "task_failed"]
        a.cursor().execute("UPDATE adm.Outbox SET status = 2 WHERE transport = 'telegram' AND status = 0")
        audit.write(dctx, "econ.snapshot", "", {}, None, None, "error", "третий сбой")
        scan()
        tf2 = [r for r in rows() if r[1] == "task_failed"]
        supp = q1("SELECT suppressed FROM adm.NotifyState WHERE event_key = 'task_failed' AND item_key = N'daily:econ.snapshot'")[0]
        a.cursor().execute("UPDATE adm.NotifyState SET last_put_utc = DATEADD(HOUR, -2, last_put_utc) WHERE event_key = 'task_failed'")
        audit.write(dctx, "econ.snapshot", "", {}, None, None, "error", "сбой через час")
        scan()
        tf2b = [r for r in rows() if r[1] == "task_failed"]
        a.cursor().execute("UPDATE adm.NotifyState SET last_put_utc = DATEADD(HOUR, -25, last_put_utc) WHERE event_key = 'task_failed'")
        audit.write(dctx, "econ.snapshot", "", {}, None, None, "error", "четвёртый сбой")
        scan()
        tf3 = [r for r in rows() if r[1] == "task_failed"]
        sn3 = q1("SELECT supp_n FROM adm.Outbox WHERE id = ?", tf3[-1][0])[0]
        check("стенд: повтор до отправки — склеен в ту же строку (повторов 1, текст свежий); после отправки суточная задача повторяется раз в час — "
              "подавлено сутки (р77 М-1); через сутки — новое сообщение, число подавленных — в столбце supp_n (р77 М-3) и в тексте экрана",
              len(tf) == 1 and tf[0][6] == 1 and "второй сбой" in tf[0][4] and len(tf2) == 1 and supp == 1 and len(tf2b) == 1 and len(tf3) == 2
              and sn3 == 2 and "ещё повторов этого события за паузу: 2" in [x for x in N.view()["rows"] if x["id"] == tf3[-1][0]][0]["text"],
              ([tuple(r) for r in tf3], supp, sn3))
        a.cursor().execute("UPDATE adm.Outbox SET status = 2 WHERE transport = 'telegram' AND status = 0")
        audit.write(dctx, "econ.snapshot", "", {}, None, None, "ok", "снимок снят")
        scan()
        up = [r for r in rows() if r[2] == "daily:econ.snapshot:up"]
        audit.write(dctx, "camp.rank_rebuild", "", {}, None, None, "ok", "ok")
        scan()
        check("р77 М-1: задача снова выполнилась — «снова выполнена» один раз (только после реально ушедшего сбоя), прочие успешные задачи — молчат",
              len(up) == 1 and "снова выполнена" in up[0][4] and not [r for r in rows() if "camp.rank_rebuild" in (r[2] or "")], [tuple(r) for r in up])
        # выключатель события
        ops.run(own, "notify.rule.set", {"event": "backup_failed", "enabled": False})
        audit.write(own, "db.backup", "Joy1", {}, None, None, "error", "снова")
        scan()
        check("стенд: выключенное событие (бэкап) не ставится", len([r for r in rows() if r[1] == "backup_failed"]) == 1)
        # задания: пропущенное — любое, сбой стойки — из журнала (не дублируется)
        a.cursor().execute("INSERT adm.job (op, runner, run_at, status, created_by, created_role, finished_at, result) VALUES "
                           "('live.announce', 'service', SYSUTCDATETIME(), 'missed', N'own_t', 'owner', SYSUTCDATETIME(), NULL), "
                           "('stack.restart', 'pc', SYSUTCDATETIME(), 'failed', N'own_t', 'owner', SYSUTCDATETIME(), N'x')")
        scan()
        jb = [r for r in rows() if r[2].startswith("job:")]
        check("стенд: задание пропущено — уведомление «пропущено», сбой задания стойки — не дублируется (его итог уже из журнала)",
              len(jb) == 1 and jb[0][2] == "job:live.announce" and "пропущено" in jb[0][4], [tuple(r) for r in jb])
        # квота, подпись, падения, жалобы (час пределов — заново: выше уже 10 уведомлений)
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -2, created_utc) WHERE transport = 'telegram'")
        a.cursor().execute("UPDATE adm.NotifyState SET suppressed = 0 WHERE event_key = '_overflow'")
        S.ld = dict(S.ld, pct=85.0, used=4500000000, quota=5368709120)
        S.rel = {"pointers": [{"name": "alpha", "sig": "ok", "level": "urgent", "days_left": 2.4, "expires": "2026-11-26T00:00:00Z"},
                              {"name": "launcher", "sig": "unverified", "level": "none"}, {"name": "version.json", "sig": "ok", "level": "ok"}]}
        a.cursor().execute("INSERT adm.ClientCrash (pkg_sha256, file_name, login, pkg_kind, status, sig, exc_code, row_md5) VALUES (REPLICATE('a', 64), N'x.acrash', N'secretlogin', 1, "
                           "'ok', 'abcdef123456', '0xC0000005', REPLICATE('0', 32)), (REPLICATE('b', 64), N'y.acrash', N'other', 1, 'ok', 'abcdef123456', '0xC0000005', "
                           "REPLICATE('1', 32))")
        a.cursor().execute("INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, body, created_utc) VALUES "
                           "(111, N'ReporterName', N'TargetNick', 'cheat', N'body', DATEADD(HOUR, -13, SYSUTCDATETIME())), "
                           "(112, N'R2', N'T2', 'scam', N'body', DATEADD(HOUR, -1, SYSUTCDATETIME()))")
        scan()
        scan()
        ev = {}
        for r in rows():
            ev.setdefault(r[1], []).append(r)
        rep = ev.get("report_stale") or [[None] * 8]
        check("стенд: LogDrop 85 % — одно (не срочное, ночью без звука), подпись alpha < 3 суток — одно, launcher не получен — молчит; новое место падения — "
              "одно (без логинов), жалоба старше 12 ч — одна (номер и категория, без ников и авторов), свежая — нет; второй проход — ничего нового",
              len(ev.get("logdrop_quota", [])) == 1 and ev["logdrop_quota"][0][5] and "85.0%" in ev["logdrop_quota"][0][4]
              and len(ev.get("release_sign", [])) == 1 and "alpha" in ev["release_sign"][0][4] and "6_Resign.bat" in ev["release_sign"][0][4]
              and len(ev.get("crash_new", [])) == 1 and "abcdef123456" in ev["crash_new"][0][4] and "учёток 2" in ev["crash_new"][0][4]
              and "secretlogin" not in ev["crash_new"][0][4] and len(ev.get("report_stale", [])) == 1 and "чит / бот" in rep[0][4]
              and "TargetNick" not in rep[0][4] and "ReporterName" not in rep[0][4], {k: [x[4][:90] for x in v] for k, v in ev.items()})
        # предел частоты 10 в час (★ р77: срочные — вне его)
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(MINUTE, -5, created_utc) WHERE transport = 'telegram'")
        n_hour = q1("SELECT COUNT(*) FROM adm.Outbox WHERE transport = 'telegram' AND kind = 'notify' AND event_key NOT IN ('stack', 'eac_down', 'backup_failed') "
                    "AND created_utc > DATEADD(HOUR, -1, SYSUTCDATETIME())")[0]
        put = lambda ev, k: q1("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.TgNotifyPut ?, ?, N't', N'x', 0, 1, 60, N'x', @i OUTPUT, @c OUTPUT; "
                               "SELECT @c", ev, k)[0]
        codes = [put("crash_new", "lim%d" % i) for i in range(12 - n_hour)]
        c_stack = put("stack", "urgent-in-limit")
        c_eac = [put("eac_down", "u%d" % i) for i in range(7)]
        c_up = put("eac_down", "u0:up")
        lp = q1("SELECT last_put_utc FROM adm.NotifyState WHERE event_key = 'eac_down' AND item_key = N'u6'")[0]
        check("р78 К-4: «снова работает» (…:up) не режется пределом срочного и не считается в нём, срочное при упоре попытку не запоминает",
              c_up == 0 and lp is None, (c_up, lp))
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -2, created_utc) WHERE transport = 'telegram'")
        put("crash_new", "after")
        last = q1("SELECT TOP 1 over_n FROM adm.Outbox WHERE transport = 'telegram' ORDER BY id DESC")[0]
        o_stack = q1("SELECT over_n FROM adm.Outbox WHERE transport = 'telegram' AND dedup_key = N'urgent-in-limit'")[0]
        o_up = q1("SELECT over_n FROM adm.Outbox WHERE transport = 'telegram' AND dedup_key = N'u0:up'")[0]
        check("стенд: предел %d уведомлений в час — сверх него код 1, число не поставленных (каждое — один раз, р77 М-2) — в следующем сообщении "
              "(столбец over_n); р77 В-1: «стойка» при исчерпанном общем пределе — поставлена, у срочного своё: 6 в час, седьмое — код 1"
              % N.PER_HOUR, codes.count(1) == 2 and codes.count(0) == len(codes) - 2 and c_stack == 0 and c_eac == [0] * 6 + [1] and o_stack == 2 and o_up == 1 and last == 0,
              (n_hour, codes, c_stack, c_eac, o_stack, last))
        # ★ р78 К-4: очередь отправителя — срочные первыми
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE transport = 'telegram' AND status = 0")
        put("crash_new", "order-low")
        q1("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.TgNotifyPut 'task_failed', N'order-normal', N't', N'x', 0, 0, 60, N'x', @i OUTPUT, @c OUTPUT; SELECT @c")
        put("stack", "order-urgent")
        SB = G.Store(connect=_AsBot)
        order = [x["event"] for x in SB.tg_claim(3)]
        SB.tg_claimed_ok()
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE transport = 'telegram' AND status IN (0, 1)")
        check("р78 К-4: отправитель забирает срочные первыми, потом обычные, потом не срочные", order == ["stack", "task_failed", "crash_new"], order)
        # разделение очередей
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE transport = 'telegram' AND status = 0")
        ops.run(own, "outbox.test", {})
        rt = ops.run(own, "telegram.test", {"mode": "check"})
        rp = ops.run(own, "telegram.ping", {})
        ops.run(own, "notify.rule.set", {"event": "backup_failed", "enabled": True})
        audit.write(own, "db.verify", "Joy1", {}, None, None, "error", "перепроверка бэкапа упала (для отправителя)")
        scan()
        SD = B.Store(connect=_AsBot)
        dc = SD.out_claim(5)
        SD.out_claimed_ok()
        ov = __import__("domains.outbox", fromlist=["view"]).view({"status": "all"})
        check("стенд: бот Discord забирает только строки Discord (проверочная запись), строк Telegram не видит ни захват, ни экран «Очередь Discord»",
              len(dc) == 1 and dc[0]["kind"] == "test" and dc[0]["channel"] == "test-info" and all(r["channel"] != "owner" for r in ov["rows"]),
              (dc, [r["channel"] for r in ov["rows"]]))
        # отправитель: настоящий Store под asda_reports, подставной HTTP
        http = _Http()
        api = G.TgApi("123456789:" + "B" * 35, 4242, proxy="", opener=http)
        W = G.Worker(G.Store(connect=_AsBot), api=api, ledger=G.Ledger(os.path.join(tmp.name, "tg.json")), limiter=G.Limiter(per_hour=1000),
                     clock=lambda: datetime.datetime(2026, 11, 23, 3, 0))
        for _ in range(6):
            asyncio.run(W.tick())
        sent = [r for r in http.reqs if r[0] == "sendMessage"]
        st_t = q1("SELECT status, error FROM adm.Outbox WHERE id = ?", rt["result"]["id"])
        st_p = q1("SELECT status, tg_message_id FROM adm.Outbox WHERE id = ?", rp["result"]["id"])
        bk = q1("SELECT TOP 1 status, tg_message_id, attempts FROM adm.Outbox WHERE transport = 'telegram' AND dedup_key = N'db.verify' ORDER BY id DESC")
        check("стенд: отправитель (asda_reports) — проверка вызывает только getMe и отмечается «тест» без сообщения; проверочное сообщение и уведомление — "
              "sendMessage в чат из секрета, номер сообщения записан; ночью (03:00) бэкап — со звуком (срочность normal); методы — только getMe и sendMessage",
              {r[0] for r in http.reqs} == {"getMe", "sendMessage"} and len(sent) == 2 and all(r[1]["chat_id"] == 4242 for r in sent)
              and st_t[0] == 6 and "getMe: @@@ASTORY_TELEGRAM_BOT@@" in st_t[1] and st_p[0] == 2 and st_p[1]
              and tuple(bk[:1]) == (2,) and bk[1] and any(x[1]["text"].startswith("Astory: проверочное") for x in sent)
              and not [x for x in sent if "бэкап" in x[1]["text"]][0][1]["disable_notification"],
              ([(r[0], r[1].get("text", "")[:40]) for r in http.reqs], tuple(st_t), tuple(st_p), tuple(bk)))
        q1("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.TgNotifyPut 'logdrop_quota', N'night', N't', N'ночное не срочное', 0, 1, 60, N'x', @i OUTPUT, @c OUTPUT; SELECT @c")
        asyncio.run(W.tick())
        check("стенд: не срочное ночью — сразу, но без звука (disable_notification)", http.reqs[-1][1].get("disable_notification") is True, http.reqs[-1])
        n_req = len(http.reqs)
        for _ in range(3):
            asyncio.run(W.tick())
        check("стенд: очередь пуста — отправитель ничего не шлёт, повторов нет", len(http.reqs) == n_req)
        pings = [_refused(lambda: ops.run(own, "telegram.ping", {})) for _ in range(3)]
        check("стенд: проверочных сообщений не больше 3 в час (4-е — отказ)", pings[:2] == [None, None] and pings[2] and "предел" in pings[2], pings)
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE transport = 'telegram' AND status = 0")
        a.cursor().execute("UPDATE adm.NotifyBeat SET beat_utc = DATEADD(MINUTE, -20, beat_utc)")
        asyncio.run(W.tick())
        asyncio.run(W.tick())
        pd = [r for r in http.reqs[n_req:] if r[0] == "sendMessage"]
        scan()
        asyncio.run(W.tick())
        pd2 = [r for r in http.reqs[n_req:] if r[0] == "sendMessage"]
        check("стенд: отметка службы старше %d мин — отправитель шлёт «служба админ-центра не отмечалась» один раз, служба отметилась — «снова отмечается»"
              % G.PANEL_STALE_MIN, len(pd) == 1 and re.search(r"не отмечалась (19|20|21) мин", pd[0][1]["text"]) and len(pd2) == 2 and "снова отмечается" in pd2[1][1]["text"],
              [r[1]["text"][:60] for r in pd2])
        # ★ р77 В-1: 10 новых мест падения и падение стойки в один час — места одним сообщением, стойка доходит
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE transport = 'telegram' AND status = 0")
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -3, created_utc) WHERE transport = 'telegram'")
        for i in range(10):
            a.cursor().execute("INSERT adm.ClientCrash (pkg_sha256, file_name, login, pkg_kind, status, sig, exc_code, row_md5) VALUES (?, N'z.acrash', N'l', 1, "
                               "'ok', ?, '0xC0000005', REPLICATE('2', 32))", ("%064x" % (1000 + i), "p%011d" % i))
        audit.write(own, "stack.start", "stack", {}, None, None, "error", "StackFailed: в тот же час")
        scan()
        cr = [r for r in rows() if r[1] == "crash_new" and r[7] == 0]
        sk = [r for r in rows() if r[1] == "stack" and r[7] == 0 and "в тот же час" in r[4]]
        check("р77 В-1: 10 новых мест падения за проход — одно сообщение (все 10 в тексте), «стойка не поднялась» в тот же час — поставлена",
              len(cr) == 1 and all("p%011d" % i in cr[0][4] for i in range(10)) and len(sk) == 1, ([r[4][:60] for r in cr], len(sk)))
        # ★ р77 М-4: при выключенном общем разовые события не помечаются, при включении — одна сводка
        ops.run(own, "notify.rule.set", {"event": "_master", "enabled": False})
        a.cursor().execute("INSERT adm.ClientCrash (pkg_sha256, file_name, login, pkg_kind, status, sig, exc_code, row_md5) VALUES (REPLICATE('c', 64), N'q.acrash', "
                           "N'l', 1, 'ok', 'offsig000001', '0xC0000005', REPLICATE('3', 32))")
        a.cursor().execute("INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, body, created_utc) VALUES "
                           "(113, N'R3', N'T3', 'rmt', N'body', DATEADD(HOUR, -14, SYSUTCDATETIME()))")
        scan()
        scan()
        marked_off = q1("SELECT COUNT(*) FROM adm.NotifyState WHERE event_key = 'crash_new' AND item_key = N'offsig000001'")[0]
        ops.run(own, "notify.rule.set", {"event": "_master", "enabled": True})
        scan()
        scan()
        sm = [r for r in rows() if (r[2] or "").startswith("summary:")]
        check("р77 М-4: пока общий выключен — новое место и жалоба не помечаются; после включения — ОДНА сводка «за время выключения: 1 новых мест, 1 жалоб», "
              "второй проход — ничего (р78 К-6: построчно)", marked_off == 0 and len(sm) == 1 and "1 новых мест падения, 1 жалоб" in sm[0][4]
              and "offsig000001" in sm[0][4] and sm[0][4].count("\n") >= 2
              and "№" in sm[0][4] and "T3" not in sm[0][4], [r[4][:120] for r in sm])
        # ★ р77 М-6: дребезг — упал, поднялся, упал в паузе, поднялся: «снова работает» только один раз (после реально ушедшего «не работает»)
        a.cursor().execute("UPDATE adm.Outbox SET status = 2 WHERE transport = 'telegram' AND status = 0")
        n_up0 = len([r for r in rows() if r[2] == "eac:up"])
        a.cursor().execute("UPDATE adm.NotifyState SET last_put_utc = DATEADD(HOUR, -2, last_put_utc) WHERE event_key = 'eac_down'")
        for snap in (_snap(eac=False), _snap(eac=False), _snap(), _snap(eac=False), _snap(eac=False), _snap()):
            S.snap = snap
            scan()
        n_up = len([r for r in rows() if r[2] == "eac:up"]) - n_up0
        check("р77 М-6: EacServer упал → поднялся → упал в паузе (подавлено) → поднялся — «снова работает» одно", n_up == 1, n_up)
        # ★ р77 К-3: свои сообщения ПК — на экране
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE transport = 'telegram' AND status = 0")
        a.cursor().execute("UPDATE adm.NotifyBeat SET beat_utc = DATEADD(MINUTE, -30, beat_utc)")
        asyncio.run(W.tick())
        loc_rows = [x for x in N.view()["rows"] if x["kind"] == "local"]
        check("р77 К-3: сообщения ПК («служба не отмечалась» и прошлые) — строками очереди вида local на экране, с итогом отправки",
              loc_rows and loc_rows[0]["title"].startswith("сообщение ПК:") and loc_rows[0]["state"] == "sent", loc_rows[:2])
        scan()
        v = N.view()
        fq, _p = _route("/api/telegram")

        class _Req:
            def __init__(self, role):
                self.query, self.session = {}, {"user": {"role": role, "login": "t_" + role}}
        ro = fq(_Req("owner"), None)
        aud = {r[0]: r[1] for r in a.cursor().execute("SELECT action, COUNT(*) FROM adm.audit WHERE result = 'ok' AND (action LIKE 'notify.%' OR action LIKE 'telegram.%') "
                                                     "GROUP BY action")}
        check("стенд: экран — общий включён, 10 событий (бэкап снова включён), записи Telegram с итогами, отметка отправителя; API — can notify.manage у owner; "
              "журнал adm.audit — notify.rule.set 5, telegram.test 1, telegram.ping 3",
              v["installed"] and v["master"] and len(v["rules"]) == 10 and all(r["enabled"] for r in v["rules"]) and v["pc_seen"] and v["rows"]
              and ro["can"]["notify.manage"] and aud == {"notify.rule.set": 5, "telegram.test": 1, "telegram.ping": 3}, (aud, v["warnings"]))
    finally:
        db.set_override("admin", None)
        tmp.cleanup()
        m2 = ldb("master")
        try:
            m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m2.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def live(check):
    """Живая dev: только проверочная запись selftest (отправитель её не шлёт) и захват только проверочных. Telegram не вызывается, выключатели не меняются."""
    _paths()
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import notify as N
    import tg_bot as G
    if config.get().on_server:
        return check("живой самотест А7.5 «Telegram владельцу» — с ПК", True)
    cn = db.admin()
    try:
        q = lambda o, p: db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?) AS p", (o, p))[0]["p"]
        perm = {"rule_sel": q("adm.NotifyRule", "SELECT"), "rule_upd": q("adm.NotifyRule", "UPDATE"), "state_ins": q("adm.NotifyState", "INSERT"),
                "put": q("adm.TgNotifyPut", "EXECUTE"), "test": q("adm.TgTestPut", "EXECUTE"), "claim": q("adm.TgClaim", "EXECUTE"),
                "done": q("adm.TgDone", "EXECUTE"), "beatget": q("adm.TgBeatGet", "EXECUTE")}
    finally:
        cn.close()
    check("живое (asda_admin): выключатели, память и отметки — чтение и процедуры панели, без прямой записи и без процедур отправителя",
          perm == {"rule_sel": 1, "rule_upd": 0, "state_ins": 0, "put": 1, "test": 1, "claim": 0, "done": 0, "beatget": 0}, perm)
    S = G.Store()
    try:
        c = S._cn()
        try:
            rows = c.cursor().execute(_read(ROOT, "sql", "adminc_29_telegram_verify.sql")).fetchall()
        finally:
            c.close()
        bad = [tuple(r) for r in rows if int(r[1] or 0) != int(r[2])]
        check("живое (путь отправителя): пароль asda_reports из reports.env, вход по VPN, права = adminc_29_telegram_verify (%d проверок)" % len(rows),
              len(rows) == 17 and not bad, bad)
        b = S.tg_beat()
        check("живое: отметка службы панели свежая (моложе %d мин — служба ищет события), выключатели читаются отправителем (общий — %s)"
              % (N.PANEL_STALE_MIN, "включён" if b.get("master") else "выключен"),
              b.get("age_s") is not None and int(b["age_s"]) < N.PANEL_STALE_MIN * 60, b)
    except Exception as ex:
        check("живое (путь отправителя): вход asda_reports по VPN", False, "%s: %s" % (type(ex).__name__, str(ex)[:200]))
    v0 = N.view()
    check("живое: экран читается (установлен, событий %d, общий выключатель %s — самотест его не трогает)" % (len(v0["rules"]), "включён" if v0["master"] else "выключен"),
          v0["installed"] and len(v0["rules"]) == 10, v0.get("error"))
    r = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "telegram.test", {"mode": "selftest"})
    oid = r["result"]["id"]
    got, claimed = [], None
    try:
        got = S.tg_claim(1, test_only=True)          # ТОЛЬКО проверочные: уведомления и проверочные сообщения этим захватом не берутся
        for x in got:
            if not x["test"]:
                raise RuntimeError("захват test_only вернул НЕ проверочную запись №%d" % x["id"])
        for x in got:                                # Telegram не вызывается: итог «тест» сразу
            S.tg_done(x["id"], True, "проверочная запись — Telegram не вызывался" if x["title"] == "selftest"
                      else "взята живым самотестом — getMe не вызывался, повторите проверку кнопкой")
        S.tg_claimed_ok()
        claimed = True
    except Exception as ex:
        claimed = "%s: %s" % (type(ex).__name__, str(ex)[:200])
    row = [x for x in N.view()["rows"] if x["id"] == oid]
    check("живое: проверочная запись №%d (selftest) → захват только проверочных → итог «тест» (или её уже отметил работающий отправитель — тоже без "
          "Telegram); номера сообщения нет — в Telegram ничего не ушло" % oid,
          claimed is True and row and row[0]["state"] == "test" and not row[0]["message_id"], (claimed, row[:1]))
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import notify as N\nfrom core import sched\nimport inspect\n"
             "v = N.view()\nprint('TGPROBE installed=%s hook=%s ids=%s' % (v['installed'], 'notify.scan_due()' in inspect.getsource(sched.start), "
             "','.join(str(r['id']) for r in v['rows'][:20])))\n")
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
    mm = re.search(r"TGPROBE installed=(\w+) hook=(\w+) ids=([\d,]*)", out)
    check("служба на сервере (SSH): раздел читается, поиск событий в потоке задач службы, проверочная запись №%d видна" % oid,
          bool(mm) and mm.group(1) == "True" and mm.group(2) == "True" and str(oid) in mm.group(3).split(","), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/telegram" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/telegram без входа — 401", code == 401, code)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import selftest as T
    T.utf8_stdout()                         # ★ р83 М-6 (А7.7): консоль cp1251 не роняет самотест
    offline(T.check)
    if "--sandbox" in sys.argv:
        sandbox(T.check, T._ldb)
    if "--live" in sys.argv:
        live(T.check)
    bad = [r for r in T.RESULTS if not r[1]]
    print("\nИТОГ: %d проверок, ошибок %d" % (len(T.RESULTS), len(bad)))
    sys.exit(1 if bad else 0)
