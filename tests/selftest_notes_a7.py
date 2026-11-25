# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_notes_a7.py — самотест шага А7.7 «Заметки к выпуску» (24.11.2026; решение владельца А7 №7 — черновик заметок для игроков в панели и
кнопка «Опубликовать»; №2 — тексты EN / RU / AR руками; domains/notes.py, sql/adminc_31_notes.sql и adminc_31_notes_verify.sql, вид notes в
CK_adm_Outbox_route (adminc_29), /api/notes, web/notes.js, asda_admin.py notes; бот — тот же AstoryAdminCenter/DiscordBot/outbox_bot.py).

НИ ОДИН ПРОГОН НЕ ПУБЛИКУЕТ В DISCORD: офлайн и стенд — бот с подставным адаптером Discord (записывает вызовы, сети нет); живой — только
публикация с отметкой «тест» (бот её отмечает «тест» без вызова Discord) и захват только проверочных (@test_only = 1).

offline(check)  — права (notes.view / notes.draft — owner, admin; notes.push — owner; публикация и отметка — community.post), операции, маршрут,
                  разбор changelog (ключи устойчивы к переносу записи в другой раздел, одинаковые строки, вид и состояние, выпуск по строке
                  выпуска, «Что стало» без «Причины»), разбор настоящего текущего changelog, текущий файл по AGENT_RULES_PORT.md, секреты и
                  внутренние детали, отказы полей публикации, тексты без «; », переводы EN, веб (без innerHTML, данные — acText), adminc_31
                  (уровень 100, права), проверка под asda_reports, adminc_10 / 29 / 99, выкладка, консоль, импорт без побочных эффектов.
sandbox(check, ldb) — СВОЯ база LocalDB: adminc_02 + 14 + 23 + 27 + 28 + 29 + 31 (31 дважды); снимок с «ПК», черновик, публикация →
                  НАСТОЯЩИЙ outbox_bot.Store под EXECUTE AS USER asda_reports и Worker с подставным Discord: «опубликовано» только по итогу бота,
                  повтор той же записи — отказ (панель и процедура), откат = удаление ветки (только owner) → записи снова свободны, тест без
                  Discord, отмена до публикации, отметка «вне панели» и её откат, пределы частоты, права asda_reports, CHECK вида notes, журнал.
live(check)     — живая dev: права asda_admin на adm.Notes*, путь бота (asda_reports по VPN = adminc_31_notes_verify), снимок changelog с ПК
                  (notes.push — пишет только AsdaAdmin), разбор, публикация с отметкой «тест» → захват ТОЛЬКО проверочных → «тест» (Discord не
                  вызывается), записи не стали «опубликованными», служба на сервере (SSH) видит тот же снимок, без входа — 401.
Побочных эффектов при импорте нет.
"""
import ast
import asyncio
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

SAMPLE = """# Changelog — образец самотеста

## 16.11.2026 — раздел до выпуска

- **Клиент: окно обучения не закрывает чат (клиент, следующий выпуск)**
  Что стало:
  - Окно обучения больше не закрывает чат.
  - Подсказка видна целиком.

  Причина: окно перехватывало ввод. Это внутренняя причина.
- **Админ-центр: новая кнопка (16.11.2026; панель выложена; в игре ничего не меняется)**
  Что стало:
  - Кнопка.

  Причина: просьба владельца.
- **Сервер: блок не пропадает (выложено 16.11.2026)**
  - Блок держится.
  - Причина: гонка при входе.

## 17.11.2026 00:38 — ВЫПУСК клиента alpha-8.1.0-11.2026 (seq 70)
- **[ВЫПУСК]** Клиент alpha-8.1.0-11.2026 выложен на @@ASTORY_UPDATE_HOST@@ по слову владельца: seq 70, манифест 15176fbe46fdd1ef.
- [ИСПРАВЛЕНИЕ] [клиент, следующий выпуск] Значок «?» стоит у панели (17.11): теперь всегда видно.
- **Сервер: события опыта для всех (сервер, следующий выпуск; собрано и проверено, не выложено)**
  Что стало:
  - Значок увидят все.
- **Сервер: события опыта для всех (сервер, следующий выпуск; собрано и проверено, не выложено)**
  Что стало:
  - Вторая запись с той же строкой.
- **Сервер: заглушка чата действует (17.11.2026 22:52; сервер, уже действует)**
  Что стало:
  - Заглушка работает.
