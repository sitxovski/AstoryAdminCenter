# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""shopcs.py — НАБОРЫ ИЗМЕНЕНИЙ магазинов (волна А3 «Данные: магазины», план §3.4, §4.Г; 19.11.2026; после ревизии 30 — 19.11).

Хранение — AsdaAdmin.adm.changeset / adm.changeset_item (sql/adminc_13_changeset.sql); данные, проверки и сборка файлов —
domains/shopdata.py. Каждый шаг — операция (core/ops): запись в журнал adm.audit с целью «changeset:<№>».

РЕШЕНИЯ ВЛАДЕЛЬЦА 19.11 (research_a3_shops.md §5):
  1. Цена и состав — ПАРОЙ «сервер + клиент» к выпуску клиента. Серверная половина без ключа --unsynced-ok — только когда клиент
     ВЫПУЩЕН (status released; ревизия 30 В-1) или набор «срочно, только сервер» (только sell.deny и веса бустеров без смены кодов).
  2. Клиентская половина — консолью панели на ПК владельца (служба на сервере не видит RawAssets / UE / Perforce). Выпуск — НЕ делается.
  3. Серверная половина и рестарт — ТОЛЬКО владелец (shop.apply), только консолью ПК: restart_stack.py (объявление ботом Discord,
     3 мин, штатная остановка, deploy_changeset.py = deploy_premium_boxes с манифестом набора, паритет, старт). ВСЕ проверки
     (есть ли что выкладывать/откатывать, сухой прогон выкладчика, md5 базы, «чужие» файлы, .bak) — ДО объявления (В-3). Итог —
     по ФАКТИЧЕСКИМ md5 стойки после прогона (В-8): applied / partial_* / без изменений / unknown. Подъём — только
     restart_stack.py --start-only (запуск ЦЕЛИКОМ остановленной стойки; при живом или непрочитанном счёте процессов — отказ) и
     только после остановки, сделанной этим рестартом; частичное состояние сначала доводится до базы (ревизии 31–32).
  4. В лавку NPC нельзя ставить предмет премиум-витрины (одна цена: золото = GXP) — проверка отказывает (в обе стороны, по итогу набора).

ПЕРЕХОДЫ (TRANSITIONS ниже — то же в коде проверок и в самотесте):
  статус набора: draft ⇄ checked → approved; reopen: checked/approved → draft (ничего не применено); cancel → rolled_back.
  half-состояния: server_state none → dry_srv (служба: только md5) → dry_ok (ПК: настоящий сухой прогон) → applied | partial →
  rolled_back | partial; client_state none → dry_ok → applying → applied → rolled_back.
  статус после шагов половин выводится из состояний (derive_status): released, если отмечен выпуск (откат сервера его не стирает,
  М-9); иначе applied_client, если клиент applying/applied; иначе applied_server, если сервер applied/partial; иначе — rolled_back
  (была применённая и откаченная половина) или approved.
РЕВИЗИЯ 31 (19.11):
  * вторая половина не пересчитывает первую: серверные шаги сверяют только серверную часть с утверждённой (манифест сухого прогона,
    md5 база/новый), клиентские — работают по утверждённым клиентским правкам (их «было» сверяет client_plan с портом) — Н-В1;
  * подъём стойки — ТОЛЬКО restart_stack.py --start-only (запускает целиком остановленную стойку, при любом живом процессе — отказ) и
    только если остановку сделал наш рестарт («все процессы стойки остановлены») и сейчас процессов 0; иначе — сообщение владельцу;
    частичная выкладка при остановленной стойке сначала откатывается до базы (паритет Ch2 = полю), потом подъём — Н-В2, Н-М2;
  * все метки времени набора — UTC (shopdata.utc_now) — Н-В3; «стойка работает» — все процессы stack_layout.EXPECT — Н-М4;
  * сбой чтения после рестарта — server_state unknown, шаг changeset server-sync N — Н-М3; partial_apply / partial_rollback — К-5.
А4.0 (19.11): движок общий для всех областей данных — позиции берутся из реестра видов domains/cs_kinds (магазины, витрина 6800,
  магазин чести, парикмахерская); права области (data.edit / data.apply у А4) проверяются вместе с shop.*; сильная правка баланса
  областей А4 — второе подтверждение при утверждении (balance_ok, консоль --balance-ok) с показом «на руках у игроков».
