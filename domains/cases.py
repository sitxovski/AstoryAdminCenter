# -*- coding: utf-8 -*-
# Copyright (c) 2026 @sitxovski (Discord)
"""cases.py — «Античит: дела» (шаг А6.7, 22.11.2026; разбор research_a6_economy_20261121.md §3 строка А6.7, §1 «Дела san.*», «Блок учётки»;
решения владельца 22.11 — ADMIN_TOOL_PLAN.md §6 п.5; отчёт — Reports/admin_center/impl_a6_econ_20261121.md §А6.7).

Перенос журнала дел AstoryServer/Tools/Anticheat/ac_case.py в операции панели БЕЗ СМЕНЫ ПРАВИЛ ДЕЛ: команды open / attach / export / decide / execute /
withdraw / appeal / close / verify / rollback-report и показ (render_case, v_cases, case_sources, verify_case, history_hint, лестница
ac_case_config.json, «два независимых источника» со ступени two_sources_from_step, переходы статусов san.UP_SAN_SetStatus) исполняет ТОТ ЖЕ
код исходника — частной копией (domains/acsrc.load: на сервере — только ext/anticheat со сверкой md5 манифеста выкладки, на ПК — исходник
порта). Меняются только входы (решения владельца №1–3):
  * БЛОК ДЕЛА — существующая операция панели account.block (domains/accounts.py, поведение не меняется) с причиной «AC-NNNN s<ступень> <часы>h…»
    (та же строка, что у исходника, ascii_reason) вместо штатного ac0_block_user.sql; её запись журнала adm.audit — своя, обычная (откат —
    как у любого блока). Блок не встал (verify account.block или us_block ≠ 5 / нет строки BlockList) — блок откатывается тем же undo
    account.block, дело не исполняется (транзакция san.* откатывается). Снятие (lift) — account.unblock (как OPBlockDel) вместо
    ac0_unblock_user.sql, с теми же проверками исходника (чужие блоки учётки — только с all_blocks, после снятия us_block 0 и BlockList пуст);
  * ХРАНИЛИЩЕ доказательств — каталог службы на сервере (CASES_ROOT = @@ASTORY_SERVER_ROOT_ESC@@\\AdminCenter\\cases; права — наследование от дерева службы:
    только SYSTEM и Administrators; выкладка его не трогает). На ПК записи с файлами нет (отказ), чтение базы — есть;
  * ФАЙЛЫ — выдержки журналов стойки через белый список domains/logs (источник → копия → вид → шаблон имени; чтение с общим доступом,
    бюджет чтения пользователя logs.charge): только строки с подстроками отбора (вместо регулярки исходника), маска секретов logs.mask_line и
    32-hex исходника (mask_secrets) — ДО отбора; предел — max_file_mb конфига исходника и logs.SCAN_FILE_MAX; sha256 источника и выдержки;
  * БАЗА — запись ТОЛЬКО joylog1.san.* логином asda_ops (sql/adminc_21_san.sql: SELECT san.*, INSERT case_log / case_event / evidence /
    case_block, UPDATE столбцов cases / case_block без status, EXEC san.UP_SAN_CaseOpen / UP_SAN_SetStatus; проверка исходника
    assert_san_write — на каждую запись); чтение всего прочего (ac.*, AsdaStoryOp, Joy1) — логином службы asda_admin (db.GameReader,
    assert_select_only); текст — сырой драйвер, как у исходника (снимки событий и их sha256 те же);
  * КТО — учётка панели (ctx.login; консоль — только от имени учётки панели: --as <логин>, ревизия 59 Н-3); права: ac.view — смотреть,
    ac.case (owner / admin / gm) — open / attach / export / rollback_report, ac.decide_low (owner / admin / gm) — decide / execute / withdraw
    ступеней 0–2, ac.decide (owner / admin) — то же со ступени 3 (решение владельца №3) и lift / close, ac.appeal (owner / admin) — апелляция;
    пересматривает ДРУГОЕ лицо — другая учётка панели (ключа исходника --same-person нет; ОГРАНИЧЕНИЕ: две учётки панели одного человека
    не различаются — атрибута «лицо» у adm.users нет); снять правило двух источников и закрыть без проверки целостности — только владелец;
    дела служебных учёток (номер ≤ 5000) — только владелец; подтверждение блока и снятия — номером дела (как ввод у исходника);
  * ПРЕДПРОСМОТР — тот же код в транзакции с откатом: блок / снятие не выполняются (только предпросмотр account.block / unblock), выдержка
    не читается, manifest.json не пишется, новые файлы удаляются.
Побочных эффектов при импорте нет.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import threading
import time

from core import audit, config, db, ops
from core.ops import Operation, OpRefused, register
from domains import acsrc, logs

AC_SRC = acsrc.AC_SRC                    # исходник на ПК (AstoryServer/Tools/Anticheat)
AC_EXT = acsrc.AC_EXT                    # его копия в дереве службы (ext/anticheat — кладёт выкладка с манифестом md5)
AC_FILES = ("ac_case.py", "ac_case_config.json")   # = autoblock.AC_FILES (выкладка их уже кладёт)
CASES_ROOT = config.SERVICE_ROOT + r"\cases"       # хранилище доказательств на сервере (решение владельца №1)
SVC_MAX = 5000                           # служебные учётки (players.OPERATOR_MAX_UID): их дела — только владелец
EVENTS_MAX = 200                         # событий за одно приложение (список или окно)
NEEDLES_MAX = 5                          # подстрок отбора выдержки
LIST_MAX = 500                           # дел в списке
SERIALS_MAX = 50                         # серийников в отчёте отката (списком)
ROLLBACK_MAX = 200                       # серийников из окна (= умолчание --max исходника)
HEAVY_PER_HOUR = 30                      # тяжёлых действий (окно событий, выдержка, отчёт отката, проверка всех дел) на пользователя в час
LOG_SAN = re.compile(r"(?<![A-Za-z0-9_])san\.", re.I)
DAY_RX = re.compile(r"^(\d{8})(?: (\d{2}):(\d{2}))?$")
GUID_RX = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
CASE_RX = re.compile(r"^(?:AC-)?0*(\d{1,6})$", re.I)
ASCII_RX = re.compile(r"^[\x20-\x7E]*$")
DECIDE_HIGH = 3                          # ★ ревизия 59 Н-2 (решение владельца №3): решение со ступени 3 — admin / owner, ступени 0–2 — и gm
CLI_AS = ("консоль: действия с делами — от имени учётки панели, укажите --as <логин панели> (апелляцию пересматривает другое лицо — "
          "сверка по учётке панели)")
STORE_PC = "хранилище доказательств — каталог службы на сервере: дела с записью ведутся в панели на сервере (на ПК — только просмотр)"

STORE_OVERRIDE = None                    # самотест: свой корень хранилища (работает и на ПК)
XLAT = None                              # самотест: {имя базы в SQL исходника: имя базы стенда}
_heavy = {}                              # пользователь → [времена тяжёлых действий]
_heavy_lock = threading.Lock()


# ---------------------------------------------------------------- исходник и хранилище

def source():
    """Частная копия ac_case.py и конфиг → (модуль, cfg, {where, code_md5, config_md5}). На сервере — только ext/ с манифестом."""
    d = acsrc.pick(AC_SRC, AC_EXT)
    try:
        mods, h = acsrc.load(d, ("ac_case",), "cases_src_")
        raw = acsrc.read_verified(os.path.join(d, "ac_case_config.json"))
    except (OSError, ImportError) as ex:
        raise OpRefused("исходник дел ac_case не прочитан: %s" % (getattr(ex, "filename", None) or ex.__class__.__name__))
    m = mods["ac_case"]
    cfg = dict(m.DEFAULT_CONFIG)                         # = ac_case.load_config(): умолчания + файл
    try:
        cfg.update(json.loads(raw.decode("utf-8")))
        m.ladder_map(cfg)
    except (ValueError, m.CaseError) as ex:
        raise OpRefused("конфиг дел ac_case_config.json не разобран: %s" % str(ex)[:200])
    return m, cfg, {"where": "ext" if acsrc._under(d, acsrc.EXT) else "port", "code_md5": h,
                    "config_md5": hashlib.md5(raw).hexdigest()}


def store_root(write=True):
    """Корень хранилища: подмена самотеста или каталог службы на сервере; на ПК запись — отказ."""
    if STORE_OVERRIDE:
        return STORE_OVERRIDE
    if config.get().on_server:
        return CASES_ROOT
    if write:
        raise OpRefused(STORE_PC)
    return None


def _x(sql):
    """Имена баз в SQL исходника → базы стенда (только самотест)."""
    if not XLAT:
        return sql
    for a, b in XLAT.items():
        sql = re.sub(r"(?<![A-Za-z0-9_\[])%s(?=\.)" % re.escape(a), b, sql, flags=re.I)
    return sql


def _heavy_charge(user, now=None):
    """Тяжёлое действие: не больше HEAVY_PER_HOUR на пользователя за 60 минут."""
    now = time.monotonic() if now is None else now
    with _heavy_lock:
        lst = [t for t in _heavy.get(user, []) if now - t < 3600]
        if len(lst) >= HEAVY_PER_HOUR:
            raise OpRefused("слишком много тяжёлых действий с делами — не больше %d в час на пользователя, подождите" % HEAVY_PER_HOUR)
        lst.append(now)
        _heavy[user] = lst


def _sql_reason(ex):
    """Причина ошибки драйвера без строки подключения (как db._sql_reason)."""
    s = str(ex.args[1] if len(getattr(ex, "args", ())) > 1 else ex)
    s = re.sub(r"\[[^\]]*\]", "", s)
    return s.split("(SQL")[0].strip()[:300]


# ---------------------------------------------------------------- сеанс: модуль исходника + две связи с базой

class Session:
    """Один запуск команды: частная копия исходника (m), чтение R (asda_admin), запись J (asda_ops, только san.*), контекст исходника k."""

    def __init__(self, pctx, write, dry):
        self.pctx, self.write, self.dry = pctx, write, dry
        self.m, self.cfg, self.src = source()
        self.root = store_root(write) if write else (STORE_OVERRIDE or (CASES_ROOT if config.get().on_server else None))
        self.out = io.StringIO()
        self.comp = []                                  # выполненные операции блока/снятия: [(имя, № журнала, параметры)] — откат при сбое
        self.R = self.J = None
        try:
            self.R = db.GameReader("joylog1")
            if write:
                self.J = db.GameWriter("joylog1")
        except db.DbError as ex:
            self.close()
            raise OpRefused("дела: %s" % ex)
        self.db = _panel_db(self.m, self.J, self.R)
        self.k = self.m.Ctx(self.cfg, self.db, self.root, (pctx.login or "?")[:64], self.out)
        if dry:
            self.m.write_manifest = lambda *_a, **_k: None   # предпросмотр: manifest.json не переписывается
        self.m.apply_block = self._apply_block
        self.m.attach_file = self._attach_excerpt

    def lines(self):
        return [x.strip() for x in self.out.getvalue().splitlines() if x.strip()]

    def close(self):
        for c in (self.J, self.R):
            if c is not None:
                c.close()
        self.J = self.R = None

    # ---- блок дела = account.block (решение владельца №2)
    def _apply_block(self, ctx, c, step, hours, reason_en=None):
        m, dbx = self.m, ctx.db
        reason = m.ascii_reason("%s s%d %sh%s" % (c["case_no"], step, hours, (": " + reason_en) if reason_en else ""))
        if not reason.startswith(c["case_no"] + " "):
            raise m.CaseError("причина блока должна начинаться с номера дела")
        login = (c["login"] or "").rstrip()
        u = dbx.one("SELECT us_id, us_block, Flag FROM AsdaStoryOp.dbo.Us_member WHERE Userindex = ?", (c["user_index"],))
        if not u or u["us_id"].rstrip() != login:
            raise m.CaseError("логин учётки изменился с открытия дела (%s -> %s)" % (login, u and u["us_id"]))
        if u["Flag"] == 1:
            ctx.p("ВНИМАНИЕ: учётка числится в игре - блок не выкидывает (нужен GM Kick 6018 или выход игрока)")
        p = {"uid": int(c["user_index"]), "hours": int(hours), "reason": reason, "case": c["case_no"]}   # case — откат только через дело (р59 Н-5)
        op = ops.REGISTRY["account.block"]
        if not self.pctx.can(op.perm):
            raise m.CaseError("блок дела — операция account.block, нужно право «%s»" % op.perm)
        try:
            prev = op.preview(self.pctx, p)
        except OpRefused as ex:
            raise m.CaseError("account.block: %s" % ex)
        if self.dry:
            ctx.p("предпросмотр: %s" % prev["text"])
            for w in prev.get("warnings") or []:
                ctx.p("  " + w)
            return
        try:
            res = op.apply(self.pctx, p, prev)
        except OpRefused as ex:
            raise m.CaseError("account.block: %s" % ex)
        aid = ops._finish(self.pctx, op.name, op.target(p), p, res, undo_of=None)
        self.comp.append((op.name, aid, p))
        try:
            op.verify(self.pctx, p, res)
        except OpRefused as ex:
            raise m.CaseError("блок не встал (%s) - блок откатывается, дело не исполнено" % ex)
        row = dbx.one("SELECT TOP 1 Userindex, Uid, BlackDate, CloseDate, Reason FROM AsdaStoryOp.dbo.BlockList "
                      "WHERE Userindex = ? AND Reason = ? ORDER BY BlackDate DESC", (c["user_index"], reason))
        ub = dbx.one("SELECT us_block FROM AsdaStoryOp.dbo.Us_member WHERE Userindex = ?", (c["user_index"],))
        if not row or not ub or ub["us_block"] != 5:
            raise m.CaseError("после account.block нет строки BlockList / us_block != 5 - блок откатывается, дело не исполнено")
        via = "панель account.block, журнал №%d" % aid
        dbx.w("INSERT INTO joylog1.san.case_block (case_id, user_index, uid, hours, reason, black_date, close_date, applied_by, apply_via) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (c["case_id"], c["user_index"], login, hours, reason, row["BlackDate"], row["CloseDate"],
                                             ctx.actor, via))
        text = "блок: us_block = 5, BlockList %s .. %s, причина «%s» (%s)" % (row["BlackDate"], row["CloseDate"], reason, via)
        m.mark_executed(ctx, c, text, "decision", "block")
        ctx.p("исполнено: " + text)

    # ---- выдержка журнала стойки (белый список logs, маска секретов) вместо копии файла ПК
    def _attach_excerpt(self, ctx, c, spec, label, excerpt=None, note=None, kind=None, sub="files"):
        m, dbx, cid = self.m, ctx.db, c["case_id"]
        src = logs.source(spec["source"])
        d, rel_dir = logs._dir_of(spec["source"], spec["proc"], spec.get("kind"))
        logs._file_ok(spec["source"], spec["name"])
        if src["writer"] == "exclusive":
            raise m.CaseError("журнал «%s» пишется без общего доступа - выдержка из него не делается" % spec["source"])
        path = d + "\\" + spec["name"]
        shown = (rel_dir + "\\" if rel_dir else "") + spec["name"]
        st = logs._io(src, "stat")(path)
        if st is None:
            raise m.CaseError("нет файла: " + shown)
        size, mtime_ms = st[0], st[1]
        cap = int(ctx.cfg["max_file_mb"]) << 20
        if size > cap:
            raise m.CaseError("журнал больше %d МБ (max_file_mb) - выдержка из него не делается" % ctx.cfg["max_file_mb"])
        if size > logs.SCAN_FILE_MAX:
            raise m.CaseError("журнал больше %d МБ - выдержка читает файл целиком, такой файл не читается" % (logs.SCAN_FILE_MAX >> 20))
        if self.dry:
            ctx.p("предпросмотр: выдержка из %s (%d б) по подстрокам: %s" % (shown, size, " | ".join(excerpt)))
            return "files/(предпросмотр)", ""
        _heavy_charge(self.pctx.login)
        show_ip = self.pctx.can("logs.view_ip")
        needles = [x.lower() for x in excerpt]
        if not logs._SEM.acquire(timeout=logs.READ_WAIT_S):
            raise logs.Throttled("служба занята чтением журналов (одновременно не больше %d) — повторите через несколько секунд" % logs.READERS)
        picked, h_src = [], hashlib.sha256()
        try:
            logs.charge(self.pctx.login, size + logs.HEAD)
            rd = logs._io(src, "read")
            carry, pos, utf16, ln = b"", 0, False, 0
            while pos < size:
                hb, raw = rd(path, pos, min(logs.SCAN_MAX, size - pos), logs.HEAD if pos == 0 else 0)
                if pos == 0:
                    utf16 = logs._is_utf16(hb)
                if not raw:
                    break
                h_src.update(raw)
                pos += len(raw)
                raw = carry + raw
                cut = logs._last_nl(raw, utf16) if pos < size else len(raw)
                carry = raw[cut:]
                texts = logs._decode(raw[:cut], src["enc"], utf16)
                if cut and texts and texts[-1] == "" and pos < size:
                    texts.pop()
                for t in texts:
                    ln += 1
                    s = m.mask_secrets(logs.mask_line(t, show_ip)[0])
                    if any(n in s.lower() for n in needles):
                        picked.append((ln, s))
        finally:
            logs._SEM.release()
        s_sha, s_size = h_src.hexdigest(), pos
        s_mtime = datetime.datetime.fromtimestamp(mtime_ms / 1000.0).replace(microsecond=0)
        dd = os.path.join(m.case_dir(ctx.root, c), sub)
        os.makedirs(dd, exist_ok=True)
        seq = 1 + len([f for f in os.listdir(dd) if re.match(r"^\d{3}_", f)])
        name = "%03d_%s.excerpt.txt" % (seq, m.safe_name(spec["name"]))
        dst = os.path.join(dd, name)
        if os.path.exists(dst):
            raise m.CaseError("файл уже есть в хранилище: " + dst)
        ctx.created.append(dst)
        with io.open(dst, "w", encoding="utf-8", newline="\n") as o:
            for line in ("выдержка для %s; источник %s (стойка)" % (c["case_no"], shown),
                         "источник: %d б, изменён %s, sha256 %s" % (s_size, s_mtime.isoformat(), s_sha),
                         "отбор: строки с подстроками %s (без учёта регистра); секреты и 32-hex замаскированы ДО отбора%s; формат «номер строки<TAB>текст»"
                         % (" | ".join(excerpt), "" if show_ip else ", IP и MAC скрыты")):
                o.write("# " + line + "\n")
            for i, s in picked:
                o.write("%d\t%s\n" % (i, s))
        ctx.p("  выдержка: %d строк" % len(picked))
        h, fsize = m.sha256_file(dst)
        rel = sub + "/" + name
        try:
            dbx.w("INSERT INTO joylog1.san.evidence (case_id, kind, rel_path, size_bytes, sha256, source_label, source_path, source_size, "
                  "source_mtime, source_sha256, added_by, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (cid, "excerpt", rel, fsize, h, label, "v2:" + shown, s_size, s_mtime, s_sha, ctx.actor, note))
            dbx.log(cid, ctx.actor, "attach_file", "%s: %s (%d б, sha256 %s); источник «%s» %s" % ("excerpt", rel, fsize, h, label, "v2:" + shown))
        except Exception:
            os.remove(dst)
            raise
        ctx.p("  + %s %s  sha256 %s" % ("excerpt", rel, h))
        return rel, h

    # ---- снятие блока дела = account.unblock (как OPBlockDel), проверки — как cmd_lift исходника
    def lift(self, a):
        m, dbx, ctx = self.m, self.db, self.k
        c = m.get_case(dbx, m.parse_case_id(a.case), lock=True)
        no = c["case_no"]
        act = dbx.rows("SELECT * FROM joylog1.san.case_block WHERE case_id = ? AND lifted_at IS NULL", (c["case_id"],))
        if not act:
            raise m.CaseError("%s: активных блоков по делу нет" % no)
        rows = dbx.rows("SELECT Reason, BlackDate, CloseDate FROM AsdaStoryOp.dbo.BlockList WHERE Userindex = ?", (c["user_index"],))
        foreign = [r for r in rows if not (r["Reason"] or "").startswith(no + " ")]
        if foreign and not a.all_blocks:
            for r in foreign:
                ctx.p("  чужой блок: %s .. %s «%s»" % (r["BlackDate"], r["CloseDate"], r["Reason"]))
            raise m.CaseError("у учётки есть блоки не этого дела - снятие (как OPBlockDel) снимет ВСЕ, подтвердите флагом «снять и чужие блоки» (all_blocks)")
        op = ops.REGISTRY["account.unblock"]
        if not self.pctx.can(op.perm):
            raise m.CaseError("снятие блока дела — операция account.unblock, нужно право «%s»" % op.perm)
        p = {"uid": int(c["user_index"]), "case": c["case_no"]}
        u0 = dbx.one("SELECT us_block FROM AsdaStoryOp.dbo.Us_member WHERE Userindex = ?", (c["user_index"],))
        need = bool(rows) or bool(u0 and u0["us_block"])
        aid = None
        if need:
            try:
                prev = op.preview(self.pctx, p)
            except OpRefused as ex:
                raise m.CaseError("account.unblock: %s" % ex)
            if self.dry:
                ctx.p("предпросмотр: %s" % prev["text"])
                for w in prev.get("warnings") or []:
                    ctx.p("  " + w)
                return
            try:
                res = op.apply(self.pctx, p, prev)
            except OpRefused as ex:
                raise m.CaseError("account.unblock: %s" % ex)
            aid = ops._finish(self.pctx, op.name, op.target(p), p, res, undo_of=None)
            self.comp.append((op.name, aid, p))
        elif self.dry:
            ctx.p("предпросмотр: строк BlockList нет, us_block = 0 - блок уже снят (истёк при входе или вне дела), отмечается в деле")
            return
        u = dbx.one("SELECT us_block, (SELECT COUNT(*) FROM AsdaStoryOp.dbo.BlockList b WHERE b.Userindex = m.Userindex) AS n "
                    "FROM AsdaStoryOp.dbo.Us_member m WHERE Userindex = ?", (c["user_index"],))
        if u["us_block"] != 0 or u["n"] != 0:
            raise m.CaseError("после account.unblock us_block = %s, строк BlockList %s - снятие откатывается" % (u["us_block"], u["n"]))
        via = ("панель account.unblock (как OPBlockDel), журнал №%d" % aid) if aid else "блок уже снят до lift (строк BlockList нет, us_block 0)"
        for b in act:
            hh = dbx.one("SELECT COUNT(*) AS n FROM AsdaStoryOp.dbo.BlockHistory WHERE Userindex = ? AND Reason = ?", (c["user_index"], b["reason"]))
            dbx.w("UPDATE joylog1.san.case_block SET lifted_by = ?, lifted_at = SYSDATETIME(), lift_via = ?, lift_text = ?, in_history = ? "
                  "WHERE block_id = ?", (ctx.actor, via, a.text, 1 if hh["n"] else 0, b["block_id"]))
        ok, lines = m.login_readiness(dbx, c["user_index"])
        dbx.log(c["case_id"], ctx.actor, "lift", ("блок снят (%s); %s; %s; проверка входа по БД: %s" %
                                                  (via, a.text or "", "сняты и чужие блоки: %d" % len(foreign) if foreign else "чужих блоков нет",
                                                   " | ".join(lines)))[:4000])
        m.write_manifest(dbx, ctx.root, c)
        ctx.p("%s: блок снят; BlockList -> BlockHistory; us_block = 0" % no)
        for ln in lines:
            ctx.p("  " + ln)

    # ---- отмена сделанного при сбое (блок / снятие уже зафиксированы своей записью журнала)
    def compensate(self, why):
        """Откатить выполненные account.block / account.unblock (их undo, новая запись журнала) → [тексты сбоев]."""
        bad = []
        for name, aid, p in reversed(self.comp):
            op = ops.REGISTRY[name]
            try:
                row = audit.get(aid)
                res = op.undo(self.pctx, row) or {}
                res["message"] = "%s (дело не записано: %s)" % (res.get("message", ""), why)
                ops._finish(self.pctx, name + ".undo", op.target(p), {"audit_id": aid}, res, undo_of=int(aid))
            except Exception as ex:
                try:
                    audit.write(self.pctx, name + ".undo", op.target(p), {"audit_id": aid}, result="error",
                                message="откат после сбоя дела не выполнен: %s" % str(ex)[:500])
                except Exception:
                    pass                                           # журнал недоступен — причина уходит в отказ вызывающему
                bad.append("%s №%d: %s" % (name, aid, ex))
        self.comp = []
        return bad


def _panel_db(m, J, R):
    """ac_case.Db исходника: запросы со схемой san.* (кроме сводки v_cases) — в транзакции записи J (asda_ops), прочие — чтением R
    (asda_admin, только SELECT). Запись — только J и только после assert_san_write исходника. Штатные скрипты блока не исполняются."""

    class PanelDb(m.Db):
        def __init__(self):
            self.cn = J.cn if J is not None else None

        def _cur(self, sql):
            if J is not None and LOG_SAN.search(sql) and "v_cases" not in sql:
                return J.cn.cursor()
            db.assert_select_only(sql)
            return R.cn.cursor()

        def rows(self, sql, params=()):
            cur = self._cur(sql)
            q = _x(sql)
            cur.execute(q, params) if params else cur.execute(q)
            if not cur.description:
                return []
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        def w(self, sql, params=()):
            m.assert_san_write(sql)
            if J is None:
                raise m.CaseError("просмотр дел ничего не пишет")
            cur = J.cn.cursor()
            q = _x(sql)
            cur.execute(q, params) if params else cur.execute(q)
            res = None
            while True:
                if cur.description and res is None:
                    cols = [c[0] for c in cur.description]
                    r = cur.fetchone()
                    res = dict(zip(cols, r)) if r else None
                if not cur.nextset():
                    break
            return res

        def run_script(self, text):
            raise m.CaseError("штатные скрипты блока в панели не исполняются - блок только операцией account.block")

        def commit(self):
            J.commit()

        def rollback(self):
            if J is not None:
                J.cn.rollback()
    return PanelDb()


def _high_step(pctx, step):
    """★ ревизия 59 Н-2: ступени ≥ DECIDE_HIGH — только с правом ac.decide (owner / admin); у gm (ac.decide_low) — ступени 0–2."""
    if step is not None and int(step) >= DECIDE_HIGH and not pctx.can("ac.decide"):
        raise OpRefused("решение со ступени %d — только администратор или владелец (gm — ступени 0–%d)" % (DECIDE_HIGH, DECIDE_HIGH - 1))


# ---------------------------------------------------------------- проверка ввода

def _s(p, key, need=False, lo=1, hi=200, what=None):
    v = p.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if need:
            raise OpRefused("дело: %s — обязательно" % (what or key))
        return None
    if not isinstance(v, str):
        raise OpRefused("дело: %s — строка" % (what or key))
    v = v.strip()
    if not lo <= len(v) <= hi or "\n" in v or "\r" in v:
        raise OpRefused("дело: %s — строка от %d до %d знаков без переводов строки" % (what or key, lo, hi))
    return v


def _case_no(p):
    m = CASE_RX.match(str(p.get("case") if p.get("case") is not None else "").strip())
    if not m or int(m.group(1)) <= 0:
        raise OpRefused("номер дела — AC-NNNN или число")
    return int(m.group(1))


def _int(v, lo, hi, what):
    if isinstance(v, bool) or v is None:
        raise OpRefused("дело: %s — целое от %d до %d" % (what, lo, hi))
    try:
        n = int(str(v).strip())
    except ValueError:
        raise OpRefused("дело: %s — целое от %d до %d" % (what, lo, hi))
    if not lo <= n <= hi:
        raise OpRefused("дело: %s — целое от %d до %d" % (what, lo, hi))
    return n


def _when(v, end=False):
    """ГГГГММДД[ ЧЧ:ММ] → datetime; конец окна без времени — начало следующих суток (сутки включительно)."""
    mm = DAY_RX.match(str(v or "").strip())
    if not mm:
        raise OpRefused("время окна — ГГГГММДД или «ГГГГММДД ЧЧ:ММ»")
    try:
        d = datetime.datetime.strptime(mm.group(1), "%Y%m%d")
        if mm.group(2):
            d = d.replace(hour=int(mm.group(2)), minute=int(mm.group(3)))
        elif end:
            d = d + datetime.timedelta(days=1)
    except ValueError:
        raise OpRefused("время окна — нет такой даты %s" % str(v).strip())
    return d


def _window(p):
    if p.get("from") in (None, "") and p.get("to") in (None, ""):
        return None
    t0, t1 = _when(p.get("from")), _when(p.get("to"), end=True)
    if t1 <= t0:
        raise OpRefused("окно: конец не позже начала")
    if (t1 - t0).days > 366:
        raise OpRefused("окно — не длиннее 366 суток")
    return t0, t1


def _flag(p, key):
    v = p.get(key)
    if v in (None, "", False, 0, "0"):
        return False
    if v in (True, 1, "1", "true"):
        return True
    raise OpRefused("дело: %s — да или нет" % key)


def _only(p, keys, op):
    extra = sorted(k for k in p if k not in keys and k != "expect")
    if extra:
        raise OpRefused("у операции %s нет параметра %s (есть: %s)" % (op, extra[0], ", ".join(keys)))


def _ascii(v, what):
    if v is not None and not ASCII_RX.match(v):
        raise OpRefused("дело: %s — только латиница (столбец Reason в кодировке базы)" % what)
    return v


# ---------------------------------------------------------------- операции

class _CaseOp(Operation):
    """База операции дела: разбор параметров → запуск команды исходника в транзакции (предпросмотр — с откатом)."""
    keys = ()
    owner_keys = ()          # параметры, которые может задать только владелец

    def target(self, p):
        if p.get("case") not in (None, ""):
            mm = CASE_RX.match(str(p.get("case")).strip())
            return "case:AC-%04d" % int(mm.group(1)) if mm else "case:?"
        return "account:%s" % (p.get("uid") or p.get("login") or "?")

    def args(self, ctx, p):
        raise NotImplementedError

    def run(self, S, a):
        return S.m.COMMANDS[self.cmd](S.k, a)

    def _check(self, ctx, p):
        _only(p, self.keys, self.name)
        for k in self.owner_keys:
            if p.get(k) not in (None, "", False) and ctx.role != "owner":
                raise OpRefused("параметр %s — только владелец" % k)
        return self.args(ctx, p)

    def _service(self, S, a, ctx):
        """Дела служебных учёток (≤ SVC_MAX) — только владелец; номер учётки дела или открываемой."""
        uid = None
        if getattr(a, "case", None):
            r = S.R.one(_x("SELECT user_index FROM joylog1.san.cases WHERE case_id = ?"), (S.m.parse_case_id(a.case),))
            if not r:
                raise OpRefused("дела %s нет" % a.case)
            uid = r["user_index"]
        elif getattr(a, "ui", None):
            uid = a.ui
        elif getattr(a, "user", None):
            r = S.R.one(_x("SELECT Userindex FROM AsdaStoryOp.dbo.Us_member WHERE us_id = ?"), (a.user,))
            uid = r["Userindex"] if r else None
        if uid is not None and int(uid) <= SVC_MAX and ctx.role != "owner":
            raise OpRefused("дела служебных учёток (номер ≤ %d) ведёт только владелец" % SVC_MAX)
        return uid

    def _go(self, ctx, p, dry):
        if ctx.via == "cli" and ctx.user_id is None:
            raise OpRefused(CLI_AS)
        a = self._check(ctx, p)
        S = Session(ctx, True, dry)
        try:
            self._service(S, a, ctx)
            if not dry and getattr(self, "confirm_case", False) and self.needs_confirm(S, a):
                want = "AC-%04d" % S.m.parse_case_id(a.case)
                if str(p.get("confirm") or "").strip().upper() != want:
                    raise OpRefused("подтвердите номером дела %s" % want)
            try:
                self.run(S, a)
            except S.m.CaseError as ex:
                raise OpRefused(str(ex).replace("; ", " — "))
            except db.DbError as ex:
                raise OpRefused("дела: %s" % ex)
            except Exception as ex:
                if ex.__class__.__module__ == "pyodbc":
                    raise OpRefused("база дел отказала: %s" % _sql_reason(ex))
                raise
            lines = S.lines()
        except BaseException as ex:
            S.db.rollback()
            S.k.cleanup()
            bad = S.compensate(str(ex)[:200]) if S.comp else []
            S.close()
            if bad:
                raise OpRefused("%s — и откат блока не выполнен: %s — проверьте учётку вручную" % (str(ex)[:300], "; ".join(bad)[:300]))
            raise
        if dry:
            S.db.rollback()
            S.k.cleanup()
            S.close()
            return {"text": lines[-1] if lines else self.title, "case_lines": lines, "warnings": [x.strip() for x in lines if "ВНИМАНИЕ" in x],
                    "case": getattr(a, "case", None)}
        return S, a, lines

    def preview(self, ctx, p):
        return self._go(ctx, p, True)

    def apply(self, ctx, p, prev):
        S, a, lines = self._go(ctx, p, False)
        no = getattr(a, "case", None)
        after = {"case_lines": lines[-40:]}
        try:
            if no is None and lines:
                mm = re.match(r"^(AC-\d+) открыто", lines[-1])
                no = mm.group(1) if mm else None
            if no:
                c = S.db.one("SELECT case_no, status, user_index, ladder_step, outcome FROM joylog1.san.cases WHERE case_id = ?",
                             (S.m.parse_case_id(no),))
                after.update({k: S.m.jval(v) for k, v in (c or {}).items()})
        except Exception:
            pass

        state = {"done": False}

        def commit():
            S.db.commit()
            state["done"] = True

        def close():
            """★ ревизия 59 Н-1: дело не зафиксировано (упала запись журнала самой операции, фиксация или что угодно после блока / снятия) —
            уже зафиксированные account.block / account.unblock откатываются своим undo; файлы этой команды удаляются."""
            try:
                if not state["done"]:
                    S.k.cleanup()
                    if S.comp:
                        bad = S.compensate("дело не записано")
                        if bad:
                            raise OpRefused("дело не записано — и откат блока не выполнен: %s — проверьте учётку вручную" % "; ".join(bad)[:300])
            finally:
                S.close()
        return {"before": None, "after": after, "message": lines[-1] if lines else self.title, "_commit": commit, "_close": close}


@register
class CaseOpen(_CaseOp):
    name, title, perm, cmd = "case.open", "Дело: открыть", "ac.case", "open"
    keys = ("uid", "login", "char", "title", "hypothesis", "training")

    def args(self, ctx, p):
        uid = p.get("uid")
        login = _s(p, "login", hi=61, what="логин")
        if (uid in (None, "")) == (login is None):
            raise OpRefused("учётка дела — номер (uid) или логин (login), одно из двух")
        if login is not None and not re.match(r"^[A-Za-z0-9_.@-]{1,61}$", login):
            raise OpRefused("логин — латиница, цифры и _.@-")
        ui = _int(uid, 1, 2147483647, "номер учётки") if login is None else None
        char = _s(p, "char", hi=32, what="персонаж")
        return argparse.Namespace(user=login, ui=ui, char=db.to_db_text(char) if char else None,
                                  title=_s(p, "title", need=True, hi=200, what="суть дела"),
                                  hypothesis=_s(p, "hypothesis", hi=2000, what="гипотеза"), training=_flag(p, "training"))

    def run(self, S, a):
        S.m.cmd_open(S.k, a)


@register
class CaseAttach(_CaseOp):
    name, title, perm, cmd = "case.attach", "Дело: приложить доказательства", "ac.case", "attach"
    keys = ("case", "events", "from", "to", "log", "needles", "label", "note")

    def args(self, ctx, p):
        case = "AC-%04d" % _case_no(p)
        ev = p.get("events") or []
        if not isinstance(ev, list) or len(ev) > EVENTS_MAX:
            raise OpRefused("события — список «таблица:номер» не длиннее %d" % EVENTS_MAX)
        for e in ev:
            if not isinstance(e, str) or not re.match(r"^(?:ac\.)?\w{1,32}[:#]\d{1,18}$", e):
                raise OpRefused("событие — «таблица:номер», например move_combat:7158")
        win = _window(p)
        log = p.get("log")
        needles = p.get("needles")
        label = _s(p, "label", hi=64, what="метка источника")
        if log is not None:
            if not ctx.can("logs.view"):
                raise OpRefused("выдержка журнала стойки — нужно право «logs.view»")
            if not isinstance(log, dict) or set(log) - {"source", "proc", "kind", "name"} or not all(isinstance(log.get(k), str) for k in ("source", "proc", "name")):
                raise OpRefused("журнал — {source, proc, kind, name} из списка «Журналы стойки»")
            if log.get("kind") is not None and not isinstance(log.get("kind"), str):
                raise OpRefused("журнал — {source, proc, kind, name} из списка «Журналы стойки»")
            if not isinstance(needles, list) or not 1 <= len(needles) <= NEEDLES_MAX or not all(
                    isinstance(x, str) and 2 <= len(x.strip()) <= 100 for x in needles):
                raise OpRefused("выдержка — от 1 до %d подстрок отбора по 2–100 знаков" % NEEDLES_MAX)
            needles = [x.strip() for x in needles]
            if label is None:
                raise OpRefused("для выдержки нужна метка источника (например «NpcServer SpeedHack»)")
        elif needles:
            raise OpRefused("подстроки отбора — только вместе с журналом")
        if not ev and not win and log is None:
            raise OpRefused("нечего прикладывать — события, окно событий учётки или выдержка журнала")
        return argparse.Namespace(case=case, event=list(ev) or None, events_auto=[t.isoformat() for t in win] if win else None,
                                  file=log, source=label, excerpt=needles, note=_s(p, "note", hi=400, what="пометка"))

    def run(self, S, a):
        if a.events_auto:
            if not S.dry:                                   # ★ ревизия 59 М-1: предпросмотр бюджет тяжёлого действия не списывает
                _heavy_charge(S.pctx.login)
            c = S.m.get_case(S.db, S.m.parse_case_id(a.case))
            t0, t1 = [datetime.datetime.fromisoformat(x) for x in a.events_auto]
            n = len(S.m.auto_event_pairs(S.db, c, t0, t1))
            if n > EVENTS_MAX:
                raise OpRefused("в окне %d событий учётки — больше %d, сузьте окно" % (n, EVENTS_MAX))
        S.m.cmd_attach(S.k, a)


@register
class CaseExport(_CaseOp):
    name, title, perm, cmd = "case.export", "Дело: выгрузить события", "ac.case", "export"
    keys = ("case", "format")

    def args(self, ctx, p):
        f = str(p.get("format") or "json,csv").strip()
        if f not in ("json", "csv", "json,csv", "csv,json"):
            raise OpRefused("формат выгрузки — json, csv или json,csv")
        return argparse.Namespace(case="AC-%04d" % _case_no(p), format=f)


@register
class CaseRollbackReport(_CaseOp):
    name, title, perm, cmd = "case.rollback_report", "Дело: отчёт отката по Serial", "ac.case", "rollback-report"
    keys = ("case", "serials", "from", "to", "max")

    def args(self, ctx, p):
        ss = p.get("serials") or []
        if not isinstance(ss, list) or len(ss) > SERIALS_MAX or not all(isinstance(s, str) and GUID_RX.match(s.strip()) for s in ss):
            raise OpRefused("серийники — список GUID (как Joy1.Item.Uuid) не длиннее %d" % SERIALS_MAX)
        win = _window(p)
        if not ss and not win:
            raise OpRefused("нет серийников — список GUID или окно учётки дела")
        mx = _int(p.get("max", ROLLBACK_MAX), 1, ROLLBACK_MAX, "серийников из окна")
        return argparse.Namespace(case="AC-%04d" % _case_no(p), serial=[s.strip() for s in ss] or None,
                                  window=[t.isoformat() for t in win] if win else None, max=mx)

    def run(self, S, a):
        if not S.dry:
            _heavy_charge(S.pctx.login)
        S.m.cmd_rollback_report(S.k, a)


@register
class CaseDecide(_CaseOp):
    name, title, perm, cmd = "case.decide", "Дело: вынести решение", "ac.decide_low", "decide"
    keys = ("case", "step", "hours", "text", "reason_en", "override_two_sources", "confirm")
    owner_keys = ("override_two_sources",)
    confirm_case = True

    def args(self, ctx, p):
        h = p.get("hours")
        return argparse.Namespace(case="AC-%04d" % _case_no(p), step=_int(p.get("step"), 0, 6, "ступень"),
                                  hours=None if h in (None, "") else _int(h, 1, 87600, "срок блока, часов"),
                                  text=_s(p, "text", need=True, hi=2000, what="основание решения"),
                                  reason_en=_ascii(_s(p, "reason_en", hi=200, what="причина латиницей"), "причина латиницей"),
                                  override_two_sources=_s(p, "override_two_sources", hi=400, what="почему без двух источников"), yes=True)

    def needs_confirm(self, S, a):
        return S.m.ladder_map(S.cfg)[a.step]["exec"] == "block"

    def run(self, S, a):
        _high_step(S.pctx, a.step)
        S.m.cmd_decide(S.k, a)


@register
class CaseExecute(_CaseOp):
    name, title, perm, cmd = "case.execute", "Дело: отметить исполнение", "ac.decide_low", "execute"
    keys = ("case", "text")

    def args(self, ctx, p):
        return argparse.Namespace(case="AC-%04d" % _case_no(p), text=_s(p, "text", need=True, hi=2000, what="что сделано"))

    def run(self, S, a):
        _high_step(S.pctx, S.m.get_case(S.db, S.m.parse_case_id(a.case))["ladder_step"])
        S.m.cmd_execute(S.k, a)


@register
class CaseWithdraw(_CaseOp):
    name, title, perm, cmd = "case.withdraw", "Дело: отозвать решение", "ac.decide_low", "withdraw"
    keys = ("case", "text")

    def args(self, ctx, p):
        return argparse.Namespace(case="AC-%04d" % _case_no(p), text=_s(p, "text", need=True, hi=2000, what="почему"))

    def run(self, S, a):
        _high_step(S.pctx, S.m.get_case(S.db, S.m.parse_case_id(a.case))["ladder_step"])
        S.m.cmd_withdraw(S.k, a)


@register
class CaseLift(_CaseOp):
    name, title, perm, cmd = "case.lift", "Дело: снять блок", "ac.decide", "lift"
    keys = ("case", "text", "all_blocks", "confirm")
    confirm_case = True

    def args(self, ctx, p):
        return argparse.Namespace(case="AC-%04d" % _case_no(p), text=_s(p, "text", hi=2000, what="пояснение") or "",
                                  all_blocks=_flag(p, "all_blocks"), yes=True)

    def needs_confirm(self, S, a):
        return True

    def run(self, S, a):
        S.lift(a)


@register
class CaseAppeal(_CaseOp):
    name, title, perm, cmd = "case.appeal", "Дело: апелляция", "ac.appeal", "appeal"
    keys = ("case", "text", "who", "late", "resolve")

    def args(self, ctx, p):
        r = p.get("resolve")
        if r not in (None, "", "upheld", "overturned"):
            raise OpRefused("решение по апелляции — upheld (в силе) или overturned (отменить)")
        return argparse.Namespace(case="AC-%04d" % _case_no(p), text=_s(p, "text", need=True, hi=2000, what="текст апелляции"),
                                  who=_s(p, "who", hi=64, what="кто подаёт"), late=_s(p, "late", hi=400, what="почему после срока"),
                                  resolve=r or None, same_person=None)

    def run(self, S, a):
        """Решение владельца №3: пересматривает ДРУГОЕ лицо — ключа исходника --same-person в панели нет (отказ до исходника, без
        подсказки про ключ консоли)."""
        if a.resolve:
            c = S.m.get_case(S.db, S.m.parse_case_id(a.case))
            if c["status"] == "appeal" and (c["decided_by"] or "") == S.k.actor:
                raise OpRefused("апелляцию пересматривает другое лицо — решение по делу выносил %s" % c["decided_by"])
        S.m.cmd_appeal(S.k, a)


@register
class CaseClose(_CaseOp):
    name, title, perm, cmd = "case.close", "Дело: закрыть", "ac.decide", "close"
    keys = ("case", "outcome", "text", "force_unverified")
    owner_keys = ("force_unverified",)

    def args(self, ctx, p):
        o = p.get("outcome")
        if o not in ("sanctioned", "acquitted", "no_action", "overturned"):
            raise OpRefused("итог дела — sanctioned, acquitted или no_action")
        return argparse.Namespace(case="AC-%04d" % _case_no(p), outcome=o, text=_s(p, "text", need=True, hi=2000, what="итог словами"),
                                  force_unverified=_s(p, "force_unverified", hi=400, what="почему без проверки целостности"))


# ---------------------------------------------------------------- чтение (без операций)

def _read(fn, ctx):
    S = Session(ctx, False, False)
    try:
        try:
            return fn(S)
        except S.m.CaseError as ex:
            raise OpRefused(str(ex).replace("; ", " — "))
        except db.DbError as ex:
            raise OpRefused("дела: %s" % ex)
        except Exception as ex:
            if ex.__class__.__module__ == "pyodbc":
                raise OpRefused("дела не прочитаны: %s" % _sql_reason(ex))
            raise
    finally:
        S.close()


def _j(r):
    out = {}
    for k, v in r.items():
        v = v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v
        out[k] = db.fix_text(v) if k in ("char_name", "login", "uid") and isinstance(v, str) else v
    return out


def ladder(ctx):
    """Лестница и правила дел из конфига исходника (как ac_case.py ladder без --check; сверка со стойкой — раздел «Автоблок»)."""
    m, cfg, src = source()
    lad = m.ladder_map(cfg)
    return {"ladder": [{"step": s, "code": lad[s]["code"], "name": lad[s]["name"], "hours": lad[s]["hours"], "exec": lad[s]["exec"],
                        "mechanism": lad[s]["mechanism"]} for s in sorted(lad)],
            "appeal_days": cfg["appeal_days"], "retention_days": cfg["retention_days"], "two_sources_from_step": cfg["two_sources_from_step"],
            "max_file_mb": cfg["max_file_mb"], "decide_high": DECIDE_HIGH, "source": src, "store": STORE_OVERRIDE or (CASES_ROOT if config.get().on_server else None),
            "can_write": bool(STORE_OVERRIDE or config.get().on_server), "store_note": None if (STORE_OVERRIDE or config.get().on_server) else STORE_PC}


def case_list(ctx, q):
    """Дела (san.v_cases) с фильтрами: status, account (номер или логин), training (0 / 1)."""
    q = q or {}
    st = q.get("status") or ""
    if st and st not in ("open", "evidence", "decision", "executed", "appeal", "closed"):
        raise OpRefused("статус дела — open, evidence, decision, executed, appeal или closed")
    acc = str(q.get("account") or "").strip()
    if acc and not re.match(r"^[A-Za-z0-9_.@-]{1,61}$", acc):
        raise OpRefused("учётка — номер или логин")
    tr = q.get("training") or ""
    if tr not in ("", "0", "1"):
        raise OpRefused("учебные — 0 или 1")

    def go(S):
        sql, prm = "SELECT TOP (%d) * FROM joylog1.san.v_cases WHERE 1 = 1" % LIST_MAX, []
        if st:
            sql += " AND status = ?"
            prm.append(st)
        if acc:
            if acc.isdigit():
                sql += " AND user_index = ?"
                prm.append(int(acc))
            else:
                sql += " AND login = ?"
                prm.append(acc)
        if tr:
            sql += " AND is_training = ?"
            prm.append(int(tr))
        rows = S.db.rows(sql + " ORDER BY case_id DESC", tuple(prm))
        return {"rows": [_j(r) for r in rows], "more": len(rows) >= LIST_MAX}
    return _read(go, ctx)


def show(ctx, case):
    """Дело целиком: поля, история, события, доказательства, блоки, BlockList учётки сейчас, источники (как render_case исходника)."""
    cid = _case_no({"case": case})

    def go(S):
        m, d = S.m, S.db
        c = m.get_case(d, cid)
        evs = d.rows("SELECT table_name, event_id, ev_local, server_name, user_index, char_name, ip, violation_type, summary, row_sha256, "
                     "attached_by, attached_at, note FROM joylog1.san.case_event WHERE case_id = ? ORDER BY ev_local", (cid,))
        return {"case": _j({k: m.jval(v) if not isinstance(v, datetime.datetime) else v for k, v in c.items()}),
                "log": [_j(r) for r in d.rows("SELECT log_id, at, actor, action, status_from, status_to, detail FROM joylog1.san.case_log "
                                               "WHERE case_id = ? ORDER BY log_id", (cid,))],
                "events": [_j(r) for r in evs],
                "evidence": [_j(r) for r in d.rows("SELECT evidence_id, kind, rel_path, size_bytes, sha256, source_label, source_path, "
                                                    "source_size, source_mtime, source_sha256, added_by, added_at, note FROM joylog1.san.evidence "
                                                    "WHERE case_id = ? ORDER BY evidence_id", (cid,))],
                "blocks": [_j(r) for r in d.rows("SELECT * FROM joylog1.san.case_block WHERE case_id = ? ORDER BY block_id", (cid,))],
                "blocklist_now": [_j(r) for r in d.rows("SELECT BlackDate, CloseDate, Reason FROM AsdaStoryOp.dbo.BlockList WHERE Userindex = ?",
                                                        (c["user_index"],))],
                "sources": m.case_sources(d, cid), "two_sources_from_step": S.cfg["two_sources_from_step"],
                "service": c["user_index"] <= SVC_MAX, "store": S.root, "md": m.render_case(d, S.root or "(каталог службы на сервере)", c)}
    return _read(go, ctx)


def verify(ctx, case=None):
    """Целостность (verify_case исходника): файлы и sha256, лишние файлы, manifest, снимки событий, связь с BlockList. Нужен каталог хранилища."""
    if store_root(write=False) is None:
        raise OpRefused(STORE_PC)
    if case in (None, ""):
        _heavy_charge(ctx.login)

    def go(S):
        m, d = S.m, S.db
        cases = [m.get_case(d, _case_no({"case": case}))] if case not in (None, "") else d.rows(
            "SELECT TOP (%d) * FROM joylog1.san.cases ORDER BY case_id" % LIST_MAX)
        out = []
        for c in cases:
            buf = io.StringIO()
            ok = m.verify_case(d, S.root, c, buf)
            out.append({"case_no": c["case_no"], "ok": bool(ok), "lines": [x.strip() for x in buf.getvalue().splitlines() if x.strip()]})
        return {"cases": out, "bad": [x["case_no"] for x in out if not x["ok"]], "store": S.root}
    return _read(go, ctx)


def for_account(ctx, uid):
    """Дела учётки (для карточки): номер, статус, ступень, итог."""
    return case_list(ctx, {"account": str(_int(uid, 1, 2147483647, "номер учётки"))})
