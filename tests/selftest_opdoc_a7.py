# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""selftest_opdoc_a7.py — самотест шага А7.10 «Справка по операциям» (24.11.2026; core/opdoc.py, /api/opdoc, справка в ответе предпросмотра
/api/ops, web/help.js, блок «Что изменится / Перезапуск / Откат» окна подтверждения в web/app.js).

offline(check) — ПОЛНОТА: у каждой операции core.ops.REGISTRY есть справка (writes / restart / undo / help и название EN), тексты RU по-русски, EN
                 без кириллицы, коды из списков, reversible ↔ undo «журнал», обратные операции существуют, лишних записей нет — новая операция без
                 справки или без перевода роняет самотест. ВЫБОРОЧНАЯ СВЕРКА С КОДОМ (исходник класса операции и её баз без комментариев и
                 строк документации): очередь Discord / команды боту / рестарт стойки с объявлением → writes Discord, sendMessage → Telegram (и
                 только у telegram.ping), команды моста → «живой сервер», удаление (DROP, уборка файлов и строк, удаление из Discord) у
                 неоткатываемой → «необратимо», рестарт стойки → restart «стойка», клиентские файлы → «данные клиента» и «выпуск», текст «пишется
                 только база панели AsdaAdmin» → writes только AsdaAdmin (и ПК); явный список необратимых и пишущих наружу по разборам
                 разделов. Тексты без «; », локализованный каталог EN без кириллицы, права = core/auth.PERMS. Веб: маршрут /api/opdoc (status.view),
                 справка в ответе предпросмотра, страница #/help в меню и маршрутизаторе, help.js в index.html, окно подтверждения берёт справку,
                 без innerHTML, переводы подписей в web/i18n.js. Импорт core.opdoc без побочных эффектов.