Побочных эффектов при импорте нет.
"""
import contextlib
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

from core import config, db
from core.ops import Operation, OpRefused, register
from domains import shopdata as SD

STATUS = ("draft", "checked", "approved", "applied_server", "applied_client", "released", "rolled_back")
EDITABLE = ("draft", "checked")
ORDERS = ("together", "client_first", "server_first")
HALF_OK = ("approved", "applied_server", "applied_client", "released")
RESTART = os.path.join(SD.SRV_TOOLS, "restart_stack.py")
# ★ ревизия 30 В-4 / 31 К-2: ТЕКУЩИЙ changelog — одно место: config.changelog (core/config.py, ключ changelog в config.ini);
#   CHANGELOG — подмена пути для самотеста (None — из config)
CHANGELOG = None
CHANGELOG_DIR = os.path.join(SD.PORT, "Docs", "Changelog")
SRV_APPLIED = ("applied", "partial_apply", "partial_rollback", "unknown")
SERVER_INDEX = os.path.join(SD.PORT, "AstoryServer", "Docs", "INDEX.md")
SERVER_CARDS = os.path.join(SD.PORT, "AstoryServer", "Docs", "_Common")

# Таблица переходов: операция → (статусы набора, server_state, client_state) ДО шага. None — любое.
TRANSITIONS = {
    "shop.cs_item_add": (EDITABLE, None, None), "shop.cs_item_del": (EDITABLE, None, None), "shop.cs_edit": (EDITABLE, None, None),
    "shop.cs_check": (EDITABLE, None, None), "shop.cs_approve": (("checked",), None, None),
    "shop.cs_reopen": (("checked", "approved"), ("none", "dry_srv", "dry_ok"), ("none", "dry_ok")),
    "shop.cs_cancel": (("draft", "checked", "approved"), ("none", "dry_srv", "dry_ok"), ("none", "dry_ok")),
    "shop.cs_server_dry": (HALF_OK, ("none", "dry_srv", "dry_ok"), None),
    "shop.cs_server_apply": (HALF_OK, ("dry_ok", "partial_apply"), None),
    "shop.cs_server_rollback": (HALF_OK, ("applied", "partial_apply", "partial_rollback"), None),
    "shop.cs_server_sync": (HALF_OK, ("unknown", "partial_apply", "partial_rollback", "applied", "dry_ok"), None),
    "shop.cs_client_dry": (("approved", "applied_server"), None, ("none", "dry_ok")),
    "shop.cs_client_apply": (("approved", "applied_server"), None, ("dry_ok",)),
    "shop.cs_client_rollback": (("applied_client",), None, ("applying", "applied")),
    "shop.cs_released": (("applied_client",), None, ("applied",)),
}


def derive_status(server_state, client_state, released, touched):
    """Статус набора по состояниям половин (после любого шага применения/отката)."""
    if released:
        return "released"
    if client_state in ("applying", "applied"):
        return "applied_client"
    if server_state in SRV_APPLIED:
        return "applied_server"
    return "rolled_back" if touched else "approved"


def _rows(sql, params=()):
    cn = db.admin()
    try:
        return db.admin_rows(cn, sql, params)
    finally:
        cn.close()


def _cs_id(p):
    try:
        return int(p.get("cs"))
    except (TypeError, ValueError):
        raise OpRefused("не указан номер набора изменений")


def get(cs_id, with_check=True):
    """Набор с позициями → dict (check — разобранный итог последней проверки)."""
    r = _rows("SELECT * FROM adm.changeset WHERE id = ?", (int(cs_id),))
    if not r:
        raise OpRefused("набора изменений №%s нет" % cs_id)
    cs = r[0]
    cs["items"] = [dict(x, params=json.loads(x["params"])) for x in
                   _rows("SELECT pos, kind, params, note, added_by, added_at FROM adm.changeset_item WHERE changeset_id = ? "
                         "ORDER BY pos", (int(cs_id),))]
    raw = cs.pop("check_json", None)
    cs["check"] = json.loads(raw) if (raw and with_check) else None
    cs["urgent"] = bool(cs["urgent"])
    return cs


def list_sets(limit=100):
    return _rows("SELECT TOP (%d) c.id, c.title, c.author, c.created_at, c.updated_at, c.status, c.order_mode, c.urgent, "
                 "c.server_state, c.client_state, c.approved_by, c.approved_at, c.released_at, "
                 "(SELECT COUNT(*) FROM adm.changeset_item i WHERE i.changeset_id = c.id) AS n "
                 "FROM adm.changeset c ORDER BY c.id DESC" % max(1, min(int(limit), 500)))


def _update(cs_id, allowed, srv=None, cli=None, **f):
    """UPDATE набора при статусе из allowed и (если заданы) состояниях половин — иначе отказ «изменился»."""
    sets = ", ".join("%s = ?" % k for k in f) + ", updated_at = SYSUTCDATETIME()"   # ревизия 32 К-6: все метки набора — UTC
    where, args = ["id = ?", "status IN (%s)" % ",".join("?" * len(allowed))], [int(cs_id)] + list(allowed)
    if srv:
        where.append("server_state IN (%s)" % ",".join("?" * len(srv)))
        args += list(srv)
    if cli:
        where.append("client_state IN (%s)" % ",".join("?" * len(cli)))
        args += list(cli)
    r = _rows("SET NOCOUNT ON; UPDATE adm.changeset SET %s OUTPUT INSERTED.id WHERE %s" % (sets, " AND ".join(where)),
              tuple(f.values()) + tuple(args))
    if not r:
        raise OpRefused("набор №%s сейчас в другом состоянии — обновите страницу" % cs_id)


APPLY_OPS = ("shop.cs_server_apply", "shop.cs_server_rollback", "shop.cs_server_sync", "shop.cs_client_apply",
             "shop.cs_client_rollback", "shop.cs_released")


def need_perms(ctx, kinds, which):
    """★ А4.0: права ОБЛАСТЕЙ позиций (реестр видов): магазины — shop.edit / shop.apply, данные А4 — data.edit / data.apply."""
    if ctx is None:
        return
    for k in sorted(set(kinds)):
        perm = SD.area_perm(k, which)
        if perm and not ctx.can(perm):
            raise OpRefused("нет права «%s»" % perm)


def _gate(op, cs, ctx=None):
    """Проверка по таблице переходов TRANSITIONS (и права областей позиций набора)."""
    need_perms(ctx, [it["kind"] for it in cs.get("items") or []], "apply" if op in APPLY_OPS else "edit")
    st, srv, cli = TRANSITIONS[op]
    if cs["status"] not in st:
        raise OpRefused("%s: набор №%s в статусе «%s» (нужно: %s)" % (OP_WHAT[op], cs["id"], cs["status"], ", ".join(st)))
    if srv and cs["server_state"] not in srv:
        raise OpRefused("%s: серверная половина набора №%s — «%s» (нужно: %s)" % (OP_WHAT[op], cs["id"], cs["server_state"], ", ".join(srv)))
    if cli and cs["client_state"] not in cli:
        raise OpRefused("%s: клиентская половина набора №%s — «%s» (нужно: %s)" % (OP_WHAT[op], cs["id"], cs["client_state"], ", ".join(cli)))


OP_WHAT = {"shop.cs_item_add": "правка позиций", "shop.cs_item_del": "правка позиций", "shop.cs_edit": "правка набора",
           "shop.cs_check": "проверка", "shop.cs_approve": "утверждение", "shop.cs_reopen": "возврат в черновик",
           "shop.cs_cancel": "отмена", "shop.cs_server_dry": "сухой прогон сервера", "shop.cs_server_apply": "применение сервера",
           "shop.cs_server_rollback": "откат серверной половины", "shop.cs_client_dry": "сухой прогон клиента",
           "shop.cs_client_apply": "применение клиента", "shop.cs_client_rollback": "откат клиентской половины",
           "shop.cs_released": "отметка выпуска", "shop.cs_server_sync": "сверка серверной половины со стойкой"}


def _pc_cli(ctx, what):
    """Шаг только консолью на ПК владельца (не служба на сервере, не браузер)."""
    if config.get().on_server:
        raise OpRefused("%s — только консолью на ПК владельца: служба на сервере не видит клиентские исходники, UE и Perforce, "
                        "а restart_stack.py работает с ПК" % what)
    if ctx.via != "cli":
        raise OpRefused("%s — только консолью: python asda_admin.py changeset …" % what)


def evaluate(cs):
    """Оценка набора по живой стойке и клиенту + порядок половин и стенд шлюза (ПК) → (Eval, итог)."""
    ev = SD.Eval(cs["items"], cs["urgent"])
    ev.cs_id = cs.get("id")                       # ★ А5.5: область «Настройки патчей» сверяет цели с ДРУГИМИ ожидающими наборами
    ev.run()
    s = ev.summary()
    if cs["order_mode"] == "server_first" and not s["urgent_ok"]:
        s["errors"].append("«сначала сервер» — только для позиций, безопасных без выпуска клиента (запрет продажи, веса бустеров)")
    if cs["urgent"] and s["client_needed"]:
        s["errors"].append("«срочно, только сервер», а клиентская половина обязательна — снимите флаг")
    if any(it["kind"] in ("price", "sell.allow", "sell.deny", "shop6000.add") for it in cs["items"]) and not s["errors"]:
        ok, lines = SD.gateway_stand(ev)
        # запрет продажи САМ даёт расхождения «после» (карточка есть, шлюз/GS не продаст) — это его цель, не ошибка набора
        deny = any(it["kind"] == "sell.deny" for it in cs["items"])
        if ok is False and deny:
            lines = lines + ["расхождения стенда ожидаемы: в наборе есть запрет продажи — сверьте коды выше"]
        (s["warnings"] if ok is not False or deny else s["errors"]).extend(lines)
        s["gateway"] = {"ok": ok, "lines": lines}
    # ★ А4.0: сильная правка баланса (решение владельца 19.11) — «сколько на руках у игроков» и предупреждение о втором
    #   подтверждении при утверждении (магазины А3 — только сведения в s["balance"], без гейта)
    if s.get("balance_strong"):
        lines, codes = SD.balance_report(s)
        s["balance_stack"] = {str(c): v for c, v in SD.stack_flags(ev, codes).items()}     # ★ ревизия 33 М-2
        s["balance_held"] = SD.held_counts(codes, {int(c): v for c, v in s["balance_stack"].items()})
        s["warnings"].append("сильная правка баланса (больше чем в %s раза; стопка / тип / замена): %s; на руках у игроков: %s — при "
                             "утверждении нужно второе подтверждение" % (SD.BALANCE_RATIO, "; ".join(lines)[:600],
                                                                         SD.held_text(s["balance_held"])))
    s["ok"] = not s["errors"]
    return ev, s


def changelog_path():
    """Текущий changelog порта (config.changelog) или подмена самотеста."""
    return CHANGELOG or os.path.join(CHANGELOG_DIR, config.get().changelog)


def check_changelog():
    """Отказ ДО применения: текущего changelog нет или появился более новый CHANGELOG_<дата>.md (сменился — поправить config)."""
    cur = changelog_path()
    if not os.path.isfile(cur):
        raise OpRefused("текущего changelog %s нет — поправьте config.changelog" % SD.rel_area(cur))
    d = os.path.dirname(cur)
    mine = re.match(r"CHANGELOG_(\d{4}-\d\d-\d\d)\.md$", os.path.basename(cur))
    newer = sorted(f for f in os.listdir(d) if re.match(r"CHANGELOG_\d{4}-\d\d-\d\d\.md$", f)
                   and mine and f[10:20] > mine.group(1))
    if newer:
        raise OpRefused("есть более новый changelog %s, а config.changelog = %s — поправьте config" % (newer[-1], os.path.basename(cur)))


def cs_dir(cs_id):
    return os.path.join(SD.CS_DIR, "cs%d" % int(cs_id))


def manifest_path(cs_id):
    return os.path.join(cs_dir(cs_id), "manifest.json")


def build_server_out(cs, ev):
    """srv_out набора + манифест для deploy_changeset.py (формат deploy_premium_boxes: путь → local / base / new) → путь."""
    d = cs_dir(cs["id"])
    out = os.path.join(d, "srv_out")
    if os.path.isdir(out):
        shutil.rmtree(out)
    tag = cs.get("server_tag") or "%s_cs%d" % (datetime.date.today().strftime("%Y%m%d"), cs["id"])
    man = {"tag": tag, "changeset": cs["id"], "files": {}}
    for rel, data in sorted(ev.new_bytes().items()):
        lp = os.path.join(out, rel.replace("\\", os.sep))
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        with open(lp, "wb") as f:
            f.write(data)
        man["files"][rel] = {"local": lp.replace("\\", "/"), "base": ev.snap.md5[rel], "new": SD.md5b(data)}
    p = manifest_path(cs["id"])
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    return p, man


def _same_as_check(cs, s):
    """Пересобранный набор = утверждённому (те же базы и те же новые файлы)."""
    chk = cs.get("check") or {}
    a = sorted((f["table"], tuple(f["gs"]), f["base"], f["new"]) for f in chk.get("server", {}).get("files", []))
    b = sorted((f["table"], tuple(f["gs"]), f["base"], f["new"]) for f in s["server"]["files"])
    if a != b:
        raise OpRefused("таблицы стойки или позиции изменились после утверждения — проверьте и утвердите набор заново")
    if json.dumps(chk.get("client"), sort_keys=True) != json.dumps(s["client"], sort_keys=True):
        raise OpRefused("клиентская половина изменилась после утверждения — проверьте и утвердите набор заново")


def _same_server(cs, s):
    """Серверная часть пересчёта = утверждённой (ошибки клиентской части при этом не важны: у той же базы — те же байты)."""
    chk = cs.get("check") or {}
    a = sorted((f["table"], tuple(f["gs"]), f["base"], f["new"]) for f in chk.get("server", {}).get("files", []))
    b = sorted((f["table"], tuple(f["gs"]), f["base"], f["new"]) for f in s["server"]["files"])
    if a != b:
        raise OpRefused("таблицы стойки или позиции изменились после утверждения — проверьте и утвердите набор заново")


def _manifest_ok(cs, m):
    """Манифест сухого прогона = утверждённой серверной части (по каждому файлу base/new)."""
    want = {}
    for f in (cs.get("check") or {}).get("server", {}).get("files", []):
        for g in f["gs"]:
            want[SD.rel_of(g, f["table"])] = (f["base"], f["new"])
    got = {rel: (f["base"], f["new"]) for rel, f in m["files"].items()}
    if want != got:
        raise OpRefused("манифест выкладки не совпадает с утверждённым набором — повторите сухой прогон (changeset server-dry)")


def _deploy_env(manifest, mode=""):
    return dict(os.environ, PYTHONIOENCODING="utf-8", ASDA_CHANGESET_MANIFEST=manifest, ASDA_CHANGESET_MODE=mode)


def run_deploy(manifest, args=(), mode="", timeout=900):
    """deploy_changeset.py процессом (сухой прогон без ключей; --check-started — только чтение) → (код, вывод)."""
    config.port_code(SD.SRV_TOOLS)                       # ★ ревизия 56 С-1: выкладчик стойки — код порта, только ПК
    p = subprocess.run([sys.executable, os.path.join(SD.SRV_TOOLS, SD.DEPLOY_SCRIPT)] + list(args), cwd=SD.SRV_TOOLS,
                       env=_deploy_env(manifest, mode), capture_output=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


ADMIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "asda_admin.py")
GUARD_MARK = "перепроверка набора после остановки стойки"     # строка deploy_changeset.py при отказе перепроверки (ревизия 39 Н-3)


def guard_argv(cs_id, mode="", held_ok=False):
    """★ ревизия 39 Н-3: команда перепроверки набора после остановки стойки (deploy_changeset.py зовёт её до копирования файлов)."""
    return ([sys.executable, ADMIN_PY, "changeset", "guard", str(int(cs_id))] + (["--rollback"] if mode == "rollback" else [])
            + (["--held-ok"] if held_ok else []))


def _restart(manifest, mode, guard=None):
    """restart_stack.py --deploy deploy_changeset.py (объявление в Discord, 3 мин, остановка, выкладка, паритет, старт) → (код, вывод).
    Без предела времени (ревизия 30 К-6: убийство посреди работы оставило бы стойку остановленной). guard — команда перепроверки
    (guard_argv): выкладчик зовёт её после остановки, до копирования; отказ — файлы не тронуты, подъём прежней стойки — _after_restart."""
    config.port_code(RESTART)                            # ★ ревизия 56 С-1: только ПК
    env = _deploy_env(manifest, mode)
    if guard:
        env["ASDA_CHANGESET_GUARD"] = json.dumps(guard)
    p = subprocess.run([sys.executable, RESTART, "--deploy", SD.DEPLOY_SCRIPT], cwd=SD.SRV_TOOLS, env=env, capture_output=True)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


@contextlib.contextmanager
def _stack_lock(ctx, cs_id, what):
    """★ ревизия 41 В-1: взаимоисключение стойки (core/jobs.stack_guard, строка running «stack.changeset») на время рестарта набора
    и подъёма --start-only (_after_restart). Занято другим управлением стойкой — отказ до объявления. Журнал недоступен — отказ."""
    from core import jobs
    try:
        with jobs.stack_guard("stack.changeset", ctx.login, ctx.user_id, ctx.role, "набор №%d: %s" % (cs_id, what)) as g:
            yield g
    except jobs.JobLocked as ex:
        raise OpRefused("%s — рестарт набора не начат, объявления не было" % ex)


def _bring_up():
    """Запуск ЦЕЛИКОМ остановленной стойки: restart_stack.py --start-only (без объявления, остановки и выкладки; при любом живом
    процессе стойки — отказ, код 7) → (код, вывод). Звать только после остановки, сделанной нашим рестартом (ревизия 31 Н-В2)."""
    config.port_code(RESTART)                            # ★ ревизия 56 С-1: только ПК
    p = subprocess.run([sys.executable, RESTART, "--start-only"], cwd=SD.SRV_TOOLS, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                       capture_output=True)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def _layout():
    config.port_code(SD.SRV_TOOLS)        # ★ ревизия 56 С-1: stack_layout порта — только ПК (на сервере путь вне дерева службы)
    if SD.SRV_TOOLS not in sys.path:
        sys.path.insert(0, SD.SRV_TOOLS)
    import stack_layout                   # noqa: E402 — единый состав стойки, без побочных эффектов
    return stack_layout


def stack_counts():
    """{процесс: число} по ВСЕМ процессам стойки (stack_layout.PROCS) или None — не прочитано (ревизия 31 Н-М4)."""
    from core import hostshell
    sl = _layout()
    try:
        out = hostshell.powershell("Get-Process %s -ErrorAction SilentlyContinue | Group-Object ProcessName | ForEach-Object { "
                                   "$_.Name + '=' + $_.Count }; Write-Output 'OK'" % ",".join(sl.PROCS), timeout=60)
    except Exception:
        return None
    if "OK" not in out:
        return None
    res = {}
    for ln in out.splitlines():
        if "=" in ln:
            k, v = ln.strip().split("=", 1)
            if v.isdigit():
                res[k] = int(v)
    return res


def stack_complete(c):
    return c is not None and all(c.get(k, 0) >= v for k, v in _layout().EXPECT.items())


def stack_running():
    """Работают ли ВСЕ процессы стойки (stack_layout.EXPECT, 15 шт.)."""
    return stack_complete(stack_counts())


def facts(man):
    """Фактическое состояние файлов манифеста на стойке: {rel: "new" | "base" | "other"} (ревизия 30 В-8, М-8). man — dict или путь."""
    if isinstance(man, str):
        man = json.load(open(man, encoding="utf-8"))
    now = SD.live_md5(sorted(man["files"]))
    return {rel: ("new" if now.get(rel) == f["new"] else "base" if now.get(rel) == f["base"] else "other")
            for rel, f in man["files"].items()}


def sales_since(cs):
    """Покупки затронутых кодов после выкладки → {"gp7": n, "npc": n} или None (не прочитано).
    Премиум — GP7PurchaseLog (success = 1, created_at = SYSUTCDATETIME(), сверка по UTC — ревизия 31 Н-В3).
    Лавки NPC — joylog1.dbo.BuyNPC / BuyNPCGear / BuyNPCNoStack / BuyNpcSowel (Edate; пояс времени этих журналов не доказан —
    окно берётся с запасом: от более раннего из «UTC» и «местного времени сервера»), ревизия 31 К-4."""
    codes = sorted({int(c) for c in (cs.get("check") or {}).get("sale_codes") or []})[:900]
    at = cs.get("server_at")
    if not codes or not at:
        return {"gp7": 0, "npc": 0}
    inl = ",".join(str(c) for c in codes)
    try:
        with db.GameReader("asdastorylogin") as g:
            gp7 = int(g.one("SELECT COUNT(*) AS n FROM GP7PurchaseLog WHERE success = 1 AND created_at >= ? AND item_code IN (%s)" % inl,
                            (at,))["n"] or 0)
        npc = 0
        with db.GameReader("joylog1") as lg:
            off = int(lg.one("SELECT DATEDIFF(minute, SYSUTCDATETIME(), SYSDATETIME()) AS m")["m"] or 0)
            since = at + datetime.timedelta(minutes=min(0, off))
            for t in ("BuyNPC", "BuyNPCGear", "BuyNPCNoStack", "BuyNpcSowel"):
                if lg.rows("SELECT 1 AS x FROM sys.tables WHERE name = ?", (t,)):
                    npc += int(lg.one("SELECT COUNT(*) AS n FROM dbo.%s WHERE Edate >= ? AND Code IN (%s)" % (t, inl), (since,))["n"] or 0)
        return {"gp7": gp7, "npc": npc}
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------------------- записи
def _index_row(text):
    """Строка в «Сводную таблицу» Server/Docs/INDEX.md (перед разделом «Хеши бинарей»; ревизия 30 М-3)."""
    if not os.path.isfile(SERVER_INDEX):
        return
    s = open(SERVER_INDEX, encoding="utf-8").read()
    i = s.find("\n## Хеши бинарей")
    if i < 0:
        with open(SERVER_INDEX, "a", encoding="utf-8") as f:
            f.write("\n" + text + "\n")
        return
    head = s[:i].rstrip("\n")
    with open(SERVER_INDEX, "w", encoding="utf-8", newline="") as f:
        f.write(head + "\n" + text + "\n" + s[i:])


def card_path(cs):
    return os.path.join(SERVER_CARDS, "admin-changeset-%d.md" % cs["id"])


def append_records(cs, half, lines, kind="apply", note=""):
    """Записи о шаге половины: changelog (только дописывать, с причиной), для сервера — строка «Сводной таблицы» INDEX.md и
    карточка правки _Common/admin-changeset-<№>.md (правило INDEX: отдельный .md на правку; откат — НОВОЙ записью, М-4)."""
    today = datetime.date.today().strftime("%d.%m.%Y")
    what = "; ".join(x for x in lines if x)[:900] or "—"
    verb = {"apply": "применена", "rollback": "откачена", "partial_apply": "выложена ЧАСТИЧНО",
            "partial_rollback": "откачена ЧАСТИЧНО", "unknown": "— состояние после рестарта НЕ ПРОЧИТАНО"}.get(kind, kind)
    cl = changelog_path()
    if kind in ("apply", "rollback") and os.path.isfile(cl):          # ревизия 31 К-3: в changelog — только вехи
        with open(cl, "a", encoding="utf-8") as f:
            f.write("\n- **Админ-центр: набор изменений №%d «%s» — %s половина %s** (%s): %s.%s Причина: %s. Журнал панели: "
                    "changeset:%d.\n" % (cs["id"], cs["title"], "серверная" if half == "server" else
                                         "клиентская (клиент, следующий выпуск)", verb, today, what,
                                         (" " + note) if note else "", cs["note"] or cs["title"], cs["id"]))
    if half != "server":
        return
    card = card_path(cs)
    new = not os.path.isfile(card)
    with open(card, "a", encoding="utf-8") as f:
        if new:
            f.write("# Набор изменений админ-центра №%d «%s»\n\n* **Процесс / путь:** GameServer, Indun_GameServer, Ch2_GameServer — "
                    "`ItemTable_Info\\` (таблицы магазинов)\n* **Тип:** данные, выкладчик `deploy_changeset.py` через restart_stack\n"
                    "* **Бэкап:** `.bak_<метка>` рядом, `v2\\_backup\\<метка>`, `@@ASTORY_DEV_ROOT_ESC@@\\_backup\\<дата>_cs%d`\n"
                    "* **Откат:** `python asda_admin.py changeset server-rollback %d --confirm-restart`\n* **Рестарт:** да (GS читает "
                    "таблицы при старте)\n\n## Журнал\n" % (cs["id"], cs["title"], cs["id"], cs["id"]))
        f.write("* %s — серверная половина %s (метка %s): %s%s\n" % (today, verb, cs.get("server_tag") or "—", what,
                                                                  (" — " + note) if note else ""))
    _index_row("| GameServer ×3 (таблицы) | Набор изменений админ-центра №%d «%s» — серверная половина %s | данные (ItemTable_Info) | %s %s "
               "| %s | [_Common/%s](_Common/%s) |" % (cs["id"], cs["title"], verb, "✅" if kind in ("apply", "rollback") else "⚠", today,
                                                     datetime.date.today().isoformat(), os.path.basename(card), os.path.basename(card)))


class CsOp(Operation):
    perm = "shop.edit"

    def target(self, p):
        return "changeset:%s" % p.get("cs", "new")


# ---------------------------------------------------------------------------------------------------------------- черновик
@register
class CsCreate(CsOp):
    name, title = "shop.cs_create", "Магазины: новый набор изменений"

    def _p(self, p):
        t = str(p.get("title") or "").strip()
        if not 1 <= len(t) <= 200:
            raise OpRefused("заголовок набора — от 1 до 200 символов")
        mode = p.get("order_mode") or "together"
        if mode not in ORDERS:
            raise OpRefused("порядок половин: together | client_first | server_first")
        return t, str(p.get("note") or "").strip()[:1000], mode, bool(p.get("urgent"))

    def preview(self, ctx, p):
        t, note, mode, urg = self._p(p)
        return {"text": "новый набор изменений «%s» (порядок %s%s)" % (t, mode, ", срочно — только сервер" if urg else ""),
                "warnings": []}

    def apply(self, ctx, p, prev):
        t, note, mode, urg = self._p(p)
        r = _rows("SET NOCOUNT ON; INSERT adm.changeset (title, author, note, order_mode, urgent) OUTPUT INSERTED.id VALUES (?,?,?,?,?)",
                  (t, ctx.login[:32], note, mode, 1 if urg else 0))
        cid = int(r[0]["id"])
        return {"after": {"id": cid}, "message": "набор изменений №%d создан" % cid}


@register
class CsEdit(CsOp):
    name, title = "shop.cs_edit", "Магазины: свойства набора"

    def preview(self, ctx, p):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        CsCreate._p(self, dict({"title": cs["title"], "order_mode": cs["order_mode"]}, **{k: v for k, v in p.items() if v is not None}))
        return {"text": "свойства набора №%d (проверка снимается)" % cs["id"], "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        t, note, mode, urg = CsCreate._p(self, {"title": p.get("title", cs["title"]), "note": p.get("note", cs["note"]),
                                               "order_mode": p.get("order_mode", cs["order_mode"]), "urgent": p.get("urgent", cs["urgent"])})
        _update(cs["id"], EDITABLE, title=t, note=note, order_mode=mode, urgent=1 if urg else 0, status="draft", check_json=None)
        return {"before": {"title": cs["title"], "order_mode": cs["order_mode"], "urgent": cs["urgent"]},
                "after": {"title": t, "order_mode": mode, "urgent": urg}, "message": "набор №%d изменён" % cs["id"]}


@register
class CsItemAdd(CsOp):
    name, title = "shop.cs_item_add", "Магазины: позиция набора"

    def _prm(self, p):
        prm = SD.norm(p.get("kind"), p.get("params"))
        js = json.dumps(prm, ensure_ascii=False)
        if len(js) > SD.PARAMS_MAX:
            raise OpRefused("позиция слишком большая (%d символов JSON, предел %d)" % (len(js), SD.PARAMS_MAX))
        return prm, js

    def preview(self, ctx, p):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        need_perms(ctx, [p.get("kind")], "edit")          # ★ А4.0: право области нового вида
        prm, _js = self._prm(p)
        return {"text": "набор №%d: + %s %s" % (cs["id"], SD.KINDS[p["kind"]][0], json.dumps(prm, ensure_ascii=False)[:300]),
                "warnings": [], "expect": prm}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        need_perms(ctx, [p.get("kind")], "edit")
        prm, js = self._prm(p)
        # ★ ревизия 30 К-2: статус и вставка — одной транзакцией (гонка с утверждением не вставит позицию в утверждённый набор)
        # ★ ревизия 30 К-2: вставка одним оператором — только пока набор правится (статус под UPDLOCK в том же операторе)
        r = _rows("SET NOCOUNT ON; INSERT adm.changeset_item (changeset_id, pos, kind, params, note, added_by) OUTPUT INSERTED.pos "
                  "SELECT ?, ISNULL(MAX(i.pos), 0) + 1, ?, ?, ?, ? FROM adm.changeset_item i WITH (UPDLOCK, HOLDLOCK) WHERE i.changeset_id = ? "
                  "AND EXISTS (SELECT 1 FROM adm.changeset c WITH (UPDLOCK) WHERE c.id = ? AND c.status IN ('draft','checked'))",
                  (cs["id"], p["kind"], js, str(p.get("note") or "")[:400], ctx.login[:32], cs["id"], cs["id"]))
        if not r:
            raise OpRefused("набор №%s сейчас в другом состоянии — обновите страницу" % cs["id"])
        _update(cs["id"], EDITABLE, status="draft", check_json=None)
        return {"after": {"pos": int(r[0]["pos"]), "kind": p["kind"], "params": prm},
                "message": "набор №%d: позиция %d добавлена" % (cs["id"], int(r[0]["pos"]))}


@register
class CsItemDel(CsOp):
    name, title = "shop.cs_item_del", "Магазины: убрать позицию набора"

    def preview(self, ctx, p):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        pos = int(p.get("pos", 0))
        if not any(x["pos"] == pos for x in cs["items"]):
            raise OpRefused("позиции %d в наборе нет" % pos)
        return {"text": "набор №%d: убрать позицию %d" % (cs["id"], pos), "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        pos = int(p.get("pos", 0))
        it = next((x for x in cs["items"] if x["pos"] == pos), None)
        if not it:
            raise OpRefused("позиции %d в наборе нет" % pos)
        r = _rows("SET NOCOUNT ON; DELETE adm.changeset_item OUTPUT DELETED.pos WHERE changeset_id = ? AND pos = ? "
                  "AND EXISTS (SELECT 1 FROM adm.changeset c WITH (UPDLOCK) WHERE c.id = ? AND c.status IN ('draft','checked'))",
                  (cs["id"], pos, cs["id"]))
        if not r:
            raise OpRefused("набор №%s сейчас в другом состоянии — обновите страницу" % cs["id"])
        _update(cs["id"], EDITABLE, status="draft", check_json=None)
        return {"before": {"pos": pos, "kind": it["kind"], "params": it["params"]}, "message": "набор №%d: позиция %d убрана" % (cs["id"], pos)}


# ---------------------------------------------------------------------------------------------------------------- проверка
@register
class CsCheck(CsOp):
    name, title = "shop.cs_check", "Магазины: проверить набор"

    def preview(self, ctx, p):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        return {"text": "проверить набор №%d (позиций %d) по живой стойке и клиенту" % (cs["id"], len(cs["items"])),
                "warnings": ["проверка ничего не записывает в таблицы стойки и порта"]}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        _ev, s = evaluate(cs)
        st = "checked" if s["ok"] else "draft"
        _update(cs["id"], EDITABLE, status=st, check_json=json.dumps(s, ensure_ascii=False, default=str), checked_at=SD.utc_now())
        return {"before": {"status": cs["status"]}, "after": {"status": st, "errors": len(s["errors"]), "warnings": len(s["warnings"])},
                "message": "проверка набора №%d: ошибок %d, предупреждений %d" % (cs["id"], len(s["errors"]), len(s["warnings"]))}


@register
class CsApprove(CsOp):
    name, title = "shop.cs_approve", "Магазины: утвердить набор"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _gate(self.name, cs, ctx)
        warn = list(cs["check"]["warnings"])[:20]
        bal = self._balance(cs, p, ctx)
        if bal:
            warn.insert(0, bal)
        return {"text": "утвердить набор №%d «%s»: сервер — %d файлов, клиент — %d правок" % (
            cs["id"], cs["title"], cs["check"]["server"]["count"], len(cs["check"]["client"])),
            "warnings": warn}

    @staticmethod
    def _balance(cs, p, ctx=None):
        """★ А4.0: сильная правка баланса — второе подтверждение (ключ balance_ok = "balance"; консоль --balance-ok) с показом
        «сколько на руках у игроков» на момент утверждения (Joy1: Item, Exitem, ItemPostBox). ★ ревизия 33 М-1: второе
        подтверждение — только тот, у кого есть права ПРИМЕНЕНИЯ областей набора (владелец)."""
        chk = cs.get("check") or {}
        if not chk.get("balance_strong"):
            return None
        lines, codes = SD.balance_report(chk)
        strong = [b for b in chk.get("balance") or [] if b.get("strong") and b.get("gate")]
        if strong and all(b.get("kind") == "patch" for b in strong):
            # ★ ревизия 45 Н-3: настройки серверных патчей — не баланс предметов («на руках у игроков» к ним не относится)
            txt = "сильная правка настроек серверных патчей (позиций %d) — строки «сильная правка» в проверке набора" % len(
                {b["pos"] for b in strong})
        else:
            stack = {int(k): v for k, v in (chk.get("balance_stack") or {}).items()}
            txt = "сильная правка баланса: %s; на руках у игроков сейчас: %s" % ("; ".join(lines)[:600],
                                                                                SD.held_text(SD.held_counts(codes, stack)))
        if p.get("balance_ok") != "balance":
            raise OpRefused("%s — нужно второе подтверждение (ключ --balance-ok)" % txt)
        if ctx is not None:
            try:
                need_perms(ctx, [it["kind"] for it in cs.get("items") or []], "apply")
            except OpRefused:
                raise OpRefused("второе подтверждение сильной правки баланса — только владелец (право применения набора)")
        return txt

    @staticmethod
    def _totp(cs, p, ctx):
        """★ ревизия 45 Н-5: MasterEnable=0, выключение защитного патча или его перевод в «журнал» — при утверждении из браузера ещё и код
        второго фактора (как режим обслуживания и события); консоль ПК — без него (вход владельца на ПК, выкладка — только консолью)."""
        chk = cs.get("check") or {}
        if ctx is None or ctx.via != "web" or not any(b.get("totp") and b.get("strong") for b in chk.get("balance") or []):
            return
        from core import auth
        auth.totp_confirm(ctx.user_id, str(p.get("totp") or "").strip())

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        _gate(self.name, cs, ctx)
        self._balance(cs, p, ctx)
        self._totp(cs, p, ctx)
        if len((cs["note"] or "").strip()) < 10:
            raise OpRefused("у набора нет причины (поле «Причина», от 10 символов) — она идёт в changelog; заполните и утвердите")
        chk = cs["check"]
        now = SD.live_md5(sorted(chk["base_all"]))
        moved = sorted(r for r, h in chk["base_all"].items() if now.get(r) != h)
        if moved:
            _update(cs["id"], ("checked",), status="draft", check_json=None)
            raise OpRefused("таблицы стойки изменились после проверки (%s) — проверьте набор заново" % ", ".join(moved[:3]))
        cli = SD.Client.load()
        if cli.md5 != chk["client_md5"]:
            _update(cs["id"], ("checked",), status="draft", check_json=None)
            raise OpRefused("клиентские таблицы изменились после проверки — проверьте набор заново")
        _update(cs["id"], ("checked",), status="approved", approved_by=ctx.login[:32], approved_at=SD.utc_now())
        return {"before": {"status": "checked"}, "after": {"status": "approved"}, "message": "набор №%d утверждён" % cs["id"]}


@register
class CsReopen(CsOp):
    name, title = "shop.cs_reopen", "Магазины: вернуть набор в черновик"

    def preview(self, ctx, p):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        return {"text": "вернуть набор №%d в черновик (проверка и утверждение снимаются, ничего не применялось)" % cs["id"], "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p), False)
        _gate(self.name, cs, ctx)
        st, srv, cli = TRANSITIONS[self.name]
        _update(cs["id"], st, srv, cli, status="draft", check_json=None, approved_by=None, approved_at=None,
                server_state="none", client_state="none")
        return {"before": {"status": cs["status"]}, "after": {"status": "draft"}, "message": "набор №%d возвращён в черновик" % cs["id"]}


@register
class CsCancel(CsOp):
    name, title = "shop.cs_cancel", "Магазины: отменить набор"

    def preview(self, ctx, p):
        cs = get(_cs_id(p), False)
        if cs["status"] == "released":
            # ★ ревизия 31 Н-В1: выпущенный набор, сервер не выложен — отменить можно только серверную половину (клиент уже у игроков)
            if cs["server_state"] not in ("none", "dry_srv", "dry_ok"):
                raise OpRefused("набор выпущен и серверная половина уже на стойке — откат: changeset server-rollback")
            return {"text": "набор №%d выпущен с клиентом: отменить невыложенную серверную половину" % cs["id"],
                    "warnings": ["клиент выпущен с правкой, сервер — нет: расхождение останется до нового набора"]}
        if cs["server_state"] in SRV_APPLIED or cs["client_state"] in ("applying", "applied"):
            raise OpRefused("половина набора уже применена — откат: changeset server-rollback / client-rollback")
        _gate(self.name, cs, ctx)
        return {"text": "отменить набор №%d «%s» (в таблицах ничего не применялось)" % (cs["id"], cs["title"]), "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p), False)
        self.preview(ctx, p)
        if cs["status"] == "released":
            _update(cs["id"], ("released",), ("none", "dry_srv", "dry_ok"), server_state="rolled_back",
                    server_note="серверная половина отменена после выпуска клиента")
            return {"before": {"server_state": cs["server_state"]}, "after": {"server_state": "rolled_back"},
                    "message": "набор №%d: серверная половина отменена (клиент выпущен)" % cs["id"]}
        st, srv, cli = TRANSITIONS[self.name]
        _update(cs["id"], st, srv, cli, status="rolled_back")
        return {"before": {"status": cs["status"]}, "after": {"status": "rolled_back"}, "message": "набор №%d отменён" % cs["id"]}


# ---------------------------------------------------------------------------------------------------------------- сухие прогоны
@register
class CsServerDry(CsOp):
    name, title = "shop.cs_server_dry", "Магазины: сухой прогон серверной половины"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _gate(self.name, cs, ctx)
        if not cs["check"]["server_needed"]:
            raise OpRefused("у набора №%d нет серверной половины — выкладывать нечего" % cs["id"])
        return {"text": "сухой прогон серверной половины набора №%d: сборка таблиц и сверка md5 базы со стойкой (без записи)" % cs["id"],
                "warnings": [] if not config.get().on_server else
                ["служба на сервере сверит только md5 базы («сверено службой»); настоящий сухой прогон выкладчика — консолью ПК"]}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        ev = SD.Eval(cs["items"], cs["urgent"]).run()
        s = ev.summary()
        _same_server(cs, s)                  # ★ ревизия 31 Н-В1: клиентская половина (возможно уже применённая) здесь не важна
        st, srv, cli = TRANSITIONS[self.name]
        if config.get().on_server:
            now = SD.live_md5(sorted(s["base"]))
            bad = [r for r, h in s["base"].items() if now.get(r) != h]
            if bad:
                raise OpRefused("база стойки сменилась: %s" % ", ".join(bad[:3]))
            # ★ ревизия 30 М-6: служба выкладчик не прогоняет — честное состояние dry_srv; server-apply требует dry_ok (ПК)
            _update(cs["id"], st, srv, server_state="dry_srv")
            return {"after": {"server_state": "dry_srv", "lines": ["служба: файлов %d, база md5 совпала; выкладчик не прогонялся — "
                                                                  "server-dry консолью ПК" % len(s["base"])]},
                    "message": "набор №%d: база сверена службой; выкладчик не прогонялся (консоль ПК: changeset server-dry %d)"
                               % (cs["id"], cs["id"])}
        man, m = build_server_out(cs, ev)
        rc, out = run_deploy(man)
        tail = [ln for ln in out.splitlines() if ln.strip()][-12:]
        if rc != 0 or "сухой прогон: всё готово" not in out:
            raise OpRefused("сухой прогон выкладчика: код %d: %s" % (rc, " | ".join(tail[-4:])))
        _update(cs["id"], st, srv, server_state="dry_ok", server_tag=m["tag"])
        return {"after": {"server_state": "dry_ok", "lines": ["манифест %s (метка %s, файлов %d)" % (SD.rel_area(man), m["tag"],
                                                                                                     len(m["files"]))] + tail},
                "message": "сухой прогон сервера набора №%d: готово к выкладке" % cs["id"]}


@register
class CsClientDry(CsOp):
    name, title = "shop.cs_client_dry", "Магазины: сухой прогон клиентской половины"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _gate(self.name, cs, ctx)
        if config.get().on_server or ctx.via != "cli":
            raise OpRefused("сухой прогон клиента — на ПК владельца: python asda_admin.py changeset client-dry %d" % cs["id"])
        if not cs["check"]["client"]:
            raise OpRefused("у набора №%d нет клиентской половины" % cs["id"])
        return {"text": "сухой прогон клиентской половины набора №%d: правки RawAssets и ведомостей в памяти (без записи, без UE)"
                % cs["id"], "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        # ★ ревизия 31 Н-В1: утверждённые клиентские правки; их «было» client_plan сверяет с живым портом (чужая правка — отказ)
        plan = SD.client_plan(cs["check"]["client"], cs["id"])
        if plan["errors"]:
            raise OpRefused("клиентская половина не собирается: %s" % "; ".join(plan["errors"][:4]))
        files = {SD.rel_area(k): {kk: vv for kk, vv in v.items()} for k, v in plan["files"].items()}
        st, srv, cli = TRANSITIONS[self.name]
        _update(cs["id"], st, None, cli, client_state="dry_ok")
        return {"after": {"client_state": "dry_ok", "files": files, "dt_jobs": plan["dt_jobs"], "importers": plan["importers"],
                          "json_jobs": plan.get("json_jobs", []), "warnings": plan.get("warnings", [])},
                "message": "сухой прогон клиента набора №%d: файлов %d, DT %d, импортёров %d" % (
                    cs["id"], len(files), len(plan["dt_jobs"]) + len(plan.get("json_jobs", [])), len(plan["importers"]))}


# ---------------------------------------------------------------------------------------------------------------- применение сервера (ПК, владелец)
STOPPED_MARK = "все процессы стойки остановлены"      # строка restart_stack.py после шага 3 (наша объявленная остановка)


def _classify(f, mode):
    want = "new" if mode == "" else "base"
    done = [r for r, v in f.items() if v == want]
    other = [r for r, v in f.items() if v == "other"]
    if len(done) == len(f) and not other:
        return ("applied" if mode == "" else "rolled_back"), done, other
    if not done and not other:
        return None, done, other
    return ("partial_apply" if mode == "" else "partial_rollback"), done, other


def _after_restart(cs, man, rc, out, mode):
    """Итог рестарта по ФАКТИЧЕСКИМ md5 → (server_state | None «без изменений» | "unknown", notes, lines).
    Подъём стойки (ревизия 31 Н-В2) — только если остановку сделал этот рестарт и сейчас процессов стойки 0; частичная выкладка /
    откат при остановленной стойке сначала доводятся до целого состояния выкладчиком (Н-М2), иначе стойка не поднимается."""
    notes, lines = [], [ln for ln in out.splitlines() if ln.strip()][-12:]
    if rc != 0:
        notes.append("restart_stack.py вернул код %d" % rc)
    notes += [ln.strip()[:600] for ln in out.splitlines() if GUARD_MARK in ln][:1]       # ★ ревизия 39 Н-3: причина отказа перепроверки
    try:
        f = facts(man)
    except Exception as ex:                                        # ★ ревизия 31 Н-М3
        f = None
        notes.append("состояние файлов стойки после рестарта не прочитано (%s) — changeset server-sync %d" % (str(ex)[:120], cs["id"]))
    state, done, other = _classify(f, mode) if f is not None else ("unknown", [], [])
    if other:
        notes.append("на стойке чужие файлы (не база и не набор): %s" % ", ".join(other[:3]))
    counts = stack_counts()
    ours = STOPPED_MARK in out
    if counts is None:
        notes.append("состояние процессов стойки не прочитано — ничего не запускаю; проверьте стойку вручную")
    elif stack_complete(counts):
        pass
    elif any(counts.values()):
        notes.append("стойка работает не полностью (%s) — ничего не делаю: решение владельца" % ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
    elif not ours:
        notes.append("стойка остановлена, но не этим рестартом (объявления/остановки панелью не было) — ничего не запускаю: решение владельца")
    else:
        if other:
            # ★ ревизия 32 М-2: чужие файлы — довести до базы нельзя, а Indun не двойник поля (--sync его не выровняет): не поднимать
            notes.append("на остановленной стойке чужие файлы — довести до базы нельзя, стойка ОСТАНОВЛЕНА, не запускаю: решение владельца")
            return (state or ("partial_apply" if mode == "" else "partial_rollback")), notes, lines
        if state in ("partial_apply", "partial_rollback"):
            # стойка остановлена нами: довести до целого состояния (база) тем же выкладчиком — паритет Ch2 = полю
            rc_r, out_r = run_deploy(man, ["--rollback"])
            lines += ["откат частичного: код %d" % rc_r]
            try:
                f2 = facts(man)
                st2, _d, _o = _classify(f2, "rollback")
            except Exception:
                st2 = "unknown"
            if st2 == "rolled_back":
                notes.append("частичная выкладка доведена до базы при остановленной стойке" if mode == "" else
                             "частичный откат доведён до базы при остановленной стойке")
                state = None if mode == "" else "rolled_back"
            else:
                state = state if st2 != "unknown" else "unknown"
                notes.append("частичное состояние не доведено до базы — стойка ОСТАНОВЛЕНА, не запускаю: решение владельца")
                return state, notes, lines
        if state == "unknown":
            notes.append("файлы стойки не прочитаны — стойка ОСТАНОВЛЕНА, не запускаю: решение владельца")
            return state, notes, lines
        brc, bout = _bring_up()
        lines += ["подъём стойки (--start-only): код %d" % brc] + [ln for ln in bout.splitlines() if ln.strip()][-4:]
        notes.append("стойка поднята --start-only после остановки этим рестартом" if brc == 0 else
                     "стойка ОСТАНОВЛЕНА: restart_stack --start-only не прошёл (код %d) — запустите start.bat" % brc)
    if state in ("partial_apply", "partial_rollback"):
        notes.append(("выложено файлов %d из %d" if mode == "" else "откачено файлов %d из %d") % (len(done), len(f or {})))
    return state, notes, lines


def held_guard(cs):
    """★ ревизия 36 Б-1: «на руках у игроков» по кодам, которым это нужно и при выкладке, и при откате сервера (области с held_guard:
    «Предметы» — смена стопки и вес стопочного предмета), прочитано ЗАНОВО → (коды, текст занятых | None). Не прочитано — отказ."""
    codes, busy = [], []
    for a in SD.AREAS:
        f = getattr(a, "held_guard", None)
        if f:
            c, b = f(cs)
            codes += c
            if b:
                busy.append(b)
    return codes, ("; ".join(busy) if busy else None)          # ★ А4.5: «; » — перевод каждой части (i18n.tr)


def post_stop_guard(cs_id, mode="", held_ok=False):
    """★ ревизия 39 Н-3: ТЕ ЖЕ перепроверки, что в preview выкладки / отката (held_guard «на руках», area_guard областей), повторённые
    ПОСЛЕ объявления и остановки стойки (игроки за 3 минуты объявления могли повысить навык, добрать опыт, дойти до порога) — их зовёт
    deploy_changeset.py до копирования файлов (asda_admin.py changeset guard) → [причины]. Откат с held_ok — как preview: прощаются
    причины, кроме «не прочитаны» и невыполнимых (guard_hard, ревизия 40 В-1)."""
    cs = get(int(cs_id))
    rb = mode == "rollback"
    out = []
    _codes, busy = held_guard(cs)
    if busy and not (rb and held_ok):
        out.append("коды со сменой стопки или веса стопки на руках (%s)" % busy)
    bad = area_guard(cs, "rollback" if rb else "apply")
    if bad and (not (rb and held_ok) or guard_hard(bad)):          # ★ ревизия 40 В-1: невыполнимое ключ не прощает
        out += bad
    return out


def guard_hard(bad):
    """★ ревизия 40 В-1: причины перепроверки, которые второе подтверждение (--held-ok) НЕ прощает: «не прочитаны» и технически
    невыполнимое — область объявляет подстроки своих таких причин в GUARD_HARD («Карты»: GameServer выйдет при старте по ThreadInfo
    COUNT, вход персонажей в мир не состоится). Ключ задуман для «коды на руках» и правил выдачи, а не для неподнимающейся стойки."""
    marks = ["не прочитаны"] + [m for a in SD.AREAS for m in getattr(a, "GUARD_HARD", ())]
    return [b for b in bad if any(m in b for m in marks)]


def area_guard(cs, mode):
    """★ А4.5 (урок ревизии 36 Б-1 для других областей): опасные условия, которые область перепроверяет по ЖИВЫМ данным перед выкладкой
    (mode = apply) и откатом (rollback) сервера (хук области apply_guard; «Задания» — правила выдачи предметов награды) → [причины]."""
    out = []
    for a in SD.AREAS:
        f = getattr(a, "apply_guard", None)
        if f and any(SD.AREA_OF.get(it["kind"]) is a for it in cs.get("items") or []):
            out += f(cs, mode)
    return out


def area_after_server(cs):
    """★ А4.6: что область доводит ПОСЛЕ выкладки / отката сервера (стойка уже в итоговом состоянии; хук области after_server —
    «Звания»: Joy1.dbo.AsdaFamePoints = живой FameInfo.txt) → [заметки]. Сбой хука не отменяет выкладку — заметка и повтор server-sync."""
    out = []
    for a in SD.AREAS:
        f = getattr(a, "after_server", None)
        if f and any(SD.AREA_OF.get(it["kind"]) is a for it in cs.get("items") or []):
            try:
                out += f(cs, "sync")
            except Exception as ex:                  # хук обязан вернуть заметку сам; страховка — не ронять итог рестарта
                out.append("область %s: доводка после выкладки не выполнена (%s) — changeset server-sync %s" % (a.AREA, str(ex)[:160], cs.get("id")))
    return out


@register
class CsServerApply(CsOp):
    name, title, perm = "shop.cs_server_apply", "Магазины: применить серверную половину (рестарт стойки)", "shop.apply"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _pc_cli(ctx, "применение серверной половины")
        _gate(self.name, cs, ctx)
        if not cs["check"]["server_needed"]:
            raise OpRefused("у набора №%d нет серверной половины — выкладывать нечего" % cs["id"])
        check_changelog()
        warn = ["рестарт стойки: объявление ботом Discord, 3 минуты, штатная остановка, выкладка, паритет Ch2, старт"]
        if cs["check"]["client_needed"] and cs["status"] != "released" and not cs["urgent"]:
            warn.append("клиент не выпущен: до выпуска игроки увидят старое, а сервер возьмёт новое" if cs["client_state"] != "applied"
                        else "клиентская половина записана в порт, но клиент не выпущен: до выпуска игроки увидят старое")
            if not p.get("unsynced_ok"):
                raise OpRefused("сервер раньше выпуска клиента — только явным решением владельца (ключ --unsynced-ok)")
        # ★ ревизия 36 Б-1: между проверкой и выкладкой (клиент копится днями) у игроков могли появиться строки кода, у которого
        #   меняется стопка или вес стопки — перечитать «на руках» ДО объявления; появились — отказ (дюп или потеря после рестарта)
        _codes, busy = held_guard(cs)
        if busy:
            raise OpRefused("после проверки набора у игроков появились коды со сменой стопки или веса стопки (%s): строки Joy1 после "
                            "рестарта значили бы другое (дюп или потеря) — выкладка не делается, стойка не тронута, объявления не было"
                            % busy)
        bad = area_guard(cs, "apply")                   # ★ А4.5: правила выдачи предметов награды — по живым таблицам, до объявления
        if bad:
            raise OpRefused("после проверки набора изменились данные стойки (%s) — выкладка не делается, стойка не тронута, объявления не было"
                            % "; ".join(bad))
        if p.get("confirm") != "restart":
            raise OpRefused("нужно подтверждение рестарта стойки (ключ --confirm-restart)")
        return {"text": "набор №%d: выложить %d файлов стойки рестартом с объявлением" % (cs["id"], cs["check"]["server"]["count"]),
                "warnings": warn}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        man = manifest_path(cs["id"])
        if not os.path.isfile(man):
            raise OpRefused("нет манифеста выкладки %s — сначала changeset server-dry" % SD.rel_area(man))
        m = json.load(open(man, encoding="utf-8"))
        _manifest_ok(cs, m)                  # ★ ревизия 31 Н-В1: без пересчёта набора по живым данным
        texts = [x["text"] for x in cs["check"]["positions"]]
        # ★ ревизия 30 В-3: ВСЕ проверки — до объявления: настоящий сухой прогон выкладчика (md5 базы, локальные файлы)
        rc0, out0 = run_deploy(man)
        if rc0 != 0 or "сухой прогон: всё готово" not in out0:
            raise OpRefused("сухой прогон выкладчика перед рестартом: код %d: %s — стойка не тронута, объявления не было"
                            % (rc0, " | ".join([ln for ln in out0.splitlines() if ln.strip()][-3:])))
        # ★ ревизия 41 В-1: рестарт набора — под тем же взаимоисключением стойки, что stack.* и задания (adm.job, «stack.changeset»);
        #   занято — отказ ДО объявления (ничего не тронуто)
        with _stack_lock(ctx, cs["id"], "выкладка") as g:
            rc, out = _restart(man, "", guard=guard_argv(cs["id"]))          # ★ ревизия 39 Н-3: перепроверка после остановки
            state, notes, lines = _after_restart(cs, man, rc, out, "")
            g.status, g.text = ("done" if state == "applied" else "failed"), "набор №%d: код %d, сервер %s" % (cs["id"], rc, state)
        st, srv, cli = TRANSITIONS[self.name]
        if state == "applied":
            notes += area_after_server(cs)               # ★ А4.6: доводка областей (AsdaFamePoints) по живой стойке
        if state:
            _update(cs["id"], st, srv, server_state=state, server_tag=m["tag"], server_note="; ".join(notes)[:1000] or None,
                    server_at=SD.utc_now(), status=derive_status(state, cs["client_state"], cs["status"] == "released", True))
            append_records(dict(cs, server_tag=m["tag"]), "server", texts, "apply" if state == "applied" else state, "; ".join(notes))
        else:
            _update(cs["id"], st, srv, server_note="; ".join(notes)[:1000] or None)
            if any("доведена до базы" in n for n in notes):
                raise OpRefused("стойка перезапущена, набор возвращён к базе: %s" % "; ".join(notes))
            raise OpRefused("выкладка не выполнена, стойка не изменена: %s" % ("; ".join(notes) or "код %d" % rc))
        rc2 = run_deploy(man, ["--check-started"])[0] if state == "applied" else None
        msg = ("серверная половина набора №%d выложена (метка %s); проверка старта: %s" % (cs["id"], m["tag"], "OK" if rc2 == 0 else "код %s" % rc2)
               if state == "applied" else "серверная половина набора №%d: %s" % (cs["id"], "; ".join(notes) or state))
        return {"after": {"server_state": state, "tag": m["tag"], "notes": notes, "check_started": rc2, "lines": lines}, "message": msg}


@register
class CsServerRollback(CsOp):
    name, title, perm = "shop.cs_server_rollback", "Магазины: откат серверной половины (рестарт стойки)", "shop.apply"

    def _plan(self, cs):
        man = manifest_path(cs["id"])
        if not os.path.isfile(man):
            raise OpRefused("нет манифеста выкладки %s" % SD.rel_area(man))
        m = json.load(open(man, encoding="utf-8"))
        f = facts(m)
        other = sorted(r for r, v in f.items() if v == "other")
        if other:
            raise OpRefused("на стойке чужие файлы (не база и не набор): %s — откат вслепую запрещён" % ", ".join(other[:3]))
        todo = sorted(r for r, v in f.items() if v == "new")
        if not todo:
            raise OpRefused("на стойке нет файлов набора №%d — откатывать нечего" % cs["id"])
        bak = SD.live_md5([r + ".bak_" + m["tag"] for r in todo])
        badbak = [r for r in todo if bak.get(r + ".bak_" + m["tag"]) != m["files"][r]["base"]]
        if badbak:
            raise OpRefused("нет бэкапа .bak_%s или это не база: %s" % (m["tag"], ", ".join(badbak[:3])))
        return man, m, todo

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _pc_cli(ctx, "откат серверной половины")
        _gate(self.name, cs, ctx)
        man, m, todo = self._plan(cs)
        check_changelog()
        warn = ["коробки и товары, проданные после выкладки, останутся у игроков; новые коды после отката не вскроются"]
        n = sales_since(cs)
        txt = "не прочитано" if n is None else "премиум %d, лавки NPC %d" % (n["gp7"], n["npc"])
        if n is None or n["gp7"] or n["npc"]:
            # ★ ревизия 30 М-10 (разбор §3.5) / 31 Н-В3, К-4: после первой продажи откат необратим — второе подтверждение
            warn.append("продаж затронутых кодов после выкладки: %s — откат необратим для купленного" % txt)
            if not p.get("irreversible_ok"):
                raise OpRefused("после выкладки были продажи затронутых кодов (%s) — нужно второе подтверждение (ключ --irreversible-ok)" % txt)
        # ★ ревизия 36 Б-1: после выкладки игроки набрали строки кода со сменой стопки или веса стопки (добыча, ремесло, почта —
        #   продажи их не видят): откат вернёт прежний смысл таблицы, и эти строки значили бы другое — второе подтверждение
        #   только владельцем с показом «на руках»; не прочитано — отказ
        _codes, busy = held_guard(cs)
        if busy:
            warn.append("на руках у игроков коды со сменой стопки или веса стопки: %s — после отката их строки Joy1 значили бы другое" % busy)
            if p.get("held_ok") != "held":
                raise OpRefused("после выкладки у игроков есть коды со сменой стопки или веса стопки (%s): после отката строки Joy1 значили "
                                "бы другое (стопка стала бы штучной вещью или наоборот, вес строки разошёлся бы) — нужно второе "
                                "подтверждение владельца (ключ --held-ok)" % busy)
            try:
                need_perms(ctx, [it["kind"] for it in cs.get("items") or []], "apply")
            except OpRefused:
                raise OpRefused("второе подтверждение отката при предметах на руках — только владелец (право применения набора)")
        # ★ А4.5: откат вернёт прежние предметы награды — их правила выдачи перепроверяются по живым таблицам (другой набор мог сменить
        #   item_table); нарушены — только вторым подтверждением владельца (тот же ключ --held-ok), не прочитано — отказ и с ключом
        bad = area_guard(cs, "rollback")
        if bad:
            warn.append("откат вернёт данные, которые по живым таблицам стойки уже не проходят проверку: %s" % "; ".join(bad))
            hard = [b for b in guard_hard(bad) if "не прочитаны" not in b]      # ★ ревизия 40 В-1: стойка не поднимется / вход не состоится
            if hard:
                raise OpRefused(("откат не делается и с ключом --held-ok: %s" % hard[0]) if len(hard) == 1 else
                                ("откат не делается и с ключом --held-ok (причин %d, первая): %s" % (len(hard), hard[0])))
            if p.get("held_ok") != "held" or guard_hard(bad):
                raise OpRefused("откат вернёт данные, которые по живым таблицам стойки не проходят проверку (%s) — нужно второе подтверждение "
                                "владельца (ключ --held-ok)" % "; ".join(bad))
            try:
                need_perms(ctx, [it["kind"] for it in cs.get("items") or []], "apply")
            except OpRefused:
                raise OpRefused("второе подтверждение такого отката — только владелец (право применения набора)")
        if p.get("confirm") != "restart":
            raise OpRefused("нужно подтверждение рестарта стойки (ключ --confirm-restart)")
        return {"text": "набор №%d: вернуть %d файлов стойки из .bak_%s рестартом с объявлением" % (cs["id"], len(todo), m["tag"]),
                "warnings": warn}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        man, m, todo = self._plan(cs)
        with _stack_lock(ctx, cs["id"], "откат") as g:                  # ★ ревизия 41 В-1
            rc, out = _restart(man, "rollback", guard=guard_argv(cs["id"], "rollback", p.get("held_ok") == "held"))   # ★ ревизия 39 Н-3
            state, notes, lines = _after_restart(cs, man, rc, out, "rollback")
            g.status, g.text = ("done" if state == "rolled_back" else "failed"), "набор №%d (откат): код %d, сервер %s" % (cs["id"], rc, state)
        st, srv, cli = TRANSITIONS[self.name]
        if state == "rolled_back":
            notes += area_after_server(cs)               # ★ А4.6: доводка областей (AsdaFamePoints) по живой стойке
        if state == "unknown":
            _update(cs["id"], st, srv, server_state="unknown", server_note="; ".join(notes)[:1000] or None)
            raise OpRefused("откат: состояние стойки не прочитано — changeset server-sync %d: %s" % (cs["id"], "; ".join(notes)))
        if state is None:
            _update(cs["id"], st, srv, server_note="; ".join(notes)[:1000] or None)
            raise OpRefused("откат не выполнен, стойка не изменена: %s" % ("; ".join(notes) or "код %d" % rc))
        _update(cs["id"], st, srv, server_state=state, server_note="; ".join(notes)[:1000] or None,
                status=derive_status(state, cs["client_state"], cs["status"] == "released", True))
        append_records(cs, "server", ["откат: " + "; ".join(x["text"] for x in cs["check"]["positions"])],
                       "rollback" if state == "rolled_back" else state, "; ".join(notes))
        if state != "rolled_back":
            raise OpRefused("откат серверной половины набора №%d выполнен не целиком: %s" % (cs["id"], "; ".join(notes)))
        return {"after": {"server_state": state, "notes": notes, "lines": lines},
                "message": "серверная половина набора №%d откачена%s" % (cs["id"], ("; " + "; ".join(notes)) if notes else "")}


@register
class CsServerSync(CsOp):
    name, title, perm = "shop.cs_server_sync", "Магазины: сверить серверную половину со стойкой", "shop.apply"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _pc_cli(ctx, "сверка серверной половины со стойкой")
        _gate(self.name, cs, ctx)
        if not os.path.isfile(manifest_path(cs["id"])):
            raise OpRefused("нет манифеста выкладки %s" % SD.rel_area(manifest_path(cs["id"])))
        return {"text": "набор №%d: прочитать md5 файлов набора на стойке и записать фактическое состояние (стойку не трогает)" % cs["id"],
                "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        f = facts(manifest_path(cs["id"]))
        new = sum(1 for v in f.values() if v == "new")
        base = sum(1 for v in f.values() if v == "base")
        other = [r for r, v in f.items() if v == "other"]
        if other:
            raise OpRefused("на стойке чужие файлы (не база и не набор): %s" % ", ".join(other[:3]))
        if new == len(f):
            state = "applied"
        elif base == len(f):
            state = "dry_ok" if cs["server_state"] in ("unknown", "partial_apply", "dry_ok") and not cs.get("server_at") else "rolled_back"
        else:
            state = "partial_rollback" if cs["server_state"] == "partial_rollback" else "partial_apply"
        st, srv, cli = TRANSITIONS[self.name]
        extra = area_after_server(cs) if state in ("applied", "rolled_back") else []     # ★ А4.6: повтор доводки (AsdaFamePoints)
        _update(cs["id"], st, srv, server_state=state, server_note=("; ".join(["сверено со стойкой: новых %d, базы %d" % (new, base)] + extra))[:1000],
                status=derive_status(state, cs["client_state"], cs["status"] == "released", True))
        return {"after": {"server_state": state, "new": new, "base": base, "notes": extra},
                "message": "набор №%d: серверная половина по стойке — %s (новых %d, базы %d)" % (cs["id"], state, new, base)}


# ---------------------------------------------------------------------------------------------------------------- клиент (ПК, владелец)
def _ue_run(script, log, marker, env=None, expect=None, require=None):
    """Скрипт редактора без окон (run_headless_safe.py: commandlet -NullRHI) → (код, вывод). Вызывать внутри ue_queue.Slot."""
    argv = [sys.executable, os.path.join(SD.UE_TOOLS, "run_headless_safe.py"), os.path.join(SD.UE_TOOLS, script), "--log", log,
            "--marker", marker, "--timeout", "1800"]
    if require:
        argv += ["--require", require]
    for a in expect or []:
        argv += ["--expect-asset", a]
    p = subprocess.run(argv, env=dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {})), capture_output=True, timeout=2400)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def _ue_queue():
    d = config.port_code(os.path.join(SD.PORT, "AstoryClient", "DEPLOY", "_tools"))   # ★ ревизия 56 С-1: только ПК
    if d not in sys.path:
        sys.path.insert(0, d)
    import ue_queue                       # noqa: E402 — без побочных эффектов при импорте
    return ue_queue


def allowed_client_path(path):
    """Путь клиентской правки — только из разрешённого набора (ревизия 30 К-3)."""
    ap = os.path.normcase(os.path.abspath(path))
    # ★ А4.0: + ведомости ItemDB (_value_overlay / _tail_append таблиц LEDGER_TABLES), файлы областей реестра (CLIENT_FILES)
    #   и пути, которые область признаёт своими (магазины — js<N>.spd каталога лавок)
    ok = {os.path.normcase(os.path.abspath(x)) for x in list(SD.CLIENT_FILES.values()) + [SD.PANEL_TAIL] + SD.all_ledger_paths()}
    return ap in ok or any(a.allowed_extra(ap) for a in SD.AREAS if hasattr(a, "allowed_extra"))


def _dt_job(job, bdir, tag):
    """Точечная заливка одного DT: сухой прогон, затем запись → (код, строка). Сторож asda_ml_dt_point: ассет = csv_old."""
    jf = os.path.join(bdir, "dt_job_%s_%s.json" % (tag, job["dt"].rsplit("/", 1)[1]))
    with open(jf, "w", encoding="utf-8") as f:
        json.dump([job], f, ensure_ascii=False, indent=1)
    lg = os.path.join(bdir, "dt_%s_%s" % (tag, job["dt"].rsplit("/", 1)[1]))
    rc, _o = _ue_run("asda_ml_dt_point.py", lg + "_dry.log", "ЗАВЕРШЕНО: точечные DT", {"ASDA_PT_JOBS": jf, "ASDA_PT_DRYRUN": "1"})
    if rc != 0:
        return rc, "сухой прогон %s: код %d" % (job["dt"], rc)
    rc, _o = _ue_run("asda_ml_dt_point.py", lg + ".log", "ЗАВЕРШЕНО: точечные DT", {"ASDA_PT_JOBS": jf}, expect=[job["dt"]])
    return rc, "%s: код %d" % (job["dt"], rc)


def _json_job(job, bdir, tag):
    """★ А4.2: точечная правка вложенного DT (DT_QuestBook) — asda_dt_json_point.py: сухой прогон, затем запись → (код, строка).
    Сторож скрипта: значение ячейки ассета = «was» (уже «now» — пропуск), иначе СТОП; после заливки — сверка «изменилось ровно это»."""
    name = job["dt"].rsplit("/", 1)[1]
    jf = os.path.join(bdir, "json_job_%s_%s.json" % (tag, name))
    with open(jf, "w", encoding="utf-8") as f:
        json.dump([{"dt": job["dt"], "edits": job["edits"]}], f, ensure_ascii=False, indent=1)
    lg = os.path.join(bdir, "dtjson_%s_%s" % (tag, name))
    rc, _o = _ue_run("asda_dt_json_point.py", lg + "_dry.log", "ЗАВЕРШЕНО: JSON-точечные DT", {"ASDA_JP_JOBS": jf, "ASDA_JP_DRYRUN": "1"})
    if rc != 0:
        return rc, "сухой прогон %s: код %d" % (job["dt"], rc)
    rc, _o = _ue_run("asda_dt_json_point.py", lg + ".log", "ЗАВЕРШЕНО: JSON-точечные DT", {"ASDA_JP_JOBS": jf}, expect=[job["dt"]])
    return rc, "%s: код %d" % (job["dt"], rc)


def _importer(key, bdir):
    script, asset = SD.IMPORTERS[key]
    name = asset.rsplit("/", 1)[1]
    # ★ ревизия 30 В-6: маркер — итоговая строка ПОСЛЕ сохранения DT; --require — только «(ok)»
    return _ue_run(script, os.path.join(bdir, key + ".log"), "ЗАВЕРШЕНО: импорт %s" % name, expect=[asset],
                   require=r"ЗАВЕРШЕНО: импорт %s \(ok\)" % name)


def client_write(cs, plan, bdir, restore=False):
    """Запись клиентских файлов (бэкап до записи) и заливка DT через очередь UE. restore=True — откат:
    1) текущие (применённые) файлы копируются в <bdir>/applied/ — от них строится сторож DT (ревизия 30 В-5);
    2) файлы порта возвращаются из бэкапа; 3) DT: csv_old = применённый, csv_new = бэкап; если ассет ещё не был залит (сбой
    применения), сухой прогон с csv_old = бэкап проходит — заливка не нужна."""
    os.makedirs(bdir, exist_ok=True)
    written = []
    for path in plan["files"]:
        if not allowed_client_path(path):
            raise OpRefused("путь %s вне разрешённых клиентских файлов — отказ" % SD.rel_area(path))
    applied_dir = os.path.join(bdir, "applied")
    bk_of = lambda x: os.path.join(bdir, SD.area_rel(x))
    if restore:
        # ★ ревизия 36 М-3: сначала md5 и бэкапы ВСЕХ файлов плана, потом запись — чужая правка второго файла (например ведомости,
        #   дописанной другим набором) не оставит первый уже восстановленным при состоянии applied
        cur_of, bad, nobak = {}, [], []
        for path, info in plan["files"].items():
            cur = cur_of[path] = SD.md5f(path) if os.path.isfile(path) else "none"
            if cur not in (info["new"], info["old"]):
                bad.append(SD.rel_area(path))
            elif cur != info["old"] and info.get("old") != "none" and not os.path.isfile(bk_of(path)):
                nobak.append(SD.rel_area(bk_of(path)))
        if bad:
            raise OpRefused("изменены после применения: %s — откат вручную, ни один файл не записан" % ", ".join(bad))
        if nobak:
            raise OpRefused("нет бэкапа %s — ни один файл не записан" % ", ".join(nobak))
        for path, info in plan["files"].items():
            bk = bk_of(path)
            cur = cur_of[path]
            ap = os.path.join(applied_dir, SD.area_rel(path))
            # ★ ревизия 31 Н-В4: копия применённого — один раз и только с «новым» файлом (повтор отката её не портит)
            if cur == info["new"] and cur != info["old"] and not os.path.isfile(ap):
                os.makedirs(os.path.dirname(ap), exist_ok=True)
                shutil.copy2(path, ap)
            if cur == info["old"]:
                written.append(SD.rel_area(path))          # уже прежний (не записывался или откачен прошлой попыткой)
                continue
            if info.get("old") == "none":                  # файл создан применением (хвост витрины панели) — убрать
                os.remove(path)
            elif not os.path.isfile(bk):
                raise OpRefused("нет бэкапа %s" % SD.rel_area(bk))
            else:
                shutil.copy2(bk, path)
                if SD.md5f(path) != info["old"]:
                    raise OpRefused("%s записан неверно (md5)" % SD.rel_area(path))
            written.append(SD.rel_area(path))
    else:
        # ★ ревизия 36 М-3: md5 ВСЕХ файлов = «было» плана — до бэкапа и первой записи (иначе план устарел: пересобрать)
        moved = [SD.rel_area(path) for path, info in plan["files"].items()
                 if (SD.md5f(path) if os.path.isfile(path) else "none") != info["old"]]
        if moved:
            raise OpRefused("изменены после сборки плана: %s — ни один файл не записан, повторите применение" % ", ".join(moved))
        # ★ ревизия 31 Н-М1: бэкап ВСЕХ файлов — до первой записи
        for path in plan["files"]:
            bk = bk_of(path)
            if os.path.isfile(path) and not os.path.isfile(bk):
                os.makedirs(os.path.dirname(bk), exist_ok=True)
                shutil.copy2(path, bk)
                if SD.md5f(bk) != SD.md5f(path):
                    raise OpRefused("бэкап %s не сошёлся" % SD.rel_area(bk))
        for path in plan["files"]:
            new = plan["_bytes"][path]
            tmp = path + ".cs_tmp"
            try:
                with open(tmp, "wb") as f:
                    f.write(new)
                os.replace(tmp, path)
            except OSError as ex:
                if os.path.isfile(tmp):
                    os.remove(tmp)
                raise OpRefused("%s не записан: %s — состояние «запись начата», откат: changeset client-rollback" % (SD.rel_area(path), ex))
            if SD.md5f(path) != SD.md5b(new):
                raise OpRefused("%s записан неверно (md5)" % SD.rel_area(path))
            written.append(SD.rel_area(path))
    lines = []
    q = _ue_queue()
    with q.Slot("exclusive", "admin changeset %d client-%s" % (cs["id"], "rollback" if restore else "apply")):
        for j in plan["dt_jobs"]:
            bk = os.path.join(bdir, SD.area_rel(j["file"]))
            if restore:
                ap = os.path.join(applied_dir, SD.area_rel(j["file"]))
                if not os.path.isfile(ap):               # файл не записывался — DT не заливался: проверить «уже прежний»
                    ap = j["file"]
                rc, ln = _dt_job({"dt": j["dt"], "csv_new": j["file"], "csv_old": ap, "allow_rows": j["allow_rows"], "allow_cols": []},
                                 bdir, "restore")
                if rc != 0:
                    rc2, ln2 = _dt_job({"dt": j["dt"], "csv_new": j["file"], "csv_old": j["file"], "allow_rows": j["allow_rows"],
                                        "allow_cols": []}, bdir, "already")
                    if rc2 == 0:
                        ln = "%s: ассет уже в прежнем состоянии" % j["dt"]
                        rc = 0
            else:
                rc, ln = _dt_job({"dt": j["dt"], "csv_new": j["file"], "csv_old": bk, "allow_rows": j["allow_rows"], "allow_cols": []},
                                 bdir, "apply")
            lines.append(ln)
            if rc != 0:
                raise OpRefused("точечная заливка DT: %s (журналы в %s)" % (ln, SD.rel_area(bdir)))
        for j in plan.get("json_jobs", []):              # ★ А4.2: откат — те же ячейки обратно (was ↔ now)
            job = dict(j, edits=[dict(e, was=e["now"], now=e["was"]) for e in j["edits"]]) if restore else j
            rc, ln = _json_job(job, bdir, "restore" if restore else "apply")
            lines.append(ln)
            if rc != 0:
                raise OpRefused("точечная правка DT (JSON): %s (журналы в %s)" % (ln, SD.rel_area(bdir)))
        for key in plan["importers"]:
            rc, _out = _importer(key, bdir)
            lines.append("%s: код %d" % (SD.IMPORTERS[key][0], rc))
            if rc != 0:
                raise OpRefused("импортёр %s: код %d (журнал %s)" % (SD.IMPORTERS[key][0], rc, SD.rel_area(os.path.join(bdir, key + ".log"))))
    return written, lines


@register
class CsClientApply(CsOp):
    name, title, perm = "shop.cs_client_apply", "Магазины: применить клиентскую половину (RawAssets/DT)", "shop.apply"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _pc_cli(ctx, "применение клиентской половины")
        _gate(self.name, cs, ctx)
        if not cs["check"]["client"]:
            raise OpRefused("у набора №%d нет клиентской половины" % cs["id"])
        check_changelog()
        return {"text": "набор №%d: записать правки RawAssets и ведомостей, залить DT (очередь UE, без окон); выпуск — НЕ делается"
                % cs["id"], "warnings": ["редактор UE должен быть закрыт; результат копится до выпуска клиента"]}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        s = cs["check"]
        plan = SD.client_plan(s["client"], cs["id"])         # ★ ревизия 31 Н-В1: утверждённые правки, «было» — по живому порту
        if plan["errors"]:
            raise OpRefused("клиентская половина не собирается: %s" % "; ".join(plan["errors"][:4]))
        bdir = os.path.join(SD.BACKUP_DIR, "%s_cs%d" % (datetime.date.today().isoformat(), cs["id"]))
        os.makedirs(bdir, exist_ok=True)
        with open(os.path.join(bdir, "client_plan.json"), "w", encoding="utf-8") as f:   # план — для отката из бэкапа
            json.dump({k: v for k, v in plan.items() if k != "_bytes"}, f, ensure_ascii=False, indent=1)
        st, srv, cli = TRANSITIONS[self.name]
        # ★ ревизия 30 М-7: «запись начата» — ДО первой записи (сбой посреди оставит applying и откроет откат)
        _update(cs["id"], st, None, cli, client_state="applying", client_backup=bdir[:400], status="applied_client",
                client_at=SD.utc_now())
        written, lines = client_write(cs, plan, bdir)
        lines += plan.get("warnings", [])                # ★ ревизия 34 К-3: предупреждения плана (снимок службы устарел и т. п.)
        _update(cs["id"], ("applied_client",), None, ("applying",), client_state="applied")
        append_records(cs, "client", [x["text"] for x in s["positions"] if x["client"]])
        return {"after": {"client_state": "applied", "files": written, "lines": lines, "backup": bdir},
                "message": "клиентская половина набора №%d записана (файлов %d); выпуск клиента — по слову владельца" % (cs["id"], len(written))}


@register
class CsClientRollback(CsOp):
    name, title, perm = "shop.cs_client_rollback", "Магазины: откат клиентской половины", "shop.apply"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))
        _pc_cli(ctx, "откат клиентской половины")
        if cs["status"] == "released":
            raise OpRefused("набор уже выпущен с клиентом — откат только новым выпуском (новый набор)")
        _gate(self.name, cs, ctx)
        check_changelog()
        return {"text": "набор №%d: вернуть файлы порта из %s и перезалить DT" % (cs["id"], cs["client_backup"]), "warnings": []}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        self.preview(ctx, p)
        pf = os.path.join(cs["client_backup"] or "", "client_plan.json")
        if not os.path.isfile(pf):
            raise OpRefused("нет плана применения %s" % SD.rel_area(pf))
        plan = json.load(open(pf, encoding="utf-8"))
        written, lines = client_write(cs, plan, cs["client_backup"], restore=True)
        st, srv, cli = TRANSITIONS[self.name]
        _update(cs["id"], st, None, cli, client_state="rolled_back",
                status=derive_status(cs["server_state"], "rolled_back", False, True))
        append_records(cs, "client", ["откат: " + "; ".join(x["text"] for x in cs["check"]["positions"] if x["client"])], "rollback")
        return {"after": {"client_state": "rolled_back", "files": written, "lines": lines},
                "message": "клиентская половина набора №%d откачена" % cs["id"]}


@register
class CsReleased(CsOp):
    name, title, perm = "shop.cs_released", "Магазины: отметить «выпущен с клиентом»", "shop.apply"

    def preview(self, ctx, p):
        cs = get(_cs_id(p))                       # ★ ревизия 30 В-2: с итогом проверки (server_needed)
        _pc_cli(ctx, "отметка выпуска")
        _gate(self.name, cs, ctx)
        rel = SD.releases_after(cs["client_at"])
        if not rel:
            raise OpRefused("выпуска клиента после применения клиентской половины (%s) в Releases/releases.log нет" % cs["client_at"])
        warn = []
        if cs["check"]["server_needed"] and cs["server_state"] != "applied":
            warn.append("серверная половина ещё не выложена — changeset server-apply %d (после выпуска — без --unsynced-ok)" % cs["id"])
        return {"text": "набор №%d выпущен с клиентом %s (%s)" % (cs["id"], rel["version"], rel["at"]), "warnings": warn, "expect": rel}

    def apply(self, ctx, p, prev):
        cs = get(_cs_id(p))
        pv = self.preview(ctx, p)
        rel = pv["expect"]
        st, srv, cli = TRANSITIONS[self.name]
        _update(cs["id"], st, None, cli, status="released", released_at=datetime.datetime.fromisoformat(rel["at"]))   # UTC
        return {"after": {"released": rel, "warnings": pv["warnings"]},
                "message": "набор №%d отмечен выпущенным (%s)%s" % (cs["id"], rel["version"], ("; " + pv["warnings"][0]) if pv["warnings"] else "")}
