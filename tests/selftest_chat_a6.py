# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_chat_a6.py — самотест шага А6.12, часть «панель» (22.11.2026; решение владельца №5 — журнал чата + заглушка, 90 дней; domains/chatlog.py,
sql/adminc_24_chat.sql, проверки adminc_10 / adminc_11, откат adminc_99, /api/chat/*, web/chat.js, консоль chat, операции chat.mute / chat.unmute;
серверная часть — P129 / AsdaPatch v86, AstoryServer/Docs/SQL/chat_01_migrate.sql).

offline(check)  — права (chat.view / chat.mute / chat.unmute — owner, admin, gm), операции с откатом и без второго фактора, маршруты, отказы ввода без
                  базы, базы нет — понятный отказ (не 500), тексты без «; », режим P129 словами, прочтения text_raw, SQL домена (чтение — без
                  fix_text, запись — только EXEC двух процедур), поле chat_text (не text: поле text служба переводит), переводы EN (shadowed = 0),
                  веб без innerHTML, консоль (ключи, --as до базы), adminc_24 (батчи, пропуск без схемы, -x -I в выкладке), adminc_10 / 11 / 99,
                  выкладчик P129 (шаг panel_grants, test_deploy_p129_rollback.py).
sandbox(check, ldb) — СВОИ базы LocalDB: joylog1 (Arabic_CI_AS) — сначала без схемы chat (adminc_24 — «пропущено», журнал — «не установлен», проверки
                  adminc_10 / 11 — строки «как без схемы»), затем НАСТОЯЩИЙ chat_01_migrate.sql и adminc_24 дважды; неполная схема — отказ; Joy1,
                  AsdaStoryOp, AsdaAdmin (adminc_02 — журнал adm.audit). Служба читает ПОД asda_admin, пишет ПОД asda_ops (EXECUTE AS USER):
                  поиск (даты ГГГГММДД — заданные, не от времени запуска; каналы, учётка и соулмейт, персонаж, подстрока кириллицей / латиницей /
                  арабским без учёта регистра, экранирование %, карта, сервер, отметки заглушки, text_raw и прочтения, страницы, глубина, бюджет),
                  заглушки (учётка, персонаж по кириллическому имени, служебная — только owner, отпечаток, повторная, снятие, истёкшая, откат обеих
                  операций, срок вышел), нет прав asda_ops — понятный отказ, права логинов напрямую, откат adminc_99, журнал adm.audit, API.
live(check)     — только чтение живой dev: состояние журнала (схема есть с 22.11 18:50 — «установлен», строки читаются; нет — «не установлен»), режим P129 по копиям, строки проверок
                  adminc_10 о чате под asda_admin, служба на сервере (SSH) видит то же, без входа — 401. В chat.* ничего не пишет.
Побочных эффектов при импорте нет.
"""
import json
import os
import re
import secrets
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = os.path.dirname(ROOT)
SQL_CHAT = os.path.join(PORT, "AstoryServer", "Docs", "SQL")
import selftest_public as P  # noqa: E402  ★ 25.11 (К-3): SKIP проверок, которым нужны файлы только среды разработчика
P129_TOOLS = os.path.join(PORT, "AstoryServer", "Patches", "AsdaPatch", "tools")
CYR = re.compile("[А-Яа-яЁё]")


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


def _batches(text):
    return [b for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]


def _read(*p):
    return open(os.path.join(*p), encoding="utf-8").read()


def _chat_lines(sql_text):
    """Строки проверок о чате из adminc_10 / adminc_11 → SELECT (первая строка — без UNION ALL)."""
    ls = [ln for ln in sql_text.splitlines() if ln.startswith("UNION ALL SELECT '") and ("chat" in ln.split("'")[1])]
    body = "\n".join(ls)
    return "SELECT " + body[len("UNION ALL SELECT "):]


def offline(check):
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import auth, db, i18n, ops
    import domains
    domains.load_all()
    from domains import chatlog as C
    roles = ("owner", "admin", "gm", "support")
    check("чат: права chat.view, chat.mute, chat.unmute — owner, admin, gm (support — нет; решение №3: gm ведёт низкие ступени и их отзыв)",
          all({r for r in roles if auth.can(r, p)} == {"owner", "admin", "gm"} for p in ("chat.view", "chat.mute", "chat.unmute")))
    check("чат: операции chat.mute / chat.unmute — свои права, с откатом, без второго фактора; откат — только audit.undo (owner)",
          ops.REGISTRY["chat.mute"].perm == "chat.mute" and ops.REGISTRY["chat.unmute"].perm == "chat.unmute"
          and ops.REGISTRY["chat.mute"].reversible and ops.REGISTRY["chat.unmute"].reversible
          and not ops.needs_two_factor("chat.mute") and not ops.needs_two_factor("chat.unmute") and auth.PERMS["audit.undo"] == {"owner"})
    rt = {p: _route(p) for p in ("/api/chat/state", "/api/chat/messages", "/api/chat/mutes")}
    check("чат: маршруты /api/chat/state, messages, mutes — GET, право chat.view", all(fn and perm == "chat.view" for fn, perm in rt.values()),
          {p: v[1] for p, v in rt.items()})
    ctx = ops.Ctx(1, "owner_t", "owner", "", "web")
    bad_q = ({"channel": "11"}, {"channel": "x"}, {"char": "x" * 33}, {"char_uid": "5"}, {"char_uid": "x", "char_slot": "1"}, {"char_uid": "5", "char_slot": "300"},
             {"text": "a"}, {"text": "x" * 101}, {"text": "a\x01b"}, {"map": "-1"}, {"server": "Game Server"}, {"mute": "3"}, {"mute_id": "0"},
             {"from": "2026-03-01"}, {"from": "20260230"}, {"from": "20260310", "to": "20260301"}, {"text": "ищу", "from": "20260301"},
             {"text": "ищу", "from": "20260101", "to": "20260301"})
    why = [_refused(lambda q=q: C.build_filters(q)) for q in bad_q]
    why += [_refused(lambda q=q: C.messages(q)) for q in ({"size": "0"}, {"size": "201"}, {"page": "x"}, {"page": "60", "size": "200"})]
    why += [_refused(lambda q=q: C.mutes(q)) for q in ({"state": "x"}, {"size": "500"})]
    why += [_refused(lambda p=p: ops.REGISTRY["chat.mute"].preview(ctx, p)) for p in (
        {"scope": "account", "uid": 9001, "minutes": 0, "reason": "спам"}, {"scope": "account", "uid": 9001, "minutes": 5256001, "reason": "спам"},
        {"scope": "account", "uid": 9001, "minutes": "x", "reason": "спам"}, {"scope": "account", "uid": 9001, "minutes": 60, "reason": "ab"},
        {"scope": "account", "uid": 9001, "minutes": 60, "reason": "a\nb c d"}, {"scope": "account", "uid": 9001, "minutes": 60, "reason": "x" * 257},
        {"scope": "account", "uid": 9001, "minutes": 60}, {"scope": "account", "uid": 9001, "minutes": 60, "reason": None})]
    why += [_refused(lambda p=p: ops.REGISTRY["chat.unmute"].preview(ctx, p)) for p in ({"mute_id": "x", "reason": "ошибка"}, {"mute_id": 5, "reason": ""}, {})]
    check("чат: отказы ввода без обращения к базе (%d: каналы, персонаж, слот, подстрока, карта, сервер, отметка, даты и окно поиска по тексту, "
          "страницы, состояние заглушек, срок, причина, номер заглушки)" % len(why), all(why), [i for i, w in enumerate(why) if not w])

    def nodb(database):
        raise db.DbError("нет подключения к %s: Login timeout expired" % database)
    db.set_override("game", nodb)
    try:
        wn = [_refused(lambda: C.messages({})), _refused(lambda: C.mutes({})), _refused(lambda: C.state(with_p129=False)),
              _refused(lambda: ops.REGISTRY["chat.unmute"].preview(ctx, {"mute_id": 1, "reason": "ошибка"}))]
    finally:
        db.set_override("game", None)
    check("чат: базы нет — отказ «журнал чата не прочитан: нет подключения …» (409, не 500)",
          all(w and w.startswith("журнал чата не прочитан: нет подключения") for w in wn), wn)
    why += wn
    check("чат: тексты отказов без «; »", all("; " not in x for x in why if x), [x for x in why if x and "; " in x])
    from api import server as SV0
    S = C.p129_summary
    check("чат: режим P129 словами — не выложен (секции нет), Mode=0 «только помечает», Mode=1 «действует», выключен, смешанно, не прочитано",
          "ещё не выложен" in S({"GameServer": "absent", "Ch2_GameServer": "absent"}, {}) and "Mode=0" in S({"GameServer": "journal"}, {})
          and "действует" in S({"GameServer": "active"}, {}) and "выключен" in S({"GameServer": "off"}, {})
          and "по-разному" in S({"GameServer": "active", "Ch2_GameServer": "absent"}, {}) and "не прочитан" in S({"GameServer": "unread"}, {}))
    lim = [_refused(lambda: C._minutes(1441, ops.Ctx(3, "gm_t", "gm", "", "web"))), _refused(lambda: C._minutes(1440, ops.Ctx(3, "gm_t", "gm", "", "web"))),
           _refused(lambda: C._minutes(1441, ops.Ctx(2, "admin_t", "admin", "", "web"))), _refused(lambda: C._minutes(5256000, ops.Ctx(1, "o", "owner", "", "web")))]
    check("чат (р71 Н-3): пределы роли — одно место ROLE_LIMITS; gm — не дольше 1440 мин (граница: 1440 можно, 1441 — отказ), снимает только свои; "
          "admin / owner — без пределов (до 5 256 000)", C.ROLE_LIMITS == {"gm": {"max_minutes": 1440, "unmute_own_only": True}}
          and lim[0] and "не дольше 1440 мин" in lim[0] and lim[1:] == [None, None, None] and C.limits_of("gm")["unmute_own_only"]
          and C.limits_of("admin") == {"max_minutes": 5256000, "unmute_own_only": False}, lim)
    rf = [C.refresh_sec({"refresh": {"A": "30", "B": "x", "C": "20"}}), C.refresh_sec({"refresh": {"A": "1"}}), C.refresh_sec({"read": False}),
          C.refresh_sec({"refresh": {"A": "5000"}})]
    check("чат (р71 М-2): «не позже чем через N с» — фактический MuteRefreshSec копий (наибольший), вне 2…3600 и не прочитано — 15",
          rf == [30, 15, 15, 15], rf)
    code_api = _read(ROOT, "api", "server.py")
    i18n.set_lang("en")
    try:
        tr_note = SV0._tr_fields({"p129": {"read": True, "mode_note": S({"GameServer": "journal"}, {})}})["p129"]["mode_note"]
    finally:
        i18n.set_lang("ru")
    check("чат (р71 Н-2): режим P129 — поле mode_note (в TR_KEYS, служба переводит; EN без русских слов), веб выводит его через T()",
          "mode_note" in SV0.TR_KEYS and not CYR.search(tr_note) and 'T(p129.mode_note || "")' in _read(ROOT, "web", "chat.js")
          and '"mode_note": p129_summary' in _read(ROOT, "domains", "chatlog.py") and "limits=chatlog.limits_of(role)" in code_api, tr_note)
    rv = C.raw_views(b"\x98" + "مرحبا".encode("cp1256"))
    rv2 = C.raw_views("ok да".encode("cp1251"))
    check("чат: text_raw — hex и прочтения cp1251 / UTF-8 / cp1256 (маркер 0x98 + cp1256 читается арабским)",
          rv["hex"].startswith("98 ") and "مرحبا" in rv["cp1256"] and rv["len"] == 6 and rv2["cp1251"] == "ok да" and C.raw_views(None) is None)
    code = _read(ROOT, "domains", "chatlog.py")
    body = code.split('"""', 2)[2]
    from api import server as SV
    check("чат: чтение — _reader (GameReader joylog1 с arabic=False: NVARCHAR без fix_text), запись — только EXEC chat.UP_ChatMuteSet / "
          "UP_ChatMuteLift логином asda_ops (нет INSERT / UPDATE / DELETE в SQL домена); текст сообщения — поле chat_text, а не text (служба переводит text)",
          "r.arabic = False" in body and sorted(set(re.findall(r"EXEC (chat\.\w+)", body))) == ["chat.UP_ChatMuteLift", "chat.UP_ChatMuteSet"]
          and not re.search(r"\b(INSERT|UPDATE|DELETE)\s+(chat|dbo|adm)\.", body) and '"chat_text": x["text"]' in body
          and "text" in SV.TR_KEYS and "chat_text" not in SV.TR_KEYS and '"text": x["text"]' not in body)
    mig = P.dev_text(SQL_CHAT, "chat_01_migrate.sql")              # ★ 25.11 (К-3): AstoryServer/Docs/SQL — только среда разработчика
    check("чат: срок хранения 90 суток, кэш сервера 15 с, служебные ≤ 5000, предел срока = процедуре (5 256 000 мин), каналы 1…10 и опкоды = chat_01_migrate.sql",
          C.RETENTION_DAYS == 90 and C.REFRESH_SEC == 15 and C.SVC_MAX == 5000 and C.MINUTES_MAX == 5256000
          and [c for c, _n, _o in C.CHANNELS] == list(range(1, 11)) and (mig is None or ("@Minutes > 5256000" in mig
          and all(re.search(r"\b%d [^,]*?%d" % (c, o), mig) for c, _n, o in C.CHANNELS[:9]) and "10 крик предметом" in mig)))
    # ---- переводы
    i18n.set_lang("en")
    try:
        ru = [x for x in why if x] + [
            C.NOT_INSTALLED, C.PARTIAL % "chat.v_recent", C.GRANTS_MISSING, S({"GameServer": "absent"}, {}), S({"GameServer": "journal"}, {}),
            S({"GameServer": "active"}, {}), S({"GameServer": "off"}, {}), S({"GameServer": "unread"}, {}), S({"GameServer": "active", "Ch2": "absent"}, {}),
            "поиск по тексту чата — не больше 12 в минуту на пользователя, подождите", "поиск по тексту чата — не больше 40 в минуту на всю службу, подождите",
            "дальше 10000 строк журнал не листается — сузьте фильтр или интервал дат", "персонажа «Кирилл» нет",
            "персонажей с именем «Bob» несколько — укажите учётку и слот", "по «1234» нашлось несколько учёток (номер и логин) — укажите номер",
            "нужна учётка (номер или логин) или персонаж", "учётки №9 нет", "у учётки №9 нет персонажа в слоте 3", "цель заглушки не прочитана: запрос к Joy1: x",
            "заглушки служебных учёток (номер ≤ 5000) ставит и снимает только владелец", "заглушка не записана: запись в joylog1: x",
            "процедура заглушки не вернула номер — заглушка не записана", "режим P129 не прочитан: настройки патчей не прочитаны: x",
            "заглушка начнёт действовать не позже чем через 15 с — сервер перечитывает заглушки раз в 15 с",
            "на учётку — все её персонажи и вход соулмейтом с неё", "на персонажа — кто бы им ни играл (хозяин и слот)",
            "GM-флаг сессии не глушится (ExemptOperators=1 по умолчанию)", "у цели уже есть действующая заглушка №3 до 2026-03-10 10:00 UTC — новая добавится рядом",
            "заглушить учётку №9001 (boblogin) на 60 мин. (до 2026-03-10 10:00 UTC): спам", "заглушить персонажа Кирилл (учётка №9002, слот 11) на 60 мин. (до 2026-03-10 10:00 UTC): мат",
            "заглушки цели изменились с предпросмотра — откройте заново", "заглушка №3: учётка №9001 (boblogin) до 2026-03-10 10:00 UTC",
            "заглушка №3: персонаж Кирилл (учётка №9002, слот 11) до 2026-03-10 10:00 UTC", "в журнале нет номера заглушки — откат не выполнен",
            "заглушка №3 уже не действует (снята или истекла) — откатывать нечего", "заглушка №3 снята откатом записи №7", "заглушки №3 нет",
            "заглушка №3 уже снята (gm_t, 2026-03-10 10:00)", "заглушка №3 уже истекла (2026-01-01 00:00 UTC)",
            "снятие дойдёт до GameServer не позже чем через 15 с — сервер перечитывает заглушки раз в 15 с",
            "снять заглушку №3 (учётка №9001, до 2026-03-10 10:00 UTC, поставил gm_t: спам): ошибка",
            "снять заглушку №3 (персонаж Кирилл, учётка №9002, слот 11, до 2026-03-10 10:00 UTC, поставил gm_t: мат): ошибка",
            "заглушка №3 изменилась с предпросмотра — откройте заново", "заглушка №3 уже не действует — снимать нечего", "заглушка №3 снята",
            "в журнале нет данных заглушки — откат не выполнен", "срок заглушки №3 уже вышел (2026-01-01 00:00 UTC) — ставить снова нечего",
            "заглушка снова поставлена откатом записи №7: №4 до 2026-03-10 10:00 UTC", "журнал чата не прочитан: запрос к joylog1: x", "учётка не найдена: запрос к AsdaStoryOp: x",
            "в каталоге настроек AsdaPatch нет секции P129_ChatLog (исходник старше v86)",
        ] + [ops.REGISTRY[n].title for n in ("chat.mute", "chat.unmute")]
        miss = [(x, i18n.tr(x)) for x in ru if CYR.search(i18n.tr(x).replace("Кирилл", "").replace("спам", "").replace("мат", "").replace("ошибка", ""))]
        check("чат EN: отказы, предпросмотры, итоги и предупреждения — без русских слов (%d строк)" % len(ru), not miss, miss[:6])
    finally:
        i18n.set_lang("ru")
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import selftest_patchcfg_a5 as P
    sh, n2 = P.shadowed_translations()
    check("чат: перехватов переводов нет (shadowed_translations = 0 из %d образцов)" % n2, not sh, sh[:5])
    # ---- веб
    js = _read(ROOT, "web", "chat.js")
    app = _read(ROOT, "web", "app.js")
    idx = _read(ROOT, "web", "index.html")
    wi = _read(ROOT, "web", "i18n.js")
    rp = _read(ROOT, "web", "reports.js")
    cs = _read(ROOT, "web", "cases.js")
    check("чат веб: раздел #/chat с правом chat.view, маршрут viewChat(my, q), скрипт после acjournal.js, reports.js и cases.js; переходы из карточки учётки, "
          "жалобы (цель) и дела — «Сообщения в чате» за период (chFrom), жалобы принимают ?target=",
          '["#/chat", "Журнал чата", "chat.view"' in app and 'case "chat": return viewChat(my, q);' in app
          and 0 < idx.index("/acjournal.js") < idx.index("/cases.js") < idx.index("/reports.js") < idx.index("/chat.js")
          and '"#/chat?account=" + uid' in app and "chFrom(r.created, 7)" in rp and "chFrom(c.opened_at, 7)" in cs and 'q.get("target")' in rp)
    check("чат веб: без innerHTML, данные — текстовыми узлами (acText / acTable); текст сообщения — chat_text; сырые байты — по флажку raw; действия — "
          "предпросмотр → подтверждение → запись с expect; снять — только действующую и служебную только владельцу; 15 с — на экране",
          "innerHTML" not in js and "acText(x.chat_text)" in js and 'raw: rawIn.checked ? "1" : ""' in js and "expect: pv.expect" in js
          and 'x.state === "active" && c["chat.unmute"] && (!x.service || st.role === "owner") && (!(st.limits || {}).unmute_own_only || x.by === st.login)' in js and "st.refresh_sec" in js
          and "T(x.chat_text" not in js and "T(x.reason" not in js and "T(x.char" not in js)
    labels = set(re.findall(r'h\("(?:h1|h2|h3|th|span|button|label|div|a)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) | set(re.findall(r'\["([^"\]]+)", [a-z]+ =>', js)) \
        | set(re.findall(r'T\("([^"]+)"', js)) | set(re.findall(r'placeholder: "([^"]+)"', js)) | set(re.findall(r'\}, "([^"]+)"\)', js))
    for name in ("CH_MUTE", "CH_MST", "CH_SCOPE"):
        i = js.index("const " + name)
        labels |= set(re.findall(r':\s*"([^"]+)"', js[i:js.index("\n", i)]))
    i = js.index("const CH_TERMS")
    labels |= set(re.findall(r'"([^"]*[А-Яа-я][^"]*)"', js[i:js.index("\n", i)]))
    labels |= {n for _c, n, _o in C.CHANNELS} | {"Журнал чата", "Чат учётки", "Сообщения в чате"}
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("чат веб EN: у подписей раздела и названий каналов есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack, lack[:8])
    keys = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', wi)          # ключ — строка, за которой «:» и строка-перевод (значение «:» не продолжается)
    tail = wi[wi.index("★ А6.12 (22.11): «Журнал чата»"):]
    mine = re.findall(r'"((?:[^"\\]|\\.)+)":\s*"', tail)
    dup = sorted({k for k in mine if keys.count(k) > 1})
    check("чат веб EN: новые ключи web/i18n.js не дублируют прежние", not dup, dup[:8])
    for f in ("chat.js", "app.js", "i18n.js", "reports.js", "cases.js"):
        try:
            r = subprocess.run(["node", "--check", os.path.join(ROOT, "web", f)], capture_output=True, timeout=60)
            check("чат: node --check web/%s" % f, r.returncode == 0, r.stderr[-300:])
        except (OSError, subprocess.SubprocessError) as ex:
            check("чат: node --check web/%s (node не запустился)" % f, False, str(ex))
    # ---- консоль
    py = sys.executable

    def con(*a):
        p = subprocess.run([py, os.path.join(ROOT, "asda_admin.py"), "chat"] + list(a), capture_output=True, timeout=120, cwd=ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
    res = [con("log", "--bogus"), con("nope"), con("mute", "--uid", "9001", "--minutes", "5", "--reason", "спам"),
           con("mute", "--as", "x"), con("unmute", "--as", "x", "--mute-id", "3"), con("undo", "--as", "x", "--audit", "x"), con("log", "--text"),
           con("mute", "--as", "x", "--uid", "1", "--char", "Bob", "--minutes", "5", "--reason", "спам")]
    check("чат консоль: неизвестный ключ, неизвестное действие, действие без --as, нет цели, нет причины, неверный --audit, ключ без значения, "
          "--char вместе с --uid — отказ без обращения к базе",
          res[0][0] and "неизвестный аргумент --bogus" in res[0][1] and res[1][0] and "нужно действие" in res[1][1]
          and res[2][0] and "--as <логин панели>" in res[2][1] and res[3][0] and "нужна цель" in res[3][1] and res[4][0] and "--reason" in res[4][1]
          and res[5][0] and "--audit N" in res[5][1] and res[6][0] and "нет значения" in res[6][1] and res[7][0] and "не вместе" in res[7][1],
          [x[1][-160:] for x in res])
    # ---- SQL, выкладка
    s24 = _read(ROOT, "sql", "adminc_24_chat.sql")
    bt = _batches(s24)
    v10 = _read(ROOT, "sql", "adminc_10_verify.sql")
    v11 = _read(ROOT, "sql", "adminc_11_verify_ops.sql")
    rb = P.dev_text(ROOT, "sql", "adminc_99_rollback.sql")
    dep = _read(ROOT, "deploy", "deploy_admin_center.py")
    check("adminc_24: QUOTED_IDENTIFIER ON отдельным батчем до USE; без схемы — PRINT «пропущено» (без RAISERROR), неполная — RAISERROR; выдачи внутри "
          "EXEC(); asda_admin — SELECT 4 объектов и DENY записи и процедур; asda_ops — EXECUTE двух процедур и SELECT chat.mute, DENY остального; "
          "своих $(…) нет",
          any("SET QUOTED_IDENTIFIER ON" in b and "USE" not in b for b in bt[:2]) and "adminc_24: пропущено" in s24 and "chat_01_migrate.sql) - права не выданы" in s24
          and s24.count("EXEC(N'GRANT") == 2 and "GRANT EXECUTE ON chat.UP_ChatMuteSet TO [asda_ops]" in s24 and "GRANT EXECUTE ON chat.UP_ChatMuteLift TO [asda_ops]" in s24
          and "GRANT SELECT ON chat.mute TO [asda_ops]" in s24 and "DENY SELECT, INSERT, UPDATE, DELETE ON chat.message TO [asda_ops]" in s24
          and all("GRANT SELECT ON chat.%s TO [asda_admin]" % o in s24 for o in ("message", "mute", "v_recent", "v_mute_active"))
          and "DENY EXECUTE ON chat.UP_ChatMuteSet TO [asda_admin]" in s24 and "$(" not in s24.split("*/", 1)[1])
    check("adminc_24 выкладка: Run после adminc_21 и adminc_22 с -x -I; строка итога «ПРОПУЩЕНО» / «выданы»; adminc_10 / 11 — строки о чате со схемой и без, "
          "«исполняемых» в JoyLog1 — 2 + 2 при схеме chat; откат adminc_99 — снятие выдач chat до удаления пользователя joylog1",
          dep.index("Run 'adminc_21_san.sql'") < dep.index("Run 'adminc_24_chat.sql' $null -xi") and "if ($xi) { $a += @('-x','-I') }" in dep
          and "adminc_24: пропущено" in dep and "log.chat.message SELECT" in v10 and "ops.chat.UP_ChatMuteSet EXEC" in v11
          and "THEN 2 ELSE 0 END" in v11 and "sc.name NOT IN ('san', 'chat')" in v11
          and (rb is None or rb.index("REVOKE ALL ON chat.") < rb.index("USE [joylog1];        IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_admin') DROP USER"))
          and (rb is None or rb.index("REVOKE ALL ON chat.") < rb.index("USE [JoyLog1];        IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'asda_ops') DROP USER"))   # ★ р71 М-4
          and "'ops.chat.v_recent SELECT'" in v11 and "'ops.chat.v_mute_active SELECT'" in v11)                                                # ★ р71 М-3
    dp = _read(P129_TOOLS, "deploy_p129.py")
    check("выкладчик P129: после chat_01_migrate.sql — шаг panel_grants (копия adminc_24 панели на сервере, sqlcmd -x -I; нет файла / сбой — "
          "предупреждение, DLL выкладка не останавливается); сухой прогон его называет",
          "def panel_grants(lines)" in dp and dp.index("install_sql(lines)\n") < dp.index("        panel_grants(lines)", dp.index("install_sql(lines)\n"))
          and "adminc_24_chat.sql" in dp and "-x -I" in dp.split("def panel_grants", 1)[1].split("def ", 1)[0])
    try:
        r = subprocess.run([py, os.path.join(P129_TOOLS, "stand_p129", "test_deploy_p129_rollback.py")], capture_output=True, timeout=120,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
        check("выкладчик P129: test_deploy_p129_rollback.py (откат + шаг panel_grants на модели) — код 0", r.returncode == 0 and "bad=0" in out, out[-400:])
    except (OSError, subprocess.SubprocessError) as ex:
        check("выкладчик P129: test_deploy_p129_rollback.py", False, str(ex))


class _As:
    """Соединение LocalDB под пользователем базы (EXECUTE AS USER); закрытие — REVERT до возврата в пул."""

    def __init__(self, cn, user):
        self.__dict__["c"] = cn
        cn.cursor().execute("EXECUTE AS USER = '%s'" % user)

    def __getattr__(self, k):
        return getattr(self.__dict__["c"], k)

    def __setattr__(self, k, v):
        setattr(self.__dict__["c"], k, v)

    def close(self):
        c = self.__dict__["c"]
        try:
            try:
                c.rollback()
            except Exception:
                pass
            c.autocommit = True
            c.cursor().execute("REVERT")
        finally:
            c.close()


def sandbox(check, ldb):
    """Свои базы LocalDB: схема chat настоящим chat_01_migrate.sql, права adminc_24, служба под asda_admin / asda_ops (см. шапку)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import db, ops
    import domains
    domains.load_all()
    from domains import chatlog as C
    tag = secrets.token_hex(3)
    names = {"L": "AsdaChL_" + tag, "P": "AsdaChP_" + tag, "Y": "AsdaChY_" + tag, "O": "AsdaChO_" + tag, "A": "AsdaChA_" + tag}
    m = ldb("master")
    for k, n in names.items():
        m.cursor().execute("CREATE DATABASE [%s] COLLATE %s" % (n, "Cyrillic_General_CI_AS" if k == "A" else "Arabic_CI_AS"))
    L = names["L"]
    p129_0, budget0 = C.p129_mode, (C.TEXT_PER_MIN, C.TEXT_ALL_MIN)
    s24 = _read(ROOT, "sql", "adminc_24_chat.sql").replace("USE [joylog1];", "USE [%s];" % L)
    mig = _read(SQL_CHAT, "chat_01_migrate.sql").replace("USE joylog1;", "USE [%s];" % L)
    v10 = _chat_lines(_read(ROOT, "sql", "adminc_10_verify.sql")).replace("joylog1.", L + ".")
    v11 = _chat_lines(_read(ROOT, "sql", "adminc_11_verify_ops.sql")).replace("JoyLog1.", L + ".")
    rb = _read(ROOT, "sql", "adminc_99_rollback.sql")
    _i = rb.index("/* 22.11: журнал чата А6.12")
    rb_chat = rb[_i:rb.index("END\nGO", _i) + len("END\nGO")].replace("USE [joylog1];", "USE [%s];" % L)

    def run(text, dbn=L):
        c = ldb(dbn)
        msgs = []
        try:
            for b in _batches(text):
                cur = c.cursor()
                cur.execute(b)
                msgs += [str(x[1]) for x in (cur.messages or [])]
                while cur.nextset():
                    msgs += [str(x[1]) for x in (cur.messages or [])]
        finally:
            c.close()
        return " ".join(msgs)

    def verify(sql, user):
        c = _As(ldb(L), user)
        try:
            rows = [tuple(r) for r in c.cursor().execute(sql).fetchall()]
        finally:
            c.close()
        return rows, [r for r in rows if int(r[1]) != int(r[2])]
    try:
        lc = ldb(L).cursor()
        for u in ("asda_admin", "asda_ops"):
            lc.execute("CREATE USER [%s] WITHOUT LOGIN" % u)
        # как adminc_03 (asda_admin: db_datareader + запрет записи и EXECUTE на базу) и adminc_04 / adminc_21 (asda_ops: без прав на базу)
        lc.execute("ALTER ROLE db_datareader ADD MEMBER [asda_admin]")
        lc.execute("DENY INSERT, UPDATE, DELETE, EXECUTE TO [asda_admin]")
        a = ldb(names["A"])
        for b in _batches(_read(ROOT, "sql", "adminc_02_schema.sql")):
            a.cursor().execute(b)
        # ---- 1. схемы chat нет
        out0 = run(s24)
        r10, b10 = verify(v10, "asda_admin")
        r11, b11 = verify(v11, "asda_ops")
        check("чат стенд: схемы chat нет — adminc_24 «пропущено» без ошибки, проверки adminc_10 / 11 — строка «absent» и ожидания совпали",
              "adminc_24: пропущено" in out0 and not b10 and not b11 and any("absent" in r[0] for r in r10) and any("absent" in r[0] for r in r11)
              and len(r10) >= 12 and len(r11) >= 11, (out0[:200], b10, b11))
        mp = {"Joy1": names["Y"], "AsdaStoryOp": names["O"]}

        def game(database):
            return _As(ldb(L), "asda_admin") if database == "joylog1" else ldb(mp.get(database, database))
        db.set_override("game", game)
        db.set_override("ops", lambda database: _As(ldb(L), "asda_ops"))
        db.set_override("admin", lambda database: ldb(names["A"]))
        C.p129_mode = lambda force=False: {"read": True, "modes": {"GameServer": "journal"}, "mode": {"GameServer": "0"},
                                           "refresh": {"GameServer": "20", "Ch2_GameServer": "x"},
                                           "mode_note": C.p129_summary({"GameServer": "journal"}, {})}
        own = ops.Ctx(1, "owner_t", "owner", "", "web")
        adm_ = ops.Ctx(2, "admin_t", "admin", "", "web")
        gm = ops.Ctx(3, "gm_t", "gm", "", "web")
        sup = ops.Ctx(4, "sup_t", "support", "", "web")
        try:
            st0 = C.state()
            m0, u0 = C.messages({}), C.mutes({})
            w0 = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "account", "uid": 9001, "minutes": 60, "reason": "спам в общем чате سب"}, dry=True))
            check("чат стенд: схемы нет — состояние, журнал и заглушки «журнал чата не установлен (P129 …)» без ошибки; заглушка — отказ тем же текстом",
                  st0["installed"] is False and st0["note"] == C.NOT_INSTALLED and m0["installed"] is False and m0["note"] == C.NOT_INSTALLED
                  and m0["rows"] == [] and u0["installed"] is False and w0 == C.NOT_INSTALLED and st0["p129"]["read"], (st0.get("note"), m0.get("note"), w0))
            # ---- неполная схема (своя база P)
            run("EXEC('CREATE SCHEMA chat'); CREATE TABLE chat.message (msg_id BIGINT);", names["P"])
            try:
                run(s24.replace("USE [%s];" % L, "USE [%s];" % names["P"]), names["P"])
                part = None
            except Exception as ex:
                part = str(ex)
            check("чат стенд: неполная схема chat — adminc_24 отказ RAISERROR «схема chat неполная … права не выданы»", bool(part) and "неполная" in part, part)
            # ---- 2. настоящая миграция и выдачи (дважды — повтор безопасен)
            run(mig)
            run(mig)
            out1 = run(s24) + run(s24)
            r10, b10 = verify(v10, "asda_admin")
            r11, b11 = verify(v11, "asda_ops")
            check("чат стенд: настоящий chat_01_migrate.sql дважды, adminc_24 дважды — «OK»; проверки adminc_10 (asda_admin) и adminc_11 (asda_ops) о чате — "
                  "все совпали, строка «present»", "adminc_24: OK" in out1 and not b10 and not b11 and any("present" in r[0] for r in r10 + r11), (b10, b11))
            deny = []
            for user, q in (("asda_admin", "EXEC chat.UP_ChatMuteSet 1, 9001, NULL, NULL, 5, N'x', N'y'"), ("asda_admin", "INSERT chat.mute (scope, user_index, until_utc, reason, created_by) VALUES (1, 9001, '2030-01-01', N'x', N'y')"),
                            ("asda_ops", "INSERT chat.mute (scope, user_index, until_utc, reason, created_by) VALUES (1, 9001, '2030-01-01', N'x', N'y')"),
                            ("asda_ops", "SELECT COUNT(*) FROM chat.message"), ("asda_ops", "EXEC chat.UP_ChatMuteActive"), ("asda_ops", "EXEC chat.UP_ChatJournalPurge 90"),
                            ("asda_ops", "UPDATE chat.mute SET reason = N'z'"), ("asda_admin", "DELETE chat.message")):
                c = _As(ldb(L), user)
                try:
                    cur = c.cursor()
                    cur.execute(q)
                    try:
                        cur.fetchall()
                    except Exception:
                        pass
                    deny.append((user, q[:40]))
                except Exception:
                    pass
                finally:
                    c.close()
            c = _As(ldb(L), "asda_ops")
            try:
                c.autocommit = False
                okset = c.cursor().execute("SET NOCOUNT ON; EXEC chat.UP_ChatMuteSet 1, 9001, NULL, NULL, 5, N'проба', N't'").fetchall()
                c.rollback()
            finally:
                c.close()
            check("чат стенд: права напрямую — asda_admin без процедур и записи, asda_ops без прямой записи chat.mute, без журнала и кэша DLL; "
                  "процедура заглушки asda_ops — работает (в откатываемой транзакции)", not deny and okset and okset[0][0], deny)
            # ---- данные: учётки и персонажи
            y = ldb(names["Y"]).cursor()
            y.execute("CREATE TABLE dbo.Charinfo (Userindex INT, Charidx TINYINT, Charname VARCHAR(20), Lvl INT)")
            y.execute("CREATE TABLE dbo.Del_Charinfo (Edate DATETIME, Userindex INT, Charidx TINYINT, Charname VARCHAR(20), Lvl INT)")
            y.execute("INSERT dbo.Charinfo VALUES (9001, 10, 'Bob', 33), (9002, 11, CONVERT(varchar(20), 0xCAE8F0E8EBEB), 5), (100, 0, 'GMa', 1)")
            o = ldb(names["O"]).cursor()
            o.execute("CREATE TABLE dbo.Us_member (Userindex INT PRIMARY KEY, Us_id VARCHAR(61), us_block TINYINT)")
            o.execute("INSERT dbo.Us_member VALUES (9001, 'boblogin', 0), (9002, 'kir', 0), (100, 'gmsvc', 0)")
            # ---- сообщения (даты заданы — не от времени запуска; ev_utc = ev_local по смещению часов этого сервера, как у DLL)
            ar = "مرحبا بك"
            raw_ar = b"\x98" + ar.encode("cp1256")
            raw_ok = "ok да".encode("cp1251")
            ins = ("INSERT chat.message (ev_utc, ev_local, server_name, server_port, map_index, channel, channel_name, sub_channel, opcode, user_num, user_index, "
                   "char_owner, char_slot, char_name, session_state, gm_flag, target_name, target_user_num, text, text_raw, mute_state, mute_id) "
                   "VALUES (DATEADD(MINUTE, DATEDIFF(MINUTE, SYSDATETIME(), SYSUTCDATETIME()), CAST(? AS datetime2(3))), CAST(? AS datetime2(3)), ?, 9001, ?, ?, ?, "
                   "NULL, ?, 1, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)")
            rows = [("2026-03-10 10:00:00", "GameServer", 1, 1, "обычный", 5084, 9001, 9001, 10, "Bob", 1, 0, None, "Привет МИР", None, 0, None),
                    ("2026-03-10 11:00:00", "GameServer", 1, 2, "глобальный", 5086, 9001, 9001, 10, "Bob", 1, 0, None, "hello World 50%", None, 0, None),
                    ("2026-03-11 09:00:00", "Indun_GameServer", 3, 4, "шёпот", 5088, 9002, 9002, 11, "Кирилл", 1, 0, "Bob", ar, raw_ar, 0, None),
                    ("2026-03-11 10:00:00", "GameServer", 1, 1, "обычный", 5084, 9002, 9002, 11, "Кирилл", 1, 0, None, "ok да", raw_ok, 2, 77),
                    ("2026-03-12 08:00:00", "Ch2_GameServer", 2, 5, "отряд", 5105, 9001, 9002, 11, "Кирилл", 2, 0, None, "через соулмейта", None, 0, None),
                    ("2026-03-12 09:00:00", "GameServer", 1, 2, "глобальный", 5086, 100, 100, 0, "GMa", 1, 1, None, "объявление", None, 1, 78),
                    ("2026-01-01 00:00:00", "GameServer", 1, 1, "обычный", 5084, 9001, 9001, 10, "Bob", 1, 0, None, "старое", None, 0, None)]
            pl = ldb(L).cursor()
            for (t, srv, mp_, ch, chn, opc, u, own_, sl, nm, ss, gmf, to, tx, raw, ms, mid) in rows:
                pl.execute(ins, (t, t, srv, mp_, ch, chn, opc, u, own_, sl, nm, ss, gmf, to, tx, raw, ms, mid))
            W = {"from": "20260310", "to": "20260312"}
            q = lambda **k: C.messages(dict(W, **k), user="t_user")
            a_ = q()
            ids = [x["chat_text"] for x in a_["rows"]]
            check("чат стенд: журнал за 10–12.03.2026 (даты параметром) — 6 строк, новые сверху, старая (01.01) не попала; логины, служебная, GM",
                  a_["total"] == 6 and ids[0] == "объявление" and "старое" not in ids and a_["rows"][0]["service"] and a_["rows"][0]["gm"]
                  and a_["rows"][-1]["login"] == "boblogin" and a_["rows"][-1]["channel_title"] == "обычный", (a_["total"], ids))
            ch1, ch45 = q(channel="1"), q(channel="4,5")
            acc_n, acc_l, ch_b, ch_s = q(account="9001"), q(account="kir"), q(char="bob"), q(char_uid="9002", char_slot="11")
            check("чат стенд: каналы (1 — 2 строки, 4,5 — 2), учётка — и сессии, и хозяин (9001 — 3 с соулмейтом, логин kir — 3), персонаж по имени без учёта "
                  "регистра (bob — 2), по хозяину и слоту (9002/11 — 3)",
                  ch1["total"] == 2 and ch45["total"] == 2 and acc_n["total"] == 3 and acc_l["total"] == 3 and ch_b["total"] == 2 and ch_s["total"] == 3,
                  (ch1["total"], ch45["total"], acc_n["total"], acc_l["total"], ch_b["total"], ch_s["total"]))
            t_cy, t_la, t_ar, t_pc, t_us = q(text="мир"), q(text="WORLD"), q(text="مرحبا"), q(text="50%"), q(text="0_")
            check("чат стенд: подстрока параметром без учёта регистра — кириллица (мир → «Привет МИР»), латиница (WORLD), арабский; % и _ — как знаки, "
                  "не шаблон", t_cy["total"] == 1 and t_la["total"] == 1 and t_ar["total"] == 1 and t_ar["rows"][0]["chat_text"] == ar
                  and t_pc["total"] == 1 and t_us["total"] == 0, (t_cy["total"], t_la["total"], t_ar["total"], t_pc["total"], t_us["total"]))
            mp3, srv, mu_any, mu2, mu1, mu_id = q(map="3"), q(server="Indun_GameServer"), q(mute="any"), q(mute="2"), q(mute="1"), q(mute_id="77")
            check("чат стенд: карта, сервер, отметка заглушки (любая — 2, помечено — 1, отклонено — 1), номер заглушки",
                  mp3["total"] == 1 and srv["total"] == 1 and mu_any["total"] == 2 and mu2["total"] == 1 and mu1["total"] == 1 and mu_id["total"] == 1
                  and mu2["rows"][0]["mute_title"].startswith("помечено") and mu1["rows"][0]["mute_title"] == "отклонено заглушкой")
            rw = q(raw="1", char_uid="9002", char_slot="11")
            byid = {x["chat_text"]: x for x in rw["rows"]}
            check("чат стенд: text_raw по ключу raw — шёпот: hex с маркера 98, прочтение cp1256 = арабский, текст в журнале без искажения (без fix_text); "
                  "«ok да» — прочтение cp1251; без raw — байтов нет",
                  byid[ar]["raw"]["hex"].startswith("98 ") and ar in byid[ar]["raw"]["cp1256"] and byid["ok да"]["raw"]["cp1251"] == "ok да"
                  and byid["через соулмейта"]["raw"] is None and "raw" not in a_["rows"][0] and byid[ar]["to"] == "Bob" and byid[ar]["map"] == 3)
            pg2 = q(size="2", page="2")
            deep = _refused(lambda: q(size="200", page="51"))
            check("чат стенд: страницы (по 2 — страница 2 из 3) и предел глубины 10000", pg2["pages"] == 3 and len(pg2["rows"]) == 2 and pg2["page"] == 2
                  and deep and "10000" in deep, (pg2["pages"], deep))
            dflt = C.messages({}, user="t_user")
            ok_txt = C.messages({"text": "мир"}, user="t_user")
            check("чат стенд: без дат — последние 2 суток (заданные даты 2026-03 туда не попадают, пометка default_days); поиск по тексту без дат — в том же окне",
                  dflt["default_days"] == 2 and dflt["total"] == 0 and ok_txt["total"] == 0 and a_["default_days"] is None)
            C.TEXT_PER_MIN = 3
            try:
                C._text_hits.clear()
                hits = [_refused(lambda: C._budget("u1", now=1000.0 + i)) for i in range(4)]
                later = _refused(lambda: C._budget("u1", now=1070.0))
                other = _refused(lambda: C._budget("u2", now=1003.5))
            finally:
                C.TEXT_PER_MIN, C.TEXT_ALL_MIN = budget0
                C._text_hits.clear()
            check("чат стенд: бюджет поиска по тексту на пользователя (на подставных часах: 4-й за минуту — отказ, через минуту — снова можно, другой "
                  "пользователь — свой счёт)", hits[:3] == [None] * 3 and hits[3] and "на пользователя" in hits[3] and later is None and other is None, hits)
            # ---- заглушки
            st1 = C.state()
            pv = ops.run(gm, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 60, "reason": "спам в общем чате سب"}, dry=True)
            w = pv["preview"]["warnings"]
            ap = ops.run(gm, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 60, "reason": "спам в общем чате سب", "expect": pv["preview"]["expect"]})
            mid1 = ap["result"]["mute_id"]
            r1 = ldb(L).cursor().execute("SELECT scope, user_index, char_slot, created_by, reason, DATEDIFF(SECOND, created_utc, until_utc) FROM chat.mute "
                                         "WHERE mute_id = ?", mid1).fetchone()
            check("чат стенд: chat.mute gm на учётку — предпросмотр («заглушить учётку №9001 (boblogin) на 60 мин.», 15 с, Mode=0 «только помечает»), "
                  "запись процедурой: scope 1, без слота, кто — логин панели, срок 60 мин",
                  st1["installed"] and pv["preview"]["text"].startswith("заглушить учётку №9001 (boblogin) на 60 мин.") and any("через 20 с" in x for x in w)
                  and any("Mode=0" in x for x in w) and pv["preview"]["expect"] == {"active": []} and tuple(r1[:5]) == (1, 9001, None, "gm_t", "спам в общем чате سب")
                  and abs(int(r1[5]) - 3600) <= 1, (pv["preview"]["text"], tuple(r1)))
            pv2 = ops.run(gm, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 30, "reason": "повтор"}, dry=True)
            stale = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 30, "reason": "повтор", "expect": {"active": []}}))
            check("чат стенд: вторая заглушка той же цели — предупреждение «уже есть действующая №…», запись по устаревшему отпечатку — отказ",
                  any(("заглушка №%d" % mid1) in x for x in pv2["preview"]["warnings"]) and pv2["preview"]["expect"] == {"active": [mid1]}
                  and stale and "изменились с предпросмотра" in stale, (pv2["preview"]["warnings"], stale))
            pc = ops.run(adm_, "chat.mute", {"scope": "char", "char": "кирилл", "minutes": 1440, "reason": "оскорбления"}, dry=True)
            apc = ops.run(adm_, "chat.mute", {"scope": "char", "char": "кирилл", "minutes": 1440, "reason": "оскорбления", "expect": pc["preview"]["expect"]})
            rc = ldb(L).cursor().execute("SELECT scope, user_index, char_slot, char_name FROM chat.mute WHERE mute_id = ?", apc["result"]["mute_id"]).fetchone()
            check("чат стенд: chat.mute на персонажа по кириллическому имени без учёта регистра — хозяин 9002, слот 11, имя «Кирилл» (Юникод)",
                  tuple(rc) == (2, 9002, 11, "Кирилл") and "персонажа Кирилл (учётка №9002, слот 11)" in pc["preview"]["text"], tuple(rc))
            # ★ р71 Н-1: персонаж по логину и слоту; Н-3: пределы роли gm — срок и чужие заглушки
            pl_ = ops.run(own, "chat.mute", {"scope": "char", "login": "kir", "idx": 11, "minutes": 10, "reason": "проба"}, dry=True)
            g_max = ops.run(gm, "chat.mute", {"scope": "account", "uid": "9001", "minutes": C.ROLE_LIMITS["gm"]["max_minutes"], "reason": "проба"}, dry=True)
            g_over = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "account", "uid": "9001", "minutes": C.ROLE_LIMITS["gm"]["max_minutes"] + 1,
                                                                 "reason": "проба"}, dry=True))
            a_over = ops.run(adm_, "chat.mute", {"scope": "account", "uid": "9001", "minutes": C.ROLE_LIMITS["gm"]["max_minutes"] + 1, "reason": "проба"}, dry=True)
            g_other = _refused(lambda: ops.run(gm, "chat.unmute", {"mute_id": apc["result"]["mute_id"], "reason": "чужая"}, dry=True))
            a_other = ops.run(adm_, "chat.unmute", {"mute_id": mid1, "reason": "проба"}, dry=True)
            check("чат стенд (р71 Н-1 / Н-3): заглушка на персонажа по логину и слоту (kir/11 → Кирилл); gm — ровно 1440 мин можно, 1441 — отказ, "
                  "admin — 1441 можно; gm снимает только свои (заглушку admin — отказ), admin — и чужие (gm)",
                  "персонажа Кирилл (учётка №9002, слот 11)" in pl_["preview"]["text"] and g_max["dry"] and g_over and "не дольше 1440 мин" in g_over
                  and a_over["dry"] and g_other and "только свои" in g_other and "admin_t" in g_other and a_other["dry"], (g_over, g_other))
            svc_gm = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "account", "uid": "100", "minutes": 10, "reason": "проба"}, dry=True))
            svc_own = ops.run(own, "chat.mute", {"scope": "account", "uid": "100", "minutes": 10, "reason": "проба"}, dry=True)
            nop = _refused(lambda: ops.run(sup, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 10, "reason": "проба"}, dry=True))
            nouid = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "account", "uid": "9555", "minutes": 10, "reason": "проба"}, dry=True))
            noslot = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "char", "uid": "9001", "idx": 3, "minutes": 10, "reason": "проба"}, dry=True))
            nochar = _refused(lambda: ops.run(gm, "chat.mute", {"scope": "char", "char": "Никто", "minutes": 10, "reason": "проба"}, dry=True))
            check("чат стенд: служебная (≤ 5000) — gm отказ «только владелец», owner — можно; support — нет права; учётки / слота / персонажа нет — отказы",
                  svc_gm and "только владелец" in svc_gm and svc_own["preview"]["text"].startswith("заглушить учётку №100") and nop and "нет права" in nop
                  and nouid == "учётки №9555 нет" and noslot == "у учётки №9001 нет персонажа в слоте 3" and nochar == "персонажа «Никто» нет",
                  (svc_gm, nop, nouid, noslot, nochar))
            ldb(L).cursor().execute("INSERT chat.mute (scope, user_index, char_slot, char_name, until_utc, reason, created_by) VALUES "
                                    "(1, 9002, NULL, NULL, '2026-01-01', N'старая', N'gm_t')")
            mid_old = ldb(L).cursor().execute("SELECT MAX(mute_id) FROM chat.mute").fetchone()[0]
            lst_a, lst_e, lst_all = C.mutes({}), C.mutes({"state": "expired"}), C.mutes({"state": "all", "account": "kir"})
            check("чат стенд: список заглушек — действующие 2, истёкшие 1 (до 2026-01-01), фильтр по учётке (kir — 2), счётчики",
                  lst_a["total"] == 2 and lst_e["total"] == 1 and lst_e["rows"][0]["state"] == "expired" and lst_all["total"] == 2
                  and lst_a["counts"] == {"active": 2, "expired": 1, "lifted": 0} and lst_a["rows"][0]["login"] == "kir", (lst_a["counts"], lst_all["total"]))
            exp_r = _refused(lambda: ops.run(gm, "chat.unmute", {"mute_id": mid_old, "reason": "ошибка"}, dry=True))
            pu = ops.run(gm, "chat.unmute", {"mute_id": mid1, "reason": "ошибся учёткой"}, dry=True)
            au = ops.run(gm, "chat.unmute", {"mute_id": mid1, "reason": "ошибся учёткой", "expect": pu["preview"]["expect"]})
            again = _refused(lambda: ops.run(gm, "chat.unmute", {"mute_id": mid1, "reason": "ещё раз"}, dry=True))
            lifted = ldb(L).cursor().execute("SELECT lifted_by, lift_reason FROM chat.mute WHERE mute_id = ?", mid1).fetchone()
            check("чат стенд: chat.unmute — истёкшая — отказ «уже истекла», действующая — снята процедурой (кто, почему), повторно — «уже снята»",
                  exp_r and "уже истекла" in exp_r and au["ok"] and tuple(lifted) == ("gm_t", "ошибся учёткой") and again and "уже снята" in again
                  and "через 20 с" in " ".join(pu["preview"]["warnings"]), (exp_r, again))
            # откат снятия → снова на остаток; откат постановки → снята
            ru = ops.undo(own, au["audit_id"])
            new_id = ru["result"]["mute_id"]
            rr = ldb(L).cursor().execute("SELECT scope, user_index, DATEDIFF(SECOND, (SELECT until_utc FROM chat.mute WHERE mute_id = ?), until_utc), created_by, "
                                         "reason FROM chat.mute WHERE mute_id = ?", mid1, new_id).fetchone()
            gm_undo = _refused(lambda: ops.undo(gm, ap["audit_id"]))
            rm = ops.undo(own, apc["audit_id"])
            rm_row = ldb(L).cursor().execute("SELECT lifted_by, lift_reason FROM chat.mute WHERE mute_id = ?", apc["result"]["mute_id"]).fetchone()
            rm2 = _refused(lambda: ops.undo(own, apc["audit_id"]))
            check("чат стенд: откат chat.unmute (owner) — новая заглушка той же учётки до прежнего срока (± минута, округление вверх), причина «откат снятия»; "
                  "причина с арабским — без искажения (запись без fix_text); откат chat.mute — снята «откат записи журнала №…»; gm откатывать не может; повторный откат — отказ",
                  new_id != mid1 and rr[0] == 1 and rr[1] == 9001 and -1 <= int(rr[2]) <= 61 and rr[3] == "owner_t" and rr[4].startswith("откат снятия") and rr[4].endswith("спам в общем чате سب")
                  and rm["ok"] and rm_row[0] == "owner_t" and rm_row[1].startswith("откат записи журнала №") and gm_undo and "нет права на откат" in gm_undo
                  and rm2 and "уже откачена" in rm2, (tuple(rr), tuple(rm_row), gm_undo, rm2))
            # откат снятия, когда срок исходной уже вышел (в журнале «до» — прошлое)
            pu2 = ops.run(own, "chat.unmute", {"mute_id": new_id, "reason": "снять снова"}, dry=True)
            au2 = ops.run(own, "chat.unmute", {"mute_id": new_id, "reason": "снять снова", "expect": pu2["preview"]["expect"]})
            aj = json.loads(a.cursor().execute("SELECT after_json FROM adm.audit WHERE id = ?", au2["audit_id"]).fetchone()[0])
            aj["until_utc"] = "2026-01-01 00:00:00"
            a.cursor().execute("UPDATE adm.audit SET after_json = ? WHERE id = ?", json.dumps(aj, ensure_ascii=False), au2["audit_id"])
            late = _refused(lambda: ops.undo(own, au2["audit_id"]))
            check("чат стенд: откат снятия после конца срока — отказ «срок заглушки … уже вышел», заглушка не ставится", late and "уже вышел" in late, late)
            # нет прав у asda_ops — понятный отказ
            run(rb_chat)
            r11, b11 = verify(v11, "asda_ops")
            grants = _refused(lambda: ops.run(own, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 10, "reason": "проба"}, dry=True))
            check("чат стенд: откат adminc_99 (блок чата) снял выдачи — проверка adminc_11 видит, что EXECUTE у asda_ops нет; заглушка — понятный отказ "
                  "«нет прав … adminc_24»", grants == C.GRANTS_MISSING and {r[0] for r in b11} >= {"ops.chat.UP_ChatMuteSet EXEC", "ops.chat.mute SELECT"},
                  (grants, b11))
            run(s24)
            okg = ops.run(own, "chat.mute", {"scope": "account", "uid": "9001", "minutes": 10, "reason": "проба"}, dry=True)
            check("чат стенд: adminc_24 повторно после отката выдач — заглушки снова доступны", okg["ok"] and okg["dry"])
            aud = {r[0]: r[1] for r in a.cursor().execute("SELECT action, COUNT(*) FROM adm.audit WHERE action LIKE 'chat.%' AND result = 'ok' GROUP BY action")}
            refd = a.cursor().execute("SELECT COUNT(*) FROM adm.audit WHERE action LIKE 'chat.%' AND result = 'refused'").fetchone()[0]
            fs, _p = _route("/api/chat/state")
            fm, _p2 = _route("/api/chat/messages")

            class _Req:
                def __init__(self, query, role):
                    self.query, self.session = dict(query), {"user": {"role": role, "login": "t_" + role}}
            rs = fs(_Req({}, "gm"), None)
            rmq = fm(_Req(dict(W, text="мир"), "gm"), None)
            check("чат стенд: журнал adm.audit — chat.mute 2, chat.unmute 2, откаты chat.mute.undo 1 и chat.unmute.undo 1 (ok), отказы записаны; API — состояние "
                  "с правами роли (gm: заглушить и снять — да, откат — нет), поиск",
                  aud == {"chat.mute": 2, "chat.unmute": 2, "chat.mute.undo": 1, "chat.unmute.undo": 1} and refd >= 1 and rs["installed"]
                  and rs["can"]["chat.mute"] and rs["can"]["chat.unmute"] and not rs["can"]["audit.undo"] and rmq["total"] == 1, (aud, refd))
        finally:
            db.set_override("game", None)
            db.set_override("ops", None)
            db.set_override("admin", None)
            C.p129_mode = p129_0
            C.TEXT_PER_MIN, C.TEXT_ALL_MIN = budget0
    finally:
        m2 = ldb("master")
        for n in names.values():
            try:
                m2.cursor().execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % n)
                m2.cursor().execute("DROP DATABASE [%s]" % n)
            except Exception:
                pass


def live(check):
    """Только чтение живой dev и службы на сервере; в chat.* ничего не пишет (P129 выложен 22.11 18:50 — схема есть; без схемы проверяется «не установлен»)."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config, db
    import domains
    domains.load_all()
    from domains import chatlog as C
    if config.get().on_server:
        return check("живой самотест А6.12 «журнал чата» — с ПК", True)
    st = C.state()
    if not st["installed"]:
        m0, u0 = C.messages({}), C.mutes({})
        check("живое: схемы chat на живой нет — состояние, журнал и заглушки «журнал чата не установлен (P129, AsdaPatch v86 — ждёт общего рестарта)», "
              "без ошибок", st["note"] == C.NOT_INSTALLED and m0["note"] == C.NOT_INSTALLED and u0["note"] == C.NOT_INSTALLED and m0["rows"] == [], st.get("note"))
    else:
        m1 = C.messages({})
        check("живое: схема chat установлена — журнал читается (строк %s, последняя %s), заглушек действует %d" % (st["rows"], st["newest"], st["mutes_active"]),
              m1["installed"] and isinstance(m1["rows"], list))
    p = st["p129"] or {}
    check("живое: режим P129 по копиям GameServer прочитан (%s)" % (p.get("mode_note") or p.get("error")), bool(p.get("read")), p)
    cn = db.admin()
    try:
        sql = _chat_lines(_read(ROOT, "sql", "adminc_10_verify.sql"))
        rows = [tuple(r) for r in cn.cursor().execute(sql).fetchall()]          # столбцы без имён — не admin_rows (dict склеил бы их)
    finally:
        cn.close()
    bad = [r for r in rows if int(r[1]) != int(r[2])]
    check("живое (asda_admin): строки adminc_10 о чате (%d) совпали — %s" % (len(rows), next((r[0] for r in rows if "schema" in r[0]), "?")),
          len(rows) >= 12 and not bad, bad)
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom domains import chatlog as C\nS = C.state(with_p129=False)\n"
             "print('CHPROBE installed=%s note=%s' % (S['installed'], S.get('note') == C.NOT_INSTALLED))\n")
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    ssh = exe if os.path.exists(exe) else "ssh"
    try:
        p2 = subprocess.run([ssh, "-i", config.SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config.SSH_HOST,
                             r'cmd /c "cd /d @@ASTORY_SERVER_ROOT@@\AdminCenter && set PYTHONIOENCODING=utf-8 && '
                             r'@@ASTORY_SERVER_PYTHON@@ -"'],
                            input=probe.encode("utf-8"), capture_output=True, timeout=300)
        out = (p2.stdout + p2.stderr).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as ex:
        out = "ssh: %s" % ex
    mm = re.search(r"CHPROBE installed=(\w+) note=(\w+)", out)
    check("служба на сервере (SSH): журнал чата в том же состоянии, что с ПК (установлен: %s)" % st["installed"],
          bool(mm) and mm.group(1) == str(st["installed"]) and (st["installed"] or mm.group(2) == "True"), out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/chat/state" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/chat/state без входа — 401", code == 401, code)