live(check)    — служба на сервере (SSH): тот же каталог полон по реестру службы (столько же операций), без входа GET /api/opdoc — 401.
Побочных эффектов при импорте нет.
"""
import ast
import inspect
import os
import re
import subprocess
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CYR = re.compile("[А-Яа-яЁё]")

# Признаки кода → чего требуют от справки (регулярное выражение по исходнику класса и его баз без комментариев и документации)
DISCORD_RX = re.compile(r"outbox\.put\(|OutboxRetry|OutboxDelete|NotesPublishPut|PlayerReportReply|BotCmdRetry|\b_restart\(|\bbuild_argv\(|"
                        r"(?<![\w.])put\((?:cmd|self\.cmd)\b|_undo_put\(")
TELEGRAM_RX = re.compile(r"test_put\(['\"]ping['\"]")
LIVE_RX = re.compile(r"bridge\.(?:call|live_call|enqueue|kick_and_wait)\(")
DELETE_RX = re.compile(r"\bDROP\b|os\.remove\(|\.unlink\(|OutboxDelete|BakDrop|ReportFilePurge|ReleasePcPrune|(?<![\w.])prune\(|delete_alogs\(")
STACK_RX = re.compile(r"\b_restart\(|\bbuild_argv\(")          # shopcs._restart / stack.build_argv — команда restart_stack.py
CLIENT_RX = re.compile(r"client_write\(")
PANEL_ONLY_TXT = "пишется только база панели AsdaAdmin"
# Исключения признаков — с причиной (по коду)
DISCORD_EXEMPT = {"stack.start": "restart_stack.py --start-only — объявления нет (игроков нет)"}

# Явная сверка (шапки domains/*.py, вызываемые скрипты и ревизия 85): что необратимо, что пишет наружу
IRREVERSIBLE = {"account.create", "account.create_service", "account.set_password", "char.restore", "db.bakdrop", "db.prune", "crash.alog_prune",
                "outbox.delete", "telegram.ping", "report.reply", "live.kick", "live.notice", "live.announce", "reports.purge", "release.prune",
                "users.reset_password", "self.password", "shop.cs_released",
                # ★ ревизия 85: рестарт (объявление, отключение, сброс CharPos), точка спавна мобов до рестарта, ротация бэкапов, «взята», сбросы
                "stack.restart", "live.mob_pop", "live.mob_return", "db.backup", "report.take", "rank.recalc", "camp.rank_rebuild", "daily.reset",
                "notes.draft"}
DISCORD = {"community.app.decide", "community.tester.add", "community.tester.remove", "community.warns.clear", "community.ban", "community.unban",
           "community.cmd.retry", "outbox.retry", "outbox.delete", "notes.publish", "report.reply", "live.announce", "stack.restart", "stack.stop",
           "shop.cs_server_apply", "shop.cs_server_rollback"}
NOT_DISCORD = {"community.test", "community.ban.check", "community.cmd.cancel", "outbox.test", "outbox.cancel", "telegram.test", "telegram.ping",
               "notify.rule.set", "notes.draft", "notes.push", "notes.resync", "stack.start"}
TELEGRAM = {"telegram.ping", "notify.rule.set"}          # ★ р85 М-5: включение общего выключателя сразу ставит сводку за 7 суток
STACK_RESTART = {"stack.restart", "stack.stop", "stack.start", "shop.cs_server_apply", "shop.cs_server_rollback", "live.mob_pop", "live.mob_return"}
# ★ ревизия 85 М-7: удаление в ВЫЗЫВАЕМЫХ функциях (на два уровня) у неоткатываемой операции — «необратимо» или «обратной операцией»; исключения:
REACH_DELETE_EXEMPT = {"db.restore_stand": "удаляет только скачанный на ПК файл и базу стенда LocalDB — живое не трогается",
                       "shop.cs_client_dry": "только временная папка сухого прогона", "shop.cs_server_dry": "только манифест сухого прогона на ПК"}
# ★ ревизия 85 М-7: явная карта «операция → внешние эффекты вызываемого скрипта» (restart_stack.py: шаги 4б2 / 4в — EXEC UP_AsdaDungeonRelogReset и
#   UP_AsdaCharPosReset в Joy1 перед каждым стартом, кроме --stop-only; announce_restart.py — объявление в Discord, кроме --start-only)
RESTART_STACK_DB = {"stack.restart", "stack.start", "shop.cs_server_apply", "shop.cs_server_rollback"}
NAME_RX = re.compile(r"(?<![\w.])([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?\(")
# Исключение признака «только база панели»: сама запись — одна строка AsdaAdmin, следствие вне неё — с причиной
PANEL_ONLY_EXEMPT = {"notify.rule.set": "пишется выключатель, а сводку в Telegram после включения общего ставит служба (domains/notify._summary)"}
# ★ ревизия 85 В-7: вызов операции без пары «предпросмотр + окно подтверждения» — только эти (с причиной)
WEB_NO_CONFIRM = {"community.ban.check": "проверка цели ботом внутри окна бана, в Discord ничего не меняется — сам бан подтверждается"}


def _read(*p):
    """Текст файла порта (UTF-8)."""
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


def _strip(src):
    """Исходник без комментариев и строк документации (ast.unparse) — признаки ищутся только в коде."""
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and node.body:
            b0 = node.body[0]
            if isinstance(b0, ast.Expr) and isinstance(getattr(b0, "value", None), ast.Constant) and isinstance(b0.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _code(op, ops):
    """Код класса операции и всех его баз до core.ops.Operation (без комментариев и документации)."""
    out = []
    for c in type(op).__mro__:
        if c is ops.Operation or c is object:
            break
        try:
            out.append(_strip(inspect.getsource(c)))
        except (OSError, TypeError):
            pass
    return "\n".join(out)


def _raw(op, ops):
    """Исходник класса и баз как есть (для текстов предупреждений)."""
    out = []
    for c in type(op).__mro__:
        if c is ops.Operation or c is object:
            break
        try:
            out.append(inspect.getsource(c))
        except (OSError, TypeError):
            pass
    return "\n".join(out)


def _reach(op, ops, depth=2):
    """Код класса операции, его баз и функций разделов / ядра, которые он вызывает (до depth уровней) — внешние эффекты вне класса."""
    import types
    seen, srcs = set(), []
    frontier = [c for c in type(op).__mro__ if c not in (ops.Operation, object)]
    for lvl in range(depth + 1):
        nxt = []
        for obj in frontier:
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            try:
                src = _strip(inspect.getsource(obj))
            except (OSError, TypeError, SyntaxError):
                continue
            srcs.append(src)
            if lvl == depth:
                continue
            g = sys.modules[obj.__module__].__dict__
            for a, b in NAME_RX.findall(src):
                f = g.get(a)
                if b:
                    f = getattr(f, b, None) if isinstance(f, types.ModuleType) else None
                if isinstance(f, types.FunctionType) and (f.__module__ or "").startswith(("domains", "core")):
                    nxt.append(f)
        frontier = nxt
    return "\n".join(srcs)


def _op_calls(line, text=None):
    """Вызовы op(…), начатые в строке JS line → [(имя или переменная, [аргументы верхнего уровня])] (скобки и строки учитываются); text —
    эта строка и следующие (вызов на нескольких строках)."""
    src = text if text is not None else line
    out = []
    for m in re.finditer(r"(?<![\w.])op\(", line):
        depth, cur, args, quote, k = 1, "", [], "", m.end()
        while k < len(src) and depth:
            ch = src[k]
            if quote:
                if ch == quote and src[k - 1] != "\\":
                    quote = ""
            elif ch in "\"'`":
                quote = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            if depth == 1 and ch == "," and not quote:
                args.append(cur.strip())
                cur = ""
            elif depth:
                cur += ch
            k += 1
        args.append(cur.strip())
        out.append((args[0].strip('"'), args))
    return out


IRREV_RX = re.compile(r"[Нн]еобратим|не откатывается|отката нет")      # ★ р86 М-2: признаки необратимости в коде, комментариях и предупреждениях
UNDO_SAYS_RX = re.compile(r"[Нн]еобратим|не вернуть|отката нет|не возвращ")    # откат «обратной операцией» честно говорит, что не вернётся
# ★ ревизия 86 М-1: следствия, которые делает НЕ сама операция, а периодический проход службы по её записи: операция → (модуль, функция, признак
#   в коде функции, код writes). notify.rule.set пишет выключатель, а notify.scan при включённом общем ставит сводку _summary в Telegram.
SCAN_EFFECTS = {"notify.rule.set": ("domains.notify", "scan", "_summary(", "telegram")}


def _violations(R, DOC, ops):
    """Нарушения справки DOC против кода операций реестра R → список текстов (пусто — всё сходится). Отдельной функцией — для проб подменой."""
    import importlib
    from domains import stack as _stack
    viol = []
    for n, op in sorted(R.items()):
        d, code, raw = DOC[n], _code(op, ops), _raw(op, ops)
        w = set(d["w"])
        if DISCORD_RX.search(code) and "discord" not in w and n not in DISCORD_EXEMPT:
            viol.append("%s: код ставит в Discord (очередь, команда боту или рестарт с объявлением), writes без Discord" % n)
        if TELEGRAM_RX.search(code) and "telegram" not in w:
            viol.append("%s: код шлёт sendMessage, writes без Telegram" % n)
        if LIVE_RX.search(code) and "live" not in w:
            viol.append("%s: код зовёт мост, writes без «живой сервер»" % n)
        if DELETE_RX.search(code) and not op.reversible and d["u"] != "irreversible":
            viol.append("%s: код удаляет (DROP / уборка / удаление из Discord), откатом не отменяется, а undo = %s" % (n, d["u"]))
        if STACK_RX.search(code) and d["r"] != "stack":
            viol.append("%s: код запускает restart_stack.py, restart ≠ «стойка»" % n)
        if CLIENT_RX.search(code) and not ("client" in w and d["r"] == "release"):
            viol.append("%s: код пишет клиентские файлы, а writes / restart не «данные клиента» / «выпуск»" % n)
        if PANEL_ONLY_TXT in raw and not w <= {"panel_db", "pc"} and n not in PANEL_ONLY_EXEMPT:
            viol.append("%s: предпросмотр говорит «пишется только база панели AsdaAdmin», а writes = %s" % (n, sorted(w)))
        if op.reversible and "def undo" not in code:
            viol.append("%s: reversible без своего undo" % n)
        reach = _reach(op, ops)
        if DELETE_RX.search(reach) and not op.reversible and d["u"] not in ("irreversible", "inverse") and n not in REACH_DELETE_EXEMPT:
            viol.append("%s: вызываемый код удаляет (ротация, уборка, DROP), а undo = %s" % (n, d["u"]))
        # ★ р86 М-2: «необратимо» в документации, комментариях или предупреждениях класса — undo «необратимо» или текст отката говорит, что не вернётся
        if IRREV_RX.search(raw) and not op.reversible and d["u"] != "irreversible" and not UNDO_SAYS_RX.search(d["ur"]):
            viol.append("%s: код говорит «необратимо / отката нет», а справка отката этого не говорит (undo = %s)" % (n, d["u"]))
        if "BAN_WARN" in raw and getattr(op, "chain", "") == "account.block" and "онбординг" not in d["ur"]:
            viol.append("%s: бан выгоняет с сервера (BAN_WARN) — откат должен сказать, что роли и онбординг не возвращаются" % n)
        if "discord" in w and n.startswith("community.") and "mod-log" not in d["wr"]:
            viol.append("%s: команда боту — бот пишет строку в mod-log (community_bot._log), в writes этого нет" % n)
    for n, (mod, fname, mark, wcode) in sorted(SCAN_EFFECTS.items()):
        src = _strip(inspect.getsource(getattr(importlib.import_module(mod), fname)))
        if mark not in src:
            viol.append("%s: в %s.%s больше нет %s — карту SCAN_EFFECTS обновить" % (n, mod, fname, mark))
        elif n in DOC and wcode not in DOC[n]["w"]:
            viol.append("%s: %s.%s по записи операции делает %s — writes без %s" % (n, mod, fname, mark, wcode))
    for n in sorted(RESTART_STACK_DB):
        if "game_db" not in DOC[n]["w"]:
            viol.append("%s: restart_stack.py со стартом сбрасывает CharPos и точки входа данжей в Joy1, а writes без игровых баз" % n)
    for n, (_w, flags, _t, _x) in sorted(_stack.MODES.items()):
        if ("--stop-only" not in flags) != (n in RESTART_STACK_DB):
            viol.append("%s: карта RESTART_STACK_DB расходится с ключами restart_stack (%s)" % (n, " ".join(flags)))
    return viol


def _probe(R, DOC, ops, name, **change):
    """Проба подменой: копия каталога, у записи name поля change → есть ли нарушение по name."""
    doc = {k: dict(v) for k, v in DOC.items()}
    doc[name].update(change)
    return any(x.startswith(name + ":") for x in _violations(R, doc, ops))


def _web_unpaired(text, fname):
    """★ р86 М-4: выполнения операции op(X, …, false) в JS без СВОЕЙ пары — ближайший выше предпросмотр op(X, …, true) с тем же первым аргументом
    (до 60 строк) и confirmWin( между ним и выполнением; системные confirm / prompt (кроме выхода из панели) → список нарушений."""
    lines, bad, dry = text.splitlines(), [], {}
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("//"):
            continue
        rest = "\n".join(lines[i:i + 6])          # вызов может занимать несколько строк — аргументы до закрывающей скобки
        for nm, args in _op_calls(ln, rest):
            if args == [""] or "async function op(" in ln:
                continue
            if args[-1:] == ["true"]:
                dry[args[0]] = i
                continue
            if nm in WEB_NO_CONFIRM:
                continue
            k = dry.get(args[0])
            between = "\n".join(lines[k:i + 1]) if k is not None else ""
            if len(args) < 3 or k is None or i - k > 60 or "confirmWin(" not in between:
                bad.append("%s:%d op(%s) без своей пары предпросмотр + confirmWin" % (fname, i + 1, nm))
        if re.search(r"(?<![\w.])(confirm|prompt)\(", ln) and "Выйти из панели" not in ln:
            bad.append("%s:%d системный confirm / prompt" % (fname, i + 1))
    return bad


def offline(check):
    """Полнота справки, сверка с кодом, веб, переводы."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import domains
    domains.load_all()
    from core import auth, ops, opdoc
    R = ops.REGISTRY
    bad = opdoc.problems(R)
    check("справка А7.10: у всех %d операций реестра есть writes / restart / undo / help и название EN, RU и EN, коды из списков, reversible ↔ "
          "откат журналом, обратные операции существуют, лишних записей нет" % len(R), not bad and len(opdoc.DOC) == len(R) and len(R) >= 165,
          bad[:6])
    # самопроверка самой проверки: операция без справки и неверный признак отката ловятся
    fake = dict(R)
    fake["zz.probe"] = True
    probe = opdoc.problems(fake)
    probe2 = opdoc.problems({"account.block": False})
    check("справка: проверка полноты ловит новую операцию без справки и reversible ≠ откат журналом",
          any(x.startswith("zz.probe: нет справки") for x in probe) and any("reversible" in x for x in probe2), (probe[:2], probe2[:2]))
    texts = [(n, k, d[k]) for n, d in opdoc.DOC.items() for k in ("wr", "we", "rr", "re", "ur", "ue", "hr", "he", "te")]
    semi = [(n, k) for n, k, t in texts if "; " in t]
    check("справка: в текстах нет «; »", not semi, semi[:5])
    # --- выборочная сверка с кодом (★ ревизия 86: правила — функция _violations, пробы подменой каталога доказывают, что они срабатывают)
    viol = _violations(R, opdoc.DOC, ops)
    check("справка: сверка с кодом — класс и вызываемые функции (2 уровня): Discord, Telegram, мост, удаление (и в ротации / уборке), рестарт "
          "стойки и его сброс CharPos в Joy1, клиентские файлы, «только база панели», «необратимо» в документации, бан и онбординг, mod-log",
          not viol, viol[:6])
    D = opdoc.DOC
    probes = {"notify.rule.set без Telegram": _probe(R, D, ops, "notify.rule.set", w=tuple(x for x in D["notify.rule.set"]["w"] if x != "telegram")),
              "shop.cs_server_rollback без «необратимо» в откате": _probe(R, D, ops, "shop.cs_server_rollback", ur="Выложить снова — shop.cs_server_apply."),
              "live.mob_pop «обратной операцией»": _probe(R, D, ops, "live.mob_pop", u="inverse", ur="Убрать — live.mob_return.", inv=("live.mob_return",)),
              "stack.start без игровых баз": _probe(R, D, ops, "stack.start", w=("stack", "panel_db")),
              "db.backup «нечего»": _probe(R, D, ops, "db.backup", u="nothing", ur="Бэкап ничего не меняет.")}
    check("справка (р86): пробы подменой каталога — каждое правило сверки срабатывает (%d проб)" % len(probes), all(probes.values()),
          [k for k, v in probes.items() if not v])
    exp = []
    exp += ["%s: ожидалось «необратимо», а %s" % (n, opdoc.DOC[n]["u"]) for n in sorted(IRREVERSIBLE) if opdoc.DOC[n]["u"] != "irreversible"]
    exp += ["%s: ожидалось writes Discord" % n for n in sorted(DISCORD) if "discord" not in opdoc.DOC[n]["w"]]
    exp += ["%s: Discord не меняется, а writes Discord" % n for n in sorted(NOT_DISCORD) if "discord" in opdoc.DOC[n]["w"]]
    tg = {n for n, d in opdoc.DOC.items() if "telegram" in d["w"]}
    exp += ["Telegram пишут %s, ожидалось %s" % (sorted(tg), sorted(TELEGRAM))] if tg != TELEGRAM else []
    st = {n for n, d in opdoc.DOC.items() if d["r"] == "stack"}
    exp += ["рестарт стойки у %s, ожидалось %s" % (sorted(st), sorted(STACK_RESTART))] if st != STACK_RESTART else []
    exp += ["%s: операция с отказом всегда, а writes не «ничего»" % "db.restore"] if opdoc.DOC["db.restore"]["w"] != ("none",) else []
    check("справка: явная сверка по разборам разделов — необратимые (%d), пишут в Discord (%d), Telegram — только telegram.ping, рестарт стойки (%d)"
          % (len(IRREVERSIBLE), len(DISCORD), len(STACK_RESTART)), not exp, exp[:6])
    # --- локализация и права
    en = opdoc.catalog("owner", True)
    cyr = [x["name"] for x in en["items"] if any(CYR.search(str(v)) for v in (x["title"], x["help"], x["section"], x["writes"]["info"],
                                                                                    x["restart"]["info"], x["undo"]["info"], x["restart"]["label"],
                                                                                    x["undo"]["label"]) + tuple(x["writes"]["labels"]))]
    ru = opdoc.catalog("support", False)
    perm_ok = all(x["roles"] == [r for r in auth.ROLES if r in auth.PERMS.get(R[x["name"]].perm, set())]
                  and x["allowed"] == auth.can("support", R[x["name"]].perm) for x in ru["items"])
    check("справка: каталог EN без кириллицы (%d операций), роли = core/auth.PERMS, «доступно вам» = праву роли, второй фактор и исполнитель — из "
          "операции" % len(en["items"]), not cyr and perm_ok and len(en["items"]) == len(R) and not en["missing"]
          and {x["name"] for x in ru["items"] if x["two_factor"]} == {n for n in R if ops.needs_two_factor(n)}
          and all(x["runner"] == (getattr(R[x["name"]], "schedule_runner", None) or "") for x in ru["items"]), cyr[:5])
    hid = [x["name"] for x in ru["items"] if not x["allowed"] and (x["writes"] or x["restart"] or x["undo"])]
    shown = [x["name"] for x in ru["items"] if x["allowed"] and not (x["writes"] and x["restart"] and x["undo"])]
    check("справка (р85 М-8): подробности — только с правом самой операции (support: %d без права — без writes / restart / undo)"
          % sum(1 for x in ru["items"] if not x["allowed"]), not hid and not shown and any(not x["allowed"] for x in ru["items"]), (hid[:4], shown[:4]))
    jd = opdoc.for_job({"op": "stack.restart"}, False, "owner")
    check("справка (р85 В-6): предпросмотр job.add показывает справку ПЛАНИРУЕМОЙ операции и строку о задании (отмена job.cancel)",
          jd["name"] == "stack.restart" and "discord" in jd["writes"]["codes"] and "job.cancel" in jd["job"]["info"]
          and opdoc.for_job({"op": "нет"}, False, "owner")["name"] == "job.add", jd.get("job"))
    sec = [x["name"] for x in ru["items"] if x["section"] == opdoc.OTHER_SECTION[0]]
    check("справка: у каждой операции свой раздел (нет «Прочее»)", not sec, sec[:5])
    # --- служба и веб
    from api import server
    rt = [(m, rx.pattern, perm) for m, rx, fn, perm, full in server.ROUTES if rx.pattern == "^/api/opdoc$"]
    srv = _read(ROOT, "api", "server.py")
    one = [(m, perm, full) for m, rx, fn, perm, full in server.ROUTES if rx.pattern == "^/api/opdoc/one$"]
    check("справка служба: GET /api/opdoc с правом status.view (есть у всех ролей), справка doc в ответе предпросмотра /api/ops (у job.add — "
          "планируемой операции), GET /api/opdoc/one для окон без предпросмотра", one == [("GET", None, False)] and "opdoc.for_job(params" in srv
          and rt == [("GET", "^/api/opdoc$", "status.view")] and "opdoc.localized(name, ops.REGISTRY.get(name)" in srv
          and all("status.view" in auth.perms_of(r) for r in auth.ROLES), rt)
    app, js, idx, wi = _read(ROOT, "web", "app.js"), _read(ROOT, "web", "help.js"), _read(ROOT, "web", "index.html"), _read(ROOT, "web", "i18n.js")
    check("справка веб: #/help в меню и маршрутизаторе, help.js в index.html, окно подтверждения берёт справку предпросмотра (takeOpDoc → opDocBlock), "
          "op() сохраняет doc, без innerHTML",
          '["#/help", "Справка", "status.view"' in app and 'case "help": return viewHelp(my);' in app and '<script src="/help.js" defer></script>' in idx
          and "doc = doc !== undefined ? doc : takeOpDoc();" in app and "doc ? opDocBlock(doc) : null" in app and "S.opDoc = r && r.dry && r.doc ?" in app
          and "innerHTML" not in js and "innerHTML" not in app.split("function opDocBlock")[1].split("function notify")[0])
    web_bad = []
    for f in sorted(os.listdir(os.path.join(ROOT, "web"))):
        if f.endswith(".js"):
            web_bad += _web_unpaired(_read(ROOT, "web", f), f)
    # ★ р86 М-4: проба — выполнение, у которого предпросмотр и окно — от ДРУГОЙ операции, ловится
    fake = ('async function a() {\n  p = await op("x.one", q, true);\n  if (!await confirmWin(T("Подтвердите"), [])) return;\n'
            '  await op("x.one", q, false);\n}\nasync function b() {\n  await op("x.two", q, false);\n}\n')
    probe = _web_unpaired(fake, "probe.js")
    check("справка веб (р86 М-4): проба — op(…, false) без СВОЕЙ пары (тот же первый аргумент, окно между ними) ловится, правильная пара — нет",
          probe == ["probe.js:7 op(x.two) без своей пары предпросмотр + confirmWin"], probe)
    check("справка веб (р85 В-7 / М-9): каждое выполнение операции — после предпросмотра и окна подтверждения со справкой, без системных confirm / "
          "prompt (кроме выхода из панели), откат из журнала и «о себе» — со справкой (/api/opdoc/one)",
          not web_bad and 'fetchOpDoc(x.action)' in app and 'fetchOpDoc("self.password")' in app and 'fetchOpDoc("self.totp_enable")' in app
          and "OPDOC_FRESH_MS" not in app, web_bad[:6])
    labels = set(re.findall(r'T\("([^"]+)"', js)) | set(re.findall(r'placeholder: "([^"]+)"', js)) \
        | set(re.findall(r'h\("(?:h1|h2|h3|span|button|label|div|b)", (?:null|\{[^}]*\}), "([^"]+)"\)', js)) \
        | set(re.findall(r'\[\s*"([^"]+)", x =>', js)) | {"Справка", "Что изменится", "Перезапуск", "Откат"}
    have = set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":', wi, re.M)) | set(re.findall(r'[{,]\s*"((?:[^"\\]|\\.)+)":\s*"', wi))
    lack = sorted(x for x in labels if CYR.search(x) and x not in have)
    check("справка веб EN: у подписей страницы и блока есть перевод в web/i18n.js (%d подписей)" % len(labels), not lack and len(labels) > 15, lack[:8])
    # --- импорт без побочных эффектов
    p = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, '.'); from core import opdoc, ops; print('N=%d' % len(ops.REGISTRY))"],
                       cwd=ROOT, capture_output=True, timeout=120)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    check("справка: импорт core.opdoc без побочных эффектов (разделы не грузит, реестр пуст)", "N=0" in out, out[-300:])


def live(check):
    """Служба на сервере: каталог полон по её реестру, без входа — 401."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config
    if config.get().on_server:
        return check("живой самотест А7.10 «справка» — с ПК", True)
    import domains
    domains.load_all()
    from core import ops
    probe = ("import sys\nsys.path.insert(0, '.')\nimport domains\ndomains.load_all()\nfrom core import ops, opdoc\n"
             "print('ODPROBE n=%d doc=%d bad=%d' % (len(ops.REGISTRY), len(opdoc.DOC), len(opdoc.problems(ops.REGISTRY))))\n")
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
    mm = re.search(r"ODPROBE n=(\d+) doc=(\d+) bad=(\d+)", out)
    check("служба на сервере (SSH): справка полна по реестру службы (операций %d, как на ПК)" % len(ops.REGISTRY),
          bool(mm) and int(mm.group(1)) == len(ops.REGISTRY) and int(mm.group(2)) == len(ops.REGISTRY) and mm.group(3) == "0", out[-600:])
    import ssl
    import urllib.error
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)).open(
            "https://%s:17890/api/opdoc" % config.SERVER_VPN_IP, timeout=10)
        code = 200
    except urllib.error.HTTPError as ex:
        code = ex.code
    except (urllib.error.URLError, OSError) as ex:
        code = str(ex)[:120]
    check("служба (живьём): GET /api/opdoc без входа — 401", code == 401, code)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    import selftest as T
    T.utf8_stdout()
    offline(T.check)
    if "--live" in sys.argv:
        live(T.check)
    bad = [r for r in T.RESULTS if not r[1]]
    print("\nИТОГ: %d проверок, ошибок %d" % (len(T.RESULTS), len(bad)))
    sys.exit(1 if bad else 0)