"""
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика


def _read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def _paths():
    for p in (ROOT, BOT, HERE):
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


def _fields(keys, **kw):
    d = {"keys": keys, "title": "Astory alpha-8.1.0-11.2026", "role": "patch", "ttl": 60, "en": "Tutorial window no longer closes the chat.",
         "ru": "• Окно обучения больше не закрывает чат.", "ar": ""}
    d.update(kw)
    return d


def offline(check):
    _paths()
    from core import auth, i18n, ops
    import domains
    domains.load_all()
    from domains import notes as N, outbox as O
    roles = ("owner", "admin", "gm", "support")
    who = lambda p: {r for r in roles if auth.can(r, p)}
    reg = ops.REGISTRY
    check("заметки: права notes.view и notes.draft — owner, admin; notes.push — owner; публикация и отметка — community.post (owner, admin); gm и "
          "support — ничего", who("notes.view") == who("notes.draft") == who("community.post") == {"owner", "admin"} and who("notes.push") == {"owner"})
    check("заметки: операции notes.push (задание ПК, без отката), notes.draft (без отката), notes.publish и notes.mark (community.post, с откатом)",
          reg["notes.push"].perm == "notes.push" and getattr(reg["notes.push"], "schedule_runner", "") == "pc" and not reg["notes.push"].reversible
          and reg["notes.draft"].perm == "notes.draft" and not reg["notes.draft"].reversible
          and reg["notes.publish"].perm == "community.post" and reg["notes.publish"].reversible
          and reg["notes.mark"].perm == "community.post" and reg["notes.mark"].reversible)
    check("р82: notes.resync (notes.push, без отката), notes.hide (notes.draft, с откатом), notes.resolve (community.post, откат только «ветка есть»)",
          reg["notes.resync"].perm == "notes.push" and not reg["notes.resync"].reversible and reg["notes.hide"].perm == "notes.draft"
          and reg["notes.hide"].reversible and reg["notes.resolve"].perm == "community.post" and reg["notes.resolve"].reversible)
    fn, perm = _route("/api/notes")
    check("заметки: маршрут GET /api/notes — право notes.view", fn is not None and perm == "notes.view")
    # ---- разбор
    e = N.parse(SAMPLE)
    by = {x["title"]: x for x in e}
    c1 = by.get("Клиент: окно обучения не закрывает чат (клиент, следующий выпуск)") or {}
    adm = by.get("Админ-центр: новая кнопка (16.11.2026; панель выложена; в игре ничего не меняется)") or {}
    s1 = by.get("Сервер: блок не пропадает (выложено 16.11.2026)") or {}
    rel = [x for x in e if x["area"] == "release"]
    c2 = [x for x in e if x["title"].startswith("[ИСПРАВЛЕНИЕ]")]
    dup = [x for x in e if x["title"].startswith("Сервер: события опыта для всех")]
    live1 = [x for x in e if x["title"].startswith("Сервер: заглушка чата действует")]
    check("разбор: 8 записей; клиент до строки выпуска — «в выпуске alpha-8.1.0-11.2026», после — «ещё не в выпуске»; выпуск — вид release; сервер "
          "«выложено» / «уже действует» — live, «следующий выпуск» — pending; админ-центр — service; галочки по умолчанию — выпуск, клиент в выпуске, "
          "сервер live",
          len(e) == 8 and c1.get("area") == "client" and c1.get("status") == "released" and c1.get("release") == "alpha-8.1.0-11.2026" and c1.get("default")
          and adm.get("area") == "service" and not adm.get("visible") and not adm.get("default") and s1.get("status") == "live" and s1.get("default")
          and len(rel) == 1 and rel[0]["release"] == "alpha-8.1.0-11.2026" and rel[0]["default"] and rel[0]["ru"] == "• Выпуск клиента alpha-8.1.0-11.2026"
          and len(c2) == 1 and c2[0]["status"] == "unreleased" and not c2[0]["default"] and c2[0]["area"] == "client"
          and all(x["status"] == "pending" and not x["default"] for x in dup) and live1 and live1[0]["status"] == "live",
          [(x["area"], x["status"], x["release"], x["default"], x["title"][:40]) for x in e])
    check("разбор: RU для игрока — пункты «Что стало» без «Причины» (внутренняя причина не попадает), у записи без блока — её пункты до «Причины»",
          c1.get("ru") == "• Окно обучения больше не закрывает чат.\n• Подсказка видна целиком." and "Причина" not in "".join(x["ru"] for x in e)
          and s1.get("ru") == "• Блок держится.", (c1.get("ru"), s1.get("ru")))
    old = "[ИСПРАВЛЕНИЕ] [клиент, следующий выпуск] Углы рамки магазинов на высоком экране (17.11): премиум-магазин 6000"
    new = ("[ИСПРАВЛЕНИЕ] [клиент, вошло в alpha-8.1.0; перенесено из замороженного CHANGELOG_2026-11-10.md] Углы рамки магазинов на высоком экране "
           "(17.11): премиум-магазин 6000")
    k_old, k_new = N.entry_key(old, N._date_entry(old, "10.11.2026")), N.entry_key(new, N._date_entry(new, "17.11.2026"))
    check("р82 В-2: контрпример строки 230 — запись перенесена в новый файл с пометкой «перенесено из …» и сменой метки (раздел другой даты): ключ тот "
          "же (метки […] и скобки «перенесено» не входят, дата «(17.11)» — с годом раздела); прежний ключ v1 у них разный (для перевода публикаций)",
          k_old == k_new and N._date_entry(old, "10.11.2026") == "17.11.2026" and N.entry_key_prev(old, "10.11.2026") != N.entry_key_prev(new, "17.11.2026"),
          (k_old, k_new))
    h920 = "**Клиент: значок события и счастливого часа больше не «застревает» (клиент, следующий выпуск)**"
    v920 = [h920, "**Клиент: значок события и счастливого часа больше не «застревает» (клиент, вошло в alpha-8.1.3; перенесено из CHANGELOG_2026-11-16.md)**",
            "**Клиент: значок события и счастливого часа больше не «застревает» (клиент, вошло в alpha-8.1.3)**"]
    k920 = {N.entry_key(h) for h in v920}
    t920 = [N.parse("## %s — x\n- %s\n  Что стало:\n  - Значок гаснет.\n" % (d, h))[0]["key"] for d, h in (("18.11.2026", v920[0]), ("25.11.2026", v920[0]),
                                                                                                    ("25.11.2026", v920[1]), ("25.11.2026", v920[2]))]
    s1t = ["**Сервер: заглушка чата действует (22.11.2026 22:52; сервер, уже действует)**", "**Сервер: заглушка чата действует (сервер, уже действует с 22.11)**"]
    check("р83 В-1: перенос строки 920 — тот же заголовок в разделе другой даты, со скобкой «(клиент, вошло в …; перенесено из …)» и «(клиент, вошло в …)» — "
          "ключ один (все скобки статуса в конце сняты, дата раздела в ключ не входит); дата в скобке статуса тоже не меняет ключ; «Что стало» — второй "
          "признак (what_hash)",
          len(k920) == 1 and len(set(t920)) == 1 and N.entry_key(s1t[0]) == N.entry_key(s1t[1]) and N.key_text(v920[0]) ==
          "клиент: значок события и счастливого часа больше не «застревает»" and N.what_hash(["Значок гаснет."]) == N.what_hash(["значок  гаснет."]),
          (k920, t920))
    ru_c, ru_n = N.ru_lines(["Окно больше не закрывает чат.", "Самотест `asda.SelfTest.Tutorial` (51/0) зелёный.", "Скрипт Tools/asda_ui_tutorial_win_anchor.py поправлен.",
                             "Перезапускался только процесс шлюза.", "Подсказка видна целиком, как в `WBP_Tutorial_WIN`."])
    gw = N.sensitive_in("Сервер: шлюз gp7 отмечает покупки", "Перезапускался только процесс шлюза, игровые серверы переподключились")
    check("р83 М-1: RU-заготовка выбрасывает пункты с внутренними деталями (имя файла, процесс шлюза) и фрагменты в `…`; шлюз gp7 и его процессы — "
          "«чувствительное»",
          ru_c == ["Окно больше не закрывает чат."] and ru_n == 4
          and "шлюз gp7 и его процессы" in gw, (ru_c, ru_n, gw))
    e2 = N.parse("## 18.11.2026 — x\n- [ВЫПУСК] alpha-8.1.2-11.2026, seq 72, манифест a16fcfdfaea6535b\n"
                 "- **Сервер: блок, поставленный в момент входа, больше не пропадает (выложено 17.11.2026)**\n  Что стало:\n  - Блок держится.\n"
                 "- **Уточнение к записи «блок, поставленный в момент входа» (17.11.2026)**\n  Что стало:\n  - Блок держится и при сбое.\n"
                 "- **Уточнение к записи «такой записи нет» (17.11.2026)**\n  Что стало:\n  - x.\n")
    check("р82 М-1: «[ВЫПУСК] alpha-8.1.2-…» без слова «выложен» — выпуск (галочка); уточнение к записи — вид и состояние исходной (ссылка на неё); "
          "исходной нет — вид «уточнение», виден игрокам, без галочки",
          [x["area"] for x in e2] == ["release", "server", "server", "clarify"] and e2[0]["default"] and e2[0]["release"] == "alpha-8.1.2-11.2026"
          and e2[2]["of_key"] == e2[1]["key"] and e2[2]["status"] == "live" and e2[3]["visible"] and not e2[3]["default"],
          [(x["area"], x["status"], x["of_key"]) for x in e2])
    rr_src = P.dev_text(PORT, "Docs", "Changelog", "CHANGELOG_2026-11-16.md")     # ★ 25.11 (К-3): Docs — только среда разработчика
    if rr_src is None:
        P.skip("р82 В-1: настоящие примеры ревизора из changelog", "нет Docs/Changelog/CHANGELOG_2026-11-16.md")
    else:
        rr = {x["title"]: x for x in N.parse(rr_src)}
        eac = [x for t, x in rr.items() if t.startswith("Сервер античита EAC")]
        pick = lambda pre: [x for t, x in rr.items() if t.startswith(pre)]
        ab, fame, stack = pick("Сервер: автоблок за поддельные пакеты"), pick("Сервер: слава за звания с номерами 256 и выше"), pick("Сервер: общий рестарт конца волны")
        check("р82 В-1: настоящие примеры ревизора — пять «Сервер античита EAC» (Mode=1, пределы поблажки), автоблок 20 / 50, слава персонажа 75209/10, "
              "«общий рестарт… 15 процессов стойки» — «чувствительное», без галочки; ни одна чувствительная запись не отмечена по умолчанию",
              len(eac) >= 5 and all(x["sens"] and not x["default"] for x in eac + ab + fame + stack) and ab and fame and stack
              and "античит / EAC" in eac[0]["sens"] and "автоблок" in ab[0]["sens"] and "номер персонажа или учётки" in fame[0]["sens"]
              and "стойка и процессы сервера" in stack[0]["sens"] and not [x for x in rr.values() if x["sens"] and x["default"]],
              [(x["title"][:40], x["sens"]) for x in eac + ab + fame + stack][:6])
    check("р82 М-5: RU-заготовка и полный текст для не-owner — IP и пути заменены («[IP]», «[путь]»)",
          N.mask("сервер @@ASTORY_SERVER_VPN_IP@@, файл @@ASTORY_DEV_ROOT_ESC@@\\port\\x.md") == "сервер [IP], файл [путь]")
    moved = SAMPLE.replace("## 16.11.2026 — раздел до выпуска", "## 16.11.2026 — перенесено из прежнего файла")
    k_moved = [x["key"] for x in N.parse(moved)]
    check("разбор: ключ записи — 16 hex; одинаковая первая строка с той же датой — разные ключи (порядковый номер); перенос записи в раздел с другим "
          "заголовком ключ не меняет; ключ = entry_key(первая строка, дата)",
          all(re.fullmatch(r"[0-9a-f]{16}", x["key"]) for x in e) and len({x["key"] for x in e}) == len(e) and dup[0]["key"] != dup[1]["key"]
          and k_moved == [x["key"] for x in e] and c1["key"] == N.entry_key(c1["head"], "16.11.2026"), k_moved[:3])
    sec2 = N.secrets_in("пароль: Qwerty12345 token=abcdef123456 Bearer abcdefghijklmnopqrstuvwxyz123 Server=srv;Uid=u;Pwd=p4ss AKIA" + "ABCDEFGHIJKLMNOP")
    check("р82 М-5: секреты шире — «пароль: …», token=, Bearer, строка подключения с Pwd=, ключ AWS; настоящий changelog их не содержит",
          set(sec2) >= {"пароль или ключ в виде «имя=значение»", "токен Bearer", "строка подключения с паролем", "ключ AWS"}, sec2)
    cur_name = "CHANGELOG_2026-11-16.md"
    real = P.dev_text(PORT, "Docs", "Changelog", cur_name)                 # ★ 25.11 (К-3)
    if real is None:
        P.skip("разбор настоящего %s" % cur_name, "нет Docs/Changelog/%s" % cur_name)
    else:
        er = N.parse(real)
        n_lines = len([ln for ln in real.replace("\r\n", "\n").split("\n") if ln.startswith("- ")])
        check("разбор настоящего %s: записей столько же, сколько строк «- » с начала строки (%d), ключи уникальны, есть выпуски и видимые игрокам, "
              "секретов нет" % (cur_name, len(er)),
              len(er) == n_lines and len({x["key"] for x in er}) == len(er) and any(x["area"] == "release" for x in er) and sum(x["visible"] for x in er) >= 10
              and not N.secrets_in(real), (len(er), n_lines))
    tmp = tempfile.TemporaryDirectory()
    try:
        d = tmp.name
        for n in ("CHANGELOG_2026-11-10.md", "CHANGELOG_2026-11-16.md", "CHANGELOG_ДЛЯ_ИГРОКОВ.md"):
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write("- x\n")
        rules = os.path.join(d, "rules.md")
        with open(rules, "w", encoding="utf-8") as f:
            f.write("- Changelog (текущий): `Docs\\Changelog\\CHANGELOG_2026-11-10.md` — писать ЗАПРЕЩЕНО\n")
        f1 = N.current_file(d, rules)
        f2 = N.current_file(d, os.path.join(d, "нет.md"))
        snap = N.pc_collect(d, rules)
        live_rules = P.dev_text(PORT, "Docs", "Process", "AGENT_RULES_PORT.md")    # ★ 25.11 (К-3): нет — сверка с правилами не проверяется
        m = N.CURRENT_RX.search(live_rules) if live_rules is not None else None
    finally:
        tmp.cleanup()
    check("текущий changelog: имя — из «Changelog (текущий)» правил агентов (даже если есть файл новее), правил нет — самый новый "
          "CHANGELOG_ГГГГ-ММ-ДД.md; снимок — имя, текст как есть, md5; настоящие правила называют %s" % cur_name,
          f1 == "CHANGELOG_2026-11-10.md" and f2 == "CHANGELOG_2026-11-16.md" and snap["file"] == f1 and snap["text"] == "- x\n" and len(snap["md5"]) == 32
          and (live_rules is None or (m and m.group(1) == cur_name)), (f1, f2, m and m.group(1)))
    sec = N.secrets_in("x " + "MTAxMjM0NTY3ODkwMTIzNDU2" + ".GhIjKl." + "abcdefghijklmnopqrstuvwxyz0123" + " y 1234567890:" + "A" * 35 + " -----BEGIN RSA PRIVATE KEY----- password=Hunter22")
    lk = N.leaks_in("см. @@ASTORY_DEV_ROOT_ESC@@\\x и @@ASTORY_SERVER_VPN_IP@@, файл notes.py, adm.NotesSnap, манифест 15176fbe46fdd1ef")
    check("секреты в changelog (токен Discord, Telegram, закрытый ключ, password=…) — снимок не отправляется; внутренние детали в тексте игрокам "
          "(путь, IP, имя файла, имя базы, хэш) — предупреждение", len(sec) == 4 and {"путь к файлу", "IP-адрес", "имя файла", "хэш или номер сборки",
                                                                      "таблица или база"} <= set(lk) and not N.leaks_in("Окно обучения больше не закрывает чат."),
          (sec, lk))
    # ---- поля публикации
    own, adm_c, gm = ops.Ctx(1, "o", "owner", "", "web"), ops.Ctx(2, "a", "admin", "", "web"), ops.Ctx(3, "g", "gm", "", "web")
    ok = N.compose_fields(adm_c, _fields(["0" * 16]))
    bad = {k: _refused(lambda c=c, f=f: N.compose_fields(c, f)) for k, (c, f) in {
        "gm": (gm, _fields([])), "role": (own, _fields([], role="news")), "role2": (own, _fields([], role="everyone")),
        "notitle": (own, _fields([], title="  ")), "longtitle": (own, _fields([], title="x" * 101)), "noen": (own, _fields([], en=" ")),
        "every": (own, _fields([], ru="все @everyone")), "here": (own, _fields([], title="@here новое")), "mention": (own, _fields([], ar="<@123>")),
        "total": (own, _fields([], en="x" * 1000, ru="y" * 990)), "ttl": (own, _fields([], ttl=2)), "ctrl": (own, _fields([], title="a\x07b"))}.items()}
    k_bad = {k: _refused(lambda v=v: N._keys({"keys": v})) for k, v in {"empty": [], "notlist": "abc", "hex": ["xyz"], "many": ["%016x" % i for i in range(201)]}.items()}
    check("публикация: годные поля → форум updates, роль patch, срок; отказы — gm, роль не Patch Ping (news, everyone), пустой и длинный заголовок, "
          "пустой EN, @everyone / @here, <@…>, сообщение > 2000, срок < 5, управляющие символы; ключи — пусто, не список, не hex, больше 200",
          ok["channel"] == "updates" and ok["role"] == "patch" and ok["ttl"] == 60 and ok["title"] == "Astory alpha-8.1.0-11.2026"
          and all(bad.values()) and all(k_bad.values()) and "community.post" in bad["gm"] and "Patch Ping" in bad["role"], (bad, k_bad))
    msg = O.compose("<@&202>", ok["en"], ok["ru"], ok["ar"])
    check("публикация: текст Discord собирает та же функция, что у объявлений и бота (роль, затем EN, AR, RU с флагами)",
          msg == "<@&202>\n🇬🇧 Tutorial window no longer closes the chat.\n🇷🇺 • Окно обучения больше не закрывает чат.")
    # ---- тексты и переводы
    texts = [N.NOT_INSTALLED, N.NO_SNAP, N.EXPECT_CHANGED] + list(N.PUT_CODES.values()) + list(bad.values()) + list(k_bad.values()) + [
        N.BUSY_TEXT[k] % ("Сервер: x", 3) for k in N.BUSY_TEXT] + [o.title for n, o in reg.items() if n.startswith("notes.")] + [
        "changelog CHANGELOG_2026-11-16.md: 100 знаков, записей 5 (видны игрокам 3), md5 " + "a" * 32, "changelog записан: снимок №3 (100 знаков)",
        "changelog не изменился: снимок №3, отмечено «ПК присылал»", "changelog лежит на ПК владельца — снимок присылает консоль ПК, поставьте задание ПК",
        "changelog пуст или больше 4000000 знаков — не записан", "changelog с ПК присылался больше 24 ч назад (2026-11-24 10:00:00 UTC) — новые записи могли не попасть, пришлите снимок заново",
        "имя файла changelog не по образцу CHANGELOG_ГГГГ-ММ-ДД.md — не записан", "в каталоге changelog нет файлов CHANGELOG_ГГГГ-ММ-ДД.md",
        "в changelog похоже на секрет (токен Discord, закрытый ключ) — снимок не отправлен, уберите это из файла",
        "в changelog похоже на секрет (токен Telegram) — снимок не отправится", "заметки к выпуску не прочитаны: x",
        "пришёл новый снимок changelog (№4) — обновите страницу и проверьте отметки", "записи changelog 0123456789abcdef нет в последнем снимке — обновите страницу",
        "заголовок ветки — строка", "поле черновика en — строка", "черновик больше 100000 знаков — не сохранён",
        "сохранить черновик заметок: отмечено записей 2, заголовок «Astory», EN 10 / RU 20 / AR 0 знаков",
        "пишется только база панели AsdaAdmin (adm.NotesDraft) — в Discord ничего не уходит", "черновик заметок сохранён (записей 2)",
        "запись «Сервер: x»: " + N.PUT_CODES[5], "запись «Сервер: x»: очередь Discord: код 9",
        "ТЕСТ: бот заберёт запись и отметит «тест», в Discord ничего не уйдёт, записи changelog не станут «опубликованными»", "роль: Patch Ping", "без упоминания роли",
        "ПУБЛИЧНО: новая ветка в форуме updates — её увидят все участники сервера Discord, пинг роли Patch Ping",
        "ПУБЛИЧНО: новая ветка в форуме updates — её увидят все участники сервера Discord, без пинга роли", "в Discord нет текста на AR",
        "в тексте похоже на внутренние детали (путь к файлу, IP-адрес, имя файла, внутреннее имя проекта или базы, хэш или номер сборки) — игрокам это обычно не нужно, проверьте",
        "ссылки в тексте ведут на: discord.gg (превью ссылок в Discord отключено)",
        "длина: сообщение 120 из 2000 знаков (с упоминанием роли), имя ветки 26 из 100",
        "записи changelog станут «опубликованными», когда бот отчитается об успехе, а не при постановке в очередь",
        "откат — в «Журнале действий»: до публикации — отмена записи очереди, после — удаление ветки из Discord (только владелец), кто уже прочитал — не вернуть",
        "в Discord публикует бот Oracle на ПК владельца (раз в 30 с), если он запущен — итог виден на странице «Очередь Discord», срок годности 60 мин",
        "опубликовать заметки к выпуску: форум updates, ветка «Astory», записей changelog 2 (снимок №3, CHANGELOG_2026-11-16.md)\nтекст в Discord:\n" + msg,
        "заметки к выпуску — проверочная запись очереди Discord №5 (публикация №2, записей 1): бот отметит «тест», в Discord ничего не уйдёт",
        "заметки к выпуску — запись очереди Discord №5 (публикация №2, записей 1): публикует бот на ПК",
        "в журнале нет номера записи очереди — откат не выполнен", "записи очереди Discord №5 нет", "проверочная публикация — в Discord ничего не уходило, откатывать нечего",
        "запись очереди Discord №5 отменена — заметки не опубликованы", "заметки уже опубликованы — удалить ветку из Discord может только владелец (community.delete)",
        "удаление ветки заметок (запись очереди №5) поставлено боту — кто уже прочитал, не вернуть", "бот публикует запись №5 прямо сейчас — повторите откат через минуту",
        "удаление ветки по записи №5 уже поставлено боту — итог виден в «Очереди Discord»", "ветка по записи №5 уже удалена из Discord — откатывать нечего",
        "запись очереди Discord №5 не опубликована и не ждёт бота (cancelled) — откатывать нечего",
        "запись очереди Discord №5 изменилась — откройте «Очередь Discord» заново",
        "причина отметки — от 3 до 200 знаков (где и когда это уже публиковалось)",
        "отметить «уже опубликовано вне панели» записей changelog: 1 (причина: вручную в Discord 20.11)\n16.11.2026 — Сервер: x",
        "в Discord ничего не уходит — пишется только база панели AsdaAdmin (adm.NotesPost), записи пропадут из черновика",
        "откат — в «Журнале действий» (отметка снимается, записи снова в черновике)", "отмечено «опубликовано вне панели»: записей 1 (отметка №2)",
        "в журнале нет номера отметки — откат не выполнен", "отметка №2 уже снята или её нет", "отметка №2 снята — записи снова в черновике",
        "нет права «community.post» (публикация в Discord — owner и admin)", O.NOTES_NO_RETRY % 5,
        "ветка с заголовком «Astory» за сутки уже была (запись очереди №5) — для следующей части дайте другой заголовок, например «… (часть 2)»",
        "реестр записей не догнал снимок №3 — на ПК: python AstoryAdminCenter\\asda_admin.py notes resync",
        "changelog сменился (CHANGELOG_2026-11-16.md → CHANGELOG_2026-11-24.md): из прежних файлов не опубликовано записей, видимых игрокам: 2 — они в списке с пометкой «из файла …», пока их не опубликуют или не скроют",
        "перечитать реестр по снимку №3 (CHANGELOG_2026-11-16.md): записей 8", "пишется только база панели AsdaAdmin (реестр записей) — в Discord ничего не уходит",
        "реестр записей перечитан по снимку №3: записей 8", "в Discord ничего не уходит — пишется только база панели AsdaAdmin (реестр записей)",
        "в журнале нет записей — откат не выполнен", "решение — «ветки нет» или «ветка есть»",
        "решение «ветки нет» не откатывается — если ветка нашлась, отметьте записи «опубликовано вне панели»", "запись «Сервер: x» скрыта — сначала верните её",
        "отмечены записи с чувствительным (2: античит / EAC, автоблок) — их текст в RU не подставлялся, проверьте, что написано своими словами",
        "итог публикации №5 неизвестен — ветка могла появиться, откат мог бы дать дубль: проверьте форум updates и решите «ветки нет» или «ветка есть» в истории публикаций",
        "записи changelog 0123456789abcdef нет в реестре — пришлите снимок или выполните notes resync", "все отмеченные записи уже скрыты", "все отмеченные записи уже видны",
        "скрыть из черновика записей changelog: 1 (причина: вручную в Discord 20.11)\n16.11.2026 — Сервер: x", "вернуть в черновик записей changelog: 1\n16.11.2026 — Сервер: x",
        "скрыто записей changelog: 1", "возвращено записей changelog: 1", "номер публикации — целое от 1",
        "публикации заметок №5 нет или это не публикация в Discord", "у публикации №5 итог известен (posted) — решать нечего",
        "публикация №5 (запись очереди №6): ветки в форуме updates нет — запись очереди закрывается, записей changelog 2 снова свободны",
        "публикация №5 (запись очереди №6): ветка в форуме updates есть — запись очереди закрывается, записей changelog 2 отмечаются «опубликовано вне панели»",
        "сначала проверьте форум updates глазами: «ветки нет» при существующей ветке даст дубль при следующей публикации",
        "удалить ветку из Discord после этого можно только руками в Discord (номер сообщения бот не записал)",
        "публикация №5: ветки нет — записи свободны", "публикация №5: ветка есть — записи отмечены «опубликовано вне панели» (отметка №2)",
        "запись очереди Discord №5 в ошибке закрыта — заметки не опубликованы, записи свободны",
        "в тексте похоже на внутренние детали (античит / EAC, номер персонажа или учётки, стойка и процессы сервера) — игрокам это обычно не нужно, проверьте"]
    check("заметки: тексты отказов, предупреждений и итогов без «; »", all("; " not in t for t in texts), [t for t in texts if "; " in t])
    i18n.set_lang("en")
    data = ("Сервер: x", "Окно обучения больше не закрывает чат.", "• ", "вручную в Discord 20.11", "16.11.2026 — ", "Astory")
    oper = lambda s: re.sub("|".join(re.escape(d) for d in data), "", s)
    try:
        miss = [(t, i18n.tr(t)) for t in texts if CYR.search(oper(i18n.tr(t)))]
    finally:
        i18n.set_lang("ru")
    check("заметки EN: отказы, предупреждения и итоги — без русских слов (%d строк; тексты changelog и оператора — как есть)" % len(texts), not miss, miss[:6])
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("заметки: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js, app, idx, wi = _read(ROOT, "web", "notes.js"), _read(ROOT, "web", "app.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("веб: раздел #/notes с правом notes.view, viewNotes(my), скрипт после outbox.js; без innerHTML; тексты changelog, оператора и предпросмотра — "
          "acText (не T()); кнопки — по правам (notes.draft, community.post); тест — флажок test; expect предпросмотра уходит в применение",
          '["#/notes", "Заметки к выпуску", "notes.view"' in app and 'case "notes": return viewNotes(my);' in app
          and 0 < idx.index("/outbox.js") < idx.index("/notes.js") and "innerHTML" not in js
          and all(x not in js for x in ("T(x.title", "T(x.body", "T(x.ru", "T(x.section", "T(p.preview.text", "T(w)"))
          and 'can["community.post"] && s' in js and 'can["notes.draft"]' in js and "test: test.checked" in js and "{ expect: p.preview.expect }" in js
          and 'dir: dir || null' in js and 'dir: k === "ar" ? "rtl" : "auto"' in js and "x.sens && x.sens.length" in js
          and "filter(x => !(x.sens && x.sens.length))" in js and 'ntRun("notes.resolve"' in js and 'ntRun("notes.hide"' in js)
    q = re.compile(r'"((?:[^"\\]|\\.)*)"')
    code = "\n".join(ln for ln in js.split("\n") if not ln.lstrip().startswith("//"))
    labels = {x for x in q.findall(code) if CYR.search(x)} | {"Заметки к выпуску"}
    have = set(re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(labels - have)
    check("веб EN: у русских строк раздела есть перевод в web/i18n.js (%d строк)" % len(labels), not lack, lack[:8])
    keys_all = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)
    tail = wi[wi.index("★ А7.7 (24.11): «Заметки к выпуску»"):]
    dupk = sorted({x for x in re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail) if keys_all.count(x) > 1})
    check("веб EN: новые ключи web/i18n.js не дублируют прежние", not dupk, dupk[:8])
    for f in ("notes.js", "app.js", "i18n.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("заметки: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("заметки: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- SQL, проверки прав, выкладка
    sql = _read(ROOT, "sql", "adminc_31_notes.sql")
    bs = _batches(sql)
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    body = re.sub(r"--[^\n]*", "", body)
    g_adm = sorted(re.findall(r"GRANT (\w+) ON (adm\.\w+)\s+TO \[asda_admin\]", body))
    want_adm = sorted([("SELECT", "adm.Notes" + t) for t in ("Snap", "Draft", "Post", "PostEntry", "Entry")]
                      + [("EXECUTE", "adm.Notes" + p) for p in ("SnapPut", "DraftSet", "PublishPut", "MarkPut", "EntryPut", "MarkRevoke", "EntrySync",
                                                                "EntryHide", "OutboxClose", "SnapDone")])
    check("adminc_31: QUOTED_IDENTIFIER ON отдельным батчем до CREATE, уровень 100 (нет THROW, IIF, CONCAT, TRY_CONVERT, FORMAT, STRING_SPLIT, "
          "CREATE OR ALTER), asda_admin — SELECT пяти таблиц и десять процедур, DENY прямой записи; asda_reports — ни одного GRANT, DENY всего; "
          "запись очереди — только вид notes в форум updates со статусом 0",
          bs[0].strip().endswith("SET QUOTED_IDENTIFIER ON;") and "CREATE TABLE" not in bs[0]
          and not re.search(r"\b(TRY_CONVERT|TRY_CAST|IIF|FORMAT|THROW|STRING_SPLIT|ISJSON|OPENJSON|CONCAT|STRING_AGG)\b|CREATE OR ALTER", body)
          and g_adm == want_adm and "TO [asda_reports]" in body and not re.search(r"GRANT [^;]*TO \[asda_reports\]", body)
          and all("DENY  INSERT, UPDATE, DELETE ON adm.Notes%s" % t in body for t in ("Snap ", "Draft ", "Post ", "PostEntry ", "Entry "))
          and "SET @code = 7;" in body and "o.error LIKE N'%итог неизвестен%'" in body and "o.kind = 'notes'" in body
          and "VALUES ('notes', 'updates', @role" in body, g_adm)
    ver = _read(ROOT, "sql", "adminc_31_notes_verify.sql")
    s29 = _read(ROOT, "sql", "adminc_29_telegram.sql")
    v10, v99 = _read(ROOT, "sql", "adminc_10_verify.sql"), P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    cli = _read(ROOT, "asda_admin.py")
    check("adminc_31_notes_verify: 17 проверок ПОД asda_reports, все 0; adminc_29: в CK_adm_Outbox_route вид notes только в форум updates; adminc_10 — "
          "SELECT = 1, прямая запись = 0, процедуры панели = 1; adminc_99 — откат шага; выкладка: adminc_31 -x -I после adminc_30, проверка под "
          "asda_reports (17); adminc_28 — код 5 имени ветки; консоль: notes show | push | resync",
          ver.count("UNION ALL SELECT") + 1 == 17 and "AND kind <> 'notes'" in _read(ROOT, "sql", "adminc_28_outbox.sql") and not re.search(r",\s*1(?: AS want)?;?\s*$", ver, re.M)
          and "kind IN ('announce', 'test', 'notes')" in s29 and "AND (kind <> 'notes' OR channel_key = 'updates')" in s29
          and "'adm.NotesPost SELECT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPost','OBJECT','SELECT'), 1" in v10
          and "'adm.NotesPost INSERT', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPost','OBJECT','INSERT'), 0" in v10
          and "'adm.NotesPublishPut EXEC', HAS_PERMS_BY_NAME('AsdaAdmin.adm.NotesPublishPut','OBJECT','EXECUTE'), 1" in v10
          and (v99 is None or "adminc_31_notes.sql" in v99) and (v99 is None or "DROP TABLE IF EXISTS adm.NotesPostEntry, adm.NotesPost, adm.NotesDraft, adm.NotesSnap" in v99)
          and "Run 'adminc_31_notes.sql' 'AsdaAdmin' -xi" in dep and dep.index("Run 'adminc_30_community.sql'") < dep.index("Run 'adminc_31_notes.sql'")
          < dep.index("adminc_10_verify.sql') 2>&1") and "adminc_31_notes_verify.sql" in dep and '("asda_reports/notes", part_notes, 17)' in dep and "SET @code = 5;" in _read(ROOT, "sql", "adminc_28_outbox.sql")
          and 'if cmd == "notes":' in cli and 'def _notes(args):' in cli and "notes …" in cli and 'if sub == "resync":' in cli)
    undoc = [n.name for n in ast.walk(ast.parse(_read(ROOT, "domains", "notes.py"))) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not ast.get_docstring(n)]
    jsf = re.findall(r"\n([^\n]*)\n\s*(?:async )?function (\w+)", js)
    js_undoc = [f for prev, f in jsf if not prev.strip().startswith("//")]
    check("р82 М-6: у каждой функции и класса domains/notes.py — описание; у каждой функции web/notes.js — комментарий над ней", not undoc and not js_undoc,
          (undoc, js_undoc))
    ok_top = True
    src = _read(ROOT, "domains", "notes.py")
    tree = ast.parse(src)
    ok_top &= {type(n).__name__ for n in tree.body} <= {"Expr", "Import", "ImportFrom", "Assign", "FunctionDef", "AsyncFunctionDef", "ClassDef"}
    check("импорт domains/notes без побочных эффектов (верхний уровень — импорты, константы, функции, классы); прямой записи в таблицы adm.* нет "
          "(только процедуры); changelog не пишется (нет open(…, \"w\"), нет записи файлов)",
          ok_top and not re.findall(r"\b(INSERT|UPDATE|DELETE)\s+(INTO\s+)?adm\.", src) and "EXEC adm.NotesPublishPut" in src
          and not re.search(r"open\([^)]*[\"'][wa]b?[\"']", src) and "write(" not in src)


def sandbox(check, ldb):
    """Своя база LocalDB: снимок → черновик → публикация через очередь → настоящий outbox_bot.Store под asda_reports и Worker с подставным Discord."""
    _paths()
    from core import audit, db, ops
    import domains
    domains.load_all()
    from domains import notes as N
    import outbox_bot as B
    from selftest_outbox_a7 import _FakeAdapter
    name = "AsdaNotes_" + secrets.token_hex(3)
    m = ldb("master")
    m.cursor().execute("CREATE DATABASE [%s] COLLATE Cyrillic_General_CI_AS" % name)
    tmp = tempfile.TemporaryDirectory()
    try:
        a = ldb(name)
        s23 = _read(ROOT, "sql", "adminc_23_reports.sql").replace("$(ReportsPw)", "Aa1-" + secrets.token_hex(12))
        s31 = _read(ROOT, "sql", "adminc_31_notes.sql")
        for f in ("adminc_02_schema.sql", "adminc_14_jobs.sql"):
            for b in _batches(_read(ROOT, "sql", f)):
                a.cursor().execute(b)
        for b in (_batches(s23) + _batches(_read(ROOT, "sql", "adminc_27_crashes.sql")) + _batches(_read(ROOT, "sql", "adminc_28_outbox.sql"))
                  + _batches(_read(ROOT, "sql", "adminc_29_telegram.sql")) + _batches(s31) + _batches(s31)):
            a.cursor().execute(b)
        q1 = lambda sql, *p: a.cursor().execute(sql, *p).fetchone()
        check("стенд: настоящие adminc_02 + 14 + 23 + 27 + 28 + 29 + 31 (31 дважды — повтор безопасен): 5 таблиц и 10 процедур adm.Notes*",
              q1("SELECT COUNT(*) FROM sys.tables WHERE name LIKE 'Notes%'")[0] == 5 and q1("SELECT COUNT(*) FROM sys.procedures WHERE name LIKE 'Notes%'")[0] == 10)
        db.set_override("admin", lambda database: ldb(name))
        own, adm, gm = ops.Ctx(None, "own_t", "owner", "", "web"), ops.Ctx(None, "adm_t", "admin", "", "web"), ops.Ctx(None, "gm_t", "gm", "", "web")
        v0 = N.view({})
        snap = {"file": "CHANGELOG_2026-11-16.md", "text": SAMPLE, "md5": __import__("hashlib").md5(SAMPLE.encode("utf-8")).hexdigest(), "host": "PC",
                "collected_utc": "2026-11-24 10:00:00"}
        p1 = N.push_pc("cli:user@PC", snap)
        p2 = N.push_pc("cli:user@PC", snap)
        row = q1("SELECT seen_count, pushed_by FROM adm.NotesSnap WHERE id = ?", p1["id"])
        w_sec = _refused(lambda: N.push_pc("cli:x@PC", dict(snap, text=SAMPLE + "\n-----BEGIN PRIVATE KEY-----\n", md5="0" * 32)))
        w_name = _refused(lambda: N.push_pc("cli:x@PC", dict(snap, file="secret.txt")))
        check("стенд: снимка нет — «changelog с ПК ещё не присылался»; снимок записан (новый), тот же второй раз — только отметка (раз 2), кто прислал — "
              "без имени пользователя Windows; секрет и чужое имя файла — отказ",
              v0["installed"] and v0["snap"] is None and N.NO_SNAP in v0["warnings"] and p1["new"] and not p2["new"] and p1["id"] == p2["id"]
              and tuple(row) == (2, "cli@PC") and w_sec and "закрытый ключ" in w_sec and w_name, (p1, p2, tuple(row), w_sec))
        check("р82 В-2: снимок записан и в постоянный реестр adm.NotesEntry — 8 записей с видом, состоянием и RU",
              q1("SELECT COUNT(*) FROM adm.NotesEntry")[0] == 8 and p1["entries"] == 8 and tuple(q1("SELECT reg_count FROM adm.NotesSnap WHERE id = ?", p1["id"])) == (8,))
        v1 = N.view({})
        ent = v1["entries"]
        keys_def = [x["key"] for x in ent if x["default"]]
        c1 = [x for x in ent if x["title"].startswith("Клиент: окно обучения")][0]
        s1 = [x for x in ent if x["title"].startswith("Сервер: блок не пропадает")][0]
        check("стенд: экран — 8 записей, все «не опубликовано», подсказка заголовка «Astory alpha-8.1.0-11.2026», черновика нет",
              len(ent) == 8 and all(x["pub"] == "free" for x in ent) and v1["title_hint"] == "Astory alpha-8.1.0-11.2026" and v1["draft"] is None, v1["title_hint"])
        dr = ops.run(adm, "notes.draft", dict(_fields(keys_def), snap=v1["snap"]["id"]))
        v2 = N.view({})
        w_gmd = _refused(lambda: ops.run(gm, "notes.draft", _fields(keys_def)))
        check("стенд: черновик сохраняется (admin) и читается: ключи, заголовок, тексты; gm — нет права",
              dr["ok"] and v2["draft"]["keys"] == keys_def and v2["draft"]["title"] == "Astory alpha-8.1.0-11.2026" and v2["draft"]["_by"] == "adm_t"
              and w_gmd and "notes.draft" in w_gmd, v2["draft"])

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
        S = B.Store(connect=_AsBot)
        ad = _FakeAdapter()
        W = B.Worker(S, ledger=B.Ledger(os.path.join(tmp.name, "ledger.json")), limiter=B.Limiter(gap=0, per_hour=1000))
        tick = lambda: asyncio.run(W.tick(ad))
        pick = [c1["key"], s1["key"]]
        prm = dict(_fields(pick), snap=v2["snap"]["id"])
        pv = ops.run(adm, "notes.publish", prm, dry=True)["preview"]
        n0 = q1("SELECT COUNT(*) FROM adm.Outbox")[0]
        w_noexp = _refused(lambda: ops.run(adm, "notes.publish", prm))
        w_exp = _refused(lambda: ops.run(adm, "notes.publish", dict(prm, expect=dict(pv["expect"], md5="0" * 32))))
        r1 = ops.run(adm, "notes.publish", dict(prm, expect=pv["expect"]))
        oid, post = r1["result"]["outbox"], r1["result"]["post"]
        o1 = q1("SELECT kind, channel_key, role_key, title, status, is_test, text_ru FROM adm.Outbox WHERE id = ?", oid)
        v3 = {x["key"]: x for x in N.view({})["entries"]}
        check("стенд: предпросмотр (admin) ничего не пишет и показывает ветку, «ПУБЛИЧНО», длины, «опубликовано — по итогу бота»; без отпечатка "
              "предпросмотра и с чужим — отказ; применение — запись очереди вида notes в форум updates, Patch Ping, статус 0 «ждёт бота», публикация "
              "с 2 записями; записи — «ждёт бота»",
              n0 == 0 and "ветка «Astory alpha-8.1.0-11.2026»" in pv["text"] and "текст в Discord:\n@Patch Ping\n🇬🇧 Tutorial" in pv["text"]
              and any(w.startswith("ПУБЛИЧНО:") for w in pv["warnings"]) and any(w.startswith("длина: сообщение") for w in pv["warnings"])
              and w_noexp == N.EXPECT_CHANGED and w_exp == N.EXPECT_CHANGED
              and tuple(o1) == ("notes", "updates", "patch", "Astory alpha-8.1.0-11.2026", 0, False, "• Окно обучения больше не закрывает чат.")
              and v3[c1["key"]]["pub"] == v3[s1["key"]]["pub"] == "queued" and v3[c1["key"]]["pub_post"] == post, (pv["text"][:200], tuple(o1)))
        w_dup = _refused(lambda: ops.run(own, "notes.publish", dict(_fields([s1["key"]]), snap=v2["snap"]["id"]), dry=True))
        c5 = q1("SET NOCOUNT ON; DECLARE @id INT, @post INT, @code INT, @c2 INT; EXEC adm.NotesPublishPut N't', N'e', NULL, NULL, NULL, 60, N'x', 0, NULL, "
                "@id OUTPUT, @post OUTPUT, @code OUTPUT; EXEC adm.NotesEntryPut @post, ?, '17.11.2026', N't', @c2 OUTPUT; SELECT @c2", s1["key"])[0]
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE kind = 'notes' AND title = N't'")
        check("стенд: та же запись второй раз — отказ и в панели («уже ждёт бота»), и в процедуре (adm.NotesEntryPut код 5)",
              w_dup and "уже ждёт бота" in w_dup and c5 == 5, (w_dup, c5))
        tick()
        o2 = q1("SELECT status, discord_channel_id, discord_message_id FROM adm.Outbox WHERE id = ?", oid)
        v4 = {x["key"]: x for x in N.view({})["entries"]}
        check("стенд: бот (настоящий Store под asda_reports, подставной Discord) публикует ОДИН раз новую ветку форума updates с именем = заголовок, "
              "упоминание <@&202> (Patch Ping); после итога — записи «опубликовано»",
              len(ad.posts) == 1 and ad.posts[0][:3] == (103, "forum", "Astory alpha-8.1.0-11.2026") and ad.posts[0][3].startswith("<@&202>\n🇬🇧 ")
              and ad.posts[0][4] == 202 and tuple(o2) == (2, 9103, 9103) and v4[c1["key"]]["pub"] == "published" and v4[s1["key"]]["pub"] == "published",
              (ad.posts, tuple(o2)))
        aid = r1["audit_id"]
        arow = audit.get(aid)
        w_un_adm = _refused(lambda: ops.undo(adm, aid))
        w_un_op = _refused(lambda: ops.REGISTRY["notes.publish"].undo(ops.Ctx(None, "x", "admin", "", "web"), arow))
        u1 = ops.undo(own, aid)
        d1 = q1("SELECT del_status FROM adm.Outbox WHERE id = ?", oid)[0]
        still = {x["key"]: x["pub"] for x in N.view({})["entries"]}[c1["key"]]
        tick()
        d2 = q1("SELECT del_status FROM adm.Outbox WHERE id = ?", oid)[0]
        v5 = {x["key"]: x for x in N.view({})["entries"]}
        check("стенд: откат опубликованного — только owner (admin — нет права на откат и community.delete); owner — удаление ветки поставлено боту, до "
              "удаления записи ещё «опубликовано», бот удалил ветку — записи снова «не опубликовано»",
              w_un_adm and w_un_op and "community.delete" in w_un_op and u1["ok"] and d1 == 0 and still == "published" and ad.deletes == [(9103, 9103, True)]
              and d2 == 2 and v5[c1["key"]]["pub"] == "free" and v5[s1["key"]]["pub"] == "free", (w_un_adm, w_un_op, d1, d2, ad.deletes))
        # тест: бот не публикует, записи не заняты
        pvt = ops.run(own, "notes.publish", dict(_fields([c1["key"]]), snap=v2["snap"]["id"], test=True), dry=True)["preview"]
        rt = ops.run(own, "notes.publish", dict(_fields([c1["key"]]), snap=v2["snap"]["id"], test=True, expect=pvt["expect"]))
        tick()
        ot = q1("SELECT kind, status, is_test, discord_message_id FROM adm.Outbox WHERE id = ?", rt["result"]["outbox"])
        v6 = {x["key"]: x for x in N.view({})["entries"]}
        w_un_t = _refused(lambda: ops.undo(own, rt["audit_id"]))
        check("стенд: публикация с отметкой «тест» — предпросмотр «ТЕСТ», запись очереди проверочная, бот отмечает «тест» и Discord НЕ вызывает, запись "
              "changelog остаётся «не опубликовано» (только тест), откат — «откатывать нечего»",
              any(w.startswith("ТЕСТ:") for w in pvt["warnings"]) and tuple(ot) == ("notes", 6, True, None) and len(ad.posts) == 1
              and v6[c1["key"]]["pub"] in ("free", "test") and w_un_t and "откатывать нечего" in w_un_t, (tuple(ot), v6[c1["key"]]["pub"]))
        # отмена до публикации
        w_title = _refused(lambda: ops.run(own, "notes.publish", dict(_fields([c1["key"]]), snap=v2["snap"]["id"]), dry=True))
        c7 = q1("SET NOCOUNT ON; DECLARE @id INT, @post INT, @code INT; EXEC adm.NotesPublishPut N'Astory alpha-8.1.0-11.2026', N'e', NULL, NULL, NULL, 60, "
                "N'x', 0, NULL, @id OUTPUT, @post OUTPUT, @code OUTPUT; SELECT @code")[0]
        check("р82 М-3: заголовок ветки, который за сутки уже был в форуме updates, — отказ и в панели, и в процедуре (код 7)",
              w_title and "за сутки уже была" in w_title and c7 == 7, (w_title, c7))
        F2 = lambda keys, **kw: dict(_fields(keys, **kw), snap=v2["snap"]["id"])
        pvc = ops.run(own, "notes.publish", F2([c1["key"]], title="Astory part 2"), dry=True)["preview"]
        rc = ops.run(own, "notes.publish", dict(F2([c1["key"]], title="Astory part 2"), expect=pvc["expect"]))
        uc = ops.undo(own, rc["audit_id"])
        tick()
        oc = q1("SELECT status FROM adm.Outbox WHERE id = ?", rc["result"]["outbox"])[0]
        v7 = {x["key"]: x for x in N.view({})["entries"]}
        check("стенд: откат до публикации — запись очереди отменена (статус 4), бот её не публикует, запись changelog снова свободна",
              uc["ok"] and oc == 4 and len(ad.posts) == 1 and v7[c1["key"]]["pub"] in ("free", "test"), (oc, v7[c1["key"]]["pub"]))
        # отметка «вне панели» и её откат
        w_note = _refused(lambda: ops.run(own, "notes.mark", {"snap": v2["snap"]["id"], "keys": [s1["key"]], "note": "x"}, dry=True))
        pvm = ops.run(own, "notes.mark", {"snap": v2["snap"]["id"], "keys": [s1["key"]], "note": "вручную в Discord 20.11"}, dry=True)["preview"]
        rm = ops.run(own, "notes.mark", {"snap": v2["snap"]["id"], "keys": [s1["key"]], "note": "вручную в Discord 20.11", "expect": pvm["expect"]})
        v8 = {x["key"]: x for x in N.view({})["entries"]}
        w_pub_m = _refused(lambda: ops.run(own, "notes.publish", dict(_fields([s1["key"]]), snap=v2["snap"]["id"]), dry=True))
        um = ops.undo(own, rm["audit_id"])
        v9 = {x["key"]: x for x in N.view({})["entries"]}
        check("стенд: «опубликовано вне панели» — без причины отказ; с причиной запись «опубликовано» (отметка), публиковать её — отказ; откат снимает "
              "отметку — запись снова свободна; Discord не вызывался",
              w_note and v8[s1["key"]]["pub"] == "published" and v8[s1["key"]]["pub_kind"] == "manual" and w_pub_m and "уже опубликована" in w_pub_m
              and um["ok"] and v9[s1["key"]]["pub"] == "free" and len(ad.posts) == 1, (w_note, w_pub_m))
        # ★ р82 М-2: ошибка освобождает, «итог неизвестен» держит до решения, повтор записи заметок запрещён
        def pub(title):
            """Публикация c1 с заголовком title → (номер записи очереди, номер публикации, номер журнала)."""
            pv_ = ops.run(own, "notes.publish", F2([c1["key"]], title=title), dry=True)["preview"]
            r_ = ops.run(own, "notes.publish", dict(F2([c1["key"]], title=title), expect=pv_["expect"]))
            return r_["result"]["outbox"], r_["result"]["post"], r_["audit_id"]
        st_c1 = lambda: {x["key"]: x for x in N.view({})["entries"]}[c1["key"]]["pub"]
        ob, pb, ab_ = pub("Astory part 3")
        a.cursor().execute("UPDATE adm.Outbox SET status = 3, attempts = 1, error = N'канал «updates»: на сервере Discord найдено 0 подходящих (нужен ровно один)' "
                           "WHERE id = ?", ob)
        f_state = st_c1()
        w_retry = _refused(lambda: ops.run(own, "outbox.retry", {"id": ob}, dry=True))
        c_retry = q1("SET NOCOUNT ON; EXEC adm.OutboxRetry ?, N'x', 10", ob)[0]
        uf = ops.undo(own, ab_)
        check("р82 М-2: точный отказ бота — записи сразу свободны («ошибка — записи свободны»); повтор записи заметок — отказ и в панели, и в процедуре; "
              "откат при ошибке — запись очереди закрыта (статус 4)",
              f_state == "failed" and w_retry and "повтор записи не делается" in w_retry and c_retry == 0 and uf["ok"]
              and q1("SELECT status FROM adm.Outbox WHERE id = ?", ob)[0] == 4, (f_state, w_retry, c_retry))
        ou, pu, au = pub("Astory part 4")
        a.cursor().execute("UPDATE adm.Outbox SET status = 3, attempts = 1, error = N'итог неизвестен: бот начал публикацию и прервался — проверьте канал в Discord, "
                           "повторно бот эту запись не публикует' WHERE id = ?", ou)
        u_state = st_c1()
        w_busy = _refused(lambda: ops.run(own, "notes.publish", F2([c1["key"]], title="Astory part 9"), dry=True))
        w_undo_u = _refused(lambda: ops.undo(own, au))
        posts = {x["id"]: x for x in N.view({})["posts"]}
        pvr = ops.run(own, "notes.resolve", {"post": pu, "thread": "none", "note": "проверил форум — ветки нет"}, dry=True)["preview"]
        rr1 = ops.run(own, "notes.resolve", {"post": pu, "thread": "none", "note": "проверил форум — ветки нет", "expect": pvr["expect"]})
        free_after = st_c1()
        oe, pe, ae = pub("Astory part 5")
        a.cursor().execute("UPDATE adm.Outbox SET status = 1, claimed_utc = DATEADD(MINUTE, -30, SYSUTCDATETIME()) WHERE id = ?", oe)
        e_state = st_c1()
        pve = ops.run(own, "notes.resolve", {"post": pe, "thread": "exists", "note": "ветка в форуме есть"}, dry=True)["preview"]
        rr2 = ops.run(own, "notes.resolve", {"post": pe, "thread": "exists", "note": "ветка в форуме есть", "expect": pve["expect"]})
        pub_after = st_c1()
        w_un_none = _refused(lambda: ops.undo(own, rr1["audit_id"]))
        ops.undo(own, rr2["audit_id"])
        back = st_c1()
        check("р82 М-2: «итог неизвестен» (ошибка бота или бот молчит > 10 мин) держит записи — новая публикация и откат отклонены (риск дубля); в истории "
              "— «итог неизвестен» с решением; «ветки нет» — записи свободны (без отката); «ветка есть» — записи «опубликовано» отметкой, её откат — снова свободны",
              u_state == "unknown" and w_busy and "итогом «неизвестен»" in w_busy and w_undo_u and "дубль" in w_undo_u and posts[pu]["state"] == "unknown"
              and posts[pu]["can_resolve"] and rr1["ok"] and free_after in ("free", "test", "failed") and e_state == "unknown" and rr2["ok"]
              and pub_after == "published" and w_un_none and back in ("free", "test", "failed") and len(ad.posts) == 1,
              (u_state, w_busy, w_undo_u, free_after, e_state, pub_after, back))
        # ★ р83 М-7: «ветки нет» по «бот взял» — только когда бот точно не держит захват
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -2, created_utc)")   # предел 6 в час — не мешать проверке
        o6, p6, a6 = pub("Astory part 6")
        a.cursor().execute("UPDATE adm.Outbox SET done_utc = DATEADD(DAY, -2, done_utc) WHERE done_utc IS NOT NULL")
        a.cursor().execute("UPDATE adm.Outbox SET status = 1, claimed_utc = DATEADD(MINUTE, -11, SYSUTCDATETIME()) WHERE id = ?", o6)
        w_hold = _refused(lambda: ops.run(own, "notes.resolve", {"post": p6, "thread": "none", "note": "ветки не вижу"}, dry=True))
        c_hold = q1("SET NOCOUNT ON; EXEC adm.NotesOutboxClose ?, N'x', N'y', 10, 0", o6)[0]
        a.cursor().execute("UPDATE adm.Outbox SET expires_utc = DATEADD(MINUTE, -1, SYSUTCDATETIME()) WHERE id = ?", o6)
        pv6 = ops.run(own, "notes.resolve", {"post": p6, "thread": "none", "note": "ветки не вижу"}, dry=True)["preview"]
        r6 = ops.run(own, "notes.resolve", {"post": p6, "thread": "none", "note": "ветки не вижу", "expect": pv6["expect"]})
        check("р83 М-7: «бот взял» и молчит, но срок годности не прошёл и бот после захвата ни по чему не отчитывался — «ветки нет» отклонено (и в "
              "процедуре); после срока годности — разрешено",
              w_hold and "ещё держит" in w_hold and c_hold == 0 and r6["ok"], (w_hold, c_hold))
        # ★ р83 М-2: имя ветки занято и закрытой записью, которую бот брал; та же проверка в adm.OutboxPut (объявления А7.4)
        a.cursor().execute("UPDATE adm.Outbox SET claimed_utc = DATEADD(MINUTE, -20, SYSUTCDATETIME()) WHERE id = ?", ou)
        taken4 = N._title_taken("Astory part 4")
        from domains import outbox as O
        w_ob5 = _refused(lambda: O.put(O.check(own, {"channel": "updates", "role": "", "en": "e", "ttl": 60}, "Astory alpha-8.1.0-11.2026"), "own_t", hold=False))
        free3 = N._title_taken("Astory part 3")
        check("р83 М-2: имя ветки после «ветки нет» по записи, которую бот брал, — занято; отменённая до бота — свободна; объявление А7.4 в updates с именем "
              "ветки заметок — отказ adm.OutboxPut (код 5)",
              taken4 == ou and free3 is None and w_ob5 == O.PUT_CODES[5], (taken4, free3, w_ob5))
        # пределы частоты — общие с объявлениями (6 в час)
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -2, created_utc)")
        codes = [q1("SET NOCOUNT ON; DECLARE @id INT, @post INT, @code INT; EXEC adm.NotesPublishPut N't%d', N'e', NULL, NULL, NULL, 60, N'x', 0, NULL, "
                    "@id OUTPUT, @post OUTPUT, @code OUTPUT; SELECT @code" % i)[0] for i in range(7)]
        a.cursor().execute("UPDATE adm.Outbox SET status = 4 WHERE status = 0")
        bad_role = q1("SET NOCOUNT ON; DECLARE @id INT, @post INT, @code INT; EXEC adm.NotesPublishPut N't', N'e', NULL, NULL, 'news', 60, N'x', 0, NULL, "
                      "@id OUTPUT, @post OUTPUT, @code OUTPUT; SELECT @code")[0]
        e_chk = None
        try:
            a.cursor().execute("INSERT adm.Outbox (kind, channel_key, title, text_en, created_by, expires_utc) VALUES ('notes', 'announcements', N't', N'e', N'x', SYSUTCDATETIME())")
        except Exception as ex:
            e_chk = str(ex)
        check("стенд: пределы общие с объявлениями — шесть за час, седьмая — код 1; роль не Patch Ping — код 4; вид notes не в форум updates — CHECK",
              codes == [0] * 6 + [1] and bad_role == 4 and e_chk and "CK_adm_Outbox_route" in e_chk, (codes, bad_role, e_chk))
        # ★ р82 В-2: смена файла changelog — опубликованное остаётся опубликованным, неопубликованное не теряется; скрытие; перевод прежних ключей
        c2 = [x for x in N.view({})["entries"] if x["title"].startswith("[ИСПРАВЛЕНИЕ]")][0]
        l1 = [x for x in N.view({})["entries"] if x["title"].startswith("Сервер: заглушка чата действует")][0]
        pvm2 = ops.run(own, "notes.mark", {"snap": v2["snap"]["id"], "keys": [c2["key"], l1["key"]], "note": "вручную 17.11"}, dry=True)["preview"]
        ops.run(own, "notes.mark", {"snap": v2["snap"]["id"], "keys": [c2["key"], l1["key"]], "note": "вручную 17.11", "expect": pvm2["expect"]})
        a.cursor().execute("INSERT adm.NotesPost (kind, title, note, created_by) VALUES ('manual', N'(вне панели)', N'старый ключ', N'x')")
        mpost = q1("SELECT MAX(id) FROM adm.NotesPost")[0]
        a.cursor().execute("INSERT adm.NotesPostEntry (post_id, entry_key, entry_date, entry_title) VALUES (?, ?, '16.11.2026', N't')", mpost, s1["key_v1"])
        rs = ops.run(own, "notes.resync", {})
        mig = q1("SELECT entry_key FROM adm.NotesPostEntry WHERE post_id = ?", mpost)[0]
        s1_pub = {x["key"]: x for x in N.view({})["entries"]}[s1["key"]]["pub"]
        a.cursor().execute("UPDATE adm.NotesPost SET revoked_utc = SYSUTCDATETIME(), revoked_by = N'x' WHERE id = ?", mpost)
        check("р82 В-2: перевод ключей — публикация, сохранённая по прежнему ключу (v1), после notes.resync получает новый ключ, запись снова «опубликовано»",
              rs["ok"] and mig == s1["key"] and s1_pub == "published", (mig, s1["key"], s1_pub))
        text2 = ("## 24.11.2026 — перенесено из прежнего файла\n"
                 "- [ИСПРАВЛЕНИЕ] [клиент, вошло в alpha-8.1.1; перенесено из CHANGELOG_2026-11-16.md] Значок «?» стоит у панели (17.11): теперь всегда видно.\n"
                 "- **Клиент: новая запись нового файла (клиент, следующий выпуск)**\n  Что стало:\n  - Новое.\n"
                 "- **Сервер: заглушка чата действует (сервер, уже действует; перенесено из CHANGELOG_2026-11-16.md)**\n  Что стало:\n  - Заглушка работает.\n"
                 "- **Сервер: чат молчит у нарушителей (сервер, уже действует)**\n  Что стало:\n  - Заглушка работает.\n"
                 "- **[СЕРВЕР / АДМИНКА] Панель открыта на https://@@ASTORY_SERVER_VPN_IP@@:17890/ и @@ASTORY_DEV_ROOT_ESC@@\\port\\x.md**\n")
        p3 = N.push_pc("cli:user@PC", {"file": "CHANGELOG_2026-11-24.md", "text": text2, "md5": __import__("hashlib").md5(text2.encode("utf-8")).hexdigest(),
                                       "host": "PC", "collected_utc": "2026-11-25 10:00:00"})
        v10 = N.view({})
        e10 = {x["key"]: x for x in v10["entries"]}
        check("р82 В-2: новый файл changelog — перенесённая запись с новой меткой и «перенесено из …» сохранила ключ и «опубликовано»; неопубликованные записи "
              "прежнего файла остаются в списке «из файла CHANGELOG_2026-11-16.md»; предупреждение «changelog сменился»",
              p3["new"] and c2["key"] in e10 and not e10[c2["key"]]["old"] and e10[c2["key"]]["pub"] == "published"
              and c1["key"] in e10 and e10[c1["key"]]["old"] and e10[c1["key"]]["file"] == "CHANGELOG_2026-11-16.md"
              and any(w.startswith("changelog сменился (CHANGELOG_2026-11-16.md → CHANGELOG_2026-11-24.md)") for w in v10["warnings"]),
              ([(x["title"][:30], x["old"], x["pub"]) for x in v10["entries"]], v10["warnings"]))
        sim = [x for x in v10["entries"] if x["title"].startswith("Сервер: чат молчит")][0]
        leak = [(x["title"][:30], f) for x in v10["entries"] for f in ("head", "title", "body", "section", "of_title", "similar")
                if isinstance(x.get(f), str) and (N._IP.search(x[f]) or N._PATH.search(x[f]))]
        own_v = N.view({}, role="owner")
        own_ip = any(N._IP.search(x["title"]) for x in own_v["entries"])
        check("р83 В-1 / М-3: перенос со сменой скобки статуса (строка 920) — «опубликовано»; другая запись с тем же «Что стало» — «похоже на уже "
              "опубликованное», без галочки; для не-owner ни в одном поле записей нет IP и путей (owner видит как есть)",
              e10[l1["key"]]["pub"] == "published" and sim["similar"] and not sim["default"] and sim["pub"] == "free" and not leak and own_ip,
              (e10.get(l1["key"], {}).get("pub"), sim["similar"], leak[:3]))
        a.cursor().execute("UPDATE adm.NotesSnap SET reg_done_utc = NULL WHERE id = ?", p3["id"])
        w_part = any("записан не полностью" in w for w in N.view({})["warnings"])
        ops.run(own, "notes.resync", {})
        w_part2 = any("записан не полностью" in w for w in N.view({})["warnings"])
        check("р83 М-4: реестр по снимку без отметки полноты — предупреждение «записан не полностью»; notes.resync ставит отметку — предупреждения нет",
              w_part and not w_part2 and not any("записан не полностью" in w for w in v10["warnings"]), (w_part, w_part2))
        w_hide = _refused(lambda: ops.run(own, "notes.hide", {"keys": [c1["key"]], "hide": True, "note": "x"}, dry=True))
        pvh = ops.run(own, "notes.hide", {"keys": [c1["key"]], "hide": True, "note": "игрокам не нужно"}, dry=True)["preview"]
        rh = ops.run(own, "notes.hide", {"keys": [c1["key"]], "hide": True, "note": "игрокам не нужно", "expect": pvh["expect"]})
        hid = {x["key"]: x for x in N.view({})["entries"]}[c1["key"]]
        w_pub_h = _refused(lambda: ops.run(own, "notes.publish", dict(_fields([c1["key"]], title="Astory part 7"), snap=p3["id"]), dry=True))
        ops.undo(own, rh["audit_id"])
        unhid = {x["key"]: x for x in N.view({})["entries"]}[c1["key"]]
        check("р82 В-2: скрыть запись — без причины отказ; скрытая не отмечается и не публикуется; откат — запись снова видна",
              w_hide and hid["hidden"] and not hid["default"] and w_pub_h and "скрыта" in w_pub_h and not unhid["hidden"], (w_hide, w_pub_h))
        # ★ р84 М-1: хэш «Что стало» хранится в записи публикации (прежние строки — из реестра); тот же ключ с другим «Что стало» — «похоже»
        a.cursor().execute("UPDATE adm.NotesPostEntry SET what_hash = NULL WHERE entry_key = ?", l1["key"])
        for b in _batches(s31):
            a.cursor().execute(b)
        mig_h = q1("SELECT COUNT(*) FROM adm.NotesPostEntry WHERE entry_key = ? AND what_hash = ?", l1["key"], l1["what_hash"])[0]
        text4 = ("## 25.11.2026 — x\n- **Сервер: заглушка чата действует (сервер, уже действует с 25.11)**\n  Что стало:\n"
                 "  - Заглушку можно снять досрочно.\n")
        a.cursor().execute("UPDATE adm.NotesSnap SET reg_count = 99 WHERE id = ?", p3["id"])
        p4 = N.push_pc("cli:user@PC", {"file": "CHANGELOG_2026-11-25.md", "text": text4, "md5": __import__("hashlib").md5(text4.encode("utf-8")).hexdigest(),
                                       "host": "PC", "collected_utc": "2026-11-26 10:00:00"})
        e4 = {x["key"]: x for x in N.view({})["entries"]}[l1["key"]]
        a.cursor().execute("UPDATE adm.Outbox SET created_utc = DATEADD(HOUR, -2, created_utc)")   # предел 6 в час — не мешать проверке
        w_pv4 = _refused(lambda: ops.run(own, "notes.publish", dict(_fields([l1["key"]], title="Astory part 8"), snap=p4["id"]), dry=True))
        reg_ru = q1("SELECT ru FROM adm.NotesEntry WHERE entry_key = ?", l1["key"])[0]
        c_free = q1("SET NOCOUNT ON; DECLARE @post INT, @code INT, @c2 INT; EXEC adm.NotesMarkPut N'проверка р84', N'x', NULL, @post OUTPUT, @code OUTPUT; "
                    "EXEC adm.NotesEntryPut @post, ?, '25.11.2026', N't', @c2 OUTPUT, ?; SELECT @c2", l1["key"], e4["what_hash"])[0]
        c_busy = q1("SET NOCOUNT ON; DECLARE @post INT, @code INT, @c2 INT; EXEC adm.NotesMarkPut N'проверка р84', N'x', NULL, @post OUTPUT, @code OUTPUT; "
                    "EXEC adm.NotesEntryPut @post, ?, '25.11.2026', N't', @c2 OUTPUT, ?; SELECT @c2", l1["key"], e4["what_hash"])[0]
        a.cursor().execute("UPDATE adm.NotesPost SET revoked_utc = SYSUTCDATETIME(), revoked_by = N'x' WHERE note = N'проверка р84'")
        check("р84 М-1 / Н-2: хэш «Что стало» прежних публикаций перенесён из реестра; запись с тем же ключом и другим «Что стало» — не «опубликовано», а "
              "«похоже на уже опубликованное», без галочки, публиковать можно (процедура не считает её занятой, повтор с тем же хэшем — уже занят); "
              "текст опубликованной записи в реестре не перезаписан; отметка полноты нового снимка — по его записям",
              mig_h >= 1 and e4["pub"] == "free" and e4["similar"] and not e4["default"] and w_pv4 is None and "работает" in (reg_ru or "")
              and c_free == 0 and c_busy == 5 and q1("SELECT reg_count FROM adm.NotesSnap WHERE id = ?", p4["id"])[0] == 1,
              (mig_h, e4["pub"], e4["similar"], w_pv4, reg_ru, c_free, c_busy))
        # права asda_reports
        cb = _AsBot()
        deny = []
        for qq in ("SELECT COUNT(*) FROM adm.NotesPost", "SELECT COUNT(*) FROM adm.NotesSnap", "UPDATE adm.NotesPost SET revoked_utc = NULL",
                   "DECLARE @p INT, @c INT; EXEC adm.NotesMarkPut N'xyz', N'x', NULL, @p OUTPUT, @c OUTPUT", "EXEC adm.NotesMarkRevoke 1, N'x'"):
            try:
                cur = cb.cursor().execute(qq)
                if qq.startswith("SELECT"):
                    cur.fetchall()
                deny.append(qq[:40])
            except Exception:
                pass
        vr = [tuple(r) for r in cb.cursor().execute(_read(ROOT, "sql", "adminc_31_notes_verify.sql")).fetchall()]
        cb.close()
        check("стенд: asda_reports — ни таблиц заметок, ни процедур панели; adminc_31_notes_verify под ним — 17 проверок совпали",
              not deny and len(vr) == 17 and all(int(r[1] or 0) == int(r[2]) for r in vr), (deny, [r for r in vr if int(r[1] or 0) != int(r[2])]))
        aud = {r[0]: r[1] for r in a.cursor().execute("SELECT action, COUNT(*) FROM adm.audit WHERE result = 'ok' AND action LIKE 'notes.%' GROUP BY action")}
        fq, _p = _route("/api/notes")

        class _Req:
            def __init__(self, query, role):
                self.query, self.session = dict(query), {"user": {"role": role, "login": "t_" + role}}
        ra = fq(_Req({}, "admin"), None)
        check("стенд: журнал adm.audit — notes.draft 1, publish 7, mark 2, resolve 3, resync 2, hide 1, откаты publish 3, mark 1, resolve 1, hide 1; API — "
              "права роли (admin: черновик и публикация, без удаления и отката), история публикаций",
              aud == {"notes.draft": 1, "notes.publish": 7, "notes.mark": 2, "notes.resolve": 3, "notes.resync": 2, "notes.hide": 1,
                      "notes.publish.undo": 3, "notes.mark.undo": 1, "notes.resolve.undo": 1, "notes.hide.undo": 1}
              and ra["can"]["notes.draft"] and ra["can"]["community.post"] and not ra["can"]["community.delete"] and not ra["can"]["audit.undo"]
              and len(ra["posts"]) >= 4 and ra["installed"], (aud, ra["can"]))
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
    """Живая dev: снимок changelog с ПК, публикация только с отметкой «тест» (бот её не публикует) и захват только проверочных."""
    _paths()
    from core import config, db, ops
    import domains
    domains.load_all()
    from domains import notes as N, outbox as O
    import outbox_bot as B
    if config.get().on_server:
        return check("живой самотест А7.7 «заметки к выпуску» — с ПК", True)
    cn = db.admin()
    try:
        q = lambda o, p: db.admin_rows(cn, "SELECT HAS_PERMS_BY_NAME(?, 'OBJECT', ?) AS p", (o, p))[0]["p"]
        perm = {"sel": q("adm.NotesPost", "SELECT"), "ins": q("adm.NotesPost", "INSERT"), "snap_upd": q("adm.NotesSnap", "UPDATE"),
                "pub": q("adm.NotesPublishPut", "EXECUTE"), "snap": q("adm.NotesSnapPut", "EXECUTE"), "claim": q("adm.OutboxClaim", "EXECUTE")}
    finally:
        cn.close()
    check("живое (asda_admin): adm.Notes* — чтение и процедуры панели, без прямой записи, без процедур бота",
          perm == {"sel": 1, "ins": 0, "snap_upd": 0, "pub": 1, "snap": 1, "claim": 0}, perm)
    S = B.Store()
    try:
        c = S._cn()
        try:
            rows = c.cursor().execute(_read(ROOT, "sql", "adminc_31_notes_verify.sql")).fetchall()
        finally:
            c.close()
        bad = [tuple(r) for r in rows if int(r[1] or 0) != int(r[2])]
        check("живое (путь бота): asda_reports по VPN не видит заметок = adminc_31_notes_verify (%d проверок)" % len(rows), len(rows) == 17 and not bad, bad)
    except Exception as ex:
        check("живое (путь бота): вход asda_reports по VPN", False, "%s: %s" % (type(ex).__name__, str(ex)[:200]))
    cli = ops.Ctx(None, "cli:selftest", "owner", "", "cli")
    rp = ops.run(cli, "notes.push", {})
    v = N.view({})
    ent = v["entries"]
    check("живое: changelog с ПК — notes.push записал снимок №%s (пишет только AsdaAdmin), панель его разобрала: записей %d, ключи уникальны, есть видимые "
          "игрокам" % (rp["result"]["id"], len(ent)),
          v["installed"] and v["snap"] and v["snap"]["id"] == rp["result"]["id"] and len(ent) > 10 and len({x["key"] for x in ent}) == len(ent)
          and any(x["visible"] for x in ent), (v["snap"], len(ent)))
    v0 = O.view({"status": "all"})
    real_q = [r for r in v0["rows"] if not r["test"] and r["state"] in ("queued", "claimed", "hold")]
    free = [x for x in ent if x["pub"] in ("free", "test") and x["visible"]]
    check("живое: в очереди Discord нет настоящих записей, ждущих публикации, и есть свободная запись changelog — самотест ничего не публикует",
          not real_q and free, real_q[:3])
    if real_q or not free:
        return
    prm = {"snap": v["snap"]["id"], "keys": [free[0]["key"]], "title": "selftest A7.7 (test — not published)", "role": "patch", "ttl": 30,
           "en": "selftest — test record, the bot does not publish it", "ru": "", "ar": "", "test": True}
    pv = ops.run(cli, "notes.publish", prm, dry=True)["preview"]
    r = ops.run(cli, "notes.publish", dict(prm, expect=pv["expect"]))
    oid = r["result"]["outbox"]
    got = []
    try:
        got = S.out_claim(1, test_only=True)          # ТОЛЬКО проверочные: настоящие записи этим захватом не берутся
        for x in got:
            if not x["test"]:
                raise RuntimeError("захват test_only вернул НЕ проверочную запись №%d" % x["id"])
        claimed = any(x["id"] == oid for x in got)
        for x in got:
            S.out_done(x["id"], True)                 # проверочная: итог «тест», Discord не вызывается
        S.out_claimed_ok()
    except Exception as ex:
        claimed = "%s: %s" % (type(ex).__name__, str(ex)[:200])
    row = [x for x in O.view({"status": "test"})["rows"] if x["id"] == oid]
    after = {x["key"]: x["pub"] for x in N.view({})["entries"]}
    check("живое: публикация с отметкой «тест» — запись очереди №%d вида notes в форум updates, захват только проверочных (или её уже взял работающий "
          "бот) → «тест», id сообщения Discord нет — в Discord ничего не ушло; запись changelog НЕ стала «опубликованной»" % oid,
          any(w.startswith("ТЕСТ:") for w in pv["warnings"]) and row and row[0]["state"] == "test" and row[0]["kind"] == "notes"
          and row[0]["channel"] == "updates" and not row[0]["posted_at"] and (claimed is True or not got) and after.get(free[0]["key"]) in ("free", "test"),
          (claimed, row[:1], after.get(free[0]["key"])))
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import notes as N\nv = N.view({})\n"
             "print('NTPROBE installed=%s snap=%s n=%d' % (v['installed'], (v['snap'] or {}).get('id'), len(v['entries'])))\n")
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
    mm = re.search(r"NTPROBE installed=(\w+) snap=(\d+) n=(\d+)", out)
    check("служба на сервере (SSH): заметки читаются, тот же снимок №%s и столько же записей" % v["snap"]["id"],
          bool(mm) and mm.group(1) == "True" and int(mm.group(2)) == v["snap"]["id"] and int(mm.group(3)) == len(ent), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/notes" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/notes без входа — 401", code == 401, code)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import selftest as T
    T.utf8_stdout()                         # ★ р82 М-7 / р83 М-6: консоль cp1251 не роняет самотест
    offline(T.check)
    if "--sandbox" in sys.argv:
        sandbox(T.check, T._ldb)
    if "--live" in sys.argv:
        live(T.check)
    bad = [r for r in T.RESULTS if not r[1]]
    print("\nИТОГ: %d проверок, ошибок %d" % (len(T.RESULTS), len(bad)))
    sys.exit(1 if bad else 0)
