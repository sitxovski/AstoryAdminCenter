# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_outbox_a7.py — самотест шага А7.4 «Очередь исходящих + Discord» (23.11.2026; решение владельца А7 №2 — в Discord только по флажку
«и в Discord» в форме объявления; domains/outbox.py, domains/live.py (live.announce + discord), domains/stack.py (job.add), sql/adminc_28_outbox.sql
и adminc_28_outbox_verify.sql, /api/outbox, web/outbox.js, web/app.js announceAll; бот — AstoryAdminCenter/DiscordBot/outbox_bot.py и
test_outbox_bot.py).

НИ ОДИН ПРОГОН НЕ ПУБЛИКУЕТ В DISCORD: офлайн и стенд — бот с подставным адаптером Discord (записывает вызовы, сети нет); живой — только
проверочная запись (kind test: бот её отмечает «тест» без вызова Discord) и захват только проверочных (@test_only = 1).

offline(check)  — права (outbox.view, community.post — owner, admin; community.delete — owner; gm и support — нет), операции outbox.* без
                  отката, маршрут, белые списки панели = бота = CHECK таблицы, сборка текста панели = бота, отказы полей «и в Discord» (право,
                  канал, роль, @everyone / @here, <@…>, длины, срок, 2000 знаков), окно job.add, тексты без «; », переводы EN, веб (без innerHTML,
                  флажок только с community.post), adminc_28 (уровень 100, права), проверка под asda_reports, adminc_10 / 99, выкладка,
                  импорт без побочных эффектов, модульные тесты бота.
sandbox(check, ldb) — СВОЯ база LocalDB: adminc_02 + adminc_23 + adminc_28 дважды; бот — НАСТОЯЩИЙ outbox_bot.Store под EXECUTE AS USER
                  asda_reports и Worker с подставным адаптером: live.announce + discord (запись «ждёт игры» → боту), сбой объявления в игру —
                  запись отменена, пределы частоты, публикация один раз (повтор после «итог неизвестен» не публикует), просрочка, проверочная
                  запись без Discord, отмена, удаление владельцем, права asda_reports, CHECK @everyone, журнал adm.audit, маршрут.
live(check)     — живая dev: права asda_admin на adm.Outbox*, путь бота (пароль из reports.env, вход asda_reports по VPN = adminc_28_outbox_verify),
                  очередь читается, проверочная запись → захват ТОЛЬКО проверочных до «бот взял» → отметка «тест» (Discord не вызывается), служба
                  на сервере (SSH) читает ту же очередь, без входа — 401.
