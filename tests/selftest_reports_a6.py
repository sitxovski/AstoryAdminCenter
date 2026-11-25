# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_reports_a6.py — самотест шага А6.11, часть «жалобы» (22.11.2026; решение владельца №6 — канал = бот Discord; domains/reports.py,
sql/adminc_23_reports.sql и adminc_23_reports_verify.sql, /api/reports/*, web/reports.js, консоль reports, операции report.*; бот —
AstoryAdminCenter/DiscordBot/player_reports.py и test_player_reports.py).

offline(check)  — права (reports.view / reports.handle — owner, admin, gm), операции под reports.handle и без отката, маршруты, отказы ввода без
                  базы (очередь, номер, итог, пояснение, дело, текст ответа), базы нет — понятный отказ, тексты без «; », правила ссылок и
                  сигнатуры картинок = бот, SQL домена (запись — только UPDATE adm.PlayerReport и INSERT adm.PlayerReportReply, без DELETE, игровые
                  базы — GameReader), переводы EN (shadowed_translations = 0), веб без innerHTML (данные — текстовыми узлами, картинка — data: только
                  четырёх типов), консоль (ключи, --as до базы), SQL adminc_23 (пакет ANSI до CREATE, DENY бота, права панели), выкладка
                  (порядок, проверка под asda_reports, пароль одной строкой в reports_bot.ini), модульные тесты бота (без Discord).
sandbox(check, ldb) — СВОИ базы LocalDB: AsdaAdmin (adminc_02 + adminc_23 дважды), Joy1, AsdaStoryOp, joylog1 (san.v_cases); бот пишет НАСТОЯЩИМ
                  player_reports.Store под EXECUTE AS USER asda_reports: подача, повтор, пределы часа / суток / всех, скриншоты (тип, размер, чужая,
                  поздняя, четвёртый, суточные байты); права asda_reports; панель: очередь и фильтры, карточка (цель по нику без учёта регистра,
                  удалённый персонаж, автор ↔ учётка, другие жалобы, ссылки), скриншот (подмена байтов — отказ), report.take / close / case / reply
                  (права, чужая взятая, дело есть / нет, итог «в дело» без дела, отпечаток expect), ответ: очередь → бот забирает один раз → итог,
                  «неизвестно» по сроку, бюджет ответов; журнал adm.audit.
live(check)     — только чтение живой dev: права asda_admin на adm.PlayerReport* (столбцы разбора), бот: пароль логина asda_reports по SSH из
                  secrets\\reports_bot.ini и проверка его прав adminc_23_reports_verify ПОД asda_reports по VPN (тот же путь, что у бота), очередь
                  и карточка (если жалобы есть), служба на сервере (SSH) читает очередь, без входа — 401. Жалоб и ответов в живой не создаёт.
Побочных эффектов при импорте нет.
"""
import base64
import os
import re
import secrets
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
BOT = os.path.join(PORT, "AstoryAdminCenter", "DiscordBot")
CYR = re.compile("[А-Яа-яЁё]")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _refused(fn):
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


def _bot():
    if BOT not in sys.path:
        sys.path.insert(0, BOT)
    import player_reports
    return player_reports


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, db, i18n, ops
    import domains
    domains.load_all()
    from domains import reports as R
    roles = ("owner", "admin", "gm", "support")
    check("жалобы: права reports.view и reports.handle — owner, admin, gm (support — нет)",
          {r for r in roles if auth.can(r, "reports.view")} == {"owner", "admin", "gm"} == {r for r in roles if auth.can(r, "reports.handle")})
    opn = ("report.take", "report.close", "report.case", "report.reply", "reports.purge")
    from core import sched
    check("р67 С-2: срок хранения скриншотов — операция reports.purge в задачах службы раз в сутки (01:00), 90 суток после закрытия",
          dict(sched.DAILY).get("reports.purge") is not None and R.RETENTION_DAYS == 90)
    check("жалобы: операции report.take / close / case / reply — под reports.handle, не откатываются (история разбора не стирается)",
          all(ops.REGISTRY.get(n) and ops.REGISTRY[n].perm == "reports.handle" and not ops.REGISTRY[n].reversible for n in opn))
    rt = {p: _route(p) for p in ("/api/reports/list", "/api/reports/show", "/api/reports/file")}
    check("жалобы: маршруты /api/reports/list, show, file — GET, право reports.view", all(fn and perm == "reports.view" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})
    ctx = ops.Ctx(1, "owner_t", "owner", "", "web")
    why = [_refused(lambda q=q: R.report_list(q)) for q in ({"status": "x"}, {"category": "hack"}, {"target": "x" * 21}, {"reporter": "12"},
                                                           {"size": "0"}, {"size": "201"}, {"page": "x"})]
    why += [_refused(lambda v=v: R.show(v)) for v in ("x", "0", None)] + [_refused(lambda: R.file_data("-1"))]
    why += [_refused(lambda p=p: ops.REGISTRY["report.close"].preview(ctx, p)) for p in ({"id": 1, "outcome": "ban", "note": "ок ок"},
                                                                                        {"id": 1, "outcome": "action", "note": "x"},
                                                                                        {"id": 1, "outcome": "action", "note": "a\x01b c"},
                                                                                        {"id": 1, "outcome": "action", "note": "x" * 501})]
    why += [_refused(lambda p=p: ops.REGISTRY["report.case"].preview(ctx, p)) for p in ({"id": 1, "case": "12"}, {"id": 1, "case": "AC-1"})]
    why += [_refused(lambda p=p: ops.REGISTRY["report.reply"].preview(ctx, p)) for p in ({"id": 1, "text": ""}, {"id": 1, "text": "x" * 1501},
                                                                                        {"id": 1, "text": None}, {"id": 1, "text": "a\x07"})]
    why += [_refused(lambda p=p: ops.REGISTRY["report.take"].preview(ctx, p)) for p in ({"id": "x"}, {})]
    check("жалобы: отказы ввода без обращения к базе (%d: состояние, категория, ник, автор, страница, номер, итог, пояснение, дело, текст ответа)"
          % len(why), all(why), why)

    def nodb(database):
        raise db.DbError("нет подключения к %s: Login timeout expired" % database)
    db.set_override("admin", nodb)
    try:
        wn = [_refused(lambda: R.report_list({})), _refused(lambda: R.show(1)), _refused(lambda: R.file_data(1)),
              _refused(lambda: ops.REGISTRY["report.take"].preview(ctx, {"id": 1}))]
    finally:
        db.set_override("admin", None)
    check("жалобы: базы нет — отказ «жалобы не прочитаны: …» с причиной (не 500)", all(w and w.startswith("жалобы не прочитаны: нет подключения") for w in wn), wn)
    why += wn
    check("жалобы: тексты отказов без «; »", all("; " not in x for x in why if x), why)
    B = _bot()
    check("жалобы: правило ссылок панели = правилу бота (player_reports.LINK_RX), сигнатуры картинок — те же",
          R.LINK_RX.pattern == B.LINK_RX.pattern and all(R.sniff(x) == B.sniff_image(x) for x in (PNG, JPG, b"GIF89a....", b"RIFF\0\0\0\0WEBPx", b"<svg", b""))
          and R.CATEGORIES.keys() == B.CATEGORIES.keys())
    lk = R.links_of("https://discord.com/channels/1111111111111111201/1111111111111111205 javascript:alert(1)")
    check("жалобы: ссылка по правилам — ok, прочее — только текстом", [x["ok"] for x in lk] == [True, False])
    code = open(os.path.join(ROOT, "domains", "reports.py"), encoding="utf-8").read()
    body = code.split('"""', 2)[2]
    lits = [s for s in re.findall(r'"((?:[^"\\]|\\.)*)"', body) if re.search(r"\b(SELECT|FROM|INSERT|UPDATE)\b", s)]
    check("жалобы: запись — только UPDATE adm.PlayerReport и INSERT adm.PlayerReportReply (без DELETE), в SQL нет русских букв, игровые базы — GameReader",
          sorted(set(re.findall(r"INSERT (adm\.\w+)", body))) == ["adm.PlayerReportReply"] and sorted(set(re.findall(r"UPDATE (adm\.\w+)", body)))
          == ["adm.PlayerReport"] and not re.search(r"\bDELETE\b", body) and not any(CYR.search(s) for s in lits) and "GameWriter" not in body, lits[:3])
    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in why if x] + [
            "жалобы №5 нет", "файла №5 нет", "файл №5 не совпал с записью (тип, размер или sha256) — не показывается",
            "жалоба №5 изменилась с предпросмотра — откройте её заново", "жалоба №5 уже закрыта (итог action)", "жалоба №5 уже закрыта",
            "жалобу №5 уже ведёт gm_t", "жалоба №5 уже у вас", "взять жалобу №5 (чит / бот на Вася) в работу",
            "взять жалобу №5 (торговля за реальные деньги (RMT) на Bob) в работу",
            "пишется только база панели AsdaAdmin (adm.PlayerReport): кто ведёт жалобу", "жалоба №5 уже не новая — откройте её заново",
            "жалоба №5 взята в работу", "жалобу №5 ведёт gm_t — закрыть может он или администратор",
            "итог «передано в дело» — сначала свяжите жалобу с делом (кнопка «Открыть дело» или номер AC-NNNN)",
            "пишется только база панели AsdaAdmin (adm.PlayerReport), автору ничего не отправляется — ответ отдельной кнопкой",
            "жалобу вёл gm_t — закрываете вы", "закрыть жалобу №5 с итогом «меры приняты»: ban 1 day", "итог «передано в дело» — жалоба не связана с делом",
            "жалоба №5 закрыта: нарушения нет", "связать жалобу с делом может роль с правом ac.case", "жалоба №5 уже связана с делом AC-0001",
            "дела AC-0099 нет в журнале дел", "пишется только база панели AsdaAdmin (adm.PlayerReport): номер дела у жалобы",
            "учётка дела №9 — не учётка персонажа Bob из жалобы (№1, №2)", "жалоба новая — она будет взята в работу вами",
            "связать жалобу №5 с делом AC-0001", "жалоба №5 уже закрыта или связана с делом", "жалоба №5 связана с делом AC-0001",
            "на жалобу №5 уже 5 ответов — больше нельзя", "за час вы уже поставили 20 ответов — предел 20 в час",
            "ответ автору жалобы №5 (user, Discord ID 1111111111111111201) личным сообщением бота:\nSpasibo",
            "бот на ПК владельца отправит сообщение в течение минуты, если бот запущен — итог «отправлено / не доставлено» появится в карточке",
            "текст уходит автору как есть — без подписи оператора", "ответ №3 по жалобе №5 поставлен в очередь бота",
            "скриншот №3 удалён по сроку хранения 2026-01-01 01:00:00 (90 суток после закрытия жалобы), sha256 и размер сохранены",
            "жалобу ведёт gm_t — дело будет связано вами (отметка в журнале), вести жалобу продолжает gm_t",
            "удалить байты 3 скриншотов закрытых жалоб старше 90 суток после закрытия (0.1 МБ)",
            "имя, тип, размер и sha256 скриншотов остаются в карточке жалобы", "срок хранения скриншотов: удалены байты 3 файлов (0.1 МБ)",
            "Joy1 (персонаж по нику): запрос к Joy1: x", "AsdaStoryOp (учётка автора): запрос к AsdaStoryOp: x", "joylog1.san (дело): запрос к joylog1: x",
        ] + [ops.REGISTRY[n].title for n in opn]
        miss = [x for x in ru if CYR.search(i18n.tr(x).replace("Вася", ""))]
        check("жалобы EN: отказы, предпросмотры, итоги и предупреждения — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("жалобы: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js = open(os.path.join(ROOT, "web", "reports.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    wi = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
    cs = open(os.path.join(ROOT, "web", "cases.js"), encoding="utf-8").read()
    check("жалобы веб: раздел #/reports с правом reports.view, маршрут viewReports(my, q), скрипт после cases.js и acjournal.js",
          '["#/reports", "Жалобы игроков", "reports.view"' in app and 'case "reports": return viewReports(my, q);' in app
          and 0 < idx.index("/acjournal.js") < idx.index("/cases.js") < idx.index("/reports.js"))
    check("жалобы веб: без innerHTML, данные — текстовыми узлами; картинка — только data: четырёх типов от службы; ссылка — только подтверждённая службой "
          "https с rel=noopener noreferrer; «Открыть дело» — форма case.open из cases.js с предзаполнением",
          "innerHTML" not in js and "acText(" in js and 'RP_IMG = ["image/png", "image/jpeg", "image/gif", "image/webp"]' in js
          and '"data:" + r.mime + ";base64," + r.b64' in js and "RP_IMG.indexOf(r.mime) < 0" in js and 'l.ok && /^https:\\/\\//.test(l.url)' in js
          and 'rel: "noopener noreferrer"' in js and "csOpenForm(L, t ? t.uid : \"\"" in js and "function csOpenForm(L, uid, after, pre)" in cs
          and 'rpOp("report.case", { id: r.id, case: no }' in js and "T(r.body" not in js and "T(r.target" not in js)
    labels = set(re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|div|a)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) | set(re.findall(r'\["([^"\]]+)", [a-z]+ =>', js)) \
        | set(re.findall(r'T\("([^"]+)"', js)) | set(re.findall(r'placeholder: "([^"]+)"', js)) | set(re.findall(r'\}, "([^"]+)"\)', js))
    for name in ("RP_STATUS", "RP_CAT", "RP_OUT", "RP_REPLY"):
        i = js.index("const " + name)
        labels |= set(re.findall(r':\s*"([^"]+)"', js[i:js.index("\n", i)]))
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("жалобы веб EN: у подписей раздела есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack, lack[:8])
    for f in ("reports.js", "cases.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("жалобы: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("жалобы: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- консоль
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "reports"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    res = [con("list", "--bogus"), con("show"), con("nope"), con("take", "--id", "1"), con("close", "--id", "1", "--as", "x", "--outcome", "ban"),
           con("list", "--status")]
    check("жалобы консоль: неизвестный ключ, нет --id, неизвестное действие, действие без --as, неверный итог, ключ без значения — отказ без обращения к базе",
          res[0][0] and "неизвестный аргумент --bogus" in res[0][1] and res[1][0] and "нужен --id" in res[1][1] and res[2][0] and "нужно действие" in res[2][1]
          and res[3][0] and "--as <логин панели>" in res[3][1] and res[4][0] and "--outcome action" in res[4][1] and res[5][0] and "нет значения" in res[5][1],
          [x[1][-160:] for x in res])
    # ---- SQL, выкладка
    s23 = open(os.path.join(ROOT, "sql", "adminc_23_reports.sql"), encoding="utf-8").read()
    v23 = open(os.path.join(ROOT, "sql", "adminc_23_reports_verify.sql"), encoding="utf-8").read()
    head = s23.split("GO", 1)[0]
    ver = open(os.path.join(ROOT, "sql", "adminc_10_verify.sql"), encoding="utf-8").read()
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = open(os.path.join(ROOT, "deploy", "deploy_admin_center.py"), encoding="utf-8").read()
    adm = open(os.path.join(ROOT, "asda_admin.py"), encoding="utf-8").read()
    check("adminc_23: ANSI_NULLS / QUOTED_IDENTIFIER ON отдельным пакетом ДО CREATE; бот asda_reports — EXECUTE четырёх процедур и DENY на все три таблицы; "
          "панель — UPDATE только столбцов разбора, DENY DELETE и процедур бота; пароль — переменной $(ReportsPw)",
          "SET QUOTED_IDENTIFIER ON" in head and "CREATE TABLE" not in head
          and all("GRANT EXECUTE ON adm.%s" % p in s23 for p in ("ReportSubmit", "ReportFileAdd", "ReportReplyClaim", "ReportReplyDone"))
          and all("DENY  SELECT, INSERT, UPDATE, DELETE ON adm.%s" % t in s23 for t in ("PlayerReport ", "PlayerReportFile ", "PlayerReportReply "))
          and "GRANT UPDATE ON adm.PlayerReport (status, taken_by, taken_utc, closed_by, closed_utc, outcome, outcome_note, case_no, case_by, case_utc)" in s23
          and "DENY  EXECUTE ON adm.ReportSubmit     TO [asda_admin]" in s23 and "N'$(ReportsPw)'" in s23 and s23.count("$(") == s23.count("$(ReportsPw)") == 3)
    check("adminc_23_reports_verify: 19 проверок ПОД asda_reports (процедуры 1, очистка, таблицы, журнал панели, игровые базы, sysadmin — 0)",
          v23.count("UNION ALL SELECT") + 1 == 19 and len(re.findall(r",\s*1(?: AS want)?;?\s*$", v23, re.M)) == 4)
    check("жалобы выкладка: adminc_23 после adminc_20 в AsdaAdmin, пароль ReportsPw из REPORTS_PASSWORD, проверка ПОД asda_reports (18), копия пароля одной "
          "строкой в reports_bot.ini; adminc_10 — права панели по столбцам; откат — логин и таблицы; консоль в справке",
          "Run 'adminc_20_names.sql' 'AsdaAdmin'\nRun 'adminc_23_reports.sql' 'AsdaAdmin'" in dep and "$env:ReportsPw = Sec '%(sf)s' 'REPORTS_PASSWORD'" in dep
          and "-U asda_reports -d AsdaAdmin" in dep and "adminc_23_reports_verify.sql" in dep and '("asda_reports", part_reports, 19)' in dep
          and "reports_bot.ini" in dep and "Env:ReportsPw" in dep
          and "'adm.PlayerReport UPDATE status'" in ver and "'adm.PlayerReport UPDATE body'" in ver and "'adm.PlayerReportReply INSERT'" in ver
          and (rb is None or "DROP LOGIN [asda_reports]" in rb) and (rb is None or "adminc_23_reports.sql" in rb) and "  reports …" in adm)
    # ---- модульные тесты бота (без Discord и без базы)
    try:
        r = subprocess.run([py, "-I", os.path.join(BOT, "test_player_reports.py")], capture_output=True, timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        n = re.search(r"Ran (\d+) tests", out)
        check("бот: модульные тесты жалоб test_player_reports.py (%s тестов) — без Discord и базы" % (n.group(1) if n else "?"), r.returncode == 0 and n, out[-400:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("бот: модульные тесты жалоб (не запустились)", False, str(ex))


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def sandbox(check, ldb):
    """Свои базы LocalDB: бот (настоящий player_reports.Store под asda_reports) → панель (очередь, карточка, разбор, ответ)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import db, ops
    import domains
    domains.load_all()
    from domains import discordlinks, reports as R
    B = _bot()
    tag = secrets.token_hex(3)
    names = {"A": "AsdaRpA_" + tag, "Y": "AsdaRpY_" + tag, "L": "AsdaRpL_" + tag, "O": "AsdaRpO_" + tag}
    m = ldb("master")
    for k, n in names.items():
        m.cursor().execute("CREATE DATABASE [%s] COLLATE %s" % (n, "Cyrillic_General_CI_AS" if k == "A" else "Arabic_CI_AS"))
    links0 = discordlinks.links
    try:
        a = ldb(names["A"])
        text = open(os.path.join(ROOT, "sql", "adminc_23_reports.sql"), encoding="utf-8").read().replace("$(ReportsPw)", "Aa1-" + secrets.token_hex(12))
        for b in _batches(open(os.path.join(ROOT, "sql", "adminc_02_schema.sql"), encoding="utf-8").read()) + _batches(text) + _batches(text):
            a.cursor().execute(b)
        check("жалобы стенд: настоящие adminc_02 + adminc_23 дважды (повтор безопасен), логин и пользователь asda_reports",
              a.cursor().execute("SELECT COUNT(*) FROM sys.tables WHERE name IN ('PlayerReport', 'PlayerReportFile', 'PlayerReportReply')").fetchone()[0] == 3
              and a.cursor().execute("SELECT COUNT(*) FROM sys.database_principals WHERE name = 'asda_reports'").fetchone()[0] == 1)

        class _AsBot:
            """Соединение под пользователем asda_reports (EXECUTE AS); закрытие — REVERT до возврата сессии в пул (иначе сброс пула рвёт сессию)."""

            def __init__(self):
                self.c = ldb(names["A"])
                self.c.cursor().execute("EXECUTE AS USER = 'asda_reports'")

            def cursor(self):
                return self.c.cursor()

            def close(self):
                try:
                    self.c.cursor().execute("REVERT")
                finally:
                    self.c.close()
        S = B.Store(connect=_AsBot)
        cbc = _AsBot()
        cb = cbc.cursor()
        deny = []
        for q in ("SELECT COUNT(*) FROM adm.PlayerReport", "SELECT COUNT(*) FROM adm.PlayerReportReply", "SELECT COUNT(*) FROM adm.audit",
                  "INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, body) VALUES (1, N'x', N'x', 'other', N'xxxxxxxxxxxx')",
                  "UPDATE adm.PlayerReportReply SET status = 2"):
            try:
                cb.execute(q).fetchall() if q.startswith("SELECT") else cb.execute(q)
                deny.append(q)
            except Exception:
                pass
        cbc.close()
        check("жалобы стенд: asda_reports — ни чтения, ни записи таблиц жалоб и журнала панели (только процедуры)", not deny, deny)
        U1, U2, U3, U4 = 1111111111111111201, 1111111111111111202, 1111111111111111203, 1111111111111111204

        def form(nick, cat="cheat", body="он стоит ботом на карте уже три часа", links=""):
            f, errs = B.validate(nick, "сегодня вечером", body, links, cat)
            assert not errs, errs
            return f
        lnk = "https://discord.com/channels/1111111111111111201/1111111111111111205/1111111111111111206"
        c1 = S.submit(U1, "alice#1", form("bob", links=lnk))
        c_dup = S.submit(U1, "alice#1", form("BOB"))
        c2 = S.submit(U1, "alice#1", form("Kirill", "abuse"))
        c3 = S.submit(U1, "alice#1", form("Zed", "scam"))
        c_h = S.submit(U1, "alice#1", form("Other", "rmt"))
        check("жалобы стенд (бот): подача — код 0 и номер; повтор на того же персонажа (без учёта регистра ника) — код 3 с номером открытой; "
              "четвёртая за час — код 1", c1[0] == 0 and c1[1] and c_dup == (3, c1[1]) and c2[0] == 0 and c3[0] == 0 and c_h[0] == 1, (c1, c_dup, c2, c3, c_h))
        a.cursor().execute("INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, body, created_utc) SELECT ?, N'old', "
                           "CONCAT(N'T', n), 'other', N'старая жалоба для предела', DATEADD(HOUR, -2, SYSUTCDATETIME()) FROM (VALUES (1),(2),(3),(4),(5),(6),(7),(8),"
                           "(9),(10)) v(n)", U2)
        c_d = S.submit(U2, "bob#2", form("Day"))
        a.cursor().execute("INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, body, created_utc) SELECT 1000 + n, N'flood', N'F', "
                           "'other', N'старая жалоба для предела', DATEADD(HOUR, -3, SYSUTCDATETIME()) FROM (SELECT TOP (60) ROW_NUMBER() OVER (ORDER BY (SELECT 1)) "
                           "AS n FROM sys.all_objects) v")
        c_g = S.submit(U3, "carl#3", form("Glob"))
        a.cursor().execute("DELETE adm.PlayerReport WHERE reporter_name IN (N'flood', N'old')")
        bad_in = []
        for args in ((0, "x", form("bob")), (U3, "x", dict(form("bob"), category="hack")), (U3, "x", dict(form("bob"), body="коротко")),
                     (U3, "x", dict(form("bob"), nick="  "))):
            try:
                S.submit(*args)
                bad_in.append(args[2]["nick"])
            except Exception:
                pass
        check("жалобы стенд (бот): 10 за сутки — код 2, 60 за сутки от всех — код 4 (р67 С-1: было 200); процедура сама отвергает пустой ID, категорию, короткое описание, "
              "пустой ник", c_d == (2, None) and c_g == (4, None) and not bad_in, (c_d, c_g, bad_in))
        rid = c1[1]
        fc = [S.add_file(rid, U1, "a.png", PNG), S.add_file(rid, U1, "b.jpg", JPG), S.add_file(rid, U2, "c.png", PNG),
              S.add_file(rid, U1, "evil.svg", b"<svg onload=alert(1)>"), S.add_file(rid, U1, "big.png", PNG + b"\x00" * (8 * 1024 * 1024)),
              S.add_file(rid, U1, "c.gif", b"GIF89a" + b"\x00" * 10), S.add_file(rid, U1, "d.png", PNG)]
        a.cursor().execute("UPDATE adm.PlayerReport SET created_utc = DATEADD(MINUTE, -20, SYSUTCDATETIME()) WHERE id = ?", c2[1])
        f_late = S.add_file(c2[1], U1, "late.png", PNG)
        a.cursor().execute("INSERT adm.PlayerReportFile (report_id, name, mime, size_bytes, sha256, data) VALUES (?, N'x', 'image/png', 41943040, "
                           "HASHBYTES('SHA2_256', 0x00), 0x00)", c3[1])
        f_day = S.add_file(c3[1], U1, "e.png", PNG)
        a.cursor().execute("DELETE adm.PlayerReportFile WHERE size_bytes = 41943040")
        check("жалобы стенд (бот): скриншоты — PNG и JPEG записаны, чужой жалобе — 1, SVG — 4, больше 8 МБ — 3, третий GIF — 0, четвёртый — 2, "
              "жалоба старше 15 минут — 1, больше 40 МБ от автора за сутки — 5", fc == [0, 0, 1, 4, 3, 0, 2] and f_late == 1 and f_day == 5, (fc, f_late, f_day))
        # ---- игровые базы для карточки
        y = ldb(names["Y"]).cursor()
        y.execute("CREATE TABLE dbo.Charinfo (Userindex INT, Charidx TINYINT, Charname VARCHAR(20), Lvl INT)")
        y.execute("CREATE TABLE dbo.Del_Charinfo (Edate DATETIME, Userindex INT, Charidx TINYINT, Charname VARCHAR(20), Lvl INT)")
        y.execute("INSERT dbo.Charinfo VALUES (9001, 10, 'Bob', 33), (9002, 11, CONVERT(varchar(20), 0xCAE8F0E8EBEB), 5)")
        y.execute("INSERT dbo.Del_Charinfo VALUES ('2026-01-02', 9003, 10, 'Bob', 12)")
        o = ldb(names["O"]).cursor()
        o.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(61), us_block TINYINT)")
        o.execute("INSERT dbo.Us_member VALUES (9001, 'boblogin', 0), (9002, 'kir', 0), (9100, 'alicelogin', 0)")
        lg = ldb(names["L"]).cursor()
        lg.execute("CREATE SCHEMA san")
        lg.execute("CREATE TABLE san.v_cases (case_no VARCHAR(8), user_index INT, status VARCHAR(12), title NVARCHAR(200))")
        lg.execute("INSERT san.v_cases VALUES ('AC-0001', 9001, 'open', N'бот на карте'), ('AC-0002', 9555, 'open', N'другое')")
        mp = {"Joy1": names["Y"], "joylog1": names["L"], "AsdaStoryOp": names["O"]}
        db.set_override("game", lambda database: ldb(mp.get(database, database)))
        db.set_override("admin", lambda database: ldb(names["A"]))
        discordlinks.links = lambda path=None: [{"handle": "alice", "discord_id": str(U1), "login": "alicelogin", "banned": None}]
        try:
            Q = R.report_list({})
            Qc = R.report_list({"status": "all", "category": "abuse"})
            Qt = R.report_list({"target": "bo"})
            Qr = R.report_list({"reporter": str(U1), "size": "1", "page": "2"})
            check("жалобы стенд (панель): очередь «новые и в работе» — 3, старые первыми; фильтры категория, ник с начала (без учёта регистра), автор и страница",
                  Q["total"] == 3 and [x["id"] for x in Q["rows"]] == sorted(x["id"] for x in Q["rows"]) and Q["counts"]["new"] == 3
                  and Qc["total"] == 1 and Qt["total"] == 1 and Qt["rows"][0]["id"] == rid and Qr["total"] == 3 and Qr["pages"] == 3 and len(Qr["rows"]) == 1
                  and Q["rows"][0]["n_files"] == 3, (Q["total"], Qc["total"], Qt["total"], Qr["total"]))
            X = R.show(rid)
            tg = {(t["uid"], t["idx"], t["deleted"]) for t in X["targets"]}
            K = R.show(c2[1])
            check("жалобы стенд (панель): карточка — цель «bob» → персонаж Bob 9001/10 (логин) и удалённый Bob 9003; кириллический ник Kirill нет, «Кирилл» "
                  "ищется байтами; автор Discord → учётка alicelogin №9100; ссылка по правилам; скриншоты 3 с sha256; другие жалобы автора 2",
                  tg == {(9001, 10, False), (9003, 10, True)} and X["targets"][0]["login"] == "boblogin" and X["reporter"]["uid"] == 9100
                  and X["links"] == [{"url": lnk, "ok": True}] and len(X["files"]) == 3 and X["same_author"]["total"] == 2 and not X["errors"]
                  and K["targets"] == [] and not K["errors"], (tg, X["reporter"], X["errors"], K["errors"]))
            S.submit(U4, "dan#4", form("Кирилл", "abuse"))
            Kr = R.show(R.report_list({"reporter": str(U4)})["rows"][0]["id"])
            check("жалобы стенд (панель): ник по-русски «Кирилл» → персонаж 9002/11 (поиск в Arabic-базе байтами cp1251)",
                  [(t["uid"], t["idx"]) for t in Kr["targets"]] == [(9002, 11)] and Kr["targets"][0]["name"] == "Кирилл", Kr["targets"])
            errs5 = []
            lo = R._target("кирилл", errs5)
            up = R._target("КИРИЛЛ", errs5)
            no = R._target("Кирил", errs5)
            check("р67 Н-5: кириллица без учёта регистра — «кирилл» и «КИРИЛЛ» → «Кирилл» 9002/11, «Кирил» — нет (длина другая)",
                  [(t["uid"], t["idx"]) for t in lo] == [(9002, 11)] == [(t["uid"], t["idx"]) for t in up] and no == [] and not errs5, (lo, up, errs5))
            a.cursor().execute("INSERT adm.PlayerReport (reporter_id, reporter_name, target_name, category, body) VALUES (?, N'dup', N'Старый', 'other', N'давняя открытая жалоба')", U4)
            a.cursor().execute("UPDATE adm.PlayerReport SET created_utc = DATEADD(DAY, -5, SYSUTCDATETIME()) WHERE reporter_name = N'dup'")
            c_old = S.submit(U4, "dan#4", form("СТАРЫЙ", "other"))
            check("р67 М-1: открытая жалоба того же автора на того же персонажа — повтор не создаётся, сколько бы ей ни было (5 суток) — код 3",
                  c_old[0] == 3 and c_old[1], c_old)
            fd = R.file_data(X["files"][0]["id"])
            a.cursor().execute("UPDATE adm.PlayerReportFile SET data = CAST('<svg onload=alert(1)>' AS varbinary(max)) WHERE id = ?", X["files"][1]["id"])
            w_f = _refused(lambda: R.file_data(X["files"][1]["id"]))
            check("жалобы стенд (панель): скриншот — base64 тех же байтов с sha256; подмена байтов в базе — отказ «не совпал с записью»",
                  base64.b64decode(fd["b64"]) == PNG and fd["mime"] == "image/png" and w_f and "не совпал с записью" in w_f, w_f)
            # ---- разбор
            own = ops.Ctx(1, "owner_t", "owner", "", "web")
            adm_ = ops.Ctx(2, "admin_t", "admin", "", "web")
            gm = ops.Ctx(3, "gm_t", "gm", "", "web")
            gm2 = ops.Ctx(4, "gm2_t", "gm", "", "web")
            sup = ops.Ctx(5, "sup_t", "support", "", "web")
            w_sup = _refused(lambda: ops.run(sup, "report.take", {"id": rid}, dry=True))
            pv = ops.run(gm, "report.take", {"id": rid}, dry=True)
            t1 = ops.run(gm, "report.take", {"id": rid, "expect": pv["preview"]["expect"]})
            w_again = _refused(lambda: ops.run(gm2, "report.take", {"id": rid}, dry=True))
            w_mine = _refused(lambda: ops.run(gm, "report.take", {"id": rid}, dry=True))
            w_close2 = _refused(lambda: ops.run(gm2, "report.close", {"id": rid, "outcome": "no_violation", "note": "нет нарушения"}, dry=True))
            w_case_out = _refused(lambda: ops.run(gm, "report.close", {"id": rid, "outcome": "case", "note": "в дело"}, dry=True))
            check("жалобы стенд: report.take — support без права, gm берёт (журнал), второй gm — «уже ведёт», свой повтор — «уже у вас», чужой gm не закрывает, "
                  "итог «в дело» без дела — отказ", w_sup and "reports.handle" in w_sup and t1["ok"] and t1["audit_id"] and w_again and "уже ведёт gm_t" in w_again
                  and w_mine and "уже у вас" in w_mine and w_close2 and "закрыть может он или администратор" in w_close2 and w_case_out
                  and "сначала свяжите" in w_case_out, (w_sup, w_again, w_mine, w_close2, w_case_out))
            w_nocase = _refused(lambda: ops.run(gm, "report.case", {"id": rid, "case": "AC-0099"}, dry=True))
            pvc = ops.run(gm, "report.case", {"id": rid, "case": "ac-0002"}, dry=True)
            pvc1 = ops.run(gm, "report.case", {"id": rid, "case": "AC-0001"}, dry=True)
            rc = ops.run(gm, "report.case", {"id": rid, "case": "AC-0001", "expect": pvc1["preview"]["expect"]})
            w_case2 = _refused(lambda: ops.run(gm, "report.case", {"id": rid, "case": "AC-0002"}, dry=True))
            # р67 М-2: жалобу ведёт gm, дело по ней открыл gm2 — связь проходит с отметкой
            pv_o = ops.run(gm, "report.take", {"id": c3[1]}, dry=True)
            ops.run(gm, "report.take", {"id": c3[1], "expect": pv_o["preview"]["expect"]})
            pvm = ops.run(gm2, "report.case", {"id": c3[1], "case": "AC-0002"}, dry=True)
            rm2 = ops.run(gm2, "report.case", {"id": c3[1], "case": "AC-0002", "expect": pvm["preview"]["expect"]})
            Xm = R.show(c3[1])
            check("р67 М-2: дело по жалобе, которую ведёт другой оператор, связывается с отметкой (предупреждение, «чужая» в журнале), вести продолжает взявший",
                  any("дело будет связано вами" in w for w in pvm["preview"]["warnings"]) and rm2["ok"] and Xm["case_no"] == "AC-0002"
                  and Xm["taken_by"] == "gm_t" and Xm["status"] == "taken", (pvm["preview"]["warnings"], Xm["case_no"], Xm["taken_by"]))
            check("жалобы стенд: report.case — дела нет — отказ, дело чужой учётки — предупреждение, AC-0001 связано (номер у жалобы), второе дело — отказ",
                  w_nocase and "нет в журнале дел" in w_nocase and any("не учётка персонажа" in w for w in pvc["preview"]["warnings"])
                  and not any("не учётка персонажа" in w for w in pvc1["preview"]["warnings"]) and rc["ok"] and R.show(rid)["case"]["found"]
                  and w_case2 and "уже связана с делом AC-0001" in w_case2, (w_nocase, w_case2))
            # отпечаток: администратор видел жалобу «новой», а пока он подтверждал, её взял другой — запись по старому отпечатку не проходит
            pv2 = ops.run(adm_, "report.close", {"id": c2[1], "outcome": "no_violation", "note": "проверено по журналу"}, dry=True)
            a.cursor().execute("UPDATE adm.PlayerReport SET status = 'taken', taken_by = N'other', taken_utc = SYSUTCDATETIME() WHERE id = ?", c2[1])
            w_exp = _refused(lambda: ops.run(adm_, "report.close", {"id": c2[1], "outcome": "no_violation", "note": "проверено по журналу",
                                                                    "expect": pv2["preview"]["expect"]}))
            pva = ops.run(adm_, "report.close", {"id": c2[1], "outcome": "no_violation", "note": "проверено по журналу"}, dry=True)
            ca = ops.run(adm_, "report.close", {"id": c2[1], "outcome": "no_violation", "note": "проверено по журналу", "expect": pva["preview"]["expect"]})
            cc = ops.run(gm, "report.close", {"id": rid, "outcome": "case", "note": "передано в AC-0001"})
            w_closed = _refused(lambda: ops.run(own, "report.close", {"id": rid, "outcome": "action", "note": "ещё раз"}, dry=True))
            check("жалобы стенд: отпечаток — жалобу взяли после предпросмотра — отказ; admin закрывает чужую взятую с предупреждением; итог «в дело» после "
                  "связи; закрытую повторно не закрыть", w_exp and "изменилась с предпросмотра" in w_exp and ca["ok"]
                  and any("вёл other" in w for w in pva["preview"]["warnings"]) and cc["ok"] and w_closed and "уже закрыта" in w_closed, (w_exp, w_closed))
            # ---- ответ автору через бота
            r1 = ops.run(gm, "report.reply", {"id": rid, "text": "Спасибо!\nМеры приняты."})
            got = S.claim()
            retry = S.claim()                     # р67 Н-4: ответ захвата «потерялся» — тот же номер вернёт те же строки
            d1 = S.done(got[0]["id"], True, "отправлено")
            S.claimed_ok()
            again = S.claim()
            d2 = S.done(got[0]["id"], False, "повтор")
            S.claimed_ok()
            check("р67 Н-4: захват ответа — повтор тем же номером (сбой по дороге) возвращает ту же строку, после итога и нового номера — ничего; "
                  "доставка ровно одна", [x["id"] for x in retry] == [x["id"] for x in got] and len(got) == 1, (got, retry))
            msg = B.reply_message(got[0]["report_id"], got[0]["category"], got[0]["target"], got[0]["text"])
            st1 = R.show(rid)["replies"][0]
            check("жалобы стенд: ответ — операция ставит строку, бот забирает её ОДИН раз (Discord ID автора, текст оператора), итог пишется один раз; в карточке "
                  "— «отправлено»; сообщение автору — номер жалобы и текст как есть",
                  r1["ok"] and len(got) == 1 and got[0]["reporter_id"] == U1 and got[0]["text"] == "Спасибо!\nМеры приняты." and again == [] and d1 == 1 and d2 == 0
                  and st1["state"] == "sent" and "#%d" % rid in msg and "Меры приняты." in msg, (got, st1))
            ops.run(gm, "report.reply", {"id": rid, "text": "второй"})
            B.Store(connect=_AsBot).claim()       # другой процесс бота взял и упал (номер захвата потерян вместе с ним)
            a.cursor().execute("UPDATE adm.PlayerReportReply SET claimed_utc = DATEADD(MINUTE, -%d, SYSUTCDATETIME()) WHERE status = 1" % (R.STUCK_MIN + 1))
            st2 = R.show(rid)["replies"][1]
            for i in range(3):
                ops.run(gm, "report.reply", {"id": rid, "text": "ответ %d" % i})
            w_many = _refused(lambda: ops.run(gm, "report.reply", {"id": rid, "text": "шестой"}, dry=True))
            a.cursor().execute("INSERT adm.PlayerReportReply (report_id, text, by_login) SELECT ?, N'x', N'gm2_t' FROM (SELECT TOP (%d) 1 AS x FROM sys.all_objects) v"
                               % R.REPLIES_PER_HOUR, Kr["id"])
            w_hour = _refused(lambda: ops.run(gm2, "report.reply", {"id": c3[1], "text": "ещё"}, dry=True))
            check("жалобы стенд: бот взял и не отчитался дольше %d мин — «неизвестно» (повторно не берётся); 6-й ответ на жалобу — отказ; %d ответов оператора "
                  "за час — отказ" % (R.STUCK_MIN, R.REPLIES_PER_HOUR), st2["state"] == "unknown" and S.claim() != [] and w_many and "больше нельзя" in w_many
                  and w_hour and "предел %d в час" % R.REPLIES_PER_HOUR in w_hour, (st2["state"], w_many, w_hour))
            # р67 С-2: срок хранения — закрытая жалоба rid «закрыта 91 сутки назад», c2 — вчера: байты только у первой
            a.cursor().execute("UPDATE adm.PlayerReport SET closed_utc = DATEADD(DAY, -91, SYSUTCDATETIME()) WHERE id = ?", rid)
            u0 = R.db_usage()
            pp = ops.run(own, "reports.purge", {}, dry=True)
            pr = ops.run(ops.Ctx(None, "service:daily", "owner", "", "sched"), "reports.purge", {})
            pr2 = ops.run(own, "reports.purge", {}, dry=True)
            u1 = R.db_usage()
            Xp = R.show(rid)
            w_p = _refused(lambda: R.file_data(Xp["files"][0]["id"]))
            meta = a.cursor().execute("SELECT COUNT(*), SUM(DATALENGTH(data)), SUM(size_bytes), COUNT(sha256) FROM adm.PlayerReportFile WHERE report_id = ?", rid).fetchone()
            check("р67 С-2: reports.purge — байты 3 скриншотов закрытой 91 сутки назад жалобы удалены (размер, sha256 и имя остались), повтор — 0; показ — "
                  "отказ «удалён по сроку»; db_usage — размер базы и доля скриншотов",
                  "3 скриншотов" in pp["preview"]["text"] and pr["ok"] and "2 скриншотов" not in pr["message"] and "0 скриншотов" in pr2["preview"]["text"]
                  and meta[0] == 3 and meta[1] == 0 and meta[2] > 0 and meta[3] == 3 and all(f["purged"] for f in Xp["files"])
                  and w_p and "удалён по сроку хранения" in w_p and u0["db_mb"] > 0 and u0["shots_purged"] == 0 and u1["shots_purged"] == 3 and u1["shots_n"] == u0["shots_n"]
                  and not u0.get("error"), (pp["preview"]["text"], pr["message"], meta, u0, u1, w_p))
            aud = {r[0]: r[1] for r in a.cursor().execute("SELECT action, COUNT(*) FROM adm.audit WHERE action LIKE 'report.%' AND result = 'ok' GROUP BY action")}
            ref = a.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action LIKE 'report.%' AND result = 'refused'").fetchone()[0]
            fq, _p = _route("/api/reports/show")

            class _Req:
                def __init__(self, query, role):
                    self.query, self.session = dict(query), {"user": {"role": role, "login": "t_" + role}}
            rs = fq(_Req({"id": str(rid)}, "gm"), None)
            fl, _p2 = _route("/api/reports/list")
            rm = fl(_Req({"mine": "1", "mine_login": "x"}, "gm"), None)
            check("жалобы стенд: журнал adm.audit — take 2, case 2, close 2, reply 5 (ok) и отказы; API — карточка с правами роли, «мои» — по входу, "
                  "а не по параметру", aud == {"report.take": 2, "report.case": 2, "report.close": 2, "report.reply": 5} and ref >= 1
                  and rs["can"]["reports.handle"] and rs["can"]["ac.case"] and rs["can"]["players.view_net"] and rm["total"] == 0, (aud, ref))
        finally:
            db.set_override("game", None)
            db.set_override("admin", None)
            discordlinks.links = links0
    finally:
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def live(check):
    """Только чтение живой dev и службы на сервере; жалоб и ответов не создаёт."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db
    import domains
    domains.load_all()
    from domains import reports as R
    if config.get().on_server:
        return check("живой самотест А6.11 «жалобы» — с ПК", True)
    cn = db.admin()
    try:
        q = lambda o, perm, col=None: db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?%s) AS p" % (", ?, 'COLUMN'" if col else ""),
                                                    (o, perm, col) if col else (o, perm))[0]["p"]
        perm = {"sel": q("adm.PlayerReport", "SELECT"), "upd_status": q("adm.PlayerReport", "UPDATE", "status"), "upd_body": q("adm.PlayerReport", "UPDATE", "body"),
                "ins": q("adm.PlayerReport", "INSERT"), "del": q("adm.PlayerReport", "DELETE"), "file_sel": q("adm.PlayerReportFile", "SELECT"),
                "file_ins": q("adm.PlayerReportFile", "INSERT"), "rep_ins": q("adm.PlayerReportReply", "INSERT"), "rep_upd": q("adm.PlayerReportReply", "UPDATE"),
                "submit": q("adm.ReportSubmit", "EXECUTE")}
    finally:
        cn.close()
    check("живое (asda_admin): жалобы — чтение, UPDATE только столбцов разбора, ответ — INSERT, без удаления и без процедур бота",
          perm == {"sel": 1, "upd_status": 1, "upd_body": 0, "ins": 0, "del": 0, "file_sel": 1, "file_ins": 0, "rep_ins": 1, "rep_upd": 0, "submit": 0}, perm)
    B = _bot()
    S = B.Store()
    try:
        c = S._cn()
        try:
            rows = c.cursor().execute(open(os.path.join(ROOT, "sql", "adminc_23_reports_verify.sql"), encoding="utf-8").read()).fetchall()
        finally:
            c.close()
        bad = [tuple(r) for r in rows if int(r[1] or 0) != int(r[2])]
        check("живое (путь бота, р67 Н-2): пароль asda_reports из reports.env рядом с ботом (без SSH), вход по VPN, права = adminc_23_reports_verify (%d проверок)"
              % len(rows), len(rows) == 19 and not bad, bad)
    except Exception as ex:
        check("живое (путь бота): вход asda_reports по VPN", False, "%s: %s" % (type(ex).__name__, str(ex)[:200]))
    L = R.report_list({"status": "all", "size": "200"})
    check("живое: очередь жалоб читается (всего %d: новых %d, в работе %d, закрытых %d)" % (L["total"], L["counts"]["new"], L["counts"]["taken"], L["counts"]["closed"]),
          L["total"] == sum(L["counts"].values()))
    if L["rows"]:
        X = R.show(L["rows"][0]["id"])
        ok = not X["errors"]
        if X["files"]:
            fd = R.file_data(X["files"][0]["id"])
            ok = ok and len(base64.b64decode(fd["b64"])) == X["files"][0]["size"]
        check("живое: карточка последней жалобы №%d (цель, автор, скриншот) без ошибок" % X["id"], ok, X["errors"])
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import reports as R\nL = R.report_list({'status': 'all'})\n"
             "print('RPPROBE total=%d' % L['total'])\n")
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
    mm = re.search(r"RPPROBE total=(\d+)", out)
    check("служба на сервере (SSH): очередь жалоб читается, жалоб столько же, сколько с ПК", bool(mm) and int(mm.group(1)) == L["total"], out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/reports/list" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/reports/list без входа — 401", code == 401, code)