Побочных эффектов при импорте нет.
"""
import ast
import asyncio
import datetime
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


DC = {"channel": "announcements", "role": "news", "en": "Server restart at 18:00 UTC", "ru": "Рестарт сервера в 18:00 UTC", "ar": "إعادة تشغيل الخادم", "ttl": 60}


def offline(check):
    _paths()
    from core import auth, i18n, ops
    import domains
    domains.load_all()
    from domains import outbox as O
    import outbox_bot as B
    roles = ("owner", "admin", "gm", "support")
    who = lambda p: {r for r in roles if auth.can(r, p)}
    check("очередь Discord: права outbox.view и community.post — owner, admin; community.delete — только owner; gm и support — ничего (публикация "
          "видна всему серверу Discord)", who("outbox.view") == who("community.post") == {"owner", "admin"} and who("community.delete") == {"owner"})
    reg = ops.REGISTRY
    check("очередь Discord: операции outbox.cancel / retry / test — под community.post, outbox.delete — под community.delete, все без отката; "
          "live.announce — прежнее право server.announce",
          all(reg[n].perm == "community.post" and not reg[n].reversible for n in ("outbox.cancel", "outbox.retry", "outbox.test"))
          and reg["outbox.delete"].perm == "community.delete" and not reg["outbox.delete"].reversible and reg["live.announce"].perm == "server.announce")
    fn, perm = _route("/api/outbox")
    check("очередь Discord: маршрут GET /api/outbox — право outbox.view", fn is not None and perm == "outbox.view")
    sql = _read(ROOT, "sql", "adminc_28_outbox.sql")
    chk_ch = set(re.search(r"CK_adm_Outbox_channel CHECK \(channel_key IN \(([^)]*)\)\)", sql).group(1).replace("'", "").replace(" ", "").split(","))
    chk_rl = set(re.search(r"CK_adm_Outbox_role CHECK \(role_key IN \(([^)]*)\)\)", sql).group(1).replace("'", "").replace(" ", "").split(","))
    check("белые списки: каналы панели = бота = CHECK adm.Outbox (announcements, updates, test-info), роли = бота = CHECK (news, patch, playtest), "
          "запрещённые @everyone / @here, порядок языков — одни и те же",
          set(O.CHANNELS) == set(B.CHANNELS) == chk_ch == {"announcements", "updates", "test-info"}
          and set(O.ROLES) - {""} == set(B.ROLES) == chk_rl == {"news", "patch", "playtest"} and O.FORBIDDEN == B.FORBIDDEN and O.LANGS == B.LANGS
          and B.CHANNELS["updates"][1] == ("forum",) and B.CHANNELS["test-info"][1] == ("text",), (chk_ch, chk_rl))
    samples = [("<@&1111111111111111301>", "a", "б", "ج"), ("", "only en", "", ""), ("@News Ping", " x ", None, "y")]
    check("сборка сообщения: панель (предпросмотр) = бот (публикация) — флаги EN, AR, RU, пустые языки пропущены",
          all(O.compose(*s) == B.compose(*s) for s in samples) and O.compose("", "a", "", "c") == "🇬🇧 a\n🇸🇦 c")
    own, adm, gm = ops.Ctx(1, "o", "owner", "", "web"), ops.Ctx(2, "a", "admin", "", "web"), ops.Ctx(3, "g", "gm", "", "web")
    ok = O.check(adm, DC, "Рестарт в 18:00")
    bad = {k: _refused(lambda d=d, c=c, t=t: O.check(c, d, t)) for k, (c, d, t) in {
        "gm": (gm, DC, "x"), "obj": (own, "x", "x"), "chan": (own, dict(DC, channel="general"), "x"), "role": (own, dict(DC, role="everyone"), "x"),
        "role2": (own, dict(DC, role="Beta Tester"), "x"), "every": (own, dict(DC, en="hi @everyone"), "x"), "here": (own, dict(DC, ru="все @HERE"), "x"),
        "title": (own, DC, "@here go"), "mention": (own, dict(DC, ar="<@123456>"), "x"), "chm": (own, dict(DC, en="see <#105>"), "x"),
        "noen": (own, dict(DC, en="  "), "x"), "long": (own, dict(DC, en="x" * 1801), "x"), "ttl0": (own, dict(DC, ttl=4), "x"),
        "ttl1": (own, dict(DC, ttl=1441), "x"), "ttlx": (own, dict(DC, ttl="abc"), "x"), "notitle": (own, DC, ""),
        "total": (own, dict(DC, en="x" * 1000, ru="y" * 990), "x"), "ctrl": (own, dict(DC, en="a\x07b"), "x")}.items()}
    check("«и в Discord»: годные поля → канал, роль, тексты, срок; отказы — gm (нет community.post), не объект, канал и роль не из списка (в т.ч. "
          "everyone, Beta Tester), @everyone / @here в любом тексте и заголовке, <@…> и <#…>, пустой EN, > 1800, срок вне 5…1440 и не число, пустой "
          "заголовок, сообщение > 2000, управляющие символы",
          ok == {"channel": "announcements", "role": "news", "en": DC["en"], "ru": DC["ru"], "ar": DC["ar"], "ttl": 60, "title": "Рестарт в 18:00"}
          and all(bad.values()) and "community.post" in bad["gm"] and "@everyone" in bad["every"] and "2000" in bad["total"], bad)
    la = reg["live.announce"]
    s1 = _refused(lambda: la.schedule_check(gm, {"text": "x", "discord": DC}))
    s2 = la.schedule_check(adm, {"text": "Рестарт", "discord": DC})
    check("live.announce.schedule_check: «и в Discord» проверяется и при постановке в задание (без права — отказ), без флажка — как раньше",
          s1 and "community.post" in s1 and s2 == ("Рестарт", [255, 255, 255]) and la.schedule_check(gm, {"text": "x"}) == ("x", [255, 255, 255]))
    at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()
    jp = None
    try:
        jp = ops.run(own, "job.add", {"op": "live.announce", "at": at, "params": {"text": "Рестарт", "discord": dict(DC, channel="updates")}}, dry=True)["preview"]
    except Exception as ex:
        jp = {"warnings": [repr(ex)]}
    w = "\n".join(jp.get("warnings") or [])
    check("job.add (live.announce + discord): в окне подтверждения — канал, роль, срок, имя ветки форума и сам текст Discord",
          "и в Discord: форум updates — новая ветка, роль News Ping, срок годности 60 мин" in w and "имя новой ветки — «Рестарт»" in w
          and "текст в Discord:\n@News Ping\n🇬🇧 Server restart" in w, w[:600])
    # ---- ★ ревизия 76
    w_rep = {r: _refused(lambda r=r: ops.run(own, "job.add", {"op": "live.announce", "at": at, "repeat": r, "params": {"text": "Рестарт", "discord": DC}},
                                             dry=True)) for r in ("daily", "weekly")}
    w_rep0 = _refused(lambda: ops.run(own, "job.add", {"op": "live.announce", "at": at, "repeat": "daily", "params": {"text": "Рестарт"}}, dry=True))
    check("р76 К4: задание live.announce с «и в Discord» — только разовое (daily / weekly — понятный отказ), без флажка повтор — как раньше",
          all(v == O.REPEAT_REFUSED for v in w_rep.values()) and w_rep0 is None, (w_rep, w_rep0))
    dm = O.describe(O.check(own, dict(DC, en="see https://Discord.gg/abc and http://evil.example:8080/x [x](https://a.b/c)"), "t"))
    check("р76 К5: предпросмотр называет домены ссылок (discord.gg, evil.example, a.b), превью ссылок бот отключает (suppress_embeds)",
          any(x == "ссылки в тексте ведут на: discord.gg, evil.example, a.b (превью ссылок в Discord отключено)" for x in dm), dm)
    long16 = _refused(lambda: O.check(own, dict(DC, en="😀" * 1000, ru="", ar=""), "t"))
    check("р76 К7: длина сообщения — в единицах UTF-16 (как у бота): 1000 эмодзи (≈1013 кодовых точек, 2013 UTF-16) — отказ «> 2000»",
          long16 and "2000" in long16 and O.dlen("🇬🇧") == B.dlen("🇬🇧") == 4, long16)
    # ---- тексты и переводы
    texts = [O.NOT_INSTALLED, O.REPEAT_REFUSED, "ссылки в тексте ведут на: a.b (превью ссылок в Discord отключено)",
             "id сообщения не совпадают с журналом бота — не удаляю", "сообщение опубликовал не этот бот — не удаляю",
             "итог неизвестен: журнал бота не знает эту запись, а попыток уже 2 — проверьте канал в Discord, повторно бот эту запись не публикует"] + list(O.PUT_CODES.values()) + O.describe(dict(ok, channel="updates", ru="")) + list(bad.values()) + [
        "объявление на GameServer, Ch2_GameServer: «Рестарт»\nи в Discord:\n" + O.preview_text(ok), "текст в Discord:\n" + O.preview_text(ok),
        "срок годности и пределы частоты считаются в момент запуска задания", "очередь Discord не прочитана: x", "записи очереди Discord №5 нет",
        "номер записи — целое от 1", "запись №5 уже не ждёт публикации (posted) — отменить нельзя", "отменить запись очереди Discord №5 (announcements, «x») — в Discord она не уйдёт",
        "пишется только база панели AsdaAdmin (adm.Outbox): статус «отменено»", "запись №5 уже взята ботом или изменилась — откройте очередь заново",
        "запись очереди Discord №5 отменена", "запись №5 не в ошибке и не «итог неизвестен» (queued) — повторять нечего",
        "у записи №5 уже 5 попыток — больше нельзя, поставьте объявление заново", "срок годности записи №5 прошёл — поставьте объявление заново",
        "бот возьмёт запись снова в течение 30 с, если он запущен",
        "бот взял запись и не отчитался — если сообщение уже есть в Discord, бот его не повторит (номер есть в журнале бота на ПК)",
        "повторить запись очереди Discord №5 (updates, Patch Ping, «x») (попытка 2 из 5)",
        "запись №5 уже нельзя повторить (статус изменился, срок или попытки) — откройте очередь заново", "запись очереди Discord №5 поставлена на повтор",
        "запись №5 не опубликована — удалять в Discord нечего", "удаление записи №5 уже поставлено (queued)", "удалить из Discord опубликованное сообщение №5 (updates, «x»)",
        "у форума updates удаляется ветка целиком (вместе с ответами в ней)",
        "отката нет: сообщение исчезнет из Discord у всех, вернуть его можно только новым объявлением",
        "удаляет бот Oracle на ПК владельца в течение 30 с, если он запущен — итог виден в очереди",
        "удаление записи №5 уже поставлено или она изменилась — откройте очередь заново", "удаление сообщения Discord по записи №5 поставлено боту",
        "поставить проверочную запись в очередь Discord — бот её заберёт и отметит «тест», в Discord ничего не уйдёт",
        "пишется только база панели AsdaAdmin (adm.Outbox, запись с отметкой «тест»)", "проверочная запись очереди Discord №5 поставлена",
        "запись №5 ждёт бота дольше 5 мин — запущен ли бот Oracle на ПК владельца",
        "запись №5: бот взял её и не отчитался дольше 10 мин — проверьте канал в Discord, потом «повторить» или «отменить»",
        "запись №5: объявление в игру не подтвердилось за 10 мин — в Discord она не уйдёт, её можно отменить", "неверный фильтр (можно: all, active)",
        "разослано на 2 узл. · в Discord: запись очереди №5 (публикует бот на ПК)",
        "разослано на 1 узл. (не вышло: GameServer: x) · в Discord НЕ отпущено: запись очереди №5 изменилась (её отменили?)",
        "разослано на 1 узл. · в Discord НЕ отпущено: запись очереди №5 не обновилась (DbError)",
        "объявление в игру не разослано: нет ни одного GameServer с мостом в режиме исполнения (Mode=1)",
        "просрочено: бот не забрал запись до срока годности", "просрочено: срок годности прошёл до публикации",
        "итог неизвестен: бот начал публикацию и прервался — проверьте канал в Discord, повторно бот эту запись не публикует",
        "канал «general» не из белого списка бота", "роль «everyone» не из белого списка бота", "в тексте @everyone или @here — бот это не публикует",
        "в тексте упоминание <@…> или <#…> — бот это не публикует", "нет текста EN", "нет заголовка",
        "канал «announcements»: на сервере Discord найдено 2 подходящих (нужен ровно один)", "роль «news»: на сервере Discord найдено 0 (нужна ровно одна)",
        "сообщение длиннее 2000 знаков", "канал 5 пропал", "сбой связи с Discord (TimeoutError) — итог неизвестен",
        "сбой связи с Discord (TimeoutError) — итог неизвестен — проверьте канал в Discord, повторно бот эту запись не публикует",
        "удалено", "уже удалено", "нет id сообщения", "канал сообщения не из белого списка бота — не удаляю"] + [o.title for n, o in reg.items() if n.startswith("outbox.")]
    check("очередь Discord: тексты отказов, предупреждений, итогов и ошибок бота без «; »", all("; " not in t for t in texts), [t for t in texts if "; " in t])
    i18n.set_lang("en")
    oper = lambda s: s.replace(DC["ru"], "").replace("Рестарт в 18:00", "").replace("Рестарт", "")    # текст оператора остаётся как есть
    try:
        miss = [(t, i18n.tr(t)) for t in texts if CYR.search(oper(i18n.tr(t)))]
    finally:
        i18n.set_lang("ru")
    check("очередь Discord EN: отказы, предупреждения, итоги и ошибки бота — без русских слов (%d строк; текст оператора — как есть)" % len(texts),
          not miss, miss[:6])
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("очередь Discord: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "outbox.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    a0 = app[app.index("async function announceAll"):app.index("// ---------- Игроки: список всех")]
    check("веб: раздел #/outbox с правом outbox.view, viewOutbox(my), скрипт после crashes.js; без innerHTML, данные записей — acText (не T()); "
          "действия — по правам роли; announceAll: флажок «и в Discord» только с community.post, поля канал / роль / EN / RU / AR / срок → params.discord, "
          "предпросмотр (dry) до постановки — и сейчас, и заданием",
          '["#/outbox", "Очередь Discord", "outbox.view"' in app and 'case "outbox": return viewOutbox(my);' in app
          and 0 < idx.index("/crashes.js") < idx.index("/outbox.js") and "innerHTML" not in js and "innerHTML" not in a0
          and "T(x.title" not in js and "T(x.preview" not in js and "T(x.error" not in js and 'can["community.delete"] ? h("button"' in js
          and 'can("community.post") ? [h("label"' in a0 and "params.discord = { channel: dch.value, role: drole.value, en: den.value, ru: dru.value, ar: dar.value, ttl: dttl.value }" in a0
          and 'announceRun("job.add"' in a0 and 'announceRun("live.announce", params)' in a0 and "await op(name, params, true)" in a0)
    q = re.compile(r'"((?:[^"\\]|\\.)*)"')
    labels = {x for x in q.findall(js) if CYR.search(x)} | {x for x in q.findall(a0) if CYR.search(x)} | {"Очередь Discord"}
    have = set(re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(labels - have)
    check("веб EN: у русских строк раздела и формы есть перевод в web/i18n.js (%d строк)" % len(labels), not lack, lack[:8])
    keys_all = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А7.4 (23.11): «Очередь Discord»"):]
    dup = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys_all.count(x) > 1})
    check("веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("outbox.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("очередь Discord: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("очередь Discord: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- SQL, проверки прав, выкладка
    bs = _batches(sql)
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    body = re.sub(r"--[^\n]*", "", body)
    g_rep = sorted(re.findall(r"GRANT EXECUTE ON (adm\.\w+)\s+TO \[asda_reports\]", body))
    g_adm = sorted(re.findall(r"GRANT (\w+) ON (adm\.\w+)\s+TO \[asda_admin\]", body))
    check("adminc_28: QUOTED_IDENTIFIER ON отдельным батчем до CREATE, уровень 100 (нет THROW, IIF, CONCAT, TRY_CONVERT, FORMAT, STRING_SPLIT, "
          "CREATE OR ALTER), бот asda_reports — EXECUTE четырёх процедур бота и DENY таблицы и процедур панели; asda_admin — SELECT и пять процедур "
          "панели, DENY прямой записи и процедур бота; CHECK @everyone / @here",
          bs[0].strip().endswith("SET QUOTED_IDENTIFIER ON;") and "CREATE TABLE" not in bs[0]
          and not re.search(r"\b(TRY_CONVERT|TRY_CAST|IIF|FORMAT|THROW|STRING_SPLIT|ISJSON|OPENJSON|CONCAT|STRING_AGG)\b|CREATE OR ALTER", body)
          and g_rep == ["adm.OutboxClaim", "adm.OutboxDelClaim", "adm.OutboxDelDone", "adm.OutboxDone"]
          and g_adm == sorted([("SELECT", "adm.Outbox")] + [("EXECUTE", "adm.Outbox" + p) for p in ("Put", "Release", "Cancel", "Retry", "Delete")])
          and "DENY  SELECT, INSERT, UPDATE, DELETE ON adm.Outbox TO [asda_reports]" in body and "DENY  INSERT, UPDATE, DELETE ON adm.Outbox TO [asda_admin]" in body
          and all("DENY  EXECUTE ON adm.Outbox%s" % p in body for p in ("Claim    TO [asda_admin]", "Put      TO [asda_reports]"))
          and "NOT LIKE N'%@everyone%'" in body, (g_rep, g_adm))
    ver = _read(ROOT, "sql", "adminc_28_outbox_verify.sql")
    check("adminc_28_outbox_verify: 15 проверок ПОД asda_reports (4 процедуры бота — 1; таблица, процедуры панели, журнал, sysadmin — 0)",
          ver.count("UNION ALL SELECT") + 1 == 15 and len(re.findall(r",\s*1(?: AS want)?;?\s*$", ver, re.M)) == 4)
    v10, v99 = _read(ROOT, "sql", "adminc_10_verify.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    check("выкладка: adminc_28 -x -I в AsdaAdmin после adminc_23 и adminc_27, проверка ПОД asda_reports (adminc_28_outbox_verify, 15); adminc_10 — "
          "SELECT / процедуры панели = 1, INSERT / процедуры бота = 0; adminc_99 — откат шага",
          "Run 'adminc_28_outbox.sql' 'AsdaAdmin' -xi" in dep and dep.index("Run 'adminc_23_reports.sql'") < dep.index("Run 'adminc_28_outbox.sql'")
          and dep.index("Run 'adminc_27_crashes.sql'") < dep.index("Run 'adminc_28_outbox.sql'") < dep.index("adminc_10_verify.sql') 2>&1")
          and "adminc_28_outbox_verify.sql" in dep and '("asda_reports/outbox", part_outbox, 15)' in dep
          and "'adm.Outbox SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.Outbox','OBJECT','SELECT'), 1" in v10
          and "'adm.Outbox INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.Outbox','OBJECT','INSERT'), 0" in v10
          and "'adm.OutboxClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxClaim','OBJECT','EXECUTE'), 0" in v10
          and "'adm.OutboxDelClaim EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxDelClaim','OBJECT','EXECUTE'), 0" in v10
          and "'adm.OutboxDelDone EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.OutboxDelDone','OBJECT','EXECUTE'), 0" in v10
          and (v99 is None or "adminc_28_outbox.sql" in v99))
    ok_top = True
    for src in (_read(ROOT, "domains", "outbox.py"), _read(BOT, "outbox_bot.py")):
        tree = ast.parse(src)
        ok_top &= {type(n).__name__ for n in tree.body} <= {"Expr", "Import", "ImportFrom", "Assign", "FunctionDef", "AsyncFunctionDef", "ClassDef"}
    code = _read(ROOT, "domains", "outbox.py")
    check("импорт domains/outbox и outbox_bot без побочных эффектов (верхний уровень — импорты, константы, функции, классы); в панели нет прямой "
          "записи в adm.Outbox (только процедуры)", ok_top and not re.findall(r"\b(INSERT|UPDATE|DELETE)\s+adm\.Outbox", code) and "EXEC adm.OutboxPut" in code)
    py = sys.executable
    try:
        r = subprocess.run([py, "-I", os.path.join(BOT, "test_outbox_bot.py")], capture_output=True, timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        n = re.search(r"Ran (\d+) tests", out)
        check("бот: модульные тесты очереди test_outbox_bot.py (%s тестов) — Discord подменён, сети нет" % (n.group(1) if n else "?"),
              r.returncode == 0 and n and "OK" in out, out[-400:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("бот: модульные тесты очереди (не запустились)", False, str(ex))


class _FakeAdapter:
    """Подставной Discord: записывает вызовы, ничего не отправляет."""

    def __init__(self):
        self.posts, self.deletes = [], []

    def channels(self):
        return [(101, "📣┃announcements", "news"), (103, "updates", "forum"), (104, "📋┃test-info", "text"), (105, "general", "text")]

    def roles(self):
        return [(201, "📢 News Ping"), (202, "⚙️ Patch Ping"), (203, "🧪 Playtest Ping")]

    async def post(self, channel_id, kind, title, content, role_id, oid):
        self.posts.append((channel_id, kind, title, content, role_id))
        if kind == "forum":                       # у ветки форума id первого сообщения = id ветки
            return 9000 + channel_id, 9000 + channel_id
        return channel_id, 500 + len(self.posts)

    async def find_threads(self, forum_id, title, minutes):
        return []

    async def is_ours(self, channel_id, message_id, forum):
        return True

    async def parent_of(self, thread_id):
        return thread_id - 9000

    async def delete(self, channel_id, message_id, forum):
        self.deletes.append((channel_id, message_id, forum))
        return "удалено"


def sandbox(check, ldb):
    """Своя база LocalDB: панель (операции) → бот (настоящий outbox_bot.Store под asda_reports, Worker с подставным Discord)."""
    _paths()
    from core import bridge, db, ops
    import domains
    domains.load_all()
    from domains import outbox as O
    import outbox_bot as B
    name = "AsdaOutbox_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    saved = (bridge.nodes, bridge.enqueue, bridge.wait)
    tmp = tempfile.TemporaryDirectory()
    try:
        a = ldb(name)
        s23 = _read(ROOT, "sql", "adminc_23_reports.sql").replace("$(ReportsPw)", "Aa1-" + secrets.token_hex(12))
        s28 = _read(ROOT, "sql", "adminc_28_outbox.sql")
        for b in _batches(_read(ROOT, "sql", "adminc_02_schema.sql")) + _batches(s23) + _batches(s28) + _batches(s28):
            a.cursor().execute(b)
        check("стенд: настоящие adminc_02 + adminc_23 + adminc_28 дважды (повтор безопасен), таблица и 9 процедур adm.Outbox*",
              a.cursor().execute("SELECT COUNT(*) FROM sys.procedures WHERE name LIKE 'Outbox%'").fetchone()[0] == 9)
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
        for qq in ("SELECT COUNT(*) FROM adm.Outbox", "UPDATE adm.Outbox SET status = 2",
                   "DECLARE @i INT, @c INT; EXEC adm.OutboxPut 'announce', 'announcements', NULL, N't', N'e', NULL, NULL, 60, N'x', 0, @i OUTPUT, @c OUTPUT",
                   "EXEC adm.OutboxCancel 1, N'x'", "SELECT COUNT(*) FROM adm.audit"):
            try:
                cur = cb.cursor().execute(qq)
                if qq.startswith("SELECT"):
                    cur.fetchall()
                deny.append(qq[:40])
            except Exception:
                pass
        cb.close()
        check("стенд: asda_reports — ни чтения и записи adm.Outbox, ни процедур панели, ни журнала (только процедуры бота)", not deny, deny)
        S = B.Store(connect=_AsBot)
        st = lambda oid: a.cursor().execute("SELECT status, attempts, error, discord_channel_id, discord_message_id, del_status FROM adm.Outbox WHERE id = ?",
                                            oid).fetchone()
        own, adm, gm = ops.Ctx(None, "own_t", "owner", "", "web"), ops.Ctx(None, "adm_t", "admin", "", "web"), ops.Ctx(None, "gm_t", "gm", "", "web")
        calls = {"wait": 2}
        bridge.nodes = lambda: [{"node": "GameServer", "fresh": True, "mode": 1}]
        bridge.enqueue = lambda *a_, **k: (777, None)
        bridge.wait = lambda cid, t: {"status": calls["wait"], "result": "ok"}
        ad = _FakeAdapter()
        W = B.Worker(S, ledger=B.Ledger(os.path.join(tmp.name, "ledger.json")), limiter=B.Limiter(gap=0, per_hour=1000))
        tick = lambda: asyncio.run(W.tick(ad))
        pv = ops.run(adm, "live.announce", {"text": "Рестарт в 18:00", "discord": DC}, dry=True)["preview"]
        n0 = a.cursor().execute("SELECT COUNT(*) FROM adm.Outbox").fetchone()[0]
        r1 = ops.run(adm, "live.announce", {"text": "Рестарт в 18:00", "discord": DC})
        oid = r1["result"]["discord"]["outbox"]
        s1 = st(oid)
        check("стенд: live.announce + discord — предпросмотр ничего не пишет и показывает сообщение (@News Ping, флаги); после объявления в игру запись "
              "отпущена боту (статус 0), в итоге — номер записи",
              n0 == 0 and "и в Discord:\n@News Ping\n🇬🇧 Server restart at 18:00 UTC\n🇸🇦 " in pv["text"] and pv["discord"]["role"] == "news"
              and s1[0] == 0 and r1["result"]["discord"]["released"] and "запись очереди №%d" % oid in r1["message"], (pv["text"][:200], tuple(s1)))
        tick()
        s2 = st(oid)
        tick()
        check("стенд: бот (подставной Discord) публикует ОДИН раз — канал announcements (новостной), упоминание <@&201>, заголовок = текст в игру; "
              "статус «опубликовано», id сообщения записан; второй проход — ничего",
              len(ad.posts) == 1 and ad.posts[0][0] == 101 and ad.posts[0][3].startswith("<@&201>\n🇬🇧 ") and ad.posts[0][2] == "Рестарт в 18:00"
              and tuple(s2[:2]) == (2, 1) and s2[3] == 101 and s2[4] == 501, (ad.posts, tuple(s2)))
        # итог неизвестен → повтор → журнал бота не даёт второй публикации
        a.cursor().execute("UPDATE adm.Outbox SET status = 1, claimed_utc = DATEADD(MINUTE, -%d, SYSUTCDATETIME()), discord_message_id = NULL WHERE id = ?"
                           % (O.STUCK_MIN + 1), oid)
        v = O.view({"status": "all"})
        x = [r for r in v["rows"] if r["id"] == oid][0]
        rr = ops.run(adm, "outbox.retry", {"id": oid})
        tick()
        s3 = st(oid)
        check("стенд: «итог неизвестен» (бот взял и молчит > %d мин) — предупреждение и «повторить»; повтор не публикует второй раз (номер в журнале "
              "бота), итог — те же id" % O.STUCK_MIN,
              x["state"] == "unknown" and x["can_retry"] and any("не отчитался" in w for w in v["warnings"]) and rr["ok"] and len(ad.posts) == 1
              and tuple(s3[:2]) == (2, 2) and s3[4] == 501, (x["state"], tuple(s3)))
        # сбой объявления в игру — запись отменяется, в Discord ничего
        calls["wait"] = 3
        w_game = _refused(lambda: ops.run(adm, "live.announce", {"text": "второе", "discord": DC}))
        calls["wait"] = 2
        g = a.cursor().execute("SELECT TOP 1 id, status, error FROM adm.Outbox ORDER BY id DESC").fetchone()
        tick()
        check("стенд: объявление в игру не разослано — отказ операции, запись очереди отменена с причиной, бот её не публикует",
              w_game and g[1] == 4 and g[2].startswith("объявление не разослано: GameServer: команда №777") and len(ad.posts) == 1, (w_game, tuple(g)))
        # пределы частоты (6 в час): уже 2 записи; ещё 4 — норма, седьмая — отказ в предпросмотре и в процедуре
        def qput(d, t):
            """Объявление мимо игры (стенд): ★ р76 К2 — встаёт «ждёт игры» (7) даже с hold=False, боту — только через Release."""
            i = O.put(O.check(own, d, t), "own_t", hold=False)
            k2.append(st(i)[0])
            O.release(i, True, "own_t")
            return i
        k2 = []
        for i in range(4):
            qput(DC, "t%d" % i)
        w_lim = _refused(lambda: ops.run(adm, "live.announce", {"text": "седьмое", "discord": DC}, dry=True))
        w_put = _refused(lambda: O.put(O.check(own, DC, "x"), "own_t", hold=False))
        check("стенд: предел %d объявлений в Discord за час — отказ и в предпросмотре, и в adm.OutboxPut (под замком)" % O.PER_HOUR,
              w_lim and "предел %d в час" % O.PER_HOUR in w_lim and w_put == w_lim, (w_lim, w_put))
        check("р76 К2: adm.OutboxPut ставит объявление (kind announce) в статус 7 «ждёт игры» и при @hold = 0 — боту только через Release",
              k2 == [7, 7, 7, 7], k2)
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -2, created_utc)")
        # просрочка, отмена, проверочная запись, повтор захвата тем же номером
        o_exp = qput(dict(DC, ttl=5), "exp")
        a.cursor().execute("UPDATE adm.Outbox SET expires_utc = DATEADD(MINUTE, -1, SYSUTCDATETIME()) WHERE id = ?", o_exp)
        o_can = qput(DC, "cancel me")
        w_gm = _refused(lambda: ops.run(gm, "outbox.cancel", {"id": o_can}))
        rc = ops.run(adm, "outbox.cancel", {"id": o_can})
        w_rc = _refused(lambda: ops.run(adm, "outbox.cancel", {"id": o_can}, dry=True))
        rt = ops.run(adm, "outbox.test", {})
        o_t = rt["result"]["id"]
        n_posts = len(ad.posts)
        for _ in range(6):
            tick()
        check("стенд: просроченная — «просрочено» без публикации, отменённая (gm — отказ, admin — да, второй раз — отказ) не публикуется, проверочная — "
              "«тест» без вызова Discord и без id сообщения",
              st(o_exp)[0] == 5 and st(o_can)[0] == 4 and w_gm and rc["ok"] and w_rc and st(o_t)[0] == 6 and st(o_t)[3] is None
              and not [p for p in ad.posts[n_posts:] if p[2] in ("exp", "cancel me", "test")], (tuple(st(o_exp)), tuple(st(o_can)), tuple(st(o_t)), w_gm,
                                                                                               [p[2] for p in ad.posts[n_posts:]]))
        posted4 = [p for p in ad.posts if p[2].startswith("t")]
        check("стенд: четыре записи, поставленные до предела, опубликованы по одной за проход (ни одна дважды)", len(posted4) == 4
              and len({p[2] for p in posted4}) == 4, [p[2] for p in ad.posts])
        o_n = qput(DC, "nonce")
        S2 = B.Store(connect=_AsBot)
        g1 = S2.out_claim(1)
        g2 = S2.out_claim(1)
        S2.out_done(g1[0]["id"], False, "проверка номера захвата")
        S2.out_claimed_ok()
        g3 = S2.out_claim(1)
        check("стенд: захват тем же номером (сбой по дороге) возвращает ту же запись, после итога и нового номера — ничего; 3 попыток нет "
              "(один захват = одна попытка)", [x["id"] for x in g1] == [x["id"] for x in g2] == [o_n] and g3 == [] and st(o_n)[1] == 1,
              (g1, g2, g3, tuple(st(o_n))))
        # удаление опубликованного: admin — нет права, owner — бот удаляет
        w_da = _refused(lambda: ops.run(adm, "outbox.delete", {"id": oid}))
        rd = ops.run(own, "outbox.delete", {"id": oid})
        tick()
        w_dd = _refused(lambda: ops.run(own, "outbox.delete", {"id": oid}, dry=True))
        check("стенд: удаление опубликованного — admin отказ (community.delete), owner — бот удаляет сообщение в канале белого списка, отметка «удалено», "
              "второй раз — отказ", w_da and "community.delete" in w_da and rd["ok"] and ad.deletes == [(101, 501, False)] and st(oid)[5] == 2 and w_dd,
              (w_da, ad.deletes, tuple(st(oid)), w_dd))
        # форум updates: ветка с заголовком, удаление — ветки (родитель проверяется)
        o_f = qput(dict(DC, channel="updates", role="patch"), "Patch 8.1.4")
        tick()
        sf = st(o_f)
        ops.run(own, "outbox.delete", {"id": o_f})
        tick()
        check("стенд: форум updates — новая ветка «Patch 8.1.4» с Patch Ping, id ветки записан; удаление — ветка целиком",
              ad.posts[-1][:3] == (103, "forum", "Patch 8.1.4") and ad.posts[-1][4] == 202 and sf[3] == sf[4] == 9103 and ad.deletes[-1] == (9103, 9103, True)
              and st(o_f)[5] == 2, (ad.posts[-1][:3], tuple(sf), ad.deletes))
        e_chk = None
        try:
            a.cursor().execute("INSERT adm.Outbox (kind, channel_key, title, text_en, created_by, expires_utc) VALUES ('announce', 'announcements', N't', "
                               "N'hello @everyone', N'x', '20991231')")
        except Exception as ex:
            e_chk = str(ex)
        c4 = a.cursor().execute("SET NOCOUNT ON; DECLARE @i INT, @c INT; EXEC adm.OutboxPut 'announce', 'general', NULL, N't', N'e', NULL, NULL, 60, N'x', 0, "
                                "@i OUTPUT, @c OUTPUT; SELECT @c").fetchone()[0]
        check("стенд: база сама не пускает @everyone (CHECK) и канал не из списка (adm.OutboxPut код 4)", e_chk and "CK_adm_Outbox" in e_chk and c4 == 4,
              (e_chk, c4))
        aud = {r[0]: r[1] for r in a.cursor().execute("SELECT action, COUNT(*) FROM adm.audit WHERE result = 'ok' AND (action LIKE 'outbox.%' OR action = 'live.announce') "
                                                     "GROUP BY action")}
        fq, _p = _route("/api/outbox")

        class _Req:
            def __init__(self, query, role):
                self.query, self.session = dict(query), {"user": {"role": role, "login": "t_" + role}}
        ra, ro = fq(_Req({"status": "all"}, "admin"), None), fq(_Req({"status": "posted"}, "owner"), None)
        check("стенд: журнал adm.audit — live.announce 1, outbox.retry 1, outbox.cancel 1, outbox.test 1, outbox.delete 2; API — права роли "
              "(admin без удаления), фильтр «опубликованные»",
              aud == {"live.announce": 1, "outbox.retry": 1, "outbox.cancel": 1, "outbox.test": 1, "outbox.delete": 2} and ra["can"]["community.post"]
              and not ra["can"]["community.delete"] and ro["can"]["community.delete"] and ra["installed"] and all(r["state"] == "posted" for r in ro["rows"]),
              (aud, ra["can"]))
    finally:
        bridge.nodes, bridge.enqueue, bridge.wait = saved
        db.set_override("admin", None)
        tmp.cleanup()
        m2 = ldb("master")
        try:
            m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % name)
            m2.cursor().execute("DROP DATABASE [%s]" % name)
        except Exception:
            pass


def live(check):
    """Живая dev: только проверочная запись (бот её не публикует) и захват только проверочных. В Discord ничего не уходит."""
    _paths()
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import outbox as O
    import outbox_bot as B
    if config.get().on_server:
        return check("живой самотест А7.4 «очередь Discord» — с ПК", True)
    cn = db.admin()
    try:
        q = lambda o, p: db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?) AS p", (o, p))[0]["p"]
        perm = {"sel": q("adm.Outbox", "SELECT"), "ins": q("adm.Outbox", "INSERT"), "upd": q("adm.Outbox", "UPDATE"), "put": q("adm.OutboxPut", "EXECUTE"),
                "del": q("adm.OutboxDelete", "EXECUTE"), "claim": q("adm.OutboxClaim", "EXECUTE"), "done": q("adm.OutboxDone", "EXECUTE")}
    finally:
        cn.close()
    check("живое (asda_admin): adm.Outbox — чтение и процедуры панели, без прямой записи и без процедур бота",
          perm == {"sel": 1, "ins": 0, "upd": 0, "put": 1, "del": 1, "claim": 0, "done": 0}, perm)
    S = B.Store()
    try:
        c = S._cn()
        try:
            rows = c.cursor().execute(_read(ROOT, "sql", "adminc_28_outbox_verify.sql")).fetchall()
        finally:
            c.close()
        bad = [tuple(r) for r in rows if int(r[1] or 0) != int(r[2])]
        check("живое (путь бота): пароль asda_reports из reports.env, вход по VPN, права очереди = adminc_28_outbox_verify (%d проверок)" % len(rows),
              len(rows) == 15 and not bad, bad)
    except Exception as ex:
        check("живое (путь бота): вход asda_reports по VPN", False, "%s: %s" % (type(ex).__name__, str(ex)[:200]))
    v0 = O.view({"status": "all"})
    real_q = [r for r in v0["rows"] if not r["test"] and r["state"] in ("queued", "claimed", "hold")]
    check("живое: очередь читается (установлена; записей на экране %d), объявлений, ждущих публикации, нет — самотест ничего не публикует"
          % len(v0["rows"]), v0["installed"] and not real_q, real_q[:3])
    r = ops.run(ops.Ctx(None, "cli:selftest", "owner", "", "cli"), "outbox.test", {})
    oid = r["result"]["id"]
    got = []
    try:
        got = S.out_claim(1, test_only=True)          # ТОЛЬКО проверочные: настоящие объявления этим захватом не берутся
        mine = [x for x in got if x["id"] == oid]
        for x in got:
            if not x["test"]:
                raise RuntimeError("захват test_only вернул НЕ проверочную запись №%d" % x["id"])
        claimed = bool(mine) and mine[0]["test"]
        for x in got:
            S.out_done(x["id"], True)                 # проверочная: итог «тест», Discord не вызывается
        S.out_claimed_ok()
    except Exception as ex:
        claimed = "%s: %s" % (type(ex).__name__, str(ex)[:200])
    row = [x for x in O.view({"status": "test"})["rows"] if x["id"] == oid]
    check("живое: проверочная запись №%d → захват только проверочных — «бот взял» (или её уже взял работающий бот) → итог «тест»; id сообщения "
          "Discord нет — в Discord ничего не ушло" % oid,
          (claimed is True or (not got and row and row[0]["state"] == "test")) and row and row[0]["state"] == "test" and not row[0]["posted_at"],
          (claimed, row[:1]))
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import outbox as O\nv = O.view({'status': 'test'})\n"
             "print('OBPROBE installed=%s ids=%s' % (v['installed'], ','.join(str(r['id']) for r in v['rows'][:20])))\n")
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
    mm = re.search(r"OBPROBE installed=(\w+) ids=([\d,]*)", out)
    check("служба на сервере (SSH): очередь читается, проверочная запись №%d видна" % oid,
          bool(mm) and mm.group(1) == "True" and str(oid) in mm.group(2).split(","), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/outbox" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/outbox без входа — 401", code == 401, code)


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
